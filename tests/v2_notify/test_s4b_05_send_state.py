"""S4B-10, S4B-11, S4B-12: what the sender's answer means (only "SENT" and "NOT_STARTED" are known, everything else is
UNKNOWN, one call, no retry), an intent without a result (UNKNOWN, not sent again), and every damage of the two files."""
import os
import unittest

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P


class Plain(BaseException):
    pass


class LoudStr(str):
    pass


class Answers(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])

    def run_with(self, answer):
        self.setUp()
        sender = H.Sender([answer])
        report = self.job(H.now_at(D[3]), sender=sender)
        return report, sender

    def test_sent_and_not_started_are_the_only_known_answers(self):
        for answer, status in (("SENT", "SENT"), ("NOT_STARTED", "NOT_SENT")):
            report, sender = self.run_with(answer)
            self.assertEqual((report.delivery, report.send_status), (status, status), answer)
            self.assertEqual(len(sender.texts), 1)
            self.assertEqual(H.jread(self.oroot, D[3] + "-morning.result.json")["status"], status)
            self.assertEqual(report.exit_code, 0 if status == "SENT" else 1)

    def test_every_other_answer_and_every_exception_is_unknown(self):
        others = [None, "OK", "sent", "SENT ", " SENT", "NOT_STARTED\n", "", 1, True, b"SENT", ("SENT",), ["SENT"], 0.5,
                  LoudStr("SENT"), LoudStr("NOT_STARTED"), object()]
        errors = [TimeoutError("t"), OSError("o"), RuntimeError("r"), ValueError("v"), KeyError("k"), ConnectionError("c"),
                  H.CoreError("send_failed", "x"), N.NotifyError("notify_args_invalid"), AssertionError("a"), Plain("p"),
                  GeneratorExit("g"), MemoryError("m")]
        for answer in others + errors:
            report, sender = self.run_with(answer)
            self.assertEqual((report.delivery, report.send_status, report.exit_code), ("UNKNOWN", "UNKNOWN", 1), repr(answer))
            self.assertEqual(len(sender.texts), 1, repr(answer))
            self.assertEqual(H.jread(self.oroot, D[3] + "-morning.result.json")["status"], "UNKNOWN", repr(answer))

    def test_a_keyboard_interrupt_and_a_system_exit_are_not_swallowed_and_leave_an_intent_only(self):
        for error in (KeyboardInterrupt(), SystemExit(3)):
            self.setUp()
            sender = H.RaisingSender(error)
            with self.assertRaises(type(error)):
                self.job(H.now_at(D[3]), sender=sender)
            self.assertEqual(H.names(self.oroot), [D[3] + "-morning.claim.json"])
            self.assertEqual(N.outbox_status(self.outbox(), D[3], "morning")[0].status, "UNKNOWN")
            again = self.job(H.now_at(D[3], 19))
            self.assertEqual((again.delivery, again.existing_status), ("SKIPPED_CLAIMED", "UNKNOWN"))
            self.assertEqual(len(sender.texts), 1)
            self.assertEqual(self.sender.texts, [])

    def test_after_unknown_or_not_sent_a_rerun_never_sends(self):
        for answer in (TimeoutError("t"), "NOT_STARTED", None):
            self.setUp()
            sender = H.Sender(answer)
            first = self.job(H.now_at(D[3]), sender=sender)
            for hour in (19, 20, 21):
                again = self.job(H.now_at(D[3], hour), sender=sender)
                self.assertEqual((again.delivery, again.exit_code, again.send_status), ("SKIPPED_CLAIMED", 1, None))
                self.assertEqual(again.existing_status, "NOT_SENT" if answer == "NOT_STARTED" else "UNKNOWN")
            self.assertEqual(len(sender.texts), 1)
            self.assertEqual(first.exit_code, 1)


class IntentOnly(H.Case):
    def test_an_intent_without_a_result_is_unknown_and_is_not_sent_again(self):
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[3]))
        os.unlink(os.path.join(self.oroot, D[3] + "-morning.result.json"))      # the form after a stop between the two files
        entry = N.outbox_status(self.outbox(), D[3], "morning")[0]
        self.assertEqual((entry.status, entry.recorded_at), ("UNKNOWN", None))
        self.assertRegex(entry.claim_id, r"^[0-9a-f]{32}$")
        before = H.snapshot(self.oroot)
        again = self.job(H.now_at(D[3], 19))
        self.assertEqual((again.delivery, again.existing_status, again.exit_code), ("SKIPPED_CLAIMED", "UNKNOWN", 1))
        self.assertEqual(len(self.sender.texts), 1)
        self.assertEqual(H.snapshot(self.oroot), before)

    def test_the_status_of_a_taken_key_is_read_only(self):
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[3]))
        ops = H.Ops()
        before = H.snapshot(self.oroot)
        entries = N.outbox_status(N.LocalOutbox(self.oroot, _ops=ops), D[3])
        self.assertEqual([(e.kind, e.resend_request_id, e.status) for e in entries],
                         [("morning", None, "SENT"), ("halt", None, "NONE"), ("error", None, "NONE")])
        self.assertEqual(H.snapshot(self.oroot), before)
        self.assertFalse(set(ops.calls) - {"lstat", "read_file", "listdir"})


MUTATIONS = {
    "empty": lambda raw: b"",
    "cut in the middle": lambda raw: raw[:len(raw) // 2],
    "not json": lambda raw: b"not json at all",
    "not utf-8": lambda raw: b"\xff\xfe\x00{}",
    "a list": lambda raw: b"[]",
    "null": lambda raw: b"null",
    "a string": lambda raw: b'"x"',
    "an empty object": lambda raw: b"{}",
    "a bom": lambda raw: b"\xef\xbb\xbf" + raw,
}


class Damage(H.Case):
    def made(self):
        self.setUp()
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[3]))
        self.assertEqual(len(self.sender.texts), 1)
        return D[3] + "-morning.claim.json", D[3] + "-morning.result.json"

    def damaged(self, label):
        entry = N.outbox_status(self.outbox(), D[3], "morning")[0]
        self.assertEqual(entry.status, "DAMAGED", label)
        before = H.snapshot(self.oroot)
        again = self.job(H.now_at(D[3], 19))
        self.assertEqual((again.delivery, again.existing_status, again.exit_code), ("SKIPPED_CLAIMED", "DAMAGED", 1), label)
        self.assertEqual(len(self.sender.texts), 1, label)
        self.assertEqual(H.snapshot(self.oroot), before, label)
        refused = N.resend(self.outbox(), self.sender, D[3], "morning", "r1", H.now_at(D[3], 20))
        self.assertEqual(refused.delivery, "REFUSED_DAMAGED", label)
        self.assertEqual(len(self.sender.texts), 1, label)

    def test_a_file_that_is_not_a_claim_or_a_result_of_the_exact_shape_is_damaged(self):
        for which in (0, 1):
            for label, mutate in MUTATIONS.items():
                claim, result = self.made()
                name = (claim, result)[which]
                H.bwrite(self.oroot, name, mutate(H.bread(self.oroot, name)))
                self.damaged("%s %s" % (name, label))

    def edit(self, name, change):
        data = H.jread(self.oroot, name)
        change(data)
        H.bwrite(self.oroot, name, H.canonical(data))

    def test_a_claim_with_a_missing_wrong_or_extra_field_is_damaged(self):
        keys = ("schema", "kind", "d", "claim_id", "text", "text_sha256", "run_outcome", "code", "claimed_at", "resend_of")
        for key in keys:
            claim, _ = self.made()
            self.edit(claim, lambda data, key=key: data.pop(key))
            self.damaged("missing " + key)
        changes = {
            "other kind": ("kind", "halt"), "other day": ("d", D[2]), "other schema": ("schema", "v2_notify.claim.2"),
            "claim_id not hex": ("claim_id", "xyz"), "claim_id upper": ("claim_id", "A" * 32), "claim_id short": ("claim_id", "a" * 31),
            "claim_id int": ("claim_id", 5), "text int": ("text", 5), "text changed": ("text", "changed"),
            "hash changed": ("text_sha256", "0" * 64), "claimed_at int": ("claimed_at", 5),
            "resend_of set on an original": ("resend_of", "a" * 32), "outcome int": ("run_outcome", 3),
            "code int": ("code", 3), "extra field": ("extra", 1),
        }
        for label, (key, value) in changes.items():
            claim, _ = self.made()
            self.edit(claim, lambda data, key=key, value=value: data.__setitem__(key, value))
            self.damaged(label)

    def test_a_result_with_a_missing_wrong_or_extra_field_is_damaged(self):
        for key in ("claim_id", "status", "recorded_at"):
            _, result = self.made()
            self.edit(result, lambda data, key=key: data.pop(key))
            self.damaged("missing " + key)
        changes = {
            "other claim_id": ("claim_id", "b" * 32), "status DONE": ("status", "DONE"), "status lower": ("status", "sent"),
            "status int": ("status", 5), "status NONE": ("status", "NONE"), "status DAMAGED": ("status", "DAMAGED"),
            "recorded_at int": ("recorded_at", 5), "extra field": ("extra", 1),
        }
        for label, (key, value) in changes.items():
            _, result = self.made()
            self.edit(result, lambda data, key=key, value=value: data.__setitem__(key, value))
            self.damaged(label)

    def test_a_result_without_a_claim_and_a_directory_in_the_place_of_a_file_are_damaged(self):
        claim, result = self.made()
        os.unlink(os.path.join(self.oroot, claim))
        self.damaged("orphan result")
        claim, result = self.made()
        os.unlink(os.path.join(self.oroot, result))
        os.mkdir(os.path.join(self.oroot, result))
        self.damaged("directory as result")
        claim, result = self.made()
        os.unlink(os.path.join(self.oroot, claim))
        os.mkdir(os.path.join(self.oroot, claim))
        self.damaged("directory as claim")

    def test_a_claim_of_another_key_copied_to_the_name_is_damaged(self):
        self.w = P.World(0, unconfirmed=(D[4],))
        S.decide(self.w, [1, 2, 3])
        self.job(H.now_at(D[4]))                                         # a halt claim for D4
        claim, _ = self.made()
        H.bwrite(self.oroot, claim, H.canonical(dict(H.jread(self.oroot, claim), kind="error")))
        self.damaged("kind of another key")

    def test_a_damaged_key_is_listed_without_an_exception(self):
        claim, result = self.made()
        H.bwrite(self.oroot, claim, b"\x00" * 10)
        entries = N.outbox_status(self.outbox(), D[3])
        self.assertEqual([e.status for e in entries], ["DAMAGED", "NONE", "NONE"])
        self.assertIsNone(entries[0].claim_id)


if __name__ == "__main__":
    unittest.main()
