# V2 S3-B-5b prefix採用 設計案

作成日：2026-11-02（日本時間）。版：初版。
状態：**初版・設計案・採否判断待ち。B-5bの限定実装は未承認。**
今回のユーザー指示は、B-5bの設計の具体化と限定実装依頼書の作成まで。文書の保存、推奨、レビュー通過、一時環境での試行の合格を、実装の承認と扱わない。作成担当はClaude Opus 5.5、effort high（セッション情報の確認は§11）。

## 0. 要約

- B-5bは、B-5設計第2版（5c9e1e8）の§9で境界を固定した単位である（D-3、採用済み）。8種目の記録RECOVERY_PREFIX_ADOPTIONを検査器に加え、B-5aの診断がPREFIX_ONLYを返した生バイトから、検証済みprefix＋採用記録の**候補History**を作る計画と、メモリ内の確認を作る。公開・退避・照合（S3-C）、CONSUME、ファイル書込みは含まない。
- 既存ランタイムの変更は3段階の6ファイルに限る（§3、§4）。B-1検査器（v2_history/values・view・restore・\_\_init\_\_）、B-2の`_REQUEST_KINDS`（v2_history_ops/chain.py）、B-4の復元点の下限（v2_history_restore/points.py）。新規は`v2_history_adopt/`の1パッケージで、公開名は7つ（§5）。
- 一時環境（c8ba08fのコピー、pushしないローカルコミット）で、§3・§4の最小変更と、§7の既存試験6本の補正を実際に適用した。既存9スイート1464件（1333件＋B-5a 131件）がLinux・Python 3.13.18で全件合格した。採用記録の振る舞いを32項目の使い捨てプローブで確認した（§8）。これは正式な実装や受入試験ではない。
- B-1検査器の変更は、記録1種の追加、chain viewでの採用記録の検査（新しいrule `adoption_evidence`）、復元の下限`restore_before_adoption`の3点である。既存の記録と既存の規則は緩めない。移行より前・バッチの途中・復元の窓の途中の採用記録、IDの重複は、既存の規則（migration_position、batch、restore_incomplete、request_id）がそのまま拒否することを試行で確認した。
- 既存試験の変更は、期待値が変わる機能試験2本（h02、h14）と、旧範囲試験4本（b17、r3_07、r4_09、d5_08）である。旧範囲試験は前の段階の範囲試験の差分を固定文字列で持つため、補正が連鎖する。d5_08の補正は追加374行・削除87行と大きい（§7.3）。B-5bでは前例どおりの補正を推奨し、連鎖を止める方式は次の段階の前に別に設計することを提案する（D-3）。
- 採否はD-1〜D-4の一組（§10）。

## 1. 目的と固定入力

壊れた履歴ファイルについて、検証できる先頭部分（prefix）を新しい正本の候補にする。上位第4版の明示復旧操作R-2「採用」を、v2履歴について具体化する。採用は「検証できない後半を捨てる」ことを、検査器が読める記録として残す操作であり、市場状態を変えず、新しい台帳の判断をしない。

| 用途 | 固定版 |
|---|---|
| コード開始点 | **c8ba08f15ea28248a9fe7924f32ce136fc16d5e6**（feat/v2-history-diagnose-s3b5a-20261102）。B-5aの試験対象fac880cに結果文書1本を加えたもの |
| B-5a受領 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9、docs/reviews/V2_RECOVERY_S3B5A_IMPLEMENTATION_REVIEW_20261102.md。重大0・通常0・提案1（§12） |
| B-5設計・依頼 第2版 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136（docs/v2-history-s3b5-20261102）。設計blob f4d4225545627dd5e7df1fc5c5e092a49ccee10f。**§9がB-5bの境界（D-3）**、§3〜§6が診断の値 |
| B-5第2版の再レビュー | 6a7210c2e278e604b953acf904cf9e796c2ce710。D-1〜D-5は採用済み（B-5a結果文書§1の記録） |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md。§3.3（記録のキー）、§11（B-5の境界） |
| B-4設計・依頼 | 0108131045d904b0997299fcade5929567940d6d（計画・確認・NO_CHANGEの形の手本） |
| 上位第4版 | e3e90947a718cca877b543739ca60539207ca7a7。§4.3のR-1〜R-4 |

読解対象：上記の文書、c8ba08fのv2_history（values、validate、view、restore、migration、common）、v2_history_ops（chain、plan、errors）、v2_history_restore（points、build、confirm、values）、v2_history_diagnose（全5ファイル）、範囲試験（h14、b17、r3_07、r4_09、d5_08）、h02。共通のCLAUDE.md・STATUS・MODEL_POLICY・ROADMAPも確認した。古いSTATUSの承認待ちの記述によって、B-5aまでの採用・受領を取り消さない。

## 2. 範囲

| 含む | 含まない |
|---|---|
| B-1検査器へのRECOVERY_PREFIX_ADOPTIONの追加（§3） | 生バイトの退避、新しい正本の公開・書込み、元ファイルとの照合（S3-C） |
| B-2 `_REQUEST_KINDS`とB-4 `check_point`の最小変更（§4） | CONSUME（B-4後続の別単位） |
| 新規`v2_history_adopt`：`prepare_prefix_adoption`と`confirm_prefix_adoption`（§5） | v1（schema 1）の採用（B-5のD-4で採用しないと決定済み） |
| 既存試験6本の限定補正（§7）と新規試験 | ストア、ファイル・パス、CLI、通知、本番接続、台帳・sessions・seriesの受取り |
| | 捨てた後半の記録の作り直し、outbox・通知意図の作り直し |

## 3. B-1検査器の変更

### 3.1 values.py

- 定数`RECOVERY_PREFIX_ADOPTION`（既にある）を**KINDSの8番目（末尾）**に加える。既存7種の並びは変えない。B-1で「B-5用に定義済みで拒否」と書いたコメントは消す。
- `ADOPTION_KEYS`として12キーを`RECORD_KEYS`に登録する：kind, seq, parent_seq, parent_hash, evidence, request_id, request_hash, request_basis, reason_code, requested_at, state_after, event_hash（S3-B第2版§3.3のとおり。prev_hashもledger_digestも持たない）。
- 監査鎖と実効親は、RECOVERY_RESTORE以外の記録と同じ既存の一般規則で検査される。parent＝直前の記録（seq−1）、parent_hash＝その記録のevent_hash。採用記録だけの規則は作らない。

### 3.2 view.py：chain viewでの検査

`_Walk.record`の制御記録の分岐に採用記録を加え、同じクラスのメソッド`adoption_record`で次を**この順に**検査する。新しいモジュールファイルは作らない（v2_historyのファイル一覧を固定しているh14を変えないため）。

| 順 | 検査 | rule |
|---|---|---|
| 1 | `claim_request(request_id)`（形式と、chain view内の既出IDとの重複） | request_id（既存） |
| 2 | state_afterが親のstate_afterと同じ | state_after（既存） |
| 3 | evidenceがdictで6キー{raw_sha256, raw_size, claimed_schema_version, claimed_head_seq, claimed_head_hash, discarded_from_seq}ちょうど。raw_sha256は16進64桁。raw_sizeは1以上の厳密整数（boolは不可）。claimed_schema_versionは厳密整数の2。claimed_head_seqは厳密整数かnull。claimed_head_hashは16進64桁かnull。discarded_from_seqは厳密整数で、記録自身のseqと等しい | **adoption_evidence（新規）** |
| 4 | request_basisがdictで4キー{request_id, evidence, reason_code, requested_at}ちょうど。basis.request_idが記録のrequest_idと等しく、basis.evidenceが記録のevidenceと同じ | request_basis（既存） |
| 5 | basis.requested_atが正規のUTC文字列で、記録のrequested_atと等しい | requested_at（既存） |
| 6 | basisと記録のreason_codeが両方"ADOPT_VERIFIED_PREFIX" | reason_code（既存） |
| 7 | request_hashが16進64桁で、既存`basis_request_hash(basis)`と等しい | request_hash（既存） |

採用記録は区間を変えない（GENESIS／RESTART_UNKNOWNではない）。APPLYの射影、宣言、frontierには関与しない。claimed_head_seqは壊れたファイルの宣言値なので、符号や範囲を検査しない（B-5a設計§4.4の型規則に合わせる）。

### 3.3 restore.py：復元の下限

`_check_one`で、既存の`restore_before_migration`の直後に次を加える：復元の時点のchain viewにある**最後の採用記録より前**を復元点にする復元は`restore_before_adoption`で拒否する。復元点が採用記録自身なのは可。

加えないと、採用記録を退避する復元は`_ALLOWED[kind]`のKeyErrorになり、`malformed`として拒否される。拒否はされるが理由が読めないので、明示の規則にする（B-5設計§9.2のとおり）。

### 3.4 変更しないが、採用記録にも効く既存の規則（試行で確認）

| 置き方 | 拒否する既存の規則 |
|---|---|
| SCHEMA_MIGRATIONより前 | migration_position（`check_positions`は移行前をGENESIS／APPLY／ACK／DECLAREに限る） |
| ACK／DECLAREのrequestバッチの途中 | batch |
| RECOVERY_RESTOREの窓（再生記録の途中） | restore_incomplete |
| 前の記録と同じrequest_id | request_id |
| 未知のキー・欠けたキー | record_keys |
| 親が直前の記録でない | parent |

採用記録の後に採用記録を置くこと（二度目の破損からの採用）は可。

### 3.5 \_\_init\_\_.py

`RECOVERY_PREFIX_ADOPTION`を公開名に加える（`__all__`は23名→24名）。それ以外の公開名は変えない。

## 4. 後続段階への影響

| 段階 | 変更 | 内容・理由 |
|---|---|---|
| B-2 chain.py | `_REQUEST_KINDS`に`RECOVERY_PREFIX_ADOPTION: RECOVERY_PREFIX_ADOPTION`を加える | 採用記録のIDを`request_groups`に載せ、B-2の`request_status`・B-3・B-4の既存の重複検査で`history_request_conflict`にするため。加えないと候補の検査でhistory_invalid/request_idになり、理由が変わる |
| B-2の投影・日次・ACK/DECLARE | 変更なし | 採用記録の後のAPPLYは親が採用記録になるが、S1射影は区間のAPPLYだけを再接続する（試行で確認） |
| B-3 再開始 | 変更なし | floorはAPPLY・宣言・区間だけを読む（試行で確認） |
| B-4 points.py | `check_point`の下限に`restore_invalid("restore_point", "restore_before_adoption")`を加える。比較対象は実効鎖の最後の採用記録 | B-1と同じ規則を、計画の段階で先に読める理由で返すため |
| B-4 values.py | 変更なし | `changes`の行の種別一覧（RECORD_KINDS、7種）は、復元点より後の記録の種別である。下限により採用記録は復元点より後に来ないので、8種目は現れない |
| B-5a 診断 | 変更なし | 捨てる側のitemsのkindは`v2_history.KINDS`で判定するので、B-5b後は採用記録が"?"でなく種別名で表示される。B-5a設計§6の「7種」の記述は、B-5b後は8種と読む |

B-2の公開値`read_effective(...).requests`の`record_kind`には、採用記録を含む履歴に限って値"RECOVERY_PREFIX_ADOPTION"が現れる。既存の履歴の値は変わらない。

**代替案（推奨しない）**：B-1だけを変え、B-2・B-4を変えない。既存試験の補正は少なくなる（b17のKIND_CONSTANTS、r4_09の語の例外が不要）。ただし採用記録のIDを再利用した依頼はhistory_invalid/request_idで、採用記録の前への復元はrestore_invalid/ops/restore_op_kind（またはB-1のrestore_before_adoption）で拒否され、利用者が読む理由が不正確になる。D-3で固定した境界（B-1＋B-2 chain＋B-4 points）を維持する。

## 5. v2_history_adopt

### 5.1 公開名（7名）

| 名前 | 契約 |
|---|---|
| prepare_prefix_adoption(data, adopt_count, request_id, requested_at) | READYの計画を返す |
| confirm_prefix_adoption(plan, confirmed_plan_hash, data) | CONFIRMED_IN_MEMORYまたはNO_CHANGEの結果を返す |
| AdoptionPlan | 不変の{basis, plan_hash}。B-4のRestorePlanと同じ作り（make／from_dict／to_dict／basis／plan_hash／status／committed=False、安全なrepr） |
| AdoptionConfirmResult | 不変の{status, history, plan_hash}。committed=False |
| READY、CONFIRMED_IN_MEMORY、NO_CHANGE | 状態定数（値は名前と同じ文字列） |

既存パッケージへ再公開しない。

### 5.2 prepare_prefix_adoptionの順序

| 順 | 処理 | 失敗 |
|---|---|---|
| 1 | dataは厳密に`bytes`型 | adoption_invalid/data/type |
| 2 | adopt_countは1以上の厳密整数（boolは不可） | adoption_invalid/adopt_count/type |
| 3 | requested_atは既存`requested_text`（aware datetime→UTC文字列。時計を読まない） | 既存のInputError（datetime_invalid等） |
| 4 | request_idは既存`valid_request_id` | adoption_invalid/request_id/request_id |
| 5 | 変更しない`diagnose_history_bytes(data)`。statusがPREFIX_ONLYでなければ拒否 | adoption_invalid/data/not_adoptable |
| 6 | 診断のschema_versionが2でなければ拒否（D-4、B-5のD-4） | adoption_invalid/data/schema_1 |
| 7 | adopt_countが診断のverified.countと等しい | adoption_invalid/adopt_count/count_mismatch |
| 8 | 移行の痕跡を捨てない：verified.migratedがFalseで、捨てる側に読めるSCHEMA_MIGRATION（items）があるか、捨てる側の要素にnullでない`origin`を持つdictがあれば拒否 | adoption_invalid/data/migration_discarded |
| 9 | dataをstrict UTF-8で読み、変更しない`decode_history`でHistoryにし、先頭k件から`history_dict`でヘッダーを計算し直したprefixを`validate_history`に通す（診断と同じ読み方） | 通らなければ内部の不整合：history_invalid/history/adoption_candidate |
| 10 | request_idが、prefixの物理履歴の全IDと、捨てる側itemsの読めたrequest_idのどちらとも重ならない | history_request_conflict/request_id（B-2のerrorsを再利用） |
| 11 | 採用記録を作る（§5.3）。候補＝prefix＋採用記録を`history_dict`→`History`にし、§3で採用記録に対応させた`validate_history`へ通す。候補のhead_seqがk、current_stateがprefixと同じ | 通らなければhistory_invalid/history/adoption_candidate |
| 12 | basis（§5.4）とplan_hash（`sha256_text(canonical_json(basis))`）→READY | — |

- 8の`origin`は、移行された記録が持つキーである（B-5設計第2版N-02：移行済み履歴では、originつきでMIGRATIONの無いkは検査器が拒否するので、移行の無いprefixの後ろにoriginつき記録が残る）。MIGRATIONの記録そのものの種別が壊れて"?"になった場合も、後ろのorigin記録で捨てる移行を見つけるための規則である。痕跡が全く読めない後半（要素がdictでない等）は判定できず、計画のdiscardedに"?"として残る。
- 10の物理履歴のIDは、prefixの各記録の`request_id`キーを直接読む（実効鎖でなく物理履歴全体。B-2の`request_groups`と同じ範囲）。捨てる側のIDとも重ねないのは、S3-Cの照合で後半の記録と取り違えないため（B-5設計§9.4）。
- 台帳・sessions・seriesは受け取らない。採用は市場状態と台帳の判断をしない（B-5設計§9.6）。

### 5.3 採用記録の作り方

| キー | 値 |
|---|---|
| kind | "RECOVERY_PREFIX_ADOPTION" |
| seq／parent_seq／parent_hash | k／k−1／prefixの最後の記録のevent_hash |
| evidence | raw_sha256、raw_size（診断の値）、claimed_schema_version＝2、claimed_head_seq・claimed_head_hash（診断のclaimed。不正ならnull）、discarded_from_seq＝k |
| request_basis | {request_id, evidence（同じ値の写し）, reason_code, requested_at} |
| request_hash | `basis_request_hash(request_basis)` |
| reason_code | "ADOPT_VERIFIED_PREFIX" |
| requested_at | 手順3の文字列 |
| state_after | prefixの最後の記録のstate_afterの写し |
| event_hash | 既存`compute_event_hash(rec)` |

### 5.4 計画のbasis（21キー）

| キー | 値 |
|---|---|
| operation | "soxl-v2-history-prefix-adoption-plan/1" |
| status | "READY" |
| raw_sha256、raw_size | 診断の値 |
| diagnosis_digest | 診断の`digest` |
| adopt_count | k |
| discarded | 診断のdiscarded（{from_index, count, items}）の写し |
| prefix_head_seq、prefix_head_hash、prefix_state_digest、prefix_document_digest | 診断のverifiedの値 |
| request_id、request_hash、reason_code、requested_at | 採用記録と同じ値 |
| candidate_history | 候補の`history_dict` |
| candidate_digest | 候補の`History.digest` |
| candidate_head_seq、candidate_head_hash、candidate_state_digest | 候補の`HistoryCheck`の値 |
| candidate_record | 採用記録 |

市場値は候補の中（既存のstate_after）にしかなく、basisの他のキーに新しく出さない。

### 5.5 confirm_prefix_adoptionの順序

| 順 | 処理 | 失敗・結果 |
|---|---|---|
| 1 | planがAdoptionPlan、confirmed_plan_hashが16進64桁でplan_hashと等しい。basisが21キーちょうどで、plan_hashがbasisから計算した値と一致。各値の形（operation、status、reason_code、整数・16進・日時文字列） | history_plan_mismatch |
| 2 | basisの内部の整合：candidate_historyが`validate_history`に通り、digest・head・state_digestがbasisの値と一致。最後の記録がcandidate_record、それより前のk件の`history_dict`の正規化テキストのdigestがprefix_document_digest | history_plan_mismatch |
| 3 | dataは厳密に`bytes`型 | adoption_invalid/data/type |
| 4 | **元の生バイト**：dataの診断のraw_sha256とraw_sizeがbasisと一致 → §5.2の手順5〜12をbasisのadopt_count・request_id・requested_atで作り直し、basis全体を比較 | 一致→CONFIRMED_IN_MEMORYと候補History。不一致や作り直しの失敗→history_plan_mismatch |
| 5 | **既に候補**：dataが候補の正規化バイト（`encode_history(candidate).encode("utf-8")`）とバイト単位で同じ | NO_CHANGEとそのHistory（二つ目の採用記録は作らない） |
| 6 | それ以外 | history_plan_stale |

- 4では、計画が述べることを信頼しない。元バイトから全部を作り直して比較する（B-4 confirmと同じ）。
- 5は、正規化バイトそのものだけを「既に候補」と認める。字下げなど同じ値の別表現はstaleになる（候補の書込みはS3-Cが正規化バイトで行う前提）。
- 結果のHistoryはメモリ内の候補で、committedは常にFalse。保存・公開・照合はしない。

### 5.6 エラー

| code／field／rule | 場面 |
|---|---|
| adoption_invalid／data／type | dataがbytesでない |
| adoption_invalid／data／not_adoptable | 診断がVALID、NO_VALID_PREFIX、UNREADABLE |
| adoption_invalid／data／schema_1 | v1のPREFIX_ONLY |
| adoption_invalid／data／migration_discarded | §5.2の8 |
| adoption_invalid／adopt_count／type、count_mismatch | §5.2の2・7 |
| adoption_invalid／request_id／request_id | IDの形式 |
| history_request_conflict／request_id | IDの重複（既存） |
| history_invalid／history／adoption_candidate | パッケージ内部の不整合（呼び出し側の誤りではない） |
| history_plan_mismatch／plan、history_plan_stale／plan | 確認（既存） |

例外文、生の値、パス、連鎖を出さない。既存のPersistenceErrorの型を使う。

### 5.7 依存（使ってよい既存の公開名）

- v2_history：History、validate_history、decode_history、encode_history、RECOVERY_PREFIX_ADOPTION、SCHEMA_MIGRATION。v2_history.values：history_dict。v2_history.common：is_int、is_hex64、basis_request_hash、same。
- v2_history_diagnose：diagnose_history_bytes、PREFIX_ONLY。
- v2_history_ops.errors：history_request_conflict、history_plan_mismatch、history_plan_stale。
- v2_persistence.codec：canonical_json、sha256_text、compute_event_hash。v2_persistence.errors：PersistenceError。
- v2_core.errors：CoreError（確認の作り直しで捕まえる場合）。v2_recovery.common：requested_text、is_requested_text、valid_request_id。
- 標準ライブラリ：copyだけ。生バイトのSHA-256は診断の値を使い、hashlibを使わない。

実装で実際に使うものだけimportする。既存private名（_Walk、Chain等）、テストヘルパー、旧ストア、v2_history_restore・v2_history_restart・台帳（v2_recovery.ledger等）は使わない。

## 6. 採用しても言えないこと

- 採用の候補は「prefixが検査器に通り、捨てた後半を記録で名指しした」ことだけを示す。復旧済み、追いつき済み、公開済みとは言わない。
- 捨てた後半にあったACK／DECLARE／APPLYで解決していた台帳の食い違いは、採用後のB-2投影で再び現れ得る。B-2の新規ACK／DECLARE、日次の追いつき、B-3の再開始で通常どおり処理する（B-5設計§9.6）。
- outboxや通知の意図は作り直さない。元バイトの退避と新しい正本の公開はS3-C。
- v1の破損ファイルは採用しない（schema_1）。

## 7. 既存試験の変更範囲

### 7.1 原則

- 機能試験はh02とh14の期待値だけを変える。ほかの機能試験・変異・fixtures・ヘルパーは変えない。
- 旧範囲試験4本は、それぞれの比較元（b17はadfdf765、r3_07はb328844、r4_09はd82a5ce、d5_08はac21980）からHEADまでのgit差分を監査するので、B-5bの変更を許す補正が要る。各本のSTART、test関数名、assert呼出しの数、skip等は変えない。
- 前の段階の範囲試験の差分を固定文字列で持つ箇所（r3_07のb17差分、r4_09のB17_\*／R307_\*、d5_08のPINNED）は、補正後の差分に合わせた**静的なリテラル**に更新する。試験の中で動的に生成しない。
- 補正は新しいモジュール定数を作らず、許された関数・定数の中で行う（新しい定数を作ると、その次の範囲試験の「変更箇所」の検査も広げることになるため）。

### 7.2 変更表

| ファイル | 変更箇所 | 内容 |
|---|---|---|
| tests/v2_history/test_h02_values_codec.py | test_unknown_kind_and_the_b5_kindの例の1行 | 未知種別の例の"RECOVERY_PREFIX_ADOPTION"を"CONSUME"に置き換える（未知種別の4例を保つ）。採用記録の受理はB-5bの新規試験で確認する |
| tests/v2_history/test_h14_scope_and_stop.py | test_the_public_surface_is_exactly_the_planned_one、test_consume_and_the_b5_kind_are_refused | `__all__`の期待一覧に1名を加える。KINDSの件数7→8。B-5の種別の`assertNotIn`を「KINDSの末尾がRECOVERY_PREFIX_ADOPTION」の確認に変える（CONSUMEを拒否する行はそのまま）。h14のファイル一覧の試験は変えない（§3.2で新ファイルを作らないため） |
| tests/v2_history_ops/test_b17_scope.py | KIND_CONSTANTS、FilesChanged.test_only_the_allowed_paths_differ、test_existing_tests_and_fixtures_are_untouched | KIND_CONSTANTSに8種目（chain.pyのimportと、後段の語の検査で"prefix"を種別名として扱うため）。許可パスにv2_history_adopt/・tests/v2_history_adopt/・V2_RECOVERY_S3B5B_RESULT.md、Mとして許すB-5bの既存6ファイル（v2_historyの4本、h02、h14。関数内のタプル）。\_\_init\_\_.pyの例外にv2_history_adopt/\_\_init\_\_.pyとv2_history/\_\_init\_\_.py。tests検索からtests/v2_history_adoptとh02・h14を除外 |
| tests/v2_history_restart/test_r3_07_scope.py | FilesChangedの既存の3メソッドだけ | Mとして許すB-5bの7ファイル（v2_historyの4本、chain.py、h02、h14）。新規の2ディレクトリと結果文書。\_\_init\_\_.pyの集合に2本。既存ランタイムの差分0の検索から上の5ランタイムを除外し、tests検索の期待値をh02・h14・b17の3本に。b17の固定差分（削除7行・追加25行・ハンク7）に更新 |
| tests/v2_history_restore/test_r4_09_scope.py | KIND_CONSTANTS、Runtime.test_nothing_of_the_later_stages、B17_\*／R307_\*の6定数、FilesChangedの既存の2メソッド | KIND_CONSTANTSに8種目（points.pyのimport）。後段の語"adoption"の検査で、拒否コード"restore_before_adoption"だけを例外にする。M集合にB-5bの7ファイル。新規の2ディレクトリと結果文書。\_\_init\_\_.pyの集合に2本。差分0の検索から5ランタイムを除外、tests検索の期待値にh02・h14。B17・R307の固定差分を更新 |
| tests/v2_history_diagnose/test_d5_08_scope.py | PINNED、Runtime.test_no_adoption_or_store_name_is_exported_or_defined、FilesChangedの6メソッド | PINNEDの3本の固定差分を更新。v2_history.KINDSの`assertNotIn`を「末尾がRECOVERY_PREFIX_ADOPTION」に変える（B-5aの新規ランタイムが採用の名前を定義しない検査はそのまま）。M集合・差分0の検索・blob比較で、B-5bの8ファイル（6ランタイム＋h02・h14）を例外にする。新規パスと\_\_init\_\_.py。旧3本の変更箇所の許可に、b17とr4_09のKIND_CONSTANTSと、r4_09のtest_nothing_of_the_later_stagesを加える。assertの数を正規表現でなくASTの呼出しで数える（下記） |

d5_08のassertの数え方の変更は必要な修正である。d5_08は旧3本の`self.assert…(`を正規表現で数えて比較しているが、r4_09の固定リテラル（R307_ADDED等）はr3_07の行を文字列として含むので、補正で文字列中の`self.assertEqual(`が増え、実際のassertが同じでも件数が65≠61となって失敗した。ASTのCall（属性名がassertで始まる呼出し）で数えると、3本とも補正前後で同数（b17 34、r3_07 38、r4_09 59）になる。数え方の変更は、この比較を文字列から実際の呼出しへ厳しくする方向で、検査を弱めない。

### 7.3 差分の大きさ（試行の値、c8ba08f起点、-U0）

| ファイル | ハンク | 削除行 | 追加行 |
|---|---:|---:|---:|
| h02 | 1 | 1 | 1 |
| h14 | 3 | 4 | 4 |
| b17 | 7 | 5 | 13 |
| r3_07 | 15 | 12 | 34 |
| r4_09 | 26 | 26 | 101 |
| d5_08 | 51 | 87 | 374 |

d5_08の大部分は、旧3本の固定差分（ac21980起点）を書き直したPINNEDである。r4_09がb17・r3_07の差分を、d5_08がその3本の差分を固定文字列で持つため、段階が進むたびに補正が二乗的に増える。B-5bの新しい範囲試験がこの6本の差分を同じ方式で固定すると、さらに大きくなる。B-5bでは前例どおりに補正し（D-3の案a）、次の段階（CONSUME、S3-C）の前に、連鎖を止める方式（例：旧範囲試験の差分監査を各段階の最終コミットまでに固定し、それ以降の変更は最新の範囲試験だけが監査する）を別に設計することを提案する。この方式は試行していない。

### 7.4 新しいB-5bの範囲試験が監査すること

c8ba08f起点の新しい範囲試験（tests/v2_history_adopt/）が、次を直接検査する。

- M集合が、§3・§4の6ランタイムと§7.2の6試験の12本ちょうど。ほかはすべてAで、v2_history_adopt/、tests/v2_history_adopt/、docs/implementation/V2_RECOVERY_S3B5B_RESULT.mdの中。\_\_init\_\_.pyはv2_history_adopt/\_\_init\_\_.pyとv2_history/\_\_init\_\_.py（M）だけ。
- 6ランタイムの差分を、削除行・追加行・ハンクの静的リテラルで固定する（§3・§4の意味を変えない折り返しは可）。
- 6試験の差分も同じく静的に固定し、変更行が§7.2の箇所の中にあること、test関数名・assert呼出しの数（AST）・START行・skip等が同じであることを検査する。
- それ以外（v2_core、v2_persistence、v2_recovery、v2_history・v2_history_ops・v2_history_restart・v2_history_restore・v2_history_diagnoseの残り、既存の試験・結果文書・設定・workflow・main.py・研究・STATUS等）がc8ba08fからblob単位で同じ。
- パス判定の対照：tests/v2_history_adopt/\_\_init\_\_.py、v2_history/の新ファイル、v2_history_restore/values.py、v2_history_diagnose/の変更、7本目の既存試験の変更、v1の採用経路の名前を拒否する。

## 8. 一時環境での試行（2026-11-02、Linux）

**位置づけ**：設計の確からしさと既存試験の補正範囲を確かめるための使い捨ての試行である。c8ba08fから作ったローカルの作業ツリーに、§3・§4の6ランタイムの変更と§7.2の6試験の補正、新パッケージ・新試験・結果文書の位置だけを示す空のプレースホルダー3本を置き、pushしないローカルコミットで試験した。v2_history_adoptの計画・確認は作っていない。正式な実装、受入試験、レビューの代わりにしない。

環境：Linux、Python 3.13.18、`PYTHONDONTWRITEBYTECODE=1`、`-B -W error::ResourceWarning`。Windows、他のPythonの版、unshareによる通信遮断は実施していない。

| スイート | 開始点c8ba08f | 6ランタイムだけ変更 | 補正後 |
|---|---|---|---|
| コア tests/v2_core | 197 OK | 197 OK | 197 OK |
| 保存 tests/v2_persistence | 170 OK | 170 OK | 170 OK |
| S2 tests/v2_persistence_local | 113 OK（skip 4） | 同じ | 113 OK（skip 4） |
| S3-A tests/v2_recovery | 176 OK | 176 OK | 176 OK |
| B-1 tests/v2_history | 230 OK | 失敗4（h02 1、h14 3） | 230 OK |
| B-2 tests/v2_history_ops | 173 OK | 失敗4（b17） | 173 OK |
| B-3 tests/v2_history_restart test_r3_\* | 109 OK | 失敗2（r3_07） | 109 OK |
| B-4 tests/v2_history_restore test_r4_\* | 165 OK | 失敗4（r4_09） | 165 OK |
| B-5a tests/v2_history_diagnose test_d5_\* | 131 OK | 失敗5（d5_08） | 131 OK |
| 合計 | 1464 | 失敗19 | **1464件合格（skip 4はWindows専用）** |

「6ランタイムだけ変更」の列は、h14のファイル一覧の失敗を避けるため採用記録の検査をview.pyに置いた最終形とは別に、最初に新モジュールで試した版の値を含む（h14の失敗3のうち1件）。最終形の試験はこの表の「補正後」の列である。試行の最後に、evidenceのraw_sizeの下限を0から1に直し、B-1〜B-4を再実行して合格した（d5_08はランタイムの中身を固定しないため再実行の対象外）。

採用記録の振る舞いの確認（使い捨てプローブ、32項目、すべて期待どおり）：

| 確認 | 結果 |
|---|---|
| GENESIS＋APPLY3件の末尾のevent_hashを壊す→B-5a診断 | PREFIX_ONLY、count＝3 |
| prefix＋採用記録の候補 | validate_historyを通る。候補の正規化バイトの診断はVALID |
| 採用後にB-2の日次（D3） | 通る。新しいAPPLYの親は採用記録 |
| 採用後にB-3の再開始 | READY。採用記録のIDの再利用はhistory_request_conflict |
| 採用記録を復元点にするB-4（REAPPLY／DROP／REAPPLY） | READY→確認CONFIRMED_IN_MEMORY、候補は検査を通る。消費済みの判断がある日を含む場合は既存のrestore_requires_consume |
| 採用記録より前を復元点にするB-4 | restore_invalid／restore_point／restore_before_adoption |
| 手で作った、採用記録より前への復元（B-1） | history_invalid／restore_before_adoption |
| 採用記録のIDを再利用するB-2のACK計画、B-4の計画 | history_request_conflict |
| state_after違い | state_after |
| discarded_from_seq違い、claimed_schema_version＝1、raw_size＝0、claimed_head_seqがbool | adoption_evidence |
| basisのevidence違い／request_hash違い／reason_code違い／requested_at違い／余分なキー | request_basis／request_hash／reason_code／requested_at／record_keys |
| 親が直前でない | parent |
| 前の再開始のIDの再利用 | request_id |
| requestバッチの途中／MIGRATIONより前／復元の窓の途中 | batch／migration_position／restore_incomplete |
| 採用記録の後の採用記録 | 通る |
| example_mのSCHEMA_MIGRATION（seq7）のkindを壊したバイトの診断（§5.2の8の前提） | PREFIX_ONLY、count＝2、migrated＝False。捨てる側はseq2〜6（originつきのACK／APPLY／DECLARE）とseq7の"?"。後ろのoriginで移行の痕跡を判定できる |

試行の差分（6ランタイムと6試験、1230行）は、同じ資料コミットのdocs/specs/V2_RECOVERY_S3B5B_SCOPE_TRIAL_20261102.diffに参考として保存する（未適用。SHA-256 3b4f34171031923db88ef576a28ef819396fe1c2be1299b4efa808ac04e68267）。実装者はこれを写すのではなく、§3・§4・§7.2の規則に従って作り、違いがあれば結果文書で説明する。

## 9. B-5bの最小受入例

| 例 | 期待 |
|---|---|
| GENESIS＋APPLY3件の末尾のevent_hashを壊したバイト、adopt_count＝3 | READY。候補はprefix3件＋採用記録（seq3）。候補の正規化バイトの診断はVALID |
| 同じ計画を同じバイトで確認 | CONFIRMED_IN_MEMORY。候補が計画と同じ |
| 候補の正規化バイトで確認 | NO_CHANGE |
| 別のバイト（1バイト違い、字下げした候補）で確認 | history_plan_stale |
| basisやplan_hashの改ざん、candidate_recordの差し替え | history_plan_mismatch |
| VALID、NO_VALID_PREFIX、UNREADABLEのバイト | adoption_invalid／data／not_adoptable |
| v1の末尾改ざん（PREFIX_ONLY） | adoption_invalid／data／schema_1 |
| adopt_countが診断のcountと違う、bool、0 | count_mismatch／type |
| example_mのMIGRATIONだけを壊したバイト（count＝2、捨てる側にMIGRATION） | migration_discarded |
| 同じ入力で、MIGRATIONの記録のkindも壊して"?"にしたもの | migration_discarded（後ろのoriginで判定） |
| prefixのIDの再利用、捨てる側の読めるIDの再利用 | history_request_conflict |
| 採用後のB-2日次、B-3再開始、B-4復元（採用記録を復元点に） | 通る（§8の確認と同じ） |
| 採用記録より前を復元点にするB-4 | restore_before_adoption |
| §3.2の各ruleを1つずつ壊した採用記録 | 該当するrule |

## 10. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | 変更範囲：既存ランタイムの変更をB-1（values・view・restore・\_\_init\_\_）、B-2 chain.pyの`_REQUEST_KINDS`、B-4 points.pyの`check_point`の6ファイルに限り、§3の検査規則（新rule adoption_evidence、restore_before_adoption、順序、raw_size≥1、claimed_head_seqに符号の検査なし）と、採用記録の検査をview.py内に置く（新ファイルを作らない）こと | 採用を推奨。B-1だけを変える代替案（§4）は、理由の読みやすさが下がるので推奨しない |
| D-2 | 採用の条件と計画・確認：PREFIX_ONLY・版2・adopt_count一致、移行の痕跡（読めるMIGRATIONまたはorigin）を捨てない、IDは物理prefixと捨てる側の読めるIDの両方と重ねない、台帳を使わない、basis21キー、確認は元バイトなら作り直して比較・候補の正規化バイトならNO_CHANGE・他はstale、hashlibを使わない（§5） | 採用を推奨 |
| D-3 | 既存試験の補正：(a) 前例どおり、h02・h14と旧範囲試験4本を§7.2の箇所だけ補正し、固定リテラルを更新する。d5_08のassertの数え方をASTにする。新しい範囲試験が§7.4を監査する。(b) 連鎖を止める方式を先に設計してからB-5bを実装する | (a)を推奨（試行で全件合格）。連鎖を止める方式は、次の段階の前に別に設計することを提案（本採否には含めない） |
| D-4 | B-5bの実装担当 | Sonnet 5.5・high。境界・規則・既存試験の補正箇所を固定し、試行の差分も参考に付けた。検査器の変更を含むが、規則の新設は1つ（adoption_evidence）と下限1つで、会計・戦略・保存方式の再設計を含まない。矛盾や規則の追加が必要なら止めて主担当へ返す |

D-1〜D-4を一組で判断する。今回の文書作成と一時環境の試行は採用ではない。B-5aの受領をB-5bの実装承認にしない。CONSUME、S3-C、全体稼働、本番保存先・資格情報は今回の採否に含まない。

## 11. 作業記録

- 担当モデル：セッション情報で configured_model `claude-opus-5-5[1m]`、last_served_model `claude-opus-5-5`、effort_level `high`を確認した（このスレッドの開始時）。
- 開始時（2026-11-02T08:20Z）に、B-5a依頼§8の56参照＋資料ブランチdocs/v2-history-s3b5-20261102の第2版5c9e1e8＋再レビュー6a7210c＋B-5a実装c8ba08f＋B-5aレビュー808ffbdの計60参照を、`git ls-remote`の完全SHAで照合し、60件とも一致した。
- 本書、依頼書、試行の差分の3ファイルだけを、コード開始点c8ba08fから作った新しい資料ブランチdocs/v2-history-s3b5b-20261102に追加した。製品コードの変更、PR、Actions、送信、新しい市場計算は0。一時環境の試行は§8のとおりで、その作業ツリーとローカルコミットはpushしていない。終了時の照合結果と完全SHAは完了報告に記す（本書はその値を含められない）。
- モデル別の利用量は未計測。

## 12. B-5aレビューの提案P-01の扱い

B-5aレビュー（808ffbd）§5の提案P-01（B-5a結果文書§7の「検査260回」は、失敗するprefix検査が260回、prefixの検査は261回、全体検査を含むvalidate_historyの呼出しは合計262回）は、B-5a結果文書を追記しない方針のため、B-5bの結果文書の「前段階の記録の訂正」として1行で記すよう依頼書§7に入れた。B-5aの製品コードと試験は変えない。
