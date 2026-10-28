"""A-04: the transition was extracted into apply_transition without changing any behaviour.

(a) every input in v2_transition_cases gives the same result as the code before the extraction (baseline JSON,
    written from 1a54a85 by gen_baseline_evaluate_day.py); the baseline is a before/after base, not a correctness
    oracle. (b)/(b2) apply_transition called with values taken out of the inputs gives the same candidate and
    judgement, and evaluate_day alone decides the final next state and state_updated. (c) evaluate_day takes its
    transition from apply_transition and nowhere else.
"""
import ast
import copy
import dataclasses
import inspect
import json
import os
import unittest
from unittest import mock

import v2_helpers as h
import v2_transition_cases as tc
from v2_core import engine, transition
from v2_core.engine import DayResult, ErrorResult, RunClass, RuleStatus, evaluate_day
from v2_core.errors import InputError
from v2_core.observations import parse_observation
from v2_core.state import MarketState
from v2_core.tri import Tri
from v2_core.transition import Transition, apply_transition

BASELINE = os.path.join(os.path.dirname(__file__), "data", "baseline_evaluate_day_1a54a85.json")
with open(BASELINE, encoding="utf-8") as _fh:
    BASE_DOC = json.load(_fh)

_CACHE = []


def all_cases():
    if not _CACHE:
        _CACHE.extend(tc.iter_all())
    return _CACHE


def derived_inputs(args):
    """Base state, D row, previous row and previous session date, taken out of the inputs of one evaluate_day call."""
    state, d, series, sess, _raw = args
    prev = sess.previous(d).date
    cut = series.through(d)
    row = cut.row(d)
    try:
        prev_row = cut.row(prev)
    except InputError:
        prev_row = None
    base = state.base if state.as_of_d == d else state
    return base, d, prev, row, prev_row


class BaselineIdentity(unittest.TestCase):
    def test_baseline_file_is_the_pre_extraction_output(self):
        self.assertEqual(BASE_DOC["generated_from_sha"], "1a54a8573023af9490017b02a8b6458f061031c7")
        self.assertEqual(BASE_DOC["case_count"], len(BASE_DOC["cases"]))
        self.assertEqual(set(BASE_DOC["cases"]), {cid for cid, _a, _r in all_cases()})

    def test_the_input_set_has_the_required_shape(self):
        ids = [cid for cid, _a, _r in all_cases()]
        grid = [i for i in ids if i.startswith("grid|")]
        # 16 (armed x streak x prev_normal_raw pairs allowed by I-05/I-06) x 3 base as_of x 9 F&G x 3 x 2
        self.assertEqual(len(grid), 16 * 3 * 9 * 3 * 2)
        self.assertEqual(len([i for i in ids if i.startswith("a1|")]), 464)      # 465 CSV rows, first is the start
        self.assertGreater(len([i for i in ids if i.startswith("rep|")]), 40)
        fg = {i.split("|")[5] for i in grid}
        self.assertEqual(fg, {"None", "0", "24.99", "25", "27.5", "29.99", "30", "30.01", "100"})

    def test_the_input_set_reaches_every_outcome(self):
        classes, codes, statuses = set(), set(), set()
        for _cid, _a, res in all_cases():
            classes.add(res.run_class)
            if isinstance(res, ErrorResult):
                codes.add(res.code)
            else:
                statuses.update((name, r.status) for name, r in res.rules.items())
        self.assertEqual(classes, set(RunClass))
        for code in ("decision_conflict_with_applied", "state_rerun_unavailable", "rerun_decision_missing",
                     "intermediate_session_unprocessed", "decision_conflict", "record_id_conflict",
                     "target_not_in_sessions", "target_unconfirmed", "next_session_missing",
                     "previous_session_missing", "session_series_mismatch", "state_ahead_of_target",
                     "decision_outside_window", "target_mismatch", "fg_value_invalid", "target_row_missing"):
            self.assertIn(code, codes)
        for name in ("EXFEAR", "NORMAL", "TREND"):
            for st in RuleStatus:
                if (name, st) != ("TREND", RuleStatus.UNCONFIRMED):         # TREND never depends on armed
                    self.assertIn((name, st), statuses, (name, st))


class PreviousRowUnavailableCases(unittest.TestCase):
    def test_the_unavailable_previous_row_really_reaches_the_transition(self):
        by_id = {cid: res for cid, _a, res in all_cases()}
        # D is not market-side normal and the previous row is unusable: previous normal_raw stays unknown
        self.assertIs(by_id["rep|prev_row_unavailable|none|None|unknown"].effective_prev_normal_raw, Tri.UNKNOWN)
        # the same inputs with a usable, not-normal previous row (grid) resolve it to FALSE
        self.assertIs(by_id["grid|UNKNOWN|0|UNKNOWN|prev|None|none|not"].effective_prev_normal_raw, Tri.FALSE)


class MatchesPreExtractionBehaviour(unittest.TestCase):
    """(a) all fields of DayResult / ErrorResult, for every input."""

    def test_every_case_is_identical(self):
        different = []
        for cid, _args, res in all_cases():
            if json.loads(json.dumps(tc.to_plain(res))) != BASE_DOC["cases"][cid]:
                different.append(cid)
        self.assertEqual(different[:10], [])
        self.assertEqual(len(different), 0)

    def test_same_d_rerun_and_new_application_flags(self):
        # (b2) also against the baseline, but spelled out from the inputs here
        seen = {"new": 0, "rerun": 0, "no_decision": 0}
        for cid, args, res in all_cases():
            if not isinstance(res, DayResult):
                self.assertFalse(res.state_updated, cid)
                continue
            state, d = args[0], args[1]
            if res.decision is None:
                seen["no_decision"] += 1
                self.assertFalse(res.state_updated, cid)
                self.assertIs(res.next_state, state, cid)
            elif state.as_of_d == d:
                seen["rerun"] += 1
                self.assertFalse(res.state_updated, cid)
                self.assertEqual(res.next_state.as_of_d, d, cid)
            else:
                seen["new"] += 1
                self.assertTrue(res.state_updated, cid)
                self.assertEqual(res.next_state.as_of_d, d, cid)
                self.assertEqual(res.next_state.base.as_of_d, state.as_of_d, cid)
            self.assertEqual(BASE_DOC["cases"][cid]["state_updated"], res.state_updated, cid)
        self.assertGreater(seen["new"], 1000)
        self.assertGreater(seen["rerun"], 5)
        self.assertGreater(seen["no_decision"], 250)


class RecalculationFromValues(unittest.TestCase):
    """(b) apply_transition with the base, D row, previous row and decision as plain values."""

    def compare(self, cid, args, res, t):
        state, d = args[0], args[1]
        self.assertEqual(t.rules, res.rules, cid)
        self.assertIs(t.run_class, res.run_class, cid)
        self.assertEqual(t.gap, res.gap, cid)
        self.assertEqual((t.effective_armed, t.effective_streak, t.effective_prev_normal_raw),
                         (res.effective_armed, res.effective_streak, res.effective_prev_normal_raw), cid)
        self.assertEqual(t.notes, res.notes, cid)
        if res.decision is None:
            self.assertIsNone(t.next_state, cid)
        else:
            self.assertEqual(t.next_state, res.next_state, cid)

    def test_direct_call_matches_evaluate_day_for_every_day_result(self):
        n_decision = n_none = n_rerun = 0
        for cid, args, res in all_cases():
            if not isinstance(res, DayResult):
                continue
            base, d, prev, row, prev_row = derived_inputs(args)
            t = apply_transition(base, d, prev, row, prev_row, res.decision)
            self.assertIsInstance(t, Transition)
            self.compare(cid, args, res, t)
            if res.decision is None:
                n_none += 1
            else:
                n_decision += 1
                n_rerun += args[0].as_of_d == d
        self.assertGreater(n_decision, 1500)
        self.assertGreater(n_none, 250)
        self.assertGreater(n_rerun, 5)

    def test_the_decision_used_is_the_one_selected_from_the_observations(self):
        from v2_core.observations import select_decision
        for cid, args, res in all_cases():
            if isinstance(res, DayResult):
                self.assertEqual(select_decision(args[4], args[3], args[1]), res.decision, cid)

    def test_values_stored_as_json_give_the_same_result(self):
        """Only values that a transition record would hold: no series, session list, observation list or clock."""
        checked = 0
        for cid, args, res in all_cases():
            if not isinstance(res, DayResult):
                continue
            base, d, prev, row, prev_row = derived_inputs(args)
            stored = json.dumps({
                "base": {"as_of_d": base.as_of_d, "armed": base.armed.value, "streak": base.streak,
                         "prev_normal_raw": base.prev_normal_raw.value},
                "d": d, "prev_session_date": prev,
                "row": dataclasses.asdict(row),
                "prev_row": None if prev_row is None else dataclasses.asdict(prev_row),
                "decision": None if res.decision is None else {
                    "record_id": res.decision.record_id, "observation_status": res.decision.status,
                    "observation_role": res.decision.role, "current_fg_value": res.decision.value,
                    "observed_at_iso8601": res.decision.observed_at.isoformat(),
                    "target_us_session_date": res.decision.target_date,
                    "fingerprint": res.decision.fingerprint()},
            })
            v = json.loads(stored)
            b = v["base"]
            restored_base = MarketState(b["as_of_d"], Tri(b["armed"]), b["streak"], Tri(b["prev_normal_raw"]))
            rec = v["decision"]
            decision = None
            if rec is not None:
                decision = parse_observation({k: x for k, x in rec.items() if k != "fingerprint"})
                self.assertEqual(decision.fingerprint(), rec["fingerprint"], cid)
            t = apply_transition(restored_base, v["d"], v["prev_session_date"], type(row)(**v["row"]),
                                 None if v["prev_row"] is None else type(row)(**v["prev_row"]), decision)
            self.compare(cid, args, res, t)
            checked += 1
        self.assertGreater(checked, 3000)

    def test_a_rerun_gives_the_same_candidate_and_only_state_updated_differs(self):
        series, sess = tc.stub_series("normal", "normal"), tc.sessions()
        raw = [h.obs("r-" + tc.D, tc.D, 27.5)]
        before = MarketState(tc.PREV, Tri.TRUE, 2, Tri.FALSE)
        first = evaluate_day(before, tc.D, series, sess, raw)
        again = evaluate_day(first.next_state, tc.D, series, sess, raw)
        self.assertTrue(first.state_updated)
        self.assertFalse(again.state_updated)
        self.assertEqual(again.next_state, first.next_state)
        self.assertEqual(again.rules, first.rules)
        t_first = apply_transition(before, tc.D, tc.PREV, series.row(tc.D), series.row(tc.PREV), first.decision)
        t_again = apply_transition(first.next_state.base, tc.D, tc.PREV, series.row(tc.D), series.row(tc.PREV),
                                   again.decision)
        self.assertEqual(t_first, t_again)

    def test_transition_has_no_state_updated_and_does_not_mutate_inputs(self):
        self.assertNotIn("state_updated", {f.name for f in dataclasses.fields(Transition)})
        base = MarketState(tc.PREV, Tri.UNKNOWN, 0, Tri.UNKNOWN)
        row, prev_row = h.row(tc.D, **h.NORMAL_OK), h.row(tc.PREV, **h.WEAK)
        decision = parse_observation(h.obs("r-x", tc.D, 27))
        snapshot = copy.deepcopy((base, row, prev_row, decision))
        apply_transition(base, tc.D, tc.PREV, row, prev_row, decision)
        self.assertEqual((base, row, prev_row, decision), snapshot)

    def test_no_prev_row_means_unknown_prev_market_side(self):
        base = MarketState(tc.PREV, Tri.TRUE, 0, Tri.UNKNOWN)
        row = h.row(tc.D, **h.NORMAL_OK)
        none = apply_transition(base, tc.D, tc.PREV, row, None, None)
        weak = apply_transition(base, tc.D, tc.PREV, row, h.row(tc.PREV, **h.WEAK), None)
        self.assertEqual(none.effective_prev_normal_raw, Tri.UNKNOWN)
        self.assertEqual(weak.effective_prev_normal_raw, Tri.FALSE)


class OnlyValuesNoSideEffects(unittest.TestCase):
    def test_signature_takes_values_only(self):
        self.assertEqual(list(inspect.signature(apply_transition).parameters),
                         ["base", "d", "prev_session_date", "row", "prev_row", "decision"])

    def test_transition_module_imports_no_io_clock_or_network(self):
        with open(transition.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = {"os", "sys", "io", "time", "datetime", "json", "socket", "random", "pathlib", "subprocess",
                  "urllib", "http", "logging", "csv", "sessions"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0] if node.level == 0 else (node.module or ""))
        self.assertEqual(imported & banned, set(), imported)
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertEqual(calls & {"open", "print", "input", "exec", "eval"}, set())


class EvaluateDayUsesApplyTransition(unittest.TestCase):
    """(c) evaluate_day has no second copy of the transition."""

    def args(self, fg=27.5, state=None):
        raw = [] if fg is None else [h.obs("r-" + tc.D, tc.D, fg)]
        return (state or MarketState(tc.PREV, Tri.TRUE, 2, Tri.FALSE), tc.D, tc.stub_series("normal", "normal"),
                tc.sessions(), raw)

    def test_replacing_apply_transition_changes_every_transition_field(self):
        real = engine.apply_transition
        calls = []

        def fake(*a):
            calls.append(a)
            t = real(*a)
            candidate = dataclasses.replace(t.next_state, streak=42, armed=Tri.FALSE)
            return dataclasses.replace(
                t, rules={"X": t.rules["NORMAL"]}, run_class=RunClass.REFERENCE_UNCONFIRMED, gap=not t.gap,
                effective_armed=Tri.UNKNOWN, effective_streak=99, effective_prev_normal_raw=Tri.TRUE,
                notes=t.notes + ["patched_note"], next_state=candidate)

        args = self.args()
        real_result = evaluate_day(*args)
        with mock.patch.object(engine, "apply_transition", fake):
            res = evaluate_day(*args)
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(res.rules), ["X"])
        self.assertIs(res.run_class, RunClass.REFERENCE_UNCONFIRMED)
        self.assertEqual(res.gap, not real_result.gap)
        self.assertEqual((res.effective_armed, res.effective_streak, res.effective_prev_normal_raw),
                         (Tri.UNKNOWN, 99, Tri.TRUE))
        self.assertIn("patched_note", res.notes)
        self.assertEqual((res.next_state.streak, res.next_state.armed), (42, Tri.FALSE))
        self.assertTrue(res.state_updated)
        # restored afterwards
        self.assertEqual(evaluate_day(*args).rules, real_result.rules)
        self.assertIs(engine.apply_transition, real)

    def test_arguments_passed_are_the_values_of_the_day(self):
        calls = []
        real = engine.apply_transition

        def spy(*a):
            calls.append(a)
            return real(*a)

        state = MarketState(tc.PREV, Tri.TRUE, 2, Tri.FALSE)
        args = self.args(state=state)
        with mock.patch.object(engine, "apply_transition", spy):
            res = evaluate_day(*args)
        (base, d, prev, row, prev_row, decision), = calls
        self.assertIs(base, state)
        self.assertEqual((d, prev), (tc.D, tc.PREV))
        self.assertEqual(row, h.row(tc.D, **h.NORMAL_OK))
        self.assertEqual(prev_row, h.row(tc.PREV, **h.NORMAL_OK))
        self.assertIs(decision, res.decision)

    def test_a_rerun_passes_the_stored_base_and_the_final_state_is_decided_by_evaluate_day(self):
        raw = h.obs("r-" + tc.D, tc.D, 27.5)
        before = MarketState(tc.PREV, Tri.TRUE, 2, Tri.FALSE)
        applied = evaluate_day(before, tc.D, tc.stub_series(), tc.sessions(), [raw])
        calls = []
        real = engine.apply_transition

        def fake(*a):
            calls.append(a)
            t = real(*a)
            return dataclasses.replace(t, next_state=dataclasses.replace(t.next_state, streak=7))

        with mock.patch.object(engine, "apply_transition", fake):
            rerun = evaluate_day(applied.next_state, tc.D, tc.stub_series(), tc.sessions(), [raw])
        self.assertEqual(calls[0][0], before)                # the base stored in the state, not the state itself
        self.assertFalse(rerun.state_updated)
        self.assertEqual(rerun.next_state.streak, 7)         # the candidate is what is returned for a rerun

    def test_without_a_decision_the_input_state_is_returned_whatever_the_candidate(self):
        real = engine.apply_transition

        def fake(*a):
            t = real(*a)
            return dataclasses.replace(t, next_state=MarketState(tc.D, Tri.TRUE, 9, Tri.FALSE))

        args = self.args(fg=None)
        with mock.patch.object(engine, "apply_transition", fake):
            res = evaluate_day(*args)
        self.assertIs(res.next_state, args[0])
        self.assertFalse(res.state_updated)

    def test_engine_source_holds_no_copy_of_the_transition(self):
        with open(engine.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        names = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        for forbidden in ("market_side_normal", "market_side_trend", "RuleResult", "tri_and", "from_bool"):
            self.assertNotIn(forbidden, names)
        self.assertEqual(names.count("apply_transition"), 1)
        evaluate = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate_day")
        inside = [n.func.id for n in ast.walk(evaluate) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertEqual(inside.count("apply_transition"), 1)

    def test_names_other_modules_import_from_engine_still_exist(self):
        for name in ("RuleResult", "RuleStatus", "RunClass", "market_side_normal", "market_side_trend",
                     "RATIO_EXFEAR", "RATIO_NORMAL", "RATIO_TREND", "DayResult", "ErrorResult", "evaluate_day",
                     "run_day_safe"):
            self.assertTrue(hasattr(engine, name), name)
        self.assertIs(engine.RuleStatus, transition.RuleStatus)
        self.assertIs(engine.RunClass, transition.RunClass)


if __name__ == "__main__":
    unittest.main()
