# V2 C-3 v2ローカル正本 設計案

作成日：2026-11-04（日本時間）。版：**第2版**（初版fd3c5bbへの設計レビュー213bcb7の通常N-01を、依頼書の1文と受入の1項として反映。設計の本文の規則は初版と同じ。§10）。
状態：**第2版・D-1〜D-9採用済み（§11）。限定実装は別スレッドへの明示の着手指示で始める。C-4（保守操作）は対象外。**
Rockyさんの「C-3の設計書と依頼書の作成を承認します」（2026-11-04、コーディネーター経由）を受けて作成した。今回の作業は、設計書と限定実装依頼書の作成、一時環境での試行まで。文書の保存、推奨、試行の合格を、実装の承認とは扱わない。作成担当はClaude Opus 5.5、effort high（このスレッドのセッション設定）。

## 0. 要約

- **C-3の範囲（D-1）**：v2履歴（schema 2）を、専用のディレクトリに1つのファイル`history.json`として保存する、ローカル機の試験用ストア`HistoryFileStore`を作る。操作は4つだけで、読込み、GENESISの初期化、追記（APPEND）の公開、成否不明の後の照合（読取り専用）。書くものは、C-2の作り手（publish_\*）が同じプロセスで返した公開値だけ。移行（MIGRATION）、採用（ADOPTION／REPLACE）、明示解錠、退避はC-4。早朝の日次処理への組込みと通知はS4。
- **S2との関係（D-2）**：OSの呼出しは、S2の`FileOps`（v2_persistence/local/fsops.py）を変えずに使う。S2の`LocalFileStore`のクラスや内部メソッドは呼ばず、ロック・走査・読込み・公開の手順を、S2と同じ順序と同じエラーの流儀（`LocalStoreError`、固定のcode・phase・cleanup）で書く。S2は1文字も変えない。
- **rootの形（D-3）**：正本`history.json`、ロック`write.lock`（**S2と同じ名前**、中身はv2用の固定語＋乱数）、一時ファイル`.history.<乱数>.tmp`。v1の`snapshot.json`があれば、どの操作も止める（移行はC-4）。C-3・S2どちらの一時ファイルが残っていても、照合以外の操作を止める。ほかの名前（C-4の`quarantine/`を含む）は見ない。
- **C-2の提案P-01（D-4）**：公開では、今の`history.json`を先に厳格に読み（既存read_history_bytes）、その後でcheck_publicationを呼ぶ。だから公開で返る`history_invalid`は、いつも「今のファイルが壊れている」を意味する。check_publicationが返す`publication_invalid`・`publication_stale`はそのまま返し、それ以外の拒否（手作りの値の候補が無効なときの`history_invalid`等）は`store_candidate_invalid`に包む。試行で区別を確かめた。
- **成否不明と照合（D-5）**：S2と同じく、replaceの呼出しを始めた後の失敗は`store_commit_uncertain`。照合`reconcile(publication)`は、ロックの下で`history.json`を読み直し、C-2のreconcile_publicationの4つの結果を返す。一時ファイルの残りでは止めない（`history.json`を変えないため）。ロックが残っていれば`store_busy`で止まり、自動では解錠しない。
- **公開値の受け取り（D-7、C-2レビューP-01の引継ぎ）**：`type(p) is HistoryPublication`だけを受け取り、v2_history_localは`_make`・`object.__new__`・公開値の構築を一切しないことを範囲試験の静的監査で確かめる。
- **範囲試験（D-8）**：C-2の範囲試験test_c2_09のENDをd6b0332に**1行で**固定する（C-2は自己読直しをHEADにしてあるので1行で足りる。試行で確認）。同じコミットでC-3の開いた範囲試験（START＝d6b0332、END=None）を足す。C-3の試験は一時ディレクトリにだけ書き、競合と強制終了の試験に限ってS2と同じ形の子プロセスを使う。
- **一時環境での試行**：d6b0332のコピーにC-3を試作した（pushしない）。既存13スイート1930件がPython 3.12.3と3.13.18で全件合格（test_c2_09の1行の固定を含む）。初期化・公開・拒否・rootの形・成否不明と照合・ロックの横取り・P-01の区別等の42項目（使い捨てのプローブ）と、8プロセス×20回の競合（成功1、ほかはstore_busyまたは既適用の拒否、残留物なし）が期待どおりだった（§7）。
- 運用方針は日足のみ（早朝に米国の確定日足で通知し、夜の寄付きで手動購入）。分足・NBBOは前提にしない。書き手は早朝の定時処理1つと、日中に人が行う保守だけを想定する。
- 採否はD-1〜D-9の一組（§8）。

## 1. 目的と固定入力

| 用途 | 固定版 |
|---|---|
| 起点（コード・試験） | **d6b0332500af8d8d46ddaae6c7fda39ee38a03db**（feat/v2-history-publish-c2-20261103）。C-2の試験対象29e2659に結果文書1本を足した保存最終 |
| C-2の受領 | 実装レビューa91a9ed31481e97cc8b56c2396f86d957fa567e0（docs/v2-history-publish-c2-impl-review-20261103、docs/reviews/V2_HISTORY_PUBLISH_C2_REVIEW_20261103.md、重大0・通常0・提案3、受領推奨）。d6b0332で受領済み |
| C-2の設計（第2版） | 081637e95160a23aab5ea0fc3a2edd01976abba4（docs/v2-history-publish-c2-revision-20261103）のdocs/specs/V2_HISTORY_PUBLISH_C2_DESIGN_DRAFT.md。特に§5（バイト・CAS・照合）、§6.3（次の段階の模擬）、§8（既知の制限とC-4への引継ぎ） |
| 上位の方針 | a6340c3937092e4cb658913b9acfb4973a084326 docs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md §5.1（日足の運用から決まること）、§5.3（C-3の方針案）、§5.5（C-4の未決） |
| S2のローカル保存 | 受領済みのv2_persistence/local（store.py、fsops.py、errors.py、results.py）。S2の設計73cec62・修正d404d4d・ユーザーPC確認aa21dbe |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6（D-3）、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4、C-2設計第2版§6.3 |
| 運用方針 | 日足単位の判定。早朝に米国市場の終値で通知し、夜の寄付きで買う。分足・NBBOは前提にしない（2026-10-26） |

読解対象：d6b0332のv2_history_publish（全6ファイル）、v2_persistence/local（全5ファイル）、試験のtests/v2_persistence_local/l_helpers.py（FaultOps、Worker）、test_c2_09_scope.py、sc_helpers.py、test_sc_02_chain.py、上の各文書とC-2の設計レビューa6e783e・実装レビューa91a9ed。共通のCLAUDE.mdも確認した。取得できなかったファイルは無い。

## 2. C-3の範囲（D-1）

### 2.1 前の段階が残したもの

- C-2は「何を書いてよいか」を公開値として決め、CASの検査と照合を純粋関数で定めた。ファイルには触れない。
- C-2レビューの提案P-01：check_publicationは、手作りの公開値（`_make`）の候補が無効なとき`history_invalid`を返す。C-3がこれを「今のファイルが壊れている」と読むと、誤った診断の経路へ進みうる。
- C-2の既知の制限：check_publicationは確認ではない。C-3は同じプロセスでpublish_\*が返した値だけを受け取り、範囲試験で監査する。
- C-4への引継ぎ：採用のREPLACEの中断後は、退避した元バイトからpublish_adoptionで公開値を作り直す（C-3では扱わない）。

### 2.2 C-3がすること・しないこと

| する | しない（C-4・S4） |
|---|---|
| 専用のrootで`history.json`を読む（毎回ロックの下で、完全に検査） | v1の`snapshot.json`からの移行、v1ファイルの退避 |
| GENESISの公開値で空のrootを初期化する | prefix採用（REPLACE）、元バイトの退避、MANIFEST、`quarantine/` |
| APPENDの公開値（DAILY・RESOLUTION・RESTART・RESTORE）を、一時ファイル→fsync→1回のreplaceで公開する | ロックや一時ファイルの明示解錠・掃除、中断後の再開 |
| replaceの成否が分からないとき、読み直して照合の結果を返す | 自動の再試行、通知、日次処理の組立て、本番の保存先 |

### 2.3 パッケージ

新しいパッケージ`v2_history_local`（ファイル案：`__init__.py`、`results.py`、`store.py`の3本）。依存は標準ライブラリ（os、secrets、stat、dataclasses、typing。S2と同じ集合）と、変更しないv2_core（エラーの型）、v2_persistence.local（FileOps、LocalStoreError、cleanupの固定語、保存水準の固定語）、v2_history_publish（公開値の型、check_publication、reconcile_publication、history_bytes、read_history_bytes、書き方と元の固定語）。hashlibは使わない（識別値はC-2のread.pyが計算する）。

既存のパッケージ・試験・ヘルパーは変えない。例外は§6の範囲試験の固定（test_c2_09の1行）だけ。

## 3. S2との関係（D-2）

- **FileOpsを使う**：OSに触れる薄い層は、S2の`FileOps`を変更せずにimportして使う（S3-B第2版§9.3で「S3-Cで決める」とされた点への回答。a6340c3 §5.3の推奨どおり）。試験は、S2の試験と同じく`_ops`引数（試験用の継ぎ目）に記録・故障注入の子クラスを渡す。
- **S2のクラスは使わない**：`LocalFileStore`の内部メソッド（_acquire、_publish等）は呼ばない。S2の公開APIはsnapshot.json用で、v2履歴には使えないからである。C-3は同じ手順を自分のファイルに書く（約400行、試作で397行）。重複は受け入れる。S2を共通の基底クラスへ作り直す案は、受領済みでユーザーPC確認も済んだS2を変えるので推奨しない。
- **同じ手順・同じ順序**：root（絶対パス、存在するディレクトリ、リンクでない）→ロック（O_EXCL、期限・横取りなし、マーカーを書く）→走査→読込み（lstat、通常ファイル、リンクでない、読んだ前後で同じinode）→（公開なら）保存水準の確認→一時ファイル（O_EXCL）→全量の書込み（短い書込みの再試行）→flush→ファイルのfsync→close→ロックの所有確認→1回のreplace→（strictなら）ディレクトリのfsync→ロックの解放（所有を確かめてunlink）。
- **同じエラーの流儀**：`LocalStoreError`（code・field・phase・rule・cleanup・primary）。パス・OSのエラー文・入力値をエラーに入れない。cleanupの固定語（tmp_left、tmp_ownership_unconfirmed、lock_left、lock_not_ours_left_untouched）もS2のまま。

## 4. rootの形と操作（D-3、D-4）

### 4.1 rootの中の名前

| 名前 | 意味 |
|---|---|
| `history.json` | v2の正本（C-2のhistory_bytesの正規化UTF-8） |
| `write.lock` | 書き手の排他。**S2と同じ名前**なので、同じrootでS2とC-3の書き手は互いにstore_busyになる。中身は`v2_history_local.lock\n`＋乱数（S2の`v2_persistence.local.lock\n`とは違う） |
| `.history.<32桁の16進>.tmp` | C-3の一時ファイル |
| `snapshot.json`、`.snapshot.<…>.tmp` | S2（v1）の正本と一時ファイル。C-3は書かない |
| そのほか（`quarantine/`を含む） | C-3は見ない（S2と同じ）。`quarantine/`はC-4が使う |

推奨はS2とは別の専用rootを使うこと。同じrootに両方があり得るのは、C-4の移行の途中だけである。

### 4.2 rootの状態と操作

| 状態 | read | initialize | publish | reconcile |
|---|---|---|---|---|
| 空（history.jsonもsnapshot.jsonも無い） | store_uninitialized | 可 | store_uninitialized | C-2の照合（今＝無い） |
| history.jsonだけ | 可 | already_initialized | 可 | 可 |
| snapshot.jsonだけ | store_layout_unsupported／v1_only | 同左 | 同左 | 同左 |
| 両方 | store_layout_unsupported／v1_and_v2 | 同左 | 同左 | 同左 |
| 一時ファイルの残り（C-3・S2どちらも） | store_artifact_present | 同左 | 同左 | **止めない** |
| ロックがある | store_busy | 同左 | 同左 | 同左 |

S2の書き手は、v2のrootを向けられると`snapshot.json`が無いのでstore_uninitializedになる。S2のinitializeがv2のrootにsnapshot.jsonを作った場合は、C-3がv1_and_v2で止まる（安全側に止まる。S2は変えないので、この順で検出する）。

### 4.3 操作（API）

`HistoryFileStore(root, writable=False, durability=STRICT, *, _ops=None)`。durabilityはS2と同じ`STRICT`／`FILE_SYNC_ONLY_MODE`。

| 操作 | 受け取る公開値 | 手順（ロックの下） | 戻り値 |
|---|---|---|---|
| `read()` | なし | 走査→読込み→read_history_bytes | History |
| `initialize(publication)` | CREATEでsourceがGENESISだけ | 走査→history.jsonが無いこと→check_publication(None, p)→公開 | HistoryStoreResult(INITIALIZED) |
| `publish(publication)` | APPENDだけ（DAILY・RESOLUTION・RESTART・RESTORE） | 走査→読込み（無ければstore_uninitialized）→**read_history_bytesで今を検査**→check_publication(今, p)→公開 | HistoryStoreResult(PUBLISHED) |
| `reconcile(publication)` | 公開値なら書き方を問わない | 走査（一時ファイルは除く）→読込み（無ければNone）→reconcile_publication | C-2のReconciliation |

- 公開値の型が違えば、ロックを取る前に`store_publication_invalid`／type。書き方・元が操作に合わなければ`store_operation_unsupported`（rule＝not_append／not_genesis）。MIGRATIONとADOPTIONはどちらの操作でも受け付けない（C-4）。
- initialize・publishは`writable=True`のときだけ（S2と同じstore_read_only）。read・reconcileは読取り専用のストアでもできるが、S2と同じくロックを取る。
- `HistoryStoreResult`は不変で、status、committed（常にTrue。正常完了だけが返す）、history、persistence_level、publication_hashを持つ。通知の権利や、電源断への保証ではない（S2と同じ注記）。

### 4.4 拒否の分け方（C-2の提案P-01）

publishの拒否は、次のように読める。

| 返るもの | 意味 |
|---|---|
| `history_invalid`（ほかのv2_historyの既存code） | 今の`history.json`が壊れている（read_history_bytesが拒否した）。C-4の診断（B-5a）へ |
| `publication_stale` | 公開値を作った後に、ほかの書込みが先に入った（作り直す） |
| `publication_invalid` | 公開値の形・hashの誤り（作り手の値では起きない） |
| `store_candidate_invalid`（phase＝candidate） | 公開値の候補そのものが無効（手作りの値だけ）。今のファイルの破損ではない |
| `store_*`（S2と同じ） | root・ロック・書込み・保存水準の問題 |

今のファイルを先に検査するので、check_publicationの`history_invalid`が今の破損を意味することはない（check_publicationは同じバイトを同じ関数で読み直すだけ）。試行で、壊れた今→`history_invalid`、手作りの値→`store_candidate_invalid`（ファイルは変わらない）を確かめた。

## 5. 書込み・成否不明・照合（D-5、D-6）

### 5.1 書込みの手順と失敗

§3の順序はS2の§6.3と同じで、失敗の扱いもS2と同じ。

| 失敗の場所 | 返すもの | 残るもの |
|---|---|---|
| ロックの作成 | store_busy（既にある）／store_io_error | 作れなかったロックは自分のものだけ消す |
| 走査・読込み・検査 | 各code | なし |
| 保存水準の確認 | store_durability_unsupported（windows_strict／directory_sync） | なし |
| 一時ファイルの作成〜close | store_io_error（phase＝tmp_create〜close） | 自分の一時ファイルを消す。消せなければcleanup＝tmp_left |
| ロックの所有確認 | store_lock_ownership_lost | 一時ファイルを消す。他人のロックには触らない |
| replaceの呼出し以後 | **store_commit_uncertain**（phase＝replace／dir_sync） | 一時ファイルを消す |
| ロックの解放 | store_io_error（lock_left）、所有を失っていればstore_lock_ownership_lost（他人のロックはそのまま）。公開の後ならstore_commit_uncertainにcleanupを足す | ロック |

### 5.2 照合の使い方

store_commit_uncertainを受けた呼び出し側は、同じ公開値で`reconcile`を呼ぶ。

- PUBLISHED／PUBLISHED_THEN_EXTENDED：公開は入っている（後者はさらに記録が続いている）。
- NOT_PUBLISHED：まだ入っていない。同じ公開値でもう一度publishを呼んでよい（ロックの下でCASをやり直す）。C-3は自動で再試行しない。
- CONFLICT：入っていない上に、今が期待どおりでもない（読めない今を含む）。保存できなかったこととして扱い、前日値で埋めない。
- 照合は誰が書いたかを示さず、通知の権利も与えない（C-2§5.3）。通知の判断はS4。
- 照合は一時ファイルの残りで止まらない（replaceが失敗して一時ファイルが消せなかった直後でも答えを出すため）。v1のファイルがあれば止まる。ロックが残っていればstore_busyで止まり、C-4の明示解錠を待つ（S2・a6340c3 §5.1と同じく、自動で解錠しない）。

### 5.3 保存水準

S2と同じ。STRICT（ファイルとディレクトリのfsync。Windowsは`windows_strict`で拒否、ディレクトリのfsyncができなければ`directory_sync`で拒否）と、FILE_SYNC_ONLY（ファイルのfsyncだけ）。persistence_levelの固定語もS2のもの。実機の電源断、実Windowsはこの段階でも未確認のまま残る。

### 5.4 日足の運用での流れ（S4で組み立てる想定。C-3では実装しない）

早朝の定時処理：`read()`→publish_day（C-2）→`publish()`。store_busyなら前回の異常終了のロックの残りなので止め、保存できなかったことを知らせる（自動解錠なし）。publication_staleなら読み直して作り直す。store_commit_uncertainなら`reconcile()`。保守（再開始・復元）は日中に人が行い、publish_restart／publish_restoreの公開値を同じ`publish()`で書く。

## 6. 範囲試験（D-8）

### 6.1 前の段階の固定（1行）

tests/v2_history_publish/test_c2_09_scope.pyの`END = None`を、受領した最終コミットの完全SHAに替える。

    END = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"   # accepted (review a91a9ed); frozen when C-3 began

C-2の範囲試験は、自分のファイルの範囲の値をHEADから読む（C-2設計§6.3）ので、この1行だけで通る。試行で、1行の固定と仮の開いた範囲試験1本を同じコミットに入れて、既存1930件が合格することを確かめた。開いた範囲が0本になる形（ENDだけの固定）は、C-2レビュー§4.5のとおり範囲の鎖の試験が2件失敗するので、自分の開いた範囲試験を同じコミットで足す。

### 6.2 C-3の試験

- 新しいディレクトリ`tests/v2_history_local/`に`test_c3_*.py`、`c3_helpers.py`、必要なら`c3_worker.py`（子プロセスの本体）を置く。`__init__.py`は作らない。
- 範囲試験は`START = "d6b0332…"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。自分のファイルの範囲の値はHEADから読む。前の段階の差分を固定文字列で書き写さない。test_c2_09の1行は、C-3自身の差分のハンクとして固定する。
- **書込みの許可**：C-3の試験はファイルを書く。書くのは`tempfile`で作った一時ディレクトリの中だけで、作業ツリーとホームには書かない（S2の試験と同じ）。終わったら消す。
- **子プロセスの許可**：競合と強制終了の試験に限り、`sys.executable`で`tests/v2_history_local/c3_worker.py`を起動してよい（S2のB-04・B-06と同じ形）。ネットワーク、時計に依存する待ち（sleepでの順序付け）、環境変数の読取りは使わない。
- **次の段階の模擬**：受入の一部として、使い捨てのコミットで、(1) C-3の範囲試験のENDだけを自分の試験対象のSHAに替え（1行）、(2) 仮の開いた範囲試験1本を足し、test_sc_\*・test_c1_\*・test_c2_\*・test_c3_\*が通ることを確かめる（C-2設計§6.3と同じ形）。
- 範囲の鎖は`adfdf765→…→bfbde7a→de6549a→d6b0332→（C-3、END=None）`になる。

### 6.3 扱わないもの

C-2実装レビューの提案P-02（test_c2_03に移行の読み方の順序の試験1件）とP-03（結果文書の注記）は、C-3でtest_c2_03を触らないので扱わない。C-1レビューの提案P-03（r4_09）も同じ。

## 7. 一時環境での試行（2026-11-04、Linux）

**位置づけ**：方式の確からしさを確かめるための使い捨ての試行。d6b0332から作ったローカルの作業ツリーに、`v2_history_local`（3ファイル、+430行）を試作し、test_c2_09の1行の固定と、仮の範囲試験1本（STARTがREVの祖先であることだけを見るもの）を加え、pushしないローカルコミットで試験した。正式な実装、受入試験、欠陥注入、レビューの代わりにしない。

環境：Linux、Python 3.12.3と3.13.18、`PYTHONDONTWRITEBYTECODE=1`、`-B -W error::ResourceWarning`。Windows、3.10・3.11、unshareによる通信遮断、物理電源断は実施していない。

| スイート | 試作後（3.12／3.13） |
|---|---|
| コア・保存・S2・S3-A・B-1〜B-5b・範囲の鎖・C-1 | 1780 OK（S2のskip 4はWindows専用） |
| C-2 test_c2_\* | 150 OK（test_c2_09のENDを固定） |
| 合計 | **1930件合格**（仮の範囲試験1件は別） |

**プローブ（42項目、すべて期待どおり）**：初期化（INITIALIZED、読込みが候補と同じ、ファイルが正規化バイト、history.json以外が残らない、二重の初期化、未初期化の読込み）。公開（PUBLISHED、読込み、同じ公開値の2回目はpublication_stale／head、読取り専用、書き方・元の取り違え3種、dictの拒否、採用の拒否）。rootの形（v1_and_v2、v1_only、C-3・S2の一時ファイルの残りで公開は止まり照合は止まらない、ロックでstore_busy、quarantine/は見ない）。S2がC-3のロックでstore_busyになること。成否不明（replaceが失敗→照合NOT_PUBLISHED、replaceが成功してから例外→PUBLISHED、ディレクトリのfsyncの失敗→PUBLISHED、その後1日足して→PUBLISHED_THEN_EXTENDED、どれも一時ファイルが残らない）。replaceの直前にロックを他人のものに替えると成否不明になり、他人のロックはそのまま残る。P-01の区別（壊れた今→history_invalid、候補の記録を書き換えて`_make`で作った値→store_candidate_invalid、ファイルは変わらない）。字下げ付きの今を受け付けて正規化して書く。Windowsのstrictの拒否とfile_sync_onlyの成功。history.jsonがシンボリックリンクならstore_root_invalid。空のrootでのGENESISの照合はNOT_PUBLISHED。

**競合（使い捨て、spawnの8プロセス×20回）**：同じGENESISのrootに、各プロセスが読込み→publish_day（D1）→publishを繰り返した。160回のうちPUBLISHED 1、store_busy 90、既に適用した日の拒否（publication_refused／not_prepared）69。最後の`history.json`は先頭1の有効な履歴で、rootに残ったのは`history.json`だけだった。

試作の差分（5ファイル、+450／−1行、仮の範囲試験を含む）は、同じ資料コミットのdocs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diffに参考として保存する（未適用。SHA-256は§9）。実装者はこれを写すのではなく、本書と依頼書の規則に従って作り、違いがあれば結果文書で説明する。試作は受入試験・欠陥注入・強制終了の試験・正式な範囲試験・名前の整理を含まない。

## 8. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | C-3の範囲：HistoryFileStoreの4操作（read、initialize＝GENESIS、publish＝APPEND、reconcile）だけ。移行・採用・解錠・退避はC-4、日次処理と通知はS4（§2） | 採用を推奨 |
| D-2 | S2との関係：FileOpsを変えずに使い、LocalFileStoreのクラス・内部は使わず、同じ手順・順序・エラーの流儀で書く。S2は変えない（§3） | 採用を推奨。S2を共通化する案は受領済みのS2を変えるので推奨しない |
| D-3 | rootの形：history.json、S2と同名のwrite.lock（v2用のマーカー）、`.history.*.tmp`。v1のファイルは全操作を止める、一時ファイルの残りは照合以外を止める、ほかの名前は見ない。専用rootを推奨（§4.1、§4.2） | 採用を推奨 |
| D-4 | 操作と拒否：公開値の型・書き方の確認はロックの前、publishは今を先に検査してからcheck_publication、check_publicationのpublication_\*以外の拒否はstore_candidate_invalid（C-2の提案P-01）（§4.3、§4.4） | 採用を推奨 |
| D-5 | 成否不明と照合：replaceの呼出し以後の失敗はstore_commit_uncertain、reconcileはロックの下でC-2の照合を返し、一時ファイルでは止まらず、ロックの残りでは止まる。自動の再試行・解錠なし（§5.1、§5.2） | 採用を推奨。ロックを取らずに読む照合は、S2の「読込みも毎回ロックの下」を崩すので推奨しない |
| D-6 | 保存水準：S2と同じSTRICT／FILE_SYNC_ONLY、Windowsのstrictは拒否、結果値は通知の権利ではない（§5.3） | 採用を推奨 |
| D-7 | 公開値の受け取り（C-2レビューP-01の引継ぎ）：`type(p) is HistoryPublication`だけ。v2_history_localは`_make`・`object.__new__`・公開値の構築をしない（静的監査）。試験で`_make`を使うのはP-01の区別の試験1本だけ | 採用を推奨 |
| D-8 | 範囲試験：test_c2_09のEND＝d6b0332（1行）と自分の開いた範囲試験を同じコミットで。試験は一時ディレクトリにだけ書き、子プロセスは競合・強制終了の試験だけ。次の段階の模擬を受入に含める（§6） | 採用を推奨 |
| D-9 | C-3の実装単位と担当：対になる依頼書の範囲（新しいパッケージ、新しい試験ディレクトリ、test_c2_09の1行、結果文書）。担当はSonnet 5.5・high | 採用を推奨。手順はS2の写しに近く、規則と試行の差分が具体的。矛盾や規則の追加が必要なら止めて主担当へ返す |

D-1〜D-9を一組で判断する。今回の文書作成と一時環境の試行は採用ではない。C-2の受領を、C-3の実装承認にしない。C-4、全体稼働、本番の保存先・資格情報・通知・定時実行は今回の採否に含まない。

範囲外として残すもの：C-2実装レビューの提案P-02・P-03、C-1レビューのP-02・P-03、B-4§7.1の既知の制限（案a）、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02、U-03、U-07、a6340c3 §5.5の未決（C-4の依頼前に判断）。

既知の制限：(1) S2の書き手は`write.lock`の中身を見ないので、C-4の明示解錠でロックを外した後に旧S2の書き手が動けば書ける（停止の宣言が正しくない場合だけ。a6340c3 §5.4）。(2) 一時ファイルの残り・ロックの残りを片付ける手段はC-4まで無い（その間はstore_artifact_present／store_busyで止まり続ける）。(3) 実Windows、物理電源断、ネットワークドライブ・同期フォルダ上のrootは未確認。(4) Pythonの内部を直接呼べば公開値の形の値を作れる（C-2§8）。C-3は型と静的監査で防ぐだけ。

## 9. 作業記録

- 担当モデル：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
- 開始時（2026-11-04T00:40Z頃）に、C-2依頼書第2版§7の75参照＋docs/v2-history-publish-c2-revision-20261103（081637e）＋feat/v2-history-publish-c2-20261103（d6b0332）＋docs/v2-history-publish-c2-impl-review-20261103（a91a9ed）の計78参照を、`git ls-remote`の完全SHAで照合し、78件とも一致した。終了時の照合は依頼書§7と結果の報告に記す。
- 本書、依頼書、試行の差分の3ファイルだけを、d6b0332から作った新しい資料ブランチdocs/v2-history-local-c3-20261104に追加した。製品コードの変更、PR、Actions、送信、新しい市場計算は0。一時環境の作業ツリーとローカルコミットはpushしていない。
- 試行の差分docs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diffのSHA-256は c3db632d539fa1f15ac24da7e0f7d84062207194d9c2d5f3b8b626382840b070（一時環境のd6b0332→試作後の`git diff`の出力そのまま。対象はv2_history_local、tests/v2_history_publish/test_c2_09_scope.py、tests/v2_history_local）。
- モデル別の利用量は未計測。

## 10. 第2版の改訂（2026-11-04）

初版fd3c5bbへのOpus 5.5・highの設計レビュー（213bcb7、docs/v2-history-local-c3-review-20261104のdocs/reviews/V2_HISTORY_LOCAL_C3_DESIGN_REVIEW_20261104.md、重大0・通常1・提案7）の通常N-01だけを反映した。提案P-01〜P-07は任意で、反映していない（範囲外として残す）。

| レビュー | 改訂した箇所 | 内容 |
|---|---|---|
| N-01（通常） | 依頼書§3「公開値の受け取り」の1文、C3-06の1項、C3-15の許可 | 手作りの値で body に mode（初期化では source も）が無いと、書き方を読む時点で生のKeyErrorが外へ出る（試行の`pub.mode`）。書き方・元は形の誤りで例外が漏れない方法で読み、読めなければロックの前にstore_publication_invalid／shape。D-4の拒否の分け方（§4.3・§4.4）を、この1か所でもそろえる |

試行の差分（§7）は初版のまま参考として残す。N-01の漏れは試行のコードに残っているので、写さない。

## 11. 採否の記録（2026-11-04）

Rockyさんの「推奨どおり」（2026-11-04T01:14Z）により、設計レビュー213bcb7の推奨（N-01を入れた第2版の差分を確認してから、D-1〜D-9を一組で採用）に従い、**D-1〜D-9を採用した**。D-4は第2版（§10のN-01の1文を含む形）で採用。第2版の差分は6ca2c9eで、内容がN-01だけであることを`git diff --word-diff fd3c5bb 6ca2c9e`で確認した。

§8の表の「推奨（未採用）」の列は採否の時点の記録として残す。提案P-01〜P-07、§8の範囲外の項目、C-4、全体稼働、本番の保存先・資格情報・通知・定時実行は今回の採用に含まない。
