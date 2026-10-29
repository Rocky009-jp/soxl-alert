# Claude開始指示：V2 S3-B-1 限定実装

日付：2026-10-29（日本時間）
指定担当：**Claude Sonnet 5.5、effort high**。
ユーザーがD-1・D-2・D-4の採用とB-1限定実装への移行を明示承認した。[採用記録](../decisions/V2_RECOVERY_S3B1_ADOPTION_20261029.md)を根拠とし、以下の固定依頼に従って実装・オフライン試験・結果保存まで進めてください。

## 1. 開始と固定入力

1. CLAUDE.md、docs/STATUS.md、docs/MODEL_POLICY.md、docs/ROADMAP.mdの必要箇所を確認する。古い承認待ちは歴史記録として扱い、本採用記録のB-1限定承認を優先する。
2. セッション情報でSonnet 5.5／highの実設定を確認し記録する。確認できなければ不明と記録し、選択できたと断言しない。
3. コードの開始点は **e68d702de7fa80f141e14b63cf88082c15493994**。新規実装ブランチ例はfeat/v2-history-s3b1-20261029。既存同名ブランチがあれば上書きせず、別名を使う。
4. 設計・依頼は以下のパーマリンクを取得し、完全SHAとblobを記録する。資料ブランチをコードの開始点にせず、資料コミットを丸ごとcherry-pickしない。作業中に資料の更新へ追従しない。

| 根拠 | 固定版 |
|---|---|
| [設計第2版](https://github.com/Rocky009-jp/soxl-alert/blob/361904b1618ae9f9d3a672875c437a388826c253/docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md) | 361904b1618ae9f9d3a672875c437a388826c253、blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7 |
| [依頼第2版](https://github.com/Rocky009-jp/soxl-alert/blob/361904b1618ae9f9d3a672875c437a388826c253/docs/tasks/V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md) | 361904b1618ae9f9d3a672875c437a388826c253、blob 61a645c086c5f62e31f29fcf662cbc76e3bb22dc |
| [第2版再レビュー](https://github.com/Rocky009-jp/soxl-alert/blob/225b10059bdc23a677f97fc3ac7597ca73c4b00c/docs/reviews/V2_RECOVERY_S3B_V2_REREVIEW_20261029.md) | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |

本書は開始手順であり、詳細契約は固定した第2版の設計と依頼に従う。読めない資料・矛盾があれば、読んだふりや独断の仕様変更をしない。

## 2. 実装範囲

追加してよいのは次だけ。

- v2_history/：不変なHistory値・codec、7種のvalidate_history、鎖ビューと既存S1への射影、make_history_genesis、migrated_sources、メモリ上の移行計画と確認。
- tests/v2_history/：H-01〜H-14の試験と、ランタイムから参照しない合成記録ビルダー。
- docs/implementation/V2_RECOVERY_S3B1_RESULT.md：結果文書。

既存ファイルは変更しない。既存の公開名だけを依頼書§2の一覧どおりに利用し、既存のprivate名・メソッドへ依存しない。遷移式・閾値・状態判定を複製せず、S1射影を既存validate_snapshotで検査する。

復元や再初期化は**記録の検査だけ**で、計画生成・実行を作らない。B-2〜B-5、S3-C、台帳投影・日次処理、新規ACK／DECLAREの計画、CONSUME、prefix採用、HistoryReplacement／HistoryAppendBatch、v2用ストア、公開・解錠・CLI・通知・outboxを追加しない。ランタイムのI/O・時計・ネット・プロセス・スレッド・乱数・環境変数を使わない。

補正の重要点：
- REPLAYのstate_afterは新しい鎖で決める。ACK／DECLAREは新しい有効親と同じ、RESTARTは初期状態。旧値のコピーはhashを付け直しても拒否する。例R・R-bとRESTART再生の対照を確認する。
- 復元点の下限は移行履歴ではSCHEMA_MIGRATION、新規v2履歴ではGENESIS。他の拒否条件は維持する。
- schema拒否と別クラスの型拒否は別試験にする。既存検査器を変更しない。
- 移行確認では計画の形・hash→入力の再検査→有効入力のdigest／期待先頭の差→再構築一致の順。不正な入力は既存エラー、正常な変更はstaleと分ける。

## 3. 確認と終了

固定依頼のH-01〜H-14と欠陥注入22種を実施する。等価・対象外・未実施は検出と区別し、過去の全欠陥注入や全市場グリッドを追加しない。

既存コア197件・保存ドメイン170件・S3-A176件は無編集。S2の113件はOSの契約に従う（Linux109件とWindows専用4件を混同しない）。新規件数は実測し別集計する。Python 3.10／3.11／3.12／3.13の完全版、OS、通信遮断方法を記録する。依頼書§6の隔離Python利用方針を維持する。

最終コードはcore.autocrlf=falseの別クリーンクローン、通信禁止で確認する。Windowsがなければ未実施とし、他担当・ユーザーPCの結果を自身の実行結果にしない。H-12で既存LocalFileStoreの拒否を試す一時rootはfile_sync_onlyを使い、既定strictをWindowsの試験準備に使わない。

結果文書には固定依頼§6の項目をすべて記録する。開始SHA・試験対象SHA・文書追加後の最終SHAを分け、後二者の差が結果文書だけか確認する。解釈・差・未確認事項を残す。受入条件はテスト件数と混同しない。

以下29参照を開始時と保存・push後の終了時に、完全SHAで別々に照合する。本採用記録の資料ブランチも、ユーザーから渡されたパーマリンクの完全SHAで追加して読取専用に固定する。自分の実装ブランチ以外は更新しない。

| 参照 | 完全SHA |
|---|---|
| main | 31144d9b6af8a6c920ad53c395cd550e8c48a7fa |
| feat/interim-notification-20261026 | 920e69571cf4feda09f3f2f560e96fcb9cb09d50 |
| docs/v2-roadmap-20261023 | 647aeac34cde0d01ec27174f7620aff1724af0e1 |
| feat/v2-offline-core-20261027 | 1a54a8573023af9490017b02a8b6458f061031c7 |
| feat/v2-core-state-checks-20261028 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| docs/v2-market-state-recovery-20261027 | b43205ce1a53e4560fb85f9cfb715c72a1132a75 |
| docs/v2-persistence-domain-20261028 | 425df80d04b116e25e481184069b89bed1380c3a |
| docs/v2-persistence-domain-s1-receipt-20261028 | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| feat/v2-persistence-domain-offline-20261028 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| fix/v2-persistence-domain-s1-review-20261028 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| docs/v2-persistence-domain-s1-fix-receipt-20261028 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048 |
| fix/v2-core-fg-numeric-overflow-20261028 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| docs/v2-core-fg-overflow-receipt-20261028 | a235b7607f5624ed84ba5427ac0f44029f41d262 |
| docs/v2-local-store-s2-20261028 | 73cec624cb73205ac63ca92e26df2b6f70019b16 |
| feat/v2-local-file-store-s2-20261028 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| docs/v2-local-store-s2-receipt-20261028 | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| fix/v2-local-store-s2-review-20261028 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| docs/v2-local-store-s2-fix-receipt-20261028 | 1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a |
| docs/v2-user-pc-tests-20261028 | aa21dbe85a133c61e8c011a6f78db1b23af0fb13 |
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |

範囲内で実装できない矛盾や既存ファイルの変更が必要なら、具体的な反例・影響・最小差分案を報告し、該当変更を行わない。許可された独立部分を進められる場合は進めてよいが、矛盾を独断で埋めない。

結果を実装ブランチへ保存・pushし、固定SHA・差分・受入条件の結果・未実施を報告したら止める。PR・マージ・Actions・本番・外部通知・証券口座への接続を行わず、B-2以降やS3-Cへ進まない。
