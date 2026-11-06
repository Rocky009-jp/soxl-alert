# V2 S4-E E-1 非公開リポジトリの作成 記録

日付：2026-11-06（UTC）。対象：設計第3版 bcb03a1（D-1〜D-10採用 a1ba2e7）、手順書 `docs/ops/V2_PRIVATE_RUN_GUIDE.md` の「E-1」と §11。E-0 受領版 2c7320f（受領記録 34a2ed4・追記 1abe472、次段階 END＝2c7320fb138f3982cc20bb56e9e923a6a3d51638）。この記録ブランチ `docs/v2-run-s4e-e1-20261106` は 1abe472 から作った。

## 1. 承認と範囲

- 承認：Rockyさん「E-1（非公開リポジトリの作成）に進んでください」（2026-11-06T02:57Z）。
- 範囲：非公開リポジトリの作成（Rockyさんのウェブ操作）と、ブランチ保護・ルールセット・Actions の枠の確認、この記録。
- しないこと（E-2以降）：workflow の追加、秘密の登録、Actions の設定の変更、台帳 `v2-ledger` の作成、`init`、試運転、送信。公開リポジトリの main（31144d9）・workflow・既存の通知先・秘密は変えない。`v2-*` のブランチは削除しない。
- Claude は非公開リポジトリへ何も push していない（読み取りだけ）。

## 2. 作成したリポジトリ

| 項目 | 値 | 確かめ方 |
|---|---|---|
| 名前 | `Rocky009-jp/soxl-alert-v2-run` | REST `GET /repos/...` |
| 公開範囲 | `private`（`private: true`） | 同上 |
| 作成 | 2026-11-06T04:14:05Z、作成者 Rocky009-jp | 同上 |
| 中身 | `README.md` 1つ（`# soxl-alert-v2-run`）。.gitignore・license なし | 浅いクローン |
| 参照 | `refs/heads/main` = b36df6d0794cd95af0e030a9069298d026ef96fe（Initial commit）だけ | `git ls-remote` |
| workflow | 0件 | REST `GET /repos/.../actions/workflows` |

## 3. ブランチ保護・ルールセット

- REST `GET /repos/Rocky009-jp/soxl-alert-v2-run/rulesets` → **HTTP 403「Upgrade to GitHub Pro or make this repository public to enable this feature.」**
- REST `GET /repos/Rocky009-jp/soxl-alert-v2-run/branches/main/protection` → **同じ 403**。
- GitHub Docs（2026-11-06 に確認）：
  - ルールセット：「Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud.」（about-rulesets）
  - 保護ブランチ：「Protected branches are available in public repositories with GitHub Free and GitHub Free for organizations.」「…also available in public and private repositories with GitHub Pro, GitHub Team, …」（about-protected-branches）
- 結論：**個人の無料プランの非公開リポジトリでは、ルールセットも保護ブランチも使えない**（APIの応答とDocsが一致）。手順書 §11 の「使えない場合」に当たる。
- 巻戻しリスクの扱い：§5 の Rockyさんの判断を参照。

## 4. Actions の枠

- GitHub Docs（billing の GitHub Actions、2026-11-06 に確認）：GitHub Free は、非公開リポジトリの Actions に月 **$12 相当**の含まれる利用（Linux 2コアは $0.006/分。Docs に分数の記載は無く、計算すると約 2,000 分）、成果物の保存 500 MB、cache はリポジトリごとに 10 GB。「If your account does not have a valid payment method on file, usage is blocked once you consume the included compute usage.」利用はリポジトリの所有者に付く。分の切上げの規則は Docs に書かれていない。
- **この枠はアカウントの全部の非公開リポジトリで共有**（Rockyさん 2026-11-06T04:11Z「他プロジェクトともActionの上限を共有しているので、Actionの仕様には気をつけて」）。
- 見込み：定時は火〜土の 1 朝 2 回で月に約 43 回、1 回 1 分前後（通常の朝の `morning_job` 3.15 秒、E-0 の測定）。手動の操作を足して **月 50〜100 分（枠の約 5% 以下）**。ひな形は成果物・cache を保存しない。最初の追いつき（149 セッション）は 1 回だけ約 4 分（172〜225 秒）。
- **課金は要らない**（無料の枠に収まる見込み）。現在の他プロジェクトの使用量は、このセッションから請求の画面を読めないため未確認。
- Actions の設定（既定の権限、許可するアクション）は、このセッションのプロキシから読めなかった（`/actions/permissions` は 403）。E-2 で workflow を置くときに確かめる。
- E-2 への申し送り（提案）：(1) ひな形の `timeout-minutes: 30` を 10 に下げる（追いつきでも約 4 分、止まらない実行が共有の枠を食い過ぎない）。(2) E-3 の試運転中に請求の画面の使用量を記録し、見込みと照らす。どちらも E-2・E-3 の承認のときに決める。

## 5. Rockyさんの判断

- 巻戻しリスク（手順書 §11、設計 §9）：**リスクを受け入れる**（Rockyさん、判断カードで推奨を選択、2026-11-06T04:15:30Z）。GitHub Pro にはしない。影響は同じ日の重複の通知で、誤った判定ではない。運用では `v2-*` のブランチを削除・強制 push せず、実行の記録の `history_digest`（12 桁）が前の朝から続いているかを時々見る。

## 6. 公開リポジトリの参照の照合

- 開始時（2026-11-06T03:00Z ごろ）：134 参照、`v2-*` なし、main 31144d9。
- push の直前：134 参照で開始時と全行一致（この記録のブランチはまだ無い）。

## 7. push の前後

（push 後に追記）
