# V2 S3-B-3 UNKNOWN再開始の計画・確認 限定実装 結果記録

作成日：2026-11-02（日本時間）。担当：Claude Sonnet 5.5（実設定の確認は§1）。
状態：**限定実装・自己試験まで完了。レビュー待ち。PR・マージ・B-4以降・S3-Cには進んでいない。**
B-3は**候補Historyまで**である。上位§9のバッチ統合・保存・耐久性は達成していない（§9）。

## 1. 固定入力・モデル・SHA

| 項目 | 値 |
|---|---|
| 採用 | Rockyが2026-11-02にD-1〜D-3を採用し、B-3限定実装を承認（スレッドの指示）。 |
| モデルの実設定 | セッション情報の確認結果：configured_model＝`claude-sonnet-5-5[1m]`、session_context.model＝`claude-sonnet-5-5[1m]`、last_served_model＝`claude-sonnet-5-5`、effort_level＝`high`。D-3（Sonnet 5.5・high）と一致。 |
| 固定した資料 | 資料ブランチ docs/v2-history-s3b3-revision-20261030 の**d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba**（途中で追従していない） |
| 依頼書blob | docs/tasks/V2_RECOVERY_S3B3_LIMITED_IMPLEMENTATION_REQUEST.md ＝ 437e10dbcff36043cb377e0a8f9796b62c63e9c0 |
| 設計書blob | docs/specs/V2_RECOVERY_S3B3_RESTART_UNKNOWN_DESIGN_DRAFT.md ＝ 48afb2ebb0c4be2147b2e06d751ba32630f6b681 |
| コード開始点 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb（fix/v2-history-s3b2-review-20261030） |
| 実装ブランチ | feat/v2-history-restart-s3b3-20261102（b328844から作成。同名は無かった） |
| 試験対象SHA | **7d75ea5dbee1f6cef9912fceced2c2be2e48fad9**（コード・試験の最終。コミット fbed004 → 7d75ea5） |
| 保存最終SHA | 本文書だけを加えた次のコミット（コミット後にスレッドで報告。本文書にはSHA自身を書けない） |
| 保護参照 | 依頼書§7の45参照＋資料ブランチ d0e11d9＝46参照。開始時（2026-11-02T01:49:08Z）と、本文書の保存直前（02:11:16Z）に完全SHAで照合し、どちらも46/46一致。push後の終了時の照合はスレッドで報告 |

読んだもの：CLAUDE.md、依頼書、設計書。STATUS・MODEL_POLICY・ROADMAPは、依頼が指示する範囲（B-2までの採用を取り直さない）に従い、内容の確認は依頼書・設計書の記述に依拠した。コードの変更はこれらに触れていない。

## 2. 作ったもの

新規パッケージ `v2_history_restart/`（6ファイル）：`prepare_restart_plan`、`confirm_restart_plan`、`RestartPlan`、`RestartConfirmResult`、定数 `READY`／`CONFIRMED_IN_MEMORY`／`NO_CHANGE`。`__all__` は設計どおりの7名。既存パッケージの `__init__.py` への再公開は無い。

| ファイル | 内容 |
|---|---|
| `build.py` | 準備と確認で共有する処理。設計§4の順序（元履歴→sessions・日付・台帳行→check_dとresume→requested_at・ID→floor・上限・無効果→元履歴のB-2投影→新記録と候補全体）。戦略式・閾値・状態式は無い |
| `prepare.py` | `prepare_restart_plan` |
| `confirm.py` | `confirm_restart_plan`（計画自身→入力→digest／head→元履歴からbasis全体を再構築。枝Bは物理prefixを検査して元履歴を復元） |
| `values.py` | 不変な `RestartPlan`／`RestartConfirmResult`。B-2の内部名 `_Frozen` は使わず、同等の値型を自前で持つ |
| `errors.py` | `restart_invalid`（指定ミス、field／rule付き）と、内部不整合用の1つ |

利用した既存の公開名は設計§3の一覧の範囲だけ。private名、Chain／ledger_of、`_Frozen`、LedgerContext／FixedFactsの代用品、HistoryAppendBatch、B-2の日次・計画関数は使っていない（AST試験で確認）。

## 3. 全差分

開始点 b328844 から 7d75ea5 まで、16ファイル、+2332／−5。

- **新規**：`v2_history_restart/`（__init__、build、confirm、errors、prepare、values）、`tests/v2_history_restart/`（r3_helpers.py、r3_sensitivity.py、test_r3_01〜07の7ファイル）。`tests/v2_history_restart/` に `__init__.py` は無い。
- **変更した既存ファイル：`tests/v2_history_ops/test_b17_scope.py` の1つだけ**（+8／−5）。それ以外の既存ファイル（ランタイム、既存試験・fixtures、依存、設定、workflow、main.py、研究、STATUS／ROADMAP／CLAUDE）の差分は0（`test_r3_07_scope.py` が `git diff` で確認）。
- 本文書 `docs/implementation/V2_RECOVERY_S3B3_RESULT.md` は新規。旧B-2結果文書には追記していない。

### 旧範囲試験 `test_b17_scope.py` の差分全文（設計§2.4の3点）

```diff
@@ -181,9 +181,11 @@ class FilesChanged(unittest.TestCase):
         for status, path in changed:
-            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/"))
+            allowed = (path.startswith(("v2_history_ops/", "tests/v2_history_ops/",
+                                        "v2_history_restart/", "tests/v2_history_restart/"))
                        or path in ("v2_recovery/facts.py", "v2_recovery/commands.py",
-                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md"))
+                                   "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",
+                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))
@@ -194,8 +196,8 @@ class FilesChanged(unittest.TestCase):
         for path in paths:
-            self.assertFalse(path.endswith("__init__.py") and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")),
-                             path)
+            self.assertFalse(path.endswith("__init__.py") and path != "v2_history_restart/__init__.py"
+                             and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)
@@ -210,7 +212,8 @@ class FilesChanged(unittest.TestCase):
     def test_existing_tests_and_fixtures_are_untouched(self):
-        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops")
+        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_ops",
+                       ":(exclude)tests/v2_history_restart")
```

3点＝(1)許可リストに新規2ディレクトリと結果文書を足す、(2)旧試験無変更のGit検索から新規B-3試験を除く、(3)末尾の `__init__.py` 検査に `v2_history_restart/__init__.py` の単一パスだけを例外にする。機能試験、旧ランタイムのAST検査、禁止機能、公開名の試験は無変更。gitが1の許可リストの2行を別の変更箇所として数えるため、`-U0` の差分は4ハンクになる。`test_r3_07_scope.py` が削除行5本・追加行8本をすべて文字列で照合し、この3点以外の緩和や対象漏れがあれば失敗する。

## 4. 受入とテスト名の対応（新規109件）

新規Nは**109件**（実測。増えた件数だけで品質は主張しない）。ファイル別：01＝15、02＝15、03＝30、04＝16、05＝8、06＝14、07＝11。

| 受入 | ファイル：クラス（主な試験） |
|---|---|
| B3-01 回帰・差分 | §6の既存スイート（無編集）＋`test_r3_07`：FilesChanged（許可パス、旧ランタイム等の差分0、旧範囲試験の差分の厳密照合） |
| B3-02 有効floor | `test_r3_01`：EffectiveFloor（全区間、宣言だけが最新、初期状態＋宣言、再開始を複数回、DROPした宣言・再開始を含めない、例R、物理配列に宣言が残るspy） |
| B3-03 下限・上限・無効果 | `test_r3_01`：BoundsAndNoEffect（成分ごとの下限、上限、無効果と境界前進、等号の準備・確認・再確認、旧文脈差とfloorが重なる場合のfloor優先） |
| B3-04 sessions | `test_r3_02`：Sessions（resumeの不存在／未確定＝restart_boundary、check_dの既存InputError4種と前後両方不足、次セッション未確定でも正常、旧applyのnext(D)のclose／confirmedは無害・openは有害、不正sessions／行／日付はID照合より前、旧境界差＋使用済みIDはconflict・未使用IDはcontext error） |
| B3-05 元履歴の照合 | `test_r3_02`：OriginalLedgerProjection（project_history_ledgerのspy＝元履歴・check_d、ledger_mismatch、late_observation、B-2のACK後は成功、record_id_conflict、入力非変更） |
| B3-06 記録・候補 | `test_r3_03`：RecordAndCandidate（15キー・5キー・20キー・hash、過去eventsの完全一致、有効／退避seq、現在状態、validate_historyのspy、独立ビルダーHBが書く記録との一致、例Rの退避記録）、InternalInvariants（validate_history／read_effective／history_dictの置換で設計§8の保存内容の検査を単独で確認） |
| B3-07 物理先頭 | `test_r3_03`：ParentIsThePhysicalHead（ACK／DECLARE／RESTORE／RESTART／MIGRATIONが先頭、現在区間の最後のAPPLYを親にしない、migrated_sourcesの元二値が不変） |
| B3-08 ID | `test_r3_03`：RequestIds（新IDのみREADY、例Rのq1〜q6、NATIVE／REPLAYED／MIGRATED、退避だけのID、他種別のID、同ID同内容・時刻だけ違いはconflict、同じ計画の再確認との対照、旧境界の時刻差との重なり） |
| B3-09 計画の結合 | `test_r3_03`：PlanBinding（20項目それぞれの改変＋hash付け直しの拒否コード、候補記録の改変、hashだけの付け直し、同一入力同一hash・時刻だけ違いはrequest_hash同一） |
| B3-10 確認A | `test_r3_04`：ConfirmAgainstTheOriginal |
| B3-11 確認B | `test_r3_04`：ConfirmAgainstItsOwnCandidate（resume==check_dを含む、prefixのvalidateのspy、prefix不一致の拒否、先へ進んだ履歴はstale、再構築より前に失敗するspy） |
| B3-12 日次接続 | `test_r3_05`：DailyAfterTheRestart（境界以前の拒否、F&G3帯、gap=false、欠測日のskipped、後発の停止、ALREADY_APPLIED、新ランタイムに数値の閾値が無いAST） |
| B3-13 ACK・宣言後 | `test_r3_05`：AckAndDeclareAfterTheRestart（等号再開始でtarget_not_after_boundary、後のcheck_dで宣言→frontier＝resume・境界不動、旧skipped／宣言の後発とLATEのACK） |
| B3-14 不変性・秘匿 | `test_r3_06`：Immutability（コピー、偽コンテナ、深いJSON・巨大整数・非有限・非str鍵・非JSON型、bool／float整数の拒否、属性変更不可、summaryのホワイトリスト、URL・値・自由文を出さない） |
| B3-15 型の境界 | `test_r3_06`：StoresRefuseEveryValue（旧MemoryStoreとfile_sync_onlyのLocalFileStoreがplan_typeで拒否、残留物なし、batch・ledger属性なし） |
| B3-16 範囲・停止 | `test_r3_07`：Runtime（許可import・名、旧機構名・private名・I/O・時計・later-stage語の不存在、公開名＝7名、ファイル構成、試験名の一意性・`__init__.py`なし）、FilesChanged（上記） |

## 5. 実行結果

条件：core.autocrlf=falseの別クリーンクローン（実装ブランチを単一ブランチで取得、HEAD＝試験対象SHA 7d75ea5、作業ツリー差分0）。各スイートを `-B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`（新規のみ `test_r3_*.py`）で実行。OS：Linux 6.18 x86_64。

| 区分 | Python | コア197 | 保存170 | S2 113 | S3-A 176 | B-1 230 | B-2 173 | 新規N 109 |
|---|---|---|---|---|---|---|---|---|
| unshare -rn＋プロセス内socket禁止 | 3.10.20（uv単体） | OK | OK | OK（skip 4） | OK | OK | OK | OK |
| 同上 | 3.11.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK |
| 同上 | 3.12.3 | OK | OK | OK（skip 4） | OK | OK | OK | OK |
| 同上 | 3.13.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK |
| プロセス内socket禁止のみ | 3.13.18 | OK | OK | OK（skip 4） | OK | OK | OK | OK |

5構成×7スイート＝35実行で failures=0、errors=0、終了コード0。S2の113件はLinuxで109合格＋4 skip（Windows専用）で、契約どおり。既存の合計は1059件（1055合格＋4 skip）。新規Nは別に集計した。`unshare -rn` 内で外部へのconnectが `Network is unreachable` になることを確認した。
B-2の173件は、範囲検査1ファイルの限定補正を含む（既存試験が全て無編集とは報告しない）。旧機能試験は1行も編集していない。作業ツリーでの実行（開発中）でも、新規は3.10／3.11／3.12／3.13で合格した。

## 6. 候補と再確認の例（例U、合成データ。requested_at＝2026-06-01T00:00:00Z）

history：0 GENESIS D0、1 APPLY D1、2 APPLY D2（D0＝2026-03-02、D3＝2026-03-05）。
- prepare(resume_after＝D3, check_d＝D3, request_id＝r1) → READY。plan_hash＝92aa9f60c7c939d47f8ff038340f892f2d299249cbe78320f43fce339b224bf1。確認で #3 RESTART_UNKNOWN（parent_seq＝2、floor＝{last_apply_d＝2026-03-04, last_declared_d＝null, prev_boundary＝2026-03-02}、state_after＝初期状態）。元の3件は同じ。独立ビルダーHBの記録と全キー一致。
- 同じ計画を候補に再確認 → NO_CHANGE、イベント数は4のまま（2件目なし）。候補で同IDの新しいprepare → history_request_conflict／request_id。
- prepare(resume_after＝D3, check_d＝D4) の plan_hash＝b268ca9f0ae456b67076201ae2516a647264b928a1c7a102a7c9dc4f1157a68f。
- 候補へB-2の日次：D1〜D3はtarget_not_after_boundary。D4のF&G 31→streak＝1・armed＝UNKNOWN・gap＝false、27→streak＝0・prev_normal_raw＝TRUE、20→armed＝FALSE。D4なし→D5：D4はNO_COMMIT、D5のskipped＝[D4]・gap＝false。その後の後発D4はlate_observation、D5の再実行はALREADY_APPLIED。

## 7. 限定欠陥注入（依頼§5の18項目、34変異）

`tests/v2_history_restart/r3_sensitivity.py`。作業ツリーを一時ディレクトリへ複製し、1件ずつ壊して新規スイートを実行する。対照（無変異）は合格。**34変異すべてが検出された。等価としたものは0**。1回目の実行では M17b（枝Bで元prefixのdigest／head／stateとplanの比較を省く）が未検出だった。最後に全basisを再構築して比較するため、結果の値は変わらないことが原因で、この比較が再構築より**前**に行われることを `build_restart` の呼出し回数で確かめる試験を追加し、再実行で検出された（今回の保存対象は追加後の7d75ea5）。

検出元の分類（P-04）。**A**＝B-3自身の事前検査（codeが変わる／誤拒否・誤受理を試験が直接検出）、**B**＝既存validate_historyの独立した防護も同じ誤りを止める（codeがhistory_invalidへ変わり、依頼の期待 restart_invalid と食い違う。誤った候補が受理されたわけではない）、**C**＝委譲・呼出しの契約（spy／置換）で検出。

| 項目 | 変異 | 結果 | 分類・メモ |
|---|---|---|---|
| 1 | M01a floorに物理配列の宣言（退避含む）を入れる | 検出（3件） | A。誤ってrestart_floorで拒否（DROPした宣言の例） |
| 1 | M01b last_apply_dに境界日を混ぜる | 検出（6件） | A |
| 2 | M02a 旧区間の宣言を落とす | 検出（2件） | A＋B（B-1がhistory_invalid／restart_floor） |
| 2 | M02b 旧区間のAPPLYを落とす | 検出（4件） | A |
| 3 | M03a prev_boundaryを下限に使わない | 検出（3件） | A（下限の比較だけが緩む。記録のfloorは正しいままなのでB-1は止めない） |
| 3 | M03b prev_boundaryが最初の区間の日付 | 検出（6件） | A＋B（history_invalid／restart_floor） |
| 4 | M04a 無効果を受理 | 検出（4件） | A＋B（B-1がhistory_invalid／restart_noop。codeの食い違いで検出） |
| 4 | M04b 境界前進まで拒否 | 検出（8件） | A |
| 5 | M05 resume==check_dを拒否 | 検出（33件） | A |
| 6 | M06a resumeの確定を見ない | 検出（1件） | A＋B（history_invalid／restart_boundary） |
| 6 | M06b 別日のセッションを境界に書く | 検出（57件） | A＋B（B-1がrestart_boundaryで止める。resume==check_dなら同じ値で成立する） |
| 7 | M07 元履歴の投影を省く | 検出（67件） | C＋A（spy・台帳不一致の各試験） |
| 8 | M08 親を最後のAPPLYにする | 検出（17件） | B（history_invalid／audit_hash）。A側の独自検査は無く、候補の独立検査と試験で検出 |
| 9 | M09 state_afterを親からコピー | 検出（77件） | B（history_invalid／state_after） |
| 10 | M10a 過去events・新記録の保存検査を省く | 検出（1件） | A。validate_historyを置換して単独で検出（InternalInvariants） |
| 10 | M10b 有効／退避seqの検査を省く | 検出（1件） | A（同上） |
| 10 | M10c 有効なAPPLY／ACK／宣言事実の検査を省く | 検出（1件） | A（同上） |
| 11 | M11a 候補にvalidate_historyを呼ばない | 検出（83件） | C（呼出し契約）＋値 |
| 11 | M11b 保存内容の不変検査を省く | 検出（3件） | A |
| 12 | M12 IDを有効鎖だけで照合 | 検出（2件） | A（退避だけのIDはB-1も止めない：probeは受理） |
| 13 | M13 同ID同内容を通す | 検出（1件） | A |
| 14 | M14a 確認hashを比較しない | 検出（1件） | A |
| 14 | M14b plan_hashを再計算しない | 検出（2件） | A |
| 14 | M14c ledger／sessions digestを無視 | 検出（3件） | A（staleがmismatchに変わる） |
| 14 | M14d history digest／headを無視 | 検出（14件） | A |
| 15 | M15 不正入力をstaleに変換 | 検出（1件） | A |
| 16 | M16a 再確認をstaleにする | 検出（10件） | A |
| 16 | M16b 候補を元として2件目を作る | 検出（9件） | A（2件目のRESTARTは作られず、mismatchになる） |
| 17 | M17a 枝Bでprefixのvalidateを省く | 検出（1件） | C（spy） |
| 17 | M17b 枝Bでprefixのdigest／head／state比較を省く | 検出（1件） | C（build_restartが呼ばれないことのspy）。結果の値だけでは区別できない（上記） |
| 17 | M17c 枝Bでbasisの完全再構築比較を省く | 検出（1件） | A（prefix不一致・floor改変の候補が通る） |
| 18 | M18a basisアクセサが参照を共有 | 検出（2件） | A |
| 18 | M18b plan_hashアクセサが参照を共有 | 検出（1件） | A |
| 18 | M18c to_dictが参照を共有 | 検出（4件） | A |

「A＋B」は、B-3の事前検査を壊してもB-1が別のcodeで止め得ることを示す。この場合も、期待するrestart_invalidと食い違うため、新規試験は失敗する。「誤った候補が受理された」と「codeが変わった」は区別して読むこと。probeの出力は、変異ごとの1例であり、検出の根拠は試験の失敗である。

## 8. 解釈した点

1. check_dのsessions検査（不存在→未確定→次→前）は、LedgerContextと同じ順序・同じ既存コードで、自前の検査として書いた（LedgerContextの代用品は作っていない）。resume_after==check_dではLedgerContextのtarget_not_after_boundaryが使えないため、投影は**元履歴**に対して行い、候補への投影はしていない（設計§8）。
2. 設計§8の保存内容の検査が失敗した場合（実装内部の不整合）は、`history_invalid／history／rule=restart_candidate` とした。設計は「既存エラーを保つ」としか書いていないため、ruleの名前は実装で決めた。
3. 確認の枝Bで元prefixの検査・digest照合のいずれかが合わない場合は`history_plan_mismatch`。再確認でも入力のledger／sessions digestが違えば`history_plan_stale`。
4. NO_CHANGEの結果の`history`は、渡された現在のHistoryそのもの。
5. 各accessorの表示用の値の再検査は、B-2に倣って`_display`にまとめた。`summary()`の`floor`は3日付（nullを含む）の辞書。
6. 開発中、`__pycache__` を1度コミットに含めたが、push前に取り除いて作り直した（pushされたコミットには含まれない）。最終コミットのgit管理下に`.pyc`は0件。

## 9. 未実施・留保

- B-3は**候補Historyまで**である。`HistoryAppendBatch`の一般化、保存、ロック、CAS、公開後の照合、成否不明時の計画保持・ALREADY_PUBLISHED相当の照合（P-01）はS3-C以降。上位§9のバッチ統合・保存・耐久性は達成していない。B-2のR-a採用は変更していない。
- 後工程（B-4／B-5／S3-C）で新規ディレクトリを足すとき、旧範囲試験（B-2・B-3）の見直しが再び必要になる（P-02）。先回りの許可や共通一覧への再編はしていない。
- 未実施：Windows（実機・環境なし）、ユーザーのPC、物理電源断、`core.autocrlf=true`。Windowsでの新規N＋B-2＋S3-A＋B-1＋S2専用4件の実行は未実施で、上の表に含めていない。
- B-4（復元計画、CONSUME）、B-5（破損診断、prefix採用）、S3-C、PR、マージ、Actions、本番、通知には進んでいない。
