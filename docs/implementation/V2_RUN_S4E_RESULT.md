# V2 S4-E（E-0）限定実装の結果：入口 `v2_run`、ひな形、手順書

実施：Claude Sonnet 5.5（セッション設定のモデル）。effort はスレッド起動時の指定（high）。セッション側で実際に適用された値は確認できていない。
日付：2026-11-05〜06。ブランチ `feat/v2-run-s4e-20261105`（PRなし）。範囲は依頼書 §2 の E-0 だけ。E-1以降・実際の取得・実際の送信・GitHubの実リモート・非公開リポジトリ・Actions・本番・PRは行っていない。

## 1. 固定資料と版

| 項目 | 値 |
|---|---|
| 依頼書・設計の採用版 | 第3版 `bcb03a1a7cf4d1acbdf96b6d5856696220490588`（採用記録 `a1ba2e7eac469cd869e17eadbd6e3fb5f73074ff`、資料ブランチ `docs/v2-run-s4e-20261105`） |
| blob（資料ブランチ a1ba2e7 の時点） | 設計 `docs/specs/V2_RUN_S4E_DESIGN_DRAFT.md`＝`32390df0b2d709a59bc58d6fff1505a2bd611bbf`、依頼書 `docs/tasks/V2_RUN_S4E_LIMITED_IMPLEMENTATION_REQUEST.md`＝`93350a567f96e5c5ea21c7344e880c0aa442d70c`、試行差分 `docs/specs/V2_RUN_S4E_TRIAL_20261105.diff`＝`f065499af59fc8696299ea0616b90cefc82674eb` |
| 開始（コード） | `9bdd4217d18e0ac328ddfa6a76b5d2a82748549d`（S4-D受領版） |
| 試験対象（コード・試験・ひな形・手順書の最終） | `bb4c135ca1b3bda86666b77082c66e6a8b938fcd` |
| 最終（この結果文書のコミット） | 試験対象の次の1コミット（差分はこの1ファイルだけ） |
| Python | 3.10.20、3.11.18、3.12.3、3.13.18 |
| git | 2.43.0（`core.autocrlf=false`） |
| 保護ref | 113件（109件＋800472f・4eb0ad5・fdf0e9b・a1ba2e7）を開始前・push後に照合（結果は §12） |

試験対象 `bb4c135` は、開始 `9bdd421` の1つ上の単一コミット（作業中の仮コミットは `git reset --soft` で1つにまとめ、どこにもpushしていない）。以下の全スイートと欠陥注入は、この `bb4c135` のクリーンクローン（`core.autocrlf=false`、完全な履歴、`git status` 差分なし）で実行した。

## 2. 変更したファイル（依頼書 §2 のとおり）

| 対象 | 行数 | 内容 |
|---|---|---|
| `v2_run/__init__.py` | 12 | 公開名 |
| `v2_run/__main__.py` | 5 | `sys.exit(main(sys.argv[1:]))` |
| `v2_run/entry.py` | 319 | `Setup`、5コマンド、引数、記録、`main` |
| `v2_run/web.py` | 171 | 取得（`make_fetch`）、`DiscordSender`、`DrySender`、`split_text`、`live_text` |
| `v2_run/check.py` | 107 | `check-source` の事実（`inspect` ほか） |
| `v2_notify/job.py` | 1行 | `judgment_known`（設計§8） |
| `v2_inputs/load.py` | 2行 | `fetch_count` の代入の位置 |
| `tests/v2_inputs/test_s4d_09_scope.py` | 1行 | `END` |
| `tests/v2_run/` | 15ファイル・2,954行 | `test_s4e_01〜13`（13本）、`s4e_helpers.py`、`s4e_worker.py`。`__init__.py` なし |
| `docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.yml` | 103 | ひな形（動かさない）。sha256 `156fe4aa3a9283544ccd7404931f10b42a71f66635cae37a8dcf67bf722f61a0` |
| `docs/ops/V2_PRIVATE_RUN_GUIDE.md` | 179 | 手順書。sha256 `f76d0e5aba7a433726e70ea5cb2f4d8109d73dd9c08d540fa114b85fa0c310b7` |
| `docs/implementation/V2_RUN_S4E_RESULT.md` | — | この文書 |

ランタイムの全文は、試験対象コミットの `v2_run/` の5ファイル（計614行）。パッケージは5ファイルで、分け方は設計どおり（変更なし）。

### 既存3ファイルの差分の全文（`git diff --unified=0 9bdd421 bb4c135`）

```diff
diff --git a/v2_notify/job.py b/v2_notify/job.py
index ffbedab..1153cd6 100644
--- a/v2_notify/job.py
+++ b/v2_notify/job.py
@@ -112 +112 @@ def morning_job(store, outbox, sender, now, series, sessions, raw_observations):
-    judgment_known = notice.kind == HALT or (notice.kind == ERROR and target_d is not None)
+    judgment_known = notice.kind in (HALT, ERROR)      # S4-E (S4-B review P-01): the fallback key checks its date too
diff --git a/v2_inputs/load.py b/v2_inputs/load.py
index df97f88..6ce3835 100644
--- a/v2_inputs/load.py
+++ b/v2_inputs/load.py
@@ -130 +129,0 @@ def load_inputs(git, fetch, now, refs, clock):
-            provenance["fetch_count"] = calls[0]
@@ -158,0 +158 @@ def load_inputs(git, fetch, now, refs, clock):
+    provenance["fetch_count"] = calls[0]                       # S4-E (S4-D review P-01): also after a parse error
diff --git a/tests/v2_inputs/test_s4d_09_scope.py b/tests/v2_inputs/test_s4d_09_scope.py
index ade91db..d6332d7 100644
--- a/tests/v2_inputs/test_s4d_09_scope.py
+++ b/tests/v2_inputs/test_s4d_09_scope.py
@@ -18 +18 @@ START = "ffa370089cd37fcc76658b4de0f4aedde0a246e0"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "9bdd4217d18e0ac328ddfa6a76b5d2a82748549d"   # accepted (receipt 43ebe55); frozen when S4-E began
```

## 3. 試行の下書き（設計§13）との違いと理由

- **T-5 `init`**：下書きは履歴があるとoutboxを作らなかった。本実装は、`v2-*-state` と `v2-*-outbox` を参照ごとに「無いときだけ」作り、あるものは `EXISTS`、片方だけがあれば足りないほうだけを作って終了0（S4E-03 c・d）。
- **`check-source` の `end`**：下書きはUTC日付の翌日。本実装は `now` のニューヨークの日付の翌日（`load_inputs` と同じ。T-6）。日本時間の朝とニューヨークの夕方で同じ日になる例を試験に含めた（S4E-08）。
- **Pythonの版**：下書きは記録しなかった。本実装は記録に `python: 3.13.18` の形で完全な版と、`git --version` の版を入れる（S4E-15 c）。
- **試行にはなく設計のRP/N項目として足したもの**：取得の失敗の理由を `fetch_failure: <記号> <語>` として記録（N-05）、`URLError(TimeoutError)` を `timeout`（RP-01）、URLに `?` があれば送信せず `NOT_STARTED`（P-05）、モードの1行のcase（RP-02）、`REFUSED_JUDGMENT_EXISTS`（S4-B P-02）。
- ひな形にはTP-01（秘密の条件は前のステップでモードを決め、liveのときだけ秘密を渡す）を注記として書いた（E-0では任意、E-4への申し送り）。
- 依頼書にない変更は行っていない。固定文書との矛盾は見つからなかった。

## 4. 受入と試験の対応

| ID | 試験（`tests/v2_run/`） | 件数 |
|---|---|---|
| 引数（§3）・公開名・5ファイル | `test_s4e_01_args.py`（不正な引数20通りが終了2で何にも触れない、値を表示しない、`code_version` の40桁） | 8 |
| S4E-01 回帰 | 全スイート（§5） | — |
| S4E-02 1回だけ決める | `test_s4e_02_once.py` | 7 |
| S4E-03 init | `test_s4e_03_init.py` | 13 |
| S4E-04 試運転の通し | `test_s4e_04_dry_run.py` | 4 |
| S4E-05 入力の失敗、S4E-11 `fetch_count` | `test_s4e_05_inputs.py` | 13 |
| S4E-06 送信の答え、S4E-07 分けと見出し、S4E-08（送信の形） | `test_s4e_06_send.py` | 20 |
| S4E-08（取得の形）、S4E-09 取得の上限と理由 | `test_s4e_07_fetch.py` | 13 |
| S4E-10 予備の鍵、S4E-12 再送と状態 | `test_s4e_08_judgment.py` | 13 |
| S4E-13 check-source | `test_s4e_10_check_source.py` | 13 |
| S4E-14 同時の実行 | `test_s4e_11_processes.py`（`s4e_worker.py`） | 1 |
| S4E-15 記録と機密 | `test_s4e_12_record.py` | 11 |
| S4E-16 測定 | 試験ではなく測定（§8） | — |
| S4E-17 静的な範囲 | `test_s4e_13_static.py` | 22 |
| S4E-18 範囲試験 | `test_s4e_09_scope.py` | 20 |
| 合計 | | 158 |

期待値は、研究のデータからS4-Dのヘルパーが作ったチャート応答、試験側で `git` を直接呼んで読んだバイト、偽の `urlopen` が受け取った要求から作っている。実際の `urlopen` は試験のヘルパーが「呼ばれたら失敗」する関数に置き換えている（`test_the_real_urlopen_is_replaced_in_the_tests`）。リモートはすべて一時ディレクトリのbare（パスの印 `SECRETMARK_`）、WebhookのURLの印は `SECRETTOKEN_`、失敗応答の本文の印は `SECRETBODY_`。

## 5. 全スイートの結果（S4E-01）

試験対象 `bb4c135` のクリーンクローンで、20スイートを `python -B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"` で1つずつ実行した（`PYTHONDONTWRITEBYTECODE=1`）。

| Python | 件数 | 失敗 | error | skip | 終了コード（20スイート） |
|---|---|---|---|---|---|
| 3.10.20 | 2,886 | 0 | 0 | 4 | すべて0 |
| 3.11.18 | 2,886 | 0 | 0 | 4 | すべて0 |
| 3.12.3 | 2,886 | 0 | 0 | 4 | すべて0 |
| 3.13.18 | 2,886 | 0 | 0 | 4 | すべて0 |

内訳：既存19スイート2,728件（S4-Dまでと件数が同じ。`v2_persistence_local` のskip 4件も同じ）＋新規 `v2_run` 158件＝2,886件。test_s4d_09の1行の固定と、job.py・load.pyの変更を含めて、既存の試験の結果は変わっていない（既存の試験は1行も直していない）。作業ツリーでも、Python 3.13で同じ2,886件が通った（仮コミット時点）。

## 6. 欠陥注入（依頼書 §5）

試験対象 `bb4c135` のクリーンクローンで、1件ずつ別のworktreeに作り、コミットして（Gitを読む範囲試験にも見えるようにして）、安い試験から順に実行した。「検出」は最初に落ちた試験。依頼の25件に、「または」の変種8件を足して33件。

結果：**検出33、等価0、未検出0、準備失敗0。**

| ID | 壊し方 | 分類 | 最初に落ちた試験（ファイル　クラス.テスト） |
|---|---|---|---|
| 01 | the clock is read twice (morning_job gets another now than load_inputs) | 検出 | 02 s4e_02_once.Once.test_the_clock_is_read_once_for_now_and_the_same_value_reaches_both_parts |
| 02 | dry uses the refs of the live run | 検出 | 03 s4e_03_init.EachOnlyWhenMissing.test_a_refused_history_does_not_stop_the_outbox_from_being_made_but_the_exit_is_1 |
| 03 | dry uses the DiscordSender | 検出 | 12 s4e_12_record.EnvironmentNames.test_a_dry_run_never_asks_for_the_secret_and_never_posts |
| 04 | a 4xx of the first part is UNKNOWN | 検出 | 06 s4e_06_send.Answers.test_a_failure_of_a_later_part_is_unknown_and_nothing_follows_it |
| 05 | a failure of a later part is NOT_STARTED | 検出 | 06 s4e_06_send.Answers.test_a_failure_of_a_later_part_is_unknown_and_nothing_follows_it |
| 06 | a failed part is posted once more | 検出 | 06 s4e_06_send.Answers.test_a_failure_of_a_later_part_is_unknown_and_nothing_follows_it |
| 07 | allowed_mentions is left out | 検出 | 06 s4e_06_send.ShapeOfAPost.test_every_post_of_a_long_text_blocks_mentions |
| 08 | the heading is not replaced | 検出 | 06 s4e_06_send.Heading.test_a_live_morning_posts_the_live_heading_and_the_outbox_keeps_the_original |
| 08b | the text that stays in the outbox is the replaced one | 検出 | 06 s4e_06_send.Heading.test_a_live_morning_posts_the_live_heading_and_the_outbox_keeps_the_original |
| 09 | the limit of a part is 2000 | 検出 | 01 s4e_01_args.PublicNames.test_the_names_and_the_constants_of_the_design |
| 10 | the form of the URL is not checked | 検出 | 06 s4e_06_send.LiveMornings.test_a_live_morning_without_the_secret_or_with_a_wrong_one_sends_nothing |
| 11 | a fetch accepts a status other than 200 | 検出 | 07 s4e_07_fetch.Limit.test_a_status_that_is_not_200_is_a_failure_with_its_digits |
| 12 | the 8 MiB limit of a fetch is dropped | 検出 | 07 s4e_07_fetch.Limit.test_exactly_8_mib_passes_and_one_byte_more_does_not |
| 13 | a morning of UNKNOWN ends with 0 | 検出 | 06 s4e_06_send.Heading.test_a_resend_goes_through_the_same_swap |
| 13b | a morning without a known judgment that was SENT ends with 1 | 検出 | 07 s4e_07_fetch.RequestsOfAMorning.test_four_symbols_once_each_in_order_with_the_exact_url |
| 14 | the refusal of a resend of HALT/ERROR over an existing judgment is removed | 検出 | 08 s4e_08_judgment.Resend.test_halt_and_error_resends_are_refused_when_the_morning_exists_in_any_state |
| 15 | the change of job.py is reverted | 検出 | 09 s4e_09_scope.FilesChanged.test_everything_else_is_blob_identical_to_the_code_start |
| 16 | the change of load.py is reverted | 検出 | 09 s4e_09_scope.FilesChanged.test_everything_else_is_blob_identical_to_the_code_start |
| 17 | the record holds the text of an exception | 検出 | 12 s4e_12_record.Exceptions.test_a_core_error_is_its_type_and_its_fixed_code |
| 18 | init accepts a day that is not closed | 検出 | 03 s4e_03_init.NotAccepted.test_a_day_that_has_not_closed_yet |
| 18b | init does not create the outbox when the history exists | 検出 | 03 s4e_03_init.EachOnlyWhenMissing.test_a_refused_outbox_makes_the_run_fail_and_the_rerun_finishes_it |
| 19 | check-source writes to the fixed refs (calls load_inputs) | 検出 | 10 s4e_10_check_source.Findings.test_an_older_close_that_changed_is_counted |
| 20 | morning_job is not called when load_inputs raised (no notice) | 検出 | 08 s4e_08_judgment.FallbackKey.test_a_damaged_morning_of_the_date_also_blocks_it |
| 21 | the timeout of a fetch is not passed | 検出 | 07 s4e_07_fetch.RequestShape.test_the_url_the_headers_and_the_timeout |
| 21b | the timeout of a post is not passed | 検出 | 06 s4e_06_send.ShapeOfAPost.test_every_post_of_a_long_text_blocks_mentions |
| 22 | the template cancels a run in progress | 検出 | 13 s4e_13_static.Template.test_the_concurrency_of_the_job |
| 22b | the template has no queue: max | 検出 | 13 s4e_13_static.Template.test_the_concurrency_of_the_job |
| 23 | the reason of a failed fetch is not recorded | 検出 | 07 s4e_07_fetch.WordsInTheRecord.test_the_record_of_a_morning_and_of_check_source_carry_symbol_and_word |
| 23b | the text of the exception is recorded as the reason of a failed fetch | 検出 | 12 s4e_12_record.EveryScene.test_no_scene_shows_a_mark_a_url_or_an_exception_text |
| 24 | status and check-source are in the group v2-writer | 検出 | 13 s4e_13_static.Template.test_the_concurrency_of_the_job |
| 25 | a scheduled run takes its mode from the input | 検出 | 13 s4e_13_static.Template.test_the_line_that_chooses_the_mode |
| 25b | a manual run ignores its mode | 検出 | 13 s4e_13_static.Template.test_the_line_that_chooses_the_mode |
| 25c | auto is fixed to dry | 検出 | 13 s4e_13_static.Template.test_the_line_that_chooses_the_mode |

注：
- 15と16は、安い順の最初が範囲試験（ブロブ・ハンクの固定）なので、そこで検出された。ふるまいの試験で効くかを、対照として別に確かめた（§7）。
- 03・13・13bは、狙いと違う試験が先に落ちた（13は再送の経路、13bは取得の要求の順）。ほかの試験も同じ欠陥で落ちることは確かめていない。
- 16は、依頼の「load.pyの変更を戻す」を、`9bdd421` のファイルそのものに戻して行った（最初に試した「追加した1行だけを消す」形は、元の位置の行も無いので戻しにならないため直した）。
- 08は見出しを置き換えない形、08bはoutboxに残る文面を置き換える形（`GitOutbox` の `claim` で文面を差し替える欠陥）。13は `UNKNOWN` の朝を終了0にする形、13bは判定なしの `SENT` の朝を終了1にする形。

## 7. 対照（S4E-10 と S4E-11）

- **S4E-10**：job.pyの `judgment_known` の変更だけ戻すと、`test_s4e_08_judgment` の2件（`test_the_error_of_a_date_with_a_judgment_is_not_sent`、`test_a_damaged_morning_of_the_date_also_blocks_it`）が `AssertionError: 'SENT' != 'SKIPPED_JUDGMENT_EXISTS'` で落ちる。つまり、同じ日付のMORNINGが判定ありでも、予備の鍵のERRORは送信を試みてSENTになる。変更を入れた状態では `SKIPPED_JUDGMENT_EXISTS`・送信0件。
- **S4E-11**：load.pyを `9bdd421` に戻すと、`test_s4e_05_inputs.FetchCount` の3件が落ちる（応答の形の誤りで止まった朝の `provenance["fetch_count"]` が `'0'`、期待は `'4'`。1記号目で止まる場合は `'0'`、期待は `'1'`）。

## 8. 測定（S4E-16）

試験対象 `bb4c135` のクリーンクローン、偽の `urlopen`、Python 3.13、この環境の4コア（ほかの処理と同時のときがあり、秒数は目安）。

**(a) outboxのファイル数と1回の読込み**（1ファイル約600バイトの詰め物を足したもの）：

| outboxのファイル数 | 1回の読込み `GitOutbox.load` | `outbox_status`（3件の鍵） | claim＋record |
|---|---|---|---|
| 1 | 0.01 s | 0.08 s | 0.09 s |
| 751 | 1.48 s | 8.23 s | 2.95 s |
| 1,501 | 2.88 s | 16.69 s | 5.37 s |

1回の `morning` が読むのは `load` 1回（`seconds.outbox_load`）。`outbox_status` は鍵ごとに読むので、ファイル数が多いと遅い（設計§10の閾値 `outbox_files > 1500` の近く）。実運用の増え方は1日2〜4ファイルなので、1,500ファイルは約1.5年以降。読込みの高速化は範囲外（依頼書 §2）。

**(b) genesis 2026-01-02 の追いつき**（149セッション）：1回目の朝の `seconds.load_inputs=0.29`、`seconds.morning_job=223.61`（同じ測定を別の回で行うと172〜225秒）。続く同じ朝の2回目（SKIPPED_CLAIMED）は `load_inputs=0.07`、`morning_job=0.85`。設計§10の試行（233秒）と同程度で、設計§10の閾値 `morning_job>60秒` は超える。追いつきは開始時の1回だけで、workflowの `timeout-minutes: 30` の内。

**(c) 通常の朝**（追いつきの翌営業日、D=2026-08-10）：`seconds.load_inputs=0.32`、`seconds.morning_job=3.15`、`seconds.outbox_load=0.03`、`outbox_files=5`。

研究のデータの範囲：`daily_adjclose.csv` のSPY・IEFは2026-08-11以降が空なので、その日以降を対象Dにした朝は `STALE`（`run_session_unconfirmed`）で止まる。入口の不具合ではなく研究データの範囲で、測定の通常の朝は2026-08-10までで行った。

## 9. 同時の実行（S4E-14）

子プロセス2・3・4個で各10ラウンド（計30ラウンド、90プロセス）、同じDの `morning --mode live` を、1つの共有リモートと偽のDiscordに対して同時に走らせた（最終コードで再実行）。

`{"done_sent": 30, "halt_posts": 30, "morning_posts": 30, "rounds": 30, "skipped": 30, "stopped": 59}`、負けた側の理由は `{"publication_stale": 59}`。

読み方：判定ありの投稿（`morning_posts`）は30ラウンドで30回（ラウンドごとにちょうど1回）、固定のsha256は各ラウンドで1つ、日の適用は1回。負けた側は `STOPPED`（`publication_stale`）になり、判定なしの `halt` の投稿が各ラウンド1回、または `SKIPPED` で、すべて終了0だった。concurrencyのグループが効かない場合の保険は成り立つ。

## 10. S4E-18：範囲試験と、ENDだけを固定した場合の手順

`tests/v2_run/test_s4e_09_scope.py`：START＝`9bdd421`、END＝None、REV＝`END or "HEAD"`、`FilesChanged`。§2の変更だけを許し、test_s4d_09・job.py・load.pyの差分をこの試験自身のハンクとして固定する。範囲の鎖は `…→ffa3700→9bdd421→（S4-E）` で通る。

手順（試験対象 `bb4c135` のクリーンクローン上の使い捨てworktreeで実行）：

```
19:END = "bb4c135ca1b3bda86666b77082c66e6a8b938fcd"   # frozen
--- (a) END frozen, no next open range
[scope_chain]
FAIL: test_an_open_range_that_is_not_last_is_rejected (test_sc_02_chain.ChainJudge.test_an_open_range_that_is_not_last_is_rejected)
FAIL: test_two_open_ranges_are_rejected (test_sc_02_chain.ChainJudge.test_two_open_ranges_are_rejected)
Ran 34 tests in 3.745s
FAILED (failures=2)
[s4e_09]
Ran 20 tests in 2.435s
OK
--- (b) END frozen and the next open range added
[scope_chain]
Ran 34 tests in 3.782s
OK
[s4e_09]
Ran 20 tests in 2.607s
OK
```

- (a) ENDだけを固定して、次の開いた範囲を置かない：`test_sc_02_chain` の鎖の試験2件（`test_an_open_range_that_is_not_last_is_rejected`、`test_two_open_ranges_are_rejected`）が失敗する。
- (b) ENDを固定し、次の段階の開いた範囲（START＝固定したコミット、END＝None）を足す：鎖の試験34件と本試験20件が通る。
- 次の段階は、`test_s4e_09_scope.py` の `END` を受領版のSHAにする1行と、自分の開いた範囲試験を足す。

## 11. 記録の例（印は入れていない。実際の出力）

### `dry` の `morning`

```
### v2_run
- command: morning
- mode: dry
- now_utc: 2026-07-24T22:40:00+00:00
- code_version: 0000000000000000000000000000000000000000
- python: 3.13.18
- git: 2.43.0
- provenance.calendar_sha256: eb41ea2ccd36a2ee9ebce0b5ac1bad12c37b2a6a8dfd54562257a3bd4f359800
- provenance.fetch_count: 4
- provenance.ledger_commit: 8b4a9510349327b4b4fe15b241c40026099f38e0
- provenance.market_commit: bcceb75e65f5813d8a7c0f55989d9c0ac189a8c6
- provenance.market_sha256: fe966cf5a54bf1afca3d72bc6bdb1e3b33c3a5eab137a40b6e3c1e0720e2095a
- provenance.market_through: 2026-07-24
- provenance.pinned_by: this
- run_outcome: DONE
- key: 2026-07-24-morning
- delivery: SENT
- send_status: SENT
- existing_status: None
- code: None
- consumed: 2026-07-24
- history_digest: 3ba3738cbaea
- seconds.load_inputs: 0.31
- seconds.morning_job: 0.34
- seconds.outbox_load: 0.04
- outbox_files: 9

#### text (dry: not sent)

```
【SOXL日次】対象D=2026-07-24
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-07-24 ／実行区分: 合図なし
データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2010-02-11〜2026-07-24、4137行、入力SHA256先頭12桁=fe966cf5a54b）
市場側（F&G以外の条件を含む判定）
  極端恐怖: 不成立（F&Gは25以上）
  通常買い: 不成立（F&Gは25以上30未満の帯にない）
  トレンド参加: 不成立（F&Gは30以上、市場側の条件が不成立）
F&G現在値（目視）: 40.7714（decision、observed_at=2026-07-24T22:05:00+00:00、対象D=2026-07-24）
市場状態: armed=確認済みtrue、連続数（確認済み観測）=3、前日normal_raw=確認済みfalse
プロファイル別（案U: 保有・原価・現金・余力は入力していません）
  条件が成立した場合の口座条件は、手元で確認してください。
P20の原価目安 b*=114.00（SOXL D終値136.81÷1.2、close_split_adjusted_not_dividend_adjusted、セント未満切り捨て）
  費用込み1株平均原価がこの値以下ならP20のD価格条件（含み益20%以上、手数料なし）を満たします。売却下限・指値・売却推奨ではありません。保有を入力していないため、本人のP20成立は未判定です。
  b*と原価の差が0.01未満の境界付近は、表示だけで断定せず n×D終値÷B−1≧0.20 を直接確認してください。
株数・金額は出しません。売却推奨・注文方式は出しません。
```
- exit_code: 0
```

### `live` の `morning`（偽のDiscordへ204）

```
### v2_run
- command: morning
- mode: live
- now_utc: 2026-07-24T22:40:00+00:00
- code_version: 0000000000000000000000000000000000000000
- python: 3.13.18
- git: 2.43.0
- provenance.calendar_sha256: eb41ea2ccd36a2ee9ebce0b5ac1bad12c37b2a6a8dfd54562257a3bd4f359800
- provenance.fetch_count: 4
- provenance.ledger_commit: 6174fd8c9c823d0cdf66ea731aaf77e5fd62d449
- provenance.market_commit: bcceb75e65f5813d8a7c0f55989d9c0ac189a8c6
- provenance.market_sha256: fe966cf5a54bf1afca3d72bc6bdb1e3b33c3a5eab137a40b6e3c1e0720e2095a
- provenance.market_through: 2026-07-24
- provenance.pinned_by: this
- run_outcome: DONE
- key: 2026-07-24-morning
- delivery: SENT
- send_status: SENT
- existing_status: None
- code: None
- consumed: 2026-07-24
- history_digest: 3ba3738cbaea
- seconds.load_inputs: 0.30
- seconds.morning_job: 0.37
- seconds.outbox_load: 0.04
- outbox_files: 9
- exit_code: 0
```

### `status`

```
### v2_run
- command: status
- mode: live
- now_utc: 2026-07-24T22:40:00+00:00
- code_version: 0000000000000000000000000000000000000000
- python: 3.13.18
- git: 2.43.0
- 2026-07-24-morning: SENT 2026-07-24T22:40:00+00:00
- 2026-07-24-halt: NONE 
- 2026-07-24-error: NONE 
- exit_code: 0
```

### `check-source`（先頭）

```
### v2_run
- command: check-source
- mode: live
- now_utc: 2026-07-24T22:40:00+00:00
- code_version: 0000000000000000000000000000000000000000
- python: 3.13.18
- git: 2.43.0
- target_d: 2026-07-24
- pin_through: 2026-07-24
- SOXX.meta_symbol_ok: True
- SOXX.shape: ok
- SOXX.rows: 4137
- SOXX.first: 2010-02-11
- SOXX.last: 2026-07-24
- SOXX.times_ny: 09:30×4137
- SOXX.duplicate_dates: -
- SOXX.target_rows: 1
- SOXX.table_days_missing_or_null: 0
- SOXX.table_days_missing_examples: -
- SOXX.null_rows: 0
- SOXX.pre2026_only_in_response: 0
- SOXX.pre2026_only_in_research: 0
- SOXX.pin_last_close_changed: False
- SOXX.pin_older_close_changed: 0
- SOXX.pin_adj_return_maxdiff: 0.00e+00
- SPY.meta_symbol_ok: True
...（SPY・IEF・SOXLも同じ形。全体は105行）
```

どの場面でも、記録にパス・URL・Webhookの値・例外の文字列・gitの出力・応答の本文は出ない（S4E-15、`SECRETMARK_`・`SECRETTOKEN_`・`SECRETBODY_`・`http` の検査）。

## 12. ひな形と手順書の要点

- `docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.yml`（103行）：cron は `40 22 * * 1-5` と `40 23 * * 1-5`（日本時間 火〜土 7:40・8:40）。`permissions: contents: write` だけ、`timeout-minutes: 30`、`python3 -E -B -m v2_run`。書くコマンドの `concurrency` は `v2-writer`・`cancel-in-progress: false`・`queue: max`、`status`・`check-source` は別グループ（`v2-read-<run_id>`）。`workflow_dispatch` に `mode`（`auto`・`dry`・`live`、既定 `auto`）、モードは1行の `case` で決め、`v2_run` へ `--mode "$MODE"` だけを渡す。入力は `env` 経由のみ、`secrets.` の行なし（E-0〜E-3）、`actions/checkout@` の後は40桁の仮の値（E-2で公式のコミットSHAに書き換える）。TP-01の注記入り。置くだけで有効にしない（`.github/` へは写していない）。
- `docs/ops/V2_PRIVATE_RUN_GUIDE.md`（179行）：毎朝の流れ、台帳の書き方（7:40がF&G記録の締切）、通知の読み方、手動の操作、再送、DAMAGED、止まり続ける理由コード、休場日の表、版の更新、保守、巻戻しの確認（ブランチ保護が使えない場合）、開始の境界（試運転と本番で同じ）、取得の失敗の理由、E-1〜E-5の段階ごとの手順と確かめること（E-3の合否12項目）。Webhookの値・ローカルのパスは含まない。

## 13. 保存と保護ref

- 保護ref113件：開始前に照合して一致。push後の照合は、pushの後にこの節へ追記せず、報告で示す（最後の差分を結果文書1本だけに保つため）。
- pushしたのは `feat/v2-run-s4e-20261105` だけ。

## 14. 未実施の事項

- E-1以降（非公開リポジトリの作成、workflowの設置、Webhookの登録、実送信、本番の有効化）は承認されておらず、行っていない。
- 実際の取得先（Yahoo）・実際のDiscord・GitHubの実リモート・Actions・非公開リポジトリへの接続は一切していない。取得もDiscordも偽の `urlopen` だけ。`queue: max` をGitHubが受け付けるか、checkoutの資格情報でのpush、ブランチ保護の有無はE-2で確かめる。
- 実Windows（新規N、S4-D 130、S4-C 118、S4-B 131、範囲の鎖34）、ユーザーPC（Python 3.10.6）、物理電源断は未実施。Linuxのgit 2.43.0とPython 3.10〜3.13だけ。
- 欠陥注入の03・13・13bは狙いと違う試験が先に落ちた（§6）。
- `test_s4e_01_args.py` の1行目の説明文は `S4E-02 (arguments)` のままで、引数の試験であることとずれている（挙動に影響なし。試験対象の固定を保つため直していない）。
- 研究データのSPY・IEFが2026-08-11以降空であること（§8）。
