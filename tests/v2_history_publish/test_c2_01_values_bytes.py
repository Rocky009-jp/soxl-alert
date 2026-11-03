"""C2-02 (the values) and C2-13 (the byte form)."""
import json
import unittest

import c2_helpers as X

U, V = X.U, X.V

BODY_KEYS = {"operation", "mode", "source", "d", "request_id", "plan_hash", "expected", "source_v1", "records",
             "candidate_history", "candidate_head_seq", "candidate_head_hash", "candidate_digest",
             "candidate_state_digest"}
MODE_OF = {"DAILY": "APPEND", "RESOLUTION": "APPEND", "RESTART": "APPEND", "RESTORE": "APPEND", "GENESIS": "CREATE",
           "MIGRATION": "CREATE", "ADOPTION": "REPLACE"}


class PublicationValue(unittest.TestCase):
    """C2-02."""

    @classmethod
    def setUpClass(cls):
        cls.cases = X.every_case()

    def test_the_body_has_the_fourteen_keys_the_operation_and_the_mode_of_its_source(self):
        self.assertEqual({c.source for c in self.cases}, set(MODE_OF))
        for c in self.cases:
            with self.subTest(source=c.source):
                body = c.pub.body
                self.assertEqual(set(body), BODY_KEYS)
                self.assertEqual(body["operation"], "soxl-v2-history-publication/1")
                self.assertEqual((body["source"], body["mode"]), (c.source, MODE_OF[c.source]))
                self.assertEqual((c.pub.source, c.pub.mode), (c.source, MODE_OF[c.source]))

    def test_the_hash_is_the_sha256_of_the_canonical_body(self):
        import hashlib
        for c in self.cases:
            with self.subTest(source=c.source):
                expected = hashlib.sha256(X.cj(c.pub.body).encode("utf-8")).hexdigest()
                self.assertEqual(c.pub.publication_hash, expected)
                self.assertEqual(c.pub.to_dict(), {"body": c.pub.body, "publication_hash": expected})

    def test_the_fields_of_each_source_follow_the_table(self):
        by = {c.source: c.pub.body for c in self.cases}
        for source in ("DAILY", "RESOLUTION", "RESTART", "RESTORE"):
            b = by[source]
            self.assertEqual(set(b["expected"]), {"head_seq", "head_hash", "history_digest"})
            self.assertIsInstance(b["records"], list)
            self.assertGreaterEqual(len(b["records"]), 1)
            self.assertIsNone(b["candidate_history"])
            self.assertIsNone(b["source_v1"])
        self.assertEqual(by["DAILY"]["d"], X.D[2])
        self.assertEqual((by["DAILY"]["request_id"], by["DAILY"]["plan_hash"]), (None, None))
        for source in ("RESOLUTION", "RESTART", "RESTORE", "MIGRATION", "ADOPTION"):
            self.assertIsNone(by[source]["d"])
            self.assertIsInstance(by[source]["request_id"], str)
            self.assertRegex(by[source]["plan_hash"], r"^[0-9a-f]{64}$")
        for source in ("GENESIS", "MIGRATION"):
            b = by[source]
            self.assertIsNone(b["expected"])
            self.assertIsNone(b["records"])
            self.assertIsInstance(b["candidate_history"], dict)
        self.assertEqual((by["GENESIS"]["request_id"], by["GENESIS"]["plan_hash"], by["GENESIS"]["source_v1"]),
                         (None, None, None))
        self.assertEqual(set(by["MIGRATION"]["source_v1"]), {"raw_sha256", "raw_size"})
        self.assertEqual(set(by["ADOPTION"]["expected"]), {"raw_sha256", "raw_size"})
        self.assertIsNone(by["ADOPTION"]["records"])
        self.assertIsNone(by["ADOPTION"]["source_v1"])
        self.assertIsInstance(by["ADOPTION"]["candidate_history"], dict)

    def test_the_candidate_fields_are_those_of_the_candidate_of_the_confirming_step(self):
        import hashlib
        for c in self.cases:
            with self.subTest(source=c.source):
                body = c.pub.body
                chk = V.validate_history(c.candidate)
                self.assertEqual(body["candidate_head_seq"], chk.head_seq)
                self.assertEqual(body["candidate_head_hash"], chk.head_hash)
                self.assertEqual(body["candidate_digest"], chk.history_digest)
                state = X.cj(c.candidate.current_state).encode("utf-8")
                self.assertEqual(body["candidate_state_digest"], hashlib.sha256(state).hexdigest())

    def test_committed_is_always_false_and_there_is_no_from_dict(self):
        for c in self.cases:
            self.assertIs(c.pub.committed, False)
        self.assertFalse(hasattr(U.HistoryPublication, "from_dict"))
        self.assertFalse(hasattr(U.Reconciliation, "from_dict"))
        self.assertFalse(hasattr(U.HistoryPublication, "committable"))

    def test_the_value_is_immutable_and_cannot_be_built_directly(self):
        pub = self.cases[0].pub
        for name in ("body", "mode", "source", "committed", "publication_hash", "x", "_text", "_view"):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    setattr(pub, name, 1)
                with self.assertRaises(AttributeError):
                    delattr(pub, name)
        with self.assertRaises(TypeError):
            U.HistoryPublication()
        with self.assertRaises(TypeError):
            U.HistoryPublication({"body": {}})
        with self.assertRaises(TypeError):
            U.Reconciliation()

    def test_what_is_handed_out_and_taken_in_is_a_copy(self):
        c = X.day_case()
        before = c.pub.publication_hash
        body = c.pub.body
        body["records"][0]["d"] = "tampered"
        body["expected"]["head_seq"] = 99
        c.pub.to_dict()["body"]["source"] = "x"
        c.pub.summary()["mode"] = "x"
        self.assertEqual(c.pub.body["expected"]["head_seq"], 1)
        self.assertEqual(c.pub.body["records"], c.candidate.events[2:])
        self.assertEqual(c.pub.publication_hash, before)
        # what was passed to the builder is not kept: changing the ledger of the world afterwards changes nothing
        w = c.w
        w.ledger.append(X.P.obs("late", X.D[3], 1.0))
        self.assertEqual(c.pub.body["records"], c.candidate.events[2:])
        # the history that the publication leaves is a new object each time
        self.assertIsNot(c.pub.body, c.pub.body)

    def test_equal_inputs_make_equal_values(self):
        a, b = X.day_case(), X.day_case()
        self.assertEqual(a.pub, b.pub)
        self.assertEqual(hash(a.pub), hash(b.pub))
        self.assertNotEqual(a.pub, X.restart_case().pub)
        self.assertNotEqual(a.pub, a.pub.to_dict())

    def test_summary_and_repr_are_a_whitelist(self):
        allowed = {"mode", "source", "d", "request_id", "records", "candidate_head_seq", "committed",
                   "publication_hash"}
        banned = ("27.0", "31.0", "22.0", "input_hash", "state_after", "events", "ledger", "confirmed_inputs",
                  "decision", "fear", "snapshot.json", "history.json", ".json", "ack", "transition_result")
        for c in self.cases:
            with self.subTest(source=c.source):
                summary = c.pub.summary()
                self.assertEqual(set(summary), allowed)
                self.assertEqual(summary["mode"], MODE_OF[c.source])
                self.assertEqual(summary["source"], c.source)
                self.assertIs(summary["committed"], False)
                self.assertEqual(summary["publication_hash"], c.pub.publication_hash)
                shown = json.dumps(summary, sort_keys=True) + repr(c.pub) + str(c.pub)
                for word in banned:
                    self.assertNotIn(word, shown.lower() if word.islower() else shown)
                self.assertLess(len(repr(c.pub)), 120)

    def test_the_summary_of_a_day_names_the_day_and_a_plan_names_its_request_only(self):
        self.assertEqual(X.day_case().pub.summary()["d"], X.D[2])
        s = X.restart_case().pub.summary()
        self.assertEqual((s["d"], s["request_id"], s["records"]), (None, "q1", 1))
        self.assertEqual(X.genesis_case().pub.summary()["records"], None)

    def test_a_reconciliation_holds_the_outcome_and_the_hash_only(self):
        c = X.day_case()
        r = c.reconcile()
        self.assertEqual(r.to_dict(), {"outcome": "NOT_PUBLISHED", "publication_hash": c.pub.publication_hash})
        self.assertEqual((r.outcome, r.publication_hash, r.committed), ("NOT_PUBLISHED", c.pub.publication_hash, False))
        self.assertEqual(repr(r), "Reconciliation(outcome=NOT_PUBLISHED)")
        with self.assertRaises(AttributeError):
            r.outcome = "PUBLISHED"
        with self.assertRaises(AttributeError):
            del r.publication_hash
        with self.assertRaises(AttributeError):
            r.x = 1
        self.assertEqual(r, c.reconcile())
        self.assertNotEqual(r, X.restart_case().reconcile())

    def test_the_names_of_the_outcomes_and_the_modes(self):
        self.assertEqual((U.PUBLISHED, U.PUBLISHED_THEN_EXTENDED, U.NOT_PUBLISHED, U.CONFLICT),
                         ("PUBLISHED", "PUBLISHED_THEN_EXTENDED", "NOT_PUBLISHED", "CONFLICT"))
        self.assertEqual((U.APPEND, U.CREATE, U.REPLACE), ("APPEND", "CREATE", "REPLACE"))
        self.assertEqual((U.DAILY, U.RESOLUTION, U.RESTART, U.RESTORE, U.GENESIS, U.MIGRATION, U.ADOPTION),
                         tuple(MODE_OF))


class Bytes(unittest.TestCase):
    """C2-13."""

    @classmethod
    def setUpClass(cls):
        cls.c = X.day_case()

    def test_history_bytes_is_the_canonical_text_in_utf8_without_bom_or_newline(self):
        h = self.c.candidate
        data = U.history_bytes(h)
        self.assertIs(type(data), bytes)
        self.assertEqual(data, V.encode_history(h).encode("utf-8"))
        self.assertEqual(data, X.cj(h.to_dict()).encode("utf-8"))
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertFalse(data.endswith(b"\n"))
        self.assertEqual(data, X.file_bytes(h))

    def test_history_bytes_takes_a_history_only(self):
        for bad in (None, {}, "x", b"x", self.c.pub, self.c.candidate.to_dict()):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.history_bytes, bad), ("history_invalid", "history", "type"))

    def test_what_is_written_is_read_back_to_the_same_history(self):
        for make in X.ALL_CASES:
            c = make()
            with self.subTest(source=c.source):
                history, check = U.read_history_bytes(U.history_bytes(c.candidate))
                self.assertEqual(history, c.candidate)
                self.assertEqual(check, V.validate_history(c.candidate))

    def test_read_takes_bytes_only(self):
        data = self.c.current

        class Sub(bytes):
            pass
        for bad in (data.decode("utf-8"), bytearray(data), memoryview(data), None, 3, [data], Sub(data)):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.read_history_bytes, bad), ("history_invalid", "history", "type"))

    def test_the_read_is_strict(self):
        data = self.c.current
        cases = {"bom": (b"\xef\xbb\xbf" + data, "json"), "not utf-8": (b"\xff\xfe\x00", "utf8"),
                 "cut": (data[:-3], "json"), "empty": (b"", "json"), "not an object": (b"[]", "shape"),
                 "duplicate key": (b'{"a":1,"a":2}', "json"), "nan": (data.replace(b'"seq":0', b'"seq":NaN', 1), "json")}
        for name, (blob, rule) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(X.err(U.read_history_bytes, blob), ("history_invalid", "history", rule))

    def test_a_valid_text_that_is_not_canonical_is_read_and_identified_by_its_canonical_digest(self):
        pretty = X.indented(self.c.history)
        self.assertNotEqual(pretty, self.c.current)
        history, check = U.read_history_bytes(pretty)
        self.assertEqual(history, self.c.history)
        self.assertEqual(check.history_digest, V.validate_history(self.c.history).history_digest)
        # a newline at the end is a valid text as well
        self.assertEqual(U.read_history_bytes(self.c.current + b"\n")[1].head_seq, 1)

    def test_a_text_that_is_valid_json_but_not_a_valid_history_is_refused(self):
        h = self.c.history.to_dict()
        h["head_hash"] = "0" * 64
        code = X.err(U.read_history_bytes, json.dumps(h).encode("utf-8"))
        self.assertEqual(code[:2], ("history_invalid", "history"))
        h = self.c.history.to_dict()
        h["events"][1]["state_after"]["streak"] = 123
        self.assertEqual(X.err(U.read_history_bytes, json.dumps(h).encode("utf-8"))[:2], ("history_invalid", "history"))

    def test_the_raw_identity_is_computed_from_the_bytes(self):
        for data in (b"", b"abc", self.c.current, b"\xff" * 1000):
            with self.subTest(size=len(data)):
                self.assertEqual(U.raw_identity(data), X.raw_of(data))
        self.assertEqual(set(U.raw_identity(b"x")), {"raw_sha256", "raw_size"})
        self.assertEqual(U.raw_identity(b"abc")["raw_sha256"],
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_the_raw_identity_takes_bytes_only(self):
        for bad in ("abc", bytearray(b"abc"), memoryview(b"abc"), None, 1):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.raw_identity, bad), ("history_invalid", "history", "type"))

    def test_the_identity_of_a_damaged_file_is_the_identity_of_its_bytes(self):
        a = X.adoption_case()
        self.assertEqual(U.raw_identity(a.data), X.raw_of(a.data))
        self.assertNotEqual(U.raw_identity(a.data), U.raw_identity(U.history_bytes(a.candidate)))


if __name__ == "__main__":
    unittest.main()
