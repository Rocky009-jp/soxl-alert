"""C4-03 inspect and C4-04 the pure plan of an unlock."""
import hashlib
import json
import os
import unittest

import c4_helpers as H
import v2_history_maintain as M
from v2_history_ops.values import digest_of


def ident(root, name):
    """The expected identity of a file, from hashlib and os.lstat (not from the package)."""
    p = os.path.join(root, name)
    st = os.lstat(p)
    data = H.raw(root, name)
    return {"raw_sha256": hashlib.sha256(data).hexdigest(), "raw_size": len(data), "st_dev": st.st_dev,
            "st_ino": st.st_ino}


class Inspect(H.RootCase):
    def test_an_empty_root(self):
        r = self.maint().inspect()
        self.assertEqual((r.layout, r.history, r.v1, r.artifacts), (M_EMPTY, None, None, []))
        self.assertEqual(r.quarantine, {"state": "absent", "keys": []})

    def test_v2_v1_only_and_both(self):
        case = H.migration()
        self.put_v1(case)
        r = self.maint().inspect()
        self.assertEqual((r.layout, r.history), ("V1_ONLY", None))
        self.assertEqual({k: r.v1[k] for k in ("raw_sha256", "raw_size", "regular")},
                         {"raw_sha256": H.sha(case.data), "raw_size": len(case.data), "regular": True})
        self.put_history(case.candidate_bytes)
        r = self.maint().inspect()
        self.assertEqual(r.layout, "V1_AND_V2")
        self.assertTrue(r.history["readable"])
        os.unlink(os.path.join(self.root, H.V1))
        r = self.maint().inspect()
        self.assertEqual(r.layout, "V2")
        self.assertEqual(r.history["raw_sha256"], H.sha(case.candidate_bytes))

    def test_a_history_file_that_cannot_be_read_is_reported_not_raised(self):
        self.put_history(b"{not json")
        r = self.maint().inspect()
        self.assertEqual((r.layout, r.history["regular"], r.history["readable"]), ("V2", True, False))
        self.put_history(b"\xff\xfe")
        self.assertFalse(self.maint().inspect().history["readable"])

    def test_the_lock_owner_kinds(self):
        for data, owner in ((H.LOCK_S2, "S2"), (H.LOCK_C3, "C3"), (H.LOCK_C4, "C4"), (b"", "EMPTY"),
                            (b"somebody else\n", "UNKNOWN"), (b"v2_history_maintain.lock", "UNKNOWN")):
            H.put(self.root, H.LOCK, data)
            arts = self.maint().inspect().artifacts
            self.assertEqual(len(arts), 1)
            exp = ident(self.root, H.LOCK)
            self.assertEqual(arts[0], dict(exp, name=H.LOCK, kind="lock", owner=owner, regular=True))

    def test_temporary_files_have_the_identity_of_the_file_system(self):
        H.lock_and_tmps(self.root)
        arts = self.maint().inspect().artifacts
        self.assertEqual([a["name"] for a in arts], [H.TMP_H, H.TMP_S, H.LOCK])
        for a in arts:
            exp = ident(self.root, a["name"])
            self.assertEqual({k: a[k] for k in exp}, exp)
        self.assertEqual([a["owner"] for a in arts], ["C3", "S2", "C3"])
        self.assertEqual([a["kind"] for a in arts], ["tmp", "tmp", "lock"])

    def test_names_that_only_look_like_temporary_files_are_not_matched(self):
        for name in ("history.json.bak", ".history.tmp.x", "snapshot.json.tmp", "notes", ".snapshot"):
            H.put(self.root, name, b"x")
        self.assertEqual(self.maint().inspect().artifacts, [])

    def test_the_c3_loose_rule_is_the_same(self):
        # C-3 refuses with store_artifact_present on any name with the prefix and the suffix
        H.put(self.root, ".history.zzz.tmp", b"x")
        self.assertEqual([a["name"] for a in self.maint().inspect().artifacts], [".history.zzz.tmp"])
        e = self.run_err(self.c3().read)
        self.assertErr(e, "store_artifact_present")

    def test_a_directory_lock_is_reported_with_regular_false(self):
        os.mkdir(os.path.join(self.root, H.LOCK))
        a = self.maint().inspect().artifacts[0]
        self.assertEqual((a["name"], a["regular"], a["raw_sha256"], a["st_ino"], a["owner"]),
                         (H.LOCK, False, None, None, None))

    def test_it_works_with_a_lock_present_creates_no_lock_and_changes_nothing(self):
        case = H.migration()
        self.put_v1(case)
        H.lock_and_tmps(self.root, lock=H.LOCK_C4)
        before = H.tree(self.root)
        ops = H.C4Ops()
        self.maint(ops).inspect()
        self.assertEqual(H.tree(self.root), before)
        self.assertEqual(ops.ops("create_exclusive", "unlink", "replace", "rename", "mkdir", "create_exclusive:lock"),
                         [])

    def test_the_quarantine_summary(self):
        case = H.migration()
        self.put_v1(case)
        self.maint().migrate(case.pub, True)
        q = self.maint().inspect().quarantine
        self.assertEqual(q["state"], "dir")
        self.assertEqual(q["keys"], [{"key": case.key, "state": "dir", "manifest_state": "valid",
                                      "manifest": {"operation": "MIGRATION", "request_id": "mig-1",
                                                   "targets": ["snapshot.json"]},
                                      "entries": ["MANIFEST", "snapshot.json"]}])

    def test_odd_quarantines_are_reported_as_they_are(self):
        os.mkdir(os.path.join(self.root, H.QUAR))
        key = "a" * 64
        os.mkdir(os.path.join(self.root, H.QUAR, key))
        os.mkdir(os.path.join(self.root, H.QUAR, "not-a-key"))
        H.put(self.root, os.path.join(H.QUAR, key, "MANIFEST"), b"{}")
        q = self.maint().inspect().quarantine
        self.assertEqual([k["key"] for k in q["keys"]], [key])
        self.assertEqual((q["keys"][0]["manifest_state"], q["keys"][0]["manifest"]), ("invalid", None))
        os.rename(os.path.join(self.root, H.QUAR), os.path.join(self.root, "q2"))
        H.put(self.root, H.QUAR, b"a file")
        self.assertEqual(self.maint().inspect().quarantine["state"], "invalid")

    def test_a_listing_failure_is_store_io_error_without_the_secret(self):
        ops = H.C4Ops().fail("listdir", "root")
        e = self.run_err(self.maint(ops).inspect)
        self.assertErr(e, "store_io_error", "root", "scan")
        self.assertNotIn(H.SECRET, str(e) + repr(e.__dict__))


M_EMPTY = "EMPTY"


class Plan(H.RootCase):
    def report(self, **kw):
        H.lock_and_tmps(self.root, **kw)
        return self.maint().inspect()

    def test_the_declaration_must_be_exactly_true(self):
        r = self.report()
        for bad in (False, None, 1, "yes", "True", 0, [], {}, 1.0):
            e = self.run_err(M.plan_unlock, r, "u-1", bad)
            self.assertErr(e, "maintenance_declaration_missing", "writers_stopped", "args")
        self.assertIsNotNone(M.plan_unlock(r, "u-1", True))

    def test_other_bad_arguments(self):
        r = self.report()
        for bad in (None, "", "has space", "a" * 300, 5, b"u-1"):
            self.assertErr(self.run_err(M.plan_unlock, r, bad, True), "maintenance_plan_invalid", "plan", "args",
                           "request_id")
        for bad in (None, {}, r.to_dict(), "report", 3):
            self.assertErr(self.run_err(M.plan_unlock, bad, "u-1", True), "maintenance_plan_invalid", "plan", "args",
                           "report_type")

    def test_nothing_to_unlock_and_targets_that_are_not_files(self):
        r = self.maint().inspect()
        self.assertErr(self.run_err(M.plan_unlock, r, "u-1", True), "maintenance_nothing_to_unlock", "store", "args")
        os.mkdir(os.path.join(self.root, H.LOCK))
        self.assertErr(self.run_err(M.plan_unlock, self.maint().inspect(), "u-1", True),
                       "maintenance_target_unsupported", "store", "args")
        os.rmdir(os.path.join(self.root, H.LOCK))
        os.mkdir(os.path.join(self.root, H.TMP_H))
        self.assertErr(self.run_err(M.plan_unlock, self.maint().inspect(), "u-1", True),
                       "maintenance_target_unsupported", "store", "args")

    def test_the_declaration_is_judged_before_the_report(self):
        e = self.run_err(M.plan_unlock, None, "x y", False)
        self.assertEqual(e.code, "maintenance_declaration_missing")

    def test_the_order_of_the_targets_tmp_files_by_name_and_the_lock_last(self):
        H.put(self.root, H.TMP_H2, b"2")
        r = self.report()
        plan = M.plan_unlock(r, "u-1", True)
        self.assertEqual([(t["name"], t["kind"]) for t in plan.targets],
                         [(H.TMP_H, "tmp"), (H.TMP_H2, "tmp"), (H.TMP_S, "tmp"), (H.LOCK, "lock")])
        r2 = self.maint().inspect()
        plan2 = M.plan_unlock(r2, "u-1", True)
        self.assertEqual(plan2, plan)

    def test_the_hash_is_the_digest_of_the_body_and_is_stable(self):
        r = self.report()
        plan = M.plan_unlock(r, "u-1", True)
        body = {"operation": "soxl-v2-maintenance-unlock/1", "request_id": "u-1", "writers_stopped": True,
                "targets": [dict(name=a["name"], kind=a["kind"], raw_sha256=a["raw_sha256"], raw_size=a["raw_size"],
                                 st_dev=a["st_dev"], st_ino=a["st_ino"]) for a in r.artifacts]}
        self.assertEqual(plan.body, body)
        expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=True).encode("ascii")).hexdigest()
        self.assertEqual(plan.plan_hash, expected)
        self.assertEqual(plan.plan_hash, digest_of(body))
        self.assertEqual(M.plan_unlock(r, "u-1", True).plan_hash, plan.plan_hash)
        self.assertNotEqual(M.plan_unlock(r, "u-2", True).plan_hash, plan.plan_hash)
        self.assertEqual((plan.request_id, plan.writers_stopped), ("u-1", True))

    def test_a_different_file_system_state_gives_another_hash(self):
        r = self.report()
        h1 = M.plan_unlock(r, "u-1", True).plan_hash
        H.put(self.root, H.TMP_H, b"changed bytes")
        h2 = M.plan_unlock(self.maint().inspect(), "u-1", True).plan_hash
        self.assertNotEqual(h1, h2)

    def test_it_is_pure_it_reads_and_writes_nothing(self):
        r = self.report()
        before = H.tree(self.root)
        M.plan_unlock(r, "u-1", True)
        self.assertEqual(H.tree(self.root), before)


if __name__ == "__main__":
    unittest.main()
