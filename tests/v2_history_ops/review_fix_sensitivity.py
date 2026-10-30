"""Limited defect injection for the S3-B-2 review fixes (R-01, R-02): put each fix back one at a time into a copy of
the tree, run the v2_history_ops suite there and require it to fail. Not a unittest (run by hand:
<python> -B tests/v2_history_ops/review_fix_sensitivity.py [ids]). The real tree is never modified.
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

F = "v2_recovery/facts.py"
MUTATIONS = [
    ("F01", "v2_history_ops/batch.py",
     '        return copy.deepcopy(self._view["batch_hash"])        # a value from from_dict may be a dict or a list',
     '        return self._view["batch_hash"]',
     "R-01 batch_hash returns the stored object"),
    ("F02", F, '    def __setattr__(self, name, value):\n        raise AttributeError("FixedApply is immutable")',
     '    def __setattr__(self, name, value):\n        object.__setattr__(self, name, value)',
     "R-02 FixedApply attributes can be assigned"),
    ("F03", F, '    def __delattr__(self, name):\n        raise AttributeError("FixedApply is immutable")',
     '    def __delattr__(self, name):\n        object.__delattr__(self, name)',
     "R-02 FixedApply attributes can be deleted"),
    ("F04", F, '    @property\n    def context(self):\n        return copy.deepcopy(self._context)',
     '    @property\n    def context(self):\n        return self._context',
     "R-02 FixedApply.context shares the stored list"),
    ("F05", F, '        return SessionList(self._sessions)',
     '        return globals().setdefault("_SHARED", {}).setdefault(self._seq, SessionList(self._sessions))',
     "R-02 FixedApply.stored_sessions shares one SessionList"),
    ("F06", F, '    def __setattr__(self, name, value):\n        raise AttributeError("FixedFacts is immutable")',
     '    def __setattr__(self, name, value):\n        object.__setattr__(self, name, value)',
     "R-02 FixedFacts attributes can be assigned"),
    ("F07", F, '    def __delattr__(self, name):\n        raise AttributeError("FixedFacts is immutable")',
     '    def __delattr__(self, name):\n        object.__delattr__(self, name)',
     "R-02 FixedFacts attributes can be deleted"),
    ("F08", F, '("_applies", tuple(fixed))', '("_applies", list(fixed))', "R-02 FixedFacts.applies is a shared list"),
    ("F09", F, '    by_seq = property(lambda self: MappingProxyType(self._by_seq))',
     '    by_seq = property(lambda self: self._by_seq)', "R-02 FixedFacts.by_seq is the shared dict"),
    ("F10", F, '("_apply_days", days)', '("_apply_days", set(days))', "R-02 FixedFacts.apply_days is a shared set"),
    ("F11", F, '("_fixed_fps", frozenset(ap.fingerprint for ap in fixed))',
     '("_fixed_fps", set(ap.fingerprint for ap in fixed))', "R-02 FixedFacts.fixed_fps is a shared set"),
    ("F12", F, '    declares = property(lambda self: copy.deepcopy(self._declares))',
     '    declares = property(lambda self: self._declares)', "R-02 FixedFacts.declares is the shared list"),
    ("F13", F, '    boundaries = property(lambda self: copy.deepcopy(self._boundaries))',
     '    boundaries = property(lambda self: self._boundaries)', "R-02 FixedFacts.boundaries is the shared list"),
]


def main():
    only = set(sys.argv[1:])
    lost, detected_n = [], 0
    for mid, rel, old, new, what in MUTATIONS:
        if only and mid not in only:
            continue
        tmp = tempfile.mkdtemp(prefix="v2s3b2fix_mut_")
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
                lost.append(mid)
        finally:
            shutil.rmtree(tmp, True)
    print("detected:", detected_n)
    print("undetected or broken setups:", lost or "none")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
