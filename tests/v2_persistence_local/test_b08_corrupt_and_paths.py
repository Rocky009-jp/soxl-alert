"""B-08: missing / corrupt files and unsafe paths are refused; nothing outside the managed names is changed."""
import json
import os
import stat
import tempfile
import unittest

import l_helpers as H
from v2_persistence.codec import encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.local import LocalFileStore, LocalStoreError


class Corrupt(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc, advance=3)
        self.good = H.raw(self.root)
        self.snap = LocalFileStore(self.root).read()
        d = self.sc.day(4)
        self.sc.observe(d, 52)
        self.plan = self.sc.prepare(self.snap, d).plan

    def mutated(self, fn):
        data = json.loads(self.good.decode("utf-8"))
        fn(data)
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def refuse(self, data, code, rule=None):
        H.put(self.root, H.SNAP, data)
        before = H.state_of(self.root)
        st = LocalFileStore(self.root, writable=True)
        for call in (st.read, lambda: st.commit(self.plan), lambda: st.initialize(self.sc.genesis)):
            with self.assertRaises(PersistenceError) as cm:
                call()
            e = cm.exception
            if call is not st.read and code == "snapshot_invalid" and e.code == "already_initialized":
                continue
            self.assertEqual(e.code, code)
            if rule is not None:
                self.assertEqual(e.rule, rule)
        self.assertEqual(H.state_of(self.root), before)             # not repaired, not rewritten
        self.assertEqual(H.listing(self.root), [H.SNAP])            # lock released every time

    def test_empty_and_truncated(self):
        self.refuse(b"", "snapshot_invalid", "json")
        self.refuse(self.good[:len(self.good) // 2], "snapshot_invalid", "json")
        self.refuse(self.good[:-1], "snapshot_invalid", "json")

    def test_not_utf8(self):
        self.refuse(b"\xff\xfe" + self.good, "snapshot_invalid", "utf8")
        self.refuse(self.good[:10] + b"\xc3\x28" + self.good[10:], "snapshot_invalid", "utf8")

    def test_bom_is_not_accepted(self):
        self.refuse(b"\xef\xbb\xbf" + self.good, "snapshot_invalid", "json")

    def test_duplicate_keys(self):
        text = self.good.decode("utf-8")
        dup = text[:-1] + ',"head_seq":99}'
        self.refuse(dup.encode("utf-8"), "snapshot_invalid", "json")

    def test_non_finite_and_not_an_object(self):
        text = self.good.decode("utf-8").replace('"head_seq":3', '"head_seq":NaN')
        self.refuse(text.encode("utf-8"), "snapshot_invalid", "json")
        self.refuse(b"[]", "snapshot_invalid")
        self.refuse(b"null", "snapshot_invalid")

    def test_huge_integer_text(self):
        text = self.good.decode("utf-8").replace('"head_seq":3', '"head_seq":' + "9" * 5000)
        self.refuse(text.encode("utf-8"), "snapshot_invalid")

    def test_hash_violations(self):
        self.refuse(self.mutated(lambda d: d.update(head_hash="0" * 64)), "snapshot_invalid", "head_hash")
        self.refuse(self.mutated(lambda d: d["events"][1].update(event_hash="0" * 64)), "snapshot_invalid")
        self.refuse(self.mutated(lambda d: d["events"][2].update(parent_hash="0" * 64)), "snapshot_invalid")

    def test_state_violations(self):
        self.refuse(self.mutated(lambda d: d["current_state"].update(as_of_d="2000-01-01")), "snapshot_invalid",
                    "current_state")
        self.refuse(self.mutated(lambda d: d.update(head_seq=1)), "snapshot_invalid", "head_seq")
        self.refuse(self.mutated(lambda d: d["events"].pop(1)), "snapshot_invalid")

    def test_schema_and_core_sha(self):
        self.refuse(self.mutated(lambda d: d.update(schema_version=2)), "unsupported_schema")
        self.refuse(self.mutated(lambda d: d.update(core_sha="0" * 40)), "unsupported_schema")
        self.refuse(self.mutated(lambda d: d["events"][1].update(kind="REWRITE")), "unsupported_event")

    def test_missing_file(self):
        os.unlink(os.path.join(self.root, H.SNAP))
        st = LocalFileStore(self.root, writable=True)
        with self.assertRaises(LocalStoreError) as cm:
            st.read()
        self.assertCode(cm.exception, "store_uninitialized", "store")
        self.assertEqual(H.listing(self.root), [])

    def test_leftover_tmp_is_never_promoted(self):
        os.unlink(os.path.join(self.root, H.SNAP))
        H.put(self.root, ".snapshot.abcdef.tmp", self.good)
        st = LocalFileStore(self.root, writable=True)
        for call in (st.read, lambda: st.commit(self.plan), lambda: st.initialize(self.sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_artifact_present", "store")
        self.assertEqual(H.listing(self.root), [".snapshot.abcdef.tmp"])
        self.assertEqual(H.raw(self.root, ".snapshot.abcdef.tmp"), self.good)

    def test_leftover_tmp_next_to_a_good_file(self):
        H.put(self.root, ".snapshot.fedcba.tmp", b"half")
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root).read()
        self.assertCode(cm.exception, "store_artifact_present", "store")
        self.assertEqual(H.raw(self.root), self.good)
        self.assertEqual(H.raw(self.root, ".snapshot.fedcba.tmp"), b"half")

    def test_unrelated_files_do_not_matter_and_stay(self):
        H.put(self.root, "notes.txt", b"mine")
        os.mkdir(os.path.join(self.root, "sub"))
        self.assertEqual(LocalFileStore(self.root, writable=True).commit(self.plan).snapshot.head_seq, 4)
        self.assertEqual(H.raw(self.root, "notes.txt"), b"mine")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "sub")))


class Paths(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        self.outside = tempfile.mkdtemp(prefix="v2s2_outside_")
        self.addCleanup(__import__("shutil").rmtree, self.outside, True)

    def outside_state(self):
        return {n: H.raw(self.outside, n) for n in sorted(os.listdir(self.outside))}

    def test_snapshot_symlink_to_outside(self):
        sc = self.sc
        outside_root = tempfile.mkdtemp(prefix="v2s2_src_")
        self.addCleanup(__import__("shutil").rmtree, outside_root, True)
        H.init_root(outside_root, sc, advance=1)
        target = os.path.join(outside_root, H.SNAP)
        os.symlink(target, os.path.join(self.root, H.SNAP))
        before = H.raw(outside_root)
        mtime = os.stat(target).st_mtime_ns
        d = sc.day(2)
        sc.observe(d, 50)
        plan = sc.prepare(LocalFileStore(outside_root).read(), d).plan
        st = LocalFileStore(self.root, writable=True)
        for call in (st.read, lambda: st.commit(plan), lambda: st.initialize(sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_root_invalid", "root")
        self.assertEqual(H.raw(outside_root), before)
        self.assertEqual(os.stat(target).st_mtime_ns, mtime)
        self.assertTrue(os.path.islink(os.path.join(self.root, H.SNAP)))
        self.assertEqual(H.listing(outside_root), [H.SNAP])

    def test_snapshot_is_a_directory_or_special_file(self):
        os.mkdir(os.path.join(self.root, H.SNAP))
        st = LocalFileStore(self.root, writable=True)
        for call in (st.read, lambda: st.initialize(self.sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_root_invalid", "root")
        os.rmdir(os.path.join(self.root, H.SNAP))
        os.mkfifo(os.path.join(self.root, H.SNAP))                     # opening it would block: it is refused first
        for call in (st.read, lambda: st.initialize(self.sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_root_invalid", "root")
        self.assertTrue(stat.S_ISFIFO(os.lstat(os.path.join(self.root, H.SNAP)).st_mode))
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_lock_that_is_a_symlink_is_busy_and_the_target_is_untouched(self):
        victim = os.path.join(self.outside, "victim.txt")
        H.put(self.outside, "victim.txt", b"keep")
        os.symlink(victim, os.path.join(self.root, H.LOCK))
        for call in (lambda: LocalFileStore(self.root, writable=True).read(),
                     lambda: LocalFileStore(self.root, writable=True).initialize(self.sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_busy", "lock")
        self.assertEqual(self.outside_state(), {"victim.txt": b"keep"})
        self.assertTrue(os.path.islink(os.path.join(self.root, H.LOCK)))

    def test_dangling_lock_symlink_is_busy_and_nothing_is_created_outside(self):
        target = os.path.join(self.outside, "not_yet")
        os.symlink(target, os.path.join(self.root, H.LOCK))
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True).initialize(self.sc.genesis)
        self.assertCode(cm.exception, "store_busy", "lock")
        self.assertEqual(os.listdir(self.outside), [])

    def test_lock_that_is_a_directory(self):
        os.mkdir(os.path.join(self.root, H.LOCK))
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True).read()
        self.assertCode(cm.exception, "store_busy", "lock")
        self.assertTrue(os.path.isdir(os.path.join(self.root, H.LOCK)))

    def test_tmp_symlink_leftover_is_an_artifact_and_not_followed(self):
        victim = os.path.join(self.outside, "victim.txt")
        H.put(self.outside, "victim.txt", b"keep")
        os.symlink(victim, os.path.join(self.root, ".snapshot.zzz.tmp"))
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root, writable=True).initialize(self.sc.genesis)
        self.assertCode(cm.exception, "store_artifact_present", "store")
        self.assertEqual(self.outside_state(), {"victim.txt": b"keep"})

    def test_root_replaced_by_a_link_after_construction(self):
        st = LocalFileStore(self.root, writable=True)
        gone = self.root + "_moved"
        os.rename(self.root, gone)
        self.addCleanup(__import__("shutil").rmtree, gone, True)
        os.symlink(self.outside, self.root)
        try:
            with self.assertRaises(LocalStoreError) as cm:
                st.initialize(self.sc.genesis)
            self.assertCode(cm.exception, "store_root_invalid", "root")
            self.assertEqual(os.listdir(self.outside), [])
        finally:
            os.unlink(self.root)
            os.rename(gone, self.root)

    def test_lock_swapped_for_foreign_file_is_not_deleted(self):
        # the ownership tests with injected swaps are in B-05; here the whole path through a real process
        sc = self.sc
        H.init_root(self.root, sc, advance=1)
        d = sc.day(2)
        sc.observe(d, 50)
        plan = sc.prepare(LocalFileStore(self.root).read(), d).plan
        self.snapshot_bytes_before = H.raw(self.root)
        w = H.Worker({"mode": "commit", "root": self.root, "plan": H.plan_to_json(plan),
                      "hook": {"point": "after_tmp_close", "action": "pause"}})
        self.addCleanup(w.kill)
        w.expect("AT")
        os.unlink(os.path.join(self.root, H.LOCK))                      # a third party takes the lock's place
        H.put(self.root, H.LOCK, b"third party\n")
        w.send("CONTINUE")
        r = w.result()
        self.assertEqual((r["ok"], r["code"], r["field"], r["phase"]), (False, "store_lock_ownership_lost", "lock",
                                                                        "lock_ownership"))
        self.assertEqual(H.raw(self.root, H.LOCK), b"third party\n")
        self.assertEqual([n for n in H.listing(self.root) if n.endswith(".tmp")], [])      # its own tmp was removed
        self.assertEqual(H.raw(self.root), self.snapshot_bytes_before)


if __name__ == "__main__":
    unittest.main()
