"""S4C-16: the static range of the runtime (read from the files about to be tested). It brings in only os, re, shutil, stat,
subprocess and tempfile from the standard library, v2_core.errors, v2_history_publish, v2_history_local,
v2_persistence.local.errors and v2_notify (and its own modules); only git.py starts a process, with one subprocess.run and an
argument list; the push list is written once and holds none of --force, -f, --force-with-lease, --mirror, --delete, --quiet
or a ref that starts with +; the commands are the nine of the design; no socket, url, http, time, random, thread or secrets
module; no clock read and no sleep; no private name of another class is read; no exception is raised inside an except
block; the arguments of every error of this package are fixed words."""
import ast
import unittest

import s4c_helpers as H

RUNTIME = tuple("v2_git_store/%s.py" % n for n in ("__init__", "git", "history", "outbox"))
STANDARD = {"os", "re", "shutil", "stat", "subprocess", "tempfile"}
ALLOWED_FROM = {
    "v2_core.errors": {"CoreError"},
    "v2_history_publish": {"APPEND", "CREATE", "GENESIS", "HistoryPublication", "check_publication", "history_bytes",
                           "read_history_bytes", "reconcile_publication"},
    "v2_history_local": {"INITIALIZED", "PUBLISHED", "HistoryStoreResult"},
    "v2_persistence.local.errors": {"LocalStoreError"},
    "v2_notify": {"DAMAGED", "KINDS", "LocalOutbox", "NotifyError", "OutboxEntry"},
    "v2_notify.values": {"ARGS_INVALID", "OUTBOX_IO_ERROR", "date_text", "request_id_text"},
}
OWN = {".git", ".history", ".outbox"}
FORBIDDEN_NAMES = {"socket", "urllib", "http", "time", "random", "threading", "secrets", "datetime", "sys", "io", "pathlib",
                   "logging", "asyncio", "multiprocessing", "signal", "ssl", "ctypes", "sqlite3", "glob", "uuid", "requests",
                   "smtplib", "getpass", "pwd", "hashlib", "json"}
FORBIDDEN_CALLS = {"input", "eval", "exec", "compile", "__import__", "print", "setattr", "globals", "locals", "breakpoint",
                   "exit", "quit", "getattr_secret"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "putenv", "system", "popen",
                   "random", "token_hex", "token_bytes", "Popen", "check_output", "check_call", "call", "spawn", "fork",
                   "connect", "sendall", "urlopen", "chdir", "rename", "replace", "chmod", "symlink", "link", "write_text",
                   "write_bytes", "removedirs", "rmdir", "remove"}
COMMANDS = {"fetch", "ls-remote", "rev-parse", "ls-tree", "cat-file", "hash-object", "mktree", "commit-tree", "push"}
BANNED_COMMANDS = {"checkout", "reset", "add", "commit", "merge", "rebase", "update-ref", "symbolic-ref", "pull", "clean",
                   "stash", "branch", "switch", "restore", "init", "clone", "config", "gc", "tag", "remote", "worktree",
                   "cherry-pick", "revert", "apply", "am", "fsck", "prune", "filter-branch", "notes", "submodule"}
PUSH_BANNED = {"--force", "-f", "--force-with-lease", "--mirror", "--delete", "--quiet", "-q", "--prune", "--all", "--tags",
               "--follow-tags", "-d", "--no-verify"}
ERRORS = {"GitError", "LocalStoreError", "NotifyError"}


def trees():
    return {p: ast.parse(H.read_source(p)) for p in RUNTIME}


def lists_starting_with_a_command(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) \
                and isinstance(node.elts[0].value, str) and node.elts[0].value in COMMANDS | BANNED_COMMANDS:
            found.append(node)
    return found


def module_constants(tree):
    return {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}


class Runtime(unittest.TestCase):
    def test_the_package_is_the_four_files_of_the_design(self):
        for path in RUNTIME:
            H.read_source(path)
        self.assertLessEqual(len(RUNTIME), 4)

    def test_the_imports_are_the_list_of_the_design(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, STANDARD, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        self.assertIn("." * node.level + (node.module or ""), OWN, path)
                        continue
                    if node.module in STANDARD:
                        continue
                    self.assertIn(node.module, ALLOWED_FROM, "%s imports from %s" % (path, node.module))
                    self.assertTrue({a.name for a in node.names} <= ALLOWED_FROM[node.module],
                                    "%s imports %s from %s" % (path, [a.name for a in node.names], node.module))

    def test_no_network_thread_clock_random_sleep_or_forbidden_module_is_used(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, "%s uses .%s" % (path, node.attr))
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_NAMES, "%s uses %s" % (path, node.id))

    def test_only_git_py_starts_a_process_with_one_subprocess_run_and_an_argument_list(self):
        for path, tree in trees().items():
            uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "subprocess"]
            if path != "v2_git_store/git.py":
                self.assertEqual(uses, [], path)
        tree = trees()["v2_git_store/git.py"]
        runs = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.run"]
        self.assertEqual(len(runs), 1)
        call = runs[0]
        self.assertIsInstance(call.args[0], ast.Name)                           # `command`, a list built above
        self.assertEqual(call.args[0].id, "command")
        self.assertEqual(sorted(k.arg for k in call.keywords if k.arg), ["capture_output", "cwd", "env", "timeout"])
        for k in call.keywords:
            self.assertNotEqual(k.arg, "shell")
        attrs = {ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Attribute) and ast.unparse(n.value) == "subprocess"}
        self.assertEqual(attrs, {"subprocess.run", "subprocess.TimeoutExpired", "subprocess.DEVNULL"})
        command = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "command"]
        self.assertEqual(len(command), 1)
        head = [ast.unparse(e) for e in command[0].value.left.elts]
        self.assertEqual(head, ["'git'", "'-c'", "'core.autocrlf=false'", "'-c'", "'commit.gpgsign=false'"])

    def test_the_commands_are_the_nine_of_the_design_and_the_push_is_written_once_without_force(self):
        used, pushes, other = set(), [], []
        for path, tree in trees().items():
            for node in lists_starting_with_a_command(tree):
                name = node.elts[0].value
                used.add(name)
                self.assertNotIn(name, BANNED_COMMANDS, path)
                (pushes if name == "push" else other).append((path, node))
        self.assertEqual(used, COMMANDS)
        self.assertEqual(len(pushes), 1)
        path, push = pushes[0]
        self.assertEqual(path, "v2_git_store/git.py")
        self.assertEqual([ast.unparse(e) for e in push.elts[:3]], ["'push'", "'--porcelain'", 'self.remote'])
        self.assertEqual(len(push.elts), 4)
        self.assertIsInstance(push.elts[3], ast.BinOp)
        self.assertEqual(push.elts[3].left.value, "%s:refs/heads/%s")
        for node in ast.walk(push):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn(node.value, PUSH_BANNED)
                self.assertFalse(node.value.startswith("+"))
        for path, tree in trees().items():                  # no force-like word anywhere outside a comment or doc
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in ("-q",):
                    if node.value.startswith("--") or node.value in ("-f", "-d"):
                        self.assertIn(node.value, ("--porcelain", "--no-tags", "--quiet", "--heads", "--verify", "--stdin"),
                                      "%s uses %s" % (path, node.value))

    def test_the_fetch_goes_only_to_the_private_namespace_and_never_to_a_branch(self):
        tree = trees()["v2_git_store/git.py"]
        fetches = [n for n in lists_starting_with_a_command(tree) if n.elts[0].value == "fetch"]
        self.assertEqual(len(fetches), 1)
        spec = fetches[0].elts[-1]
        self.assertEqual(spec.left.value, "+refs/heads/%s:refs/v2remote/%s")
        for path, t in trees().items():
            for node in ast.walk(t):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn("refs/remotes", node.value)

    def test_the_environment_is_read_only_to_make_the_copy_for_git(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and ast.unparse(node) == "os.environ":
                    self.assertEqual(path, "v2_git_store/git.py")
        tree = trees()["v2_git_store/git.py"]
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_environment"][0]
        self.assertIn("os.environ", ast.unparse(fn))
        self.assertIn("startswith('GIT_')", ast.unparse(fn))
        for path, t in trees().items():
            for node in ast.walk(t):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertIn(node.attr, ("path", "environ", "fsdecode", "fsencode", "listdir", "unlink", "lstat"),
                                  "%s uses os.%s" % (path, node.attr))

    def test_no_private_name_of_another_class_is_read_and_the_outbox_overrides_only_the_public_methods(self):
        for path, tree in trees().items():
            for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
                own = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
                assigned = {n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                            and isinstance(n.value, ast.Name) and n.value.id == "self"}
                for node in ast.walk(cls):
                    if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                        self.assertIsInstance(node.value, ast.Name, "%s %s" % (path, ast.unparse(node)))
                        self.assertEqual(node.value.id, "self", "%s %s" % (path, ast.unparse(node)))
                        self.assertIn(node.attr, own | assigned, "%s reads %s" % (path, ast.unparse(node)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    self.assertTrue(isinstance(node.value, ast.Name) and node.value.id == "self",
                                    "%s reads %s" % (path, ast.unparse(node)))
        outbox = trees()["v2_git_store/outbox.py"]
        cls = [n for n in outbox.body if isinstance(n, ast.ClassDef)][0]
        self.assertEqual([ast.unparse(b) for b in cls.bases], ["LocalOutbox"])
        public = {n.name for n in cls.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
        self.assertEqual(public, {"load", "resend_ids", "claim", "record", "initialize"})
        dunder = {n.name for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith("__")}
        self.assertEqual(dunder, {"__init__", "__repr__"})
        base_private = {"_base", "_create", "_read", "_check", "_ops", "_root", "_durability"}
        own_names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertFalse(own_names & base_private)
        calls = [ast.unparse(n.func) for n in ast.walk(cls) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and ast.unparse(n.func).startswith(("LocalOutbox.", "super()."))]
        self.assertEqual(sorted(set(calls)), ["LocalOutbox.claim", "LocalOutbox.record", "super().__init__", "super().load",
                                               "super().resend_ids"])

    def test_no_exception_is_raised_inside_an_except_block(self):
        for path, tree in trees().items():
            for handler in [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]:
                for node in ast.walk(handler):
                    self.assertNotIsInstance(node, ast.Raise, "%s raises inside an except block" % path)

    def test_the_arguments_of_every_error_of_this_package_are_fixed_words(self):
        for path, tree in trees().items():
            constants = module_constants(tree) | {"ARGS_INVALID", "GIT_ARGS_INVALID", "FAILED", "OUTBOX_IO_ERROR",
                                                  "ALREADY_INITIALIZED"}
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ERRORS:
                    for arg in node.args + [k.value for k in node.keywords]:
                        ok = (isinstance(arg, ast.Constant) and isinstance(arg.value, str)) or (
                            isinstance(arg, ast.Name) and arg.id in constants)
                        self.assertTrue(ok, "%s %s" % (path, ast.unparse(node)))
                if isinstance(node, ast.Raise) and node.exc is not None:
                    exc = node.exc
                    if isinstance(exc, ast.Call):
                        self.assertIn(ast.unparse(exc.func), ERRORS, "%s %s" % (path, ast.unparse(node)))
                    else:
                        self.assertIsInstance(exc, ast.Name, "%s %s" % (path, ast.unparse(node)))
            for node in ast.walk(tree):                     # no output of git is placed in a string that is shown or kept
                if isinstance(node, ast.Attribute) and node.attr in ("stderr", "args", "__traceback__", "__context__",
                                                                     "__cause__", "output"):
                    self.fail("%s reads .%s" % (path, node.attr))

    def test_standard_output_of_git_is_read_only_in_git_py(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "stdout":
                    self.assertEqual(path, "v2_git_store/git.py")

    def test_files_are_opened_only_by_the_outbox_to_read_or_to_make_a_mirror_file(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                    self.assertEqual(path, "v2_git_store/outbox.py")
                    self.assertIn(ast.unparse(node.args[1]), ("'rb'", "'xb'"))

    def test_the_public_names_of_the_request(self):
        import v2_git_store
        for name in ("Git", "GitError", "GitHistoryStore", "GitOutbox", "OK", "REJECTED", "UNCERTAIN"):
            self.assertTrue(hasattr(v2_git_store, name), name)
        self.assertTrue(issubclass(v2_git_store.GitError, H.CoreError))
        self.assertTrue(issubclass(v2_git_store.GitOutbox, H.N.LocalOutbox))
        self.assertEqual((v2_git_store.OK, v2_git_store.REJECTED, v2_git_store.UNCERTAIN), ("OK", "REJECTED", "UNCERTAIN"))


if __name__ == "__main__":
    unittest.main()
