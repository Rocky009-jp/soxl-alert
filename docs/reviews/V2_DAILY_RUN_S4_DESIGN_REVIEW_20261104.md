# V2 S4（日次実行と本番接続）設計案・S4-A「朝の1回の実行」限定依頼書 レビュー結果

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
位置づけ：設計案と依頼書の初版（3fe3862）へのレビュー。**D-1〜D-7の採用でも、S4-Aの実装の承認でもない。** 採否はRockyさんが決める。

## 1. 対象と参照したもの

| 用途 | 固定版 |
|---|---|
| 対象 | docs/v2-s4-daily-run-20261104 の **3fe3862271e3520cd75ae48d3103af4b9f2798f2**（起点 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb） |
| 設計 | docs/specs/V2_S4_DAILY_RUN_DESIGN_DRAFT.md（301行、blob c06e1302） |
| 依頼書 | docs/tasks/V2_DAILY_RUN_S4A_LIMITED_IMPLEMENTATION_REQUEST.md（260行、blob 8c84bcc8） |
| 試行の差分 | docs/specs/V2_DAILY_RUN_S4A_TRIAL_20261104.diff（255行、blob b0c20c65、SHA-256 13df420c6ad3c7a050e51b67f6f29fd10320f7e063f69abb3a2076673b14821e） |

読んだもの：上の3本、CLAUDE.md、上位の保存・復旧設計 e3e9094（§2.8 追いつきの開始位置、§3.4〜§3.8、§4.1、§5.2・§5.3、§6.1 N-07、§6.6 O-06〜O-09、§8 U-01〜U-14）、2e6ba5f の v2_history_ops（daily.py、read.py、chain.py、values.py）、v2_persistence/runner.py（prepare_day）、v2_history/validate.py（latest_apply_d と processing_after の作り方）、v2_core（engine.py の evaluate_day、observations.py の select_decision、display.py の render_message）、v2_history_publish（check.py の check_publication・reconcile_publication）、v2_history_local/store.py（read・publish・reconcile とロック）、v2_history_restart/build.py、tests/v2_history_restart/test_r3_05_daily_ack.py、tests/v2_history/h_helpers.py、tests/v2_scope_chain/test_sc_02_chain.py、C-4の設計レビュー74c93b1の形式。取得できなかったファイルはない。

保護参照：依頼書§7の88参照を `git ls-remote` の完全SHAで照合し、88件とも一致した。資料ブランチ docs/v2-s4-daily-run-20261104 も 3fe3862 で一致（実装時の89参照目）。

## 2. 結論

**重大0、通常2、提案7。N-01・N-02を設計・依頼書に数行ずつ足した第2版で、D-1〜D-7を一組で採用することを推奨する。依頼書は、このままでは実装に渡さないほうがよい。** 第2版の確認は差分だけでよい。

確かめた範囲：

- S4を A→B→C→D→E に分け、外部につながらない A を先にする判断（D-1）、U-01・U-11・U-13 と送信権の方針（D-2）、C-4 の範囲試験の固定（D-4）、P-01〜P-04 の持ち越し（D-5）、U-06〜U-12 の扱い（D-6）、担当（D-7）は、S1設計§3・§6、上位 e3e9094 §3〜§5・§8・§9、CLAUDE.md の固定条件（日足だけ、朝に通知し夜の寄付きで手動購入、自動発注なし、前日値で補わない）と矛盾しない。
- 試行の差分を 2e6ba5f にそのまま当て、設計§8の場面1〜12を再現した（結果は§5）。既存15スイートの件数も再現した（§5）。
- ただし、依頼書§3の4が固定する**追いつきの開始位置**は、上位 e3e9094 §2.8 と違い、S3-B-3 の再初期化（RESTART_UNKNOWN）の後に毎朝止まり続ける（N-01）。欠陥注入4は正しい実装の側を「欠陥」としている。受入 S4A-13(b) の「最終は1回の実行と同じ」は、依頼書が固定する規則（再試行しない）では保証されない（N-02）。どちらも依頼書の文面どおりに作ると、誤りを作り込むか、試験が時々落ちる。

## 3. 指摘

### 3.1 重大

なし。

### 3.2 通常

| ID | 根拠 | 内容と影響 | 修正案 | 確認方法 |
|---|---|---|---|---|
| N-01 | 依頼書§3の4「`read_effective(history)`の`latest_apply_d`、無ければ`processing_after`」、欠陥注入4「開始位置で`latest_apply_d`を見ず、常に`processing_after`から始める」。設計§5.2「有効な先頭（最後のAPPLYのD、無ければ処理の開始境界）」。試行 run.py `start = view.latest_apply_d or view.processing_after`。上位 e3e9094 §2.8（`as_of_d`があればその次、無ければ最初に見つかるGENESISの`start_after`かRESTART_UNKNOWNの`resume_after`の次）、§3.4手順4、受入案 N-07・O-06。v2_history/validate.py 84〜85行（`latest_apply_d`は有効な履歴**全体**の最後のAPPLY、`processing_after`は**現在のセグメント**の`as_of_d`か境界）。v2_persistence/runner.py の prepare_day（境界は`as_of_d`か`start_after`） | `latest_apply_d`は再初期化の前のセグメントのAPPLYも数える。RESTART_UNKNOWN（`resume_after`＝R）の後は`latest_apply_d`＜R＝`processing_after`になり、ランナーはR以前のセッションから調べ始める。最初の`prepare_history_day`が`target_not_after_boundary`で止まり、**以後の朝はすべてSTOPPED**になる（新しいAPPLYが入らないので自分では抜け出せない）。データは失われず、判定は出ないので誤通知にはならないが、S3-B-3 で用意した復旧（R-4）の後に日次が再開しない。依頼書の受入には再初期化の場面が無く、欠陥注入4は「`processing_after`から始める」を欠陥としているので、正しい実装は注入4を「等価」と報告し、誤った実装が受入をすべて通る | 依頼書§3の4と設計§5.2を「開始位置は`read_effective(history).processing_after`（現在のセグメントの`as_of_d`、無ければGENESISの`start_after`かRESTART_UNKNOWNの`resume_after`。上位§2.8）」に改める。`run_target_before_head`の比較も同じ値で行う。受入に1項（例 S4A-17）を足す：(a) APPLY D1・D2 → RESTART_UNKNOWN（R＝D3）→ D4のdecisionで、D4の引け後の実行がD4を最初のAPPLYとして保存（`gap=false`、上位N-07）、(b) 再初期化の後にACK・欠測宣言を足しても開始位置が動かない（上位O-06）。欠陥注入4を「開始位置に`latest_apply_d`を使う（再初期化の後で区別されること）」に替える | 付属 s4r_restart.py（実物のC-3で、再初期化の後の3朝ともSTOPPED／target_not_after_boundary、直接の`prepare_history_day(D4)`はPREPARED、開始位置を`processing_after`にした版はDONE）。s4r_declare.py (a)（欠測宣言の後は両者が同じ値で、正しく進む） |
| N-02 | 依頼書 S4A-13(b)「子プロセス2〜4個が同じ朝に同時に実行→最終のhistory.jsonが1回だけ実行した結果と同じ」。同§3の9と設計§5.4（`store_busy`・`publication_stale`はSTOPPED、再試行しない）。v2_history_local/store.py `_acquire`（ロックは待たずに`store_busy`）。上位§3.4手順5・§3.7の3行目（拒否されたら読み直し、同じ内容なら成功扱い） | 再試行しない規則では、先に進んでいる実行がもう一方の失敗したpublishのロックと重なって`store_busy`で止まり、もう一方は`publication_stale`で止まる、という並びがある。このとき**両方STOPPEDで、history.jsonは途中の日まで**になる。受入の文面は満たせない（時々落ちる試験になる）。実装者が合わせようとすると、禁止されている再試行（§2、U-12）に手を出しかねない。本番でも、同じ朝に2つ走ると判定の出ない朝があり得る（翌朝の追いつきで回収はされる）。S4-Aが上位§3.7の「読み直して同じ内容なら成功扱い」を採らないこと自体は、U-12をS4-Cで決める方針として妥当 | S4A-13(b)を次に替える：「各報告はDONEか、STOPPED（store_busy・publication_stale）。同じDのAPPLYは1件まで。最終のhistory.jsonは、1回だけ実行した結果の前の部分（途中まで）であり、DONEを返した実行が1つでもあれば1回の結果と同じ。その後に1回実行すると、1回の結果と同じになる」。設計§5.4に「同時に走った実行はどちらも止まり得る。本番では上位§3.6の層1（Actionsのconcurrency）で1つにする」と1文足し、§6.4のS4-Eの項目にconcurrencyを入れる | 付属 s4r_race.py（実物のC-3、6日分の追いつき、子の開始を0〜0.6秒ずらす）。保存した出力 s4r_race_out_py3.13.txt では計120回（2プロセス20＋80回、4プロセス20回）のうち3回（2プロセス）で、全員STOPPED（publication_stale と store_busy）かつAPPLY 5／6件。保存しなかった最初の試し（2・4プロセス各20回）でも各1回。二重のAPPLYは0。DONEのあった回はすべて1回の結果と一致 |

### 3.3 提案（必須ではない）

| ID | 内容 | 案 |
|---|---|---|
| P-01 | 欠測の行（T-1）の条件が`gap`である（依頼書§3の11「gapのある日について」、S4A-05「gap=true」）。GENESIS・RESTART_UNKNOWNの境界の後の最初のAPPLYでは、decisionの無い日が`skipped_sessions`に入っても`gap=false`になる（上位§2.8の最後の項、test_r3_05「a missing day is skipped later without a gap」）。この場合、記録の漏れを知らせる行が出ない | 欠測の行の条件を「`skipped_sessions`が空でない日」にし、行には`skipped_sessions`の日付を書く。S4A-05に再初期化の後の1項を足す |
| P-02 | 設計§6.1は「STALE・STOPPEDの日にも通知を作り、無通知にしない」とするが、`RunError`（引数の誤り、`run_no_closed_session`）と、CoreError以外の例外（§5.6でそのまま上へ出す）は`RunReport`を返さない。cronの遅延・取りこぼしで実行そのものが無い朝も、通知は来ない。工程0の診断（実行の成功＝通知の成功ではない、合図が無いのと止まったのが見分けられない）と同じ種類の穴が、S4-B・S4-Eに残る | §6.1・§6.4に次を書く：入口のスクリプト（S4-E）は、`RunError`と想定外の例外も「判定なし（code）」の通知にする。毎朝必ず1通（合図なしの日も）を契約とし、決まった時刻までに来なければ止まっていると読む、と利用者向けに書く |
| P-03 | 対象Dが有効な先頭の境界そのもの（GENESIS直後の朝で対象D＝`start_after`、再初期化した朝で対象D＝`resume_after`）のとき、§3の7の`prepare_history_day`が`target_not_after_boundary`で止まり、STOPPEDになる。異常ではない場面が「止まった」と読める | 対象D＝`processing_after`で現在のセグメントにAPPLYが無いときは、専用のcode（例`run_target_at_boundary`、「境界の日は評価しない。次のセッションから処理する」）にする。outcomeはSTOPPEDのままでよい |
| P-04 | `now`は対象Dの選択にしか使われない。実行が遅れて対象Dの次の寄付きを過ぎた後に走ると、文面は「F&G観測待ち」の分岐表になる（寄付きの時刻は文面に出る） | 対象DがNO_COMMITで`now`≧次の寄付きなら、文面の先頭に「この分岐表の寄付きは過ぎています」の1行を足すか、STALEにする |
| P-05 | `now`より後の`observed_at`を持つdecisionも消費して保存する。本番では台帳を読んだ時点の行なので、時刻の入力の誤り（タイムゾーンの取り違え等）でしか起きないが、注入した`now`を時刻の基準とする設計（§5.1）と合わない | 消費に使うdecisionの`observed_at`が`now`より後なら、STOPPED（例`run_observation_after_now`）。S4-Dに回すなら§6.3に書く |
| P-06 | 文面の小さなずれ。(a) 依頼書§3の9「保存先を読んだ後のCoreError」は、`store.read()`自体の誤り（ロックの残留での`store_busy`、`store_uninitialized`）を含むかが読み取りにくい（S4A-11はSTOPPEDを期待）。(b) 試行の`RunError`のcode（`run_now_invalid`、`sessions_invalid`）は依頼書§3の2（`run_args_invalid`、fieldで区別）と違う。(c) 試行は`PUBLISHED`の後に読み直したhistoryで同じループを続け、§3の8の「手順4からやり直す」とは形が違う | (a)を「保存先の読込みを含め、それ以後のCoreError」に改める。(b)(c)は依頼書が正で、試行との違いとして結果文書に書く、と依頼書§6に一言足す |
| P-07 | D-2・S4-Eの条件に足すもの。(a) 私有リポジトリのブランチ保護は、GitHub Freeの個人アカウントでは使えないと理解している（未確認のまま。設計の書き方で正しい）。(b) 定時のworkflowは混雑時に遅れたり実行されなかったりする（P-02）。(c) STALEの朝に、後でもう一度走らせるか。上位§5.3の意図の鍵は「対象Dと種別」なので、STALEの通知を出した後の同じDの再実行は送れない | (a)(b)を§4の条件に1行ずつ。(c)はS4-Bで決める問いとして§6.1に書く |

## 4. D-1〜D-7 の推奨

| ID | 推奨 | 理由 |
|---|---|---|
| D-1 S4の分割と順序 | 採用 | Aは既存の受領済みパッケージだけで作れ（試行で確認）、B〜Eはどれも Aの報告を入力にする。外部を変えるのはEだけで、各段階で別の承認を取る形は CLAUDE.md §7 に合う |
| D-2 U-01・U-11・U-13・送信権 | 採用（P-07は任意） | 案B（非公開の別リポジトリ）と台帳の別参照は、上位§3.2・§8でRockyさんが示した推奨と同じ。U-13の「非公開リポジトリのActions＋そのリポジトリのGITHUB_TOKENだけ、コードは公開リポジトリの固定SHA」は、長期の資格情報を作らずに済み、範囲もそのリポジトリに限られる。採るのは方針だけで、作成・登録・変更はS4-Eの各段階で別に承認する、という線引きも明記されている |
| D-3 S4-Aの設計 | **N-01・N-02を入れた第2版で採用** | 対象Dの決め方、未確定で止めて古い日へ落とさない規則、1日1件の保存、成否不明は1回だけ確かめる、例外は値にして外で返す、の形は妥当。開始位置だけは上位§2.8に戻す必要がある |
| D-4 C-4の範囲試験の固定 | 採用 | test_c4_09の18行目の1行と開いた範囲の仮置きで、既存15スイートが通ることを再現した。ENDだけを固定して開いた範囲を外すと鎖の試験が2件落ちることも再現した（§5） |
| D-5 P-01〜P-04の持ち越し | 採用 | S4-Aは解錠・移行・採用を呼ばないので、どれもS4-Aの動作に影響しない。P-02の手順とP-04の注記を設計に残す扱いも、906a70aの「受領の条件にしない」と合う |
| D-6 U-06・U-08・U-09・U-10・U-12 | 採用 | 上位§8の推奨のとおり。U-06（古さの上限）を置かなくても、未確定で止まる規則と、カレンダーの末尾での`next_session_missing`で、古い日へ落ちることはない（§5の確認） |
| D-7 担当 | 採用（Sonnet 5.5・high） | 既存の関数の呼出し順と誤りの扱いが中心で、N-01・N-02を直しておけば、実装者が「固定文書の矛盾」で止まる理由は残らない |

## 5. 実際に行った確認

一時ディレクトリに 2e6ba5f の作業ツリーを作り、試行の差分を `git apply` でそのまま当て、pushしないローカルコミットにした（範囲の鎖の試験のため）。製品コードの変更ではない。確認のスクリプトは付属（docs/reviews/v2_s4_daily_run_review_20261104/）。Python 3.12.3・3.13.18（Linux、git 2.43.0）。プローブの出力は両版で同じ（s4r_probes_out_py3.12.txt・py3.13.txt）。

| 確認 | 結果 |
|---|---|
| 試行のスクリプト（s4a_trial.py、s4a_trial2.py、3.12・3.13） | 設計§8の場面1〜8・10〜12と同じ報告を再現。場面3で文面に欠測の行が無いこと（T-1）、場面12（`now`が先頭より前）がSTOPPED／state_ahead_of_targetになることも同じ |
| 既存15スイート＋仮の範囲試験（`-B -W error::ResourceWarning`、PYTHONDONTWRITEBYTECODE=1、完全な履歴） | Python 3.12.3・3.13.18 とも、15スイート2253件（コア197、保存170、S2 113（skip 4、Windows専用）、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139、C-4 184）＋仮の範囲試験1件が合格、失敗・error 0。設計§8.1の件数と一致。ログ：trial_runall_py3.12.log・py3.13.log |
| ENDだけ固定・開いた範囲なし（2e6ba5fにtest_c4_09の1行だけ） | 範囲の鎖34件のうち2件が失敗（test_two_open_ranges_are_rejected、test_an_open_range_that_is_not_last_is_rejected）。設計§7.1の記述どおり。ログ：end_only_scope_chain_py3.13.log |
| 再初期化の後（s4r_restart.py、実物のC-3） | N-01の観測。再初期化の後の朝3回ともSTOPPED／target_not_after_boundary。開始位置を`processing_after`に替えた版はDONEでD4を消費 |
| 欠測宣言・境界の朝（s4r_declare.py、記憶の中の保存先 s4r_fakestore.py） | 欠測宣言の後は正しく進む（`latest_apply_d`＝`processing_after`）。GENESIS直後・再初期化した朝で対象D＝境界のときはSTOPPED／target_not_after_boundary（P-03） |
| 同時の実行（s4r_race.py） | N-02の観測（保存した計120回のうち3回で全員STOPPED・途中まで、二重APPLY 0） |
| `now`の扱い（s4r_now.py） | 寄付きの後に走った実行が「F&G観測待ち」の分岐表を出す（P-04）。`now`より後の`observed_at`のdecisionを消費する（P-05） |
| コードの読み合わせ | prepare_day が対象Dと途中のセッションの未確定・`intermediate_session_unprocessed`・`late_observation`を自分でも検査すること、NO_COMMITの対象Dでも前のセッションが欠けていればrender_messageが「観測が途切れた」行を出すこと（T-1は消費した日についての補いとして正しい）、カレンダーの末尾では`next_session_missing`で止まり古い日へ落ちないこと、を確かめた |
| 保護参照 | 88件一致（資料ブランチ 3fe3862 も一致） |

## 6. 未解決事項と次の作業

- 採用前に要るのはN-01・N-02の第2版（設計§5.2・§5.4・§6.4、依頼書§3の4・S4A-13(b)・受入1項・欠陥注入4）。差分だけの再レビューでよい。P-01〜P-07は任意で、第2版に入れてもよい。
- 実Windows・ユーザーPC・物理電源断は、このレビューでは未実施（S4-Aの依頼書も未実施と書く前提）。
- 外部の確認（GitHub Freeの私有リポジトリのブランチ保護・Actionsの無料枠）は未実施。S4-Eの作成時に確かめる、という設計の扱いのままでよい。

## 7. 変更したもの

この記録と確認スクリプト・出力を、資料ブランチ docs/v2-s4-daily-run-review-20261104（3fe3862の次）に加えた。設計・依頼書・試行の差分、コード、試験、main、workflow、Actions、Discord、Sheets、秘密、通知先は変えていない。PR・マージ・送信はしていない。
