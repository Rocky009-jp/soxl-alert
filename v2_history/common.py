"""Small shared predicates. Nothing here reads a clock, a file or the environment."""
import re

from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_persistence.codec import canonical_json, sha256_text

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


def basis_request_hash(basis):
    """SHA-256 of the request basis without requested_at (a resubmission with only a newer time is the same request).

    For ACK / DECLARE_MISSING this is the value v2_recovery.common.request_hash_of gives for the same request."""
    return sha256_text(canonical_json({k: v for k, v in basis.items() if k != "requested_at"}))
