# V2 C-4 保守操作（移行・採用・明示解錠） 設計案・限定依頼書 レビュー結果

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
位置づけ：設計案と依頼書の初版（ce4fd28）へのレビュー。**D-1〜D-9の採用でも、C-4の実装の承認でもない。** 採否はRockyさんが決める。

## 1. 対象と参照したもの

| 用途 | 固定版 |
|---|---|
| 対象 | docs/v2-history-maintain-c4-20261104 の **ce4fd281c5a1b261d99ebbacb85015437a2deed6**（起点 6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a） |
| 設計 | docs/specs/V2_HISTORY_MAINTAIN_C4_DESIGN_DRAFT.md（421行） |
| 依頼書 | docs/tasks/V2_HISTORY_MAINTAIN_C4_LIMITED_IMPLEMENTATION_REQUEST.md（314行） |
| 試行の差分 | docs/specs/V2_HISTORY_MAINTAIN_C4_TRIAL_20261104.diff（SHA-256 fa9a60e2e24a6af5ecaf742ca2308918231c78c8e0ab49abb988875d31a58e69、設計§9の値と一致） |

読んだもの：上の3本、試行の差分を当てた v2_history_maintain（__init__、ops、values、store の全1016行）、6d69bd7 の v2_history_local/store.py、v2_persistence/local（fsops、errors、store のロックの語）、v2_history_publish（build.py、check.py）、v2_history/migrate.py（prepare_migration_plan・confirm_migration_plan）、v2_history_adopt/prepare.py、tests/v2_history_publish/c2_helpers.py（migration_case・adoption_case）、tests/v2_history_adopt/a5_helpers.py、tests/v2_history_local/test_c3_09_scope.py（C-3の静的監査）、C-3の設計レビュー213bcb7と実装レビュー2049e10、CLAUDE.md。取得できなかったファイルはない。

保護参照：依頼書§7の82参照を `git ls-remote` の完全SHAで照合し、82件とも一致した。資料ブランチ docs/v2-history-maintain-c4-20261104 も ce4fd28 で一致（実装時の83参照目）。

## 2. 結論

**重大0、通常3、提案6。N-01〜N-03を設計・依頼書に数行ずつ足した第2版で、D-1〜D-9を一組で採用することを推奨する。** 第2版の確認は差分だけでよい。

確かめた範囲：

- 範囲（6操作と純粋な plan_unlock）、a6340c3 §5.5 の未決への答え、退避先の名前（publication_hash／plan_hash）、rename による退避、移行と採用の順序は、a6340c3 §4・§5、C-2設計第2版§8、C-3設計§8、C-3の両レビューの引継ぎと矛盾しない。移行で「両方」を経由する順序（公開→snapshot.jsonのrename）は、正本の無い時間を作らず、C-3が「両方」を拒否するので途中で日次が書き足されない。正しい順序だと判断した。
- 試行の差分を 6d69bd7 にそのまま当てると、既存14スイート2069件と仮の範囲試験1件が Python 3.12.3・3.13.18 で全件合格した（設計§7の記述どおり）。
- `raise … from None` が `__context__` に元の例外を残すこと（C4-19・欠陥注入19の前提）は正しい（R6）。C-3・S2 の現行コードには OSError を例外処理の中で投げ直す箇所が無いことも確かめた（C-3の `from None` 2か所は KeyError と C-2 の CoreError で、パスは含まない）。
- ただし、中断後の「作り直し」が同じhashになる前提には書かれていない条件があり（N-01）、依頼書の受入・静的監査のうち2つは、書かれたとおりには満たせない（N-02、N-03）。依頼書は「固定文書に矛盾を見つけたら止める」と定めているので、直さずに渡すと実装が止まる。

## 3. 指摘

### 3.1 重大

なし。

### 3.2 通常

| ID | 根拠 | 内容と影響 | 修正案 | 確認方法 |
|---|---|---|---|---|
| N-01 | 設計§0「中断後の再開は、同じ操作をもう一度呼ぶだけ」、§4.3 理由1「作り直した公開値は同じhashになる（C-2の作り手は決定的）」、§5.4 手順3。v2_history/migrate.py `prepare_migration_plan(snapshot_v1, resolutions, sessions, raw_observations, check_d, request_id, requested_at)`、v2_history_adopt/prepare.py `prepare_prefix_adoption(data, adopt_count, request_id, requested_at)`。MANIFEST の8キー（§4.4） | 作り手は決定的だが、**計画の requested_at（時刻）が候補の記録と plan_hash に入る**。プロセスが終わって計画が手元に無いとき、§5.4 のとおり read_original／read_set_aside のバイトから作り直しても、新しい requested_at で計画を作ると publication_hash が変わり、key が一致しない。移行の「両方」の状態では migrate が maintenance_state_unexpected／v1_and_v2 で止まり、C-3も store_layout_unsupported で止まる。C-4にも出口が無い（人の手でのファイル操作が要る）。採用の replace 後では publication_stale／raw で止まる。移行ではさらに check_d・resolutions・sessions・raw_observations も同じでなければならない。MANIFEST には request_id と plan_hash はあるが requested_at は無い。データは失われず安全側に止まるが、文書の手順どおりにやると「詰まる」道がある。試行のプローブ・総当たりは同じプロセスの同じ計画を使い直しているので、この条件を見ていない | 設計§5.4 手順3と依頼書§3「失敗の後の手順」に次を書く：(1) 作り直しには元の計画と同じ入力（request_id、requested_at、移行では check_d・resolutions・sessions・raw_observations、採用では adopt_count）を使う。(2) requested_at は、実行前に計画の入力を控えておくか、read_original("history.json")（移行の「両方」・「history.jsonだけ」、採用のreplace後）で候補の記録から読む。(3) 作り直した公開値の publication_hash が退避先の key と違えば、操作を呼ばずに入力を見直す。受入 C4-10(a)(b)・C4-12(a) は、計画オブジェクトを使い回さず prepare_\* を呼び直して作り直すこと、と明記し、「別の requested_at で作り直すと hash が違い、migrate は maintenance_state_unexpected で root を変えない」の1項を足す。MANIFEST への requested_at の追加は、形式を変えるので推奨しない | 付属 c4r_probe.py の R1a（移行：renameの故障で「両方」→別の requested_at で作り直すと hash が違い state_unexpected／v1_and_v2、同じ requested_at なら resumed=True）と R1b（採用：解放の故障→解錠→read_set_aside→別の requested_at で publication_stale／raw、同じなら resumed=True）。3.12・3.13 とも観測 |
| N-02 | 依頼書 C4-20「v2_history_maintainに`_make`・`_of`・`object.__new__`…の呼出しが無い」、設計§3「C-4は`_make`・`_of`・`object.__new__`・公開値の構築をしない」、§2.3 の標準ライブラリの一覧（os、secrets、stat、json、dataclasses、typing）。試行 values.py:33-80、store.py:180。C-3の監査 test_c3_09_scope.py（FORBIDDEN_ATTRS に `_make`・`_of`・`_wrap`・`deepcopy`・`copy`、FORBIDDEN_IMPORTS に `copy`・`json`） | 禁止の意図は「C-2の公開値を作らない・写さない」だが、文面は v2_history_maintain 全体の `_make`・`_of` を禁じている。試行は C-4自身の値を `_Frozen` の仕組みで作るので、`UnlockPlan._make`、`RootReport._of`、`cls._wrap`、`copy.deepcopy`（5か所）を使い、`copy` を import する（§2.3の一覧に無い）。実装者が C-3 の監査を写すと試行の形が落ち、文面どおりに直すと値の作り方を新しく考えることになる。どちらにしても「固定文書の矛盾」で止まる | C4-20 と設計§3を「C-2の値（HistoryPublication、Reconciliation）について、`_make`・`_of`・`_wrap`・`from_dict`・`object.__new__`・構築・`copy` を使わない。C-4自身の値（RootReport、UnlockPlan）は `_Frozen` の仕組み（`_make`・`_of`・`_wrap`・`copy.deepcopy`）で作ってよい」に改める。§2.3 の標準ライブラリに `copy` を足す（または値をdataclassにすると決める）。監査は「v2_history_publish から import した名前（とその値）に対する `_make`・`_of`・`_wrap`・`from_dict`・構築」と「RootReport・UnlockPlan 以外のクラスに対する `_make`・`_of`」を見る形にする | c4r_probe.py の R2（試行に文面の禁止への該当11か所、§2.3外の import は copy） |
| N-03 | 依頼書 C4-13「計画・公開値の値を写しただけの実装を、欠陥注入で区別できる」、欠陥注入10「MANIFEST：識別値をロックの下のバイトからでなく公開値から写す（C4-13で区別されること）」。設計§4.4 最後の項。check.py:150-157。試行 store.py の migrate・adopt（MANIFEST をロックの前に公開値の source_v1／expected から作る） | MANIFEST を書く前に check_publication が「ロックの下のバイトの識別値＝公開値の識別値」を確かめるので、どちらから写しても MANIFEST のバイトは到達できるすべての状態で同じになる。欠陥注入10は構成上「等価」で、C4-13 のこの文は満たせない。試行自体が「公開値から写す」形である（設計§4.4 もそれで規則4を満たすと書いている）。規則4の要点は「ロックの下で読んだバイトが照合を通った後にだけ MANIFEST を書く」ことで、試験すべきはこちら | C4-13 の該当文を「MANIFEST は、ロックの下で読んだバイトが check_publication を通った後にだけ書かれる。記録の子クラスで読込み→照合→MANIFEST の順を確かめ、読んだバイトを替える（公開値と違う）と MANIFEST も退避先も作られない」に替える。欠陥注入10を「MANIFEST をロックの下の読込み・照合より前に書く」に替える（または10を残し、等価と予想される理由を依頼書に書く） | c4r_probe.py の R7（MANIFEST の識別値＝hashlib で計算したバイトの値＝公開値の source_v1） |

### 3.3 提案（必須ではない）

| ID | 内容 | 案 |
|---|---|---|
| P-01 | 解錠の手順4（再確認）は、rootにある対象の inode だけを比べ、バイトは手順7（各renameの直前）で比べる。同じ inode のままバイトが変わった対象（宣言が誤っていて書き手が書き足している等）では、MANIFEST と `quarantine/<key>/` を作った後に maintenance_plan_stale になる。設計§5.1「外れれば何も変えない」と C4-06「退避先を変えない」の対象外の場合だが、plan_stale がいつも「何も変えない」とは限らない。同じ計画での再開や新しい計画には差し支えない（R3） | 手順4でバイトの識別値も比べる（ロックの下か、計画のロックの排他の下なので追加の読込みだけで済む）か、§5.1 に「同じ inode でバイトが違うときは、MANIFEST だけの退避先が残る」と1文足し、C4-06 に1項足す |
| P-02 | 退避先が見つからないときの code が文書とずれる。計画にあるロックが最初の試みの前に消えた場合、試行は maintenance_quarantine_invalid／missing を返す（設計§5.1 手順4は maintenance_plan_stale）。§4.2 の表で「退避先が完了済みでなければ maintenance_state_unexpected／v2_present」とする移行・採用の「history.jsonだけ」も、quarantine/ があって `<key>/` が無いときは quarantine_invalid／missing になる（R4） | どちらかに合わせる。人の次の手は同じ（inspect からやり直す）なので、表と§5.5に「退避先が無い場合は maintenance_quarantine_invalid／missing」と書くのが小さい |
| P-03 | inspect は、`quarantine` が通常のファイル・リンクのとき（maintenance_quarantine_invalid）や、history.json がディレクトリのとき（store_root_invalid）に、報告を返さず例外で止まる。報告が無いと plan_unlock も作れないので、同じ root に残ったロック・一時ファイルも解錠できない（R5）。どちらも人の手でしか起きない状態 | 設計§8の既知の制限に「inspect が止まる状態（退避先の親がディレクトリでない、正本がファイルでない）は人が手で直す」と書く。または inspect がその項目を報告の値（regular＝False 等）として返す |
| P-04 | Windows では STRICT が windows_strict で拒否されるので、ユーザーPCでの C-4 はいつも FILE_SYNC_ONLY になる。FILE_SYNC_ONLY ではディレクトリを fsync しないので、採用で「写しの名前の記録」が「history.json の replace」より先にディスクへ届く保証は無い（ファイルの中身は fsync される）。電源断の時に、history.json が候補になり退避先の写しが無い、という並びを理屈の上では否定できない。設計§7の「消失0」は故障の総当たり（電源断ではない）の結果で、§8 の 7 も電源断を未実施としているが、この並びは書かれていない | 設計§5.6・§8 に「FILE_SYNC_ONLY（Windows を含む）では、退避の名前と正本の置き換えの順序は電源断を越えて保証しない」と1文足す。POSIX では採用・移行を STRICT で行うことを推奨と書く。採用の前に read_original で元のバイトを別の場所へ控える手順を利用者向けのまとめに入れると、電源断でも元のバイトを失わない |
| P-05 | check_plan は対象の名前と種類の対応（lock は `write.lock`、tmp は `.history.<…>.tmp` 等）を確かめない。作り手（plan_unlock）の計画では起きず、手作りの計画で正本の名前を書いても手順4で止まる（root に無い対象は退避先に無いので）ことを試行で読んだが、防ぐのは手順4の副作用に頼っている | check_plan で名前と種類の対応を確かめ、外れれば maintenance_plan_invalid／shape。C4-06 の「形が違う計画」に1件足す |
| P-06 | 設計§5.4 手順3は「keyは inspect の退避先の要約（operation、request_id）から選ぶ」とする。同じ request_id で移行と採用、または中断後の別の計画が並ぶと、要約だけでは見分けにくい | RootReport の退避先の要約に MANIFEST の plan_hash と publication_hash も入れる（パスではないので D-7 に反しない）。N-01 の「hash が key と一致するか」の確かめにも使える |

## 4. D-1〜D-9 の推奨

| ID | 推奨 | 理由 |
|---|---|---|
| D-1 範囲 | 採用 | 解錠・移行・採用は退避先・MANIFEST・再開の規則を共有するので、1段にまとめるほうがレビューと範囲試験の固定が1回で済む。退避先の削除・自動の掃除を作らない線引きも妥当 |
| D-2 §5.5の未決への答え | **N-01を入れた第2版で採用** | 停止を人の宣言とし証明と書かない、新しいマーカーを作らず write.lock を持つ、退避先の名前を hash にする、の3点は妥当。「再開は同じ操作をもう一度呼ぶ」は、同じ入力で公開値を作り直す条件を書けば成り立つ |
| D-3 明示解錠 | 採用（P-01、P-02、P-05は任意） | rename による退避は、写しかけの状態と inode の変化を避けられ、写して消す元の案より良い。計画にロックがあればそれを排他にして最後に移す形は、競合を作らない（コードを読んだ限りでは、同じ計画を2つ並べて呼んでも rename が原子的なので後の方が止まる。試行では未確認） |
| D-4 移行の順序 | 採用 | 公開→rename の順で正本の無い時間が無い。「両方」は C-3 が拒否するので、途中の状態で日次が書き足されない |
| D-5 採用の順序とC-2の引継ぎ | **N-01を入れた第2版で採用**（P-04の注記を推奨） | 写し→読み戻し→公開の順で、replace の前に元のバイトが退避先にあることを確かめている。引継ぎ（read_set_aside の元バイトから publish_adoption）は、同じ requested_at で作り直したときだけ同じ hash になる |
| D-6 P-02と失敗の後の手順 | **N-01を入れた第2版で採用** | cleanup の語に頼らず一覧で判断する方針は、C-3実装レビューP-02の答えとして正しい。手順3の「作り直す」に N-01 の条件が要る |
| D-7 S2・C-3との関係 | **N-02を入れた第2版で採用** | FileOps の継承（mkdir・rename だけ追加）、C-3を変えない・importしない、名前の定数の一致を試験で確かめる、の形は妥当。静的監査の文面だけを C-2 の値に絞る |
| D-8 範囲試験 | 採用 | test_c3_09 の1行の固定と仮の開いた範囲で、既存2069件と範囲の鎖が通ることを再現した |
| D-9 担当 | 採用（Sonnet 5.5・high） | 手順はC-3の写しが多く、規則と試行の差分が具体的。N-02・N-03 を直しておけば、実装者が「矛盾で止まる」理由は残らない |

## 5. 実際に行った確認

一時ディレクトリに 6d69bd7 の作業ツリーを作り、試行の差分（6ファイル）を `git apply` でそのまま当て、pushしないローカルコミットにした。製品コードの変更ではない。

| 確認 | 結果 |
|---|---|
| 既存14スイート＋仮の範囲試験（Python 3.12.3、3.13.18、`-B -W error::ResourceWarning`、PYTHONDONTWRITEBYTECODE=1、完全な履歴） | 両版とも 2069件合格（S2 の skip 4 は Windows 専用）＋仮の範囲試験1件。ログ：trial_all_suites_py312_py313.log（runall.sh は C-3 実装時のものと同じ） |
| 独立プローブ c4r_probe.py（R1a・R1b・R2〜R7、3.12・3.13） | 8項目とも観測。出力：c4r_probe_out_py312.txt、c4r_probe_out_py313.txt |
| 作り手の入力の確認 | prepare_migration_plan・prepare_prefix_adoption が requested_at を基礎（basis）と候補の記録に入れることをコードで確認（N-01） |
| 試行のランタイム全1016行の読み合わせ | 設計§4・§5 の手順と対応することを確認。ずれは P-01・P-02 のとおり |
| 保護参照 | 82件一致（資料ブランチ ce4fd28 も一致） |

実施していないもの：Python 3.10・3.11、Windows、unshare による通信遮断、故障の総当たり1,638通り・6プロセスの競合・強制終了の再現（設計§7の結果は読んだだけ）、試行への欠陥注入。

## 6. 未解決事項と次の作業

- 採否はRockyさん。推奨は「N-01〜N-03を入れた第2版（提案P-01〜P-06は任意）を作り、差分を確認してから D-1〜D-9 を一組で採用」。
- 第2版の差分の目安：設計§5.4 と依頼書§3 に N-01 の3文、C4-10・C4-12 に1項ずつ、C4-20 と設計§3・§2.3 の文面（N-02）、C4-13 の1文と欠陥注入10（N-03）。試行の差分は変えなくてよい（N-01〜N-03 は文書の修正で、試行のコードは修正後の規則を満たす）。
- 範囲外として残るもの（設計§8の列挙どおり）：C-3両レビューの残りの提案、C-2・C-1レビューの P-02・P-03、実Windows・物理電源断・ユーザーPCでの確認。

## 7. 変更したもの

このレビュー文書と、確認に使ったスクリプト・出力（docs/reviews/v2_history_maintain_c4_design_review_20261104/）だけを、ce4fd28 から作った新しい資料ブランチ docs/v2-history-maintain-c4-review-20261104 に追加した。製品コード、設計・依頼書、ほかのブランチ、PR、Actions、送信は変えていない。モデル別の利用量は未計測。
