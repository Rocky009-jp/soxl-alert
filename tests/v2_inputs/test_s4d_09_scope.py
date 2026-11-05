"""S4D-18: the range of stage S4-D and its audits.

START is the code start of this stage (the accepted ffa3700, the final commit of S4-C). END is None until the next stage
freezes it with the accepted final commit (one line); REV is then the committed state under test. Everything is read from
Git at REV (or, for the one question of what this file says about itself, at HEAD): the working tree is not read, no
earlier stage's diff is copied, and nothing is written. The one line of test_s4c_09_scope.py that this stage had to change
is pinned below as the hunk of this stage's own diff."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "ffa370089cd37fcc76658b4de0f4aedde0a246e0"
END = "9bdd4217d18e0ac328ddfa6a76b5d2a82748549d"   # accepted (receipt 43ebe55); frozen when S4-E began
REV = END or "HEAD"

PACKAGE = "v2_inputs"
RUNTIME = tuple("v2_inputs/%s.py" % n for n in ("__init__", "ledger", "load", "market", "xnys"))
NEW_DIR = "tests/v2_inputs/"
RESULT_DOC = "docs/implementation/V2_INPUTS_S4D_RESULT.md"
CHANGED_TEST = "tests/v2_git_store/test_s4c_09_scope.py"
OLD_PACKAGES = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "v2_history_publish",
                "v2_history_local", "v2_history_maintain", "v2_daily_run", "v2_notify", "v2_git_store")
ROOTS = OLD_PACKAGES + ("main.py", "research", "docs", "CLAUDE.md", "README.md", ".github", "requirements.txt")
FIRST_OF_CHAIN = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"

# The one line of the previous stage's range test that this stage changed (S4D-18): `git diff --unified=0 START REV`.
PINNED = [('-18', '+18',
           ['END = None          # not accepted yet; the next stage replaces None with the accepted final commit'],
           ['END = "ffa370089cd37fcc76658b4de0f4aedde0a246e0"   # accepted (receipt 5dc9cdc); frozen when S4-D began'])]


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    if path in RUNTIME:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name in ("s4d_helpers.py", "s4d_worker.py") or name.startswith("test_s4d_")))


def parse_hunks(text):
    """The hunks of a `--unified=0` diff: [(old range, new range, removed lines, added lines)]."""
    hunks = []
    for line in text.splitlines():
        if line.startswith("@@"):
            head = line.split("@@")[1].split()
            hunks.append((head[0], head[1], [], []))
        elif line.startswith("--- ") or line.startswith("+++ "):
            continue
        elif hunks and line.startswith("-"):
            hunks[-1][2].append(line[1:])
        elif hunks and line.startswith("+"):
            hunks[-1][3].append(line[1:])
    return [(a, b, r, w) for a, b, r, w in hunks]


class PathJudgement(unittest.TestCase):
    def test_which_new_paths_are_allowed(self):
        self.assertTrue(allowed_new_path("tests/v2_inputs/test_s4d_01_args.py"))
        self.assertTrue(allowed_new_path("tests/v2_inputs/s4d_helpers.py"))
        self.assertTrue(allowed_new_path("tests/v2_inputs/s4d_worker.py"))
        for name in ("__init__", "ledger", "load", "market", "xnys"):
            self.assertTrue(allowed_new_path("v2_inputs/%s.py" % name))
        self.assertTrue(allowed_new_path(RESULT_DOC))
        self.assertFalse(allowed_new_path("tests/v2_inputs/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_inputs/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_inputs/sub/test_s4d_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_git_store/test_s4c_11.py"))
        self.assertFalse(allowed_new_path("v2_inputs/sixth.py"))
        self.assertFalse(allowed_new_path("v2_git_store/git.py"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_GIT_STORE_S4C_RESULT.md"))

    def test_the_hunk_reader(self):
        text = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -3 +3,2 @@ def f():\n-old\n+new\n+more\n"
        self.assertEqual(parse_hunks(text), [("-3", "+3,2", ["old"], ["new", "more"])])


class Base(unittest.TestCase):
    def setUp(self):
        probe = C.git("cat-file", "-e", START + "^{commit}")
        if probe.returncode == 0:
            probe = C.git("cat-file", "-e", REV + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")


class FilesChanged(Base):
    """S4D-18: compared with the code start by Git (committed state)."""

    def changed(self):
        out = C.git("diff", "--name-status", START, REV)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)               # no rename or copy
        return rows

    def test_exactly_one_test_file_is_modified_and_the_additions_are_allowed_paths(self):
        rows = self.changed()
        self.assertEqual([p for s, p in rows if s == "M"], [CHANGED_TEST])
        for status, path in rows:
            self.assertIn(status, ("M", "A"), "%s %s" % (status, path))
            if status == "A":
                self.assertTrue(allowed_new_path(path), path)
        added = {p for s, p in rows if s == "A"}
        self.assertTrue(set(RUNTIME) <= added)
        self.assertTrue(any(p.startswith(NEW_DIR + "test_s4d_") for p in added))
        self.assertIn(NEW_DIR + "s4d_helpers.py", added)
        self.assertLessEqual(len([p for p in added if p.startswith(PACKAGE + "/")]), 5)

    def test_everything_else_is_blob_identical_to_the_code_start(self):
        start_tree = C.git("ls-tree", "-r", START)
        rev_tree = C.git("ls-tree", "-r", REV)
        self.assertEqual((start_tree.returncode, rev_tree.returncode), (0, 0))

        def table(text):
            result = {}
            for line in text.splitlines():
                meta, path = line.split("\t", 1)
                mode, kind, blob = meta.split()
                result[path] = (mode, kind, blob)
            return result
        before, after = table(start_tree.stdout), table(rev_tree.stdout)
        compared = 0
        for path, row in before.items():
            self.assertIn(path, after, "removed: " + path)
            if path == CHANGED_TEST:
                self.assertNotEqual(after[path], row, path)
                continue
            self.assertEqual(after[path], row, path)
            compared += 1
        self.assertGreater(compared, 300)
        for path in set(after) - set(before):
            self.assertTrue(allowed_new_path(path), path)

    def test_the_existing_packages_helpers_and_documents_are_untouched(self):
        for root in OLD_PACKAGES:
            out = C.git("diff", "--name-only", START, REV, "--", root)
            self.assertEqual(out.stdout.strip(), "", root)
        out = C.git("diff", "--name-only", START, REV, "--", *ROOTS[len(OLD_PACKAGES):], ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")
        out = C.git("diff", "--name-only", START, REV, "--", "tests", ":(exclude)%s" % CHANGED_TEST,
                    ":(exclude)tests/v2_inputs")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("tests/v2_persistence_local/l_helpers.py", "tests/v2_persistence_local/worker.py",
                     "tests/v2_history_local/c3_helpers.py", "tests/v2_history_local/c3_worker.py",
                     "tests/v2_history_publish/c2_helpers.py", "tests/v2_history/h_helpers.py",
                     "tests/v2_history_ops/ho_helpers.py", "tests/v2_history_restart/r3_helpers.py",
                     "tests/v2_history_restore/r4_helpers.py", "tests/v2_history_consume/c1_helpers.py",
                     "tests/v2_history_adopt/a5_helpers.py", "tests/v2_history_maintain/c4_helpers.py",
                     "tests/v2_history_maintain/c4_worker.py", "tests/v2_persistence/p_helpers.py",
                     "tests/v2_daily_run/s4a_helpers.py", "tests/v2_daily_run/s4a_worker.py",
                     "tests/v2_notify/s4b_helpers.py", "tests/v2_notify/s4b_worker.py",
                     "tests/v2_notify/test_s4b_01_args_values.py", "tests/v2_notify/test_s4b_02_morning_halt.py",
                     "tests/v2_notify/test_s4b_03_error.py", "tests/v2_notify/test_s4b_04_text.py",
                     "tests/v2_notify/test_s4b_05_send_state.py", "tests/v2_notify/test_s4b_06_outbox_faults.py",
                     "tests/v2_notify/test_s4b_07_resend.py", "tests/v2_notify/test_s4b_08_processes.py",
                     "tests/v2_notify/test_s4b_10_static.py", "tests/v2_notify/test_s4b_09_scope.py",
                     "tests/v2_daily_run/test_s4a_09_scope.py", "tests/v2_git_store/s4c_helpers.py",
                     "tests/v2_git_store/s4c_worker.py", "tests/v2_git_store/test_s4c_01_args.py",
                     "tests/v2_git_store/test_s4c_02_git.py", "tests/v2_git_store/test_s4c_03_history.py",
                     "tests/v2_git_store/test_s4c_04_unreachable.py", "tests/v2_git_store/test_s4c_05_outbox.py",
                     "tests/v2_git_store/test_s4c_06_processes.py", "tests/v2_git_store/test_s4c_07_commits.py",
                     "tests/v2_git_store/test_s4c_08_static.py", "tests/v2_git_store/test_s4c_10_secrets.py",
                     "tests/v2_scope_chain/sc_helpers.py", "tests/v2_scope_chain/test_sc_01_freeze.py",
                     "tests/v2_scope_chain/test_sc_02_chain.py", "tests/v2_scope_chain/test_sc_03_scope.py",
                     "tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py",
                     "tests/v2_history_restore/test_r4_09_scope.py", "tests/v2_history_diagnose/test_d5_08_scope.py",
                     "tests/v2_history_adopt/test_a5_08_scope.py", "tests/v2_history_consume/test_c1_09_scope.py",
                     "tests/v2_history_publish/test_c2_09_scope.py", "tests/v2_history_local/test_c3_09_scope.py",
                     "tests/v2_history_maintain/test_c4_09_scope.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)

    def test_the_package_is_the_five_files_of_the_design(self):
        names = sorted(p for p in C.list_files(REV, PACKAGE))
        self.assertEqual(names, sorted(RUNTIME))
        self.assertEqual(C.list_files(START, PACKAGE), [])

    def test_the_one_modified_test_is_the_one_pinned_line(self):
        out = C.git("diff", "--unified=0", START, REV, "--", CHANGED_TEST)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in PINNED])

    def test_no_new_dependency_file_and_the_public_names_of_the_old_packages_are_unchanged(self):
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertEqual(C.blob_id(REV, name), C.blob_id(START, name), name)
        for package in OLD_PACKAGES:
            path = package + "/__init__.py"
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
        for path in ("v2_daily_run/run.py", "v2_daily_run/values.py", "v2_persistence/local/fsops.py",
                     "v2_history_local/store.py", "v2_history_local/results.py", "v2_history_ops/daily.py",
                     "v2_history_publish/build.py", "v2_core/display.py", "v2_notify/job.py", "v2_notify/outbox.py",
                     "v2_notify/values.py", "v2_notify/compose.py", "v2_git_store/git.py", "v2_git_store/history.py",
                     "v2_git_store/outbox.py", "main.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)


class Chain(Base):
    """S4D-18: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], [CHANGED_TEST])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_s4d_09_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin=FIRST_OF_CHAIN), [])
        self.assertGreaterEqual(len(rows), 12)
        starts = [r["start"] for r in rows]
        self.assertEqual(starts.count(START), 1)
        for earlier in ("bfbde7a7854bf91a77fb58737c24b19c6507453a", "de6549acb4ecea759cc771300fd0bef59dd5456a",
                        "d6b0332500af8d8d46ddaae6c7fda39ee38a03db", "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a",
                        "2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb", "6ad609fe52b50565103e56c598505cac85601216",
                        "6cab0506c408d194c63b656713e4a0a7d62c3ba1"):
            self.assertIn(earlier, starts)

    def test_the_previous_range_is_frozen_at_the_code_start_by_the_changed_line(self):
        tree = ast.parse(C.show(REV, CHANGED_TEST))
        found, end = C.read_constant(tree, "END", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, end), (True, START))
        found, start = C.read_constant(tree, "START", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, start), (True, "6cab0506c408d194c63b656713e4a0a7d62c3ba1"))

    def test_the_range_values_of_this_file_are_read_from_the_text_at_head(self):
        # HEAD, not REV: once the next stage freezes END, REV is the commit that holds END = None, and the file that
        # says it is the one that is checked out
        path = NEW_DIR + "test_s4d_09_scope.py"
        tree = ast.parse(C.show("HEAD", path))
        self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), "HEAD"), (True, START))
        self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), "HEAD"), (True, END))
        self.assertIn("FilesChanged", C.top_level(tree))


class TestFiles(Base):
    """S4D-18: what the new tests may do. They read Git and the parsed text, write to temporary roots only (the S4-C helper
    makes the bare repositories and the clones), start `git` only through that helper (tgit, with its own settings) and the
    children only through this stage's helper, never read the process environment, open files only to read the research data
    (one helper function), and read the runtime sources of the working tree through the helper."""

    ALLOWED_IMPORTS = {"ast", "csv", "datetime", "hashlib", "json", "os", "re", "subprocess", "sys", "unittest", "s4c_helpers",
                       "s4d_helpers", "sc_helpers", "test_s4d_09_scope", "v2_core.errors", "v2_core.fixture",
                       "v2_daily_run", "v2_history_publish", "v2_inputs", "v2_inputs.market", "v2_inputs.xnys"}
    FORBIDDEN_ATTRS = {"getenv", "putenv", "environ", "urandom", "sleep", "chdir", "expanduser", "home", "system", "popen",
                       "urlopen", "getaddrinfo", "gethostbyname", "connect", "create_connection", "monotonic", "utcnow",
                       "today", "now"}
    HELPER = NEW_DIR + "s4d_helpers.py"

    def own_sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 14)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def test_the_own_files_are_the_allowed_ones_and_there_is_no_init_file(self):
        names = [p.rsplit("/", 1)[1] for p in C.list_files(REV, NEW_DIR.rstrip("/"))]
        self.assertNotIn("__init__.py", names)
        for path in self.own_sources():
            self.assertTrue(allowed_new_path(path), path)

    def test_imports_and_the_absence_of_clock_network_and_environment(self):
        for path, tree in self.own_sources().items():
            helper = path == self.HELPER
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, self.ALLOWED_IMPORTS, "%s imports %s" % (path, a.name))
                        if a.name == "subprocess":
                            self.assertTrue(helper, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    allowed = self.ALLOWED_IMPORTS | {"unittest.mock", "datetime"}
                    self.assertIn(node.module, allowed, "%s imports %s" % (path, node.module))
                if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "ast"):
                    self.assertNotIn(node.attr, self.FORBIDDEN_ATTRS, "%s uses .%s" % (path, node.attr))

    def test_children_are_started_only_by_the_helper_through_the_worker(self):
        helpers = self.own_sources()[self.HELPER]
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "subprocess":
                    self.assertEqual(path, self.HELPER)
        calls = sorted({ast.unparse(n.func) for n in ast.walk(helpers) if isinstance(n, ast.Call)
                        and ast.unparse(n.func).startswith("subprocess.")})
        self.assertEqual(calls, ["subprocess.Popen"])
        popen = [[ast.unparse(e) for e in n.args[0].elts] for n in ast.walk(helpers)
                 if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.Popen"]
        self.assertEqual(popen, [["sys.executable", "'-B'", "'-I'", "WORKER", "json.dumps(spec)"]])
        assigned = [ast.unparse(n.value) for n in helpers.body if isinstance(n, ast.Assign)
                    and ast.unparse(n.targets[0]) == "WORKER"]
        self.assertEqual(assigned, ["os.path.join(HERE, 's4d_worker.py')"])

    def test_git_is_started_only_through_the_helper_of_the_previous_stage(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), ("subprocess.run", "subprocess.check_output",
                                                              "os.system", "os.popen"), path)

    def test_files_are_opened_only_to_read_the_research_data(self):
        for path, tree in self.own_sources().items():
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                opens = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                         and n.func.id == "open"]
                if opens:
                    self.assertEqual((path, fn.name), (self.HELPER, "_load_src"))
                    for call in opens:
                        self.assertEqual(ast.unparse(call.args[1]), "'rb'")
            for n in [n for n in tree.body if isinstance(n, (ast.Expr, ast.Assign))]:
                for sub in ast.walk(n):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        self.assertNotEqual(sub.func.id, "open", path)

    def test_the_tests_do_not_use_the_private_constructors_of_the_values_under_test(self):
        for path, tree in self.own_sources().items():
            if path.endswith("test_s4d_09_scope.py"):
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, ("_make", "_wrap", "_of", "from_dict", "_set"), path)

    def test_git_is_asked_only_through_the_read_only_helper_and_this_file_reads_no_working_tree(self):
        scope = self.own_sources()[NEW_DIR + "test_s4d_09_scope.py"]
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ("open", "eval", "exec", "input", "__import__", "print", "compile"))
            if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "ast"):
                self.assertNotIn(node.attr, ("listdir", "scandir", "walk", "isfile", "isdir", "exists", "read_text",
                                             "read_bytes", "glob", "write", "mkdir", "unlink", "rename", "rmtree"))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "git" \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "C":
                self.assertTrue(node.args and isinstance(node.args[0], ast.Constant))
                self.assertIn(node.args[0].value, C.READ_ONLY_GIT)
        reads = [n for n in ast.walk(scope) if isinstance(n, ast.Call) and ast.unparse(n.func) == "C.show"]
        for call in reads:
            self.assertIn(ast.unparse(call.args[0]), ("REV", "START", "'HEAD'"), ast.unparse(call))

    def test_the_tests_leave_no_bytecode_or_file_to_add(self):
        out = C.git("diff", "--name-only", START, REV)
        self.assertEqual([p for p in out.stdout.split() if "__pycache__" in p or p.endswith((".pyc", ".log"))], [])


if __name__ == "__main__":
    unittest.main()
