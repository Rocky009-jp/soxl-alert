"""Helpers for the v2_history_restart tests (never imported by the runtime). Synthetic sessions, series and ledgers.

Sockets are disabled on import (as in the other test packages). The existing helpers ho_helpers / h_helpers /
r_helpers / p_helpers are only imported, never changed. The scenario builders write histories with the independent
test-only record builder HB (h_helpers), so an expected RESTART_UNKNOWN is built without the runtime under test.
"""
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_ops")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ho_helpers as T  # noqa: E402  (existing helper; it also disables sockets)
import v2_history as V  # noqa: E402
import v2_history_ops as O  # noqa: E402
import v2_history_restart as X  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402

H, P, D, WHEN = T.H, T.P, T.D, T.WHEN
FIXED_START = "b328844fdeda235cf95bf7851ba9e3d7d55aa7bb"
INIT = None


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def prep(history, w, resume, check, rid, sessions=None, ledger=None, when=WHEN):
    return X.prepare_restart_plan(history, resume, w.sessions if sessions is None else sessions,
                                  w.ledger if ledger is None else ledger, check, rid, when)


def confirm(plan, history, w, sessions=None, ledger=None, plan_hash=None):
    return X.confirm_restart_plan(plan, plan.plan_hash if plan_hash is None else plan_hash, history,
                                  w.sessions if sessions is None else sessions,
                                  w.ledger if ledger is None else ledger)


def run(history, w, resume, check, rid):
    plan = prep(history, w, resume, check, rid)
    return plan, confirm(plan, history, w)


def refusal(fn, *args, **kwargs):
    return T.err(fn, *args, **kwargs)


def example_u():
    """Design 11.1: GENESIS D0, APPLY D1, APPLY D2. The restart is planned, not yet written."""
    b = H.HB()
    b.apply(D[1], 27.0)
    b.apply(D[2], 28.0)
    return b


def with_plan_dict(plan, fn):
    """A RestartPlan from the plan's dict after fn(dict) changed it (the hash is not fixed up)."""
    data = plan.to_dict()
    fn(data)
    return X.RestartPlan.from_dict(data)


def refreshed(plan, fn):
    """A RestartPlan whose basis was changed by fn(basis) and whose plan_hash was recomputed to match."""
    data = plan.to_dict()
    fn(data["basis"])
    data["plan_hash"] = H.sha(cj(data["basis"]))
    return X.RestartPlan.from_dict(data)


def expected_restart(builder, resume, rid, check_d):
    """The RESTART_UNKNOWN record that the independent builder writes for the same request."""
    b = H.HB(world=builder.w, events=builder.events)
    b.restart(resume, rid, check_d)
    return b.events[-1]


# --- sessions ----------------------------------------------------------------------------------------------------
import dataclasses  # noqa: E402
from datetime import timedelta  # noqa: E402


def earlier_close(session):
    """The same session with a different close time (a harmless-looking but real difference)."""
    return dataclasses.replace(session, close_at=session.close_at - timedelta(minutes=5))


def later_open(session):
    return dataclasses.replace(session, open_at=session.open_at + timedelta(minutes=5))


def sessions_with(overrides=None, unconfirmed=(), dates=None):
    return P.make_sessions(dates=dates, unconfirmed=unconfirmed, overrides=overrides)
