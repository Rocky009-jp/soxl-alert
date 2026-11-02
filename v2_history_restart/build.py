"""The shared preparation of one restart: the checked inputs, the new RESTART_UNKNOWN record, the candidate History
and the plan basis. prepare_restart_plan runs it once on the given history; confirm_restart_plan runs it again on the
original history and compares the result with the plan's basis.

The order is fixed (design 4): the history, sessions, dates and ledger rows -> check_d and the resume session ->
requested_at, the request id -> the floor and the bounds -> the ledger projection of the original history -> the new
record and the candidate as a whole. No market rule, threshold or state formula is written here: the original history
is projected by the unchanged B-2 function and the candidate is checked by the unchanged validate_history.
"""
import copy

from v2_core.state import MarketState
from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_history import History, validate_history
from v2_history.common import basis_request_hash, same
from v2_history.values import DECLARE_MISSING, RESTART_UNKNOWN, history_dict
from v2_history_ops import project_history_ledger, read_effective
from v2_history_ops.errors import history_request_conflict
from v2_persistence.codec import canonical_json, compute_event_hash, sha256_text
from v2_persistence.events import session_dict
from v2_recovery.common import requested_text, valid_request_id
from v2_recovery.ledger import copy_sessions, parse_ledger, sessions_digest

from .errors import candidate_invalid, restart_invalid
from .values import OPERATION, READY, REASON


def initial_state():
    return MarketState.initial().to_dict()


def requested_at_of(value):
    """The injected aware datetime as fixed UTC text (a clock is never read)."""
    return requested_text(value)


def _check_sessions(sl, check_d, resume_after):
    """check_d must be a confirmed session with a previous and a next session (the next one need not be confirmed);
    the resume session must exist and be confirmed. The existing session errors are reused for check_d."""
    session = sl.get(check_d)
    if session is None:
        raise InputError("target_not_in_sessions", "sessions")
    if not session.confirmed:
        raise InputError("target_unconfirmed", "sessions")
    if sl.next(check_d) is None:
        raise InputError("next_session_missing", "sessions")
    if sl.previous(check_d) is None:
        raise InputError("previous_session_missing", "sessions")
    resume = sl.get(resume_after)
    if resume is None or not resume.confirmed:
        raise restart_invalid("resume_after", "restart_boundary")
    return resume


def _floor_of(check, view):
    """The restart floor from the whole effective history (design 5). Superseded records never raise it."""
    declared = [r["d"] for r in view.resolutions if r["kind"] == DECLARE_MISSING]
    return {"last_apply_d": check.latest_apply_d, "last_declared_d": max(declared) if declared else None,
            "prev_boundary": check.current_boundary.after}


def _check_bounds(history, floor, resume_after, check_d):
    """The floor, the upper bound and the no-effect rule (design 5), in this order."""
    if resume_after < max(v for v in floor.values() if v is not None):
        raise restart_invalid("resume_after", "restart_floor")
    if resume_after > check_d:
        raise restart_invalid("check_d", "check_d")
    if same(history.current_state, initial_state()) and resume_after == floor["prev_boundary"]:
        raise restart_invalid("resume_after", "restart_noop")


def _new_record(check, resume_after, session, floor, request_id, request_hash, request_basis, requested_at):
    rec = {
        "kind": RESTART_UNKNOWN, "seq": check.head_seq + 1, "parent_seq": check.head_seq,
        "parent_hash": check.head_hash, "resume_after": resume_after, "boundary_session": session_dict(session),
        "floor": floor, "request_id": request_id, "request_hash": request_hash, "request_basis": request_basis,
        "reason_code": REASON, "requested_at": requested_at, "replay_of": None, "state_after": initial_state()}
    rec["event_hash"] = compute_event_hash(rec)
    return rec


def _check_candidate(history, check, view, candidate, rec, resume_after):
    """The whole candidate (design 8): validate_history, then everything of the original is kept as it was."""
    cand_check = validate_history(candidate)
    events, old = candidate.events, history.events
    if (len(events) != len(old) + 1 or canonical_json(events[:-1]) != canonical_json(old)
            or canonical_json(events[-1]) != canonical_json(rec)):
        raise candidate_invalid()
    cand_view = read_effective(candidate)
    boundary = cand_check.current_boundary
    if (list(cand_check.effective_seqs) != list(check.effective_seqs) + [rec["seq"]]
            or list(cand_check.superseded_seqs) != list(check.superseded_seqs)
            or (boundary.kind, boundary.seq, boundary.after) != (RESTART_UNKNOWN, rec["seq"], resume_after)
            or not same(candidate.current_state, initial_state())
            or cand_check.state_digest != sha256_text(canonical_json(initial_state()))
            or cand_check.migrated != check.migrated or cand_view.migration_seq != view.migration_seq
            or not same(cand_view.applies, view.applies) or not same(cand_view.resolutions, view.resolutions)
            or not same(cand_view.segments[:-1], view.segments)):
        raise candidate_invalid()
    return cand_check


def build_restart(history, resume_after, sessions, raw_observations, check_d, request_id, when):
    """Returns (basis, candidate). when() gives the requested_at text; it is asked for after the inputs are read, so
    that an error of the history, sessions, dates or ledger rows comes first."""
    check = validate_history(history)                                                      # 1
    sl = copy_sessions(sessions)
    parse_iso_date(check_d, "target_session_date")
    parse_iso_date(resume_after, "resume_after")
    parse_ledger(raw_observations)
    resume = _check_sessions(sl, check_d, resume_after)                                    # 2
    requested_at = when()                                                                  # 3
    if not valid_request_id(request_id):
        raise restart_invalid("request_id", "request_id")
    view = read_effective(history)
    if any(g["request_id"] == request_id for g in view.requests):
        raise history_request_conflict()
    request_basis = {"request_id": request_id, "resume_after": resume_after, "check_d": check_d,
                     "reason_code": REASON, "requested_at": requested_at}
    request_hash = basis_request_hash(request_basis)
    floor = _floor_of(check, view)                                                         # 4
    _check_bounds(history, floor, resume_after, check_d)
    ledger = project_history_ledger(history, sessions, raw_observations, check_d)          # 5
    rec = _new_record(check, resume_after, resume, floor, request_id, request_hash, request_basis, requested_at)
    events = history.events                                                                # 6
    events.append(copy.deepcopy(rec))
    candidate = History.from_dict(history_dict(events))
    cand_check = _check_candidate(history, check, view, candidate, rec, resume_after)      # 7
    basis = {
        "operation": OPERATION, "status": READY, "history_digest": check.history_digest,
        "expected_head_seq": check.head_seq, "expected_head_hash": check.head_hash,
        "expected_state_digest": check.state_digest, "resume_after": resume_after, "check_d": check_d,
        "request_id": request_id, "request_hash": request_hash, "reason_code": REASON, "requested_at": requested_at,
        "floor": floor, "boundary_session": session_dict(resume), "ledger_digest": ledger.ledger_digest,
        "sessions_digest": sessions_digest(sl), "effective_digest": ledger.effective_digest,
        "candidate_history": candidate.to_dict(), "candidate_digest": candidate.digest,
        "candidate_state_digest": cand_check.state_digest}
    return basis, candidate
