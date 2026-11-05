"""S4D-17: the static range of the runtime of v2_inputs (read as text, parsed with ast): the five files; only the standard
modules csv, datetime, hashlib, io, json, math and re, v2_core (errors, sessions, fixture) and v2_git_store (Git, GitError,
OK); no network, process, environment, clock, sleep, file or zone module; no raise inside an except body (a bare raise
excepted); no private attribute of another object; the only Git calls are fetch, blob, commit_with and push; no other package
imports v2_inputs."""
import ast
import os
import unittest

import s4d_helpers as H

PACKAGE = "v2_inputs"
FILES = ("__init__.py", "ledger.py", "load.py", "market.py", "xnys.py")
STANDARD = {"csv", "datetime", "hashlib", "io", "json", "math", "re"}
CORE = {"v2_core.errors", "v2_core.sessions", "v2_core.fixture"}
GIT_NAMES = {"Git", "GitError", "OK"}
GIT_METHODS = {"fetch", "blob", "commit_with", "push"}
FORBIDDEN_MODULES = {"urllib", "http", "socket", "ssl", "subprocess", "os", "time", "random", "threading", "zoneinfo",
                     "tempfile", "shutil", "sys", "pathlib", "requests", "yfinance"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "sleep", "environ", "getenv", "putenv", "urlopen", "system", "popen",
                   "monotonic", "perf_counter", "gethostbyname", "create_connection"}
FORBIDDEN_CALLS = {"open", "print", "eval", "exec", "compile", "input", "__import__", "globals", "locals", "vars", "getattr",
                   "setattr", "delattr"}


def sources():
    root = os.path.join(H.ROOT, PACKAGE)
    names = sorted(n for n in os.listdir(root) if n.endswith(".py"))
    out = {}
    for name in names:
        out[name] = ast.parse(H.read_source("%s/%s" % (PACKAGE, name)))
    return names, out


class Static(H.Case):
    @classmethod
    def setUpClass(cls):
        cls.names, cls.trees = sources()

    def test_the_package_is_the_five_files_of_the_design(self):
        self.assertEqual(tuple(self.names), FILES)
        root = os.path.join(H.ROOT, PACKAGE)
        self.assertEqual(sorted(n for n in os.listdir(root) if n != "__pycache__"), sorted(FILES))

    def test_only_the_allowed_modules_and_names_are_imported(self):
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, STANDARD, "%s imports %s" % (name, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        self.assertEqual(node.level, 1)
                        continue
                    if node.module in CORE:
                        continue
                    if node.module == "v2_git_store":
                        self.assertTrue({a.name for a in node.names} <= GIT_NAMES, "%s %s" % (name, node.names))
                        continue
                    self.fail("%s imports from %s" % (name, node.module))

    def test_no_network_process_environment_clock_sleep_or_file_name_is_used(self):
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_MODULES, "%s uses %s" % (name, node.id))
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, "%s uses .%s" % (name, node.attr))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, "%s calls %s" % (name, node.func.id))

    def test_no_raise_inside_an_except_body_except_a_bare_one(self):
        count = 0
        for name, tree in self.trees.items():
            for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
                count += 1
                for node in ast.walk(handler):
                    if isinstance(node, ast.Raise):
                        self.assertIsNone(node.exc, "%s raises inside an except body (line %d)" % (name, node.lineno))
        self.assertGreater(count, 8)

    def test_no_private_attribute_of_another_object(self):
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                    self.assertIsInstance(node.value, ast.Name, (name, node.attr))
                    self.assertEqual(node.value.id, "self", "%s uses .%s of %s" % (name, node.attr, node.value.id))

    def test_git_is_called_only_by_fetch_blob_commit_with_and_push(self):
        used = set()
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    target = ast.unparse(node.func.value)
                    if target == "git" or target.endswith("._git"):
                        self.assertIn(node.func.attr, GIT_METHODS, "%s calls git.%s" % (name, node.func.attr))
                        used.add(node.func.attr)
        self.assertEqual(used, GIT_METHODS)

    def test_the_remote_is_changed_only_by_the_push_of_the_pin(self):
        pushes = []
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "push":
                    pushes.append((name, ast.unparse(node.func.value), ast.unparse(node.args[1])))
        self.assertEqual(pushes, [("market.py", "self._git", "self._ref")])
        for name, tree in self.trees.items():                                   # a ledger file or a ref is never written
            if name == "ledger.py":
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute):
                        self.assertNotIn(node.attr, ("push", "commit_with"), name)

    def test_only_the_call_of_the_fetch_function_is_caught_wide(self):
        wide = []
        for name, tree in self.trees.items():
            for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
                if handler.type is None:
                    wide.append((name, handler.lineno))
                elif isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"):
                    wide.append((name, handler.lineno))
        self.assertEqual([w[0] for w in wide], ["load.py"])                    # only the call of the fetch function
        self.assertEqual(len(wide), 1)

    def test_the_public_names_and_the_constants_of_the_design(self):
        import v2_inputs
        for n in ("load_inputs", "Inputs", "guarded_store", "build_sessions", "coverage_failure", "chart_url", "parse_chart",
                  "MarketPin", "read_ledger", "SYMBOLS", "PREHISTORY_START", "PRICE_MAX", "CALENDAR_START", "CALENDAR_END",
                  "MARGIN_DAYS", "CLOSE_MARGIN"):
            self.assertTrue(hasattr(v2_inputs, n), n)
        self.assertEqual(sorted(v2_inputs.__all__), sorted(
            ["CALENDAR_END", "CALENDAR_START", "CLOSE_MARGIN", "Inputs", "MARGIN_DAYS", "MarketPin", "PREHISTORY_START",
             "PRICE_MAX", "SYMBOLS", "build_sessions", "calendar_sha256", "chart_url", "coverage_failure", "guarded_store",
             "load_inputs", "parse_chart", "read_ledger"]))

    def test_no_other_package_imports_v2_inputs(self):
        for package in ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                        "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "v2_history_publish",
                        "v2_history_local", "v2_history_maintain", "v2_daily_run", "v2_notify", "v2_git_store"):
            for dirpath, _dirs, files in os.walk(os.path.join(H.ROOT, package)):
                for f in files:
                    if f.endswith(".py"):
                        rel = os.path.relpath(os.path.join(dirpath, f), H.ROOT)
                        self.assertNotIn("v2_inputs", H.read_source(rel), rel)


if __name__ == "__main__":
    unittest.main()
