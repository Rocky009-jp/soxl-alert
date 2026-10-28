"""A-06: simultaneous updates from one head, reconcile after a conflict or a lost answer.

Two plans are prepared from the same head, then two threads commit after a Barrier (no sleeping, no timing luck).
Conditions for plans of different days from the same initial head: both worlds share the boundary D0; world 1 has a
decision only for D1, world 2 has none for D1 and a decision for D2 (D1 becomes a recorded gap in its plan).
"""
import threading
import unittest

import p_helpers as h
from v2_persistence.errors import PersistenceError
from v2_persistence.plan import AppendPlan
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import reconcile

D = h.DATES


def race(store, plans):
    barrier = threading.Barrier(len(plans))
    results = [None] * len(plans)

    def run(i):
        barrier.wait(timeout=10)
        try:
            results[i] = ("ok", store.commit(plans[i]))
        except PersistenceError as e:
            results[i] = ("err", e)
        except BaseException as e:               # a harness failure must be visible, never swallowed
            results[i] = ("crash", e)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(plans))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
        assert not t.is_alive(), "thread did not finish"
    return results


def plan_from(world_ledger_rows, d, store_snapshot):
    w = h.World()
    w.ledger[:] = world_ledger_rows
    return h.prepare_day(store_snapshot, d, w.series, w.sessions, w.ledger)


class SameHeadSameDay(unittest.TestCase):
    def test_two_equal_plans_one_wins_the_other_gets_cas_conflict_then_reconciles(self):
        for round_no in range(25):
            w = h.World()
            rows = [h.obs("R1", D[1], 27.0)]
            head = w.snap()
            plan_a = plan_from(rows, D[1], head).plan
            plan_b = plan_from(rows, D[1], head).plan
            self.assertEqual(plan_a, plan_b)
            results = race(w.store, [plan_a, plan_b])
            kinds = sorted(r[0] for r in results)
            self.assertEqual(kinds, ["err", "ok"], round_no)
            loser = [r for r in results if r[0] == "err"][0][1]
            self.assertEqual((loser.code, loser.field), ("cas_conflict", "head"))
            snap = w.snap()
            self.assertEqual(snap.head_seq, 1)
            self.assertEqual(sum(1 for e in snap.events if e["kind"] == "APPLY"), 1)
            validate_snapshot(snap)
            losing_plan = plan_a if results[0][0] == "err" else plan_b
            self.assertEqual(reconcile(losing_plan, w.store.read()).status, "ALREADY_APPLIED")

    def test_a_failed_commit_leaves_the_store_unchanged(self):
        w = h.World()
        head = w.snap()
        plan = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        w.store.commit(plan)
        after_first = w.snap()
        with self.assertRaises(PersistenceError):
            w.store.commit(plan)
        self.assertEqual(w.snap(), after_first)

    def test_different_inputs_for_the_same_day_are_a_concurrent_conflict(self):
        w = h.World()
        head = w.snap()
        plan_a = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        plan_b = plan_from([h.obs("R1", D[1], 27.5)], D[1], head).plan
        self.assertNotEqual(plan_a.input_hash, plan_b.input_hash)
        results = race(w.store, [plan_a, plan_b])
        self.assertEqual(sorted(r[0] for r in results), ["err", "ok"])
        loser_plan = plan_a if results[0][0] == "err" else plan_b
        with self.assertRaises(PersistenceError) as cm:
            reconcile(loser_plan, w.store.read())
        self.assertEqual((cm.exception.code, cm.exception.field), ("concurrent_conflict", "events"))
        self.assertEqual(w.snap().head_seq, 1)

    def test_a_different_decision_record_for_the_same_input_value_is_also_a_conflict(self):
        w = h.World()
        head = w.snap()
        plan_a = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        plan_b = plan_from([h.obs("R2", D[1], 27.0)], D[1], head).plan
        w.store.commit(plan_a)
        with self.assertRaises(PersistenceError) as cm:
            reconcile(plan_b, w.store.read())
        self.assertEqual(cm.exception.code, "concurrent_conflict")


class SameHeadDifferentDays(unittest.TestCase):
    def test_plans_of_different_days_never_both_land_and_are_not_reattached(self):
        for _ in range(10):
            w = h.World()
            head = w.snap()
            plan_d1 = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan          # decision for D1 only
            plan_d2 = plan_from([h.obs("R2", D[2], 28.0)], D[2], head).plan          # D1 is a recorded gap here
            self.assertEqual((plan_d1.expected_head_hash, plan_d2.expected_head_hash), (head.head_hash,) * 2)
            results = race(w.store, [plan_d1, plan_d2])
            self.assertEqual(sorted(r[0] for r in results), ["err", "ok"])
            snap = w.snap()
            self.assertEqual(sum(1 for e in snap.events if e["kind"] == "APPLY"), 1)
            loser_plan = plan_d1 if results[0][0] == "err" else plan_d2
            won_d = D[2] if loser_plan is plan_d1 else D[1]
            self.assertEqual(snap.events[1]["d"], won_d)
            res = reconcile(loser_plan, w.store.read())
            self.assertEqual(res.status, "REPLAN_REQUIRED")
            self.assertFalse(res.committed)
            # committing the old plan again is still refused: it is never moved to the new head
            with self.assertRaises(PersistenceError) as cm:
                w.store.commit(loser_plan)
            self.assertEqual(cm.exception.code, "cas_conflict")
            self.assertEqual(w.snap(), snap)

    def test_a_plan_for_a_day_gap_cannot_be_replayed_on_a_head_that_already_processed_the_gap(self):
        w = h.World()
        head = w.snap()
        plan_d2 = plan_from([h.obs("R2", D[2], 28.0)], D[2], head).plan             # gap D1 recorded inside the plan
        w2 = h.World()
        w2.apply(D[1], 27.0)
        with self.assertRaises(PersistenceError) as cm:
            w2.store.commit(plan_d2)
        self.assertEqual(cm.exception.code, "cas_conflict")


class AfterHeadMoves(unittest.TestCase):
    def test_own_record_is_found_after_the_head_moved_on(self):
        w = h.World()
        res = w.apply(D[1], 27.0)
        w.apply(D[2], 40.0)
        w.apply(D[3], 41.0)
        self.assertEqual(reconcile(res.plan, w.store.read()).status, "ALREADY_APPLIED")

    def test_only_the_other_side_advanced_is_not_a_success(self):
        w = h.World()
        head = w.snap()
        mine = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        w.store.commit(plan_from([h.obs("R9", D[3], 41.0)], D[3], head).plan)      # somebody else moved the head
        res = reconcile(mine, w.store.read())
        self.assertEqual(res.status, "REPLAN_REQUIRED")        # the head is newer, which proves nothing about D1
        self.assertEqual(w.snap().head_seq, 1)
        self.assertNotIn(D[1], [e.get("d") for e in w.snap().events])

    def test_same_content_by_another_run_is_reported_as_already_applied_without_any_send_right(self):
        w = h.World()
        head = w.snap()
        mine = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        theirs = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        w.store.commit(theirs)
        res = reconcile(mine, w.store.read())
        self.assertEqual(res.status, "ALREADY_APPLIED")
        self.assertFalse(res.committed)                        # reconcile never writes and never claims to have written
        self.assertFalse(hasattr(res, "snapshot"))
        import v2_persistence
        public = " ".join(n for n in dir(v2_persistence.store) + dir(v2_persistence.plan) + dir(v2_persistence.runner))
        for word in ("notify", "send", "outbox", "claim"):
            self.assertNotIn(word, public.lower())

    def test_a_parent_that_differs_is_not_the_same_plan_even_if_everything_else_matches(self):
        w = h.World()
        w.apply(D[1], 27.0)
        head1 = w.snap()
        plan_old = plan_from(list(w.ledger) + [h.obs("R2", D[2], 28.0)], D[2], head1).plan
        # another history reaches the same D2 with another parent (D1 was a gap there)
        w2 = h.World()
        w2.store.commit(plan_from([h.obs("R2", D[2], 28.0)], D[2], w2.snap()).plan)
        with self.assertRaises(PersistenceError) as cm:
            reconcile(plan_old, w2.store.read())
        self.assertEqual(cm.exception.code, "concurrent_conflict")

    def test_only_the_parent_differs_is_still_not_the_same_plan(self):
        # two histories reach D2 with equal inputs, transition and state, but through different D1 records
        wa, wb = h.World(), h.World()
        wa.apply(D[1], 27.0)
        wb.ledger.append(h.obs("OTHER-ID", D[1], 28.0))
        wb.store.commit(wb.prepare(D[1]).plan)
        row2 = h.obs("R2", D[2], 28.0)
        plan_a = plan_from(list(wa.ledger) + [row2], D[2], wa.snap()).plan
        plan_b = plan_from(list(wb.ledger) + [row2], D[2], wb.snap()).plan
        ea, eb = plan_a.event, plan_b.event
        self.assertNotEqual(ea["parent_hash"], eb["parent_hash"])
        for key in ("input_hash", "transition_result", "state_after"):
            self.assertEqual(ea[key], eb[key], key)
        wb.store.commit(plan_b)
        with self.assertRaises(PersistenceError) as cm:
            reconcile(plan_a, wb.store.read())
        self.assertEqual(cm.exception.code, "concurrent_conflict")

    def test_reconcile_writes_nothing_and_validates_the_snapshot_it_is_given(self):
        w = h.World()
        res = w.apply(D[1], 27.0)
        snap = w.snap()
        reconcile(res.plan, snap)
        self.assertEqual(w.snap(), snap)
        bad = h.tampered(snap, lambda e: e[1].__setitem__("seq", 4))
        with self.assertRaises(PersistenceError) as cm:
            reconcile(res.plan, bad)
        self.assertEqual(cm.exception.code, "snapshot_invalid")
        with self.assertRaises(PersistenceError):
            reconcile("not a plan", snap)

    def test_commit_rejects_things_that_are_not_plans(self):
        w = h.World()
        before = w.snap()
        for bad in (None, {}, "x", before.events[0]):
            with self.assertRaises(PersistenceError) as cm:
                w.store.commit(bad)
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
        self.assertEqual(w.snap(), before)

    def test_forged_plans_cannot_replace_history(self):
        w = h.World()
        res = w.apply(D[1], 27.0)
        w2 = h.World()
        head = w2.snap()
        good = plan_from([h.obs("R1", D[1], 27.0)], D[1], head).plan
        forged = good.event
        forged["transition_result"]["run_class"] = "CONDITION_MET"            # content changed, hash not
        bad_plan = AppendPlan(good.expected_head_seq, good.expected_head_hash, forged)
        with self.assertRaises(PersistenceError) as cm:
            w2.store.commit(bad_plan)
        self.assertEqual(cm.exception.code, "snapshot_invalid")
        self.assertEqual(w2.snap(), head)
        self.assertEqual(res.status, "PREPARED")


if __name__ == "__main__":
    unittest.main()
