"""MemoryStore (in-process compare-and-swap) and reconcile.

The store lives in one process. It does not survive the process, does not fsync, is not shared between processes and
does not retry or send anything. COMMITTED means "this plan was appended to this in-memory store", nothing more.
"""
import threading

from .errors import PersistenceError, snapshot_invalid
from .events import APPLY, append_event
from .plan import ALREADY_APPLIED, COMMITTED, REPLAN_REQUIRED, AppendPlan, CommitResult, ReconcileResult
from .recompute import validate_snapshot


class MemoryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = None

    def read(self):
        """The current Snapshot (immutable; every structured accessor returns a fresh copy)."""
        with self._lock:
            if self._snapshot is None:
                raise PersistenceError("store_uninitialized", "store")
            return self._snapshot

    def initialize(self, genesis):
        """Explicit initialization with a GENESIS-only Snapshot. Never done implicitly by read or commit."""
        validate_snapshot(genesis)
        events = genesis.events
        if len(events) != 1:
            raise snapshot_invalid("initialize_not_genesis_only")
        with self._lock:
            if self._snapshot is not None:
                raise PersistenceError("already_initialized", "store")
            self._snapshot = genesis

    def commit(self, plan):
        """Compare the expected head, check the whole candidate and replace the Snapshot, all under one lock."""
        if not isinstance(plan, AppendPlan):
            raise snapshot_invalid("plan_type")
        with self._lock:
            current = self._snapshot
            if current is None:
                raise PersistenceError("store_uninitialized", "store")
            if plan.expected_head_seq != current.head_seq or plan.expected_head_hash != current.head_hash:
                raise PersistenceError("cas_conflict", "head")
            candidate = append_event(current, plan.event)
            validate_snapshot(candidate)
            self._snapshot = candidate
            return CommitResult(COMMITTED, True, candidate)


def reconcile(plan, snapshot):
    """After an unknown or lost commit result: look for the plan's D in a freshly read, validated Snapshot.

    Writes nothing and never re-attaches an old plan to a newer head. ALREADY_APPLIED means a record with the same
    parent hash, input hash, transition result and state is stored; it does not say who wrote it, so it never grants
    the right to notify. A different record for the same D is concurrent_conflict; no record for D is REPLAN_REQUIRED.
    """
    if not isinstance(plan, AppendPlan):
        raise snapshot_invalid("plan_type")
    validate_snapshot(snapshot)
    wanted = plan.event
    for ev in snapshot.events:
        if ev["kind"] == APPLY and ev["d"] == plan.d:
            same = (ev["parent_hash"] == wanted["parent_hash"] and ev["input_hash"] == wanted["input_hash"]
                    and ev["transition_result"] == wanted["transition_result"]
                    and ev["state_after"] == wanted["state_after"])
            if same:
                return ReconcileResult(ALREADY_APPLIED)
            raise PersistenceError("concurrent_conflict", "events", detail=plan.d)
    return ReconcileResult(REPLAN_REQUIRED)
