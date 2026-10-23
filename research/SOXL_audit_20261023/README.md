# SOXL監査パッケージ

まず SOXL_Audit_Report_2026-10-23.md を読んでください。全数値は診断用で、分足/実約定の成績ではありません。

再実行: Node.js 22以降で node run_audit.mjs

外部依存なし・ネット接続不要。同梱data/から計算しresults/に書きます。元データと旧値の再現・30テストを含みます。外部発注・GitHub/Discord書込機能はありません。

legacy_ledger_*.csv が旧値復元、ledger_*.csv が記載ルールの診断、issuer_dividend_ledger_*.csv が分配額/支払日修正版です。requested_timing_comparison.csv は未取得条件を空欄のまま保持します。
