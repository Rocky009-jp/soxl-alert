"""Second re-review (db5dc46): tests/v2_notify 01-07 in one process where FileOps says it is Windows and the directory
sync and its probe raise PermissionError(13). Patched before the test helpers are imported, so their MODE follows the
host. Usage: python -B s4br2_windir_suite.py <repo>"""
import os, sys, unittest
REPO = sys.argv[1]
os.chdir(REPO); sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
from v2_persistence.local.fsops import FileOps
def _deny(self, path):
    raise PermissionError(13, "Permission denied")
FileOps.fsync_dir = _deny
FileOps.probe_dir_sync = _deny
FileOps.is_windows = lambda self: True
import s4b_helpers as H
print("helpers MODE:", H.MODE, "REAL_WINDOWS:", H.REAL_WINDOWS)
suite = unittest.defaultTestLoader.discover(os.path.join(REPO, "tests", "v2_notify"), pattern="test_s4b_0[1-7]*.py")
res = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
print("ran", res.testsRun, "failures", len(res.failures), "errors", len(res.errors), "skipped", len(res.skipped))
for t, _ in res.failures + res.errors:
    print("  ", t.id())
