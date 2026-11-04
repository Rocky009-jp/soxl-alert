"""C3-10 the write procedure and its faults, C3-12 the persistence levels, C3-14 no leak in an error.

The expected order is the one of design 3 (and S2's 6.3); the expected codes, phases and clean-up words are the table of
design 5.1. Both come from the documents, not from the store's output."""
import os
import unittest

import c3_helpers as H

ORDER = ["create_exclusive:lock", "listdir", "read_file:history", "probe_dir_sync", "create_exclusive:tmp",
         "write:tmp", "flush:tmp", "fsync_file:tmp", "close:tmp", "read_file:lock", "replace:history", "fsync_dir",
         "read_file:lock", "unlink:lock"]
WATCH = tuple(sorted(set(ORDER)))


class Procedure(H.RootCase):
    def test_the_order_of_the_calls_of_a_strict_publication(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        self.store(ops).publish(c.pub)
        self.assertEqual(ops.ops(*WATCH), ORDER)

    def test_an_initialization_has_the_same_order_without_the_read_of_a_file(self):
        g = H.C2.genesis_case()
        ops = H.C3Ops()
        self.store(ops).initialize(g.pub)
        self.assertEqual(ops.ops(*WATCH), [n for n in ORDER if n != "read_file:history"])

    def test_the_file_is_never_opened_for_writing_directly(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        self.store(ops).publish(c.pub)
        created = [k for (op, k) in ops.trace if op == "create_exclusive"]
        self.assertEqual(created, ["lock", "tmp"])
        self.assertEqual([k for (op, k) in ops.trace if op == "replace"], ["history"])

    def test_short_writes_are_repeated_until_everything_is_written(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        ops.max_write = 7
        self.store(ops).publish(c.pub)
        writes = [k for (op, k) in ops.trace if op == "write" and k == "tmp"]
        self.assertGreater(len(writes), 10)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_a_write_that_makes_no_progress_is_an_error_not_a_loop(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().add("write", "tmp", wrap=lambda real, w, d: 0)
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_io_error", "history", "write", cleanup=())
        self.assertEqual(H.listing(self.root), ["history.json"])
        self.assertEqual(H.raw(self.root), c.current)


class Faults(H.RootCase):
    """Each stage fails once; the history file stays what it was and no temporary file of ours is left."""

    def faulty(self, case, op, kind=None, **kw):
        self.put_current(case)
        ops = H.C3Ops().fail(op, kind, **kw)
        return ops, self.run_err(self.store(ops).publish, case.pub)

    def test_each_stage_before_the_replace(self):
        c = H.C2.day_case()
        table = [
            ("flush", "tmp", "flush"), ("fsync_file", "tmp", "file_sync"), ("close", "tmp", "close"),
            ("write", "tmp", "write"), ("create_exclusive", "tmp", "tmp_create"),
        ]
        for op, kind, phase in table:
            with self.subTest(op=op):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                ops, e = self.faulty(c, op, kind)
                self.assertStore(e, "store_io_error", "history", phase, cleanup=())
                self.assertEqual(H.listing(root), ["history.json"])
                self.assertEqual(H.raw(root), c.current)
                self.assertEqual(ops.ops("replace"), [])

    def test_the_lock_creation_and_its_marker(self):
        c = H.C2.day_case()
        for op, kind, cleanup, leftover in (("create_exclusive", "lock", (), []),
                                            ("write", "lock", (), []),
                                            ("fstat", "lock", ("lock_left",), ["write.lock"])):
            with self.subTest(op=op):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                ops, e = self.faulty(c, op, kind)
                self.assertStore(e, "store_io_error", "lock", "lock_acquire", cleanup=cleanup)
                self.assertEqual(sorted(set(H.listing(root)) - {"history.json"}), leftover)

    def test_a_temporary_file_that_cannot_be_identified_is_left_and_named(self):
        c = H.C2.day_case()
        ops, e = self.faulty(c, "fstat", "tmp")
        self.assertStore(e, "store_io_error", "history", "tmp_create", cleanup=("tmp_left",))
        self.assertEqual(len([n for n in H.listing(self.root) if n.endswith(".tmp")]), 1)
        self.assertEqual(H.raw(self.root), c.current)

    def test_a_temporary_file_that_cannot_be_removed_is_left_and_named(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("flush", "tmp").fail("unlink", "tmp")
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_io_error", "history", "flush", cleanup=("tmp_left",))
        self.assertEqual(len([n for n in H.listing(self.root) if n.startswith(".history.")]), 1)
        self.assertEqual(H.raw(self.root), c.current)

    def test_a_temporary_file_that_was_swapped_is_not_removed(self):
        c = H.C2.day_case()
        self.put_current(c)

        def swap(real, writer, data):
            name = [n for n in os.listdir(self.root) if n.startswith(".history.")][0]
            path = os.path.join(self.root, name)
            os.unlink(path)
            H.put(self.root, name, b"someone else's file")
            raise H.injected()
        ops = H.C3Ops().add("write", "tmp", wrap=swap)
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_io_error", "history", "write", cleanup=("tmp_ownership_unconfirmed",))
        left = [n for n in H.listing(self.root) if n.startswith(".history.")]
        self.assertEqual(len(left), 1)
        self.assertEqual(H.raw(self.root, left[0]), b"someone else's file")

    def test_the_replace_and_what_follows_are_uncertain(self):
        c = H.C2.day_case()
        for name, kw, phase, new in (("replace fails", dict(op="replace", kind="history"), "replace", False),
                                     ("replace fails after doing it", dict(op="replace", kind="history", after=True),
                                      "replace", True),
                                     ("directory sync fails", dict(op="fsync_dir"), "dir_sync", True)):
            with self.subTest(case=name):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                ops, e = self.faulty(c, **kw)
                self.assertStore(e, "store_commit_uncertain", "history", phase, cleanup=())
                expected = H.C2.file_bytes(c.candidate) if new else c.current
                self.assertEqual(H.raw(root), expected)
                self.assertEqual(H.listing(root), ["history.json"])

    def test_the_same_faults_for_an_initialization(self):
        g = H.C2.genesis_case()
        for op, kind, code, phase in (("create_exclusive", "tmp", "store_io_error", "tmp_create"),
                                      ("fsync_file", "tmp", "store_io_error", "file_sync"),
                                      ("replace", "history", "store_commit_uncertain", "replace"),
                                      ("fsync_dir", None, "store_commit_uncertain", "dir_sync")):
            with self.subTest(op=op):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                ops = H.C3Ops().fail(op, kind)
                e = self.run_err(self.store(ops).initialize, g.pub)
                self.assertStore(e, code, "history", phase, cleanup=())
                after = H.listing(root)
                self.assertEqual(after, ["history.json"] if op == "fsync_dir" else [])


class Levels(H.RootCase):
    def test_strict_syncs_the_file_and_the_directory(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        res = self.store(ops, durability="strict").publish(c.pub)
        self.assertEqual(res.persistence_level, "FILE_AND_DIRECTORY_SYNC")
        self.assertEqual(ops.ops("fsync_file:tmp", "probe_dir_sync", "fsync_dir"),
                         ["probe_dir_sync", "fsync_file:tmp", "fsync_dir"])

    def test_file_sync_only_does_not_touch_the_directory_sync(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        self.store(ops, durability="file_sync_only").publish(c.pub)
        self.assertEqual(ops.ops("fsync_file:tmp", "probe_dir_sync", "fsync_dir"), ["fsync_file:tmp"])

    def test_strict_is_refused_on_windows_before_anything_is_written(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        ops.windows = True
        before = H.state_of(self.root)
        e = self.run_err(self.store(ops).publish, c.pub)
        self.assertStore(e, "store_durability_unsupported", "durability", "durability_probe", rule="windows_strict")
        self.assertEqual(ops.ops("create_exclusive:tmp", "replace"), [])
        self.assertEqual(H.state_of(self.root), before)

    def test_file_sync_only_is_accepted_on_windows(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        ops.windows = True
        res = self.store(ops, durability="file_sync_only").publish(c.pub)
        self.assertEqual(res.status, "PUBLISHED")

    def test_a_directory_that_cannot_be_synced_is_refused_before_anything_is_written(self):
        for case, op in ((H.C2.day_case(), "publish"), (H.C2.genesis_case(), "initialize")):
            with self.subTest(op=op):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                self.root = root
                self.put_current(case)
                ops = H.C3Ops().fail("probe_dir_sync")
                before = H.state_of(root)
                e = self.run_err(getattr(self.store(ops), op), case.pub)
                self.assertStore(e, "store_durability_unsupported", "durability", "durability_probe",
                                 rule="directory_sync")
                self.assertEqual(ops.ops("create_exclusive:tmp"), [])
                self.assertEqual(H.state_of(root), before)

    def test_the_windows_refusal_of_an_initialization_leaves_an_empty_root(self):
        ops = H.C3Ops()
        ops.windows = True
        e = self.run_err(self.store(ops).initialize, H.C2.genesis_case().pub)
        self.assertEqual((e.code, e.rule), ("store_durability_unsupported", "windows_strict"))
        self.assertEqual(H.listing(self.root), [])


class NoLeak(H.RootCase):
    def shown(self, e):
        parts = [str(e), repr(e), repr(sorted(e.__dict__.items(), key=lambda kv: kv[0])), " ".join(getattr(e, "cleanup", ()))]
        return " | ".join(parts)

    def test_no_path_secret_or_os_text_in_any_error(self):
        c = H.C2.day_case()
        stages = [("create_exclusive", "lock"), ("fstat", "lock"), ("write", "lock"), ("listdir", None),
                  ("lstat", "history"), ("read_file", "history"), ("probe_dir_sync", None),
                  ("create_exclusive", "tmp"), ("write", "tmp"), ("flush", "tmp"), ("fsync_file", "tmp"),
                  ("close", "tmp"), ("replace", "history"), ("fsync_dir", None), ("unlink", "lock")]
        for op, kind in stages:
            for after in (False, True):
                if after and op not in ("replace", "write"):
                    continue
                with self.subTest(op=op, kind=kind, after=after):
                    root = H.make_root()
                    self.addCleanup(__import__("shutil").rmtree, root, True)
                    self.root = root
                    self.put_current(c)
                    ops = H.C3Ops().fail(op, kind, after=after)
                    try:
                        self.store(ops).publish(c.pub)
                    except Exception as e:
                        text = self.shown(e)
                        for secret in (H.SECRET, "secret", "injected failure", root, "OSError", "Errno",
                                       os.path.basename(root), "Traceback"):
                            self.assertNotIn(secret, text)
                        self.assertIsNone(e.__cause__)
                        self.assertIsNone(e.__context__)
                    else:
                        self.fail("the injected failure did not stop the publication")

    def test_a_secret_like_text_in_the_publication_is_not_echoed_either(self):
        # the refusals name fixed identifiers only: nothing of the value is in the text
        c = H.C2.day_case()
        self.put_current(c)
        H.put(self.root, H.HIST, c.current[:-7])
        e = self.run_err(self.store().publish, c.pub)
        text = self.shown(e)
        self.assertNotIn(self.root, text)
        self.assertNotIn(c.pub.publication_hash, text)


if __name__ == "__main__":
    unittest.main()
