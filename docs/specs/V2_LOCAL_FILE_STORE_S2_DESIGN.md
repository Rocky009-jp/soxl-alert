# V2 S2 ローカル実ファイル保存 設計・実装契約

2026-10-28（日本時間）。状態：ユーザーの「S2移行の実装に進めます」に基づく、S2限定実装の着手用契約。S3／S4や本番接続の承認ではない。  
主担当がS1の確定版から具体化した。実装担当はSonnet 5.5・high。今回作成した文書自体は実装・試験の完了記録ではない。

## 1. 固定版・目的・範囲

| 用途 | 版 |
|---|---|
| コード開始点 | 2d09db770d21480202c4c603e02c2aec5e030012、fix/v2-core-fg-numeric-overflow-20261028 |
| 直近受領 | [コア修正受領](https://github.com/Rocky009-jp/soxl-alert/blob/a235b7607f5624ed84ba5427ac0f44029f41d262/docs/reviews/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RECEIPT_20261028.md) |
| S1の契約 | [第4版](https://github.com/Rocky009-jp/soxl-alert/blob/425df80d04b116e25e481184069b89bed1380c3a/docs/specs/V2_PERSISTENCE_DOMAIN_OFFLINE_DESIGN_DRAFT.md) |
| 上位の保存・復旧設計 | [第4版e3e9094](https://github.com/Rocky009-jp/soxl-alert/blob/e3e90947a718cca877b543739ca60539207ca7a7/docs/specs/V2_MARKET_STATE_PERSISTENCE_RECOVERY_DESIGN_DRAFT.md)、案F・§3.5／3.6 |
| 実装依頼 | [V2_LOCAL_FILE_STORE_S2_REQUEST.md](../tasks/V2_LOCAL_FILE_STORE_S2_REQUEST.md) |

S1のSnapshot／AppendPlanを実ファイルへ保存し、再起動後の読取、同じ保存先への複数プロセスの排他と比較更新、中断・破損・保存成否不明を試験する。正常な市場判定はS1へ委譲したままにする。

対象外：本番の保存正本の選定、非公開リポジトリ・資格情報・workflow、取得・カレンダー・自動対象日、追いつきループ、ACK・復元・再初期化・履歴退避、outbox・通知・再送、口座、戦略変更。U-01／U-11／U-13は未決のまま。S2のローカル試験用保存先を、本番正本に採用したとは扱わない。

CLAUDE、STATUS、MODEL_POLICY、ROADMAPを確認した。STATUS等の古い承認待ち表記より、今回のユーザー指示と本書の限定範囲を優先する。既存の文書は書き換えない。

## 2. 保存単位と上位設計との差

専用のrootに置く管理名は次に固定する。入力のD・record_id・台帳値からパスを組み立てない。

| 名前 | 内容 |
|---|---|
| snapshot.json | S1のSnapshot全体（現在状態＋GENESISから全APPLY）。唯一の正本 |
| write.lock | 排他的な新規作成で取得する所有マーカー |
| .snapshot.<opaque>.tmp | 同じroot内で排他的に作る今回の一時ファイル |

保存内容はencode_snapshotのUTF-8バイト列で、読取は厳密UTF-8→decode_snapshot→validate_snapshot。S1のschema_version=1とCORE_SHAの互換基準を変えない。JSONの空白・キー順を真正性の証明に使わず、S1の内容とハッシュの検査を使う。

上位案Fはentriesとstate.jsonを別々に保存する例だが、S2はS1が既に持つ全履歴入りSnapshotを1ファイルとして置換する。履歴と現在状態を別の時点で公開する区間を無くすためである。物理ファイルは書き換わるが、commitで許す論理操作は既存履歴を保持したAPPLY1件の末尾追加だけ。過去のイベント値を差し替えるAPIは作らない。上位のリモート保存形式を変更・採用した意味ではない。

一時ファイルや残留ロックを「新しいから正しい」と選ばない。正本が無い・壊れている場合に一時ファイルを昇格せず、初期化もしない。

## 3. APIと既存コードの境界

新規サブパッケージv2_persistence/local/に置く。既存v2_core、v2_persistenceの既存ファイル、既存197件＋170件は変更しない。

| API | 契約 |
|---|---|
| LocalFileStore(root, writable=False, durability="strict") | 明示された既存の専用ディレクトリだけを使う。OS時刻・環境変数から保存先を推定せず、フォルダを自動作成しない |
| read() | ロック取得後に毎回ディスクを読み、全検査済みSnapshotを返す。キャッシュを正本にしない |
| initialize(genesis) | writable=Trueの明示操作。検査済みGENESIS1件だけを、正本が無い場合に保存 |
| commit(plan) | writable=True。ロック内の再読取・期待先頭比較・候補全検査・1回の正本置換 |
| LocalCommitResult | 正常完了時だけstatus=COMMITTED、committed=True、snapshot、persistence_levelを返す |

readの戻り値はS1と同じ独立性を持つ。検査結果、辞書、MarketState、書込結果からストアを変更できない。read_onlyは正本更新の禁止を意味し、readでも排他のためロック作成・解放を行う。OSの読取専用媒体から読むAPIではない。

単日処理は既存のprepare_day(store.read(), ...)を呼び、計画があるときだけcommitする。NO_COMMIT／ALREADY_APPLIEDでは正本を書かない。成否不明の論理照合は既存reconcile(plan, store.read())を使う。MemoryStoreのprivate属性へファイル状態を注入する実装にしない。

## 4. ルート・パスの前提

rootは呼出側が渡す絶対パスの、信頼できるローカル・非同期の専用フォルダ。NFS／SMB・共有ドライブ・OneDrive等の同期先はサポート対象にしない。ファイルシステムの種類を完全自動判定したという主張はせず、前提と実測を記録する。

root自体と管理対象の既存シンボリックリンク／reparse point、正本が通常ファイルでない場合は拒否する。管理パスが解決済みrootの外へ出ないことを確認する。管理外ファイルを削除・移動しない。OS固有の判定が未確認ならその範囲を留保し、リンクを追って書き込まない。

第三者がrootの祖先やロックを攻撃的に差し替える環境への防御・認証機構ではない。信頼済みrootを共有する全ライターが本APIを使い、外部から正本・ロックを手編集しないことを前提とする。

## 5. 排他

read／initialize／commitは全て同じwrite.lockをO_CREAT|O_EXCL相当の排他的作成で取得し、検査・比較・置換・後始末まで保持する。プロセス内のthreading.Lockだけでは代用しない。既に存在すればstore_busyで即停止。待機ループ・リース・時刻による期限判定・自動強奪は作らない。

所有者には実行ごとのopaqueなランダムマーカーを使い、PIDだけで判断しない。ロック作成途中の通常例外も、自分が作ったファイルだけを安全に後始末する。取得失敗した側は他者のロックを削除しない。書込直前と解放時に所有を確認し、変化していればstore_lock_ownership_lostで止め、他者のロックを消さない。

通常例外では自分のハンドル・一時ファイル・ロックを後始末する。所有を確認できないものや、他実行の一時ファイルを削除しない。後始末失敗を成功扱いしない。強制終了で残ったロックは、自動削除せず次回も停止する。明示的な解錠・復旧APIはS3へ留保する。

管理名に一致する残留一時ファイルを見つけた場合はstore_artifact_presentで止め、勝手に採用・掃除しない。正本だけが無い空の専用rootへのreadはstore_uninitialized。初期化は自動で呼ばない。

## 6. 初期化・比較更新の手順

### 6.1 initialize

書込許可・GENESIS1件・rootを確認しロックを取る。既存正本があれば読込・検査し、正常ならalready_initialized、不正なら検査エラーで停止。残留一時ファイルも拒否する。いずれも上書きしない。正本が無い場合だけ§6.3の保存手順を行う。

### 6.2 commit

1. 書込許可、AppendPlanの型、rootを確認しロックを取る。
2. 正本をディスクから読み直してvalidate_snapshot。欠損・破損・残留物は停止。
3. expected_head_seq／expected_head_hashを実際の先頭と比較。不一致はcas_conflict、書込なし。
4. 既存append_eventとvalidate_snapshotで候補を作り全検査する。旧履歴は変更しない。
5. §6.3で保存する。正常な後始末まで完了してからCOMMITTEDを返す。

同じ先頭からの2計画は同内容でも1件だけが更新に成功する。敗者はstore_busyまたはcas_conflict。読み直して既存reconcileを呼べるが、古い計画の親を付け替えず、自動で再commitしない。

### 6.3 正本の公開

1. 選択した同期モードの対応可否を公開前に確認する。
2. 同じroot内へmkstemp等で排他的に一時ファイルを作る。
3. 候補全体をバイナリで書き、短いwriteも考慮して全バイトを完了させる。
4. flush→ファイルfsync→close。開いたままの一時ファイルを置換しない。
5. ロック所有を再確認し、os.replaceでsnapshot.jsonを1回だけ置換する。
6. strictでは親ディレクトリもfsyncする。
7. 所有を確認してロックを解放し、正常な後始末後に結果を返す。

原子性の公開点は5、選択モードの同期完了点は6まで。旧ファイルを先に削除したり、正本を直接truncateして書き始めたり、別ボリュームの一時ファイルからコピーしたりしない。

## 7. 同期モードと保証範囲

| モード | 契約 |
|---|---|
| strict（既定） | ファイル同期と置換後の親ディレクトリ同期を要求。結果persistence_level=FILE_AND_DIRECTORY_SYNC |
| file_sync_only（明示指定のみ） | ファイル同期と置換まで。親ディレクトリ同期を実施したとは扱わない。結果persistence_level=FILE_SYNC_ONLY |

strictで必要なディレクトリ同期を提供できないOS／保存先ではstore_durability_unsupportedとして公開前に止める。今回のWindows strictは未対応として拒否し、Win32固有APIを追加しない。対応検査は書込操作時に行い、readだけならディレクトリ同期の未対応を理由に拒否しない。黙ってfile_sync_onlyへ下げない。POSIXでは公開前にrootのディレクトリを開いてfsyncできることも実際に確認する。公開後のディレクトリ再同期をこの事前確認で代用しない。事前に未対応を検出すれば公開しない。事前確認後に発生した同期I/O失敗は通常の成功へ変換しない。

Windowsのfile_sync_onlyはローカル試験用の明示的な選択として用意する。これは厳密な電源断耐久性の保証ではない。実Windowsで走らせていなければ、Linux上の分岐模擬だけでWindows検証済みと書かない。

COMMITTEDは指定された同期手順と後始末を完了した意味で、ハードウェア、ドライブキャッシュ、全ファイルシステムの物理的電源断への無条件保証ではない。実機の電源を切る試験は今回行わない。プロセス強制終了と物理的な電源断を区別する。

## 8. 保存失敗・成否不明

置換をまだ呼んでいない段階の失敗は、正本が従来のままであることを確認しstore_io_error等で止める。自身の一時ファイルだけを後始末する。

置換の呼出し開始以降に失敗した場合（実際には置換された後で例外、ディレクトリ同期失敗、置換後のロック解放失敗を含む）はstore_commit_uncertain。正本は旧版か新版の可能性がある。ロールバック、再初期化、再追記、成功の推定はしない。COMMITTEDを返さず、その呼出しを止める。

ロックを正常に解放できた場合は、呼出側が明示的にreadして既存reconcileで論理内容を照合できる。新版と一致してもALREADY_APPLIEDは「現在その内容が読める」の意味であり、失敗した同期手順の成功、保存した主体、送信権を保証しない。自動で次のDや外部副作用へ進む経路は作らない。残留ロックがあればreadも停止する。

## 9. エラー対応

既存PersistenceError／CoreErrorを用い、code／field／固定phaseを示す。OSErrorのパス・生の例外文・入力値を公開エラーへ入れない。安全なphase以外の例外連鎖も表示しない。

| 条件 | code／field |
|---|---|
| root不正・通常ファイル以外・リンク等 | store_root_invalid／root |
| 未知の同期モード | store_config_invalid／durability |
| writableがbool以外 | store_config_invalid／writable |
| AppendPlanでない計画 | snapshot_invalid／snapshot、rule=plan_type |
| writable=Falseで初期化・commit | store_read_only／store |
| ロックが存在 | store_busy／lock |
| 取得したロックの所有が変化 | store_lock_ownership_lost／lock |
| 残留一時ファイル | store_artifact_present／store |
| 正本なし | store_uninitialized／store |
| 初期化済み | already_initialized／store |
| 期待先頭が相違 | cas_conflict／head |
| 同期モードを実現不可 | store_durability_unsupported／durability |
| 公開前のI/O失敗・後始末失敗 | store_io_error／固定の対象field |
| 置換呼出し開始以降の失敗 | store_commit_uncertain／snapshot |
| 正本JSON・履歴の不正 | S1のsnapshot_invalid／unsupported_schema／unsupported_event等を保持。不正UTF-8はsnapshot_invalid、rule=utf8 |

優先順は、引数・書込許可→ロック→残留物・正本検査→CAS→候補検査→保存。通常例外の後始末失敗は隠さず、公開を試みていればstore_commit_uncertainを優先する。ロック所有喪失も公開を試みた後ならstore_commit_uncertainを優先し、phaseにlock_ownershipを示す。

## 10. 試験と後工程

依頼書B-01〜B-10を完了条件にする。実ファイルと独立プロセスを使い、障害注入だけでプロセス競合の証明としない。強制終了後の診断は、終了済みの子プロセスと専用テストrootだけで行う。残留ロック・一時ファイルをテストの片付けで明示削除することを、製品の自動復旧と混同しない。

S2はローカル試験用アダプタまで。S3のACK／復元、S4の保存先・台帳・実行場所・資格情報・通知は別工程。ユーザーPCでの既存181件は後日確認のままで、S2の別環境試験に置き換えない。

### 技術根拠（2026-10-28確認）

- [Python 3.10 os](https://docs.python.org/3.10/library/os.html)：flush／fsync、同一ファイルシステム内のreplace。
- [Python 3.10 tempfile](https://docs.python.org/3.10/library/tempfile.html)：安全な一時ファイル作成、closeとWindows上の扱い。
- [Linux fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html)：ファイル同期とディレクトリのエントリ同期の違い。
- [Linux open(2)](https://man7.org/linux/man-pages/man2/open.2.html)：O_CREAT|O_EXCL。

上記のOSプリミティブからS2の契約を組み立てたもので、全OSで同じ耐久性を確認済みという意味ではない。
