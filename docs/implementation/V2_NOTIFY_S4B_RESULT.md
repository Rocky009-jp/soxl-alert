# V2 S4-B 通知（文面・ローカルoutbox・送信権・手動再送）限定実装の結果

作成日：2026-11-05（日本時間）。担当：Claude Sonnet 5.5（セッション設定 `claude-sonnet-5-5[1m]`、effort `high`。最後に実行したモデルも `claude-sonnet-5-5` と、`get_session` で確かめた）。
対象：`Rocky009-jp/soxl-alert`、新ブランチ `feat/v2-notify-s4b-20261105`。PR・マージ・Actions・本番・実際の送信・S4-C以降はしていない。外部への接続（Discordを含む）、リポジトリの作成、秘密の登録もしていない。送信先は試験用の偽物だけである。

## 0. 要約

- S4-Bの限定実装は**完了**した。新パッケージ `v2_notify`（5ファイル703行）と、新しい試験 `tests/v2_notify`（10本の試験ファイルと2本の補助、新規123件）を足し、既存の1ファイル（`test_s4a_09_scope.py`）の**1行だけ**（`END`を `6ad609f` に固定）を変えた。設計試行の差分が出した同じ1行（blob `d46af27`）である。
- 試験対象 `f3b9f7f4b05691afbb92595f64ef3c53f17839e7` で、完全な履歴の別クリーンクローン（`core.autocrlf=false`）の Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版とも、**既存15スイート2,253件＋S4-A 96件＋新規123件＝2,472件が全件合格**（失敗0・エラー0・新規のskip 0。既存のskip 4件はS2のWindows専用）。17スイートの終了コードはすべて0。
- 欠陥注入は依頼書の20項目に追加32件を加えた**52件**。結果は検出51・等価1・未検出0・準備失敗0（§8・§9）。等価の1件（追加23）は根拠を書いた。
- S4B-15 の子プロセス競合（2〜4個、判定の通知・同じ再送id・別の再送id）、S4B-16 の総当たり（192通り）、S4B-18 の次の段階の模擬は期待どおり。
- 試験を作る途中で、**試行の下書きに無かった穴を1つ見つけて直した**（§4の6：結果だけが残っている鍵で、意図を作って送ってしまう）。別クリーンクローンでの1回目に、別の再送idの同時実行で「別のプロセスの意図が書き込み中に読まれて`REFUSED_DAMAGED`」という安全側の拒否が起き、試験の許す結果に加えた（§11）。どちらも§4・§11に書いた。
- **未実施**：実Windows、O_EXCLとfsync_dirのWindowsでの振る舞い、物理電源断、ユーザーPC、ネットワークドライブ・同期フォルダ。他者の結果で代用していない（§13）。
- 設計・依頼書の矛盾や範囲外の変更は**見つからなかった**。止めた箇所はない。設計§13の任意提案R-01〜R-03の扱いは§3.4。

## 1. 固定した資料と起点

| 項目 | 値 |
|---|---|
| 資料コミット（docs/v2-notify-s4b-20261105、D-1〜D-8の採用記録） | `4c54e01b218148e49e5ae283e7f0bf2fc52edb46` |
| 設計 `docs/specs/V2_NOTIFY_S4B_DESIGN_DRAFT.md`（blob） | `e95b959c1df1b57fa78e58debc0b046765e568a2` |
| 依頼書 `docs/tasks/V2_NOTIFY_S4B_LIMITED_IMPLEMENTATION_REQUEST.md`（blob） | `6e405d1ad2db46877e3b9e08350331fa175722e8` |
| 試行差分 `docs/specs/V2_NOTIFY_S4B_TRIAL_20261105.diff`（blob） | `42923fde9b82c5c13a8b1895d5bc8738c38cdf22`（sha256 `52e42f8f7a306980bb388573d70db41004bc08ac45bf40c483b3b244824cf647`、取り出して確認。共有フォルダの写しとも一致） |
| コードの開始点 | `6ad609fe52b50565103e56c598505cac85601216`（S4-Aの保存最終。ブランチは6ad609fから切った） |
| **試験対象（コード・試験の最終）** | `f3b9f7f4b05691afbb92595f64ef3c53f17839e7` |
| 最終（この結果文書の追加） | この文書だけを足した次のコミット。SHAはpushの報告に書く |

保護参照は、依頼書§7の92参照に、資料ブランチ（`4c54e01`）・設計レビュー（`1122052`）・再レビュー（`f10e719`）の3本を加えた**95参照**を、開始時・試験後・push前・push後に完全なSHAで照合した（`refcheck.py`、`refs_protected92.txt`、`refs_extra3.txt`）。D-1〜D-8は第2版（`36b2cb1`）に対してRockyさんが採用済み（設計§13、「推奨どおり」2026-11-04T22:39Z）で、本書はその採用を前提にしている。

## 2. 変更したもの

| 場所 | 内容 |
|---|---|
| `v2_notify/__init__.py`（31行） | 公開名と`outbox_status` |
| `v2_notify/values.py`（205行） | 種類・状態・配達結果の語、`NotifyError`（`CoreError`の子）、引数の文字列検査、不変の`Notice`・`JobReport`・`ResendReport`・`OutboxEntry`（reprに文面・パスを出さない） |
| `v2_notify/compose.py`（82行） | `compose_notice`（MORNING・HALT）と`compose_error_notice`（ERROR）。純粋 |
| `v2_notify/outbox.py`（214行） | `LocalOutbox`。S2の`FileOps`だけで、意図・結果を`O_EXCL`で新規作成し、状態を読む |
| `v2_notify/job.py`（171行） | `morning_job`と`resend` |
| `tests/v2_daily_run/test_s4a_09_scope.py` | 18行目 `END` の**1行だけ**（下の差分） |
| `tests/v2_notify/`（新規12ファイル） | `s4b_helpers.py`、`s4b_worker.py`、`test_s4b_01〜10_*.py`（`__init__.py`は作っていない） |
| `docs/implementation/V2_NOTIFY_S4B_RESULT.md` | この文書（別のコミット） |

分け方は5ファイルで、許された上限どおり。ランタイムの全文は `v2_notify/` の5ファイル（703行）で、ブランチの試験対象コミットにある。

`test_s4a_09_scope.py` の差分の全文（`git diff --unified=0 6ad609f f3b9f7f4b05691afbb92595f64ef3c53f17839e7`）：

```
@@ -18 +18 @@
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "6ad609fe52b50565103e56c598505cac85601216"   # accepted (receipt 3e3fd47); frozen when S4-B began
```

S4-Aの試験（96件）はこの1行の固定のあとも同じ件数で通る。`test_s4b_09_scope.py` がこのhunkをS4-Bの差分として固定している。

## 3. ランタイムの規則（依頼書§3のとおり）

### 3.1 種類と鍵、送る条件

- 種類はMORNING（`run_morning`がDONE）、HALT（STALE・STOPPED）、ERROR（`RunError`、`RunError`以外の`CoreError`、プログラムの誤りの例外）。鍵は`<対象D>-<種類>`。
- 対象Dはjobが`run_morning`を呼ぶ前に、S4-Aと同じ規則（`close_at <= now`の最後のセッション）で求める。求まらないとき（sessionsの型の誤り、閉じたセッションが無い、その途中の例外）だけ、ERRORの鍵は`<nowのUTCの日付>-error`。
- HALTとERRORは、`<対象D>-morning`の意図がある（どの状態でも。DAMAGEDを含む）なら作らず、`SKIPPED_JUDGMENT_EXISTS`にする。ERRORの鍵が予備（UTCの日付）のときは、対象Dが無いので判定の確認はしない。`target_status`は鍵に使わない。
- 同じ鍵の2通目は、内容が違っても送らない（`SKIPPED_CLAIMED`）。判定なしの後に判定ありは送れる。

### 3.2 文面

見出し→記録の欠け→注記→本文の順（設計§4）。記録の欠けの条件は`skipped_sessions`が空でないこと。MORNINGは`gap=False`の日だけ（`gap=True`の日はS4-Aの本文がすでに書く）、HALTは全部の日を書く。注記は4つ（次の寄付き以後、保存の未確認＝`run_publish_uncertain`・`run_publish_conflict`、境界の日＝`target_not_after_boundary`、同時の実行＝`store_busy`・`publication_stale`）。MORNING・HALTの本文は`report.message`をそのまま含む。ERRORは固定のcodeと例外の型の名前（識別子に使える文字だけ、64文字まで。それ以外は`Exception`）だけで、例外の本文・パス・URL・秘密は文面にも意図にも入れない。

### 3.3 送信権と記録

- 意図は`<鍵>.claim.json`、結果は`<鍵>.result.json`、再送は`<鍵>.resend-<id>.claim.json`・`.result.json`。中身は正規化JSON（`sort_keys`、区切り`,`と`:`、UTF-8、`ensure_ascii=False`）。意図の項目は設計§5どおり（`schema`＝`v2_notify.claim.1`、kind、d、claim_id、text、text_sha256、run_outcome、code、claimed_at、resend_of）。結果は claim_id・status・recorded_at。
- 書く順序は create_exclusive → 全量のwrite（短い書込みは続きを書く）→ flush → fsync_file → close → fsync_dir。replace・rename・unlinkは呼ばない（試験の偽のFileOpsはこの3つの呼出しで失敗する）。`FileExistsError`は「意図を持たない」、ほかの`OSError`・`CoreError`は`outbox_io_error`にし、値を作るだけで、`NotifyError`はハンドラの外で投げる（`__context__`・`__cause__`が残らない）。
- DAMAGEDにするもの：読めない、UTF-8でない、JSONでない、辞書でない、項目の過不足（正確な項目の集合）、schema・kind・dがファイル名と違う、claim_idが32桁の小文字16進でない、text_sha256が文面と合わない、再送のファイルなのにresend_ofが無い（または原本なのにある）、結果のclaim_idが意図と違う、statusが3語以外、通常のファイルでない（ディレクトリ・リンク）。**意図が無く結果だけある鍵**もDAMAGEDにした（依頼書の表に無い。§4の6）。
- 送信アダプタは`sender.send(text)`だけを1実行に1回呼ぶ。`str`型で値が`"SENT"`ならSENT、`"NOT_STARTED"`ならNOT_SENT、ほかの戻り値と`KeyboardInterrupt`・`SystemExit`以外のあらゆる例外はUNKNOWN（`KeyboardInterrupt`・`SystemExit`は握りつぶさず、意図だけが残る）。

### 3.4 設計§13の任意提案R-01〜R-03の扱い

- **R-01（`outbox_status`）**：採った。`outbox_status(outbox, d, kind=None)`は、そのDのmorning・halt・errorの各鍵と各再送の状態を返す（`kind`を渡すとその種類だけ）。対象Dが求まらなかったERRORは、そのUTCの日付を`d`に渡して見る（試験 `test_s4b_07` の最後）。読むだけで、ファイルを作らない・変えない。
- **R-02（投げ直し）**：採った。CoreError以外の例外は、ERRORを送った場合だけでなく、`SKIPPED_JUDGMENT_EXISTS`・`SKIPPED_CLAIMED`・`CLAIM_FAILED`の場合も、最後に同じ例外オブジェクトを投げ直す（`test_s4b_03` の`AJudgmentStopsTheError`、`Sweep`）。
- **R-03（予備の鍵の名前の重なり）**：限界として残した（依頼書§3の3は`<nowのUTCの日付>-error`を固定している。名前を変えると依頼書の文言と変わる）。対象Dが求まらなかった誤りと、そのUTCの日付と同じ日付のセッションの誤りは、同じ`<日付>-error`の名前になり、後のほうは送られない。Dが求まらない誤りは、sessionsの誤りか閉じたセッションが無い朝に限られる。

### 3.5 exit_code

DONEで、配達がSENTのとき0。`SKIPPED_CLAIMED`で既存の結果がSENTのとき（同じ朝の再実行）も、実行がDONEなら0。それ以外は1（HALT・ERRORは常に1。同じ停止の再実行でHALTがSENTでも1）。

## 4. 試行の下書き（設計§10）との違い

設計§10は「依頼の答えではない」と書いている。依頼書と設計の本文に合わせて、次を変えた。

1. 順序：本文は見出し→記録の欠け→注記→S4-Aの本文（設計§4）。下書きは注記を欠けの前に置いていた。
2. 返り値：下書きは`(report, notice, status)`の組と文字列。実装は不変の`JobReport`・`ResendReport`・`OutboxEntry`（依頼書§3の1）。
3. 鍵：ERRORの鍵を対象Dにした（第2版のN-01）。下書きは常にnowのUTCの日付。
4. 例外の扱い：下書きは`RunError`以外のすべての例外をプログラムの誤りとして投げ直した。実装は`RunError`以外の`CoreError`（例：`render_message`が投げる`soxl_price_definition_unknown`）をERRORとして通知し、**投げない**（S4B-16「CoreErrorは出さない」）。プログラムの誤りだけが同じオブジェクトで投げ直される（R-02で、送らなかった場合も）。
5. 送信アダプタ：下書きは`Exception`だけを受けた。実装は`KeyboardInterrupt`・`SystemExit`以外のBaseExceptionもUNKNOWNにし、戻り値は`str`型の完全一致だけを認める（`str`の派生クラスや`"SENT "`はUNKNOWN）。
6. **穴の修正（試験で見つけた）**：下書きの`_deliver`は、自分の鍵の状態を確かめずに意図を作った。意図が無く**結果だけ**が残っている鍵（手で消した等）では、意図が作れて**送信してしまい**、そのあと結果が作れず`RESULT_NOT_RECORDED`になる形だった（`test_s4b_05` の`Damage`が見つけた）。実装は、意図を作る前に自分の鍵の状態を読み、NONE以外（結果だけの鍵＝DAMAGEDを含む）なら`SKIPPED_CLAIMED`にして送らない。
7. 読み取り：下書きはJSONとして読めるかだけを見た。実装は項目の集合・型・ファイル名との一致・text_sha256・claim_id・statusを検査してDAMAGEDにする（依頼書§3の7より広い。広げた分は§3.3に列挙）。
8. outboxの誤りの写像：下書きは`OSError`を素通ししていた。実装はFileOpsの失敗（`OSError`・`CoreError`）を`outbox_io_error`にし、開いた書込み口・記述子を失敗でも閉じる。`create_exclusive`が`FileExistsError`なら送信権を持たない。
9. rootの検査と引数の検査：下書きには無い。実装は`LocalOutbox`が絶対パス・既存・非リンク・ディレクトリを確かめ、`now`・`resend_request_id`・`d`・`kind`・送信アダプタ・outboxの型を、ファイルに触れる前に確かめる。
10. 注記の置き方とcodeの扱い：下書きは境界・保存の未確認・同時の注記をHALTにも一部しか入れず、`store_busy`・`publication_stale`の注記は無かった（設計§4の3のT-3対応）。実装は設計どおり。
11. `claim`の項目：下書きは`outcome`、実装は設計どおり`run_outcome`と`schema`を加えた。

## 5. 受入とテスト名の対応

| ID | 試験 |
|---|---|
| S4B-01 | `runall.sh`の17スイート（§7）。`test_s4a_09`の1行の固定を含む |
| S4B-02 | `test_s4b_01_args_values`（Root・Arguments・Values：11件） |
| S4B-03 | `test_s4b_02_morning_halt.Morning`の`test_a_done_morning_sends_once_and_writes_an_intent_and_a_result`ほか |
| S4B-04 | 同`Morning`の`test_the_same_morning_again_sends_nothing_and_changes_no_byte`、`test_the_key_does_not_depend_on_the_target_status_of_the_run`（P-04(a)）、`test_a_rerun_after_an_unclear_send_is_skipped_and_is_not_a_success` |
| S4B-05 | 同`Halt`（(a)(b)(c)(d)と境界の日の判定なし） |
| S4B-06 | `test_s4b_03_error`（`ErrorNotice`(a)(b)(c)、`KeyIsTheTargetDate`(d)、`AJudgmentStopsTheError`(e)） |
| S4B-07 | `test_s4b_04_text.MissingRecords` |
| S4B-08 | 同`Notes` |
| S4B-09 | 同`Body` |
| S4B-10 | `test_s4b_05_send_state.Answers` |
| S4B-11 | 同`IntentOnly`と`Answers`の`KeyboardInterrupt`・`SystemExit` |
| S4B-12 | 同`Damage` |
| S4B-13 | `test_s4b_06_outbox_faults`の`Order`・`Claim`・`Result` |
| S4B-14 | `test_s4b_07_resend`（`Resend`・`Status`：14件） |
| S4B-15 | `test_s4b_08_processes.Race` |
| S4B-16 | `test_s4b_06_outbox_faults.Sweep` |
| S4B-17 | `test_s4b_10_static.Runtime` |
| S4B-18 | `test_s4b_09_scope`（`PathJudgement`・`FilesChanged`・`Chain`・`TestFiles`：19件） |

期待値は、S4-Aの`run_morning`の報告（別のクリーンな履歴rootで同じ入力に対して実行したもの）、試験側で書いたリテラル・JSON・`hashlib`、偽の送信先の記録から作った。実装の出力をコピーしていない。

## 6. 結果の確認（実際に行ったこと）

- 依頼書・設計・試行差分を読み、blobとsha256を共有フォルダの写しと照合した。開始点`6ad609f`からブランチを切り、保護95参照を照合した。
- 実装し、試験を作りながら直した。作業中のSHAは使い捨て（`--amend`）で、試験対象は`f3b9f7f4b05691afbb92595f64ef3c53f17839e7`の1本だけ。
- 別クリーンクローン（`git clone --no-hardlinks -c core.autocrlf=false`、完全な履歴、試験対象を`checkout --detach`）を4版のPython用に4つ作り、それぞれで`runall.sh`（17スイート）を実行した。`__pycache__`は作らず（`-B`と`PYTHONDONTWRITEBYTECODE=1`）、`-W error::ResourceWarning`で実行した。Python 3.10は環境になかったため、`uv python install 3.10`で入れた3.10.20を使った（3.11.18・3.12.3・3.13.18は環境のもの）。
- 欠陥注入は試験対象の使い捨てworktreeで1件ずつ実行した（3並列）。
- 作業記録（実行スクリプト・全ログ・欠陥注入の生結果・競合の集計・保護参照の照合）は共有フォルダ `/mnt/project-files/implementation/s4b_notify_20261105/` に置いた（リポジトリには入れていない）。
- 別の再実行：1回目のクリーンクローン試験で3.11の1件が失敗した（§11）。試験を直し、新しい試験対象で4版すべてを最初からやり直した。さらに、欠陥注入の追加22（相対パスのroot）が「検出」と出ていたのは前のレース試験の偶然の失敗によるもので、実際には検出されていなかった（相対パスで存在しないものしか試していなかった）。存在する相対パス（`.`と`os.path.relpath`）を試験に足して試験対象を作り直し、4版の全件試験と欠陥注入を最初からやり直した。以下の数値はすべて最後の試験対象`f3b9f7f4b05691afbb92595f64ef3c53f17839e7`のもの。

## 7. 全スイートの結果

4版とも次の表と同じ件数で、すべて `rc=0`・失敗0・エラー0（Python 3.12.3の実行を表にした。skipは`v2_persistence_local`の4件だけ）。

| スイート | 件数 | 結果 |
|---|---|---|
| v2_core | 197 | OK |
| v2_persistence | 170 | OK |
| v2_persistence_local | 113 | OK (skipped=4) |
| v2_recovery | 176 | OK |
| v2_history | 230 | OK |
| v2_history_ops | 173 | OK |
| v2_history_restart | 109 | OK |
| v2_history_restore | 165 | OK |
| v2_history_diagnose | 131 | OK |
| v2_history_adopt | 170 | OK |
| v2_scope_chain | 34 | OK |
| v2_history_consume | 112 | OK |
| v2_history_publish | 150 | OK |
| v2_history_local | 139 | OK |
| v2_history_maintain | 184 | OK |
| v2_daily_run | 96 | OK |
| v2_notify | 123 | OK |

既存15スイート＝2,253件、S4-A＝96件、S4-B＝123件、合計**2,472件**。`runall.sh`の終了コードは4版とも0。ログは `s4b_notify_20261105/final_runall_py3.10.log`〜`3.13.log`。

## 8. 欠陥注入

試験対象の使い捨てworktreeに1件だけ壊しを入れてコミットし（範囲試験がGitのHEADを読むため）、`tests/v2_notify`の全件（123件）を実行した。壊しが「検出」されるとは、その試験が1件以上失敗またはエラーになること。依頼書の20項目（番号は依頼書§5どおり）に、追加32件を足した。

| 区分 | 壊し | 分類 | 落ちた件数 | 最初に落ちた試験 |
|---|---|---|---|---|
| 依頼1 | HALT does not look for a judgment claim first | DETECTED | 3 | test_a_halt_after_a_damaged_judgment_is_not_sent |
| 依頼2 | a DAMAGED judgment claim does not stop the HALT | DETECTED | 2 | test_a_halt_after_a_damaged_judgment_is_not_sent |
| 依頼3 | the target status decides the kind (and so the key) of a DONE notice | DETECTED | 15 | test_a_judgment_can_follow_a_halt_of_the_same_day |
| 依頼4 | the missing-records condition is the gap | DETECTED | 5 | test_a_halt_also_names_the_missing_days_of_a_day_whose_gap_is_false |
| 依頼5 | a MORNING notice also writes the days with gap=true (they overlap the S4-A text) | DETECTED | 2 | test_a_morning_does_not_repeat_a_day_that_the_s4a_text_names |
| 依頼6 | a HALT notice writes no missing records | DETECTED | 2 | test_a_halt_also_names_the_missing_days_of_a_day_whose_gap_is_false |
| 依頼7 | the note of the passed open: >= becomes > | DETECTED | 1 | test_the_note_of_the_passed_open_is_in_from_the_open_itself_and_not_one_microsecond_before |
| 依頼8 | the ERROR text carries the text of the exception | DETECTED | 4 | test_a_big_soxl_close_in_the_core_text_is_the_same_as_any_program_error |
| 依頼9 | a program error is not raised again | DETECTED | 11 | test_a_damaged_judgment_stops_a_later_error_too |
| 依頼10 | an exception of the sender is NOT_SENT | DETECTED | 11 | test_a_rerun_after_an_unclear_send_is_skipped_and_is_not_a_success |
| 依頼11 | after NOT_SENT or UNKNOWN the same run calls send once more | DETECTED | 7 | test_a_halt_after_a_judgment_in_any_state_is_not_sent |
| 依頼12 | the claim is created by an overwriting write instead of create_exclusive | DETECTED | 12 | test_after_a_claim_that_could_not_be_created_a_healthy_rerun_sends_once |
| 依頼13 | a claim without a result is taken for 'not sent' and sent | DETECTED | 7 | test_a_rerun_after_an_unclear_send_is_skipped_and_is_not_a_success |
| 依頼14 | the claim_id of a result is not compared with the claim's | DETECTED | 1 | test_a_result_with_a_missing_wrong_or_extra_field_is_damaged |
| 依頼15 | a resend does not look at the other resends' SENT | DETECTED | 2 | test_after_a_resend_that_is_unknown_another_id_can_send |
| 依頼16 | a resend whose id has an intent is made again under another name | DETECTED | 2 | test_the_same_id_again_is_not_sent |
| 依頼17 | the outbox raises its error inside the handler (the context stays) | DETECTED | 1 | test_the_error_that_the_outbox_raises_keeps_no_context_cause_or_os_text |
| 依頼18 | fsync_file is not called | DETECTED | 6 | test_after_a_claim_that_was_started_a_healthy_rerun_does_not_send |
| 依頼19 | the ERROR key is the UTC date of the call even when D is known | DETECTED | 6 | test_a_damaged_judgment_stops_a_later_error_too |
| 依頼20 | an ERROR notice does not look for a judgment claim first | DETECTED | 3 | test_a_damaged_judgment_stops_a_later_error_too |
| 追加1 | extra: a MORNING notice is stopped by a HALT claim of the same day | DETECTED | 3 | test_a_halt_after_the_judgment_of_the_same_day_is_not_sent |
| 追加2 | extra: a rerun of a sent judgment is not exit 0 | DETECTED | 3 | test_the_key_does_not_depend_on_the_target_status_of_the_run |
| 追加3 | extra: a sent HALT is exit 0 | DETECTED | 3 | test_a_stale_morning_sends_one_halt_notice_with_the_s4a_text |
| 追加4 | extra: the hash of the text is not checked when a claim is read | DETECTED | 1 | test_a_claim_with_a_missing_wrong_or_extra_field_is_damaged |
| 追加5 | extra: an extra field in a claim is accepted | DETECTED | 1 | test_a_claim_with_a_missing_wrong_or_extra_field_is_damaged |
| 追加6 | extra: a result without a claim reads as NONE | DETECTED | 1 | test_a_result_without_a_claim_and_a_directory_in_the_place_of_a_file_are_damaged |
| 追加7 | extra: a str subclass equal to SENT counts as SENT | DETECTED | 1 | test_every_other_answer_and_every_exception_is_unknown |
| 追加8 | extra: the resend text has no line in front | DETECTED | 2 | test_a_resend_of_a_halt_and_of_an_error_uses_the_stored_text |
| 追加9 | extra: the resend_request_id is not checked in resend | DETECTED | 1 | test_a_bad_resend_request_id_d_or_kind_is_refused_before_any_file_is_read |
| 追加10 | extra: morning_job does not check now | DETECTED | 1 | test_a_now_without_a_time_zone_is_refused_everywhere_and_nothing_is_touched |
| 追加11 | extra: KeyboardInterrupt and SystemExit of the sender are swallowed | DETECTED | 1 | test_a_keyboard_interrupt_and_a_system_exit_are_not_swallowed_and_leave_an_intent_only |
| 追加12 | extra: the result always says SENT | DETECTED | 17 | test_a_resend_claim_that_is_not_shaped_as_a_resend_is_damaged |
| 追加13 | extra: the note of an unsure save only for run_publish_uncertain | DETECTED | 1 | test_the_note_of_the_unsure_save_is_in_a_halt_of_the_two_codes_only |
| 追加14 | extra: the note of a run at the same time only for store_busy | DETECTED | 2 | test_the_note_of_a_run_at_the_same_time_for_the_two_codes |
| 追加15 | extra: no note for the boundary day | DETECTED | 1 | test_the_note_of_the_boundary_day |
| 追加16 | extra: the note of the passed open also for a decided target | DETECTED | 1 | test_no_note_of_the_passed_open_when_the_target_has_its_decision_or_is_the_last_session |
| 追加17 | extra: fsync_dir is not called | DETECTED | 6 | test_after_a_claim_that_was_started_a_healthy_rerun_does_not_send |
| 追加18 | extra: the S4-A text is shortened in the MORNING notice | DETECTED | 4 | test_a_done_morning_sends_once_and_writes_an_intent_and_a_result |
| 追加19 | extra: a resend of an original that was SENT is not refused | DETECTED | 1 | test_an_original_that_was_sent_is_refused |
| 追加20 | extra: a DAMAGED earlier resend does not refuse | DETECTED | 2 | test_a_resend_claim_that_is_not_shaped_as_a_resend_is_damaged |
| 追加21 | extra: the notices are not immutable | DETECTED | 1 | test_the_values_are_immutable_and_their_repr_shows_no_text_and_no_path |
| 追加22 | extra: a relative root is accepted | DETECTED | 1 | test_a_root_that_is_not_an_absolute_existing_directory_is_refused_without_touching_anything |
| 追加23 | extra: a link is not refused by the root check (the reparse-point part) | EQUIVALENT | 0 |  |
| 追加24 | extra: the JSON is not written with sorted keys | DETECTED | 1 | test_a_done_morning_sends_once_and_writes_an_intent_and_a_result |
| 追加25 | extra: the JSON is written with ensure_ascii | DETECTED | 2 | test_a_done_morning_sends_once_and_writes_an_intent_and_a_result |
| 追加26 | extra: the claim_id is not random (a fixed value) | DETECTED | 2 | test_an_unknown_original_is_sent_again_once_with_one_line_in_front |
| 追加27 | extra: the result is recorded before the send (status UNKNOWN is final) | DETECTED | 35 | test_a_halt_after_the_judgment_of_the_same_day_is_not_sent |
| 追加28 | extra: a short write is not completed (one write only) | DETECTED | 1 | test_a_short_write_is_completed_and_a_zero_write_is_an_error_not_a_loop |
| 追加29 | extra: a CoreError that escapes the run is raised instead of notified | DETECTED | 2 | test_the_report_of_a_skipped_error_says_so |
| 追加30 | extra: the exception type name is not filtered | DETECTED | 1 | test_the_type_name_in_the_text_is_a_plain_identifier |
| 追加31 | extra: outbox_status creates a file | DETECTED | 3 | test_a_bad_resend_request_id_d_or_kind_is_refused_before_any_file_is_read |
| 追加32 | extra: a damaged original is listed as NONE | DETECTED | 9 | test_a_halt_after_a_damaged_judgment_is_not_sent |

## 9. 欠陥注入の分類

- 検出：51件。
- 等価：1件。**追加23**（rootの検査で`and not link`を外す）。Linuxの`lstat`はリンクそのものの種別を返すので、リンクなら`S_ISDIR`がすでに偽で、外しても結果が変わらない。この行が効くのはWindowsの再解析ポイント（ジャンクション）だけで、実Windowsでは確かめていない。
- 未検出：0件。準備失敗：0件。
- 依頼8（ERRORの文面に`str(e)`）は、2か所（jobの型名にstr(e)を足す、composeの識別子検査を外す）を同時に壊した。どちらか片方だけだと、もう片方の検査で防がれる（防御が二重になっている）。

## 10. 保護参照

| 時点 | 結果 |
|---|---|
| 開始時（ブランチを切る前） | 95参照が完全SHAで一致 |
| 試験後 | 95参照が完全SHAで一致（`refs_after_tests.txt`） |
| push前・push後 | 報告に書く（`refs_final_before_push.txt`・`refs_postpush.txt`） |

## 11. S4B-15・S4B-16・S4B-18 の回数と結果

### S4B-15（子プロセス）

試験は、2〜4個の子プロセスが、ファイル`go`の出現で同時に始め、各自の偽の送信先に送った文面を自分のログに書く。試験内の繰り返しは各4回（morning_job・同じ再送id・別の再送id、各N=2,3,4）。下は同じ試験の場面を**各40回**繰り返して数えた記録（`race_report.py`）。

```
morning_job, 40 repetitions each
 N=2
    40 x sends=('halt', 'morning') halt_codes=('store_busy',) note_ok=True judgments_after_rerun=1
 N=3
    40 x sends=('halt', 'morning') halt_codes=('store_busy', 'store_busy') note_ok=True judgments_after_rerun=1
 N=4
    40 x sends=('halt', 'morning') halt_codes=('store_busy', 'store_busy', 'store_busy') note_ok=True judgments_after_rerun=1
resend, the same id, 40 repetitions each
 N=2
    40 x sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED')
 N=3
    40 x sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED')
 N=4
    40 x sends=1 deliveries=('SENT', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED', 'SKIPPED_CLAIMED')
resend, different ids, 40 repetitions each
 N=2
    40 x sends=2 deliveries=('SENT', 'SENT')
 N=3
    40 x sends=3 deliveries=('SENT', 'SENT', 'SENT')
 N=4
    40 x sends=4 deliveries=('SENT', 'SENT', 'SENT', 'SENT')
```

読み方：
- **morning_job**：40回すべてで、判定なし（halt）が1通・判定あり（morning）が1通。負けた側が`store_busy`で先に止まり、勝った側が判定ありの意図を作る前に、判定なしの意図を作るため（設計のT-3と同じ）。判定ありの二重・判定なしの二重は0回。判定なしの文面には同時の実行の注記がすべてある。そのあと健全に1回実行しても判定ありは増えない（合計1通）。
- **同じ再送id**：1通まで（残りは`SKIPPED_CLAIMED`）。
- **別の再送id**：元がUNKNOWNなら各idで1通（上位§5.3の契約どおり。送信数＝意図の数）。
- 試験の許す結果に、安全側の`REFUSED_DAMAGED`を加えた。1回目のクリーンクローン試験（Python 3.11）で、別の再送idの同時実行のとき、別のプロセスが意図を**書き込んでいる途中**のファイルを読んで`REFUSED_DAMAGED`で断る場合があった（送らない側の結果で、ユーザーは後で同じ依頼を出せる）。この状態は「作成中のファイルは壊れて見える」という設計上のもので、判定ありの意図を作成中に判定なしが来た場合も同じく安全側（送らない）に倒れる。

### S4B-16（総当たり）

偽の送信先・偽の保存先・偽のFileOpsの各呼出し点に、`CoreError`・`OSError(EIO)`・`PermissionError`を1つずつ起こした。場面は3つ（判定、判定なし、実行の誤り）。呼出し点は、判定が11種21回、判定なしが11種23回、実行の誤りが10種20回（合計64点）で、**192通り**。どの場合も、`morning_job`は`JobReport`を返すか、注入した`CoreError`以外の例外の**そのオブジェクト**を出し（`CoreError`は出ない）、1つの実行の送信は1回以下、そのあとの健全な再実行を含めても、同じ種類の通知は1通まで。

### S4B-18（範囲試験）

次の段階の模擬（`next_stage_sim.sh`、使い捨てworktree、pushしない）：

```
[A] tested commit f3b9f7f4b05691afbb92595f64ef3c53f17839e7
  v2_scope_chain: Ran 34 tests in 2.240s | OK
  v2_history_maintain: Ran 31 tests in 1.726s | OK
  v2_daily_run: Ran 19 tests in 1.297s | OK
  v2_notify: Ran 19 tests in 1.445s | OK
 1 file changed, 1 insertion(+), 1 deletion(-)
[B] END frozen, no open range (expected: test_sc_02 chain test fails)
  v2_scope_chain: Ran 34 tests in 2.315s | FAILED (failures=2)
  v2_history_maintain: Ran 31 tests in 1.781s | OK
  v2_daily_run: Ran 19 tests in 1.276s | OK
  v2_notify: Ran 19 tests in 1.500s | OK
[C] END frozen + minimal open range of the next stage
  v2_scope_chain: Ran 34 tests in 2.221s | OK
  v2_history_maintain: Ran 31 tests in 1.817s | OK
  v2_daily_run: Ran 19 tests in 1.557s | OK
  v2_notify: Ran 19 tests in 1.700s | OK
```

- [A] 試験対象そのまま：S4-Bの開いた範囲で通る。
- [B] 次の段階がENDだけを固定し、開いた範囲を足さない：範囲の鎖の試験（`test_sc_02`）が2件失敗する（記録。想定どおり）。
- [C] 固定に加えて、次の段階の最小の開いた範囲試験を足す：すべて通る。

範囲の鎖は `…→2e6ba5f→6ad609f→（S4-B）` で隙間がない（`test_s4b_09_scope.Chain`）。

## 12. 文面の例

実際の出力（一部）。すべて試験用の偽の送信先に渡す値で、実際には送っていない。

```
=== MORNING (target D=2026-03-05, F&G not yet recorded)
【SOXL日次】対象D=2026-03-05
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-05 ／実行区分: F&G観測待ち
データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2026-03-02〜2026-03-05、4行）
市場側（F&G以外の条件を含む判定）
  極端恐怖: F&G次第（armedは不明。成立してもarmed等が不明のため参考・未確認）
  通常買い: 不成立（前日もnormal_raw成立で立上がりでない）
  トレンド参加: 不成立（市場側の条件が不成立）
F&G現在値（目視）: 未記録 → 購入条件は未確定です。
  F&Gの値による分岐（目視した値で手元判定できます。再通知はありません）
    25未満       → 極端恐怖の条件成立（参考・未確認） → 利用可能資金の100%（比率のみ）
    25以上30未満 → 通常買いは不成立
    30以上       → トレンド参加は不成立（RSIの55上抜けまたはSMA200条件を満たさない）
  ※この日のdecision観測を記録しないと（合図なしの日も）、次のセッションを処理するときにarmedが不明、連続数が0になります。毎日記録してください。
市場状態: armed=不明、連続数（確認済み観測）=0、前日normal_raw=確認済みtrue
プロファイル別（案U: 保有・原価・現金・余力は入力していません）
  条件が成立した場合の口座条件は、手元で確認してください。
P20の原価目安 b*: SOXL D終値が入力にないため表示しません。
株数・金額は出しません。売却推奨・注文方式は出しません。

=== MORNING (decided day)
【SOXL日次】対象D=2026-03-06
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／実行区分: 合図なし
データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2026-03-02〜2026-03-06、5行）
市場側（F&G以外の条件を含む判定）
  極端恐怖: 不成立（F&Gは25以上）
  通常買い: 不成立（F&Gは25以上30未満の帯、市場側の条件は成立、前日もnormal_raw成立で立上がりでない、armedは不明）
  トレンド参加: 不成立（F&Gは30未満）
F&G現在値（目視）: 29（decision、observed_at=2026-03-07T01:00:00+00:00、対象D=2026-03-06）
市場状態: armed=不明、連続数（確認済み観測）=0、前日normal_raw=確認済みtrue
プロファイル別（案U: 保有・原価・現金・余力は入力していません）
  条件が成立した場合の口座条件は、手元で確認してください。
P20の原価目安 b*: SOXL D終値が入力にないため表示しません。
株数・金額は出しません。売却推奨・注文方式は出しません。

=== MORNING with a missing record and after the next open
【SOXL日次】対象D=2026-03-05
【F&Gの記録の欠け】
  2026-03-04 の前に、F&Gの記録が無いセッションがありました: 2026-03-03
※この実行は対象Dの次の寄付き（2026-03-06T09:30:00-05:00）の後です。下の分岐表の寄付きは過ぎています。
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-05 ／実行区分: F&G観測待ち
データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2026-03-02〜2026-03-05、4行）
市場側（F&G以外の条件を含む判定）
  極端恐怖: F&G次第（armedは不明。成立してもarmed等が不明のため参考・未確認）
  通常買い: 不成立（前日もnormal_raw成立で立上がりでない）
  トレンド参加: 不成立（市場側の条件が不成立）
F&G現在値（目視）: 未記録 → 購入条件は未確定です。
  F&Gの値による分岐（目視した値で手元判定できます。再通知はありません）
    25未満       → 極端恐怖の条件成立（参考・未確認） → 利用可能資金の100%（比率のみ）
    25以上30未満 → 通常買いは不成立
    30以上       → トレンド参加は不成立（RSIの55上抜けまたはSMA200条件を満たさない）
  ※この日のdecision観測を記録しないと（合図なしの日も）、次のセッションを処理するときにarmedが不明、連続数が0になります。毎日記録してください。
市場状態: armed=不明、連続数（確認済み観測）=0、前日normal_raw=確認済みtrue
プロファイル別（案U: 保有・原価・現金・余力は入力していません）
  条件が成立した場合の口座条件は、手元で確認してください。
P20の原価目安 b*: SOXL D終値が入力にないため表示しません。
株数・金額は出しません。売却推奨・注文方式は出しません。

=== HALT (STALE, D2 without a record)
【SOXL日次】対象D=2026-03-06 ／判定なし
【F&Gの記録の欠け】
  2026-03-05 の前に、F&Gの記録が無いセッションがありました: 2026-03-04
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／未確定のセッションがあります
  今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
  理由コード: run_session_unconfirmed（sessions）
  対象のセッション: 2026-03-06
  この実行で保存した日: 2026-03-03、2026-03-05
  市場状態は、保存した日までです。それより後の日は処理していません。

=== HALT (store_busy)
【SOXL日次】対象D=2026-03-05 ／判定なし
※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-05 ／実行を止めました
  今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
  理由コード: store_busy（lock）
  この実行で保存した日: なし
  市場状態は、保存した日までです。それより後の日は処理していません。

=== HALT (run_publish_uncertain)
【SOXL日次】対象D=2026-03-06 ／判定なし
※最後の日の保存は確認できていません。
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-06 ／実行を止めました
  今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
  理由コード: run_publish_uncertain（store）
  対象のセッション: 2026-03-05
  この実行で保存した日: 2026-03-03、2026-03-04
  市場状態は、保存した日までです。それより後の日は処理していません。

=== HALT (boundary day)
【SOXL日次】対象D=2026-03-02 ／判定なし
※対象Dは記録の開始境界の日です。次のセッションから処理します。異常ではありません。
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-02 ／実行を止めました
  今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。
  理由コード: target_not_after_boundary（target_session_date）
  この実行で保存した日: なし
  市場状態は、保存した日までです。それより後の日は処理していません。

=== ERROR (program error)
【SOXL日次】判定なし（実行の誤り） 対象D=2026-03-04
  今朝は結果を出していません。条件未達ではありません。
  理由コード: unexpected_error（ZeroDivisionError）

=== ERROR (no closed session, key = UTC date)
【SOXL日次】判定なし（実行の誤り） 日付（UTC）=2026-03-02
  今朝は結果を出していません。条件未達ではありません。
  理由コード: run_no_closed_session

=== RESEND
【再送】元の通知の送信を確認できなかったため、同じ内容を送ります
【SOXL日次】対象D=2026-03-05
【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=2026-03-05 ／実行区分: 合図なし
データ: 検査済み（SOXX価格定義=adj_close_total_return、前史 2026-03-02〜2026-03-05、4行）
市場側（F&G以外の条件を含む判定）
  極端恐怖: 不成立（F&Gは25以上）
  通常買い: 不成立（F&Gは25以上30未満の帯、市場側の条件は成立、前日もnormal_raw成立で立上がりでない、armedは不明）
  トレンド参加: 不成立（F&Gは30未満）
F&G現在値（目視）: 28（decision、observed_at=2026-03-06T01:00:00+00:00、対象D=2026-03-05）
市場状態: 
…

=== files of the resend case
2026-03-05-morning.claim.json
  {"claim_id": "0e7cda69ba64dd52e54492b7465ba033", "claimed_at": "2026-03-05T18:00:00-05:00", "code": null, "d": "2026-03-05", "kind": "morning", "resend_of": null, "run_outcome": "DONE", "schema": "v2_notify.claim.1", "text": "【SOXL日次】対象D=2026-03-05\n【SOXL日次・ローカルプレビュー…", "text_sha256": "e003e3707df05232eb328df67a38a40a77d6e91064da055b2470a676e7d9e9a4"}

2026-03-05-morning.resend-req1.claim.json
  {"claim_id": "a08041c81f09796727483484f0de97e3", "claimed_at": "2026-03-05T22:00:00-05:00", "code": null, "d": "2026-03-05", "kind": "morning", "resend_of": "0e7cda69ba64dd52e54492b7465ba033", "run_outcome": "DONE", "schema": "v2_notify.claim.1", "text": "【再送】元の通知の送信を確認できなかったため、同じ内容を送ります\n【SOXL日次…", "text_sha256": "ec75e8218fe6685143c0c854a3aa36c53515dc2a4afc981e573cab48718b72d1"}

2026-03-05-morning.resend-req1.result.json
  {"claim_id": "a08041c81f09796727483484f0de97e3", "recorded_at": "2026-03-05T22:00:00-05:00", "status": "SENT"}

2026-03-05-morning.result.json
  {"claim_id": "0e7cda69ba64dd52e54492b7465ba033", "recorded_at": "2026-03-05T18:00:00-05:00", "status": "UNKNOWN"}
```

## 13. 未実施・持ち越し

- **未実施**：実Windows（O_EXCLとfsync_dirの振る舞いを含む。`LocalOutbox`はfsync_dirを毎回呼ぶので、ディレクトリのfsyncができない環境ではoutboxが使えない）、物理電源断、ユーザーPC、ネットワークドライブ・同期フォルダ。Windows用の新規N・S4-A 96・C-3 139・範囲の鎖34は実行していない。
- **実際の送信先**：接続しない。実際の送信先が何を`NOT_STARTED`とするか（U-04の具体化）、コアの見出し「ローカルプレビュー（実送信なし）」の扱い、文字数の上限・分割、concurrencyは、S4-E。
- **設計の持ち越しのまま**：S4-AのP-03（ACKの試験）、S4-DのP-02(b)・P-05、S4-EのP-07、S4-Cの「先頭の通番の表示」。再レビューの提案R-03は§3.4。第2版のレビューの提案P-01〜P-09は設計どおり記録のみ（P-01 同じDの2通目のHALTで欠けが出ない限界、P-07 寄付き後の注記の拡大、P-08 元の実行が終わる前の再送、など）。
- **知っておく限界**：
  - 作成中の意図は他のプロセスからDAMAGEDに見える（上のS4B-15）。判定の意図の作成中に来た判定なしも、判定ありの意図が見えれば送らないが、まだ見えなければ送る（T-3。注記で読み分ける）。
  - 再送は、元の実行がまだ走っている（意図だけがある）ときもUNKNOWNとして受け付ける（設計§13のP-08は記録のみ）。
  - 意図の作成が途中で止まると（`write`の後など）、そのファイルは空・途中までで、DAMAGEDになる。送らない側に倒れるだけで、outboxは自動では直さない。手で直す手順は未整備。
- 設計の意図と違うと分かったことは**ない**。矛盾・範囲外の変更は無く、止めた箇所もない。
