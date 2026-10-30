"""Explicit migration of an S1 Snapshot plus S3-A ResolutionSet into a schema-2 History: plan and confirmation.

A plan is a checked candidate and its fingerprint, in memory only. Its basis holds every input digest and the whole
candidate History; plan_hash is the SHA-256 of the basis (a record never carries it). Confirming rebuilds everything
from the current inputs and compares. Nothing is stored or applied: committed is always False, the v1 data is never
changed, and the candidate History is not a type any existing store accepts.

Order when confirming (design 5.6): form and hash of the plan -> the inputs themselves (existing errors stay) -> digest
and head differences of valid inputs (migration_plan_stale) -> rebuild and compare (migration_plan_mismatch).
"""
import copy
import json
from dataclasses import dataclass
from typing import Any

from v2_core.errors import CoreError
from v2_persistence.codec import canonical_json, encode_snapshot, sha256_text
from v2_persistence.recompute import validate_snapshot
from v2_recovery.common import is_requested_text, requested_text, valid_request_id
from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest
from v2_recovery import resolve_observations, validate_resolutions

from .common import is_date, is_hex64, is_int, same
from .errors import (history_invalid, migration_plan_mismatch, migration_plan_stale, migration_request_conflict)
from .migration import convert_events, reconstruct
from .validate import validate_history
from .values import History, check_json, history_dict

READY = "READY"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
OPERATION = "soxl-v2-history-migration-plan/1"
_BASIS_KEYS = frozenset([
    "operation", "status", "source_snapshot_digest", "source_head_seq", "source_head_hash", "source_resolutions_digest",
    "request_id", "request_hash", "requested_at", "check_d", "ledger_digest", "sessions_digest", "effective_digest",
    "candidate_history", "candidate_digest", "expected_state_digest"])


class MigrationPlan:
    """An immutable candidate History and its fingerprint. Not applied, not stored. Shows only counts, ids and the hash."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use prepare_migration_plan or MigrationPlan.from_dict")

    @classmethod
    def _make(cls, basis):
        return cls._from_view({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))})

    @classmethod
    def _from_view(cls, view):
        check_json(view)
        try:
            text = canonical_json(view)
            loaded = json.loads(text)
        except RecursionError:
            raise history_invalid("json_depth") from None
        except (ValueError, OverflowError):
            raise history_invalid("json_number") from None
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", loaded)
        return obj

    @classmethod
    def from_dict(cls, data):
        """Rebuild a plan from its dict. The hash and the contents are checked when confirming."""
        if not isinstance(data, dict) or set(data) != {"basis", "plan_hash"}:
            raise history_invalid("plan_shape")
        check_json(data)
        return cls._from_view(copy.deepcopy(data))

    def __setattr__(self, name, value):
        raise AttributeError("MigrationPlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("MigrationPlan is immutable")

    def __eq__(self, other):
        return isinstance(other, MigrationPlan) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def basis(self):
        return copy.deepcopy(self._view["basis"])

    @property
    def plan_hash(self):
        return copy.deepcopy(self._view["plan_hash"])

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
            cand = b["candidate_history"]
            records = len(cand["events"])
            if (b["status"] != READY or not valid_request_id(b["request_id"]) or not is_date(b["check_d"])
                    or not is_hex64(h) or not is_int(b["source_head_seq"]) or not is_int(records)):
                return None
            return b["request_id"], b["check_d"], b["source_head_seq"], records, h
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: ids, days, counts and the plan hash."""
        shown = self._display()
        if shown is None:
            raise history_invalid("plan_shape")
        request_id, check_d, source_head, records, plan_hash = shown
        return {"status": READY, "request_id": request_id, "check_d": check_d, "source_head_seq": source_head,
                "candidate_records": records, "state_unchanged": True, "committed": False, "plan_hash": plan_hash}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "MigrationPlan(?)"
        return "MigrationPlan(status=%s, records=%d, plan_hash=%s)" % (READY, shown[3], shown[4][:12])


@dataclass(frozen=True)
class MigrationConfirmResult:
    """Outcome of confirm_migration_plan: a candidate History in memory. committed is always False."""
    status: str
    committed: bool
    history: Any
    plan_hash: str
    state_unchanged: bool = True

    def __repr__(self):
        return "MigrationConfirmResult(status=%s, committed=%s)" % (self.status, self.committed)


def _build(snapshot, resolutions, sessions, raw_observations, check_d, request_id, requested_at_text):
    """The basis for one request. Order (design 5.1): the S1 Snapshot, the S3-A Set, the projection on today's ledger
    and sessions (existing errors stay as they are), the request_id, then the conversion and the full check."""
    validate_snapshot(snapshot)
    validate_resolutions(snapshot, resolutions)
    effective = resolve_observations(snapshot, resolutions, sessions, raw_observations, check_d)
    if not valid_request_id(request_id):
        raise history_invalid("request_id")
    if any(r["request_id"] == request_id for r in resolutions.records):
        raise migration_request_conflict()
    events = convert_events(snapshot, resolutions, effective.ledger_digest, check_d, request_id, requested_at_text)
    candidate = History.from_dict(history_dict(events))
    validate_history(candidate)
    mig = events[-1]
    return {
        "operation": OPERATION, "status": READY, "source_snapshot_digest": sha256_text(encode_snapshot(snapshot)),
        "source_head_seq": snapshot.head_seq, "source_head_hash": snapshot.head_hash,
        "source_resolutions_digest": resolutions.digest, "request_id": request_id,
        "request_hash": mig["request_hash"], "requested_at": requested_at_text, "check_d": check_d,
        "ledger_digest": effective.ledger_digest, "sessions_digest": sessions_digest(copy_sessions(sessions)),
        "effective_digest": effective.effective_digest, "candidate_history": candidate.to_dict(),
        "candidate_digest": candidate.digest,
        "expected_state_digest": sha256_text(canonical_json(snapshot.current_state))}


def prepare_migration_plan(snapshot_v1, resolutions, sessions, raw_observations, check_d, request_id, requested_at):
    """Check every input and the whole candidate; return a READY plan. Inputs are copied, never changed."""
    when = requested_text(requested_at)
    basis = _build(snapshot_v1, resolutions, sessions, raw_observations, check_d, request_id, when)
    return MigrationPlan._make(basis)


def _plan_basis(plan, confirmed_plan_hash):
    if not isinstance(plan, MigrationPlan) or not is_hex64(confirmed_plan_hash):
        raise migration_plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or view["plan_hash"] != sha256_text(canonical_json(basis))
            or confirmed_plan_hash != view["plan_hash"] or set(basis) != _BASIS_KEYS):
        raise migration_plan_mismatch()
    if (basis["operation"] != OPERATION or basis["status"] != READY or not is_date(basis["check_d"])
            or not valid_request_id(basis["request_id"]) or not is_requested_text(basis["requested_at"])):
        raise migration_plan_mismatch()
    return basis


def confirm_migration_plan(plan, confirmed_plan_hash, snapshot_v1, resolutions, sessions, raw_observations):
    """Re-check everything against the plan and return the candidate History. Nothing is stored or applied."""
    basis = _plan_basis(plan, confirmed_plan_hash)                                   # 1 form and hash first
    validate_snapshot(snapshot_v1)                                                   # 2 the inputs themselves
    validate_resolutions(snapshot_v1, resolutions)
    sl = copy_sessions(sessions)
    rows = parse_ledger(raw_observations)
    if (basis["source_snapshot_digest"] != sha256_text(encode_snapshot(snapshot_v1))      # 3 valid but different
            or basis["source_head_seq"] != snapshot_v1.head_seq or basis["source_head_hash"] != snapshot_v1.head_hash
            or basis["source_resolutions_digest"] != resolutions.digest
            or basis["ledger_digest"] != ledger_digest(rows) or basis["sessions_digest"] != sessions_digest(sl)):
        raise migration_plan_stale()
    try:                                                                             # 4 rebuild and compare
        rebuilt = _build(snapshot_v1, resolutions, sessions, raw_observations, basis["check_d"],
                         basis["request_id"], basis["requested_at"])
    except CoreError:
        raise migration_plan_mismatch() from None          # every input digest matched, so the plan itself is wrong
    if not same(rebuilt, basis):
        raise migration_plan_mismatch()
    return MigrationConfirmResult(CONFIRMED_IN_MEMORY, False, History.from_dict(basis["candidate_history"]),
                                  plan.plan_hash)


def migrated_sources(history):
    """The original S1 Snapshot and S3-A ResolutionSet rebuilt from a checked migrated History (design 5.5)."""
    validate_history(history)
    events = history.events
    for i, ev in enumerate(events):
        if ev["kind"] == "SCHEMA_MIGRATION":
            return reconstruct(events, i)
    raise history_invalid("not_migrated")
