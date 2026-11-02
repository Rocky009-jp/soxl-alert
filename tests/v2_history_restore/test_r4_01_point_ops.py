"""B4-02 (restore point), B4-03 (valid suffix) and B4-04 (operation list)."""
import unittest

import r4_helpers as R

T, H, Z, D, P, V = R.T, R.H, R.Z, R.D, R.P, R.V
INVALID = "restore_invalid"


def rule(case, fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    case.assertEqual(e.code, INVALID, (e.code, e.field, e.rule))
    return e.field, e.rule


class RestorePoint(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()
        self.map = {2: "DROP", 3: "REAPPLY"}

    def test_a_new_genesis_itself_is_accepted_as_the_restore_point(self):
        b = self.b
        plan, res = R.run(b, 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, D[3], "r4-1")
        self.assertEqual(plan.basis["restore_point"]["seq"], 0)
        self.assertEqual(V.validate_history(res.history).effective_seqs, (0, 4, 5, 6))
        self.assertEqual([R.cj(e) for e in res.history.events],
                         [R.cj(e) for e in R.oracle(b, 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, "r4-1", D[3])])

    def test_the_schema_migration_record_itself_is_accepted_but_nothing_before_it(self):
        b = R.ex_migrated_tail()
        mapping = {8: "REAPPLY", 9: "DROP", 10: "REAPPLY"}
        plan, res = R.run(b, 7, mapping, D[9], "r4-1")
        check = V.validate_history(res.history)
        self.assertTrue(check.migrated)
        self.assertEqual(check.effective_seqs, (0, 1, 2, 3, 4, 5, 6, 7, 11, 12, 13))
        self.assertEqual([R.cj(e) for e in res.history.events], [R.cj(e) for e in R.oracle(b, 7, mapping, "r4-1", D[9])])
        for seq in (6, 3, 0):                 # before the migration: refused, whatever it would have kept
            ops = [{"op": "DROP", "from_seq": s} for s in R.after(b, seq)]
            self.assertEqual(rule(self, R.prep, b, seq, {}, D[9], "r4-1", ops=ops),
                             ("restore_point", "restore_before_migration"))

    def test_the_physical_head_is_a_no_op_and_a_superseded_record_is_not_effective(self):
        h = self.b.history()
        head = self.b.events[-1]
        self.assertEqual(rule(self, R.prep, self.b, 3, {}, D[3], "r4-1", ops=[]), ("restore_point", "restore_noop"))
        self.assertEqual(head["seq"], 3)
        c = R.ex_after_three_restores()
        self.assertEqual(rule(self, R.prep, c, 5, {}, D[10], "r4-1", ops=[]), ("restore_point", "restore_point_not_effective"))
        self.assertEqual(rule(self, R.prep, c, 99, {}, D[10], "r4-1", ops=[], pt={"seq": 99, "event_hash": "0" * 64}),
                         ("restore_point", "restore_point_not_effective"))
        self.assertEqual(h.head_seq, 3)

    def test_a_wrong_hash_and_a_wrong_form_are_refused(self):
        b = self.b
        wrong = {"seq": 1, "event_hash": b.events[2]["event_hash"]}
        self.assertEqual(rule(self, R.prep, b, 1, self.map, D[3], "r4-1", pt=wrong),
                         ("restore_point", "restore_point_mismatch"))
        good = R.point(b, 1)
        for bad in (None, [], "1", {"seq": 1}, dict(good, extra=1), {"seq": True, "event_hash": good["event_hash"]},
                    {"seq": 1.0, "event_hash": good["event_hash"]}, {"seq": "1", "event_hash": good["event_hash"]},
                    {"seq": -1, "event_hash": good["event_hash"]}, {"seq": 1, "event_hash": "ABC"},
                    {"seq": 1, "event_hash": good["event_hash"].upper()}, {"seq": 1, "event_hash": None}):
            self.assertEqual(rule(self, R.prep, b, 1, self.map, D[3], "r4-1", pt=bad),
                             ("restore_point", "restore_point_shape"), repr(bad))

    def test_a_point_in_the_middle_of_a_request_batch_is_refused_but_its_last_record_is_a_valid_point(self):
        b = R.ex_two_command_request()
        ops = [{"op": "DROP", "from_seq": 4}, {"op": "DROP", "from_seq": 5}]
        self.assertEqual(rule(self, R.prep, b, 3, {}, D[3], "r4-1", ops=ops), ("restore_point", "restore_point_in_batch"))
        plan = R.prep(b, 4, {}, D[3], "r4-1", ops=[{"op": "DROP", "from_seq": 5}])
        self.assertEqual(plan.basis["restore_point"]["seq"], 4)

    def test_a_valid_point_is_the_last_record_of_a_batch_and_a_point_inside_an_earlier_restore_batch_is_accepted(self):
        b = R.ex_inside_old_batch()
        mapping = {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}
        plan, res = R.run(b, 8, mapping, D[10], "r4-review-1")                  # seq 8: APPLY in the middle of restore #1
        self.assertEqual(plan.basis["restore_point"]["seq"], 8)
        with self.assertRaises(Exception):                                       # the physical prefix 0..8 is no History
            V.validate_history(V.History.from_dict(H.header(b.events[:9])))
        self.assertEqual([R.cj(e) for e in res.history.events], [R.cj(e) for e in R.oracle(b, 8, mapping, "r4-review-1", D[10])])
        self.assertEqual(V.validate_history(res.history).head_seq, 18)


class ValidSuffix(unittest.TestCase):
    def test_after_two_and_three_restores_the_suffix_is_the_effective_one_not_the_physical_range(self):
        b = R.ex_after_three_restores()
        chain = H.chain_of(b.events)
        self.assertEqual(chain, [0, 1, 2, 18, 19, 20, 21, 22, 23, 24, 25])
        mapping = {18: "RETIRE", 19: "REAPPLY", 20: "REAPPLY", 21: "REAPPLY", 22: "REAPPLY", 23: "REAPPLY",
                   24: "DROP", 25: "REAPPLY"}
        plan, res = R.run(b, 2, mapping, D[10], "r4-review-1")
        self.assertEqual(plan.basis["ops"], [{"op": o, "from_seq": s} for s, o in sorted(mapping.items())])
        restore = res.history.events[26]
        self.assertEqual(restore["superseded_seqs"], [18, 19, 20, 21, 22, 23, 24, 25])
        self.assertEqual(V.validate_history(res.history).superseded_seqs, tuple(range(3, 26)))
        self.assertEqual([R.cj(e) for e in res.history.events], [R.cj(e) for e in R.oracle(b, 2, mapping, "r4-review-1", D[10])])
        # the physical range after P (3..25) names records that are already superseded: refused, nothing is completed
        ops = [{"op": "DROP", "from_seq": s} for s in range(3, 26)]
        self.assertEqual(rule(self, R.prep, b, 2, {}, D[10], "r4-review-2", ops=ops), ("ops", "superseded_mismatch"))

    def test_a_second_restore_does_not_retire_a_record_twice(self):
        b = R.ex_after_three_restores()
        plan, res = R.run(b, 21, {22: "REAPPLY", 23: "REAPPLY", 24: "DROP", 25: "REAPPLY"}, D[10], "r4-review-1")
        h2 = res.history
        self.assertEqual(V.validate_history(h2).superseded_seqs[-4:], (22, 23, 24, 25))
        # P = 21 is still effective; ask to retire 22 again from the new history: it is no longer in the suffix
        b2 = H.HB(world=b.w, events=h2.events)
        ops = [{"op": "DROP", "from_seq": 22}] + [{"op": "REAPPLY", "from_seq": s} for s in R.after(b2, 21)]
        self.assertEqual(rule(self, R.prep, b2, 21, {}, D[10], "r4-review-2", ops=ops), ("ops", "superseded_mismatch"))


class OperationList(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_restart_between()

    def bad(self, ops, expected, b=None, seq=1, rid="r4-1", check=D[3]):
        self.assertEqual(rule(self, R.prep, b or self.b, seq, {}, check, rid, ops=ops), expected, repr(ops))

    def test_the_list_must_be_a_list_of_exact_dicts_with_strict_integers(self):
        ok = [{"op": "DROP", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}]
        self.assertEqual(Z.prepare_restore_plan.__name__, "prepare_restore_plan")
        shape = ("ops", "ops_shape")
        self.bad(tuple(ok), shape)
        self.bad("x", shape)
        self.bad(None, shape)
        self.bad([ok[0], "x"], shape)
        self.bad([ok[0], {"op": 5, "from_seq": 3}], shape)
        self.bad([ok[0], {"op": "REAPPLY"}], shape)
        self.bad([ok[0], {"op": "REAPPLY", "from_seq": 3, "d": D[2]}], shape)
        self.bad([ok[0], {"op": "REAPPLY", "from_seq": True}], shape)
        self.bad([ok[0], {"op": "REAPPLY", "from_seq": 3.0}], shape)
        self.bad([ok[0], {"op": "REAPPLY", "from_seq": "3"}], shape)

    def test_every_record_after_the_point_is_named_once_in_the_same_order_nothing_is_completed(self):
        mism = ("ops", "superseded_mismatch")
        self.bad([], mism)
        self.bad([{"op": "DROP", "from_seq": 2}], mism)
        self.bad([{"op": "REAPPLY", "from_seq": 3}, {"op": "DROP", "from_seq": 2}], mism)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "DROP", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}], mism)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}, {"op": "DROP", "from_seq": 4}], mism)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 9}], mism)

    def test_consume_and_unknown_operations_are_refused_with_any_keys(self):
        unsupported = ("ops", "restore_op_unsupported")
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "from_seq": 3}], unsupported)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "d": D[2]}], unsupported)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "consume", "from_seq": 3}], unsupported)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "MERGE", "from_seq": 3}], unsupported)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "", "from_seq": 3}], unsupported)

    def test_an_operation_that_the_record_kind_does_not_allow_is_refused(self):
        kind = ("ops", "restore_op_kind")
        self.bad([{"op": "REAPPLY", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}], kind)      # restart
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "DROP", "from_seq": 3}], kind)            # apply
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "REPLAY", "from_seq": 3}], kind)
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "RETIRE", "from_seq": 3}], kind)
        self.bad([{"op": "RETIRE", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}], kind)
        c = R.ex_ack_between()
        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "REAPPLY", "from_seq": 3}, {"op": "REAPPLY", "from_seq": 4},
                  {"op": "REAPPLY", "from_seq": 5}], kind, b=c)                                   # ack
        d = R.ex_after_three_restores()
        ops = [{"op": "DROP", "from_seq": 18}] + [{"op": "REAPPLY", "from_seq": s} for s in range(19, 26)]
        self.bad(ops, kind, b=d, seq=2, check=D[10])                                               # a restore may only be retired

    def test_a_request_batch_is_dropped_or_replayed_as_a_whole(self):
        b = R.ex_two_command_request()
        part = ("ops", "restore_partial_batch")
        tail = {"op": "DROP", "from_seq": 5}
        self.bad([{"op": "REPLAY", "from_seq": 3}, {"op": "DROP", "from_seq": 4}, tail], part, b=b, seq=2, check=D[4])
        self.bad([{"op": "DROP", "from_seq": 3}, {"op": "REPLAY", "from_seq": 4}, tail], part, b=b, seq=2, check=D[4])
        # replayed as a whole (and the restart dropped): the batch is rebuilt in the same order and shape
        plan, res = R.run(b, 2, {3: "REPLAY", 4: "REPLAY", 5: "DROP"}, D[4], "r4-1")
        self.assertEqual([e["command_index"] for e in res.history.events[-2:]], [0, 1])
        self.assertEqual([c["op"] for c in plan.basis["changes"]], ["REPLAY", "REPLAY", "DROP"])


if __name__ == "__main__":
    unittest.main()
