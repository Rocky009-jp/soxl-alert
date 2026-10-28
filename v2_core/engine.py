"""Market condition evaluation and F&G state transition for one target session D.

evaluate_day checks inputs, picks the rows, the decision and the base state, and builds the display fields.
The transition itself (conditions, run class, next-state candidate) is computed by transition.apply_transition,
so a re-calculation from stored inputs uses the same code.

Case U only: no holdings, cost basis, cash, orders or sale history enter or leave this module.
Ratios are fractions of 'available funds' (100% / 25%), never shares or amounts.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .errors import ConflictError, CoreError, InputError
from .fixture import MarketRow, parse_iso_date
from .observations import Observation, first_unprocessed_session, select_decision
from .state import MarketState
from .tri import Tri
from .transition import (  # noqa: F401  (re-exported: display, preview and tests import these from here)
    RATIO_EXFEAR, RATIO_NORMAL, RATIO_TREND, RuleResult, RuleStatus, RunClass, Transition, apply_transition,
    market_side_normal, market_side_trend)


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

    try:
        prev_row = cut.row(prev_session.date)
    except InputError:
        prev_row = None               # previous indicators unavailable: its market-side normal is unknown
    t = apply_transition(base, d, prev_session.date, row, prev_row, decision)
    if decision is None:
        new_state, updated = state, False
    else:
        new_state, updated = t.next_state, not rerun

    back = sessions.back(d, 3)
    return DayResult(
        d=d, row=row, rules=t.rules, run_class=t.run_class, decision=decision,
        effective_armed=t.effective_armed, effective_streak=t.effective_streak,
        effective_prev_normal_raw=t.effective_prev_normal_raw,
        gap=t.gap, next_state=new_state, state_updated=updated,
        close_at=session.close_at, next_open_at=nxt.open_at, next_session_date=nxt.date,
        wait_session_date=back.date if back else None,
        soxl_close=cut.soxl_close(d), series_meta=cut.description(), notes=list(t.notes),
    )


def run_day_safe(state, d, series, sessions, raw_observations):
    """evaluate_day, but input/data/conflict errors become an ErrorResult (exit code 1, state unchanged)."""
    try:
        return evaluate_day(state, d, series, sessions, raw_observations)
    except ConflictError as e:
        return ErrorResult(d if isinstance(d, str) else None, e.code, e.field, RunClass.CONFLICT, state, detail=e.detail)
    except CoreError as e:
        return ErrorResult(d if isinstance(d, str) else None, e.code, e.field, RunClass.DATA_ERROR, state, detail=e.detail)
