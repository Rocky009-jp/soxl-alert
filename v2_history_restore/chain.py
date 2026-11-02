"""Readings of a list of effective records (a chain, or a working list of drafts): the segment, the frontier, the
restart floor, and the FixedFacts built from them.

These are the geometry of the records, as the history checker (v2_history) reads it; no market rule, threshold or
state formula is written here. A working list is only a draft inside one call: it is never a History and is never
handed to validate_history or to a ledger projection.
"""
import copy

from v2_history.common import same
from v2_history.values import APPLY, DECLARE_MISSING, GENESIS, RESTART_UNKNOWN
from v2_persistence.errors import PersistenceError
from v2_recovery.facts import FixedFacts


def facts_of(records, head_seq):
    """FixedFacts of a checked chain: every APPLY (all segments), declaration and boundary, in chain order. The skipped
    sessions of an APPLY are the ones its record carries (they were checked with the history)."""
    applies, declares, boundaries = [], [], []
    for rec in records:
        kind = rec["kind"]
        if kind == GENESIS:
            boundaries.append({"date": rec["start_after"], "session": copy.deepcopy(rec["boundary_session"])})
        elif kind == RESTART_UNKNOWN:
            boundaries.append({"date": rec["resume_after"], "session": copy.deepcopy(rec["boundary_session"])})
        elif kind == APPLY:
            ci = rec["confirmed_inputs"]
            applies.append({"seq": rec["seq"], "event_hash": rec["event_hash"], "d": rec["d"],
                            "decision": copy.deepcopy(ci["decision"]), "context": copy.deepcopy(ci["session_context"]),
                            "skipped": list(rec["skipped_sessions"])})
        elif kind == DECLARE_MISSING:
            declares.append({"seq": rec["seq"], "event_hash": rec["event_hash"], "d": rec["d"],
                             "context": copy.deepcopy(rec["session_context"])})
    return FixedFacts.from_parts(applies, declares, boundaries, boundaries[-1]["date"], head_seq)


def last_segment(records):
    """The last segment of a list of records: its boundary date and session, and its APPLY and DECLARE_MISSING."""
    seg = None
    for rec in records:
        kind = rec["kind"]
        if kind == GENESIS:
            seg = {"date": rec["start_after"], "session": rec["boundary_session"], "applies": [], "declares": []}
        elif kind == RESTART_UNKNOWN:
            seg = {"date": rec["resume_after"], "session": rec["boundary_session"], "applies": [], "declares": []}
        elif kind == APPLY:
            seg["applies"].append(rec)
        elif kind == DECLARE_MISSING:
            seg["declares"].append(rec)
    return seg


def frontier_of(seg):
    """The latest of the boundary, APPLY and declaration day of a segment, and the session saved for it."""
    best, session = seg["date"], seg["session"]
    if seg["applies"] and seg["applies"][-1]["d"] > best:
        best, session = seg["applies"][-1]["d"], seg["applies"][-1]["confirmed_inputs"]["session_context"][-2]
    if seg["declares"] and seg["declares"][-1]["d"] > best:
        best, session = seg["declares"][-1]["d"], seg["declares"][-1]["session_context"][1]
    return best, session


def floor_of(records):
    """The restart floor over the whole list (design 6.3)."""
    applies = [r["d"] for r in records if r["kind"] == APPLY]
    declared = [r["d"] for r in records if r["kind"] == DECLARE_MISSING]
    return {"last_apply_d": max(applies) if applies else None,
            "last_declared_d": max(declared) if declared else None,
            "prev_boundary": last_segment(records)["date"]}


def contexts_agree(old, new):
    """Every date the two saved session ranges share is equal; the last entry of each range (next(D)) is compared by
    its date and open time only, as the history checker does."""
    last = {old[-1]["date"], new[-1]["date"]}
    mine = {e["date"]: e for e in old}
    for entry in new:
        other = mine.get(entry["date"])
        if other is None:
            continue
        if entry["date"] in last:
            if other["open_at"] != entry["open_at"]:
                return False
        elif not same(other, entry):
            return False
    return True


def context_missing(d):
    return PersistenceError("session_context_missing", "sessions", detail=d)


def context_mismatch(d):
    return PersistenceError("session_context_mismatch", "sessions", detail=d)
