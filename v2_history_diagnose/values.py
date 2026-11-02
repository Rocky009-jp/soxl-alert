"""The four status names and the immutable HistoryDiagnosis value.

A HistoryDiagnosis keeps only its canonical JSON text and a private parsed view that is never handed out. It holds no
raw bytes, no decoded text and no History. Every accessor that returns structured data returns a fresh copy.
"""
import copy

from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError

OPERATION = "soxl-v2-history-diagnosis/1"
VALID = "VALID"
PREFIX_ONLY = "PREFIX_ONLY"
NO_VALID_PREFIX = "NO_VALID_PREFIX"
UNREADABLE = "UNREADABLE"
STATUSES = (VALID, PREFIX_ONLY, NO_VALID_PREFIX, UNREADABLE)

KEYS = frozenset(["operation", "status", "raw_sha256", "raw_size", "schema_version", "canonical_text", "failure",
                  "claimed", "verified", "discarded"])


def _bad(rule):
    return PersistenceError("diagnosis_invalid", "diagnosis", rule=rule)


class HistoryDiagnosis:
    """Immutable outcome of diagnose_history_bytes: fixed keys, identifiers, counts, dates and digests only.

    Direct construction is for trusted internal input only (the ten keys of to_dict, JSON-compatible); there is no
    from_dict. A diagnosis is a report, not a repair: PREFIX_ONLY says only that the first `count` records pass the
    current checker, never that the file is recovered, adopted or canonical."""

    __slots__ = ("_text", "_view")

    def __init__(self, fields):
        if type(fields) is not dict or set(fields) != KEYS:
            raise _bad("shape")
        if fields["operation"] != OPERATION or fields["status"] not in STATUSES:
            raise _bad("shape")
        try:
            text = canonical_json(fields)
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise _bad("json") from None
        object.__setattr__(self, "_text", text)
        object.__setattr__(self, "_view", copy.deepcopy(fields))

    def __setattr__(self, name, value):
        raise AttributeError("HistoryDiagnosis is immutable")

    def __delattr__(self, name):
        raise AttributeError("HistoryDiagnosis is immutable")

    def __eq__(self, other):
        return isinstance(other, HistoryDiagnosis) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    # --- read access: always fresh copies -------------------------------------------------------------------
    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def operation(self):
        return copy.deepcopy(self._view["operation"])

    @property
    def status(self):
        return copy.deepcopy(self._view["status"])

    @property
    def raw_sha256(self):
        return copy.deepcopy(self._view["raw_sha256"])

    @property
    def raw_size(self):
        return copy.deepcopy(self._view["raw_size"])

    @property
    def schema_version(self):
        return copy.deepcopy(self._view["schema_version"])

    @property
    def canonical_text(self):
        return copy.deepcopy(self._view["canonical_text"])

    @property
    def failure(self):
        return copy.deepcopy(self._view["failure"])

    @property
    def claimed(self):
        return copy.deepcopy(self._view["claimed"])

    @property
    def verified(self):
        return copy.deepcopy(self._view["verified"])

    @property
    def discarded(self):
        return copy.deepcopy(self._view["discarded"])

    @property
    def digest(self):
        """SHA-256 of the canonical to_dict. The same bytes always give the same digest."""
        return sha256_text(self._text)

    # --- display: fixed words, counts, seqs, dates and short digests only -----------------------------------
    def summary(self):
        v = self._view
        parts = ["status=%s" % v["status"], "raw_size=%d" % v["raw_size"], "raw_sha256=%s" % v["raw_sha256"][:12]]
        if v["schema_version"] is not None:
            parts.append("schema_version=%d" % v["schema_version"])
        if v["failure"] is not None:
            f = v["failure"]
            parts.append("failure=%s/%s/%s/%s" % (f["stage"], f["code"], f["field"], f["rule"]))
        if v["verified"] is not None:
            parts.append("verified_count=%d" % v["verified"]["count"])
            parts.append("head_seq=%d" % v["verified"]["head_seq"])
        d = v["discarded"]
        if d is not None:
            parts.append("discarded_from=%d" % d["from_index"])
            parts.append("discarded_count=%d" % d["count"])
            kinds = {}
            dates = []
            for item in d["items"]:
                kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
                if item["d"] is not None:
                    dates.append(item["d"])
            if kinds:
                parts.append("discarded_kinds=" + ",".join("%s:%d" % (k, kinds[k]) for k in sorted(kinds)))
            if dates:
                parts.append("first_d=%s" % dates[0])
                parts.append("last_d=%s" % dates[-1])
        return "HistoryDiagnosis " + " ".join(parts)

    def __repr__(self):
        v = self._view
        return "HistoryDiagnosis(status=%s, raw_size=%d, raw_sha256=%s)" % (v["status"], v["raw_size"],
                                                                             v["raw_sha256"][:12])
