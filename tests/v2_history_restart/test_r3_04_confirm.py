"""B3-10 (confirmation against the original history) and B3-11 (confirming the same plan against its own candidate)."""
import unittest
from unittest import mock

import r3_helpers as R

T, H, X, D, P, V, O = R.T, R.H, R.X, R.D, R.P, R.V, R.O
MISMATCH = ("err", "history_plan_mismatch", "plan")
STALE = ("err", "history_plan_stale", "plan")


class ConfirmAgainstTheOriginal(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.h, self.w = self.b.history(), self.b.w
        self.plan = R.prep(self.h, self.w, D[3], D[4], "r1")

    def test_confirmed_in_memory_and_nothing_given_changes(self):
        ledger_before, plan_before, digest_before = R.cj(self.w.ledger), self.plan.to_dict(), self.h.digest
        res = R.confirm(self.plan, self.h, self.w)
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(res.plan_hash, self.plan.plan_hash)
        self.assertEqual(res.history.digest, self.plan.basis["candidate_digest"])
        self.assertEqual((res.committed, res.committable), (False, False))
        self.assertEqual((R.cj(self.w.ledger), self.plan.to_dict(), self.h.digest),
                         (ledger_before, plan_before, digest_before))
        self.assertEqual(V.validate_history(res.history).head_seq, 3)

    def test_a_changed_but_valid_history_ledger_or_sessions_is_stale(self):
        more = H.HB(world=self.w, events=self.b.events)
        more.declare(D[3], "q9")
        self.assertEqual(T.outcome(R.confirm, self.plan, more.history(), self.w)[:3], STALE)
        rows = self.w.ledger + [P.obs("N1", D[8], 30.0)]
        self.assertEqual(T.outcome(R.confirm, self.plan, self.h, self.w, None, rows)[:3], STALE)
        sessions = R.sessions_with({D[20]: R.earlier_close})
        self.assertEqual(T.outcome(R.confirm, self.plan, self.h, self.w, sessions)[:3], STALE)

    def test_an_invalid_history_row_or_session_list_keeps_its_own_error(self):
        broken = H.mutated(self.b.events, lambda ev: ev[2].__setitem__("d", D[9]))
        out = T.outcome(R.confirm, self.plan, broken, self.w)
        self.assertEqual(out[:2], ("err", "history_invalid"))
        self.assertEqual(T.outcome(X.confirm_restart_plan, self.plan, self.plan.plan_hash, self.h, self.w.sessions,
                                   [{"x": 1}])[:2], ("err", "record_id_invalid"))
        self.assertEqual(T.outcome(X.confirm_restart_plan, self.plan, self.plan.plan_hash, self.h, None,
                                   self.w.ledger)[:3], ("err", "sessions_invalid", "sessions"))
        self.assertEqual(T.outcome(X.confirm_restart_plan, self.plan, self.plan.plan_hash, "not a history",
                                   self.w.sessions, self.w.ledger)[:2], ("err", "history_invalid"))
        # an invalid input is never turned into a stale plan
        self.assertNotEqual(out[1], "history_plan_stale")

    def test_the_plan_is_checked_before_the_inputs(self):
        broken = H.mutated(self.b.events, lambda ev: ev[2].__setitem__("d", D[9]))
        bad_plan = R.with_plan_dict(self.plan, lambda d: d["basis"].__setitem__("check_d", D[5]))
        self.assertEqual(T.outcome(R.confirm, bad_plan, broken, self.w)[:3], MISMATCH)
        self.assertEqual(T.outcome(X.confirm_restart_plan, "plan", self.plan.plan_hash, self.h, self.w.sessions,
                                   self.w.ledger)[:3], MISMATCH)

    def test_a_rebuild_error_after_matching_digests_is_a_mismatch_not_a_new_error(self):
        # the digests match the inputs, but the plan asks for a check_d that has no next session
        sessions = R.sessions_with(dates=D[:6])
        plan = R.prep(self.h, self.w, D[3], D[4], "r1", sessions)
        bad = R.refreshed(plan, lambda bs: bs.__setitem__("check_d", D[5]))
        self.assertEqual(T.outcome(R.confirm, bad, self.h, self.w, sessions)[:3], MISMATCH)

    def test_the_basis_is_rebuilt_from_the_original_and_the_original_is_projected_once(self):
        real = O.project_history_ledger
        with mock.patch("v2_history_restart.build.project_history_ledger", wraps=real) as spy:
            R.confirm(self.plan, self.h, self.w)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args[0][0], self.h)
        self.assertEqual(spy.call_args[0][3], D[4])

    def test_the_current_history_is_not_projected_to_check_d_for_a_candidate(self):
        # the candidate is never projected to check_d: resume_after == check_d would be refused by the day rules
        plan = R.prep(self.h, self.w, D[4], D[4], "r1")
        res = R.confirm(plan, self.h, self.w)
        self.assertEqual(T.outcome(O.project_history_ledger, res.history, self.w.sessions, self.w.ledger, D[4])[1],
                         "target_not_after_boundary")
        self.assertEqual(R.confirm(plan, res.history, self.w).status, "NO_CHANGE")

    def test_a_plan_from_a_message_round_trips(self):
        copy_plan = X.RestartPlan.from_dict(self.plan.to_dict())
        self.assertEqual(copy_plan, self.plan)
        self.assertEqual(R.confirm(copy_plan, self.h, self.w).status, "CONFIRMED_IN_MEMORY")


class ConfirmAgainstItsOwnCandidate(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.h, self.w = self.b.history(), self.b.w

    def test_the_same_plan_against_its_candidate_is_no_change_with_no_second_record(self):
        for resume, check_d in ((D[3], D[4]), (D[3], D[3]), (D[4], D[4])):
            rid = "r-%s" % resume
            plan, res = R.run(self.h, self.w, resume, check_d, rid)
            again = R.confirm(plan, res.history, self.w)
            self.assertEqual(again.status, "NO_CHANGE", (resume, check_d))
            self.assertEqual(again.history, res.history)
            self.assertEqual(len(again.history.events), len(self.h.events) + 1)
            self.assertEqual(sum(e["kind"] == "RESTART_UNKNOWN" for e in again.history.events), 1)
            self.assertEqual(again.plan_hash, plan.plan_hash)
            self.assertEqual((again.committed, again.committable), (False, False))

    def test_the_prefix_is_validated_and_checked_against_the_plan(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        real = V.validate_history
        with mock.patch("v2_history_restart.confirm.validate_history", wraps=real) as spy:
            R.confirm(plan, res.history, self.w)
        digests = [c[0][0].digest for c in spy.call_args_list]
        self.assertIn(self.h.digest, digests)                       # the physical prefix was checked
        self.assertIn(res.history.digest, digests)

    def test_a_prefix_that_does_not_match_the_plan_is_refused(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        hexs = "f" * 64
        for key in ("history_digest", "expected_head_hash", "expected_state_digest"):
            bad = R.refreshed(plan, lambda bs, key=key: bs.__setitem__(key, hexs))
            self.assertEqual(T.outcome(R.confirm, bad, res.history, self.w)[:3], MISMATCH, key)
        bad = R.refreshed(plan, lambda bs: bs.__setitem__("floor", {"last_apply_d": D[1], "last_declared_d": None,
                                                                    "prev_boundary": D[0]}))
        self.assertEqual(T.outcome(R.confirm, bad, res.history, self.w)[:3], MISMATCH)

    def test_the_prefix_mismatch_is_found_before_anything_is_rebuilt(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        hexs = "f" * 64
        from v2_history_restart import confirm as confirm_module
        real = confirm_module.build_restart
        for key in ("history_digest", "expected_head_hash", "expected_state_digest"):
            bad = R.refreshed(plan, lambda bs, key=key: bs.__setitem__(key, hexs))
            with mock.patch("v2_history_restart.confirm.build_restart", wraps=real) as spy:
                out = T.outcome(R.confirm, bad, res.history, self.w)
            self.assertEqual(out[:3], MISMATCH, key)
            self.assertEqual(spy.call_count, 0, key)                 # the comparison with the plan comes first
        with mock.patch("v2_history_restart.confirm.build_restart", wraps=real) as spy:
            self.assertEqual(R.confirm(plan, res.history, self.w).status, "NO_CHANGE")
        self.assertEqual(spy.call_count, 1)

    def test_a_history_that_moved_beyond_the_candidate_is_stale(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        b = H.HB(world=self.w, events=res.history.events)
        b.declare(D[4], "q9")
        self.assertEqual(T.outcome(R.confirm, plan, b.history(), self.w)[:3], STALE)

    def test_a_different_history_or_changed_inputs_is_stale_not_no_change(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        other = H.HB()
        other.apply(D[1], 27.0)
        self.assertEqual(T.outcome(R.confirm, plan, other.history(), self.w)[:3], STALE)
        rows = self.w.ledger + [P.obs("N1", D[8], 30.0)]
        self.assertEqual(T.outcome(R.confirm, plan, res.history, self.w, None, rows)[:3], STALE)

    def test_a_candidate_that_differs_only_in_the_request_is_not_the_plans_candidate(self):
        plan, res = R.run(self.h, self.w, D[3], D[3], "r1")
        other_plan, other_res = R.run(self.h, self.w, D[3], D[3], "r2")
        self.assertEqual(T.outcome(R.confirm, plan, other_res.history, self.w)[:3], STALE)

    def test_the_equal_case_never_confirms_an_unconfirmed_future_session(self):
        sessions = R.sessions_with(unconfirmed=(D[5],))
        plan = R.prep(self.h, self.w, D[4], D[4], "r1", sessions)
        res = R.confirm(plan, self.h, self.w, sessions)
        self.assertEqual(R.confirm(plan, res.history, self.w, sessions).status, "NO_CHANGE")
        events = res.history.events
        self.assertEqual(events[-1]["boundary_session"]["date"], D[4])
        # the unconfirmed session is not turned into a confirmed one by this operation
        self.assertFalse(sessions.get(D[5]).confirmed)


if __name__ == "__main__":
    unittest.main()
