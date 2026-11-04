"""C3-09: the lock. Same name as S2's (so the two stores exclude each other), its own marker, never expired, never
taken over, never removed when it is not ours."""
import os
import unittest

import c3_helpers as H
import l_helpers as L
from v2_persistence.local import LocalFileStore


class Busy(H.RootCase):
    def test_a_file_a_directory_or_a_broken_link_at_the_lock_name(self):
        c = H.C2.day_case()
        self.put_current(c)
        lock = os.path.join(self.root, H.LOCK)
        kinds = {"file": lambda: H.put(self.root, H.LOCK, b"x\n"), "directory": lambda: os.mkdir(lock),
                 "dangling link": lambda: os.symlink(os.path.join(self.root, "nowhere"), lock)}
        for name, make in kinds.items():
            with self.subTest(kind=name):
                try:
                    make()
                except (OSError, NotImplementedError, AttributeError):
                    self.skipTest("cannot make a %s here" % name)
                before = H.state_of(self.root)
                for op, arg in (("read", ()), ("publish", (c.pub,)), ("reconcile", (c.pub,))):
                    e = self.run_err(getattr(self.store(), op), *arg)
                    self.assertStore(e, "store_busy", "lock", "lock_acquire")
                self.assertEqual(H.state_of(self.root), before)
                if os.path.isdir(lock) and not os.path.islink(lock):
                    os.rmdir(lock)
                else:
                    os.unlink(lock)

    def test_a_lock_is_never_taken_over_however_old(self):
        c = H.C2.day_case()
        self.put_current(c)
        H.put(self.root, H.LOCK, b"a very old marker\n")
        os.utime(os.path.join(self.root, H.LOCK), (1, 1))
        e = self.run_err(self.store().publish, c.pub)
        self.assertEqual(e.code, "store_busy")
        self.assertEqual(H.raw(self.root, H.LOCK), b"a very old marker\n")
        self.assertEqual(H.raw(self.root), c.current)


class Marker(H.RootCase):
    def test_the_marker_is_the_history_stores_own_with_random_bytes(self):
        c = H.C2.day_case()
        self.put_current(c)
        seen = []
        for _ in range(2):
            ops = H.C3Ops().add("listdir", before=lambda: seen.append(H.raw(self.root, H.LOCK)))
            self.store(ops).read()
        self.assertEqual(len(seen), 2)
        for marker in seen:
            self.assertRegex(marker.decode("ascii"), r"\Av2_history_local\.lock\n[0-9a-f]{32}\n\Z")
            self.assertFalse(marker.startswith(b"v2_persistence.local.lock"))
        self.assertNotEqual(seen[0], seen[1])


class Ownership(H.RootCase):
    def foreign_lock(self):
        lock = os.path.join(self.root, H.LOCK)

        def swap():
            os.unlink(lock)
            H.put(self.root, H.LOCK, b"somebody else's marker\n")
        return swap

    def test_lost_before_the_replace_removes_the_tmp_and_leaves_the_others_lock(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().add("close", "tmp", after=self.foreign_lock())
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_lock_ownership_lost", "lock", "lock_ownership",
                         cleanup=("lock_not_ours_left_untouched",))
        self.assertEqual(ops.ops("replace"), [])
        self.assertEqual(H.raw(self.root), c.current)
        self.assertEqual(H.raw(self.root, H.LOCK), b"somebody else's marker\n")
        self.assertEqual(H.listing(self.root), ["history.json", "write.lock"])

    def test_lost_after_the_replace_is_an_uncertain_commit(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().add("replace", after=self.foreign_lock())
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_commit_uncertain", "history", "lock_ownership",
                         cleanup=("lock_not_ours_left_untouched",))
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))
        self.assertEqual(H.raw(self.root, H.LOCK), b"somebody else's marker\n")
        # the other's lock stops the reconciliation too; after it is removed by hand the answer is PUBLISHED
        self.assertEqual(self.run_err(self.store().reconcile, c.pub).code, "store_busy")
        os.unlink(os.path.join(self.root, H.LOCK))
        self.assertEqual(self.store().reconcile(c.pub).outcome, "PUBLISHED")

    def test_lost_during_a_read_is_reported_and_the_others_lock_stays(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().add("read_file", "history", after=self.foreign_lock())
        e = self.run_err(self.store(ops, writable=False).read)
        self.assertStore(e, "store_lock_ownership_lost", "lock", "lock_ownership",
                         cleanup=("lock_not_ours_left_untouched",))
        self.assertEqual(H.raw(self.root, H.LOCK), b"somebody else's marker\n")

    def test_a_lock_that_is_replaced_by_a_link_or_a_directory_is_not_ours(self):
        c = H.C2.day_case()
        self.put_current(c)
        lock = os.path.join(self.root, H.LOCK)

        def to_directory():
            os.unlink(lock)
            os.mkdir(lock)
        ops = H.C3Ops().add("close", "tmp", after=to_directory)
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertEqual(e.code, "store_lock_ownership_lost")
        self.assertTrue(os.path.isdir(lock))


class Release(H.RootCase):
    def test_a_failed_release_leaves_the_lock_and_says_so(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("unlink", "lock")
        e = self.run_err(self.store(ops, writable=False).read)
        self.assertStore(e, "store_io_error", "lock", "lock_release", cleanup=("lock_left",))
        self.assertIn(H.LOCK, H.listing(self.root))
        self.assertNotIn(H.SECRET, str(e) + repr(e.__dict__))

    def test_a_failed_release_after_the_replace_is_an_uncertain_commit_with_the_lock_left(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("unlink", "lock")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_commit_uncertain", "history", "lock_release", cleanup=("lock_left",))
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))
        self.assertEqual(self.run_err(self.store().read).code, "store_busy")

    def test_a_failed_replace_and_a_failed_release_stay_uncertain_and_name_both_leftovers(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("replace", "history").fail("unlink", "lock")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_commit_uncertain", "history", "replace", cleanup=("lock_left",))
        self.assertEqual(H.raw(self.root), c.current)
        self.assertEqual(H.listing(self.root), ["history.json", "write.lock"])

    def test_a_failed_tmp_write_and_a_failed_release_are_not_an_uncertain_commit(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("flush", "tmp").fail("unlink", "lock")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_io_error", "lock", "lock_release", cleanup=("lock_left",))
        self.assertEqual(e.primary, "store_io_error")

    def test_a_refusal_and_a_failed_release_keep_both_facts(self):
        c = H.C2.day_case()
        H.put(self.root, H.HIST, c.current[:-7])
        ops = H.C3Ops().fail("unlink", "lock")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_io_error", "lock", "lock_release", cleanup=("lock_left",))
        self.assertEqual(e.primary, "history_invalid")


class ExcludesS2(H.RootCase):
    """Both directions, with the real S2 LocalFileStore: the lock name is the same, so each stops the other."""

    def test_s2_is_stopped_while_the_history_store_holds_the_lock(self):
        c = H.C2.day_case()
        self.put_current(c)
        seen = []

        def during():
            try:
                LocalFileStore(self.root, writable=False).read()
            except Exception as e:
                seen.append((e.code, e.phase))
        self.store(H.C3Ops().add("listdir", before=during), writable=False).read()
        self.assertEqual(seen, [("store_busy", "lock_acquire")])
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_the_history_store_is_stopped_while_s2_holds_the_lock(self):
        c = H.C2.day_case()
        self.put_current(c)
        seen = []

        def during():
            try:
                self.store(writable=False).read()
            except Exception as e:
                seen.append((e.code, e.phase))
        s2_ops = L.FaultOps().add("listdir", before=during)
        e = self.run_err(LocalFileStore(self.root, writable=False, _ops=s2_ops).read)
        self.assertEqual(e.code, "store_uninitialized")      # S2 finds no snapshot.json in a history root
        self.assertEqual(seen, [("store_busy", "lock_acquire")])
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_an_s2_writer_does_not_see_a_history_root_as_initialized(self):
        c = H.C2.day_case()
        self.put_current(c)
        e = self.run_err(LocalFileStore(self.root, writable=True).read)
        self.assertEqual(e.code, "store_uninitialized")
        self.assertEqual(H.raw(self.root), c.current)


if __name__ == "__main__":
    unittest.main()
