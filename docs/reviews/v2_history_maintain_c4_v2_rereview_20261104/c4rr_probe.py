"""C-4 second edition (2a3a232) re-review probe. Runs against a work tree of 6d69bd7 with the (unchanged) trial diff.

usage: python -B c4rr_probe.py <trial-worktree>

T1  N-01, migration: in the "both" state, requested_at read back from history.json (read_original) rebuilds the
    same hash and resumes; another requested_at stops with maintenance_state_unexpected and leaves the root as it was.
T2  N-01, adoption: after a release fault and the unlock, requested_at read from history.json plus the bytes from
    read_set_aside rebuild the same hash; another requested_at stops with publication_stale/raw, root unchanged.
T3  N-02: the trial runtime against the second-edition C4-20 (names from v2_history_publish; _make/_of only on
    RootReport/UnlockPlan).
T4  N-03: bytes read under the lock that differ from the publication -> no MANIFEST and no quarantine (migrate,
    adopt); the read comes before the MANIFEST in the call record; injection 10 (MANIFEST before the read) is caught.
"""
import ast
import importlib
import json
import os
import shutil
import sys
import tempfile

TREE = os.path.abspath(sys.argv[1])
sys.path.insert(0, TREE)
sys.path.insert(0, os.path.join(TREE, "tests", "v2_history_publish"))
import c2_helpers as C2  # noqa: E402
import v2_history as V  # noqa: E402
import v2_history_adopt as AD  # noqa: E402
import v2_history_publish as U  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_recovery.common import parse_aware_datetime  # noqa: E402
import v2_history_maintain.store as MS  # noqa: E402
from v2_history_maintain import HistoryMaintenance, plan_unlock  # noqa: E402
from v2_history_maintain.ops import MaintenanceOps  # noqa: E402
from v2_persistence.local.store import FILE_SYNC_ONLY_MODE as FSO  # noqa: E402
import datetime  # noqa: E402

results = []
WHEN2 = datetime.datetime(2026, 11, 5, 0, 0, tzinfo=datetime.timezone.utc)


def rec(rid, ok, text):
    results.append(ok)
    print("%s %s %s" % (rid, "OK" if ok else "NG", text))


def code_of(fn, *a):
    try:
        fn(*a)
    except CoreError as e:
        return (e.code, getattr(e, "rule", None))
    return None


def put(r, name, data):
    with open(os.path.join(r, name), "wb") as f:
        f.write(data)


def snap(r):
    out = {}
    for d, ds, fs in os.walk(r):
        for n in ds + fs:
            p = os.path.join(d, n)
            out[os.path.relpath(p, r)] = open(p, "rb").read() if os.path.isfile(p) else None
    return out


def requested_at_of(history_bytes, key="requested_at"):
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == key and isinstance(v, str):
                    found.add(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(json.loads(history_bytes.decode("utf-8")))
    return found


class Faulty(MaintenanceOps):
    def __init__(self, op, suffix):
        self.op, self.suffix, self.done, self.trace = op, suffix, False, []

    def _hit(self, op, path):
        self.trace.append((op, os.path.basename(path)))
        if not self.done and op == self.op and path.endswith(self.suffix):
            self.done = True
            raise OSError("injected")

    def rename(self, src, dst):
        self._hit("rename", src)
        return super().rename(src, dst)

    def unlink(self, path):
        self._hit("unlink", path)
        return super().unlink(path)


class Swap(MaintenanceOps):
    """Returns other bytes when `name` is read (what the publication does not expect); records the calls."""

    def __init__(self, name):
        self.name, self.trace = name, []

    def read_file(self, path):
        data, st = super().read_file(path)
        self.trace.append(("read_file", os.path.basename(path)))
        if os.path.basename(path) == self.name and self.name:
            data = data + b" "
        return data, st

    def create_exclusive(self, path):
        self.trace.append(("create_exclusive", os.path.basename(path)))
        return super().create_exclusive(path)

    def mkdir(self, path):
        self.trace.append(("mkdir", os.path.basename(path)))
        return super().mkdir(path)


# ------------------------------------------------------------------------------------------------ T1 migration
c = C2.migration_case()
r = tempfile.mkdtemp(prefix="c4rr_")
put(r, "snapshot.json", c.data)
e = code_of(HistoryMaintenance(r, True, FSO, _ops=Faulty("rename", "snapshot.json")).migrate, c.pub, True)
m = HistoryMaintenance(r, True, FSO)
texts = requested_at_of(m.read_original("history.json"))
when = parse_aware_datetime(sorted(texts)[0], "requested_at") if len(texts) == 1 else None
cd = c.plan.basis["check_d"]
bad = V.prepare_migration_plan(c.snap, c.rs, c.w.sessions, c.ledger, cd, "mig-1", WHEN2)
bad_pub = U.publish_migration(bad, bad.plan_hash, m.read_original("snapshot.json"), c.rs, c.w.sessions, c.ledger)
before = snap(r)
e_bad = code_of(m.migrate, bad_pub, True)
unchanged = snap(r) == before
plan = V.prepare_migration_plan(c.snap, c.rs, c.w.sessions, c.ledger, cd, "mig-1", when)
pub = U.publish_migration(plan, plan.plan_hash, m.read_original("snapshot.json"), c.rs, c.w.sessions, c.ledger)
res = m.migrate(pub, True)
rec("T1", e is not None and len(texts) == 1 and bad_pub.publication_hash != c.pub.publication_hash
    and e_bad == ("maintenance_state_unexpected", "v1_and_v2") and unchanged
    and pub.publication_hash == c.pub.publication_hash and res.resumed is True
    and sorted(os.listdir(r)) == ["history.json", "quarantine"],
    "migration: fault %s; requested_at in history.json %s; other -> %s, root unchanged=%s; read back -> same hash, "
    "resumed=%s, root %s" % (e, sorted(texts), e_bad, unchanged, res.resumed, sorted(os.listdir(r))))
shutil.rmtree(r)

# ------------------------------------------------------------------------------------------------ T2 adoption
c = C2.adoption_case()
r = tempfile.mkdtemp(prefix="c4rr_")
put(r, "history.json", c.data)
e = code_of(HistoryMaintenance(r, True, FSO, _ops=Faulty("unlink", "write.lock")).adopt, c.pub)
m = HistoryMaintenance(r, True, FSO)
p = plan_unlock(m.inspect(), "unl-1", True)
m.unlock(p, p.plan_hash)
key = c.pub.publication_hash
orig = m.read_set_aside(key, "history.json")
new_texts = requested_at_of(m.read_original("history.json")) - requested_at_of(orig)
when = parse_aware_datetime(sorted(new_texts)[0], "requested_at") if len(new_texts) == 1 else None
bad = AD.prepare_prefix_adoption(orig, c.k, "ad1", WHEN2)
bad_pub = U.publish_adoption(bad, bad.plan_hash, orig)
before = snap(r)
e_bad = code_of(m.adopt, bad_pub)
unchanged = snap(r) == before
plan = AD.prepare_prefix_adoption(orig, c.k, "ad1", when)
pub = U.publish_adoption(plan, plan.plan_hash, orig)
res = m.adopt(pub)
rec("T2", e is not None and e[0] == "store_commit_uncertain" and len(new_texts) == 1
    and e_bad == ("publication_stale", "raw") and unchanged and pub.publication_hash == key and res.resumed is True,
    "adoption: fault %s; new requested_at in history.json %s; other -> %s, root unchanged=%s; read back -> same "
    "hash, resumed=%s" % (e, sorted(new_texts), e_bad, unchanged, res.resumed))
shutil.rmtree(r)

# ------------------------------------------------------------------------------------------------ T3 C4-20 (2nd ed.)
pkg = os.path.join(TREE, "v2_history_maintain")
viol, publish_names = [], set()
for fn in sorted(os.listdir(pkg)):
    if not fn.endswith(".py"):
        continue
    t = ast.parse(open(os.path.join(pkg, fn)).read())
    for n in ast.walk(t):
        if isinstance(n, ast.ImportFrom) and n.module == "v2_history_publish":
            publish_names |= {a.asname or a.name for a in n.names}
    for n in ast.walk(t):
        if isinstance(n, ast.Attribute) and n.attr in ("_make", "_of", "_wrap", "from_dict", "__new__"):
            base = ast.unparse(n.value)
            if base in publish_names or base == "object":
                viol.append("%s:%d %s" % (fn, n.lineno, ast.unparse(n)))
            elif n.attr in ("_make", "_of") and base not in ("RootReport", "UnlockPlan", "cls"):
                viol.append("%s:%d %s" % (fn, n.lineno, ast.unparse(n)))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("HistoryPublication",
                                                                                    "Reconciliation"):
            viol.append("%s:%d constructs %s" % (fn, n.lineno, n.func.id))
rec("T3", not viol and len(publish_names) == 12, "violations of the 2nd-edition C4-20: %s; names imported from "
    "v2_history_publish: %d" % (viol, len(publish_names)))

# ------------------------------------------------------------------------------------------------ T4 N-03
def t4(store_module, label):
    out = []
    c = C2.migration_case()
    r = tempfile.mkdtemp(prefix="c4rr_")
    put(r, "snapshot.json", c.data)
    ops = Swap("snapshot.json")
    e = code_of(store_module.HistoryMaintenance(r, True, FSO, _ops=ops).migrate, c.pub, True)
    out.append(e == ("publication_stale", "source_v1") and sorted(os.listdir(r)) == ["snapshot.json"])
    shutil.rmtree(r)
    c = C2.adoption_case()
    r = tempfile.mkdtemp(prefix="c4rr_")
    put(r, "history.json", c.data)
    e = code_of(store_module.HistoryMaintenance(r, True, FSO, _ops=Swap("history.json")).adopt, c.pub)
    out.append(e is not None and e[0] == "publication_stale" and sorted(os.listdir(r)) == ["history.json"])
    shutil.rmtree(r)
    c = C2.migration_case()
    r = tempfile.mkdtemp(prefix="c4rr_")
    put(r, "snapshot.json", c.data)
    ops = Swap("")
    store_module.HistoryMaintenance(r, True, FSO, _ops=ops).migrate(c.pub, True)
    tr = ops.trace
    i_read = tr.index(("read_file", "snapshot.json"))
    i_q = min(i for i, t in enumerate(tr) if t[0] == "mkdir")
    out.append(i_read < i_q)
    shutil.rmtree(r)
    return out


ok_trial = t4(MS, "trial")
src = open(MS.__file__).read()
old = ("            if has_v1 and not has_h:\n                v1 = self._load(V1_NAME)\n"
       "                candidate = _checked(None, publication, v1)\n                self._probe_durability()\n"
       "                kdir, resumed = self._key_dir(ctx, key, manifest, allowed=())\n"
       "                self._ensure_manifest(ctx, kdir, manifest)\n")
new = ("            if has_v1 and not has_h:\n                kdir, resumed = self._key_dir(ctx, key, manifest, allowed=())\n"
       "                self._ensure_manifest(ctx, kdir, manifest)\n                v1 = self._load(V1_NAME)\n"
       "                candidate = _checked(None, publication, v1)\n                self._probe_durability()\n")
assert src.count(old) == 1
mdir = tempfile.mkdtemp(prefix="c4rr_mut_")
shutil.copytree(os.path.join(TREE, "v2_history_maintain"), os.path.join(mdir, "v2_history_maintain_m10"))
with open(os.path.join(mdir, "v2_history_maintain_m10", "store.py"), "w") as f:
    f.write(src.replace(old, new))
sys.path.insert(0, mdir)
M10 = importlib.import_module("v2_history_maintain_m10.store")
ok_m10 = t4(M10, "m10")
shutil.rmtree(mdir)
rec("T4", all(ok_trial) and not all(ok_m10),
    "trial [migrate stale->no quarantine, adopt stale->no quarantine, read before mkdir] = %s; injection 10 (MANIFEST "
    "before the read, migrate) = %s -> detected=%s" % (ok_trial, ok_m10, not all(ok_m10)))

print("summary: %d/%d OK" % (sum(results), len(results)))
