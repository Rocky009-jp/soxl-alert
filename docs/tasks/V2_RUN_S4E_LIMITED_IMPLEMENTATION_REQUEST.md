# V2 S4-E 本番接続 E-0（入口のコード） 限定実装依頼書

作成日：2026-11-05（日本時間）。版：**初版**。作成：Claude Opus 5.5、effort high。
状態：**初版・未採用**。設計§15のD-1〜D-10は採用されていない。限定実装は、採用の後に、別スレッドへの明示の着手指示で始める。本書の保存だけでは実装を始めない。
対になる設計はdocs/specs/V2_RUN_S4E_DESIGN_DRAFT.md（以下「設計」）。本書が頼むのは、設計§2のE-0だけである。中身は次の5つである。

- 入口のパッケージ`v2_run`：朝の実行・状態の確認・手動の再送・初期化・取得先の点検の5つのコマンドと、HTTPの取得とDiscordへの送信。
- 受領済みのパッケージの2か所の小さな変更：v2_notify/job.pyの1条件（S4-B実装レビューP-01）と、v2_inputs/load.pyの`fetch_count`（S4-D実装レビューP-01）。
- S4-Dの範囲試験のENDの固定（1行）と、E-0の範囲試験。
- workflowのひな形（docs/ops/、公開リポジトリでは動かない場所）。
- 利用者向けの手順書（docs/ops/、日本語）。

通信は試験の偽物（`urlopen`の差し替え）だけ、gitのリモートは一時ディレクトリのbareリポジトリだけを使う。非公開リポジトリの作成、workflowの追加・変更、秘密の登録、実際の取得・送信、試運転、本番の有効化（E-1〜E-5）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **9bdd4217d18e0ac328ddfa6a76b5d2a82748549d**（feat/v2-inputs-s4d-20261105、S4-Dの受領版） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-run-s4e-20261105）の設計とdocs/specs/V2_RUN_S4E_TRIAL_20261105.diff。SHAと3つのblobを開始報告に記録 |
| S4-Dの受領・実装レビュー | 受領記録43ebe559c4ebeae7ef437d270c8007ff5c928787、レビュー2fb6e21c77d5b8900375d86124c679847f3bf7b9 |
| S4-Dの設計（第2版、採用済み） | 263604b1448a39e68d4d1e53983bc55ef36d92ba |
| S4-Cの設計（採用済み）・受領 | 206054509e621ec5553ee389c3912c7112cc266a、受領記録5dc9cdc338b6d8d777e5758fcca32670ceae8c25 |
| S4-Bの提案の採否 | 9b4d786a14ab10ef5c0a2525191bf7b4753f4bbf（R2-P01） |
| S4の設計（第2版、採用済み） | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6（U-01・U-11・U-13） |
| 使う既存の部品 | 設計§1の表 |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、9bdd421から作る（ブランチ名の案：feat/v2-run-s4e-YYYYMMDD）。
  1. ユーザーが設計§15のD-1〜D-10を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-10）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-10を、採用されたと書かない。
- 実行環境のgitとPythonの版を開始報告に記録する。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_run/ 新規 | `__init__.py`、`__main__.py`、`entry.py`、`web.py`、`check.py`。5ファイルを超えない。分け方を変えたら結果文書に理由を書く |
| v2_notify/job.py | 設計§8の1条件（`judgment_known`の行）だけ |
| v2_inputs/load.py | 設計§8の`fetch_count`の代入の位置だけ（2行） |
| tests/v2_inputs/test_s4d_09_scope.py | 設計§12の`END`の1行だけ |
| tests/v2_run/ 新規 | test_s4e_\*.py、s4e_helpers.py、s4e_worker.py（S4E-14の子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/ops/ 新規 | V2_MORNING_WORKFLOW_TEMPLATE.yml（ひな形）、V2_PRIVATE_RUN_GUIDE.md（手順書） |
| docs/implementation/V2_RUN_S4E_RESULT.md 新規 | 本段階の結果 |

これ以外は変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local、v2_history_maintain、v2_daily_run、v2_git_store、v2_notify（上の1条件を除く）、v2_inputs（上の2行を除く）。
- 既存の試験・ヘルパー。新しいヘルパーからimportするのはよい。job.pyの変更で既存の試験の結果が変わる場合は、試験を直さずに止めて報告する。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09〜test_c4_09、test_s4a_09〜test_s4c_09、test_s4d_09（上の1行を除く）。
- 研究のデータ（research/）は読むだけ。設定・依存・`.github/`・main.py・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

次の範囲へ広げない。

- 実際のネットワーク（取得先・Discord・GitHub）への接続。試験も、試行も、手元の確認も、偽物の`urlopen`だけで行う。
- 公開リポジトリの`.github/workflows/`、Actions、秘密、通知先、mainの変更。非公開リポジトリの作成・変更。
- 受領済みの文面（v2_core/display.py、v2_daily_run、v2_notify/compose.py）とその試験の変更。見出しの置き換えは送信の関数の中だけで行う（設計§4）。
- 固定済みの市場データの値で欠けを埋める操作、休場日の表の変更、outboxの読込みの高速化（設計§7・§10で別の設計とした）。
- 前の段階の提案のうち、設計§8で「E-0で直す」としたもの以外の修正。
- 再試行、sleep、強制push、参照の削除、自動発注、口座への接続。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

1. **公開名**：`v2_run`から`main`、`Setup`、`MODES`、`make_fetch`、`DiscordSender`、`DrySender`、`split_text`、`live_text`を公開する。定数は`USER_AGENT`（`"Mozilla/5.0 (compatible; soxl-alert-v2)"`）、`FETCH_TIMEOUT`（30）、`SEND_TIMEOUT`（20）、`MAX_BYTES`（8×1024×1024）、`LIMIT`（1900）、`PREVIEW_HEAD`（`"【SOXL日次・ローカルプレビュー（実送信なし）】"`）、`LIVE_HEAD`（`"【詳細】"`）、`WEBHOOK_PREFIXES`（設計§4の2つ）、`SECRET_NAME`（`"V2_DISCORD_WEBHOOK_URL"`）、`REFUSED_JUDGMENT_EXISTS`。`main(argv, env=None, out=print, now_fn=<UTCの時計>, urlopen=urllib.request.urlopen)`は終了コード（整数）を返し、`__main__`は`sys.exit(main(sys.argv[1:]))`だけ。
2. **引数**：設計§3.1の5コマンドと、`--mode`（`dry`・`live`、必須）、`--workdir`（必須）、`--code-version`（40桁の小文字の16進。それ以外は記録に`unknown`）、`--date`（`status`・`resend`で必須、実在する`YYYY-MM-DD`）、`--kind`（`resend`で必須、v2_notifyの`KINDS`）、`--request-id`（`resend`で必須。形の検査はv2_notifyに任せる）、`--start-after`（`init`で必須、実在する`YYYY-MM-DD`）。引数の誤りは、gitも通信も使わずに0以外で終わる。
3. **1回だけ決める（R2-P01）**：`Setup`が設計§3.2の順に、時刻・`Git`・参照の名前・保存先・outbox・送信先・取得の関数を1回だけ作る。
   - 時計は1回だけ読み、その値を`load_inputs`と`morning_job`（または`resend`・`init`・`check-source`）に渡す。時計の関数そのものは、コミットの日時のために`GitHistoryStore`・`GitOutbox`・`load_inputs`の`clock`にだけ渡す。
   - `Git`は`--workdir`で1つ。outboxは`GitOutbox`を1つで、作業用の一時ディレクトリは実行の終わりに消す。
   - 参照の名前は設計§3.2の表のとおり。`dry`の実行は`v2-state`・`v2-outbox`・`v2-market`に触れず、`live`の実行は`v2-dry-*`に触れない。
   - 送信先は、`dry`が`DrySender`（外へ何も出さず、文面を保持して`SENT`と答える）、`live`が`DiscordSender(env.get(SECRET_NAME), urlopen)`。
4. **morning**：`load_inputs(git, fetch, now, {"market": …, "ledger": …}, clock)`→`guarded_store(store, inputs.failure)`→`morning_job(…, inputs.series, inputs.sessions, inputs.raw_observations)`。`load_inputs`がCoreError（`input_args_invalid`・`input_calendar_ended`）を投げたら、`morning_job(store, outbox, sender, now, None, None, [])`を呼んで予備の鍵のERRORを1通にし、記録に投げられたコードを書いて終了1（設計§3.5）。
5. **終了コード**（設計§3.4）：`morning`は配達が`SENT`・`SKIPPED_CLAIMED`・`SKIPPED_JUDGMENT_EXISTS`のときだけ0（判定なしが送れた朝も0）。`NOT_SENT`・`UNKNOWN`・`CLAIM_FAILED`・`RESULT_NOT_RECORDED`、`load_inputs`が投げた場合、入口の例外は1。`JobReport.exit_code`は使わない。`resend`は`SENT`のときだけ0。`status`は読めたら0。`init`は§3の8。`check-source`は4記号の取得がすべて通ったら0。
6. **status**：`outbox_status(outbox, date)`の各行（鍵、再送のid、状態、時刻）を記録に書く。何も作らない・変えない。
7. **resend**：`kind`がHALT・ERRORで、同じDのMORNINGの状態が`NONE`でなければ、送らずに`REFUSED_JUDGMENT_EXISTS`を記録して終了1（S4-B実装レビューP-02）。ほかは`resend(outbox, sender, d, kind, request_id, now)`の結果をそのまま記録する。
8. **init**（設計§13のT-2、本書で加えるT-5）：
   - `--start-after`の日が、表のセッションで`now`までに閉じたものでなければ、何も書かずに終了1。
   - 履歴の参照と、outboxの参照を、**それぞれ無いときだけ**作る。履歴は`publish_genesis(start_after, build_sessions(now, start_after))`を`GitHistoryStore.initialize`で、outboxは`GitOutbox.initialize`で。あるものは変えず、`EXISTS`と記録する（片方だけ作れた後の再実行で、残りを作れるようにする。試行の下書きは履歴が先にあると例外で止まり、outboxを作れなかった）。
   - 両方が揃ったら0、どちらかを作れなければ1。市場データの固定と台帳には書かない。
9. **check-source**（設計§7）：書き込まない（4つの参照の先頭が実行の前後で同じ）。
   - 4記号を、`load_inputs`と同じ引数（`PREHISTORY_START`、`now`のニューヨークの日付の翌日）で1回ずつ取得する。試行の下書きはUTCの日付の翌日だった。揃える。
   - 記号ごとに、少なくとも次の事実を記録する：応答の形（JSONの形・列の長さ・`meta.symbol`）、行数、最初と最後の日付、ニューヨークの時刻の分布、同じ日付（直近）、対象Dの行の数、2026-01-02以後の表の日で行が無い・`null`の日の数と例、`null`の行の数、2026年より前の研究のデータとの日付の差（応答だけ・研究だけ）、モードの固定（`MarketPin`）との差（最後の日の終値が変わったか、それより前の終値が変わった日の数、調整後終値の日次の騰落率の差の最大）。
   - 研究のデータはresearch/SOXL_initial_trend_20261023/data/から読むだけ。
10. **取得**（設計§5）：`make_fetch(urlopen)`の`fetch(symbol, start, end)`は、`chart_url(symbol, start, end)`へ`User-Agent`・`Accept: application/json`付きで、時間切れ`FETCH_TIMEOUT`で1回だけ開く。状態200以外、`MAX_BYTES`を超える応答、ほかの例外は、例外にする（例外の文字列に、URL・応答の本文を入れない）。再試行しない。
11. **送信**（設計§4）：`DiscordSender.send(text)`は、URLが`WEBHOOK_PREFIXES`で始まるASCIIの文字列でなければ、通信せずに`NOT_STARTED`。そうでなければ、`live_text(text)`を`split_text`で分け、各部分を`POST <URL>?wait=true`（`Content-Type: application/json`、本文は`{"content": 部分, "allowed_mentions": {"parse": []}}`のUTF-8、時間切れ`SEND_TIMEOUT`）で1回ずつ順に送る。答えは設計§4の表のとおり。失敗した部分の後は送らない。再試行しない。`repr`・例外・記録にURLを出さない。
12. **分けと見出し**：`split_text`は、`LIMIT`以下の文面をそのまま1つにし、超える文面を行の境目で分けて各部分の先頭に`（n/N）`と改行を付ける。`LIMIT`を超える1行は途中で切る。どの部分も2000文字以下。`live_text`は`PREVIEW_HEAD`を`LIVE_HEAD`へ置き換えるだけ。outboxに残る文面と`text_sha256`は置き換える前のもの。`DrySender`は置き換えない。
13. **実行の記録**：`out`へ書き、環境の`GITHUB_STEP_SUMMARY`があればそのファイルへ追記する。
    - 書くもの：コマンド、モード、`now`（UTC、秒まで）、`code_version`、Pythonの版、gitの版、各コマンドの結果（`morning`では入力の失敗のコードと日付、`provenance`の各キー、`run_outcome`、鍵、配達、`send_status`、`existing_status`、コード、消費したD、`history_digest`の先頭12桁、`seconds.load_inputs`・`seconds.morning_job`・`seconds.outbox_load`（1回の読込み）、`outbox_files`）、終了コード。
    - `dry`の`morning`では、送ったはずの文面を1つのブロックとして書く。`live`では文面を書かない。
    - 書かないもの：パス、URL、秘密、例外の文字列、gitの出力、応答の本文。例外は型の名前と、`code`属性が文字列ならその値だけ。
14. **環境変数**：読むのは`V2_DISCORD_WEBHOOK_URL`（`live`のときだけ）と`GITHUB_STEP_SUMMARY`だけ。`main`の`env`の既定値として`os.environ`を読むのは`main`だけで、ほかは渡された`env`を使う。
15. **job.pyとload.py**（設計§8）：job.pyは`judgment_known`の条件にERRORを加える1行だけ（`notice.kind in (HALT, ERROR)`）。load.pyは`provenance["fetch_count"]`の代入を、取得の後・失敗の判定の前へ移すだけ（取得で失敗した場合も、それまでの回数が残る）。ほかの行を変えない。
16. **importと呼出し**：`urllib`・`socket`・HTTPは`web.py`だけ。`datetime.now`は`entry.py`の時計の関数1か所だけ。`os.environ`は`main`の1か所だけ。`subprocess`・`threading`・`random`・`zoneinfo`・`http.client`を直接使わない（gitは`Git`を通す）。`time`は`monotonic`だけ（`sleep`を使わない）。他のパッケージのオブジェクトの`_`で始まる属性を使わない。`raise`を`except`の本体の中に書かない（素の`raise`を除く）。
17. **ひな形**（設計§6）：docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.ymlは、設計§6.1の要点を満たすYAMLとする。
    - cronは`40 22 * * 1-5`と`40 23 * * 1-5`、`workflow_dispatch`の入力（command・date・kind・request_id・start_after）。
    - `permissions`は`contents: write`だけ。`concurrency`は`group: v2-writer`、`cancel-in-progress: false`。`timeout-minutes: 30`、`runs-on: ubuntu-24.04`。
    - `env`に`V2_MODE: dry`と`V2_CODE_SHA`（40桁の置き場所。値は`0`の40個などの明らかな仮の値）。
    - `actions/checkout`は`@`の後に40桁のSHAの置き場所（仮の値と「E-2で公式のリリースのSHAを確かめて書く」の注記）。非公開リポジトリは`persist-credentials: true`、公開リポジトリは`ref: ${{ env.V2_CODE_SHA }}`・`persist-credentials: false`。
    - `run`の行は`python3 -E -B -m v2_run`で、`${{ inputs.* }}`・`${{ github.event.* }}`を`run`の行に直接書かない（入力はすべて`env`経由）。秘密の行を含めない（E-4で足す行は、注記で示すだけ）。
18. **手順書**：docs/ops/V2_PRIVATE_RUN_GUIDE.mdは、設計§11の11項目を、Rockyさんが読んで操作できる日本語で書く。台帳の始め方（非公開リポジトリのウェブで`v2-ledger`のブランチを作り、見出しの1行だけの`observations.csv`を置く。見出しだけの台帳はS4-Dの読込みを通る）と、E-1〜E-5の各段階で確かめることの一覧を含める。秘密の値・実在のWebhookのURL・個人の口座の情報・ローカルのパスを含めない。手順書の操作は、承認された段階でだけ行うと明記する。

## 4. 受入条件 S4E-01〜S4E-18

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、研究のfixture（`load_research_fixture`）、試験側で`git`を直接呼んで読んだバイト、偽の`urlopen`が受け取った要求の記録から作る。実装の出力をコピーしない。チャートの応答は研究のデータ（daily.json・daily_adjclose.csv）から試験のヘルパーで作ったchart APIの形のバイト列、Discordは状態を選べる偽物（2xx・4xx・5xx・接続の拒否・名前の解決の失敗・時間切れ）。リモートはすべて一時ディレクトリのbareリポジトリで、パスに印（例：`SECRETPATH_`）を入れる。WebhookのURLにも印（例：`https://discord.com/api/webhooks/1/SECRETTOKEN_x`）を入れる。

| ID | 必須確認 |
|---|---|
| S4E-01 回帰 | 既存の19スイート計2,728件を、完全なクローンで維持する（S4-Cまでの18スイート2,598件とS4-D 130件）。test_s4d_09の1行の固定と、job.py・load.pyの変更を含めて、件数・結果が同じ |
| S4E-02 1回だけ決める | (a) 1回の`morning`で、`load_inputs`と`morning_job`に渡る`now`が同じ値で、時計の関数を`now`のために読むのは1回。(b) `Git`・outboxが1つずつで、`morning_job`・`resend`・`outbox_status`に同じoutboxが渡る（R2-P01）。(c) `dry`の実行の後、試験側で読んだリモートの`v2-state`・`v2-outbox`・`v2-market`が無い（または変わらない）。`live`の実行の後、`v2-dry-*`が変わらない。(d) 作業用の一時ディレクトリが終わりに消える |
| S4E-03 init | (a) 閉じたセッション→履歴INITIALIZED・outboxの印・終了0、試験側で読んだgenesisの境界が`--start-after`。(b) 閉じていない日・表に無い日・形の違う日→何も書かずに終了1。(c) 履歴だけがある状態からの再実行→履歴は変わらず`EXISTS`、outboxを作って終了0（T-5）。(d) 両方ある状態の再実行→何も変えず終了0。(e) 市場データの固定と台帳の参照を作らない |
| S4E-04 試運転の通し | `init --mode dry`の後、5回の朝（引けから60分以上の時刻）で毎回DONE・判定ありSENT・終了0。偽の`urlopen`にDiscordへの要求が0件。記録に文面のブロックと出所・時間。同じ朝の2回目はSKIPPED_CLAIMED・終了0。同じ5回を`load_research_fixture`の系列で直接走らせた場合と、各日の`run_outcome`と判定が一致 |
| S4E-05 入力の失敗 | (a) 取得の失敗（例外・状態500・8MBを超える応答）、引けの後に対象Dの行が2つ（S4-D再レビューR-02）、表の日の穴、台帳の誤り→STOPPED（そのコード）・`<D>-halt`の判定なしSENT・終了0。形が戻った同じ朝の後の実行→DONE・判定ありSENT。(b) `load_inputs`が投げる場合（`input_calendar_ended`）→予備の鍵のERRORが1通、記録に投げられたコード、終了1 |
| S4E-06 送信の答え | 設計§4の表の各行（2xx→SENT、最初の部分の400・401・404・429→NOT_STARTED、接続の拒否・名前の解決の失敗→NOT_STARTED、500・503・時間切れ・ほかの例外→UNKNOWN、2つ目以降の部分の失敗→UNKNOWN）。どの場面も各部分の要求は1回だけ（再試行なし）で、失敗の後の部分は送らない。URLが無い・`http://`・別のホスト・ASCIIでない→要求0件でNOT_STARTED。`live`の朝の配達がNOT_SENT・UNKNOWNのとき終了1、同じ朝の2回目はSKIPPED_CLAIMED（自動で送り直さない） |
| S4E-07 分けと見出し | (a) 1900文字ちょうどは1つ、1901文字は2つ。(b) 各部分の先頭が`（n/N）`、どの部分も2000文字以下、部分をつなぐと元の文面の行が順に揃う。(c) 1900文字を超える1行も2000文字以下に切れる。(d) `live`で送った本文に`PREVIEW_HEAD`が無く`LIVE_HEAD`がある。outboxに残る文面と`text_sha256`は置き換える前。再送の本文も置き換わる。`dry`の記録の文面は置き換わらない |
| S4E-08 要求の形 | 送信：`POST`、URLの末尾`?wait=true`、`Content-Type: application/json`、`User-Agent`、本文のJSONのキーが`content`と`allowed_mentions`だけで、`allowed_mentions`が`{"parse": []}`、時間切れ20。取得：URLが`chart_url`の文字列そのもの、`User-Agent`、時間切れ30、4記号を1回ずつ、引数の`end`が`now`のニューヨークの日付の翌日（日本時間の朝とニューヨークの夕方で同じ日になる例を含める） |
| S4E-09 取得の上限 | 8MBちょうどは通り、8MB＋1バイトは例外。状態200以外は例外。例外の文字列・`repr`に、URL・応答の本文が出ない |
| S4E-10 予備の鍵（S4-B P-01） | 同じ日付のMORNINGが判定ありの状態で、セッションなしの朝（予備の鍵のERROR）→`SKIPPED_JUDGMENT_EXISTS`、送信0件。対照として、job.pyの変更を戻すと送信を試みることを、結果文書に記録する（試験には残さなくてよい） |
| S4E-11 fetch_count（S4-D P-01） | 応答の形の誤り・値の誤りで止まった朝の`provenance["fetch_count"]`が、実際の取得の回数（4）。取得の例外で止まった朝は、例外までの回数 |
| S4E-12 再送と状態 | (a) 判定ありがUNKNOWNの朝の`resend --kind morning`→SENT・終了0、`status`に元のUNKNOWNと再送のSENT。(b) 同じDのMORNINGがNONE以外の朝の`resend --kind halt`・`--kind error`→REFUSED_JUDGMENT_EXISTS・送信0件・終了1。MORNINGがNONEの日の判定なしの再送は通る。(c) 同じidの2回目はS4-Bの答えのまま。(d) CLAIM_FAILED（S4-Cの試験の方法でoutboxのpushを拒む）→終了1、記録に`CLAIM_FAILED`、送信0件 |
| S4E-13 check-source | (a) 通常の応答→設計§13のC1の事実（行数、最初の日、時刻の分布、対象Dの行1、表の日の欠け0、研究との差0、固定との差0）。(b) 対象Dの行が2つ→`target_rows=2`と、その日付。(c) 固定した最後の日の終値が違う＋SPYの表の日が1つ欠ける→終値の変化、騰落率の差、欠けの数と日付。(d) どの場面も、実行の前後で4つの参照の先頭が同じ。(e) 1記号の取得の失敗→その記号に失敗の型の名前、終了1 |
| S4E-14 同時の実行 | 子プロセス2〜4個で各10回以上、同じDの`morning --mode live`（偽のDiscord）を同時に走らせ、Discordへの判定ありの投稿が1回まで、固定のsha256が1つ。回数と結果を結果文書に記録する（concurrencyのグループが効かない場合の保険の確認） |
| S4E-15 記録と機密 | (a) S4E-02〜14の全場面で、記録（`out`とGITHUB_STEP_SUMMARYのファイル）に、パスの印・URLの印・`http`の文字列・例外の文字列が無い。(b) 例外は型の名前と固定のコードだけ。(c) Pythonの版・gitの版・`code_version`（40桁でなければ`unknown`）が記録にある。(d) GITHUB_STEP_SUMMARYへは追記で、前の中身が残る。(e) `env`に`V2_DISCORD_WEBHOOK_URL`があっても、`dry`では読まず、偽の`urlopen`へ要求を出さない |
| S4E-16 測定 | 結果文書に、(a) outboxのファイル数1・751・1,501での1回の読込みの時間、(b) genesisを2026-01-02にした149セッションの追いつきの`seconds.morning_job`と、続く2回目の時間、(c) 通常の朝の`seconds.*`を記録する（設計§10の試行と比べる。閾値を超えたら報告する） |
| S4E-17 静的な範囲 | §3の16のimportと呼出しの規則。ひな形（§3の17）をYAMLの文字列として検査する：cronの2行、`concurrency`のグループと`cancel-in-progress: false`、`permissions`が`contents: write`だけ、`actions/checkout@`の後が40桁、`run`の行に`${{ inputs.`・`${{ github.event.`が無い、`secrets.`の行が無い、`timeout-minutes: 30`、`python3 -E -B -m v2_run`。手順書に`https://discord.com/api/webhooks/`の後に続く値・ローカルのパスが無い |
| S4E-18 範囲試験 | 新しい範囲試験（START＝9bdd421、END＝None、REV＝END or "HEAD"、FilesChanged）が、§2の変更だけを許す。test_s4d_09・job.py・load.pyの差分を、自分の差分のハンクとして固定する。範囲の鎖が`…→ffa3700→9bdd421→（S4-E）`で通る。ENDだけを固定して開いた範囲を外すと鎖の試験が失敗する手順を、結果文書に記録する |

## 5. 限定欠陥注入

1件ずつ壊して試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. 時計を2回読む（`load_inputs`と`morning_job`に違う`now`を渡す）。
2. `dry`で本番の参照（`v2-state`等）を使う。
3. `dry`で`DiscordSender`を使う（または`DrySender`が外へ出す）。
4. 最初の部分の4xxを`UNKNOWN`にする。
5. 2つ目以降の部分の失敗を`NOT_STARTED`にする。
6. 失敗した部分を1回送り直す。
7. `allowed_mentions`を外す。
8. 見出しを置き換えない（または、outboxに残る文面を置き換える）。
9. 分ける上限を2000にする（`（n/N）`の分で2000を超える）。
10. URLの形の検査を外す。
11. 取得で状態200以外を受け付ける。
12. 取得の8MBの上限を外す。
13. 判定なしがSENTの朝を終了1にする（または、UNKNOWNの朝を終了0にする）。
14. HALT・ERRORの再送の入口の拒否を外す。
15. job.pyの変更を戻す。
16. load.pyの変更を戻す。
17. 記録に例外の文字列を書く。
18. `init`で閉じていない日を受け付ける（または、履歴があるとoutboxを作らない）。
19. `check-source`が固定の参照に書く（`load_inputs`を呼ぶ）。
20. `load_inputs`が投げたとき、`morning_job`を呼ばない（通知が0通）。
21. 取得・送信の時間切れを渡さない。
22. ひな形の`cancel-in-progress`を`true`にする（または`concurrency`を外す）。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する（Actionsのubuntu-24.04は3.12、利用者のPCは3.10.6）。gitの版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 試験は一時ディレクトリの中だけでbareリポジトリとクローンを作る。ネットワークを使わない（偽の`urlopen`だけ。実際の`urlopen`が呼ばれたら失敗する仕掛けを試験に入れる）。試験側のgitの呼出しにも`-c`で必要な設定を渡す。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴）で試験する。
- **全スイートと欠陥注入は、試験対象のコミットそのもので行う**（S4-D実装レビューP-04）。途中の版の結果を記録に使うなら、その版をpushするか、試験対象で再実行する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、新規Nと、S4-D 130、S4-C 118、S4-B 131、範囲の鎖34を実行する。実Windowsで行うまで未実施と書く。ユーザーPC・物理電源断・GitHubのリモート・非公開リポジトリ・Actions・実際の取得先・実際のDiscordは未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_run -p "test_s4e_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。gitとPythonの版。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- ランタイムの全文の場所と行数。job.py・load.py・test_s4d_09の差分の全文。
- 試行の下書き（設計§13）との違いと、その理由（少なくともT-5の`init`、`check-source`の`end`の日付、Pythonの版の記録）。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。S4E-10の対照の結果。
- S4E-14の回数と結果、S4E-16の測定、S4E-18の手順と結果。
- 記録の例（`dry`の`morning`・`live`の`morning`・`status`・`check-source`の各1つ。印を伏せる）。
- ひな形と手順書の要点（ファイルの場所と行数）。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験・ひな形・手順書をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・非公開リポジトリの作成・GitHubへの状態のpush・実際の取得・実際の送信・E-1以降へは進まない。

## 7. 読取専用の保護参照

次の109参照を、開始時と保存・push後に完全SHAで照合する。S4-Dの依頼書の104参照に、S4-Dの資料（採用記録263604b）・実装レビュー・レビュー・再レビュー・実装（受領版9bdd421）の5本を加えたものである。実装時は、本書と設計を保存した資料ブランチdocs/v2-run-s4e-20261105の受け取った版（採用記録のコミット）を1本加える。設計・依頼書へのレビュー・再レビューの資料ブランチがあれば、その受け取った版も加える（加えた本数と合計を結果文書に書く）。

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
| docs/v2-s4-daily-run-20261104 | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6 |
| docs/v2-s4-daily-run-review-20261104 | dd60f6f22d773561cfcc3ab09c868e02d9d0a973 |
| feat/v2-daily-run-s4a-20261104 | 6ad609fe52b50565103e56c598505cac85601216 |
| docs/v2-daily-run-s4a-impl-review-20261104 | 3e3fd475a486a26eb9fd234e11c4950a04e55102 |
| docs/v2-notify-s4b-20261105 | 4c54e01b218148e49e5ae283e7f0bf2fc52edb46 |
| docs/v2-notify-s4b-fix-rereview-20261105 | 77e9cf87c7eefb0741ed17eab5658a1da1f15032 |
| docs/v2-notify-s4b-fix2-rereview-20261105 | 9b4d786a14ab10ef5c0a2525191bf7b4753f4bbf |
| docs/v2-notify-s4b-impl-review-20261105 | 1f914f982a684253cba6726489d43408aeda5e79 |
| docs/v2-notify-s4b-review-20261105 | 1122052fb15d9e6de516fb9be9aea90bc48f3842 |
| docs/v2-notify-s4b-v2-rereview-20261105 | f10e719e05344379f370860d424b66dc01c0ea6a |
| feat/v2-notify-s4b-20261105 | 6cab0506c408d194c63b656713e4a0a7d62c3ba1 |
| docs/v2-git-store-s4c-20261105 | 206054509e621ec5553ee389c3912c7112cc266a |
| docs/v2-git-store-s4c-impl-review-20261105 | 8ffa76285fe7bcc1d9af5dc717474aee004fda35 |
| docs/v2-git-store-s4c-review-20261105 | 55e770a0457d17e91a6d3e8074d53c0f3ce73372 |
| docs/v2-git-store-s4c-v2-rereview-20261105 | 3d2b79af5c6f8919bde04dd6e071628bc562f083 |
| feat/v2-git-store-s4c-20261105 | ffa370089cd37fcc76658b4de0f4aedde0a246e0 |
| docs/v2-inputs-s4d-20261105 | 263604b1448a39e68d4d1e53983bc55ef36d92ba |
| docs/v2-inputs-s4d-impl-review-20261105 | 9e03325849c9b7723eb385ef4e77311dde0ec140 |
| docs/v2-inputs-s4d-review-20261105 | 33894b254c0967cecd69c7efbccc7db8001926f6 |
| docs/v2-inputs-s4d-v2-rereview-20261105 | 04acf137294fcfb681356e9562aec79bb8d71fe0 |
| feat/v2-inputs-s4d-20261105 | 9bdd4217d18e0ac328ddfa6a76b5d2a82748549d |

本書の作成時（2026-11-05、日本時間）に、上の109参照がリモートと完全SHAで一致することを、作業の開始時に確かめた。資料ブランチのpush後の照合は、下の追記に記す。

## 8. 採用単位

設計§15のD-1〜D-10と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。

- D-1：S4-Eの分け方（E-0だけがコード。E-1〜E-5は各段階の直前に別の承認）。
- D-2：入口（5コマンド、1回だけ決める、試運転と本番で参照を分ける、終了コード、`init`は参照ごとに無いときだけ作る）。
- D-3：送信（Discord Webhook、答えの対応表、1900文字で分ける、送る直前の見出しの置き換え）。
- D-4：取得（urllib、30秒、8MB、再試行なし）。
- D-5：workflowのひな形（concurrency、資格情報、40桁の固定、時刻、30分）。
- D-6：試運転の合否の11項目。
- D-7：前の段階の提案（job.pyの1条件とload.pyの`fetch_count`はE-0で直す。ほかは入口・手順書・E-3の基準）。
- D-8：手順書。
- D-9：S4-Dの範囲試験のEND固定。
- D-10：担当（Sonnet 5.5・high）。

設計§13の一時環境の試行は、実装ではない。S4-Dの受領と「S4-Eへ進めて」を、E-0の実装承認にしない。非公開リポジトリの作成・workflowの追加・秘密の登録・試運転・実送信・本番の有効化・mainの変更も含まない。
