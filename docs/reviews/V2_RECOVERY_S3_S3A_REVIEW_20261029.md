# V2 S3 復旧設計案・S3-A限定実装依頼書 レビュー結果

作成日：2026-10-29  
レビュー担当：Claude（読み取りレビューのみ。コード変更・試験実行・PR作成なし）  
採否：Rockyさんが判断する。本書の推奨は採用・実装承認を意味しない。両文書は「レビュー待ち・実装未承認」のまま扱う。  
リポジトリへ保存する場合のパス案：`docs/reviews/V2_RECOVERY_S3_S3A_REVIEW_20261029.md`

---

## 1. 対象と参照したファイル

| 区分 | 内容 |
|---|---|
| 開始SHA（レビュー対象） | `8b79f97c551bda1af07fe08063d36e1d22c49659`（branch `docs/v2-recovery-s3-20261029`） |
| 対象文書とblob | `docs/specs/V2_RECOVERY_S3_DESIGN_DRAFT.md`（以下「設計」、blob `c42e2d78d3257196805f13f18f9002faab2908fe`）、`docs/tasks/V2_RECOVERY_S3A_RESOLUTION_REQUEST.md`（以下「依頼」、blob `2c4d1df3318d512e4fa7d2fc9bd76060decf5aec`） |
| 差分の確認 | `d404d4d..8b79f97` は受領記録2本（1b5b8ce、aa21dbe）と今回の新規2文書のみ。今回の3コミット 9ef169d、4a04827、8b79f97 は2文書だけを追加・修正。コード差分0 |
| 突き合わせたコード | `d404d4d` の `v2_core/observations.py`、`sessions.py`、`engine.py`、`transition.py`、`v2_persistence/events.py`、`runner.py`、`plan.py`、`codec.py`、`recompute.py`、`store.py`、`local/store.py`（シグネチャ） |
| 上位設計 | `e3e9094` の §2.2、§2.6〜2.8、§4.2〜4.3、§6のK-11〜K-14・X-14〜X-17d、§8 U-03 |
| S1契約 | `425df80` の S1設計（§S3留保、ACK・補完はS3へ、reconcileの親hash） |
| 既存試験数 | `def test` の数で 197（v2_core）／170（v2_persistence）／113（v2_persistence_local）。依頼C-01の件数と一致 |

保護参照（`git ls-remote`、レビュー時）：依頼§6の19参照はすべて完全SHAが一致。資料ブランチ `docs/v2-recovery-s3-20261029` の先頭は `8b79f97`。

## 2. 結論

**重大0・通常4・提案7。** S3をA／B／Cに分け、Aを「S1・S2を変えないメモリ上の純粋関数」に限る構成は、上位第4版の§2.7（検証→除外→補完→最終検査）、I-15（ACK・宣言は市場状態を変えない）、X-14〜X-17d、S1の「ACK・補完はS3へ留保」と整合しています。ROW_REMOVED補完の順序、CHANGEDの元行併存で補わないこと、LATEにapplied_refを求めないこと、next(D)のclose_at／confirmedを通常の投影から外すこと（S1のN-02）も正しく引き継がれています。依頼§6の19参照は実際のリモートと一致しました。

通常4件はいずれも§4の指示の受入条件に関するものです。うち2件（N-02、N-03）は、上位設計が許す、または禁じている操作と食い違うので、**N-01〜N-04を文書で直す（またはRockyさんが方針を決める）まで実装依頼へ進めないことを推奨します。** 修正は各数行で、S3-Aの範囲を広げる必要はありません。

## 3. 指摘表

### 通常

| ID | 根拠 | 内容と影響 | 修正案 | 確認方法 |
|---|---|---|---|---|
| **N-01** prepare_resolved_dayの計画が、そのまま実ファイルの正本へcommitできる | 設計§2「AのResolutionSetはメモリ上の検証用データ」、§3「S1 PrepareResultを返す。ストアへcommitしない」、依頼C-12「planが一致」。コード：`runner.py` の prepare_day は `AppendPlan` を返し、`local/store.py:105-106` の `LocalFileStore.commit` は `isinstance(plan, AppendPlan)` だけで受け付ける。上位§2.7手順7は、除外・補完を使ったAPPLYに `exclusions_applied`／`supplemented` を書くとするが、S1のAPPLYにはその項目が無い | 解決記録を使って作った PREPARED の計画は、S1と同じ `AppendPlan` なので、呼出側が S2 の `commit` に渡せば正本に入る。入った後は、そのAPPLYの根拠になったResolutionSetがどこにも保存されておらず（Aは保存しない）、APPLYにも除外・補完の跡が残らない。次に通常のS1 prepare_dayを動かすと、除外した行が元の台帳に残っているため `late_observation`／`decision_conflict` 等で止まり、解除にはS3-Bの保存形式が要る。設計の「Aでは保存しない」は、ResolutionSetについてだけ守られ、S1正本については守られない | 次のどちらかを設計§3と依頼§3.9に明記する。(推奨) prepare_resolved_dayは `AppendPlan` を外へ出さず、S3-A専用の結果型（status、core_result、計画イベントの正規化テキストとevent_hash、`committable=False`）を返す。C-12の「計画一致」はイベントの正規化テキストで比べる。(代替) `AppendPlan` を返すが、「S3-Bの保存形式ができるまで、解決記録を使った計画を正本へcommitしない」を契約として書き、結果文書の保留に残す | C-12またはC-14に追加：解決記録を使ったPREPAREDの戻り値が `AppendPlan` でない（推奨案）、または `MemoryStore.commit`／`LocalFileStore.commit` が型で拒否する。空のSetのときS1と同じ計画テキストになること |
| **N-02** 「元行の削除＋別IDでの打ち直し」をACKで解決できない | 設計§4のACK/ADDED「保存decisionと同じ指紋の行が今回台帳に残っていること」、§4冒頭「新規指示の証拠は今回の台帳から確認」、依頼C-03「元行が無い場合…は拒否」。上位§2.7・R-6はADDEDに元行の存在を求めていない | 消費済みDの行A（record_id `a`）を台帳から消し、同じDに別IDの行B（record_id `b`）を書き直した場合、解決にはROW_REMOVED（Aを補う）とADDED（Bを除く）の両方が要る。ところがADDEDの証拠検査は**生の台帳**にAが残っていることを求めるので、同じバッチにROW_REMOVEDがあっても拒否される。CHANGED（元行なし）＋ADDEDも同じ。この食い違いは、台帳を元に戻す以外に先へ進めなくなる。行を打ち直す操作は手作業の台帳では起こりやすい | ADDEDの証拠を「保存decisionと同じ指紋の行が今回台帳にある、**または** 同じ`applied_ref`のROW_REMOVED／元行なしCHANGEDが既存Setか同じバッチにある」に改める。元行が消えたことの確認はROW_REMOVED／CHANGEDに任せ、最後は§5手順6（補完後の最終検査）で保存decisionがちょうど1件あることを確かめる。依頼C-03の「元行が無い場合は拒否」は「元行が無く、ROW_REMOVED／CHANGEDも無い場合は拒否」に直す | C-03／C-05に追加：A削除＋B追加を {ROW_REMOVED, ADDED} の1バッチで解決し、Aが1件補われBが除外される。ADDED単独では拒否。欠陥注入に「ADDEDの証拠を生台帳だけで判定」を加える |
| **N-03** 除外によって、同じrecord_idの複数版から1つを選ぶことができてしまう（U-03の迂回） | 上位§2.7末尾「どちらかを除外すればコアは通るが、どちらを使うかを選ぶことは訂正に当たる（U-03）」。設計§4「未処理decisionの版の選択（CORRECTION／U-03）は作らない」「同じrecord_idの未処理2版から1つだけ選ばない」。設計§5手順2は衝突を最終集合まで持ち越す。コア `observations.py` の `_parse_all` は、同じrecord_idの版が**両方残っているときだけ** `record_id_conflict` を出す | 例：record_id `x` の版1が未処理のDを対象（Dの窓内）、版2が次のセッションEを対象（Eの窓内）。生の台帳では `record_id_conflict`。ここでDをDECLARE_MISSINGすると、§4の規則で名指しするのは「D対象／D窓内」の版1だけで、版2はE側にあるので名指しの対象外。除外後は版2だけが残って衝突が消え、`prepare_resolved_day(E)` は版2でEを消費する。結果として版2を採用したことになり、U-03で作らないとした「版の選択」を欠測宣言で行えてしまう。LATE（版1がスキップ済みDを対象）やADDED（別IDの行に別の版がある）でも同じ形が作れる | §4に共通規則を1つ足す：「除外する指紋のrecord_idに、生の台帳上で別の指紋の版があり、その版が最終集合に残る場合は拒否（rule=`version_selection`）。ただし残る版が有効なS1 APPLYの固定decisionと同じ指紋のとき（CHANGEDの元行併存）は許す」。DECLARE_MISSINGで両方を外したいときは、宣言とあわせて残りの版も同じバッチで名指しさせるか、台帳を直すよう案内する（上位§2.7の推奨どおり） | C-07／C-13に追加：上の例でDECLARE(D)が `version_selection` で拒否される。CHANGEDの元行併存（X-16）は引き続き通る。欠陥注入に「版の残存を検査しない」を加える |
| **N-04** 欠測宣言で、衝突していない有効なdecisionも除外できる | 設計§4 DECLARE_MISSING「今回のD対象／D窓内のobserved/decisionすべての異なる指紋を名指し（0件なら空）」。上位R-3「**衝突が解消できない**セッションDを欠測と宣言する」、E-15。上位E-13の「まとめて欠測と宣言」は追いつき上限（U-06）とセットで、S3-Aには無い | 今の文言では、Dに有効なdecisionが1件だけ（衝突なし・窓内・形式正しい）ある場合でも、その1件を名指しすればDECLAREが通り、Dは欠測になる。欠測にすると次のAPPLYで `gap` によりarmed・streak・前日normal_rawが不明／0へ戻るので、**市場判定の結果が変わる**。これは観測値を採用しないという訂正（U-03）に近い操作で、S3-Aの目的（衝突で止まった入力を明示的に外す）を超える | Rockyさんの判断事項として、次のどちらかを設計§4に明記する。(推奨) S3-Aでは、宣言しないとコアが `decision_conflict`／`record_id_conflict`／`target_mismatch`／`decision_outside_window` で止まるD、またはdecisionが0件のDに限る。有効なdecisionが1件だけのDは拒否（rule=`declare_valid_decision`）。(代替) 有効な1件の除外も許すが、その場合は市場判定を変える操作であることを設計に書き、計画表示に「有効な観測を除外」と出す | C-07に追加：有効な1件だけのDへの宣言が拒否される（推奨案）。0件の宣言と、衝突2件の宣言は通る |

### 提案

| ID | 根拠 | 内容 | 修正案 |
|---|---|---|---|
| P-01 | 設計§3.1 request_hash、§7「同じrequest_idで異内容は拒否、同内容はNO_CHANGE」 | request_hashに `requested_at` が入っているため、同じ依頼を同じ指示で出し直すときに呼出側が新しい時刻を注入すると、内容が同じでも `resolution_request_conflict` になる。再実行で冪等にしたい意図と合わない | (a) request_hashから `requested_at` を外し、記録には残す。または (b)「再試行では最初のrequested_atを再利用する」と呼出側の契約に書き、C-10に「時刻だけ違う再提出」の期待結果を固定する。(a)を推奨 |
| P-02 | 上位§2.7の表「DECLARE_MISSING／ACKは…それを見た台帳の版…を持つ」、設計§6 ledger_digest | 台帳の版を示す `ledger_digest` は計画のbasisにだけあり、確認後に残る解決記録には入らない。Aの計画は捨てられるので、どの台帳を見て除外を決めたかが記録から追えない | 各記録の `request_basis` か記録本体に `ledger_digest`（6列正規化のハッシュのみ。生の行は入れない）を持たせる。S3-Bで形式が変わるとしても、Aの時点で上位の項目に合わせておくと写像が簡単になる |
| P-03 | 設計§4「frontierは作成時prefixの最新APPLY日と、その時点までのDECLARE_MISSING日の遅い方」「複数日の宣言は直後から1日ずつ明示」 | 1つのバッチでD、次のD'を続けて宣言する場合、2件目のfrontierに同じバッチの1件目を数えるかが書かれていない。数えなければ2日連続の宣言は2回の計画に分ける必要がある | 「同じバッチ内でも、resolution_seqが小さい宣言は後の記録のfrontierに数える」と明記し、C-07に2日連続を1バッチで宣言するケースを入れる（逆順の指示は `declare_frontier` で拒否） |
| P-04 | 設計§3「check_dは…confirmed=true、次セッションが必要」 | check_dの許される範囲（最新APPLY日との前後、指示の対象Dとの関係）が書かれていない。ACKだけを確認したいときに、最新の適用済みDをcheck_dにできるか（S1ではALREADY_APPLIEDの経路）も読み取れない | 「check_d > GENESIS.start_after、かつ check_d ≥ 最新APPLY日（等しいときはS1の再実行経路）。DECLAREの対象Dは check_d 以下」のように、S1 prepare_dayと同じ条件をresolve_observations・prepare_resolution_planにも書く |
| P-05 | 設計§7.1 エラー表 | 宣言の名指し不足（D対象の行を一部しか名指ししない）、宣言対象やcontextのセッションが未確定、LATEのmissing_refの不正、N-03の版の選択に対応するruleが表に無い | rule名を追加：`declare_incomplete`、`declare_unconfirmed`、`late_missing_ref`、`version_selection`（N-03）、`declare_valid_decision`（N-04を推奨案で採る場合）。依頼の欠陥注入の一覧にもN-02〜N-04の3件を加える |
| P-06 | 上位§2.8「境界以前のdecision行…解析と衝突の検査は受ける」、設計§4（ACKはAPPLY、LATEは欠測参照、宣言はfrontier直後に限定） | GENESIS.start_after以前の日の行や、どのAPPLY・スキップ・宣言にも属さない日の `record_id_conflict` は、S3-Aのどの指示でも外せない。これは正しい停止（台帳を直す）だが、実装担当が範囲を広げて対応しようとする余地がある | 設計§4に「APPLY・スキップ・宣言のどれにも属さない日の衝突はS3-Aでは解決できず、台帳の修正で直す」と1行書き、C-02に期待どおり止まる試験を1件入れる |
| P-07 | 設計§3.1 source_head prefixの検査 | 記録ごとに「作成時prefixをS1で検査」を素直に実装すると、記録数×イベント数の全再計算になる。今の規模では問題にならないが、S3-Bで履歴が伸びると重くなる | 結果文書の任意事項として、`validate_snapshot` を1回だけ実行し、各APPLYの `state_after` とイベントhashからprefixの状態を引く方式でよいと書いておく（検査の意味は同じ） |

### 保留として記録を勧めるもの（指摘ではない）

- 宣言済みDに後から通常のS1でAPPLYが入った場合、ResolutionSetは `validate_resolutions` で恒久的に不正になる（設計どおり）。S3-Aでは解決記録が保存されないので実害はないが、S3-Bで保存形式を決める際に、宣言を取り消す操作が要るかを決める必要がある。
- 上位§2.7手順6は「decision行」と書き、not_checkedのdecision行も含むように読める。S1・S3-Aは observed のdecisionだけを数える。コアの選択と合っているので今回の指摘にはしないが、S3-Bで上位設計の文言を揃えるとよい。
- 依頼§6の保護参照に資料ブランチ自身（`docs/v2-recovery-s3-20261029` → `8b79f97`）は入っていない（自己参照になるため）。実装開始時に、渡されたSHAと上記blob SHAを結果文書へ記録する手順（依頼§1）で足りる。

## 4. 実施した確認

| 確認 | 結果 |
|---|---|
| 2文書の全文と、8b79f97での差分（request_basis追加、applied_ref／missing_refのseq上限） | 読了。差分は設計§3.1の2行の追記のみ |
| 上位第4版 §2.2・§2.6〜2.8・§4.2〜4.3・K-11〜K-14・X-14〜X-17d・U-03 | 設計§3〜§5の順序と参照（LATEはmissing_ref、ADDED/CHANGED/ROW_REMOVEDはapplied_ref、I-15）は一致。N-02・N-03・N-04は上位との差 |
| S1 425df80 の S3への留保事項 | 「ACK→除外→補完→最終検査はS3へ」「IB-04は現在状態を作ったAPPLYの親」を維持していることを確認 |
| コアの選択・指紋の挙動（observations.py、runner.py、recompute.py） | fingerprintはrecord_id・状態・役割・値・UTC時刻・対象日から作られ、表記の違い（"40"と40、時差表記）は同じ指紋になる。`_parse_all` は全行の同ID別内容を衝突とする。S1 prepare_dayは適用済みD・スキップ済みD・間のセッションを `select_decision` で検査する。N-03はこの挙動から導いた推論で、実行による再現はしていない |
| 欠測後のstreak（設計§5の「F&G≥30ならstreak=1」） | `transition.py` の gap 処理（armed・前日normal_raw不明、streak=0の後に当日分を加算）と一致 |
| S2 commitの受付条件 | `LocalFileStore.commit` と `MemoryStore.commit` は `AppendPlan` 型だけで受け付ける（N-01の根拠） |
| 既存試験数 | 197／170／113（依頼C-01、設計§1と一致） |
| 保護参照19件 | `git ls-remote` で全件一致 |

実施していないこと：コード変更、試験の実行、新しい市場計算、PR・Actions・外部送信。N-01〜N-04はコードと文書の読み取りによる指摘で、S3-Aのコードは存在しないため実行での再現はしていない。

## 5. 次の手順の案（未採用）

1. 主担当がN-01〜N-04を設計§3〜§5・§7.1と依頼§3・§4へ反映（N-04はRockyさんの方針を先に決める）。提案は任意。
2. 改訂版を再レビュー（N-01〜N-04の反映確認を最初に行う）。
3. Rockyさんが「S3-Aだけ、既存コード不変、C-01〜C-14、Sonnet 5.5・high」の一組を採用するか判断。
