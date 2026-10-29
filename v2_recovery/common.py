"""Fixed names, command normalization, request hash and record hash shared by validation and planning."""
import re

from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_core.observations import is_valid_record_id
from v2_core.sessions import parse_aware_datetime
from v2_persistence.codec import canonical_json, sha256_text, utc_text

from .errors import resolution_invalid

KIND_ACK = "ACK"
KIND_DECLARE = "DECLARE_MISSING"
V_ADDED, V_CHANGED, V_ROW_REMOVED, V_LATE = "ADDED", "CHANGED", "ROW_REMOVED", "LATE"
VARIANTS = (V_ADDED, V_CHANGED, V_ROW_REMOVED, V_LATE)

REASON_ACK = "ACKNOWLEDGE_LEDGER_CHANGE"
REASON_DECLARE = "MARK_SESSION_MISSING"
REASON_BATCH = "RESOLUTION_BATCH"

COMMAND_KEYS = frozenset(["kind", "variant", "d", "record_fingerprints", "applied_ref", "missing_ref"])
APPLIED_REF_KEYS = frozenset(["seq", "event_hash", "fingerprint"])
APPLY_MISSING_KEYS = frozenset(["kind", "seq", "event_hash"])
DECLARE_MISSING_KEYS = frozenset(["kind", "resolution_seq", "resolution_hash"])
BASIS_KEYS = frozenset(["request_id", "commands", "check_d", "reason_code", "requested_at"])
RECORD_KEYS = frozenset([
    "resolution_seq", "parent_resolution_hash", "resolution_hash", "request_id", "request_hash", "request_basis",
    "command_index", "command_count", "kind", "variant", "d", "source_head_seq", "source_head_hash", "state_after",
    "record_fingerprints", "applied_ref", "missing_ref", "session_context", "frontier_before", "ledger_digest",
    "reason_code", "requested_at"])

_HEX64 = re.compile(r"[0-9a-f]{64}")


def is_int(x):
    return type(x) is int


def is_hex64(x):
    return isinstance(x, str) and _HEX64.fullmatch(x) is not None


def is_date(x):
    try:
        parse_iso_date(x, "date")
    except InputError:
        return False
    return True


def same(a, b):
    return canonical_json(a) == canonical_json(b)


def requested_text(value):
    """The injected aware datetime as fixed UTC text. A clock is never read here."""
    from datetime import datetime
    if not isinstance(value, datetime):
        raise InputError("datetime_invalid", "requested_at")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InputError("datetime_missing_timezone", "requested_at")
    return utc_text(value, "requested_at")


def is_requested_text(text):
    if not isinstance(text, str):
        return False
    try:
        dt = parse_aware_datetime(text, "requested_at")
    except InputError:
        return False
    return utc_text(dt, "requested_at") == text


def normalize_command(cmd, field):
    """Shape and types only. Returns a fresh canonical dict (fingerprints sorted). Never echoes a raw value."""
    def bad():
        return resolution_invalid(field, "command_shape")

    if not isinstance(cmd, dict) or set(cmd) != COMMAND_KEYS:
        raise bad()
    kind, variant, d = cmd["kind"], cmd["variant"], cmd["d"]
    if kind == KIND_ACK:
        if variant not in VARIANTS:
            raise bad()
    elif kind == KIND_DECLARE:
        if variant is not None:
            raise bad()
    else:
        raise bad()
    if not is_date(d):
        raise bad()
    fps = cmd["record_fingerprints"]
    if not isinstance(fps, (list, tuple)) or not all(is_hex64(x) for x in fps) or len(set(fps)) != len(fps):
        raise bad()
    applied, missing = cmd["applied_ref"], cmd["missing_ref"]
    if applied is not None:
        if (not isinstance(applied, dict) or set(applied) != APPLIED_REF_KEYS or not is_int(applied["seq"])
                or applied["seq"] < 1 or not is_hex64(applied["event_hash"]) or not is_hex64(applied["fingerprint"])):
            raise bad()
        applied = {"seq": applied["seq"], "event_hash": applied["event_hash"], "fingerprint": applied["fingerprint"]}
    if missing is not None:
        if not isinstance(missing, dict):
            raise bad()
        if missing.get("kind") == "APPLY" and set(missing) == APPLY_MISSING_KEYS:
            if not is_int(missing["seq"]) or missing["seq"] < 1 or not is_hex64(missing["event_hash"]):
                raise bad()
            missing = {"kind": "APPLY", "seq": missing["seq"], "event_hash": missing["event_hash"]}
        elif missing.get("kind") == KIND_DECLARE and set(missing) == DECLARE_MISSING_KEYS:
            if (not is_int(missing["resolution_seq"]) or missing["resolution_seq"] < 1
                    or not is_hex64(missing["resolution_hash"])):
                raise bad()
            missing = {"kind": KIND_DECLARE, "resolution_seq": missing["resolution_seq"],
                       "resolution_hash": missing["resolution_hash"]}
        else:
            raise bad()
    if kind == KIND_DECLARE and (applied is not None or missing is not None):
        raise bad()
    return {"kind": kind, "variant": variant, "d": d, "record_fingerprints": sorted(fps),
            "applied_ref": applied, "missing_ref": missing}


def reason_for_commands(commands):
    kinds = {c["kind"] for c in commands}
    if kinds == {KIND_ACK}:
        return (REASON_ACK, REASON_BATCH)
    if kinds == {KIND_DECLARE}:
        return (REASON_DECLARE, REASON_BATCH)
    return (REASON_BATCH,)


def record_reason(kind):
    return REASON_ACK if kind == KIND_ACK else REASON_DECLARE


def request_hash_of(request_id, commands, check_d, reason_code):
    """requested_at is deliberately not part of it: a resubmission with only a newer time is the same request."""
    return sha256_text(canonical_json({"request_id": request_id, "commands": commands, "check_d": check_d,
                                       "reason_code": reason_code}))


def basis_request_hash(basis):
    return request_hash_of(basis["request_id"], basis["commands"], basis["check_d"], basis["reason_code"])


def record_hash_of(record):
    return sha256_text(canonical_json({k: v for k, v in record.items() if k != "resolution_hash"}))


def valid_request_id(x):
    return is_valid_record_id(x)
