"""Helpers for the C-3 (HistoryFileStore) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The existing helpers (c2_helpers, l_helpers) are only imported,
never changed. Every write goes to a dedicated temporary root made by the test itself. Expected values come from the
C-2 builders' own cases and from `file_bytes` (the independent byte writer of c2_helpers), never from the store under
test. Nothing here is part of the product code.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_publish"), os.path.join(ROOT, "tests", "v2_persistence_local")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import c2_helpers as C2  # noqa: E402  (existing helper; it also disables sockets)
import l_helpers as L  # noqa: E402  (existing helper: FaultOps, injected, SECRET)
import v2_history_publish as U  # noqa: E402
from v2_history_local import HistoryFileStore  # noqa: E402

WORKER = os.path.join(HERE, "c3_worker.py")
SECRET = L.SECRET
HIST, LOCK, V1 = "history.json", "write.lock", "snapshot.json"
injected = L.injected


def make_root():
    return tempfile.mkdtemp(prefix="v2c3_root_")


def listing(root):
    return sorted(os.listdir(root))


def raw(root, name=HIST):
    with open(os.path.join(root, name), "rb") as f:
        return f.read()


def put(root, name, data):
    with open(os.path.join(root, name), "wb") as f:
        f.write(data)


def state_of(root):
    """Everything observable about a root: names, bytes, mtimes and inodes (to prove 'unchanged')."""
    out = {}
    for n in sorted(os.listdir(root)):
        p = os.path.join(root, n)
        st = os.lstat(p)
        out[n] = (os.path.isfile(p) and not os.path.islink(p) and raw(root, n) or None, st.st_mtime_ns, st.st_ino)
    return out


class C3Ops(L.FaultOps):
    """The recording / fault-injecting FileOps of S2's tests, with the names of the history root."""

    @staticmethod
    def kind_of(path):
        name = os.path.basename(path)
        if name == LOCK:
            return "lock"
        if name == HIST:
            return "history"
        if name == V1:
            return "snapshot"
        if name.startswith(".history.") and name.endswith(".tmp"):
            return "tmp"
        if name.startswith(".snapshot.") and name.endswith(".tmp"):
            return "s2tmp"
        return "root"


class RootCase(unittest.TestCase):
    """A fresh dedicated root per test, removed by the test harness (explicit test clean-up, not a product feature)."""

    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)

    def store(self, ops=None, **kw):
        kw.setdefault("writable", True)
        if ops is not None:
            kw["_ops"] = ops
        return HistoryFileStore(self.root, **kw)

    def put_current(self, case):
        """Make the root hold the bytes the case's publication expects as the current state (written by the test)."""
        if case.current is not None:
            put(self.root, HIST, case.current)

    def assertStore(self, exc, code, field=None, phase=None, rule=None, cleanup=None):
        self.assertEqual(exc.code, code)
        if field is not None:
            self.assertEqual(exc.field, field)
        if phase is not None:
            self.assertEqual(exc.phase, phase)
        if rule is not None:
            self.assertEqual(exc.rule, rule)
        if cleanup is not None:
            self.assertEqual(tuple(exc.cleanup), tuple(cleanup))

    def run_err(self, fn, *args):
        """The error that fn(*args) raises (the test fails when nothing is raised)."""
        try:
            fn(*args)
        except Exception as e:  # CoreError family (LocalStoreError, PersistenceError)
            return e
        self.fail("expected an error")


def append_cases():
    return [make() for make in C2.APPEND_CASES]


def restore_without_consume():
    return C2.restore_case(consume=False)


# --- independent worker processes -----------------------------------------------------------------------------------

class Worker(object):
    """One independent Python process (c3_worker.py) driven over stdin/stdout lines. Timeouts are test-side only; a
    reader thread feeds a queue so the driver also works where select() cannot wait on pipes (Windows)."""

    def __init__(self, spec, timeout=90):
        self.timeout = timeout
        self.events = []
        self.stderr = b""
        self.proc = subprocess.Popen([sys.executable, "-B", "-I", WORKER, json.dumps(spec)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._q = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self):
        for line in iter(self.proc.stdout.readline, b""):
            self._q.put(line)
        self._q.put(None)

    def _line(self, deadline):
        try:
            line = self._q.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            self.kill()
            raise AssertionError("worker timed out")
        return None if line is None else json.loads(line.decode("utf-8"))

    def next(self):
        ev = self._line(time.monotonic() + self.timeout)
        if ev is not None:
            self.events.append(ev)
        return ev

    def expect(self, name):
        ev = self.next()
        if ev is None or ev.get("event") != name:
            self.kill()
            raise AssertionError("expected %s, got %r" % (name, ev))
        return ev

    def send(self, text):
        self.proc.stdin.write((text + "\n").encode("ascii"))
        self.proc.stdin.flush()

    def wait(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        rc = self.proc.wait(timeout=self.timeout)
        self._reader.join(timeout=self.timeout)
        self.proc.stdout.close()
        self.stderr = self.proc.stderr.read()
        self.proc.stderr.close()
        return rc

    def kill(self):
        """Test-side clean-up: stop the process (if still running) and close its pipes."""
        try:
            self.proc.kill()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=30)
        finally:
            self._reader.join(timeout=5)
            for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                try:
                    f.close()
                except Exception:
                    pass

    def result(self):
        ev = self.expect("RESULT")
        rc = self.wait()
        assert rc == 0, (rc, self.stderr[-2000:])
        return ev


# --- the one-day scenario shared by the parent and the worker processes ------------------------------------------------

def day1():
    """(history, publication): GENESIS only, and the DAILY publication of the first day. Deterministic (the synthetic
    world of the existing helpers), so a child process builds the same values as its parent. Also returns the world's
    inputs of publish_day for a child that builds the publication again from the current history."""
    b = C2.H.HB()
    h, w = b.history(), b.w
    w.ledger.append(C2.P.obs("R1", C2.D[1], 27.0))
    pub = U.publish_day(h, C2.D[1], w.series, w.sessions, w.ledger)
    return h, pub, w


def day1_root(root):
    """Write the GENESIS-only history into a root (by the test) and return (history, publication, world)."""
    h, pub, w = day1()
    put(root, HIST, C2.file_bytes(h))
    return h, pub, w
