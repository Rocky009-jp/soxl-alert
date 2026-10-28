"""make_genesis and prepare_day: one explicit target session D per call.

prepare_day never writes. Order of checks (fixed): 1. the Snapshot, 2. D and the sessions it needs, 3. the ledger
against what was stored, 4. v2_core.evaluate_day and, for the latest applied D, the comparison with the stored record.
Core errors on injected inputs are raised unchanged; the core is never asked to turn an error into NO_SIGNAL.
"""
import copy

from v2_core.engine import evaluate_day
from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_core.observations import select_decision
from v2_core.sessions import SessionList

from .codec import canonical_json
from .errors import PersistenceError, snapshot_invalid
from .events import (append_event, confirmed_inputs_dict, input_hash_of, make_apply_event, make_genesis_event,
                     project_context, serialize_transition, session_dict, snapshot_of)
from .plan import ALREADY_APPLIED, NO_COMMIT, PREPARED, AppendPlan, PrepareResult
from .recompute import validate_snapshot


def _copy_sessions(sessions):
    if not isinstance(sessions, SessionList):
        raise InputError("sessions_invalid", "sessions")
    return SessionList(list(sessions.sessions))


def make_genesis(start_after, sessions):
    """GENESIS-only Snapshot. start_after is an explicit, confirmed session: the excluded lower bound of processing.

    The initial state is MarketState() (as_of_d stays null). No other state can be imported.
    """
    parse_iso_date(start_after, "start_after")
    sl = _copy_sessions(sessions)
    s = sl.get(start_after)
    if s is None:
        raise PersistenceError("genesis_boundary_missing", "start_after")
    if not s.confirmed:
        raise PersistenceError("genesis_boundary_unconfirmed", "start_after")
    snapshot = snapshot_of([make_genesis_event(start_after, session_dict(s))])
    validate_snapshot(snapshot)
    return snapshot


def _check_applied_day(ap, sl, raw):
    """Stored range vs current sessions (missing / mismatch), then the ledger against the stored decision."""
    index = {s.date: i for i, s in enumerate(sl.sessions)}
    if any(e["date"] not in index for e in ap.context):
        raise PersistenceError("session_context_missing", "sessions", detail=ap.d)
    lo, hi = index[ap.context[0]["date"]], index[ap.context[-1]["date"]]
    current = [session_dict(s) for s in sl.sessions[lo:hi + 1]]
    if project_context(current) != project_context(ap.context):
        raise PersistenceError("session_context_mismatch", "sessions", detail=ap.d)
    for sessions in (ap.stored_sessions, sl):
        chosen = select_decision(raw, sessions, ap.d)
        if chosen is None or chosen.record_id != ap.record_id or chosen.fingerprint() != ap.fingerprint:
            raise PersistenceError("ledger_mismatch", "observations", detail=ap.d)


def prepare_day(snapshot, d, series, sessions, raw_observations):
    v = validate_snapshot(snapshot)                                          # 1
    raw = copy.deepcopy(raw_observations)
    sl = _copy_sessions(sessions)
    parse_iso_date(d, "target_session_date")                                 # 2
    cut = series.through(d)                       # a copy made once: nothing after D, and later edits stay outside
    if not d > v.start_after:
        raise PersistenceError("target_not_after_genesis", "target_session_date")
    latest = v.state.as_of_d
    if latest is not None and d < latest:
        raise InputError("state_ahead_of_target", "state")
    session = sl.get(d)
    if session is None:
        raise InputError("target_not_in_sessions", "sessions")
    if not session.confirmed:
        raise InputError("target_unconfirmed", "sessions")
    nxt = sl.next(d)
    if nxt is None:
        raise InputError("next_session_missing", "sessions")
    prev_session = sl.previous(d)
    if prev_session is None:
        raise InputError("previous_session_missing", "sessions")
    rerun = latest == d
    boundary = v.applies[-1].context[0]["date"] if rerun else (latest if latest is not None else v.start_after)
    between = [] if rerun else [s for s in sl.sessions if boundary < s.date < d]
    if not rerun:
        if sl.get(boundary) is None:
            raise PersistenceError("session_context_missing", "sessions", detail=boundary)
        for s in between:
            if not s.confirmed:
                raise PersistenceError("intermediate_session_unconfirmed", "sessions", detail=s.date)

    for ap in v.applies:                                                     # 3
        _check_applied_day(ap, sl, raw)
    for ap in v.applies:
        for sd in ap.skipped:
            if select_decision(raw, sl, sd) is not None:
                raise PersistenceError("late_observation", "observations", detail=sd)
    if not rerun:
        unprocessed = [s.date for s in between if select_decision(raw, sl, s.date) is not None]
        if unprocessed:
            raise PersistenceError("intermediate_session_unprocessed", "observations", detail=unprocessed[0])

    day = evaluate_day(v.state, d, cut, sl, raw)                             # 4
    if day.decision is None:
        return PrepareResult(NO_COMMIT, None, day)

    try:
        prev_row = cut.row(prev_session.date)
    except InputError:
        prev_row = None
    i0 = next(i for i, s in enumerate(sl.sessions) if s.date == boundary)
    i1 = next(i for i, s in enumerate(sl.sessions) if s.date == nxt.date)
    try:
        ci = confirmed_inputs_dict(day.decision, day.row, prev_row, prev_session.date, sl.sessions[i0:i1 + 1])
        transition = serialize_transition(day)
        state_after = day.next_state.to_dict()
        input_hash_of(ci)                         # a non-finite market value cannot be written as JSON
    except (ValueError, TypeError, OverflowError):
        raise snapshot_invalid("event_build")

    if rerun:
        stored = v.applies[-1]
        if input_hash_of(ci) != stored.input_hash:
            raise PersistenceError("recompute_mismatch", "confirmed_inputs")
        if canonical_json(transition) != canonical_json(stored.transition_result):
            raise PersistenceError("recompute_mismatch", "transition_result")
        if canonical_json(state_after) != canonical_json(stored.state_after):
            raise PersistenceError("recompute_mismatch", "state")
        return PrepareResult(ALREADY_APPLIED, None, day)

    event = make_apply_event(v.head_seq + 1, v.head_hash, d, ci, [s.date for s in between], transition, state_after)
    validate_snapshot(append_event(snapshot, event))       # the candidate passes the same full check as a commit
    return PrepareResult(PREPARED, AppendPlan(v.head_seq, v.head_hash, event), day)
