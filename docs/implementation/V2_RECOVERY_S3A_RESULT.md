# V2 S3-A 確認・欠測宣言の解決 限定実装 結果

2026-10-29（日本時間）。担当：Sonnet 5.5・high。本書はS3-Aの限定実装の結果記録であり、**復旧機能を本番へ採用したという意味ではない**。S3-A は**メモリ上の候補確認だけ**で、ACKの永続化・実ファイルの解錠・履歴の復元・再初期化・本番通知は実装していない（§10）。S3-B／Cは着手していない。

## 1. 結論

- 受入条件 C-01〜C-14 を実施した。**実Linux（クラウドVM）で全て合格**。**実Windows、ユーザーのPC、物理電源断、autocrlf=true は未実施**で、合格に数えていない。
- 既存**367件**（コア197＋保存ドメイン170）は無編集で、Python 3.10.20／3.11.17／3.12.3／3.13.17の全てで合格（失敗0・error0・skip0）。
- S2の既存**113件**は4版とも「109合格＋4 skip（Windows実機専用。Linuxでは未実行＝未実施）」。失敗0・error0。
- 新規**155件**は4版とも全て実行・合格（失敗0・error0・skip0）。
- 欠陥注入は53件中**49件を検出、4件は等価（検出不能の理由を記録）、未検出0**。
- 範囲外の変更は必要なかった。既存ファイルの差分は0（新規ファイルのみ）。
- 採用記録のとおり **N-04 を採用**（有効なdecisionが1件だけある日の欠測宣言は `declare_valid_decision` で拒否）。

## 2. 固定した版・環境

| 項目 | 内容 |
|---|---|
| 採用記録 | docs/decisions/V2_RECOVERY_S3A_ADOPTION_20261029.md、コミット `d215193065ebf110e6a77f22edf208b390138285` |
| 資料（設計・依頼） | `2d504de7cbf4628a3760d48f70fd0228dce6a61c`。設計 docs/specs/V2_RECOVERY_S3_DESIGN_DRAFT.md の blob `97977f6e3a56c080db26d976b55ce42d5fd69e21`、依頼 docs/tasks/V2_RECOVERY_S3A_RESOLUTION_REQUEST.md の blob `cc9e1584e1eeb224649e9ddb10179c42d2804ae9` |
| コード開始点（base） | `d404d4df481957f89201c5169f3a75d7b9d86b66` |
| 実装ブランチ | feat/v2-recovery-resolution-s3a-20261029（新規。既存ブランチは上書きしていない） |
| **試験対象（コード＋試験）** | **`3b71816f5d4fd08b0a065e3f92e189944ac604d5`** |
| 保存最終 | 試験対象に本書だけを追加したコミット。本書は自身のSHAを含められないため、完全SHAは完了報告に記載。試験対象との差分は本書1ファイルのみ |
| モデル・エフォート | 作業セッションのメタデータ（get_session）で configured_model `claude-sonnet-5-5[1m]`、last_served_model `claude-sonnet-5-5`、effort_level `high`。Rockyの指定（Sonnet 5.5・high）と一致 |
| OS | Ubuntu 24.04.5 LTS（クラウドVM、カーネル 6.18.44） |
| Python | 3.10.20（uv単体インタプリタ、スクラッチ領域）、3.11.17、3.12.3、3.13.17（システム）。取得だけが通信を使用 |
| クリーンクローン | 試験対象3b71816を新規クローンして実行。実行後 `git status` は clean。`core.autocrlf=false` |
| 通信遮断 | クリーンクローンの試験は `unshare -rn`（ネットワーク名前空間を分離）で実行。試験自身もソケット・HTTP等を遮断する helper を持つ（C-14）。`-B -W error::ResourceWarning` を指定 |

## 3. 追加ファイル（すべて新規。既存ファイル差分0）

`git diff --name-status d404d4d 3b71816` は A（追加）のみ24件。

- `v2_recovery/`（1,433行）：`__init__.py`、`errors.py`、`ledger.py`、`values.py`、`common.py`、`validate.py`、`project.py`、`commands.py`、`plan.py`、`daily.py`
- `tests/v2_recovery/`：`r_helpers.py`、`test_c02_all_rows_parsed.py`、`test_c03_added.py`、`test_c04_c05_changed_removed.py`、`test_c06_late.py`、`test_c07_declare.py`、`test_c08_daily.py`、`test_c09_refs_state.py`、`test_c10_plan.py`、`test_c11_sessions.py`、`test_c12_delegation.py`、`test_c13_immutability_privacy.py`、`test_c14_scope_and_stop.py`、`sensitivity_check.py`（欠陥注入。unittestではなく手動実行）
- `docs/implementation/V2_RECOVERY_S3A_RESULT.md`（本書）

## 4. 試験結果

### 4.1 件数（4版共通）

| 区分 | 件数 | 結果 |
|---|---|---|
| 既存コア（tests/v2_core） | 197 | 全合格 |
| 既存保存ドメイン（tests/v2_persistence） | 170 | 全合格 |
| 既存合計 | **367** | 無編集で合格 |
| S2既存（tests/v2_persistence_local） | 113 | 109合格、4 skip（Windows実機専用＝Linuxでは未実施）。失敗0・error0 |
| **新規 S3-A（tests/v2_recovery）** | **155** | 全合格（失敗0・error0・skip0） |

| Python | コア | 保存ドメイン | S2 | 新規 | 終了コード |
|---|---|---|---|---|---|
| 3.10.20 | 197 OK | 170 OK | 113（4 skip） | 155 OK | 全て0 |
| 3.11.17 | 197 OK | 170 OK | 113（4 skip） | 155 OK | 全て0 |
| 3.12.3 | 197 OK | 170 OK | 113（4 skip） | 155 OK | 全て0 |
| 3.13.17 | 197 OK | 170 OK | 113（4 skip） | 155 OK | 全て0 |

### 4.2 C-01〜C-14とテストの対応

| 受入条件 | 試験ファイル（件数） | 主なテスト名 |
|---|---|---|
| C-01 既存回帰 | 既存スイート（上表）。差分0は `git diff --name-status` で確認 | 既存367＋S2 113 |
| C-02 全行解析 | test_c02_all_rows_parsed（8） | unparsable_values_stop_with_the_core_input_error／a_bad_row_cannot_be_named_away／a_bad_value_is_never_downgraded_to_no_signal／conflict_between_versions_is_not_hidden_by_an_empty_set |
| C-03 ADDED | test_c03_added（16） | the_added_row_alone_is_excluded／it_cannot_hide_the_fixed_row_of_another_apply／no_evidence_when_the_original_is_missing／added_alone_is_refused／changed_plus_added |
| C-04 CHANGED | test_c04_c05_changed_removed Changed（6） | replacement_without_the_original_supplements_exactly_one_row／original_alongside_the_changed_row_is_not_supplemented_twice／the_original_at_another_utc_offset_counts_as_present／changed_role_or_status_is_bound_by_fingerprint_and_not_adopted |
| C-05 ROW_REMOVED | 同 RowRemoved（5） | empty_ledger_is_confirmed_then_supplemented_then_checked／the_row_comes_back_and_is_not_supplemented_twice／refusals／removed_plus_added_in_one_batch_and_added_alone |
| C-06 LATE | test_c06_late（12） | the_late_row_stops_without_an_acknowledgement／late_is_accepted_without_apply_of_d_and_without_a_supplement／the_declaration_is_found_by_number_hash_and_day |
| C-07 欠測宣言 | test_c07_declare（18） | no_decision_at_all_is_declared_with_an_empty_list／two_conflicting_decisions_are_declared／one_valid_decision_is_never_turned_into_a_gap／missing_and_extra_fingerprints／unconfirmed_day |
| C-08 日次接続 | test_c08_daily（7） | the_declared_day_is_no_commit／next_apply_follows_the_gap_rule_in_three_fg_bands／streak_after_a_gap_with_fg_at_least_30_is_one_not_zero／extending_the_snapshot_with_an_independent_s1_apply_keeps_the_records_valid |
| C-09 参照と状態 | test_c09_refs_state（20） | chain_head_and_sequence／truncated_batch／source_head_prefix_and_state／namespaces_are_not_mixed／a_record_stays_valid_when_the_snapshot_grows_and_is_judged_by_its_own_prefix |
| C-10 計画の確認 | test_c10_plan（23） | edited_plan_is_refused_by_its_hash／forged_plan_with_a_recomputed_hash_is_refused_by_the_rebuild／every_input_change_after_the_plan_is_stale／nothing_is_changed_when_one_command_of_a_batch_fails／same_id_with_different_content_is_a_conflict |
| C-11 セッションと同一性 | test_c11_sessions（9） | a_changed_open_time_of_the_next_session_stops／only_close_time_or_confirmed_flag_of_the_next_session_is_accepted／the_plan_digest_is_stricter_than_the_ordinary_projection |
| C-12 委譲と一致 | test_c12_delegation（8） | prepared_no_commit_and_already_applied／prepare_day_is_called_once_with_the_final_ledger／no_plan_and_no_s1_types_are_exposed_even_with_an_empty_set／no_market_rule_is_copied |
| C-13 不変性と秘匿 | test_c13_immutability_privacy（12） | returned_nested_values_cannot_change_the_originals／several_unresolved_places_are_resolved_in_one_batch_or_not_at_all／urls_and_notes_never_reach_a_repr_an_error_or_a_plan |
| C-14 範囲と停止 | test_c14_scope_and_stop（11） | no_io_clock_process_or_randomness_calls／nothing_unlocks_restores_restarts_or_persists／memory_store_refuses_every_such_value_and_stays_unchanged／local_file_store_on_an_empty_uninitialized_root_stays_empty |

新規件数の内訳：8＋16＋11＋12＋18＋7＋20＋23＋9＋8＋12＋11＝155。

C-14のLocalFileStore確認は、再レビューQ-02に従い、空の未初期化root、および `file_sync_only` で初期化した root だけで行う（Windowsの strict では initialize が拒否されるため）。

## 5. 実装の形

### 5.1 公開API（`v2_recovery/__init__.py`）

`empty_resolutions` `validate_resolutions` `resolve_observations` `prepare_resolution_plan` `confirm_resolution_plan` `prepare_resolved_day` `encode_resolutions` `decode_resolutions`、型 `ResolutionSet` `ResolutionCheck` `EffectiveLedger` `ResolutionPlan` `ConfirmResult` `SimulationDayResult`、定数 `READY` `NO_CHANGE` `CONFIRMED_IN_MEMORY`。

### 5.2 キー

- **ResolutionSet**：schema `soxl-v2-resolution-set/1`、キー `schema` `head_resolution_seq` `head_resolution_hash` `records`。不変・テキスト裏付け・ハッシュ鎖。encode/decode は厳格（重複キー・NaN拒否）。
- **記録（RECORD_KEYS）**：`resolution_seq` `parent_resolution_hash` `resolution_hash` `request_id` `request_hash` `request_basis` `command_index` `command_count` `kind` `variant` `d` `source_head_seq` `source_head_hash` `state_after` `record_fingerprints` `applied_ref` `missing_ref` `session_context` `frontier_before` `ledger_digest` `reason_code` `requested_at`。
- **指示（COMMAND_KEYS）**：`kind` `variant` `d` `record_fingerprints` `applied_ref` `missing_ref`。
- **計画の basis**：`operation` `status` `snapshot_digest` `expected_head_seq` `expected_head_hash` `resolutions_before_digest` `request_id` `request_hash` `requested_at` `check_d` `reason_code` `ledger_digest` `sessions_digest` `commands` `candidate_resolutions` `candidate_digest` `expected_state_digest` `excluded_fingerprints` `supplemented` `effective_digest`。`plan_hash` は basis の正規化JSONのsha256。計画の `summary()` は許可リスト方式（件数・日付・参照番号・hashだけ）。
- **EffectiveLedger**：`rows`（6列）`excluded_fingerprints` `supplemented` `ledger_digest` `effective_digest` `resolutions_digest` `check_d`。取り出しは常にコピー。repr に行を出さない。
- **種別**：kind は `ACK`／`DECLARE_MISSING`、variant は `ADDED`／`CHANGED`／`ROW_REMOVED`／`LATE`、reason_code は `ACKNOWLEDGE_LEDGER_CHANGE`／`MARK_SESSION_MISSING`／`RESOLUTION_BATCH`。
- **状態**：計画は `READY`／`NO_CHANGE`、確認結果は `CONFIRMED_IN_MEMORY`／`NO_CHANGE`。`committed` は常に False。

### 5.3 参照の名前空間

- `applied_ref`：`{seq, event_hash, fingerprint}`。S1のAPPLYイベントを seq と event_hash で指し、そのAPPLYの固定指紋と一致を要求。
- `missing_ref`：`{kind:"APPLY", seq, event_hash}`（skipped_sessions を持つAPPLY）または `{kind:"DECLARE_MISSING", resolution_seq, resolution_hash}`（宣言記録）。二つの名前空間は混ぜない（`namespaces_are_not_mixed`）。

### 5.4 source_head prefix の扱い（方式の記録）

記録は作成時の S1 履歴の先頭部分（`source_head_seq`／`source_head_hash`）に対して判定する。**prefix を記録ごとに再検証しない**。現在のSnapshot全体を `validate_snapshot` で**1回だけ**検査し（`SnapshotView`）、その検査済み履歴から seq と event_hash で各 prefix を読み出す方式にした。未検査の prefix は採用せず、古い検査結果の使い回しもしない（呼び出しごとに検査）。通常のAPPLYでSnapshotが伸びても、古い記録は自身の prefix で判定されるため無効にならない（`a_record_stays_valid_when_the_snapshot_grows_and_is_judged_by_its_own_prefix`）。逆に、記録より後のAPPLYをその記録の証拠に使うことは拒否する（`an_apply_made_after_the_record_cannot_be_used_as_its_evidence`）。

### 5.5 code／field／rule

- code：`resolution_invalid`（field は検査対象名、rule は下記）、`resolution_request_conflict`（field `request_id`）、`resolution_plan_mismatch`／`resolution_plan_stale`（field `plan`）。コア／S1由来の code（`snapshot_invalid`、入力エラー、`ledger_mismatch`、`late_observation`、`session_context_missing`／`session_context_mismatch`）は変えずに通す。
- rule：`ack_evidence` `session_context` `missing_ref` `batch` `late_missing_ref` `request_basis` `head` `fingerprints` `declare_frontier` `applied_ref` `variant` `source_head` `type` `json` `reason_code` `exclude_applied` `declare_applied` `check_d` `state_after` `seq` `schema` `version_selection` `json_type` `json_number` `json_key` `json_depth` `command_shape` `plan_shape` `request_id` `resolution_hash` `requested_at` `request_hash` `request` `records` `record_keys` `parent_hash` `ledger_digest` `kind` `header_keys` `declare_valid_decision` `declare_unconfirmed` `declare_incomplete`。
- エラー文は code／field／rule の固定文字列だけ。値・URL・メモは含まない（`error_text_is_fixed_code_field_rule_only`）。

## 6. ROW_REMOVED／LATE／CHANGED の実測

いずれも合成fixtureでの試験結果。市場価格や口座の実測ではない。

- **CHANGED**
  - 元行なしで置換版だけがある場合：置換版を除外し、保存済みdecisionを**1件補完**、最終台帳は保存行1件（`replacement_without_the_original_supplements_exactly_one_row`）。
  - 元行が併存する場合：補完**0件**（二重補完しない）。元行が別のUTCオフセットで届いても同じ行として補完0（指紋は時刻を正規化）。
  - 元の role／status が変わった置換版も、指紋で束縛して除外し、新版を採用しない。
  - 元行の指紋そのものを除外する指示は `exclude_applied` で拒否。
- **ROW_REMOVED**
  - 行なし・空一覧で「確認→1件補完→最終検査」の順に通る。補完後のAPPLY再計算は `ALREADY_APPLIED`。
  - 元行が再出現した場合は補完**0件**（二重補完しない）。
  - 拒否（rule `ack_evidence`）：applied_ref なし、event_hash 相違、指紋相違、非空一覧、元行が残っている、同じIDの未確認の変更版が残っている。
  - 同一APPLYの補完は、複数の記録があっても**1回だけ**。
- **LATE**
  - 参照は **APPLY参照**（skipped_sessions を持つAPPLY）と**宣言参照**（DECLARE_MISSING記録を seq・hash・日で特定）の両方で通る。対象DのAPPLYは不要で、補完は**0件**。
  - 拒否：参照違い、対象日がそのAPPLYの skipped_sessions にない、対象日にAPPLYがある（rule `late_missing_ref`）、`applied_ref` を付けた指示（`ack_evidence`）、空一覧、固定行を隠す指示。
  - 宣言後に現れた新しい行は、LATEで確認するまで停止する。対象日が check_d より後なら拒否、等しければ通る。

## 7. N-01〜N-04の反例と期待値

| 反例 | 修正後の期待 | 対応するテスト | rule |
|---|---|---|---|
| N-01：解決済みの日次結果をS1の `AppendPlan` として返し、LocalFileStore／MemoryStore がそのまま commit できてしまう | 専用 `SimulationDayResult` だけを返す（`committable=False`、`committed=False`、plan プロパティなし）。空のSetでもAppendPlanを返さない。ストアはこれらの値を型で拒否し、内容は不変 | test_c12 `no_plan_and_no_s1_types_are_exposed_even_with_an_empty_set`、test_c14 `memory_store_refuses_every_such_value_and_stays_unchanged` | （ストア側 `snapshot_invalid` rule `plan_type`） |
| N-02：元行を削除して別IDで打ち直す場合に ADDED が元行なしで拒否される | `{ROW_REMOVED, ADDED}` を同じ要求バッチで確認すれば通り、補完後の台帳は固定行1件。ADDED単独は拒否 | test_c04_c05 `removed_plus_added_in_one_batch_and_added_alone`、test_c03 `changed_plus_added` | `ack_evidence` |
| N-03：除外の結果、同じ record_id の別版だけが残り、版の選択が回避される | 除外後に、未確定の同IDの別版が残るなら拒否。残る版が既存APPLYの固定指紋と一致する場合だけ許す | test_c13 `added_cannot_select_one_of_two_versions`／`changed_next_to_the_fixed_old_version_is_allowed`、test_c06 `excluding_one_version_of_a_shared_id_is_a_version_choice`、test_c07 `one_version_alone_is_a_version_choice_and_both_days_together_are_not`、test_c04_c05 `a_not_yet_acknowledged_third_version_stops` | `version_selection` |
| N-04：有効なdecision 1件の日も欠測として除外できてしまう | 有効1件は拒否。0件またはDに関係する妨害（衝突・窓外・別ターゲット・同じIDの別版）のときだけ宣言可。完全に同一の再送は妨害ではなく有効1件のまま | test_c07 `one_valid_decision_is_never_turned_into_a_gap`／`identical_resubmission_is_still_one_decision`／`an_unrelated_conflict_on_another_day_is_no_reason` | `declare_valid_decision` |

他のruleの対応：`declare_incomplete`＝宣言の名指し不足／余分（test_c07 `missing_and_extra_fingerprints`）、`declare_unconfirmed`＝未確定のセッション日（`unconfirmed_day`）、`late_missing_ref`＝LATEの対象日にAPPLYがある／欠測参照が合わない（test_c06 `a_day_with_an_apply_is_refused`、`wrong_references_are_refused`）。

## 8. 欠陥注入

方式：作業ツリーを一時ディレクトリにコピーし、`v2_recovery` の複製に欠陥を1つだけ入れて新規スイートを実行し、失敗することを要求する（`tests/v2_recovery/sensitivity_check.py`。実ツリーは変更しない）。Python 3.13で実行。

- 実行53件：**検出49、等価4、未検出0**（setup誤りも0）。
- 検出した主な欠陥：不正行の黙殺、record_id による除外、LATEが補完する、固定行を除外できる（新規指示／保存済み記録の両方）、補完の無条件化／全廃、各種hash・prefix・check_d・state_after・frontier・sessions比較の削除、ledger_digest の順序依存／件数無視、最終台帳の行順の変更ほか。
- **等価（検出不能）として数えなかった4件**：
  - M02：補完判定を除外前の生の台帳で行う変更。固定行は除外されないため、生の台帳と除外後が一致する。
  - M15：request hash の関数を保存側・検査側で一貫して変える変更。両側が同じ関数のため外から見えない。
  - M18：作成時に既存の宣言を frontier に使わない変更。候補を `validate_set` が自身の frontier で再検査し、同じruleを出す。
  - M31：元行が残るのに ROW_REMOVED を受け入れる変更。未確認の同IDの別版の検査が包含する。
- 未実施：上記53件以外の欠陥は未実行。

## 9. 解釈した点と設計との差

設計の文言が複数に読める箇所は次のように解釈した。差があれば明示する。

1. **ADDED／CHANGED／ROW_REMOVED／LATE の証拠**：Q-01どおり「補完権限」ではなく「証拠」として扱う。補完は CHANGED／ROW_REMOVED のみ、同じAPPLYにつき1回、除外後に保存指紋が無い場合だけ。
2. **宣言の frontier**：直近APPLY日（なければ start_after）と宣言済み日の最大。宣言できるのは次のセッションだけで、同じバッチ内の先行宣言も数える。宣言後に再宣言、日のスキップ、check_d より後は拒否。
3. **check_d**：新規のACK／宣言は D ≤ check_d。check_d は最新APPLY日以上（再実行を許す）かつ start_after より後。既存記録が check_d より後でも、それだけでは拒否しない。LATE の対象日は check_d 以下（Q-03）。
4. **セッション文脈の投影**：next(D) は date と open_at だけを残す（close_at／confirmed は後日変わり得るため）。計画の `sessions_digest` は全列で、通常の投影より厳格（意図した差）。
5. **検査順**：セッション検査を行解析より先に行い、その後に全行を個別に解析する（既存の入力エラーcodeを保つため）。名指しされていない不正行でも、先に既存入力エラーで停止し、未観測やNO_SIGNALに変えない。
6. **request_hash**：`requested_at` を含めず、`check_d` を含む（P-01）。同じ request_id・同じ内容なら `requested_at` が新しい場合だけ元の記録と時刻を保って NO_CHANGE、内容が違えば `resolution_request_conflict`。
7. **ledger_digest**：順序とUTCオフセット表記に依存せず、件数は保つ（重複は数える）。
8. **prefix検査**：§5.4。設計が許す最適化（現在Snapshot全体の検査結果からの導出）を採った。
9. **設計との差**：設計が定める項目の削除・追加はない。ResolutionSet は S1 の保存形式に混ぜない（C-14）。

## 10. S3-Aの範囲の表明

S3-A は**メモリ上の候補確認のみ**。次は実装していない：ACKの永続化、実ファイルの解錠、履歴の復元、再初期化、本番通知、実時計、I/O、自動リトライ、依存追加。`NO_CHANGE`／`CONFIRMED_IN_MEMORY`／日次結果は常に `committed=False`。取得・保存・送信アダプタ、Actions、Discord、Sheets、証券口座への接続はない（`no_io_clock_process_or_randomness_calls`、`nothing_unlocks_restores_restarts_or_persists`）。S3-B／Cへは進めない。

## 11. 保護参照とPR等

- 保護参照は依頼§6の19件に、資料ブランチ（docs/v2-recovery-s3-20261029＝2d504de、docs/v2-recovery-s3a-adoption-20261029＝d215193）の2件を加えた**計21件**を `git ls-remote` の完全SHAと照合した。コード＋試験のpush前：21件・不一致0。結果文書のpush後の照合は、完了報告に結果を記載する（本書はその結果を含められない）。資料ブランチへの書き込みはない。
- PR作成、Actions起動・再実行、本番反映、通知送信、依存・workflow・設定変更：**なし**。

## 12. 未実施・未確認

- 実Windows（S2のWindows専用4件、S3-A新規155件のWindows実行）：未実施。
- ユーザーのPCでの実行：未実施。ユーザー報告の181／371件は本作業の実行で置き換えていない。
- 物理電源断、autocrlf=true：未実施。
- 欠陥注入53件以外：未実行。未依頼の全期間照合や耐久性証明は追加していない。
- ライブの保存先・入力／通知接続、S3-B／C：後工程で未着手。
