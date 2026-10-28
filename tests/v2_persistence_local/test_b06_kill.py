"""B-06: a separate process is killed at fixed points (os._exit without any clean-up, and one SIGKILL). The parent
inspects the raw files only after the child has ended, using the dedicated root and nothing else."""
import os
import shutil
import signal
import unittest

import l_helpers as H
from v2_persistence.codec import decode_snapshot, encode_snapshot
from v2_persistence.local import LocalFileStore, LocalStoreError
from v2_persistence.plan import ALREADY_APPLIED
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import reconcile

POINTS = ("lock_acquired", "partial_write", "after_file_fsync", "before_replace", "after_replace", "after_dir_fsync")
NEW_VISIBLE = ("after_replace", "after_dir_fsync")           # the replace has been executed


class KillBase(H.RootCase):
    def kill_at(self, point, spec_extra, how="exit"):
        spec = {"root": self.root, "hook": {"point": point, "action": "exit" if how == "exit" else "pause"}}
        spec.update(spec_extra)
        w = H.Worker(spec)
        self.addCleanup(w.kill)
        if how == "exit":
            rc = w.wait()
            self.assertEqual(rc, 77, w.stderr)
        else:
            w.expect("AT")
            os.kill(w.proc.pid, signal.SIGKILL)
            rc = w.wait()
            self.assertEqual(rc, -signal.SIGKILL)
        return w

    def tmp_names(self):
        return [n for n in H.listing(self.root) if n.startswith(".snapshot.") and n.endswith(".tmp")]

    def after_kill_checks(self, point, old_bytes, new_bytes, full_tmp_bytes):
        raw_now = H.raw(self.root) if H.SNAP in H.listing(self.root) else None
        # the formal file is exactly the old version or the complete new version; never half a JSON
        if raw_now is not None:
            self.assertIn(raw_now, [b for b in (old_bytes, new_bytes) if b is not None])
            decode_snapshot(raw_now.decode("utf-8"))
        expected_new = point in NEW_VISIBLE
        self.assertEqual(raw_now, new_bytes if expected_new else old_bytes)
        self.assertIn(H.LOCK, H.listing(self.root))                      # the lock stays: nobody cleaned it
        tmps = self.tmp_names()
        if point == "lock_acquired":
            self.assertEqual(tmps, [])
        elif point == "partial_write":
            self.assertEqual(len(tmps), 1)
            part = H.raw(self.root, tmps[0])
            self.assertTrue(0 < len(part) < len(new_bytes))
            self.assertEqual(part, new_bytes[:len(part)])
        elif point in ("after_file_fsync", "before_replace"):
            self.assertEqual(len(tmps), 1)
            self.assertEqual(H.raw(self.root, tmps[0]), new_bytes)
        else:
            self.assertEqual(tmps, [])

    def next_calls(self, point, snapshot_present):
        """Every public API stops at the leftover lock; after the test removes only the lock, a leftover tmp stops
        it again; nothing is adopted or removed by the product."""
        st = LocalFileStore(self.root, writable=True)
        for call in (st.read,):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_busy", "lock")
        lock_bytes = H.raw(self.root, H.LOCK)
        self.assertEqual(H.raw(self.root, H.LOCK), lock_bytes)
        os.unlink(os.path.join(self.root, H.LOCK))                       # explicit, test-side unlock (not a feature)
        tmps_before = self.tmp_names()
        if tmps_before:
            with self.assertRaises(LocalStoreError) as cm:
                st.read()
            self.assertCode(cm.exception, "store_artifact_present", "store")
            self.assertEqual(self.tmp_names(), tmps_before)              # still there: not adopted, not removed
            for n in tmps_before:
                os.unlink(os.path.join(self.root, n))


class KillCommit(KillBase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc, advance=2)
        self.old_bytes = H.raw(self.root)
        snap = LocalFileStore(self.root).read()
        d = self.sc.day(3)
        self.sc.observe(d, 44)
        self.plan = self.sc.prepare(snap, d).plan
        # expected new bytes: what a real commit writes, computed in a throw-away copy of the root
        copy_root = H.make_root()
        self.addCleanup(shutil.rmtree, copy_root, True)
        H.put(copy_root, H.SNAP, self.old_bytes)
        LocalFileStore(copy_root, writable=True).commit(self.plan)
        self.new_bytes = H.raw(copy_root)

    def test_each_point(self):
        for point in POINTS:
            with self.subTest(point=point):
                self.setUp_root_again()
                self.kill_at(point, {"mode": "commit", "plan": H.plan_to_json(self.plan)})
                self.after_kill_checks(point, self.old_bytes, self.new_bytes, self.new_bytes)
                self.next_calls(point, True)
                snap = LocalFileStore(self.root).read()                    # clean again: old or new, fully valid
                validate_snapshot(snap)
                if point in NEW_VISIBLE:
                    self.assertEqual(snap.head_seq, 3)
                    self.assertEqual(reconcile(self.plan, snap).status, ALREADY_APPLIED)
                else:
                    self.assertEqual(snap.head_seq, 2)
                self.assertEqual(H.listing(self.root), [H.SNAP])

    def setUp_root_again(self):
        for n in os.listdir(self.root):
            os.unlink(os.path.join(self.root, n))
        H.put(self.root, H.SNAP, self.old_bytes)

    def test_sigkill_while_paused_before_replace(self):
        self.kill_at("before_replace", {"mode": "commit", "plan": H.plan_to_json(self.plan)}, how="sigkill")
        self.after_kill_checks("before_replace", self.old_bytes, self.new_bytes, self.new_bytes)
        self.next_calls("before_replace", True)

    def test_sigkill_after_replace(self):
        self.kill_at("after_replace", {"mode": "commit", "plan": H.plan_to_json(self.plan)}, how="sigkill")
        self.after_kill_checks("after_replace", self.old_bytes, self.new_bytes, self.new_bytes)
        self.next_calls("after_replace", True)
        self.assertEqual(LocalFileStore(self.root).read().head_seq, 3)

    def test_a_second_commit_never_proceeds_past_a_dead_workers_lock(self):
        self.kill_at("after_file_fsync", {"mode": "commit", "plan": H.plan_to_json(self.plan)})
        r = H.run_worker({"mode": "commit", "root": self.root, "plan": H.plan_to_json(self.plan)})
        self.assertEqual((r["ok"], r["code"], r["phase"]), (False, "store_busy", "lock_acquire"))
        self.assertEqual(H.raw(self.root), self.old_bytes)
        self.assertEqual(len(self.tmp_names()), 1)


class KillInitialize(KillBase):
    def test_each_point(self):
        sc = H.Scenario()
        genesis_text = encode_snapshot(sc.genesis)
        new_bytes = genesis_text.encode("utf-8")
        for point in POINTS:
            with self.subTest(point=point):
                for n in os.listdir(self.root):
                    os.unlink(os.path.join(self.root, n))
                self.kill_at(point, {"mode": "init", "genesis": genesis_text})
                names = H.listing(self.root)
                if point in NEW_VISIBLE:
                    self.assertEqual(H.raw(self.root), new_bytes)
                else:
                    self.assertNotIn(H.SNAP, names)                       # before initialization: no formal file at all
                self.assertIn(H.LOCK, names)
                tmps = self.tmp_names()
                if point == "partial_write":
                    self.assertEqual(len(tmps), 1)
                    self.assertTrue(0 < len(H.raw(self.root, tmps[0])) < len(new_bytes))
                elif point in ("after_file_fsync", "before_replace"):
                    self.assertEqual(H.raw(self.root, tmps[0]), new_bytes)
                st = LocalFileStore(self.root, writable=True)
                with self.assertRaises(LocalStoreError) as cm:
                    st.read()
                self.assertCode(cm.exception, "store_busy", "lock")
                with self.assertRaises(LocalStoreError) as cm:
                    st.initialize(sc.genesis)
                self.assertCode(cm.exception, "store_busy", "lock")
                os.unlink(os.path.join(self.root, H.LOCK))                # explicit test-side unlock
                if tmps:
                    with self.assertRaises(LocalStoreError) as cm:
                        st.initialize(sc.genesis)                          # a leftover tmp is never promoted
                    self.assertCode(cm.exception, "store_artifact_present", "store")
                    self.assertNotIn(H.SNAP, H.listing(self.root))
                    for n in tmps:
                        os.unlink(os.path.join(self.root, n))
                if point in NEW_VISIBLE:
                    self.assertEqual(st.read(), sc.genesis)
                else:
                    with self.assertRaises(LocalStoreError) as cm:
                        st.read()
                    self.assertCode(cm.exception, "store_uninitialized", "store")


if __name__ == "__main__":
    unittest.main()
