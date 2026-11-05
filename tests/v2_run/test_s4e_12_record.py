"""S4E-15: the record of a run (standard output and the Actions summary file) never holds a path, a URL, a secret, the text of an
exception, the output of git or a response body; an exception is a type name and a fixed code; it holds the versions of Python
and git and the code version; the summary file is appended to; the environment is read only for the two names; a dry run never
reads the secret."""
import os
import sys
import unittest
from unittest import mock

import s4e_helpers as H

R, ENTRY = H.R, H.ENTRY
DAY, START = "2026-07-28", "2026-07-27"


class SpyEnv(dict):
    """An environment that remembers every name that was asked for."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.asked = []

    def get(self, key, default=None):
        self.asked.append(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.asked.append(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        self.asked.append(key)
        return super().__contains__(key)

    def __iter__(self):
        self.asked.append("<iter>")
        return super().__iter__()

    def items(self):
        self.asked.append("<items>")
        return super().items()

    def keys(self):
        self.asked.append("<keys>")
        return super().keys()

    def values(self):
        self.asked.append("<values>")
        return super().values()


class EveryScene(H.D.Case):
    def scenes(self):
        """Results of runs of every command in situations that tempt an implementation to show a path, a URL or a text."""
        out = []
        work, net = H.Work(self), H.Net(DAY)
        out.append(work.init(net, "dry", start=START))
        out.append(work.init(net, "live", start=START))
        out.append(work.morning(net, "dry", DAY, start=START))
        out.append(work.morning(net, "dry", DAY, hhmm="08:40", start=START))
        out.append(work.cmd(net, "status", "dry", DAY, extra=["--date", DAY]))
        out.append(work.cmd(net, "check-source", "dry", DAY))
        out.append(work.morning(net, "live", DAY, start=START))
        out.append(work.cmd(net, "resend", "live", DAY, "09:00", ["--date", DAY, "--kind", "halt", "--request-id", "r1"],
                            env={R.SECRET_NAME: H.WEBHOOK}))
        out.append(work.cmd(net, "resend", "live", DAY, "09:00", ["--date", DAY, "--kind", "morning", "--request-id", "r1"],
                            env={R.SECRET_NAME: H.WEBHOOK}))
        for behaviour in ("400", "500", "refused", "dns", "timeout", "url_timeout", "other"):
            w, n = H.Work(self), H.Net(DAY)
            w.init(n, "live", start=START)
            n.discord = [behaviour]
            out.append(w.morning(n, "live", DAY, start=START))
        for symbol, error in (("SOXX", H.http_error(H.CHART_BASE + "SOXX", 500)), ("SPY", OSError("network " + H.MARK + H.TOKEN_MARK)),
                              ("IEF", ("status", 503)), ("SOXL", ("size", R.MAX_BYTES + 5)),
                              ("SPY", b"not json " + H.MARK.encode() + H.TOKEN_MARK.encode())):
            w, n = H.Work(self), H.Net(DAY)
            w.init(n, "dry", start=START)
            n.override[symbol] = error
            out.append(w.morning(n, "dry", DAY, start=START))
            out.append(w.cmd(n, "check-source", "dry", DAY))
        out.append(work.run(net, ["morning", "--mode", "dry"], H.aware(DAY), workdir=os.path.join(work.dir, "no", H.MARK)))
        out.append(work.run(net, ["status", "--mode", "live", "--date", H.MARK], H.aware(DAY)))
        return out

    def test_no_scene_shows_a_mark_a_url_or_an_exception_text(self):
        results = self.scenes()
        self.assertGreaterEqual(len(results), 28)
        for result in results:
            self.assertEqual(H.leaks(result.text), [], result.text)
            self.assertEqual(result.summary, result.text + "\n")                       # the summary file has the same record
            self.assertTrue(result.text.startswith("### v2_run"))
            self.assertTrue(result.text.rstrip().endswith("exit_code: %d" % result.code))
        self.assertEqual(sorted({r.code for r in results}), [0, 1, 2])

    def test_every_record_names_the_versions(self):
        for result in self.scenes()[:6]:
            if result.code == 2:
                continue
            self.assertIn("python", result.kv)
            self.assertEqual(result.kv["python"], "%d.%d.%d" % sys.version_info[:3])
            self.assertEqual(result.kv["git"], H.git_version())
            self.assertEqual(result.kv["code_version"], H.CODE)
            self.assertIn("now_utc", result.kv)


class Exceptions(H.D.Case):
    def test_an_unexpected_error_is_its_type_name_only(self):
        work, net = H.Work(self), H.Net(DAY)
        work.init(net, "dry", start=START)
        work.sync_ledger(START, DAY)

        def boom(*a, **k):
            raise RuntimeError("SECRETMARK_ path /x/y and https://secret.example/" + H.TOKEN_MARK)
        with mock.patch.object(ENTRY, "morning_job", boom):
            result = work.cmd(net, "morning", "dry", DAY)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.kv["failed"], "RuntimeError")
        self.assertEqual(H.leaks(result.text), [])
        self.assertEqual(H.leaks(result.summary), [])
        self.assertNotIn("/x/y", result.text)

    def test_a_core_error_is_its_type_and_its_fixed_code(self):
        work = H.Work(self)
        result = work.run(H.Net(), ["status", "--mode", "dry", "--date", DAY], H.aware(DAY))
        self.assertEqual(result.kv["failed"], "NotifyError（outbox_io_error）")
        result = work.run(H.Net(), ["status", "--mode", "dry", "--date", DAY], H.aware(DAY),
                          workdir=os.path.join(work.dir, H.MARK))
        self.assertEqual(result.kv["failed"], "GitError（git_args_invalid）")
        self.assertEqual(H.leaks(result.text), [])

    def test_an_error_whose_code_is_not_a_text_shows_the_type_only(self):
        error = type("Odd", (Exception,), {})("x")
        error.code = 500
        self.assertEqual(ENTRY.why(error), "Odd")
        error.code = "fixed_code"
        self.assertEqual(ENTRY.why(error), "Odd（fixed_code）")


class SummaryFile(H.D.Case):
    def test_the_summary_is_appended_and_the_earlier_content_stays(self):
        work, net = H.Work(self), H.Net(DAY)
        path = os.path.join(work.summary_dir, "shared_summary.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("EARLIER STEP\n")
        first = work.run(net, ["init", "--mode", "dry", "--start-after", START], H.aware(START), env={"GITHUB_STEP_SUMMARY": path})
        second = work.run(net, ["status", "--mode", "dry", "--date", DAY], H.aware(DAY), env={"GITHUB_STEP_SUMMARY": path})
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "EARLIER STEP\n" + first.text + "\n" + second.text + "\n")

    def test_without_the_variable_nothing_is_written_and_with_the_real_environment_it_is_read(self):
        work, net = H.Work(self), H.Net(DAY)
        lines = []
        code = R.main(["init", "--mode", "dry", "--workdir", work.dir, "--start-after", START], env={}, out=lines.append,
                      now_fn=H.Clock(H.aware(START)), urlopen=net)
        self.assertEqual(code, 0)
        path = os.path.join(work.summary_dir, "from_environ.md")
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            lines2 = []
            code = R.main(["status", "--mode", "dry", "--workdir", work.dir, "--date", DAY], out=lines2.append,
                          now_fn=H.Clock(H.aware(DAY)), urlopen=net)
        self.assertEqual(code, 0)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "\n".join(lines2) + "\n")

    def test_a_summary_that_cannot_be_written_does_not_change_the_exit_code(self):
        work, net = H.Work(self), H.Net(DAY)
        lines = []
        code = R.main(["init", "--mode", "dry", "--workdir", work.dir, "--start-after", START],
                      env={"GITHUB_STEP_SUMMARY": work.summary_dir}, out=lines.append, now_fn=H.Clock(H.aware(START)), urlopen=net)
        self.assertEqual(code, 0)
        self.assertEqual(lines[-1], "- summary_file: not_written")
        self.assertEqual(H.leaks("\n".join(lines)), [])


class EnvironmentNames(H.D.Case):
    def test_a_dry_run_never_asks_for_the_secret_and_never_posts(self):
        for command, extra in (("init", ["--start-after", START]), ("morning", []), ("status", ["--date", DAY]),
                               ("check-source", [])):
            work, net = H.Work(self), H.Net(DAY)
            if command != "init":
                self.assertEqual(work.init(net, "dry", start=START).code, 0)
                work.sync_ledger(START, DAY)
            env = SpyEnv({R.SECRET_NAME: H.WEBHOOK, "GITHUB_STEP_SUMMARY": os.path.join(work.summary_dir, "s.md"),
                          "OTHER": "x", "PATH": "/usr/bin"})
            lines = []
            R.main([command, "--mode", "dry", "--workdir", work.dir, "--code-version", H.CODE] + extra, env=env, out=lines.append,
                   now_fn=H.Clock(H.aware(DAY)), urlopen=net)
            self.assertNotIn(R.SECRET_NAME, env.asked, command)
            self.assertEqual(set(env.asked), {"GITHUB_STEP_SUMMARY"}, command)
            self.assertEqual(net.posts(), [], command)
            self.assertEqual(H.leaks("\n".join(lines)), [], command)

    def test_a_live_run_asks_for_the_secret_and_the_summary_only(self):
        work, net = H.Work(self), H.Net(DAY)
        self.assertEqual(work.init(net, "live", start=START).code, 0)
        work.sync_ledger(START, DAY)
        env = SpyEnv({R.SECRET_NAME: H.WEBHOOK, "GITHUB_STEP_SUMMARY": os.path.join(work.summary_dir, "s.md"), "OTHER": "x"})
        lines = []
        R.main(["morning", "--mode", "live", "--workdir", work.dir], env=env, out=lines.append, now_fn=H.Clock(H.aware(DAY)),
               urlopen=net)
        self.assertEqual(set(env.asked), {R.SECRET_NAME, "GITHUB_STEP_SUMMARY"})
        self.assertEqual(len(net.posts()), 1)
        self.assertEqual(H.leaks("\n".join(lines)), [])

    def test_the_webhook_in_the_environment_of_a_dry_run_makes_no_request_to_discord(self):
        work, net = H.Work(self), H.Net(DAY)
        self.assertEqual(work.init(net, "dry", start=START).code, 0)
        work.morning(net, "dry", DAY, start=START, env={R.SECRET_NAME: H.WEBHOOK})
        self.assertEqual(net.posts(), [])
        self.assertEqual({r["kind"] for r in net.requests}, {"chart"})


if __name__ == "__main__":
    unittest.main()
