# Sonnet5.5依頼：現期間の利確幅×RSIを同一会計で切り分ける（2026-10-27）

## 目的・担当

**Claude Sonnet5.5**。6.1 Sol High選定。既存エンジンの固定パラメータ比較と台帳集計のため。新会計/注文方式の設計はしない。
最新CLAUDE/STATUS、本依頼、HISTORICAL_DAILY_DATA_RECEIPT_20261027を今回の資料開始SHAで読む。前回読んだ版を最新と扱わない。モデル実選択/消費が取得不能なら未確認/未計測。

ユーザーの「20%は低すぎるか、ORのRSIを下げるべきか」に応える。旧期間データが不足したので、今回は**既存現期間だけの感度確認**。過去相場の一般性や未使用OOSを証明しない。外部データの再取得はしない。

## 固定版

研究基点77bb44f0a043b0c9867ccbd2ea9d3013002bbd47。
research/SOXL_allocation_separation_20261026/engine.mjs
SHA256=89d766dacf0a2c480b509fded1bf07c1023522daa68f574bd1df155dafd9c239。
分配表dividends_verified.json、元入力3ファイルと費用/税/MMFは77bb44fのsource_refsどおり。エンジン/入力を無編集で使う。
既存summaryはresearch/profit_target_isolated_20261026/summary.csv。
052ee96のAdj Close約定/分配なし/区間平均IRXは使用しない。737ef35のClose wrapperも使わない。

新ブランチresearch/exit-factorial-current-20261027を77bb44fから作成可。成果はresearch/exit_factorial_current_20261027/だけ。
計算前にspecification.json/source_refs.jsonを別コミットで保存しSHAを記録。最新資料は別の固定SHAで読む。

## 68評価セル

売却ありは初回I25・売却後R25固定。通常買い/極端恐怖買いON、初回/再エントリーの市場条件・状態・前史は従来どおり。

| 要因 | 固定する値 |
|---|---|
| 利確幅 | 20%、30%、40%、60% |
| RSI併用 | なし（PROFIT_ONLY）、OR RSI>=70、OR RSI>=75、OR RSI>=80 |
| 追加対照 | NO_SELL I25だけ |
| 開始 | 2024-10-01、2025-01-02 |
| 終端 | 2026-08-10 |
| F&G | 履歴遅延0/1 |
| 約定 | NEXT_OPENだけ |

(4×4+1)×2×2=**68セル**。
24再利用：各利確幅PROFIT_ONLY R25の16、P20_OR_R75 R25の4、NO_SELL I25の4。
44新規：残るOR11候補×2開始×遅延2。
回帰照合8：P20_ONLY R25とP20_OR_R75 R25×開始2×遅延2。
**simulate総52回まで（新規44+回帰8）。** 保存24セルのうち回帰以外を説明台帳目的で再計算しない。追加の合成シミュレーション、旧48/954/216の全体再実行なし。

RSIはSOXLではなく**元エンジンのSOXX Adj Closeに対するWilder RSI**。期間/平滑化/欠測処理は元のまま。利確はD終値の株式時価÷費用込み取得原価−1（closeTargetNet=false）>=目標。ORの片方でシグナル、翌Openで元の費用後税引前2%ゲート。20%以上で売れたという意味ではない。RSI_ONLY、AND、トレーリング、部分売却、追加の閾値/比率/開始/終端/スリッページを入れない。

## 会計・時系列

baseOptsを77bb44fから引き継ぎ：initial10000、end固定、allowInitialReentry=true、dividendSchedule固定、dividendMode=issuer_exact_pay_date_proxy、mmfRate=.03、closeTargetNet=false、buffer/slippage=0。
売却なしexitMode=NONE、初回I25。整数株/費用込み原価/現金分配/税20.315%/USDJPY150固定/税後全額再投資を維持。
MMF3%と分配支払日は従来のシナリオ。実口座の税区分・利用可能資金時刻は未確認。終端清算は評価だけで損切りを実施しない。

翌価格を知った数量/事後2%ゲート、未検証F&G as-ofは診断の留保。実運用は朝確定日足→次回寄付き手動購入・目視F&G現在値。遅延0が朝観測に等しいとしない。売却の実行可能性は今回検証しない。

## 比較と成果

- summary.csv68行：候補/開始/遅延/再利用か新規/出典SHA、時価総資産、税後仮清算、元本との差、終端仮清算税・費用、実現税/売買費用/MMF・分配税後、現金/株数/原価、売買回数、売却ゲート不成立数。
- profit_effects.csv12行：RSIなしの30/40/60各々−20を開始/遅延ごとに記述（既存値だけ）。
- rsi_effects.csv48行：各利確幅で70/75/80−RSIなしを開始/遅延ごとに比較。開始間で資産を合計しない。
- interaction_effects.csv36行：(各30/40/60でRSI追加差)−(20で同じRSI追加差)。開始/遅延ごと。交互作用はこの固定入力内の差分で、統計的有意性を意味しない。
- ledger_new_and_regression.csvは新規44+回帰8のメモリからだけ作成。D/約定日、Dの利益率、SOXX RSI、profit_hit/rsi_hit、両方/利益のみ/RSIのみ、FILLED/BLOCKED、実際の利益率/税/費用を区別。独立した約定と同じ経路内の繰返しを混同しない。
- counts of RSI-only/both/profit-only are path descriptions, not unique causal contributions. Pending sale overwritten/blocked等は元エンジンの状態を保ち、説明に必要な情報が取れなければUNOBSERVEDとする。計算を変える計装はしない。
- 説明経路は最大6経路を既存の52実行から選ぶ。選択理由を明示し、全体表も残す。結果後に追加実行しない。
- verification.json/environment.json/REPORT.md。入力/エンジン/仕様SHA確認、回帰8の金額1e-6・日付/数量一致、全新規の会計恒等式/現金非負/整数株/原価/分配二重計上なし/売却2%ゲート、Dと次セッション約定、fg_usedの遅延整合。68評価・新規44・実行52を別記。
- 主報告は税後仮清算中心、時価併記。時価も実現益等の税控除済み。「全く無税」「利益額=総資産」と書かない。

判断順序：利確幅だけ→RSIだけ→組合せの変化。目標を上げたらRSIを下げるべきという結論を先に置かない。既存R25の優位を全比率へ一般化しない。各条件で最良値は示せるが、勝数/平均順位/最大DDを目的にしない。主目的は最終総資産最大化。

## 終了

68評価の保存・説明で終了。データ取得/ネットワーク再試行0。新閾値の自動追加0。今回比較で現期間の出口感度確認を区切り、結果から正式採用や追加探索を自動開始しない。
旧期間は日足/分配支払日/分割単位不足のため保留したまま。既知期間の感度確認を別期間の検証として報告しない。

損切りなし・税後利益全額再投資・最終総資産最大化/DD減点なしを維持。main31144d9停止、候補920e695、既存承認5項目維持。既存コード/通知設定/Actions/cron/停止条件/Discord・Sheets/認証/口座は変更しない。戦略採用/本番反映/解除/起動/送信は行わない。
