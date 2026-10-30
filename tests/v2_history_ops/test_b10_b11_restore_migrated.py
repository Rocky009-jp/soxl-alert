"""B2-10 (after a restore, examples R and R-b) and B2-11 (a migrated history, example M)."""
import unittest

import ho_helpers as T
import v2_history_ops as O
from v2_persistence.codec import encode_snapshot, sha256_text

H, D, P, RH, V = T.H, T.D, T.P, T.RH, T.V
Z3 = P.obs("B3", D[3], 41.0, hour=21)           # the row that the ACK #5 of example R excludes


class ExampleR(unittest.TestCase):
    """Design 12.4 steps 1-4. Request ids q1..q6 of example R are used; q7 is a new one. Nothing in h_helpers (the
    example, its request ids, its id checks) is changed or weakened here."""

    def setUp(self):
        self.b = H.example_r()
        self.h, self.w = self.b.history(), self.b.w
        self.led = list(self.w.ledger) + [Z3]

    def prefix_after_restore_2(self):
        """Example R up to and including RESTORE#2 (the replayed ACK #9 is effective)."""
        b = H.example_r1()
        return b.history(), b.w

    def test_1_after_restore_2_the_replayed_ack_is_in_effect(self):
        h, w = self.prefix_after_restore_2()
        v = O.read_effective(h)
        q2 = [r for r in v.resolutions if r["request_id"] == "q2"]
        self.assertEqual([(r["seq"], r["source"]) for r in q2], [(9, "REPLAYED")])
        self.assertEqual(q2[0]["applied_ref"]["seq"], 8)                # the mapped APPLY, never #4
        led = list(w.ledger) + [Z3]
        got = O.project_history_ledger(h, w.sessions, led, D[4])
        self.assertEqual(got.excluded_fingerprints, [T.fp(Z3)])

    def test_2_after_restore_3_the_retired_ack_is_not_used(self):
        v = O.read_effective(self.h)
        self.assertEqual(v.resolutions, [])
        self.assertEqual(v.effective_seqs, [0, 1, 2, 18, 19, 20, 21, 22])
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, self.led, D[6])
        self.assertEqual((e.code, e.field), ("decision_conflict", "observation_role"))
        # the same call on the prefix (#9 effective) passes: the difference is only the effective chain
        h2, w2 = self.prefix_after_restore_2()
        ok = O.project_history_ledger(h2, w2.sessions, list(w2.ledger) + [Z3], D[4])
        self.assertEqual(ok.excluded_fingerprints, [T.fp(Z3)])

    def test_3_a_new_request_q7_is_ready_and_used_ids_conflict(self):
        cmds = [T.ack_cmd(self.h, "ADDED", D[3], [T.fp(Z3)], 19)]
        plan, res = T.run_plan(self.h, cmds, self.w.sessions, self.led, D[6], "q7")
        self.assertEqual((plan.status, res.status), ("READY", "CONFIRMED_IN_MEMORY"))
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["seq"], rec["parent_seq"], rec["kind"], rec["origin"], rec["replay_of"]),
                         (23, 22, "ACK", None, None))
        self.assertEqual(rec["applied_ref"]["seq"], 19)
        self.assertEqual(res.ledger.excluded_fingerprints, [T.fp(Z3)])
        h2 = T.extend(self.h, res)
        self.assertEqual(h2.head_seq, 23)
        # the same command with the used ids: q4 (RESTORE#1), q2 (the dropped ACK) and the others
        for rid in ("q4", "q2", "q1", "q3", "q5", "q6"):
            with self.subTest(rid):
                e = T.refusal(T.plan_for, self.h, cmds, self.w.sessions, self.led, D[6], rid)
                self.assertEqual((e.code, e.field), ("history_request_conflict", "request_id"))
        # retired APPLYs (#4 and #8) cannot be named as the evidence
        for old in (4, 8):
            with self.subTest(old):
                ref = dict(T.aref(self.h, 19), seq=old, event_hash=self.h.events[old]["event_hash"])
                bad = [T.cmd("ACK", "ADDED", D[3], [T.fp(Z3)], applied=ref)]
                self.assertEqual(T.err(T.plan_for, self.h, bad, self.w.sessions, self.led, D[6], "q7"),
                                 ("resolution_invalid", "commands", "ack_evidence"))

    def test_4_the_day_after_a_restore(self):
        led = list(self.w.ledger) + [P.obs("R7", D[7], 31.0)]
        out = O.prepare_history_day(self.h, D[7], self.w.series, self.w.sessions, led)
        rec = out.batch.body["records"][0]
        self.assertEqual((out.status, rec["seq"], rec["parent_seq"]), ("PREPARED", 23, 22))
        # after an ACK has been appended the parent is the ACK
        cmds = [T.ack_cmd(self.h, "ADDED", D[3], [T.fp(Z3)], 19)]
        _plan, res = T.run_plan(self.h, cmds, self.w.sessions, self.led, D[6], "q7")
        h2 = T.extend(self.h, res)
        led2 = self.led + [P.obs("R7", D[7], 31.0)]
        out2 = O.prepare_history_day(h2, D[7], self.w.series, self.w.sessions, led2)
        self.assertEqual((out2.status, out2.batch.body["records"][0]["parent_seq"]), ("PREPARED", 23))

    def test_every_call_runs_the_history_checker_first(self):
        broken = self.h.to_dict()
        broken["events"][3]["event_hash"] = "0" * 64                    # a retired record's hash is still checked
        bad = V.History.from_dict(broken)
        e = T.refusal(O.read_effective, bad)
        self.assertEqual(e.code, "history_invalid")


class ExampleRB(unittest.TestCase):
    """Design 12.4 steps 5-6."""

    def setUp(self):
        self.b = H.example_rb()
        self.h, self.w = self.b.history(), self.b.w
        self.late = P.obs("L3", D[3], 22.0)
        self.led = list(self.w.ledger) + [self.late]

    def test_5_the_replayed_declaration_is_8_not_4(self):
        v = O.read_effective(self.h)
        self.assertEqual(v.effective_seqs, [0, 1, 6, 7, 8, 9])
        decl = [r for r in v.resolutions if r["kind"] == "DECLARE_MISSING"]
        self.assertEqual([(r["seq"], r["source"]) for r in decl], [(8, "REPLAYED")])
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, self.led, D[4])
        self.assertEqual((e.code, e.detail), ("late_observation", D[3]))
        cmd8 = T.late_cmd(D[3], [T.fp(self.late)], T.mref_decl(self.h, 8))
        plan, res = T.run_plan(self.h, [cmd8], self.w.sessions, self.led, D[4], "q9")
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(res.batch.body["records"][0]["missing_ref"]["seq"], 8)
        # the retired #4 is not a declaration in effect
        cmd4 = T.late_cmd(D[3], [T.fp(self.late)], T.mref_decl(self.h, 4))
        self.assertEqual(T.err(T.plan_for, self.h, [cmd4], self.w.sessions, self.led, D[4], "q9"),
                         ("resolution_invalid", "commands", "late_missing_ref"))
        # the APPLY form (D3 is skipped by #9)
        capply = T.late_cmd(D[3], [T.fp(self.late)], T.mref_apply(self.h, 9))
        _p, res2 = T.run_plan(self.h, [capply], self.w.sessions, self.led, D[4], "q9")
        self.assertEqual(res2.batch.body["records"][0]["missing_ref"]["kind"], "APPLY")

    def test_6_a_retired_record_is_still_checked_by_the_history_checker(self):
        broken = self.h.to_dict()
        broken["events"][4]["state_after"] = dict(broken["events"][4]["state_after"])
        broken["events"][4]["event_hash"] = "1" * 64
        bad = V.History.from_dict(broken)
        for call in (lambda: O.read_effective(bad),
                     lambda: O.project_history_ledger(bad, self.w.sessions, self.led, D[4]),
                     lambda: T.day(bad, D[5], self.w)):
            self.assertEqual(T.refusal(call).code, "history_invalid")


class ExampleM(unittest.TestCase):
    """Design 12.2."""

    def setUp(self):
        self.hb, (self.w, self.snap, self.rs, self.ledger, self.cd) = H.example_m()
        self.h = self.hb.history()
        self.base = self.w.ledger

    def test_layout_and_the_unchanged_projection(self):
        v = O.read_effective(self.h)
        self.assertEqual([e["kind"] for e in self.hb.events],
                         ["GENESIS", "APPLY", "ACK", "APPLY", "DECLARE_MISSING", "APPLY", "ACK", "SCHEMA_MIGRATION"])
        self.assertEqual([a["seq"] for a in v.applies], [1, 3, 5])
        self.assertEqual({r["source"] for r in v.resolutions}, {"MIGRATED"})
        got = O.project_history_ledger(self.h, self.w.sessions, self.ledger, self.cd)
        self.assertEqual(len(got.excluded_fingerprints), 2)

    def test_1_new_changed_ack_uses_the_v2_seq(self):
        changed = P.obs("R2", D[2], 33.0)                                   # the same id as the APPLY D2 row
        ledger = [r for r in self.ledger if r["record_id"] != "R2"] + [changed]
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, ledger, D[5])
        self.assertIn(e.code, ("record_id_conflict", "ledger_mismatch"))
        cmds = [T.ack_cmd(self.h, "CHANGED", D[2], [T.fp(changed)], 3)]    # v2 seq 3, not the v1 seq 2
        plan, res = T.run_plan(self.h, cmds, self.w.sessions, ledger, D[5], "q4")
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["seq"], rec["parent_seq"], rec["kind"], rec["origin"]), (8, 7, "ACK", None))
        self.assertEqual(res.ledger.supplemented, [rec["applied_ref"]])

    def test_2_a_v1_seq_is_not_an_apply(self):
        changed = P.obs("R2", D[2], 33.0)
        ledger = [r for r in self.ledger if r["record_id"] != "R2"] + [changed]
        good = T.aref(self.h, 3)
        bad_ref = dict(good, seq=2, event_hash=self.snap.events[2]["event_hash"])     # v1 numbering and hash
        cmd = T.cmd("ACK", "CHANGED", D[2], [T.fp(changed)], applied=bad_ref)
        self.assertEqual(T.err(T.plan_for, self.h, [cmd], self.w.sessions, ledger, D[5], "q4"),
                         ("resolution_invalid", "commands", "ack_evidence"))
        # the v1 hash with the right v2 seq is refused as well
        cmd = T.cmd("ACK", "CHANGED", D[2], [T.fp(changed)],
                    applied=dict(good, event_hash=self.snap.events[2]["event_hash"]))
        self.assertEqual(T.err(T.plan_for, self.h, [cmd], self.w.sessions, ledger, D[5], "q4"),
                         ("resolution_invalid", "commands", "ack_evidence"))

    def test_3_new_declaration_and_the_next_day(self):
        plan = T.plan_for(self.h, [T.decl_cmd(D[5])], self.w.sessions, self.base, D[5], "q5")
        rec = plan.basis["candidate_history"]["events"][-1]
        self.assertEqual((rec["kind"], rec["d"], rec["seq"], rec["frontier_before"]), ("DECLARE_MISSING", D[5], 8, D[4]))
        _p, res = T.run_plan(self.h, [T.decl_cmd(D[5])], self.w.sessions, self.base, D[5], "q5")
        h2 = T.extend(self.h, res)
        led = list(self.base) + [P.obs("R6", D[6], 31.0)]
        out = O.prepare_history_day(h2, D[6], self.w.series, self.w.sessions, led)
        self.assertEqual(out.status, "PREPARED")
        rec6 = out.batch.body["records"][0]
        self.assertEqual((rec6["parent_seq"], rec6["skipped_sessions"]), (8, [D[5]]))

    def test_4_migrated_sources_of_a_candidate(self):
        changed = P.obs("R2", D[2], 33.0)
        ledger = [r for r in self.ledger if r["record_id"] != "R2"] + [changed]
        cmds = [T.ack_cmd(self.h, "CHANGED", D[2], [T.fp(changed)], 3)]
        _plan, res = T.run_plan(self.h, cmds, self.w.sessions, ledger, D[5], "q4")
        snap, rs = V.migrated_sources(res.history)
        self.assertEqual(snap, self.snap)
        self.assertEqual(rs, self.rs)
        self.assertEqual(rs.digest, self.rs.digest)
        self.assertEqual(sha256_text(encode_snapshot(snap)), self.hb.events[7]["source"]["snapshot_digest"])
        # a day appended after the migration does not change the sources either
        h2 = T.extend(self.h, T.day(self.h, D[5], self.w, list(self.base) + [P.obs("R5", D[5], 31.0)]))
        snap2, rs2 = V.migrated_sources(h2)
        self.assertEqual((snap2, rs2.digest), (self.snap, self.rs.digest))

    def test_5_the_migrated_request_ids_are_never_new_requests(self):
        changed = P.obs("R2", D[2], 33.0)
        ledger = [r for r in self.ledger if r["record_id"] != "R2"] + [changed]
        for rid in ("q1", "q2", "q3"):
            with self.subTest(rid):
                cmds = [T.ack_cmd(self.h, "CHANGED", D[2], [T.fp(changed)], 3)]
                e = T.refusal(T.plan_for, self.h, cmds, self.w.sessions, ledger, D[5], rid)
                self.assertEqual((e.code, e.field), ("history_request_conflict", "request_id"))


if __name__ == "__main__":
    unittest.main()
