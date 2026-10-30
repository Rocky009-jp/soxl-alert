"""prepare_history_resolution_plan / confirm_history_resolution_plan: a plan is a checked candidate History and its
fingerprint, in memory only.

Order of preparation (design 6.2): the history and the ledger context (check_d, sessions, every row) -> requested_at,
request_id, the shape of the commands, reason_code -> the request id against the whole physical history -> the evidence
of the new commands (check_commands, the existing resolutions only as the premise) -> the new records -> the candidate
as a whole (validate_history, then the projection over every segment with the new records in effect).
The basis holds every input digest, the normalized commands and the whole candidate; plan_hash is the SHA-256 of the
basis. A record never carries it. Confirming rebuilds everything from the commands and the current inputs and compares.
Nothing is stored or applied: committed is always False and no state is changed.
"""
import copy

from v2_core.errors import CoreError
from v2_history import validate_history
from v2_history.common import basis_request_hash, is_date, is_hex64, is_int, same
from v2_history.values import ACK, DECLARE_MISSING, check_json
from v2_history.view import normalize_command, reasons_for_commands
from v2_persistence.codec import canonical_json, compute_event_hash, sha256_text
from v2_persistence.errors import PersistenceError
from v2_recovery.commands import check_commands
from v2_recovery.common import is_requested_text, record_reason, requested_text, valid_request_id
from v2_recovery.errors import resolution_invalid
from v2_recovery.facts import LedgerContext
from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest

from .batch import RESOLUTION, append_records, make_batch
from .chain import MIGRATED, RESOLUTION as RESOLUTION_KIND, Chain
from .errors import history_invalid, history_plan_mismatch, history_plan_stale, history_request_conflict
from .read import ledger_of
from .values import _Frozen

READY = "READY"
NO_CHANGE = "NO_CHANGE"
CONFIRMED_IN_MEMORY = "CONFIRMED_IN_MEMORY"
OPERATION = "soxl-v2-history-resolution-plan/1"
_VARIANTS = ("ADDED", "CHANGED", "ROW_REMOVED", "LATE")
_BASIS_KEYS = frozenset([
    "operation", "status", "history_digest", "expected_head_seq", "expected_head_hash", "request_id", "request_hash",
    "requested_at", "check_d", "reason_code", "ledger_digest", "sessions_digest", "commands", "candidate_history",
    "candidate_digest", "expected_state_digest", "excluded_fingerprints", "supplemented", "effective_digest"])
_HASH_KEYS = ("history_digest", "expected_head_hash", "request_hash", "ledger_digest", "sessions_digest",
              "candidate_digest", "expected_state_digest", "effective_digest")


def _plan_error(rule):
    return history_invalid(rule)


class HistoryResolutionPlan(_Frozen):
    """An immutable candidate History and its fingerprint. Not applied, not stored. A plan made by from_dict is
    unverified until it is confirmed: only a few values are shown, each re-checked against its own form."""

    __slots__ = ()

    @classmethod
    def _make(cls, basis):
        return cls._wrap({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))}, _plan_error)

    @classmethod
    def from_dict(cls, data):
        """Copy a plan dict (for a message or a test). Only the form and the JSON depth and types are checked here;
        the hash and the contents are checked when confirming."""
        if not isinstance(data, dict) or set(data) != {"basis", "plan_hash"}:
            raise history_invalid("plan_shape")
        check_json(data)                       # depth and types first: only then is copying the input safe
        return cls._wrap(copy.deepcopy(data), _plan_error)

    @property
    def basis(self):
        return copy.deepcopy(self._view["basis"])

    @property
    def plan_hash(self):
        return copy.deepcopy(self._view["plan_hash"])

    @property
    def status(self):
        b = self._view["basis"]
        status = b.get("status") if isinstance(b, dict) else None
        return status if status in (READY, NO_CHANGE) else None

    @property
    def committed(self):
        return False

    def _display(self):
        """The few values that may be shown, each re-checked against its own form; None when anything is off."""
        try:
            b, h = self._view["basis"], self._view["plan_hash"]
            cmds = []
            for c in b["commands"]:
                if (c["kind"] not in (ACK, DECLARE_MISSING) or c["variant"] not in (None,) + _VARIANTS
                        or not is_date(c["d"]) or not isinstance(c["record_fingerprints"], list)):
                    return None
                cmds.append({"kind": c["kind"], "variant": c["variant"], "d": c["d"],
                             "fingerprints": len(c["record_fingerprints"])})
            if (b["status"] not in (READY, NO_CHANGE) or not valid_request_id(b["request_id"])
                    or not is_date(b["check_d"]) or not is_hex64(h) or not isinstance(b["excluded_fingerprints"], list)
                    or not isinstance(b["supplemented"], list)):
                return None
            return b["status"], b["request_id"], b["check_d"], cmds, len(b["excluded_fingerprints"]), \
                len(b["supplemented"]), h
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: kinds, days, counts and the plan hash."""
        shown = self._display()
        if shown is None:
            raise history_invalid("plan_shape")
        status, request_id, check_d, cmds, excluded, supplemented, plan_hash = shown
        return {"status": status, "request_id": request_id, "check_d": check_d, "commands": cmds,
                "new_records": len(cmds) if status == READY else 0, "excluded": excluded,
                "supplemented": supplemented, "state_unchanged": True, "committed": False, "plan_hash": plan_hash}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "HistoryResolutionPlan(?)"
        return "HistoryResolutionPlan(status=%s, commands=%d, plan_hash=%s)" % (shown[0], len(shown[3]), shown[6][:12])


class HistoryResolutionConfirmResult:
    """Outcome of confirm_history_resolution_plan: the candidate History, its ledger and, for a new request, the batch.
    committed is always False and state_unchanged is always True."""

    __slots__ = ("_status", "_history", "_ledger", "_batch", "_plan_hash")

    def __init__(self, status, history, ledger, batch, plan_hash):
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_history", history)
        object.__setattr__(self, "_ledger", ledger)
        object.__setattr__(self, "_batch", batch)
        object.__setattr__(self, "_plan_hash", plan_hash)

    def __setattr__(self, name, value):
        raise AttributeError("HistoryResolutionConfirmResult is immutable")

    def __delattr__(self, name):
        raise AttributeError("HistoryResolutionConfirmResult is immutable")

    def __eq__(self, other):
        return (isinstance(other, HistoryResolutionConfirmResult)
                and (self._status, self._history, self._ledger, self._batch, self._plan_hash)
                == (other._status, other._history, other._ledger, other._batch, other._plan_hash))

    def __hash__(self):
        return hash((self._status, self._plan_hash))

    def __repr__(self):
        return "HistoryResolutionConfirmResult(status=%s, committed=False)" % self._status

    status = property(lambda self: self._status)
    history = property(lambda self: self._history)
    ledger = property(lambda self: self._ledger)
    batch = property(lambda self: self._batch)
    plan_hash = property(lambda self: self._plan_hash)
    committed = property(lambda self: False)
    state_unchanged = property(lambda self: True)


# --- preparation --------------------------------------------------------------------------------------------------
def _normalize(cmd):
    """The v2 form of one command; a refusal is resolution_invalid / commands / command_shape."""
    try:
        return normalize_command(cmd, "v2")
    except (PersistenceError, TypeError, ValueError, KeyError, AttributeError):
        raise resolution_invalid("commands", "command_shape") from None


def request_status(groups, request_id, request_hash):
    """The request id against the whole physical history (design 6.5): 'NEW', 'NO_CHANGE' or a refusal.

    An id that appears only in superseded records, in a migrated record, or in a restart / restore / migration record
    is never a new request. The same live native or replayed request with the same request hash is NO_CHANGE."""
    found = [g for g in groups if g["request_id"] == request_id]
    if not found:
        return "NEW"
    if any(g["record_kind"] != RESOLUTION_KIND for g in found):
        raise history_request_conflict()
    live = [g for g in found if g["effective"]]
    if not live or any(g["source"] == MIGRATED for g in live):
        raise history_request_conflict()
    if all(g["request_hash"] == request_hash for g in live):
        return "NO_CHANGE"
    raise history_request_conflict()


def _new_records(check, ctx, norm, extras, basis, request_hash, state):
    """The ACK / DECLARE_MISSING records (design 6.3), chained after the physical head."""
    out, parent_seq, parent_hash = [], check.head_seq, check.head_hash
    for i, (cmd, (frontier, context)) in enumerate(zip(norm, extras)):
        rec = {
            "kind": cmd["kind"], "seq": check.head_seq + 1 + i, "parent_seq": parent_seq,
            "parent_hash": parent_hash, "variant": cmd["variant"], "d": cmd["d"],
            "record_fingerprints": list(cmd["record_fingerprints"]),
            "applied_ref": copy.deepcopy(cmd["applied_ref"]), "missing_ref": copy.deepcopy(cmd["missing_ref"]),
            "session_context": context, "frontier_before": frontier, "request_id": basis["request_id"],
            "request_hash": request_hash, "request_basis": copy.deepcopy(basis), "command_index": i,
            "command_count": len(norm), "reason_code": record_reason(cmd["kind"]),
            "requested_at": basis["requested_at"], "ledger_digest": ctx.ledger_digest, "origin": None,
            "replay_of": None, "state_after": copy.deepcopy(state)}
        rec["event_hash"] = compute_event_hash(rec)
        parent_seq, parent_hash = rec["seq"], rec["event_hash"]
        out.append(rec)
    return out


def _build(history, commands, sessions, raw_observations, check_d, request_id, reason_code, when):
    """The basis, the candidate and the projection for one request (shared by prepare and confirm).

    when() gives the requested_at text; it is asked for after the context is built, so that an input error of the
    history, check_d, sessions or ledger comes first. Returns (basis, candidate, candidate_check, ledger, new_records)."""
    check = validate_history(history)                                                      # 1
    chain = Chain(history, check)
    ctx = LedgerContext.from_facts(chain.facts, sessions, raw_observations, check_d)
    requested_at = when()                                                                  # 2
    if not valid_request_id(request_id):
        raise resolution_invalid("commands", "request_id")
    if not isinstance(commands, (list, tuple)) or not commands:
        raise resolution_invalid("commands", "command_shape")
    norm = [_normalize(c) for c in commands]
    if reason_code not in reasons_for_commands(norm):
        raise resolution_invalid("commands", "reason_code")
    request_basis = {"request_id": request_id, "commands": norm, "check_d": ctx.check_d, "reason_code": reason_code,
                     "requested_at": requested_at}
    rhash = basis_request_hash(request_basis)
    status = READY if request_status(chain.request_groups(), request_id, rhash) == "NEW" else NO_CHANGE   # 3
    if status == NO_CHANGE:
        candidate, candidate_check, new = history, check, []
        ledger, _ = ledger_of(history, chain, sessions, raw_observations, check_d, ctx=ctx)   # still checked
    else:
        extras = check_commands(ctx, chain.resolutions, norm)                              # 4
        new = _new_records(check, ctx, norm, extras, request_basis, rhash, history.current_state)   # 5
        candidate = append_records(history, new)                                           # 6
        candidate_check = validate_history(candidate)
        cand_chain = Chain(candidate, candidate_check)
        ledger, _ = ledger_of(candidate, cand_chain, sessions, raw_observations, check_d, field="commands")
    basis = {
        "operation": OPERATION, "status": status, "history_digest": check.history_digest,
        "expected_head_seq": check.head_seq, "expected_head_hash": check.head_hash, "request_id": request_id,
        "request_hash": rhash, "requested_at": requested_at, "check_d": ctx.check_d, "reason_code": reason_code,
        "ledger_digest": ctx.ledger_digest, "sessions_digest": ctx.sessions_digest, "commands": norm,
        "candidate_history": candidate.to_dict(), "candidate_digest": candidate.digest,
        "expected_state_digest": check.state_digest, "excluded_fingerprints": ledger.excluded_fingerprints,
        "supplemented": ledger.supplemented, "effective_digest": ledger.effective_digest}
    return basis, candidate, candidate_check, ledger, new


def prepare_history_resolution_plan(history, commands, sessions, raw_observations, check_d, request_id, reason_code,
                                    requested_at):
    """Check every command and the whole candidate; return a READY or NO_CHANGE plan. Inputs are copied, never
    changed. check_d is explicit; requested_at is an injected aware datetime (no clock is read)."""
    basis = _build(history, commands, sessions, raw_observations, check_d, request_id, reason_code,
                   lambda: requested_text(requested_at))[0]
    return HistoryResolutionPlan._make(basis)


# --- confirmation -------------------------------------------------------------------------------------------------
def _plan_basis(plan, confirmed_plan_hash):
    """Step 1: the plan's own form and hash. Nothing here looks at the inputs."""
    if not isinstance(plan, HistoryResolutionPlan) or not is_hex64(confirmed_plan_hash):
        raise history_plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or view["plan_hash"] != sha256_text(canonical_json(basis))
            or confirmed_plan_hash != view["plan_hash"] or set(basis) != _BASIS_KEYS):
        raise history_plan_mismatch()
    if (basis["operation"] != OPERATION or basis["status"] not in (READY, NO_CHANGE) or not is_date(basis["check_d"])
            or not valid_request_id(basis["request_id"]) or not is_requested_text(basis["requested_at"])
            or not isinstance(basis["commands"], list) or not basis["commands"]
            or not is_int(basis["expected_head_seq"]) or any(not is_hex64(basis[k]) for k in _HASH_KEYS)
            or not isinstance(basis["candidate_history"], dict)):
        raise history_plan_mismatch()
    return basis


def _candidate_head(basis):
    """(seq, event_hash) of the last record of the plan's candidate, or None when it cannot be read."""
    try:
        last = basis["candidate_history"]["events"][-1]
        seq, event_hash = last["seq"], last["event_hash"]
    except (KeyError, TypeError, IndexError):
        return None
    return (seq, event_hash) if is_int(seq) and is_hex64(event_hash) else None


def confirm_history_resolution_plan(plan, confirmed_plan_hash, history, sessions, raw_observations):
    """Re-check everything against the plan and return the candidate History. Nothing is stored or applied.

    Order (design 6.7): the plan's form and hash -> the inputs themselves (existing errors stay as they are) -> the
    digest and head differences of valid inputs (history_plan_stale) -> rebuild and compare (history_plan_mismatch)."""
    basis = _plan_basis(plan, confirmed_plan_hash)                                         # 1
    check = validate_history(history)                                                      # 2
    sl = copy_sessions(sessions)
    rows = parse_ledger(raw_observations)
    same_inputs = (ledger_digest(rows) == basis["ledger_digest"] and sessions_digest(sl) == basis["sessions_digest"])
    original = (history.digest == basis["history_digest"] and check.head_seq == basis["expected_head_seq"]
                and check.head_hash == basis["expected_head_hash"])                        # 3 branch A
    candidate_head = _candidate_head(basis)
    already = (basis["status"] == READY and candidate_head is not None and history.digest == basis["candidate_digest"]
               and (check.head_seq, check.head_hash) == candidate_head)                    #   branch B
    if not same_inputs or not (original or already):
        raise history_plan_stale()
    if original:
        expected = basis
    else:
        expected = copy.deepcopy(basis)                    # the same plan confirmed again against its own candidate
        expected["status"] = NO_CHANGE
        expected["history_digest"] = basis["candidate_digest"]
        expected["expected_head_seq"], expected["expected_head_hash"] = candidate_head
    try:                                                                                   # 4
        rebuilt, candidate, candidate_check, ledger, new = _build(
            history, basis["commands"], sessions, raw_observations, basis["check_d"], basis["request_id"],
            basis["reason_code"], lambda: basis["requested_at"])
    except CoreError:
        raise history_plan_mismatch() from None            # every input digest matched, so the plan itself is wrong
    if not same(rebuilt, expected):
        raise history_plan_mismatch()
    if rebuilt["status"] == NO_CHANGE:
        return HistoryResolutionConfirmResult(NO_CHANGE, history, ledger, None, plan.plan_hash)
    batch = make_batch(history, check, new, candidate, candidate_check, RESOLUTION, None, basis["request_id"],
                       plan.plan_hash)
    return HistoryResolutionConfirmResult(CONFIRMED_IN_MEMORY, candidate, ledger, batch, plan.plan_hash)
