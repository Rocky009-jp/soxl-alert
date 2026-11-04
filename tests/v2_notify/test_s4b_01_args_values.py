"""S4B-02: wrong arguments and the values. A wrong argument is a NotifyError (notify_args_invalid or outbox_root_invalid)
that is raised before any file is touched; the values are immutable and their repr never shows a text or a path."""
import os
import tempfile
import unittest
from datetime import datetime

import s4b_helpers as H

N, S, D = H.N, H.S, H.D


class Root(H.Case):
    def code(self, call, *args, **kw):
        with self.assertRaises(N.NotifyError) as ctx:
            call(*args, **kw)
        return ctx.exception.code

    def test_notify_error_is_a_core_error_with_exit_code_1(self):
        self.assertTrue(issubclass(N.NotifyError, H.CoreError))
        self.assertEqual(N.NotifyError("x").exit_code, 1)

    def test_a_root_that_is_not_an_absolute_existing_directory_is_refused_without_touching_anything(self):
        file_path = os.path.join(self.oroot, "a-file")
        H.bwrite(self.oroot, "a-file", b"x")
        bad = ["relative/dir", "", ".", os.path.join(self.oroot, "missing"), file_path, None, 5, b"/tmp", "bad\x00name"]
        try:
            bad.append(os.path.relpath(self.oroot))                   # an existing directory, but named relative to cwd
        except ValueError:
            pass
        for root in bad:
            ops = H.Ops()
            self.assertEqual(self.code(N.LocalOutbox, root, _ops=ops), "outbox_root_invalid", repr(root))
            self.assertFalse([c for c in ops.calls if c not in ("lstat",)], root)
        self.assertEqual(H.names(self.oroot), ["a-file"])

    def test_a_link_is_refused(self):
        link = os.path.join(tempfile.mkdtemp(prefix="v2s4b_link_"), "link")
        self.addCleanup(lambda: os.path.islink(link) and os.unlink(link))
        try:
            os.symlink(self.oroot, link)
        except (OSError, NotImplementedError):
            self.skipTest("no symbolic link here")
        self.assertEqual(self.code(N.LocalOutbox, link), "outbox_root_invalid")

    def test_a_good_root_is_accepted_and_nothing_is_created_by_the_constructor(self):
        ops = H.Ops()
        N.LocalOutbox(self.oroot, _ops=ops)
        self.assertEqual(ops.calls, ["lstat"])
        self.assertEqual(H.names(self.oroot), [])


class Arguments(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])

    def test_a_now_without_a_time_zone_is_refused_everywhere_and_nothing_is_touched(self):
        naive = datetime(2026, 3, 5, 18, 0)
        silent = S.Silent()
        for call in (lambda: N.morning_job(silent, self.outbox(), self.sender, naive, self.w.series, self.w.sessions, []),
                     lambda: N.resend(self.outbox(), self.sender, D[2], "morning", "r1", naive),
                     lambda: N.compose_notice(self.reference(H.now_at(D[2])), self.w.sessions, naive)):
            with self.assertRaises(N.NotifyError) as ctx:
                call()
            self.assertEqual((ctx.exception.code, ctx.exception.field), ("notify_args_invalid", "now"))
        for not_a_time in (None, "2026-03-05", 5, H.now_at(D[2]).date()):
            with self.assertRaises(N.NotifyError):
                N.morning_job(silent, self.outbox(), self.sender, not_a_time, self.w.series, self.w.sessions, [])
        self.assertEqual(silent.calls, [])
        self.assertEqual(self.sender.texts, [])
        self.assertEqual(H.names(self.oroot), [])

    def test_the_outbox_and_the_sender_must_be_what_they_say(self):
        silent, now = S.Silent(), H.now_at(D[2])
        for outbox, sender in ((object(), self.sender), (self.oroot, self.sender), (self.outbox(), object()),
                               (self.outbox(), None), (self.outbox(), "send")):
            with self.assertRaises(N.NotifyError) as ctx:
                N.morning_job(silent, outbox, sender, now, self.w.series, self.w.sessions, [])
            self.assertEqual(ctx.exception.code, "notify_args_invalid")
        self.assertEqual(silent.calls, [])

    def test_a_bad_resend_request_id_d_or_kind_is_refused_before_any_file_is_read(self):
        before = H.snapshot(self.oroot)
        too_long = "a" * 65
        for rid in ("", " ", "a b", "../x", "a.b", "ä", too_long, None, 5, b"x", "a\n"):
            ops = H.Ops()
            with self.assertRaises(N.NotifyError) as ctx:
                N.resend(N.LocalOutbox(self.oroot, _ops=ops), self.sender, D[2], "morning", rid, H.now_at(D[2]))
            self.assertEqual(ctx.exception.code, "notify_args_invalid", repr(rid))
            self.assertEqual(ops.calls, ["lstat"], repr(rid))              # only the constructor looked at the root
        for d in ("2026-3-5", "x", None, "2026-03-05\n", "２０２６-03-05"):
            with self.assertRaises(N.NotifyError):
                N.resend(self.outbox(), self.sender, d, "morning", "r1", H.now_at(D[2]))
            with self.assertRaises(N.NotifyError):
                N.outbox_status(self.outbox(), d)
        for kind in ("MORNING", "other", None):
            with self.assertRaises(N.NotifyError):
                N.resend(self.outbox(), self.sender, D[2], kind, "r1", H.now_at(D[2]))
        self.assertEqual(H.snapshot(self.oroot), before)
        self.assertEqual(self.sender.texts, [])

    def test_a_good_resend_request_id_set_of_characters_is_accepted_by_the_check(self):
        for rid in ("a", "A-z_0-9", "x" * 64):
            report = N.resend(self.outbox(), self.sender, D[2], "morning", rid, H.now_at(D[2]))
            self.assertEqual(report.delivery, "REFUSED_NO_ORIGINAL")        # valid id; there is no original


class Values(H.Case):
    def test_the_values_are_immutable_and_their_repr_shows_no_text_and_no_path(self):
        S.decide(self.w, [1, 2, 3])
        report = self.job(H.now_at(D[3]))
        text = self.sender.texts[0]
        notice = N.compose_notice(self.reference(H.now_at(D[3])), self.w.sessions, H.now_at(D[3]))
        entry = N.outbox_status(self.outbox(), D[3])[0]
        resend_report = N.resend(self.outbox(), self.sender, D[3], "morning", "r1", H.now_at(D[3]))
        for value, field in ((notice, "text"), (report, "delivery"), (resend_report, "delivery"), (entry, "status")):
            with self.assertRaises(AttributeError):
                setattr(value, field, "x")
            with self.assertRaises(AttributeError):
                delattr(value, field)
            self.assertNotIn(self.oroot, repr(value))
            self.assertNotIn(self.hroot, repr(value))
        self.assertNotIn(text.splitlines()[1], repr(notice))
        self.assertNotIn(text.splitlines()[1], repr(report))
        self.assertNotIn("tmp", repr(self.outbox()))
        self.assertEqual(notice, N.compose_notice(self.reference(H.now_at(D[3])), self.w.sessions, H.now_at(D[3])))
        self.assertEqual(hash(notice), hash(N.compose_notice(self.reference(H.now_at(D[3])), self.w.sessions,
                                                             H.now_at(D[3]))))

    def test_a_notice_checks_its_own_parts(self):
        for args in (("x", D[1], "t"), ("morning", "bad", "t"), ("morning", D[1], ""), ("morning", D[1], None)):
            with self.assertRaises(ValueError):
                N.Notice(*args)
        self.assertEqual(N.Notice("halt", D[1], "t").key, D[1] + "-halt")

    def test_the_report_values_reject_unknown_words(self):
        with self.assertRaises(ValueError):
            N.JobReport("DONE", "morning", D[1], "NOPE", None, None, None, None)
        with self.assertRaises(ValueError):
            N.ResendReport("morning", D[1], "r", "NOPE", None, None)


if __name__ == "__main__":
    unittest.main()
