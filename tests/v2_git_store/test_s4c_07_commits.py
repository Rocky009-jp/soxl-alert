"""S4C-15: the shape of every commit on the remote, read by `git` directly. v2-state: each commit has one parent (the first
none) and a tree with history.json only (what was on the parent's tree besides is kept); v2-outbox: each commit has one parent
and adds exactly one file to its parent's tree (the first has the marker only). Author and committer are fixed, the date is
the date of the injected clock, the message is a fixed word with a short hash or a file name. Every head is a descendant of
the one before: the refs moved by fast-forwards only."""
import unittest

from datetime import timedelta

import s4c_helpers as H

S, N, D, B = H.S, H.N, H.D, H.B

MARKER = "v2-outbox-init"


class Shape(H.Case):
    def setUp(self):
        super().setUp()
        self.w = H.world(range(1, 5))
        self.clk = H.Tick()
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote, self.clk)
        self.clone.hist.initialize(S.genesis_pub(self.w))
        self.clone.outbox.initialize()

    def fixed(self, row, at):
        self.assertEqual(row["author"], ("v2-runner", "runner@invalid"))
        self.assertEqual(row["committer"], ("v2-runner", "runner@invalid"))
        self.assertEqual((row["at"], row["ct"]), (int(at.timestamp()), int(at.timestamp())))
        self.assertEqual(row["ad"], "%d +0900" % int(at.timestamp()))

    def test_every_commit_of_the_history_ref_has_one_parent_and_only_history_json(self):
        for i in range(1, 5):
            self.assertEqual(H.run(self.clone, self.w, i).outcome, "DONE")
        log = self.remote.log(H.STATE)
        self.assertEqual(len(log), 5)
        self.assertEqual(log[0]["parents"], [])
        for before, after in zip(log, log[1:]):
            self.assertEqual(after["parents"], [before["sha"]])
            self.assertEqual(H.tgit(self.remote.path, "merge-base", "--is-ancestor", before["sha"], after["sha"],
                                    check=False).returncode, 0)
        for row in log:
            self.assertEqual(row["names"], ["history.json"])
        modes = H.text(H.tgit(self.remote.path, "ls-tree", "-r", "refs/heads/" + H.STATE))
        self.assertTrue(modes.startswith("100644 blob "))
        # the messages: a fixed word and the first 12 characters of the publication's hash (made independently here)
        history = S.expected_history(self.w, 0)
        want = ["v2 history %s" % S.U.publish_genesis(self.w.start_after, self.w.sessions).publication_hash[:12]]
        for i in range(1, 5):
            pub = S.U.publish_day(history, D[i], self.w.series, self.w.sessions, self.w.ledger)
            want.append("v2 history %s" % pub.publication_hash[:12])
            history = S.expected_history(self.w, i)
        self.assertEqual([r["subject"] for r in log], want)
        # the bytes of each commit are the bytes of the independent chain
        for k, row in enumerate(log):
            data = H.tgit(self.remote.path, "cat-file", "blob", "%s:history.json" % row["sha"]).stdout
            self.assertEqual(data, S.expected_bytes(self.w, k))

    def test_author_committer_and_date_come_from_the_injected_clock_one_call_per_commit(self):
        for i in range(1, 3):
            H.run(self.clone, self.w, i)
        H.job(self.clone, self.w, 2, self.sender)
        rows = self.remote.log(H.STATE) + self.remote.log(H.OUTBOX)
        self.assertEqual(len(rows), 3 + 3)                 # genesis, two days; marker, claim, result
        times = sorted(r["at"] for r in rows)
        self.assertEqual(times, [int(H.WHEN.timestamp()) + k for k in range(len(rows))])      # one call of the clock for each
        for row in rows:
            self.fixed(row, H.WHEN + timedelta(seconds=row["at"] - int(H.WHEN.timestamp())))

    def test_every_commit_of_the_outbox_ref_adds_one_file_to_its_parent(self):
        H.job(self.clone, self.w, 4, self.sender)
        H.job(self.clone, self.w, 4, B.Sender())                                   # SKIPPED_CLAIMED: nothing more
        N.resend(self.clone.outbox, self.sender, D[4], "morning", "req1", H.now_at(4, 22))      # refused: it was sent
        log = self.remote.log(H.OUTBOX)
        self.assertEqual(log[0]["parents"], [])
        self.assertEqual(log[0]["names"], [MARKER])
        self.assertEqual(log[0]["subject"], "v2 outbox init")
        for before, after in zip(log, log[1:]):
            self.assertEqual(after["parents"], [before["sha"]])
            self.assertEqual(len(after["names"]), len(before["names"]) + 1)
            added = sorted(set(after["names"]) - set(before["names"]))
            self.assertEqual(len(added), 1)
            self.assertEqual(after["subject"], "v2 outbox " + added[0])
            self.assertEqual(sorted(set(before["names"]) - set(after["names"])), [])
            for name in before["names"]:                                            # nothing was replaced
                self.assertEqual(
                    H.text(H.tgit(self.remote.path, "rev-parse", "%s:%s" % (before["sha"], name))),
                    H.text(H.tgit(self.remote.path, "rev-parse", "%s:%s" % (after["sha"], name))))
            self.assertEqual(H.tgit(self.remote.path, "merge-base", "--is-ancestor", before["sha"], after["sha"],
                                    check=False).returncode, 0)
        self.assertEqual([r["subject"] for r in log[1:]], ["v2 outbox %s-morning.claim.json" % D[4],
                                                           "v2 outbox %s-morning.result.json" % D[4]])
        for row in log:
            self.assertEqual(row["author"], ("v2-runner", "runner@invalid"))
            self.assertEqual(row["committer"], ("v2-runner", "runner@invalid"))
            self.assertNotIn(H.MARK, row["subject"])

    def test_the_other_entries_of_the_parents_tree_are_kept_by_both_kinds_of_commit(self):
        remote = H.Remote(self)
        clone = H.Clone(self, remote)
        root = S.make_root()
        self.addCleanup(H.shutil.rmtree, root, True)
        S.real_store(root, self.w)
        remote.plant(H.STATE, {"history.json": S.raw(root), "README": b"kept"}, parent=None)
        pub = S.U.publish_day(clone.hist.read(), D[1], self.w.series, self.w.sessions, self.w.ledger)
        clone.hist.publish(pub)
        self.assertEqual(remote.names(H.STATE), ["README", "history.json"])
        self.assertEqual(remote.blob(H.STATE, "README"), b"kept")
        self.assertNotEqual(remote.blob(H.STATE, "history.json"), S.raw(root))
        remote.plant(H.OUTBOX, {MARKER: b"v2-outbox\n", "keep.json": b"{}"}, parent=None)
        self.assertIsNotNone(clone.outbox.claim(N.Notice("morning", D[1], "t", "DONE", None), H.now_at(1)))
        self.assertEqual(remote.names(H.OUTBOX), sorted([MARKER, "keep.json", D[1] + "-morning.claim.json"]))
        self.assertEqual(remote.blob(H.OUTBOX, "keep.json"), b"{}")

    def test_a_beaten_save_leaves_no_commit_on_the_ref_and_no_ref_other_than_the_two_is_made(self):
        H.run(self.clone, self.w, 4)
        H.job(self.clone, self.w, 4, self.sender)
        self.assertEqual(sorted(self.remote.refs()), ["refs/heads/" + H.OUTBOX, "refs/heads/" + H.STATE])


if __name__ == "__main__":
    unittest.main()
