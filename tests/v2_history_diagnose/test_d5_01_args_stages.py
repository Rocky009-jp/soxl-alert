"""D5-02 argument type, D5-03 utf8 stage, D5-04 json stage, D5-05 schema stage."""
import unittest

import d5_helpers as X
from d5_helpers import G, PersistenceError

UTF8 = {"stage": "utf8", "code": "unreadable", "field": "data", "rule": "utf8"}


class Bytes2(bytes):
    pass


class ArgumentType(unittest.TestCase):
    def test_only_exact_bytes_are_accepted(self):
        for bad in ("{}", bytearray(b"{}"), memoryview(b"{}"), None, 0, 1, [], {}, Bytes2(b"{}"), True):
            with self.assertRaises(PersistenceError) as cm:
                G.diagnose_history_bytes(bad)
            e = cm.exception
            self.assertEqual((e.code, e.field, e.rule), ("diagnosis_invalid", "data", "type"), repr(bad))

    def test_the_error_carries_no_value(self):
        with self.assertRaises(PersistenceError) as cm:
            G.diagnose_history_bytes("secret-looking text")
        self.assertNotIn("secret", str(cm.exception))
        self.assertNotIn("secret", repr(cm.exception.__dict__))

    def test_empty_bytes_are_unreadable_json_not_an_exception(self):
        d = X.diagnose(b"")
        self.assertEqual(d["status"], "UNREADABLE")
        self.assertEqual(d["failure"]["stage"], "json")
        self.assertEqual(d["raw_size"], 0)
        self.assertEqual(d["raw_sha256"], X.sha(b""))
        self.assertIsNone(d["schema_version"])
        self.assertIsNone(d["claimed"])
        self.assertIsNone(d["canonical_text"])
        self.assertIsNone(d["verified"])
        self.assertIsNone(d["discarded"])


class Utf8Stage(unittest.TestCase):
    def test_invalid_utf8(self):
        for raw in (b"\xff\xfe{}", b"\x80", b"{\"a\":\"\xc3\x28\"}"):
            with X.Spy() as spy:
                d = X.diagnose(raw)
            self.assertEqual(d["status"], "UNREADABLE", raw)
            self.assertEqual(d["failure"], UTF8)
            self.assertEqual(spy.calls, [])
            for key in ("schema_version", "canonical_text", "claimed", "verified", "discarded"):
                self.assertIsNone(d[key], key)

    def test_a_multibyte_character_cut_in_the_middle(self):
        good = X.history_file(X.ex_new())
        cut = good + "あ".encode("utf-8")[:2]
        d = X.diagnose(cut)
        self.assertEqual(d["failure"], UTF8)
        self.assertEqual(d["raw_size"], len(cut))

    def test_a_bom_passes_utf8_and_fails_in_json(self):
        good = X.history_file(X.ex_new())
        d = X.diagnose(b"\xef\xbb\xbf" + good)
        self.assertEqual(d["status"], "UNREADABLE")
        self.assertEqual(d["failure"]["stage"], "json")
        self.assertEqual((d["failure"]["code"], d["failure"]["field"], d["failure"]["rule"]),
                         ("history_invalid", "history", "json"))
        self.assertEqual(d["raw_size"], len(good) + 3)
        self.assertIsNone(d["canonical_text"])


class JsonStage(unittest.TestCase):
    def assert_json_failure(self, raw, rule):
        with X.Spy() as spy:
            d = X.diagnose(raw)
        self.assertEqual(d["status"], "UNREADABLE", raw[:40])
        self.assertEqual(d["failure"], {"stage": "json", "code": "history_invalid", "field": "history", "rule": rule})
        self.assertEqual(spy.calls, [], "no checker call after a JSON failure")
        self.assertIsNone(d["claimed"])
        self.assertIsNone(d["verified"])
        self.assertIsNone(d["discarded"])
        self.assertIsNone(d["canonical_text"])
        self.assertIsNone(d["schema_version"])

    def test_a_cut_json(self):
        good = X.history_file(X.ex_new())
        for n in (1, 10, len(good) // 2, len(good) - 1):
            self.assert_json_failure(good[:n], "json")

    def test_duplicate_keys(self):
        self.assert_json_failure(b'{"a":1,"a":2}', "json")
        good = X.history_file(X.ex_new()).decode("utf-8")
        dup = good.replace('"core_sha"', '"schema_version":2,"core_sha"', 1)
        self.assert_json_failure(dup.encode("utf-8"), "json")

    def test_non_finite_numbers(self):
        for lit in (b"NaN", b"Infinity", b"-Infinity"):
            self.assert_json_failure(b'{"schema_version":2,"x":' + lit + b"}", "json")

    def test_a_number_that_overflows_to_infinity(self):
        self.assert_json_failure(b'{"x":1e999}', "json_number")

    def test_depth_beyond_the_limit(self):
        self.assert_json_failure(b"[" * 60 + b"]" * 60, "json_depth")
        self.assert_json_failure(b'{"a":' * 50 + b"1" + b"}" * 50, "json_depth")

    def test_a_huge_integer_follows_the_existing_decoder(self):
        raw = b'{"x":' + b"9" * 5000 + b"}"
        try:
            X.V.decode_history(raw.decode("utf-8"))
        except PersistenceError as exc:                      # Python with the integer digit limit
            self.assert_json_failure(raw, exc.rule)
        else:                                               # an older Python reads it: the schema stage then refuses
            d = X.diagnose(raw)
            self.assertEqual(d["failure"]["stage"], "schema")
            self.assertEqual(d["status"], "UNREADABLE")

    def test_broken_json_is_never_rescued(self):
        b = X.ex_new()
        good = X.history_file(b)
        # the first four records are intact, the file is cut inside the fifth: still no record is reported
        cut_at = good.index(b'"seq":4')
        d = X.diagnose(good[:cut_at])
        self.assertEqual(d["status"], "UNREADABLE")
        self.assertIsNone(d["verified"])
        self.assertIsNone(d["discarded"])


class SchemaStage(unittest.TestCase):
    def assert_schema_failure(self, raw, code, field, rule, claimed=True):
        with X.Spy() as spy:
            d = X.diagnose(raw)
        self.assertEqual(d["status"], "UNREADABLE")
        self.assertEqual(d["failure"], {"stage": "schema", "code": code, "field": field, "rule": rule})
        self.assertEqual(spy.calls, [], "the prefix search must not start")
        self.assertIsNone(d["schema_version"])
        self.assertIsNone(d["verified"])
        self.assertIsNone(d["discarded"])
        self.assertIsInstance(d["canonical_text"], bool)
        if claimed:
            self.assertIsNotNone(d["claimed"])
        else:
            self.assertIsNone(d["claimed"])
        return d

    def test_a_top_level_that_is_not_an_object(self):
        for raw in (b"[]", b'"text"', b"12", b"null", b"true", b"[1,2,3]"):
            self.assert_schema_failure(raw, "history_invalid", "history", "shape", claimed=False)

    def test_schema_version_values(self):
        events = X.ex_new().events
        for value in (0, 3, 1.5, True, False, "2", "1", None, [], 2.0):
            doc = X.H.header(X.deep(events))
            doc["schema_version"] = value
            d = self.assert_schema_failure(X.doc_bytes(doc), "unsupported_schema", "schema_version", None)
            self.assertEqual(d["claimed"]["schema_version"], value if type(value) is int else None, repr(value))

    def test_a_missing_schema_version(self):
        doc = X.H.header(X.deep(X.ex_new().events))
        del doc["schema_version"]
        self.assert_schema_failure(X.doc_bytes(doc), "unsupported_schema", "schema_version", None)

    def test_core_sha_differs_in_both_versions(self):
        for sv in (2, 1):
            doc = X.H.header(X.deep(X.ex_new().events))
            doc["schema_version"] = sv
            doc["core_sha"] = "f" * 40
            d = self.assert_schema_failure(X.doc_bytes(doc), "unsupported_schema", "core_sha", None)
            self.assertIs(d["claimed"]["core_sha_matches"], False)
            self.assertEqual(d["claimed"]["schema_version"], sv)

    def test_core_sha_of_the_wrong_type(self):
        for value in (None, 7, ["x"], {}):
            doc = X.H.header(X.deep(X.ex_new().events))
            doc["core_sha"] = value
            d = self.assert_schema_failure(X.doc_bytes(doc), "unsupported_schema", "core_sha", None)
            self.assertIsNone(d["claimed"]["core_sha_matches"])

    def test_a_different_core_sha_does_not_start_a_prefix_search_even_if_a_rebuilt_header_would_pass(self):
        events = X.ex_new().events
        # independent fact: with the correct header the very same records pass the unchanged checker
        X.V.validate_history(X.V.History.from_dict(X.H.header(X.deep(events))))
        d = self.assert_schema_failure(X.file_of(events, core_sha="1" * 40), "unsupported_schema", "core_sha", None)
        self.assertEqual(d["claimed"]["event_count"], len(events))

    def test_schema_failure_still_reports_canonical_text(self):
        doc = X.H.header(X.deep(X.ex_new().events))
        doc["schema_version"] = 3
        self.assertTrue(X.diagnose(X.doc_bytes(doc))["canonical_text"])
        self.assertFalse(X.diagnose(X.indented(X.doc_bytes(doc)))["canonical_text"])


if __name__ == "__main__":
    unittest.main()
