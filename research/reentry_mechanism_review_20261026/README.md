# H2の主担当再実行・説明欄の訂正
2026-10-26（日本時間）

対象研究9f066e51286278677803357dde5ab7be1b4454fd。
analyze.mjsを無変更で再実行し、24経路/336照合・8組・会計分解が成功。15ファイルのGit blob一致、environmentだけNode/OS差。reproduction.jsonに記録。

静的レビューで、遅延1のD_fg_usedにD当日値を入れる誤注記を確認。固定エンジンのsignals(delay)で実際に使った履歴値を再計算したaudit_annotations.mjs、annotation_audit.json、annotation_corrections.csvを保存。
155行を訂正し、イベント333行＝約定288＋余力不足45と確認。0株理由も配分予算と代理Open+手数料で計算した。取引エンジン/入力/台帳/損益は変更していない。

訂正表の使用値もF&G履歴proxyで、当時の取得可能時刻や目視値の証明ではない。原研究は上書きしていない。CSVは元の全333イベントに対応する注記照合であり、新しい333約定や新規市場データではない。

研究9f066e5のチェックアウトを用意し、元analyze.mjs実行後：

```text
node /path/to/reentry_mechanism_review_20261026/audit_annotations.mjs /path/to/research-checkout
```

スクリプトのあるレビュー用フォルダへ訂正表/JSONを出す。追加API、実注文、通知の通信は行わない。次の利確幅108追加は未実行。
[受領判断](../../docs/reviews/REENTRY_MECHANISM_RECEIPT_20261026.md)参照。
