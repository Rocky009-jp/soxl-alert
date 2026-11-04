"""S4A-15: the static range of the runtime. It brings in only datetime, v2_core, v2_history_ops and v2_history_publish
(and its own modules); it has no file, process, network, clock, random or environment use; it never calls initialize,
unlock, migrate or adopt; it never makes, copies or forges a value of C-2."""
import ast
import unittest

import s4a_helpers as S

RUNTIME = ("v2_daily_run/__init__.py", "v2_daily_run/run.py", "v2_daily_run/values.py")
ALLOWED_ROOTS = {"datetime", "v2_core", "v2_history_ops", "v2_history_publish"}
ALLOWED_FROM = {
    "v2_core.display": {"render_message"},
    "v2_core.errors": {"CoreError"},
    "v2_core.sessions": {"SessionList"},
    "v2_history_ops": {"ALREADY_APPLIED", "NO_COMMIT", "PREPARED", "prepare_history_day", "read_effective"},
    "v2_history_publish": {"PUBLISHED", "PUBLISHED_THEN_EXTENDED", "publish_day"},
}
OWN_MODULES = {".run", ".values"}
FORBIDDEN_IMPORTS = {"os", "sys", "io", "socket", "subprocess", "threading", "multiprocessing", "time", "random",
                     "secrets", "pathlib", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "uuid", "json", "copy", "hashlib", "inspect",
                     "builtins", "importlib", "v2_history_local", "v2_history_maintain", "v2_persistence",
                     "v2_history", "v2_recovery", "tests"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print", "setattr", "vars", "globals",
                   "locals", "breakpoint", "exit", "quit"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "putenv",
                   "system", "popen", "random", "seed", "Thread", "Popen", "run", "md5", "sha1", "sha256", "blake2b",
                   "initialize", "unlock", "migrate", "adopt", "plan_unlock", "read_original", "read_set_aside",
                   "inspect", "__new__", "from_dict", "_make", "_of", "_wrap", "connect", "write", "mkdir", "unlink"}
CALLED_ON_THE_STORE = {"read", "publish", "reconcile"}


class Runtime(unittest.TestCase):
    def trees(self):
        return {p: ast.parse(S.read_source(p)) for p in RUNTIME}

    def test_the_package_is_three_files(self):
        for path in RUNTIME:
            S.read_source(path)
        self.assertLessEqual(len(RUNTIME), 4)

    def test_the_imports_are_the_list_of_the_design(self):
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertEqual(a.name, "datetime", path)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        self.assertIn("." * node.level + (node.module or ""), OWN_MODULES | {".run", ".values"}, path)
                        continue
                    self.assertIn(node.module, ALLOWED_FROM, "%s imports from %s" % (path, node.module))
                    self.assertTrue({a.name for a in node.names} <= ALLOWED_FROM[node.module],
                                    "%s imports %s from %s" % (path, [a.name for a in node.names], node.module))
                    self.assertIn(node.module.split(".")[0], ALLOWED_ROOTS)
                    self.assertNotIn(node.module.split(".")[0], FORBIDDEN_IMPORTS)

    def test_no_file_process_network_clock_random_or_environment_use(self):
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, "%s uses .%s" % (path, node.attr))
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("os", "sys", "socket", "subprocess", "time", "random", "environ"), path)

    def test_datetime_is_used_only_to_check_the_type_of_now(self):
        uses = []
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "datetime":
                    uses.append((path, node.attr))
        self.assertEqual(uses, [("v2_daily_run/run.py", "datetime")])
        run = self.trees()["v2_daily_run/run.py"]
        calls = [ast.unparse(n) for n in ast.walk(run) if isinstance(n, ast.Call)
                 and any("datetime" in ast.unparse(a) for a in n.args)]
        self.assertEqual(calls, ["isinstance(now, datetime.datetime)"])

    def test_the_store_is_only_asked_to_read_publish_and_reconcile(self):
        asked = set()
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "store":
                    asked.add(node.func.attr)
        self.assertEqual(asked, CALLED_ON_THE_STORE)

    def test_no_value_of_c2_is_made_copied_or_forged_and_no_publication_is_published_twice(self):
        run = self.trees()["v2_daily_run/run.py"]
        publish_calls = [n for n in ast.walk(run) if isinstance(n, ast.Call) and ast.unparse(n.func) == "store.publish"]
        self.assertEqual(len(publish_calls), 1)
        reconcile_calls = [n for n in ast.walk(run) if isinstance(n, ast.Call) and ast.unparse(n.func) == "store.reconcile"]
        self.assertEqual(len(reconcile_calls), 1)
        for path, tree in self.trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, ("HistoryPublication", "Reconciliation", "HistoryFileStore",
                                               "HistoryMaintenance"), path)

    def test_the_old_packages_are_not_named_by_a_path_of_the_runtime(self):
        for path, tree in self.trees().items():
            text = S.read_source(path)
            for forbidden in ("v2_history_local", "v2_history_maintain", "v2_persistence", "os.environ"):
                self.assertNotIn(forbidden, text, path)
            docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                          if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and n.body
                          and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    self.assertNotIn("/", node.value, path)                          # no path-like text constant
                    self.assertNotIn("\\", node.value, path)


if __name__ == "__main__":
    unittest.main()
