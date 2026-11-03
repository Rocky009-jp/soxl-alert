"""confirm_prefix_adoption: re-check everything against a plan and return the candidate History, in memory only.

Order (design 5.5): the plan's form, hash and candidate -> the data's type -> the original raw bytes are diagnosed and the
whole plan is rebuilt and compared (CONFIRMED_IN_MEMORY), or the bytes are the candidate's own normalized text
(NO_CHANGE), or they are something else (history_plan_stale). A plan is trusted for nothing it states about itself."""
from v2_core.errors import CoreError
from v2_history import KINDS, History, RECOVERY_PREFIX_ADOPTION, encode_history, validate_history
from v2_history.common import is_date, is_hex64, is_int, same
from v2_history.values import history_dict
from v2_history_diagnose import diagnose_history_bytes
from v2_history_ops.errors import history_plan_mismatch, history_plan_stale
from v2_persistence.codec import canonical_json, sha256_text
from v2_recovery.common import is_requested_text, valid_request_id

from .build import build_adoption
from .errors import adoption_invalid
from .values import (BASIS_KEYS, CONFIRMED_IN_MEMORY, NO_CHANGE, OPERATION, READY, REASON, AdoptionConfirmResult,
                     AdoptionPlan)

_HASH_KEYS = ("raw_sha256", "diagnosis_digest", "prefix_head_hash", "prefix_state_digest", "prefix_document_digest",
              "request_hash", "candidate_digest", "candidate_head_hash", "candidate_state_digest")


def _form_ok(basis):
    """The shapes of the plan's own values (design 5.5 step 1), before anything is rebuilt. The discarded part is checked in
    the form the diagnosis gives (design 5.4: the fixed keys, strict integers, the start at adopt_count, as many items as
    the count says, each with its position, a kind of the fixed list or "?", a strict integer or None, a real day or None
    and a request id of the fixed form or None). Only what the plan itself proves: its content is not proved here, and a
    declared seq may be any integer, even a negative one."""

    def item_ok(item, index):
        return (isinstance(item, dict) and set(item) == {"index", "kind", "seq", "d", "request_id"}
                and is_int(item["index"]) and item["index"] == index and (item["kind"] == "?" or item["kind"] in KINDS)
                and (item["seq"] is None or is_int(item["seq"])) and (item["d"] is None or is_date(item["d"]))
                and (item["request_id"] is None or valid_request_id(item["request_id"])))

    def discarded_ok(part):
        if not isinstance(part, dict) or set(part) != {"from_index", "count", "items"}:
            return False
        start, count, items = part["from_index"], part["count"], part["items"]
        return (is_int(start) and start == basis["adopt_count"] and is_int(count) and count >= 0
                and isinstance(items, list) and len(items) == count
                and all(item_ok(item, start + at) for at, item in enumerate(items)))

    return (basis["operation"] == OPERATION and basis["status"] == READY and basis["reason_code"] == REASON
            and valid_request_id(basis["request_id"]) and is_requested_text(basis["requested_at"])
            and all(is_hex64(basis[k]) for k in _HASH_KEYS)
            and is_int(basis["raw_size"]) and basis["raw_size"] >= 1
            and is_int(basis["adopt_count"]) and basis["adopt_count"] >= 1
            and is_int(basis["prefix_head_seq"]) and basis["prefix_head_seq"] >= 0
            and is_int(basis["candidate_head_seq"]) and basis["candidate_head_seq"] >= 0
            and discarded_ok(basis["discarded"]) and isinstance(basis["candidate_history"], dict)
            and isinstance(basis["candidate_record"], dict))


def _candidate_of(basis):
    """The plan's candidate as a checked History, or a refusal: the plan is never trusted for it."""
    try:
        candidate = History.from_dict(basis["candidate_history"])
        check = validate_history(candidate)
        events = candidate.events
        record = basis["candidate_record"]
        k = basis["adopt_count"]
        prefix_text = canonical_json(history_dict(events[:-1])) if len(events) > 1 else None
        if (candidate.digest != basis["candidate_digest"] or check.head_seq != basis["candidate_head_seq"]
                or check.head_hash != basis["candidate_head_hash"]
                or check.state_digest != basis["candidate_state_digest"]
                or len(events) != k + 1 or not same(events[-1], record) or record["kind"] != RECOVERY_PREFIX_ADOPTION
                or prefix_text is None or sha256_text(prefix_text) != basis["prefix_document_digest"]
                or record["request_id"] != basis["request_id"] or record["request_hash"] != basis["request_hash"]
                or record["reason_code"] != basis["reason_code"] or record["requested_at"] != basis["requested_at"]
                or record["evidence"]["raw_sha256"] != basis["raw_sha256"]
                or record["evidence"]["raw_size"] != basis["raw_size"]
                or events[-2]["seq"] != basis["prefix_head_seq"] or events[-2]["event_hash"] != basis["prefix_head_hash"]
                or basis["prefix_state_digest"] != basis["candidate_state_digest"]):
            raise history_plan_mismatch()
    except (CoreError, KeyError, TypeError, IndexError):
        raise history_plan_mismatch() from None
    return candidate


def _plan_basis(plan, confirmed_plan_hash):
    """Steps 1-2: the plan's own form and hash and its internally consistent candidate. Nothing here looks at bytes."""
    if not isinstance(plan, AdoptionPlan) or not is_hex64(confirmed_plan_hash):
        raise history_plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or set(basis) != BASIS_KEYS
            or view["plan_hash"] != sha256_text(canonical_json(basis)) or confirmed_plan_hash != view["plan_hash"]
            or not _form_ok(basis)):
        raise history_plan_mismatch()
    return basis, _candidate_of(basis)


def confirm_prefix_adoption(plan, confirmed_plan_hash, data):
    """Re-check everything against the plan. Returns CONFIRMED_IN_MEMORY with the candidate History when `data` are the
    raw bytes the plan was made from, or NO_CHANGE with the candidate when `data` already is the plan's candidate (no
    second adoption record is made). Nothing is stored or applied."""
    basis, candidate = _plan_basis(plan, confirmed_plan_hash)                                           # 1, 2
    if type(data) is not bytes:                                                                         # 3
        raise adoption_invalid("data", "type")
    diagnosis = diagnose_history_bytes(data)
    if diagnosis.raw_sha256 == basis["raw_sha256"] and diagnosis.raw_size == basis["raw_size"]:         # 4
        try:
            rebuilt, rebuilt_candidate = build_adoption(data, diagnosis, basis["adopt_count"], basis["request_id"],
                                                        basis["requested_at"])
        except CoreError:
            raise history_plan_mismatch() from None
        if not same(rebuilt, basis) or rebuilt_candidate != candidate:
            raise history_plan_mismatch()
        return AdoptionConfirmResult(CONFIRMED_IN_MEMORY, rebuilt_candidate, plan.plan_hash)
    if encode_history(candidate).encode("utf-8") == data:                                               # 5
        return AdoptionConfirmResult(NO_CHANGE, candidate, plan.plan_hash)
    raise history_plan_stale()                                                                          # 6
