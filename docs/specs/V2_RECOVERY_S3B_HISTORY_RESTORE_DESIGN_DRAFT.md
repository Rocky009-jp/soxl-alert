# V2 S3-B 監査履歴・明示移行・復元・再初期化 設計案

作成：2026-10-29（日本時間）、初版。状態：**設計案・レビュー待ち。限定実装は未承認・未着手。**
本書を保存したこと、レビューで問題なしとされたことを、S3-B実装・新保存形式の採用・S3-C・本番接続の承認に置き換えない。作成担当はClaude Opus 5.5、effort high（セッション情報で configured_model `claude-opus-5-5[1m]`、last_served_model `claude-opus-5-5`、effort_level `high` を確認）。

## 0. 要約

- **新形式は schema_version=2 の単一履歴**（以下「v2履歴」）。S1と同じヘッダー6項目のまま版だけを2にし、記録種別を7種（GENESIS、APPLY、ACK、DECLARE_MISSING、RESTART_UNKNOWN、RECOVERY_RESTORE、SCHEMA_MIGRATION）に広げる。後続のB-5で8種目のRECOVERY_PREFIX_ADOPTIONを足す。GENESIS／APPLYのキーはS1と完全に同じ。S1／S2の検査器はv2をunsupported_schemaで拒否し、v2の検査器はv1を受け付けない。旧検査器は緩めない。
- **監査鎖と有効親を分ける**。全記録は0基点の連続seqと、直前の物理記録へのhash（監査鎖）を持つ。現在状態を決めるのは有効親（parent_seq）をたどる鎖だけである。有効親が直前でないのはRECOVERY_RESTOREだけで、その記録だけが監査用のprev_hashを別に持つ。
- **検査は「鎖ビュー」ごとの線形検査**。最終の有効鎖と、各RECOVERY_RESTOREの直前時点の有効鎖を、それぞれ一本の線形履歴として検査する。APPLYはGENESIS／RESTART_UNKNOWNで区切った区間ごとにS1形式へ射影し、**変更しないS1 validate_snapshot**で再計算する。戦略式・遷移は複製しない。
- **明示移行**では、S1の各イベントの直後に、そのイベントを作成時先頭とするS3-A記録を挟み、最後にSCHEMA_MIGRATION記録を置く。この記録が旧seq/hashとの対応表と、元Snapshot・元ResolutionSetのdigestを持つ。検査時にはv2から元のS1 SnapshotとS3-A ResolutionSetを再構成し、digestの一致を確かめたうえで、**変更しないS1・S3-Aの検査器**に通す。
- **復元**は、復元点・退避一覧・処分の一覧（REAPPLY／REPLAY／DROP／RETIRE）を持つ1件の記録と、その直後に続く再計算・再生の記録群を、1バッチとして表す。バッチが途中で切れた履歴は検査で不正とする。退避済みのAPPLYと同じDは、保存済みのdecisionと市場入力を変えずに再適用（REAPPLY）するしかない。これにより、復元をCORRECTIONや版の選択の抜け道にしない。
- **最初の限定実装単位はB-1**とする。v2履歴の値・厳格codec・全7種の検査器（復元バッチ・再初期化を含む）と、S1＋S3-Aからの明示移行の計画・確認までを、メモリ上の純粋関数で作る。台帳投影、日次処理、復元・再初期化の計画作成、破損診断、実ファイル公開は含めない。依頼書は [V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md](../tasks/V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md)。

## 1. 固定版・根拠・用語

| 用途 | 固定版 |
|---|---|
| コード基準 | e68d702de7fa80f141e14b63cf88082c15493994（fix/v2-recovery-resolution-s3a-review-20261029）。コード・試験は 885f545c9b0a0da3f210ba601fd8b7dbf4f08848 と同一で、差は結果文書1本だけ |
| 作成依頼・S3-A受領 | [abb2e73](https://github.com/Rocky009-jp/soxl-alert/blob/abb2e73a4980c635f0f471d1819b6b1734661fa1/docs/tasks/V2_RECOVERY_S3B_DESIGN_PREPARATION_REQUEST.md)、[受領確認](https://github.com/Rocky009-jp/soxl-alert/blob/abb2e73a4980c635f0f471d1819b6b1734661fa1/docs/reviews/V2_RECOVERY_S3A_FIX_RECEIPT_20261029.md) |
| S3分割・境界 第3版 | [2d504de](https://github.com/Rocky009-jp/soxl-alert/blob/2d504de7cbf4628a3760d48f70fd0228dce6a61c/docs/specs/V2_RECOVERY_S3_DESIGN_DRAFT.md)、§9・§10 |
| S3-A採用記録 | d215193065ebf110e6a77f22edf208b390138285 |
| 上位設計 第4版 | [e3e9094](https://github.com/Rocky009-jp/soxl-alert/blob/e3e90947a718cca877b543739ca60539207ca7a7/docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md)、§2.2・§2.4・§2.6〜2.8・§4.3（R-2〜R-4）・§6.9 |
| S1／S2の固定契約 | 425df80（S1第4版）、73cec62（S2資料）。照合は実際のコード（上記基準）を優先した |

読んだコード：v2_persistence（codec／events／recompute／runner／plan／store／local/store）、v2_recovery（全モジュール）、v2_core（state／transition／engine／observations）、S3-A結果文書§5〜§13。CLAUDE.md、MODEL_POLICY、STATUS、ROADMAPは該当箇所を確認した。STATUSは2026-10-27時点の古い承認待ちの記述であり、今回の文書作成指示を取り消すものではない。また、売却境界にある「S3」と、本書の保存・復旧段階S3は別の分類である。

用語：

- **物理seq**：v2履歴のevents配列の位置（0基点）。
- **監査鎖**：seq=iの記録が、seq=i−1の記録のevent_hashを持つ鎖。退避した記録も含む全記録を結ぶ。
- **有効親**：parent_seq／parent_hash。現在状態を作る鎖をたどる。
- **鎖ビュー**：ある記録から有効親を GENESIS までたどった列を、古い順に並べたもの。
- **区間**：鎖ビューをGENESIS／RESTART_UNKNOWNで区切った部分。区間の境界は GENESIS.start_after または RESTART_UNKNOWN.resume_after。
- **制御記録**：ACK、DECLARE_MISSING、RESTART_UNKNOWN、RECOVERY_RESTORE、SCHEMA_MIGRATION。このうちRESTART_UNKNOWNだけが市場状態を初期化する。

## 2. S3-Bの範囲・分割・完了の意味

S3第3版§9の5点（形式、参照写像、複数回復元、制御記録の再生、破損証拠）を、次の単位に分ける。順番に別依頼・別採否とする。

| 単位 | 内容 | 状態 |
|---|---|---|
| **B-1** | v2履歴の値・厳格codec・全7種の検査器（監査鎖、有効親、退避、復元バッチ、再初期化、S1射影、移行記録の逆検証）。S1＋S3-Aからの明示移行の計画・確認。すべてメモリ上 | **今回、限定依頼書を作成。未承認** |
| B-2 | v2での台帳投影（S3-Aの除外・補完・版選択・最終検査を再利用）と日次処理（S1 prepare_dayへの委譲）。v2で新規に作るACK／DECLARE_MISSINGの計画・確認。公開用バッチ値 | 設計境界のみ（§10） |
| B-3 | RESTART_UNKNOWNの計画・確認（sessionsとcheck_dの検査を含む） | 設計境界のみ（§7） |
| B-4 | RECOVERY_RESTOREの計画・確認（台帳・series・sessionsの再検査、差の表示）。CONSUMEを採用する場合はここ | 設計境界のみ（§8） |
| B-5 | 破損診断と、prefix採用候補の作成（RECOVERY_PREFIX_ADOPTION記録） | 設計境界のみ（§11） |
| S3-C | 保守ゲート・明示解錠・元バイトの退避・v2用の新しいファイルアダプタによる公開・移行の実行・Windows strict | 対象外。S3第3版§10の未決のまま |

B-1が完了しても、ファイル上の正本はv1のままであり、復旧・移行・耐久性は何も達成していない。B-1が示すのは「v2という形式で、S1の履歴とS3-Aの解決記録を情報の欠落なく表せ、復元・再初期化を含む履歴の正しさを機械的に判定できる」ことだけである。

## 3. 新形式 schema_version=2

### 3.1 ヘッダーと互換

ヘッダーのキーはS1と同じ6項目に固定する：`schema_version`（整数2）、`core_sha`、`head_seq`、`head_hash`、`current_state`、`events`。

- `core_sha` はS1の`CORE_SHA`（b616b4ec7169420e199ec7e247dd375b3603a013）と同じ値とする。v2_coreは変わっていないためである。コアを変える場合は、新しい値と、その版に合わせた明示移行を別に設計する。後方互換は推測しない。
- `head_seq`／`head_hash` は**物理的に最後の記録**を指す。最後の記録は常に有効鎖の先頭である（§4.2）。そのため、有効先頭を別の項目として持たない。
- `current_state` は最後の記録の`state_after`と完全一致し、`MarketState.from_dict`の正規形に一致すること。
- schema_version≠2 は `unsupported_schema`。v1を検査器で自動変換しない（明示移行だけ）。未知の種別は `unsupported_event`。boolを整数として受け取らない。未知キー・重複JSONキー・非有限数・深さ40超は拒否する。正規化は既存`canonical_json`と同じ。
- 既存S1の`validate_snapshot`は、v2をschema_versionの段階で`unsupported_schema`として拒否する（既存の挙動で、変更しない）。したがって既存S2の`LocalFileStore.read`／`commit`／`initialize`は、v2のsnapshot.jsonを読めず、上書きもできない。これは旧ライターが残っていた場合の防護として有用だが、排他の証明ではない（§9.3）。

### 3.2 記録種別と共通規則

| 種別 | 市場状態 | state_after | 有効親 | 区間 |
|---|---|---|---|---|
| GENESIS | 初期化 | 初期状態 | なし（seq=0のみ） | 区間を開始（start_after） |
| APPLY | Dを消費 | 遷移後の状態 | seq−1 | — |
| ACK | 変えない | 親と同じ | seq−1 | — |
| DECLARE_MISSING | 変えない | 親と同じ | seq−1 | — |
| RESTART_UNKNOWN | 初期化 | 初期状態 | seq−1 | 新しい区間を開始（resume_after） |
| RECOVERY_RESTORE | 復元点の状態へ戻す | 復元点の記録と同じ | **復元点** | 復元点の区間を引き継ぐ |
| SCHEMA_MIGRATION | 変えない | 親と同じ | seq−1 | — |
| RECOVERY_PREFIX_ADOPTION（B-5） | 変えない | 親と同じ | seq−1 | — |

共通：`kind`、`seq`、`parent_seq`、`parent_hash`、`event_hash`。event_hashは、その記録からevent_hashだけを除いた正規化JSONのSHA-256（既存`compute_event_hash`と同じ）。全記録が`state_after`を持つ。

監査鎖：seq=i（i≥1）の記録の「監査上の前」は、RECOVERY_RESTOREなら`prev_hash`、それ以外なら`parent_hash`。これがseq=i−1のevent_hashと一致すること。RECOVERY_RESTORE以外では`parent_seq == seq−1`。

### 3.3 種別ごとのキー

**GENESIS・APPLY**：S1のGENESIS_KEYS・APPLY_KEYSと完全に同じ。意味も同じだが、APPLYの`parent_seq`／`parent_hash`は「直前の物理記録」（=有効親）を指す。直前が制御記録なら、その制御記録を指す。APPLYの内容（d、confirmed_inputs、input_hash、skipped_sessions、transition_result、state_after）の正しさは§4.3のS1射影で検査する。

**ACK・DECLARE_MISSING（共通キー23項目）**：
`kind` `seq` `parent_seq` `parent_hash` `variant` `d` `record_fingerprints` `applied_ref` `missing_ref` `session_context` `frontier_before` `request_id` `request_hash` `request_basis` `command_index` `command_count` `reason_code` `requested_at` `ledger_digest` `origin` `replay_of` `state_after` `event_hash`

S3-Aの記録キーから `resolution_seq` `parent_resolution_hash` `resolution_hash` `source_head_seq` `source_head_hash` を除いた。位置と監査鎖で表せるためである。代わりに `seq` `parent_seq` `parent_hash` `event_hash` `origin` `replay_of` を足した。

- `origin`：v2で新たに作った記録はnull。移行した記録は `{resolution_seq, resolution_hash, source_head_seq, source_head_hash}`（S3-Aの元の値。source_headはS1の旧seq/hash）。
- `replay_of`：復元で再生した記録だけ `{seq, event_hash}`（退避した元記録）。それ以外はnull。
- `applied_ref` `{seq, event_hash, fingerprint}`、`missing_ref` `{kind, seq, event_hash}`（kindは"APPLY"／"DECLARE_MISSING"）。どちらも**v2の物理seq**を指す（§3.5）。

**RESTART_UNKNOWN**：
`kind` `seq` `parent_seq` `parent_hash` `resume_after` `boundary_session` `floor` `request_id` `request_hash` `request_basis` `reason_code` `requested_at` `replay_of` `state_after` `event_hash`

- `boundary_session` はS1の`session_dict`形式（date／open_at／close_at／confirmed）。date==resume_after、confirmed=true。
- `floor` は `{last_apply_d, last_declared_d, prev_boundary}`。作成時の鎖ビューから計算した値と完全一致すること（§7）。
- `request_basis` は `{request_id, resume_after, check_d, reason_code, requested_at}`、reason_codeは"RESTART_UNKNOWN"。

**RECOVERY_RESTORE**：
`kind` `seq` `prev_hash` `parent_seq` `parent_hash` `superseded_seqs` `replay` `request_id` `request_hash` `request_basis` `reason_code` `requested_at` `ledger_digest` `state_after` `event_hash`

- `parent_seq`／`parent_hash` は復元点。`prev_hash` はseq−1のevent_hash。
- `request_basis` は `{request_id, restore_point:{seq, event_hash}, ops, check_d, reason_code, requested_at}`。reason_codeは"RESTORE_VERIFIED_RECORD"。`ops` は利用者が指定する処分の列で、`{op, from_seq}`（opはREAPPLY／REPLAY／DROP／RETIRE）の形をとる。CONSUMEを採用する場合（§8.7）だけ `{op:"CONSUME", d}` も入る。
- `replay` は計算結果の列 `{op, from_seq, d, seq, same_as_superseded}`。opsと同じ順・同じ長さとする。`seq` は作られた記録の物理seqで、DROP／RETIREではnull。`d` はREAPPLY／CONSUMEのD、それ以外はnull。`same_as_superseded` はREAPPLYだけがboolを持ち、それ以外はnull。

**SCHEMA_MIGRATION**：
`kind` `seq` `parent_seq` `parent_hash` `source` `source_resolutions` `event_map` `resolution_map` `request_id` `request_hash` `request_basis` `reason_code` `requested_at` `ledger_digest` `state_after` `event_hash`

- `source`：`{schema_version:1, core_sha, head_seq, head_hash, snapshot_digest}`。snapshot_digestは`sha256(encode_snapshot(v1))`。
- `source_resolutions`：`{schema:"soxl-v2-resolution-set/1", head_resolution_seq, head_resolution_hash, digest}`。解決記録が無い場合は空のSetのdigest（null値にはしない）。
- `event_map`：`[{v1_seq, v1_event_hash, seq}]`。v1の全イベントについて、v1_seqの昇順に並べる。
- `resolution_map`：`[{resolution_seq, resolution_hash, seq}]`。S3-Aの全記録について並べる。
- `request_basis`：`{request_id, source_snapshot_digest, source_resolutions_digest, check_d, reason_code, requested_at}`。reason_codeは"MIGRATE_SCHEMA_1"。

**RECOVERY_PREFIX_ADOPTION**（B-5、B-1ではunsupported_event）：
`kind` `seq` `parent_seq` `parent_hash` `evidence` `request_id` `request_hash` `request_basis` `reason_code` `requested_at` `state_after` `event_hash`。evidenceは `{raw_sha256, raw_size, claimed_schema_version, claimed_head_seq, claimed_head_hash, discarded_from_seq}`（解析できない値はnull）。

### 3.4 hashとdigestの計算

| 名前 | 計算 |
|---|---|
| event_hash | 記録からevent_hashを除いた正規化JSONのSHA-256（`compute_event_hash`） |
| request_hash | `request_basis`から`requested_at`だけを除いた正規化JSONのSHA-256。ACK／DECLAREではS3-Aの`request_hash_of`と同じ値になる。移行した記録はS3-Aの値をそのまま持つ |
| snapshot_digest（v1） | `sha256(encode_snapshot(snapshot))`（S3-Aの計画と同じ） |
| resolutions digest | `ResolutionSet.digest`（正規化テキストのSHA-256） |
| history digest | v2履歴の正規化テキスト全体のSHA-256 |
| ledger_digest | S3-Aの`ledger_digest`（6列・順序なし・個数を保持） |
| sessions_digest | S3-Aの`sessions_digest`。**計画の確認専用**で、記録には入れない |
| plan_hash | 計画のbasis全体の正規化JSONのSHA-256。記録はplan_hashを持たない（循環させない） |

hashは改ざん検知のための整合性値であり、署名・真正性・台帳の完全性を証明しない（S1と同じ）。

### 3.5 参照の名前空間（v2では一本化）

S3-Aでは、`applied_ref`とAPPLY型の`missing_ref`がS1のevent seqを、宣言型の`missing_ref`がresolution_seqを指していた。v2では**どちらも物理seq＋event_hash**に一本化する。参照先は、その記録の鎖ビューにおける**祖先**でなければならない（後で作った記録を過去の根拠にしない）。

`request_basis.commands[command_index]` と記録上の参照は、次のどれか一つの関係にある。

| 記録 | 関係 |
|---|---|
| v2で新たに作った記録（origin=null、replay_of=null） | commandsの参照とv2の参照が完全一致 |
| 移行した記録（origin≠null） | request_basisはS3-Aの元のまま（S3-Aの名前空間）。記録上の参照は、MIGRATIONのevent_map／resolution_mapで写したもの |
| 復元で再生した記録（replay_of≠null） | request系の項目は元記録のまま。記録上の参照は、元記録の**記録上の参照**を、そのRECOVERY_RESTOREの写像（§8.5）で写したもの |

## 4. 監査鎖と有効履歴

### 4.1 監査鎖

seqは0から欠けずに増え、使い回さない。全記録の監査上の前（§3.2）がseq−1のevent_hashと一致する。退避した記録を削除・変更・並べ替えれば、監査鎖かevent_hashで検出される。先頭（head_seq／head_hash）は最後の記録と一致する。

### 4.2 有効親・有効履歴・退避

- **有効履歴**：先頭から有効親をGENESISまでたどった列。現在状態・Dごとの一意性・開始境界・通知の判断は、この列だけで決まる。
- **先頭は常に有効**：新しい記録は常に末尾に足し、その有効親は直前の記録か（通常）、直前時点の有効鎖上の復元点（RECOVERY_RESTORE）である。したがって最後の物理記録は常に有効鎖の先頭になる。
- **退避**：有効履歴に含まれない記録。退避した記録はどれも、ちょうど一つのRECOVERY_RESTOREの`superseded_seqs`に入っていること。検査では、全RECOVERY_RESTOREの`superseded_seqs`の和集合が、有効でない記録の集合と一致することを確かめる（互いに素であることも含む）。一度退避した記録は、以後どの鎖からも到達できない。後の記録の有効親は、直前の記録か、その時点で有効な復元点に限られるためである。

### 4.3 鎖ビューとS1射影

検査する鎖ビューは、**最終の有効鎖**と、**各RECOVERY_RESTORE(seq=k)の直前時点の有効鎖**（seq=k−1から有効親をたどった列）である。どの記録も、少なくとも一つのビューに含まれる。退避した記録は、最初にそれを退避したRECOVERY_RESTOREの直前ビューに入り、それ以外は最終ビューに入るためである。各ビューは一本の線形履歴として検査する。ビューの中では、どの記録の有効親も直前の要素である。

- **RECOVERY_RESTOREはビューの中では透過**：ビューの中の直前要素は復元点であり、state_afterも同じなので、状態を変えない制御記録として扱う。物理的な「飛び」は§4.2と§8で検査する。
- **区間**：ビューをGENESIS／RESTART_UNKNOWNで区切る。各区間について、`make_genesis_event(境界日, boundary_session)`と区間内のAPPLYを、既存の`make_apply_event`でseq・親hashだけを付け直して並べ、`snapshot_of`→**既存`validate_snapshot`**に通す。付け直したイベントの内容項目（d、confirmed_inputs、input_hash、skipped_sessions、transition_result、state_after）が、v2の記録と完全一致することも確かめる。これにより、各APPLYの再計算（apply_transition）、IB-04、セッション文脈の連続、skipped_sessions、区間内でD重複なし・昇順を、S1の検査器そのものが確かめる。新しい検査器は戦略式・遷移・閾値を持たない。
- **IB-04の意味の維持**：射影上のAPPLYの親は、直前のAPPLYか区間の開始である。その間にある制御記録は状態を変えないので、比較の相手は上位設計§2.4のとおり「現在状態を作ったAPPLYの親のstate_after」になる。APPLYの後にACKを何件足しても、比較の相手は変わらない。
- **I-15**：ACK／DECLARE_MISSING／SCHEMA_MIGRATIONのstate_afterはビュー上の親と同じ。RESTART_UNKNOWNは初期状態。RECOVERY_RESTOREは復元点と同じ。
- **区間をまたぐ規則**：RESTART_UNKNOWNのfloor（§7）により、次の区間の境界は前の区間の全APPLY日・宣言日以上になる。したがって、ビュー全体でもAPPLY・DECLARE_MISSINGのDは重複しない。射影は区間ごとだが、この性質を別に確かめる（`d_unique`）。

計算量：ビュー数×区間内APPLY数。U-10の判断（件数が少ないうちは毎回全件）に従い、B-1では性能を受入条件にしない。同じ記録を複数のビューで検査してよいが、検査結果を呼出しの間で使い回さない。

### 4.4 現在状態・開始境界

- 現在状態は先頭のstate_after（=current_state）。
- **開始境界**（上位§2.8）：current_state.as_of_dがあればその日。無ければ、最終ビューを先頭からさかのぼって最初に見つかるGENESIS／RESTART_UNKNOWNの境界日。ACK・DECLARE_MISSING・SCHEMA_MIGRATION・RECOVERY_RESTOREは読み飛ばす（ビューの中では透過）。開始するセッションは、この日の次のセッション。
- 宣言済みのDは開始境界を動かさない。そのDを日次処理すると、S3-Aと同じくdecision無しのNO_COMMITになる（B-2）。

### 4.5 検査順と結果

`validate_history(history)` の検査順を固定する。
1. 型・ヘッダー・schema_version・core_sha・種別（B-1の7種）・各種別のキー・JSON形式。
2. 監査鎖（seq、監査上の前、event_hash、head）。
3. 有効親の形（非RESTOREは`seq−1`、RESTOREは`seq−1`未満で、その時点の有効鎖上）。
4. RECOVERY_RESTOREごとの退避一覧の完全一致・復元点の条件・復元バッチの対応（§8）。
5. 最終の有効鎖の導出と、退避の和集合の一致。
6. 鎖ビューごとの線形検査（S1射影、制御記録・再初期化・移行記録の規則、I-15、request_idの一意）。
7. SCHEMA_MIGRATIONの逆検証（§5.5）。
8. current_stateと先頭の一致。

戻り値 `HistoryCheck`（不変）は、head_seq、head_hash、record_count、effective_seqs、superseded_seqs、current_boundary `{kind, seq, after}`、latest_apply_d（有効鎖全体）、processing_after（§4.4の日付）、declared_days_in_segment、migrated（bool）、history_digest、state_digestを持つ。台帳の行・F&G値・自由文は持たない。

## 5. 明示移行（schema 1＋S3-A → schema 2）

### 5.1 入力と再検査

入力は、v1 Snapshot、S3-A ResolutionSet（無ければ`empty_resolutions()`）、sessions、raw_observations、check_d、request_id、requested_at（注入したaware日時）。S3-Aは永続化した証拠ではないので、次を省略しない。

1. `validate_snapshot(v1)`（既存）。
2. `validate_resolutions(v1, set)`（既存S3-A）。
3. `resolve_observations(v1, set, sessions, raw, check_d)`（既存S3-A）。現在の台帳・sessionsで、持ち込む解決記録の除外・補完・version_selection・最終検査が通ること。通らなければ、そのエラーのまま止め、候補を作らない。
4. request_idが、Set内のどのrequest_idとも一致しないこと（`migration_request_conflict`）。

解決記録の一部だけを移すことはしない。Setが別に進んでいれば、新しいSetで計画し直す。

### 5.2 変換規則（並べ方）

v1のイベントs=0..nを順に出力し、各イベントの直後に、`source_head_seq == s` のS3-A記録をresolution_seqの順に出力する。最後にSCHEMA_MIGRATION記録を置く。S3-Aのsource_head_seqは減少しないので、これは作成順を再現する。各解決記録は「その時点のS1先頭の直後」に作られたものだからである。

- v1のGENESIS／APPLYは、seq・parent_seq・parent_hash・event_hashだけを付け直し、内容項目は1バイトも変えない。それより前に挟んだ記録が一つも無いイベント（GENESISと、例ではv1 seq1）は、v1と同じevent_hashになる。それ以外は、seqと親hashが変わるのでevent_hashも変わり、対応はevent_mapで示す。
- 解決記録は、S3-Aのキーから§3.3の除外・追加を行う。fingerprints、variant、d、session_context、frontier_before、request_id、request_hash、request_basis、command_index、command_count、reason_code、requested_at、ledger_digest、state_afterは元のまま写す。applied_ref／missing_refはv2の名前空間へ写す（§5.4）。originに元の4値を入れ、replay_ofはnullとする。
- SCHEMA_MIGRATIONのstate_afterはv1のcurrent_stateと同じ。移行で市場状態は変わらない。

### 5.3 移行記録の位置の規則

- SCHEMA_MIGRATIONは高々1件。ある場合、それより前の記録はGENESIS／APPLY／ACK／DECLARE_MISSINGだけで、その前のACK／DECLARE_MISSINGはすべてoriginを持つ。それより後の記録はoriginを持たない。無い場合、どの記録もoriginを持たない（v2で新規に作った履歴。§7のmake_history_genesisによる）。
- 移行した解決記録のorigin.source_head_seqは、それより前で最も近いv1イベント（GENESIS／APPLY）のv1_seqと一致する。source_head_hashは、そのv1_event_hashと一致する。
- **復元点はSCHEMA_MIGRATION以後の記録に限る**（本書の推奨。§14のD-2）。移行した範囲はv1の原本を表すので、退避・再生の対象にしない。これにより、originを持つ記録の再生は起きない。

### 5.4 写像規則

| S3-A（元） | v2 |
|---|---|
| applied_ref `{seq:S1 seq, event_hash:S1 hash, fingerprint}` | `{seq:event_mapで写したv2 seq, event_hash:そのv2記録のhash, fingerprint:同じ}` |
| missing_ref `{kind:"APPLY", seq, event_hash}` | `{kind:"APPLY", seq:写したv2 seq, event_hash:v2 hash}` |
| missing_ref `{kind:"DECLARE_MISSING", resolution_seq, resolution_hash}` | `{kind:"DECLARE_MISSING", seq:resolution_mapで写したv2 seq, event_hash:v2 hash}` |
| record_fingerprints | 変えない（コアObservation.fingerprint()のまま） |
| request_id／request_hash／request_basis | 変えない（request_basisの参照はS3-Aの名前空間のまま） |
| resolution_seq／resolution_hash／source_head | originへ保存し、位置と監査鎖に置き換える |

### 5.5 検証：既存の検査器へ戻して確かめる

SCHEMA_MIGRATIONがある履歴では、検査器が次を行う（§4.5の7）。

1. 移行範囲のGENESIS／APPLYを順に取り出し、v1 seq=0..nとして`make_apply_event(v1_seq, v1の前のhash, …)`で付け直す。各hashがevent_mapのv1_event_hashと一致し、event_mapのseqがv2の位置と一致すること。
2. `snapshot_of`で再構成したv1 Snapshotを、既存`validate_snapshot`に通す。`sha256(encode_snapshot)`がsource.snapshot_digestと、head_seq／head_hashがsourceと一致すること。
3. 移行範囲の解決記録を順に取り出し、originと逆写像でS3-Aの記録を再構成する（parent_resolution_hashは直前に再構成した記録のhash、参照はS3-Aの名前空間へ戻す）。既存`record_hash_of`の値がorigin.resolution_hashと一致すること。再構成したSetのdigestがsource_resolutions.digestと一致し、既存`validate_resolutions(再構成したv1, 再構成したSet)`に通ること。

これにより、v2履歴だけから元のv1 SnapshotとS3-A Setをバイト単位（正規形）で取り戻せること、つまり移行で情報が欠けていないことを、旧検査器を緩めずに確かめる。元の**ファイルのバイト列**（S2が書いたsnapshot.jsonそのもの）の保全と、その生digestの記録はS3-Cの責任とする。正規化テキストのdigestと生バイトのdigestを混同しない。

### 5.6 計画と確認

`prepare_migration_plan(snapshot_v1, resolutions, sessions, raw_observations, check_d, request_id, requested_at)` は、§5.1の再検査→変換→`validate_history(候補)`の順に行い、READYの不変計画を返す。

basisは次の項目：operation（"soxl-v2-history-migration-plan/1"）、status、source_snapshot_digest、source_head_seq、source_head_hash、source_resolutions_digest、request_id、request_hash、requested_at、check_d、ledger_digest、sessions_digest、effective_digest（S3-Aの投影結果）、candidate_history（dict）、candidate_digest、expected_state_digest。

`confirm_migration_plan(plan, confirmed_plan_hash, snapshot_v1, resolutions, sessions, raw_observations)` は、計画の形とhashを先に検査し、入力を再検査し、全digestが一致することを確かめ、候補を作り直して完全一致を確かめる。結果は`CONFIRMED_IN_MEMORY`、committed=False、候補Historyの写し。入力が一つでも変われば`migration_plan_stale`、計画の改変・確認hashの違いは`migration_plan_mismatch`とする。表示は許可リスト方式で、件数・seq・hash・日付だけを出す。

計画を確認しても、v1ファイルは変わらず、v2は保存されていない。実際の置き換え（v1→v2）はS3-Cの公開値と、新しいアダプタの責任とする（§9）。

### 5.7 例M（移行）

日付D0〜D4は連続した確定セッション。

| v1 | S3-A |
|---|---|
| 0 GENESIS(start_after=D0) | r1：source_head=1、ACK/ADDED(D1, applied_ref={1,h1}) 依頼q1 |
| 1 APPLY D1 | r2：source_head=2、DECLARE_MISSING(D3) 依頼q2（frontier=D2） |
| 2 APPLY D2 | r3：source_head=3、ACK/LATE(D3, missing_ref={DECLARE_MISSING, r2}) 依頼q3 |
| 3 APPLY D4（skipped=[D3]） | |

v2：0 GENESIS ／ 1 APPLY D1（hash＝v1と同じ） ／ 2 ACK r1 ／ 3 APPLY D2（親=2、hashは新しい） ／ 4 DECLARE r2 ／ 5 APPLY D4 ／ 6 ACK r3 ／ 7 SCHEMA_MIGRATION。
event_map：0→0、1→1、2→3、3→5。resolution_map：1→2、2→4、3→6。
r3の記録上のmissing_refは `{kind:"DECLARE_MISSING", seq:4, event_hash:h4}`。request_basisの中は元の `{kind:"DECLARE_MISSING", resolution_seq:2, …}` のまま。

## 6. ACK・DECLARE_MISSINGのv2規則

S3-Aのvalidate（構造・参照・作成時の状態）の規則を、v2の位置と名前空間に置き換える。台帳に依存する証拠の検査（今回の台帳に元行があるか等）は、S3-Aと同じく計画作成時だけに行い（B-2）、履歴の検査では行わない。

| 規則 | v2での内容 |
|---|---|
| 作成時のprefix | S3-Aのsource_headに当たるのは、ビュー上の親までの鎖。後で正常なAPPLYを足しても失効しない |
| applied_ref | ビュー上の祖先のAPPLY、hash一致、fingerprint＝そのAPPLYの固定指紋、記録のd＝そのAPPLYのd |
| missing_ref | 祖先のAPPLYでskipped_sessionsにdを含むもの、または祖先のDECLARE_MISSINGで同じd |
| LATE | ビュー内にdのAPPLYが無い。applied_ref=null。fingerprintsは空でない |
| ROW_REMOVED | fingerprintsは空 |
| exclude_applied | fingerprintsに、ビュー内のどのAPPLYの固定指紋も含まない |
| check_d | 区間の境界より後で、親までの鎖の最新APPLY日以上。記録のd ≤ check_d。作成時の値として検査し、今のcheck_dを遡って当てはめない |
| DECLARE_MISSING | ビュー内にdのAPPLYが無い。frontier＝現在の区間の中で、境界日・APPLY日・宣言日のうち最も遅い日。d＝frontierの次。session_context＝[frontier, d, next(d)]の3件で、ctx[0]はfrontierの出どころ（境界ならboundary_session、APPLYならそのcontext[−2]、宣言ならそのctx[1]）と一致し、ctx[0]とctx[1]はconfirmed |
| バッチ | 同じrequest_idの記録はビュー上で連続した1組で、command_indexが0..count−1。request系の項目は全件同じ。記録のkind／variant／d／fingerprints／参照は、commands[index]と§3.5の関係にある |
| request_hash | §3.4。reason_codeはkindに対応（混合バッチのbasisではRESOLUTION_BATCHも可） |
| state_after | ビュー上の親と同じ |
| request_idの一意 | 1つのビューの中で、1つのrequest_idは1つのバッチだけ。再生した記録は元記録と同じrequest_idを持つが、元記録とは同じビューに並ばない |

有効なdecision1件の欠測宣言を拒否する方針（採用済みN-04）、version_selectionの禁止、ADDEDの証拠の範囲は、v2での新規作成（B-2）でもS3-Aと同じ規則を使う。B-1はこれらを変えない。

## 7. RESTART_UNKNOWN（再初期化）

### 7.1 floorと境界

floorは作成時の鎖ビュー（親まで）から計算する。
- last_apply_d：ビュー全体（全区間）の最新APPLY日。無ければnull。
- last_declared_d：ビュー全体の最新DECLARE_MISSING日。無ければnull。
- prev_boundary：現在の区間の境界日（GENESIS.start_afterか、直前のRESTART_UNKNOWN.resume_after）。

条件：
- resume_after ≥ 非nullのfloorの最大値（上位RT-09。下回れば`restart_floor`）。
- resume_after ≤ request_basis.check_d。
- 親の状態が初期状態で、かつresume_after＝prev_boundaryなら`restart_noop`。
- state_afterは初期状態。過去の記録は削除・退避せず、有効履歴に残る。

再初期化の後は、resume_afterを境界とする新しい区間になる。最初のAPPLYでは、コアは欠測（gap）を報告しない（基点のas_of_dが無いため）。一方、skipped_sessionsは境界の次からDの前までとなり、S1射影がこれを確かめる。ACK／DECLARE_MISSINGを何件足しても、境界は動かない。

### 7.2 日次・宣言・後発行との関係（B-2・B-3で実装、B-1は記録の検査だけ）

- **同日再実行**：再初期化の前なら、最新APPLY日DはS1と同じくALREADY_APPLIED。再初期化の後は、D ≤ resume_afterの日を処理しない（`target_not_after_boundary`）。前の区間の最終APPLY日を処理し直す経路は無い。
- **欠測**：新区間でdecisionの無い日はNO_COMMITとなる。次のAPPLYのskipped_sessionsにその日が入る。
- **後発行**：skipped_sessionsの日、または宣言日に後からdecisionが現れたら`late_observation`で止める。前の区間のAPPLYが記録したskipped_sessionsも引き続き対象。境界以前で、どのAPPLYにも宣言にも属さない日のdecisionは処理しない。ただし解析と衝突の検査は受ける（上位§2.8）。
- **宣言**：新区間での最初の宣言は、境界の次のセッションだけが対象。

### 7.3 例U（再初期化の後の最初の処理）

履歴：0 GENESIS(D0) ／ 1 APPLY D1 ／ 2 APPLY D2 ／ 3 RESTART_UNKNOWN(resume_after=D3, floor={D2, null, D0})。D3は意図して処理しない。

| 操作 | 期待 |
|---|---|
| D2・D3の処理 | `target_not_after_boundary`（状態不変） |
| D4のdecisionあり（F&G≥30） | APPLY D4：gap=false、skipped=[]、streak=1、armed=UNKNOWN（コアの値） |
| D4のF&G<25 | armed=FALSE、streak=0 |
| D4のF&G 25以上30未満 | streak=0、armed=UNKNOWN |
| D4がdecision無し、D5があり | D4はNO_COMMIT。APPLY D5のskipped=[D4]、gap=false |
| 上の後でD4のdecisionが現れる | `late_observation`。LATE（missing_ref＝APPLY D5）で確認するまで止める |
| D3のdecisionが後から現れる | 処理しない・LATEにもしない。解析と衝突の検査だけ |
| 4 DECLARE_MISSING(D4)を足す | frontier=D3（境界）。開始境界はD3のまま |
| 再びRESTART_UNKNOWN(resume_after=D2) | `restart_floor`（prev_boundary=D3を下回る） |

上の各値は、合成fixtureでのコアの期待であり、市場の実測ではない。

`make_history_genesis(start_after, sessions)` は、S1の`make_genesis`と同じ検査（start_afterがsessionsにあり、confirmed）でv2の新規履歴を作る。B-1に含める。

## 8. 復元（RECOVERY_RESTORE）

### 8.1 復元点

- seq=kのRECOVERY_RESTOREの復元点Pは、seq=k−1から有効親をたどって到達できること（その時点で有効）。到達できない（既に退避した記録への再接続）は`restore_point_not_effective`。
- P＝k−1は退避が空になるので`restore_noop`。
- PはSCHEMA_MIGRATION以後（§5.3）。前なら`restore_before_migration`。
- Pが複数記録のrequestバッチの途中（command_index＜command_count−1）なら`restore_point_in_batch`。復元バッチで作られた記録（REAPPLYの列など）の途中は、ここでいうrequestバッチではないので、復元点にしてよい。
- state_after＝Pのstate_after。
- request_basis.restore_pointは`{P, Pのevent_hash}`と一致し、request_basis.opsはreplayの`{op, from_seq}`（CONSUMEでは`{op, d}`）と同じ列であること。request_basis.check_dは、直前の有効鎖の区間の境界より後で、その鎖の最新APPLY日以上とする。

### 8.2 退避一覧

`superseded_seqs`は、k−1から有効親をたどってPに着くまでに通った記録（Pを除く）を、seqの昇順に並べたものと**完全一致**すること。鎖の上ではseqが増えていくので、昇順＝鎖の順である。物理seqの単純な区間（P+1..k−1）を使うと、既に退避した記録を巻き込むので不正になる（例R）。過不足や順序違いは`superseded_mismatch`。

### 8.3 処分（ops）とバッチの対応

opsは、退避した各記録について鎖の順に1件ずつ並べる（CONSUMEを除く）。種別ごとに許す処分を固定する。

| 退避した記録 | 許す処分 | 作られる記録 |
|---|---|---|
| APPLY | REAPPLYだけ（消去・選び直し不可） | APPLY 1件 |
| ACK・DECLARE_MISSING | REPLAYかDROP（requestバッチ単位で全件同じ処分） | REPLAYならその種別の記録1件 |
| RESTART_UNKNOWN | REPLAYかDROP | REPLAYならRESTART_UNKNOWN 1件 |
| RECOVERY_RESTORE | RETIRE | なし（以後の鎖の形として監査鎖に残る） |
| SCHEMA_MIGRATION | §5.3により退避されない | — |

RECOVERY_RESTOREの直後には、REAPPLY／REPLAY（／CONSUME）の数だけの記録が、opsの順に**途切れずに**続くこと。他の記録を挟まない。履歴がその途中で終わっていれば`restore_incomplete`とする。これにより、復元の途中状態は検査を通らない（§9）。replayの各項目は、作られた記録のseq、REAPPLYのd、same_as_supersededについて、事実と一致すること。

### 8.4 再適用（REAPPLY）：市場入力と決定を変えない

作られたAPPLYは、元のAPPLY（from_seq）に対して次を満たす。
- dが同じ。
- confirmed_inputsのdecision、row、prev_row、prev_session_dateが完全一致。保存済みのdecisionと市場の判定入力を使い、再計算は既存apply_transitionで行う（S1射影の検査がそれを確かめる）。新しい市場値を自動で採用しない（U-07）。決定を変えないので、CORRECTION（U-03）や版の選択の抜け道にならない。
- session_contextは、両者に共通する日付の要素が一致すること。最後の要素（next(D)）はdate／open_atだけを比べる（S1の投影と同じ）。開始日は新しい親の鎖によって変わってよい。
- same_as_superseded＝（input_hash、skipped_sessions、transition_result、state_afterがすべて元と一致）。復元点の後で制御記録だけをREPLAYした場合はtrueになる。RESTART_UNKNOWNをDROPした場合など、基点が変わればfalseになり得る。falseの記録は、計画で差として示す（上位RT-07）。

### 8.5 再生（REPLAY）と参照写像

写像m_k（seq=kのRECOVERY_RESTOREについて）：参照先tについて、tがP以前の有効記録なら変えない。tがREAPPLY／REPLAYされたなら、作られた記録のseq／hashへ写す。tがDROP／RETIREされたなら写像は無く、`restore_ref_unmapped`とする。計画（B-4）では、その記録もDROPに含めるよう求めて止める。黙って落とさない。

REPLAYで作る記録は、元記録とseq・parent・event_hash・参照・replay_of以外が同じ。ただし次は新しい鎖で計算し直す。
- DECLARE_MISSING：frontier_before・session_contextを新しい鎖で計算し直す。§6の規則を満たさなければ不正（例えば、前の宣言をDROPしたためにfrontierの次でなくなった場合）。
- RESTART_UNKNOWN：floorを新しい鎖で計算し直し、§7.1を満たすこと。
- ACK：applied_ref／missing_refをm_kで写す。fingerprintは同じ（REAPPLYでdecisionが変わらないため）。

replay_of＝`{from_seqのseq, event_hash}`。作られた記録は、最終ビュー（または後のRESTOREの直前ビュー）で通常の§6／§7の規則も満たすこと。

### 8.6 DROPとRETIRE

- DROPは、利用者が明示した制御記録の取り消しである（宣言の取消、再初期化の取消、不要になったACKの整理）。requestバッチの一部だけをDROPしない（`restore_partial_batch`）。
- RETIREは、退避した過去のRECOVERY_RESTOREに使う。その記録の効果は、以後の記録の並びとして既に表れているので、再生しない。監査鎖には残る。

### 8.7 CONSUME（未決。B-1では拒否）

宣言の取消や再初期化の取消のあとで、それまで消費しなかったDを消費し直す必要が生じることがある。例えば、DECLARE_MISSING(D3)をDROPすると、D3のdecisionが観測集合に戻る。このときCONSUMEは、既存evaluate_day（S1 prepare_dayの射影経由）で新たにAPPLYを作る処分になる。条件は次のとおり。
- 退避したどのAPPLYとも同じDではない（`restore_consume_applied_day`）。消費済みのDは、REAPPLYで保存済みのdecisionを使うしかない。
- 同じrequestバッチの再生の間に挟まない。
- 市場入力はseries、decisionは新しい鎖での台帳投影から取る。計画では、後続のREAPPLYがfalseになる差を示す。

CONSUMEが無い場合、上の操作は計画（B-4）で`restore_requires_consume`として止まる。つまり、宣言の取消や再初期化の取消は、取り消したDに今も有効なdecisionがあると実行できない。B-1の検査器はCONSUMEを`restore_op_unsupported`で拒否する。採否は§14のD-3。

### 8.8 計画（B-4）で追加する検査

計画は、`prepare_restore_plan(history, restore_point, ops, sessions, raw_observations, series, check_d, request_id, requested_at)` の形を想定する。B-1では作らない。
1. 履歴を検査し、復元点と処分の形を検査する。
2. 新しい鎖でREAPPLYを再計算する（apply_transition）。現在のseriesから同じDの判定入力をevaluate_day経由で作り直し、保存値と違えば`restore_market_input_changed`で止める（U-07。新しい値を自動で採用しない）。
3. 新しい鎖での台帳投影（B-2の投影関数）で、各REAPPLYのDについて、現在の台帳から選ばれるdecisionが保存済みの指紋と一致することを確かめる。違えば`restore_decision_changed`で止める。CORRECTIONで扱うべき差である。
4. 現在のsessionsで、保存したセッション範囲を投影して比べる（S1と同じく、next(D)のclose_at／confirmedだけを落とす）。
5. REPLAYする記録について、写像と§6／§7の再検査を行う。台帳に依存する証拠も、新しい鎖で再検査する（S3-Aと同じ規則）。
6. 候補全体を`validate_history`で検査し、basisに全入力のdigest（履歴・台帳・sessions・seriesの該当範囲）、期待先頭、候補のrecords、same_as_supersededの一覧と差の要約を入れ、plan_hashを計算する。確認時は全部を作り直して比べる。
7. 通知の意図は作らない。same_as_supersededは配信について何も言わない。

### 8.9 例R：3回の復元と拒否例（構造の例）

D0〜D6は連続した確定セッション。q1〜q3は依頼ID。

| seq | 記録 | 有効親 | 備考 |
|---|---|---|---|
| 0 | GENESIS(start_after=D0) | — | |
| 1 | APPLY D1 | 0 | |
| 2 | APPLY D2 | 1 | |
| 3 | RESTART_UNKNOWN(resume_after=D2) q1 | 2 | floor={D2, null, D0} |
| 4 | APPLY D3 | 3 | 新区間。基点は初期状態 |
| 5 | ACK/ADDED(D3, applied_ref=4) q2 | 4 | |
| 6 | APPLY D4 | 5 | |
| 7 | **RESTORE#1**(prev=6, 復元点=2, superseded=[3,4,5,6]) | 2 | ops：3 DROP(q1)、4 REAPPLY、5 REPLAY、6 REAPPLY。再初期化の取消 |
| 8 | APPLY D3（4の再適用、same=false） | 7 | 基点がD2の状態に変わる |
| 9 | ACK/ADDED(D3, applied_ref=8, replay_of=5) q2 | 8 | 参照4→8へ写像 |
| 10 | APPLY D4（6の再適用、same=false） | 9 | |
| 11 | APPLY D5 | 10 | 通常の日次 |
| 12 | RESTART_UNKNOWN(resume_after=D5) q3 | 11 | floor={D5, null, D0} |
| 13 | APPLY D6 | 12 | |
| 14 | **RESTORE#2**(prev=13, 復元点=9, superseded=[10,11,12,13]) | 9 | ops：10 REAPPLY、11 REAPPLY、12 DROP(q3)、13 REAPPLY |
| 15〜17 | APPLY D4／D5／D6（再適用。D6はsame=false） | 14→15→16 | |
| 18 | **RESTORE#3**(prev=17, 復元点=2, superseded=[7,8,9,14,15,16,17]) | 2 | ops：7 RETIRE、8 REAPPLY、9 DROP(q2)、14 RETIRE、15〜17 REAPPLY。不要になったACKの整理 |
| 19〜22 | APPLY D3／D4／D5／D6（再適用、same=true） | 18→19→20→21 | |

最終の有効鎖は0、1、2、18、19、20、21、22。退避の和集合は{3..6}∪{10..13}∪{7,8,9,14..17}＝{3..17}で、有効でない記録と一致する。

拒否例：
- RESTORE#3のsupersededを物理区間[3..17]と書く → `superseded_mismatch`（3〜6、10〜13は既に退避済み）。
- seq=23で復元点を5（RESTORE#1が退避）や12（RESTORE#2が退避）にする → `restore_point_not_effective`。
- 履歴がseq=21で終わる（RESTORE#3のバッチが途中） → `restore_incomplete`。
- 15のdecisionまたはrowを変えた再適用 → `restore_reapply_input`。same_as_supersededの偽り → `restore_replay_mismatch`。
- 9の再生でapplied_refを4のまま残す → `restore_ref_unmapped`／`restore_replay_mismatch`。
- 退避した4を処分REPLAYやDROPにする（APPLYはREAPPLYだけ） → `restore_op_kind`。
- 退避したqの2記録のうち1件だけDROP → `restore_partial_batch`。

例Rの各操作が実際に何の役に立つか（台帳がどうなっていればB-4の計画が通るか）は、B-4の受入条件で別に固定する。B-1では、構造と再計算の正しさだけを検査する。

## 9. 一括公開の境界

### 9.1 公開値（定義はS3-B、実装・実行はS3-C）

| 値 | 用途 | 結び付ける項目 |
|---|---|---|
| HistoryReplacement | 移行：v1のsnapshot.json → v2 | 期待するv1のsnapshot_digest・head、候補v2の全文、candidate_digest、plan_hash |
| HistoryAppendBatch | v2先頭への追記（日次APPLY、ACK／DECLAREのバッチ、RESTART、RESTOREと作られた記録群、prefix採用は別値） | 期待先頭seq/hash、追加する記録の正規化テキスト、候補全体のcandidate_digest、plan_hash |

どちらも、計画の確認からだけ作る。入力のdigestは計画のbasisにあり、値はplan_hashを持つ。B-1では作らない。B-1の確認結果はcommitted=Falseの候補Historyだけで、どのストアも受け付けない型である。

### 9.2 公開側の契約（S3-Cで新しいアダプタが満たす）

1. 書込みロックを取得し、残留物を走査し、現在の正本をロックの下で読み直して完全に検査する。
2. 期待値と比べる（Replacementはv1のdigestとHEAD、Batchはv2の先頭）。違えば`cas_conflict`。
3. 候補＝現在＋記録（またはReplacementの全文）を作り、candidate_digestと一致させたうえで、`validate_history`で完全に検査する。
4. 候補全体を1ファイルとして、一時ファイル→fsync→1回のreplace→（strictなら）ディレクトリ同期の順で公開する。replace呼出しの開始以後の失敗は成否不明とする。
5. 正常終了の結果だけがCOMMITTEDと保存水準を持つ。

復元記録・再計算したAPPLY群・解決記録・次状態は、すべて同じ1ファイルの1回のreplaceに含まれる。途中まで書いた正本は作らない。仮に途中のバッチが保存されても、§8.3の`restore_incomplete`と、requestバッチの欠けの検査で読込みが止まる。

### 9.3 既存S2・MemoryStoreでできること・できないこと

| 項目 | 既存公開APIのまま | 別アダプタが必要 |
|---|---|---|
| 移行前のv1の読込み・日次APPLYのcommit | できる（現状のまま） | — |
| v2の読込み | できない（validate_snapshotがunsupported_schema） | 必要 |
| 複数記録・RESTOREの一括公開 | できない（commitはAppendPlan＝単一APPLYだけを受け付け、plan_typeで拒否） | 必要 |
| v1→v2の置き換え | できない | 必要 |
| v2ファイルに対する旧S2ライターの上書き | 起きない（読込みで拒否されるため） | — |
| 旧S2ライターとの排他 | 新アダプタが同じwrite.lockの名前・O_EXCLの規約を使えば、公開の瞬間は排他される | 保守ゲート・全ライター停止の証明はS3-C |

既存S2の公開API・privateメソッドは変更せず、呼ばない。`fsops`の再利用や、ロック規約の共有方法は、S3-Cで決める。MemoryStoreにv2を受け付けさせる変更もしない。B-2以降で試験用のv2メモリストアが必要なら、新しいパッケージの新しい型として別依頼で扱う。

### 9.4 照合（成否不明の後）

S1のreconcileは「同じ親hash」を要求する厳しい形であり、S1設計§8でS3での再検討が留保されている。v2での照合の案は次のとおり（S3-Cで確定）。読み直した有効な履歴に、バッチの記録が期待先頭の直後に同じ内容で並んでいればALREADY_PUBLISHED、別の記録が並んでいれば`concurrent_conflict`、期待先頭のままなら再計画とする。誰が書いたかは示さず、通知の権利を与えない。

## 10. v2の日次処理と台帳投影（B-2の境界）

- **台帳投影**：S3-Aの除外→必要時だけの補完→version_selection→最終検査の順を、v2の有効鎖（全区間のAPPLY・skipped_sessions・宣言）で行う。S3-Aのモジュール関数（apply_records、check_versions、final_checks等）を、v2の有効鎖を読む表示（view）から呼ぶ方式を第一案とする。規則を複製しない。既存S3-Aのファイルは変更しない。必要な関数が公開されていない場合は、変更を提案として報告する。
- **日次**：現在の区間をS1 Snapshotへ射影し、最終台帳を渡して既存S1 `prepare_day`へ1回委譲する。結果のAPPLYを、v2の先頭へ付け直したHistoryAppendBatchにする。戦略式は複製しない。区間の境界以前のDは`target_not_after_boundary`とする。最新APPLY日の再実行は、射影の上でALREADY_APPLIEDとなる。
- **新規ACK／DECLARE_MISSING**：S3-Aの`prepare_resolution_plan`と同じ証拠・順序・エラー分類で、v2の名前空間の記録を作る（N-04、version_selection、ADDEDの証拠、check_dの上限を含む）。

## 11. 破損診断（B-5の境界）とS3-Cへの受け渡し

- `diagnose_history_bytes(data)` は、生バイトのsha256・長さ、UTF-8／JSON／ヘッダーの各段階の可否、宣言されたschema_version・head、検証できる最長prefix（件数・先頭seq/hash・状態digest・境界）、最初の失敗（seq、code、rule）を返す。**Historyを返さず、validとも言わない**。全体が検査に通った場合だけstatus=VALIDとする。
- 検証できるprefixとは、events[0..k−1]に、そこから計算したヘッダーを付けた履歴が`validate_history`に通る最大のk。復元バッチやrequestバッチの途中で切れるkは通らない。schema 1のファイルでは、S1のprefixとして同じ考え方で診断する。
- 採用候補は、別の計画 `prepare_prefix_adoption(data, k, …)` で作る。候補＝prefix＋RECOVERY_PREFIX_ADOPTION記録（evidenceに元バイトのsha256・長さ・宣言されたhead・捨てる位置）。確認には同じバイト列（digest一致）が必要である。捨てる後半が解析できる場合は、その種別・D・件数を計画に示すが、採用しない。
- prefixを採用すると後半の消費は失われる。その後、通常の追いつきで台帳から消費し直す。outboxや通知の意図は作り直さない。
- 元バイトの退避・保存水準の確認・解錠・候補の公開はS3-C。B-5は「候補が完全に検査済みであること」までで、復旧済みとは言わない。v1の破損ファイルの扱い（prefixを移行してから採用するか）はS3-Cの前に決める（§14のD-6）。

## 12. エラー分類（B-1）

| 条件 | code／field・rule |
|---|---|
| schema_version≠2、core_sha不一致 | unsupported_schema／schema_version・core_sha |
| 未知の種別（B-1ではRECOVERY_PREFIX_ADOPTIONを含む） | unsupported_event／kind |
| 形・キー・JSON・監査鎖・有効親・退避・バッチ・制御記録・再初期化・移行の各規則 | history_invalid／history、rule＝固定名（json_depth、json_number、header_keys、record_keys、seq、audit_hash、event_hash、parent、head、current_state、superseded_mismatch、restore_point_not_effective、restore_noop、restore_before_migration、restore_point_in_batch、restore_op_kind、restore_op_unsupported、restore_partial_batch、restore_incomplete、restore_reapply_input、restore_replay_mismatch、restore_ref_unmapped、restore_state、d_unique、applied_ref、missing_ref、fingerprints、exclude_applied、check_d、declare_frontier、declare_applied、session_context、batch、request_hash、request_basis、request_id、reason_code、requested_at、ledger_digest、state_after、restart_floor、restart_noop、restart_boundary、migration_position、migration_map、migration_source、migration_resolutions、origin、replay_of 等） |
| S1射影がS1検査に落ちる | history_invalid、rule＝"s1:"＋S1のrule（例 s1:transition_mismatch、s1:IB-04） |
| 移行の逆検証でS3-A検査に落ちる | history_invalid、rule＝"s3a:"＋S3-Aのrule |
| 移行計画の入力（v1・Set・台帳・sessions・check_d） | 既存のsnapshot_invalid／unsupported_schema、resolution_invalid、InputError／ConflictError、ledger_mismatch、late_observation 等をそのまま |
| 移行のrequest_idの衝突 | migration_request_conflict／request_id |
| 計画の改変・確認hashの違い | migration_plan_mismatch／plan |
| 確認時の入力変更 | migration_plan_stale／plan |

優先順は§4.5、移行計画では§5.1の順とする。エラー文は固定のcode／field／ruleと安全な件数・seqだけを持ち、raw値・F&G値・URL・note・source_url・パス・例外文を出さない。例外連鎖は抑える。

## 13. 範囲外・採用しないこと

- 通知意図・手動再送・outbox・配信権の再構築。復元・再生・移行は通知を作らない。
- 新保存先・資格情報・ライブ台帳、本番のU-01／U-11／U-13、保有・口座情報。本書はどれも採用したことにしない。
- S3-Cの実解錠・保守ゲート・退避先の同期・Windows strict。これらを解決済みとして書いていない。
- CORRECTION（U-03）と、未処理の版の選択。復元はREAPPLYで決定を変えないため、これらを迂回しない。
- 既存v2_core／v2_persistence（local含む）／v2_recoveryのコード・試験・fixtures・結果文書、CLAUDE／STATUS／ROADMAP、依存・設定・workflow・研究原本の変更。
- 任意区間の一括欠測、追いつき上限のための宣言、時計・自動対象日・プロセス・スレッド・乱数。

既存S3-Aの受理・拒否や採用済みN-04を変える必要は見つからなかった。v2は、S3-Aの記録を名前空間の写像つきで取り込み、S3-Aの検査器で逆検証する設計である。

## 14. 未決事項

「本書の推奨」は設計担当（Claude Opus 5.5）の推奨で、未採用。主担当の判断欄は空けてある。

| ID | 内容 | 本書の推奨 | 主担当の判断 | B-1に必要か |
|---|---|---|---|---|
| D-1 | §3〜§8の形式（単一履歴、監査鎖と有効親、鎖ビュー＋S1射影、移行で記録を挟み対応表で逆検証）とB-1の範囲を採用するか | 採用 | （未記入） | 必要 |
| D-2 | 復元点をSCHEMA_MIGRATION以後に限るか | 限る。移行範囲は原本を表す。必要になれば後で緩める | （未記入） | 必要 |
| D-3 | 復元でCONSUMEを許すか（宣言・再初期化の取消のあとで新たに消費する） | B-1では拒否。B-4の依頼前に、市場入力・台帳・差の表示の条件とあわせて決める | （未記入） | 不要（B-1は拒否で固定） |
| D-4 | B-1の実装担当のモデル・effort | Sonnet 5.5・high（仕様を固定した純粋な検査・変換の実装）。新形式の不変条件の実装に不安があればOpus 5.5・high | （未記入） | 必要 |
| D-5 | 効果のない復元（全REAPPLYがtrueでDROPも無い）を計画で拒否するか | B-4で拒否する案。検査器では受け付ける | （未記入） | 不要 |
| D-6 | v1の破損ファイルを採用する経路（prefixを移行してから採用するか） | S3-Cの前にB-5で決める | （未記入） | 不要 |
| D-7 | v2での照合（§9.4）の条件 | S3-Cで決める。S1の親hash条件は維持しない案 | （未記入） | 不要 |

外部の事実（本番の保存先、実PCのWindows strict、電源断）は確認していない。承認回答で確認済みにしない。

## 15. 作業記録

- 開始時に、作成依頼§5の24参照を`git ls-remote`の完全SHAで照合し、24件とも一致した（2026-10-29T05:33Z）。受領確認の資料ブランチ（docs/v2-recovery-s3a-fix-receipt-20261029＝abb2e73）も一致し、読取だけとした。
- 本書と依頼書の2文書だけを、コード基準e68d702から作った新しい資料ブランチdocs/v2-recovery-s3b-20261029に追加した。コード変更、試験実行、新しい市場計算、実ファイル復旧、PR、Actions、送信は0。終了時の照合結果と完全SHAは完了報告に記す（本書はその値を含められない）。
- モデル別の利用量は未計測。
