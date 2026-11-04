# V2 S4-A 朝の1回の実行 限定実装依頼書

作成日：2026-11-04（日本時間）。版：**第2版**（初版3fe3862へのレビューdd60f6fの通常N-01・N-02だけを反映。§3の4、S4A-09の語、S4A-13(b)、S4A-17の追加、欠陥注入4。ほかは初版と同じ）。作成：Claude Opus 5.5、effort high。
状態：**第2版・D-1〜D-7採用済み**（Rocky「推奨どおり」2026-11-04T14:55Z、レビューdd60f6fの推奨。設計§11）。限定実装は、別スレッドへの明示の着手指示で始める。本書の保存だけでは実装を始めない。
対になる設計はdocs/specs/V2_S4_DAILY_RUN_DESIGN_DRAFT.md（以下「設計」）。本段階はS4-A（注入した保存先・時刻・入力で、追いつき→最新セッションの評価→プレビュー文面と実行報告までを1回行う）だけを実装する。通知・outbox・送信・gitの保存先・取得・本番接続（S4-B〜S4-E）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb**（feat/v2-history-maintain-c4-20261104、C-4の保存最終） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-s4-daily-run-20261104）の設計とdocs/specs/V2_DAILY_RUN_S4A_TRIAL_20261104.diff。SHAと3つのblobを開始報告に記録 |
| C-4の受領 | 実装レビュー906a70a2877cf135947498f53c0750cb3c43156d、再レビュー8d02abf1622714cdeb38df6bd5bab91787249eb7 |
| C-3・C-2の値と保存先 | 2e6ba5fのv2_history_local（`HistoryFileStore`のread／publish／reconcile）、v2_history_publish（publish_day、Reconciliationの状態） |
| 日の準備 | 2e6ba5fのv2_history_ops（prepare_history_day、read_effective、PREPARED／NO_COMMIT／ALREADY_APPLIED） |
| 文面 | 2e6ba5fのv2_core.display.render_message |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、2e6ba5fから作る（ブランチ名の案：feat/v2-daily-run-s4a-YYYYMMDD）。
  1. ユーザーが設計§9のD-1〜D-7を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-7）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-7を、採用されたと書かない。
- 運用方針は日足だけ（分足・NBBOを前提にしない）。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_daily_run/ 新規 | `__init__.py`、`run.py`、`values.py`（RunReport・定数・RunError）。分ける必要があれば4ファイルまで。結果文書に分け方を書く |
| tests/v2_history_maintain/test_c4_09_scope.py | 設計§7.1の`END`の1行だけ |
| tests/v2_daily_run/ 新規 | test_s4a_\*.py、s4a_helpers.py、s4a_worker.py（子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_DAILY_RUN_S4A_RESULT.md 新規 | 本段階の結果 |

これ以外は変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local、v2_history_maintain。
- 既存の試験・変異・fixtures・ヘルパー（p_helpers、h_helpers、c2_helpers、c3_helpers、c4_helpers、sc_helpers等）。新しいヘルパーからimportするのはよい。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09、test_c2_09、test_c3_09、test_c4_09（上の1行を除く）。
- 設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

次の範囲へ広げない。

- S4-B〜S4-E：通知の意図・結果・送信・再送、gitの保存先、市場データ・台帳・カレンダーの取得、入口のスクリプト・CLI・環境変数、workflow、秘密、本番。
- 保存先の初期化・解錠・移行・採用の呼出し、保存の再試行、古さの上限（U-06）。
- C-4レビューのP-01〜P-04（設計§7.2）、C-3実装レビューのP-01・P-03、C-3設計レビューのP-01〜P-07、C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03、C-4設計レビュー74c93b1のP-01〜P-06、B-4§7.1の既知の制限、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

1. **入口**：`run_morning(store, now, series, sessions, raw_observations) -> RunReport`だけを公開する（設計§5.1）。ランナーは時計・環境変数・ファイル・ネットを使わない。
2. **引数の検査（保存先を読む前）**：次は`RunError`（CoreErrorの子、code `run_args_invalid`、fieldで区別）で止め、保存先に触れない。
   - nowが`datetime`でない、またはtzinfo・utcoffsetが無い。
   - sessionsが`SessionList`でない。
   - storeに呼べる`read`・`publish`・`reconcile`が無い。
3. **対象D**：`close_at <= now`の最後のセッション（設計§5.2）。無ければ`RunError`（`run_no_closed_session`）。
4. **開始位置**：`read_effective(history).processing_after`（現在のまとまりの`as_of_d`、無ければGENESISの`start_after`かRESTART_UNKNOWNの`resume_after`。上位e3e9094 §2.8、設計§5.2）。`latest_apply_d`は使わない（再初期化の前のAPPLYも数えるため）。対象Dがこれより前なら、`STOPPED`（`run_target_before_head`）で何も書かない。
5. **未確定**：開始位置より後で、対象D以前のセッションを古い順に見る。confirmed=falseに当たったら、`STALE`（code `run_session_unconfirmed`、detailにそのD）で止める。それより前の消費は残す。それより後へは進まない。
6. **追いつき**：設計§5.3の1〜3。`PREPARED`のときだけ`publish_day`→`store.publish`。返った`history`を次の入力にする。`NO_COMMIT`・`ALREADY_APPLIED`は保存しない。ほかの状態は来ない前提で、来たらプログラムの誤りとして止める（握りつぶさない）。
7. **対象Dの評価**：ループで対象Dを調べていれば、その結果を使う。開始位置が対象Dと同じで調べていなければ、`prepare_history_day(history, 対象D, …)`を1回呼ぶ（ALREADY_APPLIEDの文面）。この呼出しのCoreErrorも`STOPPED`にする（試行のT-2）。
8. **成否不明**：`store_commit_uncertain`のときだけ、同じ公開値で`store.reconcile`を1回呼ぶ。
   - `PUBLISHED`・`PUBLISHED_THEN_EXTENDED`なら、`store.read()`で読み直し、手順4から追いつきをやり直す。ただし、同じ実行の中でやり直すのは高々1回とし、2回目の成否不明は`STOPPED`（`run_publish_uncertain`）にする。
   - `NOT_PUBLISHED`は`run_publish_not_published`、`CONFLICT`は`run_publish_conflict`で`STOPPED`。
   - `publish`は同じ公開値で2回呼ばない。
9. **そのほかの誤り**：保存先を読んだ後のCoreError（保存先・C-2・コア）は、すべて`STOPPED`にし、code・field・ruleを報告に写す。例外処理の中では値を作るだけで、`RunReport`は例外処理の外で作って返す。CoreError以外の例外はそのまま出す。
10. **報告**：設計§5.5の項目を持つ不変の値にする。`exit_code`はDONEが0、STALE・STOPPEDが1。消費した日ごとに、d、状態、gap、skipped_sessions（コアの遷移の値）を持つ。
11. **文面**：
    - DONE：消費した日のうちgapのある日について1行ずつ（欠測のセッションの日付を含む）書き、その後に対象Dの`render_message`の全文を変えずに続ける。
    - STALE・STOPPED：判定・分岐表・b\*を含めない。「条件未達ではない」「前日値で補っていない」、code、それまでに保存した日を書く。
    - どの文面にも、パス・例外の本文・URL・秘密を入れない。文言の細部は実装者が決め、結果文書に例を載せる。

## 4. 受入条件 S4A-01〜S4A-17

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、既存の関数（prepare_history_day、publish_day、check_append_batch、validate_history、render_message）と、試験側の計算から作る。ランナーの出力をコピーしない。

| ID | 必須確認 |
|---|---|
| S4A-01 回帰 | 既存の15スイート計2253件を、完全なクローンで維持する（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139、C-4 184）。test_c4_09の1行の固定を含み、件数は同じ |
| S4A-02 引数 | §3の2・3の各誤りでRunError。保存先の呼出しが0回であること（記録する偽物で確かめる） |
| S4A-03 対象D | now＝close_atはそのセッション、1マイクロ秒前は前のセッション。時刻帯の違うnow（UTCと−5）で同じ結果。セッションが無い・全部未来ならrun_no_closed_session |
| S4A-04 通常の追いつき | decisionのある日を古い順に1件ずつ保存し、最終のhistory.jsonのバイトが、試験側でprepare_history_day→check_append_batchを順に適用した結果と一致する。publishの呼出し回数は、消費した日数と同じ |
| S4A-05 欠測 | decisionの無い日は保存されない。次に消費した日はgap=true、skipped_sessionsに欠測の日。文面にその日付を含む欠測の行がある（T-1） |
| S4A-06 再実行 | 同じnowでもう一度実行すると、publishは0回、ファイルのバイトは同じ、文面も同じ。対象Dを消費した後の再実行はALREADY_APPLIEDの文面 |
| S4A-07 対象Dの決定済み | 対象Dのdecisionが窓の中で記録済みなら、対象Dも消費し、文面はその結果（render_messageの全文と一致） |
| S4A-08 未確定 | 途中のセッションが未確定なら、STALE、exit 1、それより前だけ保存、それより後のdecisionは消費しない。文面に判定・分岐表・b\*が無い |
| S4A-09 時刻の戻り | 開始位置（§3の4）より前の対象DでSTOPPED（run_target_before_head）、保存なし、例外が漏れない（T-2） |
| S4A-10 入力の誤り | ledger_mismatch、decision_outside_window、市場行の欠け、sessionsの文脈の不一致で、そのDでSTOPPED。それまでの日は保存済み。止まった後のバイトは、最後の成功の後のバイトと同じ |
| S4A-11 保存先の停止 | 実物のC-3で、store_busy（ロックの残留）、store_uninitialized、store_read_only、store_layout_unsupported（snapshot.json）、store_artifact_present（一時ファイルの残留）がSTOPPED。どれもrootの一覧・バイトを変えない。ランタイムがv2_history_maintainをimportしない |
| S4A-12 成否不明 | 偽の保存先で次を確かめる。(a) 実際は書いた後にstore_commit_uncertain→reconcileがPUBLISHED→読み直して続き、最終結果が通常と同じ。(b) NOT_PUBLISHED→STOPPED、publishは1回だけ。(c) CONFLICT→STOPPED。(d) reconcile自体の誤り→STOPPED。(e) 2回目の成否不明→run_publish_uncertain |
| S4A-13 競合 | (a) 読込みと保存の間に別の書き手が1件足した→publication_staleでSTOPPED、二重の記録なし。(b) 子プロセス2〜4個が同じ朝に同時に実行（ファイルの合図で同時に始める）→各報告はDONEか、STOPPED（store_busy・publication_stale）。同じDのAPPLYは1件まで。最終のhistory.jsonは、1回だけ実行した結果の前の部分（途中まで）で、DONEを返した実行が1つでもあれば1回の結果と同じ。その後に1回実行すると、1回の結果と同じになる（第2版でN-02を反映。全員STOPPEDの並びはあり得る。本番は設計§5.4のconcurrencyで1実行にする） |
| S4A-14 例外の出口 | 偽の保存先・コアの各呼出しでCoreErrorを起こす総当たりで、run_morningは必ずRunReportを返し、`__context__`・`__cause__`が残らない。CoreError以外（例：RuntimeError）はそのまま出る |
| S4A-15 静的な範囲 | ランタイムのimportが§2の許可だけ（datetime、v2_core、v2_history_ops、v2_history_publish）。open・os・socket・subprocess・time・random・urllib・environの使用なし。`datetime.now`・`utcnow`・`today`の呼出しなし。`initialize`・`unlock`・`migrate`・`adopt`の呼出しなし。RunReportが不変で、reprに文面全体・パスが出ない |
| S4A-16 範囲試験 | 新しい範囲試験（START＝2e6ba5f、END＝None、REV＝END or "HEAD"、FilesChanged）が、§2の変更だけを許す。test_c4_09の差分を自分の差分のハンクとして固定する。範囲の鎖が`…→6d69bd7→2e6ba5f→（S4-A）`で通る。ENDだけを固定して開いた範囲を外すと鎖の試験が失敗する手順を、結果文書に記録する（C4-22と同じ形） |
| S4A-17 再初期化の後 | 実物のC-3で、(a) APPLY D1・D2 → RESTART_UNKNOWN（resume_after＝D3）→ D4のdecisionのとき、D4の引け後の実行がD4を再初期化の後の最初のAPPLYとして保存し（gap=false、上位N-07）、DONEになる。(b) 再初期化の後にACK・欠測宣言を足しても開始位置が動かない（上位O-06）。期待値は試験側のprepare_history_dayから作る（第2版でN-01を反映） |

## 5. 限定欠陥注入

1件ずつ壊して試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. 対象Dの決定で`<=`を`<`にする。
2. 未確定のセッションを飛ばして先へ進む。
3. 未確定のセッションで止めずに、評価だけ続ける（STALEにしない）。
4. 開始位置に`processing_after`ではなく`latest_apply_d`を使う（再初期化の後でS4A-17が検出すること。第2版でN-01を反映して向きを逆にした）。
5. 対象Dをループから外す（`< 対象D`にする）。
6. PREPAREDの日に保存しない。
7. 文面から欠測の行を外す。
8. NOT_PUBLISHEDを成功として扱う。
9. NOT_PUBLISHEDで同じ公開値をもう一度publishする。
10. PUBLISHED_THEN_EXTENDEDの後に読み直さず、手元のhistoryで続ける。
11. 対象Dの評価（§3の7）のCoreErrorを捕まえない（T-2）。
12. 例外処理の中でRunReportを作って返す（`__context__`が残る形）。
13. `except CoreError`を`except Exception`にする。
14. STALEでも`render_message`の全文を文面に入れる。
15. nowの代わりに`datetime.now(timezone.utc)`を使う。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴。浅いクローンでは範囲の鎖の試験が偽の失敗をする）で試験する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、新規NとC-4 184、C-3 139、範囲の鎖34を実行する。実Windowsで行うまで未実施と書く。ユーザーPC・物理電源断は未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_daily_run -p "test_s4a_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- ランタイムの全文の場所と行数。
- test_c4_09の差分の全文。
- 試行の下書き（設計§8）との違いと、その理由。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。
- S4A-14の総当たりの件数、S4A-16の手順と結果。
- 文面の例（DONE、欠測つきDONE、STALE、STOPPED）。
- 追いつきの所要時間の参考値（合否の条件にしない）。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・通知・S4-B以降へは進まない。

## 7. 読取専用の保護参照

次の88参照を、開始時と保存・push後に完全SHAで照合する。実装時は、さらに次の2本を加える（実装時は90参照）。本書と設計を保存した資料ブランチdocs/v2-s4-daily-run-20261104の受け取った版の完全SHA（採用記録のコミット）と、レビューdocs/v2-s4-daily-run-review-20261104のdd60f6f22d773561cfcc3ab09c868e02d9d0a973。

| 参照 | 完全SHA |
|---|---|
| main | 31144d9b6af8a6c920ad53c395cd550e8c48a7fa |
| feat/interim-notification-20261026 | 920e69571cf4feda09f3f2f560e96fcb9cb09d50 |
| docs/v2-roadmap-20261023 | 647aeac34cde0d01ec27174f7620aff1724af0e1 |
| feat/v2-offline-core-20261027 | 1a54a8573023af9490017b02a8b6458f061031c7 |
| feat/v2-core-state-checks-20261028 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| docs/v2-market-state-recovery-20261027 | b43205ce1a53e4560fb85f9cfb715c72a1132a75 |
| docs/v2-persistence-domain-20261028 | 425df80d04b116e25e481184069b89bed1380c3a |
| docs/v2-persistence-domain-s1-receipt-20261028 | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| feat/v2-persistence-domain-offline-20261028 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| fix/v2-persistence-domain-s1-review-20261028 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| docs/v2-persistence-domain-s1-fix-receipt-20261028 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048 |
| fix/v2-core-fg-numeric-overflow-20261028 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| docs/v2-core-fg-overflow-receipt-20261028 | a235b7607f5624ed84ba5427ac0f44029f41d262 |
| docs/v2-local-store-s2-20261028 | 73cec624cb73205ac63ca92e26df2b6f70019b16 |
| feat/v2-local-file-store-s2-20261028 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| docs/v2-local-store-s2-receipt-20261028 | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| fix/v2-local-store-s2-review-20261028 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| docs/v2-local-store-s2-fix-receipt-20261028 | 1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a |
| docs/v2-user-pc-tests-20261028 | aa21dbe85a133c61e8c011a6f78db1b23af0fb13 |
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| docs/v2-history-s3b4-review-20261102 | 814b86190562475286300d7e6df3a749a9140331 |
| fix/v2-history-restore-plan-s3b4-review-20261102 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| docs/v2-history-s3b4-fix-rereview-20261102 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| docs/v2-history-s3b5-20261102 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136 |
| docs/v2-history-s3b5-review-20261102 | 842d44b192a03531f6d3cb896d8281733814899f |
| docs/v2-history-s3b5-v2-rereview-20261102 | 6a7210c2e278e604b953acf904cf9e796c2ce710 |
| feat/v2-history-diagnose-s3b5a-20261102 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6 |
| docs/v2-history-s3b5a-review-20261102 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9 |
| docs/v2-history-s3b5b-20261102 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |
| feat/v2-history-adopt-s3b5b-20261103 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01 |
| docs/v2-history-s3b5b-review-20261103 | 92630a3d5233f14900c7472dc754850701a56b61 |
| fix/v2-history-adopt-s3b5b-review-20261103 | b626c98af5f01bc94e7b41d86aadde9663695eb9 |
| docs/v2-history-s3b5b-fix-rereview-20261103 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b |
| docs/v2-scope-range-freeze-20261103 | 08072cc47aa12340ed947d40f02ca8741a4060d6 |
| feat/v2-scope-range-freeze-20261103 | dda7eb706637adc5f6dd37513e4b6ca360fde2ba |
| docs/v2-scope-range-freeze-review-20261103 | fa4b232810569f4512d09f244ef50f9685ff0c95 |
| fix/v2-scope-range-freeze-review-20261103 | bfbde7a7854bf91a77fb58737c24b19c6507453a |
| docs/v2-scope-range-freeze-fix-rereview-20261103 | 9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d |
| docs/v2-consume-c1-review-20261103 | b473db46ad3dbf3ad76fa76f50c49b03b558936d |
| docs/v2-consume-s3c-20261103 | a6340c3937092e4cb658913b9acfb4973a084326 |
| feat/v2-history-consume-c1-20261103 | de6549acb4ecea759cc771300fd0bef59dd5456a |
| docs/v2-history-publish-c2-20261103 | 9dd64b8eb07ad35dd23c011ed2dbb1196307f542 |
| docs/v2-history-publish-c2-review-20261103 | a6e783e57c1de5dd92e6b43cfc416a1d79a672eb |
| docs/v2-history-publish-c2-impl-review-20261103 | a91a9ed31481e97cc8b56c2396f86d957fa567e0 |
| docs/v2-history-publish-c2-revision-20261103 | 081637e95160a23aab5ea0fc3a2edd01976abba4 |
| feat/v2-history-publish-c2-20261103 | d6b0332500af8d8d46ddaae6c7fda39ee38a03db |
| docs/v2-history-local-c3-20261104 | 6ad98521a788297f8db64468337c71767dca7304 |
| docs/v2-history-local-c3-review-20261104 | 213bcb7f05d2e1be5f04d529289b437367457f3e |
| feat/v2-history-local-c3-20261104 | 6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a |
| docs/v2-history-local-c3-impl-review-20261104 | 2049e1056f76e606343c3eb0fbbe82e531988ca6 |
| docs/v2-history-maintain-c4-20261104 | d11b87597ef4035f5fee0ffc8c9fa859f82fe00f |
| docs/v2-history-maintain-c4-review-20261104 | 74c93b11236f83508c354dee9a38df9cc38a1c67 |
| docs/v2-history-maintain-c4-v2-rereview-20261104 | 8f39111369531b320f20320dac733775c87f3e5c |
| feat/v2-history-maintain-c4-20261104 | 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb |
| docs/v2-history-maintain-c4-impl-review-20261104 | 906a70a2877cf135947498f53c0750cb3c43156d |
| docs/v2-history-maintain-c4-fix-rereview-20261104 | 8d02abf1622714cdeb38df6bd5bab91787249eb7 |

本書の作成時（2026-11-04）に、上の88参照がリモートと完全SHAで一致することを、開始時と資料ブランチのpush後に確かめた。

## 8. 採用単位

設計§9のD-1〜D-7と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。

- D-1：S4の分割（A〜E）と順序。
- D-2：U-01・U-11・U-13・送信権と再送の方針。作成・登録・変更は、S4-Eの各段階での別の承認による。
- D-3：S4-Aの設計。
- D-4：C-4の範囲試験の固定。
- D-5：C-4レビューのP-01〜P-04の扱い。
- D-6：U-06・U-08・U-09・U-10・U-12のS4-Aでの扱い。
- D-7：担当（Sonnet 5.5・high）。

今回の文書作成と、設計§8の一時環境の試行は、その採用ではない。C-4の受領と「次の段階へ進んでください」を、S4-Aの実装承認にしない。S4-B以降・本番の承認も含まない。
