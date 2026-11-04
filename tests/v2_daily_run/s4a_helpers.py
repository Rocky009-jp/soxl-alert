"""Helpers for the S4-A (morning run) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The existing helpers (p_helpers, h_helpers, ho_helpers, c2_helpers,
c3_helpers) are only imported, never changed. Every write goes to a dedicated temporary root made by the test itself.
Expected values come from the existing functions (prepare_history_day, check_append_batch, validate_history,
render_message) and from the independent history builder HB, never from the runner under test.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_local"), os.path.join(ROOT, "tests", "v2_history_publish"),
           os.path.join(ROOT, "tests", "v2_history_restart"), os.path.join(ROOT, "tests", "v2_history_ops")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import c2_helpers as C2  # noqa: E402  (existing helper; it also disables sockets)
import c3_helpers as C3  # noqa: E402
import v2_history as V  # noqa: E402
import v2_history_ops as O  # noqa: E402
import v2_history_publish as U  # noqa: E402
from v2_core.display import render_message  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_history_local import HistoryFileStore, LocalStoreError  # noqa: E402

D, P, H, T = C2.D, C2.P, C2.H, C2.T
TZ = P.TZ
WORKER = os.path.join(HERE, "s4a_worker.py")
HIST, LOCK, V1 = C3.HIST, C3.LOCK, C3.V1
DURABILITY = "file_sync_only"           # the same bytes and steps as strict, without the directory sync (any host)


def now_at(d, hour=18):
    """A time after D's close (16:00 at TZ) and before the next open."""
    y, m, dd = (int(x) for x in d.split("-"))
    return datetime(y, m, dd, hour, 0, tzinfo=TZ)


def close_at(d):
    return P.make_session(d).close_at


def decide(w, indexes, base=25.0):
    """Add a decision observation for each index of D to the world's ledger (record id R<i>)."""
    for i in indexes:
        w.ledger.append(P.obs("R%d" % i, D[i], base + i))


def make_root():
    return tempfile.mkdtemp(prefix="v2s4_root_")


def raw(root, name=HIST):
    with open(os.path.join(root, name), "rb") as f:
        return f.read()


def put(root, name, data):
    with open(os.path.join(root, name), "wb") as f:
        f.write(data)


def signal(path):
    """Create the file the children wait for."""
    with open(path, "wb") as f:
        f.write(b"go")


def state_of(root):
    return C3.state_of(root)


def genesis_pub(w):
    return U.publish_genesis(w.start_after, w.sessions)


def real_store(root, w, writable=True, initialize=True):
    st = HistoryFileStore(root, writable=True, durability=DURABILITY)
    if initialize:
        st.initialize(genesis_pub(w))
    return st if writable else HistoryFileStore(root, writable=False, durability=DURABILITY)


def expected_history(w, last_index, ledger=None, only=None):
    """The history after the independent chain: genesis, then prepare_history_day -> check_append_batch for every
    session after the start up to D[last_index] (for each day that is PREPARED)."""
    h = V.make_history_genesis(w.start_after, w.sessions)
    ledger = w.ledger if ledger is None else ledger
    for i in range(1, last_index + 1):
        if only is not None and i not in only:
            continue
        res = O.prepare_history_day(h, D[i], w.series, w.sessions, ledger)
        if res.status == O.PREPARED:
            h = O.check_append_batch(h, res.batch)
    return h


def expected_bytes(w, last_index, ledger=None):
    return C2.file_bytes(expected_history(w, last_index, ledger))


def applies_of(root):
    """The d of every APPLY record of the stored history, in file order (read from the file, not from the store)."""
    data = json.loads(raw(root).decode("utf-8"))
    return [e["d"] for e in data["events"] if e["kind"] == "APPLY"]


def run(store, w, now, **kw):
    import v2_daily_run
    return v2_daily_run.run_morning(store, now, kw.get("series", w.series), kw.get("sessions", w.sessions),
                                    kw.get("ledger", w.ledger))


class Recording(object):
    """Wraps a store; logs every call (name, and the publication hash for publish / reconcile)."""

    def __init__(self, inner):
        self.inner, self.calls, self.hashes = inner, [], []

    def read(self):
        self.calls.append("read")
        return self.inner.read()

    def publish(self, publication):
        self.calls.append("publish")
        self.hashes.append(publication.publication_hash)
        return self.inner.publish(publication)

    def reconcile(self, publication):
        self.calls.append("reconcile")
        return self.inner.reconcile(publication)

    def count(self, name):
        return self.calls.count(name)


class Silent(object):
    """A store that must never be touched: every call is recorded and fails."""

    def __init__(self):
        self.calls = []

    def read(self):
        self.calls.append("read")
        raise AssertionError("the store was touched")

    def publish(self, publication):
        self.calls.append("publish")
        raise AssertionError("the store was touched")

    def reconcile(self, publication):
        self.calls.append("reconcile")
        raise AssertionError("the store was touched")


class RootCase(unittest.TestCase):
    """A fresh dedicated root and world per test, removed by the test harness (explicit test clean-up)."""

    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.w = P.World(0)

    def store(self, **kw):
        return real_store(self.root, self.w, **kw)

    def assertFileIs(self, history):
        self.assertEqual(raw(self.root), C2.file_bytes(history))


def uncertain(phase="dir_sync"):
    return LocalStoreError("store_commit_uncertain", "history", phase)


class Flaky(object):
    """A store over a real HistoryFileStore with scripted faults.

    publish_plan: {n: action} for the n-th publish call (1-based), action in
      'uncertain_after_write'   the real publish happens, then store_commit_uncertain is raised
      'uncertain_without_write' nothing is written, store_commit_uncertain is raised
      'other_writer_first'      another writer appends the same day first (the run's value is then stale)
      ('hook_after_write', fn)  like uncertain_after_write, fn(inner) runs after the write and before the error
      ('hook_without_write', fn) like uncertain_without_write, fn(inner) runs before the error
    reconcile_plan: None (the real one), ('raise', error), ('outcome', text), ('hook', fn) (fn(inner) then real).
    """

    def __init__(self, inner, publish_plan=None, reconcile_plan=None):
        self.inner, self.publish_plan, self.reconcile_plan = inner, dict(publish_plan or {}), reconcile_plan
        self.calls, self.hashes, self.n_publish = [], [], 0

    def read(self):
        self.calls.append("read")
        return self.inner.read()

    def publish(self, publication):
        self.calls.append("publish")
        self.hashes.append(publication.publication_hash)
        self.n_publish += 1
        action = self.publish_plan.get(self.n_publish)
        if action is None:
            return self.inner.publish(publication)
        kind = action[0] if isinstance(action, tuple) else action
        if kind == "uncertain_after_write":
            self.inner.publish(publication)
            raise uncertain()
        if kind == "uncertain_without_write":
            raise uncertain()
        if kind == "hook_after_write":
            self.inner.publish(publication)
            action[1](self.inner)
            raise uncertain()
        if kind == "hook_without_write":
            action[1](self.inner)
            raise uncertain()
        if kind == "other_writer_first":
            action[1](self.inner)
            return self.inner.publish(publication)
        raise AssertionError(kind)

    def reconcile(self, publication):
        self.calls.append("reconcile")
        plan = self.reconcile_plan
        if plan is None:
            return self.inner.reconcile(publication)
        if plan[0] == "raise":
            raise plan[1]
        if plan[0] == "outcome":
            return _Outcome(plan[1])
        if plan[0] == "hook":
            plan[1](self.inner)
            return self.inner.reconcile(publication)
        raise AssertionError(plan[0])

    def count(self, name):
        return self.calls.count(name)


class _Outcome(object):
    def __init__(self, outcome):
        self.outcome = outcome


class Child(object):
    """One independent Python process (s4a_worker.py). The child prints READY, spins until the GO file exists, runs the
    morning once and prints one JSON line. Timeouts are test-side only."""

    def __init__(self, spec, timeout=180):
        self.timeout = timeout
        self.proc = subprocess.Popen([sys.executable, "-B", "-I", WORKER, json.dumps(spec)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def ready(self):
        line = self.proc.stdout.readline()
        if json.loads(line.decode("utf-8")).get("event") != "READY":
            raise AssertionError("not ready")

    def result(self):
        out, err = self.proc.communicate(timeout=self.timeout)
        if self.proc.returncode != 0:
            raise AssertionError((self.proc.returncode, err[-2000:]))
        return json.loads(out.decode("utf-8").strip().splitlines()[-1])


def probe_imports():
    """The modules a fresh interpreter has loaded after importing the runtime (a child, isolated mode)."""
    code = ("import sys; sys.path.insert(0, %r); import v2_daily_run; "
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0].startswith('v2_'))))") % ROOT
    out = subprocess.run([sys.executable, "-B", "-I", "-c", "import json\n" + code], capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def read_source(relative):
    """The text of a file of the working tree (the static audits read the runtime files that are about to be tested)."""
    with open(os.path.join(ROOT, relative), "rb") as f:
        return f.read().decode("utf-8")
