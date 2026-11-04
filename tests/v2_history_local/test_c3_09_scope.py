"""C3-15 .. C3-18: the range of stage C-3 and its audits.

START is the code start of this stage (the accepted d6b0332, the final commit of C-2). END is None until the next stage
freezes it with the accepted final commit (one line); REV is then the committed state under test. Everything is read from
Git at REV (or, for the one question of what this file says about itself, at HEAD): the working tree is not read, no
earlier stage's diff is copied, and nothing is written. The one line of test_c2_09_scope.py that this stage had to change
is pinned below as the hunk of this stage's own diff."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)

START = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"
END = "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a"   # accepted (review 2049e10); frozen when C-4 began
REV = END or "HEAD"

PACKAGE = "v2_history_local"
RUNTIME = tuple("v2_history_local/%s.py" % n for n in ("__init__", "results", "store"))
NEW_DIR = "tests/v2_history_local/"
RESULT_DOC = "docs/implementation/V2_HISTORY_LOCAL_C3_RESULT.md"
CHANGED_TEST = "tests/v2_history_publish/test_c2_09_scope.py"
OLD_PACKAGES = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "v2_history_publish")
ROOTS = OLD_PACKAGES + ("main.py", "research", "docs", "CLAUDE.md", "README.md", ".github", "requirements.txt")
FIRST_OF_CHAIN = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"

# The one line of the previous stage's range test that this stage changed (C3-16): `git diff --unified=0 START REV`.
PINNED = [('-18', '+18',
           ['END = None          # not accepted yet; the next stage replaces None with the accepted final commit'],
           ['END = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"   # accepted (review a91a9ed); frozen when C-3 began'])]

# The only names the runtime takes from v2_history_publish (C3-15, design 2.3).
PUBLISH_NAMES = {"APPEND", "CREATE", "GENESIS", "HistoryPublication", "check_publication", "history_bytes",
                 "read_history_bytes", "reconcile_publication"}
FILE_OPS_CALLS = {"create_exclusive", "open_writer", "close_fd", "write", "flush", "fsync_file", "close", "replace",
                  "probe_dir_sync", "fsync_dir", "unlink", "read_file", "listdir", "lstat", "fstat"}


def allowed_new_path(path):
    if path == RESULT_DOC:
        return True
    if path in RUNTIME:
        return True
    name = path[len(NEW_DIR):]
    return (path.startswith(NEW_DIR) and "/" not in name and name.endswith(".py") and name != "__init__.py"
            and (name in ("c3_helpers.py", "c3_worker.py") or name.startswith("test_c3_")))


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
        self.assertTrue(allowed_new_path("tests/v2_history_local/test_c3_01_config_values.py"))
        self.assertTrue(allowed_new_path("tests/v2_history_local/c3_helpers.py"))
        self.assertTrue(allowed_new_path("tests/v2_history_local/c3_worker.py"))
        self.assertTrue(allowed_new_path("v2_history_local/store.py"))
        self.assertTrue(allowed_new_path(RESULT_DOC))
        self.assertFalse(allowed_new_path("tests/v2_history_local/__init__.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_local/other.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_local/sub/test_c3_x.py"))
        self.assertFalse(allowed_new_path("tests/v2_history_publish/test_c2_10.py"))
        self.assertFalse(allowed_new_path("v2_history_local/fourth.py"))
        self.assertFalse(allowed_new_path("v2_history_publish/new.py"))
        self.assertFalse(allowed_new_path("docs/implementation/V2_HISTORY_PUBLISH_C2_RESULT.md"))

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
    """C3-17: compared with the code start by Git (committed state)."""

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
        self.assertTrue(any(p.startswith(NEW_DIR + "test_c3_") for p in added))
        self.assertIn(NEW_DIR + "c3_helpers.py", added)
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
                    ":(exclude)tests/v2_history_local")
        self.assertEqual(out.stdout.strip(), "")
        for path in ("tests/v2_persistence_local/l_helpers.py", "tests/v2_persistence_local/worker.py",
                     "tests/v2_history_publish/c2_helpers.py", "tests/v2_history/h_helpers.py",
                     "tests/v2_history_ops/ho_helpers.py", "tests/v2_history_restart/r3_helpers.py",
                     "tests/v2_history_restore/r4_helpers.py", "tests/v2_history_consume/c1_helpers.py",
                     "tests/v2_history_adopt/a5_helpers.py", "tests/v2_scope_chain/sc_helpers.py",
                     "tests/v2_scope_chain/test_sc_01_freeze.py", "tests/v2_scope_chain/test_sc_02_chain.py",
                     "tests/v2_scope_chain/test_sc_03_scope.py", "tests/v2_history_ops/test_b17_scope.py",
                     "tests/v2_history_restore/test_r4_09_scope.py", "tests/v2_history_consume/test_c1_09_scope.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)

    def test_the_package_is_the_three_files_of_the_design(self):
        names = sorted(p for p in C.list_files(REV, PACKAGE))
        self.assertEqual(names, sorted(RUNTIME))
        self.assertEqual(C.list_files(START, PACKAGE), [])

    def test_the_one_modified_test_is_the_one_pinned_line(self):
        out = C.git("diff", "--unified=0", START, REV, "--", CHANGED_TEST)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(parse_hunks(out.stdout), [tuple(h) for h in PINNED])


class Chain(Base):
    """C3-16: the range values."""

    def test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range(self):
        rows = C.range_tests(REV)
        mine = [r for r in rows if r["path"].startswith(NEW_DIR)]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["start"], mine[0]["end"]), (START, None))
        before = [r for r in rows if r["end"] == START]
        self.assertEqual([r["path"] for r in before], [CHANGED_TEST])
        self.assertEqual(len([r for r in rows if r["end"] is None]), 1)
        self.assertEqual(mine[0]["path"], NEW_DIR + "test_c3_09_scope.py")

    def test_the_whole_chain_has_no_gap(self):
        rows = C.range_tests(REV)
        self.assertEqual(C.judge_chain(rows, C.is_ancestor, tip=REV, begin=FIRST_OF_CHAIN), [])
        self.assertGreaterEqual(len(rows), 9)
        starts = [r["start"] for r in rows]
        self.assertEqual(starts.count(START), 1)
        for earlier in ("bfbde7a7854bf91a77fb58737c24b19c6507453a", "de6549acb4ecea759cc771300fd0bef59dd5456a"):
            self.assertIn(earlier, starts)

    def test_the_previous_range_is_frozen_at_the_code_start_by_the_changed_line(self):
        tree = ast.parse(C.show(REV, CHANGED_TEST))
        found, end = C.read_constant(tree, "END", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, end), (True, START))
        found, start = C.read_constant(tree, "START", os.path.dirname(CHANGED_TEST), REV)
        self.assertEqual((found, start), (True, "de6549acb4ecea759cc771300fd0bef59dd5456a"))

    def test_the_range_values_of_this_file_are_read_from_the_text_at_head(self):
        # HEAD, not REV: once the next stage freezes END, REV is the commit that holds END = None, and the file that
        # says it is the one that is checked out
        path = NEW_DIR + "test_c3_09_scope.py"
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


FORBIDDEN_IMPORTS = {"sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "pathlib", "io",
                     "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl", "ctypes", "sqlite3",
                     "glob", "fcntl", "msvcrt", "uuid", "webbrowser", "smtplib", "datetime", "tests", "json",
                     "inspect", "hashlib", "copy", "queue", "builtins", "importlib", "os.environ"}
ALLOWED_ROOTS = {"os", "secrets", "stat", "dataclasses", "typing", "v2_core", "v2_persistence", "v2_history_publish"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print", "setattr", "vars", "globals",
                   "locals"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "putenv",
                   "system", "popen", "random", "seed", "Thread", "Popen", "run", "md5", "sha1", "sha256", "blake2b",
                   "_make", "_of", "_wrap", "__new__", "from_dict", "deepcopy", "copy"}
OS_PATH_USES = {"join", "dirname", "abspath", "isabs", "realpath"}


class RuntimeAudit(Base):
    """C3-18: the new runtime brings in no dependency outside the list, no network, clock, thread, process, environment
    variable or hash function, uses os only for path names, and reaches the files only through FileOps."""

    def trees(self):
        return {p: ast.parse(C.show(REV, p)) for p in RUNTIME}

    def test_the_imports_are_the_list_of_the_design(self):
        for path, tree in self.trees().items():
            pairs, plain = imports_of(tree)
            for module in plain | {m for m, _n in pairs if m and not m.startswith(".")}:
                root = module.split(".")[0]
                self.assertIn(root, ALLOWED_ROOTS, "%s imports %s" % (path, module))
                self.assertNotIn(root, FORBIDDEN_IMPORTS, path)
            for module, name in pairs:
                if module.startswith("v2_persistence"):
                    self.assertTrue(module == "v2_persistence.local" or module.startswith("v2_persistence.local."),
                                    "%s imports %s" % (path, module))
                if module.startswith("v2_core"):
                    self.assertEqual((module, name), ("v2_core.errors", "CoreError"), path)
                if module.startswith("."):
                    self.assertIn(module, (".results", ".store"), path)

    def test_the_names_taken_from_the_publication_package_are_the_eight_of_the_design(self):
        seen = set()
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                        and node.module.split(".")[0] == "v2_history_publish":
                    self.assertEqual(node.module, "v2_history_publish", path)
                    seen.update(a.name for a in node.names)
                if isinstance(node, ast.Import):
                    self.assertFalse([a for a in node.names if a.name.split(".")[0] == "v2_history_publish"], path)
        self.assertEqual(seen, PUBLISH_NAMES)

    def test_no_forbidden_call_or_attribute(self):
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, path)

    def test_os_is_used_only_for_path_names(self):
        used = set()
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                        and isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                    self.assertEqual(node.value.attr, "path", path)
                    self.assertIn(node.attr, OS_PATH_USES, path)
                    used.add("path." + node.attr)
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertIn(node.attr, ("path", "fspath"), path)
                    used.add(node.attr)
        self.assertLessEqual(used, {"path", "fspath"} | {"path." + n for n in OS_PATH_USES})
        self.assertTrue({"fspath", "path.join", "path.realpath"} <= used)

    def test_the_files_are_reached_through_file_ops_only(self):
        calls = []
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in FILE_OPS_CALLS:
                    calls.append((path, node.func.attr, ast.unparse(node.func.value)))
        self.assertGreater(len(calls), 20)
        for path, name, receiver in calls:
            self.assertIn(receiver, ("ops", "self._ops"), "%s: %s.%s" % (path, receiver, name))
        names = {name for _p, name, _r in calls}
        self.assertTrue({"replace", "unlink", "create_exclusive", "fsync_file", "fsync_dir", "read_file"} <= names)

    def test_the_package_exports_the_store_the_result_and_the_words_of_s2_only(self):
        tree = self.trees()[PACKAGE + "/__init__.py"]
        names = [e.value for e in C.top_level(tree)["__all__"].value.elts]
        self.assertEqual(sorted(names), sorted(["HistoryFileStore", "HistoryStoreResult", "LocalStoreError", "STRICT",
                                                "FILE_SYNC_ONLY_MODE", "PUBLISHED", "INITIALIZED",
                                                "FILE_AND_DIRECTORY_SYNC", "FILE_SYNC_ONLY"]))
        store = C.top_level(self.trees()[PACKAGE + "/store.py"])
        self.assertIn("HistoryFileStore", store)
        api = [n.name for n in store["HistoryFileStore"].body if isinstance(n, ast.FunctionDef)
               and not n.name.startswith("_")]
        self.assertEqual(sorted(api), ["initialize", "persistence_level", "publish", "read", "reconcile"])

    def test_no_new_dependency_file_and_the_public_names_of_the_old_packages_are_unchanged(self):
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertEqual(C.blob_id(REV, name), C.blob_id(START, name), name)
        for package in OLD_PACKAGES:
            path = package + "/__init__.py"
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)
            self.assertEqual(ast.dump(C.top_level(ast.parse(C.show(REV, path)))["__all__"]),
                             ast.dump(C.top_level(ast.parse(C.show(START, path)))["__all__"]), path)
        for path in ("v2_persistence/local/fsops.py", "v2_persistence/local/store.py", "v2_persistence/local/errors.py",
                     "v2_persistence/local/results.py"):
            self.assertEqual(C.blob_id(REV, path), C.blob_id(START, path), path)


class Constructors(Base):
    """C3-15 (static): the runtime never makes, copies or forges a publication or a reconciliation."""

    def trees(self):
        return {p: ast.parse(C.show(REV, p)) for p in RUNTIME}

    def test_no_private_constructor_no_new_no_construction_of_either_class(self):
        for path, tree in self.trees().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute):
                    self.assertNotIn(n.attr, ("_make", "_of", "_wrap", "__new__", "from_dict"), path)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    self.assertNotIn(n.func.id, ("HistoryPublication", "Reconciliation"), path)
                if isinstance(n, ast.Call) and ast.unparse(n.func) in ("object.__new__", "copy.copy", "copy.deepcopy"):
                    self.fail("%s copies or makes a value" % path)
                if isinstance(n, ast.Name):
                    self.assertNotEqual(n.id, "Reconciliation", path)
                if isinstance(n, ast.alias):
                    self.assertNotIn(n.name, ("Reconciliation", "_make"), path)

    def test_the_class_is_only_used_for_the_exact_type_check(self):
        store = self.trees()[PACKAGE + "/store.py"]
        uses = [ast.unparse(n) for n in ast.walk(store) if isinstance(n, ast.Compare)
                and any(isinstance(x, ast.Name) and x.id == "HistoryPublication" for x in [n.left] + n.comparators)]
        self.assertEqual(uses, ["type(publication) is not HistoryPublication"])
        names = [n for n in ast.walk(store) if isinstance(n, ast.Name) and n.id == "HistoryPublication"]
        self.assertEqual(len(names), 1)                           # the type check (the import is an alias)


class TestFiles(Base):
    """C3-15 / C3-18: what the new tests may do. They read Git and the parsed text (this file), write to temporary
    roots only (through c3_helpers.put), start children only as C3-13 says, and use the private constructor only in the
    two files that make a value by hand."""

    ALLOWED_IMPORTS = {"ast", "dataclasses", "json", "os", "queue", "re", "shutil", "subprocess", "sys", "tempfile",
                       "threading", "time", "unittest", "c3_helpers", "c2_helpers", "l_helpers", "sc_helpers",
                       "test_c3_09_scope", "v2_history_local", "v2_history_publish", "v2_persistence.local",
                       "v2_core.errors", "v2_persistence", "socket"}
    FORBIDDEN_ATTRS = {"environ", "getenv", "putenv", "urandom", "sleep", "chdir", "expanduser", "home", "system",
                       "popen", "urlopen", "getaddrinfo", "gethostbyname", "connect", "create_connection"}
    ONLY_IN_HELPERS = {"subprocess", "threading", "queue", "time"}
    MAKE_BY_HAND = {"test_c3_03_values.py", "test_c3_04_refusals.py"}

    def own_sources(self):
        paths = [p for p in C.list_files(REV, NEW_DIR.rstrip("/")) if p.endswith(".py")]
        self.assertGreaterEqual(len(paths), 11)
        return {p: ast.parse(C.show(REV, p)) for p in paths}

    def test_the_own_files_are_the_allowed_ones_and_there_is_no_init_file(self):
        names = [p.rsplit("/", 1)[1] for p in C.list_files(REV, NEW_DIR.rstrip("/"))]
        self.assertNotIn("__init__.py", names)
        for path in self.own_sources():
            self.assertTrue(allowed_new_path(path), path)

    def test_imports_and_the_absence_of_clock_environment_and_network(self):
        for path, tree in self.own_sources().items():
            helper = path.endswith("c3_helpers.py")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, self.ALLOWED_IMPORTS, "%s imports %s" % (path, a.name))
                        if a.name in self.ONLY_IN_HELPERS:
                            self.assertTrue(helper, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module, self.ALLOWED_IMPORTS, "%s imports %s" % (path, node.module))
                if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "ast"):
                    self.assertNotIn(node.attr, self.FORBIDDEN_ATTRS, path)
                    if isinstance(node.value, ast.Name) and node.value.id == "time":
                        self.assertEqual((helper, node.attr), (True, "monotonic"), path)
                    if isinstance(node.value, ast.Name) and node.value.id == "socket":
                        self.assertTrue(path.endswith("c3_worker.py"), path)      # the probe: the call must fail
                        self.assertEqual(node.attr, "socket", path)
                    if isinstance(node.value, ast.Name) and node.value.id == "tempfile":
                        self.assertEqual(node.attr, "mkdtemp", path)

    def test_the_only_process_is_the_worker_started_with_the_interpreter_and_a_file_of_this_directory(self):
        found = 0
        for path, tree in self.own_sources().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                        and node.value.id == "subprocess":
                    self.assertTrue(path.endswith("c3_helpers.py"), path)
                    self.assertIn(node.attr, ("Popen", "PIPE"))
                    found += node.attr == "Popen"
        self.assertEqual(found, 1)
        helpers = self.own_sources()[NEW_DIR + "c3_helpers.py"]
        popen = [n for n in ast.walk(helpers) if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.Popen"]
        self.assertEqual(len(popen), 1)
        self.assertEqual([ast.unparse(e) for e in popen[0].args[0].elts],
                         ["sys.executable", "'-B'", "'-I'", "WORKER", "json.dumps(spec)"])
        assigned = [ast.unparse(n.value) for n in helpers.body if isinstance(n, ast.Assign)
                    and ast.unparse(n.targets[0]) == "WORKER"]
        self.assertEqual(assigned, ["os.path.join(HERE, 'c3_worker.py')"])

    def test_files_are_opened_only_by_the_two_helpers_that_join_the_root_and_a_name(self):
        for path, tree in self.own_sources().items():
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                opens = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                         and n.func.id == "open"]
                if opens:
                    self.assertTrue(path.endswith("c3_helpers.py") and fn.name in ("raw", "put"), "%s %s" % (path, fn.name))
                    self.assertEqual(len(opens), 1)
                    self.assertEqual(ast.unparse(opens[0].args[0]), "os.path.join(root, name)")
            top = [n for n in tree.body if isinstance(n, ast.Expr) or isinstance(n, ast.Assign)]
            for n in top:
                for sub in ast.walk(n):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        self.assertNotEqual(sub.func.id, "open", path)

    def test_the_private_constructor_is_used_to_make_values_by_hand_in_two_files_only(self):
        used = set()
        for path, tree in self.own_sources().items():
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and n.attr in ("_make", "_wrap", "_of"):
                    used.add(path.rsplit("/", 1)[1])
                if isinstance(n, ast.Attribute) and n.attr == "rehash":
                    used.add(path.rsplit("/", 1)[1])
        self.assertTrue(used <= self.MAKE_BY_HAND, used)
        self.assertEqual(used, self.MAKE_BY_HAND)

    def test_git_is_asked_only_through_the_read_only_helper_and_this_file_reads_no_working_tree(self):
        scope = self.own_sources()[NEW_DIR + "test_c3_09_scope.py"]
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
