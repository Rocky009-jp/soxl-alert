"""New commands: the evidence each needs (checked against the current ledger and the checked saved inputs), and the
records they become. Nothing is stored; a record is a value in a candidate ResolutionSet.

Rules named here are the fixed identifiers of resolution_invalid: command_shape, ack_evidence, exclude_applied,
late_missing_ref, declare_frontier, declare_applied, declare_unconfirmed, declare_valid_decision, declare_incomplete.
"""
import copy

from v2_core.errors import ConflictError, InputError
from v2_core.observations import select_decision
from v2_persistence.codec import canonical_json
from v2_persistence.errors import PersistenceError
from v2_persistence.events import session_dict

from .common import KIND_ACK, KIND_DECLARE, V_ADDED, V_CHANGED, V_ROW_REMOVED, record_hash_of, record_reason
from .errors import resolution_invalid
from .ledger import in_window
from .project import apply_records
from .values import SCHEMA


def _fail(rule):
    return resolution_invalid("commands", rule)


def _key(ref):
    return canonical_json(ref)


def _related(ctx, row, d):
    """An observed decision that targets D or lies inside D's decision window."""
    session, nxt = ctx.sl.get(d), ctx.sl.next(d)
    if session is None or nxt is None:
        raise PersistenceError("session_context_missing", "sessions", detail=d)
    o = row.obs
    if o.role != "decision" or o.status != "observed":
        return False
    return o.target_date == d or in_window(o, session, nxt)


def _check_applied_ref(ctx, cmd):
    ref = cmd["applied_ref"]
    ap = ctx.sv.by_seq.get(ref["seq"])
    if (ap is None or ref["event_hash"] != ap.event_hash or ref["fingerprint"] != ap.fingerprint
            or cmd["d"] != ap.d):
        raise _fail("ack_evidence")
    return ap


def _rows_of(ctx, cmd):
    rows = []
    for fp in cmd["record_fingerprints"]:
        row = ctx.all_by_fp.get(fp)
        if row is None:
            raise _fail("ack_evidence")
        rows.append(row)
    return rows


def _check_added(ctx, cmd, orig_refs):
    ap = _check_applied_ref(ctx, cmd)
    rows = _rows_of(ctx, cmd)
    if not rows:
        raise _fail("ack_evidence")
    for r in rows:
        if r.obs.record_id == ap.record_id or not _related(ctx, r, cmd["d"]):
            raise _fail("ack_evidence")
    if ap.fingerprint not in ctx.all_by_fp and _key(cmd["applied_ref"]) not in orig_refs:
        raise _fail("ack_evidence")


def _check_changed(ctx, cmd):
    ap = _check_applied_ref(ctx, cmd)
    rows = _rows_of(ctx, cmd)
    if not rows:
        raise _fail("ack_evidence")
    for r in rows:
        if r.obs.record_id != ap.record_id or r.fp == ap.fingerprint:
            raise _fail("ack_evidence")


def _check_row_removed(ctx, cmd, union_excl):
    ap = _check_applied_ref(ctx, cmd)
    if cmd["record_fingerprints"] or ap.fingerprint in ctx.all_by_fp:
        raise _fail("ack_evidence")
    for r in ctx.rows:
        if r.obs.record_id == ap.record_id and r.fp not in union_excl:
            raise _fail("ack_evidence")             # an unacknowledged changed version of the same row


def _check_late(ctx, cmd, existing):
    if cmd["applied_ref"] is not None:
        raise _fail("ack_evidence")
    ref = cmd["missing_ref"]
    if ref is None:
        raise _fail("late_missing_ref")
    d = cmd["d"]
    if d in ctx.sv.apply_days:
        raise _fail("late_missing_ref")
    if ref["kind"] == "APPLY":
        ap = ctx.sv.by_seq.get(ref["seq"])
        if ap is None or ref["event_hash"] != ap.event_hash or d not in ap.skipped:
            raise _fail("late_missing_ref")
    else:
        if not any(rec["kind"] == KIND_DECLARE and rec["resolution_seq"] == ref["resolution_seq"]
                   and rec["resolution_hash"] == ref["resolution_hash"] and rec["d"] == d for rec in existing):
            raise _fail("late_missing_ref")
    rows = _rows_of(ctx, cmd)
    if not rows:
        raise _fail("ack_evidence")
    for r in rows:
        if not _related(ctx, r, d):
            raise _fail("ack_evidence")


def _check_declare(ctx, cmd, declared_dates, rem0):
    """Returns (frontier, session_context). A declaration is eligible only when D has no decision (0 rows) or a
    related disturbance; one valid decision is refused. Rows are judged after the existing set, before this one."""
    sv, sl, d = ctx.sv, ctx.sl, cmd["d"]
    if d > ctx.check_d:
        raise _fail("declare_frontier")
    if d in sv.apply_days:
        raise _fail("declare_applied")
    latest = sv.latest_apply_day(sv.head_seq)
    frontier = max([latest] + declared_dates)
    fs = sl.get(frontier)
    if fs is None:
        raise PersistenceError("session_context_missing", "sessions", detail=frontier)
    ds = sl.next(frontier)
    if ds is None or ds.date != d:
        raise _fail("declare_frontier")
    nd = sl.next(d)
    if not ds.confirmed or not fs.confirmed or nd is None:
        raise _fail("declare_unconfirmed")
    related = [fp for fp, r in rem0.items() if _related(ctx, r, d)]
    ids = {rem0[fp].obs.record_id for fp in related}
    scope = [r.cols for r in rem0.values() if r.fp in related or r.obs.record_id in ids]
    try:
        chosen = select_decision(copy.deepcopy(scope), sl, d)
    except (InputError, ConflictError):
        chosen = None                               # a disturbance that belongs to D: a declaration may name it
    if chosen is not None:
        raise _fail("declare_valid_decision")
    if sorted(related) != cmd["record_fingerprints"]:
        raise _fail("declare_incomplete")
    return frontier, [session_dict(fs), session_dict(ds), session_dict(nd)]


def make_records(ctx, existing, commands, basis, request_hash):
    """Evidence for all commands, then the new records (not yet hashed into a set)."""
    sv = ctx.sv
    for cmd in commands:
        if cmd["kind"] == KIND_ACK and cmd["d"] > ctx.check_d:
            raise _fail("ack_evidence")
        if any(fp in sv.fixed_fps for fp in cmd["record_fingerprints"]):
            raise _fail("exclude_applied")
    orig_refs = {_key(r["applied_ref"]) for r in existing
                 if r["kind"] == KIND_ACK and r["variant"] in (V_CHANGED, V_ROW_REMOVED)}
    orig_refs |= {_key(c["applied_ref"]) for c in commands
                  if c["kind"] == KIND_ACK and c["variant"] in (V_CHANGED, V_ROW_REMOVED)
                  and c["applied_ref"] is not None}
    union_excl = {fp for r in existing for fp in r["record_fingerprints"]}
    union_excl |= {fp for c in commands for fp in c["record_fingerprints"]}
    declared = [r["d"] for r in existing if r["kind"] == KIND_DECLARE]
    rem0, _, _ = apply_records(ctx, existing)
    extras = []
    for cmd in commands:
        extra = (None, None)
        if cmd["kind"] == KIND_ACK:
            v = cmd["variant"]
            if v == V_ADDED:
                if cmd["applied_ref"] is None or cmd["missing_ref"] is not None:
                    raise _fail("ack_evidence")
                _check_added(ctx, cmd, orig_refs)
            elif v == V_CHANGED:
                if cmd["applied_ref"] is None or cmd["missing_ref"] is not None:
                    raise _fail("ack_evidence")
                _check_changed(ctx, cmd)
            elif v == V_ROW_REMOVED:
                if cmd["applied_ref"] is None or cmd["missing_ref"] is not None:
                    raise _fail("ack_evidence")
                _check_row_removed(ctx, cmd, union_excl)
            else:
                _check_late(ctx, cmd, existing)
        else:
            extra = _check_declare(ctx, cmd, declared, rem0)
            declared.append(cmd["d"])
        extras.append(extra)

    prev_hash = existing[-1]["resolution_hash"] if existing else None
    out = []
    for i, (cmd, (frontier, context)) in enumerate(zip(commands, extras)):
        rec = {
            "resolution_seq": len(existing) + i + 1, "parent_resolution_hash": prev_hash, "resolution_hash": None,
            "request_id": basis["request_id"], "request_hash": request_hash,
            "request_basis": copy.deepcopy(basis), "command_index": i, "command_count": len(commands),
            "kind": cmd["kind"], "variant": cmd["variant"], "d": cmd["d"],
            "source_head_seq": sv.head_seq, "source_head_hash": sv.head_hash,
            "state_after": copy.deepcopy(sv.events[sv.head_seq]["state_after"]),
            "record_fingerprints": list(cmd["record_fingerprints"]),
            "applied_ref": copy.deepcopy(cmd["applied_ref"]), "missing_ref": copy.deepcopy(cmd["missing_ref"]),
            "session_context": context, "frontier_before": frontier, "ledger_digest": ctx.ledger_digest,
            "reason_code": record_reason(cmd["kind"]), "requested_at": basis["requested_at"]}
        rec["resolution_hash"] = record_hash_of(rec)
        prev_hash = rec["resolution_hash"]
        out.append(rec)
    return out


def set_dict(records):
    return {"schema": SCHEMA, "head_resolution_seq": len(records),
            "head_resolution_hash": records[-1]["resolution_hash"] if records else None,
            "records": copy.deepcopy(records)}
