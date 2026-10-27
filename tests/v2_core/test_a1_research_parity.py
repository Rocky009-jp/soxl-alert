"""A1: research parity against the stored signals.csv (37a14c0, delay 0, 465 rows).

Layer: research parity. The reference is the saved CSV plus a test-side port of the research signals();
the product state machine is compared only where its confirmed outputs must agree.
Delay-1 history is NOT checked against a stored oracle here (reported as unchecked).
"""
import hashlib
import unittest

import v2_helpers as h
from v2_core.engine import RuleStatus, evaluate_day
from v2_core.state import MarketState
from v2_core.tri import Tri
from v2_research_reference import research_signals

PIN = {
    "signals.csv": "6b830cbaf3982077f50e6f2f61ede8d883d7f8f5",
    "daily.json": "93f221eaba0b0b98044f13d0e8443d3c631650e0",
    "daily_adjclose.csv": "29175a3fd8700cab31762bd72ced772ea5d1c807",
    "fear-greed.csv": "cea860f848268aee30e7e6a4613efe1e8cf81bfa",
}
REPORT = {}


def blob(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tf(s):
    return s == "true"


class ParityBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.series, cls.fg = h.fixture()
        cls.csv = h.read_signals_csv()
        cls.by_date = {r["date"]: r for r in cls.csv}


class FixtureIdentity(ParityBase):
    def test_pinned_blobs_and_shape(self):
        import os
        self.assertEqual(blob(h.SIGNALS_CSV), PIN["signals.csv"])
        for name in ("daily.json", "daily_adjclose.csv", "fear-greed.csv"):
            self.assertEqual(blob(os.path.join(h.FIXTURE_DIR, name)), PIN[name], name)
        manifest = {m["file"]: m["git_blob"] for m in self.series.meta["input_manifest"]}
        for name in ("daily.json", "daily_adjclose.csv", "fear-greed.csv"):
            self.assertEqual(manifest[name], PIN[name])
        self.assertEqual(len(self.csv), 465)
        self.assertEqual((self.csv[0]["date"], self.csv[-1]["date"]), ("2024-10-01", "2026-08-10"))
        self.assertEqual(self.series.meta["price_definition"], "adj_close_total_return")
        self.assertEqual(self.series.meta["prehistory_start"], "2010-02-11")


class IndicatorRecompute(ParityBase):
    def test_indicators_recomputed_from_prehistory_match_csv(self):
        s = self.series.through("2026-08-10")
        worst = {"soxx": 0.0, "rsi": 0.0, "sma": 0.0, "shd": 0.0}
        for d, r in self.by_date.items():
            row = s.row(d)
            for key in worst:
                diff = abs(getattr(row, key) - float(r[key]))
                worst[key] = max(worst[key], diff)
        REPORT["max_abs_err"] = worst
        for key, val in worst.items():
            self.assertLessEqual(val, 1e-10, key)
        print("\n[A1] max abs error vs CSV (465 rows): %r" % worst)


class ReferencePortMatchesCsv(ParityBase):
    def test_full_history_research_port_matches_every_csv_day(self):
        s = self.series.through("2026-08-10")
        rows = []
        for i, d in enumerate(s.dates):
            shd = s.shd_at(d)
            rows.append({"date": d, "soxx": s.soxx[i], "rsi": s.rsi[i], "sma": s.sma[i], "shd": shd,
                         "fg": self.fg.get(d)})
        sig = research_signals(rows, delay=0, initial_armed=True)
        checked = 0
        for r in sig:
            c = self.by_date.get(r["date"])
            if not c:
                continue
            checked += 1
            self.assertEqual(r["fg_used"], float(c["fg_used"]) if c["fg_used"] else None, r["date"])
            self.assertEqual(r["armed"], tf(c["armed"]), r["date"])
            self.assertEqual(r["streak"], int(c["streak"]), r["date"])
            for k, ck in (("ex", "ex"), ("normal", "normal"), ("normal_raw", "normal_raw"), ("reCandidate", "reCandidate")):
                self.assertEqual(r[k], tf(c[ck]), (r["date"], k))
        self.assertEqual(checked, 465)
        REPORT["port_days_matched"] = checked


class ProductStateMachineVsCsv(ParityBase):
    """Product machine with a confirmed initial state taken from the CSV row of 2024-10-01."""

    def test_product_matches_csv_where_confirmed_and_never_contradicts(self):
        series = self.series
        all_dates = [d for d in series.dates if "2024-09-25" <= d <= "2026-08-11"]
        sessions = h.make_sessions(all_dates)
        first = self.by_date["2024-10-01"]
        state = MarketState("2024-10-01", Tri.TRUE if tf(first["armed"]) else Tri.FALSE, int(first["streak"]),
                            Tri.TRUE if tf(first["normal_raw"]) else Tri.FALSE)
        csv_dates = [r["date"] for r in self.csv][1:]
        missing_fg = [d for d in csv_dates if d not in self.fg]
        self.assertEqual(missing_fg, ["2026-03-12"])
        gap_day = "2026-03-12"
        stats = {"exact_days": 0, "after_gap_days": 0, "unconfirmed_ex_or_normal": 0}
        # first day on which 3 consecutive observed F&G >= 30 follow the gap (from CSV fg_used, not from the product)
        after = [r for r in self.csv if r["date"] > gap_day]
        expected_rearm = None
        run = 0
        for r in after:
            run = run + 1 if float(r["fg_used"]) >= 30 else 0
            if run >= 3:
                expected_rearm = r["date"]
                break
        seen_rearm = None
        for d in csv_dates:
            c = self.by_date[d]
            obs = [h.obs("r-" + d, d, self.fg[d])] if d in self.fg else []
            res = evaluate_day(state, d, series, sessions, obs)
            if d == gap_day:
                self.assertIs(res.next_state, state)          # waiting day: no state change
                self.assertIn("fg_not_recorded", res.notes)
                continue
            # TREND does not depend on armed: must match on every observed day
            self.assertEqual(res.rules["TREND"].status is RuleStatus.MET, tf(c["reCandidate"]), d)
            for name, key in (("EXFEAR", "ex"), ("NORMAL", "normal")):
                st = res.rules[name].status
                if st is RuleStatus.MET:
                    self.assertTrue(tf(c[key]), (d, name))
                elif st is RuleStatus.NOT_MET:
                    self.assertFalse(tf(c[key]), (d, name))
                else:
                    stats["unconfirmed_ex_or_normal"] += 1
            if d < gap_day:
                stats["exact_days"] += 1
                for name in ("EXFEAR", "NORMAL", "TREND"):
                    self.assertIsNot(res.rules[name].status, RuleStatus.UNCONFIRMED, (d, name))
                self.assertEqual(res.next_state.streak, int(c["streak"]), d)
                self.assertEqual(res.next_state.armed, Tri.TRUE if tf(c["armed"]) else Tri.FALSE, d)
                self.assertEqual(res.next_state.prev_normal_raw, Tri.TRUE if tf(c["normal_raw"]) else Tri.FALSE, d)
            else:
                stats["after_gap_days"] += 1
                if seen_rearm is None and res.next_state.armed is Tri.TRUE:
                    seen_rearm = d
                if seen_rearm is None:
                    self.assertIn(res.next_state.armed, (Tri.UNKNOWN, Tri.FALSE), d)
            state = res.next_state
        self.assertEqual(seen_rearm, expected_rearm)
        REPORT["product_vs_csv"] = dict(stats, rearm_date=seen_rearm)
        print("\n[A1] product vs CSV: %r" % REPORT["product_vs_csv"])


if __name__ == "__main__":
    unittest.main()
