"""Defect injection for the B-1 tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
v2_history, run the v2_history tests there and require them to fail. Not part of the product, not a unittest (run it by
hand: <python> -B tests/v2_history/sensitivity_check.py [ids]). The real tree is never modified.

Every defect is a list of (old, new) text patches, each old text occurring exactly once. Defects marked EQUIVALENT
are listed with the reason no test can tell them apart; they are reported separately, never counted as detected.
A defect whose patch does not apply is reported as NOT RUN (setup error), never as detected.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# (id, group, file, [(old, new), ...], what is broken)
MUTATIONS = [
    ("D01", 1, "restore.py", [("    superseded = chain[pos[point] + 1:]\n", "    superseded = list(range(point + 1, k))\n")],
     "superseded list taken as the physical range after the restore point"),
    ("D02", 2, "validate.py", [
        ("    parents = []\n    for i, ev in enumerate(events):\n",
         "    parents = []\n    retired = set()\n    for e in events:\n"
         "        if e.get(\"kind\") == \"RECOVERY_RESTORE\" and isinstance(e.get(\"parent_seq\"), int):\n"
         "            retired.update(range(e[\"parent_seq\"] + 1, e[\"seq\"]))\n"
         "    for i, ev in enumerate(events):\n"),
        ("        if not is_hex64(ev[\"event_hash\"]) or ev[\"event_hash\"] != compute_event_hash(ev):\n            raise _bad(\"event_hash\")\n        if i > 0:\n",
         "        if i not in retired and (not is_hex64(ev[\"event_hash\"]) or ev[\"event_hash\"] != compute_event_hash(ev)):\n            raise _bad(\"event_hash\")\n        if i > 0 and i not in retired:\n")],
     "retired records: event_hash and audit chain not checked"),
    ("D03", 3, "restore.py", [
        ("    if point not in pos:\n        raise _bad(\"restore_point_not_effective\")\n",
         "    if point not in pos:\n        chain = sorted(chain + [point])\n        pos = {s: i for i, s in enumerate(chain)}\n")],
     "a restore point that is not on the effective chain (retired) is accepted"),
    ("D04", 4, "restore.py", [
        ("        if created >= len(events) or events[created][\"kind\"] != events[s][\"kind\"]:\n            raise _bad(\"restore_incomplete\")\n",
         "        if created < len(events) and events[created][\"kind\"] != events[s][\"kind\"]:\n            raise _bad(\"restore_incomplete\")\n"),
        ("    for entry, s, created in plan:\n        old, new = events[s], events[created]\n",
         "    for entry, s, created in plan:\n        if created >= len(events):\n            continue\n        old, new = events[s], events[created]\n")],
     "a cut restore batch (records missing after the RESTORE) is accepted"),
    ("D05", 5, "restore.py", [
        ("    for key in (\"decision\", \"row\", \"prev_row\", \"prev_session_date\"):\n", "    for key in (\"prev_session_date\",):\n")],
     "REAPPLY does not compare decision / row / prev_row"),
    ("D06", 6, "restore.py", [
        ("    if entry[\"d\"] != old[\"d\"] or entry[\"same_as_superseded\"] is not fact:\n", "    if entry[\"d\"] != old[\"d\"]:\n")],
     "same_as_superseded is not checked as a fact"),
    ("D07", 7, "restore.py", [
        ("    if not same(new[\"applied_ref\"], want_applied) or not same(new[\"missing_ref\"], want_missing):\n        raise _bad(\"restore_ref_unmapped\")\n",
         "    if False:\n        raise _bad(\"restore_ref_unmapped\")\n")],
     "REPLAY references are not checked against the mapping"),
    ("D08", 8, "restore.py", [
        ("    if any(len(ops) > 1 for ops in by_request.values()):\n        raise _bad(\"restore_partial_batch\")\n", "    pass\n")],
     "partial-batch DROP / REPLAY is accepted"),
    ("D09", 9, "view.py", [
        ("            ev = make_apply_event(i, events[-1][\"event_hash\"], rec[\"d\"], ci,", "            ev = make_apply_event(i, rec[\"parent_hash\"], rec[\"d\"], ci,")],
     "S1 projection uses the physical parent hash instead of the re-attached one"),
    ("D10a", 10, "view.py", [
        ("        if resume < max(v for v in expected.values() if v is not None):\n",
         "        if resume < max(v for k, v in expected.items() if v is not None and k != \"last_declared_d\"):\n")],
     "restart floor: resume_after ignores the declared day"),
    ("D10b", 10, "view.py", [
        ("        expected = {\"last_apply_d\": self.latest_apply_d, \"last_declared_d\": self.latest_declared_d,\n",
         "        expected = {\"last_apply_d\": self.latest_apply_d, \"last_declared_d\": rec[\"floor\"].get(\"last_declared_d\"),\n")],
     "restart floor: stored last_declared_d is not recomputed"),
    ("D11a", 11, "view.py", [
        ("        if resume < max(v for v in expected.values() if v is not None):\n",
         "        if resume < max(v for k, v in expected.items() if v is not None and k != \"prev_boundary\"):\n")],
     "restart floor: resume_after ignores the previous boundary"),
    ("D11b", 11, "view.py", [
        ("        expected = {\"last_apply_d\": self.latest_apply_d, \"last_declared_d\": self.latest_declared_d,\n                    \"prev_boundary\": prev_boundary}\n",
         "        expected = {\"last_apply_d\": self.latest_apply_d, \"last_declared_d\": self.latest_declared_d,\n                    \"prev_boundary\": rec[\"floor\"].get(\"prev_boundary\")}\n")],
     "restart floor: stored prev_boundary is not recomputed"),
    ("D12", 12, "view.py", [
        ("        seg = self.seg()\n        best, session = seg.date, seg.session\n", "        seg = self.segments[0]\n        best, session = seg.date, seg.session\n")],
     "DECLARE frontier ignores the segment boundary (uses the first boundary)"),
    ("D13a", 13, "view.py", [
        ("        self.apply_by_seq = {}\n", "        self.apply_by_seq = {i.seq: i for s in segments for i in s.infos}\n")],
     "EQUIVALENT: ACK may refer to an APPLY that is not an ancestor (a forward reference needs the later record's event_hash, which depends on the referencing record: a hash cycle, so the hash comparison already refuses it; the walk-order lookup is defence in depth)"),
    ("D13b", 13, "view.py", [
        ("        self.declare_by_seq = {}\n",
         "        self.declare_by_seq = {r[\"seq\"]: (r[\"event_hash\"], r[\"d\"]) for r in recs if r[\"kind\"] == DECLARE_MISSING}\n")],
     "EQUIVALENT: LATE may refer to a declaration that is not an ancestor (same hash-cycle reason as D13a)"),
    ("D14", 14, "migration.py", [
        ("            or source[\"head_hash\"] != head[\"event_hash\"]\n            or source[\"snapshot_digest\"] != sha256_text(encode_snapshot(snapshot))):\n",
         "            or source[\"head_hash\"] != head[\"event_hash\"]):\n")],
     "migration reverse check skips the v1 snapshot digest"),
    ("D15", 15, "migration.py", [
        ("        if s3a[\"resolution_hash\"] != origin[\"resolution_hash\"]:\n            raise _bad(\"origin\")\n",
         "        if False:\n            raise _bad(\"origin\")\n")],
     "S3-A resolution_hash is not recomputed against origin"),
    ("D16", 16, "migration.py", [
        ("            if (ev[\"origin\"] is not None) != migrated:\n", "            if migrated and ev[\"origin\"] is None:\n")],
     "an origin on a record after the SCHEMA_MIGRATION is accepted"),
    ("D17", 17, "migrate.py", [
        ("    effective = resolve_observations(snapshot, resolutions, sessions, raw_observations, check_d)\n",
         "    class effective:\n        ledger_digest = ledger_digest(parse_ledger(raw_observations))\n"
         "        effective_digest = sha256_text(canonical_json(raw_observations))\n")],
     "plan skips the resolve_observations re-check"),
    ("D18a", 18, "migrate.py", [
        ("    if (not isinstance(basis, dict) or view[\"plan_hash\"] != sha256_text(canonical_json(basis))\n"
         "            or confirmed_plan_hash != view[\"plan_hash\"] or set(basis) != _BASIS_KEYS):\n",
         "    if (not isinstance(basis, dict) or set(basis) != _BASIS_KEYS):\n")],
     "confirm ignores the plan hash (stored and confirmed)"),
    ("D18b", 18, "migrate.py", [
        ("            or confirmed_plan_hash != view[\"plan_hash\"] or set(basis) != _BASIS_KEYS):\n",
         "            or set(basis) != _BASIS_KEYS):\n")],
     "confirm ignores the confirmed plan hash"),
    ("D18c", 18, "migrate.py", [
        ("    if (basis[\"source_snapshot_digest\"] != sha256_text(encode_snapshot(snapshot_v1))      # 3 valid but different\n"
         "            or basis[\"source_head_seq\"] != snapshot_v1.head_seq or basis[\"source_head_hash\"] != snapshot_v1.head_hash\n",
         "    if (basis[\"source_head_seq\"] != snapshot_v1.head_seq or basis[\"source_head_hash\"] != snapshot_v1.head_hash\n")],
     "confirm ignores the snapshot digest"),
    ("D18d", 18, "migrate.py", [
        ("            or basis[\"source_resolutions_digest\"] != resolutions.digest\n", "")],
     "confirm ignores the resolutions digest"),
    ("D18e", 18, "migrate.py", [
        ("            or basis[\"ledger_digest\"] != ledger_digest(rows) or basis[\"sessions_digest\"] != sessions_digest(sl)):\n",
         "            or basis[\"sessions_digest\"] != sessions_digest(sl)):\n")],
     "confirm ignores the ledger digest"),
    ("D18f", 18, "migrate.py", [
        ("            or basis[\"ledger_digest\"] != ledger_digest(rows) or basis[\"sessions_digest\"] != sessions_digest(sl)):\n",
         "            or basis[\"ledger_digest\"] != ledger_digest(rows)):\n")],
     "confirm ignores the sessions digest"),
    ("D19a", 19, "migrate.py", [("        return copy.deepcopy(self._view)\n", "        return self._view\n")],
     "plan.to_dict shares nested references"),
    ("D19b", 19, "values.py", [("    def events(self):\n        return copy.deepcopy(self._view.get(\"events\")) if",
                                "    def events(self):\n        return self._view.get(\"events\") if")],
     "History.events shares nested references"),
    ("D20a", 20, "restore.py", [
        ("    ACK: (\"request_id\", \"request_hash\", \"request_basis\", \"command_index\", \"command_count\", \"reason_code\",\n          \"requested_at\", \"ledger_digest\", \"origin\", \"record_fingerprints\", \"variant\", \"d\"),\n",
         "    ACK: (\"request_id\", \"request_hash\", \"request_basis\", \"command_index\", \"command_count\", \"reason_code\",\n          \"requested_at\", \"ledger_digest\", \"origin\", \"record_fingerprints\", \"variant\", \"d\", \"state_after\"),\n")],
     "replayed ACK must copy the old state_after"),
    ("D20b", 20, "view.py", [
        ("            self.declare_record(rec)\n        if not same(rec[\"state_after\"], parent_state):\n            raise _bad(\"state_after\")\n",
         "            self.declare_record(rec)\n")],
     "ACK / DECLARE state_after not recomputed on the chain"),
    ("D21a", 21, "restore.py", [("    if migration_seq is not None and point < migration_seq:\n", "    if migration_seq is not None and point <= migration_seq:\n")],
     "restore-point floor too strict: the SCHEMA_MIGRATION itself refused"),
    ("D21b", 21, "restore.py", [("    if migration_seq is not None and point < migration_seq:\n", "    if migration_seq is not None and point < migration_seq - 1:\n")],
     "restore-point floor too loose: the last migrated record allowed"),
    ("D21c", 21, "restore.py", [("    if migration_seq is not None and point < migration_seq:\n", "    if False:\n")],
     "no restore-point floor for migrated history"),
    ("D21d", 21, "restore.py", [("    if migration_seq is not None and point < migration_seq:\n",
                                 "    if (migration_seq is not None and point < migration_seq) or (migration_seq is None and point == 0):\n")],
     "GENESIS refused as a restore point of a new history"),
    ("D22", 22, "migrate.py", [
        ("    validate_snapshot(snapshot_v1)                                                   # 2 the inputs themselves\n"
         "    validate_resolutions(snapshot_v1, resolutions)\n",
         "    try:\n        validate_snapshot(snapshot_v1)\n        validate_resolutions(snapshot_v1, resolutions)\n"
         "    except Exception:\n        raise migration_plan_stale() from None\n")],
     "invalid input at confirm turned into migration_plan_stale"),
]


def main():
    only = set(sys.argv[1:])
    detected, lost, equivalent, not_run = [], [], [], []
    for mid, group, fname, pairs, what in MUTATIONS:
        if only and mid not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="v2s3b1_mut_")
        try:
            for d in ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "tests/v2_history", "tests/v2_recovery",
                      "tests/v2_persistence"):
                shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = os.path.join(tmp, "v2_history", fname)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            bad = [i for i, (old, _new) in enumerate(pairs) if text.count(old) != 1]
            if bad:
                print(mid, "NOT RUN (patch does not apply once):", bad, "-", what)
                not_run.append(mid)
                continue
            for old, new in pairs:
                text = text.replace(old, new)
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history",
                                "-p", "test_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
            if r.returncode != 0:
                tail = r.stdout.decode("utf-8", "replace").strip().splitlines()[-1]
                print(mid, "DETECTED", "(group %d)" % group, "-", what, "|", tail)
                detected.append(mid)
            else:
                print(mid, "NOT DETECTED", "(group %d)" % group, "-", what)
                (equivalent if "EQUIVALENT" in what else lost).append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("detected:", len(detected), detected)
    print("equivalent (not counted as detected):", equivalent or "none")
    print("not run:", not_run or "none")
    print("undetected:", lost or "none")
    return 1 if (lost or not_run) else 0


if __name__ == "__main__":
    sys.exit(main())
