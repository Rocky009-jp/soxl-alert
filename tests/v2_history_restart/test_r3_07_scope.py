"""B3-16 (scope, stop) and the Git-difference part of B3-01: what the new runtime may import and call, what it does not
build, and which files differ from the code start. The old range test is checked line by line (the three changes)."""
import ast
import os
import subprocess
import unittest

import r3_helpers as R

ROOT = R.ROOT
PKG = os.path.join(ROOT, "v2_history_restart")
TESTS = os.path.join(ROOT, "tests", "v2_history_restart")
START = R.FIXED_START

ALLOWED_STDLIB = {"copy", "json"}
ALLOWED_NAMES = {
    "v2_history": {"History", "validate_history", "HistoryCheck", "Boundary"},
    "v2_history.values": {"history_dict", "check_json"},                       # and the kind-name constants
    "v2_history.common": {"basis_request_hash", "is_int", "is_hex64", "is_date", "same"},
    "v2_history_ops": {"read_effective", "project_history_ledger", "HistoryLedger"},
    "v2_history_ops.errors": {"history_plan_mismatch", "history_plan_stale", "history_request_conflict"},
    "v2_recovery.ledger": {"copy_sessions", "parse_ledger", "ledger_digest", "sessions_digest"},
    "v2_recovery.common": {"requested_text", "is_requested_text", "valid_request_id"},
    "v2_persistence.codec": {"canonical_json", "sha256_text", "compute_event_hash"},
    "v2_persistence.events": {"session_dict"},
    "v2_persistence.errors": {"PersistenceError"},
    "v2_core.state": {"MarketState"},
    "v2_core.fixture": {"parse_iso_date"},
    "v2_core.errors": {"CoreError", "InputError", "ConflictError"},
}
KIND_CONSTANTS = {"ACK", "APPLY", "DECLARE_MISSING", "GENESIS", "RECOVERY_RESTORE", "RESTART_UNKNOWN",
                  "SCHEMA_MIGRATION"}
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "hashlib", "uuid", "webbrowser", "smtplib",
                     "datetime", "tests"}
NEVER_USED = {"Ctx", "SnapshotView", "validate_set", "make_records", "resolve_observations", "Chain", "ledger_of",
              "_Frozen", "LedgerContext", "FixedFacts", "HistoryAppendBatch", "check_append_batch", "make_batch",
              "append_records", "prepare_history_day", "prepare_history_resolution_plan", "prepare_day"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen"}
LATER_STAGE_WORDS = ("unlock", "restore", "outbox", "webhook", "discord", "snapshot.json", "notify", "sheet",
                     "consume", "historyreplacement", "diagnos", "append_batch", "appendbatch", "adoption",
                     "reinit", "publish", "cas_")
OWN_CLASSES = {"RestartPlan", "RestartConfirmResult"}


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


class Runtime(unittest.TestCase):
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
                        ok = a.name in ALLOWED_NAMES[mod] or (mod == "v2_history.values" and a.name in KIND_CONSTANTS)
                        self.assertTrue(ok, "%s imports %s.%s" % (fname, mod, a.name))
                        self.assertFalse(a.name.startswith("_"), "%s imports a private name" % fname)
                        self.assertNotIn(a.name, NEVER_USED, fname)
                    self.assertNotIn(mod.split(".")[0], FORBIDDEN_IMPORTS, fname)
                    self.assertNotRegex(mod, r"^v2_persistence\.(local|store)", fname)
        self.assertGreater(count, 40)

    def test_no_name_of_the_old_machinery_appears_anywhere(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, NEVER_USED, fname)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, NEVER_USED, fname)

    def test_no_private_name_of_an_existing_package_is_used(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    base = node.value
                    self.assertTrue(isinstance(base, ast.Name) and (base.id in ("self", "cls", "other", "obj")
                                                                    or base.id in OWN_CLASSES),
                                    "%s uses ._%s of something else" % (fname, node.attr.lstrip("_")))

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
                    self.assertNotIn(node.id, FORBIDDEN_IMPORTS - {"time", "tests"}, fname)

    def test_nothing_of_the_later_stages(self):
        checked = 0
        for fname, tree in sources():
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
                    first = node.body[0]
                    if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                        docs.add(id(first.value))
            for node in ast.walk(tree):
                values = []
                if isinstance(node, ast.Name):
                    values.append(node.id)
                elif isinstance(node, ast.Attribute):
                    values.append(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    values.append(node.name)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    values.append(node.value)
                for v in values:
                    checked += 1
                    if v in KIND_CONSTANTS:                      # record kind names are data, not a later stage
                        continue
                    for word in LATER_STAGE_WORDS:
                        self.assertNotIn(word, v.lower(), "%s: %s" % (fname, v))
        self.assertGreater(checked, 400)

    def test_the_public_names_are_exactly_the_documented_ones(self):
        self.assertEqual(sorted(R.X.__all__), sorted([
            "prepare_restart_plan", "confirm_restart_plan", "RestartPlan", "RestartConfirmResult", "READY",
            "CONFIRMED_IN_MEMORY", "NO_CHANGE"]))
        for name in R.X.__all__:
            self.assertTrue(hasattr(R.X, name), name)
        self.assertEqual((R.X.READY, R.X.CONFIRMED_IN_MEMORY, R.X.NO_CHANGE), ("READY", "CONFIRMED_IN_MEMORY", "NO_CHANGE"))
        # the existing packages do not re-export it, and their public names are as they were
        import v2_history, v2_history_ops
        self.assertFalse(any("restart_plan" in n.lower() or "RestartPlan" in n for n in v2_history.__all__))
        self.assertFalse(any("restart_plan" in n.lower() or "RestartPlan" in n for n in v2_history_ops.__all__))

    def test_the_package_files_and_the_absence_of_dependency_files(self):
        self.assertEqual(sorted(f for f in os.listdir(PKG) if not f.startswith("__pycache__")),
                         ["__init__.py", "build.py", "confirm.py", "errors.py", "prepare.py", "values.py"])
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(os.path.exists(os.path.join(PKG, name)))
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("tests", "ho_helpers", "h_helpers", "r3_helpers")), fname)

    def test_the_new_tests_use_unique_names_and_no_init_file(self):
        self.assertFalse(os.path.exists(os.path.join(TESTS, "__init__.py")))
        names = sorted(f for f in os.listdir(TESTS) if f.endswith(".py"))
        for name in names:
            self.assertTrue(name.startswith("test_r3_") or name in ("r3_helpers.py", "r3_sensitivity.py"), name)
        taken = {}
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
            for f in files:
                if f.endswith(".py") and os.path.abspath(dirpath) != os.path.abspath(TESTS):
                    taken.setdefault(f, dirpath)
        for name in names:
            self.assertNotIn(name, taken, "%s already exists in %s" % (name, taken.get(name)))


class FilesChanged(unittest.TestCase):
    """Compared with the code start by git (committed state)."""

    def git(self, *args):
        return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True, timeout=60)

    def setUp(self):
        probe = self.git("cat-file", "-e", START + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")

    def test_only_the_allowed_paths_differ(self):
        out = self.git("diff", "--name-status", START, "HEAD")
        self.assertEqual(out.returncode, 0, out.stderr)
        changed = [line.split("\t") for line in out.stdout.splitlines()]
        for status, path in changed:
            if path == "tests/v2_history_ops/test_b17_scope.py":
                self.assertEqual(status, "M", path)
                continue
            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",
                                       "v2_history_restore/", "tests/v2_history_restore/",
                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (
                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")
            self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
            self.assertEqual(status, "A", path)                          # new files only
        paths = {p for _s, p in changed}
        self.assertIn("v2_history_restart/__init__.py", paths)
        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",
                          "v2_history_diagnose/__init__.py"})

    def test_no_existing_runtime_old_test_fixture_or_setting_differs(self):
        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",
                       "v2_history", "v2_history_ops", "main.py", "requirements.txt", ".github", "research",
                       "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md",
                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md")
        self.assertEqual(out.stdout.strip(), "")
        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",
                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")
        self.assertEqual(out.stdout.split(), ["tests/v2_history_ops/test_b17_scope.py"])

    def test_the_old_range_test_differs_in_exactly_the_three_allowed_places(self):
        out = self.git("diff", "-U0", START, "HEAD", "--", "tests/v2_history_ops/test_b17_scope.py")
        lines = out.stdout.splitlines()
        removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
        added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
        # point 1 touches two separate lines of the allowed list, so git shows four hunks for the three points
        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), 4)
        self.assertEqual(removed, [
            '            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/"))',
            '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md"))',
            '            self.assertFalse(path.endswith("__init__.py") and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")),',
            '                             path)',
            '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")'])
        self.assertEqual(added, [
            '            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",',
            '                                        "v2_history_restart/", "tests/v2_history_restart/",',
            '                                        "v2_history_restore/", "tests/v2_history_restore/",',
            '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
            '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",',
            '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
            '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
            '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
            '            self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"',
            '                             and path != "v2_history_restore/__init__.py"',
            '                             and path != "v2_history_diagnose/__init__.py"',
            '                             and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)',
            '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",',
            '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
            '                       ":(exclude)tests/v2_history_diagnose")'])


if __name__ == "__main__":
    unittest.main()
