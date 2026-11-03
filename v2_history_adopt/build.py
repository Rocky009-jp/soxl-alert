"""The adoption record and the plan basis, built from the raw bytes and their diagnosis (design 5.2 steps 5-12).

The diagnosis is made by the caller (once) and passed in; this module never reads the bytes' hash itself. Every value
of the basis is taken from the diagnosis or from the checked candidate; no market value is written anew here."""
import copy

from v2_core.errors import CoreError
from v2_history import History, RECOVERY_PREFIX_ADOPTION, SCHEMA_MIGRATION, decode_history, validate_history
from v2_history.common import basis_request_hash
from v2_history.values import history_dict
from v2_history_diagnose import PREFIX_ONLY
from v2_history_ops.errors import history_request_conflict
from v2_persistence.codec import compute_event_hash

from .errors import adoption_invalid, candidate_failure
from .values import OPERATION, READY, REASON


def _leaves_a_migration(events, discarded_items):
    """Design 5.2 step 8: a readable SCHEMA_MIGRATION on the discarded side, or any discarded element that is a dict
    with an `origin` that is not null (a migrated record only a migration explains)."""
    if any(item["kind"] == SCHEMA_MIGRATION for item in discarded_items):
        return True
    return any(isinstance(ev, dict) and ev.get("origin") is not None for ev in events)


def _physical_ids(events):
    return {ev.get("request_id") for ev in events if isinstance(ev, dict) and ev.get("request_id") is not None}


def build_adoption(data, diagnosis, adopt_count, request_id, requested_at):
    """Steps 5-12 for one diagnosis of `data`. `requested_at` is already the fixed UTC text. Returns (basis, candidate)."""
    d = diagnosis.to_dict()
    if d["status"] != PREFIX_ONLY:                                                                      # 5
        raise adoption_invalid("data", "not_adoptable")
    if d["schema_version"] != 2:                                                                        # 6
        raise adoption_invalid("data", "schema_1")
    verified = d["verified"]
    if adopt_count != verified["count"]:                                                                # 7
        raise adoption_invalid("adopt_count", "count_mismatch")
    events = decode_history(data.decode("utf-8")).to_dict()["events"]
    k = adopt_count
    discarded = d["discarded"]
    if verified["migrated"] is False and _leaves_a_migration(events[k:], discarded["items"]):           # 8
        raise adoption_invalid("data", "migration_discarded")
    prefix_events = events[:k]
    try:                                                                                                # 9
        prefix_check = validate_history(History.from_dict(history_dict(prefix_events)))
    except CoreError:
        raise candidate_failure() from None
    if (prefix_check.head_seq != verified["head_seq"] or prefix_check.head_hash != verified["head_hash"]
            or prefix_check.state_digest != verified["state_digest"]
            or prefix_check.history_digest != verified["document_digest"]):
        raise candidate_failure()
    if request_id in _physical_ids(prefix_events) or request_id in {i["request_id"] for i in discarded["items"]}:
        raise history_request_conflict()                                                                # 10
    last = prefix_events[-1]                                                                            # 11
    claimed = d["claimed"]
    evidence = {"raw_sha256": d["raw_sha256"], "raw_size": d["raw_size"], "claimed_schema_version": 2,
                "claimed_head_seq": claimed["head_seq"], "claimed_head_hash": claimed["head_hash"],
                "discarded_from_seq": k}
    request_basis = {"request_id": request_id, "evidence": copy.deepcopy(evidence), "reason_code": REASON,
                     "requested_at": requested_at}
    record = {"kind": RECOVERY_PREFIX_ADOPTION, "seq": k, "parent_seq": k - 1, "parent_hash": last["event_hash"],
              "evidence": evidence, "request_id": request_id, "request_hash": basis_request_hash(request_basis),
              "request_basis": request_basis, "reason_code": REASON, "requested_at": requested_at,
              "state_after": copy.deepcopy(last["state_after"])}
    record["event_hash"] = compute_event_hash(record)
    candidate_dict = history_dict(prefix_events + [record])
    try:
        candidate = History.from_dict(candidate_dict)
        candidate_check = validate_history(candidate)
    except CoreError:
        raise candidate_failure() from None
    if candidate_check.head_seq != k or candidate_check.state_digest != prefix_check.state_digest:
        raise candidate_failure()
    basis = {"operation": OPERATION, "status": READY, "raw_sha256": d["raw_sha256"], "raw_size": d["raw_size"],
             "diagnosis_digest": diagnosis.digest, "adopt_count": k, "discarded": copy.deepcopy(discarded),
             "prefix_head_seq": verified["head_seq"], "prefix_head_hash": verified["head_hash"],
             "prefix_state_digest": verified["state_digest"], "prefix_document_digest": verified["document_digest"],
             "request_id": request_id, "request_hash": record["request_hash"], "reason_code": REASON,
             "requested_at": requested_at, "candidate_history": candidate.to_dict(),
             "candidate_digest": candidate.digest, "candidate_head_seq": candidate_check.head_seq,
             "candidate_head_hash": candidate_check.head_hash, "candidate_state_digest": candidate_check.state_digest,
             "candidate_record": copy.deepcopy(record)}
    return basis, candidate

