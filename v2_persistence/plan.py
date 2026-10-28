"""Plan and result values. All immutable; structured content is returned as fresh copies."""
import json
from dataclasses import dataclass
from typing import Any, Optional

from .codec import canonical_json

PREPARED = "PREPARED"
NO_COMMIT = "NO_COMMIT"
ALREADY_APPLIED = "ALREADY_APPLIED"
COMMITTED = "COMMITTED"
REPLAN_REQUIRED = "REPLAN_REQUIRED"


class AppendPlan:
    """One APPLY to append to a given head. Not an instruction to replace state or history.

    Holds the event as canonical text. `event` returns a new dict on every access.
    """

    __slots__ = ("_expected_head_seq", "_expected_head_hash", "_event_text", "_d", "_event_hash", "_input_hash")

    def __init__(self, expected_head_seq, expected_head_hash, event):
        object.__setattr__(self, "_expected_head_seq", expected_head_seq)
        object.__setattr__(self, "_expected_head_hash", expected_head_hash)
        object.__setattr__(self, "_event_text", canonical_json(event))
        object.__setattr__(self, "_d", event["d"])
        object.__setattr__(self, "_event_hash", event["event_hash"])
        object.__setattr__(self, "_input_hash", event["input_hash"])

    def __setattr__(self, name, value):
        raise AttributeError("AppendPlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("AppendPlan is immutable")

    def __eq__(self, other):
        return (isinstance(other, AppendPlan) and self._expected_head_seq == other._expected_head_seq
                and self._expected_head_hash == other._expected_head_hash and self._event_text == other._event_text)

    def __hash__(self):
        return hash((self._expected_head_seq, self._expected_head_hash, self._event_text))

    def __repr__(self):
        return "AppendPlan(d=%s, head=%s)" % (self._d, self._expected_head_seq)

    @property
    def expected_head_seq(self):
        return self._expected_head_seq

    @property
    def expected_head_hash(self):
        return self._expected_head_hash

    @property
    def d(self):
        return self._d

    @property
    def event_hash(self):
        return self._event_hash

    @property
    def input_hash(self):
        return self._input_hash

    @property
    def event(self):
        return json.loads(self._event_text)


@dataclass(frozen=True)
class PrepareResult:
    """Outcome of prepare_day. Nothing has been stored: `committed` is always False here.

    core_result is evaluate_day's DayResult; its state_updated keeps the core meaning (a new transition candidate),
    not "saved".
    """
    status: str
    plan: Optional[AppendPlan]
    core_result: Any
    committed: bool = False


@dataclass(frozen=True)
class CommitResult:
    status: str
    committed: bool
    snapshot: Any


@dataclass(frozen=True)
class ReconcileResult:
    status: str
    committed: bool = False
