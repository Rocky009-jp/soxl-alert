#!/bin/bash
# usage: runall.sh <python> <repo> [extra suites...]
# The 15 existing suites (2253 tests: core 197, persistence 170, S2 113, S3-A 176, B-1 230, B-2 173, B-3 109, B-4 165,
# B-5a 131, B-5b 170, range chain 34, C-1 112, C-2 150, C-3 139, C-4 184) and the S4-A suite. Bytecode is never written.
PY=$1; REPO=$2; shift 2
cd "$REPO" || exit 9
export PYTHONDONTWRITEBYTECODE=1
for spec in v2_core:test_*.py v2_persistence:test_*.py v2_persistence_local:test_*.py v2_recovery:test_*.py v2_history:test_*.py v2_history_ops:test_*.py v2_history_restart:test_*.py v2_history_restore:test_*.py v2_history_diagnose:test_*.py v2_history_adopt:test_*.py v2_scope_chain:test_*.py v2_history_consume:test_*.py v2_history_publish:test_*.py v2_history_local:test_*.py v2_history_maintain:test_c4_*.py v2_daily_run:test_s4a_*.py "$@"; do
  d=${spec%%:*}; p=${spec#*:}
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/$d -p "$p" 2>&1); rc=$?
  last=$(echo "$out" | grep -E "^Ran " | tail -1); res=$(echo "$out" | grep -E "^(OK|FAILED)" | tail -1)
  echo "$d rc=$rc $last | $res"
  [ $rc -ne 0 ] && echo "$out" | tail -30
done
