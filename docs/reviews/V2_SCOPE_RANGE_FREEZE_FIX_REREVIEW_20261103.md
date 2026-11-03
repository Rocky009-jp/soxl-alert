# V2 範囲試験の固定 R-01限定修正 再レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（前回レビューと同じセッション。`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high）。コーディネーター経由のRockyさんの依頼。製品コード・修正ブランチ・既存試験は変更していない。
結論：**前回の通常1件（R-01）は解消。提案P-01も反映済み。新しい重大0・通常0・提案0。推奨は「受領」。** 前回の提案P-02（git_show_at_endの本文が未固定）は推奨どおり今回の範囲外で、任意のまま残る。
本レビューはPR・マージ・本番反映・CONSUME・S3-Cへの移行の承認ではない。

## 1. 対象

| 項目 | 完全SHA・内容 |
|---|---|
| 修正開始 | dda7eb706637adc5f6dd37513e4b6ca360fde2ba |
| 試験対象 | **00094cc84287cbea977f6c94bfa8126ea2ea7daa** |
| 保存最終 | **bfbde7a7854bf91a77fb58737c24b19c6507453a**（fix/v2-scope-range-freeze-review-20261103） |
| 前回レビュー・修正依頼 | fa4b232810569f4512d09f244ef50f9685ff0c95（docs/v2-scope-range-freeze-review-20261103）§5・§6 |

差分：dda7eb7→00094ccは`tests/v2_scope_chain/test_sc_02_chain.py`の1ファイルだけ（+72/−23）。00094cc→bfbde7aは結果文書の末尾に§11を足しただけ（+19/−0、既存行の削除0）。sc_helpers.py、test_sc_01・03、固定した5本、ランタイム、他の試験・設定・docsの差分0。**前回§6の変更許可の範囲内。**

## 2. 前回の指摘ごとの確認

| ID | 判定 | 根拠 |
|---|---|---|
| R-01 | **解消** | test_sc_02は`from test_sc_03_scope import REV, START`を削除し、`TIP = "HEAD"`で`range_tests(TIP)`・`judge_chain(..., TIP, CHAIN_START)`を呼ぶ。「ちょうど6本」は「既知の6本を含む」へ、鎖は「最初の5本がCHAIN、6本目がtest_sc_03（START b626c98）、長さ6以上、全範囲試験が鎖の上」、開いた範囲は「0か1で、あれば最後」に変わった。前回§6(1)〜(3)のとおり |
| P-01 | **反映** | 1行の表で各祖先検査を単独で働かせる試験2件（c8ba08f→ac21980をtip HEADで、adfdf765→c8ba08fをtip ac21980で）。前回の提案どおりHEADの線上のコミットだけを使うので、他のブランチが無いクローンでも動く |
| P-02 | 未対応（範囲外、任意） | 前回の推奨どおり。次に5本の`git_show_at_end`を触る機会に扱う |

回帰の試験（test_this_test_audits_head_and_does_not_read_the_range_of_the_scope_stage）は、コミット済みのtest_sc_02自身をASTで読み、test_sc_03のimport、`REV`・`END`の名前が無いこと、range_tests・judge_chainのtip引数が`TIP`（表を作る試験では固定コミットの文字列も可）であることを確かめる。作業ツリーは読まない。

## 3. この再レビューで実行した確認

**全スイート**：Linux 6.18、`unshare -n -r`、版ごとの完全履歴の別クリーンクローン（core.autocrlf=false、HEAD＝00094cc、実行後の作業ツリー差分0）、`PYTHONDONTWRITEBYTECODE=1 <python> -B -W error::ResourceWarning -m unittest discover`。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---:|---|---|---|---|
| 既存10スイート（v2_core〜v2_history_adopt） | 1634 | 1630合格＋4 skip | 同左 | 同左 | 同左 |
| v2_scope_chain | **34**（31＋回帰1＋P-01の2） | OK | OK | OK | OK |

skip 4はWindows専用で、開始点と同じ。`git archive 00094cc`のツリーではv2_scope_chain 34件中33件skip（PathJudgementの1件だけ実行）、失敗0。

**R-01のプローブ**（前回の`docs/reviews/v2_scope_range_freeze_review_20261103/r01_chain_after_freeze_probe.sh`）：

| 対象 | 結果 |
|---|---|
| dda7eb7（修正前） | 終了1（R-01あり、鎖の試験はOK） |
| 00094cc | **終了0**（鎖の試験が16件失敗） |
| bfbde7a | **終了0** |

**次の段階の模擬**（bfbde7aから使い捨てのコミット。tests/v2_scope_chain/34件を実行）：

| 模擬 | 結果 |
|---|---|
| test_sc_03のENDをbfbde7aにし、START＝bfbde7a・END＝Noneの範囲試験を1本足す（正しい次段階） | **OK** |
| 同じことをEND＝dda7eb7で行う（結果文書§11の対照） | OK |
| END＝bfbde7a、新しい範囲試験のSTART＝dda7eb7（隙間） | 失敗16 |
| END＝bfbde7a、正しい範囲試験に加えて2本目の開いた範囲 | 失敗16 |

**欠陥注入**（`v2_scope_range_freeze_fix_rereview_20261103/rereview_mutants.py`、00094ccを壊した使い捨てのコミット、Python 3.13）：

| # | 壊し方 | 結果 |
|---|---|---|
| R1 | judge_chainから「ENDがtipの祖先」を外す | 検出（P-01の試験） |
| R2 | judge_chainから「STARTがENDの祖先」を外す | 検出（P-01の試験） |
| R3 | test_sc_02が再びtest_sc_03のREVをTIPとして読む | 検出（回帰の試験） |
| R4 | TIPを古いコミットの固定値にする | 検出 |
| R5 | 「全範囲試験が鎖の上」の検査を外す | 未検出・等価（同じことを判定器の「gap」検査が見て、test_the_real_chain_has_no_gap_and_no_overlapが落ちる） |
| R6 | 判定器が開いた範囲2つを通す | 検出 |

実装者の再注入（R1〜R3、上限の緩和）は再実行していない。結果は本レビューの実測と矛盾しない。

## 4. 次の段階への注意（指摘ではない）

この段階の受領時の最終コミットは、修正を含む**bfbde7a**である（dda7eb7ではない）。次の段階（CONSUME・S3-C）は、
1. test_sc_03_scope.pyの`END = None`を`END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"`に替える（1行）。
2. 自分の新しい範囲試験を`START = "bfbde7a…"`、`END = None`で書く。

dda7eb7で固定しても鎖はつながるが、test_sc_03の監査がR-01の修正（test_sc_02と結果文書§11）を含まなくなり、次の段階の範囲試験がそれを自分の差分として抱えることになる。test_sc_02は書き換えずにHEADの鎖を見続ける。

## 5. 保護参照

依頼書§7の65参照＋資料ブランチ08072cc＋前回レビューfa4b232の**67参照**を`git ls-remote`の完全SHAで照合した。開始時（2026-11-03T10:58:26Z）67/67一致。修正ブランチはbfbde7aのまま、実装ブランチはdda7eb7のまま。push後の照合はスレッドの報告に記す。

## 6. 未実施・変更

- 実Windows、ユーザーPC、core.autocrlf=true、Python 3.10〜3.13以外は未実施。
- 変更したのは、bfbde7aから作った新しい資料ブランチ docs/v2-scope-range-freeze-fix-rereview-20261103 上の本書と欠陥注入スクリプト1本だけ。製品コード、既存試験、修正・実装ブランチ、main、既存の資料ブランチは変更していない。PR・マージ・Actions・本番・通知・CONSUME・S3-Cなし。
- モデル別の利用量は未計測。
