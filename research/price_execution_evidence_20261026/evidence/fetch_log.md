# 取得記録（2026-10-26、UTC時刻は未記録）

取得手段：WebFetch／WebSearch（小モデルによる要約付き取得）。生バイトは保存されず、SHA256は取得できない。表の値は要約出力からの転記で、原HTMLとの完全一致は未確認。
Bashからの直接取得（curl）は環境の許可外で拒否（query1.finance.yahoo.com／stooq.com／api.polygon.io／各社サイト：プロキシ403 CONNECT）。

| URL | 用途 | 結果 |
|---|---|---|
| https://www.financialcontent.com/quote/NY:SOXL/historical | A日足 | 2026-07-27〜10-23の表。4日(7/29,7/30,7/31,8/10)のOHLCV取得 |
| https://stockanalysis.com/etf/soxl/history/ | A日足 | 1頁目は2026-08-14〜。対象日なし（出所S&P Global Market Intelligence表記） |
| https://stockscan.io/stocks/SOXL/price-history | A日足 | 日次は2026-09-25〜、Open/Closeなし。対象日なし |
| https://digrin.com/stocks/detail/SOXL/price | A日足 | 月次のみ。2026-06=266.71、2026-07=114.72（月末終値） |
| https://www.tipranks.com/stocks/soxl/historical-prices | A日足 | 2025-03〜06の50行のみ。対象日なし |
| https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs | 企業行動 | 分配4行、分割なし表記、市場価格定義 |
| https://www.direxion.com/press-release/2024-etf-distributions | 企業行動 | SOXL 2024-03-19/06-25のみ。12月表にSOXLなし（内容不完全の可能性） |
| https://www.direxion.com/press-release/2025-etf-distributions | 企業行動 | 日程のみ。ファンド別表が取得内容に無くSOXL確認不能 |
| https://massive.com/pricing , /docs/rest/stocks/aggregates/custom-bars | B | プラン・履歴・バー定義 |
| https://docs.alpaca.markets/reference/stockbars , /stockquotes-1 , /docs/historical-stock-data-1 | B | パラメータ・feed |
| https://databento.com/pricing , /docs/venues-and-datasets | B | 料金・データセット名のみ |

注：日足の独立価格源は「最大3系統」の指示に対し、探索中に5サイトを開いた（うち日次OHLCを返したのは1、月次1）。超過分は結果として使用していない／独立性を数えていない。
