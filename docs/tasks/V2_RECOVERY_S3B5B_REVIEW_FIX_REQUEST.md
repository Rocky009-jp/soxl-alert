# S3-B-5b R-01 限定修正依頼案

作成日：2026-11-03（日本時間）。状態：**レビュー付属の依頼案・未承認**。ユーザーが限定修正を指示するまで実装しない。

## 1. 固定入力

- コード開始：`782debc2a901a421a2b5205f9dd8ad4f0b484b01`（feat/v2-history-adopt-s3b5b-20261103）。元ブランチは更新せず、新しい修正ブランチを作る。
- 設計・元依頼：`5d21c10885a97e8d0cd614444f0da9b11ca322a5`。この依頼が補正するのはconfirmの計画内discarded検査だけ。
- レビュー：同じ資料ブランチの `docs/reviews/V2_RECOVERY_S3B5B_IMPLEMENTATION_REVIEW_20261103.md`、再現コード `docs/reviews/s3b5b_review_probe.py`。これらは読取資料として使い、コード開始点へ追随マージしない。
- 推奨担当：Sonnet 5.5・high。実際の設定とeffortを確認できた範囲で記録する。

## 2. 目的と変更範囲

計画のdiscardedが形式違反・内部矛盾を持つ場合、元バイト・候補バイト・その他のdataのどの経路でも、dataの型を読む前に `history_plan_mismatch`／field `plan` で拒否する。

| 許可するファイル | 変更 |
|---|---|
| v2_history_adopt/confirm.py | discardedの検査と必要な内部ヘルパー。呼出し位置は既存の計画検査内 |
| tests/v2_history_adopt/test_a5_09_review_fix.py（新規） | R-01回帰、正常・境界の対照。既存の155件を削除・置換しない |
| tests/v2_history_adopt/test_a5_07_runtime_audit.py | 必要な場合だけALLOWED_NAMESへ既存公開名 `v2_history.KINDS` と `v2_history.common.is_date` を追加。実装で使う名前だけ。検査本体や他の制約は変更しない |
| docs/implementation/V2_RECOVERY_S3B5B_RESULT.md | 末尾に修正の試験・差分・未実施を追記。旧結果は書き換えない |

既存6ランタイムのB-5b差分、旧6試験の補正、B-5a、その他のランタイム・試験・fixture・設定・依存・workflowは変更しない。計画・記録のキー数、公開API、エラーcode、保存schema、復元下限は変えない。範囲外の変更が必要なら、その変更を行わず反例と最小差分案を報告する。

## 3. 検査規則

discardedはschema 2の診断が返す次の形だけを受け入れる。

1. dictのキーは `{from_index, count, items}` ちょうど。
2. from_indexは厳密整数でadopt_countと等しい。countは0以上の厳密整数。いずれもbool不可。
3. itemsはlistで、len(items)==count。
4. 各itemは `{index, kind, seq, d, request_id}` ちょうど。indexは厳密整数でfrom_index＋列内の位置と等しい。
5. kindは `?` または既存KINDSの値。seqはnullまたは厳密整数、dはnullまたは既存のISO日付検査を通る値、request_idはnullまたは既存valid_request_idを通る値。

これらは現在の計画だけで判断できる。診断の仕様どおり、捨てる側のseqは不正な宣言値でも厳密整数なら負を許す。claimed_head_seqも不正な宣言値を保持するので、その符号・範囲からcountやitemsを制約しない。

元ファイルがヘッダーだけ壊れていて全記録がprefixに入る場合は、count=0・items=[]の正常な採用がある。これを拒否しない。

元バイト経路の診断・全basis再構築は維持する。候補経路は既存どおり正規化バイト完全一致だけをNO_CHANGEとし、字下げや改行が違う場合はstaleを維持する。元バイトなしでdiscardedの記述内容・diagnosis_digestの真偽まで証明しようとしない。追加のI/O、保存、S3-C処理、診断内容の再構築を導入しない。

## 4. 受入と結果保存

- 付属プローブの19観測が `--expect-fixed` で全解消・終了0。正常6対照、元バイトでの拒否14対照、prefix格子56ケースも維持する。
- 新しい回帰では不正discardedの各項目を個別に壊し、候補バイトとdata=Noneを含む経路でmismatchを確認。count=0、nullの読取値、負seq、未知kindの `?`、複数itemsの連番も対照にする。
- 新しい回帰を修正前コードへ適用し、R-01を検出することを確認。修正を外す最小の感度確認を行い、元の53変異全件の再実行は不要。
- 既存1464件とB-5bの155件を維持。auditの許可名以外、既存試験本体は無編集。LinuxのWindows専用4 skipは合格に数えない。
- 利用できる隔離Python環境で3.10〜3.13を確認し、完全な版・実OS・通信遮断の方法を区別して記録。未実施のOSや版を合格扱いしない。ユーザーPCの作業は求めない。
- 依頼元§8の60参照＋資料5d21c10＋元実装782debcの62参照を開始前とpush後に照合する。今回のレビューは、元担当者の過去の開始時照合の欠落を補ったことにはしない。
- コード・回帰の試験対象SHAと、結果追記だけの保存最終SHAを分ける。新しい自分の修正ブランチだけをpushして停止する。

PR・マージ・Actions・本番反映・通知・CONSUME・S3-Cには進まない。
