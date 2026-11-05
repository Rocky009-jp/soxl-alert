"""Independent mutations for the S4-B review (each one exact replacement, applied alone in a throwaway copy of the
tested commit; the whole tests/v2_notify suite is run). Usage: python s4bi_mutate.py <clean repo> <work dir> <python> [ids]"""
import json, os, shutil, subprocess, sys
REPO, WORK, PY = sys.argv[1], sys.argv[2], sys.argv[3]
ONLY = set(sys.argv[4:])
M = [
 ("V01", "job.py", "the fix removed: no pre-check of the own key before the claim",
  "    taken = outbox.status(notice.d, notice.kind, resend_request_id).status     # a result without a claim is DAMAGED\n    if taken != NONE:\n        return SKIPPED_CLAIMED, None, taken\n", ""),
 ("V02", "job.py", "the pre-check lets a DAMAGED key go on to the claim",
  "    if taken != NONE:\n", "    if taken not in (NONE, DAMAGED):\n"),
 ("V03", "job.py", "the fallback ERROR also looks at the morning claim of the UTC date",
  "judgment_known = notice.kind == HALT or (notice.kind == ERROR and target_d is not None)",
  "judgment_known = notice.kind in (HALT, ERROR)"),
 ("V04", "job.py", "the target D rule uses < instead of <=",
  "            if s.close_at <= now:\n                found = s.date\n", "            if s.close_at < now:\n                found = s.date\n"),
 ("V05", "job.py", "a NOT_SENT original is refused by resend",
  "    if original.status == SENT:\n        return REFUSED_ALREADY_SENT", "    if original.status in (SENT, NOT_SENT):\n        return REFUSED_ALREADY_SENT"),
 ("V06", "job.py", "resend does not look whether its own id was used (the pre-check remains)",
  "    if used:\n        return ResendReport(kind, d, resend_request_id, SKIPPED_CLAIMED, None, original.status)\n", ""),
 ("V07", "outbox.py", "the date in the claim is not compared with the file name",
  "obj[\"kind\"] == kind and obj[\"d\"] == d and", "obj[\"kind\"] == kind and"),
 ("V08", "outbox.py", "resend_of is not checked against the kind of file",
  "and (resend_of is None) == (resend_request_id is None) and (resend_of is None or hex32(resend_of)))", ")"),
 ("V09", "outbox.py", "the status word of a result is not checked",
  "and obj[\"status\"] in RESULT_STATUSES and", "and"),
 ("V10", "compose.py", "the note of a run at the same time in every STOPPED/STALE halt",
  "    if report.code in _CONCURRENT_CODES:\n", "    if True:\n"),
 ("V11", "compose.py", "the label of a fallback ERROR says 対象D",
  "label = \"対象D\" if d_is_target else \"日付（UTC）\"", "label = \"対象D\""),
 ("V12", "job.py", "resend does not check now",
  "    _check_now(now)\n    _check_parts(outbox, sender)\n    if date_text(d) is None:", "    _check_parts(outbox, sender)\n    if date_text(d) is None:"),
 ("V13", "job.py", "the result of a resend is written under the original key",
  "        recorded = outbox.record(notice.d, notice.kind, claim_id, send_status, now, resend_request_id)",
  "        recorded = outbox.record(notice.d, notice.kind, claim_id, send_status, now, None)"),
 ("V14", "__init__.py", "outbox_status ignores kind",
  "    for k in KINDS if kind is None else (kind,):", "    for k in KINDS:"),
 ("V15", "outbox.py", "an existing name counts as created",
  "        if exists:\n            return False\n", "        if exists:\n            return True\n"),
 ("V16", "job.py", "the sender catches Exception only (another BaseException escapes)",
  "    except BaseException:\n        return UNKNOWN", "    except Exception:\n        return UNKNOWN"),
 ("V17", "outbox.py", "a CoreError of the FileOps is not an outbox error",
  "_IO_ERRORS = (OSError, CoreError, ValueError)", "_IO_ERRORS = (OSError, ValueError)"),
 ("V18", "job.py", "resend passes no resend_of",
  "    delivery, send_status, _existing = _take_and_send(outbox, sender, notice, now, resend_request_id,\n                                                      claim[\"claim_id\"])",
  "    delivery, send_status, _existing = _take_and_send(outbox, sender, notice, now, resend_request_id, None)"),
 ("V19", "job.py", "a CoreError that is not a RunError is raised again after the notice",
  "    if program_error is not None:\n        raise program_error",
  "    if program_error is None and error is not None and error[1] is not None:\n        raise CoreError(error[0], 'x')\n    if program_error is not None:\n        raise program_error"),
 ("V20", "compose.py", "the missing lines of a MORNING skip the gap=false days instead (only gap=true)",
  "if not day.skipped_sessions or (only_without_gap and day.gap):", "if not day.skipped_sessions or (only_without_gap and not day.gap):"),
 ("V21", "values.py", "exit 0 also for SKIPPED_CLAIMED whose existing state is UNKNOWN",
  "(delivery == SKIPPED_CLAIMED and existing_status == SENT)", "(delivery == SKIPPED_CLAIMED and existing_status in (SENT, UNKNOWN))"),
 ("V22", "job.py", "the morning job skips a HALT when a judgment exists only if it was SENT",
  "    if judgment != NONE:\n", "    if judgment == SENT:\n"),
 ("V23", "outbox.py", "the canonical JSON keeps the default separators",
  "separators=(\",\", \":\"), ", ""),
 ("V24", "job.py", "the fallback key uses the local date of now instead of the UTC date",
  "    return now.astimezone(datetime.timezone.utc).date().isoformat()", "    return now.date().isoformat()"),
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
