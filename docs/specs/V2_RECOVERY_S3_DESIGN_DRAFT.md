# V2 S3 復旧操作設計案・S3-A限定契約

作成：2026-10-29、第2版：2026-10-29（日本時間）。状態：**設計・限定依頼書の作成のみ承認済み。設計案はレビュー待ち、実装は未承認・未着手。**
本書を保存したこと、レビューで問題なしとされたことを実装承認に置き換えない。

## 1. 固定版と現在地

| 用途 | 固定版 |
|---|---|
| 実装基準 | d404d4df481957f89201c5169f3a75d7b9d86b66、fix/v2-local-store-s2-review-20261028 |
| S2完了受領 | [1b5b8ce](https://github.com/Rocky009-jp/soxl-alert/blob/1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a/docs/reviews/V2_LOCAL_FILE_STORE_S2_FIX_RECEIPT_20261028.md) |
| ユーザーPC確認 | [aa21dbe](https://github.com/Rocky009-jp/soxl-alert/blob/aa21dbe85a133c61e8c011a6f78db1b23af0fb13/docs/reviews/V2_USER_PC_TEST_RECEIPT_20261028.md) |
| 上位の保存・復旧設計 | [第4版e3e9094](https://github.com/Rocky009-jp/soxl-alert/blob/e3e90947a718cca877b543739ca60539207ca7a7/docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md)、特に§2.6〜2.8・§4.3・X-07〜X-17 |
| S1／S2の契約 | [S1第4版425df80](https://github.com/Rocky009-jp/soxl-alert/blob/425df80d04b116e25e481184069b89bed1380c3a/docs/specs/V2_PERSISTENCE_DOMAIN_OFFLINE_DESIGN_DRAFT.md)、[S2資料73cec62](https://github.com/Rocky009-jp/soxl-alert/blob/73cec624cb73205ac63ca92e26df2b6f70019b16/docs/specs/V2_LOCAL_FILE_STORE_S2_DESIGN.md) |
| 今回の依頼案 | [V2_RECOVERY_S3A_RESOLUTION_REQUEST.md](../tasks/V2_RECOVERY_S3A_RESOLUTION_REQUEST.md) |

ユーザーPCはWindows／Python 3.10.6で旧b616b4eの181件、d404d4dの既存367件＋Windows専用4件＝371件が合格済み。後日扱いだった181件は解消した。ClaudeのLinux4版は既存367件とS2の109件合格・Windows専用4件skip。主担当の別Windows環境では再現コード5件＋専用4件が合格済み。各環境を合算して単一環境の試験結果としない。

CLAUDE／STATUS／MODEL_POLICY／ROADMAPの該当工程を確認。STATUS等の古い未承認表記は過去の記録であり、今回の文書作成指示を取り消さない。旧文書は変更しない。また、過去の売却境界にある「S3」と、本書の保存・復旧段階S3は別の分類である。

## 2. S3の分割と完了の意味

現行S1はschema_version=1のGENESIS／APPLYだけを検査し、S2もその検査器と単一APPLYのAppendPlanを使う。ACKをS1 Snapshotへ足したりS2に渡したりすれば拒否される。既存検査を弱めて復旧を通す方式は採らない。

| 単位 | 目的・成果 | 今回準備する実装依頼 |
|---|---|---|
| **S3-A** | 原本を残したACK・欠測宣言の意味、入力の除外／補完、計画の指紋と確認を純粋関数で検証する | **本書§3〜§8の限定範囲だけ** |
| S3-B | 復旧記録を含む新しい保存形式、有効／退避履歴、復元＋再計算を1バッチで表す、UNKNOWN再開始 | 後続。Aの結果と保存形式の差分を基に別の具体的依頼を作る |
| S3-C | ローカル正本の明示的解錠・残留物保全・復元計画の実ファイル実行 | 後続。ライター停止と保守操作の排他を確定してから別依頼 |
| S4 | 本番保存先・台帳・実行場所・資格情報・outbox・通知接続 | 今回対象外 |

AはS3全体の完成ではない。S1／S2を変更せず、最も先に必要な「どの観測を使わないと明示したか」を固定する。そのため**AのResolutionSetはメモリ上の検証用データ**であり、正本の新形式や、本番の横置きファイルとして採用しない。プロセスをまたいだ保存・原子性・並行実行を保証しない。

U-01／U-11／U-13は未決。本番・口座・通知・取得・自動対象日・追いつきループ・資格情報・workflow・依存変更は全段階の今回範囲外。S3-Aの実装担当案はSonnet 5.5・high（確定した入力解決と検査の実装）。複雑な未解決の復旧判断は主担当へ戻し、実装担当が範囲を広げない。

## 3. S3-Aの値とAPI

新規パッケージv2_recovery/に置く案。既存v2_core／v2_persistenceは読取利用だけ。パスやストアを引数に受け取らず、実ファイル・ネット・OS時計・プロセス・スレッド・乱数を使わない。JSON文字列との変換だけはよい。

| API | 契約 |
|---|---|
| empty_resolutions() | 空の不変ResolutionSetを返す |
| validate_resolutions(snapshot, resolutions) | S1 Snapshotと解決記録の形・ハッシュ・参照・作成時状態を検査。修復せず独立した検査結果を返す |
| resolve_observations(snapshot, resolutions, sessions, raw_observations, check_d) | §5の順序で最終観測集合と除外／補完の根拠を返す。市場状態を変えない |
| prepare_resolution_plan(snapshot, resolutions, commands, sessions, raw_observations, check_d, request_id, reason_code, requested_at) | 解決記録の候補を全部検査し、READYまたはNO_CHANGEの不変計画を返す。入力は変更しない |
| confirm_resolution_plan(plan, confirmed_plan_hash, snapshot, resolutions, sessions, raw_observations) | §7の一致検査後に新しいResolutionSetと投影結果を返す**純粋な確認**。保存・適用を主張せずcommitted=False |
| prepare_resolved_day(snapshot, resolutions, d, series, sessions, raw_observations) | 解決記録と観測を検査した後、既存v2_persistence.runner.prepare_dayへ1回委譲し、S3-A専用SimulationDayResultへ変換する。AppendPlanは公開しない |
| encode_resolutions／decode_resolutions | メモリ上のJSON文字列との厳密な変換のみ。ファイルI/Oなし |

check_dは呼出側が明示する処理対象日。注入SessionListに存在しconfirmed=true、次セッションが必要。GENESIS.start_afterより後、かつ現在Snapshotの最新APPLY日以上（APPLYなしなら下限だけ）とする。等しい日はS1の再実行経路を認める。新規commandsのDECLARE_MISSING対象Dはcheck_d以下。既存Setにcheck_dより先の宣言があることだけで最新APPLYの再実行を拒否しないが、その宣言窓の検査は省略しない。時計から最新日を決めない。prepare_resolved_dayではdをcheck_dに使い、S1と同じ過去日拒否・中間セッション検査を保持する。過去記録のrequest_basis.check_dは作成時source_headのprefixに対して検査し、後のAPPLY延長で失効させない。

SimulationDayResultの公開項目はstatus、core_result、candidate_event_text（正規化JSON文字列またはnull）、candidate_event_hash（文字列またはnull）、committable=False、committed=Falseに固定。S1のPREPARED／NO_COMMIT／ALREADY_APPLIEDという状態名とコアのstate_updatedの意味は保持するが、S1 PrepareResult、AppendPlan、そのサブクラス、planプロパティを公開しない。空のSetでもこの専用型を使う。S1との「計画一致」はイベントの正規化テキストとevent_hashで比較する。

戻り値・そのイベント文字列をMemoryStore.commit／LocalFileStore.commitへ直接渡すと既存のplan_type検査で拒否されること。イベント文字列から手作業でAppendPlanを再構成するのはS3-Aの契約外で、実装・利用例・試験の通常経路へ変換機能を足さない。これは誤った接続を型で防ぐ境界であり、任意のPythonコードに対する改ざん防止機構ではない。

Snapshot、raw行、SessionList、commands、計画、結果は呼出し開始時に独立した値へ取り、公開の入れ子を変更しても別の値を変えられない。直接構築したMarketStateを検査済み保存状態の代わりに受け取らない。state_afterとbaseは既存from_dict／validate_snapshotへ通す。

### 3.1 ResolutionSetの検証用形式

schemaは固定文字列soxl-v2-resolution-set/1。ヘッダーはschema、head_resolution_seq、head_resolution_hash、recordsのみ。空ならseq=0、hash=null、records=[]。記録は1から連続し、親は直前のresolution_hash、先頭の親はnull。hashは自身を除く全項目の正規化JSONからSHA-256。boolを整数へ受理せず、未知項目・未知種別・非有限値・重複JSONキーを拒否する。正規化は既存canonical_jsonと同じ規則。

各記録の必須共通項目：
resolution_seq、parent_resolution_hash、resolution_hash、request_id、request_hash、request_basis、command_index、command_count、kind、variant、d、source_head_seq、source_head_hash、state_after、record_fingerprints、applied_ref、missing_ref、session_context、frontier_before、ledger_digest、reason_code、requested_at。
該当しない値はnull。kindはACK／DECLARE_MISSINGのみ。

- source_headは作成時のS1先頭を固定する。現在Snapshotの同seqのevent_hashと一致し、その**作成時prefix**をS1で検査できること。source_head_seqは解決記録の順に減少しない。後で同じSnapshotが末尾へ正常に延長されても記録は失効しない。
- state_afterはsource_headまでのprefixのcurrent_stateと完全一致。ACK・欠測宣言でas_of_d／armed／streak／fixed_decision／baseのいずれも変えない。現在Snapshotが後で延長された場合に最新状態との一致を求める誤りをしない。
- applied_refおよびAPPLY型missing_refのseqは、その記録のsource_head_seq以下でなければならない。後から作られたAPPLYを過去の確認根拠へ差し込まない。
- applied_refは{seq,event_hash,fingerprint}。参照先の保存decisionからコアのfingerprintを再計算して一致を確かめる。
- missing_refは{kind:"APPLY",seq,event_hash}、または{kind:"DECLARE_MISSING",resolution_seq,resolution_hash}。名前空間を混同しない。後者は既存の、より古いResolutionSet記録だけを指す。
- record_fingerprintsは小文字16進64桁の重複なし昇順。コアObservation.fingerprint()を使い、record_idだけの除外は作らない。
- ACKのvariantはADDED／CHANGED／ROW_REMOVED／LATE。ACKのsession_contextとfrontier_beforeはnull。DECLARE_MISSINGのvariant／applied_ref／missing_refはnullで、session_contextとfrontier_beforeを持つ。
- request_idはコアrecord_idと同じASCII規則・最大64文字。command_indexは0基点、command_countは正整数。同じrequestの記録は一度だけ連続して存在し、indexが0..count-1までそろう。途中だけのバッチは拒否。
- reason_codeはACKNOWLEDGE_LEDGER_CHANGEまたはMARK_SESSION_MISSINGでkindと対応。混合バッチの呼出しではreason_code="RESOLUTION_BATCH"を認め、各記録にはkind別コードを入れる。自由文・URL・note・source_url・口座項目を追加しない。
- requested_atは注入されたaware日時をUTC文字列へ正規化する。実行順・安全性を時刻から推定しない。request_hashはrequest_id、正規化したcommandsの順序、check_d、reason_codeから計算し、requested_atを含めない。計画の指紋とは別。request_basisとして{request_id,commands,check_d,reason_code,requested_at}を各記録に保持し、requested_atだけを除く投影からrequest_hashを再計算できるようにする。同じバッチ内では元のbasisが全て同一で、各記録の指示・index・countと対応することを検査する。同じ依頼ID・指示で時刻だけ新しくした再提出はNO_CHANGEとし、最初のrequested_atとbasisを保持して上書きしない。ここに生台帳や自由文を含めない。
- ledger_digestは各記録に保存し、計画を捨てても確認時の台帳版の指紋が残る。同じバッチ内で一致し、§6の計算法と同じ64桁形式。過去の生台帳は保存しないため読込時に元台帳との再計算一致を証明したとは扱わない。現在の台帳digestと異なるだけで古い解決記録を失効させない。

S3-Aの解決記録通番はS1のevent seqではない。上位のmissing_ref_seqへそのまま代入しない。永続化時に単一履歴へ写す方式と移行対応表はS3-Bの設計対象。AではS1のschema_version=1とCORE_SHAを変更しない。

## 4. 解決指示の受入条件

commandsは順序付き非空list。指示の形はkind／variant／d／record_fingerprints／applied_ref／missing_refで固定する（不使用値null）。欠測宣言のfrontierとcontextは呼出側の任意値を採用せず、検査済みprefix・既存／先行する宣言・注入sessionsから計算して記録する。新規指示の証拠は**今回の台帳と検査済み保存入力**から確認する。ADDEDの補完権限だけは下表のとおり既存Set／同じバッチの適合するROW_REMOVED・CHANGEDも参照し、指示順に依存させない。一方、既に確認した古い除外行が後で台帳から消えても、そのことだけでは古い解決記録を不正にしない。prepare_resolution_planでは既存Setの構造・参照を先に検査し、現在台帳との最終一致は候補バッチを合わせて検査する。既存Setだけでresolve_observationsの最終検査を一度通ることを、新規計画の前提にしない。

| 指示 | 必要な証拠・効果 |
|---|---|
| ACK/ADDED | 対象DのAPPLYと同じapplied_ref。保存decisionと同じ指紋の行が今回台帳にある、または**同じapplied_ref**のROW_REMOVED／元行なしCHANGEDが検査に通って既存Setか同じ候補バッチにあること。いずれも無ければ拒否。異なるrecord_idの、Dを対象とするかDの窓内にあるobserved/decisionを非空の指紋一覧で名指しして除外 |
| ACK/CHANGED | 同じAPPLY参照。元のrecord_idと同じで指紋が異なる、解析可能な行を非空一覧で名指し。元の行が残れば除外だけ、無ければ保存decisionを1件補う。role/statusの変更も「元行の変更」として名指しできる。新しい版を市場判定へ採用する操作ではない |
| ACK/ROW_REMOVED | 同じAPPLY参照。元の指紋の行が今回台帳に無いこと、record_fingerprintsは空。同じrecord_idの変更版があるならCHANGEDが必要。保存decisionを必要時だけ1件補う |
| ACK/LATE | 対象DにAPPLYが無いこと。missing_refがDをskipped_sessionsに含むAPPLY、またはDのDECLARE_MISSINGを指すこと。applied_ref=null。Dを対象とするか窓内にあるobserved/decisionの非空一覧を除外。**補完はしない** |
| DECLARE_MISSING | 対象DにAPPLYも既存宣言も無いこと。処理frontierの**直後の1セッション**だけを対象にする。下記の宣言適格性を満たし、今回のD対象／D窓内のobserved/decisionすべての異なる指紋を名指しする（0件なら空）。同じrecord_idの未処理2版から1つだけ選ばない。Dを確定状態へ進めず、記録した行を除外する |

### 4.1 全指示に共通する版の選択禁止

全生行を解析して、record_idごとの異なる指紋の集合を保持する。今回、解決記録によって実際に除外する行のrecord_idに別の版があり、その版が**除外・補完後の最終集合に残る**場合は、残る版が検査済みS1 APPLYの固定decisionの指紋と一致する場合だけ許す。それ以外はresolution_invalid、rule=version_selection。CHANGEDの元行併存と、明示確認による保存済み固定行の補完はこの例外で維持する。最終のコア検査も省略しない。

DECLARE_MISSING／LATE／ADDEDだけで、未処理の同ID別版を一つ選ぶ操作も拒否する。全版を外す場合も各指示の対象・frontier・証拠の条件を満たしたバッチでそれぞれを名指しする。任意の日の行を外す包括的な指示は作らない。全部を適法に名指しできなければ台帳を修正する。

### 4.2 欠測宣言の適格性（主担当の改訂案）

S3-Aでは、Dに関係するdecisionが0件か、宣言なしではDに関係する妨害によってdecision_conflict／record_id_conflict／target_mismatch／decision_outside_windowとなる場合だけを宣言対象とする。異なる指紋数で数え、同一行の再提出は1件とする。正常な有効decisionが1件だけのDはrule=declare_valid_decisionで拒否する。別の日だけの無関係なrecord_id_conflictを理由に、その有効1件を欠測へ変えない。

Dに関係する妨害とは、Dを対象またはD窓内とするobserved/decisionの不正な関係・複数decision、およびその行と同じrecord_idの別版による衝突をいう。関連する同IDの別版は別の日や異なるrole/statusでも確認する。既存Setによる適法な除外・補完を考慮し、既に解決済みの衝突だけを宣言の根拠にしない。この適格性の確認は全行の解析後、新規宣言による除外を行う前に行う。

decisionはコアどおりobserved/decisionを指す。not_checked／supplementalも全行の解析と同ID別版の検査から外さない。解析不能行は従来どおり宣言で回避できない。有効な1件を意図的に捨てる操作・追いつき上限のための一括欠測はS3-Aへ追加しない。この方針自体も設計案であり、ユーザーによる実装採用は未承認。

どの指示も、**有効なS1 APPLYの固定decisionと同じ指紋を除外してはならない**。他の日の固定行を隠す指示も拒否。適用済みDを欠測へ変更する機能や、未処理decisionの版の選択（CORRECTION／U-03）は作らない。上位のCHANGED ACKが適用済み旧版を維持することと、未処理の複数版から新たな採用値を選ぶことを区別する。

frontierは、対象記録の作成時prefixの最新APPLY日（無ければGENESIS.start_after）と、その時点までのDECLARE_MISSING日の遅い方。複数日の宣言は直後から1日ずつ明示する。同じバッチでもresolution_seqの小さい宣言を後の記録のfrontierに数える。D、次(D)の順は可能で、逆順はdeclare_frontierで拒否する。Dとfrontierを含む注入列、次(D)までの必要contextを保存し、Dとそれ以前に使うセッションはconfirmed=trueとする。宣言が無い期間を飛ばす通常のAPPLYは、既存S1の検査とskipped_sessionsによる。AにはRESTART_UNKNOWNが無い。

古い記録のfrontierは作成時prefixで検査する。後でAPPLYが延長された現在のfrontierを使って過去の宣言を拒否しない。宣言済みDにAPPLYを直接足した不正な組合せはvalidate_resolutionsで拒否する。宣言はprefixの市場状態を変えず、欠測規則は次のAPPLYにだけ効く。

宣言対象を「次の1日」に限定するのは上位案より狭いS3-Aの提案で、未処理の中間decisionを黙って飛ばさないため。まとめて任意区間を宣言するAPIは後続へ留保する。GENESIS境界以前や、APPLY・skipped_sessions・宣言のどれにも属さず、本書§4のいずれの指示の適法な対象にもならない行の衝突はS3-Aでは解決できない。台帳の修正で直し、未対応のACKや全行除外へ範囲を広げない。

## 5. 観測の投影：順序を固定

1. S1 SnapshotとResolutionSetを検査。必要なsessionsとcheck_dを検査し、6列だけの台帳の写しを取る。
2. **全行をparse_observationで個別に解析**。解析できない行は除外対象にもできず停止。ここでは同じrecord_idの異なる版を先に全体衝突として拒否しない（正しいCHANGED／欠測宣言が作用する前に止めない）。
3. 解決記録の参照を全て検査。新規計画では§4の今回台帳の証拠も検査する。ADDEDのROW_REMOVED／CHANGEDによる補完権限は候補バッチ全体で検証し、ADDEDを先に並べても同じ最終観測集合・補完件数にする。commandsの順序はrequest_hashと記録順に保持するため、指示順を入れ替えた別依頼のplan_hash／記録hashまで同一であることは要求しない。
4. 指紋が一致する行だけを除外。同じ指紋の再提出は全て除く。自由文やrecord_idだけで除外しない。
5. ROW_REMOVEDまたはCHANGEDを根拠に、保存済み固定decisionが最終集合に無ければその6列を1件だけ補う。元行があれば補わない。ADDED／LATE／DECLARE_MISSINGを補完権限にしない。
6. **版の選択禁止と最終集合を検査**。§4.1のversion_selection検査を補完後の集合に対して行い、未処理版の選択が残れば拒否する。その後、同一指紋はコアと同じ再提出として一つに正規化。各APPLYに保存と一致するdecisionが一つあり、他のdecisionが無いこと。skipped_sessionsとDECLARE_MISSINGにはdecisionが無いこと。既存select_decisionを保存窓・今回窓とcheck_dについて使い、最終集合の全record_id衝突もコアに検査させる。不正な行を取り除くために解析検査を省略しない。
7. 正規化した最終raw6列、実際に除外した指紋、補ったAPPLY参照を独立した値で返す。既存prepare_dayへ渡すのはこの最終rawだけ。raw原本、Snapshot、解決記録は変更しない。

適用済みDの現在sessionsとの比較はS1と同じ投影（next(D)のclose_at／confirmedだけを落とす）を使う。DECLARE_MISSINGの保存contextも対象Dに対して同じ投影で比較する。日付・open_atやD以前の値、必要なセッションの欠落は停止。翌セッションの確定フラグが後日変わっただけで恒久停止させるN-02型の誤りを再導入しない。

空の解決記録では、正常なケースで既存S1 prepare_dayと判定・イベントの正規化テキスト／hash・状態が一致すること。結果型は§3のSimulationDayResultであり、AppendPlanの型一致を要求しない。解決記録がある場合にも通常計算はS1へ委譲し、戦略の式・閾値・遷移を複製しない。宣言済みDの判定はS1が許す対象日ならdecision無しのNO_COMMITとなり、次のAPPLYのgap／streakはコアの値を保持する。例えば欠測後のF&G≥30ならstreak=1であり0ではない。

複数の既存不一致は一つのcommandsバッチで解決してよい。候補全体の最終検査が通るまでREADYを返さない。別の不一致が残れば停止し、一部の解決記録だけを返して継続しない。無関係な将来Dの扱いは既存コアの範囲を維持する。

## 6. 指紋・参照の固定

生台帳の参照は、全行のparse_observation結果を正規化した6列のリストから作るledger_digest。行順はソートして無視し、完全な同一行の**個数は保持**する。6列以外は保存しない。数値はコアのfloat、not_checkedの空値はnull、時刻はUTC。UTC／JSTで同じ瞬間の表記は同一。fingerprintは常に既存Observationの関数を使う。

snapshot_digestはS1 Snapshotの正規化JSON全体、resolutions_digestはResolutionSet全体のSHA-256。hashは署名・真正性・台帳の完全性を証明しない。source_headの参照だけで現在Snapshot全体を確認したことにしない。

sessions_digestは**計画の確認専用**として、注入列全体のdate／open_at／close_at／confirmedを正規化して計算する。計画中に翌セッションのconfirmedだけが変わっても確認はstaleとなり、計画を作り直す。これは短期の人手確認を厳しく結び付ける提案で、§5の通常実行時の投影とは別。既に確認済みの解決記録を、この全列digestで毎日失効させてはならない。

## 7. 計画と確認（Aでは保存しない）

計画のbasisに、操作形式の版、snapshot_digestと期待先頭seq/hash、resolutions_before_digest、request_id／request_hash、requested_at（今回の確認用時刻）、check_d、ledger_digest、sessions_digest、正規化commands、候補ResolutionSet全体とそのdigest、状態不変の期待値、除外／補完の結果を含める。plan_hashはbasis全体のSHA-256。候補記録はplan_hashを項目に持たず、循環したハッシュ定義を作らない。

表示は種別、対象D、件数、参照通番／指紋、状態不変、plan_hashだけのホワイトリスト。reprやエラーにraw行、F&G値、パス、URL、自由文を混ぜない。構造化APIのEffectiveLedgerにはコアへ渡す6列を持つが、ログへ自動出力しない。

確認は次の順にする。

1. 型・形式とconfirmed_plan_hashを検査し、plan_hashを再計算して一致を確認。
2. Snapshot、解決記録、sessions、台帳を再びコピー・検査し、現在値の全digestと期待先頭がbasisと一致することを確認。
3. 元commandsから候補と投影を再構築し、basisの候補・結果と完全一致することを確認。
4. 新しいResolutionSetとEffectiveLedgerを返す。status=CONFIRMED_IN_MEMORY、committed=False。市場状態は不変。COMMITTEDや「保存済み」と表示しない。

request_idが既にResolutionSetにあり、正規化したrequest_hashが違えばresolution_request_conflict。同じなら新規記録を足さずNO_CHANGE（現在の投影検査は省略しない）。requested_atだけが新しくても同じrequest_hashとして、元の記録・元時刻・ledger_digestを保持する。既存requestの照合は全行解析後、新規指示の証拠検査より先に行う。同じrequestでは消えた古い指紋の再提示を求めず、既存Setの投影を検査する。同じ計画を確認後の候補Setへもう一度確認する場合も、元Snapshot・台帳・sessionsが同一、現在Setが計画の候補Setと**全体一致**するときだけNO_CHANGE。それ以外の先頭変更やSetへの別の追加を勝手にマージせずstaleとする。NO_CHANGEもcommitted=False。

入力不一致、偽造計画、不正hash、候補途中での失敗では元Snapshot／元Set／原本台帳が深い値で不変であること。これはファイルCASや同時実行の証明ではない。

### 7.1 エラーの分類

| 条件 | code／field |
|---|---|
| S1保存内容不正 | 既存snapshot_invalid／unsupported_schema等を保持 |
| 生の観測・check_d・sessions不正 | 既存InputError／ConflictErrorを保持 |
| 解決形式・鎖・参照・状態の不正 | resolution_invalid／resolutions、固定ruleを付ける |
| 新規ACKの対象・指紋・証拠が不適合 | resolution_invalid／commands、rule=ack_evidence |
| 適用済み固定行を除外する指示 | resolution_invalid／commands、rule=exclude_applied |
| 宣言が直後の1日でない／適用済み | resolution_invalid／commands、rule=declare_frontierまたはdeclare_applied |
| 宣言の名指し不足・余分な指紋 | resolution_invalid／commands、rule=declare_incomplete |
| 宣言のD・必要な中間セッションが未確定 | resolution_invalid／commands、rule=declare_unconfirmed |
| LATEの欠測参照が不適合 | resolution_invalid／commands、rule=late_missing_ref |
| 除外によって未処理の同ID別版が残る | resolution_invalid／commands、rule=version_selection |
| 衝突していない有効decision1件の欠測宣言 | resolution_invalid／commands、rule=declare_valid_decision |
| 必要な保存／現在session範囲が欠損・不一致 | session_context_missing／sessions、session_context_mismatch／sessions |
| 最終の既存APPLYと台帳が不一致 | ledger_mismatch／observations（コアのrecord_id_conflict等が先に出る場合はそのcode） |
| 最終の欠測日にdecisionがある | late_observation／observations（窓外等のコアエラーがあればそのcode） |
| request_idを異なる内容で再利用 | resolution_request_conflict／request_id |
| 計画改変・確認hash不一致 | resolution_plan_mismatch／plan |
| 基点・Set・台帳・セッションの確認時変更 | resolution_plan_stale／plan |

優先順はSnapshot→解決記録の構造・参照→明示日と必要sessions→全行解析→新規指示の証拠（宣言の適格性も含む）→除外・補完→version_selection→最終コア検査→計画の確認。confirmの計画自体の形式・hash検査だけは入力の再検査より先とする。同時に複数の違反があるときはこの優先順を使う。例えばcheck_d自体が未確定なら、宣言のdeclare_unconfirmedより先に既存target_unconfirmedで停止する。型名・raw値・生の例外文を表示せず、例外連鎖も安全に抑える。

prefix検査は、現在Snapshot全体を既存validate_snapshotで1回検査し、その検査済みイベントhash・state_afterから各作成時prefixを参照する実装でもよい。同じ検査を記録数だけ再実行する必要はない。未検査のprefixを受け付けたり、呼出し間で変わる入力へ古い検査結果を使い回したりしてはならない。最適化は任意で、性能の追加受入条件にはしない。

## 8. S3-A受入条件

[依頼書](../tasks/V2_RECOVERY_S3A_RESOLUTION_REQUEST.md)のC-01〜C-14を固定する。重要な反例は、ROW_REMOVEDの補完前に止めない、CHANGED旧行併存時に二重補完しない、LATEに存在しない固定decisionを要求しない、DECLARATION後の後発行を黙って除外しない、同じrecord_idの衝突を除外前に確定しない、確認時の入力変更と戻り値の参照共有である。

## 9. S3-B：復元・再初期化の設計境界（今回の実装対象外）

S1にACK等を直接足す方式は不可。S3-Bでは新形式（schema_version=2等）を明示的に定義し、S1／S2のschema=1と混同しない。候補は「全記録を守る直前記録の監査鎖」と「現在状態を決める有効親」の分離。seqは旧S1に合わせ0基点で連続し、有効親だけを過去へ分岐させても退避記録の欠落・変更を検出できるようにする。版・コア互換・旧Snapshotの保存・明示変換・参照の写像を一組で具体化してから依頼する。AのResolutionSetを別ファイルとしてS2正本と個別に更新する実装は不可。

復元案の必須条件：

- 復元先は現在有効な履歴内の検証済み記録。既に退避した記録への再接続は不可。通番は全監査履歴で増やし、使い回さない。
- 計画は、復元点から旧有効先頭までの**有効な記録だけ**をちょうど列挙してsupersededとする。単純な通番区間で他の既退避記録を混ぜない。
- 現在状態と基点の関係は「現在状態を作ったAPPLYの親のstate_after」。末尾がACKでも比較相手を変えない。
- 復元点以後のACK／DECLARE_MISSING／RESTART_UNKNOWNの扱いも計画へ明記する。APPLYだけを再生してこれらを黙って落とさない。新しい通番への参照写像と、除外・補完の再検査が必要。
- 退避APPLYと台帳のdecisionが食い違えば計画に差を示して停止する。復元を値の訂正・新しい版の選択の抜け道にしない（U-03は別工程）。市場入力の再計算差も計画に表示し、任意の新値を自動採用しない。
- 確認した計画hashと期待先頭に対する1回の比較更新で、RECOVERY_RESTORE、再計算したAPPLY群、新しい現在状態、解決記録を**一括公開**する。途中の復元状態だけを保存しない。
- 過去Dの通知意図は作らず、保存主体・配信権を論理一致から推定しない。旧outboxが将来存在しても独立に保全する。
- RESTART_UNKNOWNは有効履歴を消さず、state_afterを初期状態にする。resume_afterは最後のAPPLYだけでなく、既にDECLARE_MISSINGで処理済みとした日や直近の開始境界も下回らない。ACK／宣言は新しい開始境界を動かさない。
- 壊れた正本の「検証できるprefixを探す診断」と、完全に検査済みの候補を正本へ採用する操作を区別する。破損suffixを無視してvalidと返さない。元の生バイトと破損部分の証拠を失わない方式が要る。

上位§2.6・R-2の意味を維持するための条件であり、ここまでで新形式の全キーや破損採用手順が確定したとは扱わない。S3-Bの別依頼作成前に、形式・参照写像・複数回復元・制御記録の再生・破損証拠の5点を具体化する。

## 10. S3-C：明示的解錠と実ファイル復旧（今回の実装対象外）

S2の残留write.lockは、古い・PIDが存在しない・時刻が過ぎた、だけでは削除しない。ユーザーが「停止済み」と入力しても、プロセス停止の機械的証明にはならない。

将来の計画→確認→実行は次を満たす必要がある。

1. 旧S2ライターを含む**全ライターを停止**し、通常処理との併走を防ぐ保守手順を確立。新しいmaintenanceマーカーを旧S2が見ないまま、それだけで排他できるとはしない。対象rootと稼働場所の管理範囲を決める。
2. 正本・ロック・管理tmpの名前、型、identity、所有マーカー、バイトのdigestを読取診断する。リンク／reparse／非通常ファイルを追わず、壊れた正本にも元のバイトの証拠を残す。候補tmpを「新しいから正しい」と昇格しない。
3. 専用の退避場所へ元の証拠を保全し、保存水準を満たしたことを確認してから、計画で名指しした残留物だけを扱う。他者所有・途中で変わった物は触らず停止。通常の成功したwrite.lockの解放とは別の監査記録を残す。
4. 公開直前にrootと全対象のidentity／digest、確認hashと期待先頭を再検査。どれかが変われば計画を無効にし、他のファイルの自動掃除へ切り替えない。
5. 監査記録・退避・ロック除去は複数のファイル操作になる。中断後に正本が更新可能なまま証拠だけ欠ける区間を残さない、保守ゲートと再開規則を設計する。失敗後に自動解錠を再試行しない。
6. 復元バッチの公開はS2同様、完全な候補のfile fsync／replace／選択したdirectory同期。replace呼出し開始後の失敗は成否不明。論理照合だけで失敗した同期の成功を宣言しない。Windows strictは今回未対応のまま。

S3-C前に未決のもの：全ライターの列挙・停止の証拠と責任範囲、旧S2と共存しない移行方法、保守ゲートのクラッシュ時契約、退避先の管理名と同期水準、解錠中断後の明示再開条件。これらを空欄のまま「安全なforce-unlock」APIを実装しない。実PCの電源を切る試験は要求しない。

## 11. 今回の判断対象と作業記録

今回ユーザーが承認したのは**文書作成**。次に採用する場合の最初の単位は「S3-Aの純粋な入力解決と計画だけ、既存コード不変、C-01〜C-14、Sonnet 5.5・high」。S3-B／Cや本番を一括承認する文言は使わない。

主担当は固定版のコード・文書を読んで本書と依頼書を作成した。コード変更、試験実行、新市場計算、実ファイル復旧、状態変更、PR、Actions、送信は0。モデル別利用量は未計測。保存は新しい資料ブランチのみ。保護参照の一覧と開始／終了時の照合は依頼書に記す。


## 12. 第2版のレビュー対応（2026-10-29）

根拠：[Claudeのレビュー本文](../reviews/V2_RECOVERY_S3_S3A_REVIEW_20261029.md)。対象は初版8b79f97c551bda1af07fe08063d36e1d22c49659、重大0・通常4・提案7。レビューはコードと文書の読解によるもので、実行による再現ではない。レビュー本文は取得したテキストを別ファイルに保管する（末尾改行を付与。元ファイルのバイト単位照合は未実施）。以下は主担当の文書補正であり、修正コードの試験合格を意味しない。

| ID | 第2版の対応 |
|---|---|
| N-01 | 専用SimulationDayResultだけを公開し、空SetでもAppendPlanを返さない。C-12／C-14でcommitの型拒否を確認する |
| N-02 | 元行欠落＋別ID追加を、同じapplied_refのROW_REMOVED／CHANGEDとADDEDの一括確認で扱う。補完後は固定行1件 |
| N-03 | 全指示にversion_selection禁止を適用。残る版が既存APPLYの固定指紋のときだけ例外を維持 |
| N-04 | 有効decision1件を欠測へ変える案を採らず、0件またはDに関係する妨害の場合だけ許す設計案へ補正 |
| P-01 | request_hashからrequested_atを除き、同じ指示の再提出は元時刻のままNO_CHANGE。plan_hashは時刻を含む確認対象全体を保持 |
| P-02 | ledger_digestを各解決記録に保存。現在台帳との一致を恒久条件にしない |
| P-03 | 同一バッチの先行宣言をfrontierへ数え、順序・逆順の期待を固定 |
| P-04 | check_dのGENESIS／最新APPLYとの境界、新規宣言の上限、再実行の許可を明記 |
| P-05 | declare_incomplete／declare_unconfirmed／late_missing_ref／version_selection／declare_valid_decisionをエラー表と受入条件へ追加 |
| P-06 | 解決範囲外の衝突は台帳修正が必要と明記。包括的除外へ拡張しない |
| P-07 | 全Snapshotを1回検査した結果からprefixを参照する最適化を許容。任意事項で、検査の省略は不可 |

保留：宣言取消はS3-Bで検討。上位の「decision行」は今回observed/decisionとしてコアに合わせ、not_checkedも入力・版の検査は受ける。S3-A実装、試験実行、実ファイル復旧、本番接続は引き続き未着手・未承認。
