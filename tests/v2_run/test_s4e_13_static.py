"""S4E-17: what the code of v2_run may import and call (the section 3 item 16 of the request), and the workflow template and the guide
checked as text (the template is never run; the one line that picks the mode is run with bash on a table of cases)."""
import ast
import os
import re
import unittest

import s4e_helpers as H

ROOT = H.ROOT
PKG = os.path.join(ROOT, "v2_run")
TEMPLATE = os.path.join(ROOT, "docs", "ops", "V2_MORNING_WORKFLOW_TEMPLATE.yml")
GUIDE = os.path.join(ROOT, "docs", "ops", "V2_PRIVATE_RUN_GUIDE.md")
FILES = ("__init__.py", "__main__.py", "check.py", "entry.py", "web.py")
FORBIDDEN_MODULES = ("subprocess", "threading", "random", "zoneinfo", "http", "ssl", "asyncio", "multiprocessing", "ctypes", "pickle")
NETWORK_MODULES = ("urllib", "socket")


def sources():
    out = {}
    for name in FILES:
        with open(os.path.join(PKG, name), "rb") as f:
            out[name] = ast.parse(f.read().decode("utf-8"))
    return out


def imported(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.append(node.module)
    return names


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


class Code(unittest.TestCase):
    def test_the_package_is_the_five_files(self):
        names = sorted(n for n in os.listdir(PKG) if not n.startswith("__pycache__"))
        self.assertEqual(names, sorted(FILES))

    def test_network_modules_are_imported_by_web_only_and_the_forbidden_ones_by_nobody(self):
        for name, tree in sources().items():
            for module in imported(tree):
                root = module.split(".")[0]
                self.assertNotIn(root, FORBIDDEN_MODULES, "%s imports %s" % (name, module))
                if root in NETWORK_MODULES:
                    self.assertEqual(name, "web.py", "%s imports %s" % (name, module))
        self.assertTrue(any(m.split(".")[0] == "urllib" for m in imported(sources()["web.py"])))

    def test_the_clock_is_read_in_one_place_and_the_environment_in_one_place(self):
        counts = {"now": [], "environ": []}
        for name, tree in sources().items():
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,))]:
                for node in ast.walk(fn):
                    if isinstance(node, ast.Attribute) and node.attr == "now" and isinstance(node.value, ast.Attribute) \
                            and node.value.attr == "datetime":
                        counts["now"].append((name, fn.name))
                    if isinstance(node, ast.Attribute) and node.attr == "environ":
                        counts["environ"].append((name, fn.name))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, ("utcnow", "today", "getenv", "putenv", "time", "sleep", "perf_counter",
                                                 "urandom", "uuid4", "system", "popen", "Popen", "call", "check_output"), name)
        self.assertEqual(counts["now"], [("entry.py", "utc_now")])
        self.assertEqual(counts["environ"], [("entry.py", "main")])
        self.assertEqual(sum(1 for n, t in sources().items() for x in ast.walk(t) if isinstance(x, ast.Attribute) and x.attr == "environ"), 1)

    def test_time_is_used_for_monotonic_only(self):
        for name, tree in sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "time":
                    self.assertEqual(node.attr, "monotonic", name)
            for module in imported(tree):
                self.assertNotEqual(module, "time.sleep")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "time":
                    self.assertEqual([a.name for a in node.names], ["monotonic"])

    def test_no_private_attribute_of_another_object_is_used(self):
        for name, tree in sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    self.assertTrue(isinstance(node.value, ast.Name) and node.value.id == "self", "%s uses .%s" % (name, node.attr))

    def test_nothing_is_raised_inside_an_except_body_except_a_bare_raise(self):
        for name, tree in sources().items():
            for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
                for node in ast.walk(handler):
                    if isinstance(node, ast.Raise):
                        self.assertIsNone(node.exc, "%s raises inside an except body" % name)

    def test_main_is_the_only_entry_and_main_dunder_is_one_line(self):
        text = read(os.path.join(PKG, "__main__.py"))
        code = [l for l in text.splitlines() if l.strip()]
        self.assertEqual(code, ["import sys", "from . import main", "sys.exit(main(sys.argv[1:]))"])

    def test_no_wait_no_retry_loop_no_eval(self):
        for name, tree in sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("eval", "exec", "compile", "__import__", "input"), name)
                if isinstance(node, ast.AsyncFor):
                    self.fail("an async loop in " + name)
                if isinstance(node, ast.While):       # only the cutting of a text (split_text) may loop; never a call outside
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Call):
                            callee = inner.func.attr if isinstance(inner.func, ast.Attribute) else getattr(inner.func, "id", "")
                            self.assertNotRegex(callee, r"urlopen|post|fetch|send|git|sleep|run|push|claim|write|open",
                                                "a loop that may retry in " + name)

    def test_the_defaults_of_main_are_the_real_clock_and_the_real_urlopen_through_web(self):
        import inspect
        params = inspect.signature(H.R.main).parameters
        self.assertEqual(list(params), ["argv", "env", "out", "now_fn", "urlopen"])
        self.assertIsNone(params["env"].default)
        self.assertIs(params["now_fn"].default, H.ENTRY.utc_now)
        self.assertIs(params["urlopen"].default, H.WEB.real_urlopen)
        self.assertIs(params["out"].default, print)


class Template(unittest.TestCase):
    text = read(TEMPLATE)

    def lines(self):
        return self.text.splitlines()

    def code_lines(self):
        return [l for l in self.lines() if not l.lstrip().startswith("#")]

    def block(self, header):
        """The lines under `header:` (an exact stripped line) up to the first line that is not indented deeper."""
        lines = self.lines()
        for index, line in enumerate(lines):
            if line.split("#")[0].strip() == header:
                indent = len(line) - len(line.lstrip())
                out = []
                for follow in lines[index + 1:]:
                    if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                        break
                    out.append(follow)
                return out
        self.fail("no block " + header)

    def test_the_two_cron_lines_and_the_manual_trigger(self):
        schedule = [l.strip() for l in self.code_lines() if "cron:" in l]
        self.assertEqual([l.split("#")[0].strip() for l in schedule], ['- cron: "40 22 * * 1-5"', '- cron: "40 23 * * 1-5"'])
        inputs = self.block("workflow_dispatch:")
        names = [l.strip()[:-1] for l in inputs if re.fullmatch(r"\s{6}[a-z_]+:", l)]
        self.assertEqual(names, ["command", "mode", "date", "kind", "request_id", "start_after"])

    def test_the_mode_input_is_auto_dry_live_with_auto_as_the_default(self):
        mode = []
        take = False
        for l in self.lines():
            if re.fullmatch(r"\s{6}mode:", l):
                take = True
                continue
            if take and re.fullmatch(r"\s{6}[a-z_]+:", l):
                break
            if take:
                mode.append(l.strip())
        self.assertIn("options: [auto, dry, live]", mode)
        self.assertIn("default: auto", mode)
        self.assertIn("type: choice", mode)

    def test_permissions_timeout_and_runner(self):
        self.assertEqual([l.strip() for l in self.block("permissions:") if l.strip() and not l.strip().startswith("#")],
                         ["contents: write              # この非公開リポジトリだけ（GITHUB_TOKEN）。v2-* の参照へ push する"])
        self.assertIn("timeout-minutes: 30", [l.strip() for l in self.code_lines()])
        self.assertIn("runs-on: ubuntu-24.04", [l.strip() for l in self.code_lines()])

    def test_the_concurrency_of_the_job(self):
        block = [l.strip() for l in self.block("concurrency:") if l.strip() and not l.strip().startswith("#")]
        self.assertEqual(len(block), 3)
        group, cancel, queue = block
        self.assertEqual((cancel, queue), ("cancel-in-progress: false", "queue: max"))
        self.assertTrue(group.startswith("group: ${{ ") and group.endswith(" }}"))
        expression = group[len("group: ${{ "):-3]
        first, _sep, last = expression.rpartition(" || ")
        self.assertEqual(last, "'v2-writer'")
        self.assertNotIn("v2-writer", first)
        self.assertIn("inputs.command == 'status'", first)
        self.assertIn("inputs.command == 'check-source'", first)
        # evaluate it for every event and command (the only operators are && || == and format)
        python = (expression.replace("github.event_name", "event").replace("inputs.command", "command")
                  .replace("&&", " and ").replace("||", " or ").replace("github.run_id", "run_id")
                  .replace("format('v2-read-{0}', run_id)", "'v2-read-' + run_id"))
        self.assertRegex(python, r"^[\w\s'()=\-+.]+$")

        def group_of(event, command, run_id):
            return eval(python, {"__builtins__": {}}, {"event": event, "command": command, "run_id": run_id})
        self.assertEqual(group_of("schedule", "", "7"), "v2-writer")
        for command in ("morning", "resend", "init", ""):
            self.assertEqual(group_of("workflow_dispatch", command, "7"), "v2-writer", command)
        self.assertEqual(group_of("workflow_dispatch", "status", "7"), "v2-read-7")
        self.assertEqual(group_of("workflow_dispatch", "check-source", "8"), "v2-read-8")
        self.assertNotEqual(group_of("workflow_dispatch", "status", "7"), group_of("workflow_dispatch", "status", "8"))

    def test_the_concurrency_is_set_on_the_job_not_on_the_workflow(self):
        lines = self.lines()
        index = [i for i, l in enumerate(lines) if l.strip() == "concurrency:" and not l.lstrip().startswith("#")]
        self.assertEqual(len(index), 1)
        self.assertEqual(len(lines[index[0]]) - len(lines[index[0]].lstrip()), 4)           # under jobs.run

    def test_env_and_the_two_checkouts(self):
        code = [l.strip() for l in self.code_lines()]
        self.assertIn("V2_MODE: dry", [l.split("#")[0].strip() for l in code])
        self.assertIn('V2_CODE_SHA: "%s"' % ("0" * 40), [l.split("#")[0].strip() for l in code])
        uses = [l for l in code if l.startswith("- uses:")]
        self.assertEqual(len(uses), 2)
        for l in uses:
            self.assertRegex(l.split("#")[0].strip(), r"^- uses: actions/checkout@[0-9a-f]{40}$")
        text = "\n".join(self.lines())
        private = text.split("- uses:")[1]
        public = text.split("- uses:")[2]
        self.assertIn("path: state", private)
        self.assertIn("persist-credentials: true", private)
        self.assertNotIn("ref:", private)
        self.assertIn("ref: ${{ env.V2_CODE_SHA }}", public)
        self.assertIn("persist-credentials: false", public)
        self.assertIn("repository: Rocky009-jp/soxl-alert", public)
        self.assertIn("path: code", public)
        self.assertEqual(self.text.count("E-2 で公式のリリースの SHA を確かめて書く"), 2)

    def run_block(self):
        lines = self.lines()
        for index, line in enumerate(lines):
            if line.strip() == "run: |":
                indent = len(line) - len(line.lstrip())
                out = []
                for follow in lines[index + 1:]:
                    if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                        break
                    out.append(follow.strip())
                return out
        self.fail("no run block")

    def test_the_run_step_takes_the_inputs_through_the_environment_and_has_no_secret(self):
        run = self.run_block()
        self.assertEqual(sum(1 for l in run if "python3 -E -B -m v2_run" in l), 1)
        for l in run:
            self.assertNotIn("${{", l)
            self.assertNotIn("inputs.", l)
            self.assertNotIn("github.event", l)
            self.assertNotIn("secrets", l)
        self.assertEqual(sum(l.count("--mode") for l in run), 1)
        self.assertIn('--mode "$MODE"', "\n".join(run))
        self.assertEqual(len([l for l in run if l.startswith("case ")]), 1)
        env = [l.strip() for l in self.lines() if re.match(r"\s{10}[A-Z_]+: \$\{\{ ", l)]
        self.assertIn("INPUT_MODE: ${{ inputs.mode }}", env)
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", env)
        for line in self.code_lines():
            self.assertNotIn("secrets.", line)
            self.assertNotIn("${{ secrets", line)
            self.assertNotIn("V2_DISCORD_WEBHOOK_URL", line)
            if "${{ inputs." in line or "${{ github.event." in line:
                self.assertTrue(re.match(r"\s*(INPUT_[A-Z_]+|EVENT_NAME|group): ", line.strip() and line), line)
        self.assertNotIn("secrets.", self.text)

    def test_the_line_that_chooses_the_mode(self):
        case = [l for l in self.run_block() if l.startswith("case ")][0]
        self.assertEqual(case, 'case "$EVENT_NAME:$INPUT_MODE" in schedule:*|*:auto) MODE="$V2_MODE";; *) MODE="$INPUT_MODE";; esac')
        table = []
        for v2_mode in ("dry", "live"):
            table += [("schedule", "", v2_mode, v2_mode), ("schedule", "live", v2_mode, v2_mode), ("schedule", "dry", v2_mode, v2_mode),
                      ("workflow_dispatch", "auto", v2_mode, v2_mode), ("workflow_dispatch", "dry", v2_mode, "dry"),
                      ("workflow_dispatch", "live", v2_mode, "live"), ("workflow_dispatch", "", v2_mode, "")]
        for event, input_mode, v2_mode, want in table:
            env = {"EVENT_NAME": event, "INPUT_MODE": input_mode, "V2_MODE": v2_mode, "PATH": os.environ.get("PATH", "")}
            got = H.run_bash(case + '\nprintf %s "$MODE"', env)
            if got is None:
                self.skipTest("bash is not available")
            self.assertEqual(got, want, (event, input_mode, v2_mode))

    def test_an_empty_mode_is_refused_by_the_entry_as_a_wrong_argument(self):
        lines = []
        code = H.R.main(["morning", "--mode", "", "--workdir", ROOT], env={}, out=lines.append, now_fn=H.Clock(H.aware("2026-07-21")),
                        urlopen=None)
        self.assertEqual(code, 2)

    def test_the_comments_say_where_the_template_goes_and_what_is_checked_in_e2_and_e4(self):
        for phrase in ("docs/ops/", "E-2", "queue: max", "E-4", "$GITHUB_OUTPUT", "7:40", "8:40", "F&G"):
            self.assertIn(phrase, self.text)


class Guide(unittest.TestCase):
    text = read(GUIDE)

    def test_no_webhook_value_no_local_path_no_secret_value(self):
        self.assertNotRegex(self.text, r"https?://discord(app)?\.com/api/webhooks/\S")
        self.assertNotIn("discord.com/api/webhooks/", self.text)
        for fragment in ("/home/", "/tmp/", "/Users/", "/root/", "C:\\", "~/", "/mnt/", "file://", "SECRETTOKEN", "SECRETMARK"):
            self.assertNotIn(fragment, self.text)
        self.assertNotRegex(self.text, r"[0-9]{17,}")                     # no webhook id
        self.assertNotRegex(self.text, r"[A-Za-z0-9_-]{60,}")             # no token

    def test_the_thirteen_items_the_ledger_start_and_the_five_stages(self):
        for item in ("## 1. 毎朝の流れ", "## 2. 台帳の書き方", "## 3. 通知の読み方", "## 4. 手動の操作", "## 5. 再送", "## 6. DAMAGED",
                     "## 7. 止まり続ける理由コード", "## 8. 休場日の表", "## 9. 版の更新", "## 10. 保守の操作",
                     "## 11. 巻戻しの確認", "## 12. 開始の境界", "## 13. 取得の失敗の理由"):
            self.assertIn(item, self.text)
        for stage in ("### E-1 ", "### E-2 ", "### E-3 ", "### E-4 ", "### E-5 "):
            self.assertIn(stage, self.text)
        for phrase in ("v2-ledger", "observations.csv", "見出しの 1 行だけ", "7:40", "8:40", "9:30", "1 回目の実行（7:40）までに記録",
                       "次の寄付きの前までに必ず記録", "`dry` を選ぶと送信されない", "`auto` のまま", "9:00 より後", "判定ありが有効",
                       "REFUSED_JUDGMENT_EXISTS", "CLAIM_FAILED", "時間を置いてもう一度", "手で直さない", "ICE", "V2_CODE_SHA",
                       "history_digest", "init` の時点で閉じた最後のセッション", "試運転と同じ日", "http_429", "timeout", "url_error",
                       "size", "cron の行を含むコミットは Rocky さん本人", "承認された段階でだけ"):
            self.assertIn(phrase, self.text, phrase)

    def test_the_twelve_pass_criteria_of_the_trial_are_listed(self):
        block = self.text.split("### E-3")[1].split("### E-4")[0]
        numbered = re.findall(r"^  (\d+)\. ", block, re.M)
        self.assertEqual(numbered, [str(i) for i in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
