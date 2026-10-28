"""Input sets and result serialisation for the extraction check (A-04).

The same inputs are run before the transition extraction (to write the baseline JSON) and after it. This module
only builds inputs and turns results into plain JSON values; it never decides what a correct result is.
Every record_id used here already satisfies the new record_id rule, so the extraction must not change any output.
"""
import dataclasses
import enum
import itertools
from datetime import datetime
from decimal import Decimal

import v2_helpers as h
from v2_core.engine import run_day_safe
from v2_core.observations import parse_observation
from v2_core.sessions import Session, SessionList
from v2_core.state import MarketState
from v2_core.tri import Tri

D = "2026-03-11"
PREV = "2026-03-10"
EARLY = "2026-03-06"
SESSION_DATES = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09",
                 "2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13"]

FG_VALUES = [None, 0, 24.99, 25, 27.5, 29.99, 30, 30.01, 100]
D_KINDS = ("normal", "trend", "none")
PREV_KINDS = ("normal", "not")
BASE_AS_OF = {"none": None, "prev": PREV, "gap": EARLY}


def to_plain(obj):
    """Result objects -> JSON-able values. Unknown types fail loudly so a changed result shape cannot hide."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, enum.Enum):
        return "%s.%s" % (type(obj).__name__, obj.name)
    if isinstance(obj, datetime):
        return "datetime:" + obj.isoformat()
    if isinstance(obj, Decimal):
        return "decimal:" + str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {"__type__": type(obj).__name__}
        for f in dataclasses.fields(obj):
            out[f.name] = to_plain(getattr(obj, f.name))
        return out
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    raise TypeError("unserialisable result part: %s" % type(obj).__name__)


def stub_series(d_kind="normal", prev_kind="normal"):
    d_row = {"normal": h.row(D, **h.NORMAL_OK), "trend": h.row(D, **h.TREND_OK), "none": h.row(D, **h.WEAK)}[d_kind]
    p_row = {"normal": h.row(PREV, **h.NORMAL_OK), "not": h.row(PREV, **h.WEAK)}[prev_kind]
    s = h.StubSeries([p_row, d_row])
    s.closes = {PREV: 30.5, D: 31.25}
    return s


class PrevRowUnavailable(h.StubSeries):
    """The previous session has a date but no usable indicator row (history too short)."""

    def row(self, d):
        from v2_core.errors import InputError
        if d == PREV:
            raise InputError("insufficient_history", "market")
        return super().row(d)


def sessions(confirm_d=True, dates=SESSION_DATES):
    base = h.make_sessions(dates)
    if confirm_d:
        return base
    return SessionList([Session(s.date, s.open_at, s.close_at, False if s.date == D else s.confirmed)
                        for s in base.sessions])


def _args(state=None, d=D, series=None, sess=None, raw=None):
    return (state if state is not None else MarketState.initial(), d,
            series if series is not None else stub_series(), sess if sess is not None else sessions(),
            raw if raw is not None else [])


def run(args):
    return run_day_safe(*args)


def _valid_base_triples():
    out = []
    for armed, streak, prev in itertools.product(Tri, (0, 1, 2, 3), Tri):
        if streak >= 3 and armed is not Tri.TRUE:
            continue
        if streak >= 1 and prev is not Tri.FALSE:
            continue
        out.append((armed, streak, prev))
    return out


def grid_cases():
    """Base armed x streak x prev_normal_raw (I-05/I-06 pairs) x base as_of x F&G x market x previous market."""
    for (armed, streak, prev), as_of_name, fg, d_kind, p_kind in itertools.product(
            _valid_base_triples(), BASE_AS_OF, FG_VALUES, D_KINDS, PREV_KINDS):
        state = MarketState(BASE_AS_OF[as_of_name], armed, streak, prev)
        raw = [] if fg is None else [h.obs("r-" + D, D, fg)]
        cid = "grid|%s|%d|%s|%s|%s|%s|%s" % (armed.name, streak, prev.name, as_of_name, fg, d_kind, p_kind)
        yield cid, _args(state, series=stub_series(d_kind, p_kind), raw=raw)


def _applied(raw_obs, base):
    """A current state as an earlier run would have stored it for the decision `raw_obs` on D."""
    o = parse_observation(raw_obs)
    snap = MarketState(base.as_of_d, base.armed, base.streak, base.prev_normal_raw)
    return MarketState(D, Tri.TRUE, 3, Tri.FALSE,
                       {"d": D, "record_id": o.record_id, "fingerprint": o.fingerprint()}, snap)


def representative_cases():
    ok = h.obs("r-" + D, D, 27.5)
    base_prev = MarketState(PREV, Tri.TRUE, 2, Tri.FALSE)
    base_unknown = MarketState(PREV, Tri.UNKNOWN, 0, Tri.UNKNOWN)
    c = {}

    # same-D re-runs
    for fg in (20, 27.5, 31):
        raw = h.obs("r-" + D, D, fg)
        for name, base in (("true2", base_prev), ("unknown", base_unknown),
                           ("false0", MarketState(PREV, Tri.FALSE, 0, Tri.FALSE))):
            c["rerun_match|%s|%s" % (fg, name)] = _args(_applied(raw, base), raw=[raw])
    stored = h.obs("r-" + D, D, 27.5)
    state = _applied(stored, base_prev)
    c["rerun_value_conflict"] = _args(state, raw=[h.obs("r-" + D, D, 28)])
    c["rerun_record_id_conflict"] = _args(state, raw=[h.obs("r-other", D, 27.5)])
    c["rerun_no_decision"] = _args(state, raw=[])
    c["rerun_no_base"] = _args(MarketState(D, Tri.TRUE, 1, Tri.FALSE,
                                           {"d": D, "record_id": "r-" + D, "fingerprint": "f" * 64}, None),
                               raw=[stored])
    c["rerun_no_fixed"] = _args(MarketState(D, Tri.TRUE, 1, Tri.FALSE, None, base_prev), raw=[stored])
    c["state_ahead"] = _args(MarketState("2026-03-12", Tri.TRUE, 1, Tri.FALSE), raw=[stored])

    # intermediate session with a valid decision that was never processed (R-02)
    mid = h.obs("r-mid", "2026-03-09", 31)
    c["intermediate_unprocessed"] = _args(MarketState("2026-03-05", Tri.TRUE, 1, Tri.FALSE), raw=[mid, stored])
    c["intermediate_wrong_target"] = _args(MarketState("2026-03-05", Tri.TRUE, 1, Tri.FALSE),
                                           raw=[h.obs("r-mid", "2026-03-05", 31), stored])

    # decision selection
    c["decision_conflict"] = _args(raw=[h.obs("r-a", D, 20), h.obs("r-b", D, 35)])
    c["record_id_conflict"] = _args(raw=[h.obs("r-a", D, 20), h.obs("r-a", D, 21)])
    c["same_record_two_offsets"] = _args(raw=[
        stored, dict(stored, observed_at_iso8601="2026-03-12T10:00:00+09:00")])
    c["supplemental_only"] = _args(raw=[h.obs("r-s", D, 20, role="supplemental")])
    c["not_checked_decision"] = _args(raw=[h.obs("r-n", D, None, status="not_checked")])
    c["supplemental_plus_decision"] = _args(raw=[h.obs("r-s", D, 20, role="supplemental"), stored])
    c["outside_window_early"] = _args(raw=[h.obs("r-e", D, 27, hour=15)])
    c["outside_window_late"] = _args(raw=[dict(h.obs("r-l", D, 27), observed_at_iso8601="2026-03-12T10:00:00-05:00")])
    c["target_mismatch"] = _args(raw=[dict(h.obs("r-m", D, 27), target_us_session_date="2026-03-10")])
    c["fg_out_of_range"] = _args(raw=[h.obs("r-v", D, 101)])
    c["observation_list_invalid"] = _args(raw="not a list")
    c["observation_item_invalid"] = _args(raw=["x"])
    c["record_id_blank"] = _args(raw=[h.obs("", D, 27)])
    c["record_id_not_string"] = _args(raw=[h.obs(5, D, 27)])

    # data errors and market-side edge cases
    c["target_not_in_sessions"] = _args(d="2026-03-14")
    c["target_unconfirmed"] = _args(sess=sessions(confirm_d=False), raw=[stored])
    c["next_session_missing"] = _args(sess=sessions(dates=SESSION_DATES[:8]), raw=[stored])
    c["previous_session_missing"] = _args(d=SESSION_DATES[0], sess=sessions())
    c["series_mismatch"] = _args(series=h.StubSeries([h.row("2026-03-09", **h.NORMAL_OK), h.row(D, **h.NORMAL_OK)]),
                                 raw=[stored])
    c["target_row_missing"] = _args(series=h.StubSeries([h.row(PREV, **h.NORMAL_OK)]), raw=[stored])
    c["bad_target_date"] = _args(d="2026-3-11")
    c["state_not_a_state"] = _args(state="x")
    s = PrevRowUnavailable([h.row(PREV, **h.NORMAL_OK), h.row(D, **h.NORMAL_OK)])
    s.closes = {D: 31.25}
    for fg in (None, 27.5):
        for name, st in (("unknown", base_unknown), ("false", MarketState(PREV, Tri.FALSE, 0, Tri.FALSE)),
                         ("fresh", MarketState.initial())):
            c["prev_row_unavailable|%s|%s" % (fg, name)] = _args(
                st, series=s, raw=[] if fg is None else [h.obs("r-" + D, D, fg)])
    no_close = stub_series()
    no_close.closes = {}
    c["no_soxl_close"] = _args(series=no_close, raw=[stored])
    for k, v in c.items():
        yield "rep|" + k, v


def research_sequence(run_fn):
    """A1: 465-day chain on the research fixture (same input and initial state as test_a1_research_parity)."""
    series, fg = h.fixture()
    rows = h.read_signals_csv()
    by_date = {r["date"]: r for r in rows}
    all_dates = [d for d in series.dates if "2024-09-25" <= d <= "2026-08-11"]
    sess = h.make_sessions(all_dates)
    first = by_date["2024-10-01"]
    state = MarketState("2024-10-01", Tri.TRUE if first["armed"] == "true" else Tri.FALSE, int(first["streak"]),
                        Tri.TRUE if first["normal_raw"] == "true" else Tri.FALSE)
    for r in rows[1:]:
        d = r["date"]
        raw = [h.obs("r-" + d, d, fg[d])] if d in fg else []
        args = (state, d, series, sess, raw)
        res = run_fn(args)
        yield "a1|" + d, args, res
        state = res.next_state


def iter_all(run_fn=run):
    """(case id, args, result) for every case, in a fixed order. `run_fn` evaluates one args tuple."""
    for cid, args in itertools.chain(grid_cases(), representative_cases()):
        yield cid, args, run_fn(args)
    for item in research_sequence(run_fn):
        yield item
