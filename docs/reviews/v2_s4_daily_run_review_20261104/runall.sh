#!/bin/bash
# usage: runall.sh <python> <repo> [extra suites...]
# The 14 existing suites (2069 tests) and the C-4 suite. Bytecode is never written.
PY=$1; REPO=$2; shift 2
cd "$REPO" || exit 9
export PYTHONDONTWRITEBYTECODE=1
for spec in v2_core:test_*.py v2_persistence:test_*.py v2_persistence_local:test_*.py v2_recovery:test_*.py v2_history:test_*.py v2_history_ops:test_*.py v2_history_restart:test_*.py v2_history_restore:test_*.py v2_history_diagnose:test_*.py v2_history_adopt:test_*.py v2_scope_chain:test_*.py v2_history_consume:test_*.py v2_history_publish:test_*.py v2_history_local:test_*.py v2_history_maintain:test_c4_*.py "$@"; do
  d=${spec%%:*}; p=${spec#*:}
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/$d -p "$p" 2>&1); rc=$?
  last=$(echo "$out" | grep -E "^Ran " | tail -1); res=$(echo "$out" | grep -E "^(OK|FAILED)" | tail -1)
  echo "$d rc=$rc $last | $res"
  [ $rc -ne 0 ] && echo "$out" | tail -30
done
