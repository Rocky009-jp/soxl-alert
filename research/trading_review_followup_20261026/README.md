# 売買ルールレビューの算術照合

対象版：429f90e77a2aecdb77252a0e1e53adbcbf186628。
既存daily CSV4本から、主開始2つの基準（P20_OR_R75、初回25%）とNO_SELL（同じ初回25%）を読み、日付を対応させて再集計した。新規戦略シミュレーションではない。

review_checks.jsonに入力Git blob・集計を保存。各開始のセッション数は保存行数であり、公式市場カレンダーとの完全性確認ではない。
- no_sell_greater_days：同じ日付でNO_SELL.total > baseline.totalとなる件数（厳密な>、許容幅なし）。
- difference：最終行のNO_SELL.total − baseline.total。
- hold_nonstock_total：NO_SELL.total − NO_SELL.market_value（現金だけでなく税引後未収等も含む）。
- crossover_close：(baseline.total − hold_nonstock_total) / NO_SELL.shares。
- 日次勝数は目的関数ではなく記述値。等価価格は単日の固定状態の算術で、約定や株価予測、経路再計算ではない。

この回の実行はfunctionsのJavaScript内で、取得したCSVの引用符を解釈して上式を適用した。結果は[主担当回答](../../docs/reviews/TRADING_RULE_REVIEW_RESPONSE_20261026.md)に整理した。
