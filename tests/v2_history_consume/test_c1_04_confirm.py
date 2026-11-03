"""C1-13 (the confirmation of a plan with CONSUME) and C1-14 (a plan without CONSUME is the one of bfbde7a, character
for character: the old package is read from Git and run next to the new one)."""
import importlib.abc
import importlib.util
import os
import sys
import unittest

import c1_helpers as C

sys.path.insert(0, os.path.join(C.ROOT, "tests", "v2_scope_chain"))
import sc_helpers as G  # noqa: E402  (read-only Git helpers of the range tests)

H, P, R, V, D = C.H, C.P, C.R, C.V, C.D
CONSUME = C.CONSUME
MAIN = [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)]
GAP = [("DROP", 2), (CONSUME, D[2]), (CONSUME, D[3]), ("REAPPLY", 3)]


def mismatch(case, fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    case.assertEqual((e.code, e.field), ("history_plan_mismatch", None) if e.field is None else (e.code, e.field))
    return e


class Tampering(unittest.TestCase):
    """C1-13."""

    def setUp(self):
        self.b = C.s_declare()
        self.plan = C.plan(self.b, 3, MAIN, D[5])

    def confirm(self, plan, **kw):
        return R.confirm(plan, self.b.history(), self.b.w, **kw)

    def code(self, plan, **kw):
        return R.refusal(self.confirm, plan, **kw).code

    def test_the_plan_confirms(self):
        self.assertEqual(self.confirm(self.plan).status, "CONFIRMED_IN_MEMORY")

    def test_a_changed_day_place_or_row_of_the_consume_is_a_mismatch(self):
        def other_day(b):
            b["ops"][1]["d"] = D[4]
        def moved(b):
            b["ops"][1], b["ops"][2] = b["ops"][2], b["ops"][1]
        def removed(b):
            del b["ops"][1]
        def item_day(b):
            b["series_inputs"][0]["d"] = D[4]
        def item_row(b):
            b["series_inputs"][0]["row"]["soxx"] = 999.0
        def item_dropped(b):
            del b["series_inputs"][0]
        def change_day(b):
            b["changes"][1]["d"] = D[4]
        def change_seq(b):
            b["changes"][1]["to_seq"] += 1
        def change_flag(b):
            b["changes"][1]["same_as_superseded"] = False
        def change_dropped(b):
            del b["changes"][1]
        for fn in (other_day, moved, removed, item_day, item_row, item_dropped, change_day, change_seq, change_flag,
                   change_dropped):
            with self.subTest(fn=fn.__name__):
                forged = R.refreshed(self.plan, fn)
                self.assertEqual(self.code(forged), "history_plan_mismatch")

    def test_a_consume_of_the_wrong_form_is_refused_in_the_first_stage(self):
        def extra_key(b):
            b["ops"][1]["from_seq"] = None
        def bad_day(b):
            b["ops"][1]["d"] = "2026-3-5"
        def lowercase(b):
            b["ops"][1]["op"] = "consume"
        def item_from_seq(b):
            b["series_inputs"][0]["from_seq"] = -1
        def change_from_seq(b):
            b["changes"][1]["from_seq"] = 5
        def change_kind(b):
            b["changes"][1]["kind"] = "ACK"
        def change_fields(b):
            b["changes"][1]["changed_fields"] = ["state_after"]
        def change_no_day(b):
            b["changes"][1]["d"] = None
        for fn in (extra_key, bad_day, lowercase, item_from_seq, change_from_seq, change_kind, change_fields,
                   change_no_day):
            with self.subTest(fn=fn.__name__):
                forged = R.refreshed(self.plan, fn)
                self.assertEqual(self.code(forged), "history_plan_mismatch")

    def test_a_plan_dict_with_a_consume_of_any_value_is_read_and_refused_by_the_confirmation(self):
        for entry in ({"op": CONSUME, "d": D[3], "x": 1}, {"op": CONSUME, "d": ["x"]}, {"op": CONSUME, "d": None},
                      {"op": CONSUME, "d": 5}, {"op": CONSUME, "d": {"a": 1}}, {"op": CONSUME, "d": "2026-02-30"},
                      {"op": CONSUME}, {"op": CONSUME, "from_seq": 4}):
            with self.subTest(entry=entry):
                data = self.plan.to_dict()
                data["basis"]["ops"][1] = entry
                data["plan_hash"] = H.sha(C.cj(data["basis"]))
                forged = C.Z.RestorePlan.from_dict(data)               # from_dict reads any JSON
                self.assertEqual(self.code(forged), "history_plan_mismatch")

    def test_a_wrong_confirmation_hash_is_a_mismatch(self):
        e = R.refusal(R.confirm, self.plan, self.b.history(), self.b.w, plan_hash="0" * 64)
        self.assertEqual(e.code, "history_plan_mismatch")

    def test_the_candidate_with_a_changed_consumed_record_is_a_mismatch(self):
        def edit(events, n):
            events[1]["state_after"] = dict(events[1]["state_after"], streak=7)
        forged = R.forge(self.plan, edit)
        self.assertEqual(self.code(forged), "history_plan_mismatch")

    def test_the_series_inputs_are_read_again_from_the_ops(self):
        # the day of the consume is not given a row any more: the confirmation reads the current series for it
        series = P.make_series(dates=[d for d in D if d != D[3]])
        e = R.refusal(self.confirm, self.plan, series=series)
        self.assertEqual((e.code, e.field), ("target_row_missing", "market"))

    def test_a_changed_row_of_the_consumed_day_is_stale(self):
        b = C.s_tail()
        plan = C.plan(b, 1, [("DROP", 2), (CONSUME, D[2])], D[5])
        series = R.with_row(b.w, D[2], soxx=101.0)
        e = R.refusal(R.confirm, plan, b.history(), b.w, series=series)
        self.assertEqual(e.code, "history_plan_stale")

    def test_the_same_plan_on_its_own_candidate_is_no_change_and_on_other_history_is_stale(self):
        res = self.confirm(self.plan)
        self.assertEqual(R.confirm(self.plan, res.history, self.b.w).status, "NO_CHANGE")
        b2 = C.s_declare()
        b2.declare(D[5], "q9")                                  # one more record: the head is not the plan's
        e = R.refusal(R.confirm, self.plan, b2.history(), b2.w)
        self.assertEqual(e.code, "history_plan_stale")

    def test_the_current_series_inputs_are_those_of_the_ops_of_the_plan(self):
        b = C.s_gap()
        plan = C.plan(b, 1, GAP, D[5])
        self.assertEqual(R.confirm(plan, b.history(), b.w).status, "CONFIRMED_IN_MEMORY")
        for day in (D[2], D[3]):
            series = R.with_row(b.w, day, soxx=101.0)
            self.assertEqual(R.refusal(R.confirm, plan, b.history(), b.w, series=series).code, "history_plan_stale", day)


# ---------------------------------------------------------------------------------------------------------- C1-14
PKG = "v2_history_restore"
START = "bfbde7a7854bf91a77fb58737c24b19c6507453a"
OLD = "v2_history_restore_bfbde7a"
FILES = ["__init__", "build", "chain", "confirm", "errors", "market", "points", "prepare", "records", "values"]


class _GitFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Loads the modules of the package v2_history_restore as they were at bfbde7a, from Git objects, under another name.
    Nothing is written (no bytecode, no file); the package is removed from sys.modules after the tests."""

    def find_spec(self, name, path=None, target=None):
        if name == OLD or name.startswith(OLD + "."):
            return importlib.util.spec_from_loader(name, self, is_package=(name == OLD))
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        short = "__init__" if module.__name__ == OLD else module.__name__.split(".")[-1]
        text = G.show(START, "%s/%s.py" % (PKG, short))
        if text is None:
            raise ImportError(short)
        if module.__name__ == OLD:
            module.__path__ = []
        exec(compile(text, "%s@%s/%s.py" % (PKG, START[:8], short), "exec"), module.__dict__)


class Unchanged(unittest.TestCase):
    """A plan, a candidate and a refusal without CONSUME are the ones of the code start, character for character."""

    @classmethod
    def setUpClass(cls):
        if not G.commit_exists(START):
            raise unittest.SkipTest("the code start commit is not available in this checkout")
        cls.finder = _GitFinder()
        sys.meta_path.insert(0, cls.finder)
        cls.old = importlib.import_module(OLD)

    @classmethod
    def tearDownClass(cls):
        sys.meta_path.remove(cls.finder)
        for name in [n for n in sys.modules if n == OLD or n.startswith(OLD + ".")]:
            del sys.modules[name]

    def both(self, fn, *args, **kwargs):
        """The refusal tuple or the value of a call with the old package and with the new one."""
        out = []
        for pkg in (self.old, C.Z):
            try:
                out.append(("ok", fn(pkg, *args, **kwargs)))
            except Exception as e:                                        # noqa: BLE001 the error is compared
                out.append(("error", (e.code, e.field, getattr(e, "rule", None), e.detail)))
        return out

    def prep(self, pkg, b, seq, mapping, check, rid, **kw):
        w = b.w
        return pkg.prepare_restore_plan(
            kw.get("history", b.history()), R.point(b, seq), R.ops_of(b, seq, mapping), kw.get("sessions", w.sessions),
            kw.get("ledger", w.ledger), kw.get("series", w.series), check, rid, R.WHEN)

    def test_the_package_read_from_git_is_the_code_start(self):
        self.assertEqual(sorted(n for n in self.old.__dict__ if not n.startswith("_")),
                         sorted(["confirm_restore_plan", "prepare_restore_plan", "RestorePlan", "RestoreConfirmResult",
                                 "READY", "CONFIRMED_IN_MEMORY", "NO_CHANGE", "build", "confirm", "errors", "values",
                                 "prepare", "chain", "market", "points", "records"]))
        text = G.show(START, "v2_history_restore/points.py")
        self.assertIn("CONSUME, with any keys, and every unknown name", text)
        self.assertNotIn("CONSUME", self.old.values.__dict__)

    SCENARIOS = (
        ("restart_between", lambda: R.ex_restart_between(), 1, {2: "DROP", 3: "REAPPLY"}, 3),
        ("restart_over_gap", lambda: R.ex_restart_over_gap(), 1, {2: "DROP", 3: "REAPPLY"}, 5),
        ("restart_over_gap_all", lambda: R.ex_restart_over_gap(), 0, {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}, 5),
        ("ack_between", lambda: R.ex_ack_between(), 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, 5),
        ("declare_between_replay", lambda: R.ex_declare_between(), 3, {4: "REPLAY", 5: "REAPPLY"}, 5),
        ("declare_between_drop", lambda: R.ex_declare_between(), 3, {4: "DROP", 5: "REAPPLY"}, 5),
        ("declare_tail", lambda: R.ex_declare_tail(), 1, {2: "DROP"}, 5),
        ("restart_tail", lambda: R.ex_restart_tail(), 1, {2: "DROP"}, 5),
        ("null_restart", lambda: R.ex_null_restart(), 0, {1: "DROP"}, 5),
        ("double_restart", lambda: R.ex_double_restart(), 1, {2: "DROP", 3: "REAPPLY", 4: "DROP", 5: "REAPPLY"}, 5),
        ("late_ack_tail", lambda: R.ex_late_ack_tail()[0] if isinstance(R.ex_late_ack_tail(), tuple)
         else R.ex_late_ack_tail(), 3, {4: "DROP", 5: "DROP"}, 5),
    )

    def test_the_plans_and_the_candidates_are_the_same_characters(self):
        compared = 0
        for name, make, seq, mapping, check in self.SCENARIOS:
            with self.subTest(scenario=name):
                b = make()
                old, new = self.both(self.prep, b, seq, mapping, D[check], "c1-1")
                self.assertEqual(old[0], new[0], (old, new) if old[0] == "error" or new[0] == "error" else "")
                if old[0] == "ok":
                    self.assertEqual(C.cj(old[1].to_dict()), C.cj(new[1].to_dict()))
                    self.assertEqual(old[1].plan_hash, new[1].plan_hash)
                    compared += 1
                    conf = [pkg.confirm_restore_plan(plan, plan.plan_hash, b.history(), b.w.sessions, b.w.ledger,
                                                     b.w.series) for pkg, plan in ((self.old, old[1]), (C.Z, new[1]))]
                    self.assertEqual(C.cj(conf[0].history.to_dict()), C.cj(conf[1].history.to_dict()))
                    self.assertEqual((conf[0].status, conf[1].status), ("CONFIRMED_IN_MEMORY",) * 2)
                else:
                    self.assertEqual(old[1], new[1])
        self.assertGreaterEqual(compared, 8)

    def test_the_refusals_without_consume_are_the_same(self):
        b = C.s_declare()
        cases = [
            ("stop", 3, {4: "DROP", 5: "REAPPLY"}, {}),
            ("partial", 3, {4: "DROP"}, {}),
            ("conflict", 3, {4: "DROP", 5: "REAPPLY"}, {"ledger": b.w.ledger + [P.obs("X3b", D[3], 1.0)]}),
            ("series", 3, {4: "DROP", 5: "REAPPLY"}, {"series": R.with_row(b.w, D[3], soxx=101.0)}),
            ("sessions", 3, {4: "DROP", 5: "REAPPLY"}, {"sessions": R.sessions_with(unconfirmed=(D[3],))}),
        ]
        for name, seq, mapping, kw in cases:
            with self.subTest(case=name):
                old, new = self.both(self.prep, b, seq, mapping, D[5], "c1-1", **kw)
                self.assertEqual(old, new)
        # the lowercase name and the unknown names are refused in the same way
        ops = R.ops_of(b, 3, {"*": "DROP"})
        for op in ("consume", "MERGE", "APPLY", ""):
            with self.subTest(op=op):
                bad = [dict(o) for o in ops]
                bad[0]["op"] = op
                old, new = self.both(lambda pkg: pkg.prepare_restore_plan(
                    b.history(), R.point(b, 3), bad, b.w.sessions, b.w.ledger, b.w.series, D[5], "c1-1", R.WHEN))
                self.assertEqual(old, new)
                self.assertEqual(new[1][2], "restore_op_unsupported")

    def test_the_difference_is_the_consume_only(self):
        b = C.s_declare()
        ops = C.ops_of(MAIN)
        old, new = self.both(lambda pkg: pkg.prepare_restore_plan(
            b.history(), R.point(b, 3), ops, b.w.sessions, b.w.ledger, b.w.series, D[5], "c1-1", R.WHEN))
        self.assertEqual(old, ("error", ("restore_invalid", "ops", "restore_op_unsupported", None)))
        self.assertEqual(new[0], "ok")

    def test_the_existing_b4_expectations_are_the_same_text(self):
        # the plan of the first scenario of the existing B-4 tests: the basis keys and the changes keep their shape
        b = R.ex_restart_between()
        plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "c1-1")
        self.assertEqual(sorted(plan.basis), sorted(C.Z.values.BASIS_KEYS))
        self.assertEqual(len(plan.basis), 23)
        self.assertEqual(plan.basis["operation"], "soxl-v2-history-restore-plan/1")
        self.assertTrue(all(i["from_seq"] is not None for i in plan.basis["series_inputs"]))


if __name__ == "__main__":
    unittest.main()
