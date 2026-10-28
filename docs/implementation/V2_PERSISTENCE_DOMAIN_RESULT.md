# V2 保存ドメイン・単日ランナー（S1）限定実装 結果

2026-10-28（日本時間）。依頼書 `docs/tasks/V2_PERSISTENCE_DOMAIN_OFFLINE_REQUEST.md` 第4版と設計書 `docs/specs/V2_PERSISTENCE_DOMAIN_OFFLINE_DESIGN_DRAFT.md` 第4版（資料ブランチ `docs/v2-persistence-domain-20261028` の `425df80d04b116e25e481184069b89bed1380c3a`）を、Rockyさんの採用文（2026-10-28 04:09 UTC、プロジェクトスレッド。S1の限定実装を承認、Sonnet 5.5・エフォートhigh、範囲は依頼書どおり）の範囲で実装した。PRは作っていない。

> **第2版（2026-10-28）**：受領レビュー（`docs/v2-persistence-domain-s1-receipt-20261028` の `da24fcd4fcd70a51753ff61b3f9aa1436ec431c2`、重大0・通常3・提案1）を受け、R-01〜R-03を別ブランチ `fix/v2-persistence-domain-s1-review-20261028`（`b9586d65aa411bfe32ca6fe795ad4b15e972d59c` 基準）で修正した。**§15が第2版の結果**で、§1〜§14は第1版（b9586d6）の記録。第1版の件数・SHAのうち、第2版で変わるものは§15に示す（試験は154→170件）。欠陥注入「58通り」は**57通りの誤り**で、§12を訂正した。

## 1. 結論（第1版）

- 新規パッケージ `v2_persistence/`（標準ライブラリと変更なしの `v2_core` だけに依存）、新規試験 `tests/v2_persistence/`、この結果文書だけを追加した。**b616b4e との差分は追加（A）のみで、変更・削除は0件**。
- 受入条件 A-01〜A-08 を実施し、全て合格。**既存181件**（既存ファイル無変更）と**新規154件**は、Python 3.10.20・3.11.17・3.12.3・3.13.17の全てで、失敗0・skip0・終了コード0（クリーンクローン、`core.autocrlf=false`、OSレベルで通信を遮断した状態）。
- これはクラウド環境（Linux）での別環境の試験である。**ユーザーPCでの b616b4e 全181件の確認は後日実施のまま**で、この結果で「ユーザー実機確認済み」にはしない。
- 実ファイル保存、復旧操作、通知接続、依存・workflow変更、本番操作は行っていない。範囲外の変更が必要になる場面は無く、停止して報告する項目は無かった。

## 2. 開始・試験対象・保存後の記録

| 項目 | 値 |
|---|---|
| 資料（採用版） | `docs/v2-persistence-domain-20261028` = `425df80d04b116e25e481184069b89bed1380c3a`。設計書 blob `de8235bb11b07b31e4391eeb6f462751add9ce19`、依頼書 blob `8e45dbebb0ca106a288bfbdef8cb1c919d9194bc`。開始・終了で先頭は不変 |
| 実装基準（開始SHA） | `b616b4ec7169420e199ec7e247dd375b3603a013`（`feat/v2-core-state-checks-20261028`） |
| 作業ブランチ | `feat/v2-persistence-domain-offline-20261028`（b616b4eから。既存名の上書きなし） |
| コード・試験のコミット | `a28d8ce2d439fbc80bbbc4f17be7d725e6e3c4db`（実装と試験）、`5083b376b6a082afe94380d88dba43ef999d86e1`（A-05の対比試験2件を追加） |
| **試験対象SHA（完全）** | `5083b376b6a082afe94380d88dba43ef999d86e1` |
| 保存最終SHA（完全） | 報告に記載（この文書自身のSHAは文書内に書けない）。試験対象SHAとの差分は `docs/implementation/V2_PERSISTENCE_DOMAIN_RESULT.md` の追加だけであることを `git diff --name-status` で確認する（§11） |
| 担当モデル | セッション情報（`get_session`）で確認：`configured_model` と `session_context.model` が `claude-sonnet-5-5[1m]`、`last_served_model` が `claude-sonnet-5-5`。エフォートは `high` |
| OS | Ubuntu 24.04.5 LTS、Linux 6.18.44-fc-v180 x86_64（Claude Codeクラウド環境） |
| Python | 3.10.20（uvの単体インタプリタ、スクラッチ領域）、3.11.17、3.12.3、3.13.17（システム） |
| git | `core.autocrlf=false`（作業用クローン、試験用クリーンクローンとも） |
| 環境取得と試験実行の区別 | 3.10.20の取得（`UV_PYTHON_INSTALL_DIR=<スクラッチ>/uvpy uv python install 3.10`）だけが通信を使った。試験の実行は通信なし（下記）。リポジトリの依存・lockfile・設定は変更していない |

保護5参照と上位資料ブランチの前後は §11。

## 3. 実行コマンドと結果

試験は全てクリーンクローン（`git clone -c core.autocrlf=false --depth 5 --branch feat/v2-persistence-domain-offline-20261028`、`git status` 差分0）で、`unshare -rn`（新しいネットワーク名前空間、外部へ出られない）の中で実行した。加えて、新旧とも試験の道具がプロセス内でソケット生成を無効化する（既存は `v2_helpers.py`、新規は `p_helpers.py`。後者は A-08 の試験で無効化を確認）。

    <python> -B -m unittest discover -s tests/v2_core                              # 既存（181件）
    <python> -B -m unittest discover -s tests/v2_persistence -p "test_*.py"        # 新規（154件）

| Python | 既存 | 新規 | skip | 終了コード |
|---|---|---|---|---|
| 3.10.20 | 181 合格 | 154 合格 | 0 | 0 / 0 |
| 3.11.17 | 181 合格 | 154 合格 | 0 | 0 / 0 |
| 3.12.3 | 181 合格 | 154 合格 | 0 | 0 / 0 |
| 3.13.17 | 181 合格 | 154 合格 | 0 | 0 / 0 |

新規154件の内訳（ファイル別）：A-02 = 37、A-03 = 23、A-04 = 14、A-05 = 33、A-06 = 14、A-07 = 19、A-08 = 14。件数は実測で、受入項目の数ではない。A-06の競合試験（Barrierで同時に開始する2スレッド）は、3.10.20と3.13.17で各40回繰り返して失敗0だった（コード a28d8ce で実施。試験は以後、A-05の2件追加のみ）。

## 4. 受入条件と試験の対応

| ID | 結果 | 主な試験（ファイル：クラス／関数） |
|---|---|---|
| A-01 既存回帰 | 合格 | 既存181件を4版で実行。b616b4eとの差分は追加16ファイルのみ、既存ファイル・基準JSONの差分0（`git diff --name-status b616b4e HEAD` が全てA） |
| A-02 初期化・構造 | 合格 | test_a02：未初期化の読取・commit、二重初期化、正常GENESIS、不正日付9種、境界不存在／未確認、D＝境界当日と境界以前の拒否、APPLY入りの初期化とGENESIS重複の拒否、不明版・コアSHA・イベント種類・項目、seq／親seq／親hash／event_hash／D重複・逆転／先頭状態、ヘッダー不一致、正準形（intやオフセット表記）、数値範囲、重複キー・NaN・Infinity・深い入れ子 |
| A-03 再計算 | 合格 | test_a03：5件のAPPLY（欠測1回・armed到達・トレンド日）のJSON往復と、テスト側で`v2_core.transition`を直接呼ぶ独立再計算との全件一致、研究fixture（2025-01〜04、約80日）の通し再計算と`evaluate_day`連鎖の一致、正常な基点（as_of_dあり）の受理、IB-04（基点と親状態の不一致）、固定decision指紋の不一致、ハッシュが整った保存済み中間S未確定（rule=skipped_session_unconfirmed）、入力のみ／判定のみ／状態のみを書き換えた履歴の不一致、`apply_transition`のspyと返値差替え（§5） |
| A-04 単日・再実行 | 合格 | test_a04：新規Dは準備だけで未保存、commit後1件、decision無しは追記0、正常commit直後の同じ最新Dの再実行がALREADY_APPLIED・計画なし・追記0、UTC別表記・同内容重複・補助観測・将来行・行の順序、next(D)のconfirmedのみ／close_atのみ／両方、open_atとdateの変更（session_context_mismatch／session_context_missing）、数値変更（判定が変わらなくても停止）、前日行の変更、input→transition→stateの不一致順 |
| A-05 時系列・台帳 | 合格 | test_a05：境界以前・過去Dの拒否、新規Dの中間S未確定（初回・通常とも、decision無しやNO_COMMITになる場合も）、確定後の再準備・commit・再実行（Q-01）、next(D)未確定は許容、中間Sの有効decision（intermediate_session_unprocessed）と窓外（close直前・次のopenちょうど）、誤対象・複数decision・同ID内容違い、有効decisionの後に不正行がある例、行順入替、通常欠測後F&G30以上のstreak=1、初回遅延のgap=falseとskipped_sessions、台帳事象8種×（最新Dの再実行／新しいD）、保存セッションの欠落・相違・古い適用済みDの時刻改訂（P-02）、コア単体との対比 |
| A-06 同時更新・照合 | 合格 | test_a06：同じ先頭・同内容の2計画（成功1・cas_conflict 1、読直し照合でALREADY_APPLIED）を25回、異なる入力の同D（concurrent_conflict）、異なるDの計画（成功1、REPLAN_REQUIRED、古い計画は付け替えず再commitもcas_conflict）、commit後に先頭が進んだ後の照合、相手だけが先頭を進めた例、親hashだけが違う計画 |
| A-07 障害・独立性 | 合格 | test_a07：commit直前の検査例外、検査不合格の候補、commit成功後に応答を失った想定（reconcileで追加0）、全ての拒否後の先頭不変、Snapshot／計画／戻り値／入力（実行中の変更を含む）の独立性、台帳の不正数値・時刻・窓、非有限・範囲外の市場値、生の値を出さない例外、600通りのランダム編集（固定シード）で他の例外が出ないこと |
| A-08 境界・環境 | 合格 | test_a08：静的検査（import、時計・ファイル・URL・資格情報・通知の語、閾値の複製なし）、`open`と時計を無効にした通し実行、設計§9の表の全行（code／field）、優先順位、`evaluate_day`への委譲とコアのエラーの非変換、プロセス内ソケット無効化の確認 |

N-01／N-02／Q-01／P-02の受入例への対応：
- **N-01**：test_a05 `DecisionsInTheMiddle`（初回と適用済みの両方で、close直前・次のopenちょうどの窓外行が decision_outside_window・計画なし・状態／seq／先頭不変）、`CoreVersusWrapper`（コア単体では通ってしまう窓外の中間decisionを拒否）。正常な欠測区間を挟んだcommitから同一入力の再実行までは test_a04 `test_gap_then_commit_then_same_input_rerun`／`test_first_run_after_a_long_gap...`。
- **N-02**：test_a04 `SameInputIdentity.test_next_session_confirmed_and_close_at_updates_do_not_matter`（3種の有効入力で保存済み写し・Snapshotは不変）、`test_next_session_open_at_or_date_change_stops`。
- **Q-01**：test_a05 `IntermediateSessions`（未確定→停止・不変、確定→再準備・commit・直後の再実行がALREADY_APPLIED、next(D)は未確定のまま可）。
- **P-02**：test_a05 `StoredSessionRanges`（古い適用済みDの保存範囲の時刻改訂、next(D)の2項目除外は各APPLY自身のDが基準で後続APPLYでは当日として比較されること）。

## 5. `apply_transition`のspyと返値差替え（A-03、P-06）

通常計算は`v2_core.engine.apply_transition`、新パッケージの再計算は`v2_persistence.recompute.apply_transition`（`from v2_core.transition import apply_transition`で束縛した名前）を、経路ごとに別ケースで確認した。元の`v2_core.transition.apply_transition`だけを差し替えて効いたとは見なしていない。

| 差替え先 | 到達した経路 | 観測／検出結果 |
|---|---|---|
| spy：engine、recompute、origin（`v2_core.transition`）を同時に | `prepare_day`（新規D、保存2件） | engine=D3の1回、recompute=D1,D2（保存済みの検査）＋D1,D2,D3（候補の自己検査）の5回、origin=0回 |
| origin側を例外を出す関数にする | `prepare_day`と`validate_snapshot` | どちらも影響を受けず成功（originは使われていない） |
| spy：recompute | `MemoryStore.commit` | D1,D2,D3の3回（commitも同じ全検査） |
| 返値差替え：engine（4種：連続数、gap、notes、run_class。さらに次状態候補の連続数） | `prepare_day` | `transition_mismatch`または状態規則違反で停止、PREPAREDなし。ストア不変 |
| 返値差替え：recompute（連続数） | 保存済みSnapshotの`validate_snapshot`と`prepare_day`の最初の検査 | `snapshot_invalid`（rule=`transition_mismatch`） |
| 返値差替え：recompute（新しいDの呼出しだけ） | `prepare_day`の候補自己検査 | 保存済み履歴は合格、候補だけ不一致→`snapshot_invalid`、PREPAREDを出さない |
| 返値差替え：engine（再実行時の連続数／gap／次状態） | 同日再実行 | `recompute_mismatch`（field=`transition_result`／`transition_result`／`state`） |

通常計算と再計算を同時に同じ誤った返値へ変えて一致させる試験は作っていない。

## 6. 正常時・主要停止時の不変性

正常時：`prepare_day`はMemoryStoreを変更しない（PREPARED／NO_COMMIT／ALREADY_APPLIEDのどれでも、前後のSnapshotが等しい）。`commit`成功時だけ`head_seq`が1増え、`COMMITTED`を返す。同日の再実行は追記0。停止時：`LedgerAgainstStoredDays`、`IntermediateSessions`、`StoredSessionRanges`、`FailureInjection.test_every_refused_operation_keeps_the_stored_snapshot`などで、拒否した全操作の後に Snapshot 全体・`head_seq`・`head_hash` が操作前と一致することを確認した。

## 7. 公開API、型、スキーマ、保存項目

### 7.1 パッケージと公開名

| モジュール | 公開名 |
|---|---|
| `v2_persistence.codec` | `Snapshot`（不変値。`from_dict`、`to_dict`、`events`、`current_state`、`head_seq`、`head_hash`、`core_sha`、`schema_version`）、`encode_snapshot`、`decode_snapshot`、`canonical_json`、`compute_event_hash`、`utc_text`、`SCHEMA_VERSION=1`、`CORE_SHA`（b616b4eの完全SHA） |
| `v2_persistence.events` | イベントの組立て（`make_genesis_event`、`make_apply_event`、`append_event`、`snapshot_of`）、`serialize_transition`、`input_hash_of`、`project_context` |
| `v2_persistence.recompute` | `validate_snapshot(snapshot)`（失敗は例外。成功時は`ValidatedSnapshot`を返す）、`ValidatedSnapshot`、`AppliedDay` |
| `v2_persistence.runner` | `make_genesis(start_after, sessions)`、`prepare_day(snapshot, d, series, sessions, raw_observations)` |
| `v2_persistence.plan` | `AppendPlan`（不変。期待先頭seq／hash、APPLY1件）、`PrepareResult`、`CommitResult`、`ReconcileResult`、状態名 `PREPARED`／`NO_COMMIT`／`ALREADY_APPLIED`／`COMMITTED`／`REPLAN_REQUIRED` |
| `v2_persistence.store` | `MemoryStore`（`read`、`initialize`、`commit`）、`reconcile(plan, snapshot)` |
| `v2_persistence.errors` | `PersistenceError`（`CoreError`の子。`code`、`field`、`detail`、`rule`）、`snapshot_invalid(rule)` |

GENESIS／APPLYは専用クラスにせず、Snapshotの値として正準JSONの辞書で表し、組立て関数と`validate_snapshot`が同じ正準形の関数を共有する（保存された形がそのまま値で、保存後に型と内容が食い違わないため）。

### 7.2 スキーマ（版1）と全保存項目

Snapshot：`schema_version`(1)、`core_sha`、`head_seq`、`head_hash`、`current_state`、`events`。

- GENESIS（`seq`=0）：`kind`、`seq`、`parent_seq`(null)、`parent_hash`(null)、`start_after`、`boundary_session`（`date`、`open_at`、`close_at`、`confirmed`）、`state_after`（`MarketState()`の初期状態のみ）、`event_hash`。
- APPLY：`kind`、`seq`、`parent_seq`、`parent_hash`、`d`、`confirmed_inputs`、`input_hash`、`skipped_sessions`、`transition_result`、`state_after`、`event_hash`。
- `confirmed_inputs`：`decision`（6項目：`record_id`、`observation_status`、`observation_role`、`current_fg_value`(float)、`observed_at_iso8601`(UTC)、`target_us_session_date`）、`row`（`date`、`soxx`、`sma`、`rsi`、`shd`、`prev_rsi`）、`prev_row`（同6項目またはnull）、`prev_session_date`、`session_context`（基準境界からnext(D)までの連続した注入セッション4項目）。
- `transition_result`：`rules`（`EXFEAR`／`NORMAL`／`TREND`それぞれ`name`、`status`、`ratio`、`reasons`、`may_be_unconfirmed`）、`run_class`、`gap`、`effective_armed`、`effective_streak`、`effective_prev_normal_raw`、`notes`。`state_updated`と表示項目は含めない。
- 時刻は`YYYY-MM-DDTHH:MM:SS[.ffffff]Z`（UTC）、数値は有限float。JSONはキー順固定・区切り固定・`ensure_ascii`・`allow_nan=False`・UTF-8。`input_hash`は`confirmed_inputs`から**next(D)の`close_at`と`confirmed`だけ**を除いた投影のSHA-256、`event_hash`は`event_hash`自身を除くイベント全体（保存した完全な`session_context`を含む）のSHA-256。保存順を問わず、読込時に「正準形で組み直した値と一致するか」も検査する（intとfloatの違い、UTC以外の表記、未知項目を拒否）。

### 7.3 `snapshot_invalid`の規則識別子（実装）

`type`、`json`、`json_type`／`json_key`／`json_number`／`json_depth`、`header_keys`、`events`、`first_not_genesis`、`genesis_not_first`、`genesis_keys`、`genesis_seq`、`genesis_boundary`、`genesis_state`、`apply_keys`、`seq`、`parent_seq`、`parent_hash`、`event_hash`、`apply_d`、`d_order`、`confirmed_inputs_keys`、`session_context`、`context_boundary`、`context_continuity`、`prev_session_date`、`skipped_session_unconfirmed`、`skipped_sessions`、`row`、`prev_row`、`decision`、`decision_window`、`not_canonical`、`input_hash`、`state_after:<I-xx／IB-xx>`、`IB-04`、`transition_mismatch`、`state_mismatch`、`head_seq`、`head_hash`、`current_state`、`plan_type`、`initialize_not_genesis_only`、`event_build`。

## 8. コアへ委譲される根拠

- 通常計算：`prepare_day`は`v2_core.engine.evaluate_day`を1回呼ぶ（A-08の試験で呼出し回数を確認）。再計算：`validate_snapshot`が`apply_transition`を呼ぶ。どちらもv2_coreの関数を直接使い、条件式・閾値・状態更新式を新パッケージに複製していない（A-08で、数値リテラル25／30／55の不在、`market_side_*`・`tri_and`の定義とimportの不在をASTで確認）。
- 新パッケージは`v2_core`のモジュールを書き換えない（A-08の静的検査と、既存ファイルのGit差分0）。
- `prepare_day`が`evaluate_day`の結果から組み立てる`transition_result`・`state_after`は、`apply_transition`で保存入力から再計算した結果と必ず一致する必要があり、不一致なら候補は破棄される（PREPAREDを出す前の全検査。§5）。
- コアのエラーは変換しない。台帳・日付・セッション・系列がコアに拒否された場合は元の`CoreError`（`InputError`／`ConflictError`）がそのまま送出され、NO_SIGNAL／NO_COMMITには変換しない（A-08）。

## 9. エラー優先順位：コア単体とラッパーの違い

`prepare_day`の検査順は固定：①Snapshot、②Dと必要sessions（Dの存在・確定・前後、新規Dなら基準境界の存在と全中間Sのconfirmed）、③台帳照合（適用済みDの日付昇順：必要セッションの有無→保存範囲の投影一致→`select_decision`→保存指紋、次に既存skipped_sessionsの日付昇順、最後に新規Dの中間区間の日付昇順）、④`evaluate_day`と同日比較（`input_hash`→`transition_result`→`state_after`）。

| 入力 | コア単体（`evaluate_day`） | S1（`prepare_day`） |
|---|---|---|
| 最新Dのdecision行が台帳から消えた | `rerun_decision_missing` | `ledger_mismatch` |
| 最新Dで同IDのdecisionが別値 | `decision_conflict_with_applied` | `ledger_mismatch`（単一の選択結果が保存指紋と異なる場合） |
| 同じrecord_idの旧行と新内容の併存／別IDの追加 | `record_id_conflict`／`decision_conflict` | 同じcodeを保持（`select_decision`の例外をそのまま送出） |
| 中間Sに窓外のdecision | 通る（`first_unprocessed_session`は窓を見ずに欠測扱い） | `decision_outside_window`（確定前に停止） |
| 適用済みDの保存セッションの時刻改訂 | 検出しない | `session_context_mismatch`（台帳選択より先） |
| 既存の欠測日に窓内の有効decision | 検出しない | `late_observation` |
| 中間Sに有効decision | `intermediate_session_unprocessed` | 同じcode（detailは最も早い対象日） |

コア単体の挙動はA-05の`CoreVersusWrapper`で試験した。保存Snapshot内部の不整合は`snapshot_invalid`に包み、注入入力のコアのcodeは上書きしない。

## 10. S1で確認したことと、していないこと（保留表）

| 区分 | 内容 |
|---|---|
| 確認した（このクラウド環境、別環境の試験） | A-01〜A-08（§4）、Python 4版・通信遮断下・クリーンクローンでの合格、5§の差替え、欠陥注入（§12） |
| 未確認：ユーザーPC | b616b4e全181件のユーザー実機確認は後日。Windows、`core.autocrlf=true`も未確認 |
| 未確認：耐久性・プロセス間 | MemoryStoreは同一プロセス内のスレッド間の比較更新のみ。プロセス終了後の保存、OSの置換、fsync、複数プロセス、Git pushの成否不明、通信再試行は対象外でS2。スレッド試験はCPythonのスレッドであり、本番の競合の証明ではない |
| 未確認：台帳 | 台帳の取得元・完全性・読取SHA・権限（S4）。`raw_observations`は呼出側が渡す不変の写しという契約で、取得元は証明していない |
| 未確認：配信 | outbox、送信、再送、通知の重複防止、`ALREADY_APPLIED`は自分の送信権を意味しない（通知のAPIを設けていない） |
| 未実施（設計どおり対象外） | ACK、欠測宣言、復元、再初期化、過去Dの自動追いつき、実時刻・自動対象日、実ファイル／Gitへの保存（S2〜S4） |
| 既存の保留（変更なし） | 実カレンダー、歴史遅延1全日照合（補正版§11.5）、既存候補920e695の試験 |
| 後工程へ残す3点 | ①市場値は厳密比較のまま。調整価格の改訂や浮動小数の差でも停止する。市場入力の版固定とU-07はS2／S4で一緒に決める。②`CORE_SHA`は版を示す定数で、実行中の`v2_core`の真正性を検査しない。A-01の「既存ファイルのGit差分0」を前提とする。③`reconcile`は自分と他の実行の同一内容を区別しない。S2以降で自分の保存への到達性を扱う場合は、計画識別子とスキーマ版の上げが別途必要 |
| `sessions`の供給範囲 | S1の呼出側は GENESIS 以降の全履歴を照合できる`sessions`を注入する契約。必要な範囲と固定版カレンダーの供給方法はS2／S4で決める。実カレンダーの取得や訂正の許容は実装していない |
| 完全性の限界 | `validate_snapshot`はハッシュ連鎖と保存入力からの再計算による整合性の検査で、真正性（書き換えられていないこと）の証明ではない。全項目を書き換えて再計算し直した履歴は区別できない（A-03に、判定が変わらない書換えを受理する限界の例を置いた） |
| 未決のまま | 保存先の選定、U-01／U-11／U-13は未決。S1は採用済みの意味を持たない |

## 11. 変更ファイル一覧、保護参照、本番操作

変更ファイル（b616b4e との差分。追加のみ、17件）：

| 区分 | ファイル |
|---|---|
| 新規 | `v2_persistence/__init__.py`、`codec.py`、`errors.py`、`events.py`、`plan.py`、`recompute.py`、`runner.py`、`store.py`（8本） |
| 新規 | `tests/v2_persistence/p_helpers.py`、`test_a02_init_structure.py`、`test_a03_recompute.py`、`test_a04_single_day.py`、`test_a05_timeline_ledger.py`、`test_a06_concurrency_reconcile.py`、`test_a07_failure_independence.py`、`test_a08_boundaries.py`（8本） |
| 新規 | `docs/implementation/V2_PERSISTENCE_DOMAIN_RESULT.md`（この文書） |

変更していないもの：既存181件を構成するファイルと基準データ、`v2_core/`、研究コード、`main.py`、依存・設定・workflow、`CLAUDE.md`、`docs/STATUS.md`、既存の結果文書、設計書・依頼書。

保護参照（`git ls-remote`、開始時と終了時）：

| 参照 | 完全SHA | 開始時 | 終了時 |
|---|---|---|---|
| main | `31144d9b6af8a6c920ad53c395cd550e8c48a7fa` | 同じ | 同じ |
| feat/interim-notification-20261026 | `920e69571cf4feda09f3f2f560e96fcb9cb09d50` | 同じ | 同じ |
| docs/v2-roadmap-20261023 | `647aeac34cde0d01ec27174f7620aff1724af0e1` | 同じ | 同じ |
| feat/v2-offline-core-20261027 | `1a54a8573023af9490017b02a8b6458f061031c7` | 同じ | 同じ |
| feat/v2-core-state-checks-20261028 | `b616b4ec7169420e199ec7e247dd375b3603a013` | 同じ | 同じ |
| docs/v2-persistence-domain-20261028（採用資料、読取専用） | `425df80d04b116e25e481184069b89bed1380c3a` | 同じ | 同じ |
| docs/v2-market-state-recovery-20261027（上位資料、読取専用） | `b43205ce1a53e4560fb85f9cfb715c72a1132a75` | 同じ | 同じ |

PRなし。本番反映、停止解除、Actions起動、Discord／Sheets送信、実データの外部保存、口座操作、API登録・契約・課金はしていない。

## 12. 欠陥注入による試験の感度（保存しない一時確認）

依頼書どおり、前工程の43欠陥注入や3114ケース生成は作り直していない。今回の試験が本当に効くかを確かめるため、一時コピーに新パッケージの欠陥を1つずつ入れて新規試験を実行する一時スクリプトを使った（リポジトリには保存していない。保存するとtests/v2_persistenceの範囲外の道具が増えるため）。

試験対象SHA `5083b37` のコードに対し、**57通り**を用意した（第1版では「58通り」と書いたが誤り。58は一時スクリプトの出力行数で、57通りの結果行に最後の集計の1行が加わった数だった）（ストアの比較・全検査・ロックの除去、ハッシュ連鎖・正準形・基点IB-04・再計算比較・保存入力の各検査の除去、実行側のセッション確認・台帳照合・投影比較・再実行比較・候補の自己検査・入力の写しの除去、投影の誤り、Snapshot／計画の戻り値の共有、重複キー・NaNの許容、`reconcile`の緩和など）。結果：

- **検出55**（新規試験が失敗した）。55＋対象外1＋同値の未検出1＝**57**で、総数と一致する。
- **適用対象外1**：`fixed_decision`の明示検査を外す案は、実装で冗長な検査を削除済み（§13の5）のため該当コードが無い。
- **検出されない1**：保存した窓での`select_decision`の省略（`stored_window_select_skipped`）。投影一致の後は窓が常に同じになるため結果が変わらない同値の変更で、試験で検出できないのは構造上のもの（§13の3）。

最初の一巡では、入力の写し（台帳・sessions）の省略、`serialize_transition`の`notes`落とし、`reconcile`の親hash無視も検出されなかった。そのため「実行中に呼出側が入力を書き換える」試験、系列の写しを`prepare_day`の最初に移す修正、親hashだけが違う計画の試験を追加し、全て検出されるようにした（コミット a28d8ce に含まれる）。ロック除去の欠陥は、この反復では検出されたが、競合は確率的な現象なので、全ての実行での検出を保証するものではない。

## 13. 実装上の判断と設計との違い

1. **イベントの型**：GENESIS／APPLYを専用クラスにせず、Snapshotの不変値の中の正準JSON辞書とした（§7.1）。
2. **`validate_snapshot`の戻り値**：失敗は例外。成功時は呼出側（`prepare_day`）が使う`ValidatedSnapshot`を返す（設計は戻り値を規定していない）。
3. **保存範囲の検査**：設計§7.1の「保存した窓と今回注入した窓の両方でselect_decision」は、両方を実行している。保存範囲の投影が現在と一致した後は、窓を決めるD自身の`close_at`とnext(D)の`open_at`が両者で等しいため、結果は常に同じになる（そのためこの2回目の呼出しを省いても結果は変わらず、試験では区別できない（§12））。
4. **`prepare_day`の入力の写し**：台帳と`sessions`は処理の最初に写しを作る。系列は日付を検査した直後に`series.through(D)`で1回だけ写し、以降はその写しを使う（`evaluate_day`にも写しを渡す）。
5. **`fixed_decision`の明示検査は置いていない**：`apply_transition`による再計算が`state_after`（`fixed_decision`を含む）を完全一致で比較するため、同じ違反は`state_mismatch`で検出される（A-03）。
6. **非有限の市場値**：系列が非有限値を返した場合は`snapshot_invalid`（rule=`event_build`）で止め、範囲外の有限値は候補の全検査で`row`として止める。
7. **`reconcile`**：書込み・再試行をしない。同じDの記録が親hash・入力hash・`transition_result`・`state_after`の全てで一致したときだけ`ALREADY_APPLIED`（先頭が進んでいてもよい）。同じDで異なれば`concurrent_conflict`、Dが無ければ`REPLAN_REQUIRED`。
8. **A-06のD違いの計画**：双方を同じ初期先頭から作れる台帳条件は、「境界D0は共通、計画1はD1のdecisionだけ、計画2はD1にdecisionが無くD2のdecisionがある（D1は欠測として計画に含まれる）」。
9. **ルールIDの扱い**：`state_after`の検査失敗は`state_after:<I-xx／IB-xx>`の固定識別子で包む（値は出さない）。
10. **依頼書・設計書との矛盾、既存181件の失敗、v2_coreの変更の必要性**：無かった。

## 14. 再現手順

    git clone -c core.autocrlf=false https://github.com/Rocky009-jp/soxl-alert
    cd soxl-alert && git checkout feat/v2-persistence-domain-offline-20261028
    python3 -B -m unittest discover -s tests/v2_core                        # 既存181件
    python3 -B -m unittest discover -s tests/v2_persistence -p "test_*.py"  # 新規154件
    # 通信遮断を強めるとき（Linux）：unshare -rn python3 -B -m unittest ...

## 15. 第2版：受領レビュー（R-01〜R-03、P-01）への対応

### 15.1 記録

| 項目 | 値 |
|---|---|
| 受領レビュー | `da24fcd4fcd70a51753ff61b3f9aa1436ec431c2`（`docs/v2-persistence-domain-s1-receipt-20261028`）。レビュー本文と再現スクリプト `V2_PERSISTENCE_DOMAIN_S1_REPRO_20261028.py`。依頼は coordinator 経由で、レビュー§6の限定修正案の範囲 |
| 修正の基準 | `b9586d65aa411bfe32ca6fe795ad4b15e972d59c` |
| 修正ブランチ | `fix/v2-persistence-domain-s1-review-20261028`（新規。実装ブランチ `feat/v2-persistence-domain-offline-20261028` は b9586d6 のまま不変） |
| 修正・試験のコミット（試験対象SHA、完全） | `e37275df1208a8c896954645e1997826f80a139e` |
| 保存最終SHA（完全） | 報告に記載（この文書の追加だけが差分。§15.5） |
| モデル／エフォート | 第1版と同じセッション（`claude-sonnet-5-5`、`high`） |
| 環境 | 第1版と同じ（Ubuntu 24.04.5、Python 3.10.20／3.11.17／3.12.3／3.13.17、`core.autocrlf=false`） |

### 15.2 修正内容

| ID | 原因 | 修正（`v2_persistence/` のみ） |
|---|---|---|
| R-01 | `validate_snapshot` が `Snapshot` の内部の辞書（`_internal()`）を直接読み、戻り値の `ValidatedSnapshot`、`AppliedDay`、`MarketState`（そこから `evaluate_day` の `next_state` へ）が、ストアの保存内容への参照を持っていた | `recompute.py`：入口を `snapshot.to_dict()`（呼出しごとの深い写し）に変更。戻り値の構造化データはどれも保存内容と独立になる。ほかの公開API（`Snapshot` の各アクセサ、`AppendPlan.event`、`read`／`commit`／`reconcile`／`make_genesis`／`decode_snapshot` の戻り値）は第1版から写しまたは不変値で、今回全て確認した（§15.3） |
| R-02 | `events.row_dict` が型検査の前に `float()` を呼び、`True` が `1.0` として保存候補に入った | `events.py`：`_market_float` を追加し、float変換の前に bool と数値以外を拒否。D行は rule=`row`、前日行は rule=`prev_row` の `snapshot_invalid`。通常の int／float は従来どおり float に正規化 |
| R-03 | 保存入力の `_num` が `float(x)` の `OverflowError`（10**400 など）を包んでいなかった | `recompute.py`：`_num` で `OverflowError` を `snapshot_invalid` に変換。同じ原因の経路として、保存された decision の値をコアの `parse_observation` に渡す箇所（コアは10**400で `OverflowError` を出す）も `snapshot_invalid`（rule=`decision`）に変換。`events.py` 側（準備時の組立て）にも同じ変換 |

既存の `v2_core`、既存181件、基準データ、依存・workflowは変更していない。b616b4e との差分は追加18ファイル（A）のみで、変更・削除は0件。第1版の結果文書以外にこの修正で変わったファイルは `v2_persistence/events.py`、`v2_persistence/recompute.py`、`tests/v2_persistence/test_a07_failure_independence.py`（ランダム編集の候補値に巨大整数を追加）、新規 `tests/v2_persistence/test_s1_review_fixes.py`（16件）。

### 15.3 回帰試験（`test_s1_review_fixes.py`、16件）

| 対象 | 試験の内容 |
|---|---|
| R-01（5件） | レビューの4経路（`NO_COMMIT` の `next_state.fixed_decision`、`boundary_session`、`applies[0].transition_result`、`applies[0].state_after`）。検証結果の全項目（`AppliedDay` の `context`／`stored_sessions`／`skipped` を含む）と、PREPARED／NO_COMMIT／ALREADY_APPLIED の `core_result` の `next_state`・`rules`・`notes`・`series_meta`、`plan.event`、`store.read()`／`commit`／`reconcile`／`make_genesis`／`decode_snapshot` の戻り値の全ての辞書・リストを書き換える。比較の基準は編集前に取った深い写しで、`to_dict`、`encode_snapshot`、先頭、encode→decodeの結果、`validate_snapshot` の再検査を全て確認。同じSnapshot参照との比較だけにはしていない |
| R-02（5件） | D行・前日行の5項目×True／False を拒否（`snapshot_invalid`、rule=`row`／`prev_row`、計画なし、状態不変）、系列の巨大整数の拒否、`row_dict` の直接呼出し、正常な int／float 入力の float 正規化と従来どおりの PREPARED→commit→ALREADY_APPLIED |
| R-03（6件） | 保存した `row` の5項目、前日行の5項目、decisionの値に正負の10**400（JSON往復後）、レビューの再現手順、`prepare_day`／`MemoryStore.initialize`／`reconcile` がそのSnapshotを `snapshot_invalid` で拒否、5000桁の整数テキスト（3.11以降はデコード段階、3.10は検証段階で `PersistenceError`）。例外文に桁が出ないことも確認 |

**旧コード（b9586d6）に対する回帰試験の結果**：16件中13件が失敗または error（R-01の4件、R-02の4件、R-03の5件）。残り3件（R-01の公開アクセサ、R-02の正常な正規化、5000桁テキスト）は旧コードでも正しく動く部分の確認。

**修正を1つずつ戻す欠陥注入（一時確認、保存しない）**：検証入口を `_internal()` に戻す、bool拒否を外す、`_num` の変換を外す、decision側の変換を外す、組立て側の変換を外す、前日行の厳密化を外す、の6通りを全て試験が検出した（検出6、未検出0）。

**レビューの再現スクリプト**（`--expect-fixed`）：b9586d6 では10観測すべてで現象が出て終了コード1。第2版（e37275d、クリーンクローン）では10観測すべて `issue_present=false`、終了コード0（R-01=4経路、R-02=5項目、R-03=1入力）。

### 15.4 試験結果（試験対象 `e37275d`、クリーンクローン、`unshare -rn` 下）

    <python> -B -m unittest discover -s tests/v2_core                              # 既存（181件）
    <python> -B -m unittest discover -s tests/v2_persistence -p "test_*.py"        # 新規（170件）

| Python | 既存 | 新規 | skip | 終了コード |
|---|---|---|---|---|
| 3.10.20 | 181 合格 | 170 合格 | 0 | 0 / 0 |
| 3.11.17 | 181 合格 | 170 合格 | 0 | 0 / 0 |
| 3.12.3 | 181 合格 | 170 合格 | 0 | 0 / 0 |
| 3.13.17 | 181 合格 | 170 合格 | 0 | 0 / 0 |

新規170件＝第1版の154件（弱めていない）＋回帰16件。A-06の競合試験は修正後も3.10.20と3.13.17で各40回、失敗0。ユーザーPCでの b616b4e 全181件の確認は後日のままで、今回も別環境（Linux）の試験として区別する。

### 15.5 変更ファイルと保護参照

- 修正ブランチの b9586d6 からの差分：上記の `events.py`、`recompute.py`、`test_a07_failure_independence.py`（変更）、`test_s1_review_fixes.py`（追加）。この結果文書の更新は別コミット。試験対象 `e37275d` と保存最終SHAの差分は、`docs/implementation/V2_PERSISTENCE_DOMAIN_RESULT.md` の変更だけであることを報告時に確認する。
- 保護参照は第1版と同じ：main `31144d9b6af8a6c920ad53c395cd550e8c48a7fa`、候補 `920e69571cf4feda09f3f2f560e96fcb9cb09d50`、資料正本 `647aeac34cde0d01ec27174f7620aff1724af0e1`、旧コア `1a54a8573023af9490017b02a8b6458f061031c7`、実装基準 `b616b4ec7169420e199ec7e247dd375b3603a013`。実装ブランチ `b9586d65aa411bfe32ca6fe795ad4b15e972d59c`、採用資料 `425df80d04b116e25e481184069b89bed1380c3a`、上位資料 `b43205ce1a53e4560fb85f9cfb715c72a1132a75`、レビュー資料 `da24fcd4fcd70a51753ff61b3f9aa1436ec431c2` は読取専用で、開始・終了時の `git ls-remote` で不変を確認する（終了時の結果は報告に記載）。PRなし、本番操作なし。

### 15.6 P-01：欠陥注入の集計と、fixture依存の1件の扱い

**欠陥注入の集計（訂正）**：総数は**57通り**（58ではない）。内訳は検出55、適用対象外1（`fixed_decision_unchecked`：冗長な明示検査を実装から削除したため該当コードが無い）、同値で検出不能1（`stored_window_select_skipped`）で、55＋1＋1＝57。スクリプトは保存していないが、独立確認のため57通りの名前を残す（試験対象 5083b37 に対する第1版の確認。修正後の全再実行はしていない）。

> 検出55：cas_check_removed、commit_no_validation、event_hash_unchecked、parent_hash_unchecked、seq_unchecked、d_order_unchecked、IB04_unchecked、transition_unchecked、state_unchecked、input_hash_unchecked、skipped_unconfirmed_unchecked、skipped_list_unchecked、canonical_unchecked、decision_window_unchecked、head_hash_unchecked、current_state_unchecked、core_sha_unchecked、context_continuity_unchecked、intermediate_unconfirmed_unchecked、intermediate_unprocessed_unchecked、late_observation_unchecked、ledger_fingerprint_unchecked、ledger_none_unchecked、projection_mismatch_unchecked、projection_includes_all、projection_drops_open_at、context_missing_unchecked、rerun_input_unchecked、rerun_transition_unchecked、rerun_state_unchecked、candidate_check_removed、target_not_after_genesis_removed、state_ahead_removed、ledger_not_copied、sessions_not_copied、no_commit_gives_plan、serialize_drops_notes、snapshot_events_shared、snapshot_state_shared、snapshot_to_dict_shared、dup_keys_allowed、nan_allowed_in_decode、initialize_accepts_apply、genesis_unconfirmed_ok、reconcile_ignores_parent、reconcile_head_moved_is_success、reconcile_conflict_ignored、already_initialized_ignored、plan_event_shared、lock_removed_commit、range_check_removed_state_rule、rsi_range_removed、prev_session_date_unchecked、genesis_state_unchecked、session_context_next_unchecked。  
> 対象外1：fixed_decision_unchecked。同値1：stored_window_select_skipped。

**fixture依存の1件**：`test_a03_recompute.RoundTrip.test_research_fixture_chain_matches_core_and_survives_json` は、リポジトリ内の研究fixture（`research/SOXL_audit_20261023/data` の `daily.json`、`daily_adjclose.csv`、`fear-greed.csv`）を読む。受領レビューの確認環境にはこれが無く、153件だけを実行して1件を実行対象から外し、合格・skipとして集計しなかった。作業者の環境では、fixtureを含む完全なクリーンクローン（上記）で**この1件も実行して合格している**（170件の1件として。skip=0）。この試験が使うfixtureのGit blobは、既存のA1試験が固定値で照合している（`test_a1_research_parity.py` の `PIN`）。fixtureを揃えない環境では、この1件は「未実施」と書き、合格・skipに数えない。

### 15.7 コア側の発見（今回は着手しない）

`v2_core/observations.py` の `_parse_value` は、`current_fg_value` が float に変換できない巨大な整数（10**400など）のとき、`InputError` ではなく `OverflowError` を出す。台帳（呼出側が注入する `raw_observations`）にこの値があると、`prepare_day`／`select_decision`／`evaluate_day` が規定のエラーでなく `OverflowError` で止まる（状態は変わらない）。R-03の対象は保存入力であり、コアの変更は範囲外のため、保存入力側（`validate_snapshot` が呼ぶ `parse_observation` の結果）だけを変換した。原因は `float(raw)` の例外が捕捉されていないこと。最小差分案は、`_parse_value` の `float(raw)` を `try/except OverflowError` で包んで `InputError("fg_value_invalid", "current_fg_value")` に写すこと。これは既存181件の動作を変えない見込みだが、`v2_core` の変更になるため、別承認が必要。

### 15.8 保留（変更なし）

ユーザーPCでの181件確認、実ファイル保存、耐久性、複数プロセス、台帳完全性、配信、ACK／復元、Windows、実カレンダー、歴史遅延1の全日照合、S2以降は第1版の§10のまま未実施・未承認。

