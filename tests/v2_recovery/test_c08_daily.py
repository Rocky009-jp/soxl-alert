"""C-08: a declared day runs through S1 as NO_COMMIT and the next APPLY follows the existing gap rule."""
import unittest

import r_helpers as H
from r_helpers import D, R
from v2_persistence.plan import AppendPlan


def row(record_id, d, value, hour=20):
    return H.P.obs(record_id, d, value, hour=hour)


class DeclaredDay(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.r1 = self.w.ledger[0]
        done = H.run(self.w, R.empty_resolutions(), [H.declare(D[2])], [self.r1], D[2], rid="decl-1")
        self.rs = done.resolutions

    def day(self, d, ledger, snap=None, rs=None):
        return R.prepare_resolved_day(snap or self.w.snap(), rs or self.rs, d, self.w.series, self.w.sessions, ledger)

    def test_the_declared_day_is_no_commit(self):
        res = self.day(D[2], [self.r1])
        self.assertEqual(res.status, "NO_COMMIT")
        self.assertIsNone(res.candidate_event_text)
        self.assertIsNone(res.candidate_event_hash)
        self.assertFalse(res.core_result.state_updated)

    def test_next_apply_follows_the_gap_rule_in_three_fg_bands(self):
        cases = {"at_least_30": (35.0, 1), "below_25": (20.0, 0), "between_25_and_30": (27.0, 0)}
        for name, (value, streak) in cases.items():
            with self.subTest(name):
                r3 = row("R3", D[3], value)
                ledger = [self.r1, r3]
                res = self.day(D[3], ledger)
                self.assertEqual(res.status, "PREPARED")
                core = res.core_result
                self.assertTrue(core.gap)
                self.assertIn("session_gap_state_degraded", core.notes)
                self.assertEqual(core.next_state.streak, streak)
                if name == "below_25":
                    self.assertEqual(core.next_state.armed.value, "FALSE")

    def test_streak_after_a_gap_with_fg_at_least_30_is_one_not_zero(self):
        res = self.day(D[3], [self.r1, row("R3", D[3], 35.0)])
        self.assertEqual(res.core_result.next_state.streak, 1)

    def test_extending_the_snapshot_with_an_independent_s1_apply_keeps_the_records_valid(self):
        ledger = [self.r1, row("R3", D[3], 35.0)]
        eff = H.resolve(self.w, self.rs, ledger, D[3])
        snap = H.extend_with_s1(self.w, D[3], eff.raw_observations())
        self.assertEqual(snap.head_seq, 2)
        self.assertEqual(snap.events[2]["skipped_sessions"], [D[2]])
        self.assertEqual(R.validate_resolutions(snap, self.rs).record_count, 1)
        again = self.day(D[3], ledger, snap=snap)
        self.assertEqual(again.status, "ALREADY_APPLIED")
        nxt = self.day(D[4], ledger + [row("R4", D[4], 36.0)], snap=snap)
        self.assertEqual(nxt.status, "PREPARED")
        self.assertFalse(nxt.core_result.gap)

    def test_the_candidate_event_equals_what_s1_builds_from_the_same_final_ledger(self):
        ledger = [self.r1, row("R3", D[3], 35.0)]
        res = self.day(D[3], ledger)
        eff = H.resolve(self.w, self.rs, ledger, D[3])
        s1 = H.P.prepare_day(self.w.snap(), D[3], self.w.series, self.w.sessions, eff.raw_observations())
        self.assertEqual(res.candidate_event_text, H.cj(s1.plan.event))
        self.assertEqual(res.candidate_event_hash, s1.plan.event_hash)

    def test_an_apply_on_a_declared_day_is_refused(self):
        ledger = [self.r1, row("D2R", D[2], 27.0)]              # the row for D2 exists only in this ledger
        H.extend_with_s1(self.w, D[2], ledger)
        H.expect_rule(self, "declare_applied", R.validate_resolutions, self.w.snap(), self.rs)
        H.expect_rule(self, "declare_applied", R.resolve_observations, self.w.snap(), self.rs, self.w.sessions,
                      ledger, D[2])

    def test_the_result_never_carries_a_plan(self):
        res = self.day(D[3], [self.r1, row("R3", D[3], 35.0)])
        for name in ("plan", "expected_head_seq", "expected_head_hash", "event", "input_hash", "d"):
            self.assertFalse(hasattr(res, name), name)
        self.assertNotIsInstance(res, AppendPlan)


if __name__ == "__main__":
    unittest.main()
