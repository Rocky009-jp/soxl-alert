"""S4-C implementation review probes (read-only on the code; everything runs in temporary directories with local bare
repositories). usage: python -B s4c_impl_review_probe.py <repo at 13be0d0> <probe> [args]

  scale <n> [<n> ...]  Y1: the time of one GitOutbox.load (and the number of git processes it starts) when the
                       v2-outbox ref already holds n files (about two files per morning: n=500 is about one year).
  oserror              Y2: an OSError of the mirror after the rebuild (os.listdir in _decide) leaves morning_job as a
                       raw OSError instead of CLAIM_FAILED.
  env                  Y3: a GIT_ variable that S4-E might use for credentials (GIT_SSH_COMMAND, GIT_ASKPASS,
                       GIT_CONFIG_COUNT/KEY/VALUE) does not reach git: the runtime strips every GIT_ variable.
  gaps                 Y5: the code where the suite has no test (review mutants V02, V03, V15), checked directly.
"""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(sys.argv[1])
sys.path.insert(0, REPO)

import v2_git_store as GS  # noqa: E402
from v2_git_store import git as GITMOD  # noqa: E402
from v2_git_store import outbox as OBMOD  # noqa: E402

WHEN = datetime.datetime(2026, 3, 6, 7, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
CLEAN = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
CLEAN.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, LC_ALL="C", GIT_AUTHOR_NAME="t",
             GIT_AUTHOR_EMAIL="t@invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@invalid")


def g(cwd, *args, data=None):
    p = subprocess.run(["git", "-c", "core.autocrlf=false"] + list(args), cwd=cwd, env=CLEAN, input=data,
                       capture_output=True, check=True)
    return p.stdout


def world():
    top = tempfile.mkdtemp(prefix="v2s4c_rv_")
    remote = os.path.join(top, "remote.git")
    work = os.path.join(top, "work")
    parent = os.path.join(top, "mirror_parent")
    os.mkdir(parent)
    g(top, "init", "-q", "--bare", remote)
    g(top, "init", "-q", work)
    g(work, "remote", "add", "origin", remote)
    return top, remote, work, parent


class Counting(GS.Git):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.count = 0

    def run(self, args, data=None, env=None):
        self.count += 1
        return super().run(args, data, env)


def fill(remote, work, n):
    """One commit on v2-outbox with the marker and n plain files with valid names (made by the probe, not the package)."""
    tmp = os.path.join(work, ".fill")
    os.mkdir(tmp)
    lines = []
    sha = g(work, "hash-object", "-w", "--stdin", data=b"v2-outbox\n").decode().strip()
    lines.append("100644 blob %s\tv2-outbox-init" % sha)
    for i in range(n):
        name = "2020-01-%05d-morning.%s.json" % (i // 2, "claim" if i % 2 == 0 else "result")
        sha = g(work, "hash-object", "-w", "--stdin", data=b'{"x":%d}' % i).decode().strip()
        lines.append("100644 blob %s\t%s" % (sha, name))
    tree = g(work, "mktree", data=("\n".join(lines) + "\n").encode()).decode().strip()
    commit = g(work, "commit-tree", tree, "-m", "fill").decode().strip()
    g(work, "push", "-q", "origin", "%s:refs/heads/v2-outbox" % commit)
    shutil.rmtree(tmp)


def probe_scale(ns):
    print("Y1 scale: one GitOutbox.load on a v2-outbox ref holding n files (git %s)" % g("/", "--version").decode().strip())
    for n in ns:
        top, remote, work, parent = world()
        try:
            fill(remote, work, n)
            git = Counting(work)
            box = GS.GitOutbox(git, "v2-outbox", parent, lambda: WHEN)
            t0 = time.perf_counter()
            entry, _claim = box.load("2026-03-05", "morning")
            dt = time.perf_counter() - t0
            print("  n=%5d  load: %.2f s, %d git processes, status=%s" % (n, dt, git.count, entry.status))
        finally:
            shutil.rmtree(top, True)


def probe_oserror():
    sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
    import v2_notify as N
    print("Y2 oserror: os.listdir of the mirror fails after the rebuild, inside claim")
    top, remote, work, parent = world()
    try:
        git = GS.Git(work)
        box = GS.GitOutbox(git, "v2-outbox", parent, lambda: WHEN)
        box.initialize()
        real = OBMOD.os.listdir
        state = {"n": 0}

        def listdir(path):
            # the rebuild calls listdir once; the next call (the `before` set of _decide) fails
            state["n"] += 1
            if state["n"] == 2:
                raise PermissionError("probe")
            return real(path)
        notice = N.compose_error_notice("2026-03-05", "x_code", "T", d_is_target=True)
        OBMOD.os.listdir = listdir
        try:
            box.claim(notice, WHEN)
            print("  claim returned (no error)")
        except N.NotifyError as e:
            print("  NotifyError %s (morning_job would read CLAIM_FAILED)" % e.code)
        except OSError as e:
            print("  raw %s leaves claim (morning_job catches only NotifyError -> the job ends with it)" % type(e).__name__)
        finally:
            OBMOD.os.listdir = real
    finally:
        shutil.rmtree(top, True)


def probe_env():
    print("Y3 env: the GIT_ variables of the parent never reach git")
    os.environ["GIT_SSH_COMMAND"] = "ssh -i /probe/key"
    os.environ["GIT_ASKPASS"] = "/probe/askpass"
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["GIT_CONFIG_KEY_0"] = "http.extraHeader"
    os.environ["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: probe"
    env = GITMOD._environment()
    for k in ("GIT_SSH_COMMAND", "GIT_ASKPASS", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
        print("  %-20s reaches git: %s" % (k, k in env))
    top, remote, work, parent = world()
    try:
        g(work, "config", "core.sshCommand", "ssh -i /probe/key")
        out = GS.Git(work).run(["config", "--get", "core.sshCommand"]).stdout.decode().strip()
        print("  core.sshCommand in the work directory's own config reaches git: %s" % (out == "ssh -i /probe/key"))
    finally:
        shutil.rmtree(top, True)


if __name__ == "__main__":
    what = sys.argv[2]
    if what == "scale":
        probe_scale([int(x) for x in sys.argv[3:]] or [0, 100, 500, 2000])
    elif what == "oserror":
        probe_oserror()
    elif what == "env":
        probe_env()
    elif what != "gaps":
        raise SystemExit(__doc__)


def probe_gaps():
    """Y5: what the code does where the S4-C suite has no test (review mutants V02, V03, V15): checked here directly."""
    sys.path.insert(0, os.path.join(REPO, "tests", "v2_git_store"))
    import s4c_helpers as SH
    from v2_persistence.local.errors import LocalStoreError
    print("Y5 gaps: the code against request 3.8 / 3.2 where no test pins it")
    top, remote, work, parent = world()
    try:
        w = SH.world(range(1, 3))
        git = GS.Git(work)
        hist = GS.GitHistoryStore(git, "v2-state", lambda: WHEN)
        hist.initialize(SH.S.genesis_pub(w))
        pub = SH.S.U.publish_day(hist.read(), SH.D[1], w.series, w.sessions, w.ledger)

        class RefusedThenNoFetch(GS.Git):
            n = 0

            def push(self, commit, ref):
                return GS.REJECTED

            def fetch(self, ref):
                self.n += 1
                if self.n >= 2:
                    raise GS.GitError("git_failed", "fetch")
                return super().fetch(ref)
        h2 = GS.GitHistoryStore(RefusedThenNoFetch(work), "v2-state", lambda: WHEN)
        try:
            h2.publish(pub)
        except LocalStoreError as e:
            print("  V02 publish REJECTED then the fetch fails -> %s (request 3.8: store_io_error)" % e.code)

        class Refused(GS.Git):
            def push(self, commit, ref):
                return GS.REJECTED
        top2, remote2, work2, parent2 = world()
        try:
            h3 = GS.GitHistoryStore(Refused(work2), "v2-state", lambda: WHEN)
            try:
                h3.initialize(SH.S.genesis_pub(w))
            except LocalStoreError as e:
                print("  V03 initialize REJECTED and no ref afterwards -> %s (request 3.8: store_io_error)" % e.code)
            link = os.path.join(top2, "link_parent")
            os.symlink(parent2, link)
            try:
                GS.GitOutbox(GS.Git(work2), "v2-outbox", link, lambda: WHEN)
                print("  V15 a parent that is a link is taken (request 3.2: GitError)")
            except GS.GitError as e:
                print("  V15 a parent that is a link -> GitError%s (request 3.2: git_args_invalid)" % (e.args,))
        finally:
            shutil.rmtree(top2, True)
    finally:
        shutil.rmtree(top, True)


if __name__ == "__main__" and sys.argv[2] == "gaps":
    probe_gaps()
