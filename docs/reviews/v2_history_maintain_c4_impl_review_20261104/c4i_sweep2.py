"""C-4 implementation review (independent): extra exception kinds on the first call, and double faults
(a fault in the first call, then a second fault anywhere in the person's first recovery round), then the
documented procedure (5.4) without faults. Reuses the implementer's Scenario only for setup / invariants / finish.

usage: python -B c4i_sweep2.py <repo> <mode> <kind> [durability]
  mode = kinds  : single faults with FileNotFoundError / PermissionError / IsADirectoryError / KeyError / ValueError
  mode = double : first fault (OSError with secret, before/after each call) x second fault (same, before/after each call
                  of the recovery round)
"""
import collections
import os
import shutil
import sys
import unittest

REPO = os.path.abspath(sys.argv[1])
sys.path[:0] = [REPO, os.path.join(REPO, "tests", "v2_history_maintain")]
import c4_helpers as H  # noqa: E402
import test_c4_07_procedure_faults as T  # noqa: E402
import v2_history_maintain as M  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402

mode, kind = sys.argv[2], sys.argv[3]
dur = sys.argv[4] if len(sys.argv) > 4 else "strict"
F2EXC = sys.argv[5].split(",") if len(sys.argv) > 5 else ["os"]
tc = unittest.TestCase()
tc.maxDiff = None


def positions(trace):
    seen, out = {}, []
    for op, k in trace:
        seen[(op, k)] = seen.get((op, k), 0) + 1
        out.append((op, k, seen[(op, k)]))
    return out


def first_trace():
    sc = T.Scenario(kind, dur)
    root = H.make_root()
    try:
        sc.setup(root)
        ops = H.C4Ops()
        sc.call(sc.maint(root, ops))
        return list(ops.trace)
    finally:
        shutil.rmtree(root, True)


def recovery_round(sc, root, ops):
    """The first round of 5.4 with every call through `ops`: inspect, unlock what is left, the same operation again."""
    m = sc.maint(root, ops)
    report = m.inspect()
    if report.artifacts:
        plan = M.plan_unlock(report, "fix-r", True)
        m.unlock(plan, plan.plan_hash)
    if sc.kind == "migrate":
        key = sc.case.key
        have = os.path.exists(os.path.join(root, "quarantine", key, H.V1))
        data = m.read_set_aside(key, H.V1) if have else m.read_original(H.V1)
        again = H.rebuild_migration(sc.case, data)
        assert again.publication_hash == key
        return m.migrate(again, True)
    if sc.kind == "adopt":
        key = sc.case.key
        raw = m.read_original(H.HIST)
        data = raw if raw == sc.case.data else m.read_set_aside(key, H.HIST)
        again = H.rebuild_adoption(sc.case, data)
        assert again.publication_hash == key
        return m.adopt(again)
    rest = m.inspect()
    if not rest.artifacts:
        return None
    return m.unlock(sc.plan, sc.plan.plan_hash)


def exc_of(name):
    sec = H.SECRET
    return {"fnf": lambda: FileNotFoundError(2, "gone " + sec, "/x/" + sec),
            "perm": lambda: PermissionError(13, "denied " + sec, "/x/" + sec),
            "isdir": lambda: IsADirectoryError(21, "isdir " + sec, "/x/" + sec),
            "keyerr": lambda: KeyError(sec),
            "valerr": lambda: ValueError(sec),
            "os": lambda: H.injected()}[name]()


stats = collections.Counter()
problems = []


def one(f1, f2=None, f2_exc="os"):
    """f1 = (op, kind, nth, after, excname); f2 likewise for the recovery round."""
    sc = T.Scenario(kind, dur)
    root = H.make_root()
    label = "%s/%s F1=%s F2=%s" % (kind, dur, f1, f2)
    try:
        sc.setup(root)
        ops = H.C4Ops()
        op, k, nth, after, en = f1
        e1 = exc_of(en)
        ops.add(op, k, nth, before=None if after else e1, after=e1 if after else None)
        try:
            sc.call(sc.maint(root, ops))
            stats["f1_ok"] += 1
        except CoreError as e:
            T.no_leak(tc, e, root)
            stats["f1:" + e.code] += 1
        except Exception as e:  # noqa: BLE001
            problems.append((label, "F1 leaked %s: %r" % (type(e).__name__, e)))
            stats["f1_LEAK"] += 1
            return
        sc.check_after_failure(tc, root)
        if f2 is not None:
            ops2 = H.C4Ops()
            op, k, nth, after, en = f2
            e2 = exc_of(en)
            ops2.add(op, k, nth, before=None if after else e2, after=e2 if after else None)
            try:
                recovery_round(sc, root, ops2)
                stats["f2_ok"] += 1
            except CoreError as e:
                T.no_leak(tc, e, root)
                stats["f2:" + e.code] += 1
            except AssertionError:
                raise
            except Exception as e:  # noqa: BLE001
                problems.append((label, "F2 leaked %s: %r" % (type(e).__name__, e)))
                stats["f2_LEAK"] += 1
                return
            if sc.kind in ("migrate", "adopt"):
                sc.check_after_failure(tc, root)
            else:
                check_unlock_any_key(sc, root)
        sc.finish(tc, root)
        sc.check_final(tc, root)
        stats["final_ok"] += 1
    except AssertionError as a:
        problems.append((label, "ASSERT " + str(a)[:300]))
        stats["ASSERT"] += 1
    finally:
        shutil.rmtree(root, True)


def check_unlock_any_key(sc, root):
    """After the recovery round the person's own plan has another key: each left byte must be in the root or in
    some key directory of the quarantine."""
    for n, (data, _ino) in sc.before.items():
        found = []
        if os.path.lexists(os.path.join(root, n)):
            found.append(H.raw(root, n))
        for key in (H.keys(root) if os.path.isdir(os.path.join(root, "quarantine")) else []):
            if os.path.lexists(os.path.join(root, "quarantine", key, n)):
                found.append(H.qraw(root, key, n))
        tc.assertIn(data, found, "the left bytes of %s are kept somewhere" % n)


def recovery_trace(f1):
    sc = T.Scenario(kind, dur)
    root = H.make_root()
    try:
        sc.setup(root)
        ops = H.C4Ops()
        op, k, nth, after, en = f1
        e1 = exc_of(en)
        ops.add(op, k, nth, before=None if after else e1, after=e1 if after else None)
        try:
            sc.call(sc.maint(root, ops))
            return None
        except Exception:  # noqa: BLE001
            pass
        ops2 = H.C4Ops()
        try:
            recovery_round(sc, root, ops2)
        except Exception:  # noqa: BLE001
            pass
        return list(ops2.trace)
    finally:
        shutil.rmtree(root, True)


pos1 = positions(first_trace())
if mode == "kinds":
    for (op, k, nth) in pos1:
        for after in (False, True):
            if after and op == "open_writer":
                continue
            for en in ("fnf", "perm", "isdir", "keyerr", "valerr"):
                one((op, k, nth, after, en))
elif mode == "double":
    for (op, k, nth) in pos1:
        for after in (False, True):
            if after and op == "open_writer":
                continue
            f1 = (op, k, nth, after, "os")
            rt = recovery_trace(f1)
            if rt is None:
                stats["f1_no_failure"] += 1
                continue
            for (op2, k2, nth2) in positions(rt):
                for after2 in (False, True):
                    if after2 and op2 == "open_writer":
                        continue
                    for en2 in F2EXC:
                        one(f1, (op2, k2, nth2, after2, en2))
total = sum(v for k, v in stats.items() if k.startswith("f1") and k != "f1_no_failure")
print("%s %s %s cases=%d first_positions=%d" % (mode, kind, dur, total, len(pos1)))
for k_, v in sorted(stats.items()):
    print("  %-40s %d" % (k_, v))
print("problems=%d" % len(problems))
seen = collections.Counter()
for label, what in problems:
    sig = what[:120]
    seen[sig] += 1
    if seen[sig] <= 3:
        print("  ", label, "|", what)
for sig, n in seen.most_common():
    print("  x%d %s" % (n, sig))
