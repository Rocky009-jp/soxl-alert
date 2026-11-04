# V2 S4-A 朝の1回の実行（オフライン）限定実装の結果

作成日：2026-11-04（日本時間）。担当：Claude Sonnet 5.5（セッション設定 `claude-sonnet-5-5[1m]`、effort `high`。最後に実行したモデルも `claude-sonnet-5-5` と、`get_session` で確かめた）。
対象：`Rocky009-jp/soxl-alert`、新ブランチ `feat/v2-daily-run-s4a-20261104`。PR・マージ・Actions・本番・通知・S4-B以降はしていない。外部への接続、リポジトリの作成、秘密の登録もしていない。

## 0. 要約

- S4-Aの限定実装は**完了**した。新パッケージ `v2_daily_run`（3ファイル289行）と、新しい試験 `tests/v2_daily_run`（9本の試験ファイルと2本の補助、96件）を足し、既存の1ファイル（`test_c4_09_scope.py`）の**1行だけ**（`END`を `2e6ba5f` に固定）を変えた。
- 試験対象 `c15ab18` で、完全な履歴の別クリーンクローン（`core.autocrlf=false`）の Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版とも、**既存15スイート2,253件＋新規96件が全件合格**（失敗0・エラー0・新規のskip 0。既存のskip 4件はS2のもの）。
- 欠陥注入は依頼書の15項目に追加15件を加えた**30件**。**30件すべて検出**（等価0・未検出0・準備失敗0。§9）。
- S4A-13(b) の子プロセス競合（2〜4個）、S4A-14 の総当たり（CoreError 6種×14呼出点＝84通りと、CoreError以外の例外19通り）、S4A-16 の次の段階の模擬は期待どおり。
- **未実施**：実Windows、物理電源断、ユーザーPC、ネットワークドライブ・同期フォルダ。他者の結果で代用していない（§14）。
- 設計・依頼書の矛盾や範囲外の変更は**見つからなかった**。止めた箇所はない。提案P-01〜P-07、C-4レビューのP-01〜P-04は対象外のまま（§12）。

## 1. 固定した資料と起点

| 項目 | 値 |
|---|---|
| 資料コミット（docs/v2-s4-daily-run-20261104、D-1〜D-7の採用記録） | `7542a1829a8c16e0842d53a846dc23b83f6d2ee6` |
| 設計 `docs/specs/V2_S4_DAILY_RUN_DESIGN_DRAFT.md`（blob） | `244df2b9bb4018f97975a1706d39b52a300e385f` |
| 依頼書 `docs/tasks/V2_DAILY_RUN_S4A_LIMITED_IMPLEMENTATION_REQUEST.md`（blob） | `8b983d32be022eed27eeae834a8ea2a324bb5dca` |
| 試行差分 `docs/specs/V2_DAILY_RUN_S4A_TRIAL_20261104.diff`（blob） | `b0c20c652a7d0a08250e0d25992af6e11cf02b01`（sha256 `13df420c6ad3c7a050e51b67f6f29fd10320f7e063f69abb3a2076673b14821e`、取り出して確認） |
| コードの開始点 | `2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb`（C-4の保存最終） |
| **試験対象（コード・試験の最終）** | `c15ab18ae7a02dc9bef900412ae3af7862c232d1` |
| 最終（この結果文書の追加） | この文書だけを足した次のコミット。SHAはpushの報告に書く |

保護参照は、依頼書§7の88参照に、資料ブランチ（`7542a18`）とレビュー（`dd60f6f`）の2本を加えた**90参照**を、開始時と試験前・push前に完全なSHAで照合した（`refcheck.py`、`refs_*.txt`）。開始時は**88参照が一致**（追加の2本は実装前に存在を確認）。結果は§10。D-1〜D-7は第2版（`3dc7bf9`）に対してRockyさんが採用済み（設計§11）で、本書はその採用を前提にしている。

## 2. 変更したもの

| 場所 | 内容 |
|---|---|
| `v2_daily_run/__init__.py`（9行） | 公開名：`run_morning`・`RunReport`・`ConsumedDay`・`RunError`・`DONE`・`STALE`・`STOPPED` |
| `v2_daily_run/values.py`（86行） | 結果の語、`RunError`（`CoreError`の子）、`ConsumedDay`・`RunReport`（不変、reprに文面・パス・digestを出さない） |
| `v2_daily_run/run.py`（194行） | `run_morning`。引数検査→対象D→`store.read`→開始位置→追いつきのループ→対象Dの評価→報告 |
| `tests/v2_history_maintain/test_c4_09_scope.py` | 18行目 `END` の**1行だけ**（下の差分） |
| `tests/v2_daily_run/`（新規11ファイル） | `s4a_helpers.py`、`s4a_worker.py`、`test_s4a_01〜09_*.py`（`__init__.py`は作っていない） |
| `docs/implementation/V2_DAILY_RUN_S4A_RESULT.md` | この文書（別のコミット） |

分け方は3ファイル（`__init__`・`values`・`run`）で、許された4ファイルより少ない。ランタイムの全文は `v2_daily_run/` の3ファイル（289行）で、ブランチの試験対象コミットにある。

test_c4_09の差分の全文（`git diff --unified=0 2e6ba5f 試験対象 -- tests/v2_history_maintain/test_c4_09_scope.py`）：

    @@ -18 +18 @@ START = "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a"
    -END = None          # not accepted yet; the next stage replaces None with the accepted final commit
    +END = "2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb"   # accepted (re-review 8d02abf); frozen when S4-A began

試行差分の同じ行（blob `bea589a..be25c0b`）と完全に一致した。変えていないもの：既存の14パッケージ（`v2_core`〜`v2_history_maintain`）、既存の試験・ヘルパー、ほかの範囲試験、設定・依存・workflow・`main.py`・研究・STATUS等（S4A-16で確認）。

## 3. ランタイムの規則（依頼書§3のとおり）

1. 入口は `run_morning(store, now, series, sessions, raw_observations) -> RunReport` だけ。時計・環境変数・ファイル・ネットを使わない。
2. 引数の検査は保存先を読む前：nowがtzinfo・utcoffsetの無い、または`datetime`でない／sessionsが`SessionList`でない／storeに`read`・`publish`・`reconcile`が呼べない、は`RunError`（code `run_args_invalid`、fieldは`now`・`sessions`・`store`、この順に検査）。
3. 対象D＝`close_at <= now`の最後のセッション。無ければ`RunError`（`run_no_closed_session`）。これも保存先に触れる前。
4. 開始位置＝`read_effective(history).processing_after`（`latest_apply_d`は使わない。第2版のN-01）。対象Dがこれより前なら`STOPPED`（`run_target_before_head`）で何も書かない。
5. 開始位置より後、対象D以前のセッションを古い順に見る。未確定に当たったら`STALE`（`run_session_unconfirmed`、detailにそのD）。それより前の保存は残し、それより後へは進まない。
6. `PREPARED`の日だけ`publish_day`→`store.publish`、返ったhistoryで続ける。`NO_COMMIT`・`ALREADY_APPLIED`は保存しない。ほかの状態は`AssertionError`（プログラムの誤り）。
7. 対象Dの評価：ループで調べていればその結果、開始位置が対象Dと同じならば`prepare_history_day`を1回。そのCoreErrorも`STOPPED`。
8. 成否不明（`store_commit_uncertain`）：同じ公開値で`store.reconcile`を1回。`PUBLISHED`・`PUBLISHED_THEN_EXTENDED`なら`store.read()`で読み直し、開始位置から追いつきをやり直す（同じ実行では高々1回、2回目の成否不明は`run_publish_uncertain`）。`NOT_PUBLISHED`は`run_publish_not_published`、`CONFLICT`は`run_publish_conflict`。`publish`は同じ公開値で2回呼ばない。
9. 保存先を読んだ後のCoreErrorはすべて`STOPPED`（code・field・ruleを写す）。例外処理の中は値を作るだけで、`RunReport`は外で作る。CoreError以外の例外はそのまま出る。
10. 報告は不変の値。`exit_code`はDONEが0、STALE・STOPPEDが1。消費した日ごとにd・状態・gap・skipped_sessions。
11. 文面：DONEは、gapのある日の行（欠測のセッションの日付つき）の後に、対象Dの`render_message`の全文を変えずに続ける。STALE・STOPPEDは判定・分岐表・b\*を含めず、「条件未達ではない」「前日値で補っていない」、code、保存した日を書く。パス・例外の本文・URL・秘密は入れない（codeなどは小文字・数字・`_`だけの識別子のときだけ写し、そうでなければ`unknown_error`／空にする）。

## 4. 試行の下書き（設計§8）との違い

| 下書き | 実装 | 理由 |
|---|---|---|
| 開始位置 `latest_apply_d or processing_after` | `processing_after` だけ | 第2版N-01（再初期化の後で止まらないように）。S4A-17で確認 |
| `rec.status`で成否不明の結果を見る | `rec.outcome` | C-2の`Reconciliation`は`outcome`を持つ（`status`は無い）。下書きのままだと`AttributeError`になる。実物のC-3の`reconcile`で確認した |
| 成否不明の後、読み直して**途中の位置から**続ける | 読み直して**開始位置から**追いつきをやり直す、同じ実行で高々1回 | 依頼書§3の8（設計§5.4）。他の書き手が日を足した場合（`PUBLISHED_THEN_EXTENDED`）でも二重に保存しない |
| 1つの`RunReport`に`code`を文字列で（`run_session_unconfirmed:日付`） | code・field・rule・detailを別の項目に | 依頼書§3の9・10 |
| 引数の誤りcodeは`run_now_invalid`・`sessions_invalid` | `run_args_invalid`（fieldで区別）、storeの検査を追加 | 依頼書§3の2 |
| 対象Dの評価のCoreErrorを別に捕まえる | 同じ1か所の捕まえ口（ただし対象Dの評価は別の関数で、捕まえ口の内側） | 依頼書§3の7。欠陥注入11で外した形を検出 |
| 文面は`render_message`だけ | 欠測の行（T-1）、STALE・STOPPEDの文面 | 依頼書§3の11 |
| なし | 同じ公開値を2回送らない保険（`run_publish_uncertain`）、成否不明の後に結果が不明の語のとき`AssertionError`、codeなどの識別子フィルタ | 「`publish`は同じ公開値で2回呼ばない」の機械的な保証。嘘をつく保存先の試験（追加）と欠陥注入E1・E6で確認 |

## 5. 受入とテスト名の対応

新規の試験は96件（`tests/v2_daily_run`）。S4A-01は既存スイートの実行。

| ID | 試験 |
|---|---|
| S4A-01 回帰 | §7の全スイート（既存2,253件。test_c4_09の1行の固定を含む） |
| S4A-02 引数 | `test_s4a_01_args_target.Arguments`（5件。偽の保存先 `Silent` の呼出しが0回） |
| S4A-03 対象D | `test_s4a_01_args_target.Target`（4件。close_atちょうど／1マイクロ秒前／UTC・−5・+9・+14・前のセッション・全部未来） |
| S4A-04 通常の追いつき | `test_s4a_02_catch_up.Normal`（publish回数＝日数、各publish後と最終のバイトが独立の連鎖 `prepare_history_day→check_append_batch` と一致） |
| S4A-05 欠測 | `test_s4a_02_catch_up.MissingDay`（5件。欠測の行、gapが対象D、二つのgap、開始位置直後のgapなし） |
| S4A-06 再実行 | `test_s4a_02_catch_up.Rerun`（3件。publish 0回、バイト・文面・digest同じ、ALREADY_APPLIEDの文面） |
| S4A-07 対象Dの決定済み | `test_s4a_02_catch_up.DecidedTarget`（文面が`render_message`の全文と一致） |
| S4A-08 未確定 | `test_s4a_02_catch_up.Unconfirmed`（5件。STALE、exit 1、それより前だけ保存、判定・分岐表・b\*なし） |
| S4A-09 時刻の戻り | `test_s4a_02_catch_up.TimeWentBack`（4件。run_target_before_head、保存なし、例外が漏れない） |
| S4A-10 入力の誤り | `test_s4a_03_inputs_store_restart.InputErrors`（5件。ledger_mismatch、decision_outside_window、target_row_missing、session_context_missing） |
| S4A-11 保存先の停止 | `test_s4a_03_inputs_store_restart.StoreStops`（6件。実物のC-3。busy・uninitialized・read_only・layout_unsupported・artifact_present、importの確認） |
| S4A-12 成否不明 | `test_s4a_04_uncertain_conflict.Uncertain`（10件。(a)〜(e)と、`PUBLISHED_THEN_EXTENDED`、嘘をつく保存先、想定外の結果） |
| S4A-13 競合 | (a) `test_s4a_04_uncertain_conflict.OtherWriterBetween`（2件）、(b) `test_s4a_06_processes`（子プロセス2・3・4個） |
| S4A-14 例外の出口 | `test_s4a_05_exceptions.Sweep`（4件。CoreError 6種×14呼出点＝84通りと、CoreError以外の例外19通り） |
| S4A-15 静的な範囲 | `test_s4a_08_static.Runtime`（7件）、`test_s4a_07_values_text`（不変・repr・文面の漏れ、8件） |
| S4A-16 範囲試験 | `test_s4a_09_scope`（19件）、模擬は`next_stage_sim.sh`（§11） |
| S4A-17 再初期化の後 | `test_s4a_03_inputs_store_restart.AfterReinitialisation`（3件。独立の履歴構築 `HB` で RESTART_UNKNOWN の後） |

## 6. 結果の確認（実際に行ったこと）

- 期待値は、既存の関数（`prepare_history_day`・`check_append_batch`・`render_message`・`validate_history`）と、独立の履歴構築（`h_helpers.HB`）、試験側のバイト書き（`c2_helpers.file_bytes`）から作った。ランナーの出力をコピーしていない。
- 保存先は実物のC-3（`HistoryFileStore`、一時ディレクトリ、`file_sync_only`）。成否不明・競合・読取の失敗は、実物を包んだ台本つきの偽物で起こした。実物のreconcileの結果（`PUBLISHED`・`PUBLISHED_THEN_EXTENDED`・`NOT_PUBLISHED`・`CONFLICT`）を使った。
- 子プロセスは `-B -I` で起動し、ファイルの合図で同時に始める。結果は、どの並びでも成り立つ事実（各報告がDONEかstore_busy・publication_stale、日の二重なし、途中までの前の部分、DONEがあれば全部、その後の1回で全部）だけを確かめる。

## 7. 全スイートの結果

試験対象 `c15ab18` を、完全な履歴の別クリーンクローン（`core.autocrlf=false`、浅くない）で、`-B -W error::ResourceWarning`、`PYTHONDONTWRITEBYTECODE=1`で実行した。ログは `final_runall_py3.10〜3.13.log`。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---|---|---|---|---|
| v2_core | 197 | OK | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK | OK |
| v2_persistence_local | 113 | OK (skip 4) | OK (skip 4) | OK (skip 4) | OK (skip 4) |
| v2_recovery | 176 | OK | OK | OK | OK |
| v2_history | 230 | OK | OK | OK | OK |
| v2_history_ops | 173 | OK | OK | OK | OK |
| v2_history_restart | 109 | OK | OK | OK | OK |
| v2_history_restore | 165 | OK | OK | OK | OK |
| v2_history_diagnose | 131 | OK | OK | OK | OK |
| v2_history_adopt | 170 | OK | OK | OK | OK |
| v2_scope_chain | 34 | OK | OK | OK | OK |
| v2_history_consume | 112 | OK | OK | OK | OK |
| v2_history_publish | 150 | OK | OK | OK | OK |
| v2_history_local | 139 | OK | OK | OK | OK |
| v2_history_maintain | 184 | OK | OK | OK | OK |
| v2_daily_run | 96 | OK | OK | OK | OK |

既存15スイートの計は2,253件、新規`v2_daily_run`は96件。4版とも失敗0・error 0・終了コード0。新規のskipは0（既存のskip 4件はS2のWindows専用の試験）。


## 8. 欠陥注入

試験対象 c15ab18 の一時worktreeに1件ずつ変異を入れ（範囲試験がGitのHEADを読むため各変異をコミット）、`tests/v2_daily_run` の96件を実行した（`mutate.py`、結果は `mutation_out.json`・`.txt`）。依頼書の15項目は「依頼N」、追加は「追加N」。

| ID | 内容 | 結果 | 落ちた試験（件数。例） |
|---|---|---|---|
| 依頼1 | target: close_at <= now becomes close_at < now | DETECTED | 2件。test_now_equal_to_the_close_is_that_session_and_a_microsecond_before_is_the_previous_one |
| 依頼2 | an unconfirmed session is skipped and the run goes on | DETECTED | 5件。test_a_stale_run_leaves_the_store_so_that_the_next_run_after_the_data_is_confirmed_continues |
| 依頼3 | an unconfirmed session does not stop the run (no STALE): the evaluation goes on | DETECTED | 5件。test_a_stale_run_leaves_the_store_so_that_the_next_run_after_the_data_is_confirmed_continues |
| 依頼4 | the start is latest_apply_d (the whole history), not processing_after | DETECTED | 3件。test_an_acknowledgement_and_a_declaration_after_the_restart_do_not_move_the_start |
| 依頼5 | the target is taken out of the loop (< target instead of <= target) | DETECTED | 22件。test_a_target_whose_decision_was_recorded_before_the_run_is_consumed_and_its_text_is_the_result |
| 依頼6 | a PREPARED day is not saved | DETECTED | 50件。test_a_target_whose_decision_was_recorded_before_the_run_is_consumed_and_its_text_is_the_result |
| 依頼7 | the line for a gap is dropped from the text | DETECTED | 2件。test_the_text_carries_a_line_for_the_gap_with_the_missing_date_and_then_the_core_text |
| 依頼8 | NOT_PUBLISHED is treated like a success | DETECTED | 1件。test_a_save_that_did_not_happen_is_not_published_the_run_stops_and_publish_was_called_once |
| 依頼9 | NOT_PUBLISHED: the same publication is published once more | DETECTED | 2件。test_a_save_that_did_not_happen_is_not_published_the_run_stops_and_publish_was_called_once |
| 依頼10 | after a published (or extended) outcome the history is not read again | DETECTED | 6件。test_a_save_that_was_followed_by_another_writers_day_is_published_then_extended_and_read_again |
| 依頼11 | the CoreError of the target evaluation is not turned into STOPPED | DETECTED | 1件。test_a_target_that_is_the_genesis_boundary_is_stopped_by_the_core_code |
| 依頼12 | the report is made inside the exception handler (the exception stays as its context) | DETECTED | 85件。test_every_core_error_at_every_call_point_gives_a_stopped_report_with_nothing_left_of_the_exception |
| 依頼13 | except CoreError becomes except Exception in run_morning | DETECTED | 16件。test_an_unknown_outcome_of_a_store_is_a_program_error_that_passes_through |
| 依頼14 | a STALE run also carries the full core text (of the last evaluated day) | DETECTED | 4件。test_the_text_of_a_stale_run_has_no_judgement_no_branch_table_and_no_b_star |
| 依頼15 | now is read from the clock instead of the argument | DETECTED | 37件。test_no_session_closed_yet_is_a_run_error_before_the_store_is_touched |
| 追加1 | the guard against publishing the same value twice removed | DETECTED | 1件。test_a_store_that_says_published_but_did_not_publish_never_gets_the_same_value_twice |
| 追加2 | a second uncertain save in the same run is reconciled again (no limit of one restart) | DETECTED | 1件。test_a_second_uncertain_save_in_the_same_run_stops_and_reconcile_was_called_once |
| 追加3 | the day of a reconciled save is not counted as consumed | DETECTED | 6件。test_a_save_that_was_followed_by_another_writers_day_is_published_then_extended_and_read_again |
| 追加4 | target before the start uses <= (the start itself is refused) | DETECTED | 7件。test_after_the_target_was_consumed_a_run_again_is_the_already_applied_text |
| 追加5 | the store methods are not checked | DETECTED | 1件。test_a_store_without_the_three_methods_is_refused |
| 追加6 | the code of an error is passed to the text as it is (no identifier filter) | DETECTED | 16件。test_every_core_error_at_every_call_point_gives_a_stopped_report_with_nothing_left_of_the_exception |
| 追加7 | every store error is treated as an uncertain save | DETECTED | 22件。test_a_read_only_store_stops_at_the_first_publication_and_not_before |
| 追加8 | a now whose offset is None is accepted | DETECTED | 1件。test_a_now_that_is_not_an_aware_datetime_is_refused_and_the_store_is_not_touched |
| 追加9 | the target is never evaluated when nothing lies after the start | DETECTED | 7件。test_after_the_target_was_consumed_a_run_again_is_the_already_applied_text |
| 追加10 | the start day itself is looked at again (s.date < start) | DETECTED | 51件。test_after_the_target_was_consumed_a_run_again_is_the_already_applied_text |
| 追加11 | a restart is allowed without limit (the counter is never raised) | DETECTED | 1件。test_a_second_uncertain_save_in_the_same_run_stops_and_reconcile_was_called_once |
| 追加12 | the report digest is not the last history's | DETECTED | 3件。test_the_repr_shows_neither_the_text_nor_a_path_nor_the_digest |
| 追加13 | the report is not immutable | DETECTED | 1件。test_the_report_and_its_days_are_immutable |
| 追加14 | the exit code of STALE is 0 | DETECTED | 3件。test_an_unconfirmed_session_in_the_middle_stops_the_run_with_stale_and_keeps_the_days_before |
| 追加15 | the consumed day's skipped sessions are dropped | DETECTED | 4件。test_a_day_without_a_decision_is_not_saved_and_the_next_saved_day_carries_the_gap |


## 9. 欠陥注入の分類

- **検出30、等価0、未検出0、準備失敗0**。最初の実行（同じ木の旧コミット664cd26）も、試験対象c15ab18での再実行も、30件すべて検出で、試験は補っていない。
- 依頼6（保存しない）・12（例外処理の中で報告を作る）・13（`except Exception`）・15（時計）は多数の試験が落ちる。1件だけが落ちる項目（依頼8・11、追加1・2・5・8・11・13）は、その1件がその欠陥専用の試験である。
- 依頼4（`latest_apply_d`）は、再初期化の後のS4A-17（通常の流れでは差が出ない）で検出。向きは第2版N-01に従い、`processing_after`が正しい側。

## 10. 保護参照

保護90参照（依頼書§7の88＋`7542a18`＋`dd60f6f`）を完全なSHAで照合した。

| 時点 | 結果 |
|---|---|
| 開始時（実装前） | 88参照が一致（追加の2本は存在と値を確認） |
| 全スイート・欠陥注入の後（試験対象c15ab18） | **90参照、不一致0** |
| push前・push後 | 報告に書く |

## 11. S4A-14の総当たり、S4A-16の手順と結果

S4A-14：保存先の`read`・`publish`・`reconcile`と、`read_effective`・`prepare_history_day`・`publish_day`の各呼出し（成否不明を1回起こす場面で数えた14呼出点）について、k回目に次の6種のエラーを起こした：`InputError`・`PersistenceError`（rule付き）・`ConflictError`・`LocalStoreError`・`CoreError`（detailに日付）・`CoreError`（code・field・detailにパスやURL風の文字列）＝**84通り**。すべて例外は漏れず`STOPPED`の`RunReport`を返し、エラーのcodeを写し（敵対的な文字列は`unknown_error`と空）、報告の中・文面・reprに文字列が残らず、`RunReport`は例外処理の外で作られた（`sys.exc_info()`が空であることを、`RunReport`を包んで確かめた）。続けて`RuntimeError`を14呼出点で、`KeyError`・`AttributeError`・`AssertionError`・`OSError`・`ValueError`を1点で起こした＝**19通り**。すべて**同じ例外の物がそのまま出て**、`__context__`・`__cause__`は空。

S4A-16：C-4の範囲試験の `END` だけを `2e6ba5f` に固定し、開いた範囲を外した場合（C4-22と同じ形、`next_stage_sim.sh`）。

次の段階の模擬の出力（`next_stage_sim_out.txt`）：

    [A] tested commit c15ab18ae7a02dc9bef900412ae3af7862c232d1
      v2_scope_chain: Ran 34 tests in 3.107s | OK
      v2_history_maintain: Ran 31 tests in 2.315s | OK
      v2_daily_run: Ran 96 tests in 15.711s | OK
     1 file changed, 1 insertion(+), 1 deletion(-)
    [B] END frozen, no open range (expected: test_sc_02 chain test fails)
      v2_scope_chain: Ran 34 tests in 3.119s | FAILED (failures=2)
      v2_history_maintain: Ran 31 tests in 2.694s | OK
      v2_daily_run: Ran 96 tests in 16.279s | OK
    [C] END frozen + minimal open range of the next stage
      v2_scope_chain: Ran 34 tests in 3.030s | OK
      v2_history_maintain: Ran 31 tests in 2.414s | OK
      v2_daily_run: Ran 96 tests in 16.230s | OK
    
- [A] 試験対象のまま：全部合格（範囲の鎖34件、C-4の範囲試験31件、S4-A 96件）。
- [B] S4-Aの範囲試験の`END`だけを試験対象に固定し、開いた範囲を足さない：範囲の鎖の試験が**2件失敗**（期待どおり。次の段階は開いた範囲を同時に足す）。
- [C] [B]に、次の段階の開いた範囲（START＝試験対象、END＝None）を足す：全部合格。

また、`FilesChanged`は`2e6ba5f`との差を、追加はランタイム3＋試験11＋結果文書1の許可したファイルだけ、変更は`test_c4_09_scope.py`の1行だけと確かめ、鎖は`…→6d69bd7→2e6ba5f→（S4-A）`が通る。

## 12. 文面の例

各文面は`test_the_four_examples`が作るものと同じ場面（合成の平日40日）。核の文面（市場側・分岐表・b\*など）は`render_message`のままなので、先頭部分だけ載せる。

**DONE（欠測なし、対象DのF&G未記録）**：先頭は核の文面そのもの。

    【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／実行区分: F&G観測待ち
    データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2026-03-02〜2026-03-06、5行）
    市場側（F&G以外の条件を含む判定）
    ……（以下、核の全文）

**欠測つきDONE**（2026-03-05にdecisionが無く、2026-03-06を消費）：

    【今回の追いつきで見つかった欠測】
      2026-03-06 を消費しました。直前までの観測が途切れていました（decisionの無いセッション: 2026-03-05）。
    【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-09 ／実行区分: F&G観測待ち
    ……（以下、核の全文）

**STALE**（2026-03-05が未確定）：

    【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／未確定のセッションがあります
      今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
      理由コード: run_session_unconfirmed（sessions）
      対象のセッション: 2026-03-05
      この実行で保存した日: 2026-03-03、2026-03-04
      市場状態は、保存した日までです。それより後の日は処理していません。

**STOPPED**（write.lockが残っている）：

    【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／実行を止めました
      今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
      理由コード: store_busy（lock）
      この実行で保存した日: なし
      市場状態は、保存した日までです。それより後の日は処理していません。


## 13. 追いつきの所要時間（参考。合否の条件にしない）

Linux、Python 3.13.18、合成の平日、`file_sync_only`、毎日decisionあり（`timing.py`、`timing_out.txt`）。

    17 days: first run 1.7s (DONE, consumed 17); same morning again 0.05s (DONE, consumed 0)
    37 days: first run 8.1s (DONE, consumed 37); same morning again 0.16s (DONE, consumed 0)

試行（設計§8）の37日9.8秒・再実行0.14秒と同程度。全件の再生を毎回行う（U-10）ため日数に対して二次的に増える。

## 14. 未実施・持ち越し

- **未実施**：実Windows（新規96件、C-4 184、C-3 139、範囲の鎖34）、物理電源断、ユーザーPC、ネットワークドライブ・同期フォルダ。
- **対象外のまま**（依頼書§2）：S4-B〜S4-E（通知・outbox・送信・gitの保存先・取得・入口・workflow・秘密・本番）、解錠・移行・採用の呼出し、保存の再試行、古さの上限（U-06）、C-4レビューのP-01〜P-04、レビューdd60f6fの提案P-01〜P-07。
- 実装で見えたこと（提案。実装には入れていない）：
  - 開始位置の直後の最初の日は、sessionsに欠測があっても核の `gap` が `False` のため欠測の行が出ない（`test_sessions_between_the_start_and_the_first_decision_are_skipped_but_not_a_gap_line` が現在の動作を固定している）。レビューのP-01（`skipped_sessions` を条件にする）を採るなら、行の条件とこの1件を変える。
  - 対象Dが境界そのものの朝は、核のコード `target_not_after_boundary` で`STOPPED`になる（P-03）。
  - 成否不明の後に読み直して再実行した日は、報告の `target_status` が `PREPARED` でなく `ALREADY_APPLIED` になる（バイト・文面・digest・消費した日は通常と同じ）。

次は、Rockyさんの受領判断と、Opus・highの別スレッドでの実装レビュー。
