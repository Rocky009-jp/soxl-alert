"""S4E-02 (arguments): the public names and constants of v2_run, and a wrong argument ends with a non-zero code before git, the
network, a temporary directory or the clock is touched; no value of an argument is shown."""
import unittest
from unittest import mock

import s4e_helpers as H

R = H.R


class PublicNames(unittest.TestCase):
    def test_the_names_and_the_constants_of_the_design(self):
        for name in ("main", "Setup", "MODES", "make_fetch", "DiscordSender", "DrySender", "split_text", "live_text"):
            self.assertTrue(hasattr(R, name), name)
        self.assertEqual(R.USER_AGENT, "Mozilla/5.0 (compatible; soxl-alert-v2)")
        self.assertEqual((R.FETCH_TIMEOUT, R.SEND_TIMEOUT, R.MAX_BYTES, R.LIMIT), (30, 20, 8 * 1024 * 1024, 1900))
        self.assertEqual(R.PREVIEW_HEAD, "【SOXL日次・ローカルプレビュー（実送信なし）】")
        self.assertEqual(R.LIVE_HEAD, "【詳細】")
        self.assertEqual(R.WEBHOOK_PREFIXES, ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/"))
        self.assertEqual(R.SECRET_NAME, "V2_DISCORD_WEBHOOK_URL")
        self.assertEqual(R.REFUSED_JUDGMENT_EXISTS, "REFUSED_JUDGMENT_EXISTS")
        self.assertEqual(R.MODES["dry"], {"state": "v2-dry-state", "outbox": "v2-dry-outbox", "market": "v2-dry-market",
                                          "ledger": "v2-ledger"})
        self.assertEqual(R.MODES["live"], {"state": "v2-state", "outbox": "v2-outbox", "market": "v2-market",
                                           "ledger": "v2-ledger"})
        self.assertEqual(sorted(R.MODES), ["dry", "live"])

    def test_the_preview_heading_is_the_one_of_the_accepted_core(self):
        text = H.read_source("v2_core/display.py") + H.read_source("v2_daily_run/run.py")
        self.assertIn(R.PREVIEW_HEAD, text)

    def test_the_package_has_the_five_files_of_the_design(self):
        import os
        names = sorted(n for n in os.listdir(os.path.dirname(R.__file__)) if n.endswith(".py"))
        self.assertEqual(names, ["__init__.py", "__main__.py", "check.py", "entry.py", "web.py"])


class WrongArguments(H.D.Case):
    BAD = [
        ("no command", []),
        ("unknown command", ["deploy", "--mode", "dry", "--workdir", "/x"]),
        ("no mode", ["morning", "--workdir", "/x"]),
        ("unknown mode", ["morning", "--mode", "prod", "--workdir", "/x"]),
        ("empty mode", ["morning", "--mode", "", "--workdir", "/x"]),
        ("no workdir", ["morning", "--mode", "dry"]),
        ("empty workdir", ["morning", "--mode", "dry", "--workdir", ""]),
        ("status without a date", ["status", "--mode", "dry", "--workdir", "/x"]),
        ("status with an impossible date", ["status", "--mode", "dry", "--workdir", "/x", "--date", "2026-02-30"]),
        ("status with a short date", ["status", "--mode", "dry", "--workdir", "/x", "--date", "2026-7-1"]),
        ("status with a date and a tail", ["status", "--mode", "dry", "--workdir", "/x", "--date", "2026-07-01x"]),
        ("resend without a kind", ["resend", "--mode", "live", "--workdir", "/x", "--date", "2026-07-01", "--request-id", "r1"]),
        ("resend with an unknown kind", ["resend", "--mode", "live", "--workdir", "/x", "--date", "2026-07-01", "--kind",
                                         "resume", "--request-id", "r1"]),
        ("resend without an id", ["resend", "--mode", "live", "--workdir", "/x", "--date", "2026-07-01", "--kind", "morning"]),
        ("resend without a date", ["resend", "--mode", "live", "--workdir", "/x", "--kind", "morning", "--request-id", "r1"]),
        ("init without a start", ["init", "--mode", "dry", "--workdir", "/x"]),
        ("init with an impossible start", ["init", "--mode", "dry", "--workdir", "/x", "--start-after", "2026-13-01"]),
        ("an option that does not exist", ["morning", "--mode", "dry", "--workdir", "/x", "--force", "1"]),
        ("an abbreviated option", ["morning", "--mod", "dry", "--workdir", "/x"]),
        ("a second command", ["morning", "status", "--mode", "dry", "--workdir", "/x"]),
    ]

    def test_each_wrong_argument_ends_with_2_and_touches_nothing(self):
        for name, argv in self.BAD:
            lines, calls = [], []

            def forbidden(*a, **k):
                calls.append(1)
                raise AssertionError("touched")
            clock = H.Clock(H.aware("2026-07-21"))
            with mock.patch.object(H.ENTRY, "Git", forbidden), mock.patch.object(H.ENTRY.tempfile, "mkdtemp", forbidden):
                code = R.main(argv, env={}, out=lines.append, now_fn=clock, urlopen=forbidden)
            self.assertEqual(code, 2, name)
            self.assertEqual((calls, clock.calls), ([], 0), name)
            self.assertEqual(len(lines), 1)
            self.assertIn("refused: arguments_invalid", lines[0])
            self.assertIn("exit_code: 2", lines[0])

    def test_the_value_of_an_argument_is_never_shown(self):
        argv = ["status", "--mode", "dry", "--workdir", "/" + H.MARK + "dir", "--date", "x" + H.TOKEN_MARK]
        lines = []
        code = R.main(argv, env={}, out=lines.append, now_fn=H.Clock(H.aware("2026-07-21")), urlopen=lambda *a, **k: None)
        self.assertEqual(code, 2)
        self.assertEqual(H.leaks("\n".join(lines)), [])
        self.assertNotIn("x" + H.TOKEN_MARK, "\n".join(lines))

    def test_the_summary_file_is_written_for_a_wrong_argument_too(self):
        work = H.Work(self)
        result = work.run(H.Net(), ["morning", "--mode", ""], H.aware("2026-07-21"), workdir=work.dir)
        self.assertEqual(result.code, 2)
        self.assertIn("arguments_invalid (mode)", result.summary)

    def test_the_real_urlopen_is_replaced_in_the_tests(self):
        import urllib.request
        with self.assertRaises(AssertionError):
            urllib.request.urlopen("https://example.invalid/")


class CodeVersion(H.D.Case):
    def test_only_a_lowercase_hex_of_40_digits_is_recorded(self):
        work = H.Work(self)
        net = H.Net()
        self.assertEqual(work.init(net, "dry").code, 0)
        for value, want in (("a" * 40, "a" * 40), ("0123456789abcdef0123456789abcdef01234567", "0123456789abcdef0123456789abcdef01234567"),
                            ("A" * 40, "unknown"), ("a" * 39, "unknown"), ("a" * 41, "unknown"), ("g" * 40, "unknown"),
                            ("", "unknown")):
            lines = []
            code = R.main(["status", "--mode", "dry", "--workdir", work.dir, "--date", "2026-07-21", "--code-version", value],
                          env={}, out=lines.append, now_fn=H.Clock(H.aware("2026-07-21")), urlopen=net)
            self.assertEqual(code, 0, value)
            self.assertIn("- code_version: %s\n" % want, "\n".join(lines) + "\n", value)
        self.assertEqual(net.requests, [])
        # a status of a store that was never initialized cannot be read: 1, not 0
        lines = []
        empty = H.Work(self)
        code = R.main(["status", "--mode", "dry", "--workdir", empty.dir, "--date", "2026-07-21"], env={}, out=lines.append,
                      now_fn=H.Clock(H.aware("2026-07-21")), urlopen=net)
        self.assertEqual(code, 1)
        self.assertIn("failed: NotifyError（outbox_io_error）", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
