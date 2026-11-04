"""S4A-12 (an uncertain save: reconcile once, read again, go on) and S4A-13 (a) (another writer between the read and
the save). The store is a scripted wrapper over the real C-3 file store (the real reconcile) unless the case says so."""
import os
import unittest

import s4a_helpers as S
import v2_daily_run as R

D, P, O, U, C2 = S.D, S.P, S.O, S.U, S.C2


class Uncertain(S.RootCase):
    def setUp(self):
        super().setUp()
        S.decide(self.w, range(1, 5))
        self.normal_root = S.make_root()
        import shutil
        self.addCleanup(shutil.rmtree, self.normal_root, True)

    def normal(self):
        """The same morning on a store without faults: the reference result."""
        return S.run(S.real_store(self.normal_root, self.w), self.w, S.now_at(D[4]))

    def assertSameAsNormal(self, report):
        ref = self.normal()
        self.assertEqual((report.outcome, report.message, report.history_digest, report.target_d),
                         (ref.outcome, ref.message, ref.history_digest, ref.target_d))
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in report.consumed],
                         [(c.d, c.gap, c.skipped_sessions) for c in ref.consumed])
        self.assertEqual(S.raw(self.root), S.raw(self.normal_root))
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[3], D[4]])
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 4))

    def test_a_save_that_was_written_but_reported_uncertain_is_reconciled_read_again_and_the_run_goes_on(self):
        for n in (1, 2, 4):                                   # the first, a middle and the last (target) day
            with self.subTest(uncertain_publish=n):
                self.tearDown_root()
                flaky = S.Flaky(self.store(), {n: "uncertain_after_write"})
                report = S.run(flaky, self.w, S.now_at(D[4]))
                self.assertEqual((report.outcome, report.code), ("DONE", None))
                self.assertEqual(flaky.count("reconcile"), 1)
                self.assertEqual(flaky.count("read"), 2)
                self.assertEqual(flaky.count("publish"), 4)           # every day once; the uncertain one is not sent again
                self.assertEqual(len(set(flaky.hashes)), 4)
                self.assertSameAsNormal(report)

    def tearDown_root(self):
        for name in os.listdir(self.root):
            os.unlink(os.path.join(self.root, name))
        for name in os.listdir(self.normal_root):
            os.unlink(os.path.join(self.normal_root, name))

    def test_a_save_that_was_followed_by_another_writers_day_is_published_then_extended_and_read_again(self):
        def other_writer(inner):
            history = inner.read()
            inner.publish(U.publish_day(history, D[2], self.w.series, self.w.sessions, self.w.ledger))
        flaky = S.Flaky(self.store(), {1: ("hook_after_write", other_writer)})
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("DONE", None))
        self.assertEqual(flaky.count("reconcile"), 1)
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[3], D[4]])    # D2 once, never saved twice
        self.assertEqual(flaky.count("publish"), 3)                            # D1 (uncertain), then D3 and D4
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 4))
        self.assertEqual([c.d for c in report.consumed], [D[1], D[3], D[4]])    # D2 was another writer's

    def test_a_save_that_did_not_happen_is_not_published_the_run_stops_and_publish_was_called_once(self):
        flaky = S.Flaky(self.store(), {3: "uncertain_without_write"})
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.exit_code, report.code, report.detail),
                         ("STOPPED", 1, "run_publish_not_published", D[3]))
        self.assertEqual(flaky.count("publish"), 3)                            # D1, D2, and D3 once
        self.assertEqual(flaky.count("reconcile"), 1)
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2]])
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 2))
        self.assertEqual(len(set(flaky.hashes)), len(flaky.hashes))
        self.assertIn("run_publish_not_published", report.message)

    def test_another_writer_with_other_content_at_the_same_place_is_a_conflict(self):
        other = P.World(0)
        other.ledger.append(P.obs("R1", D[1], 31.0))

        def rival(inner):
            history = inner.read()
            inner.publish(U.publish_day(history, D[1], other.series, other.sessions, other.ledger))
        flaky = S.Flaky(self.store(), {1: ("hook_without_write", rival)})
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code, report.detail), ("STOPPED", "run_publish_conflict", D[1]))
        self.assertEqual(flaky.count("publish"), 1)
        self.assertEqual(report.consumed, ())
        self.assertEqual(S.applies_of(self.root), [D[1]])                      # the rival's day, once

    def test_the_conflict_outcome_of_a_store_is_stopped_too(self):
        flaky = S.Flaky(self.store(), {2: "uncertain_without_write"}, ("outcome", "CONFLICT"))
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.code, flaky.count("publish")), ("run_publish_conflict", 2))

    def test_an_error_of_the_reconciliation_itself_stops_the_run_with_its_code(self):
        flaky = S.Flaky(self.store(), {2: "uncertain_after_write"}, ("raise", S.LocalStoreError("store_busy", "lock", "lock_acquire")))
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("STOPPED", "store_busy"))
        self.assertEqual(flaky.count("publish"), 2)
        self.assertEqual(flaky.count("reconcile"), 1)
        self.assertEqual([c.d for c in report.consumed], [D[1]])

    def test_a_real_reconcile_that_cannot_read_stops_with_the_store_code(self):
        def lock_it(inner):
            S.put(self.root, S.LOCK, b"left over")
        flaky = S.Flaky(self.store(), {1: "uncertain_after_write"}, ("hook", lock_it))
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("STOPPED", "store_busy"))
        self.assertEqual(flaky.count("publish"), 1)

    def test_a_second_uncertain_save_in_the_same_run_stops_and_reconcile_was_called_once(self):
        flaky = S.Flaky(self.store(), {1: "uncertain_after_write", 3: "uncertain_after_write"})
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code, report.detail), ("STOPPED", "run_publish_uncertain", D[3]))
        self.assertEqual(flaky.count("reconcile"), 1)
        self.assertEqual(flaky.count("read"), 2)
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2]])
        again = S.run(self.store(initialize=False), self.w, S.now_at(D[4]))                     # the next run goes on from the file
        self.assertEqual(again.outcome, "DONE")
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[3], D[4]])

    def test_a_store_that_says_published_but_did_not_publish_never_gets_the_same_value_twice(self):
        flaky = S.Flaky(self.store(), {1: "uncertain_without_write"}, ("outcome", "PUBLISHED"))
        report = S.run(flaky, self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("STOPPED", "run_publish_uncertain"))
        self.assertEqual(flaky.count("publish"), 1)
        self.assertEqual(len(set(flaky.hashes)), len(flaky.hashes))

    def test_an_unknown_outcome_of_a_store_is_a_program_error_that_passes_through(self):
        flaky = S.Flaky(self.store(), {1: "uncertain_without_write"}, ("outcome", "SOMETHING"))
        with self.assertRaises(AssertionError):
            S.run(flaky, self.w, S.now_at(D[4]))


class OtherWriterBetween(S.RootCase):
    def setUp(self):
        super().setUp()
        S.decide(self.w, range(1, 4))

    def test_a_day_added_by_another_writer_between_the_read_and_the_save_is_stale_and_never_doubled(self):
        def same_day_first(inner):
            history = inner.read()
            inner.publish(U.publish_day(history, D[1], self.w.series, self.w.sessions, self.w.ledger))
        flaky = S.Flaky(self.store(), {1: ("other_writer_first", same_day_first)})
        report = S.run(flaky, self.w, S.now_at(D[3]))
        self.assertEqual((report.outcome, report.exit_code, report.code), ("STOPPED", 1, "publication_stale"))
        self.assertEqual(S.applies_of(self.root), [D[1]])                       # D1 once
        self.assertEqual(report.consumed, ())
        self.assertEqual(flaky.count("publish"), 1)
        self.assertEqual(flaky.count("reconcile"), 0)
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 1))
        again = S.run(self.store(initialize=False), self.w, S.now_at(D[3]))                     # the next run goes on
        self.assertEqual((again.outcome, [c.d for c in again.consumed]), ("DONE", [D[2], D[3]]))

    def test_a_day_of_other_content_added_between_the_read_and_the_save_is_stale_too(self):
        other = P.World(0)
        other.ledger.append(P.obs("R1", D[1], 31.0))

        def rival(inner):
            inner.publish(U.publish_day(inner.read(), D[1], other.series, other.sessions, other.ledger))
        flaky = S.Flaky(self.store(), {1: ("other_writer_first", rival)})
        report = S.run(flaky, self.w, S.now_at(D[3]))
        self.assertEqual((report.outcome, report.code), ("STOPPED", "publication_stale"))
        self.assertEqual(S.applies_of(self.root), [D[1]])


if __name__ == "__main__":
    unittest.main()
