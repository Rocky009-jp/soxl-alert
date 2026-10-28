"""B-05 publication order and ordinary failures, B-07 unknown outcome. Real files; I/O faults are injected in the
FileOps layer of a dedicated root (no disk is filled, no permission is changed, no power is cut)."""
import errno
import os
import traceback
import unittest

import l_helpers as H
from v2_persistence.codec import encode_snapshot
from v2_persistence.local import LocalFileStore, LocalStoreError
from v2_persistence.local import errors as E
from v2_persistence.plan import ALREADY_APPLIED, REPLAN_REQUIRED
from v2_persistence.store import reconcile

STRICT_ORDER = ["write:tmp", "flush:tmp", "fsync_file:tmp", "close:tmp", "replace", "fsync_dir", "unlink:lock"]
KEY = ("write:tmp", "flush:tmp", "fsync_file:tmp", "close:tmp", "replace", "fsync_dir", "unlink:lock",
       "probe_dir_sync", "create_exclusive:lock", "create_exclusive:tmp")


class Base(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc, advance=2)
        self.old_bytes = H.raw(self.root)
        self.old_snap = LocalFileStore(self.root).read()
        self.old_deep = self.old_snap.to_dict()
        self.d = self.sc.day(3)
        self.base_ledger = list(self.sc.ledger)                             # without any observation for self.d
        self.sc.observe(self.d, 47)
        self.plan = self.sc.prepare(self.old_snap, self.d).plan

    def store_with(self, ops, **kw):
        kw.setdefault("writable", True)
        return LocalFileStore(self.root, _ops=ops, **kw)

    def assert_untouched(self, listing_=None):
        """Old snapshot: raw bytes, head and deep value unchanged; only snapshot.json left (or the given names)."""
        self.assertEqual(H.raw(self.root), self.old_bytes)
        snap = LocalFileStore(self.root).read() if listing_ is None else None
        if snap is not None:
            self.assertEqual((snap.head_seq, snap.head_hash), (self.old_snap.head_seq, self.old_snap.head_hash))
            self.assertEqual(snap.to_dict(), self.old_deep)
        self.assertEqual(H.listing(self.root), [H.SNAP] if listing_ is None else listing_)

    def no_leak(self, exc):
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for needle in (H.SECRET, "injected failure", self.root):
            self.assertNotIn(needle, text)
            self.assertNotIn(needle, repr(exc.args))
        self.assertIsNone(exc.__cause__)
        self.assertIsNone(exc.__context__)


class B05Procedure(Base):
    def test_order_strict_commit(self):
        ops = H.FaultOps()
        res = self.store_with(ops).commit(self.plan)
        self.assertEqual(ops.ops(*KEY[:7]), STRICT_ORDER)
        names = ops.ops(*KEY)
        self.assertEqual(names[0], "create_exclusive:lock")                  # the lock comes first of all
        self.assertLess(names.index("probe_dir_sync"), names.index("create_exclusive:tmp"))
        self.assertLess(names.index("create_exclusive:tmp"), names.index("write:tmp"))
        self.assertEqual(names.count("replace"), 1)
        self.assertEqual(names.count("fsync_dir"), 1)
        self.assertEqual(res.persistence_level, "FILE_AND_DIRECTORY_SYNC")
        self.assertEqual(H.raw(self.root), encode_snapshot(res.snapshot).encode("utf-8"))
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_order_strict_initialize(self):
        os.unlink(os.path.join(self.root, H.SNAP))
        ops = H.FaultOps()
        self.store_with(ops).initialize(self.sc.genesis)
        self.assertEqual(ops.ops(*KEY[:7]), STRICT_ORDER)
        self.assertEqual(ops.ops(*KEY)[0], "create_exclusive:lock")

    def test_replace_happens_after_ownership_recheck_and_never_after_a_direct_truncate(self):
        ops = H.FaultOps()
        self.store_with(ops).commit(self.plan)
        i = ops.trace.index(("replace", "snapshot"))
        self.assertIn(("read_file", "lock"), ops.trace[:i])               # lock re-read right before the replace
        self.assertNotIn(("unlink", "snapshot"), ops.trace)                # the old file is never removed first
        self.assertNotIn(("create_exclusive", "snapshot"), ops.trace)      # and never rewritten in place

    def test_short_writes_are_completed(self):
        ops = H.FaultOps()
        ops.max_write = 7
        res = self.store_with(ops).commit(self.plan)
        writes = [t for t in ops.trace if t == ("write", "tmp")]
        self.assertGreater(len(writes), 10)
        self.assertEqual(H.raw(self.root), encode_snapshot(res.snapshot).encode("utf-8"))
        self.assertEqual(LocalFileStore(self.root).read().head_seq, 3)

    def test_zero_length_write_is_an_error_not_a_hang(self):
        ops = H.FaultOps()
        ops.add("write", "tmp", wrap=lambda real, w, data: 0)
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_io_error", "snapshot", "write")
        self.assertEqual(cm.exception.cleanup, ())
        self.assert_untouched()

    def test_failures_before_publication_leave_the_old_snapshot(self):
        for op, kind, phase in (("create_exclusive", "tmp", "tmp_create"), ("write", "tmp", "write"),
                                ("flush", "tmp", "flush"), ("fsync_file", "tmp", "file_sync"),
                                ("close", "tmp", "close")):
            with self.subTest(op=op):
                ops = H.FaultOps().fail(op, kind)
                with self.assertRaises(LocalStoreError) as cm:
                    self.store_with(ops).commit(self.plan)
                e = cm.exception
                self.assertCode(e, "store_io_error", "snapshot", phase)
                self.assertEqual(e.cleanup, ())                            # own tmp and the lock are gone
                self.assertNotIn("replace", [o for o, _ in ops.trace])
                self.no_leak(e)
                self.assert_untouched()

    def test_failure_after_the_real_close_or_write_still_cleans_own_tmp(self):
        for op, kind in (("write", "tmp"), ("fsync_file", "tmp"), ("close", "tmp")):
            with self.subTest(op=op):
                ops = H.FaultOps().fail(op, kind, after=True)               # the real call happened, then it raised
                with self.assertRaises(LocalStoreError) as cm:
                    self.store_with(ops).commit(self.plan)
                self.assertEqual(cm.exception.code, "store_io_error")
                self.assertEqual(cm.exception.cleanup, ())
                self.assert_untouched()

    def test_no_sync_support_before_publication_probe_failure(self):
        ops = H.FaultOps().fail("probe_dir_sync", exc=OSError(errno.EINVAL, "x"))
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_durability_unsupported", "durability")
        self.assertNotIn(("create_exclusive", "tmp"), ops.trace)
        self.assert_untouched()

    def test_cleanup_failure_of_tmp_is_reported_and_next_call_stops(self):
        ops = H.FaultOps().fail("write", "tmp").fail("unlink", "tmp")
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        e = cm.exception
        self.assertCode(e, "store_io_error", "snapshot", "write")
        self.assertEqual(e.cleanup, (E.CLEANUP_TMP_LEFT,))
        leftovers = [n for n in H.listing(self.root) if n.endswith(".tmp")]
        self.assertEqual(len(leftovers), 1)
        self.assertEqual(H.raw(self.root), self.old_bytes)
        self.assertNotIn(H.LOCK, H.listing(self.root))                     # the lock itself was released
        for call in (lambda: LocalFileStore(self.root).read(), lambda: self.store().commit(self.plan)):
            with self.assertRaises(LocalStoreError) as cm2:
                call()
            self.assertCode(cm2.exception, "store_artifact_present", "store")
        self.assertEqual(len([n for n in H.listing(self.root) if n.endswith(".tmp")]), 1)   # not adopted, not removed

    def test_directory_listing_failure_is_an_error_not_an_empty_directory(self):
        ops = H.FaultOps().fail("listdir")
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_io_error", "root", "scan")
        self.no_leak(cm.exception)
        self.assert_untouched()

    def test_lock_creation_failures(self):
        # (a) creation itself fails: nothing exists
        ops = H.FaultOps().fail("create_exclusive", "lock", exc=OSError(errno.EACCES, "x", H.SECRET))
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_io_error", "lock", "lock_acquire")
        self.no_leak(cm.exception)
        self.assert_untouched()
        # (b) fails midway (marker write): the half-made lock is removed because it is ours
        ops = H.FaultOps().fail("write", "lock")
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_io_error", "lock", "lock_acquire")
        self.assertEqual(cm.exception.cleanup, ())
        self.assert_untouched()
        # (c) fails midway and its removal fails too: reported, left in place, next call stops
        ops = H.FaultOps().fail("write", "lock").fail("unlink", "lock")
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertEqual(cm.exception.cleanup, (E.CLEANUP_LOCK_LEFT,))
        self.assertIn(H.LOCK, H.listing(self.root))
        with self.assertRaises(LocalStoreError) as cm2:
            LocalFileStore(self.root).read()
        self.assertCode(cm2.exception, "store_busy", "lock")
        self.assertEqual(H.raw(self.root), self.old_bytes)

    def test_lock_release_failure_after_a_failed_operation_is_not_hidden(self):
        ops = H.FaultOps().fail("unlink", "lock")
        stale = self.sc.plan_for(self.old_snap, self.d, 90, "R-other", self.base_ledger)
        self.store().commit(stale)                                       # head moves; self.plan is now stale
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        e = cm.exception
        self.assertCode(e, "store_io_error", "lock", "lock_release")
        self.assertEqual((e.primary, e.cleanup), ("cas_conflict", (E.CLEANUP_LOCK_LEFT,)))
        self.assertIn(H.LOCK, H.listing(self.root))

    def test_lock_ownership_change_before_replace(self):
        foreign = b"someone else's lock\n"
        lock_path = os.path.join(self.root, H.LOCK)

        def swap_file():                       # a different file takes the lock's place
            os.unlink(lock_path)
            H.put(self.root, H.LOCK, foreign)

        def overwrite_in_place():              # same inode, other content
            H.put(self.root, H.LOCK, foreign)

        def same_bytes_new_file():             # identical content, but a different file (inode)
            same = H.raw(self.root, H.LOCK)
            H.put(self.root, "lock.new", same)                  # created while the old inode still exists
            os.replace(os.path.join(self.root, "lock.new"), lock_path)

        for name, action in (("replaced file", swap_file), ("overwritten", overwrite_in_place),
                             ("same bytes, new inode", same_bytes_new_file)):
            with self.subTest(name):
                ops = H.FaultOps().add("close", "tmp", after=action)         # after the tmp is complete, before replace
                with self.assertRaises(LocalStoreError) as cm:
                    self.store_with(ops).commit(self.plan)
                e = cm.exception
                self.assertCode(e, "store_lock_ownership_lost", "lock", "lock_ownership")
                if name.startswith("same"):
                    self.assertTrue(H.raw(self.root, H.LOCK).startswith(b"v2_persistence.local.lock\n"))
                else:
                    self.assertEqual(H.raw(self.root, H.LOCK), foreign)         # the other party's lock is untouched
                self.assertEqual(H.raw(self.root), self.old_bytes)              # nothing published
                self.assertEqual(H.listing(self.root), [H.SNAP, H.LOCK])        # our tmp was removed
                self.assertEqual(e.cleanup, (E.CLEANUP_LOCK_FOREIGN,))
                os.unlink(lock_path)                                            # test-side clean-up of the foreign lock

    def test_ownership_lost_right_after_acquisition(self):
        foreign = b"x\n"
        ops = H.FaultOps().add("listdir", before=lambda: H.put(self.root, H.LOCK, foreign))
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops).commit(self.plan)
        self.assertCode(cm.exception, "store_lock_ownership_lost", "lock", "lock_ownership")
        self.assertEqual(H.raw(self.root, H.LOCK), foreign)
        self.assertEqual(H.raw(self.root), self.old_bytes)
        os.unlink(os.path.join(self.root, H.LOCK))

    def test_failures_leave_other_files_alone(self):
        H.put(self.root, "notes.txt", b"mine")
        ops = H.FaultOps().fail("fsync_file", "tmp")
        with self.assertRaises(LocalStoreError):
            self.store_with(ops).commit(self.plan)
        self.assertEqual(H.raw(self.root, "notes.txt"), b"mine")
        self.assertEqual(H.listing(self.root), ["notes.txt", H.SNAP])


class B07Uncertain(Base):
    def uncertain(self, ops, **kw):
        with self.assertRaises(LocalStoreError) as cm:
            self.store_with(ops, **kw).commit(self.plan)
        e = cm.exception
        self.assertEqual(e.code, "store_commit_uncertain")
        self.assertEqual(e.field, "snapshot")
        self.no_leak(e)
        return e

    def test_replace_done_then_exception(self):
        ops = H.FaultOps().fail("replace", exc=OSError(errno.EIO, "x", H.SECRET), after=True)
        e = self.uncertain(ops)
        self.assertEqual((e.phase, e.cleanup), ("replace", ()))
        self.assertEqual(H.listing(self.root), [H.SNAP])                     # lock released, no tmp
        snap = LocalFileStore(self.root).read()
        self.assertEqual(snap.head_seq, self.old_snap.head_seq + 1)          # the new version is there ...
        self.assertEqual(reconcile(self.plan, snap).status, ALREADY_APPLIED)  # ... and only that is established

    def test_replace_raises_without_effect(self):
        ops = H.FaultOps().fail("replace")
        e = self.uncertain(ops)
        self.assertEqual((e.phase, e.cleanup), ("replace", ()))              # the call had started: still uncertain
        self.assert_untouched()
        self.assertEqual(reconcile(self.plan, LocalFileStore(self.root).read()).status, REPLAN_REQUIRED)
        self.assertEqual([t for t in ops.trace if t == ("replace", "snapshot")], [("replace", "snapshot")])   # no retry

    def test_replace_fails_and_lock_release_fails_too(self):
        ops = H.FaultOps().fail("replace").fail("unlink", "lock")
        e = self.uncertain(ops)
        self.assertEqual(e.phase, "replace")
        self.assertEqual(e.cleanup, (E.CLEANUP_LOCK_LEFT,))                  # the leftover lock is recorded
        self.assertEqual(H.raw(self.root), self.old_bytes)
        os.unlink(os.path.join(self.root, H.LOCK))

    def test_replace_raises_without_effect_and_tmp_removal_fails(self):
        ops = H.FaultOps().fail("replace").fail("unlink", "tmp")
        e = self.uncertain(ops)
        self.assertEqual(e.cleanup, (E.CLEANUP_TMP_LEFT,))
        self.assertEqual(H.raw(self.root), self.old_bytes)

    def test_directory_fsync_failure_after_replace(self):
        ops = H.FaultOps().fail("fsync_dir")
        e = self.uncertain(ops)
        self.assertEqual((e.phase, e.cleanup), ("dir_sync", ()))
        snap = LocalFileStore(self.root).read()                              # readable, but not claimed as synced
        self.assertEqual(snap.head_seq, 3)
        self.assertEqual(H.listing(self.root), [H.SNAP])
        self.assertEqual(reconcile(self.plan, snap).status, ALREADY_APPLIED)

    def test_lock_release_failure_after_replace(self):
        ops = H.FaultOps().fail("unlink", "lock")
        e = self.uncertain(ops)
        self.assertEqual((e.phase, e.cleanup), ("lock_release", (E.CLEANUP_LOCK_LEFT,)))
        self.assertIn(H.LOCK, H.listing(self.root))
        with self.assertRaises(LocalStoreError) as cm:                        # a leftover lock also stops read
            LocalFileStore(self.root).read()
        self.assertCode(cm.exception, "store_busy", "lock")
        os.unlink(os.path.join(self.root, H.LOCK))                            # explicit test-side unlock
        self.assertEqual(reconcile(self.plan, LocalFileStore(self.root).read()).status, ALREADY_APPLIED)

    def test_ownership_lost_after_replace(self):
        foreign = b"other\n"
        ops = H.FaultOps().add("fsync_dir", after=lambda: H.put(self.root, H.LOCK, foreign))
        e = self.uncertain(ops)
        self.assertEqual(e.phase, "lock_ownership")
        self.assertEqual(H.raw(self.root, H.LOCK), foreign)
        self.assertEqual(e.cleanup, (E.CLEANUP_LOCK_FOREIGN,))
        os.unlink(os.path.join(self.root, H.LOCK))

    def test_file_sync_only_mode_replace_failure_is_also_uncertain(self):
        ops = H.FaultOps().fail("replace", after=True)
        e = self.uncertain(ops, durability="file_sync_only")
        self.assertEqual(e.phase, "replace")

    def test_head_that_moved_is_not_our_success(self):
        """The replace raised and a different record for the same D is stored: reconcile says conflict, not ours."""
        other = self.sc.plan_for(self.old_snap, self.d, 91, "R-theirs", self.base_ledger)
        theirs = encode_snapshot(self.store().commit(other).snapshot).encode("utf-8")
        os.unlink(os.path.join(self.root, H.SNAP))
        H.put(self.root, H.SNAP, self.old_bytes)                               # reset to the old head
        ops = H.FaultOps().add("replace", before=lambda: H.put(self.root, H.SNAP, theirs))   # simulated other writer

        def raise_after_swap():
            raise H.injected()
        ops.add("replace", before=raise_after_swap, nth=1)
        e = self.uncertain(ops)
        self.assertEqual(e.phase, "replace")
        snap = LocalFileStore(self.root).read()
        self.assertEqual(snap.head_seq, 3)
        from v2_persistence.errors import PersistenceError
        with self.assertRaises(PersistenceError) as cm:
            reconcile(self.plan, snap)
        self.assertEqual(cm.exception.code, "concurrent_conflict")


if __name__ == "__main__":
    unittest.main()
