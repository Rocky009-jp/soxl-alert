# V2 S4-C gitの保存先 設計案・限定依頼書 第2版 差分再レビュー結果

作成日：2026-11-05（日本時間）。担当：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
位置づけ：第2版（0caabe2）の、初版（a4464ba）からの差分だけの再レビュー。前回のレビュー記録は docs/v2-git-store-s4c-review-20261105 の 55e770a（docs/reviews/V2_GIT_STORE_S4C_DESIGN_REVIEW_20261105.md）。**D-1〜D-9の採用でも、S4-Cの実装の承認でもない。** 採否はRockyさんが決める。

## 1. 対象と参照したもの

| 用途 | 固定版 |
|---|---|
| 対象 | docs/v2-git-store-s4c-20261105 の **0caabe29e0b40f321fa0fe8936fd727d73500b54**（前の版 a4464baad4674e9832c52f99a55912de69954af5、起点 6cab0506c408d194c63b656713e4a0a7d62c3ba1） |
| 設計 | docs/specs/V2_GIT_STORE_S4C_DESIGN_DRAFT.md（338行、blob b0ab6736） |
| 依頼書 | docs/tasks/V2_GIT_STORE_S4C_LIMITED_IMPLEMENTATION_REQUEST.md（280行、blob 2cf1102a） |
| 試行の差分 | docs/specs/V2_GIT_STORE_S4C_TRIAL_20261105.diff（454行、blob 66828740、SHA-256 f936d8137365b20285994e77003827fccbb0a04f0f9cda9cebc1f774dd15a015。§14の値と一致） |

`git diff a4464ba 0caabe2` の3ファイルを全部読んだ。共有フォルダの写し（specs/・tasks/）は、3本ともリポジトリの版とバイト単位で一致した。試行の差分の違いは v2_git_store の git.py・history.py・outbox.py だけで、範囲試験の1行・仮の範囲試験・探りは初版と同じ。

保護参照：99参照を `git ls-remote` の完全SHAで照合し、99件とも一致した。資料ブランチは 0caabe2、前回のレビュー記録は 55e770a で一致。push後の照合は§7に記す。

## 2. 結論

**N-01・N-02とも解消。重大0、通常0、提案3（R-01〜R-03）。第2版で D-1〜D-9 を一組で採用することを推奨する。依頼書はこのまま実装に渡してよい。** 提案はどれも必須ではなく、採用の後に直しても、実装のときに結果文書で扱ってもよい。

- N-01：outbox用の「足す」コミットが、親の木に同じ名前があればコミットを作らない規則になった（設計§3・§4の7・§6の3、依頼書§3の9・11、S4C-11(g)、欠陥注入19）。作り直しの`ls-tree`・`cat-file`の失敗も取得の失敗と同じ扱いになった（§6の「作り直しの失敗」）。前回の探りX1を第2版の下書きで再実行し、二度目の送信は起きなかった。
- N-02：前回の案（`[remote rejected]`の文言で分ける）から、「拒否の後に取得し直し、先頭が動いたか」で読み分ける方法に変えた（§4の8、T-7）。**T-7の事実と、この方法の妥当性を確かめ、案より良い方法と判断する**（§4）。X2は`store_io_error`・注記なしになり、同時の実行は初版と同じく`publication_stale`・注記ありのままだった。
- P-01：§7・§11の文の修正は、前回の指摘どおりの内容になっている。P-02〜P-10の§14の記録も、前回の中身と合っている（R-03の小さなずれを除く）。

## 3. 指摘

### 3.1 重大

なし。

### 3.2 通常

なし。

### 3.3 提案（必須ではない）

| ID | 内容 | 案 |
|---|---|---|
| R-01 | S4C-03(g)は「同じ親から3つのpushを同時に送り、負けたpush（`[remote rejected] (failed to update ref)`）がREJECTED」とする。負けたpushが`[remote rejected]`になるか`[rejected] (fetch first)`になるかは、相手のpushが受け側の参照の広告より前に終わったかで決まり、試験の時刻しだいで変わる（このレビューでも、順に送れば`[rejected] (fetch first)`、同時なら`[remote rejected]`だった）。文言まで期待にすると、たまに落ちる試験になり得る | S4C-03(g)の期待は「負けたpushはREJECTED、`GitHistoryStore`では`publication_stale`」だけにし、文言はどちらでもよいとして、各文言の回数を結果文書に記録する。`[remote rejected]`が少なくとも1回出たことを確かめたいなら、全回の合計で見る |
| R-02 | 拒否の読み分けは、履歴の`initialize`には書かれた（参照ができていれば`already_initialized`、無ければ`store_io_error`）が、`GitOutbox.initialize()`のpushがREJECTEDのときは書かれていない（S4C-12(b)は「2回目は拒む」だけ）。試行の下書きにも`GitOutbox.initialize`は無い | 設計§6の「初期化」に1文：「pushがREJECTEDなら取得し直し、参照ができていれば2回目と同じく拒み、無ければ`NotifyError`（`outbox_io_error`）」。S4C-12(b)に、同時に2つの初期化をしても1つだけが作る、を足す |
| R-03 | §14のP-02の要約「同じ秒・同じ親・同じ候補の2つの保存は同じコミットになり、両方PUBLISHED」は、**順に**保存した場合（前回のX3'）である。**同時に**pushすると、同じSHAでも受け側の参照のロックで片方が負け、負けた方は`publication_stale`になった（付属 Y4：10回すべて PUBLISHED＋`publication_stale`、APPLYは1つ）。どちらも安全側で、S4C-14の数え方への影響もない | §14のP-02の要約を、次に設計を触るときに「順に保存すると両方PUBLISHED、同時なら片方`publication_stale`」に直す。採否には影響しない。なお、取得し直した先頭が自分のコミットと同じならOKと読む工夫もできる（同じ呼出しの中の値だけで、T-5に反しない）が、結果はT-3と同じなので入れなくてよい |

## 4. T-7の方法（先頭の動きで拒否を読み分ける）の妥当性

**妥当で、前回の案（文言で分ける）より良い。** 理由と確かめたこと：

1. **T-7の事実は正しい。** ローカルのbareリポジトリ（git 2.43.0）で、同じ親から3つのpushを同時に送る試しを10回行い、勝ったpush 10回はすべて`<old>..<new>`、負けたpush 20回はすべて`! … [remote rejected] (failed to update ref)`だった（付属 t7_concurrent_push_3x10.txt）。受け側は、参照の広告の後にロックを取り、古い値を比べて更新するので、広告を同じ先頭で受けた同時のpushは、ロックの比較で負けて`[remote rejected]`になる。前回の案のまま文言で分けると、同時の実行の負けまで`store_io_error`になり、「同時の実行」の注記が消える。第2版の指摘は正しく、前回の案は誤りだった。
2. **意味で分けている。** 「先頭が親から動いた」は、比較交換が負けた理由そのもの（読んだ後に誰かが進めた）を、リモートの状態で確かめている。gitやGitHubの文言・版に依存しない。GitHubの規則・権限の拒否の文言も確かめずに済む。
3. **文言では分けられない場面も正しく読む。** 受け側に参照のロックのファイルが残った場合（前の異常終了など）も`[remote rejected] (failed to update ref)`になるが、先頭は動かない。第2版の下書きで`store_io_error`・注記なしになった（付属 Y1）。これは同時の実行ではないので、正しい読み方である。
4. **取り違えの向き。** 規則の拒否と別の実行の更新が重なった場合は`publication_stale`になるが、そのときは実際に別の実行が進めているので、注記は誤りではない。先頭が動かない拒否を`publication_stale`と読むことは無い（参照は早送りでしか進まず、強制pushは使わない）。取得し直しに失敗した場合は`store_io_error`で、推測しない。
5. **outboxの扱いも一貫している。** 拒否の後、同じ名前が無く先頭も動いていなければ、繰り返さず`NotifyError`（付属 Y2：outboxだけを拒むpre-receiveで、outboxのpushは1回だけ、CLAIM_FAILED、送信0）。先頭が動いていれば、別の鍵で進んだとして作り直す（最大4回）。結果のpushの拒否も同じで、RESULT_NOT_RECORDED、意図はUNKNOWNに残る（付属 Y5）。
6. **履歴の`initialize`。** 2つのクローンから同時に初期化すると、5回すべて片方がINITIALIZED、もう片方が`already_initialized`になった（付属 Y3）。拒否の後に参照ができていれば`already_initialized`、無ければ`store_io_error`、という第2版の規則どおり。

取得し直しが1回増えるのは、拒否の後だけである。U-12（再試行しない）にも反しない（取得し直しは判定のためで、pushの再試行ではない）。

## 5. 実際に行った確認と結果

すべてこのレビューの一時環境（Linux、git 2.43.0、Python 3.13.18）。試行の木のコミットはローカルだけで、pushしていない。

### 5.1 第2版の試行の再現

第2版の試行の差分を 6cab050 に`git apply`でそのまま当てた（SHA-256 一致）。

| 確かめたこと | 結果 |
|---|---|
| 場面1〜7 | 初版と同じ（1 DONE・SENT、2 SKIPPED_CLAIMED、3 別クローンでSKIPPED_CLAIMED・状態morning SENT、4 `publication_stale`、5 DONE、6 `run_publish_not_published`、7 `store_io_error`・DAMAGED・印の漏れなし） |
| 同時の実行 2×10・3×10・4×10 | どれも`sends: {('halt', 'judgment'): 10} dup APPLY rounds: 0`。負けた実行はすべて`publication_stale`（判定なしSENT、残りはSKIPPED_CLAIMED） |
| 前回の探りX1（写しがmorningの2ファイルを落とす） | 2つ目のクローンはSKIPPED_CLAIMED、送信1回。outboxのコミットは3つ（初期化・意図・結果）で、置き換えのコミットは作られていない（出力の「replaced: True」の行は意図のファイルが1つであることだけを見ており、置き換えの有無はコミット数で読む） |
| 前回の探りX2（`state`だけを拒むpre-receive） | STOPPED `store_io_error`、判定なしSENT、「同時に動いていた」の注記なし |

### 5.2 追加の探り（付属 s4c_v2_rereview_probe.py、出力 s4c_v2_rereview_probe_out.txt）

| ID | 場面 | 結果 |
|---|---|---|
| Y1 | リモートの`refs/heads/state.lock`が残っている | STOPPED `store_io_error`、判定なしSENT、注記なし |
| Y2 | outboxの参照だけを拒むpre-receive | DONE、判定ありCLAIM_FAILED、送信0、outboxのpushは1回 |
| Y3 | 2つのクローンから同時に履歴を初期化（5回） | 毎回 INITIALIZED と `already_initialized` |
| Y4 | 同じ候補を2つのクローンから同時に保存（10回） | 毎回 PUBLISHED と `publication_stale`、D1のAPPLYは1つ（R-03） |
| Y5 | 結果のpushが先頭を動かさずに拒否される | RESULT_NOT_RECORDED（送信はSENT、1回）、リモートの意図はUNKNOWN |

実行方法：第2版の試行の差分を6cab050に当てた木を`<tree>`として、`TMPDIR=<一時ディレクトリ> PYTHONDONTWRITEBYTECODE=1 python3 -B s4c_v2_rereview_probe.py <tree>`。X1・X2は前回の付属（docs/reviews/v2_git_store_s4c_review_20261105/s4c_review_probe.py）を同じ木で実行した。

### 5.3 スイート

第2版の下書きは v2_git_store の中だけの変更で、ほかのパッケージは v2_git_store を import しない。初版の試行の木で17スイート2,481件の合格を前回確かめているので、今回は関係するスイートだけを第2版の木で走らせた（付属 suites_trial2_py3.13.log）。

| スイート | 件数 | 結果 |
|---|---|---|
| v2_scope_chain（範囲の鎖） | 34 | 合格 |
| v2_daily_run（S4-A） | 96 | 合格 |
| v2_notify（S4-B、test_s4b_09を含む） | 131 | 合格 |
| v2_git_store（仮の範囲試験） | 1 | 合格 |

### 5.4 実施していないもの

- 第2版の木での残り13スイートの再実行（上の理由で影響なし）、Python 3.10〜3.12、Windows、GitHubのリモート、Actions。
- 依頼書の受入S4C-01〜18・欠陥注入20件そのものの実行（実装が無いため）。

## 6. 採否の推奨

| ID | 推奨 |
|---|---|
| D-1〜D-9 | **第2版のまま一組で採用を推奨**。D-3・D-4・D-5は、N-01・N-02の解消で前回の条件を満たした |

採用に含まれないもの（設計§12のとおり）：S4-Cの実装の着手（別スレッドへの明示の指示）、非公開リポジトリ・GitHubへのpush・秘密・workflow（S4-E）、本番、S4-D以降。

次の最小作業：採用の記録（資料ブランチ）と、実装の着手の指示。実装時の保護参照は、99参照＋資料ブランチ（第2版 0caabe2、または採用記録の版）＋前回のレビュー記録 55e770a＋本記録。R-01〜R-03は、実装の結果文書で扱ってよい（R-01はS4C-03(g)の試験の書き方、R-02はGitOutbox.initializeの拒否）。

## 7. 変更したもの・保護参照

- 変更：この記録と付属（docs/reviews/v2_git_store_s4c_v2_rereview_20261105/）を、0caabe2から作った別ブランチ docs/v2-git-store-s4c-v2-rereview-20261105 にコミットした。共有フォルダ reviews/ にも写しを置いた。資料ブランチ・実装ブランチ・製品コード・既存試験・main・workflow・外部サービスは変更していない。PR・送信はしていない。
- 保護参照：開始時に99参照＋0caabe2＋55e770aが一致。PUSH_CHECK_PLACEHOLDER
