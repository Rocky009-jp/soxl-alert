"""The shared preparation of one restore: the checked inputs, the new records, the candidate History and the plan
basis. prepare_restore_plan runs it once on the given history; confirm_restore_plan runs it again on the original
history and compares the result with the plan's basis.

The order is fixed (design 5): the history, sessions, dates and ledger rows -> check_d, the restore point and the
operations -> requested_at, the request id -> the saved context that stays, the series inputs, and every new content
item -> the hashes and the candidate as a whole -> the evidence of the replayed requests, the facts of the whole
candidate and the rows they leave -> the days that would need a new consumption, the saved decisions, the saved market
inputs -> the final projection of the unchanged B-2 function, then evaluate_day -> the no-effect rule -> the basis.

No market rule, threshold or state formula is written here: the new APPLY records come from the unchanged
apply_transition (records.py), the whole candidate is checked by the unchanged validate_history and projected by the
unchanged project_history_ledger, and every day is compared with the unchanged evaluate_day.
"""
import copy

from v2_core.engine import evaluate_day
from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_core.observations import parse_observation, select_decision
from v2_core.state import MarketState
from v2_history import History, validate_history
from v2_history.common import basis_request_hash, same
from v2_history.values import ACK, DECLARE_MISSING, RECOVERY_RESTORE, RESTART_UNKNOWN, history_dict
from v2_history_ops import project_history_ledger, read_effective
from v2_history_ops.errors import history_request_conflict
from v2_persistence.codec import canonical_json, compute_event_hash, sha256_text
from v2_persistence.errors import PersistenceError
from v2_persistence.events import serialize_transition, session_dict
from v2_recovery.commands import check_commands
from v2_recovery.common import requested_text, valid_request_id
from v2_recovery.facts import LedgerContext
from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest
from v2_recovery.project import apply_records, check_versions

from .chain import context_mismatch, context_missing, facts_of, frontier_of, last_segment
from .errors import candidate_invalid, decision_changed, market_input_changed, no_effect, requires_consume, restore_invalid
from .market import digest_of, series_inputs
from .points import check_ops, check_point
from .records import plan_records, settle_changes
from .values import DROP, OPERATION, READY, REAPPLY, REASON, REPLAY


def requested_at_of(value):
    """The injected aware datetime as fixed UTC text (a clock is never read)."""
    return requested_text(value)


def _check_check_d(check, sl, check_d):
    """check_d is after the current boundary, not before the latest applied day, a confirmed session with a previous and
    a next session (the next one need not be confirmed). The existing errors of the ledger context are reused."""
    if not check_d > check.current_boundary.after:
        raise PersistenceError("target_not_after_boundary", "target_session_date")
    if check.latest_apply_d is not None and check_d < check.latest_apply_d:
        raise InputError("state_ahead_of_target", "state")
    session = sl.get(check_d)
    if session is None:
        raise InputError("target_not_in_sessions", "sessions")
    if not session.confirmed:
        raise InputError("target_unconfirmed", "sessions")
    if sl.next(check_d) is None:
        raise InputError("next_session_missing", "sessions")
    if sl.previous(check_d) is None:
        raise InputError("previous_session_missing", "sessions")


def _check_replayed_boundaries(events, superseded, plan_ops, sl):
    """A restart that is written again keeps its saved boundary session: it must equal the current session of that day."""
    for entry, seq in zip(plan_ops, superseded):
        old = events[seq]
        if entry["op"] == REPLAY and old["kind"] == RESTART_UNKNOWN:
            now = sl.get(old["resume_after"])
            if now is None:
                raise context_missing(old["resume_after"])
            if not same(session_dict(now), old["boundary_session"]):
                raise context_mismatch(old["resume_after"])


def _restore_record(events, check, point, superseded, draft, request_basis, request_hash, requested_at, ledger_text):
    rec = {
        "kind": RECOVERY_RESTORE, "seq": len(events), "prev_hash": check.head_hash, "parent_seq": point["seq"],
        "parent_hash": point["event_hash"], "superseded_seqs": list(superseded), "replay": copy.deepcopy(draft.entries),
        "request_id": request_basis["request_id"], "request_hash": request_hash,
        "request_basis": copy.deepcopy(request_basis), "reason_code": REASON, "requested_at": requested_at,
        "ledger_digest": ledger_text, "state_after": copy.deepcopy(events[point["seq"]]["state_after"])}
    rec["event_hash"] = compute_event_hash(rec)
    return rec


def _chain_after(restore, draft, events, kept):
    """The created records chained after the RECOVERY_RESTORE: each parent is the record before it, and every hash
    inside a reference is the hash of the record it names (a kept record keeps its own)."""
    hashes = {s: events[s]["event_hash"] for s in kept}
    previous = restore["event_hash"]
    out = []
    for rec in draft.records:
        rec["parent_hash"] = previous
        for field, target in draft.fixups.get(rec["seq"], ()):
            rec[field]["event_hash"] = hashes[target]
        rec["event_hash"] = compute_event_hash(rec)
        hashes[rec["seq"]] = rec["event_hash"]
        previous = rec["event_hash"]
        out.append(rec)
    return out


def _check_candidate(history, check, view, candidate, kept, restore, created):
    """The whole candidate (design 6.4): validate_history, then everything of the original is kept as it was."""
    cand_check = validate_history(candidate)
    events, old = candidate.events, history.events
    new = [restore] + created
    if (len(events) != len(old) + len(new) or canonical_json(events[:len(old)]) != canonical_json(old)
            or canonical_json(events[len(old):]) != canonical_json(new)):
        raise candidate_invalid()
    if (list(cand_check.effective_seqs) != list(kept) + [r["seq"] for r in new]
            or list(cand_check.superseded_seqs) != sorted(list(check.superseded_seqs) + restore["superseded_seqs"])
            or len(set(check.superseded_seqs) & set(restore["superseded_seqs"])) != 0
            or not same(candidate.current_state, new[-1]["state_after"])
            or cand_check.state_digest != sha256_text(canonical_json(new[-1]["state_after"]))
            or cand_check.migrated != check.migrated
            or read_effective(candidate).migration_seq != view.migration_seq):
        raise candidate_invalid()
    return cand_check, events


def _replay_evidence(chain, created_seqs, sl, raw_observations, check_d):
    """Every replayed request is checked again as a whole against the effective records before it (design 7, steps
    2-3): the unchanged check_commands over the real facts of that prefix, with the commands as they are now written."""
    j = 0
    while j < len(chain):
        rec = chain[j]
        if rec["kind"] in (ACK, DECLARE_MISSING) and rec["seq"] in created_seqs and rec["command_index"] == 0:
            group = chain[j:j + rec["command_count"]]
            prefix = chain[:j]
            ctx = LedgerContext.from_facts(facts_of(prefix, prefix[-1]["seq"]), sl, raw_observations, check_d)
            existing = [r for r in prefix if r["kind"] in (ACK, DECLARE_MISSING)]
            commands = [{"kind": r["kind"], "variant": r["variant"], "d": r["d"],
                         "record_fingerprints": sorted(r["record_fingerprints"]),
                         "applied_ref": copy.deepcopy(r["applied_ref"]), "missing_ref": copy.deepcopy(r["missing_ref"])}
                        for r in group]
            extras = check_commands(ctx, existing, commands)
            for r, (frontier, context) in zip(group, extras):
                if not same(r["frontier_before"], frontier) or not same(r["session_context"], context):
                    raise restore_invalid("ops", "declare_frontier")
            j += len(group)
        else:
            j += 1


def _prior_rows(chain, head_seq, sl, raw_observations, check_d):
    """The facts of the whole candidate and the rows they leave (design 7, step 4): the exclusions, then the supplements,
    then the refusal of a version choice, in the order of the unchanged functions. It is only the set the final
    projection must give; it is never returned as a checked ledger."""
    facts = facts_of(chain, head_seq)
    ctx = LedgerContext.from_facts(facts, sl, raw_observations, check_d)
    existing = [r for r in chain if r["kind"] in (ACK, DECLARE_MISSING)]
    remaining, actually, supplemented = apply_records(ctx, existing)
    check_versions(ctx, remaining, actually, "resolutions")
    rows = sorted((r.cols for r in remaining.values()), key=canonical_json)
    return facts, rows, sorted(actually), supplemented


def _frontiers_before_restarts(events, effective):
    """For each restart of the original effective list: the frontier of the segment it closes."""
    out = {}
    for i, seq in enumerate(effective):
        if events[seq]["kind"] == RESTART_UNKNOWN:
            out[seq] = frontier_of(last_segment([events[s] for s in effective[:i]]))[0]
    return out


def _released_days(events, effective, superseded, plan_ops, draft, sl, apply_days):
    """The days that the operations free of a record that had passed over them (design 8): the declared day of a dropped
    declaration, the sessions a dropped restart had skipped, and the sessions a re-applied day newly skips."""
    days = set()
    frontiers = None
    for entry, seq in zip(plan_ops, superseded):
        old = events[seq]
        if entry["op"] == DROP and old["kind"] == DECLARE_MISSING:
            days.add(old["d"])
        elif entry["op"] == DROP and old["kind"] == RESTART_UNKNOWN:
            if frontiers is None:
                frontiers = _frontiers_before_restarts(events, effective)
            days.update(s.date for s in sl.sessions if frontiers[seq] < s.date <= old["resume_after"])
    for old, new in draft.reapplied:
        days.update(set(new["skipped_sessions"]) - set(old["skipped_sessions"]))
    known = {s.date for s in sl.sessions}
    return sorted(d for d in days if d in known and d not in apply_days)


def _check_new_days(rows, sl, days):
    for d in days:
        if select_decision(copy.deepcopy(rows), sl, d) is not None:
            raise requires_consume(d)


def _check_saved_decisions(rows, sl, draft):
    for old, new in draft.reapplied:
        saved = parse_observation(copy.deepcopy(old["confirmed_inputs"]["decision"]))
        chosen = select_decision(copy.deepcopy(rows), sl, old["d"])
        if chosen is None or chosen.record_id != saved.record_id or chosen.fingerprint() != saved.fingerprint():
            raise decision_changed(old["d"])


def _check_saved_market(items, draft):
    for (old, _new), item in zip(draft.reapplied, items):
        saved = old["confirmed_inputs"]
        if (not same(item["row"], saved["row"]) or not same(item["prev_row"], saved["prev_row"])
                or item["prev_session_date"] != saved["prev_session_date"]):
            raise market_input_changed(old["d"])


def _check_days_again(chain, ledger, cuts, sl, draft):
    """Each re-applied day goes through the unchanged evaluate_day on its new parent state, the same cut of the series
    and the final ledger; the transition and the next state must be the ones that were calculated from the saved
    inputs. Done only after the final projection has accepted the candidate."""
    index = {r["seq"]: i for i, r in enumerate(chain)}
    for _old, new in draft.reapplied:
        parent = chain[index[new["seq"]] - 1]
        day = evaluate_day(MarketState.from_dict(parent["state_after"]), new["d"], cuts[new["d"]], sl,
                           ledger.raw_observations())
        if (not same(serialize_transition(day), new["transition_result"])
                or not same(day.next_state.to_dict(), new["state_after"])):
            raise candidate_invalid()


def build_restore(history, restore_point, ops, sessions, raw_observations, series, check_d, request_id, when):
    """Returns (basis, candidate). when() gives the requested_at text; it is asked for after the inputs are read, so
    that an error of the history, sessions, dates or ledger rows comes first."""
    check = validate_history(history)                                                      # 1
    sl = copy_sessions(sessions)
    parse_iso_date(check_d, "target_session_date")
    ledger_rows = parse_ledger(raw_observations)
    view = read_effective(history)
    events = history.events
    _check_check_d(check, sl, check_d)                                                     # 2
    pos, superseded = check_point(check, view, events, restore_point)
    plan_ops = check_ops(events, superseded, ops)
    requested_at = when()                                                                  # 3
    if not valid_request_id(request_id):
        raise restore_invalid("request_id", "request_id")
    if any(g["request_id"] == request_id for g in view.requests):
        raise history_request_conflict()
    effective = list(check.effective_seqs)                                                 # 4
    kept = effective[:pos + 1]
    prefix = [events[s] for s in kept]
    LedgerContext.from_facts(facts_of(prefix, prefix[-1]["seq"]), sl, raw_observations, check_d)
    _check_replayed_boundaries(events, superseded, plan_ops, sl)
    olds = [events[e["from_seq"]] for e in plan_ops if e["op"] == REAPPLY]
    items, cuts = series_inputs(series, sl, olds) if olds else ([], {})
    draft = plan_records(events, kept, superseded, plan_ops, sl)
    point = {"seq": restore_point["seq"], "event_hash": restore_point["event_hash"]}
    request_basis = {"request_id": request_id, "restore_point": point, "ops": copy.deepcopy(plan_ops),
                     "check_d": check_d, "reason_code": REASON, "requested_at": requested_at}
    request_hash = basis_request_hash(request_basis)
    ledger_text = ledger_digest(ledger_rows)
    restore = _restore_record(events, check, point, superseded, draft, request_basis, request_hash, requested_at,
                              ledger_text)                                                 # 5
    created = _chain_after(restore, draft, events, kept)
    settle_changes(draft, events, created)
    candidate = History.from_dict(history_dict(events + [restore] + created))
    cand_check, cand_events = _check_candidate(history, check, view, candidate, kept, restore, created)
    chain = [cand_events[s] for s in cand_check.effective_seqs]
    _replay_evidence(chain, draft.replayed, sl, raw_observations, check_d)                       # 6
    facts, prior, _excluded, _supplemented = _prior_rows(chain, cand_check.head_seq, sl, raw_observations, check_d)
    _check_new_days(prior, sl, _released_days(events, effective, superseded, plan_ops, draft, sl, facts.apply_days))
    _check_saved_decisions(prior, sl, draft)                                               # 7
    _check_saved_market(items, draft)
    ledger = project_history_ledger(candidate, sessions, raw_observations, check_d)        # 8
    if (not same(ledger.rows, prior) or ledger.effective_digest != sha256_text(canonical_json(prior))
            or ledger.ledger_digest != ledger_text):
        raise candidate_invalid()
    _check_days_again(chain, ledger, cuts, sl, draft)
    if not any(e["op"] == DROP for e in plan_ops) and all(e["same_as_superseded"] is not False
                                                           for e in draft.entries if e["op"] == REAPPLY):
        raise no_effect()
    basis = {
        "operation": OPERATION, "status": READY, "history_digest": check.history_digest,
        "expected_head_seq": check.head_seq, "expected_head_hash": check.head_hash,
        "expected_state_digest": check.state_digest, "restore_point": point, "ops": copy.deepcopy(plan_ops),
        "check_d": check_d, "request_id": request_id, "request_hash": request_hash, "reason_code": REASON,
        "requested_at": requested_at, "ledger_digest": ledger_text, "sessions_digest": sessions_digest(sl),
        "series_inputs": items, "series_digest": digest_of(items), "effective_digest": ledger.effective_digest,
        "candidate_history": candidate.to_dict(), "candidate_digest": candidate.digest,
        "candidate_state_digest": cand_check.state_digest, "candidate_records": [restore] + created,
        "changes": draft.changes}
    return basis, candidate
