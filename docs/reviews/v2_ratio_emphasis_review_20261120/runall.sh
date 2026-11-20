#!/bin/bash
# usage: runall.sh <python> <repo>   (every tests/<dir>, pattern test_*.py)
PY=$1; REPO=$2; FAIL=0; TOTAL=0
cd "$REPO" || exit 9
export PYTHONDONTWRITEBYTECODE=1
for d in $(ls tests); do
  [ -d tests/$d ] || continue
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/$d -p "test_*.py" 2>&1); rc=$?
  n=$(echo "$out" | grep -E "^Ran " | tail -1 | awk '{print $2}'); res=$(echo "$out" | grep -E "^(OK|FAILED)" | tail -1)
  TOTAL=$((TOTAL+${n:-0})); echo "$d rc=$rc ran=$n $res"
  [ $rc -ne 0 ] && { echo "$out" | tail -30; FAIL=1; }
done; echo "TOTAL ran=$TOTAL fail=$FAIL"; exit $FAIL
