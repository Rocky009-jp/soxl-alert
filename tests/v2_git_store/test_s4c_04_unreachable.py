"""S4C-09: the remote cannot be reached at each step of a morning. The remote directory is renamed (or deleted) right
before the k-th network command (fetch or push) of one morning_job, for every k of the clean run. Whatever k is: no exception
leaves, no mark of the remote path is shown anywhere, at most one send happens, and a send happens only with a claim on the
remote. The named steps have the outcome of the design (history steps: STOPPED store_io_error and no send)."""
import shutil
import unittest

import s4c_helpers as H

S, N = H.S, H.N

NETWORK = ("fetch", "push")


class Outage(H.Case):
    def setUp(self):
        super().setUp()
        self.w = H.world([1])

    def scene(self, k=None, how="rename"):
        """One morning_job on D1 over a seeded remote; the remote goes away right before the k-th network command."""
        w = self.w
        remote = H.Remote(self)
        seed = H.Clone(self, remote)
        seed.hist.initialize(S.genesis_pub(w))
        seed.outbox.initialize()
        clone = H.Clone(self, remote, git_cls=H.Scripted)
        count = []
        gone = H.Gone(remote)

        def before(git, args):
            if args[0] in NETWORK:
                count.append(args[0])
                if k is not None and len(count) == k:
                    if how == "rename":
                        gone.__enter__()
                    else:
                        shutil.rmtree(remote.path)
        for name in NETWORK:
            clone.git.hooks[name] = before
        sender = H.B.Sender()
        report = H.job(clone, w, 1, sender)
        self.see(report, sender.texts)
        return remote, clone, report, sender, count, gone

    def test_the_clean_run_has_the_eight_network_commands_of_the_design(self):
        remote, clone, report, sender, count, gone = self.scene()
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SENT"))
        self.assertEqual(count, ["fetch", "fetch", "push", "fetch", "fetch", "push", "fetch", "push"])
        self.assertEqual(len(sender.texts), 1)

    def test_every_step_in_turn(self):
        expected = {  # k: (run_outcome, code, kind, delivery, number of sends)
            1: ("STOPPED", "store_io_error", "halt", "SKIPPED_JUDGMENT_EXISTS", 0),     # the history cannot be read
            2: ("STOPPED", "store_io_error", "halt", "SKIPPED_JUDGMENT_EXISTS", 0),     # the fetch of the publication
            3: ("STOPPED", "store_io_error", "halt", "SKIPPED_JUDGMENT_EXISTS", 0),     # the push, then no reconcile
            4: ("DONE", None, "morning", "SKIPPED_CLAIMED", 0),                         # the outbox cannot be read: DAMAGED
            5: ("DONE", None, "morning", "CLAIM_FAILED", 0),
            6: ("DONE", None, "morning", "CLAIM_FAILED", 0),
            7: ("DONE", None, "morning", "RESULT_NOT_RECORDED", 1),
            8: ("DONE", None, "morning", "RESULT_NOT_RECORDED", 1),
        }
        for how in ("rename", "delete"):
            for k, want in expected.items():
                remote, clone, report, sender, count, gone = self.scene(k, how)
                got = (report.run_outcome, report.code if report.run_outcome == "STOPPED" else None, report.kind,
                       report.delivery, len(sender.texts))
                self.assertEqual(got, want, (how, k))
                self.assertGreaterEqual(len(count), k)
                self.assertNoMark()
                if how == "rename":
                    gone.__exit__()
                    self.after_outage(remote, k, want)

    def after_outage(self, remote, k, want):
        """The remote comes back: what is there is what the steps before the outage did, and nothing is sent twice."""
        self.assertIsNotNone(remote.sha(H.STATE))
        history_saved = remote.blob(H.STATE, "history.json") == S.expected_bytes(self.w, 1)
        self.assertEqual(history_saved, k >= 4)                  # the push (3) is the one that saves the day
        files = remote.files(H.OUTBOX)
        claims = [n for n in files if n.endswith(".claim.json")]
        results = [n for n in files if n.endswith(".result.json")]
        if k <= 5:
            self.assertEqual((claims, results), ([], []))
        if k == 7:
            self.assertEqual((len(claims), results), (1, []))
        if want[4] == 1:
            self.assertEqual(len(claims), 1)
        else:
            self.assertEqual(claims, [])

    def test_whatever_the_step_nothing_is_sent_twice_when_the_morning_is_run_again(self):
        for k in range(1, 9):
            remote, clone, report, sender, count, gone = self.scene(k)
            gone.__exit__()
            again = H.job(clone, self.w, 1, sender)
            self.see(again, sender.texts)
            if report.delivery in ("RESULT_NOT_RECORDED", "SENT"):
                self.assertEqual(len(sender.texts), 1, k)                           # an intent without a result: not sent
                self.assertEqual(again.delivery, "SKIPPED_CLAIMED")
                self.assertEqual(again.existing_status, "UNKNOWN")
            else:
                self.assertEqual(len(sender.texts), 1, k)                           # the second run gave the judgment
                self.assertEqual((again.run_outcome, again.kind), ("DONE", "morning"))
            self.assertNoMark()

    def test_the_outbox_state_and_the_initializations_fail_cleanly_when_the_remote_is_gone(self):
        w = self.w
        remote, clone = H.start(self, w)
        sender = H.B.Sender()
        H.job(clone, w, 1, sender)
        with H.Gone(remote):
            with self.assertRaises(N.NotifyError) as cm:
                N.outbox_status(clone.outbox, D1)
            self.assertCleanError(cm.exception)
            self.assertEqual(cm.exception.code, "outbox_io_error")
            entry = clone.outbox.status(D1, "morning")
            self.assertEqual(entry.status, "DAMAGED")
            self.see(entry)
            fresh = H.Clone(self, remote)
            with self.assertRaises(S.LocalStoreError) as cm:
                fresh.hist.initialize(S.genesis_pub(w))
            self.assertEqual(cm.exception.code, "store_io_error")
            self.assertCleanError(cm.exception)
            with self.assertRaises(N.NotifyError) as cm:
                fresh.outbox.initialize()
            self.assertEqual(cm.exception.code, "outbox_io_error")
            self.assertCleanError(cm.exception)
            with self.assertRaises(S.LocalStoreError):
                fresh.hist.read()
        self.assertNoMark()
        self.assertEqual(N.outbox_status(clone.outbox, D1)[0].status, "SENT")             # back again


D1 = H.D[1]

if __name__ == "__main__":
    unittest.main()
