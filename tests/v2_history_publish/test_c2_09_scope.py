"""C2-15 .. C2-18: the range of stage C-2 and its audits.

START is the code start of this stage (the accepted de6549a, the final commit of C-1). END is None until the next stage
freezes it with the accepted final commit (one line); REV is then the committed state under test. Everything is read from
Git at REV (or, for the one question of what this file says about itself, at HEAD): the working tree is not read, no
earlier stage's diff is copied, and nothing is written. The two lines of test_c1_09_scope.py that this stage had to
change are pinned below as the hunks of this stage's own diff."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "de6549acb4ecea759cc771300fd0bef59dd5456a"
END = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"   # accepted (review a91a9ed); frozen when C-3 began
REV = END or "HEAD"

PACKAGE = "v2_history_publish"
RUNTIME = tuple("v2_history_publish/%s.py" % n for n in ("__init__", "build", "check", "errors", "read", "values"))
NEW_DIR = "tests/v2_history_publish/"
RESULT_DOC = "docs/implementation/V2_HISTORY_PUBLISH_C2_RESULT.md"
CHANGED_TEST = "tests/v2_history_consume/test_c1_09_scope.py"
OLD_PACKAGES = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                "v2_history_restore", "v2_history_diagnose", "v2_history_adopt")
ROOTS = OLD_PACKAGES + ("main.py", "research", "docs", "CLAUDE.md", "README.md", ".github", "requirements.txt")
FIRST_OF_CHAIN = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"

# The two lines of the previous stage's range test that this stage changed (C2-16): `git diff --unified=0 START REV`.
PINNED = [('-17', '+17',
           ['END = None          # not accepted yet; the next stage replaces None with the accepted final commit'],
           ['END = "de6549acb4ecea759cc771300fd0bef59dd5456a"   # accepted (review b473db4); frozen when C-2 began']),
          ('-274', '+274',
           ['        tree = ast.parse(C.show(REV, NEW_DIR + "test_c1_09_scope.py"))'],
           ['        tree = ast.parse(C.show("HEAD", NEW_DIR + "test_c1_09_scope.py"))   '
            '# HEAD: the frozen END is read as written'])]


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    if path in RUNTIME:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name == "c2_helpers.py" or name.startswith("test_c2_")))


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
        self.assertTrue(allowed_new_path("tests/v2_history_publish/test_c2_01_values_bytes.py"))
        self.assertTrue(allowed_new_path("tests/v2_history_publish/c2_helpers.py"))
        self.assertTrue(allowed_new_path("v2_history_publish/check.py"))
        self.assertTrue(allowed_new_path(RESULT_DOC))
        self.assertFalse(allowed_new_path("tests/v2_history_publish/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_publish/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_publish/sub/test_c2_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_consume/test_c1_10.py"))
        self.assertFalse(allowed_new_path("v2_history_publish/seventh.py"))
        self.assertFalse(allowed_new_path("v2_history_ops/new.py"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_CONSUME_C1_RESULT.md"))

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
    """C2-17: compared with the code start by Git (committed state)."""

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
        self.assertTrue(any(p.startswith(NEW_DIR + "test_c2_") for p in added))
        self.assertIn(NEW_DIR + "c2_helpers.py", added)
        self.assertLessEqual(len([p for p in added if p.startswith(PACKAGE + "/")]), 7)

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
                    ":(exclude)tests/v2_history_publish")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("tests/v2_history/h_helpers.py", "tests/v2_history_ops/ho_helpers.py",
                     "tests/v2_history_restart/r3_helpers.py", "tests/v2_history_restore/r4_helpers.py",
                     "tests/v2_history_consume/c1_helpers.py", "tests/v2_history_adopt/a5_helpers.py",
                     "tests/v2_scope_chain/sc_helpers.py", "tests/v2_scope_chain/test_sc_01_freeze.py",
                     "tests/v2_scope_chain/test_sc_02_chain.py", "tests/v2_scope_chain/test_sc_03_scope.py",
                     "tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restore/test_r4_09_scope.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)

    def test_the_package_is_the_six_files_of_the_design(self):
        names = sorted(p for p in C.list_files(REV, PACKAGE))
        self.assertEqual(names, sorted(RUNTIME))
        self.assertEqual(C.list_files(START, PACKAGE), [])

    def test_the_one_modified_test_is_the_two_pinned_lines(self):
        out = C.git("diff", "--unified=0", START, REV, "--", CHANGED_TEST)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in PINNED])


class Chain(Base):
    """C2-16: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], [CHANGED_TEST])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_c2_09_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin=FIRST_OF_CHAIN), [])
        self.assertGreaterEqual(len(rows), 8)
        starts = [r["start"] for r in rows]
        self.assertEqual(starts.count(START), 1)
        self.assertIn("bfbde7a7854bf91a77fb58737c24b19c6507453a", starts)

    def test_the_previous_range_is_frozen_at_the_code_start_by_the_changed_line(self):
        tree = ast.parse(C.show(REV, CHANGED_TEST))
        found, end = C.read_constant(tree, "END", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, end), (True, START))
        found, start = C.read_constant(tree, "START", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, start), (True, "bfbde7a7854bf91a77fb58737c24b19c6507453a"))

    def test_the_range_values_of_this_file_are_read_from_the_text_at_head(self):
        # HEAD, not REV: once the next stage freezes END, REV is the commit that holds END = None, and the file that
        # says it is the one that is checked out
        path = NEW_DIR + "test_c2_09_scope.py"
        tree = ast.parse(C.show("HEAD", path))
        self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), "HEAD"), (True, START))
        self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), "HEAD"), (True, END))
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
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "uuid", "webbrowser", "smtplib", "datetime",
                     "tests", "json", "inspect"}
ALLOWED_ROOTS = {"copy", "hashlib", "v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops",
                 "v2_history_restart", "v2_history_restore", "v2_history_adopt"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen", "md5", "sha1", "blake2b"}
HASHLIB_FILES = {"v2_history_publish/read.py"}


class RuntimeAudit(Base):
    """C2-18: the new runtime reads and writes nothing, uses no clock, no randomness, no network, no thread, no
    environment variable, no hash function of its own outside read.py, and brings in no dependency outside the list."""

    def trees(self):
        return {p: ast.parse(C.show(REV, p)) for p in RUNTIME}

    def test_no_forbidden_import_call_or_attribute(self):
        for path, tree in self.trees().items():
            pairs, plain = imports_of(tree)
            for module in plain | {m for m, _n in pairs if m and not m.startswith(".")}:
                self.assertNotIn(module.split(".")[0], FORBIDDEN_IMPORTS, path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, path)

    def test_the_imports_are_in_the_list_of_the_design(self):
        for path, tree in self.trees().items():
            pairs, plain = imports_of(tree)
            for module in plain | {m for m, _n in pairs if m and not m.startswith(".")}:
                self.assertIn(module.split(".")[0], ALLOWED_ROOTS, "%s imports %s" % (path, module))
        self.assertNotIn("v2_history_diagnose", {m.split(".")[0] for t in self.trees().values()
                                                 for m in imports_of(t)[1] | {m for m, _n in imports_of(t)[0]}})

    def test_hashlib_is_used_in_read_py_only(self):
        for path, tree in self.trees().items():
            pairs, plain = imports_of(tree)
            uses = "hashlib" in plain or any(m == "hashlib" for m, _n in pairs)
            self.assertEqual(uses, path in HASHLIB_FILES, path)
            attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            self.assertEqual("sha256" in attrs, path in HASHLIB_FILES, path)
        # the identity of raw bytes is the only thing it hashes
        read = ast.parse(C.show(REV, "v2_history_publish/read.py"))
        calls = [n for n in ast.walk(read) if isinstance(n, ast.Attribute) and n.attr == "sha256"]
        self.assertEqual(len(calls), 1)

    def test_no_new_dependency_file_and_the_public_names_of_the_old_packages_are_unchanged(self):
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertEqual(C.blob_id(REV, name), C.blob_id(START, name), name)
        for package in OLD_PACKAGES:
            path = package + "/__init__.py"
            old, new = ast.parse(C.show(START, path)), ast.parse(C.show(REV, path))
            self.assertEqual(ast.dump(C.top_level(new)["__all__"]), ast.dump(C.top_level(old)["__all__"]), path)
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
        self.assertEqual(C.show(REV, "v2_history/values.py"), C.show(START, "v2_history/values.py"))

    def test_the_kinds_of_the_history_are_the_eight(self):
        import v2_history
        self.assertEqual(len(v2_history.values.KINDS), 8)
        self.assertEqual(sorted(v2_history.KINDS), sorted(v2_history.values.KINDS))

    def test_the_package_exports_the_seven_builders_and_the_two_checks(self):
        tree = self.trees()[PACKAGE + "/__init__.py"]
        exported = C.top_level(tree)["__all__"]
        names = [e.value for e in exported.value.elts]
        self.assertEqual([n for n in names if n.startswith("publish_")],
                         ["publish_day", "publish_resolution", "publish_restart", "publish_restore", "publish_genesis",
                          "publish_migration", "publish_adoption"])
        self.assertIn("check_publication", names)
        self.assertIn("reconcile_publication", names)
        self.assertNotIn("from_dict", names)
        build = C.top_level(self.trees()[PACKAGE + "/build.py"])
        self.assertEqual(sorted(n for n in build if n.startswith("publish_")), sorted(n for n in names
                                                                                     if n.startswith("publish_")))


class Constructors(Base):
    """C2-10 (static): only the builders make a publication. HistoryPublication._make is called in build.py only, and no
    runtime file makes a value of the class in another way."""

    def trees(self):
        return {p: ast.parse(C.show(REV, p)) for p in RUNTIME}

    def test_the_private_constructor_is_called_in_build_py_only(self):
        for path, tree in self.trees().items():
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "_make"]
            if path.endswith("/build.py"):
                # the two shapes of a publication: the records that extend a history, and a whole candidate
                self.assertEqual([ast.unparse(c.func) for c in calls], ["HistoryPublication._make"] * 2, path)
            else:
                self.assertEqual(calls, [], path)
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute):
                    if n.attr == "_make":
                        self.assertTrue(path.endswith("/build.py"), path)
                    if n.attr in ("_wrap", "__new__") and not path.endswith("/values.py"):
                        self.fail("%s uses %s" % (path, n.attr))
                    if n.attr == "_of":
                        self.assertTrue(path.endswith("/check.py"), path)

    def test_the_class_is_not_built_by_another_route(self):
        for path, tree in self.trees().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "HistoryPublication":
                    self.fail("%s calls the class" % path)
                if isinstance(n, ast.Call) and ast.unparse(n.func) in ("object.__new__", "copy.copy", "copy.deepcopy") \
                        and any(ast.unparse(a) == "HistoryPublication" for a in n.args):
                    self.fail("%s copies or makes the class" % path)
        values = ast.parse(C.show(REV, "v2_history_publish/values.py"))
        names = [n.name for n in ast.walk(values) if isinstance(n, ast.FunctionDef)]
        self.assertNotIn("from_dict", names)

    def test_no_function_of_the_package_takes_a_history_to_publish(self):
        build = ast.parse(C.show(REV, "v2_history_publish/build.py"))
        for node in build.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("publish_"):
                args = [a.arg for a in node.args.args]
                self.assertNotIn("candidate", args, node.name)
                self.assertNotIn("result", args, node.name)
                self.assertNotIn("res", args, node.name)


class P02(Base):
    """C2-15: the package neither imports the diagnosis package nor reads what the plan keeps of the discarded part."""

    BANNED_WORDS = ("discarded", "diagnos")

    def package(self):
        paths = [p for p in C.list_files(REV, PACKAGE) if p.endswith(".py")]
        self.assertEqual(len(paths), 6)
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

    def test_no_import_of_the_diagnosis_package(self):
        for path, tree in self.package().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith("v2_history_diagnose"), path)
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertFalse(a.name.startswith("v2_history_diagnose"), path)

    def test_no_name_or_string_of_the_discarded_part_or_the_diagnosis(self):
        for path, tree in self.package().items():
            for word in self.words(tree):
                for banned in self.BANNED_WORDS:
                    self.assertNotIn(banned, word.lower(), "%s: %s" % (path, word))

    def test_the_adoption_builder_reads_three_keys_of_the_plan_basis_and_no_more(self):
        build = ast.parse(C.show(REV, "v2_history_publish/build.py"))
        fn = C.top_level(build)["publish_adoption"]
        keys = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "basis":
                self.assertIsInstance(n.slice, ast.Constant)
                keys.add(n.slice.value)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "items", "keys",
                                                                                                "values", "pop"):
                self.assertNotEqual(ast.unparse(n.func.value), "basis")
        self.assertEqual(keys, {"request_id", "raw_sha256", "raw_size"})
        # nothing else of the plan is read in the package
        for path, tree in self.package().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and ast.unparse(n.value) == "plan":
                    self.assertIn(n.attr, ("basis", "plan_hash"), path)
                if isinstance(n, ast.Subscript) and ast.unparse(n.value) == "plan.basis":
                    self.assertEqual(n.slice.value, "request_id", path)

    def test_the_body_keys_name_neither_part(self):
        values = ast.parse(C.show(REV, "v2_history_publish/values.py"))
        body_keys = None
        for node in values.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "BODY_KEYS":
                body_keys = [e.value for e in node.value.args[0].elts]
        self.assertEqual(len(body_keys), 14)
        for key in body_keys:
            for banned in self.BANNED_WORDS:
                self.assertNotIn(banned, key)


class SideEffects(Base):
    """C2-18: the new tests read Git and the parsed text only, and the stage's own files are the allowed ones."""

    ALLOWED_IMPORTS = {"ast", "copy", "hashlib", "inspect", "json", "os", "sys", "unittest", "unittest.mock", "mock",
                       "c2_helpers", "sc_helpers", "a5_helpers", "c1_helpers", "h_helpers", "ho_helpers", "r3_helpers",
                       "test_c2_09_scope", "types"}
    FORBIDDEN_NAMES = {"open", "eval", "input", "__import__", "print", "breakpoint"}
    FORBIDDEN_ATTRS = {"write", "write_text", "write_bytes", "mkdir", "makedirs", "remove", "unlink", "rename",
                       "rmtree", "copytree", "move", "urandom", "random", "randint", "choice", "seed", "time",
                       "monotonic", "perf_counter", "sleep", "now", "today", "utcnow", "getenv", "environ", "system",
                       "popen", "Popen", "run", "walk", "listdir", "scandir", "glob", "isfile", "isdir", "exists",
                       "read_text", "read_bytes", "connect", "urlopen", "getaddrinfo", "gethostbyname", "chdir",
                       "putenv", "setdefault"}

    def own_sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 8)
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
        out = C.git("diff", "--name-only", START, REV)
        self.assertEqual([p for p in out.stdout.split() if "__pycache__" in p or p.endswith((".pyc", ".log"))], [])

    def test_the_tests_use_the_private_constructor_only_to_make_values_by_hand(self):
        # the tests may call _make and _wrap (to forge a value on purpose); the runtime may not (Constructors above)
        used = set()
        for path, tree in self.own_sources().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and n.attr in ("_make", "_wrap"):
                    used.add(path.rsplit("/", 1)[1])
        self.assertTrue(used <= {"c2_helpers.py", "test_c2_03_build_whole.py", "test_c2_04_cas.py",
                                 "test_c2_05_reconcile.py", "test_c2_06_no_leak.py"}, used)


if __name__ == "__main__":
    unittest.main()
