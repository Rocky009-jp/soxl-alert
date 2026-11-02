"""B4-05 (the same inputs applied again), B4-06 (current inputs that differ from the saved ones) and B4-07 (sessions)."""
import unittest
from unittest import mock

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O


def rule(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


class SameInputs(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()
        self.map = {2: "DROP", 3: "REAPPLY"}

    def test_the_saved_inputs_are_kept_and_the_state_is_calculated_from_the_new_parent(self):
        plan, res = R.run(self.b, 1, self.map, D[3], "r4-1")
        events, old = res.history.events, self.b.events
        new = events[5]
        self.assertEqual(new["kind"], "APPLY")
        for key in ("decision", "row", "prev_row", "prev_session_date"):
            self.assertEqual(R.cj(new["confirmed_inputs"][key]), R.cj(old[3]["confirmed_inputs"][key]))
        self.assertEqual(new["d"], D[2])
        self.assertEqual(new["parent_hash"], events[4]["event_hash"])
        # the new parent is APPLY D1 (not the initial state), so the day is calculated on another base
        self.assertEqual(events[5]["state_after"]["base"]["as_of_d"], D[1])
        self.assertIsNone(old[3]["state_after"]["base"]["as_of_d"])
        self.assertNotEqual(R.cj(new["state_after"]), R.cj(old[3]["state_after"]))
        # the independent builder calculates the same day with the real S1 prepare_day
        self.assertEqual(R.cj(new), R.cj(R.oracle(self.b, 1, self.map, "r4-1", D[3])[5]))

    def test_the_changed_items_and_the_same_flag_come_from_the_values(self):
        b = self.b
        mapping = {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}
        plan, res = R.run(b, 0, mapping, D[3], "r4-1")
        events, old = res.history.events, b.events
        restore = events[4]
        want = []
        for entry, seq in ((restore["replay"][0], 1), (restore["replay"][2], 3)):
            fresh = events[entry["seq"]]
            diff = sorted(k for k in ("input_hash", "skipped_sessions", "transition_result", "state_after")
                          if R.cj(fresh[k]) != R.cj(old[seq][k]))
            want.append((not diff, diff))
            self.assertIs(entry["same_as_superseded"], not diff)
        self.assertEqual(want, [(True, []), (False, ["state_after", "transition_result"])])
        changes = plan.basis["changes"]
        self.assertEqual([(c["op"], c["kind"], c["d"], c["to_seq"], c["same_as_superseded"], c["changed_fields"])
                          for c in changes],
                         [("REAPPLY", "APPLY", D[1], 5, True, []),
                          ("DROP", "RESTART_UNKNOWN", D[1], None, None, []),
                          ("REAPPLY", "APPLY", D[2], 6, False, ["state_after", "transition_result"])])

    def test_the_skipped_sessions_and_the_input_hash_follow_the_new_base(self):
        b = R.ex_restart_over_gap()
        plan, res = R.run(b, 1, {2: "DROP", 3: "REAPPLY"}, D[5], "r4-1")
        new = res.history.events[5]
        self.assertEqual(new["skipped_sessions"], [D[2], D[3]])           # the saved day skipped nothing after the restart
        self.assertEqual(b.events[3]["skipped_sessions"], [])
        self.assertEqual(new["confirmed_inputs"]["session_context"][0]["date"], D[1])
        self.assertEqual(b.events[3]["confirmed_inputs"]["session_context"][0]["date"], D[3])
        entry = plan.basis["changes"][1]
        self.assertEqual(entry["changed_fields"], ["input_hash", "skipped_sessions", "state_after", "transition_result"])

    def test_the_calculation_goes_through_the_unchanged_apply_transition_and_evaluate_day(self):
        import v2_history_restore.build as build
        import v2_history_restore.records as records
        with mock.patch.object(records, "apply_transition", wraps=records.apply_transition) as spy, \
                mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day:
            R.prep(self.b, 1, self.map, D[3], "r4-1")
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args[0][0].as_of_d, D[1])               # the new parent, not the saved one
        self.assertEqual(day.call_count, 1)
        self.assertEqual(day.call_args[0][0].as_of_d, D[1])
        self.assertEqual(day.call_args[0][1], D[2])

    def test_a_copied_old_state_or_transition_is_not_what_the_runtime_gives(self):
        plan = R.prep(self.b, 1, self.map, D[3], "r4-1")
        records = plan.basis["candidate_records"]
        old = self.b.events[3]
        self.assertNotEqual(R.cj(records[1]["state_after"]), R.cj(old["state_after"]))
        self.assertNotEqual(R.cj(records[1]["transition_result"]), R.cj(old["transition_result"]))


class CurrentInputs(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()
        self.map = {2: "DROP", 3: "REAPPLY"}

    def prep(self, **kw):
        return R.prep(self.b, 1, self.map, D[3], "r4-1", **kw)

    def test_a_changed_market_value_is_refused_even_when_the_decision_would_be_the_same(self):
        series = R.with_row(self.b.w, D[2], soxx=111.0)               # still above the average: the same rules hold
        self.assertEqual(rule(self.prep, series=series), ("restore_market_input_changed", "series", None, D[2]))
        series = R.with_row(self.b.w, D[1], rsi=51.0)                 # the previous row of D2 differs
        self.assertEqual(rule(self.prep, series=series), ("restore_market_input_changed", "series", None, D[2]))
        odd = R.ReadSeries(self.b.w.series, {D[1]})                   # the previous row cannot be read: null, not the saved one
        self.assertEqual(rule(self.prep, series=odd), ("restore_market_input_changed", "series", None, D[2]))

    def test_the_series_must_agree_with_the_sessions_on_the_previous_day(self):
        dates = [d for d in D if d != D[1]]
        series = P.make_series(dates=dates)
        e = R.refusal(self.prep, series=series)
        self.assertEqual((e.code, e.field), ("session_series_mismatch", "market"))
        e = R.refusal(self.prep, series=P.make_series(dates=[d for d in D if d != D[2]]))
        self.assertEqual((e.code, e.field), ("target_row_missing", "market"))

    def test_a_missing_other_or_changed_decision_is_refused(self):
        ledger = R.without(self.b.w.ledger, "R-" + D[2])
        self.assertEqual(rule(self.prep, ledger=ledger), ("restore_decision_changed", "observations", None, D[2]))
        other = [dict(r, record_id="R-other") if r["record_id"] == "R-" + D[2] else r for r in self.b.w.ledger]
        self.assertEqual(rule(self.prep, ledger=other), ("restore_decision_changed", "observations", None, D[2]))
        changed = [dict(r, current_fg_value=29.0) if r["record_id"] == "R-" + D[2] else r for r in self.b.w.ledger]
        self.assertEqual(rule(self.prep, ledger=changed), ("restore_decision_changed", "observations", None, D[2]))

    def test_a_conflict_of_the_selection_itself_keeps_its_own_code(self):
        ledger = self.b.w.ledger + [P.obs("R-second", D[2], 31.0)]
        e = R.refusal(self.prep, ledger=ledger)
        self.assertEqual((e.code, e.field), ("decision_conflict", "observation_role"))

    def test_a_saved_decision_chosen_through_a_supplement_is_a_success(self):
        b = R.ex_removed_row_after_restart()
        h = b.history()
        self.assertEqual(O.project_history_ledger(h, b.w.sessions, b.w.ledger, D[4]).supplemented[0]["seq"], 3)
        plan, res = R.run(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY"}, D[4], "r4-1")
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        events = res.history.events
        self.assertEqual(events[7]["variant"], "ROW_REMOVED")
        self.assertEqual(events[7]["applied_ref"]["seq"], 6)              # the re-written APPLY, found again by its fingerprint
        self.assertEqual(events[7]["applied_ref"]["event_hash"], events[6]["event_hash"])
        final = O.project_history_ledger(res.history, b.w.sessions, b.w.ledger, D[4])
        self.assertEqual([r["record_id"] for r in final.rows], ["R-" + D[1], "R-" + D[2]])


class Sessions(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()
        self.map = {2: "DROP", 3: "REAPPLY"}

    def prep(self, sessions, check=D[3]):
        return R.prep(self.b, 1, self.map, check, "r4-1", sessions=sessions)

    def test_a_middle_session_that_is_not_confirmed_stops_the_restore(self):
        b = R.ex_restart_over_gap()
        sessions = R.sessions_with(unconfirmed=(D[3],))
        e = R.refusal(R.prep, b, 1, {2: "DROP", 3: "REAPPLY"}, D[5], "r4-1", sessions=sessions)
        self.assertEqual((e.code, e.field, e.detail), ("intermediate_session_unconfirmed", "sessions", D[3]))

    def test_the_session_range_must_agree_with_the_saved_one_on_the_shared_days(self):
        late_open = R.sessions_with({D[3]: R.later_open})                # next(D2): the open time is part of the range
        self.assertEqual(rule(self.prep, late_open), ("session_context_mismatch", "sessions", None, D[2]))
        sessions = R.sessions_with({D[2]: R.earlier_close})              # D2 itself is a middle entry of its range
        self.assertEqual(rule(self.prep, sessions), ("session_context_mismatch", "sessions", None, D[2]))
        without_next = R.sessions_with(dates=[d for d in D if d != D[3]])    # a date of the saved range is gone
        self.assertEqual(rule(self.prep, without_next, D[4])[0], "session_context_missing")

    def test_only_the_close_time_and_the_confirmed_flag_of_the_next_session_may_differ(self):
        base = R.prep(self.b, 1, self.map, D[3], "r4-1")
        base_new = [r for r in base.basis["candidate_records"] if r["kind"] == "APPLY"][0]
        for sessions in (R.sessions_with({D[3]: R.earlier_close}), R.sessions_with(unconfirmed=(D[3],))):
            plan = self.prep(sessions, D[4])
            new = [r for r in plan.basis["candidate_records"] if r["kind"] == "APPLY"][0]
            self.assertEqual(new["input_hash"], base_new["input_hash"])           # the hash drops those two items
            self.assertNotEqual(plan.basis["sessions_digest"], base.basis["sessions_digest"])
            self.assertEqual(plan.basis["changes"][1]["changed_fields"], base.basis["changes"][1]["changed_fields"])

    def test_check_d_needs_a_next_session_but_that_one_need_not_be_confirmed(self):
        plan = self.prep(R.sessions_with(unconfirmed=(D[4],)), D[3])
        self.assertEqual(plan.status, "READY")
        e = R.refusal(self.prep, R.sessions_with(dates=D[:4]), D[3])
        self.assertEqual((e.code, e.field), ("next_session_missing", "sessions"))
        e = R.refusal(self.prep, R.sessions_with(unconfirmed=(D[3],)), D[3])
        self.assertEqual((e.code, e.field), ("target_unconfirmed", "sessions"))


if __name__ == "__main__":
    unittest.main()
