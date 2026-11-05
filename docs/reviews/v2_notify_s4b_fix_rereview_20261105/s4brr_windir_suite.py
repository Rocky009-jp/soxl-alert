"""tests/v2_notify 01-07 with FileOps.fsync_dir raising PermissionError(13) in this process (Windows-like), on the fixed
commit: shows whether the S4-B tests can run where a directory cannot be synced. Usage: python -B s4brr_windir_suite.py <repo>"""
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
failed = sorted({t.id().split(".")[0] for t, _ in res.failures + res.errors})
print("modules with a failure:", failed)
print("Durability class failures:", sorted(t.id().split(".")[-1] for t, _ in res.failures + res.errors if ".Durability." in t.id()))
