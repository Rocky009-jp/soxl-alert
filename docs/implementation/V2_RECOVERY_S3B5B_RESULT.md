# V2 S3-B-5b 採用（prefix adoption）限定実装 結果記録

作成日：2026-11-03（日本時間）。担当：Claude Sonnet 5.5（実設定は§1）。
状態：**B-5b（診断済みprefixの採用。メモリ内のみ）の限定実装・自己試験まで完了。レビュー待ち。PR・マージ・Actions・本番・通知・CONSUME・S3-Cには進んでいない。**
採用は**メモリ内の計画と候補Historyを作るだけ**である。ファイル・ストア・時計・通信なし。`committed`は常にFalse。候補はまだ正本ではなく、保存・公開・差替えは後工程。

## 1. 固定入力・モデル・SHA

| 項目 | 値 |
|---|---|
| 採用 | RockyがD-1〜D-4を推奨どおり採用し、B-5b限定実装を承認（スレッドのRockyの発言「D-1〜D-4推奨どおり採用し、実装まで進めてください」） |
| モデルの実設定 | get_sessionの結果：configured_model＝`claude-sonnet-5-5[1m]`、session_context.model＝`claude-sonnet-5-5[1m]`、last_served_model＝`claude-sonnet-5-5`、effort_level＝`high`。フォールバックの通知は見ていない |
| 固定した資料 | 資料ブランチ docs/v2-history-s3b5b-20261102 の**5d21c10885a97e8d0cd614444f0da9b11ca322a5**（途中で追従していない） |
| 設計書blob | docs/specs/V2_RECOVERY_S3B5B_PREFIX_ADOPTION_DESIGN_DRAFT.md ＝ b574dc3072aa668b2870bc9b78844665e19b47b0 |
| 依頼書blob | docs/tasks/V2_RECOVERY_S3B5B_LIMITED_IMPLEMENTATION_REQUEST.md ＝ bbf2010bc648637ceb75d212958f1440f3aad07d |
| 試行diff blob | docs/specs/V2_RECOVERY_S3B5B_SCOPE_TRIAL_20261102.diff ＝ 299f508d9b55d769c88806e28d9e5bcc93c95a12（共有フォルダの3写しも同じblobを確認） |
| コード開始点 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6（feat/v2-history-diagnose-s3b5a-20261102）。資料ブランチからは始めていない |
| 実装ブランチ | feat/v2-history-adopt-s3b5b-20261103（c8ba08fから作成。同名は無かった） |
| 試験対象SHA（コード・試験の最終） | **2daab90ffbde881eaa33f6644a31e57dad0c8048**（c8ba08fの直接の子。作業中の仮コミットは1本にまとめ、`__pycache__`は含めていない） |
| 保存最終SHA | 本文書だけを加えた次のコミット（コミット後にスレッドで報告。本文書には自分のSHAを書けない） |
| 保護参照 | 依頼書§8の60参照＋資料ブランチ 5d21c10＝61参照を`git ls-remote`の完全SHAで照合し、**push前に61／61一致**。push後の照合は§9に記す。**開始時の照合は実装の後（push前）に初めて行った**（§10） |

## 2. 作ったもの

**既存ランタイムの変更（6ファイルだけ）**：v2_history/values.py（8番目の種別`RECOVERY_PREFIX_ADOPTION`と12キー）、v2_history/__init__.py（公開名24）、v2_history/view.py（`_Walk.adoption_record`と規則`adoption_evidence`）、v2_history/restore.py（規則`restore_before_adoption`）、v2_history_ops/chain.py（`_REQUEST_KINDS`）、v2_history_restore/points.py（B-4の同じ下限）。全文の差分は§5。

**新規パッケージ `v2_history_adopt/`**（6ファイル、409行）：公開名7（`prepare_prefix_adoption`、`confirm_prefix_adoption`、`AdoptionPlan`、`AdoptionConfirmResult`、`READY`、`CONFIRMED_IN_MEMORY`、`NO_CHANGE`）。依存は設計§5.7の名前だけ、標準ライブラリは`copy`だけ（hashlibなし。生バイトのSHA-256は診断の値）。

| ファイル | 内容 |
|---|---|
| `build.py` | 診断（1回）の結果からの検査（PREFIX_ONLY・schema 2・adopt_count照合・移行の痕跡・IDの重複）、証拠6キー、採用記録12キー、basis21キー、`validate_history`での候補検査 |
| `prepare.py` | 引数の順序検査（data→adopt_count→requested_at→request_id）と診断1回 |
| `confirm.py` | 計画の形・hash→basisの内部整合→dataの型→元の生バイトは作り直して全basisを比較（CONFIRMED_IN_MEMORY）／候補の正規化バイトはNO_CHANGE／他はhistory_plan_stale。改ざんはhistory_plan_mismatch。内部不整合は`history_invalid`／`history`／`adoption_candidate` |
| `values.py`・`errors.py`・`__init__.py` | 不変な値（`to_dict`・`basis`・`history`は独立した写し）、エラーの組立て |

**新規試験 `tests/v2_history_adopt/`**（9ファイル）：`test_a5_02`〜`test_a5_08`の7本、補助`a5_helpers.py`、変異ランナー`a5_sensitivity.py`（`__init__.py`なし）。

## 3. 結果（Linux 6.18、`unshare -n -r`下、別クリーンクローン・core.autocrlf=false、試験対象2daab90）

各版は**別のクリーンクローン**で`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`を実行。版：3.10.20（uvの単体インタプリタ）、3.11.18、3.12.3、3.13.18。4版とも全スイートのrc＝0、失敗0、error0。

| スイート | 件数 | 結果（4版共通） |
|---|---|---|
| v2_core | 197 | OK |
| v2_persistence | 170 | OK |
| v2_persistence_local（S2） | 113 | OK、skip 4（Windows専用） |
| v2_recovery（S3-A） | 176 | OK |
| v2_history（B-1） | 230 | OK |
| v2_history_ops（B-2） | 173 | OK |
| v2_history_restart（B-3） | 109 | OK |
| v2_history_restore（B-4） | 165 | OK |
| v2_history_diagnose（B-5a） | 131 | OK |
| **既存9スイート計** | **1464** | **1460合格＋Windows専用4 skip** |
| **v2_history_adopt（新規）** | **155**（機能143＋scope 12） | OK、skip 0 |
| 合計 | 1619 | 1615合格＋4 skip |

備考：(a) 各版の実行スクリプトの最後の`done 1`は、スクリプト末尾の`[ $rc -ne 0 ] && …`がrc＝0のとき1を返す書き方のためで、スイートの結果ではない。表のrcは各スイート単位の値。(b) 通信禁止はLinuxの`unshare -n -r`（ネットワーク名前空間）と、試験内のプロセス内socket禁止を**別に**扱った。後者は`unshare`なしでも実行し（3.13、新規155件OK）、`test_a5_07`が新ランタイムのAST監査でsocket等の語を検査する。**Windowsは未実施**（Windows機が無い）。他者・ユーザーPCの結果で代用していない。

## 4. 受入条件と試験名の対応

| ID | 試験（ファイル／クラス、件数） |
|---|---|
| A5-01 回帰・変更境界 | 既存9スイート（上表）、`test_a5_08_scope`（A5-18と共通） |
| A5-02 種別と鍵 | test_a5_02_checker／KindAndKeys（5） |
| A5-03 正常な採用記録 | test_a5_02_checker／ValidRecord（5） |
| A5-04 採用記録の各rule | test_a5_02_checker／EachRule（10） |
| A5-05 置き方 | test_a5_02_checker／Placement（8） |
| A5-06 復元の下限 | test_a5_03_downstream／FloorOfRestoreB1（4）、FloorOfRestoreB4（3） |
| A5-07 後続段階 | test_a5_03_downstream／LaterStages（8） |
| A5-08 prepareの引数 | test_a5_04_prepare／Arguments（7） |
| A5-09 診断の状態 | test_a5_04_prepare／DiagnosisStates（5） |
| A5-10 移行の痕跡 | test_a5_04_prepare／MigrationTrace（9。移行を残すprefixでは捨てる側の痕跡を見ない対照を含む） |
| A5-11 ID | test_a5_04_prepare／RequestIds（5） |
| A5-12 採用記録と計画の値 | test_a5_04_prepare／Values（9、期待値は入力から独立に計算） |
| A5-13 confirm | test_a5_05_confirm／Outcomes（6）、Mismatch（10） |
| A5-14 内部の不整合 | test_a5_05_confirm／InsidePackage（6） |
| A5-15 委譲 | test_a5_05_confirm／Delegation（8、新パッケージが実際に参照する名前へのspy） |
| A5-16 不変性・決定性・秘匿 | test_a5_06_value_privacy／Immutability（8）、Determinism（3）、PrintedForms（4）、StoresRefuseTheValues（3） |
| A5-17 範囲監査 | test_a5_07_runtime_audit／Dependencies（6）、Purity（4）、Scope（7） |
| A5-18 新B-5b scope | test_a5_08_scope／PathJudgement（2）、FilesChanged（10） |

件数の合計：28＋15＋35＋30＋18＋17＋12＝155。

## 4.1 具体的な採用例（試験の入力で実測）

| 例 | 入力の作り方 | 診断 | 採用 |
|---|---|---|---|
| 新規履歴の末尾破損 | `ex_new()`（GENESIS＋APPLY 6件）の最後のAPPLYのevent_hashを壊す（`new_world()`） | PREFIX_ONLY、verified.count＝6、discarded.count＝1、migrated＝False | adopt_count＝6でREADY。basisは21キー、採用記録は12キー、evidence.raw_size＝13016、claimed_head_seq＝6、discarded_from_seq＝6、parent_seq＝5。元の生バイトのconfirm＝CONFIRMED_IN_MEMORY、候補の正規化バイトのconfirm＝NO_CHANGE、committed＝False |
| 移行済みprefixの末尾破損 | `ex_m()`にAPPLY 2件を足し、最後を壊す | PREFIX_ONLY、count＝9、migrated＝True、discarded.count＝1 | READY→CONFIRMED_IN_MEMORY→NO_CHANGE |
| 移行記録だけが壊れたバイト | `ex_m()`（0..6が移したAPPLY、7がSCHEMA_MIGRATION）のseq 7のevent_hashだけを壊す | PREFIX_ONLY、count＝2、migrated＝False、捨てる側の最後＝SCHEMA_MIGRATION | `adoption_invalid`／`data`／`migration_discarded`（移行の痕跡を捨てる採用は拒否） |
| adopt_countの食い違い | 診断のcount±1 | — | `adoption_invalid`／`adopt_count`／`count_mismatch` |
| 1バイト違いのデータでconfirm | 計画を作ったバイトから1バイト削る | — | `history_plan_stale` |

## 5. 全差分（c8ba08f→2daab90）

### 5.1 ランタイム6ファイル

```diff
diff --git a/v2_history/__init__.py b/v2_history/__init__.py
index 8201d67..0dda426 100644
--- a/v2_history/__init__.py
+++ b/v2_history/__init__.py
@@ -11,10 +11,10 @@ from .migrate import (CONFIRMED_IN_MEMORY, READY, MigrationConfirmResult, Migrat
                       migrated_sources, prepare_migration_plan)
 from .validate import Boundary, HistoryCheck, validate_history
-from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, KINDS, RECOVERY_RESTORE, RESTART_UNKNOWN,
-                     SCHEMA_MIGRATION, SCHEMA_VERSION_V2, History, decode_history, encode_history)
+from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, KINDS, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,
+                     RESTART_UNKNOWN, SCHEMA_MIGRATION, SCHEMA_VERSION_V2, History, decode_history, encode_history)
 
 __all__ = ["History", "encode_history", "decode_history", "validate_history", "make_history_genesis",
            "migrated_sources", "prepare_migration_plan", "confirm_migration_plan", "HistoryCheck", "Boundary",
            "MigrationPlan", "MigrationConfirmResult", "SCHEMA_VERSION_V2", "KINDS", "GENESIS", "APPLY", "ACK",
-           "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "READY",
-           "CONFIRMED_IN_MEMORY"]
+           "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION",
+           "READY", "CONFIRMED_IN_MEMORY"]
diff --git a/v2_history/restore.py b/v2_history/restore.py
index ce85957..ed1428a 100644
--- a/v2_history/restore.py
+++ b/v2_history/restore.py
@@ -3,5 +3,6 @@
 ordinary view rules (view.py) in the chain views that contain them.
 
-CONSUME and RECOVERY_PREFIX_ADOPTION are refused (restore_op_unsupported / unsupported_event).
+CONSUME is refused (restore_op_unsupported / unsupported_event). RECOVERY_PREFIX_ADOPTION cannot be restored
+before (restore_before_adoption).
 """
 from v2_recovery.common import is_requested_text, valid_request_id
@@ -9,5 +10,6 @@ from v2_recovery.common import is_requested_text, valid_request_id
 from .common import basis_request_hash, is_date, is_hex64, is_int, same
 from .errors import history_invalid
-from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN, SCHEMA_MIGRATION
+from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,
+                     RESTART_UNKNOWN, SCHEMA_MIGRATION)
 
 REASON_RESTORE = "RESTORE_VERIFIED_RECORD"
@@ -99,4 +101,7 @@ def _check_one(events, parents, migration_seq, k, rec, replayed):
     if migration_seq is not None and point < migration_seq:
         raise _bad("restore_before_migration")
+    adoptions = [s for s in chain if events[s]["kind"] == RECOVERY_PREFIX_ADOPTION]
+    if adoptions and point < adoptions[-1]:
+        raise _bad("restore_before_adoption")
     p_rec = events[point]
     if (p_rec["kind"] in (ACK, DECLARE_MISSING) and is_int(p_rec["command_index"])
diff --git a/v2_history/values.py b/v2_history/values.py
index 6d9216a..7e30df0 100644
--- a/v2_history/values.py
+++ b/v2_history/values.py
@@ -22,7 +22,7 @@ RESTART_UNKNOWN = "RESTART_UNKNOWN"
 RECOVERY_RESTORE = "RECOVERY_RESTORE"
 SCHEMA_MIGRATION = "SCHEMA_MIGRATION"
-KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, SCHEMA_MIGRATION)
-# Designed for B-5 and refused here (unsupported_event).
 RECOVERY_PREFIX_ADOPTION = "RECOVERY_PREFIX_ADOPTION"
+KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, SCHEMA_MIGRATION,
+         RECOVERY_PREFIX_ADOPTION)
 
 HEADER_KEYS = frozenset(["schema_version", "core_sha", "head_seq", "head_hash", "current_state", "events"])
@@ -42,8 +42,11 @@ MIGRATION_KEYS = frozenset([
     "request_id", "request_hash", "request_basis", "reason_code", "requested_at", "ledger_digest", "state_after",
     "event_hash"])
+ADOPTION_KEYS = frozenset([
+    "kind", "seq", "parent_seq", "parent_hash", "evidence", "request_id", "request_hash", "request_basis",
+    "reason_code", "requested_at", "state_after", "event_hash"])
 RECORD_KEYS = {
     GENESIS: frozenset(GENESIS_KEYS), APPLY: frozenset(APPLY_KEYS), ACK: _RESOLUTION_KEYS,
     DECLARE_MISSING: _RESOLUTION_KEYS, RESTART_UNKNOWN: RESTART_KEYS, RECOVERY_RESTORE: RESTORE_KEYS,
-    SCHEMA_MIGRATION: MIGRATION_KEYS}
+    SCHEMA_MIGRATION: MIGRATION_KEYS, RECOVERY_PREFIX_ADOPTION: ADOPTION_KEYS}
 
 _MAX_DEPTH = 40
diff --git a/v2_history/view.py b/v2_history/view.py
index 2622caf..44e759c 100644
--- a/v2_history/view.py
+++ b/v2_history/view.py
@@ -18,5 +18,6 @@ from v2_recovery.common import is_requested_text, valid_request_id
 from .common import basis_request_hash, is_date, is_hex64, is_int, same
 from .errors import history_invalid
-from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN, SCHEMA_MIGRATION
+from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,
+                     RESTART_UNKNOWN, SCHEMA_MIGRATION)
 
 VARIANTS = ("ADDED", "CHANGED", "ROW_REMOVED", "LATE")
@@ -25,4 +26,5 @@ REASON_DECLARE = "MARK_SESSION_MISSING"
 REASON_BATCH = "RESOLUTION_BATCH"
 REASON_RESTART = "RESTART_UNKNOWN"
+REASON_ADOPT = "ADOPT_VERIFIED_PREFIX"
 
 COMMAND_KEYS = frozenset(["kind", "variant", "d", "record_fingerprints", "applied_ref", "missing_ref"])
@@ -30,4 +32,7 @@ BASIS_KEYS = frozenset(["request_id", "commands", "check_d", "reason_code", "req
 RESTART_BASIS_KEYS = frozenset(["request_id", "resume_after", "check_d", "reason_code", "requested_at"])
 FLOOR_KEYS = frozenset(["last_apply_d", "last_declared_d", "prev_boundary"])
+EVIDENCE_KEYS = frozenset(["raw_sha256", "raw_size", "claimed_schema_version", "claimed_head_seq",
+                           "claimed_head_hash", "discarded_from_seq"])
+ADOPTION_BASIS_KEYS = frozenset(["request_id", "evidence", "reason_code", "requested_at"])
 _CONFIRMED_INPUT_KEYS = frozenset(["decision", "row", "prev_row", "prev_session_date", "session_context"])
 _REQUEST_LEVEL = ("request_id", "request_hash", "request_basis", "command_count", "ledger_digest", "requested_at")
@@ -323,4 +328,7 @@ class _Walk:
             self.claim_request(rec["request_id"])
             return
+        if kind == RECOVERY_PREFIX_ADOPTION:
+            self.adoption_record(rec, parent_state)
+            return
 
     def resolution_record(self, idx, rec, parent_state):
@@ -449,4 +457,29 @@ class _Walk:
         self.seg_declares = []
 
+    def adoption_record(self, rec, parent_state):
+        """S3-B-5b: a control record that keeps the state and names the raw bytes whose verified prefix was adopted."""
+        self.claim_request(rec["request_id"])
+        if not same(rec["state_after"], parent_state):
+            raise _bad("state_after")
+        ev = rec["evidence"]
+        if (not isinstance(ev, dict) or set(ev) != EVIDENCE_KEYS or not is_hex64(ev["raw_sha256"])
+                or not is_int(ev["raw_size"]) or ev["raw_size"] < 1
+                or not is_int(ev["claimed_schema_version"]) or ev["claimed_schema_version"] != 2
+                or not (ev["claimed_head_seq"] is None or is_int(ev["claimed_head_seq"]))
+                or not (ev["claimed_head_hash"] is None or is_hex64(ev["claimed_head_hash"]))
+                or not is_int(ev["discarded_from_seq"]) or ev["discarded_from_seq"] != rec["seq"]):
+            raise _bad("adoption_evidence")
+        basis = rec["request_basis"]
+        if not isinstance(basis, dict) or set(basis) != ADOPTION_BASIS_KEYS:
+            raise _bad("request_basis")
+        if basis["request_id"] != rec["request_id"] or not same(basis["evidence"], ev):
+            raise _bad("request_basis")
+        if not is_requested_text(basis["requested_at"]) or basis["requested_at"] != rec["requested_at"]:
+            raise _bad("requested_at")
+        if basis["reason_code"] != REASON_ADOPT or rec["reason_code"] != REASON_ADOPT:
+            raise _bad("reason_code")
+        if not is_hex64(rec["request_hash"]) or rec["request_hash"] != basis_request_hash(basis):
+            raise _bad("request_hash")
+
 
 def check_view(recs):
diff --git a/v2_history_ops/chain.py b/v2_history_ops/chain.py
index f94c26c..14e62ea 100644
--- a/v2_history_ops/chain.py
+++ b/v2_history_ops/chain.py
@@ -8,6 +8,6 @@ No rule, threshold or state formula is written here: S1 recalculates (project_se
 functions judge the ledger.
 """
-from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN,
-                               SCHEMA_MIGRATION)
+from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,
+                               RESTART_UNKNOWN, SCHEMA_MIGRATION)
 from v2_history.view import Segment, project_segment
 from v2_persistence.codec import canonical_json, sha256_text
@@ -20,5 +20,6 @@ NATIVE, MIGRATED, REPLAYED = "NATIVE", "MIGRATED", "REPLAYED"
 RESOLUTION = "RESOLUTION"
 _REQUEST_KINDS = {ACK: RESOLUTION, DECLARE_MISSING: RESOLUTION, RESTART_UNKNOWN: RESTART_UNKNOWN,
-                  RECOVERY_RESTORE: RECOVERY_RESTORE, SCHEMA_MIGRATION: SCHEMA_MIGRATION}
+                  RECOVERY_RESTORE: RECOVERY_RESTORE, SCHEMA_MIGRATION: SCHEMA_MIGRATION,
+                  RECOVERY_PREFIX_ADOPTION: RECOVERY_PREFIX_ADOPTION}
 
 
diff --git a/v2_history_restore/points.py b/v2_history_restore/points.py
index 1116545..eebdbdf 100644
--- a/v2_history_restore/points.py
+++ b/v2_history_restore/points.py
@@ -1,5 +1,5 @@
 """The restore point and the operation list (design 4): the checks of the caller's request, in a fixed order."""
 from v2_history.common import is_hex64, is_int
-from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_RESTORE, RESTART_UNKNOWN
+from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE, RESTART_UNKNOWN
 
 from .errors import restore_invalid
@@ -27,4 +27,7 @@ def check_point(check, view, events, point):
     if migration is not None and seq < migration:
         raise restore_invalid("restore_point", "restore_before_migration")
+    taken = [s for s in effective if events[s]["kind"] == RECOVERY_PREFIX_ADOPTION]
+    if taken and seq < taken[-1]:
+        raise restore_invalid("restore_point", "restore_before_adoption")
     rec = events[seq]
     if rec["kind"] in (ACK, DECLARE_MISSING) and rec["command_index"] < rec["command_count"] - 1:
```

### 5.2 既存試験6本（許された箇所だけ）

```diff
diff --git a/tests/v2_history/test_h02_values_codec.py b/tests/v2_history/test_h02_values_codec.py
index 816d7fb..83b8526 100644
--- a/tests/v2_history/test_h02_values_codec.py
+++ b/tests/v2_history/test_h02_values_codec.py
@@ -141,5 +141,5 @@ class FormRefusals(unittest.TestCase):
 
     def test_unknown_kind_and_the_b5_kind(self):
-        for kind in ("BOGUS", "RECOVERY_PREFIX_ADOPTION", None, 7):
+        for kind in ("BOGUS", "CONSUME", None, 7):
             with self.subTest(kind):
                 ev = H.deep(self.ev)
diff --git a/tests/v2_history/test_h14_scope_and_stop.py b/tests/v2_history/test_h14_scope_and_stop.py
index e7719a2..c19f90a 100644
--- a/tests/v2_history/test_h14_scope_and_stop.py
+++ b/tests/v2_history/test_h14_scope_and_stop.py
@@ -103,15 +103,15 @@ class RuntimeIsPure(unittest.TestCase):
             "migrated_sources", "prepare_migration_plan", "confirm_migration_plan", "HistoryCheck", "Boundary",
             "MigrationPlan", "MigrationConfirmResult", "SCHEMA_VERSION_V2", "KINDS", "GENESIS", "APPLY", "ACK",
-            "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "READY",
-            "CONFIRMED_IN_MEMORY"]))
+            "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION",
+            "READY", "CONFIRMED_IN_MEMORY"]))
         for name in v2_history.__all__:
             self.assertTrue(hasattr(v2_history, name))
         self.assertEqual(v2_history.SCHEMA_VERSION_V2, 2)
-        self.assertEqual(len(v2_history.KINDS), 7)
+        self.assertEqual(len(v2_history.KINDS), 8)
         self.assertEqual((v2_history.READY, v2_history.CONFIRMED_IN_MEMORY), ("READY", "CONFIRMED_IN_MEMORY"))
 
     def test_consume_and_the_b5_kind_are_refused(self):
         import v2_history.values as values
-        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", values.KINDS)
+        self.assertEqual(values.KINDS[-1], "RECOVERY_PREFIX_ADOPTION")              # added by B-5b
         self.assertNotIn("CONSUME", sources()["restore.py"].split("_ALLOWED")[1].split("\n\n")[0])
 
diff --git a/tests/v2_history_diagnose/test_d5_08_scope.py b/tests/v2_history_diagnose/test_d5_08_scope.py
index ad03e10..a838405 100644
--- a/tests/v2_history_diagnose/test_d5_08_scope.py
+++ b/tests/v2_history_diagnose/test_d5_08_scope.py
@@ -60,32 +60,67 @@ UNCHANGED_DOCS = ("docs/implementation/V2_RECOVERY_S3B2_RESULT.md", "docs/implem
 
 # --- pinned against the code start ac21980: the removed lines, added lines and hunk headers of each corrected test ---
-PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['                                        "v2_history_restore/", '
+PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['                  "SCHEMA_MIGRATION"}',
+                                             '                                        "v2_history_restore/", '
                                              '"tests/v2_history_restore/"))',
                                              '                                   '
                                              '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
+                                             '                if path != "v2_recovery/commands.py":',
                                              '                       ":(exclude)tests/v2_history_restart", '
                                              '":(exclude)tests/v2_history_restore")'],
-                                            ['                                        "v2_history_restore/", '
+                                            ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
+                                             '        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
+                                             '"v2_history/view.py", "v2_history/restore.py",',
+                                             '               "tests/v2_history/test_h02_values_codec.py", '
+                                             '"tests/v2_history/test_h14_scope_and_stop.py")',
+                                             '                                        "v2_history_restore/", '
                                              '"tests/v2_history_restore/",',
                                              '                                        "v2_history_diagnose/", '
-                                             '"tests/v2_history_diagnose/"))',
+                                             '"tests/v2_history_diagnose/",',
+                                             '                                        "v2_history_adopt/", '
+                                             '"tests/v2_history_adopt/"))',
+                                             '                       or path in b5b',
                                              '                                   '
                                              '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
                                              '                                   '
-                                             '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
+                                             '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",',
+                                             '                                   '
+                                             '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))',
+                                             '                if path != "v2_recovery/commands.py" and path not in '
+                                             'b5b:',
                                              '                             and path != '
                                              '"v2_history_diagnose/__init__.py"',
+                                             '                             and path not in '
+                                             '("v2_history_adopt/__init__.py", "v2_history/__init__.py")',
                                              '                       ":(exclude)tests/v2_history_restart", '
                                              '":(exclude)tests/v2_history_restore",',
-                                             '                       ":(exclude)tests/v2_history_diagnose")'],
-                                            ['@@ -186 +186,2', '@@ -190 +191,2', '@@ -202,0 +205', '@@ -219 +222,2']),
- 'tests/v2_history_restart/test_r3_07_scope.py': (['                                       "v2_history_restore/", '
+                                             '                       ":(exclude)tests/v2_history_diagnose", '
+                                             '":(exclude)tests/v2_history_adopt",',
+                                             '                       '
+                                             '":(exclude)tests/v2_history/test_h02_values_codec.py",',
+                                             '                       '
+                                             '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")'],
+                                            ['@@ -39 +39',
+                                             '@@ -182,0 +183,2',
+                                             '@@ -186 +188,4',
+                                             '@@ -190 +195,3',
+                                             '@@ -193 +200',
+                                             '@@ -202,0 +210,2',
+                                             '@@ -219 +228,4']),
+ 'tests/v2_history_restart/test_r3_07_scope.py': (['            if path == "tests/v2_history_ops/test_b17_scope.py":',
+                                                   '                                       "v2_history_restore/", '
                                                    '"tests/v2_history_restore/")) or path in (',
-                                                   '                '
-                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
+                                                   '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md")',
                                                    '                         {"v2_history_restart/__init__.py", '
                                                    '"v2_history_restore/__init__.py"})',
+                                                   '                       '
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")',
                                                    '                       ":(exclude)tests/v2_history_restore")',
+                                                   '        self.assertEqual(out.stdout.split(), '
+                                                   '["tests/v2_history_ops/test_b17_scope.py"])',
+                                                   '        # point 1 touches two separate lines of the allowed list, '
+                                                   'so git shows four hunks for the three points',
+                                                   '        self.assertEqual(sum(1 for l in lines if '
+                                                   'l.startswith("@@")), 4)',
                                                    "            '                                        "
                                                    '"v2_history_restore/", "tests/v2_history_restore/"))\',',
@@ -95,48 +130,119 @@ PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['
                                                    '":(exclude)tests/v2_history_restart", '
                                                    '":(exclude)tests/v2_history_restore")\'])'],
-                                                  ['                                       "v2_history_restore/", '
+                                                  ['        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
+                                                   '"v2_history/view.py", "v2_history/restore.py",',
+                                                   '               "v2_history_ops/chain.py", '
+                                                   '"tests/v2_history/test_h02_values_codec.py",',
+                                                   '               "tests/v2_history/test_h14_scope_and_stop.py")',
+                                                   '            if path == "tests/v2_history_ops/test_b17_scope.py" or '
+                                                   'path in b5b:',
+                                                   '                                       "v2_history_restore/", '
                                                    '"tests/v2_history_restore/",',
                                                    '                                       "v2_history_diagnose/", '
-                                                   '"tests/v2_history_diagnose/")) or path in (',
-                                                   '                '
-                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
+                                                   '"tests/v2_history_diagnose/",',
+                                                   '                                       "v2_history_adopt/", '
+                                                   '"tests/v2_history_adopt/")) or path in (',
+                                                   '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
-                                                   '                '
-                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")',
+                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
                                                    '                         {"v2_history_restart/__init__.py", '
                                                    '"v2_history_restore/__init__.py",',
-                                                   '                          "v2_history_diagnose/__init__.py"})',
+                                                   '                          "v2_history_diagnose/__init__.py", '
+                                                   '"v2_history_adopt/__init__.py",',
+                                                   '                          "v2_history/__init__.py"})',
+                                                   '                       '
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
+                                                   '":(exclude)v2_history/__init__.py",',
+                                                   '                       ":(exclude)v2_history/values.py", '
+                                                   '":(exclude)v2_history/view.py",',
+                                                   '                       ":(exclude)v2_history/restore.py", '
+                                                   '":(exclude)v2_history_ops/chain.py")',
                                                    '                       ":(exclude)tests/v2_history_restore", '
-                                                   '":(exclude)tests/v2_history_diagnose")',
+                                                   '":(exclude)tests/v2_history_diagnose",',
+                                                   '                       ":(exclude)tests/v2_history_adopt")',
+                                                   '        self.assertEqual(out.stdout.split(), '
+                                                   '["tests/v2_history/test_h02_values_codec.py",',
+                                                   '                                              '
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py",',
+                                                   '                                              '
+                                                   '"tests/v2_history_ops/test_b17_scope.py"])',
+                                                   '        # four hunks for the three points of B-3; B-5b adds the '
+                                                   'kind constant and its edits of the two methods',
+                                                   '        self.assertEqual(sum(1 for l in lines if '
+                                                   'l.startswith("@@")), 7)',
+                                                   '            \'                  "SCHEMA_MIGRATION"}\',',
+                                                   "            '                if path != "
+                                                   '"v2_recovery/commands.py":\',',
+                                                   '            \'                  "SCHEMA_MIGRATION", '
+                                                   '"RECOVERY_PREFIX_ADOPTION"}\',',
+                                                   '            \'        b5b = ("v2_history/__init__.py", '
+                                                   '"v2_history/values.py", "v2_history/view.py", '
+                                                   '"v2_history/restore.py",\',',
+                                                   "            '               "
+                                                   '"tests/v2_history/test_h02_values_codec.py", '
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                    "            '                                        "
                                                    '"v2_history_restore/", "tests/v2_history_restore/",\',',
                                                    "            '                                        "
-                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
+                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
+                                                   "            '                                        "
+                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\',',
+                                                   "            '                       or path in b5b',",
                                                    "            '                                   "
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                    "            '                                   "
-                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
+                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
+                                                   "            '                                   "
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
+                                                   '            \'                if path != "v2_recovery/commands.py" '
+                                                   "and path not in b5b:',",
                                                    "            '                             and path != "
                                                    '"v2_history_diagnose/__init__.py"\',',
+                                                   "            '                             and path not in "
+                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                    "            '                       "
                                                    '":(exclude)tests/v2_history_restart", '
                                                    '":(exclude)tests/v2_history_restore",\',',
                                                    "            '                       "
-                                                   '":(exclude)tests/v2_history_diagnose")\'])'],
-                                                  ['@@ -194,2 +194,4',
-                                                   '@@ -201 +203,2',
-                                                   '@@ -210 +213',
-                                                   '@@ -229 +232,2',
-                                                   '@@ -232 +236,2',
-                                                   '@@ -234,0 +240',
-                                                   '@@ -237 +243,2']),
- 'tests/v2_history_restore/test_r4_09_scope.py': ([" '                                        "
-                                                   '"v2_history_restore/", "tests/v2_history_restore/"))\',',
+                                                   '":(exclude)tests/v2_history_diagnose", '
+                                                   '":(exclude)tests/v2_history_adopt",\',',
+                                                   "            '                       "
+                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
+                                                   "            '                       "
+                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\'])'],
+                                                  ['@@ -188,0 +189,3',
+                                                   '@@ -190 +193',
+                                                   '@@ -194,2 +197,5',
+                                                   '@@ -201 +207,3',
+                                                   '@@ -207 +215,3',
+                                                   '@@ -210,2 +220,5',
+                                                   '@@ -218,2 +231,2',
+                                                   '@@ -220,0 +234',
+                                                   '@@ -222,0 +237',
+                                                   '@@ -226,0 +242,3',
+                                                   '@@ -229 +247,4',
+                                                   '@@ -232 +253,4',
+                                                   '@@ -234,0 +259,2',
+                                                   '@@ -237 +263,4']),
+ 'tests/v2_history_restore/test_r4_09_scope.py': (['                  "SCHEMA_MIGRATION"}',
+                                                   "B17_REMOVED = ['                                        "
+                                                   '"v2_history_restart/", "tests/v2_history_restart/"))\',',
+                                                   "B17_ADDED = ['                                        "
+                                                   '"v2_history_restart/", "tests/v2_history_restart/",\',',
+                                                   ' \'                                        "v2_history_restore/", '
+                                                   '"tests/v2_history_restore/"))\',',
                                                    " '                                   "
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))\',',
                                                    ' \'                       ":(exclude)tests/v2_history_restart", '
                                                    '":(exclude)tests/v2_history_restore")\']',
-                                                   "B17_HUNKS = ['@@ -185 +185,2', '@@ -188 +189,2', '@@ -199,0 "
-                                                   "+202', '@@ -216 +219']",
+                                                   "B17_HUNKS = ['@@ -185 +185,2', '@@ -188 +189,2', '@@ -199,0 +202', "
+                                                   "'@@ -216 +219']",
+                                                   "R307_REMOVED = ['            allowed = "
+                                                   'path.startswith(("v2_history_restart/", '
+                                                   '"tests/v2_history_restart/")) or path in (\',',
+                                                   "R307_ADDED = ['            allowed = "
+                                                   'path.startswith(("v2_history_restart/", '
+                                                   '"tests/v2_history_restart/",\',',
                                                    ' \'                                       "v2_history_restore/", '
                                                    '"tests/v2_history_restore/")) or path in (\',',
@@ -146,6 +252,5 @@ PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['
                                                    ' \'                         {"v2_history_restart/__init__.py", '
                                                    '"v2_history_restore/__init__.py"})\',',
-                                                   " '                       "
-                                                   '":(exclude)tests/v2_history_restore")\',',
+                                                   ' \'                       ":(exclude)tests/v2_history_restore")\',',
                                                    " '            \\'                                        "
                                                    '"v2_history_restore/", "tests/v2_history_restore/"))\\\',\',',
@@ -162,63 +267,199 @@ PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['
                                                    " '@@ -228,0 +234',",
                                                    " '@@ -231 +237']",
+                                                   '                    if v in KIND_CONSTANTS:',
+                                                   '        self.assertEqual(modified, '
+                                                   'sorted(SCOPE_TESTS))                            # the only files '
+                                                   'that are modified',
+                                                   '            if path in SCOPE_TESTS:',
                                                    '            self.assertTrue(allowed_path(path), "unexpected '
                                                    'change: %s %s" % (status, path))',
                                                    '        self.assertEqual({p for p in paths if '
                                                    'p.endswith("__init__.py")}, {"v2_history_restore/__init__.py"})',
-                                                   '        out = self.git("diff", "--name-only", START, "HEAD", '
-                                                   '"--", "tests", ":(exclude)tests/v2_history_restore")'],
-                                                  [" '                                        "
-                                                   '"v2_history_restore/", "tests/v2_history_restore/",\',',
-                                                   " '                                        "
-                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
+                                                   '                       '
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
+                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md")',
+                                                   '        out = self.git("diff", "--name-only", START, "HEAD", "--", '
+                                                   '"tests", ":(exclude)tests/v2_history_restore")',
+                                                   '        self.assertEqual(sorted(out.stdout.split()), '
+                                                   'sorted(SCOPE_TESTS))'],
+                                                  ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
+                                                   'B17_REMOVED = [\'                  "SCHEMA_MIGRATION"}\',',
+                                                   ' \'                                        "v2_history_restart/", '
+                                                   '"tests/v2_history_restart/"))\',',
+                                                   ' \'                if path != "v2_recovery/commands.py":\',',
+                                                   'B17_ADDED = [\'                  "SCHEMA_MIGRATION", '
+                                                   '"RECOVERY_PREFIX_ADOPTION"}\',',
+                                                   ' \'        b5b = ("v2_history/__init__.py", '
+                                                   '"v2_history/values.py", "v2_history/view.py", '
+                                                   '"v2_history/restore.py",\',',
+                                                   ' \'               "tests/v2_history/test_h02_values_codec.py", '
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
+                                                   ' \'                                        "v2_history_restart/", '
+                                                   '"tests/v2_history_restart/",\',',
+                                                   ' \'                                        "v2_history_restore/", '
+                                                   '"tests/v2_history_restore/",\',',
+                                                   ' \'                                        "v2_history_diagnose/", '
+                                                   '"tests/v2_history_diagnose/",\',',
+                                                   ' \'                                        "v2_history_adopt/", '
+                                                   '"tests/v2_history_adopt/"))\',',
+                                                   " '                       or path in b5b',",
                                                    " '                                   "
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                    " '                                   "
-                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
+                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
+                                                   " '                                   "
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
+                                                   ' \'                if path != "v2_recovery/commands.py" and path '
+                                                   "not in b5b:',",
                                                    " '                             and path != "
                                                    '"v2_history_diagnose/__init__.py"\',',
+                                                   " '                             and path not in "
+                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                    ' \'                       ":(exclude)tests/v2_history_restart", '
                                                    '":(exclude)tests/v2_history_restore",\',',
+                                                   ' \'                       ":(exclude)tests/v2_history_diagnose", '
+                                                   '":(exclude)tests/v2_history_adopt",\',',
+                                                   " '                       "
+                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
                                                    " '                       "
-                                                   '":(exclude)tests/v2_history_diagnose")\']',
-                                                   "B17_HUNKS = ['@@ -185 +185,3', '@@ -188 +190,3', '@@ -199,0 "
-                                                   "+204,2', '@@ -216 +222,2']",
+                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\']',
+                                                   "B17_HUNKS = ['@@ -39 +39',",
+                                                   " '@@ -182,0 +183,2',",
+                                                   " '@@ -185 +187,5',",
+                                                   " '@@ -188 +194,4',",
+                                                   " '@@ -191 +200',",
+                                                   " '@@ -199,0 +209,3',",
+                                                   " '@@ -216 +228,4']",
+                                                   "R307_REMOVED = ['            if path == "
+                                                   '"tests/v2_history_ops/test_b17_scope.py":\',',
+                                                   ' \'            allowed = path.startswith(("v2_history_restart/", '
+                                                   '"tests/v2_history_restart/")) or path in (\',',
+                                                   " '                       "
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")\',',
+                                                   " '        self.assertEqual(out.stdout.split(), "
+                                                   '["tests/v2_history_ops/test_b17_scope.py"])\',',
+                                                   " '        # point 1 touches two separate lines of the allowed "
+                                                   "list, so git shows four hunks for the three points',",
+                                                   " '        self.assertEqual(sum(1 for l in lines if "
+                                                   'l.startswith("@@")), 4)\',',
+                                                   'R307_ADDED = [\'        b5b = ("v2_history/__init__.py", '
+                                                   '"v2_history/values.py", "v2_history/view.py", '
+                                                   '"v2_history/restore.py",\',',
+                                                   ' \'               "v2_history_ops/chain.py", '
+                                                   '"tests/v2_history/test_h02_values_codec.py",\',',
+                                                   " '               "
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
+                                                   ' \'            if path == "tests/v2_history_ops/test_b17_scope.py" '
+                                                   "or path in b5b:',",
+                                                   ' \'            allowed = path.startswith(("v2_history_restart/", '
+                                                   '"tests/v2_history_restart/",\',',
                                                    ' \'                                       "v2_history_restore/", '
                                                    '"tests/v2_history_restore/",\',',
-                                                   " '                                       "
-                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/")) or path '
-                                                   "in (',",
+                                                   ' \'                                       "v2_history_diagnose/", '
+                                                   '"tests/v2_history_diagnose/",\',',
+                                                   ' \'                                       "v2_history_adopt/", '
+                                                   '"tests/v2_history_adopt/")) or path in (\',',
                                                    " '                "
                                                    '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                    " '                "
-                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")\',',
+                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\',',
                                                    ' \'                         {"v2_history_restart/__init__.py", '
                                                    '"v2_history_restore/__init__.py",\',',
-                                                   " '                          "
-                                                   '"v2_history_diagnose/__init__.py"})\',',
+                                                   ' \'                          "v2_history_diagnose/__init__.py", '
+                                                   '"v2_history_adopt/__init__.py",\',',
+                                                   ' \'                          "v2_history/__init__.py"})\',',
+                                                   " '                       "
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
+                                                   '":(exclude)v2_history/__init__.py",\',',
+                                                   ' \'                       ":(exclude)v2_history/values.py", '
+                                                   '":(exclude)v2_history/view.py",\',',
+                                                   ' \'                       ":(exclude)v2_history/restore.py", '
+                                                   '":(exclude)v2_history_ops/chain.py")\',',
                                                    ' \'                       ":(exclude)tests/v2_history_restore", '
-                                                   '":(exclude)tests/v2_history_diagnose")\',',
+                                                   '":(exclude)tests/v2_history_diagnose",\',',
+                                                   ' \'                       ":(exclude)tests/v2_history_adopt")\',',
+                                                   " '        self.assertEqual(out.stdout.split(), "
+                                                   '["tests/v2_history/test_h02_values_codec.py",\',',
+                                                   " '                                              "
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py",\',',
+                                                   " '                                              "
+                                                   '"tests/v2_history_ops/test_b17_scope.py"])\',',
+                                                   " '        # four hunks for the three points of B-3; B-5b adds the "
+                                                   "kind constant and its edits of the two methods',",
+                                                   " '        self.assertEqual(sum(1 for l in lines if "
+                                                   'l.startswith("@@")), 7)\',',
+                                                   ' \'            \\\'                  "SCHEMA_MIGRATION"}\\\',\',',
+                                                   " '            \\'                if path != "
+                                                   '"v2_recovery/commands.py":\\\',\',',
+                                                   ' \'            \\\'                  "SCHEMA_MIGRATION", '
+                                                   '"RECOVERY_PREFIX_ADOPTION"}\\\',\',',
+                                                   ' \'            \\\'        b5b = ("v2_history/__init__.py", '
+                                                   '"v2_history/values.py", "v2_history/view.py", \'',
+                                                   ' \'"v2_history/restore.py",\\\',\',',
+                                                   " '            \\'               "
+                                                   '"tests/v2_history/test_h02_values_codec.py", \'',
+                                                   ' \'"tests/v2_history/test_h14_scope_and_stop.py")\\\',\',',
                                                    " '            \\'                                        "
                                                    '"v2_history_restore/", "tests/v2_history_restore/",\\\',\',',
                                                    " '            \\'                                        "
-                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\\\',\',',
+                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\\\',\',',
+                                                   " '            \\'                                        "
+                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\\\',\',',
+                                                   ' "            \'                       or path in b5b\',",',
                                                    " '            \\'                                   "
                                                    '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\\\',\',',
                                                    " '            \\'                                   "
-                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\\\',\',',
+                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\',\',',
+                                                   " '            \\'                                   "
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\',\',',
+                                                   " '            \\'                if path != "
+                                                   '"v2_recovery/commands.py" and path not in b5b:\\\',\',',
                                                    " '            \\'                             and path != "
                                                    '"v2_history_diagnose/__init__.py"\\\',\',',
+                                                   " '            \\'                             and path not in "
+                                                   '("v2_history_adopt/__init__.py", \'',
+                                                   ' \'"v2_history/__init__.py")\\\',\',',
                                                    " '            \\'                       "
                                                    '":(exclude)tests/v2_history_restart", '
                                                    '":(exclude)tests/v2_history_restore",\\\',\',',
                                                    " '            \\'                       "
-                                                   '":(exclude)tests/v2_history_diagnose")\\\'])\']',
-                                                   "R307_HUNKS = ['@@ -193,2 +193,5', '@@ -199 +202,3', '@@ -207 "
-                                                   "+212,2', '@@ -225 +231,3', '@@ -227 +235,3', '@@ -228,0 +239,2', "
-                                                   "'@@ -231 +243,2']",
+                                                   '":(exclude)tests/v2_history_diagnose", '
+                                                   '":(exclude)tests/v2_history_adopt",\\\',\',',
+                                                   " '            \\'                       "
+                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\\\',\',',
+                                                   " '            \\'                       "
+                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\\\'])\']',
+                                                   "R307_HUNKS = ['@@ -188,0 +189,3',",
+                                                   " '@@ -190 +193',",
+                                                   " '@@ -193,2 +196,6',",
+                                                   " '@@ -199 +206,4',",
+                                                   " '@@ -205 +215,3',",
+                                                   " '@@ -207,2 +219,6',",
+                                                   " '@@ -215,2 +231,2',",
+                                                   " '@@ -217,0 +234',",
+                                                   " '@@ -219,0 +237',",
+                                                   " '@@ -223,0 +242,3',",
+                                                   " '@@ -225 +246,5',",
+                                                   " '@@ -227 +252,5',",
+                                                   " '@@ -228,0 +258,3',",
+                                                   " '@@ -231 +263,4']",
+                                                   '                    if v in KIND_CONSTANTS or v == '
+                                                   '"restore_before_adoption":      # the B-5b refusal code',
+                                                   '        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
+                                                   '"v2_history/view.py", "v2_history/restore.py",',
+                                                   '               "v2_history_ops/chain.py", '
+                                                   '"tests/v2_history/test_h02_values_codec.py",',
+                                                   '               "tests/v2_history/test_h14_scope_and_stop.py")',
+                                                   '        self.assertEqual(modified, sorted(SCOPE_TESTS + '
+                                                   'b5b))                      # the only files that are modified',
+                                                   '            if path in SCOPE_TESTS or path in b5b:',
                                                    '            new_b5a = path.startswith(("v2_history_diagnose/", '
-                                                   '"tests/v2_history_diagnose/")) or path == \\',
-                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"',
+                                                   '"tests/v2_history_diagnose/",',
+                                                   '                                       "v2_history_adopt/", '
+                                                   '"tests/v2_history_adopt/")) or path in (',
+                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
+                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
                                                    '            self.assertTrue(allowed_path(path) or new_b5a, '
                                                    '"unexpected change: %s %s" % (status, path))',
@@ -226,20 +467,44 @@ PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['
                                                    'p.endswith("__init__.py")},',
                                                    '                         {"v2_history_restore/__init__.py", '
-                                                   '"v2_history_diagnose/__init__.py"})',
-                                                   '        out = self.git("diff", "--name-only", START, "HEAD", '
-                                                   '"--", "tests", ":(exclude)tests/v2_history_restore",',
-                                                   '                       ":(exclude)tests/v2_history_diagnose")'],
-                                                  ['@@ -83 +83,2',
-                                                   '@@ -85 +86,2',
-                                                   '@@ -87,2 +89,4',
-                                                   '@@ -97,3 +101,4',
-                                                   '@@ -101 +106,2',
-                                                   '@@ -103 +109',
-                                                   '@@ -105 +111,2',
-                                                   '@@ -107 +114,2',
-                                                   '@@ -109,9 +117,4',
-                                                   '@@ -350 +353,3',
-                                                   '@@ -354 +359,2',
-                                                   '@@ -380 +386,2'])}
+                                                   '"v2_history_diagnose/__init__.py",',
+                                                   '                          "v2_history_adopt/__init__.py", '
+                                                   '"v2_history/__init__.py"})',
+                                                   '                       '
+                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
+                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
+                                                   '                       ":(exclude)v2_history/__init__.py", '
+                                                   '":(exclude)v2_history/values.py",',
+                                                   '                       ":(exclude)v2_history/view.py", '
+                                                   '":(exclude)v2_history/restore.py",',
+                                                   '                       ":(exclude)v2_history_ops/chain.py")',
+                                                   '        out = self.git("diff", "--name-only", START, "HEAD", "--", '
+                                                   '"tests", ":(exclude)tests/v2_history_restore",',
+                                                   '                       ":(exclude)tests/v2_history_diagnose", '
+                                                   '":(exclude)tests/v2_history_adopt")',
+                                                   '        self.assertEqual(sorted(out.stdout.split()), '
+                                                   'sorted(SCOPE_TESTS + ("tests/v2_history/test_h02_values_codec.py",',
+                                                   '                                                                           '
+                                                   '"tests/v2_history/test_h14_scope_and_stop.py")))'],
+                                                  ['@@ -38 +38',
+                                                   '@@ -79 +79,2',
+                                                   '@@ -80,0 +82',
+                                                   '@@ -82,2 +84,8',
+                                                   '@@ -85 +93,4',
+                                                   '@@ -87,3 +98,15',
+                                                   '@@ -91,0 +115',
+                                                   '@@ -92,0 +117,3',
+                                                   '@@ -96,4 +123,10',
+                                                   '@@ -101 +134,6',
+                                                   '@@ -103 +141,14',
+                                                   '@@ -105 +156,4',
+                                                   '@@ -107 +161,4',
+                                                   '@@ -109,9 +166,21',
+                                                   '@@ -195 +264',
+                                                   '@@ -346 +415,4',
+                                                   '@@ -348 +420',
+                                                   '@@ -350 +422,4',
+                                                   '@@ -354 +429,3',
+                                                   '@@ -378 +455,4',
+                                                   '@@ -380,2 +460,4'])}
 
 
@@ -410,5 +675,5 @@ class Runtime(unittest.TestCase):
             self.assertNotIn(banned, defined)
         import v2_history
-        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", v2_history.KINDS)
+        self.assertEqual(v2_history.KINDS[-1], "RECOVERY_PREFIX_ADOPTION")              # the kind is added by B-5b
 
     def test_the_new_tests_use_unique_names_and_no_init_file(self):
@@ -472,12 +737,18 @@ class FilesChanged(unittest.TestCase):
     def test_modified_files_are_exactly_the_three_scope_tests_and_every_other_change_is_a_new_allowed_file(self):
         rows = self.changed()
-        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(SCOPE_TESTS))
+        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
+               "v2_history_ops/chain.py", "v2_history_restore/points.py",
+               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")
+        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(SCOPE_TESTS + b5b))
         for status, path in rows:
             if status == "M":
                 continue
             self.assertEqual(status, "A", "%s %s" % (status, path))                 # no deletion, no mode change
-            self.assertTrue(allowed_new_path(path), "unexpected change: %s %s" % (status, path))
+            new_b5b = path.startswith(("v2_history_adopt/", "tests/v2_history_adopt/")) or \
+                path == "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"
+            self.assertTrue(allowed_new_path(path) or new_b5b, "unexpected change: %s %s" % (status, path))
         paths = {p for _s, p in rows}
-        self.assertEqual({p for p in paths if p.endswith("__init__.py")}, {"v2_history_diagnose/__init__.py"})
+        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
+                         {"v2_history_diagnose/__init__.py", "v2_history_adopt/__init__.py", "v2_history/__init__.py"})
         self.assertIn("v2_history_diagnose/diagnose.py", paths)
         self.assertEqual({p for p in paths if p.startswith("v2_history_diagnose/")},
@@ -485,10 +756,15 @@ class FilesChanged(unittest.TestCase):
 
     def test_everything_else_is_identical_to_the_code_start(self):
-        out = self.git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)
+        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
+               "v2_history_ops/chain.py", "v2_history_restore/points.py",
+               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")
+        out = self.git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS,
+                       *[":(exclude)%s" % p for p in b5b])
         self.assertEqual(out.stdout.strip(), "")
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_diagnose",
-                       *[":(exclude)%s" % p for p in SCOPE_TESTS])
+                       ":(exclude)tests/v2_history_adopt", *[":(exclude)%s" % p for p in SCOPE_TESTS + b5b])
         self.assertEqual(out.stdout.strip(), "")
-        out = self.git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC)
+        out = self.git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC,
+                       ":(exclude)docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")
         self.assertEqual(out.stdout.strip(), "")
 
@@ -504,6 +780,6 @@ class FilesChanged(unittest.TestCase):
             self.assertEqual(kind, "blob")
             here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
-            if path == corrected:
-                seen_corrected = True
+            if path in (corrected, "v2_history_restore/points.py"):            # points.py: changed by B-5b
+                seen_corrected = seen_corrected or path == corrected
                 self.assertNotEqual(here.stdout.strip(), blob, path)
                 continue
@@ -521,5 +797,8 @@ class FilesChanged(unittest.TestCase):
         rows = [line.split() for line in listing.stdout.splitlines()]
         self.assertGreater(len(rows), 150)
-        corrected = set(SCOPE_TESTS)
+        corrected = set(SCOPE_TESTS) | {"v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py",
+                                        "v2_history/restore.py", "v2_history_ops/chain.py",
+                                        "tests/v2_history/test_h02_values_codec.py",
+                                        "tests/v2_history/test_h14_scope_and_stop.py"}
         for _mode, kind, blob, path in rows:
             if path in corrected:
@@ -551,5 +830,8 @@ class FilesChanged(unittest.TestCase):
             names = lambda text: [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef)]  # noqa: E731
             self.assertEqual(names(old), names(new), path)
-            self.assertEqual(len(re.findall(r"self\.assert\w*\(", new)), len(re.findall(r"self\.assert\w*\(", old)), path)
+            # counted as calls (B-5b): the pinned text of the r4_09 lists quotes assert calls of the older tests
+            asserts = lambda text: sum(1 for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call)  # noqa: E731
+                                       and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))
+            self.assertEqual(asserts(new), asserts(old), path)
             for word in ("skip", "expectedFailure", "@unittest", "pass\n", "return\n"):
                 self.assertEqual(new.count(word), old.count(word), "%s: %r" % (path, word))
@@ -588,7 +870,8 @@ class FilesChanged(unittest.TestCase):
 
     def test_each_edit_lies_in_the_allowed_places(self):
-        funcs, _ = self.spans(SCOPE_TESTS[0])
+        funcs, assigns = self.spans(SCOPE_TESTS[0])
         self.assert_inside(SCOPE_TESTS[0], [funcs["test_only_the_allowed_paths_differ"],
-                                             funcs["test_existing_tests_and_fixtures_are_untouched"]])
+                                             funcs["test_existing_tests_and_fixtures_are_untouched"],
+                                             assigns["KIND_CONSTANTS"]])
         funcs, _ = self.spans(SCOPE_TESTS[1])
         self.assert_inside(SCOPE_TESTS[1], [funcs[n] for n in (
@@ -597,7 +880,8 @@ class FilesChanged(unittest.TestCase):
         funcs, assigns = self.spans(SCOPE_TESTS[2])
         self.assert_inside(SCOPE_TESTS[2], [assigns[n] for n in (
-            "B17_REMOVED", "B17_ADDED", "B17_HUNKS", "R307_REMOVED", "R307_ADDED", "R307_HUNKS")] + [
+            "B17_REMOVED", "B17_ADDED", "B17_HUNKS", "R307_REMOVED", "R307_ADDED", "R307_HUNKS", "KIND_CONSTANTS")] + [
             funcs["test_only_the_allowed_paths_differ"],
-            funcs["test_no_existing_runtime_old_test_fixture_or_setting_differs"]])
+            funcs["test_no_existing_runtime_old_test_fixture_or_setting_differs"],
+            funcs["test_nothing_of_the_later_stages"]])
 
     def test_the_module_functions_of_the_b4_judgement_are_untouched(self):
diff --git a/tests/v2_history_ops/test_b17_scope.py b/tests/v2_history_ops/test_b17_scope.py
index c6b0ee1..600e184 100644
--- a/tests/v2_history_ops/test_b17_scope.py
+++ b/tests/v2_history_ops/test_b17_scope.py
@@ -37,5 +37,5 @@ ALLOWED_NAMES = {
 }
 KIND_CONSTANTS = {"ACK", "APPLY", "DECLARE_MISSING", "GENESIS", "RECOVERY_RESTORE", "RESTART_UNKNOWN",
-                  "SCHEMA_MIGRATION"}
+                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}
 FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                      "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
@@ -181,17 +181,22 @@ class FilesChanged(unittest.TestCase):
         self.assertEqual(out.returncode, 0, out.stderr)
         changed = [line.split("\t") for line in out.stdout.splitlines()]
+        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
+               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")
         for status, path in changed:
             allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",
                                         "v2_history_restart/", "tests/v2_history_restart/",
                                         "v2_history_restore/", "tests/v2_history_restore/",
-                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))
+                                        "v2_history_diagnose/", "tests/v2_history_diagnose/",
+                                        "v2_history_adopt/", "tests/v2_history_adopt/"))
+                       or path in b5b
                        or path in ("v2_recovery/facts.py", "v2_recovery/commands.py",
                                    "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",
                                    "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
                                    "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
-                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))
+                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md",
+                                   "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
             if not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")):
-                if path != "v2_recovery/commands.py":
+                if path != "v2_recovery/commands.py" and path not in b5b:
                     self.assertEqual(status, "A", path)                       # new files only
                 else:
@@ -204,4 +209,5 @@ class FilesChanged(unittest.TestCase):
                              and path != "v2_history_restore/__init__.py"
                              and path != "v2_history_diagnose/__init__.py"
+                             and path not in ("v2_history_adopt/__init__.py", "v2_history/__init__.py")
                              and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)
 
@@ -221,5 +227,7 @@ class FilesChanged(unittest.TestCase):
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",
                        ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",
-                       ":(exclude)tests/v2_history_diagnose")
+                       ":(exclude)tests/v2_history_diagnose", ":(exclude)tests/v2_history_adopt",
+                       ":(exclude)tests/v2_history/test_h02_values_codec.py",
+                       ":(exclude)tests/v2_history/test_h14_scope_and_stop.py")
         self.assertEqual(out.stdout.strip(), "")
         out = self.git("diff", "--name-only", START, "HEAD", "--", "main.py", "requirements.txt", ".github", "research",
diff --git a/tests/v2_history_restart/test_r3_07_scope.py b/tests/v2_history_restart/test_r3_07_scope.py
index f3eedcc..49d432b 100644
--- a/tests/v2_history_restart/test_r3_07_scope.py
+++ b/tests/v2_history_restart/test_r3_07_scope.py
@@ -187,13 +187,17 @@ class FilesChanged(unittest.TestCase):
         self.assertEqual(out.returncode, 0, out.stderr)
         changed = [line.split("\t") for line in out.stdout.splitlines()]
+        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
+               "v2_history_ops/chain.py", "tests/v2_history/test_h02_values_codec.py",
+               "tests/v2_history/test_h14_scope_and_stop.py")
         for status, path in changed:
-            if path == "tests/v2_history_ops/test_b17_scope.py":
+            if path == "tests/v2_history_ops/test_b17_scope.py" or path in b5b:
                 self.assertEqual(status, "M", path)
                 continue
             allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",
                                        "v2_history_restore/", "tests/v2_history_restore/",
-                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (
+                                       "v2_history_diagnose/", "tests/v2_history_diagnose/",
+                                       "v2_history_adopt/", "tests/v2_history_adopt/")) or path in (
                 "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
-                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")
+                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")
             self.assertTrue(allowed, "unexpected change: %s %s" % (status, path))
             self.assertEqual(status, "A", path)                          # new files only
@@ -202,5 +206,6 @@ class FilesChanged(unittest.TestCase):
         self.assertEqual({p for p in paths if p.endswith("__init__.py")},
                          {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",
-                          "v2_history_diagnose/__init__.py"})
+                          "v2_history_diagnose/__init__.py", "v2_history_adopt/__init__.py",
+                          "v2_history/__init__.py"})
 
     def test_no_existing_runtime_old_test_fixture_or_setting_differs(self):
@@ -208,9 +213,14 @@ class FilesChanged(unittest.TestCase):
                        "v2_history", "v2_history_ops", "main.py", "requirements.txt", ".github", "research",
                        "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md",
-                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md")
+                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md", ":(exclude)v2_history/__init__.py",
+                       ":(exclude)v2_history/values.py", ":(exclude)v2_history/view.py",
+                       ":(exclude)v2_history/restore.py", ":(exclude)v2_history_ops/chain.py")
         self.assertEqual(out.stdout.strip(), "")
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",
-                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")
-        self.assertEqual(out.stdout.split(), ["tests/v2_history_ops/test_b17_scope.py"])
+                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose",
+                       ":(exclude)tests/v2_history_adopt")
+        self.assertEqual(out.stdout.split(), ["tests/v2_history/test_h02_values_codec.py",
+                                              "tests/v2_history/test_h14_scope_and_stop.py",
+                                              "tests/v2_history_ops/test_b17_scope.py"])
 
     def test_the_old_range_test_differs_in_exactly_the_three_allowed_places(self):
@@ -219,28 +229,40 @@ class FilesChanged(unittest.TestCase):
         removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
         added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
-        # point 1 touches two separate lines of the allowed list, so git shows four hunks for the three points
-        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), 4)
+        # four hunks for the three points of B-3; B-5b adds the kind constant and its edits of the two methods
+        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), 7)
         self.assertEqual(removed, [
+            '                  "SCHEMA_MIGRATION"}',
             '            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/"))',
             '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md"))',
+            '                if path != "v2_recovery/commands.py":',
             '            self.assertFalse(path.endswith("__init__.py") and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")),',
             '                             path)',
             '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")'])
         self.assertEqual(added, [
+            '                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
+            '        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",',
+            '               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")',
             '            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",',
             '                                        "v2_history_restart/", "tests/v2_history_restart/",',
             '                                        "v2_history_restore/", "tests/v2_history_restore/",',
-            '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
+            '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/",',
+            '                                        "v2_history_adopt/", "tests/v2_history_adopt/"))',
+            '                       or path in b5b',
             '                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",',
             '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
             '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
-            '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
+            '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md",',
+            '                                   "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))',
+            '                if path != "v2_recovery/commands.py" and path not in b5b:',
             '            self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"',
             '                             and path != "v2_history_restore/__init__.py"',
             '                             and path != "v2_history_diagnose/__init__.py"',
+            '                             and path not in ("v2_history_adopt/__init__.py", "v2_history/__init__.py")',
             '                             and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)',
             '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",',
             '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
-            '                       ":(exclude)tests/v2_history_diagnose")'])
+            '                       ":(exclude)tests/v2_history_diagnose", ":(exclude)tests/v2_history_adopt",',
+            '                       ":(exclude)tests/v2_history/test_h02_values_codec.py",',
+            '                       ":(exclude)tests/v2_history/test_h14_scope_and_stop.py")'])
 
 
diff --git a/tests/v2_history_restore/test_r4_09_scope.py b/tests/v2_history_restore/test_r4_09_scope.py
index c5e8508..92bc2ee 100644
--- a/tests/v2_history_restore/test_r4_09_scope.py
+++ b/tests/v2_history_restore/test_r4_09_scope.py
@@ -36,5 +36,5 @@ ALLOWED_NAMES = {
 }
 KIND_CONSTANTS = {"ACK", "APPLY", "DECLARE_MISSING", "GENESIS", "RECOVERY_RESTORE", "RESTART_UNKNOWN",
-                  "SCHEMA_MIGRATION"}
+                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}
 FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                      "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
@@ -77,46 +77,112 @@ def allowed_path(path):
 
 # --- generated from the committed diff of the code start (d82a5ce) to the corrected files; pinned as text ---
-B17_REMOVED = ['                                        "v2_history_restart/", "tests/v2_history_restart/"))',
+B17_REMOVED = ['                  "SCHEMA_MIGRATION"}',
+ '                                        "v2_history_restart/", "tests/v2_history_restart/"))',
  '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))',
+ '                if path != "v2_recovery/commands.py":',
  '                       ":(exclude)tests/v2_history_restart")']
-B17_ADDED = ['                                        "v2_history_restart/", "tests/v2_history_restart/",',
+B17_ADDED = ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
+ '        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",',
+ '               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")',
+ '                                        "v2_history_restart/", "tests/v2_history_restart/",',
  '                                        "v2_history_restore/", "tests/v2_history_restore/",',
- '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
+ '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/",',
+ '                                        "v2_history_adopt/", "tests/v2_history_adopt/"))',
+ '                       or path in b5b',
  '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
  '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
- '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
+ '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md",',
+ '                                   "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))',
+ '                if path != "v2_recovery/commands.py" and path not in b5b:',
  '                             and path != "v2_history_restore/__init__.py"',
  '                             and path != "v2_history_diagnose/__init__.py"',
+ '                             and path not in ("v2_history_adopt/__init__.py", "v2_history/__init__.py")',
  '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
- '                       ":(exclude)tests/v2_history_diagnose")']
-B17_HUNKS = ['@@ -185 +185,3', '@@ -188 +190,3', '@@ -199,0 +204,2', '@@ -216 +222,2']
-R307_REMOVED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/")) or path in (',
+ '                       ":(exclude)tests/v2_history_diagnose", ":(exclude)tests/v2_history_adopt",',
+ '                       ":(exclude)tests/v2_history/test_h02_values_codec.py",',
+ '                       ":(exclude)tests/v2_history/test_h14_scope_and_stop.py")']
+B17_HUNKS = ['@@ -39 +39',
+ '@@ -182,0 +183,2',
+ '@@ -185 +187,5',
+ '@@ -188 +194,4',
+ '@@ -191 +200',
+ '@@ -199,0 +209,3',
+ '@@ -216 +228,4']
+R307_REMOVED = ['            if path == "tests/v2_history_ops/test_b17_scope.py":',
+ '            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/")) or path in (',
  '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",)',
  '        self.assertEqual({p for p in paths if p.endswith("__init__.py")}, {"v2_history_restart/__init__.py"})',
+ '                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md")',
  '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart")',
+ '        self.assertEqual(out.stdout.split(), ["tests/v2_history_ops/test_b17_scope.py"])',
+ '        # point 1 touches two separate lines of the allowed list, so git shows four hunks for the three points',
+ '        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), 4)',
  '            \'                                        "v2_history_restart/", "tests/v2_history_restart/"))\',',
  '            \'                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))\',',
  '            \'                       ":(exclude)tests/v2_history_restart")\'])']
-R307_ADDED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",',
+R307_ADDED = ['        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",',
+ '               "v2_history_ops/chain.py", "tests/v2_history/test_h02_values_codec.py",',
+ '               "tests/v2_history/test_h14_scope_and_stop.py")',
+ '            if path == "tests/v2_history_ops/test_b17_scope.py" or path in b5b:',
+ '            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",',
  '                                       "v2_history_restore/", "tests/v2_history_restore/",',
- '                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (',
+ '                                       "v2_history_diagnose/", "tests/v2_history_diagnose/",',
+ '                                       "v2_history_adopt/", "tests/v2_history_adopt/")) or path in (',
  '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
- '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")',
+ '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
  '        self.assertEqual({p for p in paths if p.endswith("__init__.py")},',
  '                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",',
- '                          "v2_history_diagnose/__init__.py"})',
+ '                          "v2_history_diagnose/__init__.py", "v2_history_adopt/__init__.py",',
+ '                          "v2_history/__init__.py"})',
+ '                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md", ":(exclude)v2_history/__init__.py",',
+ '                       ":(exclude)v2_history/values.py", ":(exclude)v2_history/view.py",',
+ '                       ":(exclude)v2_history/restore.py", ":(exclude)v2_history_ops/chain.py")',
  '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",',
- '                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")',
+ '                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose",',
+ '                       ":(exclude)tests/v2_history_adopt")',
+ '        self.assertEqual(out.stdout.split(), ["tests/v2_history/test_h02_values_codec.py",',
+ '                                              "tests/v2_history/test_h14_scope_and_stop.py",',
+ '                                              "tests/v2_history_ops/test_b17_scope.py"])',
+ '        # four hunks for the three points of B-3; B-5b adds the kind constant and its edits of the two methods',
+ '        self.assertEqual(sum(1 for l in lines if l.startswith("@@")), 7)',
+ '            \'                  "SCHEMA_MIGRATION"}\',',
+ '            \'                if path != "v2_recovery/commands.py":\',',
+ '            \'                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}\',',
+ '            \'        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", '
+ '"v2_history/restore.py",\',',
+ '            \'               "tests/v2_history/test_h02_values_codec.py", '
+ '"tests/v2_history/test_h14_scope_and_stop.py")\',',
  '            \'                                        "v2_history_restart/", "tests/v2_history_restart/",\',',
  '            \'                                        "v2_history_restore/", "tests/v2_history_restore/",\',',
- '            \'                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
+ '            \'                                        "v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
+ '            \'                                        "v2_history_adopt/", "tests/v2_history_adopt/"))\',',
+ "            '                       or path in b5b',",
  '            \'                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",\',',
  '            \'                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
- '            \'                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
+ '            \'                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
+ '            \'                                   "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
+ '            \'                if path != "v2_recovery/commands.py" and path not in b5b:\',',
  '            \'                             and path != "v2_history_restore/__init__.py"\',',
  '            \'                             and path != "v2_history_diagnose/__init__.py"\',',
+ '            \'                             and path not in ("v2_history_adopt/__init__.py", '
+ '"v2_history/__init__.py")\',',
  '            \'                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",\',',
- '            \'                       ":(exclude)tests/v2_history_diagnose")\'])']
-R307_HUNKS = ['@@ -193,2 +193,5', '@@ -199 +202,3', '@@ -207 +212,2', '@@ -225 +231,3', '@@ -227 +235,3', '@@ -228,0 +239,2', '@@ -231 +243,2']
+ '            \'                       ":(exclude)tests/v2_history_diagnose", ":(exclude)tests/v2_history_adopt",\',',
+ '            \'                       ":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
+ '            \'                       ":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\'])']
+R307_HUNKS = ['@@ -188,0 +189,3',
+ '@@ -190 +193',
+ '@@ -193,2 +196,6',
+ '@@ -199 +206,4',
+ '@@ -205 +215,3',
+ '@@ -207,2 +219,6',
+ '@@ -215,2 +231,2',
+ '@@ -217,0 +234',
+ '@@ -219,0 +237',
+ '@@ -223,0 +242,3',
+ '@@ -225 +246,5',
+ '@@ -227 +252,5',
+ '@@ -228,0 +258,3',
+ '@@ -231 +263,4']
 
 
@@ -196,5 +262,5 @@ class Runtime(unittest.TestCase):
                 for v in values:
                     checked += 1
-                    if v in KIND_CONSTANTS:
+                    if v in KIND_CONSTANTS or v == "restore_before_adoption":      # the B-5b refusal code
                         continue
                     for word in LATER_STAGE_WORDS:
@@ -347,10 +413,14 @@ class FilesChanged(unittest.TestCase):
         changed = [line.split("\t") for line in out.stdout.splitlines()]
         modified = sorted(p for s, p in changed if s == "M")
-        self.assertEqual(modified, sorted(SCOPE_TESTS))                            # the only files that are modified
+        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
+               "v2_history_ops/chain.py", "tests/v2_history/test_h02_values_codec.py",
+               "tests/v2_history/test_h14_scope_and_stop.py")
+        self.assertEqual(modified, sorted(SCOPE_TESTS + b5b))                      # the only files that are modified
         for status, path in changed:
-            if path in SCOPE_TESTS:
+            if path in SCOPE_TESTS or path in b5b:
                 continue
-            new_b5a = path.startswith(("v2_history_diagnose/", "tests/v2_history_diagnose/")) or path == \
-                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"
+            new_b5a = path.startswith(("v2_history_diagnose/", "tests/v2_history_diagnose/",
+                                       "v2_history_adopt/", "tests/v2_history_adopt/")) or path in (
+                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")
             self.assertTrue(allowed_path(path) or new_b5a, "unexpected change: %s %s" % (status, path))
             self.assertEqual(status, "A", path)                                      # new files only
@@ -358,5 +428,6 @@ class FilesChanged(unittest.TestCase):
         self.assertIn("v2_history_restore/__init__.py", paths)
         self.assertEqual({p for p in paths if p.endswith("__init__.py")},
-                         {"v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py"})
+                         {"v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py",
+                          "v2_history_adopt/__init__.py", "v2_history/__init__.py"})
 
     def test_the_b3_runtime_tests_and_result_are_the_same_as_the_code_start(self):
@@ -382,9 +453,13 @@ class FilesChanged(unittest.TestCase):
                        "v2_history", "v2_history_ops", "v2_history_restart", "main.py", "requirements.txt", ".github",
                        "research", "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md",
-                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md", "docs/implementation/V2_RECOVERY_S3B3_RESULT.md")
+                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md", "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
+                       ":(exclude)v2_history/__init__.py", ":(exclude)v2_history/values.py",
+                       ":(exclude)v2_history/view.py", ":(exclude)v2_history/restore.py",
+                       ":(exclude)v2_history_ops/chain.py")
         self.assertEqual(out.stdout.strip(), "")
         out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore",
-                       ":(exclude)tests/v2_history_diagnose")
-        self.assertEqual(sorted(out.stdout.split()), sorted(SCOPE_TESTS))
+                       ":(exclude)tests/v2_history_diagnose", ":(exclude)tests/v2_history_adopt")
+        self.assertEqual(sorted(out.stdout.split()), sorted(SCOPE_TESTS + ("tests/v2_history/test_h02_values_codec.py",
+                                                                           "tests/v2_history/test_h14_scope_and_stop.py")))
 
     def diff_lines(self, path):
```

試験の補正は、h02（種別の対照を未対応の別名`CONSUME`へ）、h14（公開名と種別数）、b17→r3_07→r4_09→d5_08（旧scope試験の連鎖。変更行の固定リテラルと、新B-5b変更の許可）に限る。test関数名と数は変えていない。d5_08は旧3本のリテラルの更新が中心のため行数が多い。

## 6. 試行diff（設計§8）との違い

- **ランタイム6ファイル**：試行と同じ。ただし`v2_history/restore.py`の冒頭docstring1箇所（「CONSUME and RECOVERY_PREFIX_ADOPTION are refused」→「CONSUME is refused … RECOVERY_PREFIX_ADOPTION cannot be restored before (restore_before_adoption)」）を、実装後の事実に合わせて直した（コメントのみ。挙動への影響なし）。
- **試験5本**（h02・h14・b17・r3_07・r4_09）：試行と同一。
- **d5_08**：試行と1箇所だけ異なる。B-4の試験・結果のblob同一性を見る`test_the_b4_runtime_tests_and_result_are_blob_identical_to_the_code_start`で、試行は`points.py`を別の分岐（`assertNotEqual`＋`continue`）にしていたが、これは旧testのassert数（AST）を増やすため、既存の`corrected`分岐に`points.py`を併せる形に直し（`seen_corrected = seen_corrected or path == corrected`）、assert数を開始点と同じにした。ほか、固定リテラル（B17_HUNKS等）の行の並びが異なるが、内容は同じである。
- 新B-5b scopeは試行のdiffを使わず、`test_a5_08_scope`が設計§7.4を直接検査する（Gitの`diff START HEAD`から読む。コミット済みの状態を見る）。固定リテラルは`genpins`相当の再生成で作り、再生成しても差分が出ないことを最終コミットで確認した。

## 7. 限定欠陥注入（`a5_sensitivity.py`、クリーンクローンの3.13）

53変異（依頼書の18項目＝M01〜M18、補助の引数検査M19a〜d）。**検出53、等価0、未検出0、準備失敗0**。コントロール（無変異）は143＋12件が失敗0。分類は、OWN＝新パッケージ自身の判断、GUARD＝B-1検査器など既存ランタイムの独立防護、SPY＝委譲のspy。OWN 36、GUARD 16、SPY 1。

| ID | 分類 | 結果 | 内容 | 失敗した試験数 |
|---|---|---|---|---|
| M01 | GUARD | DETECTED | the chain view accepts an adoption record without checking it | 82 |
| M02 | GUARD | DETECTED | the state_after of the adoption record is not compared with the parent's | 4 |
| M03a | GUARD | DETECTED | discarded_from_seq may differ from the record's own seq | 3 |
| M03b | GUARD | DETECTED | claimed_schema_version 1 is allowed | 1 |
| M04a | GUARD | DETECTED | raw_size 0 is allowed | 3 |
| M04b | GUARD | DETECTED | a bool raw_size is allowed | 1 |
| M04c | GUARD | DETECTED | a bool claimed_head_seq is allowed | 1 |
| M05 | GUARD | DETECTED | the evidence of the basis is not compared with the record's | 1 |
| M06a | GUARD | DETECTED | the request hash is not checked | 6 |
| M06b | GUARD | DETECTED | the reason code is checked on the basis only | 3 |
| M07 | GUARD | DETECTED | the adoption record does not claim its request id (a reused id is not seen) | 9 |
| M08a | GUARD | DETECTED | B-1: a restore before the last adoption record is not refused | 5 |
| M08b | GUARD | DETECTED | B-4: a restore point before the last adoption record is not refused | 4 |
| M08c | GUARD | DETECTED | B-1: the adoption record itself is refused as the restore point | 2 |
| M08d | GUARD | DETECTED | B-4: the adoption record itself is refused as the restore point | 3 |
| M09 | GUARD | DETECTED | the adoption record is not among the request kinds of the effective chain | 2 |
| M10a | OWN | DETECTED | a VALID file is taken as adoptable | 2 |
| M10b | OWN | DETECTED | schema 1 is not refused | 1 |
| M11 | OWN | DETECTED | adopt_count is not compared with the diagnosis count | 6 |
| M12a | OWN | DETECTED | the migration trace is not judged at all | 8 |
| M12b | OWN | DETECTED | only a readable SCHEMA_MIGRATION counts, the origin is not looked at | 6 |
| M12c | OWN | DETECTED | only an origin counts, a readable SCHEMA_MIGRATION on the discarded side is not looked at | 1 |
| M12d | OWN | DETECTED | the trace is judged also when the prefix keeps its migration | 1 |
| M13a | OWN | DETECTED | only the effective chain of the prefix is looked at for taken ids | 2 |
| M13b | OWN | DETECTED | the readable ids of the discarded side are not looked at | 2 |
| M13c | OWN | DETECTED | the ids of the prefix are not looked at | 8 |
| M14a | OWN | DETECTED | claimed_head_seq is the verified head_seq of the diagnosis | 25 |
| M14b | OWN | DETECTED | the parent_hash is the parent's parent | 85 |
| M14c | OWN | DETECTED | state_after is the state of the first record | 83 |
| M14d | OWN | DETECTED | raw_size is one less than the length of the bytes | 55 |
| M14e | OWN | DETECTED | the evidence of the basis is a different (older) copy: discarded_from_seq is off by one | 85 |
| M14f | OWN | DETECTED | the request hash is the hash of the whole basis (with requested_at) | 86 |
| M14g | OWN | DETECTED | the plan's candidate_state_digest is the digest of the whole document | 55 |
| M14h | OWN | DETECTED | the basis diagnosis_digest is the raw hash | 20 |
| M15 | SPY | DETECTED | the candidate is not passed to validate_history (its fields are written by hand) | 4 |
| M16a | OWN | DETECTED | confirm rebuilds but does not compare: the plan's candidate is returned | 2 |
| M16b | OWN | DETECTED | confirm does not rebuild at all: the plan's basis is trusted | 4 |
| M16c | OWN | DETECTED | confirm takes the original bytes by the length only (the hash of the raw bytes is not compared) | 4 |
| M17a | OWN | DETECTED | a re-written (indented) copy of the candidate is NO_CHANGE | 7 |
| M17b | OWN | DETECTED | stale and mismatch are mixed up (other bytes are a mismatch) | 12 |
| M17c | OWN | DETECTED | the plan's hash asked for is not compared with the plan's | 4 |
| M17d | OWN | DETECTED | the plan's own candidate is not checked again (its record may be swapped) | 25 |
| M18a | OWN | DETECTED | basis returns the internal object | 1 |
| M18b | OWN | DETECTED | to_dict returns the internal view | 1 |
| M18c | OWN | DETECTED | the plan says committed | 2 |
| M18d | OWN | DETECTED | the result says committed | 2 |
| M18e | OWN | DETECTED | the plan can be changed | 2 |
| M18f | OWN | DETECTED | the result can be changed | 3 |
| M18g | OWN | DETECTED | the repr prints the whole plan hash | 2 |
| M19a | OWN | DETECTED | bytearray is accepted as data | 2 |
| M19b | OWN | DETECTED | a bool adopt_count is accepted | 2 |
| M19c | OWN | DETECTED | adopt_count 0 is accepted | 3 |
| M19d | OWN | DETECTED | the request id is checked before the instant | 1 |

注：M12dは最初の実行で**未検出**だった（移行を残すprefixで、捨てる側に痕跡があっても採用できる対照が無かった）。そのため`test_a_trace_on_the_discarded_side_does_not_matter_when_the_prefix_keeps_its_migration`（A5-10）を1本足し、再実行で検出を確認した（この1本を含めて新規は155件）。M15（候補を`validate_history`に通さない）は委譲そのものを壊す変異のため、検出した4件はspyによる委譲の試験を含む。そのため分類をSPYとした。

## 8. 解釈した点

- 「捨てる側の痕跡」は、読める`SCHEMA_MIGRATION`、または`origin`が`null`でない辞書（0・空文字・Falseなども痕跡）。**prefixが移行記録を残している場合は判定しない**（設計§5.2）。
- 捨てる側の読めないIDは、IDの重複判定に使わない。prefixの物理履歴のIDは、実効鎖から外れた記録も含めて使う。
- `restore_before_adoption`は「最後の採用記録より前を復元点にできない。採用記録自身は復元点にできる」（B-1・B-4の両方）。
- 試験のscopeは、作業ツリーではなくコミット済みのHEADをc8ba08fと比べる。したがって試験対象SHAの確定後に、結果文書だけを別コミットで足しても、範囲試験は変わらない。
- B-5a結果文書§7の「検査260回」の訂正（前段階の記録。B-5aの文書・コード・試験は変えない）：**失敗するprefix検査が260回であり、prefixの検査は261回、全体検査を含む`validate_history`の呼出しは合計262回**である（B-5aレビュー808ffbdのP-01）。

## 9. push後の確認

push後に保護参照61を再照合し、最後の差分が本文書だけであることを確認した結果は、スレッドの報告に記す（本文書にはpush後の値を書けない）。

## 10. 未実施・逸脱

- **開始時の保護参照照合を、実装の開始前ではなく実装後（push前）に初めて行った**。その間に参照が動いたかどうかは、push前の61／61一致までは分からない。
- **Windows**・ユーザーPC・物理電源断・autocrlf=true・実機のcrlf：未実施。
- 変異試験は、過去B-1〜B-5aの変異を再実行していない（依頼どおり）。
- PR・マージ・Actions・本番・通知・CONSUME・保存・公開・S3-Cは行っていない。依存・設定・workflowは変更していない。
- 作業中の仮コミットに`__pycache__`が混入したため、最終コミットはc8ba08fからの1コミットに作り直した（最終コミットに追跡された`__pycache__`は0件）。


---

# 追記：R-01 限定修正（2026-11-03）

旧結果（上記§1〜§10）は書き換えていない。状態：**R-01の限定修正・自己試験まで完了。レビュー待ち。PR・マージ・Actions・本番・通知・CONSUME・S3-Cには進んでいない。**

## R1. 固定入力・設定

| 項目 | 値 |
|---|---|
| 採用 | Rockyのレビュー結果（重大0・通常1＝R-01）とコーディネーターの依頼で、限定修正依頼案の範囲を実装 |
| モデルの実設定 | get_session：configured_model＝`claude-sonnet-5-5[1m]`、session_context.model＝`claude-sonnet-5-5[1m]`、last_served_model＝`claude-sonnet-5-5`、effort_level＝`high` |
| 固定資料 | 資料ブランチの 92630a3d5233f14900c7472dc754850701a56b61（レビュー docs/reviews/V2_RECOVERY_S3B5B_IMPLEMENTATION_REVIEW_20261103.md、再現コード docs/reviews/s3b5b_review_probe.py、依頼案 docs/tasks/V2_RECOVERY_S3B5B_REVIEW_FIX_REQUEST.md）。読取だけで、このブランチへ追随マージしていない |
| コード開始点 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01（feat/v2-history-adopt-s3b5b-20261103） |
| 修正ブランチ | fix/v2-history-adopt-s3b5b-review-20261103（元ブランチは更新していない） |
| コミット | 修正＋R-01回帰 bad7fbcd6bc2ce30a756ca944b356b991d405e5c、回帰試験の補強 **61659892086b559a4e9c62caedcc79145f0b75dd**（コード・回帰の最終＝**試験対象SHA**） |
| 保存最終SHA | 本追記だけを加える次のコミット（本文書には自分のSHAを書けない。報告で示す） |
| 保護参照 | 依頼案§4の60参照＋資料 5d21c10＋元実装 782debc＝**62参照**を、**修正の開始前**に`git ls-remote`の完全SHAで照合し62／62一致。push後の照合結果は報告に記す |

## R2. 修正の内容

R-01：計画の`discarded`が空辞書・負やboolのcount・adopt_countと違うfrom_index・countとitemsの長さの不一致・不正なitems要素でも、plan_hashを再計算すると候補バイトでNO_CHANGEになり、data=Noneではdataの型のエラーが先に出ていた。

`v2_history_adopt/confirm.py`の計画検査`_form_ok`（dataを読む前、全経路の共通の段）に、診断が返す形だけを受け入れる検査を足した。

- dictのキーは`from_index`・`count`・`items`ちょうど。from_indexは厳密整数でadopt_countと等しい。countは厳密整数で0以上（boolは不可）。itemsはlistで長さがcount。
- 各itemのキーは`index`・`kind`・`seq`・`d`・`request_id`ちょうど。indexは厳密整数でfrom_index＋位置。kindは`?`またはKINDSの値。seqはNoneまたは厳密整数（診断の仕様どおり負も許す）。dはNoneまたは`is_date`を通る値。request_idはNoneまたは`valid_request_id`を通る値。
- 不正は全て`history_plan_mismatch`／`plan`（元バイト・候補バイト・他のバイト・None・型違いのどの経路でも、dataの型を読む前）。
- 追加した名前は既存公開の`v2_history.KINDS`と`v2_history.common.is_date`だけ。新しいモジュール変数・モジュール直下の関数は作らず（既存のaudit試験の制約を変えないため、補助は`_form_ok`の中の入れ子関数にした）、audit試験は`ALLOWED_NAMES`に上記2名を足しただけ。
- 元バイト経路の診断・全basis再構築、候補経路の正規化バイト完全一致だけをNO_CHANGEとする点、staleの扱いは変えていない。元バイトなしでdiscardedの内容やdiagnosis_digestの真偽までは証明しない（形と計画内で分かる整合だけ）。公開API・エラーcode・キー数・保存schema・復元下限は変えていない。

## R3. 差分（782debc→6165989、ランタイムとaudit試験。新規回帰試験は`tests/v2_history_adopt/test_a5_09_review_fix.py`の全文がリポジトリにある）

```diff
diff --git a/tests/v2_history_adopt/test_a5_07_runtime_audit.py b/tests/v2_history_adopt/test_a5_07_runtime_audit.py
index adf9fcb..c56ef3d 100644
--- a/tests/v2_history_adopt/test_a5_07_runtime_audit.py
+++ b/tests/v2_history_adopt/test_a5_07_runtime_audit.py
@@ -15,7 +15,7 @@ ALLOWED_STDLIB = {"copy"}
 ALLOWED_NAMES = {
     "v2_history": {"History", "validate_history", "decode_history", "encode_history", "RECOVERY_PREFIX_ADOPTION",
-                   "SCHEMA_MIGRATION"},
+                   "SCHEMA_MIGRATION", "KINDS"},
     "v2_history.values": {"history_dict"},
-    "v2_history.common": {"is_int", "is_hex64", "basis_request_hash", "same"},
+    "v2_history.common": {"is_int", "is_hex64", "is_date", "basis_request_hash", "same"},
     "v2_history_diagnose": {"diagnose_history_bytes", "PREFIX_ONLY"},
     "v2_history_ops.errors": {"history_request_conflict", "history_plan_mismatch", "history_plan_stale"},
diff --git a/v2_history_adopt/confirm.py b/v2_history_adopt/confirm.py
index 2e384de..4c86df4 100644
--- a/v2_history_adopt/confirm.py
+++ b/v2_history_adopt/confirm.py
@@ -5,6 +5,6 @@ whole plan is rebuilt and compared (CONFIRMED_IN_MEMORY), or the bytes are the c
 (NO_CHANGE), or they are something else (history_plan_stale). A plan is trusted for nothing it states about itself."""
 from v2_core.errors import CoreError
-from v2_history import History, RECOVERY_PREFIX_ADOPTION, encode_history, validate_history
-from v2_history.common import is_hex64, is_int, same
+from v2_history import KINDS, History, RECOVERY_PREFIX_ADOPTION, encode_history, validate_history
+from v2_history.common import is_date, is_hex64, is_int, same
 from v2_history.values import history_dict
 from v2_history_diagnose import diagnose_history_bytes
@@ -23,5 +23,24 @@ _HASH_KEYS = ("raw_sha256", "diagnosis_digest", "prefix_head_hash", "prefix_stat
 
 def _form_ok(basis):
-    """The shapes of the plan's own values (design 5.5 step 1), before anything is rebuilt."""
+    """The shapes of the plan's own values (design 5.5 step 1), before anything is rebuilt. The discarded part is checked in
+    the form the diagnosis gives (design 5.4: the fixed keys, strict integers, the start at adopt_count, as many items as
+    the count says, each with its position, a kind of the fixed list or "?", a strict integer or None, a real day or None
+    and a request id of the fixed form or None). Only what the plan itself proves: its content is not proved here, and a
+    declared seq may be any integer, even a negative one."""
+
+    def item_ok(item, index):
+        return (isinstance(item, dict) and set(item) == {"index", "kind", "seq", "d", "request_id"}
+                and is_int(item["index"]) and item["index"] == index and (item["kind"] == "?" or item["kind"] in KINDS)
+                and (item["seq"] is None or is_int(item["seq"])) and (item["d"] is None or is_date(item["d"]))
+                and (item["request_id"] is None or valid_request_id(item["request_id"])))
+
+    def discarded_ok(part):
+        if not isinstance(part, dict) or set(part) != {"from_index", "count", "items"}:
+            return False
+        start, count, items = part["from_index"], part["count"], part["items"]
+        return (is_int(start) and start == basis["adopt_count"] and is_int(count) and count >= 0
+                and isinstance(items, list) and len(items) == count
+                and all(item_ok(item, start + at) for at, item in enumerate(items)))
+
     return (basis["operation"] == OPERATION and basis["status"] == READY and basis["reason_code"] == REASON
             and valid_request_id(basis["request_id"]) and is_requested_text(basis["requested_at"])
@@ -31,5 +50,5 @@ def _form_ok(basis):
             and is_int(basis["prefix_head_seq"]) and basis["prefix_head_seq"] >= 0
             and is_int(basis["candidate_head_seq"]) and basis["candidate_head_seq"] >= 0
-            and isinstance(basis["discarded"], dict) and isinstance(basis["candidate_history"], dict)
+            and discarded_ok(basis["discarded"]) and isinstance(basis["candidate_history"], dict)
             and isinstance(basis["candidate_record"], dict))
 
```

変更したファイル：`v2_history_adopt/confirm.py`、`tests/v2_history_adopt/test_a5_07_runtime_audit.py`（ALLOWED_NAMESの2名）、`tests/v2_history_adopt/test_a5_09_review_fix.py`（新規、206行）。その他は782debcとblob同一（`git diff --stat 782debc 6165989`は3ファイルのみ）。

## R4. 追加した試験（test_a5_09_review_fix.py、新規15件）

| クラス | 件数 | 内容 |
|---|---|---|
| BrokenBlock | 10 | 34通りの不正を1つずつ壊し、元バイト・候補バイト・他のバイト・None・str・bytearrayの6経路でmismatch（204サブケース）。レビューの再現（空辞書・hash再計算済み）。壊れたblockではdataの型より先にmismatch。正常なblockはdataの型が先。形は正しいが内容が違うblockは、元バイトでmismatch、候補バイトでは形しか見ないのでNO_CHANGE（限界を明記）。正常な計画の他のバイトはstale。hashを再計算しない改ざんはmismatch。fromが adopt_count と違うがitemsは整合する例、itemsが空だがlistでない例 |
| ShapesTheDiagnosisGives | 5 | 診断が実際に返す形が拒否されない対照：header-onlyの破損でcount＝0・items＝[]、複数itemsの連番、null読取値・負のseq・未知kind`?`、移行済みprefixと復元を含むprefix、KINDSの全種別 |
| 計 | 15 | BrokenBlock 10＋ShapesTheDiagnosisGives 5 |

新規パッケージの合計は旧155＋15＝**170**。

## R5. 結果（Linux 6.18、`unshare -n -r`下、別クリーンクローン・core.autocrlf=false、試験対象6165989）

版：3.10.20（uvの単体インタプリタ）、3.11.18、3.12.3、3.13.18。各版は別のクリーンクローンで`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`。4版とも全スイートのrc＝0、失敗0、error0。

| スイート | 件数 | 結果 |
|---|---|---|
| v2_core／v2_persistence／v2_persistence_local／v2_recovery／v2_history／v2_history_ops／v2_history_restart／v2_history_restore／v2_history_diagnose | 197／170／113／176／230／173／109／165／131＝**1464** | OK。1460合格＋Windows専用4 skip（旧と同じ） |
| v2_history_adopt | **170**（旧155＋新15） | OK、skip 0 |
| 合計 | 1634 | 1630合格＋4 skip |

- 通信遮断：Linuxの`unshare -n -r`は使えた（OS単位）。試験内のプロセス内socket禁止は別。`unshare`なしの3.13でも新規170件OK。
- 付属プローブ（`s3b5b_review_probe.py --expect-fixed`、3.13クリーンクローン）：**終了0**。R-01の観測19件が解消（fixed 19、unfixed 0）、正常な結果の対照6／6、元バイトでの拒否14／14、prefix格子56／56合格。
- **Windows・ユーザーPC・物理電源断・autocrlf=true：未実施**（他者の結果で代用していない）。

## R6. 感度確認（元の53変異の再実行はしていない）

修正を外す変異16件を、新しい回帰試験だけで確認（`confirm.py`の1箇所を壊す）。

- 修正前コード（782debcの`confirm.py`）に回帰試験を当てると、**177件失敗**（R-01を検出）。
- 検出15、**等価1**、未検出0：A（blockがdictなら通す）、B（from_index＝adopt_count の検査を省く）、C（長さの検査を省く）、E（indexの位置検査を省く）、F（kindの検査を省く）、G（dの検査を省く）、H（request_idの検査を省く）、I（bool seqを許す）、J（負のseqを拒否する）、K（itemのキー検査を省く）、L（blockのキー検査を省く）、M（itemsがlistの検査を省く）、N（countが0を拒否する）、O（未知kind`?`を拒否する）、P（null読取値を拒否する）。
- **等価（D：`count >= 0`を省く）**：countは厳密整数で`len(items) == count`が必要であり、listの長さは負にならないため、`count >= 0`を省いても受理される入力は変わらない（`count＝-1`と`items＝[]`は長さ0≠-1で拒否される）。反例は見つからず、検査は多重防護として残した。
- 最初の実行ではB・D・Mが未検出で、B・Mには「itemsは整合するがstartが違う」例と「itemsが空でlistでない」例の回帰を足し、検出を確認した。Dのみ等価と判断した。

## R7. 解釈した点・未実施

- 診断の仕様どおり、捨てる側のseqは不正な宣言値でも厳密整数なら負を許す。claimed_head_seqなど他の宣言値からcountやitemsを制約していない。
- 本修正は、元バイトがない経路でdiscardedの記述内容の真偽やdiagnosis_digestの真偽を証明するものではない（形と計画内の整合だけ）。hashの一致を作成者の真正性の証明として扱わない。
- 旧結果§10の開始時の保護参照照合の欠落は、今回の照合で補ったことにしない（今回は修正の開始前に照合しただけ）。
- 未実施：Windows、ユーザーPC、Python 3.10〜3.13以外、autocrlf=true、物理電源断。PR・マージ・Actions・本番・通知・CONSUME・S3-C。
