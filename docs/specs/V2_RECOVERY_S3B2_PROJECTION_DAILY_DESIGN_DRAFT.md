# V2 S3-B-2 台帳投影・日次処理・新規ACK／欠測宣言 設計案

作成：2026-10-30（日本時間）。第2版：2026-10-30（主担当レビューN-01の補正と任意提案P-01〜P-03の明確化、§17）。状態：**第2版・レビュー待ち。B-2の限定実装は未承認・未着手。**
本書を保存したこと、レビューで問題なしとされたことを、B-2の実装、既存パッケージの変更（§3.3の提案）、新保存形式の採用、S3-C、本番接続の承認に置き換えない。作成担当はClaude Opus 5.5、effort high（セッション情報で指定モデル・effort highを確認）。

## 0. 要約

- **対象**：上位設計（S3-B第2版361904b）§2・§10のB-2。v2履歴での台帳投影、日次処理（S1 `prepare_day` への委譲）、v2で新しく作るACK／DECLARE_MISSINGの計画と確認、メモリ上のバッチ値の境界。B-3（再初期化の計画）、B-4（復元の計画）、B-5（prefix採用）、S3-Cは含めない。ただし、それらの記録を含む検証済み履歴は読めること。
- **最初に分かった制約**：S3-Aの規則関数（`apply_records`、`check_versions`、`final_checks`、`resolve_core`）は、S1 SnapshotとResolutionSetから作る`Ctx`を前提にしている。証拠の検査（`_check_*`）はprivateで、S3-A形式の記録を作る`make_records`の中からしか呼べない。再開始（RESTART_UNKNOWN）をまたぐ有効履歴は一つのS1 Snapshotで表せない。区間ごとに既存APIを呼んでも、除外が履歴全体に効くというS3-Aの意味と一致しない（§3.2の反例X-1〜X-5）。したがって、**既存の公開名だけでは、規則を複製せずにB-2を作れない**。
- **推奨（未承認・ユーザー判断U-1）**：v2_recoveryに最小の差分を入れる（API-1）。新規ファイル `v2_recovery/facts.py` に、S1に依存しない「固定済みの事実」の値と、その事実から作る台帳文脈を置く。`commands.py` では、証拠検査の部分を公開関数 `check_commands` として切り出し（本文はそのまま移す）、LATEの宣言参照でv2の参照形も受け付ける（1か所の分岐追加）。`project.py`・`validate.py`・`plan.py`・`daily.py`・`__init__.py` は変えない。S3-Aの受理・拒否は変わらず、既存176件と欠陥注入の目印文字列も保つ。代替（API-0）は、既存を変えずに新パッケージへ規則を明示的に移植し、S3-Aとの差分試験で同等性を示す方法。
- **新パッケージ `v2_history_ops`**（純粋関数・メモリ上）：`read_effective`（検証済み履歴の表示）、`project_history_ledger`（有効履歴の全区間で照合した最終台帳）、`prepare_history_day`（現在区間をS1へ射影し、`prepare_day` へ1回だけ委譲）、`prepare_history_resolution_plan`／`confirm_history_resolution_plan`、`HistoryAppendBatch` と `check_append_batch`。
- **全区間と現在区間の分離**：台帳照合（除外→必要時だけ補完→版選択の禁止→最終検査）は、有効鎖の**全区間**のAPPLY・skipped_sessions・宣言について行う。日次の計算に使うS1射影は**現在区間だけ**にする。旧区間の宣言は現在のfrontierを進めない。
- **名前空間**：B-2が参照をたどるのは、常に**v2の物理seq＋event_hash**（記録上の参照）である。現在区間のS1射影で付く一時的なS1 seq／hashは `prepare_day` の内側だけで使い、外へ出さない。移行記録のS3-A参照（request_basis内のresolution_seq等）と、再生記録の元の参照（request_basis内）は解釈しない。
- **候補と保存の境界（推奨・ユーザー判断U-2）**：B-2は、純粋な値 `HistoryAppendBatch`（期待先頭、追加する記録、候補digest、計画hash）と、その再検査 `check_append_batch` までを実装する。ロック、CAS実行、置換、耐久性、成否不明後の照合、解錠はS3-Cに残す。上位§2（B-2に公開用バッチ値）と§9.1（実装はS3-C）の記述差を、「値と純粋な再検査はB-2、I/Oと実行はS3-C」に揃える案である。
- **committedは常にFalse**。B-2のどの値も既存 `MemoryStore`／`LocalFileStore` の `commit` に渡せない（既存の`plan_type`で拒否）。これは誤接続を防ぐ型の境界であり、手で値を組み立てる悪意のあるコードへの防御ではない。
- 限定実装依頼書は [V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md](../tasks/V2_RECOVERY_S3B2_LIMITED_IMPLEMENTATION_REQUEST.md)。B-2を一単位として依頼する（§2.2）。

## 1. 固定版・読んだもの・用語

| 用途 | 固定版 |
|---|---|
| コード基準（将来の実装開始点） | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e（fix/v2-history-s3b1-review-20261030）。コード・試験は2b5fa2d079e2fe86b98b0e6d5be5431c5b4988ceと同一で、差は結果文書§13の追記だけ |
| 作成依頼 | fee48e944172950b7e58581c000f0750319a9fd7（docs/v2-history-s3b2-design-request-20261030）の docs/tasks/V2_RECOVERY_S3B2_DESIGN_PREPARATION_REQUEST.md |
| 初版（本書の補正前） | 62861137a28e96a361f198f5601e0f5ae77a6910（docs/v2-history-s3b2-20261030）、本書blob 7c84758219be620083742cbb804ef541f630d578 |
| 主担当レビュー・補正依頼 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e（docs/v2-history-s3b2-review-20261030）の docs/reviews/V2_RECOVERY_S3B2_DESIGN_REVIEW_20261030.md と docs/tasks/V2_RECOVERY_S3B2_DESIGN_CORRECTION_REQUEST.md（重大0・通常1・提案3） |
| B-1修正受領 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| S3-B設計第2版 | 361904b1618ae9f9d3a672875c437a388826c253、blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7（§2、§3.5、§4、§6、§7.2、§9〜§10を主に参照） |
| B-1採用・開始指示書 | 98e05e426b99154e7a5941c718b2b220f048e2a2。D-1・D-2・D-4は採用済みとして扱い、再質問しない |
| S3分割・境界 第3版 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| 上位保存・復旧設計 第4版 | e3e90947a718cca877b543739ca60539207ca7a7（除外→補完、現在状態・基点、開始境界を維持） |

読んだコード（基準adfdf765）：v2_history（全モジュール）、v2_recovery（全モジュール）、v2_persistence（codec、events、recompute、runner、plan、store、errors、local/storeのcommit入口）、v2_core（observations、engine・sessions・stateの必要箇所）、tests/v2_recovery/sensitivity_check.py（欠陥注入の目印文字列）、tests/v2_history/h_helpers.py（例M・R・R-b・Uの組立て）、B-1結果文書§1〜§13。CLAUDE.md、docs/STATUS.md、MODEL_POLICY.md、ROADMAP.mdは必要箇所を確認した。STATUSは2026-10-27時点の古い承認待ちの記述で、今回の文書作成指示とは別である。保存・復旧段階のS3と、売却実務側の別分類S3は混同しない。

B-1のLinux4版・主担当Windows3.12.14での230件と、再現コード10観測の解消は、既存の記録として参照する。本書の作成では、コード変更・試験実行・試験コードや再現スクリプトの作成・新しい市場計算を行っていない。本書の挙動の記述は、固定したコードを読んだ結果であり、実行による確認ではない。

用語（S3-B第2版§1に加えて）：

- **有効記録**：`HistoryCheck.effective_seqs` に含まれる記録。退避記録は含まない。
- **有効解決記録**：有効記録のうちACK・DECLARE_MISSING（鎖の順）。
- **全区間**：最終の有効鎖の全区間（GENESIS区間と、各RESTART_UNKNOWN以後の区間）。
- **現在区間**：最終の有効鎖の最後の区間。境界は `HistoryCheck.current_boundary.after`。
- **固定済みの事実（facts）**：有効APPLYごとの d、event_hash、保存decision、session_context、skipped_sessions、指紋、record_id。有効DECLAREごとの d とsession_context。全区間の境界セッション。
- **一時S1 seq**：現在区間をS1形式へ射影したときに付く 0..n の番号。B-2の外へ出さない。

## 2. 範囲・単位・完了の意味

### 2.1 範囲

| 含める | 含めない |
|---|---|
| 検証済みv2履歴から読む表示（有効記録・区間・参照の出どころ） | 再初期化の計画（B-3）、復元の計画・CONSUME（B-4）、破損診断・prefix採用（B-5） |
| 全区間の台帳投影（S3-Aの除外・補完・版選択・最終検査を再利用） | 公開アダプタ、ロック、CAS実行、置換、fsync、成否不明後の照合、解錠、保守ゲート、Windows strict（S3-C） |
| 現在区間のS1射影と `prepare_day` への1回の委譲 | HistoryReplacement、B-1移行APIの変更 |
| v2で新しく作るACK／DECLARE_MISSINGの計画・確認 | 新しいv2ストア（メモリ／ファイル）、通知・outbox・配信権 |
| `HistoryAppendBatch` の値と純粋な再検査（U-2で採用された場合） | 自動の対象日・追いつき、時計、ネット、プロセス、乱数 |
| 既存v2_recoveryの最小差分（U-1でAPI-1が採用された場合だけ） | 戦略式・閾値・状態式の複製、S3-Aの受理・拒否の変更 |

### 2.2 一単位にできるか

B-2の機能は、台帳投影を共通の土台にしている。日次処理も新規解決の計画も、まず有効履歴全体の投影が通ることを前提にする。日次と解決計画の間には、実装上の依存がない。分ければ、同じ投影を二回レビューすることになる。したがって**B-2を一単位として依頼する**。

一方で、既存v2_recoveryの差分（API-1）を採るか否か（U-1）は、実在の依存である。依頼書では、作業の順序を「①API-1の差分とS3-Aの回帰の確認 → ②新パッケージ」に固定する。①が回帰を満たさない場合は、②へ進まずに止める。U-1でAPI-0が選ばれた場合は、依頼書の§3と§5の一部を差し替える必要がある。自動では切り替えず、依頼書を補正してから着手する。

### 2.3 完了の意味

B-2が完了しても、正本ファイルはv1のままで、v2履歴は保存されない。B-2が示すのは、「検証済みのv2履歴と、注入された台帳・sessions・seriesから、S3-Aと同じ投影規則とS1と同じ日次計算で、追加すべき記録の候補を作れる。その候補を足した履歴が完全な検査を通る」ことだけである。保存・耐久性・通知・本番の正しさは何も達成していない。

## 3. 既存S3-A規則の再利用（作成依頼§3.2）

### 3.1 既存公開名の棚卸し

「公開名」は、本プロジェクトの慣例（B-1依頼書§2）に従い、下線で始まらないモジュール水準の名前とする。各機能について、呼ぶ名前、必要な引数・属性、v2からの写像、出力から採用する項目を示す。

| 機能 | 呼ぶ既存公開名 | 必要な引数・属性 | v2からの写像 | 出力から採用する項目 |
|---|---|---|---|---|
| 履歴の検査 | v2_history `validate_history` | History | そのまま | HistoryCheck の effective_seqs、superseded_seqs、current_boundary、latest_apply_d、processing_after、migrated、history_digest、state_digest |
| 区間ごとのAPPLYの事実 | v2_history.view `Segment`、`project_segment` | Segment(kind, seq, date, session)、.applies＝その区間の有効APPLY（v2の記録dict） | 最終の有効鎖を、GENESIS／RESTART_UNKNOWNで区切る（RESTOREは透過） | AppliedDay の d、record_id、fingerprint、skipped、context、stored_sessions。**seq・event_hash・parent_hashは一時S1の値なので採用しない** |
| 現在区間のS1 Snapshot | v2_persistence.events `make_genesis_event`、`make_apply_event`、`snapshot_of` | 境界日・境界セッション、各APPLYの内容6項目 | 一時S1 seq 1..n、親hashだけ付け直す | Snapshot（`prepare_day` へ渡すだけ） |
| 日次の計算 | v2_persistence.runner `prepare_day` | Snapshot、D、series、sessions、最終台帳 | 上のSnapshotと、`project_history_ledger` の最終台帳 | status、core_result、plan.event のd・confirmed_inputs・input_hash・skipped_sessions・transition_result・state_after。**plan.expected_head_*、eventのseq・parent・event_hashは採用しない** |
| 区間内のセッション照合 | v2_recovery.project `slice_check` | SessionList、context、d | 有効APPLYのcontext、有効DECLAREのsession_context | 例外の有無（session_context_missing／mismatch） |
| 台帳の正規化 | v2_recovery.ledger `copy_sessions`、`parse_ledger`、`ledger_digest`、`sessions_digest`、`Row` | sessions、raw行 | そのまま | 行・digest |
| 投影（除外→補完→版選択→最終検査） | v2_recovery.project `resolve_core`（内部で `apply_records`・`check_versions`・`final_checks`） | **ctx**：`sv`（fixed_fps、applies、decision_cols）、`all_by_fp`、`sl`、`check_d`、`ledger_digest`。records：kind、variant、record_fingerprints、applied_ref、d、session_context | §3.2のとおり、ctxはS1 Snapshot専用の`Ctx`しか作れない | EffectiveLedger の rows、excluded_fingerprints、supplemented、ledger_digest、effective_digest、check_d。**resolutions_digestは採用しない** |
| 新規コマンドの証拠 | v2_recovery.commands `make_records`（内部で private `_check_*`） | ctx（上と同じ＋sv.by_seq、apply_days、latest_apply_day、head_seq・head_hash・events）、existing（S3-A記録） | S3-A形式の記録（resolution_seq、source_head）を出力するため、v2では使えない | （使わない） |
| コマンドの形 | v2_history.view `normalize_command(cmd, "v2")`、`reasons_for_commands` | コマンドdict | v2名前空間 | 正規化したコマンド。エラーは`history_invalid`で来るので、B-2が`resolution_invalid`／commandsへ変換する |
| request_hash | v2_history.common `basis_request_hash` | request_basis | そのまま | hash（S3-Aの`request_hash_of`と同じ値） |
| 依頼の時刻・ID | v2_recovery.common `requested_text`、`is_requested_text`、`valid_request_id`、`record_reason` | 注入日時、ID | そのまま | UTC文字列、真偽、reason_code |
| 記録のhash | v2_persistence.codec `compute_event_hash`、`canonical_json`、`sha256_text` | 記録dict | そのまま | event_hash、digest |

使わない既存公開名（理由）：`resolve_observations`・`validate_resolutions`・`prepare_resolution_plan`・`confirm_resolution_plan`・`prepare_resolved_day`は、S1 SnapshotとResolutionSetを要求する（§3.2）。`Ctx`・`SnapshotView`・`validate_set`は、S3-Aの記録とS1の名前空間を前提にする。`migrated_sources`は移行範囲だけを再構成するので、移行後の記録や再開始区間を含む投影の代わりにはならない。

### 3.2 公開名だけでは成立しない具体例

- **X-1（一つのSnapshotで表せない）**：例V（§12.3）は、0 GENESIS(D0) ／ 1 APPLY D1 ／ 2 DECLARE_MISSING D2 ／ 3 RESTART_UNKNOWN(resume_after=D3) ／ 4 ACK/CHANGED(D1) ／ 5 APPLY D4 である。D1とD4のAPPLYを一つのS1 Snapshotに並べると、D4の基点は初期状態であり、`validate_snapshot` が `IB-04`・`skipped_sessions` で拒否する。したがって、全区間のAPPLYに対して `resolve_observations` を一度だけ呼ぶことはできない。
- **X-2（区間ごとに呼ぶと意味が変わる）**：除外は指紋で台帳全体に効く。D4を対象とし、D1の判定窓の中で観測された決定行zがあるとする。zを除外する ACK/ADDED(D4) が新しい区間にある場合、全体の投影では `select_decision(D1)` が通る。旧区間だけのSnapshot＋Setで `resolve_observations` を呼ぶと、そのACKが無いので `target_mismatch` になる。区間ごとの呼び出しの組み合わせは、S3-Aの意味と一致しない。
- **X-3（旧区間を指す新しい解決記録）**：例Vの#4は、再開始の後に作られ、旧区間の#1を指す。S3-AのSetでは、記録の`applied_ref`はそのSnapshotのAPPLYを、`state_after`は作成時先頭のstate_afterを指す必要がある。新区間のSnapshotには#1が無く、旧区間のSnapshotの最後の状態は#4のstate_after（初期状態）と違う。どちらのSetにも正しく置けない。
- **X-4（証拠検査はprivate）**：`_check_added`・`_check_changed`・`_check_row_removed`・`_check_late`・`_check_declare` はprivateで、`make_records` の中からしか呼べない。`make_records` はS3-Aの記録（resolution_seq、parent_resolution_hash、source_head_seq／hash、作成時先頭のstate_after）を作る。v2で呼ぶには、S1の先頭とS3-Aの番号を偽って与える必要があり、禁止事項（チェック済みと見せかける）に当たる。
- **X-5（宣言参照の形）**：S3-Aの`_check_late`は、宣言型の`missing_ref`を `resolution_seq`／`resolution_hash` で既存記録と照合する。v2のコマンドは `{kind, seq, event_hash}` であり、そのままでは照合できない。

`Ctx`と同じ属性を持つ別の物を新パッケージで作って規則関数へ渡す方法（属性の真似）は採らない。`Ctx`は「この呼び出しで検査済みの入力」を表す型であり、その代用は型の契約を外から迂回する。privateの呼び出し、継承による差し替えも行わない。

### 3.3 推奨：最小API差分 API-1（提案。未承認）

S3-Aの規則の本文を変えずに、規則関数が読む「固定済みの事実」をS1から切り離す。差分は次の3点に限る。

**A1　新規ファイル `v2_recovery/facts.py`**（既存行の変更なし）

| 名前 | 契約 |
|---|---|
| `FixedApply` | 不変。`seq`（int、参照の番号。B-2ではv2物理seq）、`event_hash`、`d`、`decision`（6列dict、取り出しは写し）、`context`（session dictの列、写し）、`stored_sessions`（contextのSessionList）、`skipped`（日付のtuple）、`record_id`・`fingerprint`（decisionを`parse_observation`で解析して**この型が計算する**。呼び出し側の値を信用しない） |
| `FixedFacts.from_parts(applies, declares, boundaries, boundary_day, head_seq)` | applies＝`[{seq, event_hash, d, decision, context, skipped}]`（seqの昇順、重複なし）、declares＝`[{seq, event_hash, d, context}]`、boundaries＝`[{date, session}]`（有効鎖の順、最後が現在区間）、boundary_day＝boundaries[-1].date。形だけを検査する（int・hex64・日付・正規形のsession dict・context[-2].date＝d・decisionの解析）。不正は`facts_invalid`／facts、rule固定。属性：`applies`、`by_seq`、`apply_days`、`fixed_fps`、`declares`、`boundaries`、`boundary_day`、`head_seq`、`latest_day`（全APPLYの最新日かnull）。メソッド：`decision_cols(seq)`（写し）、`latest_apply_day(upto_seq)`＝max([boundary_day]＋[seq≤upto_seqのAPPLYのd]) |
| `LedgerContext.from_facts(facts, sessions, raw_observations, check_d)` | 型と順序：FixedFactsでなければ`facts_invalid`／type → `copy_sessions` → check_dの日付 → check_d > boundary_day（違えば`target_not_after_boundary`／target_session_date） → latest_dayがあれば check_d ≥ latest_day（違えば`state_ahead_of_target`） → sessionsにある・確定・次・前（既存と同じInputErrorのcode） → 全境界セッションが現在のsessionsと完全一致（無ければ`session_context_missing`、違えば`session_context_mismatch`、detail＝日付） → 全APPLYのcontextと全宣言のcontextを`slice_check` → `parse_ledger` → digest。属性：`sv`（＝facts。既存の規則関数が`ctx.sv`として読む名前）、`facts`（同じ物）、`sl`、`check_d`、`rows`、`ledger_digest`、`sessions_digest`、`all_by_fp` |

`FixedFacts.latest_apply_day` は、S3-Aの`SnapshotView.latest_apply_day`と同じ意味の一般化である。S3-Aでは、APPLYが無ければstart_afterを返し、APPLY日は常にstart_afterより後なので、値は max(start_after, 最新APPLY日) に等しい。v2では、区間の境界と現在区間のAPPLY日の最大になる。旧区間のAPPLY日・宣言日は、RESTART_UNKNOWNのfloor（B-1で検査済み）により境界以下なので、最大値に影響しない。

docstringに「`project.apply_records`・`check_versions`・`final_checks`・`resolve_core`と`commands.check_commands`は、ctxとして`Ctx`か`LedgerContext`を受け取る。`ctx.sv`は`SnapshotView`か`FixedFacts`で、これらの関数が読む名前（applies、by_seq、apply_days、fixed_fps、decision_cols、latest_apply_day、head_seq）だけを契約とする」と書く。v2_recoveryの`__init__.py`へは再公開しない。

**A2　`commands.py`：証拠検査の切り出し**

`make_records` の前半（最初のループ〜extrasを作るループ）を、本文を変えずに公開関数 `check_commands(ctx, existing, commands)` へ移す。戻り値はコマンドごとの `(frontier, session_context)`（ACKは `(None, None)`）。`make_records` は `extras = check_commands(ctx, existing, commands)` を呼んでから、従来どおりS3-Aの記録を作る。移す行は、関数の入れ子の深さも含めて同じにする（欠陥注入の目印 M08a・M12・M14・M17〜M19・M29〜M35・M38・M39 の文字列が、それぞれちょうど1回現れるまま残る）。

**A3　`commands.py`：LATEの宣言参照の分岐**

`_check_late` の宣言型の分岐で、参照の形により照合先のキーを選ぶ。

    elif "resolution_seq" in ref:      # S3-A：既存の行のまま（目印M38の文字列を変えない）
        既存記録の resolution_seq／resolution_hash／d と照合
    else:                              # v2：{kind, seq, event_hash}
        既存記録の seq／event_hash／d と照合（kind＝DECLARE_MISSING）

S3-Aのコマンドは `normalize_command` で S3-A形に固定されるので、S3-Aの経路で新しい分岐を通ることはない。

**維持する回帰**（API-1を採る場合の受入条件。依頼書B2-02）：
- 既存のS3-A 176件、B-1 230件、コア197件、保存ドメイン170件、S2 113件（Linux109＋Windows専用4）を無編集で合格。
- S3-Aの欠陥注入スクリプトの全目印（tests/v2_recovery/sensitivity_check.py の各old文字列）が、変更後のv2_recoveryでもちょうど1回ずつ現れること（静的な数え上げ）。commands.pyに関係する変異（M06、M08a、M12、M14、M17〜M19、M29〜M35、M38、M39）だけを再実行し、元と同じ判定（検出か等価）になること。その他の過去の変異は再実行を求めない。
- `make_records` の出力が変わらないこと（S3-Aの既存試験に加えて、例として固定した入力で、変更前後の`prepare_resolution_plan`の`plan_hash`が一致すること）。

### 3.4 代替：API-0（既存を変えず、明示的に移植）

新パッケージ内に `rules.py` を置き、`apply_records`・`check_versions`・`final_checks` と証拠検査5種を、v2の事実を読む形へ**明示的に移植**する。移植した各関数の冒頭に、元の関数名と固定版（adfdf765）を書き、行ごとの対応表を結果文書に付ける。同等性は差分試験で示す：単一区間の履歴（例Mの移行履歴とその延長、新規v2履歴）について、`migrated_sources`で取り戻したv1入力に対するS3-Aの`resolve_observations`・`prepare_resolution_plan`と、v2側の結果（最終台帳の行、除外、補完、拒否のcode／rule）が一致すること。複数区間（例V）は差分試験ができないため、個別の期待値で確かめる。

### 3.5 比較と推奨

| 観点 | API-1 | API-0 |
|---|---|---|
| 既存コードの変更 | v2_recoveryの新規1ファイル＋commands.pyの2か所 | なし |
| 規則の実体 | S3-Aと同じ1つ | S3-A（v1）とv2の2つ。将来の修正を2か所で行う |
| S3-Aへの影響の確認 | 既存176件・目印の数え上げ・commands.pyの変異の再実行 | 不要 |
| 同等性の根拠 | 同じ関数を呼ぶこと（spyで確認） | 単一区間の差分試験。複数区間は個別期待値だけ |
| レビュー量 | v2_recoveryの差分のレビューが増える | 移植した約250行の対応レビューが増える |

**推奨はAPI-1**。規則の実体を一つに保てることと、複数区間でもS3-Aと同じ関数が働くことを、移植の同等性の主張より強く示せるためである。ただし、採用済みのS3-Aのファイルを変えることになるので、その判断はユーザーに委ねる（U-1）。どちらを選んでも、S3-Aの受理・拒否、採用済みN-04、ADDEDの証拠の範囲、version_selectionの禁止は変えない。

## 4. 検証済み履歴から読む表示と参照写像（作成依頼§3.1）

### 4.1 `read_effective(history) -> EffectiveView`

毎回 `validate_history(history)` を呼んでから作る。B-2の他の関数も、内部で同じ手順を通る（検査結果を呼び出しの間で使い回さない）。物理配列からACK・APPLY・宣言を無差別に拾わず、`effective_seqs`だけを読む。

EffectiveViewは不変で、構造化した値の取り出しは常に写しとする。全キー：

| キー | 内容 |
|---|---|
| history_digest、head_seq、head_hash、state_digest | HistoryCheckの値 |
| migrated、migration_seq | 移行履歴か、SCHEMA_MIGRATIONのseq（無ければnull） |
| effective_seqs、superseded_seqs | HistoryCheckの値（list） |
| current_boundary | `{kind, seq, after}` |
| processing_after、latest_apply_d | HistoryCheckの値 |
| segments | 有効鎖の区間を古い順に。各 `{kind, seq, after, apply_seqs, declare_seqs, resolution_seqs}` |
| applies | 有効APPLYを鎖の順に。各 `{seq, event_hash, d, segment_seq, record_id, fingerprint, skipped}` |
| resolutions | 有効解決記録を鎖の順に。各 `{seq, event_hash, kind, variant, d, request_id, command_index, command_count, source, applied_ref, missing_ref, record_fingerprints, segment_seq}`。sourceは NATIVE／MIGRATED／REPLAYED |
| requests | **物理履歴全体**のrequest_id。各 `{request_id, record_kind, request_hash, seqs, effective, source}`。record_kindは RESOLUTION／RESTART_UNKNOWN／RECOVERY_RESTORE／SCHEMA_MIGRATION。effectiveは、その依頼の記録が有効鎖にあるか |

台帳の行、F&G値、保存decisionの値、session_contextは持たない（facts用は内部でhistory.eventsから読む）。reprは件数とseqだけを出す。

### 4.2 名前空間

| 名前 | どこで生まれるか | B-2での使い方 |
|---|---|---|
| v2物理seq＋event_hash | v2履歴のevents配列 | **唯一の参照の名前**。applied_ref／missing_ref、FixedFacts、新しいコマンド、バッチの期待先頭 |
| 一時S1 seq＋hash | 現在区間のS1射影（0..n） | `prepare_day` の内側だけ。返ってきたeventのseq・parent・event_hash、`AppendPlan`の期待先頭、`AppliedDay`のseq・event_hash・parent_hashは捨てる |
| S3-Aの番号（resolution_seq／hash、source_head） | 移行記録のorigin、移行記録のrequest_basis | 解釈しない。request_idとrequest_hashの照合（§6.5）にだけ使う |
| 再生記録の元の参照 | 再生記録のrequest_basis（元記録の時点のv2 seq） | 解釈しない。request_hashの照合にだけ使う |

### 4.3 記録の出どころ

| 出どころ | 判定 | 記録上の参照 | request_basis | B-2での扱い |
|---|---|---|---|---|
| NATIVE | origin=null、replay_of=null | v2（commandsと完全一致） | v2 | 参照をそのまま使う |
| MIGRATED | origin≠null | v2（MIGRATIONの対応表で写したもの） | S3-Aの名前空間のまま | 記録上の参照を使う。basisは解釈しない |
| REPLAYED | replay_of≠null | v2（RESTOREの写像で写したもの） | 元記録のまま | 記録上の参照を使う。basisは解釈しない |

いずれも、記録上の参照はB-1により「その記録のビューでの祖先」で、最終の有効鎖の記録なら有効記録を指す。退避した記録を指す参照は、有効記録の上には存在しない。退避済みの解決記録を投影に入れることも、新しいコマンドの根拠にすることも無い（`FixedFacts.by_seq` は有効APPLYだけを持つ）。

### 4.4 FixedFactsの作り方

1. 最終の有効鎖をGENESIS／RESTART_UNKNOWNで区切り、区間ごとに `Segment(kind, seq, date, session)` を作り、その区間の有効APPLY記録を`applies`に入れる。RECOVERY_RESTORE・ACK・DECLARE・SCHEMA_MIGRATIONは区切りにしない。
2. 区間ごとに `project_segment(segment)` を呼び、返ったAppliedDayを、区間内の順番でv2のAPPLY記録に対応させる。
3. 各有効APPLYについて、`seq`＝v2 seq、`event_hash`＝v2 event_hash、`d`、`decision`＝記録の `confirmed_inputs.decision`、`context`＝`confirmed_inputs.session_context`、`skipped`＝AppliedDay.skipped を渡す。指紋とrecord_idは`FixedApply`が保存decisionから計算する。S1の検査器が同じdecisionから計算したAppliedDay.fingerprint・record_idと同じ値になる（試験で確かめる。依頼書B2-03）。
4. 各有効DECLAREについて、`{seq, event_hash, d, context＝session_context}`。
5. boundaries＝各区間の `{date: after, session: boundary_session}`、boundary_day＝現在区間の境界日、head_seq＝履歴の先頭seq。

AppliedDayを使うのは、指紋・skipped・stored_sessionsを、S1の検査器が計算したとおりに受け取るためである。B-2は戦略式も遷移も計算しない。

### 4.5 現在区間のS1 Snapshot

現在区間について、`make_genesis_event(境界日, 境界セッション)` と、区間内の有効APPLYを `make_apply_event(i, 直前のhash, d, confirmed_inputs, skipped_sessions, transition_result, state_after)` で付け直し、`snapshot_of` で作る。これはB-1の `project_segment` が内部で行う付け直しと同じ構成で、B-2では `prepare_day` に渡すためにSnapshotそのものが必要なので作る。付け直したAPPLYのinput_hashがv2記録と一致すること、および、このSnapshotを `validate_snapshot` に通した結果のapplies（d・指紋・skipped）が §4.4の2と一致することを、試験で確かめる（依頼書B2-03）。

## 5. 台帳投影（作成依頼§3.3前半）

### 5.1 `project_history_ledger(history, sessions, raw_observations, check_d) -> HistoryLedger`

順序（固定）：

1. `validate_history(history)`。
2. §4.4のFixedFactsと、有効解決記録（鎖の順、v2の記録dict）を作る。
3. `LedgerContext.from_facts(facts, sessions, raw_observations, check_d)`（§3.3 A1の順。check_dの検査 → 全境界セッション → 全APPLYのcontext → 全宣言のcontext → 全行の解析）。
4. `resolve_core(ctx, 有効解決記録, history.digest, "resolutions")`：指紋で除外 → CHANGED／ROW_REMOVEDで元行が無い場合だけ保存decisionを補完（APPLYごとに1回） → version_selection → 最終検査（全区間の各APPLYについて保存sessionsと現在sessionsの両方で選ばれる決定が保存値と一致、全skipped_sessionsと全宣言日に決定が無い、check_dの選択）。
5. HistoryLedgerを返す。生台帳・History・入力は変更しない。

check_dは引数で明示する。自動の日付で補わない。

### 5.2 セッション範囲の照合

| 対象 | 比べ方 | 違うとき |
|---|---|---|
| 各有効APPLYのsession_context | 既存`slice_check`：最後の要素（next(D)）はdateとopen_atだけ。他は完全一致 | session_context_missing／session_context_mismatch（detail＝D） |
| 各有効DECLAREのsession_context | 同じ（3件。最後の要素はnext(d)） | 同上 |
| 全区間の境界セッション（GENESIS.boundary_session、RESTART_UNKNOWN.boundary_session） | 現在のsessionsの同じ日と完全一致 | 同上（detail＝境界日） |
| check_dのセッション | sessionsにある・確定・次と前がある | 既存のInputError（target_not_in_sessions、target_unconfirmed、next_session_missing、previous_session_missing） |

next(D)のconfirmed・close_atだけの変化は、判定入力の差にしない（S1・S3-Aと同じ）。境界・D自身・間のセッションのopen_at・close_at・confirmedの変化と、next(D)のopen_atの変化は停止とする。境界セッションの照合は、S1の`prepare_day`には無い（S1では、境界より後にAPPLYがあればcontext[0]として照合され、無ければ候補の検査で`snapshot_invalid`／`context_boundary`になる）。v2では区間が増えるので、すべての境界を同じ規則で先に照合する（§13の差）。

### 5.3 全区間照合と現在区間

- 照合（§5.1の4）は全区間に対して行う。再開始より前の有効APPLY、そのskipped_sessions、宣言日も対象である。後から現れた決定は `late_observation`、保存decisionと違う選択は `ledger_mismatch` で止まる。
- 境界以前で、どのAPPLYのskipped_sessionsにも宣言にも属さない日（例U・例VのD3）の決定は、照合の対象にしない。全行の解析と、同じrecord_idの内容違い（`record_id_conflict`）の検査だけを受ける（上位§2.8、S3-B§7.2）。
- 日次の計算に使うのは現在区間のS1射影だけである（§7）。

### 5.4 HistoryLedger の全キー

不変。`rows`（6列dictの列、写し）、`raw_observations()`（`prepare_day`へ渡す唯一の台帳、写し）、`excluded_fingerprints`、`supplemented`（v2のapplied_refの列）、`ledger_digest`、`effective_digest`、`history_digest`、`check_d`。reprは件数だけを出す。S3-Aの`EffectiveLedger`をそのまま外へ返さない（`resolutions_digest`の欄にv2のhistory digestが入るため）。

## 6. 新規ACK／DECLARE_MISSINGの計画と確認（作成依頼§3.3後半・§3.5）

### 6.1 API

- `prepare_history_resolution_plan(history, commands, sessions, raw_observations, check_d, request_id, reason_code, requested_at) -> HistoryResolutionPlan`（READY／NO_CHANGE）
- `confirm_history_resolution_plan(plan, confirmed_plan_hash, history, sessions, raw_observations) -> HistoryResolutionConfirmResult`

コマンドの形はv2の名前空間：`{kind, variant, d, record_fingerprints, applied_ref, missing_ref}`。applied_refは `{seq, event_hash, fingerprint}`、missing_refは `{kind:"APPLY", seq, event_hash}` か `{kind:"DECLARE_MISSING", seq, event_hash}`。seqはv2物理seq。

### 6.2 作成の順序：構造 → 新しいコマンドの証拠 → 候補全体

1. **構造**：`validate_history(history)`、FixedFactsと有効解決記録、`LedgerContext.from_facts`（check_d・セッション範囲・全行の解析）。
2. `requested_text(requested_at)`、`valid_request_id(request_id)`（違えば `resolution_invalid`／commands／request_id）、コマンドが空でない列であること、各コマンドを `normalize_command(cmd, "v2")` で正規化（違えば `resolution_invalid`／commands／command_shape）、`reason_code ∈ reasons_for_commands`（違えば同／reason_code）。
3. request_hash＝`basis_request_hash({request_id, commands, check_d, reason_code, requested_at})`。§6.5の表で、NO_CHANGEか衝突かを決める。
4. **新しいコマンドの証拠**：`check_commands(ctx, 有効解決記録, commands)`（API-1）。既存の解決記録は、除外と補完の前提として使う（rem0）。ここでは、既存の解決記録を当てた後の台帳を「完成済み」として最終検査しない。未解消の衝突を解くためのACKを作れなくしないためである（S3-Aの`_build`と同じ順）。
5. 新しい記録を組み立てる（§6.3）。
6. **候補全体**：candidate＝history＋新しい記録。`validate_history(candidate)`。候補から作り直したFixedFactsと有効解決記録で、`LedgerContext.from_facts` と `resolve_core(ctx, 候補の有効解決記録, candidate.digest, "commands")` を通す（版選択の拒否はfield＝commands）。
7. basis・plan_hashを作る（§6.6）。

順序の意味：1で入力そのものの不正を既存エラーで止め、4で新しい根拠の妥当性を見て、6で「新しい記録を足した後の台帳全体」が最終検査を通ることを確かめる。6を省くと、例えば一方の乱れだけを解いて別の未解消の乱れを残したACKが、READYになってしまう（依頼書B2-14の対照）。

### 6.3 新しい記録の組立て

各コマンドiについて、ACK・DECLARE_MISSINGの23キーを次の値で作る。

| キー | 値 |
|---|---|
| kind、variant、d、record_fingerprints、applied_ref、missing_ref | 正規化したコマンドのまま（v2名前空間） |
| seq、parent_seq、parent_hash | 先頭seq＋1＋i、その直前、直前のevent_hash |
| session_context、frontier_before | DECLAREは`check_commands`の戻り値、ACKはnull |
| request_id、request_hash、request_basis、command_index、command_count、requested_at | 依頼の値。request_basis＝`{request_id, commands, check_d, reason_code, requested_at}` |
| reason_code | `record_reason(kind)`（ACKはACKNOWLEDGE_LEDGER_CHANGE、DECLAREはMARK_SESSION_MISSING） |
| ledger_digest | LedgerContextのledger_digest |
| origin、replay_of | null |
| state_after | 先頭のstate_after（＝current_state。I-15） |
| event_hash | `compute_event_hash` |

### 6.4 証拠規則

S3-Aと同じ規則（`check_commands`の本文）を、次の事実の上で使う。

| 規則 | v2での事実 |
|---|---|
| ADDED／CHANGED／ROW_REMOVEDのapplied_ref | 有効APPLY（全区間）。退避したAPPLYや一時S1 seqを指すと `ack_evidence` |
| ADDEDの証拠 | 別IDで、Dを対象とするかDの窓内の観測決定。元行が無いときは、同じバッチか既存のCHANGED／ROW_REMOVEDが同じapplied_refを持つこと（バッチ全体から先に集めるので、並べ順に依存しない） |
| ROW_REMOVED | 元行が無く、同じrecord_idの未承認の別版が無いこと。指紋は空 |
| CHANGED | 同じrecord_idで別指紋の行 |
| LATE | Dは全区間のどのAPPLY日でもない。missing_refは、有効APPLYでskipped_sessionsにDを含むもの、または**この依頼より前の**有効DECLAREで同じDのもの（v2の参照形、A3）。同じバッチ内の宣言は参照できない（S3-Aと同じ） |
| exclude_applied | 全区間の有効APPLYの固定指紋を除外しない |
| DECLARE | Dは全区間のどのAPPLY日でもない。frontier＝max(現在区間の境界、現在区間の最新APPLY日、有効宣言日)。旧区間の宣言日・APPLY日はfloorにより境界以下なので、現在のfrontierを進めない。Dはfrontierの次の確定セッションで、Dの次がある。決定が無いか、Dに属する乱れがあるときだけ宣言できる（採用済みN-04：有効な決定1件は `declare_valid_decision`）。乱れの行を漏れなく挙げる（`declare_incomplete`）。同じバッチの前の宣言はfrontierを進める |
| check_d | 現在区間の境界より後（`target_not_after_boundary`）、全区間の最新APPLY日以上（`state_ahead_of_target`）。ACKのD・宣言のDはcheck_d以下 |
| version_selection | 除外したrecord_idの別版が最終台帳に残ってよいのは、全区間の有効APPLYの固定指紋である場合だけ |

S3-Aと意味が違う点は無い。違うのは事実の集め方（全区間、v2の参照形、境界の一般化）だけである（§13）。

### 6.5 request_idの扱い

request_idは**物理履歴全体**（退避記録を含む）と照合する（EffectiveView.requests）。

| 場合 | 結果 |
|---|---|
| どの記録にも無い | 新しい依頼として作る |
| 有効鎖のNATIVEの解決依頼で、request_hashが同じ（requested_atだけが違う場合を含む） | NO_CHANGE。現在の有効解決記録での投影（§5.1の4）を検査してから返す |
| 有効鎖のREPLAYEDの解決依頼で、request_hashが同じ（元のコマンドを同じまま再提出した場合） | NO_CHANGE（同上） |
| 有効鎖のNATIVE／REPLAYEDの解決依頼で、request_hashが違う | `history_request_conflict`／request_id |
| MIGRATEDの解決依頼 | 内容にかかわらず `history_request_conflict`。保存したrequest_basisはS3-Aの名前空間で作られている。例Mの最初のAPPLYのようにv1とv2でseq・event_hashが同じ記録を指す場合は、元と同じbasisをv2のコマンドで作るとrequest_hashが一致し得る。それでも、名前空間をまたぐ同じ依頼の再提出を、B-2では保証も受理もしない（保守的にconflictとする。hashの一致・不一致で結果を変えない） |
| 退避記録だけにある（DROPした依頼など） | `history_request_conflict`。取り消した依頼を同じIDで作り直さず、新しいIDを使う |
| RESTART_UNKNOWN・RECOVERY_RESTORE・SCHEMA_MIGRATIONのrequest_id | `history_request_conflict` |

複数コマンドの依頼は1バッチ（連続、command_index 0..count−1）。同じrequest_idの記録が有効鎖に2組並ぶことは、B-1の検査で起こらない。

### 6.6 計画のbasisとplan_hash

basisの全キー：`operation`（"soxl-v2-history-resolution-plan/1"）、`status`（READY／NO_CHANGE）、`history_digest`、`expected_head_seq`、`expected_head_hash`、`request_id`、`request_hash`、`requested_at`、`check_d`、`reason_code`、`ledger_digest`、`sessions_digest`、`commands`（正規化済み）、`candidate_history`（dict）、`candidate_digest`、`expected_state_digest`（先頭の状態。ACK・DECLAREは状態を変えない）、`excluded_fingerprints`、`supplemented`、`effective_digest`（候補の投影）。

plan_hash＝basisの正規化JSONのSHA-256。記録はplan_hashを持たない（循環させない）。NO_CHANGEでは candidate_history＝現在の履歴、candidate_digest＝history_digest。

`HistoryResolutionPlan` は不変で、`from_dict`／`to_dict`／`basis`（写し）／`plan_hash`（写し）／`status`／`committed`（False）／`summary()`／reprを持つ。表示は許可リスト（status、request_id、check_d、コマンドごとのkind・variant・d・指紋の件数、新しい記録の件数、除外・補完の件数、plan_hash）で、各値を表示の前に形で再検査し、不正なら固定表現にする（S3-A R-01、B-1と同じ）。from_dictは、コピーの前にJSONの深さとJSONで表せる型かを検査し（整数欄のbool・floatなど意味の検査は確認の手順1で行う。§12.8の2）、深さ超過・巨大整数は固定のrule（history_invalid／plan_shape・json_depth・json_number）にする。

### 6.7 確認の順序とエラー

`confirm_history_resolution_plan(plan, confirmed_plan_hash, history, sessions, raw_observations)`：

| 順 | 検査 | 失敗のcode／field |
|---|---|---|
| 1 | planの型、`{basis, plan_hash}`の形、plan_hash＝SHA-256(basis)、confirmed_plan_hash＝plan_hash、basisのキー、operation、status、check_d・request_id・requested_atの形 | `history_plan_mismatch`／plan |
| 2 | 入力そのもの：`validate_history(history)`、`copy_sessions`、`parse_ledger` | 既存のエラーのまま（history_invalid、unsupported_schema、sessions_invalid、行のInputError等）。staleへ変換しない |
| 3 | 有効な入力の差。次の枝A・枝Bのどちらかに当たるか。**枝A（元の履歴）**：history.digest＝basis.history_digest、かつhistory.head_seq／head_hash＝basis.expected_head_seq／expected_head_hash。**枝B（候補の履歴）**：basis.status＝READY、history.digest＝basis.candidate_digest、かつhistory.head_seq／head_hash＝basis.candidate_historyの先頭（最後の記録のseq／event_hash）。枝Bでは元のexpected_head_*との一致を求めない。どちらの枝でも、ledger_digest・sessions_digestはbasisと同じ | どちらにも当たらなければ `history_plan_stale`／plan |
| 4 | §6.2の2〜7で作り直し、期待するbasisと完全一致。枝Aの期待basisは元のbasisそのもの。枝Bの期待basisは下の結果表の3行目のとおり。全digestが一致しているので、作り直しでCoreErrorが出たら計画自身の誤り | `history_plan_mismatch`／plan |

結果：

| 状況 | status | 値 |
|---|---|---|
| 計画時と同じ履歴（READY） | CONFIRMED_IN_MEMORY | committed=False、候補History、HistoryLedger（候補の投影）、HistoryAppendBatch（U-2がR-aの場合）、plan_hash |
| 計画時と同じ履歴（計画がNO_CHANGE） | NO_CHANGE | batchはnull |
| 計画の候補そのものが今の履歴（同じ計画の再確認、手順3の枝B） | NO_CHANGE | 期待するbasisは、元のbasisのうち次の4項目だけを変えたもの：status→NO_CHANGE、history_digest→basis.candidate_digest、expected_head_seq／expected_head_hash→候補の先頭。candidate_history・candidate_digestは元の値のまま（NO_CHANGEの規則「candidate_history＝現在の履歴」と一致する）。request_*・check_d・reason_code・commands・ledger_digest・sessions_digest・expected_state_digest・excluded_fingerprints・supplemented・effective_digestも元のまま（元の値は候補の投影から作っているため）。作り直したbasisのplan_hashは元のplan_hashと違うので、比べるのはbasisの各項目で、plan_hashではない。batchはnull |
| 候補の後にさらに記録が足された履歴 | `history_plan_stale` | 候補が今の履歴の前半であっても、照合（ALREADY_PUBLISHED等）はS3-Cの責任なので、B-2はstaleとする |

S3-Aの確認との違い：S3-Aは手順2で`Ctx`を作るので、有効だが変わったsessionsで範囲が合わない場合に、staleでなく`session_context_mismatch`になることがある。B-2は、B-1の移行確認（P-02採用の順）と同じく、手順2では入力の形と正しさだけを見て、範囲の照合は手順4に回す。digestが一致しない正常な変更はstaleになり、不正な入力は既存エラーになる（§13）。

## 7. 日次処理（作成依頼§3.4）

### 7.1 `prepare_history_day(history, d, series, sessions, raw_observations) -> HistoryDayResult`

順序（固定）：

1. `validate_history(history)`。
2. Dを日付として解析（既存の`target_session_date`のInputError）。
3. `project_history_ledger(history, sessions, raw_observations, check_d=D)`。ここで、D ≤ 現在区間の境界は `target_not_after_boundary`、D＜全区間の最新APPLY日は `state_ahead_of_target`、Dと前後のセッション、全区間の範囲照合と最終検査が行われる。
4. §4.5の現在区間のS1 Snapshotを作る。
5. `prepare_day(snapshot, D, series, sessions, ledger.raw_observations())` を**ちょうど1回**呼ぶ。通常の計算は既存`evaluate_day`、保存入力の再計算は既存の検査器と`apply_transition`に任せる。戦略式・閾値・状態式を複製しない。
6. PREPAREDなら、返ったeventの内容6項目（d、confirmed_inputs、input_hash、skipped_sessions、transition_result、state_after）をそのまま保ち、`seq`＝head_seq＋1、`parent_seq`＝head_seq、`parent_hash`＝head_hash を付け直して `compute_event_hash` する。親は物理的な先頭（ACK・DECLARE・RESTOREの後ならそれ）で、現在区間の最後のAPPLYではない。
7. candidate＝history＋APPLY。`validate_history(candidate)` と `project_history_ledger(candidate, sessions, raw_observations, D)` を通す（次回の実行と同じ検査を、準備の時点で候補に行う）。
8. HistoryDayResultを返す。PREPAREDのときだけ batch（`source="DAILY"`）を持つ。S1の`AppendPlan`・`PrepareResult`は外へ返さない。

日次のDは引数で明示する。自動の日付で補わない。

### 7.2 状態と意味

| 値 | 意味 |
|---|---|
| PREPARED | 新しいAPPLY1件の候補を作り、候補全体が§7.1の7を通った。保存はしていない |
| NO_COMMIT | Dに決定が無い（宣言日を含む）。記録を作らない。状態は変えない |
| ALREADY_APPLIED | Dは現在区間の最新APPLY日で、再計算が保存値と一致した。記録を作らない |
| core_result.state_updated | コアの意味（新しい遷移の候補があるか）のまま。保存・確認とは関係しない |
| CONFIRMED_IN_MEMORY | 解決計画の確認で、作り直した結果が計画と一致した（§6.7）。保存ではない |
| committed | B-2のすべての値で常にFalse |
| committable | 常にFalse（B-2にストアは無い） |

### 7.3 結果の表

| 状況 | 結果 |
|---|---|
| D ≤ 現在区間の境界（GENESIS区間ならstart_after以下、再開始後ならresume_after以下。前の区間の最終APPLY日を含む） | `target_not_after_boundary`／target_session_date（S1の`target_not_after_genesis`は出ない） |
| 境界＜D＜現在区間の最新APPLY日 | `state_ahead_of_target`（既存） |
| D＝現在区間の最新APPLY日、入力が保存値どおり | ALREADY_APPLIED |
| 同上、seriesの行やsessionsが変わって再計算が違う | 既存`recompute_mismatch`（field＝confirmed_inputs／transition_result／state） |
| 宣言済みのD | NO_COMMIT（宣言で除外した乱れの行は投影に残らず、決定が無い） |
| 決定の無いD | NO_COMMIT |
| 間のセッションに窓内の決定がある | 既存`intermediate_session_unprocessed` |
| 間のセッションを対象とする決定が、その窓の外で観測された | 既存`decision_outside_window`（コアのInputError） |
| Dの窓内に別の日を対象とする決定がある | 既存`target_mismatch` |
| 間のセッションが未確定 | 既存`intermediate_session_unconfirmed` |
| Dが未確定・次が無い・前が無い | 既存`target_unconfirmed`／`next_session_missing`／`previous_session_missing` |
| 再開始後の最初の処理（決定あり） | PREPARED。skipped_sessions＝境界の次からDの前まで。gap等はコアの値（例U） |
| 旧区間のAPPLYの台帳が変わった | `ledger_mismatch`（detail＝旧区間のD）。ACK（§6）で解くまで止まる |
| 旧区間のskipped_sessions・宣言日に決定が現れた | `late_observation`。LATE（§6）で解くまで止まる |

S1との順序の違い：S1の`prepare_day`は、D・sessions・間のセッションの検査の後で台帳を照合する。B-2は、S3-Aの`prepare_resolved_day`と同じく、全区間の台帳投影（§7.1の3）を先に行い、その後で`prepare_day`が間のセッションを調べる。台帳の不一致と間のセッションの未確定が同時にあれば、B-2は`ledger_mismatch`を先に返す（§13）。

### 7.4 再実行の不変条件

- **受理した候補を新しい履歴として、同じ入力で同じDを準備すると、ALREADY_APPLIEDになる。** 例：H1＝`check_append_batch(H0, prepare_history_day(H0, D1, …).batch)` のとき、`prepare_history_day(H1, D1, 同じ入力)` はALREADY_APPLIED。
- 準備時の検査は、次回の実行の検査より狭くしない。§7.1の7で、候補を`validate_history`と全区間の投影（新しいAPPLYの保存decisionの照合を含む）に通す。
- 同じ入力で同じ履歴に対して2回準備すると、同じ結果（同じbatch_hash）になる。

## 8. バッチ値と保存の境界（作成依頼§3.5）

### 8.1 上位の記述差

S3-B第2版§2はB-2の内容に「公開用バッチ値」を挙げる。一方、§9.1は「公開値の定義はS3-B、実装・実行はS3-C」とする。前者は値をB-2で作るように読め、後者は実装をS3-Cに置くように読める。本書はこの差を解消済みとはしない。次の推奨をユーザーの判断（U-2）に委ねる。

### 8.2 推奨 R-a：値と純粋な再検査はB-2、I/Oと実行はS3-C

| 段階 | 責任 |
|---|---|
| B-2 | `HistoryAppendBatch`（純粋な値）と、`check_append_batch(history, batch)`（純粋な再検査）。生成は日次のPREPAREDと、解決計画のCONFIRMED_IN_MEMORYからだけ |
| S3-C | 書込みロック、残留物の走査、ロックの下での読み直し、`check_append_batch`の呼び出し、候補全体の一時ファイル→fsync→1回のreplace→（strictなら）ディレクトリ同期、成否不明の扱い、照合（S3-B§9.4）、解錠・保守ゲート、Windows strict |

理由：何を足すか（期待先頭、記録、候補digest、計画hash、空バッチの扱い）を、I/Oを含まない純粋な値として先に固定し、試験できる。S3-Cは、I/Oと実行の正しさだけを担えばよい。代替のR-bは、B-2では候補Historyだけを返し、バッチ値の定義・実装をS3-Cに回すもの。R-bでも§7.4の不変条件は「候補Historyを新しい履歴として」で確かめられる。

HistoryReplacement（v1→v2の置き換え）とB-1の移行APIは、どちらの案でもB-2に含めない。

### 8.3 `HistoryAppendBatch`（R-aの場合）

全キー（body）：

| キー | 内容 |
|---|---|
| operation | "soxl-v2-history-append-batch/1" |
| source | "DAILY" か "RESOLUTION" |
| d | DAILYはD、RESOLUTIONはnull |
| request_id、plan_hash | RESOLUTIONは依頼IDと確認したplan_hash、DAILYはnull |
| expected_head_seq、expected_head_hash、expected_history_digest | 追加する前の履歴 |
| records | 追加する記録の列（1件以上） |
| candidate_head_seq、candidate_head_hash、candidate_digest、candidate_state_digest | 追加した後の履歴 |

値は `{body, batch_hash}` で、batch_hash＝bodyの正規化JSONのSHA-256。記録はbatch_hashもplan_hashも持たない。

- **生成経路**：`prepare_history_day` のPREPARED（APPLY1件）と、`confirm_history_resolution_plan` のCONFIRMED_IN_MEMORY（同じrequest_idの解決記録1件以上）だけ。`prepare_history_resolution_plan`（未確認）からは作らない。
- **空バッチ**：作らない。NO_COMMIT・ALREADY_APPLIED・NO_CHANGEではbatch＝null。`from_dict`で空のrecordsを与えた値は、`check_append_batch`が`batch_invalid`／records で拒否する。
- `from_dict`／`to_dict`：受け渡し用。from_dictは形とJSONの深さ・型だけを見て、検証済みとは扱わない。表示（repr・summary）は、source・d・request_id・件数・seq・hashだけを、形を再検査してから出す。

`check_append_batch(history, batch) -> History`（候補、committed相当の意味は無い）：

| 順 | 検査 | 失敗 |
|---|---|---|
| 1 | batchの型、`{body, batch_hash}`の形、bodyのキー、operation・sourceの値、batch_hash＝SHA-256(body)、JSONの深さ・型、整数欄はboolやfloatでない | `batch_invalid`／batch、rule（type、batch_shape、batch_hash、json_depth、json_number） |
| 2 | `validate_history(history)` | 既存のエラーのまま |
| 3 | history.digest・head_seq・head_hashが期待値と同じ | `batch_stale`／head（候補そのものが今の履歴である場合も含む。照合はS3-C） |
| 4 | recordsが1件以上、seqがexpected_head_seq＋1から連続、DAILYはAPPLY1件でd一致、RESOLUTIONはACK／DECLAREだけで全件同じrequest_idかつcommand_count＝件数 | `batch_invalid`／batch、rule（records、seq、source） |
| 5 | candidate＝history＋records。candidate.digest・先頭・状態digestが期待値と同じ | `batch_invalid`／batch、rule＝candidate_digest |
| 6 | `validate_history(candidate)` | 既存の`history_invalid`等 |

DAILYのバッチは台帳・sessions・seriesのdigestを持たない。S1の`AppendPlan`と同じく、日次の入力の正しさは準備の時点で確かめ、公開の時点では期待先頭と候補の正しさだけを見る。RESOLUTIONのバッチは、確認したplan_hashを持つ。S3-Cが公開の直前に確認を作り直すかは、S3-Cで決める（§15）。

### 8.4 型の境界

`HistoryLedger`、`HistoryDayResult`、`HistoryResolutionPlan`、`HistoryResolutionConfirmResult`、`HistoryAppendBatch`、候補Historyは、いずれも`AppendPlan`ではない。既存`MemoryStore.commit`・`LocalFileStore.commit`へ直接渡すと、既存の`plan_type`で拒否される。v2のテキストを`snapshot.json`に置けば、既存の`read`・`initialize`は`unsupported_schema`で止まる（B-1のH-12で確認済み）。新しいv2ストアはB-2の都合で追加しない。

### 8.5 S3-Cへ留保すること

実保存、CAS実行、fsync／replace、成否不明の後の照合、解錠、保守ゲート、Windows strict、元バイトの退避、ALREADY_PUBLISHED等の判定。計画の確認や`check_append_batch`の成功だけで、保存・耐久性・通知の権利を得たとはしない。

## 9. 公開API（`v2_history_ops`）

| 名前 | 引数 | 戻り値 |
|---|---|---|
| `read_effective` | history | EffectiveView（§4.1） |
| `project_history_ledger` | history、sessions、raw_observations、check_d | HistoryLedger（§5.4） |
| `prepare_history_day` | history、d、series、sessions、raw_observations | HistoryDayResult |
| `prepare_history_resolution_plan` | history、commands、sessions、raw_observations、check_d、request_id、reason_code、requested_at（aware日時） | HistoryResolutionPlan（§6.6） |
| `confirm_history_resolution_plan` | plan、confirmed_plan_hash、history、sessions、raw_observations | HistoryResolutionConfirmResult |
| `HistoryAppendBatch`、`check_append_batch` | batch：from_dict／to_dict。check：history、batch | 候補History（§8.3） |
| 定数 | PREPARED、NO_COMMIT、ALREADY_APPLIED（S1と同じ文字列）、READY、NO_CHANGE、CONFIRMED_IN_MEMORY、DAILY、RESOLUTION | — |

`HistoryDayResult` の全キー：`status`、`d`、`history_digest`、`core_result`（写し）、`batch`（HistoryAppendBatchかnull）、`candidate_digest`（PREPAREDだけ）、`committable`（False）、`committed`（False）。`plan`という名前の属性は持たない。

`HistoryResolutionConfirmResult` の全キー：`status`、`committed`（False）、`history`（候補History）、`ledger`（HistoryLedger）、`batch`（HistoryAppendBatchかnull）、`plan_hash`、`state_unchanged`（True）。

すべての値は不変で、構造化した値は写しを返す。repr・エラーは、固定のcode／field／ruleと、件数・seq・hash・日付だけを出す。raw行・F&G値・URL・note・source_url・パス・例外文を出さない。例外連鎖は抑える。

## 10. hashとdigest

| 名前 | 計算 |
|---|---|
| event_hash | 既存`compute_event_hash`（B-1と同じ） |
| request_hash | `basis_request_hash`（request_basisからrequested_atを除いた正規化JSONのSHA-256。S3-Aの`request_hash_of`と同じ値） |
| history_digest、candidate_digest | `History.digest`（正規化テキストのSHA-256） |
| state digest | current_stateの正規化JSONのSHA-256 |
| ledger_digest、sessions_digest | S3-Aの関数（6列・順序なし・個数保持／sessions全体） |
| effective_digest | S3-Aの`EffectiveLedger.effective_digest`（最終台帳の行） |
| plan_hash | 解決計画のbasisの正規化JSONのSHA-256 |
| batch_hash | HistoryAppendBatchのbodyの正規化JSONのSHA-256 |

hashは改ざん検知のための整合性値で、署名・真正性・台帳の完全性を証明しない。

## 11. エラー分類と優先順

### 11.1 B-2で新しく使うcode

| code | field／rule | 条件 |
|---|---|---|
| target_not_after_boundary | target_session_date | check_d・日次のDが現在区間の境界以下（LedgerContext） |
| history_request_conflict | request_id | §6.5 |
| history_plan_mismatch | plan | 計画の改変、確認hashの違い、全digest一致での作り直しの不一致 |
| history_plan_stale | plan | 有効な入力のdigest・先頭の違い |
| batch_invalid | batch、rule固定 | §8.3 |
| batch_stale | head | §8.3 |
| facts_invalid（API-1） | facts、rule固定 | FixedFacts.from_partsの形の不正、LedgerContextに別の型 |
| resolution_invalid（既存のcode） | commands、rule＝command_shape・reason_code・request_id | 新しいコマンドの形（v2_historyの`history_invalid`をこのcodeへ変換） |

既存のcodeはそのまま通す：history_invalid／unsupported_schema／unsupported_event（履歴）、InputError・ConflictError（日付・sessions・行・選択）、session_context_missing／mismatch、ledger_mismatch、late_observation、resolution_invalid（証拠のrule：ack_evidence、exclude_applied、late_missing_ref、declare_frontier、declare_applied、declare_unconfirmed、declare_valid_decision、declare_incomplete、version_selection）、S1の`prepare_day`のcode（intermediate_session_unconfirmed、intermediate_session_unprocessed、recompute_mismatch、snapshot_invalid／event_build等）。

### 11.2 優先順

- 投影：履歴 → check_d・sessions → 境界セッション → APPLYのcontext → 宣言のcontext → 全行の解析 → 除外・補完 → version_selection → 最終検査。
- 日次：履歴 → Dの解析 → 投影（上の順） → `prepare_day`（S1の順） → 候補の検査。
- 解決計画：履歴 → 投影の前半（check_dから全行の解析まで） → requested_at → request_id → コマンドの形 → reason_code → request_idの照合 → 証拠 → 候補の検査 → 候補の投影。
- 確認：§6.7の1〜4。
- バッチの再検査：§8.3の1〜6。

## 12. 時系列の具体例

日付D0〜D8は連続した確定セッション。q1〜は依頼ID。F&G値などは合成fixtureでのコアの期待であり、市場の実測ではない。以下の期待は、固定したコードを読んで導いた設計上の期待で、実行で確かめた値ではない。

### 12.1 流れ1：GENESISだけの履歴

H0＝`make_history_genesis(D0)`。台帳L1＝D1の決定a1。
1. `prepare_history_day(H0, D1, …, L1)` → PREPARED。batchのrecordsは APPLY D1（seq1、parent 0、skipped=[]）。H1＝`check_append_batch(H0, batch)`。
2. `prepare_history_day(H1, D1, 同じ入力)` → ALREADY_APPLIED、batch=null。
3. `prepare_history_day(H0, D1, …, 決定なし)` → NO_COMMIT。`prepare_history_day(H1, D2, …)`（D2に決定なし） → NO_COMMIT。D3に決定b3があれば `prepare_history_day(H1, D3, …)` → PREPARED、skipped=[D2]。
4. `prepare_history_day(H0, D0, …)` → `target_not_after_boundary`。`check_append_batch(H1, 1のbatch)` → `batch_stale`（先頭が進んでいる）。

### 12.2 流れ2：移行済み履歴（例M）への新規ACK／DECLARE

例Mのv2（S3-B§5.7）：0 GENESIS ／ 1 APPLY D1 ／ 2 ACK r1 ／ 3 APPLY D2 ／ 4 DECLARE D3 ／ 5 APPLY D4 ／ 6 ACK r3 ／ 7 SCHEMA_MIGRATION。
1. 台帳でD2の決定が同じrecord_idの別版に変わる → `project_history_ledger(…, check_d=D5)` は `record_id_conflict` か `ledger_mismatch`。コマンド ACK/CHANGED(D2, applied_ref={seq:3, event_hash:h3(v2), fingerprint}) q4 → READY。新しい記録はseq8、origin=null、親は7。
2. 誤ってS1の番号（applied_ref.seq=2、v1のhash）を渡す → seq2は解決記録でAPPLYではないので `ack_evidence`。
3. D5に決定が無い → DECLARE(D5) q5 → frontier＝max(境界D0、最新APPLY D4、宣言D3)＝D4、d＝D5。続けて `prepare_history_day(…, D6)` → PREPARED、skipped=[D5]。
4. 候補から `migrated_sources` を呼ぶと、元のv1 SnapshotとSetが同じdigestで戻る（移行範囲はseq7より前だけで、新しい記録は影響しない）。
5. 移行記録のrequest_id（r1の依頼ID）を新しい依頼に使う → `history_request_conflict`。

### 12.3 流れ3：再開始の後（例V、本書で追加）

例V：0 GENESIS(D0) ／ 1 APPLY D1 ／ 2 DECLARE_MISSING D2 q1（frontier D1） ／ 3 RESTART_UNKNOWN(resume_after=D3, floor={D1, D2, D0}) q2。
1. 台帳でD1の決定が別版に変わる → `project_history_ledger(H, …, check_d=D4)` → `ledger_mismatch`（detail D1）。旧区間のAPPLYも照合される。
2. ACK/CHANGED(D1, applied_ref={seq:1,…}) q3（check_d=D4） → READY、seq4。check_d=D3 では `target_not_after_boundary`。
3. D2の決定が後から現れる → `late_observation`。ACK/LATE(D2, missing_ref={kind:DECLARE_MISSING, seq:2, event_hash:h2}) → READY。
4. D4に決定が無い → DECLARE(D4) → frontier＝D3（境界）。旧区間の宣言D2・APPLY D1はfrontierを進めない。DECLARE(D3)は `declare_frontier`。
5. 日次：D2・D3 → `target_not_after_boundary`。D4に決定あり → PREPARED、APPLYの親は先頭（ACKならその記録）、skipped=[]、gap=false（コアの値）。射影されるS1 SnapshotはGENESIS(D3)と現在区間のAPPLYだけ。
6. D3を対象とする決定が現れても、処理しない・LATEにもしない。解析とrecord_idの衝突検査だけ。

### 12.4 流れ4：復元の後（例R、例R-b）

例R（S3-B§8.9）の台帳L_Rは、D3に別IDの決定行z3を含む。z3は#5のACK/ADDED q2が除外していた。
1. RESTORE#2の後（有効鎖は0、1、2、7、8、9、14〜17）：q2は#9（replay_of=5）として有効で、`project_history_ledger`はz3を除外して通る。applied_refは#8（写像済み）で、#4ではない。
2. RESTORE#3の後（有効鎖は0、1、2、18〜22）：q2はDROPされ、有効解決記録は無い。`project_history_ledger`はz3を除外しないので、D3（#19）の照合で `decision_conflict` になる。退避した#5・#9は使わない。
3. 新しい依頼 ACK/ADDED(D3, applied_ref={seq:19,…}) を、例Rで未使用のq7で出す → READY（新しい記録はseq23、親は#22）。例Rで使用済みの依頼IDはq1〜q6（q1・q3はRESTART_UNKNOWN、q2はACK、q4〜q6はRESTORE#1〜#3）で、§6.5により物理履歴全体と照合する。依頼IDの対照：同じコマンドをq4で出す → `history_request_conflict`（q4はRESTORE#1＝#7の依頼IDで、退避後も物理履歴に残る）。q2で出す → `history_request_conflict`（RESTORE#3でDROPされた解決依頼のID）。q7のままapplied_refに#4・#8（退避）を指定 → `ack_evidence`。fixtureの依頼IDとID検査は変えない。
4. 日次 D7 → PREPARED、親は#22（または足したACK）。

例R-b（S3-B§8.9）：有効鎖は0、1、6、7、8、9で、宣言は#8（replay_of=4）。
5. FixedFactsの宣言は#8のsession_contextで、#4のものではない。D3に決定が現れると `late_observation`。ACK/LATE(D3, missing_ref={DECLARE_MISSING, seq:8, h8}) → READY。seq:4を指す → `late_missing_ref`。APPLY型（missing_ref={APPLY, seq:9}）も受理。
6. 退避した記録のhashの検査は、B-1の`validate_history`が引き続き行う（B-2は物理配列を読み飛ばさず、まずその検査を通す）。

### 12.5 流れ5：証拠の組合せ

基本の履歴H1：0 GENESIS(D0) ／ 1 APPLY D1（決定a1、record_id "a"）。
1. 元行a1を消し、同じ値を別ID "b"（行b1）で打ち直した台帳 → 投影は `ledger_mismatch`。依頼 {ROW_REMOVED(D1, applied_ref=#1, 指紋[]), ADDED(D1, applied_ref=#1, [fp(b1)])} を、この順と逆順の両方で → どちらもREADY。最終台帳はa1を補完し、b1を除外。
2. a1が同じID "a" の別版a1'になり、さらに別ID "c" の行c1もD1の窓にある → {CHANGED(D1, [fp(a1')]), ADDED(D1, [fp(c1)])} を両方の順で → READY。
3. D2に有効な決定が1件ある → DECLARE(D2) → `declare_valid_decision`（採用済みN-04）。
4. H1に APPLY D3（skipped=[D2]）を足した履歴で、D2を対象とする同じID "x" の2版x1・x1'が後から現れる → LATE(D2, missing_ref＝APPLY D3, [fp(x1)]) は証拠を通るが、候補の投影でx1'が残るので `version_selection`。
5. 指紋に#1の固定指紋を含める → `exclude_applied`。ACKのD＞check_d → `ack_evidence`。
6. LATEの2つの参照形：APPLY型（missing_ref＝APPLY D4、D3∈skipped）と宣言型（missing_ref＝有効DECLARE）。同じ依頼の中で宣言した日を同じ依頼のLATEで参照 → `late_missing_ref`。同じ依頼でDECLARE(D2)とDECLARE(D3)を並べる → frontierが進み、READY。

### 12.6 流れ6：セッションの変化

H2：0 GENESIS(D0) ／ 1 APPLY D1（context＝[D0, D1, D2]）。
1. D2（＝next(D1)）のclose_atだけ、またはconfirmedだけを変える → `project_history_ledger(…, check_d=D1)` は通る（D1の保存範囲の最後の要素は、dateとopen_atだけを比べる）。ただしD2をconfirmed=falseにした場合、`prepare_history_day(…, D2)` は `target_unconfirmed`。
2. D2のopen_at、D1のclose_at、D0（境界）のopen_atを変える → `session_context_mismatch`。
3. D3を処理し、D2が未確定 → `intermediate_session_unconfirmed`。D2に窓内の決定 → `intermediate_session_unprocessed`。D2を対象として窓外で観測された決定 → `decision_outside_window`。

### 12.7 流れ7：計画の改変・確認

1. 計画のbasisを改変、plan_hashだけ付け直す、確認hashを違える → `history_plan_mismatch`。
2. 有効なまま履歴を1件延長、台帳に無関係の行を足す、sessionsの範囲外の日を足す → `history_plan_stale`。
3. 確認時に、壊れた履歴、行として解析できない台帳、SessionListでないsessionsを渡す → 既存のエラー（staleにしない）。
4. 同じ計画を、その候補を今の履歴として再確認 → NO_CHANGE。候補にさらに1件足した履歴 → `history_plan_stale`。
5. request_idの再利用は§6.5の各行。
6. **候補全体の検査の対照**：履歴 0 GENESIS(D0) ／ 1 APPLY D1 ／ 2 APPLY D4（skipped=[D2, D3]）。D1に乱れ（別IDの決定行）があり、同時にskippedのD3にも後発の決定がある。ADDED(D1)だけの依頼は証拠検査を通るが、候補の投影でD3の `late_observation` が残るので計画は作られない。候補の投影を省く欠陥があれば、READYになって検出される。

### 12.8 流れ8：不変性・型・秘匿

1. 入力のdict／list、戻り値（EffectiveView、HistoryLedger、計画、確認結果、batch）の入れ子を書き換えても、元の値・History・計画・batchのテキスト・digest・等値・hashは変わらない。
2. 型の検査は2段階に分け、混ぜない（B-1と同じ役割分担。意味の検査を読込口へ移さない）。
   - **読込口で拒否**：計画・batchの`from_dict`は、JSONの深さ超過・巨大整数（数値の限界）・JSONで表せない型を、コピーの前に§6.6／§8.3の固定のrule（json_depth・json_number等）で拒否する。
   - **読込みは通り、意味の検査で拒否**：整数欄（expected_head_seq、records内のseq、command_index等）にTrue・1.0を入れた値はJSONとして正しいので、`from_dict`は値を保持して返す。その値を`confirm_history_resolution_plan`に渡すと手順1で`history_plan_mismatch`、`check_append_batch`に渡すと手順1で`batch_invalid`（rule＝type等）になる。boolやfloatを整数として扱わない。
3. 台帳行に生URL・自由文・note・source_urlを入れても、repr・summary・例外の文字列に現れない。F&G値も現れない。

## 13. 上位設計・S3-A・B-1との差

| 項目 | 上位・既存 | B-2 | 理由 |
|---|---|---|---|
| S3-Aの再利用 | S3-B§10の第一案：S3-Aの関数を、v2を読む表示から呼ぶ。既存は変えない | 公開名だけでは成立しない（§3.2）。API-1（最小差分）かAPI-0（明示移植）をU-1で選ぶ | Ctxと証拠検査の構造 |
| 公開用バッチ値 | §2：B-2に含む。§9.1：実装はS3-C | R-a（値と純粋な再検査はB-2）を推奨、U-2 | 記述差の解消 |
| 境界以前のコード | S1：`target_not_after_genesis`。S3-B§7.2：再開始後は`target_not_after_boundary` | 全区間で`target_not_after_boundary` | 境界はstart_afterの一般化 |
| 境界セッション | S1：APPLYがあればcontext[0]として照合、無ければ候補検査で`snapshot_invalid`／`context_boundary` | 全区間の境界を先に完全一致で照合し、`session_context_mismatch` | 区間が複数になるため |
| 照合とS1の順 | S1：間のセッション→台帳 | 台帳投影→`prepare_day`（S3-Aの`prepare_resolved_day`と同じ） | 全区間の投影が前提 |
| 確認の順 | S3-A：Ctx（範囲照合を含む）→stale | B-1と同じく、形と正しさ→stale→作り直し | P-02の方針を維持 |
| request_idの照合 | S3-A：Set内だけ | 物理履歴全体（退避・移行・他種別を含む） | 退避した依頼の再有効化を防ぐ |
| frontierの基点 | S3-A：start_afterか最新APPLY日 | 現在区間の境界か最新APPLY日（floorにより全区間の最大と同じ） | 意味は同じ一般化 |

B-1の形式（schema_version=2、7種のキー、hash、検査器、復元点の下限、I-15、IB-04、ビュー内のrequest_idの一意）は緩めない。B-2が作るのは、`validate_history`を通る記録だけである。S3-Aの受理・拒否、採用済みN-04、ADDEDの証拠の範囲、version_selectionの禁止は変えない。

## 14. 範囲外・採用しないこと

- B-3（RESTART_UNKNOWNの計画）、B-4（RECOVERY_RESTOREの計画、CONSUME）、B-5（破損診断、prefix採用）、S3-C（公開・実行・照合・解錠・保守ゲート・Windows strict）。
- HistoryReplacement、B-1の移行APIの変更、新しいv2ストア、CLI、通知・outbox・手動再送・配信権。
- 自動の対象日・追いつき、任意区間の一括欠測、時計・ネット・プロセス・スレッド・乱数・環境変数。
- 戦略式・閾値・状態式の複製、S3-AやS1の受理・拒否の変更、CORRECTION（U-03）と未処理の版の選択。
- 保有・原価・売却済み状態の更新、自動発注、口座接続、資金移動。本番の保存先・資格情報（U-01／U-11／U-13）。

## 15. 未決事項

「本書の推奨」は作成担当（Claude Opus 5.5）の推奨で、未採用。ユーザーの判断が必要なものは次の3点に絞った。B-1の採用済み事項（D-1・D-2・D-4）、N-04、売買戦略、本番の保存先や資格情報は再質問しない。

| ID | 内容 | 本書の推奨 | 主担当の判断 | ユーザーの採否 |
|---|---|---|---|---|
| U-1 | S3-A規則の再利用の方法 | API-1：v2_recoveryに新規`facts.py`、`commands.py`の切り出しとLATE宣言参照の分岐（§3.3）。既存176件・目印の数え上げ・commands.pyの変異の再実行で回帰を示す | 推奨（主担当レビューce07dbd。ユーザーの採用ではない） | 未採用 |
| U-2 | バッチ値の境界（上位§2と§9.1の記述差） | R-a：`HistoryAppendBatch`と`check_append_batch`はB-2、I/Oと実行はS3-C（§8.2） | 推奨（主担当レビューce07dbd。ユーザーの採用ではない） | 未採用 |
| U-3 | B-2の実装担当 | Sonnet 5.5・high（作成依頼の既定。仕様を固定した純粋な投影・計画の実装）。U-1でAPI-1を採る場合も同じ | 推奨（主担当レビューce07dbd。ユーザーの採用ではない） | 未採用 |

設計上の留保（ユーザーの判断ではない）：
- S3-Cが、RESOLUTIONのバッチを公開する直前に確認を作り直すか、`check_append_batch`だけでよいか（S3-Cで決める）。
- B-4のCONSUME（D-3）、効果のない復元の扱い（D-5）、破損ファイルの経路（D-6）、照合の条件（D-7）は、上位の未決のまま。B-2はどれも前提にしない。

未確認の外部事実：本番の保存先、実PCでのWindows strict、物理電源断。いずれも確認していない。

## 16. 作業記録

- 開始時に、作成依頼§6の34参照と、作成依頼の資料ブランチ（docs/v2-history-s3b2-design-request-20261030＝fee48e9）の計35参照を、`git ls-remote`の完全SHAで照合し、35件とも一致した（2026-10-30T04:04Z）。同名の新規資料ブランチ（docs/v2-history-s3b2-20261030）はリモートに無かった。
- コード基準adfdf765から新しい資料ブランチ docs/v2-history-s3b2-20261030 を作り、本書と限定実装依頼書の2文書だけを追加した。コード変更、試験実行、試験コード・再現スクリプトの作成、新しい市場計算、PR、Actions、外部送信は0。終了時の照合結果と完全SHAは完了報告に記す（本書はその値を含められない）。
- 作成担当はClaude Opus 5.5、effort high（セッション情報で確認）。モデル別の利用量は未計測。
- 第2版（文書補正依頼ce07dbdに従う）：開始時に、依頼§8の35参照、初版の資料ブランチ（docs/v2-history-s3b2-20261030＝6286113）、レビューの資料ブランチ（docs/v2-history-s3b2-review-20261030＝ce07dbd）の計37参照を完全SHAで照合し、37件とも一致した（2026-10-30T05:00Z）。初版6286113から新しい資料ブランチ docs/v2-history-s3b2-revision-20261030 を作り、既存2文書だけを補正した。初版の資料ブランチ・レビューの資料ブランチ・コード・試験は変更していない。コード変更・試験実行・再現コード・市場計算・PR・Actions・外部送信は0。作成担当はClaude Opus 5.5、effort high（セッション情報で確認）。終了時の照合と完全SHAは完了報告に記す。

## 17. 第2版の改訂表

| ID | 区分 | 指摘 | 本書の対応 | 依頼書の対応 |
|---|---|---|---|---|
| N-01 | 通常 | §12.4の3で成功させる新しいACKのq4が、例RのRESTORE#1（#7）で使用済み。§6.5ではconflictになる | 成功例を未使用のq7に変更。q4（RESTOREのID）とq2（DROPされた解決依頼）を同じコマンドで出すとconflictになる対照を追加。#4・#8を指す拒否は維持。fixtureとID検査は変えない | B2-10・B2-13に対応を明記 |
| P-01 | 提案 | MIGRATEDのrequest_hashが一致し得る | §6.5の理由を「一致し得ても、名前空間をまたぐ再提出をB-2では保証・受理しない」に修正。常にconflictとする方針は維持 | B2-13に、hashが一致する場合もconflictとする受入を追記 |
| P-02 | 提案 | from_dictと意味検査の段階が§12.8の2で曖昧 | §12.8の2を、読込口で拒否する場合（深さ・数値の限界）と、読込みは通り確認／check_append_batchで拒否する場合（bool・floatの整数欄）に分けた | B2-16に段階の区別を追記 |
| P-03 | 提案 | 候補での再確認で比べるhead／digestが曖昧 | §6.7の手順3を枝A（元の履歴）・枝B（候補の履歴）に分け、それぞれで比べるdigest・先頭を明記。枝Bの期待basisで変える4項目を列挙。再確認NO_CHANGEは維持 | B2-14に枝A・枝Bの受入を追記 |

上位形式、API-1の範囲、R-a、受入ID B2-01〜B2-17、コード基準adfdf765、既存回帰の不変は変えていない。U-1〜U-3は未採用のまま（§15の「主担当の判断」欄にだけ、レビューの推奨を記入した）。新しい採否や後工程は追加していない。
