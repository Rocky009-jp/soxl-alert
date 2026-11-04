"""C3-11: an uncertain commit and the reconciliation. The four outcomes are C-2's; the store only reads history.json
again under the lock and passes it on. Nothing is retried, unlocked or cleaned up."""
import os
import unittest

import c3_helpers as H


class AfterAnUncertainPublish(H.RootCase):
    def uncertain(self, case, op, kind=None, after=False):
        self.put_current(case)
        ops = H.C3Ops().fail(op, kind, after=after)
        e = self.run_err(self.store(ops).publish, case.pub)
        self.assertEqual(e.code, "store_commit_uncertain")
        return e

    def test_a_failure_before_the_replace_is_not_published_and_the_same_value_can_be_tried_again(self):
        c = H.C2.day_case()
        self.uncertain(c, "replace", "history")
        self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "NOT_PUBLISHED")
        res = self.store().publish(c.pub)               # the same value, with the CAS done again under the lock
        self.assertEqual(res.status, "PUBLISHED")
        self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "PUBLISHED")

    def test_a_failure_after_the_replace_is_published(self):
        for op, kind, after in (("replace", "history", True), ("fsync_dir", None, False), ("unlink", "lock", False)):
            with self.subTest(op=op):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                c = H.C2.day_case()
                self.uncertain(c, op, kind, after)
                if op == "unlink":
                    os.unlink(os.path.join(root, H.LOCK))        # the lock the failed release left, by hand
                res = self.store(writable=False).reconcile(c.pub)
                self.assertEqual((res.outcome, res.publication_hash), ("PUBLISHED", c.pub.publication_hash))

    def test_a_later_publication_makes_it_published_then_extended(self):
        c = H.C2.day_case()
        self.uncertain(c, "fsync_dir")
        H.put(self.root, H.HIST, H.C2.file_bytes(H.C2.extended_history(c)))
        self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "PUBLISHED_THEN_EXTENDED")

    def test_another_content_or_a_broken_or_missing_file_is_a_conflict(self):
        c = H.C2.day_case()
        self.uncertain(c, "replace", "history")
        for name, data in (("another extension", H.C2.file_bytes(H.C2.other_extension(c))),
                           ("truncated", c.current[:-7]), ("empty", b""), ("not utf8", b"\xff\xfe"),
                           ("missing", None)):
            with self.subTest(name=name):
                if data is None:
                    os.unlink(os.path.join(self.root, H.HIST))
                else:
                    H.put(self.root, H.HIST, data)
                self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "CONFLICT")

    def test_a_leftover_tmp_does_not_stop_the_answer_but_does_stop_a_new_publication(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("replace", "history").fail("unlink", "tmp")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_commit_uncertain", "history", "replace", cleanup=("tmp_left",))
        left = [n for n in H.listing(self.root) if n.startswith(".history.")]
        self.assertEqual(len(left), 1)
        self.assertEqual(self.store().reconcile(c.pub).outcome, "NOT_PUBLISHED")
        self.assertEqual(self.run_err(self.store().publish, c.pub).code, "store_artifact_present")
        self.assertEqual(self.run_err(self.store().read).code, "store_artifact_present")
        self.assertEqual(H.listing(self.root), sorted(["history.json"] + left))      # nothing was cleaned up

    def test_the_answer_is_about_history_json_only_even_when_a_tmp_holds_the_candidate(self):
        c = H.C2.day_case()
        self.put_current(c)
        H.put(self.root, ".history.%s.tmp" % ("a" * 32), H.C2.file_bytes(c.candidate))
        self.assertEqual(self.store().reconcile(c.pub).outcome, "NOT_PUBLISHED")


class AfterAnUncertainInitialize(H.RootCase):
    def test_not_published_then_the_same_value_initializes(self):
        g = H.C2.genesis_case()
        ops = H.C3Ops().fail("replace", "history")
        self.assertEqual(self.run_err(self.store(ops).initialize, g.pub).code, "store_commit_uncertain")
        self.assertEqual(self.store().reconcile(g.pub).outcome, "NOT_PUBLISHED")
        self.assertEqual(self.store().initialize(g.pub).status, "INITIALIZED")

    def test_published_after_a_failed_directory_sync(self):
        g = H.C2.genesis_case()
        ops = H.C3Ops().fail("fsync_dir")
        self.assertEqual(self.run_err(self.store(ops).initialize, g.pub).code, "store_commit_uncertain")
        self.assertEqual(self.store().reconcile(g.pub).outcome, "PUBLISHED")
        self.assertEqual(self.run_err(self.store().initialize, g.pub).code, "already_initialized")


class ReconcileItself(H.RootCase):
    def test_it_takes_and_releases_the_lock_and_writes_nothing(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        before = H.state_of(self.root)
        self.store(ops, writable=False).reconcile(c.pub)
        self.assertEqual(ops.ops("create_exclusive:lock", "unlink:lock", "replace", "create_exclusive:tmp"),
                         ["create_exclusive:lock", "unlink:lock"])
        self.assertEqual(H.state_of(self.root), before)

    def test_a_v1_file_stops_it_and_a_lock_stops_it(self):
        c = H.C2.day_case()
        self.put_current(c)
        H.put(self.root, H.V1, b"{}")
        e = self.run_err(self.store().reconcile, c.pub)
        self.assertStore(e, "store_layout_unsupported", "store", "scan", rule="v1_and_v2")
        os.unlink(os.path.join(self.root, H.V1))
        H.put(self.root, H.LOCK, b"x\n")
        self.assertEqual(self.run_err(self.store().reconcile, c.pub).code, "store_busy")
        self.assertEqual(H.raw(self.root, H.LOCK), b"x\n")           # it is not unlocked for the caller

    def test_an_empty_root_is_not_published_for_a_genesis_and_a_conflict_for_an_append(self):
        self.assertEqual(self.store().reconcile(H.C2.genesis_case().pub).outcome, "NOT_PUBLISHED")
        self.assertEqual(self.store().reconcile(H.C2.day_case().pub).outcome, "CONFLICT")

    def test_a_wrong_value_is_the_values_refusal_and_the_lock_is_released(self):
        c = H.C2.day_case()
        self.put_current(c)
        e = self.run_err(self.store().reconcile, "not a publication")
        self.assertStore(e, "store_publication_invalid", "publication", "args", rule="type")
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_an_io_error_while_reading_is_an_error_not_a_conflict(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("read_file", "history")
        e = self.run_err(self.store(ops).reconcile, c.pub)
        self.assertStore(e, "store_io_error", "history", "read")

    def test_it_works_in_every_root_state_that_has_history_json(self):
        c = H.C2.restore_case(consume=True)
        self.put_current(c)
        self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "NOT_PUBLISHED")
        H.put(self.root, H.HIST, H.C2.file_bytes(c.candidate))
        self.assertEqual(self.store(writable=False).reconcile(c.pub).outcome, "PUBLISHED")


if __name__ == "__main__":
    unittest.main()
