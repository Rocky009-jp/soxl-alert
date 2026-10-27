"""A3 / A4 / A5: F&G not observed, state classes (confirmed / unknown), decision handling, re-run.

Layer: operational contract. Market rows are hand-written (StubSeries) and every expectation below is
fixed in the test text; no expected value is produced by product functions.
"""
import unittest

import v2_helpers as h
from v2_core.engine import ErrorResult, RuleStatus, RunClass, evaluate_day, run_day_safe
from v2_core.errors import ConflictError, InputError
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
SESS = h.make_sessions(DATES)
T, F, U = Tri.TRUE, Tri.FALSE, Tri.UNKNOWN


def series(**per_date):
    """Rows for every date; unspecified dates are weak (SOXX below SMA200)."""
    rows = []
    for d in DATES:
        rows.append(h.row(d, **per_date.get(d, h.WEAK)))
    return h.StubSeries(rows)


def st(as_of=None, armed=U, streak=0, prev=U):
    return MarketState(as_of, armed, streak, prev)


def status(res):
    return {k: v.status for k, v in res.rules.items()}


MET, NOT, PEND, UNC = RuleStatus.MET, RuleStatus.NOT_MET, RuleStatus.PENDING_FG, RuleStatus.UNCONFIRMED


class FgNotObserved(unittest.TestCase):
    D, P = DATES[1], DATES[0]

    def run_(self, state, **rows):
        return evaluate_day(state, self.D, series(**rows), SESS, [])

    def test_unknown_armed_weak_market_is_waiting_not_no_signal(self):
        r = self.run_(st())
        self.assertEqual(status(r), {"EXFEAR": PEND, "NORMAL": NOT, "TREND": NOT})
        self.assertTrue(r.rules["EXFEAR"].may_be_unconfirmed)
        self.assertIs(r.run_class, RunClass.WAITING_FG)
        self.assertEqual(r.exit_code, 0)

    def test_confirmed_false_armed_and_weak_market_is_no_signal(self):
        r = self.run_(st(self.P, F, 0, F))
        self.assertEqual(status(r), {"EXFEAR": NOT, "NORMAL": NOT, "TREND": NOT})
        self.assertIs(r.run_class, RunClass.NO_SIGNAL)

    def test_confirmed_true_armed_keeps_exfear_pending_without_unconfirmed_flag(self):
        r = self.run_(st(self.P, T, 4, F))
        self.assertEqual(r.rules["EXFEAR"].status, PEND)
        self.assertFalse(r.rules["EXFEAR"].may_be_unconfirmed)
        self.assertIs(r.run_class, RunClass.WAITING_FG)

    def test_normal_pending_when_market_side_met_and_rise_possible(self):
        r = self.run_(st(self.P, T, 0, F), **{self.D: h.NORMAL_OK})
        self.assertEqual(status(r), {"EXFEAR": PEND, "NORMAL": PEND, "TREND": NOT})
        self.assertFalse(r.rules["NORMAL"].may_be_unconfirmed)

    def test_normal_not_met_when_previous_day_also_normal_raw(self):
        r = self.run_(st(self.P, T, 0, T), **{self.D: h.NORMAL_OK})
        self.assertEqual(r.rules["NORMAL"].status, NOT)
        self.assertIn("not_a_rise_prev_normal_raw", r.rules["NORMAL"].reasons)

    def test_normal_not_met_when_armed_confirmed_false(self):
        r = self.run_(st(self.P, F, 0, F), **{self.D: h.NORMAL_OK})
        self.assertEqual(r.rules["NORMAL"].status, NOT)

    def test_trend_pending_only_when_market_side_cross(self):
        r = self.run_(st(self.P, F, 0, F), **{self.D: h.TREND_OK})
        self.assertEqual(r.rules["TREND"].status, PEND)
        self.assertIs(r.run_class, RunClass.WAITING_FG)

    def test_boundaries_are_strict(self):
        eq_sma = dict(soxx=100.0, sma=100.0, rsi=50.0, shd=-1.0, prev_rsi=49.0)
        self.assertEqual(self.run_(st(self.P, T, 0, F), **{self.D: eq_sma}).rules["NORMAL"].status, NOT)
        shd_zero = dict(soxx=110.0, rsi=50.0, shd=0.0, prev_rsi=49.0)
        self.assertEqual(self.run_(st(self.P, T, 0, F), **{self.D: shd_zero}).rules["NORMAL"].status, NOT)
        rsi55 = dict(soxx=110.0, rsi=55.0, shd=-1.0, prev_rsi=49.0)         # RSI <= 55 is allowed for NORMAL
        self.assertEqual(self.run_(st(self.P, T, 0, F), **{self.D: rsi55}).rules["NORMAL"].status, PEND)
        no_cross = dict(soxx=110.0, rsi=55.0, shd=1.0, prev_rsi=54.0)       # needs RSI > 55
        self.assertEqual(self.run_(st(self.P, T, 0, F), **{self.D: no_cross}).rules["TREND"].status, NOT)
        cross = dict(soxx=110.0, rsi=55.01, shd=1.0, prev_rsi=55.0)         # prev <= 55 and now > 55
        self.assertEqual(self.run_(st(self.P, T, 0, F), **{self.D: cross}).rules["TREND"].status, PEND)

    def test_waiting_day_does_not_change_state(self):
        base = st(self.P, T, 7, F)
        r = self.run_(base)
        self.assertIs(r.next_state, base)
        self.assertFalse(r.state_updated)
        self.assertIn("fg_not_recorded", r.notes)

    def test_not_checked_record_is_not_an_observation(self):
        nc = h.obs("n1", self.D, None, status="not_checked")
        r = evaluate_day(st(self.P, T, 7, F), self.D, series(), SESS, [nc])
        self.assertIsNone(r.decision)
        self.assertIs(r.run_class, RunClass.WAITING_FG)

    def test_supplemental_only_is_not_a_decision(self):
        r = evaluate_day(st(self.P, T, 7, F), self.D, series(), SESS, [h.obs("s1", self.D, 20, role="supplemental")])
        self.assertIsNone(r.decision)
        self.assertIs(r.run_class, RunClass.WAITING_FG)


class StateClasses(unittest.TestCase):
    def test_gap_degrades_armed_and_streak_and_derives_prev_normal_raw_from_market_only(self):
        base = st(DATES[0], T, 5, T)
        # previous session (DATES[2]) market side NORMAL false -> prev normal_raw is confirmed false even after a gap
        r = evaluate_day(base, DATES[3], series(**{DATES[3]: h.NORMAL_OK}), SESS, [])
        self.assertTrue(r.gap)
        self.assertEqual((r.effective_armed, r.effective_streak, r.effective_prev_normal_raw), (U, 0, F))
        self.assertEqual(r.rules["NORMAL"].status, PEND)
        self.assertTrue(r.rules["NORMAL"].may_be_unconfirmed)
        # previous session market side NORMAL true -> stays unknown
        r2 = evaluate_day(base, DATES[3], series(**{DATES[2]: h.NORMAL_OK, DATES[3]: h.NORMAL_OK}), SESS, [])
        self.assertEqual(r2.effective_prev_normal_raw, U)

    def test_initial_state_uses_unknown_never_false_or_zero_confirmed(self):
        r = evaluate_day(MarketState.initial(), DATES[1], series(), SESS, [])
        self.assertEqual((r.effective_armed, r.effective_prev_normal_raw), (U, F))   # prev derived: weak market
        r2 = evaluate_day(MarketState.initial(), DATES[1], series(**{DATES[0]: h.NORMAL_OK}), SESS, [])
        self.assertEqual(r2.effective_prev_normal_raw, U)

    def test_fg_below_25_with_unknown_armed_confirms_armed_false_but_not_the_fire(self):
        r = evaluate_day(MarketState.initial(), DATES[1], series(), SESS, [h.obs("a", DATES[1], 20)])
        self.assertEqual(r.rules["EXFEAR"].status, UNC)
        self.assertIs(r.run_class, RunClass.REFERENCE_UNCONFIRMED)
        ns = r.next_state
        self.assertEqual((ns.as_of_d, ns.armed, ns.streak, ns.prev_normal_raw), (DATES[1], F, 0, F))
        r2 = evaluate_day(ns, DATES[2], series(), SESS, [h.obs("b", DATES[2], 20)])
        self.assertEqual(r2.rules["EXFEAR"].status, NOT)          # armed is now confirmed false
        self.assertIs(r2.run_class, RunClass.NO_SIGNAL)

    def test_three_consecutive_observed_30_plus_confirm_armed(self):
        s, d_prev = MarketState.initial(), None
        expected = [(U, 1), (U, 2), (T, 3)]
        for d, (armed, streak) in zip(DATES[1:4], expected):
            r = evaluate_day(s, d, series(), SESS, [h.obs("r" + d, d, 31)])
            s = r.next_state
            self.assertEqual((s.armed, s.streak), (armed, streak), d)
        self.assertEqual(s.as_of_d, DATES[3])

    def test_trend_does_not_depend_on_unknown_armed(self):
        r = evaluate_day(MarketState.initial(), DATES[1], series(**{DATES[1]: h.TREND_OK}), SESS,
                         [h.obs("t", DATES[1], 33)])
        self.assertEqual(r.rules["TREND"].status, MET)
        self.assertEqual(r.rules["TREND"].ratio, 25)
        self.assertIs(r.run_class, RunClass.CONDITION_MET)
        self.assertEqual(r.next_state.armed, U)                    # not invented

    def test_normal_met_then_not_a_rise_then_reset(self):
        s = st(DATES[0], T, 0, F)
        r1 = evaluate_day(s, DATES[1], series(**{DATES[1]: h.NORMAL_OK}), SESS, [h.obs("a", DATES[1], 27)])
        self.assertEqual(r1.rules["NORMAL"].status, MET)
        self.assertEqual(r1.rules["NORMAL"].ratio, 100)
        self.assertIs(r1.next_state.prev_normal_raw, T)
        r2 = evaluate_day(r1.next_state, DATES[2], series(**{DATES[2]: h.NORMAL_OK}), SESS, [h.obs("b", DATES[2], 27)])
        self.assertEqual(r2.rules["NORMAL"].status, NOT)
        self.assertIs(r2.run_class, RunClass.NO_SIGNAL)
        r3 = evaluate_day(r2.next_state, DATES[3], series(), SESS, [h.obs("c", DATES[3], 33)])
        self.assertIs(r3.next_state.prev_normal_raw, F)

    def test_normal_with_unknown_armed_is_reference_only(self):
        r = evaluate_day(MarketState.initial(), DATES[1], series(**{DATES[1]: h.NORMAL_OK}), SESS,
                         [h.obs("a", DATES[1], 27)])
        self.assertEqual(r.rules["NORMAL"].status, UNC)
        self.assertIs(r.run_class, RunClass.REFERENCE_UNCONFIRMED)

    def test_exfear_fires_once_and_zero_is_a_valid_value(self):
        r = evaluate_day(st(DATES[0], T, 0, F), DATES[1], series(), SESS, [h.obs("a", DATES[1], 0)])
        self.assertEqual(r.rules["EXFEAR"].status, MET)
        self.assertEqual(r.next_state.armed, F)
        r2 = evaluate_day(r.next_state, DATES[2], series(), SESS, [h.obs("b", DATES[2], 0)])
        self.assertEqual(r2.rules["EXFEAR"].status, NOT)

    def test_fg_band_edges(self):
        s = st(DATES[0], T, 0, F)
        r25 = evaluate_day(s, DATES[1], series(**{DATES[1]: h.NORMAL_OK}), SESS, [h.obs("a", DATES[1], 25)])
        self.assertEqual((r25.rules["EXFEAR"].status, r25.rules["NORMAL"].status), (NOT, MET))
        r30 = evaluate_day(s, DATES[1], series(**{DATES[1]: h.TREND_OK}), SESS, [h.obs("a", DATES[1], 30)])
        self.assertEqual((r30.rules["NORMAL"].status, r30.rules["TREND"].status), (NOT, MET))

    def test_f_and_g_exactly_30_counts_toward_rearm_and_29_99_does_not(self):
        s = MarketState.initial()
        for d in DATES[1:4]:
            s = evaluate_day(s, d, series(), SESS, [h.obs("r" + d, d, 30)]).next_state
        self.assertEqual((s.armed, s.streak), (T, 3))
        s2 = evaluate_day(MarketState.initial(), DATES[1], series(), SESS, [h.obs("a", DATES[1], 29.99)]).next_state
        self.assertEqual(s2.streak, 0)

    def test_normal_band_upper_edge_is_exclusive(self):
        base = st(DATES[0], T, 0, F)
        at30 = evaluate_day(base, DATES[1], series(**{DATES[1]: h.NORMAL_OK}), SESS, [h.obs("a", DATES[1], 30)])
        below = evaluate_day(base, DATES[1], series(**{DATES[1]: h.NORMAL_OK}), SESS, [h.obs("a", DATES[1], 29.99)])
        self.assertEqual(at30.rules["NORMAL"].status, NOT)
        self.assertEqual(below.rules["NORMAL"].status, MET)

    def test_waiting_then_next_day_is_a_gap_never_reusing_old_armed(self):
        s1 = evaluate_day(st(DATES[0], T, 9, F), DATES[1], series(), SESS, [h.obs("a", DATES[1], 31)]).next_state
        self.assertEqual((s1.armed, s1.streak), (T, 10))
        w = evaluate_day(s1, DATES[2], series(), SESS, [])           # nothing recorded for DATES[2]
        self.assertIs(w.next_state, s1)
        r = evaluate_day(w.next_state, DATES[3], series(), SESS, [h.obs("c", DATES[3], 20)])
        self.assertTrue(r.gap)
        self.assertEqual(r.rules["EXFEAR"].status, UNC)               # old armed=TRUE is not reused


class InputValidation(unittest.TestCase):
    D, P = DATES[1], DATES[0]

    def safe(self, observations, state=None, sessions=SESS):
        state = state or st(self.P, T, 0, F)
        return state, run_day_safe(state, self.D, series(), sessions, observations)

    def test_bad_values_are_input_errors_not_unobserved(self):
        for bad in (True, False, float("nan"), float("inf"), float("-inf"), "", None, -0.1, 100.01, "abc",
                    "nan", "True", [], {}):
            state, res = self.safe([h.obs("a", self.D, bad)])
            self.assertIsInstance(res, ErrorResult, repr(bad))
            self.assertEqual(res.code, "fg_value_invalid", repr(bad))
            self.assertEqual(res.exit_code, 1)
            self.assertIs(res.next_state, state)

    def test_numeric_strings_in_range_are_accepted(self):
        _, res = self.safe([h.obs("a", self.D, "27.5")])
        self.assertEqual(res.decision.value, 27.5)

    def test_time_zone_target_role_status_and_id_errors(self):
        good = h.obs("a", self.D, 27)
        cases = {
            "datetime_missing_timezone": dict(good, observed_at_iso8601="2026-01-06T20:00:00"),
            "datetime_invalid": dict(good, observed_at_iso8601="not-a-time"),
            "role_unknown": dict(good, observation_role="final"),
            "status_unknown": dict(good, observation_status="maybe"),
            "record_id_invalid": dict(good, record_id=""),
            "target_session_missing": dict(good, target_us_session_date=""),
            "invalid_date": dict(good, target_us_session_date="2026-13-40"),
            "not_checked_has_value": dict(good, observation_status="not_checked"),
        }
        for code, bad in cases.items():
            _, res = self.safe([bad])
            self.assertIsInstance(res, ErrorResult, code)
            self.assertEqual(res.code, code)

    def test_decision_must_be_between_close_and_next_open(self):
        early = h.obs("a", self.D, 27, hour=15)         # before the 16:00 close
        late = dict(h.obs("a", self.D, 27), observed_at_iso8601="2026-01-07T10:00:00-05:00")   # after next open
        for bad in (early, late):
            _, res = self.safe([bad])
            self.assertEqual(res.code, "decision_outside_window")
        _, ok = self.safe([dict(h.obs("a", self.D, 27), observed_at_iso8601="2026-01-06T16:00:00-05:00")])
        self.assertIsNotNone(ok.decision)               # exactly at close is allowed

    def test_supplemental_is_not_window_checked_and_never_replaces_decision(self):
        base_state = st(self.P, T, 0, F)
        only = evaluate_day(base_state, self.D, series(), SESS, [h.obs("d", self.D, 20)])
        sup = dict(h.obs("s", self.D, 27, role="supplemental", hour=3))
        both = evaluate_day(base_state, self.D, series(), SESS, [sup, h.obs("d", self.D, 20)])
        self.assertEqual(only.next_state, both.next_state)
        self.assertEqual(status(only), status(both))

    def test_two_decisions_conflict_in_any_order_and_state_stays_unchanged(self):
        a, b = h.obs("a", self.D, 20), h.obs("b", self.D, 27)
        for lst in ([a, b], [b, a]):
            state, res = self.safe(lst)
            self.assertIs(res.run_class, RunClass.CONFLICT)
            self.assertEqual(res.code, "decision_conflict")
            self.assertEqual(res.exit_code, 1)
            self.assertIs(res.next_state, state)
            with self.assertRaises(ConflictError):
                evaluate_day(state, self.D, series(), SESS, lst)

    def test_identical_resubmission_is_a_noop_but_same_id_with_other_content_conflicts(self):
        a = h.obs("a", self.D, 20)
        _, res = self.safe([a, dict(a)])
        self.assertIsNotNone(res.decision)
        _, res2 = self.safe([a, h.obs("a", self.D, 21)])
        self.assertEqual(res2.code, "record_id_conflict")

    def test_observation_for_another_session_is_ignored_for_this_day(self):
        _, res = self.safe([h.obs("x", DATES[2], 20)])
        self.assertIsNone(res.decision)


class RerunAndPurity(unittest.TestCase):
    D, P = DATES[1], DATES[0]

    def test_same_inputs_same_outputs(self):
        base = st(self.P, T, 3, F)
        o = [h.obs("a", self.D, 31)]
        r1 = evaluate_day(base, self.D, series(), SESS, o)
        r2 = evaluate_day(base, self.D, series(), SESS, o)
        self.assertEqual(r1.next_state, r2.next_state)
        self.assertEqual(status(r1), status(r2))

    def test_rerun_from_applied_state_does_not_double_count(self):
        base = st(self.P, T, 3, F)
        o = [h.obs("a", self.D, 31)]
        first = evaluate_day(base, self.D, series(), SESS, o)
        self.assertEqual(first.next_state.streak, 4)
        again = evaluate_day(first.next_state, self.D, series(), SESS, o)
        self.assertEqual(again.next_state, first.next_state)       # streak stays 4, not 5
        self.assertFalse(again.state_updated)
        self.assertEqual(status(again), status(first))

    def test_rerun_with_other_decision_is_a_conflict_and_changes_nothing(self):
        base = st(self.P, T, 3, F)
        first = evaluate_day(base, self.D, series(), SESS, [h.obs("a", self.D, 31)])
        applied = first.next_state
        res = run_day_safe(applied, self.D, series(), SESS, [h.obs("z", self.D, 20)])
        self.assertIs(res.run_class, RunClass.CONFLICT)
        self.assertEqual(res.code, "decision_conflict_with_applied")
        self.assertIs(res.next_state, applied)

    def test_rerun_without_decision_and_future_state_are_errors(self):
        base = st(self.P, T, 3, F)
        first = evaluate_day(base, self.D, series(), SESS, [h.obs("a", self.D, 31)])
        with self.assertRaises(InputError) as ctx:
            evaluate_day(first.next_state, self.D, series(), SESS, [])
        self.assertEqual(ctx.exception.code, "rerun_decision_missing")
        with self.assertRaises(InputError) as ctx2:
            evaluate_day(st(DATES[3], T, 0, F), DATES[2], series(), SESS, [])
        self.assertEqual(ctx2.exception.code, "state_ahead_of_target")

    def test_lost_downstream_step_recomputes_from_saved_base(self):
        # a failed notification must not consume the day: recompute from the saved previous-day base
        base = st(self.P, F, 0, F)
        o = [h.obs("a", self.D, 20)]
        first = evaluate_day(base, self.D, series(), SESS, o)
        recomputed = evaluate_day(base, self.D, series(), SESS, o)
        self.assertEqual(first.next_state, recomputed.next_state)

    def test_state_round_trip_dict(self):
        first = evaluate_day(st(self.P, T, 3, F), self.D, series(), SESS, [h.obs("a", self.D, 31)])
        self.assertEqual(MarketState.from_dict(first.next_state.to_dict()), first.next_state)
        with self.assertRaises(InputError):
            MarketState.from_dict({"as_of_d": None, "armed": "MAYBE", "streak": 0, "prev_normal_raw": "FALSE"})


if __name__ == "__main__":
    unittest.main()
