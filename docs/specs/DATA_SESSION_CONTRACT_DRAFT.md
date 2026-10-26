# 価格定義と対象セッション決定 — 仕様案（未採用）

作成：2026-10-26（日本時間）。担当：Claude Opus 5.5（依頼：[DATA_SESSION_OPUS55_REQUEST](../tasks/DATA_SESSION_OPUS55_REQUEST.md)）。
資料開始SHA：`7d15e859dfb417306b4cf378b43d9487c87547a5`（docs/v2-roadmap-20261023）。
対象候補：`920e69571cf4feda09f3f2f560e96fcb9cb09d50`（feat/interim-notification-20261026）。main：`31144d9`（停止維持）。

本書は採否判断のための**案**であり、採用・実装・試験合格ではない。コード・設定・ワークフローは変更していない。市場データAPI・Discord・Sheets・Actionsへのアクセスは0。

凡例：**[事実]** 一次資料・対象版の実装で確認／**[推奨]** 本書の提案／**[未決]** 判断が必要／**[未検証]** 実データ・実行で確認していない。

## 0. 読んだもの・確認した一次資料

- リポジトリ：CLAUDE.md、docs/STATUS.md、依頼書、[たたき台](DATA_SESSION_DESIGN_NOTES.md)、[920e695確認](../reviews/INTERIM_FIX_REVIEW_920e695.md)、[採用仕様](INTERIM_NOTIFICATION_SPEC.md)、候補の main.py／soxl_checks.py／schedule.yml、研究の provenance.json／input_manifest.json と audit.mjs の読込部（36〜60行）、data/daily.json のメタ情報（note・splits）のみ。
- yfinance 1.7.0：PyPIのwheelを取得し `multi.py`（download既定値・docstring・失敗時処理）、`utils.py`（auto_adjust・parse_quotes）、`scrapers/history.py` を読んだ。確認日2026-10-26。
- NYSE公式 [Holidays and Trading Hours](https://www.nyse.com/trade/hours-calendars)（2026〜2028の休場・短縮取引）。確認日2026-10-26。
- GitHub公式 [Events that trigger workflows — schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。確認日2026-10-26。
- exchange_calendars 4.13.2（PyPI）をローカルの使い捨て環境へ導入し、XNYS/XNASの2025〜2028の休場・短縮日を出力して公式表と照合（市場データ取得ではない）。
- 未取得：旧Actions環境の当時のyfinance版・既定値、upstream_crosscheck.json の生成コード（比較した列の定義は不明）、daily_adjclose.csv の調整定義の原典。

## 1. 結論（推奨3点）

1. **価格：auto_adjust=False で1回取得し、同じ応答から用途別に選ぶ（案B）。** 指標（SOXX SMA/RSI、SPY/IEF SHD）は `Adj Close`、SOXLの表示・Sheetsは `Close`／`Open`。指標値は現候補（auto_adjust=True）と実装上同一になり、SOXL表示だけが「分配金未調整」に意味を固定される。
2. **対象セッション：XNYSカレンダー（exchange_calendars 4.13.2固定）＋推定予定時刻＋確定猶予で決め、データからは決めない。** 対象日Dを先に決め、取得範囲をDで閉じ、期待セッション列とデータの日付列の完全一致を検査する。
3. **スケジュール：cronを UTC `40 22 * * 1-5` へ移す案をユーザー判断に出す。** 現行 `30 21` UTC は冬時間に終値後30分しかなく、猶予60分案と両立しない。

## 2. A. 価格と依存の契約

### 2.1 確認できた事実

- **[事実]** yfinance 1.7.0 の `download` は `auto_adjust=True`、`actions=False`、`repair=False`、`keepna=False` が既定（multi.py 55〜57行）。
- **[事実]** `utils.auto_adjust` は `ratio = Adj Close / Close` を Open/High/Low に掛け、`Adj Close` を `Close` へ改名する（utils.py 506〜523行）。よって現候補の `close` は Adj Close そのもの、`open_["SOXL"]` は**分配金調整後の始値**である。
- **[事実]** `utils.parse_quotes` は応答に `adjclose` が無いと `adjclose = closes` とする（utils.py 557〜559行）。**Adj Close欠落はyfinance内部でCloseへ黙って代用され得る**。案A・Bどちらでも呼び出し側だけでは直接検出できない。
- **[事実]** 複数銘柄取得で一部銘柄が失敗しても例外にせずログへ出し、その銘柄を空表として結合する（multi.py 191〜213、290〜303行）。結果はNaN列になる。
- **[事実]** 日足で市場が開いている時間に取得すると、当日の未確定行を返す処理がある（history.py 532行 `fix_Yahoo_returning_live_separate`）。`end` は「exclusive」と記載（docstring）。
- **[事実]** 研究の監査は、SOXXに daily.json の `adjClose`（note：「split- and dividend-adjusted (total return)」）、SOXLの売買に `ohlcv`（note：「split-adjusted only」）、SHDに daily_adjclose.csv の SPY/IEF を使う（audit.mjs 42〜45行）。SOXLの分配金は発行体台帳で別計上（dividends_verified.json）。
- **[事実]** daily.json の取得は2026-10-01、Yahoo chart API 由来と記載。現候補のyfinanceと同じ定義・時点だった証拠はない（STATUS・920e695確認と同じ立場）。

### 2.2 系列の定義（推奨）

| 用途 | 系列名（仕様上の名前） | 取得列 | 調整 | 注意 |
|---|---|---|---|---|
| SOXXのSMA200・RSI14 | `ind_soxx` | SOXX `Adj Close` | 分割＋分配金（上流定義） | 研究の adjClose と同じ種類。値の一致は[未検証] |
| SHD（SPY/IEF 20日騰落差） | `ind_spy`／`ind_ief` | `Adj Close` | 同上 | daily_adjclose.csv の定義原典は未取得 |
| SOXLの表示・Sheets G/H列 | `obs_soxl_close`／`obs_soxl_open` | SOXL `Close`／`Open` | 分割は上流で遡及調整され得る、分配金は未調整 | 「当時の約定価格」「完全無調整」と呼ばない |
| Sheets B列（SOXX終値） | `ind_soxx` の対象日値 | SOXX `Adj Close` | 指標と同じ | 列の意味を「指標基準のSOXX終値」と明記 |
| 将来の損益・分配金台帳 | （今回定義しない） | 実約定・証券会社記録 | — | 指標用の調整価格を執行価格・原価にしない |

- 指標に調整済み系列を使うこと自体は分配金の二重計上ではない。二重計上は、損益計算で調整済みリターンを使いさらに現金分配を足す場合に起きる。台帳は株数・原価・現金分配を別管理し、Adj系列を入れない。
- 分割：Yahooの `Close` は過去分が分割で遡及調整され得る。既に書いたSheets行は書込時点の値のまま残し、後日の再取得値で上書き・再計算しない。台帳側は分割イベントで株数・原価を処理する（後工程）。SOXLの過去分割：2015-05-20（4:1）、2021-03-02（15:1）（daily.jsonの記載）。

### 2.3 案の比較と推奨

| 観点 | 案A：auto_adjust=True を明示 | 案B：auto_adjust=False、用途別に選択（推奨） |
|---|---|---|
| 指標値 | 現候補と同一 | `Adj Close` をそのまま使うので**現候補と同一**（auto_adjustは Adj Close を Close に改名するだけ） |
| SOXL表示の意味 | 分配金調整後。次の権利落ちで過去値が変わる | 分配金未調整の観測値。研究の ohlcv（split-adjusted only）と同種 |
| 1回の応答から両系列 | 調整前系列は別取得が必要（整合性の検査が増える） | 同じ応答から取れる |
| 取り違え | `Close` が実は調整済みという暗黙の意味が残る | 列名で区別。ただし `Close` を指標に使う誤りを試験で防ぐ必要 |
| Adj Close欠落 | 比率1として黙って通る | 同じく黙って通る（2.1）。下記の検査で一部を検出 |

**[推奨] 案B。** 指標を変えずに表示価格の意味を固定でき、既存Sheets・研究との対応も説明しやすい。「全部False」ではなく、指標は調整済み系列のままである点が要点。

### 2.4 取得時点・改訂・欠落・取り違えの扱い

- **取得範囲はDで閉じる**：`start` = Dから遡ってN=260セッション目、`end` = D＋1暦日（exclusive）。`period="1y"` は使わない。当日未確定行の混入と、取得時刻で窓が動くことを避ける。`end` の境界解釈（タイムゾーン）は[未検証]、実依存オフライン試験で確認する。
- **観測時刻の記録**：取得完了時刻（UTC）、yfinance版、取得引数を実行ログと完了サマリに残す。Adj Closeは将来の分配金で遡って変わるため、指標値は「その時点で観測した値」として扱い、後日再計算で上書きしない。
- **欠落時は停止**：対象日のどの必要値が欠けてもエラー（現候補の方針を維持）。Adj Close→Close、前日値、古い共通日への代用をしない。
- **調整欠落の疑い検査[推奨・未検証]**：`actions=True` で配当イベントを同時取得し、窓内に分配金がある銘柄で `Adj Close/Close` が全行1のままならエラーにする。誤検出・見逃しの率は実データ未検証のため、採用は6.1 Sol Highの判断とする。
- **取り違え防止**：計算関数の引数を系列名で受け、`ind_*` 以外を指標に渡せない形にする。試験で「Close を渡すと値が変わる」ことを確認する。
- **RSIの窓依存**：現候補は取得した全履歴から ewm(adjust=False) で計算するため、開始日で値がわずかに動く。N固定でこの揺れを再現可能にする。研究の rsiWilder は2010年からのSMA初期化で、理論上の差は約250行後に (13/14)^250 ≈ 1e-8 程度だが、実データ比較は[未検証]。

### 2.5 依存版の固定（方針は採用済み、内容は推奨）

- 直接依存：yfinance 1.7.0／pandas 2.3.3／numpy 2.2.6／requests 2.34.2／gspread 6.2.1／oauth2client 4.1.3。新規に exchange_calendars 4.13.2（必須依存 pyluach・korean_lunar_calendar・toolz・tzdata）。
- **[事実]** exchange_calendars 4.13.2 は Python>=3.10、pandas>=1.5、numpy>=1.26.4、tzdata>=2025.2 を要求。固定しないと pandas 3.x が入る（今回の使い捨て環境では pandas 3.1.0 が入った）。
- **[推奨]** Python 3.10.20 の環境で全推移依存を `requirements.lock.txt`（ハッシュ付き）に固定し、ワークフローは `pip install --require-hashes -r requirements.lock.txt`。`runs-on` は `ubuntu-24.04` 等に固定。
- 限界：Yahoo側APIの仕様変更・データ改訂は固定できない。curl_cffi等のバイナリwheelはOS差の影響を受け得る。tzdata固定は将来の時刻規則変更に追随しない。直接依存の固定だけで「完全再現」と呼ばない。

### 2.6 決定前に必要なもの・保留する結論

- 現候補と案Bの指標値同一性は、実装コード上の帰結として確認した段階。合成入力によるオフライン試験で数値一致を確認する（Sonnet作業）。
- yfinanceの `Adj Close` と研究の adjClose／daily_adjclose.csv の一致は[未検証]。実データ取得の許可が出るまで「研究と同一定義」とは書かない。
- 旧Actions当時の価格定義、約44,683／44,460ドル差の原因は本書で扱わず、保留のまま。

## 3. B. 対象セッションの独立決定

### 3.1 確認できた事実

- **[事実] NYSE公式**：2026年の残り休場は11/26、12/25。短縮取引（13:00 ET終了）は2026-11-27、12-24、2027-11-26、2028-07-03、2028-11-24。core取引は9:30〜16:00 ET（NYSE Arca含む）。2028年まで公表済み。
- **[事実]** exchange_calendars 4.13.2 の XNYS は2025〜2028の休場・短縮日が上記公式表と一致（2025-01-09の臨時休場も含む）。XNAS（SOXX・IEFの上場市場）との差は0。既定ではカレンダー範囲が「実行日から約1年先」で、範囲外の日付は `DateOutOfBounds` 例外になる。
- **[事実] GitHub**：scheduleは既定でUTC、IANAタイムゾーン指定も可。高負荷時に遅延し、十分高負荷なら**ジョブが破棄され得る**。毎時0分は高負荷。既定ブランチのみ。公開リポジトリは60日無活動で自動無効化。`github.event.schedule` で起動元のcron文字列を参照できる（予定時刻そのものは得られない）。
- **[事実]** 現行cron `30 21 * * 1-5`（UTC）：夏時間は17:30 ET、冬時間は16:30 ET（終値後30分）。JSTは通年で翌朝6:30。2026-11-01に冬時間へ移る。

### 3.2 カレンダー方式の比較

| 候補 | 評価 |
|---|---|
| exchange_calendars XNYS（版固定）＋公式表の照合（推奨） | 規則・臨時休場・短縮・タイムゾーン込み。公式表と2028年まで一致を確認。新依存が増える |
| pandas_market_calendars 5.5.0 | 内部で exchange_calendars>=3.3 に依存。層が増えるだけで利点が小さい |
| 自前の休場リスト | 依存は増えないが、短縮取引・臨時休場・保守の誤りを自前で負う |
| 単純な平日計算・JST前日・データ最終日 | 採らない（依頼の禁止事項） |

**[推奨]** XNYSを使い、`CALENDAR_VERIFIED_THROUGH = 2028-12-31`（公式表と照合済みの最終日）を定数で持つ。Dがこれを超えたら `CALENDAR_EXPIRED` で停止し、公式表の再照合と版更新を求める。臨時休場がカレンダーより後に決まった場合は、カレンダー上は営業日なのにデータ行が無い→データ異常として停止（安全側に失敗、正常扱いにしない）。

### 3.3 用語と時刻

- `T`：実行開始時刻（ランナー時計、UTC）。ログに記録。
- `F`：推定予定時刻。`github.event.schedule` のcron文字列が期待値と一致するときだけ、「T以前で直近のcron一致時刻」として計算する。**推定**であり、予定時刻を取得したとは書かない。前提は遅延が次のcron一致（≥24時間後）より短いこと。
- `D`：対象セッション。`close(D)`、`open(next(D))` はカレンダーから。`GRACE`：上流日足の確定待ち。**[推奨・未検証]60分**。観測した遅延の上限保証ではない。

### 3.4 決定手順（擬似コード）

```
mode ← schedule | manual_auto | replay(入力日)
if calendar の読込失敗: return CALENDAR_ERROR
if mode == schedule:
    if event.schedule != 期待cron: return CONFIG_ERROR
    F ← 直近cron一致時刻(≤T)
    D ← F の America/New_York 日付        # T の日付ではない（NY日付跨ぎ対策）
    if D > VERIFIED_THROUGH: return CALENDAR_EXPIRED
    if D が XNYS セッションでない: return HOLIDAY_SKIP
elif mode == manual_auto:
    if ある X で open(X) ≤ T < close(X)+GRACE: return TOO_EARLY(X)
    D ← close(S)+GRACE ≤ T を満たす最新セッション S
    if D > VERIFIED_THROUGH: return CALENDAR_EXPIRED
else:  # replay
    D ← 入力日（YYYY-MM-DD 厳格）
    if D がセッションでない or D > VERIFIED_THROUGH: return INPUT_ERROR / CALENDAR_EXPIRED
    if T < close(D)+GRACE: return TOO_EARLY(D)
if mode != replay:
    if T < close(D)+GRACE: return TOO_EARLY(D)
    if T ≥ open(next(D)): return OUT_OF_WINDOW     # 次セッション開始後は通常運用として扱わない
E ← D で終わる N=260 セッション列（カレンダー）
取得(start=E[0], end=D+1日, auto_adjust=False, actions=True)
検査: 日付列 == E（欠落行・余分行・順序・重複）→ 不一致は DATA_ERROR
検査: 対象日元価格、指標入力（SOXX全N行、SPY/IEF直近21行）の有限・正 → DATA_ERROR
計算 → 記録 → 完了サマリ → NORMAL / REPLAY_DONE
```

### 3.5 状態・終了・通知

| 状態 | 終了 | 取得 | Sheets | 通知 |
|---|---|---|---|---|
| NORMAL | 0 | する | 追記（重複時は3.7） | 完了サマリ |
| HOLIDAY_SKIP | 0 | しない | しない | 「休場のため対象セッションなし」の短いサマリ（実行ごとサマリの採用事項に整合） |
| REPLAY_DONE | 0 | する | 既定でしない | 「再現（手動指定）」と明記したサマリ |
| TOO_EARLY | 1 | しない | しない | 運用エラー「時刻尚早（未確定）」。条件未達とは書かない |
| OUT_OF_WINDOW | 1 | しない | しない | 運用エラー「実行遅延が次セッション開始を超過」 |
| CALENDAR_ERROR／CALENDAR_EXPIRED | 1 | しない | しない | 運用エラー（カレンダー不明・期限切れ） |
| CONFIG_ERROR／INPUT_ERROR | 1 | しない | しない | 現候補の設定エラー経路 |
| DATA_ERROR | 1 | した | しない | 現候補のデータ検査エラー経路＋欠落日 |

既存の採用事項（異常は非0、Sheets失敗は部分失敗サマリ試行後に非0、自動再送なし、売却推奨なし）は変えない。

### 3.6 境界例（推奨cron `40 22 * * 1-5` UTC、GRACE 60分を仮定。机上の例で、実行した試験ではない）

| # | T（UTC） | 状況 | 結果 |
|---|---|---|---|
| 1 | 2026-10-27 22:40 | 夏時間の通常日（18:40 ET、JST 10/28 07:40） | NORMAL、D=10-27 |
| 2 | 2026-11-02 22:40 | 冬時間初日（17:40 ET） | NORMAL、D=11-02 |
| 3 | 2026-11-26 22:40 | 感謝祭休場 | HOLIDAY_SKIP、取得なし |
| 4 | 2026-11-27 22:40 | 短縮取引（終了18:00 UTC） | NORMAL、D=11-27 |
| 5 | 2026-10-30 22:40 | 金曜。土日はcronが起動しない | NORMAL、D=10-30（JST土曜朝） |
| 6 | 2026-10-28 05:10（F=10-27 22:40） | 遅延でNY日付が10-28へ跨ぐ | NORMAL、D=10-27（Tの日付を使わない） |
| 7 | 2026-10-28 14:00（F=10-27 22:40） | 遅延が次セッション開始（13:30）を超過 | OUT_OF_WINDOW、非0 |
| 8 | 2026-10-27 19:00、手動・日付なし | 取引時間中 | TOO_EARLY（X=10-27）、非0 |
| 9 | 手動・入力2026-10-23 | 過去日の再現 | REPLAY_DONE、Sheets既定なし |
| 10 | 手動・入力2026-11-26 | 休場日を指定 | INPUT_ERROR |
| 11 | D=2029-01-02 | 照合済み期限超過 | CALENDAR_EXPIRED |
| 12 | 通常日、データに10-21行が全銘柄とも無い | 行丸ごと欠落 | DATA_ERROR（行数・最終日だけでは検出できない例） |

### 3.7 再実行と重複

- 完了サマリの重複は許容する（実行ごとサマリの採用事項）。再実行・手動・再現の区別をサマリ先頭に必ず表示し、黙って抑止しない。
- Sheets価格行は対象日ごとに1行を目標とする。**[推奨]** NORMALで追記前にA列を読み、同じ対象日があれば追記せず `sheets_state=duplicate_skipped`（終了0、サマリに表示）。REPLAYは既定で書かない。A列の表示形式（日付自動変換）による照合漏れの可能性は[未検証]で、実Sheetsの確認が必要。
- 保有・約定台帳、自動発注、通知による状態更新は追加しない。

### 3.8 スケジュールと確認期限

| 案 | ET（夏／冬） | JST | 猶予 |
|---|---|---|---|
| 現行 `30 21` UTC | 17:30／16:30 | 06:30 | 冬は30分。GRACE 60分だと冬に毎日TOO_EARLY |
| **推奨** `40 22` UTC | 18:40／17:40 | 07:40（通年同じ） | 100分以上。毎時0分を避ける |
| `40 17` America/New_York | 17:40／17:40 | 06:40／07:40 | 一定。タイムゾーン指定機能への依存が増える |

- **[推奨・未採用]** 確認期限は **JST 09:00**。07:40起動から80分の余裕。この時刻までに完了サマリも運用エラーも届かなければ、ユーザーがActions画面を見る。根拠はGitHub文書の「遅延・破棄があり得る」という記載のみで、遅延の上限は保証されない。未起動は同じワークフローの中から検知できない。新しい監視・有料サービスは導入しない。

## 4. C. 判断表

| 項目 | 区分 | 内容 |
|---|---|---|
| yfinance既定とauto_adjustの動作、Adj Close黙認代用 | 事実 | 1.7.0の実装で確認 |
| NYSE休場・短縮（〜2028）とXNYS 4.13.2の一致 | 事実 | 公式表と照合 |
| GitHub schedule の遅延・破棄・UTC・event.schedule | 事実 | 公式文書 |
| 案B（auto_adjust=False、用途別） | 推奨 | 6.1 Sol High判断（指標値を変えないため）。SOXL表示の意味変更はユーザーへ報告 |
| XNYS固定版＋照合期限2028-12-31 | 推奨 | 6.1 Sol High判断 |
| cronを `40 22` UTCへ変更 | 推奨・**ユーザー判断** | 通知時刻がJST 06:30→07:40に変わるため |
| 確認期限JST 09:00 | 推奨・**ユーザー判断** | 本人の運用負担に関わる |
| GRACE 60分 | 推奨・未検証 | 6.1 Sol High判断。実運用ログで見直し |
| Sheets重複スキップ、列追加（観測時刻・モード）の要否 | 未決・**ユーザー判断** | 列追加は既存シートの形を変えるため今回は推奨しない |
| 調整欠落の疑い検査をエラーにするか | 未決 | 6.1 Sol High判断 |
| yfinance Adj Closeと研究データの一致、`end`境界、上流確定時刻 | 実データ未検証 | 実取得の許可後 |

承認済み5項目は再承認対象にしない。

## 5. Sonnetへ渡す最小実装単位（本仕様の採否後）

工程順（0eb801cのSTATUS更新）に従い、以下は[売買ルール検討](../tasks/TRADING_RULE_REVIEW_QUEUED.md)の後に発行される想定。本書は売買ルールの採否に触れない。

1. **依存固定**：`requirements.lock.txt`（3.10.20、ハッシュ付き、exchange_calendars含む）、ワークフローのinstall行とrunner固定。実依存試験を固定セットで再実行。
2. **価格取得**：`fetch_prices(D, sessions)` を start/end 指定・auto_adjust=False・actions=True に変更し、`ind_*`／`obs_soxl_*` を返す。指標値が旧方式と同一になる合成入力試験、Close取り違え試験。
3. **対象セッション**：`session.py`（3.4の手続き、時計・カレンダー・event.schedule を引数で注入）。3.6の12行を単体試験に。`TARGET_SESSION_DATE` 必須を廃し、workflow_dispatch の任意入力 `replay_date` へ。
4. **連続性検査**：日付列とEの完全一致、欠落・余分行のエラー文言（対象日・欠落日を表示、秘密なし）。
5. **NT-01**：子プロセス試験の全URL・Locationをループバックへ限定。
6. **スケジュール・Sheets重複**：ユーザー判断が出た部分だけ反映。

切替前の確認：固定セットでの全オフライン試験、実データ取得による `end` 境界・Adj Close比較（別許可）、cron変更後の初回実行の観測（別許可）。main反映・停止解除・Actions起動・実送信・実Sheetsは本書の範囲外で未承認。

## 6. 変更の有無

本書の追加のみ。コード・設定・ワークフロー・Secrets・Sheets・Discordは変更していない。exchange_calendars の照合は作業環境の使い捨て仮想環境で行い、リポジトリには入れていない。
