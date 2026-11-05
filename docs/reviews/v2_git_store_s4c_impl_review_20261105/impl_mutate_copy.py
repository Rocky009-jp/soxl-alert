"""S4-C limited defect injection (request section 5, items 1-20, plus extras). One mutant at a time on a throwaway
worktree of the tested commit (the range tests read Git at HEAD, so each mutant is committed there). Nothing is pushed.
usage: python mutate.py <python> <repo> <tested-sha> <out.json> [i/n]
Classification: DETECTED (a test of the S4-C suite fails (the range test 09 is not counted: it reads the changed file list) or errors), UNDETECTED, PREP_FAILED (the pattern was not found
exactly once, or the mutant does not parse; nothing was run). EQUIVALENT is a judgement written in the result document,
never decided here."""
import json
import os
import re
import subprocess
import sys
import tempfile

PY, REPO, SHA, OUT = sys.argv[1:5]
SHARD = tuple(int(x) for x in sys.argv[5].split("/")) if len(sys.argv) > 5 else (0, 1)
GIT, HIST, OUTBOX = "v2_git_store/git.py", "v2_git_store/history.py", "v2_git_store/outbox.py"
M = []


def add(n, title, *edits):
    M.append({"id": n, "title": title, "edits": list(edits)})


def sub(path, old, new):
    return (path, old, new)



add("1", "push is forced (--force)",
    sub(GIT, '["push", "--porcelain", self.remote,', '["push", "--porcelain", "--force", self.remote,'))
add("1b", "push is forced (+ in the refspec)",
    sub(GIT, '"%s:refs/heads/%s" % (commit, ref)])', '"+%s:refs/heads/%s" % (commit, ref)])'))
add("2", "push is quiet (--quiet)",
    sub(GIT, '["push", "--porcelain", self.remote,', '["push", "--porcelain", "--quiet", self.remote,'))
add("3", "UNCERTAIN is treated as OK in publish",
    sub(HIST, "        if how == OK:\n            return HistoryStoreResult(PUBLISHED", "        if how != REJECTED:\n            return HistoryStoreResult(PUBLISHED"))
add("4", "REJECTED is store_commit_uncertain in publish",
    sub(HIST, "        if how == REJECTED:\n            moved", '        if how == REJECTED:\n            raise LocalStoreError("store_commit_uncertain", "history", "replace")\n            moved'))
add("5", "a failed fetch is 'no ref'",
    sub(GIT, '        raise GitError(FAILED, "fetch")', '        return None'))
add("6", "a refusal after a moved head has a new code",
    sub(HIST, 'raise LocalStoreError("publication_stale", "history", "cas")', 'raise LocalStoreError("store_ref_moved", "history", "cas")'))
add("7", "reconcile uses the bytes read before (no fetch)",
    sub(HIST, "        current = self._bytes(head)\n", "        current = self._last = self._bytes(head)\n"),
    sub(HIST, "return reconcile_publication(self._bytes(self._head()), pub)", 'return reconcile_publication(getattr(self, "_last", None), pub)'))
add("8", "publish makes the commit without check_publication",
    sub(HIST, "        candidate = _checked(current, pub)\n        how = self._push(head,", "        candidate = read_history_bytes(current)[0]\n        how = self._push(head,"))
add("9", "the tree of a new commit drops the other files of the parent",
    sub(GIT, "entries = {} if parent is None else self.tree(parent)", "entries = {}"))
add("10", "fetch goes to refs/heads/<ref>",
    sub(GIT, '"+refs/heads/%s:refs/v2remote/%s" % (ref, ref)', '"+refs/heads/%s:refs/heads/%s" % (ref, ref)'),
    sub(GIT, '"refs/v2remote/%s" % ref]', '"refs/heads/%s" % ref]'))
add("11", "GitOutbox.load raises on a failure of the remote",
    sub(OUTBOX, "            return OutboxEntry(kind, d, resend_request_id, DAMAGED), None\n        return super().load",
        '            raise NotifyError(OUTBOX_IO_ERROR, "outbox")\n        return super().load'))
add("12", "a refused create is 'taken by another' without reading the remote again",
    sub(OUTBOX, "            now_head = self._rebuild()              # refused or uncertain",
        "            if how == REJECTED:\n                return absent\n            now_head = self._rebuild()              # refused or uncertain"))
add("13", "an uncertain create is 'ours' without comparing the bytes on the remote",
    sub(OUTBOX, "            now_head = self._rebuild()              # refused or uncertain",
        "            if how != REJECTED:\n                return value\n            now_head = self._rebuild()              # refused or uncertain"))
add("14", "a create is tried once only",
    sub(OUTBOX, "TRIES = 4", "TRIES = 1"))
add("15", "the mirror keeps the files of the earlier mirror",
    sub(OUTBOX, "                for name in os.listdir(self._mirror):\n                    os.unlink(os.path.join(self._mirror, name))\n", ""),
    sub(OUTBOX, 'open(os.path.join(self._mirror, name), "xb")', 'open(os.path.join(self._mirror, name), "wb")'))
add("16", "a missing ref is an empty outbox",
    sub(OUTBOX, "        if failed or head is None:\n            raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")\n        return head",
        "        if failed:\n            raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")\n        return head"))
add("17", "the error of git carries the standard error",
    sub(GIT, '            raise GitError(FAILED, "command")', '            raise GitError(FAILED, "command", None if proc is None else proc.stderr.decode("utf-8", "replace"))'))
add("18", "the GIT_ variables of the parent are kept",
    sub(GIT, 'env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}', "env = dict(os.environ)"))
add("19", "the add commit of the outbox replaces a name of the parent's tree",
    sub(OUTBOX, '"v2 outbox " + name, when, replace=False)', '"v2 outbox " + name, when, replace=True)'))
add("20", "a refusal by a rule (head not moved) is publication_stale",
    sub(HIST, '            raise LocalStoreError("store_io_error", "history", "replace")\n        raise LocalStoreError("store_commit_uncertain", "history", "replace")\n\n    def reconcile',
        '            raise LocalStoreError("publication_stale", "history", "cas")\n        raise LocalStoreError("store_commit_uncertain", "history", "replace")\n\n    def reconcile'))
add("20b", "any refusal is store_io_error (a lost race too)",
    sub(HIST, "moved = self._head() != head ", "moved = False "))
add("E1", "extra: the flag ! is UNCERTAIN",
    sub(GIT, '    if flags[0] == "!":\n        return REJECTED', '    if flags[0] == "!":\n        return UNCERTAIN'))
add("E2", "extra: the exit code of push is not looked at",
    sub(GIT, "return OK if proc.returncode == 0 else UNCERTAIN", "return OK"))
add("E3", "extra: a timed-out push is REJECTED",
    sub(GIT, "    if proc is None:\n        return UNCERTAIN", "    if proc is None:\n        return REJECTED"))
add("E4", "extra: initialize does not look for an existing ref (history)",
    sub(HIST, '        if self._head() is not None:\n            raise LocalStoreError("already_initialized", "store", "read")\n        candidate', "        candidate"))
add("E5", "extra: a refused create of the history on a ref that exists is store_io_error",
    sub(HIST, '            if self._head() is not None:\n                raise LocalStoreError("already_initialized", "store", "read")\n            raise', "            raise"))
add("E6", "extra: a file mode is not looked at when a blob is read",
    sub(GIT, 'if entry is None or entry[1] != "blob" or entry[0] not in REGULAR_MODES:', 'if entry is None or entry[1] != "blob":'))
add("E7", "extra: every failed fetch is 'no ref'",
    sub(GIT, "if listing is not None and listing.returncode == 0 and not listing.stdout.strip():", "if True:"))
add("E8", "extra: the entries of the tree are not checked in the mirror",
    sub(OUTBOX, 'if kind != "blob" or mode not in REGULAR_MODES or not valid_name(name):', "if False:"))
add("E9", "extra: push without --porcelain",
    sub(GIT, '["push", "--porcelain", self.remote,', '["push", self.remote,'))
add("E10", "extra: GIT_TERMINAL_PROMPT is not set",
    sub(GIT, '"GIT_TERMINAL_PROMPT": "0", ', ""))
add("E11", "extra: the commit gets the real time (the given time is not used)",
    sub(GIT, 'env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}', "env={}"))
add("E12", "extra: load does not read the remote again",
    sub(OUTBOX, "            self._rebuild()\n        except NotifyError:", "            pass\n        except NotifyError:"))
add("E13", "extra: resend_ids does not read the remote again",
    sub(OUTBOX, "        self._rebuild()\n        return super().resend_ids(d, kind)", "        return super().resend_ids(d, kind)"))
add("E14", "extra: initialize of the outbox on an existing ref returns quietly",
    sub(OUTBOX, '        if head is not None:\n            raise NotifyError(ALREADY_INITIALIZED, "outbox")\n        when', "        if head is not None:\n            return None\n        when"))
add("E15", "extra: the repr of Git shows the work directory",
    sub(GIT, 'return "Git()"', 'return "Git(%s)" % self.workdir'))
add("E16", "extra: a broken current history file is not reported first",
    sub(HIST, "        read_history_bytes(current)                 # a broken current file is reported as it is, first\n", ""))
add("E17", "extra: autocrlf is not switched off",
    sub(GIT, '"-c", "core.autocrlf=false", ', ""))
add("E18", "extra: a layout without history.json is read as no history",
    sub(HIST, '        if data is None:\n            raise LocalStoreError("store_layout_unsupported", "history", "read")\n        return data', "        return data"))
add("E19", "extra: a name that is in the remote but not in the mirror is still sent as ours",
    sub(OUTBOX, "            if commit is None and not failed:       # the remote has the name although the mirror had not: not ours\n                return absent\n",
        "            if commit is None and not failed:\n                return value\n"))
add("E20", "extra: an error of the mirror is not raised (the claim is still sent)",
    sub(OUTBOX, "            if len(added) != 1:\n                raise NotifyError(OUTBOX_IO_ERROR, \"outbox\")\n", "            if len(added) != 1:\n                return value\n"))


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                          timeout=3000)


def git(wt, *a):
    return run(["git", "-c", "user.email=m@example.invalid", "-c", "user.name=mutant"] + list(a), wt)


results = []
base = tempfile.mkdtemp()
for idx, m in enumerate(M):
    if idx % SHARD[1] != SHARD[0] or m["id"] not in os.environ.get("ONLY", m["id"]).split(","):
        continue
    wt = os.path.join(base, "wt_" + m["id"])
    rec = {"id": m["id"], "title": m["title"]}
    git(REPO, "worktree", "add", "-q", "--detach", wt, SHA)
    ok = True
    for path, old, new in m["edits"]:
        full = os.path.join(wt, path)
        text = open(full).read()
        if text.count(old) != 1:
            ok = False
            rec["status"] = "PREP_FAILED"
            rec["detail"] = "pattern found %d times in %s: %r" % (text.count(old), path, old[:60])
            break
        open(full, "w").write(text.replace(old, new))
    if ok:
        compiled = run([PY, "-B", "-c", "import ast,sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]"] +
                       [os.path.join(wt, p) for p in (GIT, HIST, OUTBOX)], wt)
        if compiled.returncode != 0:
            ok = False
            rec["status"] = "PREP_FAILED"
            rec["detail"] = "the mutant does not parse"
    if ok:
        git(wt, "commit", "-qam", "mutant " + m["id"])
        text = ""
        for pat in ("test_s4c_0[1-8]*.py", "test_s4c_10*.py"):
            out = run([PY, "-B", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s", "tests/v2_git_store",
                       "-p", pat], wt)
            text += out.stdout + out.stderr
        mm = re.findall(r"^Ran (\d+) tests", text, re.M)
        failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]*)\)", text, re.M)
        rec["status"] = "DETECTED" if failed else "UNDETECTED"
        rec["ran"] = sum(int(x) for x in mm)
        rec["failing_count"] = len(failed)
        rec["failing_examples"] = ["%s (%s)" % (n, c) for n, c in failed[:4]]
    git(REPO, "worktree", "remove", "--force", wt)
    print(m["id"], rec["status"], rec.get("failing_count"), rec["title"], flush=True)
    results.append(rec)
json.dump(results, open(OUT, "w"), indent=1, ensure_ascii=False)
