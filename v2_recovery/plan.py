"""prepare_resolution_plan / confirm_resolution_plan: a plan is a checked candidate and its fingerprint, in memory only.

The plan's basis holds every input digest, the normalized commands and the whole candidate ResolutionSet; plan_hash is
the SHA-256 of the basis. A record never carries plan_hash (no circular definition). Confirming rebuilds everything
from the commands and the current inputs and compares. Nothing is stored or applied: committed is always False and
the market state is never changed.
"""
import copy
import json
from dataclasses import dataclass
from typing import Any

from v2_core.errors import CoreError
from v2_persistence.codec import canonical_json, encode_snapshot, sha256_text

from .common import (is_date, is_hex64, is_requested_text, normalize_command, reason_for_commands, request_hash_of,
                     requested_text, same, valid_request_id)
from .commands import make_records, set_dict
from .errors import plan_mismatch, plan_stale, request_conflict, resolution_invalid
from .project import Ctx, resolve_core
from .validate import validate_set
from .values import ResolutionSet, check_json

READY = "READY"
NO_CHANGE = "NO_CHANGE"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
OPERATION = "soxl-v2-resolution-plan/1"
_BASIS_KEYS = frozenset([
    "operation", "status", "snapshot_digest", "expected_head_seq", "expected_head_hash", "resolutions_before_digest",
    "request_id", "request_hash", "requested_at", "check_d", "reason_code", "ledger_digest", "sessions_digest",
    "commands", "candidate_resolutions", "candidate_digest", "expected_state_digest", "excluded_fingerprints",
    "supplemented", "effective_digest"])


class ResolutionPlan:
    """An immutable candidate and its fingerprint. Not applied, not stored. Displays kinds, days, counts and the hash only."""

    __slots__ = ("_text", "_view")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use prepare_resolution_plan or ResolutionPlan.from_dict")

    @classmethod
    def _make(cls, basis):
        return cls._from_view({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))})

    @classmethod
    def _from_view(cls, view):
        check_json(view, "plan")
        text = canonical_json(view)
        obj = object.__new__(cls)
        object.__setattr__(obj, "_text", text)
        object.__setattr__(obj, "_view", json.loads(text))
        return obj

    @classmethod
    def from_dict(cls, data):
        """Rebuild a plan from its dict (for storing in a test or a message). The hash is checked when confirming."""
        if not isinstance(data, dict) or set(data) != {"basis", "plan_hash"}:
            raise resolution_invalid("plan", "plan_shape")
        return cls._from_view(copy.deepcopy(data))

    def __setattr__(self, name, value):
        raise AttributeError("ResolutionPlan is immutable")

    def __delattr__(self, name):
        raise AttributeError("ResolutionPlan is immutable")

    def __eq__(self, other):
        return isinstance(other, ResolutionPlan) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def to_dict(self):
        return copy.deepcopy(self._view)

    @property
    def basis(self):
        return copy.deepcopy(self._view["basis"])

    @property
    def plan_hash(self):
        return self._view["plan_hash"]

    @property
    def status(self):
        b = self._view["basis"]
        return b.get("status") if isinstance(b, dict) else None

    @property
    def committed(self):
        return False

    def summary(self):
        """Whitelist only: kinds, days, counts, reference numbers and the plan hash."""
        b = self._view["basis"]
        cmds = [{"kind": c["kind"], "variant": c["variant"], "d": c["d"], "fingerprints": len(c["record_fingerprints"])}
                for c in b["commands"]]
        return {"status": b["status"], "request_id": b["request_id"], "check_d": b["check_d"], "commands": cmds,
                "excluded": len(b["excluded_fingerprints"]), "supplemented": len(b["supplemented"]),
                "state_unchanged": True, "committed": False, "plan_hash": self._view["plan_hash"]}

    def __repr__(self):
        try:
            b = self._view["basis"]
            return "ResolutionPlan(status=%s, commands=%d, plan_hash=%s)" % (
                b["status"], len(b["commands"]), self._view["plan_hash"][:12])
        except (KeyError, TypeError):
            return "ResolutionPlan(?)"


@dataclass(frozen=True)
class ConfirmResult:
    """Outcome of confirm_resolution_plan: a new set and its projection, in memory. committed is always False."""
    status: str
    committed: bool
    resolutions: Any
    effective_ledger: Any
    plan_hash: str
    state_unchanged: bool = True

    def __repr__(self):
        return "ConfirmResult(status=%s, committed=%s)" % (self.status, self.committed)


def _state_digest(ctx):
    return sha256_text(canonical_json(ctx.sv.events[ctx.sv.head_seq]["state_after"]))


def _build(ctx, snapshot, commands, request_id, reason_code, requested_at):
    """The basis, the candidate set and the projection for one request (shared by prepare and confirm)."""
    if not valid_request_id(request_id):
        raise resolution_invalid("commands", "request_id")
    if not isinstance(commands, (list, tuple)) or not commands:
        raise resolution_invalid("commands", "command_shape")
    norm = [normalize_command(c, "commands") for c in commands]
    if reason_code not in reason_for_commands(norm):
        raise resolution_invalid("commands", "reason_code")
    rhash = request_hash_of(request_id, norm, ctx.check_d, reason_code)
    existing = [r for r in ctx.records if r["request_id"] == request_id]
    if existing:
        if existing[0]["request_hash"] != rhash:
            raise request_conflict()
        status, cand = NO_CHANGE, ctx.resolutions
        eff = resolve_core(ctx, ctx.records, cand.digest, "resolutions")      # the current projection is still checked
    else:
        basis = {"request_id": request_id, "commands": norm, "check_d": ctx.check_d, "reason_code": reason_code,
                 "requested_at": requested_at}
        new = make_records(ctx, ctx.records, norm, basis, rhash)
        cand_records = ctx.records + new
        cand = ResolutionSet.from_dict(set_dict(cand_records))
        validate_set(ctx.sv, cand)                      # what was built passes the same structural check as any set
        status = READY
        eff = resolve_core(ctx, cand_records, cand.digest, "commands")
    basis_out = {
        "operation": OPERATION, "status": status, "snapshot_digest": sha256_text(encode_snapshot(snapshot)),
        "expected_head_seq": ctx.sv.head_seq, "expected_head_hash": ctx.sv.head_hash,
        "resolutions_before_digest": ctx.resolutions.digest, "request_id": request_id, "request_hash": rhash,
        "requested_at": requested_at, "check_d": ctx.check_d, "reason_code": reason_code,
        "ledger_digest": ctx.ledger_digest, "sessions_digest": ctx.sessions_digest, "commands": norm,
        "candidate_resolutions": cand.to_dict(), "candidate_digest": cand.digest,
        "expected_state_digest": _state_digest(ctx), "excluded_fingerprints": eff.excluded_fingerprints,
        "supplemented": eff.supplemented, "effective_digest": eff.effective_digest}
    return basis_out, cand, eff


def prepare_resolution_plan(snapshot, resolutions, commands, sessions, raw_observations, check_d, request_id,
                            reason_code, requested_at):
    """Check every command and the whole candidate; return READY or NO_CHANGE. Inputs are copied, never changed."""
    ctx = Ctx(snapshot, resolutions, sessions, raw_observations, check_d)
    when = requested_text(requested_at)
    basis, _cand, _eff = _build(ctx, snapshot, commands, request_id, reason_code, when)
    return ResolutionPlan._make(basis)


def _plan_basis(plan, confirmed_plan_hash):
    if not isinstance(plan, ResolutionPlan) or not is_hex64(confirmed_plan_hash):
        raise plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or view["plan_hash"] != sha256_text(canonical_json(basis))
            or confirmed_plan_hash != view["plan_hash"] or set(basis) != _BASIS_KEYS):
        raise plan_mismatch()
    if (basis["operation"] != OPERATION or basis["status"] not in (READY, NO_CHANGE) or not is_date(basis["check_d"])
            or not valid_request_id(basis["request_id"]) or not is_requested_text(basis["requested_at"])
            or not isinstance(basis["commands"], list) or not basis["commands"]):
        raise plan_mismatch()
    return basis


def confirm_resolution_plan(plan, confirmed_plan_hash, snapshot, resolutions, sessions, raw_observations):
    """Re-check everything against the plan and return the new set and projection. Nothing is stored or applied."""
    basis = _plan_basis(plan, confirmed_plan_hash)                                   # 1 form and hash first
    ctx = Ctx(snapshot, resolutions, sessions, raw_observations, basis["check_d"])   # 2 copies and checks again
    if (basis["snapshot_digest"] != sha256_text(encode_snapshot(snapshot)) or basis["expected_head_seq"] != ctx.sv.head_seq
            or basis["expected_head_hash"] != ctx.sv.head_hash or basis["ledger_digest"] != ctx.ledger_digest
            or basis["sessions_digest"] != ctx.sessions_digest):
        raise plan_stale()
    current = resolutions.digest
    if current == basis["resolutions_before_digest"]:
        expected = basis
    elif basis["status"] == READY and current == basis["candidate_digest"]:
        expected = copy.deepcopy(basis)                    # the same plan confirmed again against its own candidate
        expected["status"] = NO_CHANGE
        expected["resolutions_before_digest"] = current
    else:
        raise plan_stale()
    try:                                                   # 3 rebuild from the commands
        rebuilt, cand, eff = _build(ctx, snapshot, basis["commands"], basis["request_id"], basis["reason_code"],
                                    basis["requested_at"])
    except CoreError:
        raise plan_mismatch() from None                    # every input digest matched, so the plan itself is wrong
    if not same(rebuilt, expected):
        raise plan_mismatch()
    status = CONFIRMED_IN_MEMORY if rebuilt["status"] == READY else NO_CHANGE
    return ConfirmResult(status, False, cand, eff, plan.plan_hash)
