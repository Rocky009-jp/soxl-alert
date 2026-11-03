# V2 CONSUME・S3-C 設計案（C-1 CONSUMEの限定依頼つき）

作成日：2026-11-03（日本時間）。版：初版。
状態：**初版・設計案・採否判断待ち。C-1の限定実装は未承認。C-2〜C-4は方針案だけで、依頼書はまだ作らない。**
Rockyさんの「CONSUME/S3-Cの設計を始めてください」を受けて作成した。今回の作業は設計書・限定実装依頼書の作成と、一時環境での試行まで。文書の保存、推奨、試行の合格を、実装の承認と扱わない。作成担当はClaude Opus 5.5、effort high（このスレッドのセッション設定）。

## 0. 要約

- **範囲の読み方**：「CONSUME」はS3-B第2版§8.7で未決とされた、復元（RECOVERY_RESTORE）の5つ目の処分である。「S3-C」はS3第3版§10・S3-B第2版§9で後回しにされた、v2履歴の実ファイルへの公開・照合・明示解錠・元バイトの退避・移行の実行である。前者は純粋な計算、後者はファイル操作で、性質が違う。本書はこの二つを4つの単位に分ける（§2、D-1）。
  - **C-1 CONSUME**（純粋・メモリ内）：検査器（B-1）と復元計画（B-4）にCONSUMEを加える。**今回の限定依頼はこれだけ。**
  - C-2 公開値と照合（純粋）：DAILY・RESOLUTION・RESTART・RESTORE・MIGRATION・ADOPTIONの確認結果から、1種類の公開値を作り、現在のバイト列に対するCASの検査と成否不明後の照合を純粋関数で行う。
  - C-3 v2ローカル正本：v2履歴を1ファイル（history.json）として読み、追記の公開値を一時ファイル→fsync→1回のreplaceで公開する。解錠・移行・採用はしない。
  - C-4 保守操作：明示解錠、残留物と元バイトの退避、v1→v2移行の実行、prefix採用の実行と、その中断後の再開規則。
- **C-1を先にする理由**：C-3以降で実ファイルに書く前に、保存される記録の文法（検査器が受け付ける形）を閉じておくため。CONSUMEは記録のキーを増やさない（S3-B第2版§8.6で`{op:"CONSUME", d}`の形を予約済み）が、検査器の規則は変わる。純粋な計算なので既存の進め方（計画→hash指定確認→候補Historyまで）にそのまま乗り、一時環境の試行で動くことも確かめた（§7）。
- **CONSUMEの規則（D-2）**：復元の処分が「解放した日」（DROPした宣言の日、DROPした再開始が飛ばした日、REAPPLYで新たに飛ばす日。B-4§8の定義そのまま）だけを、呼び出し側が位置を明示して消費できる。決定は残す記録の台帳投影から、市場値は注入seriesから取り、既存apply_transitionで新しいAPPLYを作る。最終のB-2全区間投影とevaluate_dayで同じ結果になることを確かめる。CONSUMEしない解放日に有効な決定があれば、今までどおりrestore_requires_consumeで止まる。
- **B-5b再レビューの提案P-02（D-3）**：元バイトなしの確認（NO_CHANGE）で返った採用計画の`discarded`と`diagnosis_digest`は、形しか検証されていない。後段（CONSUME・公開値・通知・台帳）では使わず、表示するなら「未検証」と書く。捨てた後半の明細を何かに使うなら、元バイトでCONFIRMED_IN_MEMORYを得た計画からだけ取る。CONSUMEは採用記録や`discarded`を一切読まない（§4）。
- **範囲試験の新規則（D-5）**：test_sc_03のENDを受領済みのbfbde7aに1行で固定し、C-1の範囲試験は新しいディレクトリにEND=None／REVの形で書く。前の段階の差分は書き写さない。既存試験の補正は「CONSUMEを拒否していることを確かめていた」4本の静的な部分だけ（§6）。
- **一時環境での試行**：bfbde7aのコピーにC-1を試作した（pushしない）。既存11スイート1668件がPython 3.12.3と3.13.18で全件合格（既存試験の補正6件を含む）。CONSUMEの成功・拒否の25項目（使い捨てのプローブ）がすべて期待どおりだった（§7）。
- 運用方針は日足のみ（早朝に米国の確定日足で通知し、夜の寄付きで手動購入）。分足・NBBOは前提にしない。CONSUMEも日足の決定と日足の市場値だけを使う。
- 採否はD-1〜D-6の一組（§8）。

## 1. 目的と固定入力

| 用途 | 固定版 |
|---|---|
| 起点（コード・試験） | **bfbde7a7854bf91a77fb58737c24b19c6507453a**（fix/v2-scope-range-freeze-review-20261103）。範囲試験の固定のR-01修正（試験対象00094cc）に結果文書の追記を加えたもの。B-5bのR-01修正b626c98を含む |
| 範囲試験の固定の受領 | 再レビュー9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d（docs/reviews/V2_SCOPE_RANGE_FREEZE_FIX_REREVIEW_20261103.md、重大0・通常0・提案0、受領推奨）。Rockyさんが「推奨どおり」で受領（2026-11-03） |
| 範囲試験の規則 | 設計08072cc47aa12340ed947d40f02ca8741a4060d6のdocs/specs/V2_SCOPE_RANGE_FREEZE_DESIGN_DRAFT.md §6（D-3）。次の段階はtest_sc_03のENDを1行で固定し、新しい範囲試験はEND=None／REVの形で書く |
| B-5b再レビュー | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b、docs/reviews/V2_RECOVERY_S3B5B_FIX_REREVIEW_20261103.md §5 P-02 |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md、特に§8.6〜8.8・§9・§11・§14のD-3/D-7 |
| B-4設計（第2版＋補足） | 0108131045d904b0997299fcade5929567940d6d、docs/specs/V2_RECOVERY_S3B4_RESTORE_PLAN_DESIGN_DRAFT.md、特に§2.2・§5・§7.1・§8 |
| S3設計第3版 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c、docs/specs/V2_RECOVERY_S3_DESIGN_DRAFT.md §10（S3-Cの必要条件と未決） |
| 上位の保存・復旧設計 | 第4版e3e90947a718cca877b543739ca60539207ca7a7、docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md（R-2、§3.8） |
| 運用方針 | プロジェクトの運用方針（2026-10-26）：日足単位の判定。早朝に米国市場の終値で通知し、夜の寄付きで買う。分足・NBBOは前提にしない |

読解対象：bfbde7aのv2_history（restore.py、view.py、validate.py、values.py）、v2_history_restore（全10ファイル）、v2_history_ops（batch.py、read.py）、v2_history_adopt（confirm.py、values.py）、v2_persistence（runner.py、events.py、local/store.py）、v2_core（engine.py、observations.py）、試験のr4_helpers・h06・h14・r4_01・r4_03・r4_09・test_sc_03、上の各設計。共通のCLAUDE.md・STATUS・MODEL_POLICYも確認した。古いSTATUSの承認待ちの記述によって、B-5bまでと範囲試験の固定の受領を取り消さない。

## 2. 範囲の読み方と分割（D-1）

### 2.1 これまでの設計がCONSUMEとS3-Cに残したもの

| 出典 | 残したもの |
|---|---|
| S3-B第2版§8.7・D-3 | 復元でCONSUMEを許すか。B-1は`restore_op_unsupported`で拒否。条件案：退避したAPPLYと同じDではない、requestバッチの再生の間に挟まない、市場入力はseries・決定は新しい鎖の台帳投影から取る、後続REAPPLYがfalseになる差を示す |
| B-4設計§2.2・§8 | CONSUME保留中は解放日に有効な決定があれば`restore_requires_consume`で止める。採用するなら「B-1検査器・復元バッチ・受入条件を改める別の限定依頼」 |
| S3-B第2版§9.1〜9.4・D-7 | 公開値（HistoryReplacement／HistoryAppendBatch）の実装、新しいアダプタの公開側の契約、成否不明後の照合の条件 |
| S3第3版§10 | 全ライター停止の手順、残留物の読取診断と退避、公開直前の再検査、保守ゲートと再開規則、Windows strict。未決：全ライターの列挙・停止の証拠、旧S2と共存しない移行、保守ゲートのクラッシュ時の契約、退避先の名前と同期水準、解錠中断後の明示再開 |
| B-2・B-3・B-4・B-5b | 各確認結果（候補History）をストアへ渡す値への統合。照合（ALREADY_PUBLISHED等）。元バイトの退避と新しい正本の公開 |
| B-5b再レビューP-02 | NO_CHANGE経路のdiscarded・diagnosis_digestを未検証値として後段に渡す |

### 2.2 4つの単位

| 単位 | 中身 | 性質 | 今回 |
|---|---|---|---|
| **C-1 CONSUME** | B-1検査器と B-4復元計画へのCONSUMEの追加（§3） | 純粋・メモリ内。既存2パッケージを変える | **限定依頼を作る** |
| C-2 公開値と照合 | 6種の確認結果から1種類の公開値、現在のバイト列へのCAS検査、成否不明後の照合（§5.2） | 純粋。新パッケージ | 方針案のみ |
| C-3 v2ローカル正本 | history.jsonの読込みと、追記の公開値の公開（§5.3） | ファイル操作。新パッケージ | 方針案のみ |
| C-4 保守操作 | 明示解錠、残留物・元バイトの退避、v1→v2移行の実行、prefix採用の実行、中断後の再開（§5.4） | ファイル操作。ユーザーの手順を含む | 方針案のみ。§5.5の未決を先に決める |

本番の保存先・台帳・実行場所・資格情報・通知（上位U-01／U-13、S4）は、どの単位にも含めない。

### 2.3 順序の推奨：C-1 → C-2 → C-3 → C-4

- **C-1を最初にする**：C-3で実ファイルに書き始めると、検査器が受け付ける記録の文法を後から広げるたびに、すでに保存した履歴との関係を考えることになる。CONSUMEは記録のキーを増やさないので古い履歴はそのまま有効だが、検査器の規則とplan・changesの形は変わる。書く前に閉じておくほうが安全である。C-1は純粋な計算で、既存の計画→確認の型に乗る。
- **C-2をC-3の前にする**：公開値とCAS・照合を純粋関数で先に固定すれば、C-3はI/Oと実行の正しさだけを担えばよい（B-2の推奨R-aと同じ考え方）。
- **C-4を最後にする**：明示解錠・移行・採用は、ユーザーの停止手順と退避先の決め方（§5.5）に依存する。C-3の通常の公開が先に動いていれば、C-4は「通常でない状態からC-3の通常状態へ戻す操作」として定義できる。
- 代わりの案として「C-3を先にして早く保存を動かす」もある。ただし移行（v1→v2）と採用はC-4なので、C-3だけでは既存のv1ファイルを持つ環境は動かない。現在、本番のv1ファイルもv2ファイルも存在しない（S2は本番正本に採用されていない）ので、急ぐ理由は小さい。

## 3. C-1 CONSUMEの設計（D-2）

### 3.1 何を直せるようになるか

CONSUMEが無いと、次の取消は「取り消した日に今は有効な決定がある」限り実行できない（B-4§8、restore_requires_consume）。

| 場面 | 例 | CONSUMEで行うこと |
|---|---|---|
| 欠測宣言の取消 | 朝に決定が無く D3をDECLARE_MISSINGにしたが、実は D3の決定は窓内に記録されていた（台帳に後から入った）。D4も進んだ | 復元点をD3の前に取り、DECLAREをDROP、**CONSUME D3**、D4をREAPPLY（基点がD3に変わるのでsame=false） |
| 宣言＋LATE ACKの取消 | DECLARE D2の後にD2の決定が届き、LATE ACKで除外した | DECLAREとLATE ACKをともにDROP、**CONSUME D2**、間のAPPLYをREAPPLY |
| 早すぎた再開始の取消 | RESTART_UNKNOWN(D3)で D2・D3を飛ばしたが、D2には決定があった | RESTARTをDROP、**CONSUME D2**（D3にも決定があれば**CONSUME D3**も）、D4をREAPPLY |
| 暦の変更で新たに飛ばす日 | 現在のカレンダーにセッションが加わり、REAPPLYする日が新しく飛ばす日に決定がある | その日を**CONSUME**してからREAPPLY |

どの場面でも、市場状態は日足の決定と日足の市場値だけで再計算する。過去の日の通知の意図は作らない（S3-B第2版§8.8の7）。

### 3.2 記録の形（キーは増やさない）

S3-B第2版§8.6が予約した形をそのまま使う。RECOVERY_RESTOREの15キー、replay項目の5キー、APPLYのキーは変えない。

- request_basis.opsの要素：`{op:"CONSUME", d}`（2キー。dは日付文字列）。他の4処分は従来どおり`{op, from_seq}`。
- replayの要素：`{op:"CONSUME", from_seq:null, d, seq, same_as_superseded:null}`。seqは作られたAPPLYの物理seq。
- opsとreplayは同じ順・同じ長さ。**CONSUMEを除いた列**が、退避する記録を鎖の順に1回ずつ名指しする（従来の規則）。CONSUMEはその間の任意の位置に入れてよく、作られる記録はopsの順に途切れずに並ぶ。
- 作られるAPPLYは通常のAPPLYと同じ形で、confirmed_inputsのdecisionは台帳の決定、row・prev_rowは注入seriesの値、session_contextは区間の基点からnext(D)まで、skipped_sessionsは基点とDの間の全セッション日。

### 3.3 検査器（B-1、v2_history/restore.py）の規則

検査器は、履歴の中の記録だけから確かめられることを確かめる。台帳・注入sessions・seriesが要る規則（どの日が解放日か、決定と市場値が正しいか）は計画（§3.4）で確かめる。これはREAPPLYの決定や市場値を検査器が台帳と照合しないのと同じ分担である。

| 規則 | 拒否（history_invalid／history／rule） |
|---|---|
| replayの要素が5キーで、CONSUMEのとき対応するopsの要素が`{op:"CONSUME", d}`と同じ | restore_replay_mismatch、request_basis |
| CONSUMEのfrom_seqとsame_as_supersededはnull、dは日付 | restore_replay_mismatch |
| CONSUMEを除いたreplay・opsが退避列と同じ長さ・順・処分の許可（従来どおり） | restore_replay_mismatch、restore_op_kind、request_basis |
| CONSUMEのdが、退避するAPPLYのどれかのdと同じでない | restore_consume_applied_day |
| 同じdのCONSUMEは1回だけ | restore_consume_duplicate |
| CONSUMEが、同じrequestバッチ（ACK／DECLARE_MISSING）の記録に対する2つの処分の間に入らない | restore_consume_in_batch |
| 作られた記録がAPPLYで、そのdがCONSUMEのdと同じ。履歴がその途中で終われば未完了 | restore_incomplete、restore_replay_mismatch |
| 作られたAPPLYは、それを含む鎖ビューで通常のAPPLYの規則（S1射影の再計算、skipped_sessions、session_context、宣言日との重なり）を満たす | 既存のs1:\*、declare_applied等 |

- requestバッチの間の禁止は、そのバッチをREPLAYするかDROPするかを問わない（単純で強い規則にする）。
- 解放日であることは検査器では確かめない（D-2の(ii)）。検査器でも確かめる案は§3.9に書く。
- `restore_op_unsupported`は、未知の処分名（小文字の"consume"を含む）に対して残す。

### 3.4 計画（B-4、v2_history_restore）の規則と順序

B-4設計§5の段階を保ち、CONSUMEの検査を次の位置に入れる。

| 段階 | 変更点 |
|---|---|
| 2 | check_opsが`{op:"CONSUME", d}`を受け付ける（形の誤りはops_shape、未知の名前はrestore_op_unsupported）。CONSUMEを除いた列で退避列との一致・種別ごとの処分・バッチの部分処分を従来どおり検査し、続けてCONSUMEの3規則（退避APPLYの日でない、重複しない、requestバッチの間に入らない）を検査する |
| 4 | 市場値を固定する日を、REAPPLYとCONSUMEの日についてopsの順に読む（series_inputs）。CONSUMEのprev_session_dateは注入sessionsのprevious(D)。**決定は、残す記録（復元点までの有効列）のFixedFactsとLedgerContextに、変更しないapply_recordsで残す記録の解決記録を当てた行から、変更しないselect_decisionで選ぶ。** 決定が無ければrestore_consume_no_decision。下書きの組立て（plan_records）でCONSUMEのAPPLYを作り、区間の基点がD以上ならrestore_consume_order。組立ての後、**CONSUMEの各日が解放日（B-4§8の定義を、候補の適用日で除く前の集合）に入ること**を確かめ、入らなければrestore_consume_not_released |
| 5 | 変更なし（RESTOREのhash→後続記録の連結→候補全体のvalidate_history） |
| 6 | 変更なし（REPLAYの証拠の再検査、候補全体の事実と行の事前集合） |
| 7 | 事前集合でCONSUMEの各日の決定をselect_decisionで選び直し、使った決定（record_idと指紋）と違えばrestore_decision_changed（detail=D）。続けて従来の新規消費の検査（CONSUMEした日は候補の適用日なので除かれる）→REAPPLYの決定→REAPPLYの市場値 |
| 8 | 最終のproject_history_ledgerと事前集合の一致→**REAPPLYとCONSUMEのすべての日**を変更しないevaluate_dayで新しい親の状態から計算し直し、作ったAPPLYのtransition_result・state_afterと一致すること→無効果の検査（DROPもCONSUMEも無く、全REAPPLYがsame=trueのときだけrestore_no_effect）→basis |

- 決定を「残す記録の行」から取るのは、hashの循環を避けるためである（候補の最終投影は、候補ができるまで計算できない）。CONSUMEする日は解放日であり、残す記録の後にあるので、残す記録の解決記録はその日の行に触れない。段階7の選び直しは、REPLAYした解決記録が同じ日の行を除外している矛盾（例：その日のLATE ACKを再生しながら、その日を消費する）を止める安全柵である。
- evaluate_dayは最終投影の一致の**後**にだけ呼ぶ（B-4のN-02と同じ順序）。CONSUMEで作るAPPLYも、REAPPLYと同じく既存apply_transitionで作り、evaluate_dayの結果と比べる。戦略式・閾値・状態の式を書かない。

### 3.5 決定・市場値・セッション範囲

- **決定**：§3.4段階4の行から選ぶ。既存select_decisionの誤り（decision_outside_window、target_mismatch、decision_conflict等）はそのまま返す。補完行（ROW_REMOVED等）はAPPLY済みの日にしか生じないので、解放日には現れない。
- **市場値**：注入seriesのthrough(D)の写しから、row(D)、row(previous(D))（取得できなければnull、既存コアと同じ）、previous_date(D)を読む。previous_date(D)・注入sessionsのprevious(D)が一致しなければsession_series_mismatch。値の形の誤りはrestore_invalid／series／market_input（B-4§9と同じ）。D後のデータ、SOXLの表示価格、系列の説明は使わない。
- **セッション範囲**：基点（その区間の最後のAPPLY日、無ければ区間の境界）からnext(D)まで。間の全セッションはconfirmed（違えばintermediate_session_unconfirmed）。基点が注入sessionsに無ければsession_context_missing。
- 日足の確定値だけを使う。分足・NBBO・発注時刻は扱わない。

### 3.6 計画値の変化

- basisは23キーのまま、operationは"soxl-v2-history-restore-plan/1"のまま。CONSUMEを含まない計画の値は、C-1の前と同じ文字になる（試行で、CONSUMEを扱わない既存のB-4試験〔r4_01・r4_09の補正箇所以外〕が変更なしで合格したことで確かめた。§7。正式には依頼書C1-14で示す）。
- opsはCONSUMEの要素`{op:"CONSUME", d}`を含み得る。
- series_inputsはREAPPLYとCONSUMEの日をopsの順に並べる。CONSUMEの項目はfrom_seq=null（6キーは同じ）。
- changesはopsと同じ長さ・順。CONSUMEの行は`{op:"CONSUME", from_seq:null, kind:"APPLY", d, to_seq, same_as_superseded:null, changed_fields:[]}`。後続REAPPLYのsame_as_superseded=false・changed_fieldsが、CONSUMEによる差を示す（S3-B第2版§8.7の「後続のREAPPLYがfalseになる差を示す」）。
- summaryの表示は従来の白リスト（固定のop・種別・フィールド名、日付、seq、sameフラグ）に"CONSUME"が加わるだけ。値・市場値・F&G・自由文は出さない。

### 3.7 確認

B-4設計§11の手順を保つ。変更点は次のとおり。

- 段階1の形の検査で、opsの要素は`{op, from_seq}`（4処分）か`{op:"CONSUME", d}`、series_inputsの項目のfrom_seqはnullも可、changesのCONSUMEの行は§3.6の形だけ。
- 段階2で、現在のseries_inputsをplanのopsから同じ方法（REAPPLYは元prefixの保存値、CONSUMEは注入sessionsのprevious(D)）で読み直す。CONSUMEする日の市場値が変わればseries_digestが変わり、history_plan_stale。
- 段階4の再構築・全basis比較・同じ候補へのNO_CHANGEは従来どおり。

### 3.8 エラー表（追加分）

| 状況 | code／field／rule・detail |
|---|---|
| CONSUMEの要素の形（キー、日付） | restore_invalid／ops／ops_shape |
| CONSUMEが退避するAPPLYの日 | restore_invalid／ops／restore_consume_applied_day（detail=D） |
| 同じ日のCONSUMEが2つ | restore_invalid／ops／restore_consume_duplicate（detail=D） |
| CONSUMEがrequestバッチの間 | restore_invalid／ops／restore_consume_in_batch（detail=D） |
| 残す記録の行にその日の決定が無い | restore_invalid／ops／restore_consume_no_decision（detail=D） |
| 区間の基点がD以上（CONSUMEの位置が日付の順に合わない） | restore_invalid／ops／restore_consume_order（detail=D） |
| CONSUMEした日が解放日でない | restore_invalid／ops／restore_consume_not_released（detail=D） |
| 事前集合での決定が、使った決定と違う | restore_decision_changed／observations（detail=D） |
| CONSUMEしない解放日に有効な決定がある | restore_requires_consume／ops（detail=D）。従来どおり |
| 検査器 | history_invalid／history／restore_consume_applied_day、restore_consume_duplicate、restore_consume_in_batch、restore_replay_mismatch、request_basis、restore_incomplete |

既存のInputError・ConflictError・select_decisionの衝突・S3-Aの誤り・最終B-2台帳の誤りはそのまま。detailには日付だけを入れ、行のreprや値を出さない。

### 3.9 変えないこと・残る制限・代わりの案

- B-4§7.1の既知の制限（案a：REPLAYの証拠をprefixごとに再検査するので、正当な履歴でも拒否する2例）はそのまま残る。CONSUMEはこれを解消しない。
- 解放日の定義（B-4§8）は変えない。CONSUMEで解放日を広げない。解放日でない日（例：REPLAYで残した宣言の日、復元点より前の日、復元の範囲外の日）は消費できない。
- 自動の補完をしない：決定のある解放日をCONSUMEで自動的に足さない。呼び出し側がopsで位置ごとに名指しする（B-4§4の「自動並べ替えや省略の補完をしない」と同じ）。
- 現在の市場値の許容差や自動更新は入れない（U-07は別判断のまま）。
- 検査器で解放日も確かめる案（D-2の(i)）：記録だけから解放日を再計算する（DROPした宣言のd、DROPした再開始の(直前のfrontier, resume_after]を記録内のsession_contextから読む、REAPPLYの新旧skipped_sessionsの差）。台帳を使わずに書けるが、検査器の規則が大きく増え、暦の扱い（注入sessionsと記録内のsession_contextのどちらで数えるか）の判断が要る。計画で確かめる案(ii)を推奨する。
- B-5b設計のrestore_before_adoptionにより、復元点は採用記録より前に取れない。したがってCONSUMEは、採用で捨てた後半の日に届かない（§4）。

### 3.10 最小例（試行で確かめた形）

D0〜D6は連続した確定セッション。例の名前はB-4の試験の合成ビルダー（r4_helpers）のもの。

| 例 | 操作 | 期待 |
|---|---|---|
| ex_declare_between（0 GENESIS、1 APPLY D1、2 RESTART(D1)、3 APPLY D2、4 DECLARE D3、5 APPLY D4）＋D3の決定X3 | P=3、ops＝DROP 4、CONSUME D3、REAPPLY 5 | READY→CONFIRMED_IN_MEMORY→同じ候補にNO_CHANGE。changes＝DROP(D3)、CONSUME(D3)、REAPPLY(D4, same=false)。新しいD4はskipped_sessions=[] |
| 同上、CONSUMEなし | DROP 4、REAPPLY 5 | restore_requires_consume（D3）。従来どおり |
| 同上、X3なし | DROP 4、CONSUME D3、REAPPLY 5 | restore_consume_no_decision |
| 同上 | DROP 4、REAPPLY 5、CONSUME D3（順序違い） | restore_consume_order |
| 同上 | REPLAY 4、CONSUME D3、REAPPLY 5 | restore_consume_not_released（宣言を残すのでD3は解放されない） |
| ex_restart_over_gap（0 GENESIS、1 APPLY D1、2 RESTART(D3)、3 APPLY D4）＋D2・D3の決定 | P=1、DROP 2、CONSUME D2、CONSUME D3、REAPPLY 3 | READY。D2だけCONSUMEするとrestore_requires_consume（D3） |
| ex_declare_then_late（1 APPLY D1、2 DECLARE D2、3 APPLY D3、4 LATE ACK D2が後発L2を除外） | P=1、DROP 2、CONSUME D2、REAPPLY 3、DROP 4 | READY。CONSUMEした決定はL2。LATE ACKをREPLAYするとrestore_ref_unmapped（参照先の宣言をDROPするため） |
| ex_declare_tail、ex_null_restart（後続APPLYが無い・基点が初期状態） | DROP、CONSUME | READY |

## 4. B-5b再レビューの提案P-02の扱い（D-3）

**根拠**：B-5bの確認（confirm_prefix_adoption）は、渡されたバイト列が候補そのものの正規化テキストのときNO_CHANGEを返す。この経路では元バイトが無いので、計画の`discarded`（捨てる後半の件数・明細）と`diagnosis_digest`は、形と計画内の整合しか検証されない（003b6dc §2・§5、独立プローブBで形が正しく内容が偽の値384件を区別できないことを確認）。

**規則**：
1. NO_CHANGE由来の採用計画の`discarded`・`diagnosis_digest`は「未検証の値」とする。通知・台帳・CONSUME・公開値・照合の判断に使わない。表示する場合は、その値が未検証であることを同じ表示に書く。
2. 捨てた後半の件数・明細を何かに使う場合は、元バイトでCONFIRMED_IN_MEMORYを得た計画からだけ取る（このとき確認は元バイトから診断と計画全体を作り直して比べているので、値は検証済み）。
3. 採用の公開値（C-2）は、元バイトでCONFIRMED_IN_MEMORYを得た計画と、その同じ元バイトからだけ作る。NO_CHANGEは公開値を作らず、照合（「すでに候補である」）の結果として扱う。
4. 元バイトの退避（C-4）の証拠は、ロックの下で読み直した実ファイルのバイトのsha256・長さから作り、計画の値をそのまま写さない。計画のraw_sha256・raw_sizeとは一致を確かめるだけに使う。
5. **CONSUMEは、採用記録のevidence、採用計画の`discarded`・`diagnosis_digest`を一切読まない。** 採用で捨てた後半の日は、通常の日次の追いつき（B-2のprepare_history_day）で台帳から消費し直す（S3-B第2版§11）。CONSUMEの解放日は復元の処分（DROP・REAPPLY）からだけ決まり、復元点は採用記録より前に取れない（restore_before_adoption）。

C-1の範囲では、規則5をC-1の範囲試験（v2_history_restoreがv2_history_adopt・v2_history_diagnoseを読まないこと、"discarded"・"diagnosis"の語を持たないこと）で確かめる。規則1〜4はC-2・C-4の依頼書で受入条件にする。

## 5. S3-Cの設計方針（C-2〜C-4。今回は依頼しない、D-4）

### 5.1 日足だけの運用から決まること

- ライターは1日1回の早朝の処理（米国の確定日足で計算して通知する処理）だけである。日中の分足処理や、同じ日に何度も書く処理は前提にしない。したがって、並行して書くのは「定時処理」と「人が行う保守操作」の重なりだけを考えればよい。
- 定時処理がロックの残留（前回の異常終了）を見つけたときは、store_busyで止まり、保存できなかったことを知らせる（通知の接続はS4）。**自動で解錠しない。** 保守は、早朝の通知の後、夜の寄付きの前の日中に人が行う。
- 夜の寄付きでの購入は人が行う（自動発注なし）。保存の失敗は購入の判断材料（朝の通知）が欠けることとして扱い、前日値で埋めない（CLAUDE.md §6）。
- 保守の前提となる「全ライターの停止」は、定時処理を止めた（スケジューラで無効にした）という人の宣言で代える。機械的な証明はできないので、宣言を計画の入力に含め、結果文書・監査記録に「停止の宣言による」と書く（S3第3版§10の1）。

### 5.2 C-2 公開値と照合（純粋、新パッケージ案 v2_history_publish）

- **公開値HistoryPublication**：不変の`{body, publication_hash}`。bodyの主な項目：operation、mode（APPEND／REPLACE）、source（DAILY、RESOLUTION、RESTART、RESTORE、MIGRATION、ADOPTION）、request_id・plan_hash（DAILYはnull）、期待する現在（APPENDは{head_seq, head_hash, history_digest}、REPLACEは{raw_sha256, raw_size}と移行ならv1のhead）、追加する記録（APPEND）または候補全文（REPLACE）、candidate_digest・candidate_head_seq・candidate_head_hash・candidate_state_digest。
- **作り方**：確認済みの結果からだけ作る。B-2のHistoryAppendBatch（check_append_batchで検査）、B-3・B-4の確認結果（CONFIRMED_IN_MEMORYだけ）、移行の確認結果と元のv1バイト、採用の確認結果と元バイト（CONFIRMED_IN_MEMORYだけ、§4の3）。作る関数は計画の値を信用せず、候補Historyを検査し、期待する現在のdigestを候補の物理prefixから計算し直す。NO_CHANGEの結果からは作らない。
- **CAS検査**：`check_publication(current_bytes, publication)`は、現在のバイト列を厳格に読み、完全に検査し、期待と比べて候補Historyを返す（違えば公開値が古い）。
- **照合（S3-B第2版§9.4、D-7への回答案）**：`reconcile_publication(current_bytes, publication)`は、成否不明の後に読み直した現在のバイト列について、(a)候補と同じ→ALREADY_PUBLISHED、(b)候補が現在の物理prefixで、その後に記録が続く→ALREADY_PUBLISHED（後続あり）、(c)期待した現在と同じ→NOT_PUBLISHED（再計画ではなく同じ公開値で再試行してよい）、(d)それ以外→CONFLICTを返す。誰が書いたかは示さず、通知の権利も与えない。S1の「同じ親hash」条件は使わない。
- B-2のHistoryAppendBatchと既存パッケージは変えない（新パッケージから使うだけ）。

### 5.3 C-3 v2ローカル正本（ファイル操作、新パッケージ案 v2_history_local）

- 専用のrootに、v2の正本`history.json`を1つ置く。ロックはS2と**同じ名前のwrite.lock**をO_EXCLで作る（S2のライターとv2のライターが互いに排他される）。マーカーの中身は別（v2用の固定語＋乱数）。期限・奪取なし。一時ファイルは`.history.<乱数>.tmp`。
- rootの状態：空（初期化だけ可）、history.jsonだけ（通常）、snapshot.jsonだけ（v1。C-3は拒否し、移行はC-4）、両方（拒否、C-4の再開対象）、一時ファイルの残留（S2のものも含め拒否）、ロックあり（store_busy）。
- 読込み：ロックの下で残留物を走査し、バイトを読み、厳格に復号（decode_history）し、validate_historyで完全に検査する。
- 公開：APPENDの公開値だけを受け付ける。ロックの下で読み直し→C-2のcheck_publication→候補の正規化テキスト→一時ファイル→全量書込み→flush→fsync→close→ロックの所有確認→1回のreplace→（strictなら）ディレクトリfsync。replace呼出しの開始以後の失敗は成否不明とし、読取り専用の照合（C-2）を案内する。REPLACEはC-4へ。
- S2のFileOps（v2_persistence.local.fsops）は変更せずに使う案を推奨する（S3-B第2版§9.3で「S3-Cで決める」とされた点）。S2の公開API・privateメソッドは呼ばない。
- Windowsのstrictは、S2と同じく明示的に拒否する（file_sync_onlyは可）。実Windowsの確認は別途。

### 5.4 C-4 保守操作（ファイル操作＋人の手順）

- **共通の型**：読取り専用の診断→計画（対象の名前・型・identity・digestを名指し、人の停止宣言を含む）→hash指定の確認→実行。実行の直前に診断をやり直し、計画と1つでも違えば何もしない。失敗後に自動で再試行しない。
- **退避先**：rootの下の`quarantine/<依頼ID>/`をO_EXCLで作る。最初にMANIFEST（計画hash、対象、digest）を書いてfsyncし、その後で対象を退避する。保存水準はストアと同じ（strictならファイルとディレクトリのfsync）。
- **明示解錠**：残留した一時ファイルは中身を退避先へ写してfsyncし、digestを確かめてから消す。write.lockは最後に退避先へrename（原子的）する。中断した場合は、退避先のMANIFESTと残りの対象を診断し、MANIFESTの対象の部分集合でdigestが同じときだけ再開できる。
- **prefix採用の実行**：ロックの下でhistory.jsonの元バイトを読み、§4の4で照合し、退避先へ写してfsyncしてから、候補を一時ファイル→replaceで公開する（正本のファイルが無い時間を作らない）。replaceの後で中断したら、照合が「すでに候補」を返す。
- **v1→v2移行の実行**：ロックの下でsnapshot.jsonのバイトを計画と照合し、history.jsonを一時ファイル→replaceで作り、ディレクトリをfsyncしてから、snapshot.jsonを退避先へrenameする。途中で中断するとsnapshot.jsonとhistory.jsonが両方ある状態とロックの残留になる。C-3は両方ある状態を拒否するので、旧S2ライターもv2ライターも書けない。再開は、history.jsonが計画の候補と同じで、snapshot.jsonが計画の元バイトと同じときだけ、renameを行う。
- 旧S2ライターは保守のマーカーを見ないが、同じ名前のwrite.lockで公開の瞬間は排他される（S3-B第2版§9.3）。明示解錠でロックを外した後に旧ライターが動き得るのは、停止の宣言が正しくない場合だけで、これは残る前提として明記する。

### 5.5 C-4の依頼前に決めること（S3第3版§10の未決への回答案）

| 未決 | 回答案（未採用） |
|---|---|
| 全ライターの列挙・停止の証拠と責任範囲 | ライターは日次の定時処理1つと保守操作だけ（§5.1）。停止は人の宣言で代え、計画に固定語として入れる。機械的な証明とは書かない |
| 旧S2と共存しない移行方法 | 同じwrite.lockで排他し、移行の最後にsnapshot.jsonを退避先へrenameする。両方ある状態はC-3が拒否する（§5.4） |
| 保守ゲートのクラッシュ時の契約 | 新しい保守マーカーは作らず、write.lockを保守操作が保持する。中断後はロックの残留となり、明示解錠（再開）でだけ外す |
| 退避先の管理名と同期水準 | `quarantine/<依頼ID>/`、MANIFEST先行、ストアと同じ保存水準 |
| 解錠中断後の明示再開条件 | MANIFESTの対象の部分集合で、digestとidentityが同じときだけ。他のファイルの自動掃除へ切り替えない |
| 実行場所・本番保存先 | S4（U-01／U-13）。C-3・C-4は一時ディレクトリでの試験とユーザーPCでの確認まで |

## 6. 範囲試験（D-5）

### 6.1 前の段階の固定（1行）

tests/v2_scope_chain/test_sc_03_scope.pyの`END = None`を、受領した最終コミットの完全SHAに替える。

    END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"

dda7eb7ではない（R-01修正の最終がbfbde7a。再レビュー9fe3e19 §4）。この1行のほかは、test_sc_01〜03を変えない。test_sc_02（範囲の鎖）はHEADを基準に読むので、固定後もHEADの鎖を監査し続ける（R-01の修正）。

### 6.2 C-1の範囲試験

- 新しいディレクトリ`tests/v2_history_consume/`に`test_c1_*.py`と`c1_helpers.py`を置く。`__init__.py`は作らない。既存の試験ディレクトリには新しいファイルを足さない。
- 範囲試験は`START = "bfbde7a…"`、`END = None`、`REV = END or "HEAD"`の形で書き、git差分・中身・blob・一覧をすべてREVから読む。作業ツリーを読まない。
- 前の段階の範囲試験の差分を固定文字列で書き写さない。C-1が直した既存試験4本（§6.3）は、その削除行・追加行・ハンクを**C-1自身の差分として**固定する。
- 範囲の鎖の試験（test_sc_02）が、新しい範囲試験を自動で見つけ、`adfdf765→…→b626c98→bfbde7a→（C-1、END=None）`の鎖を確かめる。試行で、固定後の鎖が通ることを確かめた（§7）。

### 6.3 既存試験の補正（静的な部分だけ）

試行で、CONSUMEを実装すると次の6件が失敗した。いずれも「CONSUMEを拒否すること」または「CONSUMEの名前・APPLYを作る場所が無いこと」を確かめていた試験で、仕様の変更に合わせて期待を直す。固定済みのFilesChangedクラス・END・固定定数には触れない。

| ファイル | 試験 | 補正 |
|---|---|---|
| tests/v2_history/test_h06_restore_batch.py | test_consume_is_not_supported_in_b1 | 名前をtest_a_consume_entry_of_the_wrong_form_is_refusedに替え、5キーでないCONSUMEの要素・opsより多いreplayの要素の期待をrestore_op_unsupported→restore_replay_mismatchにする（2行） |
| tests/v2_history_restore/test_r4_01_point_ops.py | test_consume_and_unknown_operations_are_refused_with_any_keys | `{op:"CONSUME", from_seq}`の期待をops_shape、退避列を名指ししない`{op:"CONSUME", d}`だけの列の期待をsuperseded_mismatchにする（2行）。小文字・未知の名前の3行は変えない |
| tests/v2_history_restore/test_r4_09_scope.py（Runtimeクラス） | test_only_the_allowed_modules_and_names | ALLOWED_NAMESのv2_persistence.eventsにdecision_dictを1つ加える |
| 同 | test_consume_is_only_a_refusal | CONSUME_NAMESを、C-1で使う名前の固定の一覧（CONSUME、restore_consume_\*等）に広げる。従来の2名が含まれることは確かめ続ける |
| 同 | test_a_new_apply_is_made_only_from_the_day_of_the_record_it_replaces | APPLYを作る場所の期待を`[("records.py","_reapply")]`→`[("records.py","_reapply"), ("records.py","_consume")]`にする。_reapplyのdが元記録のdであることの検査は変えない |
| 同 | test_the_operations_that_may_be_written_are_four_and_everything_else_is_refused | OPS（退避記録を名指しする4処分）は4つのまま。`{op:"CONSUME", from_seq}`の期待をrestore_op_unsupported→ops_shapeにする |

h14（B-1の範囲）・b17・r3_07・d5_08・a5_08の静的な部分、a5_07の監査は、試行で変更なしに合格した。

## 7. 一時環境での試行（2026-11-03、Linux）

**位置づけ**：方式の確からしさを確かめるための使い捨ての試行である。bfbde7aから作ったローカルの作業ツリーで、C-1のランタイムを試作し、§6の補正と1行の固定、仮の範囲試験1本（変更パスの集合だけを見るもの）を加え、pushしないローカルコミットで試験した。CONSUMEの例は使い捨てのプローブで確かめた。正式な実装、受入試験、レビューの代わりにしない。

環境：Linux、Python 3.12.3と3.13.18、`PYTHONDONTWRITEBYTECODE=1`、`-B -W error::ResourceWarning`。Windows、3.10・3.11、unshareによる通信遮断は実施していない。

| スイート | 起点bfbde7a（3.13） | 試作後（3.12／3.13） |
|---|---|---|
| コア tests/v2_core | 197 OK | 197 OK |
| 保存 tests/v2_persistence | 170 OK | 170 OK |
| S2 tests/v2_persistence_local | 113 OK（skip 4） | 113 OK（skip 4） |
| S3-A tests/v2_recovery | 176 OK | 176 OK |
| B-1 tests/v2_history | 230 OK | 230 OK（h06の1件を補正） |
| B-2 tests/v2_history_ops | 173 OK | 173 OK |
| B-3 test_r3_\* | 109 OK | 109 OK |
| B-4 test_r4_\* | 165 OK | 165 OK（r4_01の1件、r4_09の4件を補正） |
| B-5a test_d5_\* | 131 OK | 131 OK |
| B-5b test_a5_\* | 170 OK | 170 OK |
| 範囲の鎖 test_sc_\* | 34 OK | 34 OK（test_sc_03のENDを固定） |
| 合計 | **1668件合格** | **1668件合格（skip 4はWindows専用）** |

補正前（ランタイムだけを試作した時点）の失敗は、h06の1件、r4_01の1件、r4_09の4件、test_sc_03の3件（ENDを固定していないため。§6.1の1行で解消）だった。仮の範囲試験1本も合格し、範囲の鎖の試験が新しい開いた範囲を受け入れた。

**CONSUMEのプローブ（25項目、すべて期待どおり）**：§3.10の各例のREADY→CONFIRMED_IN_MEMORY→同じ候補へのNO_CHANGE、changesの中身、新しいAPPLYのskipped_sessions、series_inputsの並び（CONSUMEはfrom_seq=null）、CONSUMEなしでのrestore_requires_consume、restore_consume_no_decision／order／applied_day／not_released／duplicate、ops_shape、宣言を残した場合のnot_released、宣言＋LATE ACKをDROPしてL2の決定で消費、LATE ACKを再生した場合のrestore_ref_unmapped、evaluate_dayがREAPPLYとCONSUMEの両方の日に呼ばれること、計画後にCONSUMEの日の市場値を変えると確認がhistory_plan_staleになること、検査器がCONSUMEの日と作られたAPPLYの日の違い・CONSUMEのfrom_seqをrestore_replay_mismatchで拒否すること。

試作の差分（ランタイム8ファイルと試験5ファイル、計13ファイル、+310／−65行、仮の範囲試験を含む）は、同じ資料コミットのdocs/specs/V2_CONSUME_C1_TRIAL_20261103.diffに参考として保存する（未適用。SHA-256は§9）。実装者はこれを写すのではなく、§3と依頼書の規則に従って作り、違いがあれば結果文書で説明する。試作は受入試験・欠陥注入・正式な範囲試験・名前の整理を含まない。

## 8. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | 範囲の読み方と分割：CONSUMEとS3-Cを4単位（C-1 CONSUME、C-2 公開値と照合、C-3 v2ローカル正本、C-4 保守操作）に分け、C-1→C-2→C-3→C-4の順に進める。今回の限定依頼はC-1だけ | 採用を推奨。C-3を先にする案は、移行・採用がC-4にあるため単独では使えず、急ぐ理由も小さい（§2.3） |
| D-2 | CONSUMEの規則：記録の形（キー追加なし、§3.2）、(ii)検査器は形・位置・日の規則だけで解放日は計画が確かめる（§3.3・§3.4）、決定は残す記録の行から取り段階7で選び直す、市場値は注入series、evaluate_dayは最終投影の後、CONSUMEしない解放日は従来どおり停止、無効果の規則にCONSUMEを加える、計画の外形は23キー・"/1"のまま | (ii)を推奨。(i)検査器でも解放日を確かめる案は、規則と暦の判断が増えるので推奨しない（§3.9） |
| D-3 | P-02の扱い：§4の規則1〜5。C-1では規則5を範囲試験で確かめ、規則1〜4はC-2・C-4の受入条件にする | 採用を推奨 |
| D-4 | S3-Cの方針：§5の方針（日足だけの運用で決まること、C-2の公開値と照合、C-3のhistory.jsonと共有write.lock、C-4の退避先・明示解錠・移行と採用の順序・再開条件）を設計案として受け取り、C-2以降の依頼書はC-1の受領後に別に作る。§5.5の回答案はC-4の依頼前に改めて判断する | 方針として受け取ることを推奨。今回の採否はC-2〜C-4の実装承認ではない |
| D-5 | 範囲試験：test_sc_03のEND＝bfbde7a（1行）、C-1の範囲試験は新しいディレクトリtests/v2_history_consume/にEND=None／REVの形、既存試験の補正は§6.3の4本6件の静的な部分だけ | 採用を推奨 |
| D-6 | C-1の実装単位と担当：対になる依頼書の範囲（ランタイムはv2_history/restore.pyとv2_history_restoreだけ、新しい試験ディレクトリ、結果文書）。担当はSonnet 5.5・high | 採用を推奨。規則と試行の差分が具体的で、既存の型に乗る。矛盾や規則の追加が必要なら止めて主担当へ返す |

D-1〜D-6を一組で判断する。今回の文書作成と一時環境の試行は採用ではない。範囲試験の固定の受領を、C-1の実装承認にしない。C-2〜C-4、全体稼働、本番保存先・資格情報・通知は今回の採否に含まない。

範囲外として残すもの：B-5b再レビューの提案P-01（a5_09に厳密整数の回帰を足す。次にtest_a5_09を触る機会）、範囲試験の固定のレビューの提案P-02（git_show_at_endの本文の固定。任意）、B-4§7.1の既知の制限（案a）、U-03（CORRECTION）、U-07（市場値の許容差）。

## 9. 作業記録

- 担当モデル：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
- 開始時（2026-11-03T11:24Z）に、範囲試験の固定の依頼§7の65参照＋docs/v2-scope-range-freeze-20261103（08072cc）＋feat/v2-scope-range-freeze-20261103（dda7eb7）＋docs/v2-scope-range-freeze-review-20261103（fa4b232）＋fix/v2-scope-range-freeze-review-20261103（bfbde7a）＋docs/v2-scope-range-freeze-fix-rereview-20261103（9fe3e19）の計70参照を、`git ls-remote`の完全SHAで照合し、70件とも一致した。終了時の照合は依頼書§7と結果の報告に記す。
- 本書、依頼書、試行の差分の3ファイルだけを、bfbde7aから作った新しい資料ブランチdocs/v2-consume-s3c-20261103に追加した。製品コードの変更、PR、Actions、送信、新しい市場計算は0。一時環境の作業ツリーとローカルコミットはpushしていない。
- 試行の差分docs/specs/V2_CONSUME_C1_TRIAL_20261103.diffのSHA-256は 03a28e4f422fdfd0f666fd4dad128e897c0c7d99db9505ab7ae595e713b7f35c（一時環境のbfbde7a→試作後の`git diff`の出力そのまま。対象は v2_history、v2_history_restore、tests/v2_history、tests/v2_history_restore、tests/v2_scope_chain、tests/v2_history_consume）。
- モデル別の利用量は未計測。
