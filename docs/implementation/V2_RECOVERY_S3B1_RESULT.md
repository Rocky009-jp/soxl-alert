# V2 S3-B-1 履歴コア 限定実装 結果

2026-10-30（日本時間）。担当：Sonnet 5.5・effort high。本書はB-1の限定実装の結果記録であり、**履歴・復元・移行を本番へ採用したという意味ではない**。B-1は**メモリ上の検証値と純粋関数だけ**で、保存・解錠・CLI・通知・日次処理・台帳投影・新しい確認／宣言／復元／再開の計画は実装していない（§10）。B-2以降・S3-Cは着手していない。

## 1. 結論

- 受入条件 H-01〜H-14 を実施した。**実Linux（クラウドVM）で全て合格**。**実Windows、ユーザーのPC、物理電源断、autocrlf=true は未実施**で、合格に数えていない。
- 新規 `tests/v2_history` は **217件**。Python 3.10.20／3.11.17／3.12.3／3.13.17 の全てで失敗0・error0・skip0。
- 既存スイートは無編集で全版合格：コア197、保存ドメイン170、S3-A 176、S2 113（109合格＋4 skip。skipはWindows実機専用でLinuxでは未実施。他と混ぜない）。
- 欠陥注入は **22項目を35変種**に展開して実施。**33変種を検出、2変種は等価（理由を記録）、未検出0、未実施0**（§8）。
- 範囲外の変更は必要なかった。開始点との差分は新規ファイルの追加のみ（既存ファイル差分0）。
- 採用記録どおり D-1（v2形式とB-1範囲）、D-2（復元点の下限）、D-4（Sonnet 5.5・high）に従った。

## 2. 固定した版・環境

| 項目 | 内容 |
|---|---|
| 開始指示書 | コミット `98e05e426b99154e7a5941c718b2b220f048e2a2`（docs/tasks/V2_RECOVERY_S3B1_SONNET55_START_REQUEST.md、blob `2ce50c7e5ff335f459ed1504addec2481a31dce6`） |
| 設計・依頼（第2版） | コミット `361904b1618ae9f9d3a672875c437a388826c253`。設計 docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md の blob `838761207b060ca8c844bf7ed0f15a9e990ad6b7`、依頼 docs/tasks/V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md の blob `61a645c086c5f62e31f29fcf662cbc76e3bb22dc` |
| 再レビュー | `225b10059bdc23a677f97fc3ac7597ca73c4b00c`（docs/reviews/V2_RECOVERY_S3B_V2_REREVIEW_20261029.md） |
| コード開始点（base） | `e68d702de7fa80f141e14b63cf88082c15493994` |
| 実装ブランチ | `feat/v2-history-s3b1-20261029`（新規。既存の同名ブランチは無かった） |
| **試験対象（コード＋試験）** | **`34cf8dbd2d645a22a4d00c711b2e8157c3db5b22`** |
| 保存最終 | 試験対象に本書だけを追加したコミット。本書は自身のSHAを含められないため、完全SHAは完了報告に記載。試験対象との差分は本書1ファイルのみ |
| モデル・エフォート | 作業セッションのメタデータ（get_session）で configured_model `claude-sonnet-5-5[1m]`、last_served_model `claude-sonnet-5-5`、effort_level `high`。指定（Sonnet 5.5・high）と一致 |
| OS | Ubuntu 24.04.5 LTS（クラウドVM、カーネル 6.18.44） |
| Python | 3.10.20（uv単体インタプリタ、スクラッチ領域）、3.11.17、3.12.3、3.13.17（システム）。取得だけが通信を使用 |
| クリーンクローン | 試験対象34cf8dbを別ディレクトリへ新規クローンして全スイートを実行。`core.autocrlf=false`、クローンの作業木は実行後も変更なし |
| 通信遮断 | クリーンクローンの試験は `unshare -rn`（ネットワーク名前空間を分離）で実行。遮断は `socket.create_connection` が `Network is unreachable` になることで確認。試験自身もソケットを遮断する helper を持つ。`-B -W error::ResourceWarning` を指定 |
| 実Windows | **未実施**。他者の結果で代用していない |

## 3. 追加ファイル（すべて新規。既存ファイル差分0）

`git diff --name-status e68d702 34cf8db` は A（追加）のみ22件。

- `v2_history/`（1,656行）：`__init__.py` `errors.py` `common.py` `values.py` `view.py` `restore.py` `migration.py` `migrate.py` `validate.py` `genesis.py`
- `tests/v2_history/`（3,595行）：`h_helpers.py`、`test_h02_values_codec.py`、`test_h03_h05_chain.py`、`test_h06_restore_batch.py`、`test_h07_s1_projection.py`、`test_h08_control_records.py`、`test_h09_restart.py`、`test_h10_h11_migration.py`、`test_h12_plan_confirm.py`、`test_h13_immutability_privacy.py`、`test_h14_scope_and_stop.py`、`sensitivity_check.py`（欠陥注入。unittestではなく手動実行）
- `docs/implementation/V2_RECOVERY_S3B1_RESULT.md`（本書）

使った既存の公開名は依頼書§2に列挙されたものだけ（H-14のASTスキャンで確認）。

## 4. 試験結果

### 4.1 件数（4版共通）

| 区分 | 件数 | 結果 |
|---|---|---|
| 既存コア（tests/v2_core） | 197 | 全合格 |
| 既存保存ドメイン（tests/v2_persistence） | 170 | 全合格 |
| 既存S3-A（tests/v2_recovery） | 176 | 全合格 |
| S2既存（tests/v2_persistence_local） | 113 | 109合格、4 skip（Windows実機専用＝Linuxでは未実施）。失敗0・error0 |
| **新規 B-1（tests/v2_history）** | **217** | 全合格（失敗0・error0・skip0） |

| Python | コア | 保存ドメイン | S2 | S3-A | 新規 | 通信遮断 |
|---|---|---|---|---|---|---|
| 3.10.20 | 197 OK | 170 OK | 113（4 skip） | 176 OK | 217 OK | 遮断（`unshare -rn`） |
| 3.11.17 | 197 OK | 170 OK | 113（4 skip） | 176 OK | 217 OK | 同上 |
| 3.12.3 | 197 OK | 170 OK | 113（4 skip） | 176 OK | 217 OK | 同上 |
| 3.13.17 | 197 OK | 170 OK | 113（4 skip） | 176 OK | 217 OK | 同上 |

新規件数の内訳（ファイル別）：25＋23＋24＋13＋38＋17＋30＋24＋12＋11＝217。

### 4.2 H-01〜H-14とテストの対応

| 受入条件 | 試験ファイル（件数） | 主なテスト |
|---|---|---|
| H-01 既存回帰 | 既存スイート（上表）。差分0は `git diff --name-status` で確認 | 既存656件（197＋170＋176＋113）。S2の4 skipは別掲 |
| H-02 値・符号化・形式拒否 | test_h02_values_codec（25） | cannot_be_built_directly_or_changed／encode_decode_round_trip_and_type_refusals／duplicate_keys_are_refused／non_finite_numbers_are_refused／unknown_kind_and_the_b5_kind／unsupported_schema_and_core_sha／a_v1_snapshot_is_not_converted_by_validate_history／the_existing_s1_checker_refuses_v2_unchanged／it_is_immutable_and_carries_no_ledger_content |
| H-03 監査鎖 | test_h03_h05_chain AuditChain（9） | a_changed_record_with_only_its_own_hash_updated_breaks_the_next_link／retired_records_cannot_be_deleted_changed_or_reordered／effective_parent_shape |
| H-04 有効鎖と上書き一覧 | 同 EffectiveChain／SupersededList（14） | final_chain_and_superseded_union_of_example_r／the_three_restores_have_the_designs_superseded_lists／a_physical_range_or_wrong_list_is_refused／the_union_must_cover_exactly_the_records_off_the_chain |
| H-05 復元点 | 同 EffectiveChain | a_point_that_is_not_effective_is_refused／a_point_inside_a_request_batch_is_refused_and_its_last_record_is_not／point_checks_hold_in_a_migrated_history_too／restore_to_genesis_is_accepted_in_a_new_history／restore_noop_in_a_new_history |
| H-06 復元バッチ | test_h06_restore_batch（24） | accepted_with_the_designs_shape／replayed_ack_maps_its_reference_and_recomputes_its_state／an_old_state_after_copied_into_the_replayed_record_is_refused_even_with_the_hash_redone／example_rb_replays_a_declaration_on_a_changed_parent／partial_batch_is_refused_and_whole_batches_are_accepted／consume_is_not_supported_in_b1／reapply_input_must_match／same_as_superseded_and_the_replay_list_must_state_facts |
| H-07 S1投影 | test_h07_s1_projection（13） | validate_snapshot_is_called_once_per_segment_of_every_view／the_rule_of_the_s1_checker_is_passed_on_with_its_prefix／every_apply_field_is_judged_with_an_s1_rule／ib04_holds_with_acks_and_declarations_between_applies |
| H-08 確認・宣言 | test_h08_control_records（38） | all_variants_are_accepted／wrong_references／frontier_from_*／whole_batch_is_accepted／the_ids_of_restart_and_restore_share_the_namespace／request_hash_equals_the_s3a_value |
| H-09 再開 | test_h09_restart（17） | accepted_with_the_designs_values（例U）／each_floor_value_is_enforced／exactly_the_floor_is_accepted／noop_restarts／days_are_unique_and_increasing_across_segments |
| H-10 移行（例M） | test_h10_h11_migration（30のうち ExampleM／ExampleMore／PrepareRefusals） | the_records_follow_the_designs_table／hashes_of_untouched_events_equal_the_v1_hashes／apply_content_is_not_changed_by_one_byte／migrated_sources_return_the_originals／the_unchanged_checkers_really_run |
| H-11 破損した移行履歴 | 同 DamagedMigratedHistory（10） | event_map／resolution_map／source／source_resolutions／origin／origin_after_the_migration_is_refused／positions |
| H-12 計画と確認 | test_h12_plan_confirm（24） | any_changed_basis_value_with_the_old_hash_is_a_mismatch／snapshot／resolutions／ledger／sessions（stale）／broken_*（既存エラー維持）／candidate_plan_and_result_cannot_reach_a_memory_store／…_a_local_file_store／a_v2_text_in_snapshot_json_stops_the_existing_store_without_touching_the_files |
| H-13 不変性・秘匿 | test_h13_immutability_privacy（12） | prepare_and_confirm_leave_every_input_untouched／changing_what_was_returned_never_changes_the_plan_or_the_history／displays_hold_no_row_value_or_free_text／errors_never_echo_the_stored_text |
| H-14 範囲と停止 | test_h14_scope_and_stop（11） | imports_are_standard_pure_modules_or_listed_existing_names／no_io_clock_network_process_thread_random_or_environment／nothing_for_a_later_stage_exists／the_public_surface_is_exactly_the_planned_one |

H-12のLocalFileStore確認は、依頼書の指定どおり一時rootを `durability="file_sync_only"` で初期化して行い、strictは使っていない。

## 5. 実装の形

### 5.1 公開API（`v2_history/__init__.py`、23名）

`History` `encode_history` `decode_history` `validate_history` `make_history_genesis` `migrated_sources` `prepare_migration_plan` `confirm_migration_plan` `HistoryCheck` `Boundary` `MigrationPlan` `MigrationConfirmResult` `SCHEMA_VERSION_V2` `KINDS` `GENESIS` `APPLY` `ACK` `DECLARE_MISSING` `RESTART_UNKNOWN` `RECOVERY_RESTORE` `SCHEMA_MIGRATION` `READY` `CONFIRMED_IN_MEMORY`。

### 5.2 記録7種のキー

- ヘッダ：S1と同じ6キー（`schema_version`=2 `core_sha`=S1 `CORE_SHA` `head_seq` `head_hash` `current_state` `events`）。
- **GENESIS／APPLY**：S1の `GENESIS_KEYS`／`APPLY_KEYS` と同一。ただし `seq` 0始まり連続。
- **ACK／DECLARE_MISSING**（同じキー集合）：`kind` `seq` `parent_seq` `parent_hash` `variant` `d` `record_fingerprints` `applied_ref` `missing_ref` `session_context` `frontier_before` `request_id` `request_hash` `request_basis` `command_index` `command_count` `reason_code` `requested_at` `ledger_digest` `origin` `replay_of` `state_after` `event_hash`。
- **RESTART_UNKNOWN**：`kind` `seq` `parent_seq` `parent_hash` `resume_after` `boundary_session` `floor`（`last_apply_d` `last_declared_d` `prev_boundary`）`request_id` `request_hash` `request_basis` `reason_code` `requested_at` `replay_of` `state_after` `event_hash`。
- **RECOVERY_RESTORE**：`kind` `seq` `prev_hash` `parent_seq` `parent_hash` `superseded_seqs` `replay`（各要素 `op` `from_seq` `d` `seq` `same_as_superseded`）`request_id` `request_hash` `request_basis`（`request_id` `restore_point` `ops` `check_d` `reason_code` `requested_at`）`reason_code` `requested_at` `ledger_digest` `state_after` `event_hash`。
- **SCHEMA_MIGRATION**：`kind` `seq` `parent_seq` `parent_hash` `source` `source_resolutions` `event_map` `resolution_map` `request_id` `request_hash` `request_basis` `reason_code` `requested_at` `ledger_digest` `state_after` `event_hash`。
- `RECOVERY_PREFIX_ADOPTION` は `unsupported_event`、`CONSUME` は `restore_op_unsupported` で拒否。

### 5.3 ハッシュと2本の鎖

- `event_hash` は S1 と同じ `compute_event_hash`（event_hash を除く正規化JSONのsha256）。
- 監査鎖：seqは0始まり連続、各記録は直前seqの event_hash を `parent_hash`（RESTOREだけ `prev_hash`）で指す。
- 有効な親：`parent_seq`／`parent_hash`。RESTOREだけが復元点Pを指す。`head_seq`／`head_hash` は常に物理的な最後の記録で、それは常に有効鎖上にある。
- `request_hash` は `requested_at` を除く basis のsha256（S3-Aの `request_hash_of` と同じ値になることをテストで固定）。`plan_hash` は basis の正規化JSONのsha256で、記録には入れない。

### 5.4 HistoryCheck（凍結dataclass）

`head_seq` `head_hash` `record_count` `effective_seqs` `superseded_seqs` `current_boundary`（`Boundary(kind, seq, after)`）`latest_apply_d` `processing_after` `declared_days_in_segment` `migrated` `history_digest` `state_digest`。台帳行・F&G値・自由文は持たない。

### 5.5 code／field／rule

- `history_invalid`（rule固定）、`unsupported_schema`（field＝`schema_version`／`core_sha`）、`unsupported_event`、`migration_request_conflict`、`migration_plan_mismatch`、`migration_plan_stale`。すべて `PersistenceError` で、生値を含まない。
- S1／S3-Aの検査から来る失敗は rule を `s1:` ／ `s3a:` の接頭辞付きで引き継ぐ。想定外の例外は `validate_history` が `history_invalid`／`malformed` に変換する。
- 主なrule：`audit_hash` `event_hash` `parent` `restore_noop` `restore_point_not_effective` `restore_point_in_batch` `restore_before_migration` `restore_state` `superseded_mismatch` `restore_replay_mismatch` `restore_op_kind` `restore_partial_batch` `restore_incomplete` `restore_reapply_input` `restore_ref_unmapped` `restore_op_unsupported` `replay_of` `restart_floor` `restart_noop` `restart_boundary` `batch` `request_id` `request_hash` `exclude_applied` `applied_ref` `missing_ref` `declare_frontier` `declare_applied` `origin` `migration_position` `migration_map` `migration_source` `migration_resolutions`。

### 5.6 鎖ビューとS1投影

- 検査する鎖ビューは「最終の鎖」と「各RESTORE kについて k-1 で終わる鎖」。RESTOREはビュー内で透過（有効な親は直前の要素、`state_after` は同じ）。
- ビューを GENESIS／RESTART_UNKNOWN で区切り、各区間のAPPLYを新しいS1履歴（`make_genesis_event`／`make_apply_event`、seqと親ハッシュだけ付け直し）に載せ、**変更していない `validate_snapshot`** で再計算する。本実装に市場規則・閾値・状態式は書いていない。
- 検査順は設計§4.5：形式 → 監査鎖 → 有効な親・初期状態・移行位置 → 各RESTOREとバッチ → 最終鎖と上書き一覧 → ビュー（パスA：S1投影、パスB：制御記録の規則）→ 移行の逆検査 → current_state。

## 6. 実測した例（M／R／U）

### 6.1 例R（復元3回、23件）

- 有効鎖 `(0, 1, 2, 18, 19, 20, 21, 22)`、上書き一覧 `(3〜17)`（15件）。現在区間の境界は GENESIS（2026-03-02）、最新APPLY日 2026-03-10。
- RESTORE#7（点2、上書き[3,4,5,6]）：DROP 3／REAPPLY 4→8（same=False）／REPLAY 5→9／REAPPLY 6→10（same=True）。
- RESTORE#14（点9、上書き[10,11,12,13]）：REAPPLY 10→15（True）／REAPPLY 11→16（True）／DROP 12／REAPPLY 13→17（False）。
- RESTORE#18（点2、上書き[7,8,9,14,15,16,17]）：RETIRE 7／REAPPLY 8→19（True）／DROP 9／RETIRE 14／REAPPLY 15→20／16→21／17→22（すべてTrue）。
- 復元#7の点（2）より前は不変、作成された記録は RESTORE の直後に連続（`restore_incomplete` で担保）。

### 6.2 例R-b（変わった親状態での宣言の再実行）

10件。有効鎖 `(0, 1, 6, 7, 8, 9)`、上書き `(2, 3, 4, 5)`。RESTORE#6（点1）：DROP 2／REAPPLY 3→7（False）／REPLAY 4→8（DECLARE_MISSING、参照・要求を維持し `replay_of` を付与）／REAPPLY 5→9（True）。宣言日 2026-03-05 は現在区間に残る。

### 6.3 例U（再開）

4件。GENESIS、APPLY D1、APPLY D2、RESTART_UNKNOWN（resume_after＝2026-03-05）。境界は RESTART_UNKNOWN seq 3、最新APPLY日 2026-03-04、`processing_after` は 2026-03-05（D3は意図的に未処理）。

### 6.4 例M（移行）

- 例M（8件、`processing_after` 2026-03-06）：event_map `(v1→v2)` ＝ (0→0)(1→1)(2→3)(3→5)、resolution_map ＝ (1→2)(2→4)(3→6)、SCHEMA_MIGRATION は seq 7。未接触のイベントのハッシュはv1と同一。
- 例M2（CHANGED／ROW_REMOVED／DECLARE／LATE２種、11件）：event_map (0→0)(1→1)(2→3)(3→6)(4→8)、resolution_map (1→2)(2→4)(3→5)(4→7)(5→9)、SCHEMA_MIGRATION は seq 10。
- 空のResolutionSet（4件）：event_map (0→0)(1→1)(2→2)、resolution_map 空、SCHEMA_MIGRATION は seq 3。
- 3例とも `migrated_sources` が元のS1 Snapshot と S3-A ResolutionSet を復元し、digest が一致する。

## 7. 復元・再開・移行の規則（実装した内容）

- **上書き一覧** ＝ 鎖(k-1) の復元点より後（物理的な範囲ではない）。
- **操作**：APPLY→REAPPLYのみ、ACK／DECLARE／RESTART→REPLAY／DROP（同じ要求バッチは同じ操作。違えば `restore_partial_batch`）、RESTORE→RETIRE。
- **REAPPLY**は decision／row／prev_row／prev_session_date を保ち、session_context は共通日で比較（最後の1件は日付と open_at のみ）。`same_as_superseded` は検査される事実。
- **REPLAY**は参照を写像（P以前は不変、REAPPLY／REPLAY先は作成seq、DROP／RETIRE先は `restore_ref_unmapped`）し、要求項目を保って `replay_of` を付ける。
- 作成された記録の `state_after`・frontier・文脈・下限は**新しい鎖で再計算**（N-01）。旧 `state_after` は写さない。
- **復元点の下限（N-02／D-2）**：移行履歴は SCHEMA_MIGRATION 自身かそれ以降。それより前は `restore_before_migration`。新規v2履歴は GENESIS も可。
- **RESTART_UNKNOWN**：floor ＝ {last_apply_d, last_declared_d, prev_boundary}、`resume_after` ≥ floorの最大値かつ ≤ `check_d`、`restart_noop`、状態は初期化、境界セッション検査。
- **移行**：各S1イベントの直後にそのときのS3-A記録を置き（`origin` にS3-Aの値を保持）、最後にSCHEMA_MIGRATION。`reconstruct` がv1 Snapshot と ResolutionSet を再構築して `validate_snapshot`／`validate_resolutions` を通す。
- **計画／確認の順序**：計画の形・ハッシュ（`migration_plan_mismatch`）→ 入力の正しさ（既存エラーのまま）→ 正しい入力の digest 差（`migration_plan_stale`）→ 再構築と比較（`migration_plan_mismatch`）。`committed` は常に False。`History`・計画・結果は既存ストアが拒否する型（`snapshot_invalid`／`plan_type`）。

## 8. 欠陥注入（`tests/v2_history/sensitivity_check.py`）

作業木を一時ディレクトリへ複製し、複製の `v2_history` に**1つの欠陥**を適用して `tests/v2_history` を実行し、失敗することを要求する。実作業木は変更しない。パッチが一度だけ当たらない場合は「未実施」とし、検出に数えない。

| 項目 | 内容 | 変種 | 結果 |
|---|---|---|---|
| 1 | 上書き一覧を物理範囲で計算 | D01 | 検出 |
| 2 | 退役記録の監査鎖・event_hashを見ない | D02 | 検出 |
| 3 | 退役済みの復元点を受理 | D03 | 検出 |
| 4 | 途中で切れた復元バッチを受理 | D04 | 検出 |
| 5 | REAPPLYの decision／row を比較しない | D05 | 検出 |
| 6 | same_as_superseded を検査しない | D06 | 検出 |
| 7 | REPLAYの参照写像を検査しない | D07 | 検出 |
| 8 | バッチ部分DROPを受理 | D08 | 検出 |
| 9 | S1投影が物理親ハッシュを使う | D09 | 検出 |
| 10 | 再開の下限が宣言日を無視（比較／期待値の2変種） | D10a／D10b | 検出 |
| 11 | 再開の下限が前の境界を無視（2変種） | D11a／D11b | 検出 |
| 12 | 宣言のfrontierが区間境界を無視 | D12 | 検出 |
| 13 | 参照が祖先であることを要求しない（ACK→APPLY／LATE→宣言） | D13a／D13b | **等価** |
| 14 | 移行の逆検査がv1 digestを見ない | D14 | 検出 |
| 15 | S3-Aのハッシュを再計算しない | D15 | 検出 |
| 16 | 移行後の記録のoriginを受理 | D16 | 検出 |
| 17 | 計画が resolve_observations の再確認を省く | D17 | 検出 |
| 18 | 確認が plan_hash／入力digestを無視（6変種：計画ハッシュ2・snapshot・resolutions・ledger・sessions） | D18a〜D18f | 検出（6／6） |
| 19 | 入れ子の参照を共有（plan.to_dict／History.events） | D19a／D19b | 検出 |
| 20 | state_after をコピー（REPLAY必須化／再計算省略の2変種） | D20a／D20b | 検出 |
| 21 | 復元点の下限が誤り（厳しすぎ・緩すぎ・無し・GENESIS拒否の4変種） | D21a〜D21d | 検出（4／4） |
| 22 | 確認で不正入力を stale に変換 | D22 | 検出 |

合計：35変種中 **33検出・2等価・0未検出・0未実施**。

- **等価（D13a／D13b）**：前方参照は、参照先の event_hash が参照元に依存するため（ハッシュの循環）作れず、event_hash の比較だけで既に拒否される。歩行順の探索は二重の防御で、どのテストでも区別できない。検出に数えていない。
- 初回の全実行ではD21b（復元点＝SCHEMA_MIGRATIONの直前の1件が受理される欠陥）が未検出だった。`restore_before_migration` の試験に点0と点6（移行直前）を追加して検出されるようにした（試験件数は同じ217件、subTestの追加）。最終の全実行結果はこの表のとおり（§12）。

## 9. 解釈した点と設計との差

- 設計と矛盾する点は見つからず、規則を変えていない。以下は読み方を決めた箇所。
  1. RESTOREの `check_d` は「鎖(k-1) の最新APPLY日以上、かつ現在区間の境界より後」とした（復元点Pまでの鎖ではなく k-1 の鎖で判定）。
  2. 規則の順序：`restore_noop` → `restore_point_not_effective` → `restore_before_migration` → `restore_point_in_batch` → `restore_state` → `superseded_mismatch` → 基本形 → 操作の整合 → 作成記録の整合。
  3. `restart_noop` ＝ 親の状態が初期状態で、かつ `resume_after` が前の境界と同じ。
  4. 取り消された（上書きされた）RESTOREの request_id を後続の復元が再利用できるのは、別のビューに属するため（試験で固定）。
  5. 試験用ビルダー `HB` は、APPLYの内容を本物のS1 `prepare_day` で現在区間に対して計算する。ランタイムからは参照されない（H-14で確認）。
- 依頼書にない公開名・補助モジュールは追加していない。

## 10. B-1の範囲の表明

- **B-1は純粋にメモリ上の検証だけ**で、ファイル・パス・ストア・時計・ネットワーク・プロセス・乱数・環境変数に触れない（H-14）。
- `History`・計画・結果は既存の `MemoryStore`／`LocalFileStore` が受け付ける型ではなく、v2テキストを `snapshot.json` に置くと既存のストアは `unsupported_schema` で止まり、バイト列とディレクトリ一覧は変わらない（H-12）。
- 日次処理、台帳投影、新しい ACK／DECLARE／再開／復元の計画、CONSUME、prefix採用、HistoryReplacement、HistoryAppendBatch、v2ストア、解錠、CLI、通知、outbox、本番接続はいずれも実装していない。
- 通知しても保有・原価・売却済み状態は更新しない。自動発注・口座接続・資金移動なし。

## 11. 保護参照とPR等

- 保護参照は開始指示書の29参照と採用ブランチ `docs/v2-recovery-s3b1-adoption-20261029`（98e05e4）の計30件。**作業開始時：30／30 一致**（`git ls-remote` の完全SHAを一覧と比較）。**push後の再確認は完了報告に記載する**（本書に結果を書くとpush後の状態を先取りするため）。
- 更新したのは自分の実装ブランチ `feat/v2-history-s3b1-20261029` だけ。mainのマージ・PR・Actions・本番反映・外部通知・口座接続はなし。

## 12. 未実施・未確認

- **実Windows**での実行：未実施（S2の4 skipも同じ）。
- ユーザーのPCでの実行：未実施。物理電源断：未実施。`autocrlf=true`：未実施。
- 欠陥注入の最終全実行は、試験対象34cf8dbのクリーンクローンで実施した。結果は§8の表と同じ（実行ログの要約は完了報告）。
- 設計の採用判断（B-2以降、S3-C）は本実装の範囲外。レビューや本書の合格は本番変更の承認ではない。

## 13. 追記：受領レビュー R-01／R-02 の限定修正（2026-10-30）

§1〜§12は修正前の実績の記録であり、書き換えていない。以下は修正後の追記。

### 13.1 固定した版

| 項目 | 内容 |
|---|---|
| 依頼 | docs/tasks/V2_RECOVERY_S3B1_REVIEW_FIX_REQUEST.md、レビュー docs/reviews/V2_RECOVERY_S3B1_IMPLEMENTATION_REVIEW_20261030.md、再現コード docs/reviews/V2_RECOVERY_S3B1_REVIEW_REPRODUCE_20261030.py。すべてコミット `6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3`（ブランチ docs/v2-history-s3b1-receipt-20261030）の版 |
| 修正開始点 | `0fbba6c46f62a5765cf1ffb8e3646325c1787373`（コードは34cf8dbと同一）。元の実装ブランチは更新していない |
| 修正ブランチ | `fix/v2-history-s3b1-review-20261030`（新規。リモートに同名なし） |
| **試験対象（修正コード＋回帰）** | **`2b5fa2d079e2fe86b98b0e6d5be5431c5b4988ce`** |
| 保存最終 | 試験対象に本節の追記だけを加えたコミット。完全SHAは完了報告に記載。差分は本書1ファイルのみ |
| モデル・エフォート | get_sessionで configured_model `claude-sonnet-5-5[1m]`、last_served_model `claude-sonnet-5-5`、effort_level `high`（指定と一致） |
| 環境 | Ubuntu 24.04.5 LTS。Python 3.10.20／3.11.17／3.12.3／3.13.17。別クリーンクローン（`core.autocrlf=false`）で `unshare -rn` により通信を遮断、`-B -W error::ResourceWarning` |
| Windows | **未実施**。レビュー担当のWindows217件を自分の結果にしていない |

### 13.2 修正点（開始点との差分：変更4ファイル＋追加2ファイル）

| 指摘 | 場所 | 修正 | 拒否時の結果 |
|---|---|---|---|
| R-01 | `v2_history/restore.py` | `superseded_seqs` の全要素を `type(x) is int` で要求した上で期待する有効鎖のsuffixと比較 | `history_invalid`／`superseded_mismatch` |
| R-01 | `v2_history/migration.py` | `source.schema_version`・`source.head_seq` を厳密な整数として要求 | `migration_source` |
| R-01（点検で見つけた同種） | 同上 | `origin.source_head_seq` も厳密な整数を要求（防御。§13.5） | `origin` |
| R-02 | `v2_history/values.py` | `History.head_seq`／`head_hash`／`schema_version` を常にdeepcopyして返す | － |
| R-02 | `v2_history/migrate.py` | `MigrationPlan.plan_hash` を常にdeepcopyして返す | － |

- **API互換**：公開名・引数・戻り値の型は不変（正常なint／strはこれまでと同じ値）。`same`・hash・schema version・`from_dict` の受理範囲は変えていない。意味検査を `from_dict` に移していない。
- 同モジュール内の整数欄を限定点検した。`is_int` で守られているもの（`parent_seq`、`head_seq`、`command_index`／`command_count`、参照の `seq`、`resolution_seq`、`from_seq`／`seq`）と、`same`（正規化JSON）で比べているもの（`event_map`、`resolution_map`、`restore_point` 等）は型を区別する。値の等しさだけの比較は上の3か所だけだった。`migrate.py` の計画 basis の `source_head_seq` の比較は偽造計画の分岐が `migration_plan_mismatch`（正しい）になるため変更していない。
- 既存S1 Snapshotの同形アクセサ、他パッケージ、既存の217件の期待値は変更していない（既存試験ファイルの差分0）。

### 13.3 受領再現コードでの確認（`<python> -B …REPRODUCE….py --repo <チェックアウト>`）

| 版 | 結果 |
|---|---|
| 修正前（0fbba6c） | 通常モード：10観測すべて `fixed:false`（R-01の6、R-02の4）。対照2件は合格 |
| 修正後（2b5fa2d） | `--expect-fixed` で **10観測すべて解消、対照2件合格、終了0**（4つのPythonすべて、通信遮断下） |

### 13.4 追加回帰（`tests/v2_history/test_h15_review_fix.py`、13件。元の217件とは別掲）

| 試験 | 内容 | 修正前 |
|---|---|---|
| R01SupersededEntries（3） | `[True]`／`[1.0]`、例Rの長い一覧のfloat要素4種、正しい一覧と他の誤りの対照 | 失敗 |
| R01MigrationSource（4） | `schema_version` に True／1.0／"1"／2／0、`head_seq` に True／float／文字列／±1、`head_seq=0` の境界（False／0.0を拒否・0は受理）、`origin.source_head_seq`（True／1.0 → `origin`） | origin以外は失敗 |
| R02PublicAccessors（4） | 未検証の `head_seq`／`head_hash`／`schema_version`／`plan_hash` にdict・list（入れ子）を置き、取得値の変更が `to_dict`・`encode_history`・`digest`・等値・`hash` を変えないこと。正常な履歴・計画は従来どおり。`events`／`current_state`／`to_dict` の独立性も維持 | 失敗 |
| P02ExampleRSameFlag（2） | 例Rの #10 の `same_as_superseded` は、合成F&GのD2＝28で True、D2＝30で False（#8は両方False）。どちらの入力でも検査を通り、逆の値を書くと `restore_replay_mismatch` | 合格（修正と無関係の対照） |

- 修正前は、この13件のうち11件（R-01／R-02部）の実行で**18の失敗サブケース**。修正後は13件すべて合格。
- 新規は計 **230件（元217＋回帰13）**。4版すべて失敗0・error0・skip0。既存は コア197／保存ドメイン170／S3-A 176／S2 113（109合格＋Windows専用4 skip）が無編集で全版合格。
- H-01〜H-14の期待値は弱めていない。

### 13.5 修正を個別に戻す感度確認（`tests/v2_history/review_fix_sensitivity.py`、Python 3.13）

| 戻した修正 | 結果 |
|---|---|
| F01 `superseded_seqs` の整数要素検査 | 検出 |
| F02 `source.schema_version` の整数検査 | 検出 |
| F03 `source.head_seq` の整数検査 | 検出 |
| F04 `origin.source_head_seq` の整数検査 | **等価**（S3-Aの `resolution_hash` を再計算するため、値に True／1.0 が入っても既存の検査が同じrule `origin` で拒否する。明示検査は防御） |
| F05〜F07 `head_seq`／`head_hash`／`schema_version` のdeepcopy | 検出（各） |
| F08 `plan_hash` のdeepcopy | 検出 |

8変種中 **7検出・1等価・未検出0・未実施0**。元の欠陥注入35変種の再実行は必須とされておらず、実施していない（§8は修正前の実績のまま）。

### 13.6 任意提案の取り込み

- **P-01（H-04／H-05の表記）**：依頼書のIDでは、H-04は有効鎖・復元点、H-05は退避一覧（上書き一覧）。§4.2の表は H-04＝有効鎖と上書き、H-05＝復元点としていたため、**訂正する**。H-04 → `EffectiveChain`（復元点の有効性・バッチ内・移行下限・no-op・GENESISを含む11件）。H-05 → `SupersededList`（3件）、`test_the_three_restores_have_the_designs_superseded_lists`、`test_final_chain_and_superseded_union_of_example_r`。試験名・件数は変えていない。
- **P-02（例Rのsameフラグ）**：設計§8.9の #10＝False に対し、実測の例R（D2＝28）では #10＝True（§6.1）。ランタイムは入力から計算した事実を検査しており、設計表に合わせて偽装していない。D2を30以上にすると #10もFalseになる対照をP02ExampleRSameFlagに追加した。構造の期待値（再適用の順序・写像）は入力に依存しない。

### 13.7 保護参照・範囲

- 保護参照は開始指示書の29参照＋採用ブランチ98e05e4＋元実装ブランチ0fbba6c＋レビュー資料ブランチ（6e7f756、読取専用）。**開始時：32／32 一致**。push後の再確認は完了報告に記載する。更新したのは新規の修正ブランチだけ。
- B-2以降・S3-C・日次・台帳投影・実保存・解錠・復元・PR・Actions・本番・通知・口座接続はなし。

### 13.8 未実施・保留

- 実Windows、ユーザーPC（3.10.6）、物理電源断、`autocrlf=true`：未実施。
- 元の欠陥注入35変種の再実行：未実施（必須でない）。
- S1 Snapshot側の同形アクセサ：変更していない（範囲外）。
