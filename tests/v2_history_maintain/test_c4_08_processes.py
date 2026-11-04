"""C4-18: independent processes. Children are started only with sys.executable and tests/v2_history_maintain/c4_worker.py
(through c4_helpers.Worker). A forced stop (a SIGKILL of the child; skipped on Windows) is made at a chosen point while the
child waits, never by sleeping for a time."""
import os
import sys
import unittest

import c4_helpers as H
import v2_history_maintain as M

SAFE = {"store_busy"}


class Probe(H.RootCase):
    def test_a_child_has_no_network_and_is_a_different_process(self):
        ev = H.Worker({"mode": "probe"}).result()
        self.assertTrue(ev["socket_blocked"])
        self.assertNotEqual(ev["pid"], os.getpid())

    def test_a_child_adopts_and_the_parent_reads_it(self):
        case = H.adoption()
        self.put_history(case.data)
        ev = H.Worker({"root": self.root, "mode": "one", "op": "adopt"}).result()
        self.assertEqual((ev["ok"], ev["status"], ev["resumed"]), (True, "ADOPTED", False))
        self.assertEqual(self.c3(writable=False).read(), case.candidate)


class Contention(H.RootCase):
    def race(self, op, put):
        put()
        workers = [H.Worker({"root": self.root, "mode": "race", "op": op, "attempts": 12, "wait_go": True})
                   for _ in range(5)]
        for worker in workers:
            self.addCleanup(worker.kill)
        for worker in workers:
            worker.expect("READY")
        for worker in workers:
            worker.send("GO")
        return [o for worker in workers for o in worker.result()["outcomes"]]

    def test_five_processes_adopt_the_same_root_and_exactly_one_does_the_work(self):
        case = H.adoption()
        outcomes = self.race("adopt", lambda: self.put_history(case.data))
        self.assertEqual(len(outcomes), 5 * 12)
        self.assertEqual(outcomes.count("ADOPTED:first"), 1)
        self.assertEqual(set(outcomes) - {"ADOPTED:first", "ADOPTED:resumed"} - SAFE, set())
        self.assertEqual(self.c3(writable=False).read(), case.candidate)
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.listing(self.root), ["history.json", "quarantine"])
        self.assertEqual(H.qraw(self.root, case.key, "history.json"), case.data)

    def test_five_processes_migrate_the_same_root_and_exactly_one_does_the_work(self):
        case = H.migration()
        outcomes = self.race("migrate", lambda: self.put_v1(case))
        self.assertEqual(len(outcomes), 5 * 12)
        self.assertEqual(outcomes.count("MIGRATED:first"), 1)
        self.assertEqual(set(outcomes) - {"MIGRATED:first", "MIGRATED:resumed"} - SAFE, set())
        self.assertEqual(self.c3(writable=False).read(), case.candidate)
        self.assertEqual(H.listing(self.root), ["history.json", "quarantine"])
        self.assertEqual(H.qraw(self.root, case.key, "snapshot.json"), case.data)


@unittest.skipIf(sys.platform == "win32", "a forced stop by SIGKILL is not made on Windows")
class ForcedStop(H.RootCase):
    def stopped_at(self, op, point):
        case = H.adoption() if op == "adopt" else H.migration()
        if op == "adopt":
            self.put_history(case.data)
        else:
            self.put_v1(case)
        worker = H.Worker({"root": self.root, "mode": "one", "op": op, "hook": {"point": point, "action": "pause"}})
        self.addCleanup(worker.kill)
        worker.expect("AT")
        worker.kill()                                    # SIGKILL: no clean-up of the child runs
        return case

    def finish(self, op, case):
        """The next operation is refused (the lock is left); the person unlocks and calls the same operation again."""
        m = self.maint()
        again = self.run_err(m.adopt if op == "adopt" else (lambda p: m.migrate(p, True)), case.pub)
        self.assertEqual(again.code, "store_busy")
        report = m.inspect()
        self.assertEqual([(a["name"], a["owner"]) for a in report.artifacts], [(H.LOCK, "C4")])
        plan = M.plan_unlock(report, "u-1", True)
        m.unlock(plan, plan.plan_hash)
        self.assertEqual(self.maint().inspect().artifacts, [])
        return m

    def test_adopt_stopped_after_the_manifest_and_before_the_publication(self):
        case = self.stopped_at("adopt", "after_manifest")
        self.assertEqual(H.raw(self.root), case.data)
        m = self.finish("adopt", case)
        res = m.adopt(case.pub)
        self.assertEqual((res.status, res.resumed), (M.ADOPTED, True))
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.qraw(self.root, case.key, "history.json"), case.data)
        self.assertEqual(sorted(os.listdir(self.root)), ["history.json", "quarantine"])

    def test_adopt_stopped_after_the_publication(self):
        case = self.stopped_at("adopt", "after_publish")
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        m = self.finish("adopt", case)
        again = H.rebuild_adoption(case, m.read_set_aside(case.key, H.HIST))
        res = m.adopt(again)
        self.assertEqual((res.status, res.resumed), (M.ADOPTED, True))
        self.assertEqual(self.c3().read(), case.candidate)

    def test_migrate_stopped_after_the_manifest_and_before_the_publication(self):
        case = self.stopped_at("migrate", "after_manifest")
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.LOCK, H.V1, "quarantine"]))
        m = self.finish("migrate", case)
        res = m.migrate(case.pub, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(sorted(os.listdir(self.root)), ["history.json", "quarantine"])
        self.assertEqual(self.c3().read(), case.candidate)

    def test_migrate_stopped_after_the_publication_and_before_the_rename(self):
        case = self.stopped_at("migrate", "after_publish")
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.LOCK, H.HIST, H.V1, "quarantine"]))
        m = self.finish("migrate", case)
        again = H.rebuild_migration(case, m.read_original(H.V1))
        res = m.migrate(again, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(sorted(os.listdir(self.root)), ["history.json", "quarantine"])
        self.assertEqual(H.qraw(self.root, case.key, H.V1), case.data)
        self.assertEqual(self.c3().read(), case.candidate)


if __name__ == "__main__":
    unittest.main()
