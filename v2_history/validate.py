"""validate_history: the order of design 4.5. Raises on any problem; repairs nothing.

1 form (header, schema, kinds, keys)  2 audit chain  3 effective parents, start, migration position
4 every RECOVERY_RESTORE and its batch  5 final chain and the superseded union  6 each chain view (S1 projection and
control rules)  7 SCHEMA_MIGRATION reverse check  8 current_state.

Integrity of the stored history against itself, not proof of who wrote it.
"""
from dataclasses import dataclass

from v2_core.errors import CoreError
from v2_core.state import MarketState
from v2_persistence.codec import CORE_SHA, canonical_json, compute_event_hash, sha256_text
from v2_persistence.errors import PersistenceError

from .common import is_hex64, is_int, same
from .errors import history_invalid, unsupported_event, unsupported_schema
from .migration import check_positions, reconstruct
from .restore import chain_to, check_restores
from .values import (GENESIS, HEADER_KEYS, KINDS, RECORD_KEYS, RECOVERY_RESTORE, SCHEMA_VERSION_V2, History)
from .view import check_view, initial_state_dict


def _bad(rule):
    return history_invalid(rule)


@dataclass(frozen=True)
class Boundary:
    kind: str
    seq: int
    after: str


@dataclass(frozen=True)
class HistoryCheck:
    """Outcome of validate_history: counts, seqs, dates and digests only. No ledger row, F&G value or free text."""
    head_seq: int
    head_hash: str
    record_count: int
    effective_seqs: tuple
    superseded_seqs: tuple
    current_boundary: Boundary
    latest_apply_d: object
    processing_after: str
    declared_days_in_segment: tuple
    migrated: bool
    history_digest: str
    state_digest: str


def validate_history(history):
    """Check a History. Returns an independent, immutable HistoryCheck; raises PersistenceError otherwise."""
    if not isinstance(history, History):
        raise _bad("type")
    try:
        return _validate(history)
    except PersistenceError:
        raise
    except (CoreError, KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError):
        raise _bad("malformed") from None


def _validate(history):
    data = history.to_dict()
    events = _form(data)
    parents = _audit_chain(data, events)
    migration_seq = _parents_and_start(events, parents)
    check_restores(events, parents, migration_seq)
    final = chain_to(parents, len(events) - 1)
    superseded = _superseded_union(events, final)
    for k, rec in enumerate(events):
        if rec["kind"] == RECOVERY_RESTORE:
            check_view([events[s] for s in chain_to(parents, k - 1)])
    summary = check_view([events[s] for s in final])
    if migration_seq is not None:
        reconstruct(events, migration_seq)
    state = _current_state(data, events)
    last = summary.last_segment
    as_of = state["as_of_d"]
    return HistoryCheck(
        head_seq=events[-1]["seq"], head_hash=events[-1]["event_hash"], record_count=len(events),
        effective_seqs=tuple(final), superseded_seqs=tuple(superseded),
        current_boundary=Boundary(last.kind, last.seq, last.date), latest_apply_d=summary.latest_apply_d,
        processing_after=as_of if as_of is not None else last.date,
        declared_days_in_segment=tuple(summary.last_segment_declared), migrated=migration_seq is not None,
        history_digest=history.digest, state_digest=sha256_text(canonical_json(state)))


def _form(data):
    if not isinstance(data, dict):
        raise _bad("shape")
    sv = data.get("schema_version")
    if not is_int(sv) or sv != SCHEMA_VERSION_V2:
        raise unsupported_schema("schema_version")
    if data.get("core_sha") != CORE_SHA:
        raise unsupported_schema("core_sha")
    if set(data) != HEADER_KEYS:
        raise _bad("header_keys")
    events = data["events"]
    if not isinstance(events, list) or not events:
        raise _bad("events")
    for ev in events:
        if not isinstance(ev, dict) or ev.get("kind") not in KINDS:
            raise unsupported_event()
    for ev in events:
        if set(ev) != RECORD_KEYS[ev["kind"]]:
            raise _bad("record_keys")
    return events


def _audit_chain(data, events):
    """seq, event_hash and the audit-previous hash of every record, then the head. Returns the effective parents."""
    parents = []
    for i, ev in enumerate(events):
        if not is_int(ev["seq"]) or ev["seq"] != i:
            raise _bad("seq")
        if i == 0:
            if ev["kind"] != GENESIS:
                raise _bad("first_not_genesis")
            if ev["parent_seq"] is not None or ev["parent_hash"] is not None:
                raise _bad("seq")
        elif ev["kind"] == GENESIS:
            raise _bad("genesis_not_first")
        if not is_hex64(ev["event_hash"]) or ev["event_hash"] != compute_event_hash(ev):
            raise _bad("event_hash")
        if i > 0:
            audit_previous = ev["prev_hash"] if ev["kind"] == RECOVERY_RESTORE else ev["parent_hash"]
            if audit_previous != events[i - 1]["event_hash"]:
                raise _bad("audit_hash")
        parents.append(ev["parent_seq"])
    last = events[-1]
    if not is_int(data["head_seq"]) or data["head_seq"] != last["seq"]:
        raise _bad("head")
    if data["head_hash"] != last["event_hash"]:
        raise _bad("head")
    return parents


def _parents_and_start(events, parents):
    """Effective parents are the previous record, except RECOVERY_RESTORE (any earlier record). Returns the seq of the
    SCHEMA_MIGRATION or None."""
    if not same(events[0]["state_after"], initial_state_dict()):
        raise _bad("genesis_state")
    for i in range(1, len(events)):
        ev = events[i]
        ps = ev["parent_seq"]
        if ev["kind"] == RECOVERY_RESTORE:
            if not is_int(ps) or not 0 <= ps <= i - 1:
                raise _bad("parent")
        elif not is_int(ps) or ps != i - 1:
            raise _bad("parent")
        if ev["parent_hash"] != events[ps]["event_hash"]:
            raise _bad("parent")
    return check_positions(events)


def _superseded_union(events, final):
    on_chain = set(final)
    off_chain = [i for i in range(len(events)) if i not in on_chain]
    union = []
    for ev in events:
        if ev["kind"] == RECOVERY_RESTORE:
            union.extend(ev["superseded_seqs"])
    if len(union) != len(set(union)) or sorted(union) != off_chain:
        raise _bad("superseded_mismatch")
    return off_chain


def _current_state(data, events):
    state = data["current_state"]
    if not same(state, events[-1]["state_after"]):
        raise _bad("current_state")
    if not same(MarketState.from_dict(state).to_dict(), state):
        raise _bad("current_state")
    return state
