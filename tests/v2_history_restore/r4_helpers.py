"""Helpers for the v2_history_restore tests (never imported by the runtime). Synthetic sessions, series and ledgers.

Sockets are disabled on import (as in the other test packages). The existing helpers ho_helpers / h_helpers / r_helpers /
p_helpers are only imported, never changed. The scenario builders write histories with the independent test-only record
builder HB (h_helpers), and `oracle` writes the RECOVERY_RESTORE batch of an expected result with HB.restore, so an
expected candidate is built without the runtime under test.
"""
import copy
import dataclasses
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_ops")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ho_helpers as T  # noqa: E402  (existing helper; it also disables sockets)
import v2_history as V  # noqa: E402
import v2_history_ops as O  # noqa: E402
import v2_history_restore as Z  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402
from v2_recovery.common import requested_text  # noqa: E402
from v2_recovery.ledger import ledger_digest, parse_ledger  # noqa: E402

H, P, D, WHEN = T.H, T.P, T.D, T.WHEN
FIXED_START = "d82a5ced64658c2e736b82b1a2f1925636055417"
WHEN_TEXT = requested_text(WHEN)


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def point(b, seq):
    return {"seq": seq, "event_hash": b.events[seq]["event_hash"]}


def after(b, seq):
    """The effective seqs after `seq` in the builder's physical history, in order (what the ops must name)."""
    chain = H.chain_of(b.events)
    return chain[chain.index(seq) + 1:]


def ops_of(b, seq, mapping):
    """[{op, from_seq}] for every superseded record; mapping gives the op by from_seq (a default for the rest)."""
    default = mapping.get("*")
    return [{"op": mapping.get(s, default), "from_seq": s} for s in after(b, seq)]


UNSET = object()


def prep(b, seq, mapping, check, rid, history=None, sessions=None, ledger=None, series=None, when=WHEN, pt=UNSET,
         ops=UNSET):
    w = b.w
    return Z.prepare_restore_plan(
        history if history is not None else b.history(), point(b, seq) if pt is UNSET else pt,
        ops_of(b, seq, mapping) if ops is UNSET else ops, w.sessions if sessions is None else sessions,
        w.ledger if ledger is None else ledger, w.series if series is None else series, check, rid, when)


def confirm(plan, history, w, sessions=None, ledger=None, series=None, plan_hash=None):
    return Z.confirm_restore_plan(plan, plan.plan_hash if plan_hash is None else plan_hash, history,
                                  w.sessions if sessions is None else sessions,
                                  w.ledger if ledger is None else ledger, w.series if series is None else series)


def run(b, seq, mapping, check, rid, **kw):
    plan = prep(b, seq, mapping, check, rid, **kw)
    return plan, confirm(plan, b.history(), b.w)


def oracle(b, seq, mapping, rid, check):
    """The physical events that the independent builder writes for the same restore, with the two fields that only the
    runtime can know (the requested time text of the injected datetime, the digest of the injected ledger) set the same.
    The builder reads the raw ledger, so the rows that only serve as evidence of an acknowledgement (b.extra_rows) are
    left out while it calculates the days."""
    w = b.w
    saved = w.ledger
    extras = [cj(r) for r in getattr(b, "extra_rows", [])]
    w.ledger = [r for r in saved if cj(r) not in extras]
    try:
        b2 = H.HB(world=w, events=b.events)
        b2.restore(seq, {s: mapping.get(s, mapping.get("*")) for s in after(b, seq)}, rid, check_d=check,
                   when=WHEN_TEXT)
    finally:
        w.ledger = saved
    events = b2.events
    events[len(b.events)]["ledger_digest"] = ledger_digest(parse_ledger(saved))
    return H.rebuild(events, remap=True).events


def refusal(fn, *args, **kwargs):
    return T.refusal(fn, *args, **kwargs)


def rule_of(fn, *args, **kwargs):
    e = refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None))


def with_plan_dict(plan, fn):
    """A RestorePlan from the plan's dict after fn(dict) changed it (the hash is not fixed up)."""
    data = plan.to_dict()
    fn(data)
    return Z.RestorePlan.from_dict(data)


def refreshed(plan, fn):
    """A RestorePlan whose basis was changed by fn(basis) and whose plan_hash was recomputed to match."""
    data = plan.to_dict()
    fn(data["basis"])
    data["plan_hash"] = H.sha(cj(data["basis"]))
    return Z.RestorePlan.from_dict(data)


def sessions_with(overrides=None, unconfirmed=(), dates=None):
    return P.make_sessions(dates=dates, unconfirmed=unconfirmed, overrides=overrides)


def earlier_close(session):
    return dataclasses.replace(session, close_at=session.close_at - timedelta(minutes=5))


def later_open(session):
    return dataclasses.replace(session, open_at=session.open_at + timedelta(minutes=5))


def with_row(w, d, **fields):
    """A series like the world's with a changed market row at d (the stub rows are hand-written)."""
    per = {x: {} for x in P.DATES}
    per[d] = fields
    return P.make_series(per_date=per)


# --- scenarios ---------------------------------------------------------------------------------------------------
def ex_restart_between():
    """0 GENESIS D0, 1 APPLY D1, 2 RESTART_UNKNOWN(D1), 3 APPLY D2: the restart, written too early, is to be dropped."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    return b


def ex_restart_over_gap():
    """0 GENESIS D0, 1 APPLY D1, 2 RESTART_UNKNOWN(D3), 3 APPLY D4. D2 and D3 have no decision."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[3], "q1")
    b.apply(D[4], 29.0)
    return b


def ex_ack_between():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2, 4 ACK ADDED(D2) on seq 3, 5 APPLY D3. The evidence row of the
    acknowledgement (B2, written after D2 closed) is in the world's ledger."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    extra = P.obs("B2", D[2], 41.0, hour=21)
    b.ack("ADDED", D[2], [H.fp(extra)], "q2", applied=3)
    b.apply(D[3], 31.0)
    b.w.ledger.append(extra)                              # after the days are calculated: the builder reads the raw ledger
    b.extra_rows = [extra]
    return b


def ex_declare_between():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2, 4 DECLARE_MISSING D3 (q2), 5 APPLY D4 (skips D3)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    b.declare(D[3], "q2")
    b.apply(D[4], 29.0)
    return b


def ex_declare_then_late():
    """0 GENESIS, 1 APPLY D1, 2 DECLARE_MISSING D2 (q1), 3 APPLY D3 (skips D2), 4 LATE ACK D2 (q2) that excludes the late
    decision L2 which arrived after the declaration. Design 7.1 (known limit): replaying 2 and 4 together is refused."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.declare(D[2], "q1")
    b.apply(D[3], 31.0)
    late = P.obs("L2", D[2], 22.0)
    b.w.ledger.append(late)
    b.extra_rows = [late]
    b.ack("LATE", D[2], [H.fp(late)], "q2", missing=("DECLARE_MISSING", 2))
    return b, late


def ex_removed_then_changed():
    """0 GENESIS, 1 APPLY D1 (record R1), 2 ROW_REMOVED ACK D1 (q1) -- R1 left the ledger --, 3 CHANGED ACK D1 (q2) that
    excludes the version R1' which came back. Design 7.1 (known limit): replaying 2 and 3 together is refused."""
    b = H.HB()
    b.apply(D[1], 27.0, "R1")
    changed = P.obs("R1", D[1], 33.0, hour=21)
    b.w.ledger[:] = [changed]
    b.extra_rows = [changed]
    b.ack("ROW_REMOVED", D[1], [], "q1", applied=1)
    b.ack("CHANGED", D[1], [H.fp(changed)], "q2", applied=1)
    return b, changed


def ex_migrated_tail():
    """The migrated history of design 5.7 (migration at seq 7) and, after it: 8 APPLY D7, 9 RESTART_UNKNOWN(D7), 10 APPLY D8.
    The world's ledger holds the evidence rows of the migrated acknowledgements (b.extra_rows)."""
    b, (w, _snap, _rs, ledger, _check_d) = H.example_m()
    base = len(w.ledger)
    b.apply(D[7], 35.0, "R7")
    b.restart(D[7], "q4")
    b.apply(D[8], 36.0, "R8")
    extras = ledger[base:]
    b.extra_rows = list(extras)
    b.w.ledger.extend(extras)
    return b


def ex_after_three_restores():
    """Design 8.9 example R (three restores, effective 0,1,2,18..22) and after it: 23 APPLY D7, 24 RESTART(D7), 25 APPLY D8."""
    b = H.example_r()
    b.apply(D[7], 35.0, "R7")
    b.restart(D[7], "q7")
    b.apply(D[8], 36.0, "R8")
    return b


def ex_inside_old_batch():
    """Design 8.9 after restore #1 (the restore at 7 and its batch 8, 9, 10) and 11 APPLY D5, 12 RESTART(D5), 13 APPLY D6.
    Seq 8 is an APPLY in the middle of the batch of the earlier restore; the evidence row of the replayed acknowledgement
    (9) is in the world's ledger."""
    b = H.example_r13()
    extra = P.obs("B3", D[3], 41.0, hour=21)
    b.w.ledger.append(extra)
    b.extra_rows = [extra]
    return b


def ex_two_command_request():
    """0 GENESIS, 1 APPLY D1, 2 APPLY D2, 3-4 one request of two ACK ADDED commands (q1), 5 RESTART_UNKNOWN(D2) (q2)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.apply(D[2], 28.0)
    e1, e2 = P.obs("B1", D[1], 40.0, hour=21), P.obs("B2", D[2], 41.0, hour=21)
    b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [H.fp(e1)], "applied": 1},
                  {"kind": "ACK", "variant": "ADDED", "d": D[2], "fps": [H.fp(e2)], "applied": 2}], "q1")
    b.restart(D[2], "q2")
    b.w.ledger.extend([e1, e2])
    b.extra_rows = [e1, e2]
    return b


class ReadSeries(object):
    """A series whose row(date) refuses one date (as a series with too short a history does) and answers the rest."""

    def __init__(self, base, missing):
        self.base, self.missing = base, set(missing)

    def through(self, d):
        return ReadSeries(self.base.through(d), self.missing)

    def previous_date(self, d):
        return self.base.previous_date(d)

    def row(self, d):
        if d in self.missing:
            raise R_INPUT_ERROR("insufficient_history", "market")
        return self.base.row(d)


from v2_core.errors import InputError as R_INPUT_ERROR  # noqa: E402


def ex_removed_row_after_restart():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2 (R-D2), 4 ROW_REMOVED ACK on seq 3 (q2): R-D2 left the ledger."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    b.ack("ROW_REMOVED", D[2], [], "q2", applied=3)
    b.w.ledger[:] = [r for r in b.w.ledger if r["record_id"] != "R-" + D[2]]
    return b


def without(ledger, record_id):
    return [r for r in ledger if r["record_id"] != record_id]


# --- scenarios for the consumption stop, the references and the recalculation ------------------------------------
def ex_restart_tail():
    """0 GENESIS, 1 APPLY D1, 2 RESTART_UNKNOWN(D3): no APPLY after the restart; D2 and D3 are passed over."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[3], "q1")
    return b


def ex_null_restart():
    """0 GENESIS, 1 RESTART_UNKNOWN(D3): the restart closes a segment that has no APPLY (null base)."""
    b = H.HB()
    b.restart(D[3], "q1")
    return b


def ex_declare_tail():
    """0 GENESIS, 1 APPLY D1, 2 DECLARE_MISSING D2: no APPLY after the declaration."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.declare(D[2], "q1")
    return b


def ex_old_skip():
    """0 GENESIS, 1 APPLY D1, 2 APPLY D3 (skips D2), 3 RESTART_UNKNOWN(D3), 4 APPLY D4: D2 was skipped by an APPLY."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.apply(D[3], 29.0)
    b.restart(D[3], "q1")
    b.apply(D[4], 30.0)
    return b


def ex_old_skip_first():
    """0 GENESIS, 1 APPLY D2 (skips D1), 2 RESTART_UNKNOWN(D2), 3 APPLY D3: the skipping APPLY has the initial state as parent."""
    b = H.HB()
    b.apply(D[2], 27.0)
    b.restart(D[2], "q1")
    b.apply(D[3], 30.0)
    return b


def ex_late_ack_tail():
    """0 GENESIS, 1 APPLY D1, 2 DECLARE D2 (q1), 3 APPLY D3 (skips D2), 4 LATE ACK D2 (q2) that excludes the late row
    L2, 5 RESTART_UNKNOWN(D3) (q3). Restoring at 3 and dropping the LATE ACK lets L2 come back for the declared day."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.declare(D[2], "q1")
    b.apply(D[3], 31.0)
    late = P.obs("L2", D[2], 22.0)
    b.w.ledger.append(late)
    b.extra_rows = [late]
    b.ack("LATE", D[2], [H.fp(late)], "q2", missing=("DECLARE_MISSING", 2))
    b.restart(D[3], "q3")
    return b


def ex_double_restart():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1) (q1), 3 APPLY D2, 4 RESTART(D2) (q2), 5 APPLY D3."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    b.restart(D[2], "q2")
    b.apply(D[3], 31.0)
    return b


def ex_declare_tail_after_restart():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2, 4 DECLARE_MISSING D3 (q2): the declaration has no APPLY after it."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.restart(D[1], "q1")
    b.apply(D[2], 28.0)
    b.declare(D[3], "q2")
    return b


def forge(plan, edit):
    """A RestorePlan whose candidate was changed by edit(events) (the records after the original head), the hashes of the
    records rebuilt (references re-linked), the candidate digest, the candidate records and the plan hash fixed up. It
    stands for a hand-written plan that is internally consistent."""
    data = plan.to_dict()
    basis = data["basis"]
    events = deep(basis["candidate_history"]["events"])
    n = basis["expected_head_seq"] + 1
    edit(events, n)
    hist = H.rebuild(events, remap=True)
    basis["candidate_history"] = hist.to_dict()
    basis["candidate_digest"] = hist.digest
    basis["candidate_records"] = deep(hist.events[n:])
    data["plan_hash"] = H.sha(cj(basis))
    return Z.RestorePlan.from_dict(data)
