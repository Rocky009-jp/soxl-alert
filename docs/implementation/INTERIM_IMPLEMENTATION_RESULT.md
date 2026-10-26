# 暫定通知仕様の限定実装・オフライン試験結果（候補・未適用）

作成：Claude Sonnet 5.5（6.1 Sol High指定）／2026-10-26。実際のモデル選択は利用環境側で確認。

## 1. 版

| 項目 | 値 |
|---|---|
| 資料ブランチ先端（読取時） | `07651d576527efd64ce714f85992c937b0ffc0bf`（`docs/v2-roadmap-20261023`） |
| 本番停止コミット（実装基点） | `31144d9b6af8a6c920ad53c395cd550e8c48a7fa`（main先端と一致を確認） |
| 実装ブランチ | `feat/interim-notification-20261026` |
| 保存SHA | 最終報告に記載（コミット後に確定） |

## 2. 変更ファイル

| ファイル | 内容 |
|---|---|
| `soxl_checks.py`（新規） | データ検査と指標計算。ネットワーク・Sheets・通知に依存しない |
| `soxl_notify.py`（新規） | 通知の1回送信（タイムアウト付き）と本文組み立て |
| `main.py` | 境界（取得・書込・送信）を差し替え可能にした実行本体。旧売り判定・旧通知文は削除 |
| `.github/workflows/schedule.yml` | 停止条件`if: ${{ false }}`とcron・トリガー維持。envに`SHEETS_ENABLED`・`TARGET_SESSION_DATE`追加、`Run script`に`id: run`、`Report setup failure`ステップ追加 |
| `tests/`、`requirements-test.txt` | オフライン試験（pytest・PyYAML） |

## 3. 期待動作

- 入力：`DISCORD_WEBHOOK_URL`（必須）、`SHEETS_ENABLED`（`true`/`false`を明示。未設定・他値は設定エラー）、有効時は`GCP_CREDENTIALS`・`SPREADSHEET_ID`（欠落は設定エラー。無効設定とは別）、`TARGET_SESSION_DATE`（YYYY-MM-DD、必須）。
- 流れ：設定確認 → 取得 → データ検査 → 技術条件 → Sheets（有効時） → サマリ通知 → 終了コード。検査NGでは判定関数・Sheets追記に進まず、運用エラー通知を試みて非0。
- 検査：DataFrame/空/日付インデックス/昇順/重複/銘柄列/指定対象日の行/最新行＝対象日/4銘柄の対象日終値と SOXL始値の有限・正/SOXX直近200行・SPY・IEF直近21行が全て有限（NaN越しの持ち越し・古い共通日への後退を拒否）/指標の有限性。補完はしない。
- 技術条件：SOXX>200SMA、SHD<0、RSI<=55（従来の閾値・式のまま。旧式との一致を試験）。成立でも「購入推奨・購入可否の確定ではない」「保有状態は確認していない」「F&G目視未確認」と表示。
- 売却系：旧売り条件・過熱参考通知・売却/全額/緊急脱出の文言は実装しない。保有・原価は読まず、状態更新なし。
- Sheets失敗：握りつぶさず「部分失敗（記録失敗）」サマリの通知を試み、成否によらず非0。
- 通知：`requests.post`を1回、タイムアウト(5,15)秒、自動再送・再帰なし。2xx以外は`HTTP失敗（HTTP n）`、例外は`配信不明（型名）`。URL・応答本文・例外メッセージはログに出さない。
- pip等の失敗：`Run script`がスキップされ、かつ先行失敗がある場合のみ、追加依存なしの`curl`で固定文言を1回送る。本体が失敗した場合は本体が通知するため二重送信しない。報告の成否に関わらずジョブは先行の失敗のまま。

## 4. 試験

環境：Python 3.13.17、pandas 3.0.5、numpy 2.5.3、requests 2.34.2、pytest 9.1.1、PyYAML 6.0.3、curl 8.5.0。yfinance・gspread・oauth2clientは未導入（本体は遅延importで、試験は実データ取得・Sheets実アクセスをしない）。
ネットワーク遮断：`conftest.py`の自動fixtureでループバック以外の`socket.connect`と名前解決を拒否し、遮断自体も試験。通知・Sheets・取得は呼出し記録付きのフェイクに差し替え。秘密は合成文字列のみ。
コマンド：`python -m pytest -q` → **48 passed**（`test_main_flow.py` 41、`test_workflow_candidate.py` 7）。構文は`py_compile`で確認。静的解析ツールは未実施。
件数の区別：旧欠陥再現の14件、原稿の13行とは別の、今回新規の48試験。

## 5. 受入行の対応（今回11行）

| 行 | 確認内容 | 試験 |
|---|---|---|
| #1 | 条件未達でもサマリ1件、対象日・検査・F&G未確認・Sheets結果 | `test_case1_*` |
| #2 | 技術条件成立でも購入推奨にしない | `test_case2_*` |
| #3 | 最新元価格NaN（5列）で判定0回・Sheets0回・非0。窓内NaN、SHDの古い共通日後退も拒否 | `test_case3_*` |
| #4 | 古い/先の日付、始値のみ古い、履歴不足、列不足、空、逆順、重複、非日付、非表形式で拒否。tz付きは正規化して通る | `test_case4_*` |
| #5 | 書込失敗→write→post の順、部分失敗サマリ、非0、秘密非表示。無効設定と必須設定欠落の区別 | `test_case5_*`ほか |
| #6 | 明示HTTP失敗（500）と配信不明（Timeout）を別表示。再送なし。エラー経路で通知失敗でも再帰せず非0 | `test_case6_*` |
| #7 | 報告関数＝YAMLの`curl`ステップをローカルHTTPサーバで確認（204/500/接続不可/設定なし）、条件式・env・停止条件・トリガー不変。**実Actionsのpip失敗は未実施** | `test_workflow_candidate.py` |
| #8 | 机上確認のみ。未起動を内部処理で検知できず、終了コードも観測されない。確認期限超過で運用上「未確認」 | 試験なし |
| #9 | 保有依存の語句（0株・数量・初回等）が出ない | `test_case9_*` |
| #11 | 原価を読まず売却系文言なし | `test_case11_12a_*` |
| #12a | RSI高・SHD>=3.0の両方で売却/参考/過熱の文言なし | `test_case11_12a_*` |

対象外：#10（保有入力は後工程）、#12b（ON案は未採用）。

## 6. 未解決・本番切替前の条件

1. **対象セッションの決定方式（未決）**：現候補は`TARGET_SESSION_DATE`が`vars`未設定だと設定エラーで非0になる。cron実行で日付を与える方法、休日・短縮取引・夏冬時間・確定時刻・遅延は未解決。切替前に決める。
2. 確認期限（JST）、独立監視、手動再実行の重複防止は未決。
3. yfinanceの実依存版・列構造・調整価格の既定値は未確認（未導入）。実データでの動作は未検証。`fetch_prices`は従来の呼出しを保っているだけ。
4. Python 3.10（workflowの版）での試験は未実施（3.13で実行）。
5. 実Actions、Discord実配信・読了、Sheets実書込、GitHub失敗通知の本人確認は未実施。checkout失敗・Actions未起動・共通通知経路故障は報告を保証できない。
6. HTTP失敗の再試行方針は未決（自動再送なし）。成功ログと終了コードは試験済みだがmain反映・停止解除は未承認。
7. `Report setup failure`は、`Run script`が実行されたが本体が通知前に落ちる極端な場合（import失敗など）は対象外。この場合は本体の非0終了のみ。

## 7. 変更・送信

main・資料ブランチの実行コードは未変更。停止条件は維持。Actions起動・再実行、Discord送信、Sheets実アクセス、実データ取得、認証・通知先変更は未実施。

---

# 追記：ad83f9b の5指摘修正と Python 3.10・実依存のオフライン確認

作成：Claude Sonnet 5.5／2026-10-26。資料開始SHA `c6faf9e78b32dab6959485042fd67f06277cdc3d`、修正開始は候補 `ad83f9bf47c43f713e7cafb738f3de1bbb42705a`（先端は未変更を確認）。保存SHAは最終報告に記載。main・停止条件（`if: ${{ false }}`）・cron・トリガーは維持。

## 指摘への対応

| ID | 修正 | 確認 |
|---|---|---|
| IR-01 | curlの標準エラーを捨て（`-s`＋`2>/dev/null`）、`curl終了値`と`HTTP status`の固定文言だけを出力。1回送信・`--max-time 20`・リダイレクト非追従・先行失敗の維持は同じ | 不正な括弧・閉じ括弧・不正スキーム・不正ポート・改行・空白/波括弧・スキームなしの合成URL7種で、stdout/stderrにトークンも`curl:`も出ない。307＋合成Locationでも追従せず非0・要求1回・Location非表示。旧設定（`-sS`）に戻すと7件失敗することを確認 |
| IR-02 | SOXX全履歴の元価格が有限・正であることを検査（式・窓は不変、補完なし） | 先頭/1/30/59行目（200行より古い）に−5・0・NaN・±inf を入れた20ケースで、エラー・判定0・Sheets0・通知1・非0。正常入力のRSIは旧式と一致 |
| IR-03 | POSTに`allow_redirects=False`。FakePostが引数を記録 | 実Requests＋ループバックサーバで302/307/308とも遷移先へ要求せず、HTTP失敗・要求1回・非0。500とタイムアウト（接続不可）も維持。引数を外すと失敗することを確認 |
| IR-04 | 設定済みの対象日を`対象取引日`としてエラー通知に、`通知（日付）:`として送信結果ログに含める。日付未設定／不正は`対象日未確定`で、生の値は表示しない | 検査失敗＋HTTP失敗、取得失敗＋配信不明、正常、未設定/不正値（合成の不正文字列が出力に無い） |
| IR-05 | 生成物6件を追跡から除外（`git rm --cached`のみ）、`.gitignore`に`__pycache__/`・`*.py[cod]`等 | 全試験後も`git status`に生成物が出ない。追跡に`.pyc`が無いことを試験化 |

## 試験結果（件数は混同しない）

- **元の48件**（ad83f9b時点）：`test_main_flow.py` 41＋`test_workflow_candidate.py` 7。うち1件（`test_import_has_no_network_or_heavy_deps`）は、実依存のimport試験と同一プロセスで干渉するため、サブプロセスでの検査に書き換えた（内容は同じ）。FakePostは`allow_redirects`引数を受けるよう更新。
- **今回追加47件**：`test_review_fixes.py` 42、`test_real_dependencies.py` 5。
- Python 3.10.20（`uv`で取得）の仮想環境、全95件：**95 passed、0 failed、0 skipped**。
- Python 3.13.17（実依存なし）：**90 passed、0 failed、1 skipped**（`test_real_dependencies.py`が`yfinance`未導入でモジュールごとスキップ）。
- 別途、`py_compile`（3.10・3.13）で構文確認。静的解析ツールは未実施。
- コマンド：`python -m pytest -q`（3.13）、`/tmp/v310/bin/python -m pytest -q -p no:cacheprovider`（3.10）。ネットワーク遮断は、Python側のsocket接続・名前解決のloopback以外拒否。curl子プロセスはこの遮断の対象外のため、試験にはループバックと合成URLのみ渡し、外部URL・実秘密は使っていない。

## 実依存（Python 3.10.20）

yfinance 1.7.0／pandas 2.3.3／numpy 2.2.6／requests 2.34.2／gspread 6.2.1／oauth2client 4.1.3／pytest 9.1.1／PyYAML 6.0.3（導入は`pip install`相当をバージョン無指定で実行。workflowの`pip install yfinance pandas requests gspread oauth2client`と同じ無指定）。実ライブラリをimportしたうえで`yf.download`・gspread・`ServiceAccountCredentials`だけをモックし、確認した事実：

- 呼出しは従来どおり`yf.download(["SOXX","SOXL","SPY","IEF"], period="1y")`。
- yfinance 1.7.0の既定値：`auto_adjust=True`、`multi_level_index=True`、`group_by="column"`。合成の列構造`(Price, Ticker)`から`Close`/`Open`の取り出し・tz付き索引の正規化・Sheetsの認証引数／`Data`シート／行の受け渡しが動く。
- **重要な観察**：`auto_adjust`既定がTrueのため、`Close`は調整後価格になる。workflowは版を固定せず最新を入れるので、**旧版で動いていた時点の価格定義（既定値）と異なる可能性がある**。今回は定義を黙って変えておらず、実データでの影響は未検証。切替前に版固定と調整有無の方針を決める必要がある（新規の採否は行わない）。
- 実データAPI・Discord・Sheetsへのアクセスは0。

## 未実施・残る切替条件

実Actions（#7のpip失敗、`Report setup failure`の実動作）、#8の未起動観測、Discord実配信・読了、Sheets実書込、GitHub通知の本人確認、実データでの動作。対象セッションの自動決定（日付未設定で非0の挙動は維持）、確認期限、独立監視、手動再実行の重複防止、HTTP失敗の再試行方針、yfinanceの版固定／調整価格の方針は未決のまま。ローカル確認は実Actions受入合格ではなく、本番再開の承認でもない。
