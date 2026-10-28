# V2 S2 ローカル実ファイル保存 限定実装 結果

2026-10-28（日本時間）。担当：Sonnet 5.5・high。本書はS2の限定実装の結果記録であり、**ローカル保存を本番正本に採用したという意味ではない**（U-01／U-11／U-13は未決のまま）。S3／S4、PR、本番接続は含まない。

## 1. 結論

- 受入条件 B-01〜B-10 を実施した。**実Linux上で全て合格**。ただし **実Windowsは未実施**（Windows実機専用3件はLinuxでは実行されず、合格にも数えていない）、**物理的な電源断は未試験**、ユーザーPCでの既存181件の確認も後日のまま。
- 既存**367件**（コア197＋保存ドメイン170）は無編集で、Python 3.10.20／3.11.17／3.12.3／3.13.17の全てで合格（失敗0・error0・skip0）。
- 新規**100件**中、**97件実行・全合格、3件はWindows実機でのみ実行（Linuxではskip＝未実施）**。4版すべて同じ。
- 範囲外の変更は必要なかった。既存ファイルの差分は0（新規ファイルのみ）。

## 2. 固定した版・環境

| 項目 | 内容 |
|---|---|
| 資料（設計・依頼） | docs/v2-local-store-s2-20261028 の **73cec624cb73205ac63ca92e26df2b6f70019b16**。設計書 docs/specs/V2_LOCAL_FILE_STORE_S2_DESIGN.md の blob `e42f9f035e265cfdcf103a004aafde83b0435d12`、依頼書 docs/tasks/V2_LOCAL_FILE_STORE_S2_REQUEST.md の blob `937c42b820f98ca90c93f7dac6fae5d89ef2971d`。作業中の更新には追従していない |
| コード開始点 | **2d09db770d21480202c4c603e02c2aec5e030012**（fix/v2-core-fg-numeric-overflow-20261028） |
| 実装ブランチ | feat/v2-local-file-store-s2-20261028（新規。既存ブランチは上書きしていない） |
| **試験対象（コード＋試験）** | **81ac624241d6d3709a3d7650e92da12f4060bb7c** |
| 保存最終 | 試験対象に本書だけを追加したコミット（完全SHAは完了報告に記載。本書自体はそのSHAを含められない）。試験対象との差分は本書1ファイルのみ |
| モデル・エフォート | 作業セッションのメタデータ（get_session）で configured_model `claude-sonnet-5-5[1m]`、last_served_model `claude-sonnet-5-5`、effort_level `high` を確認。モデル自身の申告ではなくセッション記録による確認 |
| OS／FS | Ubuntu 24.04.5 LTS、カーネル 6.18.44（クラウドVM）。試験用rootは `/tmp` 配下の専用ディレクトリで、ファイルシステムは ext4（`/dev/vda`、`df -T` で確認）。ローカル・非同期の専用ディスク前提 |
| Python | 3.10.20（uv単体インタプリタ、スクラッチ領域。取得だけが通信を使用）、3.11.17、3.12.3、3.13.17（システム） |
| git | `core.autocrlf=false`（作業クローン、試験用クリーンクローンとも）。autocrlf=true は未試験 |
| 同期モード | strict（既定）と file_sync_only の両方を実Linuxで実行 |

## 3. 実装

追加したのは次の新規ファイルだけ（既存ファイル差分0）。

| 場所 | 内容 |
|---|---|
| v2_persistence/local/store.py | `LocalFileStore(root, writable=False, durability="strict")`：`read()`／`initialize(genesis)`／`commit(plan)` |
| v2_persistence/local/fsops.py | OSに触る唯一の層（`FileOps`）。試験は私的引数 `_ops` で記録・故障注入版に差し替える（契約外の試験用の継ぎ目） |
| v2_persistence/local/errors.py | `LocalStoreError`（`PersistenceError`の子）。code／field に加え `phase`（固定識別子）、`cleanup`（後始末で残ったものの固定識別子）、`primary`（後始末失敗が置き換えた元のエラーcode） |
| v2_persistence/local/results.py | `LocalCommitResult`（status／committed／snapshot／persistence_level）、`LocalInitResult`（initializeの戻り値。依頼に定めが無いので追加。status=INITIALIZED） |
| tests/v2_persistence_local/ | 試験9ファイル、独立プロセスworker（worker.py）、補助（l_helpers.py）、欠陥注入（sensitivity_check.py） |

保存形式：専用rootに `snapshot.json`（S1のencode_snapshotのUTF-8バイト列。S1の全履歴入りSnapshot一つ。schema_version=1、CORE_SHA=b616b4e…は不変）、`write.lock`、`.snapshot.<ランダム>.tmp` だけ。S1の検査・市場計算は複製せず、既存の `decode_snapshot`／`validate_snapshot`／`append_event`／`prepare_day`／`reconcile` を使う。

公開手順（commit）：引数・書込許可 → root検査 → write.lockを O_CREAT|O_EXCL で作成（所有マーカーと作成時のinodeを保持）→ 一時ファイル残留の検査 → 正本を読んで全検査 → 期待先頭のCAS → 候補の全検査 → 同期モードの可否確認（strictはPOSIXでrootディレクトリを実際に開いてfsync）→ 同じrootに一時ファイルを排他的に作成 → 全バイトwrite（短いwrite対応）→ flush → ファイルfsync → close → ロック所有の再確認 → `os.replace` を1回 → strictなら親ディレクトリfsync → 所有確認してロック解放。待機・期限・自動強奪・自動再試行・自動解錠・復旧APIは作っていない。

### エラー（code／field／phase）

S1由来のエラー（snapshot_invalid、unsupported_schema、unsupported_event、concurrent_conflict等）はそのまま通す（phase属性なし）。新規のcode：

| code／field | phase | 備考 |
|---|---|---|
| store_root_invalid／root | root, read | root不正、root・snapshot.jsonのリンク、通常ファイル以外 |
| store_config_invalid／durability, writable | args | |
| store_read_only／store | args | |
| store_busy／lock | lock_acquire | 既存のロック（種類を問わず）。待たない |
| store_lock_ownership_lost／lock | lock_ownership | 書込直前、または解放時に所有が変わっていた |
| store_artifact_present／store | scan | 残留一時ファイル |
| store_uninitialized／store、already_initialized／store | read | |
| cas_conflict／head | cas | |
| store_durability_unsupported／durability | durability_probe | rule=windows_strict または directory_sync |
| store_io_error／lock, snapshot, root | lock_acquire, scan, read, tmp_create, write, flush, file_sync, close, lock_release | 公開前の失敗、後始末の失敗 |
| store_commit_uncertain／snapshot | replace, dir_sync, lock_release, lock_ownership | `os.replace` 呼出し開始以降の失敗（実際は置換済みの場合を含む） |

OSErrorのパス・文言・入力値はエラーに入れない。OSErrorは連鎖させず（`__cause__`／`__context__` は None）、試験で確認した。

## 4. 実測結果

通信遮断：試験は全て `unshare -rn`（新しいネットワーク名前空間。外部へ出られないことを別途確認済み）の中で実行。加えて試験の道具がプロセス内でソケット生成を無効化し、workerも同じ道具を読むため同じ遮断を引き継ぐ（試験で確認）。クリーンクローン（`git clone -c core.autocrlf=false --branch feat/v2-local-file-store-s2-20261028`、HEAD=81ac624、`git status` 差分0）で実行した。

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_core                         # 既存コア197
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence -p "test_*.py"   # 既存保存ドメイン170
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p "test_*.py"   # 新規100

| Python | 既存コア | 既存保存 | 新規（実行） | 新規skip | 失敗・error | 終了コード（3本） |
|---|---|---|---|---|---|---|
| 3.10.20 | 197 合格 | 170 合格 | 97 合格 | 3（Windows実機専用） | 0 | 0 / 0 / 0 |
| 3.11.17 | 197 合格 | 170 合格 | 97 合格 | 3 | 0 | 0 / 0 / 0 |
| 3.12.3 | 197 合格 | 170 合格 | 97 合格 | 3 | 0 | 0 / 0 / 0 |
| 3.13.17 | 197 合格 | 170 合格 | 97 合格 | 3 | 0 | 0 / 0 / 0 |

既存367件と新規100件は別集計。新規の内訳（ファイル別、件数は実測で、受入項目の数ではない）：B-01〜B-03 = 22、B-04 = 5、B-05／B-07 = 24、B-06 = 5、B-08 = 21、B-09 = 14（うち3件が実Windows専用）、B-10 = 9。

不安定さの確認：新規スイートをクリーンクローン・通信遮断下で3.10.20と3.13.17でそれぞれ10回繰り返し、失敗した回は0。

## 5. 受入条件B-01〜B-10

| ID | 結果 | 主な根拠 |
|---|---|---|
| B-01 | 合格（Linux） | 既存367件を無編集で4版合格。JSON往復（ファイルのバイト列＝encode_snapshot）、`validate_snapshot` による全再計算、MemoryStoreの8日連鎖とファイルの連鎖で同一Snapshot・現在状態、CORE_SHA／schema不変（定数を試験）。 |
| B-02 | 合格（Linux） | 未初期化のread／commit拒否（store_uninitialized、rootに何も残らない）、明示GENESIS初期化、別インスタンス・別プロセスで読取、二重初期化（already_initialized、ファイル不変）、APPLY入り初期化の拒否、既定read_onlyで正本不変（mtime・inodeも比較）、readがロックを作って消すこと。設定エラーとroot不正（自動作成しない）も。 |
| B-03 | 合格（Linux） | 準備だけではファイル不変、成功時のみAPPLY1件・seq+1・過去イベント値不変、NO_COMMIT／ALREADY_APPLIEDは書かない（トレースでtmp作成・replaceが無いことを確認）、新インスタンス・別プロセスの後も同日追記0、古い計画の再commitはcas_conflict、戻り値の入れ子改変で正本・ストアは不変、細工した計画は候補検査で拒否されファイル不変。 |
| B-04 | 合格（Linux） | 独立Pythonプロセス2本。両者が同じ先頭を読んだ（READY）後に標準入力のGOで同時に開始（sleep依存なし）。同内容／異内容の同D／異なるDの3種で各6回の自由競合：成功は常に1、敗者は store_busy。別途の強制順序：Aがロック保持中（一時ファイル書込済み、置換直前で停止）にBとプロセス内インスタンスがstore_busy、Aのロックは不変、A完了後にBが同じ古い計画を明示再呼出しでcas_conflict、読直し後のS1 reconcileは ALREADY_APPLIED／concurrent_conflict／REPLAN_REQUIRED。自動再追記は無い。別途、Bが先に読み、Aが完了した後にBが進めるとcas_conflict（別プロセス）。 |
| B-05 | 合格（Linux） | 実ファイルでの順序（write→flush→ファイルfsync→close→replace→directory fsync→ロック解放、ロック取得が最初、probeがtmp作成より前）、短いwrite（7バイトずつ）、0バイトwriteの停止、公開前の各失敗（tmp作成・write・flush・fsync・close）で旧正本不変・tmpとロック掃除済み、後始末失敗（tmp_left）と次回の停止、ロック作成途中の例外（自分の半端なロックを除去／除去失敗でlock_leftと次回store_busy）、解放失敗が元のエラーを隠さない（primary）、ロック所有変更3種（差替え・同inode別内容・同内容の別inode）、一覧取得失敗、他のファイルを触らないこと。 |
| B-06 | 合格（Linux） | 別プロセスを `os._exit(77)`（finallyなし）で、ロック取得後／部分書込後／ファイルfsync後／置換直前／replace後／directory fsync後に終了（commitとinitialize）、さらにSIGKILL2件。子の終了確認後に生バイトを診断：正本は旧版か完全な新版のみ（初期化前は不存在）、部分書込のtmpは新版の接頭辞、ロックは残る。次回のAPIは store_busy、テスト側がロックだけ消すと tmp が残る場合は store_artifact_present（自動採用・削除なし）。tmpも消した後に旧／新版が読め、新版はreconcileでALREADY_APPLIED。死んだworkerのロックを越える2つ目のcommitは行われない。 |
| B-07 | 合格（Linux） | replaceを実行してから例外、replaceが効果なく例外（それでもuncertain、再試行なし）、置換後のdirectory fsync失敗、置換後のロック解放失敗、置換後の所有喪失、file_sync_onlyでの置換失敗、replace失敗とロック解放失敗の同時発生がいずれも store_commit_uncertain（COMMITTEDなし）。読めた新版のreconcileは論理存在だけ（ALREADY_APPLIED）、別の書込者の別内容は concurrent_conflict で「自分の成功」とみなさない。 |
| B-08 | 合格（Linux） | 欠損、空、途中JSON、重複キー、NaN、非UTF-8、BOM、5000桁整数、hash／状態／schema／core_sha／イベント種の違反を read・commit・initialize で拒否（ファイル不変、ロック解放）。残留tmpは昇格せず store_artifact_present。root・snapshot.json のシンボリックリンク（外側のファイルのバイト・mtime不変）、ディレクトリ・FIFO（openする前に拒否）、ロックがリンク／ダングリング／ディレクトリ（store_busyで外側に何も作らない）、構築後にrootがリンクに差し替わる場合、worker実行中に所有が変わったロックを消さないこと。 |
| B-09 | **Linuxのみ合格、実Windowsは未実施** | 実Linux：strict既定（probe＋directory fsync、persistence_level=FILE_AND_DIRECTORY_SYNC）、file_sync_only明示（FILE_SYNC_ONLY、directory fsyncなし）、別プロセスでの水準の確認。**Linux上のWindows分岐の模擬**（`is_windows()` を差し替え。Windows実機の合格ではない）：strict拒否（公開前、tmp作成なし、黙った格下げなし）、readは拒否しない、file_sync_onlyは通る、POSIXでdirectory fsyncが使えない場合の拒否（EINVAL等4種）、probe成功後の同期失敗は成功に変換しない。**実Windows専用3件（file_sync_only往復と置換、strict拒否、プロセス競合）はコードのみ用意し、実行していない**。 |
| B-10 | 合格（Linux） | 全試験を通信遮断で実行、workerもソケット遮断を継承（workerからの確認）。ランタイム（v2_persistence/local）のimportをASTで検査：標準ライブラリ（os、stat、secrets、sys、dataclasses、typing）のみ、時計・環境変数・ネット・プロセス・sleepの名前が無いこと、管理名が3つだけ、解錠・復旧・再試行・通知等の公開名が無いこと。注入したOSErrorの秘密風パス・文言が公開エラーに出ないこと（14箇所×前後注入、エラー28件超で確認）。 |

試験の区分（混同しない）：**実ファイル**（ほぼ全て）、**実プロセス**（B-04、B-06、B-02／B-03／B-08の一部、workerによる遮断確認）、**故障注入**（`FileOps`差替えによるB-05／B-07／B-09、専用root内のみ。ディスク満杯・権限変更・電源断は行っていない）、**未実施**（物理電源断、実Windows）。強制終了（実プロセス）と故障注入の結果は別の試験で、混ぜていない。

### 欠陥注入

`tests/v2_persistence_local/sensitivity_check.py`（手動実行。作業ツリーの複製の `v2_persistence/local` に欠陥を1つ入れ、新規スイートが失敗することを確認する）。27件の欠陥（fsync欠落、O_EXCL欠落、古いロックの自動奪取、CAS欠落、候補検査欠落、所有確認欠落、uncertainの誤分類、tmp掃除欠落、リンク受理、Windows strictの黙認、短いwrite未対応、最終バイト欠落、不正UTF-8の黙った修復など）を全て検出した。検出できなかったM12（rootのリンク検査削除）は、POSIXではlstat＋ディレクトリ判定が既にリンクを除外するため**同値変異**として対象外にした。Windowsの再解析ポイント（junction）の検査は実機で未確認。

## 6. 自由競合の観察

自由競合（B-04）の3種×20回（診断用の別実行、合否判定ではない）では、敗者は常に store_busy で、cas_conflict になる場面は出なかった（先頭を読んでから同時開始すると、先に動いた側が書込の間ロックを持つため）。cas_conflict は、読んだ後に相手が完了する強制順序の試験（プロセス内・別プロセス）で確認している。

## 7. 保護参照

開始時と終了時にgit ls-remoteで確認。13参照とも依頼書の完全SHAのまま変化なし（main 31144d9…、920e695…、647aeac…、1a54a85…、b616b4e…、b43205c…、425df80…、da24fcd…、b9586d6…、d44155b…、08400ac…、2d09db7…、a235b76…）。資料ブランチ docs/v2-local-store-s2-20261028 も 73cec62 のまま。書込んだのは新ブランチ feat/v2-local-file-store-s2-20261028 のみ。PR・Actions・外部送信・本番操作なし。

## 8. 保留事項・限界

1. **実Windows未実施**。file_sync_onlyの実機確認、置換（既存ファイルの上書き）、プロセス競合、再解析ポイントの扱い、ロックのinode比較（Windowsでのst_ino）は未確認。Linux上の分岐模擬は実機の代わりにならない。実Windows専用3件は用意済み（Windowsで同じコマンドを実行すれば実行される）。
2. **物理電源断は未試験**。COMMITTEDは指定した同期手順と後始末の完了を意味し、ドライブキャッシュ・全ファイルシステムの電源断耐久の保証ではない。強制終了（プロセス）の試験と区別する。
3. ユーザーPCでの既存181件の確認は後日のまま。autocrlf=true も未試験。
4. 前提：信頼できるローカル・非同期の専用フォルダ。NFS／SMB／同期フォルダは対象外で、ファイルシステム種別を自動判定したという主張はしない（実測はext4のみ）。ロックの確認と削除の間に第三者が差し替える攻撃には防御しない（設計§4）。root祖先のシンボリックリンクは許容し、解決後のパスを使う（root自体と管理対象のリンクは拒否）。
5. 管理対象の**ハードリンク**（nlink>1）は拒否していない（置換は新しいinodeを作るので他の名前は変わらない）。
6. 契約に定めが無く私が決めた点：initializeの戻り値（LocalInitResult）、後始末情報の属性（phase／cleanup／primary）、uncertain後もロックの正常解放を試みる（§8の「解放できた場合は明示的にreadして照合できる」に従う）、残留一時ファイルの検出は「`.snapshot.` で始まり `.tmp` で終わる名前」、`KeyboardInterrupt`等の`BaseException`は捕捉せず残留物は強制終了と同様に扱う。S1由来のエラーにはphase属性が付かない。
7. 自由競合では敗者が常にstore_busyだった（§6）。cas_conflictの観察は強制順序の試験による。
8. S3（ACK・復元・明示的解錠）／S4（保存先・台帳・実行場所・資格情報・通知）は未着手。残留ロック・一時ファイルの掃除は試験側の明示操作でのみ行い、製品に自動復旧は無い。

## 9. 再現手順

    git clone -c core.autocrlf=false --branch feat/v2-local-file-store-s2-20261028 https://github.com/Rocky009-jp/soxl-alert
    cd soxl-alert && git checkout 81ac624241d6d3709a3d7650e92da12f4060bb7c     # 試験対象
    <python> -B -m unittest discover -s tests/v2_core
    <python> -B -m unittest discover -s tests/v2_persistence -p "test_*.py"
    <python> -B -m unittest discover -s tests/v2_persistence_local -p "test_*.py" -v
    # 通信遮断を強める（Linux）：unshare -rn <python> -B -m unittest ...
    # 欠陥注入（手動）：<python> -B tests/v2_persistence_local/sensitivity_check.py
    # Python 3.10が無い場合：UV_PYTHON_INSTALL_DIR=<スクラッチ>/uvpy uv python install 3.10

既存367件の研究fixtureは完全クローンで揃う。fixtureが無い環境で独立に確認する場合、その1件は「未実施」と書き、合格・skipに数えないこと（S1結果文書と同じ扱い）。
