"""SCHEMA_MIGRATION: the reverse check (design 5.5) and the conversion of S1 + S3-A into schema 2 (design 5.2-5.4).

The reverse check rebuilds the original S1 Snapshot and the S3-A ResolutionSet from the schema-2 records alone and
sends them through the unchanged validate_snapshot / validate_resolutions. Nothing is repaired; a mismatch stops.
"""
import copy

from v2_persistence.codec import CORE_SHA, compute_event_hash, encode_snapshot, sha256_text
from v2_persistence.errors import PersistenceError
from v2_persistence.events import make_apply_event, make_genesis_event, snapshot_of
from v2_persistence.recompute import validate_snapshot
from v2_recovery.commands import set_dict
from v2_recovery.common import is_requested_text, record_hash_of
from v2_recovery import ResolutionSet, validate_resolutions

from .common import basis_request_hash, is_date, is_hex64, is_int, same
from .errors import history_invalid
from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, SCHEMA_MIGRATION

REASON_MIGRATE = "MIGRATE_SCHEMA_1"
BASIS_KEYS = frozenset(["request_id", "source_snapshot_digest", "source_resolutions_digest", "check_d", "reason_code",
                        "requested_at"])
SOURCE_KEYS = frozenset(["schema_version", "core_sha", "head_seq", "head_hash", "snapshot_digest"])
SOURCE_RES_KEYS = frozenset(["schema", "head_resolution_seq", "head_resolution_hash", "digest"])
ORIGIN_KEYS = frozenset(["resolution_seq", "resolution_hash", "source_head_seq", "source_head_hash"])
_MOVED_KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING)


def _bad(rule):
    return history_invalid(rule)


def check_positions(events):
    """Where SCHEMA_MIGRATION may stand and which records carry an origin (design 5.3). Returns its seq or None."""
    found = [i for i, ev in enumerate(events) if ev["kind"] == SCHEMA_MIGRATION]
    if len(found) > 1:
        raise _bad("migration_position")
    m = found[0] if found else None
    for i, ev in enumerate(events):
        if m is not None and i < m and ev["kind"] not in _MOVED_KINDS:
            raise _bad("migration_position")
        if ev["kind"] in (ACK, DECLARE_MISSING):
            migrated = m is not None and i < m
            if (ev["origin"] is not None) != migrated:
                raise _bad("origin")
    return m


def _check_record_shape(mig, events, m):
    basis = mig["request_basis"]
    if not isinstance(basis, dict) or set(basis) != BASIS_KEYS:
        raise _bad("request_basis")
    if basis["request_id"] != mig["request_id"]:
        raise _bad("request_basis")
    if not is_requested_text(basis["requested_at"]) or basis["requested_at"] != mig["requested_at"]:
        raise _bad("requested_at")
    if basis["reason_code"] != REASON_MIGRATE or mig["reason_code"] != REASON_MIGRATE:
        raise _bad("reason_code")
    if not is_hex64(mig["request_hash"]) or mig["request_hash"] != basis_request_hash(basis):
        raise _bad("request_hash")
    if not is_hex64(mig["ledger_digest"]):
        raise _bad("ledger_digest")
    latest = None
    for ev in events[:m]:
        if ev["kind"] == APPLY and (latest is None or ev["d"] > latest):
            latest = ev["d"]
    check_d = basis["check_d"]
    if not is_date(check_d) or not check_d > events[0]["start_after"] or (latest is not None and check_d < latest):
        raise _bad("check_d")
    source, sres = mig["source"], mig["source_resolutions"]
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
        raise _bad("migration_source")
    if not isinstance(sres, dict) or set(sres) != SOURCE_RES_KEYS:
        raise _bad("migration_resolutions")
    if basis["source_snapshot_digest"] != source["snapshot_digest"]:
        raise _bad("migration_source")
    if basis["source_resolutions_digest"] != sres["digest"]:
        raise _bad("migration_resolutions")


def reconstruct(events, m):
    """Rebuild (S1 Snapshot, ResolutionSet) from the records before the SCHEMA_MIGRATION at seq m, with every check of
    design 5.5. Raises history_invalid; returns the pair when the records and the stored correspondence agree."""
    mig = events[m]
    _check_record_shape(mig, events, m)
    moved = events[:m]
    # 1. the S1 events, in order
    v1, v1_pos = [], {}
    for rec in moved:
        if rec["kind"] == GENESIS:
            ev = make_genesis_event(rec["start_after"], rec["boundary_session"])
        elif rec["kind"] == APPLY:
            ev = make_apply_event(len(v1), v1[-1]["event_hash"], rec["d"], rec["confirmed_inputs"],
                                  rec["skipped_sessions"], rec["transition_result"], rec["state_after"])
        else:
            continue
        v1_pos[rec["seq"]] = (len(v1), ev["event_hash"])
        v1.append(ev)
    expected_map = [{"v1_seq": i, "v1_event_hash": ev["event_hash"], "seq": seq}
                    for i, (ev, seq) in enumerate(zip(v1, sorted(v1_pos)))]
    if not same(mig["event_map"], expected_map):
        raise _bad("migration_map")
    snapshot = snapshot_of(v1)
    try:
        validate_snapshot(snapshot)
    except PersistenceError as e:
        raise _bad("s1:%s" % (e.rule or e.code)) from None
    source = mig["source"]
    head = v1[-1]
    if (source["schema_version"] != 1 or source["core_sha"] != CORE_SHA or source["head_seq"] != head["seq"]
            or source["head_hash"] != head["event_hash"]
            or source["snapshot_digest"] != sha256_text(encode_snapshot(snapshot))):
        raise _bad("migration_source")
    # 2. the S3-A records, in order
    recs, inv_res, res_map = [], {}, []
    last_v1 = None
    for rec in moved:
        if rec["seq"] in v1_pos:
            last_v1 = v1_pos[rec["seq"]]
            continue
        origin = rec["origin"]
        if not isinstance(origin, dict) or set(origin) != ORIGIN_KEYS:
            raise _bad("origin")
        if origin["resolution_seq"] != len(recs) + 1 or not is_int(origin["resolution_seq"]):
            raise _bad("origin")
        if last_v1 is None or origin["source_head_seq"] != last_v1[0] or origin["source_head_hash"] != last_v1[1]:
            raise _bad("origin")
        s3a = {
            "resolution_seq": origin["resolution_seq"],
            "parent_resolution_hash": recs[-1]["resolution_hash"] if recs else None, "resolution_hash": None,
            "request_id": rec["request_id"], "request_hash": rec["request_hash"],
            "request_basis": copy.deepcopy(rec["request_basis"]), "command_index": rec["command_index"],
            "command_count": rec["command_count"], "kind": rec["kind"], "variant": rec["variant"], "d": rec["d"],
            "source_head_seq": origin["source_head_seq"], "source_head_hash": origin["source_head_hash"],
            "state_after": copy.deepcopy(rec["state_after"]),
            "record_fingerprints": list(rec["record_fingerprints"]),
            "applied_ref": _inverse_applied(events, v1_pos, rec["applied_ref"]),
            "missing_ref": _inverse_missing(events, v1_pos, inv_res, rec["missing_ref"]),
            "session_context": copy.deepcopy(rec["session_context"]), "frontier_before": rec["frontier_before"],
            "ledger_digest": rec["ledger_digest"], "reason_code": rec["reason_code"],
            "requested_at": rec["requested_at"]}
        s3a["resolution_hash"] = record_hash_of(s3a)
        if s3a["resolution_hash"] != origin["resolution_hash"]:
            raise _bad("origin")
        recs.append(s3a)
        inv_res[rec["seq"]] = (s3a["resolution_seq"], s3a["resolution_hash"])
        res_map.append({"resolution_seq": s3a["resolution_seq"], "resolution_hash": s3a["resolution_hash"],
                        "seq": rec["seq"]})
    if not same(mig["resolution_map"], res_map):
        raise _bad("migration_map")
    rset = ResolutionSet.from_dict(set_dict(recs))
    rdict = rset.to_dict()
    if not same(mig["source_resolutions"], {"schema": rdict["schema"], "head_resolution_seq": rdict["head_resolution_seq"],
                                            "head_resolution_hash": rdict["head_resolution_hash"],
                                            "digest": rset.digest}):
        raise _bad("migration_resolutions")
    try:
        validate_resolutions(snapshot, rset)
    except PersistenceError as e:
        raise _bad("s3a:%s" % (e.rule or e.code)) from None
    return snapshot, rset


def _inverse_applied(events, v1_pos, ref):
    if ref is None:
        return None
    pos = v1_pos.get(ref["seq"])
    if pos is None or ref["event_hash"] != events[ref["seq"]]["event_hash"]:
        raise _bad("migration_map")
    return {"seq": pos[0], "event_hash": pos[1], "fingerprint": ref["fingerprint"]}


def _inverse_missing(events, v1_pos, inv_res, ref):
    if ref is None:
        return None
    if ref["kind"] == "APPLY":
        pos = v1_pos.get(ref["seq"])
        if pos is None or ref["event_hash"] != events[ref["seq"]]["event_hash"]:
            raise _bad("migration_map")
        return {"kind": "APPLY", "seq": pos[0], "event_hash": pos[1]}
    res = inv_res.get(ref["seq"])
    if res is None or ref["event_hash"] != events[ref["seq"]]["event_hash"]:
        raise _bad("migration_map")
    return {"kind": DECLARE_MISSING, "resolution_seq": res[0], "resolution_hash": res[1]}


# --- conversion (S1 + S3-A -> schema 2 records) ------------------------------------------------------------------
def _finish(ev):
    ev["event_hash"] = compute_event_hash(ev)
    return ev


def convert_events(snapshot, resolutions, ledger_digest, check_d, request_id, requested_at_text):
    """The schema-2 records for validated inputs: each S1 event followed by the S3-A records made right after it, and a
    SCHEMA_MIGRATION record last. Nothing is checked here; validate_history judges the result."""
    v1_events = snapshot.events
    by_source = {}
    for rec in resolutions.records:
        by_source.setdefault(rec["source_head_seq"], []).append(rec)
    out, v1_pos, v1_hash, res_pos = [], {}, {}, {}

    def head_hash():
        return out[-1]["event_hash"] if out else None

    for s, src in enumerate(v1_events):
        ev = copy.deepcopy(src)
        ev["seq"] = len(out)
        ev["parent_seq"] = len(out) - 1 if out else None
        ev["parent_hash"] = head_hash()
        out.append(_finish(ev))
        v1_pos[s] = (ev["seq"], ev["event_hash"])
        v1_hash[s] = src["event_hash"]
        for r in by_source.get(s, []):
            seq = len(out)
            applied = None if r["applied_ref"] is None else {
                "seq": v1_pos[r["applied_ref"]["seq"]][0], "event_hash": v1_pos[r["applied_ref"]["seq"]][1],
                "fingerprint": r["applied_ref"]["fingerprint"]}
            missing = r["missing_ref"]
            if missing is not None:
                if missing["kind"] == "APPLY":
                    t = v1_pos[missing["seq"]]
                    missing = {"kind": "APPLY", "seq": t[0], "event_hash": t[1]}
                else:
                    t = res_pos[missing["resolution_seq"]]
                    missing = {"kind": DECLARE_MISSING, "seq": t[0], "event_hash": t[1]}
            rec = {
                "kind": r["kind"], "seq": seq, "parent_seq": seq - 1, "parent_hash": head_hash(),
                "variant": r["variant"], "d": r["d"], "record_fingerprints": list(r["record_fingerprints"]),
                "applied_ref": applied, "missing_ref": missing,
                "session_context": copy.deepcopy(r["session_context"]), "frontier_before": r["frontier_before"],
                "request_id": r["request_id"], "request_hash": r["request_hash"],
                "request_basis": copy.deepcopy(r["request_basis"]), "command_index": r["command_index"],
                "command_count": r["command_count"], "reason_code": r["reason_code"],
                "requested_at": r["requested_at"], "ledger_digest": r["ledger_digest"],
                "origin": {"resolution_seq": r["resolution_seq"], "resolution_hash": r["resolution_hash"],
                           "source_head_seq": r["source_head_seq"], "source_head_hash": r["source_head_hash"]},
                "replay_of": None, "state_after": copy.deepcopy(r["state_after"])}
            out.append(_finish(rec))
            res_pos[r["resolution_seq"]] = (seq, rec["event_hash"])
    last = v1_events[-1]
    rdict = resolutions.to_dict()
    basis = {"request_id": request_id, "source_snapshot_digest": sha256_text(encode_snapshot(snapshot)),
             "source_resolutions_digest": resolutions.digest, "check_d": check_d, "reason_code": REASON_MIGRATE,
             "requested_at": requested_at_text}
    seq = len(out)
    out.append(_finish({
        "kind": SCHEMA_MIGRATION, "seq": seq, "parent_seq": seq - 1, "parent_hash": head_hash(),
        "source": {"schema_version": 1, "core_sha": snapshot.core_sha, "head_seq": last["seq"],
                   "head_hash": last["event_hash"], "snapshot_digest": basis["source_snapshot_digest"]},
        "source_resolutions": {"schema": rdict["schema"], "head_resolution_seq": rdict["head_resolution_seq"],
                               "head_resolution_hash": rdict["head_resolution_hash"], "digest": resolutions.digest},
        "event_map": [{"v1_seq": s, "v1_event_hash": v1_hash[s], "seq": q} for s, (q, _h) in sorted(v1_pos.items())],
        "resolution_map": [{"resolution_seq": s, "resolution_hash": r["resolution_hash"], "seq": q}
                           for (s, (q, _h)), r in zip(sorted(res_pos.items()), resolutions.records)],
        "request_id": request_id, "request_hash": basis_request_hash(basis), "request_basis": basis,
        "reason_code": REASON_MIGRATE, "requested_at": requested_at_text, "ledger_digest": ledger_digest,
        "state_after": copy.deepcopy(last["state_after"])}))
    return out
