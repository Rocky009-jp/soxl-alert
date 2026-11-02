"""RestorePlan and RestoreConfirmResult: immutable values of the restore operation.

A RestorePlan keeps only canonical JSON text plus a private parsed view that is never handed out; every accessor that
returns structured data returns a fresh copy. A plan built by from_dict is unverified until confirm_restore_plan checks
it, so nothing it carries is printed as it is: the few values shown are re-checked against their own form first.

RestoreConfirmResult may be built directly only from values that confirm_restore_plan has checked (a status, an
immutable History and a hash text). That is a trusted internal use; the only reader of outside messages is
RestorePlan.from_dict.
"""
import copy
import json

from v2_history.common import is_date, is_hex64, is_int
from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN,
                               SCHEMA_MIGRATION, check_json)
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_recovery.common import valid_request_id

from .errors import restore_invalid

READY = "READY"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
NO_CHANGE = "NO_CHANGE"
OPERATION = "soxl-v2-history-restore-plan/1"
REASON = "RESTORE_VERIFIED_RECORD"
REAPPLY, REPLAY, DROP, RETIRE = "REAPPLY", "REPLAY", "DROP", "RETIRE"
OPS = (REAPPLY, REPLAY, DROP, RETIRE)
RECORD_KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, SCHEMA_MIGRATION)
OP_KEYS = frozenset(["op", "from_seq"])
POINT_KEYS = frozenset(["seq", "event_hash"])
CHANGE_KEYS = frozenset(["op", "from_seq", "kind", "d", "to_seq", "same_as_superseded", "changed_fields"])
SERIES_KEYS = frozenset(["from_seq", "d", "prev_session_date", "series_previous_date", "row", "prev_row"])
ROW_KEYS = frozenset(["date", "soxx", "sma", "rsi", "shd", "prev_rsi"])
CHANGED_NAMES = ("applied_ref", "floor", "frontier_before", "input_hash", "missing_ref", "session_context",
                 "skipped_sessions", "state_after", "transition_result")
BASIS_KEYS = frozenset([
    "operation", "status", "history_digest", "expected_head_seq", "expected_head_hash", "expected_state_digest",
    "restore_point", "ops", "check_d", "request_id", "request_hash", "reason_code", "requested_at", "ledger_digest",
    "sessions_digest", "series_inputs", "series_digest", "effective_digest", "candidate_history", "candidate_digest",
    "candidate_state_digest", "candidate_records", "changes"])
_JSON_RULES = ("json_depth", "json_number", "json_key", "json_type")


def change_ok(c):
    """One row of a plan's `changes` in its safe form: the fixed keys, an operation and a record kind of the fixed lists,
    strict non-negative integers, a real day or None, a real bool or None, and field names of the fixed list only."""
    return (isinstance(c, dict) and set(c) == CHANGE_KEYS and c["op"] in OPS
            and is_int(c["from_seq"]) and c["from_seq"] >= 0 and c["kind"] in RECORD_KINDS
            and (c["d"] is None or is_date(c["d"]))
            and (c["to_seq"] is None or (is_int(c["to_seq"]) and c["to_seq"] >= 0))
            and (c["same_as_superseded"] is None or type(c["same_as_superseded"]) is bool)
            and isinstance(c["changed_fields"], list) and all(f in CHANGED_NAMES for f in c["changed_fields"]))


def _number(x):
    return type(x) in (int, float)


def _row_ok(r):
    return (isinstance(r, dict) and set(r) == ROW_KEYS and is_date(r["date"])
            and all(_number(r[k]) for k in ROW_KEYS if k != "date"))


def series_item_ok(item):
    """One fixed series input of a plan in its safe form (the keys of series_inputs, days, a row or None)."""
    return (isinstance(item, dict) and set(item) == SERIES_KEYS and is_int(item["from_seq"]) and item["from_seq"] >= 0
            and is_date(item["d"]) and is_date(item["prev_session_date"]) and is_date(item["series_previous_date"])
            and _row_ok(item["row"]) and (item["prev_row"] is None or _row_ok(item["prev_row"])))


class RestorePlan:
    """An immutable {basis, plan_hash}. plan_hash is the SHA-256 of the canonical basis; a record never carries it.

    Built by prepare_restore_plan or by from_dict (for a message or a test). Nothing is stored or applied: committed
    is always False."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("RestorePlan is built by prepare_restore_plan or RestorePlan.from_dict")

    @classmethod
    def _wrap(cls, view):
        try:
            text = canonical_json(view)
            loaded = json.loads(text)
        except RecursionError:
            raise restore_invalid("plan", "json_depth") from None
        except (TypeError, ValueError, OverflowError):      # e.g. an integer too long to be written as text
            raise restore_invalid("plan", "json_number") from None
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", loaded)
        return obj

    @classmethod
    def make(cls, basis):
        """The plan of a basis built by this package."""
        return cls._wrap({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))})

    @classmethod
    def from_dict(cls, data):
        """Copy a plan dict. Only the form and the JSON depth and types are checked here; the hash and the contents
        are checked when the plan is confirmed."""
        if not isinstance(data, dict) or set(data) != {"basis", "plan_hash"}:
            raise restore_invalid("plan", "plan_shape")
        try:
            check_json(data)               # depth and types first: only then is copying the input safe
        except PersistenceError as e:
            raise restore_invalid("plan", e.rule if e.rule in _JSON_RULES else "plan_shape") from None
        return cls._wrap(copy.deepcopy(data))

    def __setattr__(self, name, value):
        raise AttributeError("RestorePlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("RestorePlan is immutable")

    def __eq__(self, other):
        return type(other) is type(self) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def basis(self):
        return copy.deepcopy(self._view["basis"])

    @property
    def plan_hash(self):
        return copy.deepcopy(self._view["plan_hash"])      # a value from from_dict may be a dict or a list

    @property
    def status(self):
        b = self._view["basis"]
        status = b.get("status") if isinstance(b, dict) else None
        return READY if status == READY else None

    @property
    def committed(self):
        return False

    def _display(self):
        """The few values that may be shown, each re-checked against its own form; None when anything is off."""
        try:
            b, h = self._view["basis"], self._view["plan_hash"]
            point, records, changes = b["restore_point"], b["candidate_records"], b["changes"]
            if (b["status"] != READY or not valid_request_id(b["request_id"]) or not is_date(b["check_d"])
                    or not is_hex64(h) or not is_int(b["expected_head_seq"]) or b["expected_head_seq"] < 0
                    or not isinstance(point, dict) or set(point) != POINT_KEYS or not is_int(point["seq"])
                    or point["seq"] < 0 or not isinstance(records, list) or not records
                    or not isinstance(changes, list)):
                return None
            shown = []
            for c in changes:
                if not change_ok(c):
                    return None
                shown.append({k: copy.deepcopy(c[k]) for k in ("op", "from_seq", "kind", "d", "to_seq",
                                                               "same_as_superseded", "changed_fields")})
            return (b["status"], b["request_id"], b["check_d"], point["seq"], b["expected_head_seq"], len(records),
                    shown, h)
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: status, request id, numbers, days, fixed op / kind / field names, the same flags, the
        plan hash and the fixed false flags. No value, market figure, F&G, free text or path."""
        shown = self._display()
        if shown is None:
            raise restore_invalid("plan", "plan_shape")
        status, request_id, check_d, point, expected, count, ops, plan_hash = shown
        return {"status": status, "request_id": request_id, "check_d": check_d, "restore_point_seq": point,
                "expected_head_seq": expected, "candidate_head_seq": expected + count, "new_records": count,
                "ops": ops, "plan_hash": plan_hash, "committed": False, "committable": False}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "RestorePlan(?)"
        return "RestorePlan(status=%s, plan_hash=%s)" % (shown[0], shown[7][:12])


class RestoreConfirmResult:
    """Outcome of confirm_restore_plan: the candidate History (or, when the same plan is confirmed again against its
    own candidate, that current History). It has no batch and no ledger, and nothing in it is stored: committed and
    committable are always False. Direct construction is for checked values only."""

    __slots__ = ("_status", "_history", "_plan_hash")

    def __init__(self, status, history, plan_hash):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_history", history)
        object.__setattr__(self, "_plan_hash", plan_hash)

    def __setattr__(self, name, value):
        raise AttributeError("RestoreConfirmResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("RestoreConfirmResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, RestoreConfirmResult)
                and (self._status, self._history, self._plan_hash)
                == (other._status, other._history, other._plan_hash))

    def __hash__(self):
        return hash((self._status, self._plan_hash))

    def __repr__(self):
        return "RestoreConfirmResult(status=%s, committed=False)" % self._status

    status = property(lambda self: self._status)
    history = property(lambda self: self._history)
    plan_hash = property(lambda self: self._plan_hash)
    committed = property(lambda self: False)
    committable = property(lambda self: False)
