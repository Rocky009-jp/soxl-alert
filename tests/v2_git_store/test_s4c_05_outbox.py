"""S4C-10 .. S4C-13: the outbox on a git ref. A second clone sends nothing again and sees the same files as the S4-B
LocalOutbox would hold; the right to a name is decided by the push (a name that somebody else added first is not ours;
an uncertain push is judged by what the remote then holds; four tries at most; a rule that refuses the ref ends it at
once); a ref that does not exist is never an empty outbox; a damaged file is never sent over; the manual resend works as
on the local outbox."""
import errno
import json
import tempfile
import unittest

import s4c_helpers as H

GS, N, S, D, B = H.GS, H.N, H.S, H.D, H.B

MARKER = "v2-outbox-init"
LINE = "【再送】元の通知の送信を確認できなかったため、同じ内容を送ります"


def outbox_push(args):
    return args[0] == "push" and args[3].endswith(":refs/heads/" + H.OUTBOX)


def notice(i, kind="morning", text="a notice"):
    return N.Notice(kind, D[i], text, "DONE", None)


class Shared(H.Case):
    def setUp(self):
        super().setUp()
        self.w = H.world([1, 2, 3])
        self.remote, self.clone = H.start(self, self.w)

    def other(self, **kw):
        return H.Clone(self, self.remote, **kw)

    def claims(self):
        return sorted(n for n in self.remote.names(H.OUTBOX) if n.endswith(".claim.json"))


class SecondClone(Shared):
    """S4C-10."""

    def test_a_second_clone_runs_the_same_morning_and_sends_nothing_again(self):
        first = H.job(self.clone, self.w, 3, self.sender)
        self.assertEqual((first.run_outcome, first.delivery), ("DONE", "SENT"))
        second_clone = self.other()
        second = H.job(second_clone, self.w, 3, self.sender)
        self.assertEqual((second.run_outcome, second.delivery, second.existing_status), ("DONE", "SKIPPED_CLAIMED", "SENT"))
        self.assertEqual(len(self.sender.texts), 1)
        entries = N.outbox_status(second_clone.outbox, D[3])
        self.assertEqual([(e.kind, e.resend_request_id, e.status) for e in entries],
                         [("morning", None, "SENT"), ("halt", None, "NONE"), ("error", None, "NONE")])
        self.assertEqual(second.exit_code, 0)

    def test_the_files_on_the_ref_are_the_files_of_the_local_outbox_for_the_same_morning(self):
        H.job(self.clone, self.w, 3, self.sender)
        local_sender = B.Sender()
        root, out = tempfile.mkdtemp(prefix="v2s4c_local_"), tempfile.mkdtemp(prefix="v2s4c_out_")
        self.addCleanup(H.shutil.rmtree, root, True)
        self.addCleanup(H.shutil.rmtree, out, True)
        store = S.real_store(root, self.w)
        N.morning_job(store, N.LocalOutbox(out, B.MODE), local_sender, H.now_at(3), self.w.series, self.w.sessions,
                      self.w.ledger)
        on_ref = {n: d for n, d in self.remote.files(H.OUTBOX).items() if n != MARKER}
        local = B.snapshot(out)
        self.assertEqual(sorted(on_ref), sorted(local))
        self.assertEqual(self.remote.blob(H.OUTBOX, MARKER), b"v2-outbox\n")
        for name, data in on_ref.items():
            mine, theirs = json.loads(data.decode("utf-8")), json.loads(local[name].decode("utf-8"))
            self.assertEqual(sorted(mine), sorted(theirs), name)                # the same structure
            for key in mine:
                if key != "claim_id":
                    self.assertEqual(mine[key], theirs[key], (name, key))
        claim = json.loads(on_ref[D[3] + "-morning.claim.json"].decode("utf-8"))
        result = json.loads(on_ref[D[3] + "-morning.result.json"].decode("utf-8"))
        self.assertEqual(result["claim_id"], claim["claim_id"])
        self.assertEqual(self.sender.texts, local_sender.texts)

    def test_each_file_is_its_own_commit_added_on_the_last(self):
        H.job(self.clone, self.w, 3, self.sender)
        log = self.remote.log(H.OUTBOX)
        self.assertEqual([c["subject"] for c in log], ["v2 outbox init", "v2 outbox %s-morning.claim.json" % D[3],
                                                         "v2 outbox %s-morning.result.json" % D[3]])
        self.assertEqual(self.remote.names(H.OUTBOX), sorted([MARKER, D[3] + "-morning.claim.json",
                                                               D[3] + "-morning.result.json"]))


class Deciding(Shared):
    """S4C-11."""

    def rival(self, i=1, kind="halt", text="another key"):
        rival = self.other()

        def act(git, args):
            if outbox_push(args) and not act.done:
                act.done = True
                self.assertIsNotNone(rival.outbox.claim(notice(i, kind, text), H.now_at(i)))
        act.done = False
        return act

    def test_a_another_key_was_pushed_first_the_claim_is_made_again_and_succeeds(self):
        clone = self.other(git_cls=H.Scripted)
        clone.git.hooks["push"] = self.rival()
        claim_id = clone.outbox.claim(notice(3), H.now_at(3))
        self.assertIsNotNone(claim_id)
        self.assertEqual(self.claims(), sorted([D[1] + "-halt.claim.json", D[3] + "-morning.claim.json"]))
        self.assertEqual(json.loads(self.remote.blob(H.OUTBOX, D[3] + "-morning.claim.json"))["claim_id"], claim_id)
        self.assertEqual(len([c for c in clone.git.calls if outbox_push(c)]), 2)
        log = self.remote.log(H.OUTBOX)
        for before, after in zip(log, log[1:]):
            self.assertEqual(after["parents"], [before["sha"]])               # one line of fast-forwards

    def test_b_the_same_key_was_made_first_by_another_run_nothing_is_sent(self):
        clone = self.other(git_cls=H.Scripted)
        clone.git.hooks["push"] = self.rival(3, "morning", "the other run's notice")
        report = H.job(clone, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery, report.existing_status), ("DONE", "SKIPPED_CLAIMED", "UNKNOWN"))
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(json.loads(self.remote.blob(H.OUTBOX, D[3] + "-morning.claim.json"))["text"], "the other run's notice")
        self.assertEqual(self.claims(), [D[3] + "-morning.claim.json"])
        direct = self.other()
        self.assertIsNone(direct.outbox.claim(notice(3, "morning", "again"), H.now_at(3)))
        self.assertEqual(json.loads(self.remote.blob(H.OUTBOX, D[3] + "-morning.claim.json"))["text"], "the other run's notice")

    def test_c_an_uncertain_push_that_did_arrive_is_our_own_claim_and_is_sent_once(self):
        H.run(self.clone, self.w, 3)                               # the history is saved already: push 1 is the claim
        clone = self.other(git_cls=H.Lost, nth=1)
        report = H.job(clone, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SENT"))
        self.assertEqual(len(self.sender.texts), 1)
        claim = json.loads(self.remote.blob(H.OUTBOX, D[3] + "-morning.claim.json"))
        self.assertEqual(claim["text"], self.sender.texts[0])
        self.assertEqual(self.claims(), [D[3] + "-morning.claim.json"])
        self.assertEqual(len([c for c in clone.git.calls if outbox_push(c)]), 2)           # the claim, then the result
        self.assertEqual(N.outbox_status(clone.outbox, D[3])[0].status, "SENT")

    def test_d_an_uncertain_push_that_did_not_arrive_is_tried_once_more(self):
        H.run(self.clone, self.w, 3)
        clone = self.other(git_cls=H.Lost, nth=1, deliver=False)
        report = H.job(clone, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SENT"))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(self.claims(), [D[3] + "-morning.claim.json"])
        self.assertEqual(len([c for c in clone.git.calls if outbox_push(c)]), 3)           # lost claim, claim, result

    def test_e_four_times_beaten_by_other_keys_is_a_failure_to_claim_and_nothing_is_sent(self):
        rivals = [self.other() for _ in range(4)]
        clone = self.other(git_cls=H.Scripted)
        used = []

        def beat(git, args):
            if outbox_push(args):
                n = len(used)
                used.append(1)
                self.assertIsNotNone(rivals[n].outbox.claim(notice(n + 1, "halt", "rival %d" % n), H.now_at(n + 1)))
        clone.git.hooks["push"] = beat
        with self.assertRaises(N.NotifyError) as cm:
            clone.outbox.claim(notice(3), H.now_at(3))
        self.assertEqual(cm.exception.code, "outbox_io_error")
        self.assertEqual(len(used), 4)                                          # four tries, no fifth
        self.assertEqual(len([c for c in clone.git.calls if outbox_push(c)]), 4)
        self.assertNotIn(D[3] + "-morning.claim.json", self.remote.names(H.OUTBOX))
        # the same through the job
        clone2 = self.other(git_cls=H.Scripted)
        used2 = []
        rivals2 = [self.other() for _ in range(4)]

        def beat2(git, args):
            if outbox_push(args):
                n = len(used2)
                used2.append(1)
                rivals2[n].outbox.claim(notice(n + 1, "error", "rival2 %d" % n), H.now_at(n + 1))
        clone2.git.hooks["push"] = beat2
        report = H.job(clone2, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "CLAIM_FAILED"))
        self.assertEqual(self.sender.texts, [])

    def test_f_a_result_that_cannot_be_pushed_is_not_recorded_and_the_next_run_does_not_send(self):
        clone = self.other(git_cls=H.Scripted)
        calls = []

        def rule(args):
            if outbox_push(args):
                calls.append(1)
                if len(calls) >= 2:                      # the first outbox push is the claim; the result's pushes fail
                    return H.proc(128, b"", b"fatal")
            return None
        clone.git.rule = rule
        report = H.job(clone, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery, report.send_status), ("DONE", "RESULT_NOT_RECORDED", "SENT"))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(len(calls), 1 + 4)                                       # the claim and four tries of the result
        self.assertEqual(self.remote.names(H.OUTBOX), sorted([MARKER, D[3] + "-morning.claim.json"]))
        again = H.job(self.other(), self.w, 3, self.sender)
        self.assertEqual((again.delivery, again.existing_status), ("SKIPPED_CLAIMED", "UNKNOWN"))
        self.assertEqual(len(self.sender.texts), 1)

    def test_g_a_mirror_that_loses_a_file_does_not_let_the_same_key_be_sent_twice_nor_replace_the_intent(self):
        H.job(self.clone, self.w, 3, self.sender)
        files = self.remote.files(H.OUTBOX)
        head = self.remote.sha(H.OUTBOX)

        class Dropping(GS.GitOutbox):
            drop = ()

            def _rebuild(self):
                head = super()._rebuild()
                for name in self.drop:
                    try:
                        H.os.unlink(H.os.path.join(self._mirror, name))
                    except FileNotFoundError:
                        pass
                return head
        clone = self.other()
        broken = Dropping(clone.git, H.OUTBOX, clone.parent, H.clock)
        broken.drop = (D[3] + "-morning.claim.json", D[3] + "-morning.result.json")
        report = N.morning_job(clone.hist, broken, self.sender, H.now_at(3), self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SKIPPED_CLAIMED"))
        self.assertEqual(len(self.sender.texts), 1)                              # not sent twice
        self.assertEqual(self.remote.sha(H.OUTBOX), head)                         # nothing was pushed
        self.assertEqual(self.remote.files(H.OUTBOX), files)                       # the intent was not replaced
        self.assertIsNone(broken.claim(notice(3), H.now_at(3)))
        broken.drop = (D[3] + "-morning.result.json",)
        self.assertIs(broken.record(D[3], "morning", "0" * 32, "SENT", H.now_at(3)), False)
        self.assertEqual(self.remote.files(H.OUTBOX), files)
        # the pushes that were not made: only the pushes of the first job are in the log
        self.assertEqual(len(self.remote.log(H.OUTBOX)), 3)

    def test_h_a_rule_that_refuses_only_the_outbox_ref_ends_at_once(self):
        self.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/%s ] && exit 1; done; exit 0'
                         % H.OUTBOX)
        clone = self.other(git_cls=H.Scripted)
        report = H.job(clone, self.w, 3, self.sender)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "CLAIM_FAILED"))
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(len([c for c in clone.git.calls if outbox_push(c)]), 1)           # not repeated
        self.assertEqual(self.remote.names(H.OUTBOX), [MARKER])
        with self.assertRaises(N.NotifyError) as cm:
            self.other().outbox.claim(notice(3), H.now_at(3))
        self.assertEqual(cm.exception.code, "outbox_io_error")


class Initialization(H.Case):
    """S4C-12."""

    def setUp(self):
        super().setUp()
        self.w = H.world([1, 2, 3])
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote)
        self.clone.hist.initialize(H.S.genesis_pub(self.w))

    def test_a_no_ref_is_a_damaged_outbox_that_sends_nothing_and_makes_nothing(self):
        outbox = self.clone.outbox
        entry = outbox.status(D[3], "morning")
        self.assertEqual(entry.status, "DAMAGED")
        for kind in N.KINDS:
            self.assertEqual(outbox.status(D[3], kind).status, "DAMAGED")
        report = H.job(self.clone, self.w, 3, self.sender)
        self.assertEqual(report.run_outcome, "DONE")
        self.assertEqual((report.delivery, report.existing_status), ("SKIPPED_CLAIMED", "DAMAGED"))
        self.assertEqual(self.sender.texts, [])
        with self.assertRaises(N.NotifyError) as cm:
            outbox.claim(notice(3), H.now_at(3))
        self.assertEqual(cm.exception.code, "outbox_io_error")
        with self.assertRaises(N.NotifyError):
            outbox.record(D[3], "morning", "0" * 32, "SENT", H.now_at(3))
        with self.assertRaises(N.NotifyError):
            outbox.resend_ids(D[3], "morning")
        self.assertIsNone(self.remote.sha(H.OUTBOX))
        outbox.initialize()
        self.assertEqual(outbox.status(D[3], "morning").status, "NONE")
        self.assertEqual(self.remote.names(H.OUTBOX), [MARKER])

    def test_b_a_second_initialization_is_refused(self):
        self.clone.outbox.initialize()
        head = self.remote.sha(H.OUTBOX)
        for outbox in (self.clone.outbox, H.Clone(self, self.remote).outbox):
            with self.assertRaises(N.NotifyError) as cm:
                outbox.initialize()
            self.assertEqual(cm.exception.code, "already_initialized")
            self.assertCleanError(cm.exception)
        self.assertEqual(self.remote.sha(H.OUTBOX), head)

    def test_b_two_initializations_at_the_same_time_make_it_once(self):
        for _ in range(4):
            remote = H.Remote(self)
            clones = [H.Clone(self, remote) for _ in range(3)]
            signal = tempfile.mkdtemp(prefix="v2s4c_sig_")
            self.addCleanup(H.shutil.rmtree, signal, True)
            go = H.os.path.join(signal, "go")
            kids = [H.Child({"mode": "init", "clone": c.dir, "parent": c.parent, "go": go, "i": i}) for i, c in enumerate(clones)]
            try:
                for kid in kids:
                    kid.ready()
                S.signal(go)
                results = sorted(kid.result()["result"] for kid in kids)
            finally:
                for kid in kids:
                    if kid.proc.poll() is None:
                        kid.proc.kill()
                        kid.proc.communicate()
            self.assertEqual(results, ["OK", "already_initialized", "already_initialized"])
            self.assertEqual(remote.names(H.OUTBOX), [MARKER])
            self.assertEqual(len(remote.log(H.OUTBOX)), 1)

    def test_b_a_rule_that_refuses_the_ref_is_an_io_error_not_an_earlier_initialization(self):
        self.remote.hook("pre-receive", "exit 1")
        with self.assertRaises(N.NotifyError) as cm:
            self.clone.outbox.initialize()
        self.assertEqual(cm.exception.code, "outbox_io_error")
        self.assertIsNone(self.remote.sha(H.OUTBOX))

    def test_b_an_uncertain_initialization_that_arrived_is_done_and_one_that_did_not_is_an_error(self):
        clone = H.Clone(self, self.remote, git_cls=H.Lost)
        clone.outbox.initialize()
        self.assertEqual(self.remote.names(H.OUTBOX), [MARKER])
        remote = H.Remote(self)
        lost = H.Clone(self, remote, git_cls=H.Lost, deliver=False)
        with self.assertRaises(N.NotifyError) as cm:
            lost.outbox.initialize()
        self.assertEqual(cm.exception.code, "outbox_io_error")
        self.assertIsNone(remote.sha(H.OUTBOX))

    def plant_damaged(self, extra):
        files = {MARKER: b"v2-outbox\n"}
        files.update(extra)
        self.remote.plant(H.OUTBOX, files, parent=None)

    def valid_claim_of(self, i):
        """The bytes of a real claim of day i (made by the S4-B local outbox)."""
        out = tempfile.mkdtemp(prefix="v2s4c_out_")
        self.addCleanup(H.shutil.rmtree, out, True)
        N.LocalOutbox(out, B.MODE).claim(notice(i), H.now_at(i))
        return B.bread(out, D[i] + "-morning.claim.json")

    def test_c_damaged_intents_on_the_ref_are_never_sent_over(self):
        good = self.valid_claim_of(3)
        wrong_day = self.valid_claim_of(2)
        cases = {
            "empty": b"",
            "not json": b"{ not json",
            "wrong key": wrong_day,                                         # a claim of another day under this name
            "extra field": B.canonical(dict(json.loads(good.decode("utf-8")), extra=1)),
            "bad hash": B.canonical(dict(json.loads(good.decode("utf-8")), text_sha256="0" * 64)),
        }
        for label, data in cases.items():
            self.remote = H.Remote(self)
            self.clone = H.Clone(self, self.remote)
            self.clone.hist.initialize(H.S.genesis_pub(self.w))
            self.plant_damaged({D[3] + "-morning.claim.json": data})
            self.assertEqual(self.clone.outbox.status(D[3], "morning").status, "DAMAGED", label)
            sender = B.Sender()
            report = H.job(self.clone, self.w, 3, sender)
            self.assertEqual((report.run_outcome, report.delivery, report.existing_status), ("DONE", "SKIPPED_CLAIMED", "DAMAGED"),
                             label)
            self.assertEqual(sender.texts, [], label)
            self.assertEqual(self.remote.blob(H.OUTBOX, D[3] + "-morning.claim.json"), data, label)
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote)
        self.plant_damaged({D[3] + "-morning.result.json": b'{"claim_id":"x"}'})          # a result without a claim
        self.assertEqual(self.clone.outbox.status(D[3], "morning").status, "DAMAGED")

    def test_c_entries_that_are_not_plain_files_make_the_whole_outbox_unreadable(self):
        for mode, name in (("120000", "link"), ("100644", "bad name.json"), ("100644", "Ünï.json"), ("100755", "x" * 201),
                           ("100644", ".hidden"), ("100644", "-dash")):
            remote = H.Remote(self)
            blob = H.text(H.tgit(remote.path, "hash-object", "-w", "--stdin", data=b"x"))
            tree = H.tgit(remote.path, "mktree", data=("%s blob %s\t%s\n" % (mode, blob, name)).encode("utf-8"))
            commit = H.text(H.tgit(remote.path, "commit-tree", H.text(tree), "-m", "x"))
            H.tgit(remote.path, "update-ref", "refs/heads/" + H.OUTBOX, commit)
            clone = H.Clone(self, remote)
            self.assertEqual(clone.outbox.status(D[3], "morning").status, "DAMAGED", (mode, name))
            with self.assertRaises(N.NotifyError):
                clone.outbox.claim(notice(3), H.now_at(3))
        remote = H.Remote(self)
        blob = H.text(H.tgit(remote.path, "hash-object", "-w", "--stdin", data=b"x"))
        sub = H.text(H.tgit(remote.path, "mktree", data=("100644 blob %s\tx\n" % blob).encode("utf-8")))
        tree = H.text(H.tgit(remote.path, "mktree", data=("040000 tree %s\tdir\n" % sub).encode("utf-8")))
        commit = H.text(H.tgit(remote.path, "commit-tree", tree, "-m", "x"))
        H.tgit(remote.path, "update-ref", "refs/heads/" + H.OUTBOX, commit)
        clone = H.Clone(self, remote)
        self.assertEqual(clone.outbox.status(D[3], "morning").status, "DAMAGED")

    def test_d_a_write_into_the_mirror_that_fails_midway_leaves_nothing_on_the_remote(self):
        self.clone.outbox.initialize()
        head = self.remote.sha(H.OUTBOX)
        for method, nth in (("create_exclusive", 1), ("open_writer", 1), ("write", 1), ("flush", 1), ("fsync_file", 1),
                            ("close", 1)):
            ops = B.Ops({method: (nth, OSError(errno.EIO, "io"))})
            outbox = GS.GitOutbox(self.clone.git, H.OUTBOX, self.clone.parent, H.clock, _ops=ops)
            with self.assertRaises(N.NotifyError) as cm:
                outbox.claim(notice(3), H.now_at(3))
            self.assertEqual(cm.exception.code, "outbox_io_error", method)
            self.assertCleanError(cm.exception)
            self.assertEqual(self.remote.sha(H.OUTBOX), head, method)
            self.assertEqual(self.remote.names(H.OUTBOX), [MARKER], method)
            self.assertEqual(outbox.status(D[3], "morning").status, "NONE", method)       # the mirror is rebuilt from the ref
        report = H.job(self.clone, self.w, 3, self.sender)
        self.assertEqual(report.delivery, "SENT")


class Resend(H.Case):
    """S4C-13: the cases (a) to (f) of S4B-14 over the git outbox."""

    def setUp(self):
        super().setUp()
        self.w = H.world([1, 2, 3])
        self.remote, self.clone = H.start(self, self.w)
        self.late = B.Sender(TimeoutError("late"))
        self.original = H.job(self.clone, self.w, 3, self.late)               # UNKNOWN
        self.key = D[3] + "-morning"

    def resend(self, rid, sender=None, d=None, kind="morning", clone=None, hour=22):
        clone = clone or self.clone
        return N.resend(clone.outbox, sender or self.sender, d or D[3], kind, rid, H.now_at(3, hour))

    def test_an_unknown_original_is_sent_again_once_from_another_clone_with_one_line_in_front(self):
        self.assertEqual(self.original.delivery, "UNKNOWN")
        before = self.remote.files(H.OUTBOX)
        report = self.resend("req1", clone=H.Clone(self, self.remote))
        self.assertEqual((report.delivery, report.send_status, report.original_status, report.exit_code),
                         ("SENT", "SENT", "UNKNOWN", 0))
        self.assertEqual(self.sender.texts, [LINE + "\n" + self.late.texts[0]])
        after = self.remote.files(H.OUTBOX)
        for name, data in before.items():
            self.assertEqual(after[name], data, name)
        self.assertEqual(sorted(set(after) - set(before)),
                         [self.key + ".resend-req1.claim.json", self.key + ".resend-req1.result.json"])
        claim = json.loads(after[self.key + ".resend-req1.claim.json"].decode("utf-8"))
        original = json.loads(before[self.key + ".claim.json"].decode("utf-8"))
        self.assertEqual((claim["text"], claim["resend_of"], claim["kind"], claim["d"]),
                         (LINE + "\n" + self.late.texts[0], original["claim_id"], "morning", D[3]))
        result = json.loads(after[self.key + ".resend-req1.result.json"].decode("utf-8"))
        self.assertEqual((result["claim_id"], result["status"]), (claim["claim_id"], "SENT"))

    def test_the_same_id_again_is_not_sent_and_after_a_sent_resend_every_other_id_is_refused(self):
        down = B.Sender(TimeoutError("late"))
        self.assertEqual(self.resend("req1", sender=down).delivery, "UNKNOWN")
        for clone in (self.clone, H.Clone(self, self.remote)):
            again = self.resend("req1", clone=clone)
            self.assertEqual((again.delivery, again.send_status, again.exit_code), ("SKIPPED_CLAIMED", None, 1))
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(self.resend("req2").delivery, "SENT")                      # after an UNKNOWN resend, another id sends
        for rid in ("req3", "req1", "req2"):
            self.assertIn(self.resend(rid).delivery, ("REFUSED_ALREADY_SENT", "SKIPPED_CLAIMED"))
        self.assertEqual(self.resend("req3").delivery, "REFUSED_ALREADY_SENT")
        self.assertEqual(len(self.sender.texts), 1)

    def test_an_original_that_was_sent_is_refused_and_no_original_is_refused(self):
        remote, clone = H.start(self, self.w)
        H.job(clone, self.w, 3, self.sender)
        report = N.resend(clone.outbox, self.sender, D[3], "morning", "req1", H.now_at(3, 22))
        self.assertEqual((report.delivery, report.original_status), ("REFUSED_ALREADY_SENT", "SENT"))
        self.assertEqual(self.resend("req1", d=D[1]).delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(self.resend("req1", kind="halt").delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(self.resend("req1", kind="error").delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(len(self.sender.texts), 1)

    def test_a_damaged_original_and_a_damaged_resend_are_refused(self):
        down = B.Sender(TimeoutError("late"))
        self.assertEqual(self.resend("req1", sender=down).delivery, "UNKNOWN")
        files = self.remote.files(H.OUTBOX)
        files[self.key + ".resend-req1.result.json"] = b"{"
        self.remote.plant(H.OUTBOX, files)
        for rid in ("req1", "req2"):
            self.assertEqual(self.resend(rid).delivery, "REFUSED_DAMAGED", rid)
        files[self.key + ".claim.json"] = b""
        self.remote.plant(H.OUTBOX, files)
        self.assertEqual(self.resend("req2").delivery, "REFUSED_DAMAGED")
        self.assertEqual(self.sender.texts, [])

    def test_a_not_started_original_is_sent_again_and_a_sender_that_fails_gives_unknown(self):
        remote, clone = H.start(self, self.w)
        H.job(clone, self.w, 3, B.Sender("NOT_STARTED"))
        sent = N.resend(clone.outbox, self.sender, D[3], "morning", "again", H.now_at(3, 22))
        self.assertEqual((sent.delivery, sent.original_status), ("SENT", "NOT_SENT"))
        for answer in (TimeoutError("t"), None, "OK"):
            remote, clone = H.start(self, self.w)
            H.job(clone, self.w, 3, B.Sender(TimeoutError("late")))
            sender = B.Sender([answer])
            report = N.resend(clone.outbox, sender, D[3], "morning", "req1", H.now_at(3, 22))
            self.assertEqual((report.delivery, report.send_status), ("UNKNOWN", "UNKNOWN"))
            self.assertEqual(len(sender.texts), 1)

    def test_a_resend_whose_ids_cannot_be_listed_says_so_and_sends_nothing(self):
        clone = H.Clone(self, self.remote, git_cls=H.Scripted)
        calls = []

        def rule(args):
            if args[0] == "fetch":
                calls.append(1)
                if len(calls) >= 2:                          # the first fetch reads the original; resend_ids is the next
                    return H.proc(128, b"", b"fatal")
            if args[0] == "ls-remote" and len(calls) >= 2:
                return H.proc(128, b"", b"fatal")
            return None
        clone.git.rule = rule
        report = self.resend("req1", clone=clone)
        self.assertEqual((report.delivery, report.original_status), ("CLAIM_FAILED", None))
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(self.remote.names(H.OUTBOX), sorted([MARKER, self.key + ".claim.json", self.key + ".result.json"]))

    def test_a_resend_never_replaces_or_removes_a_file_of_the_ref(self):
        before = self.remote.files(H.OUTBOX)
        self.resend("req1")
        after = self.remote.files(H.OUTBOX)
        self.assertTrue(set(before) < set(after))
        for name, data in before.items():
            self.assertEqual(after[name], data)
        log = self.remote.log(H.OUTBOX)
        for before_c, after_c in zip(log, log[1:]):
            self.assertEqual(after_c["parents"], [before_c["sha"]])
            self.assertEqual(len(after_c["names"]), len(before_c["names"]) + 1)


if __name__ == "__main__":
    unittest.main()
