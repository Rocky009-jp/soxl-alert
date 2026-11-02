"""Defect injection for the S3-B-4 tests: copy the working tree to a temporary directory, apply ONE defect to the copy of
v2_history_restore, run the v2_history_restore suite there and require it to fail. Not part of the product, not a unittest
(run it by hand: <python> -B tests/v2_history_restore/r4_sensitivity.py [--control] [--jobs N] [ids]). The real tree is
never modified.

Review fixes (R-01/R-02, 5eede11 -> fix branch): the mutations F01a..F02h take each fix out again on its own. The four
mutations M09c, M12b, M16d and M17c were called EQUIVALENT in the 47eb7c5 run; the review (R-03) found a counterexample for
each, and they are separated by tests/v2_history_restore/test_r4_10_review_fixes.py. Their ids are kept.

The 22 items of the request (section 6) are the numbered mutations M01..M22; an item with several ways to break it has
variants a / b / c. For every mutant the output says whether it is DETECTED (and by which tests), EQUIVALENT (the defect
cannot change any answer; the reason is in `what`), NOT DETECTED (no test tells it apart) or SETUP-ERROR (a pattern of the
mutation does not occur exactly once: the mutant was not made). Where the request asks to classify the layer that answers
(the package's own pre-refusal, the independent guard of an unchanged function, or a delegation / order spy), the probe
prints what the mutated runtime says for one request. A mutant is never silently called equivalent: only the entries
whose text starts with EQUIVALENT are counted so.
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
          "v2_history_restore", "tests/v2_history_restore", "tests/v2_history_ops", "tests/v2_history",
          "tests/v2_recovery", "tests/v2_persistence")
PK = "v2_history_restore/"
BUILD, CONFIRM, VALUES, POINTS = PK + "build.py", PK + "confirm.py", PK + "values.py", PK + "points.py"
RECORDS, CHAIN, MARKET = PK + "records.py", PK + "chain.py", PK + "market.py"

HEAD = '''
import sys
sys.path.insert(0, "tests/v2_history_restore")
import r4_helpers as R
T, H, Z, D, P = R.T, R.H, R.Z, R.D, R.P
def show(label, fn, *a, **k):
    o = T.outcome(fn, *a, **k)
    print("   probe", label, "->", o[:4] if o[0] == "err" else "accepted")
'''
PROBE_POINT = HEAD + '''
b = R.ex_restart_between()
show("superseded point", R.prep, b, 2, {3: "REAPPLY"}, D[3], "r4-1")
show("head point", R.prep, b, 3, {}, D[3], "r4-1", ops=[])
show("hash mismatch", R.prep, b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "r4-1", pt={"seq": 1, "event_hash": "0" * 64})
c = R.ex_migrated_tail()
show("before migration", R.prep, c, 6, {"*": "REAPPLY"}, D[8], "r4-1", ops=[])
e = R.ex_two_command_request()
show("inside a request", R.prep, e, 3, {4: "REPLAY", 5: "DROP"}, D[5], "r4-1")
'''
PROBE_OPS = HEAD + '''
b = R.ex_restart_between()
show("auto-sorted ops", R.prep, b, 1, None, D[3], "r4-1", ops=[{"op": "REAPPLY", "from_seq": 3}, {"op": "DROP", "from_seq": 2}])
show("float seq", R.prep, b, 1, None, D[3], "r4-1", ops=[{"op": "DROP", "from_seq": 2.0}, {"op": "REAPPLY", "from_seq": 3}])
show("APPLY dropped", R.prep, b, 1, None, D[3], "r4-1", ops=[{"op": "DROP", "from_seq": 2}, {"op": "DROP", "from_seq": 3}])
e = R.ex_two_command_request()
show("partial request", R.prep, e, 2, {3: "REPLAY", 4: "DROP", 5: "DROP"}, D[5], "r4-1")
'''
PROBE_BATCH = HEAD + '''
b = R.ex_inside_old_batch()
show("point inside an old batch", R.prep, b, 8, {9: "REPLAY", 10: "REAPPLY", 11: "REAPPLY", 12: "DROP", 13: "REAPPLY"}, D[8], "r4-1")
'''
PROBE_SOURCE = HEAD + '''
b = R.ex_declare_tail()
s = R.sessions_with({D[3]: R.later_open})
show("source projection fails, declaration dropped", R.prep, b, 1, {2: "DROP"}, D[5], "r4-1", sessions=s)
'''
PROBE_CONSUME = HEAD + '''
b = R.ex_restart_over_gap()
led = b.w.ledger + [P.obs("X2", D[2], 45.0)]
show("passed-over day with a decision", R.prep, b, 1, {2: "DROP", 3: "REAPPLY"}, D[5], "r4-1", ledger=led)
c = R.ex_restart_tail()
show("no later apply", R.prep, c, 1, {2: "DROP"}, D[5], "r4-1", ledger=c.w.ledger + [P.obs("X2", D[2], 45.0)])
n = R.ex_null_restart()
show("null base", R.prep, n, 0, {1: "DROP"}, D[5], "r4-1", ledger=n.w.ledger + [P.obs("X2", D[2], 45.0)])
d = R.ex_declare_tail()
show("dropped declaration", R.prep, d, 1, {2: "DROP"}, D[5], "r4-1", ledger=d.w.ledger + [P.obs("X2", D[2], 45.0)])
'''
PROBE_OLDSKIP = HEAD + '''
for builder, seq, mp, day in ((R.ex_old_skip, 1, {2: "REAPPLY", 3: "DROP", 4: "REAPPLY"}, D[2]),
                              (R.ex_old_skip_first, 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, D[1])):
    b = builder()
    show("late row for an old skip, parent seq %d" % seq, R.prep, b, seq, mp, D[5], "r4-1", ledger=b.w.ledger + [P.obs("L", day, 22.0)])
'''
PROBE_EVIDENCE = HEAD + '''
b, late = R.ex_declare_then_late()
show("declaration + late ack", R.prep, b, 1, {2: "REPLAY", 3: "REAPPLY", 4: "REPLAY"}, D[5], "r4-1")
c, ch = R.ex_removed_then_changed()
show("removal + change", R.prep, c, 1, {2: "REPLAY", 3: "REPLAY"}, D[5], "r4-1")
'''
PROBE_CANDIDATE = HEAD + '''
b = R.ex_ack_between()
plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}, D[5], "r4-1")
def cut(events, n):
    del events[-1]
show("a candidate that stops in the middle of its batch", R.confirm, R.forge(plan, cut), b.history(), b.w)
'''
PROBE_NOEFFECT = HEAD + '''
b = R.ex_restart_over_gap()
show("nothing dropped, nothing changed", R.prep, b, 0, {1: "REAPPLY", 2: "REPLAY", 3: "REAPPLY"}, D[5], "r4-1")
n = R.ex_null_restart()
show("dropping a restart of the same state", R.prep, n, 0, {1: "DROP"}, D[5], "r4-1")
'''
PROBE_ID = HEAD + '''
b = R.ex_after_three_restores()
show("id of a superseded record", R.prep, b, 24, {25: "REAPPLY"}, D[8], "q1")
'''
PROBE_CONFIRM = HEAD + '''
b = R.ex_ack_between()
mp = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}
plan = R.prep(b, 1, mp, D[5], "r4-1")
h, w = b.history(), b.w
show("wrong confirmed hash", R.confirm, plan, h, w, plan_hash="0" * 64)
show("ledger changed", R.confirm, plan, h, w, ledger=w.ledger + [P.obs("N1", D[8], 30.0)])
res = R.confirm(plan, h, w)
show("reconfirm against the candidate", R.confirm, plan, res.history, w)
'''
PROBE_INVALID = HEAD + '''
b = R.ex_restart_between()
plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "r4-1")
broken = H.mutated(b.events, lambda ev: ev[2].__setitem__("resume_after", D[9]))
show("invalid history", R.confirm, plan, broken, b.w)
'''
PROBE_SHARE = HEAD + '''
b = R.ex_restart_between(); plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "r4-1")
plan.basis["ops"][0]["op"] = "X"
print("   probe nested change visible in the plan ->", plan.basis["ops"][0]["op"] == "X")
'''

# (id, [(path, old, new), ...], what is broken, probe or None)   every old must occur exactly once in its file
MUTATIONS = [
    ("M01a", [(POINTS, "    if seq not in effective:", "    if seq not in range(len(events)):"),
              (POINTS, "    pos = effective.index(seq)", "    pos = max(i for i, s in enumerate(effective) if s <= seq)")],
     "1 a superseded record is accepted as the restore point", PROBE_POINT),
    ("M01b", [(POINTS, "    if seq == check.head_seq:", "    if False:")],
     "1 the physical head is accepted as the restore point", PROBE_POINT),
    ("M01c", [(POINTS, "    if migration is not None and seq < migration:", "    if False:")],
     "1 a record before the migration is accepted as the restore point", PROBE_POINT),
    ("M01d", [(POINTS, '    if rec["kind"] in (ACK, DECLARE_MISSING) and rec["command_index"] < rec["command_count"] - 1:',
               "    if False:")],
     "1 a record in the middle of a request is accepted as the restore point", PROBE_POINT),
    ("M01e", [(POINTS, '    if point["event_hash"] != events[seq]["event_hash"]:', "    if False:")],
     "1 a hash that is not the record's is accepted for the restore point", PROBE_POINT),
    ("M02a", [(POINTS, "    return pos, effective[pos + 1:]", "    return pos, list(range(seq + 1, len(events)))")],
     "2 the superseded records are the physical interval after the point (not the effective suffix)", None),
    ("M02b", [(POINTS, "    return pos, effective[pos + 1:]", "    return pos, effective[pos + 1:][::-1]")],
     "2 the superseded records come in another order", None),
    ("M03a", [(POINTS, '        if set(entry) != OP_KEYS or not is_int(entry["from_seq"]):',
               '        if set(entry) != OP_KEYS or not isinstance(entry["from_seq"], (int, float)):')],
     "3 from_seq may be a float or a bool (no strict integer)", PROBE_OPS),
    ("M03b", [(POINTS, '    if [e["from_seq"] for e in norm] != list(superseded):',
               '    norm.sort(key=lambda e: e["from_seq"])\n    if [e["from_seq"] for e in norm] != list(superseded):')],
     "3 the operations are sorted for the caller (an order that is not the superseded order is accepted)", PROBE_OPS),
    ("M03c", [(POINTS, '        if entry["op"] not in _ALLOWED.get(kind, ()):', "        if False:")],
     "3 the operation need not fit the kind of the record", PROBE_OPS),
    ("M03d", [(POINTS, "    if any(len(chosen) > 1 for chosen in by_request.values()):", "    if False:")],
     "3 one request may be partly replayed and partly dropped", PROBE_OPS),
    ("M04", [(BUILD, "    plan_ops = check_ops(events, superseded, ops)",
              "    validate_history(History.from_dict(history_dict(events[:restore_point[\"seq\"] + 1])))\n"
              "    plan_ops = check_ops(events, superseded, ops)")],
     "4 the physical prefix cut at the point is validated (a point inside an old restore batch is refused)", PROBE_BATCH),
    ("M05", [(BUILD, "    items, cuts = series_inputs(series, sl, olds) if olds else ([], {})",
              "    items, cuts = series_inputs(series, sl, olds) if olds else ([], {})\n"
              "    events = copy.deepcopy(events)\n"
              "    for o, it in zip(olds, items):\n"
              "        e = events[o[\"seq\"]][\"confirmed_inputs\"]\n"
              "        e[\"row\"], e[\"prev_row\"] = it[\"row\"], it[\"prev_row\"]")],
     "5 the saved market values are replaced by the current ones before the new records are calculated", None),
    ("M06", [(RECORDS, '"transition_result": serialize_transition(t), "state_after": t.next_state.to_dict()}',
              '"transition_result": copy.deepcopy(old["transition_result"]), "state_after": copy.deepcopy(old["state_after"])}')],
     "6 the state and the transition are copied from the superseded record (apply_transition is not used for them)", None),
    ("M07a", [(BUILD, "    _check_saved_market(items, draft)", "    pass")],
     "7 the current market values are not compared with the saved ones", None),
    ("M07b", [(BUILD, "    _check_saved_decisions(prior, sl, draft)                                               # 7",
               "    pass")],
     "7 the current decision is not compared with the saved one", None),
    ("M08a", [(CHAIN, '        if entry["date"] in last:\n            if other["open_at"] != entry["open_at"]:\n                return False\n        elif not same(other, entry):',
               '        if not same(other, entry):')],
     "8 a harmless close / confirmed difference of next(D) is treated as harmful", None),
    ("M08b", [(CHAIN, '            if other["open_at"] != entry["open_at"]:', "            if False:")],
     "8 a harmful open difference of next(D) is ignored", None),
    ("M09a", [(BUILD, '            days.add(old["d"])', "            pass")],
     "9 the day of a dropped declaration is not a released day", PROBE_CONSUME),
    ("M09b", [(BUILD, '            days.update(s.date for s in sl.sessions if frontiers[seq] < s.date <= old["resume_after"])',
               "            pass")],
     "9 the sessions a dropped restart had passed over are not released days", PROBE_CONSUME),
    ("M09c", [(BUILD, '        days.update(set(new["skipped_sessions"]) - set(old["skipped_sessions"]))', "        pass")],
     "9 the sessions a re-applied day newly skips are not released days (R-03: the 47eb7c5 run called this EQUIVALENT by argument; that was wrong - a day the current calendar adds between the saved previous day and the re-applied day, with a valid decision, is newly skipped and needs a consume; separated by test_r4_10 R03CounterExamples)", PROBE_CONSUME),
    ("M09d", [(BUILD, "            out[seq] = frontier_of(last_segment([events[s] for s in effective[:i]]))[0]",
               "            seg = last_segment([events[s] for s in effective[:i]])\n"
               "            out[seq] = frontier_of(seg)[0] if seg[\"applies\"] else \"9999-99-99\"")],
     "9 a restart that closes a segment without an APPLY (null base) releases nothing", PROBE_CONSUME),
    ("M09e", [(BUILD, "    _check_new_days(prior, sl, _released_days(events, effective, superseded, plan_ops, draft, sl, facts.apply_days))",
               "    if draft.reapplied:\n"
               "        _check_new_days(prior, sl, _released_days(events, effective, superseded, plan_ops, draft, sl, facts.apply_days))")],
     "9 the released days are checked only when a day is applied again (no later APPLY: not checked)", PROBE_CONSUME),
    ("M10", [(BUILD, "    plan_ops = check_ops(events, superseded, ops)",
              "    plan_ops = check_ops(events, superseded, ops)\n"
              "    project_history_ledger(history, sessions, raw_observations, check_d)")],
     "10 the current projection of the original history is required (a restore that removes the cause is refused)", PROBE_SOURCE),
    ("M11a", [(RECORDS, '            target = mapped(applied["seq"])', '            target = applied["seq"]')],
     "11 the reference of a replayed acknowledgement is not mapped to the new record", None),
    ("M11b", [(RECORDS, '        raise restore_invalid("ops", "restore_ref_unmapped")', "        return target")],
     "11 a reference to a dropped or retired record is silently kept", None),
    ("M12a", [(RECORDS, '                "state_after": copy.deepcopy(work[-1]["state_after"])})',
               '                "state_after": copy.deepcopy(old["state_after"])})')],
     "12 a replayed acknowledgement or declaration copies the state from the superseded record", None),
    ("M12b", [(RECORDS, '        new["frontier_before"] = frontier', '        new["frontier_before"] = old["frontier_before"]')],
     "12 a replayed declaration copies its frontier from the superseded record (R-03: the 47eb7c5 run called this EQUIVALENT by argument; that was wrong - when the current calendar has lost the day between, the new frontier differs; separated by test_r4_10 R03CounterExamples)", None),
    ("M12c", [(RECORDS, '"parent_hash": None, "floor": floor,', '"parent_hash": None, "floor": old["floor"],')],
     "12 a replayed restart copies its floor from the superseded record", None),
    ("M13a", [(BUILD, "    _replay_evidence(chain, draft.replayed, sl, raw_observations, check_d)                       # 6",
               "    pass")],
     "13 the evidence of the replayed requests is not checked again", PROBE_EVIDENCE),
    ("M13b", [(BUILD, '            group = chain[j:j + rec["command_count"]]', "            group = chain[j:j + 1]")],
     "13 a request of several commands is cut into single commands", None),
    ("M13c", [(BUILD, "            prefix = chain[:j]\n            ctx = LedgerContext.from_facts(facts_of(prefix, prefix[-1][\"seq\"]), sl, raw_observations, check_d)",
               "            prefix = chain\n            ctx = LedgerContext.from_facts(facts_of(prefix, prefix[-1][\"seq\"]), sl, raw_observations, check_d)")],
     "13 the prefix holds the later APPLY and the later resolutions of the whole candidate", PROBE_EVIDENCE),
    ("M13d", [(BUILD, "            extras = check_commands(ctx, existing, commands)",
               "            try:\n                extras = check_commands(ctx, existing, commands)\n"
               "            except PersistenceError:\n                j += len(group)\n                continue")],
     "13 a refusal of the unchanged check_commands is swallowed (the two known limits pass)", PROBE_EVIDENCE),
    ("M14", [(BUILD, '    check_versions(ctx, remaining, actually, "resolutions")', "    pass")],
     "14 the refusal of a version choice is left out of the prior row set", None),
    ("M15a", [(BUILD, "    cand_check = validate_history(candidate)\n", "    cand_check = check\n")],
     "15 validate_history is not called on the candidate", PROBE_CANDIDATE),
    ("M15b", [(BUILD, "    ledger = project_history_ledger(candidate, sessions, raw_observations, check_d)        # 8",
               "    ledger = type(\"L\", (), {\"rows\": prior, \"effective_digest\": sha256_text(canonical_json(prior)),\n"
               "                             \"ledger_digest\": ledger_text,\n"
               "                             \"raw_observations\": lambda self: copy.deepcopy(prior)})()")],
     "15 the whole-range projection of B-2 is not called (the prior rows stand in for it)", None),
    ("M15c", [(BUILD, "    _check_days_again(chain, ledger, cuts, sl, draft)\n    if not any(",
               "    if not any("),
              (BUILD, "    ledger = project_history_ledger(candidate, sessions, raw_observations, check_d)        # 8",
               "    _check_days_again(chain, type(\"L\", (), {\"raw_observations\": lambda self: copy.deepcopy(prior)})(), cuts, sl, draft)\n"
               "    ledger = project_history_ledger(candidate, sessions, raw_observations, check_d)        # 8")],
     "15 evaluate_day is called before the final B-2 projection (a late row for an old skip changes its code)", PROBE_OLDSKIP),
    ("M15d", [(BUILD, "    _check_days_again(chain, ledger, cuts, sl, draft)\n    if not any(", "    if not any(")],
     "15 evaluate_day is not called at all (the transition is compared with nothing)", None),
    ("M16a", [(BUILD, "    if (len(events) != len(old) + len(new) or canonical_json(events[:len(old)]) != canonical_json(old)\n"
               "            or canonical_json(events[len(old):]) != canonical_json(new)):\n        raise candidate_invalid()",
               "    if False:\n        raise candidate_invalid()")],
     "EQUIVALENT (redundant guard, single mutation of this check with the generator unchanged) the old events and the new records are not compared with the candidate: the candidate is built by joining them, and the unchanged validate_history over the whole candidate (hash chain) is the independent guard that remains. No separating input was found; this is not a proof that none exists (review P-01)", None),
    ("M16b", [(BUILD, "    if (list(cand_check.effective_seqs) != list(kept) + [r[\"seq\"] for r in new]",
               "    if (False")],
     "16 the effective seqs of the candidate are not compared", None),
    ("M16c", [(BUILD, "            or list(cand_check.superseded_seqs) != sorted(list(check.superseded_seqs) + restore[\"superseded_seqs\"])\n",
               "")],
     "16 the superseded seqs of the candidate are not compared", None),
    ("M16d", [(CONFIRM, "                or canonical_json(events[cut:]) != canonical_json(basis[\"candidate_records\"])):",
               "                ):")],
     "16 the candidate_records of a plan are not compared with the tail of its candidate before the inputs are read (R-03: the 47eb7c5 run called this EQUIVALENT by argument; that was wrong - with this check gone a bad plan and bad sessions answer sessions_invalid, not history_plan_mismatch; separated by test_r4_10 R03CounterExamples)", None),
    ("M17a", [(BUILD, "    if not any(e[\"op\"] == DROP for e in plan_ops) and all(e[\"same_as_superseded\"] is not False\n"
               "                                                           for e in draft.entries if e[\"op\"] == REAPPLY):\n        raise no_effect()",
               "    if False:\n        raise no_effect()")],
     "17 the no-effect refusal is left out", PROBE_NOEFFECT),
    ("M17b", [(BUILD, "    if not any(e[\"op\"] == DROP for e in plan_ops) and all(e[\"same_as_superseded\"] is not False",
               "    if all(e[\"same_as_superseded\"] is not False")],
     "17 a plan with a drop is refused too when every re-applied day is the same", PROBE_NOEFFECT),
    ("M17c", [(BUILD, "    if not any(e[\"op\"] == DROP for e in plan_ops) and all(e[\"same_as_superseded\"] is not False\n"
               "                                                           for e in draft.entries if e[\"op\"] == REAPPLY):",
               "    if not any(e[\"op\"] == DROP for e in plan_ops):")],
     "17 the all-same condition is removed and the no-DROP condition stays (R-03: the 47eb7c5 run called this EQUIVALENT "
     "by argument; that was wrong - a plan without a DROP can change a re-applied day when the current calendar added a "
     "day; separated by test_r4_10 R03CounterExamples)", PROBE_NOEFFECT),
    ("M18", [(BUILD, '    if any(g["request_id"] == request_id for g in view.requests):',
              '    if any(g["request_id"] == request_id and g["effective"] for g in view.requests):')],
     "18 the request id is compared against the effective chain only", PROBE_ID),
    ("M19a", [(CONFIRM, "            or confirmed_plan_hash != view[\"plan_hash\"] or not _form_ok(basis)):",
               "            or not _form_ok(basis)):")],
     "19 the confirmed plan hash is not compared with the plan's", PROBE_CONFIRM),
    ("M19b", [(CONFIRM, "set(basis) != BASIS_KEYS or view[\"plan_hash\"] != sha256_text(canonical_json(basis))\n",
               "set(basis) != BASIS_KEYS\n")],
     "19 the plan hash is not recomputed from the basis", PROBE_CONFIRM),
    ("M19c", [(CONFIRM, "    same_inputs = (ledger_digest(rows) == basis[\"ledger_digest\"] and sessions_digest(sl) == basis[\"sessions_digest\"]\n"
               "                   and digest_of(items) == basis[\"series_digest\"])",
               "    same_inputs = True")],
     "19 the ledger, sessions and series digests of the plan are ignored", PROBE_CONFIRM),
    ("M19d", [(MARKET, "            cut = series.through(d)", "            cut = series")],
     "19 the whole series (also the rows after the day) is read, not the cut at the day", None),
    ("M19e", [(MARKET, '                    "series_previous_date": series_previous, "row": row_dict(row),',
               '                    "series_previous_date": series_previous, "row": row_dict(row), "display": cut.soxl_close(d),')],
     "19 a display-only value of the series is mixed into the series input", None),
    ("M20a", [(CONFIRM, "    already = (history.digest == basis[\"candidate_digest\"] and check.head_seq == cand_check.head_seq\n"
               "               and check.head_hash == cand_check.head_hash)                                 #   branch B",
               "    already = False")],
     "20 the same plan against its own candidate is stale", PROBE_CONFIRM),
    ("M20b", [(CONFIRM, "        source = history if is_original else original", "        source = history")],
     "20 the candidate is taken as the original again (a second RECOVERY_RESTORE would be made)", PROBE_CONFIRM),
    ("M20c", [(CONFIRM, "    check = validate_history(original)\n",
               "    check = type(\"C\", (), {\"history_digest\": original.digest, \"head_seq\": original.head_seq,\n"
               "                             \"head_hash\": original.head_hash,\n"
               "                             \"state_digest\": sha256_text(canonical_json(original.current_state))})()\n")],
     "20 branch B does not validate the original prefix of the candidate", PROBE_CONFIRM),
    ("M20d", [(CONFIRM, "    if not same(rebuilt, basis) or rebuilt_candidate != candidate:\n        raise history_plan_mismatch()",
               "    if False:\n        raise history_plan_mismatch()")],
     "20 the whole basis is not rebuilt and compared", PROBE_CONFIRM),
    ("M21a", [(CONFIRM, "    check = validate_history(history)                                                      # 2",
               "    try:\n        check = validate_history(history)\n    except CoreError:\n        raise history_plan_stale() from None")],
     "21 an invalid input history is turned into a stale plan", PROBE_INVALID),
    ("M21b", [(CONFIRM, "    basis, candidate, cand_check, cand_events, original = _plan_basis(plan, confirmed_plan_hash)   # 1",
               "    validate_history(history)\n    parse_ledger(raw_observations)\n"
               "    basis, candidate, cand_check, cand_events, original = _plan_basis(plan, confirmed_plan_hash)   # 1")],
     "21 the current inputs are read before the plan itself is checked", PROBE_INVALID),
    ("M22a", [(VALUES, '        return copy.deepcopy(self._view["basis"])', '        return self._view["basis"]')],
     "22 the basis accessor shares nested references", PROBE_SHARE),
    ("M22b", [(VALUES, '        return copy.deepcopy(self._view["plan_hash"])      # a value from from_dict may be a dict or a list',
               '        return self._view["plan_hash"]')],
     "22 the plan_hash accessor shares a container of an unverified plan", None),
    ("M22c", [(VALUES, "    def to_dict(self):\n        return copy.deepcopy(self._view)", "    def to_dict(self):\n        return self._view")],
     "22 to_dict shares the whole view", None),
    ("M22d", [(VALUES, '        return "RestorePlan(status=%s, plan_hash=%s)" % (shown[0], shown[7][:12])',
               '        return "RestorePlan(%s)" % (self._text,)')],
     "22 the representation shows the whole plan (market values, rows)", None),
    # ---- the fixes of the review (R-01, R-02): each fix taken out again on its own -----------------------------------
    ("F01a", [(BUILD, "    settle_changes(draft, events, created)\n", "")],
     "R-01 the changed fields of a replayed acknowledgement are not settled from the finished records", None),
    ("F01b", [(BUILD, "    settle_changes(draft, events, created)\n", ""),
              (RECORDS, '    changed = [] if old["kind"] == ACK else sorted(name for name in names if not same(new[name], old[name]))',
               '    changed = sorted(name for name in names if not same(new[name], old[name]))')],
     "R-01 the version before the fix: the fields are compared before the hashes inside the references are filled in", None),
    ("F02a", [(CONFIRM, "    _reapply_olds(basis, events)      # the saved APPLY records of the REAPPLY operations: a refusal is still the plan's\n",
               "")],
     "R-02 the records named by the REAPPLY operations are read only after the current inputs", None),
    ("F02b", [(CONFIRM, 'and isinstance(basis["changes"], list) and all(change_ok(c) for c in basis["changes"])',
               'and isinstance(basis["changes"], list)')],
     "R-02 the rows of changes are not checked in the plan's own form", None),
    ("F02c", [(CONFIRM, 'and isinstance(basis["series_inputs"], list) and all(series_item_ok(i) for i in basis["series_inputs"])',
               'and isinstance(basis["series_inputs"], list)')],
     "R-02 the items of series_inputs are not checked in the plan's own form", None),
    ("F02d", [(CONFIRM, 'and is_int(o["from_seq"]) and o["from_seq"] >= 0 for o in ops)', 'and is_int(o["from_seq"]) for o in ops)')],
     "R-02 a negative from_seq of an operation is not refused in the plan's own form", None),
    ("F02e", [(CONFIRM, '            and point["seq"] >= 0 and is_hex64(point["event_hash"])', '            and is_hex64(point["event_hash"])')],
     "R-02 a negative restore point of the plan is not refused in the plan's own form", None),
    ("F02f", [(VALUES, 'and is_int(c["from_seq"]) and c["from_seq"] >= 0 and c["kind"] in RECORD_KINDS',
               'and is_int(c["from_seq"]) and c["kind"] in RECORD_KINDS')],
     "R-02 a negative from_seq in a row of changes is not refused", None),
    ("F02g", [(VALUES, '            and isinstance(c["changed_fields"], list) and all(f in CHANGED_NAMES for f in c["changed_fields"]))',
               '            and isinstance(c["changed_fields"], list))')],
     "R-02 the field names of a row of changes are not checked", None),
    ("F02h", [(VALUES, 'and _row_ok(item["row"]) and (item["prev_row"] is None or _row_ok(item["prev_row"])))',
               'and (item["prev_row"] is None or _row_ok(item["prev_row"])))')],
     "R-02 the row of a series input is not checked in the plan's own form", None),
]


def failing_tests(output):
    return re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", output, re.M)


def run_one(job):
    mid, edits, what, probe = job
    tmp = tempfile.mkdtemp(prefix="v2s3b4_mut_")
    lines = []
    try:
        for d in COPIED:
            shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__", ".git"))
        for rel, old, new in edits:
            target = os.path.join(tmp, rel)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            if text.count(old) != 1:
                return mid, "SETUP-ERROR", ["%s SETUP-ERROR: pattern count %d in %s - %s" % (
                    mid, text.count(old), rel, old[:70].replace("\n", " "))], what
            with open(target, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_restore",
                            "-p", "test_r4_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           timeout=900, env=env)
        detected = r.returncode != 0
        fails = failing_tests(r.stdout)
        names = sorted({"%s.%s" % (c.split(".")[0].replace("test_r4_", "r4_"), n) for n, c in fails})
        status = "DETECTED" if detected else ("EQUIVALENT" if what.startswith("EQUIVALENT") else "NOT DETECTED")
        lines.append("%s %s (%d failing tests) - %s" % (mid, status, len(fails), what))
        for n in names[:4]:
            lines.append("   caught by " + n)
        if probe:
            p = subprocess.run([sys.executable, "-B", "-c", probe], cwd=tmp, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=300, env=env)
            lines.append(p.stdout.rstrip() if p.stdout.strip() else "   probe: (no output) %s" % p.returncode)
        return mid, status, lines, what
    finally:
        shutil.rmtree(tmp, True)


def main():
    args = sys.argv[1:]
    jobs_n = 4
    if "--jobs" in args:
        i = args.index("--jobs")
        jobs_n = int(args[i + 1])
        del args[i:i + 2]
    control = "--control" in args
    only = set(a for a in args if a != "--control")
    jobs = [("CONTROL", [], "no defect (the suite must pass)", None)] if control else []
    jobs += [m for m in MUTATIONS if not only or m[0] in only or any(m[0].startswith(o) for o in only)]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs_n) as pool:
        for mid, status, lines, what in pool.map(run_one, jobs):
            results[mid] = status
            print("\n".join(lines), flush=True)
    detected = [m for m, s in results.items() if s == "DETECTED"]
    equivalent = [m for m, s in results.items() if s == "EQUIVALENT"]
    lost = [m for m, s in results.items() if s in ("NOT DETECTED", "SETUP-ERROR") and m != "CONTROL"]
    if "CONTROL" in results and results["CONTROL"] == "DETECTED":
        lost.append("CONTROL")
    print("mutants:", len(results), "detected:", len(detected))
    print("equivalent (not counted):", equivalent or "none")
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
