# S4-B 第2版（36b2cb1）再レビューの確認材料（2026-11-05）

- s4bv2_probe.py：第2版§3のERRORの鍵の規則を、試行の差分（6ad609fに当てたもの）のcompose・outboxの上に組み直したモデル（実装ではない）。X1'・X2'（N-01の解消）、X6（R-03）。
- s4bv2_probe_out_py3.12.txt・py3.13.txt：出力（版の行を除き同じ）。
- refcheck.sh・refs_protected92.txt・refs_start.txt・refs_postpush.txt：保護92参照の照合。

実行例：PYTHONDONTWRITEBYTECODE=1 python3.13 -B s4bv2_probe.py <6ad609f＋試行の差分の作業ツリー>
