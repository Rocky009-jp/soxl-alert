"""prepare_history_day: one explicit target session D on a checked history, delegated to S1 prepare_day once.

Order (fixed): the history -> D as a date -> the ledger over every effective segment (explicit check_d = D) -> the
current segment as a temporary S1 Snapshot -> prepare_day (called exactly once, on the current segment and the final
ledger) -> for a new day: the APPLY re-attached to the physical head, the candidate history checked with
validate_history and projected over every segment again, then the batch.

The market rules, thresholds and state transition are not copied here. The S1 AppendPlan / PrepareResult are never
returned and their temporary seq and hashes never leave this function: the record carries the v2 head as its parent.
committable and committed are always False; core_result.state_updated keeps its core meaning (a new transition
candidate) and never means saved.
"""
import copy

from v2_core.fixture import parse_iso_date
from v2_history import validate_history
from v2_history.values import APPLY
from v2_persistence.codec import compute_event_hash
from v2_persistence.plan import ALREADY_APPLIED, NO_COMMIT, PREPARED
from v2_persistence.runner import prepare_day

from .batch import DAILY, append_records, make_batch
from .chain import Chain
from .read import ledger_of

__all__ = ["HistoryDayResult", "prepare_history_day", "PREPARED", "NO_COMMIT", "ALREADY_APPLIED"]


class HistoryDayResult:
    """status (PREPARED / NO_COMMIT / ALREADY_APPLIED), the core's day result and, for a new day only, the batch.

    There is no plan property. committable and committed are always False."""

    __slots__ = ("_status", "_d", "_history_digest", "_core_result", "_batch", "_candidate_digest")

    def __init__(self, status, d, history_digest, core_result, batch, candidate_digest):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_d", d)
        object.__setattr__(self, "_history_digest", history_digest)
        object.__setattr__(self, "_core_result", copy.deepcopy(core_result))
        object.__setattr__(self, "_batch", batch)
        object.__setattr__(self, "_candidate_digest", candidate_digest)

    def __setattr__(self, name, value):
        raise AttributeError("HistoryDayResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("HistoryDayResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, HistoryDayResult)
                and (self._status, self._d, self._history_digest, self._candidate_digest, self._batch)
                == (other._status, other._d, other._history_digest, other._candidate_digest, other._batch))

    def __hash__(self):
        return hash((self._status, self._d, self._history_digest, self._candidate_digest))

    def __repr__(self):
        return "HistoryDayResult(status=%s, committable=False, committed=False)" % self._status

    @property
    def status(self):
        return self._status

    @property
    def d(self):
        return self._d

    @property
    def history_digest(self):
        return self._history_digest

    @property
    def core_result(self):
        return copy.deepcopy(self._core_result)

    @property
    def batch(self):
        return self._batch

    @property
    def candidate_digest(self):
        return self._candidate_digest

    @property
    def committable(self):
        return False

    @property
    def committed(self):
        return False


def _apply_record(event, head_seq, head_hash):
    """The six content items of the S1 event kept as they are; only the position is the v2 physical head."""
    record = {"kind": APPLY, "seq": head_seq + 1, "parent_seq": head_seq, "parent_hash": head_hash}
    for key in ("d", "confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after"):
        record[key] = copy.deepcopy(event[key])
    record["event_hash"] = compute_event_hash(record)
    return record


def prepare_history_day(history, d, series, sessions, raw_observations):
    """The candidate APPLY for D, or why there is none. Inputs are copied, never changed."""
    check = validate_history(history)                                              # 1
    parse_iso_date(d, "target_session_date")                                       # 2
    chain = Chain(history, check)
    ledger, _ctx = ledger_of(history, chain, sessions, raw_observations, d)        # 3
    snapshot = chain.current_snapshot()                                            # 4
    res = prepare_day(snapshot, d, series, sessions, ledger.raw_observations())    # 5
    if res.plan is None:
        return HistoryDayResult(res.status, d, history.digest, res.core_result, None, None)
    record = _apply_record(res.plan.event, check.head_seq, check.head_hash)        # 6
    candidate = append_records(history, [record])                                  # 7
    candidate_check = validate_history(candidate)
    ledger_of(candidate, Chain(candidate, candidate_check), sessions, raw_observations, d)
    batch = make_batch(history, check, [record], candidate, candidate_check, DAILY, d, None, None)
    return HistoryDayResult(res.status, d, history.digest, res.core_result, batch, candidate.digest)
