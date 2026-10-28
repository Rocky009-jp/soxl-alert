"""validate_snapshot: structure, hash chain, saved inputs and a full re-calculation of the history.

Every APPLY is recalculated from its saved inputs with v2_core's apply_transition (imported by name below; that name
in this module is what a re-calculation really calls). No rule or state formula is copied here. A failure is never
repaired. Errors are `snapshot_invalid` with a fixed `rule`, `unsupported_schema` or `unsupported_event`.

This is an integrity check of the stored history against itself. It does not prove who wrote it: a history whose
every field was rewritten and re-calculated consistently cannot be told apart from a genuine one.
"""
from dataclasses import dataclass
from typing import List

from v2_core.errors import ConflictError, InputError
from v2_core.fixture import MarketRow, parse_iso_date
from v2_core.observations import parse_observation
from v2_core.sessions import SessionList
from v2_core.state import MarketState, StateInvalid
from v2_core.transition import apply_transition

from .codec import CORE_SHA, SCHEMA_VERSION, Snapshot, canonical_json, compute_event_hash
from .errors import PersistenceError, snapshot_invalid
from .events import (APPLY, APPLY_KEYS, CONFIRMED_INPUT_KEYS, DECISION_KEYS, GENESIS, GENESIS_KEYS, HEADER_KEYS,
                     ROW_KEYS, SESSION_KEYS, confirmed_inputs_dict, input_hash_of, serialize_transition, session_dict)

_SHA = "0123456789abcdef"


@dataclass
class AppliedDay:
    """What the runner needs from one validated APPLY. Read-only by convention; built from the private view."""
    seq: int
    d: str
    parent_hash: str
    event_hash: str
    input_hash: str
    context: list                  # saved session_context (dicts, full copy)
    stored_sessions: SessionList   # the saved session_context as a SessionList
    skipped: List[str]
    record_id: str
    fingerprint: str
    transition_result: dict
    state_after: dict


@dataclass
class ValidatedSnapshot:
    start_after: str
    boundary_session: dict
    applies: List[AppliedDay]
    head_seq: int
    head_hash: str
    state: MarketState


def _is_int(x):
    return type(x) is int


def _same(a, b):
    return canonical_json(a) == canonical_json(b)


def _is_hash(x):
    return isinstance(x, str) and len(x) == 64 and all(c in _SHA for c in x)


def _keys(obj, expected, rule):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        raise snapshot_invalid(rule)


def _sessions(items, rule):
    if not isinstance(items, list) or not items:
        raise snapshot_invalid(rule)
    try:
        sl = SessionList.from_dicts(items)
    except InputError:
        raise snapshot_invalid(rule)
    for e in items:
        _keys(e, SESSION_KEYS, rule)
    if not _same([session_dict(s) for s in sl.sessions], items):
        raise snapshot_invalid("not_canonical")
    return sl


def _num(x, rule, positive=False, lo=None, hi=None):
    if type(x) not in (int, float):
        raise snapshot_invalid(rule)
    v = float(x)
    if v != v or v in (float("inf"), float("-inf")):
        raise snapshot_invalid(rule)
    if positive and not v > 0:
        raise snapshot_invalid(rule)
    if lo is not None and not (lo <= v <= hi):
        raise snapshot_invalid(rule)
    return v


def _row(raw, rule):
    _keys(raw, ROW_KEYS, rule)
    try:
        date = parse_iso_date(raw["date"], "market")
    except InputError:
        raise snapshot_invalid(rule)
    return MarketRow(date, _num(raw["soxx"], rule, positive=True), _num(raw["sma"], rule, positive=True),
                     _num(raw["rsi"], rule, lo=0.0, hi=100.0), _num(raw["shd"], rule),
                     _num(raw["prev_rsi"], rule, lo=0.0, hi=100.0))


def _state(raw, rule):
    try:
        st = MarketState.from_dict(raw)
    except StateInvalid as e:
        raise snapshot_invalid("%s:%s" % (rule, e.rule))
    except InputError:
        raise snapshot_invalid(rule)
    if not _same(st.to_dict(), raw):
        raise snapshot_invalid("not_canonical")
    return st


def _stripped(state):
    """A parent state reduced to a base: fixed_decision and base dropped (the value IB-04 compares)."""
    return MarketState(state.as_of_d, state.armed, state.streak, state.prev_normal_raw)


def validate_snapshot(snapshot):
    """Raise on any problem; return a ValidatedSnapshot for the caller's use. Never modifies anything."""
    if not isinstance(snapshot, Snapshot):
        raise snapshot_invalid("type")
    data = snapshot._internal()
    if not isinstance(data, dict):
        raise snapshot_invalid("shape")
    sv = data.get("schema_version")
    if not _is_int(sv) or sv != SCHEMA_VERSION:
        raise PersistenceError("unsupported_schema", "schema_version")
    if data.get("core_sha") != CORE_SHA:
        raise PersistenceError("unsupported_schema", "core_sha")
    _keys(data, HEADER_KEYS, "header_keys")
    events = data["events"]
    if not isinstance(events, list) or not events:
        raise snapshot_invalid("events")
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") not in (GENESIS, APPLY):
            raise PersistenceError("unsupported_event", "kind")

    genesis = events[0]
    if genesis["kind"] != GENESIS:
        raise snapshot_invalid("first_not_genesis")
    start_after, boundary = _check_genesis(genesis)

    prev_event = genesis
    prev_state = MarketState.initial()
    prev_d = None
    prev_context = None
    applies = []
    for i in range(1, len(events)):
        ev = events[i]
        if ev["kind"] != APPLY:
            raise snapshot_invalid("genesis_not_first")
        applied, prev_state = _check_apply(ev, i, prev_event, prev_state, prev_d, prev_context, start_after, boundary)
        applies.append(applied)
        prev_event, prev_d, prev_context = ev, ev["d"], applied.context

    last = events[-1]
    if not _is_int(data["head_seq"]) or data["head_seq"] != last["seq"]:
        raise snapshot_invalid("head_seq")
    if data["head_hash"] != last["event_hash"]:
        raise snapshot_invalid("head_hash")
    if not _same(data["current_state"], last["state_after"]):
        raise snapshot_invalid("current_state")
    state = _state(data["current_state"], "current_state")
    return ValidatedSnapshot(start_after, boundary, applies, last["seq"], last["event_hash"], state)


def _check_genesis(ev):
    _keys(ev, GENESIS_KEYS, "genesis_keys")
    if not _is_int(ev["seq"]) or ev["seq"] != 0 or ev["parent_seq"] is not None or ev["parent_hash"] is not None:
        raise snapshot_invalid("genesis_seq")
    if ev["event_hash"] != compute_event_hash(ev):
        raise snapshot_invalid("event_hash")
    try:
        start_after = parse_iso_date(ev["start_after"], "start_after")
    except InputError:
        raise snapshot_invalid("genesis_boundary")
    sl = _sessions([ev["boundary_session"]], "genesis_boundary")
    s = sl.sessions[0]
    if s.date != start_after or not s.confirmed:
        raise snapshot_invalid("genesis_boundary")
    if not _same(ev["state_after"], MarketState.initial().to_dict()):
        raise snapshot_invalid("genesis_state")
    return start_after, ev["boundary_session"]


def _check_apply(ev, i, parent, parent_state, prev_d, prev_context, start_after, boundary):
    _keys(ev, APPLY_KEYS, "apply_keys")
    if not _is_int(ev["seq"]) or ev["seq"] != i:
        raise snapshot_invalid("seq")
    if not _is_int(ev["parent_seq"]) or ev["parent_seq"] != i - 1:
        raise snapshot_invalid("parent_seq")
    if ev["parent_hash"] != parent["event_hash"]:
        raise snapshot_invalid("parent_hash")
    if not _is_hash(ev["event_hash"]) or ev["event_hash"] != compute_event_hash(ev):
        raise snapshot_invalid("event_hash")
    try:
        d = parse_iso_date(ev["d"], "d")
    except InputError:
        raise snapshot_invalid("apply_d")
    base_date = start_after if prev_d is None else prev_d
    if not d > base_date:
        raise snapshot_invalid("d_order")

    ci = ev["confirmed_inputs"]
    _keys(ci, CONFIRMED_INPUT_KEYS, "confirmed_inputs_keys")
    sl = _sessions(ci["session_context"], "session_context")
    context = ci["session_context"]
    ds = sl.get(d)
    nxt = sl.next(d)
    prev_session = sl.previous(d)
    if context[0]["date"] != base_date or ds is None or nxt is None or prev_session is None:
        raise snapshot_invalid("session_context")
    if nxt.date != context[-1]["date"] or not ds.confirmed or not sl.sessions[0].confirmed:
        raise snapshot_invalid("session_context")
    if prev_context is None:
        if not _same(context[0], boundary):
            raise snapshot_invalid("context_boundary")
    elif not _same(context[0], prev_context[-2]):
        raise snapshot_invalid("context_continuity")
    if ci["prev_session_date"] != prev_session.date:
        raise snapshot_invalid("prev_session_date")
    between = [s for s in sl.sessions if base_date < s.date < d]
    if any(not s.confirmed for s in between):
        raise snapshot_invalid("skipped_session_unconfirmed")
    if not _same(ev["skipped_sessions"], [s.date for s in between]):
        raise snapshot_invalid("skipped_sessions")

    row = _row(ci["row"], "row")
    if row.date != d:
        raise snapshot_invalid("row")
    prev_row = None if ci["prev_row"] is None else _row(ci["prev_row"], "prev_row")
    if prev_row is not None and prev_row.date != prev_session.date:
        raise snapshot_invalid("prev_row")

    _keys(ci["decision"], DECISION_KEYS, "decision")
    try:
        obs = parse_observation(ci["decision"])
    except (InputError, ConflictError):
        raise snapshot_invalid("decision")
    if obs.role != "decision" or obs.status != "observed" or obs.target_date != d:
        raise snapshot_invalid("decision")
    if not (ds.close_at <= obs.observed_at < nxt.open_at):
        raise snapshot_invalid("decision_window")
    rebuilt = confirmed_inputs_dict(obs, row, prev_row, ci["prev_session_date"], sl.sessions)
    if not _same(rebuilt, ci):
        raise snapshot_invalid("not_canonical")
    if ev["input_hash"] != input_hash_of(ci):
        raise snapshot_invalid("input_hash")

    state_after = _state(ev["state_after"], "state_after")
    base = state_after.base
    if base is None or not _same(base.to_dict(), _stripped(parent_state).to_dict()):
        raise snapshot_invalid("IB-04")

    t = apply_transition(parent_state, d, prev_session.date, row, prev_row, obs)
    if t.next_state is None or not _same(serialize_transition(t), ev["transition_result"]):
        raise snapshot_invalid("transition_mismatch")
    if not _same(t.next_state.to_dict(), ev["state_after"]):
        raise snapshot_invalid("state_mismatch")
    applied = AppliedDay(
        seq=i, d=d, parent_hash=ev["parent_hash"], event_hash=ev["event_hash"], input_hash=ev["input_hash"],
        context=[dict(e) for e in context], stored_sessions=sl, skipped=list(ev["skipped_sessions"]),
        record_id=obs.record_id, fingerprint=obs.fingerprint(), transition_result=ev["transition_result"],
        state_after=ev["state_after"])
    return applied, state_after
