"""Defect injection for the S3-B-5b tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
the runtime, run the v2_history_adopt behaviour tests there and require them to fail. Not part of the product, not a
unittest (run it by hand: <python> -B tests/v2_history_adopt/a5_sensitivity.py [--control] [--jobs N] [ids]). The real
tree is never modified.

The 18 items of the request (section 6) are the numbered mutations M01..M18; an item with several ways to break it has
variants a / b / c. For every mutant the output says whether it is DETECTED (and by which tests), EQUIVALENT (the defect
cannot change any answer; only entries whose `what` starts with EQUIVALENT are counted so), NOT DETECTED or SETUP-ERROR (a
pattern of the mutation does not occur exactly once: the mutant was not made). Every mutant carries the layer that answers:
  OWN   the new package v2_history_adopt decides (arguments, trace, ids, record, basis, confirm, value classes);
  GUARD an existing checker that B-5b changed (v2_history view / restore, v2_history_ops chain, v2_history_restore
        points) decides, and the new tests notice the change;
  SPY   a test that observes which calls reach the existing functions (their count, order and outcome).
Only the behaviour tests test_a5_02 ... test_a5_07 run on a mutant: the Git scope audit (test_a5_08) reads the committed tree.
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
          "v2_history_restore", "v2_history_diagnose", "v2_history_adopt", "tests/v2_history_adopt",
          "tests/v2_history_diagnose", "tests/v2_history_ops", "tests/v2_history_restart", "tests/v2_history_restore",
          "tests/v2_history", "tests/v2_recovery", "tests/v2_persistence")
SUITE_PATTERN = "test_a5_0[2-7]*.py"
VIEW, RESTORE, CHAIN, POINTS = "v2_history/view.py", "v2_history/restore.py", "v2_history_ops/chain.py", "v2_history_restore/points.py"
BUILD, CONFIRM, VALUES, PREPARE = ("v2_history_adopt/build.py", "v2_history_adopt/confirm.py", "v2_history_adopt/values.py",
                                   "v2_history_adopt/prepare.py")

MUTANTS = {}


def mutant(mid, layer, what, *edits):
    MUTANTS[mid] = (layer, list(edits), what)


EVID_TAIL = '''        ev = rec["evidence"]
'''
# 1 the record is not checked at all
mutant("M01", "GUARD", "the chain view accepts an adoption record without checking it",
       (VIEW, "        if kind == RECOVERY_PREFIX_ADOPTION:\n            self.adoption_record(rec, parent_state)\n            return\n",
        "        if kind == RECOVERY_PREFIX_ADOPTION:\n            return\n"))
# 2 state_after
mutant("M02", "GUARD", "the state_after of the adoption record is not compared with the parent's",
       (VIEW, '        if not same(rec["state_after"], parent_state):\n            raise _bad("state_after")\n' + EVID_TAIL, EVID_TAIL))
# 3 discarded_from_seq, claimed_schema_version
mutant("M03a", "GUARD", "discarded_from_seq may differ from the record's own seq",
       (VIEW, ' or not is_int(ev["discarded_from_seq"]) or ev["discarded_from_seq"] != rec["seq"]):', ' or not is_int(ev["discarded_from_seq"])):'))
mutant("M03b", "GUARD", "claimed_schema_version 1 is allowed",
       (VIEW, 'or ev["claimed_schema_version"] != 2', 'or ev["claimed_schema_version"] not in (1, 2)'))
# 4 raw_size, bool
mutant("M04a", "GUARD", "raw_size 0 is allowed", (VIEW, 'or ev["raw_size"] < 1', 'or ev["raw_size"] < 0'))
mutant("M04b", "GUARD", "a bool raw_size is allowed", (VIEW, 'or not is_int(ev["raw_size"]) or', 'or not isinstance(ev["raw_size"], int) or'))
mutant("M04c", "GUARD", "a bool claimed_head_seq is allowed",
       (VIEW, 'or not (ev["claimed_head_seq"] is None or is_int(ev["claimed_head_seq"]))',
        'or not (ev["claimed_head_seq"] is None or isinstance(ev["claimed_head_seq"], int))'))
# 5 basis evidence
mutant("M05", "GUARD", "the evidence of the basis is not compared with the record's",
       (VIEW, ' or not same(basis["evidence"], ev):', ':'))
# 6 request_hash, reason_code
mutant("M06a", "GUARD", "the request hash is not checked",
       (VIEW, '''        if not is_hex64(rec["request_hash"]) or rec["request_hash"] != basis_request_hash(basis):
            raise _bad("request_hash")


def check_view''', '''

def check_view'''))
mutant("M06b", "GUARD", "the reason code is checked on the basis only",
       (VIEW, 'if basis["reason_code"] != REASON_ADOPT or rec["reason_code"] != REASON_ADOPT:', 'if basis["reason_code"] != REASON_ADOPT:'))
# 7 claim_request
mutant("M07", "GUARD", "the adoption record does not claim its request id (a reused id is not seen)",
       (VIEW, '        self.claim_request(rec["request_id"])\n        if not same(rec["state_after"], parent_state):\n            raise _bad("state_after")\n' + EVID_TAIL,
        '        if not same(rec["state_after"], parent_state):\n            raise _bad("state_after")\n' + EVID_TAIL))
# 8 restore floor
mutant("M08a", "GUARD", "B-1: a restore before the last adoption record is not refused",
       (RESTORE, "    if adoptions and point < adoptions[-1]:", "    if False:"))
mutant("M08b", "GUARD", "B-4: a restore point before the last adoption record is not refused",
       (POINTS, "    if taken and seq < taken[-1]:", "    if False:"))
mutant("M08c", "GUARD", "B-1: the adoption record itself is refused as the restore point",
       (RESTORE, "point < adoptions[-1]", "point <= adoptions[-1]"))
mutant("M08d", "GUARD", "B-4: the adoption record itself is refused as the restore point",
       (POINTS, "seq < taken[-1]", "seq <= taken[-1]"))
# 9 _REQUEST_KINDS
mutant("M09", "GUARD", "the adoption record is not among the request kinds of the effective chain",
       (CHAIN, ",\n                  RECOVERY_PREFIX_ADOPTION: RECOVERY_PREFIX_ADOPTION}", "}"))
# 10 status and schema
mutant("M10a", "OWN", "a VALID file is taken as adoptable",
       (BUILD, 'if d["status"] != PREFIX_ONLY:', 'if d["status"] not in (PREFIX_ONLY, "VALID"):'))
mutant("M10b", "OWN", "schema 1 is not refused", (BUILD, 'if d["schema_version"] != 2:', "if False:"))
# 11 count
mutant("M11", "OWN", "adopt_count is not compared with the diagnosis count", (BUILD, 'if adopt_count != verified["count"]:', "if False:"))
# 12 migration trace
mutant("M12a", "OWN", "the migration trace is not judged at all",
       (BUILD, 'if verified["migrated"] is False and _leaves_a_migration(events[k:], discarded["items"]):', "if False:"))
mutant("M12b", "OWN", "only a readable SCHEMA_MIGRATION counts, the origin is not looked at",
       (BUILD, '    return any(isinstance(ev, dict) and ev.get("origin") is not None for ev in events)', "    return False"))
mutant("M12c", "OWN", "only an origin counts, a readable SCHEMA_MIGRATION on the discarded side is not looked at",
       (BUILD, "    if any(item[\"kind\"] == SCHEMA_MIGRATION for item in discarded_items):\n        return True\n", ""))
mutant("M12d", "OWN", "the trace is judged also when the prefix keeps its migration",
       (BUILD, 'if verified["migrated"] is False and _leaves_a_migration', 'if _leaves_a_migration'))
# 13 ids
mutant("M13a", "OWN", "only the effective chain of the prefix is looked at for taken ids",
       (BUILD, '    return {ev.get("request_id") for ev in events if isinstance(ev, dict) and ev.get("request_id") is not None}',
        '    out, cur = set(), len(events) - 1\n    while cur is not None:\n        out.add(events[cur].get("request_id"))\n        cur = events[cur]["parent_seq"]\n    return out - {None}'))
mutant("M13b", "OWN", "the readable ids of the discarded side are not looked at",
       (BUILD, ' or request_id in {i["request_id"] for i in discarded["items"]}:', ':'))
mutant("M13c", "OWN", "the ids of the prefix are not looked at",
       (BUILD, 'if request_id in _physical_ids(prefix_events) or', 'if'))
# 14 values of the record
mutant("M14a", "OWN", "claimed_head_seq is the verified head_seq of the diagnosis",
       (BUILD, '"claimed_head_seq": claimed["head_seq"],', '"claimed_head_seq": verified["head_seq"],'))
mutant("M14b", "OWN", "the parent_hash is the parent's parent",
       (BUILD, '"parent_hash": last["event_hash"],', '"parent_hash": last["parent_hash"],'))
mutant("M14c", "OWN", "state_after is the state of the first record",
       (BUILD, '"state_after": copy.deepcopy(last["state_after"])}', '"state_after": copy.deepcopy(prefix_events[0]["state_after"])}'))
mutant("M14d", "OWN", "raw_size is one less than the length of the bytes",
       (BUILD, '"raw_size": d["raw_size"], "claimed_schema_version": 2,', '"raw_size": d["raw_size"] - 1, "claimed_schema_version": 2,'))
mutant("M14e", "OWN", "the evidence of the basis is a different (older) copy: discarded_from_seq is off by one",
       (BUILD, '"discarded_from_seq": k}\n    request_basis = {"request_id": request_id, "evidence": copy.deepcopy(evidence),',
        '"discarded_from_seq": k}\n    request_basis = {"request_id": request_id, "evidence": dict(copy.deepcopy(evidence), discarded_from_seq=k - 1),'))
mutant("M14f", "OWN", "the request hash is the hash of the whole basis (with requested_at)",
       (BUILD, '"request_hash": basis_request_hash(request_basis),', '"request_hash": __import__("hashlib").sha256(__import__("json").dumps(request_basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),'))
mutant("M14g", "OWN", "the plan's candidate_state_digest is the digest of the whole document",
       (BUILD, '"candidate_head_hash": candidate_check.head_hash, "candidate_state_digest": candidate_check.state_digest,',
        '"candidate_head_hash": candidate_check.head_hash, "candidate_state_digest": candidate_check.history_digest,'))
mutant("M14h", "OWN", "the basis diagnosis_digest is the raw hash",
       (BUILD, '"diagnosis_digest": diagnosis.digest,', '"diagnosis_digest": d["raw_sha256"],'))
# 15 candidate not checked
mutant("M15", "SPY", "the candidate is not passed to validate_history (its fields are written by hand)",
       (BUILD, "        candidate_check = validate_history(candidate)\n",
        '        candidate_check = __import__("types").SimpleNamespace(head_seq=k, head_hash=record["event_hash"], state_digest=prefix_check.state_digest)\n'))
# 16 confirm rebuild
mutant("M16a", "OWN", "confirm rebuilds but does not compare: the plan's candidate is returned",
       (CONFIRM, "        if not same(rebuilt, basis) or rebuilt_candidate != candidate:\n            raise history_plan_mismatch()\n        return AdoptionConfirmResult(CONFIRMED_IN_MEMORY, rebuilt_candidate, plan.plan_hash)",
        "        return AdoptionConfirmResult(CONFIRMED_IN_MEMORY, candidate, plan.plan_hash)"))
mutant("M16b", "OWN", "confirm does not rebuild at all: the plan's basis is trusted",
       (CONFIRM, '''        try:
            rebuilt, rebuilt_candidate = build_adoption(data, diagnosis, basis["adopt_count"], basis["request_id"],
                                                        basis["requested_at"])
        except CoreError:
            raise history_plan_mismatch() from None
        if not same(rebuilt, basis) or rebuilt_candidate != candidate:
            raise history_plan_mismatch()
        return AdoptionConfirmResult(CONFIRMED_IN_MEMORY, rebuilt_candidate, plan.plan_hash)''',
        "        return AdoptionConfirmResult(CONFIRMED_IN_MEMORY, candidate, plan.plan_hash)"))
mutant("M16c", "OWN", "confirm takes the original bytes by the length only (the hash of the raw bytes is not compared)",
       (CONFIRM, 'if diagnosis.raw_sha256 == basis["raw_sha256"] and diagnosis.raw_size == basis["raw_size"]:', 'if diagnosis.raw_size == basis["raw_size"]:'))
# 17 NO_CHANGE and stale / mismatch
mutant("M17a", "OWN", "a re-written (indented) copy of the candidate is NO_CHANGE",
       (CONFIRM, 'if encode_history(candidate).encode("utf-8") == data:',
        'if __import__("json").loads(data.decode("utf-8", "replace") or "null") == candidate.to_dict():'))
mutant("M17b", "OWN", "stale and mismatch are mixed up (other bytes are a mismatch)",
       (CONFIRM, "    raise history_plan_stale()                                                                          # 6",
        "    raise history_plan_mismatch()                                                                       # 6"))
mutant("M17c", "OWN", "the plan's hash asked for is not compared with the plan's",
       (CONFIRM, " or confirmed_plan_hash != view[\"plan_hash\"]", ""))
mutant("M17d", "OWN", "the plan's own candidate is not checked again (its record may be swapped)",
       (CONFIRM, "    return basis, _candidate_of(basis)", '    return basis, History.from_dict(basis["candidate_history"])'))
# 18 aliasing, committed
mutant("M18a", "OWN", "basis returns the internal object", (VALUES, 'return copy.deepcopy(self._view["basis"])', 'return self._view["basis"]'))
mutant("M18b", "OWN", "to_dict returns the internal view", (VALUES, "    def to_dict(self):\n        return copy.deepcopy(self._view)", "    def to_dict(self):\n        return self._view"))
mutant("M18c", "OWN", "the plan says committed", (VALUES, "    def committed(self):\n        return False", "    def committed(self):\n        return True"))
mutant("M18d", "OWN", "the result says committed", (VALUES, "committed = property(lambda self: False)", "committed = property(lambda self: True)"))
mutant("M18e", "OWN", "the plan can be changed", (VALUES, '    def __setattr__(self, name, value):\n        raise AttributeError("AdoptionPlan is immutable")', '    def __setattr__(self, name, value):\n        object.__setattr__(self, name, value)'))
mutant("M18f", "OWN", "the result can be changed", (VALUES, '    def __setattr__(self, name, value):\n        raise AttributeError("AdoptionConfirmResult is immutable")', '    def __setattr__(self, name, value):\n        object.__setattr__(self, name, value)'))
mutant("M18g", "OWN", "the repr prints the whole plan hash", (VALUES, 'shown[3][:12])', 'shown[3])'))
# the arguments of prepare
mutant("M19a", "OWN", "bytearray is accepted as data", (PREPARE, "if type(data) is not bytes:", "if not isinstance(data, (bytes, bytearray)):"))
mutant("M19b", "OWN", "a bool adopt_count is accepted", (PREPARE, "if type(adopt_count) is not int or adopt_count < 1:", "if not isinstance(adopt_count, int) or adopt_count < 1:"))
mutant("M19c", "OWN", "adopt_count 0 is accepted", (PREPARE, "or adopt_count < 1:", "or adopt_count < 0:"))
mutant("M19d", "OWN", "the request id is checked before the instant",
       (PREPARE, '    text = requested_text(requested_at)\n    if not valid_request_id(request_id):\n        raise adoption_invalid("request_id", "request_id")\n',
        '    if not valid_request_id(request_id):\n        raise adoption_invalid("request_id", "request_id")\n    text = requested_text(requested_at)\n'))


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
    proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_adopt",
                           "-p", SUITE_PATTERN], cwd=workdir, capture_output=True, text=True, env=env, timeout=900)
    out = proc.stdout + proc.stderr
    failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]*)\)", out, re.M)
    ran = re.search(r"Ran (\d+) tests", out)
    return proc.returncode, int(ran.group(1)) if ran else 0, failed, out


def one(mid):
    layer, edits, what = MUTANTS[mid]
    work = tempfile.mkdtemp(prefix="a5_mut_")
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
        work = tempfile.mkdtemp(prefix="a5_ctl_")
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
