"""RATIO-07: the range of the ratio-emphasis change and its audits.

START is the code start (the accepted 2c7320f, the final commit of S4-E E-0). END is None until the next stage freezes it
with the accepted final commit (one line); REV is then the committed state under test. Everything is read from Git at REV
(or, for what this file says about itself, at HEAD): the working tree is not read, no earlier stage's diff is copied and
nothing is written. The two existing test files that this change had to touch (the END line of test_s4e_09_scope.py and one
name of the import list of test_s4a_08_static.py) are pinned below as the hunks of this change's own diff; the four
runtime files are named and the rest of the tree is blob-identical."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "2c7320fb138f3982cc20bb56e9e923a6a3d51638"
END = None          # not accepted yet; the next stage replaces None with the accepted final commit
REV = END or "HEAD"

NEW_DIR = "tests/v2_ratio/"
RESULT_DOC = "docs/implementation/V2_RATIO_EMPHASIS_RESULT.md"
RUNTIME_CHANGED = ("v2_core/display.py", "v2_daily_run/run.py", "v2_daily_run/values.py", "v2_notify/compose.py")
TESTS_CHANGED = ("tests/v2_daily_run/test_s4a_08_static.py", "tests/v2_run/test_s4e_09_scope.py")
CHANGED = RUNTIME_CHANGED + TESTS_CHANGED
NEW_FILES = ("ratio_cases.py", "golden_2c7320f.json", "real_20261119_2c7320f.txt")
PREVIOUS_RANGE = "tests/v2_run/test_s4e_09_scope.py"
FIRST_OF_CHAIN = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"

# The lines of the two existing test files that this change changed: `git diff --unified=0 START REV -- <path>`.
PINNED = {
    "tests/v2_daily_run/test_s4a_08_static.py": [
        ('-12', '+12', ['    "v2_core.display": {"render_message"},'],
         ['    "v2_core.display": {"ratio_headline", "render_message"},'])],
    "tests/v2_run/test_s4e_09_scope.py": [
        ('-19', '+19',
         ['END = None          # not accepted yet; the next stage replaces None with the accepted final commit'],
         ['END = "2c7320fb138f3982cc20bb56e9e923a6a3d51638"   # accepted (receipt 34a2ed4); frozen when the ratio emphasis began'])],
}


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name
            and (name in NEW_FILES or (name.startswith("test_ratio_") and name.endswith(".py"))))


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
    return hunks


class PathJudgement(unittest.TestCase):
    def test_which_new_paths_are_allowed(self):
        for name in NEW_FILES + ("test_ratio_01_texts.py", "test_ratio_02_scope.py"):
            self.assertTrue(allowed_new_path(NEW_DIR + name), name)
        self.assertTrue(allowed_new_path(RESULT_DOC))
        for path in (NEW_DIR + "__init__.py", NEW_DIR + "other.py", NEW_DIR + "sub/test_ratio_x.py",
                     "tests/v2_run/test_s4e_14_x.py", "v2_run/sixth.py", "v2_ratio/__init__.py",
                     ".github/workflows/v2_morning.yml", "docs/ops/OTHER.md", "docs/implementation/V2_RUN_S4E_RESULT.md"):
            self.assertFalse(allowed_new_path(path), path)

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
    """RATIO-07: compared with the code start by Git (committed state)."""

    def changed(self):
        out = C.git("diff", "--name-status", START, REV)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)               # no rename or copy
        return rows

    def test_exactly_the_six_files_are_modified_and_the_additions_are_allowed_paths(self):
        rows = self.changed()
        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(CHANGED))
        for status, path in rows:
            self.assertIn(status, ("M", "A"), "%s %s" % (status, path))
            if status == "A":
                self.assertTrue(allowed_new_path(path), path)
        added = {p for s, p in rows if s == "A"}
        for name in NEW_FILES:
            self.assertIn(NEW_DIR + name, added)
        self.assertTrue(any(p.startswith(NEW_DIR + "test_ratio_") for p in added))

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

    def test_the_entry_the_workflow_the_main_and_the_dependencies_are_untouched(self):
        for path in ("main.py", "v2_run/__init__.py", "v2_run/__main__.py", "v2_run/check.py", "v2_run/entry.py",
                     "v2_run/web.py", "v2_notify/job.py", "v2_notify/outbox.py", "v2_notify/values.py",
                     "v2_core/engine.py", "v2_core/transition.py", "docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.yml",
                     "CLAUDE.md", "requirements.txt"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
        self.assertEqual(C.list_files(REV, ".github"), C.list_files(START, ".github"))

    def test_the_two_modified_test_files_are_exactly_the_pinned_hunks(self):
        for path in TESTS_CHANGED:
            out = C.git("diff", "--unified=0", START, REV, "--", path)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in PINNED[path]], path)

    def test_the_ratio_never_comes_from_a_written_in_number_in_the_runtime(self):
        text = C.show(REV, "v2_core/display.py")
        tree = ast.parse(text)
        names = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ("ratio_emphasis", "ratio_headline", "ratio_line"):
            self.assertIn(name, names)
            numbers = [n.value for n in ast.walk(names[name]) if isinstance(n, ast.Constant)
                       and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)]
            self.assertFalse(set(numbers) & {25, 100}, name)      # no written-in ratio in the code that makes the lines
            text_of_function = ast.get_source_segment(text, names[name])
            self.assertNotIn("RATIO_", text_of_function.replace("RATIO_SIGNAL_CLASSES", ""), name)
            attrs = {n.attr for n in ast.walk(names[name]) if isinstance(n, ast.Attribute)}
            if name != "ratio_emphasis":
                self.assertIn("ratio", attrs, name)


class Chain(Base):
    """RATIO-07: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], [PREVIOUS_RANGE])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_ratio_02_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin=FIRST_OF_CHAIN), [])
        self.assertGreaterEqual(len(rows), 14)
        starts = [r["start"] for r in rows]
        self.assertEqual(starts.count(START), 1)
        self.assertIn("9bdd4217d18e0ac328ddfa6a76b5d2a82748549d", starts)

    def test_the_previous_range_is_frozen_at_the_code_start_by_the_changed_line(self):
        tree = ast.parse(C.show(REV, PREVIOUS_RANGE))
        directory = os.path.dirname(PREVIOUS_RANGE)
        self.assertEqual(C.read_constant(tree, "END", directory, REV), (True, START))
        self.assertEqual(C.read_constant(tree, "START", directory, REV),
                         (True, "9bdd4217d18e0ac328ddfa6a76b5d2a82748549d"))

    def test_the_range_values_of_this_file_are_read_from_the_text_at_head(self):
        # HEAD, not REV: once the next stage freezes END, REV is the commit that holds END = None
        path = NEW_DIR + "test_ratio_02_scope.py"
        tree = ast.parse(C.show("HEAD", path))
        self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), "HEAD"), (True, START))
        self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), "HEAD"), (True, END))
        self.assertIn("FilesChanged", C.top_level(tree))


class TestFiles(Base):
    """RATIO-07: what the new tests may do: read Git and the sources, never the clock, a socket, a process or a write."""

    ALLOWED_IMPORTS = {"ast", "dataclasses", "datetime", "json", "os", "sys", "unittest", "ratio_cases", "s4b_helpers",
                       "v2_helpers", "v2_daily_run", "v2_notify", "sc_helpers", "v2_core", "v2_core.display",
                       "v2_core.engine", "v2_core.state", "v2_core.tri", "v2_run.web"}
    FORBIDDEN_ATTRS = {"getenv", "putenv", "environ", "urandom", "sleep", "system", "popen", "urlopen", "connect",
                       "monotonic", "utcnow", "today", "now", "Popen", "write", "mkdir", "unlink", "rename", "rmtree"}

    def sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 3)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def test_the_own_files_are_the_allowed_ones_and_there_is_no_init_file(self):
        names = [p.rsplit("/", 1)[1] for p in C.list_files(REV, NEW_DIR.rstrip("/"))]
        self.assertNotIn("__init__.py", names)
        for path in C.list_files(REV, NEW_DIR.rstrip("/")):
            self.assertTrue(allowed_new_path(path), path)

    def test_imports_and_the_absence_of_clock_network_process_and_writes(self):
        for path, tree in self.sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, self.ALLOWED_IMPORTS, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module, self.ALLOWED_IMPORTS | {"datetime", "decimal", "v2_core.engine",
                                                                       "v2_core.state", "v2_core.tri"},
                                  "%s imports %s" % (path, node.module))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ("eval", "exec", "compile", "__import__", "input", "print"), path)
                    if node.func.id == "open":
                        mode = ast.unparse(node.args[1]) if len(node.args) > 1 else "'r'"
                        self.assertEqual(mode, "'r'", path)
                if isinstance(node, ast.Attribute) and node.attr in self.FORBIDDEN_ATTRS:
                    if node.attr == "now" and isinstance(node.value, ast.Name) and node.value.id in ("self", "setup"):
                        continue
                    self.fail("%s uses .%s" % (path, node.attr))

    def test_git_is_asked_only_through_the_read_only_helper(self):
        scope = self.sources()[NEW_DIR + "test_ratio_02_scope.py"]
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "git" \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "C":
                self.assertTrue(node.args and isinstance(node.args[0], ast.Constant))
                self.assertIn(node.args[0].value, C.READ_ONLY_GIT)

    def test_the_tests_leave_no_bytecode_or_log_to_add(self):
        out = C.git("diff", "--name-only", START, REV)
        self.assertEqual([p for p in out.stdout.split() if "__pycache__" in p or p.endswith((".pyc", ".log"))], [])


if __name__ == "__main__":
    unittest.main()
