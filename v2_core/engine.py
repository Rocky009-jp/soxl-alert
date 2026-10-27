"""Market condition evaluation and F&G state transition for one target session D.

Case U only: no holdings, cost basis, cash, orders or sale history enter or leave this module.
Ratios are fractions of 'available funds' (100% / 25%), never shares or amounts.
"""
import enum
from dataclasses import dataclass, field
from typing import List, Optional

from .errors import ConflictError, CoreError, InputError
from .fixture import MarketRow, parse_iso_date
from .observations import Observation, first_unprocessed_session, select_decision
from .state import MarketState
from .tri import Tri, from_bool, tri_and

RATIO_EXFEAR = 100
RATIO_NORMAL = 100
RATIO_TREND = 25


class RuleStatus(enum.Enum):
    MET = "MET"                    # condition met, all needed states confirmed
    NOT_MET = "NOT_MET"            # confirmed not met
    PENDING_FG = "PENDING_FG"      # needs the visually observed F&G
    UNCONFIRMED = "UNCONFIRMED"    # would be met, but armed / previous normal_raw are not confirmed


class RunClass(enum.Enum):
    NO_SIGNAL = "NO_SIGNAL"
    WAITING_FG = "WAITING_FG"
    CONDITION_MET = "CONDITION_MET"
    REFERENCE_UNCONFIRMED = "REFERENCE_UNCONFIRMED"
    DATA_ERROR = "DATA_ERROR"
    CONFLICT = "CONFLICT"


@dataclass
class RuleResult:
    name: str
    status: RuleStatus
    ratio: Optional[int]
    reasons: List[str] = field(default_factory=list)
    may_be_unconfirmed: bool = False   # PENDING_FG whose outcome would stay unconfirmed


@dataclass
class DayResult:
    d: str
    row: MarketRow
    rules: dict
    run_class: RunClass
    decision: Optional[Observation]
    effective_armed: Tri
    effective_streak: int
    effective_prev_normal_raw: Tri
    gap: bool
    next_state: MarketState
    state_updated: bool
    close_at: object
    next_open_at: object
    next_session_date: str
    wait_session_date: Optional[str]    # latest S with D - S >= 3 sessions (display aid only)
    soxl_close: object
    series_meta: dict
    notes: List[str] = field(default_factory=list)
    exit_code: int = 0


@dataclass
class ErrorResult:
    d: Optional[str]
    code: str
    field: Optional[str]
    run_class: RunClass
    next_state: MarketState
    exit_code: int = 1
    state_updated: bool = False
    detail: Optional[str] = None


def market_side_normal(row):
    return row.soxx > row.sma and row.rsi <= 55 and row.shd < 0


def market_side_trend(row):
    return row.soxx > row.sma and row.prev_rsi <= 55 and row.rsi > 55


def _prev_market_side_normal(cut, prev_date):
    try:
        prev_row = cut.row(prev_date)
    except InputError:
        return None
    return market_side_normal(prev_row)


def evaluate_day(state, d, series, sessions, raw_observations):
    parse_iso_date(d, "target_session_date")
    if not isinstance(state, MarketState):
        raise InputError("state_invalid", "state")
    session = sessions.get(d)
    if session is None:
        raise InputError("target_not_in_sessions", "sessions")
    if not session.confirmed:
        raise InputError("target_unconfirmed", "sessions")
    nxt = sessions.next(d)
    if nxt is None:
        raise InputError("next_session_missing", "sessions")
    prev_session = sessions.previous(d)
    if prev_session is None:
        raise InputError("previous_session_missing", "sessions")

    cut = series.through(d)           # nothing after D is used from here on
    row = cut.row(d)
    if cut.previous_date(d) != prev_session.date:
        raise InputError("session_series_mismatch", "market")

    decision = select_decision(raw_observations, sessions, d)

    if state.as_of_d is not None and state.as_of_d > d:
        raise InputError("state_ahead_of_target", "state")
    rerun = state.as_of_d == d
    if rerun:
        applied = state.fixed_decision
        if state.base is None or applied is None:
            raise InputError("state_rerun_unavailable", "state")
        if decision is None:
            raise InputError("rerun_decision_missing", "observations")
        if applied.get("record_id") != decision.record_id or applied.get("fingerprint") != decision.fingerprint():
            raise ConflictError("decision_conflict_with_applied", "observation_role")
        base = state.base
    else:
        base = state

    if base.as_of_d is not None and base.as_of_d < prev_session.date:
        earlier = first_unprocessed_session(raw_observations, sessions, base.as_of_d, d)
        if earlier is not None:
            # an earlier session with a valid decision exists: process it first, never treat it as a gap
            raise InputError("intermediate_session_unprocessed", "observations", detail=earlier)

    notes = []
    gap = base.as_of_d is not None and base.as_of_d != prev_session.date
    armed, streak, prev_nr = base.armed, base.streak, base.prev_normal_raw
    if gap:
        armed, streak, prev_nr = Tri.UNKNOWN, 0, Tri.UNKNOWN
        notes.append("session_gap_state_degraded")
    prev_ms = _prev_market_side_normal(cut, prev_session.date)
    if prev_nr is Tri.UNKNOWN and prev_ms is False:
        prev_nr = Tri.FALSE
    eff_armed, eff_streak, eff_prev_nr = armed, streak, prev_nr

    ms_normal = market_side_normal(row)
    ms_trend = market_side_trend(row)
    rules = {}
    new_state = base
    updated = False

    if decision is None:
        notes.append("fg_not_recorded")
        ex = RuleResult("EXFEAR", RuleStatus.NOT_MET, RATIO_EXFEAR)
        if armed is Tri.FALSE:
            ex.reasons.append("armed_confirmed_false")
        else:
            ex.status = RuleStatus.PENDING_FG
            ex.may_be_unconfirmed = armed is Tri.UNKNOWN
            ex.reasons.append("armed_confirmed_true" if armed is Tri.TRUE else "armed_unknown")
        nm = RuleResult("NORMAL", RuleStatus.NOT_MET, RATIO_NORMAL)
        if not ms_normal:
            nm.reasons.append("market_side_not_met")
        elif prev_nr is Tri.TRUE:
            nm.reasons.append("not_a_rise_prev_normal_raw")
        elif armed is Tri.FALSE:
            nm.reasons.append("armed_confirmed_false")
        else:
            nm.status = RuleStatus.PENDING_FG
            nm.may_be_unconfirmed = armed is Tri.UNKNOWN or prev_nr is Tri.UNKNOWN
            nm.reasons.append("market_side_met")
            if armed is Tri.UNKNOWN:
                nm.reasons.append("armed_unknown")
            if prev_nr is Tri.UNKNOWN:
                nm.reasons.append("prev_normal_raw_unknown")
        tr = RuleResult("TREND", RuleStatus.NOT_MET, RATIO_TREND)
        if ms_trend:
            tr.status = RuleStatus.PENDING_FG
            tr.reasons.append("market_side_met")
        else:
            tr.reasons.append("market_side_not_met")
        rules = {"EXFEAR": ex, "NORMAL": nm, "TREND": tr}
        statuses = [r.status for r in rules.values()]
        run_class = RunClass.NO_SIGNAL if all(s is RuleStatus.NOT_MET for s in statuses) else RunClass.WAITING_FG
        new_state = state
    else:
        f = decision.value
        new_streak = streak + 1 if f >= 30 else 0
        ex_tri = Tri.FALSE
        new_armed = armed
        if new_streak >= 3:
            new_armed = Tri.TRUE
        elif f < 25:
            ex_tri = armed if armed is not Tri.FALSE else Tri.FALSE
            new_armed = Tri.FALSE
        normal_raw = 25 <= f < 30 and ms_normal
        if normal_raw:
            rise = {Tri.FALSE: Tri.TRUE, Tri.TRUE: Tri.FALSE, Tri.UNKNOWN: Tri.UNKNOWN}[prev_nr]
            normal_tri = tri_and(Tri.TRUE, rise, armed)
        else:
            normal_tri = Tri.FALSE
        trend_tri = from_bool(f >= 30 and ms_trend)

        def result(name, ratio, tri, why):
            status = {Tri.TRUE: RuleStatus.MET, Tri.FALSE: RuleStatus.NOT_MET,
                      Tri.UNKNOWN: RuleStatus.UNCONFIRMED}[tri]
            return RuleResult(name, status, ratio, list(why))

        ex_why = ["fg_below_25"] if f < 25 else ["fg_not_below_25"]
        if f < 25:
            ex_why.append({Tri.TRUE: "armed_confirmed_true", Tri.FALSE: "armed_confirmed_false",
                           Tri.UNKNOWN: "armed_unknown"}[armed])
        nm_why = ["fg_in_25_30"] if 25 <= f < 30 else ["fg_not_in_25_30"]
        if 25 <= f < 30:
            nm_why.append("market_side_met" if ms_normal else "market_side_not_met")
            if ms_normal:
                nm_why.append({Tri.TRUE: "not_a_rise_prev_normal_raw", Tri.FALSE: "rise_confirmed",
                               Tri.UNKNOWN: "prev_normal_raw_unknown"}[prev_nr])
                nm_why.append({Tri.TRUE: "armed_confirmed_true", Tri.FALSE: "armed_confirmed_false",
                               Tri.UNKNOWN: "armed_unknown"}[armed])
        tr_why = ["fg_at_least_30"] if f >= 30 else ["fg_below_30"]
        if f >= 30:
            tr_why.append("market_side_met" if ms_trend else "market_side_not_met")
        rules = {
            "EXFEAR": result("EXFEAR", RATIO_EXFEAR, ex_tri, ex_why),
            "NORMAL": result("NORMAL", RATIO_NORMAL, normal_tri, nm_why),
            "TREND": result("TREND", RATIO_TREND, trend_tri, tr_why),
        }
        statuses = [r.status for r in rules.values()]
        if RuleStatus.MET in statuses:
            run_class = RunClass.CONDITION_MET
        elif RuleStatus.UNCONFIRMED in statuses:
            run_class = RunClass.REFERENCE_UNCONFIRMED
        else:
            run_class = RunClass.NO_SIGNAL
        base_snapshot = MarketState(base.as_of_d, base.armed, base.streak, base.prev_normal_raw, None, None)
        new_state = MarketState(
            as_of_d=d, armed=new_armed, streak=new_streak, prev_normal_raw=from_bool(normal_raw),
            fixed_decision={"d": d, "record_id": decision.record_id, "fingerprint": decision.fingerprint()},
            base=base_snapshot,
        )
        updated = not rerun

    back = sessions.back(d, 3)
    return DayResult(
        d=d, row=row, rules=rules, run_class=run_class, decision=decision,
        effective_armed=eff_armed, effective_streak=eff_streak, effective_prev_normal_raw=eff_prev_nr,
        gap=gap, next_state=new_state, state_updated=updated,
        close_at=session.close_at, next_open_at=nxt.open_at, next_session_date=nxt.date,
        wait_session_date=back.date if back else None,
        soxl_close=cut.soxl_close(d), series_meta=cut.description(), notes=notes,
    )


def run_day_safe(state, d, series, sessions, raw_observations):
    """evaluate_day, but input/data/conflict errors become an ErrorResult (exit code 1, state unchanged)."""
    try:
        return evaluate_day(state, d, series, sessions, raw_observations)
    except ConflictError as e:
        return ErrorResult(d if isinstance(d, str) else None, e.code, e.field, RunClass.CONFLICT, state, detail=e.detail)
    except CoreError as e:
        return ErrorResult(d if isinstance(d, str) else None, e.code, e.field, RunClass.DATA_ERROR, state, detail=e.detail)
