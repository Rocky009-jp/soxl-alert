"""B4-13 (the order of the failures) and B4-14 (the request id and the no-effect rule)."""
import unittest
from unittest import mock

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O
import v2_history_restore.build as build  # noqa: E402


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


CONFLICT = ("history_request_conflict", "request_id", None, None)


class Order(unittest.TestCase):
    def test_the_shape_of_the_point_and_the_operations_come_before_the_request_id(self):
        b = R.ex_restart_between()
        mapping = {2: "DROP", 3: "REAPPLY"}
        bad_point = {"seq": 99, "event_hash": "0" * 64}
        want = ("restore_invalid", "restore_point", "restore_point_not_effective", None)
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "q1", pt=bad_point), want)               # q1 is used
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "r4-1", pt=bad_point), want)             # and unused
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "q1"), CONFLICT)
        want = ("restore_invalid", "ops", "superseded_mismatch", None)
        self.assertEqual(err(R.prep, b, 1, None, D[3], "q1", ops=[]), want)
        self.assertEqual(err(R.prep, b, 1, None, D[3], "r4-1", ops=[]), want)
        # a date that is not a date comes first of all
        self.assertEqual(err(R.prep, b, 1, mapping, "x", "")[:2], ("invalid_date", "target_session_date"))
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "")[:3], ("restore_invalid", "request_id", "request_id"))

    def test_the_context_that_stays_is_checked_after_the_request_id(self):
        b = R.ex_restart_between()
        sessions = R.sessions_with({D[1]: R.earlier_close})            # the retained APPLY D1 sees another close
        mapping = {2: "DROP", 3: "REAPPLY"}
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "r4-1", sessions=sessions)[:2], ("session_context_mismatch", "sessions"))
        self.assertEqual(err(R.prep, b, 1, mapping, D[3], "q1", sessions=sessions), CONFLICT)

    def test_the_evidence_of_the_whole_candidate_is_checked_after_the_request_id(self):
        b, _late = R.ex_declare_then_late()
        mapping = {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY"}
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1"),
                         ("resolution_invalid", "commands", "declare_valid_decision", None))
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "q1"), CONFLICT)

    def test_consumption_is_checked_before_the_saved_decision(self):
        b = R.ex_declare_between()
        gone = [r for r in b.w.ledger if r["record_id"] != "R-" + D[4]]                 # the decision of the re-applied D4 is gone
        mapping = {4: "DROP", 5: "REAPPLY"}
        self.assertEqual(err(R.prep, b, 3, mapping, D[5], "r4-1", ledger=gone)[:1], ("restore_decision_changed",))
        both = gone + [P.obs("X3", D[3], 45.0)]                                          # and the declared D3 has a row
        self.assertEqual(err(R.prep, b, 3, mapping, D[5], "r4-1", ledger=both), ("restore_requires_consume", "ops", None, D[3]))

    def test_the_saved_decision_is_checked_before_the_saved_market_values(self):
        b = R.ex_declare_between()
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        gone = [r for r in b.w.ledger if r["record_id"] != "R-" + D[2]]
        series = R.with_row(b.w, D[2], soxx=300.0)
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", series=series),
                         ("restore_market_input_changed", "series", None, D[2]))
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=gone),
                         ("restore_decision_changed", "observations", None, D[2]))
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=gone, series=series),
                         ("restore_decision_changed", "observations", None, D[2]))

    def test_the_market_values_come_before_the_projection_that_refuses_a_late_row_and_that_before_evaluate_day(self):
        b = R.ex_old_skip()
        late = b.w.ledger + [P.obs("L2", D[2], 22.0)]
        series = R.with_row(b.w, D[3], soxx=300.0)                  # the re-applied D3 now has other market values
        mapping = {2: "REAPPLY", 3: "DROP", 4: "REAPPLY"}
        with mock.patch.object(build, "project_history_ledger", wraps=build.project_history_ledger) as projection, \
                mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day:
            self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=late, series=series),
                             ("restore_market_input_changed", "series", None, D[3]))
            self.assertEqual((projection.call_count, day.call_count), (0, 0))
            self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=late),
                             ("late_observation", "observations", None, D[2]))
            self.assertEqual((projection.call_count, day.call_count), (1, 0))      # refused by the projection, before the days
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", series=series)[0], "restore_market_input_changed")

    def test_the_stages_run_in_the_fixed_order(self):
        b = R.ex_declare_between()
        order = []

        def wrap(name):
            real = getattr(build, name)

            def inner(*a, **k):
                order.append(name)
                return real(*a, **k)
            return inner

        names = ("series_inputs", "plan_records", "_check_candidate", "_replay_evidence", "_prior_rows", "_check_new_days",
                 "_check_saved_decisions", "_check_saved_market", "project_history_ledger", "_check_days_again")
        patches = [mock.patch.object(build, n, side_effect=wrap(n)) for n in names]
        for p in patches:
            p.start()
        try:
            R.prep(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, D[5], "r4-1")
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(order, ["series_inputs", "plan_records", "_check_candidate", "_replay_evidence", "_prior_rows",
                                 "_check_new_days", "_check_saved_decisions", "_check_saved_market",
                                 "project_history_ledger", "_check_days_again"])

    def test_a_failing_projection_of_the_source_does_not_stop_a_restore_that_removes_the_cause(self):
        b = R.ex_declare_tail()                                   # APPLY D1, DECLARE_MISSING D2
        sessions = R.sessions_with({D[3]: R.later_open})        # the declaration's saved context (it holds D3) no longer fits
        e = R.refusal(R.O.project_history_ledger, b.history(), sessions, b.w.ledger, D[5])
        self.assertEqual((e.code, e.field, e.detail), ("session_context_mismatch", "sessions", D[2]))
        plan = R.prep(b, 1, {2: "DROP"}, D[5], "r4-1", sessions=sessions)
        self.assertEqual(plan.status, "READY")
        res = R.confirm(plan, b.history(), b.w, sessions=sessions)
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        ok = R.O.project_history_ledger(res.history, sessions, b.w.ledger, D[5])        # the candidate projects well
        self.assertEqual(len(ok.rows), len(b.w.ledger))
        # not a success when the dropped declaration's day has a decision: that day would have to be consumed
        late = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, {2: "DROP"}, D[5], "r4-1", sessions=sessions, ledger=late),
                         ("restore_requires_consume", "ops", None, D[2]))
        # and keeping the declaration keeps the failure (no restore of anything else repairs it)
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY"}, D[5], "r4-1", sessions=sessions)[0], "restore_no_effect")

    def test_a_plan_that_is_wrong_is_refused_before_the_inputs_and_wrong_inputs_before_stale(self):
        b = R.ex_restart_between()
        mapping = {2: "DROP", 3: "REAPPLY"}
        plan = R.prep(b, 1, mapping, D[3], "r4-1")
        broken_inputs = [{"record_id": "bad"}]
        tampered = R.with_plan_dict(plan, lambda d: d["basis"].update(check_d=D[4]))
        # a wrong plan comes first, whatever the inputs
        self.assertEqual(err(R.confirm, tampered, b.history(), b.w, ledger=broken_inputs)[:2], ("history_plan_mismatch", "plan"))
        # wrong inputs come before the staleness of a history that has moved on
        b2 = R.ex_restart_between()
        b2.apply(D[3], 30.0)
        moved = b2.history()
        stale = err(R.confirm, plan, moved, b.w)
        self.assertEqual(stale[:2], ("history_plan_stale", "plan"))
        wrong = err(R.confirm, plan, moved, b.w, ledger=broken_inputs)
        self.assertNotEqual(wrong[:2], ("history_plan_stale", "plan"))
        self.assertEqual(wrong[:2], err(R.confirm, plan, b.history(), b.w, ledger=broken_inputs)[:2])


class IdsAndNoEffect(unittest.TestCase):
    def test_every_request_id_of_the_whole_physical_history_is_taken(self):
        b = R.ex_after_three_restores()                                   # q1..q7: effective, superseded and restores
        for rid in ("q1", "q2", "q3", "q4", "q5", "q6", "q7"):
            with self.subTest(rid):
                self.assertEqual(err(R.prep, b, 24, {25: "REAPPLY"}, D[8], rid), CONFLICT)
        self.assertEqual(err(R.prep, b, 24, {25: "REAPPLY"}, D[8], "q1"), CONFLICT)

    def test_an_id_is_taken_whatever_the_record_kind_and_after_a_replay(self):
        b = R.ex_ack_between()
        for rid in ("q1", "q2"):                                           # a restart and an acknowledgement
            self.assertEqual(err(R.prep, b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, D[5], rid), CONFLICT)
        b = R.ex_migrated_tail()
        for rid in ("mig-1", "q1", "q4"):                                   # a migration, a migrated request, a later restart
            self.assertEqual(err(R.prep, b, 7, {8: "REAPPLY", 9: "DROP", 10: "REAPPLY"}, D[8], rid), CONFLICT)

    def test_the_same_content_or_another_time_does_not_make_a_second_restore(self):
        b = R.ex_restart_between()
        mapping = {2: "DROP", 3: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[3], "r4-1")
        later = R.WHEN.replace(hour=R.WHEN.hour + 1)
        # against the history that already holds the restore (retire it, apply the new day again): the id is taken
        point = {"seq": 1, "event_hash": res.history.events[1]["event_hash"]}
        ops = [{"op": "RETIRE", "from_seq": 4}, {"op": "REAPPLY", "from_seq": 5}]
        for when in (R.WHEN, later):
            self.assertEqual(err(R.prep, b, 1, None, D[3], "r4-1", history=res.history, pt=point, ops=ops, when=when),
                             CONFLICT)
        # an unused id gives a READY plan; another time gives another request hash for the same id
        self.assertEqual(R.prep(b, 1, mapping, D[3], "r4-2").status, "READY")
        changed_time = R.prep(b, 1, mapping, D[3], "r4-1", when=later)
        self.assertEqual(plan.basis["request_hash"], changed_time.basis["request_hash"])      # the time is not part of it
        self.assertNotEqual(plan.basis["requested_at"], changed_time.basis["requested_at"])
        self.assertNotEqual(plan.plan_hash, changed_time.plan_hash)

    def test_a_restore_that_changes_nothing_is_refused(self):
        # REPLAY and a REAPPLY with the same values, nothing dropped: nothing would change
        b = R.ex_restart_over_gap()
        self.assertEqual(err(R.prep, b, 0, {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}, D[5], "r4-1"),
                         ("restore_no_effect", "ops", None, None))

    def test_a_restore_with_a_drop_is_not_a_no_effect_even_when_the_market_state_is_the_same(self):
        b = R.ex_restart_tail()
        # dropping the last restart gives the state of the record before it, which the restart had reset to the initial
        # state: the market state differs here. The case with the same state: the restart was written on the initial state
        b0 = R.ex_null_restart()
        plan = R.prep(b0, 0, {1: "DROP"}, D[5], "r4-1")
        self.assertEqual(plan.status, "READY")
        self.assertEqual(R.cj(plan.basis["candidate_records"][0]["state_after"]), R.cj(b0.events[0]["state_after"]))
        self.assertEqual(R.cj(b0.events[1]["state_after"]), R.cj(b0.events[0]["state_after"]))        # the same state
        self.assertEqual(R.prep(b, 1, {2: "DROP"}, D[5], "r4-1").status, "READY")

    def test_the_recalculation_and_the_input_checks_run_even_when_the_outcome_is_a_no_effect(self):
        b = R.ex_restart_over_gap()
        mapping = {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}
        with mock.patch.object(build, "_check_days_again", wraps=build._check_days_again) as day, \
                mock.patch.object(build, "_check_saved_market", wraps=build._check_saved_market) as market:
            self.assertEqual(err(R.prep, b, 0, mapping, D[5], "r4-1")[0], "restore_no_effect")
        self.assertEqual((day.call_count, market.call_count), (1, 1))
        series = R.with_row(b.w, D[1], soxx=300.0)
        self.assertEqual(err(R.prep, b, 0, mapping, D[5], "r4-1", series=series)[0], "restore_market_input_changed")


if __name__ == "__main__":
    unittest.main()
