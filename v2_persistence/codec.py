"""Canonical JSON, hashes, UTC time text and the immutable Snapshot value.

A Snapshot keeps only its canonical JSON text (plus a private parsed view that is never handed out). Every accessor
that returns structured data returns a fresh copy, so no caller can change a stored Snapshot from outside.
encode/decode only convert to and from text; they never touch a path or a file.
"""
import copy
import hashlib
import json
import math
from datetime import timezone

from v2_core.errors import InputError

from .errors import snapshot_invalid

SCHEMA_VERSION = 1
# The v2_core base this schema was written against. A constant, not a self-check of the running v2_core.
CORE_SHA = "b616b4ec7169420e199ec7e247dd375b3603a013"

_MAX_DEPTH = 40


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_event_hash(event):
    """SHA-256 of the canonical event without its own event_hash (the saved full copy is included)."""
    body = {k: v for k, v in event.items() if k != "event_hash"}
    return sha256_text(canonical_json(body))


def utc_text(dt, field="time"):
    """Fixed UTC text: YYYY-MM-DDTHH:MM:SS[.ffffff]Z. The same instant always gives the same text."""
    try:
        u = dt.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise InputError("datetime_invalid", field)
    text = "%04d-%02d-%02dT%02d:%02d:%02d" % (u.year, u.month, u.day, u.hour, u.minute, u.second)
    if u.microsecond:
        text += ".%06d" % u.microsecond
    return text + "Z"


def _check_json(value, depth=0):
    if depth > _MAX_DEPTH:
        raise snapshot_invalid("json_depth")
    t = type(value)
    if value is None or t is bool or t is str or t is int:
        return
    if t is float:
        if not math.isfinite(value):
            raise snapshot_invalid("json_number")
        return
    if t is list:
        for v in value:
            _check_json(v, depth + 1)
        return
    if t is dict:
        for k, v in value.items():
            if type(k) is not str:
                raise snapshot_invalid("json_key")
            _check_json(v, depth + 1)
        return
    raise snapshot_invalid("json_type")


def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def _reject_constant(_name):
    raise ValueError("non-finite number")


class Snapshot:
    """Immutable history value. Build with from_dict / decode_snapshot; check with validate_snapshot."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use Snapshot.from_dict or decode_snapshot")

    @classmethod
    def from_dict(cls, data):
        """Copy a JSON-compatible dict into a Snapshot. Checks JSON compatibility only, not the history."""
        _check_json(data)
        try:
            text = canonical_json(data)
            view = json.loads(text)
        except (TypeError, ValueError, RecursionError):
            raise snapshot_invalid("json")
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", view)
        return obj

    def __setattr__(self, name, value):
        raise AttributeError("Snapshot is immutable")

    def __delattr__(self, name):
        raise AttributeError("Snapshot is immutable")

    def __eq__(self, other):
        return isinstance(other, Snapshot) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def __repr__(self):
        return "Snapshot(%d chars)" % len(self._text)

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
    def core_sha(self):
        return self._view.get("core_sha") if isinstance(self._view, dict) else None

    @property
    def schema_version(self):
        return self._view.get("schema_version") if isinstance(self._view, dict) else None

    def _internal(self):
        """The private parsed view for read-only use inside this package. Never return or mutate it."""
        return self._view


def encode_snapshot(snapshot):
    if not isinstance(snapshot, Snapshot):
        raise snapshot_invalid("type")
    return snapshot._text


def decode_snapshot(text):
    """Strict text -> Snapshot. Rejects duplicate keys, NaN/Infinity and non-JSON values; does not validate history."""
    if not isinstance(text, str):
        raise snapshot_invalid("type")
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise snapshot_invalid("json")
    return Snapshot.from_dict(data)
