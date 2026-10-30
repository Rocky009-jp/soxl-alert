"""Helpers for the v2_history_ops tests (never imported by the runtime). Synthetic sessions, series and ledgers.

Sockets are disabled on import (as in the other test packages). The existing helpers h_helpers / r_helpers /
p_helpers are reused read-only.
"""
import copy
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history"), os.path.join(ROOT, "tests", "v2_recovery"),
           os.path.join(ROOT, "tests", "v2_persistence")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import h_helpers as H  # noqa: E402  (existing helper; it also disables sockets)
from v2_core.errors import ConflictError, InputError  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_recovery.facts import FixedFacts  # noqa: E402

P, R, RH, D, WHEN = H.P, H.R, H.RH, H.D, H.WHEN


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_history_ops tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket
socket.create_connection = _blocked


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def facts_of_snapshot(snap, records=()):
    """FixedFacts for an S1 Snapshot (one segment). Declarations come from S3-A records (resolution_seq / hash are
    used as the reference numbers)."""
    ev = snap.events
    g = ev[0]
    applies = [{"seq": e["seq"], "event_hash": e["event_hash"], "d": e["d"],
                "decision": e["confirmed_inputs"]["decision"], "context": e["confirmed_inputs"]["session_context"],
                "skipped": e["skipped_sessions"]} for e in ev[1:]]
    decl = [{"seq": r["resolution_seq"], "event_hash": r["resolution_hash"], "d": r["d"],
             "context": r["session_context"]} for r in records if r["kind"] == "DECLARE_MISSING"]
    return FixedFacts.from_parts(applies, decl, [{"date": g["start_after"], "session": g["boundary_session"]}],
                                 g["start_after"], snap.head_seq)


def outcome(fn, *args, **kwargs):
    """('ok', value) or ('err', code, field, rule) for a call that may raise one of the project error types."""
    try:
        return ("ok", fn(*args, **kwargs))
    except (PersistenceError, InputError, ConflictError) as e:
        return ("err", e.code, e.field, getattr(e, "rule", None))


# --- v2 commands, plans and batches ------------------------------------------------------------------------------
import v2_history as V  # noqa: E402
import v2_history_ops as O  # noqa: E402

ACK_REASON, DECL_REASON, BATCH_REASON = RH.ACK_REASON, RH.DECL_REASON, RH.BATCH_REASON
CHECK_D = H.CHECK_D


def applies_of(history):
    return {a["seq"]: a for a in O.read_effective(history).applies}


def aref(history, seq):
    a = applies_of(history)[seq]
    return {"seq": a["seq"], "event_hash": a["event_hash"], "fingerprint": a["fingerprint"]}


def mref_apply(history, seq):
    return {"kind": "APPLY", "seq": seq, "event_hash": history.events[seq]["event_hash"]}


def mref_decl(history, seq):
    return {"kind": "DECLARE_MISSING", "seq": seq, "event_hash": history.events[seq]["event_hash"]}


def cmd(kind, variant, d, fps=(), applied=None, missing=None):
    return {"kind": kind, "variant": variant, "d": d, "record_fingerprints": list(fps), "applied_ref": applied,
            "missing_ref": missing}


def ack_cmd(history, variant, d, fps, applied_seq):
    return cmd("ACK", variant, d, fps, applied=aref(history, applied_seq))


def late_cmd(d, fps, missing):
    return cmd("ACK", "LATE", d, fps, missing=missing)


def decl_cmd(d, fps=()):
    return cmd("DECLARE_MISSING", None, d, fps)


def reason_for(cmds):
    kinds = {c["kind"] for c in cmds}
    return ACK_REASON if kinds == {"ACK"} else DECL_REASON if kinds == {"DECLARE_MISSING"} else BATCH_REASON


def plan_for(history, cmds, sessions, ledger, check_d, rid, reason=None, when=WHEN):
    return O.prepare_history_resolution_plan(history, cmds, sessions, ledger, check_d, rid,
                                             reason or reason_for(cmds), when)


def run_plan(history, cmds, sessions, ledger, check_d, rid, reason=None):
    """prepare + confirm. Returns (plan, ConfirmResult)."""
    plan = plan_for(history, cmds, sessions, ledger, check_d, rid, reason)
    return plan, O.confirm_history_resolution_plan(plan, plan.plan_hash, history, sessions, ledger)


def extend(history, result):
    """The history after the batch of a confirm result / day result is accepted."""
    return O.check_append_batch(history, result.batch)


def fp(row):
    return RH.fp(row)


def row(record_id, d, value, hour=20):
    return P.obs(record_id, d, value, hour=hour)


def err(fn, *args, **kwargs):
    """('code', 'field', 'rule') of the refusal of fn."""
    out = outcome(fn, *args, **kwargs)
    assert out[0] == "err", "expected a refusal, got %r" % (out,)
    return out[1:]


def day(history, d, w, ledger=None):
    return O.prepare_history_day(history, d, w.series, w.sessions, w.ledger if ledger is None else ledger)


def refusal(fn, *args, **kwargs):
    """The refusal exception itself (code, field, rule and detail are fixed identifiers)."""
    try:
        fn(*args, **kwargs)
    except (PersistenceError, InputError, ConflictError) as e:
        return e
    raise AssertionError("expected a refusal")


def example_v():
    """Design 12.3: 0 GENESIS(D0), 1 APPLY D1, 2 DECLARE_MISSING D2 (q1), 3 RESTART_UNKNOWN(resume_after=D3) (q2)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.declare(D[2], "q1")
    b.restart(D[3], "q2")
    return b
