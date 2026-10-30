# V2 S3-B-2 設計・限定実装依頼書 作成依頼

作成：2026-10-30（日本時間）。**文書作成は承認済み。B-2の実装は未承認。**
担当：**Claude Opus 5.5、effort high**。既存S3-Aの証拠・投影規則を、有効履歴／再開始区間／v2参照へ接続する設計であるため。実設定をセッション情報で確認し、不明は不明と記録する。

## 1. 承認と固定版

ユーザーの指示：「B-2の設計・限定実装依頼書の作成へ進んでください」。
B-1のR-01／R-02は主担当が解消確認し、B-1の限定範囲として受領完了。B-2以降の実装・実ファイル保存・本番の承認へ広げない。

| 用途 | 固定参照 |
|---|---|
| 設計のコード基準・将来の実装開始点 | **adfdf765aeca0d01c8f10b596a6fac59d7c1a07e**（fix/v2-history-s3b1-review-20261030） |
| 同じコード・試験のSHA | 2b5fa2d079e2fe86b98b0e6d5be5431c5b4988ce。上の最終との差は結果文書§13の追記だけ |
| B-1修正受領 | [e8a94e5](https://github.com/Rocky009-jp/soxl-alert/blob/e8a94e5d415fce28f0ba7744b72a3d3dc390279b/docs/reviews/V2_RECOVERY_S3B1_FIX_RECEIPT_20261030.md) |
| S3-B設計第2版 | [361904b](https://github.com/Rocky009-jp/soxl-alert/blob/361904b1618ae9f9d3a672875c437a388826c253/docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md)、blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7。特に§2、§3.5、§4、§6、§9〜§10 |
| B-1採用・開始指示書 | 98e05e426b99154e7a5941c718b2b220f048e2a2。D-1・D-2・D-4を再質問しない |
| S3分割・境界 第3版 | [2d504de](https://github.com/Rocky009-jp/soxl-alert/blob/2d504de7cbf4628a3760d48f70fd0228dce6a61c/docs/specs/V2_RECOVERY_S3_DESIGN_DRAFT.md) |
| 上位保存・復旧設計第4版 | [e3e9094](https://github.com/Rocky009-jp/soxl-alert/blob/e3e90947a718cca877b543739ca60539207ca7a7/docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md)。除外→補完、現在状態・基点、開始境界を維持 |
| 実際に読む実装 | コード基準のv2_history、v2_recovery、v2_persistenceの関連モジュール、v2_coreの必要箇所、B-1結果文書§13 |

CLAUDE.md、docs/STATUS.md、docs/MODEL_POLICY.md、docs/ROADMAP.mdの必要箇所を確認する。古いSTATUSの承認待ちを今回の文書作成指示と混同しない。保存・復旧段階S3と、売却実務側の別分類S3を混同しない。対象を固定し、作業中にブランチ更新へ追従しない。

B-1のLinux4版・主担当Windows3.12.14での230件と再現コード10観測の解消は、既存の記録として参照する。今回の文書作成担当者が実行した試験へ置き換えない。

## 2. 成果物・作業範囲

コード基準adfdf765から新規資料ブランチ（例：docs/v2-history-s3b2-20261030）を作り、**新規2文書だけ**を追加する。同名ブランチがあれば上書きしない。

1. docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md
2. docs/tasks/V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md

両方に「設計案・レビュー待ち／限定実装は未承認」と明記する。既存の上位設計やB-1文書を全面改稿せず、B-2の具体化と上位との差だけを書く。主担当の本指示書・受領確認をコード基準へ丸ごと取り込まない。

**今回はコード変更・試験実行・試験コード／再現スクリプト作成・新市場計算は0。** 既存パッケージ・試験・fixture・結果・CLAUDE／STATUS／ROADMAP・依存・設定・workflow・研究は変更しない。PR・Actions・外部送信・本番・口座接続を行わない。図表や疑似コードは契約を説明する必要最小限にする。

## 3. B-2で具体化する内容

上位§2／§10のB-2（台帳投影、日次、新規ACK／DECLAREの計画・確認、メモリ上のバッチ値の境界）を対象にする。B-3の再初期化計画、B-4の復元計画、B-5のprefix採用、S3-Cは追加しない。ただしそれらの既存記録を含む検証済み履歴を読めることは必要である。

### 3.1 検証済み履歴から読む表示と参照写像

- 入力Historyは毎回既存validate_historyで検査する。有効seqはHistoryCheck.effective_seqsを基準にし、物理配列全体からACK・APPLY・宣言を無差別に拾わない。退避済みの解決記録を再有効化しない。
- **有効履歴全区間の台帳照合**と、**現在区間だけの日次用S1射影**を分ける。RESTARTより前の有効APPLY／skipped_sessions／宣言の証拠と、現在区間の開始境界・frontierを混同しない。
- 公開API・引数・戻り値・不変値の全キーを提案し、v2物理seq／event_hashと、一時的なS1 seq／hash、S3-Aの宣言参照を相互に取り違えない。origin付き移行記録、replay_of付き再生記録、native記録を区別する。
- 再利用のために仮のS3-A形式を組み立てる場合、その値が既存validate_resolutionsで保証される正規のResolutionSetなのか、検証済みv2を読む内部の表示なのかを明記する。未検証の偽造Setを既存公開APIの正規入力として扱わない。
- B-1のschema_version=2、7種のキー、hash、検査器、復元点の下限、I-15・IB-04・request_idの一意性を緩めない。

### 3.2 既存S3-A規則の再利用方法

実装基準のv2_recovery/project.pyには公開名apply_records、check_versions、final_checks、slice_check、resolve_coreがある。一方、Ctxの作成はS1 SnapshotView／ResolutionSetを前提にし、Ctxの_check_*、commandsの_check_*等はprivateである。commands.make_recordsもS3-Aのresolution_seq／hashと作成時source_headを前提にする。

**各機能について「呼ぶ既存公開名・必要な属性／引数・v2からの写像・出力から採用する項目」を表にする。** 単に「S3-Aへ委譲する」と書いて終えない。継承してprivateを呼ぶ、型検査を回避する、チェック済みと見せかける方法は使わない。

原則は既存v2_core／v2_persistence／v2_recovery／v2_historyを変更せず、新しい純粋なパッケージのアダプタで接続する。必要な再利用が公開名だけでは成立しないなら、成立しない具体例と必要な最小API差分を**提案**として示す。文書作成中に既存コードを変更せず、規則を黙って複製しない。将来の実装依頼では許可するモジュール・公開名・変更箇所を列挙する。

### 3.3 台帳投影と新規解決の証拠

- 形と構造・check_d／sessions・生の各行の解析を検査し、**指紋で除外→必要時だけ保存decisionを補完→version_selection→最終検査**の順を保つ。生台帳は変更しない。
- 全有効APPLY・欠測区間・宣言を保存窓と今回窓で照合する。next(D)のconfirmed／close_atだけの変化を判定入力差にしない。境界やD・間のセッションの確定状態、open_atの変化は別扱いにする。
- ACKはADDED／CHANGED／ROW_REMOVED／LATEを対象とし、補完できる根拠と、補完しないADDED／LATEを分ける。元行がないときのROW_REMOVEDまたはCHANGED＋ADDEDの一括解決は、指示の並べ順に依存させない。
- 有効なdecisionが1件ある日のDECLAREを拒否する採用済みN-04、衝突版の一方だけを選ぶ迂回の拒否、exclude_applied、LATEのAPPLY／宣言参照、対象日≤check_d、宣言frontierを維持する。
- 新規解決を作る際に、既存解決後の未解消衝突を「完成済み台帳」として先に検査し、新規計画を作れなくしない。構造検査・新コマンドの証拠検査・候補全体の投影検査の順を具体化する。
- 同一request_id・同内容、同ID・内容違い、requested_atだけの違い、複数コマンド、移行／再生で保持したrequest_basis、過去区間の宣言と現在frontier、同じバッチ内の参照可能範囲を具体例で固定する。既存S3-Aと違う意味が必要なら差と理由を別記する。

### 3.4 日次の候補と再実行

- 現在区間を正しいS1 Snapshotへ射影し、最終台帳を渡して**既存prepare_dayへ1回委譲**する。通常計算は既存evaluate_day、保存入力の再計算は既存検査器／apply_transitionに任せ、戦略式・閾値・状態式を複製しない。
- S1が返したAPPLYの内容項目を維持し、v2の物理先頭へseq・親hashを付け直す。古いS1 AppendPlan／PrepareResultを外部へ返さない。候補全体がvalidate_historyを通ることを準備時にも確かめる。
- PREPARED／NO_COMMIT／ALREADY_APPLIED、coreのstate_updated、メモリ上の確認成功、実際のcommittedを別の意味で定義する。committedはこの段階では常にfalse。
- 区間境界以前はtarget_not_after_boundary、最新APPLY日より前・最新日の再実行・宣言日・decisionなし・間の窓外decision・未確定session・再開後初回の各結果を固定する。
- **受理して作った候補を新しい履歴として同じ入力で同じDを準備すればALREADY_APPLIEDになる**ことを不変条件に含める。準備の検査を次回実行の検査より狭くしない。日次Dと解決用check_dを自動日付で補わない。

### 3.5 計画確認・バッチ値・保存との境界

- 計画hashは操作・期待履歴digest／先頭・入力digest・コマンド・候補全体・候補digest・状態digest等の必要な全項目へ結び付ける。記録にplan_hashを入れて循環させない。
- 確認は入力を読み直して再構築する。計画改変、不正な入力、正常だが変更された入力、同じ候補への再確認、確認後にさらに先頭が進んだ場合の固定code／field／ruleと優先順位を表で示す。B-1の移行確認と既存S3-Aの確認にある違いを曖昧に移植しない。
- 日次APPLYと複数解決記録の候補は既存S2／MemoryStoreへ渡せない型にする。手作業で値を再構築する悪意あるコードまで防ぐという主張はしない。新しいv2ストアをB-2の都合で追加しない。
- 上位§2はB-2に「公開用バッチ値」を挙げる一方、§9.1は「公開値の定義はS3-B、実装・実行はS3-C」としている。この記述差を明示し、**メモリ上の候補／確認済みバッチ値と、実ファイルへ公開するアダプタの境界**を一つに揃える推奨案を示す。上位の採用内容を無断で変更済みにしない。
- HistoryAppendBatch等の純粋な値を今回含める案なら、生成できる経路・全項目・空バッチの扱い・期待先頭・再検査を固定する。HistoryReplacementやB-1移行APIの変更を自動で含めない。
- 実保存・CAS実行・fsync／replace・成否不明後の照合・解錠・保守ゲート・Windows strictはS3-Cへ留保する。計画確認だけで保存・耐久性・通知権を得たとしない。

## 4. 具体例と受入条件

新規の受入IDを付け、各規則に少数の正常例・拒否例を対応させる。件数を目標にせず、必要な組合せを表にする。既存の例M／R／R-b／Uを読取fixtureとして利用する設計はよいが、今回実行しない。

最低限、次の流れを明示する。

1. GENESISだけのv2履歴→日次APPLY候補→その候補を履歴として同じDを再実行。decisionなしでは無追記。
2. 移行済み履歴（例M）に、新規v2 ACK／DECLAREを足す。元のsource逆検証と参照名の区別を維持。
3. RESTART後、旧区間の有効APPLYの台帳変更を照合しつつ、現在区間だけで日次計算。旧宣言で現在frontierを誤って進めない。
4. RESTORE後（例R／R-b）、退避済みACK／宣言を使わず、再生した解決記録の写像を使う。退避記録のhash検査はB-1が継続して行う。
5. 消えた元行＋別IDの打直しを一括解決する両順序、有効decision1件の宣言拒否、version_selectionの各迂回の拒否、LATEの2参照型。
6. next(D)のconfirmed／close_atの変化は無害、open_at変更・間の未確定・窓外decisionは停止。
7. 候補・計画の改変、確認時の不正入力とstale、request_id再利用、同候補への再確認。候補全体の検査を省く欠陥を検出できる対照。
8. 新規値・未検証値のdict／listを書き換えても内部不変。bool／floatを整数欄へ混入、深さ超過・巨大整数、repr／summary／例外への生URL・自由文の漏れを拒否。

将来の試験方針：
- 既存コア197・保存ドメイン170・S2 113（Linux109＋Windows専用4）・S3-A176・B-1 230を無編集で維持する。新規Nは別に実測。
- Python3.10／3.11／3.12／3.13、通信禁止、core.autocrlf=falseの別クリーンクローン。必要時だけ既定の隔離単体Pythonをスクラッチへ取得し、リポジトリの依存や設定を変えない。
- Windowsは利用できる場合に確認し、未実施は未実施と書く。S2のLinux strict前提の全探索をWindowsへ流用しない。
- 実際に参照する公開名へのspyで委譲経路を示す。今回の機能の欠陥注入だけを限定し、過去の全欠陥注入・全市場グリッドを再要求しない。
- 戻り値の参照共有・整数欄の型判定・未検証計画の表示など、既に修正済みの失敗を新しい型で再発させない。
- 実装担当案はSonnet 5.5・highを基本とする。新しい保存形式や上位契約の変更が必要なら、その判断は実装担当へ丸投げせず未決にする。

## 5. 依頼書と採否欄の完成条件

設計書には、全API・キー・型・hash・処理順・エラー表・依存する既存公開名・時系列の具体例・上位との差・未決表を書く。限定実装依頼書には、固定コード開始点adfdf765、資料固定手順、許可する新規パッケージと試験・結果文書、変更禁止、受入ID、結果保存と停止位置を具体化する。

B-2の範囲全体を一単位にできない実在の依存があれば、反例と理由を示し、最初の限定単位一つを依頼書にする。都合だけで段階を増やさない。既存変更が必要なら「変更が必要な最小ファイル・差分・維持する回帰」を提案として列挙し、変更を承認済みにしない。

ユーザー判断は不可欠なものだけ（目安3点以内）に絞り、設計上の選択と未確認の外部事実を分ける。B-1の採用済み事項・N-04・売買戦略・本番の保存先や資格情報を再質問しない。今回の設計・レビューをB-2の実装承認とみなさず、採否欄は未採用にする。

## 6. 参照の保護・保存・停止

以下34参照を開始時と保存・push後の終了時に、それぞれ完全SHAで照合する。本作成依頼を保存した資料ブランチも、渡されたパーマリンクの完全SHAを読取専用で追加する（計35参照）。開始時の照合を省かない。

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

自分の新規資料ブランチだけへ2文書を保存・pushし、開始／資料最終の完全SHA、両blob、2文書だけの差分、未決事項、開始・終了の参照一致を報告して止める。既存34参照と本作成依頼の資料ブランチは更新しない。

**コード・試験・市場計算・B-2実装・B-3以降・S3-C・PR・Actions・本番・送信へ進まない。** 文書を主担当がレビューしてから、具体化した限定実装単位をユーザーが採否判断する。
