"""Regression: an F&G value too large for a float is an InputError (fg_value_invalid), never an OverflowError.

The ledger is injected data. `float(10 ** 400)` raises OverflowError, which used to escape parse_observation,
select_decision, evaluate_day and prepare_day, and make run_day_safe crash instead of returning an ErrorResult.
Values that were accepted before (0 to 100, int / float / numeric text) and the refusals that already existed
(bool, non-finite, out of range, unreadable text, other types) are pinned here too so that the fix changes nothing else.
"""
import copy
import os
import sys
import unittest

import v2_helpers as h
from v2_core.engine import ErrorResult, RunClass, evaluate_day, run_day_safe
from v2_core.errors import InputError
from v2_core.observations import parse_observation, select_decision
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
SESS = h.make_sessions(DATES)
STATE = MarketState("2026-01-06", Tri.TRUE, 0, Tri.FALSE)
D = "2026-01-07"
HUGE = 10 ** 400
CODE = ("fg_value_invalid", "current_fg_value")


def stub():
    return h.StubSeries([h.row(d, **h.WEAK) for d in DATES])


def raw(value, role="decision", record_id="R1"):
    return h.obs(record_id, D, value, role=role)


class OverflowIsAnInputError(unittest.TestCase):
    VALUES = (HUGE, -HUGE, 10 ** 309, -10 ** 309)

    def assert_input_error(self, fn):
        with self.assertRaises(InputError) as cm:
            fn()
        self.assertEqual((cm.exception.code, cm.exception.field), CODE)

    def test_parse_observation(self):
        for v in self.VALUES:
            self.assert_input_error(lambda: parse_observation(raw(v)))

    def test_supplemental_records_are_parsed_too(self):
        for v in self.VALUES:
            self.assert_input_error(lambda: parse_observation(raw(v, role="supplemental")))

    def test_select_decision(self):
        for v in self.VALUES:
            self.assert_input_error(lambda: select_decision([raw(v)], SESS, D))

    def test_a_bad_record_next_to_a_good_decision_still_stops_the_day(self):
        for v in self.VALUES:
            ledger = [raw(30.0, record_id="R-good"), raw(v, role="supplemental", record_id="R-bad")]
            self.assert_input_error(lambda: select_decision(ledger, SESS, D))
            self.assert_input_error(lambda: evaluate_day(STATE, D, stub(), SESS, ledger))

    def test_evaluate_day(self):
        for v in self.VALUES:
            self.assert_input_error(lambda: evaluate_day(STATE, D, stub(), SESS, [raw(v)]))

    def test_run_day_safe_returns_an_error_result_and_leaves_the_state_alone(self):
        for v in self.VALUES:
            res = run_day_safe(STATE, D, stub(), SESS, [raw(v)])
            self.assertIsInstance(res, ErrorResult)
            self.assertEqual((res.code, res.field, res.exit_code, res.run_class), CODE + (1, RunClass.DATA_ERROR))
            self.assertFalse(res.state_updated)
            self.assertIs(res.next_state, STATE)

    def test_a_huge_value_is_not_turned_into_a_normal_no_signal(self):
        ok = run_day_safe(STATE, D, stub(), SESS, [raw(30.0)])
        self.assertNotIsInstance(ok, ErrorResult)
        bad = run_day_safe(STATE, D, stub(), SESS, [raw(HUGE)])
        self.assertIsInstance(bad, ErrorResult)

    def test_the_error_text_does_not_carry_the_digits(self):
        with self.assertRaises(InputError) as cm:
            parse_observation(raw(HUGE))
        digits = "1" + "0" * 50
        for text in (str(cm.exception), repr(cm.exception), str(cm.exception.detail)):
            self.assertNotIn(digits, text)

    def test_the_ledger_is_not_edited(self):
        ledger = [raw(HUGE)]
        before = copy.deepcopy(ledger)
        run_day_safe(STATE, D, stub(), SESS, ledger)
        self.assertEqual(ledger, before)


class OtherInputsAreUnchanged(unittest.TestCase):
    def test_accepted_values(self):
        for v, want in ((0, 0.0), (100, 100.0), (0.0, 0.0), (100.0, 100.0), (50, 50.0), (27.5, 27.5),
                        ("42.5", 42.5), (" 7 ", 7.0), ("100", 100.0), ("0", 0.0), (99.999, 99.999),
                        (10 ** 2, 100.0)):
            o = parse_observation(raw(v))
            self.assertEqual(o.value, want, v)
            self.assertIsInstance(o.value, float)

    def test_refusals_that_already_existed(self):
        for v in (True, False, float("nan"), float("inf"), float("-inf"), -0.1, 100.1, -1, 101, "abc", "", "nan",
                  "inf", "1e999", "1" + "0" * 400, "-" + "1" + "0" * 400, None, [], {}, (1,), b"5"):
            with self.assertRaises(InputError, msg=repr(v)[:40]) as cm:
                parse_observation(raw(v))
            self.assertEqual((cm.exception.code, cm.exception.field), CODE, repr(v)[:40])

    def test_a_ledger_with_a_normal_value_gives_the_same_day_result_as_before(self):
        res = evaluate_day(STATE, D, stub(), SESS, [raw(27.0)])
        self.assertEqual(res.decision.value, 27.0)
        self.assertEqual(res.d, D)


class PreparedDayStopsWithoutChangingTheStore(unittest.TestCase):
    """The S1 single-day runner passes the same ledger through the same core entry points."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(h.ROOT, "tests", "v2_persistence"))
        import p_helpers
        cls.p = p_helpers

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(os.path.join(h.ROOT, "tests", "v2_persistence"))

    def world(self):
        p = self.p
        w = p.World()
        w.apply(p.DATES[1], 27.0)
        w.apply(p.DATES[2], 40.0)
        return w

    def snapshot_of(self, w):
        s = w.snap()
        return copy.deepcopy(s.to_dict()), s.head_seq, s.head_hash

    def test_prepare_day_stops_with_the_same_code_and_field(self):
        p = self.p
        for v in (HUGE, -HUGE):
            w = self.world()
            before = self.snapshot_of(w)
            w.ledger.append(p.obs("R-big", p.DATES[3], v))
            with self.assertRaises(InputError) as cm:
                w.prepare(p.DATES[3])
            self.assertEqual((cm.exception.code, cm.exception.field), CODE)
            self.assertEqual(self.snapshot_of(w), before)

    def test_a_huge_value_in_a_day_already_stored_also_stops(self):
        p = self.p
        w = self.world()
        before = self.snapshot_of(w)
        w.ledger.append(p.obs("R-big", p.DATES[1], HUGE, role="supplemental"))
        with self.assertRaises(InputError) as cm:
            w.prepare(p.DATES[2])
        self.assertEqual((cm.exception.code, cm.exception.field), CODE)
        self.assertEqual(self.snapshot_of(w), before)

    def test_the_same_ledger_without_the_bad_record_still_prepares(self):
        p = self.p
        w = self.world()
        w.ledger.append(p.obs("R-ok", p.DATES[3], 55.0))
        res = w.prepare(p.DATES[3])
        self.assertIsNotNone(res.plan)

    def test_a_huge_number_inside_a_saved_snapshot_is_still_snapshot_invalid(self):
        p = self.p
        from v2_persistence.codec import decode_snapshot, encode_snapshot
        from v2_persistence.errors import PersistenceError
        from v2_persistence.events import input_hash_of
        from v2_persistence.recompute import validate_snapshot
        w = self.world()

        def mutate(evs):
            evs[1]["confirmed_inputs"]["decision"]["current_fg_value"] = HUGE
            evs[1]["input_hash"] = input_hash_of(evs[1]["confirmed_inputs"])

        snap = decode_snapshot(encode_snapshot(p.tampered(w.snap(), mutate)))
        with self.assertRaises(PersistenceError) as cm:
            validate_snapshot(snap)
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "decision"))


if __name__ == "__main__":
    unittest.main()
