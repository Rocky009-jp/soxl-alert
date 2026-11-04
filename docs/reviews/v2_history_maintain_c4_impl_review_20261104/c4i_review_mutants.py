"""C-4 implementation review: independent mutants (not in the implementer's list of 32).

usage: python -B c4i_mutants.py <clean repo> <python> <workdir> [ids]
Each mutant: a copy of the working tree (no .git), one textual replacement in v2_history_maintain, then the new suite
test_c4_01..08 (runtime tests; the scope tests 09 read git and are left out) with -f. Detected = rc != 0.
"""
import os
import shutil
import subprocess
import sys
import time

REPO, PY, WORK = sys.argv[1], sys.argv[2], sys.argv[3]
ONLY = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
S, V = "v2_history_maintain/store.py", "v2_history_maintain/values.py"

MUTANTS = [
    ("V01", S, "wanted = (PUBLISHED,) if has_v else (PUBLISHED, PUBLISHED_THEN_EXTENDED)",
     "wanted = (PUBLISHED, PUBLISHED_THEN_EXTENDED)", "migrate both: accept an extended history"),
    ("V02", S, "self._q_check_names(entries, {V1_NAME})\n        self._q_manifest(kpath, entries, self._manifest_for(info, OP_MIGRATION), ctx)\n        self._publish",
     "self._q_check_names(entries, {V1_NAME, HISTORY_NAME})\n        self._q_manifest(kpath, entries, self._manifest_for(info, OP_MIGRATION), ctx)\n        self._publish",
     "migrate fresh: allow history.json in the key directory"),
    ("V03", S, "        self._check_durability()\n        expected = manifest_bytes(unlock_manifest(body, plan_hash))\n        kpath, existed = self._q_make(plan_hash, ctx)",
     "        expected = manifest_bytes(unlock_manifest(body, plan_hash))\n        kpath, existed = self._q_make(plan_hash, ctx)\n        self._check_durability()",
     "unlock: durability checked after the quarantine is made"),
    ("V04", S, "        self._q_check_names(entries, {HISTORY_NAME})\n        self._q_manifest(kpath, entries, self._manifest_for(info, OP_ADOPTION), ctx)",
     "        self._q_manifest(kpath, entries, self._manifest_for(info, OP_ADOPTION), ctx)",
     "adopt: names of the key directory not checked"),
    ("V05", V, "        if ok and manifest_bytes(obj) != data:\n            ok = False", "",
     "read_manifest: canonical form not required"),
    ("V06", S, "        shaped = is_hex64(key)", "        shaped = True", "publication hash not checked before the lock"),
    ("V07", S, "        if own is None and any(t[\"kind\"] == KIND_LOCK for t in absent) and any(t[\"kind\"] == KIND_TMP for t in present):\n            raise stale()\n", "",
     "unlock: a moved lock with temporary files still in the root is accepted"),
    ("V08", S, "            return data == lock.marker and (st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)",
     "            return (st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)", "_owns: marker not compared"),
    ("V09", S, "    def _release(self, lock):\n        if not self._owns(lock):\n            return \"lost\"",
     "    def _release(self, lock):\n        if False:\n            return \"lost\"", "_release: ownership not checked"),
    ("V10", V, "    tmps = sorted((a for a in arts if a[\"kind\"] == KIND_TMP), key=lambda a: a[\"name\"])",
     "    tmps = sorted((a for a in arts if a[\"kind\"] == KIND_TMP), key=lambda a: a[\"name\"], reverse=True)",
     "plan_unlock: temporary files in reverse order"),
    ("V11", V, "and tmps == sorted(tmps) and len(locks) <= 1", "and len(locks) <= 1", "check_plan: order of tmps not required"),
    ("V12", S, "                ok = stat.S_ISDIR(st.st_mode) and not ops.is_link_like(st)",
     "                ok = stat.S_ISDIR(st.st_mode)", "root: a link-like root accepted"),
    ("V14", S, "        if strict:\n            try:\n                ops.fsync_dir(self._dir)", "        if False:\n            try:\n                ops.fsync_dir(self._dir)",
     "publish: no directory fsync under STRICT"),
    ("V15", S, "        if outcome not in (PUBLISHED, PUBLISHED_THEN_EXTENDED):\n            return None\n        info = self._info(pub)\n        refused",
     "        info = self._info(pub)\n        refused", "adopt completed: outcome not required"),
    ("V16", S, "    if (ctx.changed and isinstance(exc, LocalStoreError) and exc.code == \"store_io_error\"\n            and exc.field == _QUARANTINE_FIELD):",
     "    if (ctx.changed and isinstance(exc, LocalStoreError) and exc.code == \"store_io_error\"):",
     "_incomplete: every store_io_error after a change (publish errors too)"),
    ("V17", S, "        if manifest is None or manifest[\"key\"] != key:", "        if manifest is None:",
     "read_set_aside: the key inside the MANIFEST not compared"),
    ("V18", S, "        if ctx.changed:\n            raise maintenance_error(\"maintenance_incomplete\", \"lock\", phase,",
     "        if False:\n            raise maintenance_error(\"maintenance_incomplete\", \"lock\", phase,",
     "_locked: a failed release after a change is store_io_error"),
    ("V19", V, "    for magic, owner in ((S2_LOCK_MAGIC, OWNER_S2), (C3_LOCK_MAGIC, OWNER_C3), (LOCK_MAGIC, OWNER_C4)):",
     "    for magic, owner in ((S2_LOCK_MAGIC, OWNER_C3), (C3_LOCK_MAGIC, OWNER_S2), (LOCK_MAGIC, OWNER_C4)):",
     "inspect: lock owners S2/C3 swapped"),
    ("V20", S, "        if (not stat.S_ISDIR(st.st_mode) or self._ops.is_link_like(st) or st.st_dev != self._dev):",
     "        if (not stat.S_ISDIR(st.st_mode) or st.st_dev != self._dev):", "quarantine: a link-like directory accepted"),
    ("V21", S, "        if MANIFEST_NAME not in entries:\n            raise unexpected\n", "",
     "migrate resume: a key directory without MANIFEST accepted (and written)"),
    ("V22", S, "        if self._lstat(dst, _QUARANTINE_FIELD, \"move\") is not None:\n            raise maintenance_error(\"maintenance_quarantine_invalid\", _QUARANTINE_FIELD, \"move\", rule=\"target\")\n", "",
     "_move: the destination is not checked to be empty (rename may overwrite)"),
    ("V23", S, "            readable = True\n            try:\n                read_history_bytes(data)\n            except Exception:\n                readable = False",
     "            readable = True", "inspect: readable always True"),
    ("V24", S, "        if V1_NAME in names:\n            raise LocalStoreError(\"store_layout_unsupported\"",
     "        if False:\n            raise LocalStoreError(\"store_layout_unsupported\"", "adopt: snapshot.json not refused"),
    ("V25", S, "        if any(is_root_tmp(n) for n in names):\n            raise LocalStoreError(\"store_artifact_present\", \"store\", \"scan\")\n        has_h",
     "        has_h", "migrate: left temporary files not refused"),
    ("V26", S, "        if not self._matches(os.path.join(kpath, HISTORY_NAME), info[\"identity\"]):    # the copy, read back\n            raise maintenance_error(\"maintenance_copy_mismatch\", _QUARANTINE_FIELD, \"copy\")\n        self._publish",
     "        self._publish", "adopt: no read-back at all (a resumed copy also unchecked)"),
    ("V27", S, "            if (n == LOCK_NAME and own is None) or is_root_tmp(n):",
     "            if is_root_tmp(n):", "unlock: a new lock after the plan (plan with a lock) not stale"),
    ("V28", S, "        if LOCK_NAME in self._names():                    # a lock appeared after the plan: it is old\n            raise maintenance_error(\"maintenance_plan_stale\", \"store\", \"scan\")\n", "",
     "unlock: precheck of a lock that appeared removed (store_busy instead)"),
    ("V29", S, "        self._sync(kpath, \"dir_sync\")\n        self._sync(self._dir, \"dir_sync\")\n        return MaintenanceResult(UNLOCKED",
     "        return MaintenanceResult(UNLOCKED", "unlock: no final directory fsync"),
    ("V30", S, "            if ops.is_windows():\n                raise", "            if False:\n                raise", "Windows strict not refused (E8 again, as a control)"),
]


def run(mid, path, old, new, what):
    d = os.path.join(WORK, mid)
    shutil.rmtree(d, True)
    shutil.copytree(REPO, d, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    p = os.path.join(d, path)
    src = open(p).read()
    if src.count(old) != 1 or old == new:
        return mid, "PREP_FAIL(count=%d)" % src.count(old), what, ""
    open(p, "w").write(src.replace(old, new))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    t = time.time()
    r = subprocess.run([PY, "-B", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-f", "-s",
                        "tests/v2_history_maintain", "-p", "test_c4_0[1-8]_*.py"], cwd=d, env=env,
                       capture_output=True, text=True)
    first = ""
    for line in r.stderr.splitlines():
        if line.startswith(("FAIL:", "ERROR:")):
            first = line
            break
    shutil.rmtree(d, True)
    return mid, ("DETECTED" if r.returncode else "NOT_DETECTED") + " %.0fs" % (time.time() - t), what, first


for mid, path, old, new, what in MUTANTS:
    if ONLY and mid not in ONLY:
        continue
    res = run(mid, path, old, new, what)
    print("%s | %s | %s | %s" % res, flush=True)
