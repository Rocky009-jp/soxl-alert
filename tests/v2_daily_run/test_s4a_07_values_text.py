"""S4A-05 / 08 / 15 (values): the report is immutable, its repr shows no text, and no text carries a path, an exception
text, a URL or a secret. The four kinds of text (DONE, DONE with a gap, STALE, STOPPED) are made by test_the_four_examples."""
import unittest

import s4a_helpers as S
import v2_daily_run as R
from v2_core.errors import CoreError

D, P = S.D, S.P


class Values(S.RootCase):
    def done(self):
        S.decide(self.w, [1, 2, 4])
        return S.run(self.store(), self.w, S.now_at(D[5]))

    def test_the_report_and_its_days_are_immutable(self):
        report = self.done()
        for target, name in ((report, "outcome"), (report, "message"), (report.consumed[0], "d"),
                             (report.consumed[0], "gap")):
            with self.assertRaises(AttributeError):
                setattr(target, name, "x")
            with self.assertRaises(AttributeError):
                delattr(target, name)
        with self.assertRaises(AttributeError):
            report.new_field = 1
        self.assertIsInstance(report.consumed, tuple)
        self.assertIsInstance(report.consumed[0].skipped_sessions, tuple)

    def test_equal_reports_are_equal_and_hash_alike(self):
        a = self.done()
        import shutil
        root = S.make_root()
        self.addCleanup(shutil.rmtree, root, True)
        w = P.World(0)
        S.decide(w, [1, 2, 4])
        b = S.run(S.real_store(root, w), w, S.now_at(D[5]))
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertNotEqual(a, R.RunReport("STALE", D[5], (), None, "x"))

    def test_the_repr_shows_neither_the_text_nor_a_path_nor_the_digest(self):
        for report in (self.done(),):
            text = repr(report)
            self.assertNotIn(report.message, text)
            self.assertNotIn(self.root, text)
            self.assertNotIn(report.history_digest, text)
            self.assertNotIn("armed", text)
            self.assertIn("RunReport(outcome=DONE", text)
            self.assertLess(len(text), 200)
        self.assertIn("ConsumedDay(d=", repr(report.consumed[0]))

    def test_a_report_needs_a_known_outcome(self):
        with self.assertRaises(ValueError):
            R.RunReport("OK", D[1], (), None, "x")
        self.assertEqual(R.RunReport("DONE", D[1], (), None, "x").exit_code, 0)
        self.assertEqual(R.RunReport("STALE", D[1], (), None, "x").exit_code, 1)
        self.assertEqual(R.RunReport("STOPPED", D[1], (), None, "x").exit_code, 1)


class Texts(S.RootCase):
    FORBIDDEN = ("Traceback", "Error(", "http://", "https://", "token", "secret", "\\", "/tmp", "/home")

    def assertClean(self, report):
        for text in (report.message, repr(report), str(report.code), str(report.field), str(report.rule),
                     str(report.detail)):
            self.assertNotIn(self.root, text)
            for bad in self.FORBIDDEN:
                self.assertNotIn(bad, text)

    def test_the_four_examples(self):
        # DONE
        S.decide(self.w, [1, 2, 3])
        done = S.run(self.store(), self.w, S.now_at(D[4]))
        # DONE with a gap
        import shutil
        root2 = S.make_root()
        self.addCleanup(shutil.rmtree, root2, True)
        w2 = P.World(0)
        S.decide(w2, [1, 2, 4])
        gap = S.run(S.real_store(root2, w2), w2, S.now_at(D[5]))
        # STALE
        root3 = S.make_root()
        self.addCleanup(shutil.rmtree, root3, True)
        w3 = P.World(0, unconfirmed=(D[3],))
        S.decide(w3, [1, 2, 4])
        stale = S.run(S.real_store(root3, w3), w3, S.now_at(D[4]))
        # STOPPED
        S.put(self.root, S.LOCK, b"x")
        stopped = S.run(self.store(initialize=False), self.w, S.now_at(D[4]))
        for name, report in (("DONE", done), ("DONE_GAP", gap), ("STALE", stale), ("STOPPED", stopped)):
            self.assertClean(report)
            self.assertIn(report.outcome, name)
            self.assertEqual(report.exit_code, 0 if name.startswith("DONE") else 1)
        self.assertEqual((done.outcome, gap.outcome, stale.outcome, stopped.outcome),
                         ("DONE", "DONE", "STALE", "STOPPED"))

    def test_a_stopped_text_names_the_code_and_the_days_saved_and_says_it_is_not_a_miss(self):
        S.decide(self.w, [1, 2, 3])
        self.w.ledger[2] = P.obs("R3", D[3], 22.0, hour=10)
        report = S.run(self.store(), self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("STOPPED", "decision_outside_window"))
        text = report.message
        for needle in ("decision_outside_window", D[1], D[2], "条件未達ではありません", "前日の値や古い日付で補ってもいません",
                       "この実行で保存した日"):
            self.assertIn(needle, text)
        self.assertClean(report)

    def test_a_stopped_text_without_any_saved_day_says_none(self):
        S.decide(self.w, [1])
        store = self.store()
        S.put(self.root, S.LOCK, b"x")
        report = S.run(store, self.w, S.now_at(D[2]))
        self.assertIn("この実行で保存した日: なし", report.message)

    def test_hostile_codes_fields_rules_and_details_of_an_error_never_reach_the_text(self):
        class Hostile(object):
            def read(self):
                raise CoreError("x/y z", "C:\\secret\\path", detail="https://example.invalid/token")

            def publish(self, p):
                raise AssertionError

            def reconcile(self, p):
                raise AssertionError
        report = S.run(Hostile(), self.w, S.now_at(D[3]))
        self.assertEqual((report.outcome, report.code, report.field, report.rule, report.detail),
                         ("STOPPED", "unknown_error", None, None, None))
        self.assertClean(report)


if __name__ == "__main__":
    unittest.main()
