#!/bin/bash
# C-2 review: design 6.2 on a throwaway worktree. usage: c2_review_s62.sh <python> <repo>
# END-only freeze of test_c1_09 -> 1 failure; plus the HEAD self-read line -> 0. Nothing is pushed.
set -u
PY=$1; REPO=$2; W=$(mktemp -d)/wt; F=tests/v2_history_consume/test_c1_09_scope.py
git -C "$REPO" worktree add -q --detach "$W" de6549acb4ecea759cc771300fd0bef59dd5456a
cd "$W"; export PYTHONDONTWRITEBYTECODE=1
g() { git -c user.email=review@example.invalid -c user.name=review "$@"; }
sed -i 's/^END = None .*/END = "de6549acb4ecea759cc771300fd0bef59dd5456a"   # accepted (review b473db4); frozen when C-2 began/' $F
g commit -qam end-only; echo "[END only] $($PY -B -m unittest discover -s tests/v2_history_consume -p 'test_c1_*.py' 2>&1 | tail -1)"
sed -i 's|tree = ast.parse(C.show(REV, NEW_DIR + "test_c1_09_scope.py"))|tree = ast.parse(C.show("HEAD", NEW_DIR + "test_c1_09_scope.py"))   # HEAD: the frozen END is read as written|' $F
g commit -qam head; echo "[END + HEAD self-read] $($PY -B -m unittest discover -s tests/v2_history_consume -p 'test_c1_*.py' 2>&1 | tail -1)"
echo "[diff de6549a..] $(git diff --numstat de6549acb4ecea759cc771300fd0bef59dd5456a HEAD)"
cd /; git -C "$REPO" worktree remove --force "$W"
