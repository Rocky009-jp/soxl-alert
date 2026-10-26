# 920e695：5指摘の対応確認と次の設計

日付：2026-10-26（日本時間）。担当：6.1 Sol High。
資料開始SHA：`c6faf9e78b32dab6959485042fd67f06277cdc3d`。
対象候補：`920e69571cf4feda09f3f2f560e96fcb9cb09d50`（feat/interim-notification-20261026）。
main：`31144d9b6af8a6c920ad53c395cd550e8c48a7fa`。停止条件を維持。

[候補の報告原本](https://github.com/Rocky009-jp/soxl-alert/blob/920e69571cf4feda09f3f2f560e96fcb9cb09d50/docs/implementation/INTERIM_IMPLEMENTATION_RESULT.md)と、ad83f9bからの差分、修正コード・試験を取得して読了した。

## 結論

IR-01〜IR-05は、**候補コード・回帰試験のレビュー範囲で対応済み**とする。元の5件を繰り返す全面レビューは不要。Python 3.10.20・実依存での95件成功という報告を受領し、次は依存版・価格定義・対象セッションの設計へ進む。

本番復旧・実配信確認・切替承認ではない。主担当は95件を独立再実行していない。追加で4経路だけを実行した。原報告の95件と加算して「99件合格」としない。

## 5件の対応

| ID | 確認内容 | 扱い |
|---|---|---|
| IR-01 | curlの生stderrを破棄し、終了値／HTTP statusの固定出力へ変更。有限時間・1回送信・非追従を維持。合成URL／Locationの回帰試験を確認 | 本体の指摘は対応済み。下記NT-01は試験隔離の別残件 |
| IR-02 | RSIに使用するSOXX全履歴の有限・正を検査。20ケースと旧式一致の試験を確認。主担当も以前通った古い負価格が拒否されることを実行確認 | 対応済み |
| IR-03 | allow_redirects=Falseを明示。302/307/308の実Requests・ローカル試験を確認。主担当は注入引数を確認した範囲で、実Requests経路を再実行していない | 対応済み |
| IR-04 | エラー通知と送信ログに対象日を関連付け、未設定／不正は未確定表示。主担当も最新欠損と不正日付の経路を確認 | 対応済み |
| IR-05 | pyc6件を削除しgitignore追加。候補ツリーに__pycache__・pyc/pyo/pydがないことを照合 | 対応済み |

停止条件、cron、トリガーはソース上で維持。main・候補ブランチを今回変更していない。

## 試験結果の区別

実装者の報告：
- Python 3.10.20：95 passed、failed 0、skipped 0。旧48件（うち1件を独立サブプロセス検査へ変更）＋追加47件。
- Python 3.13：90 passed、1 module skipped。実依存試験5件が未導入によりモジュール単位のskipとなるため、3.10の95件との件数差は説明されている。
- 実依存とAPIモック：yfinance 1.7.0、pandas 2.3.3、numpy 2.2.6、requests 2.34.2、gspread 6.2.1、oauth2client 4.1.3。
- IR-01／03を戻したときの失敗確認は実装者の報告として受領。主担当の独立再現とはしない。

主担当の追加4経路：
正常、直近200行より古い負価格、最新元価格NaN、不正対象日。Python 3.12.10／pandas 2.3.3／numpy 2.2.6／Requestsスタブ。正常だけ判定・Sheets各1回、残りは各0回。全経路で通知1回・リダイレクト禁止引数・適切な対象日表示を確認し、不正対象日の生値が出ないことも確認した。

[再現コード](../../research/interim_review_920e695_20261026/review_probes.py)／[結果](../../research/interim_review_920e695_20261026/review_probe_results.json)。市場API・実Discord・Sheetsへのアクセスは0。候補のYAMLを実行した試験、実Requests、Python 3.10の独立再実行は未実施。

## 別残件NT-01：子プロセス試験の外部通信防止（通常）

候補 tests/test_review_fixes.py のURLパラメータには、ホスト名だけの `SYNTHETIC_WEBHOOK_TOKEN` が含まれる。curlはスキームを補ってホスト解決へ進み得る。Python socketの遮断fixtureはcurl子プロセスへ及ばないため、「合成文字列だけ」では外部DNS／通信の遮断の証拠にならない。

[curl公式マニュアル](https://curl.se/docs/manpage.html)は、スキーム省略時にプロトコルを推定すると説明している。これは実Webhook送信や実秘密漏洩を確認した指摘ではなく、試験隔離と報告の限界である。主担当は当該入力を実行していない。候補本体のIR-01の修正を未対応へ戻す理由ではないが、次回のSonnet限定作業で次を直す：
- スキームなしは `127.0.0.1:1/SYNTHETIC_WEBHOOK_TOKEN` のようにループバックだけを使う。
- 不正スキーム／ポートの例も、ホスト部分をループバックへ固定しトークンはパス側に置く。
- 子プロセスへ渡す全URL、Location、proxy／curl設定の影響を確認し、非ローカル接続を起こさない試験にする。
- 実APIアクセス0、外部HTTP接続0、外部DNS0は別の主張として、裏付けのない遮断保証を書かない。

## 価格・依存についての判断

版を固定する技術方針は採るが、まだ候補へ実装していない。まず3.10の試験で使った直接依存版を固定候補とし、推移依存・OS差・新しいカレンダー依存があれば最終セットを再現確認する。直接依存だけの固定を完全な再現保証と呼ばない。

調整有無は**未採用の設計事項**。yfinanceの現行公式文書はauto_adjust=Trueを既定とし、OHLC全体を自動調整すると説明する。公式実装もAdj Close/Close比率でOpen等を変換しAdj CloseをCloseへ置換する。これは現在の一次資料による概念確認で、過去Actions環境の既定値や当時の価格定義を復元したわけではない。
- [公式download API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)
- [公式auto_adjust実装](https://github.com/ranaroussi/yfinance/blob/main/yfinance/utils.py)

auto_adjust=Falseにすれば「当時の実約定価格」や「分割も一切未調整の価格」になると断言しない。逆に、調整価格を用いた指標計算自体を直ちに分配金の二重計上と扱わない。損益・分配金台帳に何を使うかを分けて検討する。

既存研究provenanceには第三者daily.jsonとdaily_adjclose.csvがある。現在候補のyfinanceと同一の定義・取得時点だったという証拠はない。既存CSVや結果を黙って上書きしない。

## 次の担当

[6.1 Sol Highの設計たたき台](../specs/DATA_SESSION_DESIGN_NOTES.md)を入力に、**Opus 5.5で価格・対象セッションの設計に限定して判断案を作る**。金融データの定義・時系列・休日と実行遅延の設計が関わるため。5件の再レビューや全期間再検証は依頼しない。[詳細依頼](../tasks/DATA_SESSION_OPUS55_REQUEST.md)。

Opusは仕様案だけを作成する。NT-01と版固定のコード修正、設計の実装は、仕様判断後にSonnetへまとめて渡す。main反映・停止解除・Actions起動・実送信は引き続き未承認。
