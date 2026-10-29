"""C-12: normal days match S1 exactly; the wrapper delegates once to prepare_day and exposes no plan."""
import os
import re
import unittest
from unittest import mock

import r_helpers as H
from r_helpers import D, R
from v2_persistence import runner as s1_runner
from v2_persistence.plan import AppendPlan


def row(record_id, d, value, hour=20):
    return H.P.obs(record_id, d, value, hour=hour)


class SameAsS1(unittest.TestCase):
    def setUp(self):
        self.w = H.world(2, values={1: 27.0, 2: 35.0})
        self.rs = R.empty_resolutions()
        self.ledger = list(self.w.ledger)

    def both(self, d, ledger):
        ours = R.prepare_resolved_day(self.w.snap(), self.rs, d, self.w.series, self.w.sessions, ledger)
        s1 = s1_runner.prepare_day(self.w.snap(), d, self.w.series, self.w.sessions, ledger)
        return ours, s1

    def test_prepared_no_commit_and_already_applied(self):
        r3 = row("R3", D[3], 33.0)
        cases = {"PREPARED": (D[3], self.ledger + [r3]), "NO_COMMIT": (D[3], self.ledger),
                 "ALREADY_APPLIED": (D[2], self.ledger)}
        for status, (d, ledger) in cases.items():
            with self.subTest(status):
                ours, s1 = self.both(d, ledger)
                self.assertEqual(ours.status, s1.status)
                self.assertEqual(ours.status, status)
                self.assertEqual(ours.core_result, s1.core_result)
                if s1.plan is None:
                    self.assertIsNone(ours.candidate_event_text)
                    self.assertIsNone(ours.candidate_event_hash)
                else:
                    self.assertEqual(ours.candidate_event_text, H.cj(s1.plan.event))
                    self.assertEqual(ours.candidate_event_hash, s1.plan.event_hash)

    def test_the_state_of_the_core_result_keeps_the_core_meaning(self):
        ours, s1 = self.both(D[3], self.ledger + [row("R3", D[3], 33.0)])
        self.assertTrue(ours.core_result.state_updated)          # a new transition candidate, not "saved"
        self.assertFalse(ours.committed)
        self.assertFalse(ours.committable)

    def test_input_errors_have_the_same_code_as_s1(self):
        for d in (D[0], "2030-01-01", D[-1], "x", D[1]):
            with self.subTest(d=d):
                with self.assertRaises((H.PersistenceError, H.InputError, H.ConflictError)) as a:
                    s1_runner.prepare_day(self.w.snap(), d, self.w.series, self.w.sessions, self.ledger)
                with self.assertRaises((H.PersistenceError, H.InputError, H.ConflictError)) as b:
                    R.prepare_resolved_day(self.w.snap(), self.rs, d, self.w.series, self.w.sessions, self.ledger)
                self.assertEqual(a.exception.code, b.exception.code)


class DelegationAndShape(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.rs = R.empty_resolutions()
        self.ledger = list(self.w.ledger) + [row("R2", D[2], 33.0)]

    def test_prepare_day_is_called_once_with_the_final_ledger(self):
        with mock.patch("v2_recovery.daily.prepare_day", wraps=s1_runner.prepare_day) as spy:
            res = R.prepare_resolved_day(self.w.snap(), self.rs, D[2], self.w.series, self.w.sessions, self.ledger)
        self.assertEqual(spy.call_count, 1)
        args = spy.call_args[0]
        self.assertEqual(args[1], D[2])
        self.assertEqual(args[4], [H.cols(r) for r in sorted(self.ledger, key=lambda r: H.cj(H.cols(r)))])
        self.assertEqual(res.status, "PREPARED")

    def test_the_wrapper_follows_a_replaced_prepare_day(self):
        sentinel = s1_runner.PrepareResult("NO_COMMIT", None, mock.sentinel.core)
        with mock.patch("v2_recovery.daily.prepare_day", return_value=sentinel) as fake:
            res = R.prepare_resolved_day(self.w.snap(), self.rs, D[2], self.w.series, self.w.sessions, self.ledger)
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(res.status, "NO_COMMIT")

    def test_no_plan_and_no_s1_types_are_exposed_even_with_an_empty_set(self):
        res = R.prepare_resolved_day(self.w.snap(), self.rs, D[2], self.w.series, self.w.sessions, self.ledger)
        self.assertEqual(type(res).__name__, "SimulationDayResult")
        self.assertNotIsInstance(res, AppendPlan)
        self.assertNotIsInstance(res, s1_runner.PrepareResult)
        for name in dir(res):
            if name.startswith("_"):
                continue
            self.assertNotIsInstance(getattr(res, name), (AppendPlan, s1_runner.PrepareResult), name)
        self.assertFalse(hasattr(res, "plan"))
        public = {n for n in dir(res) if not n.startswith("_")}
        self.assertEqual(public, {"status", "core_result", "candidate_event_text", "candidate_event_hash",
                                  "committable", "committed"})
        self.assertIsInstance(res.candidate_event_text, str)
        self.assertEqual(len(res.candidate_event_hash), 64)

    def test_the_module_exposes_no_s1_plan_type(self):
        for name in R.__all__:
            self.assertFalse(isinstance(getattr(R, name), type) and issubclass(getattr(R, name), AppendPlan), name)

    def test_no_market_rule_is_copied(self):
        """No rule, threshold or transition name is used by any identifier of the new package (AST scan)."""
        import ast
        banned = re.compile(r"^(apply_transition|evaluate_day|market_side_\w+|RATIO_\w+|RuleStatus|RunClass|Tri|"
                            r"MarketState|MarketRow|first_unprocessed_session|rsi\w*|sma\w*)$")
        pkg = os.path.join(H.ROOT, "v2_recovery")
        seen = 0
        for fname in sorted(os.listdir(pkg)):
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(pkg, fname), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.Attribute):
                    names.append(node.attr)
                elif isinstance(node, (ast.ImportFrom, ast.Import)):
                    names.extend(a.name.split(".")[-1] for a in node.names)
                for n in names:
                    seen += 1
                    self.assertIsNone(banned.match(n), "%s uses %s" % (fname, n))
        self.assertGreater(seen, 100)


if __name__ == "__main__":
    unittest.main()
