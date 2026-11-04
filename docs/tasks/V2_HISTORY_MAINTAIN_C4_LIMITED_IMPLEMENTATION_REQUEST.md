# V2 C-4 保守操作（移行・採用・明示解錠） 限定実装依頼書

作成日：2026-11-04（日本時間）。版：初版。
状態：**初版・採否判断待ち・未承認。本書の保存だけでは実装を始めない。**
対になる設計はdocs/specs/V2_HISTORY_MAINTAIN_C4_DESIGN_DRAFT.md（以下「設計」）。本段階はC-4（C-3のストアが止まった状態を、人の手順でC-3の通常の状態へ戻す保守操作：明示解錠、v1→v2移行の実行、prefix採用の実行、退避と中断後の再開）だけを実装する。S4（日次処理・通知・本番の保存先・定時実行）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a**（feat/v2-history-local-c3-20261104、C-3の保存最終） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-history-maintain-c4-20261104）の設計とdocs/specs/V2_HISTORY_MAINTAIN_C4_TRIAL_20261104.diff。SHAと3つのblobを開始報告に記録 |
| C-3の受領 | 実装レビュー2049e1056f76e606343c3eb0fbbe82e531988ca6（§3のP-02、§5の引継ぎ） |
| C-3の設計・依頼書（第2版） | 6ad98521a788297f8db64468337c71767dca7304 §4.2・§5・§8 |
| C-2の設計（第2版） | 081637e95160a23aab5ea0fc3a2edd01976abba4 §5・§8（C-4への引継ぎ） |
| 上位の方針 | a6340c3937092e4cb658913b9acfb4973a084326 §4（規則4）・§5.4・§5.5 |
| S2のローカル保存 | 6d69bd7のv2_persistence/local（受領済み・変更しない）と試験tests/v2_persistence_local/ |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6（D-3）、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、6d69bd7から作る（ブランチ名の案：feat/v2-history-maintain-c4-YYYYMMDD）。
  1. ユーザーが設計§8のD-1〜D-9を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-9）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-9を、採用されたと書かない。
- 運用方針は日足のみ（分足・NBBOを前提にしない）。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history_maintain/ 新規 | 設計§2.3の4ファイル（`__init__.py`、`ops.py`、`values.py`、`store.py`）。分け方を変える必要があれば、結果文書に理由を書く。6ファイルを超えない |
| tests/v2_history_local/test_c3_09_scope.py | 設計§6.1の`END`の1行だけ。コメントの書き換えはその行の中だけ |
| tests/v2_history_maintain/ 新規 | test_c4_\*.py、c4_helpers.py、c4_worker.py（子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_HISTORY_MAINTAIN_C4_RESULT.md 新規 | 本段階の結果。旧結果文書には追記しない |

これ以外の既存ファイルは変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local。
- 既存の試験・変異・fixtures・ヘルパー（l_helpers、worker.py、c2_helpers、c3_helpers、c3_worker、sc_helpersを含む）。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09、test_c2_09、test_c3_09（上の1行を除く）。
- 設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

既存パッケージの公開名（\_\_all\_\_）は変えない。

次の範囲へ広げない。

- S4：日次処理の組立て、通知、定時実行、本番の保存先・実行場所。
- 退避先（quarantine/）の削除や整理、残り物の自動の掃除、ロックの期限・奪取、自動の再試行・解錠。
- 移行計画・採用計画・診断の作成側の変更。
- C-3実装レビューのP-01・P-03、C-3設計レビューのP-01〜P-07、C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03。
- B-4§7.1の既知の制限、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。そのうえで、反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

- **API**（設計§4.5）：
  - `HistoryMaintenance(root, writable=False, durability=STRICT, *, _ops=None)`。
  - 操作：`inspect()`、`read_original(name)`、`read_set_aside(key, name)`、`unlock(plan, confirmed_plan_hash)`、`migrate(publication, writers_stopped)`、`adopt(publication)`。
  - 純粋関数`plan_unlock(report, request_id, writers_stopped)`。
  - 値：`RootReport`、`UnlockPlan`、`MaintenanceResult`。いずれも不変で、パスを持たない。
  - durabilityの値と保存水準の固定語はS2のもの。
- **S2・C-3との関係**（設計§3、D-7）：
  - OSの呼出しは、S2の`FileOps`を変えずに継承した`MaintenanceOps`だけにする。足すのは`mkdir`と`rename`だけ。
  - `_ops`を試験の継ぎ目にする。
  - C-3の`HistoryFileStore`とS2の`LocalFileStore`は、importも呼出しもしない。
  - ロック・走査・読込み・公開の手順とエラーの流儀は、C-3と同じにする（`LocalStoreError`のcode・field・phase・rule・cleanup・primary、cleanupの固定語）。
  - 名前の定数（history.json、snapshot.json、write.lock、一時ファイルの接頭辞・接尾辞）はC-3・S2と同じにする。
  - ロックのマーカーは`v2_history_maintain.lock\n`＋乱数（32桁の16進）＋改行。
  - パス・OSのエラー文・入力値をエラーに入れない。OSの例外は、例外処理の中では固定のエラーを作るだけにし、投げるのはその外で行う（`raise … from None`では`__context__`に元の例外が残る。設計§5.5）。
- **退避先**（設計§4.1〜§4.4、D-2）：
  - 置き場所は`quarantine/<key>/`。keyは、移行・採用では公開値のpublication_hash、解錠では計画のplan_hash。
  - `quarantine/`と`<key>/`は、リンクでない実ディレクトリで、rootと同じst_devであることを確かめる。
  - `<key>/`に許す名前は、`MANIFEST`、その操作が置く名前、`.q.<32桁の16進>.tmp`だけ。
  - MANIFESTは設計§4.4の8キー（正規化JSON）。退避の前に、一時ファイル→fsync→1回のreplaceで書く。
  - 再開の時は、MANIFESTが今書くはずのバイトと完全に一致すること。
  - 退避先は消さない。
- **明示解錠**（設計§5.1、D-3）：
  - 計画が渡す宣言は`writers_stopped is True`だけを受け付ける。
  - 計画は対象を識別値（名前、種類、raw_sha256、raw_size、st_dev、st_ino）で名指しし、ロックを最後に置く。
  - 実行の前に、人が確認したhashと一致することを確かめる。
  - 計画にロックがあれば、そのロックを排他として使い、新しいロックは取らない。無ければC-4のロックを取る。
  - 実行の時にrootを一覧し直し、部分集合と識別値の規則に外れればmaintenance_plan_staleとし、何も変えない。
  - 対象はrenameで移す（写して消さない）。各renameの直前に識別値と行き先が空であることを確かめる。
  - 最初のrenameの後の失敗はmaintenance_incomplete（primaryに元のcode）。同じ計画でもう一度呼べば、残りだけを移す。
- **移行**（設計§5.2、D-4）：
  - CREATEかつMIGRATIONの公開値と、`writers_stopped is True`だけを受け付ける。
  - 順序は、ロック→snapshot.jsonをロックの下で読みcheck_publication(None, pub, そのバイト)→MANIFEST→history.jsonの公開（C-3の手順）→snapshot.jsonのrename。
  - 「両方」の状態では、history.jsonがPUBLISHEDで、snapshot.jsonが識別値どおりで、退避先が一致するときだけ、残りのrenameをする。
  - 「history.jsonだけ」の状態では、PUBLISHEDかPUBLISHED_THEN_EXTENDEDで、退避先のMANIFESTとsnapshot.jsonが一致すれば、何も書かずにresumed=Trueで完了する。
  - そのほかはmaintenance_state_unexpected（rule＝empty／v1_and_v2／v2_present）。
- **採用**（設計§5.3、D-5）：
  - REPLACEかつADOPTIONの公開値だけを受け付ける。停止の宣言は求めない。
  - 順序は、ロック→history.jsonの元バイトを読む。
  - 元バイトなら、check_publication→MANIFEST→写し（`.q.*.tmp`→fsync→replace）→**写しを読み戻して識別値を確かめる**（違えばmaintenance_copy_mismatchで、replaceの前に止まる）→候補の公開。
  - 元バイトでなければ、reconcileがPUBLISHEDかPUBLISHED_THEN_EXTENDEDで、退避先のMANIFESTと写しが一致するときだけ、resumed=Trueで完了する。他はcheck_publicationの拒否（publication_stale／raw）をそのまま返す。
  - snapshot.jsonがあればstore_layout_unsupported。
- **退避の証拠**（a6340c3 §4の規則4）：MANIFESTの識別値は、ロックの下で読んだバイト（移行ではsnapshot.json、採用ではhistory.json）と、公開値の識別値の両方に一致する。read_set_asideはMANIFESTと照合してから返す。計画の値をそのまま写さない。
- **公開値の受け取り**（設計§3、D-7）：
  - `type(p) is HistoryPublication`でなければ、ロックの前にstore_publication_invalid／type。
  - 書き方・元は、形の誤りで例外が漏れない方法で読み、読めなければロックの前にstore_publication_invalid／shape。
  - 書き方・元が操作に合わなければstore_operation_unsupported（not_migration／not_adoption）。
  - check_publicationのpublication_invalid・publication_staleはそのまま返し、それ以外のCoreErrorはstore_candidate_invalidとする。
  - v2_history_maintainは`_make`・`_of`・`object.__new__`・HistoryPublication／Reconciliationの構築をしない。
- **書込みと成否不明**：history.jsonの公開はC-3の§5.1の順序とcodeのとおり（replaceの呼出し以後の失敗はstore_commit_uncertain）。自分の一時ファイル以外は消さない。計画に無い他人のロックには触らない。
- **失敗の後の手順**（設計§5.4、D-6）：残り物の有無は、ディレクトリの一覧（inspect）だけで判断し、cleanupの語に頼らない。結果文書に、inspect→解錠→同じ操作（公開値はread_original／read_set_asideの読み直しから作り直す）の手順を書く。
- **保存水準**（設計§5.6）：STRICT／FILE_SYNC_ONLY。Windowsのstrictはwindows_strict、ディレクトリのfsyncの確認の失敗はdirectory_sync。どちらも変更の前に止まる。
- **戦略式・履歴の規則を書かない**：履歴・公開値の検査と照合は、既存のread_history_bytes・check_publication・reconcile_publication・raw_identityだけで行う。
- **範囲試験**（設計§6）：
  - C-4の範囲試験は`START = "6d69bd7…"`、`END = None`、`REV = END or "HEAD"`の形で書く。
  - git差分・中身・blob・一覧はREVから読み、作業ツリーは読まない。自分のファイルの範囲の値はHEADから読む。
  - 前の段階の差分を固定文字列で書き写さない。test_c3_09の1行は、C-4自身の差分のハンクとして固定する。
  - 試験が書くのはtempfileの一時ディレクトリだけ。
  - 子プロセスは競合・強制終了の試験だけで、`sys.executable`とtests/v2_history_maintain/の本体だけを使う。
  - 子プロセスの同期にソケットを使わない（既存のヘルパーがソケットを無効にする）。

## 4. 受入条件 C4-01〜C4-22

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、C-2の関数（publish_\*、history_bytes、raw_identity）、c2_helpersの独立のバイト（file_bytes）、hashlibによる試験側の計算から作る。実装の出力をコピーしない。

| ID | 必須確認 |
|---|---|
| C4-01 回帰 | 既存の14スイート計2069件を、完全なクローンで維持する（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139。test_c3_09の1行の固定を含み、件数は同じ） |
| C4-02 構成と値 | 引数の誤り（root、durability、writable、read_originalの名前、read_set_asideのkey・名前）がstore_root_invalid／store_config_invalid。repr・属性・RootReportにパスが出ない。RootReport・UnlockPlan・MaintenanceResultが不変。名前の定数がC-3（v2_history_local.store）・S2と同じ（試験が両方を読む） |
| C4-03 inspect | 空・V2・V1_ONLY・V1_AND_V2のlayout。history.jsonが読めるかどうか。ロックの持ち主（S2、C3、C4、EMPTY、UNKNOWN）。一時ファイル（C-3／C-4、S2）の識別値が、試験側のhashlibとos.lstatの値と一致。退避先の要約。ロックがあっても動き、ロックを作らず、rootを変えない（前後の状態の比較）。ディレクトリのロックはregular＝False |
| C4-04 解錠の計画 | 宣言がTrue以外（False、None、1、"yes"）はmaintenance_declaration_missing。依頼IDの誤り、RootReport以外、対象なし、通常のファイルでない対象を拒否する。targetsの順（一時ファイルは名前順、ロックは最後）。plan_hashがbodyのdigest。同じ報告と依頼IDから同じhash |
| C4-05 解錠の実行 | 次の4つの組合せでUNLOCKEDとなり、rootに対象が残らず、`quarantine/<plan_hash>/`にMANIFESTと対象が同じバイト・同じinodeで入る：ロックだけ（C3・S2・空のマーカー）、一時ファイルだけ（C-4のロックを取り、解放する）、ロック＋C-3とS2の一時ファイル（ロックが最後）。解錠の後、C-3のread・publishが通る |
| C4-06 解錠の拒否 | 未確認のhash（maintenance_plan_unconfirmed）、計画の後に一時ファイル・ロックが増えた／消えた・別のinodeになった（maintenance_plan_stale）、読取り専用、型・形・hashが違う計画。どれもrootと退避先を変えない（前後の状態の比較） |
| C4-07 解錠の中断と再開 | 各renameの故障でmaintenance_incomplete（primary）。同じ計画で再開すると残りだけを移し、resumed=True。退避先に知らない名前を置く、またはMANIFESTを1バイト変えると、maintenance_quarantine_invalidで止まる |
| C4-08 P-02の残り物 | C-3のcreate_exclusiveが作成の後に例外を返す故障（C-3の試験と同じ形）で、cleanupが空のまま一時ファイルが残る。inspectが見つけ、解錠で移せ、その後C-3が公開できる。ロックの場合も同じ（cleanupに語が無いロックの残り） |
| C4-09 移行 | migration_caseの公開値でMIGRATED。history.jsonがfile_bytes(候補)、退避先にMANIFESTと元のsnapshot.jsonのバイト。C-3が読める。宣言なし、CREATEのGENESIS・REPLACE・APPENDの公開値、v1のバイト違い（publication_stale／source_v1）、空・他人のhistory.json・一時ファイル（store_artifact_present）の各拒否で、rootが変わらない |
| C4-10 移行の再開 | (a) snapshot.jsonのrenameの故障→「両方」→C-3はstore_layout_unsupported／v1_and_v2→read_originalのバイトからpublish_migrationで作り直した公開値（hashが同じ）で再開。(b) 解放の故障→C-4のロックの残り→解錠→read_set_asideから作り直して再開→resumed=True、書込みなし。(c) 完了後の再実行、C-3の日次の公開の後の再実行もresumed=True |
| C4-11 採用 | adoption_caseの公開値でADOPTED。history.jsonがfile_bytes(候補)、退避先の写しが元のバイト。C-3が読める。完了後に今のバイトでpublish_adoptionを呼ぶとpublication_refused／no_change。v1あり、別のバイト（publication_stale／raw）、MIGRATION・APPEND・CREATEの公開値の各拒否で、rootが変わらない |
| C4-12 採用の再開（C-2の引継ぎ） | (a) replaceの後の故障（解放の失敗・dir_syncの失敗）→解錠→read_set_aside(key, "history.json")の元バイトからpublish_adoptionで作り直すとhashが同じ→adoptでresumed=True。(b) 写しのreplace・写しの書込みの故障→history.jsonは元のまま→再開で完了。(c) 写しを読み戻すと違う（記録の子クラスで読み戻しのバイトを替える）→maintenance_copy_mismatchで、history.jsonは元のまま |
| C4-13 退避の証拠（規則4） | MANIFESTの識別値が、試験側でhashlibにより計算したロックの下のバイトの値と一致する。計画・公開値の値を写しただけの実装を、欠陥注入で区別できる。read_set_asideは、退避先のバイトが替えられていればmaintenance_set_aside_mismatch、MANIFESTに無い名前・keyも拒否 |
| C4-14 公開値の受け取り | dict・確認結果・History等の型はstore_publication_invalid／type、mode・sourceが無い手作りの値（`_make`）はshape。どちらもロックを取らない（ロックの作成が呼ばれないことを、FileOpsの記録で確かめる）。候補が無効な手作りの値はstore_candidate_invalid |
| C4-15 ロック | C-4の操作が持つロックで、C-3・S2がstore_busy（両方向）。他人のロック（残り）で、C-4のread_original・read_set_aside・migrate・adoptがstore_busy。自分のマーカーを書く。公開の前に所有を失えばstore_lock_ownership_lost、後ならstore_commit_uncertain。解放の失敗はlock_left |
| C4-16 手順と故障 | 正常時のMaintenanceOpsの呼出し列が、設計§5の順序と同じ（記録の子クラス）。全呼出し×前後×例外3種以上の単独故障の総当たりを、migrate・adopt・unlock×STRICT・FILE_SYNC_ONLYで行い、次の4点を試験で確かめる。(1) CoreError以外が漏れない。(2) 元のバイトがrootか退避先に残る。(3) history.jsonが元か候補。(4) 設計§5.4の手順で最終の状態に着く |
| C4-17 保存水準 | STRICTで、設計§5.6のファイルとディレクトリのfsyncを呼ぶ（記録で確かめる）。FILE_SYNC_ONLYでは、ディレクトリのfsyncを呼ばない。Windowsのstrict（is_windowsを替えた記録の子クラス）はwindows_strict、確認の失敗はdirectory_sync。どちらも変更の前に止まり、ロックは解放される |
| C4-18 プロセス | 4つ以上の子プロセスが同じrootでadopt（またはmigrate）を競うと、resumed=Falseの成功は1回だけで、ほかはstore_busyかresumed=True。最後のhistory.jsonが候補で、残り物なし。強制終了（SIGKILL。Windowsでは試験をskip）を、MANIFESTの後・公開の前と、公開の後・renameの前で起こす。どちらも次の操作がstore_busyになり、解錠→同じ操作で完了する |
| C4-19 情報の漏れ | 故障の例外にパスや秘密らしい文字列を入れても、エラーのstr・repr・属性・cleanup・`__cause__`・`__context__`（`__suppress_context__`に関わらず、属性そのもの）、RootReport、MANIFESTに出ない |
| C4-20 静的監査 | v2_history_maintainに`_make`・`_of`・`object.__new__`・HistoryPublication(…)・Reconciliation(…)の呼出しが無い。v2_history_localとLocalFileStoreをimportしない。v2_history_publishからimportする名前が設計§2.3の一覧だけ。osの使い方はパスの組立て（join、dirname、abspath、isabs、realpath、fspath）だけで、ファイル操作はMaintenanceOps経由。MaintenanceOpsが足すのはmkdir・renameだけ。ネット・時計・threading・subprocess・環境変数・hashlib・新しい依存が無い |
| C4-21 範囲の値と自分の範囲 | test_c3_09のENDが6d69bd7で、差分は1行だけ。範囲の鎖がadfdf765→…→d6b0332→6d69bd7→（C-4、END=None）で、開いた範囲はC-4の1本だけ。6d69bd7→REVで、Mはtest_c3_09だけ（1行のハンクと一致）、Aはv2_history_maintain/、tests/v2_history_maintain/、結果文書だけ。それ以外はblob単位で同じ。新しい試験はネットワーク・時計による順序付け・環境変数を使わず、書込みは一時ディレクトリだけ |
| C4-22 次の段階の模擬 | 使い捨てのコミットで、(1) C-4の範囲試験の`END`だけを自分の試験対象のSHAに替え（1行）、(2) 仮の開いた範囲試験1本を足す。test_sc_\*・test_c1_\*・test_c2_\*・test_c3_\*・test_c4_\*が通ること。結果文書に手順と結果を書く（そのコミットはpushしない） |

## 5. 限定欠陥注入

次の項目を1件ずつ壊し、試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. 解錠：実行の時の一覧のやり直しを外す（計画の後に増えた一時ファイルを見ない）。
2. 解錠：renameの直前のinodeの比較を外す。
3. 解錠：ロックを最後でなく最初に移す（C4-05の順序で検出されること）。
4. 解錠：計画にロックが無いのに、C-4のロックを取らない。
5. 解錠：確認したhashとの比較を外す。
6. 解錠の計画：宣言の`is True`を真値の判定にする。
7. 退避先：MANIFESTの完全一致の確認を外す（再開で知らないMANIFESTを受け入れる）。
8. 退避先：許す名前の確認を外す。
9. 退避先：st_devの比較を外す（記録の子クラスでst_devを替えて検出されること）。
10. MANIFEST：識別値をロックの下のバイトからでなく公開値から写す（C4-13で区別されること）。
11. 移行：snapshot.jsonのrenameをhistory.jsonの公開より前に行う。
12. 移行：「両方」の再開で、history.jsonの照合を外す。
13. 移行：`writers_stopped`の確認を外す。
14. 採用：写しの読み戻しの確認を外す。
15. 採用：写しを候補の公開の後に作る。
16. 採用：再開で、退避先の写しの識別値の確認を外す。
17. read_set_aside：MANIFESTとの照合を外す。
18. 公開値の型の確認をロックの後へ移す（C4-14で検出されること）。
19. 例外処理の中の1か所を`raise … from None`に戻す（C4-19で検出されること）。
20. ロックの名前をC-3・S2と違う名前にする（C4-15の相互排他で検出されること）。
21. 範囲試験：test_c3_09の固定の行を変える。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴）で試験する。`git archive`のツリーでのskipの件数は、別に記録する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、次の合計（新規N＋1593）を実行する。
  - 新規N。
  - C-3 139、C-2 150、C-1 112、範囲の鎖34、B-5b 170、B-5a 131、B-4 165、B-3 109、B-2 173、S3-A 176、B-1 230、S2専用4件。
- C-4のWindows専用の確認（strictの拒否、rename・mkdir・ディレクトリの扱い、ロック・一時ファイル名の扱い）は、実Windowsで行うまで未実施と書く。
- 未実施のOSやユーザーPCを、他者の結果で代用しない。物理電源断は未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_maintain -p "test_c4_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- 新しいランタイムの全文の場所と行数。
- C-3の手順との対応表（C-3のどの段階がC-4のどこか）。
- test_c3_09の差分の全文。
- 試行の差分（設計§7）との違いと、その理由。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。
- C4-16の総当たりの件数と分類、C4-22の手順と結果。
- 設計§5.4の失敗の後の手順を、利用者向けに短くまとめたもの。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・通知・S4へは進まない。

## 7. 読取専用の保護参照

次の82参照を、開始時と保存・push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-history-maintain-c4-20261104についても、受け取った版の完全SHAを1本加える（実装時は83参照）。

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
| docs/v2-history-local-c3-20261104 | 6ad98521a788297f8db64468337c71767dca7304 |
| docs/v2-history-local-c3-review-20261104 | 213bcb7f05d2e1be5f04d529289b437367457f3e |
| feat/v2-history-local-c3-20261104 | 6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a |
| docs/v2-history-local-c3-impl-review-20261104 | 2049e1056f76e606343c3eb0fbbe82e531988ca6 |

## 8. 採用単位

設計§8のD-1〜D-9と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。D-1〜D-9は次のとおり。

- D-1：C-4の範囲。
- D-2：a6340c3 §5.5の未決への回答。
- D-3：明示解錠。
- D-4：移行の順序。
- D-5：採用の順序とC-2の引継ぎ。
- D-6：C-3実装レビューのP-02と、失敗の後の手順。
- D-7：S2・C-3との関係。
- D-8：範囲試験。
- D-9：C-4の限定実装の担当（Sonnet 5.5・high）。

今回の文書作成と、設計§7の一時環境の試行は、その採用ではない。C-3の受領を、C-4の実装承認にしない。S4の実装承認も含まない。
