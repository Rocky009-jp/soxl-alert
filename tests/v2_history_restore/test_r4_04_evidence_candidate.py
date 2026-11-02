"""B4-11 (the evidence of the replayed requests and the two known limits of design 7.1) and B4-12 (the complete candidate)."""
import types
import unittest
from unittest import mock

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O
import v2_history_restore.build as build  # noqa: E402
from v2_history.values import ACK, DECLARE_MISSING  # noqa: E402


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


class ReplayEvidence(unittest.TestCase):
    def test_every_replayed_request_group_is_checked_by_the_unchanged_check_commands(self):
        b = R.ex_two_command_request()
        with mock.patch.object(build, "check_commands", wraps=build.check_commands) as spy:
            plan = R.prep(b, 2, {3: "REPLAY", 4: "REPLAY", 5: "DROP"}, D[5], "r4-1")
        self.assertEqual(plan.status, "READY")
        self.assertEqual(spy.call_count, 1)                                           # one request: one group, not two calls
        commands = spy.call_args[0][2]
        self.assertEqual([(c["kind"], c["variant"], c["d"]) for c in commands],
                         [("ACK", "ADDED", D[1]), ("ACK", "ADDED", D[2])])

    def test_a_request_that_is_not_replayed_is_not_checked_again(self):
        b = R.ex_restart_over_gap()
        with mock.patch.object(build, "check_commands", wraps=build.check_commands) as spy:
            R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[5], "r4-1")
        self.assertEqual(spy.call_count, 0)
        b = R.ex_inside_old_batch()
        with mock.patch.object(build, "check_commands", wraps=build.check_commands) as spy:
            R.prep(b, 8, {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, D[8], "r4-1")
        self.assertEqual(spy.call_count, 1)

    def test_the_prefix_holds_neither_a_later_apply_nor_a_later_resolution(self):
        b = R.ex_two_command_request()
        seen = []
        real = build.facts_of

        def spy(records, head_seq):
            seen.append(([r["seq"] for r in records], head_seq))
            return real(records, head_seq)

        with mock.patch.object(build, "facts_of", side_effect=spy):
            R.prep(b, 2, {3: "REPLAY", 4: "REPLAY", 5: "DROP"}, D[5], "r4-1")
        # the facts of the group's own prefix (everything before its first record) and of the whole candidate
        chain_before_group = [0, 1, 2]
        self.assertIn((chain_before_group, 2), [(s, h) for s, h in seen if h == 2 and len(s) == 3])
        for records, head in seen:
            self.assertEqual(records[-1], head)
        group_prefix = [s for s, h in seen if h == 2][0]
        self.assertEqual(group_prefix, [0, 1, 2])                                     # no created ACK, no later record

    def test_a_row_and_a_removal_of_one_request_are_checked_as_a_whole(self):
        b = H.HB()
        b.apply(D[1], 27.0, "R1")
        added = P.obs("N1", D[1], 33.0, hour=21)
        b.resolution([{"kind": "ACK", "variant": "ROW_REMOVED", "d": D[1], "fps": [], "applied": 1},
                      {"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [H.fp(added)], "applied": 1}], "q1")
        b.w.ledger[:] = [added]
        b.extra_rows = [added]
        b.restart(D[1], "q2")
        mapping = {2: "REPLAY", 3: "REPLAY", 4: "DROP"}
        plan, res = R.run(b, 1, mapping, D[5], "r4-1")
        self.assertEqual(R.cj(res.history.events[len(b.events):]),
                         R.cj(R.oracle(b, 1, mapping, "r4-1", D[5])[len(b.events):]))
        self.assertEqual([c["op"] for c in plan.basis["changes"]], ["REPLAY", "REPLAY", "DROP"])
        # either command alone is a partial request
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "DROP", 4: "DROP"}, D[5], "r4-1"),
                         ("restore_invalid", "ops", "restore_partial_batch", None))

    def test_the_known_limit_a_declaration_and_its_late_acknowledgement_are_refused_together(self):
        b, late = R.ex_declare_then_late()
        self.assertEqual(b.check().head_seq, 4)                                        # the original history is healthy
        ledger = R.O.project_history_ledger(b.history(), b.w.sessions, b.w.ledger, D[5])
        self.assertEqual(len(ledger.rows), len(b.w.ledger) - 1)                         # and the original projection works
        expected = ("resolution_invalid", "commands", "declare_valid_decision", None)
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY"}, D[5], "r4-1"), expected)
        # the declaration alone is also refused: the late row is in the ledger at the time the declaration is checked
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY", 4: "DROP"}, D[5], "r4-1"), expected)

    def test_the_known_limit_a_removal_and_a_later_change_are_refused_together(self):
        b, changed = R.ex_removed_then_changed()
        self.assertEqual(b.check().head_seq, 3)
        ledger = R.O.project_history_ledger(b.history(), b.w.sessions, b.w.ledger, D[5])
        self.assertEqual(len(ledger.rows), 1)                                      # the stored R1 is supplemented
        expected = ("resolution_invalid", "commands", "ack_evidence", None)
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REPLAY"}, D[5], "r4-1"), expected)
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "DROP"}, D[5], "r4-1"), expected)

    def test_keeping_the_whole_group_and_dropping_a_later_restart_succeeds(self):
        b = R.ex_late_ack_tail()
        self.assertEqual(b.check().head_seq, 5)
        plan, res = R.run(b, 4, {5: "DROP"}, D[5], "r4-1")                             # P is the last record of the group
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        events = res.history.events
        self.assertEqual([e["kind"] for e in events[len(b.events):]], ["RECOVERY_RESTORE"])
        self.assertEqual(events[-1]["superseded_seqs"], [5])
        self.assertEqual(R.cj(events[len(b.events):]), R.cj(R.oracle(b, 4, {5: "DROP"}, "r4-1", D[5])[len(b.events):]))
        ledger = R.O.project_history_ledger(res.history, b.w.sessions, b.w.ledger, D[5])
        self.assertEqual(len(ledger.rows), len(b.w.ledger) - 1)                          # the late row stays excluded

    def test_a_version_choice_stays_refused(self):
        # ROW_REMOVED and then CHANGED: dropping only the removal would leave two versions of the record
        b = R.ex_removed_then_changed()[0]
        self.assertEqual(err(R.prep, b, 2, {3: "REPLAY"}, D[5], "r4-1")[0], "restore_no_effect")


class CompleteCandidate(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_ack_between()
        self.map = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        self.plan, self.res = R.run(self.b, 1, self.map, D[5], "r4-1")
        self.new = self.res.history.events[len(self.b.events):]

    def test_the_old_events_stay_and_the_new_ones_follow(self):
        events = self.res.history.events
        self.assertEqual(R.cj(events[:len(self.b.events)]), R.cj(self.b.events))
        self.assertEqual([e["seq"] for e in self.new], [6, 7, 8, 9])
        self.assertEqual([e["kind"] for e in self.new], ["RECOVERY_RESTORE", "APPLY", "ACK", "APPLY"])

    def test_the_restore_record_has_its_fifteen_keys_and_its_audit_links(self):
        rec = self.new[0]
        self.assertEqual(sorted(rec), sorted(["kind", "seq", "prev_hash", "parent_seq", "parent_hash", "superseded_seqs",
                                              "replay", "request_id", "request_hash", "request_basis", "reason_code",
                                              "requested_at", "ledger_digest", "state_after", "event_hash"]))
        self.assertEqual(rec["prev_hash"], self.b.events[-1]["event_hash"])             # the physical previous record
        self.assertEqual((rec["parent_seq"], rec["parent_hash"]), (1, self.b.events[1]["event_hash"]))
        self.assertEqual(rec["superseded_seqs"], [2, 3, 4, 5])
        self.assertEqual(sorted(rec["request_basis"]), sorted(["request_id", "restore_point", "ops", "check_d",
                                                               "reason_code", "requested_at"]))
        self.assertEqual(R.cj(rec["state_after"]), R.cj(self.b.events[1]["state_after"]))
        for entry in rec["replay"]:
            self.assertEqual(sorted(entry), sorted(["op", "from_seq", "d", "seq", "same_as_superseded"]))
        self.assertEqual([(e["op"], e["from_seq"], e["seq"]) for e in rec["replay"]],
                         [("DROP", 2, None), ("REAPPLY", 3, 7), ("REPLAY", 4, 8), ("REAPPLY", 5, 9)])
        # the created records are chained after the restore record, each on the record before it
        self.assertEqual([(e["parent_seq"], e["parent_hash"]) for e in self.new[1:]],
                         [(6, self.new[0]["event_hash"]), (7, self.new[1]["event_hash"]), (8, self.new[2]["event_hash"])])

    def test_the_effective_and_the_superseded_columns_and_the_new_header(self):
        check = V.validate_history(self.res.history)
        self.assertEqual(list(check.effective_seqs), [0, 1, 6, 7, 8, 9])
        self.assertEqual(list(check.superseded_seqs), [2, 3, 4, 5])
        self.assertEqual(check.head_seq, 9)
        self.assertEqual(self.res.history.current_state, self.new[-1]["state_after"])
        self.assertEqual(self.res.history.digest, self.plan.basis["candidate_digest"])
        self.assertEqual(check.state_digest, self.plan.basis["candidate_state_digest"])

    def test_a_candidate_inside_an_old_batch_is_a_valid_history(self):
        b = R.ex_inside_old_batch()
        plan, res = R.run(b, 8, {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, D[8], "r4-1")
        check = V.validate_history(res.history)
        self.assertEqual(list(check.effective_seqs), [0, 1, 2, 7, 8, 14, 15, 16, 17, 18])
        self.assertEqual(list(check.superseded_seqs), [3, 4, 5, 6, 9, 10, 11, 12, 13])

    def test_a_batch_that_stops_in_the_middle_is_refused_by_validate_history(self):
        # a candidate whose last created record is missing is not a history: the plan carrying it is refused at confirm
        def cut(events, n):
            del events[-1]

        forged = R.forge(self.plan, cut)
        self.assertEqual(err(R.confirm, forged, self.b.history(), self.b.w)[:2], ("history_plan_mismatch", "plan"))
        history = R.H.rebuild(R.deep(self.res.history.events)[:-1], remap=True)
        e = R.refusal(V.validate_history, history)
        self.assertEqual((e.code, e.field), ("history_invalid", "history"))

    def test_the_projection_of_the_whole_candidate_is_really_called_and_must_agree_with_the_prior_rows(self):
        b = self.b
        with mock.patch.object(build, "project_history_ledger", wraps=build.project_history_ledger) as spy:
            R.prep(b, 1, self.map, D[5], "r4-1")
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(len(spy.call_args[0][0].events), len(b.events) + 4)             # the candidate, over the whole range
        real = build.project_history_ledger

        def other_rows(*args, **kwargs):
            ledger = real(*args, **kwargs)
            return types.SimpleNamespace(rows=ledger.rows[:-1], effective_digest=ledger.effective_digest,
                                         ledger_digest=ledger.ledger_digest, raw_observations=ledger.raw_observations)

        with mock.patch.object(build, "project_history_ledger", side_effect=other_rows):
            self.assertEqual(err(R.prep, b, 1, self.map, D[5], "r4-1"), ("history_invalid", "history", "restore_candidate", None))

    def test_a_candidate_that_differs_from_what_was_built_is_refused(self):
        real = build.validate_history
        calls = []

        def second_answer_differs(history):
            check = real(history)
            calls.append(check)
            if len(calls) == 2:                                                        # the candidate (the first is the history)
                return _with(check, effective_seqs=check.effective_seqs[:-1])
            return check

        with mock.patch.object(build, "validate_history", side_effect=second_answer_differs):
            self.assertEqual(err(R.prep, self.b, 1, self.map, D[5], "r4-1"),
                             ("history_invalid", "history", "restore_candidate", None))


def _with(check, **changes):
    values = {k: getattr(check, k) for k in dir(check) if not k.startswith("_") and not callable(getattr(check, k))}
    values.update(changes)
    return types.SimpleNamespace(**values)


if __name__ == "__main__":
    unittest.main()
