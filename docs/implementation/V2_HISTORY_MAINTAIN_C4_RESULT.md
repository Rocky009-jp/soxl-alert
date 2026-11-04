# V2 C-4 保守操作（明示解錠・v1→v2移行・prefix採用の実行）限定実装の結果

作成日：2026-11-04（日本時間）。担当：Claude Sonnet 5.5（セッション設定 `claude-sonnet-5-5`、effort `high`。最後に実行したモデルも `claude-sonnet-5-5` と、`get_session` で確かめた）。
対象：`Rocky009-jp/soxl-alert`、新ブランチ `feat/v2-history-maintain-c4-20261104`。PR・マージ・Actions・本番・S4はしていない。

## 0. 要約

- C-4の限定実装は**完了**した。新パッケージ `v2_history_maintain`（4ファイル1,190行）と、新しい試験 `tests/v2_history_maintain`（9本の試験ファイルと2本の補助、180件）を足し、既存の1ファイル（`test_c3_09_scope.py`）の**1行だけ**を固定した。
- 試験対象 `1eb4261ff4ea1c312bce3725fe50d39b20988b05` で、完全な履歴の別クリーンクローン（`core.autocrlf=false`）の Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版とも、**既存14スイート2,069件＋新規180件が全件合格**（失敗0・エラー0・新規のskip 0。既存のskip 4件はS2のもの）。
- 欠陥注入は依頼書の21項目に、同じ項目の別の形1件と追加9件を加えた**32件**。**31件検出、1件は等価と判断**（根拠は§9）。未検出で残るものはない。準備失敗0。
- C4-16の総当たりは**2,154通り**で、違反0。C4-22（次の段階の模擬）は期待どおり。
- **未実施**：実Windows、物理電源断、ユーザーPC、ネットワークドライブ、Windowsの合計（新規180＋1,593）。他者の結果で代用していない（§13）。
- Q-02（再レビューの任意提案）：C4-20の静的監査は、`_make`・`_of`・`_wrap`・`copy.deepcopy` を **`RootReport` と `UnlockPlan` の2つの値の中でだけ**許す。受け手は `cls`（`cls._wrap`）に限り、それ以外のクラス・関数・名前、およびC-2の値（`HistoryPublication`・`Reconciliation`）に対する呼出しは禁じている（`test_c4_09_scope.py` の `Constructors`）。
- Q-01（同）：**requested_atの読み方**は§11に書いた。

## 1. 固定した資料と起点

| 項目 | 値 |
|---|---|
| 資料コミット（docs/v2-history-maintain-c4-20261104） | `d11b87597ef4035f5fee0ffc8c9fa859f82fe00f` |
| 設計 `docs/specs/V2_HISTORY_MAINTAIN_C4_DESIGN_DRAFT.md`（blob） | `ba3871aee9663cbd4128a3fc057b0df00ca84f29` |
| 依頼書 `docs/tasks/V2_HISTORY_MAINTAIN_C4_LIMITED_IMPLEMENTATION_REQUEST.md`（blob） | `34580385b115bc4f12ecf0d541c8616a181a3ffd` |
| 試行差分 `docs/specs/V2_HISTORY_MAINTAIN_C4_TRIAL_20261104.diff`（blob） | `3ad23043697443ea632c49fe8d05f5e3cc7684ec`（sha256 `fa9a60e2e24a6af5ecaf742ca2308918231c78c8e0ab49abb988875d31a58e69`） |
| コードの開始点 | `6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a`（C-3の保存最終） |
| **試験対象（コード・試験の最終）** | `1eb4261ff4ea1c312bce3725fe50d39b20988b05` |
| 最終（この結果文書の追加） | この文書だけを足した次のコミット。SHAはpushの報告に書く |

保護参照は、依頼書§7の82参照に資料ブランチ（`d11b875`）を加えた**83参照**を、開始時とpush前（`refs_final_before_push.txt`）に完全なSHAで照合し、**83件とも一致**した。push後の照合は報告に書く。

試行差分は**写していない**（第2版のN-01〜N-03より前のため）。第2版の受入条件に従って書き、試行との比較は§8でこの文書を書く段階で初めて行った。

## 2. 変更したもの

新規（試験対象 1eb4261、起点 6d69bd7 との差分は 16ファイル、+4,388／−1）：

| 場所 | 行数 | 内容 |
|---|---|---|
| `v2_history_maintain/__init__.py` | 14 | 公開名 |
| `v2_history_maintain/ops.py` | 17 | `MaintenanceOps(FileOps)`：追加は `mkdir`（`os.mkdir(path, 0o700)`）と `rename` だけ |
| `v2_history_maintain/values.py` | 262 | 名前・固定語、`RootReport`、`UnlockPlan`、`plan_unlock`、`check_plan`、MANIFEST、`MaintenanceResult` |
| `v2_history_maintain/store.py` | 897 | `HistoryMaintenance`（inspect／read_original／read_set_aside／unlock／migrate／adopt） |
| `tests/v2_history_maintain/` | 試験9本（2,724行）＋補助 `c4_helpers.py`（370行）・`c4_worker.py`（103行） | 下の§6 |

変更した既存ファイルは `tests/v2_history_local/test_c3_09_scope.py` の**1行だけ**：

```diff
--- a/tests/v2_history_local/test_c3_09_scope.py
+++ b/tests/v2_history_local/test_c3_09_scope.py
@@ -15,7 +15,7 @@ sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
 import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)
 
 START = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a"   # accepted (review 2049e10); frozen when C-4 began
 REV = END or "HEAD"
 
 PACKAGE = "v2_history_local"
```

新しい範囲試験 `test_c4_09_scope.py` は `START = 6d69bd7`、`END = None`（次の段階が受領した最終に替える）。`main.py`、`research`、`docs`（この結果文書を除く）、`.github`、依存、他パッケージ、C-3とS2のストアは変えていない。C-3・S2のストアはimportもしていない。C-2の公開値は `type(p) is HistoryPublication` だけで受け、作らず、写さない。v2_history_publishからimportした名前は12個だけ。

## 3. 公開API

```python
HistoryMaintenance(root, writable=False, durability=STRICT)
  .inspect()                              # ロックなし。RootReportを返す
  .read_original(name)                    # name は "history.json" か "snapshot.json"。ロックの下
  .read_set_aside(key, name)              # quarantine/<key>/ のバイトを、MANIFESTと一致したときだけ返す
  .unlock(plan, confirmed_plan_hash)      # 確認済みの計画の対象だけを quarantine/<plan_hash>/ へrename
  .migrate(publication, writers_stopped)  # MIGRATIONの公開値。snapshot.json を退避
  .adopt(publication)                     # ADOPTIONの公開値。元の history.json を退避（写して読み戻す）
plan_unlock(report, request_id, writers_stopped)   # 純粋。宣言は `is True` だけ
```

結果は `MaintenanceResult(status, key, resumed, history, persistence_level)`。`status` は `UNLOCKED／MIGRATED／ADOPTED`。エラーはS2の `LocalStoreError` で、保守のための固定語 `maintenance_plan_invalid／unconfirmed／stale`、`maintenance_declaration_missing`、`maintenance_nothing_to_unlock`、`maintenance_target_unsupported`、`maintenance_quarantine_invalid`、`maintenance_copy_mismatch`、`maintenance_set_aside_mismatch`、`maintenance_state_unexpected`（rule `empty／v1_and_v2／v2_present`）、`maintenance_incomplete`（primaryに元の語）を足した。パス・OSの文言・入力値はエラーに入れない。

## 4. C-3の手順との対応

| C-3（`v2_history_local/store.py`） | C-4（`v2_history_maintain/store.py`） | 違い |
|---|---|---|
| `_acquire`（`create_exclusive`→マーカー書込み→close） | `_acquire` | 同じ。マーカーは `v2_history_maintain.lock\n`＋16バイトhex。ロック名は `write.lock`（C-3・S2と同じ名前なので相互排他になる） |
| `_owns`／`_release` | `_owns`／`_release` | 同じ（lstat・inode・マーカーを確かめてからunlink） |
| `_locked`（`ctx.published`によるcommit_uncertainの規則） | `_locked` | 同じ規則に、`ctx.changed`（変更を始めた）による `maintenance_incomplete` を足した |
| `_scan`（一時ファイル・v1の拒否） | `_migrate_body`／`_adopt_body` の先頭 | 残り物は `store_artifact_present`、v1は `store_layout_unsupported`（採用）。移行は v1 のみを正常な入口にする |
| `_load`（ロックの下で読む、lstat→read_file→inode再確認） | `_read_regular`／`_read` | 同じ |
| `_publish`（耐久性の確認→tmp→fsync→所有確認→replace→dir fsync） | `_publish` | 同じ順序。`_check_durability` は**変更の前**（STRICTのWindows・ディレクトリfsync不可の拒否） |
| `_discard_own`／`_fill`／`_write_all` | 同名 | 同じ（自分で作ったtmpだけ、inodeを確かめて消す） |
| （なし） | 退避先 `_q_make`／`_q_manifest`／`_put`／`_move` | 新規。MANIFESTは**ロックの下で読んだバイトが公開値／計画を通った後にだけ**書く（規則4・N-03） |

C-4の操作の途中で壊れたときは、cleanupの語に頼らず `inspect` で残り物を一覧し直す（C-3レビューP-02）。例外は、**例外処理（except）の外で**固定のエラーを投げる（`__context__` にOS例外を残さない。C4-19）。

## 5. 手順の順序（正常時の呼出し列、C4-16）

`test_c4_07_procedure_faults.py` の `ORDER_MIGRATE／ORDER_ADOPT／ORDER_UNLOCK_*` に、記録の子クラス（`C4Ops`）で観測した呼出し列を固定した。

- migrate：ロック→snapshot.jsonを読む→`check_publication`→（STRICTでdir probe）→quarantine／鍵ディレクトリの作成→MANIFEST（tmp→fsync→replace→dir fsync）→history.jsonの公開（C-3と同じ）→snapshot.jsonをrename→dir fsync→ロック解放。
- adopt：ロック→history.jsonを読む→`check_publication`→退避先→MANIFEST→元のバイトの写し（tmp→fsync→replace）→**読み戻して識別値を確認**→公開→ロック解放。
- unlock（計画にロックがある）：C-4のロックは取らず、残っていたロックを排他として使い、**ロックを最後にrename**する。計画にロックがなければC-4のロックを取る。

## 6. 受入条件と試験の対応

全試験は `tests/v2_history_maintain/`。

| 受入 | 試験ファイル（クラス） | 件数 |
|---|---|---|
| C4-01 回帰 | 既存14スイート（§7の表）と `test_c3_09_scope.py`（27件、固定行は1行） | 2,069 |
| C4-02 構成と値 | `test_c4_01_config_values.py`（Config・Values・Names） | 12 |
| C4-03 inspect／C4-04 計画 | `test_c4_02_inspect_plan.py`（Inspect・Plan） | 20 |
| C4-05 解錠の実行／C4-06 拒否／C4-07 中断と再開／C4-08 P-02の残り物 | `test_c4_03_unlock.py`（Unlock・Refusals・Interrupted・LeftoversWithoutWords） | 29 |
| C4-09 移行／C4-10 移行の再開 | `test_c4_04_migrate.py`（Migrate・Resume） | 22 |
| C4-11 採用／C4-12 採用の再開／C4-13 退避の証拠 | `test_c4_05_adopt.py`（Adopt・Resume・Evidence） | 22 |
| C4-14 公開値の受け取り／C4-15 ロック | `test_c4_06_publication_lock.py`（Receiving・Lock） | 14 |
| C4-16 手順と故障／C4-17 保存水準／C4-19 漏れ | `test_c4_07_procedure_faults.py`（Order・Sweep・Levels・Leaks） | 22 |
| C4-18 プロセス | `test_c4_08_processes.py`（Probe・Contention・ForcedStop） | 8 |
| C4-20 静的監査／C4-21 範囲 | `test_c4_09_scope.py`（PathJudgement・FilesChanged・Chain・RuntimeAudit・Constructors・TestFiles） | 31 |
| C4-22 次段階の模擬 | `next_stage_sim.sh`（§10） | （スクリプト） |
| 新規合計 | | **180**（12＋20＋29＋22＋22＋14＋22＋8＋31） |

主な試験名：
- C4-05：`test_a_left_lock_of_each_kind_alone`、`test_lock_and_temporary_files_the_lock_goes_last_and_no_new_lock_is_taken`、`test_after_an_unlock_c3_reads_and_publishes`
- C4-06：`test_an_unconfirmed_hash`、`test_a_new_temporary_file_after_the_plan`、`test_the_inode_changes_between_the_listing_and_the_rename`（lstatとrenameの間にinodeが替わる）、`test_the_inode_changes_while_the_file_is_being_read`
- C4-07：`test_a_fault_at_each_rename_then_the_same_plan_moves_the_rest`、`test_a_manifest_that_changed_by_one_byte_is_refused`、`test_a_quarantine_on_another_device_is_refused`
- C4-10：`test_resume_from_both_with_a_publication_made_again_from_the_original_bytes`、`test_another_requested_at_gives_another_hash_and_stops_without_changing_the_root`（N-01）
- C4-12：`test_a_failed_release_then_unlock_then_a_publication_made_again_from_the_set_aside_bytes`、`test_a_history_file_that_is_not_the_candidate_is_not_a_finished_adoption`
- C4-13：`test_the_manifest_is_written_only_after_the_bytes_read_under_the_lock_were_checked_migration／_adoption`（N-03）
- C4-14：`test_hand_made_values_without_mode_or_source_or_with_a_bad_hash_are_a_shape_error`
- C4-19：`test_a_message_with_the_path_in_it_never_reaches_an_error`、`test_the_raise_is_outside_the_exception_handling`

試験は時計を順序に使わず、一時ディレクトリの中だけに書き、`open()` は `tree()` の走査にだけ使う（`TestFiles` が検査）。

## 7. 全件試験の結果（試験対象 1eb4261、別クリーンクローン、`core.autocrlf=false`、完全な履歴）

| スイート | 件数 | | スイート | 件数 |
|---|---|---|---|---|
| v2_core | 197 | | v2_history_diagnose（B-5a） | 131 |
| v2_persistence | 170 | | v2_history_adopt（B-5b） | 170 |
| v2_persistence_local（S2） | 113（skip 4） | | v2_scope_chain | 34 |
| v2_recovery（S3-A） | 176 | | v2_history_consume（C-1） | 112 |
| v2_history（B-1） | 230 | | v2_history_publish（C-2） | 150 |
| v2_history_ops（B-2） | 173 | | v2_history_local（C-3） | 139 |
| v2_history_restart（B-3） | 109 | | **既存の合計** | **2,069** |
| v2_history_restore（B-4） | 165 | | **v2_history_maintain（C-4、新規）** | **180** |

| Python | 結果 | 新規の所要 |
|---|---|---|
| 3.10.20（`/root/.local/bin/python3.10`） | 15スイートとも `OK`、rc=0 | 225.7秒 |
| 3.11.18 | 同上 | 181.7秒 |
| 3.12.3 | 同上 | 189.1秒 |
| 3.13.18 | 同上 | 190.2秒 |

どの版も失敗0・エラー0・終了コード0。skipは既存のS2の4件（`v2_persistence_local`）だけで、新規のskipは0。`-W error::ResourceWarning` で実行した。ログは `final_runall_py3.{10,11,12,13}.log`。合計 2,069＋180＝**2,249件**。

`git archive` のツリー（`.git` なし）での、Git読取りの範囲試験のskipは別に記録した（`archive_tree_skips.log`、3.13）：v2_scope_chain 34件中33、v2_history_consume 107件中22、v2_history_publish 150件中28、v2_history_local 139件中25、v2_history_maintain 180件中29。これは合格数に数えない。

**Windows**：この環境にはWindowsがないため、「新規180＋1,593」の合計は**未実施**。

## 8. 試行差分との違いと理由（設計§7）

試行は書き方の参考にせず、第2版の受入条件で書いた。比べると違うのは次の点。公開名・エラーの語・MANIFESTの形・退避先の名前（`quarantine/<key>/MANIFEST`）・順序（MANIFEST→公開→rename）は、設計どおり同じ。

1. **計画の対象のキー**：試行は `dev／ino`、本実装は `st_dev／st_ino`（`os.lstat` の名前に合わせた）。MANIFESTの対象のキーは試行と同じ4つ（name・kind・raw_sha256・raw_size）。
2. **`check_plan` の形**：試行は `check_plan(plan, confirmed_plan_hash)` で確認とhash比較を一つにしていた。本実装は `check_plan(plan)` が形・名前・種類・hashだけを見て、確認のhashの比較は `unlock` が行う（N-01の「確認していない計画は何も動かさない」を試験しやすくするため）。名前は「ロック（`write.lock`）」か「一時ファイルの形」だけを許し、`history.json`・`snapshot.json`・ディレクトリを計画に入れられない。
3. **`inspect` の寛容さ**：試行はhistory.json／snapshot.jsonが通常のファイルでないと例外にしていたが、本実装は `regular=False` として**報告**し、例外にしない（壊れた状態の人に見せるため）。履歴が読めるかは `readable` で示す。
4. **`ctx.changed` の置き方**：最初の変更の呼出しの**直前**に立てる（結果が不確かな呼出しも「変更を始めた」と数える）。保守的な側に倒した。
5. **ロックがある計画と、後から増えたロック**：計画にロックが無いのに実行時にロックがある場合は `maintenance_plan_stale`（`store_busy` ではない）。計画にロックがあるときだけ、そのロックを排他に使う。
6. **公開値の形の確認**：`_kind` で `publication_hash` が64桁のhexであることまで、**ロックの前に**見る（ハッシュはディレクトリ名になるため）。手作りの値は `store_publication_invalid／shape`。
7. **中断後の再開**：移行は「両方」（history.jsonが候補で、snapshot.jsonが残る）／「v2のみ」（完了、または完了の後に日次で伸びた）を `reconcile_publication` の結果（`PUBLISHED`／`PUBLISHED_THEN_EXTENDED`）で区別し、退避先のsnapshot.jsonの識別値まで確かめる。採用も同様で、写しの識別値が合わなければ完了と認めず `publication_stale／raw` を返す。
8. **公開名**：試行より `STRICT`・`FILE_SYNC_ONLY_MODE`・`LocalStoreError` などS2の語を再公開した（C4-20の「S2の語だけ」で検査）。

## 9. 欠陥注入（`mutate.py`、使い捨てのgit worktreeに1件ずつ、試験対象のコミットで実行）

結果は `mutation_out.json`／`.txt`（試験対象 1eb4261）。検出＝C-4の試験（`v2_history_maintain` 全件）のどれかが失敗／エラーになる。項目21は C-3の範囲試験・C-4の範囲試験・範囲の鎖で見る。

| 依頼の項目 | 注入 | 結果 | 検出した試験（例） |
|---|---|---|---|
| 1 | 解錠：実行時の一覧と計画の部分集合の確認を外す | 検出（2件） | `test_a_new_temporary_file_after_the_plan` |
| 2 | 解錠：renameの直前のinode比較を外す | 検出（1件） | `test_the_inode_changes_between_the_listing_and_the_rename` |
| 3 | ロックを最初に移す | 検出（10件） | `test_a_fault_at_each_rename_then_the_same_plan_moves_the_rest` |
| 4 | ロックの無い計画でC-4のロックを取らない | 検出（3件） | `test_the_c4_lock_left_by_an_unlock_is_in_the_next_plan_and_the_old_key_stays` |
| 5 | 確認したhashとの比較を外す | 検出（1件） | `test_an_unconfirmed_hash` |
| 6 | 宣言の `is True` を真値の判定に | 検出（1件） | `test_the_declaration_must_be_exactly_true` |
| 7 | MANIFESTの完全一致の確認を外す | 検出（2件） | `test_a_manifest_that_changed_by_one_byte_is_refused` |
| 8 | 許す名前の確認を外す | 検出（2件） | `test_a_key_directory_with_a_name_that_does_not_belong_is_refused` |
| 9 | st_devの比較を外す | 検出（1件） | `test_a_quarantine_on_another_device_is_refused`（子クラスでst_devを替える） |
| 10 | 移行：MANIFESTをバイトの照合より前に書く | 検出（4件） | `test_the_manifest_is_written_only_after_…_migration` ほか |
| 10b | 採用：同上 | 検出（11件） | `test_an_adoption` ほか |
| 11 | 移行：snapshot.jsonのrenameを公開より前に | 検出（11件） | `test_a_failed_rename_leaves_both_files_and_c3_refuses_the_root` |
| 12 | 移行：「両方」の再開で、history.jsonの照合を外す | 検出（2件） | `test_a_history_file_that_is_not_the_candidate_is_not_a_completed_migration` |
| 13 | 移行：`writers_stopped` の確認を外す | 検出（1件） | `test_no_declaration` |
| 14 | 採用：写しの読み戻しの確認を外す | 検出（2件） | `test_a_copy_that_reads_back_differently_stops_before_the_replace` |
| 15 | 採用：写しを公開の後に作る | 検出（11件） | `test_a_failed_directory_sync_after_the_replace_is_commit_uncertain_and_resumes` ほか |
| 16 | 採用：再開で、退避先の写しの識別値の確認を外す | 検出（1件） | `test_a_tampered_copy_makes_the_finished_state_unrecognised` |
| 17 | read_set_aside：MANIFESTとの照合を外す | 検出（1件） | `test_read_set_aside_returns_the_bytes_only_when_they_match_the_manifest` |
| 18 | 公開値の型の確認をロックの後へ | 検出（2件） | `test_hand_made_values_without_mode_or_source_or_with_a_bad_hash_are_a_shape_error` |
| 19 | exceptの中の1か所を `raise … from None` に戻す（`_read_regular`） | 検出（9件） | `test_a_message_with_the_path_in_it_never_reaches_an_error` |
| 20 | ロック名を替える | 検出（59件） | `test_a_directory_lock_is_reported_with_regular_false` ほか |
| 21 | test_c3_09の固定行を替える | 検出（20件） | `test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range` |

追加（依頼書にない）：

| ID | 注入 | 結果 |
|---|---|---|
| E1 | `check_plan` の名前の規則を外す | 検出（1件） |
| E2 | `maintenance_incomplete` への変換を外す | 検出（21件） |
| E3 | 採用の完了判定で `reconcile` を外す | 検出（1件）`test_a_history_file_that_is_not_the_candidate_is_not_a_finished_adoption` |
| E4 | 退避先のdir fsyncを外す | 検出（7件） |
| E5 | ロックのマーカーをC-3のものにする | 検出（8件） |
| E6 | 公開前の所有確認を外す | 検出（3件） |
| E7 | 移行の再開でsnapshot.jsonの識別値の確認を外す | 検出（1件）`test_a_snapshot_with_other_bytes_stops_the_resume_before_any_move`（後ろの `_move` の確認が同じ誤りを止めるので、見え方の違いは段階（scan／move）だけ） |
| E8 | WindowsのSTRICT拒否を外す | 検出（1件） |
| E9 | 解錠で、root から消えた対象の退避先照合を外す | 検出（2件） |
| 19b | `_mkdir` のexcept内で `raise … from None` | **等価と判断**（下） |

**等価の根拠（19b）**：`_mkdir` は失敗の前に必ず `ctx.changed = True` を立て、`LocalStoreError("store_io_error", "quarantine", …)` を投げる。この誤りは `_locked` の `except` に捕まり、`_incomplete` が**例外処理の外で**新しい `maintenance_incomplete` を作り直して返す。作り直した誤りには `__context__` が無いので、`from None` を中に書いても外に出る誤りの `__context__`／`__cause__` は変わらない（直接確かめた：注入後も `__context__` が None）。出口の誤りに差が出ないため、試験では区別できない。同じ規則を試験で固定するために、出口に差が出る `_read_regular` の注入（項目19）を使った。

**最初の実行で未検出だったもの**（試験を補ってから最終版で全部やり直した）：項目2（15d5cbc、`lstat` と `read_file` の間の入れ替えしか試験していなかった）、項目12・19（mkdir形）・E3・E7（139d290）。補った試験は `test_the_inode_changes_between_the_listing_and_the_rename`、`test_a_history_file_that_is_not_the_candidate_*`（移行2件・採用1件）、`test_a_snapshot_with_other_bytes_stops_the_resume_before_any_move`。最初の実行の出力は `first_pass/`。

## 10. C4-16 の総当たり、C4-22 の模擬

**C4-16（Python 3.13、`sweep_py3.13.log`）**：全呼出し×前後×例外3種の単独故障。合計 **2,154通り**、違反0。

| 場面 | durability | 通り | 結果の分類 |
|---|---|---|---|
| adopt | file_sync_only | 264 | incomplete 123、ok 6、busy 4、commit_uncertain 24、io_error 83、ownership_lost 12、root_invalid 12 |
| adopt | strict | 306 | incomplete 147、ok 6、busy 4、commit_uncertain 30、durability_unsupported 12、io_error 83、ownership_lost 12、root_invalid 12 |
| migrate | file_sync_only | 231 | incomplete 87、ok 9、busy 4、commit_uncertain 24、io_error 83、ownership_lost 12、root_invalid 12 |
| migrate | strict | 279 | incomplete 117、ok 9、busy 4、commit_uncertain 30、durability_unsupported 12、io_error 83、ownership_lost 12、root_invalid 12 |
| unlock（ロックあり） | file_sync_only | 243 | incomplete 150、ok 21、io_error 60、root_invalid 12 |
| unlock（ロックあり） | strict | 279 | incomplete 180、ok 21、durability_unsupported 6、io_error 60、root_invalid 12 |
| unlock（一時ファイルのみ） | file_sync_only | 258 | incomplete 135、ok 18、busy 4、io_error 77、ownership_lost 12、root_invalid 12 |
| unlock（一時ファイルのみ） | strict | 294 | incomplete 165、ok 18、busy 4、durability_unsupported 6、io_error 77、ownership_lost 12、root_invalid 12 |

どの通りでも、出るのはCoreError（S2の語）だけ、元のバイトはrootか退避先に残り、`history.json` は元か候補、漏れ（パス・秘密）なし、人の手順（inspect→解錠→同じ操作）で最終の状態に着く。

**C4-22（`next_stage_sim.sh`、使い捨てのworktree、pushしない）**（`next_stage_sim_out.txt`）：
- [A] 試験対象そのまま：範囲の鎖34・C-1 112・C-2 150・C-3 139・C-4 180 すべて OK。
- [B] C-4の範囲試験の `END` だけを試験対象に替える（1行）：範囲の鎖が**失敗2件**（開いた範囲が無くなるため。期待どおり）。ほかは OK。
- [C] [B]に、仮の開いた範囲試験1本（`START` ＝試験対象、`END = None`）を足す：すべて OK。

## 11. 利用者向けの復旧手順（設計§5.4、短く）と requested_at（Q-01）

1. 失敗したら `inspect()` で root の残り物を見る（`artifacts` に一時ファイルとロックが並ぶ。cleanupの語には頼らない）。
2. 残り物があれば、書き手がすべて止まっていることを人が確かめ、`plan_unlock(report, 依頼ID, True)` → 計画の `plan_hash` を確認して `unlock(plan, plan_hash)`。
3. **同じ操作**（`migrate` か `adopt`）をもう一度呼ぶ。移行・採用の公開値が必要なら、`read_original`／`read_set_aside(key, name)` で得た元のバイトから、**最初と同じ入力**（`requested_at` を含む）で作り直す。
4. 作り直した公開値の `publication_hash` が最初の `key`（退避先のディレクトリ名）と違えば、**操作を呼ばない**（入力が違う）。呼んだ場合の動作は固定してあり、移行は `maintenance_state_unexpected`、採用は `publication_stale`（rule `raw`）で止まり、rootは変わらない。

**Q-01：requested_at の読み方** — `requested_at` は、移行なら**候補の `history.json` の `SCHEMA_MIGRATION` 記録**、採用なら**`RECOVERY_PREFIX_ADOPTION` 記録**の `requested_at` に書かれている。値はZ終わりのISO 8601文字列（例 `2026-…Z`）。`datetime.fromisoformat` は Python 3.10 でZを読めないので、`s.replace("Z", "+00:00")` にしてから渡す（`test_the_requested_at_can_be_read_back_from_the_candidate_record`／`…_adoption_record` が3.10〜3.13で確かめている）。history.json が元に戻っているとき（replace前に止まった等）は、`inspect` で元の公開値の入力を人が保存しておいた値を使う。

## 12. 未解決・未実施・限界

- 実Windows、物理電源断、ユーザーPC、ネットワークドライブ、Windowsの合計（新規180＋1,593）は**未実施**。C-4のWindows専用の確認（STRICTの拒否、rename・mkdir・ディレクトリの扱い、ロック・一時ファイル名の扱い）は、実Windowsで行うまで未実施。Windowsの挙動は `is_windows` を替えた記録の子クラス（STRICTの拒否の確認）で確かめただけで、実Windowsの代用ではない。
- `inspect` はロックなしで読むので、他の書き手が動いている最中の一覧は一瞬の写しにすぎない（計画の実行時に再確認する）。
- 計画の「書き手がすべて止まっている」は人の宣言で、証明ではない（設計どおり）。
- 日次の通知・Sheets・Discord・本番・S4には接続していない。

## 13. 保存したもの（`/mnt/project-files/implementation/c4_maintain_20261104/`）

`runall.sh`、`mutate.py`、`mutation_out.json`／`.txt`、`first_pass/`、`next_stage_sim.sh`／`_out.txt`、`final_runall_py3.{10,11,12,13}.log`、`sweep_py3.13.log`、`archive_tree_skips.log`、`refcheck.py`・`refs_protected82.txt`・`refs_final_before_push.txt`。

## 14. 追補：実装レビューのN-01の限定修正（2026-11-04）

実装レビュー（記録906a70a）のN-01（通常）だけを直した。提案P-01〜P-04には手を付けていない。

- **修正**：`v2_history_maintain/store.py` の `_migrate_resume` で、`history.json` をロックの下で読んだ結果が `None`（lstat／read_fileがFileNotFoundError）のとき、`self._read(...)[0]` が `TypeError` を漏らしていた2か所を、固定のエラーにした。読み始め（旧787行）は、今までと同じ `maintenance_state_unexpected`（rule `v1_and_v2`／`v2_present`）。renameの後の読み直し（旧809行）は、`maintenance_state_unexpected`／store／scan／rule `v2_present`（移行の完了を示せないため）。ほかの `_read` の呼出しは、すでに `None` を扱っている。
- **試験**：`test_c4_04_migrate.py` の `Resume` に4件（lstat・read_fileの2種×「両方」「完了後」×読み始め・読み直し＝8ケース）を足した。新規は 180→**184** 件。修正前のコードでは8ケースとも失敗する（`TypeError`）ことを確かめた。
- **試験した版**：修正コミット `195d3531007a0fb8319db90ccd058c664d04d885`。完全な履歴の別クリーンクローン（`core.autocrlf=false`）で、Python 3.10.20／3.11.18／3.12.3／3.13.18の4版とも15スイートが全件合格（既存2,069＋新規184＝2,253件、失敗0・エラー0・新規のskip 0）。ログは `fix_n01_runall_py3.{10,11,12,13}.log`。
- 総当たり（§10）の例外の種類にFileNotFoundErrorなどを足すことは、今回はしていない（レビューの任意の提案の範囲）。§0・§10の「どの通りでもCoreErrorだけ」は、この追補の前までは依頼の3種の例外での結果である。
- 実Windows・物理電源断・ユーザーPCは、引き続き未実施。
