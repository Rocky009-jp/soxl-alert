"""S4E-02: everything of a run is decided once (R2-P01). One clock read for `now` (the same value reaches load_inputs and
morning_job), one Git and one outbox that every part uses, the refs of a mode never touch the other mode's refs, and the
temporary directory of a run is gone at its end."""
import os
import tempfile
import unittest
from unittest import mock

import s4e_helpers as H

R, ENTRY = H.R, H.ENTRY
DAYS = H.days("2026-07-21", "2026-07-24")


class Counting(object):
    """Wraps a class: records every construction and keeps the instances."""

    def __init__(self, cls):
        self.cls, self.made = cls, []

    def __call__(self, *args, **kwargs):
        obj = self.cls(*args, **kwargs)
        self.made.append((obj, args, kwargs))
        return obj


class Once(H.D.Case):
    def test_the_clock_is_read_once_for_now_and_the_same_value_reaches_both_parts(self):
        work = H.Work(self)
        net = H.Net()
        self.assertEqual(work.init(net, "dry").code, 0)
        net.provider = H.D.Provider(DAYS[0])
        work.sync_ledger(H.START, DAYS[0])
        seen = {}
        real_load, real_job = ENTRY.load_inputs, ENTRY.morning_job

        def load(git, fetch, now, refs, clock):
            seen["load"] = (now, git, clock)
            return real_load(git, fetch, now, refs, clock)

        def job(store, outbox, sender, now, series, sessions, rows):
            seen["job"] = (now, outbox, sender)
            return real_job(store, outbox, sender, now, series, sessions, rows)
        now = H.aware(DAYS[0])
        with mock.patch.object(ENTRY, "load_inputs", load), mock.patch.object(ENTRY, "morning_job", job):
            result = work.run(net, ["morning", "--mode", "dry"], now, clock_step=11)
        self.assertEqual(result.code, 0)
        self.assertEqual(seen["load"][0], now)
        self.assertEqual(seen["job"][0], now)
        self.assertIs(seen["load"][0], seen["job"][0])
        self.assertEqual(result.kv["now_utc"], now.isoformat(timespec="seconds"))
        self.assertGreater(result.clock.calls, 1)           # the commits read the function again (and get later times)
        self.assertIs(seen["load"][2], result.clock)        # the function itself goes to load_inputs for the pin commit
        log = work.remote.log("v2-dry-market")
        self.assertGreater(log[-1]["ct"], int(now.timestamp()))

    def test_setup_reads_the_clock_exactly_once(self):
        work = H.Work(self)
        clock = H.Clock(H.aware(DAYS[0]), 5)
        scratch = tempfile.mkdtemp(prefix="v2s4e_scratch_")
        self.addCleanup(__import__("shutil").rmtree, scratch, True)
        setup = R.Setup("dry", work.dir, {}, H.Net(), clock, scratch)
        self.assertEqual(clock.calls, 1)
        self.assertEqual(setup.now, H.aware(DAYS[0]))
        self.assertEqual(setup.refs, R.MODES["dry"])

    def test_one_git_and_one_outbox_serve_every_part(self):
        work = H.Work(self)
        net = H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        work.sync_ledger(H.START, DAYS[0])
        git, outbox, store = Counting(ENTRY.Git), Counting(ENTRY.GitOutbox), Counting(ENTRY.GitHistoryStore)
        seen = {}
        real_load, real_job, real_status = ENTRY.load_inputs, ENTRY.morning_job, ENTRY.outbox_status

        def load(g, *rest):
            seen["load_git"] = g
            return real_load(g, *rest)

        def job(store_, outbox_, *rest):
            seen["job_outbox"] = outbox_
            return real_job(store_, outbox_, *rest)

        def status(outbox_, d):
            seen["status_outbox"] = outbox_
            return real_status(outbox_, d)
        patches = (mock.patch.object(ENTRY, "Git", git), mock.patch.object(ENTRY, "GitOutbox", outbox),
                   mock.patch.object(ENTRY, "GitHistoryStore", store), mock.patch.object(ENTRY, "load_inputs", load),
                   mock.patch.object(ENTRY, "morning_job", job), mock.patch.object(ENTRY, "outbox_status", status))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            self.assertEqual(work.cmd(net, "morning", "dry", DAYS[0]).code, 0)
            self.assertEqual(len(git.made), 1)
            self.assertEqual((len(outbox.made), len(store.made)), (1, 1))
            self.assertIs(outbox.made[0][1][0], git.made[0][0])         # the outbox and the store are built on that one Git
            self.assertIs(store.made[0][1][0], git.made[0][0])
            self.assertIs(seen["load_git"], git.made[0][0])
            self.assertIs(seen["job_outbox"], outbox.made[0][0])
            self.assertEqual(outbox.made[0][1][1], "v2-dry-outbox")
            self.assertEqual(store.made[0][1][1], "v2-dry-state")
            # status: the same outbox that was built is read
            self.assertEqual(work.cmd(net, "status", "dry", DAYS[0], extra=["--date", DAYS[0]]).code, 0)
            self.assertIs(seen["status_outbox"], outbox.made[1][0])
            self.assertEqual(len(git.made), 2)                        # one more per run, never more

    def test_resend_reads_and_sends_through_the_one_outbox(self):
        work = H.Work(self)
        net = H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        self.assertEqual(work.morning(net, "dry", DAYS[0]).code, 0)
        outbox = Counting(ENTRY.GitOutbox)
        seen = {}
        real = ENTRY.resend

        def resend(outbox_, *rest):
            seen["outbox"] = outbox_
            return real(outbox_, *rest)
        with mock.patch.object(ENTRY, "GitOutbox", outbox), mock.patch.object(ENTRY, "resend", resend):
            work.cmd(net, "resend", "dry", DAYS[0], extra=["--date", DAYS[0], "--kind", "morning", "--request-id", "r1"])
        self.assertIs(seen["outbox"], outbox.made[0][0])
        self.assertEqual(len(outbox.made), 1)


class RefsOfTheModes(H.D.Case):
    def test_a_dry_run_never_touches_the_live_refs_and_a_live_run_never_touches_the_dry_refs(self):
        work = H.Work(self)
        net = H.Net(DAYS[0])
        live_names = H.STATE_REFS["live"]
        dry_names = H.STATE_REFS["dry"]
        self.assertEqual(work.init(net, "dry").code, 0)
        for day in DAYS[:3]:
            self.assertEqual(work.morning(net, "dry", day).code, 0)
        self.assertEqual(work.v2_heads(*live_names), {n: None for n in live_names})
        self.assertEqual(sorted(k for k in work.heads() if k.startswith("v2-")),
                         ["v2-dry-market", "v2-dry-outbox", "v2-dry-state", "v2-ledger"])
        dry_before = work.v2_heads(*dry_names)
        self.assertTrue(all(dry_before.values()))
        self.assertEqual(work.init(net, "live", start=H.START).code, 0)
        self.assertEqual(work.morning(net, "live", DAYS[3]).code, 0)
        self.assertEqual(work.v2_heads(*dry_names), dry_before)
        self.assertTrue(all(work.v2_heads(*live_names).values()))
        # the ledger is the one ref that both modes read and neither writes
        self.assertEqual(len(work.remote.log("v2-ledger")), len(set(l["sha"] for l in work.remote.log("v2-ledger"))))
        self.assertEqual(net.posts()[0]["behaviour"], "204")
        self.assertEqual(len(net.posts()), 1)           # only the live morning posted

    def test_the_commits_of_a_run_are_made_with_the_time_of_the_clock_function(self):
        work = H.Work(self)
        net = H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        log = work.remote.log("v2-dry-state")
        self.assertEqual(log[0]["ct"], int(H.aware(H.D.next_day(H.START), 7, 0).timestamp()))


class ScratchDirectory(H.D.Case):
    def setUp(self):
        super().setUp()
        self.work = H.Work(self)                         # made before the temporary root is changed
        self.root = tempfile.mkdtemp(prefix="v2s4e_tmp_")
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        patch = mock.patch.object(tempfile, "tempdir", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_scratch_directory_is_made_in_the_run_and_removed_at_its_end(self):
        work = self.work
        net = H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        self.assertEqual(os.listdir(self.root), [])
        mid = []
        real = ENTRY.morning_job

        def job(store, outbox, *rest):
            mid.append(sorted(n for n in os.listdir(self.root) if n.startswith("v2run_")))
            return real(store, outbox, *rest)
        with mock.patch.object(ENTRY, "morning_job", job):
            self.assertEqual(work.morning(net, "dry", DAYS[0]).code, 0)
        self.assertEqual(len(mid[0]), 1)
        self.assertEqual(os.listdir(self.root), [])
        # also when the command fails
        result = work.cmd(net, "status", "dry", DAYS[0], extra=["--date", DAYS[0]], workdir=os.path.join(self.root, "missing"))
        self.assertEqual(result.code, 1)
        self.assertEqual(os.listdir(self.root), [])


if __name__ == "__main__":
    unittest.main()
