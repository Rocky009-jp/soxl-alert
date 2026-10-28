"""Defect injection for the S2 tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
v2_persistence/local, run the new test suite there and require it to fail. Not part of the product, not a unittest
(run it by hand: <python> -B tests/v2_persistence_local/sensitivity_check.py). The real tree is never modified.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# (id, file, old, new, what is broken)
MUTATIONS = [
    ("M01", "store.py", "            ops.fsync_file(writer)\n", "            pass\n", "no file fsync"),
    ("M02", "store.py", "                ops.fsync_dir(self._dir)\n", "                pass\n", "no directory fsync (strict)"),
    ("M03", "store.py", "            ops.flush(writer)\n", "            pass\n", "no flush"),
    ("M04", "fsops.py", "os.O_WRONLY | os.O_CREAT | os.O_EXCL |", "os.O_WRONLY | os.O_CREAT |", "lock without O_EXCL"),
    ("M05", "store.py", """        except FileExistsError:
            err = LocalStoreError("store_busy", "lock", "lock_acquire")""", """        except FileExistsError:
            ops.unlink(path)
            fd = ops.create_exclusive(path)""", "stale lock taken over automatically"),
    ("M06", "store.py", "if plan.expected_head_seq != current.head_seq or plan.expected_head_hash != current.head_hash:",
     "if False:", "no head comparison (CAS)"),
    ("M07", "store.py", "            validate_snapshot(candidate)\n            self._publish(lock, ctx, candidate)",
     "            self._publish(lock, ctx, candidate)", "candidate not checked"),
    ("M08", "store.py", "        if not self._owns(lock):\n            tokens = self._discard_own",
     "        if False:\n            tokens = self._discard_own", "no ownership check before replace"),
    ("M09", "store.py", """        if not self._owns(lock):
            return "lost"
        try:
            self._ops.unlink(lock.path)""", """        try:
            self._ops.unlink(lock.path)""", "lock released without ownership check"),
    ("M10", "store.py", """            raise LocalStoreError("store_commit_uncertain", "snapshot", "replace", cleanup=tokens)""",
     """            raise LocalStoreError("store_io_error", "snapshot", "replace", cleanup=tokens)""",
     "replace failure not reported as uncertain"),
    ("M11", "store.py", "            self._scan()\n            return self._load()", "            return self._load()",
     "read ignores leftover tmp files"),
    ("M13", "store.py", "if code is None and (ops.is_link_like(st) or not stat.S_ISREG(st.st_mode)):",
     "if False:", "snapshot.json link / special file accepted"),
    ("M14", "store.py", """        def body(lock, ctx):
            self._scan()
            return self._load()
        return self._locked(body)""", """        return self._load()""", "read without lock"),
    ("M15", "store.py", """            if ops.is_windows():
                raise LocalStoreError("store_durability_unsupported", "durability", "durability_probe",
                                      rule="windows_strict")""", """            if False:
                pass""", "Windows strict silently allowed"),
    ("M16", "store.py", """        if failed:
            created = st is not None""", """        if failed:
            raise LocalStoreError("store_io_error", "snapshot", phase)
            created = st is not None""", "own tmp not removed after failure"),
    ("M17", "store.py", "return FILE_AND_DIRECTORY_SYNC if self._durability == STRICT else FILE_SYNC_ONLY",
     "return FILE_AND_DIRECTORY_SYNC", "persistence level always strict"),
    ("M18", "store.py", "            done += n\n", "            done = len(view)\n", "short writes not completed"),
    ("M19", "store.py", """            if self._load(missing_ok=True) is not None:
                raise LocalStoreError("already_initialized", "store", "read")""", """            pass""",
     "initialize overwrites an existing file"),
    ("M20", "store.py", """            try:
                ops.fsync_dir(self._dir)
            except Exception:
                failed = True""", """            try:
                ops.fsync_dir(self._dir)
            except Exception:
                failed = False""", "directory fsync failure ignored"),
    ("M21", "store.py", """        if ctx.published:
            if isinstance(exc, LocalStoreError)""", """        if False:
            if isinstance(exc, LocalStoreError)""", "lock-release failure after replace not uncertain"),
    ("M22", "store.py", "            raise LocalStoreError(\"store_io_error\", \"root\", \"scan\")\n", "            names = []\n",
     "listing failure ignored"),
    ("M24", "store.py", "            raise LocalStoreError(\"store_io_error\", \"lock\", \"lock_acquire\", cleanup=tokens)",
     "            raise LocalStoreError(\"store_io_error\", \"lock\", \"lock_acquire\")", "lock clean-up result hidden"),
    ("M26", "store.py", "        data = encode_snapshot(snapshot).encode(\"utf-8\")",
     "        data = encode_snapshot(snapshot).encode(\"utf-8\")[:-1]", "last byte of the file is lost"),
    ("M27", "store.py", "            raise exc.add_cleanup(token)\n            raise LocalStoreError(\"store_commit_uncertain\"",
     "            raise exc\n            raise LocalStoreError(\"store_commit_uncertain\"", "release leftover not recorded"),
    ("M28", "store.py", "if len(genesis.events) != 1:", "if False:", "initialize accepts a snapshot with APPLY"),
    ("M29", "store.py", "        except UnicodeDecodeError:\n            text = None", "        except UnicodeDecodeError:\n            text = data.decode('utf-8', 'replace')",
     "invalid UTF-8 repaired silently"),
    ("M30", "store.py", ("(st.st_dev, st.st_ino) != (lock.dev, lock.ino)", "(st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)"),
     ("False", "True"), "lock inode not compared"),
    ("M31", "store.py", "cleanup = earlier + tuple(t for t in (token,) if t not in earlier)", "cleanup = (token,)",
     "R-01: earlier clean-up items dropped when the error is replaced"),
    ("M32", "store.py", "            if self._lock_path_exists(path):", "            if False:",
     "R-02: existing lock reported as I/O error when creation raises a non-FileExists error"),
]


def main():
    only = set(sys.argv[1:])
    lost = []
    for mid, fname, old, new, what in MUTATIONS:
        if (only and mid not in only):
            continue
        tmp = tempfile.mkdtemp(prefix="v2s2_mut_")
        try:
            for d in ("v2_core", "v2_persistence", "tests/v2_persistence_local", "tests/v2_persistence", "research"):
                src = os.path.join(ROOT, d)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = os.path.join(tmp, "v2_persistence", "local", fname)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            olds, news = (old, new) if isinstance(old, tuple) else ((old,), (new,))
            if any(text.count(o) != 1 for o in olds):
                print(mid, "SETUP-ERROR: pattern count", [text.count(o) for o in olds])
                lost.append(mid)
                continue
            for o, n in zip(olds, news):
                text = text.replace(o, n)
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_persistence_local",
                                "-p", "test_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            detected = r.returncode != 0
            print(mid, "DETECTED" if detected else "NOT DETECTED", "-", what)
            if not detected:
                lost.append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
