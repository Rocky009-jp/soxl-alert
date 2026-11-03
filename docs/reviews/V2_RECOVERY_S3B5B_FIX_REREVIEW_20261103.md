# V2 S3-B-5b R-01 限定修正 再レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（コーディネーター経由のRockyさんの依頼）。製品コード・既存試験の変更なし。
結論：**前回の通常1件（R-01）は解消。新しい重大0・通常0・提案2。**
R-01の限定修正は受領可能と判断する。提案2件は必須修正ではない。本レビューはPR・マージ・本番反映・CONSUME・S3-Cへの移行承認ではない。

## 1. 固定対象と範囲

| 項目 | 完全SHA・内容 |
|---|---|
| 修正開始 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01（feat/v2-history-adopt-s3b5b-20261103） |
| 修正の試験対象 | **61659892086b559a4e9c62caedcc79145f0b75dd** |
| 結果文書つき最終 | **b626c98af5f01bc94e7b41d86aadde9663695eb9** |
| 修正ブランチ | fix/v2-history-adopt-s3b5b-review-20261103（bad7fbc→6165989→b626c98） |
| 前回レビュー・修正依頼・再現コード | 92630a3d5233f14900c7472dc754850701a56b61（docs/v2-history-s3b5b-review-20261103） |
| 固定設計・元依頼 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |

修正開始→試験対象は**3ファイル、+231/−6**：`v2_history_adopt/confirm.py`（+23/−4）、`tests/v2_history_adopt/test_a5_07_runtime_audit.py`（ALLOWED_NAMESの2行だけ）、新規`tests/v2_history_adopt/test_a5_09_review_fix.py`（206行）。試験対象→最終は`docs/implementation/V2_RECOVERY_S3B5B_RESULT.md`の末尾追記だけ（+139/−0、旧§1〜§10は無変更）。プロジェクトフォルダの同名文書とバイト一致。

依頼案§2の許可表と照合した。audit試験は既存公開名`v2_history.KINDS`と`v2_history.common.is_date`の追加だけで、検査本体・他の制約に差分はない。既存6ランタイムのB-5b差分、旧6試験の補正、B-5a、その他のランタイム・試験・fixture・設定・依存・workflowに差分はない。公開API、エラーcode、basisのキー数、保存schema、復元下限は不変。**変更は依頼範囲内。**

読んだもの：CLAUDE.md、前回レビュー全文と再現コード、限定修正依頼案、結果文書の追記R1〜R7、修正差分全文、`confirm.py`全体、`v2_history_diagnose/describe.py`（discardedの生成元）、`v2_history_adopt/values.py`（AdoptionPlan.from_dict）、`prepare.py`、`build.py`のschema判定、新回帰試験全文。

## 2. 指摘ごとの確認

| ID | 判定 | 根拠 |
|---|---|---|
| R-01 discardedの形・計画内整合 | **解消** | `_form_ok`内の`discarded_ok`／`item_ok`が依頼案§3の規則1〜5をそのまま実装。呼出し位置は`_plan_basis`のhash照合の後・`_candidate_of`の前で、`confirm_prefix_adoption`のdata型判定（手順3）より前。全経路で`history_plan_mismatch`／`plan` |

規則と診断の生成元の対応：診断の`_item`（describe.py:50〜59）はkindを`isinstance(str) and kind in KINDS`か`?`、seqを`is_int`か`None`、dを`is_date`か`None`、request_idを`valid_request_id`か`None`に正規化し、indexは`enumerate`の絶対位置、`from_index`はprefix長、`count`は`len(items)`。confirmは**同じ述語（is_int、is_date、valid_request_id、KINDS）**で検査するので、診断が作る形を拒否する余地はない。採用はschema 2限定（build.pyで`schema_1`を拒否）なので、診断側のV1_KINDS分岐はこの経路に来ない。

例外の漏れ：`_form_ok`に届くbasisは`AdoptionPlan.from_dict`でJSON型だけに制限済み（tupleなどは`json_type`で拒否されることを実測）で、`canonical_json`によるhash照合も先に通っている。`set(item)`、`in KINDS`（tuple）、`is_date`（非strはInputError→False）はいずれもJSON値で例外を出さない。下記ファズでも想定外の例外は0件。

**残る限界（依頼案§3どおり、指摘にしない）：** 形と計画内整合を保ったままdiscardedの内容を書き換えた計画は、候補バイト経路でNO_CHANGEになる。元バイト経路では全basis再構築でmismatchになる。結果文書R7と新回帰の`BrokenBlock`にも明記されている。後段での扱いは提案P-02。

## 3. この再レビューで実行した確認

環境：Linux 6.18、`unshare -n -r`（OS単位のネットワーク名前空間なし）、各版ごとに完全履歴のミラーから`git clone --no-local`した新規クローン、core.autocrlf=false、HEAD=6165989、作業ツリー差分0。`PYTHONDONTWRITEBYTECODE=1 <python> -B -W error::ResourceWarning -m unittest discover -s tests/<suite> -v`をスイートごとに別プロセスで実行。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---:|---|---|---|---|
| v2_core | 197 | OK | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK | OK |
| v2_persistence_local | 113 | OK（skip 4） | OK（skip 4） | OK（skip 4） | OK（skip 4） |
| v2_recovery | 176 | OK | OK | OK | OK |
| v2_history | 230 | OK | OK | OK | OK |
| v2_history_ops | 173 | OK | OK | OK | OK |
| v2_history_restart | 109 | OK | OK | OK | OK |
| v2_history_restore | 165 | OK | OK | OK | OK |
| v2_history_diagnose | 131 | OK | OK | OK | OK |
| v2_history_adopt | **170**（旧155＋新15） | OK | OK | OK | OK |
| **合計** | **1634** | **1630合格＋4 skip** | 同左 | 同左 | 同左 |

- skip 4件はすべてWindows専用（RealWindows 3件＋RealWindowsLockDirectory 1件）。合格に数えない。scope試験（a5_08、b17ほか）は完全な履歴があるクローンで実行され、skipなし。
- 注意：`git archive`で作ったツリー（.gitなし）では、scope系試験が「the code start commit is not available」でさらに29件skipになる（ops 3・restart 3・restore 5・diagnose 8・adopt 10）。件数を比べるときは完全クローンで実行すること（結果文書の数値は完全クローン前提で一致）。
- 実行後の`__pycache__`は0、`git status`差分0。

**付属プローブ**（92630a3の`docs/reviews/s3b5b_review_probe.py --expect-fixed`）：

| 対象 | Python | 結果 |
|---|---|---|
| 6165989 | 3.13.18／3.10.20 | **終了0**。R-01の19観測すべてFIXED、正常結果の対照6/6、元バイトでの拒否14/14、prefix格子56/56 |
| 782debc（修正前、対照） | 3.13.18 | 終了1。19観測すべて未解消（前回レビューの観測を再現） |

**独立プローブ**（本レビューで新規作成、`docs/reviews/s3b5b_fix_rereview_probe.py`、seed 20261103、n 3000）：

| 区分 | 内容 | 6165989 | 782debc |
|---|---|---|---|
| A 誤拒否なし | 実際の診断：damaged位置kと、捨てる側に不正な値（非dict、未知kind、bool/float/負のseq、存在しない日付、不正request_id、余分なキー）を混ぜた1000ファイル | 972件で元バイト→CONFIRMED_IN_MEMORY、候補バイト→NO_CHANGE。残り28件は捨てる側にSCHEMA_MIGRATIONを含みprepareが`migration_discarded`で拒否（B-5bの既存仕様） | 同じ |
| B 計画改変 | discardedを1〜3回ランダムに改変しhash再計算した3000計画。依頼案§3を独立に実装した判定器で期待値を決め、候補・元バイト・None・他のバイトの4経路を確認 | 形式違反2396件がすべて4経路でmismatch。形式どおり604件は期待どおり（うち内容を変えた384件は候補バイトでNO_CHANGE＝§2の限界） | 形式違反1842件が誤判定 |
| C 厳密整数 | from_index＝6.0、index＝6.0、adopt_count＝1でのfrom_index＝True | 5例すべてmismatch | 5例すべてNO_CHANGE |

想定外の例外：0件（3.13.18、3.10.20とも`FINDINGS 0`、終了0）。

**感度の追試**（新回帰`test_a5_09`だけを、`confirm.py`の1箇所を壊した木で実行）：

| 変異 | 結果 |
|---|---|
| discarded_okを呼ばない（修正前と同等） | 検出（177失敗） |
| countのis_intを外す | 検出 |
| itemのキー集合検査を外す | 検出 |
| seqの検査を外す | 検出 |
| kindを「任意のstr」に緩める | 検出 |
| `all`を`any`に変える | 検出 |
| **from_indexのis_intを外す** | **未検出**（新回帰はOK）。実際にはfloat 6.0、adopt_count＝1でのTrueがNO_CHANGEになる（独立プローブCで確認）→ P-01 |
| **itemのindexのis_intを外す** | **未検出**。float 6.0のindexがNO_CHANGEになる → P-01 |
| itemsをtupleでも許す | 未検出だが等価（from_dictがtupleを`json_type`で拒否するため到達しない） |
| itemの`isinstance(dict)`を`hasattr(keys)`に緩める | 未検出だが実質等価（JSON値でkeysを持つのはdictだけ） |

担当者の16変異（検出15・等価1）は再実行していない。担当者の「等価D（count>=0を外す）」は、countが厳密整数かつ`len(items)==count`なので同意する。

## 4. 保護参照

依頼§8の60参照＋資料5d21c10＋元実装782debcの**62参照**を`git ls-remote`の完全SHAで照合：レビュー開始時（2026-11-03T09:21:20Z）62/62一致。保存直前・push後の照合は報告に記す（本書には自分のpush後の結果を書けない）。前回レビューの資料ブランチ92630a3、修正ブランチb626c98も開始時から不変。

## 5. 提案（必須修正ではない）

### P-01 新回帰がfrom_index・itemのindexの「厳密整数」を固定していない

- 根拠：`breakages()`の`bool_start`（from_index＝True）と`item_bool_index`（index＝True）は、world（adopt_count＝6）では値の不一致でも拒否されるため、`is_int`を外しても検出されない。float（6.0）の例はない。上の感度追試で2変異が未検出。
- 実装は正しい（独立プローブCで5例すべてmismatch）。将来の回帰を防ぐ試験の不足だけ。
- 案：次に`test_a5_09`を触る機会に、`float_start`（from_index＝float(k)）、`item_float_index`、adopt_count＝1のworld（`Z.damaged_at(X.ex_new(), 1)`）での`bool_start`／`item_bool_index`を各1件足す。今回のための再修正は不要。

### P-02 NO_CHANGE経路で返った計画のdiscarded・diagnosis_digestは「未検証の表示値」として後段に渡す

- 根拠：§2の限界。候補バイト経路では、形が正しく内容が偽のdiscardedやdiagnosis_digestを区別できない（独立プローブBで384件）。候補の採用記録のevidenceはraw_sha256・raw_sizeなどを持つが、捨てる側の明細は持たない。
- 影響は今回の範囲ではない（confirmは候補Historyしか返さず、通知や保存をしない）。
- 案：CONSUME・S3-Cの設計で、捨てた記録の件数・明細を通知や台帳に使う場合は、元バイトでのCONFIRMED_IN_MEMORYを得た計画からだけ取る、またはNO_CHANGE由来なら「未検証」と表示する、と設計に1行入れる。

### 補足（指摘にしない）

結果文書R3の差分は抜粋で、hunk見出しと文脈行が`git diff`の出力と一致しない（例：audit試験は実際には`@@ -14,9 +14,9 @@`）。正本はリポジトリの差分なので実害はないが、今後は「抜粋」と書くか`git diff`の出力をそのまま貼るとよい。

## 6. 未実施

実Windows、ユーザーPC、core.autocrlf=true、物理電源断、Python 3.10〜3.13以外は未実施。担当者の結果文書にある数値（4版のクリーンクローン、16変異）は報告として受領し、本レビューの実測とは区別した（本レビューで同じ件数を独立に再現したのは§3の表の範囲）。

変更したのは新しいレビュー資料ブランチ上の本書と独立プローブだけ。製品コード、既存試験、既存結果、main、既存の実装・資料ブランチは変更しない。PR・マージ・Actions・本番反映・通知・CONSUME・S3-Cなし。
