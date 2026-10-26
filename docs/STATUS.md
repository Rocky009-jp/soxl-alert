# 現在地 — 2026-10-26／限定実装受領・追加レビュー指摘

## 対象と権限

- 正本：`Rocky009-jp/soxl-alert`、資料ブランチ `docs/v2-roadmap-20261023`。
- 今回の資料開始：`07651d576527efd64ce714f85992c937b0ffc0bf`。
- 候補：`feat/interim-notification-20261026`／`ad83f9bf47c43f713e7cafb738f3de1bbb42705a`。
- main：`31144d9b6af8a6c920ad53c395cd550e8c48a7fa`。ジョブ常時スキップ条件を維持し、本番の判定コードは旧版のまま。
- ユーザーの5項目採用と別作業ブランチの限定実装・オフライン試験は承認済み。同じ承認を取り直さない。
- main反映、停止解除、Actions起動・再実行、実通知・Sheetsアクセスは未承認。「Rockyさん」はユーザー本人。

## 受領と主担当の確認

[実装報告原本](https://github.com/Rocky009-jp/soxl-alert/blob/ad83f9bf47c43f713e7cafb738f3de1bbb42705a/docs/implementation/INTERIM_IMPLEMENTATION_RESULT.md)を取得し、候補のコード・テスト・YAML・基点からの差分を読了。実装者は新規pytest48件合格を報告している。

主担当は固定候補に対する追加5観測を実施。元の48件を独立再実行したわけではない。Python 3.12.10／pandas 2.3.3／numpy 2.2.6、Requestsスタブ、Windows curl 8.21.0。候補が報告した3.13環境や本番3.10とは区別する。

[レビュー全文](reviews/INTERIM_IMPLEMENTATION_REVIEW_20261026.md)／[再現コード](../research/interim_review_20261026/review_probes.py)／[観測JSON](../research/interim_review_20261026/review_probe_results.json)。

| 指摘 | 内容 | 状態 |
|---|---|---|
| IR-01・重大 | curlの不正URLエラーで合成トークンがstderrに出た。秘密URL漏れの経路 | 要修正。実秘密の漏洩を観測したという意味ではない |
| IR-02・重大 | RSIが使う200行より古い価格が未検査。負価格が通りRSI・技術条件が変化 | 合成入力で再現、要修正 |
| IR-03・通常 | Requestsのリダイレクトを禁止していない。関数1回でもHTTP1回とは限らない | 引数未指定と公式仕様を確認。実クライアントの追加試験を依頼 |
| IR-04・通常 | データエラーの通知本文・ログに指定対象日がない | 最新欠損の対照で再現、要修正 |
| IR-05・通常 | 生成pyc6件がコミットに混入 | Git差分で確認、除外と再混入防止が必要 |

本番切替は保留。候補ブランチ・mainのコードは今回変更せず、資料と再現成果だけを保存する。

## 採用事項と現在

毎回サマリ、異常非0・Sheets部分失敗通知、売却推奨なし・過熱参考OFFは候補に実装されたが、上記指摘があり本番未反映。GitHub失敗通知はユーザーが確認する方針のみ採用済みで、設定・受信は未確認、未設定扱い。現行ジョブの停止は維持する。

[採用記録](specs/INTERIM_NOTIFICATION_SPEC.md)／[承認表](reviews/PHASE0_OPUS55_APPROVAL_ITEMS.md)／[停止確認](../research/interim_20261026/PAUSE_VERIFICATION.json)。

## 次の作業

**Claude Sonnet 5.5：5指摘の修正とPython 3.10・実依存のオフライン確認。**
[詳細依頼](tasks/INTERIM_FIX_COMPAT_SONNET55_REQUEST.md)／[貼り付け用](CLAUDE_START_PROMPT.md)。

明確な修正と互換性確認を同じ限定作業へまとめ、作業ブランチで修正・試験・GitHub保存まで行う。Opusの全面再レビューは不要。重大な設計判断だけ6.1 Sol Highへ返す。Claudeへ自動送信・実行はしていない。

## 本番切替前に残る条件

- 対象セッションの自動決定（休日・短縮取引・夏冬時間・確定時刻・遅延）。現候補はTARGET_SESSION_DATE必須で、未設定なら非0。データ最終日や現在日で勝手に補わない。
- Python 3.10と実依存でのオフライン確認。候補の実装者は3.13、yfinance/gspread/oauth2client未導入で試験した。
- 完了通知の確認期限、未起動の独立監視、手動再実行の重複防止。
- 実Actionsのpip失敗報告、Discord実配信・Sheets記録、GitHub失敗通知の本人確認。#7は実Actions未実施、#8は机上確認。
- 上流欠損原因と実配信は未確定。候補実装や合成試験を本番復旧と扱わない。

## 研究と固定条件

損切りなし・税引後利益全額再投資・最終総資産最大化。最大DDで減点しない。楽天証券・150円固定・税20.315%・USD MMF・整数株・SOXL現金分配・目視F&G・自動発注なし。初回あり＋25%は仮候補。

研究の過去利益額の未解決差、寄付き価格の先読み、分足・NBBO、F&G履歴取得時刻は保留。[ロードマップ](ROADMAP.md)と既存研究資料を維持する。旧欠陥再現14件・仕様13行／今回対象11行・候補48試験・主担当5観測を混同しない。
