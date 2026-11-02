"""B4-19: the minimum acceptance examples of design 13 run with real ledgers and series, the successes and the expected
refusals kept apart, and a normal candidate handed to the existing B-2 day preparation."""
import unittest

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


class Examples(unittest.TestCase):
    def test_example_1_a_restart_written_too_early_is_dropped_and_the_next_day_is_calculated_again(self):
        b = R.ex_restart_between()
        mapping = {2: "DROP", 3: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[3], "r4-review-1")
        self.assertEqual(plan.status, "READY")
        events = res.history.events
        self.assertEqual(R.cj(events[:len(b.events)]), R.cj(b.events))               # the physical list is kept
        self.assertEqual(R.cj(events), R.cj(R.oracle(b, 1, mapping, "r4-review-1", D[3])))
        new, old = events[5], b.events[3]
        changed = sorted(k for k in ("input_hash", "skipped_sessions", "transition_result", "state_after")
                         if R.cj(new[k]) != R.cj(old[k]))
        self.assertEqual(changed, ["state_after", "transition_result"])
        self.assertEqual(plan.basis["changes"][1]["changed_fields"], changed)
        self.assertEqual(plan.basis["changes"][1]["same_as_superseded"], False)

    def test_example_2_a_gap_without_decisions_is_restorable_and_a_decision_in_it_needs_a_consumption(self):
        for builder, seq, mapping in ((R.ex_restart_over_gap, 1, {2: "DROP", 3: "REAPPLY"}),
                                      (R.ex_null_restart, 0, {1: "DROP"})):
            b = builder()
            self.assertEqual(R.prep(b, seq, mapping, D[5], "r4-review-1").status, "READY")
            for d in (D[2], D[3]):
                ledger = b.w.ledger + [P.obs("X" + d, d, 45.0)]
                self.assertEqual(err(R.prep, b, seq, mapping, D[5], "r4-review-1", ledger=ledger),
                                 ("restore_requires_consume", "ops", None, d))

    def test_example_3_a_last_declaration_whose_day_gets_a_decision_back_needs_a_consumption(self):
        b = R.ex_declare_tail()
        ledger = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, {2: "DROP"}, D[5], "r4-review-1", ledger=ledger),
                         ("restore_requires_consume", "ops", None, D[2]))

    def test_example_4_the_upper_examples_with_real_ledgers_and_series(self):
        # R-b: the declaration replayed on a changed parent state
        b = R.ex_declare_between()
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[5], "r4-review-1")
        self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(b, 1, mapping, "r4-review-1", D[5])))
        self.assertEqual([e["request_id"] for e in res.history.events[len(b.events):] if "request_id" in e],
                         ["r4-review-1", "q2"])                                     # the original id of the declaration is kept
        # R: a restore at the end of the three restores of design 8.9, and one that retires the first of them
        b = R.ex_after_three_restores()
        mapping = {24: "DROP", 25: "REAPPLY"}
        plan, res = R.run(b, 23, mapping, D[9], "r4-review-1")
        self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(b, 23, mapping, "r4-review-1", D[9])))
        effective = list(V.validate_history(res.history).effective_seqs)
        self.assertEqual(effective[:9], [0, 1, 2, 18, 19, 20, 21, 22, 23])
        self.assertEqual(len(effective), 9 + 1 + 1)                                  # + the new restore and its APPLY D12
        retire = {18: "RETIRE", 19: "REAPPLY", 20: "REAPPLY", 21: "REAPPLY", 22: "REAPPLY", 23: "REAPPLY", 24: "DROP",
                  25: "REAPPLY"}
        plan, res = R.run(b, 2, retire, D[9], "r4-review-1")
        self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(b, 2, retire, "r4-review-1", D[9])))
        self.assertEqual(plan.basis["changes"][0]["op"], "RETIRE")
        self.assertEqual(plan.basis["changes"][0]["kind"], "RECOVERY_RESTORE")
        self.assertTrue(all(c["same_as_superseded"] in (True, False) for c in plan.basis["changes"] if c["op"] == "REAPPLY"))
        # the same-or-not flag depends on the inputs: another market row of a re-applied day stops the plan instead
        series = R.with_row(b.w, D[5], rsi=61.0)
        self.assertEqual(err(R.prep, b, 2, retire, D[9], "r4-review-1", series=series)[:2],
                         ("restore_market_input_changed", "series"))

    def test_example_5_a_point_inside_an_old_batch_is_valid(self):
        b = R.ex_inside_old_batch()
        mapping = {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}
        plan, res = R.run(b, 8, mapping, D[8], "r4-review-1")
        self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(b, 8, mapping, "r4-review-1", D[8])))
        # the physical prefix cut at the point is not a history of its own
        e = R.refusal(V.validate_history, H.rebuild(R.deep(b.events)[:9], remap=True))
        self.assertEqual((e.code, e.field), ("history_invalid", "history"))
        self.assertEqual(plan.basis["restore_point"]["seq"], 8)

    def test_example_6_no_drop_and_no_change_is_refused_and_a_plan_with_a_drop_is_reconfirmed_without_a_second_record(self):
        b = R.ex_restart_over_gap()
        self.assertEqual(err(R.prep, b, 0, {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}, D[5], "r4-review-9"),
                         ("restore_no_effect", "ops", None, None))
        plan, res = R.run(b, 1, {2: "DROP", 3: "REAPPLY"}, D[5], "r4-review-1")
        again = R.confirm(plan, res.history, b.w)
        self.assertEqual(again.status, "NO_CHANGE")
        self.assertEqual(len(again.history.events), len(res.history.events))

    def test_example_7_a_context_shift_of_a_dropped_declaration_does_not_stop_the_restore(self):
        b = R.ex_declare_tail()
        sessions = R.sessions_with({D[3]: R.later_open})
        self.assertEqual(err(O.project_history_ledger, b.history(), sessions, b.w.ledger, D[5])[:2],
                         ("session_context_mismatch", "sessions"))
        plan = R.prep(b, 1, {2: "DROP"}, D[5], "r4-review-1", sessions=sessions)
        res = R.confirm(plan, b.history(), b.w, sessions=sessions)
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(len(O.project_history_ledger(res.history, sessions, b.w.ledger, D[5]).rows), len(b.w.ledger))
        # a day that the candidate's own APPLY still uses is not a success: the shift stays in the candidate
        b2 = R.ex_declare_between()
        shifted = R.sessions_with({D[4]: R.later_open})
        self.assertEqual(err(O.project_history_ledger, b2.history(), shifted, b2.w.ledger, D[6])[:2],
                         ("session_context_mismatch", "sessions"))
        self.assertEqual(err(R.prep, b2, 3, {4: "DROP", 5: "REAPPLY"}, D[6], "r4-review-1", sessions=shifted)[:2],
                         ("session_context_mismatch", "sessions"))
        # a restart whose saved boundary differs from the current session: dropping it is a success, replaying is not
        b3 = R.ex_restart_tail()
        moved = R.sessions_with({D[3]: R.earlier_close})
        self.assertEqual(err(O.project_history_ledger, b3.history(), moved, b3.w.ledger, D[6])[:2],
                         ("session_context_mismatch", "sessions"))
        self.assertEqual(R.prep(b3, 1, {2: "DROP"}, D[6], "r4-review-1", sessions=moved).status, "READY")
        self.assertEqual(err(R.prep, b3, 1, {2: "REPLAY"}, D[6], "r4-review-1", sessions=moved)[:2],
                         ("session_context_mismatch", "sessions"))
        # and the declaration's dropped day with a decision is never turned into a success
        late = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, {2: "DROP"}, D[5], "r4-review-1", sessions=sessions, ledger=late)[:2],
                         ("restore_requires_consume", "ops"))

    def test_example_8_the_two_known_limits_are_refused_although_the_originals_are_healthy(self):
        b, _late = R.ex_declare_then_late()
        self.assertEqual(R.O.project_history_ledger(b.history(), b.w.sessions, b.w.ledger, D[5]).check_d, D[5])
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY"}, D[5], "r4-review-1")[:3],
                         ("resolution_invalid", "commands", "declare_valid_decision"))
        b, _changed = R.ex_removed_then_changed()
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REPLAY"}, D[5], "r4-review-1")[:3],
                         ("resolution_invalid", "commands", "ack_evidence"))

    def test_example_9_keeping_the_group_and_dropping_a_later_restart_succeeds(self):
        b = R.ex_late_ack_tail()
        plan, res = R.run(b, 4, {5: "DROP"}, D[5], "r4-review-1")
        self.assertEqual([c["op"] for c in plan.basis["changes"]], ["DROP"])
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(list(V.validate_history(res.history).effective_seqs), [0, 1, 2, 3, 4, 6])
        # this is not a replacement for undoing a restart that lies before the group: P at the group's start is the
        # case that is refused (the late row comes back with a declaration that is checked first)
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY", 5: "DROP"}, D[5], "r4-review-1")[:3],
                         ("resolution_invalid", "commands", "declare_valid_decision"))


class HandedToTheDailyPreparation(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()
        self.w = self.b.w
        self.plan, self.res = R.run(self.b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "r4-1")
        self.cand = self.res.history

    def day(self, history, d, ledger):
        return O.prepare_history_day(history, d, self.w.series, self.w.sessions, ledger)

    def test_the_applied_day_is_already_applied_and_a_new_day_is_prepared_from_the_candidates_head(self):
        self.assertEqual(self.day(self.cand, D[2], self.w.ledger).status, "ALREADY_APPLIED")
        ledger = self.w.ledger + [P.obs("R-" + D[4], D[4], 31.0)]
        res = self.day(self.cand, D[4], ledger)
        self.assertEqual(res.status, "PREPARED")
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["parent_seq"], rec["parent_hash"]), (self.cand.head_seq, self.cand.head_hash))
        self.assertEqual(rec["skipped_sessions"], [D[3]])

    def test_a_late_decision_for_a_skipped_day_stops_the_next_day(self):
        ledger = self.w.ledger + [P.obs("R-" + D[4], D[4], 31.0)]
        cand2 = O.check_append_batch(self.cand, self.day(self.cand, D[4], ledger).batch)
        late = ledger + [P.obs("L3", D[3], 33.0)]
        e = R.refusal(self.day, cand2, D[5], late)
        self.assertEqual((e.code, e.field, e.detail), ("late_observation", "observations", D[3]))
        self.assertEqual(self.day(cand2, D[4], ledger).status, "ALREADY_APPLIED")


if __name__ == "__main__":
    unittest.main()
