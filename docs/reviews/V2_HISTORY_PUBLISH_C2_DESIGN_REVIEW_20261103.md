# V2 C-2 公開値と照合 設計案・限定実装依頼書 レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。コーディネーター経由のRockyさんの依頼（「Opus・highに依頼して、終了後は推奨のとおり作業してください」）。作成者の結論に頼らず、D-1〜D-8、受入条件、欠陥注入、変更境界、§6.2の2行補正、保護参照を、コードと試行の再現で独立に確かめた。設計・依頼書・製品コード・既存試験は変更していない。

結論：**重大0・通常3・提案3。推奨は「依頼書（と設計の該当2か所）の限定改訂が先」。** 方式（D-1〜D-6）はそのまま採用してよい。通常の3件は、どれも受入条件・欠陥注入・形の規則の**文言**の問題で、方式を変えない。ただしR-01とR-02は、今の文言のままだと実装者が満たせない受入条件（C2-19、C2-12）を含み、依頼書§2の停止規則で実装が止まる。したがって「そのまま実装承認」ではなく、文言の改訂（第2版）の後にD-1〜D-8を一組で採用し、実装へ進むことを推奨する。改訂は文言だけなので、再レビューは不要と考える（改訂の差分の確認は改訂者が結果に書く）。
本レビューはC-2の実装承認、PR・マージ・本番反映、C-3・C-4への移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らして、公開値の書き手が「日次の定時処理1つ」と「人の保守操作」だけであるという設計§5.4の前提も確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 対象（資料ブランチ） | **9dd64b8eb07ad35dd23c011ed2dbb1196307f542**（docs/v2-history-publish-c2-20261103、親はde6549a） |
| 設計 | docs/specs/V2_HISTORY_PUBLISH_C2_DESIGN_DRAFT.md（blob 40da7cfa3e0327106a4d3ca2d0381814c17a5c24） |
| 依頼書 | docs/tasks/V2_HISTORY_PUBLISH_C2_LIMITED_IMPLEMENTATION_REQUEST.md（blob f8417a8befd93e397cb4f9990720088d86a10c41） |
| 試行差分 | docs/specs/V2_HISTORY_PUBLISH_C2_TRIAL_20261103.diff（blob d2be5de04158365e746fa60f8fd8bb9deb417c3e、sha256 7bfd3a80534c0e7fc3f2618db1894bd05883aed00c29449cc886cc219554b0ba＝設計§9の値と一致） |
| 起点 | de6549acb4ecea759cc771300fd0bef59dd5456a（C-1保存最終、受領済み） |
| 基準 | a6340c3（S3-C設計、D-1〜D-6採用済み）§4・§5、b473db4（C-1レビュー、§4.5とP-01〜P-03）、08072cc §6と9fe3e19 §4（範囲試験の規則） |

読んだもの：上の3文書の全文、a6340c3の§4・§5、de6549aのv2_history（values.py・validate.pyの鎖の検査）、v2_history_ops（values.pyの_Frozen、batch.pyのcheck_append_batch、plan.pyのconfirm_history_resolution_plan）、v2_history_adopt/confirm.py、v2_history_diagnose（raw_sha256の計算）、v2_persistence（codec.compute_event_hash、local/store.pyのsnapshotの読み方）、v2_history_restore/values.py、tests/v2_history_consume（c1_helpers、test_c1_09）、tests/v2_scope_chain（sc_helpers.judge_chain、test_sc_02）、C-1レビューの確認スクリプトc1_division.py、CLAUDE.md。取得できなかったファイルは無い。共有フォルダの設計・依頼書の写しは資料ブランチの版とバイト単位で同じ（試行差分の写しは共有フォルダに無い。提案ではなく記録として）。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 保護73参照＋資料ブランチ | **一致** | 2026-11-03T14:32Zに`git ls-remote`の完全SHAで、依頼書§7の表から独自に作った73件＋docs/v2-history-publish-c2-20261103（9dd64b8）の計74件がすべて一致。記録のpush後にも照合（§6） |
| 試行の再現（設計§7） | **再現した** | de6549aに試行差分を適用したworktreeで既存1780件が3.11.18・3.12.3・3.13.18で合格（§4.1） |
| §6.2の2行補正（D-7） | **妥当** | ENDの1行だけでtest_c1_09が1件失敗（(True, None)≠(True, de6549a…)）、HEADの自己読直しの1行を足すと112件合格を再現。この試験は「凍結後のREVの版には`END = None`と書かれている」ので、1行固定の規則とは構造的に両立しない。1行で直す案として最小（§4.2） |
| D-2：検査器だけ通った履歴が公開値にならないか（P-01） | **作り手の側では守られている** | C-1レビュー§4.5の履歴（検査器は受け付け、計画はrestore_consume_not_released）は、(a)正しい計画のbasisをその履歴に書き換えてhashを付け直した計画→history_plan_mismatch、(b)RestoreConfirmResult→history_plan_mismatch。ただしcheck_publicationは`_make`で作った値を受け付ける（設計§8の既知の制限どおり。提案P-01）（§4.3） |
| check_publication・reconcile_publicationの規則（D-4・D-5） | **妥当**（文言に2点の不足） | APPEND＝正規化digest＋先頭、REPLACE＝生バイトの識別値、CREATE＝無いこと（MIGRATIONはv1の識別値も）は、S2の読み方とB-5bの確認の段階4に合う。PUBLISHED_THEN_EXTENDEDの物理prefix判定は正しいが、記録のhashが鎖になっているため、正直な公開値では「最後の記録のhash」の判定と区別できない（R-02）。candidate_head_seqの下限が形の規則に無く、試行の照合は負の値でIndexErrorを漏らす（R-03）（§4.4、§4.5） |
| REPLACEの元バイト・CREATEとMIGRATIONのv1識別値 | **妥当** | confirm_prefix_adoptionはdiagnoseが`data`から計算したsha256・長さが計画と同じときだけCONFIRMED_IN_MEMORYを返すので、expectedを`data`から計算する規則（P-02の規則3・4の識別値）と矛盾しない。MIGRATIONをa6340c3 §5.2のREPLACE案からCREATE＋source_v1へ変えたのは、移行前にhistory.jsonが無いことと、a6340c3のD-4（§5は方針案）に合う。snapshotの読み方（UTF-8→decode_snapshot→validate_snapshot、rule＝utf8）はS2のlocal/store.pyと同じ |
| P-02の規則1〜4の割り振り（D-6） | **妥当** | 規則1〜3と規則4の識別値の部分をC-2の受入（C2-09、C2-15）に、規則4の退避の部分をC-4に。規則5はC-1で確認済み。C-2は`discarded`・`diagnosis_digest`を読まない（読むのは確認の関数の中だけ） |
| 受入C2-01〜C2-19 | **2件の文言の改訂が必要** | C2-19は書かれたとおりに行うと範囲の鎖の試験が2件失敗する（R-01）。C2-12の合成入力は有効な今では作れない（R-02）。C2-14は型の例しか挙げず、整数の境界を落とす（R-03）。件数（1780、Windows 1304）は計算どおり |
| 欠陥注入18項目 | **4項目に検出手段の指定が必要** | 3・4・5は実物の確認の関数の下では等価、15は正直な公開値では等価（R-02、提案P-02） |
| 変更境界（依頼書§2） | **十分** | 新パッケージ6ファイル（上限7）、新試験ディレクトリ、test_c1_09の2行、結果文書。既存の公開名・KINDS・B-2の型を固定。C-1のP-02・P-03、B-4§7.1、a5_09、git_show_at_endを範囲外にしている |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| R-01 | 通常 | 依頼書§4 C2-19、設計§6.3「次の段階の模擬」。tests/v2_scope_chain/test_sc_02_chain.pyのChainJudge.test_two_open_ranges_are_rejectedとtest_an_open_range_that_is_not_last_is_rejected（実際の表に開いた範囲が1本あることを前提に、もう1本を開いて「open range」の問題を期待する） | C2-19の手順（使い捨てのコミットでC-2の範囲試験のENDだけを固定し、新規の全試験と範囲の鎖が通ること）をそのまま行うと、開いた範囲が0本になり、test_sc_02の2件が「2 chain beginnings」で失敗する。実装者は依頼書§2の停止規則で止まるか、範囲外のtest_sc_02を直そうとする | C2-19と設計§6.3の模擬を「ENDを1行で固定し、**次の段階の仮の開いた範囲試験1本**（START＝C-2のEND、END=None、`class FilesChanged`を持つ最小のもの）を同じ使い捨てのコミットに足して、test_sc_\*・test_c1_\*・test_c2_\*が通る」に改める。実際の次の段階も自分の開いた範囲試験を同じコミットで足すので、これが正しい模擬。あわせて「自分の最終SHA」を明確にする：結果文書を書く前の**試験対象のSHA**で模擬し（範囲試験は結果文書を必須にしないので通る）、レビューで保存最終のSHAで再現する | `c2_review_next_stage_sim.sh`：開いたまま→全OK、ENDだけ固定→test_sc_\*がfailures=2、仮の開いた範囲を足す→全OK（3.12.3） |
| R-02 | 通常 | 依頼書§4 C2-12の括弧書き「候補の最後の記録と同じhashを持つ別のprefixを作る合成入力で確かめる」、§5の欠陥注入15。v2_history/validate.pyの_audit_chain（各記録のevent_hashはseqと親（復元はprev_hash）を含む記録全体のSHA-256で、直前の記録のevent_hashと一致することを検査）、v2_persistence/codec.compute_event_hash | reconcile_publicationは今を厳格に読んで完全に検査した後で判定する。有効な履歴では、位置n−1の記録のevent_hashが同じなら先頭n件は（SHA-256の衝突を除き）同じ記録で、history_dictも同じになる。したがって「同じhashを持つ別のprefix」は作れず、正直な公開値では変異15は等価になる。C2-12の必須の合成入力が作れないので、実装者は止まるか、等価として欠陥注入の感度を確かめないまま終わる | C2-12の括弧書きを「candidate_head_hashは今の位置n−1の記録と同じだがcandidate_digestが違う公開値（hashを付け直したもの）で、物理prefixのdigestを見ていることを確かめる（正しい実装はCONFLICT、変異15はPUBLISHED_THEN_EXTENDED）」に改める。欠陥注入15にも同じ検出手段を書き、「正直な公開値だけでは鎖のため等価」と注記する | `c2_review_m15.py`：試行のままではCONFLICT、変異15を当てたcheck.pyではPUBLISHED_THEN_EXTENDED（3.12.3） |
| R-03 | 通常 | 設計§5.2の手順1（形の検査に「各hashの形、書き方ごとの欄の形」とあり、candidate_head_seqの範囲が無い）、依頼書§4 C2-14（「None・数・真偽・空文字・list・dict等」の型の例だけ）、試行check.pyのreconcile_publication（`n = candidate_head_seq + 1`、`events[n - 1]`、`prefix_digest(events, n)`） | 試行は、hashを付け直してcandidate_head_seqを負にした公開値で、reconcile_publicationがIndexErrorを漏らす（−1・−5・−50・−10⁶。3つの書き方で、1,080通り中16件）。設計§7の「型の試し2,660通りで0件」は型だけを替えた試しで、値の範囲を見ていない。照合は「中身の問題で例外を出さない」（設計§5.3）が規則なので、試行を参考に書くと同じ漏れが入りやすい。正直な公開値では起きないので影響は限定的 | 設計§5.2の手順1に「candidate_head_seqは0以上。APPENDではexpected.head_seq＋len(records)、CREATE・REPLACEではcandidate_historyの記録数−1と同じ」を加える（違えば`publication_invalid`／shape）。C2-14に「整数の欄（candidate_head_seq、expected.head_seq、raw_size、recordsのseq）の負・0・境界・巨大な値」を明記する | `c2_review_int_bounds.py`：runs 1080、leaks 16（3.11・3.12・3.13で同じ）（すべてreconcile、candidate_head_seq≤−1）。checkは同じ入力をすべてpublication_invalidで拒否 |
| P-01 | 提案 | 設計§8の既知の制限、§3.1(3)。`c2_review_probe_p01.py`の(c) | `HistoryPublication._make`で作った値は、C-1レビュー§4.5の履歴（計画は拒否）を候補にしてもcheck_publicationを通る（形とhashと今が合えば受け付ける。計画を確認し直さない規則どおり）。P-01の境界は「作り手が確認を自分で実行し、`_make`を呼ぶのはbuild.pyだけ」で守られ、check_publicationは確認ではない | この性質を特性の試験として1件固定する（「check_publicationは`_make`で作った値を受け付ける。だから`_make`はbuild.pyだけ」）。C-3の依頼書に「C-3は同じプロセスでpublish_\*が返した値だけを受け取り、C-3の範囲試験でv2_history_publish/build.py以外が`_make`・`object.__new__(HistoryPublication)`を呼ばないことを監査する」を受入として引き継ぐ | プローブ(c)：OK True（候補が問題の履歴と同じ） |
| P-02 | 提案 | 依頼書§5の欠陥注入3・4・5。build.pyの試行、check_append_batch（候補のdigestをbatchの値と比べる）、confirm_history_resolution_plan（batchは自分の候補から作る）、confirm_prefix_adoptionの段階4（diagnoseが`data`から計算したraw_sha256・raw_sizeが計画と同じときだけCONFIRMED_IN_MEMORY） | 3（延長の確認を外す）、4（確認結果のhistoryとの一致を外す）、5（expectedを計画のbasisから写す）は、実物の確認の関数の下ではどの入力でも結果が同じになる（防御の重ね）。何も指定しないと「等価」で終わり、防御が効いていることを誰も確かめない | 3・4・5について「確認の関数をbuildモジュールの名前空間で差し替える代役（C-1の変異7と同じやり方）で検出する。代役を使わない場合は、上の理由で等価と書く」と依頼書に明記する | コードの読解（実測はしていない） |
| P-03 | 提案 | 設計§5.2（「移行以外の公開値にsource_v1を渡したらpublication_invalid／source_v1」を手順2の末尾に置く）、依頼書C2-11（「公開値の誤りは今より先」）、試行check.py | 試行は、APPENDの公開値に今が古い状態でsource_v1を渡すと、引数の誤用（publication_invalid／source_v1）より先にpublication_stale／headを返す。C2-11の「公開値の誤りは今より先」をこの規則にも当てる試験を書くと、試行どおりの実装は失敗する。また、MIGRATIONでsource_v1が`bytes`でない場合は／source_v1（stale）で、current_typeと扱いが違う | 引数の誤用（currentの型、書き方とsource_v1の有無・型）を手順1の最後にまとめ、今の比較より先に見る、と設計§5.2に1行書く | 試行check.pyの読解 |

C-4への引継ぎ（指摘ではなく記録）：採用のREPLACEがreplaceの後で中断すると、元バイトはhistory.jsonから消えている。照合に要る公開値は、C-4がquarantineへ写した元バイトからpublish_adoptionで作り直す（今のバイトでの確認はNO_CHANGE＝publication_refused／no_changeになり、これがP-02の規則3の「すでに候補である」に当たる）。a6340c3 §5.4の順序（退避先へ写してfsyncしてからreplace）がこれを可能にしているので、C-4の依頼書でこの手順を受入にする。

## 4. 実行した確認

### 4.1 試行の再現

使い捨てのworktree（de6549a、`git apply`で試行差分を適用してローカルコミット2ea0d6f、pushしない）で、`unshare -n -r <python> -B -W error::ResourceWarning -m unittest discover`、`PYTHONDONTWRITEBYTECODE=1`。ランナーはC-1レビューのrunall.shにv2_history_publishを足したもの（`runall.sh`）。

| スイート | 件数 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---:|---|---|---|
| v2_core | 197 | OK | OK | OK |
| v2_persistence | 170 | OK | OK | OK |
| v2_persistence_local | 113 | OK（skip 4） | OK（skip 4） | OK（skip 4） |
| v2_recovery | 176 | OK | OK | OK |
| v2_history | 230 | OK | OK | OK |
| v2_history_ops | 173 | OK | OK | OK |
| v2_history_restart | 109 | OK | OK | OK |
| v2_history_restore | 165 | OK | OK | OK |
| v2_history_diagnose | 131 | OK | OK | OK |
| v2_history_adopt | 170 | OK | OK | OK |
| v2_scope_chain | 34 | OK | OK | OK |
| v2_history_consume（test_c1_09の2行補正を含む） | 112 | OK | OK | OK |
| 合計 | **1780** | 1776合格＋4 skip | 1776合格＋4 skip | 1776合格＋4 skip |

試行の仮の範囲試験（1件）も合格。Python 3.10とWindowsは未実施（この環境に3.10が無い。試行の位置づけの確認なので、実装の受入で4版を行う）。

### 4.2 §6.2の2行補正（`c2_review_s62.sh`）

| 版 | test_c1_\*（112件） |
|---|---|
| ENDの1行だけ固定 | FAILED（failures=1）。Chain.test_the_range_values_of_this_file_are_those_read_from_the_textで`(True, None) != (True, 'de6549a…')` |
| ＋自己読直しを`C.show("HEAD", …)`に | OK |
| de6549aからの差分 | test_c1_09の2行（+2／−2）だけ。試行差分のハンクと同じ文字 |

判断：この試験は「REVの版のファイルに書かれたEND」と実行中のENDを比べるので、ENDを固定すると必ず失敗する（固定前のREVの版には`END = None`しか書けない）。範囲試験の固定（08072cc）の「次の段階は1行」という規則に、C-1の試験が合っていなかった。HEADを読むのは作業ツリーを読まない規則に反しない。ほかの試験はREV（＝de6549a）を読んだままで、C-1の範囲の監査は変わらない。2行目は規則の例外として妥当で、C-2の範囲試験が最初から自己読直しをHEADにする（設計§6.3）ので、同じ例外は次の段階で繰り返さない。ただし、R-01のとおり、C-2の範囲試験の次の段階の模擬は「仮の開いた範囲を足す」形でないと鎖の試験が通らない。

### 4.3 P-01の経路（`c2_review_probe_p01.py`）

| 入力 | 結果 |
|---|---|
| 問題の履歴の計画（REPLAY 2、REAPPLY 3、CONSUME D5、check D7） | restore_invalid／restore_consume_not_released |
| 同じ履歴を検査器へ | 受け付ける（head 7） |
| 同じ基点でREADYの計画（DROP 2、CONSUME D2、CONSUME D3、REAPPLY 3）→publish_restore | APPENDの公開値 |
| (a) その計画のbasisの候補の欄を問題の履歴に書き換え、hashを付け直した計画 | history_plan_mismatch |
| (b) RestoreConfirmResult(CONFIRMED_IN_MEMORY, 問題の履歴, …)を計画の代わりに | history_plan_mismatch |
| (c) 問題の履歴を候補にした本文から`HistoryPublication._make`で作った値→check_publication | **受け付ける**（返る候補が問題の履歴と同じ）。設計§8の既知の制限どおり。提案P-01 |

`_Frozen`に`from_dict`が無いこと（コンストラクタはTypeError）もコードで確かめた。

### 4.4 照合の物理prefix判定（`c2_review_m15.py`）

基点の履歴を候補とする公開値（hashを付け直したもの）と、それを先頭に持つ長い今（復元の候補）で比べた。candidate_digestが正しいとPUBLISHED_THEN_EXTENDED、candidate_digestだけを変えるとCONFLICT。check.pyの判定から`prefix_digest(...) == candidate_digest`を外した変異15では、後者もPUBLISHED_THEN_EXTENDEDになり、検出できる。有効な今では記録のhashが鎖になっているので、正直な公開値だけでは区別できない（R-02）。

### 4.5 整数の境界（`c2_review_int_bounds.py`）

APPEND（復元の公開値）、CREATE（GENESIS）、REPLACE（形だけの採用）の整数の欄（candidate_head_seq、expected.head_seq、recordsのseq、candidate_historyのhead_seq・先頭のseq、expected.raw_size）を−10⁶〜2⁷⁰の12値に替え、hashを付け直し、今を5種（基点、候補、無い、壊れたUTF-8、壊れたバイト）にして、check・reconcileを呼んだ。1,080通りで想定外の例外は16件で、すべてreconcile_publicationのcandidate_head_seq≤−1（`events[n-1]`または`history_dict([])`のIndexError）。checkは同じ入力をpublication_invalid（candidate_digest）で拒否した（R-03）。

### 4.6 次の段階の模擬（`c2_review_next_stage_sim.sh`）

| 版 | test_sc_\* | test_c1_\* | test_c2_\*（仮） |
|---|---|---|---|
| C-2の範囲が開いたまま | OK | OK | OK |
| C-2の範囲試験のENDだけを固定（1行） | **FAILED（failures=2）** | OK | OK |
| ＋次の段階の仮の開いた範囲試験1本 | OK | OK | OK |

失敗した2件はtest_sc_02のChainJudge（開いた範囲をもう1本作って「open range」の問題を期待する）。開いた範囲が0本の表では「2 chain beginnings」になる（R-01）。

### 4.7 その他の照合

- 件数：既存1780＝197＋170＋113＋176＋230＋173＋109＋165＋131＋170＋34＋112。Windowsの1304＝112＋34＋170＋131＋165＋109＋173＋176＋230＋4。どちらも依頼書どおり。
- 依頼書§7の表は73行で、資料ブランチを足して74参照。

## 5. D-1〜D-8の採否の推奨

| ID | 推奨 | 理由 |
|---|---|---|
| D-1 C-2の範囲 | **採用** | 純粋関数だけで、C-3のファイル操作と切り離して試験できる。既存パッケージ不変 |
| D-2 作り方とP-01 | **採用** | (a)(b)の経路は確認で拒否され、Historyや確認結果を受け取る関数が無い。check_publicationが確認でないことはP-01の特性の試験とC-3への引継ぎで明示する |
| D-3 公開値の形 | **採用** | 3つの書き方×7つの元。GENESISの追加とMIGRATIONのCREATE化は、a6340c3のD-4の範囲内で、C-3の初期化と移行前の状態に合う |
| D-4 バイトの形と読み方 | **採用** | S2の読み方・B-5aの診断・B-5bの確認と一貫する。正規化されていない有効なテキストを受け付ける理由も妥当 |
| D-5 照合 | **採用** | 4つの結果、読めない今はCONFLICT、REPLACEの「元のまま」を先に、誰が書いたかを示さない。物理prefix判定は正しい（R-02は受入の文言だけ） |
| D-6 P-02の規則1〜4 | **採用** | 割り振りが妥当（§2） |
| D-7 範囲試験 | **採用（R-01の改訂を含めて）** | 2行補正は必要かつ最小。次の段階の模擬は「仮の開いた範囲を足す」形に改める |
| D-8 実装単位と担当 | **採用（第2版の依頼書で）** | 変更境界は十分。R-01〜R-03を反映した依頼書で、Sonnet 5.5・highが止まらずに進められる |

**判断：そのまま実装承認ではなく、依頼書の限定改訂が先。** 改訂の範囲：設計§5.2手順1（R-03の下限、P-03の順序）・§6.3（R-01の模擬）、依頼書§4のC2-12（R-02）・C2-14（R-03）・C2-19（R-01）・C2-10か新しい項目（P-01の特性の試験）、§5の3・4・5・15（P-02、R-02）。方式・パッケージ・変更境界・件数は変えない。改訂後にD-1〜D-8を一組で採用し、C-2の限定実装へ進むことを推奨する。

## 6. 作業記録

- 開始時（2026-11-03T14:32Z）に74参照（依頼書§7の73＋資料ブランチ9dd64b8）を`git ls-remote`の完全SHAで照合し、すべて一致。記録のpush後の照合は報告に記す。
- 本記録と確認スクリプトだけを、9dd64b8から作った新しい資料ブランチdocs/v2-history-publish-c2-review-20261103に追加した。設計・依頼書・試行差分・製品コード・既存試験は変更していない。PR・Actions・送信・新しい市場計算は0。使い捨てのworktreeとローカルコミットはpushしていない。
- 確認スクリプト（docs/reviews/v2_history_publish_c2_review_20261103/）：`runall.sh`、`c2_review_s62.sh`、`c2_review_next_stage_sim.sh`、`c2_review_probe_p01.py`、`c2_review_m15.py`、`c2_review_int_bounds.py`。どれも読取り専用で、試行差分を適用した使い捨てのツリーで動かす。
- モデル別の利用量は未計測。
