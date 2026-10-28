"""Helpers for the v2_persistence.local tests: sandboxed roots, a scenario builder, a recording / fault-injecting
FileOps and an independent-process worker driver.

Sockets are disabled on import (as in the other test packages). Every write goes to a dedicated temporary root made
by the test itself. Nothing here is part of the product code.
"""
import copy
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import p_helpers as P  # noqa: E402  (existing helper, read-only reuse; it also disables sockets)
from v2_persistence.codec import decode_snapshot, encode_snapshot  # noqa: E402
from v2_persistence.local import LocalFileStore  # noqa: E402
from v2_persistence.local.fsops import FileOps  # noqa: E402
from v2_persistence.plan import AppendPlan  # noqa: E402
from v2_persistence.runner import make_genesis, prepare_day  # noqa: E402


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_persistence.local tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket
socket.create_connection = _blocked

WORKER = os.path.join(HERE, "worker.py")
SECRET = "/secret/dedicated-path"          # appears only inside injected OSErrors; must never reach a public error
SNAP, LOCK = "snapshot.json", "write.lock"


def make_root():
    return tempfile.mkdtemp(prefix="v2s2_root_")


def listing(root):
    return sorted(os.listdir(root))


def raw(root, name=SNAP):
    with open(os.path.join(root, name), "rb") as f:
        return f.read()


def put(root, name, data):
    with open(os.path.join(root, name), "wb") as f:
        f.write(data)


def state_of(root):
    """Everything observable about a root: names, bytes, mtimes (to prove 'unchanged')."""
    out = {}
    for n in sorted(os.listdir(root)):
        p = os.path.join(root, n)
        st = os.lstat(p)
        out[n] = (os.path.isfile(p) and not os.path.islink(p) and raw(root, n) or None, st.st_mtime_ns, st.st_ino)
    return out


class RootCase(unittest.TestCase):
    """A fresh dedicated root per test, removed by the test harness (explicit test clean-up, not a product feature)."""

    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)

    def store(self, **kw):
        kw.setdefault("writable", True)
        return LocalFileStore(self.root, **kw)

    def assertCode(self, exc, code, field=None, phase=None):
        self.assertEqual(exc.code, code)
        if field is not None:
            self.assertEqual(exc.field, field)
        if phase is not None:
            self.assertEqual(exc.phase, phase)


class Scenario(object):
    """Synthetic sessions / series / ledger (from the existing p_helpers). Not a market calendar."""

    def __init__(self, start_idx=0):
        self.sessions = P.make_sessions()
        self.series = P.make_series()
        self.start_after = P.DATES[start_idx]
        self.genesis = make_genesis(self.start_after, self.sessions)
        self.ledger = []
        self.dates = P.DATES

    def day(self, i):
        """The i-th session after start_after (1-based)."""
        return self.dates[self.dates.index(self.start_after) + i]

    def observe(self, d, value, record_id=None, ledger=None):
        (self.ledger if ledger is None else ledger).append(P.obs(record_id or ("R-%s-%s" % (d, value)), d, value))

    def prepare(self, snapshot, d, ledger=None):
        return prepare_day(snapshot, d, self.series, self.sessions, self.ledger if ledger is None else ledger)

    def plan_for(self, snapshot, d, value, record_id=None, base=None):
        led = copy.deepcopy(self.ledger if base is None else base)
        self.observe(d, value, record_id, ledger=led)
        res = self.prepare(snapshot, d, led)
        assert res.plan is not None, res.status
        return res.plan

    def advance(self, store, n, value=50):
        """Apply n consecutive days to the store through the real prepare -> commit path."""
        for _ in range(n):
            snap = store.read()
            d = self.next_day(snap)
            self.observe(d, value)
            res = self.prepare(snap, d)
            assert res.plan is not None, res.status
            store.commit(res.plan)

    def next_day(self, snapshot):
        applies = [e for e in snapshot.events if e["kind"] == "APPLY"]
        last = applies[-1]["d"] if applies else self.start_after
        return self.dates[self.dates.index(last) + 1]


def plan_to_json(plan):
    return {"expected_head_seq": plan.expected_head_seq, "expected_head_hash": plan.expected_head_hash,
            "event": plan.event}


def plan_from_json(obj):
    return AppendPlan(obj["expected_head_seq"], obj["expected_head_hash"], obj["event"])


def init_root(root, scen, advance=0, **kw):
    st = LocalFileStore(root, writable=True, **kw)
    st.initialize(scen.genesis)
    if advance:
        scen.advance(st, advance)
    return st


# --- recording / fault-injecting FileOps ---------------------------------------------------------------------

class Rule(object):
    def __init__(self, op, kind, nth, before, after, wrap):
        self.op, self.kind, self.nth, self.before, self.after, self.wrap = op, kind, nth, before, after, wrap
        self.seen = 0


def _fire(action):
    if isinstance(action, BaseException):
        raise action
    return action()


def injected(errno_=5):
    """An OSError that carries a secret-looking path and message: public errors must not echo either."""
    return OSError(errno_, "injected failure for " + SECRET, SECRET)


class FaultOps(FileOps):
    """The real FileOps, recording every call as (op, kind) and optionally failing / hooking chosen ones."""

    def __init__(self):
        self.trace = []
        self.rules = []
        self.max_write = None
        self.windows = None
        self._fdkind = {}
        self._wkind = {}

    # --- configuration
    def add(self, op, kind=None, nth=1, before=None, after=None, wrap=None):
        self.rules.append(Rule(op, kind, nth, before, after, wrap))
        return self

    def fail(self, op, kind=None, exc=None, nth=1, after=False):
        exc = injected() if exc is None else exc
        return self.add(op, kind, nth, after=exc if after else None, before=None if after else exc)

    # --- plumbing
    @staticmethod
    def kind_of(path):
        name = os.path.basename(path)
        if name == LOCK:
            return "lock"
        if name == SNAP:
            return "snapshot"
        if name.startswith(".snapshot.") and name.endswith(".tmp"):
            return "tmp"
        return "root"

    def _run(self, op, kind, real, *args):
        self.trace.append((op, kind))
        hit = []
        for r in self.rules:
            if r.op == op and r.kind in (None, kind):
                r.seen += 1
                if r.seen == r.nth:
                    hit.append(r)
        for r in hit:
            if r.before is not None:
                _fire(r.before)
        wraps = [r for r in hit if r.wrap is not None]
        result = wraps[0].wrap(real, *args) if wraps else real(*args)
        for r in hit:
            if r.after is not None:
                _fire(r.after)
        return result

    def ops(self, *pairs):
        """The trace filtered to the given 'op' / 'op:kind' names, as 'op' or 'op:kind' strings."""
        want = set(pairs)
        out = []
        for op, kind in self.trace:
            for name in (op + ":" + str(kind), op):
                if name in want:
                    out.append(name)
                    break
        return out

    # --- FileOps
    def is_windows(self):
        return super().is_windows() if self.windows is None else self.windows

    def lstat(self, path):
        return self._run("lstat", self.kind_of(path), super().lstat, path)

    def listdir(self, path):
        return self._run("listdir", "root", super().listdir, path)

    def create_exclusive(self, path):
        kind = self.kind_of(path)

        def real(p):
            fd = super(FaultOps, self).create_exclusive(p)
            self._fdkind[fd] = kind
            return fd
        return self._run("create_exclusive", kind, real, path)

    def fstat(self, fd):
        return self._run("fstat", self._fdkind.get(fd), super().fstat, fd)

    def open_writer(self, fd):
        w = self._run("open_writer", self._fdkind.get(fd), super().open_writer, fd)
        self._wkind[id(w)] = self._fdkind.get(fd)
        return w

    def close_fd(self, fd):
        return self._run("close_fd", self._fdkind.get(fd), super().close_fd, fd)

    def write(self, writer, data):
        kind = self._wkind.get(id(writer))
        if self.max_write is not None and kind == "tmp":
            data = data[:self.max_write]
        return self._run("write", kind, super().write, writer, data)

    def flush(self, writer):
        return self._run("flush", self._wkind.get(id(writer)), super().flush, writer)

    def fsync_file(self, writer):
        return self._run("fsync_file", self._wkind.get(id(writer)), super().fsync_file, writer)

    def close(self, writer):
        return self._run("close", self._wkind.get(id(writer)), super().close, writer)

    def replace(self, src, dst):
        return self._run("replace", self.kind_of(dst), super().replace, src, dst)

    def probe_dir_sync(self, path):
        return self._run("probe_dir_sync", "root", super().probe_dir_sync, path)

    def fsync_dir(self, path):
        return self._run("fsync_dir", "root", super().fsync_dir, path)

    def unlink(self, path):
        return self._run("unlink", self.kind_of(path), super().unlink, path)

    def read_file(self, path):
        return self._run("read_file", self.kind_of(path), super().read_file, path)


# --- independent worker processes -------------------------------------------------------------------------------

class Worker(object):
    """One independent Python process (worker.py) driven over stdin/stdout lines. Timeouts are test-side only.

    A reader thread feeds a queue, so the driver also works where select() cannot wait on pipes (Windows).
    """

    def __init__(self, spec, timeout=60):
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


def run_worker(spec, steps=()):
    """Start a worker, send each step line after its expected event, return its RESULT event."""
    w = Worker(spec)
    for expect_event, send in steps:
        w.expect(expect_event)
        if send:
            w.send(send)
    return w.result()
