# V2 C-3 v2ローカル正本 限定実装の結果

作成日：2026-11-04（日本時間）。対象：`Rocky009-jp/soxl-alert`、実装ブランチ `feat/v2-history-local-c3-20261104`。
範囲：v2履歴を1つのファイル `history.json` として保存するローカル機の試験用ストア `HistoryFileStore`（read／initialize＝GENESIS／publish＝APPEND／reconcile の4操作）。移行・採用・解錠・退避（C-4）と日次処理・通知・本番の保存先（S4）には触れていない。S2は1文字も変えていない。
状態：**限定実装の結果。受領・採用の判断ではない。** PR・マージ・Actions・本番・通知・送信はしていない。

## 0. 要約

- 試験対象コミットは `e3d880ad64b08c83985ad641aa16ac6734b380d5`（コード・試験の最終）。この結果文書は、その次の別コミットで1本だけ加える（最後の差分は本書のみ）。
- 別クリーンクローン（完全な履歴、`core.autocrlf=false`、`git checkout`した試験対象）で、**Python 3.10.20／3.11.18／3.12.3／3.13.18 の4版すべてで、既存の13スイート1930件と新規139件が全件合格**（失敗0・error0・終了コード0）。S2のskip 4件はWindows専用の既存のもの。
- 依頼書§5の欠陥注入18項目は**すべて検出**。追加の8項目も検出（§8）。
- 第2版のN-01（手作りの公開値で `mode`／`source` が無いときの生のKeyError）は、`_kind`（§6）で塞ぎ、C3-06の項の試験で確かめた。試行差分のままだと漏れる（追加の変異E1で検出）。
- 実Windows、物理電源断、ネットワークドライブ・同期フォルダ上のroot、unshareによる通信遮断は**未実施**（§11）。

## 1. 実モデルと固定資料

| 項目 | 値 |
|---|---|
| 実モデル設定 | `claude-sonnet-5-5[1m]`（セッション情報の `session_context.model`）。直近に実際に返したモデルは `claude-sonnet-5-5`（`last_served_model`）。effort は `high` |
| 担当 | D-9のとおりSonnet 5.5・high |
| 資料コミット（設計・依頼書・試行差分） | `6ad98521a788297f8db64468337c71767dca7304`（docs/v2-history-local-c3-20261104） |
| 設計のblob | `98ab7dd40b130a6e57538aad2fa581c2f2f079ac`（docs/specs/V2_HISTORY_LOCAL_C3_DESIGN_DRAFT.md） |
| 依頼書のblob | `1aabeb93ad2b84c14790e21fc6bee5a0751b14c5`（docs/tasks/V2_HISTORY_LOCAL_C3_LIMITED_IMPLEMENTATION_REQUEST.md） |
| 試行差分のblob | `83283dfc2d182b489cd26d6c99fcae12a695aca6`（docs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diff） |
| 開始点 | `d6b0332500af8d8d46ddaae6c7fda39ee38a03db`（feat/v2-history-publish-c2-20261103、C-2の保存最終） |
| 試験対象（コード・試験の最終） | `e3d880ad64b08c83985ad641aa16ac6734b380d5`（tree `30d1ef682a3751e465dee8f667e5975be31a231b`） |
| 最終コミット | 本書を1本だけ加えた、ブランチ先端のコミット（その差分は本書のみ。自分のSHAは本書に書けないので、報告とpush後の照合に書く） |

D-1〜D-9は、Rockyさんの「推奨どおり」（2026-11-04T01:14Z）で採用済み（D-4は第2版）。着手は別スレッドへの明示の指示による。

## 2. 変更したもの

| 対象 | 内容 |
|---|---|
| `v2_history_local/`（新規3ファイル） | `__init__.py` 16行、`results.py` 17行、`store.py` 416行（合計449行）。全文はd6b0332→試験対象のコミットの差分にあり、場所は `v2_history_local/` |
| `tests/v2_history_publish/test_c2_09_scope.py` | 18行目の`END`の1行だけ（§5）。コメントの書き換えもその行の中だけ |
| `tests/v2_history_local/`（新規12ファイル） | `c3_helpers.py`、`c3_worker.py`、`test_c3_01`〜`test_c3_10`。`__init__.py`は作っていない |
| `docs/implementation/V2_HISTORY_LOCAL_C3_RESULT.md` | 本書 |

d6b0332→試験対象の差分は16ファイル、+2709／−1行（−1はtest_c2_09の1行）。それ以外の既存ファイルは1つも変えていない（C3-17の試験がblob単位で確かめている）。実行用の補助（試験の実行スクリプト、欠陥注入、模擬、保護参照の照合、各ログ）はリポジトリの外、共有フォルダの `implementation/c3_local_20261104/` に置いた（§12）。

## 3. S2の手順との対応表

S2の `LocalFileStore`（v2_persistence/local/store.py）のクラスと内部メソッドは呼んでいない。OSの呼出しはS2の`FileOps`（変更なし）を`import`して使い、手順の順序とエラーの流儀（`LocalStoreError`のcode・field・phase・rule・cleanup・primary、cleanupの固定語）はS2に合わせて自分のファイルに書いた。

| S2の段階（LocalFileStore） | C-3（HistoryFileStore） | 違い |
|---|---|---|
| `__init__`／`_check_root`（絶対パス、存在するディレクトリ、リンクでない） | 同名のメソッド | 同じ。操作ごとにも確認し直す |
| `_acquire`（O_EXCL、マーカーを書く） | 同名のメソッド | ロック名は`write.lock`（S2と同じで相互排他）。マーカーは`v2_history_local.lock\n`＋乱数。S2は`v2_persistence.local.lock\n` |
| `_owns`／`_release`／`_locked` | 同名のメソッド | 同じ。公開の後の失敗は`store_commit_uncertain`（fieldは`history`） |
| `_scan`（S2の一時ファイルの残りで止める） | `_scan(tolerate_tmp)` | v1の`snapshot.json`があれば`store_layout_unsupported`（v1_only／v1_and_v2）。C-3・S2どちらの一時ファイル名でも`store_artifact_present`。reconcileだけ一時ファイルを許す |
| `_load`（lstat→通常ファイル→読む前後のinode→UTF-8とJSON→S1の検査） | `_load` | バイト列を返すだけ。復号と検査は呼び出し側がC-2の`read_history_bytes`で行う |
| `_discard_own` | 同名のメソッド | 同じ（自分のinodeを確かめて消す、消せなければ`tmp_left`等） |
| `_publish`（保存水準の確認→一時ファイル→全量の書込み→flush→fsync→close→所有確認→replace→ディレクトリfsync） | 同名のメソッド | 同じ順序。符号化がS1の`encode_snapshot`ではなくC-2の`history_bytes` |
| `initialize`（S1の検査、GENESISだけ） | `initialize` | 公開値はCREATEかつGENESISだけ。`check_publication(None, p)`で検査 |
| `commit`（期待headの比較→`append_event`→検査） | `publish` | 公開値はAPPENDだけ。今を`read_history_bytes`で先に検査し、`check_publication(今, p)`でCAS。P-01の分け方（§6） |
| （S2に無い） | `reconcile` | ロックの下でv1の確認と読込みだけを行い、C-2の`reconcile_publication`をそのまま返す |

## 4. 試行の差分との違いと理由

試行差分（設計§7、blob 83283df…）は写していない。ただし3ファイルの構成と手順は設計§3・依頼書と同じなので、中身は試行と同じ形になった部分が多い。試行のstore.pyと最終のstore.pyを機械的に比べた違いは次のとおり（`results.py`は同一、`__init__.py`は1語）。

| 箇所 | 試行 | 最終 | 理由 |
|---|---|---|---|
| `__init__.py`の先頭の文 | `(trial)` | 外した | 試行ではない |
| `store.py`の先頭の説明 | 1文 | 型の厳密な確認・構築しないこと・禁止事項を書いた | 依頼書の固定する振る舞いを文書にした |
| 書き方・元の読み方（`initialize`／`publish`） | `pub.mode`、`pub.source`（公開値のプロパティ） | `_kind(publication, with_source)`：`publication.to_dict()["body"]["mode"]`（初期化は`["source"]`も）を`try/except Exception`で読み、読めなければ`store_publication_invalid`（field＝publication、phase＝args、rule＝shape）、`from None` | **N-01（第2版）**。手作りの値でbodyに`mode`が無いと、試行のコードは生の`KeyError`を外へ出す（`_make`の本体が`mode`なし）。ロックの前に固定のcodeで拒否する |
| 試験 | 範囲試験は仮の1本（STARTがREVの祖先かだけ） | §5.1の完全な範囲試験と受入試験139件 | 試行は受入・欠陥注入・強制終了・正式な範囲試験・名前の整理を含まない（設計§7） |

それ以外のロジック（ロック、走査、読込み、公開、成否不明、保存水準）は試行と同じ。理由は、設計と依頼書の手順と順序が試行と同じで、依頼書が「規則に従う」と求めるものが一致したためで、違う書き方にする根拠が無かったことによる。試行のコードの漏れで、この実装が対処したのはレビューが指摘したN-01だけである。

## 5. test_c2_09の差分全文

`git diff --unified=0 d6b0332 e3d880a -- tests/v2_history_publish/test_c2_09_scope.py`

```
diff --git a/tests/v2_history_publish/test_c2_09_scope.py b/tests/v2_history_publish/test_c2_09_scope.py
index a7c875f..ece0d22 100644
--- a/tests/v2_history_publish/test_c2_09_scope.py
+++ b/tests/v2_history_publish/test_c2_09_scope.py
@@ -18 +18 @@ START = "de6549acb4ecea759cc771300fd0bef59dd5456a"
-END = None          # not accepted yet; the next stage replaces None with the accepted final commit
+END = "d6b0332500af8d8d46ddaae6c7fda39ee38a03db"   # accepted (review a91a9ed); frozen when C-3 began
```

C-2の範囲試験は`REV = END or "HEAD"`なので、これで以後はd6b0332の状態を読む（150件はそのまま合格）。同じコミットでC-3の開いた範囲試験（`START = "d6b0332…"`、`END = None`）を足してあるので、範囲の鎖の試験（test_sc_02）は通る。この1行の差分は、C-3の範囲試験が自分の差分のハンクとして固定している（`PINNED`）。

### 5.1 C-3の範囲試験（test_c3_09_scope.py）

`START = "d6b0332…"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。自分のファイルの範囲の値はHEADから読む。前の段階の差分は書き写していない（pinするのはtest_c2_09の1行の自分のハンクだけ）。

## 6. 実装の要点

- **API**：`HistoryFileStore(root, writable=False, durability=STRICT, *, _ops=None)`と`read()`・`initialize(p)`・`publish(p)`・`reconcile(p)`。`HistoryStoreResult`（status、committed、history、persistence_level、publication_hash）は不変のdataclass。
- **公開値の受け取り**：`type(p) is HistoryPublication`でなければロックの前に`store_publication_invalid`／type。続いて`_kind`で書き方（初期化は元も）を読む（読めなければ`store_publication_invalid`／shape、ロックの前）。initializeはCREATEかつGENESISだけ、publishはAPPENDだけ、違えば`store_operation_unsupported`（`not_genesis`／`not_append`）。その後に書込み可否（`store_read_only`）。順序は型→書き方→操作の種類→書込み可否→ロック→v1→一時ファイル（設計のP-04の順と同じ）。
- **拒否の分け方（P-01）**：publishは今をロックの下で`read_history_bytes`で先に検査（壊れていれば`history_invalid`等をそのまま返す）。その後に`check_publication`を呼び、`publication_invalid`・`publication_stale`はそのまま返し、それ以外の`CoreError`は`store_candidate_invalid`（field＝publication、phase＝candidate）に包む。initializeの`check_publication`も同じ扱い。
- **v2_history_publishから取る名前**は8つだけ（`APPEND`、`CREATE`、`GENESIS`、`HistoryPublication`、`check_publication`、`history_bytes`、`read_history_bytes`、`reconcile_publication`）。`Reconciliation`は取らない。`_make`・`_of`・`_wrap`・`object.__new__`・公開値の構築は無い（静的に確認）。
- **書込みと成否不明**：replaceの呼出し以後の失敗は`store_commit_uncertain`（phase＝replace／dir_sync／lock_ownership／lock_release、field＝history）。自分の一時ファイル以外は消さず、他人のロックには触らない。
- **照合**：ロックの下でv1の確認と`history.json`の読込み（無ければNone）だけ。一時ファイルの残りでは止まらず、ロックの残りでは`store_busy`で止まる。読取り専用のストアでもできる。再試行・解錠・掃除はしない。

## 7. 受入とテスト名の対応

新規は139件（`tests/v2_history_local/test_c3_*.py`）。件数はIDごとの機能項目で、期待値はC-2の`file_bytes`・`indented`・各ケース（`day_case`等）と、設計§3の順序・§5.1の表から作った（実装の出力のコピーではない）。

| ID | 試験（ファイル：クラス．名前の要旨） |
|---|---|
| C3-01 回帰 | 既存13スイート1930件（core 197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150）。§9 |
| C3-02 構成と値 | test_c3_01：`RootArguments`（相対・存在しない・ファイル・リンク・NUL・空・型）、`OtherArguments`（durability、writable、repr・属性・エラーにパスが無い）、`ResultValue`（不変） |
| C3-03 初期化 | test_c3_02：`Initialize`（INITIALIZED、候補と同じバイト、history.json以外が残らない、二重はalready_initialized、壊れたファイルもinitialized、store_read_only） |
| C3-04 読込み | test_c3_02：`Read`（未初期化、リンク・ディレクトリ・入れ替わり、UTF-8・JSON・BOM・切り詰め・hash変更、字下げ付き、毎回ロックの取得と解放） |
| C3-05 公開 | test_c3_02：`Publish`（DAILY・RESOLUTION・RESTART・RESTORE［CONSUME入りを1つ］でPUBLISHED、2回目と別の書込みの後はstale、未初期化、字下げ付きは正規化、2回続けて追記） |
| C3-06 受け取らない値 | test_c3_03：`WrongTypes`（dict・Historyなど11種×3操作で、ロックの作成が記録に無い）、`WrongKinds`（CREATE・MIGRATION・ADOPTION）、`HandMadeBodiesWithoutMode`（**N-01**：modeが無い、initializeはsourceも、bodyが辞書でない値。ロックを取らない） |
| C3-07 拒否の分け方 | test_c3_04：`BrokenCurrent`（壊れた今→history_invalid、変わらない）、`BadCandidate`（手作りの候補が無効→store_candidate_invalid、initializeも） |
| C3-08 rootの形 | test_c3_05：`Table.test_every_cell`（4操作×7状態：空、history.jsonだけ、v1だけ、両方、C-3の一時ファイル、S2の一時ファイル、ロック）、ほかの名前は見ない、検査の順 |
| C3-09 ロック | test_c3_06：`Busy`、`Marker`、`Ownership`（公開の前はlock_ownership_lost、後はcommit_uncertain、他人のロックはそのまま）、`Release`（lock_left）、`ExcludesS2`（実のS2と両方向でstore_busy） |
| C3-10 書込みの手順と故障 | test_c3_07：`Procedure`（呼出し列が設計§3の順序、短い書込み）、`Faults`（ロック作成・tmp_create・write・flush・file_sync・close・replace・dir_syncの各故障、tmp_left等）。lock_releaseはtest_c3_06 |
| C3-11 成否不明と照合 | test_c3_08：replaceの前→NOT_PUBLISHED（再publish可）、後・dir_sync→PUBLISHED、その後の公開→PUBLISHED_THEN_EXTENDED、別内容・壊れた今・無い→CONFLICT、一時ファイルの残りでも答える、v1・ロックで止まる、読取り専用でもできる |
| C3-12 保存水準 | test_c3_07：`Levels`（STRICTはfileとdirのfsync、FILE_SYNC_ONLYはdirを呼ばない、Windows strictはwindows_strict、probeの失敗はdirectory_sync、どれもhistory.jsonと一時ファイルに触れず） |
| C3-13 プロセス | test_c3_10：`Contention`（6プロセス×15回、成功1回）、`ForcedStop`（SIGKILL：tmp後・replace前／replace後。lockの残り→手で外した後の挙動） |
| C3-14 情報の漏れ | test_c3_07：`NoLeak`（15の段階×故障の前後で、パス・秘密・OSの文が`str`・`repr`・属性・cleanupに出ない、`__cause__`・`__context__`も無い）、test_c3_01：`test_errors_show_no_path` |
| C3-15 公開値の受け取りの監査 | test_c3_09：`Constructors`、`RuntimeAudit.test_the_names_taken_from_the_publication_package_are_the_eight_of_the_design`、`TestFiles.test_the_private_constructor_is_used_to_make_values_by_hand_in_two_files_only`（test_c3_03とtest_c3_04だけ） |
| C3-16 範囲の値 | test_c3_09：`Chain`、`FilesChanged.test_the_one_modified_test_is_the_one_pinned_line` |
| C3-17 自分の範囲 | test_c3_09：`FilesChanged`（MはC-2の範囲試験だけ、Aは許可された名前だけ、他はblob単位で同じ、パッケージは3ファイル） |
| C3-18 範囲監査 | test_c3_09：`RuntimeAudit`（import、os、FileOps経由）、`TestFiles`（import、時計・環境変数・ネットワーク無し、子プロセスは`sys.executable`＋c3_worker.pyだけ、ファイルを開くのは2つのヘルパーだけ、範囲試験は作業ツリーを読まない） |
| C3-19 次の段階の模擬 | §10（試験ではなく手順。結果をここに記す） |

## 8. 欠陥注入（依頼書§5の18項目＋追加）

試験対象 `e3d880a` を別クリーンクローンに置き、使い捨てのworktreeで1件ずつ壊して（範囲試験はHEADを読むので変異ごとにコミット）、新規スイートを実行した（Python 3.12.3）。スクリプトは `implementation/c3_local_20261104/mutate.py`、結果は同じ場所の `mutation_out.json`・`mutation_out.txt`。分類は検出／等価／未検出／準備失敗。

| # | 変異 | 結果（失敗した試験の数） | 失敗した試験（記録した先頭4件の範囲） |
|---|---|---|---|
| 1 | 走査：v1のファイルの確認を外す | 検出（12） | test_c3_05 |
| 2 | 走査：S2の一時ファイル名の確認を外す | 検出（4） | test_c3_05 |
| 3 | 照合：一時ファイルの残りで止める | 検出（7） | test_c3_05、test_c3_08、test_c3_10 |
| 4 | 公開：今のread_history_bytesを先に呼ばない | 検出（6） | test_c3_04 |
| 5 | 公開：history_invalidをそのまま返す | 検出（2） | test_c3_04 |
| 6 | 公開：CREATEも受け付ける | 検出（3） | test_c3_03 |
| 7 | 初期化：GENESIS以外のCREATE（MIGRATION）も受け付ける | 検出（2） | test_c3_03 |
| 8 | 公開値の型の確認をロックの後へ移す | 検出（24） | test_c3_03（C3-06） |
| 9 | replaceの前のロックの所有確認を外す | 検出（4） | test_c3_06、test_c3_07 |
| 10 | 成否不明の印をreplaceの後で立てる | 検出（1） | test_c3_06（replaceと解放の同時の失敗） |
| 11 | STRICTでディレクトリのfsyncを省く | 検出（10） | test_c3_07 |
| 12 | Windowsのstrictを受け付ける | 検出（2） | test_c3_07 |
| 13 | 後片付けでinodeの一致を確かめずに消す | 検出（1） | test_c3_07（取り替えられた一時ファイル） |
| 14 | ロックの解放でマーカーの一致を確かめない | 検出（6） | test_c3_06 |
| 15 | 読込みで読む前後のinode比較を外す | 検出（1） | test_c3_02（読込み） |
| 16 | ロックの名前をS2と違う名前にする | 検出（40） | test_c3_06（相互排他）、test_c3_02、test_c3_05ほか |
| 17 | 範囲試験：新しい範囲試験が作業ツリーを読む（`open`） | 検出（2） | test_c3_09（`TestFiles`） |
| 18 | 範囲試験：test_c2_09の固定の行を変える | 検出（27） | test_c3_09（失敗数27は新規・C-2の範囲試験・範囲の鎖の3スイートの合計） |
| E1 | 追加：N-01の守り（`_kind`の`except`）を外す | 検出（16） | test_c3_03 |
| E2 | 追加：history.jsonがリンク・ディレクトリでも読む | 検出（2） | test_c3_02 |
| E3 | 追加：進まない書込みを許す（無限ループの守りを外す） | 検出（1） | test_c3_07 |
| E4 | 追加：ディレクトリfsyncの確認（probe）を省く | 検出（6） | test_c3_07 |
| E5 | 追加：型の厳密な確認を`isinstance`にする | 検出（2） | test_c3_03、test_c3_09 |
| E6 | 追加：照合がロックを取らない | 検出（7） | test_c3_05、test_c3_06、test_c3_08 |
| E7 | 追加：初期化で空のrootの確認を外す | 検出（4） | test_c3_02、test_c3_05、test_c3_08 |
| E8 | 追加：ロックのマーカーをS2と同じにする | 検出（1） | test_c3_06 |

検出18／18、準備失敗0、未検出0、等価の判定は0（等価と判断した変異は無い）。追加はE1〜E8の8項目がすべて検出。途中の実行で入れていたもう1つの追加の変異（候補を`data if False else …`と書き換えるもの）は、書き換えても式の値が変わらない無効な変異（実質は等価）だったので、スクリプトから外した。変異10（成否不明の印）は、replaceと解放が同時に失敗する組合せでだけ差が出る。その試験2件（test_c3_06）は、欠陥注入の前に、この組合せを狙って足したもの。

## 9. 全スイートの結果

別クリーンクローン（GitHubから取った完全な履歴＝shallowでない、`core.autocrlf=false`。試験対象`e3d880a`はまだpushしていなかったので、ローカルの実装リポジトリから`git fetch`で取り込んで`checkout`した。作業ツリーは別のディレクトリ）。`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover -s tests/<dir> -p "test_*.py"`（新規は`test_c3_*.py`、C-1は`test_c1_*.py`、C-2は`test_c2_*.py`）。ログは `implementation/c3_local_20261104/final_runall_py<版>.log`。

| スイート | 件数 | 3.10.20 | 3.11.18 | 3.12.3 | 3.13.18 |
|---|---|---|---|---|---|
| コア | 197 | OK | OK | OK | OK |
| 保存 | 170 | OK | OK | OK | OK |
| S2 | 113 | OK（skip 4） | OK（skip 4） | OK（skip 4） | OK（skip 4） |
| S3-A | 176 | OK | OK | OK | OK |
| B-1 | 230 | OK | OK | OK | OK |
| B-2 | 173 | OK | OK | OK | OK |
| B-3 | 109 | OK | OK | OK | OK |
| B-4 | 165 | OK | OK | OK | OK |
| B-5a | 131 | OK | OK | OK | OK |
| B-5b | 170 | OK | OK | OK | OK |
| 範囲の鎖 | 34 | OK | OK | OK | OK |
| C-1 | 112 | OK | OK | OK | OK |
| C-2 | 150 | OK | OK | OK | OK |
| **既存の計** | **1930** | 失敗0・error0 | 失敗0・error0 | 失敗0・error0 | 失敗0・error0 |
| **C-3（新規）** | **139** | OK（skip 0） | OK（skip 0） | OK（skip 0） | OK（skip 0） |

どの実行も終了コード0。S2のskip 4はWindows専用の既存の試験。新規のskipは0（Linuxで強制終了・リンクの試験が動いた）。Python 3.10.20は環境に無かったため、`uv python install 3.10`（リポジトリの外）で入れたcpython 3.10.20を使った。3.11.18／3.12.3／3.13.18は環境にあったもの。依存・設定・workflowは変更していない。

そのほかの確認：
- 同じコミットの`git archive`のツリー（`.git`なし）：範囲の鎖34は33skip、C-1 112件のうち実行された107件は22skip（Gitを読む試験がskip）、C-2 150は28skip、C-3 139は25skip。いずれも失敗0（ログ `archive_tree_skips.log`）。
- ローカルの実装リポジトリで新規スイートを6回繰り返し実行（3.12）：毎回139件OK。
- `__pycache__`は`git add`の前に無いことを確認（`PYTHONDONTWRITEBYTECODE=1`）。

## 10. C3-19 次の段階の模擬

`implementation/c3_local_20261104/next_stage_sim.sh`（C-2の同じ形）。試験対象のコミットの使い捨てworktreeで、コミットを重ねる。pushしない。出力は `next_stage_sim_out.txt`（クローン上、3.12.3）。

1. [A] 試験対象のそのまま：範囲の鎖34、C-1 112、C-2 150、C-3 139、すべてOK。
2. [B] (1)だけ：C-3の範囲試験の`END`を試験対象のSHAに替える（1行）。**範囲の鎖34のうち2件が失敗**（開いた範囲が0本になるため。依頼書・設計のとおりの想定。C-1・C-2・C-3の各スイートは合格）。
3. [C] (1)に加えて、仮の開いた範囲試験1本（START＝試験対象、END＝None）を足す：範囲の鎖34、C-1 112、C-2 150、C-3 139、すべてOK。

## 11. 保護参照

依頼書§7の78参照＋資料ブランチdocs/v2-history-local-c3-20261104（6ad9852）の計79参照を、`git ls-remote origin`の完全SHAで照合（`implementation/c3_local_20261104/refcheck.py`）。
- 開始時：79件すべて一致（`refs_start.txt`）。
- push前（試験対象の試験の後）：79件すべて一致（`refs_final_before_push.txt`）。
- push後：報告に記す（push後の確認は本書の保存より後なので、本書には書けない）。

## 12. 未実施・限界

- **実Windows**：C-3のWindows専用の確認（strictの拒否の実機、ロック・一時ファイル名の扱い）、およびWindowsでの新規N＋1454件の実行は**未実施**。Windows strictの拒否は`is_windows`を替えた記録の子クラスで動作だけ確かめた。強制終了（SIGKILL）の試験はWindowsではskipする。他者の結果や他のOSで代用していない。
- **物理電源断**、ネットワークドライブ・同期フォルダ上のroot、unshareによる通信遮断の試験：未実施（試験は同じプロセス内でsocketを無効にし、子プロセスにも同じ設定をしているだけ）。
- **ユーザーPC**：未実施。
- 設計§8の既知の制限（S2の書き手は`write.lock`の中身を見ない、一時ファイル・ロックの残りの片付けはC-4まで無い、実Windows・電源断は未確認、Pythonの内部を直接呼べば公開値の形の値を作れる）はそのまま残る。
- 範囲外：C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03、B-4§7.1、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02、設計レビュー213bcb7の提案P-01〜P-07（任意、第2版で反映していない）には広げていない。
- 補助スクリプト・ログはリポジトリの外（共有フォルダ `implementation/c3_local_20261104/`：`runall.sh`、`mutate.py`、`mutation_out.json`、`mutation_out.txt`、`next_stage_sim.sh`、`next_stage_sim_out.txt`、`refcheck.py`、`refs_*.txt`、`final_runall_py*.log`、`archive_tree_skips.log`）。リポジトリには入れていない。
- モデル別の利用量は未計測。

## 13. 次の判断

- 受領と、その後のC-4（移行・採用の実行、明示解錠、退避）の依頼書作成は別の判断（この限定実装はそれを含まない）。
- 実Windows・ユーザーPCでの確認を、受領の条件にするか、C-4の前に回すかは主担当の判断。
