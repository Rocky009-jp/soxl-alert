"""C-4 implementation review: targeted probes (independent of the implementer's tests).

usage: python -B c4i_probe.py <repo>
"""
import os
import shutil
import sys

REPO = os.path.abspath(sys.argv[1])
sys.path[:0] = [REPO, os.path.join(REPO, "tests", "v2_history_maintain")]
import c4_helpers as H  # noqa: E402
import v2_history_maintain as M  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_history_local import HistoryFileStore  # noqa: E402

out = []


def show(tag, fn):
    try:
        r = fn()
        out.append("%s -> OK %r" % (tag, r))
    except CoreError as e:
        out.append("%s -> %s/%s/%s rule=%s primary=%s cleanup=%s" % (tag, e.code, getattr(e, "field", None), getattr(e, "phase", None),
                   getattr(e, "rule", None), getattr(e, "primary", None), getattr(e, "cleanup", None)))
    except Exception as e:  # noqa: BLE001
        out.append("%s -> LEAK %s: %r" % (tag, type(e).__name__, e))


def fresh():
    r = H.make_root()
    return r


def m(root, ops=None, **kw):
    return M.HistoryMaintenance(root, writable=True, _ops=ops, **kw)


FNF = lambda: FileNotFoundError(2, "gone")  # noqa: E731

# --- X1: migrate resume, history.json vanishes between the listing and the read (FileNotFoundError) ----------
for state in ("both", "v2_only"):
    for nth in (1, 2):
        case = H.migration()
        root = fresh()
        H.put(root, H.V1, case.data)
        ops = H.C4Ops().fail("rename", "snapshot")
        try:
            m(root, ops).migrate(case.pub, True)
        except CoreError:
            pass
        if state == "v2_only":
            m(root).migrate(case.pub, True)            # completes (both -> v2 only)
        ops = H.C4Ops().fail("lstat", "history", exc=FNF(), nth=nth)
        show("X1 migrate resume %s, FileNotFoundError at lstat:history #%d" % (state, nth),
             lambda: m(root, ops).migrate(case.pub, True))
        out.append("   root after: %s" % sorted(os.listdir(root)))
        shutil.rmtree(root, True)

# --- X2: unlock, the second target changes after the first rename (plan_stale after a change) -------------------
root = fresh()
H.lock_and_tmps(root, tmps=((H.TMP_H, b"c3-partial"), (H.TMP_H2, b"c3-second")))
plan = M.plan_unlock(m(root).inspect(), "u-1", True)


def swap(real, src, dst):
    real(src, dst)
    p = os.path.join(root, H.TMP_H2)
    with open(p + ".new", "wb") as f:
        f.write(b"c3-second")      # same bytes, another inode (made while the old one still exists)
    os.replace(p + ".new", p)


ops = H.C4Ops().add("rename", "tmp", nth=1, wrap=swap)
show("X2 unlock, 2nd target replaced (same bytes, new inode) after the 1st rename", lambda: m(root, ops).unlock(plan, plan.plan_hash))
out.append("   root after: %s ; quarantine: %s" % (sorted(os.listdir(root)),
           {k: H.qnames(root, k) for k in H.keys(root)}))
show("X2 same plan again", lambda: m(root).unlock(plan, plan.plan_hash))
rep = m(root).inspect()
out.append("   after same plan: root %s artifacts=%d" % (sorted(os.listdir(root)), len(rep.artifacts)))
if rep.artifacts:
    plan2 = M.plan_unlock(rep, "u-2", True)
    show("X2 new plan", lambda: m(root).unlock(plan2, plan2.plan_hash))
out.append("   root after: %s ; keys=%d" % (sorted(os.listdir(root)), len(H.keys(root))))
shutil.rmtree(root, True)

# --- X3: adopt, copy reads back differently -> copy_mismatch; then the same publication again ----------------------
case = H.adoption()
root = fresh()
H.put(root, H.HIST, case.data)


def corrupt(real, src, dst):
    real(src, dst)
    with open(dst, "r+b") as f:          # the copy reads back differently
        f.seek(0)
        f.write(b"X")


ops = H.C4Ops().add("replace", "qfile", nth=1, wrap=corrupt)
show("X3 adopt with a copy written wrong", lambda: m(root, ops).adopt(case.pub))
show("X3 adopt again, same publication", lambda: m(root).adopt(case.pub))
show("X3 C-3 still reads", lambda: HistoryFileStore(root).read() is not None)
out.append("   history.json is original: %s" % (H.raw(root, H.HIST) == case.data))
other = H.adoption(when=H.WHEN2)
show("X3 adopt with another requested_at (new key)", lambda: m(root).adopt(other.pub).status)
shutil.rmtree(root, True)

# --- X4: 19b equivalence: the mkdir failure, observed at the exit ------------------------------------------------
case = H.adoption()
root = fresh()
H.put(root, H.HIST, case.data)
inj = H.injected()
inj.filename = root
ops = H.C4Ops().fail("mkdir", "qdir", exc=inj)
try:
    m(root, ops).adopt(case.pub)
except CoreError as e:
    out.append("X4 mkdir failure -> %s/%s/%s primary=%s context=%r cause=%r suppress=%s" % (
        e.code, e.field, e.phase, e.primary, e.__context__, e.__cause__, e.__suppress_context__))
shutil.rmtree(root, True)

# --- X5: the rule label of a v1 that disappears under the lock ---------------------------------------------------
case = H.migration()
root = fresh()
H.put(root, H.V1, case.data)
ops = H.C4Ops().fail("lstat", "snapshot", exc=FNF())
show("X5 migrate, snapshot.json lstat FileNotFoundError", lambda: m(root, ops).migrate(case.pub, True))
shutil.rmtree(root, True)

# --- X6: unlock with a plan whose lock is gone and nothing in quarantine (the owner released it) -----------------
root = fresh()
H.lock_and_tmps(root, tmps=())
plan = M.plan_unlock(m(root).inspect(), "u-1", True)
os.unlink(os.path.join(root, H.LOCK))
show("X6 plan names a lock that its owner released", lambda: m(root).unlock(plan, plan.plan_hash))
out.append("   root after: %s" % sorted(os.listdir(root)))
shutil.rmtree(root, True)

# --- X7: inspect on odd roots -----------------------------------------------------------------------------------
root = fresh()
os.mkdir(os.path.join(root, H.HIST))
with open(os.path.join(root, "quarantine"), "wb") as f:
    f.write(b"x")
show("X7 inspect: history.json is a dir, quarantine is a file",
     lambda: (lambda r: (r.layout, r.history, r.quarantine))(m(root).inspect()))
shutil.rmtree(root, True)

# --- X8: adopt resume after replace when the copy in quarantine was removed by hand -------------------------------
case = H.adoption()
root = fresh()
H.put(root, H.HIST, case.data)
ops = H.C4Ops().fail("unlink", "lock")
show("X8 adopt, release fails after replace", lambda: m(root, ops).adopt(case.pub))
plan = M.plan_unlock(m(root).inspect(), "u-1", True)
m(root).unlock(plan, plan.plan_hash)
os.unlink(os.path.join(root, "quarantine", case.key, H.HIST))
show("X8 adopt again with the copy removed by hand", lambda: m(root).adopt(case.pub))
shutil.rmtree(root, True)

# --- X9: read-only maintenance on a mutating call -------------------------------------------------------------
root = fresh()
show("X9 read-only adopt", lambda: M.HistoryMaintenance(root).adopt(H.adoption().pub))
shutil.rmtree(root, True)

print("\n".join(out))
