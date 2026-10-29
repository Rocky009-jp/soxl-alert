"""Defect injection for the S3-A tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
v2_recovery, run the new test suite there and require it to fail. Not part of the product, not a unittest (run it by
hand: <python> -B tests/v2_recovery/sensitivity_check.py [ids]). The real tree is never modified.

Mutants marked EQUIVALENT are listed with the reason they cannot be told apart by any test; they are not counted as
undetected defects.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# (id, file, old, new, what is broken)   old/new may be tuples (all patterns replaced, each must occur once)
MUTATIONS = [
    ("M01", "ledger.py", "    return [parse_row(r) for r in raw_observations]\n",
     "    out = []\n    for r in raw_observations:\n        try:\n            out.append(parse_row(r))\n"
     "        except Exception:\n            pass\n    return out\n",
     "bad rows dropped instead of stopping (exclusion before parsing)"),
    ("M02", "project.py", "            if ref[\"fingerprint\"] not in remaining:\n                remaining[ref[\"fingerprint\"]] = stored_row(ctx, ref)\n                supplemented.append(copy.deepcopy(ref))",
     "            if ref[\"fingerprint\"] not in ctx.all_by_fp:\n                remaining[ref[\"fingerprint\"]] = stored_row(ctx, ref)\n                supplemented.append(copy.deepcopy(ref))",
     "EQUIVALENT: supplement judged on the raw ledger before exclusion (a fixed row is never excluded, so raw and remaining agree)"),
    ("M03", "project.py", "            if ref[\"fingerprint\"] not in remaining:\n                remaining[ref[\"fingerprint\"]] = stored_row(ctx, ref)\n                supplemented.append(copy.deepcopy(ref))",
     "            pass", "no supplement at all"),
    ("M04", "project.py", "            if ref[\"fingerprint\"] not in remaining:\n                remaining[ref[\"fingerprint\"]] = stored_row(ctx, ref)",
     "            if True:\n                remaining[ref[\"fingerprint\"]] = stored_row(ctx, ref)", "unconditional supplement"),
    ("M05", "project.py", "    actually = {fp for fp in ctx.all_by_fp if fp in excl}\n    remaining = {fp: r for fp, r in ctx.all_by_fp.items() if fp not in excl}",
     "    ids = {ctx.all_by_fp[fp].obs.record_id for fp in excl if fp in ctx.all_by_fp}\n"
     "    actually = {fp for fp, r in ctx.all_by_fp.items() if fp in excl or r.obs.record_id in ids}\n"
     "    remaining = {fp: r for fp, r in ctx.all_by_fp.items() if fp not in actually}",
     "exclusion by record_id instead of fingerprint"),
    ("M06", "commands.py", "    if cmd[\"applied_ref\"] is not None:\n        raise _fail(\"ack_evidence\")\n    ref = cmd[\"missing_ref\"]",
     "    if cmd[\"applied_ref\"] is None:\n        raise _fail(\"ack_evidence\")\n    ref = cmd[\"missing_ref\"]", "LATE requires an applied_ref"),
    ("M07", "project.py", "        if rec[\"kind\"] == KIND_ACK and rec[\"variant\"] in (V_CHANGED, V_ROW_REMOVED):",
     "        if rec[\"kind\"] == KIND_ACK and rec[\"variant\"] in (V_CHANGED, V_ROW_REMOVED, \"LATE\"):", "LATE supplements"),
    ("M08a", "commands.py", "        if any(fp in sv.fixed_fps for fp in cmd[\"record_fingerprints\"]):\n            raise _fail(\"exclude_applied\")",
     "        pass", "a new command may exclude a fixed row"),
    ("M08b", "validate.py", "        if any(fp in sv.fixed_fps for fp in fps):\n            raise _bad(\"exclude_applied\")",
     "        pass", "a stored record may exclude a fixed row"),
    ("M09a", "plan.py", "    if (not isinstance(basis, dict) or view[\"plan_hash\"] != sha256_text(canonical_json(basis))\n            or confirmed_plan_hash != view[\"plan_hash\"] or set(basis) != _BASIS_KEYS):",
     "    if (not isinstance(basis, dict) or set(basis) != _BASIS_KEYS):", "plan_hash not checked when confirming"),
    ("M09b", "plan.py", "    if (basis[\"snapshot_digest\"] != sha256_text(encode_snapshot(snapshot)) or basis[\"expected_head_seq\"] != ctx.sv.head_seq\n            or basis[\"expected_head_hash\"] != ctx.sv.head_hash or basis[\"ledger_digest\"] != ctx.ledger_digest\n            or basis[\"sessions_digest\"] != ctx.sessions_digest):",
     "    if (basis[\"expected_head_seq\"] != ctx.sv.head_seq\n            or basis[\"expected_head_hash\"] != ctx.sv.head_hash or basis[\"ledger_digest\"] != ctx.ledger_digest\n            or basis[\"sessions_digest\"] != ctx.sessions_digest):",
     "snapshot digest not compared"),
    ("M09c", "plan.py", "basis[\"expected_head_hash\"] != ctx.sv.head_hash or basis[\"ledger_digest\"] != ctx.ledger_digest\n            or basis[\"sessions_digest\"] != ctx.sessions_digest):",
     "basis[\"expected_head_hash\"] != ctx.sv.head_hash\n            or basis[\"sessions_digest\"] != ctx.sessions_digest):", "ledger digest not compared"),
    ("M09d", "plan.py", "basis[\"expected_head_hash\"] != ctx.sv.head_hash or basis[\"ledger_digest\"] != ctx.ledger_digest\n            or basis[\"sessions_digest\"] != ctx.sessions_digest):",
     "basis[\"expected_head_hash\"] != ctx.sv.head_hash or basis[\"ledger_digest\"] != ctx.ledger_digest):", "sessions digest not compared"),
    ("M09e", "plan.py", "    if current == basis[\"resolutions_before_digest\"]:\n        expected = basis",
     "    if True:\n        expected = basis", "resolution set digest not compared"),
    ("M09f", "plan.py", "    if not same(rebuilt, expected):\n        raise plan_mismatch()", "    pass", "rebuilt candidate not compared"),
    ("M10a", "values.py", "        recs = self._view.get(\"records\") if isinstance(self._view, dict) else None\n        return copy.deepcopy(recs)",
     "        recs = self._view.get(\"records\") if isinstance(self._view, dict) else None\n        return recs", "records share nested references"),
    ("M10b", "plan.py", "        return copy.deepcopy(self._view[\"basis\"])", "        return self._view[\"basis\"]", "plan basis shares references"),
    ("M10c", "project.py", "    @property\n    def rows(self):\n        return copy.deepcopy(self._view[\"rows\"])",
     "    @property\n    def rows(self):\n        return self._view[\"rows\"]", "effective rows share references"),
    ("M11", "daily.py", "    res = prepare_day(snapshot, d, series, sessions, effective.raw_observations())\n    if res.plan is None:\n        return SimulationDayResult(res.status, res.core_result, None, None)\n    event = res.plan.event\n    return SimulationDayResult(res.status, res.core_result, canonical_json(event), res.plan.event_hash)",
     "    return prepare_day(snapshot, d, series, sessions, effective.raw_observations())", "the S1 PrepareResult / AppendPlan is exposed"),
    ("M12", "commands.py", "    if ap.fingerprint not in ctx.all_by_fp and _key(cmd[\"applied_ref\"]) not in orig_refs:\n        raise _fail(\"ack_evidence\")",
     "    if ap.fingerprint not in ctx.all_by_fp:\n        raise _fail(\"ack_evidence\")", "ADDED evidence from the raw ledger only"),
    ("M13", "project.py", "    for fp, r in remaining.items():\n        if r.obs.record_id in ids and fp not in ctx.sv.fixed_fps:\n            raise resolution_invalid(field, \"version_selection\")",
     "    return", "version_selection check omitted"),
    ("M14", "commands.py", "    if chosen is not None:\n        raise _fail(\"declare_valid_decision\")", "    pass", "a valid single decision may be declared missing"),
    ("M15", "common.py", "    return sha256_text(canonical_json({\"request_id\": request_id, \"commands\": commands, \"check_d\": check_d,\n                                       \"reason_code\": reason_code}))",
     "    return sha256_text(canonical_json({\"request_id\": request_id, \"commands\": commands, \"check_d\": check_d,\n                                       \"reason_code\": reason_code, \"t\": 1}))",
     "request hash input changed consistently (review P-02: pinned by an independent hash expectation in test_r_review_fix)"),
    ("M16", "plan.py", "    rhash = request_hash_of(request_id, norm, ctx.check_d, reason_code)\n    existing",
     "    rhash = request_hash_of(request_id, norm, ctx.check_d, reason_code + requested_at)\n    existing", "requested_at is part of the request hash"),
    ("M17", "commands.py", "    related = [fp for fp, r in rem0.items() if _related(ctx, r, d)]\n    ids = {rem0[fp].obs.record_id for fp in related}\n    scope = [r.cols for r in rem0.values() if r.fp in related or r.obs.record_id in ids]",
     "    related = [fp for fp, r in rem0.items() if _related(ctx, r, d)]\n    scope = [r.cols for r in rem0.values()]", "declaration eligibility judged on the whole ledger"),
    ("M18", "commands.py", "    declared = [r[\"d\"] for r in existing if r[\"kind\"] == KIND_DECLARE]", "    declared = []", "EQUIVALENT: existing declarations ignored for the frontier at creation (validate_set re-checks the candidate with its own frontier and raises the same rule)"),
    ("M19", "commands.py", "            extra = _check_declare(ctx, cmd, declared, rem0)\n            declared.append(cmd[\"d\"])",
     "            extra = _check_declare(ctx, cmd, list(declared), rem0)", "earlier declarations of the same batch ignored for the frontier"),
    ("M20", "project.py", "    select_decision(raw, sl, ctx.check_d)\n\n\nclass EffectiveLedger", "\n\nclass EffectiveLedger", "final selection for check_d omitted"),
    ("M21", "project.py", "        for sessions in (stored, sl):\n            if select_decision(raw, sessions, rec[\"d\"]) is not None:\n                raise PersistenceError(\"late_observation\", \"observations\", detail=rec[\"d\"])",
     "        pass", "a decision on a declared day is not noticed"),
    ("M22", "project.py", "    if project_context(current) != project_context(context):", "    if current != context:", "no next(D) projection when comparing sessions"),
    ("M23", "daily.py", "    @property\n    def committed(self):\n        return False", "    @property\n    def committed(self):\n        return True", "day result reports committed"),
    ("M24", "plan.py", "        eff = resolve_core(ctx, ctx.records, cand.digest, \"resolutions\")      # the current projection is still checked",
     "        eff = None", "NO_CHANGE skips the current projection check"),
    ("M25", "daily.py", "    res = prepare_day(snapshot, d, series, sessions, effective.raw_observations())", "    res = prepare_day(snapshot, d, series, sessions, raw_observations)",
     "S1 is given the raw ledger instead of the final one"),
    ("M26", "validate.py", "        if not same(first[\"state_after\"], sv.events[src][\"state_after\"]):\n            raise _bad(\"state_after\")", "        pass", "creation state not compared"),
    ("M27", "validate.py", "        if first[\"source_head_hash\"] != sv.events[src][\"event_hash\"]:\n            raise _bad(\"source_head\")", "        pass", "source head hash not compared"),
    ("M28", "validate.py", "        if not is_int(count) or count < 1 or first[\"command_index\"] != 0 or i + count > n:\n            raise _bad(\"batch\")",
     "        count = 1", "request batches not required to be complete"),
    ("M29", "commands.py", "        if r.obs.record_id == ap.record_id or not _related(ctx, r, cmd[\"d\"]):", "        if not _related(ctx, r, cmd[\"d\"]):",
     "ADDED may name a row with the stored record_id"),
    ("M30", "commands.py", "    for r in ctx.rows:\n        if r.obs.record_id == ap.record_id and r.fp not in union_excl:\n            raise _fail(\"ack_evidence\")             # an unacknowledged changed version of the same row",
     "    pass", "ROW_REMOVED accepted with an unacknowledged changed version"),
    ("M31", "commands.py", "    if cmd[\"record_fingerprints\"] or ap.fingerprint in ctx.all_by_fp:\n        raise _fail(\"ack_evidence\")",
     "    if cmd[\"record_fingerprints\"]:\n        raise _fail(\"ack_evidence\")", "EQUIVALENT: ROW_REMOVED accepted while the original row is present (subsumed by the unacknowledged same-id version check)"),
    ("M32", "commands.py", "        if cmd[\"kind\"] == KIND_ACK and cmd[\"d\"] > ctx.check_d:\n            raise _fail(\"ack_evidence\")", "        pass", "new ACK may target a day after check_d"),
    ("M33", "commands.py", "    if sorted(related) != cmd[\"record_fingerprints\"]:\n        raise _fail(\"declare_incomplete\")", "    pass", "declaration need not name every row"),
    ("M34", "commands.py", "    if not ds.confirmed or not fs.confirmed or nd is None:\n        raise _fail(\"declare_unconfirmed\")", "    pass", "unconfirmed day may be declared"),
    ("M35", "commands.py", "    if ds is None or ds.date != d:\n        raise _fail(\"declare_frontier\")", "    if ds is None:\n        raise _fail(\"declare_frontier\")", "declaration not required to be the next session"),
    ("M36", "validate.py", "        if d in sv.apply_days:\n            raise _bad(\"declare_applied\")", "        pass", "an APPLY on a declared day is accepted"),
    ("M37", "validate.py", "        elif prefix is None:\n            expected = sv.boundary\n        else:\n            expected = prefix.context[-2]\n        if not same(ctx[0], expected):\n            raise _bad(\"session_context\")",
     "        else:\n            expected = ctx[0]", "declared context continuity not checked"),
    ("M38", "commands.py", "        if not any(rec[\"kind\"] == KIND_DECLARE and rec[\"resolution_seq\"] == ref[\"resolution_seq\"]\n                   and rec[\"resolution_hash\"] == ref[\"resolution_hash\"] and rec[\"d\"] == d for rec in existing):\n            raise _fail(\"late_missing_ref\")",
     "        pass", "LATE accepted with any declaration reference"),
    ("M39", "commands.py", "        if ap is None or ref[\"event_hash\"] != ap.event_hash or d not in ap.skipped:\n            raise _fail(\"late_missing_ref\")",
     "        if ap is None:\n            raise _fail(\"late_missing_ref\")", "LATE accepted for a day the APPLY did not skip"),
    ("M40", "project.py", "        for sd in ap.skipped:\n            if select_decision(raw, sl, sd) is not None:\n                raise PersistenceError(\"late_observation\", \"observations\", detail=sd)",
     "        pass", "late rows for skipped sessions not noticed"),
    ("M41", "plan.py", "    except CoreError:\n        raise plan_mismatch() from None                    # every input digest matched, so the plan itself is wrong",
     "    except CoreError:\n        raise", "rebuild errors of a forged plan not mapped to plan_mismatch"),
    ("M42", "common.py", "    if not isinstance(cmd, dict) or set(cmd) != COMMAND_KEYS:\n        raise bad()", "    if not isinstance(cmd, dict):\n        raise bad()",
     "command key set not checked"),
    ("M43", "validate.py", "        if not is_date(check_d) or not check_d > sv.start_after or not check_d >= prefix_day:\n            raise _bad(\"check_d\")",
     "        pass", "stored check_d not checked against its own prefix"),
    ("M44", "validate.py", "        if not is_date(rec[\"d\"]) or rec[\"d\"] > check_d:\n            raise _bad(\"check_d\")", "        pass", "stored record day may exceed its check_d"),
    ("M45", "project.py", "    final = sorted((r.cols for r in remaining.values()), key=canonical_json)", "    final = [r.cols for r in remaining.values()][::-1]",
     "final rows in a different order (the order is pinned by the delegation test)"),
    ('M46', 'plan.py',
     'if (b["status"] not in (READY, NO_CHANGE) or not valid_request_id(b["request_id"])\n                    or not is_date(b["check_d"])',
     'if (not valid_request_id(b["request_id"])\n                    or not is_date(b["check_d"])', 'R-01: status shown without a check'),
    ('M47', 'plan.py',
     'if (b["status"] not in (READY, NO_CHANGE) or not valid_request_id(b["request_id"])',
     'if (b["status"] not in (READY, NO_CHANGE)', 'R-01: request_id shown without a check'),
    ('M48', 'plan.py',
     'or not is_date(c["d"]) or not isinstance(c["record_fingerprints"], list)):',
     'or not isinstance(c["record_fingerprints"], list)):', 'R-01: command day shown without a check'),
    ('M49', 'plan.py',
     'or not is_date(b["check_d"]) or not is_hex64(h)',
     'or not is_hex64(h)', 'R-01: check_d shown without a check'),
    ('M50', 'plan.py',
     '        shown = self._display()\n        if shown is None:\n            raise resolution_invalid("plan", "plan_shape")',
     '        shown = self._display()', 'R-01: summary of an unchecked plan is not refused'),
    ('M51', 'plan.py',
     '        check_json(data, "plan")                       # depth and types first: only then is copying the input safe\n',
     '', 'R-02: input copied before the depth check'),
    ('M52', 'plan.py',
     '        except RecursionError:\n            raise resolution_invalid("plan", "json_depth") from None\n',
     '', 'EQUIVALENT: R-02 recursion handler of the conversion (unreachable after the depth check; kept as a defensive mapping)'),
    ('M53', 'plan.py',
     '        except (ValueError, OverflowError):                     # e.g. an integer too long to be written as text\n            raise resolution_invalid("plan", "json_number") from None\n',
     '', 'R-02: integer too long for text not mapped'),
    ('M54', 'plan.py',
     'raise resolution_invalid("plan", "json_number") from None',
     'raise resolution_invalid("plan", "json_number")', 'R-02: exception chain not suppressed'),
    ('M55', 'common.py',
     '        dt = parse_aware_datetime(text, "requested_at")\n        return utc_text(dt, "requested_at") == text\n    except InputError:\n        return False\n',
     '        dt = parse_aware_datetime(text, "requested_at")\n    except InputError:\n        return False\n    return utc_text(dt, "requested_at") == text\n', "P-01: UTC conversion of requested_at outside the predicate's try"),
]


def main():
    only = set(sys.argv[1:])
    lost, equivalent = [], []
    for mid, fname, old, new, what in MUTATIONS:
        if only and mid not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="v2s3a_mut_")
        try:
            for d in ("v2_core", "v2_persistence", "v2_recovery", "tests/v2_recovery", "tests/v2_persistence"):
                src = os.path.join(ROOT, d)
                shutil.copytree(src, os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = os.path.join(tmp, "v2_recovery", fname)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            if text.count(old) != 1:
                print(mid, "SETUP-ERROR: pattern count", text.count(old))
                lost.append(mid)
                continue
            with open(target, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_recovery",
                                "-p", "test_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            detected = r.returncode != 0
            tag = "DETECTED" if detected else "NOT DETECTED"
            print(mid, tag, "-", what)
            if not detected:
                (equivalent if "EQUIVALENT" in what else lost).append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("equivalent (not counted):", equivalent or "none")
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
