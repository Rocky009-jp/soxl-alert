"""Mutations of the RN-01 fix (db5dc46) for the second S4-B re-review (each one exact replacement, applied alone in a throwaway copy of the
tested commit; the whole tests/v2_notify suite is run). Usage: python s4bi_mutate.py <clean repo> <work dir> <python> [ids]"""
import json, os, shutil, subprocess, sys
REPO, WORK, PY = sys.argv[1], sys.argv[2], sys.argv[3]
ONLY = set(sys.argv[4:])
M = [
 ("G01", "outbox.py", "strict does not refuse Windows at construction",
  "            if ops.is_windows():\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")\n", ""),
 ("G02", "outbox.py", "strict does not probe the directory sync",
  "                ops.probe_dir_sync(root)\n", "                pass\n"),
 ("G03", "outbox.py", "a failed probe is ignored",
  "            except _IO_ERRORS:\n                supported = False\n", "            except _IO_ERRORS:\n                supported = True\n"),
 ("G04", "outbox.py", "the probe runs before the Windows check",
  "            if ops.is_windows():\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")\n            supported = True\n            try:\n                ops.probe_dir_sync(root)\n            except _IO_ERRORS:\n                supported = False\n",
  "            supported = True\n            try:\n                ops.probe_dir_sync(root)\n            except _IO_ERRORS:\n                supported = False\n            if ops.is_windows():\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")\n"),
 ("G05", "outbox.py", "the refusal is raised inside the handler (context kept)",
  "            except _IO_ERRORS:\n                supported = False\n            if not supported:\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")",
  "            except _IO_ERRORS:\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")\n            if not supported:\n                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, \"durability\")"),
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
