"""S4A-04 .. S4A-09: the catch-up, a missing day, the same morning again, a decided target, an unconfirmed session and a
time that went back. The store is the real C-3 file store in a temporary root; expected values come from the existing
functions (prepare_history_day -> check_append_batch) and from the independent history builder."""
import dataclasses
import unittest
from datetime import timedelta

import s4a_helpers as S
import v2_daily_run as R
from v2_core.display import render_message

D, P, O, C2 = S.D, S.P, S.O, S.C2


class Normal(S.RootCase):
    def test_every_day_with_a_decision_is_saved_oldest_first_one_publication_each(self):
        S.decide(self.w, range(1, 7))
        rec = S.Recording(self.store())
        seen = []
        original = rec.publish

        def publish(p):
            out = original(p)
            seen.append(S.raw(self.root))
            return out
        rec.publish = publish
        report = S.run(rec, self.w, S.now_at(D[6]))
        self.assertEqual((report.outcome, report.exit_code, report.code), ("DONE", 0, None))
        self.assertEqual([c.d for c in report.consumed], [D[i] for i in range(1, 7)])
        self.assertTrue(all(c.status == "PREPARED" and c.gap is False and c.skipped_sessions == ()
                            for c in report.consumed))
        self.assertEqual(rec.count("publish"), 6)
        self.assertEqual(len(set(rec.hashes)), 6)
        self.assertEqual(rec.count("reconcile"), 0)
        self.assertEqual(rec.count("read"), 1)
        for k, data in enumerate(seen, 1):                             # the bytes after each publication
            self.assertEqual(data, S.expected_bytes(self.w, k), k)
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 6))
        self.assertEqual(S.applies_of(self.root), [D[i] for i in range(1, 7)])
        expected = S.expected_history(self.w, 6)
        self.assertEqual(report.history_digest, expected.digest)
        self.assertEqual(report.target_d, D[6])
        self.assertEqual(report.target_status, "PREPARED")

    def test_the_message_is_the_core_text_of_the_target_when_nothing_is_missing(self):
        S.decide(self.w, range(1, 5))
        report = S.run(self.store(), self.w, S.now_at(D[5]))             # D5 has no decision yet
        self.assertEqual(report.target_status, "NO_COMMIT")
        before_d5 = S.expected_history(self.w, 4)
        day = O.prepare_history_day(before_d5, D[5], self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual(report.message, render_message(day.core_result))


class MissingDay(S.RootCase):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 4])                                    # no decision for D3, none for D5

    def test_a_day_without_a_decision_is_not_saved_and_the_next_saved_day_carries_the_gap(self):
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        self.assertEqual(report.outcome, "DONE")
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2], D[4]])
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[4]])
        self.assertEqual([(c.gap, c.skipped_sessions) for c in report.consumed],
                         [(False, ()), (False, ()), (True, (D[3],))])
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 5))

    def test_the_text_carries_a_line_for_the_gap_with_the_missing_date_and_then_the_core_text(self):
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        core = render_message(O.prepare_history_day(S.expected_history(self.w, 5), D[5], self.w.series,
                                                    self.w.sessions, self.w.ledger).core_result)
        self.assertNotIn(D[3], core)                                   # the core text alone hides the missing day (T-1)
        self.assertTrue(report.message.endswith(core))                 # the core text, whole and unchanged
        head = report.message[:-len(core)]
        self.assertIn(D[3], head)
        self.assertIn(D[4], head)
        self.assertEqual(len([line for line in head.splitlines() if D[3] in line]), 1)
        self.assertNotIn(D[1], head)
        self.assertNotIn(D[2], head)

    def test_a_gap_that_ends_in_the_target_is_listed_too(self):
        self.w.ledger.append(P.obs("R5", D[5], 26.0))
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2], D[4], D[5]])
        self.assertEqual(report.target_status, "PREPARED")
        self.assertEqual([c.gap for c in report.consumed], [False, False, True, False])

    def test_two_gaps_give_two_lines(self):
        w = P.World(0)
        S.decide(w, [1, 3, 5])
        report = S.run(self.store_for(w), w, S.now_at(D[5]))
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in report.consumed],
                         [(D[1], False, ()), (D[3], True, (D[2],)), (D[5], True, (D[4],))])
        lines = [line for line in report.message.splitlines() if D[2] in line or D[4] in line]
        self.assertEqual(len([ln for ln in lines if "消費しました" in ln]), 2)

    def store_for(self, w):
        import shutil
        root = S.make_root()
        self.addCleanup(shutil.rmtree, root, True)
        self.root = root
        return S.real_store(root, w)

    def test_sessions_between_the_start_and_the_first_decision_are_skipped_but_not_a_gap_line(self):
        # the first day after the start: the core's gap is False (design 5.5 follows the core's value, the review
        # proposal P-01 about skipped_sessions is not part of this stage)
        w = P.World(0)
        S.decide(w, [3])
        report = S.run(self.store_for(w), w, S.now_at(D[3]))
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in report.consumed], [(D[3], False, (D[1], D[2]))])
        self.assertNotIn("欠測", report.message)
        self.assertNotIn("消費しました", report.message)


class Rerun(S.RootCase):
    def test_the_same_morning_again_publishes_nothing_and_changes_nothing(self):
        S.decide(self.w, [1, 2])
        store = self.store()
        first = S.run(store, self.w, S.now_at(D[3]))
        self.assertEqual([c.d for c in first.consumed], [D[1], D[2]])
        before = S.state_of(self.root)
        rec = S.Recording(store)
        again = S.run(rec, self.w, S.now_at(D[3]))
        self.assertEqual(rec.count("publish"), 0)
        self.assertEqual(again.consumed, ())
        self.assertEqual(S.state_of(self.root), before)
        self.assertEqual((again.outcome, again.message, again.history_digest, again.target_status),
                         (first.outcome, first.message, first.history_digest, first.target_status))

    def test_after_the_target_was_consumed_a_run_again_is_the_already_applied_text(self):
        S.decide(self.w, range(1, 4))
        store = self.store()
        first = S.run(store, self.w, S.now_at(D[3]))
        self.assertEqual((first.target_status, [c.d for c in first.consumed][-1]), ("PREPARED", D[3]))
        before = S.state_of(self.root)
        rec = S.Recording(store)
        again = S.run(rec, self.w, S.now_at(D[3]))
        self.assertEqual((again.outcome, again.target_status, again.consumed), ("DONE", "ALREADY_APPLIED", ()))
        self.assertEqual(rec.count("publish"), 0)
        self.assertEqual(S.state_of(self.root), before)
        day = O.prepare_history_day(S.expected_history(self.w, 3), D[3], self.w.series, self.w.sessions,
                                    self.w.ledger)
        self.assertEqual(day.status, "ALREADY_APPLIED")
        self.assertEqual(again.message, render_message(day.core_result))
        self.assertEqual(again.message, first.message)
        self.assertEqual(again.history_digest, first.history_digest)

    def test_a_later_morning_continues_from_the_saved_start(self):
        S.decide(self.w, range(1, 4))
        store = self.store()
        S.run(store, self.w, S.now_at(D[3]))
        S.decide(self.w, [4, 5])
        rec = S.Recording(store)
        report = S.run(rec, self.w, S.now_at(D[5]))
        self.assertEqual([c.d for c in report.consumed], [D[4], D[5]])
        self.assertEqual(rec.count("publish"), 2)
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 5))


class DecidedTarget(S.RootCase):
    def test_a_target_whose_decision_was_recorded_before_the_run_is_consumed_and_its_text_is_the_result(self):
        S.decide(self.w, range(1, 4))
        report = S.run(self.store(), self.w, S.now_at(D[3]))
        self.assertEqual(report.target_status, "PREPARED")
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2], D[3]])
        day = O.prepare_history_day(S.expected_history(self.w, 2), D[3], self.w.series, self.w.sessions,
                                    self.w.ledger)
        self.assertEqual(day.status, "PREPARED")
        self.assertEqual(report.message, render_message(day.core_result))
        self.assertIn("decision", report.message)
        self.assertEqual(S.applies_of(self.root)[-1], D[3])


class Unconfirmed(S.RootCase):
    def test_an_unconfirmed_session_in_the_middle_stops_the_run_with_stale_and_keeps_the_days_before(self):
        self.w = P.World(0, unconfirmed=(D[3],))
        S.decide(self.w, [1, 2, 4, 5])
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        self.assertEqual((report.outcome, report.exit_code, report.code, report.detail),
                         ("STALE", 1, "run_session_unconfirmed", D[3]))
        self.assertEqual([c.d for c in report.consumed], [D[1], D[2]])
        self.assertEqual(S.applies_of(self.root), [D[1], D[2]])           # D4 and D5 were not consumed
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 2))
        self.assertIsNone(report.target_status)

    def test_the_text_of_a_stale_run_has_no_judgement_no_branch_table_and_no_b_star(self):
        self.w = P.World(0, unconfirmed=(D[3],))
        S.decide(self.w, [1, 2, 4])
        report = S.run(self.store(), self.w, S.now_at(D[4]))
        text = report.message
        for forbidden in ("b*", "分岐", "市場側", "F&G現在値", "armed", "P20", "購入条件", "EXFEAR", "NORMAL", "TREND"):
            self.assertNotIn(forbidden, text)
        self.assertIn("条件未達ではありません", text)
        self.assertIn("run_session_unconfirmed", text)
        self.assertIn(D[3], text)
        self.assertIn(D[1], text)
        self.assertIn(D[2], text)
        self.assertIn("前日の値や古い日付で補ってもいません", text)

    def test_an_unconfirmed_target_is_stale_too(self):
        self.w = P.World(0, unconfirmed=(D[3],))
        S.decide(self.w, [1, 2])
        report = S.run(self.store(), self.w, S.now_at(D[3]))
        self.assertEqual((report.outcome, report.detail, [c.d for c in report.consumed]),
                         ("STALE", D[3], [D[1], D[2]]))

    def test_an_unconfirmed_session_after_the_target_does_not_matter(self):
        self.w = P.World(0, unconfirmed=(D[6], D[7]))
        S.decide(self.w, [1, 2, 3])
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        self.assertEqual((report.outcome, report.target_d), ("DONE", D[5]))

    def test_a_stale_run_leaves_the_store_so_that_the_next_run_after_the_data_is_confirmed_continues(self):
        S.decide(self.w, [1, 2, 4, 5])
        unconfirmed = P.World(0, unconfirmed=(D[3],))
        unconfirmed.ledger = self.w.ledger
        store = self.store()
        stale = S.run(store, unconfirmed, S.now_at(D[5]))
        self.assertEqual(stale.outcome, "STALE")
        done = S.run(store, self.w, S.now_at(D[5]))
        self.assertEqual((done.outcome, [c.d for c in done.consumed]), ("DONE", [D[4], D[5]]))
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[4], D[5]])
        # the days saved while D3 was unconfirmed keep the context they were saved with, so the bytes are not those of a
        # single run over the confirmed world; the file is a fully valid history and the report names its digest
        self.assertEqual(store.read().digest, done.history_digest)


class TimeWentBack(S.RootCase):
    def test_a_target_before_the_start_stops_the_run_and_writes_nothing(self):
        S.decide(self.w, range(1, 6))
        store = self.store()
        S.run(store, self.w, S.now_at(D[5]))
        before = S.state_of(self.root)
        rec = S.Recording(store)
        report = S.run(rec, self.w, S.now_at(D[3]))
        self.assertEqual((report.outcome, report.exit_code, report.code, report.target_d),
                         ("STOPPED", 1, "run_target_before_head", D[3]))
        self.assertEqual((report.consumed, report.target_status), ((), None))
        self.assertEqual(rec.count("publish"), 0)
        self.assertEqual(S.state_of(self.root), before)
        for forbidden in ("b*", "分岐", "市場側"):
            self.assertNotIn(forbidden, report.message)

    def test_a_target_equal_to_the_start_is_the_already_applied_text(self):
        S.decide(self.w, range(1, 6))
        store = self.store()
        S.run(store, self.w, S.now_at(D[5]))
        report = S.run(store, self.w, S.now_at(D[5]))
        self.assertEqual((report.outcome, report.target_status), ("DONE", "ALREADY_APPLIED"))

    def test_a_target_that_is_the_genesis_boundary_is_stopped_by_the_core_code(self):
        report = S.run(self.store(), self.w, S.now_at(D[0]))
        self.assertEqual((report.outcome, report.code, report.target_d), ("STOPPED", "target_not_after_boundary", D[0]))

    def test_a_session_list_that_changed_the_context_of_a_saved_day_stops_the_run_without_writing(self):
        S.decide(self.w, range(1, 4))
        store = self.store()
        S.run(store, self.w, S.now_at(D[3]))
        before = S.state_of(self.root)

        def shifted(s):
            return dataclasses.replace(s, open_at=s.open_at + timedelta(minutes=1))
        other = P.make_sessions(overrides={D[2]: shifted})
        report = S.run(store, self.w, S.now_at(D[4]), sessions=other)
        self.assertEqual((report.outcome, report.code), ("STOPPED", "session_context_mismatch"))
        self.assertEqual(S.state_of(self.root), before)


if __name__ == "__main__":
    unittest.main()
