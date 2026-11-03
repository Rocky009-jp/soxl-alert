"""The restore point and the operation list (design 4): the checks of the caller's request, in a fixed order."""
from v2_history.common import is_hex64, is_int
from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE, RESTART_UNKNOWN

from .errors import restore_invalid
from .values import DROP, OP_KEYS, OPS, POINT_KEYS, REAPPLY, REPLAY, RETIRE

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
    """The operations, one per superseded record in the same order. Nothing is sorted, completed or defaulted.
    Returns a fresh list of {op, from_seq}."""
    if type(ops) is not list:
        raise restore_invalid("ops", "ops_shape")
    norm = []
    for entry in ops:
        if not isinstance(entry, dict) or not isinstance(entry.get("op"), str):
            raise restore_invalid("ops", "ops_shape")
        if entry["op"] not in OPS:                              # CONSUME, with any keys, and every unknown name
            raise restore_invalid("ops", "restore_op_unsupported")
        if set(entry) != OP_KEYS or not is_int(entry["from_seq"]):
            raise restore_invalid("ops", "ops_shape")
        norm.append({"op": entry["op"], "from_seq": entry["from_seq"]})
    if [e["from_seq"] for e in norm] != list(superseded):
        raise restore_invalid("ops", "superseded_mismatch")
    by_request = {}
    for entry, seq in zip(norm, superseded):
        kind = events[seq]["kind"]
        if entry["op"] not in _ALLOWED.get(kind, ()):
            raise restore_invalid("ops", "restore_op_kind")
        if kind in (ACK, DECLARE_MISSING):
            by_request.setdefault(events[seq]["request_id"], set()).add(entry["op"])
    if any(len(chosen) > 1 for chosen in by_request.values()):
        raise restore_invalid("ops", "restore_partial_batch")
    return norm
