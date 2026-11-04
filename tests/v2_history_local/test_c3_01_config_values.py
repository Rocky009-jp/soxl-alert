"""C3-02: configuration, root and result values. C3-03 (initialization) is in test_c3_02."""
import dataclasses
import os
import unittest

import c3_helpers as H
from v2_history_local import (FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, FILE_SYNC_ONLY_MODE, INITIALIZED, PUBLISHED,
                              STRICT, HistoryFileStore, HistoryStoreResult, LocalStoreError)


class RootArguments(H.RootCase):
    def test_roots_that_are_not_an_absolute_existing_plain_directory(self):
        file_path = os.path.join(self.root, "a-file")
        H.put(self.root, "a-file", b"x")
        link = os.path.join(self.root, "a-link")
        linked = True
        try:
            os.symlink(self.root, link)
        except (OSError, NotImplementedError, AttributeError):
            linked = False
        bad = ["relative/dir", "history", "", os.path.join(self.root, "missing"), file_path, self.root + "\0x",
               None, 5, b"/tmp", [self.root], 3.5]
        if linked:
            bad.append(link)
        for root in bad:
            with self.subTest(root=repr(root)[:30]):
                with self.assertRaises(LocalStoreError) as cm:
                    HistoryFileStore(root)
                self.assertStore(cm.exception, "store_root_invalid", "root", "root")

    def test_root_is_checked_again_at_every_operation(self):
        store = self.store()
        import shutil
        shutil.rmtree(self.root)
        for call in (store.read,):
            e = self.run_err(call)
            self.assertStore(e, "store_root_invalid", "root", "root")
        g = H.C2.genesis_case()
        self.assertStore(self.run_err(store.initialize, g.pub), "store_root_invalid", "root", "root")
        self.assertStore(self.run_err(store.reconcile, g.pub), "store_root_invalid", "root", "root")
        os.mkdir(self.root)                     # for the clean-up of the test

    def test_a_path_object_is_accepted_like_its_string(self):
        class P(object):
            def __fspath__(self_inner):
                return self.root
        self.assertEqual(HistoryFileStore(P()).durability, STRICT)


class OtherArguments(H.RootCase):
    def test_durability_and_writable(self):
        for value in ("x", "", None, 1, "STRICT", ["strict"]):
            with self.subTest(durability=repr(value)):
                with self.assertRaises(LocalStoreError) as cm:
                    HistoryFileStore(self.root, durability=value)
                self.assertStore(cm.exception, "store_config_invalid", "durability", "args")
        for value in ("yes", 1, 0, None, []):
            with self.subTest(writable=repr(value)):
                with self.assertRaises(LocalStoreError) as cm:
                    HistoryFileStore(self.root, writable=value)
                self.assertStore(cm.exception, "store_config_invalid", "writable", "args")

    def test_defaults_and_the_two_modes(self):
        s = HistoryFileStore(self.root)
        self.assertEqual((s.writable, s.durability, s.persistence_level), (False, STRICT, FILE_AND_DIRECTORY_SYNC))
        s = HistoryFileStore(self.root, writable=True, durability=FILE_SYNC_ONLY_MODE)
        self.assertEqual((s.writable, s.durability, s.persistence_level), (True, FILE_SYNC_ONLY_MODE, FILE_SYNC_ONLY))

    def test_the_store_shows_no_path(self):
        s = HistoryFileStore(self.root, writable=True)
        self.assertNotIn(self.root, repr(s))
        self.assertEqual(repr(s), "HistoryFileStore(writable=True, durability=strict)")
        public = [n for n in dir(s) if not n.startswith("_")]
        for name in public:
            value = getattr(s, name)
            if not callable(value):
                self.assertNotIn(self.root, str(value))
        self.assertEqual(set(public), {"initialize", "durability", "persistence_level", "publish", "read",
                                       "reconcile", "writable"})

    def test_errors_show_no_path(self):
        with self.assertRaises(LocalStoreError) as cm:
            HistoryFileStore(os.path.join(self.root, "missing"))
        for text in (str(cm.exception), repr(cm.exception), repr(cm.exception.__dict__)):
            self.assertNotIn(self.root, text)
            self.assertNotIn("missing", text)


class ResultValue(unittest.TestCase):
    def test_it_is_immutable_and_has_five_fields(self):
        r = HistoryStoreResult(PUBLISHED, True, None, FILE_SYNC_ONLY, "h" * 64)
        self.assertEqual([f.name for f in dataclasses.fields(r)],
                         ["status", "committed", "history", "persistence_level", "publication_hash"])
        for name in ("status", "committed", "history", "persistence_level", "publication_hash", "extra"):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(r, name, 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            delattr(r, "status")
        self.assertEqual((PUBLISHED, INITIALIZED), ("PUBLISHED", "INITIALIZED"))
        self.assertEqual(r, HistoryStoreResult(PUBLISHED, True, None, FILE_SYNC_ONLY, "h" * 64))


if __name__ == "__main__":
    unittest.main()
