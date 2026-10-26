# 暫定実装 ad83f9b：6.1 Sol Highレビュー

日付：2026-10-26（日本時間）。資料開始SHA：`07651d576527efd64ce714f85992c937b0ffc0bf`。
候補：`feat/interim-notification-20261026`／`ad83f9bf47c43f713e7cafb738f3de1bbb42705a`。
main：`31144d9b6af8a6c920ad53c395cd550e8c48a7fa`（停止条件を維持）。
[実装者の報告原本](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/docs/implementation/INTERIM_IMPLEMENTATION_RESULT.md)。

## 結論と確認範囲

候補の限定実装と、実装者が報告した新規48件合格を受領。コード・テスト・YAML・差分を読んだ。毎回サマリ、検査失敗の非0、Sheets失敗後の通知試行、売却系抑止、停止条件維持はソース上で確認できる。ただし以下5件を修正し、本番切替は保留する。

主担当が実施したのは、固定候補から取得したPythonソースを用いる追加の5観測（正常・異常の対照を含む）であり、元のpytest 48件の独立再実行ではない。Python 3.12.10／pandas 2.3.3／numpy 2.2.6、Requestsはスタブ。curlはWindows版8.21.0。実装者のPython 3.13／pandas 3.0.5等の環境、Linux curl 8.5.0、Python 3.10と同一環境ではない。

[再現コード](../../research/interim_review_20261026/review_probes.py)／[観測JSON](../../research/interim_review_20261026/review_probe_results.json)。

## 指摘

| ID | 重大度 | 根拠・再現 | 影響 | 修正と確認 |
|---|---|---|---|---|
| IR-01 | 重大 | [schedule.yml](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/.github/workflows/schedule.yml) 54行のcurl `-sS` はstderrをそのまま出す。合成の不正URL `http://127.0.0.1:1/[SYNTHETIC_WEBHOOK_TOKEN` でcurlの解析エラーがURLとトークン文字列をstderrへ表示（exit 3） | 不正なWebhook設定などで秘密URLがログへ出る経路。実秘密の漏洩を観測したという意味ではない | 生stderrを抑止して固定の分類・終了コード・HTTP statusだけを記録。合成URLの括弧・不正形式・改行等のローカル試験を追加。変更後も再送なし・有限時間・元の失敗を保持 |
| IR-02 | 重大 | [soxl_checks.py](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/soxl_checks.py) 65行以降はSOXX全履歴でRSIを計算するが、142行の元価格検査は直近200行だけ。260行の先頭を負値にした合成入力が通り、RSI 18.629244→88.095505、技術条件成立→未達へ変わった | 計算へ入る元価格の検査が不完全で、データ検査OKのまま結果が変わる | 実際にRSIへ渡す全履歴の有限・正の検査を行う。式や入力窓を勝手に変えて消さない。先頭・200行より古い部分の負値／0／NaN／infを試験し、判定・Sheets0回、エラー1回、非0を確認 |
| IR-03 | 通常 | [soxl_notify.py](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/soxl_notify.py) 19行の実POSTに `allow_redirects=False` がない。注入スタブで未指定を確認。Requests公式APIはPOSTも既定True。既存のFakePostによる302試験は実クライアントの追従を検証していない | 追加HTTP要求や、リダイレクト先200を元のWebhook受付成功と誤認する可能性。307/308ではPOSTを再度送り得る。「post関数1回」だけでHTTP1回を保証できない | リダイレクトを無効にする。ローカルサーバで実Requestsを用い、302→200と307/308の先へ追従しない、非成功・要求1回を確認。本番Webhookには送らない |
| IR-04 | 通常 | [main.py](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/main.py) 109/119/128/134行→[build_error](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/soxl_notify.py) に対象日が渡らない。最新SOXX欠損の対照で非0と通知1回は成立したが、通知本文・ログの双方に指定日がない | 対象日と通知失敗等を結び付ける要件を満たさず、複数実行の診断が難しい | 設定済みの対象日をエラー通知・送信結果ログへ含める。日付未設定／不正は未確定と表す。生の不正設定値・URLを表示しない。正常・取得／検査失敗・HTTP／配信不明を確認 |
| IR-05 | 通常 | 基点とのGit差分に `__pycache__/*.pyc` 等の生成バイナリ6件 | 対象外生成物が混入し、異なるPython版のキャッシュやローカル情報を保存する | 当該6件だけを追跡から外し、`.gitignore` を追加。再試験後も生成物が差分に入らないことを確認。履歴改変や無関係なファイル削除は不要 |

IR-03の一次資料：[Requests API](https://requests.readthedocs.io/en/latest/api/)（`allow_redirects` は既定True）。今回実Requestsによる追従自体は再実行していない。IR-01も候補のLinux実Actionsで再現したとはしない。どちらも上表の追加試験を修正担当へ依頼する。

## 再現結果の読み方

- 正常対照：終了0・通知スタブ1回。
- 通知引数：タイムアウト(5,15)、リダイレクト無効の指定なし。
- 古い負価格：検査を通過し、RSIと技術条件が変化。追加の検査漏れとして確認。
- 最新欠損対照：終了1・通知1回。対象日が本文／ログにないことを確認。
- curl不正URL：ローカルの構文解析でexit 3、合成トークン文字列がstderrへ出ることを確認。

外部への通知・データ取得・Sheetsアクセスは0。curlの入力はローカル宛てで解析段階に失敗。Requestsはスタブで、実Webhook・実秘密は使っていない。原報告の48件とこの5観測を加算して「53件合格」とはしない。

## 既報の切替条件

対象セッション日の自動決定、実依存とPython 3.10、確認期限・重複防止、実Actionsのpip失敗報告、Discord／Sheetsの実確認、GitHub通知の本人確認は残る。候補が未設定の対象日で非0になる動作は、安全側の未完成として明示されており、隠された不具合として二重計上しない。

次は[Sonnet 5.5への修正・互換性試験依頼](../tasks/INTERIM_FIX_COMPAT_SONNET55_REQUEST.md)。今回の指摘修正とPython 3.10・実依存を用いたオフライン確認を同じ限定作業へまとめる。カレンダーの設計採用は別に残し、無断で現在日やデータ最終日を代用しない。

main・候補ブランチのコード／設定は今回変更しない。資料・再現結果だけを資料ブランチへ保存する。本番反映・停止解除・Actions起動・実送信は引き続き未承認。
