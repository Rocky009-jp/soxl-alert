"""RECOVERY_RESTORE records: restore point, superseded list, operations and the batch of records that follows
(design 8.1-8.6). Only the form and the facts of the batch are checked here; the created records must also pass the
ordinary view rules (view.py) in the chain views that contain them.

CONSUME (stage C-1) is a new APPLY for a day that the operations set free of a record that had passed over it. Only its
form, place and day are checked here: the day is not the day of a superseded APPLY, it is named once, it does not stand
inside one request batch, and the record it made is an APPLY of that day. Which days are free, and which decision and
market values the new APPLY was made with, need the ledger, the sessions and the series, so they are the plan's matter
(v2_history_restore), as the decisions and market values of a REAPPLY are. The created APPLY passes the ordinary rules of
the chain view like any other. RECOVERY_PREFIX_ADOPTION cannot be restored before (restore_before_adoption).
"""
from v2_recovery.common import is_requested_text, valid_request_id

from .common import basis_request_hash, is_date, is_hex64, is_int, same
from .errors import history_invalid
from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,
                     RESTART_UNKNOWN, SCHEMA_MIGRATION)

REASON_RESTORE = "RESTORE_VERIFIED_RECORD"
BASIS_KEYS = frozenset(["request_id", "restore_point", "ops", "check_d", "reason_code", "requested_at"])
REPLAY_KEYS = frozenset(["op", "from_seq", "d", "seq", "same_as_superseded"])

REAPPLY, REPLAY, DROP, RETIRE, CONSUME = "REAPPLY", "REPLAY", "DROP", "RETIRE", "CONSUME"
_ALLOWED = {APPLY: (REAPPLY,), ACK: (REPLAY, DROP), DECLARE_MISSING: (REPLAY, DROP), RESTART_UNKNOWN: (REPLAY, DROP),
            RECOVERY_RESTORE: (RETIRE,)}
_ALL_OPS = (REAPPLY, REPLAY, DROP, RETIRE)

_COPIED = {
    ACK: ("request_id", "request_hash", "request_basis", "command_index", "command_count", "reason_code",
          "requested_at", "ledger_digest", "origin", "record_fingerprints", "variant", "d"),
    DECLARE_MISSING: ("request_id", "request_hash", "request_basis", "command_index", "command_count", "reason_code",
                      "requested_at", "ledger_digest", "origin", "record_fingerprints", "variant", "d"),
    RESTART_UNKNOWN: ("request_id", "request_hash", "request_basis", "reason_code", "requested_at", "resume_after",
                      "boundary_session")}


def _bad(rule):
    return history_invalid(rule)


def chain_to(parents, seq):
    """Seqs from GENESIS to `seq` along effective parents, ascending."""
    out = []
    cur = seq
    while cur is not None:
        out.append(cur)
        cur = parents[cur]
    out.reverse()
    return out


def contexts_agree(a, b):
    """The session ranges of two APPLY records for the same D: every shared date equal; next(D), the last entry of
    each, compared by date and open_at only (as the S1 projection does)."""
    if not (isinstance(a, list) and isinstance(b, list) and a and b
            and all(isinstance(e, dict) and "date" in e for e in a + b)):
        return False
    last = {a[-1]["date"], b[-1]["date"]}
    ma, mb = {e["date"]: e for e in a}, {e["date"]: e for e in b}
    for date in ma.keys() & mb.keys():
        ea, eb = ma[date], mb[date]
        if date in last:
            if ea.get("open_at") != eb.get("open_at"):
                return False
        elif not same(ea, eb):
            return False
    return True


def _scan_chain(events, chain):
    """Segment boundary date (the last GENESIS / RESTART) and the latest APPLY day of a chain."""
    boundary, latest = None, None
    for s in chain:
        ev = events[s]
        if ev["kind"] == GENESIS:
            boundary = ev["start_after"]
        elif ev["kind"] == RESTART_UNKNOWN:
            boundary = ev["resume_after"]
        elif ev["kind"] == APPLY and (latest is None or ev["d"] > latest):
            latest = ev["d"]
    return boundary, latest


def check_restores(events, parents, migration_seq):
    """Check every RECOVERY_RESTORE and its batch. Returns {created seq: replay_of} for REPLAY-created records."""
    replayed = {}
    for k, rec in enumerate(events):
        if rec["kind"] == RECOVERY_RESTORE:
            _check_one(events, parents, migration_seq, k, rec, replayed)
    for ev in events:
        if ev["kind"] in (ACK, DECLARE_MISSING, RESTART_UNKNOWN):
            if not same(ev["replay_of"], replayed.get(ev["seq"])):
                raise _bad("replay_of")
    return replayed


def _check_one(events, parents, migration_seq, k, rec, replayed):
    point = rec["parent_seq"]
    if point == k - 1:
        raise _bad("restore_noop")
    chain = chain_to(parents, k - 1)
    pos = {s: i for i, s in enumerate(chain)}
    if point not in pos:
        raise _bad("restore_point_not_effective")
    if migration_seq is not None and point < migration_seq:
        raise _bad("restore_before_migration")
    adoptions = [s for s in chain if events[s]["kind"] == RECOVERY_PREFIX_ADOPTION]
    if adoptions and point < adoptions[-1]:
        raise _bad("restore_before_adoption")
    p_rec = events[point]
    if (p_rec["kind"] in (ACK, DECLARE_MISSING) and is_int(p_rec["command_index"])
            and is_int(p_rec["command_count"]) and p_rec["command_index"] < p_rec["command_count"] - 1):
        raise _bad("restore_point_in_batch")
    if not same(rec["state_after"], p_rec["state_after"]):
        raise _bad("restore_state")
    superseded = chain[pos[point] + 1:]
    listed = rec["superseded_seqs"]
    if not isinstance(listed, list) or not all(is_int(s) for s in listed) or listed != superseded:
        raise _bad("superseded_mismatch")
    _check_basis(events, rec, point, p_rec, chain)
    ops = rec["request_basis"]["ops"]
    replay = rec["replay"]
    if not isinstance(replay, list) or not isinstance(ops, list):
        raise _bad("restore_replay_mismatch")
    if len(replay) != len(ops):
        raise _bad("restore_replay_mismatch")
    for entry in replay:
        if not isinstance(entry, dict) or set(entry) != REPLAY_KEYS:
            raise _bad("restore_replay_mismatch")
    named = []                               # (replay entry, ops entry) of the operations that name a superseded record
    for entry, op_entry in zip(replay, ops):
        if entry["op"] != CONSUME:
            named.append((entry, op_entry))
            continue
        if entry["from_seq"] is not None or entry["same_as_superseded"] is not None or not is_date(entry["d"]):
            raise _bad("restore_replay_mismatch")
        if not same(op_entry, {"op": CONSUME, "d": entry["d"]}):
            raise _bad("request_basis")
    if len(named) != len(superseded):
        raise _bad("restore_replay_mismatch")
    for (entry, op_entry), s in zip(named, superseded):
        if entry["op"] not in _ALL_OPS or entry["op"] not in _ALLOWED[events[s]["kind"]]:
            raise _bad("restore_op_kind")
        if entry["from_seq"] != s or not is_int(entry["from_seq"]):
            raise _bad("restore_replay_mismatch")
        if not same(op_entry, {"op": entry["op"], "from_seq": entry["from_seq"]}):
            raise _bad("request_basis")
    _check_batch_ops(events, [entry for entry, _op in named], superseded)
    _check_consumes(events, replay, superseded)
    _check_window(events, k, replay, superseded, point, pos, replayed)


def _check_basis(events, rec, point, p_rec, chain):
    basis = rec["request_basis"]
    if not isinstance(basis, dict) or set(basis) != BASIS_KEYS:
        raise _bad("request_basis")
    if basis["request_id"] != rec["request_id"] or not valid_request_id(rec["request_id"]):
        raise _bad("request_id")
    if not same(basis["restore_point"], {"seq": point, "event_hash": p_rec["event_hash"]}):
        raise _bad("request_basis")
    if basis["reason_code"] != REASON_RESTORE or rec["reason_code"] != REASON_RESTORE:
        raise _bad("reason_code")
    if not is_requested_text(basis["requested_at"]) or basis["requested_at"] != rec["requested_at"]:
        raise _bad("requested_at")
    if not is_hex64(rec["request_hash"]) or rec["request_hash"] != basis_request_hash(basis):
        raise _bad("request_hash")
    if not is_hex64(rec["ledger_digest"]):
        raise _bad("ledger_digest")
    boundary, latest = _scan_chain(events, chain)
    check_d = basis["check_d"]
    if not is_date(check_d) or not check_d > boundary or (latest is not None and not check_d >= latest):
        raise _bad("check_d")
    if not isinstance(basis["ops"], list):
        raise _bad("request_basis")


def _check_batch_ops(events, replay, superseded):
    """A request batch is dropped or replayed as a whole."""
    by_request = {}
    for entry, s in zip(replay, superseded):
        ev = events[s]
        if ev["kind"] in (ACK, DECLARE_MISSING):
            by_request.setdefault(ev["request_id"], set()).add(entry["op"])
    if any(len(ops) > 1 for ops in by_request.values()):
        raise _bad("restore_partial_batch")


def _check_consumes(events, replay, superseded):
    """A CONSUME is not the day of a superseded APPLY, is named once, and does not stand between two operations on the
    records of one request (a batch is dropped or replayed as a whole, and nothing is put inside it)."""
    applied = {events[s]["d"] for s in superseded if events[s]["kind"] == APPLY}
    named = iter(superseded)
    seen, owners = set(), []                  # owners: the request of each place; None for a record of no request
    for entry in replay:
        if entry["op"] == CONSUME:
            if entry["d"] in applied:
                raise _bad("restore_consume_applied_day")
            if entry["d"] in seen:
                raise _bad("restore_consume_duplicate")
            seen.add(entry["d"])
            owners.append(CONSUME)
        else:
            ev = events[next(named)]
            owners.append(ev["request_id"] if ev["kind"] in (ACK, DECLARE_MISSING) else None)
    for i, owner in enumerate(owners):
        if owner == CONSUME:
            before = {o for o in owners[:i] if o not in (None, CONSUME)}
            after = {o for o in owners[i + 1:] if o not in (None, CONSUME)}
            if before & after:
                raise _bad("restore_consume_in_batch")


def _check_window(events, k, replay, superseded, point, pos, replayed):
    created_map, dropped = {}, set()
    plan = []
    n = 0
    named = iter(superseded)
    for entry in replay:
        if entry["op"] == CONSUME:
            created = k + 1 + n
            n += 1
            if entry["seq"] != created or not is_int(entry["seq"]):
                raise _bad("restore_replay_mismatch")
            plan.append((entry, None, created))
            continue
        s = next(named)
        if entry["op"] in (REAPPLY, REPLAY):
            created = k + 1 + n
            n += 1
            if entry["seq"] != created or not is_int(entry["seq"]):
                raise _bad("restore_replay_mismatch")
            created_map[s] = created
            plan.append((entry, s, created))
        else:
            if entry["seq"] is not None or entry["d"] is not None or entry["same_as_superseded"] is not None:
                raise _bad("restore_replay_mismatch")
            dropped.add(s)
    for entry, s, created in plan:
        if created >= len(events):
            raise _bad("restore_incomplete")
        if s is None:                                   # a consumed day: an APPLY of that day
            if events[created]["kind"] != APPLY:
                raise _bad("restore_incomplete")
            if events[created]["d"] != entry["d"]:
                raise _bad("restore_replay_mismatch")
        elif events[created]["kind"] != events[s]["kind"]:
            raise _bad("restore_incomplete")
    point_pos = pos[point]

    def mapped(target):
        if target in created_map:
            return created_map[target]
        if target in dropped or target not in pos or pos[target] > point_pos:
            raise _bad("restore_ref_unmapped")
        return target

    for entry, s, created in plan:
        if s is None:
            continue                                    # a consumed day: the chain view checks it like any APPLY
        old, new = events[s], events[created]
        if entry["op"] == REAPPLY:
            _check_reapply(entry, old, new)
        else:
            _check_replay(entry, old, new, mapped, events)
            replayed[created] = {"seq": old["seq"], "event_hash": old["event_hash"]}


def _check_reapply(entry, old, new):
    if new["d"] != old["d"]:
        raise _bad("restore_reapply_input")
    oi, ni = old["confirmed_inputs"], new["confirmed_inputs"]
    if not isinstance(oi, dict) or not isinstance(ni, dict):
        raise _bad("restore_reapply_input")
    for key in ("decision", "row", "prev_row", "prev_session_date"):
        if not same(oi.get(key), ni.get(key)):
            raise _bad("restore_reapply_input")
    if not contexts_agree(oi.get("session_context"), ni.get("session_context")):
        raise _bad("restore_reapply_input")
    fact = (old["input_hash"] == new["input_hash"] and same(old["skipped_sessions"], new["skipped_sessions"])
            and same(old["transition_result"], new["transition_result"])
            and same(old["state_after"], new["state_after"]))
    if entry["d"] != old["d"] or entry["same_as_superseded"] is not fact:
        raise _bad("restore_replay_mismatch")


def _check_replay(entry, old, new, mapped, events):
    if entry["d"] is not None or entry["same_as_superseded"] is not None:
        raise _bad("restore_replay_mismatch")
    if not same(new["replay_of"], {"seq": old["seq"], "event_hash": old["event_hash"]}):
        raise _bad("replay_of")
    for key in _COPIED[old["kind"]]:
        if not same(old[key], new[key]):
            raise _bad("restore_replay_mismatch")
    if old["kind"] != ACK:
        if old["kind"] == DECLARE_MISSING and (new["applied_ref"] is not None or new["missing_ref"] is not None):
            raise _bad("restore_ref_unmapped")
        return
    applied, missing = old["applied_ref"], old["missing_ref"]
    want_applied = want_missing = None
    if applied is not None:
        target = mapped(applied["seq"])
        want_applied = {"seq": target, "event_hash": events[target]["event_hash"],
                        "fingerprint": applied["fingerprint"]}
    if missing is not None:
        target = mapped(missing["seq"])
        want_missing = {"kind": missing["kind"], "seq": target, "event_hash": events[target]["event_hash"]}
    if not same(new["applied_ref"], want_applied) or not same(new["missing_ref"], want_missing):
        raise _bad("restore_ref_unmapped")
