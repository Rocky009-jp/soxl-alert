# V2 範囲試験の固定 限定実装 レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（`get_session`で`session_context.model`＝claude-opus-5-5[1m]、`last_served_model`＝claude-opus-5-5、`effort_level`＝high を確認）。コーディネーター経由のRockyさんの依頼。製品コード・実装ブランチ・既存試験は変更していない。
結論：**重大0・通常1・提案2。推奨は「R-01だけの限定修正」。** 5本の固定（置換5種・91行）、ランタイム差分0、範囲遵守、既存1634件の維持、F-06の効果は独立に確認でき、受領できる品質である。ただし新しい鎖の試験（test_sc_02）は、結果文書が書く「次の段階はtest_sc_03のENDを1行替えるだけ」に従うと、HEADの鎖を見なくなる（R-01）。この段階の目的（次の段階の補正を1行にする）に直結するため、CONSUME・S3-Cの前に直すことを推奨する。
本レビューはPR・マージ・本番反映・CONSUME・S3-Cへの移行の承認ではない。

## 1. 対象・参照

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | b626c98af5f01bc94e7b41d86aadde9663695eb9 |
| 試験対象 | **584b406ad8707dab1ccf1c77e209f870ade234f4** |
| 保存最終 | **dda7eb706637adc5f6dd37513e4b6ca360fde2ba**（feat/v2-scope-range-freeze-20261103） |
| 基準（設計・依頼書・試行差分） | 08072cc47aa12340ed947d40f02ca8741a4060d6（docs/v2-scope-range-freeze-20261103）。D-1〜D-4はRockyさんが推奨どおり採用 |

差分：b626c98→584b406は**M 5本・A 4本**（tests/v2_scope_chain/のsc_helpers.py、test_sc_01〜03）。584b406→dda7eb7は結果文書1本のAだけ。PRは0件（GitHub APIで確認）。
読んだもの：CLAUDE.md、設計・依頼書全文、結果文書全文、5本の差分全文、tests/v2_scope_chain/ 4ファイル全文、5本のEND時点・b626c98時点の文字（git show）。

## 2. 変更境界の独立確認（F-02〜F-05、F-08）

実装者の試験やスクリプトを使わず、自作のスクリプト（`v2_scope_range_freeze_review_20261103/freeze_audit.py`、`freeze_gaps.py`）で確かめた。

| 確認 | 結果 |
|---|---|
| 加えた最上位の要素 | 5本とも`END`、`import io`、`git_show_at_end`の3つだけ。削除0、順序はb626c98と同じ |
| 固定しない部分 | 固定対象以外の最上位の要素（Runtime、Imports、NoSideEffects、PathJudgement、パス判定関数、KIND_CONSTANTS、a5_08のPINNED_TESTS等）はb626c98と**1文字も違わない**。要素の間で変わったのは`git_show_at_end`の前後の空行だけ |
| 固定した部分とENDの時点の差 | difflibで行ごとに分類し、すべてが5種の規則で説明できた：`"HEAD"`→`END`、`"hash-object", path`→`"rev-parse", END + ":" + path`、`open(os.path.join(ROOT, X), encoding="utf-8")`→`io.StringIO(git_show_at_end(X))`、a5_08のlistdir→ls-tree（1行→2行）、setUpの2行。行数は b17 −4/+6、r3_07 −4/+6、r4_09 −10/+12、d5_08 −11/+13、a5_08 −11/+14、**計91行（−40/+51）**で結果文書・PINNED_REPLACEMENTSと一致 |
| 固定部分の残り | コードとしての"HEAD"トークン（tokenizeで確認）0。open・hash-object・listdir・walk 0。r3_07の固定文字列内の`START, "HEAD"`は残っている |
| START・END（F-02） | 5本のENDは設計§5.1の完全SHA。r3_07・r4_09のSTARTはr3_helpers／r4_helpersのFIXED_START（ヘルパーは差分0）。adfdf765→b328844→d82a5ce→ac21980→c8ba08f→b626c98で隙間なし |
| 自分の範囲（F-08） | ランタイム9パッケージ、他の試験・ヘルパー・fixtures、main.py、research、docs（結果文書以外）、設定・依存・workflowの差分0 |

固定の方式は設計§5.2どおりで、範囲外の変更はない。

## 3. 試験の再現（F-01、F-06、F-09）

環境：Linux 6.18、`unshare -n -r`、版ごとに完全履歴の別クリーンクローン（core.autocrlf=false、HEAD＝584b406、作業ツリー差分0）、`PYTHONDONTWRITEBYTECODE=1 <python> -B -W error::ResourceWarning -m unittest discover`（スイートごとに別プロセス）。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---:|---|---|---|---|
| v2_core | 197 | OK | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK | OK |
| v2_persistence_local | 113 | OK（skip 4） | OK（skip 4） | OK（skip 4） | OK（skip 4） |
| v2_recovery | 176 | OK | OK | OK | OK |
| v2_history | 230 | OK | OK | OK | OK |
| v2_history_ops | 173 | OK | OK | OK | OK |
| v2_history_restart（test_r3_*） | 109 | OK | OK | OK | OK |
| v2_history_restore（test_r4_*） | 165 | OK | OK | OK | OK |
| v2_history_diagnose（test_d5_*） | 131 | OK | OK | OK | OK |
| v2_history_adopt（test_a5_*） | 170 | OK | OK | OK | OK |
| **既存計** | **1634** | 1630合格＋4 skip | 同左 | 同左 | 同左 |
| v2_scope_chain（新規） | 31 | OK | OK | OK | OK |

- skip 4はWindows専用で、開始点と同じ。
- **F-06（独立に再実施）**：設計§7と同じ変更（3つのランタイムへのコメント1行ずつ、新規v2_history_next/\_\_init\_\_.py、試験1本、結果文書1本）を使い捨てのクローンで1コミットにし、5本だけを実行。b626c98基準は失敗2・2・2・2・3（計11）、dda7eb7基準は5本ともOK。結果文書§5と一致。
- **F-09（独立に再実施）**：`git archive 584b406`の展開先で、b17 skip 3、r3_07 3、r4_09 5、d5_08 8、a5_08 10（計29）、v2_scope_chain 31件中30 skip。失敗0。結果文書§6と一致。

## 4. 新しい試験（tests/v2_scope_chain/）の妥当性

test_sc_01（固定の監査）とtest_sc_03（自分の範囲・副作用）は設計§8の1・3を満たす。test_sc_01がREV（＝test_sc_03のEND or "HEAD"）を読むのは正しい。次の段階が古いパッケージの静的な検査を直したとき、test_sc_01がHEADを読むと「固定しない部分がb626c98と同じ」が壊れるからである。

一方、test_sc_02（範囲の鎖）も同じREVを読み、鎖の終点（tip）にも使っている。これがR-01である。

本レビューで行った欠陥注入（`review_mutants.py`、584b406を壊した使い捨てのコミット、Python 3.13）：

| # | 壊し方 | 結果 |
|---|---|---|
| R1 | judge_chainから「ENDがtipの祖先」の検査を外す | **未検出**（→P-01） |
| R2 | judge_chainから「STARTがENDの祖先」の検査を外す | **未検出**（→P-01） |
| R1＋R2 | 両方を外す | 検出（2件） |
| R5 | b17のモジュールdocstringを1語変える | 検出 |
| R6 | d5_08に最上位の関数を1つ足す | 検出 |
| R9 | 範囲試験の自動探索からadoptを外す | 検出 |
| R10 | r3_07のFilesChangedに無害な1行を足す | 検出 |
| R11 | b17の`git_show_at_end`に作業ツリーへのフォールバック（`out.stdout or open(...)`）を足す | **未検出**（→P-02） |

実装者の欠陥注入17点は再実行していない（報告として受領）。

## 5. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| R-01 | 通常 | test_sc_02_chain.py：`from test_sc_03_scope import REV`、`C.range_tests(REV)`、`judge_chain(..., REV, ...)`。さらに「範囲試験はちょうど6本」「鎖は6本」「開いた範囲はtest_sc_03」を固定している | 結果文書§3・§9と設計§6.2どおり次の段階がtest_sc_03の`END = None`を受領SHAに替えると、REVがdda7eb7になり、鎖の試験はdda7eb7の木だけを見る。HEADで隙間のある範囲試験や2つ目の開いた範囲があっても合格する。設計§6.3「各ENDがHEADの祖先」「段階が増えても書き換えが要らない」と依頼書§3に反し、結果文書§9「END以後は最新の開いた範囲試験と鎖の試験が覆う」が次の段階から成り立たない | §6の限定修正 | `r01_chain_after_freeze_probe.sh`：584b406で終了1（試験はOKのまま、判定器はHEADで「2 open ranges」「3 chain beginnings」を返す）。修正後は終了0 |
| P-01 | 提案 | ChainJudgeの「ENDがSTARTの祖先でない」「ENDがtipの祖先でない」の表は、別の検査（つながり、もう一方の祖先検査）でも拒否される | 二つの祖先検査のどちらか一方を外しても試験が通る（R1・R2）。判定器そのものは正しい（それぞれを単独で働かせる表で拒否を確認） | 1行の表で各検査を単独で働かせる試験を2件足す：`[{start: c8ba08f, end: ac21980}]`をtip HEADで（STARTがENDの祖先でない）、`[{start: adfdf765, end: c8ba08f}]`をtip ac21980で（ENDがtipの祖先でない）。どちらもHEADの線上のコミットなので、他のブランチが無いクローンでも動く | R1・R2を再注入して検出 |
| P-02 | 提案 | 5本の`git_show_at_end`は加えた要素なので、F-04の「作業ツリーを読まない」検査（固定部分だけが対象）の外にある。test_sc_01は本体に`git show END:path`の文字があることしか見ない。また`returncode`を見ず、`text=True`でロケールの文字コードで読む（元のopenは`encoding="utf-8"`） | 本体に作業ツリーへのフォールバックを足しても検出されない（R11）。今は読む5本・ヘルパーがすべてASCIIで、gitが失敗すると空文字→後の比較が失敗するので、実害はない | 次に触る機会に、test_sc_01で5本の`git_show_at_end`の本文をENDごとに同じ固定文字列と比べる。必要なら`encoding="utf-8"`と`returncode`の検査を足す。今回の限定修正に入れなくてよい | R11を再注入して検出 |

## 6. 推奨：R-01の限定修正

Rockyさんは「レビュー結果の推奨どおり進める」としているので、推奨を明示する：**受領の前に、R-01だけの限定修正を行う。P-01は同じファイルを触るので一緒に入れてよい（推奨）。P-02は任意で、今回は入れない。**

| 項目 | 内容 |
|---|---|
| 開始点・ブランチ | dda7eb706637adc5f6dd37513e4b6ca360fde2ba から fix/v2-scope-range-freeze-review-20261103 |
| 担当 | Sonnet 5.5・high（機械的で範囲が小さい） |
| 変更してよいファイル | tests/v2_scope_chain/test_sc_02_chain.py、docs/implementation/V2_SCOPE_RANGE_FREEZE_RESULT.md（末尾への追記）。sc_helpers.pyは変えない。test_sc_01・test_sc_03・5本・ランタイムは変えない。test_sc_03のFilesChangedは、どちらの変更もSTART時点に無いファイルなのでAのまま通る |
| 修正の中身 | (1) test_sc_02は範囲試験ではなく、常にコミット済みのHEADを監査する試験とする。`TIP = "HEAD"`を置き、`range_tests(TIP)`と`judge_chain(..., TIP, CHAIN_START)`で読む。test_sc_03からREV・ENDをimportしない（STARTは鎖の6本目の確認に使ってよい）。(2) 「ちょうど6本」の固定を「既知の6本を含む」に変える：鎖の最初の5本がCHAIN、6本目がtest_sc_03（START b626c98）、長さは6以上。開いた範囲は0本か1本で、あれば鎖の最後。(3) 回帰：test_sc_02のASTに`REV`・`END`のimportが無く、`range_tests`と`judge_chain`の引数がTIPであることを確かめる試験を1件。(4) P-01の2件 |
| 受入 | 既存1634＋新規（31＋追加分）がPy3.10〜3.13の完全クローンで合格。`r01_chain_after_freeze_probe.sh <clone> <修正の試験対象>`が終了0。対照として、test_sc_03のENDをdda7eb7にし、START＝dda7eb7・END＝Noneの正しい範囲試験を1本足した使い捨てコミットでtest_sc_02が合格することを結果文書に記す。R1・R2の再注入が検出されること。保護66参照＋本レビューの資料ブランチの照合 |
| 止める条件 | test_sc_01・test_sc_03や5本の変更が必要になった場合、または設計§6の規則の追加が必要な場合は、変更せず報告する。CONSUME・S3-C・P-02には広げない |

修正後の次の段階の手順は変わらない：test_sc_03の`END = None`を受領SHAに替える1行と、静的な検査の必要箇所、新しい範囲試験（START＝そのSHA、END＝None）。test_sc_02は書き換えずにHEADの鎖を見続ける。

R-01を直さずに受領する場合は、次の段階（CONSUME・S3-C）の依頼書に「test_sc_02をHEAD基準に直す」を必ず含める必要がある。この段階の目的（次の段階の補正を1行にする）に反するので推奨しない。

## 7. 保護参照

依頼書§7の65参照＋資料ブランチ08072ccの**66参照**を`git ls-remote`の完全SHAで照合した。開始時（2026-11-03T10:32:49Z）66/66一致、確認作業の後（10:46:18Z）66/66一致。実装ブランチfeat/v2-scope-range-freeze-20261103はdda7eb7のまま。push後の照合はスレッドの報告に記す。

## 8. 未実施・変更

- 実Windows、ユーザーPC、core.autocrlf=true、Python 3.10〜3.13以外は未実施。実装者の欠陥注入17点、実装者の変換スクリプトは再実行していない。
- 変更したのは、dda7eb7から作った新しい資料ブランチ docs/v2-scope-range-freeze-review-20261103 上の本書と、`docs/reviews/v2_scope_range_freeze_review_20261103/`の確認スクリプト5本（freeze_audit.py、freeze_gaps.py、review_mutants.py、run_all_suites.sh、r01_chain_after_freeze_probe.sh）だけ。製品コード、既存試験、実装ブランチ、main、既存の資料ブランチは変更していない。PR・マージ・Actions・本番・通知・CONSUME・S3-Cなし。
- モデル別の利用量は未計測。
