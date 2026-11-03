#!/bin/bash
# R-01 probe (scope-range freeze review, 2026-11-03). Read-only for the source repository: everything happens in a
# throw-away clone under a temporary directory, and nothing is pushed.
#
# usage: r01_chain_after_freeze_probe.sh <path of a full-history clone> <commit under test> [python]
#
# It plays the next stage exactly as the result document tells it to (END = None in test_sc_03_scope.py becomes the
# accepted final commit, one line) and adds two broken range tests at HEAD: one whose START leaves a gap, and a second
# open range (END = None). The chain test (test_sc_02_chain.py) must then FAIL. Exit 0 = the chain test fails as it
# should (fixed); exit 1 = the chain test still passes (R-01 present); exit 2 = setup problem.
set -u
SRC=$1; REV=$2; PY=${3:-python3}
ACCEPTED=dda7eb706637adc5f6dd37513e4b6ca360fde2ba
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
git clone -q --no-local "$SRC" "$TMP/r" || exit 2
cd "$TMP/r" || exit 2
git -c advice.detachedHead=false checkout -q "$REV" || exit 2
sed -i "s/^END = None .*/END = \"$ACCEPTED\"/" tests/v2_scope_chain/test_sc_03_scope.py
grep -q "^END = \"$ACCEPTED\"" tests/v2_scope_chain/test_sc_03_scope.py || exit 2
mkdir -p tests/v2_next
printf 'import unittest\nSTART = "584b406ad8707dab1ccf1c77e209f870ade234f4"\nEND = None\n\n\nclass FilesChanged(unittest.TestCase):\n    def test_x(self):\n        pass\n' > tests/v2_next/test_n9_scope.py
printf 'import unittest\nSTART = "0000000000000000000000000000000000000000"\nEND = None\n\n\nclass FilesChanged(unittest.TestCase):\n    def test_x(self):\n        pass\n' > tests/v2_next/test_n8_scope.py
git add -A && git -c user.name=probe -c user.email=probe@invalid commit -qm "probe: next stage with a broken chain" || exit 2
echo "judge at the committed HEAD:"
PYTHONDONTWRITEBYTECODE=1 "$PY" -B - <<'PYEOF'
import sys
sys.path.insert(0, "tests/v2_scope_chain")
import sc_helpers as C
rows = C.range_tests("HEAD")
print("  range tests found:", len(rows))
print("  problems:", C.judge_chain(rows, C.is_ancestor, "HEAD", "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"))
PYEOF
PYTHONDONTWRITEBYTECODE=1 "$PY" -B -m unittest discover -s tests/v2_scope_chain -p "test_sc_02_chain.py" > "$TMP/out.txt" 2>&1
rc=$?
tail -3 "$TMP/out.txt"
if [ $rc -eq 0 ]; then echo "R-01 PRESENT: the chain test passes on a broken chain at HEAD"; exit 1; fi
echo "R-01 FIXED: the chain test rejects the broken chain at HEAD"; exit 0
