"""Sensitivity check: put one defect at a time into a TEMPORARY COPY of the tree and confirm the new tests fail.

    python3 -B tests/v2_core/v2_sensitivity_check.py

The working tree is never modified. For each mutation the script copies the tree, replaces one exact piece of
source text (it must occur exactly once), runs the new test files, and expects a failure. At the end it runs the
copy without any mutation and expects a pass. Exit code 0 only if every mutation was caught and the clean run passed.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PATTERNS = ("test_state_checks*.py", "test_transition*.py")

S, O, T, E = "v2_core/state.py", "v2_core/observations.py", "v2_core/transition.py", "v2_core/engine.py"

MUTATIONS = [
    # P-04: current state
    ("I-01 off", S, 'if not ((as_of is None) == (fixed is None) == (base is None)):', "if False:"),
    ("I-01 only fixed/base pair", S, '(as_of is None) == (fixed is None) == (base is None)',
     '(as_of is None) == (fixed is None)'),
    ("I-02 off", S, 'if as_of is None and not _is_initial(f):', "if False:"),
    ("I-03 off", S, 'if fixed is not None and fixed["d"] != as_of:', "if False:"),
    ("I-04 off", S, 'if base is not None and base.as_of_d is not None and not base.as_of_d < as_of:', "if False:"),
    ("I-04 allows equal", S, 'not base.as_of_d < as_of', 'base.as_of_d > as_of'),
    ("I-05 off", S, 'if f["streak"] >= 3 and f["armed"] is not Tri.TRUE:',
     'if f["streak"] >= 3 and f["armed"] is not Tri.TRUE and not current:'),
    ("I-06 off", S, 'if f["streak"] >= 1 and f["prev_normal_raw"] is not Tri.FALSE:',
     'if f["streak"] >= 1 and f["prev_normal_raw"] is not Tri.FALSE and not current:'),
    ("I-07 fingerprint unchecked", S, '_FINGERPRINT.fullmatch(fixed["fingerprint"])', "True"),
    ("I-07 fingerprint accepts upper case", S, "[0-9a-f]{64}", "[0-9a-fA-F]{64}"),
    ("I-07 fingerprint length 63..65", S, "[0-9a-f]{64}", "[0-9a-f]{63,65}"),
    ("I-07 fingerprint match instead of fullmatch", S, '_FINGERPRINT.fullmatch(', "_FINGERPRINT.match("),
    ("I-07 record_id unchecked", S, 'is_valid_record_id(fixed["record_id"])', "True"),
    # P-04: base
    ("IB-01 off", S, 'if f["fixed_decision"] is not None or f["base"] is not None:', "if False:"),
    ("IB-01 ignores fixed_decision", S, 'f["fixed_decision"] is not None or f["base"] is not None',
     'f["base"] is not None'),
    ("IB-01 ignores nested base", S, 'f["fixed_decision"] is not None or f["base"] is not None',
     'f["fixed_decision"] is not None'),
    ("IB-02 off", S, 'if f["as_of_d"] is None and not _is_initial(f):', "if False:"),
    ("IB-03 armed off", S, 'if f["streak"] >= 3 and f["armed"] is not Tri.TRUE:',
     'if f["streak"] >= 3 and f["armed"] is not Tri.TRUE and current:'),
    ("IB-03 prev_normal_raw off", S, 'if f["streak"] >= 1 and f["prev_normal_raw"] is not Tri.FALSE:',
     'if f["streak"] >= 1 and f["prev_normal_raw"] is not Tri.FALSE and current:'),
    ("top-level rule I-01 applied to the base", S, '    """IB-01..IB-03 on the nested base only."""\n',
     '    """IB-01..IB-03 on the nested base only."""\n    if f["as_of_d"] is not None:\n        raise StateInvalid("IB-01")\n'),
    ("base checked with current-state rules", S, "_check_base(raw)", "_check_current(raw, None)"),
    ("base check skipped", S, "                _check_base(raw)\n", "                pass\n"),
    # P-06
    ("record_id 65 chars allowed", O, "{0,63}", "{0,64}"),
    ("record_id space allowed", O, "[A-Za-z0-9._-]{0,63}", "[A-Za-z0-9._ -]{0,63}"),
    ("record_id may start with a dot", O, 'RECORD_ID_PATTERN = re.compile(r"[A-Za-z0-9]',
     'RECORD_ID_PATTERN = re.compile(r"[A-Za-z0-9.]'),
    ("record_id match instead of fullmatch (newline)", O, "RECORD_ID_PATTERN.fullmatch(value) is not None",
     're.match(RECORD_ID_PATTERN.pattern + "$", value) is not None'),
    ("record_id unchecked in observations", O, "if not is_valid_record_id(record_id):",
     "if not isinstance(record_id, str) or not record_id.strip():"),
    ("record_id accepts non-ASCII letters", O, "[A-Za-z0-9][A-Za-z0-9._-]{0,63}", r"\w[\w.-]{0,63}"),
    # U-14: transition
    ("transition: F&G 30 is not a streak day", T, "new_streak = streak + 1 if f >= 30 else 0",
     "new_streak = streak + 1 if f > 30 else 0"),
    ("transition: gap never detected", T, "gap = base.as_of_d is not None and base.as_of_d != prev_session_date",
     "gap = False"),
    ("transition: unknown previous row treated as not normal", T,
     "prev_ms = None if prev_row is None else market_side_normal(prev_row)", "prev_ms = False"),
    ("transition: previous market side ignored", T, "if prev_nr is Tri.UNKNOWN and prev_ms is False:",
     "if prev_nr is Tri.UNKNOWN and prev_ms is True:"),
    ("transition: candidate base keeps fixed_decision", T,
     "base_snapshot = MarketState(base.as_of_d, base.armed, base.streak, base.prev_normal_raw, None, None)",
     "base_snapshot = base"),
    ("transition: normal threshold 25 -> 26", T, "normal_raw = 25 <= f < 30 and ms_normal",
     "normal_raw = 26 <= f < 30 and ms_normal"),
    # U-14: evaluate_day
    ("engine: state_updated always true with a decision", E, "new_state, updated = t.next_state, not rerun",
     "new_state, updated = t.next_state, True"),
    ("engine: state_updated inverted", E, "new_state, updated = t.next_state, not rerun",
     "new_state, updated = t.next_state, rerun"),
    ("engine: no decision marks the state as updated", E, "new_state, updated = state, False",
     "new_state, updated = state, True"),
    ("engine: no decision returns a copy of the state", E, "new_state, updated = state, False",
     "new_state, updated = MarketState(state.as_of_d, state.armed, state.streak, state.prev_normal_raw, "
     "state.fixed_decision, state.base), False"),
    ("engine: transition gets the state instead of the base", E,
     "apply_transition(base, d, prev_session.date, row, prev_row, decision)",
     "apply_transition(state, d, prev_session.date, row, prev_row, decision)"),
    ("engine: notes dropped", E, "notes=list(t.notes)", "notes=[]"),
    ("engine: missing previous row replaced by the D row", E, "prev_row = None               #",
     "prev_row = row               #"),
    ("engine: second copy of the market-side test", E, "    t = apply_transition(",
     "    _ms = market_side_normal(row)\n    t = apply_transition("),
    ("engine: rules recomputed outside apply_transition", E, "rules=t.rules,", "rules=dict(t.rules, EXFEAR=t.rules['TREND']),"),
]


def run_tests(tree):
    failed, total, out = 0, 0, ""
    for pat in PATTERNS:
        p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_core", "-p", pat],
                           cwd=tree, capture_output=True, text=True)
        text = p.stderr + p.stdout
        m = re.search(r"Ran (\d+) tests?", text)
        total += int(m.group(1)) if m else 0
        if p.returncode != 0:
            failed += 1
            m2 = re.search(r"FAILED \(([^)]*)\)", text)
            out += (m2.group(1) if m2 else "crashed") + "; "
    return failed, total, out.strip("; ")


def main():
    work = tempfile.mkdtemp(prefix="v2core-sens-")
    try:
        tree = os.path.join(work, "tree")
        shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        originals = {}
        for rel in (S, O, T, E):
            with open(os.path.join(tree, rel), encoding="utf-8") as fh:
                originals[rel] = fh.read()
        missed = []
        print("%-62s %s" % ("mutation (one defect at a time)", "result"))
        for name, rel, old, new in MUTATIONS:
            text = originals[rel]
            if text.count(old) != 1:
                print("%-62s NOT APPLIED (found %d times)" % (name, text.count(old)))
                missed.append(name)
                continue
            path = os.path.join(tree, rel)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text.replace(old, new))
            failed, total, detail = run_tests(tree)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            if failed:
                print("%-62s caught (%s)" % (name, detail))
            else:
                print("%-62s NOT CAUGHT (new tests passed)" % name)
                missed.append(name)
        failed, total, detail = run_tests(tree)
        print("clean copy, no mutation: %d new tests, %s" % (total, "FAILED " + detail if failed else "all passed"))
        print("mutations: %d, caught: %d, not caught or not applied: %d" % (
            len(MUTATIONS), len(MUTATIONS) - len(missed), len(missed)))
        return 1 if (missed or failed) else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
