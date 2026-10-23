# Claude作業・レビューの入口

まずリポジトリルートの **[CLAUDE.md](../CLAUDE.md)** を読んでください。目的、固定条件、権限、証拠の扱い、モデル選定、成果物管理、報告形式をまとめた共通指示です。

- [新しい会話へ貼り付ける入口プロンプト](CLAUDE_START_PROMPT.md)
- [現在地](STATUS.md)
- [モデル分担ルール](MODEL_POLICY.md)
- [工程・完了条件・予算](ROADMAP.md)
- [今後の個別依頼テンプレート](CLAUDE_TASK_TEMPLATE.md)

## 今回の依頼

指定モデルは **Sonnet 5.5**。6.1 Sol Highが、固定コード・実ログ・合成入力の再現・限定した修正案の照合に適すると判断しています。

[工程0レビュー依頼](reviews/PHASE0_SONNET55_REQUEST.md)に従い、[診断書](../research/phase0_20261023/PHASE0_DIAGNOSIS.md)、修正案、再現コード、結果JSON、実ログ抜粋を確認してください。これはレビュー依頼であり、コード変更や本番送信の依頼ではありません。

取得元の欠損原因と実際の配信状況は未確認です。14項目は不具合の挙動確認であり、修正済みの受入合格とは扱いません。取引仕様や戦略の採否は今回の範囲に含めず、重大な判断が必要なら6.1 Sol Highへ戻してください。

## 研究工程で必要な場合に読む資料

- [Phase A監査](../research/SOXL_audit_20261023/SOXL_Audit_Report_2026-10-23.md)
- [初回参加・再エントリー比較](../research/SOXL_initial_trend_20261023/SOXL_Initial_Trend_Comparison_2026-10-23.md)
- [利確条件比較](../research/SOXL_exit_study_20261023/SOXL_Exit_Comparison_2026-10-23.md)

工程0レビューで大量のCSVや過去の全検証を一括で読み直す必要はありません。対象コミットを記録し、必要な根拠へ進んでください。レビュー結果は共有後に `docs/reviews/` へ保存し、指摘への対応と `STATUS.md` を更新します。Claudeへの自動送信・依頼は行っていません。
