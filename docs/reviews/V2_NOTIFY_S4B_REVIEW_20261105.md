# V2 S4-B 通知（文面・ローカルoutbox・送信権・手動再送） 限定実装 レビュー

作成日：2026-11-05（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由の依頼（2026-11-05T00:35Z、Rocky「推奨どおり」2026-11-04T22:39Zを添付）。実装者の結論に頼らず、変更境界・依頼書§3の11項目・受入S4B-01〜18・実装中の2つの直し・R-01〜R-03の扱い・欠陥注入（実装者の52件の再現と独立の24件）・同時実行・Windows相当のディレクトリ同期・次段階の模擬・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常1・提案4。推奨は「限定修正（N-01だけ）」。** 依頼書第2版§3の11項目と受入S4B-01〜S4B-18は、Linuxの試験対象f3b9f7fで満たされている。実装中の2つの直し（結果だけの鍵で送ってしまう穴の修正、競合中の書込み途中を読んだREFUSED_DAMAGEDの許容）はどちらも妥当である。R-03を限界として残した判断も依頼書の文言に沿っている（ただし限界の書き方が足りない。P-01）。
通常のN-01は、`LocalOutbox`が書込みのたびに必ずディレクトリのfsyncを呼ぶことである。ディレクトリのfsyncができない環境では、意図のファイルを全部書いた後で`CLAIM_FAILED`になり、何も送らず、意図がUNKNOWNとして残って再送も同じく失敗する。C-3はこの環境を「Windowsではstrictを拒む」（`windows_strict`）として扱っており、Windowsはまさにこの環境である。設計§5は「（strictなら）ディレクトリをfsyncする」と書いていたが、依頼書§3の5が順序を固定したため、モードが無いまま実装された。Windows相当の模擬では、新規試験のうち同じプロセスで走る90件中69件が失敗した。本番（非公開リポジトリのActions、Linux）には影響しないが、利用者PC（Windows）での試験・手元の実行ができない。
本レビューはPR・マージ・本番反映・S4-Cへの移行・実際の送信の承認ではない。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | 6ad609fe52b50565103e56c598505cac85601216（S4-Aの保存最終、受領記録3e3fd47） |
| 試験対象 | **f3b9f7f4b05691afbb92595f64ef3c53f17839e7**（コード・試験の最終） |
| 保存最終 | **d49a4cc89ee682cc4656f6f037a97e510771e906**（feat/v2-notify-s4b-20261105。f3b9f7fからは結果文書1本の追加だけ） |
| 基準 | 4c54e01b218148e49e5ae283e7f0bf2fc52edb46（docs/v2-notify-s4b-20261105）の設計第2版・依頼書第2版・試行差分。D-1〜D-8採用済み（設計§13）。設計レビュー1122052、再レビューf10e719（任意R-01〜R-03） |

読んだもの：設計第2版と依頼書第2版の全文、結果文書の全文、ランタイム5ファイルの全文（703行）、比較のためv2_daily_run/run.py・values.py、v2_persistence/local/fsops.py、v2_history_local/store.pyの耐久性の分岐（`_publish`）、tests/v2_persistence_local/test_b09_modes_os.pyの実Windowsの試験。新規試験のうちs4b_helpers・s4b_worker・test_s4b_03・test_s4b_08・test_s4b_09の全文と、ほかの該当部分。共有フォルダの実装者のmutate.py・runall.sh・race_report.py・next_stage_sim.sh。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、S4B-18） | **合格** | 6ad609f→f3b9f7fはA 17本・M 1本。Mはtest_s4a_09_scope.pyの18行目`END`の1行だけ。Aはv2_notify/の5ファイル（上限どおり）とtests/v2_notify/の12本（`__init__.py`なし）。f3b9f7f→d49a4ccはA 結果文書1本だけ |
| 依存とimport（S4B-17） | **合格** | ランタイムのimportは標準のdatetime・hashlib・json・os・secrets・stat、v2_core（errors・sessions）、v2_persistence.local.fsops、v2_daily_runだけ。時計の読取り・replace・rename・unlinkなし |
| 依頼書§3の1〜11 | **合格（Linux）** | 公開名、時計と乱数、種類と鍵（ERRORの鍵は対象D、求まらないときだけUTCの日付）、文面の部品と順序、LocalOutboxの検査と書く順序、正規化JSON、DAMAGEDの条件、送信アダプタの3分類、morning_jobの順序と投げ直し、resendの条件、outbox_statusの読取り専用を、コードと試験の両方で確かめた |
| 受入S4B-01〜S4B-18 | **合格（Linux）** | 4版×17スイートで2,472件合格（§4.1） |
| 実装中の直し1（結果だけの鍵） | **妥当** | §4.3 |
| 実装中の直し2（REFUSED_DAMAGEDの許容） | **妥当** | §4.3 |
| R-01・R-02 | **採用は妥当** | outbox_statusは3つの鍵と各再送を返す。プログラムの誤りは、送らなかった場合も同じオブジェクトを投げ直す（試験で固定、独立V19も検出） |
| R-03（限界として残す） | **判断は妥当、書き方が不足** | 日本時間の朝の実行では、予備の鍵の日付（UTCの日付）が対象Dと**いつも**同じになる。結果文書は抑えられる向きだけを書いている（P-01） |
| ディレクトリ同期ができない環境 | **通常N-01** | §4.5 |
| 欠陥注入 | **実装者52件を再現、独立24件は検出21・等価1・未検出2** | §4.2 |
| 同時実行（S4B-15） | **合格** | §4.6 |
| 次段階の模擬 | **保存最終で再現** | §4.7 |
| 保護参照 | **一致** | 95参照（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| N-01 | 通常 | `LocalOutbox._create`（outbox.py 183行）は、意図・結果のどちらでも、全部を書いてflush・fsync・closeした後に必ず`fsync_dir`を呼び、その失敗を`outbox_io_error`にする。ディレクトリを開いてfsyncできない環境では、毎回この段で失敗する。C-3（v2_history_local/store.py 362〜373行）は同じ制約を`durability`で扱い、Windowsではstrictを`windows_strict`で拒み、他でも`probe_dir_sync`で先に確かめる（実Windowsの試験test_b09 `RealWindows.test_strict_is_refused_before_publication`）。設計§5は「（strictなら）ディレクトリをfsyncする」と書いていたが、依頼書§3の5は順序を固定し、モードも事前の確認も無いまま実装された（依頼書は`probe_dir_sync`を許可したメソッドに含めている）。`s4bi_windir.py`で、ディレクトリ同期がPermissionError（13）になるFileOpsを入れると、W1：DONEの朝が`CLAIM_FAILED`（送信0、意図のファイルは完全に書かれて残る）、W2：再実行は`SKIPPED_CLAIMED`・既存UNKNOWN、W3・W4：再送は別のidでも毎回`CLAIM_FAILED`で、再送の意図も残る。`s4bi_windir_suite.py`で、同じ置き換えをしてtest_s4b_01〜07を走らせると、90件中69件が失敗・エラー（50＋19） | ディレクトリ同期ができない環境では、通知が1通も届かず、鍵ごとに「送ったかもしれない」UNKNOWNの意図が残り、手動の再送でも回復できない。Windowsでは常にこうなる。本番の予定（非公開リポジトリのActions、Linux、S4-Cのgitのoutbox）には影響しない。一方、依頼書§6が予定する利用者PC（Windows）での新規試験は大半が失敗し、手元での実行・確認もできない。結果文書§13は「fsync_dirができない環境ではoutboxが使えない」と1行で書いているが、残るファイルと回復できないことは書いていない | C-3と同じ形にする。`LocalOutbox(root, durability="strict", _ops=None)`。(1) `"strict"`（既定）：Windowsなら作成時に`NotifyError`（例`outbox_durability_unsupported`）、それ以外は作成時に`probe_dir_sync(root)`を1回呼び、失敗なら同じ誤り。どちらもファイルを作らない。書く順序は今のまま。(2) `"file_sync_only"`：`fsync_dir`を呼ばない（create_exclusive→write→flush→fsync_file→close）。試験は、順序の試験をstrictのまま残し、それ以外はS4-Aの補助と同じく実行環境に合うモードを使う。Windowsの分岐はLinuxで`is_windows`を真にした模擬で確かめる（S2のtest_b09と同じ）。欠陥注入に「strictで事前の確認をしない」「file_sync_onlyでもfsync_dirを呼ぶ」を足す。変更はoutbox.py・values.py（定数1つ）と試験だけ。依頼書§3の5の固定順序を変えるので、設計§5の「（strictなら）」に合わせる限定修正の依頼として出す | `s4bi_windir.py`（strict：作成時に拒む、ファイル0。file_sync_only：W1がSENT）、`s4bi_windir_suite.py`をfile_sync_onlyで0件失敗。実Windowsでの新規N |
| P-01 | 提案 | R-03の限界の書き方が足りない。日本時間の朝の定時実行（対象Dの引けの後、UTCでは同じ日の21〜22時台）では、予備の鍵の日付＝nowのUTCの日付が、対象Dと同じ日付になる。結果文書§3.4は「後のほうは送られない」の向きだけを書いている。`s4bi_probe2.py`：(R03a) 判定ありをSENTの後、同じ朝にsessionsが壊れた再実行があると、予備の鍵`<D>-error`で「判定なし（実行の誤り） 日付（UTC）=D」が**送られる**（予備の鍵は判定の確認をしない。設計レビュー1122052のN-01(b)の読み違いが、予備の経路にだけ残る）。(R03b) 予備のERRORの後の同じDの誤りは送られない（結果文書どおり）。独立V03（予備の鍵でも`<UTCの日付>-morning`を確かめる）は未検出で、試験はこの場面を固定していない | 起きるのは、判定を送った後の同じ朝に、sessionsの型が壊れた・閉じたセッションが無い実行が走ったときだけで、入力アダプタ（S4-D）の誤りに限られる。文面の見出しは「日付（UTC）」で区別できる | どちらかを選ぶ。(a) 限界の説明に(R03a)の向きを足すだけ（結果文書または受領記録）。(b) 予備の鍵でも、同じ日付の`-morning`の意図があれば送らない（job.py 112行の条件1つ。設計§3の「HALTと同じく判定ありの意図があれば送らない」の趣旨に合う）と、試験1件。今回の受領の条件にしない。N-01の限定修正と一緒に(b)を入れてもよい | (R03a)で2通目が送られないこと（(b)の場合） |
| P-02 | 提案 | 手動の再送は、HALT・ERRORの鍵でも、同じDの判定あり（`<D>-morning`）の意図があるかを見ない。`s4bi_probe.py` X2：判定なし（STALE）の送信がUNKNOWN→同じDの判定ありがSENT→利用者がhaltの再送を依頼すると、「【再送】…」「対象D=… ／判定なし」が**送られる**。設計§7の拒む条件（元が無い、SENTがある、DAMAGED）どおりの実装で、設計の穴 | 利用者が自分で依頼したときだけ起きる。判定の後に「判定なし」が届き、§3が避けようとした読み違いが再送で起き得る | resendで、kindがhalt・errorなら`<D>-morning`の意図（どの状態でも）があれば拒む（例`REFUSED_JUDGMENT_EXISTS`）。またはS4-Eの利用者向けの手順と`outbox_status`の見方に書く。今回の受領の条件にしない | X2の再送が送られないこと |
| P-03 | 提案 | DAMAGEDの残り方と回復の手順。(a) 意図のwriteで失敗（ENOSPC等）・書込み中の異常終了では、空・途中までの意図が残る（X4：`CLAIM_FAILED`、ファイル0バイト）。その鍵は以後DAMAGEDで、morningなら同じDの判定なし・誤りも止まり、再送もREFUSED_DAMAGED（X3）。結果文書§13「手で直す手順は未整備」のとおり。(b) 競合中のREFUSED_DAMAGED（§4.3）は、他方が送っている最中でも「壊れている」と報告する。なお、送信は意図を全部書いてfsyncした後だけなので、**中身が欠けた意図は、その実行が送信アダプタを呼んでいない**ことを意味する（実行中でなければ）。手順を作るときの手がかりになる | 送らない側に倒れるだけで、二重送信は起きない。その朝の通知が来ないので「来なければ止まっている」（S4-E）の手順で拾う | S4-Eの利用者向けの手順に、DAMAGEDの読み方（作成中の可能性、少し待って`outbox_status`を見直す）と、空・途中までの意図の扱い（送っていない、実行が終わっていることを確かめて手で退避）を書く。コードは変えない | 手順の文書の確認だけ |
| P-04 | 提案 | 試験の小さな穴。(a) 独立V04（jobの対象Dを`close_at < now`で求める）が未検出。nowがちょうど引けの時刻のとき、jobの対象D（ERRORの鍵と判定の確認に使う）とrun_morningの対象Dがずれ、誤りの通知が前の日の鍵になり、前の日の判定ありで抑えられる。f3b9f7fは正しい（`s4bi_probe3.py`）。(b) 独立V06（resendで同じidの使用を見ない）は、`_take_and_send`の事前の確認が同じ結果を返すので**等価**（二重の守り）。(c) V03はP-01 | 実装は正しい。将来jobの対象Dの規則とS4-Aの規則がずれても試験が拾わない | 次にtest_s4b_03を触る機会に、now＝引けの時刻ちょうどの誤りが、そのDの鍵になる試験を1件足す（N-01の限定修正と一緒でよい） | V04が検出されること |

重大は無い。通常はN-01だけ。

## 4. 確認の詳細

### 4.1 全スイートの再実行（S4B-01）

試験対象f3b9f7fを、完全な履歴の別クリーンクローン（`git clone -c core.autocrlf=false`、浅くない）で取り出し、実装者のrunall.sh（`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`）で17スイートを4版同時に実行した（`s4bi_allver_f3b9f7f.log`）。

| 版 | 結果 |
|---|---|
| 3.10.20（uv） | 17スイートとも rc＝0。既存15スイート2,253件（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139、C-4 184）＋S4-A 96件＋新規123件。skipはS2のWindows専用4件だけ |
| 3.11.18 | 同上 |
| 3.12.3 | 同上 |
| 3.13.18 | 同上 |

合計2,472件。新規のskipは0。結果§7の表と件数が一致した。

### 4.2 欠陥注入

- **実装者の52件の再現**：共有フォルダのmutate.pyを、f3b9f7fを含む別クローンで3.13により4分割で再実行した（`s4bi_impl_mutants_repro.txt`・`.json`）。52件の分類は結果§8と同じで、検出51・未検出1（追加23。結果§9の等価の判断どおり、Linuxの`lstat`はリンクを`S_ISLNK`で返すので`S_ISDIR`がすでに偽になり、再解析点の分岐はWindowsでしか効かない。妥当）。落ちた試験の数は51件で結果§8と一致し、依頼13だけ7件に対し8件だった（検出の結論は同じ。子プロセスの競合の試験の結果に依存する数と思われる。未確認）。
- **独立の変異24件**（`s4bi_mutate.py`、f3b9f7fの作業ツリーの写しでランタイムを1件ずつ変え、tests/v2_notifyの123件を3.13で実行。出力`s4bi_mutants_out.json`）：

| ID | 内容 | 結果 |
|---|---|---|
| V01 | 実装中の直しを外す（自分の鍵の事前の確認なし） | 検出1（結果だけの鍵） |
| V02 | 事前の確認でDAMAGEDを通す | 検出1 |
| V03 | 予備のERRORでも`<UTCの日付>-morning`を確かめる | **未検出**（P-01。設計と違う動作だが試験が固定していない） |
| V04 | jobの対象Dを`close_at < now`で求める | **未検出**（P-04(a)） |
| V05 | 再送でNOT_SENTの元を拒む | 検出1 |
| V06 | 再送で同じidの使用を見ない | **等価**（事前の確認が同じ結果を返す。P-04(b)） |
| V07 | 意図のdをファイル名と比べない | 検出1 |
| V08 | resend_ofとファイルの種類の対応を見ない | 検出2 |
| V09 | 結果のstatusの語を確かめない | 検出1 |
| V10 | 同時の実行の注記をすべての判定なしに入れる | 検出4 |
| V11 | 予備のERRORの見出しも「対象D」にする | 検出1 |
| V12 | resendでnowを確かめない | 検出1 |
| V13 | 再送の結果を元の鍵に書く | 検出12 |
| V14 | outbox_statusがkindを無視する | 検出1 |
| V15 | 名前が既にあっても作れたことにする | 検出4 |
| V16 | 送信アダプタの例外をExceptionだけで受ける | 検出1 |
| V17 | FileOpsのCoreErrorをoutboxの誤りにしない | 検出2 |
| V18 | 再送でresend_ofを渡さない | 検出6 |
| V19 | RunError以外のCoreErrorを通知の後に投げる | 検出2 |
| V20 | MORNINGの欠けの行をgap=trueの日だけにする | 検出4 |
| V21 | 既存UNKNOWNのSKIPPED_CLAIMEDもexit 0 | 検出3 |
| V22 | 判定ありがSENTのときだけHALTを抑える | 検出4 |
| V23 | 正規化JSONの区切りを既定にする | 検出1 |
| V24 | 予備の鍵をnowの地方日付にする | 検出1 |

### 4.3 実装中の2つの直し

**(1) 結果だけの鍵で送ってしまう穴（結果§4の6）**

- 直しは`_take_and_send`（job.py 74〜76行）で、意図を作る前に自分の鍵を読み、NONE以外なら送らない。`load`（outbox.py 117〜119行）は、意図が無く結果だけある鍵をDAMAGEDにする。
- 穴の再現：V01（直しを外す）・V02（DAMAGEDを通す）は、どちらも`test_a_result_without_a_claim_and_a_directory_in_the_place_of_a_file_are_damaged`で検出された。`s4bi_probe.py` X5で、結果だけの`<D>-morning`があると、DONEの朝は`SKIPPED_CLAIMED`・既存DAMAGEDで、送信0。
- 競合の安全性：結果のファイルは、意図をO_EXCLで作れた実行だけが`record`で作る。このため、事前の確認（NONE）と意図の作成の間に、他の実行が同じ鍵の結果だけを作ることは無い。事前の確認で読み違えるのは「作成中の意図をDAMAGEDと読む」場合だけで、その場合も送らない側に倒れる。
- 範囲：morning・halt・errorの3つの鍵と、再送の鍵のすべてが同じ関数を通る。再送では`_eligible`の各idの確認でもDAMAGEDになり、REFUSED_DAMAGEDで先に止まる。
- 依頼書の状態表は「意図が無い→NONE（結果は問わない）」だが、「読めない→DAMAGED」の趣旨に沿う安全側の拡張で、結果§3.3・§4の6に書かれている。妥当と判断する。

**(2) 競合中のREFUSED_DAMAGEDの許容（結果§11）**

- 起きる仕組み：意図は`create_exclusive`で名前ができた後に中身を書くので、その間に他のプロセスが読むと、空のファイルとしてDAMAGEDになる。再送の`_eligible`は他のidの状態を読むので、別のid（または同じid）の作成中の意図を読むとREFUSED_DAMAGEDで断る。
- 安全性：DAMAGEDの読みから送信に進む経路は無い（morning_jobでは`SKIPPED_JUDGMENT_EXISTS`か`SKIPPED_CLAIMED`、resendではREFUSED_DAMAGED）。断った側は意図を作っていないので、意図の数＝送信の数は保たれる。少なくとも1つは送る：誰かの作成中の意図を読んで断るには、その意図を作った実行が先にいて、作れた実行は後で断ることがない。
- 試験の緩め方：test_s4b_08の2つの再送の試験は、許す配達の値にREFUSED_DAMAGEDを足しただけで、「同じidは送信がちょうど1通」「別のidは1通以上・id数以下、再送の意図の数＝送信の数」の検査は残っている。二重送信を見逃す緩め方ではない。
- 本レビューの競合の回数は§4.6。

### 4.4 R-01〜R-03

- R-01：`outbox_status(outbox, d, kind=None)`は3つの鍵と各再送を返す（V14で検出）。予備の鍵のERRORはUTCの日付を`d`に渡して見る。予備かどうかは意図に記録されず、`outbox_status`では見分けられない（文面の見出しの「日付（UTC）」だけで分かる）。
- R-02：プログラムの誤りは、ERRORを送らなかった場合（SKIPPED_JUDGMENT_EXISTS・SKIPPED_CLAIMED・CLAIM_FAILED）も同じオブジェクトを投げ直す（job.py 120〜121行）。
- R-03：依頼書§3の3が`<nowのUTCの日付>-error`を固定しているので、名前を変えずに限界として書いた判断は依頼書に沿う。ただし、日本時間の朝の実行ではUTCの日付＝対象Dになるので、重なりは稀な場合ではなく、予備の経路が起きればいつも起きる。抑えられる向き（R03b）に加え、判定の後に予備のERRORが届く向き（R03a）がある（P-01）。予備の経路が起きるのは、sessionsの型の誤り・閉じたセッションが無い朝だけである。

### 4.5 ディレクトリ同期ができない環境（N-01）

`s4bi_windir.py`（LocalOutboxのFileOpsだけを、`fsync_dir`・`probe_dir_sync`がPermissionError（13）になる派生に替える。履歴の保存先はS4-Aの補助のfile_sync_only）：

    W1 first morning: DONE CLAIM_FAILED 1 sends 0 ['2026-03-05-morning.claim.json']
    W2 rerun: SKIPPED_CLAIMED UNKNOWN 1 sends 0
    W3 resend: CLAIM_FAILED UNKNOWN sends 0 [... '2026-03-05-morning.resend-req1.claim.json']
    W4 resend another id: CLAIM_FAILED UNKNOWN sends 0

`s4bi_windir_suite.py`（同じプロセスで`FileOps.fsync_dir`を置き換え、test_s4b_01〜07を実行。子プロセスの試験08と範囲・静的の試験09・10は含めない）：`ran 90 failures 50 errors 19`。

Windowsでディレクトリを`os.open`できないことは、このリポジトリではC-3の`windows_strict`の規則と、S2の実Windowsの試験（strictを拒むことを確かめる）として前提にされている。本レビューは実Windowsで実行していない。ネットワークドライブ・同期フォルダでも同じことが起き得る（未確認）。

### 4.6 同時実行（S4B-15）

実装者のrace_report.pyを、f3b9f7fで3.13により各20回実行した（`s4bi_race_report_out.txt`、計180回）。

| 場面 | N=2 | N=3 | N=4 |
|---|---|---|---|
| morning_job（同じD） | 20回すべて判定なし1通＋判定あり1通（haltはstore_busy） | 同左 | 同左。haltの組はstore_busy 3が11回、publication_stale＋store_busy 2が9回 |
| 同じ再送id | 20回すべて送信1通、残りSKIPPED_CLAIMED | 同左 | 同左 |
| 別の再送id（元がUNKNOWN） | 20回すべて各id 1通（2通） | 19回は3通、1回は2通（1つがREFUSED_ALREADY_SENT：他のidのSENTを読んで正しく断った） | 20回すべて4通 |

- 判定ありの二重・判定なしの二重は0回。判定なしの文面には、すべて同時の実行の注記があった。その後の健全な1回でも判定ありは増えない（合計1通）。
- 今回の180回ではREFUSED_DAMAGEDは出なかった。実装者の観測（§4.3の(2)）と矛盾しない（書込み中の短い間を読んだときだけ起きる）。
- 設計のT-3（同時の2〜4実行で判定なしと判定ありが1通ずつ）は、実装でもそのまま起きる。本番はconcurrencyで1実行にする（採用済み）。

### 4.7 次段階の模擬（S4B-18）

実装者のnext_stage_sim.shを、保存最終d49a4ccに対して3.13で実行した（`s4bi_next_stage_sim_d49a4cc.txt`）。次の段階はENDを保存最終に固定するので、試験対象でなくd49a4ccで行った。

    [A] tested commit d49a4cc89ee682cc4656f6f037a97e510771e906
      v2_scope_chain: Ran 34 tests | OK
      v2_history_maintain: Ran 31 tests | OK
      v2_daily_run: Ran 19 tests | OK
      v2_notify: Ran 19 tests | OK
    [B] END frozen, no open range (expected: test_sc_02 chain test fails)
      v2_scope_chain: Ran 34 tests | FAILED (failures=2)
      （ほかの3つはOK）
    [C] END frozen + minimal open range of the next stage
      4つともOK

次の段階（修正または受領の後の段階）は、test_s4b_09_scope.pyの`END`を、その時点で受領した保存最終に固定し、同じコミットで開いた範囲を足す。N-01の限定修正をする場合、修正は同じS4-Bの開いた範囲（START＝6ad609f、END＝None）の中で行えば、範囲試験の変更は要らない（変更を許すファイルはv2_notify/とtests/v2_notify/と結果文書）。

### 4.8 調べて問題が無かったこと

- 対象Dの規則：jobの`_target_d`はS4-Aの`_target`と同じ`close_at <= now`の最後の1つ。sessionsが`SessionList`でない・例外ならNone（予備の鍵）で、run_morningもその場合RunErrorになる。nowが引けちょうどでも一致する（`s4bi_probe3.py`。ただし試験が固定していない。P-04(a)）。
- 文面：MORNINGの欠けの行はgap=falseかつskipped_sessionsのある日だけで、S4-Aの`_gap_lines`（gap=trueの日）と重ならない。HALTは全部の日。注記4つの条件は設計§4の3どおりで、`NO_COMMIT`の文字列はS4-Aの定数と等しいことが試験で固定されている（test_s4b_10）。`report.target_d`はS4-Aで常に設定されるので、HALTの`Notice`の作成で落ちることは無い。
- 例外の出口：run_morningから出るRunError以外のCoreErrorは、S4-Aでは`_report`の文面作成（`render_message`）からだけ出る。jobはこれをERRORで通知し、投げない（結果§4の4。S4B-16の「CoreErrorは出さない」に合う）。プログラムの誤りは通知の後に同じオブジェクトで出る。
- outboxの書込み：失敗時に書込み口と記述子を閉じ、`NotifyError`はハンドラの外で投げる（`__context__`なし）。短い書込みは続きを書き、0や不正な戻り値は誤りにする。
- 送信アダプタ：`str`型の完全一致だけをSENT・NOT_SENTとし、KeyboardInterrupt・SystemExit以外のBaseExceptionはUNKNOWN（V16で検出）。
- exit_code：DONEかつSENT、またはDONEかつ既存SENTのSKIPPED_CLAIMEDだけ0（V21で検出）。

## 5. 推奨

**限定修正（N-01だけ）。** その後に差分の再レビュー。

- 理由：S4-Bの規則・受入・試験の感度は十分で、Linuxでは受領してよい品質である。ただし、ディレクトリ同期ができない環境（Windowsを含む）では、通知が1通も届かないうえに、回復できないUNKNOWNの意図を鍵ごとに残す。採用済みの設計§5は「（strictなら）」としてモードを想定しており、C-3に同じ形の前例がある。修正は小さく（outbox.pyと試験）、次の段階（S4-C）へ進む前に直すのが安い。
- 修正の範囲：§3のN-01の修正案。担当はD-8と同じSonnet 5.5・highでよい。修正の依頼書では、依頼書§3の5の固定順序を「strictのとき」に改め、受入にWindowsの分岐の模擬（作成時に拒む、ファイル0）と、file_sync_onlyでの送信を足す。P-01(b)とP-04(a)の試験1件ずつを同じ修正に入れてもよい（任意）。
- 受領を先にする場合の代わり：コードを変えずに受領し、受領記録に「LocalOutboxはディレクトリ同期ができる環境（Linux等）専用。Windowsでのtests/v2_notifyは失敗が見込まれる」と書き、N-01をS4-C（gitのoutbox）とS4-Eの条件に持ち越す。本番の予定には影響しないので、これも成り立つ。
- どちらの場合も、提案P-01〜P-04は受領の条件にしない。未実施（実Windows、O_EXCLのWindowsでの振る舞い、物理電源断、利用者PC）は結果§13のとおり残る。

## 6. 保護参照

依頼書§7の92参照＋資料ブランチdocs/v2-notify-s4b-20261105（4c54e01b218148e49e5ae283e7f0bf2fc52edb46）＋設計レビューdocs/v2-notify-s4b-review-20261105（1122052fb15d9e6de516fb9be9aea90bc48f3842）＋再レビューdocs/v2-notify-s4b-v2-rereview-20261105（f10e719e05344379f370860d424b66dc01c0ea6a）の95件を、`git ls-remote`の完全SHAで照合した。あわせて実装ブランチfeat/v2-notify-s4b-20261105がd49a4cc89ee682cc4656f6f037a97e510771e906であることも確かめた。

| 時点 | 結果 |
|---|---|
| 開始時（2026-11-05 00:40Z頃） | 95件一致、実装ブランチd49a4cc |
| 記録の1回目のpush後 | 95件一致（`s4bi_refs_postpush.txt`。記録ブランチの先端は2回目のコミットで追記） |

本レビューの記録は、d49a4ccから作った新しいブランチdocs/v2-notify-s4b-impl-review-20261105にだけ置いた。実装ブランチ・資料ブランチ・mainは変えていない。

## 7. 確認に使ったもの

`docs/reviews/v2_notify_s4b_impl_review_20261105/`（共有フォルダ reviews/ にも写し）：

| ファイル | 内容 |
|---|---|
| s4bi_allver_f3b9f7f.log | 4版×17スイートの結果（§4.1） |
| s4bi_impl_mutants_repro.txt・.json | 実装者のmutate.pyの再現（§4.2） |
| s4bi_mutate.py・s4bi_mutants_out.txt・.json | 独立の変異24件（§4.2） |
| s4bi_probe.py・s4bi_probe_out_py3.13.txt | X1〜X7（P-02 X2、P-03 X3・X4、直し1 X5） |
| s4bi_probe2.py・s4bi_probe2_out_py3.13.txt | R-03の重なり（日本時間の朝、P-01） |
| s4bi_probe3.py・s4bi_probe3_out_py3.13.txt | 引けちょうどのnow（P-04(a)） |
| s4bi_windir.py・s4bi_windir_out_py3.13.txt | ディレクトリ同期ができない環境の1回ずつ（N-01） |
| s4bi_windir_suite.py・s4bi_windir_suite_out_py3.13.txt | 同じ環境での新規試験01〜07（N-01） |
| s4bi_race_report_out.txt | 競合の回数（§4.6） |
| s4bi_next_stage_sim_d49a4cc.txt | 次段階の模擬（§4.7） |
| s4bi_protected95.txt・s4bi_ls_remote_start.txt・s4bi_refs_postpush.txt | 保護95参照と照合（開始時・push後） |

再実行の例（リポジトリの根で、試験対象を取り出して）：

    PYTHONDONTWRITEBYTECODE=1 python3.13 -B docs/reviews/v2_notify_s4b_impl_review_20261105/s4bi_windir.py .
