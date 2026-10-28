"""Regression tests for the three findings of the S1 receipt review (R-01, R-02, R-03).

R-01: no structured return value of the public API may alias the stored Snapshot.
R-02: a bool in a market row is refused before it can be turned into 1.0 / 0.0.
R-03: an int too large for a float, in a saved input, is a snapshot_invalid and not an OverflowError.
The reference for "unchanged" is a deep copy taken before the edit, never the same Snapshot object or its encoding alone.
"""
import copy
import unittest

import p_helpers as h
from v2_core.errors import CoreError
from v2_persistence.codec import Snapshot, decode_snapshot, encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.events import input_hash_of, row_dict
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import reconcile

D = h.DATES
HUGE = 10 ** 400


def world():
    w = h.World()
    w.apply(D[1], 27.0)
    w.apply(D[2], 40.0)
    return w


class Reference(object):
    """Deep copy of what the store holds, to compare against after an edit of a returned value."""

    def __init__(self, w):
        self.w = w
        self.dict = copy.deepcopy(w.snap().to_dict())
        self.text = encode_snapshot(w.snap())
        self.head = (w.snap().head_seq, w.snap().head_hash)

    def check(self, case, label):
        snap = self.w.snap()
        case.assertEqual(snap.to_dict(), self.dict, label)                      # the content read through accessors
        case.assertEqual(encode_snapshot(snap), self.text, label)
        case.assertEqual((snap.head_seq, snap.head_hash), self.head, label)
        case.assertEqual(decode_snapshot(encode_snapshot(snap)).to_dict(), self.dict, label)   # both views agree
        validate_snapshot(snap)                                                  # and the history still checks


def scribble(obj, depth=0):
    """Edit every dict / list reachable from a returned value (in place)."""
    if depth > 8:
        return
    if isinstance(obj, dict):
        for key in list(obj):
            scribble(obj[key], depth + 1)
        obj["review_marker"] = 1
        for key in list(obj):
            if key != "review_marker" and isinstance(obj[key], (int, float, str)) and not isinstance(obj[key], bool):
                obj[key] = "EDITED"
    elif isinstance(obj, list):
        for item in obj:
            scribble(item, depth + 1)
        obj.append("review_marker")
    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        for value in list(vars(obj).values()):
            scribble(value, depth + 1)


class R01_NoSharedReferences(unittest.TestCase):
    def test_the_four_reviewed_routes(self):
        w = world()
        ref = Reference(w)
        res = w.prepare(D[3])                                                    # no decision for D3: NO_COMMIT
        self.assertEqual(res.status, "NO_COMMIT")
        res.core_result.next_state.fixed_decision["record_id"] = "REVIEW-EDIT"
        ref.check(self, "NO_COMMIT.next_state.fixed_decision")
        v = validate_snapshot(w.snap())
        v.boundary_session.update(confirmed=False)
        ref.check(self, "boundary_session")
        v = validate_snapshot(w.snap())
        v.applies[0].transition_result["notes"].append("review_marker")
        ref.check(self, "applies[0].transition_result")
        v = validate_snapshot(w.snap())
        v.applies[0].state_after.update(streak=99)
        ref.check(self, "applies[0].state_after")

    def test_every_field_of_the_validation_result(self):
        w = world()
        ref = Reference(w)
        v = validate_snapshot(w.snap())
        for ap in list(v.applies):
            scribble(ap)
            ap.stored_sessions.sessions.clear()
            ap.context.clear()
            ap.skipped.append("x")
        v.state.fixed_decision["d"] = "1999-01-01"
        scribble(v)
        ref.check(self, "ValidatedSnapshot")
        again = validate_snapshot(w.snap())
        self.assertEqual(again.applies[0].d, D[1])                               # a new, pristine result each time
        self.assertEqual(again.state.fixed_decision["d"], D[2])

    def test_every_field_of_every_prepare_result(self):
        for d, value, kind in ((D[3], None, "NO_COMMIT"), (D[2], None, "ALREADY_APPLIED"), (D[3], 41.0, "PREPARED")):
            w = world()
            if value is not None:
                w.ledger.append(h.obs("R-" + d, d, value))
            ref = Reference(w)
            res = w.prepare(d)
            self.assertEqual(res.status, kind)
            core = res.core_result
            for part in (core.next_state.fixed_decision, core.rules, core.notes, core.series_meta):
                scribble(part)
            if core.next_state.base is not None:
                scribble(core.next_state.base.__dict__)
            if res.plan is not None:
                scribble(res.plan.event)
            ref.check(self, kind)
            if res.plan is not None:                                             # the plan itself is still intact
                clean = w.prepare(d).plan
                self.assertEqual(res.plan, clean)
                w.store.commit(res.plan)
                self.assertEqual(w.snap().events[-1], clean.event)

    def test_snapshot_values_returned_by_the_store_and_the_helpers(self):
        w = world()
        ref = Reference(w)
        w.ledger.append(h.obs("R-" + D[3], D[3], 41.0))
        plan = w.prepare(D[3]).plan
        results = [w.store.read(), h.make_genesis(D[0], w.sessions), decode_snapshot(ref.text), w.store.read()]
        for snap in results:
            scribble(snap.to_dict())
            scribble(snap.events)
            scribble(snap.current_state)
        ref.check(self, "accessors")
        done = w.store.commit(plan)
        scribble(done.snapshot.events)
        scribble(done.snapshot.to_dict())
        ref2 = Reference(w)
        scribble(w.store.read().events)
        ref2.check(self, "commit result")
        rec = reconcile(plan, w.store.read())
        scribble(rec)
        ref2.check(self, "reconcile result")

    def test_validate_does_not_hand_out_the_private_view_of_a_snapshot_it_was_given(self):
        # a Snapshot that is not held by a store behaves the same: what validate returns is never the snapshot's own data
        snap = world().snap()
        before = snap.to_dict()
        v = validate_snapshot(snap)
        scribble(v)
        self.assertEqual(snap.to_dict(), before)
        validate_snapshot(snap)


class R02_MarketBools(unittest.TestCase):
    FIELDS = ("soxx", "sma", "rsi", "shd", "prev_rsi")

    def refuse(self, per_date, rule):
        w = h.World(per_date=per_date)
        w.ledger.append(h.obs("R1", D[1], 27.0))
        before = w.snap()
        with self.assertRaises(CoreError) as cm:
            w.prepare(D[1])
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", rule), per_date)
        self.assertEqual(w.snap(), before)
        self.assertEqual(w.snap().head_seq, 0)

    def test_bool_in_the_target_row(self):
        for field in self.FIELDS:
            for value in (True, False):
                self.refuse({D[1]: {field: value}}, "row")

    def test_bool_in_the_previous_row(self):
        for field in self.FIELDS:
            for value in (True, False):
                self.refuse({D[0]: {field: value}}, "prev_row")

    def test_an_int_beyond_float_in_the_series_is_refused_before_a_plan(self):
        self.refuse({D[1]: {"soxx": HUGE}}, "row")
        self.refuse({D[0]: {"sma": -HUGE}}, "prev_row")

    def test_the_row_builder_refuses_directly(self):
        row = h.row(D[1])
        for field in self.FIELDS:
            bad = type(row)(**dict(vars(row), **{field: True}))
            with self.assertRaises(PersistenceError) as cm:
                row_dict(bad)
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "row"))

    def test_normal_int_and_float_inputs_are_normalized_as_before(self):
        w = h.World(per_date={D[1]: dict(soxx=110, sma=100, rsi=50, shd=-1, prev_rsi=49),
                              D[0]: dict(soxx=111, sma=100)})
        w.ledger.append(h.obs("R1", D[1], 27.0))
        res = w.prepare(D[1])
        self.assertEqual(res.status, "PREPARED")
        ci = res.plan.event["confirmed_inputs"]
        for part in (ci["row"], ci["prev_row"]):
            for field in self.FIELDS:
                self.assertIs(type(part[field]), float, field)
        self.assertEqual((ci["row"]["soxx"], ci["prev_row"]["soxx"]), (110.0, 111.0))
        w.store.commit(res.plan)
        validate_snapshot(w.snap())
        self.assertEqual(w.prepare(D[1]).status, "ALREADY_APPLIED")


class R03_HugeIntegersInSavedInputs(unittest.TestCase):
    def setUp(self):
        self.snap = world().snap()

    def tampered(self, mutate):
        def apply(evs):
            mutate(evs)
            evs[1]["input_hash"] = input_hash_of(evs[1]["confirmed_inputs"])
        snap = h.tampered(self.snap, apply)
        return decode_snapshot(encode_snapshot(snap))                           # through JSON text, as read from storage

    def refuse(self, mutate, rule):
        snap = self.tampered(mutate)
        with self.assertRaises(PersistenceError) as cm:
            validate_snapshot(snap)
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", rule))
        digits = "1" + "0" * 50
        for text in (str(cm.exception), repr(cm.exception), str(cm.exception.rule), str(cm.exception.detail)):
            self.assertNotIn(digits, text)

    def test_row_fields(self):
        for field in ("soxx", "sma", "rsi", "shd", "prev_rsi"):
            for value in (HUGE, -HUGE):
                self.refuse(lambda e: e[1]["confirmed_inputs"]["row"].__setitem__(field, value), "row")

    def test_previous_row_fields(self):
        for field in ("soxx", "sma", "rsi", "shd", "prev_rsi"):
            self.refuse(lambda e: e[2]["confirmed_inputs"]["prev_row"].__setitem__(field, HUGE), "prev_row")

    def test_saved_decision_value(self):
        for value in (HUGE, -HUGE):
            self.refuse(lambda e: e[1]["confirmed_inputs"]["decision"].__setitem__("current_fg_value", value), "decision")

    def test_the_review_reproduction(self):
        w = h.World()
        w.apply(D[1], 27.0)
        events = w.snap().events
        events[1]["confirmed_inputs"]["row"]["soxx"] = HUGE
        events[1]["input_hash"] = input_hash_of(events[1]["confirmed_inputs"])
        with self.assertRaises(PersistenceError) as cm:
            validate_snapshot(h.rehash(events))
        self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "row"))

    def test_prepare_day_and_the_store_refuse_such_a_snapshot_without_changing_anything(self):
        bad = self.tampered(lambda e: e[1]["confirmed_inputs"]["row"].__setitem__("soxx", HUGE))
        w = h.World()
        with self.assertRaises(PersistenceError) as cm:
            h.prepare_day(bad, D[3], w.series, w.sessions, [])
        self.assertEqual(cm.exception.code, "snapshot_invalid")
        with self.assertRaises(PersistenceError):
            h.MemoryStore().initialize(bad)
        with self.assertRaises(PersistenceError):
            reconcile(_any_plan(), bad)

    def test_an_absurdly_long_integer_in_text_is_a_package_error_on_every_python(self):
        text = encode_snapshot(self.snap).replace('"soxx":110.0', '"soxx":' + "9" * 5000, 1)
        self.assertNotEqual(text, encode_snapshot(self.snap))
        with self.assertRaises(PersistenceError):
            validate_snapshot(decode_snapshot(text))            # Python 3.11+ stops at decode, 3.10 at validation


def _any_plan():
    w = h.World()
    w.ledger.append(h.obs("R1", D[1], 27.0))
    return w.prepare(D[1]).plan


if __name__ == "__main__":
    unittest.main()
