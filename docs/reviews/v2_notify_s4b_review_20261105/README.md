# S4-B 設計・依頼書レビューの確認材料（2026-11-05）

対象：docs/v2-notify-s4b-20261105 の e196a68。6ad609f の一時の作業ツリーに試行の差分（V2_NOTIFY_S4B_TRIAL_20261105.diff）を
`git apply` で当て、pushしないローカルコミットにしたものの上で動かした。製品コードではない。

| ファイル | 中身 |
|---|---|
| runall.sh | 既存16スイートの実行（S4-Aの結果の補助と同じもの）。`bash runall.sh <python> <作業ツリー>` |
| trial_runall_py3.12.log・py3.13.log | 上の出力。16スイート計2349件 |
| end_only_scope_chain_py3.13.log | 仮置きの開いた範囲を外し、ENDだけ固定したコミットでの範囲の鎖（2件失敗） |
| s4bx_probe.py | X1・X2 ERRORの鍵（N-01）、X3 同じDの2回目のHALT（P-01）、X4 空の意図（P-06）、X5 outbox＝履歴のroot（P-09） |
| s4bx_x3b.py | X3の詳細（2回目に消費した日と、1回目が無い場合との比較） |
| s4bx_late.py | 次の寄付きの後の判定あり（PREPARED）に注記が入らないこと（P-07） |
| s4bx_probes_out_py3.12.txt・py3.13.txt | 上の3本の出力（版の行を除き同じ） |
| s4bx_race.py・s4bx_race_out_py3.13.txt | T-3の再確認（2プロセス40回、4プロセス20回） |
| refcheck.sh・refs_protected92.txt | 依頼書§7の92参照の照合 |
| refs_start.txt・refs_postpush.txt | 開始時・本記録のpush後の `git ls-remote` |

実行例：`PYTHONDONTWRITEBYTECODE=1 python3.13 -B s4bx_probe.py <作業ツリー>`（共有フォルダ上ではnoexecなので、python に渡して動かす）。
