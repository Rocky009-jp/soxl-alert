"""S4E-18: the range of stage S4-E and its audits.

START is the code start of this stage (the accepted 9bdd421, the final commit of S4-D). END is None until the next stage
freezes it with the accepted final commit (one line); REV is then the committed state under test. Everything is read from
Git at REV (or, for the one question of what this file says about itself, at HEAD): the working tree is not read, no
earlier stage's diff is copied, and nothing is written. The three existing files that this stage had to change (the END line
of test_s4d_09_scope.py, one condition of v2_notify/job.py, the place of one assignment of v2_inputs/load.py) are pinned
below as the hunks of this stage's own diff."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "9bdd4217d18e0ac328ddfa6a76b5d2a82748549d"
END = None          # not accepted yet; the next stage replaces None with the accepted final commit
REV = END or "HEAD"

PACKAGE = "v2_run"
RUNTIME = tuple("v2_run/%s.py" % n for n in ("__init__", "__main__", "check", "entry", "web"))
NEW_DIR = "tests/v2_run/"
OPS = ("docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.yml", "docs/ops/V2_PRIVATE_RUN_GUIDE.md")
RESULT_DOC = "docs/implementation/V2_RUN_S4E_RESULT.md"
CHANGED = ("tests/v2_inputs/test_s4d_09_scope.py", "v2_inputs/load.py", "v2_notify/job.py")
OLD_PACKAGES = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "v2_history_publish",
                "v2_history_local", "v2_history_maintain", "v2_daily_run", "v2_notify", "v2_git_store", "v2_inputs")
ROOTS = ("main.py", "research", "CLAUDE.md", "README.md", ".github", "requirements.txt")
FIRST_OF_CHAIN = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"
S4D_SCOPE = "tests/v2_inputs/test_s4d_09_scope.py"

# The lines of the three existing files that this stage changed (S4E-18): `git diff --unified=0 START REV -- <path>`.
PINNED = {
    "tests/v2_inputs/test_s4d_09_scope.py": [
        ('-18', '+18',
         ['END = None          # not accepted yet; the next stage replaces None with the accepted final commit'],
         ['END = "9bdd4217d18e0ac328ddfa6a76b5d2a82748549d"   # accepted (receipt 43ebe55); frozen when S4-E began'])],
    "v2_inputs/load.py": [
        ('-130', '+129,0', ['            provenance["fetch_count"] = calls[0]'], []),
        ('-158,0', '+158',
         [], ['    provenance["fetch_count"] = calls[0]                       # S4-E (S4-D review P-01): also after a parse error'])],
    "v2_notify/job.py": [
        ('-112', '+112',
         ['    judgment_known = notice.kind == HALT or (notice.kind == ERROR and target_d is not None)'],
         ['    judgment_known = notice.kind in (HALT, ERROR)      # S4-E (S4-B review P-01): the fallback key checks its date too'])],
}


def allowed_new_path(path):
    if path == RESULT_DOC or path in RUNTIME or path in OPS:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name in ("s4e_helpers.py", "s4e_worker.py") or name.startswith("test_s4e_")))


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
        self.assertTrue(allowed_new_path("tests/v2_run/test_s4e_01_args.py"))
        self.assertTrue(allowed_new_path("tests/v2_run/s4e_helpers.py"))
        self.assertTrue(allowed_new_path("tests/v2_run/s4e_worker.py"))
        for name in ("__init__", "__main__", "check", "entry", "web"):
            self.assertTrue(allowed_new_path("v2_run/%s.py" % name))
        for path in OPS + (RESULT_DOC,):
            self.assertTrue(allowed_new_path(path))
        self.assertFalse(allowed_new_path("tests/v2_run/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_run/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_run/sub/test_s4e_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_inputs/test_s4d_10.py"))
        self.assertFalse(allowed_new_path("v2_run/sixth.py"))
        self.assertFalse(allowed_new_path("v2_inputs/market.py"))
        self.assertFalse(allowed_new_path(".github/workflows/v2_morning.yml"))
        self.assertFalse(allowed_new_path("docs/ops/OTHER.md"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_INPUTS_S4D_RESULT.md"))

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
    """S4E-18: compared with the code start by Git (committed state)."""

    def changed(self):
        out = C.git("diff", "--name-status", START, REV)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)               # no rename or copy
        return rows

    def test_exactly_three_files_are_modified_and_the_additions_are_allowed_paths(self):
        rows = self.changed()
        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(CHANGED))
        for status, path in rows:
            self.assertIn(status, ("M", "A"), "%s %s" % (status, path))
            if status == "A":
                self.assertTrue(allowed_new_path(path), path)
        added = {p for s, p in rows if s == "A"}
        self.assertTrue(set(RUNTIME) <= added)
        self.assertTrue(set(OPS) <= added)
        self.assertTrue(any(p.startswith(NEW_DIR + "test_s4e_") for p in added))
        self.assertIn(NEW_DIR + "s4e_helpers.py", added)
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
            if path in CHANGED:
                self.assertNotEqual(after[path], row, path)
                continue
            self.assertEqual(after[path], row, path)
            compared += 1
        self.assertGreater(compared, 300)
        for path in set(after) - set(before):
            self.assertTrue(allowed_new_path(path), path)

    def test_the_existing_packages_helpers_and_documents_are_untouched(self):
        for root in OLD_PACKAGES:
            out = C.git("diff", "--name-only", START, REV, "--", root, ":(exclude)v2_notify/job.py", ":(exclude)v2_inputs/load.py")
            self.assertEqual(out.stdout.strip(), "", root)
        out = C.git("diff", "--name-only", START, REV, "--", *ROOTS)
        self.assertEqual(out.stdout.strip(), "")
        out = C.git("diff", "--name-only", START, REV, "--", "docs", ":(exclude)docs/ops", ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")
        out = C.git("diff", "--name-only", START, REV, "--", "tests", ":(exclude)%s" % S4D_SCOPE, ":(exclude)tests/v2_run")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("tests/v2_persistence_local/l_helpers.py", "tests/v2_history_local/c3_helpers.py",
                     "tests/v2_history_publish/c2_helpers.py", "tests/v2_history/h_helpers.py",
                     "tests/v2_history_maintain/c4_helpers.py", "tests/v2_persistence/p_helpers.py",
                     "tests/v2_daily_run/s4a_helpers.py", "tests/v2_daily_run/s4a_worker.py",
                     "tests/v2_notify/s4b_helpers.py", "tests/v2_notify/s4b_worker.py",
                     "tests/v2_notify/test_s4b_09_scope.py", "tests/v2_daily_run/test_s4a_09_scope.py",
                     "tests/v2_git_store/s4c_helpers.py", "tests/v2_git_store/s4c_worker.py",
                     "tests/v2_git_store/test_s4c_09_scope.py", "tests/v2_inputs/s4d_helpers.py",
                     "tests/v2_inputs/s4d_worker.py", "tests/v2_inputs/test_s4d_01_args.py",
                     "tests/v2_scope_chain/sc_helpers.py", "tests/v2_scope_chain/test_sc_01_freeze.py",
                     "tests/v2_scope_chain/test_sc_02_chain.py", "tests/v2_scope_chain/test_sc_03_scope.py",
                     "tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py",
                     "tests/v2_history_restore/test_r4_09_scope.py", "tests/v2_history_diagnose/test_d5_08_scope.py",
                     "tests/v2_history_adopt/test_a5_08_scope.py", "tests/v2_history_consume/test_c1_09_scope.py",
                     "tests/v2_history_publish/test_c2_09_scope.py", "tests/v2_history_local/test_c3_09_scope.py",
                     "tests/v2_history_maintain/test_c4_09_scope.py", "v2_daily_run/run.py", "v2_core/display.py",
                     "v2_notify/compose.py", "v2_notify/outbox.py", "v2_notify/values.py", "v2_git_store/git.py",
                     "v2_git_store/history.py", "v2_git_store/outbox.py", "v2_inputs/market.py", "v2_inputs/ledger.py",
                     "v2_inputs/xnys.py", "v2_inputs/__init__.py", "main.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)

    def test_the_package_is_the_five_files_of_the_design(self):
        self.assertEqual(sorted(C.list_files(REV, PACKAGE)), sorted(RUNTIME))
        self.assertEqual(C.list_files(START, PACKAGE), [])

    def test_the_three_modified_files_are_exactly_the_pinned_hunks(self):
        for path in CHANGED:
            out = C.git("diff", "--unified=0", START, REV, "--", path)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in PINNED[path]], path)

    def test_no_new_dependency_file_and_no_workflow(self):
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertEqual(C.blob_id(REV, name), C.blob_id(START, name), name)
        self.assertEqual(C.list_files(REV, ".github"), C.list_files(START, ".github"))
        for package in OLD_PACKAGES:
            path = package + "/__init__.py"
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)


class Chain(Base):
    """S4E-18: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], [S4D_SCOPE])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_s4e_09_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin=FIRST_OF_CHAIN), [])
        self.assertGreaterEqual(len(rows), 13)
        starts = [r["start"] for r in rows]
        self.assertEqual(starts.count(START), 1)
        for earlier in ("ffa370089cd37fcc76658b4de0f4aedde0a246e0", "6cab0506c408d194c63b656713e4a0a7d62c3ba1",
                        "6ad609fe52b50565103e56c598505cac85601216", "2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb",
                        "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a", "d6b0332500af8d8d46ddaae6c7fda39ee38a03db",
                        "de6549acb4ecea759cc771300fd0bef59dd5456a", "bfbde7a7854bf91a77fb58737c24b19c6507453a"):
            self.assertIn(earlier, starts)

    def test_the_previous_range_is_frozen_at_the_code_start_by_the_changed_line(self):
        tree = ast.parse(C.show(REV, S4D_SCOPE))
        directory = os.path.dirname(S4D_SCOPE)
        self.assertEqual(C.read_constant(tree, "END", directory, REV), (True, START))
        self.assertEqual(C.read_constant(tree, "START", directory, REV), (True, "ffa370089cd37fcc76658b4de0f4aedde0a246e0"))

    def test_the_range_values_of_this_file_are_read_from_the_text_at_head(self):
        # HEAD, not REV: once the next stage freezes END, REV is the commit that holds END = None, and the file that
        # says it is the one that is checked out
        path = NEW_DIR + "test_s4e_09_scope.py"
        tree = ast.parse(C.show("HEAD", path))
        self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), "HEAD"), (True, START))
        self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), "HEAD"), (True, END))
        self.assertIn("FilesChanged", C.top_level(tree))


class TestFiles(Base):
    """S4E-18: what the new tests may do. They read Git and the parsed text; write to temporary roots only (the S4-C helper
    makes the bare repositories and the clones, this stage's helper the work directories); start `git` only through that
    helper (tgit, with its own settings); start `subprocess` only in the helper (the version of git, the bash line of the
    template, the children of S4E-14); never read the clock or the network (the fake urlopen and the injected clock);
    read the process environment only to give `bash` its PATH and to prove that main reads it; open files only to read
    the sources, the template and the records (the one write is the shared summary file of a temporary directory)."""

    ALLOWED_IMPORTS = {"ast", "datetime", "hashlib", "inspect", "io", "json", "os", "re", "shutil", "socket", "subprocess",
                       "sys", "tempfile", "unittest", "unittest.mock", "urllib.error", "urllib.request", "s4d_helpers",
                       "s4e_helpers", "sc_helpers", "test_s4e_09_scope", "v2_core.fixture", "v2_run", "v2_run.web"}
    FORBIDDEN_ATTRS = {"getenv", "putenv", "environ", "urandom", "sleep", "chdir", "expanduser", "home", "system", "popen",
                       "urlopen", "getaddrinfo", "gethostbyname", "connect", "create_connection", "monotonic", "utcnow",
                       "today", "now"}
    HELPER = NEW_DIR + "s4e_helpers.py"
    ENVIRON_FILES = (NEW_DIR + "test_s4e_12_record.py", NEW_DIR + "test_s4e_13_static.py")
    OPEN_FILES = (HELPER, NEW_DIR + "test_s4e_12_record.py", NEW_DIR + "test_s4e_13_static.py")
    URLOPEN_FILES = (HELPER, NEW_DIR + "test_s4e_01_args.py")

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
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, self.ALLOWED_IMPORTS, "%s imports %s" % (path, a.name))
                        if a.name == "subprocess":
                            self.assertEqual(path, self.HELPER, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module, self.ALLOWED_IMPORTS | {"v2_run"}, "%s imports %s" % (path, node.module))
                    self.assertNotEqual(node.module, "subprocess", path)
                if not isinstance(node, ast.Attribute) or (isinstance(node.value, ast.Name) and node.value.id == "ast"):
                    continue
                if node.attr not in self.FORBIDDEN_ATTRS:
                    continue
                text = ast.unparse(node)
                if node.attr == "now":                    # the field of the injected clock and of the Setup, never datetime.now
                    self.assertIn(node.value.id if isinstance(node.value, ast.Name) else "", ("self", "setup", "clock"),
                                  "%s uses %s" % (path, text))
                elif node.attr == "urlopen":              # only the replacement of the real one by a function that fails
                    self.assertIn(path, self.URLOPEN_FILES, "%s uses %s" % (path, text))
                    self.assertEqual(text, "urllib.request.urlopen", path)
                elif node.attr == "environ":
                    self.assertIn(path, self.ENVIRON_FILES, "%s uses %s" % (path, text))
                    self.assertIn(text, ("os.environ", "os.environ.get"), path)
                else:
                    self.fail("%s uses .%s" % (path, node.attr))

    def test_subprocess_is_used_only_by_the_helper_for_git_version_bash_and_the_children(self):
        sources = self.own_sources()
        for path, tree in sources.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "subprocess":
                    self.assertEqual(path, self.HELPER)
        helpers = sources[self.HELPER]
        calls = sorted({ast.unparse(n.func) for n in ast.walk(helpers) if isinstance(n, ast.Call)
                        and ast.unparse(n.func).startswith("subprocess.")})
        self.assertEqual(calls, ["subprocess.Popen", "subprocess.run"])
        popen = [[ast.unparse(e) for e in n.args[0].elts] for n in ast.walk(helpers)
                 if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.Popen"]
        self.assertEqual(popen, [["sys.executable", "'-B'", "'-I'", "WORKER", "json.dumps(spec)"]])
        assigned = [ast.unparse(n.value) for n in helpers.body if isinstance(n, ast.Assign)
                    and ast.unparse(n.targets[0]) == "WORKER"]
        self.assertEqual(assigned, ["os.path.join(HERE, 's4e_worker.py')"])
        runs = [(fn.name, [ast.unparse(a) for a in n.args[0].elts][:2] if isinstance(n.args[0], ast.List) else None)
                for fn in ast.walk(helpers) if isinstance(fn, ast.FunctionDef)
                for n in ast.walk(fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.run"]
        self.assertEqual(sorted(name for name, _ in runs), ["git_version", "run_bash"])

    def test_git_is_started_only_through_the_helper_of_the_previous_stage(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    self.assertNotIn(ast.unparse(node.func), ("subprocess.check_output", "subprocess.call", "os.system",
                                                              "os.popen"), path)

    def test_files_are_opened_only_where_it_is_allowed_and_only_the_one_test_writes(self):
        for path, tree in self.own_sources().items():
            opens = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "open"]
            if opens:
                self.assertIn(path, self.OPEN_FILES)
            for call in opens:
                mode = ast.unparse(call.args[1]) if len(call.args) > 1 else "'r'"
                if mode == "'w'":
                    self.assertEqual(path, NEW_DIR + "test_s4e_12_record.py")
                else:
                    self.assertIn(mode, ("'rb'", "'r'"), path)
            for n in [n for n in tree.body if isinstance(n, (ast.Expr, ast.Assign))]:
                for sub in ast.walk(n):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        self.assertNotEqual(sub.func.id, "open", path)

    def test_the_tests_do_not_use_the_private_constructors_of_the_values_under_test(self):
        for path, tree in self.own_sources().items():
            if path.endswith("test_s4e_09_scope.py"):
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, ("_make", "_wrap", "_of", "from_dict", "_set"), path)

    def test_git_is_asked_only_through_the_read_only_helper_and_this_file_reads_no_working_tree(self):
        scope = self.own_sources()[NEW_DIR + "test_s4e_09_scope.py"]
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
