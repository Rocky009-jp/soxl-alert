# Claude作業の入口

[CLAUDE.md](../CLAUDE.md)と[STATUS](STATUS.md)を読み開始SHAを記録。
77bb44fの利確幅216セルは[受領・終了](reviews/PROFIT_TARGET_ISOLATED_RECEIPT_20261026.md)。P60を次の主候補にせず、売却なしと20%利確を軸にする。正式採用ではない。

次は **[Sonnet 5.5の日足買い条件切り分け](tasks/BUY_TRIGGER_ABLATION_SONNET55_REQUEST.md)**。3主プロファイルで通常/極端恐怖の注文を一つずつ外す。参照込み144評価セル（72再利用/72新規）、回帰24実行＋合成最大12。仕様を先に別コミットで固定。市場状態・会計を変えず、API/本番操作・通知実装へ広げない。[貼り付け用](CLAUDE_START_PROMPT.md)。
