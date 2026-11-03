#!/bin/bash
S=${S:?set S to the folder that holds runall.sh}
# usage: S=<folder of implementation/c2_publish_20261103/runall.sh> c2i_allver.sh  (clones /home/claude/clone10..13 at the commit under test)
for v in 10 11 12 13; do
  if [ $v = 10 ]; then PY=/root/.local/share/uv/python/cpython-3.10-linux-x86_64-gnu/bin/python3.10; else PY=python3.$v; fi
  echo "== py3.$v $($PY --version)"; git -C /home/claude/clone$v rev-parse HEAD
  bash $S/runall.sh $PY /home/claude/clone$v v2_history_consume:test_c1_*.py v2_history_publish:test_c2_*.py
done
