# V2 S2 ローカル実ファイル保存 受領レビューと限定修正依頼

2026-10-28（日本時間）。主担当による固定版の読取レビューと独立Windows確認。
実装コードは変更していない。S3／S4、本番採用、送信、PRの承認ではない。

## 1. 対象と結論

- 資料：73cec624cb73205ac63ca92e26df2b6f70019b16 の S2設計・依頼書（blobはそれぞれ e42f9f035e265cfdcf103a004aafde83b0435d12、937c42b820f98ca90c93f7dac6fae5d89ef2971d）。
- 基準：2d09db770d21480202c4c603e02c2aec5e030012。
- コード・試験：81ac624241d6d3709a3d7650e92da12f4060bb7c。
- 受領最終：00e7f84806ce34dc8754a0fc558870db145ade68、feat/v2-local-file-store-s2-20261028。
- 結論：**重大0件・通常2件・任意の文書提案2件。** 正本置換・CAS・同期水準の分離・強制終了時の停止という基本構成は契約に沿う。R-01／R-02だけをS2内で直してから完了確認へ進む。新しい全面設計レビューは追加しない。

両不具合の再現でも、旧snapshot.jsonのバイト列は不変で、COMMITTEDを返していない。誤った市場計算、二重追記、他者のロックの削除は今回の確認では起きていない。未確認範囲全体に安全を保証する意味ではない。

## 2. 通常の指摘

| ID | 根拠 | 再現・影響 | 最小修正と確認 |
|---|---|---|---|
| R-01 複数の後始末失敗で残留情報が欠ける | v2_persistence/local/store.py:215〜241、特に最終行の新規LocalStoreError。設計§5・§8・§9、B-05の「後始末失敗を隠さない」 | 一時ファイルwrite失敗→そのtmpのunlink失敗→lockのunlink失敗を注入。実際にはtmpとlockの両方が残るが、公開エラーは code=store_io_error、field=lock、phase=lock_release、cleanup=(lock_left,) だけ。先に作られた例外のcleanup=(tmp_left,)を新しい例外へ移していない。復旧時に残留物の説明が不完全になる。 | エラーを作り直す全分岐で、元の安全なcleanupを新しいlockトークンと重複なく統合する。phase／primaryの既存優先順位、公開後のuncertain優先、他者所有物の不削除は維持。公開前のtmp＋lock削除失敗、tmp削除失敗＋所有喪失、公開後のuncertainとの組合せを回帰試験へ。 |
| R-02 Windowsの既存ロック用ディレクトリでcodeが違う | store.py:162〜177。設計§5／§9、結果文書のstore_busy「種類を問わず」、既存S2試験 test_b08_corrupt_and_paths.Paths.test_lock_that_is_a_directory | 実Windowsではwrite.lockがディレクトリのとき、排他的作成がFileExistsErrorではなくPermissionErrorになる。一般例外へ入り、store_io_error／lock／lock_acquireになる。契約は「既存のロックは種類を問わずstore_busy」。正本・既存ディレクトリは不変だが、占有と通常I/Oエラーの区別が崩れる。 | 作成失敗時、リンクを追わない存在確認により「既存ロック」と判断できる場合をstore_busyにそろえる。真の権限・I/O障害まで一律busyにせず、存在確認できなければ従来のstore_io_errorを維持。既存ファイル／ディレクトリ／リンクを削除せず、通常の権限エラーも安全に秘匿する回帰試験を追加。Windows実機ケースとLinux上の分岐模擬を区別する。 |

R-01は実Windows上のfile_sync_onlyと既存FileOps故障注入で確認した、OSに依存しない例外統合の欠陥。R-02は実Windowsで確認したOS依存の差異。R-02だけのためにstrictをWindowsで実現したり、自動解錠を追加したりしない。

正常な対照では、(a)ロック所有喪失を既に主エラーとしている分岐、(b)replace呼出し開始後のuncertain分岐はcleanup両項目を保持していた。R-01はこの正常分岐まで一律に壊れているという指摘ではない。

## 3. 任意の文書提案と§8の判断

| ID | 内容 |
|---|---|
| Q-01 Windows向けの実行手順 | 結果文書§8の「Windowsで同じコマンド」と§9の全探索は、そのままだと多数のLinux strict前提ケースも動く。全探索を実Windowsで診断すると、100件探索、failures=6・errors=77・skip=4、終了1だった。大半はWindows strictを意図どおり拒否した結果とLinux専用機能によるもので、83件の独立した製品不具合という意味ではない。Linux全件のコマンドとWindows専用3件のコマンド（下記）を区別し、新しいWindows回帰試験の対象も明示するとよい。既存Linux試験をfile_sync_onlyへ一律に書き換えて合格扱いにしない。 |
| Q-02 ファイル数の表記 | 結果文書§3の「試験9ファイル」は、新規test_*.pyが7ファイルであることと一致しない。S2追加全体は16ファイル（ランタイム5、test_*.py 7、helper／worker／sensitivity計3、結果文書1）。件数100の合計に問題はない。表記のみ訂正可。 |

結果文書§8で補った判断について：
- initializeのLocalInitResult（INITIALIZED、initialized=True）は、S1の初期化とcommitの区別を保ち、まだ利用側への接続も無い。今回のローカルAPIとして受領する。LocalCommitResultのCOMMITTED契約はcommitに限ることを結果文書で明確にすればよく、型を戻す修正は求めない。
- phase／cleanup／primaryは安全な固定識別子での診断拡張として受領する。ただしcleanupの取りこぼしはR-01として修正する。
- uncertain後に所有を確認して通常解放を試みることは、上位契約§8の「正常に解放できた場合、明示的read＋reconcileが可能」と整合する。解放失敗を成功扱いしない現方針を維持する。
- BaseExceptionを捕捉せず残留物で停止すること、ハードリンクや攻撃的な差替えを防御対象に広げないこと、root祖先リンクの許容は、記載された信頼済みrootの範囲で留保付き受領とする。今回、新しい復旧機能やパス防御機構を追加しない。

## 4. 独立確認の環境・結果

主担当環境：実Windows 11、10.0.26300、Python 3.12.14（MSC 64bit）。
GitHub固定blobから確認専用のローカルコピーを組み立て、S2追加16ファイルと既存runtime／保存ドメイン試験計34ファイルをGit blob SHAで照合した。Gitのクリーンクローンそのものではない。既存研究fixtureは取得していない。
専用rootは明示した作業領域のreview-temp配下へ生成。デフォルトのサンドボックス用TEMPではファイル作成が拒否されたため、TEMP／TMPをこの書込可能な専用領域へ向けてから測定した。初回の環境起因の失敗を製品不具合へ数えていない。ファイルシステム種別は本確認では取得できず未計測。
helper／workerのソケット禁止を使用した。LinuxのunshareによるOSレベル遮断と同じ実行条件とは扱わない。

| 確認 | 結果 |
|---|---|
| 基準2d09db7→最終00e7f84のGitHub差分 | 新規16ファイルだけ。既存ファイル変更0。 |
| コード試験81ac624→最終00e7f84のGitHub差分 | 結果文書の追加1ファイルだけ。間のコミット数は2だが、差分に実装変更なし。 |
| Windows専用RealWindows 3件 | 3件実行、全合格、skip0、終了0。file_sync_only往復と既存正本への置換、strictの公開前拒否、実プロセス競合の1勝を確認。 |
| 添付再現コード・既知挙動モード | 5件合格。R-01／R-02の実測挙動と、正常な対照3件を固定。 |
| 同コード --expect-fixed | 5件中2件失敗、対照3件合格。失敗はR-01／R-02の修正後期待値との不一致。これは修正前の検出力の確認であって、実装完了ではない。 |
| Windowsで全新規探索（手順の診断） | 100件探索、failures=6・errors=77・skip=4、終了1。Q-01のための診断で、Linuxの97件合格報告を否定する実行ではない。 |
| 保護参照 | 依頼の13参照＋資料73cec62、計14参照をGitHub APIから照合、全て不変。 |
| Linux4版の367＋97件、10回反復、27欠陥、SIGKILL | Claude報告として受領。主担当は今回再実行していない。 |
| 物理電源断、autocrlf=true、ユーザーPCの181件 | 未実施のまま。Windows専用3件の主担当実行はユーザーPC確認の代替ではない。 |

Windows専用3件を実行したコマンド（事前にTEMP／TMPは書込可能な専用一時フォルダへ設定）：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p test_b09_modes_os.py -k RealWindows -v

R-01／R-02の再現（[同じ資料コミットのコード](v2_s2_receipt_probe.py)）：

    <python> -B -W error::ResourceWarning <資料側>/docs/reviews/v2_s2_receipt_probe.py --repo-root <実装側> --scratch-root <専用一時フォルダ>
    <python> -B -W error::ResourceWarning <資料側>/docs/reviews/v2_s2_receipt_probe.py --repo-root <修正側> --scratch-root <専用一時フォルダ> --expect-fixed

このコードは対象runtimeを書き換えず、生成した専用rootだけにI/Oを行う。defaultは旧版の観測確認、--expect-fixedは修正後の契約確認。Linux上ではR-02のネイティブWindows差異を再現したとは扱わない。Windows上で5件の--expect-fixed合格が最終の直接確認になる。

## 5. 保護参照・未実施

元のS2実装ブランチ00e7f84を含め、既存ブランチは変更しない。本レビューの保存は新規の資料ブランチだけに限定する。
本番、Actions、通知、アカウント、資格情報、実口座、PR、S3／S4の操作なし。主担当のローカル確認用コードは再現可能な補助であり製品機能ではない。

## 6. 次の限定修正（Sonnet 5.5・high）

既に認められたS2の範囲にある不具合2件の修正として、次だけを依頼する。新たな本番承認やS3への移行を意味しない。

1. コード基準を00e7f84806ce34dc8754a0fc558870db145ade68に固定し、新しいfix/v2-local-store-s2-review-20261028等のブランチを作る。元のfeatブランチと本資料を上書きしない。開始時に実モデルとeffort、資料の完全SHAを記録する。
2. 変更を許すのは v2_persistence/local/store.py、R-02の正規化で必要な場合だけ同fsops.py、tests/v2_persistence_local/の限定回帰試験、docs/implementation/V2_LOCAL_FILE_STORE_S2_RESULT.md の追記・訂正。既存のv2_core、S1、197＋170件、基準データ、schema／CORE_SHA、依存、設定、workflowは変更しない。
3. R-01は元のcleanupと新しい残留トークンの統合だけを直す。R-02は排他的作成失敗時の既存ロック分類だけを直す。自動解錠・再試行・API変更・新しいWindows同期機構を入れない。既存期待値を弱めない。Q-01／Q-02の文書訂正は同時にしてよい。
4. R-01の複合後始末失敗、所有喪失時の不削除、公開後uncertain優先、R-02の既存directory／regular／linkと本来の権限エラーを確認する。OS依存分岐の注入と実Windows試験を明確に区別する。実Windowsが無ければその部分を保留し、Linuxで合格したという表現へ置換しない。
5. 既存367件を無編集で維持し、新規S2と追加回帰をPython3.10／3.11／3.12／3.13で確認。元の100件と追加件数を別記し、OS別skipを区別する。隔離インタプリタの方針、通信遮断、別クリーンクローンcore.autocrlf=falseは元の依頼を継承。全過去の欠陥注入・市場再計算・物理電源断を追加しない。
6. 結果文書へ修正前の失敗、修正後の合格、code／field／phase／cleanup、正本と残留物、完全SHA、実施・未実施を追記する。元のLinux結果・未実施の履歴は消さず、主担当Windows3件の確認は別環境の受領レビューと明記する。
7. 元の14参照とS2実装00e7f84、本レビュー資料の参照を開始・終了に確認して変更しない。コード・試験SHAと結果文書だけの最終SHAを分け、報告して止める。PR、本番、S3／S4なし。

対象範囲で修正できなければ、その理由と最小差分案を報告し、範囲外の変更は行わない。
