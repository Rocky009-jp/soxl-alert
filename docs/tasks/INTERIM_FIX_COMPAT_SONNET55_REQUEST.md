# Sonnet 5.5依頼：ad83f9bの5指摘修正とPython 3.10互換性のオフライン確認

指定：**Claude Sonnet 5.5**。選定者：6.1 Sol High。
範囲が明確な修正と互換性確認のため。戦略・会計・カレンダー方式の新規採否は行わず、Opus 5.5の全面再レビューも不要。重大な未解決判断だけ6.1 Sol Highへ返す。

## 開始と資料

資料ブランチ `docs/v2-roadmap-20261023` のCLAUDE.md・docs/STATUS.mdを読み、資料開始の完全SHAを記録する。
次に[今回の指摘と再現](../reviews/INTERIM_IMPLEMENTATION_REVIEW_20261026.md)、[採用済み仕様](../specs/INTERIM_NOTIFICATION_SPEC.md)、[前回の実装依頼](INTERIM_IMPLEMENTATION_SONNET55_REQUEST.md)を読む。

実装対象は `feat/interim-notification-20261026`、開始候補 `ad83f9bf47c43f713e7cafb738f3de1bbb42705a`。先端が進んでいれば差分を確認し、既存変更を上書きしない。本番mainは停止コミット `31144d9b6af8a6c920ad53c395cd550e8c48a7fa` のまま。資料ブランチやmainへ候補コードを反映しない。

5項目採用と別作業ブランチの限定実装・オフライン試験は承認済み。同じ承認・原稿提出を再要求せず、修正と確認まで行う。

## 許可した編集対象

- 候補ブランチの `main.py`、`soxl_checks.py`、`soxl_notify.py`。
- 候補の `.github/workflows/schedule.yml`（報告処理の修正のみ）。ジョブ停止条件・cron・トリガーを維持。
- 必要なtests、依存版の記録／再現用設定、`.gitignore`。
- 差分に入った生成バイナリ6件だけを追跡から除外。
- `docs/implementation/INTERIM_IMPLEMENTATION_RESULT.md` の追記・更新。旧48件の結果と新結果を区別。

大きなリファクタリング・閾値変更・保有入力・研究修正は含めない。

## 修正する5件

### IR-01：curlの秘密漏れ経路
`-sS` の生stderrをログに流さない。有限時間・1回送信・元の失敗維持を保ちながら、固定の分類と非秘密の終了値／HTTP statusだけを出す。エラー本文・URL・Location等を出さない。

合成のローカルURLを使い、不正な括弧、形式、改行等でstderrにトークンが出ないことを確認。元候補の成功／HTTP失敗／到達不能／未設定のケースも維持する。実Webhookの設定値は読まない。CI上で試さず、ローカルのYAML内スクリプトを検証する。

### IR-02：RSIの全入力履歴検査
RSIが実際に利用するSOXX全履歴について元価格の有限・正を検査する。直近200行だけの検査にとどめない。RSI式・入力窓の変更や欠損補完で問題を隠さない。

先頭や200行より古い位置の負値／0／NaN／infを加えた合成入力を試し、エラー、判定呼出し0、Sheets0、通知1回、非0を確認。正常入力の計算・技術条件が旧式と整合することも保つ。

### IR-03：実Requestsでリダイレクトを禁止
POSTへ `allow_redirects=False` を明示。注入FakePost側もこの引数を検査できるよう更新する。

実Requestsとローカルサーバを用い、302→200、307/308で遷移先へ要求しないこと、HTTP要求が1回で、成功扱いせず非0になることを確認する。元の500／タイムアウト／再帰なしを維持。外部ネットワークや本番Webhookへ送らない。

### IR-04：エラーと対象日を結び付ける
検証済み設定の対象日をエラー通知と送信結果ログへ含める。日付設定欠落／不正は「対象日未確定」とし、生の不正設定値をログや通知に入れない。正常、取得失敗、データ検査失敗、HTTP失敗、配信不明を確認する。生例外・URL・応答本文等は引き続き出さない。

### IR-05：生成物の除外
次の6件だけを追跡から外し、`__pycache__/` と `*.py[cod]` 等の再混入を防ぐ。履歴改変や無関係な削除は不要。
- `__pycache__/main.cpython-313.pyc`
- `__pycache__/soxl_checks.cpython-313.pyc`
- `__pycache__/soxl_notify.cpython-313.pyc`
- `tests/__pycache__/conftest.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_main_flow.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_workflow_candidate.cpython-313-pytest-9.1.1.pyc`

再試験・構文確認後に、生成物が追跡差分へ出ないことを確認する。

## Python 3.10・実依存のオフライン確認

既存workflowのPython 3.10で、互換な実依存（yfinance・pandas・numpy・requests・gspread・oauth2client等）を導入・importし、使用版を記録する。必要なパッケージ取得は許可された通常の依存導入の範囲。実データAPI・Discord・Sheetsへアクセスしない。

- 取得・Sheets境界は、実ライブラリをimportしたうえでAPIをモックし、合成のyfinance列構造、列の取り出し、日付処理、Sheets引数・行の受け渡し等を確認する。
- 価格調整の既定値・列構造をインストール版から調べ、確認できた事実と実データ未検証を分ける。黙って価格の定義を変えない。
- ローカルのRequests/curl試験はループバックだけを許可する。Pythonのsocketモックは子プロセスを自動遮断するものではないので、curlにも外部URL・実秘密を渡さない。
- Python 3.10を利用できない場合は取得可否と制約を記録し、未実施を明示する。別版での成功を3.10合格とせず、workflowのPython版を無断で上げて解消したことにしない。
- 変更箇所の回帰試験と既存試験を実行し、passed／failed／skippedの実数・内訳・依存版・コマンドを残す。元の48件と今回結果、受入13行と今回11行、主担当の追加5観測を混ぜない。
- #7の実Actions試験と#8の未起動観測は今回も対象外。ローカル確認を実Actions受入合格としない。

## 未決のまま残す事項

対象セッションの運用上の自動決定（休日・短縮取引・夏冬時間・確定時刻・遅延）、完了通知の確認期限、独立監視、手動再実行の重複防止、GitHub通知の本人確認は本作業で採用しない。日付未設定で非0とする挙動を維持し、データ最終日・ローカル現在日で勝手に補わない。

## 成果と禁止事項

GitHubの候補ブランチへ保存し、開始SHA・保存SHA、5指摘の対応、実際の試験と版、未実施・残条件を報告する。書込できなければ適用可能な全パッチ／ファイルと結果を返し、未保存と明記する。

main反映・マージ・停止解除・Actions起動／再実行、Discord送信、Sheets実アクセス、実データ取得、認証・通知先変更、自動発注は禁止。本番再開は今回の合格から自動承認しない。
