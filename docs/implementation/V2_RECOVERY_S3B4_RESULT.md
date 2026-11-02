# V2 S3-B-4 復元計画・確認 限定実装 結果記録

作成日：2026-11-02（日本時間）。担当：Claude Sonnet 5.5（実設定の確認は§1）。
状態：**限定実装・自己試験まで完了。レビュー待ち。PR・マージ・CONSUME・B-5・S3-Cには進んでいない。**
B-4は**候補Historyまで**である。保存・バッチ・耐久性は達成していない。CONSUMEは保留（必要な日は`restore_requires_consume`で停止する）。成否不明時の計画保持と公開後の照合はS3-Cの範囲である（§9）。

## 1. 固定入力・モデル・SHA

| 項目 | 値 |
|---|---|
| 採用 | Rockyが2026-11-02にD-1〜D-3（既知の制限＝設計§7.1案aを含む）を採用し、B-4限定実装を承認（スレッドの指示） |
| モデルの実設定 | セッション情報の確認結果：configured_model＝`claude-sonnet-5-5[1m]`、session_context.model＝`claude-sonnet-5-5[1m]`、last_served_model＝`claude-sonnet-5-5`、effort_level＝`high`。D-3（Sonnet 5.5・high）と一致 |
| 固定した資料 | 資料ブランチ docs/v2-history-s3b4-v2-receipt-20261102 の**0108131045d904b0997299fcade5929567940d6d**（設計・依頼書本体は第2版 f353fb96557993e95049dd7dfd57286a80f1afb4 と同じ内容。途中で追従していない） |
| 依頼書blob | docs/tasks/V2_RECOVERY_S3B4_LIMITED_IMPLEMENTATION_REQUEST.md ＝ dcbc98b2b7ca5fcc5a96d783b98f7a1711a71731 |
| 設計書blob | docs/specs/V2_RECOVERY_S3B4_RESTORE_PLAN_DESIGN_DRAFT.md ＝ 6111058bdc0ae8eba1df15caccee03f83dd14d59 |
| コード開始点 | d82a5ced64658c2e736b82b1a2f1925636055417（feat/v2-history-restart-s3b3-20261102） |
| 実装ブランチ | feat/v2-history-restore-plan-s3b4-20261102（d82a5ceから作成。同名は無かった） |
| コミット | 実装＋scope補正2本 e7987c979500171fe0f1349a4c1062985cb01e20 → 受入試験140件 1338f53c20f37158d0fc47a7bb1a445576e87c7d → 欠陥注入スクリプトと追加試験 **47eb7c5c8c42acc8e218b3b891ce1b6a02e5a664**（コード・試験の最終＝**試験対象SHA**） |
| 保存最終SHA | 本文書だけを加えた次のコミット（コミット後にスレッドで報告。本文書にはSHA自身を書けない） |
| 保護参照 | 依頼書§8の49参照＋資料ブランチ 0108131＝50参照。実装の途中（2026-11-02T04:50:53Z）に49／49、本文書の保存直前（05:01:24Z）に50／50を完全SHAで照合し、差は0。push後の終了時の照合はスレッドで報告 |

読んだもの：CLAUDE.md、設計書、依頼書、再レビュー（V2_RECOVERY_S3B4_V2_REREVIEW）。STATUS・MODEL_POLICY・ROADMAPは、依頼が指示する範囲（B-3までの採用を取り直さない）に従い、内容は依頼書・設計書の記述に依拠した。これらは変更していない。

## 2. 作ったもの

新規パッケージ `v2_history_restore/`（10ファイル、1082行）：`prepare_restore_plan`、`confirm_restore_plan`、`RestorePlan`、`RestoreConfirmResult`、定数 `READY`／`CONFIRMED_IN_MEMORY`／`NO_CHANGE`。`__all__` は設計どおりの7名。既存パッケージの `__init__.py` への再公開は無い。

| ファイル | 内容 |
|---|---|
| `points.py` | 復元点（新GENESIS／移行記録自身は可、head・退避済み・hash違い・移行前・request途中は拒否）と、有効suffixに1対1のops検査（REAPPLY＝APPLYのみ、REPLAY／DROP＝ACK・宣言・UNKNOWN再開始、RETIRE＝復元記録。CONSUMEと未知opはrestore_op_unsupported） |
| `market.py` | REAPPLYする日のseries入力を`through(D)`・`row`・`previous_date`だけで読み、固定する（series_digest） |
| `records.py` | 新記録の草稿：REAPPLYは新親stateから既存`apply_transition`で再計算、REPLAYは新親のstate・DECLAREのfrontier/context・RESTARTのfloorを再計算し、参照を新seqへ写す |
| `chain.py` | 草稿・有効列の読取（FixedFacts、last_segment、frontier、floor、contexts_agree） |
| `build.py` | 準備と確認で共有する8段階（released_days→decision→市場値→B-2全区間投影→evaluate_day→無効果→basis） |
| `prepare.py`／`confirm.py` | 計画の作成、確認A（元履歴→CONFIRMED_IN_MEMORY）／B（自分の候補→NO_CHANGE、元prefixを検査して全basisを再構築） |
| `values.py`／`errors.py` | 不変な`RestorePlan`（23キーbasis）／`RestoreConfirmResult`、固定code |

利用した既存の公開名は設計§13の一覧の範囲だけ。private名、`Chain`／`ledger_of`／`_Walk`／`_Frozen`、S1のCtx／SnapshotView、B-2のbatchは使っていない（AST試験で確認）。戦略式・閾値・状態式は書いていない（新APPLYは既存`apply_transition`、日の照合は既存`evaluate_day`）。

## 3. 全差分

開始点 d82a5ce から 47eb7c5 まで、23ファイル、+4064／−10。

- **新規**：`v2_history_restore/`（10ファイル）、`tests/v2_history_restore/`（r4_helpers.py、r4_sensitivity.py、test_r4_01〜09の9ファイル）。`tests/v2_history_restore/` に `__init__.py` は無い。
- **変更した既存ファイル：`tests/v2_history_ops/test_b17_scope.py`（+6／−3）と `tests/v2_history_restart/test_r3_07_scope.py`（+13／−7）の2本だけ**。それ以外の既存ファイル（ランタイム、既存の機能試験・fixtures、依存、設定、workflow、main.py、研究、STATUS／ROADMAP／CLAUDE）の差分は0。B-3のランタイム・試験・結果文書は、r3_07の3メソッド以外すべてblob一致（新B-4範囲試験が直接検査）。
- 本文書 `docs/implementation/V2_RECOVERY_S3B4_RESULT.md` は新規。旧結果文書には追記していない。
- 「既存試験は全て無編集」とは報告しない。scope試験2本を限定補正した。旧機能試験のテスト関数は増減していない（B-4範囲試験が関数名の一致を検査）。

### scope試験2本の差分全文（開始点 d82a5ce → 47eb7c5）

`tests/v2_history_ops/test_b17_scope.py`

```diff
diff --git a/tests/v2_history_ops/test_b17_scope.py b/tests/v2_history_ops/test_b17_scope.py
index a394608..ca2df74 100644
--- a/tests/v2_history_ops/test_b17_scope.py
+++ b/tests/v2_history_ops/test_b17_scope.py
@@ -182,10 +182,12 @@ class FilesChanged(unittest.TestCase):
         changed = [line.split("\t") for line in out.stdout.splitlines()]
         for status, path in changed:
             allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",
-                                        "v2_history_restart/", "tests/v2_history_restart/"))
+                                        "v2_history_restart/", "tests/v2_history_restart/",
+                                        "v2_history_restore/", "tests/v2_history_restore/"))
                        or path in ("v2_recovery/facts.py", "v2_recovery/commands.py",
                                    "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",
-                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))
+                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
+                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
             if not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")):
                 if path != "v2_recovery/commands.py":
@@ -197,6 +199,7 @@ class FilesChanged(unittest.TestCase):
         self.assertIn("v2_recovery/commands.py", paths)
         for path in paths:
             self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"
+                             and path != "v2_history_restore/__init__.py"
                              and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)
 
     def test_commands_py_changes_are_the_two_allowed_ones_only(self):
@@ -213,7 +216,7 @@ class FilesChanged(unittest.TestCase):
 
     def test_existing_tests_and_fixtures_are_untouched(self):
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",
-                       ":(exclude)tests/v2_history_restart")
+                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore")
         self.assertEqual(out.stdout.strip(), "")
         out = self.git("diff", "--name-only", START, "HEAD", "--", "main.py", "requirements.txt", ".github", "research",
                        "docs/STATUS.md", "docs/ROADMAP.md", "CLAUDE.md")
```

`tests/v2_history_restart/test_r3_07_scope.py`（変更は3メソッドの中だけ）

```diff
diff --git a/tests/v2_history_restart/test_r3_07_scope.py b/tests/v2_history_restart/test_r3_07_scope.py
index 3be74af..d7bf3db 100644
--- a/tests/v2_history_restart/test_r3_07_scope.py
+++ b/tests/v2_history_restart/test_r3_07_scope.py
@@ -190,13 +190,15 @@ class FilesChanged(unittest.TestCase):
             if path == "tests/v2_history_ops/test_b17_scope.py":
                 self.assertEqual(status, "M", path)
                 continue
-            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/")) or path in (
-                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",)
+            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",
+                                       "v2_history_restore/", "tests/v2_history_restore/")) or path in (
+                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md")
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
             self.assertEqual(status, "A", path)                          # new files only
         paths = {p for _s, p in changed}
         self.assertIn("v2_history_restart/__init__.py", paths)
-        self.assertEqual({p for p in paths if p.endswith("__init__.py")}, {"v2_history_restart/__init__.py"})
+        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
+                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py"})
 
     def test_no_existing_runtime_old_test_fixture_or_setting_differs(self):
         out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",
@@ -204,7 +206,8 @@ class FilesChanged(unittest.TestCase):
                        "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md",
                        "docs/implementation/V2_RECOVERY_S3B2_RESULT.md")
         self.assertEqual(out.stdout.strip(), "")
-        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart")
+        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",
+                       ":(exclude)tests/v2_history_restore")
         self.assertEqual(out.stdout.split(), ["tests/v2_history_ops/test_b17_scope.py"])
 
     def test_the_old_range_test_differs_in_exactly_the_three_allowed_places(self):
@@ -222,13 +225,16 @@ class FilesChanged(unittest.TestCase):
             '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")'])
         self.assertEqual(added, [
             '            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",',
-            '                                        "v2_history_restart/", "tests/v2_history_restart/"))',
+            '                                        "v2_history_restart/", "tests/v2_history_restart/",',
+            '                                        "v2_history_restore/", "tests/v2_history_restore/"))',
             '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",',
-            '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))',
+            '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
+            '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
             '            self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"',
+            '                             and path != "v2_history_restore/__init__.py"',
             '                             and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)',
             '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",',
-            '                       ":(exclude)tests/v2_history_restart")'])
+            '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore")'])
 
 
 if __name__ == "__main__":
```

補正の趣旨：(1)許可パスに新規2ディレクトリと結果文書を足す、(2)旧試験無変更のGit検索から新規B-4試験を除く、(3)末尾の`__init__.py`検査に`v2_history_restore/__init__.py`を単一パスで例外にする。r3_07は3メソッドの`added`リテラルとexcludeだけを更新し、`removed`側は不変（ハンクは4のまま）。新規の `test_r4_09_scope.py` が両ファイルの削除行・追加行・ハンク位置を文字列で固定し、これ以外の緩和があれば失敗する。

## 4. 受入とテスト名の対応（新規144件）

新規Nは**144件**（実測）。ファイル別：01＝13、02＝14、03＝21、04＝17、05＝15、06＝21、07＝14、08＝11、09＝18。欠陥注入スクリプト `r4_sensitivity.py` は`test_*`ではなく、件数に含めない。

| 受入 | ファイル：主な試験 |
|---|---|
| B4-01 回帰・変更境界 | §6の既存7スイート（機能試験無編集）＋`test_r4_09`：FilesChanged（変更は2本のみ、B-3のruntime・試験・結果文書を`git ls-tree`のblobと直接照合、旧ランタイム等の差分0、2本の差分リテラル固定、r3_07の編集行が3メソッド内） |
| B4-02 復元点 | `test_r4_01`：新GENESIS・移行記録自身の受理、移行前／head／退避済み／hash違い／request途中の拒否、厳密int（bool・float拒否） |
| B4-03 有効suffix | `test_r4_01`：2回・3回復元後のsuffixが物理区間と異なる例、既退避点の重複退避拒否、旧復元バッチ途中のAPPLYをPにする正常例 |
| B4-04 ops | `test_r4_01`：過不足・順序・重複・未知キー・種別違反・request部分処分の拒否、CONSUME／未知opのrestore_op_unsupported、自動補完なし |
| B4-05 同一入力のREAPPLY | `test_r4_02`：元decision/row/prev_row/prev_session_date保持、新baseからのapply_transition（呼出しspy）、evaluate_day一致、元state/transitionコピーの検出、HB独立ビルダーとの全キー一致 |
| B4-06 現在入力の相違 | `test_r4_02`：市場値だけの変更はrestore_market_input_changed、decision不存在・別ID・指紋違いはrestore_decision_changed、CHANGED／ROW_REMOVED補完で選ばれる保存decisionは成功 |
| B4-07 セッション | `test_r4_02`：中間未確定、prev日、共通context、next(D)のclose／confirmedは無害でopenは有害、check_dのnextのみ未確定は成功 |
| B4-08 新規消費の停止 | `test_r4_03`：ConsumeStop（宣言DROP・再開始DROPの免除区間、後続APPLY無し、null基点、無関係な日は消費しない）、OldSkipAndLateAck（旧skipへの後発をB-2投影がlate_observationで拒否しevaluate_dayを呼ばない：親が非nullでも初期状態でも、DROPしたLATE ACKで戻る後発） |
| B4-09 REPLAY参照 | `test_r4_03`：ReplayReferences（retained／REAPPLY／REPLAYへの写像、DROP依存はrestore_ref_unmapped、二重写像なし、元request系の維持） |
| B4-10 REPLAY再計算 | `test_r4_03`：ReplayRecalculation（新親のstate_after、R-bのDECLARE frontier／context、RESTARTのfloor／初期状態、元stateコピー＋hash付け直しplanをhistory_plan_mismatchで拒否） |
| B4-11 証拠と版 | `test_r4_04`：ReplayEvidence（requestグループごとの`check_commands`呼出しspy、prefixに未来APPLYを混ぜない、ROW_REMOVED＋ADDEDの一括、設計§7.1の2例の既存エラーでの拒否、組を保持し後のRESTARTだけをDROPする成功対照）、除外→補完→版の既存関数spy |
| B4-12 候補完全検査 | `test_r4_04`：CompleteCandidate（旧events不変、RESTORE15キー／request_basis6キー／replay5キー、監査prevと有効親、有効／退避列、バッチ途中の候補の拒否、B-2全区間投影の実呼出しと行集合・digest一致、validate_historyの返値が違う場合の固定拒否） |
| B4-13 失敗の優先順位 | `test_r4_05`：Order（形→ID、残す文脈・候補全体の証拠はIDより後、consume→decision→市場値→B-2投影→evaluate_dayの順をspyで固定、元投影失敗→DROP成功、plan不正は入力より前・入力不正はstaleより前） |
| B4-14 ID/無効果 | `test_r4_05`：IdsAndNoEffect（物理全体のID、他種別・再生・移行のID、時刻だけ違う再準備でrequest_hash同一・plan_hash別、無効果、DROPあり市場state同一の正常例、無効果でも再計算と入力照合は実行） |
| B4-15 plan/hash/差 | `test_r4_06`：PlanContent（23キー全項目の改変＋hash付け直しの拒否、candidate_records末尾一致、series_inputsの範囲・正規化、changesの項目とsameの実値、確認hash違い拒否） |
| B4-16 確認A/B | `test_r4_06`：Confirmation（A：CONFIRMED_IN_MEMORY・入力非変更、B：NO_CHANGE・追加0・prefix検査と全basis再構築のspy、先へ進んだ履歴・別candidate・正常な入力変更はstale、digest一致後の再構築差はmismatch、不正履歴はstaleにしない） |
| B4-17 入力の範囲 | `test_r4_06`：SeriesRange（根のseriesにrow/previous_dateを許さない厳格series、D後の行・表示SOXL・descriptionの変更でseries_digest不変、前史改訂で停止、REAPPLY 0件ならseries未参照、series形式違反は固定エラー） |
| B4-18 不変性/秘匿/型境界 | `test_r4_07`：コピー独立、偽コンテナ、深いJSON・巨大整数・非有限・非str鍵、bool／float整数の拒否、summaryのホワイトリスト、URL・値・自由文を出さない、旧MemoryStoreとfile_sync_onlyのLocalFileStoreがplan_typeで拒否（残留物なし）、`__all__`7名・batch／durabilityの名前なし |
| B4-19 統合例 | `test_r4_08`：設計§13の9例（例1〜9）を実台帳・実seriesで実行、例R／R-bの複数回復元と旧RESTORE RETIRE、§7.1の既知の拒否、DECLARE context差のDROP成功／残るAPPLYが使う日は不成功、正常候補をB-2日次へ渡してALREADY_APPLIED／後発停止 |
| B4-20 範囲監査 | `test_r4_09`：Runtime（許可import・名、旧機構名・private名・I/O・時計・later-stage語の不存在、CONSUMEは`requires_consume`／固定エラー名だけ、新APPLYは`old["d"]`だけから作る、数値定数が0〜7と12だけ、公開名＝7名、ファイル構成、op許可集合4つと拒否）、PathJudgement（許可パス判定の対照）、試験名の一意性・`__init__.py`なし |

## 5. 実行結果

条件：core.autocrlf=falseの別クリーンクローン（実装ブランチを単一ブランチで取得、HEAD＝試験対象SHA 47eb7c5、作業ツリー差分0）。各スイートを `-B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`（新規のみ `test_r4_*.py`）で実行。OS：Linux 6.18 x86_64。

| 区分 | Python | コア197 | 保存170 | S2 113 | S3-A 176 | B-1 230 | B-2 173 | B-3 109 | 新規N 144 |
|---|---|---|---|---|---|---|---|---|---|
| unshare -rn＋プロセス内socket禁止 | 3.10.20（uv単体） | OK | OK | OK（skip 4） | OK | OK | OK | OK | OK |
| 同上 | 3.11.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK | OK |
| 同上 | 3.12.3 | OK | OK | OK（skip 4） | OK | OK | OK | OK | OK |
| 同上 | 3.13.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK | OK |
| プロセス内socket禁止のみ | 3.13.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK | OK |

5構成×8スイート＝40実行で failures=0、errors=0、終了コード0。S2の113件はLinuxで109合格＋4 skip（Windows専用）で、契約どおり。既存の合計は1168件（1164合格＋4 skip）。新規Nは別に集計した。`unshare -rn` 内の外部connectは遮断される。開発中の作業ツリー（コミット前）でも新規はPython 3.13で合格した。
B-2の173件とB-3の109件は、scope試験1本ずつの限定補正を含む。

## 6. 具体的な復元例（合成データ。requested_at＝2026-06-01T00:00:00Z、D0＝2026-03-02、D1＝03-03、D2＝03-04、D3＝03-05）

**例1（設計§13の最初の例）**：0 GENESIS D0、1 APPLY D1、2 RESTART_UNKNOWN(D1)、3 APPLY D2。復元点P＝1、ops＝{2:DROP、3:REAPPLY}、check_d＝D3、request_id＝r4-review-1。
- prepare → READY。plan_hash＝623ddbed9665b3c623412ce94083660bf30f01d0227172f76dc834d04cc8bcba、request_hash＝f0321596c86b4bf5140b7b69939f8ca239b7222a904b94c9cf1f12223f4da749、candidate_digest＝f2827c34d1aed6a00f8ce9cfdd36d253417d8bbab1993b657559350f72cd20a3。
- 確認A → CONFIRMED_IN_MEMORY。候補は 4 RECOVERY_RESTORE（parent_seq＝1、superseded＝[2, 3]、replay＝DROP(2)・REAPPLY(3→5, same_as_superseded＝false)）と 5 APPLY D2。有効列＝[0, 1, 4, 5]、退避＝[2, 3]、head＝5。独立ビルダーHBが書く記録と全キー一致。
- **復元前後**：旧3 APPLY D2のstate_afterは base.as_of_d＝null（再開始で初期状態から計算）、新5 APPLY D2は base.as_of_d＝2026-03-03（APPLY D1のstateから計算）。streak＝0、prev_normal_raw＝TRUEは同じだが、base（直前のstate）が違うため、`changes`は**changed_fields＝[state_after, transition_result]**（input_hash・skipped_sessionsは同一）。この4項目とsameは実値の比較から出しており、旧値のコピーではない。
- 同じ計画を候補に再確認 → NO_CHANGE、イベント数は6のまま（2件目の復元記録なし）。同IDの新しいprepare → history_request_conflict。時刻だけ変えた再準備は、request_hashは同一・requested_atとplan_hashは別。
- 市場値だけ変えたseries（D2のrsiなど）→ restore_market_input_changed。D2のdecisionが消えた・別IDになった・指紋が違う場合→restore_decision_changed（detail＝D2）。

**例2（R-b）**：0 GENESIS、1 APPLY D1、2 RESTART(D1)、3 APPLY D2、4 DECLARE D3、5 APPLY D4。P＝1、ops＝{2:DROP、3:REAPPLY、4:REPLAY、5:REAPPLY}。changes：DROP(2)／REAPPLY(3→7, same＝false, [state_after, transition_result])／REPLAY(4→8, [state_after])／REAPPLY(5→9, same＝true, [])。有効列＝[0, 1, 6, 7, 8, 9]。

**例3（CONSUME停止）**：0 GENESIS、1 APPLY D1、2 RESTART(D3)、3 APPLY D4。再開始をDROPしてD4をREAPPLYするとD2・D3が通過済みでなくなる。D2またはD3に有効decisionを1件足すと restore_requires_consume（detail＝D2／D3）。決定が無ければ成功。後続APPLY無しのRESTART／DECLAREのDROP、null基点（GENESIS直後のRESTART）でも同じ。

**例4（複数回復元）**：設計8.9の例R（3回復元、有効0,1,2,18〜22）に 23 APPLY、24 RESTART、25 APPLY を足した履歴で、P＝23・{24:DROP、25:REAPPLY}（有効列 [0,1,2,18〜23,26,27]）、およびP＝2で旧RESTORE(18)をRETIRE・19〜23をREAPPLY・24をDROP・25をREAPPLY。どちらもHB独立ビルダーと全キー一致。

**例5（§7.1の既知の制限）**：DECLARE D2＋後のLATE ACK、またはROW_REMOVED＋後のCHANGED ACKは、元履歴のvalidate／全区間投影は成功するが、REPLAYでは `resolution_invalid／commands／declare_valid_decision` または `ack_evidence` で拒否される。LATE ACKが残る場合は宣言だけを再生しても拒否される（遅れた行が台帳にあるため）。Pを組の最後にして保持し、さらに後のRESTARTだけをDROPすると成功する。

## 7. 限定欠陥注入（依頼§6の22項目、61変異）

`tests/v2_history_restore/r4_sensitivity.py`。作業ツリーを一時ディレクトリへ複製し、1件ずつ壊して新規スイートを実行する（4並列）。対照（無変異）は合格。**61変異のうち検出56、等価5、未検出0**。

経緯（正直な記録）：1回目の全実行（試験は1338f53相当）で未検出が9件あった。うち5件（M14／M16c／M19d／M20c／M21a）は、グラフの意味に根拠のある試験を足して検出した（M14：除外→補完→版選択の既存関数spy、M16c：候補のsuperseded列の食い違いの置換、M19d：根のseriesにrow／previous_dateを許さない厳格series、M20c：枝Bのprefix検査spy、M21a：不正履歴をstaleにしないこと）。残る4件（M09c／M12b／M16a／M16d）は、差の出る入力が作れない／独立した防護が残るため、**等価と判断**した（下表、§8）。この9件の再実行は最終コミットで行い、残り52変異は1回目の実行結果（試験は追加後も上位集合のため検出は変わらない）である。検出元の分類は、probeの出力（変異した実装の1例の答え）で、B-4自身の事前拒否（A）、既存validate_historyの独立防護がcodeを変えて止める（B：M01b／M01d／M01e／M03a／M03c／M03d／M04）、委譲・順序のspy（C：M06／M14／M15a〜d／M13a〜d／M20c）に分ける。Bは「誤った候補が受理された」ではなく「codeが変わった」である。

| 変異 | 内容 | 結果 | 検出した主な試験／等価の根拠 |
|---|---|---|---|
| M01a | a superseded record is accepted as the restore point | 検出（1件） | r4\_01\_point\_ops.test\_the\_physical\_head\_is\_a\_no\_op\_and\_a\_superseded\_record\_is\_not\_effective |
| M01b | the physical head is accepted as the restore point | 検出（1件） | r4\_01\_point\_ops.test\_the\_physical\_head\_is\_a\_no\_op\_and\_a\_superseded\_record\_is\_not\_effective |
| M01c | a record before the migration is accepted as the restore point | 検出（1件） | r4\_01\_point\_ops.test\_the\_schema\_migration\_record\_itself\_is\_accepted\_but\_nothing\_before\_it |
| M01d | a record in the middle of a request is accepted as the restore point | 検出（1件） | r4\_01\_point\_ops.test\_a\_point\_in\_the\_middle\_of\_a\_request\_batch\_is\_refused\_but\_its\_last\_record\_is\_a\_valid\_point |
| M01e | a hash that is not the record's is accepted for the restore point | 検出（1件） | r4\_01\_point\_ops.test\_a\_wrong\_hash\_and\_a\_wrong\_form\_are\_refused |
| M02a | the superseded records are the physical interval after the point (not the effective suffix) | 検出（4件） | r4\_01\_point\_ops.test\_after\_two\_and\_three\_restores\_the\_suffix\_is\_the\_effective\_one\_not\_the\_physical\_range |
| M02b | the superseded records come in another order | 検出（109件） | r4\_01\_point\_ops.test\_a\_new\_genesis\_itself\_is\_accepted\_as\_the\_restore\_point |
| M03a | from_seq may be a float or a bool (no strict integer) | 検出（1件） | r4\_01\_point\_ops.test\_the\_list\_must\_be\_a\_list\_of\_exact\_dicts\_with\_strict\_integers |
| M03b | the operations are sorted for the caller (an order that is not the superseded order is accepted) | 検出（1件） | r4\_01\_point\_ops.test\_every\_record\_after\_the\_point\_is\_named\_once\_in\_the\_same\_order\_nothing\_is\_completed |
| M03c | the operation need not fit the kind of the record | 検出（1件） | r4\_01\_point\_ops.test\_an\_operation\_that\_the\_record\_kind\_does\_not\_allow\_is\_refused |
| M03d | one request may be partly replayed and partly dropped | 検出（2件） | r4\_01\_point\_ops.test\_a\_request\_batch\_is\_dropped\_or\_replayed\_as\_a\_whole |
| M04 | the physical prefix cut at the point is validated (a point inside an old restore batch is refused) | 検出（9件） | r4\_01\_point\_ops.test\_a\_second\_restore\_does\_not\_retire\_a\_record\_twice |
| M05 | the saved market values are replaced by the current ones before the new records are calculated | 検出（6件） | r4\_02\_reapply.test\_a\_changed\_market\_value\_is\_refused\_even\_when\_the\_decision\_would\_be\_the\_same |
| M06 | the state and the transition are copied from the superseded record (apply_transition is not used for them) | 検出（82件） | r4\_01\_point\_ops.test\_a\_new\_genesis\_itself\_is\_accepted\_as\_the\_restore\_point |
| M07a | the current market values are not compared with the saved ones | 検出（7件） | r4\_02\_reapply.test\_a\_changed\_market\_value\_is\_refused\_even\_when\_the\_decision\_would\_be\_the\_same |
| M07b | the current decision is not compared with the saved one | 検出（4件） | r4\_02\_reapply.test\_a\_missing\_other\_or\_changed\_decision\_is\_refused |
| M08a | a harmless close / confirmed difference of next(D) is treated as harmful | 検出（1件） | r4\_02\_reapply.test\_only\_the\_close\_time\_and\_the\_confirmed\_flag\_of\_the\_next\_session\_may\_differ |
| M08b | a harmful open difference of next(D) is ignored | 検出（1件） | r4\_02\_reapply.test\_the\_session\_range\_must\_agree\_with\_the\_saved\_one\_on\_the\_shared\_days |
| M09a | the day of a dropped declaration is not a released day | 検出（6件） | r4\_03\_consume\_replay.test\_a\_dropped\_declaration\_frees\_its\_day |
| M09b | the sessions a dropped restart had passed over are not released days | 検出（3件） | r4\_03\_consume\_replay.test\_a\_dropped\_restart\_without\_a\_later\_apply\_is\_checked\_too |
| M09c | the sessions a re-applied day newly skips are not released days | 等価 | 根拠は§7。released\_daysの再開始項・宣言項と重なり、差が出る入力が無い |
| M09d | a restart that closes a segment without an APPLY (null base) releases nothing | 検出（2件） | r4\_03\_consume\_replay.test\_a\_restart\_with\_a\_null\_base\_is\_checked\_from\_the\_boundary |
| M09e | the released days are checked only when a day is applied again (no later APPLY: not checked) | 検出（7件） | r4\_03\_consume\_replay.test\_a\_dropped\_declaration\_without\_a\_later\_apply\_is\_checked\_too |
| M10 | the current projection of the original history is required (a restore that removes the cause is refused) | 検出（13件） | r4\_02\_reapply.test\_a\_middle\_session\_that\_is\_not\_confirmed\_stops\_the\_restore |
| M11a | the reference of a replayed acknowledgement is not mapped to the new record | 検出（45件） | r4\_02\_reapply.test\_a\_saved\_decision\_chosen\_through\_a\_supplement\_is\_a\_success |
| M11b | a reference to a dropped or retired record is silently kept | 検出（1件） | r4\_03\_consume\_replay.test\_a\_reference\_to\_a\_dropped\_declaration\_is\_refused |
| M12a | a replayed acknowledgement or declaration copies the state from the superseded record | 検出（48件） | r4\_02\_reapply.test\_a\_saved\_decision\_chosen\_through\_a\_supplement\_is\_a\_success |
| M12b | a replayed declaration copies its frontier from the superseded record | 等価 | next(frontier)＝宣言日の検査がfrontierを一意に決める |
| M12c | a replayed restart copies its floor from the superseded record | 検出（1件） | r4\_03\_consume\_replay.test\_a\_replayed\_restart\_has\_a\_new\_floor\_and\_the\_initial\_state |
| M13a | the evidence of the replayed requests is not checked again | 検出（8件） | r4\_04\_evidence\_candidate.test\_a\_request\_that\_is\_not\_replayed\_is\_not\_checked\_again |
| M13b | a request of several commands is cut into single commands | 検出（1件） | r4\_04\_evidence\_candidate.test\_every\_replayed\_request\_group\_is\_checked\_by\_the\_unchanged\_check\_commands |
| M13c | the prefix holds the later APPLY and the later resolutions of the whole candidate | 検出（11件） | r4\_03\_consume\_replay.test\_a\_replayed\_declaration\_follows\_the\_new\_parent\_and\_the\_current\_sessions |
| M13d | a refusal of the unchanged check_commands is swallowed (the two known limits pass) | 検出（5件） | r4\_04\_evidence\_candidate.test\_the\_known\_limit\_a\_declaration\_and\_its\_late\_acknowledgement\_are\_refused\_together |
| M14 | the refusal of a version choice is left out of the prior row set | 検出（1件） | r4\_04\_evidence\_candidate.test\_the\_prior\_rows\_come\_from\_the\_unchanged\_exclusion\_then\_supplement\_then\_version\_choice |
| M15a | validate_history is not called on the candidate | 検出（108件） | r4\_01\_point\_ops.test\_a\_new\_genesis\_itself\_is\_accepted\_as\_the\_restore\_point |
| M15b | the whole-range projection of B-2 is not called (the prior rows stand in for it) | 検出（6件） | r4\_03\_consume\_replay.test\_a\_dropped\_late\_acknowledgement\_lets\_the\_late\_row\_come\_back |
| M15c | evaluate_day is called before the final B-2 projection (a late row for an old skip changes its code) | 検出（4件） | r4\_03\_consume\_replay.test\_a\_late\_row\_for\_a\_day\_an\_apply\_skipped\_is\_refused\_by\_the\_projection\_before\_evaluate\_day |
| M15d | evaluate_day is not called at all (the transition is compared with nothing) | 検出（5件） | r4\_02\_reapply.test\_the\_calculation\_goes\_through\_the\_unchanged\_apply\_transition\_and\_evaluate\_day |
| M16a | the old events and the new records are not compared with the candidate | 等価 | validate\_historyのhash鎖が独立に残る |
| M16b | the effective seqs of the candidate are not compared | 検出（1件） | r4\_04\_evidence\_candidate.test\_a\_candidate\_that\_differs\_from\_what\_was\_built\_is\_refused |
| M16c | the superseded seqs of the candidate are not compared | 検出（1件） | r4\_04\_evidence\_candidate.test\_a\_candidate\_whose\_superseded\_column\_differs\_is\_refused |
| M16d | the candidate_records of a plan are not compared with the tail of its candidate | 等価 | basis全体の再構築比較が後に残る（同じcode） |
| M17a | the no-effect refusal is left out | 検出（6件） | r4\_03\_consume\_replay.test\_a\_replayed\_restart\_frees\_nothing |
| M17b | a plan with a drop is refused too when every re-applied day is the same | 検出（17件） | r4\_01\_point\_ops.test\_a\_point\_in\_the\_middle\_of\_a\_request\_batch\_is\_refused\_but\_its\_last\_record\_is\_a\_valid\_point |
| M17c | the all-same condition is removed and the no-DROP condition stays | 等価 | P-01。DROPなしの拒否と同値 |
| M18 | the request id is compared against the effective chain only | 検出（6件） | r4\_05\_priority\_ids.test\_every\_request\_id\_of\_the\_whole\_physical\_history\_is\_taken |
| M19a | the confirmed plan hash is not compared with the plan's | 検出（2件） | r4\_06\_plan\_confirm.test\_a\_confirmation\_hash\_that\_is\_not\_the\_plans\_is\_refused |
| M19b | the plan hash is not recomputed from the basis | 検出（5件） | r4\_05\_priority\_ids.test\_a\_plan\_that\_is\_wrong\_is\_refused\_before\_the\_inputs\_and\_wrong\_inputs\_before\_stale |
| M19c | the ledger, sessions and series digests of the plan are ignored | 検出（1件） | r4\_06\_plan\_confirm.test\_a\_normal\_change\_of\_the\_inputs\_is\_stale |
| M19d | the whole series (also the rows after the day) is read, not the cut at the day | 検出（4件） | r4\_06\_plan\_confirm.test\_nothing\_after\_the\_cut\_day\_is\_read |
| M19e | a display-only value of the series is mixed into the series input | 検出（3件） | r4\_02\_reapply.test\_a\_changed\_market\_value\_is\_refused\_even\_when\_the\_decision\_would\_be\_the\_same |
| M20a | the same plan against its own candidate is stale | 検出（5件） | r4\_06\_plan\_confirm.test\_a\_confirmation\_against\_its\_own\_candidate\_changes\_nothing\_and\_adds\_nothing |
| M20b | the candidate is taken as the original again (a second RECOVERY_RESTORE would be made) | 検出（5件） | r4\_06\_plan\_confirm.test\_a\_confirmation\_against\_its\_own\_candidate\_changes\_nothing\_and\_adds\_nothing |
| M20c | branch B does not validate the original prefix of the candidate | 検出（1件） | r4\_06\_plan\_confirm.test\_branch\_b\_validates\_the\_original\_prefix\_of\_the\_candidate |
| M20d | the whole basis is not rebuilt and compared | 検出（5件） | r4\_06\_plan\_confirm.test\_every\_item\_is\_bound\_by\_the\_hash\_and\_by\_the\_rebuild |
| M21a | an invalid input history is turned into a stale plan | 検出（1件） | r4\_06\_plan\_confirm.test\_an\_invalid\_history\_is\_its\_own\_error\_not\_a\_stale\_plan |
| M21b | the current inputs are read before the plan itself is checked | 検出（1件） | r4\_05\_priority\_ids.test\_a\_plan\_that\_is\_wrong\_is\_refused\_before\_the\_inputs\_and\_wrong\_inputs\_before\_stale |
| M22a | the basis accessor shares nested references | 検出（2件） | r4\_07\_immut\_types.test\_every\_accessor\_returns\_an\_independent\_copy |
| M22b | the plan_hash accessor shares a container of an unverified plan | 検出（1件） | r4\_07\_immut\_types.test\_unverified\_values\_never\_share\_a\_container |
| M22c | to_dict shares the whole view | 検出（3件） | r4\_05\_priority\_ids.test\_a\_plan\_that\_is\_wrong\_is\_refused\_before\_the\_inputs\_and\_wrong\_inputs\_before\_stale |
| M22d | the representation shows the whole plan (market values, rows) | 検出（1件） | r4\_07\_immut\_types.test\_repr\_summary\_and\_errors\_show\_no\_url\_value\_or\_free\_text |

## 8. 解釈した点

1. **released_daysの新skip項（M09c）は等価と判断**：REAPPLYのbaseが変わるのは再開始をDROPするときだけで、その通過済み日は再開始項が、手前の宣言日は宣言項（DROP）または宣言の再検査（REPLAY）が拾う。項を落としても答えが変わる入力を作れなかったため、項は防御として残し、等価として記録した（反例が見つかれば未検出に改める）。
2. **DECLAREのfrontier（M12b）**：`next(frontier)＝宣言日`の検査がfrontierを宣言日の直前のセッションに固定するので、元のfrontierのコピーとは一致する。等価と判断した。
3. 旧skipへの後発は、多くの場合B-2の全区間投影が`late_observation`で止め、その前に`evaluate_day`を呼ばない。市場値の変更があるときは、B-2投影の前の市場値照合が`restore_market_input_changed`を先に出す（設計の順序どおり）。
4. 無効果の判定：DROPなしでREAPPLYがすべて同一なら`restore_no_effect`。REPLAYだけの計画も無効果。DROPがあれば、市場stateが同一でも成功（GENESIS直後のRESTARTのDROPで固定）。M17cは設計P-01どおり等価。
5. REPLAY記録の`replay_of`は、直前の置換元（元の記録）を指す。さらに前の起源は指さない（二重写像を避ける）。request_id・request_hash・request_basis・ledger_digestは元のまま保つ。
6. 準備と確認で`request_hash`はrequested_atを含まない（時刻だけ違う再準備で同一）。plan_hashはrequested_atとcandidate全体を含むので別になる。
7. NO_CHANGEの結果の`history`は、渡された現在のHistoryそのもの。
8. 設計§7.1の既知の制限は、案aどおり拒否のまま実装した。解消は試みていない。宣言だけを再生する場合にも（遅れた行が台帳にある限り）同じ拒否になる点を、試験で固定した。
9. 開発中の`__pycache__`が1度コミットに入ったが、push前に除いて作り直した。最終コミットのgit管理下に`.pyc`は0件。

## 9. 未実施・留保

- B-4は**候補Historyまで**。保存・ロック・CAS・`HistoryAppendBatch`の一般化・バッチ・耐久性は含まない。**CONSUMEは保留**（必要な日は`restore_requires_consume`で停止し、新しい日のAPPLYを作る経路は無い）。成否不明時の計画の保持と、公開後の照合（ALREADY_PUBLISHED相当）は**S3-C**の範囲。
- 後工程でさらに新規ディレクトリを足すと、旧範囲試験（B-2・B-3・B-4のscope）の見直しが再び必要になる。先回りの許可や共通一覧への再編はしていない。
- 未実施：Windows（実機・環境なし）、ユーザーのPC、物理電源断、`core.autocrlf=true`。Windowsでの新規N＋B-3＋B-2＋S3-A＋B-1＋S2専用4件の実行は未実施で、上の表に含めていない。他者の結果で代用していない。
- B-5（破損診断・prefix採用）、S3-C、CONSUME、PR、マージ、Actions、本番、通知には進んでいない。

## 10. レビュー指摘R-01〜R-03の限定修正（追記。§1〜§9は修正前の記録として変更しない）

作成日：2026-11-02。Rockyが限定修正を承認（レビュー保存SHA 814b861、修正依頼書どおり）。担当：Claude Sonnet 5.5。
ブランチ：`fix/v2-history-restore-plan-s3b4-review-20261102`（開始 5eede119b6729e288d188c67de900bcdfcb27cb1）。**試験対象SHA＝`00ae4b6a69e358fd868ce1f2e9b24b14519b507e`**（修正・試験・r4_sensitivity.py）。本文書だけを足した最終SHAは別に報告する（試験対象とは区別する）。PR・マージ・CONSUME・B-5・S3-Cには進んでいない。

### 10.1 変更したファイル
| ファイル | 内容 |
|---|---|
| `v2_history_restore/records.py` | 再生ACKの`changed_fields`を仮計算から外し、新関数`settle_changes`で最終記録と直接の元記録を比べて確定（比較項目は applied_ref／missing_ref／state_after のみ） |
| `v2_history_restore/build.py` | `_chain_after`（参照hash確定）の直後に`settle_changes`を呼ぶ（1行＋import） |
| `v2_history_restore/values.py` | `_display`内の行検査を`change_ok`として取り出し（動作は同じ）、`series_item_ok`を追加 |
| `v2_history_restore/confirm.py` | `_form_ok`にchanges各行・series_inputs各項目・opsのfrom_seq下限・restore_pointのseq下限を追加。`_plan_basis`（段階1）で`_reapply_olds`を呼び、REAPPLYが指す記録の取得をstale/現在入力より前へ |
| `tests/v2_history_restore/test_r4_10_review_fixes.py` | 新規21件（R-01 5、R-02 8、R-03 8） |
| `tests/v2_history_restore/r4_sensitivity.py` | 4件の等価判断を訂正、M16aの根拠を狭め、修正を1つずつ戻す10変異（F01a〜F02h）を追加 |

既存の144件の試験本体、scope試験、既存パッケージ、フィクスチャ、スキーマ、公開名・引数、依存・設定・workflowは変更していない。新しいランタイムファイルも作っていない。

### 10.2 R-01（差の誤表示）
- 原因：`_replay_resolution`が参照hashを確定する前（`_chain_after`の前）に`applied_ref`／`missing_ref`を旧記録と比べていた。
- 修正：hash確定後の最終記録と元記録を、許された3項目だけで比べる。seq/parent/event_hash等の連結上の差は足していない。
- 結果：Pに残すAPPLYを指すADDED ACK・LATE ACKは`['state_after']`だけになる（修正前は`applied_ref`／`missing_ref`も表示）。REAPPLYされた日を指す参照（`ex_ack_between`）は`['applied_ref','state_after']`のまま表示される。
- 候補Historyは変わらない：3ケースの候補digestが修正前（5eede11で同じ入力を実行）と修正後で完全一致（applied_ref `79fec801…`、missing_ref `eda9b04e…`、写像あり `cfa1d1e3…`）。独立ビルダ（oracle）の記録とも一致。changesが正しくなるため`plan_hash`は変わる（変わるのは誤表示が消えた2ケース。写像ありは変わらない）。

### 10.3 R-02（検査順序）
- 原因：changes／series_inputsはlistかどうかだけを見ており、REAPPLYのfrom_seq抽出（`_reapply_olds`）は現在履歴・sessions・台帳の検査の後だった。
- 修正：plan自身の形（changes行の鍵・op列挙・厳密整数・非負・日付・bool/None・変更項目名、series_inputs項目の鍵・日付・行、opsとrestore_pointのseq下限、REAPPLYが指す記録）を段階1で検査し、失敗は`history_plan_mismatch`/`plan`に固定。確認Aと再確認Bで共通。正しいplan＋不正入力では従来の入力固有エラー（`sessions_invalid`、`record_id_invalid`）のまま。JSON深さ・コピー・表示の防護は変更していない。
- 結果：レビューの再現10観測（changes 3形×A/B、負のfrom_seq×A/B）はすべて`history_plan_mismatch`。生の`KeyError`／`IndexError`／`TypeError`は出ない（`CoreError`のみを許す試験ヘルパで確認）。

### 10.4 R-03（等価判断の訂正）
- **旧§7の「等価」とした4件（M09c／M12b／M16d／M17c）の判断は誤りだった。** 現在のカレンダー（注入sessions）が元の履歴作成時から変わる入力を考えていなかった。旧144件がこれらを検出したとは数え直さない（47eb7c5の実行では未検出のまま「等価」と記録した）。
- 設計§10/P-01の「DROPなしなら必ずsame=true」という説明も誤りで、撤回する。実装の条件「DROPなし、かつ全REAPPLYがsame=true」は変更していない。DROPなしを一律に拒否する変更もしていない。
- 4反例を新回帰に固定（合成入力。実取引所のカレンダー変更の主張ではない）：
  - M09c：現在sessionsに新しいD1とD1の有効decisionを足し、D3をREAPPLY・RESTARTをDROP → `restore_requires_consume`（変異では`late_observation`）。
  - M12b：宣言D1・D2、現在sessionsからD1を除き、D1 DROP・D2 REPLAY → READY、新frontier＝D0（変異では`history_invalid/declare_frontier`）。確認A・BもCONFIRMED_IN_MEMORY→NO_CHANGE。
  - M16d：`candidate_records=[{}]`＋hash付け直し＋`sessions=None` → `history_plan_mismatch`（変異では`sessions_invalid`）。
  - M17c：現在sessionsにD1を足し（decisionなし）、D3をREAPPLYのみ → READY、same=false、changed_fields＝`['input_hash','skipped_sessions']`、確認A＝CONFIRMED_IN_MEMORY・B＝NO_CHANGE（変異では`restore_no_effect`）。

### 10.5 実行結果（試験対象 00ae4b6、core.autocrlf=falseの別クリーンクローン、作業ツリー差分0、Linux 6.18）
| 区分 | Python | core 197 | 保存170 | S2 113 | S3-A 176 | B-1 230 | B-2 173 | B-3 109 | B-4 165 |
|---|---|---|---|---|---|---|---|---|---|
| unshare -rn＋プロセス内socket禁止 | 3.10.20 | OK | OK | OK(skip 4) | OK | OK | OK | OK | OK |
| 同上 | 3.11.18 | OK | OK | OK(skip 4) | OK | OK | OK | OK | OK |
| 同上 | 3.12.3 | OK | OK | OK(skip 4) | OK | OK | OK | OK | OK |
| 同上 | 3.13.18 | OK | OK | OK(skip 4) | OK | OK | OK | OK | OK |
| プロセス内socket禁止のみ | 3.13.18 | OK | OK | OK(skip 4) | OK | OK | OK | OK | OK |

`-B -W error::ResourceWarning`、5構成×8スイート＝40実行でfailures=0、errors=0、終了コード0。既存7スイートは1168件（1164合格＋Windows専用4 skip）で件数・結果とも変化なし。B-4は旧144件が無変更のまま全合格し、新規21件を加えて165件。Linux合計は1168＋165＝1333（Windows専用4 skip）。
**実Windows・ユーザーPC・物理電源断・autocrlf=trueは実行していない（未実施）。** Windowsで比較する場合の期待値は836＋新規21＝857件（レビューのWindows 836件は修正前の標準試験）。
レビュー付属の再現スクリプトを読み取り専用で、クリーンクローン（Python 3.12.3）に対し`--expect-fixed --mutations`で実行：**10観測すべて解消（unresolved 0）**、終了コード0。4つの単一変異（M09c／M12b／M16d／M17c）は元の正常動作と区別できた（DISTINGUISHED）。

### 10.6 欠陥注入（修正後の全件再実行）
修正後のクリーンクローンで`r4_sensitivity.py --control`を**全件**実行した（旧61変異＋修正を戻す10変異＋対照）。
- 対照（欠陥なし）は全合格。
- 旧61変異：**検出60、等価1（M16a）、未検出0、準備失敗0**。M09c／M12b／M16d／M17cは新しい`test_r4_10_review_fixes.py`が検出する（IDは旧と同じ。旧144件が検出したのではない）。
- 修正を1つずつ戻す10変異（F01a／F01b／F02a〜F02h）：**10件すべて検出**。R-01は`test_kept_applied_ref_is_not_listed`ほか、R-02は`test_negative_or_wrong_from_seq_of_an_op`（F02a）、`test_bad_changes_rows_with_missing_sessions`／`test_other_bad_changes_rows`（F02b）、`test_bad_series_inputs_with_missing_sessions`（F02c・F02h）、`test_a_negative_restore_point_is_the_plans_own_error`（F02e）ほかが検出。
- 合計：対照を除く71変異中、検出70・等価1。
- M16aの根拠は「生成器を変えない単一変異に対し、独立ガード（validate_history）が残る」へ狭めた。**M16aを非等価と主張も、等価と証明もしていない**（分離する入力は見つからなかった、という記録に留める）。

### 10.7 留保・未実施
- 案a（DECLARE＋後のLATE ACK、ROW_REMOVED＋後のCHANGED ACKの同時再生拒否）、CONSUME保留、候補Historyまで、B-1〜B-3のランタイム固定は変更していない。
- B-5・S3-C・保存・バッチ・耐久性・公開後の照合は未着手。PR・マージ・Actions・本番反映・送信なし。
- 旧§7の「等価（argued）」の表記は修正前の記録として残してあり、正しい扱いは本§10.4・§10.6による。
