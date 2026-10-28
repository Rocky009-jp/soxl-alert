# V2 保存ドメイン・単日ランナー オフライン設計案

作成日：2026-10-28／第4版：2026-10-28（日本時間）  
状態：レビュー用の設計案。実装は未承認・未着手。今回の指示は設計と依頼書の作成まで。  
段階名：S1（メモリ上の検証）。本番の永続保存形式を確定する文書ではない。

## 1. 目的と参照版

P-04・P-06・U-14で検査と純粋な遷移関数を備えたコアの外側に、遷移記録、再実行、更新競合を扱う小さな層を設ける案である。実ファイルへの耐久保存を作る前に、保存すべき内容と「いつ1件だけ確定するか」を検証する。

| 用途 | 固定版 |
|---|---|
| 実装基準 | feat/v2-core-state-checks-20261028、b616b4ec7169420e199ec7e247dd375b3603a013 |
| コア結果 | [V2_CORE_STATE_CHECKS_RESULT.md](https://github.com/Rocky009-jp/soxl-alert/blob/b616b4ec7169420e199ec7e247dd375b3603a013/docs/implementation/V2_CORE_STATE_CHECKS_RESULT.md) |
| 上位の保存・復旧設計 | [第4版](https://github.com/Rocky009-jp/soxl-alert/blob/e3e90947a718cca877b543739ca60539207ca7a7/docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md)、e3e90947a718cca877b543739ca60539207ca7a7 |
| 前工程の依頼 | [第2版](https://github.com/Rocky009-jp/soxl-alert/blob/b43205ce1a53e4560fb85f9cfb715c72a1132a75/docs/tasks/V2_CORE_STATE_CHECKS_TRANSITION_REQUEST.md) |
| 今回の実装依頼案 | [V2_PERSISTENCE_DOMAIN_OFFLINE_REQUEST.md](../tasks/V2_PERSISTENCE_DOMAIN_OFFLINE_REQUEST.md) |

上位設計の推奨を採用済みに変更しない。U-01・U-11・U-13（保存先・台帳・実行場所・資格情報）は引き続き一組で後日決定する。U-02の「不一致時は停止」は、本S1に限って採用を提案する。U-06の経過セッション数による上限値は設定せず、S1が古い状態の運用許可を与える意味にはしない。P-04・P-06・U-14は実装済みだが、上位設計の復旧・通知まで完成した意味ではない。

CLAUDE.md、docs/STATUS.md、docs/MODEL_POLICY.md、docs/ROADMAP.md、上記固定版と対象コアを確認した。STATUS等には前工程より古い「承認待ち」の記述が残る。今回の最新ユーザー指示と固定版を優先し、既存文書は書き換えない。

## 2. 前工程の確認と保留

| 確認主体 | 確認できた範囲 |
|---|---|
| Claudeの作業報告 | b616b4eで既存138＋新規43＝181件、Python 3.10.20・3.11.17・3.12.3・3.13.17合格。旧新版3114ケース一致、欠陥注入43件を検出。独立した再確認の全項目を意味しない |
| ChatGPT側の独立確認 | Windows／Python 3.12.14で状態検査23件、旧新版2650ケース一致、直接遷移2625ケース一致。全181件・歴史464ケースの独立再実行はしていない |
| ユーザーのPC | 旧1a54a85の138件は「全てOK」の報告あり。最新b616b4eの全181件はPCが手元にないため後日実施。今回の設計作業で完了扱いにしない |

最新コアのユーザーPC確認を、文書作成の前提条件にしない。後日実施する際はb616b4eの完全SHA、Python版、コマンド、件数、失敗・skip、終了コードを残す。core.autocrlf=true、実カレンダー、歴史遅延1全日照合、候補920e695の試験も今回の完了条件へ追加しない。

## 3. 段階分け

| 段階 | 内容 | 今回との関係 |
|---|---|---|
| S1 | 保存用データの検査・再計算、明示Dの準備、MemoryStoreでの比較更新 | 本書と依頼書で具体化する提案 |
| S2 | 実ファイル保存アダプタ、プロセス間競合、電源断・置換・耐久性の検証 | 別設計・別依頼。S1の試験で代替しない |
| S3 | ACK、欠測宣言、復元、再初期化、有効・退避履歴の操作 | 上位第4版を基に別依頼 |
| S4 | 非公開保存先等の選定、実行場所・権限、通知outboxと接続 | 未決事項を具体化した後の別依頼 |

S1の対象外：実ファイル／Gitへの状態保存、取得アダプタ、自動対象日、追いつきループ、実時刻、ACK・DECLARE_MISSING・RESTORE・RESTART_UNKNOWN、outbox、再送、Discord・Sheets、資格情報、workflow、依存追加、本番接続、口座入力。新しいリポジトリやトークンを作らない。

## 4. モジュールと入出力

新規パッケージをv2_persistenceとし、既存v2_coreは変更しない。公開APIの責務を次に固定する。ファイル分割や型名の細部は担当者が決め、結果文書に対応表を残す。

| API | 契約 |
|---|---|
| make_genesis(start_after, sessions) | 明示された確認済みセッションを境界とし、初期状態とGENESISのみのSnapshotを返す。保存操作はしない |
| validate_snapshot(snapshot) | 構造、履歴、保存入力、全APPLYの再計算を検査する。失敗を修復しない |
| prepare_day(snapshot, d, series, sessions, raw_observations) | 検査後に既存evaluate_dayで1日分を評価。PREPARED／NO_COMMIT／ALREADY_APPLIEDと、必要時だけAppendPlanを返す |
| MemoryStore.read() | 独立した値のSnapshotを返す。未初期化はstore_uninitialized |
| MemoryStore.initialize(genesis) | 未初期化時だけ、GENESIS1件のみのSnapshotで明示的に初期化。二度目は拒否 |
| MemoryStore.commit(plan) | 期待する先頭との比較と1件追記を同じロック内で実施 |
| reconcile(plan, snapshot) | 更新成否が不明／競合した場合の照合だけを行う。書込み・再試行はしない |
| encode_snapshot／decode_snapshot | 文字列との変換のみ。パスやファイルを扱わない |

series・sessionsはb616b4eの既存入力を使う。raw_observationsはGENESIS境界より後から今回D（または適用済み最新Dの遅い方）までを含む台帳全体を、呼出側が不変の写しとして渡す契約とする。日単位に絞った一覧ではない。S1は台帳取得元の完全性を証明しない。台帳の所在・読取SHA・権限はS4で扱う。

prepare_dayは入力の写しを作り、その1回の処理内では同じ値を使う。関数の途中で呼出側が元のlistやdictを変更しても準備済み記録を変えられない構造にする。

## 5. Snapshotと遷移記録

### 5.1 S1専用スキーマ

Snapshotの項目はschema_version=1、core_sha、head_seq、head_hash、current_state、events。core_shaは実装基準の完全SHAに固定する。不明な版・コア版・項目・イベント種類は拒否し、後方互換を推測しない。

eventsはGENESISから先頭までの1本の順序付き履歴。退避履歴や分岐はS1では作らない。GENESISのseqは0。APPLYは1から連続し、parent_seqとparent_hashで直前を指す。seq／parent_seqの整数にboolを受け付けない。APPLYのDは厳密昇順で、同じDを2件持てない。各イベントはstate_afterとevent_hashを持つ。

| 種類 | 固有の内容 |
|---|---|
| GENESIS | start_after、boundary_session、初期のstate_after。parent_seq／parent_hashはnull。boundary_sessionはdate／open_at／close_at／confirmedの確認済み1セッション |
| APPLY | d、confirmed_inputs、input_hash、skipped_sessions、transition_result、state_after。親は直前イベント |

GENESISのstate_afterはMarketState()の初期状態のみ。既存の任意状態をGENESISとして取り込む機能は作らない。保存先が無い・壊れているだけで自動初期化しない。

start_afterは処理開始の「除外する下限」であり、初回に処理するDではない。make_genesisは呼出側が明示した日付を既存parse_iso_dateで検査し、注入sessionsにその日が存在しconfirmed=trueであること、boundary_session.dateと一致することを求める。最新日・台帳の最初の日・OS時刻から推定しない。GENESISは市場の1日を適用した記録ではなく、as_of_dはnullのまま。初回Dは必ずstart_afterより後とし、その直後からDの前までを中間区間として検査する。start_after当日は自動適用も欠測記録もしない。台帳に境界以前の行が混在した場合も全行の構文／record_id検査は省略せず、将来Dの窓に入る誤対象行を黙って無視しない。

### 5.2 確定入力

confirmed_inputsには次だけを保存する。

- 選択されたdecisionの6項目。既存parse_observationで検査し、同じ意味の入力へ戻せるrawキー名で保存する。値はfloat、時刻はUTC、record_id・status・role・target Dを含む。指紋は既存Observation.fingerprint()を使う。
- DのMarketRow全6項目（date、soxx、sma、rsi、shd、prev_rsi）。
- 直前セッションのMarketRow全6項目、または利用できなかった場合はnull。prev_session_dateは別途必須とする。
- session_context：基準境界からDの次セッションまでの連続した注入セッション列。基準境界は直前state_after.as_of_d、初回はGENESIS.start_after。境界は注入列上でDの直前セッション以前なので、この範囲に直前セッションも含まれる。open_at／close_atをUTCで保存し、confirmedも保持する。

session_contextは新規APPLYでその時点の写しを固定する。同じDの照合では、保存時と同じ日付範囲で現在の注入列を切り出す。無関係な前史や次セッションより先を追加してもinput_hashを変えない。

保存する写しと、入力同一性を比較するための投影を区別する。保存するsession_contextには全セッションの4項目を保持するが、input_hash用の投影ではnext(D)のclose_atとconfirmedだけを除く。next(D)のdateとopen_atは観測窓・翌セッションの同一性に必要なので含める。D以前の項目は従来どおり含める。欠けた中間セッションや投影に残る値の改訂は同一入力と扱わない。

next(D)のclose_at／confirmedだけを後から更新しても、注入SessionListとして有効で他の判定入力が同一なら、同日再実行はALREADY_APPLIEDとする。除外項目の型・時刻順序等の入力検査は省略しない。保存済み写しは再実行時の新しい値で書き換えない。

市場の数値はboolを拒否し有限floatへ正規化する。soxx・smaは正、rsi・prev_rsiは0〜100、shdは有限値とする。前日行があるならdateはprev_session_dateと一致する。入力に存在しない前日行を補わない。

台帳全体の順序・重複行数、将来行、補助観測、series_meta全体はinput_hashへ含めない。選択decisionと判定に使った確定値が同じなら、同一UTC瞬間の別オフセット表記や同じ行の再提出で同一性を失わない。自由文・URL・口座値・通知内容は保存しない。

本段階が再現するのは市場状態と遷移判定である。SOXL参考終値、b*、待機表示などDayResultの表示全項目の再構築を保証しない。必要なら後続設計で保存項目を増やし、版を上げる。

### 5.3 ハッシュと判定の表現

JSONはキー順を固定（sort_keys=True）、区切りを固定（comma／colon、空白なし）、ensure_ascii=True、allow_nan=False、UTF-8で符号化する。数値の正規化後にSHA-256を計算する。読込時の重複キー、NaN／Infinity、型違い、未知項目は拒否する。

input_hashはconfirmed_inputsからnext(D)のclose_atとconfirmedだけを落とした投影を正規化して求める。投影はハッシュ比較専用であり、完全なsession_contextを要求するSessionList.from_dictsの入力には使わない。event_hashはevent_hash自身を除くイベント全体（保存した完全なsession_contextを含む）から求める。ヘッダーの先頭とcurrent_stateは履歴から求めた値と一致させる。これは整合性検査であり、悪意ある書換えの真正性や署名を保証しない。

transition_resultはapply_transitionとDayResultの共通部分を明示的に直列化する。rules各件のname／status／ratio／reasons／may_be_unconfirmed、run_class、gap、effective_armed、effective_streak、effective_prev_normal_raw、notesをすべて含める。Enumはvalue、理由やnotesの配列順は保持する。state_afterは別項目に置く。state_updatedと表示項目は含めない。

## 6. 検査と保存入力からの再計算

validate_snapshotは毎回履歴全体を検査する（S1に限る提案。U-10の本番方式を決めない）。

1. スキーマ・型・連続seq・親・各ハッシュ・Dの順序・初期境界を検査する。
2. current_stateと各state_afterをMarketState.from_dictで検査する。直接構築した値で検査を迂回しない。
3. 各APPLYのconfirmed_inputsを再検査する。decisionがDの窓内で、対象D・record_id・指紋がstate_after.fixed_decisionと一致することを確認する。session_contextはSessionList.from_dictsへ渡し、保存した基準境界・prev_session_date・D・next(D)の関係、Dがconfirmed=trueであること、D行の日付も検査する。
4. 当該APPLYの基点は、親イベントのstate_afterからfixed_decisionとbaseだけを落とした値と比較する（IB-04）。同じ値を別の現在状態としてfrom_dictへ渡さない。
5. 親の検査済み市場状態、保存済みの行・decision・prev_session_dateを既存apply_transitionに渡す。候補状態とtransition_resultを全項目比較する。戦略の計算式を新パッケージへ複製しない。
6. skipped_sessionsは、基準境界の次からDの前までのsession_context上の全セッションと一致し、そのすべてがconfirmed=trueであることを確認する。未確定の保存済み中間セッションはsnapshot_invalid（rule=skipped_session_unconfirmed）で拒否する。snapshot.current_stateは最後のstate_afterと一致する。

S1にACK等の状態を変えないイベントは無い。後に追加する際は、IB-04が「現在状態を作ったAPPLYの親」を指す上位設計を維持する。将来の復旧履歴を単純に末尾の状態とだけ比較して処理しない。

## 7. 台帳の検査と単日処理

### 7.1 不一致は停止する限定契約

S1ではACKによる継続や保存入力の補完を実装しない。次のいずれも保存状態を保持して停止する。この停止方式自体が今回の採用提案である。

- 適用済み各Dについて、現在の台帳に保存済みdecisionが無い、指紋が違う、別IDのdecisionが増えた、窓や対象日が不正。
- skipped_sessionsにdecisionが後から追加された。late_observationとし、以前の遷移に自動挿入しない。
- 同じrecord_idの内容違い、不正な入力行。台帳の並び順で勝者を選ばない。

適用済み各Dについて、保存したsession_contextの日付範囲を今回のsessionsから切り出し、保存時と同じ投影（当該Dのnext(D)のclose_at／confirmedだけを除外）で照合する。必要なセッションや窓のどちらかが欠ければsession_context_missing、両方存在して投影が異なればsession_context_mismatchで停止する。保存した窓だけを正として現在の相違を無視せず、保存済み写しも書き換えない。

投影が一致してから、既存select_decisionで保存した窓と今回注入した窓の両方の台帳照合を行う。欠測区間については各対象Dの窓を今回sessionsから得て、select_decisionで検査する。supplemental／not_checkedはdecisionの代用にしない。同じ最新Dの再実行もこの前処理を通るため、セッション投影の相違はrecompute_mismatchに先立ちsession_context_mismatchで止まる。

S1の呼出側はGENESIS以降の全履歴を照合できるsessionsを注入する。必要な供給範囲と、現在のカレンダーを固定版として供給する方法の運用設計はS2／S4で決める。S1は実カレンダー取得や訂正許容を実装しない。

最新Dより先の市場行は参照しない。過去Dを処理しない通常実行で、保存済み市場入力を最新価格へ自動差し替えしない。古い市場行の改訂を新しいDの処理時にもすべて検出する機能はS1の対象外。同じ最新Dの再実行では§7.3の厳密比較で検出する。

上位設計§2.7のACK検証→除外→保存入力から補完→最終検査はS3へ留保する。現在の台帳との不一致を「保存入力があるから正常」と見なさない。

### 7.2 新しいDとdecision無し

検査の順は、snapshot→dと必要sessions→台帳照合→既存evaluate_dayとする。例外の優先順位は同じ段階内では既存コアに従い、S1が返すエラーの分類を新しい試験で固定する。

DはGENESIS.start_afterより後で、現在state.as_of_dより過去であってはならない。

新しいDを準備する際の基準境界Bは、現在state.as_of_dがあればその日、初回はGENESIS.start_after。B<S<Dの全注入セッションSを日付昇順で列挙する。必要sessionsの検査段階で、全Sにconfirmed=trueを求め、未確定が1件でもあればintermediate_session_unconfirmed（field=sessions）で計画を作らず停止する。これはdecisionが無いSにも適用し、next(D)には適用しない。その後、各Sについて既存select_decision(raw_observations, sessions, S)を呼ぶ。窓外decision、誤対象、複数decision、同じrecord_idの内容違い等は、その既存codeで計画作成前に止める。有効なdecisionを1件見つけても、残りSの検査を飛ばして欠測を確定してはならない。全Sの検査を終え、有効なdecisionがあれば最も早いSをintermediate_session_unprocessedとして止める。全Sでdecisionが無い場合だけ、その区間をskipped_sessionsにできる。

first_unprocessed_sessionだけでは窓外decisionを拒否できないため、S1の中間区間検査をこの関数だけで済ませない。初回も通常の新規Dも同じselect_decisionによる検査を行う。NO_COMMITの場合も検査を省略しない。これで新たに記録する欠測区間は、後続実行で行う§7.1と同じ検査を既に通っている。

判定は既存evaluate_dayに委譲する。既存コアの不正入力／衝突を正常なNO_SIGNALへ変換しない。自動で過去Dを再生するループは作らない。

decisionが無ければNO_COMMIT。DayResultは返せるが、イベント・seq・状態は変更しない。decisionがある新しいDでは、候補状態をfrom_dictで再検査し、作成したAPPLYを元Snapshotへ1件追記した候補Snapshotに対してvalidate_snapshotと同じ全検査・再計算を行う。これを通った1件だけをAppendPlanとしてPREPAREDで返す。この段階ではMemoryStoreを変更しない。

初回に複数セッション空いた場合、初期状態のas_of_dがnullなのでコアのgapはfalseのまま。一方、GENESIS境界からのskipped_sessionsは記録する。通常の欠測後で当日のF&Gが30以上なら、コアどおり終了時streakは1。gapと記録上の欠測区間を同一視しない。

### 7.3 同じ最新Dの再実行

既存evaluate_dayを保存状態で再実行し、保存APPLYのinput_hash、transition_result、state_afterと比較する。同じならALREADY_APPLIEDで計画なし、追記なし。state_updatedだけがfalseになることは比較から除く。判定用の数値が変わった場合、判定結果が偶然同じでもrecompute_mismatchで止める。decisionが変わった／消えた場合は先に§7.1のledger_mismatchで止まる。複数decision等でselect_decision自身が出す既存エラーはそのcodeを保持する。コア単体とラッパーのエラー優先順位の違いを明記して試験する。

新規Dを正常にcommitした直後、他の更新を挟まず、同じseries・sessions・台帳で同じDをprepare_dayすると、必ずALREADY_APPLIEDで計画なし・追記なしになることを受入条件にする。窓外decisionを含むため確定前に停止すべき入力を、commit後の再実行で初めて拒否する設計にしない。これは不変入力かつ最新Dの再実行の契約であり、その後の台帳改訂・先頭更新まで正常とする主張ではない。

過去のD（最新Dより前）をprepare_dayで指定した場合は拒否する。過去記録の検査はvalidate_snapshot、成否不明の照合はreconcileで行う。

## 8. MemoryStoreと更新競合

AppendPlanはexpected_head_hash、expected_head_seq、追加するAPPLYを含む不変の値。現在stateや任意の履歴を置き換えるAPIにしない。

commitはthreading.Lockの同じクリティカルセクション内で、先頭比較、計画と新Snapshotの全検査、1件追記による全体置換を行う。失敗時は元Snapshotを保つ。同じ先頭から2実行が準備した場合、同内容でも1実行だけが成功し、他方はcas_conflict。自動リトライ、番号の繰上げ、新しいDへの読み替えはしない。read／initialize／commit間も同じロックで保護する。

readや各APIの戻り値は深い写しまたは再帰的な不変値とする。frozenなdataclassの内側のdictだけを書き換えられる構造を残さない。入力／戻り値の改変でストアや過去の計画を変えられないことを試験する。

reconcileは、検査済みの読直しSnapshot内に計画のDを探す。計画と同じ親hash、入力hash、transition_result、state_afterを持つAPPLYがあればALREADY_APPLIEDとする。先頭がその後進んでいてもよい。自分が書いた／通知を送れるという意味は持たせない。親が違えば、他の項目が同じでも同一計画の成功とはしない。この親hashの条件は上位§3.8の内容一致判定より厳しいS1限定の契約である。S3で復元・退避履歴を扱う際に再検討し、上位設計の条件を変更済みとは扱わない。

同じDで異なる記録があればconcurrent_conflict。該当Dが無ければREPLAN_REQUIREDを返す。先頭が新しいだけでは保存済みと判断しない。古い計画を新しい先頭へ付け替えない。呼出側は新Snapshotで明示的にprepare_dayし直す必要がある。

準備結果のcore_result.state_updatedはコアの「新規遷移候補」の意味を保つ。保存成功フラグに流用しない。外側の結果はPREPARED／NO_COMMIT／ALREADY_APPLIED／COMMITTEDとcommit実施の有無を別に表す。COMMITTEDを返せるのはcommit成功後だけ。準備済み・競合・失敗の候補を本番通知へ流す経路は作らない。

メモリストアは同一プロセス内の比較更新モデルである。プロセス終了後の保存、OSの置換、fsync、複数プロセス、Git pushの成否不明、通信再試行、通知の重複防止は保証しない。

## 9. エラーと受入境界

固定された安全なcode／field／ruleで表す。入力値・URL・生行を例外文へ埋め込まない。次の表をS1の対応規則とし、担当者が同じ条件へ別codeを付けない。

| 条件・発生箇所 | code | field／扱い |
|---|---|---|
| Snapshotの版／core_shaが未対応 | unsupported_schema | schema_version／core_sha |
| Snapshotのイベント種類が未対応 | unsupported_event | kind |
| その他のSnapshot構造・hash・保存状態・再計算の不整合 | snapshot_invalid | snapshot。ruleは固定識別子。内部from_dict等のエラーもこの場合は安全なruleとして包む |
| make_genesisのstart_afterが不正な日付 | invalid_date | start_after。既存parse_iso_dateのcode |
| GENESIS境界日がsessionsに無い／未確認 | genesis_boundary_missing／genesis_boundary_unconfirmed | start_after |
| DがGENESIS境界以前 | target_not_after_genesis | target_session_date |
| Dが適用済み最新Dより前 | state_ahead_of_target | state。既存コアと同じcode |
| Dがsessionsに無い／未確認、next／previous不足 | target_not_in_sessions／target_unconfirmed／next_session_missing／previous_session_missing | sessions。既存コアと同じcode |
| 台帳照合・中間区間に必要なセッションや窓が不足 | session_context_missing | sessions |
| 新規Dの中間区間にconfirmed=falseのSがある | intermediate_session_unconfirmed | sessions。必要sessions検査で停止、計画なし |
| 適用済みDの保存範囲と今回のセッション投影が相違 | session_context_mismatch | sessions。next(D)のclose_at／confirmedだけの変更を除く |
| 適用済みdecisionが無い／選択した指紋が保存値と異なる | ledger_mismatch | observations |
| 既存の欠測区間に有効なdecisionが追加された | late_observation | observations |
| 新規Dの中間区間に有効なdecisionがある | intermediate_session_unprocessed | observations。最も早い対象日を安全なdetailに残してよい |
| 注入台帳をselect_decision等が拒否 | 元のCoreError.codeを保持 | 元のfieldを保持。decision_outside_window、target_mismatch、decision_conflict、record_id_conflict等 |
| 同日再実行の入力投影／判定／状態の不一致 | recompute_mismatch | confirmed_inputs／transition_result／state |
| 未初期化read・commit／二重initialize | store_uninitialized／already_initialized | store |
| commitの期待先頭と実際の先頭が不一致 | cas_conflict | head |
| reconcileで同じDに異なる記録 | concurrent_conflict | events |
| reconcileで該当Dが無い | エラーではなくREPLAN_REQUIRED | 書込なしの結果ステータス |

prepare_dayの優先順位は、①Snapshot検査、②Dと必要sessionsの検査、③台帳照合、④evaluate_dayと同日比較。②には新規Dの全中間Sのconfirmed検査も含める。③では適用済みDの日付昇順、既存skipped_sessionsの日付昇順、新規Dの中間区間の日付昇順の順に検査する。適用済み各Dでは必要セッションの有無、保存範囲の投影一致、select_decision、保存指紋との一致の順とする。各select_decisionの例外はその時点で伝え、正常に選択された値についてのみledger_mismatch／late_observationを判定する。新規中間区間では全Sを検査後にintermediate_session_unprocessedを判定する。同日比較はinput_hash、transition_result、state_afterの順で不一致を判定する。

注入入力をコアが拒否した場合と、保存済みSnapshotの内部不整合は区別する。後者でstate_invalid等をsnapshot_invalidへ包むことは、前者のcodeを上書きする規則ではない。台帳照合を先に行うため、コア単体ならrerun_decision_missing等となる入力もS1ではledger_mismatchになる場合がある。

受入条件の詳細は依頼書A-01〜A-08。本設計の中心は、コアを変えず、通常の評価と保存入力からの再計算が同じ純粋関数に到達し、同じDを2回確定しないことである。自動再送や完全なexactly-once配信の証明は含まない。

## 10. 採用時に確認する範囲と後工程

今回ユーザーに求める判断は、別途実装を依頼する際の「S1の範囲・停止契約・受入条件を採用するか」の1組だけに絞る。文書作成の指示を実装承認へ読み替えない。

担当モデルは固定仕様の実装としてSonnet 5.5、エフォートhighを推奨（未採用）。実際のモデルは開始時に環境情報で確認し、確認できなければ不明と記録する。利用量・所要時間は未計測。新しい全面レビューや戦略比較をこの工程へ追加しない。

S1完了後の結果により、S2の保存単位・復旧ポイント・実機検証を具体化する。S3のACK／復元は上位第4版の順序・参照関係を維持する。S4へ進む前にU-01／U-11／U-13と通知の送信権・再送契約をまとめて決める。

保護対象はmain 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、今回の実装基準b616b4e。完全SHAは依頼書§1に記す。第3版では本書・依頼書を更新し、受領したレビュー原文1本を追加する。実装・試験実行・本番操作・PR作成は行わない。

## 11. 第2版の修正記録

本節は第2版保存時の履歴。第3版での全文受領と残り提案への対応は§12を参照。

対象初版：97bdd98324098422ed034d87d5521ecc29dc2689。ユーザーから貼り付けられた2026-10-28のレビュー報告（重大0・通常2・提案8、試験未実施・リポジトリ変更なし）を受領した。リンク先のレビュー全文は取得できていない。以下は本文にある2指摘と、明記された2提案への対応であり、残り6提案を確認・採用した意味ではない。

| 対応 | 修正箇所・受入例 |
|---|---|
| N-01 | §7.2を全中間Sへのselect_decisionに統一。窓外・競合を確定前に拒否。§7.3にcommit後の不変入力でのALREADY_APPLIED契約を追加。依頼書A-04／A-05 |
| N-02 | §5.2／§5.3でnext(D)のclose_at／confirmedのみinput_hash投影から除外。event_hashと保存原本には保持。同日比較は完全なsession_contextの直接一致を求めない。依頼書A-04 |
| エラーcodeの提案 | §9に条件・code・field・優先順位の対応表を追加。依頼書A-02／A-05／A-08 |
| GENESIS境界の提案 | §5.1に明示・確認済みの除外下限、as_of_d=null、初回Dとの関係を記述。依頼書A-02／A-05 |

b616b4eのobservations.py、engine.py、sessions.pyを読み、2指摘の根拠を確認した。今回行ったのは文書の補正と整合性確認であり、実装・試験実行はしていない。S1の範囲、保護5参照、実装未承認、ユーザーPCでの全181件保留は変えていない。

## 12. 全文受領・第3版の対応記録

開始SHA：faff0800b5d2c78cefb3dae37e04491760df0cc9。2026-10-28、ユーザーが貼り付けた[レビュー全文](../reviews/V2_PERSISTENCE_DOMAIN_S1_REVIEW_20261028.md)を受領した。原文のレビュー対象は初版97bdd98であり、第2版／第3版への再レビュー結果に置き換えない。以下は文書案への対応であり、ユーザーによるS1実装承認ではない。

| ID | 文書案での扱い |
|---|---|
| N-01／N-02 | 第2版で修正した全中間区間検査・正常確定後の再実行契約・入力投影を維持。実装での合格はまだ確認していない |
| P-01 | §9のcode／優先順位と依頼§3.2の台帳事象別表で明示。旧行なしの置換と、旧新併存を分ける |
| P-02 | §7.1で必要窓の「どちらか」が欠ければ停止。保存セッション投影の相違はsession_context_mismatch。next(D)の未使用2項目を除く。sessions供給の運用設計はS2／S4へ |
| P-03 | 第2版の境界条件を維持し、§5.2の不要な「前方へ広げる」を除去 |
| P-04 | §8に親hashを求めるS1限定の厳しさとS3での再検討を明記 |
| P-05 | §7.2でPREPAREDの前に候補Snapshotの全検査・再計算を追加。先頭・計画が不変で、障害注入等がなければcommitの同じ検査にも通ることを依頼A-03で確認 |
| P-06 | 依頼A-03で通常経路のengine側の束縛名と、再計算経路の新パッケージ側の束縛名を別々にspy／差替えし、どちらが検証できたかを記録 |
| P-07 | Sonnet 5.5・highを推奨値に追記。選択・確認済みとは書かない |
| P-08 | 依頼§1で上位設計の資料ブランチも読取専用の確認対象に追加。依頼のdisplay.pyをv2_core/display.pyと記載 |

### 後工程へ残す3点

- 市場値は引き続き厳密比較する。調整価格改訂や浮動小数の差でも停止するため、S2／S4で市場データの取得版固定とU-07を一緒に決める。S1へ許容誤差や再取得を追加しない。
- core_shaは版を示す定数であり、実行中のv2_coreの真正性を自己検査しない。依頼A-01でb616b4eとの既存ファイル差分0を確認する前提を結果文書へ残す。
- S1のreconcileは自分と他実行の同一内容を区別しない。S2以降で上位§3.8の自分の保存への到達性を扱う場合、保存方式に応じた計画識別子とスキーマの版上げを別途設計する。送信権の意味を付けない。

今回も文書のみ。本文・コアの読解による整合性確認であり、試験・再現スクリプトは実行していない。ユーザーPCでの全181件は後日実施、S1実装は未承認・未着手のままである。

## 13. 第4版：第3版の確認報告とQ-01／Q-02

開始SHA：8ff1240cd213ce4f5845ded09dfe1bb395c5d07e。ユーザーから、第3版はN-01／N-02と提案8件が反映され、新たな重大・通常問題なし、文書として実装判断へ進める、との確認報告を受領した。これは文書の確認でありS1の実装承認ではない。

- Q-01：§7.2で新規Dの全中間Sにconfirmed=trueを要求。未確定なら準備前に停止し、§6でも未確定の欠測記録を拒否する。next(D)のconfirmed=falseは許容する。依頼A-03／A-05に拒否・確定後の再準備の受入例を追加。
- Q-02：依頼§3.2の「内容違いはledger_mismatch」を、単一行の置換と旧新併存・追加を区別する対応表の意味に揃えた。

変更は設計と依頼の2文書のみ。保存済みレビュー原文は変更しない。今回もコード変更・試験実行はなく、ユーザーPCでの181件確認は後日、S1は実装未承認・未着手のまま。
