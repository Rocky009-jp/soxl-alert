# V2 S3-B-2 限定実装 受領レビュー

日付：2026-10-30（日本時間）。対象：feat/v2-history-s3b2-20261030。
判定：**重大0・通常3・提案1。R-01〜R-03を限定修正してから、次の工程の判断へ進むことを推奨する。**
本書はレビューであり、B-3以降・S3-C・本番の採用や実装を承認しない。

## 1. 固定対象と確認範囲

| 用途 | 完全SHA |
|---|---|
| 実装開始点 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| コード・試験のレビュー／実行対象 | 3b6c21cb5f7769d425fc01ac01498310695a1572 |
| 結果文書を含む保存最終 | 132a3392115e44105895ecea92e472b49107fed3 |
| 採用済み設計・依頼 第2版 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| 採用・開始指示 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |

設計blob 988258c798ee2d867c86238db1c4f426a360dda2、依頼blob ab65b43704182a5416f5dbf935468da6239462fc。
固定文書、新規ランタイム全体、既存commands.pyとの差分、関連する既存投影・履歴検査器、新規試験と欠陥注入スクリプト、結果文書を照合した。

基準からの最終差分は、新規22ファイルと既存commands.pyの1ファイル変更。commands.pyは+15/-3行で、API-1の切出しとLATEのv2分岐に限られる。試験対象から保存最終への差分は、結果文書1本（182行）の追加だけ。既存試験・fixtures・依存・設定・workflowの変更はなく、最終ツリーに追跡された__pycache__／pycはない。push前の履歴整理の経緯そのものは作業者報告として区別する。

全区間の投影／現在区間の日次計算の分離、S1への1回の委譲、物理先頭への付け直し、候補の完全検査、確認の枝A／枝B、退避した依頼IDとMIGRATEDの扱いは、読解と下記試験の範囲では固定契約に沿っている。

## 2. 通常の指摘

| ID | 箇所 | 内容・影響 | 最小修正と確認 |
|---|---|---|---|
| **R-01** バッチhashアクセサの参照共有 | v2_history_ops/batch.py:67–68 | from_dictは意味検査前なのでbatch_hashがdict／listでも値を作れる。batch_hashが内部の同じ物を返すため、取り出した値への書込みでto_dict()の内容が変わる。一方、_textに基づく等値・hashは変わらず、不変値の内部表現が食い違う。正常な文字列hashでは発生せず、確認を迂回できたという指摘ではない | plan_hashやB-1の同形アクセサと同様、batch_hashを常に独立した写しとして返す。dictとlistの両方で確認。from_dictの受理範囲は狭めず、check_append_batchでは引き続き固定エラーで拒否 |
| **R-02** 固定事実の不変性が未実装 | v2_recovery/facts.py:52–91、93–158 | FixedApplyは「read-only by convention」とされ、seq等を代入でき、context・stored_sessionsも同じ可変物を公開している。FixedFactsもapplies／by_seq／fixed_fps／declares／boundaries等を直接公開する。例：欠けた保存decisionを含む入力に対してLedgerContextを作り、facts.applies.clear()後にresolve_coreを呼ぶと、元はledger_mismatchだった結果が成功へ変わる。これは公開された事実APIの契約違反。日次・計画APIは内部で毎回事実を作り直すため、この操作だけで保存や通知が起きるわけではない | 設計§3.3のFixedApply「不変」と§9の不変値の契約を満たす。属性の代入・削除を拒否し、構造化アクセサは独立した写しか再帰的に不変な値を返す。stored_sessionsは外からsessionsの列を変えても元の値に影響しないこと。FixedFactsの派生集合・索引・APPLYの列も同様。既存の属性名と正常入力での値は維持する |
| **R-03** B03xの等価判定に反例 | tests/v2_history_ops/sensitivity_check.py:38–43、結果文書§9・§10 | B03xは「有効な宣言だけ」から「物理配列のreplay_ofがない宣言全部」へFixedFacts.declaresを変える変異。DROPされた宣言を含めると、新たなセッション照合を加えるため等価ではない。下記の有効履歴では製品コードは成功し、同変異はsession_context_mismatchで停止する。製品の投影自体はこの反例で正しく動くが、等価として除外した検証・報告が誤っている | 反例を新規の回帰試験へ追加し、実際のB03x置換でその試験が失敗することを確認。EQUIVALENT指定と理由を訂正し、対象変異の実測結果を結果文書へ追記する。未実測のまま26件全検出などへ数字だけ直さない |

### R-03の反例

合成の有効な履歴を既存h_helpersで作る。

1. #0 GENESIS D0。
2. #1 APPLY D1。
3. #2 DECLARE D2（q1）。
4. #3 RESTORE、復元点#1、#2はDROP（q2）。
5. #4 RESTART_UNKNOWN、resume_after=D4（q3）。

validate_historyは成功し、有効seqは0,1,3,4。現在のsessionsのうちD2のclose_atだけを変更し、check_d=D5で投影する。
有効APPLY D1にとってD2はnext(D1)であり、close_atは比較対象外。有効な宣言はないので、通常の投影は成功する。
B03xでは退避済みDECLARE D2のcontextを照合し、D2自身のclose_atの差でsession_context_mismatchになる。
「前後のAPPLYが同じセッションを比較する」は、DROPした末尾宣言のこの例には成立しない。

## 3. 任意の提案

**P-01（結果文書の正確さ）**：結果文書§4はHistoryResolutionConfirmResultにもcommittable=Falseがあると記すが、実装にその属性はない。固定設計§9の同値の全キーにもcommittableはないので、追加実装をせず、この文をHistoryDayResultだけに直す案を勧める。保存できないという型の境界自体は試験で確認できている。

## 4. 主担当が実際に実行した確認

Windows、Python **3.12.14**。新しいクリーンクローン、core.autocrlf=false、detached HEAD＝3b6c21c。TEMP／TMPは書込み可能な試験専用領域。unittestには-B -W error::ResourceWarningを指定した。

| スイート | 実測 | 時間 |
|---|---|---|
| tests/v2_history_ops | 156件合格、失敗・error・skip 0、終了0 | 18.093秒 |
| tests/v2_recovery | 176件合格、失敗・error・skip 0、終了0 | 5.128秒 |
| tests/v2_history | 230件合格、失敗・error・skip 0、終了0 | 19.316秒 |
| S2 RealWindows（test_b09_modes_os） | 3件合格、失敗・error・skip 0、終了0 | 1.368秒 |
| S2 RealWindowsLockDirectory（test_b11_review_fixes） | 1件合格、失敗・error・skip 0、終了0 | 0.112秒 |
| 同梱レビュー再現コード | R-01/R-02の7観測すべて再現、対照5件合格、R-03反例1件で差を確認、終了0 | 別集計 |

unittestは合計**566件合格**。再現コードの観測はこの566件に足していない。ネットワークは既存／新規ヘルパーのsocket禁止で遮断し、Linux unshareのOSレベル遮断とは区別する。ユーザーPCの試験ではない。

再現コードの通常実行は修正前の7観測を要求する。--expect-fixedはR-01/R-02の解消を要求する。R-03は製品の不具合ではなく変異の分類・試験不足なので、同オプションにかかわらず「通常コードとB03xの差」が出ることを確認する。新規回帰がB03xを検出することは別に確認する必要がある。

今回こちらでは、既存コア197・保存ドメイン170の再実行、Linux4版、全26変異やcommands.pyの16変異の再実行はしていない。作業者の合格報告を自分の実行へ置き換えない。物理電源断、autocrlf=true、本番等も未実施。

## 5. 参照・成果物・次の最小作業

採用・開始指示§5の40参照はレビュー開始時にすべて完全SHAで一致した。実装ブランチも132a339を確認。本レビューを新規資料ブランチへ保存し、保存後に同じ参照を再照合する。照合結果は完了報告で示す。

成果物は本書、再現コード、限定修正依頼書。実装・既存試験・元ブランチへは変更していない。PR・マージ・Actions・本番・通知はない。
次の最小作業はR-01/R-02の範囲内修正、R-03の回帰追加と変異・報告訂正、該当試験と既存回帰の確認まで。B-3以降・S3-Cへ進む判断はこの後に残す。
