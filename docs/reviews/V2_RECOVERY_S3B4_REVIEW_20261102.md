# V2 S3-B-4 復元計画・確認 設計案・限定実装依頼書 レビュー結果

作成日：2026-11-02  
レビュー担当：Claude（読み取りレビュー。コード変更・push・PR作成なし）  
採否：Rockyさんが判断する。本書は採用・実装承認を意味しない。両文書は「レビュー待ち・実装未承認」のまま扱う。  
リポジトリへ保存する場合のパス案：`docs/reviews/V2_RECOVERY_S3B4_REVIEW_20261102.md`

---

## 1. 対象

| 区分 | 内容 |
|---|---|
| 対象SHA | `f94220856c849f4a7dd91deac04b9b5a820a6239`（branch `docs/v2-history-s3b4-20261102` の先頭と一致） |
| 差分 | `d82a5ce..f942208` は 75e9443（設計）と f942208（依頼）の2コミット。変更は新規文書2本だけで、コード差分は0 |
| blob | 設計 `83202d84c565aa70f3b62aefe39bfa0bd4c7b323`、依頼 `aad20dbfda8ae5d8c44c8ecc65ede205235c04d3` |
| 突き合わせたコード | B-3 `d82a5ce`（B-1 adfdf765、B-2 b328844 を含む）。B-1 restore／view／validate、B-2 chain／read、S3-A facts／commands／project、コア engine／transition／fixture、S1 events／recompute |
| 参照した資料 | B-3受領 `78b9b40`、S3-B第2版 `361904b` §8、前回のB-3レビュー・再レビュー |
| 保護参照 | 依頼§8の48参照は、`git ls-remote` で全件一致 |
| 試したこと | スクラッチの作業ツリーで一時コミットと読み取り用の確認スクリプトを使った（§3）。pushはしておらず、作業ツリーは削除済み。確認スクリプトと試した補正の差分は `/mnt/project-files/reviews/v2_recovery_s3b4_review_probes_20261102/` に置いた |

## 2. 結論

**重大0・通常3・提案5です。** 構成（候補Historyまで、CONSUMEは保留して必要なら停止、二段階でhashを決める、最後は変更しないvalidate_historyとB-2の全区間投影に任せる、旧復元バッチの途中のAPPLYを復元点にするとき物理prefixを切ってvalidateしない）は、B-1・B-2・S3-Aのコードと整合しています。

ただし次の3点は、このままだと実装担当が止まるか、受入試験の期待値が実際の動作と合いません。

- N-01：B-3範囲試験（r3_07）の補正指示のうち2行が、コードの事実と合いません。指示どおりにすると2件落ちます（再現済み）。
- N-02：「旧skipへの後発は最後のB-2照合でlate_observation」は、REAPPLYするAPPLYの旧skipでは成り立ちません。手前のevaluate_dayが `intermediate_session_unprocessed` で止まります（再現済み）。
- N-03：REPLAYの証拠をprefixと**現在の**台帳で再検査すると、後の再生記録が解決している行のせいで、正当な履歴の復元を拒否します（再現済み）。

これらを直した版なら、3点（D-1〜D-3）を一組で採否判断に出せると考えます。

コードで裏付けを取った主な点は次のとおりです。

- 復元点・退避一覧・処分の規則（§4）は、B-1 `_check_one`（`v2_history/restore.py:91-131`）と一致します。`restore_point_in_batch` はACK／DECLAREの `command_index` だけを見るので、旧復元バッチの途中のAPPLYは復元点にできます。そこまでの物理prefixは `_check_window` の `restore_incomplete`（同186-187行）で落ちるので、§4の「切り出してvalidateしない」は必須です。
- `same_as_superseded` の4項目は、B-1 `_check_reapply`（同217-219行）の定義と同じです。`input_hash` は `project_context` を通す（`v2_persistence/events.py:70-81`）ので、next(D)のclose_at／confirmedだけの差では変わりません。§6.2・§11とB4-07の「無害」は事実どおりです。
- 再生記録の `check_d_ok`（`view.py:240-246`）、floor（同432-446行）、frontier（同230-238行）は、ops が鎖の順に並び、DROPしか鎖を短くしないので、§6.3の再計算で足ります。
- `late_observation`／`ledger_mismatch` は `final_checks`（`v2_recovery/project.py:120-140`）にしかなく、`apply_records`／`check_versions` は出しません。このため §5 の段階7（`restore_requires_consume`、`restore_decision_changed`）は、最後のB-2照合より前に出ます。
- `apply_records`／`check_versions` は `LedgerContext` を ctx として受け付けます（`stored_row` は `ctx.sv.decision_cols`、`check_versions` は `ctx.sv.fixed_fps` だけを使う）。§7の橋渡しはコード上可能です。
- 既存7スイートの合計1168件（197+170+113+176+230+173+109）、Windows側の692件（109+173+176+230+4）は、受領記録の件数と合います。

## 3. 通常（3件）

### N-01 B-3範囲試験 r3_07 の補正指示のうち2行が事実と合わない。指示どおりだと2件落ちる

- **箇所**：依頼§3.2の表の1行目・2行目、B4-01、B4-20。
- **内容**：r3_07 の `FilesChanged` は `b328844`（B-3の開始点）からHEADまでの差分を見ます（`r3_helpers.py:24`）。`tests/v2_history_restart/test_r3_07_scope.py` は b328844 には存在しないので、この差分では状態が **A** です（`git diff --name-status b328844 d82a5ce` で確認）。
  - 1行目の「このB-3範囲試験自身の1パスをMとして認める」は、M にはならないので成り立ちません。r3_07 自身は、既存の `tests/v2_history_restart/` の許可（A）に最初から含まれています。
  - 2行目の「残る旧試験の差分をB-17と本ファイルの2パスだけに固定」は、同じメソッドの検索に `:(exclude)tests/v2_history_restart` があるため、r3_07 自身が結果に出ません。結果は B-17 の1パスのままです。
- **再現**：d82a5ce の上に、空の `v2_history_restore/__init__.py`、`tests/v2_history_restore/test_r4_x.py`、結果文書を一時コミットしました。
  - 補正なし：b17 は `failures=2`、r3_07 は `failures=2`（新規の結果文書と tests/v2_history_restore が範囲外）。
  - §3.1 の3点を b17 に当てると、b17 は `Ran 10 tests … OK`。§3.1 はそのまま実装できます。
  - §3.2 を文字どおり当てると、r3_07 は `test_only_the_allowed_paths_differ` で `AssertionError: 'A' != 'M'`、`test_no_existing_runtime_old_test_fixture_or_setting_differs` で「2パスを期待したが1パス」で落ちます。
  - 1行目は新規のB-4パスの許可と `__init__.py` の2パスだけ、2行目は除外に `:(exclude)tests/v2_history_restore` を足すだけ（期待値はB-17の1パスのまま）、3行目はB-17の期待リテラルの更新だけ、という最小の補正なら、r3_07 は `Ran 11 tests … OK` でした。ハンク数は4のままです。この状態で、B-1 230・S3-A 176・B-2 173・B-3 109 も全件合格しました（Python 3.13.18、Linux）。
- **影響**：依頼どおりに実装すると、B-3の109件のうち2件が落ちます。実装担当は停止して報告することになります。
- **修正案**：§3.2 の1行目は「既存B-17のM例外は変えない。r3_07 自身は b328844 から見て A なので、例外は不要」と書き直す。2行目は「除外に新規 tests/v2_history_restore を足す。期待値はB-17の1パスのまま」と書き直す。r3_07 自身の差分（3メソッドだけが変わったこと）は、d82a5ce を基準にする新しいB-4範囲試験だけが監査できます。依頼にそう明記してください。

### N-02 REAPPLYするAPPLYの旧skipに後発がある場合、late_observationより前にevaluate_dayが止まる

- **箇所**：設計§5の段階7・8の順序、§8の末尾（「released_days以外の旧skippedへの後発……は最後のB-2照合で既存late_observationになる」）、§9の手順3、依頼B4-08・B4-13。
- **内容**：`evaluate_day`（`v2_core/engine.py:93-97`）は、`base.as_of_d < previous(D)` のとき、その間に有効なdecisionがあると `InputError("intermediate_session_unprocessed")` を出します。REAPPLYの新しい有効親がAPPLY（as_of_d が null でない）で、そのAPPLYの旧skipped_sessions のどれかに後から有効なdecisionが入った場合、§9の手順3（段階7）がこれに当たります。最後のB-2照合（段階8）の `late_observation` には届きません。
  `released_days` の日は段階7の最初で `restore_requires_consume` になるので、ここに当たるのはちょうど「旧skipへの後発」と「DROPしたLATE ACKで戻る後発」です。設計が late_observation と書いている場面そのものです。
- **再現**：GENESIS(D0)→APPLY D1→APPLY D3（D2はskip。その時点でD2の行なし）→RESTART(D3)→APPLY D4 を作り、あとからD2の有効なdecisionを台帳に足しました。元履歴の `project_history_ledger` は `late_observation/observations`。P=APPLY D1 で D3 を再適用するときの `evaluate_day(D1の状態, D3, …)` は `intermediate_session_unprocessed/observations` でした（確認スクリプトの probe2）。新しい有効親が初期状態（RESTARTの直後）なら、この検査は飛ばされて late_observation になります。つまり、同じ種類の入力で、エラーが幾何によって変わります。
- **影響**：B4-08 の対照「旧skip後発は既存late_observation」の期待値が、典型的な配置では成り立ちません。実装担当が期待値に合わせようとすると、evaluate_day の前に独自の後発検査を足す（規則の複製）か、順序を独自に変えることになります。
- **修正案（推奨）**：evaluate_day による照合を、最後の `project_history_ledger` と事前集合の一致確認の**後**に移す。順序は「released_days → decision比較 → 市場値比較 → B-2全区間照合 → evaluate_day照合 → 無効果 → basis」。B-2照合が通ると、候補のどのAPPLYのskipにも、どの宣言日にも有効なdecisionが無いことが確かめられています。なので、その後の evaluate_day は `intermediate_session_unprocessed` を出しません。late_observation の扱いも、B-2の日次処理と同じになります。
  順序を変えない場合は、§8・§12・B4-08 に「新しい有効親が非nullなら intermediate_session_unprocessed、初期状態なら late_observation」と両方の期待値を固定してください。

### N-03 REPLAYの証拠をprefixと現在の台帳で再検査すると、後の再生記録が解決済みの行で、正当な復元を拒否する

- **箇所**：設計§7の手順2・3、§5の段階6、依頼B4-11・B4-19。
- **内容**：§7の手順2では、各REPLAYグループの直前までの有効prefixからFixedFactsとLedgerContextを作り、`existing` もそのprefixの解決記録に限ります。一方、台帳は**現在の**ものを使います。その結果、そのグループより後に台帳へ入り、後のACK（これも再生する）が除外している行が、前のグループの検査には見えてしまいます。
  - DECLARE D2 の後でD2の有効なdecisionが届き、LATE ACK（missing_ref＝そのDECLARE）で除外した履歴。DECLAREの再検査では、`_check_declare` の `rem0` にその行が残ります（`existing` に LATE ACK が無いため）。そのため `declare_valid_decision` になります（`v2_recovery/commands.py:120-150`）。
  - ROW_REMOVED の後で同じrecord_idの行が別の内容で戻り、CHANGED ACK で除外した履歴。ROW_REMOVED の再検査では、`union_excl` に後の CHANGED の指紋が無いので、`_check_row_removed` が `ack_evidence` になります（同82-88行）。
- **再現**：H.HB で上の2つの履歴を作りました。どちらも `validate_history` と元履歴の `project_history_ledger` は通ります。prefix=[GENESIS, APPLY D1] の `LedgerContext.from_facts(…, 現在の台帳, CHECK_D)` で `check_commands(ctx, [], [元記録のコマンド])` を呼ぶと、それぞれ `resolution_invalid/commands/declare_valid_decision` と `resolution_invalid/commands/ack_evidence` でした（probe1、probe1b）。
- **影響**：たとえば「DECLAREとLATE ACKの組より前にした不要なRESTARTを取り消す」復元は、どのopsを選んでも通りません。両方をREPLAYすると上の拒否になります。DECLAREをDROPすると、D2に有効なdecisionがあるので `restore_requires_consume` です。LATEだけDROPすると、DECLAREの再検査で同じ拒否になります。誤った候補を受け入れるわけではありませんが、元履歴が正常なのに、利用者には「宣言が不正」と読めるエラーが出ます。B4-11・B4-19 の期待値もこの点で揺れます。
- **修正案**：どれを採るかを設計に明記してください。
  - (a)（今回の限定単位での推奨）今の保守的な再検査を残し、上の誤拒否を既知の制限として §7・§12 に書く。B4-11 に、拒否される対照（DECLARE＋LATE、ROW_REMOVED＋CHANGED）と、復元点を組の後に取れば通る対照を入れる。
  - (b) 前のグループの検査では、候補で後に有効になる解決記録が除外する指紋を、台帳から見えなくする。frontierと宣言日はprefixのままにする。check_commands の existing に後の記録を混ぜると frontier が壊れるので、この案には設計の追記が必要です。
  - (c) REPLAYでは台帳の証拠を再検査せず、幾何の再計算と、最後のB-2全区間照合に任せる。上位S3-B §8.8手順5 の「台帳に依存する証拠も新しい鎖で再検査する」から外れるので、上位の改訂として記録が要ります。

## 4. 提案（5件）

- **P-01（D-2の同値な言い換え）**：CONSUMEを保留し、市場値・decisionの変更を拒否する前提では、DROPが0件の計画では、全REAPPLYが必ず same=true になります。鎖の上のAPPLY・境界・宣言の並びが変わらないので、input_hash・skip・状態が変わる経路が無いためです。つまり restore_no_effect は「DROPが1件も無い」と同値です。§10に1行書くと、受入例（B4-14）が読みやすくなります。また、限定欠陥注入17で「全REAPPLY trueの判定だけを外す」変種は等価変異になるので、等価として分類するよう依頼§6に添えると、無根拠なspyの追加を防げます。
- **P-02（B4-13・§13の「元投影は失敗するがDROPで整合」の例）**：思いつきやすい「宣言日に後から有効なdecisionが届いた」場合は、DECLAREをDROPすると `restore_requires_consume` になり、成功例になりません。成功例には、たとえば「DECLAREの保存contextが現在sessionsと食い違い、そのDECLAREをDROPする（released_daysに有効なdecisionなし）」や、「RESTARTのboundary_sessionの食い違いをDROPで解消する」を指定すると、期待値が固まります。
- **P-03（B-3ランタイムの固定は新しいB-4範囲試験だけが担う）**：b17（adfdf765起点）と r3_07（b328844起点）から見ると、B-3のファイルはすべて A です。どちらも `v2_history_restart/**`、`tests/v2_history_restart/**`（r3_07を除く）、`V2_RECOVERY_S3B3_RESULT.md` の変更を検出できません。B4-01・B4-20 に「d82a5ce基準で、これらの差分0（r3_07は§3.2の3メソッドだけ）」と明記してください。
- **P-04（B-4範囲試験の後工程語の扱い）**：r3_07 の `LATER_STAGE_WORDS` には "restore" と "consume" が入っています。B-4では、パッケージ名と、CONSUMEを拒否する比較の文字列に、必ずこの2語が現れます。B-4の範囲試験で「CONSUME実装の不存在」をどう確かめるか（例：CONSUMEは拒否の比較にだけ現れる、ledgerから選んだdecisionでAPPLYを作る経路が無い）を依頼に一言書くと、B-3の検査をそのまま写して落ちる手戻りを防げます。
- **P-05（段階番号の書き方）**：§5の末尾に「候補の保存文脈と現在sessionsとの差は段階6」とあります。一方 §6.1 では、残す文脈の照合を組立ての前（段階4）に置いています。どちらもID照合（段階3）より後なので優先順位は変わりませんが、「残す文脈は段階4、候補全体は段階6」と書き分けると、B4-13 の期待値が一意になります。

## 5. 3点への意見

| 判断 | 意見 | 理由・条件 |
|---|---|---|
| 1. 候補Historyまでの復元計画・確認に限定し、CONSUMEは保留して必要なら停止する（D-1） | **賛成（N-01〜N-03を直すことが条件）** | B-1はCONSUMEを `restore_op_unsupported` で拒否します。上位S3-B §8.7も「CONSUMEが無ければ restore_requires_consume で止める」と書いているので、一貫しています。保存用バッチはDAILY／RESOLUTION専用（B-3レビューで確認済み）なので、候補までで止めるのが最小です。実際上の制限として、取り消した宣言・再開始の日に有効なdecisionがあると取り消せないこと、N-03の(a)を採ればその誤拒否も残ることを、Rockyさんが承知のうえで採否してください |
| 2. 無効果な復元は計画で拒否する（D-2） | **賛成** | P-01のとおり、実質は「DROPを含まない復元は拒否」です。RETIREやREPLAYだけで監査鎖を付け替えても、市場状態も台帳も変わらないので、拒否してよいです。B-1の検査器は変えないので、既存の履歴の読み取りには影響しません |
| 3. 実装担当は Sonnet 5.5・high（D-3） | **賛成（N-03の扱いを先に決めることが条件）** | 純粋関数で、新しい戦略式もありません。B-3を同じ設定で実装し、受領時のレビューは重大0・通常0でした。ただし、B-4は橋渡し（FixedFacts／LedgerContext／check_commands）と順序の契約がB-3より多いです。N-03で(b)や(c)を選ぶ場合は、仕様の追記が先に要ります。実装担当に設計判断を残さない形にしてから渡すのがよいです |

## 6. 範囲外・未確認

- 既存スイートは、N-01の一時構成で B-1 230・S3-A 176・B-2 173・B-3 109 を Linux（Python 3.13.18）で1回ずつ実行しただけです。コア・保存・S2は実行していません。Windows・他のPythonは未実施です。
- N-02・N-03 は、既存の公開関数（evaluate_day、LedgerContext、check_commands）を直接呼んで、設計の手順をなぞって確かめました。B-4は未実装なので、復元計画そのものを実行したわけではありません。
- 例R・例R-b の数値の再計算、series_inputs の正規化、不変性・JSON境界（B4-15〜B4-18）は、文書の記述とコードの規則だけで読み、fixtureでは確かめていません。