# V2 S4-A 朝の1回の実行（オフライン） 限定実装 レビュー

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由の依頼（2026-11-04T15:34Z）。実装者の結論に頼らず、変更境界・受入条件・設計と依頼書からの違い・欠陥注入（実装者の30件の再現と独立の25件）・成否不明と例外の出口・同時実行・範囲試験と次段階の模擬・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常0・提案4。推奨は「受領」。** 依頼書第2版§3の11項目と受入S4A-01〜S4A-17は、試験対象c15ab18で満たされている。第2版で直したN-01（開始位置をprocessing_afterに）とN-02（同時実行の受入）も、実装と試験の両方に入っている。提案はどれも受領の条件にしない。いちばん重いのはP-01で、STALE・STOPPEDの朝に消費した欠測が、どの朝の文面にも出なくなる。S4-Bで通知の文面を作るときに扱うことを勧める。
本レビューはPR・マージ・本番反映・S4-Bへの移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らしても、S4-Aは注入された時刻・保存先・入力で1回動くだけで、時計・ネット・通知・再試行・解錠を持たないことを確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb（C-4の保存最終、再レビュー8d02abfで受領） |
| 試験対象 | **c15ab18ae7a02dc9bef900412ae3af7862c232d1**（コード・試験の最終） |
| 保存最終 | **6ad609fe52b50565103e56c598505cac85601216**（feat/v2-daily-run-s4a-20261104。c15ab18からは結果文書1本の追加だけ） |
| 基準 | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6（docs/v2-s4-daily-run-20261104）の設計（blob 244df2b）・依頼書第2版（blob 8b983d3）・試行差分（blob b0c20c6、sha256 13df420c…）。D-1〜D-7採用済み。設計レビューdd60f6f（N-01・N-02、提案P-01〜P-07） |

読んだもの：依頼書第2版の全文、設計§5（S4-Aの設計）の全文、結果文書の全文、ランタイム3ファイルの全文（289行）、比較のためv2_persistence/runner.pyのprepare_day、v2_history_ops/daily.pyのprepare_history_day、v2_core/display.pyのrender_messageとbstar、v2_core/sessions.py、v2_core/fixture.pyのMarketSeries。新規試験のうちs4a_helpers・test_s4a_04（成否不明）・test_s4a_05（総当たり）・test_s4a_06（子プロセス）の全文と、test_s4a_02・03・08・09の該当部分。共有フォルダの実装者のmutate.py・next_stage_sim.sh・runall.sh・mutation_out.json。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、S4A-16） | **合格** | 2e6ba5f→c15ab18はA 14本・M 1本。Mはtest_c4_09_scope.pyの18行目`END`の1行だけで、試行差分の同じ行（blob bea589a→be25c0b）と一致。Aはv2_daily_run/の3ファイル（4以下）とtests/v2_daily_run/の11本（`__init__.py`なし）。c15ab18→6ad609fはA 結果文書1本だけ |
| 依存とimport（S4A-15） | **合格** | ランタイムのimportは`datetime`・v2_core（display・errors・sessions）・v2_history_ops・v2_history_publishだけ。v2_history_local・v2_history_maintainなし。datetimeは`now`の型の確認だけに使う |
| 依頼書§3の1〜11 | **合格** | 入口・引数の検査の順・対象D・開始位置（processing_after）・未確定でSTALE・PREPAREDだけ保存・対象Dの評価・成否不明の1回のやり直し・捕まえ口の外での報告・報告の項目・文面の規則を、コードと試験の両方で確かめた |
| 受入S4A-01〜S4A-17 | **合格** | 4版×16スイートで2,349件合格（§4.1）。S4A-17(b)の試験はDECLARE_MISSINGだけでACKを足していない（P-03） |
| 第2版のN-01・N-02 | **反映済み** | 開始位置は`read_effective(history).processing_after`（run.py 70行）。S4A-17で再初期化の後の最初のAPPLYを確認し、注入4（latest_apply_d）を検出。同時実行の受入は「途中までの前の部分、DONEがあれば1回と同じ、その後1回で同じ」で、本レビューの80回でも成り立った（§4.4） |
| 下書きとの違い（結果§4） | **妥当** | `rec.status`→`rec.outcome`（C-2の`Reconciliation`は`outcome`だけを持つ）、開始位置から高々1回のやり直し、同じ公開値を2回送らない保険は、どれも依頼書§3の8の範囲内で、下書きの誤りを直したもの |
| 欠陥注入 | **実装者30件を再現（30件検出）、独立25件は検出23・等価2・穴0** | §4.2 |
| 例外の出口（S4A-14） | **合格。ただし文面の作成は捕まえ口の外** | 実装者の総当たり（CoreError 6種×14呼出点、他の例外19通り）を再実行して合格。`render_message`は`try`の外（run.py 174行、194行）で、ここから出たCoreErrorは漏れる（P-02、現実の入力では起きない） |
| 次段階の模擬（S4A-16） | **保存最終で再現** | 6ad609fで[A]全件合格、[B]（ENDだけ固定）で範囲の鎖2件だけ失敗、[C]（仮の開いた範囲を追加）で全件合格（§4.5） |
| 保護参照 | **一致** | 依頼書§7の88参照＋7542a18＋dd60f6f＋実装ブランチ（6ad609f）の91件を`git ls-remote`の完全SHAで照合（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| P-01 | 提案 | STALE・STOPPEDの文面（run.py `_notice`、158〜167行）は、保存した日の一覧は書くが、そのうちgapのある日の欠測の行（`_gap_lines`）を書かない。依頼書§3の11と設計§5.5の文言どおりの実装だが、欠測は消費した日の遷移にしか残らないので、次の朝の開始位置はその日より後になり、どの朝の文面にも出なくなる。`s4ai_probe.py`のX1で再現：D2にdecisionが無く、D4が未確定の朝はD1・D3を保存してSTALE（D3はgap、skipped＝D2）。文面にD2は無い。D4が確定した次の朝はD5を消費してDONEだが、文面に出る欠測はD4だけで、D2はどの文面にも出ない | 設計§5.5が欠測の行を足した理由（T-1：朝の文面だけを読む人は、前のセッションの記録が欠けたことに気づけない）が、STALE・STOPPEDの朝には働かない。`RunReport.consumed`にはgapとskipped_sessionsが残るので、情報そのものは失われていない。データの誤り・判定の誤りは無い | S4-Bで通知の文面を作るとき、DONE以外でも欠測の行を書く（`_notice`の「この実行で保存した日」の後に`_gap_lines(consumed)`を置くだけで、判定・分岐表・b\*は含まない）。S4-Aで直すなら、文面の規則の1行の変更と試験1件。設計レビューdd60f6fのP-01（gapでなくskipped_sessionsを条件にする）と同じ機会に決めるのがよい | X1の2つの文面の少なくとも一方にD2が出ること |
| P-02 | 提案 | DONEの文面の`render_message`（run.py 174行）は`_report`の中で呼ばれ、`_report`は`try`の外（194行）にある。依頼書§3の9・設計§5.6は「保存先を読んだ後のCoreErrorは、すべてSTOPPED」としている。(a) `render_message`の中の`bstar`はInputError（`soxl_price_definition_unknown`・`price_not_finite_positive`）を投げ得るが、`MarketSeries`の構築時の検査で同じ条件を拒むので、正しく作った系列では起きない。X2で`render_message`にInputErrorを起こすと、その日を保存した後にInputErrorが漏れ、次の朝も同じになる。(b) 既存のコアで、`MarketSeries`が受け付けるSOXL終値1e27以上で`bstar`の`quantize`が`decimal.InvalidOperation`（CoreErrorでない）を投げる（X2b）。日は保存された後で、毎朝同じ例外になる。依頼書どおり「プログラムの誤りはそのまま出す」に当たる | 現実の入力では起きない（(a)は型の契約の外、(b)はSOXL終値として起こり得ない値）。起きた場合は、保存は正しく、文面と報告だけが出ない | (a) コードの変更は任意：`try`の中で文面を作り、`_report`には文字列を渡す（報告は外で作る規則はそのまま）。(b) S4-Aの範囲外。S4-Dの入力アダプタで価格の上限を検査するか、コアの`bstar`の文脈の精度を検討する。S4-Bの「例外でも判定なしの通知を必ず1通」（設計レビューP-02）が入れば、利用者に沈黙は残らない | X2が`STOPPED`の報告を返すこと（(a)を直した場合） |
| P-03 | 提案 | 試験の小さな穴：(a) S4A-17(b)は「ACK・欠測宣言を足しても開始位置が動かない」だが、`test_an_acknowledgement_and_a_declaration_after_the_restart_do_not_move_the_start`はDECLARE_MISSINGだけを足し、ACKは足していない（試験名とずれる）。(b) 独立の変異で等価が2件（V17：対象Dの結果をPREPAREDのときだけ残す→NO_COMMITの対象Dを同じ履歴でもう一度評価するので同じ結果、V30：やり直しの時に対象Dの結果を消さない→やり直しは対象Dの結果を記録する前にしか起きない）。どちらも観測できる違いが無く、穴ではない | 実装は正しい（開始位置は既存の`read_effective`が決め、ACKの扱いはC-1〜C-4の試験で確かめ済み）。将来`processing_after`の扱いを変えたとき、ACKの場合を試験が拾わない | 次にtest_s4a_03を触る機会に、再初期化の後にACKを足す1件を加える。今回の受領の条件にしない | ACKを足した履歴で開始位置がresume_afterのままであること |
| P-04 | 提案 | 記録と文面の小さなずれ：(a) 成否不明の後に読み直して続けた実行は、対象Dが成否不明の日だと`target_status`が`ALREADY_APPLIED`になる（X3。文面・バイト・digest・消費した日は通常と同じ）。結果§14にも書かれている。S4-Bで`target_status`を「新しい判定かどうか」に使うと誤るので、通知の意図の鍵には使わない旨を設計に書く。(b) 2回目の成否不明（`run_publish_uncertain`）と`run_publish_conflict`の文面は「市場状態は、保存した日までです」と書くが、その日が実際に書かれたかは分からない（前者）。読んだ人が、保存の有無を確定したものと受け取るおそれ。(c) 実装者の欠陥注入の再現で、追加7の落ちた試験の数が結果§8の22件に対し24件だった（検出の結論は同じ）。子プロセスの競合の試験の結果に依存する数と思われる（未確認） | 動作への影響なし | (a) S4-Bの設計に1行。(b) S4-Bの文面で「この日の保存は確認できていません」を足す。(c) 受領記録に注記 | 記録の確認だけ |

重大・通常は無い。

## 4. 確認の詳細

### 4.1 全スイートの再実行（S4A-01）

試験対象c15ab18を、完全な履歴の別クリーンクローン（`git clone`、浅くない、core.autocrlf未設定＝false）から版ごとの`git worktree`に取り出し、実装者のrunall.sh（`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`）で16スイートを実行した（`s4ai_allver_c15ab18.log`）。

| 版 | 結果 |
|---|---|
| 3.10.20（uv） | 16スイートとも rc＝0。既存15スイート2,253件（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139、C-4 184）＋新規96件。skipはS2のWindows専用4件だけ |
| 3.11.18 | 同上 |
| 3.12.3 | 同上 |
| 3.13.18 | 同上 |

合計2,349件。新規のskipは0。新規96件の内訳（9＋20＋14＋12＋4＋3＋8＋7＋19）は結果§5と一致した。

### 4.2 欠陥注入

- **実装者の30件の再現**：共有フォルダのmutate.pyを、c15ab18を含む別クローンで3.12により2分割で再実行した（`s4ai_implementer_mutants_repro.json`）。30件すべてDETECTEDで、落ちた試験の数は29件で結果§8と一致した（例：依頼5は22件、6は50件、12は85件、15は37件、追加10は51件）。追加7だけ22件に対し24件（P-04(c)）。
- **独立の変異25件**（`s4ai_mutants.py`、c15ab18の作業ツリーの写しでrun.py・values.pyを1件ずつ変え、tests/v2_daily_runの96件を3.13で実行。出力`s4ai_mutants_out.json`）：

| ID | 内容 | 結果 |
|---|---|---|
| V01 | 消費した日のgapを「skipped_sessionsが空でない」にする（P-01の方向） | 検出1（今の動作を固定する試験） |
| V02 | 対象Dの後で`break`しない | 検出29 |
| V03 | 対象Dが開始位置より前の確認を外す（コアの誤りに任せる） | 検出1 |
| V04 | やり直しのたびに送った公開値の記録を消す | 検出1（嘘をつく保存先） |
| V05 | reconcileを例外処理の中でも呼ぶ（2回、文脈つき） | 検出8 |
| V07 | STALEのdetailを空にする | 検出3 |
| V08 | 文面から「条件未達ではありません」を外す | 検出2 |
| V10 | sessionsの型を確かめない | 検出2 |
| V11 | storeの3つを`callable`でなく`hasattr`で確かめる | 検出1 |
| V12 | 対象Dを`open_at <= now`で決める | 検出3 |
| V15 | PUBLISHED_THEN_EXTENDEDを成功として扱わない | 検出1 |
| V17 | 対象Dの結果をPREPAREDのときだけ残す | **等価**（P-03(b)） |
| V19 | 欠測の行を核の文面の後に置く | 検出1 |
| V20 | 識別子の長さの上限を16にする | 検出27 |
| V22 | STALEの終了コードを0にする | 検出3 |
| V23 | 各回の初めに`run.history`を設定しない | 検出9 |
| V25 | 送った公開値を記録しない | 検出1 |
| V27 | 文面から「この実行で保存した日」を外す | 検出3 |
| V28 | 欠測の見出しを常に出す | 検出5 |
| V29 | 未確定をSTALEでなくSTOPPEDにする | 検出4 |
| V30 | やり直しの時に対象Dの結果を消さない | **等価**（P-03(b)） |
| V31 | 未確定の対象Dをコアに任せる（target_unconfirmedでSTOPPED） | 検出1 |
| V32 | やり直しの印を`None`（＝終わり）と同じにする | 検出（試験が終わらない。`_drive`が無限に読み直すので900秒で打ち切り） |
| V33 | 照合で書かれた日を消費した日に数えない | 検出6 |
| V34 | 文面から「対象のセッション」の行を外す | 検出1 |

### 4.3 例外の出口と成否不明（S4A-12・S4A-14）

- コードの経路：保存先を読んだ後の呼出し（`store.read`・`read_effective`・`prepare_history_day`・`publish_day`・`store.publish`・`store.reconcile`）はすべて`run_morning`の`try`の内側にある。`store.publish`の例外処理は`store_commit_uncertain`以外を素の`raise`で投げ直すだけで、`reconcile`は例外処理の外（`uncertain`の旗の後）で呼ぶ。外側の例外処理は値（code・field・rule・detail）を作るだけで、`RunReport`は`_report`で作る。`_ident`・`_date`で、codeなどは小文字・数字・`_`の64文字以内、detailは日付の形のときだけ写す。既存のコード・field・ruleの値（`rule="v1_and_v2"`等）はすべてこの形に入ることを、ソースのgrepで確かめた。
- 実装者の総当たり（test_s4a_05）を4版で再実行して合格。他の例外が`reconcile`で起きた場合も`__context__`が空であることを、この試験が確かめている（V05で検出）。
- 例外の出口の唯一の外れは文面の作成（P-02）。
- 成否不明の後のやり直しは高々1回（`run.restarts`）。2回目の成否不明はreconcileを呼ばずに`run_publish_uncertain`。やり直しは開始位置から行うので、PUBLISHED_THEN_EXTENDEDで他の書き手が足した日を自分の消費に数えない（test_s4a_04で確認）。

### 4.4 同時実行（S4A-13(b)、第2版N-02）

設計レビューの`s4r_race.py`を、論理を変えずにc15ab18の`run_morning`に当てた（`s4ai_race.py`、3.13、6日分、実物のC-3）。

| 子プロセス | 回数 | 1回の結果と同じ | 前の部分だけ | 二重のAPPLY | 報告の組 |
|---|---|---|---|---|---|
| 2 | 60 | 60 | 0 | 0 | すべて（DONE, store_busy） |
| 4 | 20 | 20 | 0 | 0 | DONE＋store_busy 3が15、DONE＋publication_stale＋store_busy 2が4、DONE＋publication_stale 2＋store_busyが1 |

今回の80回では全員STOPPEDの並びは出なかったが、受入は第2版のとおりそれを許している（設計レビューでは80回中3回）。

### 4.5 次段階の模擬（S4A-16）

実装者のnext_stage_sim.shを、保存最終6ad609fに対して3.13で実行した（`s4ai_next_stage_sim_6ad609f.txt`）。次の段階はENDを保存最終に固定するので、試験対象でなく6ad609fで行った。

    [A] tested commit 6ad609fe52b50565103e56c598505cac85601216
      v2_scope_chain: Ran 34 tests | OK
      v2_history_maintain: Ran 31 tests | OK
      v2_daily_run: Ran 96 tests | OK
    [B] END frozen, no open range (expected: test_sc_02 chain test fails)
      v2_scope_chain: Ran 34 tests | FAILED (failures=2)
      v2_history_maintain: Ran 31 tests | OK
      v2_daily_run: Ran 96 tests | OK
    [C] END frozen + minimal open range of the next stage
      v2_scope_chain: Ran 34 tests | OK
      v2_history_maintain: Ran 31 tests | OK
      v2_daily_run: Ran 96 tests | OK

次の段階は、test_s4a_09_scope.pyの`END`を`6ad609fe52b50565103e56c598505cac85601216`に固定し、同じコミットで開いた範囲を足す。

### 4.6 調べて問題が無かったこと

- 対象Dの決定：`SessionList`は日付の昇順と、前のclose_atが次のopen_atより前であることを構築時に検査するので、`close_at <= now`の最後の1つで対象Dが一意に決まる。
- `ConsumedDay.skipped_sessions`は`res.batch.body["records"][0]`から取るが、`prepare_history_day`のPREPAREDのbatchはAPPLY 1件だけ（daily.py 113〜117行）なので、常にその日のAPPLYである。
- 開始位置の直後の最初の日にsessionsの欠測があってもgapはFalse（結果§14、設計レビューP-01）。依頼書§3の11の「gapのある日」のとおりで、V01で今の動作が試験で固定されていることを確かめた。
- 追いつきは毎日`prepare_history_day`と`publish_day`の両方を呼び、同じ日の計算を2回行う。所要時間（結果§13の37日8.1秒）は参考値で、正しさには影響しない。

## 5. 推奨

**受領**（コードの修正なし）。

- S4-Aの範囲（オフラインの1回の実行）として、依頼書の規則と受入を満たし、試験は独立の変異にも十分に感度がある（穴0）。
- P-01とP-02(b)の利用者への影響（STALE・STOPPEDの朝の欠測の行、例外の朝の沈黙）は、どちらもS4-B（通知の文面と「毎朝必ず1通」）で扱うのが自然で、S4-Aの受領を止める理由にならない。S4-Aで先に直したい場合は、P-01の1行とP-02(a)の文面の作成の移動を、試験数件とともに限定修正にできる（Sonnet high、差分だけの再レビュー）。
- 受領する場合、次の段階はtest_s4a_09のENDを6ad609fに固定する。未実施（実Windows、物理電源断、ユーザーPC）は結果§14のとおり残る。

## 6. 保護参照

依頼書§7の88参照＋資料ブランチdocs/v2-s4-daily-run-20261104（7542a1829a8c16e0842d53a846dc23b83f6d2ee6）＋設計レビューdocs/v2-s4-daily-run-review-20261104（dd60f6f22d773561cfcc3ab09c868e02d9d0a973）＋実装ブランチfeat/v2-daily-run-s4a-20261104（6ad609fe52b50565103e56c598505cac85601216）の91件を、`git ls-remote`の完全SHAで照合した。

| 時点 | 結果 |
|---|---|
| 開始時（2026-11-04 15:40Z頃） | 91件一致 |
| 記録の1回目のpush後 | 91件一致（`s4ai_refs_postpush.txt`。記録ブランチの先端は報告に書く） |

本レビューの記録は、6ad609fから作った新しいブランチdocs/v2-daily-run-s4a-impl-review-20261104にだけ置いた。実装ブランチ・資料ブランチ・mainは変えていない。

## 7. 確認に使ったもの

`docs/reviews/v2_daily_run_s4a_impl_review_20261104/`（共有フォルダ reviews/ にも写し）：

| ファイル | 内容 |
|---|---|
| s4ai_allver_c15ab18.log | 4版×16スイートの結果（§4.1） |
| s4ai_implementer_mutants_repro.json | 実装者のmutate.pyの再現（§4.2） |
| s4ai_mutants.py・s4ai_mutants_out.json | 独立の変異25件（§4.2） |
| s4ai_probe.py・s4ai_probe_out_py3.13.txt | X1（P-01）、X2・X2b（P-02）、X3（P-04(a)） |
| s4ai_race.py・s4ai_race_n2_out.txt・s4ai_race_n4_out.txt | 同時実行（§4.4） |
| s4ai_next_stage_sim_6ad609f.txt | 次段階の模擬（§4.5） |
| s4ai_refs_start.txt | 保護91参照の照合（開始時） |

再実行の例（リポジトリの根で、試験対象を取り出して）：

    PYTHONDONTWRITEBYTECODE=1 python3.13 -B docs/reviews/v2_daily_run_s4a_impl_review_20261104/s4ai_probe.py .
