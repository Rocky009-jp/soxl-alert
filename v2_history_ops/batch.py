"""HistoryAppendBatch and check_append_batch: the records to add to one head, as a value, and its pure re-check.

A batch is made only by a day preparation (PREPARED) or by a confirmed resolution plan (CONFIRMED_IN_MEMORY). It is a
value in memory: nothing is locked, written, compared and swapped or published here; the I/O and the execution belong
to a later stage. committed is always False, and the batch is not an AppendPlan, so no existing store accepts it.
"""
import copy

from v2_history import History, validate_history
from v2_history.common import is_date, is_hex64, is_int
from v2_history.values import ACK, APPLY, DECLARE_MISSING, check_json, history_dict
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_recovery.common import valid_request_id

from .errors import batch_invalid, batch_stale
from .values import _Frozen, digest_of

DAILY = "DAILY"
RESOLUTION = "RESOLUTION"
OPERATION = "soxl-v2-history-append-batch/1"
_BODY_KEYS = frozenset([
    "operation", "source", "d", "request_id", "plan_hash", "expected_head_seq", "expected_head_hash",
    "expected_history_digest", "records", "candidate_head_seq", "candidate_head_hash", "candidate_digest",
    "candidate_state_digest"])


def _batch_error(rule):
    return batch_invalid(rule)


def _json_checked(data):
    """Depth, key and value types of a dict that came from outside. The history checker's rules, as batch refusals."""
    try:
        check_json(data)
    except PersistenceError as e:
        raise batch_invalid(e.rule if e.rule in ("json_depth", "json_number", "json_key", "json_type")
                            else "batch_shape") from None


class HistoryAppendBatch(_Frozen):
    """An immutable {body, batch_hash}. batch_hash is the SHA-256 of the canonical body; a record never carries it.

    Built by prepare_history_day / confirm_history_resolution_plan or by from_dict (for a message or a test). A value
    made by from_dict is unverified until check_append_batch has checked it, so nothing it carries is printed as it is.
    """

    __slots__ = ()

    @classmethod
    def _make(cls, body):
        return cls._wrap({"body": body, "batch_hash": digest_of(body)}, _batch_error)

    @classmethod
    def from_dict(cls, data):
        """Copy a JSON-compatible dict. Only the form and the JSON depth and types are checked here."""
        if not isinstance(data, dict) or set(data) != {"body", "batch_hash"}:
            raise batch_invalid("batch_shape")
        _json_checked(data)                   # depth and types first: only then is copying the input safe
        return cls._wrap(copy.deepcopy(data), _batch_error)

    @property
    def body(self):
        return copy.deepcopy(self._view["body"])

    @property
    def batch_hash(self):
        return self._view["batch_hash"]

    @property
    def committed(self):
        return False

    def _display(self):
        """The few values that may be shown, each re-checked against its own form; None when anything is off."""
        try:
            b, h = self._view["body"], self._view["batch_hash"]
            if (b["source"] not in (DAILY, RESOLUTION) or not is_hex64(h) or not isinstance(b["records"], list)
                    or not is_int(b["expected_head_seq"]) or not is_int(b["candidate_head_seq"])
                    or not is_hex64(b["candidate_digest"])):
                return None
            d = b["d"] if b["d"] is not None and is_date(b["d"]) else None
            rid = b["request_id"] if b["request_id"] is not None and valid_request_id(b["request_id"]) else None
            return b["source"], d, rid, len(b["records"]), b["expected_head_seq"], b["candidate_head_seq"], h
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: source, day, request id, counts, head numbers and the batch hash."""
        shown = self._display()
        if shown is None:
            raise batch_invalid("batch_shape")
        source, d, rid, n, expected, candidate, h = shown
        return {"source": source, "d": d, "request_id": rid, "records": n, "expected_head_seq": expected,
                "candidate_head_seq": candidate, "committed": False, "batch_hash": h}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "HistoryAppendBatch(?)"
        return "HistoryAppendBatch(source=%s, records=%d, batch_hash=%s)" % (shown[0], shown[3], shown[6][:12])


def append_records(history, records):
    """The candidate History: the checked history and records added after its head."""
    events = history.events
    events.extend(copy.deepcopy(list(records)))
    return History.from_dict(history_dict(events))


def make_batch(history, check, records, candidate, candidate_check, source, d, request_id, plan_hash):
    """The batch for records that were just built from `history` (already checked as `check`) and checked as
    `candidate` (`candidate_check`). Callers pass only a prepared day or a confirmed plan."""
    return HistoryAppendBatch._make({
        "operation": OPERATION, "source": source, "d": d, "request_id": request_id, "plan_hash": plan_hash,
        "expected_head_seq": check.head_seq, "expected_head_hash": check.head_hash,
        "expected_history_digest": check.history_digest, "records": copy.deepcopy(list(records)),
        "candidate_head_seq": candidate_check.head_seq, "candidate_head_hash": candidate_check.head_hash,
        "candidate_digest": candidate_check.history_digest, "candidate_state_digest": candidate_check.state_digest})


def _batch_body(batch):
    """Step 1: type, form, operation, source, hash and the types of the integer fields."""
    if not isinstance(batch, HistoryAppendBatch):
        raise batch_invalid("type")
    view = batch.to_dict()
    body = view["body"]
    if not isinstance(body, dict) or set(body) != _BODY_KEYS:
        raise batch_invalid("batch_shape")
    if body["operation"] != OPERATION or body["source"] not in (DAILY, RESOLUTION):
        raise batch_invalid("batch_shape")
    if not is_hex64(view["batch_hash"]) or view["batch_hash"] != digest_of(body):
        raise batch_invalid("batch_hash")
    if not is_int(body["expected_head_seq"]) or not is_int(body["candidate_head_seq"]) or body["expected_head_seq"] < 0:
        raise batch_invalid("type")
    for key in ("expected_head_hash", "expected_history_digest", "candidate_head_hash", "candidate_digest",
                "candidate_state_digest"):
        if not is_hex64(body[key]):
            raise batch_invalid("batch_shape")
    if not isinstance(body["records"], list):
        raise batch_invalid("batch_shape")
    return body


def _check_records(body):
    """Step 4: at least one record, seqs from the expected head + 1, and the shape that the source allows."""
    records = body["records"]
    if not records:
        raise batch_invalid("records")
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise batch_invalid("records")
        if not is_int(rec.get("seq")) or rec["seq"] != body["expected_head_seq"] + 1 + i:
            raise batch_invalid("seq")
    if body["source"] == DAILY:
        if (len(records) != 1 or records[0].get("kind") != APPLY or body["d"] is None
                or records[0].get("d") != body["d"] or body["request_id"] is not None
                or body["plan_hash"] is not None):
            raise batch_invalid("source")
        return
    if (body["d"] is not None or not valid_request_id(body["request_id"]) or not is_hex64(body["plan_hash"])):
        raise batch_invalid("source")
    for rec in records:
        if (rec.get("kind") not in (ACK, DECLARE_MISSING) or rec.get("request_id") != body["request_id"]
                or not is_int(rec.get("command_count")) or rec["command_count"] != len(records)):
            raise batch_invalid("source")


def check_append_batch(history, batch):
    """Check a batch against a history and return the candidate History (in memory; committed has no meaning here).

    Order: the batch itself -> the history -> the head -> the records -> the candidate's digests -> the candidate."""
    body = _batch_body(batch)                                              # 1
    check = validate_history(history)                                      # 2 existing errors stay
    if (check.history_digest != body["expected_history_digest"] or check.head_seq != body["expected_head_seq"]
            or check.head_hash != body["expected_head_hash"]):             # 3 includes a history that already
        raise batch_stale()                                                #   holds this batch: S3-C decides that
    _check_records(body)                                                   # 4
    try:
        candidate = append_records(history, body["records"])               # 5
    except (KeyError, TypeError, IndexError):
        raise batch_invalid("records") from None
    if (candidate.digest != body["candidate_digest"] or candidate.head_seq != body["candidate_head_seq"]
            or candidate.head_hash != body["candidate_head_hash"]):
        raise batch_invalid("candidate_digest")
    if sha256_text(canonical_json(candidate.current_state)) != body["candidate_state_digest"]:
        raise batch_invalid("candidate_digest")
    validate_history(candidate)                                            # 6
    return candidate
