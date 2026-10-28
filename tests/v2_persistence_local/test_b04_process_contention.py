"""B-04: competition between independent OS processes (python workers), synchronised with pipes, never by sleep."""
import os
import unittest

import l_helpers as H
from v2_persistence.codec import decode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.local import LocalFileStore, LocalStoreError
from v2_persistence.plan import ALREADY_APPLIED, REPLAN_REQUIRED
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import reconcile

SAME, DIFFERENT_CONTENT, DIFFERENT_D = "same_content_same_d", "different_content_same_d", "different_d"


def two_plans(sc, snapshot, kind):
    d1, d2 = sc.day(1), sc.day(2)
    if kind == SAME:
        return sc.plan_for(snapshot, d1, 40, "R-a"), sc.plan_for(snapshot, d1, 40, "R-a")
    if kind == DIFFERENT_CONTENT:
        return sc.plan_for(snapshot, d1, 20, "R-a"), sc.plan_for(snapshot, d1, 80, "R-b")
    return sc.plan_for(snapshot, d1, 40, "R-a"), sc.plan_for(snapshot, d2, 40, "R-b")


def spec(root, plan, **kw):
    s = {"mode": "commit", "root": root, "plan": H.plan_to_json(plan), "wait_go": True}
    s.update(kw)
    return s


class Contention(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc)
        self.start = LocalFileStore(self.root).read()

    def check_final(self, winner_plan):
        snap = LocalFileStore(self.root).read()
        validate_snapshot(snap)
        self.assertEqual(snap.head_seq, self.start.head_seq + 1)
        self.assertEqual(snap.events[:-1], self.start.events)
        self.assertEqual(snap.events[-1]["event_hash"], winner_plan.event_hash)
        self.assertEqual(H.listing(self.root), [H.SNAP])
        return snap

    def check_loser(self, kind, loser_plan, snap):
        """Explicit re-read + S1 reconcile; nothing is appended automatically."""
        if kind == SAME:
            self.assertEqual(reconcile(loser_plan, snap).status, ALREADY_APPLIED)
        elif kind == DIFFERENT_CONTENT:
            with self.assertRaises(PersistenceError) as cm:
                reconcile(loser_plan, snap)
            self.assertEqual(cm.exception.code, "concurrent_conflict")
        else:
            self.assertEqual(reconcile(loser_plan, snap).status, REPLAN_REQUIRED)
        self.assertEqual(sum(1 for e in snap.events if e["kind"] == "APPLY"), 1)

    def race_once(self, kind):
        pa, pb = two_plans(self.sc, self.start, kind)
        # the first read finishes (READY, lock released) before the second worker starts: a read also takes the lock
        wa = H.Worker(spec(self.root, pa))
        self.addCleanup(wa.kill)
        ra = wa.expect("READY")
        wb = H.Worker(spec(self.root, pb))
        self.addCleanup(wb.kill)
        rb = wb.expect("READY")
        self.assertEqual((ra["head_seq"], rb["head_seq"]), (0, 0))   # both read the same head first
        wa.send("GO")
        wb.send("GO")
        res = [wa.result(), wb.result()]
        ok = [r for r in res if r["ok"]]
        bad = [r for r in res if not r["ok"]]
        self.assertEqual(len(ok), 1, res)
        self.assertEqual(len(bad), 1, res)
        self.assertIn(bad[0]["code"], ("store_busy", "cas_conflict"))
        winner, loser = (pa, pb) if res[0]["ok"] else (pb, pa)
        snap = self.check_final(winner)
        self.check_loser(kind, loser, snap)
        return bad[0]["code"]

    def test_free_race_same_content(self):
        for _ in range(6):
            self.tearDownRoot()
            self.race_once(SAME)

    def test_free_race_different_content_same_d(self):
        for _ in range(6):
            self.tearDownRoot()
            self.race_once(DIFFERENT_CONTENT)

    def test_free_race_different_d(self):
        for _ in range(6):
            self.tearDownRoot()
            self.race_once(DIFFERENT_D)

    def tearDownRoot(self):
        """Fresh genesis for the next round (test-side reset of the dedicated root)."""
        for n in os.listdir(self.root):
            os.unlink(os.path.join(self.root, n))
        H.init_root(self.root, self.sc)

    def test_forced_busy_then_explicit_cas_conflict(self):
        for kind in (SAME, DIFFERENT_CONTENT, DIFFERENT_D):
            self.tearDownRoot()
            pa, pb = two_plans(self.sc, self.start, kind)
            a = H.Worker(spec(self.root, pa, hook={"point": "before_replace", "action": "pause"}))
            self.addCleanup(a.kill)
            a.expect("READY")
            a.send("GO")
            a.expect("AT")                                         # A holds the lock, its tmp file is written
            lock_before = H.raw(self.root, H.LOCK)
            self.assertTrue(any(n.endswith(".tmp") for n in H.listing(self.root)))
            # B (independent process) and an in-process instance are both refused at once
            rb = H.run_worker(spec(self.root, pb, wait_go=False))
            self.assertFalse(rb["ok"])
            self.assertEqual((rb["code"], rb["field"], rb["phase"]), ("store_busy", "lock", "lock_acquire"))
            with self.assertRaises(LocalStoreError) as cm:
                LocalFileStore(self.root, writable=True).read()
            self.assertCode(cm.exception, "store_busy", "lock")
            self.assertEqual(H.raw(self.root, H.LOCK), lock_before)    # B did not delete or change A's lock
            a.send("CONTINUE")
            ra = a.result()
            self.assertTrue(ra["ok"], ra)
            snap = self.check_final(pa)
            # A finished; B explicitly hands over the same old plan again: refused by compare-and-swap
            with self.assertRaises(LocalStoreError) as cm:
                LocalFileStore(self.root, writable=True).commit(pb)
            self.assertCode(cm.exception, "cas_conflict", "head")
            self.assertEqual(LocalFileStore(self.root).read(), snap)
            self.check_loser(kind, pb, snap)

    def test_cas_conflict_in_a_second_process_after_the_first_finished(self):
        pa, pb = two_plans(self.sc, self.start, DIFFERENT_D)
        wb = H.Worker(spec(self.root, pb))
        self.addCleanup(wb.kill)
        wb.expect("READY")                                        # B has read the old head
        ra = H.run_worker(spec(self.root, pa, wait_go=False))
        self.assertTrue(ra["ok"])
        wb.send("GO")
        rb = wb.result()
        self.assertEqual((rb["ok"], rb["code"], rb["field"]), (False, "cas_conflict", "head"))
        self.check_final(pa)
        self.assertEqual(H.listing(self.root), [H.SNAP])


if __name__ == "__main__":
    unittest.main()
