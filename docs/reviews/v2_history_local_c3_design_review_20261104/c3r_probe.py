"""C-3 design review: independent probes against the trial diff (docs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diff)
applied to d6b0332. Run from the root of that trial tree: python -B <this file>. Writes only in tempfile directories."""
import collections, copy, os, shutil, sys, tempfile
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_publish"))
sys.path.insert(0, ROOT)
import c2_helpers as X  # noqa: E402
U = X.U
from v2_core.errors import CoreError  # noqa: E402
from v2_history_local import HistoryFileStore, LocalStoreError  # noqa: E402
from v2_persistence.local import LocalFileStore  # noqa: E402
from v2_persistence.local.fsops import FileOps  # noqa: E402

results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("OK  " if ok else "NG  ") + name + ("  " + detail if detail else ""))


def code(fn, *a):
    try:
        r = fn(*a)
        return ("ok", getattr(r, "status", None) or getattr(r, "outcome", None))
    except CoreError as e:
        return (e.code, getattr(e, "rule", None), getattr(e, "phase", None), tuple(getattr(e, "cleanup", ())))


def root_with(data):
    d = tempfile.mkdtemp(prefix="c3r_")
    if data is not None:
        with open(os.path.join(d, "history.json"), "wb") as f:
            f.write(data)
    return d


def put(p, data):
    with open(p, "wb") as f:
        f.write(data)


def raw(d, n="history.json"):
    p = os.path.join(d, n)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


cases = X.every_case()
by = {c.source: c for c in cases}

# 1. P-01: with a valid current, no hand-made value makes publish return history_invalid; the file never changes.
WEIRD = [None, True, 0, -1, 1, 2**63, 1.5, "", "x", "0" * 64, [], [None], {}, {"a": 1}, "2026-01-01"]
DELETE = object()


def paths(x, prefix=()):
    yield prefix
    if isinstance(x, dict):
        for k in x:
            yield from paths(x[k], prefix + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x[:2]):
            yield from paths(v, prefix + (i,))


def set_at(body, path, value):
    t = body
    for p in path[:-1]:
        t = t[p]
    if value is DELETE:
        del t[path[-1]]
    else:
        t[path[-1]] = value


def search(case, op):
    codes, leaks, changed, n = collections.Counter(), [], 0, 0
    global oks
    oks = []
    d = root_with(case.current)
    st = HistoryFileStore(d, writable=True, durability="file_sync_only")
    before = raw(d)
    body0 = case.pub.body
    for path in paths(body0):
        if not path:
            continue
        for v in WEIRD + [DELETE]:
            body = copy.deepcopy(body0)
            try:
                set_at(body, path, v)
            except (KeyError, IndexError, TypeError):
                continue
            try:
                pub = U.HistoryPublication._make(body)
            except CoreError:
                codes[("_make refused",)] += 1
                continue
            n += 1
            try:
                getattr(st, op)(pub)
                codes[("ok",)] += 1
                oks.append((path, v if v is not DELETE else "DELETE"))
            except CoreError as e:
                codes[(e.code, getattr(e, "rule", None))] += 1
            except Exception as e:  # noqa: BLE001
                leaks.append((path, v if v is not DELETE else "DELETE", type(e).__name__, str(e)[:60]))
            if raw(d) != before or sorted(os.listdir(d)) != sorted(["history.json"] if before is not None else []):
                changed += 1
                shutil.rmtree(d)
                d = root_with(case.current)
                st = HistoryFileStore(d, writable=True, durability="file_sync_only")
    shutil.rmtree(d)
    return n, codes, leaks, changed


total_hi = 0
for src in ("DAILY", "RESOLUTION", "RESTART", "RESTORE"):
    n, codes, leaks, changed = search(by[src], "publish")
    hi = sum(v for k, v in codes.items() if k[0] == "history_invalid")
    total_hi += hi
    print("  oks:", sorted(set(repr((p, v)) for p, v in oks)), "leaks:", leaks)
    rec("P-01 publish %s hand-made: no history_invalid, no leak" % src, hi == 0 and not leaks,
        "n=%d codes=%s leaks=%d changed=%d" % (n, dict(codes), len(leaks), changed))
n, codes, leaks, changed = search(by["GENESIS"], "initialize")
print("  oks:", sorted(set(repr((p, v)) for p, v in oks)), "leaks:", leaks)
rec("P-01 initialize GENESIS hand-made: no history_invalid, no leak",
    not any(k[0] == "history_invalid" for k in codes) and not leaks,
    "n=%d codes=%s leaks=%d changed=%d" % (n, dict(codes), len(leaks), changed))

# 1b. A candidate that fails validate_history vs one that only fails the digest: two codes for "the candidate is wrong".
c = by["DAILY"]
pa = X.rehash(c.pub, lambda b: b["records"][0].__setitem__("hash", X.ZERO))
pb = X.rehash(c.pub, lambda b: b.__setitem__("candidate_digest", X.ZERO))
d = root_with(c.current)
st = HistoryFileStore(d, writable=True, durability="file_sync_only")
ca, cb = code(st.publish, pa), code(st.publish, pb)
rec("P-01 two codes for a wrong candidate (record hash / candidate digest)", True, "%s / %s" % (ca[:2], cb[:2]))
shutil.rmtree(d)

# 2. broken current: publish -> history_invalid, reconcile -> CONFLICT
d = root_with(c.current[:-1])
st = HistoryFileStore(d, writable=True, durability="file_sync_only")
rec("broken current: publish history_invalid", code(st.publish, c.pub)[0] == "history_invalid", str(code(st.publish, c.pub)[:2]))
rec("broken current: reconcile CONFLICT", code(st.reconcile, c.pub) == ("ok", "CONFLICT"))
shutil.rmtree(d)

# 3. reconcile when history.json is a symbolic link -> a store error, not CONFLICT
d = root_with(None)
other = tempfile.mkdtemp(prefix="c3r_o_")
with open(os.path.join(other, "h"), "wb") as f:
    f.write(c.current)
os.symlink(os.path.join(other, "h"), os.path.join(d, "history.json"))
st = HistoryFileStore(d, writable=False)
r = code(st.reconcile, c.pub)
rec("reconcile on a linked history.json raises (not an outcome)", r[0] == "store_root_invalid", str(r[:3]))
shutil.rmtree(d); shutil.rmtree(other)


# 4. replace fails and the temporary file cannot be removed: reconcile NOT_PUBLISHED, publish again stops
class F(FileOps):
    def __init__(self, fail=()):
        self.fail = set(fail)

    def replace(self, a, b):
        if "replace" in self.fail:
            raise OSError("boom /secret/path")
        return super().replace(a, b)

    def unlink(self, p):
        if "unlink_tmp" in self.fail and p.endswith(".tmp"):
            raise OSError("no")
        return super().unlink(p)

    def read_file(self, p):
        if "lock_lost_after_replace_attempt" in self.fail and p.endswith("write.lock") and self.after:
            raise OSError("gone")
        return super().read_file(p)
    after = False


d = root_with(c.current)
st = HistoryFileStore(d, writable=True, durability="file_sync_only", _ops=F({"replace", "unlink_tmp"}))
r = code(st.publish, c.pub)
rec("replace fails, tmp not removable: store_commit_uncertain/tmp_left", r[0] == "store_commit_uncertain" and "tmp_left" in r[3], str(r))
st2 = HistoryFileStore(d, writable=True, durability="file_sync_only")
r2 = code(st2.reconcile, c.pub)
r3 = code(st2.publish, c.pub)
rec("then reconcile NOT_PUBLISHED but publish again store_artifact_present", r2 == ("ok", "NOT_PUBLISHED") and r3[0] == "store_artifact_present", "%s / %s" % (r2, r3[:1]))
shutil.rmtree(d)


# 5. mutation 10 of the request (published flag after the replace) is only seen with a combined fault
class G(FileOps):
    def __init__(self):
        self.replaced = False

    def replace(self, a, b):
        self.replaced = True
        raise OSError("x")

    def read_file(self, p):
        if p.endswith("write.lock") and self.replaced:
            raise OSError("x")
        return super().read_file(p)


d = root_with(c.current)
st = HistoryFileStore(d, writable=True, durability="file_sync_only", _ops=G())
r = code(st.publish, c.pub)
rec("replace fails + lock ownership lost on release -> store_commit_uncertain", r[0] == "store_commit_uncertain", str(r))
shutil.rmtree(d)

# 6. S2 and C-3 exclude each other (both directions), using a leftover lock of the other
d = root_with(c.current)
put(os.path.join(d, "write.lock"), b"v2_persistence.local.lock\nabc\n")
r = code(HistoryFileStore(d).read)
rec("S2 lock -> C-3 store_busy", r[0] == "store_busy")
os.unlink(os.path.join(d, "write.lock"))
put(os.path.join(d, "write.lock"), b"v2_history_local.lock\nabc\n")
r = code(LocalFileStore(d).read)
rec("C-3 lock -> S2 store_busy", r[0] == "store_busy")
os.unlink(os.path.join(d, "write.lock"))
r = code(LocalFileStore(d).read)
rec("S2 reader on a v2 root -> store_uninitialized", r[0] == "store_uninitialized")
shutil.rmtree(d)

# 7. precedence when several states hold: v1 + tmp, read-only + wrong mode
d = root_with(c.current)
put(os.path.join(d, "snapshot.json"), b"{}")
put(os.path.join(d, ".history.%s.tmp" % ("0" * 32)), b"x")
r = code(HistoryFileStore(d, writable=True).publish, c.pub)
rec("v1 + tmp: layout first", r[0] == "store_layout_unsupported", str(r[:2]))
shutil.rmtree(d)
d = root_with(None)
r = code(HistoryFileStore(d, writable=False).publish, by["GENESIS"].pub)
rec("read-only + CREATE to publish: which first", True, str(r[:2]))
r = code(HistoryFileStore(d, writable=False).initialize, by["DAILY"].pub)
rec("read-only + APPEND to initialize: which first", True, str(r[:2]))
shutil.rmtree(d)

# 8. case: names are compared exactly (on a case-insensitive filesystem a differently cased v1 file would be missed)
d = root_with(c.current)
put(os.path.join(d, "Snapshot.json"), b"{}")
r = code(HistoryFileStore(d).read)
rec("Snapshot.json (other case) is not seen as v1 [case-sensitive FS]", r[0] == "ok", str(r[:2]))
shutil.rmtree(d)

# 9. initialize then a day, all four outcomes of reconcile through the store
g = by["GENESIS"]
d = root_with(None)
st = HistoryFileStore(d, writable=True, durability="file_sync_only")
rec("reconcile GENESIS on empty root NOT_PUBLISHED", code(st.reconcile, g.pub) == ("ok", "NOT_PUBLISHED"))
rec("initialize INITIALIZED", code(st.initialize, g.pub) == ("ok", "INITIALIZED"))
rec("reconcile GENESIS after PUBLISHED", code(st.reconcile, g.pub) == ("ok", "PUBLISHED"))
rec("bytes are canonical", raw(d) == X.file_bytes(g.candidate))
rec("only history.json left", sorted(os.listdir(d)) == ["history.json"])
shutil.rmtree(d)

for src in ("DAILY", "RESOLUTION", "RESTART", "RESTORE"):
    cc = by[src]
    d = root_with(X.indented(cc.history) if src == "DAILY" else cc.current)
    st = HistoryFileStore(d, writable=True)
    r = code(st.publish, cc.pub)
    rec("publish %s PUBLISHED strict, canonical bytes" % src, r == ("ok", "PUBLISHED") and raw(d) == X.file_bytes(cc.candidate), str(r))
    rec("publish %s twice -> publication_stale" % src, code(st.publish, cc.pub)[0] == "publication_stale")
    shutil.rmtree(d)

bad = [r for r in results if not r[1]]
print("\n%d probes, %d not as expected" % (len(results), len(bad)))
