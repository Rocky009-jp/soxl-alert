"""Immutable values of the history operations. Each keeps only canonical JSON text plus a private parsed view that is
never handed out; every accessor that returns structured data returns a fresh copy. A value built by from_dict is
unverified until the function that consumes it checks it; nothing it carries is printed as it is.
"""
import copy
import json

from v2_persistence.codec import canonical_json, sha256_text

from .errors import history_invalid


class _Frozen:
    """Text-backed immutable value. Subclasses add properties; the text is the identity."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("%s is built by a history operation" % type(self).__name__)

    @classmethod
    def _wrap(cls, view, on_error):
        """Copy a JSON-compatible dict into a new value. on_error(rule) builds the refusal for a value that cannot
        be written as JSON text."""
        try:
            text = canonical_json(view)
            loaded = json.loads(text)
        except RecursionError:
            raise on_error("json_depth") from None
        except (TypeError, ValueError, OverflowError):      # e.g. an integer too long to be written as text
            raise on_error("json_number") from None
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", loaded)
        return obj

    def __setattr__(self, name, value):
        raise AttributeError("%s is immutable" % type(self).__name__)

    def __delattr__(self, name):
        raise AttributeError("%s is immutable" % type(self).__name__)

    def __eq__(self, other):
        return type(other) is type(self) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def to_dict(self):
        return copy.deepcopy(self._view)


def _history_error(rule):
    return history_invalid(rule)


class EffectiveView(_Frozen):
    """What a checked history says: effective records, segments, references and every request id. No ledger row,
    F&G value, stored decision or session context is held."""

    __slots__ = ()

    @classmethod
    def _make(cls, view):
        return cls._wrap(view, _history_error)

    def _get(self, key):
        return copy.deepcopy(self._view[key])

    history_digest = property(lambda self: self._get("history_digest"))
    head_seq = property(lambda self: self._get("head_seq"))
    head_hash = property(lambda self: self._get("head_hash"))
    state_digest = property(lambda self: self._get("state_digest"))
    migrated = property(lambda self: self._get("migrated"))
    migration_seq = property(lambda self: self._get("migration_seq"))
    effective_seqs = property(lambda self: self._get("effective_seqs"))
    superseded_seqs = property(lambda self: self._get("superseded_seqs"))
    current_boundary = property(lambda self: self._get("current_boundary"))
    processing_after = property(lambda self: self._get("processing_after"))
    latest_apply_d = property(lambda self: self._get("latest_apply_d"))
    segments = property(lambda self: self._get("segments"))
    applies = property(lambda self: self._get("applies"))
    resolutions = property(lambda self: self._get("resolutions"))
    requests = property(lambda self: self._get("requests"))

    def __repr__(self):
        v = self._view
        return "EffectiveView(head_seq=%d, effective=%d, segments=%d, applies=%d, resolutions=%d)" % (
            v["head_seq"], len(v["effective_seqs"]), len(v["segments"]), len(v["applies"]), len(v["resolutions"]))


class HistoryLedger(_Frozen):
    """The final six-column ledger handed to the core for one check_d, with what was excluded and supplemented.
    Never printed with its rows."""

    __slots__ = ()

    @classmethod
    def _make(cls, rows, excluded, supplemented, ledger_digest, effective_digest, history_digest, check_d):
        return cls._wrap({"rows": rows, "excluded_fingerprints": sorted(excluded), "supplemented": supplemented,
                          "ledger_digest": ledger_digest, "effective_digest": effective_digest,
                          "history_digest": history_digest, "check_d": check_d}, _history_error)

    @property
    def rows(self):
        return copy.deepcopy(self._view["rows"])

    def raw_observations(self):
        """Fresh six-column dicts, the only ledger prepare_day is given."""
        return copy.deepcopy(self._view["rows"])

    excluded_fingerprints = property(lambda self: list(self._view["excluded_fingerprints"]))
    supplemented = property(lambda self: copy.deepcopy(self._view["supplemented"]))
    ledger_digest = property(lambda self: self._view["ledger_digest"])
    effective_digest = property(lambda self: self._view["effective_digest"])
    history_digest = property(lambda self: self._view["history_digest"])
    check_d = property(lambda self: self._view["check_d"])

    def __repr__(self):
        v = self._view
        return "HistoryLedger(rows=%d, excluded=%d, supplemented=%d)" % (
            len(v["rows"]), len(v["excluded_fingerprints"]), len(v["supplemented"]))


def digest_of(body):
    return sha256_text(canonical_json(body))
