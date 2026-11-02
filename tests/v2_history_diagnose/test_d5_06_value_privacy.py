"""D5-15 immutability, determinism, privacy of the printed forms, and that the old stores refuse the value."""
import os
import shutil
import tempfile
import unittest

import d5_helpers as X
from d5_helpers import G, PersistenceError
from v2_persistence.local import LocalFileStore
from v2_persistence.store import MemoryStore, reconcile


def a_diagnosis():
    b = X.ex_new()
    return G.diagnose_history_bytes(X.file_of(X.with_hash(b.events, 5)))


class Immutability(unittest.TestCase):
    def test_attributes_cannot_be_set_deleted_or_added(self):
        d = a_diagnosis()
        for name in ("status", "_text", "_view", "extra"):
            with self.assertRaises(AttributeError):
                setattr(d, name, "x")
            with self.assertRaises(AttributeError):
                delattr(d, name)
        self.assertFalse(hasattr(d, "__dict__"))

    def test_to_dict_and_every_reader_return_independent_copies(self):
        d = a_diagnosis()
        first = d.to_dict()
        first["status"] = "VALID"
        first["verified"]["count"] = 999
        first["discarded"]["items"].append("x")
        first["failure"]["rule"] = "changed"
        first["claimed"]["head_seq"] = -1
        self.assertEqual(d.to_dict(), a_diagnosis().to_dict())
        for name in ("failure", "claimed", "verified", "discarded"):
            value = getattr(d, name)
            value.clear()
            self.assertTrue(getattr(d, name), name)
            self.assertIsNot(getattr(d, name), getattr(d, name))
        self.assertEqual(d.to_dict()["verified"]["count"], 5)

    def test_every_key_has_a_reader_equal_to_the_dict_value(self):
        d = a_diagnosis()
        as_dict = d.to_dict()
        self.assertEqual(set(as_dict), {"operation", "status", "raw_sha256", "raw_size", "schema_version",
                                        "canonical_text", "failure", "claimed", "verified", "discarded"})
        for key, value in as_dict.items():
            self.assertEqual(getattr(d, key), value, key)

    def test_nothing_of_the_input_is_kept(self):
        d = a_diagnosis()
        self.assertEqual(G.HistoryDiagnosis.__slots__, ("_text", "_view"))
        self.assertFalse(hasattr(G.HistoryDiagnosis, "from_dict"))
        text, view = object.__getattribute__(d, "_text"), object.__getattribute__(d, "_view")
        self.assertIs(type(text), str)
        self.assertIs(type(view), dict)
        self.assertEqual(text, X.cj(d.to_dict()))
        raw = X.file_of(X.with_hash(X.ex_new().events, 5))
        self.assertNotIn("confirmed_inputs", text)
        self.assertLess(len(text), len(raw) // 4)
        self.assertEqual(sorted(view), sorted(d.to_dict()))

    def test_the_only_things_the_value_refers_to_are_its_text_and_its_parsed_view(self):
        import gc
        raw = X.file_of(X.with_hash(X.ex_new().events, 5))
        d = G.diagnose_history_bytes(raw)
        referents = [r for r in gc.get_referents(d) if not isinstance(r, type)]
        self.assertEqual(sorted(type(r).__name__ for r in referents), ["dict", "str"])
        for r in referents:
            self.assertNotIn(type(r), (bytes, bytearray, memoryview))
        text = [r for r in referents if isinstance(r, str)][0]
        self.assertEqual(text, X.cj(d.to_dict()), "the text is the canonical report, not the decoded input")
        self.assertNotEqual(text, raw.decode("utf-8"))

    def test_the_input_bytes_are_not_changed(self):
        raw = X.file_of(X.with_hash(X.ex_new().events, 5))
        copy = bytes(raw)
        G.diagnose_history_bytes(raw)
        self.assertEqual(raw, copy)

    def test_direct_construction_checks_only_the_shape(self):
        good = a_diagnosis().to_dict()
        self.assertEqual(G.HistoryDiagnosis(good), a_diagnosis())
        for bad in ({}, dict(good, extra=1), {k: v for k, v in good.items() if k != "status"},
                    dict(good, status="MAYBE"), dict(good, operation="other/1"), list(good.items()), None):
            with self.assertRaises(PersistenceError) as cm:
                G.HistoryDiagnosis(bad)
            self.assertEqual((cm.exception.code, cm.exception.field), ("diagnosis_invalid", "diagnosis"))

    def test_the_constructor_copies_its_input(self):
        fields = a_diagnosis().to_dict()
        d = G.HistoryDiagnosis(fields)
        before = d.to_dict()
        fields["status"] = "VALID"
        fields["verified"]["count"] = 999
        fields["discarded"]["items"].clear()
        self.assertEqual(d.to_dict(), before)
        self.assertEqual(d.digest, a_diagnosis().digest)

    def test_equality_and_hash_follow_the_value(self):
        a, b = a_diagnosis(), a_diagnosis()
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertNotEqual(a, G.diagnose_history_bytes(b""))
        self.assertNotEqual(a, a.to_dict())


class Determinism(unittest.TestCase):
    def test_the_same_bytes_give_the_same_dict_and_digest(self):
        for data in (X.history_file(X.ex_r()), X.file_of(X.with_hash(X.ex_r().events, 12)), b"", b"\xff",
                     X.v1_file(X.v1_world(3).snap()), X.file_of(X.ex_u().events, head_hash=X.ZERO)):
            a, b = G.diagnose_history_bytes(data), G.diagnose_history_bytes(bytes(data))
            self.assertEqual(a.to_dict(), b.to_dict())
            self.assertEqual(X.cj(a.to_dict()), X.cj(b.to_dict()))
            self.assertEqual(a.digest, b.digest)
            self.assertEqual(a.digest, X.text_sha(X.cj(a.to_dict())))
            self.assertEqual(len(a.digest), 64)
            self.assertEqual(a.summary(), b.summary())

    def test_different_files_give_different_digests(self):
        b = X.ex_new()
        digests = {G.diagnose_history_bytes(X.file_of(X.with_hash(b.events, i))).digest for i in range(1, 7)}
        self.assertEqual(len(digests), 6)

    def test_the_dict_contains_no_time_or_random_looking_field(self):
        d = G.diagnose_history_bytes(X.history_file(X.ex_new())).to_dict()
        self.assertEqual(sorted(d), sorted(["operation", "status", "raw_sha256", "raw_size", "schema_version",
                                            "canonical_text", "failure", "claimed", "verified", "discarded"]))


class PrintedForms(unittest.TestCase):
    MARKERS = ("SECRET-VALUE", "https://", "/etc/", "C:\\", "resume_after", "password")

    def damaged_with_markers(self):
        b = X.ex_u()
        events = X.deep(b.events)
        events[2]["event_hash"] = X.ZERO
        events[2]["note"] = "SECRET-VALUE https://example.invalid/hook /etc/passwd C:\\Users\\x password"
        events[3]["request_id"] = "SECRET-VALUE-id with spaces"
        events[3]["resume_after"] = "SECRET-VALUE"
        return X.file_of(events)

    def test_repr_and_summary_hold_no_raw_value(self):
        for data in (self.damaged_with_markers(), self.damaged_with_markers()[:-9], b"\xff SECRET-VALUE"):
            d = G.diagnose_history_bytes(data)
            for text in (repr(d), d.summary(), str(d)):
                for marker in self.MARKERS:
                    self.assertNotIn(marker, text)
                self.assertNotIn(X.cj(d.to_dict()), text)
            for marker in self.MARKERS:
                self.assertNotIn(marker, X.cj(d.to_dict()))

    def test_repr_is_short_and_has_a_short_digest(self):
        d = a_diagnosis()
        self.assertLessEqual(len(repr(d)), 120)
        self.assertIn(d.raw_sha256[:12], repr(d))
        self.assertNotIn(d.raw_sha256, repr(d))
        self.assertNotIn(d.raw_sha256, d.summary())
        self.assertIn(d.raw_sha256[:12], d.summary())

    def test_summary_of_a_valid_and_an_unreadable_value(self):
        v = G.diagnose_history_bytes(X.history_file(X.ex_new()))
        self.assertIn("status=VALID", v.summary())
        self.assertIn("verified_count=7", v.summary())
        u = G.diagnose_history_bytes(b"{")
        self.assertIn("status=UNREADABLE", u.summary())
        self.assertIn("failure=json/history_invalid/history/json", u.summary())


class StoresRefuseTheValue(unittest.TestCase):
    def test_the_memory_store_refuses_a_diagnosis_as_a_plan(self):
        store = MemoryStore()
        store.initialize(X.P.World().snap())
        before = store.read()
        for item in (a_diagnosis(), a_diagnosis().to_dict()):
            with self.assertRaises(PersistenceError) as cm:
                store.commit(item)
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
            with self.assertRaises(PersistenceError) as cm:
                reconcile(item, before)
            self.assertEqual(cm.exception.rule, "plan_type")
        self.assertEqual(store.read(), before)

    def test_the_local_store_refuses_a_diagnosis_and_leaves_no_trace(self):
        root = tempfile.mkdtemp(prefix="v2d5_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            store.initialize(X.P.World().snap())
            before = sorted(os.listdir(root))
            with open(os.path.join(root, "snapshot.json"), "rb") as f:
                content = f.read()
            for item in (a_diagnosis(), a_diagnosis().to_dict()):
                with self.assertRaises(PersistenceError) as cm:
                    store.commit(item)
                self.assertEqual(cm.exception.rule, "plan_type")
            self.assertEqual(sorted(os.listdir(root)), before)
            with open(os.path.join(root, "snapshot.json"), "rb") as f:
                self.assertEqual(f.read(), content)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_diagnosis_writes_nothing_in_the_working_directory(self):
        work = tempfile.mkdtemp(prefix="v2d5_cwd_")
        old = os.getcwd()
        try:
            os.chdir(work)
            for data in (X.history_file(X.ex_new()), b"", b"\xff", self_damaged()):
                G.diagnose_history_bytes(data)
            self.assertEqual(os.listdir(work), [])
        finally:
            os.chdir(old)
            shutil.rmtree(work, ignore_errors=True)


def self_damaged():
    return X.file_of(X.with_hash(X.ex_r().events, 12))


if __name__ == "__main__":
    unittest.main()
