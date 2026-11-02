"""B3-02 (the effective floor) and B3-03 (floor, upper bound, no-effect rule, resume_after == check_d)."""
import unittest

import r3_helpers as R

T, H, X, D, V, O = R.T, R.H, R.X, R.D, R.V, R.O
FLOOR = ("restart_invalid", "resume_after", "restart_floor")
NOOP = ("restart_invalid", "resume_after", "restart_noop")
BOUND = ("restart_invalid", "check_d", "check_d")


def floor_of(plan):
    return plan.basis["floor"]


class EffectiveFloor(unittest.TestCase):
    def test_floor_takes_every_segment_and_the_declaration(self):
        b = T.example_v()                       # GENESIS D0, APPLY D1, DECLARE D2, RESTART D3
        h = b.history()
        plan = R.prep(h, b.w, D[4], D[5], "r1")
        self.assertEqual(floor_of(plan), {"last_apply_d": D[1], "last_declared_d": D[2], "prev_boundary": D[3]})
        self.assertEqual(R.refusal(R.prep, h, b.w, D[3], D[5], "r2"), NOOP)           # initial state, same boundary
        # the record carries the same floor as the independent builder writes
        self.assertEqual(plan.basis["candidate_history"]["events"][-1]["floor"], floor_of(plan))

    def test_declaration_is_the_latest_day(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        h = b.history()
        self.assertEqual(R.refusal(R.prep, h, b.w, D[1], D[3], "r1"), FLOOR)             # below the declared day
        self.assertEqual(R.prep(h, b.w, D[2], D[3], "r1").status, "READY")              # the declared day itself
        plan = R.prep(h, b.w, D[3], D[3], "r1")
        self.assertEqual(floor_of(plan), {"last_apply_d": D[1], "last_declared_d": D[2], "prev_boundary": D[0]})

    def test_initial_state_plus_declaration_keeps_the_declared_floor(self):
        b = H.HB()
        b.declare(D[1], "q1")
        h = b.history()
        self.assertEqual(R.refusal(R.prep, h, b.w, D[0], D[2], "r1"), FLOOR)           # not restart_noop
        plan = R.prep(h, b.w, D[1], D[2], "r1")                                         # advancing past the boundary
        self.assertEqual(floor_of(plan), {"last_apply_d": None, "last_declared_d": D[1], "prev_boundary": D[0]})

    def test_several_restarts_and_the_last_segment_boundary(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restart(D[2], "q1")
        b.apply(D[3], 31.0)
        b.restart(D[4], "q2")
        h = b.history()
        plan = R.prep(h, b.w, D[5], D[6], "r1")
        self.assertEqual(floor_of(plan), {"last_apply_d": D[3], "last_declared_d": None, "prev_boundary": D[4]})
        self.assertEqual(R.refusal(R.prep, h, b.w, D[3], D[6], "r1"), FLOOR)
        self.assertEqual(R.refusal(R.prep, h, b.w, D[4], D[6], "r1"), NOOP)

    def test_a_dropped_declaration_does_not_raise_the_floor(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        b.restore(1, {2: "DROP"}, "q2")         # the declaration of D2 is superseded
        h = b.history()
        self.assertEqual(V.validate_history(h).superseded_seqs, (2,))
        plan = R.prep(h, b.w, D[1], D[2], "r1")
        self.assertEqual(floor_of(plan), {"last_apply_d": D[1], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(R.refusal(R.prep, h, b.w, D[0], D[2], "r1"), FLOOR)

    def test_a_dropped_restart_does_not_raise_the_boundary(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restart(D[3], "q1")                   # boundary D3 ...
        b.restore(1, {2: "DROP"}, "q2")         # ... dropped again
        h = b.history()
        self.assertEqual(V.validate_history(h).current_boundary.after, D[0])
        plan = R.prep(h, b.w, D[1], D[2], "r1")
        self.assertEqual(floor_of(plan), {"last_apply_d": D[1], "last_declared_d": None, "prev_boundary": D[0]})

    def test_superseded_apply_days_do_not_count_either(self):
        # Example R: the final chain keeps every APPLY by REAPPLY, so the floor is the same as a plain read
        b = H.example_r()
        h = b.history()
        view = O.read_effective(h)
        days = [a["d"] for a in view.applies]
        plan = R.prep(h, b.w, D[7], D[8], "r1")
        self.assertEqual(floor_of(plan)["last_apply_d"], max(days))
        self.assertEqual(floor_of(plan)["prev_boundary"], view.current_boundary["after"])

    def test_spy_the_floor_comes_from_the_checked_view_not_the_raw_list(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        b.restore(1, {2: "DROP"}, "q2")
        h = b.history()
        # the physical list still holds the declaration of D2
        self.assertIn("DECLARE_MISSING", [e["kind"] for e in h.events])
        self.assertIsNone(floor_of(R.prep(h, b.w, D[1], D[2], "r1"))["last_declared_d"])


class BoundsAndNoEffect(unittest.TestCase):
    def test_each_floor_component_refuses_a_smaller_day(self):
        b = T.example_v()                       # floor {D1, D2, D3}
        h = b.history()
        for resume in (D[0], D[1], D[2]):
            self.assertEqual(R.refusal(R.prep, h, b.w, resume, D[5], "r1"), FLOOR, resume)
        b2 = H.HB()
        b2.apply(D[2], 28.0)                    # last_apply_d only: boundary D0, no declaration
        self.assertEqual(R.refusal(R.prep, b2.history(), b2.w, D[1], D[5], "r1"), FLOOR)
        self.assertEqual(R.refusal(R.prep, b2.history(), b2.w, D[0], D[5], "r1"), FLOOR)
        b3 = H.HB(start_idx=0)
        b3.restart(D[3], "q1")                  # prev_boundary only (initial state)
        self.assertEqual(R.refusal(R.prep, b3.history(), b3.w, D[2], D[5], "r1"), FLOOR)
        self.assertEqual(R.refusal(R.prep, b3.history(), b3.w, D[3], D[5], "r1"), NOOP)

    def test_the_apply_day_itself_is_allowed_when_the_state_is_not_initial(self):
        b = R.example_u()
        h = b.history()
        plan = R.prep(h, b.w, D[2], D[3], "r1")                     # resume == last_apply_d
        self.assertEqual(plan.status, "READY")

    def test_upper_bound(self):
        b = R.example_u()
        h = b.history()
        self.assertEqual(R.refusal(R.prep, h, b.w, D[4], D[3], "r1"), BOUND)
        self.assertEqual(R.prep(h, b.w, D[3], D[3], "r1").status, "READY")           # equal is fine

    def test_initial_state_same_boundary_is_no_effect_and_an_advance_is_not(self):
        b = H.HB()
        h = b.history()
        self.assertEqual(R.refusal(R.prep, h, b.w, D[0], D[1], "r1"), NOOP)
        self.assertEqual(R.prep(h, b.w, D[1], D[1], "r1").status, "READY")
        self.assertEqual(R.prep(h, b.w, D[1], D[2], "r1").status, "READY")

    def test_resume_equal_check_d_succeeds_in_prepare_confirm_and_reconfirm(self):
        b = R.example_u()
        h = b.history()
        plan, result = R.run(h, b.w, D[3], D[3], "r1")
        self.assertEqual(result.status, "CONFIRMED_IN_MEMORY")
        again = R.confirm(plan, result.history, b.w)
        self.assertEqual(again.status, "NO_CHANGE")
        self.assertEqual(again.history, result.history)

    def test_old_context_difference_and_floor_overlap_gives_the_floor_error(self):
        b = T.example_v()                       # boundary D3 etc.
        h = b.history()
        changed = R.sessions_with({D[3]: R.earlier_close})          # the boundary session now differs
        # a valid request meets the context error ...
        self.assertEqual(R.refusal(R.prep, h, b.w, D[4], D[5], "r1", changed)[:2], ("session_context_mismatch", "sessions"))
        # ... but a request below the floor is refused for the floor first
        self.assertEqual(R.refusal(R.prep, h, b.w, D[2], D[5], "r1", changed), FLOOR)

    def test_the_bound_error_comes_before_the_projection(self):
        b = R.example_u()
        changed = R.sessions_with({D[0]: R.earlier_close})
        self.assertEqual(R.refusal(R.prep, b.history(), b.w, D[5], D[4], "r1", changed), BOUND)


if __name__ == "__main__":
    unittest.main()
