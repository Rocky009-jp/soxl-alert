"""H-03 audit chain, H-04 effective chain and superseded records, H-05 superseded list. Example R is the design's
three-restore history (new schema-2 history, no SCHEMA_MIGRATION); example M's records are built on a migration."""
import unittest

import h_helpers as H
from h_helpers import D, V


class AuditChain(unittest.TestCase):
    def setUp(self):
        self.ev = H.example_r().events

    def test_example_r_is_accepted(self):
        chk = V.validate_history(H.history_of(self.ev))
        self.assertEqual(chk.record_count, 23)

    def test_a_missing_or_repeated_seq(self):
        gone = H.deep(self.ev)
        del gone[2]
        H.expect_rule(self, "seq", H.rebuild(gone))
        twice = H.deep(self.ev)
        twice[3]["seq"] = 2
        H.expect_rule(self, "seq", H.rebuild(twice))

    def test_a_changed_record_without_its_hash_updated(self):
        ev = H.deep(self.ev)
        ev[6]["d"] = D[9]
        H.expect_rule(self, "event_hash", H.history_of(ev))
        ev = H.deep(self.ev)
        ev[6]["event_hash"] = "f" * 64
        H.expect_rule(self, "event_hash", H.history_of(ev))

    def test_a_changed_record_with_only_its_own_hash_updated_breaks_the_next_link(self):
        ev = H.deep(self.ev)
        ev[6]["d"] = D[9]
        ev[6]["event_hash"] = H.hash_of(ev[6])
        H.expect_rule(self, "audit_hash", H.history_of(ev))

    def test_a_wrong_audit_previous_hash(self):
        ev = H.deep(self.ev)
        ev[5]["parent_hash"] = "0" * 64
        ev[5]["event_hash"] = H.hash_of(ev[5])
        H.expect_rule(self, "audit_hash", H.history_of(ev))
        ev = H.deep(self.ev)                                  # a RECOVERY_RESTORE keeps its audit link in prev_hash
        ev[7]["prev_hash"] = ev[5]["event_hash"]
        ev[7]["event_hash"] = H.hash_of(ev[7])
        H.expect_rule(self, "audit_hash", H.history_of(ev))

    def test_head_must_match_the_last_record(self):
        d = H.history_of(self.ev).to_dict()
        d["head_hash"] = "0" * 64
        H.expect_rule(self, "head", V.History.from_dict(d))
        d = H.history_of(self.ev).to_dict()
        d["head_seq"] = 21
        H.expect_rule(self, "head", V.History.from_dict(d))

    def test_first_must_be_genesis_and_only_the_first(self):
        ev = H.deep(self.ev)
        ev[0] = H.deep(ev[1])
        ev[0]["seq"] = 0
        H.expect_rule(self, "first_not_genesis", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[2] = dict(H.deep(self.ev[0]), seq=2)
        H.expect_rule(self, "genesis_not_first", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[0]["state_after"]["streak"] = 4
        H.expect_rule(self, "genesis_state", H.rebuild(ev))

    def test_effective_parent_shape(self):
        ev = H.deep(self.ev)
        ev[4]["parent_seq"] = 2                                # an ordinary record must point at seq-1
        H.expect_rule(self, "parent", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[7]["parent_seq"] = 7                                # a RESTORE may point only strictly before seq-1... 
        H.expect_rule(self, "parent", H.rebuild(ev))
        b = H.HB()                                             # the RESTORE is the last record of this history
        b.apply(D[1], 27.0)
        b.ack("ADDED", D[1], [P_fp("X1", D[1])], "qa", applied=1)
        b.restore(1, {2: "DROP"}, "qr")
        ev = H.deep(b.events)
        ev[3]["parent_hash"] = "0" * 64                        # the effective parent hash must be the parent's
        ev[3]["event_hash"] = H.hash_of(ev[3])
        H.expect_rule(self, "parent", H.history_of(ev))

    def test_retired_records_cannot_be_deleted_changed_or_reordered(self):
        # records 4 and 11 are not on the final chain, but the audit chain still covers them (design 4.1)
        for index in (4, 11):
            with self.subTest("delete %d" % index):
                ev = H.deep(self.ev)
                del ev[index]
                H.expect_rule(self, "seq", H.rebuild(ev))
            with self.subTest("change %d" % index):
                ev = H.deep(self.ev)
                ev[index]["d"] = D[9]
                H.expect_rule(self, "event_hash", H.history_of(ev))
            with self.subTest("change and rehash only %d" % index):
                ev = H.deep(self.ev)
                ev[index]["d"] = D[9]
                ev[index]["event_hash"] = H.hash_of(ev[index])
                H.expect_rule(self, "audit_hash", H.history_of(ev))
            with self.subTest("change %d and relink everything" % index):
                # the records still hash and link consistently, but no later record agrees with the changed one
                ev = H.deep(self.ev)
                ev[index]["d"] = D[9]
                self.assertIsNotNone(H.rule_of(self, H.rebuild(ev, remap=True)))
        with self.subTest("reorder"):
            ev = H.deep(self.ev)
            ev[4], ev[11] = ev[11], ev[4]
            H.expect_rule(self, "seq", H.rebuild(ev))
            ev = H.deep(self.ev)
            ev[4], ev[5] = ev[5], ev[4]
            ev[4]["seq"], ev[5]["seq"] = 4, 5
            ev[4]["event_hash"], ev[5]["event_hash"] = H.hash_of(ev[4]), H.hash_of(ev[5])
            H.expect_rule(self, "audit_hash", H.history_of(ev))


class EffectiveChain(unittest.TestCase):
    """H-04. Example R is a new schema-2 history (no SCHEMA_MIGRATION): its restores are accepted at the current seqs."""

    def test_final_chain_and_superseded_union_of_example_r(self):
        chk = H.example_r().check()
        self.assertEqual(chk.effective_seqs, (0, 1, 2, 18, 19, 20, 21, 22))
        self.assertEqual(chk.superseded_seqs, tuple(range(3, 18)))
        self.assertEqual(chk.head_seq, 22)
        self.assertEqual(chk.record_count, 23)
        self.assertEqual(chk.current_boundary, V.Boundary("GENESIS", 0, D[0]))
        self.assertFalse(chk.migrated)

    def test_the_three_restores_have_the_designs_superseded_lists(self):
        ev = H.example_r().events
        self.assertEqual(ev[7]["superseded_seqs"], [3, 4, 5, 6])
        self.assertEqual(ev[14]["superseded_seqs"], [10, 11, 12, 13])
        self.assertEqual(ev[18]["superseded_seqs"], [7, 8, 9, 14, 15, 16, 17])
        self.assertEqual([ev[k]["parent_seq"] for k in (7, 14, 18)], [2, 9, 2])
        self.assertEqual([ev[k]["kind"] for k in range(19, 23)], ["APPLY"] * 4)

    def test_example_r_b_and_u(self):
        chk = H.example_rb().check()
        self.assertEqual(chk.effective_seqs, (0, 1, 6, 7, 8, 9))
        self.assertEqual(chk.superseded_seqs, (2, 3, 4, 5))
        chk = H.example_u().check()
        self.assertEqual(chk.effective_seqs, (0, 1, 2, 3))

    def test_restore_to_genesis_is_accepted_in_a_new_history(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        rec = b.restore(0, {1: "REAPPLY", 2: "REAPPLY"}, "q1")
        self.assertEqual((rec["parent_seq"], rec["superseded_seqs"]), (0, [1, 2]))
        chk = b.check()
        self.assertEqual(chk.effective_seqs, (0, 3, 4, 5))
        self.assertEqual(chk.superseded_seqs, (1, 2))
        self.assertTrue(all(e["same_as_superseded"] for e in rec["replay"]))

    def test_restore_noop_in_a_new_history(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restore(1, {}, "q1")
        H.expect_rule(self, "restore_noop", b.history())

    def test_a_point_that_is_not_effective_is_refused(self):
        ev = H.example_r().events
        for p in (5, 12, 4, 8):                                # 5 and 12 are the design's examples
            with self.subTest(p):
                got = H.hand_restore(ev, p, [])
                H.expect_rule(self, "restore_point_not_effective", H.history_of(got))

    def test_a_point_inside_a_request_batch_is_refused_and_its_last_record_is_not(self):
        def build(point):
            b = H.HB()
            b.apply(D[1], 27.0)
            x, y = P_fp("X1", D[1]), P_fp("X2", D[1])
            b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [x], "applied": 1},
                          {"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [y], "applied": 1}], "qb")   # 2, 3
            b.apply(D[2], 28.0)                                # 4
            b.restore(point, {s: "REAPPLY" if s == 4 else "REPLAY" for s in b.chain()[b.chain().index(point) + 1:]},
                      "qr")
            return b
        H.expect_rule(self, "restore_point_in_batch", build(2).history())
        self.assertEqual(build(3).check().effective_seqs[:4], (0, 1, 2, 3))

    def test_point_checks_hold_in_a_migrated_history_too(self):
        b, _ = H.example_m()                                   # 0..6 moved, 7 SCHEMA_MIGRATION
        mig = 7
        b.apply(D[5], 30.0)                                    # 8
        b.apply(D[6], 31.0)                                    # 9
        got = H.hand_restore(b.events, 9, [])                  # the point is the previous record: no-op
        H.expect_rule(self, "restore_noop", H.history_of(got))
        for point in (0, 5, 6):                                # 6 is the record right before the SCHEMA_MIGRATION
            with self.subTest(point):
                got = H.hand_restore(b.events, point, [])
                H.expect_rule(self, "restore_before_migration", H.history_of(got))
        # retired / non-effective records are refused as points in a migrated history as well
        r = H.HB(world=b.w, events=b.events)
        r.restore(mig, {8: "REAPPLY", 9: "REAPPLY"}, "rr1")    # to the SCHEMA_MIGRATION itself: accepted
        chk = r.check()
        self.assertEqual(chk.effective_seqs, tuple(range(8)) + (10, 11, 12))
        got = H.hand_restore(r.events, 8, [])
        H.expect_rule(self, "restore_point_not_effective", H.history_of(got))
        got = H.hand_restore(r.events, 9, [])
        H.expect_rule(self, "restore_point_not_effective", H.history_of(got))

    def test_a_point_inside_a_request_batch_after_the_migration_is_refused_too(self):
        b, _ = H.example_m()
        b.apply(D[5], 30.0)                                                  # 8
        b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[5], "fps": [P_fp("X5", D[5])], "applied": 8},
                      {"kind": "ACK", "variant": "ADDED", "d": D[5], "fps": [P_fp("X6", D[5])], "applied": 8}],
                     "rb")                                                   # 9, 10
        b.apply(D[6], 31.0)                                                  # 11
        b.restore(9, {10: "REPLAY", 11: "REAPPLY"}, "rr1")
        H.expect_rule(self, "restore_point_in_batch", b.history())
        c, _ = H.example_m()
        c.apply(D[5], 30.0)
        c.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[5], "fps": [P_fp("X5", D[5])], "applied": 8},
                      {"kind": "ACK", "variant": "ADDED", "d": D[5], "fps": [P_fp("X6", D[5])], "applied": 8}], "rb")
        c.apply(D[6], 31.0)
        c.restore(10, {11: "REAPPLY"}, "rr1")                                # the last record of the batch is fine
        self.assertTrue(c.check().migrated)

    def test_restore_after_the_migration_is_accepted_at_and_after_the_migration(self):
        b, _ = H.example_m()
        mig = 7
        b.apply(D[5], 30.0)                                    # 8
        b.apply(D[6], 31.0)                                    # 9
        b.restore(8, {9: "REAPPLY"}, "rr1")                    # a later point
        self.assertTrue(b.check().migrated)
        b.restore(mig, {s: "REAPPLY" if b.events[s]["kind"] == "APPLY" else "RETIRE"
                        for s in b.chain()[b.chain().index(mig) + 1:]}, "rr2")
        chk = b.check()
        self.assertTrue(chk.migrated)
        self.assertEqual(chk.effective_seqs[:8], tuple(range(8)))

    def test_the_effective_chain_does_not_use_physical_ranges(self):
        chk = H.example_r().check()
        self.assertNotEqual(chk.effective_seqs, tuple(range(0, 3)) + tuple(range(18, 23)) + (99,))
        self.assertEqual(sorted(chk.effective_seqs + chk.superseded_seqs), list(range(23)))   # I-08 / I-09


class SupersededList(unittest.TestCase):
    """H-05"""

    def setUp(self):
        self.ev = H.example_r().events

    def test_restore_3_list_is_accepted(self):
        self.assertEqual(V.validate_history(H.history_of(self.ev)).superseded_seqs, tuple(range(3, 18)))

    def test_a_physical_range_or_wrong_list_is_refused(self):
        wrong = {
            "physical_range": list(range(3, 18)),
            "missing_element": [7, 8, 9, 14, 15, 16],
            "extra_element": [6, 7, 8, 9, 14, 15, 16, 17],
            "reversed": [17, 16, 15, 14, 9, 8, 7],
            "wrong_order": [8, 7, 9, 14, 15, 16, 17],
            "duplicate": [7, 8, 9, 14, 15, 16, 17, 17],
            "empty": [],
            "not_a_list": "7,8",
        }
        for name, lst in wrong.items():
            with self.subTest(name):
                ev = H.edit_restore(self.ev, 18, lambda r: r.__setitem__("superseded_seqs", lst))
                H.expect_rule(self, "superseded_mismatch", H.rebuild(ev))

    def test_the_union_must_cover_exactly_the_records_off_the_chain(self):
        # drop RESTORE#1's claim on [3..6]: records 3..6 become retired by nobody
        ev = H.edit_restore(self.ev, 7, lambda r: r.__setitem__("superseded_seqs", [3, 4, 5]))
        H.expect_rule(self, "superseded_mismatch", H.rebuild(ev))


def P_fp(rid, d):
    return H.fp(H.P.obs(rid, d, 41.0, hour=21))


if __name__ == "__main__":
    unittest.main()
