# 日足買い条件切り分け：主担当再現記録

2026-10-26、6.1 Sol High。資料開始172d5d6763533f83f802b9273314fb7b9c531be3。
対象：research/buy-trigger-ablation-20261026、e14efa847e45012058957dc7332e64ad58ab85f9。

[主担当判断](../../docs/reviews/BUY_TRIGGER_ABLATION_RECEIPT_20261026.md)を参照。元REPORT/CSVを上書きしない。

## 実施

固定入力・相対配置を維持した一時コピーで実行：

```powershell
Set-Location research/buy_trigger_ablation_20261026
node run.mjs
```

Node v24.22.1 / Windows。依存は標準ライブラリ。研究e14efa8に保存されたrun/engine/specification/source_refsと、同ブランチ内の元allocationエンジン・分配金・exit_study入力・profit_target summary/month_endを使用する。市場データを取得せず、GitHub保存ソースを使う。

144セル、simulate105（主72/回帰24/合成9）、検証失敗0、月末1728、イベント560を再現。REPORT以外11ファイル中10件がGit blob一致、環境だけ差。

再生成後、研究ファイル群と本レビュー用フォルダを同じ一時ルートへ配置し、そのルートから以下を実行すると、独立の集計照合とblob比較を再現できる：

```powershell
node research/buy_trigger_ablation_review_20261026/checks.mjs
```

このスクリプトはシミュレーションを追加せず、72差/再利用72/現在順位144を検査し、同フォルダのreproduction.jsonを再生成する。元run.mjsも出力を再生成するため、一時コピーで実行する。資料ブランチだけに元研究一式が揃っているとは仮定しない。

- [reproduction.json](reproduction.json)：独立集計、全12組、主要差、Git blob、再現verification/environment。
- [expected_blobs.json](expected_blobs.json)：e14efa8の比較対象11ファイル。
- [review_metadata.json](review_metadata.json)：仕様コミットと祖先関係、追加市場状態読取1回、説明補足BA-01〜03、許可範囲。

## 解釈

通常/極端恐怖は次候補に残すが、正式採用や将来の優位を証明しない。NO_SELLとP20では現金再投入の有無により効果が異なる。追加閾値探索は区切り、次は実運用候補の文書整理のみ。

2025-01-03代理買付は、口座開始時armed初期化ではなく、前史12月の再武装後の1月2日episode消費に続く。コード・損益は不変。null型の説明と、最初の乖離への因果帰属にも限定を付けた。

F&G as-of/価格独立確認0/32/翌Open数量と事後売却ゲート/分配・資金時刻/終端依存/OOSなしを維持。本番変更・起動・実送信なし。
