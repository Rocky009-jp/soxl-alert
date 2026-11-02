"""Defect injection for the S3-B-5a tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
v2_history_diagnose, run the v2_history_diagnose behaviour tests there and require them to fail. Not part of the
product, not a unittest (run it by hand: <python> -B tests/v2_history_diagnose/d5_sensitivity.py [--control] [--jobs N]
[ids]). The real tree is never modified.

The 17 items of the request (section 6) are the numbered mutations M01..M17; an item with several ways to break it has
variants a / b / c. For every mutant the output says whether it is DETECTED (and by which tests), EQUIVALENT (the defect
cannot change any answer; the reason is in `what`, and only entries whose text starts with EQUIVALENT are counted so),
NOT DETECTED (no test tells it apart) or SETUP-ERROR (a pattern of the mutation does not occur exactly once: the mutant
was not made). Every mutant also carries the layer that answers, so that the B-5a decision itself, the independent guard
of an unchanged checker and a delegation spy are not counted as one thing:
  OWN   the B-5a package decides (its stages, its prefix search, its report shape, its value class);
  GUARD an unchanged checker (validate_history / validate_snapshot / decode_history) would refuse or accept the same input
        regardless of this package, and a test of the B-5a answer is what notices the change;
  SPY   a test that observes which calls reach the unchanged checkers (their order, count and outcome).
The slow cost measurement (test_d5_07) and the Git scope audit (test_d5_08) are not run on a mutant: the scope audit
reads the committed tree, and the cost test only measures.
"""
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
COPIED = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
          "v2_history_restore", "v2_history_diagnose", "tests/v2_history_diagnose", "tests/v2_history_ops",
          "tests/v2_history_restore", "tests/v2_history", "tests/v2_recovery", "tests/v2_persistence")
PK = "v2_history_diagnose/"
DIAGNOSE, DESCRIBE, FAILURE, VALUES = PK + "diagnose.py", PK + "describe.py", PK + "failure.py", PK + "values.py"
SUITE_PATTERN = "test_d5_0[1-6]*.py"

Q = '"'
LOOP = "    for k in range(len(events), 0, -1):\n"
TRY_V2 = "                verified = verified_v2(validate_history(History.from_dict(history_dict(events[:k]))))\n"
CATCH = "        except CAUGHT:\n            continue\n        return k, verified\n    return None\n"

# id: (layer, files-and-edits, what). edits: list of (relative file, old text, new text); old must occur exactly once.
MUTANTS = {}


def mutant(mid, layer, what, *edits):
    MUTANTS[mid] = (layer, list(edits), what)


# 1 UTF-8
mutant("M01a", "OWN", 'decode with errors="replace"', (DIAGNOSE, 'text = data.decode("utf-8")', 'text = data.decode("utf-8", errors="replace")'))
mutant("M01b", "OWN", "decode with utf-8-sig (the BOM is removed)", (DIAGNOSE, 'text = data.decode("utf-8")', 'text = data.decode("utf-8-sig")'))
mutant("M01c", "OWN", 'decode with errors="ignore"', (DIAGNOSE, 'text = data.decode("utf-8")', 'text = data.decode("utf-8", errors="ignore")'))
# 2 lenient JSON
mutant("M02a", "OWN", "plain json.loads: duplicate keys are accepted",
       (DIAGNOSE, "history = decode_history(text)", 'history = History.from_dict(__import__("json").loads(text))'))
mutant("M02b", "OWN", "json.loads with parse_constant: NaN / Infinity become 0",
       (DIAGNOSE, "history = decode_history(text)",
        'history = History.from_dict(__import__("json").loads(text, parse_constant=lambda c: 0))'))
# 3 version and core_sha
mutant("M03a", "OWN", "a different core_sha no longer stops at the schema stage", (DIAGNOSE, 'if top.get("core_sha") != CORE_SHA:', "if False:"))
mutant("M03b", "OWN", "an unsupported schema_version (3, 0, ...) no longer stops", (DIAGNOSE, "if not is_int(version) or version not in (1, 2):", "if not is_int(version):"))
# 4 checkers swapped
mutant("M04a", "OWN", "the whole file of version 1 goes to the history checker, version 2 to the snapshot checker",
       (DIAGNOSE, "    if version == 2:\n        return verified_v2(validate_history(history))", "    if version == 1:\n        return verified_v2(validate_history(history))"))
mutant("M04b", "OWN", "the prefix search swaps the checkers of the two versions",
       (DIAGNOSE, "            if version == 2:\n                verified = verified_v2", "            if version == 1:\n                verified = verified_v2"))
# 5 order of the search
mutant("M05a", "OWN", "search from below: the first passing k (k = 1) is taken", (DIAGNOSE, LOOP, "    for k in range(1, len(events) + 1):\n"))
mutant("M05b", "OWN", "search from below that stops at the first k that fails and keeps the last one that passed",
       (DIAGNOSE, LOOP, "    best = None\n    for k in range(1, len(events) + 1):\n"),
       (DIAGNOSE, CATCH, "        except CAUGHT:\n            return best\n        best = (k, verified)\n    return best\n"))
mutant("M05c", "OWN", "bisection (assumes that prefix validity is monotonic)",
       (DIAGNOSE, LOOP + "        try:\n", "    lo, hi, best = 1, len(events), None\n    while lo <= hi:\n        k = (lo + hi) // 2\n        try:\n"),
       (DIAGNOSE, CATCH, "        except CAUGHT:\n            hi = k - 1\n            continue\n        best = (k, verified)\n        lo = k + 1\n    return best\n"))
mutant("M05d", "OWN", "an own batch-boundary rule: k is refused when the next record is an APPLY",
       (DIAGNOSE, "        except CAUGHT:\n            continue\n        return k, verified",
        "        except CAUGHT:\n            continue\n        if k < len(events) and isinstance(events[k], dict) and events[k].get(\"kind\") == \"APPLY\":\n            continue\n        return k, verified"))
# 6 header rebuilt
mutant("M06a", "OWN", "version 2: each k is checked under the file's own header, not a rebuilt one",
       (DIAGNOSE, "History.from_dict(history_dict(events[:k]))", "History.from_dict(dict(_TOP[0], events=events[:k]))"),
       (DIAGNOSE, "def _longest_prefix(events, version):", "_TOP = [None]\n\n\ndef _longest_prefix(events, version):"),
       (DIAGNOSE, "        found = _longest_prefix(events, version)", "        _TOP[0] = top\n        found = _longest_prefix(events, version)"))
mutant("M06b", "OWN", "version 1: each k is checked under the file's own header",
       (DIAGNOSE, "Snapshot.from_dict(snapshot_dict(events[:k]))", "Snapshot.from_dict(dict(_TOP[0], events=events[:k]))"),
       (DIAGNOSE, "def _longest_prefix(events, version):", "_TOP = [None]\n\n\ndef _longest_prefix(events, version):"),
       (DIAGNOSE, "        found = _longest_prefix(events, version)", "        _TOP[0] = top\n        found = _longest_prefix(events, version)"))
# 7 k = n
mutant("M07a", "OWN", "k = n is not tried", (DIAGNOSE, LOOP, "    for k in range(len(events) - 1, 0, -1):\n"))
mutant("M07b", "OWN", "k = n passing is reported as VALID",
       (DIAGNOSE, "            return _report(data, PREFIX_ONLY, failure=first_error, verified=verified,",
        "            if k == len(events):\n                return _report(data, VALID, verified=verified, **common)\n            return _report(data, PREFIX_ONLY, failure=first_error, verified=verified,"))
# 8 whole check skipped
mutant("M08a", "OWN", "the whole-file check is skipped (the prefix search always starts)",
       (DIAGNOSE, '    """The whole document through the unchanged checker of its own version."""\n', '    """The whole document through the unchanged checker of its own version."""\n    raise ValueError("skipped")\n'))
# 9 exceptions
mutant("M09a", "OWN", "an exception while trying a prefix is not caught", (DIAGNOSE, CATCH, "        except PersistenceError:\n            continue\n        return k, verified\n    return None\n"))
mutant("M09b", "OWN", "the exception text goes into the failure", (FAILURE, 'return failure(stage, "history_invalid", "history", "malformed")', 'return failure(stage, "history_invalid", "history", str(exc))'))
mutant("M09c", "OWN", "identifiers of an error are not sanitised", (FAILURE, "    if not isinstance(x, str) or not 0 < len(x) <= _MAX_IDENT:\n        return None\n", "    if isinstance(x, str):\n        return x\n    return None\n"))
# 10 failure
mutant("M10a", "OWN", "the failure is the error of the last prefix tried",
       (DIAGNOSE, CATCH, "        except CAUGHT as late:\n            _LAST.append(late)\n            continue\n        return k, verified\n    return None\n"),
       (DIAGNOSE, "def _longest_prefix(events, version):", "_LAST = []\n\n\ndef _longest_prefix(events, version):"),
       (DIAGNOSE, "            return _report(data, PREFIX_ONLY, failure=first_error, verified=verified,",
        "            return _report(data, PREFIX_ONLY, failure=(from_exception(STAGE_VALIDATE, _LAST[-1], version) if _LAST else first_error), verified=verified,"))
mutant("M10b", "OWN", "a wrong stage in the failure of the whole-file check", (DIAGNOSE, "first_error = from_exception(STAGE_VALIDATE, exc, version)", "first_error = from_exception(STAGE_SCHEMA, exc, version)"))
# 11 canonical_text
mutant("M11a", "OWN", "canonical_text=false makes the file not VALID", (DIAGNOSE, "        return _report(data, VALID, verified=verified, **common)", "        return _report(data, VALID if canonical else PREFIX_ONLY, verified=verified, **common)"))
# 12 discarded items
mutant("M12a", "OWN", "a request_id that is not valid is shown", (DESCRIBE, '"request_id": rid if valid_request_id(rid) else None', '"request_id": rid'))
mutant("M12b", "OWN", "a d that is not a date is shown", (DESCRIBE, '"d": d if is_date(d) else None', '"d": d'))
mutant("M12c", "OWN", 'an unknown kind is shown instead of "?"', (DESCRIBE, '"kind": kind if isinstance(kind, str) and kind in kinds else "?",', '"kind": kind,'))
mutant("M12d", "OWN", "a seq that is not an integer is shown", (DESCRIBE, '"seq": seq if is_int(seq) else None,', '"seq": seq,'))
mutant("M12e", "OWN", "resume_after of a RESTART_UNKNOWN is shown as d", (DESCRIBE, 'd = ev.get("d")', 'd = ev.get("d") or ev.get("resume_after")'))
mutant("M12f", "OWN", "a record that is not a dict is not turned into an empty item", (DESCRIBE, '''    if not isinstance(ev, dict):
        return {"index": index, "kind": "?", "seq": None, "d": None, "request_id": None}''', '''    if not isinstance(ev, dict):
        raise TypeError("not a record")'''))
# 13 verified columns
mutant("M13a", "OWN", "document_digest is the state digest (version 2)", (DESCRIBE, '"document_digest": check.history_digest', '"document_digest": check.state_digest'))
mutant("M13b", "OWN", "state_digest is the document digest (version 2)", (DESCRIBE, '"state_digest": check.state_digest', '"state_digest": check.history_digest'))
mutant("M13c", "OWN", "version 1 count is the head_seq", (DESCRIBE, '    return {"count": count, "head_seq": valid.head_seq', '    return {"count": valid.head_seq, "head_seq": valid.head_seq'))
mutant("M13d", "OWN", "version 1 migrated is false instead of null", (DESCRIBE, '"effective_count": count, "superseded_count": 0, "migrated": None}', '"effective_count": count, "superseded_count": 0, "migrated": False}'))
mutant("M13e", "OWN", "version 1 document_digest is computed over the state", (DESCRIBE, '"document_digest": sha256_text(document_text),', '"document_digest": sha256_text(canonical_json(state.to_dict())),'))
mutant("M13f", "OWN", "version 2 count is the effective count", (DESCRIBE, '{"count": check.record_count,', '{"count": len(check.effective_seqs),'))
mutant("M13g", "OWN", "the state digest of version 1 is taken over the whole valid snapshot head", (DESCRIBE, '"state_digest": sha256_text(canonical_json(state.to_dict())),', '"state_digest": sha256_text(valid.head_hash),'))
mutant("M13h", "OWN", "version 1 boundary is not GENESIS", (DESCRIBE, '"boundary": {"kind": "GENESIS", "seq": 0, "after": valid.start_after},', '"boundary": {"kind": "RESTART_UNKNOWN", "seq": 0, "after": valid.start_after},'))
# 14 aliasing and retention
mutant("M14a", "OWN", "to_dict returns the internal view", (VALUES, "    def to_dict(self):\n        return copy.deepcopy(self._view)", "    def to_dict(self):\n        return self._view"))
mutant("M14b", "OWN", "the verified reader returns the internal object", (VALUES, 'return copy.deepcopy(self._view["verified"])', 'return self._view["verified"]'))
mutant("M14c", "OWN", "the constructor keeps the caller's dict", (VALUES, 'object.__setattr__(self, "_view", copy.deepcopy(fields))', 'object.__setattr__(self, "_view", fields)'))
mutant("M14d", "OWN", "the value gets a __dict__", (VALUES, '__slots__ = ("_text", "_view")', '__slots__ = ("_text", "_view", "__dict__")'))
mutant("M14e", "OWN", "the value can be changed", (VALUES, '    def __setattr__(self, name, value):\n        raise AttributeError("HistoryDiagnosis is immutable")', '    def __setattr__(self, name, value):\n        object.__setattr__(self, name, value)'))
mutant("M14f", "OWN", "the value keeps the dict it was made from in a third slot",
       (VALUES, '__slots__ = ("_text", "_view")', '__slots__ = ("_text", "_view", "_raw")'),
       (VALUES, 'object.__setattr__(self, "_text", text)', 'object.__setattr__(self, "_text", text)\n        object.__setattr__(self, "_raw", fields)'))

# 15 argument type and content exceptions
mutant("M15a", "OWN", "bytearray is accepted", (DIAGNOSE, "if type(data) is not bytes:", "if not isinstance(data, (bytes, bytearray)):"))
mutant("M15b", "OWN", "a bytes subclass is accepted", (DIAGNOSE, "if type(data) is not bytes:", "if not isinstance(data, bytes):"))
mutant("M15c", "OWN", "a content problem (non-UTF-8) raises", (DIAGNOSE, '        return _report(data, UNREADABLE, failure=failure(STAGE_UTF8, "unreadable", "data", "utf8"))', '        raise PersistenceError("diagnosis_invalid", "data", rule="utf8")'))
# 16 non-determinism
mutant("M16a", "OWN", "the digest has an address in it", (VALUES, "return sha256_text(self._text)", "return sha256_text(self._text + str(id(self)))"))
mutant("M16b", "OWN", "raw_size has a clock in it", (DIAGNOSE, '"raw_size": len(data),', '"raw_size": len(data) + __import__("time").time_ns() % 7,'))
mutant("M16c", "OWN", "operation has a counter in it", (DIAGNOSE, 'out = {"operation": OPERATION,', 'out = {"operation": OPERATION + str(len(__import__("sys").modules) % 1),'))
# 17 delegation
mutant("M17a", "SPY", "a prefix k < n is judged by its last event hash only; the checker is not called for it",
       (DIAGNOSE, TRY_V2, "                if k < len(events):\n                    if events[k - 1][\"event_hash\"] != compute_event_hash(events[k - 1]):\n                        raise ValueError(\"hash\")\n                    verified = verified_v2(validate_history(History.from_dict(history_dict(events[:1]))))\n                else:\n                    verified = verified_v2(validate_history(History.from_dict(history_dict(events[:k]))))\n"),
       (DIAGNOSE, "from v2_persistence.codec import CORE_SHA,", "from v2_persistence.codec import compute_event_hash, CORE_SHA,"))
mutant("M17b", "SPY", "the checker is called for a k but its refusal is ignored for the restore batch kinds",
       (DIAGNOSE, TRY_V2, "                try:\n                    verified = verified_v2(validate_history(History.from_dict(history_dict(events[:k]))))\n                except PersistenceError as refusal:\n                    if refusal.rule not in (\"restore_incomplete\", \"batch\"):\n                        raise\n                    verified = verified_v2(validate_history(History.from_dict(history_dict(events[:1]))))\n"))
mutant("M17c", "SPY", "the checker used for the prefix is the one of the whole file (a name kept from the first call)",
       (DIAGNOSE, TRY_V2, "                verified = verified_v2(_FIRST[0](History.from_dict(history_dict(events[:k]))))\n"),
       (DIAGNOSE, "def _longest_prefix(events, version):", "_FIRST = [lambda h: validate_history(History.from_dict(history_dict(h.events[:1])))]\n\n\ndef _longest_prefix(events, version):"))


def apply(workdir, edits):
    for rel, old, new in edits:
        path = os.path.join(workdir, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if text.count(old) != 1:
            return "pattern occurs %d times in %s: %r" % (text.count(old), rel, old[:60])
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))
    return None


def copy_tree(dest):
    for rel in COPIED:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def run_suite(workdir):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_diagnose",
                           "-p", SUITE_PATTERN], cwd=workdir, capture_output=True, text=True, env=env, timeout=900)
    out = proc.stdout + proc.stderr
    failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]*)\)", out, re.M)
    ran = re.search(r"Ran (\d+) tests", out)
    return proc.returncode, int(ran.group(1)) if ran else 0, failed, out


def one(mid):
    layer, edits, what = MUTANTS[mid]
    work = tempfile.mkdtemp(prefix="d5_mut_")
    try:
        copy_tree(work)
        if edits:
            problem = apply(work, edits)
            if problem:
                return mid, "SETUP-ERROR", layer, what, problem, []
        code, ran, failed, out = run_suite(work)
        if ran == 0:
            return mid, "SETUP-ERROR", layer, what, "no test ran: " + out[-300:], []
        names = sorted({"%s.%s" % (cls.split(".")[-1] if "." in cls else cls, name) for name, cls in failed})
        if code != 0:
            return mid, "DETECTED", layer, what, "%d failing" % len(failed), names
        return mid, "NOT DETECTED", layer, what, "", []
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    jobs = 4
    control = False
    ids = []
    it = iter(argv)
    for a in it:
        if a == "--jobs":
            jobs = int(next(it))
        elif a == "--control":
            control = True
        else:
            ids.append(a)
    if control:
        work = tempfile.mkdtemp(prefix="d5_ctl_")
        try:
            copy_tree(work)
            code, ran, failed, out = run_suite(work)
            print("CONTROL (no defect): exit=%d ran=%d failed=%d" % (code, ran, len(failed)))
            if code != 0:
                print(out[-2000:])
            return code
        finally:
            shutil.rmtree(work, ignore_errors=True)
    chosen = [m for m in MUTANTS if not ids or any(m == i or m.startswith(i) for i in ids)]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for res in pool.map(one, chosen):
            results.append(res)
            mid, status, layer, what, note, names = res
            print("%s [%s] %s: %s %s" % (mid, layer, status, what, note))
            for n in names[:4]:
                print("      by", n)
            sys.stdout.flush()
    counts = {}
    for _m, status, *_rest in results:
        counts[status] = counts.get(status, 0) + 1
    print("SUMMARY: %d mutants; %s" % (len(results), ", ".join("%s %d" % kv for kv in sorted(counts.items()))))
    return 0 if not counts.get("NOT DETECTED") and not counts.get("SETUP-ERROR") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
