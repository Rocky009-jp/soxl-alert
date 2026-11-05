# V2 S4-B 通知 N-01修正（3b2c4ea） 差分の再レビュー

作成日：2026-11-05（日本時間）。担当：Claude Opus 5.5・high（前回のレビュー1f914f9と同じセッション。`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high）。Rockyさんの「推奨どおり」（2026-11-05T02:25Z）を受けた修正について、コーディネーター経由の依頼（02:37Z）で、`git diff d49a4cc 3b2c4ea`の差分だけを再レビューした。製品コード・実装ブランチ・既存試験は変更していない。

結論：**N-01は部分的に解消。重大0・通常1（RN-01：N-01の残り）・提案3。推奨は「限定修正（RN-01だけ、2回目）」。**
`file_sync_only`を選べば、ディレクトリを同期できない環境でも送れるようになった。Windows相当の模擬では、判定の送信・再実行・再送が期待どおりに動く。
ただし、既定の`strict`は、ディレクトリ同期ができない環境でも作成時に拒まない。そのため、`file_sync_only`を選び忘れると、元のN-01と同じく送れず、UNKNOWNの意図が残る。さらに、試験の補助が既定の`strict`を使うので、Windowsでの新規試験は修正前と同じく大半が失敗する（Windows相当で96件中71件）。レビュー1f914f9の修正案のうち、「strictは作成時にWindowsを拒み、`probe_dir_sync`で確かめる」と「試験は実行環境に合うモードを使う」の2点が入っていない。残りの修正は小さい（outbox.pyに数行、補助1行、試験2〜3件）。

## 1. 対象

| 項目 | 完全SHA |
|---|---|
| 修正前（前回の保存最終） | d49a4cc89ee682cc4656f6f037a97e510771e906 |
| 修正 | **3b2c4ea1ae405e77b1f127139f57d8c72518e378**（feat/v2-notify-s4b-20261105の先端） |
| 指摘の元 | レビュー記録1f914f982a684253cba6726489d43408aeda5e79（docs/v2-notify-s4b-impl-review-20261105）のN-01 |

差分：M 3本だけ（v2_notify/outbox.py +14/−4、tests/v2_notify/test_s4b_06_outbox_faults.py +86、tests/v2_notify/test_s4b_10_static.py +1）。どれもS4-Bの開いた範囲で変更を許すファイルで、範囲試験の変更は要らない。読んだもの：差分の全文、修正後のoutbox.pyの`__init__`と`_create`、v2_persistence/local/store.pyの定数、v2_history_local/store.pyの同じimportと`_publish`の耐久性の分岐、修正後のs4b_helpers.pyの`outbox`。

## 2. 修正の中身と判定

| 修正 | 判定 | 根拠 |
|---|---|---|
| `LocalOutbox(root, durability="strict", *, _ops=None)`。値は`"strict"`・`"file_sync_only"`だけ（`str`型の完全一致）、ほかは`notify_args_invalid`で、rootに触れる前に拒む | **妥当** | C-3と同じ2語（定数もC-3と同じくv2_persistence.local.storeから）。拒む値10通りでファイルが変わらないことを試験が確かめる（F03で検出）。`_ops`をキーワード専用にしたので、位置引数で`_ops`を渡す呼出しは無い（既存の試験はすべて`_ops=`） |
| `file_sync_only`では、書く順序からfsync_dirだけを外す | **妥当** | F01（file_sync_onlyでもfsync_dirを呼ぶ）を検出3。ほかの段の失敗はfile_sync_onlyでもCLAIM_FAILED（試験6段） |
| `strict`は従来どおり（fsync_dirの失敗はoutbox_io_error） | **妥当（ただしRN-01）** | F02（strictでもfsync_dirを外す）を検出8、F05（既定をfile_sync_onlyにする）を検出6 |
| strictで作成時の確認（Windows・`probe_dir_sync`） | **入っていない** | RN-01 |
| 試験の補助のモード | **既定のstrictのまま** | RN-01 |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| RN-01 | 通常（N-01の残り） | (a) `LocalOutbox.__init__`は、`strict`のときもディレクトリ同期ができるかを確かめない。C-3（v2_history_local/store.py `_publish`）は、strictでWindowsなら`windows_strict`、それ以外は`probe_dir_sync`の失敗で`directory_sync`として、何も書く前に拒む。`s4brr_windir.py`（`is_windows`が真、fsync_dir・probe_dir_syncがPermissionError（13））：既定・`strict`では、作成は通り、最初の朝が`CLAIM_FAILED`、意図が残り、再実行は`SKIPPED_CLAIMED`・UNKNOWN、再送も`CLAIM_FAILED`で再送の意図も残る（修正前と同じ）。`file_sync_only`では、SENT・exit 0、再実行は既存SENTでexit 0、再送は正しくREFUSED_ALREADY_SENT。(b) 試験の補助`Case.outbox()`（s4b_helpers.py 179〜180行）は既定の`strict`を使う。`s4brr_windir_suite.py`（同じプロセスでfsync_dirをPermissionErrorにし、test_s4b_01〜07を実行）：96件中71件が失敗・エラー（52＋19）。新しいDurabilityの試験6件のうち2件も、strictで走る部分があるため失敗する | (a) Windowsで`file_sync_only`を指定し忘れると、レビュー1f914f9のN-01と同じく、通知が届かず、回復できないUNKNOWNの意図が鍵ごとに残る。設定の誤りが黙って起きる（C-3では起きない）。(b) 依頼書§6の予定する利用者PC（Windows）での新規試験は、修正前と同じく大半が失敗する。本番の予定（Actions、Linux、strict）には影響しない | (1) outbox.py：`strict`のとき、作成時に`ops.is_windows()`なら`NotifyError`（例`outbox_durability_unsupported`）、それ以外は`ops.probe_dir_sync(root)`を1回呼び、失敗なら同じ誤り。どちらもファイルを作らない（C-3と同じ順）。(2) s4b_helpers.py：`Case.outbox()`の既定を`"file_sync_only" if FileOps().is_windows() else "strict"`にする（Linuxの試験は今と同じ）。s4b_worker.pyも同じ。(3) 試験：`is_windows`を真にした模擬でstrictが作成時に拒みファイル0、probe_dir_syncの失敗でも同じ、の2件。欠陥注入に「strictで作成時に確かめない」を足す | `s4brr_windir.py`で既定・strictが作成時に拒まれ、ファイル0。`s4brr_windir_suite.py`で失敗0（補助がfile_sync_onlyを選ぶ形に置き換えて） |
| RP-01 | 提案 | ランタイムのimportに`v2_persistence.local.store`（`STRICT`・`FILE_SYNC_ONLY_MODE`）が増え、静的試験の許可も1行足された。依頼書のS4B-17の許可（fsops）より広い。C-3が同じ定数を同じ場所からimportしている前例はあり、2語をC-3と揃える目的には合う | 動作への影響なし。S2の保存モジュール（codec等）を読み込む | 結果文書の追補に、S4B-17の許可を1つ広げたことと理由を書く。または2語をvalues.pyに文字列で置き、C-3の定数と等しいことを試験で固定する（`NO_COMMIT`と同じやり方） | 記録の確認 |
| RP-02 | 提案 | 試験の名前と中身のずれ：(a) `test_strict_with_a_directory_sync_that_fails_creates_no_notice_and_sends_nothing`は送らないことだけを確かめ、意図のファイルは残る（「creates no notice」は誤解を招く）。(b) `test_file_sync_only_writes_the_same_bytes_...`は、JSONの項目名とtext_sha256の一致を見ていて、バイトの一致ではない（claim_idと時刻が違うので当然）。(c) 独立の変異F04（`str`型の検査を外す）は等価（`str`の派生だけが違う） | 試験の感度は足りている | RN-01の修正の機会に名前を直す | 記録の確認 |
| RP-03 | 提案 | 結果文書V2_NOTIFY_S4B_RESULT.mdは修正前の数値と記述のまま：新規123件→129件、全体2,472件→2,478件、§3.3の書く順序、§13「LocalOutboxはfsync_dirを毎回呼ぶので…使えない」、§5のS4B-13の対応（Durabilityの試験）、RP-01のimport | 受領の記録が古い数値を指す | **更新は必要**。C-4の前例（結果文書へのN-01修正の追補）と同じく、本文は残して末尾に「N-01修正の追補」の節を足す形がよい。RN-01の修正と同じコミット列で行う | 追補の数値が4版の実行と一致すること |

## 4. 確認の詳細

### 4.1 全スイートの再実行

3b2c4eaを完全な履歴の別クリーンクローン（core.autocrlf=false）で取り出し、実装者のrunall.shで17スイートを4版同時に実行した（`s4brr_allver_3b2c4ea.log`）。3.10.20（uv）・3.11.18・3.12.3・3.13.18のすべてで、17スイートとも rc＝0。既存15スイート2,253件＋S4-A 96件＋新規129件（123＋Durability 6）＝**2,478件**。skipはS2のWindows専用4件だけ。実装者の報告と一致した。

### 4.2 修正部分の欠陥注入（`s4brr_mutate.py`、`s4brr_mutants_out.txt`、tests/v2_notifyの129件を3.13で）

| ID | 内容 | 結果 |
|---|---|---|
| F01 | file_sync_onlyでもfsync_dirを呼ぶ | 検出3 |
| F02 | strictでもfsync_dirを外す | 検出8 |
| F03 | どのdurabilityの語も受け入れる | 検出1 |
| F04 | `str`型の検査を外す（集合への所属だけ） | 等価（RP-02(c)） |
| F05 | 既定をfile_sync_onlyにする | 検出6 |

### 4.3 Windows相当の模擬

- `s4brr_windir.py`（`s4brr_windir_out_py3.13.txt`）：

      file_sync_only | first SENT 0 | rerun SKIPPED_CLAIMED SENT 0 | resend REFUSED_ALREADY_SENT | sends 1 | files [claim, result]
      strict | first CLAIM_FAILED 1 | rerun SKIPPED_CLAIMED UNKNOWN 1 | resend CLAIM_FAILED | sends 0 | files [claim, resend-req1.claim]
      default(strict) | （strictと同じ）

- `s4brr_windir_suite.py`（`s4brr_windir_suite_out_py3.13.txt`）：`ran 96 failures 52 errors 19`。失敗はtest_s4b_01〜07のすべてのモジュールにあり、Durabilityの6件のうち2件（strictで走る部分を持つもの）も含む。修正前（1f914f9の`s4bi_windir_suite.py`、90件中69件）とほぼ同じ。

本レビューも実Windowsでは実行していない。Windowsでディレクトリを開けないことは、C-3の`windows_strict`の規則とS2の実Windowsの試験が前提にしている。

### 4.4 調べて問題が無かったこと

- 書く順序と意図・結果の中身は、file_sync_onlyでもfsync_dir以外は同じ（試験とF01で確認）。DAMAGEDの判定、送信権、再送の条件は変わっていない（差分は`__init__`と`_create`の1行だけ）。
- `durability`の検査はrootの検査より前で、誤った値ではファイルシステムに触れない。
- `_ops`のキーワード専用化で、既存の試験・子プロセス（s4b_worker.pyは`LocalOutbox(spec["out"])`）の呼出しは変わらない。

## 5. 推奨

**限定修正（RN-01だけ、2回目）**、その後に差分の再レビュー。

- 理由：`file_sync_only`の追加で「Windowsでは送れない」は解けたが、既定のstrictはWindowsでも黙って通り、元のN-01と同じ失敗と残留を起こす。また、Windowsでの新規試験は修正前と同じく通らない。C-3の前例どおりに作成時に確かめれば、設定の誤りは何も書く前に分かる。修正はoutbox.pyの数行、補助1行、試験2件で、Sonnet・highで足りる。RP-02の名前の直しとRP-03の結果文書の追補を、同じ修正で行う。
- 受領を先にする場合の代わり：3b2c4eaで受領し、受領記録に「Windowsではfile_sync_onlyを必ず指定する（strictは作成時に拒まれない）。tests/v2_notifyはWindowsで大半が失敗する」と書き、RN-01をS4-E（入口のスクリプトでモードを決める段階）の条件に持ち越す。本番の予定には影響しないので、これも成り立つ。
- 結果文書の数値の更新は、どちらの場合も必要（RP-03）。

## 6. 保護参照

依頼書§7の92参照＋4c54e01＋1122052＋f10e719の95件を、`git ls-remote`の完全SHAで照合した。

| 時点 | 結果 |
|---|---|
| 開始時（2026-11-05 02:40Z頃） | 95件一致。feat/v2-notify-s4b-20261105＝3b2c4ea、docs/v2-notify-s4b-impl-review-20261105＝1f914f9 |
| 記録の1回目のpush後 | 95件一致（`s4brr_refs_postpush.txt`）。実装ブランチは3b2c4eaのまま。記録の1回目のコミットは50043e491bea4e2b4f1ddda673d7178932f0a505 |

本再レビューの記録は、3b2c4eaから作った新しいブランチdocs/v2-notify-s4b-fix-rereview-20261105にだけ置いた。実装ブランチ・前回の記録ブランチ・mainは変えていない。

## 7. 確認に使ったもの

`docs/reviews/v2_notify_s4b_fix_rereview_20261105/`（共有フォルダ reviews/ にも写し）：s4brr_allver_3b2c4ea.log、s4brr_mutate.py・s4brr_mutants_out.txt、s4brr_windir.py・s4brr_windir_out_py3.13.txt、s4brr_windir_suite.py・s4brr_windir_suite_out_py3.13.txt、s4brr_protected95.txt・s4brr_ls_remote_start.txt・s4brr_refs_postpush.txt。

再実行の例（リポジトリの根で3b2c4eaを取り出して）：

    PYTHONDONTWRITEBYTECODE=1 python3.13 -B docs/reviews/v2_notify_s4b_fix_rereview_20261105/s4brr_windir.py .
