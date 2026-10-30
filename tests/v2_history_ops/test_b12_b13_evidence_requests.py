"""B2-12 (evidence of new resolutions, design 12.5) and B2-13 (the request id against the whole physical history,
design 6.5)."""
import datetime
import unittest
from unittest import mock

import ho_helpers as T
import v2_history_ops as O
import v2_history_ops.plan as OP
from v2_history_ops.chain import Chain

H, D, P, RH, V = T.H, T.D, T.P, T.RH, T.V
RESOLUTION_INVALID = "resolution_invalid"


class Evidence(unittest.TestCase):
    def one_day(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        return b.history(), b.w

    def test_1_row_removed_and_added_in_both_orders(self):
        h, w = self.one_day()
        b1 = P.obs("b", D[1], 27.0)                                  # the same value, re-typed under another id
        led = [b1]
        e = T.refusal(O.project_history_ledger, h, w.sessions, led, D[2])
        self.assertEqual(e.code, "ledger_mismatch")
        rr = T.cmd("ACK", "ROW_REMOVED", D[1], [], applied=T.aref(h, 1))
        ad = T.ack_cmd(h, "ADDED", D[1], [T.fp(b1)], 1)
        results = []
        for order in ([rr, ad], [ad, rr]):
            _plan, res = T.run_plan(h, order, w.sessions, led, D[2], "q1")
            self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
            self.assertEqual(res.ledger.excluded_fingerprints, [T.fp(b1)])
            self.assertEqual(len(res.ledger.supplemented), 1)             # a1 is supplemented once
            results.append(res.ledger.effective_digest)
        self.assertEqual(results[0], results[1])

    def test_2_changed_and_added_in_both_orders(self):
        h, w = self.one_day()
        a1p = P.obs("R-" + D[1], D[1], 28.0)
        c1 = P.obs("c", D[1], 29.0)
        led = [a1p, c1]
        self.assertEqual(T.refusal(O.project_history_ledger, h, w.sessions, led, D[2]).code, "decision_conflict")
        ch = T.ack_cmd(h, "CHANGED", D[1], [T.fp(a1p)], 1)
        ad = T.ack_cmd(h, "ADDED", D[1], [T.fp(c1)], 1)
        for order in ([ch, ad], [ad, ch]):
            _plan, res = T.run_plan(h, order, w.sessions, led, D[2], "q1")
            self.assertEqual(sorted(res.ledger.excluded_fingerprints), sorted([T.fp(a1p), T.fp(c1)]))
            self.assertEqual(len(res.ledger.supplemented), 1)

    def test_3_a_day_with_a_valid_decision_cannot_be_declared_n04(self):
        h, w = self.one_day()
        extra = P.obs("v2", D[2], 30.0)
        led = list(w.ledger) + [extra]
        for fps in ([], [T.fp(extra)]):
            self.assertEqual(T.err(T.plan_for, h, [T.decl_cmd(D[2], fps)], w.sessions, led, D[3], "q1"),
                             (RESOLUTION_INVALID, "commands", "declare_valid_decision"))

    def test_4_version_selection_is_not_bypassed_by_a_late(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 31.0)                                          # D2 is skipped
        h, w = b.history(), b.w
        x1, x2 = P.obs("x", D[2], 22.0), P.obs("x", D[2], 23.0)      # two versions of one id, both targeting D2
        led = list(w.ledger) + [x1, x2]
        one = T.late_cmd(D[2], [T.fp(x1)], T.mref_apply(h, 2))
        self.assertEqual(T.err(T.plan_for, h, [one], w.sessions, led, D[4], "q1"),
                         (RESOLUTION_INVALID, "commands", "version_selection"))
        both = T.late_cmd(D[2], [T.fp(x1), T.fp(x2)], T.mref_apply(h, 2))
        self.assertEqual(T.plan_for(h, [both], w.sessions, led, D[4], "q1").status, "READY")

    def test_5_exclude_applied_and_ack_after_check_d(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 31.0)
        h, w = b.history(), b.w
        x1 = P.obs("x", D[2], 22.0)
        led = list(w.ledger) + [x1]
        fixed = T.aref(h, 1)["fingerprint"]                          # a fingerprint the APPLY #1 fixed
        self.assertEqual(T.err(T.plan_for, h, [T.late_cmd(D[2], [fixed], T.mref_apply(h, 2))], w.sessions, led,
                               D[4], "q1"), (RESOLUTION_INVALID, "commands", "exclude_applied"))
        ahead = T.ack_cmd(h, "ADDED", D[4], [T.fp(x1)], 2)
        self.assertEqual(T.err(T.plan_for, h, [ahead], w.sessions, led, D[3], "q1"),
                         (RESOLUTION_INVALID, "commands", "ack_evidence"))

    def test_6_late_references_and_declaration_frontier(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 31.0)                                          # D2 skipped by APPLY #2
        b.declare(D[4], "q9")                                        # #3, D4 declared; D5 follows
        h, w = b.history(), b.w
        x1, y1 = P.obs("x", D[2], 22.0), P.obs("y", D[4], 24.0)
        led = list(w.ledger) + [x1, y1]
        # the APPLY form and the declaration form are both accepted (each against a ledger with its own late row)
        late_apply = T.late_cmd(D[2], [T.fp(x1)], T.mref_apply(h, 2))
        late_decl = T.late_cmd(D[4], [T.fp(y1)], T.mref_decl(h, 3))
        self.assertEqual(T.plan_for(h, [late_apply], w.sessions, list(w.ledger) + [x1], D[5], "q1").status, "READY")
        self.assertEqual(T.plan_for(h, [late_decl], w.sessions, list(w.ledger) + [y1], D[5], "q2").status, "READY")
        self.assertEqual(T.plan_for(h, [late_apply, late_decl], w.sessions, led, D[5], "q4").status, "READY")
        # a reference to a day that is not in the skipped list / not that declaration's day
        wrong = T.late_cmd(D[4], [T.fp(y1)], T.mref_decl(h, 3))
        wrong["d"] = D[2]
        self.assertEqual(T.err(T.plan_for, h, [dict(wrong, record_fingerprints=[T.fp(x1)])], w.sessions, led, D[5],
                               "q3"), (RESOLUTION_INVALID, "commands", "late_missing_ref"))
        # a declaration in the same request cannot be the reference of a LATE (it is not in effect yet)
        b2 = H.HB()
        b2.apply(D[1], 27.0)
        h2, w2 = b2.history(), b2.w
        bogus = {"kind": "DECLARE_MISSING", "seq": 2, "event_hash": "a" * 64}
        self.assertEqual(T.err(T.plan_for, h2, [T.decl_cmd(D[2]), T.late_cmd(D[2], [], bogus)], w2.sessions,
                               w2.ledger, D[4], "q1"), (RESOLUTION_INVALID, "commands", "late_missing_ref"))
        # consecutive declarations: the frontier moves; D3 alone (skipping D2) is a frontier error
        plan = T.plan_for(h2, [T.decl_cmd(D[2]), T.decl_cmd(D[3])], w2.sessions, w2.ledger, D[4], "q1")
        evs = plan.basis["candidate_history"]["events"]
        self.assertEqual([(e["kind"], e["d"], e["frontier_before"]) for e in evs[-2:]],
                         [("DECLARE_MISSING", D[2], D[1]), ("DECLARE_MISSING", D[3], D[2])])
        self.assertEqual(T.err(T.plan_for, h2, [T.decl_cmd(D[3])], w2.sessions, w2.ledger, D[4], "q1"),
                         (RESOLUTION_INVALID, "commands", "declare_frontier"))

    def test_evidence_goes_through_check_commands(self):
        h, w = self.one_day()
        x = P.obs("x", D[1], 22.0)
        led = list(w.ledger) + [x]
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
        with mock.patch.object(OP, "check_commands", wraps=OP.check_commands) as spy:
            T.plan_for(h, cmds, w.sessions, led, D[2], "q1")
        self.assertEqual(spy.call_count, 1)
        ctx, existing, commands = spy.call_args[0]
        self.assertEqual(type(ctx).__name__, "LedgerContext")
        self.assertEqual((existing, [c["kind"] for c in commands]), ([], ["ACK"]))
        # a refusal of the evidence comes from that function: nothing else is consulted first
        with mock.patch.object(OP, "check_commands", side_effect=RuntimeError("sentinel")):
            with self.assertRaises(RuntimeError):
                T.plan_for(h, cmds, w.sessions, led, D[2], "q1")


class RequestIds(unittest.TestCase):
    def native(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        h, w = b.history(), b.w
        x = P.obs("x", D[1], 22.0)
        led = list(w.ledger) + [x]
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
        _p, res = T.run_plan(h, cmds, w.sessions, led, D[2], "q1")
        return T.extend(h, res), w, led, x

    def test_new_id_is_ready(self):
        h, w, led, x = self.native()
        y = P.obs("y", D[1], 21.0)
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(y)], 1)]
        self.assertEqual(T.plan_for(h, cmds, w.sessions, led + [y], D[2], "q2").status, "READY")

    def test_same_id_and_content_is_no_change_even_with_another_requested_at(self):
        h, w, led, x = self.native()
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
        for when in (T.WHEN, T.WHEN + datetime.timedelta(minutes=5)):
            plan = T.plan_for(h, cmds, w.sessions, led, D[2], "q1", when=when)
            self.assertEqual((plan.status, plan.basis["candidate_digest"], plan.basis["history_digest"]),
                             ("NO_CHANGE", h.digest, h.digest))
            res = O.confirm_history_resolution_plan(plan, plan.plan_hash, h, w.sessions, led)
            self.assertEqual((res.status, res.batch), ("NO_CHANGE", None))

    def test_same_id_with_other_content_conflicts(self):
        h, w, led, x = self.native()
        y = P.obs("y", D[1], 21.0)
        other = [T.ack_cmd(h, "ADDED", D[1], [T.fp(y)], 1)]
        variants = [(other, D[2]),                                           # other rows
                    ([T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)], D[3]),      # other check_d
                    ([T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1), T.decl_cmd(D[2])], D[2])]   # one more command
        for cmds, check_d in variants:
            with self.subTest(check_d=check_d, n=len(cmds)):
                e = T.refusal(T.plan_for, h, cmds, w.sessions, led + [y], check_d, "q1")
                self.assertEqual((e.code, e.field), ("history_request_conflict", "request_id"))

    def test_a_request_of_several_commands(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        h, w = b.history(), b.w
        cmds = [T.decl_cmd(D[2]), T.decl_cmd(D[3])]
        _p, res = T.run_plan(h, cmds, w.sessions, w.ledger, D[4], "q1")
        self.assertEqual([r["command_index"] for r in res.batch.body["records"]], [0, 1])
        h2 = T.extend(h, res)
        self.assertEqual(T.plan_for(h2, cmds, w.sessions, w.ledger, D[4], "q1").status, "NO_CHANGE")
        # only the first command of the same id: another content
        e = T.refusal(T.plan_for, h2, cmds[:1], w.sessions, w.ledger, D[4], "q1")
        self.assertEqual(e.code, "history_request_conflict")

    def test_replayed_request_same_content_is_no_change_and_other_content_conflicts(self):
        b = H.example_r1()                                              # RESTORE#2 replayed the ACK q2 as #9
        h, w = b.history(), b.w
        z3 = P.obs("B3", D[3], 41.0, hour=21)
        led = list(w.ledger) + [z3]
        orig = b.events[5]
        self.assertEqual(O.read_effective(h).resolutions[0]["source"], "REPLAYED")
        basis = orig["request_basis"]
        same = [dict(basis["commands"][0])]
        plan = O.prepare_history_resolution_plan(h, same, w.sessions, led, basis["check_d"], "q2",
                                                 basis["reason_code"], T.WHEN)
        self.assertEqual(plan.status, "NO_CHANGE")
        e = T.refusal(O.prepare_history_resolution_plan, h, same, w.sessions, led, D[10], "q2",
                      basis["reason_code"], T.WHEN)
        self.assertEqual(e.code, "history_request_conflict")

    def test_migrated_ids_conflict_whether_or_not_the_hash_matches(self):
        hb, (w, snap, rs, ledger, cd) = H.example_m()
        h = hb.history()
        chain = Chain(h, V.validate_history(h))
        groups = chain.request_groups()
        migrated = [g for g in groups if g["source"] == "MIGRATED"]
        self.assertEqual([g["request_id"] for g in migrated], ["q1", "q2", "q3"])
        # the first one: the original basis points to the APPLY that v1 and v2 number the same way; its stored
        # hash is the hash a new request with that basis would have
        q1 = migrated[0]
        self.assertEqual(h.events[2]["request_basis"]["commands"][0]["applied_ref"]["seq"], 1)
        e = T.refusal(OP.request_status, groups, "q1", q1["request_hash"])
        self.assertEqual(e.code, "history_request_conflict")
        e = T.refusal(OP.request_status, groups, "q1", "f" * 64)
        self.assertEqual(e.code, "history_request_conflict")
        # through the public function (another basis, so another hash)
        x = P.obs("x", D[1], 22.0)
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
        e = T.refusal(T.plan_for, h, cmds, w.sessions, list(ledger) + [x], cd, "q1")
        self.assertEqual((e.code, e.field), ("history_request_conflict", "request_id"))

    def test_retired_only_ids_and_restart_restore_migration_ids(self):
        b = H.example_r()
        h, w = b.history(), b.w
        z3 = P.obs("B3", D[3], 41.0, hour=21)
        led = list(w.ledger) + [z3]
        cmds = [T.ack_cmd(h, "ADDED", D[3], [T.fp(z3)], 19)]
        for rid, what in (("q2", "ACK that RESTORE#3 dropped (retired only)"), ("q1", "RESTART_UNKNOWN"),
                          ("q4", "RESTORE#1"), ("q6", "RESTORE#3")):
            with self.subTest(what):
                e = T.refusal(T.plan_for, h, cmds, w.sessions, led, D[6], rid)
                self.assertEqual((e.code, e.field), ("history_request_conflict", "request_id"))
        self.assertEqual(T.plan_for(h, cmds, w.sessions, led, D[6], "q7").status, "READY")
        hb, (wm, _snap, _rs, ledger, cd) = H.example_m()
        hm = hb.history()
        self.assertEqual(hm.events[7]["request_id"], "mig-1")
        x = P.obs("x", D[1], 22.0)
        e = T.refusal(T.plan_for, hm, [T.ack_cmd(hm, "ADDED", D[1], [T.fp(x)], 1)], wm.sessions,
                      list(ledger) + [x], cd, "mig-1")
        self.assertEqual(e.code, "history_request_conflict")


if __name__ == "__main__":
    unittest.main()
