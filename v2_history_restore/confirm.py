"""confirm_restore_plan: re-check everything against a plan and return the candidate History, in memory only.

Order (design 11): the plan's form, hash and candidate -> the inputs themselves (existing errors stay as they are, the
series inputs are read again from the plan's own original prefix) -> the digest and head differences of valid inputs
(history_plan_stale) -> rebuild the original and compare (history_plan_mismatch). A plan is trusted for nothing it
states about itself: the candidate it carries is checked again, and the basis is rebuilt from the original history and
the current inputs.
"""
from v2_core.errors import CoreError
from v2_history import History, validate_history
from v2_history.common import is_date, is_hex64, is_int, same
from v2_history.values import APPLY, RECOVERY_RESTORE, history_dict
from v2_history_ops.errors import history_plan_mismatch, history_plan_stale
from v2_persistence.codec import canonical_json, sha256_text
from v2_recovery.common import is_requested_text, valid_request_id
from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest

from .build import build_restore
from .market import digest_of, series_inputs
from .values import (BASIS_KEYS, CONFIRMED_IN_MEMORY, NO_CHANGE, OP_KEYS, OPERATION, OPS, POINT_KEYS, READY, REAPPLY,
                     REASON, RestoreConfirmResult, RestorePlan)

_HASH_KEYS = ("history_digest", "expected_head_hash", "expected_state_digest", "request_hash", "ledger_digest",
              "sessions_digest", "series_digest", "effective_digest", "candidate_digest", "candidate_state_digest")


def _form_ok(basis):
    """The shapes of the plan's own values (design 11 step 1), before anything is rebuilt."""
    point, ops = basis["restore_point"], basis["ops"]
    return (basis["operation"] == OPERATION and basis["status"] == READY and basis["reason_code"] == REASON
            and valid_request_id(basis["request_id"]) and is_requested_text(basis["requested_at"])
            and is_date(basis["check_d"]) and is_int(basis["expected_head_seq"]) and basis["expected_head_seq"] >= 0
            and all(is_hex64(basis[k]) for k in _HASH_KEYS)
            and isinstance(point, dict) and set(point) == POINT_KEYS and is_int(point["seq"])
            and is_hex64(point["event_hash"])
            and isinstance(ops, list) and all(isinstance(o, dict) and set(o) == OP_KEYS and o["op"] in OPS
                                              and is_int(o["from_seq"]) for o in ops)
            and isinstance(basis["series_inputs"], list) and isinstance(basis["changes"], list)
            and isinstance(basis["candidate_records"], list) and basis["candidate_records"]
            and isinstance(basis["candidate_history"], dict))


def _original_prefix(events, basis):
    """The history the plan was made from, as the physical prefix of a candidate: checked like any history, and it must
    match the plan's digest, head and state."""
    original = History.from_dict(history_dict(events[:basis["expected_head_seq"] + 1]))
    check = validate_history(original)
    if (check.history_digest != basis["history_digest"] or check.head_seq != basis["expected_head_seq"]
            or check.head_hash != basis["expected_head_hash"] or check.state_digest != basis["expected_state_digest"]):
        raise history_plan_mismatch()
    return original


def _candidate_of(basis):
    """The plan's candidate as a checked History with its original prefix, or a refusal: the plan is never trusted for it."""
    try:
        candidate = History.from_dict(basis["candidate_history"])
        cand_check = validate_history(candidate)
        events = candidate.events
        cut = basis["expected_head_seq"] + 1
        if (candidate.digest != basis["candidate_digest"] or cand_check.state_digest != basis["candidate_state_digest"]
                or len(events) <= cut or events[cut]["kind"] != RECOVERY_RESTORE
                or canonical_json(events[cut:]) != canonical_json(basis["candidate_records"])):
            raise history_plan_mismatch()
        original = _original_prefix(events, basis)
    except CoreError:
        raise history_plan_mismatch() from None
    return candidate, cand_check, events, original


def _reapply_olds(basis, events):
    """The saved APPLY records the plan says it applies again, read from the plan's own original prefix."""
    olds = []
    for o in basis["ops"]:
        if o["op"] == REAPPLY:
            seq = o["from_seq"]
            if not 0 <= seq <= basis["expected_head_seq"] or events[seq]["kind"] != APPLY:
                raise history_plan_mismatch()
            olds.append(events[seq])
    return olds


def _plan_basis(plan, confirmed_plan_hash):
    """Step 1: the plan's own form and hash, and its candidate. Nothing here looks at the inputs."""
    if not isinstance(plan, RestorePlan) or not is_hex64(confirmed_plan_hash):
        raise history_plan_mismatch()
    view = plan.to_dict()
    basis = view["basis"]
    if (not isinstance(basis, dict) or set(basis) != BASIS_KEYS or view["plan_hash"] != sha256_text(canonical_json(basis))
            or confirmed_plan_hash != view["plan_hash"] or not _form_ok(basis)):
        raise history_plan_mismatch()
    candidate, cand_check, events, original = _candidate_of(basis)
    return basis, candidate, cand_check, events, original


def confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_observations, series):
    """Re-check everything against the plan. Returns CONFIRMED_IN_MEMORY with the candidate History when the history is
    the one the plan was made from, or NO_CHANGE with the current History when it already is the plan's candidate (no
    second RECOVERY_RESTORE is made). Nothing is stored or applied."""
    basis, candidate, cand_check, cand_events, original = _plan_basis(plan, confirmed_plan_hash)   # 1
    check = validate_history(history)                                                      # 2
    sl = copy_sessions(sessions)
    rows = parse_ledger(raw_observations)
    olds = _reapply_olds(basis, cand_events)
    items = series_inputs(series, sl, olds)[0] if olds else []
    same_inputs = (ledger_digest(rows) == basis["ledger_digest"] and sessions_digest(sl) == basis["sessions_digest"]
                   and digest_of(items) == basis["series_digest"])
    is_original = (history.digest == basis["history_digest"] and check.head_seq == basis["expected_head_seq"]
                   and check.head_hash == basis["expected_head_hash"])                      # 3 branch A
    already = (history.digest == basis["candidate_digest"] and check.head_seq == cand_check.head_seq
               and check.head_hash == cand_check.head_hash)                                 #   branch B
    if not same_inputs or not (is_original or already):
        raise history_plan_stale()
    try:                                                                                   # 4
        source = history if is_original else original
        rebuilt, rebuilt_candidate = build_restore(
            source, basis["restore_point"], basis["ops"], sessions, raw_observations, series, basis["check_d"],
            basis["request_id"], lambda: basis["requested_at"])
    except CoreError:
        raise history_plan_mismatch() from None            # every input digest matched, so the plan itself is wrong
    if not same(rebuilt, basis) or rebuilt_candidate != candidate:
        raise history_plan_mismatch()
    if is_original:
        return RestoreConfirmResult(CONFIRMED_IN_MEMORY, rebuilt_candidate, plan.plan_hash)
    return RestoreConfirmResult(NO_CHANGE, history, plan.plan_hash)
