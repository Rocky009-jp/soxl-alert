# V2 S4-B 通知 RN-01修正（db5dc46・追補6cab050） 差分の再レビュー（2回目）

作成日：2026-11-05（日本時間）。担当：Claude Opus 5.5・high（前回のレビュー1f914f9・再レビュー77e9cf8と同じセッション。`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high）。Rockyさんの「推奨どおり」（2026-11-05T02:53Z）を受けた2回目の修正について、コーディネーター経由の依頼（03:12Z）で、`git diff 3b2c4ea db5dc46`と追補6cab050の差分だけを再レビューした。製品コード・実装ブランチ・既存試験は変更していない。

結論：**RN-01は解消。重大0・通常0・提案2。推奨は「受領」（受領版6cab050）。** これでレビュー1f914f9のN-01も、全体として解消した。
- 既定の`strict`は、作成時に、Windowsなら拒み、そうでなければディレクトリ同期を1回試し、失敗なら拒む。どちらの場合も何も作らない。C-3の`_publish`と同じ順である。
- 試験の補助は、ホストに合うモードを選ぶ。Windows相当の模擬では、test_s4b_01〜07の98件が失敗0になった（修正前は96件中71件が失敗）。
- 4版とも2,480件が合格した。修正部分の欠陥注入5件は、検出4・等価1。
- 結果文書の追補（§14）の数値は、本レビューの実行と一致した。

## 1. 対象

| 項目 | 完全SHA |
|---|---|
| 修正前（1回目の修正） | 3b2c4ea1ae405e77b1f127139f57d8c72518e378 |
| 2回目の修正（コード・試験） | **db5dc4692dbdc77c87d751e31e76edc8a54c4c74** |
| 追補（結果文書§14） | **6cab0506c408d194c63b656713e4a0a7d62c3ba1**（feat/v2-notify-s4b-20261105の先端。db5dc46からは結果文書の+18行だけ） |
| 指摘の元 | 再レビュー記録77e9cf87c7eefb0741ed17eab5658a1da1f15032（docs/v2-notify-s4b-fix-rereview-20261105）のRN-01・RP-01〜RP-03 |

差分：db5dc46はM 9本（v2_notify/outbox.py +16/−3、values.py +1、tests/v2_notify/のs4b_helpers・s4b_worker・test_s4b_01・05・06・07・10）。どれもS4-Bの開いた範囲で変更を許すファイル。6cab050は結果文書だけ。差分の全文を読んだ。

## 2. 修正の中身と判定

| 修正 | 判定 | 根拠 |
|---|---|---|
| `strict`のとき、rootの検査の後、ファイルを作る前に、`ops.is_windows()`なら`outbox_durability_unsupported`（新しいcode、values.py） | **妥当** | C-3と同じ順。`is_windows`の確認を外すG01を検出2 |
| そうでなければ`ops.probe_dir_sync(root)`を1回呼び、`OSError`・`CoreError`・`ValueError`なら同じ誤り。誤りはハンドラの外で投げる（`__context__`なし） | **妥当** | probeを外すG02を検出5、失敗を無視するG03を検出1、ハンドラの中で投げるG05を検出1（`__context__`の検査） |
| `file_sync_only`は確認せず、どの環境でも作れる | **妥当** | 試験`test_file_sync_only_is_accepted_on_windows_and_does_not_probe_the_directory`。`s4brr_windir.py`でSENT・exit 0 |
| 試験の補助：`MODE`（実際のホストがWindowsなら`file_sync_only`、そうでなければ`strict`）を`Case.outbox()`と子プロセスで使う。strictの手順の試験は`StrictOps`（Windowsでないホストとして振る舞い、実Windowsではディレクトリ同期の呼出しを数えるだけ）と`strict_outbox()` | **妥当** | Linuxでは`MODE`＝strictなので、試験の中身は修正前と同じ。実Windowsでもstrictの順序・失敗の試験が走る形になっている |
| 静的試験：`FILE_OPS_ALLOWED`に`is_windows`を足し、使う集合が許可と等しいことを確かめる | **妥当** | ランタイムが使うFileOpsのメソッドが1つ増えただけ |
| 結果文書§14の追補 | **妥当** | 数値（新規131件、全体2,480件、途中の3b2c4eaは129件・2,478件）、Windows相当の98件・失敗0、RP-01のimportの記録、§13の記述の訂正。本文は残し、追補が優先と明記（C-4の前例と同じ形） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| R2-P01 | 提案 | 読むだけの使い方（`outbox_status`、`resend`の前に作る`LocalOutbox`）でも、`strict`ならWindowsで拒まれ、Windows以外ではディレクトリを開いてfsyncする（`probe_dir_sync`）。C-3は書込み（`_publish`）のときだけ確かめる | 誤りではない（拒まれても何も作らず、`file_sync_only`を渡せば読める）。入口で書込み用と状態確認用のモードを揃え忘れると、状態確認だけがWindowsで拒まれる | S4-Eの入口のスクリプトで、モードを1か所で決めて全ての`LocalOutbox`に渡す、と手順に書く。コードは変えない | 記録の確認 |
| R2-P02 | 提案 | 小さな記録のずれ：(a) 追補§14の「依頼書§1の許す範囲」は、変更を許す範囲を定めた依頼書§2のこと。(b) 独立の変異G04（strictでprobeをWindowsの確認より先に呼ぶ）は等価（Windowsではどちらも同じ誤りで、違いは呼出しの順だけ。試験は呼出しの集合を見ている）。(c) 再レビュー77e9cf8のRP-02（試験名`test_file_sync_only_writes_the_same_bytes_...`が項目名とhashの一致を見ている）は、追補の方針どおり未対応のまま | 動作への影響なし | 次に結果文書を触る機会に(a)を直す。受領の条件にしない | 記録の確認 |

重大・通常は無い。

## 4. 確認の詳細

### 4.1 全スイートの再実行

db5dc46を、完全な履歴の別クリーンクローン（core.autocrlf=false）で取り出し、実装者のrunall.shで17スイートを4版同時に実行した（`s4br2_allver_db5dc46.log`）。3.10.20（uv）・3.11.18・3.12.3・3.13.18のすべてで、17スイートとも rc＝0。既存15スイート2,253件＋S4-A 96件＋新規131件＝**2,480件**。skipはS2のWindows専用4件だけ。6cab050はdb5dc46に結果文書を足しただけで、コードと試験は同じ。

### 4.2 修正部分の欠陥注入（`s4br2_mutate.py`、`s4br2_mutants_out.txt`、tests/v2_notifyの131件を3.13で）

| ID | 内容 | 結果 |
|---|---|---|
| G01 | strictで作成時にWindowsを拒まない | 検出2 |
| G02 | strictで`probe_dir_sync`を呼ばない | 検出5 |
| G03 | probeの失敗を無視する | 検出1 |
| G04 | probeをWindowsの確認より先に呼ぶ | 等価（R2-P02(b)） |
| G05 | 拒む誤りをハンドラの中で投げる（`__context__`が残る） | 検出1 |

実装者の追補§14の4件（Windowsを確かめない、probeを呼ばない、確認ごと外す、例外をOSErrorだけにする）とは別に作った。G01・G02は内容が重なり、どちらも検出された。

### 4.3 Windows相当の模擬

- `s4brr_windir.py`（前回と同じスクリプト。`is_windows`が真、fsync_dir・probe_dir_syncがPermissionError（13）。`s4br2_windir_out_py3.13.txt`）：

      file_sync_only | first SENT 0 | rerun SKIPPED_CLAIMED SENT 0 | resend REFUSED_ALREADY_SENT | sends 1 | files [claim, result]
      strict refused at construction: outbox_durability_unsupported []
      default refused at construction: outbox_durability_unsupported []

  前回（3b2c4ea）のstrict・既定は、最初の朝が`CLAIM_FAILED`で意図が残っていた。今回は作成時に拒まれ、ファイルは0。

- `s4br2_windir_suite.py`（試験の補助をimportする前に`FileOps`の`is_windows`を真、`fsync_dir`・`probe_dir_sync`をPermissionErrorにし、test_s4b_01〜07を同じプロセスで実行。`s4br2_windir_suite_out_py3.13.txt`）：`helpers MODE: file_sync_only`、`ran 98 failures 0 errors 0 skipped 0`。実装者の報告（98件・失敗0）と一致した。子プロセスの試験08は含めていない。

本レビューも実Windowsでは実行していない（結果§14のとおり未実施）。

### 4.4 次段階の模擬

実装者のnext_stage_sim.shを6cab050に対して3.13で実行した（`s4br2_next_stage_sim_6cab050.txt`）：[A]全件合格、[B]ENDだけ固定で範囲の鎖2件だけ失敗、[C]固定＋次の段階の開いた範囲で全件合格。受領する場合、次の段階はtest_s4b_09_scope.pyの`END`を`6cab0506c408d194c63b656713e4a0a7d62c3ba1`に固定し、同じコミットで開いた範囲を足す。

### 4.5 調べて問題が無かったこと

- 拒む確認は、`durability`の語の検査とrootの検査の後で、ファイルを作る操作より前。拒んだときの呼出しは`lstat`と`probe_dir_sync`だけ（試験で固定）。
- 送信権・DAMAGEDの判定・書く順序・再送の条件は変わっていない（ランタイムの差分は`__init__`の確認とcodeの定数だけ）。
- 子プロセス（s4b_worker.py）も`MODE`で作るので、Linuxではstrictの確認を通り、競合の試験の中身は前と同じ。

## 5. 推奨

**受領**（コードの修正なし）。受領版は**6cab0506c408d194c63b656713e4a0a7d62c3ba1**。

- RN-01は解消した。これで、実装レビュー1f914f9のN-01（ディレクトリ同期ができない環境で送れず、意図が残る）は、`file_sync_only`で送れること、`strict`の誤った指定は作成時に何も作らずに分かること、試験がどのホストでも走ることの3点で解消した。
- 提案（1f914f9のP-01〜P-04、77e9cf8のRP-02、本書のR2-P01・R2-P02）は、受領の条件にしない。R2-P01はS4-Eの手順で扱う。
- 受領する場合、次の段階はtest_s4b_09のENDを6cab050に固定する。未実施（実Windows、O_EXCLとfsync_dirのWindowsでの振る舞い、物理電源断、利用者PC）は結果§13・§14のとおり残る。

## 6. 保護参照

依頼書§7の92参照＋4c54e01＋1122052＋f10e719の95件を、`git ls-remote`の完全SHAで照合した。

| 時点 | 結果 |
|---|---|
| 開始時（2026-11-05 03:15Z頃） | 95件一致。feat/v2-notify-s4b-20261105＝6cab050、docs/v2-notify-s4b-fix-rereview-20261105＝77e9cf8 |
| 記録の1回目のpush後 | 95件一致（`s4br2_refs_postpush.txt`）。実装ブランチは6cab050のまま |

本再レビューの記録は、6cab050から作った新しいブランチdocs/v2-notify-s4b-fix2-rereview-20261105にだけ置いた。実装ブランチ・前回までの記録ブランチ・mainは変えていない。

## 7. 確認に使ったもの

`docs/reviews/v2_notify_s4b_fix2_rereview_20261105/`（共有フォルダ reviews/ にも写し）：s4br2_allver_db5dc46.log、s4br2_mutate.py・s4br2_mutants_out.txt、s4brr_windir.py・s4br2_windir_out_py3.13.txt、s4br2_windir_suite.py・s4br2_windir_suite_out_py3.13.txt、s4br2_next_stage_sim_6cab050.txt、s4br2_protected95.txt・s4br2_ls_remote_start.txt・s4br2_refs_postpush.txt。

再実行の例（リポジトリの根で6cab050を取り出して）：

    PYTHONDONTWRITEBYTECODE=1 python3.13 -B docs/reviews/v2_notify_s4b_fix2_rereview_20261105/s4br2_windir_suite.py .
