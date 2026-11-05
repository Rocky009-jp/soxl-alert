# V2 S4-C gitの保存先（履歴とoutboxをgitの参照に置く）限定実装の結果

作成日：2026-11-05（日本時間）。担当：Claude Sonnet 5.5（セッション設定 `claude-sonnet-5-5[1m]`、effort `high`）。gitの版は 2.43.0。
対象：`Rocky009-jp/soxl-alert`、新ブランチ `feat/v2-git-store-s4c-20261105`。PR・マージ・Actions・本番・実際の送信・S4-D以降はしていない。GitHubへのpushは新しい実装ブランチ1本だけで、状態の保存先（`v2-state`・`v2-outbox`）としてGitHubは使っていない。試験のリモートはすべて一時ディレクトリのbareリポジトリである。

## 0. 要約

- S4-Cの限定実装は**完了**した。新パッケージ `v2_git_store`（4ファイル628行）と、新しい試験 `tests/v2_git_store`（10本の試験ファイルと2本の補助、新規118件）を足し、既存の1ファイル（`tests/v2_notify/test_s4b_09_scope.py`）の**1行だけ**（`END`を `6cab050` に固定）を変えた。受領済みのパッケージ・補助・資料は変えていない。
- 試験対象 `13be0d0903df82d8c2cdd8196071ba957b2eb711` で、完全な履歴の別クリーンクローン（`core.autocrlf=false`）の Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版とも、**既存17スイート2,480件＋新規118件＝2,598件が全件合格**（失敗0・エラー0・新規のskip 0。既存のskip 4件はS2のWindows専用）。18スイートの終了コードはすべて0。
- 欠陥注入は依頼書の20項目に追加分を加えた**42件**（依頼の項目には枝番の変種を含む）。結果は検出41・等価1・未検出0・準備失敗0（§8）。
- 子プロセスの同時実行（2〜4個、判定の通知・同じ再送id・別の再送id）は、毎回、判定ありの通知は1通まで・判定なしは1通まで・履歴のAPPLYの重複0（§9）。S4C-03(g)の3つ同時のpushは、100回とも勝ち1・負け2（§9.2）。
- 設計§15のR-01〜R-03は§3.4のとおり扱った。次の段階の模擬（S4C-18）は期待どおり（§6）。
- **未実施**：実Windows、物理電源断、ユーザーPC、GitHubのリモートを使った確認、ネットワークの遅延・認証が絡む本物のリモート（§13）。
- 設計・依頼書の矛盾や範囲外の変更は**見つからなかった**。止めた箇所はない。気づいた点が2つある：同じ時間に別の再送idが3つ走ると1つが`CLAIM_FAILED`になる（安全側、§9.3）、`v2_notify.values`の定数を`outbox.py`が使う（許可されたimport、§3.5）。

## 1. 固定した資料と起点

| 項目 | 値 |
|---|---|
| 資料コミット（docs/v2-git-store-s4c-20261105、D-1〜D-9の採用記録） | `206054509e621ec5553ee389c3912c7112cc266a` |
| 設計 `docs/specs/V2_GIT_STORE_S4C_DESIGN_DRAFT.md`（blob） | `40a023024d70c1318aa64f00d71adf2653096e68` |
| 依頼書 `docs/tasks/V2_GIT_STORE_S4C_LIMITED_IMPLEMENTATION_REQUEST.md`（blob） | `a50276dd8a2a5101613455577697b171cd0f6074` |
| 試行差分 `docs/specs/V2_GIT_STORE_S4C_TRIAL_20261105.diff`（blob） | `6682874035b748f6ca0105d7de431b01f2586ccf`（sha256 `f936d8137365b20285994e77003827fccbb0a04f0f9cda9cebc1f774dd15a015` の写しと照合。参考にしただけで適用していない） |
| コードの開始点 | `6cab0506c408d194c63b656713e4a0a7d62c3ba1`（S4-Bの保存最終・受領版。ブランチはここから切った） |
| **試験対象（コード・試験の最終）** | `13be0d0903df82d8c2cdd8196071ba957b2eb711` |
| 最終（この結果文書の追加） | この文書だけを足した次のコミット。SHAはpushの報告に書く |

試験対象の前の `193d2404ed7008800609f05a758ab0eb7043f586`（116件）との差は、`tests/v2_git_store/test_s4c_03_history.py`の試験2件だけで、ランタイムは同一である。競合のレポート（§9）・次の段階の模擬（§6）・欠陥注入（§8）の本体は `193d240` で実行し、追加5・6だけ `13be0d0` で再実行した。全スイート（§7）は `13be0d0` で4版とも実行した。

保護参照は、依頼書§7の99参照に、資料ブランチ（`2060545`）・設計レビュー（`55e770a`）・再レビュー（`3d2b79a`）の3本を加えた**102参照**を、開始時・試験後・push前・push後に完全なSHAで照合した（`refcheck.py`、`refs_protected102.txt`、結果は§12）。

## 2. 変更したもの

| 場所 | 内容 |
|---|---|
| `v2_git_store/__init__.py`（11行） | 公開名 |
| `v2_git_store/git.py`（225行） | `Git`：gitを起動する唯一の場所。配管コマンド（hash-object、mktree -z、commit-tree）でコミットを作り、取得は`refs/v2remote/<ref>`だけへ、リモートを変えるのは`git push --porcelain <remote> <sha>:refs/heads/<ref>`の1か所だけ。判定はOK・REJECTED・UNCERTAIN。環境の写しから`GIT_`の変数を除く。gitの出力はこのファイルの外に出ない。`GitError`の引数は固定の語だけ |
| `v2_git_store/history.py`（169行） | `GitHistoryStore`：C-3の保存先と同じ`read`・`initialize`・`publish`・`reconcile`・同じ結果型と符号。比較交換は取得したばかりのバイトに対するC-2の`check_publication`と、親を取得した先頭にした早送りの1コミットのpush。成否不明の判定は内容だけ（`reconcile_publication`） |
| `v2_git_store/outbox.py`（223行） | `GitOutbox`：`LocalOutbox`の子クラス。公開メソッド（`load`・`resend_ids`・`claim`・`record`・`initialize`）だけを上書きし、基底の`_`で始まる名前は使わない。写しのディレクトリは自分で`mkdtemp`し、使う前に必ずリモートから作り直す。名前を作る権利は、その1ファイルだけを足すコミットのpushで決める（最大4回） |
| `tests/v2_notify/test_s4b_09_scope.py` | 18行目 `END` の**1行だけ**（下の差分） |
| `tests/v2_git_store/`（新規12ファイル） | `s4c_helpers.py`、`s4c_worker.py`、`test_s4c_01〜10_*.py`（`__init__.py`は作っていない） |
| `docs/implementation/V2_GIT_STORE_S4C_RESULT.md` | この文書（別のコミット） |

ランタイムの全文は `v2_git_store/` の4ファイル（628行）で、ブランチの試験対象コミットにある。

`test_s4b_09_scope.py` の差分の全文（`git diff --unified=0 6cab050 13be0d0903df82d8c2cdd8196071ba957b2eb711 -- tests/v2_notify/test_s4b_09_scope.py`）：

```
@@ -18 +18 @@
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "6cab0506c408d194c63b656713e4a0a7d62c3ba1"   # accepted (receipt 983ced8); frozen when S4-C began
```

S4-Bの試験（131件）はこの1行の固定のあとも同じ件数で通る。新しい `test_s4c_09_scope.py` がこのhunkをS4-Cの差分として固定している。

## 3. ランタイムの規則（設計のとおり）

### 3.1 参照とファイル

`v2-state`（`history.json`だけ）と`v2-outbox`（`v2-outbox-init`の印のファイルと、S4-Bと同じ名前の意図・結果のファイル）の2参照。`v2-ledger`（S4-D）には触れていない。作業場所の`HEAD`・`refs/heads/*`・インデックス・作業ツリーは変えない（S4C-04の試験）。

### 3.2 push

`Git.push`は`git push --porcelain <remote> <sha>:refs/heads/<ref>`の1か所の配列だけで、`--force`・`+`・`--quiet`・`--delete`・`--mirror`を使わない。判定は参照の行が1つだけあるときの記号で決める：`*`・`=`・空白でかつ終了コード0→OK、`!`→REJECTED、それ以外（時間切れ、行が無い、記号がOKで終了コードが0でない）→UNCERTAIN。

### 3.3 履歴

`publish`：取得→`history.json`のバイト→現在の履歴の検査→`check_publication`→コミット→push。REJECTEDのあと取得し直し、先頭が動いていれば`publication_stale`、動いていなければ`store_io_error`（規則・フック・権限）。UNCERTAINは`store_commit_uncertain`で、`reconcile`が取得し直して内容だけで判定する（`reconcile_publication`。自分のコミットのSHAを覚えない）。

### 3.4 設計§15のR-01〜R-03の扱い

- **R-01**：S4C-03(g)の試験の期待に拒否の文言を入れていない（期待はREJECTED、`GitHistoryStore`では`publication_stale`だけ）。各文言の回数は§9.2に記録した：100回の3つ同時のpushで、負けた200件は**すべて** `[remote rejected] (failed to update ref)`。
- **R-02**：`GitOutbox.initialize()`のpushがREJECTEDのときは取得し直し、参照ができていれば2回目と同じく`already_initialized`で拒み、無ければ`outbox_io_error`にした。UNCERTAINのときは参照ができていて印のファイルの内容が合っていれば成功とする。S4C-12(b)に「2つの初期化が同時に走ると1つだけが作る」を足した（`test_b_two_initializations_at_the_same_time_make_it_once`）。
- **R-03**：設計§14のP-02の要約のずれ（同時にpushすると同じSHAでも片方が参照のロックで負けて`publication_stale`になる、どちらも安全側）は、実装とS4C-03(g)・S4C-14の試験の結果と合っている。設計文書は変えない。

### 3.5 試行の下書き（設計§10）との違い

試行の下書きは使わず、設計の文面に従って書き直した（試行は適用されない下書きと設計に書かれている）。主な違い：

- 環境の写しから`GIT_`の変数を除く処理と、引数の検査（ref・remote・timeout・clock・親ディレクトリ）を入れた。
- 写しのディレクトリは呼び出し側から受け取らず、`GitOutbox`が親の下に`mkdtemp`する（設計T-6）。
- 成否不明の判定は内容だけにし、自分のコミットのSHAを覚えない。ファイル名は「写しに増えたファイル」で求め、基底の`_`で始まる名前を使わない（設計T-5）。
- N-01（足すコミットは親の木に同じ名前があれば作らない）と、N-02（拒否の後に取得し直して先頭が動いたかで読み分ける）を入れた。
- `load`は取得の失敗で例外を出さず`DAMAGED`を返す（T-2）。作成は参照が無いoutboxを空と読まない。
- 時計は注入。コミットの日時は注入した時計の値で、日付はUNIX秒とUTCオフセットで渡す（`datetime`をimportしない）。

`outbox.py`は`v2_notify.values`の`date_text`・`request_id_text`・`OUTBOX_IO_ERROR`・`ARGS_INVALID`をimportしている（許可された`v2_notify`のimport）。

## 4. 受入とテスト名の対応

| ID | 試験ファイル（クラス） | 件数 |
|---|---|---|
| S4C-01 回帰 | 既存17スイート（§7） | 2,480 |
| S4C-02 引数 | `test_s4c_01_args.py`（Args） | 8 |
| S4C-03 push、S4C-04 取得 | `test_s4c_02_git.py`（Push、Fetch、Start）。(g)は`test_g_three_pushes_…` | 16 |
| S4C-05 初期化と読込み、S4C-06 C-3との一致、S4C-07 先を越された保存、S4C-08 成否不明 | `test_s4c_03_history.py`（InitializeAndRead、SameAsC3、Beaten、Uncertain） | 21 |
| S4C-09 リモートに届かない | `test_s4c_04_unreachable.py`（Outage） | 4 |
| S4C-10 別のクローンでも1通、S4C-11 作成の決め方、S4C-12 初期化と壊れ、S4C-13 手動の再送 | `test_s4c_05_outbox.py`（SecondClone、Deciding、Initialization、Resend） | 26 |
| S4C-14 同時の実行 | `test_s4c_06_processes.py`（Race） | 4 |
| S4C-15 コミットの形 | `test_s4c_07_commits.py`（Shape） | 5 |
| S4C-16 静的な範囲 | `test_s4c_08_static.py`（Runtime） | 13 |
| S4C-17 機密 | `test_s4c_10_secrets.py`（Scenes） | 1 |
| S4C-18 範囲試験 | `test_s4c_09_scope.py`（FilesChanged、TestFiles） | 20 |
| 合計（新規） | | 118 |

## 5. S4C-09 の場面の一覧

`test_s4c_04_unreachable.py`は、1回の`morning_job`の中のネットワークのコマンド（取得とpush）を数え、k番目の直前にリモートのディレクトリを**改名**する（もう1つの試験は削除）。正常な朝のネットワークのコマンドは8つ（fetch、fetch、push、fetch、fetch、push、fetch、push）。kごとの結果は次のとおり（試験の期待値）：

| k | 止めた段 | run_outcome／code | 通知の種類 | delivery | 送信 |
|---|---|---|---|---|---|
| 1 | 履歴の読込み（取得） | STOPPED／`store_io_error` | halt | SKIPPED_JUDGMENT_EXISTS | 0 |
| 2 | 公開の取得 | STOPPED／`store_io_error` | halt | SKIPPED_JUDGMENT_EXISTS | 0 |
| 3 | 公開のpush（reconcileはできない） | STOPPED／`store_io_error` | halt | SKIPPED_JUDGMENT_EXISTS | 0 |
| 4 | outboxの読込み | DONE | morning | SKIPPED_CLAIMED（DAMAGED） | 0 |
| 5 | 意図を作る前の取得 | DONE | morning | CLAIM_FAILED | 0 |
| 6 | 意図のpush | DONE | morning | CLAIM_FAILED | 0 |
| 7 | 結果を足す前の取得 | DONE | morning | RESULT_NOT_RECORDED | 1 |
| 8 | 結果のpush | DONE | morning | RESULT_NOT_RECORDED | 1 |

（試験は「改名」と「削除」の両方でkごとに確かめ、改名のときはリモートを戻して、そこまでの段が残したものだけがあること――履歴が保存済みなのはk≥4、意図はk≥7――と、二重に送らないことも確かめる。）

（期待値の全文は `test_every_step_in_turn`。ほかに、`test_whatever_the_step_nothing_is_sent_twice_when_the_morning_is_run_again`、`test_the_outbox_state_and_the_initializations_fail_cleanly_when_the_remote_is_gone`、正常な朝のコマンド数の試験がある。どの場面でも、例外が漏れず、報告・文面・例外の引数・reprに印（`SECRETMARK_`）が出ず、送信は多くて1回、送るのは意図がリモートにあるときだけである。）

## 6. S4C-18 の手順と結果

新しい範囲試験 `test_s4c_09_scope.py`：START＝`6cab050`、END＝None、REV＝END or "HEAD"。許す変更は`v2_git_store/`の4ファイル、`tests/v2_git_store/`の新規ファイル、`tests/v2_notify/test_s4b_09_scope.py`のENDの1行（hunkをそのまま固定）、結果文書1本だけ。既存のパッケージ・補助・資料の木は開始点と同一（300ファイル以上の照合）であること、試験ファイルのimport・時計・ネットワーク・環境変数の使用が補助だけに限られることも確かめる。

次の段階の模擬（`next_stage_sim.sh`、一時のworktree、何もpushしない）：

```
[A] tested commit 193d2404ed7008800609f05a758ab0eb7043f586
  v2_scope_chain: Ran 34 tests in 5.697s | OK
  v2_history_maintain: Ran 31 tests in 4.538s | OK
  v2_daily_run: Ran 19 tests in 2.940s | OK
  v2_notify: Ran 19 tests in 3.174s | OK
  v2_git_store: Ran 20 tests in 3.924s | OK
 1 file changed, 1 insertion(+), 1 deletion(-)
[B] END frozen, no open range (expected: test_sc_02 chain test fails)
  v2_scope_chain: Ran 34 tests in 6.545s | FAILED (failures=2)
  v2_history_maintain: Ran 31 tests in 4.334s | OK
  v2_daily_run: Ran 19 tests in 3.112s | OK
  v2_notify: Ran 19 tests in 3.463s | OK
  v2_git_store: Ran 20 tests in 4.044s | OK
[C] END frozen + minimal open range of the next stage
  v2_scope_chain: Ran 34 tests in 5.796s | OK
  v2_history_maintain: Ran 31 tests in 4.134s | OK
  v2_daily_run: Ran 19 tests in 2.930s | OK
  v2_notify: Ran 19 tests in 3.463s | OK
  v2_git_store: Ran 20 tests in 3.833s | OK
```

読み方：[A] 試験対象のままでは範囲の鎖は通る。[B] S4-Cの`END`だけを固定して開いた範囲を外すと、鎖の試験が失敗する（期待どおり、2件）。[C] 次の段階の開いた範囲試験を加えると、すべて通る。つまり、次の段階は`END`の1行の固定と新しい開いた範囲試験を足せばよい。

## 7. 全スイートの件数・失敗・error・skip・終了コード

試験対象 `13be0d0903df82d8c2cdd8196071ba957b2eb711` を、別クリーンクローン（`git clone`したのち`core.autocrlf=false`でcheckout、`PYTHONDONTWRITEBYTECODE=1`、`-W error::ResourceWarning`）で、`runall.sh`（18スイート）を4つの版で実行した。**4版とも18スイートのrc=0、失敗0、エラー0**（`v2_persistence_local`のskip 4は既存のWindows専用）。

| スイート | 件数 | 結果（Python 3.13.18） |
|---|---|---|
| v2_core | 197 | rc=0、OK |
| v2_persistence | 170 | rc=0、OK |
| v2_persistence_local | 113 | rc=0、OK (skipped=4) |
| v2_recovery | 176 | rc=0、OK |
| v2_history | 230 | rc=0、OK |
| v2_history_ops | 173 | rc=0、OK |
| v2_history_restart | 109 | rc=0、OK |
| v2_history_restore | 165 | rc=0、OK |
| v2_history_diagnose | 131 | rc=0、OK |
| v2_history_adopt | 170 | rc=0、OK |
| v2_scope_chain | 34 | rc=0、OK |
| v2_history_consume | 112 | rc=0、OK |
| v2_history_publish | 150 | rc=0、OK |
| v2_history_local | 139 | rc=0、OK |
| v2_history_maintain | 184 | rc=0、OK |
| v2_daily_run | 96 | rc=0、OK |
| v2_notify | 131 | rc=0、OK |
| v2_git_store | 118 | rc=0、OK |

| 版 | 完全な版 | 件数 | 終了コード |
|---|---|---|---|
| 3.10 | 3.10.20 | 2,598 | 0 |
| 3.11 | 3.11.18 | 2,598 | 0 |
| 3.12 | 3.12.3 | 2,598 | 0 |
| 3.13 | 3.13.18 | 2,598 | 0 |

既存17スイートの内訳は 2,480件（S4-Aまでの16スイート2,349件＋S4-B 131件）。新規は118件。

## 8. 欠陥注入

依頼書§5の20項目（枝番の変種を含む）に追加を加えた42件を、1件ずつ使い捨てのworktreeで壊して、新規スイート（範囲試験09は変更したファイルの一覧を見るので数えない）の失敗の有無で分けた。`mutate.py`。最初の試験対象（`193d240`、116件）では追加5・追加6が未検出だったので、試験を2件足し（`13be0d0`、118件）、この2件だけを再実行して検出された（表は再実行の結果。足した試験は`test_a_creation_that_another_clone_won_in_the_meantime_is_already_initialized`と`test_a_file_that_is_not_a_regular_file_is_not_the_history`）。それ以外は最初の試験対象での結果である（足した試験は試験だけで、ランタイムは同じ）。

| ID | 内容 | 結果 | 失敗した件数 | 最初の失敗した試験 |
|---|---|---|---|---|
| 依頼1 | push is forced (--force) | DETECTED | 16 | test_no_command_of_a_whole_morning_changes_a_branch_the_index_or_the_work_tree |
| 依頼1b | push is forced (+ in the refspec) | DETECTED | 13 | test_no_command_of_a_whole_morning_changes_a_branch_the_index_or_the_work_tree |
| 依頼2 | push is quiet (--quiet) | DETECTED | 63 | test_no_command_of_a_whole_morning_changes_a_branch_the_index_or_the_work_tree |
| 依頼3 | UNCERTAIN is treated as OK in publish | DETECTED | 5 | test_b_it_did_not_arrive |
| 依頼4 | REJECTED is store_commit_uncertain in publish | DETECTED | 5 | test_d_a_pre_receive_hook_refusal_is_rejected_and_the_history_store_reads_it_as_a_rule_not_a_race |
| 依頼5 | a failed fetch is 'no ref' | DETECTED | 4 | test_a_failed_fetch_is_none_only_when_ls_remote_says_there_is_no_ref |
| 依頼6 | a refusal after a moved head has a new code | DETECTED | 4 | test_the_morning_job_says_that_another_run_may_have_been_at_work_and_the_judgment_comes_later |
| 依頼7 | reconcile uses the bytes read before (no fetch) | DETECTED | 7 | test_a_publication_adds_one_day_and_gives_the_result_of_the_c3_store |
| 依頼8 | publish makes the commit without check_publication | DETECTED | 39 | test_the_morning_job_says_that_another_run_may_have_been_at_work_and_the_judgment_comes_later |
| 依頼9 | the tree of a new commit drops the other files of the parent | DETECTED | 21 | test_c_an_uncertain_push_that_did_arrive_is_our_own_claim_and_is_sent_once |
| 依頼10 | fetch goes to refs/heads/<ref> | DETECTED | 4 | test_a_fetch_changes_nothing_in_the_work_directory |
| 依頼11 | GitOutbox.load raises on a failure of the remote | DETECTED | 6 | test_every_step_in_turn |
| 依頼12 | a refused create is 'taken by another' without reading the remote again | DETECTED | 4 | test_d_a_pre_receive_hook_refusal_is_rejected_and_the_history_store_reads_it_as_a_rule_not_a_race |
| 依頼13 | an uncertain create is 'ours' without comparing the bytes on the remote | DETECTED | 5 | test_a_clock_that_does_not_return_a_time_makes_nothing_and_pushes_nothing |
| 依頼14 | a create is tried once only | DETECTED | 4 | test_a_another_key_was_pushed_first_the_claim_is_made_again_and_succeeds |
| 依頼15 | the mirror keeps the files of the earlier mirror | DETECTED | 11 | test_a_clock_that_does_not_return_a_time_makes_nothing_and_pushes_nothing |
| 依頼16 | a missing ref is an empty outbox | DETECTED | 1 | test_a_no_ref_is_a_damaged_outbox_that_sends_nothing_and_makes_nothing |
| 依頼17 | the error of git carries the standard error | DETECTED | 1 | test_the_arguments_of_every_error_of_this_package_are_fixed_words |
| 依頼18 | the GIT_ variables of the parent are kept | DETECTED | 3 | test_a_git_variable_of_the_parent_cannot_send_git_to_another_repository |
| 依頼19 | the add commit of the outbox replaces a name of the parent's tree | DETECTED | 1 | test_g_a_mirror_that_loses_a_file_does_not_let_the_same_key_be_sent_twice_nor_replace_the_intent |
| 依頼20 | a refusal by a rule (head not moved) is publication_stale | DETECTED | 1 | test_d_a_pre_receive_hook_refusal_is_rejected_and_the_history_store_reads_it_as_a_rule_not_a_race |
| 依頼20b | any refusal is store_io_error (a lost race too) | DETECTED | 4 | test_the_morning_job_says_that_another_run_may_have_been_at_work_and_the_judgment_comes_later |
| 追加1 | extra: the flag ! is UNCERTAIN | DETECTED | 11 | test_b_not_a_fast_forward_is_rejected_and_the_remote_does_not_change |
| 追加2 | extra: the exit code of push is not looked at | DETECTED | 1 | test_f_fake_answers_of_git |
| 追加3 | extra: a timed-out push is REJECTED | DETECTED | 10 | test_b_an_uncertain_initialization_that_arrived_is_done_and_one_that_did_not_is_an_error |
| 追加4 | extra: initialize does not look for an existing ref (history) | DETECTED | 2 | test_a_second_initialization_is_refused_and_changes_nothing |
| 追加5 | extra: a refused create of the history on a ref that exists is store_io_error（試験を足して再実行） | DETECTED | 1 | test_a_creation_that_another_clone_won_in_the_meantime_is_already_initialized |
| 追加6 | extra: a file mode is not looked at when a blob is read（試験を足して再実行） | DETECTED | 1 | test_a_file_that_is_not_a_regular_file_is_not_the_history |
| 追加7 | extra: every failed fetch is 'no ref' | DETECTED | 4 | test_a_failed_fetch_is_none_only_when_ls_remote_says_there_is_no_ref |
| 追加8 | extra: the entries of the tree are not checked in the mirror | DETECTED | 1 | test_c_entries_that_are_not_plain_files_make_the_whole_outbox_unreadable |
| 追加9 | extra: push without --porcelain | DETECTED | 65 | test_no_command_of_a_whole_morning_changes_a_branch_the_index_or_the_work_tree |
| 追加10 | extra: GIT_TERMINAL_PROMPT is not set | DETECTED | 1 | test_the_command_the_settings_and_the_environment |
| 追加11 | extra: the commit gets the real time (the given time is not used) | DETECTED | 1 | test_author_committer_and_date_come_from_the_injected_clock_one_call_per_commit |
| 追加12 | extra: load does not read the remote again | DETECTED | 12 | test_every_step_in_turn |
| 追加13 | extra: resend_ids does not read the remote again | DETECTED | 3 | test_the_outbox_state_and_the_initializations_fail_cleanly_when_the_remote_is_gone |
| 追加14 | extra: initialize of the outbox on an existing ref returns quietly | DETECTED | 1 | test_b_a_second_initialization_is_refused |
| 追加15 | extra: the repr of Git shows the work directory | DETECTED | 1 | test_a_good_call_is_not_refused_and_the_reprs_show_nothing |
| 追加16 | extra: a broken current history file is not reported first | DETECTED | 1 | test_a_history_json_that_is_not_a_history_is_reported_as_the_c3_store_reports_it_and_nothing_is_pushed |
| 追加17 | extra: autocrlf is not switched off | DETECTED | 2 | test_the_command_the_settings_and_the_environment |
| 追加18 | extra: a layout without history.json is read as no history | DETECTED | 1 | test_a_ref_without_history_json_is_a_layout_we_do_not_know |
| 追加19 | extra: a name that is in the remote but not in the mirror is still sent as ours | DETECTED | 1 | test_g_a_mirror_that_loses_a_file_does_not_let_the_same_key_be_sent_twice_nor_replace_the_intent |
| 追加20 | extra: an error of the mirror is not raised (the claim is still sent) | EQUIVALENT | 0 |  |

- **追加20**（extra: an error of the mirror is not raised (the claim is still sent)）：等価（実際には起こらない防御）。`claim`・`record`が真を返すときは基底の作成が必ず1ファイルだけ足すので、`len(added) != 1`は到達しない。到達しない分岐の検査なので、試験では壊せない

## 9. 同時の実行（S4C-03(g)、S4C-14）

### 9.1 `morning_job` と再送（`race_report.py`、各Nで24回）

子プロセスごとに別のクローン、1つのbareリポジトリ、ファイルの合図で同時に開始。各ラウンドで、判定ありの通知は1通まで、判定なしは1通まで、履歴の同じDのAPPLYは1つだけ、判定なしの文面に「同時の実行」の注記、のあとに1回の健全な実行で判定がちょうど1通に揃うことを確かめた。

```
race rounds: 4 tests run, failures=0, errors=0 (rounds per N for the job: 24)
morning_job: (shifted clocks?, N, sorted notice kinds, sorted (run_outcome, delivery) of the children) -> count
   24 x shifted=False N=2 sends=('halt', 'morning') children=(('DONE', 'SENT'), ('STOPPED', 'SENT'))
   24 x shifted=True N=2 sends=('halt', 'morning') children=(('DONE', 'SENT'), ('STOPPED', 'SENT'))
   24 x shifted=True N=3 sends=('halt', 'morning') children=(('DONE', 'SENT'), ('STOPPED', 'SENT'), ('STOPPED', 'SKIPPED_CLAIMED'))
   24 x shifted=True N=4 sends=('halt', 'morning') children=(('DONE', 'SENT'), ('STOPPED', 'SENT'), ('STOPPED', 'SKIPPED_CLAIMED'), ('STOPPED', 'SKIPPED_CLAIMED'))
resend: (kind of ids, N, texts sent, sorted deliveries) -> count
   12 x different_ids N=3 sends=2 deliveries=('CLAIM_FAILED', 'SENT', 'SENT')
   12 x same_id N=2 sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED')
   12 x same_id N=3 sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED')
   12 x same_id N=4 sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED')
rc=0
```

### 9.2 S4C-03(g)：3つの同時のpushの文言（`wording_report.py`、100回）

```
rounds=100 tests=1 failures=0 errors=0
verdicts of the 300 pushes: {'OK': 100, 'REJECTED': 200}
  200 x [remote rejected] (failed to update ref)
rc=0
```

R-01のとおり、試験は文言を期待していない。勝ち1・負け2はどの回も変わらなかった。

### 9.3 気づいた点

同じ時間に別の再送idを3つ走らせると、**毎回1つが`CLAIM_FAILED`**（4回の試行を使い切り、送らない）になった。3つ同時では、一番遅い子が、自分の作り直しの間に他の2つが意図と結果の計4つを先に足してしまう。安全側（二重に送らない）で、依頼書S4C-11(e)の規則どおりである。同じidを同時に走らせた場合は、毎回1通で、残りは`SKIPPED_CLAIMED`。

## 10. リモートのコミットの例

一時のローカルbareリポジトリで、初期化・3日の追いつき・1回の通知を作った後。パスは`<remote>`と伏せた。

```
job: run_outcome=DONE delivery=SENT exit_code=0
== refs/heads/v2-state  (git log --reverse --format='%h %p | %an <%ae> | %ad | %s' --date=raw)
3f9bf5d - | v2-runner <runner@invalid> | 1793849696 +0900 | v2 history c52f1a665e35
b7f4fb2 3f9bf5d | v2-runner <runner@invalid> | 1793849696 +0900 | v2 history b900f84f7d8a
8744cd1 b7f4fb2 | v2-runner <runner@invalid> | 1793849696 +0900 | v2 history 297e4d01c49c
6965600 8744cd1 | v2-runner <runner@invalid> | 1793849696 +0900 | v2 history ce55788728c8
-- git ls-tree refs/heads/v2-state
100644 blob fe129859ece14b37a2a896f9250bdbbaa0b84df0  history.json
== refs/heads/v2-outbox  (git log --reverse --format='%h %p | %an <%ae> | %ad | %s' --date=raw)
94de828 - | v2-runner <runner@invalid> | 1793849696 +0900 | v2 outbox init
3461255 94de828 | v2-runner <runner@invalid> | 1793849696 +0900 | v2 outbox 2026-03-05-morning.claim.json
f058491 3461255 | v2-runner <runner@invalid> | 1793849696 +0900 | v2 outbox 2026-03-05-morning.result.json
-- git ls-tree refs/heads/v2-outbox
100644 blob 0ada2996e8fb60cdb55d50d3e2b6693cff2fb11d  2026-03-05-morning.claim.json
100644 blob 6f7a935a0e0385de6c2e5b6409b446dbc78b2f5a  2026-03-05-morning.result.json
100644 blob b9fc9afd6a2d32e6c12f0dc5c048fdd31b2129e4  v2-outbox-init
== refs of the remote (names only; the path is <remote>)
refs/heads/v2-outbox
refs/heads/v2-state
```

## 11. 試験を作る途中で直したこと

- push以外の呼出しに「`--quiet`を付けない」検査を当てて失敗した → 検査をpushだけに限った（取得は`--quiet`でよい）。
- 静的検査で、`GitError`の引数にパラメータ化した値（`check_dir`のfield、`phase`など）があった → 固定の語のリテラルに置き換え、`is_absolute_dir`を足した。
- `datetime`をimportしていたため、許可されたimportの一覧から外れた → 日付は`utcoffset`・`timestamp`を持つ値として扱う形にした。
- `tests`の差分の確認で`tests/v2_git_store`を除外し忘れていた、試験ファイルが`os.environ`を直接読んでいた → 範囲試験の除外を直し、PATHは補助の定数を使う形にした。
- `__pycache__`が1度できた → `git add`の前に消した（試験対象には含まれない）。

## 12. 保護参照の照合

保護参照102本（依頼書§7の99本＋資料ブランチ `2060545`・レビュー `55e770a`・再レビュー `3d2b79a`）を、`refcheck.py` で `git ls-remote origin` と完全なSHAで照合した（`refs_protected102.txt`）。

| 時点 | 結果 |
|---|---|
| 作業の開始時 | S4-C start: 102 refs checked, 0 mismatches |
| 全試験・レポート・模擬の後 | after the tests (suites, race reports, simulation): 102 refs checked, 0 mismatches |
| push前（結果文書のコミットの前） | before the push: 102 refs checked, 0 mismatches |
| push後 | 結果文書のコミットに書けないので、完了報告と作業記録（`refs_postpush.txt`）に書く |

## 13. 未実施

実Windows（`O_EXCL`・`fsync`・`core.autocrlf=true`・パスの長さ・再解析ポイント）、物理電源断、ユーザーPC、GitHubのリモート（認証・ブランチ保護・pushの遅延・Actions）、ネットワークのリモートを使った確認は、していない。他者の結果で代用していない。S4-D以降（台帳の参照、定時実行の接続）も、していない。

## 14. 次の段階の前提

S4-Eへの条件は設計§11のとおり。本書の結果は、設計・依頼書の変更を求めない。任意の提案はない。
