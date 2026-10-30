# V2 S3-B-2 設計・依頼書 文書限定補正依頼

日付：2026-10-30（日本時間）。担当：**Claude Opus 5.5、effort high**。
今回は文書の補正だけ。B-2実装、API-1のコード変更、試験・再現コード・市場計算は行わない。

## 1. 固定版・変更範囲

開始点：**62861137a28e96a361f198f5601e0f5ae77a6910**。
元の資料ブランチdocs/v2-history-s3b2-20261030は更新せず、新規資料ブランチ（例：docs/v2-history-s3b2-revision-20261030）を作る。同名があれば別名にする。

変更するのは次の既存2文書だけ：

- docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md（開始blob 7c84758219be620083742cbb804ef541f630d578）
- docs/tasks/V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md（開始blob 542485aa2b7e40f0394153e31349bfdb6171149e）

[レビュー](../reviews/V2_RECOVERY_S3B2_DESIGN_REVIEW_20261030.md)を読む。コード基準adfdf765aeca0d01c8f10b596a6fac59d7c1a07e、受入ID B2-01〜B2-17、既存回帰の不変、3点の採否待ちは維持する。状態は「第2版・レビュー待ち／限定実装は未承認」のまま。主担当の推奨をユーザー採用にしない。

## 2. 必須補正 N-01

設計§12.4の3で成功する新しいACKの依頼IDを、例Rで使っていないq7等に変える。既存h_helpersの例Rは、RESTORE#1（seq7）でq4、RESTORE#2でq5、RESTORE#3でq6を使っている。q4は退避後も物理履歴に残り、設計§6.5の方針では再利用できない。

成功例：未使用q7＋有効APPLY#19へのADDED→READY。
拒否例：同じコマンドでもq4→history_request_conflict（RESTOREのID）、q2→history_request_conflict（DROPされた解決依頼）。#4／#8への参照拒否は維持する。
依頼B2-10／B2-13に対応させる。元fixtureやID検査を弱めない。

## 3. 任意提案の整理

P-01：MIGRATEDのrequest_hashが一致する場合はあり得る。例Mの最初のAPPLYはv1／v2でseqとhashが同じ。MIGRATEDを常にconflictとする保守的方針は維持し、理由だけを正確にする。

P-02：from_dictでJSONとして保持する段階と、確認／check_append_batchで意味を検査して拒否する段階を§12.8／B2-16で区別する。深さ超過・巨大整数の読込拒否と混ぜない。

P-03：確認時に元履歴と一致する枝／候補履歴と一致する枝で、比較するheadとdigestを具体化する。候補の枝で元のheadとの一致を要求せず、再確認NO_CHANGEを維持する。

必要なら3提案を一緒に取り込み、対応を小さな改訂表に記す。上位形式・API-1の範囲・R-a・新しい採否や後工程へ広げない。

## 4. 保存・停止

CLAUDE／STATUS／MODEL_POLICYの必要箇所を確認し、指定モデル・effortの実設定を確認できた場合だけ記録する。依頼§8の35参照＋元資料6286113＋本レビュー資料（渡された完全SHA）の計37参照を、開始時と保存・push後の終了時に照合する。

新規資料ブランチへ2文書だけを保存・pushし、開始／最終の完全SHA・両blob・差分・反映対応・未決・参照一致を報告して止める。元の資料・レビュー・実装ブランチ、既存コード・試験・結果・設定は変更しない。B-2実装・B-3以降・S3-C・PR・Actions・本番・通知は行わない。
