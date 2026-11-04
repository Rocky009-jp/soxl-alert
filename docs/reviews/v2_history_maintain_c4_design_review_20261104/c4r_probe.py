"""C-4 design review probe (ce4fd28). Runs against a work tree of 6d69bd7 with the trial diff applied (never pushed).

usage: python -B c4r_probe.py <trial-worktree>

R1  requested_at enters the plan, so a publication rebuilt after a crash has the same hash only with the same inputs.
R2  the trial runtime against the literal static audit of C4-20 (and the C-3 audit it would mirror).
R3  unlock: a target with the same inode but other bytes -> maintenance_plan_stale, yet quarantine/<key>/ was made.
R4  unlock with the lock in the plan, the lock gone before the first attempt -> which code.
R5  inspect cannot report a root whose 'quarantine' is a file, or whose history.json is a directory.
R6  raise ... from None inside except keeps __context__.
R7  injection 10: the MANIFEST identity from the publication equals the one from the bytes under the lock.
"""
import ast
import hashlib
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
from v2_history_maintain import HistoryMaintenance, plan_unlock  # noqa: E402
from v2_history_maintain.ops import MaintenanceOps  # noqa: E402
from v2_persistence.local.store import FILE_SYNC_ONLY_MODE  # noqa: E402
import datetime  # noqa: E402

FSO = FILE_SYNC_ONLY_MODE
results = []


def rec(rid, ok, text):
    results.append((rid, ok))
    print("%s %s %s" % (rid, "OBSERVED" if ok else "NOT-OBSERVED", text))


def code_of(fn, *a):
    try:
        fn(*a)
    except CoreError as e:
        return (e.code, getattr(e, "rule", None), getattr(e, "phase", None), getattr(e, "primary", None))
    return None


def root():
    return tempfile.mkdtemp(prefix="c4r_")


def put(r, name, data):
    with open(os.path.join(r, name), "wb") as f:
        f.write(data)


def get(r, name):
    with open(os.path.join(r, name), "rb") as f:
        return f.read()


def tree(r):
    out = []
    for d, ds, fs in os.walk(r):
        for n in sorted(ds + fs):
            out.append(os.path.relpath(os.path.join(d, n), r))
    return sorted(out)


class FailOnce(MaintenanceOps):
    def __init__(self, op, match):
        self.op, self.match, self.done = op, match, False

    def _maybe(self, op, path):
        if not self.done and op == self.op and self.match(path):
            self.done = True
            raise OSError("injected")

    def rename(self, src, dst):
        self._maybe("rename", src)
        return super().rename(src, dst)

    def unlink(self, path):
        self._maybe("unlink", path)
        return super().unlink(path)


WHEN2 = datetime.datetime(2026, 11, 5, 0, 0, tzinfo=datetime.timezone.utc)

# ---------------------------------------------------------------- R1 migration
c = C2.migration_case()
r = root()
put(r, "snapshot.json", c.data)
m = HistoryMaintenance(r, True, FSO, _ops=FailOnce("rename", lambda p: p.endswith("snapshot.json")))
e1 = code_of(m.migrate, c.pub, True)
names = sorted(os.listdir(r))
m2 = HistoryMaintenance(r, True, FSO)
# the operator rebuilds after the process ended: same request id, a new requested_at
plan2 = V.prepare_migration_plan(c.snap, c.rs, c.w.sessions, c.ledger, c.plan.basis["check_d"], "mig-1", WHEN2)
pub2 = U.publish_migration(plan2, plan2.plan_hash, m2.read_original("snapshot.json"), c.rs, c.w.sessions, c.ledger)
e2 = code_of(m2.migrate, pub2, True)
key = c.pub.publication_hash
man = json.loads(get(os.path.join(r, "quarantine", key), "MANIFEST"))
plan3 = V.prepare_migration_plan(c.snap, c.rs, c.w.sessions, c.ledger, c.plan.basis["check_d"], "mig-1", C2.WHEN)
pub3 = U.publish_migration(plan3, plan3.plan_hash, m2.read_original("snapshot.json"), c.rs, c.w.sessions, c.ledger)
res3 = m2.migrate(pub3, True)
rec("R1a", e1[0] == "maintenance_incomplete" and names == ["history.json", "quarantine", "snapshot.json"]
    and pub2.publication_hash != key and e2[:2] == ("maintenance_state_unexpected", "v1_and_v2")
    and "requested_at" not in man and pub3.publication_hash == key and res3.resumed is True,
    "migration: rename fault %s -> both; rebuilt with another requested_at: hash differs, migrate -> %s; MANIFEST keys"
    " %s; same requested_at -> same hash, resumed=%s" % (e1[:2], e2[:2], sorted(man), res3.resumed))
shutil.rmtree(r)

# ---------------------------------------------------------------- R1 adoption
c = C2.adoption_case()
r = root()
put(r, "history.json", c.data)
m = HistoryMaintenance(r, True, FSO, _ops=FailOnce("unlink", lambda p: p.endswith("write.lock")))
e1 = code_of(m.adopt, c.pub)
m2 = HistoryMaintenance(r, True, FSO)
rep = m2.inspect()
plan = plan_unlock(rep, "unl-1", True)
m2.unlock(plan, plan.plan_hash)
orig = m2.read_set_aside(c.pub.publication_hash, "history.json")
p_other = AD.prepare_prefix_adoption(orig, c.k, "ad1", WHEN2)
pub_other = U.publish_adoption(p_other, p_other.plan_hash, orig)
e2 = code_of(m2.adopt, pub_other)
p_same = AD.prepare_prefix_adoption(orig, c.k, "ad1", C2.WHEN)
pub_same = U.publish_adoption(p_same, p_same.plan_hash, orig)
res = m2.adopt(pub_same)
rec("R1b", e1[0] == "store_commit_uncertain" and pub_other.publication_hash != c.pub.publication_hash
    and e2 is not None and e2[0] in ("publication_stale", "maintenance_state_unexpected")
    and pub_same.publication_hash == c.pub.publication_hash and res.resumed is True,
    "adoption: release fault %s; rebuilt with another requested_at -> %s; same requested_at -> resumed=%s"
    % (e1[:2], e2[:2], res.resumed))
shutil.rmtree(r)

# ---------------------------------------------------------------- R2 static audit
pkg = os.path.join(TREE, "v2_history_maintain")
hits, imports = [], set()
for fn in sorted(os.listdir(pkg)):
    if not fn.endswith(".py"):
        continue
    t = ast.parse(open(os.path.join(pkg, fn)).read())
    for n in ast.walk(t):
        if isinstance(n, ast.Attribute) and n.attr in ("_make", "_of", "_wrap", "__new__", "from_dict"):
            hits.append("%s:%d .%s" % (fn, n.lineno, n.attr))
        if isinstance(n, ast.Call) and ast.unparse(n.func) in ("copy.copy", "copy.deepcopy"):
            hits.append("%s:%d %s()" % (fn, n.lineno, ast.unparse(n.func)))
        if isinstance(n, ast.Import):
            imports |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            imports.add(n.module.split(".")[0])
listed = {"os", "secrets", "stat", "json", "dataclasses", "typing", "v2_core", "v2_persistence", "v2_history",
          "v2_history_ops", "v2_recovery", "v2_history_publish"}
rec("R2", bool(hits) and bool(imports - listed),
    "C4-20 literal ('_make/_of/object.__new__ calls absent'): %d hits %s; imports outside design 2.3: %s"
    % (len(hits), hits[:6], sorted(imports - listed)))

# ---------------------------------------------------------------- R3 same inode, other bytes
r = root()
put(r, "history.json", C2.adoption_case().data)
put(r, ".history." + "a" * 32 + ".tmp", b"partial")
m = HistoryMaintenance(r, True, FSO)
plan = plan_unlock(m.inspect(), "unl-3", True)
with open(os.path.join(r, ".history." + "a" * 32 + ".tmp"), "ab") as f:  # same inode, bytes grow
    f.write(b"more")
before = tree(r)
e = code_of(m.unlock, plan, plan.plan_hash)
after = tree(r)
rec("R3", e[0] == "maintenance_plan_stale" and before != after and any(p.endswith("MANIFEST") for p in after),
    "same inode, other bytes -> %s; tree before %s, after %s" % (e[:3], before, after))
shutil.rmtree(r)

# ---------------------------------------------------------------- R4 the planned lock is gone
r = root()
put(r, "write.lock", b"v2_history_local.lock\n" + b"b" * 32 + b"\n")
m = HistoryMaintenance(r, True, FSO)
plan = plan_unlock(m.inspect(), "unl-4", True)
os.unlink(os.path.join(r, "write.lock"))
e = code_of(m.unlock, plan, plan.plan_hash)
rec("R4", e[:2] == ("maintenance_quarantine_invalid", "missing"),
    "lock in the plan gone before the first attempt -> %s (design 5.1 step 4 says maintenance_plan_stale)" % (e[:3],))
shutil.rmtree(r)

# ---------------------------------------------------------------- R5 inspect cannot report
r = root()
put(r, "history.json", C2.adoption_case().data)
put(r, "quarantine", b"x")
put(r, ".history." + "c" * 32 + ".tmp", b"left")
ea = code_of(HistoryMaintenance(r, True, FSO).inspect)
shutil.rmtree(r)
r = root()
os.mkdir(os.path.join(r, "history.json"))
put(r, ".history." + "d" * 32 + ".tmp", b"left")
eb = code_of(HistoryMaintenance(r, True, FSO).inspect)
shutil.rmtree(r)
rec("R5", ea is not None and eb is not None,
    "'quarantine' is a file -> inspect %s; history.json is a directory -> inspect %s (no report, so no plan)"
    % (ea and ea[:3], eb and eb[:3]))

# ---------------------------------------------------------------- R6 from None keeps __context__
try:
    try:
        raise OSError("/secret/path")
    except OSError:
        raise ValueError("fixed") from None
except ValueError as v:
    rec("R6", isinstance(v.__context__, OSError) and v.__suppress_context__ and v.__cause__ is None,
        "__context__=%r, __suppress_context__=%s" % (type(v.__context__).__name__, v.__suppress_context__))

# ---------------------------------------------------------------- R7 injection 10
c = C2.migration_case()
r = root()
put(r, "snapshot.json", c.data)
HistoryMaintenance(r, True, FSO).migrate(c.pub, True)
man = json.loads(get(os.path.join(r, "quarantine", c.pub.publication_hash), "MANIFEST"))
t = man["targets"][0]
from_bytes = {"raw_sha256": hashlib.sha256(c.data).hexdigest(), "raw_size": len(c.data)}
from_pub = c.pub.to_dict()["body"]["source_v1"]
rec("R7", from_bytes == from_pub == {"raw_sha256": t["raw_sha256"], "raw_size": t["raw_size"]},
    "MANIFEST identity == bytes under the lock == publication's source_v1 (check_publication forces it); the trial "
    "builds the MANIFEST from the publication before the lock")
shutil.rmtree(r)

print("summary: %d/%d observed" % (sum(1 for _r, ok in results if ok), len(results)))
