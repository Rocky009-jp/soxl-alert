# V2 C-3 v2ローカル正本 限定実装依頼書

作成日：2026-11-04（日本時間）。版：**第2版**（初版fd3c5bbへの設計レビュー213bcb7の通常N-01だけを反映。§3の1文、C3-06の1項、C3-15の許可。ほかは初版と同じ）。
状態：**第2版・D-1〜D-9採用済み（Rocky「推奨どおり」2026-11-04T01:14Z、設計レビュー213bcb7の推奨。D-4は第2版で採用）。限定実装は、別スレッドへの明示の着手指示で始める。本書の保存だけでは実装を始めない。**
対になる設計はdocs/specs/V2_HISTORY_LOCAL_C3_DESIGN_DRAFT.md（以下「設計」）。本段階はC-3（v2履歴を1つのファイルhistory.jsonとして保存する、ローカル機の試験用ストア）だけを実装する。C-4（移行・採用の実行、明示解錠、退避）、S4（日次処理・通知・本番の保存先）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **d6b0332500af8d8d46ddaae6c7fda39ee38a03db**（feat/v2-history-publish-c2-20261103、C-2の保存最終） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-history-local-c3-20261104）の設計とdocs/specs/V2_HISTORY_LOCAL_C3_TRIAL_20261104.diff。SHAと3つのblobを開始報告に記録 |
| C-2の受領 | 実装レビューa91a9ed31481e97cc8b56c2396f86d957fa567e0（§3のP-01、§5の引継ぎ） |
| C-2の設計（第2版） | 081637e95160a23aab5ea0fc3a2edd01976abba4 §5・§6.3・§8 |
| S2のローカル保存 | d6b0332のv2_persistence/local（受領済み・変更しない）と試験tests/v2_persistence_local/ |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6（D-3）、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

ユーザーが設計§8のD-1〜D-9を採用し、この限定実装への移行を指示した後にのみ、新規実装ブランチをd6b0332から作る（ブランチ名の案：feat/v2-history-local-c3-YYYYMMDD）。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-9）。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。未承認のD-1〜D-9を採用されたと書かない。運用方針は日足のみ（分足・NBBOを前提にしない）。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history_local/ 新規 | 設計§2.3の3ファイル（`__init__.py`、`results.py`、`store.py`）。分け方を変える必要があれば結果文書に理由を書く。5ファイルを超えない |
| tests/v2_history_publish/test_c2_09_scope.py | 設計§6.1の`END`の1行だけ。コメントの書き換えはその行の中だけ |
| tests/v2_history_local/ 新規 | test_c3_\*.py、c3_helpers.py、c3_worker.py（子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_HISTORY_LOCAL_C3_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、既存の試験・変異・fixtures・ヘルパー（l_helpers、worker.py、c2_helpers、sc_helpersを含む）、範囲試験（test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09、test_c2_09の上の1行以外）、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
既存パッケージの公開名（\_\_all\_\_）は変えない。
C-4（移行・採用の実行、明示解錠、一時ファイル・ロックの片付け、退避、quarantine/）、S4（日次処理の組立て、通知、定時実行、本番の保存先）、C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03、B-4§7.1の既知の制限、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02へ広げない。範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 固定する振る舞い

- **API**（設計§4.3）：`HistoryFileStore(root, writable=False, durability=STRICT, *, _ops=None)`と、`read()`・`initialize(publication)`・`publish(publication)`・`reconcile(publication)`の4操作、`HistoryStoreResult`（status、committed、history、persistence_level、publication_hash、不変）。durabilityの値と保存水準の固定語はS2のもの。
- **S2との関係**（設計§3）：S2の`FileOps`を変えずに使い、`_ops`を試験の継ぎ目にする。`LocalFileStore`のクラス・内部メソッドは呼ばない。手順の順序とエラーの流儀（`LocalStoreError`のcode・field・phase・rule・cleanup・primary、cleanupの固定語）はS2と同じ。パス・OSのエラー文・入力値をエラーに入れない。
- **rootの形**（設計§4.1、§4.2）：`history.json`、`write.lock`（S2と同名、中身は`v2_history_local.lock\n`＋乱数）、`.history.<32桁の16進>.tmp`。状態表の各セルのとおり（v1のファイル→store_layout_unsupported／v1_only・v1_and_v2、一時ファイルの残り→store_artifact_present［reconcileを除く］、ロック→store_busy、ほかの名前は見ない）。
- **公開値の受け取り**（設計§4.3、D-7）：`type(p) is HistoryPublication`でなければロックの前にstore_publication_invalid／type。initializeはCREATEかつGENESISだけ、publishはAPPENDだけ、違えばstore_operation_unsupported（not_genesis／not_append）。v2_history_localは`_make`・`_of`・`object.__new__`・HistoryPublication／Reconciliationの構築をしない。書き方・元は、形の誤りで例外が漏れない方法で読み、読めなければロックの前にstore_publication_invalid（rule＝shape）とする（第2版、レビューN-01）。
- **拒否の分け方**（設計§4.4、C-2の提案P-01）：publishは今をread_history_bytesで先に検査し、その後でcheck_publicationを呼ぶ。check_publicationのpublication_invalid・publication_staleはそのまま返し、それ以外のCoreErrorはstore_candidate_invalid（field＝publication、phase＝candidate）。initializeのcheck_publicationも同じ扱い。
- **書込みと成否不明**（設計§5.1）：S2の§6.3の順序。replaceの呼出し以後の失敗はstore_commit_uncertain（phase＝replace／dir_sync、field＝history）。自分の一時ファイル以外は消さない。他人のロックには触らない。
- **照合**（設計§5.2）：reconcileはロックの下で、v1の確認と読込みだけを行い、C-2のreconcile_publicationをそのまま返す。一時ファイルの残りでは止まらない。読取り専用のストアでもできる。自動の再試行・解錠・掃除をしない。
- **保存水準**（設計§5.3）：STRICT／FILE_SYNC_ONLY。Windowsのstrictはwindows_strict、ディレクトリのfsyncの確認の失敗はdirectory_sync。
- **戦略式・履歴の規則を書かない**：履歴の検査・公開値の検査・照合は、既存のread_history_bytes・check_publication・reconcile_publicationだけで行う。
- **範囲試験**（設計§6）：C-3の範囲試験は`START = "d6b0332…"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。自分のファイルの範囲の値はHEADから読む。前の段階の差分を固定文字列で書き写さない。test_c2_09の1行はC-3自身の差分のハンクとして固定する。試験が書くのはtempfileの一時ディレクトリだけ。子プロセスは競合・強制終了の試験だけで、`sys.executable`とtests/v2_history_local/の本体だけを使う。

## 4. 受入条件 C3-01〜C3-19

各IDは機能項目であってテスト件数ではない。新規Nは実測する。期待値はC-2の関数（publish_\*、history_bytes、read_history_bytes）や試験側の独立の計算から作り、実装の出力をコピーしない。

| ID | 必須確認 |
|---|---|
| C3-01 回帰 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150の計1930件を、完全なクローンで維持（test_c2_09の1行の固定を含む。件数は同じ） |
| C3-02 構成と値 | 引数の誤り（root：相対・存在しない・ファイル・リンク・NUL・空・型、durability、writableの型）がstore_root_invalid／store_config_invalid。repr・属性にパスが出ない。HistoryStoreResultが不変 |
| C3-03 初期化 | publish_genesisの値でINITIALIZED、ファイルがhistory_bytes(候補)と同じバイト、history.json以外が残らない。二重の初期化はalready_initialized。読取り専用はstore_read_only |
| C3-04 読込み | 未初期化、history.jsonがリンク・ディレクトリ・読む間に入れ替わる、UTF-8・JSON・BOM・無効な履歴（既存のhistory_invalid等）。字下げ付きの有効なファイルを読む。読込みも毎回ロックを取り、解放する |
| C3-05 公開 | DAILY・RESOLUTION・RESTART・RESTOREの公開値（C-2の作り手で作る。RESTOREはC-1のCONSUMEを含む例を1つ）でPUBLISHED、ファイルが候補の正規化バイト。同じ公開値の2回目・別の書込みの後はpublication_stale。未初期化はstore_uninitialized。字下げ付きの今に公開すると正規化して書く |
| C3-06 受け取らない値 | dict・確認結果・Historyなどの型はstore_publication_invalid（ロックを取らない：ロックの作成が呼ばれないことをFileOpsの記録で確かめる）。CREATE・REPLACEのpublish、GENESIS以外のinitialize、MIGRATION・ADOPTIONはstore_operation_unsupported。body に mode（初期化では source も）が無い手作りの値（`_make`）は、publish・initializeとも固定のcodeで拒否し、ロックを取らない（第2版、N-01） |
| C3-07 拒否の分け方（P-01） | 壊れた今（末尾を切る、記録のhashを変える）にpublish→今の検査のcode（history_invalid等）。正しい今に、候補が無効な手作りの値（`_make`、試験のこの1本だけで使う）→store_candidate_invalid。どちらもファイルは変わらない |
| C3-08 rootの形 | 設計§4.2の表の全セル（4操作×6状態）。S2の一時ファイル名の残りも止まる。quarantine/等ほかの名前は見ない |
| C3-09 ロック | store_busy（ファイル・ディレクトリ・壊れたリンクがロックの名前にある）。自分のマーカーを書く。公開の前に所有を失ったらstore_lock_ownership_lost（一時ファイルを消す）、公開の後ならstore_commit_uncertain。他人のロックはそのまま。解放の失敗はlock_left。S2のLocalFileStoreとC-3が同じrootで互いにstore_busyになる（両方向） |
| C3-10 書込みの手順と故障 | 正常時のFileOpsの呼出し列が設計§3の順序と同じ（記録の子クラス）。各段階（ロックの作成と書込み、tmp_create、短い書込み、write、flush、file_sync、close、replace、dir_sync、lock_release）の故障で、code・phase・cleanupが設計§5.1の表のとおり。故障の後に自分の一時ファイルが残らない（消せない場合はtmp_left） |
| C3-11 成否不明と照合 | replaceの前の故障→reconcileがNOT_PUBLISHED、replaceの後の故障・dir_syncの故障→PUBLISHED、その後に別の公開→PUBLISHED_THEN_EXTENDED、別の内容→CONFLICT、壊れた今→CONFLICT。一時ファイルの残りでも答える。v1のファイルでは止まる。ロックの残りはstore_busy。読取り専用のストアでもできる |
| C3-12 保存水準 | STRICTはファイルとディレクトリのfsyncを呼ぶ、FILE_SYNC_ONLYはディレクトリのfsyncを呼ばない。Windowsのstrict（is_windowsを替えた記録の子クラス）はwindows_strict、確認の失敗はdirectory_sync。どちらもhistory.jsonと一時ファイルに触れず、ロックは解放される |
| C3-13 プロセス | 4つ以上の子プロセスが同じrootで公開を競うと、成功は同じ日に1回だけで、ほかはstore_busy・publication_stale・publication_refusedのどれか。最後のファイルが有効。強制終了（SIGKILL。Windowsでは試験をskip）を、一時ファイルを書いた後・replaceの前とreplaceの後で起こし、次の操作がstore_busy（ロックの残り）になること、試験がロックを手で外した後は一時ファイルの残りでstore_artifact_present（replaceの前）または正常（replaceの後）になること、history.jsonが前か後のどちらかの有効な履歴であること |
| C3-14 情報の漏れ | 故障の例外にパスや秘密らしい文字列を入れても、エラーのstr・repr・属性・cleanupに出ない（S2の試験と同じ形） |
| C3-15 公開値の受け取りの監査 | 静的に：v2_history_localに`_make`・`_of`・`object.__new__`・HistoryPublication(…)・Reconciliation(…)の呼出しが無い。v2_history_publishからimportする名前が設計§2.3の一覧だけ。試験で`_make`を呼ぶのはC3-07の1ファイルと、C3-06のN-01の項の試験だけ |
| C3-16 範囲の値 | test_c2_09のENDがd6b0332で、差分は1行だけ。範囲の鎖がadfdf765→…→de6549a→d6b0332→（C-3、END=None）で、開いた範囲はC-3の1本だけ |
| C3-17 自分の範囲 | d6b0332→REVで、Mはtest_c2_09だけ（1行のハンクと一致）。Aはv2_history_local/、tests/v2_history_local/、結果文書だけ。それ以外はblob単位で同じ |
| C3-18 範囲監査 | 新しいランタイムのimportが設計§2.3の一覧だけ（os、secrets、stat、dataclasses、typingと、v2_core・v2_persistence.local・v2_history_publishの名前）。ネット・時計・threading・subprocess・環境変数・hashlib・新しい依存が無い。osの使い方はパスの組立て（join、dirname、abspath、isabs、realpath、fspath）だけで、ファイル操作はFileOps経由。新しい試験はネットワーク・時計による順序付け・環境変数を使わず、書込みは一時ディレクトリだけ、子プロセスは§3のものだけ |
| C3-19 次の段階の模擬 | 使い捨てのコミットで、(1) C-3の範囲試験の`END`だけを自分の試験対象のSHAに替え（1行）、(2) 仮の開いた範囲試験1本を足し、test_sc_\*・test_c1_\*・test_c2_\*・test_c3_\*が通ること。結果文書に手順と結果を書く（そのコミットはpushしない） |

## 5. 限定欠陥注入

次の項目を1件ずつ壊し、試験の感度を確認する。検出・等価・未検出・準備失敗を分け、等価には根拠を書く。

1. 走査：v1のファイルの確認を外す。
2. 走査：S2の一時ファイル名の確認を外す。
3. 照合：一時ファイルの残りで止める（tolerateを外す）。
4. 公開：今のread_history_bytesを先に呼ばない（P-01の順序）。
5. 公開：check_publicationのhistory_invalidをそのまま返す（store_candidate_invalidに包まない）。
6. 公開：CREATEの公開値も受け付ける。
7. 初期化：GENESIS以外のCREATE（MIGRATION）も受け付ける。
8. 公開値の型の確認をロックの後へ移す（C3-06で検出されること）。
9. replaceの前のロックの所有確認を外す。
10. 成否不明の印（published）をreplaceの後で立てる。
11. STRICTでディレクトリのfsyncを省く。
12. Windowsのstrictを受け付ける。
13. 一時ファイルの後片付けで、inodeの一致を確かめずに消す。
14. ロックの解放で、マーカーの一致を確かめない。
15. 読込みで、読む前後のinodeの比較を外す。
16. ロックの名前をS2と違う名前にする（C3-09の相互排他で検出されること）。
17. 範囲試験：新しい範囲試験が作業ツリーを読む（REVでなくopen）。
18. 範囲試験：test_c2_09の固定の行を変える。

## 6. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使う。依存/設定/workflowを変更しない。
core.autocrlf=falseの別クリーンクローン（完全な履歴）で最終コードを試験する。`git archive`のツリーでのskipの件数は別に記録する。`git add`前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
Windowsがある場合は新規N＋C-2 150＋C-1 112＋範囲の鎖34＋B-5b 170＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行する（合計は新規N＋1454）。C-3のWindows専用の確認（strictの拒否、ロック・一時ファイル名の扱い）は、実Windowsで行うまで未実施と書く。未実施のOSやユーザーPCを他者の結果で代用しない。物理電源断は未実施と書く。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_local -p "test_c3_*.py" -v

結果文書には、実モデル設定/effort、固定資料の完全SHA/3つのblob、開始/試験/最終SHA、新しいランタイムの全文の場所と行数、S2の手順との対応表（S2のどの段階がC-3のどこか）、test_c2_09の差分全文、試行の差分（設計§7）との違いとその理由、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、変異一覧・分類、C3-19の手順と結果、未実施を記す。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、C-4・S4へ進まない。

## 7. 読取専用の保護参照

次の78参照を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-history-local-c3-20261104も、受け取った版の完全SHAを1本加える（実装時は79参照）。

| 参照 | 完全SHA |
|---|---|
| main | 31144d9b6af8a6c920ad53c395cd550e8c48a7fa |
| feat/interim-notification-20261026 | 920e69571cf4feda09f3f2f560e96fcb9cb09d50 |
| docs/v2-roadmap-20261023 | 647aeac34cde0d01ec27174f7620aff1724af0e1 |
| feat/v2-offline-core-20261027 | 1a54a8573023af9490017b02a8b6458f061031c7 |
| feat/v2-core-state-checks-20261028 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| docs/v2-market-state-recovery-20261027 | b43205ce1a53e4560fb85f9cfb715c72a1132a75 |
| docs/v2-persistence-domain-20261028 | 425df80d04b116e25e481184069b89bed1380c3a |
| docs/v2-persistence-domain-s1-receipt-20261028 | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| feat/v2-persistence-domain-offline-20261028 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| fix/v2-persistence-domain-s1-review-20261028 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| docs/v2-persistence-domain-s1-fix-receipt-20261028 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048 |
| fix/v2-core-fg-numeric-overflow-20261028 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| docs/v2-core-fg-overflow-receipt-20261028 | a235b7607f5624ed84ba5427ac0f44029f41d262 |
| docs/v2-local-store-s2-20261028 | 73cec624cb73205ac63ca92e26df2b6f70019b16 |
| feat/v2-local-file-store-s2-20261028 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| docs/v2-local-store-s2-receipt-20261028 | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| fix/v2-local-store-s2-review-20261028 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| docs/v2-local-store-s2-fix-receipt-20261028 | 1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a |
| docs/v2-user-pc-tests-20261028 | aa21dbe85a133c61e8c011a6f78db1b23af0fb13 |
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| docs/v2-history-s3b4-review-20261102 | 814b86190562475286300d7e6df3a749a9140331 |
| fix/v2-history-restore-plan-s3b4-review-20261102 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| docs/v2-history-s3b4-fix-rereview-20261102 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| docs/v2-history-s3b5-20261102 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136 |
| docs/v2-history-s3b5-review-20261102 | 842d44b192a03531f6d3cb896d8281733814899f |
| docs/v2-history-s3b5-v2-rereview-20261102 | 6a7210c2e278e604b953acf904cf9e796c2ce710 |
| feat/v2-history-diagnose-s3b5a-20261102 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6 |
| docs/v2-history-s3b5a-review-20261102 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9 |
| docs/v2-history-s3b5b-20261102 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |
| feat/v2-history-adopt-s3b5b-20261103 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01 |
| docs/v2-history-s3b5b-review-20261103 | 92630a3d5233f14900c7472dc754850701a56b61 |
| fix/v2-history-adopt-s3b5b-review-20261103 | b626c98af5f01bc94e7b41d86aadde9663695eb9 |
| docs/v2-history-s3b5b-fix-rereview-20261103 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b |
| docs/v2-scope-range-freeze-20261103 | 08072cc47aa12340ed947d40f02ca8741a4060d6 |
| feat/v2-scope-range-freeze-20261103 | dda7eb706637adc5f6dd37513e4b6ca360fde2ba |
| docs/v2-scope-range-freeze-review-20261103 | fa4b232810569f4512d09f244ef50f9685ff0c95 |
| fix/v2-scope-range-freeze-review-20261103 | bfbde7a7854bf91a77fb58737c24b19c6507453a |
| docs/v2-scope-range-freeze-fix-rereview-20261103 | 9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d |
| docs/v2-consume-c1-review-20261103 | b473db46ad3dbf3ad76fa76f50c49b03b558936d |
| docs/v2-consume-s3c-20261103 | a6340c3937092e4cb658913b9acfb4973a084326 |
| feat/v2-history-consume-c1-20261103 | de6549acb4ecea759cc771300fd0bef59dd5456a |
| docs/v2-history-publish-c2-20261103 | 9dd64b8eb07ad35dd23c011ed2dbb1196307f542 |
| docs/v2-history-publish-c2-review-20261103 | a6e783e57c1de5dd92e6b43cfc416a1d79a672eb |
| docs/v2-history-publish-c2-impl-review-20261103 | a91a9ed31481e97cc8b56c2396f86d957fa567e0 |
| docs/v2-history-publish-c2-revision-20261103 | 081637e95160a23aab5ea0fc3a2edd01976abba4 |
| feat/v2-history-publish-c2-20261103 | d6b0332500af8d8d46ddaae6c7fda39ee38a03db |

## 8. 採用単位

設計§8のD-1（C-3の範囲）、D-2（S2との関係）、D-3（rootの形）、D-4（操作と拒否、C-2の提案P-01）、D-5（成否不明と照合）、D-6（保存水準）、D-7（公開値の受け取り）、D-8（範囲試験）、D-9（C-3の限定実装、Sonnet 5.5・high）と、本書の変更境界/受入/欠陥注入/結果保存を一組で判断する。
今回の文書作成と、設計§7の一時環境の試行は、その採用ではない。C-2の受領をC-3の実装承認にしない。C-4・S4の実装承認も含まない。
