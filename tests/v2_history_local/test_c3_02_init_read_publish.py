"""C3-03 initialization, C3-04 reading, C3-05 publishing. Expected bytes come from c2_helpers.file_bytes."""
import os
import unittest

import c3_helpers as H
from v2_history_local import FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, INITIALIZED, PUBLISHED


class Initialize(H.RootCase):
    def test_genesis_initializes_a_root_and_leaves_only_history_json(self):
        g = H.C2.genesis_case()
        res = self.store().initialize(g.pub)
        self.assertEqual((res.status, res.committed, res.persistence_level), (INITIALIZED, True,
                                                                              FILE_AND_DIRECTORY_SYNC))
        self.assertEqual(res.publication_hash, g.pub.publication_hash)
        self.assertEqual(res.history, g.candidate)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(g.candidate))
        self.assertEqual(H.listing(self.root), ["history.json"])
        self.assertEqual(self.store().read(), g.candidate)

    def test_file_sync_only_mode_reports_its_level(self):
        g = H.C2.genesis_case()
        res = self.store(durability="file_sync_only").initialize(g.pub)
        self.assertEqual(res.persistence_level, FILE_SYNC_ONLY)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(g.candidate))

    def test_a_second_initialization_is_refused_and_changes_nothing(self):
        g = H.C2.genesis_case()
        store = self.store()
        store.initialize(g.pub)
        before = H.state_of(self.root)
        e = self.run_err(store.initialize, g.pub)
        self.assertStore(e, "already_initialized", "store", "read")
        self.assertEqual(H.state_of(self.root), before)

    def test_even_a_damaged_file_counts_as_initialized(self):
        H.put(self.root, H.HIST, b"not a history")
        e = self.run_err(self.store().initialize, H.C2.genesis_case().pub)
        self.assertStore(e, "already_initialized", "store", "read")
        self.assertEqual(H.raw(self.root), b"not a history")

    def test_a_read_only_store_does_not_initialize(self):
        e = self.run_err(self.store(writable=False).initialize, H.C2.genesis_case().pub)
        self.assertStore(e, "store_read_only", "store", "args")
        self.assertEqual(H.listing(self.root), [])


class Read(H.RootCase):
    def test_an_uninitialized_root(self):
        self.assertStore(self.run_err(self.store().read), "store_uninitialized", "store", "read")
        self.assertEqual(H.listing(self.root), [])

    def test_a_valid_file_is_read_and_the_lock_is_taken_and_released(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        history = self.store(ops, writable=False).read()
        self.assertEqual(history, c.history)
        self.assertEqual(ops.ops("create_exclusive:lock", "unlink:lock"), ["create_exclusive:lock", "unlink:lock"])
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_every_read_takes_the_lock_again(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops()
        store = self.store(ops, writable=False)
        for _ in range(3):
            store.read()
        self.assertEqual(ops.ops("create_exclusive:lock"), ["create_exclusive:lock"] * 3)
        self.assertEqual(ops.ops("unlink:lock"), ["unlink:lock"] * 3)

    def test_the_lock_is_released_after_a_failed_read_too(self):
        H.put(self.root, H.HIST, b"\xff\xfe")
        self.run_err(self.store().read)
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_an_indented_valid_file_is_read(self):
        c = H.C2.day_case()
        H.put(self.root, H.HIST, H.C2.indented(c.history))
        self.assertNotEqual(H.raw(self.root), H.C2.file_bytes(c.history))
        self.assertEqual(self.store().read(), c.history)

    def test_history_json_that_is_a_directory(self):
        os.mkdir(os.path.join(self.root, H.HIST))
        self.assertStore(self.run_err(self.store().read), "store_root_invalid", "root", "read")

    def test_history_json_that_is_a_link(self):
        c = H.C2.day_case()
        H.put(self.root, "other.json", c.current)
        try:
            os.symlink(os.path.join(self.root, "other.json"), os.path.join(self.root, H.HIST))
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("no symbolic links here")
        self.assertStore(self.run_err(self.store().read), "store_root_invalid", "root", "read")

    def test_a_file_replaced_while_it_is_read(self):
        c = H.C2.day_case()
        self.put_current(c)
        other = os.path.join(self.root, "swap.tmp-test")

        def swap():
            H.put(self.root, "swap.tmp-test", c.current)
            os.replace(other, os.path.join(self.root, H.HIST))
        ops = H.C3Ops().add("read_file", "history", before=swap)
        e = self.run_err(self.store(ops, writable=False).read)
        self.assertStore(e, "store_root_invalid", "root", "read")

    def test_a_failure_to_read_is_an_io_error_without_the_path(self):
        c = H.C2.day_case()
        self.put_current(c)
        ops = H.C3Ops().fail("read_file", "history")
        e = self.run_err(self.store(ops, writable=False).read)
        self.assertStore(e, "store_io_error", "history", "read")
        self.assertNotIn(H.SECRET, str(e) + repr(e.__dict__))

    def test_files_that_are_not_valid_histories(self):
        c = H.C2.day_case()
        good = c.current
        cases = {
            "empty": b"",
            "not utf8": b"\xff\xfe\x00",
            "bom": b"\xef\xbb\xbf" + good,
            "not json": b"{not json",
            "truncated": good[:-5],
            "a list": b"[]",
            "trailing text": good + b" x",
        }
        text = good.decode("utf-8")
        cases["a hash changed"] = text.replace('"event_hash":"', '"event_hash":"0', 1).encode("utf-8")
        for name, data in cases.items():
            with self.subTest(name=name):
                H.put(self.root, H.HIST, data)
                e = self.run_err(self.store(writable=False).read)
                self.assertEqual(e.code, "history_invalid", name)
                self.assertEqual(H.raw(self.root), data)
                self.assertEqual(H.listing(self.root), ["history.json"])


class Publish(H.RootCase):
    def test_each_append_source_publishes_the_candidate_bytes(self):
        cases = H.append_cases() + [H.C2.restore_case(consume=False)]
        self.assertEqual([c.source for c in cases], ["DAILY", "RESOLUTION", "RESTART", "RESTORE", "RESTORE"])
        for c in cases:
            with self.subTest(source=c.source):
                root = H.make_root()
                self.addCleanup(__import__("shutil").rmtree, root, True)
                H.put(root, H.HIST, c.current)
                store = H.HistoryFileStore(root, writable=True)
                res = store.publish(c.pub)
                self.assertEqual((res.status, res.committed, res.publication_hash),
                                 (PUBLISHED, True, c.pub.publication_hash))
                self.assertEqual(res.history, c.candidate)
                self.assertEqual(H.raw(root), H.C2.file_bytes(c.candidate))
                self.assertEqual(H.listing(root), ["history.json"])
                self.assertEqual(store.read(), c.candidate)

    def test_the_restore_with_a_consume_record_is_one_of_them(self):
        c = H.C2.restore_case(consume=True)
        self.assertIn(H.C2.C1.CONSUME, [op["op"] for op in c.plan.to_dict()["basis"]["ops"]])
        self.put_current(c)
        self.store().publish(c.pub)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))

    def test_the_same_publication_twice_is_stale_and_changes_nothing(self):
        c = H.C2.day_case()
        self.put_current(c)
        store = self.store()
        store.publish(c.pub)
        before = H.state_of(self.root)
        e = self.run_err(store.publish, c.pub)
        self.assertEqual((e.code, e.field, e.rule), ("publication_stale", "current", "head"))
        self.assertEqual(H.state_of(self.root), before)

    def test_another_write_in_between_makes_it_stale(self):
        c = H.C2.day_case()
        other = H.C2.other_extension(c)
        H.put(self.root, H.HIST, H.C2.file_bytes(other))
        before = H.state_of(self.root)
        e = self.run_err(self.store().publish, c.pub)
        self.assertEqual((e.code, e.rule), ("publication_stale", "head"))
        self.assertEqual(H.state_of(self.root), before)

    def test_an_uninitialized_root(self):
        c = H.C2.day_case()
        e = self.run_err(self.store().publish, c.pub)
        self.assertStore(e, "store_uninitialized", "store", "read")
        self.assertEqual(H.listing(self.root), [])

    def test_a_read_only_store_does_not_publish(self):
        c = H.C2.day_case()
        self.put_current(c)
        before = H.state_of(self.root)
        e = self.run_err(self.store(writable=False).publish, c.pub)
        self.assertStore(e, "store_read_only", "store", "args")
        self.assertEqual(H.state_of(self.root), before)

    def test_an_indented_current_file_is_published_in_the_canonical_form(self):
        c = H.C2.day_case()
        H.put(self.root, H.HIST, H.C2.indented(c.history))
        self.store().publish(c.pub)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))

    def test_file_sync_only_publishes_the_same_bytes(self):
        c = H.C2.day_case()
        self.put_current(c)
        res = self.store(durability="file_sync_only").publish(c.pub)
        self.assertEqual(res.persistence_level, FILE_SYNC_ONLY)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))

    def test_two_publications_in_a_row_extend_the_history(self):
        h, pub, w = H.day1_root(self.root)
        store = self.store()
        res = store.publish(pub)
        d2 = H.C2.D[2]
        w.ledger.append(H.C2.P.obs("R2", d2, 31.0))
        pub2 = H.U.publish_day(res.history, d2, w.series, w.sessions, w.ledger)
        res2 = store.publish(pub2)
        self.assertEqual(res2.history.head_seq, res.history.head_seq + 1)
        self.assertEqual(store.read(), res2.history)


if __name__ == "__main__":
    unittest.main()
