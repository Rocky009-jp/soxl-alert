# V2 S4-B 通知の記録と送信権 限定実装依頼書

作成日：2026-11-05（日本時間）。版：**第2版**（初版e196a68へのレビュー1122052の通常N-01だけを反映。§3の3、S4B-06、欠陥注入19・20。ほかは初版と同じ）。作成：Claude Opus 5.5、effort high。
状態：**未採用**。本書の保存だけでは実装を始めない。実装は、設計§11のD-1〜D-8の採用と、別スレッドへの明示の着手の指示の後に始める。
対になる設計はdocs/specs/V2_NOTIFY_S4B_DESIGN_DRAFT.md（以下「設計」）。本段階はS4-Bだけを実装する。中身は次の4つである。

- 通知の文面。
- ローカルのoutbox（意図・結果の新規作成）。
- 朝の処理`morning_job`。
- 手動の再送`resend`と状態の確認。

送信先は注入した偽物だけである。実際の送信先（Discord等）、gitの保存先・outbox（S4-C）、入力の取得（S4-D）、入口のスクリプト・workflow・秘密・本番（S4-E）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **6ad609fe52b50565103e56c598505cac85601216**（feat/v2-daily-run-s4a-20261104、S4-Aの保存最終） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-notify-s4b-20261105）の設計とdocs/specs/V2_NOTIFY_S4B_TRIAL_20261105.diff。SHAと3つのblobを開始報告に記録 |
| S4-Aの受領 | 実装レビュー63b7f23e29808a9b1537676f94dfec97c3f6cb35、受領記録3e3fd475a486a26eb9fd234e11c4950a04e55102 |
| S4の設計・依頼書（第2版、採用済み） | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6 |
| 上位の送信権の契約 | e3e9094 §5.2・§5.3（第3版） |
| 使う既存の部品 | 6ad609fのv2_daily_run（run_morning、RunReport、ConsumedDay、RunError、DONE／STALE／STOPPED）、v2_persistence.local.fsops.FileOps、v2_core.sessions.SessionList、v2_core.errors.CoreError |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、6ad609fから作る（ブランチ名の案：feat/v2-notify-s4b-YYYYMMDD）。
  1. ユーザーが設計§11のD-1〜D-8を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-8）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-8を、採用されたと書かない。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_notify/ 新規 | `__init__.py`、`compose.py`、`outbox.py`、`job.py`、`values.py`。5ファイルを超えない。分け方を変えたら結果文書に理由を書く |
| tests/v2_daily_run/test_s4a_09_scope.py | 設計§9.1の`END`の1行だけ |
| tests/v2_notify/ 新規 | test_s4b_\*.py、s4b_helpers.py、s4b_worker.py（子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_NOTIFY_S4B_RESULT.md 新規 | 本段階の結果 |

これ以外は変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local、v2_history_maintain、v2_daily_run。
- 既存の試験・ヘルパー。新しいヘルパーからimportするのはよい。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09〜test_c4_09、test_s4a_09（上の1行を除く）。
- 設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

次の範囲へ広げない。

- 実際の送信アダプタ、HTTP、URL、秘密、環境変数、入口のスクリプト・CLI、workflow、gitのoutbox。
- 自動の再送、同じ実行の中での再試行、outboxの掃除・削除・置換。
- S4-A以前のパッケージの変更。コアの見出しの変更（設計§9.3、S4-E）。
- 設計§9.2・§9.3で「持ち越し」「S4-D」「S4-E」とした提案。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

1. **公開名**：`morning_job`、`resend`、`outbox_status`、`compose_notice`、`compose_error_notice`、`LocalOutbox`、`Notice`、`JobReport`、`ResendReport`、`NotifyError`（CoreErrorの子）、状態と種類の定数。
2. **時計と乱数**：時計を読まない（nowは注入、時刻つきのdatetimeでなければ`NotifyError`の`notify_args_invalid`）。乱数はclaim_idの`secrets.token_hex(16)`だけ。
3. **種類と鍵**：設計§3。MORNING＝`<対象D>-morning`、HALT＝`<対象D>-halt`、ERROR＝`<対象D>-error`。対象Dはjobが`run_morning`の前にS4-Aと同じ規則（`close_at <= now`の最後のセッション）で求め、求まらない場合（sessionsの型の誤り、閉じたセッションが無い、その途中の例外）だけ`<nowのUTCの日付>-error`にする。HALTとERRORは、`<対象D>-morning`の意図がある（どの状態でも。DAMAGEDを含む）なら作らない。`target_status`を鍵の判断に使わない。
4. **文面**：設計§4の部品と順序。
   - 記録の欠けの条件はskipped_sessionsが空でない日。MORNINGではgap=falseの日だけ、HALTでは全部の日を書く。
   - 注記は4つ（次の寄付きの後、保存の未確認、境界の日、同時の実行）。それぞれ設計の条件のときだけ入れる。
   - MORNING・HALTの本文は`report.message`を1文字も変えずに含める。
   - ERRORは、codeと例外の型の名前だけを書く。例外の本文（`str(e)`）・パス・URL・秘密を、どの文面・報告・意図にも入れない。
5. **LocalOutbox(root, \_ops=None)**：
   - rootは絶対パスの既存ディレクトリで、リンクでないこと。違えば`NotifyError`（`outbox_root_invalid`）。
   - 書込み・読込みはS2のFileOpsのメソッドだけで行う（create_exclusive、open_writer、write、flush、fsync_file、close、close_fd、fsync_dir、probe_dir_sync、read_file、listdir、lstat）。
   - 書く順序は、create_exclusive→全量のwrite→flush→fsync_file→close→fsync_dir。
   - `FileExistsError`は「意図を持たない」とし、ほかのOSErrorは`outbox_io_error`にする。どちらも例外処理の中では値を作るだけで、`NotifyError`は外で投げる（`__context__`を残さない。C-4の規則C4-19と同じ）。
   - replace・rename・unlinkを呼ばない。
6. **ファイルの中身**：設計§5の項目の正規化JSON（`sort_keys`、区切りは`,`と`:`、UTF-8、`ensure_ascii=False`）。意図にはschema（固定値`v2_notify.claim.1`）を入れる。
7. **状態**：設計§5の表。次の場合はDAMAGEDとし、送らない。
   - 意図が読めない、JSONでない、項目が欠けている、鍵（kind・d・resend）がファイル名と違う。
   - 結果のclaim_idが意図と違う。
   - 結果のstatusが3語以外。
8. **送信アダプタ**：`sender.send(text)`だけを呼ぶ。`"SENT"`ならSENT、`"NOT_STARTED"`ならNOT_SENT、ほかの戻り値・あらゆる例外（BaseExceptionのうちKeyboardInterrupt・SystemExitを除く）はUNKNOWNとする。1つの実行で1回だけ呼ぶ。
9. **morning_job**：設計§6の順。
   - CoreError以外の例外は、ERRORの送信・記録の後に、同じ例外オブジェクトを投げ直す。
   - outboxの誤り（意図を作れない）はCLAIM_FAILEDで送らない。結果を書けないときはRESULT_NOT_RECORDED。
   - exit_codeは設計§6。
10. **resend**：設計§7の条件と順序。
    - resend_request_idの検査は、ファイルに触れる前に行う。
    - 同じidの意図があれば送らない。
    - 元・再送のどれかにSENTがあれば拒む。DAMAGEDも拒む。
    - 文面は、元のtextに【再送】の1行を足したもの。
11. **outbox_status**：読取り専用。ファイルを作らない、変えない。

## 4. 受入条件 S4B-01〜S4B-18

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、S4-Aの`run_morning`の報告、試験側で書いたJSON・hashlib、偽の送信先の記録から作る。実装の出力をコピーしない。

| ID | 必須確認 |
|---|---|
| S4B-01 回帰 | 既存の16スイート計2349件を、完全なクローンで維持する（S4-Aまでの15スイート2253件とS4-A 96件）。test_s4a_09の1行の固定を含み、件数は同じ |
| S4B-02 引数と値 | nowに時刻帯が無い、outboxのrootが相対・存在しない・ファイル・リンク、resend_request_idの文字種・長さの誤りで、NotifyErrorになり、ファイルに触れない。Notice・JobReport・ResendReportが不変で、reprに文面全体・パスが出ない |
| S4B-03 MORNING | DONEの朝に1通送り、意図と結果の2ファイルができる。中身が設計§5の項目どおり（試験側でJSONを読んで確かめる）。text_sha256が文面のsha256と一致する。exit 0 |
| S4B-04 同じ朝の再実行 | 2回目・3回目は送らない（SKIPPED_CLAIMED）。前の結果がSENTならexit 0。ファイルのバイトは変わらない |
| S4B-05 HALTと順序 | (a) STALE・STOPPEDの朝に判定なしを1通。(b) その後に同じDが成功すれば判定ありを1通。(c) 判定ありの後に止まった実行は判定なしを送らない（SKIPPED_JUDGMENT_EXISTS）。(d) 判定ありの意図がDAMAGEDでも判定なしを送らない |
| S4B-06 ERROR | (a) RunError（閉じたセッションが無い）でERRORを1通（鍵はnowのUTCの日付）、同じUTCの日の2回目は送らない。(b) CoreError以外の例外（市場データの読込みで投げる偽物、本文にパスを含める）で、ERRORを1通送ってから同じ例外オブジェクトが出る。文面・意図に本文・パスが無い。(c) S4-AレビューのP-02(b)の形（bstarでdecimal.InvalidOperation）でも(b)と同じ。(d) 日本時間の昼の手動の再実行（UTCの当日）と翌朝の定時実行（UTCの同じ日の21〜22時台）がともに誤りで、対象Dが違えば、2通とも届く（レビュー1122052のX1の場面）。(e) 判定ありの意図（SENT・UNKNOWN・DAMAGEDのどれでも）がある同じDの誤りは、ERRORを送らない（SKIPPED_JUDGMENT_EXISTS）。ERRORの後に同じDが成功すれば判定ありは送れる |
| S4B-07 記録の欠け | (a) HALT：STALEの朝に保存した日の欠けの日付が文面にある（S4-AレビューのX1の場面）。(b) MORNING：GENESISの直後・再初期化の直後の最初のAPPLY（gap=false、skipped_sessionsあり）の欠けが文面にある。(c) MORNINGでgap=trueの日の行が重ならない（同じ日付の欠けの行が1回だけ） |
| S4B-08 注記 | 4つの注記が、設計の条件のときだけ入る。次の寄付きちょうど（now＝open_at）は入る、1マイクロ秒前は入らない |
| S4B-09 本文 | MORNING・HALTの文面が`report.message`を変えずに含む（部分文字列として一致）。ERRORの文面にreport.messageは無い |
| S4B-10 送信の結果 | SENT／NOT_STARTED／ほかの戻り値（None、"OK"等）／例外（TimeoutError、OSError、RuntimeError）→SENT／NOT_SENT／UNKNOWN。send呼出しは1回だけ。UNKNOWN・NOT_SENTの後の再実行は送らない |
| S4B-11 意図だけ残る | 意図を書いた直後に止まった形（結果のファイルが無い）をUNKNOWNと読み、送らない。outbox_statusでUNKNOWNと出る |
| S4B-12 DAMAGED | 意図・結果を手で、空・途中まで・JSONでない・項目欠け・kind/dがファイル名と違う・claim_idが違う・statusが別の語に壊すと、DAMAGEDで送らない。例外が漏れない |
| S4B-13 outboxの誤り | 偽のFileOpsで、create_exclusive・write・fsync_file・close・fsync_dirの各段にOSErrorを起こす。意図を作れなければCLAIM_FAILEDで送らない。結果を書けなければRESULT_NOT_RECORDED（意図は残り、次の実行は送らない）。`__context__`・`__cause__`が残らない |
| S4B-14 手動の再送 | (a) UNKNOWN・NOT_SENTの元に再送1通、文面は【再送】の1行＋元のtext。(b) 同じidをもう一度→送らない。(c) 再送がSENTの後の別のid→拒む。(d) 元がSENT→拒む。(e) 元が無い・DAMAGED→拒む。(f) 再送がUNKNOWNなら、別のidで次を送れる |
| S4B-15 同時の実行 | 子プロセス2〜4個（ファイルの合図で同時に始める）で、(a) morning_jobを同時に走らせる→同じDの判定ありは1通まで、判定なしは1通まで。判定なしにはT-3の注記がある。(b) 同じ再送idを同時に→1通まで。(c) 異なる再送idを同時に→元がUNKNOWNなら各idで1通まで（上位§5.3の契約どおり）。回数と結果を結果文書に記録する |
| S4B-16 例外の出口 | 偽の送信先・偽のFileOps・偽の保存先の各呼出しでCoreError・OSErrorを起こす総当たりで、morning_jobはJobReportを返すか、CoreError以外の元の例外をそのまま出す。NotifyError・JobReportに`__context__`が残らない |
| S4B-17 静的な範囲 | ランタイムのimportが許可だけ（標準ライブラリのdatetime・hashlib・json・os・secrets・stat、v2_core、v2_persistence.local.fsops、v2_daily_run）。socket・subprocess・urllib・http・time・random・threading・environの使用なし。`datetime.now`・`utcnow`・`today`の呼出しなし。`replace`・`rename`・`unlink`の呼出しなし。v2_history\*をimportしない |
| S4B-18 範囲試験 | 新しい範囲試験（START＝6ad609f、END＝None、REV＝END or "HEAD"、FilesChanged）が、§2の変更だけを許す。test_s4a_09の差分を自分の差分のハンクとして固定する。範囲の鎖が`…→2e6ba5f→6ad609f→（S4-B）`で通る。ENDだけを固定して開いた範囲を外すと鎖の試験が失敗する手順を、結果文書に記録する |

## 5. 限定欠陥注入

1件ずつ壊して試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. HALTの前に判定ありの意図を確かめない。
2. 判定ありの意図がDAMAGEDのとき、HALTを送る。
3. 鍵に`target_status`を含める。
4. 記録の欠けの条件をgapにする。
5. MORNINGでgap=trueの日も欠けの行に書く（重なる）。
6. HALTで記録の欠けを書かない。
7. 次の寄付きの注記で`>=`を`>`にする。
8. ERRORの文面に`str(e)`を入れる。
9. CoreError以外の例外を投げ直さない。
10. 送信の例外をNOT_SENTにする。
11. NOT_SENT・UNKNOWNのとき、同じ実行でもう一度sendを呼ぶ。
12. 意図をcreate_exclusiveでなく、上書きの書込みで作る。
13. 結果が無い意図を「送っていない」として送る。
14. 結果のclaim_idを確かめない。
15. 再送で、別のidの再送のSENTを見ない。
16. 再送で、同じidの意図があるのに別の名前で作って送る。
17. 例外処理の中でNotifyErrorを投げる（`__context__`が残る形）。
18. fsync_fileを呼ばない。
19. ERRORの鍵に、対象Dが求まるときもnowの日付を使う（第2版、N-01）。
20. ERRORの前に判定ありの意図を確かめない（第2版、N-01）。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴）で試験する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、新規N、S4-A 96、C-3 139、範囲の鎖34を実行する。実Windowsで行うまで未実施と書く。O_EXCLとfsync_dirのWindowsでの振る舞いも未実施と書く。ユーザーPC・物理電源断は未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_notify -p "test_s4b_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- ランタイムの全文の場所と行数。
- test_s4a_09の差分の全文。
- 試行の下書き（設計§10）との違いと、その理由。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。
- S4B-15の回数と結果、S4B-16の総当たりの件数、S4B-18の手順と結果。
- 文面の例（MORNING、欠けつきMORNING、HALT（STALE・store_busy・成否不明・境界）、ERROR、再送）。
- 意図・結果のファイルの例。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・実際の送信・S4-C以降へは進まない。

## 7. 読取専用の保護参照

次の92参照を、開始時と保存・push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-notify-s4b-20261105についても、受け取った版の完全SHAを1本加える（実装時は93参照。レビューの後に第2版・採用記録が加わった場合は、その版とレビューのブランチを加える）。

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
| docs/v2-history-maintain-c4-20261104 | d11b87597ef4035f5fee0ffc8c9fa859f82fe00f |
| docs/v2-history-maintain-c4-review-20261104 | 74c93b11236f83508c354dee9a38df9cc38a1c67 |
| docs/v2-history-maintain-c4-v2-rereview-20261104 | 8f39111369531b320f20320dac733775c87f3e5c |
| feat/v2-history-maintain-c4-20261104 | 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb |
| docs/v2-history-maintain-c4-impl-review-20261104 | 906a70a2877cf135947498f53c0750cb3c43156d |
| docs/v2-history-maintain-c4-fix-rereview-20261104 | 8d02abf1622714cdeb38df6bd5bab91787249eb7 |
| docs/v2-s4-daily-run-20261104 | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6 |
| docs/v2-s4-daily-run-review-20261104 | dd60f6f22d773561cfcc3ab09c868e02d9d0a973 |
| feat/v2-daily-run-s4a-20261104 | 6ad609fe52b50565103e56c598505cac85601216 |
| docs/v2-daily-run-s4a-impl-review-20261104 | 3e3fd475a486a26eb9fd234e11c4950a04e55102 |

本書の作成時（2026-11-05、日本時間）に、上の92参照がリモートと完全SHAで一致することを、開始時と資料ブランチのpush後に確かめた。

## 8. 採用単位

設計§11のD-1〜D-8と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。

- D-1：S4-Bの範囲。
- D-2：通知の種類と鍵。
- D-3：文面。
- D-4：送信権と記録・朝の処理（U-04を含む）。
- D-5：手動の再送。
- D-6：前の段階の提案の扱い。
- D-7：範囲試験。
- D-8：担当（Sonnet 5.5・high）。

今回の文書作成と、設計§10の一時環境の試行は、その採用ではない。S4-Aの受領と「次の段階にすすんで」を、S4-Bの実装承認にしない。実際の送信先への接続・S4-C以降・本番の承認も含まない。
