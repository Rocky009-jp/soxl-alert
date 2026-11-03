"""Helpers for the C-2 (publication) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The existing helpers (h_helpers, ho_helpers, r3_helpers,
r4_helpers, c1_helpers, a5_helpers) are only imported, never changed. Every expected value comes from the existing
confirming functions, from `check_append_batch`, from the history checker and from plain hashlib, never from the
package under test: `expected_*` below are written without it.

A Case holds the inputs of one source, the publication that its builder made, the bytes that the publication expects
as the current state, and the candidate History that the existing confirming step returned for the same inputs.
"""
import copy
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _name in ("v2_history_consume", "v2_history_adopt", "v2_history_restart", "v2_history_restore", "v2_history_ops",
              "v2_history_diagnose", "v2_history"):
    _p = os.path.join(ROOT, "tests", _name)
    if _p not in sys.path:
        sys.path.insert(0, _p)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import a5_helpers as A5  # noqa: E402  (existing helper; it also disables sockets)
import c1_helpers as C1  # noqa: E402
import h_helpers as HH  # noqa: E402
import ho_helpers as T  # noqa: E402
import r3_helpers as R3  # noqa: E402
import v2_history as V  # noqa: E402
import v2_history_adopt as AD  # noqa: E402
import v2_history_ops as O  # noqa: E402
import v2_history_publish as U  # noqa: E402
import v2_history_restart as RT  # noqa: E402
import v2_history_restore as RS  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_history_ops.values import digest_of  # noqa: E402
from v2_persistence.codec import canonical_json, encode_snapshot  # noqa: E402
from v2_recovery.ledger import sessions_digest  # noqa: E402

H, P, D, WHEN = HH, T.P, T.D, T.WHEN
ZERO = "0" * 64
UNSET = object()


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw_of(data):
    """The identity of raw bytes, from hashlib directly."""
    return {"raw_sha256": sha(data), "raw_size": len(data)}


def file_bytes(history):
    """The bytes a store would hold for a History: the canonical text, UTF-8, no BOM, no newline (written here, not by
    the package under test)."""
    return V.encode_history(history).encode("utf-8")


def indented(history):
    """A valid text of the same history that is not canonical (indented, keys in file order)."""
    import json
    return json.dumps(history.to_dict(), indent=2).encode("utf-8")


def err(fn, *args, **kwargs):
    """(code, field, rule) of the refusal of fn; fails when fn does not raise a CoreError."""
    try:
        fn(*args, **kwargs)
    except CoreError as e:
        return (e.code, e.field, getattr(e, "rule", None))
    raise AssertionError("expected a refusal")


def refusal(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except CoreError as e:
        return e
    raise AssertionError("expected a refusal")


def rehash(pub, fn):
    """A publication whose body was changed by fn(body) and whose hash was written again (so that only the content is
    wrong). Made with the private constructor, which the tests may use (the range test limits the runtime)."""
    body = pub.body
    fn(body)
    return U.HistoryPublication._make(body)


class Case(object):
    def __init__(self, source, pub, current, candidate, **more):
        self.source, self.pub, self.current, self.candidate = source, pub, current, candidate
        self.source_v1 = None
        self.__dict__.update(more)

    def check(self, current=UNSET, source_v1=UNSET):
        """check_publication with the case's own current bytes and v1 bytes unless others are given."""
        return U.check_publication(self.current if current is UNSET else current, self.pub,
                                   self.source_v1 if source_v1 is UNSET else source_v1)

    def reconcile(self, current=UNSET):
        return U.reconcile_publication(self.current if current is UNSET else current, self.pub)


# --- the seven sources ----------------------------------------------------------------------------------------------
def day_case():
    """0 GENESIS, 1 APPLY D1; the day D2 is new."""
    b = H.HB()
    b.apply(D[1], 27.0)
    h, w = b.history(), b.w
    w.ledger.append(P.obs("R2", D[2], 31.0))
    res = T.day(h, D[2], w)
    candidate = O.check_append_batch(h, res.batch)
    pub = U.publish_day(h, D[2], w.series, w.sessions, w.ledger)
    return Case("DAILY", pub, file_bytes(h), candidate, history=h, w=w, d=D[2], batch=res.batch)


def resolution_case():
    """An ACK ADDED of D1 (one acknowledgement record)."""
    b = H.HB()
    b.apply(D[1], 27.0)
    h, w = b.history(), b.w
    x = P.obs("x", D[1], 22.0)
    ledger = list(w.ledger) + [x]
    cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
    plan = T.plan_for(h, cmds, w.sessions, ledger, D[2], "q1")
    conf = O.confirm_history_resolution_plan(plan, plan.plan_hash, h, w.sessions, ledger)
    pub = U.publish_resolution(plan, plan.plan_hash, h, w.sessions, ledger)
    return Case("RESOLUTION", pub, file_bytes(h), conf.history, history=h, w=w, plan=plan, ledger=ledger, conf=conf)


def restart_case():
    """GENESIS, APPLY D1, APPLY D2; the restart is written now."""
    b = R3.example_u()
    h, w = b.history(), b.w
    plan = R3.prep(h, w, D[3], D[3], "q1")
    conf = RT.confirm_restart_plan(plan, plan.plan_hash, h, w.sessions, w.ledger)
    pub = U.publish_restart(plan, plan.plan_hash, h, w.sessions, w.ledger)
    return Case("RESTART", pub, file_bytes(h), conf.history, history=h, w=w, plan=plan, conf=conf)


def restore_case(consume=True):
    """consume=True: C-1's scenario, DROP 4, CONSUME D3 (a new APPLY), REAPPLY 5. consume=False: a restore that
    drops the restart written too early and applies the day again (no decision of a freed day, no CONSUME)."""
    if consume:
        b = C1.s_declare()
        plan = C1.plan(b, 3, [("DROP", 4), (C1.CONSUME, D[3]), ("REAPPLY", 5)], D[5])
    else:
        b = C1.R.ex_restart_between()
        plan = C1.R.prep(b, 1, {2: "DROP", "*": "REAPPLY"}, D[3], "c2-r")
    h, w = b.history(), b.w
    conf = RS.confirm_restore_plan(plan, plan.plan_hash, h, w.sessions, w.ledger, w.series)
    pub = U.publish_restore(plan, plan.plan_hash, h, w.sessions, w.ledger, w.series)
    return Case("RESTORE", pub, file_bytes(h), conf.history, history=h, w=w, plan=plan, conf=conf, builder=b)


def genesis_case():
    w = P.World()
    candidate = V.make_history_genesis(w.start_after, w.sessions)
    pub = U.publish_genesis(w.start_after, w.sessions)
    return Case("GENESIS", pub, None, candidate, w=w)


def migration_case():
    w, snap, rs, ledger, check_d = HH.example_m_world()
    plan = V.prepare_migration_plan(snap, rs, w.sessions, ledger, check_d, "mig-1", WHEN)
    conf = V.confirm_migration_plan(plan, plan.plan_hash, snap, rs, w.sessions, ledger)
    data = encode_snapshot(snap).encode("utf-8")
    pub = U.publish_migration(plan, plan.plan_hash, data, rs, w.sessions, ledger)
    c = Case("MIGRATION", pub, None, conf.history, w=w, snap=snap, rs=rs, ledger=ledger, plan=plan, data=data)
    c.source_v1 = data
    return c


def adoption_case():
    """A damaged history file (the last record has a wrong hash): the verified prefix plus one adoption record."""
    b, data, k = A5.new_world()
    plan = A5.prep(data, k)
    conf = AD.confirm_prefix_adoption(plan, plan.plan_hash, data)
    pub = U.publish_adoption(plan, plan.plan_hash, data)
    return Case("ADOPTION", pub, data, conf.history, plan=plan, data=data, k=k, conf=conf, builder=b)


ALL_CASES = (day_case, resolution_case, restart_case, restore_case, genesis_case, migration_case, adoption_case)


def every_case():
    return [make() for make in ALL_CASES]


APPEND_CASES = (day_case, resolution_case, restart_case, restore_case)


def extended_history(case):
    """The candidate of a case with one more APPLY after it, written by the independent record builder: the history that
    a later writer leaves when it appends to the published bytes."""
    world = case.builder.w if hasattr(case, "builder") else case.w
    events = case.candidate.events
    applied = [e["d"] for e in events if e["kind"] == "APPLY"]
    nxt = D[D.index(applied[-1]) + 1] if applied else D[1]
    if case.source == "RESTART":
        nxt = D[4]                                # the restart resumes after D3
    has_row = any(r["target_us_session_date"] == nxt for r in world.ledger)
    b = HH.HB(world=world, events=events)
    b.apply(nxt, None if has_row else 44.0)
    return b.history()


def other_extension(case):
    """A valid history that extends the history the case started from by another record than the publication's (so it
    is neither the bytes the publication expects nor the bytes it makes). Only for the cases whose base ends with an
    APPLY that a later day can follow without a late observation."""
    base = case.history
    world = case.w
    nxt = D[D.index([e["d"] for e in base.events if e["kind"] == "APPLY"][-1]) + 1]
    saved = world.ledger
    world.ledger = [r for r in saved if r["target_us_session_date"] != nxt]
    try:
        b = HH.HB(world=world, events=base.events)
        b.apply(nxt, 55.5)
        return b.history()
    finally:
        world.ledger = saved
