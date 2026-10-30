# V2 S3-B-3 UNKNOWN再開始 設計案・限定実装依頼書 レビュー結果

作成日：2026-10-30  
レビュー担当：Claude（読み取りレビュー。コード変更・push・PR作成なし）  
採否：Rockyさんが判断する。本書は採用・実装承認を意味しない。両文書は「レビュー待ち・実装未承認」のまま扱う。  
リポジトリへ保存する場合のパス案：`docs/reviews/V2_RECOVERY_S3B3_REVIEW_20261030.md`

---

## 1. 対象

| 区分 | 内容 |
|---|---|
| 対象SHA | `f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c`（branch `docs/v2-history-s3b3-20261030` の先頭と一致） |
| 差分 | `b328844..f90c2e6` は d74919a（設計）と f90c2e6（依頼）の2コミット。変更は文書2本だけで、コード差分は0 |
| 突き合わせたコード | B-2 `b328844`（fix/v2-history-s3b2-review-20261030）。B-1 `adfdf765`（fix/v2-history-s3b1-review-20261030）を含む |
| 参照した資料 | B-2受領 `5743732`、B-2設計第2版 `e083cd3`、S3-B設計第2版 `361904b` §7・§9、上位第4版 `e3e9094` R-4・RT-04・RT-09 |
| 保護参照 | 依頼§7の44参照は、`git ls-remote` で全件一致 |
| 試したこと | 通常N-01を確かめるため、スクラッチの作業ツリーで一時コミットを作って試験を1回実行した（§3 N-01）。pushはしておらず、作業ツリーは削除済み。それ以外の試験は実行していない |

## 2. 結論

**重大0・通常3・提案5です。** 構成（候補Historyまで、元履歴を既存のB-2投影に任せ、候補を変更しないvalidate_historyに通す、枝Bでは物理prefixから元履歴を復元する）は、B-1・B-2のコードと整合しています。

ただし、§2.4の「旧範囲試験は2か所だけ補正する」は、このままでは実装できません（N-01、再現済み）。N-01〜N-03を直した版なら、3提案（D-1〜D-3）を一組で採否判断に出せると考えます。

コードで裏付けを取った主な点は次のとおりです。

- floor の3成分は、B-1検査器の `restart_record`（`v2_history/view.py:419-446`）が計算する期待値と同じ定義です。latest_apply_d と latest_declared_d は、どちらも有効ビュー全体から取ります。
- 候補の floor／親／state_after がずれていれば、validate_history が独立に拒否します。
- check_d の検査順は `LedgerContext._check_check_d`（`v2_recovery/facts.py:268-283`）と同じです。next を previous より先に見ます。
- floor を満たして無効果でない計画では、必ず check_d > 元の境界になります。現在区間にAPPLYが無ければ状態は初期のままなので、境界が同じならrestart_noopになり、APPLYがあれば last_apply_d が境界より後になるためです。このため、元履歴への投影が `target_not_after_boundary` で止まることはありません。
- `check_append_batch` は source が DAILY／RESOLUTION 以外だと拒否します（`v2_history_ops/batch.py:78,130,155-166`）。§2.3 の説明は事実どおりです。
- B-2 の `request_status` は、RESTART・RESTORE・MIGRATION の request_id を既に一律で conflict にしています（`v2_history_ops/plan.py:179-180`）。
- 合計1059件（197+170+176+230+173+113）は、既存スイートの件数と合っています。

## 3. 通常（3件）

### N-01 旧範囲試験の補正が2か所では足りない。新パッケージの `__init__.py` で失敗する

- **箇所**：設計§2.4、依頼§2（「FilesChangedの2箇所だけ」）、B3-16。
- **内容**：`tests/v2_history_ops/test_b17_scope.py` の `test_only_the_allowed_paths_differ` は、許可リストのループの後で、次の検査もしています（195-197行）。

  ```python
  for path in paths:
      self.assertFalse(path.endswith("__init__.py") and not path.startswith(("v2_history_ops/", "tests/v2_history_ops/")), path)
  ```

  設計§3のとおり `v2_history_restart.__all__` を置けば、`v2_history_restart/__init__.py` が新しく増えるので、この検査に必ず当たります。
- **再現**：b328844 の上に、空の `v2_history_restart/__init__.py`、`tests/v2_history_restart/test_x.py`、結果文書を一時コミットしました。§2.4 の2点（許可リストに2ディレクトリと結果文書を追加、Git検索から `tests/v2_history_restart` を除外）だけを当てて実行した結果、`Ran 10 tests … FAILED (failures=1)`、`AssertionError: True is not false : v2_history_restart/__init__.py`（197行）でした。
- **影響**：依頼どおりに実装すると、B-2の173件のうち1件が落ちます。直すには3か所目の補正が要りますが、依頼§2はそれを禁じています。そのため、実装担当は停止して報告するか、範囲外の変更をするかの二択になります。
- **修正案**：§2.4、依頼§2、B3-16 の補正対象を3点にする。3点目は「同じ関数末尾の `__init__.py` 検査の startswith に `"v2_history_restart/"` を足す」。B-3 の新規範囲試験では、旧ファイルの差分がこの3行（相当）だけであることを厳密に照合する。tests 側には `__init__.py` を置かない（既存の tests/v2_history・v2_history_ops にも無い）、と明記すると迷いません。

### N-02 prepareで依頼を拒否するときのエラーが `history_invalid／history` になっている

- **箇所**：設計§4手順2・4、§5、§10の表（restart_boundary、restart_floor、restart_noop、check_d）、B3-03・B3-04。
- **内容**：B-1・B-2では、`history_invalid` は「渡された保存履歴が validate_history を通らない」ことを表すコードです（`v2_history/errors.py`、`v2_history_ops/errors.py`）。一方、B-3のこれらの拒否は、履歴は正常で、利用者が指定した resume_after／check_d／sessions がおかしい、という場面です。B-2では、同じ性質の依頼の拒否は `resolution_invalid("commands", rule)` で、履歴の破損と区別していました（`v2_recovery/commands.py:23`、`v2_history_ops/plan.py` の `_build`）。
- **影響**：S3-C や B-5（破損診断）が `history_invalid` を「正本の破損」として扱うと、正常な履歴に対する指定ミスが破損と誤って案内されます。試験でコードを固定した後に変えると、B3-03／B3-04 の期待値をすべて変えることになります。
- **修正案**：prepare で依頼として拒否するものは、B-3で新しく作る `restart_invalid` にそろえる。field は `resume_after`（範囲外の場合は `check_d`）、rule はB-1と同じ名前（restart_boundary／restart_floor／restart_noop／check_d）を使う。`history_invalid` は、入力履歴そのものの検査失敗と、候補の validate_history が失敗した場合（内部の不具合）に限る。B-1のコードに合わせて意図的に `history_invalid` を使うのなら、その理由を§10に書けば足ります。

### N-03 §4の「不正なsessions等はその前に止まる」が、範囲照合のエラーには当てはまらない

- **箇所**：設計§4の末尾、B3-04、B3-08。
- **内容**：§4の手順5（`project_history_ledger`）の中で、`LedgerContext` は次の順で検査します（`facts.py:244-258`）。check_d → 全境界セッションとの完全一致（`session_context_missing／mismatch`）→ APPLY／宣言の `slice_check` → 台帳行の解析。手順1・2で前に出せるのは、sessions の形（copy_sessions）、台帳行（parse_ledger）、check_d のセッション検査だけです。旧境界や旧APPLY文脈との差は、手順3の ID 照合と手順4の floor より**後**にしか出ません。
  B-2 の `_build` は、`LedgerContext` を作ってから request_id を照合します（`plan.py` の `_build`、番号 1→2→3）。そのため、「旧境界のセッションが変わった」と「使用済みID」が重なった入力では、B-2は `session_context_mismatch` を返しますが、B-3の順序では `history_request_conflict` になります。§4の文は、この場合も前で止まると読めてしまいます。
- **影響**：B3-04／B3-08 の組み合わせ試験で、期待値が実装担当の解釈に左右されます。
- **修正案**：今の順序（resume==check_d の候補へ同じIDを再提出したとき、`target_not_after_boundary` ではなく conflict を返すための順序）は妥当です。順序は保ったまま、§4の末尾を優先順位の表に書き換えてください。①履歴・sessionsの形・台帳行、②check_dのセッション、③requested_at・IDの形・ID照合、④floor・上限・無効果、⑤元履歴の投影（境界・文脈の差、ledger_mismatch、late_observation、version_selection 等）。そのうえで、「旧境界の変更と使用済みIDが重なれば conflict」を対照の例として1件、B3-04 か B3-08 に入れると固定されます。

## 4. 提案（5件）

- **P-01（D-2の運用上の帰結）**：保存したかどうか分からない状態（S3-Cで公開に成功したが、結果を受け取れなかった場合）から同じIDでprepareし直すと、conflict になります。保持していた計画を再確認しても、NO_CHANGE になるのは候補の後に記録が1件も無いときだけです。早朝の日次処理が先に走ると stale になります。§7 に「この場合の扱い（計画の保持、ALREADY_PUBLISHED に当たる照合）は S3-C の義務」と1行書くとよいです。可能なら、conflict の rule を「有効な同じ再開始が既に履歴にある」場合と、それ以外で分けると、利用者への案内がしやすくなります（固定名のみで、値は出さない）。
- **P-02（範囲試験が段階ごとに繰り返し壊れる）**：b17 も、B-3 の新しい範囲試験も、`HEAD` との差分で検査します。そのため、B-4・B-5・S3-C のたびに、前の段階の範囲試験をすべて補正することになります。B-3 の新規範囲試験の設計時に、B-4 で補正が要ることを明記するか、後の段階のディレクトリを1か所の一覧で受け付ける形にしておくと、毎回「旧試験の限定補正」を判断する手間が減ります。B-3では採否不要の記録だけでも十分です。
- **P-03（利用者への説明として書いておくこと）**：
  - (a) 再開始では、旧区間の未解消の台帳問題（ledger_mismatch、late_observation）を回避できません。先にB-2のACKが必要です。
  - (b) 旧区間の最後のAPPLYから resume_after までの間に、どの記録にも属さない日の decision があっても、処理されません（解析と衝突の検査だけは受けます）。
  - (c) B-1 の `check_d_ok`（`view.py:240-244`）は check_d > 現在の境界を求めます。このため、resume_after==check_d で再開始した直後は、次のセッションが確定するまで、新しい ACK／DECLARE を作れません。

  (c) は、B3-13 の期待値に1行で入れておくと、実装時に戸惑いません。
- **P-04（欠陥注入の分類）**：変異1〜3（floor）、8（親）、9（state_after）、10（過去events）は、prepare 自身の検査を外しても、手順7の validate_history が `restart_floor`／`parent`／`state_after` 等で独立に止めます（`view.py:435-446`、`validate.py` の `_parents_and_start`）。変異11と同じように、「B-3自身の検査で検出」と「既存検査器で検出（エラーのコードや順序が変わる）」を分けて報告するよう、依頼§5 に書くとよいです。
- **P-05（試験ファイル名）**：B-2では `test_r_review_fix` が既存のファイル名と衝突しました。新しい試験は `ho_helpers` 経由で他の試験ディレクトリを sys.path に加えるので、`test_r3_*` のように、どのパッケージとも重ならない接頭辞を依頼§6 で指定しておくと安全です。

## 5. 3提案への意見

| 提案 | 意見 | 理由・条件 |
|---|---|---|
| 1. 候補Historyまでとし、保存用バッチへの統合はS3-Cへ（D-1） | **賛成（N-01を直すことが条件）** | 今のバッチは DAILY／RESOLUTION 専用です。RESTART を足すには、B-2ランタイムの変更が必要になります。RestartPlan の basis には、expected_head_seq／hash、candidate_digest、plan_hash があり、新しい記録は候補の末尾にあります。なので、S3-C は prepare をやり直さずにバッチを作れます。その旨を §2.3 に1行書いておくと、S3-C への引き継ぎが明確になります |
| 2. 既存IDの再利用は拒否し、同じ計画の再確認だけを `NO_CHANGE`（D-2） | **賛成** | B-2 は RESTART のIDを既に一律 conflict にしていて、B-1 も有効ビュー内の重複IDを拒否します（`view.py:225-228`）。B-2の方式との違いは、同じIDで再提出したときの見え方だけです。状態を初期化する操作なので、厳しいほうが安全です。保存したか分からない状態の扱いは P-01 のとおり S3-C に残します |
| 3. 実装担当は Sonnet 5.5・high（D-3） | **賛成** | 純粋関数で、既存の公開名を組み合わせるだけです。新しい戦略式もありません。難所は枝Bの prefix 復元と範囲試験ですが、N-01〜N-03 を直せば依頼書に十分固定されます。B-2 を同じ設定で実装し、レビュー修正まで完了した実績もあります |

## 6. 範囲外・未確認

- B-1・B-2・既存スイートの試験は実行していません（N-01の再現で b17 を1回実行しただけです）。
- 上位設計・S3-B設計は、B-3に関係する節（§7、§9、R-4、RT-04、RT-09）だけを読みました。
- 例U・例R・例M の具体的な期待値は、文書の記述とコードの規則から確かめました。fixture を作っての再計算はしていません。