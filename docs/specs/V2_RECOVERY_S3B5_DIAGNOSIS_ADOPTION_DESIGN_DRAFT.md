# V2 S3-B-5 破損診断・prefix採用 設計案

作成日：2026-11-02（日本時間）。版：初版。
状態：**初版・設計案・レビュー待ち。B-5の限定実装は未承認。**
今回のユーザー指示は設計書・限定実装依頼書の作成まで。文書の保存・推奨・レビュー通過を実装承認に置き換えない。作成担当はClaude Opus 5.5、effort high（セッション情報で configured_model `claude-opus-5-5[1m]`、last_served_model `claude-opus-5-5`、effort_level `high` を確認）。

## 0. 要約

- B-5は、S3-B第2版§2の表と§11で「破損診断と、prefix採用候補の作成（RECOVERY_PREFIX_ADOPTION記録）」と定義された単位である。B-4設計§2.3で対象外とされた「B-5の破損診断・prefix採用、壊れた履歴の救済」を、本書の範囲とする。**CONSUMEはB-5に含めない**（§2.2）。
- B-5を二つに分けることを推奨する（D-1）。**B-5a**は、生バイトを読むだけの診断 `diagnose_history_bytes` を新パッケージに作り、既存ランタイムを変えない。**B-5b**は、8種目の記録RECOVERY_PREFIX_ADOPTIONと採用の計画・確認を作る。B-5bは受入済みのB-1検査器とB-2の読取りを変える必要があるため、境界と契約だけを本書で固定し、限定依頼は別に作る。
- 今回の限定依頼書（対になる docs/tasks/V2_RECOVERY_S3B5_LIMITED_IMPLEMENTATION_REQUEST.md）は**B-5aだけ**を対象とする。
- 診断は内容の問題で例外を出さず、固定キーの値を返す。厳格な読込み（S2と同じUTF-8・重複キー拒否・非有限数拒否）だけを行い、壊れたJSONから記録を拾い出さない。検証できる最長prefixは、変更しない`validate_history`（schema 2）または`validate_snapshot`（schema 1）に通る最大の件数kである。Historyを返さず、VALID以外で「有効」と言わない（D-2）。
- schema 1（v1）の破損ファイルは、B-5aで診断だけ行い、B-5bでも採用しない案を推奨する（D-4、S3-B第2版のD-6への回答案）。

## 1. 目的と固定入力

保存済みの履歴ファイルが壊れていたとき、どこまでが検証できるか、何が失われるかを、書込みなしに示す。上位第4版の明示復旧操作R-1「検証」（保存先を読み、検査して結果を出すだけ、書かない）を、v2履歴とv1スナップショットの生バイトについて具体化する。採用（B-5b）は、その診断の結果から、検証済みprefixを新しい正本の候補にする操作である。

| 用途 | 固定版 |
|---|---|
| コード開始点 | **ac219801d290ebb59b720f37a086103b6e1251c9**（fix/v2-history-restore-plan-s3b4-review-20261102）。コード・試験は00ae4b6a69e358fd868ce1f2e9b24b14519b507eと同じで、差はB-4結果文書§10の追記だけ |
| B-4受領 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab、docs/reviews/V2_RECOVERY_S3B4_FIX_REREVIEW_20261102.md（blob ae8419fe3acf36226ca4bc46441c9ea9539b0cef）。重大0・通常0・提案0 |
| B-4設計・依頼 | 0108131045d904b0997299fcade5929567940d6d。設計blob 6111058bdc0ae8eba1df15caccee03f83dd14d59（§2.2・§2.3・§14）、依頼blob dcbc98b2b7ca5fcc5a96d783b98f7a1711a71731 |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md。特に§2、§3.2〜§3.3（RECOVERY_PREFIX_ADOPTIONのキー）、§9、§11、§14のD-6 |
| 上位第4版 | e3e90947a718cca877b543739ca60539207ca7a7、docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md。§4.3のR-1・R-2・R-4、§6.5のK-01〜K-05 |
| B-3第2版 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba（元履歴のB-2投影を必須とする再開始） |

読解対象：上記文書、B-1のvalues／validate／view／restore／migration、B-2のchain、B-4のpoints、S1のcodec／events／recompute、S2のlocal/store（_loadの読込み順）、既存の範囲試験（h14、b17、r3_07、r4_09）。共通のCLAUDE.md・STATUS・MODEL_POLICY・ROADMAPも確認した。古いSTATUSの承認待ちの記述によって、B-4までの採用・受領を取り消さない。
今回は文書の作成のみ。コード変更、試験実行、再現コード、新しい市場計算は行っていない。本書の既存コードに関する記述は読取りによるもので、実行による確認ではない。

## 2. B-5の範囲の読み方

### 2.1 根拠

| 資料 | B-5に回された範囲 |
|---|---|
| S3-B第2版§2 | 「B-5：破損診断と、prefix採用候補の作成（RECOVERY_PREFIX_ADOPTION記録）」 |
| S3-B第2版§11 | `diagnose_history_bytes(data)`、検証できるprefixの定義、`prepare_prefix_adoption(data, k, …)`、元バイトの退避・公開はS3-C、v1の扱い（D-6）はS3-Cの前にB-5で決める |
| S3-B第2版§3.3 | RECOVERY_PREFIX_ADOPTIONの12キーとevidenceの6キー。B-1ではunsupported_event |
| B-4設計§2.3 | 「B-5の破損診断・prefix採用、壊れた履歴の救済」を対象外 |
| B-4設計§2.2・§14 | CONSUMEは保留。採用する場合は「B-1検査器・復元バッチ・受入条件を改める別の限定依頼」。B-5とは書いていない |

### 2.2 本書の解釈（明記）

- **B-5＝破損診断＋prefix採用**とする。S3-B第2版の単位定義をそのまま使い、B-4から回された「壊れた履歴の救済」もこれに含める。
- **CONSUMEはB-5ではない**。B-4設計は、CONSUMEを採用するなら別の限定依頼とし、その時期を定めていない。B-5は壊れた履歴を扱う単位であり、検証済み履歴上の復元の拡張であるCONSUMEとは前提が違う。CONSUME保留とrestore_requires_consumeでの停止、B-4§7.1案aの既知の拒否は、B-5の採否で変わらない。CONSUMEが必要になれば、B-4の後続（仮称B-4c）として別に設計する。
- S3-C（保守ゲート、解錠、元バイトの退避、CAS、公開、公開後照合、Windows strict）はB-5に含めない。
- この解釈が誤りであれば、D-1で範囲を差し戻してほしい。

### 2.3 B-5a／B-5bへ分ける案（D-1）

| 単位 | 内容 | 既存コードへの影響 |
|---|---|---|
| **B-5a 診断** | 新パッケージ `v2_history_diagnose`。生バイト→読込み段階・宣言値・検証できる最長prefix・捨てる後半の表示。schema 1とschema 2の両方。書込みなし、Historyを返さない | 既存ランタイム無変更。旧範囲試験3本（b17、r3_07、r4_09）の限定補正だけ |
| **B-5b 採用** | RECOVERY_PREFIX_ADOPTIONを8種目として検査器に加え、`prepare_prefix_adoption`／`confirm_prefix_adoption`で候補Historyまでを作る | v2_history（values、view、restore、__init__）、v2_history_ops/chain.py、v2_history_restore/points.pyの変更と、既存機能試験h02・h14の期待値の変更が要る（§9.7） |

分ける理由：

1. B-5bは、これまでの段階で一度も変えていない**受入済みのB-1検査器**を変える最初の作業になる。新しい記録種別は、全ての後続段階（B-2の読取り、B-3の再開始、B-4の復元）に「透明な制御記録」として現れる。この影響を、診断の正しさと混ぜずに別のレビューで確かめたい。
2. B-5aは単独で役に立つ。壊れたファイルを前にして、まず何が失われるかを書込みなしで知る必要がある（上位R-1）。B-5bの採用計画も、その中でB-5aの診断を呼ぶ。
3. B-5aは公開済みの`validate_history`／`validate_snapshot`だけを呼ぶので、B-5bで検査器が8種を受け付けるようになれば、診断も自動的にその記録を含む履歴を扱える。B-5aを先に作っても作り直しにならない。

一つの依頼にまとめる案（B-5a＋B-5b）も可能である。その場合、変更境界・受入条件・欠陥注入は本依頼書の約2倍になり、既存機能試験の編集を含む。主担当がその形を望むなら、D-1で選んでほしい。

### 2.4 対象外

S3-Cの全事項、CLI、ファイル・パスの読み書き、実時計・乱数・ネット、通知・outbox、売買・口座、CONSUME、B-4§7.1の既知制限の解消、CORRECTION（U-03）。壊れたJSONの部分的な救出（§4.3）。台帳・sessions・seriesによる照合（§9.6）。

## 3. B-5a：APIと値

| 名前 | 契約 |
|---|---|
| diagnose_history_bytes(data) | dataは厳密に`bytes`型。それ以外（str、bytearray、memoryview、None等）は`PersistenceError("diagnosis_invalid", "data", rule="type")`。内容の問題では例外を出さず、HistoryDiagnosisを返す |
| HistoryDiagnosis | 不変の値。to_dict、digest、summary、安全なrepr、各キーの読取り（独立した写し）。直接構築は信頼済み内部入力に限るとdocstringに明記。from_dictは作らない |
| 状態定数 | VALID、PREFIX_ONLY、NO_VALID_PREFIX、UNREADABLE |

__all__は上の1関数・1型・4定数の6名。既存パッケージへ再公開しない。

### 3.1 HistoryDiagnosis.to_dict()の固定10キー

| キー | 値 |
|---|---|
| operation | "soxl-v2-history-diagnosis/1" |
| status | 4定数のどれか（§3.2） |
| raw_sha256 | 生バイトのSHA-256（16進64桁） |
| raw_size | 生バイトの長さ（int） |
| schema_version | 検査に使った版（1または2）。§4の段階3に届かなければnull |
| canonical_text | 生バイトが、読み込んだ値の`canonical_json(...).encode("utf-8")`と完全一致するか。JSONとして読めなければnull。**状態には影響しない参考値** |
| failure | null、または{stage, code, field, rule}（§4.2）。VALIDのときだけnull |
| claimed | null、または{schema_version, core_sha_matches, head_seq, head_hash, event_count}（§4.4） |
| verified | null、または検証できた文書の要約（§5.4）。VALIDでは全体、PREFIX_ONLYではprefix |
| discarded | null、または{from_index, count, items}（§6）。PREFIX_ONLYとNO_VALID_PREFIXで使う |

digestは`sha256_text(canonical_json(to_dict()))`。同じバイト列からは常に同じto_dictとdigestになる（時刻・乱数を含めない）。B-5bの採用計画はこのdigestを計画に結び付ける。

### 3.2 状態

| status | 条件 |
|---|---|
| VALID | 全体が、選んだ版の変更しない検査器に通る |
| PREFIX_ONLY | 全体は通らないが、k≥1のprefixが通る。k＝元のevents件数（後半を捨てずヘッダーだけ違う）も含む |
| NO_VALID_PREFIX | 版・core_shaは読めたが、どのk≥1も通らない。eventsが空でないlistでない場合も含む |
| UNREADABLE | §4の段階1〜3（UTF-8、JSON、版）で止まった。prefixは探さない |

## 4. 読込みの段階と失敗の記録

### 4.1 段階

| 段階 | 処理 | 失敗の記録（failure） | 次へ進むか |
|---|---|---|---|
| 1 utf8 | `data.decode("utf-8")`（strict）。BOMは除かない（S2の_loadと同じ。BOMつきはJSON段階で失敗する） | {utf8, "unreadable", "data", "utf8"} | 止める（UNREADABLE） |
| 2 json | 変更しない`decode_history(text)`で厳格に読む（重複キー、NaN/Infinity、深さ、巨大整数の拒否は既存のまま）。版を見る前なのでv2の読込み関数を共通に使い、得たHistoryは`to_dict()`で読むだけ | {json, 既存のcode, field, rule}（history_invalid/history/json・json_depth・json_number等） | 止める（UNREADABLE） |
| 3 schema | 最上位がdict、`schema_version`がboolでないintで1または2、`core_sha`が既存`CORE_SHA`と一致 | 最上位がdictでない：{schema, "history_invalid", "history", "shape"}。版：{schema, "unsupported_schema", "schema_version", null}。core_sha：{schema, "unsupported_schema", "core_sha", null} | 止める（UNREADABLE） |
| 4 validate | 版2は`validate_history(History.from_dict(data))`、版1は`validate_snapshot(Snapshot.from_dict(data))`。どちらも変更しない | 検査器のcode/field/ruleをそのまま（例 history_invalid/history/audit_hash、snapshot_invalid/snapshot/head_hash）。stage="validate" | 通ればVALID、落ちれば§5へ |

段階3で止める理由：版やcore_shaが違うのは破損ではなく、別の形式・別のコアである。§5のprefixはヘッダーを`CORE_SHA`で計算し直すため、core_sha違いのファイルでprefix探索をすると、違う版を「ヘッダーだけ壊れた正しい履歴」として扱ってしまう。

### 4.2 failureの形

{stage, code, field, rule}の4キー。stageは"utf8"、"json"、"schema"、"validate"。code/field/ruleは固定の識別子だけで、例外文・生の値・パスを含めない。

検査器からPersistenceError以外の例外が出た場合（validate_snapshotの内部でKeyError等が起きる場合を含む）、`validate_history`と同じ例外集合（CoreError、KeyError、TypeError、ValueError、AttributeError、IndexError、OverflowError、RecursionError）を捕まえ、PersistenceError・CoreErrorはそのcode/field/rule（CoreErrorのruleはnull）を、その他は版2なら{history_invalid, history, malformed}、版1なら{snapshot_invalid, snapshot, malformed}を記録する。例外の連鎖や文面は持ち出さない。

failureは**全体の検査で最初に出たエラー**であり、そのエラーが§6のfrom_indexの記録で起きたとは言わない。検査器はseqつきのエラーを返さないためである。

### 4.3 壊れたJSONを救出しない

書込みが途中で切れたファイルは、JSONとして読めないことが多い。その場合でも、本書は寛容な構文解析で途中までの記録を拾い出さない（UNREADABLE、prefixなし）。理由：

- 寛容な解析は新しい構文規則を持ち込み、重複キー・非有限数・深さ等の既存の厳格な規則と別の結果を出し得る。
- S2とS3-Cの公開は「一時ファイル→fsync→1回のreplace」であり、正常な経路では途中で切れたファイルが正本にならない。切れたファイルが見つかるのは、公開の外側での破損であり、退避した元バイトや別の保存（S3-C）から戻すほうが確実である。
- 失われる範囲を推測で決めず、「読めない」と正しく伝えることを優先する。

この制限はD-2に含める。

### 4.4 宣言値（claimed）

段階2を通り最上位がdictなら作る。各値は型が正しいときだけ値を持ち、そうでなければnull。

| キー | 値 |
|---|---|
| schema_version | boolでないint |
| core_sha_matches | core_shaが文字列なら一致したかのbool、文字列でなければnull |
| head_seq | boolでないint |
| head_hash | 16進64桁の文字列 |
| event_count | eventsがlistならその長さ |

宣言値は検査済みの値ではない。表示とB-5bのevidenceにだけ使う。

## 5. 検証できる最長prefix

### 5.1 定義

eventsが空でないlistで、段階4が失敗したとき、k＝n,n−1,…,1（n＝eventsの件数）について次を作り、通る最大のkを採る。

- 版2：`History.from_dict(history_dict(events[:k]))`を`validate_history`へ。
- 版1：`Snapshot.from_dict(snapshot_dict(events[:k]))`を`validate_snapshot`へ。

ヘッダーは末尾の記録から計算し直す（S3-B第2版§11の定義どおり）。各kの組立てや検査で§4.2の例外集合が出たら、そのkは通らないとして次へ進む。通るkがあればPREFIX_ONLY、無ければNO_VALID_PREFIX。

### 5.2 上から全部試す理由

「prefix kが通る」はkについて単調ではない。

- 復元バッチ（RECOVERY_RESTOREと作られた記録群）の途中で切れるkは`restore_incomplete`で通らないが、バッチの直前と、バッチを含む長いkは通る。
- ACK／DECLAREのrequestバッチの途中で切れるkも同様（command_countの欠け）。

そのため二分探索や下からの探索は使わず、上から順に試して最初に通ったkを採る。これは`validate_history`の判断をそのまま使うためで、バッチ境界を診断側で独自に判定しない。

既知の性質：

- 移行済み履歴で、SCHEMA_MIGRATION自身かそれ以前が壊れている場合、移行前の範囲のACK／DECLAREは`origin`を持つため、MIGRATIONを欠いたprefixは`origin`規則で通らないことが多い。移行前にGENESIS／APPLYしか無い場合は、MIGRATIONを欠いたprefixが新規v2として通り得る。診断はそのとおり報告する（discardedにSCHEMA_MIGRATIONが現れる）。採用の可否はB-5bで扱う（§9.5）。
- 記録を書き換えたうえでevent_hashと後続の監査hashまで計算し直されたものは検出できない。digestは整合性の検査であって署名ではない（S1から同じ）。

### 5.3 費用

最悪（GENESISの直後が壊れている場合）、検査をn回行い、各回が最大n件を検査する。S1射影の再計算を含むため、件数が多いと時間がかかる。本書は上限・打ち切り・高速化を入れない。限定実装では、合成した1年分程度（APPLY約260件）の履歴で最悪位置の所要時間を実測し、結果文書に記録する。打ち切りが必要と判明したら、別判断とする。

### 5.4 verifiedの形

| キー | 版2（HistoryCheckから） | 版1（ValidatedSnapshotから） |
|---|---|---|
| count | k（VALIDではn） | 同じ |
| head_seq / head_hash | HistoryCheckの値 | ValidatedSnapshotの値 |
| state_digest | HistoryCheck.state_digest | `sha256_text(canonical_json(state.to_dict()))`（ValidatedSnapshot.state） |
| document_digest | 検査した文書（再計算したヘッダーを含む）の正規化テキストのSHA-256 | 同じ（`encode_snapshot`の文字列） |
| boundary | {kind, seq, after}（current_boundary） | {"GENESIS", 0, start_after} |
| latest_apply_d | HistoryCheckの値 | 最後のAPPLYのD、無ければnull |
| processing_after | HistoryCheckの値 | as_of_d、無ければstart_after |
| effective_count / superseded_count | effective_seqs／superseded_seqsの件数 | count／0 |
| migrated | HistoryCheck.migrated | null |

VALIDのdocument_digestは元の文書の正規化テキストのdigestであり、canonical_textがtrueならraw_sha256と一致する。

## 6. 捨てる後半の表示（discarded）

PREFIX_ONLYでは{from_index: k, count: n−k, items}、NO_VALID_PREFIXでeventsがlistなら{from_index: 0, count: n, items}、eventsがlistでなければnull。

itemsはindex k〜n−1の各要素について{index, kind, seq, d, request_id}。

- kind：文字列で、その版の既知の種別（版2はv2_history.KINDSの7種、版1はGENESIS/APPLY）ならその値、それ以外は"?"。
- seq：boolでないintならその値、そうでなければnull。
- d：要素がdictで`d`が日付として正しければその値、そうでなければnull（RESTART_UNKNOWNのresume_afterは表示しない）。
- request_id：要素がdictで、`valid_request_id`に通る`request_id`を持てばその値、そうでなければnull。

市場値・F&G・decision・自由文・パスは出さない。後半は検査に通っていないので、これらの値は「その位置に書かれていた文字列」であって事実ではない。summaryは件数と種別ごとの数、最初と最後のdだけを示す。

## 7. 不変性・表示・エラー

- HistoryDiagnosisは不変。to_dictと各読取りは独立した写しを返す。内部に元バイト、デコードした文字列、Historyを保持しない（digestと要約だけ）。
- repr／summaryは、status、stage、code/field/rule、raw_size、raw_sha256の先頭12文字、件数、seq、日付、固定語だけ。生の値やURL、例外文を出さない。
- 例外を出すのは引数の型違い（§3）だけ。内容の不正はすべて値で返す。
- 旧MemoryStore／LocalFileStoreはHistoryDiagnosisを受け付けない（plan_type）。診断は何も保存しない。

## 8. 診断が言わないこと

- PREFIX_ONLYは「このkまでが現在の検査器に通る」ことだけを示す。復旧済み、採用済み、正本とは言わない。
- 台帳・sessions・seriesとの照合はしない。prefixの全区間投影が現在の台帳で通るかは、B-2以降の通常の操作で分かる（§9.6）。
- canonical_text=falseは改ざんの証拠ではない。手で整形しただけのファイルでも起きる。
- v1のResolutionSet（S3-A）はファイル形式を持たないため、診断の対象外。

## 9. B-5b：採用記録と計画・確認の境界（今回は依頼しない）

本節はD-3で境界として固定するかを判断する。B-5bの限定依頼は、B-5aの受領後に別に作る。

### 9.1 記録

S3-B第2版§3.3の12キーをそのまま使う：
kind, seq, parent_seq, parent_hash, evidence, request_id, request_hash, request_basis, reason_code, requested_at, state_after, event_hash。

- seq＝k、parent＝k−1（通常の監査鎖）、state_after＝親のstate_after。
- evidenceは6キー{raw_sha256, raw_size, claimed_schema_version, claimed_head_seq, claimed_head_hash, discarded_from_seq}。discarded_from_seq＝seq。claimed_*は§4.4の宣言値（不正ならnull）。claimed_schema_versionはD-4の推奨では2だけ。
- request_basisは4キー{request_id, evidence, reason_code, requested_at}。reason_code＝"ADOPT_VERIFIED_PREFIX"。request_hashは既存`basis_request_hash`。

### 9.2 検査器の変更（B-1）

- values：KINDSへ8種目を加え、RECORD_KEYSに12キーを登録。
- view：chain viewの制御記録の分岐に追加。state_afterが親と同じ、evidence・request_basis・request_hash・reason_code・requested_atの形、discarded_from_seq＝seq、`claim_request`でIDを登録。区間は変えない（GENESIS／RESTART_UNKNOWNではない）。S1射影は無関係。
- migration：既存のcheck_positionsは、MIGRATIONより前の記録をGENESIS／APPLY／ACK／DECLAREに限るので、MIGRATIONより前の採用記録はmigration_positionで拒否される（変更不要の見込み。B-5bで試験する）。
- restore：採用記録を退避する復元を拒否する。今の`_ALLOWED[kind]`は採用記録でKeyErrorとなり`malformed`になるため、明示の規則`restore_before_adoption`（復元点が鎖ビュー上の最後の採用記録より前）を加える。復元点が採用記録自身は可。
- 現在B-1では、未知の種別はview.recordで何も検査されずに通り抜ける作りであり、KINDSにだけ足すと検査の抜けになる。分岐の追加とKINDSの追加は同じ変更で行う。

### 9.3 後続段階への影響

| 段階 | 変更 | 理由 |
|---|---|---|
| B-2 chain.py | `_REQUEST_KINDS`へ採用記録を加える | 新規依頼のIDが採用記録のIDと重なったとき、既存の`history_request_conflict`で止めるため。足さないと候補の検査でhistory_invalid/request_idになる |
| B-2の投影・日次 | 変更なし | 区間・APPLY・宣言だけを読む。採用記録の後のAPPLYは親が採用記録になるが、S1射影は区間のAPPLYだけを再接続する |
| B-3 | 変更なし | floorはAPPLY・宣言・区間だけを読む |
| B-4 points.py | 復元点の下限に`restore_before_adoption`を加える | B-1と同じ規則を計画段階で先に返すため |

### 9.4 IDと位置

- 新しい採用のrequest_idは、prefixの物理履歴全体で未使用であることに加え、捨てる後半で読めたrequest_id（§6のitems）とも重ならないこと。後半に同じIDがあると、後でS3-Cの照合が「既に公開された」と誤認し得るため。
- 採用記録は復元バッチ・requestバッチの途中に入らない（prefixの定義から、kの直前はバッチの終わり）。

### 9.5 計画・確認

- `prepare_prefix_adoption(data, adopt_count, request_id, requested_at)`：B-5aの診断を呼び、statusがPREFIX_ONLY、版2、adopt_count＝verified.countであることを要求する。捨てる後半にSCHEMA_MIGRATIONが読める場合は拒否する（移行の事実を失うため）。候補＝prefix＋採用記録を変更しない`validate_history`へ通し、READYの計画を返す。
- 計画のbasisには、operation、status、raw_sha256、raw_size、diagnosis_digest、adopt_count、prefixの head・state・document digest、discardedの要約、request_id、request_hash、reason_code、requested_at、candidate_history、candidate_digest、candidate_state_digest、candidate_recordを入れる案。キー数はB-5bの依頼で固定する。
- `confirm_prefix_adoption(plan, confirmed_plan_hash, data)`：(a)同じ生バイト（raw_sha256とraw_sizeが一致）なら診断と計画を作り直して全basisを比較し、CONFIRMED_IN_MEMORYと候補を返す。(b)dataが候補の正規化バイトそのものならNO_CHANGE。他はhistory_plan_stale、改変やhash違いはhistory_plan_mismatch（B-2のerrorsを再利用）。
- エラーの案：adoption_invalid/data/not_adoptable（VALID・NO_VALID_PREFIX・UNREADABLE）、adoption_invalid/adopt_count/count_mismatch、adoption_invalid/data/schema_1（D-4）、adoption_invalid/data/migration_discarded、history_request_conflict/request_id。
- 返すのは候補Historyまで（committed=False）。元バイトの退避・公開・照合はS3-C。

### 9.6 台帳を使わない理由と結果

S3-B第2版§3.3の記録はledger_digestを持たない。採用は「検証できない後半を捨てる」操作であり、市場状態を変えず、新しい台帳の判断をしない。採用の計画は台帳・sessions・seriesを受け取らない。

結果として、捨てた後半にあったACK／DECLARE／APPLYで解決していた台帳の食い違いは、採用後のB-2投影で再び現れ得る（例：後半のLATE ACKで除外していた後発がlate_observationに戻る）。これは失われた記録を作り直さないという設計の帰結であり、B-2の新規ACK／DECLARE、B-2日次の追いつき、B-3の再開始で、通常どおり処理する。採用だけで「追いつき済み」とは言わない。outboxや通知の意図は作り直さない（S3-B第2版§11）。

### 9.7 既存試験への影響

B-5bでは、v2_history・v2_history_ops・v2_history_restoreのランタイム変更に伴い、少なくとも次の既存機能試験の期待値が変わる。

- tests/v2_history/test_h02_values_codec.py：未知種別の例に"RECOVERY_PREFIX_ADOPTION"を含む。
- tests/v2_history/test_h14_scope_and_stop.py：KINDSが7件であること、B-5の種別を拒否すること、公開名の一覧。
- 旧範囲試験（b17、r3_07、r4_09、B-5aの新scope）：v2_history・v2_history_ops・v2_history_restoreの差分0を固定している。

これらを「無編集」とは言えないため、B-5bの依頼で変更箇所を一つずつ固定する。

## 10. v1の破損ファイル（D-4、S3-B第2版D-6への回答案）

| 案 | 内容 | 評価 |
|---|---|---|
| (i) 診断だけ（推奨） | B-5aでv1も診断する。B-5bではschema 1の採用を拒否する（adoption_invalid/data/schema_1）。壊れたv1は、S3-Cで退避した元バイトや別の保存から戻すか、R-4の明示初期化（新規v2のGENESIS）で始め直す | 現時点で本番のv1ファイルは無い（S2は本番未接続、mainは停止中）。v1の採用経路は使う場面が見込めない |
| (ii) prefixを移行してから採用 | v1のprefixを既存の`prepare_migration_plan`で移行し、MIGRATIONの直後に採用記録（claimed_schema_version=1）を置く | ResolutionSetのうち捨てた後半を参照する記録の扱い、MIGRATIONと採用記録の位置規則、evidenceと移行元digestの関係を新たに決める必要がある |
| (iii) v1のまま採用 | — | v1の検査器は新しい種別を持てず、旧検査器を緩めない方針に反する。採らない |

(i)を推奨する。後で本番にv1のデータが生じた場合は、(ii)を別に設計する。

## 11. B-5aの最小受入例

| 例 | 期待 |
|---|---|
| 例R（複数回復元）・移行済み履歴・新規v2を既存ビルダーで作り、`encode_history(...).encode("utf-8")` | VALID、canonical_text=true、verifiedが`validate_history`のHistoryCheckと一致、document_digest＝raw_sha256 |
| 同じ値を字下げつきJSONで書いたバイト | VALID、canonical_text=false |
| 空、途中で切れたバイト、非UTF-8、BOMつき、重複キー、NaN、深さ超過 | UNREADABLE。stageとruleが§4.1どおり。prefixを探さない（検査器のspyで0回） |
| 最上位がlist、schema_version 3、bool、core_sha違い（v1・v2とも） | UNREADABLE（schema段階）。core_sha違いのv2で、ヘッダーを作り直せば通る入力でもprefixを探さない |
| head_hashだけ違う、current_stateだけ違う | PREFIX_ONLY、count＝n、discarded.count＝0 |
| 末尾の記録のevent_hashを変える | PREFIX_ONLY、count＝n−1、itemsに種別とd |
| 中ほどのAPPLYの値を変える（hashは変えない） | PREFIX_ONLY、count＝その位置。後ろの正しい記録も捨てる側に出る |
| 復元バッチの途中で終わる履歴、requestバッチの途中で終わる履歴 | PREFIX_ONLY、countはバッチの開始位置。途中のkは`validate_history`が拒否したことをspyで確認 |
| バッチの途中で切ったkより長いkが通る入力 | 上からの探索で最長が選ばれる（非単調の対照） |
| GENESISを壊す | NO_VALID_PREFIX、discarded.from_index＝0 |
| 移行済み履歴でMIGRATIONの記録を壊す（移行前にACKあり／GENESIS・APPLYだけの2種） | 前者はNO_VALID_PREFIXまたはMIGRATIONより前で通らない結果、後者はMIGRATIONを捨てるPREFIX_ONLY。どちらも実際の検査器の結果をそのまま記録し、itemsにSCHEMA_MIGRATIONが出ることを確認 |
| v1（S2の`encode_snapshot`のバイト）：正常・末尾改ざん・ヘッダーだけ違う | VALID／PREFIX_ONLY（n−1）／PREFIX_ONLY（n）。schema_version=1、migrated=null |
| 同じバイトを2回診断 | to_dictとdigestが完全一致。元のbytesは変更されない |
| 型違いの引数 | diagnosis_invalid/data/type |

## 12. 委譲境界（B-5aで許す既存公開依存）

- v2_history：History、validate_history、decode_history、KINDS。v2_history.values：history_dict。v2_history.common：is_int、is_hex64、is_date。
- v2_persistence.codec：CORE_SHA、Snapshot、canonical_json、sha256_text、encode_snapshot。v2_persistence.events：snapshot_dict。v2_persistence.recompute：validate_snapshot。v2_persistence.errors：PersistenceError。
- v2_core.errors：CoreError。v2_recovery.common：valid_request_id。
- 標準ライブラリ：copy、hashlib（生バイトのSHA-256だけ。既存の`sha256_text`は文字列しか受け取らないため）。B-4までの範囲試験はhashlibを禁止していたので、B-5aの新scopeでは用途を1か所に限ることを検査する。

実装で実際に使うものだけimportする。既存private名（_Walk、Chain、_internal等）、テストヘルパー、旧ストアのprivateメソッドは使わない。

## 13. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | B-5の範囲を「破損診断＋prefix採用」と読み、CONSUMEを含めないこと。B-5をB-5a（診断、既存ランタイム無変更）とB-5b（採用記録、検査器変更）に分け、今回の限定依頼をB-5aだけとすること | 採用を推奨。まとめる案を選ぶ場合は、依頼書を作り直す |
| D-2 | 診断の読み方：厳格な読込みだけで壊れたJSONを救出しない（§4.3）、版・core_sha違いでprefixを探さない、最長prefixは変更しない検査器に通る最大kを上から全探索で求める（§5）、内容の問題は例外でなく値で返し、Historyを返さない | 採用を推奨 |
| D-3 | B-5bの境界（§9：12キー記録、evidence6キー、basis4キー、採用記録を退避しない`restore_before_adoption`、IDは後半の読めたIDとも重ねない、台帳を使わない、既存B-1／B-2／B-4の最小変更と既存試験の編集が要ること）を先に固定すること | 境界としての固定を推奨。B-5bの実装承認ではない |
| D-4 | v1の破損ファイル（S3-B第2版D-6） | 案(i)：診断だけ、採用しない |
| D-5 | B-5aの実装担当 | Sonnet 5.5・high。仕様を固定した読取り専用の診断で、会計・戦略・保存方式の再設計を含まない。矛盾は主担当へ返す |

D-1〜D-5を一組で判断する。今回の文書作成は採用ではない。B-4の受領をB-5の実装承認にしない。CONSUME、B-5b、S3-C、全体稼働、本番保存先・資格情報は今回の採否に含まない。

## 14. 作業記録

- 開始時（2026-11-02T06:17Z）に、B-4修正再レビュー§6の54参照と再レビュー資料1f7d8c1の計55参照を`git ls-remote`の完全SHAで照合し、55件とも一致した。
- 本書と依頼書の2文書だけを、コード開始点ac21980から作った新しい資料ブランチdocs/v2-history-s3b5-20261102に追加した。コード変更、試験実行、再現コード、新しい市場計算、PR、Actions、送信は0。終了時の照合結果と完全SHAは完了報告に記す（本書はその値を含められない）。
- 既存コードの読取りで確認した事実（未知種別がview.recordを素通りすること、restoreの`_ALLOWED[kind]`がKeyErrorになること、check_positionsの移行前種別の制限、h02・h14の期待値）は、実行による確認ではない。
- モデル別の利用量は未計測。
