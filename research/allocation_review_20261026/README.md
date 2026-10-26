# 配分分離研究の主担当再実行記録
2026-10-26（日本時間）

研究対象37a14c02517b6357bcaeecb6f0a023bfc8a3696a。資料開始359216b。
[判断全文](../../docs/reviews/ALLOCATION_SEPARATION_RESPONSE_20261026.md)。

保存されたengine.mjs/run.mjsを変更せずNode v24.22.1 / win32で再実行した。これは同じアルゴリズムの再現確認であり、別実装での戦略全体検証や市場価格の正しさの保証ではない。集計のグループ首位・R比較は別途CSVを読み算術照合した。

- 主試算252件、月末3,024行、失敗0。
- 旧108＋新216の324追加実行による216組比較、保存集計54・遅延感度18・台帳18の一致。
- NO_SELLのR不変108追加実行を主試算へ混ぜない。
- 52ファイルが対象コミットのGit blobと一致。environmentだけはNode/OS/時間が異なる。
- 同一YahooキャッシュとのOHLC各465日照合、欠落0・相対差0.005%超0。独立ベンダー照合ではない。最大相対差は約5.71e-8。
- F&G as-of、次始値を見た注文、事後売却ゲート、MMF/分配/税/受渡の研究仮定は未解消。
- 市場データの新規取得、実注文、Actions/Discord/Sheetsは実施しなかった。GitHubから固定コード・資料を読み取った通信と、計算のオフライン実行は区別する。

## ファイル

reproduction_verification.jsonは同じrun.mjsの再実行出力。environment.jsonは今回環境。
artifact_hash_checks.jsonは比較した53ファイルとGit blob。
summary_checks.jsonは12条件の首位/基準資産とR集計。
cached_price_check.jsonは保存Yahoo応答との照合と8日アンカー。
verify_saved_results.mjsはこの記録に対する再確認コード。portable_check_result.jsonは実行結果。

## 再現手順

研究37a14c0のチェックアウトを用意し、その研究フォルダで node run.mjs を実行する。
この資料ブランチの本フォルダを別に保存し、次で照合できる：

```text
node /path/to/allocation_review_20261026/verify_saved_results.mjs /path/to/research-checkout
```

対象研究コード・入力は研究ブランチに存在し、この資料ブランチへ複製していない。
キャッシュ根拠はresearch/SOXL_audit_20261023/evidence/yahoo_SOXL.json、
Git blob 7dbe382acfd5b85c1cd19ec780363e111850aa80。
比較は保存データの算術で、新しい価格取得や実約定評価ではない。
