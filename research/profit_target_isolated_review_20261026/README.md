# 利確幅216セル：主担当再現記録

2026-10-26、6.1 Sol High。資料開始e31691cd6a16457a47f63076912ad52bac058e8e。
対象研究：research/profit-target-isolated-20261026、77bb44f0a043b0c9867ccbd2ea9d3013002bbd47。

[受領・判断](../../docs/reviews/PROFIT_TARGET_ISOLATED_RECEIPT_20261026.md)と[次の限定依頼](../../docs/tasks/BUY_TRIGGER_ABLATION_SONNET55_REQUEST.md)を参照。

## 再現

元研究の相対配置とファイルを維持し、保存版の次のスクリプトをそのまま実行した。

```powershell
Set-Location research/profit_target_isolated_20261026
node run.mjs
```

実行環境：Node v24.22.1 / Windows。入力取得はGitHub保存資料の取得のみで、市場API・Discord/Sheetsは使っていない。前提ファイルは対象研究のsource_refs.jsonとrun.mjsが示す37a14c0のengine/run/summary/month_end、SOXL_exit_study_20261023の入力/summary/sensitivity、分配金、および当該研究に保存済みのH2訂正参照CSV。相対パス・SHAを維持する。再現スクリプトは対象フォルダの出力を再生成するため、一時作業コピーで実行する。

- [reproduction.json](reproduction.json)：再生成したverification、実行環境、11ファイルのGit blob比較、静的に確認した実行内訳。
- [summary_checks.json](summary_checks.json)：summaryから別途抽出した12組の主要指標と比較条件。
- 元REPORT/CSV/コードは元研究コミットに保存済みのため重複保存しない。

検証失敗0。REPORT以外11ファイル中10件がGit blob一致、environmentだけ環境差。216評価セルとsimulate168実行（主108、検算36、H2キャッシュ24）は別概念。H2参照のstart/fg_delay/Rキーは24個であり、実行数はコード構造とこの件数から確認した。呼出しの動的計測ログを作成したわけではない。

## 判断と限界

P60 R25はP20 R25を12組すべてで下回り、次の主候補にしない。売却なしを保持し、利確幅追加探索は終了。P20_ONLY R25/R100を固定して買い条件を切り分ける依頼を準備したが、その新研究はまだ実行していない。

再現一致は市場での実約定・先読みの解消・将来の優位を証明しない。F&G取得可能時刻未検証、翌Open代理数量/事後2%ゲート、入力品質/独立価格確認、終端依存、既知期間への当てはめ、仕様固定時系列の独立確認限界を維持。元252全体の再実行、本番変更・起動・実送信はしていない。
