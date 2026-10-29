"""Immutable values: ResolutionSet (in-memory, text-backed). Structured accessors always return fresh copies."""
import copy
import json
import math

from v2_persistence.codec import canonical_json, sha256_text

from .errors import resolution_invalid

SCHEMA = "soxl-v2-resolution-set/1"
_MAX_DEPTH = 40


def check_json(value, field="resolutions", depth=0):
    if depth > _MAX_DEPTH:
        raise resolution_invalid(field, "json_depth")
    t = type(value)
    if value is None or t is bool or t is str or t is int:
        return
    if t is float:
        if not math.isfinite(value):
            raise resolution_invalid(field, "json_number")
        return
    if t is list:
        for v in value:
            check_json(v, field, depth + 1)
        return
    if t is dict:
        for k, v in value.items():
            if type(k) is not str:
                raise resolution_invalid(field, "json_key")
            check_json(v, field, depth + 1)
        return
    raise resolution_invalid(field, "json_type")


def no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key")
        out[k] = v
    return out


def reject_constant(_name):
    raise ValueError("non-finite number")


class ResolutionSet:
    """The chain of acknowledgement / declaration records. A verification value in memory; nothing here is stored.

    Build with ResolutionSet.from_dict / decode_resolutions / empty_resolutions; check with validate_resolutions.
    """

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use ResolutionSet.from_dict or decode_resolutions")

    @classmethod
    def from_dict(cls, data):
        """Copy a JSON-compatible dict. Checks JSON compatibility only, not the contents."""
        check_json(data)
        try:
            text = canonical_json(data)
            view = json.loads(text)
        except (TypeError, ValueError, RecursionError):
            raise resolution_invalid("resolutions", "json") from None
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", view)
        return obj

    def __setattr__(self, name, value):
        raise AttributeError("ResolutionSet is immutable")

    def __delattr__(self, name):
        raise AttributeError("ResolutionSet is immutable")

    def __eq__(self, other):
        return isinstance(other, ResolutionSet) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def __repr__(self):
        seq = self._view.get("head_resolution_seq") if isinstance(self._view, dict) else None
        return "ResolutionSet(head_resolution_seq=%s)" % (seq if type(seq) is int else "?")

    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def records(self):
        recs = self._view.get("records") if isinstance(self._view, dict) else None
        return copy.deepcopy(recs)

    @property
    def head_resolution_seq(self):
        return self._view.get("head_resolution_seq") if isinstance(self._view, dict) else None

    @property
    def head_resolution_hash(self):
        return self._view.get("head_resolution_hash") if isinstance(self._view, dict) else None

    @property
    def digest(self):
        return sha256_text(self._text)


def empty_resolutions():
    return ResolutionSet.from_dict(
        {"schema": SCHEMA, "head_resolution_seq": 0, "head_resolution_hash": None, "records": []})


def encode_resolutions(resolutions):
    if not isinstance(resolutions, ResolutionSet):
        raise resolution_invalid("resolutions", "type")
    return resolutions._text


def decode_resolutions(text):
    """Strict text -> ResolutionSet. Rejects duplicate keys and NaN/Infinity; does not validate the contents."""
    if not isinstance(text, str):
        raise resolution_invalid("resolutions", "type")
    try:
        data = json.loads(text, object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise resolution_invalid("resolutions", "json") from None
    return ResolutionSet.from_dict(data)
