# Claude開始指示：V2 S3-B-2 限定実装

日付：2026-10-30（日本時間）
指定担当：**Claude Sonnet 5.5、effort high**。
ユーザーがU-1＝API-1、U-2＝R-a、U-3＝Sonnet 5.5・highと、B-2限定実装への移行を明示承認しました。[採用記録](../decisions/V2_RECOVERY_S3B2_ADOPTION_20261030.md)を根拠に、以下の固定依頼に従って実装・オフライン試験・結果保存まで進めてください。

## 1. 開始と固定入力

1. CLAUDE.md、docs/STATUS.md、docs/MODEL_POLICY.md、docs/ROADMAP.mdの必要箇所を確認する。古い承認待ちは歴史記録として扱い、今回の採用記録によるB-2限定承認を優先する。
2. セッション情報でSonnet 5.5／highの実設定を確認し、確認できなければ不明と記録する。モデルを独断で変更せず、プロンプトに書いたことで設定できたと断言しない。
3. コード開始点は **adfdf765aeca0d01c8f10b596a6fac59d7c1a07e**。新規実装ブランチ例はfeat/v2-history-s3b2-20261030。同名があれば上書きせず別名にする。資料コミットをコードの開始点にせず、丸ごとcherry-pickしない。
4. 次のパーマリンクを取得し、完全SHA・両blobを記録する。作業中に資料更新へ追従しない。

| 根拠 | 固定版 |
|---|---|
| [設計第2版](https://github.com/Rocky009-jp/soxl-alert/blob/e083cd3187f17692cb081fcc1031b09551fb8cb7/docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md) | e083cd3187f17692cb081fcc1031b09551fb8cb7、blob 988258c798ee2d867c86238db1c4f426a360dda2 |
| [限定実装依頼書第2版](https://github.com/Rocky009-jp/soxl-alert/blob/e083cd3187f17692cb081fcc1031b09551fb8cb7/docs/tasks/V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md) | e083cd3187f17692cb081fcc1031b09551fb8cb7、blob ab65b43704182a5416f5dbf935468da6239462fc |
| [第2版再レビュー](https://github.com/Rocky009-jp/soxl-alert/blob/c4284ffc818d79155407ce153e44e35d135659e1/docs/reviews/V2_RECOVERY_S3B2_V2_REREVIEW_20261030.md) | c4284ffc818d79155407ce153e44e35d135659e1 |

固定文書の未承認表記は、今回の採用記録で上書きする対象の歴史的状態である。詳細契約は第2版に従い、初版6286113を実装根拠にしない。読めない資料・矛盾は報告し、推測で埋めない。

## 2. 作業順序と変更範囲

**①API-1の差分と既存回帰確認 → ②新パッケージと試験 → ③結果文書**の順に進める。①のB2-01・B2-02を満たせなければ②へ進まず報告する。①に必要な新規試験はtests/v2_history_ops/へ置き、既存試験を書き換えない。

| 場所 | 許可内容 |
|---|---|
| v2_recovery/facts.py 新規 | 設計§3.3 A1のFixedApply、FixedFacts、LedgerContext。形の検査・事実の表示・台帳文脈 |
| v2_recovery/commands.py | A2：make_records前半を本文のままcheck_commandsへ切り出し、make_recordsから呼ぶ。A3：LATE宣言参照にv2形の分岐を追加。**この2点以外は変更しない** |
| v2_history_ops/ 新規 | 固定依頼§4の公開API・値・純粋な再検査 |
| tests/v2_history_ops/ 新規 | B2-01〜B2-17、新機能の限定欠陥注入。既存h_helpersは読取のみ |
| docs/implementation/V2_RECOVERY_S3B2_RESULT.md 新規 | 固定依頼§7の結果記録 |

上記以外の既存v2_core／v2_persistence（local含む）／v2_recovery／v2_history、既存全試験・欠陥注入スクリプト・fixture・基準データ・研究・main.py・依存・設定・workflow・CLAUDE／STATUS／ROADMAP・既存結果文書は変更しない。既存パッケージの__init__.pyへの再公開もしない。

利用できる既存公開名は、固定依頼§3の一覧どおり。新パッケージからCtx・SnapshotView・validate_set・make_records・private名を呼ばず、Ctxの属性を真似た代用品で検査を迂回しない。規則の本文はS3-Aへ、通常計算はS1 prepare_dayへ委譲し、戦略式・閾値・状態式を複製しない。

## 3. 実装で保つ要点

- 投影は**有効履歴の全区間**、日次のS1射影は**現在区間だけ**。物理配列の退避ACK／宣言を再有効化しない。参照はv2物理seq＋event_hash。一時S1のseq／hashを外へ出さない。
- 構造と各行の解析→証拠→候補全体の順。未解消の衝突を解く計画が、証拠検査前の最終照合で作れなくなる順序にしない。
- 除外→必要時補完→version_selection→最終検査を維持。有効decision1件のDECLARE拒否（N-04）、ADDEDの証拠、一括解決の順序非依存、LATEの2参照型を保つ。
- 日次PREPARED候補を完全検査・全区間投影へ通す。その候補を新しい履歴にして同じ入力・同じDを処理すればALREADY_APPLIED。core.state_updatedと保存成功を混同しない。
- 第2版の例Rは、未使用q7の成功、使用済みq4とDROP済みq2のconflictを固定する。fixtureやID検査を試験都合で変えない。MIGRATEDのIDはhashが一致してもconflict。
- from_dictのJSON検査と、確認／checkでの意味検査を分ける。未検証値を含む全アクセサの参照共有を避け、表示前の形式検査・生値の秘匿・固定エラーを保つ。
- 再確認は第2版§6.7の枝A／枝Bどおり。枝Bで元のheadとの一致を要求しない。NO_CHANGEへ変わる期待basisの4項目を守り、元のplan_hashへ再構築後のplan_hashを一致させない。
- R-aはHistoryAppendBatchとcheck_append_batchの**メモリ上の値と検査だけ**。committed／committableはfalse。既存ストアが拒否する型の境界を守る。

B-3〜B-5、S3-C、HistoryReplacement、B-1移行APIの変更、v2ストア、実保存・公開・ロック・CAS実行・置換・解錠・CLI・通知・outbox・自動日付・追いつき・口座接続は作らない。ランタイムのI/O・時計・ネット・プロセス・スレッド・乱数・環境変数を使わない。

## 4. 試験・結果保存・停止

固定依頼のB2-01〜B2-17、§6の欠陥注入22項目と、B2-02の既存S3-Aの目印数え上げ・commands.py関連変異の限定再実行を行う。検出・等価・対象外・未実施を区別する。過去の全変異や全市場グリッドへ広げない。

既存コア197・保存ドメイン170・S3-A176・B-1 230を無編集で維持し、S2 113はOS契約どおり（Linux109合格＋Windows専用4件非対象）。新規Nを別集計する。Python3.10／3.11／3.12／3.13の完全版、OS、通信禁止の方法を記録する。隔離Pythonの利用方針・Windowsでのfile_sync_onlyとstrictの区別は固定依頼§7に従う。

最終コードをcore.autocrlf=falseの別クリーンクローンで確認する。WindowsやユーザーPCが無ければ未実施とし、他者の試験を自分の結果にしない。既存コードの差分を列挙し、特にv2_recoveryの差分は全文を結果文書に示す。モデル実設定・資料SHA／blob・API／キー／hash／rule・受入対応・具体例・欠陥注入・解釈・保留は固定依頼§7どおり記録する。

開始SHA・試験対象SHA・結果文書だけの保存最終SHAを分け、最後の差分が結果文書だけであることを確認する。結果を新しい実装ブランチへ保存・pushし、完全SHAと確認範囲を報告したら止める。

契約矛盾や範囲外の既存変更が必要なら、反例・影響・最小差分案を報告し、該当変更を行わない。モデル変更・API-0／R-bへの切替・仕様変更を独断で進めない。PR・マージ・Actions・本番・送信やB-3以降へ進まない。

## 5. 読取専用に固定する参照

以下39参照を、開始時と保存・push後の終了時に完全SHAで別々に照合する。本採用記録と開始指示書を保存した資料ブランチも、渡されたパーマリンクの完全SHAを追加して固定する（計40参照）。開始時照合を省かない。更新してよいのは自分の新規実装ブランチだけである。

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
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
