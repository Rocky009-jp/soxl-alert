"""diagnose_history_bytes: bytes -> HistoryDiagnosis, in the four stages of the design (utf8, json, schema, validate),
then the longest verified prefix.

Strict reading only: UTF-8 (BOM not removed), the unchanged decode_history (duplicate keys, NaN/Infinity, depth and huge
integers refused). A broken JSON text is never parsed leniently and no record is rescued from it. The checkers are the
unchanged validate_history (schema 2) and validate_snapshot (schema 1). A content problem is a value, never an
exception; only a wrong argument type raises.
"""
import hashlib

from v2_history import History, decode_history, validate_history
from v2_history.common import is_int
from v2_history.values import history_dict
from v2_persistence.codec import CORE_SHA, Snapshot, canonical_json, encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.events import snapshot_dict
from v2_persistence.recompute import validate_snapshot

from .describe import claimed_of, discarded_of, verified_v1, verified_v2
from .failure import CAUGHT, STAGE_JSON, STAGE_SCHEMA, STAGE_UTF8, STAGE_VALIDATE, failure, from_exception
from .values import NO_VALID_PREFIX, OPERATION, PREFIX_ONLY, UNREADABLE, VALID, HistoryDiagnosis


def diagnose_history_bytes(data):
    """Diagnose the raw bytes of a stored history. `data` must be exactly `bytes` (no str, bytearray, memoryview,
    None or subclass): anything else raises PersistenceError("diagnosis_invalid", "data", rule="type"). Every
    problem with the content is reported in the returned HistoryDiagnosis. Nothing is written or repaired."""
    if type(data) is not bytes:
        raise PersistenceError("diagnosis_invalid", "data", rule="type")
    return HistoryDiagnosis(_diagnose(data))


def _report(data, status, **fields):
    out = {"operation": OPERATION, "status": status, "raw_sha256": hashlib.sha256(data).hexdigest(),
           "raw_size": len(data), "schema_version": None, "canonical_text": None, "failure": None, "claimed": None,
           "verified": None, "discarded": None}
    out.update(fields)
    return out


def _diagnose(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _report(data, UNREADABLE, failure=failure(STAGE_UTF8, "unreadable", "data", "utf8"))
    try:
        history = decode_history(text)
    except CAUGHT as exc:
        return _report(data, UNREADABLE, failure=from_exception(STAGE_JSON, exc, 2))
    top = history.to_dict()
    canonical = canonical_json(top).encode("utf-8") == data
    if not isinstance(top, dict):
        return _report(data, UNREADABLE, canonical_text=canonical,
                       failure=failure(STAGE_SCHEMA, "history_invalid", "history", "shape"))
    claimed = claimed_of(top)
    version = top.get("schema_version")
    if not is_int(version) or version not in (1, 2):
        return _report(data, UNREADABLE, canonical_text=canonical, claimed=claimed,
                       failure=failure(STAGE_SCHEMA, "unsupported_schema", "schema_version", None))
    if top.get("core_sha") != CORE_SHA:
        return _report(data, UNREADABLE, canonical_text=canonical, claimed=claimed,
                       failure=failure(STAGE_SCHEMA, "unsupported_schema", "core_sha", None))
    common = {"schema_version": version, "canonical_text": canonical, "claimed": claimed}
    try:
        verified = _check_whole(top, history, version)
    except CAUGHT as exc:
        first_error = from_exception(STAGE_VALIDATE, exc, version)
    else:
        return _report(data, VALID, verified=verified, **common)
    events = top.get("events")
    if isinstance(events, list) and events:
        found = _longest_prefix(events, version)
        if found is not None:
            k, verified = found
            return _report(data, PREFIX_ONLY, failure=first_error, verified=verified,
                           discarded=discarded_of(events, k, version), **common)
    return _report(data, NO_VALID_PREFIX, failure=first_error, discarded=discarded_of(events, 0, version), **common)


def _check_whole(top, history, version):
    """The whole document through the unchanged checker of its own version."""
    if version == 2:
        return verified_v2(validate_history(history))
    snapshot = Snapshot.from_dict(top)
    return verified_v1(validate_snapshot(snapshot), len(top["events"]), encode_snapshot(snapshot))


def _longest_prefix(events, version):
    """(k, verified) for the largest k, tried from len(events) down to 1, whose first k records pass the unchanged
    checker under a header recomputed from record k-1. Prefix validity is not monotonic in k (a batch cut in the
    middle fails while a longer prefix passes), so there is no bisection and no search from below. A problem in one
    k only means that k does not pass."""
    for k in range(len(events), 0, -1):
        try:
            if version == 2:
                verified = verified_v2(validate_history(History.from_dict(history_dict(events[:k]))))
            else:
                snapshot = Snapshot.from_dict(snapshot_dict(events[:k]))
                verified = verified_v1(validate_snapshot(snapshot), k, encode_snapshot(snapshot))
        except CAUGHT:
            continue
        return k, verified
    return None
