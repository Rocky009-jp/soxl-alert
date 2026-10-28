"""B-01 compatibility with S1, B-02 read / initialize, B-03 ordinary update and re-run (real files)."""
import copy
import dataclasses
import json
import os
import subprocess
import sys
import unittest

import l_helpers as H
from v2_persistence import codec
from v2_persistence.codec import decode_snapshot, encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.local import (COMMITTED, FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, INITIALIZED, LocalCommitResult,
                                  LocalFileStore, LocalStoreError)
from v2_persistence.plan import ALREADY_APPLIED, NO_COMMIT, PREPARED, REPLAN_REQUIRED
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import MemoryStore, reconcile


class B01Compat(H.RootCase):
    def test_constants_unchanged(self):
        self.assertEqual(codec.SCHEMA_VERSION, 1)
        self.assertEqual(codec.CORE_SHA, "b616b4ec7169420e199ec7e247dd375b3603a013")

    def test_file_bytes_are_the_s1_encoding_and_round_trip(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=5)
        snap = st.read()
        self.assertEqual(H.raw(self.root), encode_snapshot(snap).encode("utf-8"))
        again = decode_snapshot(H.raw(self.root).decode("utf-8"))
        self.assertEqual(again, snap)
        self.assertEqual(again.to_dict(), snap.to_dict())
        validate_snapshot(again)                       # the S1 full recompute accepts the stored file
        self.assertEqual(snap.schema_version, 1)
        self.assertEqual(snap.core_sha, codec.CORE_SHA)

    def test_chain_equals_memory_store_chain(self):
        """The same plans through MemoryStore and through the file give identical Snapshots and current states."""
        sc = H.Scenario()
        mem = MemoryStore()
        mem.initialize(sc.genesis)
        fs = H.init_root(self.root, sc)
        for i in range(1, 9):
            d = sc.day(i)
            sc.observe(d, 30 + i)
            pm = sc.prepare(mem.read(), d)
            pf = sc.prepare(fs.read(), d)
            self.assertEqual(pm.status, PREPARED)
            self.assertEqual(pm.plan, pf.plan)
            mem.commit(pm.plan)
            fs.commit(pf.plan)
            self.assertEqual(mem.read(), fs.read())
        self.assertEqual(mem.read().current_state, fs.read().current_state)
        self.assertEqual(fs.read().head_seq, 8)

    def test_new_instance_reads_the_same_snapshot(self):
        sc = H.Scenario()
        a = H.init_root(self.root, sc, advance=4)
        b = LocalFileStore(self.root)
        self.assertEqual(a.read(), b.read())


class B02ReadInit(H.RootCase):
    def test_uninitialized_read_and_commit(self):
        sc = H.Scenario()
        st = self.store()
        with self.assertRaises(LocalStoreError) as cm:
            st.read()
        self.assertCode(cm.exception, "store_uninitialized", "store")
        mem = MemoryStore()
        mem.initialize(sc.genesis)
        sc.observe(sc.day(1), 50)
        plan = sc.prepare(mem.read(), sc.day(1)).plan
        with self.assertRaises(LocalStoreError) as cm:
            st.commit(plan)
        self.assertCode(cm.exception, "store_uninitialized", "store")
        self.assertEqual(H.listing(self.root), [])                 # no initialization, no leftovers

    def test_explicit_initialize_one_genesis(self):
        sc = H.Scenario()
        st = self.store()
        res = st.initialize(sc.genesis)
        self.assertEqual((res.status, res.initialized, res.persistence_level), (INITIALIZED, True,
                                                                               FILE_AND_DIRECTORY_SYNC))
        self.assertEqual(H.listing(self.root), [H.SNAP])
        snap = LocalFileStore(self.root).read()
        self.assertEqual(snap, sc.genesis)
        self.assertEqual(len(snap.events), 1)
        self.assertEqual(snap.events[0]["kind"], "GENESIS")

    def test_read_from_independent_process(self):
        sc = H.Scenario()
        H.init_root(self.root, sc, advance=2)
        res = H.run_worker({"mode": "read", "root": self.root})
        snap = self.store().read()
        self.assertEqual((res["head_seq"], res["head_hash"]), (snap.head_seq, snap.head_hash))
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_double_initialize_rejected_without_change(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=2)
        before = H.state_of(self.root)
        with self.assertRaises(LocalStoreError) as cm:
            st.initialize(sc.genesis)
        self.assertCode(cm.exception, "already_initialized", "store")
        self.assertEqual(H.state_of(self.root), before)

    def test_initialize_with_apply_rejected(self):
        sc = H.Scenario()
        mem = MemoryStore()
        mem.initialize(sc.genesis)
        sc.observe(sc.day(1), 50)
        mem.commit(sc.prepare(mem.read(), sc.day(1)).plan)
        with self.assertRaises(PersistenceError) as cm:
            self.store().initialize(mem.read())
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "initialize_not_genesis_only"))
        self.assertEqual(H.listing(self.root), [])

    def test_default_is_read_only_and_never_changes_the_file(self):
        sc = H.Scenario()
        H.init_root(self.root, sc, advance=1)
        ro = LocalFileStore(self.root)                            # defaults: writable=False, strict
        self.assertFalse(ro.writable)
        before = H.state_of(self.root)
        sc.observe(sc.day(2), 50)
        plan = sc.prepare(ro.read(), sc.day(2)).plan
        for call in (lambda: ro.commit(plan), lambda: ro.initialize(sc.genesis)):
            with self.assertRaises(LocalStoreError) as cm:
                call()
            self.assertCode(cm.exception, "store_read_only", "store")
        self.assertEqual(H.state_of(self.root), before)
        ro.read()
        self.assertEqual(H.listing(self.root), [H.SNAP])           # the lock taken for read is gone again

    def test_read_takes_and_releases_the_lock(self):
        sc = H.Scenario()
        H.init_root(self.root, sc)
        ops = H.FaultOps()
        LocalFileStore(self.root, _ops=ops).read()
        self.assertEqual(ops.ops("create_exclusive:lock", "unlink:lock"), ["create_exclusive:lock", "unlink:lock"])
        self.assertEqual(H.listing(self.root), [H.SNAP])

    def test_configuration_errors(self):
        for kw, field in (({"writable": 1}, "writable"), ({"writable": None}, "writable"),
                          ({"durability": "fast"}, "durability"), ({"durability": None}, "durability")):
            with self.assertRaises(LocalStoreError) as cm:
                LocalFileStore(self.root, **kw)
            self.assertCode(cm.exception, "store_config_invalid", field)

    def test_invalid_roots_and_no_auto_create(self):
        missing = os.path.join(self.root, "nope")
        for bad in (missing, "relative/dir", "", None, 5, b"/tmp", os.path.join(self.root, "a\0b")):
            with self.assertRaises(LocalStoreError) as cm:
                LocalFileStore(bad)
            self.assertCode(cm.exception, "store_root_invalid", "root")
        self.assertFalse(os.path.exists(missing))
        f = os.path.join(self.root, "file")
        H.put(self.root, "file", b"x")
        with self.assertRaises(LocalStoreError):
            LocalFileStore(f)
        link = os.path.join(self.root, "lnk")
        os.mkdir(os.path.join(self.root, "real"))
        os.symlink(os.path.join(self.root, "real"), link)
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(link)
        self.assertCode(cm.exception, "store_root_invalid", "root")

    def test_non_plan_argument(self):
        st = self.store()
        with self.assertRaises(PersistenceError) as cm:
            st.commit("not a plan")
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
        with self.assertRaises(PersistenceError):
            st.initialize("not a snapshot")


class B03Update(H.RootCase):
    def test_prepare_does_not_touch_files(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=2)
        before = H.state_of(self.root)
        d = sc.day(3)
        sc.observe(d, 40)
        res = sc.prepare(st.read(), d)
        self.assertEqual(res.status, PREPARED)
        self.assertFalse(res.committed)
        self.assertEqual(H.state_of(self.root), before)

    def test_commit_appends_exactly_one_apply(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=3)
        old = st.read()
        old_events = old.events
        d = sc.day(4)
        sc.observe(d, 61)
        plan = sc.prepare(old, d).plan
        res = st.commit(plan)
        self.assertIsInstance(res, LocalCommitResult)
        self.assertEqual((res.status, res.committed, res.persistence_level), (COMMITTED, True,
                                                                              FILE_AND_DIRECTORY_SYNC))
        new = st.read()
        self.assertEqual(new, res.snapshot)
        self.assertEqual(new.head_seq, old.head_seq + 1)
        self.assertEqual(new.events[:-1], old_events)             # every earlier event value unchanged
        self.assertEqual(new.events[-1]["d"], d)
        self.assertEqual(new.events[-1]["kind"], "APPLY")
        self.assertEqual(sum(1 for e in new.events if e.get("d") == d), 1)

    def test_no_commit_writes_nothing(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=2)
        before = H.state_of(self.root)
        d = sc.day(3)                                              # no observation for this day
        ops = H.FaultOps()
        ro = LocalFileStore(self.root, writable=True, _ops=ops)
        res = sc.prepare(ro.read(), d)
        self.assertEqual(res.status, NO_COMMIT)
        self.assertIsNone(res.plan)
        self.assertNotIn("replace", [o for o, _ in ops.trace])
        self.assertNotIn(("create_exclusive", "tmp"), ops.trace)
        self.assertEqual(H.state_of(self.root), before)

    def test_already_applied_writes_nothing_and_survives_restart(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=3)
        d = sc.day(3)
        before = H.state_of(self.root)
        for store in (st, LocalFileStore(self.root, writable=True)):    # same instance, then a fresh one
            res = sc.prepare(store.read(), d)
            self.assertEqual(res.status, ALREADY_APPLIED)
            self.assertIsNone(res.plan)
        out = subprocess.run([sys.executable, "-B", "-I", H.WORKER, json.dumps({"mode": "read", "root": self.root})],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(H.state_of(self.root), before)
        self.assertEqual(sum(1 for e in st.read().events if e.get("d") == d), 1)

    def test_recommit_of_old_plan_is_cas_conflict_not_a_second_append(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=1)
        d = sc.day(2)
        sc.observe(d, 55)
        plan = sc.prepare(st.read(), d).plan
        st.commit(plan)
        before = H.state_of(self.root)
        with self.assertRaises(LocalStoreError) as cm:
            st.commit(plan)
        self.assertCode(cm.exception, "cas_conflict", "head", "cas")
        self.assertEqual(H.state_of(self.root), before)
        self.assertEqual(sc.prepare(st.read(), d).status, ALREADY_APPLIED)

    def test_returned_values_cannot_change_the_store(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=2)
        before = H.state_of(self.root)
        read = st.read()
        snap_text = encode_snapshot(read)
        read.events[0]["start_after"] = "1999-01-01"
        read.to_dict()["events"].clear()
        read.current_state["as_of_d"] = "x"
        self.assertEqual(encode_snapshot(read), snap_text)
        d = sc.day(3)
        sc.observe(d, 33)
        plan = sc.prepare(read, d).plan
        plan.event["d"] = "1999-01-01"
        res = st.commit(plan)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.status = "X"
        res.snapshot.events.clear()
        res.snapshot.to_dict()["events"].clear()
        again = st.read()
        self.assertEqual(again.head_seq, 3)
        self.assertEqual(H.raw(self.root), encode_snapshot(again).encode("utf-8"))
        validate_snapshot(again)

    def test_candidate_is_fully_checked_before_anything_is_published(self):
        from v2_persistence.plan import AppendPlan
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=1)
        d = sc.day(2)
        sc.observe(d, 55)
        good = sc.prepare(st.read(), d).plan
        bad_event = good.event
        bad_event["transition_result"]["gap"] = 12345            # content no longer matches its hash / recomputation
        bad = AppendPlan(good.expected_head_seq, good.expected_head_hash, bad_event)
        before = H.state_of(self.root)
        with self.assertRaises(PersistenceError) as cm:
            st.commit(bad)
        self.assertEqual(cm.exception.code, "snapshot_invalid")
        self.assertEqual(H.state_of(self.root), before)
        self.assertEqual(H.listing(self.root), [H.SNAP])
        st.commit(good)                                           # the genuine plan still goes through
        self.assertEqual(st.read().head_seq, 2)

    def test_reconcile_after_a_successful_commit(self):
        sc = H.Scenario()
        st = H.init_root(self.root, sc, advance=1)
        d = sc.day(2)
        sc.observe(d, 55)
        plan = sc.prepare(st.read(), d).plan
        self.assertEqual(reconcile(plan, st.read()).status, REPLAN_REQUIRED)
        st.commit(plan)
        self.assertEqual(reconcile(plan, st.read()).status, ALREADY_APPLIED)


if __name__ == "__main__":
    unittest.main()
