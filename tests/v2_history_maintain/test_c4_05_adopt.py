"""C4-11 the prefix adoption, C4-12 its resumption (C-2's hand-over, review N-01), C4-13 the evidence that is set aside."""
import os
import unittest

import c4_helpers as H
import v2_history_maintain as M
import v2_history_publish as U


def manifest_of(case):
    return H.manifest_expected("ADOPTION", case.key, case.request_id, case.plan_hash, case.key, False,
                               [("history.json", "history", H.sha(case.data), len(case.data))])


class Adopt(H.RootCase):
    def test_an_adoption(self):
        case = H.adoption()
        self.put_history(case.data)
        res = self.maint().adopt(case.pub)
        self.assertEqual((res.status, res.key, res.resumed), (M.ADOPTED, case.key, False))
        self.assertEqual(res.history, case.candidate)
        self.assertEqual(H.listing(self.root), ["history.json", "quarantine"])
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.qnames(self.root, case.key), ["MANIFEST", "history.json"])
        self.assertEqual(H.qraw(self.root, case.key, "history.json"), case.data)
        self.assertEqual(H.qraw(self.root, case.key, "MANIFEST"), manifest_of(case))
        self.assertEqual(self.c3().read(), case.candidate)

    def test_the_original_is_copied_and_the_file_never_goes_missing(self):
        case = H.adoption()
        self.put_history(case.data)
        ops = H.C4Ops()
        self.maint(ops).adopt(case.pub)
        self.assertEqual([k for (op, k) in ops.trace if op == "unlink"], ["lock"])
        self.assertEqual([(op, k) for (op, k) in ops.trace if op in ("replace", "rename")],
                         [("replace", "manifest"), ("replace", "qfile"), ("replace", "history")])

    def test_after_completion_the_current_bytes_give_no_change_and_a_rerun_is_resumed(self):
        case = H.adoption()
        self.put_history(case.data)
        self.maint().adopt(case.pub)
        e = H.C2.refusal(U.publish_adoption, case.plan, case.plan.plan_hash, H.raw(self.root))
        self.assertEqual((e.code, e.rule), ("publication_refused", "no_change"))
        res = self.maint().adopt(case.pub)
        self.assertEqual((res.status, res.resumed, res.history), (M.ADOPTED, True, case.candidate))

    def refused(self, pub, setup):
        setup()
        before = H.tree(self.root)
        e = self.run_err(self.maint().adopt, pub)
        self.assertEqual(H.tree(self.root), before)
        return e

    def test_refusals_leave_the_root_as_it_was(self):
        case = H.adoption()
        e = self.refused(case.pub, lambda: (self.put_history(case.data), self.put_v1(H.migration())))
        self.assertErr(e, "store_layout_unsupported", "store", "scan", "v1_and_v2")
        os.unlink(os.path.join(self.root, H.V1))
        e = self.refused(case.pub, lambda: self.put_history(case.data + b" "))
        self.assertErr(e, "publication_stale", rule="raw")
        self.put_history(case.data)                                      # the right bytes again; other publications:
        for make in (H.C2.migration_case, H.C2.genesis_case, H.C2.day_case):
            e = self.run_err(self.maint().adopt, make().pub)
            self.assertErr(e, "store_operation_unsupported", "publication", "args", "not_adoption")
        os.unlink(os.path.join(self.root, H.HIST))
        e = self.run_err(self.maint().adopt, case.pub)
        self.assertErr(e, "store_uninitialized", "store", "read")
        for name in (H.TMP_H, H.TMP_S):
            self.put_history(case.data)
            H.put(self.root, name, b"left")
            before = H.tree(self.root)
            e = self.run_err(self.maint().adopt, case.pub)
            self.assertErr(e, "store_artifact_present", "store", "scan")
            self.assertEqual(H.tree(self.root), before)
            os.unlink(os.path.join(self.root, name))

    def test_a_v1_file_alone_is_the_unsupported_layout(self):
        self.put_v1(H.migration())
        e = self.run_err(self.maint().adopt, H.adoption().pub)
        self.assertErr(e, "store_layout_unsupported", "store", "scan", "v1_only")

    def test_no_stop_declaration_is_asked_for(self):
        import inspect
        self.assertEqual(list(inspect.signature(M.HistoryMaintenance.adopt).parameters), ["self", "publication"])


class Resume(H.RootCase):
    def adopted_with(self, ops, case=None):
        case = case or H.adoption()
        self.put_history(case.data)
        return case, self.run_err(self.maint(ops).adopt, case.pub)

    def test_a_failed_release_then_unlock_then_a_publication_made_again_from_the_set_aside_bytes(self):
        case, e = self.adopted_with(H.C4Ops().fail("unlink", "lock"))
        self.assertErr(e, "store_commit_uncertain", "history", "lock_release", cleanup=("lock_left",))
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        m = self.maint()
        self.assertEqual(self.run_err(m.adopt, case.pub).code, "store_busy")
        self.unlock_all(m)
        original = m.read_set_aside(case.key, H.HIST)
        self.assertEqual(original, case.data)
        again = H.rebuild_adoption(case, original)
        self.assertEqual(again.publication_hash, case.key)
        ops = H.C4Ops()
        res = self.maint(ops).adopt(again)
        self.assertEqual((res.status, res.resumed), (M.ADOPTED, True))
        self.assertEqual(ops.ops("replace", "create_exclusive:tmp", "create_exclusive:qtmp"), [])
        self.assertEqual(self.c3().read(), case.candidate)

    def test_a_failed_directory_sync_after_the_replace_is_commit_uncertain_and_resumes(self):
        ops = H.C4Ops().fail("fsync_dir", "root", nth=2)
        case, e = self.adopted_with(ops)
        self.assertErr(e, "store_commit_uncertain", "history", "dir_sync")
        self.assertEqual(H.raw(self.root), case.candidate_bytes)
        self.assertEqual(H.listing(self.root), ["history.json", "quarantine"])
        again = H.rebuild_adoption(case, self.maint().read_set_aside(case.key, H.HIST))
        res = self.maint().adopt(again)
        self.assertEqual((res.status, res.resumed), (M.ADOPTED, True))

    def test_a_failed_replace_of_the_copy_leaves_the_original_and_the_same_call_completes(self):
        for op, kind, nth, phase in (("replace", "qfile", 1, "copy"), ("write", "qtmp", 2, "copy"),
                                     ("fsync_file", "qtmp", 2, "copy"), ("create_exclusive", "qtmp", 2, "copy"),
                                     ("replace", "manifest", 1, "manifest")):
            with self.subTest(op=op, kind=kind):
                self.root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, self.root, True)
                case, e = self.adopted_with(H.C4Ops().fail(op, kind, nth=nth))
                self.assertErr(e, "maintenance_incomplete", "quarantine", phase, primary="store_io_error")
                self.assertEqual(H.raw(self.root), case.data)
                res = self.maint().adopt(case.pub)
                self.assertEqual((res.status, res.resumed), (M.ADOPTED, True))
                self.assertEqual(H.raw(self.root), case.candidate_bytes)
                self.assertEqual(H.qraw(self.root, case.key, "history.json"), case.data)

    def test_a_copy_that_reads_back_differently_stops_before_the_replace(self):
        case = H.adoption()
        self.put_history(case.data)

        def wrapped(real, path):
            data, st = real(path)
            return data[:-1] + b"?", st
        ops = H.C4Ops().add("read_file", "qfile", wrap=wrapped)
        e = self.run_err(self.maint(ops).adopt, case.pub)
        self.assertErr(e, "maintenance_copy_mismatch", "quarantine", "copy")
        self.assertEqual(H.raw(self.root), case.data)
        self.assertEqual(sorted(os.listdir(self.root)), sorted(["history.json", "quarantine"]))
        self.assertEqual(ops.ops("replace:history"), [])

    def test_another_requested_at_gives_another_hash_and_stops_without_changing_the_root(self):
        case, _e = self.adopted_with(H.C4Ops().fail("unlink", "lock"))
        self.unlock_all()
        other = H.adoption(when=H.WHEN2)
        self.assertNotEqual(other.key, case.key)
        before = H.tree(self.root)
        e = self.run_err(self.maint().adopt, other.pub)
        self.assertErr(e, "publication_stale", rule="raw")
        self.assertEqual(H.tree(self.root), before)

    def test_the_requested_at_can_be_read_back_from_the_adoption_record(self):
        # review Q-01 for an adoption: the requested_at of the RECOVERY_PREFIX_ADOPTION record of history.json
        import json
        from datetime import datetime
        case, _e = self.adopted_with(H.C4Ops().fail("unlink", "lock"))
        self.unlock_all()
        events = json.loads(self.maint().read_original(H.HIST).decode("utf-8"))["events"]
        marks = [ev["requested_at"] for ev in events if ev["kind"] == "RECOVERY_PREFIX_ADOPTION"]
        self.assertEqual(len(marks), 1)
        when = datetime.fromisoformat(marks[0].replace("Z", "+00:00"))
        self.assertEqual(when, H.WHEN)
        original = self.maint().read_set_aside(case.key, H.HIST)
        self.assertEqual(H.rebuild_adoption(case, original, when=when).publication_hash, case.key)

    def test_a_tampered_copy_makes_the_finished_state_unrecognised(self):
        case = H.adoption()
        self.put_history(case.data)
        self.maint().adopt(case.pub)
        path = os.path.join(self.root, "quarantine", case.key, "history.json")
        H.put(self.root, os.path.join("quarantine", case.key, "history.json"), case.data + b"!")
        before = H.tree(self.root)
        e = self.run_err(self.maint().adopt, case.pub)
        self.assertErr(e, "publication_stale", rule="raw")
        self.assertEqual(H.tree(self.root), before)

    def test_a_history_file_that_is_not_the_candidate_is_not_a_finished_adoption(self):
        other = H.C2.day_case().current
        case = H.adoption()
        self.put_history(case.data)
        self.maint().adopt(case.pub)                      # finished: the copy and the MANIFEST are right
        H.put(self.root, H.HIST, other)                   # but history.json is now neither the original nor the candidate
        before = H.tree(self.root)
        e = self.run_err(self.maint().adopt, case.pub)
        self.assertErr(e, "publication_stale", rule="raw")
        self.assertEqual(H.tree(self.root), before)

    def test_a_key_directory_with_a_foreign_name_stops_the_first_run(self):
        case = H.adoption()
        self.put_history(case.data)
        os.makedirs(os.path.join(self.root, "quarantine", case.key))
        H.put(self.root, os.path.join("quarantine", case.key, "snapshot.json"), b"alien")
        before = H.tree(self.root)
        e = self.run_err(self.maint().adopt, case.pub)
        self.assertErr(e, "maintenance_quarantine_invalid", "quarantine", "quarantine", "entries")
        self.assertEqual(H.tree(self.root), before)


class Evidence(H.RootCase):
    def test_the_manifest_identity_is_the_hash_of_the_bytes_read_under_the_lock(self):
        for case, put in ((H.migration(), "v1"), (H.adoption(), "history")):
            self.root = H.make_root()
            self.addCleanup(__import__("shutil").rmtree, self.root, True)
            if put == "v1":
                self.put_v1(case)
                self.maint().migrate(case.pub, True)
                name = H.V1
            else:
                self.put_history(case.data)
                self.maint().adopt(case.pub)
                name = H.HIST
            import json
            manifest = json.loads(H.qraw(self.root, case.key, "MANIFEST"))
            self.assertEqual(manifest["targets"][0]["raw_sha256"], H.sha(case.data))
            self.assertEqual(manifest["targets"][0]["raw_size"], len(case.data))
            self.assertEqual(H.sha(H.qraw(self.root, case.key, name)), manifest["targets"][0]["raw_sha256"])
            body = case.pub.body
            ident = body["source_v1"] if put == "v1" else body["expected"]
            self.assertEqual(manifest["targets"][0]["raw_sha256"], ident["raw_sha256"])

    def order_and_tamper(self, case, put, call, name_kind, make):
        put()
        ops = H.C4Ops()
        call(self.maint(ops))
        trace = ops.trace
        read_at = trace.index(("read_file", name_kind))
        first_change = min(i for i, (op, k) in enumerate(trace) if op in ("mkdir", "rename")
                           or (op == "create_exclusive" and k in ("qtmp", "tmp")))
        self.assertLess(read_at, first_change)
        manifest_at = trace.index(("replace", "manifest"))
        self.assertLess(read_at, manifest_at)
        # the read under the lock returns other bytes: the publication does not match them, nothing is set aside
        self.root = H.make_root()
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        put()

        def other(real, path):
            data, st = real(path)
            return data + b"\n", st
        ops2 = H.C4Ops().add("read_file", name_kind, wrap=other)
        before = H.tree(self.root)
        e = self.run_err(call, self.maint(ops2))
        self.assertEqual(e.code, "publication_stale")
        self.assertEqual(H.tree(self.root), before)
        self.assertEqual(ops2.ops("mkdir", "replace:manifest", "rename"), [])

    def test_the_manifest_is_written_only_after_the_bytes_read_under_the_lock_were_checked_migration(self):
        case = H.migration()
        self.order_and_tamper(case, lambda: self.put_v1(case), lambda m: m.migrate(case.pub, True), "snapshot", None)

    def test_the_manifest_is_written_only_after_the_bytes_read_under_the_lock_were_checked_adoption(self):
        case = H.adoption()
        self.order_and_tamper(case, lambda: self.put_history(case.data), lambda m: m.adopt(case.pub), "history", None)

    def set_aside(self):
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)
        return case

    def test_read_set_aside_returns_the_bytes_only_when_they_match_the_manifest(self):
        case = self.set_aside()
        m = self.maint()
        self.assertEqual(m.read_set_aside(case.key, H.V1), case.data)
        path = os.path.join(self.root, "quarantine", case.key, H.V1)
        H.put(self.root, os.path.join("quarantine", case.key, H.V1), case.data[:-1] + b"!")
        self.assertErr(self.run_err(m.read_set_aside, case.key, H.V1), "maintenance_set_aside_mismatch", "quarantine",
                       "read")

    def test_names_and_keys_that_the_manifest_does_not_know(self):
        case = self.set_aside()
        m = self.maint()
        for name in (H.HIST, H.LOCK, H.TMP_H):
            self.assertErr(self.run_err(m.read_set_aside, case.key, name), "maintenance_quarantine_invalid",
                           "quarantine", "read", "target")
        self.assertErr(self.run_err(m.read_set_aside, "0" * 64, H.V1), "maintenance_quarantine_invalid", "quarantine",
                       "quarantine", "missing")

    def test_a_missing_set_aside_file_and_a_broken_manifest(self):
        case = self.set_aside()
        m = self.maint()
        path = os.path.join(self.root, "quarantine", case.key, H.V1)
        os.rename(path, path + ".away")
        e = self.run_err(m.read_set_aside, case.key, H.V1)
        self.assertEqual(e.code, "maintenance_quarantine_invalid")      # the name that does not belong, first
        os.rename(path + ".away", path)
        mpath = os.path.join(self.root, "quarantine", case.key, "MANIFEST")
        H.put(self.root, os.path.join("quarantine", case.key, "MANIFEST"), b"{}")
        self.assertErr(self.run_err(m.read_set_aside, case.key, H.V1), "maintenance_quarantine_invalid", "quarantine",
                       "read", "manifest")

    def test_read_original_and_read_set_aside_take_the_lock(self):
        case = self.set_aside()
        H.put(self.root, H.LOCK, H.LOCK_C3)
        m = self.maint()
        self.assertEqual(self.run_err(m.read_original, H.HIST).code, "store_busy")
        self.assertEqual(self.run_err(m.read_set_aside, case.key, H.V1).code, "store_busy")


if __name__ == "__main__":
    unittest.main()
