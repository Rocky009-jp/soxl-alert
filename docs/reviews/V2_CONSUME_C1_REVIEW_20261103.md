# V2 C-1 CONSUME 限定実装 レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由のRockyさんの依頼。実装者の結論に頼らず、受入条件・変更境界・試行からの変更・変異の判断・分担・範囲試験・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常0・提案3。推奨は「受領」（限定修正は不要）。** 提案はどれも任意で、受領の条件にしない（P-01はC-2の依頼書へ、P-02は受領記録の注記で足りる、P-03は次にr4_09を触る機会）。
本レビューはPR・マージ・本番反映・C-2〜C-4への移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らして、CONSUMEが使うのは日足の決定と日足の市場値だけであることも確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | bfbde7a7854bf91a77fb58737c24b19c6507453a |
| ランタイム | c63912a27c4783e18f9fdbc2137e2daa70cd69aa |
| 試験対象 | **3f780c116964bbcfc8007b8e371f194bdca6db39** |
| 保存最終 | **de6549acb4ecea759cc771300fd0bef59dd5456a**（feat/v2-history-consume-c1-20261103、3f780c1からは結果文書1本の追加だけ） |
| 基準 | a6340c3937092e4cb658913b9acfb4973a084326（docs/v2-consume-s3c-20261103）の設計 docs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md、依頼書 docs/tasks/V2_CONSUME_C1_LIMITED_IMPLEMENTATION_REQUEST.md、試行差分 docs/specs/V2_CONSUME_C1_TRIAL_20261103.diff。D-1〜D-6採用済み。RockyさんのD-1〜D-6へのレビュー意見（D-2：検査器の成功だけで解放日・決定・市場値まで照合済みとしない） |

読んだもの：上の3文書、結果文書（共有フォルダの写しと一致）、ランタイム9ファイルの差分全文、既存試験4本の差分、新規試験6本（c1_helpers、test_c1_01〜04・09）、v2_history_restoreのchain.py・confirm.py・records.pyの全体、CLAUDE.md。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、C1-17） | **合格** | bfbde7a→de6549aでMは許可の13ファイル（ランタイム9、既存試験4）、Aはtests/v2_history_consume/の6本と結果文書だけ。`__init__.py`は作っていない。`__all__`、v2_history.KINDS（8種）、OPS（4つ）は不変。新しいimportはv2_persistence.events.decision_dictの1つ。test_sc_03の差分はENDの1行 |
| 受入C1-01〜C1-18 | **合格** | 4版で既存1634＋鎖34＋新規112が合格。各IDの試験を読み、主要な規則は独立の変異で殺せることを確かめた（§4.4） |
| 試行からの変更3点（結果§5の1〜3） | **3点とも妥当** | 試行を適用したツリーと実装を同じ入力で比べた（§3） |
| 変異11の等価 | **等価と認める** | 論証を確認し、14,941通りの総当たりで区別できる入力が0（§4.3） |
| 検査器の成功を照合済みとしない分担 | **守られている** | 解放日・決定・市場値は計画（build.py）と確認（再構築の全basis比較）だけで確かめる。検査器は解放日でない日のCONSUMEを受け付け、計画は同じ日をrestore_consume_not_releasedで拒否することをプローブで確かめた（§4.5） |
| 範囲試験（D-5） | **合格** | test_sc_03のEND＝bfbde7a。test_c1_09はSTART＝bfbde7a、END＝None、REV＝END or "HEAD"で、Gitだけを読む。鎖の試験は新しい開いた範囲を受け入れ、STARTを1つ前に戻すと失敗する（§4.6） |
| 保護71参照 | **一致** | 2026-11-03T13:18Zに`git ls-remote`の完全SHAで71件とも一致。依頼書§7の表から独自に作った一覧と、実装者のprotected_refs.txtは同じ71行。記録のpush後にも照合（§6） |

## 3. 試行の差分からの変更3点

試行の差分（a6340c3のV2_CONSUME_C1_TRIAL_20261103.diff）を使い捨てのbfbde7aのworktreeに適用し、実装（3f780c1）と同じ入力で比べた（`v2_consume_c1_review_20261103/c1_trial_compare.py`、`c1_change2.py`）。

| # | 変更 | 試行 | 実装 | 判定 |
|---|---|---|---|---|
| 1 | REAPPLYの前に置いたCONSUMEの日を「新たに飛ばす日」に数える（`new_skips`） | 設計§3.1の4つ目の場面（暦にセッションSが加わり、REAPPLY D11がSを新たに飛ばす）で`CONSUME S, REAPPLY 2`が**restore_consume_not_released** | **READY** | **必要な修正**。試行は設計が想定した場面を通せていなかった |
| 2 | `_reapply`の位置の防御（基点<Dでなければrestore_consume_order） | `DROP 4, CONSUME D3, CONSUME D5, REAPPLY 5(D4)`でnot_released（区間の基点D5がD4より後のまま下書きを作り、空のsession_contextの下書きが一時的にできる） | restore_consume_order（detail＝D5） | **妥当**。拒否は両方で起きるが、実装は壊れた下書きを作らない。C1-10の順序（位置の誤りは段階4の組立て中）にも合う |
| 3 | 確認の段階1で、計画のopsと候補のRECOVERY_RESTOREのopsの一致（CONSUMEを含むときだけ） | CONSUMEの日だけを変えてhashを付け直した計画がhistory_plan_stale | history_plan_mismatch | **妥当**。C1-13（改変はmismatch）を満たす。CONSUMEが無いときに限るのはC1-14（同じ文字）を守るためで、無い場合の結果は従来どおり |

変更1の正しさを、記録の幾何から確かめた。`_reapply`のskipped_sessionsは「基点とDの間の全セッション」（宣言した日も含む）なので、元のREAPPLYのskippedは元の暦の間のセッションを全部含む。REAPPLYの前のCONSUMEの日はすべて「CONSUME前の基点」とそのREAPPLYの日の間にある（基点<Dの検査が順に効く）。したがって`(new.skipped ∪ consumed_since) − old.skipped`は「CONSUMEが無かったときの新しいskipped − old.skipped」と同じ集合で、設計の定義（B-4§8の、候補の適用日で除く前の集合）を広げていない。REPLAYで残した宣言の日・復元点に残した宣言の日はold.skippedに含まれるので除かれる。プローブで確かめた：`REPLAY 4, CONSUME D3, REAPPLY 5`も、復元点を宣言（seq 4）に取った`CONSUME D3, REAPPLY 5`も**restore_consume_not_released（D3）**。

変異で確かめた：変更1を試行の式へ戻す（m06d）、変更2を外す（m12b）、変更3を外す（m18）は、どれも新規の試験で検出された（§4.4）。

## 4. 実行した確認

### 4.1 全スイート（4版）

Linux 6.18、`unshare -n -r`、版ごとに別の完全履歴のクリーンクローン（core.autocrlf=false、`git checkout 3f780c1`）、`PYTHONDONTWRITEBYTECODE=1 <python> -B -W error::ResourceWarning -m unittest discover`（新規は`-p "test_c1_*.py"`）。ランナーは`v2_consume_c1_review_20261103/runall.sh`。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---:|---|---|---|---|
| v2_core | 197 | OK | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK | OK |
| v2_persistence_local | 113 | OK（skip 4） | 同左 | 同左 | 同左 |
| v2_recovery | 176 | OK | OK | OK | OK |
| v2_history | 230 | OK | OK | OK | OK |
| v2_history_ops | 173 | OK | OK | OK | OK |
| v2_history_restart | 109 | OK | OK | OK | OK |
| v2_history_restore | 165 | OK | OK | OK | OK |
| v2_history_diagnose | 131 | OK | OK | OK | OK |
| v2_history_adopt | 170 | OK | OK | OK | OK |
| v2_scope_chain | 34 | OK | OK | OK | OK |
| v2_history_consume（新規） | 112 | OK | OK | OK | OK |
| 合計 | **1780** | 1776合格＋4 skip | 同左 | 同左 | 同左 |

全スイートrc＝0、失敗0、error0。skip 4はWindows専用（開始点と同じ）。`git archive 3f780c1`のツリー（Python 3.13.18）では、v2_history_consumeがskip 22、v2_scope_chainがskip 33で、結果文書§7.1と同じ。Windowsは未実施（この環境に無い）。

### 4.2 境界の入力（`c1_review_probe.py`）

| 入力（s_tail等はc1_helpersの場面） | 結果 |
|---|---|
| 暦の最後のセッション（next(D)が無い）をCONSUME | next_session_missing（例外の漏れなし） |
| check_dより後の日をCONSUME | restore_consume_not_released |
| CONSUMEする日のセッションが未確定 | target_unconfirmed |
| next(D)が未確定 | READY（通常の日と同じ。next(D)は開場時刻だけを使う） |
| 週末（セッションでない日） | target_not_in_sessions |
| 日付の形の誤り | restore_invalid／ops／ops_shape |
| CONSUMEがREAPPLYの後（設計§3.10） | restore_consume_order |

想定外の例外（AttributeError等）はどの入力でも出なかった。

### 4.3 変異11（無効果の規則でCONSUMEを数えない）の等価

結果文書の論証を確認した：CONSUMEがあってDROPが無い計画が無効果の規則に届くには、CONSUMEの日が解放日でなければならず、DROPが無ければ「REAPPLYが新たに飛ばす日」しかない。その日をCONSUMEするにはそのREAPPLYの前に置くしかなく（後ろならrestore_consume_order）、そのREAPPLYの基点が変わってsession_context（input_hash）が変わるので、same_as_supersededは必ずfalseになる。したがって元の条件と変異の条件は、到達できるすべての入力で同じ値になる。

独立の総当たり（`c1_mut11_search.py`）：7つの場面（宣言の間、再開始の飛び越し、再開始の間、ACKの間、古いskip、二重の再開始、暦の変更）で、DROPを使わない処分の列に1〜2個のCONSUMEを全位置・全日に挿し、消費する日にだけ決定を足して計画した。14,941通りのうちREADYでCONSUMEを含みDROPの無い計画は2件（どちらも暦の変更の場面）で、どちらも後続REAPPLYがsame=false。区別できる入力は0件だった。**等価の判断を認める。**

### 4.4 独立の欠陥注入（`c1_review_mutants.py`）

実装者のランナーとは別に、3f780c1の使い捨てのworktreeを1件ずつ壊して新規112件（検査器・無効果の変異はB-1・B-4も）を実行した。

| ID | 壊し方 | 結果 |
|---|---|---|
| m01 | 検査器：CONSUMEの日と作られたAPPLYの日の比較を外す | 検出（1件） |
| m03 | 検査器：requestバッチの間の規則を外す | 検出（2件） |
| m05 | 計画：解放日の検査を外す | 検出（6件） |
| m06c | 計画：REAPPLYで新たに飛ばす日を解放日から落とす | 検出（2件） |
| m06d | 計画：`new_skips`を試行の式（CONSUMEの日を数えない）へ戻す | 検出（2件） |
| m09 | 計画：evaluate_dayの再計算をREAPPLYだけにする | 検出（2件） |
| m11 | 計画：無効果の規則でCONSUMEを数えない | **生存（等価、§4.3）** |
| m12b | 計画：`_reapply`の位置の防御を外す | 検出（1件） |
| m14 | 確認：series_inputsの読み直しでCONSUMEの日を落とす | 検出（48件） |
| m18 | 確認：段階1のopsと候補の一致を外す | 検出（3件） |
| m19 | 計画：restore_consume_duplicateのdetail（日）を外す | 検出（1件） |
| m20 | 計画：残す記録の行の並べ替えを外す | 準備失敗（置換が2か所に一致、未実行） |

変異7（決定を生の台帳から選ぶ）と段階7の選び直しは、実装者の記述どおり、通常の入力では差が出ないと読んだ。残す記録（復元点までのACK・宣言）が名指すのはAPPLY済みの日か復元点までの宣言の日で、どちらも解放日になれないからである。試験はapply_records・select_decisionのスタンドインでこの分岐を通している。依頼書C1-08が「spyまたは合成入力で通す」と認めているので受入の範囲内で、結果文書§10にも明記がある。

### 4.5 検査器と計画の分担（`c1_division.py`）

再開始をREPLAYし（D3まで飛ばしたまま）、REAPPLY D4の後にD5をCONSUMEする復元を考える。

- 計画：`restore_invalid／ops／restore_consume_not_released（D5）`。
- 同じ復元を独立のビルダー（c1_helpers.oracle）で書いた履歴：**validate_historyは受け付ける**。

D-2(ii)のとおり、検査器は形・位置・日・バッチの間だけを見て、解放日を確かめない。実装は、解放日・決定・市場値の確かめを計画（`_check_consumed_released`、`_consume_inputs`、`_check_consumed_decisions`、`_check_days_again`）と確認（同じ入力で計画を作り直し、全basisと候補を比べる）に置いていて、検査器の合格をその代わりにしている箇所は無い。restore.pyのdocstringと結果文書§2・§10も同じ分担を書いている。ただ、この境界（検査器が受け付けるのに計画が拒否する履歴があること）を固定する試験はまだ無い（P-01）。

### 4.6 範囲試験と鎖

- test_sc_03：`END = "bfbde7a…"`の1行だけ（差分の確認とtest_c1_09の固定行の試験）。
- test_c1_09：START＝bfbde7a、END＝None、REV＝END or "HEAD"。ファイルの読み取りはsc_helpers経由のGitだけで、`open`等は禁止語の監査の対象。既存試験4本の補正は、C-1自身の`git diff -U0`のハンクとして固定されている（変異17で検出、結果§8）。
- 鎖の確認：使い捨てのコミットでtest_c1_09のSTARTをb626c98に戻すと、test_sc_02の実鎖の試験3件（隙間なし、受領済みの順、開いた範囲は最後の1本）が失敗した。正しい3f780c1では34件合格。

### 4.7 P-02（C1-15）

v2_history_restoreはv2_history_adopt・v2_history_diagnoseをimportしない。C-1の差分が足した名前・文字列に"discarded"・"diagnosis"・"evidence"は無い（docstringの文章中の語だけ）。既存の`_replay_evidence`（bfbde7a以前からある名前で、B-4の試験がspyする）は例外として扱われている（結果§5の11）。依頼書C1-15の「evidence」は設計§4に無い語で、既存の名前と両立しない書き方だった。実装の扱い（新しい名前と文字列に適用し、既存の名前は改名しない）は依頼書§2（他の関数の振る舞いを変えない）に沿っている。

## 5. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| P-01 | 提案 | §4.5。検査器（v2_history/restore.py）は解放日でない日のCONSUMEを受け付け、計画だけが拒否する。これはD-2(ii)の設計どおりだが、境界を固定する試験が無い | 今は無い。C-2（公開値と照合）以降で「validate_historyを通った履歴＝照合済み」と扱う実装が入ると、Rocky指摘の分担が崩れても試験が気づかない | C-1は直さない。C-2の依頼書の受入条件に「公開値はCONFIRMED_IN_MEMORYの計画からだけ作り、検査器を通っただけの履歴（例：§4.5の履歴）からは作らない」と、§4.5の履歴を使う試験を入れる | §4.5の履歴から公開値を作ろうとして拒否されること |
| P-02 | 提案 | 結果文書と設計の記述の小さなずれ：(a) 結果§3の差分の行数は「+2137」だが、`git diff --shortstat bfbde7a 3f780c1`は**+2157**／−88。(b) 設計§3.3・依頼書§3は検査器で未知の処分名（小文字の"consume"を含む）が「restore_op_unsupportedのまま」と書くが、bfbde7aの検査器は元々restore_op_kindを返す。実装はこの従来の値を保ち、試験（test_the_lowercase_name_and_the_unknown_names_stay_what_they_were）で固定したが、結果§5の違いの表には無い。計画側（points.py）は従来どおりrestore_op_unsupported。(c) `restore_consume_input`（apply_transitionが次の状態を返さないとき）は設計§3.8の表に無い。CONSUMEの決定は必ずあるので到達しない防御で、試験も無い | 動作への影響なし。記録を読む人が、設計と実装の違いを見落とすおそれ | 受領記録に(a)〜(c)を注記する。設計を改訂する機会があれば、§3.3の一文を「検査器ではrestore_op_kind、計画ではrestore_op_unsupportedのまま」に直す | 記録の確認だけ |
| P-03 | 提案 | test_r4_09_scope.pyのtest_consume_is_only_a_refusalから、名前の現れるファイルを固定する`assertEqual(... ["build.py", "errors.py"])`が削除され、置き換えが無い（試行の差分も同じ削除） | 監査が少し弱まった（CONSUMEの名前が別のファイルに増えても、固定一覧の名前なら通る）。名前の一覧自体は固定のまま | 次にr4_09を触る機会に、ファイルの固定一覧（build.py、confirm.py、errors.py、market.py、points.py、records.py、values.py）を戻す。今回の受領の条件にしない | 名前を別のファイルに足す変異で失敗すること |

重大・通常は無い。

## 6. 推奨と次の作業

- **推奨：受領**（3f780c1を試験対象、de6549aを保存最終として受け取る）。限定修正の依頼は不要。
- 受領する場合の残り：実Windowsでの実行は未実施（依頼書§6の新規N＋1192件）。ユーザーPCで確認するなら、新規112件＋1192件＝1304件が目安。
- 次の段階：D-1の順序どおりC-2（公開値と照合）の依頼書を作る。そのとき(1) test_c1_09の`END = None`をde6549a（受領した最終）に1行で固定し、新しい範囲試験はSTART＝de6549aで書く、(2) P-01を受入条件に入れる、(3) 設計§4のP-02規則1〜4をC-2の受入条件にする。C-2〜C-4の実装は未承認のまま。
- 範囲外のまま残るもの：B-4§7.1の既知の制限（案a）、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02（git_show_at_endの本文）、U-03、U-07。

## 7. 作業記録

- 保護参照：開始時（2026-11-03T13:18Z）、依頼書§7の70参照＋docs/v2-consume-s3c-20261103（a6340c3）の71件を`git ls-remote`で照合し、全件一致。feat/v2-history-consume-c1-20261103はde6549a。push後の照合はスレッドの報告に記す。
- 変更したもの：本書と確認スクリプト（`docs/reviews/v2_consume_c1_review_20261103/`の7本）だけを、de6549aから作った新しい資料ブランチdocs/v2-consume-c1-review-20261103に追加した。製品コード・実装ブランチ・既存試験・設定の変更、PR、Actions、送信、新しい市場計算は0。プローブと変異は使い捨てのクローン・worktreeで実行し、pushしていない。
- 確認スクリプトはどれも、第1引数に3f780c1のクリーンクローンを渡して`python -B`で実行する（`c1_review_mutants.py`は第2引数に作業ディレクトリ）。リポジトリには何も書かない。
- モデル別の利用量は未計測。
