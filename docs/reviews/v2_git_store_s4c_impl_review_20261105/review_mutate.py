"""Independent defect injection for the S4-C implementation review (not the implementer's list). usage:
    python3 review_mutate.py <clone at 13be0d0> <out.json> [ids...]
Each mutant is applied alone to a throw-away worktree (git worktree add --detach 13be0d0); the S4-C suite runs without the
scope test 09 (it lists changed files) and, unless the mutant is about races, without the process races 06. A mutant is
DETECTED when a test fails or errors, NOT_DETECTED otherwise; SETUP_FAILED when the text to replace is not found once."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

BASE = "13be0d0903df82d8c2cdd8196071ba957b2eb711"
G, H, O = "v2_git_store/git.py", "v2_git_store/history.py", "v2_git_store/outbox.py"
FILES = ["test_s4c_01_args.py", "test_s4c_02_git.py", "test_s4c_03_history.py", "test_s4c_04_unreachable.py",
         "test_s4c_05_outbox.py", "test_s4c_07_commits.py", "test_s4c_08_static.py", "test_s4c_10_secrets.py"]
RACE = ["test_s4c_06_processes.py"]

M = [
    ("V01", "push verdict takes the first of several lines for the ref", G,
     "    if len(flags) != 1:\n        return UNCERTAIN", "    if not flags:\n        return UNCERTAIN", False),
    ("V02", "history publish: a failed fetch after a refusal is read as a moved head (publication_stale)", H,
     "            moved = self._head() != head            # a failed fetch here is store_io_error",
     "            try:\n                moved = self._head() != head\n            except LocalStoreError:\n"
     "                moved = True", False),
    ("V03", "history initialize: every refusal is already_initialized (no fetch again)", H,
     "            if self._head() is not None:\n                raise LocalStoreError(\"already_initialized\"",
     "            if True:\n                raise LocalStoreError(\"already_initialized\"", False),
    ("V04", "outbox create: an uncertain push that did not arrive (head not moved) ends at once", O,
     "            if how == REJECTED and now_head == head:", "            if now_head == head:", True),
    ("V05", "outbox create: every refusal without the name ends at once (moved head too)", O,
     "            if how == REJECTED and now_head == head:", "            if how == REJECTED:", True),
    ("V06", "outbox create: five tries", O, "TRIES = 4", "TRIES = 5", True),
    ("V07", "outbox create: three tries", O, "TRIES = 4", "TRIES = 3", True),
    ("V08", "commit time: a negative offset is written with +", G,
     '"-" if seconds < 0 else "+"', '"+"', False),
    ("V09", "fetch without + (not forced into refs/v2remote)", G,
     '"+refs/heads/%s:refs/v2remote/%s"', '"refs/heads/%s:refs/v2remote/%s"', False),
    ("V10", "history reconcile: a missing ref is store_uninitialized instead of the C-2 reconciliation of nothing", H,
     "        return reconcile_publication(self._bytes(self._head()), pub)",
     "        head = self._head()\n        if head is None:\n"
     "            raise LocalStoreError(\"store_uninitialized\", \"store\", \"read\")\n"
     "        return reconcile_publication(self._bytes(head), pub)", False),
    ("V11", "outbox initialize: an uncertain push is done when the ref exists, whatever its marker", O,
     "and self._marker_is_there(now_head):", "and True:", False),
    ("V12", "mirror: a name that is not a plain name is not refused", O,
     'if kind != "blob" or mode not in REGULAR_MODES or not valid_name(name):',
     'if kind != "blob" or mode not in REGULAR_MODES:', False),
    ("V13", "outbox claim: the key is not checked before git is started", O,
     "        _check_key(notice.d, notice.kind, resend_request_id)\n        return self._decide(",
     "        return self._decide(", False),
    ("V14", "outbox mirror: the base mode is strict", O, 'super().__init__(mirror, "file_sync_only", _ops=_ops)',
     'super().__init__(mirror, "strict", _ops=_ops)', False),
    ("V15", "outbox parent: a link is taken", O, "    if link or not stat.S_ISDIR(st.st_mode):",
     "    if not stat.S_ISDIR(st.st_mode):", False),
    ("V16", "outbox create: a name on the remote after a failed push is ours whatever its bytes", O,
     "                return value if _slurp(path) == data else absent", "                return value", True),
    ("V17", "history commit message: 13 characters of the hash", H, 'publication_hash[:12]', 'publication_hash[:13]', False),
    ("V18", "commit: only the committer date is set (the author date is git's)", G,
     'env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}', 'env={"GIT_COMMITTER_DATE": stamp}', False),
    ("V19", "environment: GIT_CONFIG_NOSYSTEM is not set", G, '"GIT_CONFIG_NOSYSTEM": "1", ', '', False),
    ("V20", "push verdict: = (already there) is not OK", G, 'if flags[0] in ("*", " ", "="):', 'if flags[0] in ("*", " "):',
     False),
    ("V21", "outbox create: four lost tries are 'taken by another' (SKIPPED_CLAIMED) instead of an error", O,
     "                raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")\n        raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")",
     "                raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")\n        return absent", True),
    ("V22", "history publish: the mode is not checked (a CREATE publication is appended)", H,
     "        if mode != APPEND:\n            raise LocalStoreError(\"store_operation_unsupported\", \"publication\", \"args\", "
     "rule=\"not_append\")", "        if False:\n            raise LocalStoreError(\"store_operation_unsupported\", "
     "\"publication\", \"args\", rule=\"not_append\")", False),
    ("V23", "load: an outbox whose ref is missing reads as the base's (empty) outbox", O,
     "        if failed or head is None:\n            raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")",
     "        if failed:\n            raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")", False),
    ("V24", "outbox create: the result of a push is not looked at when the commit was made (OK assumed)", O,
     "            if how == OK:\n                return value\n            now_head",
     "            if how in (OK, REJECTED):\n                return value\n            now_head", True),
]


def run_one(clone, m):
    mid, desc, path, old, new, race = m
    tmp = tempfile.mkdtemp(prefix="rvmut_%s_" % mid)
    wt = os.path.join(tmp, "wt")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        subprocess.run(["git", "-C", clone, "worktree", "add", "-q", "--detach", wt, BASE], check=True,
                       capture_output=True)
        f = os.path.join(wt, path)
        text = open(f, encoding="utf-8").read()
        if text.count(old) != 1:
            return dict(id=mid, desc=desc, result="SETUP_FAILED", count=text.count(old))
        open(f, "w", encoding="utf-8", newline="").write(text.replace(old, new))
        failed, first = 0, None
        for name in FILES + (RACE if race else []):
            p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_git_store", "-p", name],
                               cwd=wt, env=env, capture_output=True, text=True, timeout=1800)
            last = [l for l in p.stderr.splitlines() if l.startswith("FAILED") or l == "OK"]
            if p.returncode != 0:
                import re
                n = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", last[-1] if last else "")) or 1
                failed += n
                if first is None:
                    hit = [l for l in p.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
                    first = hit[0] if hit else name
        return dict(id=mid, desc=desc, result="DETECTED" if failed else "NOT_DETECTED", failed=failed, first=first,
                    race_included=race)
    finally:
        subprocess.run(["git", "-C", clone, "worktree", "remove", "--force", wt], capture_output=True)
        shutil.rmtree(tmp, True)


def main():
    clone, out = sys.argv[1], sys.argv[2]
    want = set(sys.argv[3:])
    ms = [m for m in M if not want or m[0] in want]
    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda m: run_one(clone, m), ms))
    json.dump(results, open(out, "w"), indent=1, ensure_ascii=False)
    for r in results:
        print("%-4s %-13s %3s  %s | %s" % (r["id"], r["result"], r.get("failed", ""), r["desc"], r.get("first") or ""))


main()
