# V2 S3-B-4 復元計画・確認 設計案

作成日：2026-11-02（日本時間）。版：第1版。
状態：**設計案・レビュー待ち。B-4限定実装は未承認。**
今回のユーザー指示は設計書・限定実装依頼書の作成まで。文書の保存・推奨・レビュー通過を実装承認に置き換えない。

## 1. 目的と固定入力

検証済みschema_version=2履歴の有効な復元点Pを選び、有効な後続記録を退避して、明示したREAPPLY／REPLAY／DROP／RETIREを行う計画を作る。同じ計画の確認で、RECOVERY_RESTOREと後続記録をすべて含む候補Historyを返す。過去の物理記録は残す。

| 用途 | 固定版 |
|---|---|
| コード開始点 | **d82a5ced64658c2e736b82b1a2f1925636055417**（feat/v2-history-restart-s3b3-20261102）。コード・試験は7d75ea5dbee1f6cef9912fceced2c2be2e48fad9と同じ |
| B-3受領 | 78b9b405cebfb37283bf59f35d7774ad6910b331、docs/reviews/V2_RECOVERY_S3B3_IMPLEMENTATION_RECEIPT_20261102.md |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md、特に§8・§14のD-3/D-5 |
| 上位第4版 | e3e90947a718cca877b543739ca60539207ca7a7、docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md、R-2・RT-07 |
| B-2第2版 | e083cd3187f17692cb081fcc1031b09551fb8cb7、docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md |
| B-3第2版 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba、docs/specs/V2_RECOVERY_S3B3_RESTART_UNKNOWN_DESIGN_DRAFT.md |

読解対象：上記文書、B-1のrestore／view／values／validate、B-2のchain／read／daily／values、S3-Aのfacts／project／commands／ledger、S1のevents／recompute／runner、コアのengine／transition／fixture、B-2/B-3の範囲試験と既存合成ビルダー。共通のCLAUDE.md・STATUS・MODEL_POLICY・ROADMAPも確認した。古いSTATUSの承認待ち記述によって、B-3までの採用・受領を取り消さない。
今回は文書の作成のみ。コード変更、試験実行、再現コード、新しい市場計算は行っていない。

## 2. 今回の限定単位と採用案

### 2.1 含めるもの

新パッケージv2_history_restoreで、復元計画・hash指定確認・同じ候補への再確認、現在の台帳・sessions・seriesとの照合、差の安全な表示を作る。返すのは候補Historyまで。新しい戦略式・台帳の判定規則は作らない。

### 2.2 CONSUMEは保留する案（D-1）

B-1はCONSUMEをrestore_op_unsupportedで拒否する。今回はその検査器と保存形式を変えず、4処分だけを計画できる最初のB-4限定単位とすることを推奨する。CONSUMEの採用を先に決めた扱いにはしない。

未適用Dの新規消費が必要なら§8のrestore_requires_consumeで止める。後日CONSUMEを採用する場合は、B-1検査器・復元バッチ・受入条件を改める別の限定依頼を作る。今回の完了はCONSUMEを含む復元全機能の完成ではない。

### 2.3 対象外

B-5の破損診断・prefix採用、壊れた履歴の救済、S3-Cの保存・保守ゲート・解錠・CAS・元バイト退避・公開後照合、CLI、通知・outbox、実時計・乱数・ネット・ファイル操作、売買・口座接続を含めない。
B-2のHistoryAppendBatchはDAILY/RESOLUTIONのまま固定する。RESTOREをRESOLUTIONに偽装せず、独自の保存用バッチ/checkerも作らない。B-3と同じくバッチ統合はS3-Cへ留保する。確認済みplanとcandidateを保持すれば、バッチ化のためだけにprepareをやり直す必要はないが、保存時の再検査は別途必要。

## 3. APIと値

| 名前 | 契約 |
|---|---|
| prepare_restore_plan(history, restore_point, ops, sessions, raw_observations, series, check_d, request_id, requested_at) | READYのRestorePlan。restore_pointは{seq,event_hash}、opsは順序付きlist。requested_atは注入aware datetime |
| confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_observations, series) | CONFIRMED_IN_MEMORYまたはNO_CHANGEのRestoreConfirmResult |
| RestorePlan | from_dict/to_dict、basis、plan_hash、status、committed=False、summary、安全なrepr |
| RestoreConfirmResult | status、history、plan_hash、committed=False、committable=False。batch/ledger属性なし |
| 定数 | READY、CONFIRMED_IN_MEMORY、NO_CHANGE |

__all__は上の2関数・2型・3定数の7名。旧パッケージへ再公開しない。
計画のfrom_dictはJSON深さ・型をコピー前に検査し、hashや候補は確認時に検査する。全構造化アクセサと、未検証のplan_hash/status等のコンテナは独立した写しを返す。表示前に日付・seq・hash・固定語・IDを再検査し、不正なら固定の(?)表示またはrestore_invalid/plan/plan_shape。
確認結果は確認関数が検査済みの固定status・不変History・文字列hashから構築する。結果型の直接構築は信頼済み内部入力に限るとdocstring・結果文書に明記する。外部メッセージの読込口はRestorePlan.from_dictだけ。B-3受領P-01に便乗して既存型を変更しない。

## 4. 復元点・処分・ID

まずvalidate_history(history)とread_effective(history)から元の有効列Eを得る。

- PはE内、hashはその記録と一致すること。移行履歴ではMIGRATION自身以後、新規v2ではGENESISを下限とする。
- Pは現在の物理先頭ではない。ACK/DECLAREのcommand_indexがcommand_count-1未満の点は拒否する。
- 過去の復元バッチで生成されたAPPLY等の途中をPにすることは許す。そこまでの物理prefixが単独で有効なHistoryになるとは限らないため、これを履歴として切り出してvalidateしない。
- superseded_seqsはEのPより後だけを、Eの順に並べる。物理区間P+1..headを使わず、既に退避した記録を再び退避しない。
- opsの各要素は厳密に{op,from_seq}。from_seqはbool/floatではないint。superseded列と同じ順・同じ件数で各記録を1回だけ名指しする。自動並べ替えや省略の補完をしない。

| 元記録 | 許可するop |
|---|---|
| APPLY | REAPPLYのみ |
| ACK / DECLARE_MISSING | REPLAYまたはDROP。同じrequestバッチ全件で同じ処分 |
| RESTART_UNKNOWN | REPLAYまたはDROP |
| RECOVERY_RESTORE | RETIREのみ |
| SCHEMA_MIGRATION | 復元点の下限によって退避されない |

CONSUMEは{op:"CONSUME",d}を含め一律拒否。未知opも拒否する。
新しい復元依頼のrequest_idは物理履歴全体で未使用を要求する。内容一致・時刻だけの違い、有効/退避、NATIVE/MIGRATED/REPLAYED、他種別を問わず既存IDはhistory_request_conflict/request_id。再生する旧記録が旧IDを保持することと、新依頼のIDの再利用は別である。
prepareはREADYだけを返す。同じ元planと確認hashを、その候補そのものへ再確認する経路だけがNO_CHANGE。IDを替えた自動再試行は作らない。

## 5. 準備の順序・エラーの優先順位

| 順 | 検査・処理 | 失敗時 |
|---|---|---|
| 1 | 入力履歴全体のvalidate、sessionsのコピー、check_dの日付解析、台帳各行の独立解析 | 既存履歴/入力エラーを維持 |
| 2 | check_dは元の現在境界より後・元latest_apply_d以上、存在・confirmed・next・previous。その後、Pとopsを§4で検査 | check_dの既存エラー、P/opsのrestore_invalid |
| 3 | requested_at→ID形→物理履歴のID照合 | 既存日時エラー、restore_invalid/request_id/request_id、history_request_conflict |
| 4 | 元履歴のPまでの実事実で残す文脈を照合し、REPLAYする境界も照合。REAPPLY各Dのseries入力を§9で固定。§6の意味内容・写像・frontier/floorを計算 | seriesの既存入力エラー、restore_invalid、参照欠落等 |
| 5 | hashを確定して候補全体をvalidateし、過去保存・退避/再生対応を検査 | 既存history_invalid、内部不変検査はhistory_invalid/history/restore_candidate |
| 6 | §7のREPLAY証拠→候補の全事実と現在sessions照合→除外・補完・版選択の事前投影 | S3-Aの既存エラーを維持 |
| 7 | §8の新規消費の必要性→各REAPPLYの現在decision比較→現在seriesの値比較とevaluate_day照合 | restore_requires_consume、restore_decision_changed、restore_market_input_changed、既存入力エラー |
| 8 | 変更しないproject_history_ledger(candidate,...,check_d)で最終照合。事前投影と一致を確認。§10の無効果検査→basis/hash→READY | 既存台帳エラー、restore_no_effect、内部不変エラー |

check_dは次セッションが存在すればよく、そのconfirmedは不要。B-3で等号の再開始をした直後には、その再開始日では復元計画も作れない。後の確定check_dを明示する。
sessionsの形の不正や不正な台帳行はIDより前。一方、候補の保存文脈と現在sessionsとの差は段階6なので、使用済みIDと重なる場合はID conflictを優先する。
**元履歴に対する現在台帳の最終投影は、準備の必須前提にしない。** DROPで解決するはずの旧宣言/ACKの問題がそこで先に止まることを避ける。元履歴そのものの整合性は段階1で必ず検査し、残す/再適用/再生する事実は候補で完全照合する。退避しただけの旧境界・旧宣言を、現在sessionsの追加制約として使わない。

## 6. 候補を最後まで組み立てる

### 6.1 二段階でhashの循環を避ける

組立ての前に、完全検査済み元履歴のPまでの有効prefixから§7と同じ実物のFixedFacts/LedgerContextを作り、残すAPPLY/宣言/境界と現在sessionsの文脈を照合する（台帳の最終投影はしない）。REPLAYするRESTARTの保存boundary_sessionも現在の同日セッションと完全一致を要求する。これにより、保持する文脈の改訂を、組立ての内部history_invalidへ化けさせずsession_context_missing/mismatchとして止める。DROP/RETIREだけの旧境界/宣言はこの照合へ含めない。

復元点までの有効な記録列を作業列として読み、opsの順に新しい状態・入力・context・各記録の内容を計算する。作業列はHistoryでも検証済み履歴の代用品でもなく、この呼出し内の下書き。途中の不完全な復元バッチを、validate_historyやB-2投影へ渡さない。

第1段階で新seq、各REAPPLYの4項目の同一性、replay一覧を決める。same_as_supersededは親hash/event_hashを比較しないため、まだ新しいhashが無くても計算できる。
第2段階でRECOVERY_RESTOREのhashを確定し、後続記録を順に結ぶ。参照先の新hashも先行記録から確定する。下書きの仮hashや未検証値を公開しない。

### 6.2 REAPPLY

保存済みconfirmed_inputsのdecision・row・prev_row・prev_session_dateは完全に維持する。これらをparse_observation/MarketRow等へ戻し、**変更しないapply_transition**に、新しい有効親のMarketStateを渡して計算する。旧state_afterやtransition_resultをコピーしない。

新contextは、新区間の最後のAPPLY日（無ければ境界）からnext(D)までの注入sessions。間の全セッションはconfirmed。skipped_sessionsはその開始点とDの間の全セッション日。新prev_session_dateは保存値と一致し、旧contextと共通する日付は同じ投影で一致すること（両contextの末尾next(D)のclose_at/confirmedだけ無視）。不存在/ずれはsession_context_missing/mismatch。row等を現在seriesの値に置き換えて作らない。

same_as_supersededはinput_hash、skipped_sessions、transition_result、state_afterの4項目すべての正規化比較が同じ場合だけtrue。4項目のどれが変わったかをchangesへ残す。

### 6.3 REPLAY・DROP・RETIRE

保持する値と再計算する値はS3-B第2版§8.5のまま固定する。
ACK/DECLAREのrequest系・command_index/count・reason・時刻・旧ledger_digest・origin・fingerprints・variant/dを保持する。RESTARTもrequest系・resume_after・boundary_sessionを保持する。
ACK/DECLAREのstate_afterは新しい有効親の値。DECLAREのfrontier_before/contextは新しい区間から再計算し、dが注入sessionsでfrontierの次であることを要求する。RESTARTのstate_afterは初期状態、floorは新しい有効列全体から再計算する。resumeが新floor未満、元request_basis.check_d超過、初期状態同境界なら拒否する。

参照写像mは、元の有効列のP以前に残る点なら元seq/hash、REAPPLY/REPLAYされた点なら新seq/hash。DROP/RETIREした点・有効列にない点に写像は無い。必要な参照が無ければrestore_ref_unmappedで止まり、依存するACKもDROPするなどの指示の修正を求める。自動で落とさない。
すでに再生済み/移行済みの記録をさらに再生する場合も、その元記録が**現在持つ記録上の参照**を1回だけ写す。古いrequest_basisの名前空間を再変換しない。replay_ofは今回退避する直接の元seq/hash。
DROP/RETIREでは新記録を作らない。物理履歴から元記録を削除しない。

### 6.4 RECOVERY_RESTOREと完全候補

記録は既存の15キーを維持する：
kind, seq, prev_hash, parent_seq, parent_hash, superseded_seqs, replay, request_id, request_hash, request_basis, reason_code, requested_at, ledger_digest, state_after, event_hash。

seq=旧head+1、prev_hash=旧物理head hash、parent=P、state_after=P.state_after。ledger_digestは今回の生台帳6列のdigest。
request_basisは既存の6キーrequest_id, restore_point, ops, check_d, reason_code, requested_at。reason_code=RESTORE_VERIFIED_RECORD。request_hashはrequested_atだけを除くbasisのhash。
replayは各opにつき{op,from_seq,d,seq,same_as_superseded}。新記録はREAPPLY/REPLAYの数だけ直後へ連続して置く。DROP/RETIREのd/seq/sameはnull、REPLAYのd/sameはnull。

最終candidateは元の全物理events＋RESTORE＋全生成記録。旧eventsは完全一致、有効列は旧EのPまで＋RESTORE＋生成列、退避集合は旧退避と今回supersededの互いに素な和、新header/stateは末尾と一致すること。元移行情報も変えない。全体を変更しないvalidate_historyへ通す。

## 7. 台帳規則を複製しないための橋渡し

既存ランタイムの変更を避け、B-2で導入済みの公開FixedFacts/LedgerContextとS3-Aの公開関数を再利用する。この利用は**新B-4パッケージだけ**に明示して許可する。B-3の禁止を緩めたり、Chain/ledger_of/_Frozen等の内部名を使ったりしない。

1. 段階5で完全検査済みのcandidateから、有効列上のAPPLY・宣言・境界の部分値を取り出し、FixedFacts.from_partsへ渡す。APPLYのskippedは検査済みrecordのskipped_sessions。架空のSnapshotView/Ctxや検証済みフラグを作らない。
2. 再生するACK/DECLAREはrequestバッチ単位で証拠を再検査する。そのグループの直前までの**有効列のprefix**から実物のFixedFactsを構築し、LedgerContext.from_facts(...,外側のcheck_d)を作る。existingはそのprefixの有効な解決記録、commandsは再生後の記録上のkind/variant/d/fingerprints/参照から作り、変更しないcheck_commandsへ渡す。元request_basis.commandsの古い参照をそのまま渡さない。
3. check_commandsのextrasが、再計算したDECLAREのfrontier/contextと一致すること。ROW_REMOVED+ADDED等はグループを分断せず一括検査し、指示順の偶然で証拠を失わせない。DECLAREは有効decision1件なら既存declare_valid_decisionで拒否する。
4. candidate全体のFixedFactsと現在入力でLedgerContextを作る。apply_records→check_versionsの順に呼び、残った6列をcanonical_json順に並べる。これは§8/§9の照合用の**事前の行集合**であり、最終照合済みのHistoryLedgerとして公開しない。
5. 最後は必ず変更しないproject_history_ledger(candidate, sessions, raw, check_d)を呼び、全区間のAPPLY/欠測/宣言/当日選択を検査する。返る行・effective_digestは事前集合と一致すること。最終検査を省かない。

prefixは完全検査済みsourceまたはcandidateの祖先列からこの関数内で導出した事実だけを使う。呼出し元がFixedFactsやLedgerContextを注入できるAPIは作らず、作業contextも戻り値に含めない。参照の構造検査はB-1、証拠/版選択はS3-A、最終全区間照合はB-2に委譲する。

## 8. CONSUMEが必要な場合の停止

今回、新しいDのAPPLYを足してよいのは退避したAPPLYのREAPPLYだけ。新しい市場入力/decisionの採用はしない。
§7の事前集合に対し、次のreleased_daysを現在の注入sessionsの日付集合として作る。

- DROPするDECLARE_MISSINGのd。
- DROPするRESTART_UNKNOWNごとに、**元の有効列でその再開始の直前のfrontier**（その区間の境界/APPLY/宣言の最大日）より後、元resume_after以下の全セッション。
- 各REAPPLYについて、新skipped_sessionsからその元APPLYの旧skipped_sessionsを引いた日。

上の和集合を注入sessionsの日付集合と交差させ、candidateに有効APPLYがある日は除く。DROPだけの旧宣言日が現在のカレンダーに無い場合、その日の有効decisionを仮定して日付を補わない（残る文脈に必要な日付の欠落は別途拒否する）。それ以外のreleased_daysを昇順にselect_decisionで検査し、有効decisionがあればrestore_requires_consume/ops、detail=Dで停止する。最後の宣言だけをDROPして後続APPLYが無い場合や、新基点as_of_d=nullの場合も省略しない。
これはCONSUME保留時の保守的な制限であり、後のRESTARTにより再び境界以前になる日でも、DROPした操作による再消費が必要かを自動で免除しない。さらに広い取消を許す条件はCONSUME採用時の別設計とする。
select_decisionのdecision_outside_window/target_mismatch/decision_conflict等は変更せず返す。単に行があるだけで有効decisionと断定しない。

released_days以外の旧skippedへの後発、DROPしたLATE ACKにより戻る旧後発などは、最後のB-2照合で既存late_observationになる。この区別を受入試験で固定する。未適用行のある無関係な全日を勝手に消費対象に広げない。

## 9. REAPPLYの現在入力と市場値の固定

REAPPLY対象だけを元seq順に取り、各Dでseries.through(D)を取得する。現在のMarketRow(D)、保存prev_session_dateの行（既存コアと同じく取得不能ならnull）、series.previous_date(D)を読む。Dより後や、SOXL表示価格・description・パス/取得時刻は判定入力digestに含めない。REAPPLYが無ければseriesは参照せず、series_inputs=[]のdigestを使う（series=Noneも可）。

series_inputsの各項目は厳密に{from_seq,d,prev_session_date,series_previous_date,row,prev_row}。row/prev_rowは既存row_dictの6キー正規形。series_previous_dateと注入sessions.previous(D).dateと保存prev_session_dateが一致しなければsession_series_mismatch。数値はbool・非有限・巨大整数を受理しない。既存InputErrorは維持し、JSON化不能/系列プロトコルの形の誤りはrestore_invalid/series/market_input。この正規化は入力の固定であり指標式の複製ではない。

各Dで次の順に照合する。
1. §7の行集合からselect_decisionで選ぶ。不存在または保存したrecord_id/指紋と違う場合はrestore_decision_changed/observations、detail=D。選択自体の衝突/入力エラーは維持する。補完済みの保存行が選ばれることは許す。
2. 現在row/prev_row/prev_session_dateと保存値を正規化比較し、違えばrestore_market_input_changed/series、detail=D。判定が同じでも市場値の差を許容しない。
3. 新しい有効親state、同じ固定cut、現在sessions、事前の行集合を変更しないevaluate_dayへ渡す。保存値によるapply_transitionの候補とserialize_transition/next_stateが一致すること。原則Dは親as_of_dより後なので再実行扱いにしない。state_updatedを保存成功の意味で使わない。

series_digest=sha256(canonical_json(series_inputs))。前史の変更でも対象rowの指標が変われば拒否する。D後のデータだけ、SOXL表示価格や系列の説明だけの変更はこのdigestを変えない。現在入力の許容差や市場データの自動更新は入れず、U-07の別判断に残す。

## 10. 差・無効果・計画

changesはopsと同じ長さ/順で、各項目は{op,from_seq,kind,d,to_seq,same_as_superseded,changed_fields}。
REAPPLYのchanged_fieldsは4項目input_hash/skipped_sessions/transition_result/state_afterのうち変わった項目を名前順に列挙する。REPLAYは再計算可能な参照/state/frontier/context/floorのうち変わった項目名のみ。DROP/RETIREはto_seq/same=null、changed_fields=[]。dはAPPLY/ACK/DECLAREならその日、RESTARTならresume_after、旧RESTOREならnull。
値そのものや市場値、F&G、自由文をsummaryへ出さない。summaryはstatus、request_id、P/旧head/候補head、件数、日付、固定op・種別・フィールド名、sameフラグ、plan_hash、固定falseフラグだけを表示する。

D-2の推奨：**DROPが1件も無く、全REAPPLYがsame=trueならrestore_no_effect/opsで拒否**する。REAPPLYが0件の場合も「全件true」とみなす。RETIREによる監査鎖の付け替えだけを新しい復旧としない。DROPがある場合は市場状態が同じでも明示した制御記録取消として受理し得る。B-1の検査器はこの無効果制限を追加せず、計画だけの制限とする。

RestorePlanの外形は{basis,plan_hash}。basisは次の**23キー**：
operation="soxl-v2-history-restore-plan/1", status=READY,
history_digest, expected_head_seq, expected_head_hash, expected_state_digest,
restore_point, ops, check_d, request_id, request_hash, reason_code, requested_at,
ledger_digest, sessions_digest, series_inputs, series_digest, effective_digest,
candidate_history, candidate_digest, candidate_state_digest, candidate_records, changes。

candidate_recordsは今回追加するRESTOREと後続記録の列で、candidate_history.eventsの旧head+1以後と完全一致。effective_digestは最後の候補B-2投影の値。
plan_hashはbasis全体のcanonical_jsonのSHA-256。時刻だけ変更するとrequest_hashは同じだが、RESTORE/event/planのhashは変わる。元台帳の余分な列は保存しない。digestは整合性の検査であって署名ではない。

## 11. 確認と同じ候補への再確認

1. 計画の型・外形・23キー・固定語・厳密整数・日付/時刻/ID・hash・changesの安全な形とconfirmed_plan_hashを検査する。候補を完全validateし、candidate_records/個数/末尾/全digestを照合する。候補の元物理prefix events[:expected_head_seq+1]を復元してvalidateし、元history/head/stateのbasisとも照合する。これは元の完全履歴の長さで切るので、復元点Pが旧復元バッチの途中でも元履歴は切断しない。不正はhistory_plan_mismatch/plan。
2. 渡された履歴のvalidate、sessionsのコピー、台帳各行の解析、planの元prefixとREAPPLY一覧から現在series_inputsを§9の方法で固定する。入力そのものの不正は既存入力エラー/restore_invalidを維持し、staleにしない。ここでは台帳の最終投影やIDの再照合を先に行わない。
3. ledger/sessions/seriesのdigestが一致し、渡された履歴が(a)元prefixの完全なdigest/head、または(b)planのcandidateそのものの完全な内容/digest/headのどちらかに一致すること。他はhistory_plan_stale/plan。候補へ日次等が増えた場合もstale。
4. (a)は渡された元履歴、(b)は検査済み元物理prefixを使い、同じP/ops/check_d/ID/元requested_atで準備全体を再構築する。全basisと候補を完全比較する。digest一致後の再構築失敗・不一致はhistory_plan_mismatchに固定し、元例外の自由文やチェーンを表示しない。
5. (a)はCONFIRMED_IN_MEMORYと候補、(b)はNO_CHANGEと現在Historyそのものを返す。2つ目のRESTOREを作らない。B-2のNO_CHANGE用4項目書換え方式は使わない。

確認時のsessions_digestは全注入列への結合であり、next(D)のconfirmed/close変更でも計画がstaleになり得る。新しい計画でのAPPLY文脈の投影比較/input_hashとは別の契約で、無害なnext変更を保存入力不一致と誤判定しない。
成否不明時の計画保持と公開後照合はS3-Cの責任。ID conflictやstaleだけで「保存されていない」と断定しない。

## 12. エラー対応表

| 状況 | code / field / rule |
|---|---|
| Pの形、hash不一致 | restore_invalid / restore_point / restore_point_shape または restore_point_mismatch |
| Pが退避済み・head・移行より前・request途中 | restore_invalid / restore_point / restore_point_not_effective、restore_noop、restore_before_migration、restore_point_in_batch |
| opsの型/キー/厳密整数、列の過不足/順序 | restore_invalid / ops / ops_shape または superseded_mismatch |
| CONSUME/未知op、種別に禁止のop、request部分処分 | restore_invalid / ops / restore_op_unsupported、restore_op_kind、restore_partial_batch |
| 写せない参照、再生DECLARE/RESTARTの幾何的条件 | restore_invalid / ops / restore_ref_unmapped、declare_frontier、restart_floor、restart_noop、check_d |
| 新しい消費が必要 | restore_requires_consume / ops / ruleなし、detail=D |
| 現在のdecision / 市場値が保存値と違う | restore_decision_changed / observations、restore_market_input_changed / series。ruleなし、detail=D |
| 無効果 | restore_no_effect / ops / ruleなし |
| 不正JSON・計画読込の形 | restore_invalid / plan / json_depth、json_number、json_key、json_type、plan_shape |
| 計画改変/確認hash違い、正常な入力変更 | history_plan_mismatch / plan、history_plan_stale / plan |
| 既存依頼ID | history_request_conflict / request_id |
| 入力履歴・候補の完全検査 | 元のhistory_invalid/unsupported_schema等を維持。独自保存不変条件だけhistory_invalid / history / restore_candidate |

InputErrorの日付/セッション/市場系列エラー、S3-Aのresolution_invalid/version_selection/declare_valid_decision、select_decisionの衝突、最終B-2台帳エラーはそのまま。既存検査器を緩めない。detailsは日付等の安全な値だけとし、rawのreprやURLを出さない。

## 13. 最小受入例と委譲境界

| 例 | 期待 |
|---|---|
| GENESIS→APPLY D1→RESTART D1→APPLY D2。P=APPLY D1、restart DROP、D2 REAPPLY、他のdecisionなし | READY。旧物理列を保持、新D2はD1から再計算。変わる4項目とsameを実値から確認し、旧値コピーで期待値を作らない |
| GENESIS→APPLY D1→RESTART D3→APPLY D4。D2/D3に有効decisionなし、P=D1 | restart DROPとD4 REAPPLYが可能。D2/D3に有効decisionを1件加える対照はrestore_requires_consume（初期as_of_d=nullの対照も含む） |
| 最後がDECLARE D2。Pはその直前、DECLARE DROP、D2の有効decisionが戻る | 後続APPLYが無くてもrestore_requires_consume |
| 上位例R/R-bの複数回復元・ACK/DECLARE再生 | 実際の台帳/seriesを注入し、元の例IDを維持。新しい外側IDは未使用のr4-review-1等。B-1の構造だけの合格をB-4の証拠合格とみなさない |
| Pが旧復元バッチの途中のAPPLY | 有効点なら受理し得る。Pで切った不完全な物理Historyを検証する実装は拒否する |
| 全REAPPLY true、DROPなし | 新IDでもrestore_no_effect。DROPのある正常計画の候補を同planで再確認する対照はNO_CHANGE |
| sourceの最終投影に問題があるが、DROP後のcandidateは整合 | 元履歴内部は正常なら計画を作り得る。残るAPPLYのdecision変更や版選択は許さない |

新コードで許す既存公開依存は、History/validate_history/read_effective/project_history_ledger、history_dict/check_json/種別定数、basis_request_hash/is_int/is_hex64/is_date/same、FixedFacts/LedgerContext、check_commands、apply_records/check_versions、台帳parse/digest/copy_sessions、requested_text/is_requested_text/valid_request_id、MarketState/MarketRow/parse_iso_date、parse_observation/select_decision、apply_transition/evaluate_day、canonical_json/sha256_text/compute_event_hash、session_dict/row_dict/decision_dict/confirmed_inputs_dict/input_hash_of/project_context/serialize_transition/make_apply_event、PersistenceError/CoreError/InputError/ConflictError。実装で実際に使うものだけimportし、不要な公開名は増やさない。
標準ライブラリはcopy/json。既存private名、Chain/ledger_of/_Walk/_Frozen、Ctx/SnapshotViewの代用品、S1 planやB-2 batchを保存用に流用することは禁止。テストヘルパーをランタイムから呼ばない。

## 14. 採否と後工程

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | 候補HistoryまでのB-4限定範囲、CONSUME保留と必要時停止、既存ランタイム無変更・公開S3-A橋渡し、新ID/同計画再確認、旧範囲試験2本の限定補正を採用するか | 採用を推奨 |
| D-2 | DROPなし・全REAPPLY同一の無効果復元を計画で拒否するか | §10のrestore_no_effectを推奨。既存検査器は変更しない |
| D-3 | 実装担当 | Sonnet 5.5・highを推奨。上記で仕様を固定した後の純粋な計画/検証実装。矛盾は主担当へ返す |

CONSUME、B-5、S3-C、全体稼働、本番保存先・資格情報は今回の採否に含まない。モデル実設定は実装セッションで確認する。
変更境界・範囲試験の補正・受入条件・限定欠陥注入は、対になるdocs/tasks/V2_RECOVERY_S3B4_LIMITED_IMPLEMENTATION_REQUEST.mdで固定する。レビュー後にD-1〜D-3を一組で採否判断し、採用後に別実装ブランチで着手する。
