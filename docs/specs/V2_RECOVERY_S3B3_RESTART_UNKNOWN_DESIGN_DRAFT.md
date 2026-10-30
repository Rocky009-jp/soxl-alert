# V2 S3-B-3 UNKNOWN再開始の計画・確認 設計案

作成日：2026-10-30（日本時間）。版：第2版（同日のレビューN-01〜N-03と提案P-01〜P-05を反映、§13）。
状態：**第2版・レビュー待ち。B-3限定実装は未承認。**
今回のユーザー指示は設計書と限定実装依頼書の作成までである。実装への移行、保存・公開・本番の採用は別の判断とする。

## 1. 目的・固定入力

B-3は、検証済みschema_version=2履歴にRESTART_UNKNOWNを1件足す計画と、そのhashを指定したメモリ上の確認だけを実装する案である。市場状態を初期UNKNOWNへ戻し、resume_afterより後から日次処理を再開できる候補を作る。過去の記録・確定入力・ACK・欠測宣言を消したり退避したりしない。

| 用途 | 固定版 |
|---|---|
| コード開始点 | **b328844fdeda235cf95bf7851ba9e3d7d55aa7bb**（fix/v2-history-s3b2-review-20261030）。コード・試験は4ed0c364bcc1c63b44be07349880b741936d8b77と同じ |
| 本書初版 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c、設計blob fdf9a995957acc9b4e442fad83e85cbb9ddc755b |
| 初版レビュー原文 | 同じ固定コミットのdocs/reviews/V2_RECOVERY_S3B3_REVIEW_20261030.md。重大0・通常3・提案5。N-01の実行による確認はレビュー担当の報告 |
| B-2修正受領 | 5743732781523ab60f1025037d99410a41285de8、docs/reviews/V2_RECOVERY_S3B2_FIX_RECEIPT_20261030.md |
| B-2設計第2版 | e083cd3187f17692cb081fcc1031b09551fb8cb7、docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md、blob 988258c798ee2d867c86238db1c4f426a360dda2 |
| S3-B設計第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md、blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7。特に§3.3、§7、§9 |
| 上位第4版 | e3e90947a718cca877b543739ca60539207ca7a7、docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md。§2.6〜2.8、R-4、RT-04／RT-09 |

本書は上記GitHub固定版とコードの読解に基づく。今回の作成ではコード・試験・再現スクリプトの作成や実行、新しい市場計算は行っていない。CLAUDE.md、STATUS、MODEL_POLICY、ROADMAPの該当箇所を確認した。STATUSは2026-10-27時点の記録であり、B-2までの採用・受領を取り消すものとして扱わない。

## 2. 範囲と既存コードへの影響

### 2.1 含めるもの

- 新パッケージv2_history_restartのprepare_restart_plan／confirm_restart_planと、不変なRestartPlan／RestartConfirmResult。
- 注入sessionsと明示check_d／resume_afterの検査、有効履歴全体からのfloor、物理履歴全体のrequest_id検査。
- B-2のproject_history_ledgerによる元履歴の全区間照合。新記録の候補全体は変更しないvalidate_historyに通す。
- 同じ計画を、その候補そのものに対して再確認した場合のNO_CHANGE。
- B3-01〜B3-16の試験と限定欠陥注入。

### 2.2 含めないもの

B-4（復元計画、CONSUME）、B-5（破損診断、prefix採用）、S3-C（保存・公開・CAS・照合・解錠）、新ストア、HistoryReplacement、通知・outbox、CLI、自動対象日・追いつき、実時計・乱数・ネット・口座接続は作らない。
壊れた履歴を初期化して検査を回避する経路、消費済みdecisionの訂正、APPLYの再計算式の複製も作らない。
LedgerContext自体の不変化はB-2受領判断どおり追加しない。

### 2.3 候補Historyまでとする提案（D-1に含む）

上位§9のHistoryAppendBatchの一般化はS3-Cに残す。B-2のHistoryAppendBatchとcheck_append_batchはDAILY／RESOLUTION専用で、RESTARTを受け付けない。B-3で別のバッチ・別の保存用checkerを並行して増やしたり、RESTARTをRESOLUTIONと偽ったりしない。

B-3の確認結果は、B-1の移行確認と同様に**候補Historyだけ**を持つ。batch属性を持たず、committed／committableは常にFalse。上位§2のB-3の「計画・確認」は満たし、上位§9の保存用バッチの統合は未達として明記する。B-2のR-a採用を取り消す提案ではない。

S3-Cは、確認済み計画のexpected_head_seq／hash、candidate_digest、plan_hashと、候補末尾のRESTARTから公開用バッチを組み立てられる。バッチ化のためだけにprepareを再実行する必要はない。ただし、公開時のロック下での期待先頭・計画・候補の再検査や成否照合はS3-Cで別途設計し、B-3の確認だけで保存権限や保存成功を与えない。

### 2.4 既存の範囲試験に必要な最小補正

B-2のtests/v2_history_ops/test_b17_scope.pyは、adfdf765からHEADのGit差分をB-2の場所だけに限り、末尾ではB-2以外の__init__.pyの追加も禁止している。このままでは正当な新規B-3ファイルも失敗になる。
D-1の採用後に限り、この1ファイルのFilesChanged内で次の**3点だけ**を変える。

1. test_only_the_allowed_paths_differの許可リスト：新規v2_history_restart/、tests/v2_history_restart/、新結果文書docs/implementation/V2_RECOVERY_S3B3_RESULT.mdだけを足す。
2. test_existing_tests_and_fixtures_are_untouched：Git検索から新規tests/v2_history_restart/も除外する。
3. test_only_the_allowed_paths_differ末尾の__init__.py検査：**v2_history_restart/__init__.pyという単一パスだけ**を追加例外にする。既存パッケージの__init__.pyの変更や、それ以外の新規__init__.pyは従来どおり拒否する。tests/v2_history_restart/には__init__.pyを作らない。

それ以外の行、B-2ランタイムの後工程禁止・公開名・importの試験、既存の機能試験・期待値は変更しない。B-3側の新規範囲試験でこの3点の差分を厳密に照合し、新規B-3ランタイム全体をASTで検査する。旧試験をskipしたり、GitのHEADを偽って合格させたりしない。

将来のB-4／B-5／S3-Cで新規ディレクトリを足すと、B-2とB-3のHEAD差分の範囲検査には再度見直しが必要になる（P-02の留保）。今回は後工程を先回りして許可リストへ入れず、共通一覧への再編も実装しない。各段階で変更対象を明示する。

## 3. 公開APIと再利用

| 名前 | 契約 |
|---|---|
| prepare_restart_plan(history, resume_after, sessions, raw_observations, check_d, request_id, requested_at) | READYのRestartPlan。requested_atは注入されたaware datetime。reason_codeは内部でRESTART_UNKNOWNに固定 |
| confirm_restart_plan(plan, confirmed_plan_hash, history, sessions, raw_observations) | CONFIRMED_IN_MEMORYまたはNO_CHANGEのRestartConfirmResult |
| RestartPlan | from_dict／to_dict／basis（写し）／plan_hash（常に写し）／status／committed=False／summary／安全なrepr |
| RestartConfirmResult | status、history（候補Historyまたは再確認時の現在History）、plan_hash、committed=False、committable=False。batch・ledger属性は持たない |
| 定数 | READY、CONFIRMED_IN_MEMORY、NO_CHANGE。既存と同じ文字列 |

v2_history_restart.__all__は上の2関数・2型・3定数の7名。既存パッケージの__init__.pyへ再公開しない。

利用する既存公開名：
- v2_history：History、validate_history、HistoryCheck、Boundary。values：history_dict、check_json、種別定数。common：basis_request_hash、is_int、is_hex64、is_date、same。
- v2_history_ops：read_effective、project_history_ledger、HistoryLedger。errors：history_plan_mismatch、history_plan_stale、history_request_conflict。
- v2_recovery.ledger：copy_sessions、parse_ledger、ledger_digest、sessions_digest。common：requested_text、is_requested_text、valid_request_id。
- v2_persistence.codec：canonical_json、sha256_text、compute_event_hash。events：session_dict。errors：PersistenceError。
- v2_core：MarketState、SessionList。fixture：parse_iso_date。errors：CoreError、InputError、ConflictError。
- 標準ライブラリcopy／json。依存追加なし。

private名、Ctx／SnapshotViewの属性を模した代用品、B-2のChain／ledger_ofや_Frozenなどの内部名は使わない。初期状態はMarketState.initial().to_dict()から得る。戦略式・閾値・状態式を新たに書かない。

## 4. 準備の順序と境界

prepare_restart_planは次の順序を固定する。

1. validate_history(history)。sessionsをcopy_sessions、check_dをtarget_session_dateのfield、resume_afterをresume_afterのfieldで日付解析し、台帳各行をparse_ledgerで独立して解析する。
2. check_dがsessionsに存在・confirmed=True・前後のセッションあり、resume_afterがsessionsに存在・confirmed=Trueであること。check_dの次セッションは存在すればよく、confirmedは求めない。resume_afterはcheck_dと同じでもよい。
3. requested_text、request_idの形を検査。§6のrequest_basis／request_hashを作り、物理履歴全体のrequest_idを照合。既存IDは§7どおり拒否する。
4. §5のfloorと上限・無効果の検査を行う。
5. **元履歴**についてproject_history_ledger(history, sessions, raw_observations, check_d)を呼ぶ。全区間の境界・APPLY・skipped・宣言のセッション範囲と、除外→補完→version_selection→最終検査をそのまま再利用する。返るエラーは変更せず、未解消の台帳不一致を再開始で消さない。
6. RESTART_UNKNOWNを1件組み立てる。candidate=History.from_dict(history_dict(元events+[新記録]))。
7. validate_history(candidate)と§8の保存内容の不変検査を通す。basisを作りplan_hashを計算し、READYを返す。

上の順序を維持し、エラーの優先順位を次の表で固定する。sessions自体の構造検査と、保存済みセッション文脈との差の検査は別の段階である。

| 優先順 | 検査 | 主な拒否 |
|---|---|---|
| 1 | 元履歴そのもの→copy_sessions→check_dとresume_afterの日付解析→台帳各行の解析 | 既存history_invalid／unsupported_schema、sessions_invalid等、日付・台帳行のInputError |
| 2 | check_dの存在→confirmed→next→previous、その後resume_afterの存在→confirmed | check_dの既存InputError、resumeのrestart_invalid／resume_after／restart_boundary |
| 3 | requested_at→IDの形→物理履歴全体のID照合 | 日時の既存InputError、restart_invalid／request_id／request_id、history_request_conflict |
| 4 | floorの下限→resume_after<=check_d→無効果 | restart_invalid。field／ruleは§5・§10 |
| 5 | 元履歴のB-2投影。元境界・旧APPLY／宣言の保存文脈と現在のsessionsの照合、除外・補完後の版と台帳の最終照合 | session_context_missing／mismatch、ledger_mismatch、late_observation、resolution_invalid／version_selection等の既存エラー |

不正な台帳行やsessionsの構造の不正はID照合より前に止まる。一方、形は正しいsessionsと旧境界・旧APPLY文脈のずれは手順5なので、使用済みIDと重なれば**history_request_conflictを優先する**。同じsessionsで未使用ID・有効なfloorを指定した対照はsession_context_mismatch等で止まる。
既存の再開始日＝check_dの場合も、ID再利用はfloor／元履歴投影より前にhistory_request_conflictとなる。B-2は文脈照合がIDより前であり、この重複エラー時の優先順位はB-2と異なる。

## 5. floor・開始位置・無効果

floorは**現在の有効履歴全体**（退避記録を含めない）から計算する。

| 項目 | 内容 |
|---|---|
| last_apply_d | HistoryCheck.latest_apply_d。全区間の最新APPLY日、無ければnull |
| last_declared_d | read_effective(history).resolutionsの有効DECLARE_MISSINGの最大d、無ければnull |
| prev_boundary | HistoryCheck.current_boundary.after |

resume_after ≥ floorの非null値の最大、resume_after ≤ check_dを要求する。下限未満はrestart_invalid／resume_after／restart_floor、上限超過はrestart_invalid／check_d／check_d。
親のcurrent_stateが初期状態そのもので、resume_after==prev_boundaryならrestart_invalid／resume_after／restart_noop。状態が初期でも境界を前進させる再開始は許す。比較は正規化した値で行う。

過去の宣言やAPPLYを有効履歴に残す。旧区間の台帳照合も続く。resume_after以前の未適用・無所属の日を自動で消費せず、明示指定した境界より後から処理する。台帳行を削除・除外する操作ではなく、ACKや欠測宣言を暗黙に作らない。

利用者へ説明する意味として、旧区間のledger_mismatch／late_observation等が未解消なら、先にB-2のACK等で解決する必要がある。最後のAPPLYとresume_afterの間に無所属のdecisionがあっても、その日を自動適用しない（解析と衝突の検査は続ける）。
またresume_after==check_dで再開始した後は、そのcheck_dで新しいACK／DECLAREは作れずtarget_not_after_boundaryになる。境界より後でconfirmed=Trueのセッションを新たなcheck_dとして明示し、前後のセッション等の条件も満たしてから、新しいACK／DECLAREを作る。B-3がcheck_dを自動で進めることはない。

## 6. 記録・hash・計画の全キー

### 6.1 RESTART_UNKNOWN（既存の15キー）

kind=RESTART_UNKNOWN、seq=元head_seq+1、parent_seq=元head_seq、parent_hash=元head_hash、
resume_after、boundary_session（注入sessionsの同日のsession_dict）、floor、
request_id、request_hash、request_basis、reason_code=RESTART_UNKNOWN、requested_at、
replay_of=null、state_after=MarketState.initial().to_dict()、event_hash。

request_basisは5キー：request_id、resume_after、check_d、reason_code、requested_at。
request_hash=basis_request_hash(request_basis)（requested_atだけ除く）。
event_hash=compute_event_hash(記録)。plan_hashやbatch_hashは記録へ入れない。
親はAPPLYに限らず、ACK／DECLARE／RESTORE／MIGRATION／RESTARTが物理先頭でも、その物理先頭を指す。

### 6.2 RestartPlanのbasis（20キー）

operation="soxl-v2-history-restart-plan/1"、status=READY、
history_digest、expected_head_seq、expected_head_hash、expected_state_digest、
resume_after、check_d、request_id、request_hash、reason_code、requested_at、
floor、boundary_session、ledger_digest、sessions_digest、effective_digest、
candidate_history、candidate_digest、candidate_state_digest。

ledger_digest／sessions_digest／effective_digestは§4手順5の**元履歴の照合**の値。expected_state_digestは元の市場状態、candidate_state_digestは初期状態の正規化JSONのhash。candidate_historyは候補のdict。
値は{basis, plan_hash}、plan_hash=SHA-256(正規化JSON(basis全体))。
同一入力・同一requested_atなら同一plan_hash。時刻だけ変えるとrequest_hashは同じだが、記録hashとplan_hashは変わる。

## 7. IDと再確認の方針案（D-2）

**prepareでの既存request_idはすべてhistory_request_conflict／request_id。** read_effective.requestsで物理履歴全体を調べ、有効・退避・MIGRATED・REPLAYED・他種別・内容一致・時刻だけの相違を問わない。未使用IDだけが新しいREADYを作れる。IDを変えて自動再試行しない。

B-2の同ID同内容で新しいNO_CHANGE計画を作る契約とは異なる。状態を初期化するB-3は、**元の計画と確認hashを保持して再確認する経路**に限定する案である。同じ計画を候補そのものに対して確認すれば§9のNO_CHANGEになる。新しいprepare呼出しの同ID再提出と、既存計画の再確認を混同しない。
この厳しい方針は上位に未指定の詳細なので、未採用の提案としてD-2で判断する。採用前にB-2へ合わせて独断で変更しない。

保存の成否が不明な場合の計画保持と、ALREADY_PUBLISHED等に相当する照合は**S3-Cの責任**として留保する。同じIDのprepareがconflictになったこと、または保持した計画でも候補の後に日次記録等が増えてstaleになったことだけで、「保存されていない」と断定しない。B-3は自動でIDを替えて再実行しない。
P-01の追加案であるconflictのrule細分化は、S3-Cの案内・照合契約と合わせて再検討する。今回はhistory_request_conflict／request_idを維持し、新しいruleや照合実装は足さない。

## 8. 候補の全体検査とresume_after==check_d

元履歴の投影、候補の完全な履歴検査に加え、次をすべて比較する。

- candidate.events[:-1]が元history.eventsと完全一致し、新しい末尾は§6.1どおり1件だけ。
- candidateの有効seqは元の有効seq列＋新seq。退避seq列は元と同じ。
- 新しい境界は新seqのRESTART_UNKNOWNとresume_after、現在状態は初期状態。
- 新記録のboundary_sessionは今回注入した同日のconfirmedなセッションと完全一致。
- 元のAPPLY、skipped、ACK、宣言、各参照、migrationの情報が変わらない。

**候補へcheck_dを日次対象として投影し直すことは要求しない。** resume_after==check_dは上位で許されるが、B-2の候補投影はtarget_not_after_boundaryで止まるためである。check_dをnext(check_d)へずらしたり、未確定の未来セッションを作ったり、LedgerContextの境界を偽ったりしない。

本操作は新しい除外・補完・APPLY・宣言を足さず、既存の事実をそのまま残す。したがって、全区間の台帳照合は**元履歴の既存B-2投影＋履歴・事実の完全保存＋新境界の実sessionsとの一致**で確かめる。候補の構造・状態・floorはvalidate_historyで完全検査する。日次候補に新しいAPPLYを足すB-2の契約とは、検査対象を区別する。

## 9. 確認の順序と同じ計画の再確認

confirm_restart_planの順序：

1. RestartPlanの型、外形{basis,plan_hash}、basis20キー、operation／READY／reason、hash、confirmed_plan_hash、request_id／日時／日付／floor／boundary_sessionの形を検査する。expected_head_seqと候補header・記録の整数は厳密なint（bool／float拒否）。候補Historyを検査し、candidate_digest／state_digest・初期状態・末尾種別・元head+1の長さを確かめる。失敗はhistory_plan_mismatch／plan。利用者指定のhashだけで候補を信頼しない。
2. 今回の入力そのものをvalidate_history、copy_sessions、parse_ledgerで検査する。不正な入力は既存のエラーを優先する。この段階で今回の履歴へcheck_dを投影しない。
3. ledger_digest／sessions_digestがbasisと一致し、次のAまたはBに当たるかを確認。不一致はhistory_plan_stale／plan。
4. 元履歴から§4を作り直し、**元のbasis全項目と完全一致**を要求する。不一致・digest一致後の再構築CoreErrorはhistory_plan_mismatch（連鎖抑止）。候補の各項目や表示された値だけの比較で代用しない。

| 枝 | 現在の履歴 | 再構築と結果 |
|---|---|---|
| A | digestとhead_seq/hashがbasis.history_digest／expected_head_*と一致 | 現在の履歴を元履歴として再構築。CONFIRMED_IN_MEMORY、候補History |
| B | 現在の履歴がbasis.candidate_historyそのもの。digest・head・全内容が一致し、元head+1のRESTARTが末尾 | 下記のprefixから元履歴を復元して再構築。NO_CHANGE、現在Historyを返す。2件目のRESTARTを作らない |

枝Bの元履歴は、今回のeventsの先頭からexpected_head_seqまでを残し、history_dictでヘッダーを作ったHistory。**必ずvalidate_historyを通し、元のhistory_digest・head・state_digestとも一致させる**。物理prefixであり、現在の有効seqだけをつないで再構成しない。元の退避記録・移行記録も残す。
そのprefixを§4へ渡せばcheck_dは元の境界の後であり、resume_after==check_dでも元履歴の照合を正しく再実行できる。

B-2の再確認の「basisの4項目をNO_CHANGEに変える」方式は使わない。B-3の計画はREADYだけで、枝Bでも**元のbasisそのもの**を再構築して比較する。現在の履歴が候補より1件でも先に進んでいればstale。保存の成否の照合やALREADY_PUBLISHEDはS3-Cに残す。

## 10. 不変性・表示・エラー

from_dictは外形とJSON互換性だけを検査し、深さ・型の検査をコピーより前に行う。JSONの深さ超過、巨大整数、非有限float、非JSON型はrestart_invalid／plan、rule=json_depth／json_number／json_key／json_type等の固定名。外形不正はrule=plan_shape。整数欄のTrue・1.0はJSONとして読み込み、確認の手順1でmismatchとする。
内部は正規化テキストを値の同一性とし、全アクセサで内部の可変参照を出さない。未検証のplan_hashがdict／listでも必ず写しを返す。外部private属性を書き換えるコードへの防御を主張しない。

summaryの許可リスト：status、request_id、resume_after、check_d、floorの3日付、expected_head_seq、candidate_head_seq、new_records=1、plan_hash、committed=False、committable=False。値を表示する前にそれぞれ形で再検査し、任意の値をstr／reprへ直接渡さない。不正な計画のreprはRestartPlan(?)、summaryはrestart_invalid／plan／plan_shape。確認結果のreprは固定statusとcommitted=Falseだけ。
URL、note、source_url、F&G値、台帳行、パス、例外の自由文を表示へ出さない。

| 条件 | code／field／rule |
|---|---|
| planの読込・表示の不正 | restart_invalid／plan／plan_shapeまたはjson_* |
| 確認時の計画の不正・再構築不一致 | history_plan_mismatch／plan |
| 正常な入力のdigest・head差 | history_plan_stale／plan |
| prepareで既存ID | history_request_conflict／request_id |
| request_idの形が不正 | restart_invalid／request_id／request_id |
| resume_afterのセッションが無い・未確定 | restart_invalid／resume_after／restart_boundary |
| floor未満 | restart_invalid／resume_after／restart_floor |
| 無効果 | restart_invalid／resume_after／restart_noop |
| resume_after>check_d | restart_invalid／check_d／check_d |
| check_dの不存在・未確定・前後不足 | 既存InputErrorのtarget_not_in_sessions／target_unconfirmed／previous_session_missing／next_session_missing、field=sessions（前後両方不足時はnextを先に検査） |
| 元履歴の投影・入力の不正 | 既存の履歴・sessions・台帳・範囲照合のエラーのまま |
| 元履歴または候補のvalidate_history失敗 | 既存history_invalid／history等のまま。正常履歴への依頼の指定ミスと区別する |

prepareの指定ミスはrestart_invalid、入力履歴そのものの検査失敗はhistory_invalid等と分類する。候補のvalidate_history失敗は計画を返さず、実装内部の不整合として既存エラーを保つ。確認時の未検証plan内の候補の不正は§9手順1のhistory_plan_mismatchであり、今回の入力履歴の破損とは区別する。B-1の検査器やそのruleは変更しない。

## 11. 具体例・対照

日付D0,D1…は注入した合成の連続セッション。下記は実測結果ではなく実装時の受入期待。

### 11.1 例Uを実際の計画から作る

0 GENESIS D0／1 APPLY D1／2 APPLY D2。
prepare(resume_after=D3,check_d=D3,未使用r1)はREADY。確認で#3 RESTART、floor={last_apply_d:D2,last_declared_d:null,prev_boundary:D0}、初期状態。元の3件は同じまま。
同じ計画を候補へ再確認するとNO_CHANGE。候補で同IDの新しいprepareを呼ぶとhistory_request_conflict。
候補へ既存B-2の日次を接続し、D2/D3はtarget_not_after_boundary、D4のF&G>=30はstreak=1・armed=UNKNOWN・gap=false。25未満／25以上30未満も上位例Uの期待どおり。D4なし→D5ありならD4はNO_COMMIT、D5のskipped=[D4]・gap=false。後からD4決定が来ればlate_observation。

### 11.2 floorと無効果

- GENESISだけ、resume_after=D0 → restart_noop（check_d=D1等）。resume_after=D1かつcheck_d=D1 → READY、境界を進める。
- 旧区間にAPPLY D1・DECLARE D2、新しい境界D3がある場合のfloorは{D1,D2,D3}。resume_after=D2はrestart_floor。
- 初期状態であっても、DECLAREが新たに有効ならlast_declared_dを無視しない。
- 退避したDが有効履歴の最新Dより後にある場合、それをfloorへ含めない。既存例R等から組立て、退避済み最大日と有効最大日が異なるケースを使う。
- 旧APPLYの台帳変更や旧skipped／宣言日の後発は、再開始しても元履歴の投影で止まる。既存B-2の明示ACKで解決した履歴なら計画を作れる。

### 11.3 親・移行・復元

親がACK／DECLARE／MIGRATION／RESTORE／RESTARTの各ケースで物理先頭を使う。例Mに再開始を足した後もmigrated_sourcesの元v1二値のdigestは同じ。例Rの退避記録は復活させず、使用済みq1〜q6等のIDを再利用しない。
B-2 R-03のDROPした末尾宣言の反例も使い、退避した宣言からfloorやセッション制約を増やさない。

## 12. 受入条件・変更境界・判断

受入B3-01〜B3-16と限定欠陥注入の詳細は、同じ版のdocs/tasks/V2_RECOVERY_S3B3_LIMITED_IMPLEMENTATION_REQUEST.mdに固定する。新規試験数Nは実測する。

実装を許すのは、採用後の新規v2_history_restart/、tests/v2_history_restart/、docs/implementation/V2_RECOVERY_S3B3_RESULT.mdと、§2.4の範囲検査1ファイルの限定補正だけ。既存ランタイムは全て無変更。既存B-2の公開面・バッチ値も無変更。

| 判断 | 推奨案 | 状態 |
|---|---|---|
| D-1 | 本書のB-3限定範囲を採用。候補Historyまで、新規パッケージ、旧範囲試験1ファイルの明記した3箇所だけを補正 | 未採用 |
| D-2 | prepareの既存IDは一律conflict。同じ元計画の再確認だけがNO_CHANGE | 未採用 |
| D-3 | 実装はClaude Sonnet 5.5、effort high。固定した純粋な計画・確認・回帰の実装として推奨 | 未採用 |

この3点の採用とB-3限定実装の明示指示を得た後だけ着手する。モデル実設定はセッション情報で確認し、プロンプトに書いたことで設定できたと断言しない。現時点で実装・試験は未着手。

## 13. 第2版の改訂とレビュー記録

初版f90c2e6へのClaudeレビュー（重大0・通常3・提案5）を受領した。原文をdocs/reviews/V2_RECOVERY_S3B3_REVIEW_20261030.mdへ取得した本文のまま保存する。N-01の一時作業ツリーでの実行はレビュー担当の報告であり、本補正の作成担当が実行した試験へ置き換えない。本補正も文書だけで、コード・試験実行・再現コード作成は0。

| ID | 対応 |
|---|---|
| N-01 | §2.4・D-1を3点の補正へ修正。3点目は新ランタイムの__init__.pyの単一パスだけを例外にする。tests側には__init__.pyを置かない |
| N-02 | §5・§10でprepareの指定ミスをrestart_invalidへ分離し、fieldとruleを固定。B-1検査器のhistory_invalidは変更しない |
| N-03 | §4へ5段階の優先順位と、旧文脈差＋使用済みIDのconflict／未使用IDの文脈エラーの対照を追加。検査順は変えない |
| P-01 | §7へ成否不明時の計画保持・公開後照合をS3-Cへ留保する旨を追加。任意のrule細分化は留保 |
| P-02 | §2.4へ後工程で旧範囲検査の見直しが再び必要になる点を記録。後工程の自動許可・一覧の再編はしない |
| P-03 | §5へ旧台帳問題の事前解決、無所属decisionの非消費、等号再開始後のACK／DECLAREと新check_dの条件を明記 |
| P-04 | 依頼§5にB-3自身の検出と既存検査器の防護による検出の区別を追加 |
| P-05 | 依頼§2・§6で新規試験をtest_r3_*.py、ヘルパーをr3_helpers.pyとする |

レビューはD-1（N-01解消を条件）・D-2・D-3に賛成している。これはユーザーの採用・B-3限定実装の承認ではない。§12の3点は引き続き未採用。本書第2版を固定SHAで確認した後に採否判断する。
