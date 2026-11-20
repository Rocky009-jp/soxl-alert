#!/bin/bash
# usage: next_stage_sim.sh <python> <repo> <tested rev>: freeze only END -> the chain tests fail; freeze END and add the next open range -> they pass.
PY="$1"; REPO="$2"; REV="$3"
export PYTHONDONTWRITEBYTECODE=1
W=$(mktemp -u -d "${TMPDIR:-/tmp}/nextsim_XXXX")
git -C "$REPO" worktree add --detach "$W" "$REV" -q || exit 9
cd "$W"
G="git -c user.name=sim -c user.email=sim@example.invalid"
run() { "$PY" -B -m unittest discover -s "$1" -p "$2" 2>&1 | grep -E "^(FAIL|ERROR):|^Ran |^OK|^FAILED"; }
sed -i "s/^END = None .*/END = \"$REV\"   # frozen/" tests/v2_ratio/test_ratio_02_scope.py
grep -n "^END" tests/v2_ratio/test_ratio_02_scope.py
$G commit -qam "freeze END only"
echo "--- (a) END frozen, no next open range"
echo "[scope_chain]"; run tests/v2_scope_chain "test_*.py"
echo "[ratio_02]"; run tests/v2_ratio "test_ratio_02*.py"
mkdir -p tests/v2_next
cat > tests/v2_next/test_n_09_scope.py <<PYEOF
START = "$REV"
END = None
class FilesChanged(object):
    pass
PYEOF
$G add tests/v2_next; $G commit -qm "next stage open range"
echo "--- (b) END frozen and the next open range added"
echo "[scope_chain]"; run tests/v2_scope_chain "test_*.py"
echo "[ratio_02]"; run tests/v2_ratio "test_ratio_02*.py"
cd "$REPO"; git worktree remove --force "$W"
