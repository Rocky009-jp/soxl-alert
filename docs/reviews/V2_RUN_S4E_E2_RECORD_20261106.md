# V2 S4-E E-2 workflow の追加（送信なし） 記録

日付：2026-11-06（UTC）。対象：設計第3版 bcb03a1（D-1〜D-10採用 a1ba2e7）の §2「E-2」・§6、手順書 `docs/ops/V2_PRIVATE_RUN_GUIDE.md` の「E-2」・§2・§12。コードの版は E-0 受領版 2c7320fb138f3982cc20bb56e9e923a6a3d51638。E-1 の記録は `docs/reviews/V2_RUN_S4E_E1_RECORD_20261106.md`（4ebcebb）。この記録ブランチ `docs/v2-run-s4e-e2-20261106` は 4ebcebb から作った。

## 1. 承認と判断

- 着手の承認：Rockyさん「E-2に進めてください」（2026-11-06T04:16:58Z）。
- push の中身の確認：workflow の案（4点の変更、下の §2）と台帳の見出しの 1 行を示し、Rockyさん「OK」（2026-11-06T04:20:31Z）。
- **定時の実行（cron の 2 行）は E-3 の開始の承認のときに足す**（設計・手順書では E-2 で入れる形）。理由：cron を入れると翌朝から定時の実行が走り、E-3 の開始の承認と「定時の実行より前に `check-source` を 1 回」（設計 §2 の E-3、P-06）の順番が崩れる。共有の Actions の枠も、試運転を始めるまで使わない。判断カードでこれを推奨し、Rockyさんの「OK」（cron をコメントにした案の確認）をこの選択として記録した。
- E-3 の開始のときに、**cron の行を含むコミットを Rockyさん本人がウェブで行う**（失敗のメールは cron を最後に変えた人へ届く。手順書 §1、P-01）。そのコミットの前に `check-source` を手動で 1 回走らせる。
- しないこと：E-3 以降（定時の実行、試運転、秘密の登録、送信、`V2_MODE: live`）。公開リポジトリの main（31144d9）・workflow は変えない。`v2-*` は削除しない。

## 2. 非公開リポジトリへの変更

リポジトリ `Rocky009-jp/soxl-alert-v2-run`（非公開）。

| 参照 | コミット | 中身 |
|---|---|---|
| `main` | 301950478f11deaeff3d8ce8c597d386923d1f19 | `.github/workflows/v2-morning.yml` を追加（親 b36df6d） |
| `v2-ledger` | cc0ca2e29c781175faeb9727f7ff195e577c88c7 | `observations.csv`（見出しの 1 行だけ。親 b36df6d） |
| `v2-dry-state` | aa812122861528e1535f52e490f0cbfee03a5144 | `init` が作成（§3） |
| `v2-dry-outbox` | e6ff99093457f4d4f1e6299fb67adb7541569c2d | `init` が作成（§3） |

workflow は、ひな形 `docs/ops/V2_MORNING_WORKFLOW_TEMPLATE.yml`（2c7320f）から次の 4 点だけを変えた（ほかは同じ。モードを決める `case` の 1 行、`concurrency` の式と `queue: max`、入力の受渡しは変えていない）：

1. `actions/checkout` を **v7.0.1 = 3d3c42e5aac5ba805825da76410c181273ba90b1** に固定（2 か所）。2026-11-06 に、リリースの一覧で v7.0.1 が「Latest」の正式リリース（プレリリースではない）であることと、タグ `v7.0.1` が同じコミットを指すことを確かめた。`action.yml` は `using: node24`。
2. `V2_CODE_SHA` を 2c7320fb138f3982cc20bb56e9e923a6a3d51638 に。
3. `timeout-minutes` を 30 から **10** に（共有の Actions の枠の対策。E-1 記録 §4 の提案。通常の朝は 1 分前後、最初の追いつきでも約 4 分）。
4. `schedule` の 2 行をコメントにし、E-3 の開始のときに Rockyさんのコミットで足す注記を置いた。先頭の注記を E-2 の内容に書き換えた。

台帳の見出し：`record_id,target_us_session_date,observation_role,observation_status,current_fg_value,observed_at_iso8601`（LF で終わる 1 行）。受領版の `v2_inputs.ledger.read_ledger` で push 後の `v2-ledger` を読み、`([], 'cc0ca2e…')`（行 0、誤りなし）を確かめた。

## 3. `init --mode dry`

- 実行：Actions の run 42162022884（`workflow_dispatch`、2026-11-06T04:21:31Z）。入力 `command=init`・`mode=auto`・`start_after=2026-11-05`。この run は Claude が REST の dispatch で起こした（Rockyさんの資格情報で動くため、画面の起動者は Rocky009-jp）。
- 日本時間 13:21 に実行（9:00 より後。手順書 §12）。**境界は 2026-11-05**（`init` の時点で閉じた最後のセッション）。台帳は **2026-11-06 のセッションから毎日記録する**。
- 結果：ジョブ `success`（04:21:37〜04:21:47、10 秒）。実行の要約：

      command: init / mode: dry / now_utc: 2026-11-06T04:21:41+00:00
      code_version: 2c7320fb138f3982cc20bb56e9e923a6a3d51638 / python: 3.12.3 / git: 2.56.0
      state: INITIALIZED / outbox: INITIALIZED / exit_code: 0

- `v2-dry-state` の `history.json`：GENESIS の 1 件、`start_after: 2026-11-05`、境界のセッション 2026-11-05（14:30Z〜21:00Z、confirmed）、`armed: UNKNOWN`。作成者は `v2-runner`。
- `v2-dry-market` は無い（最初の朝の実行で作られる）。

## 4. E-2 で確かめること（手順書の「E-2」）

| 項目 | 結果 |
|---|---|
| `actions/checkout` の公式のリリースの SHA | v7.0.1 = 3d3c42e5aac5ba805825da76410c181273ba90b1（§2） |
| `queue: max` を GitHub が受け付けたか | **受け付けた**。workflow は `v2-morning` の名前で `active` に登録され、`concurrency` に `queue: max` を含むジョブが警告なく `success` で走った。待ちの先着順の挙動そのものは、まだ実物で見ていない |
| `init` の最初の push（checkout の資格情報で `v2-*` へ push できるか） | **通った**（`v2-dry-state`・`v2-dry-outbox` が作られた）。checkout v7.0.1 は資格情報を `$RUNNER_TEMP` の別ファイルに置き、作業場所の `.git/config` の `includeIf.gitdir` から読む形で、S4-C の Git（作業場所の設定を読む、`GIT_CONFIG_NOSYSTEM=1`）で動いた |
| 浅いクローンか | **浅い**（`fetch-depth: 1`。state 側は `main` の 1 コミット、code 側は 2c7320f の 1 コミット） |
| `v2-ledger` の最初のコミット | cc0ca2e（見出しの 1 行だけ） |
| ランナー | ubuntu-24.04（イメージ 20261101.360.1）、Python 3.12.3、git 2.56.0 |
| 秘密 | 無し（workflow に秘密の行は無い。ログの `token: ***` は GITHUB_TOKEN の伏字） |

## 5. Actions の使用

- この E-2 で走った run は 1 回（10 秒）。定時の実行は無い。
- このセッションから、Actions の workflow・run・ジョブ・ログの読み取りと dispatch はできた。Actions の設定（`/actions/permissions`）・秘密の一覧・請求の画面は読めない。

## 6. E-3 への申し送り

- 開始の承認のときに決める：`check-source` が続けて拒否されたら何回で止めて相談するか（設計 §2）。
- 順番：(1) `check-source` を手動で 1 回（`mode` は `auto`）、(2) 通ったら Rockyさんが cron の 2 行をウェブでコミット（コメントを外す）、(3) 失敗のメールを受け取る設定（手順書 §1）、(4) 定時の実行を 10 セッション以上。
- 台帳は 2026-11-06 のセッションから毎日（定時の実行が始まる前の日の分も）。最初の定時の朝は、境界の後の全セッションを追いつく。
- E-0 レビューの P-04（試験の穴 V10）は E-3 の前に足すことが推奨されている。
- 請求の画面の使用量を試運転中に記録する（E-1 記録 §4）。

## 7. 参照の照合

- 公開リポジトリ：この記録の push の直前は 135 参照で、E-1 の開始時の 134 参照と全行一致（増えたのは E-1 の記録のブランチ 1 本）。push の後は §8 に追記する。
- 非公開リポジトリ：push の後は上の表の 4 参照と `main` だけ。

## 8. push の後

- 本文のコミット 1d69569d18c09dca30aa30ac32bd77b07283b5ef を push した後：136 参照。直前の 135 参照はすべて同じ値のまま、増えたのはこの記録のブランチ 1 本だけ。
- 非公開リポジトリ：変化なし（`main` 3019504、`v2-ledger` cc0ca2e、`v2-dry-state` aa81212、`v2-dry-outbox` e6ff990）。
