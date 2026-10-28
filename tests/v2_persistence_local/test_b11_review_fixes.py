"""Regression tests for the S2 receipt review (R-01, R-02). Real files; OS-dependent branches are injected on Linux
and labelled as such. The real-Windows case only runs on win32 (reported as not run elsewhere)."""
import os
import sys
import unittest

import l_helpers as H
from v2_persistence.local import LocalFileStore, LocalStoreError
from v2_persistence.local import errors as E

TMP_LEFT, LOCK_LEFT, FOREIGN = E.CLEANUP_TMP_LEFT, E.CLEANUP_LOCK_LEFT, E.CLEANUP_LOCK_FOREIGN


class Base(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc, advance=1, durability="file_sync_only")
        self.before = H.raw(self.root)
        d = self.sc.day(2)
        self.sc.observe(d, 47)
        self.plan = self.sc.prepare(LocalFileStore(self.root).read(), d).plan

    def tmps(self):
        return [n for n in H.listing(self.root) if n.endswith(".tmp")]

    def commit_error(self, ops, durability="file_sync_only"):
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True, durability=durability, _ops=ops).commit(self.plan)
        e = cm.exception
        self.assertEqual(len(e.cleanup), len(set(e.cleanup)), e.cleanup)       # never duplicated
        return e


class R01CombinedCleanup(Base):
    def test_tmp_and_lock_removal_both_fail_before_publication(self):
        ops = H.FaultOps().fail("write", "tmp").fail("unlink", "tmp").fail("unlink", "lock")
        e = self.commit_error(ops)
        self.assertCode(e, "store_io_error", "lock", "lock_release")
        self.assertEqual((e.primary, e.cleanup), ("store_io_error", (TMP_LEFT, LOCK_LEFT)))
        self.assertIn(H.LOCK, H.listing(self.root))
        self.assertEqual(len(self.tmps()), 1)                               # what the error says is what is there
        self.assertEqual(H.raw(self.root), self.before)
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root).read()
        self.assertCode(cm.exception, "store_busy", "lock")
        self.no_leak(e)

    def no_leak(self, e):
        for needle in (H.SECRET, "injected failure", self.root):
            self.assertNotIn(needle, str(e) + repr(e.args))
        self.assertIsNone(e.__cause__)

    def test_tmp_removal_fails_and_the_lock_is_no_longer_ours_at_release(self):
        foreign = b"other owner\n"

        def swap_then_fail():
            H.put(self.root, H.LOCK, foreign)
            raise H.injected()
        ops = H.FaultOps().fail("write", "tmp").add("unlink", "tmp", before=swap_then_fail)
        e = self.commit_error(ops)
        self.assertCode(e, "store_lock_ownership_lost", "lock", "lock_ownership")
        self.assertEqual((e.primary, e.cleanup), ("store_io_error", (TMP_LEFT, FOREIGN)))
        self.assertEqual(H.raw(self.root, H.LOCK), foreign)                  # the other party's lock is untouched
        self.assertEqual(len(self.tmps()), 1)
        self.assertEqual(H.raw(self.root), self.before)

    def test_ownership_already_lost_before_replace_keeps_both_items(self):
        ops = H.FaultOps().add("close", "tmp", after=lambda: H.put(self.root, H.LOCK, b"x\n")).fail("unlink", "tmp")
        e = self.commit_error(ops)
        self.assertCode(e, "store_lock_ownership_lost", "lock", "lock_ownership")
        self.assertEqual(e.cleanup, (TMP_LEFT, FOREIGN))
        self.assertEqual(H.raw(self.root, H.LOCK), b"x\n")

    def test_uncertain_replace_with_both_removals_failing(self):
        ops = H.FaultOps().fail("replace").fail("unlink", "tmp").fail("unlink", "lock")
        e = self.commit_error(ops)
        self.assertCode(e, "store_commit_uncertain", "snapshot", "replace")
        self.assertEqual(e.cleanup, (TMP_LEFT, LOCK_LEFT))
        self.assertEqual(H.raw(self.root), self.before)

    def test_uncertain_precedes_after_publication_even_with_lock_loss(self):
        foreign = b"someone\n"

        def swap_then_fail():                  # the replace was executed, then the lock changed hands and it raised
            H.put(self.root, H.LOCK, foreign)
            raise H.injected()
        ops = H.FaultOps().add("replace", after=swap_then_fail)
        e = self.commit_error(ops)
        self.assertCode(e, "store_commit_uncertain", "snapshot", "replace")   # published: uncertain wins
        self.assertEqual(e.cleanup, (FOREIGN,))
        self.assertEqual(H.raw(self.root, H.LOCK), foreign)

    def test_directory_sync_failure_then_lock_release_failure(self):
        ops = H.FaultOps().fail("fsync_dir").fail("unlink", "lock")
        e = self.commit_error(ops, durability="strict")
        self.assertCode(e, "store_commit_uncertain", "snapshot", "dir_sync")
        self.assertEqual(e.cleanup, (LOCK_LEFT,))

    def test_initialize_path_keeps_both_items_too(self):
        os.unlink(os.path.join(self.root, H.SNAP))
        ops = H.FaultOps().fail("write", "tmp").fail("unlink", "tmp").fail("unlink", "lock")
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True, durability="file_sync_only", _ops=ops).initialize(self.sc.genesis)
        self.assertEqual(cm.exception.cleanup, (TMP_LEFT, LOCK_LEFT))
        self.assertNotIn(H.SNAP, H.listing(self.root))

    def test_non_local_primary_error_still_reports_the_lock(self):
        other = self.sc.plan_for(LocalFileStore(self.root).read(), self.sc.day(2), 90, "R-o", self.sc.ledger[:-1])
        LocalFileStore(self.root, writable=True, durability="file_sync_only").commit(other)
        e = self.commit_error(H.FaultOps().fail("unlink", "lock"))           # stale plan -> cas_conflict first
        self.assertCode(e, "store_io_error", "lock", "lock_release")
        self.assertEqual((e.primary, e.cleanup), ("cas_conflict", (LOCK_LEFT,)))


class R02ExistingLockClassification(Base):
    """Linux INJECTION of the Windows behaviour (create_exclusive raising PermissionError although something is
    there). Not a Windows run; the real-Windows case is RealWindowsLockDirectory below."""

    def perm(self):
        return PermissionError(13, "Access is denied for " + H.SECRET, H.SECRET)

    def ops(self):
        return H.FaultOps().fail("create_exclusive", "lock", exc=self.perm())

    def attempts(self, ops):
        sc = self.sc
        plan = self.plan
        for name, call in (("read", lambda: LocalFileStore(self.root, _ops=ops).read()),
                           ("commit", lambda: LocalFileStore(self.root, writable=True, _ops=ops).commit(plan)),
                           ("initialize", lambda: LocalFileStore(self.root, writable=True, _ops=ops).initialize(sc.genesis))):
            ops.rules[0].seen = 0                                           # fire again for every call
            with self.assertRaises(LocalStoreError) as cm:
                call()
            yield name, cm.exception

    def test_existing_directory_regular_file_and_links_are_busy_and_untouched(self):
        lock = os.path.join(self.root, H.LOCK)
        outside = H.make_root()
        self.addCleanup(__import__("shutil").rmtree, outside, True)
        H.put(outside, "victim.txt", b"keep")
        for kind in ("dir", "file", "symlink", "dangling"):
            with self.subTest(kind):
                if os.path.lexists(lock):
                    (os.rmdir if os.path.isdir(lock) and not os.path.islink(lock) else os.unlink)(lock)
                if kind == "dir":
                    os.mkdir(lock)
                elif kind == "file":
                    H.put(self.root, H.LOCK, b"another process\n")
                elif kind == "symlink":
                    os.symlink(os.path.join(outside, "victim.txt"), lock)
                else:
                    os.symlink(os.path.join(outside, "missing"), lock)
                for name, e in self.attempts(self.ops()):
                    self.assertCode(e, "store_busy", "lock", "lock_acquire")
                    self.assertEqual(e.cleanup, ())
                    self.assertNotIn(H.SECRET, str(e) + repr(e.args))
                    self.assertIsNone(e.__cause__)
                self.assertTrue(os.path.lexists(lock))
                self.assertEqual(os.path.isdir(lock) and not os.path.islink(lock), kind == "dir")
                self.assertEqual(os.path.islink(lock), kind in ("symlink", "dangling"))
                if kind == "file":
                    self.assertEqual(H.raw(self.root, H.LOCK), b"another process\n")
                self.assertEqual(H.raw(outside, "victim.txt"), b"keep")
                self.assertEqual(os.listdir(outside), ["victim.txt"])
                self.assertEqual(H.raw(self.root), self.before)

    def test_a_real_permission_error_without_any_lock_stays_an_io_error(self):
        ops = self.ops()
        for name, e in self.attempts(ops):
            self.assertCode(e, "store_io_error", "lock", "lock_acquire")
            self.assertNotIn(H.SECRET, str(e) + repr(e.args))
            self.assertIsNone(e.__cause__)
        self.assertEqual(H.listing(self.root), [H.SNAP])                    # nothing was created or removed

    def test_if_existence_cannot_be_established_it_stays_an_io_error(self):
        lock = os.path.join(self.root, H.LOCK)
        os.mkdir(lock)
        ops = self.ops().fail("lstat", "lock", exc=OSError(5, "boom", H.SECRET))
        for name, e in self.attempts(ops):
            self.assertCode(e, "store_io_error", "lock", "lock_acquire")
            ops.rules[1].seen = 0
        self.assertTrue(os.path.isdir(lock))

    def test_native_linux_directory_is_still_busy(self):
        os.mkdir(os.path.join(self.root, H.LOCK))
        for name, call in (("read", lambda: LocalFileStore(self.root).read()),):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_busy", "lock", "lock_acquire")
        self.assertTrue(os.path.isdir(os.path.join(self.root, H.LOCK)))


@unittest.skipUnless(sys.platform == "win32", "needs real Windows; reported as NOT RUN elsewhere")
class RealWindowsLockDirectory(Base):
    def test_existing_lock_directory_is_store_busy_and_unchanged(self):
        lock = os.path.join(self.root, H.LOCK)
        os.mkdir(lock)
        for call in (lambda: LocalFileStore(self.root).read(),
                     lambda: LocalFileStore(self.root, writable=True, durability="file_sync_only").commit(self.plan)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_busy", "lock", "lock_acquire")
        self.assertTrue(os.path.isdir(lock))
        self.assertEqual(H.raw(self.root), self.before)


if __name__ == "__main__":
    unittest.main()
