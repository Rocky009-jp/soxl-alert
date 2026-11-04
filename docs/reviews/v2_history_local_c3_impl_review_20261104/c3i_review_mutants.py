"""C-3 implementation review: independent mutants (different from the implementer's 18 + E1..E8). One at a time on the
working tree of a throwaway worktree of e3d880a (runtime file only; the range tests read committed Git and are not
affected), then the new suite test_c3_* is run and the file restored.
usage: python c3i_review_mutants.py <python> <worktree>"""
import os, subprocess, sys
PY, WT = sys.argv[1], os.path.abspath(sys.argv[2])
STORE = os.path.join(WT, "v2_history_local", "store.py")
M = [
 ("V01", "_locked: the primary code is not kept when the release fails",
  'raise LocalStoreError(code, "lock", phase, cleanup=cleanup, primary=getattr(exc, "code", None))',
  'raise LocalStoreError(code, "lock", phase, cleanup=cleanup)'),
 ("V02", "_locked: an uncertain commit does not get the lock token added",
  "                raise exc.add_cleanup(token)\n            raise LocalStoreError(\"store_commit_uncertain\"",
  "                raise exc\n            raise LocalStoreError(\"store_commit_uncertain\""),
 ("V03", "_publish: a failed replace does not remove its temporary file",
  '            tokens = self._discard_own(tmp, st, None, None, CLEANUP_TMP_LEFT)\n            raise LocalStoreError("store_commit_uncertain", "history", "replace", cleanup=tokens)',
  '            tokens = ()\n            raise LocalStoreError("store_commit_uncertain", "history", "replace", cleanup=tokens)'),
 ("V04", "_publish: a failure while writing the temporary file never cleans up",
  "            created = st is not None or fd is not None or writer is not None or phase != \"tmp_create\"",
  "            created = False"),
 ("V05", "_acquire: an existing path behind a non-FileExistsError is store_io_error (no busy fallback)",
  "            if self._exists(path):\n                err = LocalStoreError(\"store_busy\", \"lock\", \"lock_acquire\")",
  "            if False:\n                err = LocalStoreError(\"store_busy\", \"lock\", \"lock_acquire\")"),
 ("V06", "_acquire: a failed marker write leaves the lock (no discard)",
  "            tokens = self._discard_own(path, st, writer, fd, CLEANUP_LOCK_LEFT)",
  "            tokens = (CLEANUP_LOCK_LEFT,)"),
 ("V07", "_load: an I/O error on the read is reported as store_root_invalid",
  '        if code == "io":\n            raise LocalStoreError("store_io_error", "history", "read")',
  '        if code == "io":\n            raise LocalStoreError("store_root_invalid", "root", "read")'),
 ("V08", "_load: a non-regular history.json counts as absent",
  '        if code is None and (ops.is_link_like(st) or not stat.S_ISREG(st.st_mode)):\n            code = "root"',
  '        if code is None and (ops.is_link_like(st) or not stat.S_ISREG(st.st_mode)):\n            code = "missing"\n            if missing_ok:\n                return None'),
 ("V09", "operations do not re-check the root (only the constructor does)",
  "    def read(self):\n        \"\"\"The validated History, read under the lock every time.\"\"\"\n        self._dir = self._check_root()",
  "    def read(self):\n        \"\"\"The validated History, read under the lock every time.\"\"\""),
 ("V10", "_checked: publication_stale is wrapped as store_candidate_invalid",
  '_PUBLICATION_CODES = ("publication_invalid", "publication_stale")', '_PUBLICATION_CODES = ("publication_invalid",)'),
 ("V11", "_checked: publication_invalid is wrapped as store_candidate_invalid",
  '_PUBLICATION_CODES = ("publication_invalid", "publication_stale")', '_PUBLICATION_CODES = ("publication_stale",)'),
 ("V12", "publish: one extra byte (newline) after the canonical bytes",
  "            self._publish(lock, ctx, history_bytes(candidate))\n            return HistoryStoreResult(PUBLISHED",
  "            self._publish(lock, ctx, history_bytes(candidate) + b\"\\n\")\n            return HistoryStoreResult(PUBLISHED"),
 ("V13", "result: publication_hash is not the publication's",
  "return HistoryStoreResult(PUBLISHED, True, candidate, self.persistence_level, pub.publication_hash)",
  "return HistoryStoreResult(PUBLISHED, True, candidate, self.persistence_level, \"0\" * 64)"),
 ("V14", "persistence_level reversed",
  "return FILE_AND_DIRECTORY_SYNC if self._durability == STRICT else FILE_SYNC_ONLY",
  "return FILE_SYNC_ONLY if self._durability == STRICT else FILE_AND_DIRECTORY_SYNC"),
 ("V15", "reconcile requires a writable store",
  "        pub = _publication(publication)\n        self._dir = self._check_root()\n\n        def body(lock, ctx):\n            self._scan(tolerate_tmp=True)",
  "        pub = _publication(publication)\n        self._require_writable()\n        self._dir = self._check_root()\n\n        def body(lock, ctx):\n            self._scan(tolerate_tmp=True)"),
 ("V16", "read: no scan (leftovers and v1 do not stop a read)",
  "        def body(lock, ctx):\n            self._scan()\n            history, _check = read_history_bytes(self._load())",
  "        def body(lock, ctx):\n            history, _check = read_history_bytes(self._load())"),
 ("V17", "scan: v1_only and v1_and_v2 swapped",
  'rule="v1_and_v2" if HISTORY_NAME in names else "v1_only"', 'rule="v1_only" if HISTORY_NAME in names else "v1_and_v2"'),
 ("V18", "_release: reports success without removing the lock",
  "        try:\n            self._ops.unlink(lock.path)\n        except Exception:\n            return \"failed\"",
  "        try:\n            pass\n        except Exception:\n            return \"failed\""),
 ("V19", "_owns: the inode is not compared (marker only)",
  "            if ops.is_link_like(st) or not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (lock.dev, lock.ino):",
  "            if ops.is_link_like(st) or not stat.S_ISREG(st.st_mode):"),
 ("V20", "_owns: the marker is not compared (inode only)",
  "            return data == lock.marker and (st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)",
  "            return (st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)"),
 ("V21", "_write_all: one write only (a short write is not retried)",
  "        while done < len(view):\n            n = ops.write(writer, view[done:])",
  "        for _ in range(1):\n            n = ops.write(writer, view[done:])"),
 ("V22", "_publish: the file fsync is omitted",
  '            phase = "file_sync"\n            ops.fsync_file(writer)', '            phase = "file_sync"'),
 ("V23", "_publish: a failed directory fsync after the replace is swallowed",
  '            if failed:\n                raise LocalStoreError("store_commit_uncertain", "history", "dir_sync")',
  '            if failed:\n                pass'),
 ("V24", "_publish: a failed replace reports phase dir_sync",
  'raise LocalStoreError("store_commit_uncertain", "history", "replace", cleanup=tokens)',
  'raise LocalStoreError("store_commit_uncertain", "history", "dir_sync", cleanup=tokens)'),
 ("V25", "_locked: an uncertain commit whose lock was lost loses the earlier cleanup tokens",
  '            raise LocalStoreError("store_commit_uncertain", "history", phase, cleanup=cleanup,',
  '            raise LocalStoreError("store_commit_uncertain", "history", phase, cleanup=(token,),'),
 ("V26", "_locked: lost ownership before the publish keeps the error but drops the lock token",
  '        if isinstance(exc, LocalStoreError) and exc.code == "store_lock_ownership_lost" and rel == "lost":\n            raise exc.add_cleanup(token)',
  '        if isinstance(exc, LocalStoreError) and exc.code == "store_lock_ownership_lost" and rel == "lost":\n            raise exc'),
 ("V27", "lock marker without the trailing newline after the fixed word",
  'LOCK_MAGIC = b"v2_history_local.lock\\n"', 'LOCK_MAGIC = b"v2_history_local.lock"'),
 ("V28", "lock marker without the random part",
  'marker = LOCK_MAGIC + secrets.token_hex(16).encode("ascii") + b"\\n"', 'marker = LOCK_MAGIC + b"0" * 32 + b"\\n"'),
 ("V29", "temporary file name without the random part",
  "tmp = self._managed(TMP_PREFIX + secrets.token_hex(16) + TMP_SUFFIX)", 'tmp = self._managed(TMP_PREFIX + "0" * 32 + TMP_SUFFIX)'),
 ("V30", "scan: a temporary name is judged by its prefix only (suffix not checked)",
  "                if name.endswith(TMP_SUFFIX) and (name.startswith(TMP_PREFIX) or name.startswith(S2_TMP_PREFIX)):",
  "                if (name.startswith(TMP_PREFIX) or name.startswith(S2_TMP_PREFIX)):"),
 ("V31", "reconcile: a v1 file does not stop it",
  "        if V1_NAME in names:\n", "        if V1_NAME in names and not tolerate_tmp:\n"),
 ("V32", "_kind: a publish also requires the source (with_source True)",
  "        mode, _source = _kind(pub, False)", "        mode, _source = _kind(pub, True)"),
 ("V33", "initialize: the read-only check is skipped",
  "            raise LocalStoreError(\"store_operation_unsupported\", \"publication\", \"args\", rule=\"not_genesis\")\n        self._require_writable()",
  "            raise LocalStoreError(\"store_operation_unsupported\", \"publication\", \"args\", rule=\"not_genesis\")"),
 ("V34", "publish: writability is checked before the kind (order of the design changed)",
  "        pub = _publication(publication)\n        mode, _source = _kind(pub, False)",
  "        self._require_writable()\n        pub = _publication(publication)\n        mode, _source = _kind(pub, False)"),
 ("V35", "_discard_own: the file is removed even when its inode differs (no tmp_ownership_unconfirmed)",
  "            return (CLEANUP_TMP_UNCONFIRMED,) if left_token == CLEANUP_TMP_LEFT else (left_token,)",
  "            pass"),
 ("V36", "_check_root: realpath not taken (the joined path is used)",
  "                    real = os.path.realpath(path)", "                    real = path"),
]
src = open(STORE).read()
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
res = []
for mid, title, old, new in M:
    if src.count(old) != 1:
        res.append((mid, "PREP_FAILED(%d)" % src.count(old), title)); continue
    open(STORE, "w").write(src.replace(old, new))
    try:
        p = subprocess.run([PY, "-B", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s",
                            "tests/v2_history_local", "-p", "test_c3_*.py"], cwd=WT, env=env, capture_output=True,
                           text=True, timeout=900)
        tail = [l for l in p.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
        fails = sorted({l.split("(")[1].split(")")[0].split(".")[0] for l in p.stderr.splitlines()
                        if l.startswith(("FAIL:", "ERROR:")) and "(" in l})
        res.append((mid, "DETECTED" if p.returncode else "UNDETECTED", title, " ".join(tail), ",".join(fails)))
    finally:
        open(STORE, "w").write(src)
for r in res:
    print(" | ".join(r))
print("detected", sum(r[1] == "DETECTED" for r in res), "undetected", sum(r[1] == "UNDETECTED" for r in res),
      "prep_failed", sum(r[1].startswith("PREP") for r in res))
