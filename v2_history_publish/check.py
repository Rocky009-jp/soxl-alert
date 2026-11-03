"""check_publication (compare and swap, pure) and reconcile_publication (read-only, after an uncertain outcome).

Neither re-confirms the plan: they check that the value is one that a builder made (form, integer ranges, hash) and
that the current bytes are what it expects. Only the builders confirm. The form check is shared by both, so a value
that one refuses the other refuses in the same way."""
import copy

from v2_core.errors import CoreError
from v2_history import History, validate_history
from v2_history.common import is_date, is_hex64, is_int
from v2_history.values import history_dict
from v2_history_ops.values import digest_of
from v2_persistence.codec import canonical_json, sha256_text
from v2_recovery.common import valid_request_id

from .errors import publication_invalid, publication_stale
from .read import prefix_digest, raw_identity, read_history_bytes
from .values import (APPEND, APPEND_EXPECTED_KEYS, BODY_KEYS, CONFLICT, CREATE, DAILY, MIGRATION, MODE_OF,
                     NOT_PUBLISHED, OPERATION, PUBLISHED, PUBLISHED_THEN_EXTENDED, RAW_KEYS, REPLACE,
                     HistoryPublication, Reconciliation)

PLAN_SOURCES = frozenset(["RESOLUTION", "RESTART", "RESTORE", "MIGRATION", "ADOPTION"])


def _count(x):
    """An integer that is not negative (a bool is not one)."""
    return is_int(x) and x >= 0


def _raw_ok(v):
    return isinstance(v, dict) and set(v) == RAW_KEYS and is_hex64(v["raw_sha256"]) and _count(v["raw_size"])


def _body(publication):
    """The body of a publication whose type, form, integer ranges, mode for the source and hash are right. Raises
    publication_invalid otherwise. Nothing but the value is looked at."""
    if type(publication) is not HistoryPublication:
        raise publication_invalid("type")
    view = publication.to_dict()
    body = view.get("body")
    if not isinstance(body, dict) or set(body) != BODY_KEYS or body["operation"] != OPERATION:
        raise publication_invalid("shape")
    source = body["source"]
    if type(source) is not str or source not in MODE_OF or body["mode"] != MODE_OF[source]:
        raise publication_invalid("mode")
    if not is_hex64(view.get("publication_hash")) or view["publication_hash"] != digest_of(body):
        raise publication_invalid("publication_hash")
    for key in ("candidate_head_hash", "candidate_digest", "candidate_state_digest"):
        if not is_hex64(body[key]):
            raise publication_invalid("shape")
    if not _count(body["candidate_head_seq"]):
        raise publication_invalid("shape")
    if source == DAILY:
        if body["d"] is None or not is_date(body["d"]):
            raise publication_invalid("shape")
    elif body["d"] is not None:
        raise publication_invalid("shape")
    if source in PLAN_SOURCES:
        if not valid_request_id(body["request_id"]) or not is_hex64(body["plan_hash"]):
            raise publication_invalid("shape")
    elif body["request_id"] is not None or body["plan_hash"] is not None:
        raise publication_invalid("shape")
    mode = body["mode"]
    if mode == APPEND:
        e, records = body["expected"], body["records"]
        if (not isinstance(e, dict) or set(e) != APPEND_EXPECTED_KEYS or not _count(e["head_seq"])
                or not is_hex64(e["head_hash"]) or not is_hex64(e["history_digest"])
                or not isinstance(records, list) or not records
                or body["candidate_history"] is not None or body["source_v1"] is not None):
            raise publication_invalid("shape")
        if body["candidate_head_seq"] != e["head_seq"] + len(records):
            raise publication_invalid("shape")
    else:
        candidate = body["candidate_history"]
        if body["records"] is not None or not isinstance(candidate, dict):
            raise publication_invalid("shape")
        events = candidate.get("events")
        if not isinstance(events, list) or not events or body["candidate_head_seq"] != len(events) - 1:
            raise publication_invalid("shape")
        if mode == CREATE and body["expected"] is not None:
            raise publication_invalid("shape")
        if mode == REPLACE and not _raw_ok(body["expected"]):
            raise publication_invalid("shape")
        if source == MIGRATION:
            if not _raw_ok(body["source_v1"]):
                raise publication_invalid("shape")
        elif body["source_v1"] is not None:
            raise publication_invalid("shape")
    return body


def _arguments(body, current, source_v1, has_source_v1):
    """A misuse of the arguments, seen before the current bytes are compared (so that it is the same whatever the
    current bytes are)."""
    if current is not None and type(current) is not bytes:
        raise publication_invalid("current_type")
    if has_source_v1:
        if body["source"] != MIGRATION and source_v1 is not None:
            raise publication_invalid("source_v1")
        if source_v1 is not None and type(source_v1) is not bytes:
            raise publication_invalid("source_v1")


def _candidate(body, current_history):
    """The candidate History of the publication (APPEND: the current history plus the records), checked in full."""
    if body["mode"] == APPEND:
        records = copy.deepcopy(body["records"])
        first = body["expected"]["head_seq"] + 1
        for i, rec in enumerate(records):
            if not isinstance(rec, dict) or not is_int(rec.get("seq")) or rec["seq"] != first + i:
                raise publication_invalid("records")
        events = current_history.events + records
    else:
        events = None
    try:
        if events is not None:
            candidate = History.from_dict(history_dict(events))
        else:
            candidate = History.from_dict(body["candidate_history"])
    except (KeyError, TypeError, IndexError):
        raise publication_invalid("records") from None
    check = validate_history(candidate)
    if (check.history_digest != body["candidate_digest"] or check.head_seq != body["candidate_head_seq"]
            or check.head_hash != body["candidate_head_hash"]
            or sha256_text(canonical_json(candidate.current_state)) != body["candidate_state_digest"]):
        raise publication_invalid("candidate_digest")
    return candidate


def check_publication(current, publication, source_v1=None):
    """current: the bytes of history.json read under the lock, or None when it is absent. source_v1: for MIGRATION
    only, the bytes of the v1 snapshot.json read under the same lock. Returns the candidate History; raises
    publication_stale when the current bytes are not what the publication expects. Nothing is written.

    The order is fixed: the publication (form, integer ranges, hash), then the arguments, then the current bytes, then
    the candidate."""
    body = _body(publication)                                                             # 1 the value
    _arguments(body, current, source_v1, True)                                            # 1 the arguments
    mode = body["mode"]
    current_history = None
    if mode == APPEND:                                                                    # 2 the current bytes
        if current is None:
            raise publication_stale("absent")
        current_history, check = read_history_bytes(current)
        e = body["expected"]
        if (check.history_digest, check.head_seq, check.head_hash) != (e["history_digest"], e["head_seq"],
                                                                       e["head_hash"]):
            raise publication_stale("head")
    elif mode == CREATE:
        if current is not None:
            raise publication_stale("present")
        if body["source"] == MIGRATION:
            if source_v1 is None or raw_identity(source_v1) != body["source_v1"]:
                raise publication_stale("source_v1")
    else:
        if current is None or raw_identity(current) != body["expected"]:
            raise publication_stale("raw")
    return _candidate(body, current_history)                                              # 3 the candidate


def reconcile_publication(current, publication):
    """After an uncertain outcome: the bytes read again (None when history.json is absent) against the publication.
    PUBLISHED: the current history is the candidate. PUBLISHED_THEN_EXTENDED: the candidate is its physical prefix and
    records follow. NOT_PUBLISHED: the current bytes are still what the publication expects (the same publication may
    be tried again, after check_publication under the lock). CONFLICT: anything else, an unreadable file included.
    Read-only; says nothing about who wrote what. Only a wrong publication or a wrong argument raises."""
    body = _body(publication)
    _arguments(body, current, None, False)
    h = digest_of(body)
    mode = body["mode"]
    if current is None:
        return Reconciliation._of(NOT_PUBLISHED if mode == CREATE else CONFLICT, h)
    if mode == REPLACE and raw_identity(current) == body["expected"]:
        return Reconciliation._of(NOT_PUBLISHED, h)
    try:
        history, check = read_history_bytes(current)
    except CoreError:
        return Reconciliation._of(CONFLICT, h)
    if (check.history_digest, check.head_seq, check.head_hash) == (body["candidate_digest"],
                                                                   body["candidate_head_seq"],
                                                                   body["candidate_head_hash"]):
        return Reconciliation._of(PUBLISHED, h)
    events = history.events
    n = body["candidate_head_seq"] + 1
    if len(events) > n and prefix_digest(events, n) == body["candidate_digest"]:
        return Reconciliation._of(PUBLISHED_THEN_EXTENDED, h)
    if mode == APPEND:
        e = body["expected"]
        if (check.history_digest, check.head_seq, check.head_hash) == (e["history_digest"], e["head_seq"],
                                                                       e["head_hash"]):
            return Reconciliation._of(NOT_PUBLISHED, h)
    return Reconciliation._of(CONFLICT, h)
