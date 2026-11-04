"""C-3 implementation review: every pair of faults (k1 < k2, OSError, before/after) in publish and initialize, same
invariants as c3i_fault_sweep.py. Construction is done with clean FileOps, then the faulting FileOps is swapped in
(store._ops) so that indices count the operation's own calls only."""
import os, shutil, sys, collections
REPO = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(REPO, "tests", "v2_history_local"))
os.chdir(REPO)
import c3_helpers as H  # noqa
from v2_core.errors import CoreError  # noqa
from v2_history_local import HistoryFileStore, STRICT, FILE_SYNC_ONLY_MODE  # noqa
from v2_persistence.local.fsops import FileOps  # noqa
SECRET = H.SECRET
LOCK_TOKENS = {"lock_left", "lock_not_ours_left_untouched"}
TMP_TOKENS = {"tmp_left", "tmp_ownership_unconfirmed"}
METHODS = ["lstat", "fstat", "listdir", "create_exclusive", "open_writer", "close_fd", "write", "flush", "fsync_file",
           "close", "replace", "probe_dir_sync", "fsync_dir", "unlink", "read_file"]


class KOps(FileOps):
    def __init__(self, faults=()):
        self.faults, self.n, self.trace = dict(faults), 0, []

    def __getattribute__(self, name):
        if name in METHODS:
            real = getattr(FileOps, name).__get__(self)

            def call(*a):
                i = self.n
                self.n += 1
                self.trace.append(name)
                f = self.faults.get(i)
                if f == "before":
                    raise H.injected()
                r = real(*a)
                if f == "after" and name != "create_exclusive":     # (a create that succeeds and then fails: see sweep)
                    raise H.injected()
                return r
            return call
        return object.__getattribute__(self, name)


def setup(op):
    root = H.make_root()
    h, pub, w = H.day1()
    if op == "initialize":
        g = H.C2.genesis_case()
        return root, None, H.C2.file_bytes(g.candidate), g.pub
    H.put(root, H.HIST, H.C2.file_bytes(h))
    old = H.raw(root)
    return root, old, H.C2.file_bytes(H.U.check_publication(old, pub)), pub


stats, problems = collections.Counter(), []
for op in ("publish", "initialize"):
    for dur in (STRICT, FILE_SYNC_ONLY_MODE):
        root, old, new, p = setup(op)
        st = HistoryFileStore(root, writable=True, durability=dur)
        st._ops = KOps()
        getattr(st, op)(p)
        n = len(st._ops.trace); trace = list(st._ops.trace)
        shutil.rmtree(root)
        for k1 in range(n):
            for k2 in range(k1 + 1, n):
                for w1 in ("before", "after"):
                    for w2 in ("before", "after"):
                        root, old, new, p = setup(op)
                        st = HistoryFileStore(root, writable=True, durability=dur)
                        st._ops = KOps({k1: w1, k2: w2})
                        err = None
                        try:
                            getattr(st, op)(p)
                        except CoreError as e:
                            err = e
                        except BaseException as e:
                            problems.append((op, dur, trace[k1], w1, trace[k2], w2, "raw", type(e).__name__)); shutil.rmtree(root); continue
                        tag = (op, dur, k1, trace[k1], w1, k2, trace[k2], w2)
                        stats[err.code if err else "OK"] += 1
                        if err is not None and (SECRET in repr(err) or SECRET in str(err) or root in repr(err)):
                            problems.append(tag + ("leak",))
                        names = H.listing(root)
                        cleanup = set(getattr(err, "cleanup", ()) or ())
                        cur = H.raw(root) if H.HIST in names else None
                        if cur not in (old, new):
                            problems.append(tag + ("neither",))
                        if cur == new and err is not None and err.code != "store_commit_uncertain":
                            problems.append(tag + ("new but", err.code))
                        if err is None and cur != new:
                            problems.append(tag + ("ok but old",))
                        if H.LOCK in names and not cleanup & LOCK_TOKENS:
                            problems.append(tag + ("lock no token", getattr(err, "code", None)))
                        tmps = [x for x in names if x.startswith(".history.")]
                        if tmps and not cleanup & TMP_TOKENS:
                            problems.append(tag + ("tmp no token", getattr(err, "code", None)))
                        for x in tmps + ([H.LOCK] if H.LOCK in names else []):
                            os.unlink(os.path.join(root, x))
                        rec = HistoryFileStore(root).reconcile(p).outcome
                        if rec != ("PUBLISHED" if cur == new else "NOT_PUBLISHED"):
                            problems.append(tag + ("reconcile", rec))
                        shutil.rmtree(root)
print("cases:", sum(stats.values()), dict(stats))
print("problems:", len(problems))
for pr in problems[:40]:
    print("  ", pr)
