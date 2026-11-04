"""C4-05 unlock, C4-06 its refusals, C4-07 interruption and resumption, C4-08 the leftovers of C-3's review P-02."""
import os
import unittest

import c4_helpers as H
import v2_history_maintain as M
from v2_history_maintain.values import UnlockPlan


def inode(root, name):
    return os.lstat(os.path.join(root, name)).st_ino


class Unlock(H.RootCase):
    def planned(self, lock=H.LOCK_C3, tmps=((H.TMP_H, b"c3-partial"), (H.TMP_S, b"s2-partial"))):
        H.lock_and_tmps(self.root, lock=lock, tmps=tmps)
        before = {n: (H.raw(self.root, n), inode(self.root, n)) for n in os.listdir(self.root)}
        m = self.maint()
        plan = M.plan_unlock(m.inspect(), "u-1", True)
        return m, plan, before

    def check_done(self, plan, before):
        self.assertEqual(H.listing(self.root), ["quarantine"])
        key = plan.plan_hash
        names = sorted(before) + ["MANIFEST"]
        self.assertEqual(H.qnames(self.root, key), sorted(names))
        for n, (data, ino) in before.items():
            self.assertEqual(H.qraw(self.root, key, n), data)
            self.assertEqual(os.lstat(os.path.join(self.root, "quarantine", key, n)).st_ino, ino)   # renamed, not copied
        targets = [(t["name"], t["kind"], t["raw_sha256"], t["raw_size"]) for t in plan.targets]
        for (n, _k, s, z) in targets:
            self.assertEqual((s, z), (H.sha(before[n][0]), len(before[n][0])))
        self.assertEqual(H.qraw(self.root, key, "MANIFEST"),
                         H.manifest_expected("UNLOCK", key, "u-1", key, None, True, targets))

    def test_a_left_lock_of_each_kind_alone(self):
        for data in (H.LOCK_C3, H.LOCK_S2, b"", H.LOCK_C4, b"foreign\n"):
            with self.subTest(owner=data[:12]):
                for n in os.listdir(self.root):
                    if n == H.QUAR:
                        import shutil
                        shutil.rmtree(os.path.join(self.root, n))
                    else:
                        os.unlink(os.path.join(self.root, n))
                m, plan, before = self.planned(lock=data, tmps=())
                res = m.unlock(plan, plan.plan_hash)
                self.assertEqual((res.status, res.key, res.resumed, res.history), (M.UNLOCKED, plan.plan_hash, False, None))
                self.check_done(plan, before)

    def test_temporary_files_alone_use_the_c4_lock_and_release_it(self):
        m, plan, before = self.planned(lock=None)
        self.assertNotIn(H.LOCK, before)
        ops = H.C4Ops()
        res = self.maint(ops).unlock(plan, plan.plan_hash)
        self.assertEqual(res.status, M.UNLOCKED)
        self.check_done(plan, before)
        self.assertEqual(ops.ops("create_exclusive:lock", "unlink:lock"), ["create_exclusive:lock", "unlink:lock"])

    def test_lock_and_temporary_files_the_lock_goes_last_and_no_new_lock_is_taken(self):
        m, plan, before = self.planned()
        ops = H.C4Ops()
        self.maint(ops).unlock(plan, plan.plan_hash)
        self.check_done(plan, before)
        self.assertEqual([k for (op, k) in ops.trace if op == "rename"], ["tmp", "s2tmp", "lock"])
        self.assertEqual(ops.ops("create_exclusive:lock", "unlink:lock"), [])
        self.assertEqual([k for (op, k) in ops.trace if op == "create_exclusive"], ["qtmp"])

    def test_after_an_unlock_c3_reads_and_publishes(self):
        c = H.C2.day_case()
        self.put_history(c.current)
        m, plan, before = self.planned()
        e = self.run_err(self.c3().publish, c.pub)
        self.assertEqual(e.code, "store_busy")
        m.unlock(plan, plan.plan_hash)
        res = self.c3().publish(c.pub)
        self.assertEqual(res.status, "PUBLISHED")
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))
        self.assertEqual(sorted(os.listdir(self.root)), ["history.json", "quarantine"])
        self.assertEqual(self.c3().read(), c.candidate)

    def test_the_strict_levels_and_the_directory_syncs(self):
        m, plan, before = self.planned(tmps=((H.TMP_H, b"x"),))
        ops = H.C4Ops()
        self.maint(ops).unlock(plan, plan.plan_hash)
        self.assertEqual(ops.ops("probe_dir_sync", "fsync_dir:root", "fsync_dir:qdir", "fsync_dir:kdir"),
                         ["probe_dir_sync", "fsync_dir:root", "fsync_dir:qdir", "fsync_dir:kdir", "fsync_dir:kdir",
                          "fsync_dir:root"])
        self.assertEqual(ops.ops("fsync_file:qtmp"), ["fsync_file:qtmp"])

    def test_file_sync_only_does_not_sync_directories(self):
        m, plan, before = self.planned(tmps=((H.TMP_H, b"x"),))
        ops = H.C4Ops()
        res = self.maint(ops, durability=M.FILE_SYNC_ONLY_MODE).unlock(plan, plan.plan_hash)
        self.assertEqual(res.persistence_level, M.FILE_SYNC_ONLY)
        self.assertEqual(ops.ops("probe_dir_sync", "fsync_dir"), [])
        self.assertEqual(ops.ops("fsync_file:qtmp"), ["fsync_file:qtmp"])
        self.check_done(plan, before)

    def test_a_second_call_after_completion_is_a_resumed_success(self):
        m, plan, before = self.planned()
        m.unlock(plan, plan.plan_hash)
        res = m.unlock(plan, plan.plan_hash)
        self.assertEqual((res.status, res.resumed), (M.UNLOCKED, True))
        self.check_done(plan, before)


ABSENT = object()


class Refusals(H.RootCase):
    def planned(self, with_lock=True):
        H.lock_and_tmps(self.root, lock=H.LOCK_C3 if with_lock else None)
        m = self.maint()
        return m, M.plan_unlock(m.inspect(), "u-1", True)

    def refused(self, m, plan, h=ABSENT):
        before = H.tree(self.root)
        e = self.run_err(m.unlock, plan, plan.plan_hash if h is ABSENT else h)
        self.assertEqual(H.tree(self.root), before)
        return e

    def test_an_unconfirmed_hash(self):
        m, plan = self.planned()
        for h in ("0" * 64, plan.plan_hash.upper(), None, 5, "", plan.plan_hash + "0", b"x"):
            self.assertErr(self.refused(m, plan, h), "maintenance_plan_unconfirmed", "plan", "args")

    def test_a_new_temporary_file_after_the_plan(self):
        for with_lock in (True, False):
            m, plan = self.planned(with_lock)
            H.put(self.root, H.TMP_H2, b"new")
            self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")
            os.unlink(os.path.join(self.root, H.TMP_H2))
            os.unlink(os.path.join(self.root, H.TMP_H))
            os.unlink(os.path.join(self.root, H.TMP_S))
            if with_lock:
                os.unlink(os.path.join(self.root, H.LOCK))

    def test_a_lock_that_appeared_after_a_plan_without_a_lock(self):
        m, plan = self.planned(with_lock=False)
        H.put(self.root, H.LOCK, H.LOCK_S2)
        self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")

    def test_a_target_that_disappeared(self):
        for gone in (H.TMP_H, H.LOCK):
            m, plan = self.planned()
            os.unlink(os.path.join(self.root, gone))
            self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")
            for n in os.listdir(self.root):
                os.unlink(os.path.join(self.root, n))

    def test_the_same_bytes_in_another_file_are_another_inode(self):
        m, plan = self.planned()
        data = H.raw(self.root, H.LOCK)
        H.put(self.root, "copy-of-lock", data)             # both exist at once, so the inode cannot be the same
        os.replace(os.path.join(self.root, "copy-of-lock"), os.path.join(self.root, H.LOCK))
        before_ino = inode(self.root, H.LOCK)
        self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")
        self.assertEqual(inode(self.root, H.LOCK), before_ino)

    def _swapped(self, op, nth):
        m, plan = self.planned(with_lock=False)

        def swap():
            H.put(self.root, "copy-of-tmp", H.raw(self.root, H.TMP_H))        # the same bytes in a new inode
            os.replace(os.path.join(self.root, "copy-of-tmp"), os.path.join(self.root, H.TMP_H))
        ops = H.C4Ops().add(op, "tmp", nth=nth, before=swap)
        e = self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_plan_stale", "store", "scan")
        self.assertEqual(ops.ops("rename"), [])
        self.assertIn(H.TMP_H, os.listdir(self.root))

    def test_the_inode_changes_between_the_listing_and_the_rename(self):
        # the 2nd lstat of the temporary file is the one right before the rename: only the inode comparison of the move
        # sees a same-bytes file in a new inode there
        self._swapped("lstat", 2)

    def test_the_inode_changes_while_the_file_is_being_read(self):
        # the swap between the lstat and the read of the same call: the read's own before/after comparison sees it
        self._swapped("read_file", 2)

    def test_changed_bytes_in_the_same_inode(self):
        m, plan = self.planned()
        data = H.raw(self.root, H.TMP_H)
        H.put(self.root, H.TMP_H, b"X" + data[1:])
        self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")

    def test_read_only(self):
        m, plan = self.planned()
        self.assertErr(self.refused(self.maint(writable=False), plan), "store_read_only", "store", "args")

    def test_a_directory_in_place_of_a_target(self):
        m, plan = self.planned()
        os.unlink(os.path.join(self.root, H.TMP_S))
        os.mkdir(os.path.join(self.root, H.TMP_S))
        self.assertErr(self.refused(m, plan), "maintenance_plan_stale", "store", "scan")

    def test_plans_of_the_wrong_type_shape_or_hash(self):
        m, plan = self.planned()
        body = plan.body
        errs = []
        for bad in (None, plan.to_dict(), "plan", 5, object()):
            errs.append(self.refused(m, bad, plan.plan_hash))
        for e in errs:
            self.assertErr(e, "maintenance_plan_invalid", "plan", "args", "type")

        def forged(mutate):
            b = plan.body
            mutate(b)
            return UnlockPlan._make(b)
        shapes = [
            lambda b: b.__setitem__("operation", "x"),
            lambda b: b.__setitem__("writers_stopped", 1),
            lambda b: b.__setitem__("request_id", "no good"),
            lambda b: b.__setitem__("targets", []),
            lambda b: b.__setitem__("extra", 1),
            lambda b: b["targets"][0].__setitem__("name", "history.json"),
            lambda b: b["targets"][0].__setitem__("name", "../" + H.TMP_H),
            lambda b: b["targets"][0].__setitem__("name", H.LOCK),
            lambda b: b["targets"][-1].__setitem__("name", H.TMP_H2),
            lambda b: b["targets"][0].__setitem__("kind", "lock"),
            lambda b: b["targets"][0].__setitem__("raw_sha256", "short"),
            lambda b: b["targets"][0].__setitem__("raw_size", -1),
            lambda b: b["targets"][0].__setitem__("st_ino", True),
            lambda b: b["targets"][0].__setitem__("st_ino", "1"),
            lambda b: b["targets"][0].pop("st_dev"),
            lambda b: b["targets"].reverse(),
            lambda b: b["targets"].append(dict(b["targets"][0])),
            lambda b: b["targets"].insert(0, dict(b["targets"][-1])),
        ]
        for mutate in shapes:
            p = forged(mutate)
            e = self.refused(m, p, p.plan_hash)
            self.assertErr(e, "maintenance_plan_invalid", "plan", "args", "shape")
        wrong_hash = UnlockPlan._wrap({"body": body, "plan_hash": "0" * 64}, lambda rule: Exception(rule))
        self.assertErr(self.refused(m, wrong_hash, "0" * 64), "maintenance_plan_invalid", "plan", "args", "plan_hash")
        wrong_hash2 = UnlockPlan._wrap({"body": body, "plan_hash": "xyz"}, lambda rule: Exception(rule))
        self.assertErr(self.refused(m, wrong_hash2, "xyz"), "maintenance_plan_invalid", "plan", "args", "plan_hash")

    def test_the_stale_plan_leaves_no_quarantine_and_no_lock(self):
        m, plan = self.planned(with_lock=False)
        H.put(self.root, H.TMP_H2, b"new")
        e = self.refused(m, plan)
        self.assertEqual(e.code, "maintenance_plan_stale")
        self.assertNotIn(H.QUAR, os.listdir(self.root))
        self.assertNotIn(H.LOCK, os.listdir(self.root))


class Interrupted(H.RootCase):
    def plan_with(self, with_lock):
        H.lock_and_tmps(self.root, lock=H.LOCK_C3 if with_lock else None, tmps=((H.TMP_H, b"a"), (H.TMP_H2, b"b"),
                                                                              (H.TMP_S, b"c")))
        m = self.maint()
        return M.plan_unlock(m.inspect(), "u-1", True)

    def test_a_fault_at_each_rename_then_the_same_plan_moves_the_rest(self):
        for with_lock, count in ((True, 4), (False, 3)):
            for nth in range(1, count + 1):
                for after in (False, True):
                    with self.subTest(lock=with_lock, nth=nth, after=after):
                        for n in list(os.listdir(self.root)):
                            p = os.path.join(self.root, n)
                            if os.path.isdir(p):
                                import shutil
                                shutil.rmtree(p)
                            else:
                                os.unlink(p)
                        plan = self.plan_with(with_lock)
                        originals = {t["name"]: None for t in plan.targets}
                        ops = H.C4Ops().fail("rename", None, nth=nth, after=after)
                        e = self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
                        self.assertErr(e, "maintenance_incomplete", "quarantine", "move", primary="store_io_error")
                        self.assertNotIn(H.SECRET, str(e) + repr(e.__dict__))
                        res = self.maint().unlock(plan, plan.plan_hash)
                        self.assertEqual((res.status, res.resumed), (M.UNLOCKED, True))
                        self.assertEqual(H.listing(self.root), ["quarantine"])
                        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "quarantine", plan.plan_hash))),
                                         sorted(list(originals) + ["MANIFEST"]))

    def test_the_resume_moves_only_what_is_left(self):
        plan = self.plan_with(True)
        ops = H.C4Ops().fail("rename", None, nth=3)
        self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.LOCK, H.TMP_S, "quarantine"]))
        ops2 = H.C4Ops()
        self.maint(ops2).unlock(plan, plan.plan_hash)
        self.assertEqual([k for (op, k) in ops2.trace if op == "rename"], ["s2tmp", "lock"])

    def test_a_key_directory_with_a_name_that_does_not_belong_is_refused(self):
        plan = self.plan_with(True)
        ops = H.C4Ops().fail("rename", None, nth=2)
        self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        H.put(self.root, os.path.join("quarantine", plan.plan_hash, "history.json"), b"alien")
        before = H.tree(self.root)
        e = self.run_err(self.maint().unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "quarantine", "entries")
        self.assertEqual(H.tree(self.root), before)

    def test_a_manifest_that_changed_by_one_byte_is_refused(self):
        plan = self.plan_with(False)
        ops = H.C4Ops().fail("rename", None, nth=2)
        self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        path = os.path.join(self.root, "quarantine", plan.plan_hash, "MANIFEST")
        data = bytearray(H.qraw(self.root, plan.plan_hash, "MANIFEST"))
        data[-3] ^= 1
        H.put(self.root, os.path.join("quarantine", plan.plan_hash, "MANIFEST"), bytes(data))
        before = H.tree(self.root)
        e = self.run_err(self.maint().unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "manifest", "manifest")
        self.assertEqual(H.tree(self.root), before)

    def test_a_set_aside_file_with_other_bytes_makes_the_plan_stale(self):
        plan = self.plan_with(True)
        ops = H.C4Ops().fail("rename", None, nth=2)
        self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        H.put(self.root, os.path.join("quarantine", plan.plan_hash, H.TMP_H), b"other")
        e = self.run_err(self.maint().unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_plan_stale", "store", "scan")

    def test_a_quarantine_that_is_a_link_or_a_file_is_refused_before_anything_moves(self):
        plan = self.plan_with(True)
        H.put(self.root, H.QUAR, b"file")
        before = H.tree(self.root)
        e = self.run_err(self.maint().unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "quarantine", "type")
        self.assertEqual(H.tree(self.root), before)

    def test_a_quarantine_on_another_device_is_refused(self):
        plan = self.plan_with(True)
        ops = H.C4Ops()
        real = ops.lstat

        class Moved(object):
            def __init__(self, st):
                self._st = st

            def __getattr__(self, n):
                return self._st.st_dev + 1 if n == "st_dev" else getattr(self._st, n)

        def lstat(path):
            st = real(path)
            return Moved(st) if os.path.basename(path) == "quarantine" else st
        ops.lstat = lstat
        os.mkdir(os.path.join(self.root, "quarantine"))
        e = self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "quarantine", "type")
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.LOCK, H.TMP_H, H.TMP_H2, H.TMP_S, "quarantine"]))

    def test_the_c4_lock_left_by_an_unlock_is_in_the_next_plan_and_the_old_key_stays(self):
        plan = self.plan_with(False)
        ops = H.C4Ops().fail("unlink", "lock")
        e = self.run_err(self.maint(ops).unlock, plan, plan.plan_hash)
        self.assertErr(e, "maintenance_incomplete", "lock", "lock_release", cleanup=("lock_left",))
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.LOCK, "quarantine"]))
        e2 = self.run_err(self.maint().unlock, plan, plan.plan_hash)
        self.assertErr(e2, "maintenance_plan_stale")
        plan2 = M.plan_unlock(self.maint().inspect(), "u-2", True)
        self.assertEqual([t["name"] for t in plan2.targets], [H.LOCK])
        self.maint().unlock(plan2, plan2.plan_hash)
        self.assertEqual(sorted(os.listdir(self.root)), ["quarantine"])
        self.assertEqual(H.keys(self.root), sorted([plan.plan_hash, plan2.plan_hash]))


class LeftoversWithoutWords(H.RootCase):
    """C-3's implementation review P-02: create_exclusive reports a failure after it created the file, so the error has
    no clean-up word and the file is still there. C-4 finds it from the directory listing."""

    def test_a_temporary_file_that_the_error_does_not_mention(self):
        c = H.C2.day_case()
        self.put_history(c.current)
        ops = H.C3.C3Ops().add("create_exclusive", "tmp", after=H.injected())
        e = self.run_err(self.c3(ops).publish, c.pub)
        self.assertEqual((e.code, tuple(e.cleanup)), ("store_io_error", ()))
        leftovers = [n for n in os.listdir(self.root) if n.startswith(".history.")]
        self.assertEqual(len(leftovers), 1)
        e2 = self.run_err(self.c3().publish, c.pub)
        self.assertEqual(e2.code, "store_artifact_present")
        report = self.maint().inspect()
        self.assertEqual([a["name"] for a in report.artifacts], leftovers)
        plan = M.plan_unlock(report, "u-1", True)
        self.maint().unlock(plan, plan.plan_hash)
        self.assertEqual(self.c3().publish(c.pub).status, "PUBLISHED")
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))

    def test_a_lock_that_the_error_does_not_mention(self):
        c = H.C2.day_case()
        self.put_history(c.current)
        ops = H.C3.C3Ops().add("create_exclusive", "lock", after=H.injected())
        e = self.run_err(self.c3(ops).publish, c.pub)
        self.assertEqual((e.code, tuple(e.cleanup)), ("store_busy", ()))
        self.assertEqual(self.run_err(self.c3().publish, c.pub).code, "store_busy")
        report = self.maint().inspect()
        self.assertEqual([(a["name"], a["owner"], a["raw_size"]) for a in report.artifacts], [(H.LOCK, "EMPTY", 0)])
        plan = M.plan_unlock(report, "u-1", True)
        self.maint().unlock(plan, plan.plan_hash)
        self.assertEqual(self.c3().publish(c.pub).status, "PUBLISHED")


if __name__ == "__main__":
    unittest.main()
