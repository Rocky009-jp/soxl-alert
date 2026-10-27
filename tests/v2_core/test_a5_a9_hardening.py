"""Hardening: malformed saved state or fixture files become coded input errors (exit 1), never tracebacks."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import v2_helpers as h
from v2_core.errors import InputError
from v2_core.fixture import load_research_fixture
from v2_core.state import MarketState
from v2_core.tri import Tri

DATA = os.path.join(os.path.dirname(__file__), "data")
GOOD = {"as_of_d": "2026-01-06", "armed": "TRUE", "streak": 2, "prev_normal_raw": "FALSE",
        "fixed_decision": {"d": "2026-01-06", "record_id": "a", "fingerprint": "f" * 64},
        "base": {"as_of_d": "2026-01-05", "armed": "UNKNOWN", "streak": 0, "prev_normal_raw": "UNKNOWN",
                 "fixed_decision": None, "base": None}}


class StateFileValidation(unittest.TestCase):
    def code(self, data):
        with self.assertRaises(InputError) as ctx:
            MarketState.from_dict(data)
        return ctx.exception.code

    def test_good_state_round_trips(self):
        s = MarketState.from_dict(GOOD)
        self.assertEqual((s.armed, s.streak, s.base.armed), (Tri.TRUE, 2, Tri.UNKNOWN))
        self.assertEqual(MarketState.from_dict(s.to_dict()), s)

    def test_malformed_states_are_coded_errors(self):
        bad = [
            "x", None, [], 5,
            dict(GOOD, as_of_d="2026-13-01"),
            dict(GOOD, as_of_d=20260106),
            dict(GOOD, armed="MAYBE"),
            dict(GOOD, streak=True),
            dict(GOOD, streak=-1),
            dict(GOOD, streak=1.5),
            dict(GOOD, fixed_decision="x"),
            dict(GOOD, fixed_decision={"d": "2026-01-06", "record_id": 5, "fingerprint": "f"}),
            dict(GOOD, fixed_decision={"d": "bad", "record_id": "a", "fingerprint": "f"}),
            dict(GOOD, base=dict(GOOD["base"], base=dict(GOOD["base"]))),     # nesting deeper than one level
            dict(GOOD, base="x"),
        ]
        for data in bad:
            self.assertEqual(self.code(data), "state_invalid", repr(data)[:60])
        missing = dict(GOOD)
        del missing["armed"]
        self.assertEqual(self.code(missing), "state_invalid")


class FixtureFileValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="v2core-")
        for n in ("daily.json", "daily_adjclose.csv", "fear-greed.csv"):
            shutil.copy(os.path.join(h.FIXTURE_DIR, n), os.path.join(self.tmp, n))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def code(self):
        with self.assertRaises(InputError) as ctx:
            load_research_fixture(self.tmp)
        return ctx.exception.code

    def write(self, name, text):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_missing_directory_and_files(self):
        with self.assertRaises(InputError) as ctx:
            load_research_fixture(os.path.join(self.tmp, "nope"))
        self.assertEqual(ctx.exception.code, "fixture_unreadable_or_invalid")
        os.remove(os.path.join(self.tmp, "fear-greed.csv"))
        self.assertEqual(self.code(), "fixture_unreadable_or_invalid")

    def test_broken_json_and_missing_keys(self):
        self.write("daily.json", "{not json")
        self.assertEqual(self.code(), "fixture_unreadable_or_invalid")
        self.write("daily.json", json.dumps({"date": ["2024-01-02"]}))
        self.assertEqual(self.code(), "fixture_unreadable_or_invalid")

    def test_broken_csv_values_keep_their_specific_codes(self):
        self.write("fear-greed.csv", "Date,Fear Greed,Rating\n2024-01-02,nan,x\n")
        self.assertEqual(self.code(), "fg_value_invalid")
        self.write("fear-greed.csv", "Date,Fear Greed,Rating\n2024-01-02,150,x\n")
        self.assertEqual(self.code(), "fg_value_invalid")
        self.write("fear-greed.csv", "no,header\n1,2\n")
        self.assertEqual(self.code(), "fixture_unreadable_or_invalid")

    def test_bad_through_date(self):
        with self.assertRaises(InputError) as ctx:
            load_research_fixture(h.FIXTURE_DIR, through="2024-99-99")
        self.assertEqual(ctx.exception.code, "invalid_date")


class CliDoesNotCrash(unittest.TestCase):
    def run_cli(self, fixture_dir, *extra):
        cmd = [sys.executable, "-B", "-m", "v2_core.preview", "--fixture-dir", fixture_dir, "--date", "2024-10-02",
               "--sessions", os.path.join(DATA, "cli_sessions_synthetic.json")] + list(extra)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(cmd, cwd=h.ROOT, capture_output=True, text=True, env=env, timeout=120)

    def test_broken_state_file_exits_one_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="v2core-") as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(dict(GOOD, fixed_decision="SECRET-LIKE-VALUE")))
            p = self.run_cli(h.FIXTURE_DIR, "--state", path)
        self.assertEqual(p.returncode, 1)
        self.assertIn("state_invalid", p.stdout)
        self.assertEqual(p.stderr, "")
        self.assertNotIn("SECRET-LIKE-VALUE", p.stdout)

    def test_broken_fixture_directory_exits_one_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix="v2core-") as tmp:
            p = self.run_cli(tmp)
        self.assertEqual(p.returncode, 1)
        self.assertIn("fixture_unreadable_or_invalid", p.stdout)
        self.assertEqual(p.stderr, "")

    def test_sessions_file_with_wrong_shape_exits_one(self):
        with tempfile.TemporaryDirectory(prefix="v2core-") as tmp:
            path = os.path.join(tmp, "sessions.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"date": "2024-10-02"}))
            cmd = [sys.executable, "-B", "-m", "v2_core.preview", "--fixture-dir", h.FIXTURE_DIR, "--date",
                   "2024-10-02", "--sessions", path]
            p = subprocess.run(cmd, cwd=h.ROOT, capture_output=True, text=True, timeout=120,
                               env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stderr, "")


if __name__ == "__main__":
    unittest.main()
