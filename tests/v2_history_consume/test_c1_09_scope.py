"""C1-15 .. C1-18: the range of stage C-1 and its audits.

START is the code start of this stage (the accepted bfbde7a). END is None until the next stage freezes it with the
accepted final commit (one line); REV is then the committed state under test. Everything is read from Git at REV; the
working tree is not read, no earlier stage's diff is copied, and nothing is written. The four existing tests that this
stage had to correct are pinned below as the lines and hunks of this stage's own diff."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "bfbde7a7854bf91a77fb58737c24b19c6507453a"
END = None          # not accepted yet; the next stage replaces None with the accepted final commit
REV = END or "HEAD"

RUNTIME = ("v2_history/restore.py", "v2_history_restore/__init__.py", "v2_history_restore/build.py",
           "v2_history_restore/confirm.py", "v2_history_restore/errors.py", "v2_history_restore/market.py",
           "v2_history_restore/points.py", "v2_history_restore/records.py", "v2_history_restore/values.py")
FOUR = ("tests/v2_history/test_h06_restore_batch.py", "tests/v2_history_restore/test_r4_01_point_ops.py",
        "tests/v2_history_restore/test_r4_09_scope.py", "tests/v2_scope_chain/test_sc_03_scope.py")
NEW_DIR = "tests/v2_history_consume/"
RESULT_DOC = "docs/implementation/V2_CONSUME_C1_RESULT.md"
PACKAGE = "v2_history_restore"
ROOTS = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
         "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "main.py", "research", "docs", "CLAUDE.md",
         "README.md", ".github", "requirements.txt")

# The four existing tests that the stage corrected (C1-17): file -> hunks of `git diff --unified=0 START REV`, each as
# (old range, new range, removed lines, added lines). The fifth changed test, test_sc_03_scope.py, is the one-line freeze.
PINNED = {'tests/v2_history/test_h06_restore_batch.py': [('-163',
                                                 '+163',
                                                 ['    def test_consume_is_not_supported_in_b1(self):'],
                                                 ['    def test_a_consume_entry_of_the_wrong_form_is_refused(self):']),
                                                ('-166',
                                                 '+166',
                                                 ['        H.expect_rule(self, "restore_op_unsupported", '
                                                  'H.rebuild_edit(self.ev, 7, fn))'],
                                                 ['        H.expect_rule(self, "restore_replay_mismatch", '
                                                  'H.rebuild_edit(self.ev, 7, fn))']),
                                                ('-169',
                                                 '+169',
                                                 ['        H.expect_rule(self, "restore_op_unsupported", '
                                                  'H.rebuild_edit(self.ev, 7, fn2))'],
                                                 ['        H.expect_rule(self, "restore_replay_mismatch", '
                                                  'H.rebuild_edit(self.ev, 7, fn2))'])],
 'tests/v2_history_restore/test_r4_01_point_ops.py': [('-145,2',
                                                       '+145,3',
                                                       ['        self.bad([{"op": "DROP", "from_seq": 2}, {"op": '
                                                        '"CONSUME", "from_seq": 3}], unsupported)',
                                                        '        self.bad([{"op": "DROP", "from_seq": 2}, {"op": '
                                                        '"CONSUME", "d": D[2]}], unsupported)'],
                                                       ['        # C-1: CONSUME takes {op, d} only and names no '
                                                        'superseded record',
                                                        '        self.bad([{"op": "DROP", "from_seq": 2}, {"op": '
                                                        '"CONSUME", "from_seq": 3}], ("ops", "ops_shape"))',
                                                        '        self.bad([{"op": "DROP", "from_seq": 2}, {"op": '
                                                        '"CONSUME", "d": D[2]}], ("ops", "superseded_mismatch"))'])],
 'tests/v2_history_restore/test_r4_09_scope.py': [('-30',
                                                   '+30',
                                                   ['    "v2_persistence.events": {"session_dict", "row_dict", '
                                                    '"input_hash_of", "serialize_transition"},'],
                                                   ['    "v2_persistence.events": {"session_dict", "row_dict", '
                                                    '"input_hash_of", "serialize_transition", "decision_dict"},']),
                                                  ('-58',
                                                   '+58,7',
                                                   ['CONSUME_NAMES = {"requires_consume", "restore_requires_consume"}'],
                                                   ['CONSUME_NAMES = {"requires_consume", "restore_requires_consume",',
                                                    '                 # C-1 (a new APPLY for a day the operations set '
                                                    'free): the fixed list of the names that hold the word',
                                                    '                 "CONSUME", "CONSUME_KEYS", "consume_inputs", '
                                                    '"consumed", "consumed_since", "_consume", "_consume_inputs",',
                                                    '                 "_check_consumed_decisions", '
                                                    '"_check_consumed_released", "_check_consumes", "_has_consume",',
                                                    '                 "restore_consume_applied_day",',
                                                    '                 "restore_consume_duplicate", '
                                                    '"restore_consume_in_batch", "restore_consume_input",',
                                                    '                 "restore_consume_no_decision", '
                                                    '"restore_consume_not_released", "restore_consume_order"}']),
                                                  ('-228',
                                                   '+234,2',
                                                   ['        # the one function that raises it and the one place that '
                                                    'calls it, and nothing that makes a day of its own'],
                                                   ['        # the stop of a freed day that is not consumed is still '
                                                    'there, and the names of the consumption are the fixed list',
                                                    '        self.assertTrue({"requires_consume", '
                                                    '"restore_requires_consume"} <= set(v for _f, v in found))']),
                                                  ('-230',
                                                   '+236,0',
                                                   ['        self.assertEqual(sorted(set(f for f, _v in found)), '
                                                    '["build.py", "errors.py"])'],
                                                   []),
                                                  ('-245',
                                                   '+251',
                                                   ['        self.assertEqual([(f, n) for f, n, _d, _fn in sites], '
                                                    '[("records.py", "_reapply")])'],
                                                   ['        self.assertEqual([(f, n) for f, n, _d, _fn in sites], '
                                                    '[("records.py", "_reapply"), ("records.py", "_consume")])']),
                                                  ('-291',
                                                   '+297',
                                                   ['        for op, rule in (("CONSUME", "restore_op_unsupported"), '
                                                    '("consume", "restore_op_unsupported"),'],
                                                   ['        for op, rule in (("CONSUME", "ops_shape"), ("consume", '
                                                    '"restore_op_unsupported"),'])]}


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name == "c1_helpers.py" or name.startswith("test_c1_")))


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
        self.assertTrue(allowed_new_path("tests/v2_history_consume/test_c1_01_checker.py"))
        self.assertTrue(allowed_new_path("tests/v2_history_consume/c1_helpers.py"))
        self.assertTrue(allowed_new_path(RESULT_DOC))
        self.assertFalse(allowed_new_path("tests/v2_history_consume/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_consume/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_consume/sub/test_c1_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_restore/test_r4_11.py"))
        self.assertFalse(allowed_new_path("v2_history_restore/new.py"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_SCOPE_RANGE_FREEZE_RESULT.md"))

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
    """C1-17: compared with the code start by Git (committed state)."""

    def changed(self):
        out = C.git("diff", "--name-status", START, REV)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)               # no rename or copy
        return rows

    def test_exactly_the_runtime_files_and_the_five_tests_are_modified_and_the_additions_are_allowed_paths(self):
        rows = self.changed()
        modified = sorted(p for s, p in rows if s == "M")
        self.assertEqual(modified, sorted(RUNTIME + FOUR))
        for status, path in rows:
            self.assertIn(status, ("M", "A"), "%s %s" % (status, path))
            if status == "A":
                self.assertTrue(allowed_new_path(path), path)
        added = {p for s, p in rows if s == "A"}
        self.assertTrue(any(p.startswith(NEW_DIR + "test_c1_") for p in added))
        self.assertIn(NEW_DIR + "c1_helpers.py", added)

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
            if path in RUNTIME or path in FOUR:
                self.assertNotEqual(after[path], row, path)
                continue
            self.assertEqual(after[path], row, path)
            compared += 1
        self.assertGreater(compared, 300)
        for path in set(after) - set(before):
            self.assertTrue(allowed_new_path(path), path)

    def test_the_package_keeps_its_files_and_the_untouched_runtime_is_untouched(self):
        names = lambda rev: sorted(p for p in C.list_files(rev, PACKAGE) if p.endswith(".py"))        # noqa: E731
        self.assertEqual(names(REV), names(START))
        self.assertEqual(len(names(REV)), 10)
        for root in ("v2_core", "v2_persistence", "v2_recovery", "v2_history_ops", "v2_history_restart",
                     "v2_history_diagnose", "v2_history_adopt"):
            out = C.git("diff", "--name-only", START, REV, "--", root)
            self.assertEqual(out.stdout.strip(), "", root)
        out = C.git("diff", "--name-only", START, REV, "--", "v2_history", ":(exclude)v2_history/restore.py")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("v2_history_restore/chain.py", "v2_history_restore/prepare.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
        out = C.git("diff", "--name-only", START, REV, "--", *ROOTS[8:], ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")

    def test_the_helpers_and_the_other_tests_are_not_changed(self):
        out = C.git("diff", "--name-only", START, REV, "--", "tests", *[":(exclude)%s" % p for p in FOUR],
                    ":(exclude)tests/v2_history_consume")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("tests/v2_history/h_helpers.py", "tests/v2_history_ops/ho_helpers.py",
                     "tests/v2_history_restore/r4_helpers.py", "tests/v2_scope_chain/sc_helpers.py",
                     "tests/v2_scope_chain/test_sc_01_freeze.py", "tests/v2_scope_chain/test_sc_02_chain.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
        out = C.git("diff", "--name-only", START, REV, "--", "docs", ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")

    def test_the_four_corrected_tests_are_the_pinned_hunks(self):
        for path, expected in PINNED.items():
            out = C.git("diff", "--unified=0", START, REV, "--", path)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in expected], path)
        self.assertEqual(sorted(PINNED), sorted(f for f in FOUR if "sc_03" not in f))

    def test_the_freeze_of_the_previous_range_is_one_line(self):
        path = "tests/v2_scope_chain/test_sc_03_scope.py"
        out = C.git("diff", "--unified=0", START, REV, "--", path)
        hunks = parse_hunks(out.stdout)
        self.assertEqual(len(hunks), 1)
        self.assertEqual(hunks[0][2:], (['END = None          # not accepted yet; the next stage replaces None with the '
                                         'accepted final commit'],
                                        ['END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"   # accepted (re-review 9fe3e19); '
                                         'frozen when C-1 began']))
        tree = ast.parse(C.show(REV, path))
        found, end = C.read_constant(tree, "END", "tests/v2_scope_chain", REV)
        self.assertEqual((found, end), (True, START))


class Chain(Base):
    """C1-16: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], ["tests/v2_scope_chain/test_sc_03_scope.py"])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_c1_09_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin="adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"), [])
        self.assertGreaterEqual(len(rows), 7)

    def test_the_range_values_of_this_file_are_those_read_from_the_text(self):
        tree = ast.parse(C.show(REV, NEW_DIR + "test_c1_09_scope.py"))
        self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), REV), (True, START))
        self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), REV), (True, END))
        self.assertIn("FilesChanged", C.top_level(tree))


def imports_of(tree):
    """{(module, name)} of the from-imports and {module} of the plain imports."""
    pairs, plain = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                pairs.add(('.' * node.level + (node.module or ''), a.name))
        elif isinstance(node, ast.Import):
            plain.update(a.name for a in node.names)
    return pairs, plain


FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "hashlib", "uuid", "webbrowser", "smtplib",
                     "datetime", "tests"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen", "sha256", "md5", "sha1", "blake2b"}
# the names that the stage brings into the runtime (everything else that is imported is what bfbde7a imported)
NEW_IMPORTS = {
    "v2_history/restore.py": set(),
    "v2_history_restore/errors.py": set(),
    "v2_history_restore/records.py": {("v2_persistence.events", "decision_dict"), (".values", "CONSUME")},
    "v2_history_restore/build.py": {(".market", "fixed_days"), (".values", "CONSUME")},
    "v2_history_restore/market.py": {(".values", "CONSUME"), (".values", "REAPPLY")},
    "v2_history_restore/points.py": {("v2_history.common", "is_date"), (".values", "CONSUME"),
                                     (".values", "CONSUME_KEYS")},
    "v2_history_restore/confirm.py": {(".market", "fixed_days"), (".values", "CONSUME"), (".values", "CONSUME_KEYS")},
    "v2_history_restore/values.py": set(),
    "v2_history_restore/__init__.py": set(),
}


class RuntimeAudit(Base):
    """C1-18: the changed runtime reads and writes nothing, uses no clock, no randomness, no network, no thread, no
    environment variable and no hash function of its own, and brings in no dependency and no public name."""

    def trees(self):
        return {p: (ast.parse(C.show(START, p)), ast.parse(C.show(REV, p))) for p in RUNTIME}

    def test_no_forbidden_import_call_or_attribute(self):
        for path, (_old, new) in self.trees().items():
            pairs, plain = imports_of(new)
            for module in plain | {m for m, _n in pairs if m}:
                self.assertNotIn(module.split(".")[0], FORBIDDEN_IMPORTS, path)
            for node in ast.walk(new):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, path)

    def test_the_imports_are_those_of_the_code_start_and_the_listed_new_names(self):
        for path, (old, new) in self.trees().items():
            old_pairs, old_plain = imports_of(old)
            new_pairs, new_plain = imports_of(new)
            self.assertEqual(new_plain, old_plain, path)
            self.assertEqual({m for m, _n in new_pairs} - {m for m, _n in old_pairs} - {m for m, _n in NEW_IMPORTS[path]},
                             set(), path)
            self.assertEqual(new_pairs - old_pairs, NEW_IMPORTS[path], path)

    def test_no_dependency_file_and_no_new_public_name(self):
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertEqual(C.blob_id(REV, name), C.blob_id(START, name), name)
        for path in ("v2_history/__init__.py", "v2_history_restore/__init__.py"):
            old, new = ast.parse(C.show(START, path)), ast.parse(C.show(REV, path))
            self.assertEqual(ast.dump(C.top_level(new)["__all__"]), ast.dump(C.top_level(old)["__all__"]), path)
        self.assertEqual(C.blob_id(REV, "v2_history/__init__.py"), C.blob_id(START, "v2_history/__init__.py"))
        names = {p: ast.parse(C.show(REV, p)) for p in RUNTIME}
        for path, tree in names.items():
            for node in tree.body:                                 # nothing is exported by a new top-level name
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__"
                                                        for t in node.targets):
                    self.assertTrue(path.endswith("__init__.py"), path)

    def test_the_kinds_and_the_named_operations_are_unchanged(self):
        import v2_history
        from v2_history_restore import values
        self.assertEqual(len(v2_history.values.KINDS), 8)
        self.assertEqual(values.OPS, ("REAPPLY", "REPLAY", "DROP", "RETIRE"))
        text = C.show(REV, "v2_history/values.py")
        self.assertEqual(text, C.show(START, "v2_history/values.py"))


class SideEffects(Base):
    """C1-18: the new tests read Git and the parsed text only, and the stage's own files are the allowed ones."""

    ALLOWED_IMPORTS = {"ast", "importlib", "importlib.abc", "importlib.util", "os", "sys", "unittest", "unittest.mock",
                       "mock", "copy", "c1_helpers", "sc_helpers", "r4_helpers", "test_c1_09_scope"}
    FORBIDDEN_NAMES = {"open", "eval", "input", "__import__", "print", "breakpoint"}
    FORBIDDEN_ATTRS = {"write", "write_text", "write_bytes", "mkdir", "makedirs", "remove", "unlink", "rename", "replace",
                       "rmtree", "copytree", "move", "urandom", "random", "randint", "choice", "seed", "time",
                       "monotonic", "perf_counter", "sleep", "now", "today", "utcnow", "getenv", "environ", "system",
                       "popen", "Popen", "run", "walk", "listdir", "scandir", "glob", "isfile", "isdir", "exists",
                       "read_text", "read_bytes", "connect", "urlopen", "getaddrinfo", "gethostbyname", "chdir",
                       "putenv", "setdefault"}

    def own_sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 6)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def test_the_own_files_are_the_allowed_ones_and_there_is_no_init_file(self):
        names = [p.rsplit("/", 1)[1] for p in C.list_files(REV, NEW_DIR.rstrip("/"))]
        self.assertNotIn("__init__.py", names)
        for path in self.own_sources():
            self.assertTrue(allowed_new_path(path), path)

    def test_only_allowed_imports_and_no_io_clock_random_or_network(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertTrue(a.name in self.ALLOWED_IMPORTS or a.name.split(".")[0].startswith("v2_"),
                                        "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    root = node.module.split(".")[0]
                    self.assertTrue(node.module in self.ALLOWED_IMPORTS or root.startswith("v2_") or root == "unittest",
                                    "%s imports %s" % (path, node.module))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, self.FORBIDDEN_NAMES, path)
                if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "ast"):
                    if node.attr == "remove" and ast.unparse(node.value) == "sys.meta_path":
                        continue                                   # the list method, for the Git-loaded old package
                    self.assertNotIn(node.attr, self.FORBIDDEN_ATTRS, path)

    def test_the_tests_start_no_process_and_git_is_asked_only_through_the_read_only_helper(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    self.assertNotEqual(node.value.id, "subprocess", path)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "git" \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "C":
                    self.assertTrue(node.args and isinstance(node.args[0], ast.Constant), path)
                    self.assertIn(node.args[0].value, C.READ_ONLY_GIT, path)

    def test_os_is_used_only_for_path_names(self):
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                        and isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                    self.assertEqual(node.value.attr, "path", path)
                    self.assertIn(node.attr, ("abspath", "dirname", "join"), path)
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertEqual(node.attr, "path", path)

    def test_the_tests_leave_no_bytecode_or_file_to_add(self):
        # nothing in the range is a cache file (git add of a __pycache__ would show up as an added path)
        out = C.git("diff", "--name-only", START, REV)
        self.assertEqual([p for p in out.stdout.split() if "__pycache__" in p or p.endswith((".pyc", ".log"))], [])


class P02(Base):
    """C1-15: the restore package neither imports the adoption and diagnosis packages nor reads their fields."""

    BANNED_IMPORT_ROOTS = ("v2_history_adopt", "v2_history_diagnose")
    BANNED_WORDS = ("discarded", "diagnos")
    # the one name of the package that holds the word and is older than the stage: B-4's re-check of the commands of a
    # replayed request (build._replay_evidence, spied on by the B-4 tests)
    OLD_EVIDENCE_NAMES = {"_replay_evidence"}

    def package(self):
        paths = [p for p in C.list_files(REV, PACKAGE) if p.endswith(".py")]
        self.assertEqual(len(paths), 10)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def words(self, tree):
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                    docs.add(id(first.value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                yield node.id
            elif isinstance(node, ast.Attribute):
                yield node.attr
            elif isinstance(node, ast.alias):
                yield node.name
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                yield node.name
            elif isinstance(node, ast.arg):
                yield node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                yield node.value

    def test_no_import_of_the_adoption_or_diagnosis_packages(self):
        for path, tree in self.package().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(self.BANNED_IMPORT_ROOTS), path)
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertFalse(a.name.startswith(self.BANNED_IMPORT_ROOTS), path)

    def test_no_name_or_string_of_the_adoption_evidence_or_the_discarded_part(self):
        seen_evidence = set()
        for path, tree in self.package().items():
            for word in self.words(tree):
                low = word.lower()
                for banned in self.BANNED_WORDS:
                    self.assertNotIn(banned, low, "%s: %s" % (path, word))
                if "evidence" in low:
                    seen_evidence.add(word)
                    self.assertIn(word, self.OLD_EVIDENCE_NAMES, "%s: %s" % (path, word))
        self.assertEqual(seen_evidence, self.OLD_EVIDENCE_NAMES)
        # and the old name is the one of bfbde7a, not a new use of the word
        old = set()
        for p in (p for p in C.list_files(START, PACKAGE) if p.endswith(".py")):
            old.update(w for w in self.words(ast.parse(C.show(START, p))) if "evidence" in w.lower())
        self.assertEqual(old, self.OLD_EVIDENCE_NAMES)

    def test_the_package_reads_no_record_of_the_adoption(self):
        for path, tree in self.package().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn("PREFIX_ADOPTION", node.value, path)
                    self.assertNotIn("adoption", node.value.lower() if node.value != "restore_before_adoption" else "", path)


if __name__ == "__main__":
    unittest.main()
