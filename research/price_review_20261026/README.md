# 価格調査の主担当確認
2026-10-26（日本時間）

対象eb993a04d5b734d087fc73987b86d2110383a882。
[主担当回答](../../docs/reviews/PRICE_EXECUTION_EVIDENCE_RESPONSE_20261026.md)。

元のbuild_price_checks.mjsを変更せずNodeで実行し、49行・11,836バイト・Git blob 24e7b1b1756a0fa55187f0d524b419e18caf9876を再現した。固定daily.jsonと転記定数からの算術再現であり、元ページや独立配信元の正しさの試験ではない。

主担当はFinancialContentの履歴表をブラウザ抽出本文で読み、4日OHLC16セルを確認した。保存値と一致するが上流独立性・調整・通常時間は未確定。原HTMLバイトやそのSHA256は取得していない。このJSONのハッシュを元HTMLのハッシュと呼ばない。

Alpaca公式FAQ/プラン表、Direxion公式2024ページと検索結果、Massive公式プラン表を読み、取得条件と分配の扱いを補正した。元のClaudeの日時欠落を新しい観測日時で埋めていない。主担当のアクセス日は2026-10-26で、秒単位のブラウザ取得時刻は未保存。

review_checks.jsonに再現結果、16セルの値、文書確認の範囲、未実施を保存した。
実際の市場APIからの分足・気配取得、登録、キー設定、有料契約は0件。株式の発注・Actions・Discord・Sheets操作も行っていない。

再現する場合は研究eb993a0のチェックアウトで：

```text
cd research/price_execution_evidence_20261026
node build_price_checks.mjs
```

生成CSVが上記Git blobに一致することを照合する。元データの独立確認の代わりにはならない。
