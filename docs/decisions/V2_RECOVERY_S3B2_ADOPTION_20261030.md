# V2 S3-B-2 採用・限定実装承認記録

日付：2026-10-30（日本時間）
状態：**U-1・U-2・U-3を採用。第2版に基づくB-2限定実装への移行をユーザーが承認。**

## 1. 承認の根拠

ユーザーの明示指示：「3点を採用し、B-2限定実装へ移行します」。
直前の第2版再レビューで示した、次の3点と限定実装の一組を採用する。

| ID | 採用内容 |
|---|---|
| U-1 | **API-1**。新規v2_recovery/facts.py、commands.pyの証拠検査切出しとLATE宣言参照の分岐だけ。既存回帰・同等出力・影響する変異の確認を条件とする |
| U-2 | **R-a**。HistoryAppendBatchの純粋な値とcheck_append_batchをB-2に含め、I/O・公開・実行をS3-Cへ残す |
| U-3 | **Claude Sonnet 5.5、effort high**。開始時に実設定を確認し、不明は不明と記録する |

## 2. 採用する固定版

| 用途 | 完全SHA・blob |
|---|---|
| 実装開始点 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| 設計・限定依頼書第2版 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| 設計blob | 988258c798ee2d867c86238db1c4f426a360dda2 |
| 依頼blob | ab65b43704182a5416f5dbf935468da6239462fc |
| 第2版再レビュー | c4284ffc818d79155407ce153e44e35d135659e1 |

- [設計第2版](https://github.com/Rocky009-jp/soxl-alert/blob/e083cd3187f17692cb081fcc1031b09551fb8cb7/docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md)
- [限定実装依頼書第2版](https://github.com/Rocky009-jp/soxl-alert/blob/e083cd3187f17692cb081fcc1031b09551fb8cb7/docs/tasks/V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md)
- [再レビュー](https://github.com/Rocky009-jp/soxl-alert/blob/c4284ffc818d79155407ce153e44e35d135659e1/docs/reviews/V2_RECOVERY_S3B2_V2_REREVIEW_20261030.md)

固定文書・再レビュー・過去のSTATUSの「未承認」「未採用」は当時の記録である。今回のユーザー指示により、上の3点とB-2限定実装だけを承認済みに進める。固定文書や既存資料の承認待ち表記を書き換える必要はない。本記録は試験合格・本番採用を先取りしない。

## 3. 許可範囲と終了位置

許可する場所は、固定依頼書§3のとおり、新規v2_recovery/facts.py、限定したv2_recovery/commands.pyの2点、新規v2_history_ops/、tests/v2_history_ops/、docs/implementation/V2_RECOVERY_S3B2_RESULT.mdである。API-1の変更は新規実装ブランチの上でだけ行い、既存S3-Aブランチは更新しない。

作業順序はAPI-1と回帰の確認→新パッケージと試験→結果文書。最初の回帰を満たせなければ新パッケージへ進まない。受入条件B2-01〜B2-17、固定依頼§6の欠陥注入22項目、影響するS3-A変異の限定再実行、既存試験非変更、Python4版・通信禁止・別クリーンクローンの方針を採用する。

B-3〜B-5、S3-C、HistoryReplacement、B-1移行APIの変更、v2ストア、実ファイル移行・公開・CAS実行・解錠・復元・再初期化の実行、PR・Actions・本番・通知・口座接続は含めない。結果を実装ブランチへ保存・pushし、完全SHAと確認結果を報告して止める。

契約矛盾や範囲外変更が必要なら、反例・影響・最小差分案を報告し、該当変更を行わない。採用済みのS3-A受理・拒否、N-04、戦略式・閾値・状態式を独断で変えない。

## 4. 今回の保存

本記録と開始指示書の新規2文書だけを、別資料ブランチdocs/v2-history-s3b2-adoption-20261030へ保存する。保存前に固定依頼§8の35参照と初版・初版レビュー・第2版・第2版再レビューの4参照、計39参照を完全SHAで照合し一致した。保存後にも同じ39参照を照合する。

主担当の今回の作業は文書の保存だけ。実装・試験・市場計算・PR・Actions・本番操作・送信は行っていない。Claudeへの実行指示は、ユーザーが開始指示書を渡す形とする。
