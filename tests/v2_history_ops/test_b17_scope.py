"""B2-17: the runtime has no I/O, clock, network, process, thread, randomness, environment or new dependency; the new
package uses only the existing public names that the request allows; it builds none of the later stages; and no
existing file other than the two allowed ones differs from the code start."""
import ast
import os
import subprocess
import unittest

import ho_helpers as T

ROOT = T.ROOT
PKG = os.path.join(ROOT, "v2_history_ops")
START = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"

ALLOWED_STDLIB = {"copy", "json"}
ALLOWED_NAMES = {
    "v2_history": {"validate_history", "History", "encode_history", "HistoryCheck", "Boundary"},
    "v2_history.values": {"history_dict", "check_json"},                       # and the kind-name constants
    "v2_history.view": {"Segment", "project_segment", "normalize_command", "reasons_for_commands", "initial_state_dict"},
    "v2_history.common": {"basis_request_hash", "is_int", "is_hex64", "is_date", "same"},
    "v2_recovery.facts": {"FixedFacts", "FixedApply", "LedgerContext"},
    "v2_recovery.commands": {"check_commands"},
    "v2_recovery.project": {"resolve_core", "slice_check", "EffectiveLedger"},
    "v2_recovery.common": {"requested_text", "is_requested_text", "valid_request_id", "record_reason", "KIND_ACK",
                           "KIND_DECLARE"},
    "v2_recovery.ledger": {"copy_sessions", "parse_ledger", "ledger_digest", "sessions_digest", "Row"},
    "v2_recovery.errors": {"resolution_invalid"},
    "v2_persistence.codec": {"canonical_json", "sha256_text", "compute_event_hash", "CORE_SHA"},
    "v2_persistence.events": {"make_genesis_event", "make_apply_event", "snapshot_of", "session_dict", "project_context"},
    "v2_persistence.recompute": {"validate_snapshot"},
    "v2_persistence.runner": {"prepare_day"},
    "v2_persistence.plan": {"PREPARED", "NO_COMMIT", "ALREADY_APPLIED"},
    "v2_persistence.errors": {"PersistenceError"},
    "v2_core.fixture": {"parse_iso_date"},
    "v2_core.errors": {"CoreError", "InputError", "ConflictError"},
    "v2_core": {"SessionList", "MarketState", "parse_iso_date"},
}
KIND_CONSTANTS = {"ACK", "APPLY", "DECLARE_MISSING", "GENESIS", "RECOVERY_RESTORE", "RESTART_UNKNOWN",
                  "SCHEMA_MIGRATION"}
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "hashlib", "uuid", "webbrowser", "smtplib",
                     "datetime", "tests"}
NEVER_USED = {"Ctx", "SnapshotView", "validate_set", "make_records", "resolve_observations", "prepare_resolution_plan",
              "confirm_resolution_plan", "prepare_resolved_day"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen"}
LATER_STAGE_WORDS = ("unlock", "restore", "restart", "reinit", "outbox", "webhook", "discord", "snapshot.json",
                     "notify", "sheet", "CONSUME", "HistoryReplacement", "prefix", "diagnos")


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


class Imports(unittest.TestCase):
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
                    top = mod.split(".")[0]
                    self.assertNotIn(top, FORBIDDEN_IMPORTS, fname)
                    self.assertNotRegex(mod, r"^v2_persistence\.(local|store)", fname)
        self.assertGreater(count, 60)

    def test_no_name_of_the_old_machinery_appears_anywhere(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, NEVER_USED, fname)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, NEVER_USED, fname)

    def test_no_private_name_of_an_existing_package_is_used(self):
        """A leading underscore is used only on self / cls and on the package's own classes."""
        own_classes = {"HistoryAppendBatch", "HistoryResolutionPlan", "EffectiveView", "HistoryLedger", "_Frozen",
                       "HistoryResolutionConfirmResult", "HistoryDayResult"}
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    base = node.value
                    self.assertTrue(isinstance(base, ast.Name) and (base.id in ("self", "cls", "other", "obj")
                                                                    or base.id in own_classes),
                                    "%s uses ._%s of something else" % (fname, node.attr.lstrip("_")))


class NoSideEffects(unittest.TestCase):
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
                        self.assertNotIn(word.lower(), v.lower(), "%s: %s" % (fname, v))
        self.assertGreater(checked, 500)

    def test_the_public_names_are_exactly_the_documented_ones(self):
        import v2_history_ops as O
        self.assertEqual(sorted(O.__all__), sorted([
            "read_effective", "project_history_ledger", "prepare_history_day", "prepare_history_resolution_plan",
            "confirm_history_resolution_plan", "check_append_batch", "HistoryAppendBatch", "EffectiveView",
            "HistoryLedger", "HistoryDayResult", "HistoryResolutionPlan", "HistoryResolutionConfirmResult",
            "PREPARED", "NO_COMMIT", "ALREADY_APPLIED", "READY", "NO_CHANGE", "CONFIRMED_IN_MEMORY", "DAILY",
            "RESOLUTION"]))
        for name in O.__all__:
            self.assertTrue(hasattr(O, name), name)

    def test_the_runtime_does_not_import_tests_and_has_no_dependency_file(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("tests", "ho_helpers", "h_helpers")), fname)
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(os.path.exists(os.path.join(PKG, name)))


class FilesChanged(unittest.TestCase):
    """Compared with the code start by git. The two allowed existing files are checked line by line."""

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
            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/"))
                       or path in ("v2_recovery/facts.py", "v2_recovery/commands.py",
                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md"))
            self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
            if not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")):
                if path != "v2_recovery/commands.py":
                    self.assertEqual(status, "A", path)                       # new files only
                else:
                    self.assertEqual(status, "M", path)
        paths = {p for _s, p in changed}
        self.assertIn("v2_recovery/facts.py", paths)
        self.assertIn("v2_recovery/commands.py", paths)
        for path in paths:
            self.assertFalse(path.endswith("__init__.py") and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")),
                             path)

    def test_commands_py_changes_are_the_two_allowed_ones_only(self):
        out = self.git("diff", "-U0", START, "HEAD", "--", "v2_recovery/commands.py")
        removed = [l[1:] for l in out.stdout.splitlines() if l.startswith("-") and not l.startswith("---")]
        added = [l[1:] for l in out.stdout.splitlines() if l.startswith("+") and not l.startswith("+++")]
        self.assertEqual(removed, ["    else:", "def make_records(ctx, existing, commands, basis, request_hash):",
                                   '    """Evidence for all commands, then the new records (not yet hashed into a set)."""'])
        text = "\n".join(added)
        self.assertIn("def check_commands(ctx, existing, commands):", text)
        self.assertIn('elif "resolution_seq" in ref:', text)
        self.assertIn("extras = check_commands(ctx, existing, commands)", text)
        self.assertIn('rec["seq"] == ref["seq"]', text)

    def test_existing_tests_and_fixtures_are_untouched(self):
        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")
        self.assertEqual(out.stdout.strip(), "")
        out = self.git("diff", "--name-only", START, "HEAD", "--", "main.py", "requirements.txt", ".github", "research",
                       "docs/STATUS.md", "docs/ROADMAP.md", "CLAUDE.md")
        self.assertEqual(out.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
