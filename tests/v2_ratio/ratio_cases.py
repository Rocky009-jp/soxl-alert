"""The scenarios of the ratio-emphasis tests (never imported by the runtime).

build(root) makes the judgments of a fixed table of days with the v2_core of the repository at `root` and returns the
texts of render_message / compose_notice / compose_error_notice for them: {name: text}. The same function ran once at the
code start (2c7320f, before the ratio emphasis) and its output is the file golden_2c7320f.json; the tests run it on the
tree under test and compare (R-02). Nothing is read from the clock, a file other than the sources, or the network."""
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
D = "2026-01-09"        # four sessions after DATES[0]: the same dates as the A6-A8 display tests
DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"]
PREV = "2026-01-08"
SIGNAL = ("exfear_confirmed", "exfear_unconfirmed", "normal_confirmed", "normal_unconfirmed", "trend_confirmed")
NO_SIGNAL = ("no_signal", "no_signal_exfear_consumed", "waiting_fg_weak", "waiting_fg_trend", "waiting_fg_normal",
             "data_error", "conflict")


def _modules(root):
    for path in (root, os.path.join(root, "tests", "v2_core")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import v2_helpers as h
    from v2_core import display, engine
    from v2_core.state import MarketState
    from v2_core.tri import Tri
    return h, display, engine, MarketState, Tri


def results(root):
    """{name: the result of the core for the scenario}."""
    h, display, engine, MarketState, Tri = _modules(root)
    sessions = h.make_sessions(DATES)

    def series(row_args):
        s = h.StubSeries([h.row(d, **(row_args if d == D else h.WEAK)) for d in DATES])
        s.closes[D] = 48.00
        return s

    def day(row_args, f, armed=Tri.TRUE, observations=None):
        state = MarketState(PREV, armed, 0, Tri.FALSE)
        obs = observations if observations is not None else ([] if f is None else [h.obs("r", D, f)])
        return engine.run_day_safe(state, D, series(row_args), sessions, obs)

    return {
        "exfear_confirmed": day(h.WEAK, 20),
        "exfear_unconfirmed": day(h.WEAK, 20, armed=Tri.UNKNOWN),
        "normal_confirmed": day(h.NORMAL_OK, 27),
        "normal_unconfirmed": day(h.NORMAL_OK, 27, armed=Tri.UNKNOWN),
        "trend_confirmed": day(h.TREND_OK, 33),
        "no_signal": day(h.WEAK, 40),
        "no_signal_exfear_consumed": day(h.WEAK, 20, armed=Tri.FALSE),
        "waiting_fg_weak": day(h.WEAK, None),
        "waiting_fg_trend": day(h.TREND_OK, None),
        "waiting_fg_normal": day(h.NORMAL_OK, None),
        "data_error": engine.run_day_safe(MarketState(PREV, Tri.TRUE, 0, Tri.FALSE), "2026-01-10", series(h.WEAK),
                                          sessions, []),
        "conflict": day(h.WEAK, 20, observations=[h.obs("r1", D, 20), h.obs("r2", D, 21)]),
    }


def build(root):
    """{name: text} for every scenario: the body (render_message), the whole preview (render), and the notices."""
    h, display, engine, MarketState, Tri = _modules(root)
    import v2_daily_run as run_values
    import v2_notify as notify
    out = {}
    sessions = h.make_sessions(DATES)
    now = datetime(2026, 1, 10, 7, 40, tzinfo=timezone(timedelta(hours=9)))
    for name, res in results(root).items():
        body = display.render_message(res)
        out["body:" + name] = body
        out["render:" + name] = display.render(res)
        if hasattr(res, "series_meta"):          # a judgment: the morning notice around the body
            report = run_values.RunReport(run_values.DONE, D, (), "PREPARED", body)
            out["notice:" + name] = notify.compose_notice(report, sessions, now).text
    halt = run_values.RunReport(run_values.STALE, D, (), None, "plain notice", code="run_session_unconfirmed",
                                field="sessions", detail="2026-01-12")
    out["halt"] = notify.compose_notice(halt, sessions, now).text
    out["error"] = notify.compose_error_notice(D, "run_args_invalid", "RunError").text
    return out
