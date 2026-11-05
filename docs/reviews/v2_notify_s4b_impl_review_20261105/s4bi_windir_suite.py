"""Run tests/v2_notify with FileOps.fsync_dir raising PermissionError(13) in this process (Windows-like directory sync).
The child processes of test_s4b_08 are not patched. Usage: python -B s4bi_windir_suite.py <repo>"""
import os, sys, unittest
REPO = sys.argv[1]
os.chdir(REPO); sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
from v2_persistence.local.fsops import FileOps
def _deny(self, path):
    raise PermissionError(13, "Permission denied")
FileOps.fsync_dir = _deny
suite = unittest.defaultTestLoader.discover(os.path.join(REPO, "tests", "v2_notify"), pattern="test_s4b_0[1-7]*.py")
res = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
print("ran", res.testsRun, "failures", len(res.failures), "errors", len(res.errors))
