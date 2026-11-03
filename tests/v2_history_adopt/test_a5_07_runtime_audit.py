"""A5-17 audit of the new runtime (AST): dependencies, purity, public names, nothing of the later stages."""
import ast
import inspect
import os
import unittest

import a5_helpers as Z
from a5_helpers import A

ROOT = Z.ROOT
PKG = os.path.join(ROOT, "v2_history_adopt")
TESTS = os.path.join(ROOT, "tests", "v2_history_adopt")

ALLOWED_STDLIB = {"copy"}
ALLOWED_NAMES = {
    "v2_history": {"History", "validate_history", "decode_history", "encode_history", "RECOVERY_PREFIX_ADOPTION",
                   "SCHEMA_MIGRATION", "KINDS"},
    "v2_history.values": {"history_dict"},
    "v2_history.common": {"is_int", "is_hex64", "is_date", "basis_request_hash", "same"},
    "v2_history_diagnose": {"diagnose_history_bytes", "PREFIX_ONLY"},
    "v2_history_ops.errors": {"history_request_conflict", "history_plan_mismatch", "history_plan_stale"},
    "v2_persistence.codec": {"canonical_json", "sha256_text", "compute_event_hash"},
    "v2_persistence.errors": {"PersistenceError"},
    "v2_core.errors": {"CoreError"},
    "v2_recovery.common": {"requested_text", "is_requested_text", "valid_request_id"},
}
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "uuid", "webbrowser", "smtplib", "datetime", "json",
                     "re", "hashlib", "tests"}
NEVER_USED = {"Ctx", "SnapshotView", "validate_set", "make_records", "resolve_observations", "Chain", "ledger_of",
              "_Walk", "_Frozen", "HistoryAppendBatch", "check_append_batch", "prepare_history_day", "prepare_day",
              "AppendPlan", "make_apply_event", "MemoryStore", "LocalFileStore", "decode_snapshot", "check_view",
              "prepare_restore_plan", "confirm_restore_plan", "prepare_restart_plan", "build_restore", "RestorePlan",
              "diagnose", "hashlib"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen", "sha256", "md5", "hexdigest", "write", "read"}
# CONSUME, S3-C (putting the bytes aside, publishing, comparing with the original) and every kind of store, notification
# or outbound connection. "adopt", "prefix" and "plan" are the words of this stage itself.
LATER_STAGE_WORDS = ("consume", "unlock", "outbox", "webhook", "discord", "snapshot.json", "notify", "sheet", "publish",
                     "durab", "cas_", "fsync", "localfile", "memorystore", "journal", "reinit", "restore", "restart",
                     "ledger", "sessions", "series", "quarantine", "evacuat", "archive", "compare_and", "swap", "lock",
                     "commit_", "path", "file", "socket", "url", "http")
KIND_NAMES = {"GENESIS", "APPLY", "SCHEMA_MIGRATION", "RECOVERY_RESTORE", "RESTART_UNKNOWN", "KINDS",
              "RECOVERY_PREFIX_ADOPTION"}
PUBLIC = ["prepare_prefix_adoption", "confirm_prefix_adoption", "AdoptionPlan", "AdoptionConfirmResult", "READY",
          "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
FILES = ["__init__.py", "build.py", "confirm.py", "errors.py", "prepare.py", "values.py"]


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


def docstring_ids(tree):
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                docs.add(id(first.value))
    return docs


class Dependencies(unittest.TestCase):
    def test_only_the_allowed_modules_and_names(self):
        count = 0
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        count += 1
                        self.assertIn(a.name, ALLOWED_STDLIB, "%s imports %s" % (fname, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                                              # inside the package
                        count += 1
                        continue
                    mod = node.module
                    self.assertIn(mod, ALLOWED_NAMES, "%s imports from %s" % (fname, mod))
                    for a in node.names:
                        count += 1
                        self.assertIn(a.name, ALLOWED_NAMES[mod], "%s imports %s.%s" % (fname, mod, a.name))
                        self.assertFalse(a.name.startswith("_"), "%s imports a private name" % fname)
                        self.assertNotIn(a.name, NEVER_USED, fname)
                    self.assertNotIn(mod.split(".")[0], FORBIDDEN_IMPORTS, fname)
                    self.assertNotRegex(mod, r"^v2_persistence\.(local|store|plan|runner)", fname)
                    self.assertNotRegex(mod, r"^v2_history_(restore|restart)", fname)
        self.assertGreater(count, 25)

    def test_the_standard_library_is_copy_only_and_hashlib_is_not_there(self):
        imported = set()
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {a.name for a in node.names}
                if isinstance(node, ast.Name):
                    self.assertNotEqual(node.id, "hashlib", fname)
        self.assertEqual(imported, {"copy"})

    def test_every_allowed_name_is_really_used_by_some_module(self):
        used = set()
        for _f, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and not node.level:
                    used |= {"%s.%s" % (node.module, a.name) for a in node.names}
        allowed = {"%s.%s" % (m, n) for m, names in ALLOWED_NAMES.items() for n in names}
        # the allowed list is the ceiling of design 5.7; a name that is allowed but unused is only reported here
        self.assertTrue(used <= allowed)
        self.assertGreaterEqual(len(used), 20)

    def test_no_name_of_the_old_machinery_appears_anywhere(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, NEVER_USED, fname)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, NEVER_USED, fname)

    def test_no_private_name_of_an_existing_package_is_used(self):
        """A leading underscore is used only on self / cls and on the package's own module-level names."""
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    base = node.value
                    self.assertTrue(isinstance(base, ast.Name) and base.id in ("self", "cls", "other", "obj"),
                                    "%s uses ._%s of something else" % (fname, node.attr.lstrip("_")))

    def test_no_test_helper_or_dependency_file(self):
        self.assertEqual(sorted(f for f in os.listdir(PKG) if not f.startswith("__pycache__")), FILES)
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(os.path.exists(os.path.join(PKG, name)))
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("tests", "ho_helpers", "h_helpers", "d5_helpers",
                                                             "a5_helpers", "r3_helpers", "r4_helpers")), fname)


class Purity(unittest.TestCase):
    def test_no_io_clock_process_thread_random_or_environment(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        self.assertNotIn(f.id, FORBIDDEN_CALLS, fname)
                    if isinstance(f, ast.Attribute):
                        self.assertNotIn(f.attr, FORBIDDEN_ATTRS, fname)
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_IMPORTS - {"tests"}, fname)

    def test_no_global_state_is_assigned_or_declared(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                self.assertNotIsInstance(node, (ast.Global, ast.Nonlocal), fname)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        self.assertTrue(isinstance(t, ast.Name) and (t.id.isupper() or t.id in ("__all__",)),
                                        "%s assigns %r at module level" % (fname, getattr(t, "id", t)))
                    self.assertIsInstance(node.value, (ast.Constant, ast.Tuple, ast.Call, ast.List), fname)

    def test_no_threshold_ratio_or_market_number_is_written(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    self.assertIsInstance(node.value, int, fname)
                    # indexes, "- 1", the schema version 2 and the 12-character hash prefix of a repr
                    self.assertIn(node.value, (0, 1, 2, 3, 12), "%s holds the number %r" % (fname, node.value))

    def test_the_module_level_constants_are_the_documented_ones(self):
        names = {}
        for fname, tree in sources():
            names[fname] = sorted(t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
                                  if isinstance(t, ast.Name))
        flat = [n for v in names.values() for n in v]
        self.assertEqual(sorted(flat), sorted(["__all__", "BASIS_KEYS", "CONFIRMED_IN_MEMORY", "NO_CHANGE", "OPERATION",
                                               "READY", "REASON", "_HASH_KEYS", "_JSON_RULES"]))


class Scope(unittest.TestCase):
    def test_nothing_of_the_later_stages(self):
        checked = 0
        for fname, tree in sources():
            docs = docstring_ids(tree)
            for node in ast.walk(tree):
                values = []
                if isinstance(node, ast.Name):
                    values.append(node.id)
                elif isinstance(node, ast.Attribute):
                    values.append(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    values.append(node.name)
                elif isinstance(node, ast.arg):
                    values.append(node.arg)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    values.append(node.value)
                for v in values:
                    checked += 1
                    if v in KIND_NAMES or v == "committed":
                        continue                                    # record kind names are data; committed is the fixed False flag
                    for word in LATER_STAGE_WORDS:
                        self.assertNotIn(word, v.lower(), "%s: %s" % (fname, v))
        self.assertGreater(checked, 400)

    def test_the_public_names_are_exactly_the_documented_seven(self):
        self.assertEqual(sorted(A.__all__), sorted(PUBLIC))
        self.assertEqual(len(A.__all__), 7)
        for name in A.__all__:
            self.assertTrue(hasattr(A, name), name)
        self.assertEqual((A.READY, A.CONFIRMED_IN_MEMORY, A.NO_CHANGE), ("READY", "CONFIRMED_IN_MEMORY", "NO_CHANGE"))
        public_attributes = {n for n in dir(A) if not n.startswith("_")}
        self.assertEqual(public_attributes - set(PUBLIC), {"build", "confirm", "errors", "prepare", "values"})

    def test_no_other_package_exports_the_new_names(self):
        import v2_history
        import v2_history_diagnose
        import v2_history_ops
        import v2_history_restart
        import v2_history_restore
        import v2_persistence
        import v2_recovery
        for module in (v2_history, v2_history_ops, v2_history_restart, v2_history_restore, v2_history_diagnose,
                       v2_persistence, v2_recovery):
            exported = set(getattr(module, "__all__", []))
            self.assertFalse(exported & {"prepare_prefix_adoption", "confirm_prefix_adoption", "AdoptionPlan",
                                         "AdoptionConfirmResult"}, module.__name__)

    def test_the_two_functions_take_no_ledger_sessions_or_series(self):
        prepare = list(inspect.signature(A.prepare_prefix_adoption).parameters)
        confirm = list(inspect.signature(A.confirm_prefix_adoption).parameters)
        self.assertEqual(prepare, ["data", "adopt_count", "request_id", "requested_at"])
        self.assertEqual(confirm, ["plan", "confirmed_plan_hash", "data"])

    def test_the_package_defines_two_functions_two_types_and_the_documented_helpers(self):
        defined = {}
        for fname, tree in sources():
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    defined.setdefault(fname, []).append(node.name)
        self.assertEqual(defined["values.py"], ["AdoptionPlan", "AdoptionConfirmResult"])
        self.assertEqual(defined["prepare.py"], ["check_arguments", "prepare_prefix_adoption"])
        self.assertEqual(defined["confirm.py"], ["_form_ok", "_candidate_of", "_plan_basis", "confirm_prefix_adoption"])
        self.assertEqual(defined["build.py"], ["_leaves_a_migration", "_physical_ids", "build_adoption"])
        self.assertEqual(defined["errors.py"], ["adoption_invalid", "candidate_failure"])

    def test_the_stage_does_not_define_the_kind_or_the_store_names(self):
        defined = {n.name for _f, tree in sources() for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for banned in ("RECOVERY_PREFIX_ADOPTION", "check_view", "diagnose_history_bytes", "validate_history"):
            self.assertNotIn(banned, defined)
        import v2_history
        self.assertEqual(v2_history.KINDS[-1], "RECOVERY_PREFIX_ADOPTION")

    def test_the_new_tests_use_unique_names_and_no_init_file(self):
        self.assertFalse(os.path.exists(os.path.join(TESTS, "__init__.py")))
        names = sorted(f for f in os.listdir(TESTS) if f.endswith(".py"))
        for name in names:
            self.assertTrue(name.startswith("test_a5_") or name in ("a5_helpers.py", "a5_sensitivity.py"), name)
        taken = {}
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
            for f in files:
                if f.endswith(".py") and os.path.abspath(dirpath) != os.path.abspath(TESTS):
                    taken.setdefault(f, dirpath)
        for name in names:
            self.assertNotIn(name, taken, "%s already exists in %s" % (name, taken.get(name)))


if __name__ == "__main__":
    unittest.main()
