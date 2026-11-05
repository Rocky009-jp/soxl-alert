"""Mutations of the N-01 fix (3b2c4ea) for the S4-B re-review (each one exact replacement, applied alone in a throwaway copy of the
tested commit; the whole tests/v2_notify suite is run). Usage: python s4bi_mutate.py <clean repo> <work dir> <python> [ids]"""
import json, os, shutil, subprocess, sys
REPO, WORK, PY = sys.argv[1], sys.argv[2], sys.argv[3]
ONLY = set(sys.argv[4:])
M = [
 ("F01", "outbox.py", "file_sync_only also syncs the directory",
  "                if self._durability == STRICT:\n                    ops.fsync_dir(self._root)", "                ops.fsync_dir(self._root)"),
 ("F02", "outbox.py", "strict skips the directory sync too",
  "                if self._durability == STRICT:\n                    ops.fsync_dir(self._root)", "                pass"),
 ("F03", "outbox.py", "any durability word is accepted",
  "        if type(durability) is not str or durability not in _MODES:\n            raise NotifyError(ARGS_INVALID, \"durability\")\n", ""),
 ("F04", "outbox.py", "the str type check is dropped (membership only)",
  "if type(durability) is not str or durability not in _MODES:", "if durability not in _MODES:"),
 ("F05", "outbox.py", "the default durability is file_sync_only",
  "def __init__(self, root, durability=STRICT, *, _ops=None):", "def __init__(self, root, durability=FILE_SYNC_ONLY_MODE, *, _ops=None):"),
]
results = []
for mid, fname, desc, old, new in M:
    if ONLY and mid not in ONLY:
        continue
    wt = os.path.join(WORK, mid)
    shutil.rmtree(wt, True)
    shutil.copytree(REPO, wt, symlinks=True)
    path = os.path.join(wt, "v2_notify", fname)
    src = open(path, encoding="utf-8").read()
    n = src.count(old)
    if n != 1:
        results.append({"id": mid, "desc": desc, "class": "PREP_FAILED", "count": n}); print(mid, "PREP_FAILED", n, flush=True); continue
    open(path, "w", encoding="utf-8").write(src.replace(old, new))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([PY, "-B", "-m", "unittest", "discover", "-s", "tests/v2_notify", "-p", "test_s4b_*.py"],
                       cwd=wt, env=env, capture_output=True, text=True, timeout=1800)
    tail = [l for l in p.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    failed = [l.split(" (")[0].replace("FAIL: ", "").replace("ERROR: ", "") for l in p.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
    cls = "DETECTED" if p.returncode != 0 else "NOT_DETECTED"
    results.append({"id": mid, "file": fname, "desc": desc, "class": cls, "summary": tail, "failed": failed[:5], "n_failed": len(failed)})
    print(mid, cls, tail, len(failed), failed[:2], flush=True)
    shutil.rmtree(wt, True)
json.dump(results, open(os.path.join(WORK, "mutation_%s.json" % ("_".join(sorted(ONLY)) or "all")), "w"), ensure_ascii=False, indent=1)
