#!/bin/bash
# S4D-18: the "next stage" simulation on a throwaway worktree of the tested commit. Nothing is pushed.
# usage: next_stage_sim.sh <python> <repo> <tested-sha>
#  [A] the tested commit as it is (the open S4-D range)
#  [B] (1) only: END of the S4-D range test frozen to the tested commit -> the chain test of test_sc_02 fails (recorded, expected)
#  [C] (1) + (2): plus a minimal open range test of the next stage (START = the tested commit, END = None) -> all pass
set -u
PY=$1; REPO=$2; T=$3; W=$(mktemp -d)/wt
git -C "$REPO" worktree add -q --detach "$W" "$T"
cd "$W"; export PYTHONDONTWRITEBYTECODE=1
g() { git -c user.email=sim@example.invalid -c user.name=sim "$@"; }
run() { for d in v2_scope_chain:test_*.py v2_history_maintain:test_c4_09_scope.py v2_daily_run:test_s4a_09_scope.py v2_notify:test_s4b_09_scope.py v2_git_store:test_s4c_09_scope.py v2_inputs:test_s4d_09_scope.py; do
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/${d%%:*} -p "${d#*:}" 2>&1); echo "  ${d%%:*}: $(echo "$out" | grep -E '^Ran ' | tail -1) | $(echo "$out" | tail -1)"; done; }
echo "[A] tested commit $T"; run
python3 - "$T" <<'PY'
import re, sys
p = "tests/v2_inputs/test_s4d_09_scope.py"
s = open(p).read()
new, n = re.subn(r'^END = None .*$', 'END = "%s"   # simulation: frozen by the next stage' % sys.argv[1], s, flags=re.M)
assert n == 1
open(p, "w").write(new)
PY
git diff --stat | tail -1; g commit -qam "sim: freeze END (one line)"
echo "[B] END frozen, no open range (expected: test_sc_02 chain test fails)"; run
mkdir -p tests/v2_next_stage
cat > tests/v2_next_stage/test_n_01_scope.py <<PY
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
import sc_helpers as C
START = "$T"
END = None
REV = END or "HEAD"
class FilesChanged(unittest.TestCase):
    def test_start_is_an_ancestor(self):
        self.assertTrue(C.is_ancestor(START, REV))
PY
git add -A; g commit -qm "sim: open range of the next stage"
echo "[C] END frozen + minimal open range of the next stage"; run
cd /; git -C "$REPO" worktree remove --force "$W"
