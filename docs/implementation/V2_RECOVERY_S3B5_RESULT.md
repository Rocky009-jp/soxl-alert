# V2 S3-B-5a 破損診断 限定実装 結果記録

作成日：2026-11-02（日本時間）。担当：Claude Sonnet 5.5（実設定の確認は§1）。
状態：**B-5a（破損診断のみ）の限定実装・自己試験まで完了。レビュー待ち。PR・マージ・B-5b・CONSUME・S3-Cには進んでいない。**
B-5aは**書込みなしの診断**である。診断は復旧ではない。`PREFIX_ONLY`は「先頭のcount件が現在の検査器に通る」ことだけを示し、復旧済み・採用済み・正本とは言わない。元バイトの退避・公開・照合はS3-Cの範囲である（§10）。

## 1. 固定入力・モデル・SHA

| 項目 | 値 |
|---|---|
| 採用 | RockyがD-1〜D-5を一組で採用し、B-5a限定実装を承認（スレッドの指示。再レビュー記録は 6a7210c2e278e604b953acf904cf9e796c2ce710 の docs/reviews/V2_RECOVERY_S3B5_V2_REREVIEW_20261102.md、重大・通常の新規指摘なし） |
| モデルの実設定 | セッション情報の確認結果：configured_model＝`claude-sonnet-5-5[1m]`、session_context.model＝`claude-sonnet-5-5[1m]`、last_served_model＝`claude-sonnet-5-5`、effort_level＝`high`。D-5（Sonnet 5.5・high）と一致 |
| 固定した資料 | 資料ブランチ docs/v2-history-s3b5-20261102 の**5c9e1e89c8f9d33689e9bc67e266fa6031507136**（第2版。途中で追従していない） |
| 設計書blob | docs/specs/V2_RECOVERY_S3B5_DIAGNOSIS_ADOPTION_DESIGN_DRAFT.md ＝ f4d4225545627dd5e7df1fc5c5e092a49ccee10f |
| 依頼書blob | docs/tasks/V2_RECOVERY_S3B5_LIMITED_IMPLEMENTATION_REQUEST.md ＝ 2e4bb7e34f9c442450fe11ac179e4f134b97cb29 |
| コード開始点 | ac219801d290ebb59b720f37a086103b6e1251c9（fix/v2-history-restore-plan-s3b4-review-20261102）。資料ブランチからは始めていない |
| 実装ブランチ | feat/v2-history-diagnose-s3b5a-20261102（ac21980から作成。同名は無かった） |
| コミット | 実装＋試験＋scope補正3本 **fac880c40e235a849e36269cee99985a5183f5ae**（コード・試験の最終＝**試験対象SHA**） |
| 保存最終SHA | 本文書だけを加えた次のコミット（コミット後にスレッドで報告。本文書にはSHA自身を書けない） |
| 保護参照 | 依頼書§8の56参照＋資料ブランチ 5c9e1e8＝57参照を、開始後（2026-11-02T07:41:04Z）に`git ls-remote`の完全SHAで照合し、57／57一致。ほかに再レビュー資料 6a7210c（docs/v2-history-s3b5-v2-rereview-20261102）も記録した値と一致。push後の終了時の照合はスレッドで報告 |

読んだもの：CLAUDE.md、設計書、依頼書、初版レビュー（842d44b）の再現スクリプト2本、既存のB-1 validate/values/common、S1 codec/events/recompute、S2 localのstore、B-4の範囲試験、既存のテスト補助（h_helpers、ho_helpers、r4_helpers、p_helpers）。STATUS・MODEL_POLICY・ROADMAPは、依頼が指示する範囲（B-4までの採用を取り直さない）に従い、内容は依頼書・設計書の記述に依拠した。これらは変更していない。

## 2. 作ったもの

新規パッケージ `v2_history_diagnose/`（5ファイル、365行）：`diagnose_history_bytes`、`HistoryDiagnosis`、定数 `VALID`／`PREFIX_ONLY`／`NO_VALID_PREFIX`／`UNREADABLE`。`__all__`は設計どおりの6名。既存パッケージの`__init__.py`への再公開は無い。既存ランタイムは1行も変えていない。

| ファイル | 内容 |
|---|---|
| `diagnose.py` | 引数の型検査（厳密に`bytes`だけ）、段階utf8→json→schema→validate、全体検査、最長prefixの探索（k＝nから1まで上から全探索）。hashlibは生バイトのSHA-256の1か所だけ |
| `failure.py` | `{stage, code, field, rule}`の組立て。PersistenceErrorとCoreErrorはcode/field/rule（CoreErrorのruleはnull）、それ以外の例外は版ごとの`malformed`。識別子は短いASCII（英数字と`_:.-`）だけ通し、それ以外はnull（コードが不正なら`malformed`）。例外文・生の値・連鎖は出さない |
| `describe.py` | claimed（型が正しい宣言値だけ）、verified（版2は`HistoryCheck`、版1は`ValidatedSnapshot`から）、discarded（`{index, kind, seq, d, request_id}`の5キーだけ。市場値・F&G・decision・自由文・resume_afterは出さない） |
| `values.py` | 不変な`HistoryDiagnosis`（10キー、`__slots__`は`_text`と`_view`だけ、読取りはすべて独立した写し、`digest`＝`sha256_text(canonical_json(to_dict()))`、`summary()`／`repr`は固定語・件数・seq・日付・先頭12桁のdigestだけ） |

利用した既存の公開名は設計§12の一覧の範囲だけ（AST試験で確認）。private名、`Chain`／`_Walk`／`_Frozen`、S1のCtx／SnapshotView、B-2のbatch、各ストアは使っていない。戦略式・閾値・市場値は書いていない（検査はすべて既存の`validate_history`／`validate_snapshot`への委譲）。

主な振る舞い：
- 段階1 utf8：strict、BOMは除かない（BOMつきはjson段階でUNREADABLE）。段階2 json：変更しない`decode_history`（重複キー・NaN/Infinity・深さ・巨大整数は既存ruleのまま）。段階3 schema：最上位がdict、`schema_version`がboolでないint（1または2）、`core_sha`一致。ここまでで止まればUNREADABLEでprefixは探さない。
- 段階4：版2は`validate_history`、版1は`validate_snapshot`。通ればVALID。通らず、eventsが空でないlistなら、k＝nから1まで各kでヘッダーを作り直して同じ検査器に渡し、最初に通ったkを採る（PREFIX_ONLY）。通るkが無い、またはeventsが空/非listならNO_VALID_PREFIX。
- failureは全体検査の最初のエラー（prefix探索中のエラーではない）。

## 3. 全差分

開始点ac21980→試験対象fac880c。変更は18ファイル（追加15・変更3）、+2838／−33。

| 区分 | ファイル |
|---|---|
| 新規ランタイム | v2_history_diagnose/{__init__,diagnose,describe,failure,values}.py |
| 新規試験 | tests/v2_history_diagnose/{d5_helpers,d5_sensitivity,test_d5_01〜08}.py（`__init__.py`なし） |
| 変更（限定補正） | tests/v2_history_ops/test_b17_scope.py、tests/v2_history_restart/test_r3_07_scope.py、tests/v2_history_restore/test_r4_09_scope.py |

ランタイム5ファイルと新規試験の全文はブランチ上のファイルを正とする（本文書には載せない）。変更した既存ファイルはscope試験の3本だけで、全差分（`git diff -U1 ac21980 fac880c -- <3本>`）は次のとおり。test関数の増減は無く、旧件数（b17 10件・r3_07 11件・r4_09 18件）は維持している。

```diff
diff --git a/tests/v2_history_ops/test_b17_scope.py b/tests/v2_history_ops/test_b17_scope.py
index ca2df74..c6b0ee1 100644
--- a/tests/v2_history_ops/test_b17_scope.py
+++ b/tests/v2_history_ops/test_b17_scope.py
@@ -185,3 +185,4 @@ class FilesChanged(unittest.TestCase):
                                         "v2_history_restart/", "tests/v2_history_restart/",
-                                        "v2_history_restore/", "tests/v2_history_restore/"))
+                                        "v2_history_restore/", "tests/v2_history_restore/",
+                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))
                        or path in ("v2_recovery/facts.py", "v2_recovery/commands.py",
@@ -189,3 +190,4 @@ class FilesChanged(unittest.TestCase):
                                    "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
-                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))
+                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
+                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
@@ -202,2 +204,3 @@ class FilesChanged(unittest.TestCase):
                              and path != "v2_history_restore/__init__.py"
+                             and path != "v2_history_diagnose/__init__.py"
                              and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)
@@ -218,3 +221,4 @@ class FilesChanged(unittest.TestCase):
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",
-                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore")
+                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",
+                       ":(exclude)tests/v2_history_diagnose")
         self.assertEqual(out.stdout.strip(), "")
diff --git a/tests/v2_history_restart/test_r3_07_scope.py b/tests/v2_history_restart/test_r3_07_scope.py
index d7bf3db..f3eedcc 100644
--- a/tests/v2_history_restart/test_r3_07_scope.py
+++ b/tests/v2_history_restart/test_r3_07_scope.py
@@ -193,4 +193,6 @@ class FilesChanged(unittest.TestCase):
             allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",
-                                       "v2_history_restore/", "tests/v2_history_restore/")) or path in (
-                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md")
+                                       "v2_history_restore/", "tests/v2_history_restore/",
+                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (
+                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
+                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
@@ -200,3 +202,4 @@ class FilesChanged(unittest.TestCase):
         self.assertEqual({p for p in paths if p.endswith("__init__.py")},
-                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py"})
+                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",
+                          "v2_history_diagnose/__init__.py"})
 
@@ -209,3 +212,3 @@ class FilesChanged(unittest.TestCase):
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",
-                       ":(exclude)tests/v2_history_restore")
+                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")
         self.assertEqual(out.stdout.split(), ["tests/v2_history_ops/test_b17_scope.py"])
@@ -228,11 +231,15 @@ class FilesChanged(unittest.TestCase):
             '                                        "v2_history_restart/", "tests/v2_history_restart/",',
-            '                                        "v2_history_restore/", "tests/v2_history_restore/"))',
+            '                                        "v2_history_restore/", "tests/v2_history_restore/",',
+            '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
             '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",',
             '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
-            '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
+            '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
+            '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
             '            self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"',
             '                             and path != "v2_history_restore/__init__.py"',
+            '                             and path != "v2_history_diagnose/__init__.py"',
             '                             and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)',
             '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",',
-            '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore")'])
+            '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
+            '                       ":(exclude)tests/v2_history_diagnose")'])
 
diff --git a/tests/v2_history_restore/test_r4_09_scope.py b/tests/v2_history_restore/test_r4_09_scope.py
index 28b5446..c5e8508 100644
--- a/tests/v2_history_restore/test_r4_09_scope.py
+++ b/tests/v2_history_restore/test_r4_09_scope.py
@@ -82,8 +82,12 @@ B17_REMOVED = ['                                        "v2_history_restart/", "
 B17_ADDED = ['                                        "v2_history_restart/", "tests/v2_history_restart/",',
- '                                        "v2_history_restore/", "tests/v2_history_restore/"))',
+ '                                        "v2_history_restore/", "tests/v2_history_restore/",',
+ '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
  '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
- '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
+ '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
+ '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
  '                             and path != "v2_history_restore/__init__.py"',
- '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore")']
-B17_HUNKS = ['@@ -185 +185,2', '@@ -188 +189,2', '@@ -199,0 +202', '@@ -216 +219']
+ '                             and path != "v2_history_diagnose/__init__.py"',
+ '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
+ '                       ":(exclude)tests/v2_history_diagnose")']
+B17_HUNKS = ['@@ -185 +185,3', '@@ -188 +190,3', '@@ -199,0 +204,2', '@@ -216 +222,2']
 R307_REMOVED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/")) or path in (',
@@ -96,23 +100,22 @@ R307_REMOVED = ['            allowed = path.startswith(("v2_history_restart/", "
 R307_ADDED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",',
- '                                       "v2_history_restore/", "tests/v2_history_restore/")) or path in (',
- '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
- '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md")',
+ '                                       "v2_history_restore/", "tests/v2_history_restore/",',
+ '                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (',
+ '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
+ '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")',
  '        self.assertEqual({p for p in paths if p.endswith("__init__.py")},',
- '                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py"})',
+ '                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",',
+ '                          "v2_history_diagnose/__init__.py"})',
  '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",',
- '                       ":(exclude)tests/v2_history_restore")',
+ '                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")',
  '            \'                                        "v2_history_restart/", "tests/v2_history_restart/",\',',
- '            \'                                        "v2_history_restore/", "tests/v2_history_restore/"))\',',
+ '            \'                                        "v2_history_restore/", "tests/v2_history_restore/",\',',
+ '            \'                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
  '            \'                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",\',',
- '            \'                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))\',',
+ '            \'                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
+ '            \'                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
  '            \'                             and path != "v2_history_restore/__init__.py"\',',
- '            \'                       ":(exclude)tests/v2_history_restart", '
- '":(exclude)tests/v2_history_restore")\'])']
-R307_HUNKS = ['@@ -193,2 +193,3',
- '@@ -199 +200,2',
- '@@ -207 +209,2',
- '@@ -225 +228,2',
- '@@ -227 +231,2',
- '@@ -228,0 +234',
- '@@ -231 +237']
+ '            \'                             and path != "v2_history_diagnose/__init__.py"\',',
+ '            \'                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",\',',
+ '            \'                       ":(exclude)tests/v2_history_diagnose")\'])']
+R307_HUNKS = ['@@ -193,2 +193,5', '@@ -199 +202,3', '@@ -207 +212,2', '@@ -225 +231,3', '@@ -227 +235,3', '@@ -228,0 +239,2', '@@ -231 +243,2']
 
@@ -349,3 +352,5 @@ class FilesChanged(unittest.TestCase):
                 continue
-            self.assertTrue(allowed_path(path), "unexpected change: %s %s" % (status, path))
+            new_b5a = path.startswith(("v2_history_diagnose/", "tests/v2_history_diagnose/")) or path == \
+                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"
+            self.assertTrue(allowed_path(path) or new_b5a, "unexpected change: %s %s" % (status, path))
             self.assertEqual(status, "A", path)                                      # new files only
@@ -353,3 +358,4 @@ class FilesChanged(unittest.TestCase):
         self.assertIn("v2_history_restore/__init__.py", paths)
-        self.assertEqual({p for p in paths if p.endswith("__init__.py")}, {"v2_history_restore/__init__.py"})
+        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
+                         {"v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py"})
 
@@ -379,3 +385,4 @@ class FilesChanged(unittest.TestCase):
         self.assertEqual(out.stdout.strip(), "")
-        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore")
+        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore",
+                       ":(exclude)tests/v2_history_diagnose")
         self.assertEqual(sorted(out.stdout.split()), sorted(SCOPE_TESTS))
```

補正は依頼§3.1〜§3.3の範囲だけである。r4_09のモジュール定数`B17_*`／`R307_*`は、d82a5ce→fac880cの差分に合わせて静的リテラルに更新した（動的生成にしていない）。b17の許可リスト補正では、`__init__.py`の例外は`v2_history_diagnose/__init__.py`の単一パスだけを加えている。

## 4. 受入とテスト名の対応（新規131件）

| ID | 試験（tests/v2_history_diagnose/） | 件数 |
|---|---|---|
| D5-01 回帰・変更境界 | 既存8スイートの実行（§5）、test_d5_08_scope.py の `FilesChanged`（ac21980起点の新B-5a scope） | 既存1333＋scope内8 |
| D5-02 引数 | test_d5_01_args_stages.py `ArgumentType`（str・bytearray・memoryview・None・int・bytes派生はdiagnosis_invalid/data/type、空bytesはUNREADABLE json） | 3 |
| D5-03 utf8段階 | 同 `Utf8Stage`（非UTF-8、途中で切れた多バイト、BOMはjson段階で失敗） | 3 |
| D5-04 json段階 | 同 `JsonStage`（切れたJSON、重複キー、NaN/Infinity、1e999、深さ超過、巨大整数、救出しないこと。いずれも検査器のspyが0回） | 7 |
| D5-05 schema段階 | 同 `SchemaStage`（list・文字列、版0・3・true・"2"、core_sha違い、ヘッダーを作り直せば通る入力でもprefixを探さない） | 7 |
| D5-06 VALID | test_d5_02_valid.py `ValidHistories`（新規v2、移行済み2種、例R、例R-b、再開始、例R13、indent付き、canonical_textは状態に影響しない） | 10 |
| D5-14 claimedとverified | 同 `ClaimedValues`、`StateAndDocumentDigests`、test_d5_04_v1.py `ValidSnapshot`（版1列） | 3＋4＋4 |
| D5-07 ヘッダーだけの違い | test_d5_03_prefix.py `HeaderOnly`（head_hash・head_seq・current_state・余分なキー・欠けたキー。count＝n、discarded.count＝0、spyでk＝nのみ） | 4 |
| D5-08 後半の破損 | 同 `LaterDamage`（末尾はn−1、中ほどのAPPLY書換えはその位置、後ろも捨てる側、spyで下を試さない） | 4 |
| D5-09 バッチと非単調 | 同 `Batches`（復元バッチ途中、requestバッチ途中、途中のkの拒否をspyで確認、非単調でkの10〜8が拒否・11と7が通る入力で最長を採る） | 7 |
| D5-10 NO_VALID_PREFIXと移行 | 同 `NoValidPrefix`（GENESIS破損、空list、非list、eventsキー無し、全件破損、非dict要素）、`MigrationExamples`（example_m、example_m_empty_world） | 6＋3 |
| D5-11 v1 | test_d5_04_v1.py `DamagedSnapshot`、`VersionsAreNotMixed`（正常・末尾改ざん・ヘッダーだけ・GENESIS破損、版ごとの検査器、migrated＝null） | 6＋3 |
| D5-12 failureと例外 | test_d5_05_failure_discarded.py `FailureShape`、`StubbedCheckers`（検査器の差替えで全例外集合・PersistenceError・CoreError・自由文の識別子・prefix検査中の例外） | 4＋7 |
| D5-13 discarded | 同 `Discarded`、`JsonSafety`（5キー、未知の種別は"?"、型不正はnull、秘匿、summaryは件数・種別・最初と最後のd） | 5＋1 |
| D5-15 不変性・決定性・秘匿 | test_d5_06_value_privacy.py `Immutability`、`Determinism`、`PrintedForms`、`StoresRefuseTheValue`（旧MemoryStore／LocalFileStoreはplan_typeで拒否、作業ディレクトリに何も作らない） | 9＋3＋3＋3 |
| D5-16 費用の実測 | test_d5_07_cost.py `Cost`（約260件のAPPLY、結果は§7） | 2 |
| D5-17 範囲監査 | test_d5_08_scope.py `Runtime`（AST）、`PathJudgement`、`FilesChanged` | 20 |

D5-16の試験は約75〜100秒かかる（合成履歴の構築が主）。閾値・打ち切りは入れていない。

## 5. 実行結果

実行：core.autocrlf=falseの別クリーンクローン（試験対象fac880c）4か所、`unshare -n -r`（ネットワーク名前空間なし）、`<python> -B -W error::ResourceWarning -m unittest discover`、PYTHONDONTWRITEBYTECODE=1、Linux 6.18。試験内でもプロセス内のsocket禁止が有効。

| スイート | 件数 | Py3.10.20 | Py3.11.18 | Py3.12.3 | Py3.13.18 |
|---|---|---|---|---|---|
| v2_core | 197 | OK | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK | OK |
| v2_persistence_local（S2） | 113 | OK（skip 4） | OK（skip 4） | OK（skip 4） | OK（skip 4） |
| v2_recovery（S3-A） | 176 | OK | OK | OK | OK |
| v2_history（B-1） | 230 | OK | OK | OK | OK |
| v2_history_ops（B-2） | 173 | OK | OK | OK | OK |
| v2_history_restart（B-3） | 109 | OK | OK | OK | OK |
| v2_history_restore（B-4） | 165 | OK | OK | OK | OK |
| **v2_history_diagnose（新規）** | **131** | OK | OK | OK | OK |

- 既存8スイートは各版で1333件（1329合格＋Windows専用4 skip）。失敗0・error0。終了コードはすべて0（36実行）。
- 新規は各版で131件、失敗0・error0・skip0。Linuxの合計は1464件（新規131＋既存1333）。
- 旧scope3本（b17 10、r3_07 11、r4_09 18）はスイート内で合格。実装中の個別実行でも39件合格（初版レビュー担当の報告と同数）。
- 「既存試験が全部無編集」とは言えない（scope3本を補正した）。それ以外の既存試験・fixture・基準データ・ランタイムは差分0（新B-5a scopeがblobで確認）。
- 実Windows、ユーザーPC、物理電源断、core.autocrlf=trueは**未実施**（他者の結果で代用していない）。Windowsで実行する場合の合計は新規131＋857。

## 6. 具体的な診断例（合成データ。入力はテスト補助のビルダーで作り、`encode_history`のバイト、または壊した後の正規化JSON）

| 入力の作り方 | status | verified | discarded | failure | schema |
|---|---|---|---|---|---|
| 新規v2（GENESIS＋APPLY 6件）のencode_historyバイト | VALID | count=7, head_seq=6, migrated=False | — | — | 2 |
| 例R（3回の復元、23件） | VALID | count=23, head_seq=22 | — | — | 2 |
| 例Rの字下げJSON | VALID（canonical_text=false） | 同上 | — | — | 2 |
| 新規v2のhead_hashだけ0×64 | PREFIX_ONLY | count=7, head_seq=6 | from=7, count=0 | validate/history_invalid/history/head | 2 |
| 新規v2の末尾のevent_hashを0×64 | PREFIX_ONLY | count=6, head_seq=5 | from=6, count=1 | …/event_hash | 2 |
| 新規v2の3番目のAPPLYのdを書換え（hash据置） | PREFIX_ONLY | count=3, head_seq=2 | from=3, count=4 | …/event_hash | 2 |
| 例R1（11件）をindex10で切る（復元バッチ途中） | PREFIX_ONLY | count=7, head_seq=6 | from=7, count=3 | …/restore_incomplete | 2 |
| 2コマンドrequestの1つ目で切る | PREFIX_ONLY | count=3, head_seq=2 | from=3, count=1 | …/batch | 2 |
| 例R1＋APPLY（index11）の末尾hash破損（非単調：k=10〜8は拒否、11と7は通る） | PREFIX_ONLY | count=11, head_seq=10 | from=11, count=1 | …/event_hash | 2 |
| example_m（MIGRATION=seq7、n=8）のMIGRATIONのevent_hashを0×64 | PREFIX_ONLY | count=2, head_seq=1, migrated=False | from=2, count=6（seq2〜7） | …/event_hash（k=7〜3はorigin、k=8はevent_hash、k=2で通過） | 2 |
| example_m_empty_world移行後（n=4）のMIGRATIONのevent_hashを0×64 | PREFIX_ONLY | count=3, head_seq=2, migrated=False | from=3, count=1（SCHEMA_MIGRATION） | …/event_hash | 2 |
| GENESISのevent_hashを0×64 | NO_VALID_PREFIX | — | from=0, count=7 | …/event_hash | 2 |
| eventsが空のlist | NO_VALID_PREFIX | — | from=0, count=0, items=[] | …/events | 2 |
| eventsが文字列 | NO_VALID_PREFIX | — | null | …/events | 2 |
| v1（S2のencode_snapshot、GENESIS＋APPLY 4件） | VALID | count=5, head_seq=4, migrated=null | — | — | 1 |
| v1 末尾event_hash改ざん | PREFIX_ONLY | count=4, head_seq=3 | from=4, count=1 | validate/snapshot_invalid/snapshot/event_hash | 1 |
| v1 head_hashだけ違う | PREFIX_ONLY | count=5, head_seq=4 | from=5, count=0 | …/head_hash | 1 |
| v1 GENESIS破損 | NO_VALID_PREFIX | — | from=0, count=5 | …/event_hash | 1 |
| BOM＋正常JSON | UNREADABLE | — | — | json/history_invalid/history/json | null |
| 途中で切れたJSON | UNREADABLE | — | — | json/history_invalid/history/json | null |
| 非UTF-8 | UNREADABLE | — | — | utf8/unreadable/data/utf8 | null |
| core_sha違い | UNREADABLE | — | — | schema/unsupported_schema/core_sha/null | null |
| schema_version=3 | UNREADABLE | — | — | schema/unsupported_schema/schema_version/null | null |

example_mとexample_m_empty_worldの値は、設計§11と依頼D5-10に書かれたレビュー担当の実行結果と一致した（B-1を変更して合わせていない）。`migrated=False`のprefixが通ったことは、移行の不在や採用可能の根拠にならない。

## 7. D5-16 費用の実測

合成した261件（GENESIS＋APPLY 260、519,622バイト）での値。Linux 6.18、4版の各実行（unshare下、同時に4版を走らせたため時間は粗い値）。

| ケース | 所要時間（4版の範囲） |
|---|---|
| 正常（VALID） | 0.12〜0.14秒 |
| 末尾を壊した通常位置（PREFIX_ONLY、count＝260） | 0.16〜0.21秒 |
| ヘッダーだけの違い | 0.14〜0.19秒 |
| **GENESIS直後を壊した最悪位置（count＝1、検査260回）** | **2.4〜3.3秒** |
| GENESISを壊した場合（NO_VALID_PREFIX） | 2.3〜3.2秒 |

これはAPPLY中心の指定した合成履歴での値であり、全入力の最悪時間の証明ではない（複数のRECOVERY_RESTOREを含む履歴は各復元前の鎖ビューも検査される）。閾値・打ち切り・高速化は入れていない。

## 8. 限定欠陥注入（依頼§6の17項目、53変異）

スクリプト：tests/v2_history_diagnose/d5_sensitivity.py（unittestではない。実際のツリーは変更せず、一時コピーに1件ずつ適用して新規の挙動試験test_d5_01〜06を実行）。コントロール（無変更）は109件合格（Py3.10.20・3.13.18）。test_d5_07（実測）とtest_d5_08（Git scope）は変異では走らせない。結果は**検出53／等価0／未検出0／準備失敗0**で、Py3.10.20とPy3.13.18のクリーンクローン（fac880c）で完全に一致した。

| 項目 | 変異 | 検出した主な試験 |
|---|---|---|
| 1 UTF-8 | M01a replace、M01b utf-8-sig、M01c ignore | Utf8Stage |
| 2 寛容な読込み | M02a 重複キー許容、M02b NaN許容 | JsonStage |
| 3 版・core_sha | M03a core_shaを見ない、M03b 未知の版を通す | SchemaStage |
| 4 検査器の取り違え | M04a 全体で入替え、M04b prefixで入替え | ValidHistories、ValidSnapshot、DamagedSnapshot ほか |
| 5 探索の向き | M05a 下から（k＝1）、M05b 下から最初の失敗まで、M05c 二分探索、M05d 独自のバッチ境界判定 | HeaderOnly、LaterDamage、Batches |
| 6 ヘッダー | M06a 版2で元のヘッダー、M06b 版1で元のヘッダー | HeaderOnly、LaterDamage、DamagedSnapshot |
| 7 k＝n | M07a k＝nを試さない、M07b k＝nで通ればVALID | HeaderOnly ほか |
| 8 全体検査 | M08a 全体検査を省く | ValidHistories ほか |
| 9 例外 | M09a prefixの例外を捕まえない、M09b 例外文をfailureへ、M09c 識別子の無害化を外す | StubbedCheckers |
| 10 failure | M10a 最後に試したkのエラー、M10b stageを誤る | FailureShape、MigrationExamples |
| 11 canonical_text | M11a falseで状態を変える | ValidHistories、ValidSnapshot |
| 12 discarded | M12a request_id、M12b d、M12c kind、M12d seq、M12e resume_after、M12f 非dict要素 | Discarded |
| 13 verified | M13a〜h（版2のdocument/state取り違え、count、版1のcount・migrated・document_digest・state_digest・boundary） | ValidHistories、ValidSnapshot、DamagedSnapshot |
| 14 参照・保持 | M14a to_dict、M14b 読取り、M14c コンストラクタ、M14d __dict__、M14e 変更可能、M14f 別スロットに保持 | Immutability |
| 15 型・内容の例外 | M15a bytearray、M15b bytes派生、M15c 内容で例外 | ArgumentType、Utf8Stage |
| 16 非決定的 | M16a digestにid、M16b raw_sizeに時計、M16c operationに文字（実質は固定値の変更） | Determinism ほか |
| 17 委譲のspy | M17a k＜nは最後のevent_hashだけで判定（検査器を呼ばない）、M17b 検査器の拒否のうちバッチ系を無視、M17c prefixに別の検査器 | Batches、MigrationExamples、LaterDamage |

分類：B-5a自身の判断（OWN）50、委譲spy（SPY）3（M17a〜c）、独立防護のみ（GUARD）0。変異はすべて診断パッケージに入れ、その応答を試験が見ている（検査器の独立防護だけで値が変わらない変異は作っていない）。冗長な検査を除いても値が変わらない変異は見つからず、等価と分類したものは無い。したがって根拠のないspyは足していない。

初回の53変異は3.13で52検出・1未検出（旧M14f：値を持たず、モジュール変数に入力を保持する変異）だった。値が入力を保持することの検査としては不適切だったため、変異を「値の別スロットに保持」に改め、`gc.get_referents`で値の参照先がstrとdictだけであることを見る試験を1件足した（test_d5_06）。その後の試験対象fac880cは上記のとおり全件検出。

## 9. 解釈した点

- 段階3で止まったときの`schema_version`（診断値）はnullにした（設計は「段階3に届かなければnull」）。版が読めても、その版の検査には使っていないため。宣言値`claimed.schema_version`には読めた値を入れる。
- `claimed`は最上位がdictなら段階3の失敗でも作る（最上位がlistや文字列のときはnull）。
- 識別子の無害化：例外のcode/field/ruleが短いASCII（英数字・`_:.-`）でなければfield/ruleはnull、codeが不正なら版ごとの`malformed`とした（設計の「固定識別子だけ」の実装）。既存の検査器が出すcode/field/ruleはすべて通る。
- `HistoryDiagnosis`の直接構築は、10キーと`operation`・`status`の値だけを検査する（信頼済み内部入力。`from_dict`は作っていない）。
- k＝nで通ってもPREFIX_ONLY（全体は通らなかったため）。ヘッダーの違いだけの場合、discardedは`{from_index: n, count: 0, items: []}`。
- 版1のファイルで版2専用の種別（RESTART_UNKNOWN等）が出た場合、その位置の`kind`は"?"（版1の既知の種別はGENESISとAPPLYだけ）。GENESIS＋APPLYだけのファイルは、版1の記録と版2の記録が同じなので、`schema_version`の宣言だけが検査器の選択を決める（試験で確認）。
- 巨大整数は、整数桁数の上限を持つPythonでは`decode_history`が既存のruleで拒否し、持たない古いPythonではschema段階で止まる。いずれもUNREADABLEで、試験は`decode_history`の実際の応答を基準にしている。
- D5-16の試験は構築に時間がかかるため、他の試験と同じスイートに入れた。性能の閾値はない。

## 10. 未実施・留保

- B-5b（RECOVERY_PREFIX_ADOPTION記録、検査器・chain・pointsの変更、採用の計画・確認）、CONSUME、S3-Cは**未着手**。
- 診断は書込みなしで復旧ではない。元バイトの退避・公開・照合、保守ゲート、解錠、CASはS3-C。台帳・sessions・seriesによる照合もしない。
- 実Windows、ユーザーPC、物理電源断、core.autocrlf=trueは未実施。
- 本番接続・通知・Actions・PR・マージ・STATUS/ROADMAP更新はしていない。
- モデル別の利用量は未計測。
