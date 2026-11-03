"""The restore point and the operation list (design 4): the checks of the caller's request, in a fixed order."""
from v2_history.common import is_date, is_hex64, is_int
from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE, RESTART_UNKNOWN

from .errors import restore_invalid
from .values import CONSUME, CONSUME_KEYS, DROP, OP_KEYS, OPS, POINT_KEYS, REAPPLY, REPLAY, RETIRE

_ALLOWED = {APPLY: (REAPPLY,), ACK: (REPLAY, DROP), DECLARE_MISSING: (REPLAY, DROP),
            RESTART_UNKNOWN: (REPLAY, DROP), RECOVERY_RESTORE: (RETIRE,)}


def check_point(check, view, events, point):
    """The restore point P: a valid effective record, not the physical head, not before a migration, not in the middle
    of a request batch. Returns (P's position in the effective list, the effective seqs after P in order)."""
    if (not isinstance(point, dict) or set(point) != POINT_KEYS or not is_int(point["seq"]) or point["seq"] < 0
            or not is_hex64(point["event_hash"])):
        raise restore_invalid("restore_point", "restore_point_shape")
    effective = list(check.effective_seqs)
    seq = point["seq"]
    if seq not in effective:                                   # superseded, or not a record of this history
        raise restore_invalid("restore_point", "restore_point_not_effective")
    if seq == check.head_seq:
        raise restore_invalid("restore_point", "restore_noop")
    if point["event_hash"] != events[seq]["event_hash"]:
        raise restore_invalid("restore_point", "restore_point_mismatch")
    migration = view.migration_seq
    if migration is not None and seq < migration:
        raise restore_invalid("restore_point", "restore_before_migration")
    taken = [s for s in effective if events[s]["kind"] == RECOVERY_PREFIX_ADOPTION]
    if taken and seq < taken[-1]:
        raise restore_invalid("restore_point", "restore_before_adoption")
    rec = events[seq]
    if rec["kind"] in (ACK, DECLARE_MISSING) and rec["command_index"] < rec["command_count"] - 1:
        raise restore_invalid("restore_point", "restore_point_in_batch")
    pos = effective.index(seq)
    return pos, effective[pos + 1:]


def check_ops(events, superseded, ops):
    """The operations: one per superseded record in the same order, and CONSUME entries between them wherever the caller
    names them. Nothing is sorted, completed or defaulted. Returns a fresh list of {op, from_seq} and {op, d}.

    The order of the checks: the form of every entry; then, over the entries that name a superseded record (CONSUME left
    out), the list, the kinds and the request batches as before; then the three rules of CONSUME that need no ledger."""
    if type(ops) is not list:
        raise restore_invalid("ops", "ops_shape")
    norm = []
    for entry in ops:
        if not isinstance(entry, dict) or not isinstance(entry.get("op"), str):
            raise restore_invalid("ops", "ops_shape")
        if entry["op"] == CONSUME:
            if set(entry) != CONSUME_KEYS or not is_date(entry["d"]):
                raise restore_invalid("ops", "ops_shape")
            norm.append({"op": CONSUME, "d": entry["d"]})
            continue
        if entry["op"] not in OPS:                              # every unknown name, with any keys
            raise restore_invalid("ops", "restore_op_unsupported")
        if set(entry) != OP_KEYS or not is_int(entry["from_seq"]):
            raise restore_invalid("ops", "ops_shape")
        norm.append({"op": entry["op"], "from_seq": entry["from_seq"]})
    named = [e for e in norm if e["op"] != CONSUME]
    if [e["from_seq"] for e in named] != list(superseded):
        raise restore_invalid("ops", "superseded_mismatch")
    by_request = {}
    for entry, seq in zip(named, superseded):
        kind = events[seq]["kind"]
        if entry["op"] not in _ALLOWED.get(kind, ()):
            raise restore_invalid("ops", "restore_op_kind")
        if kind in (ACK, DECLARE_MISSING):
            by_request.setdefault(events[seq]["request_id"], set()).add(entry["op"])
    if any(len(chosen) > 1 for chosen in by_request.values()):
        raise restore_invalid("ops", "restore_partial_batch")
    _check_consumes(events, superseded, norm)
    return norm


def _check_consumes(events, superseded, norm):
    """A CONSUME is not the day of a superseded APPLY (that day is re-applied or dropped, never made anew), is named once,
    and does not stand between two operations on the records of one request. The reported day is the CONSUME's."""
    applied = {events[s]["d"] for s in superseded if events[s]["kind"] == APPLY}
    seen, owners = set(), []                   # owners: the request of each place; None for a record of no request
    for entry in norm:
        if entry["op"] == CONSUME:
            if entry["d"] in applied:
                raise restore_invalid("ops", "restore_consume_applied_day", detail=entry["d"])
            if entry["d"] in seen:
                raise restore_invalid("ops", "restore_consume_duplicate", detail=entry["d"])
            seen.add(entry["d"])
            owners.append(CONSUME)
        else:
            ev = events[entry["from_seq"]]
            owners.append(ev["request_id"] if ev["kind"] in (ACK, DECLARE_MISSING) else None)
    for i, entry in enumerate(norm):
        if entry["op"] == CONSUME:
            before = {o for o in owners[:i] if o not in (None, CONSUME)}
            after = {o for o in owners[i + 1:] if o not in (None, CONSUME)}
            if before & after:
                raise restore_invalid("ops", "restore_consume_in_batch", detail=entry["d"])
