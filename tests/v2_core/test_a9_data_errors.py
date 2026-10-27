"""A9: data errors are exit-1 operational errors, never 'condition not met' and never a fallback to an older day."""
import math
import unittest

import v2_helpers as h
from v2_core.engine import ErrorResult, RunClass, evaluate_day, run_day_safe
from v2_core.errors import InputError
from v2_core.fixture import MarketSeries, load_research_fixture
from v2_core.sessions import Session, SessionList
from v2_core.state import MarketState
from v2_core.tri import Tri

DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
SESS = h.make_sessions(DATES)
STATE = MarketState("2026-01-06", Tri.TRUE, 0, Tri.FALSE)
META = {"price_definition": "adj_close_total_return"}


def stub(dates=DATES):
    return h.StubSeries([h.row(d, **h.WEAK) for d in dates])


def code_of(fn):
    with_err = None
    try:
        fn()
    except InputError as e:
        with_err = e.code
    return with_err


class SessionAndRowErrors(unittest.TestCase):
    def check(self, state, d, series, sessions, code):
        res = run_day_safe(state, d, series, sessions, [])
        self.assertIsInstance(res, ErrorResult, code)
        self.assertEqual((res.code, res.exit_code, res.run_class), (code, 1, RunClass.DATA_ERROR))
        self.assertIs(res.next_state, state)

    def test_target_not_a_session_or_unconfirmed_or_edges(self):
        self.check(STATE, "2026-01-10", stub(), SESS, "target_not_in_sessions")
        self.check(STATE, "2026-01-07", stub(), h.make_sessions(DATES, confirmed=False), "target_unconfirmed")
        self.check(STATE, "2026-01-08", stub(), SESS, "next_session_missing")
        self.check(STATE, "2026-01-05", stub(), SESS, "previous_session_missing")
        self.check(STATE, "not-a-date", stub(), SESS, "invalid_date")

    def test_missing_target_row_does_not_fall_back_to_older_day(self):
        s = stub(["2026-01-05", "2026-01-06"])               # no row for D=2026-01-07
        self.check(STATE, "2026-01-07", s, SESS, "target_row_missing")

    def test_series_missing_previous_session_is_a_mismatch(self):
        s = stub(["2026-01-05", "2026-01-07"])               # sessions say 2026-01-06 precedes D
        self.check(STATE, "2026-01-07", s, SESS, "session_series_mismatch")

    def test_session_list_validation(self):
        o, c = SESS.get("2026-01-05").open_at, SESS.get("2026-01-05").close_at
        with self.assertRaises(InputError):
            SessionList([Session("2026-01-05", c, o, True)])                  # open after close
        with self.assertRaises(InputError):
            SessionList([Session("2026-01-06", o, c, True), Session("2026-01-05", o, c, True)])   # order
        with self.assertRaises(InputError):
            SessionList.from_dicts([{"date": "2026-01-05", "open_at": "2026-01-05T09:30:00",
                                     "close_at": "2026-01-05T16:00:00-05:00", "confirmed": True}])   # naive time
        with self.assertRaises(InputError):
            SessionList.from_dicts([{"date": "2026-01-05", "open_at": "2026-01-05T09:30:00-05:00",
                                     "close_at": "2026-01-05T16:00:00-05:00", "confirmed": "yes"}])   # not a bool


class SeriesValidation(unittest.TestCase):
    def build(self, **over):
        n = 260
        dates = ["2024-%02d-%02d" % (1 + i // 28, 1 + i % 28) for i in range(12 * 28)][:n]
        args = dict(dates=dates, soxx=[100.0 + (i % 7) for i in range(n)], spy={d: 100.0 for d in dates},
                    ief={d: 50.0 for d in dates}, market_dates=set(dates), soxl_close=None, meta=dict(META))
        args.update(over)
        return MarketSeries(**args)

    def test_valid_series_has_a_full_row_at_the_end(self):
        s = self.build()
        row = s.row(s.dates[-1])
        self.assertTrue(all(math.isfinite(x) for x in (row.soxx, row.sma, row.rsi, row.shd, row.prev_rsi)))

    def test_bad_prices_and_dates_are_rejected(self):
        for bad in (float("nan"), float("inf"), 0.0, -1.0, True):
            soxx = [100.0] * 260
            soxx[100] = bad
            with self.assertRaises(InputError) as ctx:
                self.build(soxx=soxx)
            self.assertEqual(ctx.exception.code, "price_not_finite_positive", repr(bad))
        dates = self.build().dates
        with self.assertRaises(InputError) as ctx:
            self.build(dates=dates[:-1] + [dates[-2]])
        self.assertEqual(ctx.exception.code, "date_order_or_duplicate")
        with self.assertRaises(InputError) as ctx:
            self.build(soxx=[100.0] * 259)
        self.assertEqual(ctx.exception.code, "series_misaligned")

    def test_unknown_price_definition_is_an_error(self):
        for meta in ({}, {"price_definition": "close"}, {"price_definition": None}):
            with self.assertRaises(InputError) as ctx:
                self.build(meta=meta)
            self.assertEqual(ctx.exception.code, "price_definition_unknown")

    def test_soxl_close_requires_its_own_definition(self):
        with self.assertRaises(InputError) as ctx:
            self.build(soxl_close={"2024-01-01": 30.0})
        self.assertEqual(ctx.exception.code, "soxl_price_definition_unknown")

    def test_short_history_is_an_error_not_a_non_match(self):
        n = 30
        dates = ["2024-01-%02d" % (i + 1) for i in range(n)]
        s = MarketSeries(dates, [100.0 + i for i in range(n)], {d: 100.0 for d in dates},
                         {d: 50.0 for d in dates}, set(dates), meta=dict(META))
        self.assertEqual(code_of(lambda: s.row(dates[-1])), "insufficient_history")

    def test_missing_spy_ief_makes_shd_unavailable(self):
        s = self.build()
        d = s.dates[-1]
        spy = {k: 100.0 for k in s.dates}
        spy[d] = None
        s2 = self.build(spy=spy)
        self.assertEqual(code_of(lambda: s2.row(d)), "insufficient_history")


class NoFutureData(unittest.TestCase):
    def test_prices_after_d_cannot_change_the_result(self):
        series, fg = h.fixture()
        d = "2025-03-14"
        i = series.dates.index(d)
        dates = series.dates[: i + 4]
        soxx = series.soxx[: i + 1] + [1e9, 1e-9, 5.0]
        polluted = MarketSeries(dates, soxx, series._spy, series._ief, series._market_dates, meta=dict(series.meta))
        sessions = h.make_sessions(dates[-12:])
        prev = series.previous_date(d)
        state = MarketState(prev, Tri.TRUE, 0, Tri.FALSE)
        clean = evaluate_day(state, d, series, sessions, [])
        dirty = evaluate_day(state, d, polluted, sessions, [])
        self.assertEqual(clean.row, dirty.row)
        self.assertEqual({k: v.status for k, v in clean.rules.items()}, {k: v.status for k, v in dirty.rules.items()})

    def test_loader_cuts_everything_after_through(self):
        cut, fg = load_research_fixture(h.FIXTURE_DIR, through="2025-03-14")
        self.assertEqual(cut.dates[-1], "2025-03-14")
        self.assertTrue(all(k <= "2025-03-14" for k in fg))
        full, _ = h.fixture()
        self.assertEqual(cut.row("2025-03-14"), full.row("2025-03-14"))


if __name__ == "__main__":
    unittest.main()
