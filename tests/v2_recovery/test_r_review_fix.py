"""Review fixes R-01 / R-02 (and the optional P-01 / P-02): an unverified plan shows nothing it was given, a hostile
plan dict ends in the fixed error, and the request hash is pinned by an independent expectation.

The marker is a reserved-domain synthetic string; nothing here needs a real URL, a secret or a network.
"""
import hashlib
import json
import sys
import unittest

import r_helpers as H
from r_helpers import D, R
from v2_persistence.errors import PersistenceError

MARKER = "https://example.invalid/SYNTHETIC_REVIEW_MARKER"


def digit_limit():
    return getattr(sys, "get_int_max_str_digits", lambda: 0)()


class Base(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.extra = H.P.obs("B1", D[1], 40.0, hour=21)
        self.ledger = list(self.w.ledger) + [self.extra]
        self.cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.extra)])]
        self.plan = H.plan_for(self.w, self.rs, self.cmds, self.ledger, D[1])

    def confirm(self, plan, hash_=None):
        return R.confirm_resolution_plan(plan, plan.plan_hash if hash_ is None else hash_, self.w.snap(), self.rs,
                                         self.w.sessions, self.ledger)

    def rehash(self, data):
        data["plan_hash"] = hashlib.sha256(H.cj(data["basis"]).encode("utf-8")).hexdigest()
        return data


class R01UnverifiedDisplay(Base):
    PLACES = {
        "status": lambda b: b.update(status=MARKER),
        "request_id": lambda b: b.update(request_id=MARKER),
        "check_d": lambda b: b.update(check_d=MARKER),
        "command_d": lambda b: b["commands"][0].update(d=MARKER),
        "command_kind": lambda b: b["commands"][0].update(kind=MARKER),
        "command_variant": lambda b: b["commands"][0].update(variant=MARKER),
        "command_fingerprints": lambda b: b["commands"][0].update(record_fingerprints=MARKER),
        "excluded": lambda b: b.update(excluded_fingerprints=MARKER),
        "supplemented": lambda b: b.update(supplemented=MARKER),
        "commands_not_a_list": lambda b: b.update(commands=MARKER),
        "command_not_a_dict": lambda b: b.update(commands=[MARKER]),
    }

    def test_free_text_in_any_displayed_field_is_never_shown(self):
        for name, mutate in self.PLACES.items():
            with self.subTest(name):
                data = self.plan.to_dict()
                mutate(data["basis"])
                value = R.ResolutionPlan.from_dict(data)
                self.assertNotIn(MARKER, repr(value))
                self.assertNotIn(MARKER, str(value))
                self.assertEqual(repr(value), "ResolutionPlan(?)")
                with self.assertRaises(PersistenceError) as cm:
                    value.summary()
                self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.rule),
                                 ("resolution_invalid", "plan", "plan_shape"))
                self.assertNotIn(MARKER, str(cm.exception) + repr(cm.exception))

    def test_the_plan_hash_itself_is_checked_before_it_is_shown(self):
        for bad in (MARKER, "A" * 64, "a" * 63, 5, None):
            with self.subTest(repr(bad)[:20]):
                value = R.ResolutionPlan.from_dict(dict(self.plan.to_dict(), plan_hash=bad))
                self.assertNotIn(MARKER, repr(value))
                self.assertEqual(repr(value), "ResolutionPlan(?)")
                H.expect_rule(self, "plan_shape", value.summary)

    def test_missing_keys_and_wrong_types_give_the_fixed_error_not_key_or_type_error(self):
        for basis in ({}, {"status": "READY"}, {"commands": []}, [], "x", 5, None):
            with self.subTest(repr(basis)):
                value = R.ResolutionPlan.from_dict({"basis": basis, "plan_hash": "a" * 64})
                self.assertEqual(repr(value), "ResolutionPlan(?)")
                H.expect_rule(self, "plan_shape", value.summary)
        data = self.plan.to_dict()
        del data["basis"]["commands"]
        H.expect_rule(self, "plan_shape", R.ResolutionPlan.from_dict(data).summary)

    def test_fields_that_are_not_displayed_do_not_change_the_display(self):
        data = self.plan.to_dict()
        for key in ("reason_code", "requested_at", "snapshot_digest", "ledger_digest", "candidate_digest",
                    "expected_head_hash", "operation"):
            data["basis"][key] = MARKER
        value = R.ResolutionPlan.from_dict(data)
        self.assertEqual(value.summary(), dict(self.plan.summary(), plan_hash=self.plan.plan_hash))
        self.assertNotIn(MARKER, repr(value) + repr(value.summary()))

    def test_a_valid_plan_keeps_its_whitelist_and_repr(self):
        s = self.plan.summary()
        self.assertEqual(set(s), {"status", "request_id", "check_d", "commands", "excluded", "supplemented",
                                  "state_unchanged", "committed", "plan_hash"})
        self.assertEqual(s["status"], "READY")
        self.assertEqual(s["commands"], [{"kind": "ACK", "variant": "ADDED", "d": D[1], "fingerprints": 1}])
        self.assertEqual(repr(self.plan), "ResolutionPlan(status=READY, commands=1, plan_hash=%s)"
                         % self.plan.plan_hash[:12])
        again = R.ResolutionPlan.from_dict(self.plan.to_dict())
        self.assertEqual(again.summary(), s)
        self.assertEqual(self.confirm(again).status, "CONFIRMED_IN_MEMORY")

    def test_status_property_is_only_a_known_status(self):
        data = self.plan.to_dict()
        data["basis"]["status"] = MARKER
        self.assertIsNone(R.ResolutionPlan.from_dict(data).status)
        self.assertEqual(self.plan.status, "READY")

    def test_a_safe_display_does_not_make_a_forged_plan_confirmable(self):
        for name, mutate in self.PLACES.items():
            with self.subTest(name):
                data = self.plan.to_dict()
                mutate(data["basis"])
                for variant in (data, self.rehash(json.loads(json.dumps(data)))):
                    forged = R.ResolutionPlan.from_dict(variant)
                    H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged)
                    H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged, forged.plan_hash)

    def test_no_confirmation_is_needed_to_show_a_plan(self):
        # displaying never calls the checks of confirm_resolution_plan, so no store or input is needed
        self.assertIn("READY", repr(R.ResolutionPlan.from_dict(self.plan.to_dict())))


class R02HostileDictionaries(Base):
    def test_a_deeply_nested_dictionary_ends_in_the_fixed_error(self):
        data = self.plan.to_dict()
        node = {}
        data["basis"] = node
        for _ in range(1200):
            node["x"] = {}
            node = node["x"]
        with self.assertRaises(PersistenceError) as cm:
            R.ResolutionPlan.from_dict(data)
        self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.rule),
                         ("resolution_invalid", "plan", "json_depth"))
        self.assertIsNone(cm.exception.__cause__)
        self.assertTrue(cm.exception.__suppress_context__ or cm.exception.__context__ is None)

    def test_a_deep_list_and_a_deep_value_inside_a_command_too(self):
        data = self.plan.to_dict()
        deep = []
        node = deep
        for _ in range(1200):
            nxt = []
            node.append(nxt)
            node = nxt
        data["basis"]["commands"][0]["record_fingerprints"] = deep
        H.expect_rule(self, "json_depth", R.ResolutionPlan.from_dict, data)

    def test_the_input_is_not_copied_before_it_is_checked(self):
        import copy
        data = self.plan.to_dict()
        node = {}
        data["basis"] = node
        for _ in range(1200):
            node["x"] = {}
            node = node["x"]
        calls = []
        real = copy.deepcopy
        copy.deepcopy = lambda *a, **k: calls.append(1) or real(*a, **k)
        try:
            with self.assertRaises(PersistenceError):
                R.ResolutionPlan.from_dict(data)
        finally:
            copy.deepcopy = real
        self.assertEqual(calls, [])

    def test_an_integer_too_long_for_text_ends_in_the_fixed_error(self):
        data = self.plan.to_dict()
        data["basis"]["request_id"] = 10 ** 5000
        limit = digit_limit()
        if limit and limit < 5001:
            with self.assertRaises(PersistenceError) as cm:
                R.ResolutionPlan.from_dict(data)
            self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.rule),
                             ("resolution_invalid", "plan", "json_number"))
            self.assertIsNone(cm.exception.__cause__)
            self.assertTrue(cm.exception.__suppress_context__)             # the Python error is not chained
        else:
            # this interpreter has no integer conversion limit: the value is a plan that cannot be confirmed
            forged = R.ResolutionPlan.from_dict(data)
            H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged)

    def test_a_huge_integer_in_other_places_is_handled_the_same_way(self):
        for place in ("check_d", "expected_head_seq", "candidate_digest"):
            with self.subTest(place):
                data = self.plan.to_dict()
                data["basis"][place] = 10 ** 5000
                limit = digit_limit()
                if limit and limit < 5001:
                    H.expect_rule(self, "json_number", R.ResolutionPlan.from_dict, data)
                else:
                    H.expect_code(self, "resolution_plan_mismatch", self.confirm, R.ResolutionPlan.from_dict(data))

    def test_values_inside_the_limits_are_still_accepted_and_do_not_change_the_hash(self):
        data = self.plan.to_dict()
        deep = {}
        node = deep
        for _ in range(30):
            node["x"] = {}
            node = node["x"]
        data["basis"]["note"] = deep
        limit = digit_limit()
        data["basis"]["request_id"] = 10 ** ((limit - 2) if limit else 4000)         # just inside the conversion limit
        value = R.ResolutionPlan.from_dict(data)
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, value)          # unknown key: not a plan
        self.assertEqual(R.ResolutionPlan.from_dict(self.plan.to_dict()).plan_hash, self.plan.plan_hash)
        expected = hashlib.sha256(json.dumps(self.plan.basis, sort_keys=True, separators=(",", ":"),
                                             ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(self.plan.plan_hash, expected)

    def test_process_wide_limits_are_not_changed(self):
        before = (sys.getrecursionlimit(), digit_limit())
        for fn in (self.test_a_deeply_nested_dictionary_ends_in_the_fixed_error,
                   self.test_an_integer_too_long_for_text_ends_in_the_fixed_error):
            fn()
        self.assertEqual((sys.getrecursionlimit(), digit_limit()), before)

    def test_the_other_input_errors_of_from_dict_are_unchanged(self):
        H.expect_rule(self, "plan_shape", R.ResolutionPlan.from_dict, {"basis": {}})
        H.expect_rule(self, "plan_shape", R.ResolutionPlan.from_dict, "x")
        H.expect_rule(self, "json_number", R.ResolutionPlan.from_dict, {"basis": float("nan"), "plan_hash": "a"})
        H.expect_rule(self, "json_type", R.ResolutionPlan.from_dict, {"basis": (1,), "plan_hash": "a"})
        H.expect_rule(self, "json_key", R.ResolutionPlan.from_dict, {"basis": {1: 2}, "plan_hash": "a"})


class P01BadRequestedAt(Base):
    BAD = "0001-01-01T00:00:00+23:00"

    def test_the_text_predicate_never_raises(self):
        from v2_recovery.common import is_requested_text
        for text in (self.BAD, "9999-12-31T23:59:59-23:59", "x", "", None, 5):
            with self.subTest(repr(text)):
                self.assertIs(is_requested_text(text), False)

    def test_confirm_calls_it_a_plan_mismatch(self):
        data = self.plan.to_dict()
        data["basis"]["requested_at"] = self.BAD
        forged = R.ResolutionPlan.from_dict(self.rehash(data))
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged)

    def test_a_stored_record_with_it_is_a_resolution_error(self):
        res = H.run(self.w, self.rs, self.cmds, self.ledger, D[1])

        def mutate(records):
            records[0]["request_basis"]["requested_at"] = self.BAD
            records[0]["requested_at"] = self.BAD
        forged = H.forge(res.resolutions, mutate)
        H.expect_rule(self, "request_basis", R.validate_resolutions, self.snap, forged)


class P02RequestHashIsPinned(Base):
    def expected(self, request_id, commands, check_d, reason_code):
        text = json.dumps({"request_id": request_id, "commands": commands, "check_d": check_d,
                           "reason_code": reason_code}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def test_request_hash_equals_an_independent_computation(self):
        b = self.plan.basis
        self.assertEqual(b["request_hash"], self.expected(b["request_id"], b["commands"], b["check_d"],
                                                          b["reason_code"]))
        self.assertEqual(b["request_hash"],
                         self.expected("req-1", [dict(self.cmds[0], record_fingerprints=sorted(
                             self.cmds[0]["record_fingerprints"]))], D[1], "ACKNOWLEDGE_LEDGER_CHANGE"))

    def test_stored_records_carry_the_same_independent_value(self):
        res = H.run(self.w, self.rs, self.cmds, self.ledger, D[1])
        rec = res.resolutions.to_dict()["records"][0]
        basis = rec["request_basis"]
        self.assertEqual(rec["request_hash"], self.expected(basis["request_id"], basis["commands"],
                                                            basis["check_d"], basis["reason_code"]))
        self.assertNotIn("requested_at", rec["request_hash"])


if __name__ == "__main__":
    unittest.main()
