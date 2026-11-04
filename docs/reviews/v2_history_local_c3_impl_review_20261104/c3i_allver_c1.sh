#!/bin/bash
S=/tmp/claude-0/-home-claude/fef4c33c-eb89-5c04-ae9b-86701a1a2728/scratchpad
cd $S/clean; export PYTHONDONTWRITEBYTECODE=1
for PY in /root/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/bin/python3.10 /usr/bin/python3.11 /usr/bin/python3.12 /usr/local/bin/python3.13; do
  v=$($PY -c 'import platform;print(platform.python_version())')
  out=$($PY -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_consume -p "test_c1_*.py" 2>&1); rc=$?
  echo "$v v2_history_consume rc=$rc $(echo "$out" | grep -E '^Ran ' | tail -1) | $(echo "$out" | grep -E '^(OK|FAILED)' | tail -1)"
done > $S/run_c1.log
