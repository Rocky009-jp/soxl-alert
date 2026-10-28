"""Event shapes of the S1 schema (version 1) and their builders.

GENESIS (seq 0): start_after, boundary_session, state_after (the initial state only).
APPLY (seq 1..): d, confirmed_inputs, input_hash, skipped_sessions, transition_result, state_after.
Builders and the validator in recompute.py share these helpers, so a stored event is accepted only if it equals the
event rebuilt from its own typed content (canonical form).
"""
import copy

from v2_core.state import MarketState

from .errors import snapshot_invalid
from .codec import CORE_SHA, SCHEMA_VERSION, Snapshot, canonical_json, compute_event_hash, sha256_text, utc_text

GENESIS = "GENESIS"
APPLY = "APPLY"

HEADER_KEYS = frozenset(["schema_version", "core_sha", "head_seq", "head_hash", "current_state", "events"])
GENESIS_KEYS = frozenset(["kind", "seq", "parent_seq", "parent_hash", "start_after", "boundary_session",
                          "state_after", "event_hash"])
APPLY_KEYS = frozenset(["kind", "seq", "parent_seq", "parent_hash", "d", "confirmed_inputs", "input_hash",
                        "skipped_sessions", "transition_result", "state_after", "event_hash"])
CONFIRMED_INPUT_KEYS = frozenset(["decision", "row", "prev_row", "prev_session_date", "session_context"])
SESSION_KEYS = frozenset(["date", "open_at", "close_at", "confirmed"])
ROW_KEYS = frozenset(["date", "soxx", "sma", "rsi", "shd", "prev_rsi"])
DECISION_KEYS = frozenset(["record_id", "observation_status", "observation_role", "current_fg_value",
                           "observed_at_iso8601", "target_us_session_date"])


def session_dict(s):
    return {"date": s.date, "open_at": utc_text(s.open_at, "sessions"), "close_at": utc_text(s.close_at, "sessions"),
            "confirmed": s.confirmed}


def _market_float(x, rule):
    """bool is refused before any conversion (True must never become 1.0); an int beyond float range is refused."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise snapshot_invalid(rule)
    try:
        return float(x)
    except OverflowError:
        raise snapshot_invalid(rule)


def row_dict(r, rule="row"):
    return {"date": r.date, "soxx": _market_float(r.soxx, rule), "sma": _market_float(r.sma, rule),
            "rsi": _market_float(r.rsi, rule), "shd": _market_float(r.shd, rule),
            "prev_rsi": _market_float(r.prev_rsi, rule)}


def decision_dict(o):
    """The six raw keys parse_observation reads; value as float, time as UTC text."""
    return {"record_id": o.record_id, "observation_status": o.status, "observation_role": o.role,
            "current_fg_value": float(o.value), "observed_at_iso8601": utc_text(o.observed_at, "observed_at_iso8601"),
            "target_us_session_date": o.target_date}


def serialize_transition(t):
    """The part shared by apply_transition's Transition and evaluate_day's DayResult. state_updated and display
    fields are not part of it; state_after is stored separately."""
    rules = {}
    for name, r in t.rules.items():
        rules[name] = {"name": r.name, "status": r.status.value, "ratio": r.ratio, "reasons": list(r.reasons),
                       "may_be_unconfirmed": r.may_be_unconfirmed}
    return {"rules": rules, "run_class": t.run_class.value, "gap": t.gap, "effective_armed": t.effective_armed.value,
            "effective_streak": t.effective_streak, "effective_prev_normal_raw": t.effective_prev_normal_raw.value,
            "notes": list(t.notes)}


def project_context(context):
    """Comparison projection: next(D) (the last entry) keeps date and open_at only; close_at and confirmed are dropped."""
    out = [dict(e) for e in context[:-1]]
    last = context[-1]
    out.append({"date": last["date"], "open_at": last["open_at"]})
    return out


def input_hash_of(confirmed_inputs):
    projected = dict(confirmed_inputs)
    projected["session_context"] = project_context(confirmed_inputs["session_context"])
    return sha256_text(canonical_json(projected))


def confirmed_inputs_dict(decision, row, prev_row, prev_session_date, context_sessions):
    return {"decision": decision_dict(decision), "row": row_dict(row),
            "prev_row": None if prev_row is None else row_dict(prev_row, "prev_row"),
            "prev_session_date": prev_session_date,
            "session_context": [session_dict(s) for s in context_sessions]}


def make_genesis_event(start_after, boundary_session):
    ev = {"kind": GENESIS, "seq": 0, "parent_seq": None, "parent_hash": None, "start_after": start_after,
          "boundary_session": boundary_session, "state_after": MarketState.initial().to_dict()}
    ev["event_hash"] = compute_event_hash(ev)
    return ev


def make_apply_event(seq, parent_hash, d, confirmed_inputs, skipped, transition_result, state_after):
    ev = {"kind": APPLY, "seq": seq, "parent_seq": seq - 1, "parent_hash": parent_hash, "d": d,
          "confirmed_inputs": confirmed_inputs, "input_hash": input_hash_of(confirmed_inputs),
          "skipped_sessions": list(skipped), "transition_result": transition_result, "state_after": state_after}
    ev["event_hash"] = compute_event_hash(ev)
    return ev


def snapshot_dict(events):
    last = events[-1]
    return {"schema_version": SCHEMA_VERSION, "core_sha": CORE_SHA, "head_seq": last["seq"],
            "head_hash": last["event_hash"], "current_state": copy.deepcopy(last["state_after"]),
            "events": events}


def snapshot_of(events):
    return Snapshot.from_dict(snapshot_dict(events))


def append_event(snapshot, event):
    """A new Snapshot with one more event. The original is untouched; nothing is checked here."""
    events = snapshot.events
    events.append(copy.deepcopy(event))
    return snapshot_of(events)
