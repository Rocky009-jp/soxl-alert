"""A-02 / A-03: persisted-state checks (P-04), record_id rule (P-06), and state round trips.

Expected values are written here by hand (rule ids, accept/reject lists); none is taken from product output.
"""
import copy
import unittest

import v2_helpers as h
from v2_core.display import render
from v2_core.engine import ErrorResult, RunClass, evaluate_day, run_day_safe
from v2_core.errors import InputError
from v2_core.observations import parse_observation
from v2_core.state import MarketState
from v2_core.tri import Tri

FP = "f" * 64
BASE = {"as_of_d": "2026-01-05", "armed": "UNKNOWN", "streak": 0, "prev_normal_raw": "UNKNOWN",
        "fixed_decision": None, "base": None}
GOOD = {"as_of_d": "2026-01-06", "armed": "TRUE", "streak": 2, "prev_normal_raw": "FALSE",
        "fixed_decision": {"d": "2026-01-06", "record_id": "a", "fingerprint": FP}, "base": BASE}
INITIAL = {"as_of_d": None, "armed": "UNKNOWN", "streak": 0, "prev_normal_raw": "UNKNOWN",
           "fixed_decision": None, "base": None}


def with_(data, **changes):
    out = copy.deepcopy(data)
    out.update(changes)
    return out


def with_base(**changes):
    return with_(GOOD, base=with_(BASE, **changes))


def rule_of(case, data):
    with case.assertRaises(InputError) as ctx:
        MarketState.from_dict(data)
    exc = ctx.exception
    case.assertEqual((exc.code, exc.field), ("state_invalid", "state"))
    case.assertEqual(str(exc), "state_invalid:state")          # the message holds no value
    return getattr(exc, "rule", None)


class CurrentStateRules(unittest.TestCase):
    """I-01..I-07 on the top level, one violation at a time."""

    def test_the_good_state_is_accepted(self):
        s = MarketState.from_dict(GOOD)
        self.assertEqual((s.as_of_d, s.armed, s.streak, s.prev_normal_raw), ("2026-01-06", Tri.TRUE, 2, Tri.FALSE))
        self.assertEqual(s.base.as_of_d, "2026-01-05")

    def test_each_violation_is_rejected_with_its_own_rule(self):
        no_fixed = with_(GOOD, fixed_decision=None)
        no_base = with_(GOOD, base=None)
        cases = [
            ("I-01", no_fixed),                                                    # as_of, base, but no fixed_decision
            ("I-01", no_base),                                                     # as_of, fixed_decision, but no base
            ("I-01", with_(GOOD, as_of_d=None, armed="UNKNOWN", streak=0, prev_normal_raw="UNKNOWN")),
            ("I-01", with_(GOOD, as_of_d=None, armed="UNKNOWN", streak=0, prev_normal_raw="UNKNOWN",
                           fixed_decision=None)),                                  # only base left
            ("I-01", with_(INITIAL, fixed_decision=GOOD["fixed_decision"])),       # only fixed_decision
            ("I-01", with_(GOOD, as_of_d="2026-01-06", fixed_decision=None, base=None)),
            ("I-02", with_(INITIAL, armed="TRUE")),
            ("I-02", with_(INITIAL, armed="FALSE")),
            ("I-02", with_(INITIAL, streak=1)),
            ("I-02", with_(INITIAL, prev_normal_raw="FALSE")),
            ("I-02", with_(INITIAL, prev_normal_raw="TRUE")),
            ("I-03", with_(GOOD, fixed_decision=dict(GOOD["fixed_decision"], d="2026-01-05"))),
            ("I-03", with_(GOOD, fixed_decision=dict(GOOD["fixed_decision"], d="2026-01-07"))),
            ("I-04", with_(GOOD, base=with_(BASE, as_of_d="2026-01-06"))),         # equal
            ("I-04", with_(GOOD, base=with_(BASE, as_of_d="2026-01-07"))),         # later
            ("I-05", with_(GOOD, streak=3, armed="FALSE")),
            ("I-05", with_(GOOD, streak=3, armed="UNKNOWN")),
            ("I-05", with_(GOOD, streak=7, armed="FALSE")),
            ("I-06", with_(GOOD, streak=1, prev_normal_raw="TRUE")),
            ("I-06", with_(GOOD, streak=2, prev_normal_raw="UNKNOWN")),
            ("I-06", with_(GOOD, streak=3, prev_normal_raw="TRUE")),
        ]
        for expected, data in cases:
            self.assertEqual(rule_of(self, data), expected, (expected, data["armed"], data["streak"]))

    def test_fingerprint_and_record_id_format(self):
        fixed = GOOD["fixed_decision"]
        bad_fp = ["F" * 64, "f" * 63, "f" * 65, "g" * 64, "", "f" * 64 + "\n", "A" + "f" * 63, "ｆ" * 64]
        for fp in bad_fp:
            self.assertEqual(rule_of(self, with_(GOOD, fixed_decision=dict(fixed, fingerprint=fp))), "I-07", repr(fp))
        for rid in ["", "-a", ".a", "_a", "a b", "a/b", "https://x.example/p", "a@b", "a?b", "a\n", "ａ", "é", "a" * 65]:
            self.assertEqual(rule_of(self, with_(GOOD, fixed_decision=dict(fixed, record_id=rid))), "I-07", repr(rid))
        ok = ["a", "A", "0", "a-b_c.d", "9" + "z" * 63, "cli-1", "r-2026-01-06"]
        for rid in ok:
            MarketState.from_dict(with_(GOOD, fixed_decision=dict(fixed, record_id=rid)))
        MarketState.from_dict(with_(GOOD, fixed_decision=dict(fixed, fingerprint="0123456789abcdef" * 4)))

    def test_shape_errors_stay_state_invalid(self):
        for data in ["x", None, [], 5, with_(GOOD, as_of_d="2026-13-01"), with_(GOOD, armed="MAYBE"),
                     with_(GOOD, streak=True), with_(GOOD, streak=-1), with_(GOOD, streak=1.5),
                     with_(GOOD, fixed_decision="x"), with_(GOOD, base="x"), with_(GOOD, base=[]),
                     with_(GOOD, base={}), with_(GOOD, base=0),
                     with_(GOOD, fixed_decision={"d": "2026-01-06", "record_id": 5, "fingerprint": FP})]:
            self.assertEqual(rule_of(self, data), "shape", repr(data)[:50])
        missing = copy.deepcopy(GOOD)
        del missing["prev_normal_raw"]
        self.assertEqual(rule_of(self, missing), "shape")


class BaseRules(unittest.TestCase):
    """IB-01..IB-03 on the nested base only; the top-level rules must not be applied to it."""

    def test_normal_base_is_accepted(self):
        # as_of_d present, no fixed_decision, no base: the shape the engine itself writes (K-07)
        s = MarketState.from_dict(GOOD)
        self.assertIsNone(s.base.fixed_decision)
        self.assertIsNone(s.base.base)
        self.assertEqual(s.base.as_of_d, "2026-01-05")

    def test_base_without_keys_is_accepted(self):
        data = copy.deepcopy(GOOD)
        del data["base"]["fixed_decision"], data["base"]["base"]
        self.assertEqual(MarketState.from_dict(data).base.as_of_d, "2026-01-05")

    def test_base_that_is_the_initial_state_is_accepted(self):
        # first application after GENESIS: the base has no as_of_d (K-09)
        s = MarketState.from_dict(with_(GOOD, base=copy.deepcopy(INITIAL)))
        self.assertEqual(s.base, MarketState.initial())

    def test_base_with_any_valid_arithmetic_is_accepted(self):
        for armed, streak, prev in [("TRUE", 3, "FALSE"), ("TRUE", 5, "FALSE"), ("FALSE", 1, "FALSE"),
                                    ("UNKNOWN", 2, "FALSE"), ("FALSE", 0, "TRUE"), ("UNKNOWN", 0, "UNKNOWN")]:
            MarketState.from_dict(with_base(armed=armed, streak=streak, prev_normal_raw=prev))

    def test_each_violation_is_rejected_with_its_own_rule(self):
        cases = [
            ("IB-01", with_base(fixed_decision=GOOD["fixed_decision"])),
            ("IB-01", with_base(base=copy.deepcopy(BASE))),                       # nested one level further
            ("IB-01", with_base(fixed_decision=GOOD["fixed_decision"], base=copy.deepcopy(BASE))),
            ("IB-02", with_base(as_of_d=None, armed="TRUE")),
            ("IB-02", with_base(as_of_d=None, armed="FALSE")),
            ("IB-02", with_base(as_of_d=None, streak=1, prev_normal_raw="FALSE")),
            ("IB-02", with_base(as_of_d=None, prev_normal_raw="FALSE")),
            ("IB-03", with_base(streak=3, armed="FALSE", prev_normal_raw="FALSE")),
            ("IB-03", with_base(streak=3, armed="UNKNOWN", prev_normal_raw="FALSE")),
            ("IB-03", with_base(streak=1, prev_normal_raw="TRUE")),
            ("IB-03", with_base(streak=2, armed="TRUE", prev_normal_raw="UNKNOWN")),
        ]
        for expected, data in cases:
            self.assertEqual(rule_of(self, data), expected, expected)

    def test_top_level_rules_are_not_applied_to_the_base(self):
        # I-01 would reject this base (as_of_d without fixed_decision/base) if it were applied to it
        self.assertEqual(MarketState.from_dict(GOOD).base.fixed_decision, None)
        # I-04 is about base vs top level; a base is not compared with itself
        MarketState.from_dict(with_base(as_of_d="2026-01-01"))

    def test_current_state_rules_are_still_applied_when_the_base_is_fine(self):
        self.assertEqual(rule_of(self, with_(GOOD, streak=3, armed="FALSE")), "I-05")


class RecordIdOnObservations(unittest.TestCase):
    """P-06 at observation parsing: allowed set, boundaries, and no echo of the value."""

    D = "2026-01-06"

    def parse(self, rid):
        return parse_observation(h.obs(rid, self.D, 27))

    def test_accepted(self):
        for rid in ["a", "Z", "0", "a.b", "a_b", "a-b", "a1.B2_c3-d4", "r" * 64, "9" + "-" * 63,
                    "cli-1", "SECRET-ID-XYZ", "r-2026-01-06"]:
            self.assertEqual(self.parse(rid).record_id, rid)

    def test_rejected(self):
        bad = ["", " ", "a b", " a", "a ", "r" * 65, ".a", "-a", "_a", "https://x.example/a", "a://b", "a/b", "a\\b",
               "a@b", "a?b", "a#b", "a:b", "a,b", "a\n", "\na", "a\tb", "a\x00", "ａｂ", "あ", "aあ", "é", "a\u00e9",
               "\u2460", "٣", "a" * 100]
        for rid in bad:
            with self.assertRaises(InputError) as ctx:
                self.parse(rid)
            self.assertEqual((ctx.exception.code, ctx.exception.field), ("record_id_invalid", "record_id"), repr(rid))
            self.assertEqual(str(ctx.exception), "record_id_invalid:record_id")

    def test_non_strings_are_rejected(self):
        for rid in [None, 5, 1.5, True, ["a"], {"a": 1}, b"a"]:
            with self.assertRaises(InputError) as ctx:
                self.parse(rid)
            self.assertEqual(ctx.exception.code, "record_id_invalid", repr(rid))

    def test_a_bad_id_stops_the_run_and_the_text_never_shows_it(self):
        sess = h.make_sessions(["2026-01-05", "2026-01-06", "2026-01-07"])
        series = h.StubSeries([h.row("2026-01-05", **h.NORMAL_OK), h.row(self.D, **h.NORMAL_OK)])
        state = MarketState("2026-01-05", Tri.TRUE, 0, Tri.FALSE)
        secret = "https://discord.com/api/webhooks/SECRET123/TOKEN456"
        for rid in (secret, "SECRET 123", "SECRET123\n", "ｓｅｃｒｅｔ"):
            res = run_day_safe(state, self.D, series, sess, [h.obs(rid, self.D, 27)])
            self.assertIsInstance(res, ErrorResult)
            self.assertEqual((res.code, res.exit_code, res.state_updated), ("record_id_invalid", 1, False))
            self.assertIs(res.next_state, state)
            out = render(res) + repr(res.code) + repr(res.field) + repr(res.detail)
            for needle in ("SECRET", "TOKEN", "discord", "webhooks", "http", "ｓｅｃ"):
                self.assertNotIn(needle, out)

    def test_an_invalid_id_in_a_supplemental_record_also_stops_the_run(self):
        sess = h.make_sessions(["2026-01-05", "2026-01-06", "2026-01-07"])
        series = h.StubSeries([h.row("2026-01-05", **h.NORMAL_OK), h.row(self.D, **h.NORMAL_OK)])
        state = MarketState("2026-01-05", Tri.TRUE, 0, Tri.FALSE)
        res = run_day_safe(state, self.D, series, sess, [h.obs("bad id", self.D, 20, role="supplemental")])
        self.assertEqual(res.code, "record_id_invalid")


class RecordIdOnPersistedState(unittest.TestCase):
    """P-06 at state reading: fixed_decision.record_id, same set, state_invalid and no echo."""

    def test_boundaries(self):
        fixed = GOOD["fixed_decision"]
        for rid in ["a", "r" * 64, "0.-_", "A" * 64]:
            MarketState.from_dict(with_(GOOD, fixed_decision=dict(fixed, record_id=rid)))
        for rid in ["", "r" * 65, ".a", "-a", "_a", "a b", "a://b", "a/b", "a@b", "a?b", "a\n", "ａ", "あ"]:
            self.assertEqual(rule_of(self, with_(GOOD, fixed_decision=dict(fixed, record_id=rid))), "I-07", repr(rid))

    def test_error_does_not_contain_the_value(self):
        secret = "https://discord.com/api/webhooks/SECRET123/TOKEN456"
        data = with_(GOOD, fixed_decision=dict(GOOD["fixed_decision"], record_id=secret))
        with self.assertRaises(InputError) as ctx:
            MarketState.from_dict(data)
        e = ctx.exception
        text = " ".join([str(e), repr(e), e.code, str(e.field), str(e.detail), str(getattr(e, "rule", ""))])
        for needle in ("SECRET", "TOKEN", "discord", "http"):
            self.assertNotIn(needle, text)
        res = ErrorResult(None, e.code, e.field, RunClass.DATA_ERROR, MarketState.initial())
        for needle in ("SECRET", "TOKEN", "discord", "http"):
            self.assertNotIn(needle, render(res))

    def test_a_state_written_from_an_accepted_id_reads_back(self):
        sess = h.make_sessions(["2026-01-05", "2026-01-06", "2026-01-07"])
        series = h.StubSeries([h.row("2026-01-05", **h.NORMAL_OK), h.row("2026-01-06", **h.NORMAL_OK)])
        res = evaluate_day(MarketState("2026-01-05", Tri.TRUE, 0, Tri.FALSE), "2026-01-06", series, sess,
                           [h.obs("A1.b_c-" + "x" * 57, "2026-01-06", 27.5)])      # 64 characters
        self.assertEqual(len(res.next_state.fixed_decision["record_id"]), 64)
        self.assertEqual(MarketState.from_dict(res.next_state.to_dict()), res.next_state)


class RoundTripFromPersistable(unittest.TestCase):
    """A-03: to_dict -> from_dict is the identity for states that start from a persistable state.

    States built directly with an incomplete shape are out of scope here (they are trusted internal input);
    rejection of invalid persisted states is tested above.
    """

    DATES = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10",
             "2026-03-11", "2026-03-12", "2026-03-13", "2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19"]
    # (date, F&G or None for a day without a record). Includes a missed session (03-06), a 3-streak, a re-arm gap.
    PLAN = [("2026-03-03", 20), ("2026-03-04", 27.5), ("2026-03-05", None), ("2026-03-06", None),
            ("2026-03-09", 31), ("2026-03-10", 32), ("2026-03-11", 33), ("2026-03-12", 34),
            ("2026-03-13", None), ("2026-03-17", 24), ("2026-03-18", 28)]

    def series(self):
        rows = []
        for i, d in enumerate(self.DATES):
            kind = (h.NORMAL_OK, h.TREND_OK, h.WEAK)[i % 3]
            rows.append(h.row(d, **kind))
        return h.StubSeries(rows)

    def walk(self, start, via_dict):
        sess = h.make_sessions(self.DATES)
        series = self.series()
        state = start
        stages = [state]
        for d, fg in self.PLAN:
            raw = [] if fg is None else [h.obs("r-" + d, d, fg)]
            res = evaluate_day(state, d, series, sess, raw)
            stages.append(res.next_state)
            if fg is not None:                                   # the same D again: a re-run
                again = evaluate_day(res.next_state, d, series, sess, raw)
                self.assertFalse(again.state_updated)
                stages.append(again.next_state)
            state = res.next_state
            if via_dict:
                state = MarketState.from_dict(state.to_dict())
        return stages

    def check(self, stages):
        for i, s in enumerate(stages):
            self.assertEqual(MarketState.from_dict(s.to_dict()), s, i)

    def test_from_the_initial_state(self):
        stages = self.walk(MarketState.initial(), via_dict=False)
        self.assertGreater(len(stages), 15)
        self.check(stages)

    def test_from_a_state_that_went_through_from_dict(self):
        stages = self.walk(MarketState.from_dict(INITIAL), via_dict=True)
        self.check(stages)

    def test_from_a_good_persisted_state(self):
        start = MarketState.from_dict(with_(GOOD, as_of_d="2026-03-02",
                                            fixed_decision=dict(GOOD["fixed_decision"], d="2026-03-02"),
                                            base=with_(BASE, as_of_d="2026-03-01")))
        self.check(self.walk(start, via_dict=True))

    def test_the_walk_covers_a_gap_a_streak_and_an_armed_state(self):
        sess = h.make_sessions(self.DATES)
        series = self.series()
        state = MarketState.initial()
        seen = set()
        for d, fg in self.PLAN:
            res = evaluate_day(state, d, series, sess, [] if fg is None else [h.obs("r-" + d, d, fg)])
            seen.add(("gap", res.gap))
            seen.add(("armed", res.next_state.armed))
            seen.add(("streak3", res.next_state.streak >= 3))
            state = res.next_state
        self.assertTrue({("gap", True), ("gap", False), ("armed", Tri.TRUE), ("armed", Tri.FALSE),
                         ("streak3", True)} <= seen)


if __name__ == "__main__":
    unittest.main()
