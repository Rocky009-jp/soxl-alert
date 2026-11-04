"""C4-09 the v1 -> v2 migration, C4-10 its resumption (design 5.2, 5.4, review N-01)."""
import os
import unittest

import c4_helpers as H
import v2_history_maintain as M
import v2_history_publish as U


def manifest_of(case):
    return H.manifest_expected("MIGRATION", case.key, case.request_id, case.plan_hash, case.key, True,
                               [("snapshot.json", "v1", H.sha(case.data), len(case.data))])


class Migrate(H.RootCase):
    def test_a_migration(self):
        case = H.migration()
        self.put_v1(case)
        res = self.maint().migrate(case.pub, True)
        self.assertEqual((res.status, res.key, res.resumed), (M.MIGRATED, case.key, False))
        self.assertEqual(res.history, case.candidate)
        self.assertEqual(H.listing(self.root), ["history.json", "quarantine"])
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.keys(self.root), [case.key])
        self.assertEqual(H.qnames(self.root, case.key), ["MANIFEST", "snapshot.json"])
        self.assertEqual(H.qraw(self.root, case.key, "snapshot.json"), case.data)
        self.assertEqual(H.qraw(self.root, case.key, "MANIFEST"), manifest_of(case))
        self.assertEqual(self.c3().read(), case.candidate)

    def test_the_snapshot_is_renamed_not_copied(self):
        case = H.migration()
        self.put_v1(case)
        ino = os.lstat(os.path.join(self.root, H.V1)).st_ino
        self.maint().migrate(case.pub, True)
        self.assertEqual(os.lstat(os.path.join(self.root, "quarantine", case.key, H.V1)).st_ino, ino)

    def refused(self, pub, writers_stopped=True, setup=None):
        case = H.migration()
        if setup is None:
            self.put_v1(case)
        else:
            setup(case)
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, pub, writers_stopped)
        self.assertEqual(H.tree(self.root), before)
        return e

    def test_no_declaration(self):
        case = H.migration()
        for bad in (False, None, 1, "yes", 0):
            self.assertErr(self.refused(case.pub, bad), "maintenance_declaration_missing", "writers_stopped", "args")

    def test_other_kinds_of_publication(self):
        for make in (H.C2.genesis_case, H.C2.adoption_case, H.C2.day_case, H.C2.resolution_case):
            self.assertErr(self.refused(make().pub), "store_operation_unsupported", "publication", "args",
                           "not_migration")

    def test_a_v1_file_with_other_bytes(self):
        case = H.migration()
        e = self.refused(case.pub, setup=lambda c: H.put(self.root, H.V1, c.data + b" "))
        self.assertErr(e, "publication_stale", rule="source_v1")
        self.assertNotIn(H.QUAR, os.listdir(self.root))

    def test_no_v1_and_no_history(self):
        e = self.refused(H.migration().pub, setup=lambda c: None)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "empty")

    def test_somebody_elses_history_file(self):
        other = H.C2.day_case().current
        e = self.refused(H.migration().pub, setup=lambda c: H.put(self.root, H.HIST, other))
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
        case = H.migration()

        def both(c):
            self.put_v1(c)
            H.put(self.root, H.HIST, other)
        self.root = H.make_root()
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        e = self.refused(case.pub, setup=both)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v1_and_v2")

    def test_temporary_files(self):
        for name in (H.TMP_H, H.TMP_S):
            def setup(c, name=name):
                self.put_v1(c)
                H.put(self.root, name, b"left")
            e = self.refused(H.migration().pub, setup=setup)
            self.assertErr(e, "store_artifact_present", "store", "scan")
            for n in os.listdir(self.root):
                os.unlink(os.path.join(self.root, n))

    def test_a_foreign_lock_stops_it(self):
        case = H.migration()
        self.put_v1(case)
        H.put(self.root, H.LOCK, H.LOCK_C3)
        before = H.tree(self.root)
        self.assertErr(self.run_err(self.maint().migrate, case.pub, True), "store_busy", "lock", "lock_acquire")
        self.assertEqual(H.tree(self.root), before)

    def test_a_hand_made_publication_is_not_accepted(self):
        case = H.migration()
        self.put_v1(case)
        body = case.pub.body
        body["candidate_history"]["events"][0] = {"seq": 0}
        forged = U.HistoryPublication._make(body)
        e = self.run_err(self.maint().migrate, forged, True)
        self.assertIn(e.code, ("publication_invalid", "store_candidate_invalid"))
        self.assertEqual(H.listing(self.root), [H.V1])


class Resume(H.RootCase):
    def interrupted_at_rename(self):
        case = H.migration()
        self.put_v1(case)
        ops = H.C4Ops().fail("rename", "snapshot")
        e = self.run_err(self.maint(ops).migrate, case.pub, True)
        return case, e

    def test_a_failed_rename_leaves_both_files_and_c3_refuses_the_root(self):
        case, e = self.interrupted_at_rename()
        self.assertErr(e, "maintenance_incomplete", "quarantine", "move", primary="store_io_error")
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.HIST, H.V1, "quarantine"]))
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.raw(self.root, H.V1), case.data)
        e2 = self.run_err(self.c3().read)
        self.assertErr(e2, "store_layout_unsupported", "store", "scan", "v1_and_v2")
        e3 = self.run_err(self.c3().publish, H.C2.day_case().pub)
        self.assertEqual(e3.code, "store_layout_unsupported")

    def test_resume_from_both_with_a_publication_made_again_from_the_original_bytes(self):
        case, _e = self.interrupted_at_rename()
        m = self.maint()
        self.assertIsNone(self.unlock_all(m))                   # nothing left: the lock was released
        data = m.read_original(H.V1)
        again = H.rebuild_migration(case, data)
        self.assertEqual(again.publication_hash, case.key)
        ops = H.C4Ops()
        res = self.maint(ops).migrate(again, True)
        self.assertEqual((res.status, res.resumed, res.key), (M.MIGRATED, True, case.key))
        self.assertEqual(ops.ops("replace", "create_exclusive:tmp"), [])      # history.json is not written again
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.HIST, "quarantine"]))
        self.assertEqual(H.qraw(self.root, case.key, H.V1), case.data)
        self.assertEqual(self.c3().read(), case.candidate)

    def test_a_failed_release_leaves_the_c4_lock_then_unlock_then_resume_from_the_set_aside_bytes(self):
        case = H.migration()
        self.put_v1(case)
        ops = H.C4Ops().fail("unlink", "lock")
        e = self.run_err(self.maint(ops).migrate, case.pub, True)
        self.assertErr(e, "store_commit_uncertain", "history", "lock_release", cleanup=("lock_left",))
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.HIST, H.LOCK, "quarantine"]))
        self.assertEqual(self.run_err(self.maint().migrate, case.pub, True).code, "store_busy")
        m = self.maint()
        report = m.inspect()
        self.assertEqual([(a["name"], a["owner"]) for a in report.artifacts], [(H.LOCK, "C4")])
        self.assertEqual([(k["key"], k["manifest"]["operation"], k["manifest"]["request_id"])
                          for k in report.quarantine["keys"]], [(case.key, "MIGRATION", "mig-1")])
        self.unlock_all(m)
        data = m.read_set_aside(case.key, H.V1)
        self.assertEqual(data, case.data)
        again = H.rebuild_migration(case, data)
        ops2 = H.C4Ops()
        res = self.maint(ops2).migrate(again, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(ops2.ops("replace", "create_exclusive:tmp", "rename", "mkdir"), [])
        self.assertEqual(self.c3().read(), case.candidate)

    def test_a_rerun_after_completion_and_after_a_daily_publication_of_c3(self):
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)
        res = self.maint().migrate(case.pub, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(res.history, case.candidate)
        # C-3 appends a day (history.json now holds the candidate and more)
        full = H.C2.migration_case()
        self.assertEqual(full.pub.publication_hash, case.key)
        longer = H.C2.extended_history(full)
        H.put(self.root, H.HIST, H.C2.file_bytes(longer))
        res = self.maint().migrate(case.pub, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(res.history, longer)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(longer))

    def test_another_requested_at_gives_another_hash_and_stops_without_changing_the_root(self):
        case = H.migration()
        other = H.migration(when=H.WHEN2)
        self.assertNotEqual(other.key, case.key)
        # (1) the state "both"
        self.put_v1(case)
        self.run_err(self.maint(H.C4Ops().fail("rename", "snapshot")).migrate, case.pub, True)
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, other.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v1_and_v2")
        self.assertEqual(H.tree(self.root), before)
        # (2) the state "history.json only"
        self.maint().migrate(case.pub, True)
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, other.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
        self.assertEqual(H.tree(self.root), before)

    def test_the_requested_at_can_be_read_back_from_the_candidate_record(self):
        # review Q-01: the place is the requested_at of the SCHEMA_MIGRATION record of history.json (an ISO 8601 text that
        # ends in Z); datetime.fromisoformat needs +00:00 in place of the Z (Python 3.10 does not read the Z)
        import json
        from datetime import datetime
        case, _e = self.interrupted_at_rename()
        self.assertEqual(self.maint().inspect().layout, "V1_AND_V2")
        events = json.loads(self.maint().read_original(H.HIST).decode("utf-8"))["events"]
        marks = [ev["requested_at"] for ev in events if ev["kind"] == "SCHEMA_MIGRATION"]
        self.assertEqual(len(marks), 1)
        self.assertTrue(marks[0].endswith("Z"))
        when = datetime.fromisoformat(marks[0].replace("Z", "+00:00"))
        self.assertEqual(when, H.WHEN)
        again = H.rebuild_migration(case, self.maint().read_original(H.V1), when=when)
        self.assertEqual(again.publication_hash, case.key)

    def test_a_tampered_quarantine_stops_the_resume(self):
        case, _e = self.interrupted_at_rename()
        path = os.path.join(self.root, "quarantine", case.key, "MANIFEST")
        data = bytearray(H.qraw(self.root, case.key, "MANIFEST"))
        data[-5] ^= 1
        H.put(self.root, os.path.join("quarantine", case.key, "MANIFEST"), bytes(data))
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, case.pub, True)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "manifest")
        self.assertEqual(H.tree(self.root), before)

    def test_a_history_file_that_is_not_the_candidate_stops_the_resume_even_with_a_valid_quarantine(self):
        other = H.C2.day_case().current
        case, _e = self.interrupted_at_rename()           # both files, the MANIFEST and the key directory are right
        H.put(self.root, H.HIST, other)
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, case.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v1_and_v2")
        self.assertEqual(H.tree(self.root), before)
        self.assertEqual(H.raw(self.root, H.V1), case.data)

    def test_a_history_file_that_is_not_the_candidate_is_not_a_completed_migration(self):
        other = H.C2.day_case().current
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)               # complete: the set-aside copy and the MANIFEST are right
        H.put(self.root, H.HIST, other)
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, case.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
        self.assertEqual(H.tree(self.root), before)

    def test_a_snapshot_with_other_bytes_stops_the_resume_before_any_move(self):
        case, _e = self.interrupted_at_rename()
        H.put(self.root, H.V1, case.data + b" ")
        before = H.tree(self.root)
        ops = H.C4Ops()
        e = self.run_err(self.maint(ops).migrate, case.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v1_and_v2")   # seen at the scan, not at the move
        self.assertEqual(ops.ops("rename"), [])
        self.assertEqual(H.tree(self.root), before)

    # review N-01: history.json is in the listing but is not found when it is read under the lock (lstat or read_file
    # answers FileNotFoundError): a fixed word, never a TypeError, the root unchanged; after the rename of snapshot.json it
    # is "not shown to be complete"
    def _history_gone(self, op, nth, completed):
        if completed:
            case = H.migration()
            self.put_v1(case)
            self.maint().migrate(case.pub, True)
        else:
            case, _e = self.interrupted_at_rename()
        before = H.tree(self.root)
        ops = H.C4Ops().fail(op, "history", exc=FileNotFoundError("gone"), nth=nth)
        e = self.run_err(self.maint(ops).migrate, case.pub, True)
        return case, e, before

    def test_history_not_found_under_the_lock_while_both_files_are_there(self):
        for op in ("lstat", "read_file"):
            with self.subTest(op=op):
                self.setUp()
                case, e, before = self._history_gone(op, 1, False)
                self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v1_and_v2")
                self.assertEqual(H.tree(self.root), before)

    def test_history_not_found_under_the_lock_in_the_completed_state(self):
        for op in ("lstat", "read_file"):
            with self.subTest(op=op):
                self.setUp()
                case, e, before = self._history_gone(op, 1, True)
                self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
                self.assertEqual(H.tree(self.root), before)

    def test_history_not_found_when_it_is_read_again_after_the_rename(self):
        for op in ("lstat", "read_file"):
            with self.subTest(op=op):
                self.setUp()
                case, e, _before = self._history_gone(op, 2, False)
                self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
                self.assertEqual(sorted(os.listdir(self.root)), sorted([H.HIST, "quarantine"]))   # the rename was done
                self.assertEqual(H.qraw(self.root, case.key, H.V1), case.data)
                self.assertEqual(self.maint().migrate(case.pub, True).status, M.MIGRATED)          # the same call completes

    def test_history_not_found_when_it_is_read_again_in_the_completed_state(self):
        for op in ("lstat", "read_file"):
            with self.subTest(op=op):
                self.setUp()
                case, e, before = self._history_gone(op, 2, True)
                self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
                self.assertEqual(H.tree(self.root), before)

    def test_a_missing_set_aside_copy_stops_the_completed_state_from_being_recognised(self):
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)
        os.unlink(os.path.join(self.root, "quarantine", case.key, H.V1))
        before = H.tree(self.root)
        e = self.run_err(self.maint().migrate, case.pub, True)
        self.assertErr(e, "maintenance_state_unexpected", "store", "scan", "v2_present")
        self.assertEqual(H.tree(self.root), before)

    def test_a_first_run_after_a_failure_before_the_publication_starts_from_the_set_aside_directory(self):
        case = H.migration()
        self.put_v1(case)
        ops = H.C4Ops().fail("create_exclusive", "tmp")
        e = self.run_err(self.maint(ops).migrate, case.pub, True)
        self.assertEqual(e.code, "store_io_error")
        self.assertEqual(sorted(os.listdir(self.root)), sorted([H.V1, "quarantine"]))
        res = self.maint().migrate(case.pub, True)
        self.assertEqual((res.status, res.resumed), (M.MIGRATED, True))
        self.assertEqual(self.c3().read(), case.candidate)


if __name__ == "__main__":
    unittest.main()
