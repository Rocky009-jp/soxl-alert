# V2 S3-B-1 採用・限定実装承認記録

日付：2026-10-29（日本時間）
状態：**D-1・D-2・D-4を採用。第2版に基づくB-1限定実装への移行をユーザーが承認。**

## 1. 承認の根拠と固定版

ユーザーの明示指示：「この3点の採用とB-1限定実装へ移行します」。
直前に示した3点は、次の一組である。

| ID | 採用内容 |
|---|---|
| D-1 | 第2版の形式とB-1の限定範囲を採用。単一履歴の監査鎖と有効親、鎖ビューと既存S1検査器への射影、移行対応表による逆検証 |
| D-2 | 復元点の下限は、移行履歴ではSCHEMA_MIGRATION自身かそれ以後、新規v2履歴ではGENESIS。有効な点だけ・直前不可・requestバッチ途中不可は両方で維持 |
| D-4 | Claude Sonnet 5.5、effort high。開始時に実設定を確認し、取得できなければ不明と記録。独断でモデルや範囲を変えない |

| 用途 | 完全SHA・blob |
|---|---|
| 実装開始点 | e68d702de7fa80f141e14b63cf88082c15493994 |
| 採用する設計・依頼書の第2版 | 361904b1618ae9f9d3a672875c437a388826c253 |
| 設計blob | 838761207b060ca8c844bf7ed0f15a9e990ad6b7 |
| 依頼blob | 61a645c086c5f62e31f29fcf662cbc76e3bb22dc |
| 第2版再レビュー | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |

- [設計書](https://github.com/Rocky009-jp/soxl-alert/blob/361904b1618ae9f9d3a672875c437a388826c253/docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md)
- [限定実装依頼書](https://github.com/Rocky009-jp/soxl-alert/blob/361904b1618ae9f9d3a672875c437a388826c253/docs/tasks/V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md)
- [再レビュー](https://github.com/Rocky009-jp/soxl-alert/blob/225b10059bdc23a677f97fc3ac7597ca73c4b00c/docs/reviews/V2_RECOVERY_S3B_V2_REREVIEW_20261029.md)

固定文書と過去のSTATUSにある「未承認」「採否待ち」は当時の記録である。今回の明示指示により、上の3点とB-1限定実装だけを承認済みに進める。過去文書は書き換えない。B-1の完成・試験合格や、実運用での新形式採用を意味しない。

## 2. 許可範囲と完了位置

B-1は、メモリ上のv2履歴値・codec・7種の検査器（復元バッチと再初期化の検査を含む）、make_history_genesis、migrated_sources、明示移行の計画・確認に限る。H-01〜H-14、依頼書の欠陥注入22種、Python4版・通信禁止・別クリーンクローンでの確認を採用する。CONSUMEとprefix採用は拒否する。

追加を許す場所は、v2_history/、tests/v2_history/、docs/implementation/V2_RECOVERY_S3B1_RESULT.mdだけ。既存パッケージ・既存試験・fixture・依存・設定・workflow・共通資料は変更しない。

B-2〜B-5、S3-C、日次処理・台帳投影、新規ACK／DECLARE・復元・再初期化の計画、公開値・v2ストア、ファイル上の移行、実解錠・復元、本番・通知・口座接続は承認対象外。D-3・D-5〜D-7の判断は後続に留保する。

結果文書を別実装ブランチへ保存・pushし、完全SHAと確認範囲を報告した時点で止める。範囲外変更や契約の矛盾が必要なら、反例・影響・最小差分案を報告し、該当変更を行わない。

## 3. 今回の記録作成

記録作成前に依頼書の25参照と、初版・初版レビュー・第2版・第2版再レビューの4参照、計29参照を完全SHAで照合し一致した。本承認記録と開始指示書だけを、新しい資料ブランチdocs/v2-recovery-s3b1-adoption-20261029へ追加する。既存29参照は変更しない。保存後にも照合する。

主担当が今回行うのは採用記録・開始指示書の保存のみ。実装・試験実行・新市場計算・PR・Actions・本番操作・送信は行っていない。
