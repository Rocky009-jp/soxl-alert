# V2 S3-B-1 v2履歴の形式・検査器・明示移行 限定実装依頼案

作成：2026-10-29（日本時間）、初版。状態：**設計案・レビュー待ち。限定実装は未承認。**
ユーザーが今回承認したのは、S3-Bの設計・限定依頼書の**作成**まで。本書を受け取った担当者は、採用・着手の明示指示があるまで、コード・試験へ着手しない。S3-Bの全体、新保存形式の本番採用、S3-C、本番接続を一括で承認する文書ではない。

## 1. 固定版・担当

| 用途 | 固定版 |
|---|---|
| 実装基準（コード） | e68d702de7fa80f141e14b63cf88082c15493994（fix/v2-recovery-resolution-s3a-review-20261029）。コード・試験は885f545と同一 |
| 設計 | [V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md](../specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md)（資料ブランチdocs/v2-recovery-s3b-20261029）。着手時に、渡されたパーマリンクの完全SHAと両文書のblob SHAを記録し、作業中に更新へ追従しない |
| 上位・S3境界 | 上位第4版e3e9094、S3第3版2d504de、S3-A採用記録d215193、S3-A受領abb2e73 |

- **実装対象は設計のB-1だけ**：§3（形式。ただしRECOVERY_PREFIX_ADOPTIONは除く）、§4（監査鎖・有効履歴・鎖ビュー・S1射影・開始境界・検査順）、§5（明示移行）、§6のうち履歴の検査部分、§7.1、§8.1〜§8.6の**検査**、§12。§7.2・§8.7〜§8.9の計画作成、§9〜§11は後続の境界であり、実装の根拠にしない。
- 実装担当案：**Claude Sonnet 5.5、effort high**（設計§14のD-4）。仕様を固定した純粋な検査・変換の実装として選ぶ。ユーザーが新形式の不変条件の実装をOpusに任せると判断した場合は、Opus 5.5・highとする。実設定は開始時のセッション情報で確認し、取得できなければ不明と記録する。
- 実装を承認された後の新規ブランチ例：feat/v2-history-s3b1-20261029。基準e68d702から作り、保護参照や資料ブランチを上書きしない。

CLAUDE／STATUS／MODEL_POLICY／ROADMAPを確認する。STATUSの古い承認待ちの記述を現在の指示と混同しない。モデルの役割や、未知の復旧の意味を独断で変えない。

## 2. 変更を許す場所（着手承認後だけ）

| 場所 | 内容 |
|---|---|
| v2_history/ 新規 | History値・codec、validate_history、鎖ビュー・S1射影、移行の変換・逆変換・計画・確認、make_history_genesis。標準ライブラリと、下記の既存公開名だけを使う |
| tests/v2_history/ 新規 | H-01〜H-14に対応する合成試験。試験専用の記録ビルダー（v2で新規に作るACK／DECLARE、RESTART、RESTORE、再生の記録を作る）を置いてよい。ランタイムからは読み込まない |
| docs/implementation/V2_RECOVERY_S3B1_RESULT.md 新規 | API・キー・hash・rule・試験対応・解釈・欠陥注入・保留・固定SHA・参照照合 |

**既存の公開名の利用**（読取のみ。下線で始まる名前・privateメソッドは使わない）：
- v2_persistence：codec（canonical_json、sha256_text、compute_event_hash、encode_snapshot、decode_snapshot、Snapshot、CORE_SHA、utc_text）、events（GENESIS_KEYS、APPLY_KEYS、SESSION_KEYS、make_genesis_event、make_apply_event、snapshot_dict、snapshot_of、session_dict、project_context、input_hash_of）、recompute（validate_snapshot）、errors（PersistenceError）。
- v2_recovery：validate_resolutions、resolve_observations、empty_resolutions、ResolutionSet、common（record_hash_of、request_hash_of、is_requested_text、requested_text、valid_request_id）、commands（set_dict）、ledger（ledger_digest、parse_ledger、sessions_digest、copy_sessions）。
- v2_core：MarketState、SessionList、parse_iso_date、各エラー型。

既存v2_core、v2_persistence（localを含む）、v2_recovery、既存の試験（コア197＋保存ドメイン170＋S2 113＋S3-A 176）、fixtures、基準データ、研究原本、main.py、依存、設定、workflow、CLAUDE／STATUS／ROADMAP、既存の結果文書は変更しない。既存パッケージの`__init__.py`への再公開も行わない。

ランタイムは、ファイル・パス・root・ストア・秘密値・口座値を受け取らない。実時計・ネット・プロセス・スレッド・乱数・環境変数を使わない。JSON文字列との変換だけはよい。次は作らない：台帳投影・日次処理（B-2）、新規ACK／DECLAREの計画（B-2）、RESTART_UNKNOWN・RECOVERY_RESTOREの計画（B-3・B-4）、CONSUME、破損診断・prefix採用（B-5）、公開値（HistoryReplacement／HistoryAppendBatch）、v2用のメモリ／ファイルストア、解錠、CLI、通知・outbox、自動日付・追いつき。

範囲内で実装できない契約の矛盾や、既存ファイルの変更が必要だと分かった場合は、具体的な反例・影響・最小差分案を報告し、その変更は行わない。新しい全面レビューや市場計算を自動で追加しない。

## 3. 公開APIと固定する振る舞い

| API | 契約 |
|---|---|
| History（from_dict／to_dict／events／head_seq／head_hash／current_state／schema_version／digest）、encode_history、decode_history | S1のSnapshotと同じく、テキストを裏付けにした不変値。構造化した値の取り出しは常に写し。decodeは重複キー・NaN・非JSONを拒否する。内容の検査はしない |
| validate_history(history) | 設計§4.5の順で検査し、問題があれば例外。問題が無ければ、独立した不変のHistoryCheck（§4.5の項目）を返す。何も修復しない |
| make_history_genesis(start_after, sessions) | S1 make_genesisと同じ検査で、GENESISだけのv2履歴を作る |
| migrated_sources(history) | 検査済みの移行範囲から、元のv1 SnapshotとS3-A ResolutionSetを再構成して返す（設計§5.5）。移行していない履歴では固定エラー |
| prepare_migration_plan(snapshot_v1, resolutions, sessions, raw_observations, check_d, request_id, requested_at) | 設計§5.1の再検査→§5.2の変換→validate_historyの順。READYの不変計画を返す。入力は変更しない |
| confirm_migration_plan(plan, confirmed_plan_hash, snapshot_v1, resolutions, sessions, raw_observations) | 設計§5.6。結果はCONFIRMED_IN_MEMORY、committed=False、候補History。保存・適用はしない |
| 定数 | SCHEMA_VERSION_V2=2、種別名7種、READY、CONFIRMED_IN_MEMORY |

固定する振る舞い：

1. ヘッダーはS1と同じ6キーで、schema_version=2、core_shaはS1のCORE_SHA。GENESIS／APPLYのキーはS1と完全に同じ。他の5種のキーは設計§3.3のとおり固定する。B-1ではRECOVERY_PREFIX_ADOPTIONをunsupported_eventとし、RECOVERY_RESTOREのCONSUMEはrestore_op_unsupportedで拒否する。
2. 監査鎖：seqは0基点で連続。RESTOREは`prev_hash`、それ以外は`parent_hash`が、seq−1のevent_hashと一致する。RESTORE以外は`parent_seq==seq−1`。
3. 有効鎖・退避：先頭は常に有効。全RESTOREのsuperseded_seqsの和集合（互いに素）が、有効でない記録の集合と一致する。superseded_seqsは、k−1から有効親をたどった列と完全一致する。物理seqの区間で代用しない。
4. 鎖ビュー：最終の有効鎖と各RESTOREの直前の有効鎖を、それぞれ線形に検査する。ビュー内でRESTOREは透過とする。区間（GENESIS／RESTART）ごとに、既存のmake_genesis_event／make_apply_eventでseq・親hashだけを付け直してS1 Snapshotを作り、**既存validate_snapshot**に通す。付け直したイベントの内容項目とv2の記録が一致することも確かめる。遷移・閾値・状態式を新たに書かない。
5. 制御記録：設計§6の規則（祖先への参照、v2名前空間、LATE、ROW_REMOVED、exclude_applied、check_d、区間内のfrontierとsession_contextの出どころ、バッチ、request_hash、I-15、ビュー内のrequest_idの一意）。台帳に依存する証拠は検査しない。
6. RESTART_UNKNOWN：floorを作成時のビューから計算して完全一致させ、resume_after ≥ floor、≤ check_d、restart_noop、state_afterは初期状態。次の区間の最初のAPPLYは、S1射影で境界からの文脈・skipped_sessionsを検査する。ビュー全体でAPPLY・宣言のDが重複しない（d_unique）。
7. RECOVERY_RESTORE：設計§8.1〜§8.6。復元点の条件（有効、k−1でない、MIGRATION以後、requestバッチの途中でない）、ops・replayとsuperseded_seqsの対応、種別ごとに許す処分、DROPはrequestバッチ単位、直後に途切れず続く作られた記録、REAPPLYの入力の一致（decision／row／prev_row／prev_session_date、共通する文脈）とsame_as_supersededの真偽、REPLAYの参照写像（P以前は不変、REAPPLY／REPLAY先へ写す、DROP／RETIRE先はrestore_ref_unmapped）、DECLAREのfrontier／文脈とRESTARTのfloorの再計算、replay_of、state_after＝復元点。
8. 移行：§5.2の並べ方、§5.3の位置規則、§5.4の写像、§5.5の逆検証（再構成したv1を既存validate_snapshotへ、再構成したSetを既存record_hash_of・validate_resolutionsへ通し、digestを比べる）。移行計画では、既存resolve_observationsで現在の台帳・sessionsに対する投影を再検査してから候補を作る。request_idの衝突はmigration_request_conflict。
9. 計画：basisに設計§5.6の全項目を入れ、plan_hashはbasisのSHA-256。記録はplan_hashを持たない。確認は、形・hash→入力の再検査とdigestの照合→作り直して完全一致、の順。入力が一つでも変わればmigration_plan_stale、改変はmigration_plan_mismatch。committed=False。候補Historyはどのストアにも渡せる型ではない。
10. 戻り値は独立した写しか、再帰的に不変な値。repr・エラーは、固定のcode／field／ruleと安全な件数・seq・hashだけ。raw値・F&G値・URL・note・source_url・パス・例外文を出さない。例外連鎖は抑える。

## 4. 受入条件H-01〜H-14

IDは受入項目であり、テスト関数の件数ではない。新規Nは実測し、件数を増やしただけで品質を主張しない。例M（移行）・例R（3回の復元）・例U（再初期化）は設計§5.7・§8.9・§7.3の構造をそのまま試験fixtureにする。日付は合成のセッション列でよい。

| ID | 必須の確認 |
|---|---|
| H-01 既存回帰 | 完全クローンで、既存コア197＋保存ドメイン170＋S3-A 176を無編集で合格。S2の113件はOS別の契約どおり（Linuxは109合格・Windows専用4件は非対象）。新規Nは別に集計する。既存ファイル・fixturesの差分0 |
| H-02 値とcodec | 不変・写しの取り出し。重複キー、NaN、boolを整数として、未知キー・未知種別、深さ超過、巨大整数を固定エラーで拒否。schema_version=1のSnapshotをvalidate_historyへ渡すとunsupported_schema（自動変換しない）。既存validate_snapshotはv2をunsupported_schemaで拒否する（既存の挙動であり、変更していないこと） |
| H-03 監査鎖 | seqの欠け・重複、監査上の前のhashの違い、event_hashの改変、headの違いを拒否。例Rで、退避した記録（例：4、11）の削除・変更・並べ替えを検出する |
| H-04 有効鎖と退避 | 例Rの最終有効鎖が0、1、2、18〜22で、退避の和集合が{3..17}。RESTOREの有効親がk−1（restore_noop）、退避済みの記録（5、12）（restore_point_not_effective）、MIGRATIONより前（restore_before_migration）、requestバッチの途中（restore_point_in_batch）をそれぞれ拒否 |
| H-05 退避一覧 | RESTORE#3のsuperseded=[7,8,9,14,15,16,17]を受理し、物理区間[3..17]や過不足・順序違いをsuperseded_mismatchで拒否 |
| H-06 復元バッチ | 作られた記録の途中で終わる履歴（restore_incomplete）、作られた記録の間に別の記録を挟む、APPLYにREPLAY／DROP（restore_op_kind）、requestバッチの一部だけDROP（restore_partial_batch）、REAPPLYでdecisionかrowを変える（restore_reapply_input）、same_as_supersededの偽り・replayのseqの違い（restore_replay_mismatch）、REPLAYで参照を写さない・DROP先を指す（restore_ref_unmapped）、RETIRE以外のRESTORE処分、CONSUME（restore_op_unsupported）。RESTORE#1でRESTARTをDROPした後のREAPPLYがsame=falseで受理され、例RのREPLAY（5→9の参照写像）が受理される |
| H-07 S1射影 | 各区間を既存validate_snapshotで検査していることを、実際に参照する名前のspy／差し替えで確認する。APPLYのtransition_result・state_after・input_hash・skipped_sessions・session_contextの改変は"s1:"付きのruleで拒否。APPLYの後にACK・DECLAREを挟んでもIB-04が通る。制御記録のstate_afterの改変はstate_after。RESTOREのstate_afterの改変はrestore_state |
| H-08 制御記録 | v2名前空間の参照（祖先のみ、後の記録を根拠にしない）、applied_ref／missing_ref（APPLY型・宣言型）の各不一致、LATEのビュー内APPLY、ROW_REMOVEDの非空一覧、exclude_applied、check_dの境界（区間の境界より後・最新APPLY日以上・d ≤ check_d、作成時の値で判定）、区間内のfrontierと3種類の出どころ、バッチの欠け・順序、request_hash、reason_code、ビュー内のrequest_idの重複を拒否。正常な延長で古い記録が失効しない |
| H-09 再初期化 | 例Uの履歴を受理。floorの3値がそれぞれ効く（最後のAPPLY日・宣言日・前の境界を下回るとrestart_floor）、floorの値の偽り、resume_after > check_d、restart_noop、state_afterが初期状態でない、boundary_sessionの日付違い・未確定を拒否。境界以前のDのAPPLYを足した履歴はS1射影で拒否。再初期化の後のACK・DECLAREで、HistoryCheckのprocessing_afterとcurrent_boundaryが動かない |
| H-10 移行の変換 | 例M（ADDED、DECLARE、LATEの宣言参照）に、ROW_REMOVED・CHANGED・APPLY参照のLATEを加えた例と、空のSetの例で、記録の並び、event_map／resolution_map、v2名前空間の参照、request_basisが元のままであること、APPLYの内容項目が元と1バイトも違わないこと、GENESISと例Mのv1 seq1のhashがv1と同じことを確認。migrated_sourcesで取り戻したv1 SnapshotとSetのdigestが元と一致し、既存validate_snapshot／validate_resolutionsが実際に呼ばれる（spy） |
| H-11 移行の拒否 | 不正なv1・不正なSet・現在の台帳で投影が通らない（既存のcodeのまま）・request_idの衝突・check_dの範囲外では候補を作らない。履歴側では、MIGRATIONの対応表・source・source_resolutionsの改変、originの改変、MIGRATIONより後のorigin、MIGRATIONが2件、移行範囲にRESTART／RESTORE、移行した記録の位置（source_head）の違いを、それぞれ固定ruleで拒否 |
| H-12 計画と確認 | plan_hashはbasis全体に結び付く。snapshot・Set・台帳・sessionsのどれを変えてもmigration_plan_stale。計画の改変・確認hashの違いはmigration_plan_mismatch。確認結果はcommitted=False。候補・計画・確認結果は、MemoryStore.commit／LocalFileStore.commitへ直接渡すと既存のplan_typeで拒否される。v2の正規化テキストを専用の一時rootのsnapshot.jsonに置くと、既存LocalFileStore（durability="file_sync_only"）のread・initializeがunsupported_schemaで止まり、ファイルのバイト列とディレクトリの中身が変わらない。Windowsで既定のstrictを試験準備に使わない |
| H-13 不変性と秘匿 | 入力・戻り値の入れ子を変えても、元のHistory・Snapshot・Set・計画が変わらない。repr・エラー・計画の表示に、raw行・F&G値・URL・自由文・パスが出ない |
| H-14 範囲と停止 | ランタイムにI/O・時計・ネット・プロセス・スレッド・乱数・環境変数・依存追加が無い。解錠・公開・通知・日次処理・台帳投影・復元／再初期化の計画を作っていない。既存パッケージのファイル差分0 |

追加回帰として、上位設計のI-08〜I-10・I-15・IB-04、RT-02・RT-06・RT-08・RT-09のうち、履歴の検査で判定できる部分を対応させる。RT-02・RT-03・RT-05・RT-07の計画・確認・公開は、B-1で達成済みと書かない。

## 5. 欠陥注入（今回の機能に限る）

最低限、次を一つずつ入れ、対応する試験が失敗することを確認する。等価変異・対象外は件数を分ける。過去の全機能の欠陥注入や、全市場のグリッドは再実行しない。

1. superseded_seqsを物理区間で計算する
2. 退避した記録の監査鎖・event_hashを検査しない
3. 退避済みの復元点を受け付ける
4. 途中で切れた復元バッチを受け付ける
5. REAPPLYでdecision／rowの一致を見ない
6. same_as_supersededの真偽を見ない
7. REPLAYの参照を写さない（元のseqのまま受け付ける）
8. requestバッチの一部だけのDROPを受け付ける
9. S1射影で、APPLYの親を「ビュー上の直前」でなく「物理的な直前」にする
10. RESTART_UNKNOWNのfloorで宣言日を無視する
11. 同じくprev_boundaryを無視する
12. DECLAREのfrontierで区間の境界を無視する
13. 参照先が祖先であることを検査しない（後の記録を根拠にできる）
14. 移行の逆検証でv1 Snapshotのdigestを比べない
15. 移行した記録のS3-A hash（origin.resolution_hash）を再計算しない
16. MIGRATIONより後のoriginを受け付ける
17. 移行計画でresolve_observationsの再検査を省く
18. plan_hashかいずれかの入力digestを確認で無視する
19. 戻り値で入れ子の参照を共有する

## 6. 環境・結果の保存

Python 3.10／3.11／3.12／3.13で確認し、完全な版を記録する。既存の隔離インタプリタを再利用し、必要な場合だけスクラッチ領域のuv単体Pythonの取得を認める。リポジトリの依存・設定・workflowは変えない。

新規スイートの例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history -p "test_*.py" -v

試験は通信禁止とする。Linuxで使える場合はunshare等のOSレベルの遮断を併用し、プロセス内のsocket禁止と区別して記録する。core.autocrlf=falseの別クリーンクローンで最終コードを確認し、結果文書だけの最終コミットとの差分を示す。

新規B-1は純粋関数（H-12のS2確認だけは一時rootを使う）なので、Windows環境を使える場合は新規Nをそのまま実行する。Windowsで既存S2の全探索を実行して、Linux strict前提のエラーを製品不具合に数えない。S2のWindows専用4件は既存の手順で確認し、Windowsが無ければ未実施と記録する。ユーザーのPCや主担当の環境で確認済みの件数を、作業者自身の実行に置き換えない。

結果文書には次を含める。
- モデルの実設定・effort、開始／試験／最終の完全SHA、資料SHAと両blob、追加ファイルの一覧。
- H-01〜H-14とテスト名の対応。既存（コア197・保存ドメイン170・S2 113・S3-A 176）と新規Nを分けた件数・失敗・error・skip・終了コード。OS・Python・クリーンクローン・通信遮断の区分。
- 7種のキー、hash、HistoryCheckの項目、各code／field／rule、鎖ビューとS1射影の実装方式。
- 例M・例R・例Uの実測（有効鎖、退避一覧、対応表、same_as_superseded、processing_after）。
- 欠陥注入の一覧（検出・等価・未実施）、解釈した点と設計との差。
- B-1はメモリ上の形式・検査・移行計画であり、台帳投影・日次・復元／再初期化の計画・破損診断・公開・解錠・本番を実装していないこと。
- 保護参照の照合（開始時と終了時を分ける）、PR／Actions／本番／通知が無いこと。結果を保存したら止め、B-2以降・S3-Cへ進まない。

## 7. 変更しない参照

開始時と終了時に、それぞれ完全SHAで照合し、この一覧へ書き込まない。開始時の照合を省かない。

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

上の24件は作成依頼§5の24参照で、25件目はS3-Aの受領確認を保存した資料ブランチ（読取専用）。本書を保存した資料ブランチdocs/v2-recovery-s3b-20261029も、着手時に渡された完全SHAで固定し、書き換えない。

## 8. レビュー後に採用する単位（未採用）

採用する場合の対象は、次の一組とする。
- B-1だけ：v2履歴の値・codec・全7種の検査器（復元バッチ・再初期化を含む、CONSUMEとprefix採用は拒否）、make_history_genesis、migrated_sources、明示移行の計画・確認。§2の追加場所だけ。
- 設計§14のD-1（形式とB-1の範囲）、D-2（復元点はMIGRATION以後）、D-4（担当モデル・effort）。
- H-01〜H-14、既存の固定版・回帰の不変、隔離したPythonと通信禁止。
- B-2〜B-5、S3-C、公開値、v2用ストア、ファイル上の移行の実行、実解錠・復元・再初期化の実行、本番は含めない。

今回のユーザーの発言は「S3-Bの設計・限定依頼書の作成へ進める」であり、この一組の実装採用はまだ得ていない。本書はその判断を代わりに行わない。レビューで重大・通常の指摘があれば文書を補正し、その後にユーザーが採否を判断する。
