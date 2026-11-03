#!/bin/bash
# usage: runall.sh <python> <repo>
PY=$1; R=$2; cd $R
export PYTHONDONTWRITEBYTECODE=1
for spec in "v2_core:test_*.py" "v2_persistence:test_*.py" "v2_persistence_local:test_*.py" "v2_recovery:test_*.py" "v2_history:test_*.py" "v2_history_ops:test_*.py" "v2_history_restart:test_r3_*.py" "v2_history_restore:test_r4_*.py" "v2_history_diagnose:test_d5_*.py" "v2_history_adopt:test_a5_*.py" "v2_scope_chain:test_sc_*.py"; do
  d=${spec%%:*}; p=${spec#*:}
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/$d -p "$p" 2>&1); rc=$?
  echo "$d rc=$rc $(echo "$out" | grep -E '^Ran ') $(echo "$out" | tail -1)"
done
