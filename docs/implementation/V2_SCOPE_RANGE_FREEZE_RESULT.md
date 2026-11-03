# V2 範囲試験の固定 限定実装 結果

作成日：2026-11-03（日本時間）。担当：Claude Sonnet 5.5、effort high（`get_session`の`session_context.model`＝claude-sonnet-5-5[1m]、`last_served_model`＝claude-sonnet-5-5、`effort_level`＝high で確認）。
状態：**実装・自己検証まで。レビュー待ち。** PR・マージ・Actions・本番・通知、CONSUME、S3-Cへは進んでいない。ランタイムは1文字も変えていない。

## 1. 固定入力・SHA

| 用途 | 値 |
|---|---|
| 実装開始点 | b626c98af5f01bc94e7b41d86aadde9663695eb9（fix/v2-history-adopt-s3b5b-review-20261103） |
| 試験対象（最後のコード・試験） | **584b406ad8707dab1ccf1c77e209f870ade234f4**（feat/v2-scope-range-freeze-20261103） |
| 保存最終 | 本結果文書だけを足した次のコミット（結果文書内には自身のSHAを書けないため、push報告に記す） |
| 設計・依頼の資料コミット | 08072cc47aa12340ed947d40f02ca8741a4060d6（docs/v2-scope-range-freeze-20261103） |
| 3つのblob | 設計 390804c378af28e6849edfe6660d1e1dac871c0b、依頼書 7805db612beeb931194de836338ad15a87d81168、試行差分 8ceb7c32fcaa6ed97d09d71f50b19a8bbe9c4736（SHA-256 c7ea001f9e4294d2cd1bed91c7550e3aa55e117db804b9ea1aea45961ffe88b0） |
| B-5b受領 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b |
| 連鎖の指摘 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |

採用：RockyさんがD-1〜D-4を推奨どおり一組で採用し、この限定実装を指示した（コーディネーター経由、2026-11-03）。実装ブランチはb626c98から新規に作った。

## 2. 変えたもの

b626c98→584b406の差分は9ファイル（M 5、A 4）。ランタイム・機能試験・ヘルパー・設定・研究・STATUS等の差分は0。

| ファイル | 内容 |
|---|---|
| tests/v2_history_ops/test_b17_scope.py | 固定（END＝b328844） |
| tests/v2_history_restart/test_r3_07_scope.py | 固定（END＝d82a5ce） |
| tests/v2_history_restore/test_r4_09_scope.py | 固定（END＝ac21980。B17_\*／R307_\*の6定数も受領時の値へ） |
| tests/v2_history_diagnose/test_d5_08_scope.py | 固定（END＝c8ba08f。PINNEDも受領時の値へ） |
| tests/v2_history_adopt/test_a5_08_scope.py | 固定（END＝b626c98。FilesChanged・git・current_textの置換だけ） |
| tests/v2_scope_chain/sc_helpers.py、test_sc_01_freeze.py、test_sc_02_chain.py、test_sc_03_scope.py | 新規（__init__.pyなし） |
| docs/implementation/V2_SCOPE_RANGE_FREEZE_RESULT.md | 本結果文書（別コミット） |

### 2.1 固定の作り方

使い捨ての変換スクリプト（共有フォルダの freeze_transform.py）で、各ENDの`git show END:path`からFilesChangedと固定定数のASTの範囲を取り、現在のファイルの同じ要素と入れ替えた。入れ替えた本文には設計§5.2の5種だけを適用した。

1. コードとしての文字列トークン"HEAD"→END（tokenizeでSTRINGトークンが"HEAD"ちょうどのものだけ。固定文字列の中の文字は変えない）
2. `git hash-object path`→`git rev-parse END:path`
3. `open(os.path.join(ROOT, …), encoding="utf-8")`→`io.StringIO(git_show_at_end(…))`
4. `os.listdir(v2_history)`→`git ls-tree --name-only END v2_history/`
5. setUpでENDが無ければskip

加えたのは`END = "…"`、`import io`、`git_show_at_end`の3つだけ。a5_08は今がENDの時点の文字なので置換だけ（FilesChanged、`git`、`current_text`）。

### 2.2 試行の差分（設計§7）との違い

変更される行の集合（追加・削除の各行）は、試行の差分と**完全に一致**した（行の内容の差0）。違うのは**空行1行ずつ（5本とも）**だけで、`git_show_at_end`と`class FilesChanged`の間を2行空けた（PEP 8）。試行は1行だった。そのため追加が225→228行（−593は同じ）。ほかの違いはない。

### 2.3 置換の行（ENDの時点との差・全文）

ENDの時点のFilesChanged・固定定数と、584b406のそれの差は次の91行（削除40＋追加51）だけである。この表は`test_sc_01_freeze`のPINNED_REPLACEMENTSに静的なリテラルで固定してある。b626c98→584b406の差分全文（1357行）は共有フォルダの FREEZE_FIVE_FILES_vs_b626c98.diff（SHA-256 074d6fc8249806f7df9e15f6371180f5ee5839da1945f0c0e616acc04886739a）に置いた。

#### tests/v2_history_ops/test_b17_scope.py（削除 4 行・追加 6 行）

```diff
-         out = self.git("diff", "--name-status", START, "HEAD")
-         out = self.git("diff", "-U0", START, "HEAD", "--", "v2_recovery/commands.py")
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "main.py", "requirements.txt", ".github", "research",
+         if probe.returncode == 0:
+             probe = self.git("cat-file", "-e", END + "^{commit}")
+         out = self.git("diff", "--name-status", START, END)
+         out = self.git("diff", "-U0", START, END, "--", "v2_recovery/commands.py")
+         out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_ops")
+         out = self.git("diff", "--name-only", START, END, "--", "main.py", "requirements.txt", ".github", "research",
```

#### tests/v2_history_restart/test_r3_07_scope.py（削除 4 行・追加 6 行）

```diff
-         out = self.git("diff", "--name-status", START, "HEAD")
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart")
-         out = self.git("diff", "-U0", START, "HEAD", "--", "tests/v2_history_ops/test_b17_scope.py")
+         if probe.returncode == 0:
+             probe = self.git("cat-file", "-e", END + "^{commit}")
+         out = self.git("diff", "--name-status", START, END)
+         out = self.git("diff", "--name-only", START, END, "--", "v2_core", "v2_persistence", "v2_recovery",
+         out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_restart")
+         out = self.git("diff", "-U0", START, END, "--", "tests/v2_history_ops/test_b17_scope.py")
```

#### tests/v2_history_restore/test_r4_09_scope.py（削除 10 行・追加 12 行）

```diff
-         out = self.git("diff", "--name-status", START, "HEAD")
-                 self.assertNotEqual(self.git("hash-object", path).stdout.strip(), blob)     # the one corrected file
-             here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_history_restart", "tests/v2_history_restart",
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore")
-         out = self.git("diff", "-U0", START, "HEAD", "--", path)
-             with open(os.path.join(ROOT, path), encoding="utf-8") as f:
-         with open(os.path.join(ROOT, SCOPE_TESTS[1]), encoding="utf-8") as f:
-         out = self.git("diff", "-U0", START, "HEAD", "--", SCOPE_TESTS[1])
+         if probe.returncode == 0:
+             probe = self.git("cat-file", "-e", END + "^{commit}")
+         out = self.git("diff", "--name-status", START, END)
+                 self.assertNotEqual(self.git("rev-parse", END + ":" + path).stdout.strip(), blob)     # the one corrected file
+             here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)
+         out = self.git("diff", "--name-only", START, END, "--", "v2_history_restart", "tests/v2_history_restart",
+         out = self.git("diff", "--name-only", START, END, "--", "v2_core", "v2_persistence", "v2_recovery",
+         out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_restore")
+         out = self.git("diff", "-U0", START, END, "--", path)
+             with io.StringIO(git_show_at_end(path)) as f:
+         with io.StringIO(git_show_at_end(SCOPE_TESTS[1])) as f:
+         out = self.git("diff", "-U0", START, END, "--", SCOPE_TESTS[1])
```

#### tests/v2_history_diagnose/test_d5_08_scope.py（削除 11 行・追加 13 行）

```diff
-         out = self.git("diff", "--name-status", START, "HEAD")
-         out = self.git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_diagnose",
-         out = self.git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC)
-             here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
-             here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
-         out = self.git("diff", "-U0", START, "HEAD", "--", path)
-             with open(os.path.join(ROOT, path), encoding="utf-8") as f:
-         out = self.git("diff", "-U0", START, "HEAD", "--", path)
-         with open(os.path.join(ROOT, path), encoding="utf-8") as f:
-         with open(os.path.join(ROOT, SCOPE_TESTS[2]), encoding="utf-8") as f:
+         if probe.returncode == 0:
+             probe = self.git("cat-file", "-e", END + "^{commit}")
+         out = self.git("diff", "--name-status", START, END)
+         out = self.git("diff", "--name-only", START, END, "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)
+         out = self.git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_diagnose",
+         out = self.git("diff", "--name-only", START, END, "--", "docs", ":(exclude)%s" % RESULT_DOC)
+             here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)
+             here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)
+         out = self.git("diff", "-U0", START, END, "--", path)
+             with io.StringIO(git_show_at_end(path)) as f:
+         out = self.git("diff", "-U0", START, END, "--", path)
+         with io.StringIO(git_show_at_end(path)) as f:
+         with io.StringIO(git_show_at_end(SCOPE_TESTS[2])) as f:
```

#### tests/v2_history_adopt/test_a5_08_scope.py（削除 11 行・追加 14 行）

```diff
-         out = git("diff", "--name-status", START, "HEAD")
-         out = git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS)
-             out = git("diff", "--name-only", START, "HEAD", "--", root, *[":(exclude)%s" % p for p in kept])
-         out = git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_adopt",
-         out = git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC)
-             here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
-             out = git("diff", "--name-only", START, "HEAD", "--", "docs/implementation/" + name)
-         out = git("diff", "-U0", START, "HEAD", "--", path)
-         out = git("diff", "-U0", START, "HEAD", "--", path)
-         names = sorted(f for f in os.listdir(os.path.join(ROOT, "v2_history")) if f.endswith(".py"))
-     with open(os.path.join(ROOT, path), encoding="utf-8") as f:
+         if probe.returncode == 0:
+             probe = git("cat-file", "-e", END + "^{commit}")
+         out = git("diff", "--name-status", START, END)
+         out = git("diff", "--name-only", START, END, "--", *UNCHANGED_ROOTS)
+             out = git("diff", "--name-only", START, END, "--", root, *[":(exclude)%s" % p for p in kept])
+         out = git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_adopt",
+         out = git("diff", "--name-only", START, END, "--", "docs", ":(exclude)%s" % RESULT_DOC)
+             here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)
+             out = git("diff", "--name-only", START, END, "--", "docs/implementation/" + name)
+         out = git("diff", "-U0", START, END, "--", path)
+         out = git("diff", "-U0", START, END, "--", path)
+         names = sorted(os.path.basename(p) for p in git("ls-tree", "--name-only", END, "v2_history/").stdout.split()
+                        if p.endswith(".py"))
+     with io.StringIO(git_show_at_end(path)) as f:
```

## 3. 新しい試験（tests/v2_scope_chain/、31件）

START＝b626c98、`END = None`、`REV = END or "HEAD"`（test_sc_03_scope.py。ENDを固定するのはこの1行だけ）。gitとASTの読取りだけで、作業ツリーを読まず、前の段階の差分を書き写さない。

| 受入 | 試験 |
|---|---|
| F-02 範囲の値 | test_sc_01_freeze.FrozenRanges.test_the_ranges_are_the_accepted_ones（5本のSTART/END、2つのヘルパーのFIXED_START、隙間のなさ） |
| F-03 受領時の文字 | …test_the_frozen_part_differs_from_the_end_of_its_range_only_in_the_pinned_lines（`git show END:path`から読み、91行のPINNED_REPLACEMENTSと照合）、…test_the_frozen_part_reads_the_end_from_git |
| F-04 置換 | …test_the_frozen_part_reads_nothing_from_the_working_tree_and_has_no_code_head（コードの"HEAD"・open・hash-object・listdir・walk等が0、固定文字列内の"HEAD"はENDの時点と同数残る、r3_07で`START, "HEAD"`を確認） |
| F-05 固定しない部分 | …test_the_part_that_is_not_frozen_is_the_text_of_the_code_start、…test_only_end_import_io_and_git_show_at_end_are_added、…test_tests_asserts_and_skips_are_those_of_the_end_of_the_range（test関数名・assert呼出し・skipTest 1がENDと同じ） |
| F-06 固定の効果 | §5（結果文書に手順と結果を記す。新しい試験の中では作らない） |
| F-07 範囲の鎖 | test_sc_02_chain.Chain（実際の鎖、順序、開いた範囲は最後の1本だけ）、ChainJudge 11件（START重複、隙間、先頭欠落、ENDがSTARTの祖先でない、STARTがENDの祖先でない、開いた範囲2つ、開いた範囲が最後でない、END欠落、ENDがtipの祖先でない、鎖に届かない輪、始まりが無い） |
| F-08 自分の範囲 | test_sc_03_scope.FilesChanged（Mが5本ちょうど、Aは許可パスだけ、他はblob単位で同じ、各ランタイム・docs・tests・設定の差分0） |
| F-09 skip | §6 |
| F-10 範囲監査 | test_sc_03_scope.SideEffects（import、open・時計・乱数・環境・ネットワーク・書込み・walk等が0、gitは読取りサブコマンド6種だけ、プロセスはヘルパーのgit 1か所、__init__.pyなし） |

範囲の鎖の試験は、tests/配下の`test_*.py`でトップレベルのSTARTとclass FilesChangedを持つものを自動で探す（今は6本）。START/ENDはASTで読み、importしない。r3_07・r4_09の`R.FIXED_START`は、同じ版のヘルパーファイルから読む。

## 4. 結果（Linux 6.18、`unshare -n -r`下、別クリーンクローン・core.autocrlf=false、試験対象584b406）

各版を別のクリーンクローン（完全な履歴）で`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`。版：3.10.20（uvの単体）、3.11.18、3.12.3、3.13.18。4版とも全スイートrc＝0、失敗0、error0。

| スイート | 件数 | 結果（4版共通） |
|---|---|---|
| v2_core | 197 | OK |
| v2_persistence | 170 | OK |
| v2_persistence_local（S2） | 113 | OK、skip 4（Windows専用） |
| v2_recovery（S3-A） | 176 | OK |
| v2_history（B-1） | 230 | OK |
| v2_history_ops（B-2） | 173 | OK（b17を含む） |
| v2_history_restart（B-3） | 109 | OK（r3_07を含む） |
| v2_history_restore（B-4） | 165 | OK（r4_09を含む） |
| v2_history_diagnose（B-5a） | 131 | OK（d5_08を含む） |
| v2_history_adopt（B-5b） | 170 | OK（a5_08を含む） |
| **既存計（F-01）** | **1634** | **1630合格＋Windows専用4 skip（開始点と同数）** |
| **v2_scope_chain（新規）** | **31** | OK、skip 0 |
| 合計 | 1665 | 1661合格＋4 skip |

5本のtest関数の数は変えていないので、既存の件数は開始点と同じである。**Windowsは未実施**（Windows機が無い）。他者・ユーザーPCの結果で代用していない。ネットワーク遮断は`unshare -n -r`と試験内のsocket禁止を併用した。

## 5. F-06：次の段階の模擬（2026-11-03、Python 3.13.18）

設計§7と同じ変更（v2_history/values.py、v2_history_restore/points.py、v2_history_adopt/build.pyへのコメント1行ずつ、新規v2_history_next/__init__.py、tests/v2_history_next/の試験1本、結果文書1本）を、使い捨ての別クローンで1コミットにして、範囲試験5本だけを実行した（手順は共有フォルダの simulate_next_stage.sh）。

| 範囲試験 | b626c98＋模擬（固定前） | 584b406＋模擬（固定後） |
|---|---|---|
| b17 | 失敗2 | OK（10件） |
| r3_07 | 失敗2 | OK（11件） |
| r4_09 | 失敗2 | OK（18件） |
| d5_08 | 失敗2 | OK（20件） |
| a5_08 | 失敗3 | OK（12件） |

固定前は計11件失敗、固定後は0件で、設計§7と同じ。実際の次の段階では、これに「test_sc_03_scopeのEND＝None→SHAの1行」と、静的な検査の必要箇所が加わる。模擬では静的な検査に触れる変更はしていない。

## 6. F-09：履歴の無いツリー（`git archive`）

`git archive 584b406`の展開先（.gitなし）で実行した。FilesChangedと鎖の試験は**失敗にならずskip**になる。

| 範囲試験 | 件数 | skip |
|---|---|---|
| b17 | 10 | 3 |
| r3_07 | 11 | 3 |
| r4_09 | 18 | 5 |
| d5_08 | 20 | 8 |
| a5_08 | 12 | 10 |
| 既存5本のFilesChanged計 | | **29**（B-5b再レビュー003b6dc §3の29件と同数） |
| v2_scope_chain | 31 | 30（PathJudgementの1件だけ実行） |

## 7. 限定欠陥注入（584b406を直接壊した使い捨てのコミット、共有フォルダの mutate_runner.py）

依頼書§5の10項目（6は2点）と、追加の7点を1件ずつ壊し、tests/v2_scope_chain/を実行した（Python 3.13）。検出された試験名は一覧の先頭のものを示す。準備失敗0・未検出0・等価0。

| # | 壊し方 | 結果 | 検出した主な試験 |
|---|---|---|---|
| 1 | b17のENDを1つ前のコミットにする | 検出 | FrozenRanges.test_the_ranges_are_the_accepted_ones ほか鎖の試験 |
| 2 | b17のFilesChangedに後の段階の許可（v2_history_adopt/）を1行残す | 検出 | …only_in_the_pinned_lines |
| 3 | r3_07の固定文字列の中の"HEAD"もENDに置換 | 検出 | …only_in_the_pinned_lines、…no_code_head |
| 4 | d5_08のFilesChangedにopenを1か所残す | 検出 | …only_in_the_pinned_lines、…no_code_head |
| 5 | 固定しない部分（b17のKIND_CONSTANTS）を変える | 検出 | …is_the_text_of_the_code_start |
| 6a | r4_09のB17_ADDEDの1行を違う値にする | 検出 | …only_in_the_pinned_lines |
| 6b | d5_08のPINNEDの1行を違う値にする | 検出 | …only_in_the_pinned_lines |
| 7 | 鎖の判定器で隙間（到達数）の検査を省く | 検出 | ChainJudge.test_a_range_that_the_chain_does_not_reach_is_rejected |
| 8 | 判定器で`END = None`が2つあっても通す | 検出 | ChainJudge.test_two_open_ranges_are_rejected ほか |
| 9 | test_sc_03のM集合の検査を緩め、6本目（README.md）を変える | 検出 | test_everything_else_is_blob_identical_to_the_code_start（別の試験が6本目を捕える） |
| 10 | 新しい試験が作業ツリーを読む（REVでなくopen） | 検出 | SideEffects.test_only_allowed_imports_and_no_io_clock_random_or_network |
| x11 | a5_08の差分をHEADに戻す | 検出 | …only_in_the_pinned_lines ほか |
| x12 | r4_09にhash-objectを残す | 検出 | 同上 |
| x13 | b17の`END = None` | 検出 | …accepted_ones、鎖の試験 |
| x14 | r3_07のSTARTを別の値にする | 検出 | …accepted_ones、…text_of_the_code_start |
| x15 | a5_08のsetUpがEND欠落でskipしない | 検出 | …only_in_the_pinned_lines |
| x16 | b17のtest関数1本を名前変更で外す | 検出 | …are_those_of_the_end_of_the_range |
| x17 | d5_08のgit_show_at_endが作業ツリーを読む | 検出 | …reads_the_end_from_git |

欠陥注入の途中で、7（隙間の検査）が最初の試験では検出されなかった（隙間のある表は先に「始まりが複数」で拒否され、到達数の検査に届かない）。そのため、輪（始まりを持たない2本の範囲）を足した表で到達数の検査だけが拒否する試験を1件加えた（ChainJudge.test_a_range_that_the_chain_does_not_reach_is_rejected）。6a/6bの初回は準備失敗（置換対象の文字が無く変更なし）だったので、対象の文字を直して再実行した。上の表は最終の584b406に対する全件の再実行の結果。

## 8. 保護参照

依頼書§7の65参照に資料ブランチdocs/v2-scope-range-freeze-20261103（08072cc）を加えた**66参照**を、`git ls-remote`の完全SHAで照合した。**開始時（実装ブランチを作る前）**は66件とも一致。push後の照合は、結果文書が別コミットのため本書には書かず、スレッドの報告に記す。

## 9. 未実施・制限

- Windows（実機）と、ユーザーPCでの実行は未実施。
- 固定した5本は、END以後の変更を見ない。最新の開いた範囲試験（test_sc_03_scope）と鎖の試験が覆う。固定した試験の合格を、今のHEADの監査と書かない。
- `git archive`などの履歴の無いツリーでは、FilesChanged（29件）と鎖の試験（30件）はskipになる。完全なクローンで件数を比べること。
- 鎖の先頭コミット（adfdf765）があるのに途中のコミットが無い履歴（履歴を書き換えた場合など）では、鎖の試験はENDの祖先判定（`git merge-base --is-ancestor`の失敗）を拒否として扱うので失敗になる設計である。この場合を実際の履歴で作った確認は未実施（判定器の拒否は表を使った試験で確認）。履歴が全く無い場合、または鎖の先頭コミットが無い場合はskip。固定の監査（test_sc_01）は、5本のSTART・ENDのどれかが無いときもskipする。
- b626c98の再レビュー提案P-01（a5_09のfloat）、P-02（NO_CHANGE経路のdiscarded）、CONSUME、S3-Cには触れていない。

## 10. 作業記録

- 開始：2026-11-03T09:58Z。クローンは完全な履歴（shallowでない）。
- 未コミットの`__pycache__`が一度コミットに混入したが、push前に消してamendした（PYTHONDONTWRITEBYTECODE=1、`git add`前に確認）。pushしたコミットに含まれない。
- 共有フォルダ implementation/scope_range_freeze_20261103/ に、変換スクリプト（freeze_transform.py）、欠陥注入ランナー（mutate_runner.py）、模擬の手順（simulate_next_stage.sh）、差分全文を置いた。
- モデル別の利用量は未計測。
