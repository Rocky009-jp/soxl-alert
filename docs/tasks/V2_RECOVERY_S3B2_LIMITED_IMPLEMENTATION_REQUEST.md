# V2 S3-B-2 台帳投影・日次処理・新規ACK／欠測宣言 限定実装依頼案

作成：2026-10-30（日本時間）。第2版：2026-10-30（主担当レビューN-01の補正と任意提案P-01〜P-03の反映、§10）。状態：**第2版・レビュー待ち。限定実装は未承認。**
ユーザーが今回承認したのは、B-2の設計・限定実装依頼書の**作成**まで。本書を受け取った担当者は、採用・着手の明示指示があるまで、コード・試験へ着手しない。本書は、B-2全体の本番採用、既存v2_recoveryの変更（設計§3.3のAPI-1）、新保存形式の採用、S3-C、本番接続を承認する文書ではない。

## 1. 固定版・担当

| 用途 | 固定版 |
|---|---|
| 実装の開始点（コード） | **adfdf765aeca0d01c8f10b596a6fac59d7c1a07e**（fix/v2-history-s3b1-review-20261030）。コード・試験は2b5fa2dと同一で、差はB-1結果文書§13の追記だけ |
| 設計 | [V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md](../specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md) の第2版（資料ブランチ docs/v2-history-s3b2-revision-20261030）。初版は62861137a28e96a361f198f5601e0f5ae77a6910（docs/v2-history-s3b2-20261030）で、実装の根拠にしない |
| 主担当レビュー・補正依頼 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e（docs/v2-history-s3b2-review-20261030）。重大0・通常1（N-01）・提案3（P-01〜P-03） |
| 上位・境界 | S3-B第2版361904b（設計blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7）、B-1採用98e05e4、B-1修正受領e8a94e5、S3第3版2d504de、上位第4版e3e9094、S3-A採用d215193 |

- **実装対象は設計のB-2だけ**：§3.3（U-1でAPI-1が採用された場合だけ）、§4〜§7、§8（U-2でR-aが採用された場合）、§9〜§11。B-3〜B-5、S3-Cは実装の根拠にしない。
- 実装担当案：**Claude Sonnet 5.5、effort high**（設計§15のU-3）。仕様を固定した純粋な投影・計画の実装として選ぶ。ユーザーが別のモデルを指定した場合はそれに従う。実設定は開始時のセッション情報で確認し、取得できなければ不明と記録する。
- 実装を承認された後の新規ブランチ例：feat/v2-history-s3b2-20261030（着手日が違えばその日付）。開始点adfdf765から作る。同名のブランチがあれば上書きせず、別名を使う。

CLAUDE／STATUS／MODEL_POLICY／ROADMAPの必要箇所を確認する。STATUSの古い承認待ちを今回の指示と混同しない。保存・復旧段階のS3と、売却実務側の別分類S3を混同しない。

## 2. 着手条件と資料の固定手順

1. 着手の前に、ユーザーの採用記録で、設計§15のU-1・U-2・U-3の採否を確認する。**本書はU-1＝API-1、U-2＝R-a、U-3＝Sonnet 5.5・highを前提に書いている。** U-1でAPI-0、またはU-2でR-bが選ばれた場合は、本書の§3・§4・§5の該当箇所を補正した版で着手する。担当者が独断で読み替えない。
2. 設計と本書は、渡されたパーマリンクの完全SHAで取得し、そのSHAと両文書のblob SHAを結果文書に記録する。作業中に資料ブランチの更新へ追従しない。
3. 資料ブランチをコードの開始点にしない。資料コミットを丸ごとcherry-pickしない（両文書をコードのブランチへ取り込まない）。
4. 読めない資料・矛盾があれば、読んだふりや独断の仕様変更をしない。

## 3. 変更を許す場所（着手承認後だけ）

作業の順序を固定する：**①v2_recoveryの差分（API-1）と回帰の確認 → ②新パッケージと試験 → ③結果文書**。①の回帰（B2-01・B2-02）が満たせない場合は、②へ進まずに止めて報告する。

| 場所 | 内容 |
|---|---|
| v2_recovery/facts.py 新規（API-1のA1） | `FixedApply`、`FixedFacts.from_parts`、`LedgerContext.from_facts`、`facts_invalid`の生成（設計§3.3）。既存v2_recoveryの公開名と標準ライブラリだけを使う |
| v2_recovery/commands.py 変更（API-1のA2・A3） | `make_records`の前半を本文のまま公開関数`check_commands(ctx, existing, commands)`へ移し、`make_records`はそれを呼ぶ。`_check_late`の宣言型の分岐に、v2の参照形の照合を足す（S3-Aの行は変えない）。**この2点以外の変更をしない** |
| v2_history_ops/ 新規 | 設計§9の公開APIと、その値。標準ライブラリと下記の既存公開名だけを使う |
| tests/v2_history_ops/ 新規 | B2-01〜B2-17の試験、欠陥注入スクリプト（unittestではなく手動実行）。例M・R・R-b・Uの組立てに、tests/v2_history/h_helpers.pyを**読取りだけで**importしてよい。例Vなど足りない組立ては新しい試験用ヘルパーに書く |
| docs/implementation/V2_RECOVERY_S3B2_RESULT.md 新規 | §7の項目 |

**既存の公開名の利用**（読取のみ。下線で始まる名前・privateメソッドは使わない）：
- v2_history：`validate_history`、`History`（from_dict、to_dict、events、digest、head_seq、head_hash、current_state）、`encode_history`、`HistoryCheck`、`Boundary`、`make_history_genesis`（試験）、`migrated_sources`（試験）、values（`history_dict`、`check_json`、種別名の定数）、view（`Segment`、`project_segment`、`normalize_command`、`reasons_for_commands`、`initial_state_dict`）、common（`basis_request_hash`、`is_int`、`is_hex64`、`is_date`、`same`）。
- v2_recovery：facts（API-1の新しい名前）、commands（`check_commands`）、project（`resolve_core`、`slice_check`、`EffectiveLedger`の読取）、common（`requested_text`、`is_requested_text`、`valid_request_id`、`record_reason`、`KIND_ACK`、`KIND_DECLARE`）、ledger（`copy_sessions`、`parse_ledger`、`ledger_digest`、`sessions_digest`、`Row`）、errors（`resolution_invalid`）。
- v2_persistence：codec（`canonical_json`、`sha256_text`、`compute_event_hash`、`CORE_SHA`）、events（`make_genesis_event`、`make_apply_event`、`snapshot_of`、`session_dict`、`project_context`）、recompute（`validate_snapshot`）、runner（`prepare_day`）、plan（`PREPARED`、`NO_COMMIT`、`ALREADY_APPLIED`）、errors（`PersistenceError`）。
- v2_core：`SessionList`、`MarketState`、`parse_iso_date`、各エラー型。

使わない名前：v2_recoveryの`Ctx`、`SnapshotView`、`validate_set`、`make_records`（新パッケージからは呼ばない）、`resolve_observations`・`prepare_resolution_plan`・`confirm_resolution_plan`・`prepare_resolved_day`（S1専用の入力のため）。`Ctx`と同じ属性を持つ別の物を新パッケージで作って規則関数へ渡すことは禁止する。

**変更しないもの**：上記以外の既存v2_core、v2_persistence（localを含む）、v2_recovery（project.py、validate.py、plan.py、daily.py、values.py、ledger.py、common.py、errors.py、`__init__.py`）、v2_history、既存の全試験（コア197、保存ドメイン170、S2 113、S3-A 176、B-1 230）と欠陥注入スクリプト、fixtures、基準データ、研究原本、main.py、依存、設定、workflow、CLAUDE／STATUS／ROADMAP、既存の結果文書。既存パッケージの`__init__.py`への再公開も行わない。

ランタイムは、ファイル・パス・root・ストア・秘密値・口座値を受け取らない。実時計・ネット・プロセス・スレッド・乱数・環境変数を使わない。testsをimportしない。次は作らない：B-3（RESTART_UNKNOWNの計画）、B-4（RECOVERY_RESTOREの計画、CONSUME）、B-5（破損診断、prefix採用）、HistoryReplacement、B-1移行APIの変更、v2用のメモリ／ファイルストア、公開アダプタ、ロック・CAS実行・置換、解錠、CLI、通知・outbox、自動日付・追いつき。

範囲内で実装できない契約の矛盾や、上記以外の既存ファイルの変更が必要だと分かった場合は、具体的な反例・影響・最小差分案を報告し、その変更は行わない。新しい全面レビューや市場計算を自動で追加しない。

## 4. 公開APIと固定する振る舞い

| API | 契約（設計の節） |
|---|---|
| `v2_recovery.facts.FixedFacts.from_parts`、`LedgerContext.from_facts`、`v2_recovery.commands.check_commands` | §3.3。S3-Aの受理・拒否・出力を変えない |
| `read_effective(history)` | §4.1。毎回validate_history。有効記録だけを読む。台帳行・F&G値・session_contextを持たない |
| `project_history_ledger(history, sessions, raw_observations, check_d)` | §5。全区間の照合、§5.2の範囲照合、HistoryLedger（§5.4） |
| `prepare_history_day(history, d, series, sessions, raw_observations)` | §7。`prepare_day`へちょうど1回委譲。親は物理先頭。候補を`validate_history`と全区間の投影に通す |
| `prepare_history_resolution_plan(…)`、`confirm_history_resolution_plan(…)` | §6。構造→証拠→候補全体の順。request_idは§6.5。確認は§6.7の順 |
| `HistoryAppendBatch`、`check_append_batch(history, batch)` | §8.3。生成は日次PREPAREDと確認CONFIRMED_IN_MEMORYだけ。空バッチを作らない |
| 定数 | §9 |

固定する振る舞い：

1. 参照の名前は常にv2物理seq＋event_hash（設計§4.2）。一時S1 seq・hash、`AppendPlan`の期待先頭、`AppliedDay`のseq・event_hash・parent_hashを外へ出さない。移行記録と再生記録のrequest_basisを参照の解決に使わない（§4.3）。
2. 投影は全区間、日次の計算は現在区間（§5.3）。旧区間の宣言・APPLYは現在のfrontierを進めない。境界以前で無所属の日の決定は、解析と`record_id_conflict`の検査だけ。
3. next(D)のconfirmed・close_atだけの変化は無害。境界・D・間のセッションの変化とnext(D)のopen_atの変化は停止（§5.2）。
4. 日次のDと解決のcheck_dは引数で明示し、自動で補わない。D・check_d ≤ 現在区間の境界は`target_not_after_boundary`。
5. 受理した候補を新しい履歴として、同じ入力で同じDを準備するとALREADY_APPLIED（§7.4）。
6. 計画のbasisは§6.6の全キー、plan_hash＝SHA-256(basis)。記録はplan_hash・batch_hashを持たない。
7. committedは常にFalse。どの値も既存`MemoryStore.commit`・`LocalFileStore.commit`へ直接渡すと`plan_type`で拒否される。手で値を組み立てるコードへの防御は主張しない。
8. 戻り値は独立した写しか、再帰的に不変な値。整数欄はboolやfloatを受け付けない（`type(x) is int`）。未検証の値（from_dictで作った計画・バッチ）の表示は、形を再検査してから許可リストだけを出し、不正なら固定表現にする。repr・エラーは固定のcode／field／ruleと安全な件数・seq・hash・日付だけ。raw値・F&G値・URL・note・source_url・パス・例外文を出さない。例外連鎖は抑える。

## 5. 受入条件 B2-01〜B2-17

IDは受入項目であり、テスト関数の件数ではない。新規Nは実測し、件数を増やしただけで品質を主張しない。例M・R・R-b・Uは既存のh_helpersの組立てを使い、例Vは設計§12.3の構造で新しく組み立てる。日付は合成のセッション列でよい。

| ID | 必須の確認 |
|---|---|
| B2-01 既存回帰 | 完全クローンで、既存コア197・保存ドメイン170・S3-A 176・B-1 230を無編集で合格。S2の113件はOS別の契約どおり（Linuxは109合格・Windows専用4件は非対象）。新規Nは別に集計する。§3で許した以外の既存ファイル・fixturesの差分0 |
| B2-02 API-1の回帰 | S3-Aの欠陥注入スクリプトの全目印（各old文字列）が、変更後のv2_recoveryでちょうど1回ずつ現れること（静的な数え上げ、結果を一覧で記録）。commands.pyに関係する変異 M06、M08a、M12、M14、M17〜M19、M29〜M35、M38、M39 を既存スクリプトで再実行し、元の判定（検出か、M18・M31の等価）と同じになること。固定した入力で、変更前後の`prepare_resolution_plan`の`plan_hash`と`make_records`の出力が一致すること。`_check_late`はS3-Aの参照形とv2の参照形の両方で正常例・拒否例を持つ。`FixedFacts.from_parts`の形の不正（seqの重複・bool・未正規のsession dict・context[-2]とdの不一致・解析できないdecision）は`facts_invalid`。`LedgerContext.from_facts`に別の型を渡すと`facts_invalid`／type |
| B2-03 読取と参照写像 | `read_effective`の全キー（設計§4.1）。例R・R-bで、退避した解決記録・APPLYがapplies・resolutionsに入らない。sourceがNATIVE・MIGRATED・REPLAYEDで正しい。requestsは退避記録を含む。FixedFactsのseqがv2 seqで、一時S1 seqでない（例Mで、v1 seqとv2 seqがずれるAPPLYを使って確かめる）。§4.5の現在区間のSnapshotの付け直しが、`project_segment`の結果（d・指紋・skipped）と一致する。FixedApplyの指紋・record_idが、S1の検査器の値と一致する |
| B2-04 全区間と現在区間 | 例V（設計§12.3）の1〜6。旧区間のAPPLYの台帳変更が`ledger_mismatch`、旧区間の宣言日の後発が`late_observation`、旧区間を指すACK／LATEが受理、新区間のDECLAREのfrontierが境界、旧区間の宣言・APPLYでfrontierが進まない、境界以前で無所属の日の決定は止めない |
| B2-05 投影の順序と規則 | 除外→補完（APPLYごとに1回）→version_selection→最終検査の順を、spyと拒否例で示す。全行の解析が除外より先（不正な行は除外されても止まる）。生台帳・History・入力が変わらない。最終台帳の行の並びが入力の並べ順に依存しない。`resolve_core`を実際に呼んでいること（spy） |
| B2-06 セッション範囲 | 設計§12.6の1〜3と、境界セッションの変更（GENESIS境界と再開始の境界の両方）。旧区間の境界の変更も止まる |
| B2-07 日次の結果 | 設計§7.3の各行と§12.1。`prepare_day`がちょうど1回、現在区間のSnapshotと最終台帳で呼ばれること（spy）。返したAPPLYの内容6項目がS1のeventと1バイトも違わず、seq・parent_seq・parent_hashだけがv2の先頭に付け直されている。親がACK・DECLARE・RESTORE・SCHEMA_MIGRATIONの場合も受理される。S1の`AppendPlan`・`PrepareResult`を返さない。core_result.state_updatedの意味を変えない |
| B2-08 再実行の不変条件 | 設計§7.4。GENESISだけ・移行後・再開始後・復元後の各履歴で、PREPAREDの候補を`check_append_batch`で新しい履歴にし、同じ入力で同じDを準備するとALREADY_APPLIED。同じ入力の2回の準備で同じbatch_hash。候補の検査（validate_historyと全区間の投影）を準備時に行っていること（spy） |
| B2-09 再開始後の日次 | 例Uの表（S3-B§7.3）のうち日次の行と、設計§12.3の5。D≤境界、前の区間の最終APPLY日の再処理は`target_not_after_boundary` |
| B2-10 復元後 | 設計§12.4の1〜6。RESTORE#2後に通る投影が、RESTORE#3後には退避したACKを使わないので止まり、例Rで未使用の依頼ID **q7** の新しい依頼（ACK/ADDED(D3, applied_ref=#19)）でREADYになる。同じコマンドをq4（RESTORE#1のID）・q2（DROPされた解決依頼のID）で出すと`history_request_conflict`。退避した記録（#4・#8）を指すコマンドは`ack_evidence`／`late_missing_ref`。例R-bの宣言は#8の値。h_helpersの例Rの依頼IDとID検査を、試験を通すために変えたり弱めたりしない |
| B2-11 移行済み履歴 | 設計§12.2の1〜5。候補の`migrated_sources`が元のv1 SnapshotとSetのdigestを返す |
| B2-12 新規解決の証拠 | 設計§12.5の1〜6。ROW_REMOVED＋ADDED、CHANGED＋ADDEDの両方の順。採用済みN-04（`declare_valid_decision`）。version_selectionの迂回の拒否。LATEの2つの参照形。exclude_applied。ACKのD＞check_d。同じバッチ内の宣言参照の拒否と、連続宣言のfrontier。証拠の判定が`check_commands`を通ること（spy） |
| B2-13 request_id | 設計§6.5の各行（同じID・同内容でNO_CHANGE、requested_atだけの違いでNO_CHANGE、内容違い、複数コマンドの依頼、MIGRATED、REPLAYEDの同内容と内容違い、退避記録だけにあるID、RESTART・RESTORE・MIGRATIONのID）。MIGRATEDは、request_hashが一致する場合（例Mの最初のAPPLYを指す、元と同じbasisのADDED）も一致しない場合も`history_request_conflict`。退避記録だけにあるIDと、RESTOREのIDは、例Rのq2・q4で確かめる（設計§12.4の3） |
| B2-14 計画と確認 | 設計§6.6・§6.7・§12.7。plan_hashがbasis全体に結び付く。改変・確認hashの違いは`history_plan_mismatch`。有効なまま変えた履歴・台帳・sessionsは`history_plan_stale`。確認時の不正な入力は既存エラー（正常な変更と不正な変更を別の受入例にする）。同じ計画の再確認はNO_CHANGE、さらに先頭が進んだ履歴は`history_plan_stale`。確認の手順3は枝A（元の履歴：元のhistory_digestとexpected_head_*）と枝B（候補の履歴：candidate_digestと候補の先頭。元のexpected_head_*は求めない）を別の受入例にし、枝Bの期待basisが設計§6.7の結果表3行目の4項目だけ変わることを示す。§12.7の6の対照で、候補の投影を省いた場合にREADYになることを欠陥注入で示す。既存の未解消の衝突があっても、それを解くACKの計画は作れる |
| B2-15 バッチ値 | 設計§8.3。生成経路が2つだけで、未確認の計画・NO_COMMIT・ALREADY_APPLIED・NO_CHANGEからは作られない。`check_append_batch`の表の1〜6の各拒否（空records、seqの欠け、DAILYで2件、RESOLUTIONで別のrequest_id、候補digestの違い、先頭の違い＝`batch_stale`、batch_hashの改変）。成功時の候補が`validate_history`を通る |
| B2-16 型・不変性・秘匿 | 設計§12.8の1〜3。§12.8の2は、`from_dict`が拒否する例（JSONの深さ超過・巨大整数）と、`from_dict`は値を保持し、確認の手順1／`check_append_batch`の手順1が拒否する例（整数欄のTrue・1.0）を別の受入例にする。全戻り値と候補を`MemoryStore.commit`・`LocalFileStore.commit`へ直接渡すと`plan_type`で拒否。LocalFileStoreの試験用一時rootは`durability="file_sync_only"`とし、Windowsで既定のstrictを試験準備に使わない |
| B2-17 範囲と停止 | ランタイムにI/O・時計・ネット・プロセス・スレッド・乱数・環境変数・依存追加が無い（ASTの走査）。新パッケージが使う既存の名前が§3の一覧の中だけ。新パッケージが`Ctx`・`SnapshotView`・`make_records`・private名を参照しない。B-3〜B-5・S3-Cの機能を作っていない。§3で許した以外の既存ファイルの差分0 |

上位設計の受入（I-08〜I-10、I-15、IB-04、RT-02、RT-06、RT-08、RT-09）のうち、B-2で判定できる部分を対応させる。RT-03・RT-05・RT-07の公開・実行は、B-2で達成済みと書かない。

## 6. 欠陥注入（今回の機能に限る）

最低限、次を一つずつ入れ、対応する試験が失敗することを確認する。等価変異・対象外は件数を分ける。過去の全機能の欠陥注入や、全市場のグリッドは再実行しない（B2-02のcommands.pyの変異の再実行は別）。

1. 投影で、有効記録でなく物理配列の全ACK／DECLAREを使う
2. FixedFactsに現在区間のAPPLYだけを入れる（旧区間を照合しない）
3. 退避した宣言を入れ、再生した宣言を落とす
4. FixedFactsのseqに一時S1 seqを使う
5. 境界セッションを照合しない
6. `LedgerContext.from_facts`でcheck_d ≤ 境界を受け付ける
7. `FixedFacts.latest_apply_day`で境界を無視する（再開始後の宣言のfrontierが旧区間の日になる）
8. `_check_late`のv2分岐でevent_hashを比べない
9. 日次のAPPLYの親を、物理先頭でなく現在区間の最後のAPPLYにする
10. 日次の候補を`validate_history`に通さない（等価なら理由を記録）
11. 日次の候補を全区間の投影に通さない（等価なら理由を記録）
12. 解決計画で、候補の投影を省く（設計§12.7の6で検出）
13. 解決計画で、証拠の前に既存の解決記録での投影を「完成済み」として最終検査する（未解消の衝突を解くACKが作れなくなる）
14. request_idを有効鎖だけで照合する（退避した依頼IDの再利用を受け付ける）
15. MIGRATEDの依頼IDをNO_CHANGEにする
16. 確認で、plan_hashかいずれかの入力digestを無視する
17. 確認時の不正な入力を`history_plan_stale`へ変換する
18. 同じ計画の再確認をstaleにする
19. `check_append_batch`で期待先頭を比べない
20. `check_append_batch`で候補digestを比べない
21. 戻り値で入れ子の参照を共有する
22. ADDEDの元行の判定に、バッチ全体でなく前のコマンドまでのCHANGED／ROW_REMOVEDだけを使う（一方の並べ順が失敗する）

## 7. 環境・結果の保存

Python 3.10／3.11／3.12／3.13で確認し、完全な版を記録する。既存の隔離インタプリタを再利用し、必要な場合だけスクラッチ領域のuv単体Pythonの取得を認める。リポジトリの依存・設定・workflowは変えない。

新規スイートの例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_ops -p "test_*.py" -v

試験は通信禁止とする。Linuxで使える場合はunshare等のOSレベルの遮断を併用し、プロセス内のsocket禁止と区別して記録する。core.autocrlf=falseの別クリーンクローンで最終コードを確認し、結果文書だけの最終コミットとの差分を示す。

新規B-2は純粋関数（B2-16のS2確認だけは一時rootを使う）なので、Windows環境を使える場合は新規Nと既存S3-A・B-1をそのまま実行する。Windowsで既存S2の全探索を実行して、Linux strict前提のエラーを製品不具合に数えない。Windowsが無ければ未実施と記録する。ユーザーのPCや主担当の環境で確認した件数を、作業者自身の実行に置き換えない。

結果文書には次を含める。
- モデルの実設定・effort、開始／試験対象／最終の完全SHA、資料SHAと両blob、追加・変更ファイルの一覧（v2_recoveryの差分は全文を示す）。
- U-1〜U-3の採用記録の参照。
- B2-01〜B2-17とテスト名の対応。既存（コア197・保存ドメイン170・S2 113・S3-A 176・B-1 230）と新規Nを分けた件数・失敗・error・skip・終了コード。OS・Python・クリーンクローン・通信遮断の区分。
- B2-02の目印の数え上げとcommands.pyの変異の再実行結果。
- 公開API・全キー・hash・code／field／rule、v2_recoveryの差分の形。
- 例V・例R・例R-b・例Mでの実測（有効記録、frontier、照合で止まる日、ALREADY_APPLIED、batch_hash）。
- 欠陥注入の一覧（検出・等価・未実施）、解釈した点と設計との差。
- B-2はメモリ上の投影・日次の候補・解決計画・バッチ値であり、保存・公開・解錠・本番・B-3以降を実装していないこと。
- 保護参照の照合（開始時と終了時を分ける）、PR／Actions／本番／通知が無いこと。結果を保存したら止め、B-3以降・S3-Cへ進まない。

## 8. 変更しない参照

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

上の34件は作成依頼§6の一覧、35件目は作成依頼を保存した資料ブランチ（読取専用）。このほか、初版の資料ブランチ docs/v2-history-s3b2-20261030（62861137a28e96a361f198f5601e0f5ae77a6910）とレビューの資料ブランチ docs/v2-history-s3b2-review-20261030（ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e）も書き換えない。本書第2版と設計第2版を保存した資料ブランチ（docs/v2-history-s3b2-revision-20261030）と、採用・着手を記録する資料ブランチも、着手時に渡された完全SHAで固定し、書き換えない。v2_recoveryの差分は、自分の新しい実装ブランチの上でだけ行い、上の参照（特にS3-Aの各ブランチ）を更新しない。

## 9. 採用する単位と停止位置（未採用）

採用する場合の対象は、次の一組とする。
- B-2だけ：§3の追加・変更の場所、§4の公開API、B2-01〜B2-17、§6の欠陥注入。
- 設計§15のU-1（推奨API-1）、U-2（推奨R-a）、U-3（推奨Sonnet 5.5・high）。いずれも作成担当と主担当レビュー（ce07dbd）の推奨で、ユーザーの採用ではない。
- 既存の固定版・回帰の不変、隔離したPythonと通信禁止。
- B-3〜B-5、S3-C、HistoryReplacement、v2用ストア、公開・CAS実行・解錠、ファイル上の移行の実行、本番は含めない。

今回のユーザーの発言は「B-2の設計・限定実装依頼書の作成へ進んでください」であり、この一組の実装採用はまだ得ていない。本書はその判断を代わりに行わない。主担当のレビュー（ce07dbd、重大0・通常1・提案3）を受けて、本第2版で文書を補正した（§10）。補正版を固定SHAで確認した後に、ユーザーが採否を判断する。主担当がU-1＝API-1、U-2＝R-a、U-3＝Sonnet 5.5・highを推奨していることは、ユーザーの採用ではない。

## 10. 第2版の改訂表

| ID | 区分 | 本書の対応 | 設計の対応 |
|---|---|---|---|
| N-01 | 通常 | B2-10の成功例を未使用のq7とし、q4・q2のconflictの対照と、fixture・ID検査を変えないことを明記。B2-13に例Rのq2・q4での確認を追記 | §12.4の3 |
| P-01 | 提案 | B2-13に、MIGRATEDのrequest_hashが一致する場合もconflictとする受入を追記 | §6.5のMIGRATEDの行 |
| P-02 | 提案 | B2-16に、from_dictで拒否する例と、確認／check_append_batchで拒否する例の区別を追記 | §12.8の2 |
| P-03 | 提案 | B2-14に、確認の手順3の枝A・枝Bを別の受入例にすることを追記 | §6.7の手順3・4と結果表3行目 |

§1に第2版の設計と主担当レビューの固定版を、§8に初版とレビューの資料ブランチを追加した。受入ID B2-01〜B2-17、欠陥注入の22件、コード基準adfdf765、既存回帰の不変、変更を許す場所（§3）、公開API（§4）、U-1〜U-3（未採用）は変えていない。
