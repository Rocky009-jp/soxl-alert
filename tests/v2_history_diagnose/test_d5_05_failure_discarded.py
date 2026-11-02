"""D5-12 failure and exceptions, D5-13 the discarded side."""
import json
import unittest

import d5_helpers as X
from d5_helpers import GD, PersistenceError
from v2_core.errors import CoreError

SECRET = "SECRET-VALUE-9f3"
FAILURE_KEYS = {"stage", "code", "field", "rule"}


class FailureShape(unittest.TestCase):
    def test_every_failure_has_exactly_four_keys_of_fixed_identifiers(self):
        b = X.ex_new()
        files = [X.file_of(X.with_hash(b.events, 6)), X.file_of(b.events, head_hash=X.ZERO), b"", b"\xff", b"[]",
                 X.file_of(b.events, schema_version=9), X.file_of(b.events, core_sha="x" * 40),
                 X.file_of(X.with_hash(b.events, 0)), X.v1_file(X.v1_world(2).snap())[:-3]]
        for data in files:
            d = X.diagnose(data)
            f = d["failure"]
            if d["status"] == "VALID":
                continue
            self.assertEqual(set(f), FAILURE_KEYS)
            self.assertIn(f["stage"], ("utf8", "json", "schema", "validate"))
            for key in ("code", "field", "rule"):
                value = f[key]
                self.assertTrue(value is None or (isinstance(value, str) and value.replace("_", "").replace(":", "")
                                                  .replace(".", "").isalnum()), (key, value))

    def test_failure_is_none_only_for_valid(self):
        b = X.ex_new()
        self.assertIsNone(X.diagnose(X.history_file(b))["failure"])
        for data in (X.file_of(X.with_hash(b.events, 6)), X.file_of(b.events, head_hash=X.ZERO), b"x"):
            self.assertIsNotNone(X.diagnose(data)["failure"])

    def test_failure_is_the_first_error_of_the_whole_file_not_of_the_last_prefix_tried(self):
        b = X.ex_m()
        data = X.file_of(X.with_hash(b.events, 7))
        self.assertEqual(X.full_error(data), ("history_invalid", "history", "event_hash"))
        d = X.diagnose(data)
        self.assertEqual(d["failure"], {"stage": "validate", "code": "history_invalid", "field": "history",
                                        "rule": "event_hash"})
        # the prefixes in between were refused for another rule (origin)
        with X.Spy() as spy:
            X.diagnose(data)
        self.assertIn(("history_invalid", "origin"), [(c[2], c[3]) for c in spy.calls])

    def test_a_failure_of_the_whole_file_that_is_not_in_the_damaged_record(self):
        b = X.ex_new()
        d = X.diagnose(X.file_of(b.events, current_state={}))
        self.assertEqual(d["failure"]["rule"], "current_state")
        self.assertEqual(d["verified"]["count"], len(b.events))


class StubbedCheckers(unittest.TestCase):
    """Exceptions the checkers could raise are turned into fixed identifiers. The checker names that diagnose really
    uses are replaced, and the exception text is a marker that must not appear anywhere in the report."""

    def run_with(self, version, raiser, data):
        name = "validate_history" if version == 2 else "validate_snapshot"
        original = getattr(GD, name)
        calls = []

        def stub(arg):
            calls.append(1)
            return raiser(arg, original, len(calls))

        setattr(GD, name, stub)
        try:
            return X.G.diagnose_history_bytes(data), calls
        finally:
            setattr(GD, name, original)

    def assert_clean(self, diag):
        self.assertNotIn(SECRET, X.cj(diag.to_dict()))
        self.assertNotIn(SECRET, repr(diag))
        self.assertNotIn(SECRET, diag.summary())

    def test_non_persistence_exceptions_become_malformed_of_the_version(self):
        b = X.ex_new()
        for exc in (KeyError(SECRET), TypeError(SECRET), ValueError(SECRET), AttributeError(SECRET),
                    IndexError(SECRET), OverflowError(SECRET), RecursionError(SECRET)):
            def raiser(_arg, _orig, _n, exc=exc):
                raise exc
            diag, _ = self.run_with(2, raiser, X.history_file(b))
            self.assertEqual(diag.status, "NO_VALID_PREFIX", repr(exc))
            self.assertEqual(diag.failure, {"stage": "validate", "code": "history_invalid", "field": "history",
                                            "rule": "malformed"})
            self.assert_clean(diag)
            snap = X.v1_world(2).snap()
            diag, _ = self.run_with(1, raiser, X.v1_file(snap))
            self.assertEqual(diag.failure, {"stage": "validate", "code": "snapshot_invalid", "field": "snapshot",
                                            "rule": "malformed"})
            self.assert_clean(diag)

    def test_a_core_error_gives_its_code_and_field_without_a_rule(self):
        def raiser(_arg, _orig, _n):
            raise CoreError("some_core_code", "some_field", SECRET)
        diag, _ = self.run_with(2, raiser, X.history_file(X.ex_new()))
        self.assertEqual(diag.failure, {"stage": "validate", "code": "some_core_code", "field": "some_field",
                                        "rule": None})
        self.assert_clean(diag)

    def test_a_persistence_error_gives_code_field_and_rule(self):
        def raiser(_arg, _orig, _n):
            raise PersistenceError("c_code", "c_field", SECRET, rule="c_rule")
        diag, _ = self.run_with(2, raiser, X.history_file(X.ex_new()))
        self.assertEqual(diag.failure, {"stage": "validate", "code": "c_code", "field": "c_field", "rule": "c_rule"})
        self.assert_clean(diag)

    def test_free_text_in_an_error_identifier_is_not_reported(self):
        malformed = {"stage": "validate", "code": "history_invalid", "field": "history", "rule": "malformed"}
        cases = [(("has space " + SECRET, "f", "r"), malformed),
                 (("c", "/etc/passwd", "r"), {"stage": "validate", "code": "c", "field": None, "rule": "r"}),
                 (("c", "f", "http://example.invalid/x"), {"stage": "validate", "code": "c", "field": "f", "rule": None}),
                 (("c" * 200, "f", "r"), malformed), (("", "f", "r"), malformed)]
        for (code, field, rule), expected in cases:
            def raiser(_arg, _orig, _n, code=code, field=field, rule=rule):
                raise PersistenceError(code, field, rule=rule)
            diag, _ = self.run_with(2, raiser, X.history_file(X.ex_new()))
            self.assertEqual(diag.failure, expected)
            text = X.cj(diag.to_dict())
            for forbidden in ("passwd", "example.invalid", SECRET):
                self.assertNotIn(forbidden, text)

    def test_an_exception_while_trying_a_prefix_does_not_stop_the_diagnosis(self):
        b = X.ex_new()
        n = len(b.events)
        data = X.file_of(X.with_hash(b.events, n - 1))           # k = n-1 would pass

        def raiser(arg, original, count):
            if count <= 3:                                        # the whole file, k = n, then k = n-1 explodes
                raise KeyError(SECRET)
            return original(arg)
        diag, calls = self.run_with(2, raiser, data)
        self.assertEqual(diag.status, "PREFIX_ONLY")
        self.assertEqual(diag.verified["count"], n - 2, "k = n-1 'did not pass', so the next k is the longest")
        self.assertEqual(diag.failure["rule"], "malformed", "the failure is the whole-file one")
        self.assert_clean(diag)

    def test_exceptions_on_every_prefix_end_in_no_valid_prefix(self):
        def raiser(_arg, _orig, _n):
            raise ValueError(SECRET)
        diag, calls = self.run_with(2, raiser, X.history_file(X.ex_new()))
        self.assertEqual(diag.status, "NO_VALID_PREFIX")
        self.assertEqual(len(calls), 1 + 7)
        self.assertEqual(diag.discarded["count"], 7)

    def test_a_real_malformed_input_never_raises(self):
        b = X.ex_new()
        for index, value in ((2, 5), (3, "x"), (1, None), (0, [])):
            events = X.deep(b.events)
            events[index] = value
            d = X.diagnose(X.file_of(events))
            self.assertIn(d["status"], ("PREFIX_ONLY", "NO_VALID_PREFIX"))


class Discarded(unittest.TestCase):
    def damaged(self):
        b = X.ex_new()
        events = X.deep(b.events)
        events[3]["event_hash"] = X.ZERO
        return b, events

    def test_items_have_five_keys(self):
        b, events = self.damaged()
        d = X.diagnose(X.file_of(events))
        self.assertEqual(set(d["discarded"]), {"from_index", "count", "items"})
        for item in d["discarded"]["items"]:
            self.assertEqual(set(item), {"index", "kind", "seq", "d", "request_id"})

    def test_unknown_kinds_and_invalid_values_are_null(self):
        b, events = self.damaged()
        events[3]["kind"] = "NOT_A_KIND"
        events[4]["kind"] = 5
        events[4]["seq"] = True
        events[5]["seq"] = "5"
        events[5]["d"] = "2026-13-45"
        events[6]["d"] = 20260310
        events[6]["seq"] = 6.0
        events[6]["request_id"] = {"x": 1}
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["verified"]["count"], 3)
        items = d["discarded"]["items"]
        self.assertEqual(items[0], {"index": 3, "kind": "?", "seq": 3, "d": events[3]["d"], "request_id": None})
        self.assertEqual(items[1], {"index": 4, "kind": "?", "seq": None, "d": events[4]["d"], "request_id": None})
        self.assertEqual(items[2], {"index": 5, "kind": "APPLY", "seq": None, "d": None, "request_id": None})
        self.assertEqual(items[3], {"index": 6, "kind": "APPLY", "seq": None, "d": None, "request_id": None})

    def test_request_id_is_given_only_when_it_is_a_valid_id(self):
        b = X.R4.ex_two_command_request()
        events = X.deep(b.events)
        events[3]["event_hash"] = X.ZERO                        # k = 3
        events[4]["request_id"] = "bad id with spaces"
        events[5]["request_id"] = ""
        d = X.diagnose(X.file_of(events))
        self.assertEqual([i["request_id"] for i in d["discarded"]["items"]], ["q1", None, None])

    def test_no_market_value_decision_free_text_or_resume_after_is_shown(self):
        b = X.ex_u()                                              # 0 GENESIS, 1 APPLY, 2 APPLY, 3 RESTART_UNKNOWN(q1)
        events = X.deep(b.events)
        events[1]["event_hash"] = X.ZERO                          # so everything after the genesis is discarded
        events[1]["note"] = SECRET + " free text"
        events[2]["confirmed_inputs"]["decision"]["record_id"] = SECRET + "-record"
        events[2]["confirmed_inputs"]["decision"]["current_fg_value"] = 54321.5
        events[2]["confirmed_inputs"]["row"]["soxx"] = 98765.25
        events[3]["resume_after"] = "2031-07-07"
        events[3]["reason_code"] = SECRET + "-reason"
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["verified"]["count"], 1)
        text = X.cj(d)
        for forbidden in (SECRET, "54321", "98765", "2031-07-07", "resume_after", "fixed_decision", "free text"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(d["discarded"]["items"][2], {"index": 3, "kind": "RESTART_UNKNOWN", "seq": 3, "d": None,
                                                     "request_id": "q1"})

    def test_the_summary_counts_kinds_and_the_first_and_last_date_only(self):
        b = X.ex_r()
        events = X.deep(b.events)
        events[9]["event_hash"] = X.ZERO
        diag = X.G.diagnose_history_bytes(X.file_of(events))
        s = diag.summary()
        items = diag.discarded["items"]
        counts = {}
        for item in items:
            counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        self.assertIn("discarded_kinds=" + ",".join("%s:%d" % (k, counts[k]) for k in sorted(counts)), s)
        dates = [i["d"] for i in items if i["d"]]
        self.assertIn("first_d=" + dates[0], s)
        self.assertIn("last_d=" + dates[-1], s)
        self.assertIn("discarded_count=%d" % len(items), s)
        self.assertIn("verified_count=%d" % diag.verified["count"], s)
        for item in items:
            if item["request_id"]:
                self.assertNotIn(item["request_id"], s, "request ids are not in the summary")


class JsonSafety(unittest.TestCase):
    def test_the_report_is_plain_json(self):
        b = X.ex_r()
        for data in (X.history_file(b), X.file_of(X.with_hash(b.events, 12)), b"{}", b"\xff"):
            d = X.diagnose(data)
            self.assertEqual(json.loads(X.cj(d)), d)


if __name__ == "__main__":
    unittest.main()
