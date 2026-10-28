"""A-02: initialization, GENESIS, version/event/field checks, seq/parent/hash/D order, JSON strictness."""
import json
import unittest

import p_helpers as h
from v2_core.errors import InputError
from v2_persistence.codec import Snapshot, decode_snapshot, encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.recompute import validate_snapshot
from v2_persistence.runner import make_genesis
from v2_persistence.store import MemoryStore

D = h.DATES


def rule_of(case, fn, *a, **k):
    with case.assertRaises(PersistenceError) as cm:
        fn(*a, **k)
    return cm.exception


def chain(n=3):
    """A world with n consecutive applied days (some with a gap), plus its Snapshot."""
    w = h.World()
    w.apply(D[1], 27.0)
    if n >= 2:
        w.apply(D[2], 40.0)
    if n >= 3:
        w.apply(D[5], 41.0)     # D[3], D[4] skipped
    return w, w.snap()


class StoreInitialization(unittest.TestCase):
    def test_uninitialized_read_and_commit(self):
        store = MemoryStore()
        e = rule_of(self, store.read)
        self.assertEqual((e.code, e.field), ("store_uninitialized", "store"))
        # a plan from another store cannot be committed into an uninitialized store
        w2 = h.World()
        w2.ledger.append(h.obs("R1", D[1], 27.0))
        plan = w2.prepare(D[1]).plan
        e = rule_of(self, MemoryStore().commit, plan)
        self.assertEqual(e.code, "store_uninitialized")

    def test_no_implicit_initialization(self):
        store = MemoryStore()
        for _ in range(2):
            rule_of(self, store.read)
        self.assertIsNone(store._snapshot)

    def test_double_initialize_is_rejected_and_state_kept(self):
        w = h.World()
        before = w.snap()
        e = rule_of(self, w.store.initialize, make_genesis(D[3], w.sessions))
        self.assertEqual((e.code, e.field), ("already_initialized", "store"))
        self.assertEqual(w.snap(), before)

    def test_initialize_accepts_only_a_genesis_only_snapshot(self):
        w, snap = chain(1)
        store = MemoryStore()
        e = rule_of(self, store.initialize, snap)          # contains an APPLY
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "initialize_not_genesis_only"))
        with self.assertRaises(PersistenceError):
            store.read()

    def test_initialize_rejects_non_genesis_first_event_and_second_genesis(self):
        w, snap = chain(1)
        genesis_only = make_genesis(D[0], w.sessions)

        def second_genesis(evs):
            evs.append(dict(evs[0]))
        two = h.tampered(genesis_only, second_genesis)
        e = rule_of(self, MemoryStore().initialize, two)
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "genesis_not_first"))

        def first_is_apply(evs):
            evs[0] = dict(snap.events[1])
        e = rule_of(self, MemoryStore().initialize, h.tampered(genesis_only, first_is_apply, rehash_events=False))
        self.assertEqual(e.code, "snapshot_invalid")


class GenesisConstruction(unittest.TestCase):
    def test_normal_genesis(self):
        sessions = h.make_sessions()
        g = make_genesis(D[2], sessions)
        validate_snapshot(g)
        ev = g.events
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["kind"], ev[0]["seq"], ev[0]["parent_seq"], ev[0]["parent_hash"]),
                         ("GENESIS", 0, None, None))
        self.assertEqual(ev[0]["start_after"], D[2])
        self.assertEqual(ev[0]["boundary_session"]["date"], D[2])
        self.assertIs(ev[0]["boundary_session"]["confirmed"], True)
        self.assertIsNone(ev[0]["state_after"]["as_of_d"])         # a boundary day is not an applied market day
        self.assertEqual(g.current_state, ev[0]["state_after"])
        self.assertEqual((g.head_seq, g.head_hash), (0, ev[0]["event_hash"]))
        self.assertEqual(g.schema_version, 1)

    def test_invalid_start_after_dates(self):
        sessions = h.make_sessions()
        for bad in ("2026-02-30", "20260302", "", None, "2026-3-2", 20260302, True, "2026-03-02 ", "2026-03-02\n"):
            with self.assertRaises(InputError) as cm:
                make_genesis(bad, sessions)
            self.assertEqual((cm.exception.code, cm.exception.field), ("invalid_date", "start_after"), repr(bad))

    def test_boundary_missing_and_unconfirmed(self):
        e = rule_of(self, make_genesis, "2026-03-07", h.make_sessions())           # a Saturday: not a session
        self.assertEqual((e.code, e.field), ("genesis_boundary_missing", "start_after"))
        e = rule_of(self, make_genesis, D[2], h.make_sessions(unconfirmed=(D[2],)))
        self.assertEqual((e.code, e.field), ("genesis_boundary_unconfirmed", "start_after"))

    def test_boundary_is_never_inferred(self):
        # the signature requires the date; nothing is taken from the latest day, the first ledger row or a clock
        with self.assertRaises(TypeError):
            make_genesis(h.make_sessions())

    def test_target_on_or_before_boundary_is_rejected(self):
        w = h.World(start_idx=3)
        w.ledger.append(h.obs("R", D[3], 27.0))
        w.ledger.append(h.obs("R0", D[2], 27.0))
        before = w.snap()
        for d in (D[3], D[2], D[0]):
            e = rule_of(self, w.prepare, d)
            self.assertEqual((e.code, e.field), ("target_not_after_genesis", "target_session_date"))
        self.assertEqual(w.snap(), before)


class VersionAndFields(unittest.TestCase):
    def setUp(self):
        self.w, self.snap = chain(2)

    def _with_header(self, **changes):
        d = self.snap.to_dict()
        d.update(changes)
        return Snapshot.from_dict(d)

    def test_unknown_schema_version(self):
        for bad in (2, 0, True, 1.0, "1", None):
            e = rule_of(self, validate_snapshot, self._with_header(schema_version=bad))
            self.assertEqual((e.code, e.field), ("unsupported_schema", "schema_version"), repr(bad))

    def test_unknown_core_sha(self):
        for bad in ("0" * 40, self.snap.core_sha.upper(), None, 1):
            e = rule_of(self, validate_snapshot, self._with_header(core_sha=bad))
            self.assertEqual((e.code, e.field), ("unsupported_schema", "core_sha"), repr(bad))

    def test_unknown_event_kind(self):
        for kind in ("ACK", "apply", "", None, 7):
            snap = h.tampered(self.snap, lambda evs: evs[1].__setitem__("kind", kind), rehash_events=False)
            e = rule_of(self, validate_snapshot, snap)
            self.assertEqual((e.code, e.field), ("unsupported_event", "kind"), repr(kind))

    def test_unknown_or_missing_fields(self):
        d = self.snap.to_dict()
        d["extra"] = 1
        e = rule_of(self, validate_snapshot, Snapshot.from_dict(d))
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "header_keys"))
        d = self.snap.to_dict()
        del d["head_hash"]
        e = rule_of(self, validate_snapshot, Snapshot.from_dict(d))
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "header_keys"))
        for i, rule in ((0, "genesis_keys"), (1, "apply_keys")):
            snap = h.tampered(self.snap, lambda evs: evs[i].__setitem__("unexpected", 1))
            e = rule_of(self, validate_snapshot, snap)
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", rule))
            snap = h.tampered(self.snap, lambda evs: evs[i].pop("state_after"))
            e = rule_of(self, validate_snapshot, snap)
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", rule))
        snap = h.tampered(self.snap, lambda evs: evs[1]["confirmed_inputs"].__setitem__("note", "x"))
        self.assertEqual(rule_of(self, validate_snapshot, snap).rule, "confirmed_inputs_keys")

    def test_not_a_snapshot(self):
        for bad in (None, {}, "text", self.snap.to_dict()):
            e = rule_of(self, validate_snapshot, bad)
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", "type"))

    def test_empty_event_list(self):
        e = rule_of(self, validate_snapshot, self._with_header(events=[]))
        self.assertEqual(e.rule, "events")


class ChainAndOrder(unittest.TestCase):
    def setUp(self):
        self.w, self.snap = chain(3)

    def fails(self, mutate, rule, rehash_events=True, fix_chain=True):
        snap = h.tampered(self.snap, mutate, rehash_events=rehash_events, fix_chain=fix_chain)
        e = rule_of(self, validate_snapshot, snap)
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", rule))

    def test_baseline_is_valid(self):
        v = validate_snapshot(self.snap)
        self.assertEqual([a.d for a in v.applies], [D[1], D[2], D[5]])
        self.assertEqual(v.head_seq, 3)

    def test_seq(self):
        self.fails(lambda e: e[2].__setitem__("seq", 5), "seq")
        self.fails(lambda e: e[1].__setitem__("seq", True), "seq")        # bool is not an int here
        self.fails(lambda e: e[1].__setitem__("seq", 1.0), "seq")
        self.fails(lambda e: e[3].__setitem__("seq", 2), "seq")

    def test_parent_seq_and_hash(self):
        self.fails(lambda e: e[2].__setitem__("parent_seq", 0), "parent_seq")
        self.fails(lambda e: e[2].__setitem__("parent_seq", True), "parent_seq")
        # every event_hash is recomputed after the change, so only the chain link itself is wrong
        self.fails(lambda e: e[2].__setitem__("parent_hash", "0" * 64), "parent_hash", fix_chain=False)
        self.fails(lambda e: e[3].__setitem__("parent_hash", e[1]["event_hash"]), "parent_hash", fix_chain=False)

    def test_event_hash(self):
        self.fails(lambda e: e[1]["confirmed_inputs"]["row"].__setitem__("soxx", 111.0), "event_hash",
                   rehash_events=False)
        self.fails(lambda e: e[2].__setitem__("event_hash", "0" * 64), "event_hash", rehash_events=False)
        self.fails(lambda e: e[2].__setitem__("event_hash", None), "event_hash", rehash_events=False)

    def test_d_order_and_duplicates(self):
        self.fails(lambda e: e[2].__setitem__("d", D[1]), "d_order")                 # same D twice
        self.fails(lambda e: e[2].__setitem__("d", D[0]), "d_order")                 # reversed
        self.fails(lambda e: e[1].__setitem__("d", D[0]), "d_order")                 # not after the boundary
        self.fails(lambda e: e[1].__setitem__("d", "2026-13-01"), "apply_d")

    def test_genesis_state_must_be_initial(self):
        self.fails(lambda e: e[0]["state_after"].__setitem__("streak", 1), "genesis_state")
        self.fails(lambda e: e[0]["state_after"].__setitem__("as_of_d", D[0]), "genesis_state")
        self.fails(lambda e: e[0].__setitem__("seq", 1), "genesis_seq")
        self.fails(lambda e: e[0].__setitem__("parent_hash", "0" * 64), "genesis_seq")

    def test_genesis_boundary_fields(self):
        self.fails(lambda e: e[0].__setitem__("start_after", D[1]), "genesis_boundary")
        self.fails(lambda e: e[0]["boundary_session"].__setitem__("confirmed", False), "genesis_boundary")
        self.fails(lambda e: e[0].__setitem__("start_after", "bad"), "genesis_boundary")

    def test_header_mismatch(self):
        d = self.snap.to_dict()
        for key, value, rule in (("head_seq", 2, "head_seq"), ("head_seq", True, "head_seq"),
                                 ("head_hash", "0" * 64, "head_hash")):
            bad = dict(d)
            bad[key] = value
            self.assertEqual(rule_of(self, validate_snapshot, Snapshot.from_dict(bad)).rule, rule)
        bad = dict(d)
        bad["current_state"] = self.snap.events[2]["state_after"]               # the previous state
        self.assertEqual(rule_of(self, validate_snapshot, Snapshot.from_dict(bad)).rule, "current_state")

    def test_canonical_form(self):
        self.fails(lambda e: e[1]["confirmed_inputs"]["row"].__setitem__("soxx", 110), "not_canonical")      # int
        self.fails(lambda e: e[1]["confirmed_inputs"]["decision"].__setitem__("current_fg_value", "27.0"),
                   "not_canonical")
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"][0].__setitem__(
            "open_at", "2026-03-02T09:30:00-05:00"), "not_canonical")                                       # offset text
        self.fails(lambda e: e[1]["confirmed_inputs"]["decision"].__setitem__(
            "observed_at_iso8601", "2026-03-04T01:00:00+00:00"), "not_canonical")

    def test_market_number_ranges_and_types(self):
        for field, value in (("soxx", 0.0), ("soxx", -1.0), ("sma", 0.0), ("rsi", 100.5), ("rsi", -0.1),
                             ("prev_rsi", 101.0), ("soxx", True), ("rsi", None), ("shd", "1.0"), ("sma", [1.0])):
            snap = h.tampered(self.snap, lambda e: e[1]["confirmed_inputs"]["row"].__setitem__(field, value))
            e = rule_of(self, validate_snapshot, snap)
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", "row"), (field, value))

    def test_row_and_prev_row_dates(self):
        self.fails(lambda e: e[1]["confirmed_inputs"]["row"].__setitem__("date", D[0]), "row")
        self.fails(lambda e: e[2]["confirmed_inputs"]["prev_row"].__setitem__("date", D[0]), "prev_row")
        self.fails(lambda e: e[1]["confirmed_inputs"].__setitem__("prev_session_date", D[3]), "prev_session_date")
        self.fails(lambda e: e[1]["confirmed_inputs"].__setitem__("prev_session_date", None), "prev_session_date")

    def test_decision_fields(self):
        for key, value in (("observation_role", "supplemental"), ("observation_status", "not_checked"),
                           ("target_us_session_date", D[2]), ("record_id", "http://x"), ("record_id", "")):
            snap = h.tampered(self.snap, lambda e: e[1]["confirmed_inputs"]["decision"].__setitem__(key, value))
            self.assertEqual(rule_of(self, validate_snapshot, snap).rule, "decision", (key, value))

    def test_decision_outside_window(self):
        def late(evs):
            evs[1]["confirmed_inputs"]["decision"]["observed_at_iso8601"] = "2026-03-04T15:00:00Z"
        self.fails(late, "decision_window")
        def early(evs):
            evs[1]["confirmed_inputs"]["decision"]["observed_at_iso8601"] = "2026-03-03T20:59:59Z"   # before close
        self.fails(early, "decision_window")

    def test_session_context_structure(self):
        self.fails(lambda e: e[1]["confirmed_inputs"].__setitem__("session_context", []), "session_context")
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"].pop(), "session_context")      # no next(D)
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"].pop(0), "session_context")     # no boundary
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"][1].__setitem__("confirmed", False),
                   "session_context")                                                                   # D unconfirmed
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"][0].__setitem__("close_at",
                   "2026-03-02T08:00:00Z"), "session_context")                                          # open >= close
        self.fails(lambda e: e[1]["confirmed_inputs"]["session_context"][0].__setitem__("extra", 1),
                   "session_context")
        self.fails(lambda e: e[2]["confirmed_inputs"]["session_context"][0].__setitem__("close_at",
                   "2026-03-03T22:00:00Z"), "context_continuity")


class JsonStrictness(unittest.TestCase):
    def setUp(self):
        _, self.snap = chain(2)
        self.text = encode_snapshot(self.snap)

    def test_round_trip(self):
        self.assertEqual(decode_snapshot(self.text), self.snap)
        self.assertEqual(encode_snapshot(decode_snapshot(self.text)), self.text)
        validate_snapshot(decode_snapshot(self.text))
        # non-canonical but equivalent text (indentation, key order) decodes to the same value
        pretty = json.dumps(json.loads(self.text), indent=2, sort_keys=False)
        self.assertEqual(decode_snapshot(pretty), self.snap)

    def test_duplicate_keys(self):
        dup = self.text.replace('{"core_sha"', '{"schema_version":2,"core_sha"', 1)
        self.assertIn('"schema_version":2,"core_sha"', dup)
        e = rule_of(self, decode_snapshot, dup)
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "json"))
        e = rule_of(self, decode_snapshot, '{"a":1,"a":1}')
        self.assertEqual(e.rule, "json")
        e = rule_of(self, decode_snapshot, '{"a":{"b":1,"b":2}}')
        self.assertEqual(e.rule, "json")

    def test_non_finite_and_bad_text(self):
        for bad in ('{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999}', '', 'not json', '{"a":',
                    '[1,2', '﻿{}', None, b'{}', 1):
            with self.assertRaises(PersistenceError, msg=repr(bad)):
                decode_snapshot(bad)

    def test_non_json_values_in_dicts(self):
        for bad in ({"a": float("nan")}, {"a": float("inf")}, {1: "x"}, {"a": (1, 2)}, {"a": {1, 2}}, {"a": object()},
                    {"a": b"x"}):
            with self.assertRaises(PersistenceError, msg=repr(bad)):
                Snapshot.from_dict(bad)

    def test_deep_nesting_is_rejected_not_crashed(self):
        deep = cur = []
        for _ in range(500):
            nxt = []
            cur.append(nxt)
            cur = nxt
        with self.assertRaises(PersistenceError):
            Snapshot.from_dict({"a": deep})
        with self.assertRaises(PersistenceError):
            decode_snapshot("[" * 100000 + "]" * 100000)

    def test_bool_numbers_in_stored_event(self):
        snap = h.tampered(self.snap, lambda e: e[1]["confirmed_inputs"]["row"].__setitem__("soxx", True))
        self.assertEqual(rule_of(self, validate_snapshot, snap).rule, "row")
        text = self.text.replace('"soxx":110.0', '"soxx":true', 1)
        self.assertNotEqual(text, self.text)
        e = None
        try:
            validate_snapshot(decode_snapshot(text))
        except PersistenceError as err:
            e = err
        self.assertIsNotNone(e)
        self.assertEqual(e.code, "snapshot_invalid")

    def test_invalid_times_and_windows_in_stored_context(self):
        for text in ("2026-03-03", "2026-03-03T09:30", "2026-03-03T09:30:00", "2026-03-03T25:30:00Z", "x", None, 5):
            snap = h.tampered(self.snap, lambda e: e[1]["confirmed_inputs"]["session_context"][1].__setitem__(
                "open_at", text))
            self.assertEqual(rule_of(self, validate_snapshot, snap).rule, "session_context", repr(text))


if __name__ == "__main__":
    unittest.main()
