"""H-08: ACK / DECLARE_MISSING rules in the schema-2 history (design 6): references to ancestors only, LATE, ROW_REMOVED,
exclude_applied, check_d, the frontier and its three sources, batches, request hashes and ids, and that a normal
extension never invalidates an older record."""
import unittest

import h_helpers as H
from h_helpers import D, V


def fp(rid, d):
    return H.fp(H.P.obs(rid, d, 41.0, hour=21))


def added():
    """0 GENESIS, 1 APPLY D1, 2 APPLY D2, 3 ACK/ADDED(D2), 4 APPLY D3."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.apply(D[2], 28.0)
    b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2)
    b.apply(D[3], 31.0)
    return b


def declared():
    """0 GENESIS, 1 APPLY D1, 2 DECLARE D2, 3 APPLY D3 (skips D2), 4 ACK/LATE(D2 -> declaration 2)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.declare(D[2], "qd")
    b.apply(D[3], 29.0)
    b.ack("LATE", D[2], [fp("L2", D[2])], "ql", missing=("DECLARE_MISSING", 2))
    return b


def skipped():
    """0 GENESIS, 1 APPLY D1, 2 APPLY D3 (skips D2), 3 ACK/LATE(D2 -> APPLY 2)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.apply(D[3], 29.0)
    b.ack("LATE", D[2], [fp("L2", D[2])], "ql", missing=("APPLY", 2))
    return b


class Accepted(unittest.TestCase):
    def test_all_variants_are_accepted(self):
        for build in (added, declared, skipped):
            with self.subTest(build.__name__):
                build().check()
        b = added()
        b.ack("CHANGED", D[2], [fp("X2", D[2])], "qc", applied=2)
        b.ack("ROW_REMOVED", D[1], [], "qr", applied=1)
        b.check()

    def test_a_normal_extension_does_not_invalidate_older_records(self):
        b = added()
        b.apply(D[4], 32.0)
        b.declare(D[5], "qd")
        b.apply(D[6], 34.0)                                                  # skips D5
        b.ack("LATE", D[5], [fp("L5", D[5])], "ql", missing=("DECLARE_MISSING", 6))
        b.apply(D[7], 35.0)
        chk = b.check()
        self.assertEqual(chk.latest_apply_d, D[7])
        self.assertEqual(chk.declared_days_in_segment, (D[5],))

    def test_request_hash_equals_the_s3a_value(self):
        b = added()
        rec = b.events[3]
        basis = rec["request_basis"]
        from v2_recovery.common import request_hash_of
        self.assertEqual(rec["request_hash"], request_hash_of(basis["request_id"], basis["commands"],
                                                              basis["check_d"], basis["reason_code"]))


class AppliedReference(unittest.TestCase):
    def setUp(self):
        self.ev = added().events

    def rule(self, **fields):
        return H.rule_of(self, H.rebuild(H.edit_resolution(self.ev, 3, **fields)))

    def test_wrong_references(self):
        good = self.ev[3]["applied_ref"]
        cases = {
            "event_hash": dict(good, event_hash="0" * 64),
            "fingerprint": dict(good, fingerprint="1" * 64),
            "other_apply": {"seq": 1, "event_hash": self.ev[1]["event_hash"], "fingerprint": H.fp_of_apply(self.ev[1])},
            "not_an_apply": {"seq": 0, "event_hash": self.ev[0]["event_hash"], "fingerprint": good["fingerprint"]},
            "forward": {"seq": 4, "event_hash": self.ev[4]["event_hash"], "fingerprint": H.fp_of_apply(self.ev[4])},
            "itself": {"seq": 3, "event_hash": self.ev[3]["event_hash"], "fingerprint": good["fingerprint"]},
            "beyond": {"seq": 9, "event_hash": "0" * 64, "fingerprint": good["fingerprint"]},
        }
        for name, ref in cases.items():
            with self.subTest(name):
                got = self.rule(applied_ref=ref)
                self.assertIn(got, ("applied_ref", "command_shape") if name == "not_an_apply" else ("applied_ref",))

    def test_the_day_must_be_the_applys(self):
        self.assertEqual(self.rule(d=D[1]), "applied_ref")

    def test_a_reference_to_an_ancestor_is_accepted(self):
        V.validate_history(H.rebuild(H.edit_resolution(self.ev, 3, applied_ref=self.ev[3]["applied_ref"])))

    def test_variant_presence_rules(self):
        self.assertEqual(self.rule(missing_ref={"kind": "APPLY", "seq": 1, "event_hash": self.ev[1]["event_hash"]}),
                         "missing_ref")
        self.assertEqual(self.rule(applied_ref=None), "applied_ref")

    def test_fingerprints_must_be_sorted_unique_hex_and_not_empty(self):
        a, b = sorted([fp("X1", D[2]), fp("X2", D[2])])
        for name, fps in {"unsorted": [b, a], "duplicate": [a, a], "not_hex": ["zz"], "empty": []}.items():
            with self.subTest(name):
                got = self.rule(record_fingerprints=fps)
                self.assertIn(got, ("fingerprints", "command_shape"))
        self.assertEqual(self.rule(record_fingerprints=[]), "fingerprints")

    def test_row_removed_has_no_fingerprints(self):
        ev = H.deep(self.ev)
        ev = H.edit_resolution(ev, 3, variant="ROW_REMOVED")
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "fingerprints")
        ev = H.edit_resolution(ev, 3, record_fingerprints=[])
        V.validate_history(H.rebuild(ev))

    def test_an_applys_own_fingerprint_may_not_be_excluded(self):
        for i in (1, 2, 4):
            with self.subTest(i):
                self.assertEqual(self.rule(record_fingerprints=[H.fp_of_apply(self.ev[i])]), "exclude_applied")

    def test_ack_has_no_session_context_or_frontier(self):
        self.assertEqual(self.rule(frontier_before=D[1]), "session_context")
        self.assertEqual(self.rule(session_context=[]), "session_context")

    def test_unknown_variant_and_command_shape(self):
        ev = H.edit_resolution(self.ev, 3, variant="BOGUS")
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "command_shape")
        ev = H.deep(self.ev)
        ev[3]["request_basis"]["commands"][0]["extra"] = 1
        ev[3]["request_hash"] = H.request_hash(ev[3]["request_basis"])
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "command_shape")


class LateReference(unittest.TestCase):
    def test_late_after_a_declaration(self):
        ev = declared().events
        decl = {"kind": "DECLARE_MISSING", "seq": 2, "event_hash": ev[2]["event_hash"]}
        cases = {
            "not_a_declaration": {"kind": "DECLARE_MISSING", "seq": 1, "event_hash": ev[1]["event_hash"]},
            "wrong_hash": dict(decl, event_hash="0" * 64),
            "apply_without_the_day": {"kind": "APPLY", "seq": 1, "event_hash": ev[1]["event_hash"]},
            "forward": {"kind": "DECLARE_MISSING", "seq": 4, "event_hash": ev[4]["event_hash"]},
            "unknown_kind": dict(decl, kind="X"),
            "missing": None,
        }
        for name, ref in cases.items():
            with self.subTest(name):
                got = H.rule_of(self, H.rebuild(H.edit_resolution(ev, 4, missing_ref=ref)))
                self.assertIn(got, ("missing_ref", "command_shape"))
        self.assertEqual(H.rule_of(self, H.rebuild(H.edit_resolution(ev, 4, missing_ref=None))), "missing_ref")
        H.rebuild(H.edit_resolution(ev, 4, missing_ref=decl))

    def test_late_after_skipped_sessions(self):
        ev = skipped().events
        self.assertEqual(ev[2]["skipped_sessions"], [D[2]])
        ref = {"kind": "APPLY", "seq": 2, "event_hash": ev[2]["event_hash"]}
        V.validate_history(H.rebuild(H.edit_resolution(ev, 3, missing_ref=ref)))
        for name, fields in {
                "day_not_skipped_by_that_apply": dict(d=D[4]),
                "apply_of_the_day_exists": dict(d=D[3]),
                "earlier_apply_has_no_skip": dict(missing_ref={"kind": "APPLY", "seq": 1,
                                                               "event_hash": ev[1]["event_hash"]}),
                "wrong_hash": dict(missing_ref=dict(ref, event_hash="0" * 64)),
        }.items():
            with self.subTest(name):
                self.assertEqual(H.rule_of(self, H.rebuild(H.edit_resolution(ev, 3, **fields))), "missing_ref")

    def test_late_without_rows_or_with_an_applied_reference(self):
        ev = skipped().events
        self.assertEqual(H.rule_of(self, H.rebuild(H.edit_resolution(ev, 3, record_fingerprints=[]))), "fingerprints")
        ref = {"seq": 1, "event_hash": ev[1]["event_hash"], "fingerprint": H.fp_of_apply(ev[1])}
        self.assertEqual(H.rule_of(self, H.rebuild(H.edit_resolution(ev, 3, applied_ref=ref))), "applied_ref")

    def test_late_for_a_day_that_has_an_apply_in_the_view(self):
        ev = declared().events
        # D3 is applied; claim the declaration covers D3
        got = H.rule_of(self, H.rebuild(H.edit_resolution(ev, 4, d=D[3])))
        self.assertEqual(got, "missing_ref")


class CheckD(unittest.TestCase):
    def test_check_d_is_judged_against_the_creation_time_prefix(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        for name, cd, build in (("before_boundary", D[0], lambda cd: b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2, check_d=cd)),
                                ("before_latest_apply", D[1], lambda cd: b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2, check_d=cd))):
            with self.subTest(name):
                c = H.HB()
                c.apply(D[1], 27.0)
                c.apply(D[2], 28.0)
                c.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2, check_d=cd)
                H.expect_rule(self, "check_d", c.history())
        # the same record is fine when check_d equals the latest APPLY day
        c = H.HB()
        c.apply(D[1], 27.0)
        c.apply(D[2], 28.0)
        c.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2, check_d=D[2])
        c.apply(D[3], 31.0)                                                  # later APPLYs do not invalidate it
        c.check()

    def test_a_record_day_after_check_d(self):
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "qd", check_d=D[1])                                  # D2 > check_d == latest APPLY day
        H.expect_rule(self, "check_d", c.history())
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "qd", check_d=D[2])
        c.check()

    def test_a_malformed_check_d(self):
        ev = added().events
        e = H.deep(ev)
        e[3]["request_basis"]["check_d"] = "soon"
        e[3]["request_hash"] = H.request_hash(e[3]["request_basis"])
        H.expect_rule(self, "check_d", H.rebuild(e))


class Declarations(unittest.TestCase):
    def rule(self, ev, index, **fields):
        return H.rule_of(self, H.rebuild(H.edit_resolution(ev, index, **fields)))

    def test_frontier_from_the_start_boundary(self):
        b = H.HB()
        b.declare(D[1], "qd")                                                # frontier = start_after
        chk = b.check()
        self.assertEqual(b.events[1]["frontier_before"], D[0])
        self.assertEqual(b.events[1]["session_context"][0], b.events[0]["boundary_session"])
        self.assertEqual(chk.processing_after, D[0])
        self.assertEqual(self.rule(b.events, 1, frontier_before=D[1]), "declare_frontier")
        self.assertEqual(self.rule(b.events, 1, session_context=H.deep(b.events[1]["session_context"][::-1])),
                         "session_context")

    def test_frontier_from_the_last_apply(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "qd")
        self.assertEqual(b.events[2]["frontier_before"], D[1])
        self.assertEqual(b.events[2]["session_context"][0], b.events[1]["confirmed_inputs"]["session_context"][-2])
        b.check()
        ctx = H.deep(b.events[2]["session_context"])
        ctx[0]["close_at"] = "2030-01-01T00:00:00Z"
        self.assertEqual(self.rule(b.events, 2, session_context=ctx), "session_context")
        self.assertEqual(self.rule(b.events, 2, frontier_before=D[0]), "declare_frontier")

    def test_frontier_from_the_last_declaration_and_consecutive_declarations(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "qd1")
        b.declare(D[3], "qd2")
        self.assertEqual(b.events[3]["frontier_before"], D[2])
        self.assertEqual(b.events[3]["session_context"][0], b.events[2]["session_context"][1])
        b.check()
        self.assertEqual(self.rule(b.events, 3, frontier_before=D[1]), "declare_frontier")
        ctx = H.deep(b.events[3]["session_context"])
        ctx[0] = H.deep(b.events[1]["confirmed_inputs"]["session_context"][-2])      # the APPLY's session, not D2's
        self.assertEqual(self.rule(b.events, 3, session_context=ctx), "session_context")
        # one batch of two declarations: the second sees the first (same-batch frontier)
        c = H.HB()
        c.apply(D[1], 27.0)
        c.resolution([{"kind": "DECLARE_MISSING", "d": D[2]}, {"kind": "DECLARE_MISSING", "d": D[3]}], "qb")
        self.assertEqual(c.events[3]["frontier_before"], D[2])
        c.check()

    def test_frontier_after_a_restart_is_the_new_boundary(self):
        b = H.example_u()
        b.declare(D[4], "qd")
        self.assertEqual(b.events[4]["frontier_before"], D[3])
        self.assertEqual(b.events[4]["session_context"][0], b.events[3]["boundary_session"])
        b.check()

    def test_declaration_must_come_after_the_frontier_and_not_on_an_applied_day(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.declare(D[3], "qd")
        self.assertEqual(self.rule(b.events, 3, d=D[2]), "declare_applied")
        self.assertEqual(self.rule(b.events, 3, d=D[1]), "declare_applied")
        # a declaration on a day that is applied later in the view
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "qd")
        c.apply(D[2], 28.0)
        H.expect_rule(self, "declare_applied", c.history())
        # a day at or before the frontier
        b2 = H.HB()
        b2.apply(D[1], 27.0)
        b2.declare(D[2], "qd")
        ev = H.edit_resolution(b2.events, 2, d=D[1])
        got = H.rule_of(self, H.rebuild(ev))
        self.assertEqual(got, "declare_applied")

    def test_declaration_fields(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "qd")
        ref = {"kind": "APPLY", "seq": 1, "event_hash": b.events[1]["event_hash"]}
        applied = {"seq": 1, "event_hash": b.events[1]["event_hash"], "fingerprint": H.fp_of_apply(b.events[1])}
        # a reference inside the command is a shape error; on the record alone it disagrees with the command
        self.assertEqual(self.rule(b.events, 2, missing_ref=ref), "command_shape")
        self.assertEqual(self.rule(b.events, 2, applied_ref=applied), "command_shape")
        for key, value in (("missing_ref", ref), ("applied_ref", applied)):
            ev = H.deep(b.events)
            ev[2][key] = value
            H.expect_rule(self, "batch", H.rebuild(ev))
        self.assertEqual(self.rule(b.events, 2, variant="ADDED"), "command_shape")
        ctx = H.deep(b.events[2]["session_context"])
        ctx[1]["confirmed"] = False
        self.assertEqual(self.rule(b.events, 2, session_context=ctx), "session_context")
        self.assertEqual(self.rule(b.events, 2, session_context=ctx[:2]), "session_context")
        self.assertEqual(self.rule(b.events, 2, session_context=None), "session_context")


class Batches(unittest.TestCase):
    def three(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [fp("X%d" % i, D[1])], "applied": 1}
                      for i in range(3)], "qb")                              # 2, 3, 4
        return b

    def test_whole_batch_is_accepted(self):
        b = self.three()
        b.apply(D[2], 28.0)
        self.assertEqual([e["command_index"] for e in b.events[2:5]], [0, 1, 2])
        b.check()

    def test_missing_member_wrong_order_or_interruption(self):
        b = self.three()
        H.expect_rule(self, "batch", H.history_of(b.events[:4]))
        H.expect_rule(self, "batch", H.history_of(b.events[:3]))
        ev = H.deep(b.events)
        ev[2]["command_index"], ev[3]["command_index"] = 1, 0
        H.expect_rule(self, "batch", H.rebuild(ev))
        ev = H.deep(b.events)
        ev[3]["command_index"] = 2
        H.expect_rule(self, "batch", H.rebuild(ev))
        # an unrelated record between two members
        b2 = self.three()
        mid = H.deep(H.example_u().events[3])                                # a RESTART_UNKNOWN in the middle
        got = H.insert_record(b2.events, 3, mid)
        H.expect_rule(self, "batch", H.rebuild(got))
        mid = H.deep(b2.events[2])                                           # another ACK that starts its own batch
        mid["request_id"] = "other"
        got = H.insert_record(b2.events, 3, mid)
        H.expect_rule(self, "batch", H.rebuild(got))

    def test_members_must_share_the_request(self):
        b = self.three()
        for key, value in {"request_id": "other", "request_hash": "0" * 64, "requested_at": "2030-01-01T00:00:00Z",
                           "ledger_digest": "1" * 64, "command_count": 2}.items():
            with self.subTest(key):
                ev = H.deep(b.events)
                ev[3][key] = value
                H.expect_rule(self, "batch", H.rebuild(ev))
        ev = H.deep(b.events)
        ev[3]["request_basis"]["check_d"] = D[24]
        H.expect_rule(self, "batch", H.rebuild(ev))

    def test_a_member_must_match_its_command(self):
        b = self.three()
        for key, value in {"d": D[2], "variant": "CHANGED", "record_fingerprints": [fp("Z", D[1])],
                           "kind": "DECLARE_MISSING"}.items():
            with self.subTest(key):
                ev = H.deep(b.events)
                ev[3][key] = value
                got = H.rule_of(self, H.rebuild(ev))
                self.assertIn(got, ("batch", "record_keys"))
        ev = H.deep(b.events)
        ev[3]["applied_ref"] = None
        H.expect_rule(self, "batch", H.rebuild(ev))

    def test_request_hash_reason_and_time(self):
        ev = added().events
        e = H.deep(ev)
        e[3]["request_hash"] = "0" * 64
        H.expect_rule(self, "request_hash", H.rebuild(e))
        e = H.deep(ev)
        e[3]["request_basis"]["check_d"] = D[24]                              # content changed, hash not
        H.expect_rule(self, "request_hash", H.rebuild(e))
        e = H.deep(ev)
        e[3]["request_basis"]["reason_code"] = "MARK_SESSION_MISSING"
        e[3]["request_hash"] = H.request_hash(e[3]["request_basis"])
        H.expect_rule(self, "reason_code", H.rebuild(e))
        e = H.deep(ev)
        e[3]["reason_code"] = "MARK_SESSION_MISSING"
        H.expect_rule(self, "reason_code", H.rebuild(e))
        e = H.deep(ev)
        e[3]["requested_at"] = "2030-01-01T00:00:00Z"
        H.expect_rule(self, "requested_at", H.rebuild(e))
        e = H.deep(ev)
        e[3]["request_basis"]["requested_at"] = e[3]["requested_at"] = "yesterday"
        H.expect_rule(self, "requested_at", H.rebuild(e))
        e = H.deep(ev)
        e[3]["ledger_digest"] = "xyz"
        H.expect_rule(self, "ledger_digest", H.rebuild(e))
        e = H.deep(ev)
        e[3]["request_basis"]["extra"] = 1
        e[3]["request_hash"] = H.request_hash(e[3]["request_basis"])
        H.expect_rule(self, "request_basis", H.rebuild(e))

    def test_a_requested_time_only_change_is_the_same_request(self):
        a, b = added().events[3], H.deep(added().events[3])
        b["request_basis"]["requested_at"] = "2031-01-01T00:00:00Z"
        self.assertEqual(a["request_hash"], H.request_hash(b["request_basis"]))

    def test_mixed_batch_reason(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [fp("X1", D[1])], "applied": 1},
                      {"kind": "DECLARE_MISSING", "d": D[2]}], "qm")
        self.assertEqual(b.events[2]["request_basis"]["reason_code"], "RESOLUTION_BATCH")
        b.check()


class RequestIds(unittest.TestCase):
    def test_one_id_one_batch_in_a_view(self):
        b = added()
        b.ack("CHANGED", D[2], [fp("X2", D[2])], "qa", applied=2)             # the same id again
        H.expect_rule(self, "request_id", b.history())

    def test_the_ids_of_restart_and_restore_share_the_namespace(self):
        b = added()
        b.restart(D[3], "qa")
        H.expect_rule(self, "request_id", b.history())
        c = added()
        c.restore(3, {4: "REAPPLY"}, "qa")                                   # the ACK qa stays on the final chain
        H.expect_rule(self, "request_id", c.history())
        d = added()
        d.restore(2, {3: "DROP", 4: "REAPPLY"}, "qa")                        # qa is superseded: its id is free again
        d.check()

    def test_invalid_ids(self):
        for bad in ("", "a b", "https://x.invalid/p", "é" * 3, " lead"):
            with self.subTest(bad):
                ev = H.deep(added().events)
                ev[3]["request_id"] = bad
                ev[3]["request_basis"]["request_id"] = bad
                ev[3]["request_hash"] = H.request_hash(ev[3]["request_basis"])
                H.expect_rule(self, "request_id", H.rebuild(ev))

    def test_the_same_id_on_a_superseded_and_a_replayed_record_is_allowed(self):
        ev = H.example_r1().events
        self.assertEqual(ev[5]["request_id"], ev[9]["request_id"])
        V.validate_history(H.history_of(ev))


class OriginAndReplayOf(unittest.TestCase):
    def test_a_new_history_has_no_origin(self):
        ev = H.deep(added().events)
        ev[3]["origin"] = {"resolution_seq": 1, "resolution_hash": "0" * 64, "source_head_seq": 2,
                           "source_head_hash": "1" * 64}
        H.expect_rule(self, "origin", H.rebuild(ev))

    def test_replay_of_outside_a_replay(self):
        ev = H.deep(added().events)
        ev[3]["replay_of"] = {"seq": 2, "event_hash": ev[2]["event_hash"]}
        H.expect_rule(self, "replay_of", H.rebuild(ev))
        ev = H.deep(added().events)
        ev[3]["replay_of"] = "x"
        H.expect_rule(self, "replay_of", H.rebuild(ev))


if __name__ == "__main__":
    unittest.main()
