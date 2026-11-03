"""C1-07 (the stop stays), C1-08 (the decision), C1-09 (the market values), C1-10 (the order of the errors), C1-11 (what
the plan shows) and C1-12 (the no-effect rule) of the plan of a restore with CONSUME."""
import unittest
from unittest import mock

import c1_helpers as C
import v2_history_restore.build as build

H, P, R, V, D, O = C.H, C.P, C.R, C.V, C.D, C.O
CONSUME = C.CONSUME
invalid = C.invalid
MAIN = [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)]            # on C.s_declare(), restore point 3


class Stop(unittest.TestCase):
    """C1-07: a freed day that has a decision and is not consumed stops the plan, as before."""

    def test_the_declared_day_with_a_decision_stops_without_a_consume(self):
        b = C.s_declare()
        self.assertEqual(C.err(C.plan, b, 3, [("DROP", 4), ("REAPPLY", 5)], D[5]),
                         ("restore_requires_consume", "ops", None, D[3]))

    def test_the_declared_day_without_a_decision_is_no_stop(self):
        b = R.ex_declare_between()                               # no decision of D3
        self.assertEqual(C.plan(b, 3, [("DROP", 4), ("REAPPLY", 5)], D[5]).status, "READY")

    def test_one_of_two_days_consumed_stops_at_the_other(self):
        b = C.s_gap()
        self.assertEqual(C.err(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3)], D[5]),
                         ("restore_requires_consume", "ops", None, D[3]))
        # D3 consumed in front: the APPLY of D3 passes over D2, which has a decision and is not applied
        self.assertEqual(C.err(C.plan, b, 1, [("DROP", 2), (CONSUME, D[3]), ("REAPPLY", 3)], D[5]),
                         ("restore_requires_consume", "ops", None, D[2]))

    def test_the_stop_is_given_the_days_that_remain_after_the_consumed_ones(self):
        b = C.s_gap()
        with mock.patch.object(build, "_check_new_days", wraps=build._check_new_days) as spy:
            C.plan(b, 1, [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)], D[5])
        self.assertEqual(spy.call_args[0][2], [])
        with mock.patch.object(build, "_check_new_days", wraps=build._check_new_days) as spy:
            C.err(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3)], D[5])
        self.assertEqual(spy.call_args[0][2], [D[3]])


class Decision(unittest.TestCase):
    """C1-08."""

    def test_a_day_without_a_decision_is_refused(self):
        b = R.ex_declare_between()
        self.assertEqual(C.err(C.plan, b, 3, MAIN, D[5]), invalid("restore_consume_no_decision", D[3]))

    def test_the_selection_errors_of_the_core_are_returned_as_they_are(self):
        b = C.s_declare()
        two = b.w.ledger + [P.obs("X3b", D[3], 46.0)]
        e = C.err(C.plan, b, 3, MAIN, D[5], ledger=two)
        self.assertEqual(e[:2], ("decision_conflict", "observation_role"))
        early = [r for r in b.w.ledger if r["record_id"] != "X3"] + [P.obs("X3", D[3], 45.0, hour=8)]
        e = C.err(C.plan, b, 3, MAIN, D[5], ledger=early)
        self.assertEqual(e[:2], ("decision_outside_window", "observed_at_iso8601"))
        other = [r for r in b.w.ledger if r["record_id"] != "X3"] + [P.obs("X3", D[3], 45.0, hour=20)]
        # a decision observed in the window of D3 that names D4 as its target
        other[-1]["target_us_session_date"] = D[4]
        e = C.err(C.plan, b, 3, MAIN, D[5], ledger=other)
        self.assertEqual(e[:2], ("target_mismatch", "target_us_session_date"))

    def test_a_declaration_and_a_late_acknowledgement_that_are_dropped_give_the_later_decision(self):
        b, late = C.s_late()
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3), ("DROP", 4)], D[5])
        made = plan.basis["candidate_records"][1]
        self.assertEqual(made["d"], D[2])
        self.assertEqual(made["confirmed_inputs"]["decision"]["record_id"], "L2")
        self.assertEqual(made["confirmed_inputs"]["decision"]["current_fg_value"], 22.0)

    def test_a_late_acknowledgement_that_is_replayed_cannot_go_with_the_consumption_of_its_day(self):
        b, late = C.s_late()
        e = C.err(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3), ("REPLAY", 4)], D[5])
        self.assertEqual(e[:3], ("restore_invalid", "ops", "restore_ref_unmapped"))

    def test_the_decision_is_chosen_from_the_rows_the_kept_records_leave(self):
        b = C.s_declare()
        calls = []
        real = build.apply_records

        def spy(ctx, records):
            calls.append([r["kind"] for r in records])
            return real(ctx, records)
        with mock.patch.object(build, "apply_records", side_effect=spy):
            C.plan(b, 3, MAIN, D[5])
        # the unchanged function is applied to the kept acknowledgements and declarations first (none are kept here),
        # then to those of the whole candidate
        self.assertEqual(calls, [[], []])
        calls.clear()
        with mock.patch.object(build, "apply_records", side_effect=spy):
            C.plan(b, 3, [("DROP", 4), ("REAPPLY", 5)], D[5], ledger=[r for r in b.w.ledger if r["record_id"] != "X3"])
        self.assertEqual(calls, [[]])                       # nothing is consumed: nothing is read from the kept records

    def test_the_rows_that_the_kept_records_leave_are_the_rows_the_decision_is_chosen_from(self):
        # No ordinary input makes the kept acknowledgements and declarations exclude a row of a freed day (they name the
        # days they were written for), so the use of the answer is shown with a stand-in for the unchanged
        # apply_records: the first call (the kept records) leaves out the decision row X3; the plan must then find no
        # decision for D3. The second call (the whole candidate) is the real one.
        b = C.s_declare()
        real = build.apply_records
        calls = []

        def stand_in(ctx, records):
            remaining, actually, supplemented = real(ctx, records)
            calls.append(len(records))
            if len(calls) == 1:
                remaining = {k: v for k, v in remaining.items() if v.cols["record_id"] != "X3"}
            return remaining, actually, supplemented
        with mock.patch.object(build, "apply_records", side_effect=stand_in):
            e = C.err(C.plan, b, 3, MAIN, D[5])
        self.assertEqual(e, C.invalid("restore_consume_no_decision", D[3]))
        self.assertEqual(calls, [0])                          # refused before the whole candidate is looked at

    def test_a_decision_that_the_whole_candidate_does_not_give_any_more_is_refused(self):
        # The chain view refuses an acknowledgement that excludes the decision of an APPLY (exclude_applied), so no input
        # of the ordinary kind reaches the re-selection of stage 7 with another answer. The branch is passed through by
        # a stand-in for the unchanged select_decision that answers differently the second time it is asked for the day:
        # nothing at all, then another decision.
        b = C.s_declare()
        real = build.select_decision
        other = real([P.obs("Z3", D[3], 33.0)], b.w.sessions, D[3])
        for answer in (None, other):
            calls = []

            def stand_in(rows, sessions, d, answer=answer):
                calls.append(d)
                if d == D[3] and calls.count(D[3]) == 2:
                    return answer
                return real(rows, sessions, d)
            with mock.patch.object(build, "select_decision", side_effect=stand_in):
                e = C.err(C.plan, b, 3, MAIN, D[5])
            self.assertEqual(e, ("restore_decision_changed", "observations", None, D[3]))
            self.assertEqual(calls.count(D[3]), 2)

    def test_the_real_selection_is_asked_twice_for_a_consumed_day_and_agrees(self):
        b = C.s_declare()
        real = build.select_decision
        calls = []

        def spy(rows, sessions, d):
            calls.append(d)
            return real(rows, sessions, d)
        with mock.patch.object(build, "select_decision", side_effect=spy):
            C.plan(b, 3, MAIN, D[5])
        self.assertEqual(calls, [D[3], D[3], D[4]])          # stage 4, stage 7 (the consumed day), stage 7 (the re-applied day)


class Market(unittest.TestCase):
    """C1-09."""

    def test_the_rows_of_the_consumed_day_are_fixed_from_the_series(self):
        b = C.s_tail()                                            # DECLARE D2, no APPLY after it
        series = R.with_row(b.w, D[2], soxx=123.0, rsi=61.0)
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2])], D[5], series=series)
        items = plan.basis["series_inputs"]
        self.assertEqual([(i["from_seq"], i["d"]) for i in items], [(None, D[2])])
        item = items[0]
        self.assertEqual((item["prev_session_date"], item["series_previous_date"]), (D[1], D[1]))
        self.assertEqual((item["row"]["soxx"], item["row"]["rsi"]), (123.0, 61.0))
        self.assertEqual(item["prev_row"]["date"], D[1])
        made = plan.basis["candidate_records"][1]["confirmed_inputs"]
        self.assertEqual((made["row"], made["prev_row"], made["prev_session_date"]),
                         (item["row"], item["prev_row"], D[1]))

    def test_the_series_items_are_in_the_order_of_the_operations(self):
        b = C.s_gap()
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)], D[5])
        self.assertEqual([(i["from_seq"], i["d"]) for i in plan.basis["series_inputs"]],
                         [(None, D[2]), (None, D[3]), (3, D[4])])

    def test_a_previous_day_that_differs_between_the_series_and_the_sessions_is_refused(self):
        b = C.s_declare()
        series = P.make_series(dates=[d for d in D if d != D[2]])
        e = C.err(C.plan, b, 3, MAIN, D[5], series=series)
        self.assertEqual(e[:2], ("session_series_mismatch", "market"))

    def test_a_row_that_cannot_be_read_is_a_core_error(self):
        b = C.s_declare()
        e = C.err(C.plan, b, 3, MAIN, D[5], series=P.make_series(dates=[d for d in D if d != D[3]]))
        self.assertEqual(e[:2], ("target_row_missing", "market"))

    def test_a_series_that_does_not_answer_in_the_expected_form_is_a_fixed_error(self):
        class Broken(object):
            def through(self, d):
                return self

            def row(self, d):
                return object()

            def previous_date(self, d):
                return D[2]
        e = C.err(C.plan, C.s_declare(), 3, MAIN, D[5], series=Broken())
        self.assertEqual(e, ("restore_invalid", "series", "market_input", None))

    def test_a_previous_row_that_cannot_be_read_is_null_as_in_the_core(self):
        b = C.s_tail()

        class NoRow(object):
            """The series of the world, but the row of one date cannot be read."""

            def __init__(self, base, missing):
                self.base, self.missing = base, missing

            def through(self, d):
                return NoRow(self.base.through(d), self.missing)

            def row(self, d):
                if d == self.missing:
                    raise C.T.InputError("insufficient_history", "market")
                return self.base.row(d)

            def __getattr__(self, name):
                return getattr(self.base, name)
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2])], D[5], series=NoRow(b.w.series, D[1]))
        self.assertIsNone(plan.basis["series_inputs"][0]["prev_row"])
        self.assertIsNone(plan.basis["candidate_records"][1]["confirmed_inputs"]["prev_row"])

    def test_the_day_must_have_a_next_and_a_previous_session(self):
        b = C.s_declare()
        sessions = C.P.make_sessions(dates=[d for d in D if d != D[2]])
        e = C.err(C.plan, b, 3, MAIN, D[5], sessions=sessions)
        self.assertIn(e[0], ("session_context_mismatch", "session_context_missing", "session_series_mismatch"))

    def test_a_row_changed_after_the_plan_makes_the_confirmation_stale(self):
        b = C.s_tail()
        entries = [("DROP", 2), (CONSUME, D[2])]
        plan = C.plan(b, 1, entries, D[5])
        series = R.with_row(b.w, D[2], soxx=101.0)
        e = C.err(R.confirm, plan, b.history(), b.w, series=series)
        self.assertEqual(e[0], "history_plan_stale")
        self.assertEqual(R.confirm(plan, b.history(), b.w).status, "CONFIRMED_IN_MEMORY")


class Order(unittest.TestCase):
    """C1-10: the priority of the errors and of the stages."""

    def test_the_stages_run_in_the_fixed_order_and_evaluate_day_comes_last(self):
        b = C.s_declare()
        order = []

        def wrap(name):
            real = getattr(build, name)

            def inner(*a, **k):
                order.append(name)
                return real(*a, **k)
            return inner
        names = ("series_inputs", "_consume_inputs", "plan_records", "_check_consumed_released", "_check_candidate",
                 "_replay_evidence", "_prior_rows", "_check_consumed_decisions", "_check_new_days",
                 "_check_saved_decisions", "_check_saved_market", "project_history_ledger", "evaluate_day")
        patches = [mock.patch.object(build, n, side_effect=wrap(n)) for n in names]
        for p in patches:
            p.start()
        try:
            C.plan(b, 3, MAIN, D[5])
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(order, ["series_inputs", "_consume_inputs", "plan_records", "_check_consumed_released",
                                 "_check_candidate", "_replay_evidence", "_prior_rows", "_check_consumed_decisions",
                                 "_check_new_days", "_check_saved_decisions", "_check_saved_market",
                                 "project_history_ledger", "evaluate_day", "evaluate_day"])

    def test_evaluate_day_is_called_once_for_every_reapplied_and_consumed_day_after_the_projection(self):
        b = C.s_gap()
        entries = [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)]
        with mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day, \
                mock.patch.object(build, "project_history_ledger", wraps=build.project_history_ledger) as proj:
            C.plan(b, 1, entries, D[5])
        self.assertEqual(day.call_count, 3)
        self.assertEqual([c.args[1] for c in day.call_args_list], [D[2], D[3], D[4]])
        self.assertEqual(proj.call_count, 1)
        # and not at all when an earlier stage refuses
        with mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day:
            C.err(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3)], D[5])
        self.assertEqual(day.call_count, 0)

    def test_the_form_comes_before_the_id_and_the_id_before_the_decision(self):
        b = R.ex_declare_between()                               # no decision of D3
        bad_form = [{"op": "DROP", "from_seq": 4}, {"op": CONSUME, "d": "x"}, {"op": "REAPPLY", "from_seq": 5}]
        e = C.err(R.prep, b, 3, None, D[5], "bad id!", ops=bad_form)
        self.assertEqual(e, invalid("ops_shape"))
        e = C.err(R.prep, b, 3, None, D[5], "bad id!", ops=C.ops_of(MAIN))
        self.assertEqual(e[:3], ("restore_invalid", "request_id", "request_id"))
        e = C.err(C.plan, b, 3, MAIN, D[5])
        self.assertEqual(e, invalid("restore_consume_no_decision", D[3]))

    def test_the_form_rules_of_the_consume_come_before_the_ledger_is_looked_at(self):
        b = R.ex_declare_between()                               # no decision of D3: the rules of place go first
        applied = [("DROP", 4), (CONSUME, D[4]), ("REAPPLY", 5)]
        self.assertEqual(C.err(C.plan, b, 3, applied, D[5]), invalid("restore_consume_applied_day", D[4]))
        twice = [("DROP", 4), (CONSUME, D[3]), (CONSUME, D[3]), ("REAPPLY", 5)]
        self.assertEqual(C.err(C.plan, b, 3, twice, D[5]), invalid("restore_consume_duplicate", D[3]))

    def test_a_consume_inside_a_batch_is_refused_before_the_ledger_is_looked_at(self):
        b = C.R.ex_two_command_request()
        entries = [("DROP", 3), (CONSUME, D[3]), ("DROP", 4), ("DROP", 5)]
        self.assertEqual(C.err(C.plan, b, 2, entries, D[5]), invalid("restore_consume_in_batch", D[3]))
        entries = [("REPLAY", 3), (CONSUME, D[3]), ("REPLAY", 4), ("DROP", 5)]
        self.assertEqual(C.err(C.plan, b, 2, entries, D[5]), invalid("restore_consume_in_batch", D[3]))

    def test_the_mistakes_of_the_operations_come_before_those_of_the_consume(self):
        b = C.s_declare()
        e = C.err(C.plan, b, 3, [("DROP", 4), (CONSUME, D[4]), ("REAPPLY", 9)], D[5])
        self.assertEqual(e, invalid("superseded_mismatch"))
        e = C.err(C.plan, b, 3, [("REAPPLY", 4), (CONSUME, D[4]), ("REAPPLY", 5)], D[5])
        self.assertEqual(e, invalid("restore_op_kind"))

    def test_the_place_and_the_missing_decision_come_before_the_freed_days(self):
        b = C.s_declare()
        # D3 is not freed (the declaration is kept) and there is no decision of D6: the decision is looked for first
        e = C.err(C.plan, b, 3, [("REPLAY", 4), (CONSUME, D[6]), ("REAPPLY", 5)], D[8])
        self.assertEqual(e, invalid("restore_consume_no_decision", D[6]))
        e = C.err(C.plan, b, 3, [("REPLAY", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
        self.assertEqual(e, invalid("restore_consume_not_released", D[3]))

    def test_the_freed_days_come_before_the_check_of_the_candidate(self):
        # the same input is refused by the chain view when it is written by hand (declare_applied), see test_c1_01
        b = C.s_declare()
        e = C.err(C.plan, b, 3, [("REPLAY", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
        self.assertEqual(e[2], "restore_consume_not_released")


class Shown(unittest.TestCase):
    """C1-11."""

    def test_the_change_rows(self):
        b = C.s_declare()
        plan = C.plan(b, 3, MAIN, D[5])
        changes = plan.basis["changes"]
        self.assertEqual(changes[1], {"op": CONSUME, "from_seq": None, "kind": "APPLY", "d": D[3],
                                      "to_seq": len(b.events) + 1, "same_as_superseded": None, "changed_fields": []})
        self.assertEqual(changes[2]["op"], "REAPPLY")
        self.assertIs(changes[2]["same_as_superseded"], False)
        self.assertEqual(changes[2]["changed_fields"], ["input_hash", "skipped_sessions", "state_after",
                                                        "transition_result"])
        self.assertEqual(len(changes), len(plan.basis["ops"]))

    def test_the_summary_and_the_repr_show_no_value(self):
        b = C.s_declare()
        plan = C.plan(b, 3, MAIN, D[5])
        shown = plan.summary()
        self.assertEqual(shown["ops"][1], {"op": CONSUME, "from_seq": None, "kind": "APPLY", "d": D[3],
                                           "to_seq": len(b.events) + 1, "same_as_superseded": None, "changed_fields": []})
        text = repr(shown) + repr(plan) + str(plan.summary())
        for word in ("X3", "45.0", "soxx", "sma", "rsi", "fear", "record_id", "observed_at", "decision"):
            self.assertNotIn(word, text)
        self.assertFalse(plan.committed)
        self.assertFalse(shown["committed"] or shown["committable"])

    def test_a_row_of_the_wrong_form_is_not_shown(self):
        b = C.s_declare()
        plan = C.plan(b, 3, MAIN, D[5])

        def bad(basis):
            basis["changes"][1]["from_seq"] = 5
        forged = R.refreshed(plan, bad)
        with self.assertRaises(Exception) as cm:
            forged.summary()
        self.assertEqual((cm.exception.code, cm.exception.rule), ("restore_invalid", "plan_shape"))
        self.assertEqual(repr(forged), "RestorePlan(?)")


class NoEffect(unittest.TestCase):
    """C1-12."""

    def test_a_plan_without_a_drop_and_a_consume_whose_days_are_all_the_same_is_no_effect(self):
        b = R.ex_restart_over_gap()
        mapping = {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}
        self.assertEqual(C.err(R.prep, b, 0, mapping, D[5], "c1-1")[0], "restore_no_effect")

    def test_a_consume_is_never_a_plan_without_effect(self):
        b, s, sessions, series = C.s_calendar()
        plan = C.plan(b, 1, [(CONSUME, s), ("REAPPLY", 2)], D[13], sessions=sessions, series=series)
        self.assertEqual(plan.status, "READY")
        # a day consumed in front of a re-applied day always changes it: no plan with a CONSUME can have only same days
        self.assertIs(plan.basis["changes"][1]["same_as_superseded"], False)

    def test_a_drop_alone_is_still_an_effect(self):
        b = R.ex_restart_between()
        self.assertEqual(R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "c1-1").status, "READY")


if __name__ == "__main__":
    unittest.main()
