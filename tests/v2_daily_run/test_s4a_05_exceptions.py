"""S4A-14: the way out. Whatever CoreError a call raises after the store was reached, run_morning returns a RunReport
(STOPPED) built outside the handler, with nothing of the exception left; any other exception passes through unchanged."""
import sys
import unittest
from unittest import mock

import s4a_helpers as S
import v2_daily_run as R
import v2_daily_run.run as run_module
from v2_core.errors import ConflictError, CoreError, InputError
from v2_persistence.errors import PersistenceError

D, P = S.D, S.P
HOSTILE = "/tmp/secret-token-123"
KINDS = (
    ("input", lambda: InputError("x_input_error", "market")),
    ("persistence", lambda: PersistenceError("x_persistence_error", "history", rule="x_rule")),
    ("conflict", lambda: ConflictError("x_conflict_error", "observation_role")),
    ("local", lambda: S.LocalStoreError("x_store_error", "store", "read", rule="x_rule")),
    ("core_detail", lambda: CoreError("x_core_error", "sessions", detail=D[2])),
    ("hostile", lambda: CoreError("bad code " + HOSTILE, HOSTILE + "/field", detail=HOSTILE)),
)
POINTS = ("store.read", "store.publish", "store.reconcile", "read_effective", "prepare_history_day", "publish_day")


class Counting(object):
    """Wraps the scripted store and the three module functions: counts the calls per point and raises `error()` at the
    k-th call of `point` (never when point is None)."""

    def __init__(self, inner, point=None, k=None, error=None):
        self.inner, self.point, self.k, self.error = inner, point, k, error
        self.counts = dict.fromkeys(POINTS, 0)

    def hit(self, name):
        self.counts[name] += 1
        if name == self.point and self.counts[name] == self.k:
            raise self.error()

    def read(self):
        self.hit("store.read")
        return self.inner.read()

    def publish(self, publication):
        self.hit("store.publish")
        return self.inner.publish(publication)

    def reconcile(self, publication):
        self.hit("store.reconcile")
        return self.inner.reconcile(publication)

    def wrap(self, name):
        original = getattr(run_module, name)

        def call(*args, **kwargs):
            self.hit(name)
            return original(*args, **kwargs)
        return call


class Sweep(S.RootCase):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])

    def fresh(self):
        import os
        for name in os.listdir(self.root):
            os.unlink(os.path.join(self.root, name))
        return S.Flaky(self.store(), {2: "uncertain_after_write"})

    def execute(self, point=None, k=None, error=None):
        spy_seen = []

        class Spy(R.RunReport):
            __slots__ = ()

            def __init__(spy_self, *args, **kwargs):
                spy_seen.append(sys.exc_info()[1])
                super().__init__(*args, **kwargs)

        counting = Counting(self.fresh(), point, k, error)
        patches = [mock.patch.object(run_module, "RunReport", Spy)]
        for name in ("read_effective", "prepare_history_day", "publish_day"):
            patches.append(mock.patch.object(run_module, name, counting.wrap(name)))
        for p in patches:
            p.start()
        try:
            try:
                return counting, S.run(counting, self.w, S.now_at(D[3])), None, spy_seen
            except BaseException as e:           # the test must see whatever leaves run_morning
                return counting, None, e, spy_seen
        finally:
            for p in patches:
                p.stop()

    def test_a_clean_run_counts_the_call_points_of_the_scenario(self):
        counting, report, raised, seen = self.execute()
        self.assertIsNone(raised)
        self.assertEqual((report.outcome, [c.d for c in report.consumed]), ("DONE", [D[1], D[2], D[3]]))
        for point in POINTS:
            self.assertGreaterEqual(counting.counts[point], 1, point)
        self.assertEqual(seen, [None])                                       # built outside any handler

    def test_every_core_error_at_every_call_point_gives_a_stopped_report_with_nothing_left_of_the_exception(self):
        reference = self.execute()[0].counts
        cases = 0
        for point in POINTS:
            for k in range(1, reference[point] + 1):
                for name, make in KINDS:
                    with self.subTest(point=point, k=k, error=name):
                        counting, report, raised, seen = self.execute(point, k, make)
                        self.assertIsNone(raised, "an exception left run_morning")
                        self.assertIsInstance(report, R.RunReport)
                        self.assertEqual((report.outcome, report.exit_code), ("STOPPED", 1))
                        self.assertEqual(counting.counts[point], k)             # nothing was called after the error
                        expected = "unknown_error" if name == "hostile" else make().code
                        self.assertEqual(report.code, expected)
                        self.assertEqual(report.detail, D[2] if name == "core_detail" else None)
                        for value in (report.code, report.field, report.rule, report.detail):
                            self.assertNotIn(HOSTILE, str(value))
                        self.assertNotIn(HOSTILE, report.message)
                        self.assertNotIn(HOSTILE, repr(report))
                        self.assertFalse([v for v in (getattr(report, n) for n in R.RunReport._NAMES)
                                          if isinstance(v, BaseException)])
                        self.assertEqual(seen, [None])                          # RunReport made outside the handler
                        cases += 1
        self.assertEqual(cases, len(KINDS) * sum(reference[p] for p in POINTS))
        self.assertGreaterEqual(cases, 60)
        type(self).cases = cases

    def test_any_other_exception_passes_through_unchanged_at_every_call_point(self):
        reference = self.execute()[0].counts
        for point in POINTS:
            for k in range(1, reference[point] + 1):
                with self.subTest(point=point, k=k):
                    boom = RuntimeError("program error")
                    counting, report, raised, seen = self.execute(point, k, lambda: boom)
                    self.assertIs(raised, boom)
                    self.assertIsNone(report)
                    self.assertIsNone(raised.__context__)
                    self.assertIsNone(raised.__cause__)
                    self.assertEqual(seen, [])
        for exc in (KeyError("x"), AttributeError("x"), AssertionError("x"), OSError("x"), ValueError("x")):
            counting, report, raised, seen = self.execute("prepare_history_day", 1, lambda exc=exc: exc)
            self.assertIs(raised, exc)

    def test_a_report_made_for_stopped_holds_only_plain_values(self):
        _c, report, _r, _s = self.execute("store.publish", 2, KINDS[3][1])
        for name in R.RunReport._NAMES:
            value = getattr(report, name)
            self.assertIsInstance(value, (str, int, tuple, type(None)), name)
        self.assertTrue(all(type(c).__name__ == "ConsumedDay" for c in report.consumed))


if __name__ == "__main__":
    unittest.main()
