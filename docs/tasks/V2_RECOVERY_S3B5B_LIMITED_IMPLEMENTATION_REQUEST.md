# V2 S3-B-5b prefix採用 限定実装依頼書

作成日：2026-11-02（日本時間）。版：初版。
状態：**初版・採否判断待ち・未承認。本書の保存だけでは実装を始めない。**
本書はB-5のうちB-5b（RECOVERY_PREFIX_ADOPTION記録と、採用の計画・メモリ内確認）を対象とする。対になる設計はdocs/specs/V2_RECOVERY_S3B5B_PREFIX_ADOPTION_DESIGN_DRAFT.md（以下「設計」）。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **c8ba08f15ea28248a9fe7924f32ce136fc16d5e6**（feat/v2-history-diagnose-s3b5a-20261102） |
| コード・試験の同値版 | fac880c40e235a849e36269cee99985a5183f5ae。c8ba08fとの差はB-5a結果文書1本 |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-history-s3b5b-20261102）の設計とdocs/specs/V2_RECOVERY_S3B5B_SCOPE_TRIAL_20261102.diff。SHAと3つのblobを開始報告に記録 |
| B-5a受領 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9、docs/reviews/V2_RECOVERY_S3B5A_IMPLEMENTATION_REVIEW_20261102.md |
| B-5境界（D-3、採用済み） | 5c9e1e89c8f9d33689e9bc67e266fa6031507136、docs/specs/V2_RECOVERY_S3B5_DIAGNOSIS_ADOPTION_DESIGN_DRAFT.md §9 |
| 上位S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253（§3.3、§11） |
| 計画・確認の手本 | B-4 0108131045d904b0997299fcade5929567940d6d と実装ac21980のv2_history_restore |

ユーザーが設計§10のD-1〜D-4を採用し、B-5b限定実装への移行を指示した後にのみ、新規実装ブランチをc8ba08fから作る。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-4）。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。古いSTATUSの承認待ちを、B-5aまでの採用を取り直す指示とは扱わない。未承認のD-1〜D-4を採用されたと書かない。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history/values.py、view.py、restore.py、\_\_init\_\_.py | 設計§3の変更だけ。採用記録の検査はview.pyの`_Walk`のメソッドに置き、v2_history/に新しいファイルを作らない |
| v2_history_ops/chain.py | `_REQUEST_KINDS`への1項目とそのimportだけ（設計§4） |
| v2_history_restore/points.py | `check_point`の下限1つとそのimportだけ（設計§4） |
| v2_history_adopt/ 新規 | 設計§5の2関数・2型・3定数。公開名7名。内部モジュールもこの内側 |
| tests/v2_history_adopt/ 新規 | test_a5_\*.py、a5_helpers.py、限定変異を保存する場合はa5_sensitivity.py。\_\_init\_\_.pyは作らない |
| 既存試験6本 | 設計§7.2の箇所だけ（§3） |
| docs/implementation/V2_RECOVERY_S3B5B_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence（local含む）、v2_recovery、v2_history_restart、v2_history_diagnose、上記以外のv2_history・v2_history_ops・v2_history_restoreの既存ランタイム、既存機能試験/変異/fixtures/基準データ/ヘルパー、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
CONSUME、S3-C（退避・公開・照合）、ストア、ファイル・パスの読み書き、CLI、通知・本番接続、v1の採用、台帳・sessions・seriesの受取りへ広げない。既存private名やテストビルダーをランタイムへ取り込まない。
範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 既存試験6本の限定補正

設計§7.2の表が正本である。要点：

- **h02**：test_unknown_kind_and_the_b5_kindの例の"RECOVERY_PREFIX_ADOPTION"を"CONSUME"に置き換える1行だけ。
- **h14**：公開名一覧に1名、KINDSの件数7→8、B-5の種別の`assertNotIn`を「KINDSの末尾がRECOVERY_PREFIX_ADOPTION」に。CONSUMEの拒否とファイル一覧の試験は変えない。
- **b17**：KIND_CONSTANTSに8種目、FilesChangedの既存2メソッドだけ（許可パス、Mとして許すB-5bの6ファイル、\_\_init\_\_.pyの例外2本、tests検索の除外）。commands.pyの差分検査は変えない。
- **r3_07**：FilesChangedの既存3メソッドだけ。b17の固定差分（削除行・追加行・ハンク数）を補正後のb17に合わせて静的に更新する。
- **r4_09**：KIND_CONSTANTS、Runtime.test_nothing_of_the_later_stages（"restore_before_adoption"だけを語の例外にする）、B17_\*／R307_\*の6定数、FilesChangedの既存2メソッドだけ。allowed_path()とPathJudgementは変えない。
- **d5_08**：PINNED、Runtime.test_no_adoption_or_store_name_is_exported_or_defined（v2_history.KINDSの確認だけ）、FilesChangedの各メソッド。旧3本の変更箇所の許可にb17・r4_09のKIND_CONSTANTSとr4_09のtest_nothing_of_the_later_stagesを加える。旧3本のassertの数をASTの呼出しで数える（設計§7.2の理由）。allowed_new_path()とPathJudgementは変えない。

共通：各本のSTART、test関数名、assert呼出しの数、skip・expectedFailure・早期returnの数、`"HEAD"`の使い方を変えない。新しいモジュール定数を作らない。固定リテラルを試験の中で動的に生成しない。

設計作成時の一時環境（c8ba08f、空のプレースホルダー、pushしないローカルコミット）で、この補正と設計§3・§4の6ランタイム変更を適用し、既存9スイート1464件がLinux・Python 3.13.18で全件合格した（設計§8）。参考の差分はdocs/specs/V2_RECOVERY_S3B5B_SCOPE_TRIAL_20261102.diff。写すのではなく規則に従って作り、違いがあれば結果文書で説明する。行の折り返しは意味を変えない範囲でよい。

## 4. 固定する振る舞い

- 検査器（設計§3）：KINDSの末尾に8種目、12キー、`adoption_record`の7段の順序とrule（新規はadoption_evidenceだけ）、raw_size≥1、claimed_schema_version＝2、discarded_from_seq＝seq、claimed_head_seq・claimed_head_hashはnull可で符号を見ない。復元の下限restore_before_adoption（復元点＝採用記録は可）。既存の記録・規則を緩めない。
- B-2 `_REQUEST_KINDS`とB-4 `check_point`は設計§4の1項目ずつ。B-4の`changes`の種別一覧、B-2の投影、B-3は変えない。
- prepare（設計§5.2）：引数→診断→PREFIX_ONLY→版2→count一致→移行の痕跡（読めるSCHEMA_MIGRATION、またはnullでない`origin`を持つ捨てる側の要素、prefixがmigrated=Falseのとき）→prefixの作り直しと検査→IDの重複（prefixの物理履歴と捨てる側の読めるID）→採用記録と候補の検査→basis21キー。順序とエラーは設計§5.2・§5.6どおり。
- 採用記録（設計§5.3）とbasis（§5.4）のキー・値を固定する。operation "soxl-v2-history-prefix-adoption-plan/1"、reason_code "ADOPT_VERIFIED_PREFIX"。
- confirm（設計§5.5）：計画の形とhash→basisの内部整合→dataの型→元の生バイトなら作り直して全basisを比較してCONFIRMED_IN_MEMORY→候補の正規化バイトならNO_CHANGE→他はhistory_plan_stale。改ざん・作り直しの不一致はhistory_plan_mismatch。
- 生バイトのSHA-256は診断の値を使い、hashlibを使わない。標準ライブラリはcopyだけ。依存は設計§5.7の名前だけ。
- 時刻・乱数・I/O・ストアなし。結果のHistoryはメモリ内の候補で、committedは常にFalse。

## 5. 受入条件 A5-01〜A5-18

各IDは機能項目であってテスト件数ではない。新規Nは実測する。

| ID | 必須確認 |
|---|---|
| A5-01 回帰・変更境界 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131の計1464件をOS契約どおり維持。機能試験はh02・h14の§3の箇所だけ、旧範囲試験4本は§3の箇所だけ。c8ba08f起点の新B-5b scopeが設計§7.4を直接検査する |
| A5-02 種別と鍵 | KINDSが8種で末尾がRECOVERY_PREFIX_ADOPTION、既存7種の順序が同じ。12キーちょうど。キーの過不足はrecord_keys。v2_history.\_\_all\_\_が24名 |
| A5-03 正常な採用記録 | prefix＋採用記録の候補がvalidate_historyを通り、HistoryCheckのhead・current_state・effective・境界が期待どおり（採用記録は区間を変えない、current_stateはprefixと同じ）。採用記録の後の採用記録も通る |
| A5-04 採用記録の各rule | 設計§3.2の1〜7を1つずつ壊して、該当するrule（request_id、state_after、adoption_evidence、request_basis、requested_at、reason_code、request_hash）。adoption_evidenceは、6キーの過不足、raw_sha256の形、raw_size 0・負・bool・小数、claimed_schema_version 1・3・"2"・bool、claimed_head_seqのbool・文字列（nullと負の整数は通る）、claimed_head_hashの形、discarded_from_seq≠seqを別々に確認 |
| A5-05 置き方 | MIGRATIONより前（migration_position）、requestバッチの途中（batch）、復元の窓の途中（restore_incomplete）、親が直前でない（parent）、前の記録のIDの再利用（request_id）を、既存の規則で拒否する |
| A5-06 復元の下限 | B-1：最後の採用記録より前を復元点にする復元はrestore_before_adoption、採用記録自身を復元点にする復元は通る。B-4：同じ位置でrestore_invalid／restore_point／restore_before_adoption、採用記録を復元点にする計画はREADY→CONFIRMED_IN_MEMORY |
| A5-07 後続段階 | 採用後のB-2日次（APPLYの親が採用記録）、B-2のACK／DECLARE、B-3の再開始が通る。採用記録のIDの再利用はB-2・B-3・B-4の計画でhistory_request_conflict。read_effectiveのrequestsに採用記録が`record_kind`="RECOVERY_PREFIX_ADOPTION"で現れる |
| A5-08 prepareの引数 | dataのstr・bytearray・memoryview・None・bytesのサブクラス→data/type。adopt_countのbool・0・負・小数・文字列→adopt_count/type。requested_atのnaive・非datetime→既存InputError。request_idの形式違い→request_id/request_id。この順序（複数が同時に違うとき先の段の失敗） |
| A5-09 診断の状態 | VALID、NO_VALID_PREFIX、UNREADABLEのバイトはnot_adoptable。v1のPREFIX_ONLYはschema_1。adopt_countが診断のcount±1はcount_mismatch |
| A5-10 移行の痕跡 | example_mのMIGRATIONのevent_hashだけを壊したバイト（count＝2）、MIGRATIONのkindを壊して"?"にしたバイト（後ろのoriginで判定）がmigration_discarded。example_m_empty_worldのMIGRATION破損（捨てる側はMIGRATIONだけ）もmigration_discarded。移行済みのprefix（MIGRATIONが残るk）の後半破損は採用できる |
| A5-11 ID | prefixの物理履歴のID（実効鎖から外れた記録・移行記録・再開始・復元のIDを含む）と、捨てる側itemsの読めるIDの再利用がhistory_request_conflict。捨てる側の読めないIDは判定に使わない |
| A5-12 採用記録と計画の値 | 採用記録の12キーとevidence・basisの値が設計§5.3どおり（独立に計算したraw_sha256・raw_size・claimed・request_hash・event_hashと照合）。basisが21キーちょうどで、各値が診断・候補から独立に計算した値と一致。plan_hash＝sha256(canonical_json(basis)) |
| A5-13 confirm | 同じバイト→CONFIRMED_IN_MEMORY（候補が計画と同じ）。候補の正規化バイト→NO_CHANGE。1バイト違い・字下げした候補・別の壊れ方のバイト→history_plan_stale。plan_hash違い・basisの各キーの改ざん・candidate_recordやcandidate_historyの差し替え・計画でない値→history_plan_mismatch。dataの型違い→data/type |
| A5-14 内部の不整合 | 候補の検査の失敗はhistory_invalid／history／adoption_candidate（呼び出し側の誤りと区別）。spyで検査器を失敗させて確認 |
| A5-15 委譲 | 診断は変更しない`diagnose_history_bytes`、候補の検査は`validate_history`、hashは`basis_request_hash`・`compute_event_hash`を、新パッケージが実際に参照する名前へのspyで確認。prepareの診断は1回、confirmの元バイトの経路は作り直しで1回 |
| A5-16 不変性・決定性・秘匿 | AdoptionPlan・AdoptionConfirmResultは不変で、to_dict・basis・historyが独立した写し。同じ入力と同じrequested_atで同じbasis・plan_hash。入力のbytesは不変。repr・summaryに生の値・市場値・URL・パス・例外文なし。committedはFalse。旧MemoryStore／LocalFileStoreが計画・結果をplan_typeで拒否する |
| A5-17 範囲監査 | 新runtime全体のAST。公開依存は設計§5.7の名前だけ、\_\_all\_\_は7名、標準ライブラリはcopyだけ（hashlibなし）。I/O・時計・乱数・環境・外部private・閾値・戦略式なし。CONSUME・公開・退避・解錠・outbox・ストアの語なし。台帳・sessions・seriesの名前を受け取らない |
| A5-18 新B-5b scope | 設計§7.4の全項目。6ランタイムと6試験の差分を静的リテラルで固定し、変更行が許された箇所の中にあること、旧6試験のtest関数名・assertの数（AST）・START行・skip等が同じこと、それ以外がc8ba08fからblob単位で同じこと、パス判定の対照 |

既存の構造ビルダー（h_helpers、ho_helpers、r3_helpers、r4_helpers、d5_helpers）は試験だけで読取り再利用できるが、期待値を同じ新実装で生成しない。採用記録とbasisの期待値は、入力を作った位置と既存の公開関数から独立に計算する。

## 6. 限定欠陥注入

次の18項目を1件ずつ壊し、新規試験の感度を確認する。複数変種なら実件数/IDを別掲し、検出・等価・未検出・準備失敗を分ける。過去B-1〜B-5aの全変異を自動で再実行しない。

1. KINDSに加えるが、view.recordで採用記録を検査しない（素通り）。
2. state_afterの比較を省く。
3. discarded_from_seq＝seqの検査を省く、またはclaimed_schema_version 1を許す。
4. raw_size 0やboolのraw_size、boolのclaimed_head_seqを許す。
5. basisのevidenceと記録のevidenceの比較を省く。
6. request_hashの検査を省く、またはreason_codeを片方だけ見る。
7. claim_requestを呼ばない（IDの重複を見逃す）。
8. restore_before_adoptionを省く（B-1とB-4の両方を別々に）、または復元点＝採用記録を拒否する。
9. `_REQUEST_KINDS`に加えない。
10. prepareでPREFIX_ONLY以外（VALID等）を通す、またはschema 1を通す。
11. adopt_countを診断のcountと照合しない。
12. 移行の痕跡の判定を省く、または読めるSCHEMA_MIGRATIONだけを見てoriginを見ない。
13. IDの重複を実効鎖だけで見る、または捨てる側の読めるIDを見ない。
14. 採用記録のparent・state_after・evidenceの値を誤る（例：claimed_head_seqに診断のverified.head_seqを入れる）。
15. 候補をvalidate_historyに通さない。
16. confirmで元バイトの経路の作り直しを省き、計画のbasisを信頼する。
17. confirmで候補と同じ値の別表現（字下げ）をNO_CHANGEにする、またはstaleとmismatchを取り違える。
18. 計画・結果が内部の参照を返す、またはcommittedをTrueにできる。

新パッケージ自身の判断と、B-1検査器の独立防護、委譲のspyを分類する。冗長な検査の除去で値が変わらないなら、その限定的な等価性と残る防護を記録し、「全検出」にするためだけの無根拠なspyを足さない。等価と分類する場合は、生成器を変えない単一変異の範囲で、反例を探した入力を示す。

## 7. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使い、必要な場合だけスクラッチの単体インタプリタを準備する。依存/設定/workflowを変更しない。
runtimeの通信は禁止。Linuxで使える場合のunshareと、プロセス内socket禁止を区別する。core.autocrlf=falseの別クリーンクローンで最終コードを試験する。`git add`前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。

既存9スイートの計1464件を別掲する。Linuxは1460合格＋Windows専用4 skip。h02・h14と旧範囲試験4本を補正するため「既存試験が全部無編集」と報告しない。test関数を増減しなければ旧件数は維持できる。
Windowsがある場合は新規N＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行し、Linux strict前提のS2全探索はしない。合計は新規N＋988。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_adopt -p "test_a5_*.py" -v

結果文書には、実モデル設定/effort、固定資料の完全SHA/3つのblob、開始/試験/最終SHA、全差分（6ランタイムと6試験の全文）、試行の差分（設計§8）との違いとその理由、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、具体的な採用例（入力の作り方、診断のcount、basisの主要値、確認の状態）、変異一覧・分類、解釈した点、未実施を記す。
**前段階の記録の訂正**として、B-5a結果文書§7の「検査260回」は「失敗するprefix検査260回（prefixの検査は261回、全体検査を含むvalidate_historyの呼出しは合計262回）」であることを1行で記す（B-5aレビュー808ffbdのP-01。B-5aの結果文書・コード・試験は変えない）。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、CONSUME、S3-Cへ進まない。

## 8. 読取専用の保護参照

次の60参照を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-history-s3b5b-20261102も、受け取った版の完全SHAを1本加える（実装時は61参照）。

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
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| docs/v2-history-s3b4-review-20261102 | 814b86190562475286300d7e6df3a749a9140331 |
| fix/v2-history-restore-plan-s3b4-review-20261102 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| docs/v2-history-s3b4-fix-rereview-20261102 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| docs/v2-history-s3b5-review-20261102 | 842d44b192a03531f6d3cb896d8281733814899f |
| docs/v2-history-s3b5-20261102 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136 |
| docs/v2-history-s3b5-v2-rereview-20261102 | 6a7210c2e278e604b953acf904cf9e796c2ce710 |
| feat/v2-history-diagnose-s3b5a-20261102 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6 |
| docs/v2-history-s3b5a-review-20261102 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9 |

## 9. 採用単位

設計§10のD-1（既存ランタイムの変更を6ファイルに限ることと検査規則）、D-2（採用の条件と計画・確認の契約）、D-3（既存試験6本の補正方式。案(a)）、D-4（Sonnet 5.5・high）と、本書の変更境界/受入/欠陥注入/通信禁止/結果保存を一組で判断する。
今回の文書作成と、設計§8の一時環境の試行は、その採用ではない。B-5aの受領をB-5bの実装承認にしない。市場戦略、本番保存先、資格情報、旧工程の採用を再質問する依頼ではない。
