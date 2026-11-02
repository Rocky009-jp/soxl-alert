"""Review-only realization of the B-5a scope edits, in a disposable repository.

No B-5 implementation is provided. Run with --repo pointing to a COPY at ac21980.
This prepares static literals once; the resulting tests do not generate expectations.
It makes a local-only commit so the old tests can inspect HEAD. Never pushes.
"""
import argparse
import ast
import pprint
import subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
args = ap.parse_args()
root = Path(args.repo).resolve()
def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, encoding='utf-8').strip()

assert git('rev-parse', 'HEAD') == 'ac219801d290ebb59b720f37a086103b6e1251c9'
assert not git('status', '--porcelain')
B17 = 'tests/v2_history_ops/test_b17_scope.py'
R307 = 'tests/v2_history_restart/test_r3_07_scope.py'
R409 = 'tests/v2_history_restore/test_r4_09_scope.py'
def replace_once(s, old, new):
    assert s.count(old) == 1, (s.count(old), old)
    return s.replace(old, new)
def write(p, s):
    (root / p).write_text(s, encoding='utf-8', newline='\n')
def diff_parts(start, path):
    lines = git('diff', '-U0', start, '--', path).splitlines()
    return ([s[1:] for s in lines if s.startswith('-') and not s.startswith('---')],
            [s[1:] for s in lines if s.startswith('+') and not s.startswith('+++')],
            [s.split(' @@')[0] for s in lines if s.startswith('@@')])

s = (root / B17).read_text(encoding='utf-8')
s = replace_once(s, '"v2_history_restore/", "tests/v2_history_restore/"))',
    '"v2_history_restore/", "tests/v2_history_restore/",\n'
    '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))')
s = replace_once(s, '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\n'
    '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))')
s = replace_once(s, '                             and path != "v2_history_restore/__init__.py"',
    '                             and path != "v2_history_restore/__init__.py"\n'
    '                             and path != "v2_history_diagnose/__init__.py"')
s = replace_once(s, '":(exclude)tests/v2_history_restore")',
    '":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")')
write(B17, s)

s = (root / R307).read_text(encoding='utf-8')
cut = s.index('    def test_the_old_range_test_differs_in_exactly_the_three_allowed_places')
tail, s = s[cut:], s[:cut]
s = replace_once(s, '"v2_history_restore/", "tests/v2_history_restore/")) or path in (',
    '"v2_history_restore/", "tests/v2_history_restore/",\n'
    '                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (')
s = replace_once(s, '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md")',
    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md", "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")')
s = replace_once(s, '{"v2_history_restart/__init__.py", "v2_history_restore/__init__.py"})',
    '{"v2_history_restart/__init__.py", "v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py"})')
s = replace_once(s, '":(exclude)tests/v2_history_restore")',
    '":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")')
s += tail
# Replace only the static expectation part inside the existing third method.
a = s.index('        # point 1 touches')
z = s.index('\n\n\nif __name__', a)
removed, added, hunks = diff_parts('b328844fdeda235cf95bf7851ba9e3d7d55aa7bb', B17)
s = s[:a] + ('        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), %d)\n'
             '        self.assertEqual(removed, %s)\n'
             '        self.assertEqual(added, %s)' %
             (len(hunks), repr(removed), repr(added))) + s[z:]
write(R307, s)

s = (root / R409).read_text(encoding='utf-8')
s = replace_once(s, '            self.assertTrue(allowed_path(path), "unexpected change: %s %s" % (status, path))',
    '            extra = path.startswith(("v2_history_diagnose/", "tests/v2_history_diagnose/")) or path == \\\n'
    '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"\n'
    '            self.assertTrue(allowed_path(path) or extra, "unexpected change: %s %s" % (status, path))')
s = replace_once(s, '{"v2_history_restore/__init__.py"})',
    '{"v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py"})')
s = replace_once(s, '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore")',
    '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore",\n'
    '                       ":(exclude)tests/v2_history_diagnose")')
a = s.index('B17_REMOVED = ')
z = s.index('\n\n\nclass Runtime', a)
parts = []
for name, path in [('B17', B17), ('R307', R307)]:
    for suffix, val in zip(('REMOVED', 'ADDED', 'HUNKS'), diff_parts('d82a5ced64658c2e736b82b1a2f1925636055417', path)):
        parts.append(name + '_' + suffix + ' = ' + pprint.pformat(val, width=110))
s = s[:a] + '\n'.join(parts) + s[z:]
write(R409, s)

for p in ('v2_history_diagnose/__init__.py', 'tests/v2_history_diagnose/test_d5_placeholder.py',
          'docs/implementation/V2_RECOVERY_S3B5_RESULT.md'):
    (root / p).parent.mkdir(parents=True, exist_ok=True)
    write(p, '# Review-only placeholder; no B-5a implementation.\n')
for p in (B17, R307, R409):
    def names(s):
        return [n.name for n in ast.walk(ast.parse(s)) if isinstance(n, ast.FunctionDef)]
    assert names(git('show', 'ac219801d290ebb59b720f37a086103b6e1251c9:' + p)) == names((root / p).read_text(encoding='utf-8'))
git('add', '--', B17, R307, R409, 'v2_history_diagnose', 'tests/v2_history_diagnose',
    'docs/implementation/V2_RECOVERY_S3B5_RESULT.md')
git('-c', 'user.name=Review Scratch', '-c', 'user.email=review@example.invalid', 'commit', '-m',
    'Scratch only: realize B-5a scope proposal without runtime')
print(git('diff', '--stat', 'ac219801d290ebb59b720f37a086103b6e1251c9', 'HEAD'))
print('Local-only scratch commit:', git('rev-parse', 'HEAD'))
