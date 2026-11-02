"""confirm_restart_plan: re-check everything against a plan and return the candidate History, in memory only.

Order (design 9): the plan's form and hash -> the inputs themselves (existing errors stay as they are) -> the digest
and head differences of valid inputs (history_plan_stale) -> rebuild the original and compare (history_plan_mismatch).
A plan is trusted for nothing it states about itself: the candidate it carries is checked again, and the basis is
rebuilt from the original history and the current inputs.
"""
from v2_core.errors import CoreError
from v2_history import History, validate_history
from v2_history.common import is_date, is_hex64, is_int, same
from v2_history.values import RESTART_UNKNOWN, history_dict
from v2_history_ops.errors import history_plan_mismatch, history_plan_stale
from v2_persistence.codec import canonical_json, sha256_text
from v2_recovery.common import is_requested_text, valid_request_id
from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest

from .build import build_restart, initial_state
from .values import (BASIS_KEYS, CONFIRMED_IN_MEMORY, FLOOR_KEYS, NO_CHANGE, OPERATION, READY, REASON, RestartConfirmResult,
                     RestartPlan)

_HASH_KEYS = ("history_digest", "expected_head_hash", "expected_state_digest", "request_hash", "ledger_digest",
              "sessions_digest", "effective_digest", "candidate_digest", "candidate_state_digest")
_SESSION_KEYS = {"date", "open_at", "close_at", "confirmed"}


def _form_ok(basis):
    """The shapes of the plan's own values (design 9 step 1), before anything is rebuilt."""
    floor, session = basis["floor"], basis["boundary_session"]
    return (basis["operation"] == OPERATION and basis["status"] == READY and basis["reason_code"] == REASON
            and valid_request_id(basis["request_id"]) and is_requested_text(basis["requested_at"])
            and is_date(basis["resume_after"]) and is_date(basis["check_d"])
            and is_int(basis["expected_head_seq"]) and basis["expected_head_seq"] >= 0
            and all(is_hex64(basis[k]) for k in _HASH_KEYS)
            and isinstance(floor, dict) and set(floor) == set(FLOOR_KEYS)
            and all(floor[k] is None or is_date(floor[k]) for k in FLOOR_KEYS) and is_date(floor["prev_boundary"])
            and isinstance(session, dict) and set(session) == _SESSION_KEYS
            and session["date"] == basis["resume_after"]
            and isinstance(basis["candidate_history"], dict))


def _candidate_of(basis):
    """The plan's candidate as a checked History, or a refusal: the plan is never trusted for it."""
    try:
        candidate = History.from_dict(basis["candidate_history"])
        cand_check = validate_history(candidate)
    except CoreError:
        raise history_plan_mismatch() from None
    events = candidate.events
    if (candidate.digest != basis["candidate_digest"] or cand_check.state_digest != basis["candidate_state_digest"]
            or not same(candidate.current_state, initial_state()) or events[-1]["kind"] != RESTART_UNKNOWN
            or len(events) != basis["expected_head_seq"] + 2):
        raise history_plan_mismatch()
    return candidate, cand_check


def _plan_basis(plan, confirmed_plan_hash):
    """Step 1: the plan's own form and hash, and its candidate. Nothing here looks at the inputs."""
    if not isinstance(plan, RestartPlan) or not is_hex64(confirmed_plan_hash):
        raise history_plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or set(basis) != BASIS_KEYS or view["plan_hash"] != sha256_text(canonical_json(basis))
            or confirmed_plan_hash != view["plan_hash"] or not _form_ok(basis)):
        raise history_plan_mismatch()
    candidate, cand_check = _candidate_of(basis)
    return basis, candidate, cand_check


def _original_of(history, basis):
    """Branch B: the history the plan was made from, as the physical prefix of the plan's own candidate. It is checked
    like any history and must match the plan's digest, head and state."""
    events = history.events[:basis["expected_head_seq"] + 1]
    original = History.from_dict(history_dict(events))
    check = validate_history(original)
    if (check.history_digest != basis["history_digest"] or check.head_seq != basis["expected_head_seq"]
            or check.head_hash != basis["expected_head_hash"] or check.state_digest != basis["expected_state_digest"]):
        raise history_plan_mismatch()
    return original


def confirm_restart_plan(plan, confirmed_plan_hash, history, sessions, raw_observations):
    """Re-check everything against the plan. Returns CONFIRMED_IN_MEMORY with the candidate History when the history
    is the one the plan was made from, or NO_CHANGE with the current History when it already is the plan's candidate
    (no second record is made). Nothing is stored or applied."""
    basis, candidate, cand_check = _plan_basis(plan, confirmed_plan_hash)                  # 1
    check = validate_history(history)                                                      # 2
    sl = copy_sessions(sessions)
    rows = parse_ledger(raw_observations)
    same_inputs = (ledger_digest(rows) == basis["ledger_digest"] and sessions_digest(sl) == basis["sessions_digest"])
    original = (history.digest == basis["history_digest"] and check.head_seq == basis["expected_head_seq"]
                and check.head_hash == basis["expected_head_hash"])                        # 3 branch A
    already = (history.digest == basis["candidate_digest"] and check.head_seq == cand_check.head_seq
               and check.head_hash == cand_check.head_hash)                                #   branch B
    if not same_inputs or not (original or already):
        raise history_plan_stale()
    try:                                                                                   # 4
        source = history if original else _original_of(history, basis)
        rebuilt, rebuilt_candidate = build_restart(
            source, basis["resume_after"], sessions, raw_observations, basis["check_d"], basis["request_id"],
            lambda: basis["requested_at"])
    except CoreError:
        raise history_plan_mismatch() from None            # every input digest matched, so the plan itself is wrong
    if not same(rebuilt, basis) or rebuilt_candidate != candidate:
        raise history_plan_mismatch()
    if original:
        return RestartConfirmResult(CONFIRMED_IN_MEMORY, rebuilt_candidate, plan.plan_hash)
    return RestartConfirmResult(NO_CHANGE, history, plan.plan_hash)
