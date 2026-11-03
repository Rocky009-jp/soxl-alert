# V2 C-2 公開値と照合 限定実装 結果

作成日：2026-11-03（日本時間）。状態：**実装・試験済み、レビュー待ち。未受領。**
対象：docs/tasks/V2_HISTORY_PUBLISH_C2_LIMITED_IMPLEMENTATION_REQUEST.md（第2版）と docs/specs/V2_HISTORY_PUBLISH_C2_DESIGN_DRAFT.md（第2版）。
運用方針は日足のみ（早朝に米国の確定日足で通知、夜の寄付きで手動購入）。分足・NBBOは前提にしていない。

## 1. 実施条件

- **担当モデル/effort**：セッション情報（get_session）の確認結果は、設定モデル claude-sonnet-5-5[1m]、最後の応答を実行したモデル claude-sonnet-5-5、effort_level high。依頼書の推奨（Sonnet 5.5・high）と一致。
- **着手の根拠**：Rockyさんは「レビューをOpus・highに依頼して、終了後は推奨のとおり作業してください」と指示した（2026-11-03 14:31Z、コーディネーター経由）。Opusレビュー（a6e783e）の推奨は「依頼書の限定改訂のあとに実装」で、第2版（081637e）が作られ、D-1〜D-8（第2版）はすべて採用推奨だった。この指示を、D-1〜D-8（第2版）を推奨どおり採用しC-2を限定実装する指示として扱った。C-3・C-4は含まない。
- **固定資料**：

| 用途 | 完全SHA / blob |
|---|---|
| 実装開始点（C-1の保存最終） | de6549acb4ecea759cc771300fd0bef59dd5456a |
| 設計・依頼書（第2版）の資料コミット（docs/v2-history-publish-c2-revision-20261103） | 081637e95160a23aab5ea0fc3a2edd01976abba4 |
| 設計 blob（docs/specs/V2_HISTORY_PUBLISH_C2_DESIGN_DRAFT.md） | 3517beba75087a1d139646abdcf94f62bf064eb7 |
| 依頼書 blob | 894a91d433873669828b401ddc0434c5f32cf965 |
| 試行の差分 blob（docs/specs/V2_HISTORY_PUBLISH_C2_TRIAL_20261103.diff、初版から不変） | d2be5de04158365e746fa60f8fd8bb9deb417c3e（SHA-256 7bfd3a80534c0e7fc3f2618db1894bd05883aed00c29449cc886cc219554b0ba） |
| 設計・依頼書の初版 / レビュー | 9dd64b8eb07ad35dd23c011ed2dbb1196307f542 / a6e783e57c1de5dd92e6b43cfc416a1d79a672eb |
| C-1の受領レビュー | b473db46ad3dbf3ad76fa76f50c49b03b558936d |

- **ブランチ**：feat/v2-history-publish-c2-20261103（de6549aから）。
- **SHA**：開始 de6549acb4ecea759cc771300fd0bef59dd5456a、ランタイム 52782ac642b78a41fe862ab2cc1d86185584a336、**試験対象 29e26592f3c0e79d8d33fd3296e4e8c32817907f**、保存最終は結果文書を足した最後のコミット（本文書自身のSHAは本文書に書けないので、報告とメモリに記す）。試験対象から保存最終までの差分は本文書1本だけ。
- **環境**：Linux。Python 3.10.20（uvの単体）、3.11.18、3.12.3、3.13.18。Windowsとユーザーのパソコンは**未実施**（他者の結果で代用していない）。依存・設定・workflow・main.pyは変更なし。

## 2. 変更の一覧

| 対象 | 内容 |
|---|---|
| v2_history_publish/（新規6ファイル、計519行） | `__init__.py` 23行、`build.py` 129行、`check.py` 192行、`errors.py` 28行、`read.py` 41行、`values.py` 106行。全文は試験対象コミット（29e2659）のそのパス、ランタイムだけのコミットは 52782ac。ファイルの分け方は設計§2.3のとおり（理由の追加なし） |
| tests/v2_history_publish/（新規） | `c2_helpers.py`、`test_c2_01_values_bytes.py`（22件）、`test_c2_02_build_append.py`（17）、`test_c2_03_build_whole.py`（21）、`test_c2_04_cas.py`（28）、`test_c2_05_reconcile.py`（17）、`test_c2_06_no_leak.py`（6）、`test_c2_07_standins.py`（9）、`test_c2_09_scope.py`（30）。計150件。`__init__.py`は作っていない |
| tests/v2_history_consume/test_c1_09_scope.py | 2行（下記の差分全文） |
| docs/implementation/V2_HISTORY_PUBLISH_C2_RESULT.md | 本文書 |

既存のパッケージ、試験、変異、ヘルパー、範囲試験（上の2行以外）、設定、docs（本文書以外）は blob 単位で同じ（C2-17）。PR・マージ・Actions・送信・本番・C-3・C-4には進んでいない。

### test_c1_09_scope.py の差分全文（`git diff de6549a 29e2659`、SHA-256 5b2c5fbdf940414f6cc386ee359f40bc4f8ae1d0b6f016a3f4e37c1295793c5d）

```diff
diff --git a/tests/v2_history_consume/test_c1_09_scope.py b/tests/v2_history_consume/test_c1_09_scope.py
index 325a167..b7ecf13 100644
--- a/tests/v2_history_consume/test_c1_09_scope.py
+++ b/tests/v2_history_consume/test_c1_09_scope.py
@@ -14,7 +14,7 @@ sys.path.insert(0, os.path.join(HERE, "..", "v2_scope_chain"))
 import sc_helpers as C  # noqa: E402  (read-only Git helpers of the range tests)
 
 START = "bfbde7a7854bf91a77fb58737c24b19c6507453a"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "de6549acb4ecea759cc771300fd0bef59dd5456a"   # accepted (review b473db4); frozen when C-2 began
 REV = END or "HEAD"
 
 RUNTIME = ("v2_history/restore.py", "v2_history_restore/__init__.py", "v2_history_restore/build.py",
@@ -271,7 +271,7 @@ class Chain(Base):
         self.assertGreaterEqual(len(rows), 7)
 
     def test_the_range_values_of_this_file_are_those_read_from_the_text(self):
-        tree = ast.parse(C.show(REV, NEW_DIR + "test_c1_09_scope.py"))
+        tree = ast.parse(C.show("HEAD", NEW_DIR + "test_c1_09_scope.py"))   # HEAD: the frozen END is read as written
         self.assertEqual(C.read_constant(tree, "START", NEW_DIR.rstrip("/"), REV), (True, START))
         self.assertEqual(C.read_constant(tree, "END", NEW_DIR.rstrip("/"), REV), (True, END))
         self.assertIn("FilesChanged", C.top_level(tree))
```

blob は b7ecf13（試行と同じ）。ENDだけでは自己読直しが失敗する（設計§6.2）。

## 3. 試行の差分（設計§7）との違いと理由

試行の差分は写さず、設計と依頼書の規則から書いた。主な違い：

| 項目 | 試行 | 本実装 | 理由 |
|---|---|---|---|
| 整数の欄（R-03） | candidate_head_seq等は`is_int`だけ。負の値で`reconcile_publication`が`IndexError` | 形の検査で、candidate_head_seq・expected.head_seq・raw_sizeは0以上のint（boolを除く）。candidate_head_seqはAPPENDで`expected.head_seq + records数`、CREATE/REPLACEで`candidate_history.events`の件数−1に一致。recordsのseqは続き番号 | 依頼書§3・C2-14。両関数が同じ形の検査を共有 |
| 引数の誤用（P-03） | `source_v1`の誤用を今の比較の後で見る | 公開値の検査→引数（current型・source_v1）→今→候補の順 | 依頼書§3・C2-11 |
| PUBLISHED_THEN_EXTENDED（R-02） | 記録のhashの一致を前置きしてから物理prefixのdigest | 物理prefixのdigestだけ | 欠陥注入15が、食い違う公開値で区別できるように |
| 形の検査 | request_idはNoneでなければ妥当であればよい | 元ごとに厳密（計画の元は request_id・plan_hash とも必須、DAILY・GENESISは両方None、日は DAILY だけ） | 設計§4.2の表のとおり |
| 内部の呼び名 | Reconciliationも`_make` | Reconciliationは`_of`。`_make`はHistoryPublicationだけで、build.pyだけが呼ぶ | C2-10「`_make`の呼出しがbuild.pyだけ」を静的に確かめやすくするため |
| 読めない今 | `PersistenceError`だけ捕捉 | `CoreError`を捕捉（照合は中身の問題を例外にしない） | C2-12 |
| 移行のv1のバイト | 型の誤りは`history_invalid`／type | `snapshot_invalid`／type（S2と同じ系統） | C2-08 |
| `prefix_digest` | build.py（check.pyが取り込む） | read.py | hashlib（read.pyだけ）に近い読み書きの部品を1か所に |
| 採用のbasis | `isinstance(plan, AdoptionPlan)`の防御 | 確認が成功した後なので`plan.basis`を直接読む（読むキーは request_id・raw_sha256・raw_size だけ） | C2-15 |
| 範囲試験 | 仮の1件 | 正式な範囲試験（30件） | 依頼書§6 |

## 4. 受入条件と試験の対応

| ID | 試験（ファイル：クラス） |
|---|---|
| C2-01 回帰 | 下の§5。既存12スイートの1780件を完全なクローンで維持（test_c1_09の2行補正を含む。件数同じ） |
| C2-02 値 | test_c2_01：PublicationValue（11件。不変性、コピー、14キー、operation、sourceとmode、hash、committed、from_dictなし、summary・repr） |
| C2-03 DAILY | test_c2_02：Daily |
| C2-04 RESOLUTION | test_c2_02：Resolution |
| C2-05 RESTART | test_c2_02：Restart |
| C2-06 RESTORE | test_c2_02：Restore（C-1のCONSUMEを含む例：DROP→CONSUME D3→REAPPLY。recordsは復元記録と作られた2件のAPPLY） |
| C2-07 GENESIS | test_c2_03：Genesis |
| C2-08 MIGRATION | test_c2_03：Migration |
| C2-09 ADOPTION | test_c2_03：Adoption（bodyにdiscarded・diagnosisを名に含むキーが無い、値も入っていない） |
| C2-10 P-01 | test_c2_03：Verified（C-1レビュー§4.5の履歴：検査器は受け付け、計画は`restore_consume_not_released`で拒否。(a)basisを書き換えてhashを付け直した計画、(b)その履歴のRestoreConfirmResult、のどちらも公開値にならない。7つのbuilder、Historyを受け取る関数なし。(c)特性の試験：`_make`で作った値は`check_publication`を通る）。静的：test_c2_09：Constructors |
| C2-11 CAS | test_c2_04：Success、StaleCurrent、UnreadableCurrent、ArgumentMisuse、WrongPublication |
| C2-12 照合 | test_c2_05：FourOutcomes、PhysicalPrefix（candidate_head_hashは今と同じ位置の記録と同じだがcandidate_digestが違う公開値でCONFLICT）、Boundaries |
| C2-13 バイト | test_c2_01：Bytes |
| C2-14 例外の漏れ | test_c2_06：Leak（試験が数える下限：公開値の型の変更1,500通り超、整数の境界400通り超、現在・v1のバイトの改変1,500通り超、現在のJSONの欄の型の変更600通り超、深い入れ子・巨大整数。いずれも想定外の例外0） |
| C2-15 P-02 | test_c2_09：P02、test_c2_03：Adoption |
| C2-16 範囲の値 | test_c2_09：Chain、FilesChanged.test_the_one_modified_test_is_the_two_pinned_lines |
| C2-17 自分の範囲 | test_c2_09：FilesChanged |
| C2-18 範囲監査 | test_c2_09：RuntimeAudit、SideEffects、Constructors |
| C2-19 次の段階の模擬 | §7（手順と結果） |
| 補助 | test_c2_07：Layers（実物の確認の関数の下では到達できない層を、build.pyの名前空間の確認の関数を代役に差し替えて試す。欠陥注入2・3・4・5の検出用） |

期待値は、既存の確認の関数が返した候補、`check_append_batch`、履歴の検査器、hashlib、試験側で作った履歴（独立のレコードビルダーHB）から作り、本実装の出力を写していない。

## 5. 全スイートの結果

各版を別のクリーンクローン（ローカルの実装リポジトリからの完全な履歴、shallowでない、core.autocrlf=false、`git checkout 29e2659`）で、`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`（新規は`test_c2_*.py`、C-1は`test_c1_*.py`）。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---|---|---|---|---|
| コア v2_core | 197 | OK | OK | OK | OK |
| 保存 v2_persistence | 170 | OK | OK | OK | OK |
| S2 v2_persistence_local | 113（skip 4、Windows専用） | OK | OK | OK | OK |
| S3-A v2_recovery | 176 | OK | OK | OK | OK |
| B-1 v2_history | 230 | OK | OK | OK | OK |
| B-2 v2_history_ops | 173 | OK | OK | OK | OK |
| B-3 v2_history_restart | 109 | OK | OK | OK | OK |
| B-4 v2_history_restore | 165 | OK | OK | OK | OK |
| B-5a v2_history_diagnose | 131 | OK | OK | OK | OK |
| B-5b v2_history_adopt | 170 | OK | OK | OK | OK |
| 範囲の鎖 v2_scope_chain | 34 | OK | OK | OK | OK |
| C-1 v2_history_consume | 112 | OK | OK | OK | OK |
| **C-2 v2_history_publish（新規）** | **150** | OK | OK | OK | OK |
| 合計 | **1930**（既存1780＋新規150） | | | | |

4版とも13スイートすべて rc＝0、失敗0、error0、skipは S2 の4件（Windows専用）だけ。新規スイートは`unshare -n`（通信遮断）の下でも3.12で150件合格。新規Nは150、Windowsで走らせる件数は新規150＋1304（C-1 112＋範囲34＋B-5b 170＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4）＝**新規N＋1304＝1454**。
`git archive`のツリー（.gitなし）でのskip（3.12）：S2 4、B-2 3、B-3 3、B-4 5、B-5a 8、B-5b 10、範囲の鎖 33、C-1 22（実行107件）、**C-2 28**（実行150件）。そのほかは0。

## 6. 限定欠陥注入（39変異）

試験対象と同じ木（tree ea8e8f133bc2f6c5ddc39089485b003dae4d732e）の`git archive`の複製に1か所ずつ変更を入れ、3.12で`tests/v2_history_publish`の`test_c2_01`〜`07`を`-f`で実行した（範囲の変異16・17は使い捨てのworktreeでコミットして`test_c2_09`、18は次段階の模擬）。スクリプトは共有フォルダの implementation/c2_publish_20261103/mutate.py。設計§5の18項目に、2つの項目の分割（2a/2b、7a/7b）と追加20件を加えた。

**検出39、等価0、未検出0、準備失敗0。**

| ID | 設計の項目 | 内容 | 分類 | 最初に失敗した試験 |
|---|---|---|---|---|
| M01 | 1 | build: adoption makes a publication from NO_CHANGE too (status check removed) | 検出 | test_c2_03_build_whole.test_a_plan_that_is_confirmed_against_its_own_candidate_is_refused_as_no_change |
| M02a | 2 | build: DAILY makes a publication from a status that is not PREPARED (status test removed, batch test kept) | 検出 | test_c2_07_standins.test_a_day_that_is_not_prepared_gives_no_publication_even_with_a_batch |
| M02b | 2 | build: DAILY makes a publication from a day that is not PREPARED (both tests removed) | 検出 | test_c2_02_build_append.test_a_day_that_is_not_prepared_is_refused_as_not_prepared |
| M03 | 3 | build: APPEND does not check that the candidate extends the history | 検出 | test_c2_07_standins.test_a_candidate_that_does_not_extend_the_history_is_not_published |
| M04 | 4 | build: RESOLUTION does not compare the candidate with the history of the confirm result | 検出 | test_c2_07_standins.test_the_candidate_of_a_resolution_must_be_the_one_of_its_batch |
| M05 | 5 | build: the expected identity of an adoption is copied from the plan basis | 検出 | test_c2_07_standins.test_the_adopted_bytes_must_be_the_bytes_the_plan_names |
| M06 | 6 | build: the body of an adoption gets a discarded part | 検出 | FAIL: test_the_body_has_the_fourteen_keys_the_operation_and_ |
| M07a | 7 | build: a publish_history that takes a History is added | 検出 | test_c2_03_build_whole.test_there_are_seven_builders_and_none_takes_a_history_a_result_or_a_dict |
| M07b | 7 | values: HistoryPublication gets a from_dict | 検出 | test_c2_01_values_bytes.test_committed_is_always_false_and_there_is_no_from_dict |
| M08 | 8 | check: the publication hash is not checked | 検出 | test_c2_04_cas.test_a_value_whose_hash_does_not_fit_is_refused |
| M09 | 9 | check: APPEND compares the head without head_hash | 検出 | test_c2_04_cas.test_an_append_that_differs_by_one_part_of_the_expected_head_is_stale |
| M10 | 10 | check: REPLACE does not compare the raw identity | 検出 | test_c2_04_cas.test_a_replace_needs_the_raw_identity_of_the_bytes_it_names |
| M11 | 11 | check: CREATE accepts a current file | 検出 | test_c2_04_cas.test_a_create_needs_that_nothing_is_there |
| M12 | 12 | check: MIGRATION does not check the v1 bytes | 検出 | FAIL: test_the_identity_is_that_of_the_received_bytes_even_w |
| M13 | 13 | check: the candidate digest is not compared | 検出 | test_c2_04_cas.test_the_candidate_must_be_what_the_fields_say |
| M14 | 14 | reconcile: an unreadable current is NOT_PUBLISHED | 検出 | test_c2_05_reconcile.test_a_file_that_cannot_be_read_is_a_conflict_not_an_error |
| M15 | 15 | reconcile: PUBLISHED_THEN_EXTENDED by the hash of the last record only | 検出 | FAIL: test_a_publication_whose_head_hash_fits_but_whose_dige |
| M16 | 16 | range test reads the working tree (open) instead of Git | 検出 | test_c2_09_scope.test_only_allowed_imports_and_no_io_clock_random_or_network |
| M17 | 17 | one pinned line of the corrected test_c1_09 is changed | 検出 | test_c2_09_scope.test_the_one_modified_test_is_the_two_pinned_lines |
| M18 | 18 | own range values are read from REV instead of HEAD | 検出（C2-19の模擬） | 次段階の模擬 [C] が失敗 |
| M19 | extra | check: no range for the integer fields (candidate_head_seq may be negative, no relation to the records) | 検出 | test_c2_04_cas.test_the_integer_fields_have_ranges_in_the_form |
| M20 | extra | check: the arguments are looked at after the current bytes are compared | 検出 | test_c2_04_cas.test_a_misuse_is_seen_before_a_current_that_is_stale_absent_or_unreadable |
| M21 | extra | reconcile: a REPLACE reads the current bytes before it looks at the raw identity | 検出 | FAIL: test_a_replace_is_not_published_while_the_named_bytes_ |
| M22 | extra | build: the identity of the v1 bytes is that of the canonical text of the snapshot | 検出 | FAIL: test_the_identity_is_that_of_the_received_bytes_even_w |
| M23 | extra | read: a byte order mark is removed | 検出 | test_c2_01_values_bytes.test_the_read_is_strict |
| M24 | extra | read: a bytearray is accepted as bytes | 検出 | test_c2_01_values_bytes.test_read_takes_bytes_only |
| M25 | extra | values: the summary shows the body | 検出 | test_c2_01_values_bytes.test_summary_and_repr_are_a_whitelist |
| M26 | extra | values: a reconciliation carries one more field | 検出 | test_c2_01_values_bytes.test_a_reconciliation_holds_the_outcome_and_the_hash_only |
| M28 | extra | check: APPEND compares the digest of the history only (no head seq, no head hash) | 検出 | test_c2_04_cas.test_an_append_that_differs_by_one_part_of_the_expected_head_is_stale |
| M29 | extra | build: APPEND takes one record too many (new[n - 1:]) | 検出 | test_c2_01_values_bytes.test_a_reconciliation_holds_the_outcome_and_the_hash_only |
| M30 | extra | build: a day publication does not name the day | 検出 | test_c2_01_values_bytes.test_a_reconciliation_holds_the_outcome_and_the_hash_only |
| M31 | extra | check: the seq of the records is not checked | 検出 | test_c2_04_cas.test_changed_records_are_refused_even_with_the_hash_written_again |
| M32 | extra | reconcile: an APPEND whose current is the expected head is a CONFLICT | 検出 | test_c2_01_values_bytes.test_a_reconciliation_holds_the_outcome_and_the_hash_only |
| M33 | extra | values: committed is True | 検出 | test_c2_01_values_bytes.test_committed_is_always_false_and_there_is_no_from_dict |
| M34 | extra | build: a resolution is published with the plan hash of nothing | 検出 | test_c2_02_build_append.test_the_candidate_is_the_one_of_the_confirmation |
| M35 | extra | check: the v1 misuse for other sources is not refused | 検出 | test_c2_04_cas.test_a_misuse_is_seen_before_a_current_that_is_stale_absent_or_unreadable |
| M36 | extra | check: the type of the current is not refused | 検出 | test_c2_04_cas.test_the_current_must_be_bytes_or_none |
| M37 | extra | check: a bool counts as an integer | 検出 | test_c2_04_cas.test_the_fields_of_a_create_and_a_replace_are_checked |
| M38 | extra | check: the current of a CREATE is compared before the v1 misuse (order of the two checks) | 検出 | test_c2_04_cas.test_a_misuse_is_seen_before_a_current_that_is_stale_absent_or_unreadable |

- 欠陥注入2a・3・4・5は、実物の確認の関数の下ではどの入力でも結果が同じになる防御の重ね（依頼書§5）。**検出は test_c2_07 の代役**（build.pyの名前空間の確認の関数を、実物が返さない結果を返す代役に差し替える。C-1の変異7と同じやり方）による。代役を使わなければ、この4件は等価と書くところだった。2bは、status・batchの両方の防御を外す変異で、通常の試験で検出される。
- 欠陥注入15は、正直な公開値では記録のhashが鎖になっているので物理prefixの判定と同じ結果になる。candidate_head_hashは今と同じ位置の記録と同じで candidate_digest だけが違う公開値（hashを付け直したもの）で区別され、検出された。
- 欠陥注入18は通常の試験を通る。C2-19の模擬（試験対象のSHAをENDにすると、REVから読むと失敗する）で検出された。
- 追加のM19（整数の範囲を外す）は、試行のR-03の再現に当たる。検出された。

## 7. C2-19 次の段階の模擬

使い捨てのworktree（pushしない）で、試験対象のSHA（29e2659）から：[A] そのまま、[B] C-2の範囲試験のENDだけを自分の試験対象のSHAに替える（1行）、[C] [B]に次の段階の仮の開いた範囲試験1本（START＝試験対象のSHA、END=None、`class FilesChanged`を持つ最小のもの、使い捨ての`tests/v2_next_stage/`）を足す。各場合に test_sc_*・test_c1_*・test_c2_* を実行する。スクリプト：共有フォルダ implementation/c2_publish_20261103/next_stage_sim.sh。

| 場合 | 範囲の鎖34 | C-1 112 | C-2 150 |
|---|---|---|---|
| [A] 試験対象のまま | OK | OK | OK |
| [B] ENDだけ固定（開いた範囲0本） | **失敗2**（test_sc_02のChainJudge。「2 chain beginnings」、次の段階では起きない形。test_sc_02は直さない） | OK | OK |
| [C] ENDの固定＋仮の開いた範囲試験 | OK | OK | OK |

保存最終のSHAでの再現はレビューで行う（範囲試験は結果文書を必須にしないので、保存最終でも同じ結果になる想定）。

## 8. 保護参照

依頼書§7の75参照（main、各資料・実装ブランチ、de6549a、a6e783e、9dd64b8を含む）に、第2版の資料ブランチ docs/v2-history-publish-c2-revision-20261103（081637e95160a23aab5ea0fc3a2edd01976abba4）を加えた76参照を、`git ls-remote`の完全SHAで照合した。開始時（2026-11-03 約14:55Z）は76件とも一致。push前後の結果は報告とメモリに記す。pushするのは新しい実装ブランチ feat/v2-history-publish-c2-20261103 だけ。

## 9. 未実施・既知の制限

- **Windows**、ユーザーのパソコン、物理電源断は未実施。autocrlf=trueの環境も未実施。
- C-3（v2ローカル正本）、C-4（保守操作）、PR、マージ、Actions、通知、送信、本番は範囲外。
- 既知の制限（設計§8）：`check_publication`は確認ではない。Pythonでは`_make`や`object.__new__`で公開値の形の値を作れる。試験C2-10(c)がこの性質を特性として固定し、静的監査（Constructors）がbuild.py以外の呼出しを禁じる。C-3は同じプロセスで`publish_*`が返した値だけを受け取り、範囲試験で同じ監査を行うことをC-3の受入条件に引き継ぐ（レビューP-01）。
- C-4への引継ぎ（設計§8）：採用のREPLACEがreplaceの後で中断すると、元バイトはhistory.jsonから消えている。照合に要る公開値は、C-4が退避へ写した元バイトから`publish_adoption`で作り直す。今のバイトでの確認はNO_CHANGE（`publication_refused`／`no_change`）になる。
- 範囲外として残したもの（依頼書§2）：C-1レビューの提案P-02・P-03、B-4§7.1、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02。
- モデル別の利用量は未計測。
