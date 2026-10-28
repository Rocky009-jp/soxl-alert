"""B-09: synchronisation modes and OS dependence.

Three kinds of evidence, kept apart in the result document:
  * real Linux (POSIX) runs: strict and file_sync_only against real files and a real directory fsync;
  * a SIMULATION of the Windows branch on Linux (FileOps.is_windows forced to True) - it checks the branch logic,
    it is not a Windows run;
  * real Windows runs (class RealWindows): they only execute where sys.platform == "win32" and are reported as
    not run anywhere else.
"""
import errno
import os
import sys
import unittest

import l_helpers as H
from v2_persistence.local import (FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, LocalFileStore, LocalStoreError)

POSIX = os.name == "posix"


class Base(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()

    def fresh_plan(self, store, advance=0):
        if advance:
            self.sc.advance(store, advance)
        snap = store.read()
        d = self.sc.next_day(snap)
        self.sc.observe(d, 58)
        return self.sc.prepare(snap, d).plan


@unittest.skipUnless(POSIX, "real POSIX run")
class RealPosix(Base):
    def test_strict_is_the_default_and_syncs_the_directory(self):
        ops = H.FaultOps()
        st = LocalFileStore(self.root, writable=True, _ops=ops)
        self.assertEqual(st.durability, "strict")
        res = st.initialize(self.sc.genesis)
        self.assertEqual(res.persistence_level, FILE_AND_DIRECTORY_SYNC)
        self.assertEqual(ops.ops("probe_dir_sync", "fsync_dir"), ["probe_dir_sync", "fsync_dir"])
        plan = self.fresh_plan(st)
        res = st.commit(plan)
        self.assertEqual(res.persistence_level, FILE_AND_DIRECTORY_SYNC)
        self.assertEqual(ops.ops("fsync_dir").count("fsync_dir"), 2)

    def test_file_sync_only_is_explicit_and_labelled(self):
        ops = H.FaultOps()
        st = LocalFileStore(self.root, writable=True, durability="file_sync_only", _ops=ops)
        r1 = st.initialize(self.sc.genesis)
        plan = self.fresh_plan(st)
        r2 = st.commit(plan)
        self.assertEqual((r1.persistence_level, r2.persistence_level), (FILE_SYNC_ONLY, FILE_SYNC_ONLY))
        self.assertEqual(ops.ops("probe_dir_sync", "fsync_dir"), [])          # no directory sync is claimed or done
        self.assertEqual(ops.ops("fsync_file:tmp").count("fsync_file:tmp"), 2)
        self.assertEqual(ops.ops("replace").count("replace"), 2)
        self.assertEqual(LocalFileStore(self.root).read().head_seq, 1)         # strict reader reads the same file

    def test_levels_are_distinct_values(self):
        self.assertNotEqual(FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY)

    def test_independent_processes_report_the_level(self):
        st = self.store()
        st.initialize(self.sc.genesis)
        plan = self.fresh_plan(st)
        r = H.run_worker({"mode": "commit", "root": self.root, "plan": H.plan_to_json(plan),
                          "durability": "file_sync_only"})
        self.assertEqual((r["ok"], r["status"], r["persistence_level"]), (True, "COMMITTED", FILE_SYNC_ONLY))


class SimulatedWindowsBranch(Base):
    """Linux-only SIMULATION of the Windows branch (is_windows() -> True). Not a Windows run."""

    def ops(self):
        ops = H.FaultOps()
        ops.windows = True
        return ops

    def test_strict_commit_is_refused_before_publication(self):
        H.init_root(self.root, self.sc)
        base_state = H.state_of(self.root)
        plan = self.fresh_plan(LocalFileStore(self.root))
        ops = self.ops()
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True, _ops=ops).commit(plan)
        e = cm.exception
        self.assertCode(e, "store_durability_unsupported", "durability", "durability_probe")
        self.assertEqual(e.rule, "windows_strict")
        self.assertNotIn(("create_exclusive", "tmp"), ops.trace)
        self.assertNotIn("replace", [o for o, _ in ops.trace])
        self.assertEqual(H.state_of(self.root), base_state)

    def test_strict_initialize_on_empty_root_is_refused_and_nothing_is_created(self):
        ops = self.ops()
        st = LocalFileStore(self.root, writable=True, _ops=ops)
        with self.assertRaises(LocalStoreError) as cm:
            st.initialize(self.sc.genesis)
        self.assertCode(cm.exception, "store_durability_unsupported", "durability")
        self.assertEqual(H.listing(self.root), [])
        self.assertNotIn(("create_exclusive", "tmp"), ops.trace)

    def test_no_silent_downgrade(self):
        st = LocalFileStore(self.root, writable=True, _ops=self.ops())
        with self.assertRaises(LocalStoreError):
            st.initialize(self.sc.genesis)
        self.assertEqual(st.durability, "strict")                       # still strict: never rewritten to file_sync_only
        self.assertEqual(H.listing(self.root), [])

    def test_read_is_not_refused_for_directory_sync(self):
        H.init_root(self.root, self.sc, advance=1)
        snap = LocalFileStore(self.root, _ops=self.ops()).read()          # default strict, read-only instance
        self.assertEqual(snap.head_seq, 1)
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_file_sync_only_runs_the_whole_path(self):
        ops = self.ops()
        st = LocalFileStore(self.root, writable=True, durability="file_sync_only", _ops=ops)
        st.initialize(self.sc.genesis)
        res = st.commit(self.fresh_plan(st))
        self.assertEqual(res.persistence_level, FILE_SYNC_ONLY)
        self.assertEqual(ops.ops("probe_dir_sync", "fsync_dir"), [])

    def test_directory_sync_not_possible_on_posix_is_refused_before_publication(self):
        H.init_root(self.root, self.sc)
        plan = self.fresh_plan(LocalFileStore(self.root))
        before = H.state_of(self.root)
        for err in (errno.EINVAL, errno.EBADF, errno.EACCES, errno.ENOTSUP):
            ops = H.FaultOps().fail("probe_dir_sync", exc=OSError(err, "x", H.SECRET))
            with self.assertRaises(LocalStoreError) as cm:
                LocalFileStore(self.root, writable=True, _ops=ops).commit(plan)
            self.assertEqual(cm.exception.rule, "directory_sync")
            self.assertCode(cm.exception, "store_durability_unsupported", "durability")
            self.assertNotIn(("create_exclusive", "tmp"), ops.trace)
        self.assertEqual(H.state_of(self.root), before)

    def test_sync_failure_after_a_successful_probe_is_not_turned_into_success(self):
        H.init_root(self.root, self.sc)
        plan = self.fresh_plan(LocalFileStore(self.root))
        ops = H.FaultOps().fail("fsync_dir")                            # probe passes, the real directory sync fails
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True, _ops=ops).commit(plan)
        self.assertCode(cm.exception, "store_commit_uncertain", "snapshot", "dir_sync")


@unittest.skipUnless(sys.platform == "win32", "needs real Windows; reported as NOT RUN elsewhere")
class RealWindows(Base):
    """Only executes on a real Windows host. On Linux this whole class is skipped = not run, never counted as passed."""

    def test_file_sync_only_roundtrip_and_replace_over_existing(self):
        st = LocalFileStore(self.root, writable=True, durability="file_sync_only")
        st.initialize(self.sc.genesis)
        for _ in range(3):
            res = st.commit(self.fresh_plan(st))
            self.assertEqual(res.persistence_level, FILE_SYNC_ONLY)
        self.assertEqual(LocalFileStore(self.root).read().head_seq, 3)
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_strict_is_refused_before_publication(self):
        st = LocalFileStore(self.root, writable=True)
        with self.assertRaises(LocalStoreError) as cm:
            st.initialize(self.sc.genesis)
        self.assertCode(cm.exception, "store_durability_unsupported", "durability")
        self.assertEqual(H.listing(self.root), [])

    def test_process_contention_one_winner(self):
        st = LocalFileStore(self.root, writable=True, durability="file_sync_only")
        st.initialize(self.sc.genesis)
        start = st.read()
        d = self.sc.day(1)
        pa = self.sc.plan_for(start, d, 20, "R-a")
        pb = self.sc.plan_for(start, d, 80, "R-b")
        spec = lambda p: {"mode": "commit", "root": self.root, "plan": H.plan_to_json(p), "wait_go": True,
                          "durability": "file_sync_only"}
        wa = H.Worker(spec(pa))
        self.addCleanup(wa.kill)
        wa.expect("READY")
        wb = H.Worker(spec(pb))
        self.addCleanup(wb.kill)
        wb.expect("READY")
        wa.send("GO")
        wb.send("GO")
        res = [wa.result(), wb.result()]
        self.assertEqual(sum(1 for r in res if r["ok"]), 1, res)
        self.assertIn([r for r in res if not r["ok"]][0]["code"], ("store_busy", "cas_conflict"))
        self.assertEqual(LocalFileStore(self.root).read().head_seq, 1)


if __name__ == "__main__":
    unittest.main()
