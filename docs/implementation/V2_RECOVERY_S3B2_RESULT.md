# V2 復旧 S3-B-2 限定実装 結果記録

版：1.0／2026-10-30
対象：B-2（履歴の有効鎖の台帳投影・日次の候補・解決計画・バッチ値）。メモリ上の純粋関数だけ。保存・公開・解錠・本番・B-3以降は実装していない。

## 1. 版・設定

| 項目 | 値 |
|---|---|
| 実行モデル・effort | `claude-sonnet-5-5[1m]`、effort `high`（セッション情報の `session_context.model`／`effort_level`、`last_served_model=claude-sonnet-5-5` で確認）。モデル別の利用量は未計測 |
| 採否 | U-1 API-1、U-2 R-a、U-3 Sonnet 5.5 high（採用・着手の記録：資料ブランチ `docs/v2-history-s3b2-adoption-20261030`＝`9b290e7a25144dccd9aa1ffee5664f47ad924b5d`） |
| 設計・依頼（第2版） | `e083cd3187f17692cb081fcc1031b09551fb8cb7`（docs/v2-history-s3b2-revision-20261030）。設計blob `988258c798ee2d867c86238db1c4f426a360dda2`、依頼blob `ab65b43704182a5416f5dbf935468da6239462fc` |
| 開始（コード基準）SHA | `adfdf765aeca0d01c8f10b596a6fac59d7c1a07e`（fix/v2-history-s3b1-review-20261030） |
| 試験対象SHA（コードの最終） | `3b6c21cb5f7769d425fc01ac01498310695a1572` |
| 結果だけの最終SHA | 本書だけを足した最後のコミット（値は完了報告に記す。本書は自分のSHAを含められない） |
| 実装ブランチ | `feat/v2-history-s3b2-20261030` |

試験対象SHAと結果だけの最終SHAの差は本書1ファイル（`docs/implementation/V2_RECOVERY_S3B2_RESULT.md`）だけである。

## 2. 追加・変更したファイル

| 場所 | 区分 |
|---|---|
| `v2_recovery/facts.py` | 新規（API-1のA1）。`FixedApply`、`FixedFacts.from_parts`、`LedgerContext(.from_facts)`、`facts_invalid` |
| `v2_recovery/commands.py` | 変更（A2・A3）。差分の全文は§3 |
| `v2_history_ops/` | 新規：`__init__.py`、`errors.py`、`values.py`、`chain.py`、`read.py`、`batch.py`、`daily.py`、`plan.py` |
| `tests/v2_history_ops/` | 新規：`ho_helpers.py`、`s3a_golden.py`、`test_b02`〜`test_b17`の9ファイル（156件）、`sensitivity_check.py` |
| `docs/implementation/V2_RECOVERY_S3B2_RESULT.md` | 新規（本書） |

上記以外の既存ファイル・既存の試験・fixtures・`__init__.py` の差分は0（B2-17が `git diff` で検査）。

## 3. v2_recoveryの差分（A2・A3の全文）

`git diff adfdf76 -- v2_recovery/commands.py`

```diff
@@ -101,10 +101,14 @@ def _check_late(ctx, cmd, existing):
         ap = ctx.sv.by_seq.get(ref["seq"])
         if ap is None or ref["event_hash"] != ap.event_hash or d not in ap.skipped:
             raise _fail("late_missing_ref")
-    else:
+    elif "resolution_seq" in ref:                   # S3-A reference: resolution_seq / resolution_hash
         if not any(rec["kind"] == KIND_DECLARE and rec["resolution_seq"] == ref["resolution_seq"]
                    and rec["resolution_hash"] == ref["resolution_hash"] and rec["d"] == d for rec in existing):
             raise _fail("late_missing_ref")
+    else:                                           # v2 reference: seq / event_hash of an effective declaration
+        if not any(rec["kind"] == KIND_DECLARE and rec["seq"] == ref["seq"]
+                   and rec["event_hash"] == ref["event_hash"] and rec["d"] == d for rec in existing):
+            raise _fail("late_missing_ref")
     rows = _rows_of(ctx, cmd)
@@ -146,8 +150,10 @@ def _check_declare(ctx, cmd, declared_dates, rem0):
-def make_records(ctx, existing, commands, basis, request_hash):
-    """Evidence for all commands, then the new records (not yet hashed into a set)."""
+def check_commands(ctx, existing, commands):
+    """Evidence for all commands. Returns one (frontier, session_context) per command ((None, None) for an ACK).
+
+    ctx is a project.Ctx or a facts.LedgerContext; existing are the records already in effect."""
     sv = ctx.sv
     ...(本文は無編集)
         extras.append(extra)
+    return extras
+
+
+def make_records(ctx, existing, commands, basis, request_hash):
+    """Evidence for all commands, then the new records (not yet hashed into a set)."""
+    sv = ctx.sv
+    extras = check_commands(ctx, existing, commands)
     prev_hash = existing[-1]["resolution_hash"] if existing else None
```

`...(本文は無編集)` は表記の省略で、`git diff -U0` では本文の行は差分に出ない（B2-17の `test_commands_py_changes_are_the_two_allowed_ones_only` が、削除行が上の3行だけであることを確かめる）。`facts.py` は新規212行。

## 4. 公開API・値の形

`v2_history_ops.__all__`（20名）：`read_effective`、`project_history_ledger`、`prepare_history_day`、`prepare_history_resolution_plan`、`confirm_history_resolution_plan`、`check_append_batch`、`HistoryAppendBatch`、`EffectiveView`、`HistoryLedger`、`HistoryDayResult`、`HistoryResolutionPlan`、`HistoryResolutionConfirmResult`、定数 `PREPARED`／`NO_COMMIT`／`ALREADY_APPLIED`／`READY`／`NO_CHANGE`／`CONFIRMED_IN_MEMORY`／`DAILY`／`RESOLUTION`。

- 計画のbasis（19キー）：`operation`（`soxl-v2-history-resolution-plan/1`）、`status`、`history_digest`、`expected_head_seq`、`expected_head_hash`、`request_id`、`request_hash`、`requested_at`、`check_d`、`reason_code`、`ledger_digest`、`sessions_digest`、`commands`、`candidate_history`、`candidate_digest`、`expected_state_digest`、`excluded_fingerprints`、`supplemented`、`effective_digest`。`plan_hash`＝SHA-256(正規化JSON(basis))。記録は `plan_hash` を持たない。
- バッチ（`{body, batch_hash}`）のbody（13キー）：`operation`（`soxl-v2-history-append-batch/1`）、`source`（DAILY／RESOLUTION）、`d`、`request_id`、`plan_hash`、`expected_head_seq`、`expected_head_hash`、`expected_history_digest`、`records`、`candidate_head_seq`、`candidate_head_hash`、`candidate_digest`、`candidate_state_digest`。`batch_hash`＝SHA-256(正規化JSON(body))。記録は `batch_hash` を持たない。
- 固定のエラー：`history_invalid`（rule：`plan_shape`、`json_depth`、`json_number`、`json_type`）／`history_request_conflict`（request_id）／`history_plan_mismatch`（plan）／`history_plan_stale`（plan）／`batch_invalid`（rule：`type`、`batch_shape`、`batch_hash`、`json_*`、`records`、`seq`、`source`、`candidate_digest`）／`batch_stale`（head）／`facts_invalid`（facts、rule）。その他は既存のエラー（`resolution_invalid`、`ledger_mismatch`、`late_observation`、`target_not_after_boundary` など）をそのまま返す。
- `committed` は常にFalse。`HistoryDayResult`／`HistoryResolutionConfirmResult` の `committable` もFalse。どの値も `AppendPlan` ではなく、`MemoryStore.commit`・`LocalFileStore.commit` は `snapshot_invalid`／`plan_type` で拒否する（B2-16で11種の値を直接渡して確認）。

## 5. 受入とテスト名の対応

新規は `tests/v2_history_ops/` の156件（unittest）。

| 受入 | ファイル：クラス | 件数 |
|---|---|---|
| B2-01 既存回帰 | §6の既存スイート（無編集）＋B2-17の差分検査 | — |
| B2-02 API-1の回帰 | `test_b02_api1_regression.py`：S3AUnchanged、FactsShape、LedgerContextOrder、SameDecisionsAsTheS3AContext、LateReferenceForms | 24 |
| B2-03 読取と参照写像 | `test_b03_read_refs.py` | 13 |
| B2-04 全区間と現在区間（例V）／B2-05 投影の順序と規則／B2-06 セッション範囲 | `test_b04_b06_projection.py`：ExampleV、OrderAndRules、SessionRanges | 23 |
| B2-07 日次の結果／B2-08 再実行の不変条件／B2-09 再開始後の日次 | `test_b07_b09_daily.py`：GenesisOnly、ResultTable、Delegation、RerunInvariant、AfterRestart | 21 |
| B2-10 復元後（例R・R-b）／B2-11 移行済み（例M） | `test_b10_b11_restore_migrated.py`：ExampleR、ExampleRB、ExampleM | 13 |
| B2-12 新規解決の証拠／B2-13 request_id | `test_b12_b13_evidence_requests.py`：Evidence、RequestIds | 14 |
| B2-14 計画と確認 | `test_b14_plan_confirm.py`：PlanBinding、StaleAndInvalidInputs、BranchesAB、WholeCandidate | 15 |
| B2-15 バッチ値／B2-16 型・不変性・秘匿 | `test_b15_b16_batch_values.py`：Creation、CheckAppendBatch、Types、Immutability、Secrecy、StoresRefuseEveryValue | 23 |
| B2-17 範囲と停止 | `test_b17_scope.py`：Imports、NoSideEffects、FilesChanged | 10 |
| 合計 | | 156 |

B2-16のLocalFileStoreの一時rootは `durability="file_sync_only"`（`StoresRefuseEveryValue`）。

## 6. 実行結果

条件：core.autocrlf=falseの別クリーンクローン（`feat/v2-history-s3b2-20261030` を単一ブランチで取得、HEAD＝試験対象SHA、作業ツリーに差分0）。各スイートを `-B -W error::ResourceWarning -m unittest discover` で実行。OS：Linux（6.18、x86_64）。

| 区分 | Python | コア197 | 保存ドメイン170 | S2 113 | S3-A 176 | B-1 230 | 新規N 156 |
|---|---|---|---|---|---|---|---|
| unshare -rn（OSレベルの通信遮断）＋プロセス内socket禁止 | 3.10.20（uv単体） | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.11.17 | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.12.3 | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.13.17 | OK | OK | OK（skip 4） | OK | OK | OK |
| プロセス内socket禁止のみ（unshareなし） | 3.13.17 | OK | OK | OK（skip 4） | OK | OK | OK |

全5構成×6スイート＝30実行で failures=0、errors=0、終了コード0。S2の113件はLinuxで109合格＋4 skip（Windows専用の4件は非対象）で、契約どおり。既存スイートは1行も編集していない。新規Nの集計は既存と分けた。OSレベルの遮断（unshare）は、新規ヘルパーとテスト実行全体にかかる別の層であり、プロセス内の `socket` 差し替えとは区別して記録した（`unshare -rn` 内で `connect` が `Network is unreachable` になることも別に確認）。

未実施：Windows（実機・環境なし）、ユーザーのPC、物理電源断、`core.autocrlf=true`。ユーザーや主担当の環境の確認件数は、この表に含めていない。

## 7. B2-02：API-1の回帰

- 固定ゴールデン：変更前（基準adfdf76）と変更後で、S3-Aの出力（有効台帳digest、`make_records`、plan_hash など14点）のhashが一致（`s3a_golden.py`、基準値は `test_b02` に固定）。
- 目印：S3-Aの欠陥注入スクリプトの全目印（各 `old` 文字列）が、変更後のv2_recoveryにちょうど1回ずつ現れる。静的に数え上げて63件（試験は55件以上を要求）で、全件1回（`test_b02`）。
- commands.pyに関係する変異（M06、M08a、M12、M14、M17〜M19、M29〜M35、M38、M39）を、既存の `tests/v2_recovery/sensitivity_check.py` で再実行した：16変異のうち14件は元どおり検出、M18・M31の2件は元どおり等価（理由も元と同じ）。判定の変化0。
- 既存S3-A 176件とB-1 230件は無編集で合格（§6）。

## 8. 例V・R・R-b・Mでの実測

日付は合成セッション（D1＝2026-03-03、D2＝03-04、…）。F&G値などは合成fixtureで、市場の実測ではない。

| 例 | 有効記録 | 照合で止まる／結果 | frontier／日次 |
|---|---|---|---|
| V（0 GENESIS／1 APPLY D1／2 DECLARE D2 q1／3 RESTART_UNKNOWN resume D3 q2） | 0,1,2,3（退避なし）。境界は再開始#3（after＝D3） | D1の決定が別版：`ledger_mismatch`（旧区間APPLYも照合）。D2・D3の日次：`target_not_after_boundary` | DECLARE(D4)のfrontier＝D3（境界）。D4の日次：PREPARED、親＝#3、再実行：ALREADY_APPLIED。batch_hash `0eaa9bb9…a36c9` |
| R（RESTORE 3回後） | 有効 0,1,2,18,19〜22。退避 3〜17。有効な解決記録なし | RESTORE#3後の投影：`decision_conflict`（退避したACK#5・#9は使わない）。未使用q7のACK/ADDED(D3,#19)：READY→CONFIRMED_IN_MEMORY、seq23、親＝#22。q4・q2は `history_request_conflict`。#4・#8を指すと `ack_evidence` | D7の日次（q7のACK後）：PREPARED、親＝#23、再実行：ALREADY_APPLIED。q7のplan_hash `5741403a…5e80`、batch_hash `896bdba3…c921` |
| R-b | 有効 0,1,6,7,8,9。宣言は#8（REPLAYED、元は#4） | D3の後発：`late_observation`。LATE(missing_ref＝DECLARE #8)：受理。#4を指すと `late_missing_ref` | APPLY型（#9）の参照も受理。batch_hash `5e8fea95…1c677` |
| M（移行済み） | 0〜7（退避なし）。applies＝v2 seq 1,3,5。解決記録3件はすべてMIGRATED | 移行後の投影は通る。ACK/CHANGED(D2, v2 seq3)：READY、seq8、親＝#7、origin＝null。v1のseq・hashを渡すと `ack_evidence`。q1〜q3は常に `history_request_conflict` | DECLARE(D5)のfrontier＝D4（2026-03-06）。次の日（D6）：skipped＝[D5]。`migrated_sources` は候補でも元のv1 SnapshotとSetのdigestを返す。batch_hash `fae1046e…6fdd` |

hashの全値は試験の中で再計算でき、本書の値は上記の合成入力・固定時刻（`WHEN`＝2026-06-01T00:00Z）での実測。

## 9. 欠陥注入（`tests/v2_history_ops/sensitivity_check.py`、依頼§6の22件）

26変異（22件のうち複数の壊し方を持つ項目は a／b／c）。作業ツリーのコピーに1件ずつ入れ、新規Nを実行：**検出25、等価1、未検出0、準備失敗0**。所要約4分。

| 項目 | ID | 結果 |
|---|---|---|
| 1 物理配列のACK／DECLARE | B01 | 検出 |
| 2 現在区間のAPPLYだけ | B02 | 検出 |
| 3 退避した宣言を入れ再生を落とす | B03／B03x | B03：検出（解決記録として）。B03x（`FixedFacts.declares` だけ）：等価（宣言のsession_contextは保存範囲の照合にしか使われず、再生した宣言は元と同じ文脈で、前後のAPPLYが同じセッションを比べる） |
| 4 一時S1 seq | B04 | 検出 |
| 5 境界セッション照合なし | B05 | 検出 |
| 6 check_d ≤ 境界を受理 | B06 | 検出 |
| 7 latest_apply_dayが境界を無視 | B07 | 検出 |
| 8 v2のLATE参照でevent_hashを比べない | B08 | 検出 |
| 9 日次APPLYの親が物理先頭でない | B09 | 検出 |
| 10 候補をvalidate_historyに通さない | B10a（batch）／B10b（plan） | 検出 |
| 11 日次の候補を全区間の投影に通さない | B11 | 検出（等価ではない） |
| 12 計画で候補の投影を省く | B12 | 検出（設計§12.7の6） |
| 13 証拠の前に既存の投影を完成させる | B13 | 検出 |
| 14 request_idを有効鎖だけで照合 | B14 | 検出 |
| 15 MIGRATEDをNO_CHANGE | B15 | 検出 |
| 16 plan_hash／入力digest／再構築の比較を無視 | B16a／b／c | 検出 |
| 17 不正な入力をstale化 | B17 | 検出 |
| 18 同じ計画の再確認をstale化 | B18 | 検出 |
| 19 期待先頭を比べない | B19 | 検出 |
| 20 候補digestを比べない | B20 | 検出 |
| 21 入れ子の参照の共有 | B21a（EffectiveView）／B21b（plan.basis） | 検出 |
| 22 ADDEDの元行判定が前のコマンドまでだけ | B22 | 検出（一方の並べ順が失敗） |

全市場のグリッドや過去の機能の欠陥注入は再実行していない（B2-02のcommands.pyの変異を除く）。

## 10. 解釈した点・設計との差

- 日次・解決計画の「親」は常に物理先頭（ACK／DECLARE／RESTORE／SCHEMA_MIGRATIONが先頭でも受理）。設計§7.3どおり。
- 再開始後だけでなく全区間で、境界以前のD・check_dを `target_not_after_boundary` とした（設計§13の表どおり）。
- `FixedFacts.declares` は保存範囲の照合だけに使い、LATE参照の解決は `chain.resolutions`（有効鎖）で行う。そのため欠陥B03xは等価と判断した。これは設計の「再生した宣言の値を使う」を満たす別の経路であり、設計からの変更ではない。
- HistoryAppendBatchの `from_dict` が許すのはJSONの深さ・数値・型の検査だけで、意味の検査（整数欄のbool・float）は `check_append_batch`／確認の手順1に置いた（設計§12.8の2の段階分けのとおり）。
- 試験の組立て：例Vなど不足する履歴は `tests/v2_history_ops/ho_helpers.py` に書き、既存の `h_helpers.py` は読取りだけでimportした。`ho_helpers.py` は既存ファイルではなく新規。
- 実装中に、`__pycache__` を誤ってコミットに入れたため、未pushのブランチ上で履歴を書き換えて除いた（push前のため、リモートの参照は影響を受けない）。

## 11. 範囲・停止

B-2はメモリ上の投影、日次の候補、解決計画、バッチ値であり、保存・公開（CAS）・ロック・解錠・本番接続・B-3（再開始の計画）・B-4（復元の計画、CONSUME）・B-5（破損診断）・S3-C・HistoryReplacement・v2用ストア・通知は実装していない。PR、マージ、Actions、本番の変更、通知・Discord・Sheets送信、口座・API契約は行っていない。受入IDのうち、S3-Cの公開・実行に関わるRT-03・RT-05・RT-07は達成済みと書かない。

保護参照40件（作成依頼§6の34、資料ブランチ、設計・依頼の各版、採用記録）の照合は、開始時と終了時を別に行った。開始時＝2026-10-30T06:17:45Z に40/40一致。終了時の結果は完了報告に記す。結果を保存したので、B-3以降・S3-Cへは進まず、ここで停止する。

---

# 12. 受領レビュー（R-01〜R-03）への限定修正 追記

追記日：2026-10-30。上の§1〜§11は元の記録として残す。訂正がある箇所は、この§12に訂正元と根拠を示す。

## 12.1 版・設定

| 項目 | 値 |
|---|---|
| 実行モデル・effort | `claude-sonnet-5-5[1m]`、effort `high`（セッション情報で確認。モデル別の利用量は未計測） |
| 入力 | 修正依頼 `docs/tasks/V2_RECOVERY_S3B2_REVIEW_FIX_REQUEST.md`、レビュー `docs/reviews/V2_RECOVERY_S3B2_REVIEW_20261030.md`、再現コード `docs/reviews/s3b2_review_reproduce.py`（資料ブランチ `docs/v2-history-s3b2-receipt-20261030`＝`bd59d456cd33108e97428036a665664c04b802b5`）。修正指示はユーザー（Rocky）のレビュー報告と、これに従う旨のコーディネーター経由の依頼 |
| 修正の開始SHA | `132a3392115e44105895ecea92e472b49107fed3`（コード・試験は `3b6c21c…` と同じ） |
| 修正ブランチ | `fix/v2-history-s3b2-review-20261030`（元の `feat/v2-history-s3b2-20261030` は更新していない） |
| 試験対象SHA（コード＋試験の最終） | `4ed0c364bcc1c63b44be07349880b741936d8b77` |
| 保存最終SHA | 本節だけを足した最後のコミット（値は完了報告に記す） |

試験対象SHAと保存最終SHAの差は、本書1ファイルの追記だけ。

## 12.2 指摘への対応

| ID | 対応 | 変更箇所 |
|---|---|---|
| R-01 | `HistoryAppendBatch.batch_hash` を常に独立した写し（`copy.deepcopy`）で返す。from_dictの受理範囲、`check_append_batch` の固定エラー（`batch_invalid`／`batch_hash`）、batch_hashの算出規則は不変 | `v2_history_ops/batch.py` 1行 |
| R-02 | `FixedApply` を不変化：属性の代入・削除は `AttributeError`、`__slots__` で `__dict__` なし、`context` と `decision_cols()` は深いコピー、`stored_sessions` は読むたびに新しい `SessionList`（Sessionは凍結dataclass）、`skipped` は tuple。`FixedFacts` も同様：代入・削除は `AttributeError`、`applies` は不変なFixedApplyのtuple、`by_seq` は書込みのない読取専用ビュー（`_ReadOnlyMap`）、`apply_days`／`fixed_fps` は frozenset、`declares`／`boundaries` は読むたびに深いコピー。`from_parts` は入力を従来どおりコピー。公開名・正常値・`latest_apply_day`／`decision_cols` は従来どおり | `v2_recovery/facts.py`（212→292行） |
| R-03 | B03xの「等価」は誤り。反例（0 GENESIS D0／1 APPLY D1／2 DECLARE D2 q1／3 RESTORE 復元点#1・#2 DROP q2／4 RESTART_UNKNOWN resume D4 q3、有効seq 0,1,3,4、D2のclose_atだけ変更、check_d＝D5）を回帰試験に固定し、`sensitivity_check.py` のB03xのEQUIVALENT指定と理由を訂正 | `tests/v2_history_ops/test_s3b2_review_fix.py`（R03RetiredTrailingDeclaration）、`sensitivity_check.py` |
| P-01（提案） | 結果文書§4の訂正：`committable` を持つのは `HistoryDayResult` だけ。`HistoryResolutionConfirmResult` は `committed`（常にFalse）と `state_unchanged`（常にTrue）を持ち、`committable` はない（レビューのとおり。実装追加はしていない） | 本節の文言のみ |

`v2_recovery/commands.py` の差分は追加0（`132a339` と同一）。S3-Aのgolden14点と目印63件は維持（`test_b02` 合格）。

## 12.3 旧コードでの確認

1. 同梱再現コード（旧コード `132a339`、通常実行）：R-01/R-02の7観測がすべてISSUE、対照5件OK、R-03反例はDISTINGUISHED（終了0）。
2. 修正後（`--expect-fixed`、`4ed0c36` のクリーンクローンで実行）：7観測すべてFIXED、対照5件OK、R-03反例DISTINGUISHED、終了0。再現コードの私有属性には合わせていない。
3. 新規回帰 `test_s3b2_review_fix.py`（17件）を旧コードの作業ツリーに当てると、28件が失敗（R-01の2サブテスト、FixedApply・FixedFactsの代入／削除／コンテナ／コピー、レビューの再現シナリオ）。R-03の3件は製品の挙動に対する試験なので旧コードでも合格し、変異側で失敗する（§12.4）。
4. 正常な値は修正前と同じ：R・V・Mの例のplan_hash、batch_hash、投影digestの9個を修正前コードで取り、試験に固定した（`PinnedValuesDoNotChange`）。

R-02の欠けた決定の再現（`facts.applies.clear()` 後の `resolve_core` が成功へ変わる）は、修正後は `clear()` が拒否され、`ledger_mismatch` のまま。

## 12.4 限定感度確認

| 範囲 | 結果 |
|---|---|
| R-01/R-02の修正を1件ずつ戻す（`review_fix_sensitivity.py`、F01〜F13） | **13件すべて検出**（未検出0、準備失敗0）。最初にF13が未検出だったため、`declares`／`boundaries` のコピーを実値で比べるよう試験を補強してから13/13にした |
| B03x（実際の置換：`FixedFacts.declares` の元を物理配列の `replay_of` なしの宣言全部にする） | **検出**。失敗するのは新規回帰のR03の2件だけ（`session_context_mismatch`＝試験側ではERROR、declaresの空の検査＝FAIL）。文字列・ASTの違いではなく実行結果で検出 |
| 実装差分で目印が変わるB-2の既存変異を再実行：B05、B06、B07（`facts.py`）、B04、B08、B22（同じ機能の近傍） | すべて検出（B07は`facts.py`の私有名への変更に合わせてパターンを更新。変異の意味は同じ） |

**変異の合計と件数の訂正**：スクリプトの一覧は**27変異**（B03とB03xを別に数える）。元の§9の「26変異、検出25・等価1」は数え間違いで、元の実行結果を一覧の行に当てると**検出26・等価1（B03x）**だった。B03xを「検出」へ訂正した結果、**27変異のうち、検出27・等価0**となる。ただし、この合計のうち今回**再実行したのは7件**（B03x、B04、B05、B06、B07、B08、B22）で、すべて検出。**再実行していない20件（B01、B02、B03、B09、B10a、B10b、B11〜B15、B16a〜c、B17〜B20、B21a、B21b）は元の実行結果（§9の検出）のままで、今回の実行済みとは数えない。** `commands.py` に追加差分がないため、過去の16変異の全再実行はしていない。

## 12.5 回帰件数・環境

core.autocrlf=falseの別クリーンクローン（HEAD＝`4ed0c364…`）、`-B -W error::ResourceWarning`。Linux 6.18。

| 区分 | Python | コア197 | 保存ドメイン170 | S2 113 | S3-A 176 | B-1 230 | 新規N 173 |
|---|---|---|---|---|---|---|---|
| unshare -rn＋プロセス内socket禁止 | 3.10.20（uv単体） | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.11.17 | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.12.3 | OK | OK | OK（skip 4） | OK | OK | OK |
| 同上 | 3.13.17 | OK | OK | OK（skip 4） | OK | OK | OK |
| プロセス内socket禁止のみ | 3.13.17 | OK | OK | OK（skip 4） | OK | OK | OK |

failures=0、errors=0、終了コード0（5構成×6スイート）。新規Nは156→173件（R-01/R-02/R-03の回帰17件を追加）。既存スイートは1行も編集していない。

**途中の失敗（記録）**：最初の修正案は `types.MappingProxyType` を使ったため、既存S3-Aの `test_c14_scope_and_stop.test_imports_are_limited`（v2_recoveryのstdlib import許可リスト）が全5構成で1件失敗した（コミット `d80df8c`）。既存の試験は編集せず、自前の読取専用ビューへ変更して `import types` をなくし、`4ed0c36` で全合格にした。この失敗は新規Nだけの実行では見つからず、既存スイートを含む全マトリクスで見つかった。

未実施：Windows（実機なし。レビュー側のWindows/Python 3.12.14での566件合格は主担当の確認であり、この表に含めていない）、ユーザーのPC、物理電源断、`core.autocrlf=true`。

## 12.6 解釈した点

- 「再帰的に不変な値」は、`FixedApply` を不変クラス、構造化アクセサをコピーとして実現した。`applies` と `by_seq` が返す `FixedApply` は同じ不変オブジェクトを共有する（書き換えられないため）。
- `LedgerContext` 自体の属性（`sv`、`rows`、`sl` など）は依頼の範囲外（FixedApply／FixedFacts）なので、不変化していない。投影・計画のAPIは毎回内部で事実とコンテキストを作り直すので、外から保持される経路は公開APIにはない。`LedgerContext` の不変化が必要なら、別の限定依頼にする。
- 元の§9／§10の「B03xは等価」、§4の `HistoryResolutionConfirmResult` の `committable` の記述は、元の記録として残し、上記の訂正を正とする。

## 12.7 範囲・保護参照・停止

`commands.py`、既存コア／保存／S2／S3-A／B-1の試験、旧欠陥注入スクリプト、fixtures、依存、設定、workflow、既存資料は変更していない。B-3以降、S3-C、保存・CAS・解錠・CLI・通知・本番は追加していない。PR・マージ・Actions・本番反映・通知はない。

保護参照42件（開始指示書§5の40件＋元の実装ブランチ `feat/v2-history-s3b2-20261030`＝`132a3392…`＋本依頼を保存した資料ブランチ `docs/v2-history-s3b2-receipt-20261030`＝`bd59d456…`）を読取専用に保った。開始時は2026-10-30T07:30:03Zに40/40一致、元の実装ブランチと資料ブランチも固定SHAと一致。終了時の結果は完了報告に記す。自分の新規修正ブランチだけをpushした。結果を保存したら止め、次の工程には進まない。
