"""Writes data/baseline_evaluate_day_1a54a85.json: what the code BEFORE the transition extraction returned.

Run once, from the repository root, on a checkout of 1a54a85 (v2_core/ untouched):

    python3 -B tests/v2_core/gen_baseline_evaluate_day.py

The file records outputs of the pre-extraction product code. It is a before/after comparison base, not an
oracle of correct behaviour: correctness tests (A1, A3-A5, ...) never take expected values from product code.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import v2_transition_cases as tc  # noqa: E402

OUT = os.path.join(HERE, "data", "baseline_evaluate_day_1a54a85.json")
EXPECTED_SHA = "1a54a8573023af9490017b02a8b6458f061031c7"


def git(*args):
    return subprocess.run(("git",) + args, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main():
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--", "v2_core")
    if head != EXPECTED_SHA or dirty:
        sys.exit("refusing to write: HEAD is %s (need %s) or v2_core/ is modified" % (head, EXPECTED_SHA))
    cases = {}
    for cid, _args, res in tc.iter_all():
        assert cid not in cases, cid
        cases[cid] = tc.to_plain(res)
    doc = {
        "generated_from_sha": head,
        "generator": "tests/v2_core/gen_baseline_evaluate_day.py",
        "note": "outputs of the code before the transition extraction; a before/after base, not a correctness oracle",
        "case_count": len(cases),
        "cases": cases,
    }
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote %s: %d cases, %d bytes, sha256 %s" % (
        os.path.relpath(OUT, ROOT), len(cases), len(text), hashlib.sha256(text.encode()).hexdigest()))


if __name__ == "__main__":
    main()
