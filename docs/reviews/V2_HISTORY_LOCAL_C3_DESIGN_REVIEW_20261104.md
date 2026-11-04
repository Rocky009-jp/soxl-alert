# V2 C-3 v2ローカル正本 設計案・限定依頼書 レビュー結果

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
位置づけ：設計案と依頼書の初版（fd3c5bb）へのレビュー。**D-1〜D-9の採用でも、C-3の実装の承認でもない。** 採否はRockyさんが決める。

## 1. 対象と参照したもの

| 用途 | 固定版 |
|---|---|
| 対象 | docs/v2-history-local-c3-20261104 の **fd3c5bb5e63f532f3b7fbf9f3569e02f842cea50**（起点 d6b0332500af8d8d46ddaae6c7fda39ee38a03db） |
| 設計 | docs/specs/V2_HISTORY_LOCAL_C3_DESIGN_DRAFT.md（222行） |
| 依頼書 | docs/tasks/V2_HISTORY_LOCAL_C3_LIMITED_IMPLEMENTATION_REQUEST.md（199行） |
| 試行の差分 | docs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diff（SHA-256 c3db632d539fa1f15ac24da7e0f7d84062207194d9c2d5f3b8b626382840b070、設計§9の値と一致） |

読んだもの：上の3本、d6b0332 の v2_history_publish（__init__、check、read、values、errors）、v2_persistence/local（store、errors、fsops）、tests/v2_history_publish/c2_helpers.py、tests/v2_persistence_local/test_b06_kill.py と worker.py（子プロセスの止め方）、tests/v2_scope_chain/sc_helpers.py と test_sc_02_chain.py（範囲試験の見つけ方）、a6340c3 の §5.1〜§5.5、CLAUDE.md。取得できなかったファイルはない。

保護参照：依頼書§7の78参照を `git ls-remote` の完全SHAで照合し、78件とも一致した（2026-11-04、レビュー開始時と保存前）。

## 2. 結論

**重大0、通常1、提案7。N-01（通常）を依頼書・設計に数行足した第2版で、D-1〜D-9を一組で採用することを推奨する。** 第2版の確認は差分だけでよい。

確かめた範囲：

- 範囲（4操作、C-4・S4に残すもの）、S2との関係、rootの形、P-01の扱い、成否不明と照合は、a6340c3 §5.3の方針、C-2設計第2版、C-2実装レビュー a91a9ed の引継ぎと矛盾しない。S2を変えない方針、S2と同じ名前の write.lock による相互排他も、試行で両方向とも確かめた。
- C-2レビューの P-01（公開で返る history_invalid の意味）は、設計どおり解消している。正しい今に対して手作りの公開値 7,088 通りを試し、公開・初期化が history_invalid を返したのは 0 回だった。壊れた今では history_invalid が返った。
- ただし、同じ探索で、`mode`（初期化では `source` も）のキーが無い手作りの値が、固定のcodeの拒否ではなく生の KeyError で抜けることを見つけた（N-01）。
- 範囲試験の1行の固定（test_c2_09 の END＝d6b0332）は試行で通った。開いた範囲が0本になる形では test_sc_02 が2件失敗することも再現した（設計§6.1の記述どおり）。

## 3. 指摘

### 3.1 重大

なし。

### 3.2 通常

| ID | 根拠 | 内容と影響 | 修正案 | 確認方法 |
|---|---|---|---|---|
| N-01 | 試行 store.py の publish・initialize（`pub.mode != APPEND`、`pub.mode != CREATE or pub.source != GENESIS`）。values.py の `mode`・`source` は `_view["body"][…]` をそのまま返す。依頼書§3「公開値の受け取り」、C3-06 | 手作りの値（`_make`）で body に `mode`（初期化では `source` も）が無いと、C-3 が書き方を読む時点で **KeyError がそのまま外へ出る**。同じ値を check_publication に渡すと publication_invalid／shape になる。C-2では例外の漏れの探索が0件だった性質を、C-3が新しく崩す。ロックの前なので、ファイルとロックは残らない。作り手（publish_\*）の値では起きず、ランタイムは `_make` を使わない（D-7の監査）ので、運用で起きる道は無い。ただし P-01 の主旨は「手作りの値でも、決まったcodeで、今の破損と区別して返す」ことなので、ここも同じ扱いにそろえるべき | 依頼書§3「公開値の受け取り」に1文足す。「書き方・元は、形の誤りで例外が漏れない方法で読む。読めなければロックの前に store_publication_invalid（rule＝shape）」。実装は、`(KeyError, TypeError)` を捕まえて変換するか、`publication.summary()`（形が誤りなら publication_invalid／shape）から読む。C3-06 に「mode・source の無い手作りの値（`_make`）は固定のcodeで拒否し、ロックを取らない」を1項足す。`_make` を使う試験はC3-07の1ファイルだけという決まり（C3-15）にこの試験も入れるか、C3-15 の許可を「C3-07とこの1項」に広げる | docs/reviews/v2_history_local_c3_design_review_20261104/c3r_n01_repro.py（試行のツリーで3通りとも `LEAK KeyError`、check_publication は publication_invalid/shape）。修正後は3通りとも固定のcodeになること |

### 3.3 提案（必須ではない）

| ID | 内容 | 案 |
|---|---|---|
| P-01 | 設計§4.4の表では publication_invalid を「形・hashの誤り（作り手の値では起きない）」、store_candidate_invalid を「候補そのものが無効」としている。実際には、候補が無効な手作りの値は、どこで分かるかによって publication_invalid（rule＝records、candidate_digest）と store_candidate_invalid の両方になる（プローブでは、記録のhashを壊すと store_candidate_invalid、candidate_digest を書き換えると publication_invalid／candidate_digest）。肝心の「history_invalid は今の破損だけ」は守られている | 表の publication_invalid の行に「rule が records・candidate_digest のときは候補の誤り」と注記する。どちらも作り手の値では起きず、呼び出し側の扱いは同じ（作り直さず止める）と書く |
| P-02 | 設計§5.2は NOT_PUBLISHED のとき「同じ公開値でもう一度publishを呼んでよい」とする。replaceが失敗して一時ファイルを消せなかった場合（cleanup＝tmp_left）は、照合は NOT_PUBLISHED を返すが、次の publish は store_artifact_present で止まる（プローブで確認）。安全側に止まるので不具合ではない | §5.2 と §5.4 に「tmp_left が付いていた場合は、C-4の明示解錠まで再公開できない」と1文足す |
| P-03 | 設計§5.2は CONFLICT に「読めない今を含む」と書くが、これはバイトが壊れている場合の話で、history.json がリンク・ディレクトリ・読込みの失敗の場合は、照合は結果を返さず store_root_invalid／store_io_error で止まる（プローブで確認） | §5.2 に「ファイルとして読めないときは照合も store_\* で止まり、成否はまだ分からないまま」と書き、C3-11 に1項足す |
| P-04 | 複数の状態が重なったときの順序が文書に無い。試行では、型→書き方・元→書込み可否→（ロック）→v1→一時ファイル→history.jsonの有無の順だった（読取り専用のストアに CREATE を publish すると store_operation_unsupported が先） | 依頼書§3にこの順序を固定し、C3-08 の表の外の組合せ（v1＋一時ファイル、読取り専用＋書き方違い）を2〜3件試す。欠陥注入の判定がぶれないようにするため |
| P-05 | C3-15 は「v2_history_publish から import する名前が設計§2.3の一覧だけ」とするが、§2.3 は「書き方と元の固定語」と書くだけで、名前の一覧になっていない | 一覧を名前で固定する（試行では HistoryPublication、check_publication、reconcile_publication、history_bytes、read_history_bytes、APPEND、CREATE、GENESIS の8つ） |
| P-06 | 欠陥注入10（published の印を replace の後で立てる）は、replace の故障だけでは結果が変わらず、replace の故障と同時にロックの所有を失う（または解放に失敗する）組合せでだけ見分けられる（プローブで、元の形は store_commit_uncertain になることを確認） | C3-10 に「replaceの故障＋解放時の所有喪失→store_commit_uncertain」の組合せを1項足す |
| P-07 | 公開値は文字列にして子プロセスへ渡せない（from_dict が無い）。C3-13 の子プロセスが `_make` で作り直すと C3-15 に反する。また、Windows・macOS のように名前の大文字小文字を区別しないファイルシステムでは、`Snapshot.json` のような名前を v1 として見落とす（走査は名前の完全一致。Linuxのプローブでは見落とすことを確認、実Windowsは未確認） | 依頼書に「c3_worker は C-2 の作り手で、子プロセスの中で公開値を作る」と書く。大文字小文字は、設計§8の既知の制限に1行足す（S2も同じで、S2を変えないため） |

## 4. D-1〜D-9 の推奨

| ID | 推奨 | 理由 |
|---|---|---|
| D-1 範囲 | 採用 | a6340c3 §5.3 と一致。移行・採用・解錠をC-4に残す分け方は、C-3を「書く道を1つだけ持つストア」に絞れていて、レビューしやすい |
| D-2 S2との関係 | 採用 | FileOps だけを共有し、S2を変えない。手順は S2 の store.py とほぼ1行ずつ対応している（試行と比べて確認）。重複は受け入れてよい |
| D-3 rootの形 | 採用（P-04、P-07の注記つき） | S2と同じ名前のロックで、S2とC-3が互いに store_busy になることを両方向で確認した。S2 の読み手を v2 の root に向けると store_uninitialized になることも確認 |
| D-4 操作と拒否 | **N-01を入れた第2版で採用** | P-01 の区別は試行で成り立っている（手作りの値 7,088 通りで history_invalid は0回）。漏れは書き方を読む1か所だけ |
| D-5 成否不明と照合 | 採用（P-02、P-03の文言） | replaceの前後・dir_sync の失敗の分け方は S2 と同じ。照合が一時ファイルで止まらないことは、tmp_left の直後に答えを出すために要る |
| D-6 保存水準 | 採用 | S2と同じ。実Windows・電源断が未確認であることも明記されている |
| D-7 公開値の受け取り | 採用（N-01の1項を試験の許可に含める） | 型の確認をロックの前に置き、ランタイムが `_make` を使わないことを静的に監査する形で十分 |
| D-8 範囲試験 | 採用 | test_c2_09 の1行の固定で既存1930件が通ること、開いた範囲が0本だと test_sc_02 が2件失敗することを再現した。範囲試験は sc_helpers が tests/\*\*/test_\*.py から自動で見つけるので、既存の範囲試験を触る必要はない |
| D-9 担当 | 採用（Sonnet 5.5・high） | 手順は S2 の写しに近く、規則と試行の差分が具体的。N-01 と P-04〜P-07 を依頼書に入れれば、判断の余地はさらに小さくなる |

## 5. 実際に行った確認

一時ディレクトリに d6b0332 の作業ツリーを作り、試行の差分（5ファイル、+450／−1）を `git apply` でそのまま当て、pushしないローカルコミットにした。製品コードの変更ではない。

| 確認 | 結果 |
|---|---|
| 既存13スイート＋仮の範囲試験（Python 3.12.3、3.13.18、`-B -W error::ResourceWarning`、PYTHONDONTWRITEBYTECODE=1） | 両版とも 1930件合格（S2のskip 4はWindows専用）＋仮の範囲試験1件。ログ：trial_all_suites_py312_py313.log |
| 開いた範囲を消して END だけを固定した形 | test_sc_02 が2件失敗（test_two_open_ranges_are_rejected、test_an_open_range_that_is_not_last_is_rejected）、test_c2_09 は合格。設計§6.1の記述と一致 |
| 独立プローブ c3r_probe.py（32項目、3.12・3.13） | 27項目が期待どおり。5項目の「NG」はすべて N-01 の KeyError（各探索で1〜2件）で、history_invalid は0回。出力：c3r_probe_out_py312.txt、c3r_probe_out_py313.txt |
| 手作りの値の探索（body の各位置を15種の値と削除で置き換え、hashを書き直す） | DAILY 1,696、RESOLUTION 1,216、RESTART 816、RESTORE 2,640（publish）、GENESIS 720（initialize）。主な結果は store_candidate_invalid と publication_invalid。成功した値は、同じ値への置換（等価）と、d・request_id・plan_hash の付け替えだけ（後者は C-2§8 の既知の制限そのもので、D-7 の監査で防ぐ前提） |
| N-01 の再現 c3r_n01_repro.py | DAILY・GENESIS で mode を削除、GENESIS で source を削除の3通りとも、check_publication は publication_invalid/shape、ストアは KeyError。ロックは残らない |
| 保護参照 | 78件一致 |

実施していないもの：Python 3.10・3.11、Windows、unshareによる通信遮断、強制終了（SIGKILL）と8プロセスの競合の再現（設計§7の結果は読んだだけ）、試行の差分の全行の読み合わせ以外の欠陥注入。

## 6. 未解決事項と次の作業

- 採否はRockyさん。推奨は「N-01を入れた第2版（提案P-01〜P-07は任意）を作り、差分を確認してから D-1〜D-9 を一組で採用」。
- 範囲外として残るもの（設計§8の列挙どおり）：C-2実装レビューの P-02・P-03、C-1レビューの P-02・P-03、a6340c3 §5.5 の未決（C-4の依頼前）、実Windows・物理電源断・ユーザーPCでの確認。

## 7. 変更したもの

このレビュー文書と、確認に使ったスクリプト・出力（docs/reviews/v2_history_local_c3_design_review_20261104/）だけを、fd3c5bb から作った新しい資料ブランチ docs/v2-history-local-c3-review-20261104 に追加した。製品コード、設計・依頼書、ほかのブランチ、PR、Actions、送信は変えていない。モデル別の利用量は未計測。
