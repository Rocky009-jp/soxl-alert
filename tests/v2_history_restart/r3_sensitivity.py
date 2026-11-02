"""Defect injection for the S3-B-3 tests: copy the working tree to a temporary directory, apply ONE defect to the copy
of v2_history_restart, run the v2_history_restart suite there and require it to fail. Not part of the product, not a
unittest (run it by hand: <python> -B tests/v2_history_restart/r3_sensitivity.py [ids]). The real tree is never modified.

The 18 defects of the request (section 5) are the numbered items; an item with several ways to break it has variants
a / b / c. For every defect the output says by which test it was caught and, where the request asks for it (P-04), what the
mutated runtime answers for a probe request: the package's own pre-check (restart_invalid ...), the independent guard of the
unchanged validate_history (history_invalid ...), or the delegation contract (spy / double tests). A mutant that no test
tells apart is printed as NOT DETECTED (it is never silently called equivalent; an argued case is marked EQUIVALENT).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
COPIED = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
          "tests/v2_history_restart", "tests/v2_history_ops", "tests/v2_history", "tests/v2_recovery",
          "tests/v2_persistence")
BUILD, CONFIRM, VALUES = "v2_history_restart/build.py", "v2_history_restart/confirm.py", "v2_history_restart/values.py"

PROBE_HEAD = '''
import sys
sys.path.insert(0, "tests/v2_history_restart")
import r3_helpers as R
T, H, X, D, P = R.T, R.H, R.X, R.D, R.P
def show(label, fn, *a, **k):
    o = T.outcome(fn, *a, **k)
    print("   probe", label, "->", o[:4] if o[0] == "err" else "accepted")
'''
P_DROPDECL = PROBE_HEAD + '''
b = H.HB(); b.apply(D[1], 27.0); b.declare(D[2], "q1"); b.restore(1, {2: "DROP"}, "q2")
show("dropped declaration, resume=D1", R.prep, b.history(), b.w, D[1], D[2], "r1")
'''
P_DROPRESTART = PROBE_HEAD + '''
b = H.HB(); b.apply(D[1], 27.0); b.restart(D[3], "q1"); b.restore(1, {2: "DROP"}, "q2")
show("dropped restart, resume=D1", R.prep, b.history(), b.w, D[1], D[2], "r1")
'''
P_OLDSEG = PROBE_HEAD + '''
b = H.HB(); b.apply(D[1], 27.0); b.declare(D[2], "q1"); b.restart(D[3], "q2"); b.apply(D[4], 30.0)
show("old-segment declaration D2, resume=D4", R.prep, b.history(), b.w, D[4], D[5], "r1")
c = H.HB(); c.apply(D[2], 28.0); c.restart(D[3], "q1")
show("old-segment apply D2, resume=D3 (noop-free)", R.prep, c.history(), c.w, D[3], D[4], "r1")
d = H.HB(); d.apply(D[1], 27.0); d.restart(D[2], "q1"); d.apply(D[3], 30.0); d.restart(D[4], "q2")
show("two restarts, resume=D2", R.prep, d.history(), d.w, D[2], D[5], "r1")
'''
P_NOOP = PROBE_HEAD + '''
b = H.HB()
show("initial state, same boundary", R.prep, b.history(), b.w, D[0], D[1], "r1")
show("initial state, advance", R.prep, b.history(), b.w, D[1], D[1], "r1")
'''
P_EQ = PROBE_HEAD + '''
b = R.example_u()
show("resume == check_d", R.prep, b.history(), b.w, D[3], D[3], "r1")
'''
P_SESS = PROBE_HEAD + '''
b = R.example_u()
show("resume unconfirmed", R.prep, b.history(), b.w, D[3], D[4], "r1", R.sessions_with(unconfirmed=(D[3],)))
show("resume == check_d, valid", R.prep, b.history(), b.w, D[3], D[3], "r1")
'''
P_PARENT = PROBE_HEAD + '''
b = H.HB(); b.apply(D[1], 27.0); b.declare(D[2], "q1")
show("parent is a declaration", R.prep, b.history(), b.w, D[3], D[3], "r1")
'''
P_STATE = PROBE_HEAD + '''
b = R.example_u()
show("state after an apply", R.prep, b.history(), b.w, D[3], D[3], "r1")
'''
P_ID = PROBE_HEAD + '''
b = H.HB(); b.apply(D[1], 27.0); b.restart(D[3], "only-superseded"); b.restore(1, {2: "DROP"}, "q2")
show("id only in a superseded record", R.prep, b.history(), b.w, D[2], D[3], "only-superseded")
c = R.example_u(); plan, res = R.run(c.history(), c.w, D[3], D[3], "r1")
show("same id, same content", R.prep, res.history, c.w, D[3], D[3], "r1")
'''
P_CONFIRM = PROBE_HEAD + '''
b = R.example_u(); h = b.history(); w = b.w
plan = R.prep(h, w, D[3], D[4], "r1")
show("wrong confirmed hash", X.confirm_restart_plan, plan, "0" * 64, h, w.sessions, w.ledger)
forged = R.with_plan_dict(plan, lambda d: d.__setitem__("plan_hash", "a" * 64))
show("forged plan hash", R.confirm, forged, h, w, None, None, "a" * 64)
show("ledger changed", R.confirm, plan, h, w, None, w.ledger + [P.obs("N1", D[8], 30.0)])
show("history moved", R.confirm, plan, H.HB(world=w, events=b.events + []).history(), w)
'''
P_INVALID = PROBE_HEAD + '''
b = R.example_u(); h = b.history(); w = b.w
plan = R.prep(h, w, D[3], D[4], "r1")
broken = H.mutated(b.events, lambda ev: ev[2].__setitem__("d", D[9]))
show("invalid history", R.confirm, plan, broken, w)
'''
P_B = PROBE_HEAD + '''
b = R.example_u(); h = b.history(); w = b.w
plan, res = R.run(h, w, D[3], D[3], "r1")
show("reconfirm against the candidate", R.confirm, plan, res.history, w)
bad = R.refreshed(plan, lambda bs: bs.__setitem__("floor", {"last_apply_d": D[1], "last_declared_d": None, "prev_boundary": D[0]}))
show("candidate with a wrong floor", R.confirm, bad, res.history, w)
'''
P_SHARE = PROBE_HEAD + '''
b = R.example_u(); plan = R.prep(b.history(), b.w, D[3], D[4], "r1")
plan.basis["floor"]["last_apply_d"] = "X"; plan.to_dict()["basis"]["floor"]["x"] = 1
print("   probe nested change visible in the plan ->", plan.basis["floor"].get("last_apply_d") == "X")
'''

# (id, [(path, old, new), ...], what is broken, probe or None)   every old must occur exactly once in its file
MUTATIONS = [
    ("M01a", [(BUILD, '    declared = [r["d"] for r in view.resolutions if r["kind"] == DECLARE_MISSING]',
               '    declared = [e["d"] for e in HIST.events if e["kind"] == DECLARE_MISSING]'),
              (BUILD, "def _floor_of(check, view):", "def _floor_of(check, view, HIST=None):"),
              (BUILD, "    floor = _floor_of(check, view)", "    floor = _floor_of(check, view, history)")],
     "1 the floor reads declared days from the physical array (superseded ones count)", P_DROPDECL),
    ("M01b", [(BUILD, '    return {"last_apply_d": check.latest_apply_d,',
               '    return {"last_apply_d": max([a["d"] for a in view.applies] + [view.current_boundary["after"]]),'),
              ],
     "1 the floor's last_apply_d takes the current boundary into it (a boundary day counts as an apply day)", P_DROPRESTART),
    ("M02a", [(BUILD, '    declared = [r["d"] for r in view.resolutions if r["kind"] == DECLARE_MISSING]',
               '    declared = [r["d"] for r in view.resolutions if r["kind"] == DECLARE_MISSING\n'
               '                and r["segment_seq"] == view.segments[-1]["seq"]]')],
     "2 the floor leaves out the declarations of older segments", P_OLDSEG),
    ("M02b", [(BUILD, '    return {"last_apply_d": check.latest_apply_d,',
               '    return {"last_apply_d": max([a["d"] for a in view.applies if a["segment_seq"] == view.segments[-1]["seq"]],\n'
               '                                 default=None),')],
     "2 the floor leaves out the APPLY days of older segments", P_OLDSEG),
    ("M03a", [(BUILD, "    if resume_after < max(v for v in floor.values() if v is not None):",
               '    if resume_after < max([v for k, v in floor.items() if v is not None and k != "prev_boundary"] or [""]):')],
     "3 the previous boundary is ignored in the lower bound (still written into the record)", P_OLDSEG),
    ("M03b", [(BUILD, '            "prev_boundary": check.current_boundary.after}',
               '            "prev_boundary": view.segments[0]["after"]}')],
     "3 the previous boundary is the first segment's date", P_OLDSEG),
    ("M04a", [(BUILD, '    if same(history.current_state, initial_state()) and resume_after == floor["prev_boundary"]:',
               "    if False:")],
     "4 the no-effect restart (initial state, same boundary) is accepted", P_NOOP),
    ("M04b", [(BUILD, '    if same(history.current_state, initial_state()) and resume_after == floor["prev_boundary"]:',
               '    if same(history.current_state, initial_state()) and resume_after >= floor["prev_boundary"]:')],
     "4 the no-effect rule also refuses an advance of the boundary", P_NOOP),
    ("M05", [(BUILD, "    if resume_after > check_d:", "    if resume_after >= check_d:")],
     "5 resume_after == check_d is refused", P_EQ),
    ("M06a", [(BUILD, "    if resume is None or not resume.confirmed:", "    if resume is None:")],
     "6 the resume session's confirmed flag is not checked", P_SESS),
    ("M06b", [(BUILD, "    return resume\n", "    return session\n")],
     "6 the boundary session of another day (check_d's) is written into the record", P_SESS),
    ("M07", [(BUILD, "    ledger = project_history_ledger(history, sessions, raw_observations, check_d)          # 5",
              '    ledger = type("L", (), {"ledger_digest": "0" * 64, "effective_digest": "0" * 64})()')],
     "7 the projection of the original history is left out", P_OLDSEG),
    ("M08", [(BUILD, "    events = history.events                                                                # 6",
              "    events = history.events\n"
              '    last_apply = [e for e in events if e["kind"] == "APPLY"][-1]\n'
              '    rec["parent_seq"], rec["parent_hash"] = last_apply["seq"], last_apply["event_hash"]\n'
              '    rec.pop("event_hash")\n    rec["event_hash"] = compute_event_hash(rec)')],
     "8 the parent is the last APPLY, not the physical head", P_PARENT),
    ("M09", [(BUILD, "    events = history.events                                                                # 6",
              "    events = history.events\n"
              '    rec["state_after"] = history.current_state\n'
              '    rec.pop("event_hash")\n    rec["event_hash"] = compute_event_hash(rec)')],
     "9 state_after is copied from the parent", P_STATE),
    ("M10a", [(BUILD, "    if (len(events) != len(old) + 1 or canonical_json(events[:-1]) != canonical_json(old)\n"
               "            or canonical_json(events[-1]) != canonical_json(rec)):",
               "    if False:")],
     "10 a candidate that changes the past events or the new record is passed", None),
    ("M10b", [(BUILD, "    if (list(cand_check.effective_seqs) != list(check.effective_seqs) + [rec[\"seq\"]]\n"
               "            or list(cand_check.superseded_seqs) != list(check.superseded_seqs)\n",
               "    if (False\n")],
     "10 a candidate with other effective / superseded seqs is passed", None),
    ("M10c", [(BUILD, "            or not same(cand_view.applies, view.applies) or not same(cand_view.resolutions, view.resolutions)\n"
               "            or not same(cand_view.segments[:-1], view.segments)):",
               "            ):")],
     "10 a candidate that changes the effective APPLY / ACK / declaration facts is passed", None),
    ("M11a", [(BUILD, "    cand_check = validate_history(candidate)\n    events, old = candidate.events, history.events",
               "    cand_check = check\n    events, old = candidate.events, history.events")],
     "11 validate_history is not called on the candidate", None),
    ("M11b", [(BUILD, "    cand_view = read_effective(candidate)\n", "    return cand_check\n    cand_view = read_effective(candidate)\n")],
     "11 the preservation checks of design 8 are left out (validate_history stays)", None),
    ("M12", [(BUILD, '    if any(g["request_id"] == request_id for g in view.requests):',
              '    if any(g["request_id"] == request_id and g["effective"] for g in view.requests):')],
     "12 the request id is compared against the effective chain only", P_ID),
    ("M13", [(BUILD, '    if any(g["request_id"] == request_id for g in view.requests):',
              '    if any(g["request_id"] == request_id and g["request_hash"] != basis_request_hash({\n'
              '            "request_id": request_id, "resume_after": resume_after, "check_d": check_d, "reason_code": REASON,\n'
              '            "requested_at": requested_at}) for g in view.requests):')],
     "13 prepare lets a same id with the same content through (as in B-2's NO_CHANGE)", P_ID),
    ("M14a", [(CONFIRM, "            or confirmed_plan_hash != view[\"plan_hash\"] or not _form_ok(basis)):",
               "            or not _form_ok(basis)):")],
     "14 the confirmed plan hash is not compared with the plan's", P_CONFIRM),
    ("M14b", [(CONFIRM, "    if (not isinstance(basis, dict) or set(basis) != BASIS_KEYS or view[\"plan_hash\"] != sha256_text(canonical_json(basis))\n",
               "    if (not isinstance(basis, dict) or set(basis) != BASIS_KEYS\n")],
     "14 the plan hash is not recomputed from the basis", P_CONFIRM),
    ("M14c", [(CONFIRM, "    same_inputs = (ledger_digest(rows) == basis[\"ledger_digest\"] and sessions_digest(sl) == basis[\"sessions_digest\"])",
               "    same_inputs = True")],
     "14 the ledger and sessions digests of the plan are ignored", P_CONFIRM),
    ("M14d", [(CONFIRM, "    original = (history.digest == basis[\"history_digest\"] and check.head_seq == basis[\"expected_head_seq\"]\n"
               "                and check.head_hash == basis[\"expected_head_hash\"])                        # 3 branch A",
               "    original = True")],
     "14 the history digest and head of the plan are ignored (every history is taken as the original)", P_CONFIRM),
    ("M15", [(CONFIRM, "    check = validate_history(history)                                                      # 2",
              "    try:\n        check = validate_history(history)\n    except CoreError:\n        raise history_plan_stale() from None")],
     "15 an invalid input history is turned into a stale plan", P_INVALID),
    ("M16a", [(CONFIRM, "    already = (history.digest == basis[\"candidate_digest\"] and check.head_seq == cand_check.head_seq\n"
               "               and check.head_hash == cand_check.head_hash)                                #   branch B",
               "    already = False")],
     "16 the same plan against its own candidate is stale", P_B),
    ("M16b", [(CONFIRM, "        source = history if original else _original_of(history, basis)", "        source = history")],
     "16 the candidate is taken as the original again (a second RESTART would be made)", P_B),
    ("M17a", [(CONFIRM, "    check = validate_history(original)\n",
               "    check = type(\"C\", (), {\"history_digest\": original.digest, \"head_seq\": original.head_seq,\n"
               "                             \"head_hash\": original.head_hash,\n"
               "                             \"state_digest\": sha256_text(canonical_json(original.current_state))})()\n")],
     "17 branch B does not check the original prefix with validate_history", P_B),
    ("M17b", [(CONFIRM, "    if (check.history_digest != basis[\"history_digest\"] or check.head_seq != basis[\"expected_head_seq\"]\n"
               "            or check.head_hash != basis[\"expected_head_hash\"] or check.state_digest != basis[\"expected_state_digest\"]):\n"
               "        raise history_plan_mismatch()\n    return original",
               "    return original")],
     "17 branch B does not compare the original prefix's digest / head / state with the plan", P_B),
    ("M17c", [(CONFIRM, "    if not same(rebuilt, basis) or rebuilt_candidate != candidate:\n        raise history_plan_mismatch()",
               "    if original and (not same(rebuilt, basis) or rebuilt_candidate != candidate):\n        raise history_plan_mismatch()")],
     "17 branch B does not compare the whole rebuilt basis", P_B),
    ("M18a", [(VALUES, '        return copy.deepcopy(self._view["basis"])', '        return self._view["basis"]')],
     "18 the basis accessor shares nested references", P_SHARE),
    ("M18b", [(VALUES, '        return copy.deepcopy(self._view["plan_hash"])      # a value from from_dict may be a dict or a list',
               '        return self._view["plan_hash"]')],
     "18 the plan_hash accessor shares a container of an unverified plan", None),
    ("M18c", [(VALUES, "    def to_dict(self):\n        return copy.deepcopy(self._view)", "    def to_dict(self):\n        return self._view")],
     "18 to_dict shares the whole view", None),
]


def failing_tests(output):
    return re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", output, re.M)


def main():
    only = set(a for a in sys.argv[1:])
    control = "--control" in sys.argv
    only.discard("--control")
    lost, detected_n, equivalent = [], 0, []
    jobs = [("CONTROL", [], "no defect (the suite must pass)", None)] if control else []
    jobs += [m for m in MUTATIONS if not only or m[0] in only]
    for mid, edits, what, probe in jobs:
        tmp = tempfile.mkdtemp(prefix="v2s3b3_mut_")
        try:
            for d in COPIED:
                shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d),
                                ignore=shutil.ignore_patterns("__pycache__", ".git"))
            ok = True
            for rel, old, new in edits:
                target = os.path.join(tmp, rel)
                with open(target, encoding="utf-8") as f:
                    text = f.read()
                if text.count(old) != 1:
                    print(mid, "SETUP-ERROR: pattern count", text.count(old), "in", rel, "-", old[:60].replace("\n", " "))
                    lost.append(mid)
                    ok = False
                    break
                with open(target, "w", encoding="utf-8") as f:
                    f.write(text.replace(old, new))
            if not ok:
                continue
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history_restart",
                                "-p", "test_r3_*.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=900, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            detected = r.returncode != 0
            fails = failing_tests(r.stdout)
            names = sorted({"%s.%s" % (c.split(".")[0].replace("test_r3_", "r3_"), n) for n, c in fails})
            print(mid, "DETECTED" if detected else "NOT DETECTED", "(%d failing tests)" % len(fails), "-", what)
            for n in names[:4]:
                print("   caught by", n)
            if probe:
                p = subprocess.run([sys.executable, "-B", "-c", probe], cwd=tmp, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, timeout=300,
                                   env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                print(p.stdout.rstrip() if p.stdout.strip() else "   probe: (no output) %s" % p.returncode)
            if detected:
                detected_n += 1
            elif mid == "CONTROL":
                pass
            else:
                (equivalent if "EQUIVALENT" in what else lost).append(mid)
            if mid == "CONTROL" and detected:
                lost.append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("detected:", detected_n)
    print("equivalent (not counted):", equivalent or "none")
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
