# 価格・対象セッション契約 — 4論点の限定補完（仕様案・未採用）

作成：2026-10-26（日本時間）。担当：Claude Opus 5.5（依頼：[DATA_SESSION_FINALIZATION_OPUS55_REQUEST](../tasks/DATA_SESSION_FINALIZATION_OPUS55_REQUEST.md)）。
開始SHA：`bd9dc17a5c77f1158c0f9299a9672e772a5c7e3b`（docs/v2-roadmap-20261023）。保存先ブランチ：docs/data-session-finalization-20261026。
土台：[旧草案6dbc71c](https://github.com/Rocky009-jp/soxl-alert/blob/6dbc71cf1e25bd4a407f06330c4134cfc2f34298/docs/specs/DATA_SESSION_CONTRACT_DRAFT.md)、[受領時の留保](../reviews/DATA_SESSION_RECEIPT_20261026.md)、[採用済み暫定仕様](INTERIM_NOTIFICATION_SPEC.md)、[API保留の判断](../decisions/API_DEFERRAL_AND_RECOVERY_20261026.md)。候補 `920e695` と main `31144d9` は今回不変。

**運用前提（ユーザー、2026-10-26）**：日足単位でタイミングを判定する仕組み。米国市場の引け後、早朝に確定済みの終値を元に通知し、ユーザーはその夜の寄付きに合わせて手動で買う。本書は分足・NBBOを前提にしない。通知の対象は確定済みのセッション D、発注を想定する時点は `open(next(D))`。これは表示用の情報で、約定価格の推定ではない。

本書は**未採用の仕様案**。実装・試験合格ではない。本文で触れない事項（用途別の系列表、XNYS採用、依存固定の方針など）は旧草案のまま。

**静的に読んだもの（実行していない）**
- yfinance 1.7.0：`utils.parse_quotes`（548〜573行）、`utils.auto_adjust`（506〜523行）、`scrapers/history.py`（300〜394行）。前回取得したwheelを再読した。
- gspread 6.2.1：wheelを取得し `Worksheet.append_row`（1781行〜）を読んだ。導入・実行はしていない。
- 旧main（`origin/main` の main.py）：Sheetsへの書き込み部分。
- GitHub公式文書（2026-10-26確認）：[同時実行制御](https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs)、[再実行](https://docs.github.com/en/enterprise-cloud@latest/actions/managing-workflow-runs/re-running-workflows-and-jobs)、[schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

**今回やっていないこと**：市場データの取得、ライブラリの導入・実行、95件／17件／252件の再実行、Actions・Discord・Sheetsの操作。

## 1. 調整価格の起源と欠落

### 事実
- `parse_quotes` は応答の `indicators` に `adjclose` が無いと、`Adj Close` に `close` の配列をそのまま入れる。出来上がった表には `Adj Close` 列が普通に存在する。したがって表の列や値だけでは、黙って代用されたことを判別できない。
- `history.py` は `from yfinance import utils` で読み込み、`utils.parse_quotes(data["chart"]["result"][0])` を呼ぶ（392行）。この引数には Yahoo の `meta`（symbol を含む）と `indicators` が入っている。
- `repair=False` の場合、`Adj Close` を書き換える修復処理（`_fix_bad_div_adjust` など）は走らない。

### 比較
| 案 | 確認できること | 確認できないこと | 評価 |
|---|---|---|---|
| X1：表だけで検査（列の有無、有限、比率） | 値の明らかな異常 | 代用されたかどうか | 単独では不足 |
| **X2：版固定のうえで `yfinance.utils.parse_quotes` を包み、銘柄ごとに `adjclose` キーの有無と長さを記録（推奨）** | 既知の黙認代用の経路（キーが無い場合）を、応答の構造から検出できる | Yahoo が返した adjclose 自体が誤り、配当を取りこぼしている、close と同じ値、後日修正される、といった上流の品質 | 採用案 |
| X3：chart API を自前で呼んで解析 | 応答全体 | — | API保留の方針と新規実装の禁止に反するため不採用 |

### 推奨する契約
- 包む処理は取得の直前にだけ入れ、取得後に元へ戻す。`yfinance.__version__ == "1.7.0"` で、`utils.parse_quotes` が存在するときに限り有効にする。条件を満たさなければ取得へ進まない。記録の鍵は `meta.symbol`。取得は `threads=False` にして順序を決定的にする。
- 状態と進め方（対象は指標に使う SOXX・SPY・IEF。SOXL の Adj Close は使わないので記録だけ残す）：

| 状態 | 条件 | 指標計算・Sheets | 終了 | サマリ |
|---|---|---|---|---|
| ADJ_OK | 3銘柄とも `adjclose` キーあり、長さが quote と一致、値は有限かつ正 | 進む | — | 「調整列：応答に存在」 |
| ADJ_ABSENT | どれか1銘柄でもキーが無い、または長さが違う | 進まない | 1 | 運用エラー「調整価格が応答に無い（終値で代用され得る）」 |
| ADJ_ORIGIN_UNKNOWN | 版が違う、関数が無い、記録の無い銘柄がある | 進まない | 1 | 運用エラー「調整価格の起源を確認できない」 |
| ADJ_ANOMALY | 対象窓のどこかで Adj Close が非有限・0以下、または `Adj/Close > 1+1e-6` | 進まない | 1 | 運用エラー |
| ADJ_NOTE（警告） | 比率が時系列で減少する、または窓内に配当イベントがあるのに比率が全行1 | 進む | 終了値に影響しない | 「調整の整合に注意（参考判定）」 |

- ADJ_NOTE は経験則による参考判定であり、代用されていないことの証明ではない。許容幅 1e-6 は丸め誤差の目安で、[未検証]。実データで一度確認したあと、警告のままにするかエラーに格上げするかを6.1 Sol Highが決める。
- 試験で確認できる範囲：合成の応答辞書を `parse_quotes` に渡し、キーがある場合と無い場合で状態が正しく分かれることまで。上流データの品質を検知できるかのような試験は作らない。

## 2. RSIの窓と価格方式の変更

### 2つの変更を分けて扱う
- **(a) 列の対応**：同じ応答・同じ窓なら、`auto_adjust=True` の `Close` と `auto_adjust=False` の `Adj Close` は同じ浮動小数配列になる。`utils.auto_adjust` は `Adj Close` を `Close` に名前を変えるだけで、`rounding=False` が既定だからである。これは実装を読んだうえでの帰結であり、合成データの試験で完全一致を確認する。
- **(b) 窓の変更**：候補は実行時点から `period="1y"` で約250〜252セッションを取る。これを「Dで終わるN=260セッション」に変えると、RSI（`ewm(alpha=1/14, adjust=False)`）の始点が変わる。2つの系列の差は、共通区間の長さを k として最大で `(13/14)^k` 倍に縮む。k≈250 のとき約 9e-9 で、RSIではおおむね 1e-6 ポイント以下と見込める。これは仮定付きの上界の見積もりであり、**完全同一とはいえない**。値が閾値55（売却を再開すれば75も）のごく近くにあれば、判定が反転する可能性は残る。

### 推奨（1つに固定する）
- 取得窓：XNYS で D を末尾とする連続260セッション（E）。`start=E[0]`、`end=D+1暦日`（exclusive）。
- RSI：E 全体の SOXX `Adj Close` を入力にし、現在の式（ewm, adjust=False, 初期値は窓の最初の差分）をそのまま使う。SMA200 は直近200行、SHD は `iloc[-21]` 比で変更しない。研究側の Wilder 方式（SMA初期化、2010年起点）へは合わせない。差は既知の相違として記録する。
- 必要な履歴：E の260行すべてが揃っていること（2.の検査は §3.4）。対象日の境界は「Eの最後＝D」。
- 新しい売買閾値は提案しない。

### 受入の分け方
- 同じ窓での列対応：完全一致（許容差0）。
- 窓の変更による差：合成系列で、1y相当の窓と260セッションの窓の差を測って記録する。合否は「差が見積もりの範囲内」かどうかで判定し、「差が0であること」は求めない。閾値近傍で反転し得る合成例も1件入れ、それは仕様どおりの記録として扱う（失敗ではない）。

## 3. 対象日と遅延

### 利用できる情報と限界
- 使えるもの：`T`（ランナーの時計、UTC）、`github.event_name`、`github.event.schedule`（cron 文字列だけ）、`github.run_attempt`、workflow_dispatch の入力。
- 予定時刻そのものは得られない。再実行は元の SHA・ref を使う（公式文書）。payload がどこまで同じになるかは文書から確定できない。そのため、再実行では `event.schedule` を予定日の手掛かりに使わない。
- 次の cron 一致を越える遅延は、その次の起動と区別できない。

### 方針の変更（旧草案との差）
**D は「T 時点でカレンダー上確定した最新のセッション」と定義する**（`close(S)+GRACE ≤ T` を満たす最新の S）。推定予定時刻 C（T 以前で直近の cron 一致時刻）は D を決めるためではなく、**定期起動が D と整合しているかの検査**にだけ使う。元の予定日を取得したとは書かない。GRACE＝60分は日足が確定したことの保証ではない。

### 決定手順
```
mode ← SCHEDULED(schedule かつ run_attempt==1) | RERUN(schedule かつ run_attempt>1)
       | MANUAL(dispatch・日付なし) | REPLAY(dispatch・日付あり)
calendar 読込失敗 → CALENDAR_ERROR
REPLAY: D←入力（厳格に YYYY-MM-DD）。セッションでない → INPUT_ERROR
その他: ある X で open(X) ≤ T < close(X)+GRACE → UNCONFIRMED(X)
        D ← close(S)+GRACE ≤ T を満たす最新の S
D > VERIFIED_THROUGH(2028-12-31) → CALENDAR_EXPIRED
REPLAY かつ T < close(D)+GRACE → UNCONFIRMED(D)
SCHEDULED: event.schedule ≠ 期待 cron → CONFIG_ERROR
           C ← T 以前で直近の cron 一致時刻、Dc ← C の NY日付
           Dc がセッションでない → NO_NEW_SESSION（休場か長時間遅延かは区別できない）
           Dc < D → DELAYED_MISMATCH（前日の起動が遅れて、次のセッション確定後に来た疑い）
           Dc == D → 通常
取得・検査（§1, §3.4）→ 計算 → Sheets（§4）→ サマリ
```
`T ≥ open(next(D))` は UNCONFIRMED か、D が後ろへずれるかのどちらかに必ず含まれる。そのため旧草案の OUT_OF_WINDOW は不要になった。

### 3.4 データの連続性
取得した日付列が E と完全に一致することを検査する。欠落した日・余分な日・順序・重複の違反はどれも DATA_ERROR とし、欠落日を表示する。D の行が無い場合は「対象日行なし（上流未着の可能性）」とし、古い日付の行で正常終了しない。自動で取り直すことはしない。

### 状態・終了・通知（実装者用の最小表）
| 状態 | 終了 | 取得 | Sheets | 通知 |
|---|---|---|---|---|
| NORMAL（SCHEDULED） | 0 | する | §4 | 完了サマリ（T、C、遅延分数、D、次の寄付き `open(next(D))` の JST を表示） |
| MANUAL_DONE／RERUN_DONE | 0 | する | §4 | 完了サマリ（先頭に「手動」「再実行」と表示） |
| REPLAY_DONE | 0 | する | 書かない（判断③） | 「再現」と表示したサマリ |
| NO_NEW_SESSION | 0 | しない | しない | 「新たに確定したセッションなし（休場または遅延）。直近の確定は D、次の寄付きは open(next(D))」 |
| UNCONFIRMED | 1 | しない | しない | 運用エラー「未確定（取引中・確定待ち）」 |
| DELAYED_MISMATCH | 1 | しない | しない | 運用エラー「起動遅延の疑い。予定 Dc、確定済み D」 |
| CALENDAR_ERROR／CALENDAR_EXPIRED／CONFIG_ERROR／INPUT_ERROR | 1 | しない | しない | 既存の設定・運用エラー経路 |
| ADJ_ABSENT／ADJ_ORIGIN_UNKNOWN／ADJ_ANOMALY／DATA_ERROR | 1 | した | しない | 既存のデータ検査エラー経路 |

異常時の非0終了、毎回のサマリ、自動再送なし、売却推奨なしという採用済みの規則は変えない。

## 4. Sheets の重複・競合・旧行

### 事実
- gspread 6.2.1 の `append_row` は既定で `value_input_option=RAW` の values.append を使う。追記は冪等ではない。通信が途中で失敗すると、書き込まれたかどうかが分からない。
- 旧mainも候補も、A列にはデータ最終行の日付を `YYYY/MM/DD` の文字列で書く。旧mainは古い共通日に落ちた行を書いた可能性がある。旧行の価格定義（当時の yfinance の版と既定値）は分からない。
- GitHub の concurrency はリポジトリ単位で、同時に実行できるのは1つまで。既定（`queue: single`）では待機中の実行が新しい実行に置き換えられて**キャンセルされる**。`queue: max` なら最大100件まで待機できる（公式文書）。

### 推奨手順（1行であることは保証しない）
1. ワークフローに `concurrency: {group: soxl-alert-run, cancel-in-progress: false, queue: max}` を付ける（案。`queue: max` の実動作は[未検証]）。直列にできるのはこのリポジトリの実行どうしだけで、手動編集や他のクライアントによる変更は保証しない。
2. 追記の前に A列を読む。照合は日付を正規化して行う（`YYYY/MM/DD` と `YYYY-MM-DD` を受け付ける）。読み取りに失敗したら追記せず、`sheets_state=failed`（既存規則どおり部分失敗として非0）。
3. D の行が無ければ追記し、続けて再読込して D の行数を数える。1行なら ok、2行以上なら `duplicate_detected`（非0、削除しない）。追記がエラーまたは結果不明だった場合も再読込し、1行なら `ok_after_unknown`（0）、0行なら failed、2行以上なら duplicate_detected とする。
4. D の行が既にある場合：B〜H列が小数点以下2桁の丸め後に一致すれば `existing_same`（追記しない、0）。違えば `existing_conflict`（追記・上書きしない、非0、サマリに両方の値を表示）。日付を解釈できない行は数だけ数えてサマリに出し、処理は止めない。
5. 既存の行は削除も上書きもしない。旧行の価格定義は「不明」とし、切替日を資料に記録する。列やタブを足して定義の版を持たせる案は、既存シートを変えるため承認前の案にとどめる。
- Sheets を無効にした場合、設定が欠けている場合、部分失敗の場合の規則は採用済みのものを変えない。

## 5. 受入ケースの設計（未実施）
| # | 入力 | 期待 |
|---|---|---|
| 1 | 合成応答で SOXX に `adjclose` キーが無い | ADJ_ABSENT、非0、指標・Sheets 0回 |
| 2 | yfinance の版が 1.7.0 以外を装う | ADJ_ORIGIN_UNKNOWN、取得へ進まない |
| 3 | 同じ合成表に `auto_adjust` を適用 | `Close` と `Adj Close` が完全一致し、指標も完全一致 |
| 4 | 合成300セッション、252窓と260窓 | RSI の差を記録、見積もりの範囲内 |
| 5 | T=2026-11-02 22:40Z（冬時間）、schedule | NORMAL、D=11-02 |
| 6 | T=2026-11-26 22:40Z（感謝祭） | NO_NEW_SESSION、取得なし、0 |
| 7 | 10-28 の起動が 10-29 05:10Z に遅れる | NORMAL、D=10-28（NY日付を跨いでも正しい） |
| 8 | 11-03 の起動が 11-04 22:10Z に遅れる | DELAYED_MISMATCH、非0 |
| 9 | 手動、T=10-27 19:00Z（取引中） | UNCONFIRMED、非0 |
| 10 | schedule の再実行（run_attempt=2） | RERUN として T から D を決める |
| 11 | 取得表から D-5 の行が全銘柄とも欠ける | DATA_ERROR、欠落日を表示 |
| 12 | Sheets に D が既にあり値が違う／追記が timeout した後の再読込で1行 | existing_conflict（非0・上書きなし）／ok_after_unknown（0） |

## 6. ユーザー判断表（すべて未承認・未変更）
| 項目 | 推奨 | 影響 |
|---|---|---|
| ① 通知時刻 | cron を UTC 22:40（JST 07:40、毎時0分を避ける） | 現行の JST 06:30 から遅くなる。冬時間でも終値後100分以上あり、GRACE 60分を満たす。現行のままだと冬は毎日 UNCONFIRMED になる |
| ② 未着確認 | JST 09:00 にサマリもエラーも無ければ、本人が Actions 画面を見る | 未起動や破棄は内部から検知できない。80分の余裕は遅延の上限を保証しない |
| ③ Sheets の既存行・再実行 | §4 の手順。replay は書かない | 同じ日に値が違う行があると非0で知らせる。旧行は変えない。concurrency を付けるとワークフローが変わる |

技術的な事項（ADJ の扱い、N=260、GRACE、状態表）は6.1 Sol Highが判断する。承認済みの5項目は再質問しない。

## 7. Sonnetへ渡す最小差分（実装依頼はまだ出さない）
- `fetch_prices(D, E)`：`auto_adjust=False`、`actions=True`、`threads=False`、start/end 指定、parse_quotes の記録、`ind_*` と `obs_soxl_*` を返す。
- `session.py`：§3 の手順。時計・カレンダー・event・run_attempt を注入できるようにする。`TARGET_SESSION_DATE` の必須を外し、dispatch の入力 `replay_date` を加える。
- 連続性と ADJ の検査、§4 の Sheets 手順、サマリへの mode／T／C／D の表示。
- ハッシュ付きの依存固定（exchange_calendars 4.13.2 を含む）、NT-01、`concurrency` 案、cron（判断①の後）。
- 未実施の確認：上記12ケース、Python 3.10 の固定環境での全オフライン試験、実データでの `end` 境界・ADJ_NOTE の頻度・`queue: max` の動作（いずれも別途許可が必要）。

## 8. 4論点に残るもの
- Yahoo が返す adjclose の品質は、引き続き検知できない。
- 窓変更による RSI の差は0ではない。
- 長時間遅延は次の起動と区別できない。休場と遅延も NO_NEW_SESSION として同じ扱いになる。
- Sheets で1行しかないことは保証できない。旧行の価格定義は不明のまま。

いずれも実データ・実運用では未検証。
