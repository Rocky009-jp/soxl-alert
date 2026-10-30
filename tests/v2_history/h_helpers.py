"""Helpers for the v2_history tests: a test-only record builder for schema-2 histories (never imported by the runtime).

The builder is written independently of the checker: it makes APPLY content with the real S1 prepare_day on the current
segment, and writes ACK / DECLARE_MISSING / RESTART_UNKNOWN / RECOVERY_RESTORE records (and their re-created batches)
by the rules of the design document. Sessions, series and ledgers are synthetic (not a market calendar).

Sockets are disabled on import (as in the other test packages). The existing helpers r_helpers / p_helpers are reused
read-only.
"""
import copy
import hashlib
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence"), os.path.join(ROOT, "tests", "v2_recovery")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import r_helpers as RH  # noqa: E402  (existing helper; it also disables sockets)
import v2_history as V  # noqa: E402
from v2_core.state import MarketState  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_persistence.events import make_apply_event, make_genesis_event, session_dict, snapshot_of  # noqa: E402
from v2_recovery import ledger as L  # noqa: E402

P = RH.P
R = RH.R
D = P.DATES
WHEN = RH.WHEN
CHECK_D = D[25]
ZERO = "0" * 64
CORE_SHA = "b616b4ec7169420e199ec7e247dd375b3603a013"


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_history tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket
socket.create_connection = _blocked


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_of(ev):
    return sha(cj({k: v for k, v in ev.items() if k != "event_hash"}))


def finish(ev):
    ev["event_hash"] = hash_of(ev)
    return ev


def initial_state():
    return MarketState.initial().to_dict()


def header(events):
    last = events[-1]
    return {"schema_version": 2, "core_sha": CORE_SHA, "head_seq": last["seq"], "head_hash": last["event_hash"],
            "current_state": deep(last["state_after"]), "events": events}


def history_of(events):
    return V.History.from_dict(header(deep(events)))


def request_hash(basis):
    return sha(cj({k: v for k, v in basis.items() if k != "requested_at"}))


def fp_of_apply(ev):
    return L.parse_row(ev["confirmed_inputs"]["decision"]).fp


def fp(row):
    return L.parse_row(row).fp


def segment_of(chain_recs):
    """The last segment of a chain (list of record dicts): boundary, its APPLY and DECLARE_MISSING records."""
    seg = None
    for r in chain_recs:
        k = r["kind"]
        if k == "GENESIS":
            seg = {"kind": k, "seq": r.get("seq"), "date": r["start_after"], "session": r["boundary_session"],
                   "applies": [], "declares": []}
        elif k == "RESTART_UNKNOWN":
            seg = {"kind": k, "seq": r.get("seq"), "date": r["resume_after"], "session": r["boundary_session"],
                   "applies": [], "declares": []}
        elif k == "APPLY":
            seg["applies"].append(r)
        elif k == "DECLARE_MISSING":
            seg["declares"].append(r)
    return seg


def frontier_of(seg):
    best, sess = seg["date"], seg["session"]
    if seg["applies"] and seg["applies"][-1]["d"] > best:
        best, sess = seg["applies"][-1]["d"], seg["applies"][-1]["confirmed_inputs"]["session_context"][-2]
    if seg["declares"] and seg["declares"][-1]["d"] > best:
        best, sess = seg["declares"][-1]["d"], seg["declares"][-1]["session_context"][1]
    return best, sess


def floor_of(chain_recs):
    last_apply = max([r["d"] for r in chain_recs if r["kind"] == "APPLY"], default=None)
    last_decl = max([r["d"] for r in chain_recs if r["kind"] == "DECLARE_MISSING"], default=None)
    return {"last_apply_d": last_apply, "last_declared_d": last_decl, "prev_boundary": segment_of(chain_recs)["date"]}


class HB(object):
    """Builds a schema-2 history record by record. self.events is the physical list; chain() the effective chain."""

    def __init__(self, world=None, events=None, start_idx=0):
        self.w = world if world is not None else P.World(start_idx)
        self.events = []
        if events is None:
            s = self.w.sessions.get(self.w.start_after)
            self.events.append(finish({
                "kind": "GENESIS", "seq": 0, "parent_seq": None, "parent_hash": None,
                "start_after": self.w.start_after, "boundary_session": session_dict(s),
                "state_after": initial_state()}))
        else:
            self.events = deep(events)

    # --- chain ----------------------------------------------------------------------------------------------
    def chain(self, upto=None):
        cur = len(self.events) - 1 if upto is None else upto
        out = []
        while cur is not None:
            out.append(cur)
            cur = self.events[cur]["parent_seq"]
        return out[::-1]

    def chain_recs(self, upto=None):
        return [self.events[s] for s in self.chain(upto)]

    @property
    def last(self):
        return self.events[-1]

    def history(self):
        return history_of(self.events)

    def check(self):
        return V.validate_history(self.history())

    def _push(self, ev):
        ev["seq"] = len(self.events)
        ev["parent_seq"] = ev["seq"] - 1
        ev["parent_hash"] = self.events[-1]["event_hash"]
        self.events.append(finish(ev))
        return ev

    def sessions(self):
        return self.w.sessions

    # --- APPLY ----------------------------------------------------------------------------------------------
    def apply_content(self, chain_recs, d):
        """Content of an APPLY for D after the given chain: the real S1 prepare_day on the current segment."""
        seg = segment_of(chain_recs)
        evs = [make_genesis_event(seg["date"], seg["session"])]
        for i, r in enumerate(seg["applies"], 1):
            evs.append(make_apply_event(i, evs[-1]["event_hash"], r["d"], r["confirmed_inputs"],
                                        r["skipped_sessions"], r["transition_result"], r["state_after"]))
        res = P.prepare_day(snapshot_of(evs), d, self.w.series, self.w.sessions, self.w.ledger)
        assert res.plan is not None, "no APPLY for %s" % d
        ev = res.plan.event
        return {k: ev[k] for k in ("d", "confirmed_inputs", "input_hash", "skipped_sessions", "transition_result",
                                   "state_after")}

    def apply(self, d, value=None, rid=None):
        if value is not None:
            self.w.ledger.append(P.obs(rid or ("R-" + d), d, value))
        ev = {"kind": "APPLY"}
        ev.update(self.apply_content(self.chain_recs(), d))
        return self._push(ev)

    # --- ACK / DECLARE_MISSING --------------------------------------------------------------------------------
    def _refs(self, spec):
        applied = missing = None
        if spec.get("applied") is not None:
            a = self.events[spec["applied"]]
            applied = {"seq": a["seq"], "event_hash": a["event_hash"], "fingerprint": fp_of_apply(a)}
        if spec.get("missing") is not None:
            kind, seq = spec["missing"]
            missing = {"kind": kind, "seq": seq, "event_hash": self.events[seq]["event_hash"]}
        return applied, missing

    def resolution(self, specs, rid, check_d=None, when=None):
        """A request batch of ACK / DECLARE_MISSING records. spec: kind, variant, d, fps, applied (v2 seq of an
        APPLY), missing ('APPLY'|'DECLARE_MISSING', v2 seq)."""
        check_d = check_d or CHECK_D
        when = when or "2026-06-01T00:00:00Z"
        cmds = []
        for sp in specs:
            applied, missing = self._refs(sp)
            cmds.append({"kind": sp["kind"], "variant": sp.get("variant"), "d": sp["d"],
                         "record_fingerprints": sorted(sp.get("fps", [])), "applied_ref": applied,
                         "missing_ref": missing})
        kinds = {c["kind"] for c in cmds}
        batch_reason = "RESOLUTION_BATCH"
        reason = ("ACKNOWLEDGE_LEDGER_CHANGE" if kinds == {"ACK"} else
                  "MARK_SESSION_MISSING" if kinds == {"DECLARE_MISSING"} else batch_reason)
        basis = {"request_id": rid, "commands": cmds, "check_d": check_d, "reason_code": reason, "requested_at": when}
        out = []
        for j, c in enumerate(cmds):
            frontier = ctx = None
            if c["kind"] == "DECLARE_MISSING":
                seg = segment_of(self.chain_recs())
                frontier, fsess = frontier_of(seg)
                sl = self.w.sessions
                ctx = [session_dict(sl.get(frontier)), session_dict(sl.get(c["d"])),
                       session_dict(sl.next(c["d"]))]
                assert ctx[0] == fsess
            ev = {"kind": c["kind"], "variant": c["variant"], "d": c["d"],
                  "record_fingerprints": list(c["record_fingerprints"]), "applied_ref": deep(c["applied_ref"]),
                  "missing_ref": deep(c["missing_ref"]), "session_context": ctx, "frontier_before": frontier,
                  "request_id": rid, "request_hash": request_hash(basis), "request_basis": deep(basis),
                  "command_index": j, "command_count": len(cmds),
                  "reason_code": "ACKNOWLEDGE_LEDGER_CHANGE" if c["kind"] == "ACK" else "MARK_SESSION_MISSING",
                  "requested_at": when, "ledger_digest": sha("ledger-" + rid), "origin": None, "replay_of": None,
                  "state_after": deep(self.last["state_after"])}
            out.append(self._push(ev))
        return out

    def ack(self, variant, d, fps, rid, applied=None, missing=None, check_d=None):
        return self.resolution([{"kind": "ACK", "variant": variant, "d": d, "fps": fps, "applied": applied,
                                 "missing": missing}], rid, check_d)[0]

    def declare(self, d, rid, fps=(), check_d=None):
        return self.resolution([{"kind": "DECLARE_MISSING", "d": d, "fps": list(fps)}], rid, check_d)[0]

    # --- RESTART_UNKNOWN -------------------------------------------------------------------------------------
    def restart_content(self, chain_recs, resume_after, rid, check_d=None, when=None):
        check_d = check_d or CHECK_D
        when = when or "2026-06-01T00:00:00Z"
        basis = {"request_id": rid, "resume_after": resume_after, "check_d": check_d,
                 "reason_code": "RESTART_UNKNOWN", "requested_at": when}
        return {"kind": "RESTART_UNKNOWN", "resume_after": resume_after,
                "boundary_session": session_dict(self.w.sessions.get(resume_after)),
                "floor": floor_of(chain_recs), "request_id": rid, "request_hash": request_hash(basis),
                "request_basis": basis, "reason_code": "RESTART_UNKNOWN", "requested_at": when, "replay_of": None,
                "state_after": initial_state()}

    def restart(self, resume_after, rid, check_d=None):
        return self._push(self.restart_content(self.chain_recs(), resume_after, rid, check_d))

    # --- RECOVERY_RESTORE ------------------------------------------------------------------------------------
    def restore(self, point, ops, rid, check_d=None, when=None):
        """ops: {from_seq: op} or a list aligned with the superseded records. Writes the RESTORE record and the batch
        of records it creates (REAPPLY / REPLAY), recomputed on the new chain."""
        check_d = check_d or CHECK_D
        when = when or "2026-06-01T00:00:00Z"
        chain = self.chain()
        superseded = chain[chain.index(point) + 1:]
        op_list = [ops[s] for s in superseded] if isinstance(ops, dict) else list(ops)
        assert len(op_list) == len(superseded)
        k = len(self.events)
        vchain = [deep(self.events[s]) for s in chain[:chain.index(point) + 1]]
        drafts, created_map, replay, same_flags = [], {}, [], {}
        for s, op in zip(superseded, op_list):
            old = self.events[s]
            entry = {"op": op, "from_seq": s, "d": None, "seq": None, "same_as_superseded": None}
            if op in ("REAPPLY", "REPLAY"):
                created_map[s] = k + 1 + len(drafts)
                entry["seq"] = created_map[s]
                if op == "REAPPLY":
                    content = self.apply_content(vchain, old["d"])
                    same = all(cj(content[key]) == cj(old[key]) for key in
                               ("input_hash", "skipped_sessions", "transition_result", "state_after"))
                    entry["d"], entry["same_as_superseded"] = old["d"], same
                    draft = dict(kind="APPLY", **content)
                else:
                    draft = self._replay_draft(old, vchain)
                    draft["_from"] = s
                drafts.append(draft)
                vchain.append(draft)
            replay.append(entry)
        basis = {"request_id": rid, "restore_point": {"seq": point, "event_hash": self.events[point]["event_hash"]},
                 "ops": [{"op": e["op"], "from_seq": e["from_seq"]} for e in replay], "check_d": check_d,
                 "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": when}
        rec = finish({
            "kind": "RECOVERY_RESTORE", "seq": k, "prev_hash": self.events[-1]["event_hash"], "parent_seq": point,
            "parent_hash": self.events[point]["event_hash"], "superseded_seqs": list(superseded), "replay": replay,
            "request_id": rid, "request_hash": request_hash(basis), "request_basis": basis,
            "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": when, "ledger_digest": sha("restore-" + rid),
            "state_after": deep(self.events[point]["state_after"])})
        self.events.append(rec)
        for draft in drafts:
            ev = {key: v for key, v in draft.items() if key != "_from"}
            if "_from" in draft:
                old = self.events[draft["_from"]]
                self._map_refs(ev, old, created_map)
                ev["replay_of"] = {"seq": old["seq"], "event_hash": old["event_hash"]}
            self._push(ev)
        return rec

    def _replay_draft(self, old, vchain):
        """A REPLAY record's content on the new chain (vchain): copied request items, recomputed state_after /
        frontier / context / floor. References are filled in by _map_refs once the created seqs are final."""
        ev = deep(old)
        for key in ("seq", "parent_seq", "parent_hash", "event_hash"):
            ev.pop(key, None)
        if old["kind"] == "RESTART_UNKNOWN":
            ev["floor"] = floor_of(vchain)
            ev["state_after"] = initial_state()
        else:
            ev["state_after"] = deep(vchain[-1]["state_after"])
            if old["kind"] == "DECLARE_MISSING":
                seg = segment_of(vchain)
                frontier, _sess = frontier_of(seg)
                sl = self.w.sessions
                ev["frontier_before"] = frontier
                ev["session_context"] = [session_dict(sl.get(frontier)), session_dict(sl.get(old["d"])),
                                         session_dict(sl.next(old["d"]))]
        return ev

    def _map_refs(self, ev, old, created_map):
        def target(t):
            if t in created_map:
                return created_map[t]
            return t
        if ev["kind"] != "ACK":
            return
        if old["applied_ref"] is not None:
            t = target(old["applied_ref"]["seq"])
            ev["applied_ref"] = {"seq": t, "event_hash": self.events[t]["event_hash"],
                                 "fingerprint": old["applied_ref"]["fingerprint"]}
        if old["missing_ref"] is not None:
            t = target(old["missing_ref"]["seq"])
            ev["missing_ref"] = {"kind": old["missing_ref"]["kind"], "seq": t,
                                 "event_hash": self.events[t]["event_hash"]}


def chain_of(events, upto=None):
    cur = len(events) - 1 if upto is None else upto
    out = []
    while cur is not None:
        out.append(cur)
        cur = events[cur]["parent_seq"]
    return out[::-1]


def hand_restore(events, point, replay, superseded=None, rid="q99", check_d=None, when="2026-06-01T00:00:00Z"):
    """Append a RECOVERY_RESTORE written by hand (no batch, no consistency beyond hashes): for refusal tests."""
    events = deep(events)
    k = len(events)
    if superseded is None:
        chain = chain_of(events, k - 1)
        superseded = chain[chain.index(point) + 1:] if point in chain else []
    basis = {"request_id": rid, "restore_point": {"seq": point, "event_hash": events[point]["event_hash"]},
             "ops": [{"op": e["op"], "from_seq": e["from_seq"]} if "from_seq" in e else deep(e) for e in replay],
             "check_d": check_d or CHECK_D, "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": when}
    events.append(finish({
        "kind": "RECOVERY_RESTORE", "seq": k, "prev_hash": events[-1]["event_hash"], "parent_seq": point,
        "parent_hash": events[point]["event_hash"], "superseded_seqs": list(superseded), "replay": deep(replay),
        "request_id": rid, "request_hash": request_hash(basis), "request_basis": basis,
        "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": when, "ledger_digest": sha("restore-" + rid),
        "state_after": deep(events[point]["state_after"])}))
    return events


def edit_restore(events, index, fn):
    """Apply fn(record) to the RECOVERY_RESTORE at `index`, mirror its replay into request_basis.ops, recompute the
    request hash, then relink everything (so only the edited content is wrong)."""
    events = deep(events)
    rec = events[index]
    fn(rec)
    rec["request_basis"]["ops"] = [{"op": e["op"], "from_seq": e["from_seq"]} if "from_seq" in e else deep(e)
                                   for e in rec["replay"]]
    rec["request_hash"] = request_hash(rec["request_basis"])
    return events


def edit_resolution(events, index, **fields):
    """Change fields of an ACK / DECLARE_MISSING and, for the command fields, the matching command inside the shared
    request_basis (all records of that request), then refresh request_hash. Returns the raw records (not rebuilt)."""
    events = deep(events)
    rec = events[index]
    j, rid = rec["command_index"], rec["request_id"]
    for key, value in fields.items():
        rec[key] = deep(value)
        if key in ("kind", "variant", "d", "record_fingerprints", "applied_ref", "missing_ref"):
            rec["request_basis"]["commands"][j][key] = deep(value)
    for r in events:
        if r["kind"] in ("ACK", "DECLARE_MISSING") and r["request_id"] == rid:
            r["request_basis"] = deep(rec["request_basis"])
            r["request_hash"] = request_hash(r["request_basis"])
    return events


def rebuild_edit(events, index, fn, remap=True):
    """edit_restore + rebuild; remap=True re-links the references of the records the RESTORE created."""
    return rebuild(edit_restore(events, index, fn), remap=remap)


def insert_record(events, pos, rec):
    """Insert a raw record at `pos` and renumber seq / parent_seq of ordinary records after it (RESTORE parents move
    along when they point at or after the insertion)."""
    events = deep(events)
    rec = deep(rec)
    events.insert(pos, rec)
    for i, ev in enumerate(events):
        if i >= pos:
            ev["seq"] = i
        if i > 0 and ev["kind"] != "RECOVERY_RESTORE":
            ev["parent_seq"] = i - 1
        elif ev["kind"] == "RECOVERY_RESTORE" and ev["parent_seq"] >= pos:
            ev["parent_seq"] += 1
    return events


# --- mutation helpers -------------------------------------------------------------------------------------------
def rebuild(events, remap=False):
    """New History from raw record dicts: restore the audit links and the event hashes. With remap=True, the
    references that carry an event hash (applied_ref, missing_ref, replay_of, restore_point) are re-linked to the
    rebuilt hashes of the records they point at, and the request hashes are recomputed."""
    events = deep(events)
    for i, ev in enumerate(events):
        if i > 0:
            if ev["kind"] == "RECOVERY_RESTORE":
                ev["prev_hash"] = events[i - 1]["event_hash"]
                ev["parent_hash"] = events[ev["parent_seq"]]["event_hash"]
            else:
                ev["parent_hash"] = events[i - 1]["event_hash"]
        if remap:
            for key in ("applied_ref", "missing_ref", "replay_of"):
                ref = ev.get(key)
                if isinstance(ref, dict) and isinstance(ref.get("seq"), int) and ref["seq"] < i:
                    ref["event_hash"] = events[ref["seq"]]["event_hash"]
            if ev["kind"] == "RECOVERY_RESTORE":
                rp = ev["request_basis"]["restore_point"]
                rp["event_hash"] = events[rp["seq"]]["event_hash"]
                ev["request_hash"] = request_hash(ev["request_basis"])
        ev["event_hash"] = hash_of(ev)
    return history_of(events)


def mutated(events, fn, remap=False):
    """Apply fn(list_of_records) to a copy of the records, then rebuild the links (history_of with fresh hashes)."""
    ev = deep(events)
    fn(ev)
    return rebuild(ev, remap=remap)


def rule_of(case, history):
    with case.assertRaises(PersistenceError) as cm:
        V.validate_history(history)
    e = cm.exception
    case.assertEqual(e.code, "history_invalid", "unexpected code %s (rule %s)" % (e.code, e.rule))
    return e.rule


def expect_rule(case, rule, history):
    case.assertEqual(rule_of(case, history), rule)


def expect_error(case, code, rule, fn, *args, **kwargs):
    with case.assertRaises(PersistenceError) as cm:
        fn(*args, **kwargs)
    case.assertEqual(cm.exception.code, code)
    if rule is not None:
        case.assertEqual(cm.exception.rule, rule)
    return cm.exception


def expect_field(case, code, field, fn, *args, **kwargs):
    """A refusal that carries a field instead of a rule (unsupported_schema, unsupported_event, ...)."""
    with case.assertRaises(PersistenceError) as cm:
        fn(*args, **kwargs)
    case.assertEqual((cm.exception.code, cm.exception.field), (code, field))
    return cm.exception


def sess(d):
    return session_dict(P.make_sessions().get(d))


# --- fixed examples ----------------------------------------------------------------------------------------------
def values():
    """F&G values that keep every day a decision day with a distinct, valid state."""
    return {1: 27.0, 2: 28.0, 3: 31.0, 4: 32.0, 5: 33.0, 6: 34.0}


def example_u():
    """Design 7.3: GENESIS(D0), APPLY D1, APPLY D2, RESTART_UNKNOWN(resume_after=D3). D3 is intentionally unprocessed."""
    b = HB()
    b.apply(D[1], 27.0)
    b.apply(D[2], 28.0)
    b.restart(D[3], "q1")
    return b


def example_r1():
    """Example R up to and including RESTORE#1 and the three records it creates (seqs 0..10)."""
    b = HB()
    b.apply(D[1], 27.0)                                   # 1
    b.apply(D[2], 28.0)                                   # 2
    b.restart(D[2], "q1")                                 # 3
    b.apply(D[3], 31.0)                                   # 4
    b.ack("ADDED", D[3], [fp(P.obs("B3", D[3], 41.0, hour=21))], "q2", applied=4)   # 5
    b.apply(D[4], 32.0)                                   # 6
    b.restore(2, {3: "DROP", 4: "REAPPLY", 5: "REPLAY", 6: "REAPPLY"}, "q4")        # 7 (+8, 9, 10)
    return b


def example_r13():
    """Example R up to the APPLY D6 after the second RESTART (seqs 0..13)."""
    b = example_r1()
    b.apply(D[5], 33.0)                                   # 11
    b.restart(D[5], "q3")                                 # 12
    b.apply(D[6], 34.0)                                   # 13
    return b


def example_r():
    """Design 8.9: three restores. Returns the builder; seqs follow the design table."""
    b = HB()
    b.apply(D[1], 27.0)                                   # 1
    b.apply(D[2], 28.0)                                   # 2
    b.restart(D[2], "q1")                                 # 3
    b.apply(D[3], 31.0)                                   # 4
    b.ack("ADDED", D[3], [fp(P.obs("B3", D[3], 41.0, hour=21))], "q2", applied=4)   # 5
    b.apply(D[4], 32.0)                                   # 6
    b.restore(2, {3: "DROP", 4: "REAPPLY", 5: "REPLAY", 6: "REAPPLY"}, "q4")        # 7 (+8, 9, 10)
    b.apply(D[5], 33.0)                                   # 11
    b.restart(D[5], "q3")                                 # 12
    b.apply(D[6], 34.0)                                   # 13
    b.restore(9, {10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, "q5")   # 14 (+15, 16, 17)
    b.restore(2, {7: "RETIRE", 8: "REAPPLY", 9: "DROP", 14: "RETIRE", 15: "REAPPLY", 16: "REAPPLY",
                  17: "REAPPLY"}, "q6")                  # 18 (+19..22)
    return b


def example_rb():
    """Design 8.9 R-b: a DECLARE_MISSING replayed on a changed parent state."""
    b = HB()
    b.apply(D[1], 27.0)                                   # 1
    b.restart(D[1], "q1")                                 # 2
    b.apply(D[2], 28.0)                                   # 3
    b.declare(D[3], "q2")                                 # 4
    b.apply(D[4], 29.0)                                   # 5 (skips D3: no decision row)
    b.restore(1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, "q3")        # 6 (+7, 8, 9)
    return b


def example_m_world():
    """Design 5.7 on the S1 + S3-A machinery: returns (world, snapshot, resolutions, ledger, check_d)."""
    w = P.World()
    w.apply(D[1], 27.0, "R1")
    rs = R.empty_resolutions()
    extra = P.obs("B1", D[1], 40.0, hour=21)
    ledger = list(w.ledger) + [extra]
    snap = w.snap()
    rs = RH.run(w, rs, [RH.ack(snap, "ADDED", D[1], [fp(extra)])], ledger, D[1], "q1").resolutions
    w.apply(D[2], 28.0, "R2")
    ledger = list(w.ledger) + [extra]
    snap = w.snap()
    rs = RH.run(w, rs, [RH.declare(D[3])], ledger, D[3], "q2", snapshot=snap).resolutions
    w.apply(D[4], 29.0, "R4")
    snap = w.snap()
    late = P.obs("L3", D[3], 22.0)
    ledger = list(w.ledger) + [extra, late]
    miss = RH.declare_missing(rs, 2)
    rs = RH.run(w, rs, [RH.late(D[3], [fp(late)], miss)], ledger, D[4], "q3", snapshot=snap).resolutions
    return w, snap, rs, ledger, D[4]


def example_m2_world():
    """A larger S1 + S3-A scenario: CHANGED, ROW_REMOVED, DECLARE, LATE (declaration reference) and LATE (APPLY
    reference). v1: 0 GENESIS, 1 APPLY D1, 2 APPLY D2, 3 APPLY D4 (skips D3), 4 APPLY D6 (skips D5).
    S3-A: r1 CHANGED(D1) at head 1, r2 ROW_REMOVED(D2) at head 2, r3 DECLARE(D3) at head 2, r4 LATE(D3) at head 3,
    r5 LATE(D5) at head 4. Returns (world, snapshot, resolutions, ledger, check_d)."""
    w = P.World()
    w.apply(D[1], 27.0, "R1")
    snap1 = w.snap()
    changed = P.obs("R1", D[1], 31.0, hour=21)
    rs = RH.run(w, R.empty_resolutions(), [RH.ack(snap1, "CHANGED", D[1], [fp(changed)])],
                [w.ledger[0], changed], D[1], "c1", snapshot=snap1).resolutions
    w.apply(D[2], 28.0, "R2")
    snap2 = w.snap()
    ledger = [w.ledger[0], changed]                                  # R2 is gone from the ledger
    rs = RH.run(w, rs, [RH.ack(snap2, "ROW_REMOVED", D[2], [], seq=2)], ledger, D[2], "c2", snapshot=snap2).resolutions
    rs = RH.run(w, rs, [RH.declare(D[3])], ledger, D[3], "c3", snapshot=snap2).resolutions
    w.apply(D[4], 29.0, "R4")
    snap3 = w.snap()
    l3 = P.obs("L3", D[3], 22.0)
    ledger = [w.ledger[0], changed, w.ledger[2], l3]
    rs = RH.run(w, rs, [RH.late(D[3], [fp(l3)], RH.declare_missing(rs, 3))], ledger, D[4], "c4",
                snapshot=snap3).resolutions
    w.apply(D[6], 30.0, "R6")
    snap4 = w.snap()
    l5 = P.obs("L5", D[5], 23.0)
    ledger = [w.ledger[0], changed, w.ledger[2], w.ledger[3], l3, l5]
    rs = RH.run(w, rs, [RH.late(D[5], [fp(l5)], RH.apply_missing(snap4, 4))], ledger, D[6], "c5",
                snapshot=snap4).resolutions
    return w, snap4, rs, ledger, D[6]


def example_m_empty_world():
    """Two APPLYs and an empty ResolutionSet."""
    w = P.World()
    w.apply(D[1], 27.0, "R1")
    w.apply(D[2], 28.0, "R2")
    return w, w.snap(), R.empty_resolutions(), list(w.ledger), D[2]


def migrate(w, snap, rs, ledger, check_d, rid="mig-1"):
    """Prepare + confirm the migration; returns the candidate History."""
    plan = V.prepare_migration_plan(snap, rs, w.sessions, ledger, check_d, rid, WHEN)
    return V.confirm_migration_plan(plan, plan.plan_hash, snap, rs, w.sessions, ledger).history


def example_m():
    """The migrated history of design 5.7 as a builder (world ledger holds the APPLY decisions of the S1 history)."""
    w, snap, rs, ledger, check_d = example_m_world()
    h = migrate(w, snap, rs, ledger, check_d)
    return HB(world=w, events=h.events), (w, snap, rs, ledger, check_d)
