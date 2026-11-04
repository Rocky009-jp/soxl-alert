"""Helpers for the C-4 (HistoryMaintenance) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The existing helpers (c2_helpers, c3_helpers, l_helpers) are only
imported, never changed. Every write goes to a dedicated temporary root made by the test itself. Expected values come
from the C-2 builders' own cases, from `file_bytes` and `raw_of` (the independent byte writers of c2_helpers) and from
hashlib / os.lstat in the tests, never from the package under test. Nothing here is part of the product code.
"""
import hashlib
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
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_publish"), os.path.join(ROOT, "tests", "v2_persistence_local"),
           os.path.join(ROOT, "tests", "v2_history_local")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import c2_helpers as C2  # noqa: E402  (existing helper; it also disables sockets)
import c3_helpers as C3  # noqa: E402  (existing helper: C-3 root helpers, the C-3 store for cross checks)
import l_helpers as L  # noqa: E402  (existing helper: FaultOps, injected, SECRET)
import v2_history_publish as U  # noqa: E402
from v2_history_maintain import HistoryMaintenance, plan_unlock  # noqa: E402
from v2_history_maintain.ops import MaintenanceOps  # noqa: E402
from v2_persistence.local.fsops import FileOps  # noqa: E402

WORKER = os.path.join(HERE, "c4_worker.py")
SECRET = L.SECRET
HIST, LOCK, V1, QUAR, MANIFEST = "history.json", "write.lock", "snapshot.json", "quarantine", "MANIFEST"
injected = L.injected
put, raw, listing = C3.put, C3.raw, C3.listing
WHEN = C2.WHEN
WHEN2 = WHEN + timedelta(minutes=7)               # another requested_at (it changes plan_hash and publication_hash)
LOCK_C4 = b"v2_history_maintain.lock\n" + b"0" * 32 + b"\n"
LOCK_C3 = b"v2_history_local.lock\n" + b"1" * 32 + b"\n"
LOCK_S2 = b"v2_persistence.local.lock\n" + b"2" * 32 + b"\n"
TMP_H = ".history." + "a" * 32 + ".tmp"
TMP_H2 = ".history." + "b" * 32 + ".tmp"
TMP_S = ".snapshot." + "c" * 32 + ".tmp"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_root():
    return tempfile.mkdtemp(prefix="v2c4_root_")


def tree(root):
    """Everything observable under a root, the quarantine included: names, kinds, bytes, mtimes and inodes (to prove
    'unchanged')."""
    out = {}
    for base, dirs, files in os.walk(root):
        for n in sorted(dirs + files):
            p = os.path.join(base, n)
            st = os.lstat(p)
            rel = os.path.relpath(p, root)
            data = None
            if os.path.isfile(p) and not os.path.islink(p):
                with open(p, "rb") as f:
                    data = f.read()
            out[rel] = (os.path.isdir(p) and not os.path.islink(p), data, st.st_mtime_ns, st.st_ino)
    return out


def key_dir(root, key):
    return os.path.join(root, QUAR, key)


def qraw(root, key, name):
    return raw(root, os.path.join(QUAR, key, name))


def qnames(root, key):
    return sorted(os.listdir(os.path.join(root, QUAR, key)))


def keys(root):
    p = os.path.join(root, QUAR)
    return sorted(os.listdir(p)) if os.path.isdir(p) else []


def manifest_expected(operation, key, request_id, plan_hash, publication_hash, writers_stopped, targets):
    """The MANIFEST text of design 4.4, written here (sorted keys, no spaces, ASCII), never by the package."""
    obj = {"format": "soxl-v2-quarantine/1", "operation": operation, "key": key, "request_id": request_id,
           "plan_hash": plan_hash, "publication_hash": publication_hash, "writers_stopped": writers_stopped,
           "targets": [{"name": n, "kind": k, "raw_sha256": s, "raw_size": z} for (n, k, s, z) in targets]}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


# --- recording / fault-injecting ops ----------------------------------------------------------------------------------

def _is_hex64(s):
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


class C4Ops(L.FaultOps, MaintenanceOps):
    """The FileOps of S2's tests with the names of the maintenance root and the two added calls (mkdir, rename). The
    recording wrappers of FaultOps call the real FileOps method; the three that need a finer kind are redone here."""

    @staticmethod
    def kind_of(path):
        name = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        if name == QUAR:
            return "qdir"
        if parent == QUAR:
            return "kdir"
        if _is_hex64(parent) and os.path.basename(os.path.dirname(os.path.dirname(path))) == QUAR:
            if name == MANIFEST:
                return "manifest"
            if name.startswith(".q.") and name.endswith(".tmp"):
                return "qtmp"
            return "qfile"
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

    @staticmethod
    def _dirkind(path):
        name = os.path.basename(path)
        if name == QUAR:
            return "qdir"
        if _is_hex64(name):
            return "kdir"
        return "root"

    def listdir(self, path):
        return self._run("listdir", self._dirkind(path), lambda p: FileOps.listdir(self, p), path)

    def probe_dir_sync(self, path):
        return self._run("probe_dir_sync", "root", lambda p: FileOps.probe_dir_sync(self, p), path)

    def fsync_dir(self, path):
        return self._run("fsync_dir", self._dirkind(path), lambda p: FileOps.fsync_dir(self, p), path)

    def mkdir(self, path):
        return self._run("mkdir", self._dirkind(path), lambda p: MaintenanceOps.mkdir(self, p), path)

    def rename(self, src, dst):
        return self._run("rename", self.kind_of(src), lambda a, b: MaintenanceOps.rename(self, a, b), src, dst)

    def write(self, writer, data):
        kind = self._wkind.get(id(writer))
        if self.max_write is not None and kind in ("tmp", "qtmp"):
            data = data[:self.max_write]
        return self._run("write", kind, lambda w, d: FileOps.write(self, w, d), writer, data)


def plain_ops():
    return MaintenanceOps()


# --- cases -----------------------------------------------------------------------------------------------------------

class Case(object):
    def __init__(self, pub, candidate, data, **more):
        self.pub, self.candidate, self.data = pub, candidate, data
        self.key = pub.publication_hash
        self.__dict__.update(more)

    @property
    def request_id(self):
        return self.pub.body["request_id"]

    @property
    def plan_hash(self):
        return self.pub.body["plan_hash"]

    @property
    def candidate_bytes(self):
        return C2.file_bytes(self.candidate)


def migration(when=WHEN, rid="mig-1"):
    """The v1 -> v2 case, made again from the same inputs each time (so a different `when` gives another plan)."""
    w, snap, rs, ledger, check_d = C2.HH.example_m_world()
    plan = C2.V.prepare_migration_plan(snap, rs, w.sessions, ledger, check_d, rid, when)
    conf = C2.V.confirm_migration_plan(plan, plan.plan_hash, snap, rs, w.sessions, ledger)
    data = C2.encode_snapshot(snap).encode("utf-8")
    pub = U.publish_migration(plan, plan.plan_hash, data, rs, w.sessions, ledger)
    return Case(pub, conf.history, data, plan=plan, inputs=(snap, rs, w.sessions, ledger, check_d), when=when,
                rid=rid)


def rebuild_migration(case, snapshot_bytes, when=None, rid=None):
    """What a person does after the process ended: the same inputs, the v1 bytes read back, publish_migration again."""
    snap, rs, sessions, ledger, check_d = case.inputs
    plan = C2.V.prepare_migration_plan(snap, rs, sessions, ledger, check_d, rid or case.rid, when or case.when)
    return U.publish_migration(plan, plan.plan_hash, snapshot_bytes, rs, sessions, ledger)


def adoption(when=WHEN, rid="ad1"):
    b, data, k = C2.A5.new_world()
    plan = C2.A5.prep(data, k, rid=rid, when=when)
    conf = C2.AD.confirm_prefix_adoption(plan, plan.plan_hash, data)
    pub = U.publish_adoption(plan, plan.plan_hash, data)
    return Case(pub, conf.history, data, plan=plan, k=k, when=when, rid=rid)


def rebuild_adoption(case, original_bytes, when=None, rid=None):
    plan = C2.A5.prep(original_bytes, case.k, rid=rid or case.rid, when=when or case.when)
    return U.publish_adoption(plan, plan.plan_hash, original_bytes)


# --- cases of the root ------------------------------------------------------------------------------------------------

class RootCase(unittest.TestCase):
    """A fresh dedicated root per test, removed by the test harness (explicit test clean-up, not a product feature)."""

    def setUp(self):
        self.root = make_root()
        self.addCleanup(shutil.rmtree, self.root, True)

    def maint(self, ops=None, **kw):
        kw.setdefault("writable", True)
        if ops is not None:
            kw["_ops"] = ops
        return HistoryMaintenance(self.root, **kw)

    def c3(self, ops=None, **kw):
        kw.setdefault("writable", True)
        if ops is not None:
            kw["_ops"] = ops
        return C3.HistoryFileStore(self.root, **kw)

    def put_v1(self, case):
        put(self.root, V1, case.data)

    def put_history(self, data):
        put(self.root, HIST, data)

    def assertErr(self, exc, code, field=None, phase=None, rule=None, cleanup=None, primary=None):
        self.assertEqual(exc.code, code)
        if field is not None:
            self.assertEqual(exc.field, field)
        if phase is not None:
            self.assertEqual(exc.phase, phase)
        if rule is not None:
            self.assertEqual(exc.rule, rule)
        if cleanup is not None:
            self.assertEqual(tuple(exc.cleanup), tuple(cleanup))
        if primary is not None:
            self.assertEqual(exc.primary, primary)

    def run_err(self, fn, *args):
        """The error that fn(*args) raises (the test fails when nothing is raised)."""
        try:
            fn(*args)
        except Exception as e:  # CoreError family
            return e
        self.fail("expected an error")

    def unlock_all(self, m=None, request_id="u-1"):
        """The person's step of design 5.4: look at the root, confirm a plan for what is left, unlock. Returns the
        plan (None when nothing was left)."""
        m = m or self.maint()
        report = m.inspect()
        if not report.artifacts:
            return None
        plan = plan_unlock(report, request_id, True)
        m.unlock(plan, plan.plan_hash)
        return plan


def lock_and_tmps(root, lock=LOCK_C3, tmps=((TMP_H, b"c3-partial"), (TMP_S, b"s2-partial"))):
    """A root in the state an interrupted writer leaves: the lock and temporary files (written by the test)."""
    if lock is not None:
        put(root, LOCK, lock)
    for name, data in tmps:
        put(root, name, data)


# --- independent worker processes -------------------------------------------------------------------------------------

class Worker(object):
    """One independent Python process (c4_worker.py) driven over stdin/stdout lines. Timeouts are test-side only; a
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
