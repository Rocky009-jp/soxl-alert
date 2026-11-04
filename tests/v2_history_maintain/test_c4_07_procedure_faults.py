"""C4-16 the order of the calls and the exhaustive single faults, C4-17 the persistence levels, C4-19 no leak."""
import os
import shutil
import unittest

import c4_helpers as H
import v2_history_maintain as M
from v2_core.errors import CoreError

WATCH = ("create_exclusive", "write", "replace", "rename", "mkdir", "probe_dir_sync", "fsync_dir", "fsync_file",
         "unlink", "read_file", "listdir")
LOCK_TAKE = ["create_exclusive:lock", "write:lock", "listdir:root"]
LOCK_FREE = ["read_file:lock", "unlink:lock"]
Q_MAKE = ["probe_dir_sync:root", "mkdir:qdir", "fsync_dir:root", "mkdir:kdir", "fsync_dir:qdir", "listdir:kdir"]
MANIFEST = ["create_exclusive:qtmp", "write:qtmp", "fsync_file:qtmp", "replace:manifest", "fsync_dir:kdir"]
PUBLISH = ["probe_dir_sync:root", "create_exclusive:tmp", "write:tmp", "fsync_file:tmp", "read_file:lock",
           "replace:history", "fsync_dir:root"]

ORDER_MIGRATE = LOCK_TAKE + ["read_file:snapshot"] + Q_MAKE + MANIFEST + PUBLISH + [
    "read_file:snapshot", "rename:snapshot", "fsync_dir:kdir", "fsync_dir:root"] + LOCK_FREE
ORDER_ADOPT = LOCK_TAKE + ["read_file:history"] + Q_MAKE + MANIFEST + [
    "create_exclusive:qtmp", "write:qtmp", "fsync_file:qtmp", "replace:qfile", "fsync_dir:kdir", "read_file:qfile"
] + PUBLISH + LOCK_FREE
ORDER_UNLOCK_WITH_LOCK = ["listdir:root", "read_file:tmp", "read_file:s2tmp", "read_file:lock"] + Q_MAKE + MANIFEST + [
    "read_file:tmp", "rename:tmp", "read_file:s2tmp", "rename:s2tmp", "read_file:lock", "rename:lock",
    "fsync_dir:kdir", "fsync_dir:root"]
ORDER_UNLOCK_TMP_ONLY = ["listdir:root"] + LOCK_TAKE + ["read_file:tmp", "read_file:s2tmp"] + Q_MAKE + MANIFEST + [
    "read_file:tmp", "rename:tmp", "read_file:s2tmp", "rename:s2tmp", "fsync_dir:kdir", "fsync_dir:root"] + LOCK_FREE


def watched(ops):
    return [n for n in ops.ops(*[w for w in WATCH], *["%s:%s" % (w, k) for w in WATCH for k in
                                                       ("lock", "history", "snapshot", "tmp", "s2tmp", "qtmp", "manifest",
                                                        "qfile", "qdir", "kdir", "root")])]


def stripped(names):
    """The trace as the documents describe it: the calls named in the design, in order (the per-call helpers of the write
    - fstat, open_writer, flush, close - and the repeated lstat are not part of it)."""
    keep = set(ORDER_MIGRATE + ORDER_ADOPT + ORDER_UNLOCK_WITH_LOCK + ORDER_UNLOCK_TMP_ONLY)
    return [n for n in names if n in keep]


class Order(H.RootCase):
    def test_migrate(self):
        case = H.migration()
        self.put_v1(case)
        ops = H.C4Ops()
        self.maint(ops).migrate(case.pub, True)
        self.assertEqual(stripped(watched(ops)), ORDER_MIGRATE)

    def test_adopt(self):
        case = H.adoption()
        self.put_history(case.data)
        ops = H.C4Ops()
        self.maint(ops).adopt(case.pub)
        self.assertEqual(stripped(watched(ops)), ORDER_ADOPT)

    def test_unlock_with_the_left_lock_as_the_exclusion(self):
        H.lock_and_tmps(self.root)
        plan = M.plan_unlock(self.maint().inspect(), "u-1", True)
        ops = H.C4Ops()
        self.maint(ops).unlock(plan, plan.plan_hash)
        self.assertEqual(stripped(watched(ops)), ORDER_UNLOCK_WITH_LOCK)

    def test_unlock_of_temporary_files_with_the_c4_lock(self):
        H.lock_and_tmps(self.root, lock=None)
        plan = M.plan_unlock(self.maint().inspect(), "u-1", True)
        ops = H.C4Ops()
        self.maint(ops).unlock(plan, plan.plan_hash)
        self.assertEqual(stripped(watched(ops)), ORDER_UNLOCK_TMP_ONLY)

    def test_nothing_is_ever_unlinked_but_the_c4_lock_and_the_own_temporary_file(self):
        for make in ("migrate", "adopt"):
            root = H.make_root()
            self.addCleanup(shutil.rmtree, root, True)
            ops = H.C4Ops()
            if make == "migrate":
                case = H.migration()
                H.put(root, H.V1, case.data)
                M.HistoryMaintenance(root, writable=True, _ops=ops).migrate(case.pub, True)
            else:
                case = H.adoption()
                H.put(root, H.HIST, case.data)
                M.HistoryMaintenance(root, writable=True, _ops=ops).adopt(case.pub)
            self.assertEqual([k for (op, k) in ops.trace if op == "unlink"], ["lock"])

    def test_short_writes_are_repeated(self):
        case = H.adoption()
        self.put_history(case.data)
        ops = H.C4Ops()
        ops.max_write = 7
        self.maint(ops).adopt(case.pub)
        self.assertGreater(len([1 for (op, k) in ops.trace if op == "write" and k == "qtmp"]), 10)
        self.assertEqual(H.qraw(self.root, case.key, "history.json"), case.data)
        self.assertEqual(H.raw(self.root), case.candidate_bytes)

    def test_a_write_that_makes_no_progress_is_an_error_not_a_loop(self):
        case = H.adoption()
        self.put_history(case.data)
        ops = H.C4Ops().add("write", "qtmp", wrap=lambda real, w, d: 0)
        e = self.run_err(self.maint(ops).adopt, case.pub)
        self.assertErr(e, "maintenance_incomplete", "quarantine", "manifest", primary="store_io_error")
        self.assertEqual(H.raw(self.root), case.data)
        self.assertEqual(sorted(os.listdir(self.root)), ["history.json", "quarantine"])


# --- the exhaustive single faults ---------------------------------------------------------------------------------------

def _exc(kind):
    if kind == 0:
        return H.injected()
    if kind == 1:
        return FileExistsError(17, "exists " + H.SECRET, H.SECRET)
    return RuntimeError("boom " + H.SECRET)


class Scenario(object):
    """One of the three operations (the unlock in two forms). run() makes the root, builds what the person had before the
    failure, and calls the operation under `ops`; finish() is the person's procedure of design 5.4; the checks say what must
    be true after a failure and after the procedure."""

    def __init__(self, kind, durability):
        self.kind, self.durability = kind, durability

    def setup(self, root):
        k = self.kind
        if k == "migrate":
            self.case = H.migration()
            H.put(root, H.V1, self.case.data)
        elif k == "adopt":
            self.case = H.adoption()
            H.put(root, H.HIST, self.case.data)
        else:
            H.lock_and_tmps(root, lock=H.LOCK_C3 if k == "unlock_lock" else None,
                            tmps=((H.TMP_H, b"c3-partial"), (H.TMP_H2, b"c3-second"), (H.TMP_S, b"s2-partial")))
            m = M.HistoryMaintenance(root, writable=True)
            self.plan = M.plan_unlock(m.inspect(), "u-1", True)
            self.before = {n: (H.raw(root, n), os.lstat(os.path.join(root, n)).st_ino) for n in os.listdir(root)}

    def call(self, m):
        if self.kind == "migrate":
            return m.migrate(self.case.pub, True)
        if self.kind == "adopt":
            return m.adopt(self.case.pub)
        return m.unlock(self.plan, self.plan.plan_hash)

    def maint(self, root, ops=None):
        return M.HistoryMaintenance(root, writable=True, durability=self.durability, _ops=ops)

    # what must hold after a failure
    def check_after_failure(self, tc, root):
        k = self.kind
        key = self.case.key if k in ("migrate", "adopt") else self.plan.plan_hash
        kd = os.path.join(root, "quarantine", key)

        def where(name):
            p = os.path.join(root, name)
            if os.path.lexists(p):
                return H.raw(root, name)
            q = os.path.join(kd, name)
            return H.qraw(root, key, name) if os.path.lexists(q) else None
        if k == "migrate":
            tc.assertEqual(where(H.V1), self.case.data, "the v1 bytes are kept")
            hist = os.path.join(root, H.HIST)
            tc.assertTrue(not os.path.exists(hist) or H.raw(root, H.HIST) == self.case.candidate_bytes,
                          "history.json is absent or the candidate")
        elif k == "adopt":
            hist = H.raw(root, H.HIST)
            tc.assertIn(hist, (self.case.data, self.case.candidate_bytes), "history.json is the original or the candidate")
            if hist == self.case.candidate_bytes:
                tc.assertEqual(H.qraw(root, key, H.HIST), self.case.data, "the original is kept before it is replaced")
        else:
            for n, (data, _ino) in self.before.items():
                tc.assertEqual(where(n), data, "the left bytes of %s are kept" % n)

    def finish(self, tc, root):
        """The person's steps: inspect, unlock what is left, then the same operation again (made again from the original
        bytes read back, never from the first call's values)."""
        k = self.kind
        for round_ in range(1, 5):
            m = self.maint(root)
            report = m.inspect()
            if report.artifacts:
                plan = M.plan_unlock(report, "fix-%d" % round_, True)
                m.unlock(plan, plan.plan_hash)
            try:
                if k == "migrate":
                    key = self.case.key
                    have = os.path.exists(os.path.join(root, "quarantine", key, H.V1))
                    data = m.read_set_aside(key, H.V1) if have else m.read_original(H.V1)
                    again = H.rebuild_migration(self.case, data)
                    tc.assertEqual(again.publication_hash, key)
                    return m.migrate(again, True)
                if k == "adopt":
                    key = self.case.key
                    raw = m.read_original(H.HIST)
                    data = raw if raw == self.case.data else m.read_set_aside(key, H.HIST)
                    again = H.rebuild_adoption(self.case, data)
                    tc.assertEqual(again.publication_hash, key)
                    return m.adopt(again)
                rest = m.inspect()
                if not rest.artifacts:
                    return None
                return m.unlock(self.plan, self.plan.plan_hash)
            except CoreError as e:
                tc.assertIn(e.code, ("store_busy", "maintenance_plan_stale"), e.code)       # then look again
        tc.fail("the procedure did not reach the final state")

    def check_final(self, tc, root):
        k = self.kind
        names = sorted(os.listdir(root))
        if k == "migrate":
            tc.assertEqual(names, ["history.json", "quarantine"])
            tc.assertEqual(H.raw(root, H.HIST), self.case.candidate_bytes)
            tc.assertEqual(H.qraw(root, self.case.key, H.V1), self.case.data)
        elif k == "adopt":
            tc.assertEqual(names, ["history.json", "quarantine"])
            tc.assertEqual(H.raw(root, H.HIST), self.case.candidate_bytes)
            tc.assertEqual(H.qraw(root, self.case.key, H.HIST), self.case.data)
        else:
            tc.assertEqual(names, ["quarantine"])
            seen = {}
            for key in H.keys(root):
                for n in H.qnames(root, key):
                    if n != "MANIFEST":
                        seen[n] = H.qraw(root, key, n)
            for n, (data, _ino) in self.before.items():
                tc.assertEqual(seen.get(n), data, n)


def no_leak(tc, e, root):
    """C4-19: the text, the attributes and the chained exceptions of an error carry no path and no injected secret, and
    no foreign exception type is chained."""
    bad = (H.SECRET, root, os.path.basename(root), "boom", "injected failure")
    seen, stack = set(), [e]
    while stack:
        x = stack.pop()
        if x is None or id(x) in seen:
            continue
        seen.add(id(x))
        tc.assertIsInstance(x, CoreError, type(x).__name__)
        blob = str(x) + repr(x) + repr(sorted((k, repr(v)) for k, v in x.__dict__.items()))
        for b in bad:
            tc.assertNotIn(b, blob)
        stack.extend((x.__cause__, x.__context__))


class Sweep(unittest.TestCase):
    """Every call of every operation, before and after, with three kinds of exception: only CoreErrors leave, the original
    bytes are always in the root or in the quarantine, history.json is the original or the candidate, no leak, and the
    person's procedure always reaches the final state."""

    counts = {}

    @classmethod
    def tearDownClass(cls):
        import sys
        for (kind, dur), (total, outcomes) in sorted(cls.counts.items()):
            sys.stderr.write("C4-16 sweep %-12s %-14s cases=%d outcomes=%s\n" % (kind, dur, total, sorted(outcomes.items())))
        sys.stderr.write("C4-16 sweep total cases=%d\n" % sum(t for t, _o in cls.counts.values()))

    def trace_of(self, sc):
        root = H.make_root()
        try:
            sc.setup(root)
            ops = H.C4Ops()
            sc.call(sc.maint(root, ops))
            return list(ops.trace)
        finally:
            shutil.rmtree(root, True)

    def sweep(self, kind, durability):
        probe = Scenario(kind, durability)
        trace = self.trace_of(probe)
        positions, seen = [], {}
        for op, k in trace:
            seen[(op, k)] = seen.get((op, k), 0) + 1
            positions.append((op, k, seen[(op, k)]))
        self.assertGreater(len(positions), 20)
        total = 0
        outcomes = {}
        for (op, k, nth) in positions:
            for after in (False, True):
                if after and op == "open_writer":
                    continue        # the handle that the real call made is lost by the fault itself: nothing to clean up
                for which in range(3):
                    sc = Scenario(kind, durability)
                    root = H.make_root()
                    try:
                        sc.setup(root)
                        ops = H.C4Ops()
                        exc = _exc(which)
                        ops.add(op, k, nth, before=None if after else exc, after=exc if after else None)
                        label = "%s/%s %s:%s#%d %s exc%d" % (kind, durability, op, k, nth, "after" if after else "before",
                                                              which)
                        try:
                            sc.call(sc.maint(root, ops))
                            outcomes["ok"] = outcomes.get("ok", 0) + 1
                        except Exception as e:                                       # noqa: BLE001 - classified below
                            self.assertIsInstance(e, CoreError, label + " leaked " + type(e).__name__)
                            no_leak(self, e, root)
                            outcomes[e.code] = outcomes.get(e.code, 0) + 1
                        sc.check_after_failure(self, root)
                        sc.finish(self, root)
                        sc.check_final(self, root)
                        total += 1
                    finally:
                        shutil.rmtree(root, True)
        Sweep.counts[(kind, durability)] = (total, outcomes)
        skipped = len([1 for (op, _k, _n) in positions if op == "open_writer"]) * 3
        self.assertEqual(total, len(positions) * 6 - skipped)

    def test_migrate_strict(self):
        self.sweep("migrate", "strict")

    def test_migrate_file_sync_only(self):
        self.sweep("migrate", "file_sync_only")

    def test_adopt_strict(self):
        self.sweep("adopt", "strict")

    def test_adopt_file_sync_only(self):
        self.sweep("adopt", "file_sync_only")

    def test_unlock_with_the_left_lock_strict(self):
        self.sweep("unlock_lock", "strict")

    def test_unlock_with_the_left_lock_file_sync_only(self):
        self.sweep("unlock_lock", "file_sync_only")

    def test_unlock_of_temporary_files_strict(self):
        self.sweep("unlock_tmp", "strict")

    def test_unlock_of_temporary_files_file_sync_only(self):
        self.sweep("unlock_tmp", "file_sync_only")


class Levels(H.RootCase):
    def test_strict_syncs_the_files_and_the_directories_of_design_5_6(self):
        case = H.migration()
        self.put_v1(case)
        ops = H.C4Ops()
        self.maint(ops).migrate(case.pub, True)
        syncs = [n for n in ops.ops("fsync_dir:root", "fsync_dir:qdir", "fsync_dir:kdir", "fsync_file:qtmp",
                                    "fsync_file:tmp", "fsync_file:lock", "probe_dir_sync")]
        self.assertEqual(syncs, ["probe_dir_sync", "fsync_dir:root", "fsync_dir:qdir", "fsync_file:qtmp", "fsync_dir:kdir",
                                 "probe_dir_sync", "fsync_file:tmp", "fsync_dir:root", "fsync_dir:kdir", "fsync_dir:root"])

    def test_file_sync_only_never_syncs_a_directory(self):
        for make in ("migrate", "adopt"):
            root = H.make_root()
            self.addCleanup(shutil.rmtree, root, True)
            ops = H.C4Ops()
            m = M.HistoryMaintenance(root, writable=True, durability=M.FILE_SYNC_ONLY_MODE, _ops=ops)
            if make == "migrate":
                case = H.migration()
                H.put(root, H.V1, case.data)
                res = m.migrate(case.pub, True)
            else:
                case = H.adoption()
                H.put(root, H.HIST, case.data)
                res = m.adopt(case.pub)
            self.assertEqual(res.persistence_level, M.FILE_SYNC_ONLY)
            self.assertEqual(ops.ops("fsync_dir", "probe_dir_sync"), [])
            self.assertGreaterEqual(len(ops.ops("fsync_file")), 2)

    def test_windows_strict_is_refused_before_any_change_and_the_lock_is_released(self):
        for make in ("migrate", "adopt", "unlock_tmp", "unlock_lock"):
            root = H.make_root()
            self.addCleanup(shutil.rmtree, root, True)
            sc = Scenario(make, "strict")
            sc.setup(root)
            before = H.tree(root)
            ops = H.C4Ops()
            ops.windows = True
            e = self.run_err(sc.call, sc.maint(root, ops))
            self.assertErr(e, "store_durability_unsupported", "durability", "durability_probe", "windows_strict")
            self.assertEqual(H.tree(root), before)
            self.assertEqual(ops.ops("mkdir", "rename", "replace", "probe_dir_sync"), [])

    def test_a_failed_directory_sync_probe_is_refused_before_any_change(self):
        for make in ("migrate", "adopt", "unlock_tmp", "unlock_lock"):
            root = H.make_root()
            self.addCleanup(shutil.rmtree, root, True)
            sc = Scenario(make, "strict")
            sc.setup(root)
            before = H.tree(root)
            ops = H.C4Ops().fail("probe_dir_sync", "root")
            e = self.run_err(sc.call, sc.maint(root, ops))
            self.assertErr(e, "store_durability_unsupported", "durability", "durability_probe", "directory_sync")
            self.assertEqual(H.tree(root), before)
            self.assertEqual(ops.ops("mkdir", "rename", "replace"), [])

    def test_file_sync_only_works_where_strict_is_refused(self):
        case = H.adoption()
        self.put_history(case.data)
        ops = H.C4Ops()
        ops.windows = True
        res = self.maint(ops, durability=M.FILE_SYNC_ONLY_MODE).adopt(case.pub)
        self.assertEqual(res.status, M.ADOPTED)


class Leaks(H.RootCase):
    def test_a_message_with_the_path_in_it_never_reaches_an_error(self):
        case = H.adoption()
        for op, kind in (("lstat", "history"), ("read_file", "history"), ("listdir", "root"), ("mkdir", "qdir"),
                         ("replace", "manifest"), ("write", "qtmp"), ("rename", "snapshot"), ("fsync_dir", "kdir"),
                         ("unlink", "lock"), ("create_exclusive", "lock")):
            root = H.make_root()
            self.addCleanup(shutil.rmtree, root, True)
            H.put(root, H.HIST, case.data)
            e = injected = H.injected()
            injected.filename = root
            ops = H.C4Ops().fail(op, kind, exc=injected)
            try:
                M.HistoryMaintenance(root, writable=True, _ops=ops).adopt(case.pub)
            except CoreError as err:
                no_leak(self, err, root)
            del e

    def test_the_raise_is_outside_the_exception_handling(self):
        # the review rule C4-19: no OS exception is left as __context__ of an error of the package
        case = H.migration()
        root = H.make_root()
        self.addCleanup(shutil.rmtree, root, True)
        H.put(root, H.V1, case.data)
        ops = H.C4Ops().fail("replace", "manifest")
        e = self.run_err(M.HistoryMaintenance(root, writable=True, _ops=ops).migrate, case.pub, True)
        self.assertIsNone(e.__cause__)
        self.assertIsNone(e.__context__)
        self.assertFalse(e.__suppress_context__ and e.__context__ is not None)


if __name__ == "__main__":
    unittest.main()
