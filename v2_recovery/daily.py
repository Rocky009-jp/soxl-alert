"""prepare_resolved_day: the S1 single-day preparation on the final ledger, returned as a value that cannot be committed.

The market rules, thresholds and state transition are not copied here: prepare_day (S1) is called once with the final
six-column ledger. Its AppendPlan / PrepareResult are never exposed, so a day computed from resolution records cannot be
handed to MemoryStore.commit or LocalFileStore.commit (their plan_type check refuses anything that is not an AppendPlan).
That is a type boundary against a wrong connection, not protection against code that rebuilds a plan by hand.
"""
import copy

from v2_persistence.codec import canonical_json
from v2_persistence.runner import prepare_day

from .project import Ctx, resolve_core


class SimulationDayResult:
    """status (PREPARED / NO_COMMIT / ALREADY_APPLIED), the core's day result, and the candidate event as text and hash.

    committable and committed are always False. The core's state_updated keeps its core meaning (a new transition
    candidate); it never means saved. There is no plan property.
    """

    __slots__ = ("_status", "_core_result", "_event_text", "_event_hash")

    def __init__(self, status, core_result, event_text, event_hash):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_core_result", copy.deepcopy(core_result))
        object.__setattr__(self, "_event_text", event_text)
        object.__setattr__(self, "_event_hash", event_hash)

    def __setattr__(self, name, value):
        raise AttributeError("SimulationDayResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("SimulationDayResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, SimulationDayResult) and self._status == other._status
                and self._event_text == other._event_text and self._event_hash == other._event_hash)

    def __hash__(self):
        return hash((self._status, self._event_hash))

    def __repr__(self):
        return "SimulationDayResult(status=%s, committable=False, committed=False)" % self._status

    @property
    def status(self):
        return self._status

    @property
    def core_result(self):
        return copy.deepcopy(self._core_result)

    @property
    def candidate_event_text(self):
        return self._event_text

    @property
    def candidate_event_hash(self):
        return self._event_hash

    @property
    def committable(self):
        return False

    @property
    def committed(self):
        return False


def prepare_resolved_day(snapshot, resolutions, d, series, sessions, raw_observations):
    """Resolve the ledger for D (check_d = D), then delegate to S1's prepare_day exactly once."""
    ctx = Ctx(snapshot, resolutions, sessions, raw_observations, d)
    effective = resolve_core(ctx, ctx.records, resolutions.digest, "resolutions")
    res = prepare_day(snapshot, d, series, sessions, effective.raw_observations())
    if res.plan is None:
        return SimulationDayResult(res.status, res.core_result, None, None)
    event = res.plan.event
    return SimulationDayResult(res.status, res.core_result, canonical_json(event), res.plan.event_hash)
