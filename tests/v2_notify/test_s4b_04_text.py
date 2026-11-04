"""S4B-07, S4B-08, S4B-09: the lines about sessions without a record, the four notes and the body. Expected facts come
from the S4-A report of the same inputs (the consumed days and their skipped sessions) and from literals."""
import unittest

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P

MISSING_HEAD = "【F&Gの記録の欠け】"
S4A_GAP_HEAD = "【今回の追いつきで見つかった欠測】"


def missing_line(day, skipped):
    return "  %s の前に、F&Gの記録が無いセッションがありました: %s" % (day, "、".join(skipped))


class MissingRecords(H.Case):
    def test_a_halt_names_the_missing_days_that_the_s4a_text_does_not(self):
        # S4-A review X1: D1 and D3 are saved, D2 has no record, D4 is unconfirmed -> the S4-A text of the halt names no gap
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 3])
        now = H.now_at(D[4])
        ref = self.reference(now)
        self.assertEqual(ref.outcome, "STALE")
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in ref.consumed], [(D[1], False, ()), (D[3], True, (D[2],))])
        self.assertNotIn(D[2], ref.message)
        self.job(now)
        lines = self.last_text().splitlines()
        self.assertEqual(lines[:3], ["【SOXL日次】対象D=%s ／判定なし" % D[4], MISSING_HEAD, missing_line(D[3], [D[2]])])
        self.assertEqual(self.last_text().count(MISSING_HEAD), 1)

    def test_a_halt_also_names_the_missing_days_of_a_day_whose_gap_is_false(self):
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [2, 3])                    # the first save after the genesis: D1 has no record, gap is false
        now = H.now_at(D[4])
        ref = self.reference(now)
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in ref.consumed],
                         [(D[2], False, (D[1],)), (D[3], False, ())])
        self.job(now)
        self.assertIn(missing_line(D[2], [D[1]]), self.last_text().splitlines())

    def test_a_morning_names_the_first_save_after_the_genesis_although_its_gap_is_false(self):
        S.decide(self.w, [2])
        now = H.now_at(D[3])
        ref = self.reference(now)
        self.assertEqual(ref.outcome, "DONE")
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in ref.consumed], [(D[2], False, (D[1],))])
        self.assertNotIn(S4A_GAP_HEAD, ref.message)                    # the S4-A text writes gap=true days only
        self.job(now)
        lines = self.last_text().splitlines()
        self.assertEqual(lines[:3], ["【SOXL日次】対象D=%s" % D[3], MISSING_HEAD, missing_line(D[2], [D[1]])])
        self.assertTrue(self.last_text().endswith(ref.message))

    def test_a_morning_does_not_repeat_a_day_that_the_s4a_text_names(self):
        S.decide(self.w, [1, 3])
        now = H.now_at(D[3])
        ref = self.reference(now)
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in ref.consumed], [(D[1], False, ()), (D[3], True, (D[2],))])
        self.assertEqual(ref.message.count(S4A_GAP_HEAD), 1)
        self.job(now)
        text = self.last_text()
        self.assertNotIn(MISSING_HEAD, text)
        self.assertEqual(text.count(D[2]), ref.message.count(D[2]))     # D2 is named as often as the S4-A text names it

    def test_a_morning_with_both_kinds_names_each_day_once(self):
        S.decide(self.w, [2, 4])                    # D2: first save, D1 skipped, gap false; D4: D3 skipped, gap true
        now = H.now_at(D[4])
        ref = self.reference(now)
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in ref.consumed],
                         [(D[2], False, (D[1],)), (D[4], True, (D[3],))])
        self.job(now)
        text = self.last_text()
        self.assertEqual(text.count(missing_line(D[2], [D[1]])), 1)
        self.assertNotIn(missing_line(D[4], [D[3]]), text)
        self.assertEqual(text.count(S4A_GAP_HEAD), 1)
        self.assertEqual(text.count(MISSING_HEAD), 1)
        self.assertLess(text.index(MISSING_HEAD), text.index(S4A_GAP_HEAD))

    def test_several_skipped_sessions_are_listed_in_order(self):
        S.decide(self.w, [4])
        self.job(H.now_at(D[4]))
        self.assertIn(missing_line(D[4], [D[1], D[2], D[3]]), self.last_text().splitlines())

    def test_no_line_when_nothing_was_skipped(self):
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[3]))
        self.assertNotIn(MISSING_HEAD, self.last_text())


class Notes(H.Case):
    AFTER_OPEN = "※この実行は対象Dの次の寄付き（%s）の後です。下の分岐表の寄付きは過ぎています。"
    UNSURE = "※最後の日の保存は確認できていません。"
    BOUNDARY = "※対象Dは記録の開始境界の日です。次のセッションから処理します。異常ではありません。"
    CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"
    ALL = ("※この実行は対象Dの次の寄付き", "※最後の日の保存は確認できていません", "※対象Dは記録の開始境界の日です",
           "※別の実行が同時に動いていた可能性があります")

    def only(self, text, expected=()):
        for note in self.ALL:
            if any(e.startswith(note) for e in expected):
                continue
            self.assertNotIn(note, text)

    def test_the_note_of_the_passed_open_is_in_from_the_open_itself_and_not_one_microsecond_before(self):
        S.decide(self.w, [1, 2])
        open_at = self.w.sessions.next(D[3]).open_at
        from datetime import timedelta
        self.job(open_at - timedelta(microseconds=1))
        self.only(self.last_text())
        self.setUp()
        S.decide(self.w, [1, 2])
        self.job(open_at)
        self.assertIn(self.AFTER_OPEN % open_at.isoformat(), self.last_text().splitlines())
        self.only(self.last_text(), [self.AFTER_OPEN])
        self.setUp()
        S.decide(self.w, [1, 2])
        self.job(open_at + timedelta(hours=3))
        self.assertIn(self.AFTER_OPEN % open_at.isoformat(), self.last_text())

    def test_no_note_of_the_passed_open_when_the_target_has_its_decision_or_is_the_last_session(self):
        from datetime import timedelta
        S.decide(self.w, [1, 2, 3])
        open_at = self.w.sessions.next(D[3]).open_at
        self.job(open_at + timedelta(hours=1))
        self.only(self.last_text())
        self.setUp()
        last = self.w.sessions.sessions[-1].date
        self.assertIsNone(self.w.sessions.next(last))
        S.decide(self.w, range(1, 40))
        self.job(H.now_at(last))
        self.only(self.last_text())

    def test_the_note_of_the_unsure_save_is_in_a_halt_of_the_two_codes_only(self):
        S.decide(self.w, [1, 2, 3, 4])
        flaky = S.Flaky(self.store(), {1: "uncertain_after_write", 3: "uncertain_after_write"})
        report = self.job(H.now_at(D[4]), store=flaky)
        self.assertEqual((report.run_outcome, report.code), ("STOPPED", "run_publish_uncertain"))
        self.assertIn(self.UNSURE, self.last_text().splitlines())
        self.only(self.last_text(), [self.UNSURE])
        self.setUp()
        S.decide(self.w, [1, 2, 3, 4])
        flaky = S.Flaky(self.store(), {2: "uncertain_without_write"}, ("outcome", "CONFLICT"))
        report = self.job(H.now_at(D[4]), store=flaky)
        self.assertEqual((report.run_outcome, report.code), ("STOPPED", "run_publish_conflict"))
        self.assertIn(self.UNSURE, self.last_text().splitlines())
        self.setUp()
        S.decide(self.w, [1, 2, 3, 4])
        flaky = S.Flaky(self.store(), {1: "uncertain_without_write"}, ("outcome", "NOT_PUBLISHED"))
        report = self.job(H.now_at(D[4]), store=flaky)
        self.assertEqual(report.code, "run_publish_not_published")        # a save known not to have happened
        self.only(self.last_text())

    def test_the_note_of_the_boundary_day(self):
        report = self.job(H.now_at(D[0]))
        self.assertEqual(report.code, "target_not_after_boundary")
        self.assertIn(self.BOUNDARY, self.last_text().splitlines())
        self.only(self.last_text(), [self.BOUNDARY])

    def test_the_note_of_a_run_at_the_same_time_for_the_two_codes(self):
        S.decide(self.w, [1, 2, 3])
        self.store()
        H.bwrite(self.hroot, S.LOCK, b"left over")
        report = self.job(H.now_at(D[3]))
        self.assertEqual(report.code, "store_busy")
        self.assertIn(self.CONCURRENT, self.last_text().splitlines())
        self.only(self.last_text(), [self.CONCURRENT])
        self.setUp()
        S.decide(self.w, [1, 2, 3])
        rival = P.World(0)
        rival.ledger.append(P.obs("R1", D[1], 31.0))
        import v2_history_publish as U

        def other_content_first(inner):
            inner.publish(U.publish_day(inner.read(), D[1], rival.series, rival.sessions, rival.ledger))
        flaky = S.Flaky(self.store(), {1: ("other_writer_first", other_content_first)})
        report = self.job(H.now_at(D[3]), store=flaky)
        self.assertEqual(report.code, "publication_stale")
        self.assertIn(self.CONCURRENT, self.last_text().splitlines())
        self.only(self.last_text(), [self.CONCURRENT])

    def test_a_stale_halt_has_none_of_the_four_notes(self):
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[4]))
        self.only(self.last_text())


class Body(H.Case):
    def test_the_s4a_text_is_inside_the_notice_unchanged_for_the_morning_and_the_halt(self):
        S.decide(self.w, [1, 2, 3])
        ref = self.reference(H.now_at(D[3]))
        self.job(H.now_at(D[3]))
        self.assertIn(ref.message, self.last_text())
        self.assertEqual(self.last_text().count(ref.message), 1)
        self.setUp()
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 2, 3])
        ref = self.reference(H.now_at(D[4]))
        self.job(H.now_at(D[4]))
        self.assertIn(ref.message, self.last_text())

    def test_the_text_made_by_the_compose_function_equals_the_text_that_was_sent_and_stored(self):
        S.decide(self.w, [1, 2, 3])
        now = H.now_at(D[3])
        notice = N.compose_notice(self.reference(now), self.w.sessions, now)
        self.job(now)
        self.assertEqual(notice.text, self.last_text())
        self.assertEqual(notice.text_sha256, H.sha(self.last_text()))
        self.assertEqual((notice.kind, notice.d, notice.run_outcome, notice.code), ("morning", D[3], "DONE", None))

    def test_the_error_notice_has_no_s4a_text(self):
        S.decide(self.w, [1])
        ref = self.reference(H.now_at(D[2]))
        with self.assertRaises(ZeroDivisionError):
            self.job(H.now_at(D[2]), series=H.RaisingSeries(ZeroDivisionError("x")))
        self.assertNotIn(ref.message.splitlines()[0], self.last_text())
        self.assertEqual(len(self.last_text().splitlines()), 3)

    def test_compose_checks_its_arguments(self):
        S.decide(self.w, [1, 2, 3])
        ref = self.reference(H.now_at(D[3]))
        for args in ((None, self.w.sessions, H.now_at(D[3])), (ref, [], H.now_at(D[3])), (ref, self.w.sessions, None)):
            with self.assertRaises(N.NotifyError):
                N.compose_notice(*args)
        for args in (("bad", "unexpected_error"), (D[1], "Bad Code"), (D[1], None)):
            with self.assertRaises(N.NotifyError):
                N.compose_error_notice(*args)


if __name__ == "__main__":
    unittest.main()
