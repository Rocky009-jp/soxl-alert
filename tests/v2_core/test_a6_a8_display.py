"""A6 / A7 / A8: case-U boundary, b* reference, parallel NO_SELL / P20 display, no recommendation text."""
import re
import unittest
from decimal import Decimal

import v2_helpers as h
from v2_core.display import bstar, render, render_message
from v2_core.engine import RunClass, evaluate_day
from v2_core.errors import InputError
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
SESS = h.make_sessions(DATES)
D = "2026-01-09"        # four sessions after DATES[0]: back(D, 3) == 2026-01-06, next(D) == 2026-01-12
PREV = "2026-01-08"
ARMED = MarketState(PREV, Tri.TRUE, 0, Tri.FALSE)

FORBIDDEN_ASSERTIONS = ["購入条件確定", "購入条件は確定しました", "売却を推奨", "売却してください", "買ってください",
                        "成行", "S+3に購入", "あなたのP20が成立", "初回です", "再参加です"]


def series(per=None, close=None):
    per = per or {}
    s = h.StubSeries([h.row(d, **per.get(d, h.WEAK)) for d in DATES])
    if close:
        s.closes[D] = close
    return s


def day(per, f, close=48.00, state=ARMED):
    o = [] if f is None else [h.obs("r", D, f)]
    return evaluate_day(state, D, series(per, close), SESS, o)


class BstarTests(unittest.TestCase):
    DEF = "close_split_adjusted_not_dividend_adjusted"

    def test_examples_fixed_in_advance(self):
        self.assertEqual(bstar(Decimal("48.00"), self.DEF), Decimal("40.00"))     # exact boundary
        self.assertEqual(bstar(Decimal("48.01"), self.DEF), Decimal("40.00"))     # 40.008333... floored
        self.assertEqual(bstar(Decimal("47.99"), self.DEF), Decimal("39.99"))     # 39.991666... floored
        self.assertEqual(bstar(Decimal("100.00"), self.DEF), Decimal("83.33"))
        self.assertEqual(bstar(48.0, self.DEF), Decimal("40.00"))                 # float input goes through str()
        self.assertEqual(bstar("48.00", self.DEF), Decimal("40.00"))

    def test_floor_property_exact_decimal(self):
        for cents in range(1, 20001, 7):
            d = Decimal(cents) / 100
            b = bstar(d, self.DEF)
            self.assertLessEqual(b * Decimal("1.2"), d)                           # never overstates
            self.assertGreater((b + Decimal("0.01")) * Decimal("1.2"), d)          # and is the largest cent value

    def test_definition_and_value_checks(self):
        for bad_def in ("adj_close_total_return", "", None, "close"):
            with self.assertRaises(InputError) as ctx:
                bstar(48, bad_def)
            self.assertEqual(ctx.exception.code, "soxl_price_definition_unknown")
        for bad in (0, -1, float("nan"), float("inf"), Decimal("0")):
            with self.assertRaises(InputError):
                bstar(bad, self.DEF)


class CaseUBoundary(unittest.TestCase):
    def texts(self):
        out = []
        for per, f in ((h.WEAK, None), ({D: h.TREND_OK}, 33), ({D: h.NORMAL_OK}, 27), (h.WEAK, 20),
                       ({D: h.NORMAL_OK}, None), ({D: h.TREND_OK}, None)):
            out.append(render(day({D: per} if per is h.WEAK else per, f)))
        return out

    def test_no_shares_amounts_orders_or_status_assertions(self):
        for t in self.texts():
            self.assertNotRegex(t, r"(?<![\d,])(?:[2-9]|[1-9][\d,]*\d)[\d,]*\s*株")   # no share counts (the words "0株" / "1株平均原価" are not counts)
            self.assertNotRegex(t, r"[¥$]\s*\d|\d\s*(円|USD)")        # no amounts
            for phrase in FORBIDDEN_ASSERTIONS:
                self.assertNotIn(phrase, t, phrase)
            self.assertIn("株数・金額は出しません", t)

    def test_ratios_only(self):
        t = render(day({D: h.NORMAL_OK}, 27))
        self.assertIn("利用可能資金の100%", t)
        self.assertIn("保有を全部買い換える意味ではなく", t)
        t2 = render(day({D: h.TREND_OK}, 33))
        self.assertIn("利用可能資金の25%", t2)

    def test_own_status_is_not_asserted(self):
        t = render(day({D: h.TREND_OK}, 33))
        self.assertIn("初回（0株・売却歴なし）か全売却後の再参加か、どちらでもないかは手元確認", t)
        self.assertIn("本人のP20成立は未判定", t)
        self.assertIn("手元確認: 保有株数／全売却歴／利用可能USD／未約定注文", t)
        self.assertIn("売却側の手元確認が先", t)


class ParallelProfiles(unittest.TestCase):
    def test_trend_shows_both_profiles_with_wait_dates(self):
        t = render(day({D: h.TREND_OK}, 33))
        self.assertIn("NO_SELL I25: 本人が0株の場合のみ、利用可能資金の25%", t)
        self.assertIn("再参加は該当しません", t)
        self.assertIn("P20_ONLY I25/R25", t)
        self.assertIn("全売却の約定セッションS・合図D・手動購入next(D)を区別", t)
        self.assertIn("D−S≧3（最短でS+4に購入）", t)
        self.assertIn("Sが2026-01-06以前なら", t)               # back(D, 3), computed from the injected list
        self.assertIn("next(D)=2026-01-12", t)
        self.assertIn("待機の成立は未判定", t)

    def test_normal_and_exfear_are_common_to_both_profiles(self):
        for per, f in (({D: h.NORMAL_OK}, 27), (h.WEAK, 20)):
            t = render(day({D: per} if per is h.WEAK else per, f))
            self.assertIn("NO_SELL I25／P20_ONLY I25/R25 とも共通: 利用可能資金の100%", t)

    def test_unconfirmed_is_labelled_reference_only(self):
        r = evaluate_day(MarketState.initial(), D, series({D: h.NORMAL_OK}, 48.0), SESS, [h.obs("r", D, 27)])
        self.assertIs(r.run_class, RunClass.REFERENCE_UNCONFIRMED)
        t = render(r)
        self.assertIn("参考・未確認", t)
        self.assertNotIn("条件成立（確認済み）", t)

    def test_no_sell_text_has_no_sale_conditions(self):
        t = render(day({D: h.TREND_OK}, 33))
        for phrase in ("過熱", "RSI75", "売却条件成立", "緊急脱出"):
            self.assertNotIn(phrase, t)


class WaitingDisplay(unittest.TestCase):
    def test_waiting_shows_branch_table_and_does_not_confirm(self):
        r = day({D: h.NORMAL_OK}, None)
        t = render_message(r)
        self.assertIs(r.run_class, RunClass.WAITING_FG)
        self.assertIn("購入条件は未確定です", t)
        self.assertIn("F&Gの値による分岐", t)
        self.assertIn("25未満", t)
        self.assertIn("通常買いの条件成立 → 利用可能資金の100%", t)
        self.assertIn("再通知はありません", t)

    def test_no_signal_when_everything_is_excluded(self):
        r = day(h.WEAK, None, state=MarketState(PREV, Tri.FALSE, 0, Tri.FALSE))
        self.assertIs(r.run_class, RunClass.NO_SIGNAL)
        self.assertIn("合図なし", render(r))

    def test_weak_market_alone_does_not_prove_no_signal_when_armed_not_excluded(self):
        # SOXX <= SMA200 cannot rule out EXFEAR (it has no SOXX condition)
        r = day(h.WEAK, None, state=ARMED)
        self.assertIs(r.run_class, RunClass.WAITING_FG)
        self.assertNotIn("合図なし", render_message(r).split("\n")[0])

    def test_bstar_line_present_with_definition_and_no_floor_claim(self):
        t = render(day({D: h.TREND_OK}, 33, close=48.00))
        self.assertIn("b*=40.00", t)
        self.assertIn("SOXL D終値48.0÷1.2", t)
        self.assertIn("close_split_adjusted_not_dividend_adjusted", t)
        self.assertIn("売却下限・指値・売却推奨ではありません", t)
        self.assertIn("0.01未満の境界付近", t)
        t2 = render(day({D: h.TREND_OK}, 33, close=None))
        self.assertIn("b*: SOXL D終値が入力にないため表示しません", t2)


if __name__ == "__main__":
    unittest.main()
