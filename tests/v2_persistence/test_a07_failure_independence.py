"""A-07: in-memory failure injection, independence of values, strict input rejection, safe error text.

"A lost answer" is simulated by an exception raised after the store already committed. No network is used and no
power loss is produced.
"""
import copy
import unittest
from unittest import mock

import p_helpers as h
from v2_core.errors import ConflictError, InputError
from v2_persistence import store as store_module
from v2_persistence.codec import Snapshot, decode_snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import reconcile

D = h.DATES
ERRORS = (PersistenceError, InputError, ConflictError)


class FailureInjection(unittest.TestCase):
    def test_exception_in_the_pre_commit_check_leaves_the_store_untouched(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        plan = w.prepare(D[1]).plan
        before = w.snap()
        with mock.patch.object(store_module, "validate_snapshot", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                w.store.commit(plan)
        self.assertEqual(w.snap(), before)
        self.assertEqual(w.snap().head_seq, 0)
        w.store.commit(plan)                                   # the lock was released; the same plan now works
        self.assertEqual(w.snap().head_seq, 1)

    def test_candidate_that_fails_the_check_is_never_stored(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        plan = w.prepare(D[1]).plan
        before = w.snap()
        with mock.patch.object(store_module, "validate_snapshot",
                               side_effect=PersistenceError("snapshot_invalid", "snapshot", rule="injected")):
            with self.assertRaises(PersistenceError):
                w.store.commit(plan)
        self.assertEqual(w.snap(), before)

    def test_answer_lost_after_a_successful_commit_is_resolved_by_reconcile_with_nothing_added(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        plan = w.prepare(D[1]).plan
        real_commit = w.store.commit

        class AnswerLost(Exception):
            pass

        def commit_then_lose(p):
            real_commit(p)
            raise AnswerLost()
        with self.assertRaises(AnswerLost):
            commit_then_lose(plan)
        snap = w.store.read()
        self.assertEqual(snap.head_seq, 1)
        self.assertEqual(reconcile(plan, snap).status, "ALREADY_APPLIED")
        # the caller does not commit again; if it did, the old head makes the second commit fail
        with self.assertRaises(PersistenceError):
            w.store.commit(plan)
        self.assertEqual(w.snap(), snap)
        self.assertEqual(sum(1 for e in snap.events if e["kind"] == "APPLY"), 1)

    def test_answer_lost_before_the_commit_ran_is_replan_or_retry_without_a_double_record(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        plan = w.prepare(D[1]).plan
        snap = w.store.read()
        self.assertEqual(reconcile(plan, snap).status, "REPLAN_REQUIRED")
        w.store.commit(plan)                                    # a retry of the same plan is still possible
        self.assertEqual(reconcile(plan, w.store.read()).status, "ALREADY_APPLIED")

    def test_every_refused_operation_keeps_the_stored_snapshot(self):
        w = h.World()
        w.apply(D[1], 27.0)
        w.apply(D[4], 28.0)
        head = w.snap()
        w.ledger.append(h.obs("NEW", D[5], 29.0))
        plan = w.prepare(D[5]).plan
        w.ledger.append(h.obs("ADD", D[4], 33.0))
        operations = [
            lambda: w.prepare(D[4]),                                # decision_conflict
            lambda: w.prepare(D[1]),                                # state ahead
            lambda: w.prepare("2026-02-30"),
            lambda: w.prepare(D[5], snapshot=h.tampered(head, lambda e: e[1].__setitem__("seq", 9))),
            lambda: w.store.initialize(w.snap()),
            lambda: w.store.initialize(h.make_genesis(D[0], w.sessions)),
        ]
        for op in operations:
            with self.assertRaises(ERRORS):
                op()
            self.assertEqual(w.snap(), head)
            self.assertEqual((w.snap().head_seq, w.snap().head_hash), (head.head_seq, head.head_hash))
        w.store.commit(plan)                                        # the plan prepared before is still valid
        after = w.snap()
        for p in (plan, "x"):
            with self.assertRaises(PersistenceError):
                w.store.commit(p)
            self.assertEqual(w.snap(), after)


class IndependenceOfValues(unittest.TestCase):
    def setUp(self):
        self.w = h.World()
        self.w.apply(D[1], 27.0)
        self.w.apply(D[2], 40.0)

    def test_snapshot_accessors_return_copies(self):
        snap = self.w.snap()
        text = snap.to_dict()
        events = snap.events
        state = snap.current_state
        events[1]["d"] = "1999-01-01"
        events[1]["confirmed_inputs"]["row"]["soxx"] = 1.0
        events.append({"junk": 1})
        state["streak"] = 99
        text["events"].clear()
        self.assertEqual(self.w.snap().events[1]["d"], D[1])
        self.assertEqual(len(self.w.snap().events), 3)
        self.assertEqual(self.w.snap().current_state["streak"], 1)
        validate_snapshot(self.w.snap())
        with self.assertRaises(AttributeError):
            snap.head_seq = 5
        with self.assertRaises(AttributeError):
            snap._text = "x"
        with self.assertRaises(AttributeError):
            del snap._view
        with self.assertRaises(TypeError):
            Snapshot()

    def test_plan_is_independent_of_caller_inputs_and_of_what_it_hands_out(self):
        self.w.ledger.append(h.obs("R3", D[3], 41.0))
        ledger_before = copy.deepcopy(self.w.ledger)
        res = self.w.prepare(D[3])
        plan = res.plan
        event = plan.event
        expected = copy.deepcopy(event)
        event["d"] = "1999-01-01"
        event["confirmed_inputs"]["decision"]["current_fg_value"] = 1.0
        self.w.ledger[-1]["current_fg_value"] = 0.0                     # the caller edits the ledger afterwards
        self.w.ledger.append({"junk": 1})
        res.core_result.rules.clear()                                   # and the returned core result
        self.assertEqual(plan.event, expected)
        self.assertEqual(self.w.ledger[:-1][:-1], ledger_before[:-1])
        self.w.store.commit(plan)
        self.assertEqual(self.w.snap().events[-1], expected)
        with self.assertRaises(AttributeError):
            plan.d = "x"
        with self.assertRaises(AttributeError):
            plan._event_text = "x"

    def test_inputs_are_copied_at_the_start_of_prepare_day(self):
        ledger = [h.obs("R3", D[3], 41.0)]
        res = h.prepare_day(self.w.snap(), D[3], self.w.series, self.w.sessions, self.w.ledger + ledger)
        ledger[0]["current_fg_value"] = 5.0
        self.assertEqual(res.plan.event["confirmed_inputs"]["decision"]["current_fg_value"], 41.0)
        sessions = h.make_sessions()
        res = h.prepare_day(self.w.snap(), D[3], self.w.series, sessions, self.w.ledger + [h.obs("R3", D[3], 41.0)])
        sessions.sessions.clear()
        self.assertEqual(res.plan.event["d"], D[3])

    def test_caller_edits_during_the_run_do_not_reach_the_result(self):
        """The caller's ledger, session list and series are changed while prepare_day is running (from inside the
        first call that reads them). The run works on its own copies, so the outcome is the one for the inputs
        it was given."""
        from v2_persistence import runner
        w = self.w
        w.ledger.append(h.obs("R3", D[3], 41.0))
        real_select, real_eval = runner.select_decision, runner.evaluate_day
        fired = []

        def edit_inputs():
            if fired:
                return
            fired.append(1)
            w.ledger[0]["current_fg_value"] = 1.0           # a stored decision changes
            w.ledger.append(h.obs("INTRUDER", D[2], 3.0))
            w.sessions.sessions.reverse()                    # the session list is scrambled
            w.series.rows[D[3]] = h.row(D[3], soxx=1.0)       # and a market row is replaced

        def select(raw, sessions, d):
            edit_inputs()
            return real_select(raw, sessions, d)

        def evaluate(state, d, series, sessions, raw):
            edit_inputs()
            return real_eval(state, d, series, sessions, raw)
        expected = h.prepare_day(w.snap(), D[3], h.make_series(), h.make_sessions(),
                                 copy.deepcopy(w.ledger)).plan.event
        with mock.patch.object(runner, "select_decision", select), mock.patch.object(runner, "evaluate_day", evaluate):
            res = w.prepare(D[3])
        self.assertTrue(fired)
        self.assertEqual(res.status, "PREPARED")
        self.assertEqual(res.plan.event, expected)

    def test_series_edits_between_the_ledger_checks_and_the_core_call_do_not_reach_the_result(self):
        from v2_persistence import runner
        w = self.w
        w.ledger.append(h.obs("R3", D[3], 41.0))
        real_eval = runner.evaluate_day
        expected = h.prepare_day(w.snap(), D[3], h.make_series(), h.make_sessions(), copy.deepcopy(w.ledger)).plan.event

        def evaluate(state, d, series, sessions, raw):
            w.series.rows[D[3]] = h.row(D[3], soxx=1.0)       # the original series changes right at the core call
            return real_eval(state, d, series, sessions, raw)
        with mock.patch.object(runner, "evaluate_day", evaluate):
            res = w.prepare(D[3])
        self.assertEqual(res.plan.event, expected)

    def test_store_state_is_independent_of_what_read_returned(self):
        snap = self.w.store.read()
        snap.events[0]["start_after"] = "2000-01-01"
        again = self.w.store.read()
        self.assertEqual(again.events[0]["start_after"], D[0])
        self.assertIs(again, self.w.store.read())                   # immutable value: sharing it is safe

    def test_genesis_given_to_initialize_is_not_aliased(self):
        store = store_module.MemoryStore()
        genesis = h.make_genesis(D[0], self.w.sessions)
        store.initialize(genesis)
        genesis.events[0]["start_after"] = "2000-01-01"
        self.assertEqual(store.read().events[0]["start_after"], D[0])


class StrictInputs(unittest.TestCase):
    def setUp(self):
        self.w = h.World()

    def refuse(self, row, code=None):
        self.w.ledger[:] = [row]
        with self.assertRaises(ERRORS) as cm:
            self.w.prepare(D[1])
        if code is not None:
            self.assertEqual(cm.exception.code, code)
        self.assertEqual(self.w.snap().head_seq, 0)

    def test_bad_numbers_in_the_ledger(self):
        base = h.obs("R1", D[1], 27.0)
        for value in (True, False, float("nan"), float("inf"), -1, 100.5, "abc", "nan", "inf", None, [27.0]):
            self.refuse(dict(base, current_fg_value=value), "fg_value_invalid")

    def test_bad_times_and_windows_in_the_ledger(self):
        base = h.obs("R1", D[1], 27.0)
        for text in ("2026-03-03T20:00", "2026-03-03", "bad", 5, None):
            self.refuse(dict(base, observed_at_iso8601=text))
        self.refuse(dict(base, observed_at_iso8601="2026-03-03T12:00:00-05:00"), "decision_outside_window")
        self.refuse(dict(base, observed_at_iso8601="2026-03-04T09:30:00-05:00"), "decision_outside_window")

    def test_bad_series_and_sessions_objects(self):
        self.w.ledger.append(h.obs("R1", D[1], 27.0))
        with self.assertRaises(InputError) as cm:
            h.prepare_day(self.w.snap(), D[1], self.w.series, [1, 2, 3], self.w.ledger)
        self.assertEqual(cm.exception.code, "sessions_invalid")
        with self.assertRaises(InputError) as cm:
            h.prepare_day(self.w.snap(), D[1], self.w.series, self.w.sessions, "not rows")
        self.assertEqual(cm.exception.code, "observation_invalid")

    def test_bad_rows_inside_the_series_are_core_errors_and_not_no_signal(self):
        self.w.ledger.append(h.obs("R1", D[1], 27.0))
        series = h.make_series()
        series.rows.pop(D[1])
        series.dates = sorted(series.rows)
        self.w.series = series
        with self.assertRaises(InputError) as cm:
            self.w.prepare(D[1])
        self.assertIn(cm.exception.code, ("session_series_mismatch", "target_row_missing"))
        self.assertEqual(self.w.snap().head_seq, 0)

    def test_non_finite_market_values_from_the_series_are_refused_not_stored(self):
        self.w.ledger.append(h.obs("R1", D[1], 27.0))
        before = self.w.snap()
        for bad in (float("nan"), float("inf"), float("-inf")):
            self.w.series = h.make_series(per_date={D[1]: dict(shd=bad)})
            with self.assertRaises(PersistenceError) as cm:
                self.w.prepare(D[1])
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "event_build"))
            self.assertEqual(self.w.snap(), before)
        for field, bad in (("rsi", 101.0), ("soxx", 0.0), ("prev_rsi", -1.0)):          # finite but out of range
            self.w.series = h.make_series(per_date={D[1]: {field: bad}})
            with self.assertRaises(PersistenceError) as cm:
                self.w.prepare(D[1])
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "row"))
            self.assertEqual(self.w.snap(), before)

    def test_errors_do_not_echo_raw_input(self):
        secret = "https://hooks.example.invalid/api/webhooks/123456/SECRET-TOKEN"
        self.w.ledger[:] = [dict(h.obs("R1", D[1], 27.0), record_id=secret)]
        with self.assertRaises(ERRORS) as cm:
            self.w.prepare(D[1])
        self.assert_safe(cm.exception, secret)
        bad_snapshot = h.tampered(h.World().snap(), lambda e: e[0].__setitem__("start_after", secret))
        with self.assertRaises(ERRORS) as cm:
            validate_snapshot(bad_snapshot)
        self.assert_safe(cm.exception, secret)
        with self.assertRaises(ERRORS) as cm:
            Snapshot.from_dict({"a": {secret: object()}})
        self.assert_safe(cm.exception, secret)
        with self.assertRaises(ERRORS) as cm:
            decode_snapshot('{"k":"%s","k":1}' % secret)
        self.assert_safe(cm.exception, secret)

    def assert_safe(self, exc, secret):
        for text in (str(exc), repr(exc), str(getattr(exc, "detail", "")), str(getattr(exc, "rule", "")),
                     str(getattr(exc, "field", "")), str(exc.args)):
            self.assertNotIn("SECRET", text)
            self.assertNotIn("hooks.example", text)
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()


class MutationRobustness(unittest.TestCase):
    """Random leaf-level edits of a valid history (fixed seed): validation either accepts the (rare) harmless edit or
    raises the package error. It never crashes with another exception and never leaks the edited value."""

    LEAVES = (None, True, False, 0, -1, 1, 7, 1.5, -2.5, "", "x", "2026-03-04", "2026-03-04T20:00:00Z", "A" * 70, [], {},
              [1], {"k": 1}, "http://example.invalid/hook")

    @staticmethod
    def paths(obj, prefix=()):
        out = [prefix]
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.extend(MutationRobustness.paths(v, prefix + (k,)))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                out.extend(MutationRobustness.paths(v, prefix + (i,)))
        return out

    def test_random_edits_only_raise_package_errors(self):
        import random
        rng = random.Random(20261028)
        w = h.World()
        for i, v in ((1, 27.0), (2, 40.0), (5, 41.0)):
            w.apply(D[i], v)
        base = w.snap().to_dict()
        paths = [p for p in self.paths(base) if p]
        accepted = rejected = 0
        for n in range(600):
            data = copy.deepcopy(base)
            path = rng.choice(paths)
            parent = data
            for key in path[:-1]:
                parent = parent[key]
            kind = rng.choice(("set", "set", "set", "delete", "add"))
            if kind == "set":
                parent[path[-1]] = copy.deepcopy(rng.choice(self.LEAVES))
            elif kind == "delete" and isinstance(parent, dict):
                del parent[path[-1]]
            elif kind == "delete":
                parent.pop(path[-1])
            elif isinstance(parent, dict):
                parent["unexpected"] = 1
            else:
                parent.append(rng.choice(self.LEAVES))
            snap = Snapshot.from_dict(data)
            try:
                validate_snapshot(snap)
                accepted += 1
            except PersistenceError as e:
                rejected += 1
                self.assertNotIn("example.invalid", str(e) + repr(e) + str(e.rule) + str(e.detail))
            # a second pass with the hashes rebuilt, so that deeper checks are reached
            try:
                again = h.rehash(data["events"])
            except (KeyError, TypeError, AttributeError, IndexError):
                continue                                   # the test helper cannot rebuild this shape
            try:
                validate_snapshot(again)
                accepted += 1
            except PersistenceError as e:
                rejected += 1
                self.assertNotIn("example.invalid", str(e) + repr(e) + str(e.rule) + str(e.detail))
        self.assertGreater(rejected, 600)
        self.assertLess(accepted, 400)
