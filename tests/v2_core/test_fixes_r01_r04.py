"""Review fixes R-01..R-04, P-01..P-03 (reviewer report on cd25676) and spec S-2(a)."""
import unittest
from datetime import datetime, timedelta, timezone

import v2_helpers as h
from v2_core.display import render, render_message, render_summary
from v2_core.engine import ErrorResult, RunClass, evaluate_day, run_day_safe
from v2_core.errors import ConflictError, InputError
from v2_core.observations import Observation, parse_observation, select_decision
from v2_core.sessions import parse_aware_datetime
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
SESS = h.make_sessions(DATES)
D = "2026-01-09"
PREV = "2026-01-08"
ARMED = MarketState(PREV, Tri.TRUE, 0, Tri.FALSE)


def series(per=None):
    per = per or {}
    s = h.StubSeries([h.row(d, **per.get(d, h.WEAK)) for d in DATES])
    s.closes[D] = 48.00
    return s


class R01TrendBlockWhileWaitingForFG(unittest.TestCase):
    """R-01: with F&G not yet recorded and the trend rule pending, show what to check by hand (no assertions)."""

    def result(self):
        return evaluate_day(ARMED, D, series({D: h.TREND_OK}), SESS, [])

    def test_waiting_with_pending_trend_shows_profile_block(self):
        r = self.result()
        self.assertIs(r.run_class, RunClass.WAITING_FG)
        t = render_message(r)
        for needle in ("0株の場合のみ", "初回", "再参加", "D−S≧3", "next(D)=2026-01-12", "再通知はありません",
                       "本人のSは未入力"):
            self.assertIn(needle, t, needle)
        self.assertNotIn("条件が成立した場合の口座条件は、手元で確認してください", t)

    def test_waiting_block_still_asserts_nothing_about_the_user(self):
        t = render_message(self.result())
        for phrase in ("購入条件確定", "あなたのP20が成立", "初回です", "再参加です", "売却を推奨"):
            self.assertNotIn(phrase, t)
        self.assertIn("F&G現在値（目視）: 未記録 → 購入条件は未確定です。", t)

    def test_waiting_without_pending_trend_has_no_trend_block(self):
        r = evaluate_day(ARMED, D, series({D: h.WEAK}), SESS, [])
        t = render_message(r)
        self.assertIn("条件が成立した場合の口座条件は、手元で確認してください", t)
        self.assertNotIn("0株の場合のみ", t)

    def test_observed_met_trend_text_unchanged(self):
        r = evaluate_day(ARMED, D, series({D: h.TREND_OK}), SESS, [h.obs("r", D, 33)])
        t = render_message(r)
        self.assertIn("0株の場合のみ", t)
        self.assertNotIn("再通知はありません", t)


class R02IntermediateSessionUnprocessed(unittest.TestCase):
    def state_at(self, d, armed=Tri.TRUE):
        return MarketState(d, armed, 1, Tri.FALSE)

    def test_observed_but_unprocessed_middle_session_is_an_input_error(self):
        st = self.state_at("2026-01-06")                      # last processed: 01-06; 01-07 observed; D=01-09
        raw = [h.obs("m", "2026-01-07", 40), h.obs("d", D, 40)]
        with self.assertRaises(InputError) as ctx:
            evaluate_day(st, D, series(), SESS, raw)
        self.assertEqual(ctx.exception.code, "intermediate_session_unprocessed")
        self.assertEqual(ctx.exception.detail, "2026-01-07")

    def test_safe_wrapper_reports_data_error_with_detail_and_keeps_state(self):
        st = self.state_at("2026-01-06")
        raw = [h.obs("m", "2026-01-07", 40), h.obs("d", D, 40)]
        r = run_day_safe(st, D, series(), SESS, raw)
        self.assertIsInstance(r, ErrorResult)
        self.assertIs(r.run_class, RunClass.DATA_ERROR)
        self.assertEqual((r.code, r.detail, r.exit_code, r.state_updated), ("intermediate_session_unprocessed",
                                                                          "2026-01-07", 1, False))
        self.assertEqual(r.next_state, st)
        t = render(r)
        self.assertIn("先に処理するセッション: 2026-01-07", t)
        self.assertIn("自動で過去は処理しません", t)
        self.assertIn("条件未達ではありません", t)

    def test_earliest_unprocessed_session_is_named(self):
        st = self.state_at("2026-01-05")
        raw = [h.obs("b", "2026-01-07", 40), h.obs("a", "2026-01-06", 40), h.obs("d", D, 40)]
        r = run_day_safe(st, D, series(), SESS, raw)
        self.assertEqual(r.detail, "2026-01-06")

    def test_no_observation_in_between_is_still_a_plain_gap(self):
        st = self.state_at("2026-01-06")
        r = evaluate_day(st, D, series(), SESS, [h.obs("d", D, 40)])
        self.assertIs(r.state_updated, True)
        self.assertEqual(r.next_state.armed, Tri.UNKNOWN)         # missing session -> armed UNKNOWN, streak restarts
        self.assertEqual(r.next_state.streak, 1)                  # (reset to 0, then D's own F&G 40 counts once)

    def test_supplemental_unobserved_or_out_of_window_middle_records_do_not_trigger(self):
        st = self.state_at("2026-01-06")
        mid = "2026-01-07"
        out_of_window = dict(h.obs("m3", mid, 40), observed_at_iso8601="2026-01-06T20:00:00-05:00")   # before close(mid)
        cases = {
            "supplemental": h.obs("m1", mid, 40, role="supplemental"),
            "not_checked": h.obs("m2", mid, 0, status="not_checked"),
            "out_of_window": out_of_window,
        }
        for name, o in cases.items():
            r = evaluate_day(st, D, series(), SESS, [o, h.obs("d", D, 40)])
            self.assertIs(r.state_updated, True, name)
            self.assertEqual(r.next_state.armed, Tri.UNKNOWN, name)

    def test_sequential_processing_still_works(self):
        st = MarketState(None, Tri.UNKNOWN, 0, Tri.UNKNOWN)
        raw = [h.obs("a", "2026-01-07", 40), h.obs("b", "2026-01-08", 40), h.obs("c", D, 40)]
        for d in ("2026-01-07", "2026-01-08", D):
            r = evaluate_day(st, d, series(), SESS, raw)
            st = r.next_state
        self.assertEqual(st.as_of_d, D)

    def test_same_day_rerun_is_not_blocked(self):
        raw = [h.obs("d", D, 40)]
        first = evaluate_day(ARMED, D, series(), SESS, raw)
        again = evaluate_day(first.next_state, D, series(), SESS, raw)
        self.assertEqual(again.next_state, first.next_state)

    def test_error_text_has_no_raw_input(self):
        st = self.state_at("2026-01-06")
        r = run_day_safe(st, D, series(), SESS, [h.obs("SECRET-ID-XYZ", "2026-01-07", 40), h.obs("d", D, 40)])
        self.assertNotIn("SECRET-ID-XYZ", render(r))


class R03TargetMismatch(unittest.TestCase):
    def test_decision_in_window_with_wrong_target_is_input_error(self):
        wrong = dict(h.obs("w", D, 40), target_us_session_date="2026-01-08")     # observed in D's window, targets D-1
        with self.assertRaises(InputError) as ctx:
            select_decision([wrong], SESS, D)
        self.assertEqual((ctx.exception.code, ctx.exception.field), ("target_mismatch", "target_us_session_date"))

    def test_run_day_safe_gives_data_error_and_text(self):
        wrong = dict(h.obs("w", D, 40), target_us_session_date="2026-01-12")
        r = run_day_safe(ARMED, D, series(), SESS, [wrong])
        self.assertIs(r.run_class, RunClass.DATA_ERROR)
        self.assertEqual(r.code, "target_mismatch")
        self.assertEqual(r.next_state, ARMED)
        self.assertIn("米国セッションの日付", render(r))

    def test_other_days_proper_ledger_rows_are_allowed(self):
        prev_day = h.obs("p", PREV, 40)              # observed in PREV's window, targets PREV: not in D's window
        r = evaluate_day(ARMED, D, series(), SESS, [prev_day, h.obs("d", D, 40)])
        self.assertEqual(r.decision.record_id, "d")

    def test_supplemental_and_unobserved_with_other_target_are_ignored(self):
        sup = dict(h.obs("s", D, 40, role="supplemental"), target_us_session_date="2026-01-08")
        un = h.obs("u", "2026-01-08", 0, status="not_checked")
        r = evaluate_day(ARMED, D, series(), SESS, [sup, un])
        self.assertIsNone(r.decision)


class R04TimeFormat(unittest.TestCase):
    def ok(self, text):
        return parse_aware_datetime(text, "f")

    def err(self, text):
        with self.assertRaises(InputError) as ctx:
            parse_aware_datetime(text, "f")
        return ctx.exception.code

    def test_accepted_forms(self):
        cases = {
            "2026-01-09T20:00-05:00": (20, 0, 0, 0, -5 * 3600),
            "2026-01-09T20:00:30-05:00": (20, 0, 30, 0, -5 * 3600),
            "2026-01-09T20:00:30.5+09:00": (20, 0, 30, 500000, 9 * 3600),
            "2026-01-09T20:00:30.123456Z": (20, 0, 30, 123456, 0),
            "2026-01-09T20:00:30.1Z": (20, 0, 30, 100000, 0),
            "2026-01-09T20:00Z": (20, 0, 0, 0, 0),
            "2026-01-09T05:30:00+05:30": (5, 30, 0, 0, 19800),
            "2026-01-09T23:59:59-00:00": (23, 59, 59, 0, 0),
        }
        for text, (hh, mm, ss, us, off) in cases.items():
            dt = self.ok(text)
            self.assertEqual((dt.hour, dt.minute, dt.second, dt.microsecond), (hh, mm, ss, us), text)
            self.assertEqual(dt.utcoffset(), timedelta(seconds=off), text)

    def test_missing_time_zone(self):
        for text in ("2026-01-09T20:00", "2026-01-09T20:00:30", "2026-01-09T20:00:30.25"):
            self.assertEqual(self.err(text), "datetime_missing_timezone", text)

    def test_rejected_forms_are_identical_on_every_python(self):
        bad = [
            "", " ", "2026-01-09", "2026-01-09T20", "2026-01-09 20:00:00-05:00", "2026-01-09t20:00:00-05:00",
            "2026-01-09T20:00:00+0900", "2026-01-09T20:00:00+09", "20260109T200000-0500", "2026-01-09T2000-05:00",
            "2026-01-09T20:00:00.1234567Z", "2026-01-09T20:00:00.Z", "2026-01-09T20:00:00,5Z",
            "2026-01-09T24:00:00Z", "2026-01-09T20:60:00Z", "2026-01-09T20:00:60Z", "2026-02-30T20:00:00Z",
            "2026-13-01T20:00:00Z", "2026-01-09T20:00:00+24:00", "2026-01-09T20:00:00+09:60",
            "2026-01-09T20:00:00z", "2026-01-09T20:00:00 Z", "2026-01-09T20:00:00Z ", " 2026-01-09T20:00:00Z",
            "２０２６-01-09T20:00:00Z", "2026-W02-5T20:00:00Z", "2026-01-09T２０:00:00Z",
            "2026-01-09T20:00:00+٠٩:00", "0000-01-01T00:00:00Z",
        ]
        for text in bad:
            self.assertEqual(self.err(text), "datetime_invalid", repr(text))

    def test_non_string_values(self):
        for v in (None, 123, 1.5, [], b"2026-01-09T20:00:00Z"):
            self.assertEqual(self.err(v), "datetime_invalid", repr(v))

    def test_trailing_newline_is_rejected(self):
        self.assertEqual(self.err("2026-01-09T20:00:00Z\n"), "datetime_invalid")
        self.assertEqual(self.err("2026-01-09T20:00:00-05:00\n"), "datetime_invalid")

    def test_date_only_fields_accept_only_the_canonical_form(self):
        from v2_core.fixture import parse_iso_date
        self.assertEqual(parse_iso_date("2026-01-09", "f"), "2026-01-09")
        for text in ("20260109", "2026-W02-5", "2026-01-9", "2026-1-09", " 2026-01-09", "2026-01-09T00:00", None):
            with self.assertRaises(InputError, msg=repr(text)):
                parse_iso_date(text, "f")

    def test_parser_does_not_use_fromisoformat(self):
        import inspect
        import v2_core.sessions as sess_mod
        self.assertNotIn(".fromisoformat(", inspect.getsource(sess_mod))


class P01SameInstantDifferentOffsets(unittest.TestCase):
    EST = h.obs("r", D, 40)                                                    # 20:00-05:00
    UTC = dict(EST, observed_at_iso8601="2026-01-10T01:00:00Z")                 # same instant
    TOKYO = dict(EST, observed_at_iso8601="2026-01-10T10:00:00+09:00")          # same instant

    def test_fingerprint_is_offset_independent(self):
        fp = {parse_observation(x).fingerprint() for x in (self.EST, self.UTC, self.TOKYO)}
        self.assertEqual(len(fp), 1)

    def test_same_record_in_any_order_is_not_a_conflict_and_results_are_identical(self):
        base = evaluate_day(ARMED, D, series(), SESS, [self.EST])
        for raw in ([self.EST, self.UTC], [self.UTC, self.EST], [self.TOKYO, self.EST, self.UTC], [self.TOKYO]):
            r = evaluate_day(ARMED, D, series(), SESS, raw)
            self.assertEqual(r.decision.value, base.decision.value)
            self.assertEqual(r.next_state.fixed_decision, base.next_state.fixed_decision)
            self.assertEqual(r.next_state, base.next_state)

    def test_applied_state_fingerprint_matches_when_rerun_uses_other_offset(self):
        first = evaluate_day(ARMED, D, series(), SESS, [self.EST])
        again = evaluate_day(first.next_state, D, series(), SESS, [self.TOKYO])
        self.assertEqual(again.next_state, first.next_state)

    def test_different_instant_same_record_id_is_still_a_conflict(self):
        later = dict(self.EST, observed_at_iso8601="2026-01-09T21:00:00-05:00")
        for raw in ([self.EST, later], [later, self.EST]):
            with self.assertRaises(ConflictError) as ctx:
                select_decision(raw, SESS, D)
            self.assertEqual(ctx.exception.code, "record_id_conflict")

    def test_window_check_uses_instants_not_wall_clock(self):
        # 01-10T10:00+09:00 is 20:00-05:00 on D: inside the window although the wall clock reads the next day
        self.assertEqual(select_decision([self.TOKYO], SESS, D).value, 40)


class P02ConflictGuidance(unittest.TestCase):
    def conflict(self, raw, state=ARMED):
        r = run_day_safe(state, D, series(), SESS, raw)
        self.assertIs(r.run_class, RunClass.CONFLICT)
        return r

    def test_decision_conflict_separates_supplemental_and_correction(self):
        t = render(self.conflict([h.obs("a", D, 40), h.obs("b", D, 41)]))
        self.assertIn("追加の観測は observation_role を supplemental", t)
        self.assertIn("判断は差し替わりません", t)
        self.assertIn("訂正は", t)
        self.assertIn("自動で差し替えません", t)

    def test_record_id_conflict_guidance(self):
        a = h.obs("a", D, 40)
        t = render(self.conflict([a, dict(a, current_fg_value=41)]))
        self.assertIn("新しいrecord_idのsupplemental", t)
        self.assertIn("訂正は、追加観測とは別の手順", t)

    def test_conflict_with_applied_decision_keeps_applied_state(self):
        first = evaluate_day(ARMED, D, series(), SESS, [h.obs("a", D, 40)])
        r = self.conflict([h.obs("a2", D, 41)], state=first.next_state)
        self.assertEqual(r.code, "decision_conflict_with_applied")
        self.assertEqual(r.next_state, first.next_state)
        self.assertFalse(r.state_updated)
        t = render(r)
        self.assertIn("適用済みの状態は変更していません", t)
        self.assertIn("適用済みdecisionの訂正は、追加観測とは別の明示手順", t)

    def test_summary_does_not_call_a_conflict_a_price_data_anomaly(self):
        r = self.conflict([h.obs("a", D, 40), h.obs("b", D, 41)])
        s = render_summary(r)
        self.assertIn("観測記録の検査: 衝突（価格データの異常ではありません。コード=decision_conflict）", s)
        self.assertNotIn("データ検査: 異常", s)
        self.assertIn("終了コード: 1", s)

    def test_input_error_summary_keeps_the_data_check_label(self):
        r = run_day_safe(ARMED, D, series(), SESS, [dict(h.obs("w", D, 40), target_us_session_date="2026-01-08")])
        self.assertIn("データ検査: 異常（コード=target_mismatch）", render_summary(r))


class P03UnrecordedDayNotice(unittest.TestCase):
    def test_notice_when_decision_not_recorded(self):
        for per in ({D: h.WEAK}, {D: h.TREND_OK}, {D: h.NORMAL_OK}):
            t = render_message(evaluate_day(ARMED, D, series(per), SESS, []))
            self.assertIn("この日のdecision観測を記録しないと（合図なしの日も）", t)
            self.assertIn("armedが不明、連続数が0になります", t)

    def test_no_notice_when_recorded(self):
        t = render_message(evaluate_day(ARMED, D, series({D: h.WEAK}), SESS, [h.obs("d", D, 40)]))
        self.assertNotIn("毎日記録してください", t)

    def test_the_notice_describes_the_actual_state_change(self):
        # Unrecorded D, then processing the next session: armed UNKNOWN and streak 0 (spec S-2(a))
        no_rec = evaluate_day(ARMED, D, series(), SESS, [])
        nxt = "2026-01-12"
        st = MarketState(no_rec.next_state.as_of_d, Tri.TRUE, 2, Tri.FALSE)
        s = series()
        r = evaluate_day(st, nxt, s, SESS, [h.obs("n", nxt, 40)])
        self.assertEqual((r.next_state.armed, r.next_state.streak), (Tri.UNKNOWN, 1))


if __name__ == "__main__":
    unittest.main()
