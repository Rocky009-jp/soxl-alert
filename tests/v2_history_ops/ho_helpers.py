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
