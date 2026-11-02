"""The records the restore makes, as drafts (design 6.1-6.3): the working list after the restore point, in the order of
the operations, with every content item calculated and no hash yet.

A draft carries its new seq and the seq its parent will have; the audit hashes and the hashes inside references are
filled in later, when the RECOVERY_RESTORE record is fixed and the records are chained after it. The working list is a
draft of this call only: it is neither a History nor a checked chain.

Nothing about the strategy is written here: an APPLY is calculated by the unchanged apply_transition from the new
effective parent's state and the saved inputs, and the saved decision, the saved rows and the saved previous session
date are carried over as they are.
"""
import copy

from v2_core.errors import InputError
from v2_core.fixture import MarketRow
from v2_core.observations import parse_observation
from v2_core.state import MarketState
from v2_core.transition import apply_transition
from v2_history.common import same
from v2_history.values import ACK, APPLY, DECLARE_MISSING, RESTART_UNKNOWN
from v2_persistence.events import input_hash_of, serialize_transition, session_dict

from .chain import context_mismatch, context_missing, contexts_agree, floor_of, frontier_of, last_segment
from .errors import restore_invalid
from .values import DROP, REAPPLY, REPLAY, RETIRE

_APPLY_FIELDS = ("input_hash", "skipped_sessions", "state_after", "transition_result")


def _row(raw):
    return MarketRow(raw["date"], float(raw["soxx"]), float(raw["sma"]), float(raw["rsi"]), float(raw["shd"]),
                     float(raw["prev_rsi"]))


def _change(op, old, to_seq, same_flag, changed):
    kind = old["kind"]
    if kind in (APPLY, ACK, DECLARE_MISSING):
        d = old["d"]
    elif kind == RESTART_UNKNOWN:
        d = old["resume_after"]
    else:
        d = None
    return {"op": op, "from_seq": old["seq"], "kind": kind, "d": d, "to_seq": to_seq,
            "same_as_superseded": same_flag, "changed_fields": changed}


def _initial_state():
    return MarketState.initial().to_dict()


class Draft:
    """What stage one of the calculation produces."""

    def __init__(self):
        self.records = []          # the created records, in order, without hashes
        self.entries = []          # the `replay` list of the RECOVERY_RESTORE record
        self.changes = []          # the plan's changes, one per operation
        self.fixups = {}           # new seq -> [(field, target seq)]: hashes inside references
        self.created = {}          # old seq -> new seq
        self.reapplied = []        # (old record, new draft), in order
        self.replayed = set()      # the new seqs of the replayed records


def _reapply(work, old, new_seq, sl):
    saved = old["confirmed_inputs"]
    d = old["d"]
    seg = last_segment(work)
    base = seg["applies"][-1]["d"] if seg["applies"] else seg["date"]
    nxt = sl.next(d)
    index = {s.date: i for i, s in enumerate(sl.sessions)}
    if base not in index:
        raise context_missing(d)
    for entry in saved["session_context"]:
        if entry["date"] not in index:
            raise context_missing(d)
    between = [s for s in sl.sessions if base < s.date < d]
    for s in between:
        if not s.confirmed:
            raise InputError("intermediate_session_unconfirmed", "sessions", detail=s.date)
    context = [session_dict(s) for s in sl.sessions[index[base]:index[nxt.date] + 1]]
    if sl.previous(d).date != saved["prev_session_date"] or not contexts_agree(saved["session_context"], context):
        raise context_mismatch(d)
    ci = {"decision": copy.deepcopy(saved["decision"]), "row": copy.deepcopy(saved["row"]),
          "prev_row": copy.deepcopy(saved["prev_row"]), "prev_session_date": saved["prev_session_date"],
          "session_context": context}
    decision = parse_observation(copy.deepcopy(saved["decision"]))
    prev_row = None if saved["prev_row"] is None else _row(saved["prev_row"])
    t = apply_transition(MarketState.from_dict(work[-1]["state_after"]), d, saved["prev_session_date"],
                         _row(saved["row"]), prev_row, decision)
    if t.next_state is None:
        raise restore_invalid("ops", "restore_reapply_input")
    rec = {"kind": APPLY, "seq": new_seq, "parent_seq": new_seq - 1, "parent_hash": None, "d": d,
           "confirmed_inputs": ci, "input_hash": input_hash_of(ci), "skipped_sessions": [s.date for s in between],
           "transition_result": serialize_transition(t), "state_after": t.next_state.to_dict()}
    changed = sorted(name for name in _APPLY_FIELDS if not same(rec[name], old[name]))
    return rec, changed


def _replay_resolution(work, old, new_seq, sl, mapped, fixups):
    new = copy.deepcopy(old)
    new.pop("event_hash", None)
    new.update({"seq": new_seq, "parent_seq": new_seq - 1, "parent_hash": None,
                "replay_of": {"seq": old["seq"], "event_hash": old["event_hash"]},
                "state_after": copy.deepcopy(work[-1]["state_after"])})
    fix = fixups.setdefault(new_seq, [])
    if old["kind"] == ACK:
        applied, missing = old["applied_ref"], old["missing_ref"]
        if applied is not None:
            target = mapped(applied["seq"])
            new["applied_ref"] = {"seq": target, "event_hash": None, "fingerprint": applied["fingerprint"]}
            fix.append(("applied_ref", target))
        if missing is not None:
            target = mapped(missing["seq"])
            new["missing_ref"] = {"kind": missing["kind"], "seq": target, "event_hash": None}
            fix.append(("missing_ref", target))
        names = ("applied_ref", "missing_ref", "state_after")
        # the hashes inside the references are not known yet: the fields of an acknowledgement are listed by
        # settle_changes, from the finished records
    else:
        frontier, saved_session = frontier_of(last_segment(work))
        d = old["d"]
        fs = sl.get(frontier)
        if fs is None:
            raise context_missing(frontier)
        ds = sl.next(frontier)
        if ds is None or ds.date != d:
            raise restore_invalid("ops", "declare_frontier")
        nd = sl.next(d)
        if nd is None:
            raise context_missing(d)
        if not same(session_dict(fs), saved_session):
            raise context_mismatch(frontier)
        new["frontier_before"] = frontier
        new["session_context"] = [session_dict(fs), session_dict(ds), session_dict(nd)]
        names = ("frontier_before", "session_context", "state_after")
    changed = [] if old["kind"] == ACK else sorted(name for name in names if not same(new[name], old[name]))
    return new, changed


def _replay_restart(work, old, new_seq):
    new = copy.deepcopy(old)
    new.pop("event_hash", None)
    floor = floor_of(work)
    resume = old["resume_after"]
    if resume < max(v for v in floor.values() if v is not None):
        raise restore_invalid("ops", "restart_floor")
    if resume > old["request_basis"]["check_d"]:
        raise restore_invalid("ops", "check_d")
    if same(work[-1]["state_after"], _initial_state()) and resume == floor["prev_boundary"]:
        raise restore_invalid("ops", "restart_noop")
    new.update({"seq": new_seq, "parent_seq": new_seq - 1, "parent_hash": None, "floor": floor,
                "replay_of": {"seq": old["seq"], "event_hash": old["event_hash"]},
                "state_after": _initial_state()})
    changed = sorted(name for name in ("floor", "state_after") if not same(new[name], old[name]))
    return new, changed


_ACK_FIELDS = ("applied_ref", "missing_ref", "state_after")


def settle_changes(draft, events, created):
    """The changed fields of every replayed acknowledgement, from the finished records (hashes inside the references
    filled in) against the superseded ones, over the same named items only. A reference that still names the same
    record - a kept one, which keeps its own hash - is not listed; one that follows a re-applied day is."""
    by_seq = {rec["seq"]: rec for rec in created}
    for change in draft.changes:
        if change["op"] == REPLAY and change["kind"] == ACK:
            old, new = events[change["from_seq"]], by_seq[change["to_seq"]]
            change["changed_fields"] = sorted(name for name in _ACK_FIELDS if not same(new[name], old[name]))


def plan_records(events, kept, superseded, plan_ops, sl):
    """The working list after the restore point, operation by operation. kept are the effective seqs up to and
    including the restore point; superseded the ones after it. Returns a Draft."""
    work = [copy.deepcopy(events[s]) for s in kept]
    kept_set = set(kept)
    draft = Draft()
    new_seq = len(events) + 1                         # the RECOVERY_RESTORE record takes len(events)

    def mapped(target):
        if target in draft.created:
            return draft.created[target]
        if target in kept_set:
            return target
        raise restore_invalid("ops", "restore_ref_unmapped")

    for entry, seq in zip(plan_ops, superseded):
        op, old = entry["op"], events[seq]
        if op in (DROP, RETIRE):
            draft.entries.append({"op": op, "from_seq": seq, "d": None, "seq": None, "same_as_superseded": None})
            draft.changes.append(_change(op, old, None, None, []))
            continue
        if op == REAPPLY:
            new, changed = _reapply(work, old, new_seq, sl)
            same_flag = not changed
            draft.entries.append({"op": op, "from_seq": seq, "d": old["d"], "seq": new_seq,
                                  "same_as_superseded": same_flag})
            draft.reapplied.append((old, new))
        else:                                           # REPLAY: the only operation left
            if old["kind"] == RESTART_UNKNOWN:
                new, changed = _replay_restart(work, old, new_seq)
            else:
                new, changed = _replay_resolution(work, old, new_seq, sl, mapped, draft.fixups)
            same_flag = None
            draft.replayed.add(new_seq)
            draft.entries.append({"op": op, "from_seq": seq, "d": None, "seq": new_seq,
                                  "same_as_superseded": None})
        draft.changes.append(_change(op, old, new_seq, same_flag, changed))
        draft.records.append(new)
        draft.created[seq] = new_seq
        work.append(new)
        new_seq += 1
    return draft
