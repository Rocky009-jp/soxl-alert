"""S4B-13 and S4B-16: failures of the outbox's file operations (no send without a claim; an unrecorded result leaves the
claim, so a rerun does not send; no __context__ or __cause__), the order of the writes, and the sweep that injects an
error at every call point of the sender, the store and the file operations: the job returns a JobReport or raises the
injected non-CoreError object itself; nothing is sent twice."""
import errno
import os
import unittest

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P

WRITE_STEPS = ["create_exclusive", "open_writer", "write", "flush", "fsync_file", "close", "fsync_dir"]


class Order(H.Case):
    def test_one_file_is_written_in_the_order_of_the_request_and_nothing_is_replaced_or_removed(self):
        S.decide(self.w, [1, 2, 3])
        ops = H.Ops()
        self.job(H.now_at(D[3]), outbox=self.outbox(ops))
        writes = [c for c in ops.calls if c in WRITE_STEPS]
        self.assertEqual(writes, WRITE_STEPS + WRITE_STEPS)             # the claim, then the result
        self.assertNotIn("replace", ops.calls)
        self.assertNotIn("unlink", ops.calls)
        self.assertEqual(ops.count["create_exclusive"], 2)

    def test_a_short_write_is_completed_and_a_zero_write_is_an_error_not_a_loop(self):
        class Short(H.Ops):
            def write(self, writer, data):
                return H.FileOps.write(self, writer, data[:7])
        S.decide(self.w, [1, 2, 3])
        report = self.job(H.now_at(D[3]), outbox=self.outbox(Short()))
        self.assertEqual(report.delivery, "SENT")
        self.assertEqual(H.jread(self.oroot, D[3] + "-morning.claim.json")["text"], self.last_text())

        class Zero(H.Ops):
            def write(self, writer, data):
                return 0
        self.setUp()
        S.decide(self.w, [1, 2, 3])
        report = self.job(H.now_at(D[3]), outbox=self.outbox(Zero()))
        self.assertEqual((report.delivery, self.sender.texts), ("CLAIM_FAILED", []))

    def test_the_text_is_written_as_utf8_as_it_is(self):
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[3]))
        raw = H.bread(self.oroot, D[3] + "-morning.claim.json")
        self.assertIn("【SOXL日次】".encode("utf-8"), raw)
        self.assertNotIn(b"\\u", raw)


class Claim(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])
        self.now = H.now_at(D[3])

    def with_fault(self, method, n, error):
        self.setUp()
        ops = H.Ops({method: (n, error)})
        report = self.job(self.now, outbox=self.outbox(ops))
        return report, ops

    def test_no_claim_means_no_send(self):
        for method in WRITE_STEPS:
            for error in (OSError(errno.EIO, "io"), PermissionError("p"), H.CoreError("disk_full", "x"), OSError(errno.ENOSPC, "full")):
                report, ops = self.with_fault(method, 1, error)
                label = "%s %r" % (method, error)
                self.assertEqual((report.delivery, report.send_status, report.exit_code), ("CLAIM_FAILED", None, 1), label)
                self.assertEqual(self.sender.texts, [], label)
                self.assertEqual(ops.count["create_exclusive"], 1, label)
                self.assertFalse([n for n in H.names(self.oroot) if n.endswith(".result.json")], label)
                if method == "create_exclusive":
                    self.assertEqual(H.names(self.oroot), [], label)
                # a file that was created is closed, even on the failure path
                if method == "open_writer":
                    self.assertIn("close_fd", ops.calls, label)
                elif method != "create_exclusive" and method != "close":
                    self.assertIn("close", ops.calls, label)

    def test_after_a_claim_that_could_not_be_created_a_healthy_rerun_sends_once(self):
        report, _ops = self.with_fault("create_exclusive", 1, OSError(errno.EIO, "io"))
        self.assertEqual(H.names(self.oroot), [])
        again = self.job(self.now)
        self.assertEqual((again.delivery, again.exit_code), ("SENT", 0))
        self.assertEqual(len(self.sender.texts), 1)

    def test_after_a_claim_that_was_started_a_healthy_rerun_does_not_send(self):
        for method in ("open_writer", "write", "flush", "fsync_file", "close", "fsync_dir"):
            self.with_fault(method, 1, OSError(errno.EIO, "io"))
            again = self.job(self.now)
            self.assertEqual(again.delivery, "SKIPPED_CLAIMED", method)
            self.assertIn(again.existing_status, ("DAMAGED", "UNKNOWN"), method)
            self.assertEqual(self.sender.texts, [], method)

    def test_an_exclusive_creation_that_finds_the_name_taken_does_not_hold_the_right(self):
        report, _ops = self.with_fault("create_exclusive", 1, FileExistsError(errno.EEXIST, "exists"))
        self.assertEqual((report.delivery, report.exit_code, self.sender.texts), ("SKIPPED_CLAIMED", 1, []))

    def test_the_error_that_the_outbox_raises_keeps_no_context_cause_or_os_text(self):
        notice = N.compose_notice(self.reference(self.now), self.w.sessions, self.now)
        for method in WRITE_STEPS:
            for k in (1,):
                ops = H.Ops({method: (k, OSError(errno.EIO, "secret /private/path"))})
                outbox = self.outbox(ops)
                with self.assertRaises(N.NotifyError) as ctx:
                    outbox.claim(notice, self.now)
                error = ctx.exception
                self.assertIsNone(error.__context__, method)
                self.assertIsNone(error.__cause__, method)
                self.assertEqual((error.code, error.field, error.detail), ("outbox_io_error", "outbox", None), method)
                self.assertNotIn("secret", str(error))
                self.assertNotIn("/private", repr(error))
                self.setUp()
        self.setUp()
        listing = self.outbox(H.Ops({"listdir": (1, OSError(errno.EIO, "secret"))}))
        with self.assertRaises(N.NotifyError) as ctx:
            listing.resend_ids(D[3], "morning")
        self.assertIsNone(ctx.exception.__context__)


class Durability(H.Case):
    """N-01: the directory sync is optional through durability, as in the C-3 history store. file_sync_only writes the same
    bytes in the same steps and skips only the directory sync (a host that cannot sync a directory, such as Windows)."""

    SYNC_FAILS = (OSError(errno.EINVAL, "no directory sync here"))

    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])
        self.now = H.now_at(D[3])

    def outbox_of(self, durability, ops=None):
        return N.LocalOutbox(self.oroot, durability, _ops=ops)

    def test_the_default_is_strict_and_only_the_two_words_are_accepted(self):
        ops = H.Ops()
        self.job(self.now, outbox=N.LocalOutbox(self.oroot, _ops=ops))
        self.assertEqual(ops.count["fsync_dir"], 2)
        before = H.snapshot(self.oroot)
        for bad in ("", "STRICT", "file-sync-only", "relaxed", None, 0, True, b"strict", ("strict",), ["strict"]):
            with self.assertRaises(N.NotifyError) as cm:
                N.LocalOutbox(self.oroot, bad)
            self.assertEqual(cm.exception.code, "notify_args_invalid", repr(bad))
        self.assertEqual(H.snapshot(self.oroot), before)

    def test_strict_with_a_directory_sync_that_fails_creates_no_notice_and_sends_nothing(self):
        ops = H.Ops({"fsync_dir": (1, self.SYNC_FAILS)})
        report = self.job(self.now, outbox=self.outbox_of("strict", ops))
        self.assertEqual((report.delivery, report.exit_code), ("CLAIM_FAILED", 1))
        self.assertEqual(self.sender.texts, [])

    def test_file_sync_only_writes_the_same_bytes_in_the_same_steps_without_the_directory_sync(self):
        strict_root = self.oroot
        ops_strict = H.Ops()
        self.job(self.now, outbox=self.outbox_of("strict", ops_strict))
        steps = [c for c in ops_strict.calls if c in WRITE_STEPS]
        self.setUp()
        ops = H.Ops()
        report = self.job(self.now, outbox=self.outbox_of("file_sync_only", ops))
        self.assertEqual((report.delivery, report.send_status, report.exit_code), ("SENT", "SENT", 0))
        self.assertEqual([c for c in ops.calls if c in WRITE_STEPS], [c for c in steps if c != "fsync_dir"])
        self.assertNotIn("fsync_dir", ops.calls)
        names = [D[3] + "-morning.claim.json", D[3] + "-morning.result.json"]
        self.assertEqual(H.names(self.oroot), names)
        for name in names:                       # the same keys and the same text; only the claim id and the times differ
            mine, theirs = H.jread(self.oroot, name), H.jread(strict_root, name)
            self.assertEqual(sorted(mine), sorted(theirs))
        self.assertEqual(H.jread(self.oroot, names[0])["text_sha256"], H.jread(strict_root, names[0])["text_sha256"])
        self.assertEqual(H.jread(self.oroot, names[1])["status"], "SENT")

    def test_where_the_directory_cannot_be_synced_file_sync_only_sends_and_strict_does_not(self):
        report = self.job(self.now, outbox=self.outbox_of("file_sync_only", H.Ops({"fsync_dir": (1, self.SYNC_FAILS)})))
        self.assertEqual((report.delivery, report.exit_code), ("SENT", 0))
        self.assertEqual(len(self.sender.texts), 1)
        entry = N.outbox_status(self.outbox_of("file_sync_only"), D[3], "morning")[0]
        self.assertEqual(entry.status, "SENT")

    def test_the_halt_the_error_and_the_manual_resend_also_work_without_the_directory_sync(self):
        class NoDirSync(H.Ops):
            def fsync_dir(self, path):
                raise OSError(errno.EINVAL, "no directory sync here")
        ops = NoDirSync()
        out = self.outbox_of("file_sync_only", ops)
        down = H.Sender(TimeoutError("late"))
        self.assertEqual(self.job(self.now, sender=down, outbox=out).send_status, "UNKNOWN")
        again = N.resend(out, self.sender, D[3], "morning", "req-1", H.now_at(D[3], 20))
        self.assertEqual((again.delivery, again.exit_code), ("SENT", 0))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual([e.status for e in N.outbox_status(out, D[3], "morning")], ["UNKNOWN", "SENT"])
        halt_out = self.outbox_of("file_sync_only", NoDirSync())
        halted = N.morning_job(self.store(), halt_out, self.sender, H.now_at(D[0], 18), self.w.series, self.w.sessions,
                               self.w.ledger)
        self.assertEqual(halted.delivery, "SENT")
        err = N.morning_job(self.store(), self.outbox_of("file_sync_only", NoDirSync()), self.sender, H.now_at(D[0], 8),
                            self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual(err.delivery, "SENT")

    def test_a_fault_in_any_other_step_is_still_an_outbox_error_in_file_sync_only(self):
        for method in ("create_exclusive", "open_writer", "write", "flush", "fsync_file", "close"):
            self.setUp()
            ops = H.Ops({method: (1, OSError(errno.EIO, "io"))})
            report = self.job(self.now, outbox=self.outbox_of("file_sync_only", ops))
            self.assertEqual(report.delivery, "CLAIM_FAILED", method)
            self.assertEqual(self.sender.texts, [], method)


class Result(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])
        self.now = H.now_at(D[3])

    def test_a_result_that_cannot_be_recorded_leaves_the_claim_and_the_next_run_does_not_send(self):
        # what the file reads back as: nothing was created / an empty file / the whole file (the bytes were written)
        for method, status in (("create_exclusive", "UNKNOWN"), ("open_writer", "DAMAGED"), ("write", "DAMAGED"),
                               ("flush", "SENT"), ("fsync_file", "SENT"), ("close", "SENT"), ("fsync_dir", "SENT")):
            self.setUp()
            ops = H.Ops({method: (2, OSError(errno.EIO, "io"))})
            report = self.job(self.now, outbox=self.outbox(ops))
            self.assertEqual((report.delivery, report.send_status, report.exit_code), ("RESULT_NOT_RECORDED", "SENT", 1), method)
            self.assertEqual(len(self.sender.texts), 1, method)
            self.assertIn(D[3] + "-morning.claim.json", H.names(self.oroot), method)
            self.assertEqual(N.outbox_status(self.outbox(), D[3], "morning")[0].status, status, method)
            again = self.job(H.now_at(D[3], 19))
            self.assertEqual((again.delivery, again.existing_status), ("SKIPPED_CLAIMED", status), method)
            self.assertEqual(len(self.sender.texts), 1, method)

    def test_a_result_that_already_exists_is_not_replaced(self):
        class Plant(H.Ops):
            def create_exclusive(self, path):
                if path.endswith(".result.json"):
                    H.bwrite(os.path.dirname(path), os.path.basename(path), b"planted")
                return H.Ops.create_exclusive(self, path)
        report = self.job(self.now, outbox=self.outbox(Plant()))
        self.assertEqual((report.delivery, report.send_status), ("RESULT_NOT_RECORDED", "SENT"))
        self.assertEqual(H.bread(self.oroot, D[3] + "-morning.result.json"), b"planted")


class Sweep(H.Case):
    """S4B-16. For every call point of the sender, the store and the file operations, for several errors, in three
    scenarios (a judgment, a halt, an error notice): the job returns a JobReport or raises the injected object itself
    (never a CoreError); one send at most per key, also after a healthy rerun."""

    ERRORS = (lambda: H.CoreError("injected_core_error", "x"), lambda: OSError(errno.EIO, "injected"),
              lambda: PermissionError("injected"))

    def scenario(self, name):
        self.setUp()
        if name == "morning":
            S.decide(self.w, [1, 2, 3])
            return H.now_at(D[3]), None
        if name == "halt":
            self.w = P.World(0, unconfirmed=(D[4],))
            S.decide(self.w, [1, 2, 3])
            return H.now_at(D[4]), None
        S.decide(self.w, [1])
        return H.now_at(D[2]), H.RaisingSeries(ZeroDivisionError("program error"))

    def build(self, name, plan):
        """(now, series, sender, store, ops, outbox) of a fresh scenario with one planned fault."""
        now, series = self.scenario(name)
        sender = Plan(H.Sender(), plan.get("sender"))
        store = Plan(self.store(), None, plan.get("store"))
        ops = H.Ops({plan["ops"][0]: (plan["ops"][1], plan["ops"][2])} if "ops" in plan else {})
        return now, series, sender, store, ops, self.outbox(ops)

    def execute(self, name, plan):
        now, series, sender, store, ops, outbox = self.build(name, plan)
        kw = {} if series is None else {"series": series}
        injected = [v for v in (plan.get("sender"), plan.get("store", (None, None))[1] if "store" in plan else None,
                                plan["ops"][2] if "ops" in plan else None) if v is not None]
        try:
            report = N.morning_job(store, outbox, sender, now, kw.get("series", self.w.series), self.w.sessions, self.w.ledger)
        except BaseException as e:
            if name == "error" and isinstance(e, ZeroDivisionError):
                report = "program error"
            else:
                self.assertTrue(any(e is x for x in injected), "an unexpected exception %r" % (e,))
                self.assertNotIsInstance(e, H.CoreError)
                report = e
        else:
            self.assertIsInstance(report, N.JobReport)
        self.assertLessEqual(len(sender.inner.texts), 1)               # one send at most in one job
        return now, series, sender, store, ops, outbox, report

    def points(self, name):
        now, series, sender, store, ops, outbox, _ = self.execute(name, {})
        counts = {("sender", "send"): sender.n}
        counts.update({("store", m): c for m, c in store.counts.items()})
        counts.update({("ops", m): c for m, c in ops.count.items() if m != "lstat"})
        return counts

    def test_the_sweep(self):
        total = 0
        for name in ("morning", "halt", "error"):
            points = self.points(name)
            self.assertGreaterEqual(len(points), 8, name)
            for (component, method), calls in sorted(points.items()):
                for k in range(1, calls + 1):
                    for make in self.ERRORS:
                        error = make()
                        if component == "sender":
                            plan = {"sender": error}
                        elif component == "store":
                            plan = {"store": (method, error)}
                        else:
                            plan = {"ops": (method, k, error)}
                        if component == "store" and k > 1 and method != "publish":
                            continue
                        total += 1
                        now, series, sender, store, ops, outbox, report = self.execute(name, plan)
                        again_sender = H.Sender()
                        kw = {} if series is None else {"series": series}
                        try:
                            N.morning_job(self.store_for_rerun(store), self.outbox(), again_sender, now,
                                          kw.get("series", self.w.series), self.w.sessions, self.w.ledger)
                        except ZeroDivisionError:
                            pass
                        kinds = [H.kind_of(t) for t in sender.inner.texts + again_sender.texts]
                        for kind in set(kinds):
                            self.assertEqual(kinds.count(kind), 1, (name, component, method, k, error, kinds))
        self.assertGreater(total, 150)
        self.__class__.swept = total

    def store_for_rerun(self, planned):
        return planned.inner


class Plan(object):
    """Wraps a sender or a store; fails the planned call once (the sender: its first call; the store: the planned
    method's first call, or its k-th for publish) and counts calls."""

    def __init__(self, inner, sender_error=None, store_plan=None):
        self.inner, self.sender_error, self.store_plan = inner, sender_error, store_plan
        self.n, self.counts = 0, {}

    def send(self, text):
        self.n += 1
        answer = self.inner.send(text)
        if self.sender_error is not None:
            raise self.sender_error
        return answer

    def _call(self, name, *args):
        self.counts[name] = self.counts.get(name, 0) + 1
        if self.store_plan is not None and self.store_plan[0] == name and self.counts[name] == 1:
            raise self.store_plan[1]
        return getattr(self.inner, name)(*args)

    def read(self):
        return self._call("read")

    def publish(self, publication):
        return self._call("publish", publication)

    def reconcile(self, publication):
        return self._call("reconcile", publication)


if __name__ == "__main__":
    unittest.main()
