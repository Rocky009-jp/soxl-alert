# NYSE 2026〜2028 休場日・短縮取引日の照合（S4-D設計§4.1）

出典：ICE（NYSEの親会社）の発表「NYSE Group Announces 2026, 2027 and 2028 Holiday and Early Closings Calendar」、2025-12-23。
https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/default.aspx
（2026-11-05、取得の道具で読んだ。nyse.comの表とYahooには、この環境からは届かなかった。）

| 祝日 | 2026 | 2027 | 2028 |
|---|---|---|---|
| New Year's Day | 1/1 (Thu) | 1/1 (Fri) | なし（1/1が土曜のため振替なし） |
| Martin Luther King, Jr. Day | 1/19 | 1/18 | 1/17 |
| Washington's Birthday | 2/16 | 2/15 | 2/21 |
| Good Friday | 4/3 | 3/26 | 4/14 |
| Memorial Day | 5/25 | 5/31 | 5/29 |
| Juneteenth | 6/19 | 6/18（振替） | 6/19 |
| Independence Day | 7/3（振替） | 7/5（振替） | 7/4 |
| Labor Day | 9/7 | 9/6 | 9/4 |
| Thanksgiving Day | 11/26 | 11/25 | 11/23 |
| Christmas Day | 12/25 | 12/24（振替） | 12/25 |

短縮取引日（13:00 ET）：2026-11-27、2026-12-24、2027-11-26、2028-07-03、2028-11-24。

設計§4.1（fad0f5b）の表、試行 v2_inputs/xnys.py の HOLIDAYS（29日）・EARLY_CLOSES（5日）と、すべて一致した。
