"""B3-14 (immutability and privacy) and B3-15 (the values are refused by the old stores)."""
import copy
import os
import shutil
import tempfile
import unittest

import r3_helpers as R

T, H, X, D, P, V, O = R.T, R.H, R.X, R.D, R.P, R.V, R.O
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_persistence.store import MemoryStore  # noqa: E402

URL = "https://example.invalid/secret-token-path"


class World(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.h, self.w = self.b.history(), self.b.w
        self.plan = R.prep(self.h, self.w, D[3], D[4], "r1")
        self.res = R.confirm(self.plan, self.h, self.w)


class Immutability(World):
    def test_the_inputs_are_not_changed(self):
        h, w = self.h, self.w
        ledger = copy.deepcopy(w.ledger)
        sessions = [R.cj(H.session_dict(s)) for s in w.sessions.sessions]
        digest = h.digest
        plan = R.prep(h, w, D[3], D[4], "r5")
        R.confirm(plan, h, w)
        self.assertEqual((h.digest, w.ledger, [R.cj(H.session_dict(s)) for s in w.sessions.sessions]),
                         (digest, ledger, sessions))

    def test_every_accessor_returns_an_independent_copy(self):
        for getter in (lambda p: p.basis, lambda p: p.to_dict(), lambda p: p.summary()):
            first = getter(self.plan)
            first["x"] = 1
            for key in list(first):
                if isinstance(first[key], dict):
                    first[key]["x"] = 1
                elif isinstance(first[key], list):
                    first[key].append("x")
            self.assertEqual(self.plan.to_dict(), R.prep(self.h, self.w, D[3], D[4], "r1").to_dict())
        basis = self.plan.basis
        basis["candidate_history"]["events"][-1]["floor"]["last_apply_d"] = "X"
        basis["floor"]["last_apply_d"] = "X"
        self.assertEqual(self.plan.basis["floor"]["last_apply_d"], D[2])
        self.assertEqual(self.plan.basis["candidate_history"]["events"][-1]["floor"]["last_apply_d"], D[2])
        self.assertEqual(R.confirm(self.plan, self.h, self.w).status, "CONFIRMED_IN_MEMORY")

    def test_a_plan_does_not_share_the_dict_it_was_made_from(self):
        data = self.plan.to_dict()
        plan = X.RestartPlan.from_dict(data)
        data["basis"]["floor"]["last_apply_d"] = "X"
        data["plan_hash"] = "x"
        self.assertEqual(plan, self.plan)
        self.assertEqual(R.confirm(plan, self.h, self.w).status, "CONFIRMED_IN_MEMORY")

    def test_unverified_values_never_share_a_container(self):
        fake = {"basis": {"status": ["READY"], "floor": {"k": [1]}, "request_id": {"a": 1}},
                "plan_hash": {"nested": [1, 2]}}
        plan = X.RestartPlan.from_dict(fake)
        got = plan.plan_hash
        got["nested"].append(3)
        self.assertEqual(plan.plan_hash, {"nested": [1, 2]})
        fake["plan_hash"]["nested"].append(9)
        self.assertEqual(plan.plan_hash, {"nested": [1, 2]})
        for _ in range(2):
            b = plan.basis
            b["floor"]["k"].append(5)
            b["status"].append("x")
        self.assertEqual(plan.basis["floor"], {"k": [1]})
        self.assertIsNone(plan.status)
        self.assertEqual(repr(plan), "RestartPlan(?)")
        with self.assertRaises(PersistenceError) as cm:
            plan.summary()
        self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.rule), ("restart_invalid", "plan", "plan_shape"))

    def test_a_scalar_replaced_by_a_container_is_not_shown(self):
        for key, value in (("status", ["READY"]), ("request_id", {"a": URL}), ("resume_after", [D[3]]),
                           ("expected_head_seq", "2"), ("floor", [1])):
            data = self.plan.to_dict()
            data["basis"][key] = value
            plan = X.RestartPlan.from_dict(data)
            self.assertEqual(repr(plan), "RestartPlan(?)", key)
            with self.assertRaises(PersistenceError):
                plan.summary()
        data = self.plan.to_dict()
        data["basis"]["floor"]["last_apply_d"] = {"x": URL}
        plan = X.RestartPlan.from_dict(data)
        with self.assertRaises(PersistenceError):
            plan.summary()
        self.assertNotIn("example.invalid", repr(plan))

    def test_deep_json_big_integers_and_odd_types_are_fixed_errors(self):
        deep = []
        for _ in range(60):
            deep = [deep]
        cases = [
            ({"basis": {"x": deep}, "plan_hash": "0" * 64}, "json_depth"),
            ({"basis": {"x": 10 ** 6000}, "plan_hash": "0" * 64}, "json_number"),
            ({"basis": {"x": float("nan")}, "plan_hash": "0" * 64}, "json_number"),
            ({"basis": {1: 2}, "plan_hash": "0" * 64}, "json_key"),
            ({"basis": {"x": {1, 2}}, "plan_hash": "0" * 64}, "json_type"),
            ({"basis": {"x": 1}}, "plan_shape"),
            ([], "plan_shape"),
            (None, "plan_shape"),
            ({"basis": {}, "plan_hash": "0" * 64, "extra": 1}, "plan_shape"),
        ]
        for data, rule in cases:
            with self.assertRaises(PersistenceError) as cm:
                X.RestartPlan.from_dict(data)
            self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.rule), ("restart_invalid", "plan", rule))

    def test_bool_and_float_integers_load_but_are_refused_when_confirming(self):
        for key, value in (("expected_head_seq", True), ("expected_head_seq", 2.0)):
            plan = R.refreshed(self.plan, lambda bs, key=key, value=value: bs.__setitem__(key, value))
            out = T.outcome(R.confirm, plan, self.h, self.w)
            self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"), (key, value))

        def float_head(bs):
            bs["candidate_history"]["head_seq"] = 3.0
        out = T.outcome(R.confirm, R.refreshed(self.plan, float_head), self.h, self.w)
        self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"))

        def bool_seq(bs):
            bs["candidate_history"]["events"][-1]["parent_seq"] = True
        out = T.outcome(R.confirm, R.refreshed(self.plan, bool_seq), self.h, self.w)
        self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"))

    def test_the_values_are_immutable(self):
        for obj, name in ((self.plan, "basis"), (self.plan, "x"), (self.res, "status"), (self.res, "history")):
            with self.assertRaises(AttributeError):
                setattr(obj, name, 1)
            with self.assertRaises(AttributeError):
                delattr(obj, name)
        with self.assertRaises(TypeError):
            X.RestartPlan()
        with self.assertRaises(AttributeError):
            self.plan._text = "x"
        self.assertEqual(hash(self.plan), hash(X.RestartPlan.from_dict(self.plan.to_dict())))
        self.assertEqual(self.res, R.confirm(self.plan, self.h, self.w))
        self.assertNotEqual(self.res, self.plan)

    def test_the_summary_is_a_whitelist(self):
        s = self.plan.summary()
        self.assertEqual(sorted(s), sorted(["status", "request_id", "resume_after", "check_d", "floor",
                                            "expected_head_seq", "candidate_head_seq", "new_records", "plan_hash",
                                            "committed", "committable"]))
        self.assertEqual((s["new_records"], s["committed"], s["committable"], s["expected_head_seq"],
                          s["candidate_head_seq"]), (1, False, False, 2, 3))
        self.assertEqual(s["floor"], {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(s["plan_hash"], self.plan.plan_hash)

    def test_repr_summary_and_errors_show_no_url_value_or_free_text(self):
        w = self.w
        rows = [dict(r, note=URL, source_url=URL) for r in w.ledger]
        plan = X.prepare_restart_plan(self.h, D[3], w.sessions, rows, D[4], "r1", R.WHEN)
        blob = repr(plan) + repr(plan.summary()) + repr(self.res) + repr(plan.to_dict()["plan_hash"])
        for banned in ("example.invalid", "secret", "27.0", "28.0", "observed_at", "current_fg_value", "record_id"):
            self.assertNotIn(banned, blob, banned)
        self.assertNotIn("example.invalid", repr(plan.to_dict()))        # the extra ledger columns were never kept
        errors = [
            T.refusal(X.prepare_restart_plan, self.h, D[3], w.sessions, w.ledger, D[4], URL, R.WHEN),
            T.refusal(X.prepare_restart_plan, self.h, D[3], w.sessions, w.ledger, D[4], "r1", URL),
            T.refusal(X.prepare_restart_plan, self.h, D[3], w.sessions, [{"record_id": URL}], D[4], "r1", R.WHEN),
            T.refusal(X.prepare_restart_plan, self.h, URL, w.sessions, w.ledger, D[4], "r1", R.WHEN),
            T.refusal(X.confirm_restart_plan, URL, URL, self.h, w.sessions, w.ledger),
            T.refusal(X.confirm_restart_plan, self.plan, URL, self.h, w.sessions, w.ledger),
        ]
        for e in errors:
            self.assertNotIn("example.invalid", str(e) + repr(e.__dict__))
            self.assertNotIn("secret", str(e) + repr(e.__dict__))

    def test_the_result_has_no_batch_and_no_ledger(self):
        for name in ("batch", "ledger", "body", "records", "basis"):
            self.assertFalse(hasattr(self.res, name), name)
        self.assertEqual(repr(self.res), "RestartConfirmResult(status=CONFIRMED_IN_MEMORY, committed=False)")
        self.assertFalse(self.res.committed)
        self.assertFalse(self.res.committable)
        self.assertFalse(self.plan.committed)


class StoresRefuseEveryValue(World):
    def things(self):
        again = R.confirm(self.plan, self.res.history, self.w)
        return [self.plan, self.res, again, self.res.history, self.plan.basis, self.plan.to_dict(), self.plan.summary(),
                self.res.history.to_dict(), O.read_effective(self.res.history)]

    def test_memory_store(self):
        store = MemoryStore()
        for thing in self.things():
            with self.subTest(type=type(thing).__name__):
                with self.assertRaises(PersistenceError) as cm:
                    store.commit(thing)
                self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))

    def test_local_file_store_with_a_file_sync_only_root(self):
        from v2_persistence.local import LocalFileStore
        root = tempfile.mkdtemp(prefix="v2s3b3_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            for thing in self.things():
                with self.subTest(type=type(thing).__name__):
                    with self.assertRaises(PersistenceError) as cm:
                        store.commit(thing)
                    self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
            self.assertEqual(os.listdir(root), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_the_api_has_no_batch_and_the_old_batch_check_does_not_take_a_restart(self):
        self.assertFalse(any("batch" in name.lower() for name in X.__all__))
        self.assertNotIn("check_append_batch", dir(X))
        self.assertFalse(hasattr(self.res, "batch"))


if __name__ == "__main__":
    unittest.main()
