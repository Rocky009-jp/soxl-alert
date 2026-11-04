"""Helpers for the S4-B (notification) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The S4-A helpers (and through them the existing ones) are only
imported, never changed. Every write goes to a dedicated temporary root made by the test itself. Expected values come
from the S4-A report of the same inputs, from json / hashlib written in the tests, and from what the sender double
received, never from the notification code under test.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_daily_run")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import s4a_helpers as S  # noqa: E402  (existing helper; it also disables sockets)
import v2_notify as N  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402,F401  (re-exported for the tests)
from v2_persistence.local.fsops import FileOps  # noqa: E402

D, P, TZ = S.D, S.P, S.TZ
WORKER = os.path.join(HERE, "s4b_worker.py")
UTC = timezone.utc


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_at(d, hour=18, minute=0):
    y, m, dd = (int(x) for x in d.split("-"))
    return datetime(y, m, dd, hour, minute, tzinfo=TZ)


def jread(root, name):
    with open(os.path.join(root, name), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def bread(root, name):
    with open(os.path.join(root, name), "rb") as f:
        return f.read()


def bwrite(root, name, data):
    with open(os.path.join(root, name), "wb") as f:
        f.write(data)


def names(root):
    return sorted(os.listdir(root))


def snapshot(root):
    """{name: bytes} of the directory (to show that a call changed nothing)."""
    return {n: (None if os.path.isdir(os.path.join(root, n)) else bread(root, n)) for n in names(root)}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class Sender(object):
    """The sender double. answers: a list of answers or exceptions used in order (the last one repeats); a string is
    the answer to every call. Records every text it was given."""

    def __init__(self, answers="SENT"):
        self.answers = answers if isinstance(answers, list) else [answers]
        self.texts = []

    def send(self, text):
        self.texts.append(text)
        answer = self.answers[min(len(self.texts), len(self.answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer


class RaisingSender(object):
    def __init__(self, error):
        self.error, self.texts = error, []

    def send(self, text):
        self.texts.append(text)
        raise self.error


class Ops(FileOps):
    """FileOps that records every call and can fail the n-th call of a method: fail = {name: (n, exception)}."""

    def __init__(self, fail=None):
        self.fail, self.calls, self.count = dict(fail or {}), [], {}

    def _hit(self, name):
        self.calls.append(name)
        self.count[name] = self.count.get(name, 0) + 1
        plan = self.fail.get(name)
        if plan is not None and self.count[name] == plan[0]:
            raise plan[1]

    def create_exclusive(self, path):
        self._hit("create_exclusive")
        return FileOps.create_exclusive(self, path)

    def open_writer(self, fd):
        self._hit("open_writer")
        return FileOps.open_writer(self, fd)

    def write(self, writer, data):
        self._hit("write")
        return FileOps.write(self, writer, data)

    def flush(self, writer):
        self._hit("flush")
        return FileOps.flush(self, writer)

    def fsync_file(self, writer):
        self._hit("fsync_file")
        return FileOps.fsync_file(self, writer)

    def close(self, writer):
        self._hit("close")
        return FileOps.close(self, writer)

    def close_fd(self, fd):
        self._hit("close_fd")
        return FileOps.close_fd(self, fd)

    def fsync_dir(self, path):
        self._hit("fsync_dir")
        return FileOps.fsync_dir(self, path)

    def read_file(self, path):
        self._hit("read_file")
        return FileOps.read_file(self, path)

    def listdir(self, path):
        self._hit("listdir")
        return FileOps.listdir(self, path)

    def lstat(self, path):
        self._hit("lstat")
        return FileOps.lstat(self, path)

    def replace(self, src, dst):
        self._hit("replace")
        raise AssertionError("the outbox must never replace")

    def unlink(self, path):
        self._hit("unlink")
        raise AssertionError("the outbox must never unlink")


class Case(unittest.TestCase):
    """A fresh history root, outbox directory and world per test (removed by the harness)."""

    def setUp(self):
        self.hroot = tempfile.mkdtemp(prefix="v2s4b_hist_")
        self.oroot = tempfile.mkdtemp(prefix="v2s4b_out_")
        self.addCleanup(shutil.rmtree, self.hroot, True)
        self.addCleanup(shutil.rmtree, self.oroot, True)
        self.w = P.World(0)
        self.sender = Sender()
        self._store = None

    def store(self):
        if self._store is None:
            self._store = S.real_store(self.hroot, self.w)
        return self._store

    def outbox(self, ops=None):
        return N.LocalOutbox(self.oroot, _ops=ops)

    def job(self, now, sender=None, outbox=None, store=None, **kw):
        w = self.w
        return N.morning_job(store or self.store(), outbox or self.outbox(), sender or self.sender, now,
                             kw.get("series", w.series), kw.get("sessions", w.sessions), kw.get("ledger", w.ledger))

    def reference(self, now, **kw):
        """The S4-A report of the same inputs on a separate history root (the expected text comes from it)."""
        root = tempfile.mkdtemp(prefix="v2s4b_ref_")
        self.addCleanup(shutil.rmtree, root, True)
        w = self.w
        store = S.real_store(root, w)
        return S.run(store, w, now, **kw)

    def last_text(self):
        return self.sender.texts[-1]


class Child(object):
    """One independent Python process (s4b_worker.py): READY, wait for the GO file, run once, print one JSON line."""

    def __init__(self, spec, timeout=240):
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


def read_source(relative):
    return S.read_source(relative)


class RaisingSeries(object):
    """A market series whose first use fails with `error` (a program error inside the morning run)."""

    def __init__(self, error):
        self.error = error

    def through(self, d):
        raise self.error


class OddSeries(P.StubSeries):
    """The stub series with a given SOXL close (and optionally another price definition for it)."""

    def __init__(self, rows, close, definition=None):
        super().__init__(rows)
        self.close, self.definition = close, definition
        if definition:
            self.meta["soxl_close_definition"] = definition

    def through(self, d):
        return OddSeries([r for r in self.rows.values() if r.date <= d], self.close, self.definition)

    def soxl_close(self, d):
        return self.close


def utc_date(now):
    return now.astimezone(UTC).date().isoformat()


def append_line(path, obj):
    """One JSON line appended to a file (the sender double of a child process logs what it was asked to send)."""
    with open(path, "ab") as f:
        f.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        return [json.loads(line.decode("utf-8")) for line in f.read().splitlines()]


def signal(path):
    S.signal(path)


def kind_of(text):
    """The kind of notice that a text is (from its heading line)."""
    heading = text.splitlines()[0]
    return "error" if "実行の誤り" in heading else "halt" if heading.endswith("／判定なし") else "morning"
