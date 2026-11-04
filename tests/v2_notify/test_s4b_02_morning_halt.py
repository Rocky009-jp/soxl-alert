"""S4B-03, S4B-04, S4B-05: the MORNING notice (one send, an intent and a result), the same morning run again, the HALT
notice and its order with the MORNING notice."""
import json
import unittest

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P

CLAIM_KEYS = {"schema", "kind", "d", "claim_id", "text", "text_sha256", "run_outcome", "code", "claimed_at", "resend_of"}


class Morning(H.Case):
    def test_a_done_morning_sends_once_and_writes_an_intent_and_a_result(self):
        S.decide(self.w, [1, 2, 3])
        now = H.now_at(D[3])
        report = self.job(now)
        self.assertEqual((report.run_outcome, report.kind, report.d, report.delivery, report.exit_code),
                         ("DONE", "morning", D[3], "SENT", 0))
        self.assertEqual((report.key, report.send_status, report.existing_status, report.code),
                         (D[3] + "-morning", "SENT", None, None))
        self.assertEqual(report.report.outcome, "DONE")
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(H.names(self.oroot), [D[3] + "-morning.claim.json", D[3] + "-morning.result.json"])
        text = self.sender.texts[0]
        expected_message = self.reference(now).message                      # the S4-A text of the same inputs
        self.assertEqual(text, "【SOXL日次】対象D=%s\n%s" % (D[3], expected_message))
        raw_claim = H.bread(self.oroot, D[3] + "-morning.claim.json")
        claim = json.loads(raw_claim.decode("utf-8"))
        self.assertEqual(set(claim), CLAIM_KEYS)
        self.assertEqual((claim["schema"], claim["kind"], claim["d"], claim["run_outcome"], claim["code"],
                          claim["resend_of"]), ("v2_notify.claim.1", "morning", D[3], "DONE", None, None))
        self.assertEqual(claim["text"], text)
        self.assertEqual(claim["text_sha256"], H.sha(text))
        self.assertEqual(claim["claimed_at"], now.isoformat())
        self.assertRegex(claim["claim_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(raw_claim, H.canonical(claim))                     # sorted keys, compact, UTF-8 as it is
        raw_result = H.bread(self.oroot, D[3] + "-morning.result.json")
        result = json.loads(raw_result.decode("utf-8"))
        self.assertEqual(result, {"claim_id": claim["claim_id"], "status": "SENT", "recorded_at": now.isoformat()})
        self.assertEqual(raw_result, H.canonical(result))
        self.assertEqual(N.outbox_status(self.outbox(), D[3], "morning")[0].status, "SENT")

    def test_the_morning_of_a_decided_day_is_a_judgment_too(self):
        S.decide(self.w, [1, 2, 3])
        S.decide(self.w, [4])
        report = self.job(H.now_at(D[4]))
        self.assertEqual((report.run_outcome, report.delivery, report.exit_code), ("DONE", "SENT", 0))
        self.assertTrue(self.last_text().startswith("【SOXL日次】対象D=%s\n" % D[4]))

    def test_the_same_morning_again_sends_nothing_and_changes_no_byte(self):
        S.decide(self.w, [1, 2, 3])
        now = H.now_at(D[3])
        self.job(now)
        before = H.snapshot(self.oroot)
        for later in (now, H.now_at(D[3], 19), H.now_at(D[3], 23, 59)):
            again = self.job(later)
            self.assertEqual((again.run_outcome, again.kind, again.d, again.delivery, again.exit_code),
                             ("DONE", "morning", D[3], "SKIPPED_CLAIMED", 0))
            self.assertEqual((again.existing_status, again.send_status), ("SENT", None))
            self.assertEqual(H.snapshot(self.oroot), before)
        self.assertEqual(len(self.sender.texts), 1)

    def test_the_key_does_not_depend_on_the_target_status_of_the_run(self):
        # S4-A review P-04 (a): a rerun of a decided day reports ALREADY_APPLIED where the first run reported PREPARED
        S.decide(self.w, [1, 2, 3, 4])
        first = self.job(H.now_at(D[4]))
        again = self.job(H.now_at(D[4], 19))
        self.assertEqual((first.report.target_status, again.report.target_status), ("PREPARED", "ALREADY_APPLIED"))
        self.assertEqual((first.key, again.key), (D[4] + "-morning", D[4] + "-morning"))
        self.assertEqual((again.delivery, again.exit_code), ("SKIPPED_CLAIMED", 0))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(H.names(self.oroot), [D[4] + "-morning.claim.json", D[4] + "-morning.result.json"])

    def test_a_rerun_after_an_unclear_send_is_skipped_and_is_not_a_success(self):
        S.decide(self.w, [1, 2, 3])
        sender = H.Sender(TimeoutError("late"))
        first = self.job(H.now_at(D[3]), sender=sender)
        again = self.job(H.now_at(D[3], 19), sender=sender)
        self.assertEqual((first.delivery, first.exit_code, first.send_status), ("UNKNOWN", 1, "UNKNOWN"))
        self.assertEqual((again.delivery, again.exit_code, again.existing_status), ("SKIPPED_CLAIMED", 1, "UNKNOWN"))
        self.assertEqual(len(sender.texts), 1)


class Halt(H.Case):
    def setUp(self):
        super().setUp()
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 2, 3])

    def confirm_d4(self):
        self.w.sessions = P.make_sessions()
        S.decide(self.w, [4])

    def test_a_stale_morning_sends_one_halt_notice_with_the_s4a_text(self):
        now = H.now_at(D[4])
        report = self.job(now)
        self.assertEqual((report.run_outcome, report.kind, report.d, report.delivery, report.exit_code, report.code),
                         ("STALE", "halt", D[4], "SENT", 1, "run_session_unconfirmed"))
        self.assertEqual(H.names(self.oroot), [D[4] + "-halt.claim.json", D[4] + "-halt.result.json"])
        ref = self.reference(now)
        self.assertEqual((ref.outcome, ref.code), ("STALE", "run_session_unconfirmed"))
        text = self.last_text()
        self.assertEqual(text.splitlines()[0], "【SOXL日次】対象D=%s ／判定なし" % D[4])
        self.assertTrue(text.endswith(ref.message))
        claim = H.jread(self.oroot, D[4] + "-halt.claim.json")
        self.assertEqual((claim["kind"], claim["run_outcome"], claim["code"]), ("halt", "STALE", "run_session_unconfirmed"))

    def test_the_same_halt_twice_is_sent_once(self):
        self.job(H.now_at(D[4]))
        again = self.job(H.now_at(D[4], 19))
        self.assertEqual((again.delivery, again.existing_status, again.exit_code), ("SKIPPED_CLAIMED", "SENT", 1))
        self.assertEqual(len(self.sender.texts), 1)

    def test_a_judgment_can_follow_a_halt_of_the_same_day(self):
        self.job(H.now_at(D[4]))
        self.confirm_d4()
        report = self.job(H.now_at(D[4], 19))
        self.assertEqual((report.run_outcome, report.kind, report.delivery, report.exit_code), ("DONE", "morning", "SENT", 0))
        self.assertEqual(len(self.sender.texts), 2)
        self.assertEqual(H.names(self.oroot), [D[4] + "-halt.claim.json", D[4] + "-halt.result.json",
                                               D[4] + "-morning.claim.json", D[4] + "-morning.result.json"])
        third = self.job(H.now_at(D[4], 20))
        self.assertEqual(third.delivery, "SKIPPED_CLAIMED")
        self.assertEqual(len(self.sender.texts), 2)

    def stop_with_a_left_over_lock(self):
        H.bwrite(self.hroot, S.LOCK, b"left over")

    def test_a_halt_after_the_judgment_of_the_same_day_is_not_sent(self):
        self.job(H.now_at(D[4]))
        self.confirm_d4()
        self.job(H.now_at(D[4], 19))
        sent = len(self.sender.texts)
        before = H.snapshot(self.oroot)
        self.stop_with_a_left_over_lock()
        report = self.job(H.now_at(D[4], 21))
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery, report.exit_code),
                         ("STOPPED", "store_busy", "halt", "SKIPPED_JUDGMENT_EXISTS", 1))
        self.assertEqual((report.existing_status, report.send_status), ("SENT", None))
        self.assertEqual(len(self.sender.texts), sent)
        self.assertEqual(H.snapshot(self.oroot), before)

    def test_a_halt_after_a_judgment_in_any_state_is_not_sent(self):
        self.confirm_d4()
        late = H.Sender(TimeoutError("late"))
        self.job(H.now_at(D[4]), sender=late)                                      # judgment: UNKNOWN
        self.stop_with_a_left_over_lock()
        report = self.job(H.now_at(D[4], 21))
        self.assertEqual(report.delivery, "SKIPPED_JUDGMENT_EXISTS")
        self.assertEqual((len(late.texts), len(self.sender.texts)), (1, 0))

    def test_a_halt_after_a_damaged_judgment_is_not_sent(self):
        self.confirm_d4()
        self.job(H.now_at(D[4]))
        for damage in (b"", b"{", b"[]", b"\xff\xfe"):
            H.bwrite(self.oroot, D[4] + "-morning.claim.json", damage)
            self.stop_with_a_left_over_lock()
            report = self.job(H.now_at(D[4], 21))
            self.assertEqual((report.kind, report.delivery), ("halt", "SKIPPED_JUDGMENT_EXISTS"), damage)
        self.assertEqual(len(self.sender.texts), 1)
        self.assertNotIn(D[4] + "-halt.claim.json", H.names(self.oroot))

    def test_a_halt_of_another_day_is_not_stopped_by_a_judgment_of_this_day(self):
        self.confirm_d4()
        self.job(H.now_at(D[4]))
        self.w.sessions = P.make_sessions(unconfirmed=(D[5],))
        S.decide(self.w, [5])
        report = self.job(H.now_at(D[5]))
        self.assertEqual((report.kind, report.d, report.delivery), ("halt", D[5], "SENT"))

    def test_a_stopped_run_on_the_boundary_day_sends_a_halt_notice(self):
        report = self.job(H.now_at(D[0]))
        self.assertEqual((report.run_outcome, report.code, report.kind, report.d, report.delivery),
                         ("STOPPED", "target_not_after_boundary", "halt", D[0], "SENT"))


if __name__ == "__main__":
    unittest.main()
