# V2 S4-D 朝の実行の入力（セッション・市場データ・台帳）限定実装の結果

作成日：2026-11-05（日本時間）。担当：Claude Sonnet 5.5（セッション設定 `claude-sonnet-5-5[1m]`、effort `high`）。gitの版は 2.43.0。
対象：`Rocky009-jp/soxl-alert`、新ブランチ `feat/v2-inputs-s4d-20261105`。PR・マージ・Actions・本番・実際の取得・実際の送信・S4-Eへの着手はしていない。GitHubへのpushは新しい実装ブランチ1本だけである。試験のリモートはすべて一時ディレクトリのbareリポジトリで、取得の関数は試験の偽物だけである（ネットワーク不使用）。

## 0. 要約

- S4-Dの限定実装は**完了**した。新パッケージ `v2_inputs`（5ファイル534行）と新しい試験 `tests/v2_inputs`（12本の試験ファイルと2本の補助、新規130件）を足し、既存の1ファイル（`tests/v2_git_store/test_s4c_09_scope.py`）の**1行だけ**（`END`を `ffa3700` に固定）を変えた。受領済みのパッケージ・補助・資料は変えていない。
- 試験対象 `ec28ccf4fd7a82aa2ce78f0a33db80ee5bdd928f` で、S4-Dの130件が Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版とも全件合格（失敗0・エラー0・skip 0）。既存18スイート2,598件も4版とも全件合格（失敗0・エラー0。skip 4はS2のWindows専用で既存）。**合計2,728件**。ただし既存18スイートの実行は一つ前の `a99be14` で行い、`ec28ccf` では範囲に関わる6スイートだけを再実行した（§7.2に正確に書く）。
- 欠陥注入は依頼の22項目に変種2件（10b、21+22）と追加27件を加えた**51件**。検出49・未検出2・準備失敗0。未検出2件のうち、21（単独）は**等価**と判断（根拠は§8.2）、E4は試験を1件足して**検出に変えた**（§8.3）。
- S4D-13(d)は2〜4個の子プロセスで各10ラウンド、4版とも毎回、固定の版は1つ・判定ありの通知は1通・APPLYの重複0（§9）。
- 試行の下書き（設計§11）との差は§5。設計・依頼書の矛盾や範囲外の変更は見つからなかった。止めた箇所はない。
- **未実施**：実Windows、物理電源断、ユーザーPC、GitHubのリモートを使った確認、実際の取得先（Yahoo chart API）への接続（§13）。

## 1. 固定した資料と起点

| 項目 | 値 |
|---|---|
| 資料コミット（docs/v2-inputs-s4d-20261105、D-1〜D-10の採用記録） | `263604b1448a39e68d4d1e53983bc55ef36d92ba` |
| 設計 `docs/specs/V2_INPUTS_S4D_DESIGN_DRAFT.md`（blob） | `206ac8e7f4039cfd0c39c94aeba3c2118c5816fe` |
| 依頼書 `docs/tasks/V2_INPUTS_S4D_LIMITED_IMPLEMENTATION_REQUEST.md`（blob） | `aab7587dd504d856aaebca593c208acb153107ec` |
| 試行差分 `docs/specs/V2_INPUTS_S4D_TRIAL_20261105.diff`（blob） | `20abc003d159af5124e967a6c11ade70effeafcb`（sha256 `3ce7077fd705b171492d08e81e442a64b7dca2c0cafaee8e79e9adb8e8cd0c77`）。参考にしただけで適用していない |
| コードの開始点 | `ffa370089cd37fcc76658b4de0f4aedde0a246e0`（S4-Cの保存最終・受領版） |
| **試験対象（コード・試験の最終）** | `ec28ccf4fd7a82aa2ce78f0a33db80ee5bdd928f` |
| 途中の試験版 | `a99be14`（初回の全スイート実行）→ `8c86a48`（試験内の監査1件を修正）→ `ec28ccf`（欠陥注入E4の試験を1件追加）。ランタイム（`v2_inputs/*.py`）は3版とも同一 |
| 最終（この結果文書の追加） | この文書だけを足した次のコミット。SHAはpushの報告に書く |

保護参照は、依頼書§7の104参照に、資料ブランチ（`263604b`）・設計レビュー（`33894b2`）・再レビュー（`04acf13`）の3本を加えた**107参照**を、開始時・試験後・push前・push後に完全なSHAで照合した（`refcheck.py`、`refs_protected107.txt`）。push前の照合は 107参照・不一致0。push後は報告に書く。

## 2. 変更したもの

| 場所 | 内容 |
|---|---|
| `v2_inputs/__init__.py`（14行） | 公開名 |
| `v2_inputs/xnys.py`（93行） | 休場日・短縮取引日の固定表（2026-01-02〜2028-12-29）、米国の夏時間の規則、`build_sessions`、`coverage_failure`、`calendar_sha256`。tzdata・暦ライブラリは使わない |
| `v2_inputs/market.py`（202行） | `chart_url`、`parse_chart`（対象Dより後の行を検査の前に捨てる）、`market.json`の正規のJSON、`read_snapshot`、`MarketPin`（`v2-market`の読み書き。commit_with＋早送りのpush） |
| `v2_inputs/ledger.py`（64行） | `read_ledger`：`v2-ledger`の`observations.csv`を取得したSHAで読む。ランナーは書かない |
| `v2_inputs/load.py`（161行） | `Inputs`、`guarded_store`、`load_inputs`。入力の失敗は`Inputs.failure`で返し、`guarded_store`が`read()`で投げる |
| `tests/v2_git_store/test_s4c_09_scope.py` | 18行目 `END` の**1行だけ**（下の差分） |
| `tests/v2_inputs/`（新規14ファイル） | `s4d_helpers.py`、`s4d_worker.py`、`test_s4d_01〜12_*.py`（`__init__.py`は作っていない） |
| `docs/implementation/V2_INPUTS_S4D_RESULT.md` | この文書（別のコミット） |

`calendar_sha256` の作り方：`"<CALENDAR_START>..<CALENDAR_END>|H:<休場日をソートしてカンマ区切り>|E:<短縮取引日をソートしてカンマ区切り>"` のASCII文字列のsha256。値は `eb41ea2ccd36a2ee9ebce0b5ac1bad12c37b2a6a8dfd54562257a3bd4f359800`（`2026-01-02..2028-12-29`、休場日は表の範囲内28日＋範囲前の1日を含む29日の表）。

ランタイムの全文は `v2_inputs/` の5ファイル（534行）で、試験対象コミットにある。

`test_s4c_09_scope.py` の差分の全文（`git diff --unified=0 ffa3700 ec28ccf -- tests/v2_git_store/test_s4c_09_scope.py`）：

```
@@ -18 +18 @@ START = "6cab0506c408d194c63b656713e4a0a7d62c3ba1"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "ffa370089cd37fcc76658b4de0f4aedde0a246e0"   # accepted (receipt 5dc9cdc); frozen when S4-D began
```

新しい `test_s4d_09_scope.py` がこのhunkをS4-Dの差分として固定している（`-18 +18`）。

## 3. ランタイムの規則（設計のとおり）

- **セッション**：固定表から作る。夏時間は3月の第2日曜日から11月の第1日曜日の前日までUTC-4、それ以外はUTC-5。引けから`CLOSE_MARGIN`（60分）たったセッションだけを確定として数える。`now`＋`MARGIN_DAYS`（14日）が表の端を超えると`input_calendar_not_covered`（返す）、`now`のUTC日付が表の端の翌日以降で`input_calendar_ended`（投げる）。
- **市場データ**：取得は`fetch(記号, "2010-02-11", nowのニューヨークの日付の翌日)`を4記号1回ずつ。値は有限で0超`PRICE_MAX`（1,000,000）未満。SOXX・SPY・IEFは調整後終値、SOXLは終値。`null`の日は行なし。`market_dates`はSPYとIEFの両方がある日。
- **固定**：対象Dごとに `v2-market` の `market.json`（正規JSON、schema `v2_inputs.market.1`）。対象Dより後の行は捨ててから検査する。固定が対象Dに届いていれば取得しない（`existing`）。そうでなければ取得して揃った最後の日まで固定（`this`）、pushで負けたら読み直して届いた版を使う（`other`）。届かなければ`input_market_pin_failed`。
- **台帳**：`v2-ledger`の`observations.csv`。BOMとCRLFを許し、見出しは厳密な6列。値は空白を除いた文字列のままcoreへ渡す。`now`より後の`observed_at`は拒む。
- **失敗の伝え方**：入力の失敗は返し、`guarded_store`の`read()`が投げる。S4-AはSTOPPED、S4-Bは「判定なし」を1通送る。`GitError`は`CoreError`の子なので先に捕まえて`input_git_failed`にする。例外の処理（`except`）の本体の中では投げない。

## 4. 追加・確認した点（設計の確認）

- 表と研究のdaily.jsonのSOXXの日付が2026-01-02〜2026-10-01の188日で完全に一致（S4D-03(a)）。
- 研究の`load_research_fixture(through=D)`と固定から読んだ系列の判定の入力が、設計T-4の6日（2024-10-01、2025-01-02、2025-06-02、2026-03-02、2026-07-28、2026-08-10）で一致（S4D-07）。
- 通しの6回の朝（genesis 2026-07-20）は、`load_inputs`経由と直接の入力で、各日のRunReportと最後の`history.json`の各APPLYの判定が一致。`history.json`のバイトも同じ。違うのは通知側の入力の出所の記録（`provenance`の指紋）だけ（S4D-15）。

## 5. 試行の下書き（設計§11）との違い

| 点 | 試行 | 実装 | 理由 |
|---|---|---|---|
| `parse_chart` | 全行を検査 | `through`（対象D）を受け、それより後の行を検査の前に捨てる | 設計第2版N-01。取引時間中の取得で当日の日足が混ざっても止めない |
| 表との照合 | 閉じたセッションだけ | 表の全セッションに対して照合 | 同上（欠陥21・22） |
| 引数の検査 | なし | `input_args_invalid`（`now`が時刻帯なし、参照名、関数でない等）。取得・gitを呼ぶ前に拒む | 依頼§3 |
| 入力の失敗 | 一部が例外 | 返す16コード（`input_calendar_ended`と`input_args_invalid`だけ投げる） | 設計§7 |
| `GitError` | `CoreError`を先に捕まえていた | `GitError`を先に捕まえて`input_git_failed` | 試行T-7 |
| `__context__` | 例外の処理の中で投げる箇所があった | 処理の外で投げる（`__context__`・`__cause__`はNone） | 依頼§3、S4D-16(d) |
| 追加の検査 | — | SOXXの始まり（`input_market_history_short`）、同じ日付、UTF-8でない応答、bytesでない応答、`market.json`の形（キー・列の長さ・値の範囲・`through`以下の行） | 設計§5.2・§5.3 |
| 出所 | 一部のキー | `calendar_sha256`・`market_commit`・`fetch_count`・`pinned_by`・`market_sha256`・`market_through`・`ledger_commit`などの全キー | 依頼§3の13 |

## 6. 受入とテスト名の対応

| ID | 試験ファイル（クラス） |
|---|---|
| S4D-01 回帰 | `runall.sh`の18スイート（§7）。`test_s4c_09`の1行の固定を含む |
| S4D-02 引数 | `test_s4d_01_args`（NoGit、Counting、Args） |
| S4D-03 暦 | `test_s4d_02_calendar`（Calendar） |
| S4D-04 URLと取得の引数 | `test_s4d_03_url_parse`（Url、FetchArguments） |
| S4D-05 解釈 | `test_s4d_03_url_parse`（Rows） |
| S4D-06 固定の形 | `test_s4d_04_pin_shape`（Shape、Columns） |
| S4D-07 研究との一致 | `test_s4d_04_pin_shape`（ResearchEquality） |
| S4D-08 固定の進め方 | `test_s4d_05_pin_progress`（Progress） |
| S4D-09 価格改訂 | `test_s4d_05_pin_progress`（PriceRevision） |
| S4D-10 失敗は判定なし | `test_s4d_06_failures`（EveryFailureStops、NothingClosedYet） |
| S4D-11 対象Dの行がまだ無い | `test_s4d_05_pin_progress`（TargetNotThereYet） |
| S4D-12 穴と表に無い日 | `test_s4d_06_failures`（Holes、DaysTheTableDoesNotHave、SessionStillOpen） |
| S4D-13 固定の競合 | `test_s4d_07_race`（Pair、Processes） |
| S4D-14 台帳 | `test_s4d_08_ledger` |
| S4D-15 通しの朝 | `test_s4d_10_mornings`（SixMornings） |
| S4D-16 出所と機密 | `test_s4d_11_secrets`（Provenance、Secrets、Details） |
| S4D-17 静的な範囲 | `test_s4d_12_static` |
| S4D-18 範囲試験 | `test_s4d_09_scope`（PathJudgement、Base、FilesChanged、Chain、TestFiles） |

件数（実行した試験の数）：01=7、02=8、03=14、04=10、05=10、06=18（E4の1件を含む）、07=8、08=15、09=20、10=3、11=7、12=10、計130。

S4D-10の場面（`H.CODES`の16コード）：`input_calendar_not_covered`、`input_market_fetch_failed`、`input_market_response_invalid`、`input_market_value_invalid`、`input_market_history_short`、`input_calendar_data_mismatch`、`input_market_rows_missing`、`input_market_pin_invalid`、`input_market_pin_failed`、`input_market_unavailable`、`input_ledger_missing`、`input_ledger_unreadable`、`input_ledger_header_invalid`、`input_ledger_row_invalid`、`input_ledger_observation_after_now`、`input_git_failed`。それぞれSTOPPED・判定なし1通SENT・理由コードの文面・リモートの履歴は変化なし。`input_calendar_ended`は`load_inputs`から投げられることを別に確認。

## 7. 全スイートの結果

### 7.1 Python 3.10.20／3.11.18／3.12.3／3.13.18（完全な履歴の別クリーンクローン、`core.autocrlf=false`、`PYTHONDONTWRITEBYTECODE=1`、`-W error::ResourceWarning`）

| スイート | 件数 | 結果 |
|---|---|---|
| v2_core | 197 | OK |
| v2_persistence | 170 | OK |
| v2_persistence_local | 113 | OK（skip 4、S2のWindows専用） |
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
| v2_notify | 131 | OK |
| v2_git_store | 118 | OK |
| 既存18スイートの計 | **2,598** | 4版とも失敗0・エラー0 |
| **v2_inputs（新規、`ec28ccf`）** | **130** | 4版とも OK、終了コード0 |

### 7.2 正確な実行の経過（隠さずに書く）

1. `a99be14` で19スイートを4版で実行した。既存18スイートは全件合格。v2_inputsは129件中1件が失敗した：`test_s4d_09_scope`の自作の監査（試験ファイルが標準ライブラリの`decimal`をimportしてはならない）に、`test_s4d_05_pin_progress.py`の`from decimal import Decimal`が当たった。ランタイムの誤りではなく試験の書き方の問題なので、試験側を直した（`8c86a48`）。
2. `8c86a48` で v2_inputs（129件）を4版とも再実行し全件合格。欠陥注入（§8）はこの版で行った。
3. 欠陥注入のE4が未検出だったため、`test_s4d_06_failures.py`に1件足した（`ec28ccf`、130件）。v2_inputsを4版とも再実行し全件合格（ログ：`s4d_final_py3.1X.log`）。
4. `ec28ccf` では既存18スイートの全件は再実行していない。`a99be14`→`ec28ccf`の差は`tests/v2_inputs`の2ファイルだけで、どの既存パッケージもこれをimportしない。範囲に関わる6スイート（v2_scope_chain、test_c4_09、s4a_09、s4b_09、s4c_09、s4d_09）は `ec28ccf` で S4D-18 の手順（§10）の[A]として実行し、全件合格した。

ログは `/mnt/project-files/implementation/s4d_inputs_20261105/` の `final_runall_py3.1X.log`（`a99be14`）、`rerun_s4d_after_test_fix_py3.1X.log`（`8c86a48`）、`s4d_final_py3.1X.log`（`ec28ccf`）。

## 8. 限定欠陥注入

1件ずつ、試験対象のクリーンクローンの使い捨ての作業ツリーに壊した版をコミットして実行した（`mutate.py`、4分割、`8c86a48`）。何もpushしていない。

### 8.1 結果

51件：検出49・未検出2・準備失敗0。

- 依頼の22項目：1〜20、22は検出。21（単独）は未検出。
- 変種：10b（値の誤りの日を黙って捨てる）検出。21+22（R-01の確認）検出。
- 追加27件（E1〜E27）：E4以外は検出。

追加の内容：始まりの日付、`market.json`のschema・行の範囲、穴や表に無い日のdetail、台帳の空白・BOM、記号ごとの価格の種類、`market_dates`、短縮取引日の引け、取得の終わりの日付、参照名の重複、bool、`now`ちょうどの観測、固定のコミットの親、表の端の比較、`chart_url`の配当・分割、数値化、応答の記号名、固定のsha256、取得失敗の記号を飛ばす、台帳の参照、`fetch_count`。

### 8.2 欠陥21（単独）：等価と判断

壊し方：`_last_complete`の表との照合（`table = set(s.date for s in sessions)`）を、閉じたセッションだけ（`for s in closed`）にする。

根拠：`closed`は`sessions`の先頭からの連続した接頭辞で、対象D＝`closed`の最後の日である。閉じていないセッションは、すべてDより後の日付である。照合に届く系列は`parse_chart`で対象Dより後の行をすでに捨てている（欠陥22が壊す部分）ので、「表の全セッションに対して照合する」と「閉じたセッションに対して照合する」は、Dまでの行に対して同じ結果を返す。差が出るのはDより後の行が残るときだけで、それは欠陥22を同時に入れたとき（21+22）に限る。実際に21+22は検出された（取引時間中の取得で当日の日足が混ざる場面で`input_calendar_data_mismatch`になる）。つまり単独の21はこの二段の防御の一段目が破られても二段目で守られるため、観測できる差がない。依頼書R-01のとおり、単独では等価とし、組合せで感度を確かめた。

### 8.3 E4：試験を足して検出に変えた

壊し方：穴の日の記録を、最初の穴ではなく最後の穴にする（`hole = session.date`）。既存の試験は穴が離れた2か所（07-21と07-23）だけで、穴の間に揃った日があると最初の穴の直後に止まるため、差が出なかった。連続した2つの穴（07-21と07-22）を作る試験（`test_two_holes_in_a_row_name_the_first`）を足し、壊した版で失敗することを確かめた（手作業で壊して実行し、元に戻した）。`mutate.py`を最終版で全件再実行はしていない。

結果ファイル：`mut_0〜3.json`／`mut_0〜3.log`、作成スクリプト `mutate.py`。

## 9. S4D-13：固定の競合

- (a)(b)(c)の場面は`Pair`の試験で確認した（先に固定した版が勝ち、負けた方は`other`として同じ`market_sha256`を使う。UNCERTAINは読み直して使う。`v2-market`だけを拒むpre-receiveは`input_market_pin_failed`・判定なし1通）。
- (d) 2〜4個の独立したPythonプロセス（各`n`で10ラウンド、計30ラウンド、結果90件）。各ラウンドで、固定のsha256は1つ、`this`は最大1、リモートの`v2-market`のコミットは1つ、判定ありの通知は最大1通、判定なしは最大`n-1`通、履歴のAPPLYは対象Dで1回だけ。
- 4版の集計（`this`=30、`other`=60、`existing`=0、固定30、判定あり30通）。負けた実行は`STOPPED publication_stale`（受領済みの動作）で、判定なしの通知数は版ごとに24〜29で変わるが、すべて上限`n-1`以内。

| 版 | 判定なし | 止まった実行（publication_stale） |
|---|---|---|
| 3.10 | 29 | 58 |
| 3.11 | 27 | 55 |
| 3.12 | 29 | 58 |
| 3.13 | 24 | 48 |

## 10. S4D-18：範囲試験と次の段階の模擬

新しい範囲試験（START＝`ffa3700`、END＝None、REV＝END or "HEAD"、FilesChanged、Chain、TestFiles）は、§2の変更だけを許し、`test_s4c_09`の差分を自分のhunkとして固定する。鎖は `…→6cab050→ffa3700→（S4-D）` で通る。

手順（`next_stage_sim.sh`、使い捨ての作業ツリー、何もpushしない、`ec28ccf`で実行）：

| 段階 | 内容 | 結果 |
|---|---|---|
| [A] | 試験対象のまま | 6スイート（v2_scope_chain 34、c4_09 31、s4a_09 19、s4b_09 19、s4c_09 20、s4d_09 20）すべて合格 |
| [B] | S4-Dの範囲試験の`END`だけを`ec28ccf`に固定し、次の段階の開いた範囲を足さない | `v2_scope_chain`が**失敗2件**（期待どおり：開いた範囲がない鎖を拒む）。他は合格 |
| [C] | [B]に加えて、次の段階の最小の開いた範囲試験（START＝`ec28ccf`、END＝None）を足す | 6スイートすべて合格 |

つまり、S4-Eは `END` を固定する1行と、自分の開いた範囲試験を足すことで鎖を通せる。ログ：`next_stage_sim.log`。

## 11. 測定（S4-Cの申し送り3、設計§10.3）

`measure.py`で、2026-01-02から2026-08-10までの毎セッション（150日）に固定した。genesisは2026-01-02、台帳は毎日その日まで揃え、取得の関数は試験の偽物（研究のfixtureから作った応答）、リモートはローカルのbare。Linux、Python 3.13.18、他のジョブを止めた状態で実行。時間は`load_inputs`の呼出し全体（偽の取得関数の応答の生成を含み、実際のネットワークは含まない）。

| 項目 | 値 |
|---|---|
| `load_inputs`・最初の日（固定が無い、取得4回） | 0.43秒 |
| 次の対象D（毎日、取得4回＋固定1回）の中央値／最大 | 0.51秒／0.70秒（150回の合計77.3秒） |
| 同じ朝の再実行（取得0回、`existing`） | 0.12秒 |
| `market.json`の大きさ | 393,161バイト（初日）→ 411,335バイト（最後の日） |
| 150回固定した後の`v2-market`のコミット数 | 150 |
| `gc --aggressive --prune=now`の後のbareリポジトリ | in-pack 906オブジェクト、packは1つ、`size-pack` 237 KiB、loose 0（`git count-objects -v`） |

試行（12回の固定で約171KB）と同じ桁で、1日あたり約1.5KiBの増加である。150日で237KiB、1年（約252セッション）で約400KiB、表の端まで（約750セッション）でも数MBに収まる見込みだが、これは外挿であり実測ではない。

リモートのコミットの例（パスは伏せる）：

```
$ git log --format="%h %an <%ae> %s" -3 v2-market
8fd2e43 v2-runner <runner@invalid> v2 market through 2026-08-10
2a70f1d v2-runner <runner@invalid> v2 market through 2026-08-07
c6e7633 v2-runner <runner@invalid> v2 market through 2026-08-06
$ git ls-tree -r -l v2-market
100644 blob 7dc256873a2e337ae8e5afeda3b8e2b8c1a6dd87  411335	market.json
```

結果ファイル：`measure_result.json`。

## 12. 保護参照の照合

push前：107参照を完全なSHAで照合し、不一致0。push後の照合は報告に書く。本文は`refcheck.py`（`refs_protected107.txt`と`git ls-remote origin`の比較）で行った。

## 13. 未実施・残るリスク

- **未実施**：実Windows（新規130、S4-C 118、S4-B 131、S4-A 96、範囲の鎖34を実Windowsで走らせる手順は未実行）、ユーザーPC、物理電源断、GitHubの実リモート（認証・遅延・拒否の振る舞い）、実際の取得先（Yahoo chart v8）。取得の関数は偽物だけで、実際の応答の形・欠測の傾向・レート制限は未確認。
- 負けた実行は`STOPPED publication_stale`になる（S4-Cで受領済みの動作）。S4-Eはこれを再試行するか、次の定時実行に任せるかを決める必要がある。
- 台帳は読むだけで、書く側（目視F&Gの記録）はS4-Dの範囲外。
- 臨時の休場・短縮取引日の訂正は表を更新するまで反映されない（設計§4.3）。表の末尾（2028-12-29）の14日前から`input_calendar_not_covered`で止まる。
- `calendar_sha256`は表のバージョンの記録であり、表の正しさの証明ではない（休場日はICE発表2025-12-23と設計時に照合済み）。

## 14. 作業記録

`/mnt/project-files/implementation/s4d_inputs_20261105/`：`mutate.py`、`mut_0〜3.json`／`.log`、`next_stage_sim.sh`／`.log`、`runall.sh`、`final_runall_py3.1X.log`、`rerun_s4d_after_test_fix_py3.1X.log`、`s4d_final_py3.1X.log`、`measure.py`／`measure_result.json`、`refcheck.py`、`refs_protected107.txt`。
