# V2 C-1 CONSUME 限定実装 結果

作成日：2026-11-03（日本時間）。担当：Claude Sonnet 5.5、effort high（`get_session`の`session_context.model`＝claude-sonnet-5-5[1m]、`effort_level`＝high で確認。実際に提供されたモデルの切替は利用環境側で行われるため、プロンプトの記載だけでは確認としていない）。
状態：**実装・自己検証まで。レビュー待ち。** PR・マージ・Actions・本番・通知、C-2〜C-4へは進んでいない。ブランチ feat/v2-history-consume-c1-20261103 だけをpushする。

## 1. 固定入力・SHA

| 用途 | 値 |
|---|---|
| 実装開始点 | bfbde7a7854bf91a77fb58737c24b19c6507453a（fix/v2-scope-range-freeze-review-20261103） |
| ランタイムのコミット | c63912a27c4783e18f9fdbc2137e2daa70cd69aa |
| 試験対象（最後のコード・試験） | **3f780c116964bbcfc8007b8e371f194bdca6db39**（feat/v2-history-consume-c1-20261103） |
| 保存最終 | 本結果文書だけを足した次のコミット（結果文書内には自身のSHAを書けないため、push報告に記す） |
| 設計・依頼・試行の資料コミット | a6340c3937092e4cb658913b9acfb4973a084326（docs/v2-consume-s3c-20261103） |
| 3つのblob | 設計 d7c369c6b1c73205399ec79b7f9f29c509ca3f44（docs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md）、依頼書 61369b7d9aecfa1d4b20d8b9df5cd2bba69d1bb2（docs/tasks/V2_CONSUME_C1_LIMITED_IMPLEMENTATION_REQUEST.md）、試行差分 2b49efc9389500a633aaaab8a9aa46c71574e0f7（docs/specs/V2_CONSUME_C1_TRIAL_20261103.diff、SHA-256 03a28e4f422fdfd0f666fd4dad128e897c0c7d99db9505ab7ae595e713b7f35c） |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6（設計§6、D-3）、再レビュー 9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |
| B-5b再レビュー | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b §5 P-02 |

採用：Rockyさんが設計§8のD-1〜D-6を推奨どおり採用し、C-1だけの着手を指示した（コーディネーター経由、2026-11-03）。C-2〜C-4は未承認で、触れていない。実装ブランチはbfbde7aから新規に作った。運用方針は日足のみで、分足・NBBOは前提にしていない。

## 2. 結論

CONSUMEを復元計画の5つ目の処分として、メモリ内の純粋な計算で実装した。検査器（v2_history/restore.py）、計画（v2_history_restore）、確認の3つが形を知り、決定は「残す記録が残す行」から、市場値は注入seriesから固定し、作られたAPPLYは変更しない`evaluate_day`で最終投影の後に再計算して照合する。基本のbasisは23キー、operationは`soxl-v2-history-restore-plan/1`のまま、OPSは4つのまま、`__all__`と`v2_history.KINDS`は変えていない。取得・保存・送信のアダプタは無い。通知しただけで保有・原価・売却済みの状態を更新しない。

**履歴検査器の成功だけでは、解放日・決定・市場値まで照合済みとは扱っていない**（Rockyさんの指示）。検査器は形・位置・日・バッチの間までを見る。解放日・決定・市場値は計画側で、台帳・暦・seriesと一緒に検証し、確認で再検証する。それぞれを別の試験で固定した（§6）。

結果：4版（3.10/3.11/3.12/3.13）、別クリーンクローン、`unshare -n -r`下で、全12スイート rc＝0、失敗0、error0。新規112件。欠陥注入は17項目（細分20件）で、最終版では検出19、等価1（根拠あり）、未検出0、準備失敗0（§8）。なお変異7は最初の版の試験では未検出だったため、検出する試験を1件足した（§8、§10）。Windowsは未実施。

## 3. 変えたもの

`git diff --stat bfbde7a 3f780c1`：19ファイル、+2137／−88。

| 区分 | ファイル | 内容 |
|---|---|---|
| ランタイム（変更9） | v2_history/restore.py | 検査器：CONSUMEの形・位置・日・バッチの間・作られたAPPLYの種別と日 |
| | v2_history_restore/values.py | `CONSUME`、`CONSUME_KEYS`、変更行・series項目の形（from_seq null）。OPSは4つのまま |
| | v2_history_restore/errors.py | `restore_invalid`に日だけのdetail。stopの説明 |
| | v2_history_restore/points.py | opsの形（`{op,d}`）、重複・退避APPLYの日・バッチの間（台帳不要の3規則） |
| | v2_history_restore/market.py | `fixed_days`：REAPPLYとCONSUMEの市場値の固定日（CONSUMEは注入sessionsのprevious(D)） |
| | v2_history_restore/records.py | `_consume`、Draftの`consumed`／`made`／`new_skips`、`_reapply`の位置の防御 |
| | v2_history_restore/build.py | 解放日、決定の選択、段階7の選び直し、`evaluate_day`の再計算、無効果の規則 |
| | v2_history_restore/confirm.py | 現在のseries読み直し、段階1のopsと候補の一致 |
| | v2_history_restore/__init__.py | docstringのみ（`__all__`は不変） |
| 既存試験の補正（4） | tests/v2_history/test_h06_restore_batch.py、tests/v2_history_restore/test_r4_01_point_ops.py、tests/v2_history_restore/test_r4_09_scope.py、tests/v2_scope_chain/test_sc_03_scope.py | §4。補正6件（h06 1件、r4_01 1件、r4_09 4件）＋ENDの1行 |
| 新規（6） | tests/v2_history_consume/c1_helpers.py、test_c1_01_checker.py（24）、test_c1_02_success.py（16）、test_c1_03_plan.py（34）、test_c1_04_confirm.py（15）、test_c1_09_scope.py（23） | 計112件。`__init__.py`は作っていない |
| 結果文書 | docs/implementation/V2_CONSUME_C1_RESULT.md | 本書（別コミット） |

追加・変更していないもの：v2_core、v2_persistence、v2_recovery、v2_history（restore.py以外）、v2_history_ops、v2_history_restart、v2_history_diagnose、v2_history_adopt、main.py、研究、設定、依存、workflow、STATUS／ROADMAP／MODEL_POLICY／CLAUDE。新しい依存は無い。

### 3.1 記録の形（設計§3.2）

- opsの要素：`{"op":"CONSUME","d":<日>}`（2キー）。
- replayの要素：`{"op":"CONSUME","from_seq":null,"d":<日>,"seq":<作られたseq>,"same_as_superseded":null}`（5キーのまま）。
- 作られる記録：通常のAPPLY（キーは変わらない）。RECOVERY_RESTOREは15キーのまま。CONSUMEを除いた列が退避列を鎖の順に1回ずつ名指しし、作られる記録はopsの順に途切れず並ぶ。

### 3.2 解放日の集合（設計§3.4／D-2）

解放日は次の和集合：DROPした宣言の宣言日、DROPした再開始が飛ばしたセッション、REAPPLYで新たに飛ばす日。**REAPPLYの前に置いたCONSUMEの日も「新たに飛ばす日」に数える**（`Draft.new_skips`）。これは試行差分と違う点で、暦の変更（現在のカレンダーにセッションを加える合成入力）でREAPPLYが新たに飛ばす日を、同じバッチのCONSUMEが消費する場合（C1-06の3種目）を通すための追加である（§5）。

### 3.3 エラーの規則（restore_invalid／ops、detail＝日）

`restore_consume_applied_day`、`restore_consume_duplicate`、`restore_consume_in_batch`（検査器と計画の双方）、`restore_consume_no_decision`、`restore_consume_order`、`restore_consume_not_released`、`restore_consume_input`、段階7の`restore_decision_changed`、停止の`restore_requires_consume`（従来どおり）。

## 4. 変更したランタイムの差分全文と、既存試験の補正の差分全文

### 4.1 ランタイム（`git diff bfbde7a 3f780c1 -- v2_history v2_history_restore`、9ファイル、771行）

```diff
diff --git a/v2_history/restore.py b/v2_history/restore.py
index ed1428a..fb1b379 100644
--- a/v2_history/restore.py
+++ b/v2_history/restore.py
@@ -2,8 +2,12 @@
 (design 8.1-8.6). Only the form and the facts of the batch are checked here; the created records must also pass the
 ordinary view rules (view.py) in the chain views that contain them.
 
-CONSUME is refused (restore_op_unsupported / unsupported_event). RECOVERY_PREFIX_ADOPTION cannot be restored
-before (restore_before_adoption).
+CONSUME (stage C-1) is a new APPLY for a day that the operations set free of a record that had passed over it. Only its
+form, place and day are checked here: the day is not the day of a superseded APPLY, it is named once, it does not stand
+inside one request batch, and the record it made is an APPLY of that day. Which days are free, and which decision and
+market values the new APPLY was made with, need the ledger, the sessions and the series, so they are the plan's matter
+(v2_history_restore), as the decisions and market values of a REAPPLY are. The created APPLY passes the ordinary rules of
+the chain view like any other. RECOVERY_PREFIX_ADOPTION cannot be restored before (restore_before_adoption).
 """
 from v2_recovery.common import is_requested_text, valid_request_id
 
@@ -118,21 +122,31 @@ def _check_one(events, parents, migration_seq, k, rec, replayed):
     replay = rec["replay"]
     if not isinstance(replay, list) or not isinstance(ops, list):
         raise _bad("restore_replay_mismatch")
-    for entry in list(ops) + list(replay):
-        if isinstance(entry, dict) and entry.get("op") == CONSUME:
-            raise _bad("restore_op_unsupported")
-    if len(replay) != len(superseded) or len(ops) != len(superseded):
+    if len(replay) != len(ops):
         raise _bad("restore_replay_mismatch")
-    for entry, op_entry, s in zip(replay, ops, superseded):
+    for entry in replay:
         if not isinstance(entry, dict) or set(entry) != REPLAY_KEYS:
             raise _bad("restore_replay_mismatch")
+    named = []                               # (replay entry, ops entry) of the operations that name a superseded record
+    for entry, op_entry in zip(replay, ops):
+        if entry["op"] != CONSUME:
+            named.append((entry, op_entry))
+            continue
+        if entry["from_seq"] is not None or entry["same_as_superseded"] is not None or not is_date(entry["d"]):
+            raise _bad("restore_replay_mismatch")
+        if not same(op_entry, {"op": CONSUME, "d": entry["d"]}):
+            raise _bad("request_basis")
+    if len(named) != len(superseded):
+        raise _bad("restore_replay_mismatch")
+    for (entry, op_entry), s in zip(named, superseded):
         if entry["op"] not in _ALL_OPS or entry["op"] not in _ALLOWED[events[s]["kind"]]:
             raise _bad("restore_op_kind")
         if entry["from_seq"] != s or not is_int(entry["from_seq"]):
             raise _bad("restore_replay_mismatch")
         if not same(op_entry, {"op": entry["op"], "from_seq": entry["from_seq"]}):
             raise _bad("request_basis")
-    _check_batch_ops(events, replay, superseded)
+    _check_batch_ops(events, [entry for entry, _op in named], superseded)
+    _check_consumes(events, replay, superseded)
     _check_window(events, k, replay, superseded, point, pos, replayed)
 
 
@@ -171,11 +185,45 @@ def _check_batch_ops(events, replay, superseded):
         raise _bad("restore_partial_batch")
 
 
+def _check_consumes(events, replay, superseded):
+    """A CONSUME is not the day of a superseded APPLY, is named once, and does not stand between two operations on the
+    records of one request (a batch is dropped or replayed as a whole, and nothing is put inside it)."""
+    applied = {events[s]["d"] for s in superseded if events[s]["kind"] == APPLY}
+    named = iter(superseded)
+    seen, owners = set(), []                  # owners: the request of each place; None for a record of no request
+    for entry in replay:
+        if entry["op"] == CONSUME:
+            if entry["d"] in applied:
+                raise _bad("restore_consume_applied_day")
+            if entry["d"] in seen:
+                raise _bad("restore_consume_duplicate")
+            seen.add(entry["d"])
+            owners.append(CONSUME)
+        else:
+            ev = events[next(named)]
+            owners.append(ev["request_id"] if ev["kind"] in (ACK, DECLARE_MISSING) else None)
+    for i, owner in enumerate(owners):
+        if owner == CONSUME:
+            before = {o for o in owners[:i] if o not in (None, CONSUME)}
+            after = {o for o in owners[i + 1:] if o not in (None, CONSUME)}
+            if before & after:
+                raise _bad("restore_consume_in_batch")
+
+
 def _check_window(events, k, replay, superseded, point, pos, replayed):
     created_map, dropped = {}, set()
     plan = []
     n = 0
-    for entry, s in zip(replay, superseded):
+    named = iter(superseded)
+    for entry in replay:
+        if entry["op"] == CONSUME:
+            created = k + 1 + n
+            n += 1
+            if entry["seq"] != created or not is_int(entry["seq"]):
+                raise _bad("restore_replay_mismatch")
+            plan.append((entry, None, created))
+            continue
+        s = next(named)
         if entry["op"] in (REAPPLY, REPLAY):
             created = k + 1 + n
             n += 1
@@ -188,7 +236,14 @@ def _check_window(events, k, replay, superseded, point, pos, replayed):
                 raise _bad("restore_replay_mismatch")
             dropped.add(s)
     for entry, s, created in plan:
-        if created >= len(events) or events[created]["kind"] != events[s]["kind"]:
+        if created >= len(events):
+            raise _bad("restore_incomplete")
+        if s is None:                                   # a consumed day: an APPLY of that day
+            if events[created]["kind"] != APPLY:
+                raise _bad("restore_incomplete")
+            if events[created]["d"] != entry["d"]:
+                raise _bad("restore_replay_mismatch")
+        elif events[created]["kind"] != events[s]["kind"]:
             raise _bad("restore_incomplete")
     point_pos = pos[point]
 
@@ -200,6 +255,8 @@ def _check_window(events, k, replay, superseded, point, pos, replayed):
         return target
 
     for entry, s, created in plan:
+        if s is None:
+            continue                                    # a consumed day: the chain view checks it like any APPLY
         old, new = events[s], events[created]
         if entry["op"] == REAPPLY:
             _check_reapply(entry, old, new)
diff --git a/v2_history_restore/__init__.py b/v2_history_restore/__init__.py
index a848280..3c43e33 100644
--- a/v2_history_restore/__init__.py
+++ b/v2_history_restore/__init__.py
@@ -4,9 +4,10 @@ records it makes, on a checked schema-2 history.
 Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
 randomness. Depends on the standard library, v2_core, v2_persistence, v2_recovery, v2_history and v2_history_ops (all
 unchanged). The result is a candidate History, an in-memory verification value: committed and committable are always
-False, there is no batch, and nothing is stored, published, locked or compared and swapped. Four operations only
-(REAPPLY, REPLAY, DROP, RETIRE); a day that would have to be consumed anew is refused. Consuming, damage diagnosis and
-publication are not here. Draft, not adopted for production.
+False, there is no batch, and nothing is stored, published, locked or compared and swapped. Four operations name a
+superseded record (REAPPLY, REPLAY, DROP, RETIRE); CONSUME (stage C-1) makes a new APPLY for a day that the operations
+set free, named by the caller with its place; a freed day with a decision that is not consumed is still refused.
+Damage diagnosis and publication are not here. Draft, not adopted for production.
 """
 from .confirm import confirm_restore_plan
 from .prepare import prepare_restore_plan
diff --git a/v2_history_restore/build.py b/v2_history_restore/build.py
index ac0140e..e95dd94 100644
--- a/v2_history_restore/build.py
+++ b/v2_history_restore/build.py
@@ -2,11 +2,13 @@
 basis. prepare_restore_plan runs it once on the given history; confirm_restore_plan runs it again on the original
 history and compares the result with the plan's basis.
 
-The order is fixed (design 5): the history, sessions, dates and ledger rows -> check_d, the restore point and the
-operations -> requested_at, the request id -> the saved context that stays, the series inputs, and every new content
-item -> the hashes and the candidate as a whole -> the evidence of the replayed requests, the facts of the whole
-candidate and the rows they leave -> the days that would need a new consumption, the saved decisions, the saved market
-inputs -> the final projection of the unchanged B-2 function, then evaluate_day -> the no-effect rule -> the basis.
+The order is fixed (design 5; C-1 design 3.4): the history, sessions, dates and ledger rows -> check_d, the restore
+point and the operations -> requested_at, the request id -> the saved context that stays, the series inputs, the
+decision of each consumed day and every new content item, then the days that were consumed must be days the operations
+set free -> the hashes and the candidate as a whole -> the evidence of the replayed requests, the facts of the whole
+candidate and the rows they leave -> the decisions the consumed days were made with, the days that still need a
+consumption, the saved decisions, the saved market inputs -> the final projection of the unchanged B-2 function, then
+evaluate_day for every re-applied and consumed day -> the no-effect rule -> the basis.
 
 No market rule, threshold or state formula is written here: the new APPLY records come from the unchanged
 apply_transition (records.py), the whole candidate is checked by the unchanged validate_history and projected by the
@@ -35,10 +37,10 @@ from v2_recovery.project import apply_records, check_versions
 
 from .chain import context_mismatch, context_missing, facts_of, frontier_of, last_segment
 from .errors import candidate_invalid, decision_changed, market_input_changed, no_effect, requires_consume, restore_invalid
-from .market import digest_of, series_inputs
+from .market import digest_of, fixed_days, series_inputs
 from .points import check_ops, check_point
 from .records import plan_records, settle_changes
-from .values import DROP, OPERATION, READY, REAPPLY, REASON, REPLAY
+from .values import CONSUME, DROP, OPERATION, READY, REAPPLY, REASON, REPLAY
 
 
 def requested_at_of(value):
@@ -66,8 +68,10 @@ def _check_check_d(check, sl, check_d):
 
 def _check_replayed_boundaries(events, superseded, plan_ops, sl):
     """A restart that is written again keeps its saved boundary session: it must equal the current session of that day."""
-    for entry, seq in zip(plan_ops, superseded):
-        old = events[seq]
+    for entry in plan_ops:
+        if entry["op"] == CONSUME:
+            continue
+        old = events[entry["from_seq"]]
         if entry["op"] == REPLAY and old["kind"] == RESTART_UNKNOWN:
             now = sl.get(old["resume_after"])
             if now is None:
@@ -169,12 +173,16 @@ def _frontiers_before_restarts(events, effective):
     return out
 
 
-def _released_days(events, effective, superseded, plan_ops, draft, sl, apply_days):
+def _freed_days(events, effective, plan_ops, draft, sl):
     """The days that the operations free of a record that had passed over them (design 8): the declared day of a dropped
-    declaration, the sessions a dropped restart had skipped, and the sessions a re-applied day newly skips."""
+    declaration, the sessions a dropped restart had skipped, and the sessions a re-applied day newly skips (a day consumed
+    in front of the re-applied day counted as one it newly skips). Before the days applied in the candidate are taken out."""
     days = set()
     frontiers = None
-    for entry, seq in zip(plan_ops, superseded):
+    for entry in plan_ops:
+        if entry["op"] == CONSUME:
+            continue
+        seq = entry["from_seq"]
         old = events[seq]
         if entry["op"] == DROP and old["kind"] == DECLARE_MISSING:
             days.add(old["d"])
@@ -182,10 +190,22 @@ def _released_days(events, effective, superseded, plan_ops, draft, sl, apply_day
             if frontiers is None:
                 frontiers = _frontiers_before_restarts(events, effective)
             days.update(s.date for s in sl.sessions if frontiers[seq] < s.date <= old["resume_after"])
-    for old, new in draft.reapplied:
-        days.update(set(new["skipped_sessions"]) - set(old["skipped_sessions"]))
+    days |= draft.new_skips
+    return days
+
+
+def _released_days(events, effective, superseded, plan_ops, draft, sl, apply_days):
+    """The freed days that no APPLY of the candidate covers: the ones that would still have to be consumed."""
     known = {s.date for s in sl.sessions}
-    return sorted(d for d in days if d in known and d not in apply_days)
+    return sorted(d for d in _freed_days(events, effective, plan_ops, draft, sl) if d in known and d not in apply_days)
+
+
+def _check_consumed_released(events, effective, plan_ops, draft, sl):
+    """Each consumed day is a freed day. Checked on the drafts, before any hash is made."""
+    freed = _freed_days(events, effective, plan_ops, draft, sl)
+    for d, _new in draft.consumed:
+        if d not in freed:
+            raise restore_invalid("ops", "restore_consume_not_released", detail=d)
 
 
 def _check_new_days(rows, sl, days):
@@ -202,8 +222,19 @@ def _check_saved_decisions(rows, sl, draft):
             raise decision_changed(old["d"])
 
 
+def _check_consumed_decisions(rows, sl, draft):
+    """The final rows still give each consumed day the decision it was made with (it was chosen from the rows the kept
+    records leave, before the records of the batch were known)."""
+    for d, new in draft.consumed:
+        saved = parse_observation(copy.deepcopy(new["confirmed_inputs"]["decision"]))
+        chosen = select_decision(copy.deepcopy(rows), sl, d)
+        if chosen is None or chosen.record_id != saved.record_id or chosen.fingerprint() != saved.fingerprint():
+            raise decision_changed(d)
+
+
 def _check_saved_market(items, draft):
-    for (old, _new), item in zip(draft.reapplied, items):
+    reapplied = [item for item in items if item["from_seq"] is not None]
+    for (old, _new), item in zip(draft.reapplied, reapplied):
         saved = old["confirmed_inputs"]
         if (not same(item["row"], saved["row"]) or not same(item["prev_row"], saved["prev_row"])
                 or item["prev_session_date"] != saved["prev_session_date"]):
@@ -213,9 +244,9 @@ def _check_saved_market(items, draft):
 def _check_days_again(chain, ledger, cuts, sl, draft):
     """Each re-applied day goes through the unchanged evaluate_day on its new parent state, the same cut of the series
     and the final ledger; the transition and the next state must be the ones that were calculated from the saved
-    inputs. Done only after the final projection has accepted the candidate."""
+    inputs; a consumed day goes the same way. Done only after the final projection has accepted the candidate."""
     index = {r["seq"]: i for i, r in enumerate(chain)}
-    for _old, new in draft.reapplied:
+    for new in draft.made:
         parent = chain[index[new["seq"]] - 1]
         day = evaluate_day(MarketState.from_dict(parent["state_after"]), new["d"], cuts[new["d"]], sl,
                            ledger.raw_observations())
@@ -224,6 +255,25 @@ def _check_days_again(chain, ledger, cuts, sl, draft):
             raise candidate_invalid()
 
 
+def _consume_inputs(ctx, prefix, plan_ops, items, sl):
+    """For each CONSUME day: the decision that the rows left by the kept records give (the unchanged apply_records over
+    the kept acknowledgements and declarations, then the unchanged select_decision), and the series item fixed for that
+    day. A day without a decision is refused. Nothing is read when no day is consumed."""
+    days = [entry["d"] for entry in plan_ops if entry["op"] == CONSUME]
+    if not days:
+        return {}
+    remaining, _actually, _supplemented = apply_records(ctx, [r for r in prefix if r["kind"] in (ACK, DECLARE_MISSING)])
+    rows = sorted((r.cols for r in remaining.values()), key=canonical_json)
+    fixed = {item["d"]: item for item in items if item["from_seq"] is None}
+    out = {}
+    for d in days:
+        decision = select_decision(copy.deepcopy(rows), sl, d)
+        if decision is None:
+            raise restore_invalid("ops", "restore_consume_no_decision", detail=d)
+        out[d] = (decision, fixed[d])
+    return out
+
+
 def build_restore(history, restore_point, ops, sessions, raw_observations, series, check_d, request_id, when):
     """Returns (basis, candidate). when() gives the requested_at text; it is asked for after the inputs are read, so
     that an error of the history, sessions, dates or ledger rows comes first."""
@@ -244,11 +294,13 @@ def build_restore(history, restore_point, ops, sessions, raw_observations, serie
     effective = list(check.effective_seqs)                                                 # 4
     kept = effective[:pos + 1]
     prefix = [events[s] for s in kept]
-    LedgerContext.from_facts(facts_of(prefix, prefix[-1]["seq"]), sl, raw_observations, check_d)
+    ctx = LedgerContext.from_facts(facts_of(prefix, prefix[-1]["seq"]), sl, raw_observations, check_d)
     _check_replayed_boundaries(events, superseded, plan_ops, sl)
-    olds = [events[e["from_seq"]] for e in plan_ops if e["op"] == REAPPLY]
-    items, cuts = series_inputs(series, sl, olds) if olds else ([], {})
-    draft = plan_records(events, kept, superseded, plan_ops, sl)
+    days = fixed_days(events, plan_ops, sl)
+    items, cuts = series_inputs(series, sl, days) if days else ([], {})
+    consume_inputs = _consume_inputs(ctx, prefix, plan_ops, items, sl)
+    draft = plan_records(events, kept, superseded, plan_ops, sl, consume_inputs)
+    _check_consumed_released(events, effective, plan_ops, draft, sl)
     point = {"seq": restore_point["seq"], "event_hash": restore_point["event_hash"]}
     request_basis = {"request_id": request_id, "restore_point": point, "ops": copy.deepcopy(plan_ops),
                      "check_d": check_d, "reason_code": REASON, "requested_at": requested_at}
@@ -263,15 +315,16 @@ def build_restore(history, restore_point, ops, sessions, raw_observations, serie
     chain = [cand_events[s] for s in cand_check.effective_seqs]
     _replay_evidence(chain, draft.replayed, sl, raw_observations, check_d)                       # 6
     facts, prior, _excluded, _supplemented = _prior_rows(chain, cand_check.head_seq, sl, raw_observations, check_d)
+    _check_consumed_decisions(prior, sl, draft)                                            # 7
     _check_new_days(prior, sl, _released_days(events, effective, superseded, plan_ops, draft, sl, facts.apply_days))
-    _check_saved_decisions(prior, sl, draft)                                               # 7
+    _check_saved_decisions(prior, sl, draft)
     _check_saved_market(items, draft)
     ledger = project_history_ledger(candidate, sessions, raw_observations, check_d)        # 8
     if (not same(ledger.rows, prior) or ledger.effective_digest != sha256_text(canonical_json(prior))
             or ledger.ledger_digest != ledger_text):
         raise candidate_invalid()
     _check_days_again(chain, ledger, cuts, sl, draft)
-    if not any(e["op"] == DROP for e in plan_ops) and all(e["same_as_superseded"] is not False
+    if not any(e["op"] in (DROP, CONSUME) for e in plan_ops) and all(e["same_as_superseded"] is not False
                                                            for e in draft.entries if e["op"] == REAPPLY):
         raise no_effect()
     basis = {
diff --git a/v2_history_restore/confirm.py b/v2_history_restore/confirm.py
index 1bdbdea..49f7b6f 100644
--- a/v2_history_restore/confirm.py
+++ b/v2_history_restore/confirm.py
@@ -16,9 +16,9 @@ from v2_recovery.common import is_requested_text, valid_request_id
 from v2_recovery.ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest
 
 from .build import build_restore
-from .market import digest_of, series_inputs
-from .values import (BASIS_KEYS, CONFIRMED_IN_MEMORY, NO_CHANGE, OP_KEYS, OPERATION, OPS, POINT_KEYS, READY, REAPPLY,
-                     REASON, RestoreConfirmResult, RestorePlan, change_ok, series_item_ok)
+from .market import digest_of, fixed_days, series_inputs
+from .values import (BASIS_KEYS, CONFIRMED_IN_MEMORY, CONSUME, CONSUME_KEYS, NO_CHANGE, OP_KEYS, OPERATION, OPS,
+                     POINT_KEYS, READY, REAPPLY, REASON, RestoreConfirmResult, RestorePlan, change_ok, series_item_ok)
 
 _HASH_KEYS = ("history_digest", "expected_head_hash", "expected_state_digest", "request_hash", "ledger_digest",
               "sessions_digest", "series_digest", "effective_digest", "candidate_digest", "candidate_state_digest")
@@ -33,14 +33,25 @@ def _form_ok(basis):
             and all(is_hex64(basis[k]) for k in _HASH_KEYS)
             and isinstance(point, dict) and set(point) == POINT_KEYS and is_int(point["seq"])
             and point["seq"] >= 0 and is_hex64(point["event_hash"])
-            and isinstance(ops, list) and all(isinstance(o, dict) and set(o) == OP_KEYS and o["op"] in OPS
-                                              and is_int(o["from_seq"]) and o["from_seq"] >= 0 for o in ops)
+            and isinstance(ops, list) and all(_op_ok(o) for o in ops)
             and isinstance(basis["series_inputs"], list) and all(series_item_ok(i) for i in basis["series_inputs"])
             and isinstance(basis["changes"], list) and all(change_ok(c) for c in basis["changes"])
             and isinstance(basis["candidate_records"], list) and basis["candidate_records"]
             and isinstance(basis["candidate_history"], dict))
 
 
+def _op_ok(o):
+    """One entry of the plan's ops: {op, from_seq} of the four operations, or {op: CONSUME, d}."""
+    if isinstance(o, dict) and o.get("op") == CONSUME:
+        return set(o) == CONSUME_KEYS and is_date(o["d"])
+    return (isinstance(o, dict) and set(o) == OP_KEYS and o["op"] in OPS and is_int(o["from_seq"])
+            and o["from_seq"] >= 0)
+
+
+def _has_consume(ops):
+    return any(isinstance(o, dict) and o.get("op") == CONSUME for o in ops)
+
+
 def _original_prefix(events, basis):
     """The history the plan was made from, as the physical prefix of a candidate: checked like any history, and it must
     match the plan's digest, head and state."""
@@ -92,6 +103,9 @@ def _plan_basis(plan, confirmed_plan_hash):
             or confirmed_plan_hash != view["plan_hash"] or not _form_ok(basis)):
         raise history_plan_mismatch()
     candidate, cand_check, events, original = _candidate_of(basis)
+    stated = events[basis["expected_head_seq"] + 1]["request_basis"]["ops"]       # the RECOVERY_RESTORE of the candidate
+    if (_has_consume(basis["ops"]) or _has_consume(stated)) and not same(basis["ops"], stated):
+        raise history_plan_mismatch()          # the consumed days and their places are those of the plan's own candidate
     _reapply_olds(basis, events)      # the saved APPLY records of the REAPPLY operations: a refusal is still the plan's
     return basis, candidate, cand_check, events, original
 
@@ -104,8 +118,9 @@ def confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_obser
     check = validate_history(history)                                                      # 2
     sl = copy_sessions(sessions)
     rows = parse_ledger(raw_observations)
-    olds = _reapply_olds(basis, cand_events)
-    items = series_inputs(series, sl, olds)[0] if olds else []
+    _reapply_olds(basis, cand_events)
+    days = fixed_days(cand_events, basis["ops"], sl)
+    items = series_inputs(series, sl, days)[0] if days else []
     same_inputs = (ledger_digest(rows) == basis["ledger_digest"] and sessions_digest(sl) == basis["sessions_digest"]
                    and digest_of(items) == basis["series_digest"])
     is_original = (history.digest == basis["history_digest"] and check.head_seq == basis["expected_head_seq"]
diff --git a/v2_history_restore/errors.py b/v2_history_restore/errors.py
index 6a2ec75..569945e 100644
--- a/v2_history_restore/errors.py
+++ b/v2_history_restore/errors.py
@@ -2,9 +2,10 @@
 from v2_persistence.errors import PersistenceError
 
 
-def restore_invalid(field, rule):
-    """A mistake in what the caller asked for (or a plan that cannot be read), as opposed to a broken history."""
-    return PersistenceError("restore_invalid", field, rule=rule)
+def restore_invalid(field, rule, detail=None):
+    """A mistake in what the caller asked for (or a plan that cannot be read), as opposed to a broken history. detail is
+    only ever a day."""
+    return PersistenceError("restore_invalid", field, rule=rule, detail=detail)
 
 
 def candidate_invalid():
@@ -13,7 +14,7 @@ def candidate_invalid():
 
 
 def requires_consume(d):
-    """A day would have to be consumed anew; CONSUME is not planned in this stage."""
+    """A day the operations set free has a decision and the caller did not name it in a CONSUME."""
     return PersistenceError("restore_requires_consume", "ops", detail=d)
 
 
diff --git a/v2_history_restore/market.py b/v2_history_restore/market.py
index b694f23..a866e08 100644
--- a/v2_history_restore/market.py
+++ b/v2_history_restore/market.py
@@ -1,7 +1,8 @@
-"""The market inputs of the days that are applied again (design 9): the current rows are read once, from a copy of the
-series made at each day, and fixed as the series inputs that the plan binds to.
+"""The market inputs of the days that are applied again or consumed (design 9; C-1 design 3.5): the current rows are read
+once, from a copy of the series made at each day, and fixed as the series inputs that the plan binds to.
 
-The rows are read, compared with the saved ones and fixed here; no indicator is calculated. The injected series is
+The rows are read and fixed here (a re-applied day also compares them with the saved ones, in build.py); no indicator is
+calculated. The injected series is
 only asked for through(D), row(date) and previous_date(D)."""
 from v2_core.errors import CoreError, InputError
 from v2_persistence.codec import canonical_json, sha256_text
@@ -9,19 +10,35 @@ from v2_persistence.errors import PersistenceError
 from v2_persistence.events import row_dict
 
 from .errors import restore_invalid
+from .values import CONSUME, REAPPLY
 
 
 def _bad():
     return restore_invalid("series", "market_input")
 
 
-def series_inputs(series, sl, olds):
-    """For each APPLY that will be applied again (in order): the cut of the series at D and the fixed input item.
-    Returns (items, cuts {d: cut}). A series that does not answer in the expected form is restore_invalid / series /
-    market_input; the core's own input errors are kept as they are."""
+def fixed_days(events, plan_ops, sl):
+    """The days whose market values the plan fixes, in the order of the operations: (from_seq, d, previous session date)
+    of each REAPPLY (the previous session date the superseded APPLY saved) and of each CONSUME (no superseded record,
+    so from_seq is None; the previous session date is the injected sessions' previous(D), None when D has none, which
+    series_inputs then refuses)."""
+    out = []
+    for entry in plan_ops:
+        if entry["op"] == REAPPLY:
+            old = events[entry["from_seq"]]
+            out.append((old["seq"], old["d"], old["confirmed_inputs"]["prev_session_date"]))
+        elif entry["op"] == CONSUME:
+            before = sl.previous(entry["d"])
+            out.append((None, entry["d"], None if before is None else before.date))
+    return out
+
+
+def series_inputs(series, sl, days):
+    """For each day that is applied again or consumed (in order): the cut of the series at D and the fixed input item.
+    days is fixed_days(...). Returns (items, cuts {d: cut}). A series that does not answer in the expected form is
+    restore_invalid / series / market_input; the core's own input errors are kept as they are."""
     items, cuts = [], {}
-    for old in olds:
-        d, saved = old["d"], old["confirmed_inputs"]
+    for from_seq, d, saved_previous in days:
         session = sl.get(d)
         if session is None:
             raise InputError("target_not_in_sessions", "sessions")
@@ -36,11 +53,11 @@ def series_inputs(series, sl, olds):
             cut = series.through(d)
             row = cut.row(d)
             try:
-                prev_row = cut.row(saved["prev_session_date"])
+                prev_row = cut.row(saved_previous)
             except InputError:
                 prev_row = None                       # as the core does: the previous indicators are unavailable
             series_previous = cut.previous_date(d)
-            item = {"from_seq": old["seq"], "d": d, "prev_session_date": saved["prev_session_date"],
+            item = {"from_seq": from_seq, "d": d, "prev_session_date": saved_previous,
                     "series_previous_date": series_previous, "row": row_dict(row),
                     "prev_row": None if prev_row is None else row_dict(prev_row, "prev_row")}
             canonical_json(item)                        # a value that cannot be written as JSON is refused here
@@ -50,7 +67,7 @@ def series_inputs(series, sl, olds):
             raise
         except (AttributeError, TypeError, KeyError, ValueError, IndexError, OverflowError, RecursionError):
             raise _bad() from None
-        if not (series_previous == prev_session.date == saved["prev_session_date"]):
+        if not (series_previous == prev_session.date == saved_previous):
             raise InputError("session_series_mismatch", "market")
         items.append(item)
         cuts[d] = cut
diff --git a/v2_history_restore/points.py b/v2_history_restore/points.py
index eebdbdf..e2fd9d9 100644
--- a/v2_history_restore/points.py
+++ b/v2_history_restore/points.py
@@ -1,9 +1,9 @@
 """The restore point and the operation list (design 4): the checks of the caller's request, in a fixed order."""
-from v2_history.common import is_hex64, is_int
+from v2_history.common import is_date, is_hex64, is_int
 from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE, RESTART_UNKNOWN
 
 from .errors import restore_invalid
-from .values import DROP, OP_KEYS, OPS, POINT_KEYS, REAPPLY, REPLAY, RETIRE
+from .values import CONSUME, CONSUME_KEYS, DROP, OP_KEYS, OPS, POINT_KEYS, REAPPLY, REPLAY, RETIRE
 
 _ALLOWED = {APPLY: (REAPPLY,), ACK: (REPLAY, DROP), DECLARE_MISSING: (REPLAY, DROP),
             RESTART_UNKNOWN: (REPLAY, DROP), RECOVERY_RESTORE: (RETIRE,)}
@@ -37,23 +37,32 @@ def check_point(check, view, events, point):
 
 
 def check_ops(events, superseded, ops):
-    """The operations, one per superseded record in the same order. Nothing is sorted, completed or defaulted.
-    Returns a fresh list of {op, from_seq}."""
+    """The operations: one per superseded record in the same order, and CONSUME entries between them wherever the caller
+    names them. Nothing is sorted, completed or defaulted. Returns a fresh list of {op, from_seq} and {op, d}.
+
+    The order of the checks: the form of every entry; then, over the entries that name a superseded record (CONSUME left
+    out), the list, the kinds and the request batches as before; then the three rules of CONSUME that need no ledger."""
     if type(ops) is not list:
         raise restore_invalid("ops", "ops_shape")
     norm = []
     for entry in ops:
         if not isinstance(entry, dict) or not isinstance(entry.get("op"), str):
             raise restore_invalid("ops", "ops_shape")
-        if entry["op"] not in OPS:                              # CONSUME, with any keys, and every unknown name
+        if entry["op"] == CONSUME:
+            if set(entry) != CONSUME_KEYS or not is_date(entry["d"]):
+                raise restore_invalid("ops", "ops_shape")
+            norm.append({"op": CONSUME, "d": entry["d"]})
+            continue
+        if entry["op"] not in OPS:                              # every unknown name, with any keys
             raise restore_invalid("ops", "restore_op_unsupported")
         if set(entry) != OP_KEYS or not is_int(entry["from_seq"]):
             raise restore_invalid("ops", "ops_shape")
         norm.append({"op": entry["op"], "from_seq": entry["from_seq"]})
-    if [e["from_seq"] for e in norm] != list(superseded):
+    named = [e for e in norm if e["op"] != CONSUME]
+    if [e["from_seq"] for e in named] != list(superseded):
         raise restore_invalid("ops", "superseded_mismatch")
     by_request = {}
-    for entry, seq in zip(norm, superseded):
+    for entry, seq in zip(named, superseded):
         kind = events[seq]["kind"]
         if entry["op"] not in _ALLOWED.get(kind, ()):
             raise restore_invalid("ops", "restore_op_kind")
@@ -61,4 +70,29 @@ def check_ops(events, superseded, ops):
             by_request.setdefault(events[seq]["request_id"], set()).add(entry["op"])
     if any(len(chosen) > 1 for chosen in by_request.values()):
         raise restore_invalid("ops", "restore_partial_batch")
+    _check_consumes(events, superseded, norm)
     return norm
+
+
+def _check_consumes(events, superseded, norm):
+    """A CONSUME is not the day of a superseded APPLY (that day is re-applied or dropped, never made anew), is named once,
+    and does not stand between two operations on the records of one request. The reported day is the CONSUME's."""
+    applied = {events[s]["d"] for s in superseded if events[s]["kind"] == APPLY}
+    seen, owners = set(), []                   # owners: the request of each place; None for a record of no request
+    for entry in norm:
+        if entry["op"] == CONSUME:
+            if entry["d"] in applied:
+                raise restore_invalid("ops", "restore_consume_applied_day", detail=entry["d"])
+            if entry["d"] in seen:
+                raise restore_invalid("ops", "restore_consume_duplicate", detail=entry["d"])
+            seen.add(entry["d"])
+            owners.append(CONSUME)
+        else:
+            ev = events[entry["from_seq"]]
+            owners.append(ev["request_id"] if ev["kind"] in (ACK, DECLARE_MISSING) else None)
+    for i, entry in enumerate(norm):
+        if entry["op"] == CONSUME:
+            before = {o for o in owners[:i] if o not in (None, CONSUME)}
+            after = {o for o in owners[i + 1:] if o not in (None, CONSUME)}
+            if before & after:
+                raise restore_invalid("ops", "restore_consume_in_batch", detail=entry["d"])
diff --git a/v2_history_restore/records.py b/v2_history_restore/records.py
index 5a0c0fb..8b1f06c 100644
--- a/v2_history_restore/records.py
+++ b/v2_history_restore/records.py
@@ -18,11 +18,11 @@ from v2_core.state import MarketState
 from v2_core.transition import apply_transition
 from v2_history.common import same
 from v2_history.values import ACK, APPLY, DECLARE_MISSING, RESTART_UNKNOWN
-from v2_persistence.events import input_hash_of, serialize_transition, session_dict
+from v2_persistence.events import decision_dict, input_hash_of, serialize_transition, session_dict
 
 from .chain import context_mismatch, context_missing, contexts_agree, floor_of, frontier_of, last_segment
 from .errors import restore_invalid
-from .values import DROP, REAPPLY, REPLAY, RETIRE
+from .values import CONSUME, DROP, REAPPLY, REPLAY, RETIRE
 
 _APPLY_FIELDS = ("input_hash", "skipped_sessions", "state_after", "transition_result")
 
@@ -59,6 +59,9 @@ class Draft:
         self.created = {}          # old seq -> new seq
         self.reapplied = []        # (old record, new draft), in order
         self.replayed = set()      # the new seqs of the replayed records
+        self.consumed = []         # (day, new draft) of each CONSUME, in order
+        self.made = []             # the new APPLY drafts of the REAPPLY and CONSUME operations, in the order of the operations
+        self.new_skips = set()     # the days that a REAPPLY newly passes over, a day consumed in front of it counted
 
 
 def _reapply(work, old, new_seq, sl):
@@ -66,6 +69,8 @@ def _reapply(work, old, new_seq, sl):
     d = old["d"]
     seg = last_segment(work)
     base = seg["applies"][-1]["d"] if seg["applies"] else seg["date"]
+    if not base < d:                       # only a CONSUME put in front of it, for a later day, can make this so
+        raise restore_invalid("ops", "restore_consume_order", detail=base)
     nxt = sl.next(d)
     index = {s.date: i for i, s in enumerate(sl.sessions)}
     if base not in index:
@@ -96,6 +101,36 @@ def _reapply(work, old, new_seq, sl):
     return rec, changed
 
 
+def _consume(work, d, new_seq, sl, decision, item):
+    """A new APPLY for a day that the operations set free: the decision the kept records leave for D and the market values
+    fixed from the injected series (item), through the unchanged apply_transition on the new parent. The session range
+    and the skipped sessions are those of an ordinary day: from the base of the segment (its last APPLY day, else its
+    boundary) to next(D), the sessions between the base and D being skipped."""
+    seg = last_segment(work)
+    base = seg["applies"][-1]["d"] if seg["applies"] else seg["date"]
+    if not base < d:
+        raise restore_invalid("ops", "restore_consume_order", detail=d)
+    index = {s.date: i for i, s in enumerate(sl.sessions)}
+    if base not in index:
+        raise context_missing(d)
+    between = [s for s in sl.sessions if base < s.date < d]
+    for s in between:
+        if not s.confirmed:
+            raise InputError("intermediate_session_unconfirmed", "sessions", detail=s.date)
+    context = [session_dict(s) for s in sl.sessions[index[base]:index[sl.next(d).date] + 1]]
+    ci = {"decision": decision_dict(decision), "row": copy.deepcopy(item["row"]),
+          "prev_row": copy.deepcopy(item["prev_row"]), "prev_session_date": item["prev_session_date"],
+          "session_context": context}
+    prev_row = None if item["prev_row"] is None else _row(item["prev_row"])
+    t = apply_transition(MarketState.from_dict(work[-1]["state_after"]), d, item["prev_session_date"],
+                         _row(item["row"]), prev_row, decision)
+    if t.next_state is None:
+        raise restore_invalid("ops", "restore_consume_input", detail=d)
+    return {"kind": APPLY, "seq": new_seq, "parent_seq": new_seq - 1, "parent_hash": None, "d": d,
+            "confirmed_inputs": ci, "input_hash": input_hash_of(ci), "skipped_sessions": [s.date for s in between],
+            "transition_result": serialize_transition(t), "state_after": t.next_state.to_dict()}
+
+
 def _replay_resolution(work, old, new_seq, sl, mapped, fixups):
     new = copy.deepcopy(old)
     new.pop("event_hash", None)
@@ -169,12 +204,15 @@ def settle_changes(draft, events, created):
             change["changed_fields"] = sorted(name for name in _ACK_FIELDS if not same(new[name], old[name]))
 
 
-def plan_records(events, kept, superseded, plan_ops, sl):
+def plan_records(events, kept, superseded, plan_ops, sl, consume_inputs=None):
     """The working list after the restore point, operation by operation. kept are the effective seqs up to and
-    including the restore point; superseded the ones after it. Returns a Draft."""
+    including the restore point; superseded the ones after it (plan_ops names each of them once, in order, with the
+    CONSUME entries standing between). consume_inputs maps each CONSUME day to its (decision, fixed series item).
+    Returns a Draft."""
     work = [copy.deepcopy(events[s]) for s in kept]
     kept_set = set(kept)
     draft = Draft()
+    consumed_since = []                              # CONSUME days after the last APPLY that was not a CONSUME / restart
     new_seq = len(events) + 1                         # the RECOVERY_RESTORE record takes len(events)
 
     def mapped(target):
@@ -184,7 +222,21 @@ def plan_records(events, kept, superseded, plan_ops, sl):
             return target
         raise restore_invalid("ops", "restore_ref_unmapped")
 
-    for entry, seq in zip(plan_ops, superseded):
+    for entry in plan_ops:
+        if entry["op"] == CONSUME:
+            d = entry["d"]
+            new = _consume(work, d, new_seq, sl, *consume_inputs[d])
+            draft.entries.append({"op": CONSUME, "from_seq": None, "d": d, "seq": new_seq, "same_as_superseded": None})
+            draft.changes.append({"op": CONSUME, "from_seq": None, "kind": new["kind"], "d": d, "to_seq": new_seq,
+                                  "same_as_superseded": None, "changed_fields": []})
+            draft.consumed.append((d, new))
+            consumed_since.append(d)
+            draft.made.append(new)
+            draft.records.append(new)
+            work.append(new)
+            new_seq += 1
+            continue
+        seq = entry["from_seq"]
         op, old = entry["op"], events[seq]
         if op in (DROP, RETIRE):
             draft.entries.append({"op": op, "from_seq": seq, "d": None, "seq": None, "same_as_superseded": None})
@@ -196,9 +248,13 @@ def plan_records(events, kept, superseded, plan_ops, sl):
             draft.entries.append({"op": op, "from_seq": seq, "d": old["d"], "seq": new_seq,
                                   "same_as_superseded": same_flag})
             draft.reapplied.append((old, new))
+            draft.made.append(new)
+            draft.new_skips |= (set(new["skipped_sessions"]) | set(consumed_since)) - set(old["skipped_sessions"])
+            consumed_since = []
         else:                                           # REPLAY: the only operation left
             if old["kind"] == RESTART_UNKNOWN:
                 new, changed = _replay_restart(work, old, new_seq)
+                consumed_since = []
             else:
                 new, changed = _replay_resolution(work, old, new_seq, sl, mapped, draft.fixups)
             same_flag = None
diff --git a/v2_history_restore/values.py b/v2_history_restore/values.py
index 60cf7ed..f54a750 100644
--- a/v2_history_restore/values.py
+++ b/v2_history_restore/values.py
@@ -26,9 +26,11 @@ NO_CHANGE = "NO_CHANGE"
 OPERATION = "soxl-v2-history-restore-plan/1"
 REASON = "RESTORE_VERIFIED_RECORD"
 REAPPLY, REPLAY, DROP, RETIRE = "REAPPLY", "REPLAY", "DROP", "RETIRE"
-OPS = (REAPPLY, REPLAY, DROP, RETIRE)
+CONSUME = "CONSUME"
+OPS = (REAPPLY, REPLAY, DROP, RETIRE)        # the four operations that name a superseded record
 RECORD_KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, SCHEMA_MIGRATION)
 OP_KEYS = frozenset(["op", "from_seq"])
+CONSUME_KEYS = frozenset(["op", "d"])
 POINT_KEYS = frozenset(["seq", "event_hash"])
 CHANGE_KEYS = frozenset(["op", "from_seq", "kind", "d", "to_seq", "same_as_superseded", "changed_fields"])
 SERIES_KEYS = frozenset(["from_seq", "d", "prev_session_date", "series_previous_date", "row", "prev_row"])
@@ -45,7 +47,13 @@ _JSON_RULES = ("json_depth", "json_number", "json_key", "json_type")
 
 def change_ok(c):
     """One row of a plan's `changes` in its safe form: the fixed keys, an operation and a record kind of the fixed lists,
-    strict non-negative integers, a real day or None, a real bool or None, and field names of the fixed list only."""
+    strict non-negative integers, a real day or None, a real bool or None, and field names of the fixed list only. The
+    row of a CONSUME names no superseded record: from_seq is null, it makes an APPLY of a real day, and nothing is
+    compared with anything (no same flag, no changed field)."""
+    if isinstance(c, dict) and c.get("op") == CONSUME:
+        return (set(c) == CHANGE_KEYS and c["from_seq"] is None and c["kind"] == APPLY and is_date(c["d"])
+                and is_int(c["to_seq"]) and c["to_seq"] >= 0 and c["same_as_superseded"] is None
+                and c["changed_fields"] == [])
     return (isinstance(c, dict) and set(c) == CHANGE_KEYS and c["op"] in OPS
             and is_int(c["from_seq"]) and c["from_seq"] >= 0 and c["kind"] in RECORD_KINDS
             and (c["d"] is None or is_date(c["d"]))
@@ -64,8 +72,10 @@ def _row_ok(r):
 
 
 def series_item_ok(item):
-    """One fixed series input of a plan in its safe form (the keys of series_inputs, days, a row or None)."""
-    return (isinstance(item, dict) and set(item) == SERIES_KEYS and is_int(item["from_seq"]) and item["from_seq"] >= 0
+    """One fixed series input of a plan in its safe form (the keys of series_inputs, days, a row or None). The item of a
+    CONSUMEd day has from_seq null: no superseded record stands behind it."""
+    return (isinstance(item, dict) and set(item) == SERIES_KEYS
+            and (item["from_seq"] is None or (is_int(item["from_seq"]) and item["from_seq"] >= 0))
             and is_date(item["d"]) and is_date(item["prev_session_date"]) and is_date(item["series_previous_date"])
             and _row_ok(item["row"]) and (item["prev_row"] is None or _row_ok(item["prev_row"])))
 
```

### 4.2 既存試験4本（`git diff bfbde7a 3f780c1 -- tests/v2_history tests/v2_history_restore tests/v2_scope_chain`、108行。test_sc_03_scope.pyは1行の固定）

```diff
diff --git a/tests/v2_history/test_h06_restore_batch.py b/tests/v2_history/test_h06_restore_batch.py
index 628327e..8de4e29 100644
--- a/tests/v2_history/test_h06_restore_batch.py
+++ b/tests/v2_history/test_h06_restore_batch.py
@@ -160,13 +160,13 @@ class RestoreRefusals(unittest.TestCase):
                 got = H.rebuild_edit(full, 18, lambda r: r["replay"][0].update(op=op))
                 H.expect_rule(self, "restore_op_kind", got)
 
-    def test_consume_is_not_supported_in_b1(self):
+    def test_a_consume_entry_of_the_wrong_form_is_refused(self):
         def fn(r):
             r["replay"][0] = {"op": "CONSUME", "d": D[3]}
-        H.expect_rule(self, "restore_op_unsupported", H.rebuild_edit(self.ev, 7, fn))
+        H.expect_rule(self, "restore_replay_mismatch", H.rebuild_edit(self.ev, 7, fn))
         def fn2(r):
             r["replay"].append({"op": "CONSUME", "d": D[5]})
-        H.expect_rule(self, "restore_op_unsupported", H.rebuild_edit(self.ev, 7, fn2))
+        H.expect_rule(self, "restore_replay_mismatch", H.rebuild_edit(self.ev, 7, fn2))
 
     def test_ops_and_replay_must_agree(self):
         ev = H.deep(self.ev)
diff --git a/tests/v2_history_restore/test_r4_01_point_ops.py b/tests/v2_history_restore/test_r4_01_point_ops.py
index 98f2f5e..aa26799 100644
--- a/tests/v2_history_restore/test_r4_01_point_ops.py
+++ b/tests/v2_history_restore/test_r4_01_point_ops.py
@@ -142,8 +142,9 @@ class OperationList(unittest.TestCase):
 
     def test_consume_and_unknown_operations_are_refused_with_any_keys(self):
         unsupported = ("ops", "restore_op_unsupported")
-        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "from_seq": 3}], unsupported)
-        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "d": D[2]}], unsupported)
+        # C-1: CONSUME takes {op, d} only and names no superseded record
+        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "from_seq": 3}], ("ops", "ops_shape"))
+        self.bad([{"op": "DROP", "from_seq": 2}, {"op": "CONSUME", "d": D[2]}], ("ops", "superseded_mismatch"))
         self.bad([{"op": "DROP", "from_seq": 2}, {"op": "consume", "from_seq": 3}], unsupported)
         self.bad([{"op": "DROP", "from_seq": 2}, {"op": "MERGE", "from_seq": 3}], unsupported)
         self.bad([{"op": "DROP", "from_seq": 2}, {"op": "", "from_seq": 3}], unsupported)
diff --git a/tests/v2_history_restore/test_r4_09_scope.py b/tests/v2_history_restore/test_r4_09_scope.py
index e9b06f8..1e8abf6 100644
--- a/tests/v2_history_restore/test_r4_09_scope.py
+++ b/tests/v2_history_restore/test_r4_09_scope.py
@@ -27,7 +27,7 @@ ALLOWED_NAMES = {
     "v2_recovery.commands": {"check_commands"},
     "v2_recovery.project": {"apply_records", "check_versions"},
     "v2_persistence.codec": {"canonical_json", "sha256_text", "compute_event_hash"},
-    "v2_persistence.events": {"session_dict", "row_dict", "input_hash_of", "serialize_transition"},
+    "v2_persistence.events": {"session_dict", "row_dict", "input_hash_of", "serialize_transition", "decision_dict"},
     "v2_persistence.errors": {"PersistenceError"},
     "v2_core.state": {"MarketState"},
     "v2_core.fixture": {"parse_iso_date", "MarketRow"},
@@ -55,7 +55,13 @@ FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "uran
 LATER_STAGE_WORDS = ("unlock", "outbox", "webhook", "discord", "snapshot.json", "notify", "sheet", "historyreplacement",
                      "diagnos", "append_batch", "appendbatch", "adoption", "reinit", "publish", "cas_", "durab", "fsync",
                      "localfile", "memorystore", "journal")
-CONSUME_NAMES = {"requires_consume", "restore_requires_consume"}
+CONSUME_NAMES = {"requires_consume", "restore_requires_consume",
+                 # C-1 (a new APPLY for a day the operations set free): the fixed list of the names that hold the word
+                 "CONSUME", "CONSUME_KEYS", "consume_inputs", "consumed", "consumed_since", "_consume", "_consume_inputs",
+                 "_check_consumed_decisions", "_check_consumed_released", "_check_consumes", "_has_consume",
+                 "restore_consume_applied_day",
+                 "restore_consume_duplicate", "restore_consume_in_batch", "restore_consume_input",
+                 "restore_consume_no_decision", "restore_consume_not_released", "restore_consume_order"}
 OWN_CLASSES = {"RestorePlan", "RestoreConfirmResult"}
 PUBLIC = ["prepare_restore_plan", "confirm_restore_plan", "RestorePlan", "RestoreConfirmResult", "READY",
           "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
@@ -225,9 +231,9 @@ class Runtime(unittest.TestCase):
                     if "consum" in v.lower():
                         found.append((fname, v))
                         self.assertIn(v, CONSUME_NAMES, "%s: %s" % (fname, v))
-        # the one function that raises it and the one place that calls it, and nothing that makes a day of its own
+        # the stop of a freed day that is not consumed is still there, and the names of the consumption are the fixed list
+        self.assertTrue({"requires_consume", "restore_requires_consume"} <= set(v for _f, v in found))
         self.assertEqual(sorted(set(v for _f, v in found)), sorted(CONSUME_NAMES))
-        self.assertEqual(sorted(set(f for f, _v in found)), ["build.py", "errors.py"])
 
     def test_a_new_apply_is_made_only_from_the_day_of_the_record_it_replaces(self):
         sites = []
@@ -242,7 +248,7 @@ class Runtime(unittest.TestCase):
                             kind = node.values[keys.index("kind")]
                             if isinstance(kind, ast.Name) and kind.id == "APPLY":
                                 sites.append((fname, func.name, node, func))
-        self.assertEqual([(f, n) for f, n, _d, _fn in sites], [("records.py", "_reapply")])
+        self.assertEqual([(f, n) for f, n, _d, _fn in sites], [("records.py", "_reapply"), ("records.py", "_consume")])
         _f, _n, record, func = sites[0]
         keys = [k.value for k in record.keys]
         day = record.values[keys.index("d")]
@@ -288,7 +294,7 @@ class Runtime(unittest.TestCase):
         from v2_history_restore import values
         self.assertEqual(values.OPS, ("REAPPLY", "REPLAY", "DROP", "RETIRE"))
         b = R.ex_restart_between()
-        for op, rule in (("CONSUME", "restore_op_unsupported"), ("consume", "restore_op_unsupported"),
+        for op, rule in (("CONSUME", "ops_shape"), ("consume", "restore_op_unsupported"),
                          ("APPLY", "restore_op_unsupported"), ("", "restore_op_unsupported"), (None, "ops_shape"),
                          (1, "ops_shape")):
             ops = R.ops_of(b, 1, {"*": "DROP"})
diff --git a/tests/v2_scope_chain/test_sc_03_scope.py b/tests/v2_scope_chain/test_sc_03_scope.py
index d8877d5..5d7d316 100644
--- a/tests/v2_scope_chain/test_sc_03_scope.py
+++ b/tests/v2_scope_chain/test_sc_03_scope.py
@@ -10,7 +10,7 @@ import unittest
 import sc_helpers as C
 
 START = "b626c98af5f01bc94e7b41d86aadde9663695eb9"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"   # accepted (re-review 9fe3e19); frozen when C-1 began
 REV = END or "HEAD"
 
 FIVE = ("tests/v2_history_adopt/test_a5_08_scope.py", "tests/v2_history_diagnose/test_d5_08_scope.py",
```

## 5. 試行の差分（設計§7）との違いとその理由

試行の差分（docs/specs/V2_CONSUME_C1_TRIAL_20261103.diff、759行）は参考にとどめ、受入試験・欠陥注入の代わりにはしていない。ランタイムの差は9ファイルすべてにある（行単位の差分は`diff`で、試行を`bfbde7a`に適用したツリーと本実装の間）。主な違いと理由：

| # | 違い | 理由・影響 |
|---|---|---|
| 1 | **REAPPLYの前に置いたCONSUMEの日を「新たに飛ばす日」に数える**（`Draft.new_skips`と`consumed_since`）。試行は`new.skipped − old.skipped`のみ | 暦にセッションが加わったときのC1-06 3種目（REAPPLYで新たに飛ばす日の消費）。試行のままだと、CONSUMEの後のREAPPLYのskippedからその日が消え、解放日に数えられずrestore_consume_not_releasedになる。試験`test_a_day_a_reapplied_apply_newly_passes_over`が固定 |
| 2 | `_reapply`に位置の防御（`base < d`でなければ`restore_consume_order`、detail＝base） | CONSUMEを後の日に置くと、続くREAPPLYの基点（直前のAPPLYの日）がそのREAPPLYの日以降になり得る。この場合を明示して拒否する（試行にこの防御は無い。試行がこの入力で何を返すかは試していない）。試験`test_a_consume_in_front_of_an_earlier_reapplied_day_is_out_of_order_too` |
| 3 | 確認の段階1に「計画のopsと候補のRECOVERY_RESTOREのopsの一致」（CONSUMEを含むときだけ） | 本実装では、計画dictのopsだけを改変すると再計算が別の候補になり、`history_plan_stale`が返って`history_plan_mismatch`にならなかった（C1-13は改変＝mismatch）。試行でも同じかは試していない。CONSUMEが無い場合の動作は変えていない（C1-14で確認） |
| 4 | `targets_of`→`fixed_days`。値は`(from_seq, d, 保存したprev_session_date)`の組 | CONSUMEは退避記録を持たず`from_seq`がnull。名前は「固定する日」の意味に合わせた |
| 5 | `values.py`に`ALL_OPS`を足さず、`OPS`は4つのまま。`CONSUME`と`CONSUME_KEYS`だけ足した | 依頼書§2「OPSは4つのまま」。結果として`restore_op_unsupported`の対象にCONSUMEは入らない |
| 6 | `restore_invalid`に`detail`（日だけ）。CONSUME関係のエラーは日を載せる | 依頼書のエラー表に日を持たせる指定。値・自由文は載せない（C1-11の試験） |
| 7 | 検査器：CONSUMEの要素の形（from_seq／same＝null、dの日付）をnamed列の検査より先に行う。opsとの不一致は`request_basis` | 試行は形の検査を`_check_consumes`の中に置いていた。エラーの優先順位（形→ID→…）をC1-10で固定するため、形を先に見るようにした |
| 8 | 検査器：CONSUMEの位置の規則は`owners`を用いたバッチの間のみ（前後の集合の積）。計画側（points.py）は`norm`の添字で同じ規則 | 試行の`mark`変数の整理。振る舞いは同じ（変異3・3bで検出） |
| 9 | `_check_days_again`は`draft.made`（REAPPLYとCONSUMEをopsの順に並べたもの）を回す。試行は「REAPPLY全部、CONSUME全部」の順 | 作られた順の親状態で`evaluate_day`を呼ぶため。順序がC1-10の試験の期待 |
| 10 | `_consume_inputs`の行を`canonical_json`で並べる。ctx0→ctx、`by_day`→`fixed` | 行順に依存しない選択（select_decisionの入力を固定）。名前の整理 |
| 11 | 範囲試験・P-02：既存の名前`_replay_evidence`は「evidence」の語を持つが、B-4の既存試験が名前でスパイするため除外 | P-02は新しい名前・文字列に適用し、既存の名前を改名しない（依頼書§2：他の関数の振る舞いを変えない） |
| 12 | 試行の試験は範囲試験1本。本実装は受入C1-01〜C1-14のための4本と範囲試験1本、ヘルパー1本 | 受入試験は試行の代わりにしない（依頼書） |

試行にあって本実装に無いものは無い。試行の`ALL_OPS`は不採用（#5）。

## 6. 受入IDとテスト名の対応（tests/v2_history_consume/、計112件）

テスト名は`クラス.メソッド`を略した（ファイルはtest_c1_0X。メソッドの全名は`python -m unittest discover ... -v`で一覧できる）。

| ID | ファイル・クラス（件数） | 主な試験 |
|---|---|---|
| C1-01 回帰 | 既存の全スイート（§7）。補正6件を含み件数は開始点と同じ（1634＋範囲の鎖34＝1668） | — |
| C1-02 記録の形 | 01 Form（3）、EntryForm（6） | `test_the_restore_record_and_the_created_apply_have_the_fixed_form`、`test_the_replay_entry_has_exactly_five_keys`、`test_the_ops_entry_is_the_op_and_the_day_of_the_replay_entry`、`test_ops_and_replay_have_the_same_length` |
| C1-03 検査器 | 01 Operations（3）、Rules（8）、Batches（4）。独立ビルダー（h_helpersのHB）で作った履歴の改変 | `test_the_day_of_a_superseded_apply_is_refused`、`test_the_same_day_twice_is_refused`、`test_between_two_records_of_one_request_it_is_refused`（REPLAY・DROP両方）、`test_a_day_that_is_not_the_day_of_the_created_apply_is_refused`、`test_the_created_record_is_an_apply`、`test_a_history_that_ends_inside_the_batch_is_incomplete`、`test_the_created_apply_is_checked_by_the_ordinary_rules`（S1射影） |
| C1-04 成功例 | 02 Examples（5）：READY→CONFIRMED_IN_MEMORY→同じ候補へのNO_CHANGE。候補をvalidate_historyとproject_history_ledgerに通す | 宣言の間／再開始の飛び越し／宣言＋LATE ACK／宣言の後にAPPLYなし／APPLYのない区間の再開始 |
| C1-05 独立性 | 02 Independence（2）＋Examplesのoracle | `test_a_cancelled_declaration`、`test_a_cancelled_restart`。期待値はHB.apply_content（S1 prepare_day）と`evaluate_day`で試験側が作る（c1_helpers.oracle）。実装の出力は使わない |
| C1-06 解放日 | 02 FreedDays（9） | `test_the_day_of_a_dropped_declaration`、`test_the_sessions_a_dropped_restart_had_passed_over`、`test_a_dropped_restart_whose_base_is_the_initial_state`、`test_a_day_a_reapplied_apply_newly_passes_over`（暦にセッションを加える合成入力）、`test_the_day_a_replayed_declaration_keeps_is_not_freed`、`test_a_day_outside_the_freed_range_is_not_freed`、`test_a_day_after_a_restart_that_is_replayed_is_not_freed`、`test_a_day_before_the_base_or_the_base_itself_is_out_of_order` |
| C1-07 停止 | 03 Stop（4） | `test_the_declared_day_with_a_decision_stops_without_a_consume`、`test_one_of_two_days_consumed_stops_at_the_other` |
| C1-08 決定 | 03 Decision（8） | `test_a_day_without_a_decision_is_refused`、`test_the_selection_errors_of_the_core_are_returned_as_they_are`、`test_a_declaration_and_a_late_acknowledgement_that_are_dropped_give_the_later_decision`（L2）、`test_the_rows_that_the_kept_records_leave_are_the_rows_the_decision_is_chosen_from`（変異7の後で追加）、`test_a_decision_that_the_whole_candidate_does_not_give_any_more_is_refused`、`test_the_real_selection_is_asked_twice_for_a_consumed_day_and_agrees` |
| C1-09 市場値 | 03 Market（8） | `test_the_rows_of_the_consumed_day_are_fixed_from_the_series`、`test_a_previous_day_that_differs_between_the_series_and_the_sessions_is_refused`、`test_a_series_that_does_not_answer_in_the_expected_form_is_a_fixed_error`、`test_a_row_changed_after_the_plan_makes_the_confirmation_stale` |
| C1-10 順序 | 03 Order（8） | `test_the_stages_run_in_the_fixed_order_and_evaluate_day_comes_last`、`test_evaluate_day_is_called_once_for_every_reapplied_and_consumed_day_after_the_projection`、`test_the_freed_days_come_before_the_check_of_the_candidate` ほか |
| C1-11 差の表示 | 03 Shown（3） | `test_the_change_rows`、`test_the_summary_and_the_repr_show_no_value` |
| C1-12 無効果 | 03 NoEffect（3） | `test_a_consume_is_never_a_plan_without_effect`、`test_a_drop_alone_is_still_an_effect` |
| C1-13 確認 | 04 Tampering（10） | `test_a_changed_day_place_or_row_of_the_consume_is_a_mismatch`、`test_a_consume_of_the_wrong_form_is_refused_in_the_first_stage`、`test_a_wrong_confirmation_hash_is_a_mismatch`、`test_a_changed_row_of_the_consumed_day_is_stale` |
| C1-14 互換 | 04 Unchanged（5） | bfbde7aの`git show`から読み込んだ旧パッケージ（名前v2_history_restore_bfbde7a、書き込みなし）を同じ入力で比較：`test_the_plans_and_the_candidates_are_the_same_characters`、`test_the_refusals_without_consume_are_the_same`、`test_the_difference_is_the_consume_only`、`test_the_existing_b4_expectations_are_the_same_text` |
| C1-15 P-02 | 09 P02（3） | `test_no_import_of_the_adoption_or_diagnosis_packages`、`test_no_name_or_string_of_the_adoption_evidence_or_the_discarded_part`、`test_the_package_reads_no_record_of_the_adoption` |
| C1-16 範囲の値 | 09 Chain（3） | `test_the_previous_range_ends_where_this_one_starts_and_this_is_the_only_open_range`（START＝bfbde7a、END＝None、REV＝END or "HEAD"）、`test_the_whole_chain_has_no_gap`（先頭adfdf765）、`test_the_range_values_of_this_file_are_those_read_from_the_text` |
| C1-17 自分の範囲 | 09 FilesChanged（6）、PathJudgement（2） | `test_exactly_the_runtime_files_and_the_five_tests_are_modified_and_the_additions_are_allowed_paths`、`test_everything_else_is_blob_identical_to_the_code_start`、`test_the_four_corrected_tests_are_the_pinned_hunks`、`test_the_freeze_of_the_previous_range_is_one_line` |
| C1-18 範囲監査 | 09 RuntimeAudit（4）、SideEffects（5） | `test_no_forbidden_import_call_or_attribute`、`test_the_imports_are_those_of_the_code_start_and_the_listed_new_names`、`test_no_dependency_file_and_no_new_public_name`、`test_only_allowed_imports_and_no_io_clock_random_or_network`、`test_the_tests_leave_no_bytecode_or_file_to_add` |

C1-14の方法：同じ入力（CONSUMEを含まない復元計画の各例と拒否の例）を、現在のパッケージと、`git show bfbde7a:...`から読み込んだ旧パッケージ（名前v2_history_restore_bfbde7a、書き込みなし）の双方に与え、basis・候補・拒否の文字列を比べた（`test_the_plans_and_the_candidates_are_the_same_characters`、`test_the_refusals_without_consume_are_the_same`）。CONSUMEを含む入力は旧版でrestore_op_unsupported、新版でokになる（`test_the_difference_is_the_consume_only`、1例）。さらにB-4の最初の例でbasisが23キー・operation名が同じ・REAPPLYのseries項目のfrom_seqが非nullであることを確かめる（`test_the_existing_b4_expectations_are_the_same_text`）。既存B-4の165件が補正6件を除いて元の期待値のまま合格することも併せて、不変の根拠とする。

## 7. 結果（Linux 6.18、`unshare -n -r`下、別クリーンクローン・core.autocrlf=false、試験対象3f780c1）

各版を別のクリーンクローン（ローカルの実装リポジトリからの完全な履歴、shallowでない、`git checkout 3f780c1`）で、`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`（新規だけ`test_c1_*.py`）。版：3.10.20（uvの単体）、3.11.18、3.12.3、3.13.18。**4版とも12スイートすべてrc＝0、失敗0、error0。**

| スイート | 件数 | 結果（4版共通） |
|---|---|---|
| v2_core | 197 | OK |
| v2_persistence | 170 | OK |
| v2_persistence_local（S2） | 113 | OK、skip 4（Windows専用） |
| v2_recovery（S3-A） | 176 | OK |
| v2_history（B-1） | 230 | OK（補正のh06を含む） |
| v2_history_ops（B-2） | 173 | OK |
| v2_history_restart（B-3） | 109 | OK |
| v2_history_restore（B-4） | 165 | OK（補正のr4_01・r4_09を含む） |
| v2_history_diagnose（B-5a） | 131 | OK |
| v2_history_adopt（B-5b） | 170 | OK |
| **既存計** | **1634** | **1630合格＋Windows専用4 skip（開始点と同数）** |
| v2_scope_chain | 34 | OK、skip 0（sc_03のENDの固定を含む） |
| **v2_history_consume（新規）** | **112** | **OK、skip 0** |
| 合計 | 1780 | 1776合格＋4 skip |

C1-01の「1668件」は既存1634＋範囲の鎖34で、件数は開始点と同じ。ネットワーク遮断は`unshare -n -r`と各試験内のsocket禁止を併用した。**Windowsは未実施**（Windows機が無い）。他者・ユーザーPCの結果で代用していない。

### 7.1 `git archive`のツリー（.gitなし、Python 3.13.18）の skip

履歴の無いツリーでは、Gitを読む範囲試験はfailではなくskipになる。完全なクローンの件数と比べること。

| スイート | 件数 | skip |
|---|---|---|
| v2_history_consume | 107（検出された件数。クラス単位のskipが1件に数えられるため完全なクローンの112と異なる） | 22 |
| v2_scope_chain | 34 | 33（PathJudgementの1件だけ実行） |
| v2_history_ops（b17） | 173 | 3 |
| v2_history_restart（r3_07） | 109 | 3 |
| v2_history_restore（r4_09） | 165 | 5 |
| v2_history_diagnose（d5_08） | 131 | 8 |
| v2_history_adopt（a5_08） | 170 | 10 |
| 既存5本のFilesChanged計 | | **29**（開始点の29件と同数） |

いずれもrc＝0。archiveのツリーでskipされた件数を、合格の件数に数えていない。

### 7.2 結果文書を足した後の確認

本書だけを加えた最終コミットで、範囲試験（v2_history_consume test_c1_09）と鎖（v2_scope_chain）をもう一度実行する（push報告に記す）。

## 8. 限定欠陥注入（依頼書§5、試験対象3f780c1を使い捨てのクローンで1件ずつ壊す）

ランナー：共有フォルダ implementation/c1_consume_20261103/mutate.py（文字列置換が1回だけ一致することを確かめ、新規の受入試験、見つからなければB-1／B-2／B-4＋範囲の鎖を実行する。範囲試験の変異16・17は使い捨てのコミットにして範囲試験を実行する）。分類は、検出／等価／未検出／準備失敗。

| 依頼書の項目 | ID | 変異 | 結果 | 検出した試験（一部） |
|---|---|---|---|---|
| 1 | 1 | 検査器：CONSUMEの日と作られたAPPLYの日の比較を省く | 検出 | `test_a_day_that_is_not_the_day_of_the_created_apply_is_refused` |
| 2 | 2 | 検査器：退避APPLYの日の規則を省く | 検出 | `test_the_day_of_a_superseded_apply_is_refused` |
| 3 | 3 | 検査器：requestバッチの間の規則を省く | 検出（2件） | `test_between_two_records_of_one_request_it_is_refused` |
| 3 | 3b | 同：REPLAYの場合だけ規則を残す | 検出 | 同上 |
| 4 | 4 | 検査器：重複の規則を省く | 検出 | `test_the_same_day_twice_is_refused` |
| 5 | 5 | 計画：解放日の検査を省く | 検出（6件） | `test_a_day_outside_the_freed_range_is_not_freed` ほか |
| 6 | 6a | 解放日の集合からDROPした宣言を落とす | 検出（15件） | 宣言の成功例・確認の試験 |
| 6 | 6b | 同：DROPした再開始を落とす | 検出（4件） | `test_the_sessions_a_dropped_restart_had_passed_over` ほか |
| 6 | 6c | 同：REAPPLYで新たに飛ばす日を落とす | 検出（2件） | `test_a_day_a_reapplied_apply_newly_passes_over` ほか |
| 7 | 7 | 計画：決定を残す記録の行でなく生の台帳から選ぶ | **検出**（最初の版では未検出→試験を1件追加、§10） | `test_the_rows_that_the_kept_records_leave_are_the_rows_the_decision_is_chosen_from` |
| 8 | 8 | 計画：段階7の選び直しを省く | 検出（3件） | `test_the_real_selection_is_asked_twice_for_a_consumed_day_and_agrees` ほか |
| 9 | 9 | 計画：CONSUMEの日を`evaluate_day`の再計算から外す | 検出（2件） | `test_evaluate_day_is_called_once_for_every_reapplied_and_consumed_day_after_the_projection` |
| 10 | 10 | 計画と確認：series_digestにCONSUMEの日が入らない | 検出（3件） | `test_a_changed_row_of_the_consumed_day_is_stale` ほか |
| 11 | 11 | 計画：無効果の規則でCONSUMEを数えない | **等価**（下記） | 検出なし |
| 12 | 12 | 計画：CONSUMEの位置（基点＜D）の検査を省く | 検出 | `test_a_day_before_the_base_or_the_base_itself_is_out_of_order` |
| 13 | 13 | 計画：解放日の検査をhashの後（候補の検査の後）へ移す | 検出（4件） | `test_the_freed_days_come_before_the_check_of_the_candidate` ほか |
| 14 | 14 | 確認：現在のseriesの読み直しでCONSUMEの日を落とす | 検出（17件） | 成功例・確認の試験 |
| 15 | 15 | 形の検査でCONSUMEの行のfrom_seq＝null以外を受け付ける | 検出 | `test_a_row_of_the_wrong_form_is_not_shown` |
| 16 | 16 | 範囲試験：新しい範囲試験が作業ツリーを読む（`open(__file__)`を足す） | 検出 | `SideEffects.test_only_allowed_imports_and_no_io_clock_random_or_network` |
| 17 | 17 | 既存試験4本の補正の固定行を1行変える | 検出 | `FilesChanged.test_the_four_corrected_tests_are_the_pinned_hunks` |

計：17項目、細分20件。検出19、等価1、未検出0、準備失敗0（最終版）。

**変異11が等価である根拠**：CONSUMEがあってDROPが無い計画が無効果の規則に届くには、CONSUMEが「解放日」でなければならない（そうでなければ`restore_consume_not_released`で先に拒否される）。解放日はDROPした宣言・DROPした再開始・REAPPLYが新たに飛ばす日のどれかで、DROPが無ければ最後の種類だけである。その場合、REAPPLYの前にCONSUMEが挟まるので、そのREAPPLYの親状態が変わり、`same_as_superseded`は必ずfalseになる。したがって「DROPもCONSUMEも無く全REAPPLYがsame」の元の条件と「DROPが無く全REAPPLYがsame」の変異の条件は、CONSUMEを含む計画では一致する。測定：使い捨てのクローン（ランタイムは3f780c1と同じ）で元の条件と変異の条件をこの箇所で計算し、新規の受入試験89件を実行した。CONSUMEを含む計画61回でこの規則に到達し、両者が異なった回数は0だった。等価の判断は根拠であって、試験で殺せるわけではない（同一入力の振る舞いが同じため）。

最初の実行で変異7の置換が`build.py`の2か所に一致し、準備失敗になった。ランナーの置換を一意になる文脈（前の行）付きに直して再実行した。その結果、変異7は最初の版の試験では未検出だったので、スタンドインの試験を1件足して検出した。

## 9. 保護参照

依頼書§7の70参照に資料ブランチdocs/v2-consume-s3c-20261103（a6340c3937092e4cb658913b9acfb4973a084326）を加えた**71参照**を、`git ls-remote origin`の完全SHAで照合した（共有フォルダ implementation/c1_consume_20261103/ の protected_refs.txt と refcheck.py）。**開始時（実装ブランチを作る前）**と、結果文書を書く直前（push前）の2回とも71件とも一致、不一致0。push後の照合は、結果文書が別コミットのため本書には書かず、スレッドの報告に記す。

## 10. 未実施・制限

- Windows（実機）と、ユーザーPCでの実行は未実施。他者の結果で代用していない。
- 段階7の`restore_decision_changed`（消費した日）と、変異7の「残す記録の行」の使い方は、実入力では差が出る場合を作れなかった（残す記録が解放日の決定の行を除外する入力を作れなかった。作れないことの証明はしていない）。そのため試験は、変異を殺すためにunchangedの`select_decision`と`apply_records`のスタンドイン（試験側で答えを決めた差し替え）を使う。実入力で到達できることの証明ではない。実入力の反例が見つかれば報告する。
- 履歴検査器の合格は、解放日・決定・市場値の照合を意味しない。それは計画側（と確認）の検証で、台帳・暦・seriesを注入した場合に限る。ライブの保存先・前史・価格改訂・入力／通知接続は後工程で、本段階では扱っていない。
- 変異11は等価と判断した（§8）。試験で殺せないことは、試験の網羅の欠落ではなく入力が存在しないことによる、という判断である。
- 市場の約定・NBBO・分足は扱っていない。目視F&Gの値・時刻は履歴で上書きしていない。損切り・売却推奨・株数・金額・注文案内は追加していない。
- C-2〜C-4、B-4§7.1の既知の制限の解消、B-5b再レビューP-01（a5_09のfloat）、範囲試験の固定レビューのP-02には触れていない。

## 11. 作業記録

- 開始：2026-11-03（日本時間）。クローンは完全な履歴（shallowでない）。モデル別の利用量は未計測。
- 開始時に保護71参照の完全SHAを照合し全件一致。実装ブランチをbfbde7aから作成。
- ランタイムの実装後、B-4の既存試験`test_r4_09_scope`のCONSUME_NAMESが、確認に足した`_has_consume`を許可していないのを、全スイートの実行で見つけて補正に足した（補正6件の範囲内、PINNEDを作り直し）。
- 未コミットの`__pycache__`が一度ステージされたが、`git add`前に消した。以後`PYTHONDONTWRITEBYTECODE=1`と`python -B`で実行し、コミットは3f780c1・c63912aにバイトコードを含まない。
- 実装中、何度か中間のコミット（wip）を作ったが、push前に`git reset --soft bfbde7a`で2つのコミット（ランタイムc63912a、試験3f780c1）に作り直した。pushしたコミットに中間のものは含まれない。
- 変異7が未検出だったので試験を1件足し、3f780c1を作り直して、全スイート4版・欠陥注入・archiveをやり直した（本書の数値はすべて3f780c1）。
- 共有フォルダ implementation/c1_consume_20261103/ に、ランナー（mutate.py、runall.sh）、保護参照の照合（refcheck.py、protected_refs.txt）、差分全文、欠陥注入の出力を置いた。
