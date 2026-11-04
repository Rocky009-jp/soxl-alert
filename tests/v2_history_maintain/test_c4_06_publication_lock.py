"""C4-14 how a publication is received, C4-15 the lock."""
import os
import unittest

import c4_helpers as H
import v2_history_maintain as M
import v2_history_publish as U


def spoil(b):
    b["candidate_history"]["events"][0]["state_after"]["streak"] = 77


class Receiving(H.RootCase):
    def both(self):
        return (("migrate", lambda m, p: m.migrate(p, True)), ("adopt", lambda m, p: m.adopt(p)))

    def test_values_that_are_not_publications(self):
        case = H.adoption()
        junk = [None, {}, case.pub.to_dict(), case.plan, case.candidate, "x", 3, [case.pub],
                H.C2.migration_case().data, U.Reconciliation._of("PUBLISHED", case.key)]
        for name, call in self.both():
            for v in junk:
                ops = H.C4Ops()
                e = self.run_err(call, self.maint(ops), v)
                self.assertErr(e, "store_publication_invalid", "publication", "args", "type")
                self.assertEqual(ops.ops("create_exclusive", "create_exclusive:lock"), [])
                self.assertEqual(H.listing(self.root), [])

    def test_a_subclass_is_not_the_class(self):
        case = H.adoption()

        class Sub(U.HistoryPublication):
            __slots__ = ()
        forged = Sub._wrap(case.pub.to_dict(), lambda rule: Exception(rule))
        e = self.run_err(self.maint().adopt, forged)
        self.assertErr(e, "store_publication_invalid", "publication", "args", "type")

    def test_hand_made_values_without_mode_or_source_or_with_a_bad_hash_are_a_shape_error(self):
        case = H.adoption()
        for body in ({"x": 1}, {"mode": "REPLACE"}, {"source": "ADOPTION"}, {}):
            forged = U.HistoryPublication._make(body)
            for name, call in self.both():
                ops = H.C4Ops()
                e = self.run_err(call, self.maint(ops), forged)
                self.assertErr(e, "store_publication_invalid", "publication", "args", "shape")
                self.assertEqual(ops.ops("create_exclusive:lock"), [])
        # a hash that is a path: it must never reach a path name
        for key in ("../" + "a" * 61, "a" * 63, "A" * 64, "/" + "a" * 63, None, 5):
            view = case.pub.to_dict()
            view["publication_hash"] = key
            forged = U.HistoryPublication._wrap(view, lambda rule: Exception(rule))
            e = self.run_err(self.maint().adopt, forged)
            self.assertErr(e, "store_publication_invalid", "publication", "args", "shape")
        self.assertEqual(H.listing(self.root), [])

    def test_an_operation_that_does_not_fit(self):
        case = H.adoption()
        for name, call in self.both():
            wrong = H.migration().pub if name == "adopt" else case.pub
            e = self.run_err(call, self.maint(), wrong)
            self.assertErr(e, "store_operation_unsupported", "publication", "args",
                           "not_adoption" if name == "adopt" else "not_migration")

    def test_a_hand_made_value_with_an_invalid_candidate(self):
        case = H.migration()
        self.put_v1(case)
        bad = H.C2.rehash(case.pub, spoil)
        self.assertEqual(H.C2.err(U.check_publication, None, bad, case.data)[0], "history_invalid")
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, bad, True)
        self.assertErr(e, "store_candidate_invalid", "publication", "candidate")
        self.assertIsNone(e.__cause__)
        self.assertEqual(H.tree(self.root), before)
        root2 = H.make_root()
        self.addCleanup(__import__("shutil").rmtree, root2, True)
        a = H.adoption()
        H.put(root2, H.HIST, a.data)
        bad = H.C2.rehash(a.pub, spoil)
        e = self.run_err(M.HistoryMaintenance(root2, writable=True).adopt, bad)
        self.assertErr(e, "store_candidate_invalid", "publication", "candidate")
        self.assertEqual(H.raw(root2), a.data)
        self.assertEqual(H.listing(root2), ["history.json"])

    def test_the_refusals_of_the_publication_check_pass_through(self):
        case = H.migration()
        self.put_v1(case)
        body = case.pub.body
        body["plan_hash"] = "zz"
        broken = U.HistoryPublication._make(body)
        e = self.run_err(self.maint().migrate, broken, True)
        self.assertEqual(e.code, "publication_invalid")


class Lock(H.RootCase):
    def test_the_c4_lock_excludes_c3_and_s2(self):
        seen = {}

        def during(real, *args):
            # while C-4 holds its lock (before the publication), C-3 and S2 cannot take theirs
            seen["c3"] = self.run_err(self.c3().read)
            from v2_persistence.local import LocalFileStore
            seen["s2"] = self.run_err(LocalFileStore(self.root, writable=True).read)
            return real(*args)
        ops = H.C4Ops().add("fsync_file", "qtmp", wrap=during)
        adopt = H.adoption()
        self.put_history(adopt.data)
        self.maint(ops).adopt(adopt.pub)
        self.assertEqual(seen["c3"].code, "store_busy")
        self.assertEqual(seen["s2"].code, "store_busy")

    def test_a_c3_operation_in_flight_stops_the_c4_operations(self):
        c = H.C2.day_case()
        self.put_history(c.current)
        outcome = {}

        def during(real, *args):
            m = self.maint()
            outcome["read_original"] = self.run_err(m.read_original, H.HIST)
            outcome["read_set_aside"] = self.run_err(m.read_set_aside, "a" * 64, H.HIST)
            outcome["adopt"] = self.run_err(m.adopt, H.adoption().pub)
            outcome["migrate"] = self.run_err(m.migrate, H.migration().pub, True)
            outcome["inspect"] = m.inspect()
            return real(*args)
        ops = H.C3.C3Ops().add("fsync_file", "tmp", wrap=during)
        self.c3(ops).publish(c.pub)
        for name in ("read_original", "read_set_aside", "adopt", "migrate"):
            self.assertErr(outcome[name], "store_busy", "lock", "lock_acquire")
        self.assertEqual(outcome["inspect"].artifacts[0]["owner"], "C3")          # inspect ignores the lock
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))

    def test_a_left_lock_of_any_owner_stops_every_locked_operation_of_c4(self):
        case = H.migration()
        self.put_v1(case)
        adopt = H.adoption()
        for data in (H.LOCK_C3, H.LOCK_S2, H.LOCK_C4, b"", b"x"):
            H.put(self.root, H.LOCK, data)
            before = H.tree(self.root)
            m = self.maint()
            for fn in (lambda: m.read_original(H.V1), lambda: m.read_set_aside("a" * 64, H.V1),
                       lambda: m.migrate(case.pub, True), lambda: m.adopt(adopt.pub)):
                self.assertErr(self.run_err(fn), "store_busy", "lock", "lock_acquire")
            self.assertEqual(H.tree(self.root), before)

    def test_the_lock_it_writes_is_its_own_marker_and_is_gone_after_a_normal_end(self):
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)
        self.assertNotIn(H.LOCK, os.listdir(self.root))

    def test_a_lock_lost_before_the_publication_is_ownership_lost_and_nothing_is_published(self):
        case = H.adoption()
        self.put_history(case.data)

        def steal(real, *args):
            os.unlink(os.path.join(self.root, H.LOCK))
            H.put(self.root, H.LOCK, H.LOCK_S2)
            return real(*args)
        ops = H.C4Ops().add("fsync_file", "tmp", wrap=steal)
        e = self.run_err(self.maint(ops).adopt, case.pub)
        self.assertErr(e, "store_lock_ownership_lost", "lock", "lock_ownership")
        self.assertEqual(H.raw(self.root), case.data)
        self.assertEqual(H.raw(self.root, H.LOCK), H.LOCK_S2)                    # somebody else's lock is not touched
        self.assertIn("lock_not_ours_left_untouched", e.cleanup)
        self.assertEqual([n for n in os.listdir(self.root) if n.startswith(".history.")], [])

    def test_a_lock_lost_after_the_publication_is_commit_uncertain(self):
        case = H.adoption()
        self.put_history(case.data)

        def steal(real, *args):
            result = real(*args)
            os.unlink(os.path.join(self.root, H.LOCK))
            H.put(self.root, H.LOCK, H.LOCK_S2)
            return result
        ops = H.C4Ops().add("replace", "history", wrap=steal)
        e = self.run_err(self.maint(ops).adopt, case.pub)
        self.assertErr(e, "store_commit_uncertain", "history", "lock_ownership")
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.raw(self.root, H.LOCK), H.LOCK_S2)

    def test_a_failed_release_is_lock_left(self):
        case = H.migration()
        self.put_v1(case)
        e = self.run_err(self.maint(H.C4Ops().fail("unlink", "lock")).migrate, case.pub, True)
        self.assertEqual(e.code, "store_commit_uncertain")
        self.assertEqual(tuple(e.cleanup), ("lock_left",))
        root2 = H.make_root()
        self.addCleanup(__import__("shutil").rmtree, root2, True)
        H.put(root2, H.LOCK, b"")
        os.unlink(os.path.join(root2, H.LOCK))
        # a read-only operation: the failed release is a plain io error with the word
        c = H.C2.day_case()
        H.put(root2, H.HIST, c.current)
        e = self.run_err(M.HistoryMaintenance(root2, _ops=H.C4Ops().fail("unlink", "lock")).read_original, H.HIST)
        self.assertErr(e, "store_io_error", "lock", "lock_release", cleanup=("lock_left",))

    def test_a_directory_as_the_lock_name_is_busy(self):
        os.mkdir(os.path.join(self.root, H.LOCK))
        self.assertEqual(self.run_err(self.maint().read_original, H.HIST).code, "store_busy")


if __name__ == "__main__":
    unittest.main()
