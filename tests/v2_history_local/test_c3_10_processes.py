"""C3-13: independent processes. Children are started only with sys.executable and tests/v2_history_local/c3_worker.py
(through c3_helpers.Worker). A forced stop (a SIGKILL of the child; skipped on Windows) is made at a chosen point
while the child waits, never by sleeping for a time."""
import sys
import os
import unittest

import c3_helpers as H

SAFE_REFUSALS = {"store_busy", "publication_stale", "publication_refused"}


class Probe(H.RootCase):
    def test_a_child_has_no_network_and_is_a_different_process(self):
        w = H.Worker({"mode": "probe"})
        ev = w.result()
        self.assertTrue(ev["socket_blocked"])
        self.assertNotEqual(ev["pid"], os.getpid())

    def test_a_child_publishes_and_the_parent_reads_it(self):
        h, pub, w = H.day1_root(self.root)
        ev = H.Worker({"root": self.root, "mode": "one"}).result()
        self.assertEqual((ev["ok"], ev["status"], ev["head_seq"]), (True, "PUBLISHED", 1))
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(H.U.check_publication(H.C2.file_bytes(h), pub)))
        self.assertEqual(self.store(writable=False).read().head_seq, 1)
        self.assertEqual(H.listing(self.root), ["history.json"])


class Contention(H.RootCase):
    def test_six_processes_race_for_the_same_day_and_exactly_one_wins(self):
        h, pub, w = H.day1_root(self.root)
        start = H.C2.file_bytes(h)
        workers = [H.Worker({"root": self.root, "mode": "race", "attempts": 15, "wait_go": True}) for _ in range(6)]
        for worker in workers:
            self.addCleanup(worker.kill)
        for worker in workers:
            worker.expect("READY")
        for worker in workers:
            worker.send("GO")
        outcomes = [o for worker in workers for o in worker.result()["outcomes"]]
        self.assertEqual(len(outcomes), 6 * 15)
        self.assertEqual(outcomes.count("PUBLISHED"), 1)
        self.assertEqual(set(outcomes) - {"PUBLISHED"} - SAFE_REFUSALS, set())
        self.assertGreater(outcomes.count("store_busy") + outcomes.count("publication_refused"), 0)
        final = self.store(writable=False).read()
        self.assertEqual(final.head_seq, 1)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(H.U.check_publication(start, pub)))
        self.assertEqual(H.listing(self.root), ["history.json"])


@unittest.skipIf(sys.platform == "win32", "a forced stop by SIGKILL is not made on Windows")
class ForcedStop(H.RootCase):
    def stopped_at(self, point):
        h, pub, w = H.day1_root(self.root)
        start = H.raw(self.root)
        worker = H.Worker({"root": self.root, "mode": "one", "hook": {"point": point, "action": "pause"}})
        self.addCleanup(worker.kill)
        worker.expect("AT")
        worker.kill()                                    # SIGKILL: no clean-up of the child runs
        return h, pub, start

    def test_stopped_after_the_tmp_is_written_and_before_the_replace(self):
        for point in ("after_tmp_close", "before_replace"):
            with self.subTest(point=point):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                h, pub, start = self.stopped_at(point)
                names = H.listing(root)
                tmp = [n for n in names if n.startswith(".history.") and n.endswith(".tmp")]
                self.assertEqual(sorted(set(names) - set(tmp)), ["history.json", "write.lock"])
                self.assertEqual(len(tmp), 1)
                self.assertEqual(H.raw(root), start)             # still the previous valid history
                self.assertEqual(H.raw(root, tmp[0]), H.C2.file_bytes(H.U.check_publication(start, pub)))
                for op, args in (("read", ()), ("publish", (pub,)), ("reconcile", (pub,))):
                    self.assertEqual(self.run_err(getattr(self.store(), op), *args).code, "store_busy")
                os.unlink(os.path.join(root, H.LOCK))             # the test unlocks by hand (C-4 will do it)
                self.assertEqual(self.run_err(self.store().publish, pub).code, "store_artifact_present")
                self.assertEqual(self.run_err(self.store().read).code, "store_artifact_present")
                self.assertEqual(self.store().reconcile(pub).outcome, "NOT_PUBLISHED")
                self.assertEqual(H.raw(root), start)
                self.assertEqual(self.store().reconcile(pub).publication_hash, pub.publication_hash)

    def test_stopped_after_the_replace(self):
        for point in ("after_replace", "after_dir_fsync"):
            with self.subTest(point=point):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                h, pub, start = self.stopped_at(point)
                new = H.C2.file_bytes(H.U.check_publication(start, pub))
                self.assertEqual(H.listing(root), ["history.json", "write.lock"])
                self.assertEqual(H.raw(root), new)
                self.assertEqual(self.run_err(self.store().read).code, "store_busy")
                os.unlink(os.path.join(root, H.LOCK))
                self.assertEqual(self.store().read().head_seq, 1)
                self.assertEqual(self.store().reconcile(pub).outcome, "PUBLISHED")
                e = self.run_err(self.store().publish, pub)
                self.assertEqual((e.code, e.rule), ("publication_stale", "head"))
                self.assertEqual(H.raw(root), new)

    def test_the_file_is_always_one_of_two_valid_histories(self):
        for point in ("after_tmp_close", "before_replace", "after_replace"):
            with self.subTest(point=point):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                h, pub, start = self.stopped_at(point)
                new = H.C2.file_bytes(H.U.check_publication(start, pub))
                self.assertIn(H.raw(root), (start, new))
                H.U.read_history_bytes(H.raw(root))               # fully valid either way


if __name__ == "__main__":
    unittest.main()
