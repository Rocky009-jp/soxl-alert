"""Independent defect injection of the reviewer (ratio emphasis, 4b5ed0c). Each mutant changes one place of the runtime in a
copy of the tree (without .git); the quick suites of the four touched packages and v2_run must fail.
usage: mutate_review.py <python> <tree> <workdir> <out.json>"""
import json, os, shutil, subprocess, sys
PY, SRC, WORK, OUT = sys.argv[1:5]
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree(SRC, WORK, ignore=shutil.ignore_patterns(".git"))
DISPLAY, VALUES, RUN, COMPOSE = "v2_core/display.py", "v2_daily_run/values.py", "v2_daily_run/run.py", "v2_notify/compose.py"
H = "headline=ratio_headline(run.core_result))"
M = [
 ("V01 run: only a confirmed day gets the headline", RUN, H,
  "headline=ratio_headline(run.core_result) if run.core_result.run_class.name == 'CONDITION_MET' else None)"),
 ("V02 run: a morning after skipped sessions (gap lines) loses the headline", RUN, H,
  "headline=None if lines else ratio_headline(run.core_result))"),
 ("V03 run: only a PREPARED target gets the headline (ALREADY_APPLIED / NO_COMMIT re-run loses it)", RUN, H,
  "headline=ratio_headline(run.core_result) if run.target_status == PREPARED else None)"),
 ("V04 compose: the headline is dropped when there are lines about sessions without a record", COMPOSE,
  "        if report.headline is not None:\n",
  "        if report.headline is not None and not _missing_lines(report, only_without_gap=True):\n"),
 ("V05 compose: the headline is dropped on a NO_COMMIT morning (the note after the open)", COMPOSE,
  "        if report.headline is not None:\n",
  "        if report.headline is not None and report.target_status != NO_COMMIT_STATUS:\n"),
 ("V06 compose: the headline goes after the note lines instead of the first line", COMPOSE,
  "        lines.append(report.message)\n        return Notice(MORNING",
  "        lines.append(report.message)\n        lines = [lines[0].split(' ／ ')[0]] + lines[1:-1] + ([report.headline] if report.headline else []) + lines[-1:]\n        return Notice(MORNING"),
 ("V07 display: the body line goes right before the profile lines", DISPLAY,
  "    lines += _profile_lines(result)\n",
  "    lines += ([ratio_line(result)] if ratio_line(result) else []) + _profile_lines(result)\n"),
 ("V08 display: the confirmed headline of NORMAL also says hand check", DISPLAY,
  'tail = "（手元確認が必要）" if rule.name == "TREND" else ""', 'tail = "（手元確認が必要）" if rule.name != "EXFEAR" else ""'),
 ("V09 display: the unconfirmed body line is bold too", DISPLAY,
  '"▶ 投入比率の目安：利用可能資金の%d%%（参考・未確認、比率のみ）"', '"▶ 投入比率の目安：**利用可能資金の%d%%**（参考・未確認、比率のみ）"'),
 ("V10 display: a WAITING_FG day whose trend rule could fire gets a ratio", DISPLAY,
  "    if isinstance(result, ErrorResult) or result.run_class not in RATIO_SIGNAL_CLASSES:\n        return None\n",
  "    if isinstance(result, ErrorResult):\n        return None\n    if result.run_class is RunClass.WAITING_FG and result.rules['TREND'].status is RuleStatus.PENDING_FG:\n        return result.rules['TREND'], False\n    if result.run_class not in RATIO_SIGNAL_CLASSES:\n        return None\n"),
 ("V11 display: confirmed decided by the class instead of the rule", DISPLAY,
  "return met[0], met[0].status is RuleStatus.MET", "return met[0], result.run_class is RunClass.CONDITION_MET"),
 ("V12 values: the headline limit is 30 characters", VALUES, "HEADLINE_MAX = 80", "HEADLINE_MAX = 30"),
 ("V13 values: headline left out of equality", VALUES,
  "return tuple(getattr(self, n) for n in self._NAMES)", "return tuple(getattr(self, n) for n in self._NAMES if n != 'headline')"),
 ("V14 compose: an empty separator (no space)", COMPOSE, 'first += " ／ " + report.headline', 'first += "／" + report.headline'),
 ("V15 display: the body line names the class instead of the rule", DISPLAY,
  "(rule.ratio, RULE_LABEL[rule.name], tail)", "(rule.ratio, CLASS_LABEL[result.run_class], tail)"),
]
SUITES = [("tests/v2_ratio", "test_ratio_01*.py"), ("tests/v2_core", "test_*.py"), ("tests/v2_daily_run", "test_*.py"),
          ("tests/v2_notify", "test_*.py"), ("tests/v2_run", "test_s4e_0[1-8]*.py")]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
def run():
    bad = []
    for d, p in SUITES:
        r = subprocess.run([PY, "-B", "-m", "unittest", "discover", "-s", os.path.join(WORK, d), "-p", p], cwd=WORK, env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            tail = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:"))][:2]
            bad.append((d.split("/")[-1], tail))
    return bad
base = run(); assert base == [], base
results = []
ONLY = os.environ.get('ONLY')
if ONLY: M = [m for m in M if m[0].split()[0] in ONLY.split(',')]
for name, path, old, new in M:
    fp = os.path.join(WORK, path); orig = open(fp, encoding="utf-8").read()
    assert orig.count(old) == 1, (name, orig.count(old))
    open(fp, "w", encoding="utf-8").write(orig.replace(old, new))
    try: bad = run()
    finally: open(fp, "w", encoding="utf-8").write(orig)
    results.append({"name": name, "detected": bool(bad), "by": [b[0] for b in bad], "first": (bad[0][1][:1] if bad else [])})
    print(name, "DETECTED" if bad else "SURVIVED", [b[0] for b in bad], flush=True)
json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("detected", sum(r["detected"] for r in results), "of", len(results))
