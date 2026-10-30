"""H-02: the History value and its strict codec; schema and type refusals; make_history_genesis."""
import dataclasses
import json
import unittest

import h_helpers as H
from h_helpers import D, V

from v2_persistence.codec import Snapshot, sha256_text
from v2_persistence.recompute import validate_snapshot


class ValueBasics(unittest.TestCase):
    def setUp(self):
        self.b = H.example_u()
        self.h = self.b.history()

    def test_cannot_be_built_directly_or_changed(self):
        with self.assertRaises(TypeError):
            V.History()
        with self.assertRaises(AttributeError):
            self.h.head_seq = 1
        with self.assertRaises(AttributeError):
            del self.h._text

    def test_accessors_return_independent_copies(self):
        d = self.h.to_dict()
        d["events"][1]["d"] = "x"
        d["current_state"]["streak"] = 99
        ev = self.h.events
        ev.append({})
        ev[0]["kind"] = "X"
        st = self.h.current_state
        st["streak"] = 77
        self.assertEqual(self.h.to_dict(), self.b.history().to_dict())
        self.assertEqual(self.h.events[0]["kind"], "GENESIS")
        self.assertNotEqual(self.h.current_state["streak"], 77)

    def test_header_properties(self):
        self.assertEqual(self.h.schema_version, 2)
        self.assertEqual(self.h.head_seq, 3)
        self.assertEqual(self.h.head_hash, self.b.last["event_hash"])
        self.assertEqual(self.h.current_state, self.b.last["state_after"])
        self.assertEqual(self.h.digest, sha256_text(V.encode_history(self.h)))

    def test_equality_and_hash_follow_the_text(self):
        again = V.History.from_dict(self.h.to_dict())
        self.assertEqual(self.h, again)
        self.assertEqual(hash(self.h), hash(again))
        self.assertNotEqual(self.h, H.example_r().history())
        self.assertNotEqual(self.h, "text")

    def test_encode_decode_round_trip_and_type_refusals(self):
        text = V.encode_history(self.h)
        self.assertEqual(V.decode_history(text), self.h)
        self.assertEqual(json.loads(text)["schema_version"], 2)
        for fn, arg in ((V.encode_history, self.h.to_dict()), (V.encode_history, None), (V.decode_history, b"{}"),
                        (V.decode_history, None)):
            with self.subTest("%s/%s" % (fn.__name__, type(arg).__name__)):
                H.expect_error(self, "history_invalid", "type", fn, arg)

    def test_repr_hides_contents(self):
        self.assertRegex(repr(self.h), r"^History\(\d+ chars\)$")


class StrictCodec(unittest.TestCase):
    def setUp(self):
        self.text = V.encode_history(H.example_u().history())

    def test_duplicate_keys_are_refused(self):
        dup = '{"schema_version":2,"schema_version":2}'
        H.expect_error(self, "history_invalid", "json", V.decode_history, dup)

    def test_non_finite_numbers_are_refused(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token):
                H.expect_error(self, "history_invalid", "json", V.decode_history, '{"a":%s}' % token)
        with self.assertRaises(Exception) as cm:
            V.History.from_dict({"a": float("nan")})
        self.assertEqual(cm.exception.rule, "json_number")

    def test_non_json_text_is_refused(self):
        for bad in ("", "{", "[1,", "null null", "\x00"):
            with self.subTest(repr(bad)):
                H.expect_error(self, "history_invalid", "json", V.decode_history, bad)

    def test_values_that_are_not_json_are_refused(self):
        for value, rule in (({"a": {1, 2}}, "json_type"), ({"a": b"x"}, "json_type"), ({1: "a"}, "json_key"),
                            ({"a": object()}, "json_type")):
            with self.subTest(rule):
                H.expect_error(self, "history_invalid", rule, V.History.from_dict, value)

    def test_depth_beyond_the_limit_is_refused(self):
        deep = x = {}
        for _ in range(45):
            x["a"] = {}
            x = x["a"]
        H.expect_error(self, "history_invalid", "json_depth", V.History.from_dict, deep)
        nested = "[" * 5000 + "]" * 5000
        H.expect_error(self, "history_invalid", None, V.decode_history, nested)

    def test_huge_integers_are_refused_with_a_fixed_error(self):
        H.expect_error(self, "history_invalid", "json_number", V.History.from_dict, {"a": 10 ** 5000})
        H.expect_error(self, "history_invalid", "json", V.decode_history, '{"a":' + "9" * 5000 + "}")

    def test_bool_is_not_an_integer(self):
        d = H.example_u().history().to_dict()
        d["head_seq"] = True
        H.expect_rule(self, "head", V.History.from_dict(d))
        d = H.example_u().history().to_dict()
        d["schema_version"] = True
        H.expect_field(self, "unsupported_schema", "schema_version", V.validate_history, V.History.from_dict(d))
        ev = H.example_u().events
        ev[1]["seq"] = True
        H.expect_rule(self, "seq", H.rebuild(ev))

    def test_the_error_never_echoes_the_text(self):
        secret = "https://example.invalid/secret-token-path"
        e = H.expect_error(self, "history_invalid", None, V.decode_history, '{"a":"%s"' % secret)
        self.assertNotIn("secret-token", str(e) + repr(e) + str(e.field) + str(e.rule))


class FormRefusals(unittest.TestCase):
    def setUp(self):
        self.b = H.example_u()
        self.ev = self.b.events

    def test_unknown_header_or_record_keys(self):
        d = self.b.history().to_dict()
        d["extra"] = 1
        H.expect_rule(self, "header_keys", V.History.from_dict(d))
        d = self.b.history().to_dict()
        del d["head_hash"]
        H.expect_rule(self, "header_keys", V.History.from_dict(d))
        ev = H.deep(self.ev)
        ev[1]["extra"] = 1
        H.expect_rule(self, "record_keys", H.rebuild(ev))
        ev = H.deep(self.ev)
        del ev[2]["skipped_sessions"]
        H.expect_rule(self, "record_keys", H.rebuild(ev))

    def test_unknown_kind_and_the_b5_kind(self):
        for kind in ("BOGUS", "RECOVERY_PREFIX_ADOPTION", None, 7):
            with self.subTest(kind):
                ev = H.deep(self.ev)
                ev[2]["kind"] = kind
                H.expect_field(self, "unsupported_event", "kind", V.validate_history, H.rebuild(ev))

    def test_unsupported_schema_and_core_sha(self):
        d = self.b.history().to_dict()
        d["schema_version"] = 3
        H.expect_field(self, "unsupported_schema", "schema_version", V.validate_history, V.History.from_dict(d))
        d = self.b.history().to_dict()
        d["core_sha"] = "0" * 40
        H.expect_field(self, "unsupported_schema", "core_sha", V.validate_history, V.History.from_dict(d))

    def test_empty_events_and_non_dict_input(self):
        d = self.b.history().to_dict()
        d["events"] = []
        H.expect_rule(self, "events", V.History.from_dict(d))
        H.expect_rule(self, "shape", V.History.from_dict([1, 2]))

    def test_current_state_must_match_and_be_canonical(self):
        d = self.b.history().to_dict()
        d["current_state"]["streak"] = 5
        H.expect_rule(self, "current_state", V.History.from_dict(d))      # I-10
        ev = H.example_u().events
        ev[-1]["state_after"] = {"as_of_d": None}
        H.expect_rule(self, "state_after", H.rebuild(ev))


class SchemaAndTypeRefusals(unittest.TestCase):
    def setUp(self):
        self.w = H.P.World()
        self.w.apply(D[1], 27.0)
        self.v1 = self.w.snap()
        self.v2 = H.example_u().history()

    def test_a_v1_snapshot_is_not_converted_by_validate_history(self):
        as_history = V.History.from_dict(self.v1.to_dict())
        H.expect_field(self, "unsupported_schema", "schema_version", V.validate_history, as_history)

    def test_the_existing_s1_checker_refuses_v2_unchanged(self):
        as_snapshot = Snapshot.from_dict(self.v2.to_dict())
        H.expect_field(self, "unsupported_schema", "schema_version", validate_snapshot, as_snapshot)

    def test_a_value_of_the_other_class_is_a_type_refusal(self):
        H.expect_error(self, "history_invalid", "type", V.validate_history, self.v1)
        H.expect_error(self, "snapshot_invalid", "type", validate_snapshot, self.v2)
        H.expect_error(self, "history_invalid", "type", V.validate_history, self.v2.to_dict())
        H.expect_error(self, "history_invalid", "type", V.validate_history, None)


class HistoryCheckValue(unittest.TestCase):
    def test_it_is_immutable_and_carries_no_ledger_content(self):
        chk = H.example_r().check()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            chk.head_seq = 1
        with self.assertRaises(dataclasses.FrozenInstanceError):
            chk.current_boundary.seq = 1
        for name in ("effective_seqs", "superseded_seqs", "declared_days_in_segment"):
            self.assertIsInstance(getattr(chk, name), tuple)
        self.assertEqual(sorted(f.name for f in dataclasses.fields(chk)),
                         sorted(["head_seq", "head_hash", "record_count", "effective_seqs", "superseded_seqs",
                                 "current_boundary", "latest_apply_d", "processing_after",
                                 "declared_days_in_segment", "migrated", "history_digest", "state_digest"]))


class MakeHistoryGenesis(unittest.TestCase):
    def setUp(self):
        self.sessions = H.P.make_sessions()

    def test_builds_a_checked_genesis_only_history(self):
        h = V.make_history_genesis(D[0], self.sessions)
        chk = V.validate_history(h)
        self.assertEqual((chk.record_count, chk.head_seq, chk.migrated), (1, 0, False))
        self.assertEqual(chk.current_boundary, V.Boundary("GENESIS", 0, D[0]))
        self.assertEqual(chk.processing_after, D[0])
        self.assertEqual(chk.effective_seqs, (0,))
        ev = h.events[0]
        from v2_persistence.events import GENESIS_KEYS
        self.assertEqual(set(ev), set(GENESIS_KEYS))                     # the same keys as the S1 GENESIS
        self.assertEqual(h.schema_version, 2)
        self.assertEqual(H.HB().history(), h)                           # the same bytes as the test builder's genesis

    def test_same_refusals_as_s1_make_genesis(self):
        from v2_persistence.runner import make_genesis
        cases = {
            "missing": (D[0].replace("03-02", "01-01"), self.sessions),
            "unconfirmed": (D[0], H.P.make_sessions(unconfirmed=(D[0],))),
        }
        for name, (start, sessions) in cases.items():
            with self.subTest(name):
                with self.assertRaises(H.PersistenceError) as c1:
                    make_genesis(start, sessions)
                with self.assertRaises(H.PersistenceError) as c2:
                    V.make_history_genesis(start, sessions)
                self.assertEqual((c1.exception.code, c1.exception.field), (c2.exception.code, c2.exception.field))
        for bad_date in ("2026-13-40", 5, None):
            with self.subTest(bad_date):
                with self.assertRaises(Exception) as c:
                    V.make_history_genesis(bad_date, self.sessions)
                self.assertEqual(c.exception.code, "invalid_date")
        with self.assertRaises(Exception) as c:
            V.make_history_genesis(D[0], [1, 2])
        self.assertEqual(c.exception.code, "sessions_invalid")


if __name__ == "__main__":
    unittest.main()
