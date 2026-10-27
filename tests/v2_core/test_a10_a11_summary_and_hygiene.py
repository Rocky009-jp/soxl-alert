"""A10 / A11: completion summary, exit codes, no account fields, no leakage, no network / storage / sending.

Existing candidate (920e695) code is not touched here; its tests are reported separately in the result document.
"""
import ast
import json
import os
import socket
import subprocess
import sys
import unittest

import v2_helpers as h
from v2_core.display import CLASS_LABEL, render, render_summary
from v2_core.engine import ErrorResult, RunClass, evaluate_day, run_day_safe
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
SESS = h.make_sessions(DATES)
D = "2026-01-07"
DATA = os.path.join(os.path.dirname(__file__), "data")


def series(per=None):
    per = per or {}
    return h.StubSeries([h.row(d, **per.get(d, h.WEAK)) for d in DATES])


class SummaryClasses(unittest.TestCase):
    def test_every_class_is_distinguishable_and_exit_codes_follow_the_adopted_rule(self):
        armed = MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE)
        off = MarketState(DATES[1], Tri.FALSE, 0, Tri.FALSE)
        results = {
            RunClass.NO_SIGNAL: evaluate_day(off, D, series(), SESS, []),
            RunClass.WAITING_FG: evaluate_day(armed, D, series(), SESS, []),
            RunClass.CONDITION_MET: evaluate_day(armed, D, series({D: h.NORMAL_OK}), SESS, [h.obs("a", D, 27)]),
            RunClass.REFERENCE_UNCONFIRMED: evaluate_day(MarketState.initial(), D, series({D: h.NORMAL_OK}), SESS,
                                                         [h.obs("a", D, 27)]),
            RunClass.DATA_ERROR: run_day_safe(armed, "2026-01-20", series(), SESS, []),
            RunClass.CONFLICT: run_day_safe(armed, D, series(), SESS, [h.obs("a", D, 20), h.obs("b", D, 27)]),
        }
        labels = set()
        for cls, res in results.items():
            self.assertIs(res.run_class, cls)
            text = render_summary(res)
            self.assertIn("実行区分: " + CLASS_LABEL[cls], text)
            labels.add(CLASS_LABEL[cls])
            expected = 1 if cls in (RunClass.DATA_ERROR, RunClass.CONFLICT) else 0
            self.assertEqual(res.exit_code, expected, cls)
            self.assertIn("終了コード: %d" % expected, text)
            self.assertIn("本コアは保存・送信しません", text)
        self.assertEqual(len(labels), 6)

    def test_no_signal_day_still_produces_a_summary(self):
        res = evaluate_day(MarketState(DATES[1], Tri.FALSE, 0, Tri.FALSE), D, series(), SESS, [])
        self.assertIn("実行区分: 合図なし", render_summary(res))

    def test_error_text_keeps_state_unchanged_and_denies_a_condition_miss(self):
        res = run_day_safe(MarketState.initial(), "2026-01-20", series(), SESS, [])
        text = render(res)
        self.assertIn("条件未達ではありません", text)
        self.assertIn("状態更新: なし", text)
        self.assertIn("データ検査: 異常", text)

    def test_waiting_summary_says_held_and_applied_summary_says_candidate(self):
        armed = MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE)
        self.assertIn("保留", render_summary(evaluate_day(armed, D, series(), SESS, [])))
        applied = evaluate_day(armed, D, series(), SESS, [h.obs("a", D, 20)])
        self.assertIn("次状態候補あり", render_summary(applied))
        again = evaluate_day(applied.next_state, D, series(), SESS, [h.obs("a", D, 20)])
        self.assertIn("同じDの再実行", render_summary(again))


class NoAccountFieldsNoLeakage(unittest.TestCase):
    ACCOUNT_WORDS = ("shares", "holding", "basis", "cost", "cash", "mmf", "order", "balance", "fill", "position")

    def test_state_and_result_structures_carry_no_account_fields(self):
        keys = set(MarketState.initial().to_dict())
        self.assertEqual(keys, {"as_of_d", "armed", "streak", "prev_normal_raw", "fixed_decision", "base"})
        res = evaluate_day(MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE), D, series(), SESS, [h.obs("a", D, 20)])
        for name in list(res.__dict__) + list(res.next_state.to_dict()) + list(res.next_state.fixed_decision):
            for word in self.ACCOUNT_WORDS:
                self.assertNotIn(word, name.lower(), name)
        import inspect
        params = " ".join(inspect.signature(evaluate_day).parameters)
        for word in self.ACCOUNT_WORDS:
            self.assertNotIn(word, params)

    def test_error_text_never_echoes_raw_input_or_urls(self):
        secret = "https://discord.com/api/webhooks/SECRET123/TOKEN456"
        bad = dict(h.obs(secret, D, "SECRETVAL"), source_url=secret)
        res = run_day_safe(MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE), D, series(), SESS, [bad])
        out = render(res) + repr(res.code) + repr(res.field)
        for needle in ("SECRET", "TOKEN", "discord", "webhooks", "http"):
            self.assertNotIn(needle, out)
        bad2 = dict(h.obs(secret, D, 27), observed_at_iso8601="SECRETTIME")
        res2 = run_day_safe(MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE), D, series(), SESS, [bad2])
        self.assertNotIn("SECRET", render(res2))

    def test_rendered_message_does_not_contain_record_ids(self):
        rid = "private-record-id-xyz"
        res = evaluate_day(MarketState(DATES[1], Tri.TRUE, 0, Tri.FALSE), D, series(), SESS, [h.obs(rid, D, 20)])
        self.assertNotIn(rid, render(res))


class OfflineHygiene(unittest.TestCase):
    PKG = os.path.join(h.ROOT, "v2_core")
    BANNED_IMPORTS = {"socket", "http", "urllib", "requests", "ssl", "smtplib", "ftplib", "subprocess", "asyncio",
                      "sqlite3", "shelve", "pickle", "gspread", "yfinance", "pandas", "numpy", "logging"}

    def modules(self):
        for name in sorted(os.listdir(self.PKG)):
            if name.endswith(".py"):
                path = os.path.join(self.PKG, name)
                with open(path, encoding="utf-8") as fh:
                    yield name, ast.parse(fh.read())

    def test_network_is_blocked_in_this_test_process(self):
        with self.assertRaises(RuntimeError):
            socket.socket()

    def test_imports_are_standard_library_only_and_offline(self):
        for name, tree in self.modules():
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, self.BANNED_IMPORTS, "%s imports %s" % (name, m))
                    if hasattr(sys, "stdlib_module_names") and m != "v2_core":
                        self.assertIn(m, sys.stdlib_module_names, "%s imports non-stdlib %s" % (name, m))

    def test_no_write_opens_or_calls_to_write_or_environment(self):
        for name, tree in self.modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                    mode = node.args[1] if len(node.args) > 1 else None
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode = kw.value
                    if mode is not None:
                        self.assertTrue(isinstance(mode, ast.Constant) and set(str(mode.value)) <= set("rbt"),
                                        "%s opens a file for writing" % name)
                if isinstance(node, ast.Attribute) and node.attr in ("write", "writelines", "mkdir", "makedirs", "remove",
                                                                      "rename", "environ", "system", "popen"):
                    self.fail("%s uses %s" % (name, node.attr))


class PreviewCli(unittest.TestCase):
    def run_cli(self, *extra):
        cmd = [sys.executable, "-B", "-m", "v2_core.preview", "--fixture-dir", h.FIXTURE_DIR, "--date", "2024-10-02",
               "--sessions", os.path.join(DATA, "cli_sessions_synthetic.json")] + list(extra)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(cmd, cwd=h.ROOT, capture_output=True, text=True, env=env, timeout=120)

    def test_preview_prints_text_and_next_state_candidate_only(self):
        p = self.run_cli("--observations", os.path.join(DATA, "cli_observations_synthetic.json"), "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ローカルプレビュー（実送信なし）", p.stdout)
        self.assertIn("対象D=2024-10-02", p.stdout)
        tail = p.stdout[p.stdout.index("{"):]
        state = json.loads(tail)
        self.assertEqual(state["as_of_d"], "2024-10-02")
        self.assertEqual(state["armed"], "UNKNOWN")                 # initial state: nothing is invented
        self.assertEqual(p.stderr, "")

    def test_preview_without_observation_is_waiting_or_no_signal_and_exit_zero(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("未記録", p.stdout)

    def test_preview_invalid_observation_exits_one_without_echoing_input(self):
        p = self.run_cli("--observations", os.path.join(DATA, "cli_observations_invalid_synthetic.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("データ異常", p.stdout)
        self.assertIn("fg_value_invalid", p.stdout)
        self.assertNotIn("nan", p.stdout.replace("fg_value_invalid", ""))

    def test_preview_missing_file_exits_one(self):
        p = self.run_cli("--observations", os.path.join(DATA, "does_not_exist.json"))
        self.assertEqual(p.returncode, 1)
        self.assertIn("file_unreadable", p.stdout)


if __name__ == "__main__":
    unittest.main()
