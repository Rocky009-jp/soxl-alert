# V2 S4-D 朝の実行の入力（セッション・市場データ・台帳） 限定実装依頼書

作成日：2026-11-05（日本時間）。版：**第2版**（初版fad0f5bへのレビュー33894b2の通常N-01と提案P-01を反映。§2、§3の2・5・7・8、S4D-05(g)・S4D-12(d)、欠陥注入21・22、§7・§8。ほかは初版と同じ）。作成：Claude Opus 5.5、effort high。
状態：**第2版・D-1〜D-10採用済み**（Rocky「推奨どおり」2026-11-05T11:07Z、再レビュー04acf13の推奨。設計§16）。限定実装は、別スレッドへの明示の着手指示で始める。本書の保存だけでは実装を始めない。再レビューの任意提案R-01（欠陥注入21の等価）とR-02（S4-Eの試運転の確認項目）は設計§16のとおり扱い、R-01は結果文書に書く。
対になる設計はdocs/specs/V2_INPUTS_S4D_DESIGN_DRAFT.md（以下「設計」）。本段階はS4-Dだけを実装する。中身は次の4つである。

- XNYSのセッションを表と夏時間の規則から作る`xnys.py`。
- 市場データの応答の解釈と、参照`v2-market`への系列の固定`market.py`。
- 参照`v2-ledger`の台帳の読込み`ledger.py`。
- 3つをまとめ、入力の失敗を値で返す`load.py`（`load_inputs`・`guarded_store`）。

市場データは研究のfixtureから作った応答の形のバイト列、gitのリモートは一時ディレクトリのbareリポジトリだけを使う。HTTPの取得そのもの、ネットワーク、GitHub、非公開リポジトリ、資格情報、入口のスクリプト・workflow・秘密・本番（S4-E）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **ffa370089cd37fcc76658b4de0f4aedde0a246e0**（feat/v2-git-store-s4c-20261105、S4-Cの受領版） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-inputs-s4d-20261105）の設計とdocs/specs/V2_INPUTS_S4D_TRIAL_20261105.diff。SHAと3つのblobを開始報告に記録 |
| S4-Cの受領・実装レビュー | 受領記録5dc9cdc338b6d8d777e5758fcca32670ceae8c25、レビューc8666713c0e82724bf8c158d8166c11dcc10787f |
| S4-Cの設計（第2版、採用済み） | 206054509e621ec5553ee389c3912c7112cc266a |
| S4の設計・依頼書（第2版、採用済み） | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6（§6.3、D-6） |
| 上位の保存・復旧の設計 | e3e9094 §2.3（U-07）、§4.2 E-10・E-13（U-06） |
| 使う既存の部品 | v2_core（errors、sessions、fixture）、v2_git_store（`Git`、`GitError`、`OK`） |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、ffa3700から作る（ブランチ名の案：feat/v2-inputs-s4d-YYYYMMDD）。
  1. ユーザーが設計§13のD-1〜D-10を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-10）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-10を、採用されたと書かない。
- 実行環境のgitの版（`git --version`）を開始報告に記録する。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_inputs/ 新規 | `__init__.py`、`xnys.py`、`market.py`、`ledger.py`、`load.py`。5ファイルを超えない。分け方を変えたら結果文書に理由を書く |
| tests/v2_git_store/test_s4c_09_scope.py | 設計§10.1の`END`の1行だけ |
| tests/v2_inputs/ 新規 | test_s4d_\*.py、s4d_helpers.py、s4d_worker.py（S4D-13(d)の子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_INPUTS_S4D_RESULT.md 新規 | 本段階の結果 |

これ以外は変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local、v2_history_maintain、v2_daily_run、v2_notify、**v2_git_store**。
- 既存の試験・ヘルパー。新しいヘルパーからimportするのはよい。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09〜test_c4_09、test_s4a_09、test_s4b_09、test_s4c_09（上の1行を除く）。
- 研究のデータ（research/）は読むだけ。設定・依存・workflow・main.py・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

次の範囲へ広げない。

- HTTPの取得（URLを開く、ソケット、プロキシ、User-Agent、再試行、時間切れ）。ネットワーク越しのgit。GitHubのAPI。資格情報・トークン・環境変数の読込み。入口のスクリプト・CLI・workflow。
- 台帳への書込み（ランナーは読むだけ）。休場日の表を、設計§4.1の表と違う内容にすること（表はICEの公式発表と照合済み。直す必要を見つけたら、直さずに止めて報告する）。
- 時計の読込み、sleep、時間を置いた再試行、強制push、参照の削除。
- 受領済みのパッケージの変更。前の段階の提案（S4-B実装レビューP-01等、設計§10.2）の修正。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

1. **公開名**：設計§9の表のとおり（`load_inputs`、`Inputs`、`guarded_store`、`build_sessions`、`coverage_failure`、`chart_url`、`parse_chart`、`MarketPin`、`read_ledger`）。ほかに定数`SYMBOLS`（`("SOXX", "SPY", "IEF", "SOXL")`）、`PREHISTORY_START`（`"2010-02-11"`）、`PRICE_MAX`（`1000000`）、`CALENDAR_START`・`CALENDAR_END`、`MARGIN_DAYS`（14）、`CLOSE_MARGIN`（60分）。
2. **誤りの形**：誤りはすべてv2_coreの`InputError(code, field, detail=…)`である。detailは日付（`YYYY-MM-DD`）か無しで、ほかの文字列（パス、URL、応答の本文、gitの出力、利用者の行の値）を入れない。コードと項目名は次の表だけ。

   | コード | 項目名 | 返すか投げるか | 場面 |
   |---|---|---|---|
   | `input_args_invalid` | `inputs` | 投げる（gitも取得も呼ばない） | `now`が時刻帯つきのdatetimeでない、`refs`が`market`・`ledger`の2つの参照名（v2_git_storeの参照の形）でない、`fetch`・`clock`が呼べない、`chart_url`の記号が`SYMBOLS`に無い |
   | `input_calendar_ended` | `calendar` | 投げる | `now`のUTCの日付が`CALENDAR_END`より後（設計§4.2） |
   | `input_calendar_not_covered` | `calendar` | 返す | `now`＋14日が`CALENDAR_END`より後 |
   | `input_market_fetch_failed` | `market` | 返す | `fetch`が例外を出した |
   | `input_market_response_invalid` | `market` | 返す | 応答がbytesでない、UTF-8・JSONでない、形が違う、`meta.symbol`が違う、列の長さが違う、時刻が整数でない、対象Dまでの行に同じ日付が2つ |
   | `input_market_value_invalid` | `market` | 返す（detail＝最初の日付） | 対象Dまでの行の値が有限の正の数でない、または`PRICE_MAX`以上（boolは数でない） |
   | `input_market_history_short` | `market` | 返す（detail＝`2010-02-11`） | SOXXに`PREHISTORY_START`の行が無い（系列の始まりが変わるとRSIが変わる。設計§5.1） |
   | `input_calendar_data_mismatch` | `market` | 返す（detail＝その日） | `CALENDAR_START`以後・対象Dまでに、表の全セッション（閉じていないものを含む）に無い日のSOXX・SPY・IEFの行がある |
   | `input_market_rows_missing` | `market` | 返す（detail＝穴の日） | 表の閉じたセッションに、4記号が揃わない日があり、その後に揃った日がある |
   | `input_market_pin_invalid` | `market` | 返す | 固定の参照に`market.json`が無い・形式が違う |
   | `input_market_pin_failed` | `market` | 返す | 固定のpushが通らず、読み直した固定が自分の日まで届いていない |
   | `input_market_unavailable` | `market` | 返す | 固定が無く、揃った日も無い |
   | `input_ledger_missing` | `ledger` | 返す | 参照または`observations.csv`が無い |
   | `input_ledger_unreadable` | `ledger` | 返す | UTF-8でない、CSVとして読めない、空 |
   | `input_ledger_header_invalid` | `ledger` | 返す | 見出しが設計§6の6列・この順でない |
   | `input_ledger_row_invalid` | `ledger` | 返す | 列の数が違う行 |
   | `input_ledger_observation_after_now` | `observed_at_iso8601` | 返す | 読める`observed_at`が`now`より後 |
   | `input_git_failed` | `inputs` | 返す | `Git`の操作が`GitError`を出した。`GitError`はCoreErrorの子なので、ほかのCoreErrorより先に捕まえて置き換える（`git_failed`のまま返さない。設計T-7） |

3. **例外の連鎖**：例外の処理の中で新しい例外を投げない。値を作って処理の外で投げ、`InputError`の`__context__`・`__cause__`をNoneにする（S4-Cの§3の7と同じ）。
4. **時刻**：`load_inputs`は時計を読まない。`now`だけを使い、`clock`はコミットの日時にだけ使う。夏時間は設計§4.1の規則（3月の第2日曜日から11月の第1日曜日の前日まで−4時間、ほかは−5時間）で、zoneinfo・tzdataを使わない。
5. **セッション**：設計§4.1の表と時刻。`build_sessions(now, confirmed_through)`は、表の全セッション（`CALENDAR_START`から）を返し、`confirmed`は`confirmed_through`以下の日だけ。表の内容から`calendar_sha256`（表の正規の文字列のsha256。文字列の作り方は結果文書に書く）を作る。表の横に、出典（ICEの発表「NYSE Group Announces 2026, 2027 and 2028 Holiday and Early Closings Calendar」、2025-12-23）と照合の日付（2026-11-05、レビュー33894b2）を注記する（設計§4.1）。
6. **取得**：`load_inputs`は、固定の`through`が対象D（`now`までに閉じた最後のセッション）より前のときだけ、4記号それぞれについて`fetch(symbol, PREHISTORY_START, end)`を1回ずつ呼ぶ。`end`は`now`のニューヨークの日付の翌日（`YYYY-MM-DD`）。`chart_url(symbol, start, end)`は、`https://query1.finance.yahoo.com/v8/finance/chart/<記号>?period1=<startの0時UTCの秒>&period2=<endの0時UTCの秒>&interval=1d&events=div%2Csplit&includeAdjustedClose=true`を返す純粋な関数で、`load_inputs`は呼ばない（S4-Eの取得の関数が使う）。
7. **解釈**：設計§5.2。`parse_chart(data, symbol, through=None)`。日付は時刻（UTCの秒）をニューヨークの日付にしたもの。**`through`より後の日付の行は、同じ日付・値の検査よりも前に捨てる**（固定しない、誤りにもしない。第2版N-01）。`load_inputs`は`through`に対象Dを渡す。`null`の日は行を作らない。`PREHISTORY_START`より前の行は捨てる。
8. **揃った最後の日**：設計§5.3。表の閉じたセッションを古い順に見て、引けから60分以上たち、4記号が揃った日。60分に満たない日で止まる。表との照合（`input_calendar_data_mismatch`）は、閉じたセッションだけでなく表の全セッションに対して行う（第2版N-01）。
9. **固定**：設計§5.3。
   - `market.json`は、キーを並べた正規のJSON（`sort_keys`、区切り`,`・`:`、ASCII）で、`schema`＝`v2_inputs.market.1`、`through`、`source`＝`yahoo_chart_v8`、記号ごとの`dates`・`close`・`adjclose`（`PREHISTORY_START`以上、`through`以下）。同じ内容は同じバイト。
   - 揃った最後の日が固定の`through`より後のときだけ、`Git.commit_with`で親＝固定の先頭（無ければ親なし）の木の`market.json`を置き換えるコミット（`replace=True`、メッセージは固定の語と`through`の日付だけ）を作り、`Git.push`で送る。
   - 後でなければ、取得したものは使わず固定済みを使う。
   - `OK`以外（REJECTED・UNCERTAIN）は固定を読み直し、`through`が自分の日以上ならそれを使う（`pinned_by`＝`other`。UNCERTAINで自分のものが届いていた場合も、読み直した版を使う）。届いていなければ`input_market_pin_failed`。繰り返さない。
   - 系列は、つねに固定から読み直したバイト（または自分がpushしたバイトそのもの）から作る。
10. **系列**：`MarketSeries`の`dates`はSOXXの日付、値はSOXXの`adjclose`、`spy`・`ief`は`adjclose`、`market_dates`はSPYとIEFの両方がある日、`soxl_close`はSOXLの`close`。meta の`price_definition`・`soxl_close_definition`はv2_coreの定数、`input_manifest`は`market.json`のsha256。
11. **台帳**：設計§6。値は前後の空白を除いた文字列のままcoreへ渡し、数・時刻に変えない。空の行は捨てる。BOM・CRLFを受け付ける。読めない`observed_at`はcoreに任せる。`observed_at`が`now`と同じ時刻は受け付ける。
12. **失敗の包み**：設計§7。`load_inputs`は§3の2の「返す」誤りを`Inputs.failure`に入れ、そのときも`sessions`を返す（`confirmed`は、読めた固定の`through`まで。読めなければすべて未確定）。`series`はNone、`raw_observations`は空。`guarded_store`の包みは、`read()`で失敗を投げ、`publish`・`reconcile`は元の保存先の結果をそのまま返す。
13. **出所**：`Inputs.provenance`は辞書で、キーは`calendar_sha256`、`market_through`、`market_sha256`、`market_commit`、`pinned_by`（`this`・`other`・`existing`）、`fetch_count`、`ledger_commit`だけ。値は文字列か整数。失敗のときは、そこまでに決まったキーだけ。
14. **importと呼出し**：ランタイムのimportは、標準ライブラリのcsv・datetime・hashlib・io・json・math・re、v2_core（errors・sessions・fixture）、v2_git_store（`Git`・`GitError`・`OK`）だけ。urllib・http・socket・ssl・subprocess・os・time・random・threading・zoneinfoを使わない。`datetime.now`・`utcnow`・`today`・`sleep`・`os.environ`を呼ばない。他のパッケージのオブジェクトの`_`で始まる属性を使わない。

## 4. 受入条件 S4D-01〜S4D-18

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、設計§4.1の表を試験に書き写した値、研究のfixture（`load_research_fixture`）、試験側で`git`を直接呼んで読んだバイト、偽の送信先の記録から作る。実装の出力をコピーしない。応答は、研究のfixture（daily.json・daily_adjclose.csv）から試験のヘルパーで作ったchart APIの形のバイト列。リモートはすべて一時ディレクトリのbareリポジトリで、パスに印（例：`SECRETMARK_`）を入れる。

| ID | 必須確認 |
|---|---|
| S4D-01 回帰 | 既存の18スイート計2,598件を、完全なクローンで維持する（S4-Bまでの17スイート2,480件とS4-C 118件）。test_s4c_09の1行の固定を含み、件数は同じ |
| S4D-02 引数 | §3の2の`input_args_invalid`の各場面で例外になり、`fetch`・`Git`を呼ばない（呼出しの回数0）。`now`が時刻帯なしのdatetime・dateも拒む |
| S4D-03 暦 | (a) 2026-01-02〜2026-10-01のセッションの日付が、研究のdaily.jsonのSOXXの日付（188日）と一致。(b) 休場日・短縮取引日の集合が設計§4.1の表と一致し、土日のセッションが無い。(c) 寄付き・引けのUTCの時刻を、夏時間の切替えの前後の平日（2026・2027・2028年の3月と11月の各4日）と短縮取引日（2026-11-27は18:00Z、2028-07-03は17:00Z）で確かめる。(d) `confirmed`が`confirmed_through`以下の日だけ。(e) `now`＋14日がちょうど`CALENDAR_END`は失敗なし、1日超えると`input_calendar_not_covered`。`now`のUTCの日付が`CALENDAR_END`の翌日で`input_calendar_ended`。(f) `calendar_sha256`は同じ表で同じ、表の1日を変えると変わる |
| S4D-04 URLと取得の引数 | `chart_url`が§3の6の文字列そのもの（2つの例）。`load_inputs`が呼ぶ`fetch`の引数が`(記号, "2010-02-11", nowのニューヨークの日付の翌日)`で、4記号を1回ずつ |
| S4D-05 解釈 | (a) 正しい応答→行。(b) `null`の日は行が無く、誤りにならない。(c) NaN・inf・0・負・`PRICE_MAX`ちょうど・bool・文字列→`input_market_value_invalid`、detailは最初の日付。`PRICE_MAX`未満の最大の例は通る。(d) 形の誤りの各場面（§3の2）→`input_market_response_invalid`。(e) 9:30・16:00・0:00（ニューヨーク）の時刻が、夏時間の前後とも同じ日付になる。(f) `PREHISTORY_START`より前の行は捨てる。(g) `through`より後の行は、同じ日付が2つでも、値が範囲外でも捨てられ誤りにならない。`through`までに同じ日付が2つあれば誤りのまま |
| S4D-06 固定の形 | (a) 正規のJSON：同じ内容を違う順で作っても同じバイト、読んで書き直すと同じバイト。(b) `read_snapshot`の誤り（JSONでない、schemaが違う、列の長さが違う、値が範囲外、キーが無い）→`input_market_pin_invalid`。(c) SOXXに2010-02-11の行が無い→`input_market_history_short` |
| S4D-07 研究との一致 | 研究のデータから作った応答を固定し、固定から読んだ系列の判定の入力（`row(D)`・`soxl_close(D)`・`market_dates`の該当範囲）が、`load_research_fixture(through=D)`と、設計T-4の6日すべてで一致 |
| S4D-08 固定の進め方 | (a) 最初の実行→`this`、試験側で読んだコミットが親なしで木が`market.json`だけ。(b) 同じ朝の再実行→取得0回、`existing`。(c) 次の対象D→取得4回、新しいコミットの親が前の先頭（早送り）。(d) 取得したが揃った最後の日が`through`より後でない→コミットを作らず、固定済みのバイトから系列を作る。(e) 引けから59分の日は数えず、60分の日は数える |
| S4D-09 価格改訂 | 同じ対象Dの再実行で、取得先が調整後終値を改訂（試験の応答を0.1%変える）しても、固定済みを使い、`morning_job`はSKIPPED_CLAIMED・送信なしで止まらない。対照として、改訂した系列を直接渡すと`recompute_mismatch`になることを試験で示す（設計T-1） |
| S4D-10 失敗は判定なし | §3の2の「返す」誤りの各コード（`input_calendar_not_covered`を含む）を作り、`guarded_store`で包んだS4-Cの`GitHistoryStore`と`GitOutbox`の上で`morning_job`を走らせる。どれもSTOPPED（そのコード）、`<D>-halt`の判定なし1通SENT、文面に「理由コード: <コード>（<項目名>）」、リモートの履歴は変わらない。`input_calendar_ended`だけは例外で、`load_inputs`から投げられる |
| S4D-11 対象Dの行がまだ無い | 対象Dの行が無い応答→失敗なし、対象Dが未確定でSTALE（`run_session_unconfirmed`）、判定なし1通。同じ朝の後の実行で行が揃う→DONE・判定あり1通 |
| S4D-12 穴と表に無い日 | (a) 前の日に穴、対象Dはある→`input_market_rows_missing`（detail＝穴の日）。直した後の実行→DONE（止まった日を追いついて消費）。(b) 休場日の行→`input_calendar_data_mismatch`（detail＝その日）。(c) 2026年より前の休場日の行は誤りにしない。(d) 取引時間中（例：ニューヨーク10:40）の取得で、その日の日足が1行ある応答と、同じ日付の2行がある応答→どちらも失敗なし、その日は固定されず、前日のDがDONE・判定あり（レビューの探りZ1・Z2と同じ場面） |
| S4D-13 固定の競合 | (a) 2つのクローンで同じDを同時に固定（取得の途中で他方が改訂した版を先に固定。設計S11）→負けた方は`other`、両方の`market_sha256`が同じ、判定あり1通。(b) pushがUNCERTAIN（S4C-03(e)のpost-receiveの方法）で届いていた→読み直した版を使う。(c) `v2-market`だけを拒むpre-receive→`input_market_pin_failed`・判定なし1通。(d) 子プロセス2〜4個で各10回以上、同じDの固定のsha256が1つ、判定あり1通まで。回数と結果を結果文書に記録する |
| S4D-14 台帳 | (a) BOM・CRLF・空の行・前後の空白→受け付け、coreへ渡る値が空白を除いた文字列（数・時刻に変わっていない）。(b) 見出しの誤り、列の数の誤り、UTF-8でない、空のファイル、参照なし、ファイルなし→各コード。(c) `observed_at`が`now`の1秒後→`input_ledger_observation_after_now`、`now`ちょうど→受け付け。(d) 読めない`observed_at`→`load_inputs`は通し、coreの誤りで止まる。(e) `ledger_commit`が試験側で読んだ先頭のSHA。(f) 台帳の参照を読んだ後、リモートの台帳を変えない（ランナーが書かない） |
| S4D-15 通しの朝 | genesis（2026-07-20）から6回の朝（S4-A・S4-B・S4-Cの受領済みの部品）を`load_inputs`で走らせ、毎回DONE・判定あり1通。同じ6回を、`load_research_fixture`の系列と表のセッション・同じ台帳の行で直接走らせた場合と、各日のRunReportの結果と、最後の`history.json`の各APPLYの判定が一致。バイトが違う部分（入力の出所の記録など）があれば、結果文書に列挙する |
| S4D-16 出所と機密 | (a) `provenance`のキーと値の型が§3の13のとおり。(b) リモートのパスと参照に印を入れ、S4D-02〜15の全場面で、例外の文字列・引数・repr、`provenance`、RunReport・JobReport、文面、`market.json`、コミットのメッセージに印が出ない。(c) `InputError`のdetailが日付か無し。(d) 投げた・返した`InputError`の`__context__`・`__cause__`がNone |
| S4D-17 静的な範囲 | §3の14のimportだけ。禁止のモジュール・呼出しが無い。`raise`が`except`の本体の中に無い（素の`raise`を除く）。他のパッケージの`_`で始まる属性を使わない。v2_git_storeのpush以外にリモートを変える呼出しが無い |
| S4D-18 範囲試験 | 新しい範囲試験（START＝ffa3700、END＝None、REV＝END or "HEAD"、FilesChanged）が、§2の変更だけを許す。test_s4c_09の差分を自分の差分のハンクとして固定する。範囲の鎖が`…→6cab050→ffa3700→（S4-D）`で通る。ENDだけを固定して開いた範囲を外すと鎖の試験が失敗する手順を、結果文書に記録する |

## 5. 限定欠陥注入

1件ずつ壊して試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. 固定の`through`が対象Dでも取得する。
2. 揃った最後の日が`through`と同じでも固定し直す（同じDの系列を変える）。
3. 固定し直さないとき、固定済みではなく取得した系列を使う。
4. pushで負けたとき、読み直さずに自分の系列を使う。
5. `load_inputs`が入力の失敗を投げる（返さない）。
6. `guarded_store`の包みの`read()`が元の保存先を読む。
7. `confirmed`をすべてのセッションに付ける。
8. 夏時間の規則を1週ずらす（3月の第1日曜日から）。
9. 引けからの60分を0分にする。
10. `null`の日を値の誤りにする（または、値の誤りの日を黙って捨てる）。
11. 価格の上限を外す。
12. `now`より後の`observed_at`を受け付ける。
13. 台帳の値を数に変えてcoreへ渡す。
14. 表に無い日のデータの検査を外す。
15. 穴の後の日を揃った最後の日にする（穴を飛ばす）。
16. `market.json`をキーを並べずに書く。
17. 表の残りの日数の検査（14日）を外す。
18. `GitError`を`input_git_failed`に置き換えない（または「参照なし」として扱う）。
19. SOXXの始まりの検査（`input_market_history_short`）を外す。
20. `InputError`を例外の処理の中で投げる（`__context__`が残る）。
21. 表との照合を、閉じたセッションだけにする（第2版N-01）。
22. 対象Dより後の行を捨てずに、同じ日付の検査（または表との照合）をする（第2版N-01）。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する。gitの版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 試験は一時ディレクトリの中だけでbareリポジトリとクローンを作る。ネットワークを使わない。取得の関数は試験の偽物だけ。試験側のgitの呼出しにも`-c`で必要な設定を渡す。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴）で試験する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、新規Nと、S4-C 118、S4-B 131、S4-A 96、範囲の鎖34を実行する。実Windowsで行うまで未実施と書く。ユーザーPC・物理電源断・GitHubのリモート・実際の取得先は未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_inputs -p "test_s4d_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。gitの版。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- ランタイムの全文の場所と行数。`calendar_sha256`の文字列の作り方と値。
- test_s4c_09の差分の全文。
- 試行の下書き（設計§11）との違いと、その理由。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。
- S4D-13(d)の回数と結果、S4D-10の場面の一覧、S4D-18の手順と結果。
- 測定（S4-Cの申し送り3、設計§10.3）：`load_inputs`の時間（取得を除く。初回・同じ朝の再実行・次の対象D）、`market.json`の大きさ、2026-01-02〜2026-08-10の毎セッションに固定した後のbareリポジトリの大きさ（`git count-objects -v`と`gc`の後）。
- リモートのコミットの例（`git log --format=…`と`ls-tree`の写し。パスは伏せる）。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・非公開リポジトリの作成・GitHubへの状態のpush・実際の取得・実際の送信・S4-Eへは進まない。

## 7. 読取専用の保護参照

次の104参照を、開始時と保存・push後に完全SHAで照合する。S4-Cの依頼書の99参照に、S4-Cの資料・実装レビュー（受領記録を含む）・レビュー・再レビュー・実装の5本を加えたものである。本書と設計を保存した資料ブランチdocs/v2-inputs-s4d-20261105についても、受け取った版の完全SHAを1本加える。設計・依頼書へのレビュー・再レビューの資料ブランチがあれば、その受け取った版も加える（加えた本数と合計を結果文書に書く）。**実装時は、少なくとも次の2本を加えた106参照**を照合する：資料ブランチdocs/v2-inputs-s4d-20261105の受け取った版（採用記録のコミット）、レビューdocs/v2-inputs-s4d-review-20261105の33894b254c0967cecd69c7efbccc7db8001926f6。第2版の再レビューの資料ブランチがあれば、さらに1本加える。**採用の時点で、実装時の照合は107参照に決まった**：上の104参照に、資料ブランチdocs/v2-inputs-s4d-20261105の受け取った版（採用記録のコミット）、レビューdocs/v2-inputs-s4d-review-20261105の33894b254c0967cecd69c7efbccc7db8001926f6、再レビューdocs/v2-inputs-s4d-v2-rereview-20261105の04acf137294fcfb681356e9562aec79bb8d71fe0を加えたもの（設計§16）。

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

本書の作成時（2026-11-05、日本時間）に、上の104参照がリモートと完全SHAで一致することを、作業の開始時に確かめた。資料ブランチのpush後の照合は、下の追記に記す。

追記（2026-11-05）：資料ブランチdocs/v2-inputs-s4d-20261105の最初のpush（fad0f5b1ea0565b7feff424bc662d2531a6fc59c）の前と後にも、上の104参照がリモートと完全SHAで一致することを確かめた。

追記（2026-11-05、第2版）：第2版cb50286baf0308b3fa272e528149e38b7f7d4f01のpushの前と後にも、上の104参照がリモートと完全SHAで一致することを確かめた。実装時に加えるレビュー33894b254c0967cecd69c7efbccc7db8001926f6も、この時点でリモートと一致した。

## 8. 採用単位

設計§13のD-1〜D-10と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。2026-11-05T11:07ZのRocky「推奨どおり」に基づき、第2版のとおり採用として記録した（設計§16）。

- D-1：S4-Dの範囲（`v2_inputs`の5ファイルと試験。HTTPの取得と受領済みのパッケージの変更は含めない）。
- D-2：全体の流れ（`load_inputs`→`guarded_store`→`morning_job`、`now`は入口で1回）。
- D-3：セッション（表と夏時間の規則、残り14日の検査。表はICEの公式発表2025-12-23と照合済み）。
- D-4：取得先と値の定義（Yahoo Financeのchart API v8、始まり2010-02-11、価格の上限）。
- D-5：価格改訂（`v2-market`への対象Dごとの固定）。
- D-6：台帳（`v2-ledger`の`observations.csv`）。
- D-7：入力の失敗（値で返し、包みの`read()`で投げる）。
- D-8：古さの上限（U-06、置かない）。
- D-9：公開する名前と出所の記録。
- D-10：引継ぎ（S4-CのEND固定、P-02(b)・P-05、申し送りとR2-P01のS4-Dの部分）と担当（Sonnet 5.5・high）。

設計§11の一時環境の試行は、実装ではない。S4-Cの受領と「次の段階に進めてください」を、S4-Dの実装承認にしない。市場データの取得先への実際の接続、非公開リポジトリの作成・秘密の登録・workflowの変更・本番の承認も含まない。
