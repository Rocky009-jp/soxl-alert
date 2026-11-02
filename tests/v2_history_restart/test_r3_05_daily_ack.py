"""B3-12 (the candidate handed to the existing B-2 day preparation) and B3-13 (ACK / declarations after a restart).
These are integration checks with the existing B-2 functions; no daily or ACK logic is written in the new package."""
import unittest

import r3_helpers as R

T, H, X, D, P, V, O = R.T, R.H, R.X, R.D, R.P, R.V, R.O


def day(history, d, w, ledger):
    return O.prepare_history_day(history, d, w.series, w.sessions, ledger)


class DailyAfterTheRestart(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()                       # GENESIS D0, APPLY D1 (27), APPLY D2 (28)
        self.w = self.b.w
        self.plan, self.res = R.run(self.b.history(), self.w, D[3], D[3], "r1")
        self.cand = self.res.history

    def test_days_up_to_the_boundary_are_refused(self):
        for d in (D[1], D[2], D[3]):
            out = T.outcome(day, self.cand, d, self.w, self.w.ledger)
            self.assertEqual(out[:3], ("err", "target_not_after_boundary", "target_session_date"), d)

    def test_the_three_f_and_g_bands_start_from_the_unknown_state_without_a_gap(self):
        expected = {31.0: ("UNKNOWN", 1, "FALSE"), 27.0: ("UNKNOWN", 0, "TRUE"), 20.0: ("FALSE", 0, "FALSE")}
        for value, (armed, streak, prev_normal) in expected.items():
            ledger = self.w.ledger + [P.obs("R4", D[4], value)]
            res = day(self.cand, D[4], self.w, ledger)
            self.assertEqual(res.status, "PREPARED", value)
            rec = res.batch.body["records"][0]
            self.assertEqual((rec["state_after"]["armed"], rec["state_after"]["streak"],
                              rec["state_after"]["prev_normal_raw"]), (armed, streak, prev_normal), value)
            self.assertFalse(rec["transition_result"]["gap"], value)
            self.assertEqual(rec["state_after"]["base"], H.initial_state())     # the record before is the restart
            self.assertEqual((rec["parent_seq"], rec["parent_hash"]), (self.cand.head_seq, self.cand.head_hash))
            self.assertEqual(rec["skipped_sessions"], [])

    def test_a_missing_day_is_skipped_later_without_a_gap_and_a_late_decision_stops(self):
        ledger = self.w.ledger + [P.obs("R5", D[5], 31.0)]
        self.assertEqual(day(self.cand, D[4], self.w, ledger).status, "NO_COMMIT")
        res = day(self.cand, D[5], self.w, ledger)
        self.assertEqual(res.status, "PREPARED")
        rec = res.batch.body["records"][0]
        self.assertEqual(rec["skipped_sessions"], [D[4]])
        self.assertFalse(rec["transition_result"]["gap"])
        cand2 = O.check_append_batch(self.cand, res.batch)
        late = ledger + [P.obs("L4", D[4], 33.0)]
        self.assertEqual(T.outcome(day, cand2, D[6], self.w, late)[:3], ("err", "late_observation", "observations"))
        self.assertEqual(day(cand2, D[5], self.w, ledger).status, "ALREADY_APPLIED")

    def test_the_new_package_holds_no_market_rule(self):
        import ast
        import os
        pkg = os.path.join(R.ROOT, "v2_history_restart")
        for name in sorted(os.listdir(pkg)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(pkg, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    # only tuple positions, "+ 1" and the 12-character hash prefix of a repr; no threshold, no ratio
                    self.assertIsInstance(node.value, int, name)
                    self.assertIn(node.value, tuple(range(8)) + (12,), "%s holds the number %r" % (name, node.value))
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("v2_core.engine", "v2_core.state_rules", "v2_core.rules",
                                                             "v2_core.indicators")), name)


class AckAndDeclareAfterTheRestart(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.w = self.b.w
        self.plan, self.res = R.run(self.b.history(), self.w, D[3], D[3], "r1")
        self.cand = self.res.history

    def test_no_new_ack_or_declaration_can_use_the_restart_day_as_check_d(self):
        out = T.outcome(T.plan_for, self.cand, [T.decl_cmd(D[3])], self.w.sessions, self.w.ledger, D[3], "d1")
        self.assertEqual(out[:3], ("err", "target_not_after_boundary", "target_session_date"))

    def test_with_a_later_confirmed_check_d_the_first_declaration_starts_at_the_resume_day(self):
        self.assertEqual(T.outcome(T.plan_for, self.cand, [T.decl_cmd(D[4])], self.w.sessions, self.w.ledger, D[6],
                                   "d1")[0], "ok")
        _plan, res = T.run_plan(self.cand, [T.decl_cmd(D[4])], self.w.sessions, self.w.ledger, D[6], "d1")
        after = T.extend(self.cand, res)
        rec = after.events[-1]
        self.assertEqual(rec["kind"], "DECLARE_MISSING")
        self.assertEqual(rec["frontier_before"], D[3])
        self.assertEqual(V.validate_history(after).current_boundary.after, D[3])      # the boundary did not move
        self.assertEqual(O.read_effective(after).segments[-1]["declare_seqs"], [rec["seq"]])

    def test_old_segment_applies_skipped_days_and_declarations_are_still_checked(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 29.0)                              # skips D2
        b.declare(D[4], "q1")
        h, w = b.history(), b.w
        plan, res = R.run(h, w, D[6], D[6], "r1")
        cand = res.history
        late2 = P.obs("L2", D[2], 22.0)
        late4 = P.obs("L4", D[4], 23.0)
        # the old skipped day and the old declared day still stop later work when their rows arrive ...
        self.assertEqual(T.outcome(day, cand, D[7], w, w.ledger + [late2])[:3], ("err", "late_observation", "observations"))
        self.assertEqual(T.outcome(day, cand, D[7], w, w.ledger + [late4])[:3], ("err", "late_observation", "observations"))
        # ... and an explicit LATE acknowledgement of the old skipped day is accepted on the candidate
        cmds = [T.late_cmd(D[2], [T.fp(late2)], T.mref_apply(cand, 2))]
        _p, ack = T.run_plan(cand, cmds, w.sessions, w.ledger + [late2], D[7], "a1")
        after = T.extend(cand, ack)
        self.assertEqual(after.events[-1]["kind"], "ACK")
        self.assertEqual(after.events[-1]["variant"], "LATE")
        self.assertEqual(day(after, D[7], w, w.ledger + [late2]).status in ("NO_COMMIT", "PREPARED"), True)

    def test_after_an_acknowledgement_the_restart_can_be_planned_on_the_acknowledged_history(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 29.0)
        h, w = b.history(), b.w
        late2 = P.obs("L2", D[2], 22.0)
        rows = w.ledger + [late2]
        _p, ack = T.run_plan(h, [T.late_cmd(D[2], [T.fp(late2)], T.mref_apply(h, 2))], w.sessions, rows, D[4], "a1")
        acked = T.extend(h, ack)
        plan = X.prepare_restart_plan(acked, D[5], w.sessions, rows, D[5], "r1", R.WHEN)
        self.assertEqual(plan.status, "READY")
        self.assertEqual(X.confirm_restart_plan(plan, plan.plan_hash, acked, w.sessions, rows).status,
                         "CONFIRMED_IN_MEMORY")


if __name__ == "__main__":
    unittest.main()
