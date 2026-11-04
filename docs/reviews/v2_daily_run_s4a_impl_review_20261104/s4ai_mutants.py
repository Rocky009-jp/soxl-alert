"""Independent mutants of v2_daily_run/run.py (c15ab18) for the S4-A implementation review.
usage: python s4ai_mutants.py <worktree> <python> <out.json> [ids...]
Each mutant replaces one text that must occur exactly once, runs tests/v2_daily_run, then restores the file."""
import json, os, subprocess, sys, time

RUN = "v2_daily_run/run.py"
VAL = "v2_daily_run/values.py"
M = [
 ("V01", RUN, "return ConsumedDay(res.d, res.status, res.core_result.gap, skipped)",
  "return ConsumedDay(res.d, res.status, bool(skipped), skipped)", "gap of a consumed day = skipped non-empty (P-01 direction)"),
 ("V02", RUN, "        if s.date > target_d:\n            break\n", "", "no break after the target (sessions after D are looked at)"),
 ("V03", RUN, "    if target_d < start:\n        return (STOPPED, TARGET_BEFORE_HEAD, \"sessions\", None, None)\n", "",
  "no target-before-start check (the core error decides)"),
 ("V04", RUN, "    run.history = history\n    run.target_status, run.core_result = None, None\n",
  "    run.history = history\n    run.target_status, run.core_result = None, None\n    run.sent = set()\n",
  "the double-send guard is reset on a restart"),
 ("V05", RUN, "                if e.code != \"store_commit_uncertain\":\n                    raise\n                uncertain = True\n",
  "                if e.code != \"store_commit_uncertain\":\n                    raise\n                uncertain = True\n                if run.restarts < 1:\n                    rec_outcome = store.reconcile(publication).outcome\n",
  "reconcile also called inside the handler (twice, context chain)"),
 ("V07", RUN, "return (STALE, SESSION_UNCONFIRMED, \"sessions\", None, s.date)",
  "return (STALE, SESSION_UNCONFIRMED, \"sessions\", None, None)", "STALE without the session date"),
 ("V08", RUN, "条件未達ではありません。", "", "notice without 'not a condition failure'"),
 ("V10", RUN, "    if not isinstance(sessions, SessionList):\n        raise RunError(ARGS_INVALID, \"sessions\")\n", "",
  "sessions not type-checked"),
 ("V11", RUN, "if not callable(getattr(store, name, None)):", "if not hasattr(store, name):", "store methods: hasattr instead of callable"),
 ("V12", RUN, "if s.close_at <= now:", "if s.open_at <= now:", "target by open_at"),
 ("V15", RUN, "if outcome in (PUBLISHED, PUBLISHED_THEN_EXTENDED):", "if outcome == PUBLISHED:", "PUBLISHED_THEN_EXTENDED not a success"),
 ("V17", RUN, "        if s.date == target_d:\n            run.target_status",
  "        if s.date == target_d and res.status == PREPARED:\n            run.target_status", "target result kept only when PREPARED"),
 ("V19", RUN, "message = \"\\n\".join(lines + [render_message(run.core_result)])",
  "message = \"\\n\".join([render_message(run.core_result)] + lines)", "gap lines after the core text"),
 ("V20", RUN, "0 < len(text) <= 64", "0 < len(text) <= 16", "identifier filter limited to 16 characters"),
 ("V22", VAL, "EXIT_OK if outcome == DONE else EXIT_NOT_OK", "EXIT_OK if outcome != STOPPED else EXIT_NOT_OK", "STALE exit 0"),
 ("V23", RUN, "    run.history = history\n    run.target_status", "    run.target_status", "run.history not set at the start of a pass"),
 ("V25", RUN, "            run.sent.add(publication.publication_hash)\n", "", "sent set never filled"),
 ("V27", RUN, "    lines.append(\"  この実行で保存した日: %s\" % _days([d.d for d in consumed]))\n", "", "notice without the saved days"),
 ("V28", RUN, "    if lines:\n        lines.insert(0, \"【今回の追いつきで見つかった欠測】\")\n",
  "    lines.insert(0, \"【今回の追いつきで見つかった欠測】\")\n", "gap header always"),
 ("V29", RUN, "return (STALE, SESSION_UNCONFIRMED", "return (STOPPED, SESSION_UNCONFIRMED", "unconfirmed -> STOPPED instead of STALE"),
 ("V30", RUN, "    run.history = history\n    run.target_status, run.core_result = None, None\n", "    run.history = history\n",
  "target result not reset on a restart"),
 ("V31", RUN, "        if not s.confirmed:\n            return", "        if not s.confirmed and s.date != target_d:\n            return",
  "an unconfirmed target is left to the core (STOPPED target_unconfirmed)"),
 ("V32", RUN, "_RESTART = object()", "_RESTART = None", "restart marker equals 'done' (a reconciled save ends the run)"),
 ("V33", RUN, "                    run.consumed.append(day)\n                    run.restarts += 1\n",
  "                    run.restarts += 1\n", "reconciled day not counted (cf. add3)"),
 ("V34", RUN, "lines.append(\"  対象のセッション: %s\" % detail)", "pass", "notice without the detail line"),
]

def main():
    wt, py, out = sys.argv[1], sys.argv[2], sys.argv[3]
    ids = set(sys.argv[4:])
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    results = []
    for mid, rel, old, new, what in M:
        if ids and mid not in ids:
            continue
        path = os.path.join(wt, rel)
        src = open(path, encoding="utf-8").read()
        n = src.count(old)
        if n != 1:
            results.append({"id": mid, "what": what, "result": "SETUP_FAILED", "count": n}); continue
        open(path, "w", encoding="utf-8").write(src.replace(old, new))
        try:
            t = time.time()
            p = subprocess.run([py, "-B", "-m", "unittest", "discover", "-s", "tests/v2_daily_run", "-p", "test_s4a_*.py"],
                               cwd=wt, env=env, capture_output=True, text=True, timeout=900)
            tail = p.stderr.strip().splitlines()
            failed = [l.split(" ", 1)[1] for l in tail if l.startswith(("FAIL: ", "ERROR: "))]
            results.append({"id": mid, "what": what, "result": "DETECTED" if p.returncode else "UNDETECTED",
                            "summary": tail[-1] if tail else "", "failed": failed[:5], "n_failed": len(failed),
                            "seconds": round(time.time() - t, 1)})
        finally:
            open(path, "w", encoding="utf-8").write(src)
        print(mid, results[-1]["result"], results[-1].get("n_failed"), flush=True)
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)

main()
