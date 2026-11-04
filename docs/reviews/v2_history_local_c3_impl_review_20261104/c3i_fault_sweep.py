"""C-3 implementation review: exhaustive single-fault sweep over every FileOps call of each operation.

For each operation (publish / initialize / read / reconcile) x durability, record the fault-free call trace, then for
every call index k, both before and after the real call, and for each exception type, raise at that call only. Check:
- only CoreError-family errors leave, with no secret / root path in str, repr, attributes, cleanup, cause or context;
- history.json is the old or the new bytes; new only on success or store_commit_uncertain;
- a leftover write.lock implies a lock token in cleanup; a leftover tmp implies a tmp token in cleanup;
- after the leftovers are removed by hand, reconcile says PUBLISHED iff the file is new, NOT_PUBLISHED iff old.
Run from the repository root: python -B probes/c3i_fault_sweep.py <repo>
"""
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


def excs():
    return [("OSError", lambda: H.injected()), ("FileExistsError", lambda: FileExistsError(17, "x " + SECRET, SECRET)),
            ("FileNotFoundError", lambda: FileNotFoundError(2, "x " + SECRET, SECRET)),
            ("PermissionError", lambda: PermissionError(13, "x " + SECRET, SECRET)),
            ("ValueError", lambda: ValueError("bad " + SECRET)), ("RuntimeError", lambda: RuntimeError(SECRET))]


class KOps(FileOps):
    def __init__(self, k=None, when=None, exc=None):
        self.k, self.when, self.exc, self.n, self.trace = k, when, exc, 0, []

    def __getattribute__(self, name):
        if name in METHODS:
            real = getattr(FileOps, name).__get__(self)

            def call(*a):
                i = self.n
                self.n += 1
                self.trace.append(name)
                if i == self.k and self.when == "before":
                    raise self.exc()
                r = real(*a)
                if i == self.k and self.when == "after":
                    raise self.exc()
                return r
            return call
        return object.__getattribute__(self, name)


def leaks(e, root):
    texts = [str(e), repr(e)] + [repr(getattr(e, a, None)) for a in ("code", "field", "phase", "rule", "cleanup", "primary", "detail")]
    bad = [t for t in texts if SECRET in t or root in t]
    c = e.__cause__ or (None if e.__suppress_context__ else e.__context__)
    seen = 0
    while c is not None and seen < 10:
        if SECRET in repr(c) or SECRET in str(c):
            bad.append("chain:" + type(c).__name__)
        c = c.__cause__ or (None if c.__suppress_context__ else c.__context__)
        seen += 1
    return bad


def setup(op):
    root = H.make_root()
    h, pub, w = H.day1()
    if op == "initialize":
        g = H.C2.genesis_case()
        old, new, p = None, H.C2.file_bytes(g.candidate), g.pub
    else:
        H.put(root, H.HIST, H.C2.file_bytes(h))
        old = H.raw(root)
        new = H.C2.file_bytes(H.U.check_publication(old, pub))
        p = pub
    return root, old, new, p


def call(store, op, p):
    return getattr(store, op)() if op == "read" else getattr(store, op)(p)


stats = collections.Counter()
problems = []
for op in ("publish", "initialize", "read", "reconcile"):
    for dur in (STRICT, FILE_SYNC_ONLY_MODE):
        root, old, new, p = setup(op)
        ops = KOps()
        call(HistoryFileStore(root, writable=True, durability=dur, _ops=ops), op, p)
        n = len(ops.trace)
        trace = list(ops.trace)
        shutil.rmtree(root)
        for k in range(n):
            for when in ("before", "after"):
                for ename, mk in excs():
                    root, old, new, p = setup(op)
                    try:
                        store = HistoryFileStore(root, writable=True, durability=dur, _ops=KOps(k, when, mk))
                    except Exception as e:
                        problems.append((op, dur, k, trace[k], when, ename, "construct", repr(e)))
                        shutil.rmtree(root); continue
                    err = None
                    try:
                        call(store, op, p)
                    except CoreError as e:
                        err = e
                    except BaseException as e:
                        problems.append((op, dur, k, trace[k], when, ename, "raw exception", type(e).__name__))
                        shutil.rmtree(root); continue
                    stats[(op, err.code if err else "OK")] += 1
                    tag = (op, dur, k, trace[k], when, ename)
                    if err is not None:
                        b = leaks(err, root)
                        if b:
                            problems.append(tag + ("leak", b))
                    names = H.listing(root)
                    cleanup = set(getattr(err, "cleanup", ()) or ())
                    cur = H.raw(root) if H.HIST in names else None
                    if op in ("read", "reconcile"):
                        if cur != old:
                            problems.append(tag + ("read-only op changed the file",))
                    else:
                        if cur not in (old, new):
                            problems.append(tag + ("file neither old nor new", cur and cur[:40]))
                        if cur == new and old != new and err is not None and err.code != "store_commit_uncertain":
                            problems.append(tag + ("new bytes but code", err.code))
                        if err is None and cur != new:
                            problems.append(tag + ("success but not new",))
                    if H.LOCK in names and not (cleanup & LOCK_TOKENS):
                        problems.append(tag + ("lock left without token", getattr(err, "code", None), sorted(cleanup)))
                    tmps = [x for x in names if x.startswith(".history.") and x.endswith(".tmp")]
                    if tmps and not (cleanup & TMP_TOKENS):
                        problems.append(tag + ("tmp left without token", getattr(err, "code", None), sorted(cleanup)))
                    extra = set(names) - {H.HIST, H.LOCK} - set(tmps)
                    if extra:
                        problems.append(tag + ("unexpected names", sorted(extra)))
                    if err is None and set(names) - {H.HIST}:
                        problems.append(tag + ("success with leftovers", names))
                    if op in ("publish", "initialize"):
                        for x in tmps + ([H.LOCK] if H.LOCK in names else []):
                            os.unlink(os.path.join(root, x))
                        rec = HistoryFileStore(root).reconcile(p).outcome
                        want = "PUBLISHED" if cur == new else "NOT_PUBLISHED"
                        if rec != want:
                            problems.append(tag + ("reconcile", rec, want))
                    shutil.rmtree(root)
total = sum(stats.values()) + len([x for x in problems if x[6] in ("raw exception", "construct")])
print("cases:", sum(stats.values()))
for (op, code), c in sorted(stats.items()):
    print("  %-10s %-32s %d" % (op, code, c))
print("problems:", len(problems))
seen = set()
for pr in problems:
    key = (pr[0], pr[3], pr[4], pr[5], pr[6])
    if key in seen:
        continue
    seen.add(key)
    print("  ", pr)
