"""Helpers for the C-1 (CONSUME) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The existing helpers (h_helpers, ho_helpers, r4_helpers) are only
imported, never changed. `oracle` writes the RECOVERY_RESTORE batch of an expected result with the test-only record
builder HB of h_helpers and the S1 prepare_day it uses (through HB.apply_content), so that a CONSUMEd APPLY is expected
without the runtime under test. The scenarios are the synthetic histories of r4_helpers, each with the ledger rows that
give the freed days a decision.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_restore")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import r4_helpers as R  # noqa: E402  (existing helper; it also disables sockets)
from v2_recovery.ledger import ledger_digest, parse_ledger  # noqa: E402

H, P, D, T, Z, V, O = R.H, R.P, R.D, R.T, R.Z, R.V, R.O
WHEN, WHEN_TEXT = R.WHEN, R.WHEN_TEXT
cj, deep, refusal = R.cj, R.deep, R.refusal

CONSUME = "CONSUME"


def ops_of(entries):
    """[(op, from_seq)] and [(CONSUME, day)] -> the ops list a caller writes."""
    return [{"op": CONSUME, "d": x} if op == CONSUME else {"op": op, "from_seq": x} for op, x in entries]


def err(fn, *args, **kwargs):
    """(code, field, rule, detail) of the refusal."""
    e = refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


def invalid(rule, detail=None):
    return ("restore_invalid", "ops", rule, detail)


# --- scenarios ------------------------------------------------------------------------------------------------------
def s_declare():
    """ex_declare_between + a decision X3 of D3 that is in the ledger now (the declaration D3 was written before it).
    0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2, 4 DECLARE D3, 5 APPLY D4."""
    b = R.ex_declare_between()
    b.w.ledger.append(P.obs("X3", D[3], 45.0))
    return b


def s_gap():
    """ex_restart_over_gap + decisions of D2 and D3. 0 GENESIS, 1 APPLY D1, 2 RESTART(D3), 3 APPLY D4."""
    b = R.ex_restart_over_gap()
    b.w.ledger.extend([P.obs("X2", D[2], 44.0), P.obs("X3", D[3], 46.0)])
    return b


def s_null():
    """ex_null_restart + a decision of D1. 0 GENESIS, 1 RESTART(D3): the restart closes a segment without APPLY."""
    b = R.ex_null_restart()
    b.w.ledger.append(P.obs("X1", D[1], 43.0))
    return b


def s_tail():
    """ex_declare_tail + a decision of D2. 0 GENESIS, 1 APPLY D1, 2 DECLARE D2: no APPLY after the declaration."""
    b = R.ex_declare_tail()
    b.w.ledger.append(P.obs("X2", D[2], 47.0))
    return b


def s_late():
    """ex_declare_then_late: 1 APPLY D1, 2 DECLARE D2, 3 APPLY D3, 4 LATE ACK D2 that excludes the late row L2."""
    b, late = R.ex_declare_then_late()
    return b, late


SKIP_DAYS = (4, 11)          # the APPLY days of s_calendar: D4, then D11 which passes over D5..D10


def s_calendar():
    """A history on the usual calendar: 0 GENESIS, 1 APPLY D4 (passes over D1..D3), 2 APPLY D11 (passes over D5..D10).
    The caller plans on a calendar that has one more session S between D9 and D10 (a Saturday): re-applying D11 then
    newly passes over S. A decision of S is in the ledger. Returns (builder, S, sessions_with_S, series_with_S)."""
    b = H.HB()
    b.apply(D[4], 27.0)
    b.apply(D[11], 29.0)
    s = "2026-03-14"
    assert D[9] < s < D[10] and s not in D
    dates = sorted(D + [s])
    b.w.ledger.append(P.obs("XS", s, 48.0))
    return b, s, P.make_sessions(dates=dates), P.make_series(dates=dates)


# --- the independent expected result --------------------------------------------------------------------------------
def oracle(b, point, entries, rid, check_d, ledger=None, sessions=None, series=None, reveal=()):
    """The physical events that the independent builder writes for the same restore: entries are (op, from_seq) of the
    superseded records in order and (CONSUME, day) wherever a day is consumed. A REAPPLY and a CONSUME are calculated by
    HB.apply_content (the S1 prepare_day) on the chain the batch has made so far. The two fields that only the runtime
    knows (the requested time text of the injected datetime, the digest of the injected ledger) are set the same."""
    w = b.w
    saved = (w.sessions, w.series, w.ledger)
    full = w.ledger if ledger is None else ledger
    extras = [cj(r) for r in getattr(b, "extra_rows", []) if r["record_id"] not in reveal]   # evidence rows of acknowledgements
    w.sessions, w.series = (sessions or w.sessions), (series or w.series)
    w.ledger = [r for r in full if cj(r) not in extras]
    try:
        return _oracle(b, w, point, entries, rid, check_d, full)
    finally:
        w.sessions, w.series, w.ledger = saved


def _oracle(b, w, point, entries, rid, check_d, ledger):
    hb = H.HB(world=w, events=b.events)
    chain = hb.chain()
    superseded = chain[chain.index(point) + 1:]
    named = [x for op, x in entries if op != CONSUME]
    assert named == superseded, (named, superseded)
    k = len(hb.events)
    vchain = [deep(hb.events[s]) for s in chain[:chain.index(point) + 1]]
    drafts, created_map, replay = [], {}, []
    for op, x in entries:
        if op == CONSUME:
            content = hb.apply_content(vchain, x)
            replay.append({"op": CONSUME, "from_seq": None, "d": x, "seq": k + 1 + len(drafts),
                           "same_as_superseded": None})
            draft = dict(kind="APPLY", **content)
            drafts.append(draft)
            vchain.append(draft)
            continue
        old = hb.events[x]
        entry = {"op": op, "from_seq": x, "d": None, "seq": None, "same_as_superseded": None}
        if op in ("REAPPLY", "REPLAY"):
            created_map[x] = k + 1 + len(drafts)
            entry["seq"] = created_map[x]
            if op == "REAPPLY":
                content = hb.apply_content(vchain, old["d"])
                same = all(cj(content[key]) == cj(old[key]) for key in
                           ("input_hash", "skipped_sessions", "transition_result", "state_after"))
                entry["d"], entry["same_as_superseded"] = old["d"], same
                draft = dict(kind="APPLY", **content)
            else:
                draft = hb._replay_draft(old, vchain)
                draft["_from"] = x
            drafts.append(draft)
            vchain.append(draft)
        replay.append(entry)
    ops = [{"op": e["op"], "d": e["d"]} if e["op"] == CONSUME else {"op": e["op"], "from_seq": e["from_seq"]}
           for e in replay]
    basis = {"request_id": rid, "restore_point": {"seq": point, "event_hash": hb.events[point]["event_hash"]},
             "ops": ops, "check_d": check_d, "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": WHEN_TEXT}
    rec = H.finish({
        "kind": "RECOVERY_RESTORE", "seq": k, "prev_hash": hb.events[-1]["event_hash"], "parent_seq": point,
        "parent_hash": hb.events[point]["event_hash"], "superseded_seqs": list(superseded), "replay": replay,
        "request_id": rid, "request_hash": H.request_hash(basis), "request_basis": basis,
        "reason_code": "RESTORE_VERIFIED_RECORD", "requested_at": WHEN_TEXT,
        "ledger_digest": ledger_digest(parse_ledger(w.ledger if ledger is None else ledger)),
        "state_after": deep(hb.events[point]["state_after"])})
    hb.events.append(rec)
    for draft in drafts:
        ev = {key: v for key, v in draft.items() if key != "_from"}
        if "_from" in draft:
            old = hb.events[draft["_from"]]
            hb._map_refs(ev, old, created_map)
            ev["replay_of"] = {"seq": old["seq"], "event_hash": old["event_hash"]}
        hb._push(ev)
    return H.rebuild(hb.events, remap=True).events


# --- edits of a written history ------------------------------------------------------------------------------------
def mirror_op(entry):
    """The ops entry that belongs to a replay entry (the form a caller writes)."""
    if entry.get("op") == CONSUME:
        return {"op": CONSUME, "d": entry.get("d")}
    return {"op": entry.get("op"), "from_seq": entry.get("from_seq")}


def edit(events, index, fn, mirror=True):
    """Apply fn(record) to the RECOVERY_RESTORE at `index`; with mirror, request_basis.ops is written again from the
    replay (so only the edited content is wrong); then relink the hashes. Returns a History."""
    events = deep(events)
    rec = events[index]
    fn(rec)
    if mirror:
        rec["request_basis"]["ops"] = [mirror_op(e) for e in rec["replay"]]
    return H.rebuild(events, remap=True)


def rule_of(case, history):
    return H.rule_of(case, history)


# --- plan, confirm ----------------------------------------------------------------------------------------------------
def plan(b, point, entries, check, rid="c1-1", **kw):
    return R.prep(b, point, None, check, rid, ops=ops_of(entries), **kw)


def plan_and_confirm(b, point, entries, check, rid="c1-1", **kw):
    p = plan(b, point, entries, check, rid, **kw)
    conf = {k: kw[k] for k in ("sessions", "ledger", "series") if k in kw}
    return p, R.confirm(p, b.history(), b.w, **conf)


def new_records(b, history):
    return history.events[len(b.events):]
