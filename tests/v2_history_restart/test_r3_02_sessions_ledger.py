"""B3-04 (sessions, error priority) and B3-05 (the whole-history ledger projection of the original history)."""
import unittest
from unittest import mock

import r3_helpers as R

T, H, X, D, P, V, O = R.T, R.H, R.X, R.D, R.P, R.V, R.O
BOUNDARY = ("restart_invalid", "resume_after", "restart_boundary")


class Sessions(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()                  # GENESIS D0, APPLY D1, APPLY D2
        self.h = self.b.history()
        self.w = self.b.w

    def test_resume_session_must_exist_and_be_confirmed(self):
        self.assertEqual(R.refusal(R.prep, self.h, self.w, "2026-03-07", D[5], "r1"), BOUNDARY)   # a Saturday
        self.assertEqual(R.refusal(R.prep, self.h, self.w, D[3], D[5], "r1", R.sessions_with(unconfirmed=(D[3],))),
                         BOUNDARY)

    def test_check_d_errors_are_the_existing_input_errors(self):
        def check(sessions, resume, check_d):
            return R.refusal(R.prep, self.h, self.w, resume, check_d, "r1", sessions)
        self.assertEqual(check(None, D[3], "2026-03-07"), ("target_not_in_sessions", "sessions", None))
        self.assertEqual(check(R.sessions_with(unconfirmed=(D[5],)), D[3], D[5]), ("target_unconfirmed", "sessions", None))
        self.assertEqual(check(R.sessions_with(dates=D[:6]), D[3], D[5]), ("next_session_missing", "sessions", None))
        # the first session has no previous one
        w0 = H.HB()
        self.assertEqual(R.refusal(R.prep, w0.history(), w0.w, D[0], D[0], "r1"),
                         ("previous_session_missing", "sessions", None))
        # both missing: the next one is looked at first
        self.assertEqual(R.refusal(R.prep, w0.history(), w0.w, D[0], D[0], "r1", R.sessions_with(dates=D[:1])),
                         ("next_session_missing", "sessions", None))

    def test_check_d_error_comes_before_the_resume_error(self):
        out = R.refusal(R.prep, self.h, self.w, D[5], D[5], "r1", R.sessions_with(unconfirmed=(D[5],)))
        self.assertEqual(out, ("target_unconfirmed", "sessions", None))

    def test_the_session_after_check_d_may_be_unconfirmed(self):
        plan = R.prep(self.h, self.w, D[3], D[4], "r1", R.sessions_with(unconfirmed=(D[5],)))
        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.basis["boundary_session"]["date"], D[3])
        # the unconfirmed next session is not made confirmed and no session is invented
        self.assertEqual(R.confirm(plan, self.h, self.w, R.sessions_with(unconfirmed=(D[5],))).status,
                         "CONFIRMED_IN_MEMORY")

    def test_resume_equal_check_d_never_confirms_a_future_session(self):
        plan = R.prep(self.h, self.w, D[4], D[4], "r1", R.sessions_with(unconfirmed=(D[5],)))
        rec = plan.basis["candidate_history"]["events"][-1]
        self.assertTrue(rec["boundary_session"]["confirmed"])
        self.assertEqual(rec["boundary_session"]["date"], D[4])

    def test_the_stored_next_session_of_an_apply_close_and_confirmed_are_harmless_open_is_not(self):
        # APPLY D2 stored [D1, D2, D3]: the D3 session is the next session of D2
        def run(sessions):
            return R.prep(self.h, self.w, D[4], D[4], "r1", sessions)
        self.assertEqual(run(R.sessions_with({D[3]: R.earlier_close})).status, "READY")
        self.assertEqual(run(R.sessions_with(unconfirmed=(D[3],))).status, "READY")
        out = R.refusal(run, R.sessions_with({D[3]: R.later_open}))
        self.assertEqual(out[:2], ("session_context_mismatch", "sessions"))

    def test_bad_sessions_or_rows_stop_before_the_request_id_check(self):
        v = T.example_v()
        h, w = v.history(), v.w                  # uses q1 and q2
        out = T.outcome(X.prepare_restart_plan, h, D[4], None, w.ledger, D[5], "q1", T.WHEN)
        self.assertEqual(out[:3], ("err", "sessions_invalid", "sessions"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, [{"x": 1}], D[5], "q1", T.WHEN)
        self.assertEqual(out[:2], ("err", "record_id_invalid"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, None, D[5], "q1", T.WHEN)
        self.assertEqual(out[:3], ("err", "observation_invalid", "observations"))
        out = T.outcome(X.prepare_restart_plan, h, "2026-13-40", w.sessions, w.ledger, D[5], "q1", T.WHEN)
        self.assertEqual(out[:3], ("err", "invalid_date", "resume_after"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, w.ledger, "nope", "q1", T.WHEN)
        self.assertEqual(out[:3], ("err", "invalid_date", "target_session_date"))

    def test_an_old_context_difference_and_a_used_id_give_the_id_conflict_unused_id_gives_the_context_error(self):
        v = T.example_v()                        # the boundary of the last segment is D3
        h, w = v.history(), v.w
        changed = R.sessions_with({D[3]: R.earlier_close})
        used = R.refusal(R.prep, h, w, D[4], D[5], "q2", changed)
        self.assertEqual(used, ("history_request_conflict", "request_id", None))
        unused = R.refusal(R.prep, h, w, D[4], D[5], "r9", changed)
        self.assertEqual(unused[:2], ("session_context_mismatch", "sessions"))
        gone = R.sessions_with(dates=[d for d in D if d != D[3]])
        self.assertEqual(R.refusal(R.prep, h, w, D[4], D[5], "q2", gone), used)
        self.assertEqual(R.refusal(R.prep, h, w, D[4], D[5], "r9", gone)[:2], ("session_context_missing", "sessions"))

    def test_the_request_time_and_form_come_before_the_id_check(self):
        v = T.example_v()
        h, w = v.history(), v.w
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, w.ledger, D[5], "q1", "2026-06-01")
        self.assertEqual(out[:3], ("err", "datetime_invalid", "requested_at"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, w.ledger, D[5], "", T.WHEN)
        self.assertEqual(out[:4], ("err", "restart_invalid", "request_id", "request_id"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, w.ledger, D[5], "bad id!", T.WHEN)
        self.assertEqual(out[:4], ("err", "restart_invalid", "request_id", "request_id"))
        out = T.outcome(X.prepare_restart_plan, h, D[4], w.sessions, w.ledger, D[5], 5, T.WHEN)
        self.assertEqual(out[:4], ("err", "restart_invalid", "request_id", "request_id"))


class OriginalLedgerProjection(unittest.TestCase):
    def test_the_original_history_is_projected_once_with_the_explicit_check_d(self):
        b = R.example_u()
        h, w = b.history(), b.w
        real = O.project_history_ledger
        with mock.patch("v2_history_restart.build.project_history_ledger", wraps=real) as spy:
            plan = R.prep(h, w, D[3], D[3], "r1")
        self.assertEqual(spy.call_count, 1)
        args = spy.call_args[0]
        self.assertEqual(args[0], h)                 # the original, not the candidate
        self.assertEqual(args[3], D[3])
        ledger = real(h, w.sessions, w.ledger, D[3])
        self.assertEqual(plan.basis["ledger_digest"], ledger.ledger_digest)
        self.assertEqual(plan.basis["effective_digest"], ledger.effective_digest)

    def test_changed_rows_of_an_old_apply_stop_the_restart(self):
        b = R.example_u()
        h, w = b.history(), b.w
        changed = P.obs("R-%s" % D[1], D[1], 44.0)
        rows = [r for r in w.ledger if r["record_id"] != "R-%s" % D[1]] + [changed]
        self.assertEqual(R.refusal(R.prep, h, w, D[3], D[3], "r1", None, rows), ("ledger_mismatch", "observations", None))
        self.assertEqual(R.refusal(R.prep, h, w, D[3], D[3], "r1", None, w.ledger[1:]),
                         ("ledger_mismatch", "observations", None))

    def test_a_late_row_for_a_skipped_or_declared_day_stops_the_restart(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 29.0)                       # D2 is skipped
        self.assertEqual(O.read_effective(b.history()).applies[-1]["skipped"], [D[2]])
        late = P.obs("L2", D[2], 22.0)
        self.assertEqual(R.refusal(R.prep, b.history(), b.w, D[4], D[4], "r1", None, b.w.ledger + [late]),
                         ("late_observation", "observations", None))
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "q1")
        self.assertEqual(R.refusal(R.prep, c.history(), c.w, D[3], D[3], "r1", None, c.w.ledger + [late]),
                         ("late_observation", "observations", None))

    def test_after_an_explicit_ack_the_restart_can_be_planned(self):
        b = R.example_u()
        h, w = b.history(), b.w
        changed = P.obs("R-%s" % D[1], D[1], 44.0)
        rows = [r for r in w.ledger if r["record_id"] != "R-%s" % D[1]] + [changed]
        cmds = [T.ack_cmd(h, "CHANGED", D[1], [T.fp(changed)], 1)]
        _plan, res = T.run_plan(h, cmds, w.sessions, rows, D[2], "a1")
        acked = T.extend(h, res)
        plan = R.prep(acked, w, D[3], D[3], "r1", None, rows)
        self.assertEqual(plan.status, "READY")
        self.assertEqual(R.confirm(plan, acked, w, None, rows).status, "CONFIRMED_IN_MEMORY")
        projected = O.project_history_ledger(acked, w.sessions, rows, D[3])
        self.assertEqual(plan.basis["effective_digest"], projected.effective_digest)
        self.assertEqual(plan.basis["ledger_digest"], projected.ledger_digest)
        # the acknowledgement keeps the effective ledger equal to what the stored APPLY records saw
        self.assertEqual(projected.effective_digest,
                         O.project_history_ledger(h, w.sessions, w.ledger, D[2]).effective_digest)

    def test_every_row_is_parsed_and_a_conflicting_duplicate_is_refused(self):
        b = R.example_u()
        h, w = b.history(), b.w
        dup = w.ledger + [dict(w.ledger[0], current_fg_value=33.0)]
        self.assertEqual(R.refusal(R.prep, h, w, D[3], D[3], "r1", None, dup), ("record_id_conflict", "record_id", None))
        extra = P.obs("X1", D[1], 41.0, hour=21)
        self.assertEqual(R.refusal(R.prep, h, w, D[3], D[3], "r1", None, w.ledger + [extra])[0], "decision_conflict")

    def test_the_inputs_and_the_raw_ledger_are_not_changed(self):
        b = R.example_u()
        h, w = b.history(), b.w
        before = (h.digest, R.cj(w.ledger), [R.cj(T.H.session_dict(s)) for s in w.sessions.sessions])
        R.prep(h, w, D[3], D[3], "r1")
        after = (h.digest, R.cj(w.ledger), [R.cj(T.H.session_dict(s)) for s in w.sessions.sessions])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
