"""Helpers for the v2_recovery tests. Synthetic sessions, rows and ledgers; no calendar, no clock, no file of its own.

Sockets are disabled on import (as in the other test packages). The existing helper p_helpers (v2_persistence tests) is
reused read-only for the sessions, the market stub and the World scenario builder.
"""
import copy
import os
import socket
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import p_helpers as P  # noqa: E402  (existing helper; it also disables sockets)
import v2_recovery as R  # noqa: E402
from v2_core.errors import ConflictError, InputError  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_persistence.recompute import validate_snapshot  # noqa: E402
from v2_recovery import ledger as L  # noqa: E402
from v2_recovery.common import basis_request_hash, record_hash_of  # noqa: E402


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_recovery tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket
socket.create_connection = _blocked

D = P.DATES
WHEN = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
ACK_REASON, DECL_REASON, BATCH_REASON = "ACKNOWLEDGE_LEDGER_CHANGE", "MARK_SESSION_MISSING", "RESOLUTION_BATCH"
URL = "https://example.invalid/secret-token-path"


def fp(row):
    return L.parse_row(row).fp


def cols(row):
    return L.parse_row(row).cols


def ref_of(snapshot, seq):
    ap = validate_snapshot(snapshot).applies[seq - 1]
    return {"seq": ap.seq, "event_hash": ap.event_hash, "fingerprint": ap.fingerprint}


def apply_missing(snapshot, seq):
    return {"kind": "APPLY", "seq": seq, "event_hash": snapshot.events[seq]["event_hash"]}


def declare_missing(rs, resolution_seq):
    rec = rs.records[resolution_seq - 1]
    return {"kind": "DECLARE_MISSING", "resolution_seq": rec["resolution_seq"], "resolution_hash": rec["resolution_hash"]}


def cmd(kind, variant, d, fps=(), applied=None, missing=None):
    return {"kind": kind, "variant": variant, "d": d, "record_fingerprints": list(fps), "applied_ref": applied,
            "missing_ref": missing}


def ack(snapshot, variant, d, fps, seq=1):
    return cmd("ACK", variant, d, fps, applied=ref_of(snapshot, seq))


def late(d, fps, missing):
    return cmd("ACK", "LATE", d, fps, missing=missing)


def declare(d, fps=()):
    return cmd("DECLARE_MISSING", None, d, fps)


def reason_for(cmds):
    kinds = {c["kind"] for c in cmds}
    return ACK_REASON if kinds == {"ACK"} else DECL_REASON if kinds == {"DECLARE_MISSING"} else BATCH_REASON


def world(n_applies=1, values=None):
    w = P.World()
    for i in range(1, n_applies + 1):
        v = (values or {}).get(i, 27.0)
        w.apply(D[i], v, "R%d" % i)
    return w


def plan_for(w, rs, cmds, ledger, check_d, rid="req-1", reason=None, when=WHEN, snapshot=None):
    return R.prepare_resolution_plan(snapshot if snapshot is not None else w.snap(), rs, cmds, w.sessions, ledger,
                                     check_d, rid, reason or reason_for(cmds), when)


def run(w, rs, cmds, ledger, check_d, rid="req-1", reason=None, snapshot=None):
    """prepare + confirm. Returns the ConfirmResult."""
    snap = snapshot if snapshot is not None else w.snap()
    plan = plan_for(w, rs, cmds, ledger, check_d, rid, reason, snapshot=snap)
    return R.confirm_resolution_plan(plan, plan.plan_hash, snap, rs, w.sessions, ledger)


def resolve(w, rs, ledger, check_d, snapshot=None):
    return R.resolve_observations(snapshot if snapshot is not None else w.snap(), rs, w.sessions, ledger, check_d)


def forge(rs, mutate, rehash=True):
    """Mutate the record dicts, then (by default) rebuild hash, parent and head so only the content is wrong."""
    data = rs.to_dict()
    mutate(data["records"])
    if rehash:
        prev = None
        for i, r in enumerate(data["records"]):
            r["resolution_seq"] = i + 1
            r["parent_resolution_hash"] = prev
            r["resolution_hash"] = record_hash_of(r)
            prev = r["resolution_hash"]
        data["head_resolution_seq"] = len(data["records"])
        data["head_resolution_hash"] = prev
    return R.ResolutionSet.from_dict(data)


def refresh_request(rec):
    """Recompute request_hash of one record from its (edited) request_basis."""
    rec["request_hash"] = basis_request_hash(rec["request_basis"])


def rule_of(case, fn, *args, **kwargs):
    with case.assertRaises(PersistenceError) as cm:
        fn(*args, **kwargs)
    e = cm.exception
    case.assertEqual(e.code, "resolution_invalid", "code %s rule %s" % (e.code, e.rule))
    return e.rule


def expect_rule(case, rule, fn, *args, **kwargs):
    got = rule_of(case, fn, *args, **kwargs)
    case.assertEqual(got, rule)


def expect_code(case, code, fn, *args, **kwargs):
    with case.assertRaises((PersistenceError, InputError, ConflictError)) as cm:
        fn(*args, **kwargs)
    case.assertEqual(cm.exception.code, code)
    return cm.exception


def extend_with_s1(w, d, ledger):
    """An independent S1 APPLY for D, made with S1 directly (the S3-A result is never converted to a plan)."""
    res = P.prepare_day(w.snap(), d, w.series, w.sessions, ledger)
    assert res.plan is not None
    w.store.commit(res.plan)
    return w.snap()


def deep(x):
    return copy.deepcopy(x)


def cj(x):
    return canonical_json(x)
