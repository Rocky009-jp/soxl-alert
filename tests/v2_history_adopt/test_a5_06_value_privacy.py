"""A5-16 immutability, determinism, privacy of the printed forms and the old stores refusing the values."""
import os
import re
import shutil
import tempfile
import unittest

import a5_helpers as Z
from a5_helpers import A, X, GONE
from v2_persistence.errors import PersistenceError
from v2_persistence.local import LocalFileStore
from v2_persistence.store import MemoryStore, reconcile


def world():
    b, data, k = Z.new_world()
    return data, k, Z.prep(data, k)


class Immutability(unittest.TestCase):
    def test_the_values_cannot_be_changed_deleted_or_extended(self):
        data, k, plan = world()
        res = Z.confirm(plan, data)
        for obj, names in ((plan, ("_text", "_view", "basis", "extra", "committed")),
                           (res, ("_status", "_history", "_plan_hash", "status", "extra", "committed"))):
            for name in names:
                with self.subTest("%s.%s" % (type(obj).__name__, name)):
                    with self.assertRaises(AttributeError):
                        setattr(obj, name, "x")
                    with self.assertRaises(AttributeError):
                        delattr(obj, name)
            self.assertFalse(hasattr(obj, "__dict__"))
        self.assertEqual(A.AdoptionPlan.__slots__, ("_text", "_view"))
        self.assertEqual(A.AdoptionConfirmResult.__slots__, ("_status", "_history", "_plan_hash"))

    def test_a_plan_cannot_be_built_directly(self):
        for args in ((), ({"basis": {}, "plan_hash": "x"},)):
            with self.assertRaises(TypeError):
                A.AdoptionPlan(*args)

    def test_to_dict_basis_and_history_are_independent_copies(self):
        data, k, plan = world()
        before = plan.to_dict()
        d = plan.to_dict()
        d["basis"]["candidate_history"]["events"].clear()
        d["basis"]["discarded"]["items"].append("x")
        d["plan_hash"] = "x"
        b = plan.basis
        b["candidate_record"]["evidence"]["raw_size"] = -1
        b.clear()
        self.assertEqual(plan.to_dict(), before)
        self.assertIsNot(plan.basis, plan.basis)
        self.assertIsNot(plan.to_dict(), plan.to_dict())
        res = Z.confirm(plan, data)
        events = res.history.events
        events.clear()
        self.assertEqual(len(res.history.events), k + 1)
        self.assertEqual(Z.confirm(plan, data), res)

    def test_from_dict_copies_its_input_and_round_trips(self):
        data, k, plan = world()
        d = plan.to_dict()
        copy = A.AdoptionPlan.from_dict(d)
        self.assertEqual(copy, plan)
        self.assertEqual(hash(copy), hash(plan))
        d["basis"]["raw_size"] = 0
        self.assertEqual(copy, plan)
        self.assertEqual(Z.confirm(copy, data).status, "CONFIRMED_IN_MEMORY")

    def test_from_dict_checks_only_shape_and_json(self):
        data, k, plan = world()
        for bad in (None, [], {}, {"basis": {}}, dict(plan.to_dict(), x=1), "plan"):
            with self.subTest(repr(bad)[:30]):
                self.assertEqual(Z.err(A.AdoptionPlan.from_dict, bad), ("adoption_invalid", "plan", "plan_shape"))
        deep = {}
        cur = deep
        for _ in range(60):
            cur["x"] = {}
            cur = cur["x"]
        self.assertEqual(Z.err(A.AdoptionPlan.from_dict, {"basis": deep, "plan_hash": "x"})[2], "json_depth")
        self.assertEqual(Z.err(A.AdoptionPlan.from_dict, {"basis": {"x": float("nan")}, "plan_hash": "x"})[2], "json_number")
        self.assertEqual(Z.err(A.AdoptionPlan.from_dict, {"basis": {1: 2}, "plan_hash": "x"})[2], "json_key")
        self.assertEqual(Z.err(A.AdoptionPlan.from_dict, {"basis": {"x": (1,)}, "plan_hash": "x"})[2], "json_type")
        # a shape-valid plan that says nothing true is accepted here and refused when confirmed
        odd = A.AdoptionPlan.from_dict({"basis": {"x": 1}, "plan_hash": 5})
        self.assertIsNone(odd.status)
        self.assertEqual(Z.err(A.confirm_prefix_adoption, odd, Z.ZERO, data), ("history_plan_mismatch", "plan", None))

    def test_equality_and_hash_follow_the_value(self):
        data, k, plan = world()
        a, b = Z.confirm(plan, data), Z.confirm(plan, data)
        self.assertEqual((a, hash(a)), (b, hash(b)))
        self.assertNotEqual(a, Z.confirm(plan, Z.candidate_bytes(data, k)))             # CONFIRMED_IN_MEMORY vs NO_CHANGE
        self.assertNotEqual(plan, plan.to_dict())
        self.assertNotEqual(a, a.history)

    def test_committed_is_always_false_and_there_is_no_committable(self):
        data, k, plan = world()
        for obj in (plan, Z.confirm(plan, data), Z.confirm(plan, Z.candidate_bytes(data, k))):
            self.assertIs(obj.committed, False)
            self.assertFalse(hasattr(obj, "committable"))
            self.assertFalse(hasattr(obj, "batch"))

    def test_the_status_of_a_plan(self):
        data, k, plan = world()
        self.assertEqual(plan.status, "READY")
        self.assertEqual(A.READY, "READY")
        self.assertEqual((A.CONFIRMED_IN_MEMORY, A.NO_CHANGE), ("CONFIRMED_IN_MEMORY", "NO_CHANGE"))


class Determinism(unittest.TestCase):
    def test_the_same_input_and_the_same_instant_give_the_same_basis_and_hash(self):
        data, k, plan = world()
        for _ in range(3):
            again = Z.prep(bytes(data), k)
            self.assertEqual(again.basis, plan.basis)
            self.assertEqual(again.plan_hash, plan.plan_hash)
            self.assertEqual(Z.cj(again.to_dict()), Z.cj(plan.to_dict()))

    def test_another_file_or_id_gives_another_plan(self):
        b = X.ex_new()
        hashes = set()
        for index in range(1, 7):
            data, k = Z.damaged_at(b, index)
            hashes.add(Z.prep(data, k).plan_hash)
        self.assertEqual(len(hashes), 6)

    def test_the_input_bytes_are_not_changed_and_are_not_kept(self):
        import gc
        data, k, plan = world()
        copy = bytes(data)
        res = Z.confirm(plan, data)
        self.assertEqual(data, copy)
        for obj in (plan, res):
            for r in gc.get_referents(obj):
                self.assertNotIsInstance(r, (bytes, bytearray, memoryview))
                self.assertNotEqual(r, data)


class PrintedForms(unittest.TestCase):
    MARKERS = ("SECRET-VALUE", "https://", "/etc/", "C:\\", "password", "example.invalid")

    def marked_world(self):
        b = X.ex_new()
        events = Z.deep(b.events)
        events[6]["event_hash"] = Z.ZERO
        events[6]["note"] = "SECRET-VALUE https://example.invalid/hook /etc/passwd C:\\Users\\x password"
        return X.file_of(events), 6

    def test_repr_and_summary_hold_no_raw_value(self):
        data, k = self.marked_world()
        plan = Z.prep(data, k)
        res = Z.confirm(plan, data)
        texts = [repr(plan), repr(res), str(plan), str(res), Z.cj(plan.summary())]
        for text in texts:
            for marker in self.MARKERS:
                self.assertNotIn(marker, text)
            self.assertNotIn(Z.sha_bytes(data), text)
        for text in texts[:4]:
            self.assertNotIn(plan.plan_hash, text)                       # repr / str show a short digest only
        self.assertNotIn("SECRET-VALUE", Z.cj(plan.to_dict()))          # the discarded side is described, never copied

    def test_the_forms_are_fixed_and_short(self):
        data, k, plan = world()
        self.assertRegex(repr(plan), r"^AdoptionPlan\(status=READY, plan_hash=[0-9a-f]{12}\)$")
        self.assertRegex(repr(Z.confirm(plan, data)), r"^AdoptionConfirmResult\(status=CONFIRMED_IN_MEMORY, committed=False\)$")
        self.assertRegex(repr(Z.confirm(plan, Z.candidate_bytes(data, k))), r"status=NO_CHANGE, committed=False\)$")
        self.assertEqual(plan.summary(), {"status": "READY", "request_id": "ad1", "adopt_count": k,
                                          "plan_hash": plan.plan_hash, "committed": False})
        self.assertLessEqual(len(repr(plan)), 80)

    def test_nothing_that_is_not_re_checked_is_printed(self):
        hostile = A.AdoptionPlan.from_dict({"basis": {"status": "READY", "request_id": "https://example.invalid/x?k=SECRET-VALUE",
                                                      "adopt_count": 3, "path": "/etc/passwd"},
                                            "plan_hash": "SECRET-VALUE"})
        self.assertEqual(repr(hostile), "AdoptionPlan(?)")
        self.assertEqual(Z.err(hostile.summary), ("adoption_invalid", "plan", "plan_shape"))
        self.assertNotIn("SECRET-VALUE", str(hostile))

    def test_refusals_carry_fixed_identifiers_only(self):
        data, k, plan = world()
        marked, mk = self.marked_world()
        causes = [
            lambda: Z.prep(marked, mk + 1), lambda: Z.prep(marked, mk, "SECRET VALUE"), lambda: Z.prep(b"SECRET-VALUE", 1),
            lambda: Z.prep(marked, 0),
            lambda: Z.confirm(plan, marked), lambda: Z.confirm(plan, data, plan_hash="SECRET-VALUE"),
            lambda: Z.confirm(plan, "SECRET-VALUE".encode("utf-8").decode("utf-8")),
        ]
        for fn in causes:
            with self.assertRaises(Exception) as cm:
                fn()
            text = "%s %s %r" % (cm.exception, getattr(cm.exception, "detail", None), cm.exception.args)
            for marker in self.MARKERS + (Z.sha_bytes(data), plan.plan_hash):
                self.assertNotIn(marker, text)
            self.assertRegex(str(cm.exception), r"^[a-z_0-9]+(:[a-z_0-9]+)?$")


class StoresRefuseTheValues(unittest.TestCase):
    def values(self):
        data, k, plan = world()
        return [plan, plan.to_dict(), Z.confirm(plan, data), Z.confirm(plan, Z.candidate_bytes(data, k))]

    def test_the_memory_store_refuses_a_plan_and_a_result_as_a_commit(self):
        store = MemoryStore()
        store.initialize(X.P.World().snap())
        before = store.read()
        for item in self.values():
            with self.assertRaises(PersistenceError) as cm:
                store.commit(item)
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
            with self.assertRaises(PersistenceError) as cm:
                reconcile(item, before)
            self.assertEqual(cm.exception.rule, "plan_type")
        self.assertEqual(store.read(), before)

    def test_the_local_store_refuses_them_and_leaves_no_trace(self):
        root = tempfile.mkdtemp(prefix="v2a5_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            store.initialize(X.P.World().snap())
            before = sorted(os.listdir(root))
            with open(os.path.join(root, "snapshot.json"), "rb") as f:
                content = f.read()
            for item in self.values():
                with self.assertRaises(PersistenceError) as cm:
                    store.commit(item)
                self.assertEqual(cm.exception.rule, "plan_type")
            self.assertEqual(sorted(os.listdir(root)), before)
            with open(os.path.join(root, "snapshot.json"), "rb") as f:
                self.assertEqual(f.read(), content)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_working_directory_is_not_touched(self):
        before = sorted(os.listdir(os.getcwd()))
        data, k, plan = world()
        Z.confirm(plan, data)
        Z.confirm(plan, Z.candidate_bytes(data, k))
        self.assertEqual(sorted(os.listdir(os.getcwd())), before)


if __name__ == "__main__":
    unittest.main()
