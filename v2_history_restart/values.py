"""RestartPlan and RestartConfirmResult: immutable values of the restart operation.

A RestartPlan keeps only canonical JSON text plus a private parsed view that is never handed out; every accessor that
returns structured data returns a fresh copy. A plan built by from_dict is unverified until confirm_restart_plan checks
it, so nothing it carries is printed as it is: the few values shown are re-checked against their own form first.
"""
import copy
import json

from v2_history.common import is_date, is_hex64, is_int
from v2_history.values import check_json
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_recovery.common import valid_request_id

from .errors import restart_invalid

READY = "READY"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
NO_CHANGE = "NO_CHANGE"
OPERATION = "soxl-v2-history-restart-plan/1"
REASON = "RESTART_UNKNOWN"
FLOOR_KEYS = ("last_apply_d", "last_declared_d", "prev_boundary")
BASIS_KEYS = frozenset([
    "operation", "status", "history_digest", "expected_head_seq", "expected_head_hash", "expected_state_digest",
    "resume_after", "check_d", "request_id", "request_hash", "reason_code", "requested_at", "floor",
    "boundary_session", "ledger_digest", "sessions_digest", "effective_digest", "candidate_history",
    "candidate_digest", "candidate_state_digest"])
_JSON_RULES = ("json_depth", "json_number", "json_key", "json_type")


class RestartPlan:
    """An immutable {basis, plan_hash}. plan_hash is the SHA-256 of the canonical basis; a record never carries it.

    Built by prepare_restart_plan or by from_dict (for a message or a test). Nothing is stored or applied: committed
    is always False."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("RestartPlan is built by prepare_restart_plan or RestartPlan.from_dict")

    @classmethod
    def _wrap(cls, view):
        try:
            text = canonical_json(view)
            loaded = json.loads(text)
        except RecursionError:
            raise restart_invalid("plan", "json_depth") from None
        except (TypeError, ValueError, OverflowError):      # e.g. an integer too long to be written as text
            raise restart_invalid("plan", "json_number") from None
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
            raise restart_invalid("plan", "plan_shape")
        try:
            check_json(data)               # depth and types first: only then is copying the input safe
        except PersistenceError as e:
            raise restart_invalid("plan", e.rule if e.rule in _JSON_RULES else "plan_shape") from None
        return cls._wrap(copy.deepcopy(data))

    def __setattr__(self, name, value):
        raise AttributeError("RestartPlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("RestartPlan is immutable")

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
        return READY if isinstance(b, dict) and b.get("status") == READY else None

    @property
    def committed(self):
        return False

    def _display(self):
        """The few values that may be shown, each re-checked against its own form; None when anything is off."""
        try:
            b, h = self._view["basis"], self._view["plan_hash"]
            floor = b["floor"]
            if (b["status"] != READY or not valid_request_id(b["request_id"]) or not is_date(b["resume_after"])
                    or not is_date(b["check_d"]) or not is_hex64(h) or not is_int(b["expected_head_seq"])
                    or b["expected_head_seq"] < 0 or not isinstance(floor, dict) or set(floor) != set(FLOOR_KEYS)):
                return None
            for key in FLOOR_KEYS:
                if floor[key] is not None and not is_date(floor[key]):
                    return None
            shown = {key: floor[key] for key in FLOOR_KEYS}
            return (b["status"], b["request_id"], b["resume_after"], b["check_d"], shown, b["expected_head_seq"], h)
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: status, request id, days, head numbers, the plan hash and the two fixed flags."""
        shown = self._display()
        if shown is None:
            raise restart_invalid("plan", "plan_shape")
        status, request_id, resume_after, check_d, floor, expected, plan_hash = shown
        return {"status": status, "request_id": request_id, "resume_after": resume_after, "check_d": check_d,
                "floor": floor, "expected_head_seq": expected, "candidate_head_seq": expected + 1,
                "new_records": 1, "plan_hash": plan_hash, "committed": False, "committable": False}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "RestartPlan(?)"
        return "RestartPlan(status=%s, plan_hash=%s)" % (shown[0], shown[6][:12])


class RestartConfirmResult:
    """Outcome of confirm_restart_plan: the candidate History (or, when the same plan is confirmed again against its
    own candidate, that current History). It has no batch and no ledger, and nothing in it is stored:
    committed and committable are always False."""

    __slots__ = ("_status", "_history", "_plan_hash")

    def __init__(self, status, history, plan_hash):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_history", history)
        object.__setattr__(self, "_plan_hash", plan_hash)

    def __setattr__(self, name, value):
        raise AttributeError("RestartConfirmResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("RestartConfirmResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, RestartConfirmResult)
                and (self._status, self._history, self._plan_hash)
                == (other._status, other._history, other._plan_hash))

    def __hash__(self):
        return hash((self._status, self._plan_hash))

    def __repr__(self):
        return "RestartConfirmResult(status=%s, committed=False)" % self._status

    status = property(lambda self: self._status)
    history = property(lambda self: self._history)
    plan_hash = property(lambda self: self._plan_hash)
    committed = property(lambda self: False)
    committable = property(lambda self: False)
