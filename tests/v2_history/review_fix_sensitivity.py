"""Sensitivity check of the R-01 / R-02 fixes: revert ONE fix in a temporary copy of the tree and run
tests/v2_history/test_h15_review_fix.py there; the run must fail. Not part of the product, not a unittest
(run by hand: <python> -B tests/v2_history/review_fix_sensitivity.py [ids]). The real tree is never modified.
A revert marked EQUIVALENT is listed with its reason and not counted as detected.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

REVERTS = [
    ("F01", "restore.py",
     [("not all(is_int(s) for s in listed) or ", "")], "R-01: superseded_seqs entries not required to be exact ints"),
    ("F02", "migration.py",
     [("not is_int(source[\"schema_version\"]) or ", "")], "R-01: source.schema_version not required to be an exact int"),
    ("F03", "migration.py",
     [("            or not is_int(source[\"head_seq\"]) or source[\"head_seq\"] != head[\"seq\"]", "            or source[\"head_seq\"] != head[\"seq\"]")],
     "R-01: source.head_seq not required to be an exact int"),
    ("F04", "migration.py",
     [("not is_int(origin[\"source_head_seq\"]) or ", "")],
     "EQUIVALENT: origin.source_head_seq not required to be an exact int (the recomputed S3-A resolution_hash, which contains the value, "
     "already refuses True / 1.0 with the same rule `origin`; the explicit check is defence in depth)"),
    ("F05", "values.py", [("copy.deepcopy(self._view.get(\"head_seq\"))", "self._view.get(\"head_seq\")")],
     "R-02: History.head_seq shares the nested value"),
    ("F06", "values.py", [("copy.deepcopy(self._view.get(\"head_hash\"))", "self._view.get(\"head_hash\")")],
     "R-02: History.head_hash shares the nested value"),
    ("F07", "values.py", [("copy.deepcopy(self._view.get(\"schema_version\"))", "self._view.get(\"schema_version\")")],
     "R-02: History.schema_version shares the nested value"),
    ("F08", "migrate.py", [("copy.deepcopy(self._view[\"plan_hash\"])", "self._view[\"plan_hash\"]")],
     "R-02: MigrationPlan.plan_hash shares the nested value"),
]


def main():
    only = set(sys.argv[1:])
    detected, equivalent, lost, not_run = [], [], [], []
    for rid, fname, pairs, what in REVERTS:
        if only and rid not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="v2s3b1_fix_")
        try:
            for d in ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "tests/v2_history", "tests/v2_recovery",
                      "tests/v2_persistence"):
                shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__", ".git"))
            target = os.path.join(tmp, "v2_history", fname)
            with open(target, encoding="utf-8") as f:
                text = f.read()
            if any(text.count(old) != 1 for old, _new in pairs):
                print(rid, "NOT RUN (patch does not apply once) -", what)
                not_run.append(rid)
                continue
            for old, new in pairs:
                text = text.replace(old, new)
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
            r = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/v2_history",
                                "-p", "test_h15_review_fix.py"], cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
            if r.returncode != 0:
                print(rid, "DETECTED -", what, "|", r.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
                detected.append(rid)
            else:
                print(rid, "NOT DETECTED -", what)
                (equivalent if "EQUIVALENT" in what else lost).append(rid)
        finally:
            shutil.rmtree(tmp, True)
    print("detected:", len(detected), detected)
    print("equivalent (not counted as detected):", equivalent or "none")
    print("not run:", not_run or "none")
    print("undetected:", lost or "none")
    return 1 if (lost or not_run) else 0


if __name__ == "__main__":
    sys.exit(main())
