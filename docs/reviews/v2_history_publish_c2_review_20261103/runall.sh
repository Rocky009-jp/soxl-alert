#!/bin/bash
# usage: runall.sh <python> <repo> <outdir>
PY=$1; REPO=$2; OUT=$3; mkdir -p $OUT
cd $REPO
export PYTHONDONTWRITEBYTECODE=1
for spec in v2_core:test_*.py v2_persistence:test_*.py v2_persistence_local:test_*.py v2_recovery:test_*.py v2_history:test_*.py v2_history_ops:test_*.py v2_history_restart:test_*.py v2_history_restore:test_*.py v2_history_diagnose:test_*.py v2_history_adopt:test_*.py v2_scope_chain:test_*.py v2_history_consume:test_c1_*.py v2_history_publish:test_c2_*.py; do
  d=${spec%%:*}; p=${spec#*:}
  unshare -n -r $PY -B -W error::ResourceWarning -m unittest discover -s tests/$d -p "$p" > $OUT/$d.log 2>&1
  rc=$?
  echo "$d rc=$rc $(grep -E '^Ran ' $OUT/$d.log) $(tail -1 $OUT/$d.log)"
done
