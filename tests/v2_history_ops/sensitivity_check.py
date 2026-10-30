"""Defect injection for the S3-B-2 tests: copy the working tree to a temporary directory, apply ONE defect to the copy
(of v2_history_ops, or of the two allowed v2_recovery files), run the v2_history_ops suite there and require it to fail.
Not part of the product, not a unittest (run it by hand: <python> -B tests/v2_history_ops/sensitivity_check.py [ids]).
The real tree is never modified.

The 22 defects of the request (section 6) are the numbered items; an item with several ways to break it has variants
a / b. Mutants marked EQUIVALENT are listed with the reason that no test can tell them apart; they are not counted as
undetected defects. (After the review R-03 no mutant of this list is marked EQUIVALENT: B03x was wrongly marked.)
The existing S3-A mutants of commands.py are re-run by tests/v2_recovery/sensitivity_check.py (result in the S3-B-2
result record); this script covers the new feature.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
COPIED = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "tests/v2_history_ops",
          "tests/v2_history", "tests/v2_recovery", "tests/v2_persistence")

# (id, path, old, new, what is broken)   old must occur exactly once in the file
MUTATIONS = [
    ("B01", "v2_history_ops/chain.py",
     '        self.resolutions = [rec for rec in self.recs if rec["kind"] in (ACK, DECLARE_MISSING)]',
     '        self.resolutions = [rec for rec in self.events if rec["kind"] in (ACK, DECLARE_MISSING)]',
     "1 resolutions read from the physical array (retired ACKs and declarations are used)"),
    ("B02", "v2_history_ops/chain.py",
     "        for seg, validated in zip(self.segments, self.projected):",
     "        for seg, validated in zip(self.segments[-1:], self.projected[-1:]):",
     "2 facts hold the current segment only"),
    ("B03", "v2_history_ops/chain.py",
     '        self.resolutions = [rec for rec in self.recs if rec["kind"] in (ACK, DECLARE_MISSING)]',
     '        effective = set(check.effective_seqs)\n'
     '        self.resolutions = [rec for rec in self.events if (rec["kind"] == ACK and rec["seq"] in effective) or\n'
     '                            (rec["kind"] == DECLARE_MISSING and rec["replay_of"] is None)]',
     "3 the retired declaration is in, the replayed one dropped (as a resolution in effect)"),
    ("B03x", "v2_history_ops/chain.py",
     '                    for r in self.resolutions if r["kind"] == DECLARE_MISSING]',
     '                    for r in self.events if r["kind"] == DECLARE_MISSING and r["replay_of"] is None]',
     "3 same, but only in FixedFacts.declares (the DROPped trailing declaration is compared with the sessions; "
     "review R-03: NOT equivalent, detected by test_s3b2_review_fix.R03RetiredTrailingDeclaration)"),
    ("B04", "v2_history_ops/chain.py",
     '                ci = rec["confirmed_inputs"]\n'
     '                applies.append({"seq": rec["seq"], "event_hash": rec["event_hash"], "d": rec["d"],',
     '                ci = rec["confirmed_inputs"]\n'
     '                applies.append({"seq": len(applies) + 1, "event_hash": rec["event_hash"], "d": rec["d"],',
     "4 a temporary S1 seq (position in the projection) is used as the reference"),
    ("B05", "v2_recovery/facts.py",
     "        for b in self.facts.boundaries:",
     "        for b in []:",
     "5 boundary sessions are not compared"),
    ("B06", "v2_recovery/facts.py",
     "        if not d > facts.boundary_day:",
     "        if False:",
     "6 from_facts accepts check_d at or before the boundary"),
    ("B07", "v2_recovery/facts.py",
     "        return max([self._boundary_day] + [ap.d for ap in self._applies if ap.seq <= upto_seq])",
     "        return max([ap.d for ap in self._applies if ap.seq <= upto_seq] or [self._boundary_day])",
     "7 latest_apply_day ignores the current boundary"),
    ("B08", "v2_recovery/commands.py",
     '        if not any(rec["kind"] == KIND_DECLARE and rec["seq"] == ref["seq"]\n'
     '                   and rec["event_hash"] == ref["event_hash"] and rec["d"] == d for rec in existing):',
     '        if not any(rec["kind"] == KIND_DECLARE and rec["seq"] == ref["seq"]\n'
     '                   and rec["d"] == d for rec in existing):',
     "8 the v2 LATE reference does not compare the event hash"),
    ("B09", "v2_history_ops/daily.py",
     "    record = _apply_record(res.plan.event, check.head_seq, check.head_hash)        # 6",
     '    last = [r for r in chain.recs if r["kind"] in ("APPLY", "GENESIS", "RESTART_UNKNOWN")][-1]\n'
     '    record = _apply_record(res.plan.event, last["seq"], last["event_hash"])',
     "9 the day record's parent is the last APPLY (boundary), not the physical head"),
    ("B10a", "v2_history_ops/batch.py",
     "    validate_history(candidate)                                            # 6",
     "    pass",
     "10 check_append_batch does not run validate_history on the candidate"),
    ("B10b", "v2_history_ops/plan.py",
     "        candidate_check = validate_history(candidate)\n        cand_chain = Chain(candidate, candidate_check)",
     "        candidate_check = validate_history(history)\n        cand_chain = Chain(candidate, validate_history(history))",
     "10 the plan checks the old history in place of the candidate"),
    ("B11", "v2_history_ops/daily.py",
     "    ledger_of(candidate, Chain(candidate, candidate_check), sessions, raw_observations, d)\n",
     "    pass\n",
     "11 the day's candidate is not projected over every segment"),
    ("B12", "v2_history_ops/plan.py",
     '        ledger, _ = ledger_of(candidate, cand_chain, sessions, raw_observations, check_d, field="commands")',
     '        ledger = __import__("v2_history_ops.values", fromlist=["x"]).HistoryLedger._make(\n'
     '            [], [], [], ctx.ledger_digest, ctx.ledger_digest, candidate.digest, check_d)',
     "12 the plan skips the projection of the candidate (design 12.7 case 6)"),
    ("B13", "v2_history_ops/plan.py",
     "        extras = check_commands(ctx, chain.resolutions, norm)                              # 4",
     "        ledger_of(history, chain, sessions, raw_observations, check_d, ctx=ctx)\n"
     "        extras = check_commands(ctx, chain.resolutions, norm)",
     "13 a completed projection of the existing history is required before the evidence"),
    ("B14", "v2_history_ops/plan.py",
     '    status = READY if request_status(chain.request_groups(), request_id, rhash) == "NEW" else NO_CHANGE   # 3',
     '    status = READY if request_status([g for g in chain.request_groups() if g["effective"]], request_id,\n'
     '                                     rhash) == "NEW" else NO_CHANGE',
     "14 the request id is checked against the effective chain only"),
    ("B15", "v2_history_ops/plan.py",
     '    if not live or any(g["source"] == MIGRATED for g in live):',
     "    if not live:",
     "15 a migrated request with the same hash becomes NO_CHANGE"),
    ("B16a", "v2_history_ops/plan.py",
     '    if (not isinstance(basis, dict) or view["plan_hash"] != sha256_text(canonical_json(basis))\n'
     '            or confirmed_plan_hash != view["plan_hash"] or set(basis) != _BASIS_KEYS):',
     "    if (not isinstance(basis, dict) or set(basis) != _BASIS_KEYS):",
     "16 confirmation ignores plan_hash"),
    ("B16b", "v2_history_ops/plan.py",
     '    same_inputs = (ledger_digest(rows) == basis["ledger_digest"] and sessions_digest(sl) == basis["sessions_digest"])',
     '    same_inputs = (sessions_digest(sl) == basis["sessions_digest"])',
     "16 confirmation ignores the ledger digest"),
    ("B16c", "v2_history_ops/plan.py",
     "    if not same(rebuilt, expected):\n        raise history_plan_mismatch()",
     "    pass",
     "16 confirmation does not compare the rebuilt basis"),
    ("B17", "v2_history_ops/plan.py",
     "    check = validate_history(history)                                                      # 2",
     "    try:\n        check = validate_history(history)\n    except PersistenceError:\n        raise history_plan_stale() from None",
     "17 an invalid history is reported as stale"),
    ("B18", "v2_history_ops/plan.py",
     '    already = (basis["status"] == READY and candidate_head is not None and history.digest == basis["candidate_digest"]',
     '    already = (False and candidate_head is not None and history.digest == basis["candidate_digest"]',
     "18 the same plan confirmed against its own candidate becomes stale"),
    ("B19", "v2_history_ops/batch.py",
     '    if (check.history_digest != body["expected_history_digest"] or check.head_seq != body["expected_head_seq"]\n'
     '            or check.head_hash != body["expected_head_hash"]):             # 3 includes a history that already',
     "    if False:                                                              # 3 includes a history that already",
     "19 check_append_batch does not compare the head"),
    ("B20", "v2_history_ops/batch.py",
     '    if (candidate.digest != body["candidate_digest"] or candidate.head_seq != body["candidate_head_seq"]\n'
     '            or candidate.head_hash != body["candidate_head_hash"]):',
     "    if False:",
     "20 check_append_batch does not compare the candidate digest and head"),
    ("B21a", "v2_history_ops/values.py",
     "        return copy.deepcopy(self._view[key])",
     "        return self._view[key]",
     "21 the effective view shares nested references"),
    ("B21b", "v2_history_ops/plan.py",
     '        return copy.deepcopy(self._view["basis"])',
     '        return self._view["basis"]',
     "21 the plan basis shares nested references"),
    ("B22", "v2_recovery/commands.py",
     '    orig_refs |= {_key(c["applied_ref"]) for c in commands\n'
     '                  if c["kind"] == KIND_ACK and c["variant"] in (V_CHANGED, V_ROW_REMOVED)\n'
     '                  and c["applied_ref"] is not None}',
     "    pass",
     "22 the ADDED original-row check looks at the previous records only, not at this request's other commands"),
]


def main():
    only = set(sys.argv[1:])
    lost, equivalent, detected_n = [], [], 0
    for mid, rel, old, new, what in MUTATIONS:
        if only and mid not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="v2s3b2_mut_")
        try:
            for d in COPIED:
                shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d),
                                ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = os.path.join(tmp, rel)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            if text.count(old) != 1:
                print(mid, "SETUP-ERROR: pattern count", text.count(old))
                lost.append(mid)
                continue
            with open(target, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_ops",
                                "-p", "test_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=900)
            detected = r.returncode != 0
            print(mid, "DETECTED" if detected else "NOT DETECTED", "-", what)
            if detected:
                detected_n += 1
            else:
                (equivalent if "EQUIVALENT" in what else lost).append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("detected:", detected_n)
    print("equivalent (not counted):", equivalent or "none")
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
