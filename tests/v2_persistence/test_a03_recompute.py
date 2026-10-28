"""A-03: re-calculation from saved inputs, base (IB-04) checks, unconfirmed saved sessions, apply_transition spies.

The spies patch the name each path really calls: v2_core.engine.apply_transition for evaluate_day (normal path) and
v2_persistence.recompute.apply_transition for the re-calculation. Patching the origin v2_core.transition name changes
neither path, which one test shows.
"""
import dataclasses
import unittest
from unittest import mock

import p_helpers as h
from v2_core import engine as core_engine
from v2_core import transition as core_transition
from v2_core.fixture import MarketRow, load_research_fixture
from v2_core.observations import parse_observation
from v2_core.state import MarketState
from v2_persistence import recompute
from v2_persistence.codec import decode_snapshot, encode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.events import input_hash_of, serialize_transition
from v2_persistence.recompute import validate_snapshot

D = h.DATES


def build_world():
    """Five applied days with a gap, armed reached, and a normal-rise day."""
    w = h.World(per_date={D[7]: dict(rsi=56.0, shd=1.0, prev_rsi=54.0)})
    w.apply(D[1], 40.0)
    w.apply(D[2], 41.0)
    w.apply(D[3], 42.0)           # streak 3 -> armed
    w.apply(D[6], 27.0)           # gap (D4, D5 skipped), NORMAL
    w.apply(D[7], 35.0)           # trend
    return w


def error_of(case, fn, *a):
    with case.assertRaises(PersistenceError) as cm:
        fn(*a)
    return cm.exception


class RoundTrip(unittest.TestCase):
    def test_json_round_trip_keeps_every_state_and_transition(self):
        w = build_world()
        snap = w.snap()
        again = decode_snapshot(encode_snapshot(snap))
        self.assertEqual(again, snap)
        validate_snapshot(again)
        # an independent re-calculation in the test, straight from v2_core
        events = again.events
        state = MarketState.initial()
        for ev in events[1:]:
            ci = ev["confirmed_inputs"]
            obs = parse_observation(ci["decision"])
            row = MarketRow(**ci["row"])
            prev = None if ci["prev_row"] is None else MarketRow(**ci["prev_row"])
            t = core_transition.apply_transition(state, ev["d"], ci["prev_session_date"], row, prev, obs)
            self.assertEqual(serialize_transition(t), ev["transition_result"], ev["d"])
            self.assertEqual(t.next_state.to_dict(), ev["state_after"], ev["d"])
            self.assertEqual(MarketState.from_dict(ev["state_after"]), t.next_state)
            state = t.next_state
        self.assertEqual(again.current_state, state.to_dict())
        self.assertEqual([e["skipped_sessions"] for e in events[1:]], [[], [], [], [D[4], D[5]], []])
        self.assertTrue(events[4]["transition_result"]["gap"])

    def test_every_saved_state_is_a_persistable_state(self):
        snap = build_world().snap()
        for ev in snap.events:
            MarketState.from_dict(ev["state_after"])         # I-01..07 and IB-01..03, no exception

    def test_research_fixture_chain_matches_core_and_survives_json(self):
        series, fg = load_research_fixture(h.FIXTURE_DIR)
        dates = [d for d in series.dates if "2025-01-02" <= d <= "2025-04-30"]
        sessions = h.make_sessions(dates)
        ledger = [h.obs("FG-" + d, d, fg[d]) for d in dates if d in fg]
        store = h.MemoryStore()
        store.initialize(h.make_genesis(dates[0], sessions))
        state = MarketState.initial()
        for d in dates[1:-1]:               # the last date has no next session in the list
            res = h.prepare_day(store.read(), d, series, sessions, ledger)
            direct = core_engine.evaluate_day(state, d, series, sessions, ledger)
            self.assertEqual(res.core_result.next_state, direct.next_state, d)
            if res.plan is not None:
                store.commit(res.plan)
                state = direct.next_state
        snap = store.read()
        self.assertGreater(snap.head_seq, 70)
        validate_snapshot(decode_snapshot(encode_snapshot(snap)))
        self.assertEqual(snap.current_state, state.to_dict())
        last = dates[-2]
        self.assertEqual(h.prepare_day(snap, last, series, sessions, ledger).status, "ALREADY_APPLIED")


class BaseChecks(unittest.TestCase):
    def setUp(self):
        self.snap = build_world().snap()

    def fails(self, mutate, rule, code="snapshot_invalid"):
        e = error_of(self, validate_snapshot, h.tampered(self.snap, mutate))
        self.assertEqual((e.code, e.rule), (code, rule))

    def test_normal_base_with_as_of_d_is_accepted(self):
        for ev in self.snap.events[2:]:
            base = ev["state_after"]["base"]
            self.assertIsNotNone(base["as_of_d"])                # a legitimate base has an as_of_d
            self.assertIsNone(base["fixed_decision"])
            self.assertIsNone(base["base"])
        validate_snapshot(self.snap)

    def test_base_differs_from_parent_state(self):
        self.fails(lambda e: e[3]["state_after"]["base"].__setitem__("as_of_d", D[0]), "IB-04")
        self.fails(lambda e: e[3]["state_after"]["base"].__setitem__("streak", 0), "IB-04")
        self.fails(lambda e: e[2]["state_after"]["base"].__setitem__("armed", "TRUE"), "IB-04")
        self.fails(lambda e: e[3]["state_after"]["base"].__setitem__("armed", "FALSE"), "IB-04")

    def test_base_with_fixed_decision_or_nested_base(self):
        self.fails(lambda e: e[3]["state_after"]["base"].__setitem__(
            "fixed_decision", e[2]["state_after"]["fixed_decision"]), "state_after:IB-01")
        self.fails(lambda e: e[3]["state_after"]["base"].__setitem__("base", e[2]["state_after"]["base"]),
                   "state_after:IB-01")

    def test_fixed_decision_mismatch(self):
        self.fails(lambda e: e[2]["state_after"]["fixed_decision"].__setitem__("fingerprint", "a" * 64),
                   "state_mismatch")
        self.fails(lambda e: e[2]["state_after"]["fixed_decision"].__setitem__("record_id", "OTHER"),
                   "state_mismatch")
        self.fails(lambda e: e[2]["state_after"]["fixed_decision"].__setitem__("d", D[1]), "state_after:I-03")

    def test_state_after_violating_current_state_rules(self):
        self.fails(lambda e: e[2]["state_after"].__setitem__("streak", 7), "state_after:I-05")
        self.fails(lambda e: e[2]["state_after"].__setitem__("base", None), "state_after:I-01")

    def test_state_or_transition_changed_with_consistent_hashes_is_a_mismatch(self):
        # every hash is rebuilt: the stored values still disagree with the re-calculation from the stored inputs
        def state_changed(evs):
            st = evs[1]["state_after"]
            st["armed"] = "FALSE"
        self.fails(state_changed, "state_mismatch")

        def result_changed(evs):
            evs[1]["transition_result"]["effective_streak"] += 1
        self.fails(result_changed, "transition_mismatch")

        def reasons_reordered(evs):
            r = evs[2]["transition_result"]["rules"]["EXFEAR"]["reasons"]
            r.reverse()
            r.append("extra")
        self.fails(reasons_reordered, "transition_mismatch")

    def test_input_changed_with_consistent_hashes_that_alters_the_judgement(self):
        def weaker_market(evs):
            ci = evs[5]["confirmed_inputs"]
            ci["row"]["soxx"] = 90.0                           # below the SMA: market side no longer met
            evs[5]["input_hash"] = input_hash_of(ci)
        self.fails(weaker_market, "transition_mismatch")

        def other_decision(evs):
            ci = evs[1]["confirmed_inputs"]
            ci["decision"]["current_fg_value"] = 20.0
            evs[1]["input_hash"] = input_hash_of(ci)
        self.fails(other_decision, "transition_mismatch")

    def test_limit_a_fully_consistent_rewrite_that_changes_no_judgement_is_not_detectable(self):
        # Documented limit (design 5.3): this is an integrity check, not a proof of authorship.
        def harmless(evs):
            ci = evs[1]["confirmed_inputs"]
            ci["row"]["soxx"] = 111.0
            evs[1]["input_hash"] = input_hash_of(ci)
        validate_snapshot(h.tampered(self.snap, harmless))

    def test_input_hash_must_match_inputs(self):
        def changed(evs):
            evs[1]["confirmed_inputs"]["row"]["soxx"] = 111.0           # input_hash not updated
        self.fails(changed, "input_hash")

    def test_unconfirmed_saved_intermediate_session_is_rejected_even_with_consistent_hashes(self):
        # events[4] skipped D4 and D5; make D4 unconfirmed in its saved copy and keep skipped_sessions and hashes right
        def unconfirm(evs):
            ci = evs[4]["confirmed_inputs"]
            entry = [s for s in ci["session_context"] if s["date"] == D[4]][0]
            entry["confirmed"] = False
            evs[4]["input_hash"] = input_hash_of(ci)
        self.fails(unconfirm, "skipped_session_unconfirmed")

    def test_skipped_sessions_must_equal_the_gap(self):
        self.fails(lambda e: e[4].__setitem__("skipped_sessions", [D[4]]), "skipped_sessions")
        self.fails(lambda e: e[4].__setitem__("skipped_sessions", []), "skipped_sessions")
        self.fails(lambda e: e[2].__setitem__("skipped_sessions", [D[1]]), "skipped_sessions")
        self.fails(lambda e: e[4].__setitem__("skipped_sessions", [D[5], D[4]]), "skipped_sessions")

    def test_first_apply_context_must_start_at_the_genesis_boundary(self):
        def other_boundary(evs):
            evs[1]["confirmed_inputs"]["session_context"][0]["open_at"] = "2026-03-02T14:00:00Z"
        self.fails(other_boundary, "context_boundary")


class ApplyTransitionSpies(unittest.TestCase):
    """Both paths reach apply_transition by their own bound names; each is observed and substituted separately."""

    def setUp(self):
        self.w = h.World()
        self.w.apply(D[1], 27.0)
        self.w.apply(D[2], 40.0)
        self.w.ledger.append(h.obs("R-" + D[3], D[3], 41.0))

    def spy(self, target):
        calls = []
        real = getattr(*target)

        def wrapper(*a, **k):
            calls.append(a[1])
            return real(*a, **k)
        return calls, wrapper

    def test_normal_and_recompute_paths_use_their_own_names(self):
        engine_calls, engine_wrapper = self.spy((core_engine, "apply_transition"))
        recompute_calls, recompute_wrapper = self.spy((recompute, "apply_transition"))
        origin_calls, origin_wrapper = self.spy((core_transition, "apply_transition"))
        with mock.patch.object(core_engine, "apply_transition", engine_wrapper), \
                mock.patch.object(recompute, "apply_transition", recompute_wrapper), \
                mock.patch.object(core_transition, "apply_transition", origin_wrapper):
            res = self.w.prepare(D[3])
        self.assertEqual(res.status, "PREPARED")
        self.assertEqual(engine_calls, [D[3]])                                   # evaluate_day: exactly once
        self.assertEqual(recompute_calls, [D[1], D[2], D[1], D[2], D[3]])        # 2 saved + 3 candidate days
        self.assertEqual(origin_calls, [])                                       # the origin name is not what runs

    def test_origin_patch_does_not_change_either_path(self):
        def broken(*a, **k):
            raise AssertionError("origin name must not be reached")
        with mock.patch.object(core_transition, "apply_transition", broken):
            res = self.w.prepare(D[3])
            validate_snapshot(self.w.snap())
        self.assertEqual(res.status, "PREPARED")

    def test_commit_check_uses_the_recompute_path(self):
        plan = self.w.prepare(D[3]).plan
        recompute_calls, wrapper = self.spy((recompute, "apply_transition"))
        with mock.patch.object(recompute, "apply_transition", wrapper):
            self.w.store.commit(plan)
        self.assertEqual(recompute_calls, [D[1], D[2], D[3]])                    # the same full check as validate

    @staticmethod
    def altered(fn, **changes):
        def wrapper(*a, **k):
            t = fn(*a, **k)
            return dataclasses.replace(t, **changes)
        return wrapper

    def test_substituted_engine_result_is_caught_by_the_candidate_self_check(self):
        real = core_engine.apply_transition
        before = self.w.snap()
        for change in ({"effective_streak": 9}, {"gap": True}, {"notes": ["x"]},
                       {"run_class": core_transition.RunClass.CONDITION_MET}):
            with mock.patch.object(core_engine, "apply_transition", self.altered(real, **change)):
                e = error_of(self, self.w.prepare, D[3])
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", "transition_mismatch"), change)
        # an altered next-state candidate: the transition_result is the same, the state differs
        real_next = real

        def other_state(*a, **k):
            t = real_next(*a, **k)
            ns = t.next_state
            return dataclasses.replace(t, next_state=dataclasses.replace(ns, streak=ns.streak + 1))
        with mock.patch.object(core_engine, "apply_transition", other_state):
            e = error_of(self, self.w.prepare, D[3])
        self.assertIn(e.rule, ("state_after:I-05", "state_mismatch", "state_after:I-06"))
        self.assertEqual(self.w.snap(), before)

    def test_substituted_recompute_result_is_caught_for_a_stored_snapshot(self):
        real = recompute.apply_transition
        snap = self.w.snap()
        with mock.patch.object(recompute, "apply_transition", self.altered(real, effective_streak=9)):
            e = error_of(self, validate_snapshot, snap)
            self.assertEqual((e.code, e.rule), ("snapshot_invalid", "transition_mismatch"))
            e = error_of(self, self.w.prepare, D[3])                      # step 1 of prepare_day is the same check
            self.assertEqual(e.rule, "transition_mismatch")
        validate_snapshot(snap)

    def test_candidate_self_check_blocks_prepared_when_only_the_new_day_disagrees(self):
        real = recompute.apply_transition

        def only_new_day(*a, **k):
            t = real(*a, **k)
            return dataclasses.replace(t, effective_streak=9) if a[1] == D[3] else t
        with mock.patch.object(recompute, "apply_transition", only_new_day):
            validate_snapshot(self.w.snap())                            # the stored history is still fine
            e = error_of(self, self.w.prepare, D[3])                    # the new day is not
        self.assertEqual((e.code, e.rule), ("snapshot_invalid", "transition_mismatch"))

    def test_prepared_plan_passes_the_commit_check_when_nothing_changes(self):
        plan = self.w.prepare(D[3]).plan
        self.w.store.commit(plan)
        self.assertEqual(self.w.snap().head_seq, 3)
        validate_snapshot(self.w.snap())

    def test_the_new_package_holds_no_second_copy_of_the_formulas(self):
        self.assertIs(recompute.apply_transition, core_transition.apply_transition)
        from v2_persistence import runner
        self.assertIs(runner.evaluate_day, core_engine.evaluate_day)


if __name__ == "__main__":
    unittest.main()
