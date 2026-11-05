"""Helpers for the S4-C (git store) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The S4-B and S4-A helpers (and through them the existing ones) are
only imported, never changed. The only remotes are bare repositories in a temporary directory whose path carries the
mark SECRETMARK_; the clones, the mirror parents and the world are made by the test itself and removed by the harness.
Expected values come from `git` called here directly (cat-file, ls-tree, log, for-each-ref, status), from the C-3 store
and the S4-B LocalOutbox run over the same inputs, and from what the sender double received, never from the code under
test. Every git call of the tests gets its settings with -c and runs without the GIT_ variables of the parent.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_notify")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import s4b_helpers as B  # noqa: E402  (existing helper; it also disables sockets)
import v2_git_store as GS  # noqa: E402
from v2_git_store import git as G  # noqa: E402

S, P, N, D, TZ, CoreError = B.S, B.P, B.N, B.D, B.TZ, B.CoreError
WORKER = os.path.join(HERE, "s4c_worker.py")
MARK = "SECRETMARK_"
STATE, OUTBOX = "v2-state", "v2-outbox"
WHEN = datetime(2026, 11, 5, 12, 34, 56, tzinfo=timezone(timedelta(hours=9)))
SHA0 = "0" * 40
UTC = timezone.utc


def clock():
    return WHEN


class Tick(object):
    """A clock that goes forward one second at each call (so that two commits made at different calls differ)."""

    def __init__(self, start=WHEN):
        self.t = start - timedelta(seconds=1)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


PATH_AT_START = os.environ.get("PATH", "")      # for the tests that compare the PATH that git gets


def _env():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0", LC_ALL="C",
               GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@invalid", GIT_COMMITTER_NAME="test",
               GIT_COMMITTER_EMAIL="test@invalid")
    return env


def tgit(cwd, *args, data=None, check=True):
    """A git call made by a test (its own settings; the work is in `cwd`). Returns the CompletedProcess (bytes)."""
    command = ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main"]
    kw = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
    proc = subprocess.run(command + list(args), cwd=cwd, capture_output=True, env=_env(), timeout=120, **kw)
    if check and proc.returncode != 0:
        raise AssertionError((args[0], proc.returncode))
    return proc


def text(proc):
    return proc.stdout.decode("utf-8").strip()


def with_env(**values):
    """The environment of this process with the given variables (for the one test that sets a GIT_ variable)."""
    return mock.patch.dict(os.environ, values)


# --- the remote ---------------------------------------------------------------------------------------------------------
class Remote(object):
    """A bare repository in a temporary directory (the path has the mark). Reads it with git, directly."""

    def __init__(self, case):
        self.path = tempfile.mkdtemp(prefix=MARK)
        case.addCleanup(shutil.rmtree, self.path, True)
        tgit(self.path, "init", "-q", "--bare")

    def sha(self, ref):
        proc = tgit(self.path, "rev-parse", "--verify", "-q", "refs/heads/" + ref, check=False)
        return text(proc) if proc.returncode == 0 else None

    def refs(self):
        out = text(tgit(self.path, "for-each-ref", "--format=%(refname) %(objectname)", "refs/"))
        return dict(line.split(" ") for line in out.splitlines())

    def names(self, ref):
        out = tgit(self.path, "ls-tree", "-z", "--name-only", "refs/heads/" + ref).stdout
        return sorted(n.decode("utf-8") for n in out.split(b"\0") if n)

    def blob(self, ref, name):
        proc = tgit(self.path, "cat-file", "blob", "refs/heads/%s:%s" % (ref, name), check=False)
        return proc.stdout if proc.returncode == 0 else None

    def files(self, ref):
        return {n: self.blob(ref, n) for n in self.names(ref)}

    def log(self, ref):
        """The commits of a ref, oldest first: dicts of sha, parents, author, committer, dates, message and file names."""
        fmt = "%H%x00%P%x00%an%x00%ae%x00%cn%x00%ce%x00%at%x00%ct%x00%ad%x00%s"
        out = text(tgit(self.path, "log", "--reverse", "--date=raw", "--format=" + fmt, "refs/heads/" + ref))
        rows = []
        for line in out.splitlines():
            sha, parents, an, ae, cn, ce, at, ct, ad, subject = line.split("\0")
            names = sorted(n.decode("utf-8") for n in
                           tgit(self.path, "ls-tree", "-z", "--name-only", sha).stdout.split(b"\0") if n)
            rows.append({"sha": sha, "parents": parents.split(), "author": (an, ae), "committer": (cn, ce), "at": int(at),
                         "ct": int(ct), "ad": ad, "subject": subject, "names": names})
        return rows

    def hook(self, name, script):
        path = os.path.join(self.path, "hooks", name)
        with open(path, "wb") as f:
            f.write(("#!/bin/sh\n" + script + "\n").encode("utf-8"))
        os.chmod(path, 0o755)

    def plant(self, ref, files, parent="HEAD~", message="planted"):
        """Write a commit with exactly `files` (name -> bytes) onto the ref by plumbing, as a person with write access would.
        parent: the SHA to build on (None for a first commit, "HEAD~" for the current head of the ref)."""
        entries = []
        for name, data in sorted(files.items()):
            blob = text(tgit(self.path, "hash-object", "-w", "--stdin", data=data))
            entries.append("100644 blob %s\t%s\n" % (blob, name))
        tree = text(tgit(self.path, "mktree", data="".join(entries).encode("utf-8")))
        if parent == "HEAD~":
            parent = self.sha(ref)
        args = ["commit-tree", tree, "-m", message] + ([] if parent is None else ["-p", parent])
        commit = text(tgit(self.path, *args))
        tgit(self.path, "update-ref", "refs/heads/" + ref, commit)
        return commit


class Clone(object):
    """A work directory with the remote configured, a mirror parent, and the stores over them."""

    def __init__(self, case, remote, clk=clock, timeout=120, git_cls=GS.Git, **git_kw):
        self.remote = remote
        self.dir = tempfile.mkdtemp(prefix="v2s4c_clone_")
        self.parent = tempfile.mkdtemp(prefix="v2s4c_mirror_")
        case.addCleanup(shutil.rmtree, self.dir, True)
        case.addCleanup(shutil.rmtree, self.parent, True)
        tgit(self.dir, "init", "-q")
        tgit(self.dir, "remote", "add", "origin", remote.path)
        self.git = git_cls(self.dir, timeout=timeout, **git_kw)
        self.hist = GS.GitHistoryStore(self.git, STATE, clk)
        self.outbox = GS.GitOutbox(self.git, OUTBOX, self.parent, clk)

    def state(self):
        """The things a fetch must not change in the work directory."""
        return {"head": text(tgit(self.dir, "symbolic-ref", "HEAD")),
                "heads": text(tgit(self.dir, "for-each-ref", "refs/heads/")),
                "status": text(tgit(self.dir, "status", "--porcelain")),
                "index": os.path.exists(os.path.join(self.dir, ".git", "index")),
                "tree": sorted(n for n in os.listdir(self.dir) if n != ".git")}


def world(decisions=range(1, 5), **kw):
    w = P.World(0, **kw)
    S.decide(w, decisions)
    return w


def now_at(i, hour=18):
    return B.now_at(D[i], hour)


def start(case, w, clk=clock):
    """A remote with an initialized history and outbox, and the first clone."""
    remote = Remote(case)
    clone = Clone(case, remote, clk)
    clone.hist.initialize(S.genesis_pub(w))
    clone.outbox.initialize()
    return remote, clone


def job(clone, w, i, sender, hour=18, **kw):
    return N.morning_job(kw.get("hist", clone.hist), kw.get("outbox", clone.outbox), sender, now_at(i, hour),
                         w.series, w.sessions, w.ledger)


def run(clone, w, i, hour=18, store=None):
    return S.run(store or clone.hist, w, now_at(i, hour))


# --- test doubles for git ---------------------------------------------------------------------------------------------------
class Spy(GS.Git):
    """The real Git that records every command it is asked to run (the argument lists), and the standard output of pushes."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls, self.push_out = [], []

    def run(self, args, data=None, env=None):
        self.calls.append(list(args))
        proc = super().run(args, data, env)
        if args and args[0] == "push" and proc is not None:
            self.push_out.append(proc.stdout.decode("utf-8", "replace"))
        return proc

    def names(self):
        return [c[0] for c in self.calls]


class Scripted(Spy):
    """Git whose commands can be faked: `rule(args)` returns None (run the real command) or a CompletedProcess / None-timeout
    marker. before/after hooks let a test change the remote at a chosen point."""

    TIMEOUT = object()

    def __init__(self, *a, rule=None, **kw):
        super().__init__(*a, **kw)
        self.rule, self.hooks = rule, {}

    def run(self, args, data=None, env=None):
        hook = self.hooks.get(args[0]) if args else None
        if hook is not None:
            hook(self, args)
        fake = self.rule(args) if self.rule else None
        if fake is not None:
            self.calls.append(list(args))
            return None if fake is Scripted.TIMEOUT else fake
        return super().run(args, data, env)


class Lost(Spy):
    """The real Git whose n-th push really happens (or not, with deliver=False) and is then reported as UNCERTAIN (a timeout
    for the caller). `after()` runs between the push and the answer: another writer may act there."""

    def __init__(self, *a, nth=1, deliver=True, after=None, **kw):
        super().__init__(*a, **kw)
        self.nth, self.deliver, self.after, self.pushes = nth, deliver, after, 0

    def run(self, args, data=None, env=None):
        if args and args[0] == "push":
            self.pushes += 1
            if self.pushes == self.nth:
                if self.deliver:
                    Spy.run(self, args, data, env)
                else:
                    self.calls.append(list(args))
                if self.after is not None:
                    self.after()
                return None
        return Spy.run(self, args, data, env)


def proc(returncode=0, out=b"", err=b""):
    return subprocess.CompletedProcess(["git"], returncode, out, err)


def failing(*names):
    """A rule: every command in `names` fails (exit 128, some text that names the mark)."""
    return lambda args: proc(128, b"", ("fatal: " + MARK + " denied").encode()) if args[0] in names else None


class Gone(object):
    """Make the remote unreachable by moving its directory; undo restores it."""

    def __init__(self, remote):
        self.remote, self.moved = remote, remote.path + "_moved"

    def __enter__(self):
        os.rename(self.remote.path, self.moved)
        return self

    def __exit__(self, *exc):
        if os.path.exists(self.moved):
            os.rename(self.moved, self.remote.path)


# --- what may leave the code under test -------------------------------------------------------------------------------------
def flatten(obj, depth=0):
    """Every text that an object shows: strings, reprs, exception arguments, the fields of the immutable values."""
    if depth > 6:
        return []
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, (bytes, bytearray)):
        out.append(bytes(obj).decode("utf-8", "replace"))
    elif isinstance(obj, BaseException):
        out += [type(obj).__name__, str(obj), repr(obj)]
        for a in obj.args:
            out += flatten(a, depth + 1)
        for v in vars(obj).values():
            out += flatten(v, depth + 1)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            out += flatten(v, depth + 1)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out += flatten(k, depth + 1) + flatten(v, depth + 1)
    elif obj is None or isinstance(obj, (bool, int, float)):
        pass
    else:
        out.append(repr(obj))
        names = getattr(obj, "_NAMES", None)
        if names:
            for n in names:
                out += flatten(getattr(obj, n, None), depth + 1)
        elif hasattr(obj, "__dict__"):
            for v in vars(obj).values():
                out += flatten(v, depth + 1)
    return out


class Case(unittest.TestCase):
    """A fresh world and sender double per test. `see(x)` records what the code under test showed; leaks() lists the texts
    that carry the mark."""

    def setUp(self):
        self.sender = B.Sender()
        self.shown = []

    def see(self, *objs):
        for obj in objs:
            self.shown.extend(flatten(obj))
        return objs[0] if len(objs) == 1 else objs

    def leaks(self):
        return [t for t in self.shown if MARK in t]

    def assertNoMark(self):
        self.assertEqual(self.leaks(), [])

    def assertCleanError(self, err):
        """An error of this package: fixed words only, and no exception was chained to it."""
        self.assertIsNone(err.__context__)
        self.assertIsNone(err.__cause__)
        for t in flatten(err):
            self.assertNotIn(MARK, t)


# --- children -------------------------------------------------------------------------------------------------------------------
class Child(B.Child):
    def __init__(self, spec, timeout=300):
        self.timeout = timeout
        self.proc = subprocess.Popen([sys.executable, "-B", "-I", WORKER, json.dumps(spec)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def read_source(relative):
    return S.read_source(relative)
