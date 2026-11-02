"""B4-08 (the days a restore would have to consume are refused), B4-09 (references of replayed records) and B4-10 (replayed
records are recalculated, not copied)."""
import unittest
from unittest import mock

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O,
import v2_history_restore.build as build  # noqa: E402


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


CONSUME = lambda d: ("restore_requires_consume", "ops", None, d)  # noqa: E731
LATE = lambda d: ("late_observation", "observations", None, d)  # noqa: E731


class ConsumeStop(unittest.TestCase):
    def days_of(self, b, seq, mapping, check, ledger=None):
        """The days that the unchanged _check_new_days is given (the released days), whatever the result is."""
        with mock.patch.object(build, "_check_new_days", wraps=build._check_new_days) as spy:
            try:
                R.prep(b, seq, mapping, check, "r4-1", ledger=ledger)
            except Exception:
                pass
        return spy.call_args[0][2] if spy.call_args else None

    def test_a_dropped_declaration_frees_its_day(self):
        b = R.ex_declare_between()
        late = b.w.ledger + [P.obs("X3", D[3], 45.0)]
        mapping = {4: "DROP", 5: "REAPPLY"}
        self.assertEqual(err(R.prep, b, 3, mapping, D[5], "r4-1", ledger=late), CONSUME(D[3]))
        self.assertEqual(R.prep(b, 3, mapping, D[5], "r4-1").status, "READY")           # nothing on D3: not consumed
        self.assertEqual(self.days_of(b, 3, mapping, D[5]), [D[3]])

    def test_a_dropped_declaration_without_a_later_apply_is_checked_too(self):
        b = R.ex_declare_tail()
        late = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, {2: "DROP"}, D[5], "r4-1", ledger=late), CONSUME(D[2]))
        self.assertEqual(R.prep(b, 1, {2: "DROP"}, D[5], "r4-1").status, "READY")

    def test_a_dropped_restart_frees_the_passed_over_sessions_but_not_the_applied_day(self):
        b = R.ex_restart_over_gap()
        mapping = {2: "DROP", 3: "REAPPLY"}
        self.assertEqual(self.days_of(b, 1, mapping, D[5]), [D[2], D[3]])             # (frontier D1, resume D3]
        with_d2 = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=with_d2), CONSUME(D[2]))
        with_d3 = b.w.ledger + [P.obs("X3", D[3], 45.0)]
        self.assertEqual(err(R.prep, b, 1, mapping, D[5], "r4-1", ledger=with_d3), CONSUME(D[3]))
        # a row of the day after the resume day is not a released day: it is still a decision day of its own
        with_d5 = b.w.ledger + [P.obs("X5", D[5], 45.0)]
        self.assertEqual(R.prep(b, 1, mapping, D[5], "r4-1", ledger=with_d5).status, "READY")

    def test_a_dropped_restart_without_a_later_apply_is_checked_too(self):
        b = R.ex_restart_tail()
        with_d2 = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 1, {2: "DROP"}, D[5], "r4-1", ledger=with_d2), CONSUME(D[2]))
        self.assertEqual(R.prep(b, 1, {2: "DROP"}, D[5], "r4-1").status, "READY")
        after = b.w.ledger + [P.obs("X4", D[4], 45.0)]                              # after the resume day: not released
        self.assertEqual(R.prep(b, 1, {2: "DROP"}, D[5], "r4-1", ledger=after).status, "READY")

    def test_a_restart_with_a_null_base_is_checked_from_the_boundary(self):
        b = R.ex_null_restart()
        self.assertEqual(self.days_of(b, 0, {1: "DROP"}, D[5]), [D[1], D[2], D[3]])
        with_d2 = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        self.assertEqual(err(R.prep, b, 0, {1: "DROP"}, D[5], "r4-1", ledger=with_d2), CONSUME(D[2]))
        self.assertEqual(R.prep(b, 0, {1: "DROP"}, D[5], "r4-1").status, "READY")

    def test_a_replayed_restart_frees_nothing(self):
        b = R.ex_restart_over_gap()
        late = b.w.ledger + [P.obs("X2", D[2], 45.0)]
        # REPLAY keeps the restart (its passed-over D2 stays passed over), so the row on D2 is not a released day; the
        # candidate is then refused by the projection as a late row, which is a different refusal than the consumption
        days = self.days_of(b, 1, {2: "REPLAY", 3: "REAPPLY"}, D[5], ledger=late)
        self.assertEqual(days, [])
        self.assertEqual(err(R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY"}, D[5], "r4-1", ledger=late)[0], "restore_no_effect")

    def test_a_row_on_an_unrelated_day_is_not_consumed(self):
        b = R.ex_restart_over_gap()
        unrelated = b.w.ledger + [P.obs("X6", D[6], 45.0)]
        self.assertEqual(R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[6], "r4-1", ledger=unrelated).status, "READY")


class OldSkipAndLateAck(unittest.TestCase):
    def test_a_late_row_for_a_day_an_apply_skipped_is_refused_by_the_projection_before_evaluate_day(self):
        for name, seq, mapping, late_day in (
                ("non-null parent", 1, {2: "REAPPLY", 3: "DROP", 4: "REAPPLY"}, D[2]),
                ("initial parent", 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, D[1])):
            with self.subTest(name):
                b = R.ex_old_skip() if seq == 1 else R.ex_old_skip_first()
                late = b.w.ledger + [P.obs("L", late_day, 22.0)]
                with mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day:
                    self.assertEqual(err(R.prep, b, seq, mapping, D[5], "r4-1", ledger=late), LATE(late_day))
                self.assertEqual(day.call_count, 0)
                with mock.patch.object(build, "evaluate_day", wraps=build.evaluate_day) as day:
                    self.assertEqual(R.prep(b, seq, mapping, D[5], "r4-1").status, "READY")      # contrast: no late row
                self.assertEqual(day.call_count, 2)                   # both re-applied days are calculated

    def test_a_dropped_late_acknowledgement_lets_the_late_row_come_back(self):
        b = R.ex_late_ack_tail()
        self.assertEqual(err(R.prep, b, 3, {4: "DROP", 5: "DROP"}, D[5], "r4-1"), LATE(D[2]))
        contrast = R.prep(b, 3, {4: "REPLAY", 5: "DROP"}, D[5], "r4-1")                       # the acknowledgement is kept
        self.assertEqual(contrast.status, "READY")
        self.assertEqual([c["op"] for c in contrast.basis["changes"]], ["REPLAY", "DROP"])


class ReplayReferences(unittest.TestCase):
    def test_a_replayed_acknowledgement_points_at_the_reapplied_record(self):
        b = R.ex_ack_between()
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[5], "r4-1")
        events, old = res.history.events, b.events
        ack, apply_ = events[8], events[7]
        self.assertEqual((ack["kind"], apply_["kind"]), ("ACK", "APPLY"))
        self.assertEqual(ack["applied_ref"], {"seq": 7, "event_hash": apply_["event_hash"],
                                              "fingerprint": old[4]["applied_ref"]["fingerprint"]})
        self.assertEqual(ack["replay_of"], {"seq": 4, "event_hash": old[4]["event_hash"]})
        self.assertEqual(R.cj(events[6:]), R.cj(R.oracle(b, 1, mapping, "r4-1", D[5])[6:]))

    def test_a_reference_to_a_retained_record_stays_and_to_a_replayed_one_follows(self):
        b = R.ex_inside_old_batch()
        for point, mapping, apply_seq in (
                (8, {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, 8),     # retained
                (7, {8: "REAPPLY", 9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, 15)):
            with self.subTest(point=point):
                plan, res = R.run(b, point, mapping, D[8], "r4-1")
                ack = [e for e in res.history.events[len(b.events):] if e["kind"] == "ACK"][0]
                self.assertEqual(ack["applied_ref"]["seq"], apply_seq)
                self.assertEqual(ack["applied_ref"]["event_hash"], res.history.events[apply_seq]["event_hash"])
                self.assertEqual(ack["replay_of"]["seq"], 9)                       # the record it replaces, not its origin
                self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(b, point, mapping, "r4-1", D[8])))

    def test_the_request_of_a_replayed_record_is_kept(self):
        b = R.ex_ack_between()
        plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, D[5], "r4-1")
        new, old = plan.basis["candidate_records"][2], b.events[4]
        for key in ("request_id", "request_hash", "request_basis", "command_index", "command_count", "ledger_digest",
                    "variant", "d", "record_fingerprints", "reason_code", "requested_at"):
            if key in old:
                self.assertEqual(R.cj(new.get(key)), R.cj(old[key]), key)

    def test_a_reference_to_a_dropped_declaration_is_refused(self):
        b, _late = R.ex_declare_then_late()
        self.assertEqual(err(R.prep, b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY"}, D[5], "r4-1"),
                         ("restore_invalid", "ops", "restore_ref_unmapped", None))

    def test_a_reference_to_a_record_after_the_point_that_is_not_listed_cannot_be_written(self):
        # the operations must name every record after the point: a hand-written list that leaves out the record
        # the acknowledgement refers to is a shape error (no silent completion)
        b = R.ex_ack_between()
        ops = [{"op": "REPLAY", "from_seq": 4}, {"op": "REAPPLY", "from_seq": 5}]
        self.assertEqual(err(R.prep, b, 1, None, D[5], "r4-1", ops=ops),
                         ("restore_invalid", "ops", "superseded_mismatch", None))

    def test_a_replayed_record_is_never_mapped_twice(self):
        # the acknowledgement 9 of the example replays the one before it (replay_of 5); replaying it again maps the
        # record it refers to once (to the re-applied 8), never to 4 as well
        b = R.ex_inside_old_batch()
        plan = R.prep(b, 7, {8: "REAPPLY", 9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"},
                      D[8], "r4-1")
        ack = plan.basis["candidate_records"][2]
        self.assertEqual((ack["kind"], ack["applied_ref"]["seq"]), ("ACK", 15))
        self.assertEqual(ack["replay_of"]["seq"], 9)


class ReplayRecalculation(unittest.TestCase):
    def test_a_replayed_state_is_the_new_parents_not_the_old_one(self):
        b = R.ex_ack_between()
        plan, res = R.run(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, D[5], "r4-1")
        events = res.history.events
        ack = events[8]
        self.assertEqual(R.cj(ack["state_after"]), R.cj(events[7]["state_after"]))
        self.assertNotEqual(R.cj(ack["state_after"]), R.cj(b.events[4]["state_after"]))
        self.assertIn("state_after", plan.basis["changes"][2]["changed_fields"])

    def test_a_replayed_declaration_follows_the_new_parent_and_the_current_sessions(self):
        b = R.ex_declare_between()                                             # the design's R-b
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[5], "r4-1")
        events = res.history.events
        self.assertEqual(R.cj(events[len(b.events):]), R.cj(R.oracle(b, 1, mapping, "r4-1", D[5])[len(b.events):]))
        declared = events[8]
        self.assertEqual((declared["kind"], declared["frontier_before"]), ("DECLARE_MISSING", D[2]))
        self.assertEqual(R.cj(declared["state_after"]), R.cj(events[7]["state_after"]))
        self.assertEqual(plan.basis["changes"][2]["changed_fields"], ["state_after"])
        # the saved state is the other one: copying it (and fixing the hashes) is not what the runtime writes
        self.assertNotEqual(R.cj(declared["state_after"]), R.cj(b.events[4]["state_after"]))

    def test_the_declaration_context_is_taken_from_the_current_sessions(self):
        b = R.ex_declare_tail_after_restart()
        sessions = R.sessions_with({D[4]: R.earlier_close})                     # next(D3) closes earlier: harmless to every APPLY
        plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY"}, D[6], "r4-1", sessions=sessions)
        change = plan.basis["changes"][2]
        self.assertEqual(change["changed_fields"], ["session_context", "state_after"])
        rec = plan.basis["candidate_records"][2]
        self.assertEqual([e["date"] for e in rec["session_context"]], [D[2], D[3], D[4]])
        self.assertNotEqual(rec["session_context"][2]["close_at"], b.events[4]["session_context"][2]["close_at"])

    def test_a_declaration_that_no_longer_follows_the_frontier_is_refused(self):
        b = H.HB()                                                               # a declaration right after the resume day
        b.apply(D[1], 27.0)
        b.restart(D[3], "q1")
        b.declare(D[4], "q2")
        self.assertEqual(err(R.prep, b, 1, {2: "DROP", 3: "REPLAY"}, D[6], "r4-1"),
                         ("restore_invalid", "ops", "declare_frontier", None))

    def test_a_replayed_restart_has_a_new_floor_and_the_initial_state(self):
        b = R.ex_double_restart()
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        plan, res = R.run(b, 1, mapping, D[5], "r4-1")
        events = res.history.events
        restart = events[len(b.events) + 2]
        self.assertEqual(restart["kind"], "RESTART_UNKNOWN")
        self.assertEqual(restart["floor"], {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(b.events[4]["floor"]["prev_boundary"], D[1])
        self.assertEqual(R.cj(restart["state_after"]), R.cj(events[0]["state_after"]))        # the initial state
        self.assertEqual(R.cj(events[len(b.events):]), R.cj(R.oracle(b, 1, mapping, "r4-1", D[5])[len(b.events):]))
        self.assertEqual(plan.basis["changes"][2]["changed_fields"], ["floor"])

    def test_a_copied_state_with_fixed_hashes_is_not_accepted(self):
        b = R.ex_ack_between()
        mapping = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
        plan, history = R.prep(b, 1, mapping, D[5], "r4-1"), b.history()

        def copy_old_state(events, n):
            events[n + 2]["state_after"] = R.deep(b.events[4]["state_after"])        # the replayed acknowledgement

        forged = R.forge(plan, copy_old_state)
        # the forged candidate is a valid History of its own; only the rebuild from the inputs tells it from the real one
        self.assertEqual(err(R.confirm, forged, history, b.w)[:2], ("history_plan_mismatch", "plan"))


if __name__ == "__main__":
    unittest.main()
