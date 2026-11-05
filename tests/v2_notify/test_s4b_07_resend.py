"""S4B-14: the manual resend (and the read-only status). A resend needs a claim of the original that is UNKNOWN or NOT_SENT
and no SENT or DAMAGED among the original and the earlier resends; the same id is never sent twice; the text is the
original text under one line of notice; the files of the original are not touched."""
import errno
import unittest

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P

LINE = "【再送】元の通知の送信を確認できなかったため、同じ内容を送ります"


class Resend(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])
        self.now = H.now_at(D[3])
        self.late = H.Sender(TimeoutError("late"))
        self.original = self.job(self.now, sender=self.late)               # UNKNOWN
        self.key = D[3] + "-morning"

    def resend(self, rid, sender=None, d=None, kind="morning", outbox=None, hour=22):
        return N.resend(outbox or self.outbox(), sender or self.sender, d or D[3], kind, rid, H.now_at(D[3], hour))

    def test_an_unknown_original_is_sent_again_once_with_one_line_in_front(self):
        self.assertEqual(self.original.delivery, "UNKNOWN")
        original_text = self.late.texts[0]
        before = H.snapshot(self.oroot)
        report = self.resend("req1")
        self.assertEqual((report.delivery, report.send_status, report.original_status, report.exit_code, report.resend_request_id),
                         ("SENT", "SENT", "UNKNOWN", 0, "req1"))
        self.assertEqual(self.sender.texts, [LINE + "\n" + original_text])
        after = H.snapshot(self.oroot)
        for name, data in before.items():
            self.assertEqual(after[name], data, name)                      # the original files are not touched
        self.assertEqual(sorted(set(after) - set(before)), [self.key + ".resend-req1.claim.json", self.key + ".resend-req1.result.json"])
        claim = H.jread(self.oroot, self.key + ".resend-req1.claim.json")
        original = H.jread(self.oroot, self.key + ".claim.json")
        text = LINE + "\n" + original_text
        self.assertEqual((claim["text"], claim["text_sha256"], claim["resend_of"], claim["kind"], claim["d"]),
                         (text, H.sha(text), original["claim_id"], "morning", D[3]))
        self.assertEqual((claim["run_outcome"], claim["code"], claim["claimed_at"]), ("DONE", None, H.now_at(D[3], 22).isoformat()))
        self.assertNotEqual(claim["claim_id"], original["claim_id"])
        result = H.jread(self.oroot, self.key + ".resend-req1.result.json")
        self.assertEqual((result["claim_id"], result["status"]), (claim["claim_id"], "SENT"))

    def test_a_not_sent_original_can_be_sent_again_too(self):
        self.setUp()
        notstarted = H.Sender("NOT_STARTED")
        S.decide(self.w, [4])
        report = self.job(H.now_at(D[4]), sender=notstarted)
        self.assertEqual(report.delivery, "NOT_SENT")
        sent = N.resend(self.outbox(), self.sender, D[4], "morning", "again", H.now_at(D[4], 22))
        self.assertEqual((sent.delivery, sent.original_status), ("SENT", "NOT_SENT"))

    def test_the_same_id_again_is_not_sent(self):
        down = H.Sender(TimeoutError("late"))
        first = self.resend("req1", sender=down)
        self.assertEqual(first.delivery, "UNKNOWN")
        before = H.snapshot(self.oroot)
        for hour in (22, 23):
            again = self.resend("req1", hour=hour)
            self.assertEqual((again.delivery, again.send_status, again.exit_code), ("SKIPPED_CLAIMED", None, 1))
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(H.snapshot(self.oroot), before)

    def test_after_a_resend_that_was_sent_every_other_id_and_the_same_id_are_refused(self):
        self.assertEqual(self.resend("req1").delivery, "SENT")
        for rid in ("req2", "req1", "req3"):
            report = self.resend(rid)
            self.assertEqual((report.delivery, report.exit_code), ("REFUSED_ALREADY_SENT", 1), rid)
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(sorted(n for n in H.names(self.oroot) if "resend" in n),
                         [self.key + ".resend-req1.claim.json", self.key + ".resend-req1.result.json"])

    def test_an_original_that_was_sent_is_refused(self):
        self.setUp()
        S.decide(self.w, [4])
        self.job(H.now_at(D[4]))
        report = N.resend(self.outbox(), self.sender, D[4], "morning", "req1", H.now_at(D[4], 22))
        self.assertEqual((report.delivery, report.original_status), ("REFUSED_ALREADY_SENT", "SENT"))
        self.assertEqual(len(self.sender.texts), 1)

    def test_no_original_a_damaged_original_and_a_damaged_resend_are_refused(self):
        self.assertEqual(self.resend("req1", d=D[2]).delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(self.resend("req1", kind="halt").delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(self.resend("req1", kind="error").delivery, "REFUSED_NO_ORIGINAL")
        self.assertEqual(self.sender.texts, [])
        down = H.Sender(TimeoutError("late"))
        self.assertEqual(self.resend("req1", sender=down).delivery, "UNKNOWN")
        H.bwrite(self.oroot, self.key + ".resend-req1.result.json", b"{")
        for rid in ("req1", "req2"):
            report = self.resend(rid)
            self.assertEqual(report.delivery, "REFUSED_DAMAGED", rid)
        H.bwrite(self.oroot, self.key + ".claim.json", b"")
        self.assertEqual(self.resend("req2").delivery, "REFUSED_DAMAGED")
        self.assertEqual(self.sender.texts, [])

    def test_a_resend_claim_that_is_not_shaped_as_a_resend_is_damaged(self):
        down = H.Sender(TimeoutError("late"))
        self.resend("req1", sender=down)
        name = self.key + ".resend-req1.claim.json"
        data = H.jread(self.oroot, name)
        for resend_of in (None, "zz", 5):
            H.bwrite(self.oroot, name, H.canonical(dict(data, resend_of=resend_of)))
            entries = {(e.kind, e.resend_request_id): e.status for e in N.outbox_status(self.outbox(), D[3])}
            self.assertEqual(entries[("morning", "req1")], "DAMAGED", resend_of)
            self.assertEqual(self.resend("req2").delivery, "REFUSED_DAMAGED")
        self.assertEqual(self.sender.texts, [])

    def test_after_a_resend_that_is_unknown_another_id_can_send(self):
        down = H.Sender(TimeoutError("late"))
        self.assertEqual(self.resend("req1", sender=down).delivery, "UNKNOWN")
        again = self.resend("req2")
        self.assertEqual((again.delivery, again.original_status), ("SENT", "UNKNOWN"))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(self.resend("req3").delivery, "REFUSED_ALREADY_SENT")

    def test_a_resend_of_a_halt_and_of_an_error_uses_the_stored_text(self):
        self.setUp()
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 2, 3])
        down = H.Sender(TimeoutError("late"))
        self.job(H.now_at(D[4]), sender=down)
        sent = N.resend(self.outbox(), self.sender, D[4], "halt", "h1", H.now_at(D[4], 22))
        self.assertEqual(sent.delivery, "SENT")
        self.assertEqual(self.sender.texts, [LINE + "\n" + down.texts[0]])
        self.assertEqual(H.jread(self.oroot, D[4] + "-halt.resend-h1.claim.json")["code"], "run_session_unconfirmed")
        H.Case.setUp(self)
        S.decide(self.w, [1])
        with self.assertRaises(ZeroDivisionError):
            self.job(H.now_at(D[2]), sender=down, series=H.RaisingSeries(ZeroDivisionError("x")))
        sent = N.resend(self.outbox(), self.sender, D[2], "error", "e1", H.now_at(D[2], 22))
        self.assertEqual(sent.delivery, "SENT")

    def test_a_sender_that_fails_in_a_resend_gives_unknown_and_one_call(self):
        for answer in (TimeoutError("t"), None, "OK"):
            self.setUp()
            sender = H.Sender([answer])
            report = self.resend("req1", sender=sender)
            self.assertEqual((report.delivery, report.send_status), ("UNKNOWN", "UNKNOWN"))
            self.assertEqual(len(sender.texts), 1)
        notstarted = H.Sender("NOT_STARTED")
        self.setUp()
        self.assertEqual(self.resend("req1", sender=notstarted).delivery, "NOT_SENT")

    def test_a_resend_whose_claim_cannot_be_created_sends_nothing_and_one_that_cannot_list_says_so(self):
        ops = H.Ops({"create_exclusive": (1, OSError(errno.EIO, "io"))})
        report = self.resend("req1", outbox=self.outbox(ops))
        self.assertEqual((report.delivery, report.send_status), ("CLAIM_FAILED", None))
        self.assertEqual(self.sender.texts, [])
        ops = H.Ops({"listdir": (1, OSError(errno.EIO, "io"))})
        report = self.resend("req1", outbox=self.outbox(ops))
        self.assertEqual((report.delivery, report.original_status), ("CLAIM_FAILED", None))
        self.assertEqual(self.sender.texts, [])
        ops = H.Ops({"create_exclusive": (2, OSError(errno.EIO, "io"))})            # the result of the resend
        report = self.resend("req2", outbox=self.outbox(ops))
        self.assertEqual((report.delivery, report.send_status), ("RESULT_NOT_RECORDED", "SENT"))
        self.assertEqual(N.outbox_status(self.outbox(), D[3], "morning")[1].status, "UNKNOWN")      # req2: a claim only
        self.assertEqual(self.resend("req3").delivery, "SENT")

    def test_a_resend_never_replaces_or_removes_a_file(self):
        ops = H.Ops()
        self.resend("req1", outbox=self.outbox(ops))
        self.assertNotIn("replace", ops.calls)
        self.assertNotIn("unlink", ops.calls)


class Status(H.Case):
    def test_the_status_lists_the_three_keys_and_every_resend_and_changes_nothing(self):
        S.decide(self.w, [1, 2, 3])
        down = H.Sender(TimeoutError("late"))
        self.job(H.now_at(D[3]), sender=down)
        N.resend(self.outbox(), H.Sender(TimeoutError("late")), D[3], "morning", "b-2", H.now_at(D[3], 22))
        N.resend(self.outbox(), self.sender, D[3], "morning", "a-1", H.now_at(D[3], 23))
        before = H.snapshot(self.oroot)
        ops = H.Ops()
        entries = N.outbox_status(N.LocalOutbox(self.oroot, H.MODE, _ops=ops), D[3])
        self.assertEqual([(e.kind, e.resend_request_id, e.status) for e in entries],
                         [("morning", None, "UNKNOWN"), ("morning", "a-1", "SENT"), ("morning", "b-2", "UNKNOWN"),
                          ("halt", None, "NONE"), ("error", None, "NONE")])
        self.assertEqual(entries[0].d, D[3])
        self.assertEqual(entries[1].recorded_at, H.now_at(D[3], 23).isoformat())
        self.assertEqual(entries[0].text_sha256, H.sha(down.texts[0]))
        self.assertEqual(H.snapshot(self.oroot), before)
        self.assertFalse(set(ops.calls) - {"lstat", "probe_dir_sync", "read_file", "listdir"})
        only = N.outbox_status(self.outbox(), D[3], "error")
        self.assertEqual([(e.kind, e.status) for e in only], [("error", "NONE")])

    def test_the_error_key_of_a_call_without_a_target_day_is_read_by_its_utc_date(self):
        now = H.now_at(D[0], 8)
        self.job(now)
        utc = H.utc_date(now)
        entries = N.outbox_status(self.outbox(), utc)
        self.assertEqual([(e.kind, e.status) for e in entries], [("morning", "NONE"), ("halt", "NONE"), ("error", "SENT")])


if __name__ == "__main__":
    unittest.main()
