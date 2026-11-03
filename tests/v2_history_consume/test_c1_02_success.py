"""C1-04 (the examples of design 3.10), C1-05 (the expected values are made on the test side) and C1-06 (the three kinds
of freed day that can be consumed, and the days that cannot)."""
import unittest

import c1_helpers as C
from v2_core.engine import evaluate_day
from v2_core.state import MarketState
from v2_persistence.events import serialize_transition

H, P, R, V, D, O = C.H, C.P, C.R, C.V, C.D, C.O
CONSUME = C.CONSUME
rule = C.invalid


def check_example(case, b, point, entries, check, rid="c1-1", reveal=(), **kw):
    """READY -> CONFIRMED_IN_MEMORY -> NO_CHANGE on the candidate; the candidate is the one the independent builder
    writes, passes validate_history and projects through the unchanged B-2 function. Returns (plan, result)."""
    plan = C.plan(b, point, entries, check, rid, **kw)
    case.assertEqual(plan.status, "READY")
    conf = {k: kw[k] for k in ("sessions", "ledger", "series") if k in kw}
    res = R.confirm(plan, b.history(), b.w, **conf)
    case.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
    n = len(b.events)
    expected = C.oracle(b, point, entries, rid, check, ledger=kw.get("ledger"), sessions=kw.get("sessions"),
                        series=kw.get("series"), reveal=reveal)
    case.assertEqual(C.cj(res.history.events[n:]), C.cj(expected[n:]))
    V.validate_history(res.history)
    sessions = kw.get("sessions") or b.w.sessions
    ledger = kw.get("ledger") or b.w.ledger
    O.project_history_ledger(res.history, sessions, ledger, check)
    again = R.confirm(plan, res.history, b.w, **conf)
    case.assertEqual(again.status, "NO_CHANGE")
    case.assertEqual(again.history, res.history)
    return plan, res


class Examples(unittest.TestCase):
    """Design 3.10."""

    def test_a_declaration_between_two_applies(self):
        b = C.s_declare()
        plan, res = check_example(self, b, 3, [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
        changes = plan.basis["changes"]
        self.assertEqual([(c["op"], c["d"], c["same_as_superseded"]) for c in changes],
                         [("DROP", D[3], None), (CONSUME, D[3], None), ("REAPPLY", D[4], False)])
        new = C.new_records(b, res.history)
        self.assertEqual([e["kind"] for e in new], ["RECOVERY_RESTORE", "APPLY", "APPLY"])
        self.assertEqual(new[2]["skipped_sessions"], [])                  # D4 no longer passes over D3

    def test_a_restart_over_a_gap_consumes_both_days(self):
        b = C.s_gap()
        plan, res = check_example(self, b, 1, [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)], D[5])
        new = C.new_records(b, res.history)
        self.assertEqual([e["d"] for e in new[1:]], [D[2], D[3], D[4]])
        self.assertEqual([e["skipped_sessions"] for e in new[1:]], [[], [], []])

    def test_a_declaration_with_a_late_acknowledgement(self):
        b, late = C.s_late()
        plan, res = check_example(self, b, 1, [("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3), ("DROP", 4)], D[5],
                                  reveal=("L2",))                       # the late row comes back with the LATE ACK dropped
        made = C.new_records(b, res.history)[1]
        self.assertEqual((made["d"], made["confirmed_inputs"]["decision"]["record_id"]), (D[2], "L2"))

    def test_a_declaration_without_a_later_apply(self):
        b = C.s_tail()
        check_example(self, b, 1, [("DROP", 2), (CONSUME, D[2])], D[5])

    def test_a_restart_whose_segment_has_no_apply(self):
        b = C.s_null()
        plan, res = check_example(self, b, 0, [("DROP", 1), (CONSUME, D[1])], D[5])
        made = C.new_records(b, res.history)[1]
        self.assertEqual((made["d"], made["skipped_sessions"]), (D[1], []))


class Independence(unittest.TestCase):
    """C1-05: the confirmed inputs, the skipped sessions, the transition and the next state of a consumed day are made on the
    test side, from the S1 prepare_day (through HB.apply_content) and from evaluate_day, not from the runtime's output."""

    def parent_state(self, events, seq):
        return events[seq]["state_after"]

    def test_a_cancelled_declaration(self):
        b = C.s_declare()
        plan = C.plan(b, 3, [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
        made = plan.basis["candidate_records"][1]
        # S1: the day on the chain of the kept records up to the restore point
        kept = b.chain_recs(3)
        expected = b.apply_content(kept, D[3])
        for key in ("confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after"):
            self.assertEqual(C.cj(made[key]), C.cj(expected[key]), key)
        self.assertEqual(made["confirmed_inputs"]["decision"]["record_id"], "X3")
        self.assertEqual(made["confirmed_inputs"]["decision"]["current_fg_value"], 45.0)
        # the core: the same day through evaluate_day from the state of the restore point
        day = evaluate_day(MarketState.from_dict(b.events[3]["state_after"]), D[3], b.w.series.through(D[3]),
                           b.w.sessions, b.w.ledger)
        self.assertEqual(C.cj(serialize_transition(day)), C.cj(made["transition_result"]))
        self.assertEqual(C.cj(day.next_state.to_dict()), C.cj(made["state_after"]))

    def test_a_cancelled_restart(self):
        b = C.s_gap()
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)], D[5])
        first, second = plan.basis["candidate_records"][1:3]
        kept = b.chain_recs(1)
        expected2 = b.apply_content(kept, D[2])
        for key in ("confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after"):
            self.assertEqual(C.cj(first[key]), C.cj(expected2[key]), key)
        # the second day is calculated on the chain that holds the first
        expected3 = b.apply_content(kept + [dict(kind="APPLY", **expected2)], D[3])
        for key in ("confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after"):
            self.assertEqual(C.cj(second[key]), C.cj(expected3[key]), key)
        day = evaluate_day(MarketState.from_dict(first["state_after"]), D[3], b.w.series.through(D[3]), b.w.sessions,
                           b.w.ledger)
        self.assertEqual(C.cj(serialize_transition(day)), C.cj(second["transition_result"]))
        self.assertEqual(C.cj(day.next_state.to_dict()), C.cj(second["state_after"]))
        # the state moved: the consumed day is not a copy of the state it started from
        self.assertNotEqual(C.cj(first["state_after"]), C.cj(b.events[1]["state_after"]))


class FreedDays(unittest.TestCase):
    """C1-06: the days that can be consumed are the freed ones, of three kinds; the other days are refused."""

    def test_the_day_of_a_dropped_declaration(self):
        b = C.s_declare()
        self.assertEqual(C.plan(b, 3, [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5]).status, "READY")

    def test_the_sessions_a_dropped_restart_had_passed_over(self):
        b = C.s_gap()
        for entries in ([("DROP", 2), (CONSUME, D[2]), ("REAPPLY", 3)],                       # D3 has a decision: stop
                        [("DROP", 2), (CONSUME, D[3]), ("REAPPLY", 3)]):
            e = C.err(C.plan, b, 1, entries, D[5])
            self.assertEqual(e[0], "restore_requires_consume")                                # the other one is left
        self.assertEqual(C.plan(b, 1, [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)], D[5]).status,
                         "READY")

    def test_a_dropped_restart_whose_base_is_the_initial_state(self):
        b = C.s_null()
        self.assertEqual(C.plan(b, 0, [("DROP", 1), (CONSUME, D[1])], D[5]).status, "READY")

    def test_a_day_a_reapplied_apply_newly_passes_over(self):
        b, s, sessions, series = C.s_calendar()
        entries = [(CONSUME, s), ("REAPPLY", 2)]
        plan, res = check_example(self, b, 1, entries, D[13], sessions=sessions, series=series)
        changes = plan.basis["changes"]
        self.assertEqual([(c["op"], c["d"], c["same_as_superseded"]) for c in changes],
                         [(CONSUME, s, None), ("REAPPLY", D[11], False)])
        new = C.new_records(b, res.history)
        self.assertEqual(new[1]["skipped_sessions"], D[5:10])                               # D5..D9, then the new day S
        self.assertEqual(new[2]["skipped_sessions"], [D[10]])
        # without the new session the same day is not freed
        e = C.err(C.plan, b, 1, entries, D[13])
        self.assertEqual(e[0], "target_not_in_sessions")

    def test_the_day_a_replayed_declaration_keeps_is_not_freed(self):
        b = C.s_declare()
        self.assertEqual(C.err(C.plan, b, 3, [("REPLAY", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5]),
                         rule("restore_consume_not_released", D[3]))

    def test_a_day_outside_the_freed_range_is_not_freed(self):
        b = C.s_declare()
        b.w.ledger.append(C.P.obs("X6", D[6], 49.0))
        entries = [("DROP", 4), ("REAPPLY", 5), (CONSUME, D[6])]
        self.assertEqual(C.err(C.plan, b, 3, entries, D[8]), rule("restore_consume_not_released", D[6]))

    def test_a_day_after_a_restart_that_is_replayed_is_not_freed(self):
        b = C.s_gap()
        b.w.ledger.append(C.P.obs("X5", D[5], 50.0))
        # the restart (resume D3) is kept: D5 is no day the operations set free
        entries = [("REPLAY", 2), ("REAPPLY", 3), (CONSUME, D[5])]
        self.assertEqual(C.err(C.plan, b, 1, entries, D[7]), rule("restore_consume_not_released", D[5]))

    def test_a_day_before_the_base_or_the_base_itself_is_out_of_order(self):
        b = C.s_declare()
        for d in (D[2], D[1]):                                  # both have the decision of the kept APPLY
            self.assertEqual(C.err(C.plan, b, 3, [("DROP", 4), (CONSUME, d), ("REAPPLY", 5)], D[5]),
                             rule("restore_consume_order", d))

    def test_a_consume_in_front_of_an_earlier_reapplied_day_is_out_of_order_too(self):
        b = C.s_declare()
        b.w.ledger.append(C.P.obs("X6", D[6], 49.0))
        # D6 is consumed before D4 is applied again: the base of D4 would be D6
        e = C.err(C.plan, b, 3, [("DROP", 4), (CONSUME, D[6]), ("REAPPLY", 5)], D[8])
        self.assertEqual(e, rule("restore_consume_order", D[6]))


if __name__ == "__main__":
    unittest.main()
