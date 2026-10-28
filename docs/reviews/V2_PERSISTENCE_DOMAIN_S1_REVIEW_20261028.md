# V2 保存ドメイン S1（設計書・限定実装依頼書）レビュー結果

作成日：2026-10-28  
レビュー担当：Claude（読み取りレビューのみ。コード変更・試験実行・PR作成なし）  
採否：Rockyさんが判断する。本書の推奨は採用・実装承認を意味しない。  
リポジトリへ保存する場合のパス案：`docs/reviews/V2_PERSISTENCE_DOMAIN_S1_REVIEW_20261028.md`

---

## 1. 対象と参照したファイル

| 区分 | 内容 |
|---|---|
| 開始SHA（レビュー対象） | `97bdd98324098422ed034d87d5521ecc29dc2689`（branch `docs/v2-persistence-domain-20261028`） |
| 対象文書 | `docs/specs/V2_PERSISTENCE_DOMAIN_OFFLINE_DESIGN_DRAFT.md`（以下「設計」）、`docs/tasks/V2_PERSISTENCE_DOMAIN_OFFLINE_REQUEST.md`（以下「依頼」） |
| 差分の確認 | `b616b4e..97bdd98` は上記の新規2文書のみ（+305行）。コミットは 3963ecd、97bdd98 の2件 |
| 突き合わせたコア | `b616b4ec7169420e199ec7e247dd375b3603a013` の `v2_core/engine.py`、`transition.py`、`state.py`、`observations.py`、`sessions.py`、`fixture.py`、`indicators.py`、`errors.py` |
| 上位設計 | `e3e90947a718cca877b543739ca60539207ca7a7` の `V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md` §2.1〜2.8、§3.4〜3.8、§6.2〜6.7、§8、§9 |
| その他 | `CLAUDE.md`（§3、§8、§9）、`docs/specs/DATA_SESSION_CONTRACT_DRAFT.md`（セッションの「確定」の意味） |
| 未取得 | なし（STATUS.md・ROADMAP.md・MODEL_POLICY.md は存在のみ確認、本文は今回の論点に不要のため未読） |

保護参照（`git ls-remote`、レビュー開始時）：main `31144d9`、候補 `920e695`、資料正本 `647aeac`、旧コア `1a54a85`、実装基準 `b616b4e` はいずれも依頼§1の完全SHAと一致。e3e9094 は `docs/v2-market-state-recovery-20261027`（先頭 b43205c）の祖先であることを確認。

## 2. 結論

**重大0・通常2・提案8。** S1の範囲（メモリ上の検証に限定、実ファイル・ACK・通知を後工程へ分離）、コア非変更、「通常計算は evaluate_day、保存入力からの再計算は apply_transition」という委譲の構成は、上位第4版とb616b4eのコードに整合しています。誤った売買判定や先読みにつながる箇所は見つかりませんでした。

ただし通常2件は、どちらも「正しく確定した記録が、台帳も入力も変わらないまま次の実行で停止する」という同じ種類の欠陥で、受入試験でも見逃されやすい形です。**N-01・N-02を文書で直してから実装依頼へ進めることを推奨します。** 修正はいずれも数行の追記で済み、範囲の拡大は不要です。

## 3. 指摘表

### 通常

| ID | 根拠 | 内容と影響 | 修正案 | 確認方法 |
|---|---|---|---|---|
| **N-01** 準備時の検査が次回実行時の検査より狭い | 設計§7.1（欠測区間は `select_decision` で検査）、§7.2（新しいDの途中検査はコアに委譲）。コア `observations.py:145-162` `first_unprocessed_session` は**窓内**のdecisionだけを数え、`select_decision`（同116-142）は窓外なら `decision_outside_window`、窓内の別対象なら `target_mismatch` を出す | 新しいDの準備では、間のセッションSは `first_unprocessed_session` だけで検査される。Sを対象とする**窓外の**decision行、またはSの窓内で別の日を対象にした行は見逃され、Sは `skipped_sessions` に入って確定する。ところが次の実行（同じDの再実行を含む）では§7.1がSに `select_decision` を呼ぶため `decision_outside_window`／`target_mismatch` で止まり、S3のACKが無いS1では解除手段がない。台帳を一切変えていないのに「準備→確定→同入力で再実行」が停止する | 新しいAPPLYの `skipped_sessions` になるセッション（初回は境界の次から、通常は `as_of_d` の次からDの前まで）に、**§7.1と同じ関数**で `select_decision` を準備時にも適用し、行があれば計画を作らずに止める、と§7.2に明記する。原則として「準備時の検査 ⊇ 次回実行時の検査」を設計に書く | A-05に追加：(a) 間のセッションに窓外decisionがある台帳で準備が止まり計画が出ない、(b) 間のセッションの窓内に別対象の行がある場合も同様。A-04に不変条件を追加：受け付けた全ケースで「commit後、同じ入力の prepare_day(D) は ALREADY_APPLIED」 |
| **N-02** 入力の同一性に、Dの判定に使わない時間変化の項目が入っている | 設計§5.2（session_context は次セッションまで、`confirmed` も保持、確認フラグの相違は同一入力と扱わない）。コアでは next(D) は `open_at` だけを窓に使う（`observations.py:112-113` `_in_window`、`engine.py:67`・`118`）。`confirmed` はデータ確定（終了＋猶予）を表す（DATA_SESSION_CONTRACT §対象セッション） | Dを確定する朝の時点では next(D) は通常 `confirmed=false`。next(D) の終了後に同じDを再実行すると `confirmed=true` に変わり、input_hash が変わって `recompute_mismatch` で止まる。判定にも窓にも影響しない値で停止する。next(D) の `close_at` も同じ（判定に不使用） | input_hash の対象から **next(D) の `confirmed` と `close_at` を除く**（保存は `SessionList.from_dicts` の都合で残してよい）。上位§2.2の例（next は date・open_at のみ）と揃う。D・前日・間のセッションの `confirmed` は従来どおり比較対象 | A-04に追加：next(D) の confirmed を false→true、close_at を変えて再実行しても ALREADY_APPLIED。対照として next(D) の open_at 変更は停止 |

### 提案

| ID | 根拠 | 内容 | 修正案 |
|---|---|---|---|
| P-01 | 設計§7.1・依頼§3.2・A-05 | 台帳の食い違いごとのエラーcodeが文書間で揃っていない。依頼§3.2は「削除／内容違いは ledger_mismatch」だが、コードを読むと、同じrecord_idの旧版と新版が両方ある場合は `_parse_all` が先に `record_id_conflict`、別IDの追加は `decision_conflict`、窓外の追加は `decision_outside_window` になる | 依頼に対応表を1つ置く：削除→ledger_mismatch／置換（旧行なし）→ledger_mismatch／同ID旧新併存→record_id_conflict／別ID追加→decision_conflict／窓外→decision_outside_window／欠測日に窓内の行→late_observation。A-05の期待codeをこれで固定する |
| P-02 | 設計§7.1「保存した窓と今回注入した窓の両方で照合」「両方の窓に必要なセッションが今回のsessionsに無ければ」 | (a)「両方に無ければ」は「どちらかが無ければ」の意と思われる。(b) 古い適用済みDについて、保存した session_context と今回の注入列が食い違う場合（時刻改訂など）に止めるのかが書かれていない。(c) 毎回、GENESIS以降の全セッションを注入する必要があることが運用上の前提になる | (a) 文言を直す。(b) S1では「適用済みDの保存範囲と今回の注入列が食い違えば session_context_mismatch で停止」または「保存窓だけを正とする」のどちらかを明記（前者を推奨、N-02と同じく next(D) の confirmed・close_at は除く）。(c) 保留表に「sessions の供給範囲は S2/S4 で決める」と記す |
| P-03 | 設計§5.1 GENESIS、§5.2「前方へ広げる」 | `start_after` と `boundary_session.date` の関係が書かれていない。基準境界は常に前日以前のセッションなので「Dの直前セッションまで前方へ広げる」が起きる場面が読み取れない | 「`boundary_session.date == start_after`、境界は注入列に存在し confirmed=true」を明記。広げる規定は不要なら削り、必要なら具体例を1つ書く |
| P-04 | 設計§8 reconcile「親が違えば…成功とはしない」 | 上位§3.8手順3は内容（指紋）の一致だけで成功扱い。S1は親hashも求めるので厳しい。S1の直線履歴では親が違えば input_hash・state_after.base も通常違うため実害はないが、上位との差であることが書かれていない | 「上位§3.8より厳しくしている、S3で退避履歴を入れる際に再検討」と1行添える |
| P-05 | 設計§7.2「候補状態をfrom_dictで再検査し」 | commit時の全検査で、evaluate_day の結果と保存入力からの再計算の食い違いは捕まる。ただし準備時に捕まえないと、PREPARED を返した計画が commit で必ず拒否される形になり得る | prepare_day でも、作ったAPPLYを validate と同じ再計算で自己検査してから PREPARED を返す、と明記（N-01の不変条件と合わせると「PREPARED なら commit で検査落ちしない」を試験できる） |
| P-06 | 依頼A-03「apply_transitionの実呼出をspyで確認」 | `engine.py:17-19` は `apply_transition` を名前で取り込み、`engine.py:106` でその名前を呼んでいるため、`v2_core.transition.apply_transition` を差し替えても evaluate_day 経路にも新パッケージ経路にも効かない | 依頼に「差し替えは `v2_core.engine.apply_transition` と新パッケージが参照する名前の両方を対象にし、どちらの経路を検査したかを結果文書に書く」と添える |
| P-07 | 依頼§5、CLAUDE.md §3 | 担当モデル Sonnet 5.5 は CLAUDE.md §3（明確な仕様の実装）に合う。エフォートの指定が無い。N-01のような検査範囲の整合を扱う実装なので、Rockyさんの方針（推論が必要な作業は high）に当たる | 「Sonnet 5.5、エフォート high」を推奨値として記載（採否はRockyさん） |
| P-08 | 依頼§1・§2 | (a) 設計が参照する上位第4版の置き場 `docs/v2-market-state-recovery-20261027`（b43205c）が保護参照の確認対象に入っていない。(b) §2の「display.py」は b616b4e では `v2_core/display.py` だけで、ルートには無い | (a) 開始・終了時の確認に読取専用の参照として追加（変更禁止の対象にするかはRockyさん判断）。(b) パスを `v2_core/display.py` と書く（v2_core 全体を変更しないので重複でもある） |

### 保留として記録を勧めるもの（指摘ではない）

- 市場値の厳密比較：S1の試験はfixtureなので問題ないが、本番で再取得したデータを使うと、調整後価格の改訂や浮動小数の微差でも同じDの再実行が `recompute_mismatch` で止まる。設計の意図（判定が同じでも止める）どおりだが、S2/S4で市場データの固定方法（取得版の固定など）とU-07をあわせて決める必要がある。
- `core_sha` は定数で、v2_core の実際の内容を検査しない。A-01の「既存ファイルのGit差分0」で担保される前提を結果文書に明記するとよい。
- reconcile の ALREADY_APPLIED は「自分が書いた」を区別しない（設計どおり）。S2以降で上位§3.8手順2（自分のコミットの到達性）を実現するには、計画ごとの識別子が必要で、スキーマの版上げになる。

## 4. 実施した確認

| 確認 | 結果 |
|---|---|
| 97bdd98 の差分範囲 | b616b4e からの差分は新規2文書のみ |
| 保護5参照の完全SHA | 依頼§1と一致（ls-remote） |
| e3e9094 の到達性 | b43205c の祖先 |
| 設計の前提とコードの対応（コード読解） | evaluate_day の再実行経路（`engine.py:83-92`）、初回の途中検査がコア単体では効かないこと（`engine.py:95-100`、`base.as_of_d is None` で飛ばす）、apply_transition が基点から fixed_decision/base を落とす（`transition.py:177-181`）、from_dict の現在状態と基点の分離（`state.py`）、同一記録の別オフセット表記の扱い（`observations.py:95-109`）は設計の記述どおり |
| N-01・N-02 | コード読解による。再現スクリプト・試験は実行していない（今回の範囲外） |

実施していないもの：試験実行、Python での再現、ユーザーPCでの b616b4e 全181件（設計§2どおり後日）。

## 5. 未解決事項と次の最小作業

1. N-01・N-02 を設計§5.2・§7.2と依頼A-04・A-05へ反映（数行）。
2. 提案のうち P-01（エラーcode対応表）と P-03（GENESIS境界）は、実装担当の解釈が分かれやすいので同時に入れることを推奨。その他は任意。
3. その後、依頼§6の「1組の判断」（S1の範囲・不一致時停止・受入条件・担当モデル／隔離Python環境）をRockyさんが行う。本レビューはその判断を代替しない。

## 6. 変更したもの

リポジトリ・設定・外部環境への変更なし。push・PR・Actions・通知なし。成果物は本ファイル（`/mnt/project-files/reviews/V2_PERSISTENCE_DOMAIN_S1_REVIEW_20261028.md`）のみ。
