# V2 保存ドメイン・単日ランナー オフライン設計案

作成日：2026-10-28  
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

### 5.2 確定入力

confirmed_inputsには次だけを保存する。

- 選択されたdecisionの6項目。既存parse_observationで検査し、同じ意味の入力へ戻せるrawキー名で保存する。値はfloat、時刻はUTC、record_id・status・role・target Dを含む。指紋は既存Observation.fingerprint()を使う。
- DのMarketRow全6項目（date、soxx、sma、rsi、shd、prev_rsi）。
- 直前セッションのMarketRow全6項目、または利用できなかった場合はnull。prev_session_dateは別途必須とする。
- session_context：基準境界からDの次セッションまでの連続した注入セッション列。基準境界は直前state_after.as_of_d、初回はGENESIS.start_after。Dの直前セッションを含むことが必要なら、その日まで前方へ広げる。open_at／close_atをUTCで保存し、confirmedも保持する。

session_contextは新規APPLYでその時点の写しを固定する。同じDの照合では、保存時と同じ日付範囲で現在の注入列を切り出す。無関係な前史や次セッションより先を追加してもinput_hashを変えない。欠けた中間セッション、日付や時刻の改訂、確認フラグの相違は同一入力と扱わない。

市場の数値はboolを拒否し有限floatへ正規化する。soxx・smaは正、rsi・prev_rsiは0〜100、shdは有限値とする。前日行があるならdateはprev_session_dateと一致する。入力に存在しない前日行を補わない。

台帳全体の順序・重複行数、将来行、補助観測、series_meta全体はinput_hashへ含めない。選択decisionと判定に使った確定値が同じなら、同一UTC瞬間の別オフセット表記や同じ行の再提出で同一性を失わない。自由文・URL・口座値・通知内容は保存しない。

本段階が再現するのは市場状態と遷移判定である。SOXL参考終値、b*、待機表示などDayResultの表示全項目の再構築を保証しない。必要なら後続設計で保存項目を増やし、版を上げる。

### 5.3 ハッシュと判定の表現

JSONはキー順を固定（sort_keys=True）、区切りを固定（comma／colon、空白なし）、ensure_ascii=True、allow_nan=False、UTF-8で符号化する。数値の正規化後にSHA-256を計算する。読込時の重複キー、NaN／Infinity、型違い、未知項目は拒否する。

input_hashはconfirmed_inputsの正規化JSONから求める。event_hashはevent_hash自身を除くイベント全体から求める。ヘッダーの先頭とcurrent_stateは履歴から求めた値と一致させる。これは整合性検査であり、悪意ある書換えの真正性や署名を保証しない。

transition_resultはapply_transitionとDayResultの共通部分を明示的に直列化する。rules各件のname／status／ratio／reasons／may_be_unconfirmed、run_class、gap、effective_armed、effective_streak、effective_prev_normal_raw、notesをすべて含める。Enumはvalue、理由やnotesの配列順は保持する。state_afterは別項目に置く。state_updatedと表示項目は含めない。

## 6. 検査と保存入力からの再計算

validate_snapshotは毎回履歴全体を検査する（S1に限る提案。U-10の本番方式を決めない）。

1. スキーマ・型・連続seq・親・各ハッシュ・Dの順序・初期境界を検査する。
2. current_stateと各state_afterをMarketState.from_dictで検査する。直接構築した値で検査を迂回しない。
3. 各APPLYのconfirmed_inputsを再検査する。decisionがDの窓内で、対象D・record_id・指紋がstate_after.fixed_decisionと一致することを確認する。session_contextはSessionList.from_dictsへ渡し、保存した基準境界・prev_session_date・D・next(D)の関係、Dがconfirmed=trueであること、D行の日付も検査する。
4. 当該APPLYの基点は、親イベントのstate_afterからfixed_decisionとbaseだけを落とした値と比較する（IB-04）。同じ値を別の現在状態としてfrom_dictへ渡さない。
5. 親の検査済み市場状態、保存済みの行・decision・prev_session_dateを既存apply_transitionに渡す。候補状態とtransition_resultを全項目比較する。戦略の計算式を新パッケージへ複製しない。
6. skipped_sessionsは、基準境界の次からDの前までのsession_context上の全セッションと一致することを確認する。snapshot.current_stateは最後のstate_afterと一致する。

S1にACK等の状態を変えないイベントは無い。後に追加する際は、IB-04が「現在状態を作ったAPPLYの親」を指す上位設計を維持する。将来の復旧履歴を単純に末尾の状態とだけ比較して処理しない。

## 7. 台帳の検査と単日処理

### 7.1 不一致は停止する限定契約

S1ではACKによる継続や保存入力の補完を実装しない。次のいずれも保存状態を保持して停止する。この停止方式自体が今回の採用提案である。

- 適用済み各Dについて、現在の台帳に保存済みdecisionが無い、指紋が違う、別IDのdecisionが増えた、窓や対象日が不正。
- skipped_sessionsにdecisionが後から追加された。late_observationとし、以前の遷移に自動挿入しない。
- 同じrecord_idの内容違い、不正な入力行。台帳の並び順で勝者を選ばない。

適用済みDの選択は既存select_decisionを使い、保存した窓と今回注入した窓の両方で照合する。両方の窓に必要なセッションが今回のsessionsに無ければsession_context_missingで停止する。欠測区間については各対象Dの窓を今回sessionsから得て、select_decisionで検査する。supplemental／not_checkedはdecisionの代用にしない。

最新Dより先の市場行は参照しない。過去Dを処理しない通常実行で、保存済み市場入力を最新価格へ自動差し替えしない。古い市場行の改訂を新しいDの処理時にもすべて検出する機能はS1の対象外。同じ最新Dの再実行では§7.3の厳密比較で検出する。

上位設計§2.7のACK検証→除外→保存入力から補完→最終検査はS3へ留保する。現在の台帳との不一致を「保存入力があるから正常」と見なさない。

### 7.2 新しいDとdecision無し

検査の順は、snapshot→dと必要sessions→台帳照合→既存evaluate_dayとする。例外の優先順位は同じ段階内では既存コアに従い、S1が返すエラーの分類を新しい試験で固定する。

DはGENESIS.start_afterより後で、現在state.as_of_dより過去であってはならない。初回でも境界とDの間に有効なdecisionがあればintermediate_session_unprocessedで止める。これは初期as_of_dがnullのコア単体では拾わないため、first_unprocessed_sessionにGENESIS.start_afterを渡す前処理で補う。

判定は既存evaluate_dayに委譲する。既存コアの不正入力／衝突を正常なNO_SIGNALへ変換しない。自動で過去Dを再生するループは作らない。

decisionが無ければNO_COMMIT。DayResultは返せるが、イベント・seq・状態は変更しない。decisionがある新しいDでは、候補状態をfrom_dictで再検査し、1件のAppendPlanを返す。この段階ではMemoryStoreを変更しない。

初回に複数セッション空いた場合、初期状態のas_of_dがnullなのでコアのgapはfalseのまま。一方、GENESIS境界からのskipped_sessionsは記録する。通常の欠測後で当日のF&Gが30以上なら、コアどおり終了時streakは1。gapと記録上の欠測区間を同一視しない。

### 7.3 同じ最新Dの再実行

既存evaluate_dayを保存状態で再実行し、保存APPLYのinput_hash、transition_result、state_afterと比較する。同じならALREADY_APPLIEDで計画なし、追記なし。state_updatedだけがfalseになることは比較から除く。判定用の数値が変わった場合、判定結果が偶然同じでもrecompute_mismatchで止める。decisionが変わった／消えた場合は先に§7.1のledger_mismatchで止まる。複数decision等でselect_decision自身が出す既存エラーはそのcodeを保持する。コア単体とラッパーのエラー優先順位の違いを明記して試験する。

過去のD（最新Dより前）をprepare_dayで指定した場合は拒否する。過去記録の検査はvalidate_snapshot、成否不明の照合はreconcileで行う。

## 8. MemoryStoreと更新競合

AppendPlanはexpected_head_hash、expected_head_seq、追加するAPPLYを含む不変の値。現在stateや任意の履歴を置き換えるAPIにしない。

commitはthreading.Lockの同じクリティカルセクション内で、先頭比較、計画と新Snapshotの全検査、1件追記による全体置換を行う。失敗時は元Snapshotを保つ。同じ先頭から2実行が準備した場合、同内容でも1実行だけが成功し、他方はcas_conflict。自動リトライ、番号の繰上げ、新しいDへの読み替えはしない。read／initialize／commit間も同じロックで保護する。

readや各APIの戻り値は深い写しまたは再帰的な不変値とする。frozenなdataclassの内側のdictだけを書き換えられる構造を残さない。入力／戻り値の改変でストアや過去の計画を変えられないことを試験する。

reconcileは、検査済みの読直しSnapshot内に計画のDを探す。計画と同じ親hash、入力hash、transition_result、state_afterを持つAPPLYがあればALREADY_APPLIEDとする。先頭がその後進んでいてもよい。自分が書いた／通知を送れるという意味は持たせない。親が違えば、他の項目が同じでも同一計画の成功とはしない。

同じDで異なる記録があればconcurrent_conflict。該当Dが無ければREPLAN_REQUIREDを返す。先頭が新しいだけでは保存済みと判断しない。古い計画を新しい先頭へ付け替えない。呼出側は新Snapshotで明示的にprepare_dayし直す必要がある。

準備結果のcore_result.state_updatedはコアの「新規遷移候補」の意味を保つ。保存成功フラグに流用しない。外側の結果はPREPARED／NO_COMMIT／ALREADY_APPLIED／COMMITTEDとcommit実施の有無を別に表す。COMMITTEDを返せるのはcommit成功後だけ。準備済み・競合・失敗の候補を本番通知へ流す経路は作らない。

メモリストアは同一プロセス内の比較更新モデルである。プロセス終了後の保存、OSの置換、fsync、複数プロセス、Git pushの成否不明、通信再試行、通知の重複防止は保証しない。

## 9. エラーと受入境界

新規エラーは、snapshot_invalid、unsupported_schema、unsupported_event、store_uninitialized、already_initialized、session_context_missing、ledger_mismatch、late_observation、recompute_mismatch、cas_conflict、concurrent_conflict等、固定された安全なcode／field／ruleで表す。入力値・URL・生行を例外文へ埋め込まない。既存CoreErrorのcodeは保持し、S1の整合性エラーとの違いを結果文書へ示す。

受入条件の詳細は依頼書A-01〜A-08。本設計の中心は、コアを変えず、通常の評価と保存入力からの再計算が同じ純粋関数に到達し、同じDを2回確定しないことである。自動再送や完全なexactly-once配信の証明は含まない。

## 10. 採用時に確認する範囲と後工程

今回ユーザーに求める判断は、別途実装を依頼する際の「S1の範囲・停止契約・受入条件を採用するか」の1組だけに絞る。文書作成の指示を実装承認へ読み替えない。

担当モデルは固定仕様の実装としてSonnet 5.5を推奨。実際のモデルは開始時に環境情報で確認し、確認できなければ不明と記録する。利用量・所要時間は未計測。新しい全面レビューや戦略比較をこの工程へ追加しない。

S1完了後の結果により、S2の保存単位・復旧ポイント・実機検証を具体化する。S3のACK／復元は上位第4版の順序・参照関係を維持する。S4へ進む前にU-01／U-11／U-13と通知の送信権・再送契約をまとめて決める。

保護対象はmain 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、今回の実装基準b616b4e。完全SHAは依頼書§1に記す。今回変更するのは本書と依頼書の新規2文書だけ。実装・試験実行・本番操作・PR作成は行わない。
