#!/bin/bash
S=/tmp/claude-0/-home-claude/fef4c33c-eb89-5c04-ae9b-86701a1a2728/scratchpad
for PY in /root/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/bin/python3.10 /usr/bin/python3.11 /usr/bin/python3.12 /usr/local/bin/python3.13; do
  v=$($PY -c 'import platform;print(platform.python_version())')
  echo "== $v" > $S/run_$v.log
  bash $S/runall.sh $PY $S/clean v2_history_publish:test_c2_*.py v2_history_local:test_c3_*.py >> $S/run_$v.log 2>&1
done
echo done > $S/runall.done
