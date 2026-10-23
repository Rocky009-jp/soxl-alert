# SOXL Alert — Ver.2 workspace

SOXLの売買候補を日本時間の朝に確認するための通知アラートツール。既存ツールの不具合修正と、検証に基づくアラート基準の改善を進める。

このブランチは資料・検証資産の保存用。既存の本番コード `main.py` と定期実行設定は変更していない。

## 最初に読む資料

1. [現在地と次の作業](docs/STATUS.md)
2. [Ver.2ロードマップ・工数・トークン計画](docs/ROADMAP.md)
3. [Claude向けレビュー入口](docs/CLAUDE_REVIEW.md)

## 検証成果物

| 検証 | レポート | コード・入力・台帳 |
|---|---|---|
| Phase A監査 | [監査レポート](research/SOXL_audit_20261023/SOXL_Audit_Report_2026-10-23.md) | [一式](research/SOXL_audit_20261023/) |
| 初回参加×再エントリー比率 | [比較レポート](research/SOXL_initial_trend_20261023/SOXL_Initial_Trend_Comparison_2026-10-23.md) | [一式](research/SOXL_initial_trend_20261023/) |
| 利確条件の変更 | [比較レポート](research/SOXL_exit_study_20261023/SOXL_Exit_Comparison_2026-10-23.md) | [一式](research/SOXL_exit_study_20261023/) |

原引き継ぎ資料は [handoff_original.md](research/SOXL_audit_20261023/handoff_original.md)。過去の記録なので、現在地は `docs/STATUS.md` を優先する。移行対象のサイズ・SHA-256は [MIGRATION_MANIFEST.json](research/MIGRATION_MANIFEST.json) に保存。

## 検証の再実行

Node.jsのES modulesを使用。これらの研究スクリプトはネット接続・認証情報・Discord送信を必要とせず、同梱入力から再計算する。リポジトリルートから実行する。

```sh
node research/SOXL_audit_20261023/run_audit.mjs
node research/SOXL_initial_trend_20261023/run_comparison.mjs
node research/SOXL_exit_study_20261023/run_exit_study.mjs
```

各ディレクトリの `results/` へ新しい結果を出す。保存済みの元結果を上書きしない。研究エンジンには翌寄付き価格による判定など実運用へそのまま移せない仮定があるため、研究コードを本番の売買判断として直接実行しない。

## 作業管理

今後の作業成果と判断はGitHubを正本としてコミットする。ローカルにしかない引き継ぎ情報を作らない。既存本番コードや通知設定の変更・切替は別途具体的な差分を示して承認を受ける。秘密値・実口座の個人情報は公開リポジトリへ保存しない。


## 工程0：現行ツールの初期診断

[診断書](research/phase0_20261023/PHASE0_DIAGNOSIS.md)と[最小修正案](research/phase0_20261023/MINIMAL_FIX_PROPOSAL.md)、[14項目の再現結果](research/phase0_20261023/reproduction_results.json)を追加しました。実ログと合成入力の再現を区別しています。修正は未適用。[Claude Sonnet 5.5向け依頼文](docs/reviews/PHASE0_SONNET55_REQUEST.md)と[モデル分担](docs/MODEL_POLICY.md)も参照してください。
