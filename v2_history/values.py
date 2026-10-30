"""Fixed names and key sets of schema version 2, and the immutable History value.

A History keeps only its canonical JSON text (plus a private parsed view that is never handed out). Every accessor that
returns structured data returns a fresh copy. encode/decode only convert to and from text; they never touch a path.
"""
import copy
import json
import math

from v2_persistence.codec import CORE_SHA, canonical_json, sha256_text
from v2_persistence.events import APPLY_KEYS, GENESIS_KEYS

from .errors import history_invalid

SCHEMA_VERSION_V2 = 2

GENESIS = "GENESIS"
APPLY = "APPLY"
ACK = "ACK"
DECLARE_MISSING = "DECLARE_MISSING"
RESTART_UNKNOWN = "RESTART_UNKNOWN"
RECOVERY_RESTORE = "RECOVERY_RESTORE"
SCHEMA_MIGRATION = "SCHEMA_MIGRATION"
KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, SCHEMA_MIGRATION)
# Designed for B-5 and refused here (unsupported_event).
RECOVERY_PREFIX_ADOPTION = "RECOVERY_PREFIX_ADOPTION"

HEADER_KEYS = frozenset(["schema_version", "core_sha", "head_seq", "head_hash", "current_state", "events"])
_RESOLUTION_KEYS = frozenset([
    "kind", "seq", "parent_seq", "parent_hash", "variant", "d", "record_fingerprints", "applied_ref", "missing_ref",
    "session_context", "frontier_before", "request_id", "request_hash", "request_basis", "command_index",
    "command_count", "reason_code", "requested_at", "ledger_digest", "origin", "replay_of", "state_after",
    "event_hash"])
RESTART_KEYS = frozenset([
    "kind", "seq", "parent_seq", "parent_hash", "resume_after", "boundary_session", "floor", "request_id",
    "request_hash", "request_basis", "reason_code", "requested_at", "replay_of", "state_after", "event_hash"])
RESTORE_KEYS = frozenset([
    "kind", "seq", "prev_hash", "parent_seq", "parent_hash", "superseded_seqs", "replay", "request_id",
    "request_hash", "request_basis", "reason_code", "requested_at", "ledger_digest", "state_after", "event_hash"])
MIGRATION_KEYS = frozenset([
    "kind", "seq", "parent_seq", "parent_hash", "source", "source_resolutions", "event_map", "resolution_map",
    "request_id", "request_hash", "request_basis", "reason_code", "requested_at", "ledger_digest", "state_after",
    "event_hash"])
RECORD_KEYS = {
    GENESIS: frozenset(GENESIS_KEYS), APPLY: frozenset(APPLY_KEYS), ACK: _RESOLUTION_KEYS,
    DECLARE_MISSING: _RESOLUTION_KEYS, RESTART_UNKNOWN: RESTART_KEYS, RECOVERY_RESTORE: RESTORE_KEYS,
    SCHEMA_MIGRATION: MIGRATION_KEYS}

_MAX_DEPTH = 40


def check_json(value, depth=0):
    if depth > _MAX_DEPTH:
        raise history_invalid("json_depth")
    t = type(value)
    if value is None or t is bool or t is str or t is int:
        return
    if t is float:
        if not math.isfinite(value):
            raise history_invalid("json_number")
        return
    if t is list:
        for v in value:
            check_json(v, depth + 1)
        return
    if t is dict:
        for k, v in value.items():
            if type(k) is not str:
                raise history_invalid("json_key")
            check_json(v, depth + 1)
        return
    raise history_invalid("json_type")


def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def _reject_constant(_name):
    raise ValueError("non-finite number")


class History:
    """Immutable schema-2 history value. Build with History.from_dict / decode_history; check with validate_history."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use History.from_dict or decode_history")

    @classmethod
    def from_dict(cls, data):
        """Copy a JSON-compatible dict into a History. Checks JSON compatibility only, not the history."""
        check_json(data)
        try:
            text = canonical_json(data)
            view = json.loads(text)
        except RecursionError:
            raise history_invalid("json_depth") from None
        except (TypeError, ValueError, OverflowError):      # e.g. an integer too long to be written as text
            raise history_invalid("json_number") from None
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", view)
        return obj

    def __setattr__(self, name, value):
        raise AttributeError("History is immutable")

    def __delattr__(self, name):
        raise AttributeError("History is immutable")

    def __eq__(self, other):
        return isinstance(other, History) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def __repr__(self):
        return "History(%d chars)" % len(self._text)

    # --- read access: always fresh copies -------------------------------------------------------------------
    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def events(self):
        return copy.deepcopy(self._view.get("events")) if isinstance(self._view, dict) else None

    @property
    def current_state(self):
        return copy.deepcopy(self._view.get("current_state")) if isinstance(self._view, dict) else None

    @property
    def head_seq(self):
        return self._view.get("head_seq") if isinstance(self._view, dict) else None

    @property
    def head_hash(self):
        return self._view.get("head_hash") if isinstance(self._view, dict) else None

    @property
    def schema_version(self):
        return self._view.get("schema_version") if isinstance(self._view, dict) else None

    @property
    def digest(self):
        return sha256_text(self._text)


def encode_history(history):
    if not isinstance(history, History):
        raise history_invalid("type")
    return history._text


def decode_history(text):
    """Strict text -> History. Rejects duplicate keys, NaN/Infinity and non-JSON values; does not validate history."""
    if not isinstance(text, str):
        raise history_invalid("type")
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except RecursionError:
        raise history_invalid("json_depth") from None
    except (ValueError, OverflowError):
        raise history_invalid("json") from None
    return History.from_dict(data)


def history_dict(events):
    """The header around a list of records (the last record is the head and carries the current state)."""
    last = events[-1]
    return {"schema_version": SCHEMA_VERSION_V2, "core_sha": CORE_SHA, "head_seq": last["seq"],
            "head_hash": last["event_hash"], "current_state": copy.deepcopy(last["state_after"]), "events": events}
