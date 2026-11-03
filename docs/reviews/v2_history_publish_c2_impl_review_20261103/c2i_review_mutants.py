"""C-2 implementation review: independent mutants (not in the implementer's list of 39).
usage: c2i_review_mutants.py <repo> <tested-sha> <python> [ids...]
Each mutant runs on a `git archive` copy of the tested commit: tests/v2_history_publish test_c2_0[1-7]*.py (not
fail-fast, so the number of failing tests is shown). Nothing is written to the repository."""
import os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

REPO, SHA, PY = sys.argv[1:4]
ONLY = set(sys.argv[4:])
B, CK, RD, VL = ("v2_history_publish/build.py", "v2_history_publish/check.py", "v2_history_publish/read.py",
                 "v2_history_publish/values.py")
M = [
 ("V01", "check: the candidate state digest is not compared", CK,
  '            or sha256_text(canonical_json(candidate.current_state)) != body["candidate_state_digest"]):', '            ):'),
 ("V02", "check: the candidate head hash is not compared", CK,
  '            or check.head_hash != body["candidate_head_hash"]\n', '\n'),
 ("V03", "reconcile: PUBLISHED by the digest only (no head seq, no head hash)", CK,
  '    if (check.history_digest, check.head_seq, check.head_hash) == (body["candidate_digest"],\n                                                                   body["candidate_head_seq"],\n                                                                   body["candidate_head_hash"]):',
  '    if check.history_digest == body["candidate_digest"]:'),
 ("V04", "reconcile: a CREATE with no file is a CONFLICT", CK,
  'NOT_PUBLISHED if mode == CREATE else CONFLICT', 'CONFLICT'),
 ("V05", "form: a DAILY publication may have no day", CK,
  '        if body["d"] is None or not is_date(body["d"]):', '        if body["d"] is not None and not is_date(body["d"]):'),
 ("V06", "form: the request id of a plan source is not checked", CK,
  '        if not valid_request_id(body["request_id"]) or not is_hex64(body["plan_hash"]):', '        if not is_hex64(body["plan_hash"]):'),
 ("V07", "form: the expected identity of a REPLACE is not checked", CK,
  '        if mode == REPLACE and not _raw_ok(body["expected"]):', '        if False:'),
 ("V08", "form: the v1 identity of a MIGRATION is not checked", CK,
  '            if not _raw_ok(body["source_v1"]):', '            if False:'),
 ("V09", "form: a CREATE may name an expected value", CK,
  '        if mode == CREATE and body["expected"] is not None:', '        if False:'),
 ("V10", "arguments: v1 bytes of another type are not refused as a misuse", CK,
  '        if source_v1 is not None and type(source_v1) is not bytes:\n            raise publication_invalid("source_v1")\n', ''),
 ("V11", "read: raw_identity takes a bytearray", RD,
  '    if type(data) is not bytes:\n        raise history_unreadable("type")\n    return {', '    if not isinstance(data, (bytes, bytearray)):\n        raise history_unreadable("type")\n    return {'),
 ("V12", "build: RESTORE without the status test", B,
  '    res = confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_observations, series)\n    if res.status != RESTORE_CONFIRMED:\n        raise publication_refused("no_change")\n',
  '    res = confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_observations, series)\n'),
 ("V13", "build: RESTART without the status test", B,
  '    res = confirm_restart_plan(plan, confirmed_plan_hash, history, sessions, raw_observations)\n    if res.status != RESTART_CONFIRMED:\n        raise publication_refused("no_change")\n',
  '    res = confirm_restart_plan(plan, confirmed_plan_hash, history, sessions, raw_observations)\n'),
 ("V14", "build: the v1 snapshot is not validated before the confirm step", B,
  '    snapshot = decode_snapshot(text)\n    validate_snapshot(snapshot)\n', '    snapshot = decode_snapshot(text)\n'),
 ("V15", "build: the v1 bytes are read with utf-8-sig (a BOM is removed)", B,
  '        text = data.decode("utf-8")\n    except UnicodeDecodeError:\n        raise snapshot_invalid("utf8")', '        text = data.decode("utf-8-sig")\n    except UnicodeDecodeError:\n        raise snapshot_invalid("utf8")'),
 ("V16", "check: the first seq of the records is off by one", CK,
  '        first = body["expected"]["head_seq"] + 1', '        first = body["expected"]["head_seq"]'),
 ("V17", "read: invalid UTF-8 is replaced instead of refused", RD,
  '        text = data.decode("utf-8")\n    except UnicodeDecodeError:\n        raise history_unreadable("utf8") from None',
  '        text = data.decode("utf-8", "replace")\n    except UnicodeDecodeError:\n        raise history_unreadable("utf8") from None'),
 ("V18", "check: APPEND compares the canonical bytes instead of the digest (an indented file is stale)", CK,
  '        current_history, check = read_history_bytes(current)\n        e = body["expected"]\n',
  '        current_history, check = read_history_bytes(current)\n        if current != __import__("v2_history_publish.read", fromlist=["r"]).history_bytes(current_history):\n            raise publication_stale("head")\n        e = body["expected"]\n'),
 ("V19", "build: adoption does not compare the plan identity with the received bytes", B,
  '    if (basis["raw_sha256"], basis["raw_size"]) != (raw["raw_sha256"], raw["raw_size"]):\n        raise candidate_invalid()\n', ''),
 ("V20", "reconcile: the misuse of the current type is not refused", CK,
  '    _arguments(body, current, None, False)\n', ''),
 ("V21", "values: the summary shows a request id that is not valid", VL,
  'rid = b["request_id"] if b["request_id"] is not None and valid_request_id(b["request_id"]) else None', 'rid = b["request_id"]'),
 ("V22", "check: the error of an unreadable current is publication_stale (not history_invalid)", CK,
  '        current_history, check = read_history_bytes(current)\n        e = body["expected"]\n',
  '        try:\n            current_history, check = read_history_bytes(current)\n        except CoreError:\n            raise publication_stale("head") from None\n        e = body["expected"]\n'),
]


def one(m):
    mid, desc, path, old, new = m
    tmp = tempfile.mkdtemp(prefix="c2i_" + mid + "_")
    try:
        subprocess.run("git -C %s archive %s | tar -x -C %s" % (REPO, SHA, tmp), shell=True, check=True)
        full = os.path.join(tmp, path)
        s = open(full).read()
        if s.count(old) != 1:
            return mid, "PREP_FAILED", desc, "%d matches" % s.count(old)
        open(full, "w").write(s.replace(old, new))
        p = subprocess.run([PY, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_publish", "-p",
                            "test_c2_0[1-7]*.py"], cwd=tmp, capture_output=True, text=True, timeout=1800,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        out = p.stdout + p.stderr
        fails = [l.split(" (")[0] for l in out.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
        tail = (re.findall(r"^(OK.*|FAILED.*)$", out, re.M) or ["?"])[-1]
        return mid, "DETECTED" if p.returncode else "SURVIVED", desc, "%s | %s" % (tail, "; ".join(fails[:3]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


todo = [m for m in M if not ONLY or m[0] in ONLY]
with ThreadPoolExecutor(max_workers=2) as ex:
    for r in ex.map(one, todo):
        print(*r, sep=" | ", flush=True)
