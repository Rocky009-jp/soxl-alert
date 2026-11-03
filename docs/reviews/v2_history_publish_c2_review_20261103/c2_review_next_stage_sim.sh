#!/bin/bash
# C-2 review: the "next stage" simulation of C2-19 on a throwaway worktree. usage: c2_review_next_stage_sim.sh <python> <repo> <trial.diff>
# (1) de6549a + the trial diff, committed; (2) END of the C-2 range test frozen to (1) only -> test_sc_02 fails 2;
# (3) plus a placeholder open range test of the next stage (START = (1), END = None) -> all pass. Nothing is pushed.
set -u
PY=$1; REPO=$2; DIFF=$3; W=$(mktemp -d)/wt
git -C "$REPO" worktree add -q --detach "$W" de6549acb4ecea759cc771300fd0bef59dd5456a
cd "$W"; export PYTHONDONTWRITEBYTECODE=1
g() { git -c user.email=review@example.invalid -c user.name=review "$@"; }
git apply "$DIFF" && git add -A && g commit -qm trial; T=$(git rev-parse HEAD)
run() { for d in v2_scope_chain:test_*.py v2_history_consume:test_c1_*.py v2_history_publish:test_c2_*.py; do
  echo "  ${d%%:*}: $($PY -B -m unittest discover -s tests/${d%%:*} -p "${d#*:}" 2>&1 | tail -1)"; done; }
echo "[open C-2 range]"; run
sed -i "s/^END = None$/END = \"$T\"/" tests/v2_history_publish/test_c2_09_scope.py && g commit -qam freeze
echo "[END frozen, no open range]"; run
mkdir -p tests/v2_next_stage && sed "s/^START = .*/START = \"$T\"/; s/^END = .*/END = None/" \
  tests/v2_history_publish/test_c2_09_scope.py > tests/v2_next_stage/test_n_09_scope.py && git add -A && g commit -qm next
echo "[END frozen + placeholder open range of the next stage]"; run
cd /; git -C "$REPO" worktree remove --force "$W"
