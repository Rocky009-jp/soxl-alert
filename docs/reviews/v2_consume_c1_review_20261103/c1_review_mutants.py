"""Independent mutants of the review (not the implementer's runner). argv[1] = clean clone at 3f780c1, argv[2] = work dir.
Each mutant: a fresh worktree, one exact replacement (must match once), the C-1 suite run; killed when it fails."""
import os, subprocess, sys, shutil
SRC, WORK = sys.argv[1], sys.argv[2]
REV = "3f780c116964bbcfc8007b8e371f194bdca6db39"
M = {
 "m01_checker_day": ("v2_history/restore.py",
   "            if events[created][\"d\"] != entry[\"d\"]:\n                raise _bad(\"restore_replay_mismatch\")\n",
   ""),
 "m03_checker_batch": ("v2_history/restore.py",
   "            if before & after:\n                raise _bad(\"restore_consume_in_batch\")", "            pass"),
 "m05_no_freed_check": ("v2_history_restore/build.py",
   "    _check_consumed_released(events, effective, plan_ops, draft, sl)\n    point =", "    point ="),
 "m06c_no_new_skips": ("v2_history_restore/build.py", "    days |= draft.new_skips\n", ""),
 "m06d_trial_new_skips": ("v2_history_restore/records.py",
   "(set(new[\"skipped_sessions\"]) | set(consumed_since))", "set(new[\"skipped_sessions\"])"),
 "m09_eval_reapply_only": ("v2_history_restore/build.py", "    for new in draft.made:\n",
   "    for new in [n for _o, n in draft.reapplied]:\n"),
 "m11_no_effect": ("v2_history_restore/build.py", "e[\"op\"] in (DROP, CONSUME) for e in plan_ops", "e[\"op\"] == DROP for e in plan_ops"),
 "m12b_reapply_guard": ("v2_history_restore/records.py",
   "    if not base < d:                       # only a CONSUME", "    if False:                       # only a CONSUME"),
 "m14_confirm_drop_consume": ("v2_history_restore/market.py",
   "        elif entry[\"op\"] == CONSUME:\n", "        elif False:\n"),
 "m18_confirm_ops_match": ("v2_history_restore/confirm.py",
   "    if (_has_consume(basis[\"ops\"]) or _has_consume(stated)) and not same(basis[\"ops\"], stated):", "    if False:"),
 "m19_consume_detail": ("v2_history_restore/points.py",
   "raise restore_invalid(\"ops\", \"restore_consume_duplicate\", detail=entry[\"d\"])",
   "raise restore_invalid(\"ops\", \"restore_consume_duplicate\")"),
 "m20_kept_rows_unsorted": ("v2_history_restore/build.py",
   "rows = sorted((r.cols for r in remaining.values()), key=canonical_json)", "rows = [r.cols for r in remaining.values()]"),
}
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
for name, (path, old, new) in M.items():
    wt = os.path.join(WORK, name)
    shutil.rmtree(wt, ignore_errors=True)
    subprocess.run(["git", "-C", SRC, "worktree", "add", "-q", "--detach", wt, REV], check=True)
    p = os.path.join(wt, path)
    text = open(p).read()
    n = text.count(old)
    if n != 1:
        print(name, "SETUP_FAILED count=%d" % n); continue
    open(p, "w").write(text.replace(old, new))
    out = {}
    for d, pat in (("v2_history_consume", "test_c1_*.py"), ("v2_history", "test_h*.py"), ("v2_history_restore", "test_r4_*.py")):
        if d != "v2_history_consume" and name not in ("m01_checker_day", "m03_checker_batch", "m11_no_effect", "m20_kept_rows_unsorted"):
            continue
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/" + d, "-p", pat],
                           cwd=wt, env=env, capture_output=True, text=True)
        last = [l for l in r.stderr.splitlines() if l.startswith("FAILED") or l == "OK" or l.startswith("OK ")]
        out[d] = (r.returncode, last[-1] if last else r.stderr[-200:])
    killed = any(rc != 0 for rc, _ in out.values())
    print(name, "KILLED" if killed else "SURVIVED", out)
    subprocess.run(["git", "-C", SRC, "worktree", "remove", "--force", wt], check=True)
