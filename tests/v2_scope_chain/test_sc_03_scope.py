"""SC-03: the range of this stage and its side-effect audit.

START is the code start of this stage. END is None until the next stage freezes it with the accepted final commit
(one line); REV is then the committed state under test. Everything is read from Git at REV; the working tree is not
read, no previous stage's diff is copied, and nothing is written.
"""
import ast
import unittest

import sc_helpers as C

START = "b626c98af5f01bc94e7b41d86aadde9663695eb9"
END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"   # accepted (re-review 9fe3e19); frozen when C-1 began
REV = END or "HEAD"

FIVE = ("tests/v2_history_adopt/test_a5_08_scope.py", "tests/v2_history_diagnose/test_d5_08_scope.py",
        "tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py",
        "tests/v2_history_restore/test_r4_09_scope.py")
NEW_DIR = "tests/v2_scope_chain/"
RESULT_DOC = "docs/implementation/V2_SCOPE_RANGE_FREEZE_RESULT.md"
UNCHANGED_ROOTS = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                   "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "main.py", "research", "docs",
                   "CLAUDE.md", "README.md", ".github", "requirements.txt")


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name == "sc_helpers.py" or name.startswith("test_sc_")))


class PathJudgement(unittest.TestCase):
    def test_which_new_paths_are_allowed(self):
        self.assertTrue(allowed_new_path("tests/v2_scope_chain/test_sc_01_freeze.py"))
        self.assertTrue(allowed_new_path("tests/v2_scope_chain/sc_helpers.py"))
        self.assertTrue(allowed_new_path(RESULT_DOC))
        self.assertFalse(allowed_new_path("tests/v2_scope_chain/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_scope_chain/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_scope_chain/sub/test_sc_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_adopt/test_a5_10.py"))
        self.assertFalse(allowed_new_path("v2_history_adopt/new.py"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))


class FilesChanged(unittest.TestCase):
    """Compared with the code start by Git (committed state)."""

    def setUp(self):
        probe = C.git("cat-file", "-e", START + "^{commit}")
        if probe.returncode == 0:
            probe = C.git("cat-file", "-e", REV + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")

    def changed(self):
        out = C.git("diff", "--name-status", START, REV)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)               # no rename or copy
        return rows

    def test_exactly_the_five_range_tests_are_modified_and_the_only_additions_are_allowed_paths(self):
        rows = self.changed()
        modified = sorted(p for s, p in rows if s == "M")
        self.assertEqual(modified, sorted(FIVE))
        self.assertEqual(len(modified), 5)
        for status, path in rows:
            self.assertIn(status, ("M", "A"), "%s %s" % (status, path))
            if status == "A":
                self.assertTrue(allowed_new_path(path), path)
        added = {p for s, p in rows if s == "A"}
        self.assertTrue(any(p.startswith(NEW_DIR + "test_sc_") for p in added))

    def test_everything_else_is_blob_identical_to_the_code_start(self):
        out = C.git("diff", "--name-only", START, REV, "--", *UNCHANGED_ROOTS)
        self.assertEqual(set(out.stdout.split()) - {RESULT_DOC}, set())
        start_tree = C.git("ls-tree", "-r", START)
        rev_tree = C.git("ls-tree", "-r", REV)
        self.assertEqual(start_tree.returncode, 0)
        self.assertEqual(rev_tree.returncode, 0)

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
            if path in FIVE:
                self.assertNotEqual(after[path], row, path)
                continue
            self.assertEqual(after[path], row, path)
            compared += 1
        self.assertGreater(compared, 300)
        for path in set(after) - set(before):
            self.assertTrue(allowed_new_path(path), path)

    def test_no_runtime_functional_test_helper_or_old_result_changes(self):
        for root in ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                     "v2_history_restore", "v2_history_diagnose", "v2_history_adopt"):
            out = C.git("diff", "--name-only", START, REV, "--", root)
            self.assertEqual(out.stdout.strip(), "", root)
        out = C.git("diff", "--name-only", START, REV, "--", "tests", *[":(exclude)%s" % p for p in FIVE],
                    ":(exclude)tests/v2_scope_chain")
        self.assertEqual(out.stdout.strip(), "")
        out = C.git("diff", "--name-only", START, REV, "--", "docs", ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")
        out = C.git("diff", "--name-only", START, REV, "--", "docs/implementation", ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")


ALLOWED_IMPORTS = {"ast", "copy", "difflib", "os", "socket", "subprocess", "unittest", "sc_helpers", "test_sc_03_scope"}
FORBIDDEN_NAMES = {"open", "eval", "exec", "compile", "__import__", "input", "print"}
FORBIDDEN_ATTRS = {"write", "write_text", "write_bytes", "mkdir", "makedirs", "remove", "unlink", "rename", "replace",
                   "rmtree", "copy", "copytree", "move", "urandom", "random", "randint", "choice", "seed", "time",
                   "monotonic", "perf_counter", "sleep", "now", "today", "utcnow", "getenv", "environ", "system",
                   "popen", "Popen", "walk", "listdir", "scandir", "glob", "isfile", "isdir", "exists", "read_text",
                   "read_bytes", "connect", "urlopen", "getaddrinfo", "gethostbyname"}


class SideEffects(unittest.TestCase):
    """F-10: the new tests use Git and the parsed text only."""

    def setUp(self):
        if C.git("cat-file", "-e", REV + "^{commit}").returncode != 0:
            self.skipTest("the revision under test is not available in this checkout")

    def own_sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 4)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def test_the_own_files_are_the_allowed_ones(self):
        for path in self.own_sources():
            self.assertTrue(allowed_new_path(path), path)

    def test_only_allowed_imports_and_no_io_clock_random_or_network(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, ALLOWED_IMPORTS, path)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, ALLOWED_IMPORTS, path)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_NAMES, path)
                if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name)
                                                            and node.value.id == "ast"):       # ast.walk is not os.walk
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, path)

    def test_every_git_call_is_a_read_only_subcommand(self):
        calls = 0
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "git" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "C":
                    self.assertTrue(node.args and isinstance(node.args[0], ast.Constant), path)
                    self.assertIn(node.args[0].value, C.READ_ONLY_GIT, path)
                    calls += 1
        self.assertGreater(calls, 10)
        self.assertEqual(sorted(C.READ_ONLY_GIT), sorted(["cat-file", "diff", "ls-tree", "merge-base", "rev-parse",
                                                         "show"]))

    def test_the_only_process_is_git_in_the_helper(self):
        for path, tree in self.own_sources().items():
            runs = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "run"
                    and isinstance(n.value, ast.Name) and n.value.id == "subprocess"]
            if path.endswith("sc_helpers.py"):
                self.assertEqual(len(runs), 1)
            else:
                self.assertEqual(runs, [], path)

    def test_no_init_file_and_os_is_used_only_for_path_names(self):
        names = [p.rsplit("/", 1)[1] for p in C.list_files(REV, NEW_DIR.rstrip("/"))]
        self.assertNotIn("__init__.py", names)
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                        and isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                    self.assertEqual(node.value.attr, "path", path)
                    self.assertIn(node.attr, ("abspath", "dirname", "join", "basename"), path)
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertEqual(node.attr, "path", path)


if __name__ == "__main__":
    unittest.main()
