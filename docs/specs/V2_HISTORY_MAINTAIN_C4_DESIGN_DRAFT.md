# V2 C-4 保守操作（移行・採用・明示解錠） 設計案

作成日：2026-11-04（日本時間）。版：**第2版**（初版ce4fd28への設計レビュー74c93b1の通常N-01〜N-03だけを反映。§10）。
状態：**第2版・設計案・採否判断待ち（再レビューの後に採否）。C-4の限定実装は未承認。**
Rockyさんの「C-4の作業を始めてください」（2026-11-04T02:47Z、コーディネーター経由）を、設計書と限定依頼書から始める指示として受けて作成した。今回の作業は、設計書と限定実装依頼書の作成と、一時環境での試行まで。文書の保存、推奨、試行の合格を、実装の承認とは扱わない。作成担当はClaude Opus 5.5、effort high（このスレッドのセッション設定）。

## 0. 要約

- **C-4の範囲（D-1）**：C-3のストアが止まったまま先へ進めない状態を、人の手順でC-3の通常の状態へ戻す操作を作る。新しいパッケージ`v2_history_maintain`の`HistoryMaintenance`に、次の6つを置く。
  - 見るだけ：`inspect()`（ロックを取らない。rootの中身を報告する）、`read_original(name)`（ロックの下で、`history.json`または`snapshot.json`の生のバイトを返す）、`read_set_aside(key, name)`（ロックの下で、退避したバイトをMANIFESTと照合して返す）。
  - 変えるもの：`unlock(plan, confirmed_plan_hash)`（明示解錠。残ったロックと一時ファイルを退避先へ移す）、`migrate(publication, writers_stopped)`（v1→v2移行の実行）、`adopt(publication)`（prefix採用の実行）。
  - 解錠の計画は純粋関数`plan_unlock(report, request_id, writers_stopped)`で作る。
  - 日次処理・通知・本番の保存先はS4。退避先の削除や自動の掃除は作らない。
- **a6340c3 §5.5の未決への回答（D-2）**：
  - 停止の証拠は人の宣言で代える（`writers_stopped=True`）。解錠の計画と移行の呼出しに入れ、MANIFESTに記録する。機械的な証明とは書かない。
  - 保守用の新しいマーカーは作らない。C-4の操作は`write.lock`（中身はC-4の固定語）を持ち、中断すればロックの残りになる。外すのは明示解錠だけ。
  - 退避先は`quarantine/<key>/`。keyは公開値のpublication_hash（移行・採用）または解錠計画のplan_hashにする（a6340c3の`<依頼ID>`を改めた。§4.3）。MANIFESTを最初に書き、保存水準はストアと同じにする。
  - 中断後の再開は、同じ操作をもう一度呼ぶだけでよい。退避先の中身が「MANIFESTと、その操作が置く名前だけ」で、識別値が一致するときに限る。
- **退避の仕方（D-3）**：ロックと一時ファイルは、同じファイルシステムの中で**rename**して退避先へ移す（inodeとバイトがそのまま残り、写しかけの状態が生じない）。採用の元の`history.json`だけは、replaceまで置いたままにする必要があるので、**写して**から読み戻して確かめる。a6340c3 §5.4の「一時ファイルは写してから消す」を改めた。
- **移行の順序（D-4）**：
  1. ロックを取る。
  2. snapshot.jsonをロックの下で読み、C-2のcheck_publicationで公開値と照合する。
  3. MANIFESTを書く。
  4. history.jsonを一時ファイル→replaceで作る。
  5. 最後にsnapshot.jsonを退避先へrenameする。
  - 途中で止まると「両方ある」状態とロックの残りになる。C-3はこの状態を拒否する。
- **採用の順序（D-5）**：
  1. ロックを取る。
  2. history.jsonの元バイトを読み、照合する。
  3. MANIFESTを書く。
  4. 元バイトを退避先へ写して確かめる。
  5. 候補を一時ファイル→replaceで公開する。
  - **C-2からの引継ぎ**：replaceの後で止まった場合は、退避した元バイトを`read_set_aside`で読み、`publish_adoption`で同じ公開値を作り直す。それをもう一度`adopt`に渡すと「完了済み」として終わる。今のバイトでの確認はNO_CHANGEになる（C-2の規則のまま）。
  - a6340c3 §4の規則4（退避の証拠はロックの下で読んだバイトから作る）を受入に入れる。
- **C-3レビューの提案P-02（D-6）**：作成の直後に例外を返すような故障では、エラーのcleanupに語が付かないまま、ロックや一時ファイルが残ることがある。C-4はcleanupの語を当てにせず、**ディレクトリの一覧だけ**から残りを見つける（`inspect`）。C-4自身のエラーも同じなので、失敗の後はいつも`inspect`から始める手順にする。ネットワークドライブ・同期フォルダ上のrootは推奨しない。
- **S2・C-3との関係（D-7）**：
  - OSの呼出しは、S2の`FileOps`を変えずに継承した`MaintenanceOps`を使う。足すのは`mkdir`と`rename`の2つだけ。
  - C-3の`HistoryFileStore`は変えず、内部も呼ばない。ロック・走査・公開の手順はC-3の写しで、ロックの名前はS2・C-3と同じ`write.lock`にする。名前の定数がC-3・S2と同じことは試験で確かめる。
  - 公開値は`type(p) is HistoryPublication`のものだけを受け取り、C-4は公開値を作らない（静的監査）。
- **範囲試験（D-8）**：C-3の範囲試験test_c3_09のENDを6d69bd7に1行で固定し、同じコミットでC-4の開いた範囲試験（START＝6d69bd7、END=None）を足す。
- **一時環境での試行（§7）**：6d69bd7のコピーにC-4を試作した（pushしない）。
  - 既存の14スイート2069件が、Python 3.12.3と3.13.18で全件合格した（test_c3_09の1行の固定を含む）。
  - 使い捨てのプローブ87項目が期待どおりだった。
  - 故障の総当たり1,638通り（3操作×2保存水準×全呼出し×前後×3種の例外）で、CoreError以外の例外0、元のバイトの消失0、history.jsonが元か候補以外になったもの0、文書の手順で復旧できなかったもの0。
  - 6プロセス×10回の競合で、毎回成功1・残留物なし。
- 運用方針は日足のみ（早朝に米国の確定日足で通知し、夜の寄付きで手動購入）。分足・NBBOは前提にしない。保守は、早朝の通知の後、夜の寄付きの前の日中に人が行う（a6340c3 §5.1）。
- 採否はD-1〜D-9の一組で判断する（§8）。

## 1. 目的と固定入力

| 用途 | 固定版 |
|---|---|
| 起点（コード・試験） | **6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a**（feat/v2-history-local-c3-20261104）。C-3の試験対象e3d880aに結果文書1本を足した保存最終 |
| C-3の受領 | 実装レビュー2049e1056f76e606343c3eb0fbbe82e531988ca6（docs/v2-history-local-c3-impl-review-20261104、重大0・通常0・提案3、受領推奨）。6d69bd7で受領済み（コーディネーター経由で確認） |
| C-3の設計・依頼書（第2版） | 6ad98521a788297f8db64468337c71767dca7304（docs/v2-history-local-c3-20261104）。特に§4.2（rootの状態）、§5（成否不明と照合）、§8（既知の制限） |
| C-3の設計レビュー | 213bcb7f05d2e1be5f04d529289b437367457f3e（N-01、提案P-01〜P-07） |
| C-2の設計（第2版） | 081637e95160a23aab5ea0fc3a2edd01976abba4 §5・§8（C-4への引継ぎ） |
| 上位の方針 | a6340c3937092e4cb658913b9acfb4973a084326 docs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md §4（P-02の規則4）、§5.1、§5.4、§5.5 |
| S3設計第3版 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c §10（S3-Cの未決） |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6（D-3）、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4、C-3設計§6 |
| 運用方針 | 日足単位の判定。早朝に米国市場の終値で通知し、夜の寄付きで買う。分足・NBBOは前提にしない（2026-10-26） |

読解対象：6d69bd7のv2_history_local（全3ファイル）、v2_history_publish（build.py、check.py、read.py、values.py、errors.py）、v2_persistence/local（store.py、fsops.py、errors.py）、試験のc2_helpers・c3_helpers・l_helpers（FaultOps）・test_c3_09_scope.py、上の各文書とC-3の実装レビュー2049e10・結果文書。共通のCLAUDE.mdも確認した。取得できなかったファイルは無い。

## 2. C-4の範囲（D-1）

### 2.1 前の段階が残したもの

| 出典 | 残したもの |
|---|---|
| a6340c3 §5.4・§5.5 | 明示解錠、残留物と元バイトの退避、移行・採用の実行と中断後の再開。未決の6項目（停止の証拠、旧S2と共存しない移行、保守ゲートのクラッシュ時の契約、退避先の名前と同期水準、解錠中断後の再開条件、実行場所） |
| a6340c3 §4 規則4 | 元バイトの退避の証拠は、ロックの下で読み直したバイトから作り、計画の値は一致を確かめるだけに使う |
| C-2設計第2版§8 | 採用のREPLACEがreplaceの後で中断したら、退避した元バイトからpublish_adoptionで公開値を作り直す。今のバイトではNO_CHANGE |
| C-3設計§8 | 既知の制限(1)解錠の後の旧S2の書き手、(2)残り物を片付ける手段がC-4まで無い、(3)ネットワークドライブ等は未確認 |
| C-3設計レビュー213bcb7 P-02 | replaceが失敗して一時ファイルが消せなかった（tmp_left）場合、照合はNOT_PUBLISHEDでも再公開はstore_artifact_presentで止まる。C-4の明示解錠まで再公開できない |
| C-3実装レビュー2049e10 P-02 | create_exclusiveが作成の後に例外を返すと、cleanupに語が付かないままロック・一時ファイルが残る。C-4の解錠・片付けは「cleanupに語が無くても残り物はあり得る」を前提にする |

### 2.2 C-4がすること・しないこと

| する | しない（S4・範囲外） |
|---|---|
| rootの中身を、ロックを取らずに報告する（残ったロックの持ち主の種類を含む） | 残り物の自動の掃除、ロックの期限・奪取、自動の解錠・再試行 |
| 人が確認した計画で、残ったロック・一時ファイルを退避先へ移す | 退避先（quarantine/）の削除・整理 |
| MIGRATIONの公開値でv1→v2を実行し、snapshot.jsonを退避する | 移行計画・採用計画の作成（既存のv2_history・v2_history_adoptのまま） |
| ADOPTIONの公開値でprefix採用を実行し、元のhistory.jsonを退避する | 損傷の診断（既存のv2_history_diagnoseのまま） |
| 中断の後、同じ操作をもう一度呼べば残りだけを行う | 日次処理の組立て、通知、定時実行、本番の保存先・実行場所 |
| 退避したバイトを、MANIFESTと照合して読む | S2・C-3のコードの変更 |

### 2.3 パッケージ

新しいパッケージ`v2_history_maintain`を作る。ファイル案は次の4本。

- `__init__.py`
- `ops.py`：`MaintenanceOps`。S2の`FileOps`を継承し、`mkdir`と`rename`の2つを足す。
- `values.py`：`RootReport`、`UnlockPlan`、`plan_unlock`、MANIFESTのバイト、`MaintenanceResult`。
- `store.py`：`HistoryMaintenance`。

依存は次のとおり。

- 標準ライブラリ：os、secrets、stat、json、copy、dataclasses、typing。C-3の集合にjsonを足すのはMANIFESTを読むためだけ、copyはC-4自身の値（RootReport・UnlockPlan）の属性を写して返すためだけ（第2版、レビューN-02）。
- 変更しない既存のもの：
  - v2_core：エラーの型。
  - v2_persistence.local：FileOps、LocalStoreError、cleanupの固定語、保存水準の固定語。
  - v2_persistence.codec：canonical_json。
  - v2_history.common：is_hex64、is_int。
  - v2_history_ops.values：_Frozen、digest_of。
  - v2_recovery.common：valid_request_id。
  - v2_history_publish：次の12の名前だけ。`HistoryPublication`、`check_publication`、`reconcile_publication`、`history_bytes`、`read_history_bytes`、`raw_identity`、`CREATE`、`REPLACE`、`MIGRATION`、`ADOPTION`、`PUBLISHED`、`PUBLISHED_THEN_EXTENDED`。

hashlibは使わない（識別値はC-2のraw_identityで計算する）。v2_history_localはimportしない。

既存のパッケージ・試験・ヘルパーは変えない。例外は§6の範囲試験の固定（test_c3_09の1行）だけ。

## 3. S2・C-3との関係（D-7）

- **FileOpsを継承する**：OSに触れる層は、S2の`FileOps`を変更せずに継承した`MaintenanceOps`だけにする。
  - 足すのは`mkdir(path)`（`os.mkdir(path, 0o700)`。何かあればFileExistsError）と`rename(src, dst)`（`os.rename`）の2つだけ。
  - S2の受領済みのファイルは1文字も変えない。
  - 試験はC-3と同じく`_ops`引数に、記録・故障注入の子クラスを渡す。
- **C-3を変えず、内部も呼ばない**：ロック（`_acquire`、`_owns`、`_release`、`_locked`）、走査、読込み、公開（`_publish`、`_discard_own`）は、C-3の手順を同じ順序とエラーの流儀で写す。C-3設計D-2が「S2を共通化しない」としたのと同じ理由で、受領済みのC-3を共通化のために変えない。
- **名前を合わせる**：`history.json`、`snapshot.json`、`write.lock`、`.history.<32桁の16進>.tmp`、`.snapshot.<…>.tmp`は、C-3・S2と同じ。値が同じであることは、試験が両方のモジュールの定数を読んで確かめる（ランタイムはC-3をimportしない）。
- **ロックのマーカー**：C-4が作る`write.lock`の中身は`v2_history_maintain.lock\n`＋乱数（32桁の16進）＋改行。`inspect`は残ったロックの中身の先頭から持ち主の種類を示す（S2、C3、C4、EMPTY＝空、UNKNOWN）。種類によって解錠の扱いは変えない（人の判断の材料にするだけ）。
- **公開値の受け取り**：C-3と同じく`type(p) is HistoryPublication`だけを受け取る。書き方・元は、形の誤りで例外が漏れない方法で読む（C-3のN-01と同じ）。C-2の値（HistoryPublication、Reconciliation）については、`_make`・`_of`・`_wrap`・`from_dict`・`object.__new__`・構築・`copy`を使わない。C-4自身の値（RootReport、UnlockPlan）は、既存の`_Frozen`の仕組み（`_make`・`_of`・`_wrap`・`copy.deepcopy`）で作ってよい（第2版、レビューN-02）。

## 4. rootと退避先

### 4.1 名前

| 名前 | 意味 | C-4の扱い |
|---|---|---|
| `history.json` | v2の正本 | 移行で作る、採用で置き換える（元は退避先へ写す） |
| `snapshot.json` | v1（S2）の正本 | 移行の最後に退避先へrenameする |
| `write.lock` | S2・C-3・C-4の共通のロック | 移行・採用・読む操作で作り、終われば外す。残りは解錠で退避先へrenameする |
| `.history.<32桁>.tmp`、`.snapshot.<…>.tmp` | C-3・C-4、S2の一時ファイル | 残りは解錠で退避先へrenameする。移行・採用はこれがあれば止まる（store_artifact_present） |
| `quarantine/` | 退避先の親 | 最初の退避で作る。中の`<64桁の16進>`だけを見る |
| `quarantine/<key>/` | 1回の操作の退避先 | `MANIFEST`、その操作が置く名前、`.q.<32桁>.tmp`（C-4の一時ファイル）だけを許す |
| そのほか | — | 見ない（S2・C-3と同じ） |

`quarantine/`と`quarantine/<key>/`は、リンクでない実ディレクトリで、rootと同じst_devであることを毎回確かめる（違えばmaintenance_quarantine_invalid）。renameが同じファイルシステムの中で完結するためである。

### 4.2 rootの状態と操作

| 状態 | inspect | read_original | unlock | migrate | adopt |
|---|---|---|---|---|---|
| 空 | 報告（EMPTY） | store_uninitialized | maintenance_nothing_to_unlock（計画） | maintenance_state_unexpected／empty | store_uninitialized |
| history.jsonだけ | 報告（V2、読めるか） | 生のバイト | 同上 | 退避先が完了済みなら完了（resumed）、でなければmaintenance_state_unexpected／v2_present | 元バイトなら実行。候補（とその延長）で退避先が完了済みなら完了（resumed）。他はpublication_stale／raw |
| snapshot.jsonだけ | 報告（V1_ONLY） | 生のバイト | 同上 | 実行 | store_layout_unsupported／v1_only |
| 両方 | 報告（V1_AND_V2） | 生のバイト | 同上 | history.jsonが候補で、snapshot.jsonが元で、退避先があれば残りのrenameだけ。他はmaintenance_state_unexpected／v1_and_v2 | store_layout_unsupported／v1_and_v2 |
| 一時ファイルの残り | 報告（名前・種類・識別値） | 生のバイト（止まらない） | 退避先へ移す | store_artifact_present | store_artifact_present |
| ロックの残り | 報告（持ち主の種類・識別値） | store_busy | 計画にロックがあれば、それを排他として使い、最後に移す | store_busy | store_busy |

read_original・read_set_aside・migrate・adoptは、C-3と同じくロックを取る。inspectはロックを取らない（残ったロックを報告するため）。inspectの結果は計画の材料にすぎず、実行はロックの下で状態をもう一度確かめる。

### 4.3 退避先の名前（a6340c3 §5.5の改め）

a6340c3は`quarantine/<依頼ID>/`を案としていた。本書は**keyを公開値のpublication_hash（移行・採用）または解錠計画のplan_hash**にする。理由は3つある。

1. 中断の後に、元の計画と**同じ入力**（requested_atを含む。§5.4）で作り直した公開値は、同じhashになる（C-2の作り手は決定的）。同じ操作がいつも同じ退避先を見つけるので、再開の規則が単純になる。
2. 64桁の16進なので、ファイル名として安全である。依頼IDの文字種や長さに頼らない。
3. 依頼IDを使い回しても、別の操作の退避先と衝突しない。

依頼IDとplan_hashはMANIFESTに記録するので、人が辿ることはできる。

### 4.4 MANIFEST

`quarantine/<key>/MANIFEST`は、退避する前に書く。正規化したJSONをUTF-8で書いたもので、キーは次の8つに固定する。

    {format:"soxl-v2-quarantine/1", operation: "UNLOCK"|"MIGRATION"|"ADOPTION", key, request_id,
     plan_hash, publication_hash (解錠ではnull), writers_stopped (true/false),
     targets: [{name, kind, raw_sha256, raw_size}]}

- パス、時刻、自由文は入れない。
- 中身は公開値（または解錠計画）だけから決まる。だから再開の時は、今書くはずのバイトと完全に一致するかで確かめる。
- 書くときは退避先の中の一時ファイル（`.q.<32桁>.tmp`）に書き、fsyncしてから1回のreplaceで`MANIFEST`にする。MANIFESTは「無い」か「完全」のどちらかになる。
- MANIFESTのtargetsの識別値は、ロックの下で読んだバイトから作ったもの（移行ではsnapshot.json、採用ではhistory.json）と、公開値の識別値（source_v1、expected）の両方に一致する。どちらから写しても同じバイトになる。規則4（a6340c3 §4）の要点は、**ロックの下で読んだバイトがcheck_publicationの照合を通った後にだけ、MANIFESTと退避先を作る**ことで、受入と欠陥注入はこの順序を確かめる（第2版、レビューN-03）。

### 4.5 API と値

- `HistoryMaintenance(root, writable=False, durability=STRICT, *, _ops=None)`。引数の検査はC-3と同じ。
- `inspect() -> RootReport`：不変の値で、次を持つ。
  - layout：EMPTY／V2／V1_ONLY／V1_AND_V2。
  - history：識別値と、read_history_bytesで読めるか。
  - v1：識別値。
  - artifacts：ロック・一時ファイルの、名前、種類、通常のファイルか、持ち主の種類、識別値（raw_sha256、raw_size、st_dev、st_ino）。
  - quarantine：key、MANIFESTの要約（operation、request_id、targetsの名前）、中の名前。
  - パスは持たない。
- `read_original(name) -> bytes`：nameは`history.json`か`snapshot.json`。ロックの下で読む。検査も変更もしない。
- `read_set_aside(key, name) -> bytes`：`quarantine/<key>/<name>`をロックの下で読み、MANIFESTのtargetsの識別値と一致するときだけ返す（違えばmaintenance_set_aside_mismatch）。
- `plan_unlock(report, request_id, writers_stopped) -> UnlockPlan`：純粋。
  - `writers_stopped is True`でなければmaintenance_declaration_missing。1などの真値も拒否する。
  - 対象が無ければmaintenance_nothing_to_unlock。
  - 通常のファイルでない対象（ディレクトリ、リンク）があればmaintenance_target_unsupported。人が手で扱う。
  - bodyは`{operation:"soxl-v2-maintenance-unlock/1", request_id, writers_stopped:true, targets}`。targetsは一時ファイルを名前の順に並べ、ロックを最後に置く。
  - plan_hashはbodyのdigest_of。
- `unlock(plan, confirmed_plan_hash)`、`migrate(publication, writers_stopped)`、`adopt(publication)` -> `MaintenanceResult`。
  - 結果は不変で、status（UNLOCKED／MIGRATED／ADOPTED）、key、resumed、history（解錠ではNone）、persistence_levelを持つ。
  - 正常に終わったときだけ返る。通知の権利ではない。

## 5. 手順

### 5.1 明示解錠（D-3）

1. 計画の型・形・hashを確かめ、人が確認したhash（confirmed_plan_hash）と一致することを確かめる（違えばmaintenance_plan_unconfirmed）。書込み可とrootも確かめる。
2. 排他をとる。
   - 計画にロックがあれば、その残ったロックがこの操作の排他になる（ほかの書き手は作れない）。新しいロックは取らない。
   - 計画にロックが無ければ、C-4のロックを取る。
3. 保存水準を確かめる（STRICTならディレクトリのfsyncの確認。Windowsのstrictは拒否）。
4. rootを一覧し、状態をもう一度確かめる。
   - 今あるロック・一時ファイル（自分のロックを除く）が、計画の対象の部分集合であること。
   - rootにある対象は、inodeが計画と同じこと。
   - rootに無い対象は、`quarantine/<key>/`に同じinode・同じバイトであること（前の試みで移した分）。
   - 外れればmaintenance_plan_stale。何も変えない。
5. `quarantine/`と`quarantine/<key>/`を作るか、再開なら見つける。再開では、中身がMANIFEST・対象の名前・`.q.*.tmp`だけで、MANIFESTが今書くはずのバイトと一致すること。
6. MANIFESTが無ければ書く。
7. 対象をtargetsの順にrenameする（ロックは最後）。各renameの直前に、識別値（st_dev・st_ino・バイトのsha256と長さ）が計画と同じこと、行き先に何も無いことを確かめる。
8. STRICTなら退避先とrootのディレクトリをfsyncする。自分のロックを取っていれば外す。

最初のrenameの後の失敗は、maintenance_incompleteになる（primaryに元のcode）。もう一度同じ計画で呼べば、残りだけを移す（手順4の部分集合の規則）。新しいロックや一時ファイルが現れていれば、計画は古いので、inspectからやり直す。

### 5.2 移行の実行（D-4）

1. 公開値の型と書き方を確かめる（CREATEかつMIGRATION以外はstore_operation_unsupported／not_migration）。`writers_stopped is True`、書込み可、rootも確かめる。
2. C-4のロックを取る。一時ファイルの残りがあればstore_artifact_present。
3. 状態で分ける。
   - **snapshot.jsonだけ**（通常）：
     1. snapshot.jsonをロックの下で読む。
     2. check_publication(None, 公開値, そのバイト)で照合する（違えばpublication_stale／source_v1）。
     3. 保存水準を確かめる。
     4. 退避先を作る。
     5. MANIFESTを書く。
     6. 候補を一時ファイル→fsync→所有の確認→replace→（STRICT）rootのfsyncで公開する（C-3の手順）。
     7. snapshot.jsonを退避先へrenameする（直前にバイトが識別値と同じことを確かめる）。
     8. 退避先とrootをfsyncする。
   - **両方**（再開）：history.jsonがreconcileでPUBLISHED（候補そのもの）、snapshot.jsonが公開値のsource_v1と同じ識別値で、退避先のMANIFESTが一致すれば、snapshot.jsonのrenameだけを行う。どれかが違えばmaintenance_state_unexpected／v1_and_v2。
   - **history.jsonだけ**（再開）：history.jsonがPUBLISHEDかPUBLISHED_THEN_EXTENDED（移行の後にC-3の日次の公開があっても可）で、退避先のMANIFESTとsnapshot.jsonの識別値が一致すれば、何も書かずにresumedで完了する。違えばmaintenance_state_unexpected／v2_present。
   - **空**：maintenance_state_unexpected／empty。
4. ロックを外す。

replaceの前の失敗は、C-3と同じcode（store_io_error等）になる。history.jsonは無いままで、snapshot.jsonは元のまま残る。replaceの呼出し以後の失敗はstore_commit_uncertain。snapshot.jsonのrenameの失敗はmaintenance_incompleteで、「両方」の状態が残る。C-3はこの状態を拒否する（store_layout_unsupported／v1_and_v2）ので、旧S2の書き手もv2の書き手も、history.jsonに日次を書き足せない。

### 5.3 採用の実行（D-5）

1. 公開値の型と書き方を確かめる（REPLACEかつADOPTION以外はstore_operation_unsupported／not_adoption）。書込み可とrootも確かめる。採用では停止の宣言を求めない（通常のロックで排他でき、誰のロックも外さず、書き手を入れ替えもしない）。
2. C-4のロックを取る。一時ファイルの残り→store_artifact_present。snapshot.jsonがあればstore_layout_unsupported。history.jsonが無ければstore_uninitialized。
3. history.jsonの元バイトを読み、状態で分ける。
   - **元バイトが公開値のexpectedと同じ**（通常、または再開でreplaceの前）：
     1. check_publication(元バイト, 公開値)で候補を得る。C-3と同じく、publication_invalid・publication_stale以外の拒否はstore_candidate_invalidに包む。
     2. 保存水準を確かめる。
     3. 退避先を作るか、見つける。
     4. MANIFESTを書く。
     5. 写しが無ければ、元バイトを`.q.*.tmp`に書いてfsyncし、replaceで`quarantine/<key>/history.json`にする。STRICTなら退避先をfsyncする。
     6. **写しを読み戻し**、識別値がexpectedと同じことを確かめる（違えばmaintenance_copy_mismatchで、replaceの前に止まる）。
     7. 候補を一時ファイル→replaceで公開する（C-3の手順）。
   - **元バイトでない**：
     - reconcileがPUBLISHEDかPUBLISHED_THEN_EXTENDEDで、退避先のMANIFESTと写しの識別値が一致すれば、resumedで完了する（何も書かない）。
     - それ以外はcheck_publicationの拒否（publication_stale／raw）をそのまま返す。
4. ロックを外す。

正本のファイルが無い時間は生じない（a6340c3 §5.4）。replaceの後で止まると、元バイトはhistory.jsonから消えているが、写しが退避先にある。C-2からの引継ぎの手順は§5.4の3のとおり。

### 5.4 失敗の後の手順（D-6）

どの操作が失敗しても、次の順で進める。cleanupの語は参考にとどめ、残り物の有無は判断に使わない（C-3実装レビューのP-02）。

1. `inspect()`で、ロック・一時ファイルの残りと退避先を見る。
2. 残りがあれば、人が書き手を止めたことを確かめ、`plan_unlock(report, 依頼ID, True)`で計画を作り、計画のhashを見て`unlock(plan, hash)`を呼ぶ。
3. 元の操作をもう一度呼ぶ。プロセスが終わって公開値が手元に無いときは、作り直す。
   - 移行：snapshot.jsonがrootにあれば`read_original`で、退避済みなら`read_set_aside(key, "snapshot.json")`で読み、`publish_migration`に渡す。
   - 採用：history.jsonが元バイトのままなら`read_original`で、でなければ`read_set_aside(key, "history.json")`で読み、`publish_adoption`に渡す（C-2からの引継ぎ）。
   - keyは`inspect`の退避先の要約（operation、request_id）から選ぶ。作り直した公開値のhashが、keyと一致する。
   - 作り直しの条件（第2版、レビューN-01）：
     - 作り直しには、元の計画と同じ入力を使う。request_id、requested_at、移行ではcheck_d・resolutions・sessions・raw_observations、採用ではadopt_count。requested_atは計画のbasisと候補の記録に入るので、違えばplan_hashとpublication_hashが変わり、keyと一致しない。
     - requested_atは、実行の前に計画の入力を控えておく。控えが無ければ、read_original("history.json")で候補の記録から読む（移行の「両方」・「history.jsonだけ」、採用のreplaceの後）。
     - 作り直した公開値のpublication_hashが退避先のkeyと違えば、操作を呼ばずに入力を見直す。移行の「両方」や採用のreplaceの後の状態で違う公開値を呼ぶと、移行はmaintenance_state_unexpected、採用はpublication_staleで止まる（rootは変えない）。
4. 結果がresumed=Trueでも、正常の完了と同じに扱う。

試行の故障の総当たり（§7）で、全1,638通りがこの手順で最終の状態に着いた。

### 5.5 エラー表（追加分）

| 状況 | code／field／phase・rule |
|---|---|
| 計画の型・形・hash | maintenance_plan_invalid／plan／args・type、shape、plan_hash、report_type、request_id |
| 人が確認したhashと違う | maintenance_plan_unconfirmed／plan／args |
| 停止の宣言が無い（True以外） | maintenance_declaration_missing／writers_stopped／args |
| 解錠の対象が無い | maintenance_nothing_to_unlock／store／args |
| 対象が通常のファイルでない | maintenance_target_unsupported／store／args |
| 実行の時に状態が計画と違う | maintenance_plan_stale／store／scan・move |
| 退避先がリンク・別のデバイス・知らない名前・MANIFESTの不一致 | maintenance_quarantine_invalid／quarantine／quarantine・move・read・type、entries、manifest、missing、target |
| 写しを読み戻すと違う | maintenance_copy_mismatch／quarantine／copy |
| 退避したバイトがMANIFESTと違う | maintenance_set_aside_mismatch／quarantine／read |
| 移行・採用で、状態がどの場合にも当たらない | maintenance_state_unexpected／store／scan・empty、v1_and_v2、v2_present、adoption |
| 最初の変更（退避先の作成、MANIFEST、rename）の後の失敗 | maintenance_incomplete／quarantine または lock／manifest、copy、move、lock_release等（primaryに元のcode） |
| 公開値の型・形、書き方 | C-3と同じ（store_publication_invalid／type・shape、store_operation_unsupported／not_migration・not_adoption） |
| ロック、走査、読込み、公開、保存水準、成否不明 | C-3と同じ（store_busy、store_artifact_present、store_layout_unsupported、store_uninitialized、store_root_invalid、store_io_error、store_candidate_invalid、store_lock_ownership_lost、store_commit_uncertain、store_durability_unsupported） |

パス、OSのエラー文、入力値をエラーに入れない（S2・C-3と同じ）。OSの例外は、例外処理（except）の中では固定のエラーを作るだけにし、投げるのはその外で行う。こうすると、OSの例外が`__context__`にも残らない（`raise … from None`は表示を止めるだけで、`__context__`には元の例外が残る。§7）。

### 5.6 保存水準

S2・C-3と同じSTRICT／FILE_SYNC_ONLYにする。STRICTでは、次をfsyncする。

- ファイル：MANIFEST、写し、一時ファイル。
- ディレクトリ：`quarantine/`を作った後のroot、`quarantine/<key>/`を作った後の`quarantine/`、MANIFEST・写し・renameの後の`quarantine/<key>/`とroot。

Windowsのstrictはwindows_strictで拒否する。確認は変更の前に行う。

## 6. 範囲試験（D-8）

### 6.1 前の段階の固定（1行）

tests/v2_history_local/test_c3_09_scope.pyの`END = None`を、受領した最終コミットの完全SHAに替える。

    END = "6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a"   # accepted (review 2049e10); frozen when C-4 began

C-3の範囲試験は自分の範囲の値をHEADから読むので、1行で足りる（2049e10 §4.4の[B][C]で確認済み、試行でも確認）。

### 6.2 C-4の範囲試験

- 新しいディレクトリ`tests/v2_history_maintain/`に`test_c4_*.py`と`c4_helpers.py`（任意で`c4_worker.py`）を置く。`__init__.py`は作らない。
- 範囲試験は`START = "6d69bd7…"`、`END = None`、`REV = END or "HEAD"`の形で書く。git差分・中身・blob・一覧はREVから読み、作業ツリーは読まない。test_c3_09の1行は、C-4自身の差分のハンクとして固定する。
- 範囲の鎖の試験（test_sc_02）が新しい範囲試験を自動で見つけ、`adfdf765→…→d6b0332→6d69bd7→（C-4、END=None）`の鎖を確かめる。試行で、固定後の鎖が通ることを確かめた。
- 試験はtempfileの一時ディレクトリにだけ書く。子プロセスは競合と強制終了の試験だけ。

## 7. 一時環境での試行（2026-11-04、Linux）

**位置づけ**：方式の確からしさを確かめるための使い捨ての試行である。6d69bd7から作ったローカルの作業ツリーで、次を行った。

- C-4のランタイム4ファイル（計1016行）を試作した。
- §6.1の1行の固定と、仮の範囲試験1本を加えた。
- pushしないローカルコミットで試験した。
- 振る舞いは使い捨てのプローブ・故障の総当たり・競合で確かめた。

正式な実装、受入試験、レビューの代わりにはしない。

環境：Linux、Python 3.12.3と3.13.18、`PYTHONDONTWRITEBYTECODE=1`、`-B -W error::ResourceWarning`。Windows、3.10・3.11、unshareによる通信遮断は実施していない。

| スイート | 試作後（3.12／3.13） |
|---|---|
| 既存13スイート（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150） | 全件合格（S2のWindows専用skip 4） |
| C-3 139（test_c3_09のENDを固定） | 全件合格 |
| 仮のC-4範囲試験 1 | 合格（範囲の鎖が新しい開いた範囲を受け入れた） |
| 合計 | **2070件合格**（既存2069＋仮1） |

**プローブ（87項目、すべて期待どおり）**：

- 解錠：C-3・S2・空のロック、一時ファイルだけ（C-4のロックを取る）、ロック＋C-3とS2の一時ファイル（ロックが最後）。
- 解錠の拒否：未確認のhash、宣言なし・真値の1、計画の後に一時ファイルが増えた、同じバイトで別のinodeのロック、対象なし、ディレクトリのロック、読取り専用、型違い。いずれも何も変えない。
- 解錠の中断と再開：2つ目のrenameの故障→maintenance_incomplete→同じ計画で再開。
- C-3実装レビューのP-02の再現：C-3のcreate_exclusiveが作成後に失敗し、cleanupが空でも一時ファイルが残る。inspectが見つけ、解錠の後にC-3が公開できる。
- 移行：通常、宣言なし、採用・GENESISの公開値、v1のバイト違い（publication_stale／source_v1）。
  - renameの故障→「両方」→C-3は拒否→read_originalから作り直した公開値（同じhash）で再開。
  - 解放の故障→store_commit_uncertainとC-4のロックの残り→解錠→read_set_asideから作り直して再開。
  - 完了後の再実行、他人のhistory.jsonがある「両方」、一時ファイル、空のroot。
- 採用：通常（写しが元バイトと同じ、C-3が読める）、完了後に今のバイトで作るとNO_CHANGE、完了後の再実行。
  - replaceの後の解放の故障→解錠→read_set_asideの元バイトからpublish_adoptionで作り直すと同じhash→再開で完了。
  - 写しのreplaceの故障→元のまま→再開。
  - v1あり、別のバイト（publication_stale／raw）、写しの改ざん（maintenance_quarantine_invalidとread_set_asideの拒否）。
- そのほか：C-4のロックでC-3がstore_busy、Windowsのstrictの拒否とfile_sync_onlyの成功、エラーにrootのパスが出ないこと。

**故障の総当たり**：migrate・adopt・unlock×STRICT・FILE_SYNC_ONLYで、故障なしの呼出し列（MaintenanceOpsの17種）を記録した。その各呼出しの前・後に、3種の例外（パス・秘密らしい文字列を含むOSError、FileExistsError、RuntimeError）を1つずつ起こした。

- 対象は1,638通り。
- (1) CoreError以外の例外0。
- (2) 元のバイト（snapshot.json、採用前のhistory.json、残ったロック）はいつもrootか退避先に同じバイトで残った（消失0）。
- (3) history.jsonは元か候補のどちらか（0件の違反）。
- (4) §5.4の手順で全件が最終の状態に着いた（復旧の失敗0）。
- (5) エラーのstr・repr・属性・cause・contextに、パス・秘密らしい文字列が出たもの0。

試作の初回には、次の2つの問題があり、どちらも直して0になった。

- 解錠の再確認のlstatが、裸の例外を漏らす24通りがあった。例外を漏らさない形に直した。
- 例外処理の中で`raise … from None`としていた21か所では、エラーの`__context__`に、パスと秘密らしい文字列を含むOSの例外が残っていた（総当たりで340通り）。固定のエラーを例外処理の外で投げる形（C-3・S2と同じ形）に直した。§5.5の規則と受入C4-19に入れた。

**競合**：6つの子プロセスが同じrootでadopt（またはmigrate）を同時に呼ぶ試行を、10回ずつ行った。毎回、成功（resumed=False）は1回だけだった。ほかはstore_busyか、完了の後の再実行（resumed=True）。最後のhistory.jsonは候補で、rootの名前は`history.json`と`quarantine/`だけだった。

試作の差分（ランタイム4ファイル、test_c3_09の1行、仮の範囲試験1本）は、同じ資料コミットのdocs/specs/V2_HISTORY_MAINTAIN_C4_TRIAL_20261104.diffに参考として保存する。未適用で、SHA-256は§9に記す。プローブ・総当たり・競合のスクリプトは保存しない（実装者は受入試験として作り直す）。実装者は試作を写すのではなく、本書と依頼書の規則に従って作り、違いがあれば結果文書で説明する。

## 8. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | C-4の範囲：v2_history_maintainの6操作（inspect、read_original、read_set_aside、unlock、migrate、adopt）と純粋なplan_unlock。退避先の削除・自動の掃除・日次処理・通知・本番はしない。1つの限定実装として依頼する（§2） | 採用を推奨。解錠と移行・採用を2段に分ける案（C-4a／C-4b）は、退避先・MANIFEST・再開の規則を両方で使うので、範囲試験の固定とレビューが2回になる割に、各段が小さくならない。ただし、小さな単位を望むならこの分け方が自然 |
| D-2 | a6340c3 §5.5の未決への回答：停止は人の宣言（解錠計画と移行の引数、MANIFESTに記録、証明とは書かない）、保守用の新しいマーカーは作らずC-4がwrite.lockを持つ、退避先は`quarantine/<publication_hash または plan_hash>/`でMANIFEST先行・同じ保存水準、再開は同じ操作をもう一度呼ぶ（部分集合と識別値の一致）、実行場所・本番はS4（§0、§4.3、§5） | 採用を推奨。退避先の名前を依頼IDにする元の案は、再開時に同じ場所を確実に見つけられず、使い回しで衝突するので推奨しない |
| D-3 | 明示解錠：計画（識別値で名指し、人の宣言、hashの確認）、計画にロックがあればそれを排他にして最後にrename、無ければC-4のロックを取る、一時ファイルもrename（写して消すのではない）、識別値の再確認、部分集合での再開（§5.1） | 採用を推奨。写してから消す元の案は、写しかけの状態と二重のバイトが生じ、識別値（inode）も変わる |
| D-4 | 移行の順序：ロック→snapshot.jsonの照合→MANIFEST→history.jsonの公開→snapshot.jsonのrename。「両方」の状態の再開と、完了済みの判定（§5.2） | 採用を推奨 |
| D-5 | 採用の順序：ロック→元バイトの照合→MANIFEST→写しと読み戻し→候補の公開。replaceの後の中断は、退避した元バイトからpublish_adoptionで作り直して再開（C-2からの引継ぎ）。採用では停止の宣言を求めない（§5.3） | 採用を推奨 |
| D-6 | C-3実装レビューP-02と失敗の後の手順：残り物はディレクトリの一覧だけで判断し、cleanupの語に頼らない。失敗の後はinspect→解錠→同じ操作の手順（§5.4）。ネットワークドライブ・同期フォルダ上のrootは推奨しない | 採用を推奨 |
| D-7 | S2・C-3との関係：FileOpsを継承したMaintenanceOps（mkdirとrenameだけを足す）、C-3は変えず内部も呼ばない、名前の定数は試験で一致を確認、ロックのマーカーは`v2_history_maintain.lock`、公開値は`type(p) is HistoryPublication`だけでC-4は構築しない（§3） | 採用を推奨。C-3から共通部分を切り出す案は、受領済みのC-3を変えるので推奨しない |
| D-8 | 範囲試験：test_c3_09のEND＝6d69bd7（1行）と、自分の開いた範囲試験を同じコミットで足す。試験は一時ディレクトリにだけ書き、子プロセスは競合・強制終了の試験だけ。次の段階の模擬を受入に含める（§6） | 採用を推奨 |
| D-9 | C-4の実装単位と担当：対になる依頼書の範囲（新しいパッケージ、新しい試験ディレクトリ、test_c3_09の1行、結果文書）。担当はSonnet 5.5・high | 採用を推奨。規則と試行の差分が具体的で、手順はC-3の写しが多い。ランタイムはC-3の約2倍（試行で1016行）なので、矛盾や規則の追加が必要なら止めて主担当へ返す。Opusに任せる案もあるが、C-3と同じ型の作業なので必要性は小さい |

D-1〜D-9を一組で判断する。今回の文書作成と一時環境の試行は採用ではない。C-3の受領を、C-4の実装承認にしない。S4、全体稼働、本番の保存先・資格情報・通知・定時実行は今回の採否に含まない。

範囲外として残すもの：

- C-3実装レビューの提案P-01（test_c3_06の試験2件。次にtest_c3_06を触る機会）とP-03（受領記録の注記）。
- C-3設計レビューの提案P-01〜P-07。
- C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03。
- B-4§7.1の既知の制限（案a）、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02。
- U-03、U-07。

既知の制限：

1. 停止の宣言は証明ではない。S2の書き手は`write.lock`の中身を見ないので、宣言が誤っていて解錠の後に旧S2の書き手が動けば書ける。移行の後に旧S2の書き手がsnapshot.jsonを作れば「両方」になり、C-3が止める（a6340c3 §5.4、C-3設計§8(1)）。
2. 識別値（st_dev、st_ino、バイトのsha256と長さ）は、消して同じバイトで作り直したファイルとinodeが再利用された場合を区別できない。このときバイトは同じなので、退避するものは変わらない。
3. inspectはロックを取らないので、変わりつつあるrootの一瞬を報告することがある。実行はロックの下でもう一度確かめる。
4. 退避先は消さない。不要になった退避先の扱いは人が決める（範囲外）。
5. 一時ファイルだけの解錠（C-4のロックを取る）が途中で止まりC-4のロックが残ると、次の計画はそのロックを含む別のkeyになる。前の退避先は移した分を持ったまま残る（両方とも保持する）。
6. C-4自身のエラーのcleanupにも、C-3と同じく語が付かない残り物があり得る（§5.4の手順で扱う）。
7. 実Windows、物理電源断、ネットワークドライブ・同期フォルダ上のroot、ユーザーPCでの確認は未実施。Windowsのrename・mkdir・ディレクトリの扱いは、実機で確かめるまで未確認とする。
8. Pythonの内部を直接呼べば公開値の形の値を作れる（C-2§8）。C-4は型と静的監査で防ぐだけ。

## 9. 作業記録

- 担当モデル：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
- 開始時（2026-11-04T02:50Z頃）に、C-3依頼書§7の78参照を`git ls-remote`の完全SHAで照合し、78件とも一致した。加えて、次の4本を新たに保護参照へ加え、計82参照とした。
  - docs/v2-history-local-c3-20261104（6ad9852）
  - docs/v2-history-local-c3-review-20261104（213bcb7）
  - feat/v2-history-local-c3-20261104（6d69bd7）
  - docs/v2-history-local-c3-impl-review-20261104（2049e10）
  - 終了時の照合は、依頼書§7と結果の報告に記す。
- 本書、依頼書、試行の差分の3ファイルだけを、6d69bd7から作った新しい資料ブランチdocs/v2-history-maintain-c4-20261104に追加した。製品コードの変更、PR、Actions、送信、新しい市場計算は0。一時環境の作業ツリーとローカルコミットはpushしていない。
- 試行の差分docs/specs/V2_HISTORY_MAINTAIN_C4_TRIAL_20261104.diffのSHA-256は fa9a60e2e24a6af5ecaf742ca2308918231c78c8e0ab49abb988875d31a58e69。一時環境の6d69bd7→試作後の`git diff`の出力そのままで、対象はv2_history_maintain、tests/v2_history_local/test_c3_09_scope.py、tests/v2_history_maintain。
- モデル別の利用量は未計測。

## 10. 第2版の改訂（2026-11-04）

初版ce4fd28へのOpus 5.5・highの設計レビュー（74c93b1、docs/v2-history-maintain-c4-review-20261104のdocs/reviews/V2_HISTORY_MAINTAIN_C4_DESIGN_REVIEW_20261104.md、重大0・通常3・提案6）の通常N-01〜N-03だけを反映した。提案P-01〜P-06は任意で、反映していない。D-1〜D-9の内容（§8の表）と試行の差分（§7）は変えていない。試行のコードは改訂後の規則を満たす（レビュー§6）。

| レビュー | 改訂した箇所 | 内容 |
|---|---|---|
| N-01（通常） | §4.3の理由1、§5.4の手順3。依頼書§3「失敗の後の手順」、C4-10、C4-12 | 公開値の作り直しは、元の計画と同じ入力（requested_atを含む）を使う。requested_atの控え方・読み方、hashがkeyと違うときは呼ばないことを書いた。受入に、計画を使い回さずprepare_\*を呼び直す作り直しと、別のrequested_atではhashが違いrootを変えずに止まる項を足した |
| N-02（通常） | §2.3の標準ライブラリ、§3の公開値の受け取り。依頼書§3、C4-20 | `_make`・`_of`等の禁止をC-2の値に絞り、C-4自身の値は`_Frozen`の仕組みで作ってよいとした。標準ライブラリにcopyを足した |
| N-03（通常） | §4.4の最後の項。依頼書§3「退避の証拠」、C4-13、欠陥注入10 | MANIFESTはどちらから写しても同じバイトになるので、確かめるのは「ロックの下の読込み→照合→MANIFEST」の順序とした。欠陥注入10を、MANIFESTを読込み・照合より前に書く変異に替えた |
