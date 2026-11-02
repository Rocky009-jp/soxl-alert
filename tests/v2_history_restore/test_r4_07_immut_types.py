"""B4-18: the values are immutable and share nothing, nothing private is shown, odd types are fixed errors, and the older
stores refuse every value of this package."""
import copy
import os
import shutil
import tempfile
import unittest

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_persistence.store import MemoryStore  # noqa: E402

URL = "https://example.invalid/secret-token-path"
MAPPING = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}


class World(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_ack_between()
        self.h, self.w = self.b.history(), self.b.w
        self.plan = R.prep(self.b, 1, MAPPING, D[5], "r4-1")
        self.res = R.confirm(self.plan, self.h, self.w)


class Immutability(World):
    def test_the_inputs_are_not_changed(self):
        ledger = copy.deepcopy(self.w.ledger)
        sessions = [R.cj(H.session_dict(s)) for s in self.w.sessions.sessions]
        digest, events = self.h.digest, R.cj(self.h.events)
        plan = R.prep(self.b, 1, MAPPING, D[5], "r4-2")
        R.confirm(plan, self.h, self.w)
        self.assertEqual((self.h.digest, R.cj(self.h.events), self.w.ledger,
                          [R.cj(H.session_dict(s)) for s in self.w.sessions.sessions]),
                         (digest, events, ledger, sessions))

    def test_every_accessor_returns_an_independent_copy(self):
        for getter in (lambda p: p.basis, lambda p: p.to_dict(), lambda p: p.summary()):
            first = getter(self.plan)
            first["x"] = 1
            for key in list(first):
                if isinstance(first[key], dict):
                    first[key]["x"] = 1
                elif isinstance(first[key], list):
                    first[key].append("x")
            self.assertEqual(self.plan.to_dict(), R.prep(self.b, 1, MAPPING, D[5], "r4-1").to_dict())
        basis = self.plan.basis
        basis["candidate_history"]["events"][-1]["state_after"] = "X"
        basis["ops"][0]["op"] = "X"
        basis["changes"].append("x")
        self.assertEqual(self.plan.basis["ops"][0]["op"], "DROP")
        self.assertNotEqual(self.plan.basis["candidate_history"]["events"][-1]["state_after"], "X")
        self.assertEqual(R.confirm(self.plan, self.h, self.w).status, "CONFIRMED_IN_MEMORY")

    def test_a_plan_does_not_share_the_dict_it_was_made_from(self):
        data = self.plan.to_dict()
        plan = Z.RestorePlan.from_dict(data)
        data["basis"]["ops"][0]["op"] = "X"
        data["plan_hash"] = "x"
        self.assertEqual(plan, self.plan)
        self.assertEqual(R.confirm(plan, self.h, self.w).status, "CONFIRMED_IN_MEMORY")

    def test_unverified_values_never_share_a_container(self):
        fake = {"basis": {"status": ["READY"], "ops": {"k": [1]}, "request_id": {"a": 1}}, "plan_hash": {"nested": [1, 2]}}
        plan = Z.RestorePlan.from_dict(fake)
        got = plan.plan_hash
        got["nested"].append(3)
        self.assertEqual(plan.plan_hash, {"nested": [1, 2]})
        fake["plan_hash"]["nested"].append(9)
        self.assertEqual(plan.plan_hash, {"nested": [1, 2]})
        for _ in range(2):
            b = plan.basis
            b["ops"]["k"].append(5)
            b["status"].append("x")
        self.assertEqual(plan.basis["ops"], {"k": [1]})
        self.assertIsNone(plan.status)
        self.assertEqual(repr(plan), "RestorePlan(?)")
        e = R.refusal(plan.summary)
        self.assertEqual((e.code, e.field, e.rule), ("restore_invalid", "plan", "plan_shape"))

    def test_a_scalar_replaced_by_a_container_is_not_shown(self):
        for key, value in (("status", ["READY"]), ("request_id", {"a": URL}), ("check_d", [D[3]]),
                           ("expected_head_seq", "2"), ("restore_point", [1]), ("changes", {"a": URL}),
                           ("candidate_records", [])):
            data = self.plan.to_dict()
            data["basis"][key] = value
            plan = Z.RestorePlan.from_dict(data)
            self.assertEqual(repr(plan), "RestorePlan(?)", key)
            self.assertEqual(R.refusal(plan.summary).code, "restore_invalid")
        for edit in (lambda c: c.update(d={"x": URL}), lambda c: c.update(changed_fields=[URL]),
                     lambda c: c.update(op=URL), lambda c: c.update(same_as_superseded="yes"),
                     lambda c: c.update(to_seq=True)):
            data = self.plan.to_dict()
            edit(data["basis"]["changes"][1])
            plan = Z.RestorePlan.from_dict(data)
            self.assertEqual(R.refusal(plan.summary).code, "restore_invalid")
            self.assertNotIn("example.invalid", repr(plan))

    def test_deep_json_big_integers_and_odd_types_are_fixed_errors(self):
        deep = []
        for _ in range(60):
            deep = [deep]
        cases = [
            ({"basis": {"x": deep}, "plan_hash": "0" * 64}, "json_depth"),
            ({"basis": {"x": 10 ** 6000}, "plan_hash": "0" * 64}, "json_number"),
            ({"basis": {"x": float("nan")}, "plan_hash": "0" * 64}, "json_number"),
            ({"basis": {"x": float("inf")}, "plan_hash": "0" * 64}, "json_number"),
            ({"basis": {1: 2}, "plan_hash": "0" * 64}, "json_key"),
            ({"basis": {"x": {1, 2}}, "plan_hash": "0" * 64}, "json_type"),
            ({"basis": {"x": 1}}, "plan_shape"),
            ([], "plan_shape"),
            (None, "plan_shape"),
            ({"basis": {}, "plan_hash": "0" * 64, "extra": 1}, "plan_shape"),
        ]
        for data, rule in cases:
            e = R.refusal(Z.RestorePlan.from_dict, data)
            self.assertEqual((e.code, e.field, e.rule), ("restore_invalid", "plan", rule))

    def test_bool_and_float_integers_load_but_are_refused_when_confirming(self):
        for key, value in (("expected_head_seq", True), ("expected_head_seq", 5.0)):
            plan = R.refreshed(self.plan, lambda bs, key=key, value=value: bs.__setitem__(key, value))
            out = T.outcome(R.confirm, plan, self.h, self.w)
            self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"), (key, value))
        for edit in (lambda bs: bs["restore_point"].__setitem__("seq", True),
                     lambda bs: bs["ops"][0].__setitem__("from_seq", 2.0),
                     lambda bs: bs["candidate_records"][1].__setitem__("parent_seq", True)):
            out = T.outcome(R.confirm, R.refreshed(self.plan, edit), self.h, self.w)
            self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"))

    def test_the_values_are_immutable(self):
        for obj, name in ((self.plan, "basis"), (self.plan, "x"), (self.res, "status"), (self.res, "history")):
            with self.assertRaises(AttributeError):
                setattr(obj, name, 1)
            with self.assertRaises(AttributeError):
                delattr(obj, name)
        with self.assertRaises(TypeError):
            Z.RestorePlan()
        with self.assertRaises(AttributeError):
            self.plan._text = "x"
        self.assertEqual(hash(self.plan), hash(Z.RestorePlan.from_dict(self.plan.to_dict())))
        self.assertEqual(self.res, R.confirm(self.plan, self.h, self.w))
        self.assertNotEqual(self.res, self.plan)

    def test_the_summary_is_a_whitelist(self):
        s = self.plan.summary()
        self.assertEqual(sorted(s), sorted(["status", "request_id", "check_d", "restore_point_seq", "expected_head_seq",
                                            "candidate_head_seq", "new_records", "ops", "plan_hash", "committed",
                                            "committable"]))
        self.assertEqual((s["new_records"], s["committed"], s["committable"], s["expected_head_seq"],
                          s["candidate_head_seq"], s["restore_point_seq"]), (4, False, False, 5, 9, 1))
        self.assertEqual([(o["op"], o["from_seq"], o["to_seq"], o["changed_fields"]) for o in s["ops"]],
                         [("DROP", 2, None, []), ("REAPPLY", 3, 7, ["state_after", "transition_result"]),
                          ("REPLAY", 4, 8, ["applied_ref", "state_after"]), ("REAPPLY", 5, 9, [])])
        self.assertEqual(s["plan_hash"], self.plan.plan_hash)

    def test_repr_summary_and_errors_show_no_url_value_or_free_text(self):
        w = self.w
        rows = [dict(r, note=URL, source_url=URL) for r in w.ledger]
        plan = Z.prepare_restore_plan(self.h, R.point(self.b, 1), R.ops_of(self.b, 1, MAPPING), w.sessions, rows, w.series,
                                      D[5], "r4-1", R.WHEN)
        blob = repr(plan) + repr(plan.summary()) + repr(self.res) + repr(plan.to_dict()["plan_hash"])
        for banned in ("example.invalid", "secret", "27.0", "28.0", "110.0", "observed_at", "current_fg_value", "record_id"):
            self.assertNotIn(banned, blob, banned)
        self.assertNotIn("example.invalid", repr(plan.to_dict()))        # the extra ledger columns were never kept
        ops = R.ops_of(self.b, 1, MAPPING)
        errors = [
            T.refusal(Z.prepare_restore_plan, self.h, R.point(self.b, 1), ops, w.sessions, w.ledger, w.series, D[5], URL, R.WHEN),
            T.refusal(Z.prepare_restore_plan, self.h, R.point(self.b, 1), ops, w.sessions, w.ledger, w.series, D[5], "r4-1", URL),
            T.refusal(Z.prepare_restore_plan, self.h, R.point(self.b, 1), ops, w.sessions, [{"record_id": URL}], w.series, D[5], "r4-1", R.WHEN),
            T.refusal(Z.prepare_restore_plan, self.h, {"seq": URL, "event_hash": URL}, ops, w.sessions, w.ledger, w.series, D[5], "r4-1", R.WHEN),
            T.refusal(Z.prepare_restore_plan, self.h, R.point(self.b, 1), [{"op": URL, "from_seq": 2}], w.sessions, w.ledger, w.series, D[5], "r4-1", R.WHEN),
            T.refusal(Z.prepare_restore_plan, self.h, R.point(self.b, 1), ops, w.sessions, w.ledger, w.series, URL, "r4-1", R.WHEN),
            T.refusal(Z.confirm_restore_plan, URL, URL, self.h, w.sessions, w.ledger, w.series),
            T.refusal(Z.confirm_restore_plan, self.plan, URL, self.h, w.sessions, w.ledger, w.series),
        ]
        for e in errors:
            self.assertNotIn("example.invalid", str(e) + repr(e.__dict__))
            self.assertNotIn("secret", str(e) + repr(e.__dict__))

    def test_the_result_has_no_batch_and_no_ledger(self):
        for name in ("batch", "ledger", "body", "records", "basis"):
            self.assertFalse(hasattr(self.res, name), name)
        self.assertEqual(repr(self.res), "RestoreConfirmResult(status=CONFIRMED_IN_MEMORY, committed=False)")
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
        root = tempfile.mkdtemp(prefix="v2s3b4_root_")
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

    def test_the_api_has_no_batch_store_or_durability(self):
        self.assertEqual(sorted(Z.__all__), sorted(["prepare_restore_plan", "confirm_restore_plan", "RestorePlan",
                                                    "RestoreConfirmResult", "READY", "CONFIRMED_IN_MEMORY", "NO_CHANGE"]))
        for name in dir(Z):
            self.assertNotIn("batch", name.lower())
            self.assertNotIn("durab", name.lower())
        self.assertFalse(hasattr(Z, "commit"))


if __name__ == "__main__":
    unittest.main()
