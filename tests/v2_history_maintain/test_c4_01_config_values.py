"""C4-02 the configuration, the immutable values and the names that must match C-3 and S2."""
import os
import re
import unittest

import c4_helpers as H
import v2_history_local.store as c3store
import v2_history_maintain as M
import v2_history_maintain.store as m4store
import v2_history_maintain.values as m4values
import v2_persistence.local.store as s2store
from v2_core.errors import CoreError


class Config(H.RootCase):
    def test_a_good_construction_and_its_repr(self):
        m = M.HistoryMaintenance(self.root, writable=True, durability=M.STRICT)
        self.assertEqual(repr(m), "HistoryMaintenance(writable=True, durability=strict)")
        self.assertTrue(m.writable)
        self.assertEqual(m.persistence_level, M.FILE_AND_DIRECTORY_SYNC)
        m2 = M.HistoryMaintenance(self.root, durability=M.FILE_SYNC_ONLY_MODE)
        self.assertFalse(m2.writable)
        self.assertEqual(m2.persistence_level, M.FILE_SYNC_ONLY)
        self.assertNotIn(self.root, repr(m))

    def test_bad_roots_are_store_root_invalid(self):
        dummy = os.path.join(self.root, "file")
        H.put(self.root, "file", b"x")
        link = os.path.join(self.root, "link")
        try:
            os.symlink(self.root, link)
        except (OSError, NotImplementedError, AttributeError):
            link = None
        bad = [None, 5, "", "relative/path", b"/abs", os.path.join(self.root, "missing"), dummy, "/a\0b"]
        if link:
            bad.append(link)
        for root in bad:
            with self.assertRaises(M.LocalStoreError) as cm:
                M.HistoryMaintenance(root)
            self.assertErr(cm.exception, "store_root_invalid", "root", "root")

    def test_bad_durability_and_writable_are_store_config_invalid(self):
        for d in ("", "STRICT", None, 1, "FILE_SYNC_ONLY"):
            with self.assertRaises(M.LocalStoreError) as cm:
                M.HistoryMaintenance(self.root, durability=d)
            self.assertErr(cm.exception, "store_config_invalid", "durability", "args")
        for w in (0, 1, None, "yes"):
            with self.assertRaises(M.LocalStoreError) as cm:
                M.HistoryMaintenance(self.root, writable=w)
            self.assertErr(cm.exception, "store_config_invalid", "writable", "args")

    def test_a_root_that_vanished_is_noticed_by_every_operation(self):
        m = self.maint()
        os.rmdir(self.root)
        for fn in (m.inspect, lambda: m.read_original(H.HIST), lambda: m.read_set_aside("a" * 64, H.HIST)):
            e = self.run_err(fn)
            self.assertErr(e, "store_root_invalid", "root", "root")
        os.mkdir(self.root)

    def test_bad_names_and_keys_are_store_config_invalid(self):
        m = self.maint()
        for name in ("history", "write.lock", "", None, 3, "../history.json", "MANIFEST", "history.json/"):
            e = self.run_err(m.read_original, name)
            self.assertErr(e, "store_config_invalid", "name", "args")
        for key in ("", "A" * 64, "a" * 63, "a" * 65, None, 7, "../" + "a" * 61):
            e = self.run_err(m.read_set_aside, key, H.HIST)
            self.assertErr(e, "store_config_invalid", "key", "args")
        for name in ("MANIFEST", "../history.json", "", None, "x.json", ".q." + "a" * 32 + ".tmp", "a/b"):
            e = self.run_err(m.read_set_aside, "a" * 64, name)
            self.assertErr(e, "store_config_invalid", "name", "args")
        self.assertEqual(H.listing(self.root), [])

    def test_read_only_store_cannot_change_anything(self):
        m = self.maint(writable=False)
        case = H.migration()
        self.put_v1(case)
        before = H.tree(self.root)
        for fn in (lambda: m.migrate(case.pub, True), lambda: m.adopt(H.adoption().pub)):
            self.assertErr(self.run_err(fn), "store_read_only", "store", "args")
        self.assertEqual(H.tree(self.root), before)


class Values(H.RootCase):
    def test_the_values_are_immutable_and_hold_no_path(self):
        H.lock_and_tmps(self.root)
        report = self.maint().inspect()
        plan = M.plan_unlock(report, "u-1", True)
        res = self.maint().unlock(plan, plan.plan_hash)
        for obj in (report, plan, res):
            for attr in ("x", "layout", "status", "plan_hash"):
                with self.assertRaises((AttributeError, TypeError)):
                    setattr(obj, attr, 1)
            with self.assertRaises((AttributeError, TypeError)):
                delattr(obj, "__class__")
            text = repr(obj) + str(obj.__class__)
            self.assertNotIn(self.root, text)
            self.assertNotIn(os.path.basename(self.root), text)
        self.assertNotIn(self.root, repr(report.to_dict()))
        self.assertNotIn(self.root, repr(plan.to_dict()))
        self.assertNotIn(self.root, repr(res))
        with self.assertRaises(TypeError):
            M.RootReport()
        with self.assertRaises(TypeError):
            M.UnlockPlan()

    def test_accessors_hand_out_copies(self):
        H.lock_and_tmps(self.root)
        report = self.maint().inspect()
        report.artifacts[0]["name"] = "changed"
        self.assertNotEqual(report.artifacts[0]["name"], "changed")
        plan = M.plan_unlock(report, "u-1", True)
        plan.targets[0]["name"] = "changed"
        plan.body["targets"].clear()
        self.assertEqual(len(plan.targets), 3)

    def test_a_result_is_a_frozen_dataclass_of_five_fields(self):
        case = H.migration()
        self.put_v1(case)
        res = self.maint().migrate(case.pub, True)
        self.assertEqual((res.status, res.key, res.resumed, res.persistence_level),
                         (M.MIGRATED, case.key, False, M.FILE_AND_DIRECTORY_SYNC))
        self.assertEqual(sorted(res.__dataclass_fields__), ["history", "key", "persistence_level", "resumed", "status"])
        with self.assertRaises(Exception):
            res.status = "x"
        self.assertEqual(res.history, case.candidate)


class Names(unittest.TestCase):
    """The name constants are the same in S2, C-3 and C-4 (the runtime imports none of the first two beyond the words)."""

    def test_the_file_and_lock_names_and_tmp_shapes(self):
        self.assertEqual(m4values.HISTORY_NAME, c3store.HISTORY_NAME)
        self.assertEqual(m4values.V1_NAME, c3store.V1_NAME)
        self.assertEqual(m4values.V1_NAME, s2store.SNAPSHOT_NAME)
        self.assertEqual(m4values.LOCK_NAME, c3store.LOCK_NAME)
        self.assertEqual(m4values.LOCK_NAME, s2store.LOCK_NAME)
        self.assertEqual((m4values.TMP_PREFIX, m4values.TMP_SUFFIX), (c3store.TMP_PREFIX, c3store.TMP_SUFFIX))
        self.assertEqual(m4values.S2_TMP_PREFIX, c3store.S2_TMP_PREFIX)
        self.assertEqual(m4values.S2_TMP_PREFIX, s2store.TMP_PREFIX)
        self.assertEqual(m4values.TMP_SUFFIX, s2store.TMP_SUFFIX)
        self.assertEqual(m4values.C3_LOCK_MAGIC, c3store.LOCK_MAGIC)
        self.assertEqual(m4values.S2_LOCK_MAGIC, s2store.LOCK_MAGIC)
        self.assertEqual(m4values.LOCK_MAGIC, b"v2_history_maintain.lock\n")
        self.assertEqual(m4store._MODES, c3store._MODES)

    def test_the_lock_marker_the_package_writes(self):
        case = H.migration()
        root = H.make_root()
        try:
            H.put(root, H.V1, case.data)
            seen = []

            class Spy(H.C4Ops):
                def write(self, writer, data):
                    if self._wkind.get(id(writer)) == "lock":
                        seen.append(bytes(data))
                    return super().write(writer, data)
            M.HistoryMaintenance(root, writable=True, _ops=Spy()).migrate(case.pub, True)
            self.assertEqual(len(seen), 1)
            self.assertTrue(re.fullmatch(rb"v2_history_maintain\.lock\n[0-9a-f]{32}\n", seen[0]), seen[0])
        finally:
            import shutil
            shutil.rmtree(root, True)

    def test_the_error_type_is_the_one_of_s2(self):
        self.assertIs(M.LocalStoreError, c3store.LocalStoreError)
        self.assertTrue(issubclass(M.LocalStoreError, CoreError))
        self.assertEqual((M.STRICT, M.FILE_SYNC_ONLY_MODE), (s2store.STRICT, s2store.FILE_SYNC_ONLY_MODE))


if __name__ == "__main__":
    unittest.main()
