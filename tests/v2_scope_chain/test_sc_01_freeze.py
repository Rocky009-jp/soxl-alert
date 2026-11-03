"""SC-01: the five accepted range tests are frozen at the end of their range.

For each range test (b17, r3_07, r4_09, d5_08, a5_08) this reads the file at REV, the file at the code start (START of
test_sc_03_scope) and the file at the accepted end of its range, all from Git, and checks that

  * the part that is not frozen is the same text as at the code start;
  * the frozen part (class FilesChanged and the constants only it uses) differs from its text at the end of the range
    only in the replacement lines pinned below (the five substitutions of the freeze: the code token "HEAD" becomes END,
    the working-tree blob becomes the blob at END, the working-tree read becomes git show END:path, the working-tree
    listing becomes git ls-tree END, setUp also skips when END is missing);
  * only END, `import io` and git_show_at_end are added at the top level;
  * the test methods, the assert calls and the skipTest calls are the same as at the end of the range;
  * the frozen part reads nothing from the working tree and has no code token "HEAD".
Nothing here reads the working tree; a tree without history skips.
"""
import ast
import difflib
import unittest

import sc_helpers as C
from test_sc_03_scope import REV, START

# path: (END of the range, names of the frozen top-level elements)
FROZEN = {
    "tests/v2_history_ops/test_b17_scope.py": ("b328844fdeda235cf95bf7851ba9e3d7d55aa7bb", ("FilesChanged",)),
    "tests/v2_history_restart/test_r3_07_scope.py": ("d82a5ced64658c2e736b82b1a2f1925636055417", ("FilesChanged",)),
    "tests/v2_history_restore/test_r4_09_scope.py": (
        "ac219801d290ebb59b720f37a086103b6e1251c9",
        ("FilesChanged", "B17_REMOVED", "B17_ADDED", "B17_HUNKS", "R307_REMOVED", "R307_ADDED", "R307_HUNKS")),
    "tests/v2_history_diagnose/test_d5_08_scope.py": ("c8ba08f15ea28248a9fe7924f32ce136fc16d5e6",
                                                      ("FilesChanged", "PINNED")),
    "tests/v2_history_adopt/test_a5_08_scope.py": ("b626c98af5f01bc94e7b41d86aadde9663695eb9",
                                                   ("FilesChanged", "git", "current_text")),
}
# path: the START the range test must have
STARTS = {
    "tests/v2_history_ops/test_b17_scope.py": "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e",
    "tests/v2_history_restart/test_r3_07_scope.py": "b328844fdeda235cf95bf7851ba9e3d7d55aa7bb",
    "tests/v2_history_restore/test_r4_09_scope.py": "d82a5ced64658c2e736b82b1a2f1925636055417",
    "tests/v2_history_diagnose/test_d5_08_scope.py": "ac219801d290ebb59b720f37a086103b6e1251c9",
    "tests/v2_history_adopt/test_a5_08_scope.py": "c8ba08f15ea28248a9fe7924f32ce136fc16d5e6",
}
HELPER_STARTS = {
    "tests/v2_history_restart/r3_helpers.py": "b328844fdeda235cf95bf7851ba9e3d7d55aa7bb",
    "tests/v2_history_restore/r4_helpers.py": "d82a5ced64658c2e736b82b1a2f1925636055417",
}
ADDED_AT_TOP = {"END", "git_show_at_end"}
SUBSTITUTED_LINES = 91

# path: (lines of the frozen part at the end of the range that are replaced, the lines that replace them)
PINNED_REPLACEMENTS = {
    'tests/v2_history_ops/test_b17_scope.py': (
        ['        out = self.git("diff", "--name-status", START, "HEAD")',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", "v2_recovery/commands.py")',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "main.py", "requirements.txt", ".github", "research",'],
        ['        if probe.returncode == 0:',
         '            probe = self.git("cat-file", "-e", END + "^{commit}")',
         '        out = self.git("diff", "--name-status", START, END)',
         '        out = self.git("diff", "-U0", START, END, "--", "v2_recovery/commands.py")',
         '        out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_ops")',
         '        out = self.git("diff", "--name-only", START, END, "--", "main.py", "requirements.txt", ".github", "research",']),
    'tests/v2_history_restart/test_r3_07_scope.py': (
        ['        out = self.git("diff", "--name-status", START, "HEAD")',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart")',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", "tests/v2_history_ops/test_b17_scope.py")'],
        ['        if probe.returncode == 0:',
         '            probe = self.git("cat-file", "-e", END + "^{commit}")',
         '        out = self.git("diff", "--name-status", START, END)',
         '        out = self.git("diff", "--name-only", START, END, "--", "v2_core", "v2_persistence", "v2_recovery",',
         '        out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_restart")',
         '        out = self.git("diff", "-U0", START, END, "--", "tests/v2_history_ops/test_b17_scope.py")']),
    'tests/v2_history_restore/test_r4_09_scope.py': (
        ['        out = self.git("diff", "--name-status", START, "HEAD")',
         '                self.assertNotEqual(self.git("hash-object", path).stdout.strip(), blob)     # the one corrected file',
         '            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_history_restart", "tests/v2_history_restart",',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore")',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", path)',
         '            with open(os.path.join(ROOT, path), encoding="utf-8") as f:',
         '        with open(os.path.join(ROOT, SCOPE_TESTS[1]), encoding="utf-8") as f:',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", SCOPE_TESTS[1])'],
        ['        if probe.returncode == 0:',
         '            probe = self.git("cat-file", "-e", END + "^{commit}")',
         '        out = self.git("diff", "--name-status", START, END)',
         '                self.assertNotEqual(self.git("rev-parse", END + ":" + path).stdout.strip(), blob)     # the one corrected file',
         '            here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)',
         '        out = self.git("diff", "--name-only", START, END, "--", "v2_history_restart", "tests/v2_history_restart",',
         '        out = self.git("diff", "--name-only", START, END, "--", "v2_core", "v2_persistence", "v2_recovery",',
         '        out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_restore")',
         '        out = self.git("diff", "-U0", START, END, "--", path)',
         '            with io.StringIO(git_show_at_end(path)) as f:',
         '        with io.StringIO(git_show_at_end(SCOPE_TESTS[1])) as f:',
         '        out = self.git("diff", "-U0", START, END, "--", SCOPE_TESTS[1])']),
    'tests/v2_history_diagnose/test_d5_08_scope.py': (
        ['        out = self.git("diff", "--name-status", START, "HEAD")',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_diagnose",',
         '        out = self.git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC)',
         '            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)',
         '            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", path)',
         '            with open(os.path.join(ROOT, path), encoding="utf-8") as f:',
         '        out = self.git("diff", "-U0", START, "HEAD", "--", path)',
         '        with open(os.path.join(ROOT, path), encoding="utf-8") as f:',
         '        with open(os.path.join(ROOT, SCOPE_TESTS[2]), encoding="utf-8") as f:'],
        ['        if probe.returncode == 0:',
         '            probe = self.git("cat-file", "-e", END + "^{commit}")',
         '        out = self.git("diff", "--name-status", START, END)',
         '        out = self.git("diff", "--name-only", START, END, "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)',
         '        out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_diagnose",',
         '        out = self.git("diff", "--name-only", START, END, "--", "docs", ":(exclude)%s" % RESULT_DOC)',
         '            here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)',
         '            here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)',
         '        out = self.git("diff", "-U0", START, END, "--", path)',
         '            with io.StringIO(git_show_at_end(path)) as f:',
         '        out = self.git("diff", "-U0", START, END, "--", path)',
         '        with io.StringIO(git_show_at_end(path)) as f:',
         '        with io.StringIO(git_show_at_end(SCOPE_TESTS[2])) as f:']),
    'tests/v2_history_adopt/test_a5_08_scope.py': (
        ['        out = git("diff", "--name-status", START, "HEAD")',
         '        out = git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS)',
         '            out = git("diff", "--name-only", START, "HEAD", "--", root, *[":(exclude)%s" % p for p in kept])',
         '        out = git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_adopt",',
         '        out = git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC)',
         '            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)',
         '            out = git("diff", "--name-only", START, "HEAD", "--", "docs/implementation/" + name)',
         '        out = git("diff", "-U0", START, "HEAD", "--", path)',
         '        out = git("diff", "-U0", START, "HEAD", "--", path)',
         '        names = sorted(f for f in os.listdir(os.path.join(ROOT, "v2_history")) if f.endswith(".py"))',
         '    with open(os.path.join(ROOT, path), encoding="utf-8") as f:'],
        ['        if probe.returncode == 0:',
         '            probe = git("cat-file", "-e", END + "^{commit}")',
         '        out = git("diff", "--name-status", START, END)',
         '        out = git("diff", "--name-only", START, END, "--", *UNCHANGED_ROOTS)',
         '            out = git("diff", "--name-only", START, END, "--", root, *[":(exclude)%s" % p for p in kept])',
         '        out = git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_adopt",',
         '        out = git("diff", "--name-only", START, END, "--", "docs", ":(exclude)%s" % RESULT_DOC)',
         '            here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)',
         '            out = git("diff", "--name-only", START, END, "--", "docs/implementation/" + name)',
         '        out = git("diff", "-U0", START, END, "--", path)',
         '        out = git("diff", "-U0", START, END, "--", path)',
         '        names = sorted(os.path.basename(p) for p in git("ls-tree", "--name-only", END, "v2_history/").stdout.split()',
         '                       if p.endswith(".py"))',
         '    with io.StringIO(git_show_at_end(path)) as f:']),
}


def frozen_nodes(tree, names):
    found = C.top_level(tree)
    return [found[n] for n in names]


def frozen_lines(text, names):
    tree = ast.parse(text)
    return [C.node_text(text, node) for node in frozen_nodes(tree, names)]


def replaced_lines(before, after):
    removed, added = [], []
    for old, new in zip(before, after):
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag != "equal":
                removed.extend(old[i1:i2])
                added.extend(new[j1:j2])
    return removed, added


class FrozenRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skip_reason = None
        if not C.commit_exists(START):
            cls.skip_reason = "the code start commit is not available in this checkout"
            return
        for path, (end, _names) in sorted(FROZEN.items()):
            if not C.commit_exists(end) or not C.commit_exists(STARTS[path]):
                cls.skip_reason = "a commit of the frozen ranges is not available in this checkout"
                return
        if not C.commit_exists(REV):
            cls.skip_reason = "the revision under test is not available"

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def texts(self, path):
        end, names = FROZEN[path]
        rev_text, start_text, end_text = C.show(REV, path), C.show(START, path), C.show(end, path)
        for text in (rev_text, start_text, end_text):
            self.assertIsNotNone(text, path)
        return rev_text, start_text, end_text, end, names

    def test_the_ranges_are_the_accepted_ones(self):
        """F-02: START and END of the five range tests, as the code reads them (the two helpers' constants too)."""
        for path, (end, _names) in sorted(FROZEN.items()):
            tree = ast.parse(C.show(REV, path))
            directory = path.rsplit("/", 1)[0]
            self.assertEqual(C.read_constant(tree, "START", directory, REV), (True, STARTS[path]), path)
            self.assertEqual(C.read_constant(tree, "END", directory, REV), (True, end), path)
        for path, start in sorted(HELPER_STARTS.items()):
            tree = ast.parse(C.show(REV, path))
            self.assertEqual(C.read_constant(tree, "FIXED_START", path.rsplit("/", 1)[0], REV), (True, start), path)
        ends = [end for end, _names in FROZEN.values()]
        self.assertEqual(sorted(STARTS.values()), sorted(
            ["adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"] + ends[:-1]))        # the chain has no gap

    def test_the_part_that_is_not_frozen_is_the_text_of_the_code_start(self):
        """F-05: outside the frozen elements and the three added ones, every non-blank line is the code start's line."""
        for path, (_end, names) in sorted(FROZEN.items()):
            rev_text, start_text, _end_text, _e, names = self.texts(path)
            rev_tree, start_tree = ast.parse(rev_text), ast.parse(start_text)
            rev_top, start_top = C.top_level(rev_tree), C.top_level(start_tree)
            added = [rev_top[n] for n in sorted(ADDED_AT_TOP)] + [n for n in rev_tree.body if C.is_import_io(n)]
            before = C.lines_of(start_text, [start_top[n] for n in names] + [n for n in start_tree.body
                                                                          if C.is_import_io(n)])
            after = C.lines_of(rev_text, [rev_top[n] for n in names] + added)
            self.assertEqual(after, before, path)

    def test_only_end_import_io_and_git_show_at_end_are_added(self):
        """F-05: three added top-level elements, none removed."""
        for path in sorted(FROZEN):
            rev_text, start_text, _end_text, _end, _names = self.texts(path)
            rev_tree, start_tree = ast.parse(rev_text), ast.parse(start_text)
            rev_top, start_top = C.top_level(rev_tree), C.top_level(start_tree)
            self.assertEqual(set(rev_top) - set(start_top), ADDED_AT_TOP, path)
            self.assertEqual(set(start_top) - set(rev_top), set(), path)
            self.assertEqual(len(rev_tree.body), len(start_tree.body) + 3, path)
            self.assertEqual(sum(1 for n in rev_tree.body if C.is_import_io(n)), 1, path)
            self.assertEqual(sum(1 for n in start_tree.body if C.is_import_io(n)), 0, path)
            self.assertEqual(len(C.node_text(rev_text, rev_top["END"])), 1, path)

    def test_the_frozen_part_differs_from_the_end_of_its_range_only_in_the_pinned_lines(self):
        """F-03: the only differences are the replacement lines pinned in PINNED_REPLACEMENTS (91 lines in all)."""
        total = 0
        for path in sorted(FROZEN):
            rev_text, _start_text, end_text, _end, names = self.texts(path)
            removed, added = replaced_lines(frozen_lines(end_text, names), frozen_lines(rev_text, names))
            self.assertEqual((removed, added), PINNED_REPLACEMENTS[path], path)
            total += len(removed) + len(added)
        self.assertEqual(total, SUBSTITUTED_LINES)

    def test_tests_asserts_and_skips_are_those_of_the_end_of_the_range(self):
        for path in sorted(FROZEN):
            rev_text, _start_text, end_text, _end, _names = self.texts(path)
            rev_tree, end_tree = ast.parse(rev_text), ast.parse(end_text)
            self.assertEqual(C.test_method_names(rev_tree), C.test_method_names(end_tree), path)
            self.assertEqual(C.count_calls(rev_tree, prefix="assert"), C.count_calls(end_tree, prefix="assert"), path)
            self.assertEqual(C.count_calls(rev_tree, exact="skipTest"), C.count_calls(end_tree, exact="skipTest"), path)
            self.assertEqual(C.count_calls(rev_tree, exact="skipTest"), 1, path)
            self.assertGreater(len(C.test_method_names(rev_tree)), 5, path)

    def test_the_frozen_part_reads_nothing_from_the_working_tree_and_has_no_code_head(self):
        """F-04: no code token "HEAD", no open / hash-object / listdir / walk in the frozen elements; "HEAD" inside a
        longer pinned string stays (r3_07 pins a diff that contains it)."""
        forbidden_os = {"listdir", "walk", "scandir", "glob", "isfile", "isdir", "exists", "join"}
        forbidden_any = {"read_text", "read_bytes", "listdir", "scandir", "isfile", "isdir"}
        for path in sorted(FROZEN):
            rev_text, _start_text, end_text, _end, names = self.texts(path)
            rev_tree, end_tree = ast.parse(rev_text), ast.parse(end_text)
            rev_nodes, end_nodes = frozen_nodes(rev_tree, names), frozen_nodes(end_tree, names)
            for node in rev_nodes:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        self.assertNotEqual(sub.value, "HEAD", path)
                        self.assertNotEqual(sub.value, "hash-object", path)
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        self.assertNotEqual(sub.func.id, "open", path)
                    if isinstance(sub, ast.Attribute):
                        self.assertNotIn(sub.attr, forbidden_any, path)
                        root = sub
                        while isinstance(root, ast.Attribute):
                            root = root.value
                        if isinstance(root, ast.Name) and root.id in ("os", "glob", "pathlib"):
                            self.assertNotIn(sub.attr, forbidden_os, path)

            def strings(nodes, exact):
                count = 0
                for node in nodes:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and (
                                (sub.value == "HEAD") if exact else ("HEAD" in sub.value)):
                            count += 1
                return count
            self.assertEqual(strings(end_nodes, False) - strings(end_nodes, True), strings(rev_nodes, False), path)
        r3 = self.texts("tests/v2_history_restart/test_r3_07_scope.py")[0]
        self.assertIn('START, "HEAD"', r3)                  # the pinned old range test text keeps its own "HEAD"

    def test_the_frozen_part_reads_the_end_from_git(self):
        """F-03/F-04: every range test defines git_show_at_end, and the frozen part names END."""
        for path in sorted(FROZEN):
            rev_text, _start_text, _end_text, _end, names = self.texts(path)
            top = C.top_level(ast.parse(rev_text))
            body = " ".join(" ".join(C.node_text(rev_text, top["git_show_at_end"])).split())
            self.assertIn('"git", "-C", ROOT, "show", "%s:%s" % (END, path)', body, path)
            used = {n.id for node in frozen_nodes(ast.parse(rev_text), names) for n in ast.walk(node)
                    if isinstance(n, ast.Name)}
            self.assertIn("END", used, path)
            if path.endswith("test_a5_08_scope.py"):
                self.assertIn("git_show_at_end", used, path)


if __name__ == "__main__":
    unittest.main()
