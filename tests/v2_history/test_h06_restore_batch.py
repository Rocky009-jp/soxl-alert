"""H-06: the RECOVERY_RESTORE batch. Example R (design 8.9) and R-b, the re-calculated state_after of created records
(N-01), and every refusal of the restore operations and the batch that follows."""
import unittest

import h_helpers as H
from h_helpers import D, V


def fp(rid, d):
    return H.fp(H.P.obs(rid, d, 41.0, hour=21))


class Restore1(unittest.TestCase):
    def setUp(self):
        self.b = H.example_r1()
        self.ev = self.b.events

    def test_accepted_with_the_designs_shape(self):
        chk = self.b.check()
        self.assertEqual(chk.effective_seqs, (0, 1, 2, 7, 8, 9, 10))
        self.assertEqual(chk.superseded_seqs, (3, 4, 5, 6))
        r = self.ev[7]
        self.assertEqual([(e["op"], e["from_seq"], e["seq"]) for e in r["replay"]],
                         [("DROP", 3, None), ("REAPPLY", 4, 8), ("REPLAY", 5, 9), ("REAPPLY", 6, 10)])
        self.assertEqual([e["op"] for e in r["request_basis"]["ops"]], ["DROP", "REAPPLY", "REPLAY", "REAPPLY"])
        self.assertEqual(r["request_basis"]["restore_point"], {"seq": 2, "event_hash": self.ev[2]["event_hash"]})
        self.assertEqual(r["state_after"], self.ev[2]["state_after"])

    def test_reapply_after_dropping_the_restart_is_not_the_same_as_before(self):
        r = self.ev[7]
        self.assertIs(r["replay"][1]["same_as_superseded"], False)
        old, new = self.ev[4], self.ev[8]
        self.assertEqual(new["d"], old["d"])
        self.assertEqual(new["confirmed_inputs"]["decision"], old["confirmed_inputs"]["decision"])
        self.assertIsNone(old["state_after"]["base"]["as_of_d"])        # after the RESTART: no base date
        self.assertEqual(new["state_after"]["base"]["as_of_d"], D[2])   # after the restore: D2's state is the parent

    def test_replayed_ack_maps_its_reference_and_recomputes_its_state(self):
        old, new = self.ev[5], self.ev[9]
        self.assertEqual(old["applied_ref"]["seq"], 4)
        self.assertEqual(new["applied_ref"], {"seq": 8, "event_hash": self.ev[8]["event_hash"],
                                              "fingerprint": old["applied_ref"]["fingerprint"]})
        self.assertEqual(new["replay_of"], {"seq": 5, "event_hash": old["event_hash"]})
        self.assertEqual(new["state_after"], self.ev[8]["state_after"])
        self.assertNotEqual(new["state_after"], old["state_after"])
        for key in ("request_id", "request_hash", "request_basis", "command_index", "command_count", "reason_code",
                    "requested_at", "ledger_digest", "origin", "record_fingerprints", "variant", "d"):
            self.assertEqual(new[key], old[key], key)

    def test_an_old_state_after_copied_into_the_replayed_record_is_refused_even_with_the_hash_redone(self):
        for who, source in (("old #5", self.ev[5]["state_after"]), ("old #4", self.ev[4]["state_after"])):
            with self.subTest(who):
                ev = H.deep(self.ev)
                ev[9]["state_after"] = H.deep(source)
                H.expect_rule(self, "state_after", H.rebuild(ev, remap=True))

    def test_created_apply_content_is_judged_by_the_s1_projection(self):
        ev = H.deep(self.ev)
        ev[10]["transition_result"]["notes"] = ["x"]
        got = H.rule_of(self, H.rebuild(ev, remap=True))
        self.assertTrue(got.startswith("s1:") or got.startswith("restore_"), got)

    def test_an_ordinary_ack_after_a_restore_keeps_ib04(self):                # K-14
        b = H.example_r1()
        b.ack("ADDED", D[4], [fp("B4", D[4])], "q9", applied=10)
        b.apply(D[5], 33.0)
        self.assertEqual(b.check().effective_seqs[-3:], (10, 11, 12))


class RestartReplayAndRb(unittest.TestCase):
    def test_example_rb_replays_a_declaration_on_a_changed_parent(self):
        b = H.example_rb()
        ev = b.events
        chk = b.check()
        self.assertEqual(chk.effective_seqs, (0, 1, 6, 7, 8, 9))
        self.assertEqual(ev[6]["superseded_seqs"], [2, 3, 4, 5])
        self.assertEqual([(e["op"], e["same_as_superseded"]) for e in ev[6]["replay"]][:3],
                         [("DROP", None), ("REAPPLY", False), ("REPLAY", None)])
        self.assertIsNone(ev[3]["state_after"]["base"]["as_of_d"])
        self.assertEqual(ev[7]["state_after"]["base"]["as_of_d"], D[1])
        self.assertEqual(ev[8]["state_after"], ev[7]["state_after"])
        self.assertNotEqual(ev[8]["state_after"], ev[4]["state_after"])
        self.assertEqual(ev[8]["replay_of"], {"seq": 4, "event_hash": ev[4]["event_hash"]})
        self.assertEqual(ev[8]["frontier_before"], D[2])
        self.assertEqual(ev[8]["session_context"][0], ev[7]["confirmed_inputs"]["session_context"][-2])

    def test_example_rb_refuses_copied_or_stale_values(self):
        ev = H.example_rb().events
        e = H.deep(ev)
        e[8]["state_after"] = H.deep(ev[4]["state_after"])
        H.expect_rule(self, "state_after", H.rebuild(e, remap=True))
        e = H.deep(ev)
        e[8]["frontier_before"] = D[1]
        H.expect_rule(self, "declare_frontier", H.rebuild(e, remap=True))
        e = H.deep(ev)
        e[8]["session_context"][0] = H.deep(ev[8]["session_context"][1])
        H.expect_rule(self, "session_context", H.rebuild(e, remap=True))

    def test_restart_replay_resets_state_and_recomputes_its_floor(self):
        b = H.example_r13()
        b.restore(9, {10: "REAPPLY", 11: "REAPPLY", 12: "REPLAY", 13: "REAPPLY"}, "q5")      # 14 (+15, 16, 17, 18)
        ev = b.events
        chk = b.check()
        self.assertEqual(chk.effective_seqs, (0, 1, 2, 7, 8, 9, 14, 15, 16, 17, 18))
        self.assertEqual([e["op"] for e in ev[14]["replay"]], ["REAPPLY", "REAPPLY", "REPLAY", "REAPPLY"])
        new, old = ev[17], ev[12]
        self.assertEqual(new["replay_of"], {"seq": 12, "event_hash": old["event_hash"]})
        self.assertEqual(new["state_after"], H.initial_state())
        self.assertEqual(new["floor"], {"last_apply_d": D[5], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(old["floor"], new["floor"])
        self.assertTrue(ev[14]["replay"][3]["same_as_superseded"])                      # D6 again from the restart
        self.assertEqual(chk.current_boundary, V.Boundary("RESTART_UNKNOWN", 17, D[5]))
        # refusals on the replayed restart
        e = H.deep(ev)
        e[17]["state_after"] = H.deep(ev[16]["state_after"])
        H.expect_rule(self, "state_after", H.rebuild(e, remap=True))
        e = H.deep(ev)
        e[17]["floor"]["last_apply_d"] = D[4]
        H.expect_rule(self, "restart_floor", H.rebuild(e, remap=True))


class RestoreRefusals(unittest.TestCase):
    def setUp(self):
        self.ev = H.example_r1().events

    # -- the batch must be whole and uninterrupted
    def test_incomplete_batch(self):
        for n in (8, 9, 10):
            with self.subTest(n):
                H.expect_rule(self, "restore_incomplete", H.history_of(self.ev[:n]))
        full = H.example_r().events
        for n in (19, 20, 21, 22):
            with self.subTest("restore 3 cut at %d" % n):
                H.expect_rule(self, "restore_incomplete", H.history_of(full[:n]))

    def test_a_foreign_record_inside_the_batch(self):
        foreign = H.deep(self.ev[4])                                     # an APPLY where an ACK must stand
        got = H.insert_record(self.ev, 9, foreign)
        H.expect_rule(self, "restore_incomplete", H.rebuild(got))
        ack = H.deep(self.ev[5])
        got = H.insert_record(self.ev, 8, ack)                           # an ACK where the APPLY must stand
        H.expect_rule(self, "restore_incomplete", H.rebuild(got))

    # -- operation kinds
    def test_operation_kind_rules(self):
        def setop(index, op):
            def fn(r):
                r["replay"][index].update(op=op, **({} if op in ("REAPPLY", "REPLAY") else
                                                    {"seq": None, "d": None, "same_as_superseded": None}))
            return H.rebuild_edit(self.ev, 7, fn)
        cases = {"apply_dropped": (1, "DROP"), "apply_replayed": (1, "REPLAY"), "apply_retired": (1, "RETIRE"),
                 "ack_reapplied": (2, "REAPPLY"), "ack_retired": (2, "RETIRE"), "restart_reapplied": (0, "REAPPLY"),
                 "restart_retired": (0, "RETIRE"), "unknown_op": (1, "BOGUS")}
        for name, (index, op) in cases.items():
            with self.subTest(name):
                H.expect_rule(self, "restore_op_kind", setop(index, op))
        full = H.example_r().events
        for op in ("REPLAY", "DROP", "REAPPLY"):
            with self.subTest("restore_with_" + op):
                got = H.rebuild_edit(full, 18, lambda r: r["replay"][0].update(op=op))
                H.expect_rule(self, "restore_op_kind", got)

    def test_consume_is_not_supported_in_b1(self):
        def fn(r):
            r["replay"][0] = {"op": "CONSUME", "d": D[3]}
        H.expect_rule(self, "restore_op_unsupported", H.rebuild_edit(self.ev, 7, fn))
        def fn2(r):
            r["replay"].append({"op": "CONSUME", "d": D[5]})
        H.expect_rule(self, "restore_op_unsupported", H.rebuild_edit(self.ev, 7, fn2))

    def test_ops_and_replay_must_agree(self):
        ev = H.deep(self.ev)
        ev[7]["request_basis"]["ops"][1]["op"] = "REPLAY"
        ev[7]["request_hash"] = H.request_hash(ev[7]["request_basis"])
        H.expect_rule(self, "request_basis", H.rebuild(ev))
        ev = H.edit_restore(self.ev, 7, lambda r: r["replay"].pop())
        H.expect_rule(self, "restore_replay_mismatch", H.rebuild(ev, remap=True))

    # -- request batches are dropped / replayed whole
    def test_partial_batch_is_refused_and_whole_batches_are_accepted(self):
        def build(ops):
            b = H.HB()
            b.apply(D[1], 27.0)                                              # 1
            b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [fp("X1", D[1])], "applied": 1},
                          {"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [fp("X2", D[1])], "applied": 1}],
                         "qb")                                               # 2, 3
            b.apply(D[2], 28.0)                                              # 4
            b.restore(1, ops, "qr")
            return b
        for name, ops in {"replay_drop": {2: "REPLAY", 3: "DROP", 4: "REAPPLY"},
                          "drop_replay": {2: "DROP", 3: "REPLAY", 4: "REAPPLY"}}.items():
            with self.subTest(name):
                H.expect_rule(self, "restore_partial_batch", build(ops).history())
        for name, ops in {"replay_both": {2: "REPLAY", 3: "REPLAY", 4: "REAPPLY"},
                          "drop_both": {2: "DROP", 3: "DROP", 4: "REAPPLY"}}.items():
            with self.subTest(name):
                chk = build(ops).check()
                self.assertEqual(chk.superseded_seqs, (2, 3, 4))

    # -- REAPPLY keeps the decision and the market row
    def test_reapply_input_must_match(self):
        def mutate(fn):
            ev = H.deep(self.ev)
            fn(ev[8])
            return H.rebuild(ev, remap=True)
        cases = {
            "decision_value": lambda r: r["confirmed_inputs"]["decision"].update(current_fg_value=44.0),
            "decision_id": lambda r: r["confirmed_inputs"]["decision"].update(record_id="Other1"),
            "row": lambda r: r["confirmed_inputs"]["row"].update(soxx=1.0),
            "prev_row": lambda r: r["confirmed_inputs"].update(prev_row=None),
            "prev_session_date": lambda r: r["confirmed_inputs"].update(prev_session_date=D[0]),
            "d": lambda r: r.update(d=D[9]),
            "context_shared_date": lambda r: r["confirmed_inputs"]["session_context"][1].update(close_at="2030-01-01T00:00:00Z"),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                H.expect_rule(self, "restore_reapply_input", mutate(fn))

    def test_reapply_may_start_from_a_different_date_but_next_d_is_compared_by_date_and_open_only(self):
        # the S1 projection also ignores close_at / confirmed of next(D); so does the REAPPLY comparison
        ev = H.deep(self.ev)
        ev[8]["confirmed_inputs"]["session_context"][-1]["close_at"] = "2030-01-01T00:00:00Z"
        ev[8]["confirmed_inputs"]["session_context"][-1]["confirmed"] = False
        V.validate_history(H.rebuild(ev, remap=True))                       # accepted: only date and open_at count

    def test_same_as_superseded_and_the_replay_list_must_state_facts(self):
        cases = {
            "same_flag_flipped": lambda r: r["replay"][1].update(same_as_superseded=True),
            "same_flag_on_reapply_4": lambda r: r["replay"][3].update(same_as_superseded=False),
            "same_flag_null": lambda r: r["replay"][1].update(same_as_superseded=None),
            "created_seq_off_by_one": lambda r: r["replay"][1].update(seq=9),
            "created_seq_null": lambda r: r["replay"][1].update(seq=None),
            "from_seq_wrong": lambda r: r["replay"][1].update(from_seq=5),
            "d_wrong": lambda r: r["replay"][1].update(d=D[9]),
            "drop_with_seq": lambda r: r["replay"][0].update(seq=8),
            "replay_with_d": lambda r: r["replay"][2].update(d=D[3]),
            "extra_key": lambda r: r["replay"][2].update(extra=1),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                got = H.rule_of(self, H.rebuild_edit(self.ev, 7, fn))
                self.assertEqual(got, "restore_replay_mismatch", name)

    # -- REPLAY: references are mapped, request items are kept
    def test_replay_reference_not_mapped_or_pointing_at_a_dropped_record(self):
        ev = H.deep(self.ev)
        ev[9]["applied_ref"] = {"seq": 4, "event_hash": self.ev[4]["event_hash"],
                                "fingerprint": ev[9]["applied_ref"]["fingerprint"]}
        H.expect_rule(self, "restore_ref_unmapped", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[9]["applied_ref"]["event_hash"] = "0" * 64
        H.expect_rule(self, "restore_ref_unmapped", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[9]["applied_ref"]["fingerprint"] = "1" * 64
        H.expect_rule(self, "restore_ref_unmapped", H.rebuild(ev))

    def test_replay_of_a_record_whose_reference_target_was_dropped(self):
        b = H.HB()
        b.apply(D[1], 27.0)                                                  # 1
        b.declare(D[2], "qd")                                                # 2
        b.apply(D[3], 29.0)                                                  # 3 (skips D2)
        late_fp = fp("L2", D[2])
        b.ack("LATE", D[2], [late_fp], "ql", missing=("DECLARE_MISSING", 2))  # 4
        b.restore(1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY"}, "qr")           # the LATE refers to the dropped record
        H.expect_rule(self, "restore_ref_unmapped", b.history())
        ok = H.HB()
        ok.apply(D[1], 27.0)
        ok.declare(D[2], "qd")
        ok.apply(D[3], 29.0)
        ok.ack("LATE", D[2], [late_fp], "ql", missing=("DECLARE_MISSING", 2))
        ok.restore(1, {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY"}, "qr")
        self.assertEqual(ok.events[-1]["missing_ref"]["seq"], ok.events[-3]["seq"])
        ok.check()

    def test_replay_keeps_request_items_and_names_its_original(self):
        cases = {"request_id": "Z9", "requested_at": "2030-01-01T00:00:00Z", "d": D[9], "variant": "CHANGED"}
        for key, value in cases.items():
            with self.subTest(key):
                ev = H.deep(self.ev)
                ev[9][key] = value
                got = H.rule_of(self, H.rebuild(ev, remap=True))
                self.assertEqual(got, "restore_replay_mismatch")
        ev = H.deep(self.ev)
        ev[9]["record_fingerprints"] = ["f" * 64]
        self.assertEqual(H.rule_of(self, H.rebuild(ev, remap=True)), "restore_replay_mismatch")

    def test_replay_of_must_name_the_superseded_original(self):
        ev = H.deep(self.ev)
        ev[9]["replay_of"] = None
        H.expect_rule(self, "replay_of", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[9]["replay_of"]["event_hash"] = "0" * 64
        H.expect_rule(self, "replay_of", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[5]["replay_of"] = {"seq": 3, "event_hash": self.ev[3]["event_hash"]}      # a record nobody replayed
        H.expect_rule(self, "replay_of", H.rebuild(ev, remap=True))

    def test_restore_state_must_be_the_restore_points(self):
        ev = H.deep(self.ev)
        ev[7]["state_after"] = H.deep(self.ev[6]["state_after"])
        H.expect_rule(self, "restore_state", H.rebuild(ev))

    def test_restore_basis_form(self):
        cases = {
            "point_hash": (lambda r: r["request_basis"]["restore_point"].update(event_hash="0" * 64), "request_basis"),
            "reason_code": (lambda r: r.update(reason_code="X"), "reason_code"),
            "check_d_before_boundary": (lambda r: r["request_basis"].update(check_d=D[0]), "check_d"),
            "check_d_before_latest_apply": (lambda r: r["request_basis"].update(check_d=D[1]), "check_d"),
            "bad_request_id": (lambda r: r.update(request_id="a b"), "request_id"),
            "ledger_digest": (lambda r: r.update(ledger_digest="zz"), "ledger_digest"),
        }
        for name, (fn, rule) in cases.items():
            with self.subTest(name):
                ev = H.deep(self.ev)
                fn(ev[7])
                if name not in ("point_hash", "reason_code", "bad_request_id"):
                    ev[7]["request_hash"] = H.request_hash(ev[7]["request_basis"])
                H.expect_rule(self, rule, H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[7]["request_hash"] = "0" * 64
        H.expect_rule(self, "request_hash", H.rebuild(ev))


if __name__ == "__main__":
    unittest.main()
