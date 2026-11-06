# V2 S4-E E-0（入口 `v2_run`・ひな形・手順書） 限定実装 レビュー

作成日：2026-11-06（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由の依頼（2026-11-06T00:18Z）。実装者の結論に頼らず、変更境界・依頼書第3版§3の1〜18・受入S4E-01〜18・欠陥注入・保護参照を、試験対象bb4c135で独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。外部（取得先・Discord・GitHubのActions）には接続していない。

結論：**重大0・通常1・提案5。推奨は「限定修正」（N-01の1条件と試験2件、手順書の数行）の後に受領。** 依頼書第3版§3の1〜18と受入S4E-01〜S4E-18は、Linuxの試験対象bb4c135で満たされている（全20スイート2,886件がPython 3.12.3・3.13.18で合格、実装者の報告と一致）。job.py・load.pyの2か所、範囲試験の1行、取得・送信の答え、1回だけ決めるもの、記録の機密は、コードと試験の両方で確かめた。

ただし、**outboxが読めない（参照が無い・gitの取得に失敗）朝に、通知が1通も出ないまま終了コード0になる**（N-01、探りZ4・Z6）。設計§3.4は終了コードの0以外を「通知が届いていない、または届いたか分からない」の2つ目の知らせとしているが、`SKIPPED_CLAIMED`・`SKIPPED_JUDGMENT_EXISTS`を、相手の状態（`existing_status`）を見ずに0にしている。v2-outboxの参照が消えると（無料の非公開リポジトリではブランチ保護が使えず、GitHubのブランチ一覧から削除できる）、毎朝、履歴は進むが通知は出ず、Actionsは成功のまま、失敗のメールも来ない。設計どおりの実装であり、設計§3.4の規則の穴である。修正は入口の1条件（`existing_status`がDAMAGEDなら1）で、探りで効果を確かめた（候補の差分で新規158件もPython 3.11で合格）。
本レビューはPR・マージ・E-1以降・実際の取得・実際の送信・本番の承認ではない。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | 9bdd4217d18e0ac328ddfa6a76b5d2a82748549d（S4-Dの受領版） |
| 試験対象 | **bb4c135ca1b3bda86666b77082c66e6a8b938fcd**（コード・試験・ひな形・手順書の最終。親は9bdd421） |
| 保存最終 | **e4bf50a43b36f47241351ffe9c4a7baa7174fd3f**（feat/v2-run-s4e-20261105。bb4c135からは結果文書1本の追加だけ） |
| 基準 | 設計・依頼書第3版bcb03a1、D-1〜D-10の採用記録a1ba2e7eac469cd869e17eadbd6e3fb5f73074ff（docs/v2-run-s4e-20261105）。設計レビュー800472f、再レビュー4eb0ad5、第3版の確認fdf0e9b |

読んだもの：依頼書第3版の全文、設計第3版の§0〜§13、結果文書の全文、ランタイム5ファイルの全文（614行）、job.py・load.py・test_s4d_09の差分、ひな形・手順書の全文。比較のため v2_notify/job.py の`_take_and_send`・`morning_job`、v2_git_store/outbox.py の`_rebuild`・`load`、v2_git_store/git.py の環境、v2_inputs の`load_inputs`・`MarketPin.read`・`read_ledger`、v2_core の`parse_observation`・`parse_aware_datetime`。新規試験はs4e_helpersと test_s4e_04・06・08・09・10 の本文、ほかの試験名の一覧。共有フォルダの実装者の runall.sh・mutate.py・next_stage_sim.sh・run3.13.log。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠 |
|---|---|---|
| 変更境界（依頼書§2、S4E-18） | **合格** | 9bdd421→bb4c135はA 22本・M 3本。Mは test_s4d_09 の END 1行、job.py の`judgment_known`1行、load.py の`fetch_count`の位置（1行削除・1行追加）だけ。Aは`v2_run/`の5ファイル、`tests/v2_run/`の15本（`__init__.py`なし）、docs/ops/ の2本。bb4c135→e4bf50aは結果文書1本だけ |
| import・呼出し（§3の16） | **合格** | HTTP・`urllib`・`socket`は web.py だけ。時計は`utc_now`1か所、`os.environ`は`main`1か所、`time`は`monotonic`だけ。subprocess・threading・zoneinfo・http.client の直接の使用なし。他パッケージの`_`属性なし |
| 1回だけ決める（R2-P01、§3の3） | **合格** | `Setup`が now→Git→参照→store→outbox→sender→fetch の順に1回。`load_inputs`と`morning_job`に同じ`now`。dryは`v2-dry-*`、liveは`v2-*`、台帳は共通 |
| 送信（§3の11・12、設計§4） | **合格** | 答えの表、`?`を含むURLの拒否、`?wait=true`、`allowed_mentions`、20秒、再試行なし、1900字の分け、見出しの置換は送る直前だけ（outboxと`text_sha256`は元のまま） |
| 取得（§3の10、N-05、RP-01） | **合格** | 30秒・8MiB・200以外は失敗・再試行なし。失敗の語は`http_<3桁>`・`timeout`・`url_error`・`size`・`other`。`URLError(TimeoutError)`は`timeout` |
| 終了コード（§3の5、設計§3.4） | **設計どおり。ただし設計の規則に穴（N-01）** | `SKIPPED_*`を`existing_status`を見ずに0にする |
| init（T-5）・check-source（T-6） | **合格** | 参照ごとに無いときだけ作る。check-source は書かず、`end`はNYの日付の翌日。固定が無いときは比較を省く（探りZ5） |
| 記録の機密（§3の13、S4E-15） | **合格** | パス・URL・秘密・例外の本文なし。`detail`は日付だけ（v2_inputsの`detail=`は4か所とも日付） |
| ひな形（§3の17） | **合格（静的）** | cron 2行、`v2-writer`と読むだけのグループの式、`cancel-in-progress: false`・`queue: max`、モードの1行、入力は`env`経由、`secrets.`なし、40桁の仮の値。`queue: max`の受理と資格情報でのpushは E-2 で確かめる（未確認のまま） |
| 手順書（§3の18） | **合格。小さなずれ（P-03）** | 13項目とE-1〜E-5の確かめること、台帳の始め方。秘密・パスなし |
| job.py・load.py（§3の15） | **合格** | 対照：結果文書§7のとおり（S4E-10・11） |
| 全スイート（S4E-01） | **合格** | bb4c135で2,886件、Py3.12.3・3.13.18（§4.1） |
| 欠陥注入 | **独立28件：検出21・試験の穴5・等価2** | §4.2（実装者の33件は再実行していない） |
| 保護参照 | **一致** | 113参照＋実装ブランチ（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| N-01 | 通常 | entry.py `cmd_morning`の最後の行は`job.delivery in OK_DELIVERIES`（SENT・SKIPPED_CLAIMED・SKIPPED_JUDGMENT_EXISTS）だけで0を返す。`SKIPPED_*`は、v2_notifyが**相手の鍵の状態が`NONE`でない**ときに返す答えで、その状態には`DAMAGED`を含む（job.py `_take_and_send`の`taken != NONE`、`morning_job`の`judgment != NONE`）。`GitOutbox.load`は、参照が無い・gitの取得に失敗した・木が読めないときに例外を出さずに`DAMAGED`を返す（outbox.py 113〜122行、「never raise, never send」）。そのため、outboxが読めない朝は、判定ありは`SKIPPED_CLAIMED`、判定なしは`SKIPPED_JUDGMENT_EXISTS`になり、**何も送らずに終了0**になる。探りZ6（live、2朝SENTの後にv2-outboxの参照を消す）：07-23・07-24の朝とも`run_outcome=DONE`（履歴はその日を消費）、`SKIPPED_CLAIMED`・`existing_status=DAMAGED`、投稿0、終了0。探りZ4（init前の朝）：`store_uninitialized`の判定なしが`SKIPPED_JUDGMENT_EXISTS`（DAMAGED）で送られず、終了0 | 誤った判定は出ない（送らない側）。しかし設計§3.4が終了コードに持たせた役割（「0以外＝通知が届いていない・分からない」、定時の失敗のメールが「来なければ止まっている」の2つ目の知らせ）が、outboxが読めないという**いちばん知らせが要る場面で働かない**。v2-outboxが消えると（P-04：無料の非公開リポジトリでは保護ブランチが使えない。GitHubのブランチ一覧の削除や「古いブランチ」の整理で消せる）、毎朝、履歴は進むが通知は出ず、Actionsは緑のまま、メールも来ない。気づく手段は「9:30までに来なければ止まっている」の1つだけになり、その間の日は消費済みで、後から通知は出ない。gitの取得が全部失敗する朝（Z7）は、記録の測定（`_outbox_files`）が例外を出すので偶然1になるが、outboxの読込みだけが失敗して測定が通る朝は0になる。設計§3.4の規則の穴で、実装は設計どおり | entry.pyの1条件：`delivered = job.delivery in OK_DELIVERIES and job.existing_status != DAMAGED`、`return 0 if (raised is None and delivered) else 1`（`DAMAGED`はv2_notifyから）。候補の差分は付属の`n01_fix_candidate.diff`。試験2件：(a) outboxの参照を消した live の朝→`SKIPPED_CLAIMED`・DAMAGED・投稿0・**終了1**（Z6）、(b) 判定ありがSENTの同じDで、2回目の朝が取得の失敗で判定なし→`SKIPPED_JUDGMENT_EXISTS`・existing SENT・**終了0**（変異V06の穴も同時に埋める）。手順書§6・§10に「v2-*のブランチを削除しない（ブランチ一覧の削除・古いブランチの整理を含む）」「`delivery`がSKIPPEDで`existing_status: DAMAGED`の失敗は、`status`で確かめ、outboxが無ければ`init`で作り直す前にClaudeに相談」を足す。設計§3.4には「`existing_status`がDAMAGEDの`SKIPPED_*`は1」と1行の注記（実装の結果文書に記録でよい）。`CLAIMED`（結果の無い送信権）は、前の実行が時間切れ等で失敗として知らせているので0のままでよい | 候補の差分で、Z6・Z4が終了1、Z7は1のまま、Z8（履歴の参照だけ消す。判定なしが届く）は0のまま（`probe_out_n01_fix.txt`）。新規158件は候補の差分でもPython 3.11.18で合格（`n01_fix_v2_run_py3.11.log`、範囲試験は未コミットなので対象外） |
| P-01 | 提案 | 測定（S4E-16(b)）で149セッションの追いつきの`seconds.morning_job`が172〜225秒となり、設計§10の閾値60秒を超えた | 設計§10が予想した233秒と同じ程度で、開始時の1回だけ（2回目は0.85秒）。閾値は通常の朝のためのもので、追いつきの1回で「別の設計を作る」に進む必要は無い。E-3の境界は直近のセッション（追いつき無し）、E-4の本番の初回は試運転の日数分（10〜20セッション、数秒）。追いつきは日数の2乗に近く伸びるので、E-3とE-4の間を何か月も空けると長くなる（30分の内には収まる見込み） | 手順書のE-3の9に「閾値は通常の朝に当てる。E-4の本番の初回の朝（追いつき）は除き、その時間は記録だけする」と1行。E-4はE-3の後、間を空けずに行う、と添える。今回の受領の条件にしない | E-4の本番の初回の朝の`seconds.morning_job`を記録 |
| P-02 | 提案 | 探りZ1：その朝の7:40より前に`init --start-after <D>`（Dはその朝に閉じた最後のセッション）を行うと、7:40の朝は対象Dが境界と同じなので、`target_not_after_boundary`の判定なしが届く（dry、終了0）。翌朝からは通常どおり | E-2はdryなので外へは出ないが、試運転の最初の記録に判定なしが1つ残り、合否の基準2・10の数え方を迷わせる。E-4の本番の`init`は試運転と同じ古い境界なので起きない | 手順書§12とE-2に「`init`は日本時間9:00より後（その朝の2回の実行の後）に行う」と1行。コードは変えない | E-2の最初の記録 |
| P-03 | 提案 | 手順書の小さなずれ。(a) §1「日曜・月曜の朝…2回とも何も送らない（Actionsの画面には『SKIPPED_CLAIMED』と出る）」：cronは火〜土だけなので、日曜・月曜の朝は実行そのものが無い。`SKIPPED_CLAIMED`が出るのは米国の休場日の翌朝だけ。(b) §2「時刻は必ず`+09:00`を付ける（付けない・`+00:00`と書くと、今より後の観測として台帳の誤りで止まる）」：付けない場合は「今より後」ではなく、coreの`datetime_missing_timezone`で止まる（止まることは同じ）。(c) §9に、`V2_CODE_SHA`の受領版は作業ブランチ上のコミットで、そのブランチを消すとcheckoutが失敗することが無い | どれも判定・通知に影響しない。(a)は日曜にActionsの画面を見たときに「止まった」と誤読させ得る | N-01の手順書の修正と一緒に3か所を直す。今回の受領の条件にしない | 読み合わせ |
| P-04 | 提案 | 独立の変異で、次の5つは試験が拾わない（§4.2）。V06 判定ありがSENTのDの判定なし（`SKIPPED_JUDGMENT_EXISTS`）を終了1にする、V10 2026年より前の「研究だけ」「応答だけ」を入れ替える（試験は両方1件ずつの対称な場面だけ）、V09 固定の最後の日の比較を調整後終値にする（試験は終値と調整後を同じ割合で変える）、V24 `target_rows`を対象D以後の行で数える、V03 素の`ConnectionRefusedError`を`UNKNOWN`にする | 実装は正しい。V06が崩れると、2回目の朝の取得の失敗で毎回失敗のメールが届く（誤警報）。V10が崩れると、E-3の合否の基準5（SOXXで研究だけにある日が0）を逆の数で判断する。V09・V24・V03は影響が小さい（V03は実際の`urlopen`が`URLError`に包むので起きにくい） | V06はN-01の試験(b)で埋まる。V10は「研究だけ2日・応答だけ1日」の非対称の場面を1件。V09・V24は次にcheck.pyを触るときでよい。今回の受領の条件はV06（N-01に含める）だけ | 5つの変異が検出されること |
| P-05 | 提案 | 結果文書§10と実装の報告は、次の段階で`test_s4e_09`のENDを**試験対象bb4c135**に固定するとしている。これまでの段階は、受領版＝保存最終（結果文書のコミット。S4-Dなら9bdd421）をENDにしてきた | どちらでも範囲の鎖は通る（`next_stage_sim`を bb4c135・e4bf50a の両方で再実行し、[a]鎖の失敗2・[b]合格で同じ）。ただし受領記録・メモリ・次の依頼書で版がずれると、次の段階の開始点と範囲の起点が食い違う | 受領記録で「受領版＝ENDに固定する版」を1つに決めて書く（N-01の修正をするなら、その保存最終）。今回の受領の条件にしない | 受領記録と次の依頼書の版が同じ |

重大は無い。

### 3.1 N-01を重大にしない理由

CLAUDE.md §9の重大は「無通知等に影響」を含む。N-01は、通知が出ない朝そのものを作るのではなく（outboxが読めない朝に送らないのは、S4-B・S4-Cで受領済みの安全側の規則）、その朝を**利用者に知らせる2つ目の手段**を失わせる。1つ目の手段（手順書§1「届くべき朝に9:30までに来なければ止まっている」）は残り、起きる条件はoutboxの参照が無い・読めない場合に限られる。そのため通常とした。ただし、本番（E-5）の前に直すべき不具合であり、修正は1条件と試験2件で小さいので、受領の前の限定修正を推奨する。

## 4. 確認の詳細

### 4.1 全スイートの再実行（S4E-01）

試験対象bb4c135を、完全な履歴の別クリーンクローン（`git -c core.autocrlf=false clone`）で取り出し、実装者のrunall.sh（`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`、20スイート）で実行した。版ごとに別のクローン。

| 版 | 結果 |
|---|---|
| 3.13.18 | 全20スイートrc＝0、**2,886件**（既存2,728＋新規158）。skipは`v2_persistence_local`の4件だけ（`runall_bb4c135_py3.13.log`） |
| 3.12.3（Actionsのubuntu-24.04と同じ系列） | 同上、2,886件（`runall_bb4c135_py3.12.log`） |
| 3.11.18 | 新規158件だけ、N-01の候補の差分を当てた状態で合格（`n01_fix_v2_run_py3.11.log`） |
| 3.10 | 未実施（この環境に無く、取得は外部への接続になるため）。実装者の記録では3.10.20で合格 |

スイートごとの件数は結果文書§5・実装者のrun3.13.logと一致した。

### 4.2 独立の欠陥注入（28件＋基準1件）

`review_mutate.py`（試験対象bb4c135のクローンに1件ずつ当て、`tests/v2_run`の`test_s4e_*.py`を`-f`で実行。未コミットなので範囲試験には見えない。Python 3.13、出力`review_mut.json`・`review_mut.txt`）。V00（変更なし）は合格（基準）。

| ID | 内容 | 結果 |
|---|---|---|
| V01 | `URLError(ConnectionRefusedError)`を`UNKNOWN`に | 検出 |
| V02 | `URLError(gaierror)`を`UNKNOWN`に | 検出 |
| V03 | 素の`ConnectionRefusedError`を`UNKNOWN`に | **未検出**（P-04、影響小） |
| V04 | 取得：素の`ConnectionError`を`other`に | 検出 |
| V05 | 取得：`Accept`を外す | 検出 |
| V06 | `SKIPPED_JUDGMENT_EXISTS`を終了1に | **未検出**（P-04、N-01の試験(b)で埋める） |
| V07 | `load_inputs`が投げてもERRORが送れたら終了0 | 検出 |
| V08 | check-sourceの`end`をUTCの日付＋1に | 検出 |
| V09 | `pin_last_close_changed`を調整後終値で比べる | **未検出**（P-04、影響小） |
| V10 | 2026年より前の「研究だけ」と「応答だけ」を入れ替える | **未検出**（P-04） |
| V11 | 分けの境目を`>=`に（1900字ちょうどの行の組を早めに切る） | 未検出・**等価扱い**（部分が増えるだけで、どの部分も上限内、内容は同じ） |
| V12 | 要約のファイルを上書き | 検出 |
| V13 | dryでも環境から`DiscordSender`を作る（使わない） | 検出 |
| V14 | 例外の文字列を記録に出す | 検出 |
| V15 | HALT・ERRORの再送の拒否を判定ありSENTのときだけに | 検出 |
| V16 | initでoutboxを先に作る | 未検出・**等価**（作る順は仕様に無く、どちらの失敗も記録され、終了コードも同じ） |
| V17 | check-sourceの取得失敗でも終了0 | 検出 |
| V18 | check-sourceが履歴の参照を固定として読む | 検出 |
| V19 | 2つ目の部分の4xxを`NOT_STARTED`に | 検出 |
| V20 | 取得で200以外の2xxを受け付ける | 検出 |
| V21 | `status`が別のモードのoutboxを読む | 検出 |
| V22 | `outbox_files`を履歴の参照で数える | 検出 |
| V23 | dryの記録の文面の見出しを置き換える | 検出 |
| V24 | `target_rows`を対象D以後の行で数える | **未検出**（P-04、影響小） |
| V25 | 入口の例外で終了0 | 検出 |
| V26 | `code_version`をそのまま記録 | 検出 |
| V27 | `null`の行を値のある日として数える | 検出 |
| V28 | 拒んだ`start_after`でもoutboxを作る | 検出 |

検出21・試験の穴5（V03・V06・V09・V10・V24）・等価2（V11・V16）。通知の誤り・二重送信・秘密の漏れ・モードの取り違えにつながる変異（V01・V02・V13・V14・V15・V18・V19・V21・V23・V25・V28）はすべて検出された。実装者の33件は再実行していない（結果文書§6の対象はbb4c135そのもので、S4-D実装レビューP-04の申し送りどおり。試験の構成が同じなので、独立の変異で感度を確かめた）。

### 4.3 探り（`s4e_review_probe.py`、試験のヘルパーを使う。一時ディレクトリだけ、ネットワークなし）

| 探り | 場面 | bb4c135 | N-01の候補の差分 |
|---|---|---|---|
| Z1 | 7:00に`init --start-after 07-20`、同じ朝の7:40の朝 | 判定なし`target_not_after_boundary`SENT（dry）、終了0。翌朝はDONE（P-02） | 同じ |
| Z2 | 見出しだけの台帳で最初の朝 | DONE・判定ありSENT（F&G未記録の分岐の文面）、終了0 | 同じ |
| Z3 | 台帳の参照が無い最初の朝 | STOPPED`input_ledger_missing`・判定なしSENT、終了0 | 同じ |
| Z4 | initの前の朝 | STOPPED`store_uninitialized`、`SKIPPED_JUDGMENT_EXISTS`（DAMAGED）、投稿0、**終了0**（N-01） | **終了1** |
| Z5 | 固定の前のcheck-source | 終了0、`pin_through: None`、固定との比較は省く | 同じ |
| Z6 | live、2朝SENTの後にv2-outboxの参照を消す | 2朝ともDONE（履歴は消費）、`SKIPPED_CLAIMED`（DAMAGED）、投稿0、**終了0**（N-01） | **終了1** |
| Z7 | live、リモートに届かない朝 | `input_git_failed`、`SKIPPED_JUDGMENT_EXISTS`（DAMAGED）、投稿0、終了1（測定の例外による） | 終了1 |
| Z8 | live、v2-stateの参照を消す | STOPPED`store_uninitialized`・判定なしSENT、終了0（届いている） | 同じ |

出力は`probe_out_bb4c135.txt`・`probe_out_n01_fix.txt`。

### 4.4 コードを読んで確かめたこと（指摘にしないもの）

- **測定の後の例外**：`cmd_morning`は配達の後に`_outbox_files`と`outbox.load`を測る。ここでgitが失敗すると、通知が届いた朝でも終了1になる（誤警報の側）。記録には配達の行が先に書かれているので、`delivery: SENT`と`failed: GitError…`が並び、読み分けられる。N-01を直した後は、この測定を失敗にしない形も選べるが、今のままでも安全側なので指摘にしない。
- **台帳の例**：手順書の例`fg-2026-11-05,2026-11-05,decision,observed,23,2026-11-06T07:05+09:00`と`not_checked`の空欄は、`read_ledger`・`parse_observation`・`RECORD_ID_PATTERN`・`parse_aware_datetime`（秒なし可）を通る。
- **ひな形の式**：`concurrency.group`は`cond && format(...) || 'v2-writer'`で、`format`は空でないので正しく分かれる。定時の実行では`inputs`が空で`v2-writer`。`ref: ${{ env.V2_CODE_SHA }}`は`with`で`env`の文脈が使える。`run`は`${{ }}`を含まない。gitの作者は`Git`の固定の環境（`v2-runner`）で、ランナーに設定は要らない。
- **資格情報**：`Git`は`GIT_*`を除き`GIT_CONFIG_NOSYSTEM=1`だが、作業場所の設定（とそこからのinclude）は読む。`actions/checkout`の版によって資格情報の置き方が変わり得るので、E-2のpushで確かめる（設計P-03どおり、未確認）。
- **研究データの範囲**：SPY・IEFが2026-08-11以降空なのは、試験の偽の取得先（研究データから作る応答）の制約である。実際の試運転（E-3）は取得先の実データを使い、check-sourceが研究データと比べるのは2026年より前だけなので、E-3の日付の制約にはならない（実装の報告・メモリの「試運転の日付は2026-08-10以前」は、オフラインの試験の場面の話）。
- **追いつきの測定**：P-01のとおり、閾値超えは予想どおりで、指摘にしない。

### 4.5 次の段階の模擬（S4E-18）

実装者の`next_stage_sim.sh`を、bb4c135と保存最終e4bf50aの両方に当てて3.13で実行した（`next_stage_sim_bb4c135_py3.13.log`・`next_stage_sim_e4bf50a_py3.13.log`）。どちらも[a] ENDだけを固定すると`test_sc_02_chain`の2件が失敗（期待どおり）、[b] 次の段階の開いた範囲を足すと鎖34件・本試験20件が合格。

## 5. 推奨と次の最小の作業

- **推奨：限定修正の後に受領。** N-01の1条件（`existing_status`がDAMAGEDの`SKIPPED_*`は終了1）と試験2件（Z6の形、V06の形）、手順書の数行（N-01の2行、P-02・P-03）を、同じブランチの次のコミットとして直す。job.py・load.py・受領済みのパッケージは変えない。担当はSonnet 5.5・high（実装者と同じ）で足りる。修正の後は、差分の再レビュー（Opus・high）で、新規の試験と全スイート1版の結果を確かめる。
- Rockyさんが今のまま受領を選ぶ場合は、N-01をE-2より前（E-1以降の最初のコード変更）の条件として記録する。
- 提案P-01〜P-05は、受領の条件にしない（P-04のV06だけはN-01の試験に含める）。
- 次の段階のEND：受領版を1つに決め、その版に固定する（P-05）。

## 6. 保護参照

開始時（2026-11-06T00:30Z頃）に、依頼書§7の109参照、設計§16で加えた4参照（a1ba2e7・800472f・4eb0ad5・fdf0e9b）、実装ブランチfeat/v2-run-s4e-20261105＝e4bf50aの、計114参照がリモートと完全SHAで一致することを確かめた。本レビューの記録ブランチのpushの前後の照合は、push後の追記に記す。

## 7. 変更したもの

- 新しい記録ブランチ docs/v2-run-s4e-impl-review-20261106（e4bf50aから）に、本書と付属 docs/reviews/v2_run_s4e_e0_impl_review_20261106/（探り・変異のスクリプトと出力、全スイートのログ、N-01の候補の差分と試験のログ、次の段階の模擬のログ）を加えた。
- 製品コード・試験・実装ブランチ・main・Actions・秘密・外部サービスは変更していない。N-01の候補の差分は適用していない（記録だけ）。

## 8. 未実施

- 実Windows、ユーザーPC（Python 3.10.6）、Python 3.10の全スイート、物理電源断。
- 実際の取得先（Yahoo）・Discord・GitHubのActions・非公開リポジトリ。`queue: max`の受理、checkoutの資格情報でのpush、ブランチ保護・ルールセットの可否（E-1・E-2で確かめる）。
- 実装者の33件の変異の再実行（独立の28件で代えた）。
