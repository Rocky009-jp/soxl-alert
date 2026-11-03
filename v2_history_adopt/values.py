"""AdoptionPlan and AdoptionConfirmResult: immutable values of the prefix adoption (design 5.1).

An AdoptionPlan keeps only canonical JSON text plus a private parsed view that is never handed out; every accessor that
returns structured data returns a fresh copy. A plan built by from_dict is unverified until confirm_prefix_adoption
checks it, so nothing it carries is printed as it is: the few values shown are re-checked against their own form first.

AdoptionConfirmResult may be built directly only from values that confirm_prefix_adoption has checked (a status, an
immutable History and a hash text). That is a trusted internal use; the only reader of outside messages is
AdoptionPlan.from_dict.
"""
import copy

from v2_history import History
from v2_history.common import is_hex64, is_int
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_recovery.common import valid_request_id

from .errors import adoption_invalid

READY = "READY"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
NO_CHANGE = "NO_CHANGE"
OPERATION = "soxl-v2-history-prefix-adoption-plan/1"
REASON = "ADOPT_VERIFIED_PREFIX"
BASIS_KEYS = frozenset([
    "operation", "status", "raw_sha256", "raw_size", "diagnosis_digest", "adopt_count", "discarded",
    "prefix_head_seq", "prefix_head_hash", "prefix_state_digest", "prefix_document_digest", "request_id",
    "request_hash", "reason_code", "requested_at", "candidate_history", "candidate_digest", "candidate_head_seq",
    "candidate_head_hash", "candidate_state_digest", "candidate_record"])
_JSON_RULES = ("json_depth", "json_number", "json_key", "json_type")


class AdoptionPlan:
    """An immutable {basis, plan_hash}. plan_hash is the SHA-256 of the canonical basis; a record never carries it.

    Built by prepare_prefix_adoption or by from_dict (for a message or a test). Nothing is stored or applied:
    committed is always False."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("AdoptionPlan is built by prepare_prefix_adoption or AdoptionPlan.from_dict")

    @classmethod
    def _wrap(cls, view):
        try:
            text = canonical_json(view)
            loaded = copy.deepcopy(view)      # JSON types only: canonical_json refused anything else
        except RecursionError:
            raise adoption_invalid("plan", "json_depth") from None
        except (TypeError, ValueError, OverflowError):      # e.g. an integer too long to be written as text
            raise adoption_invalid("plan", "json_number") from None
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
            raise adoption_invalid("plan", "plan_shape")
        try:
            History.from_dict(data)        # depth and JSON types first (a check of the JSON only): then copying is safe
        except PersistenceError as e:
            raise adoption_invalid("plan", e.rule if e.rule in _JSON_RULES else "plan_shape") from None
        return cls._wrap(copy.deepcopy(data))

    def __setattr__(self, name, value):
        raise AttributeError("AdoptionPlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("AdoptionPlan is immutable")

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
            if (b["status"] != READY or not valid_request_id(b["request_id"]) or not is_hex64(h)
                    or not is_int(b["adopt_count"]) or b["adopt_count"] < 1):
                return None
            return b["status"], b["request_id"], b["adopt_count"], h
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: status, request id, the adopted count, the plan hash and the fixed false flag. No market
        value, raw byte, free text or path."""
        shown = self._display()
        if shown is None:
            raise adoption_invalid("plan", "plan_shape")
        status, request_id, count, plan_hash = shown
        return {"status": status, "request_id": request_id, "adopt_count": count, "plan_hash": plan_hash,
                "committed": False}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "AdoptionPlan(?)"
        return "AdoptionPlan(status=%s, plan_hash=%s)" % (shown[0], shown[3][:12])


class AdoptionConfirmResult:
    """Outcome of confirm_prefix_adoption: the candidate History (verified prefix plus one adoption record), or, when
    the plan is confirmed against its own candidate bytes, that same candidate. Nothing in it is stored: committed is
    always False. Direct construction is for checked values only."""

    __slots__ = ("_status", "_history", "_plan_hash")

    def __init__(self, status, history, plan_hash):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_history", history)
        object.__setattr__(self, "_plan_hash", plan_hash)

    def __setattr__(self, name, value):
        raise AttributeError("AdoptionConfirmResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("AdoptionConfirmResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, AdoptionConfirmResult)
                and (self._status, self._history, self._plan_hash)
                == (other._status, other._history, other._plan_hash))

    def __hash__(self):
        return hash((self._status, self._plan_hash))

    def __repr__(self):
        return "AdoptionConfirmResult(status=%s, committed=False)" % self._status

    status = property(lambda self: self._status)
    history = property(lambda self: self._history)
    plan_hash = property(lambda self: self._plan_hash)
    committed = property(lambda self: False)
