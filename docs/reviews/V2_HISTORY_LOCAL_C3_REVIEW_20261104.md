# V2 C-3 v2ローカル正本 限定実装 レビュー

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由のRockyさんの依頼（設計採用の「推奨どおり」2026-11-04T01:14Zに続く実装レビュー）。実装者の結論に頼らず、変更境界・受入条件・設計と試行からの違い・欠陥注入・故障の総当たり・範囲試験と次段階の模擬・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常0・提案3。推奨は「受領」（限定修正は不要）。** 提案はどれも任意で、受領の条件にしない（P-01は次にtest_c3_06を触る機会の試験2件、P-02はC-4の設計への引継ぎ、P-03は受領記録の注記）。
本レビューはPR・マージ・本番反映・C-4・S4への移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らして、C-3は日足の履歴を1つのファイルに書く試験用ストアで、時計・ネット・通知・定時実行・自動の再試行や解錠を持たないことも確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | d6b0332500af8d8d46ddaae6c7fda39ee38a03db（C-2の保存最終、実装レビューa91a9edで受領） |
| 試験対象 | **e3d880ad64b08c83985ad641aa16ac6734b380d5**（コード・試験の最終） |
| 保存最終 | **6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a**（feat/v2-history-local-c3-20261104、e3d880aからは結果文書1本の追加だけ） |
| 基準 | 6ad98521a788297f8db64468337c71767dca7304（docs/v2-history-local-c3-20261104）の設計・依頼書第2版（D-1〜D-9採用済み）、試行差分（SHA-256 c3db632d…、一致を確認）、設計レビュー 213bcb7f05d2e1be5f04d529289b437367457f3e（N-01、提案P-01〜P-07） |

読んだもの：依頼書第2版の全文、設計第2版の全文、結果文書（共有フォルダの写しと同じ内容）、実装スレッドの報告、ランタイム3ファイルの全文（449行）、比較のためS2のv2_persistence/local/store.py・errors.py・fsops.pyとv2_history_publishのvalues.py・check.py、新規試験のうちc3_helpers・c3_worker・test_c3_02（前半）・test_c3_03・test_c3_04・test_c3_09・test_c3_10の全文、test_c2_09の差分。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、C3-16・C3-17） | **合格** | d6b0332→e3d880aでMはtest_c2_09の18行目（END）の1行だけ。Aはv2_history_local/の3ファイル（5以下）、tests/v2_history_local/の12本（`__init__.py`なし）。e3d880a→6d69bd7はA 結果文書1本だけ |
| 受入C3-01〜C3-19 | **合格** | 保存最終で4版×14スイートが合格（§4.1）。各IDの試験を読み、主要な規則は独立の変異36件と故障の総当たりで確かめた（§4.2、§4.3） |
| 試行・設計からの違い（結果§4） | **妥当** | 試行のstore.pyとの違いは`_kind`（N-01）と説明文だけ（`diff`で確認）。残りは設計どおりの手順でS2の写し。S2のstore.pyと並べ、違いは名前・v1/一時ファイルの走査・バイトの読み方（C-2のread_history_bytes）・公開値の受け取り・reconcileだけ |
| N-01（第2版） | **対処済み** | `_kind`がbodyの`mode`（初期化は`source`も）を例外が漏れない形で読み、ロックの前に`store_publication_invalid`／shape（`from None`）。test_c3_03 `HandMadeBodiesWithoutMode`で確認。手作り値2万件の探索でも生の例外0（§4.3） |
| C-2の提案P-01（D-4） | **設計どおり** | publishは今を`read_history_bytes`で先に検査し、check_publicationの`publication_invalid`・`publication_stale`以外のCoreErrorを`store_candidate_invalid`に包む。壊れた今と手作りの値の両方がある場合も今の破損を先に返す（test_c3_04） |
| 欠陥注入 | **再現：26件とも検出** | 実装者のmutate.py（依頼書§5の18件＋E1〜E8）をe3d880aで再実行し、全件DETECTED。独立変異36件は検出31、未検出5（等価3、試験の穴2＝P-01）（§4.2） |
| 故障・例外の漏れ（C3-10・C3-14） | **漏れ・不整合0** | 全FileOps呼出し×前後×6種の例外の単独故障1,656通り、2重故障3,880通りで、パス・秘密の漏れ、ファイルの破損、成否不明の取り違え、照合の誤りは0（例外は§4.3、P-02） |
| 次段階の模擬（C3-19） | **保存最終で再現** | 6d69bd7で[A]全件合格、[B]（ENDだけ固定）で範囲の鎖2件だけ失敗、[C]（仮の開いた範囲を追加）で全件合格（§4.4） |
| 保護参照 | **一致** | 依頼書§7の78参照＋資料ブランチ（6ad9852）の79件を`git ls-remote`の完全SHAで照合（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| P-01 | 提案 | 独立変異V05・V19がLinuxの新規139件をすべて通る。V05：`_acquire`で、FileExistsError以外の例外のときにロックの名前に何かあれば`store_busy`にする退避（Windowsではディレクトリが`PermissionError`になる）を外す。S2にはこの注入試験（test_b11_review_fixes、PermissionErrorの注入）があるが、C-3には無い。V19：`_owns`のinodeの比較を外し、マーカーの一致だけで所有とみなす | 実装はS2と同じで正しい。V05はLinuxではディレクトリがFileExistsErrorになるため見えず、実Windowsでtest_c3_06 `Busy`（ディレクトリ）を流せば実機で通る経路。V19は「同じマーカーで別のinode」（同期ツールの作り直し等）でだけ差が出る。将来の変更でどちらかが外れてもLinuxの試験が気づかない | 次にtest_c3_06を触る機会に、(1) ロックの名前に既存のファイルがある状態でcreate_exclusive:lockにPermissionErrorを注入→store_busy、(2) 公開の前にロックを同じマーカーの別ファイルへ差し替え→store_lock_ownership_lost、の2件を足す。今回の受領の条件にしない | V05・V19が検出されること |
| P-02 | 提案 | `_acquire`・`_publish`の`create_exclusive`が「ファイルを作った後に例外を返す」故障（ネットワーク上のFS等で応答だけ失われる場合）。ロックでは自分のロックが残ったまま`store_busy`（cleanupにlock_leftなし）、一時ファイルでは`.history.*.tmp`が残ったまま`store_io_error`／tmp_create（cleanupが空）になる。単独故障の総当たりで、この72通り（4操作×2保存水準×6例外のロック48、2操作×2×6の一時ファイル24）だけが「残り物と固定語の対応」の不変条件から外れた。S2のコードと同じ（受領済みのS2から継承） | 安全側に止まる（次の操作はstore_busy／store_artifact_presentで止まり、history.jsonは変わらない）。ただ、cleanupの固定語だけを見る呼び出し側は、自分の残り物があることを知らない。ローカルの通常のFSではos.openが作成と失敗を同時に返すことはほぼ無い | C-3・S2は直さない。C-4の明示解錠・片付けの設計で、「cleanupに語が無くても、ロック・一時ファイルの残りはあり得る」を前提にする（既知の制限に1行）。ネットワークドライブ上のrootは推奨しない旨を、既知の制限(3)と並べて書く | `c3i_fault_sweep_out_py312.txt`の分類（`c3i_fault_sweep_classify.py`） |
| P-03 | 提案 | 文書・試験の文言の小さなずれ：(a) test_c3_03の冒頭は「`_make`はN-01の項だけ」だが、`WrongTypes.test_a_subclass_of_the_class_is_not_the_class`が派生クラスを`_wrap`で作り、`HandMadeBodiesWithoutMode.test_a_create_value_with_a_wrong_source_is_not_a_genesis`が`mode`の欠落ではない値を`_make`で作る。C3-15の監査（TestFiles）はファイル単位なので通る。(b) 結果文書§4は「試行差分は写していない」と書きつつ、ロジックは`_kind`以外が試行と同一だと開示している（事実の記述としては正確）。(c) 結果文書§7 C3-03の「壊れたファイルもinitialized」は、試験の内容どおり「already_initialized」の意味。(d) c3_worker.pyの`exit`の動作は試験から使われていない | 動作への影響なし。2つの追加の手作り値は、型の厳密な確認と書き方→種類の順序を確かめる妥当な試験。記録を読む人が、C3-15の「`_make`はN-01の項だけ」や試行との関係を誤読するおそれ | 受領記録に(a)〜(d)を注記する。(a)は依頼書の文言をファイル単位の監査に合わせて読む（D-7の趣旨＝ランタイムが作らない、は守られている）。(d)は次に触るときに消してよい | 記録の確認だけ |

重大・通常は無い。

## 4. 確認の詳細

### 4.1 全スイートの再実行（C3-01）

保存最終6d69bd7を、完全な履歴の別クリーンクローン（core.autocrlf=false）にcheckoutし、`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`で14スイートを実行した（`c3i_allver.sh`・`c3i_allver_c1.sh`、結果`c3i_allver_6d69bd7.log`）。

| 版 | 結果 |
|---|---|
| 3.10.20（uv） | 14スイートとも rc＝0。既存1930件（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150）＋新規139件。skipはS2のWindows専用4件だけ |
| 3.11.18 | 同上 |
| 3.12.3 | 同上 |
| 3.13.18 | 同上 |

新規のskipは0（強制終了・リンクの試験もLinuxで動いた）。競合と強制終了のtest_c3_10を3.11で5回繰り返し、5回とも合格した（6プロセス×15回で成功は毎回1回）。

### 4.2 欠陥注入

- **実装者の26件の再現**：共有フォルダのmutate.pyを、e3d880aを含む別クローンで3.12により再実行した。1〜18とE1〜E8の26件すべてDETECTED、失敗数も結果文書§8と一致（`c3i_implementer_mutants_repro.txt`）。
- **独立の変異36件**（`c3i_review_mutants.py`、e3d880aの使い捨てworktreeのstore.pyだけを1件ずつ変え、新規139件を実行、出力`c3i_review_mutants_out.txt`）：

| ID | 内容 | 結果 |
|---|---|---|
| V01 / V02 / V26 | 解放の失敗でprimaryを落とす／成否不明にロックの語を足さない／公開前の所有喪失でロックの語を落とす | 検出（test_c3_06） |
| V03 / V04 / V06 | replaceの失敗で一時ファイルを消さない／書込み中の失敗で片付けない／マーカーの書込み失敗でロックを消さない | 検出 |
| **V05** | FileExistsError以外の例外でロックの名前の存在を見ない（Windowsの退避を外す） | **未検出**（P-01） |
| V07 / V08 | 読込みのI/O誤りをroot_invalidに／通常ファイルでないhistory.jsonを「無い」とみなす | 検出 |
| V09 | 操作ごとのrootの再確認を外す | 検出（test_c3_01） |
| V10 / V11 | publication_stale／publication_invalidを`store_candidate_invalid`に包む | 検出 |
| V12 / V13 / V14 | 書くバイトに改行を1つ足す／結果のpublication_hashを替える／保存水準の語を逆に | 検出 |
| V15 / V16 / V31 | reconcileが書込み可を要求／readが走査しない／reconcileがv1で止まらない | 検出 |
| V17 / V30 | v1_onlyとv1_and_v2を逆に／一時ファイル名を接頭辞だけで判定 | 検出 |
| V18 / V20 | 解放でunlinkしない／所有の確認でマーカーを比べない | 検出 |
| **V19** | 所有の確認でinodeを比べない | **未検出**（P-01） |
| V21 / V22 / V23 / V24 | 短い書込みを再試行しない／ファイルのfsyncを省く／ディレクトリfsyncの失敗を握りつぶす／replaceの失敗のphaseをdir_syncに | 検出 |
| V25 | 公開後に所有を失ったとき、前のcleanupの語を落とす | 未検出・**等価**：`ctx.published`が真になった後に例外が起きるのはreplace・dir_syncで、どちらも`store_commit_uncertain`（別の分岐で語を足す）。この分岐に来るのは例外なしで解放だけ失敗した場合だけで、前の語は常に空 |
| V27 / V28 | マーカーの固定語の改行を外す／乱数部を固定に | 検出（test_c3_06 Marker） |
| V29 | 一時ファイル名の乱数部を固定に | 未検出・**等価**：ロックの下でだけ作るので名前は衝突せず、残りは走査で止まる。名前の形（32桁の16進）だけは試験で固定されていない |
| V32 / V33 / V34 | publishでもsourceを要求／initializeで書込み可を見ない／書込み可を種類より先に | 検出 |
| V35 | 一時ファイルのinodeが違っても消す | 検出（test_c3_07） |
| V36 | rootのrealpathを取らない | 未検出・**等価**：`_managed`の比較もFileOpsの呼出しも同じ結果になる（S2と同じ書き方） |

検出31、未検出5（等価3、試験の穴2＝P-01）。

### 4.3 故障の総当たりと例外の漏れ（C3-10、C3-11、C3-14、N-01）

- **単独故障**（`c3i_fault_sweep.py`）：publish・initialize・read・reconcile×STRICT・FILE_SYNC_ONLYで、故障なしの呼出し列（FileOpsの全15種）を記録し、その各呼出しの前・後に6種の例外（パスと秘密らしい文字列を含むOSError、FileExistsError、FileNotFoundError、PermissionError、ValueError、RuntimeError）を1つずつ起こした。1,656通りで、(1) CoreError以外の例外0、(2) str・repr・属性・cleanup・cause・contextへのパス・秘密の漏れ0、(3) history.jsonは常に前か後のバイトで、後のバイトになるのは成功と`store_commit_uncertain`だけ、(4) read・reconcileはファイルを変えない、(5) 残り物を手で外した後のreconcileが、後のバイトならPUBLISHED、前ならNOT_PUBLISHED、をすべて満たした。外れたのはP-02の72通り（作成後に例外を返すcreate_exclusive）だけ（このほか、コンストラクタ自身のrootの確認への注入96通りは`store_root_invalid`で止まり、対象外として数えていない）。
- **2重故障**（`c3i_fault_pairs.py`）：publish・initializeの呼出しの組（k1＜k2）×前後の組合せで3,880通り。上の不変条件の違反0（replaceの失敗と解放の失敗、所有確認の失敗と一時ファイルの片付けの失敗などの組合せを含む）。
- **手作りの値**（`c3i_handmade_fuzz.py`）：実の公開値のbodyを1〜3か所、削除・20種の値への置換・入れ子の要素の置換で壊し、`_make`で作り直して3操作に渡した。2万件で、CoreError以外の例外0、ロックの残り0、拒否で根が変わったもの0。publishが成功した6件は、request_id・plan_hashだけを形の正しい別の値にしたもので（`c3i_handmade_explain.py`）、check_publicationは確認ではない（C-2§8、設計§8の既知の制限(4)）。書かれたのは正しい候補のバイトそのもので、C-3は型と静的監査で防ぐ設計どおり。

### 4.4 次段階の模擬（C3-19）を保存最終で

実装者のnext_stage_sim.shを、6d69bd7の別クローンで、ENDに固定するSHAを6d69bd7（受領するなら次段階が固定する値）として実行した（`c3i_next_stage_sim_6d69bd7.txt`、3.13）。

| 場合 | 範囲の鎖34 | C-1 112 | C-2 150 | C-3 139 |
|---|---|---|---|---|
| [A] 6d69bd7のまま | OK | OK | OK | OK |
| [B] test_c3_09のENDだけ6d69bd7に固定（1行） | **失敗2**（開いた範囲が0本） | OK | OK | OK |
| [C] [B]＋仮の開いた範囲試験1本（START＝6d69bd7、END=None） | OK | OK | OK | OK |

[B]の2件は設計§6.1・C-2レビュー§4.5の想定どおり。次の段階はENDの固定と自分の開いた範囲試験を同じコミットで足す。C-3の範囲試験は自分のSTART・ENDをHEADから読む（`test_the_range_values_of_this_file_are_read_from_the_text_at_head`）ので1行で足りる。

### 4.5 そのほか読んだ点

- 確認の順序は、型→書き方（`_kind`）→種類（not_append／not_genesis）→書込み可→root→ロック→v1→一時ファイル→読込み→今の検査→check_publication→保存水準→一時ファイル→所有確認→replace→ディレクトリfsync→解放。設計レビューの提案P-04の順と同じで、test_c3_03 `test_the_kind_is_judged_before_writability`が一部を固定している。
- reconcileは`_kind`を通らないが、`type(p) is HistoryPublication`だけはロックの前に確かめ、形の誤りはreconcile_publicationの`publication_invalid`（ロックの下、解放される）になる。設計§4.3「公開値なら書き方を問わない」どおり。
- 初期化は壊れたhistory.jsonでも`already_initialized`（設計§4.2「history.jsonだけ」の行）。データを上書きしない側に止まる。
- 子プロセスは子の中で作り手（publish_day）から公開値を作る（設計レビューP-07）。強制終了は親の`proc.kill()`（POSIXではSIGKILL）で、子が一時停止の行を出してから行い、sleepに頼らない。
- 範囲試験は作業ツリーを読まず、`C.show`の引数はREV・START・'HEAD'だけ（ASTで自己監査）。v2_history_publishから取る名前は8つで、設計§2.3の一覧と一致。
- 試験はtempfileの一時ディレクトリにだけ書き、ネットワークは既存ヘルパーのsocket無効化（子プロセスでも有効であることをProbeで確認）。

## 5. 推奨と次の作業

- **推奨：受領**（e3d880aを試験対象、6d69bd7を保存最終として受け取る）。限定修正の依頼は不要。
- 受領する場合の残り：実Windowsでの実行は未実施（依頼書§6の新規139＋1454＝1593件。C-3のWindows専用の確認＝strictの拒否、ロック・一時ファイル名の扱い、P-01のV05の経路を含む）。ユーザーPC、物理電源断、ネットワークドライブ・同期フォルダ上のroot、unshareによる通信遮断も未実施。
- 次の段階（C-4、移行・採用の実行、明示解錠、退避）の依頼書を作るとき：(1) test_c3_09の`END = None`を6d69bd7（受領した最終）に1行で固定し、同じコミットで自分の開いた範囲試験（START＝6d69bd7）を足す、(2) a6340c3 §5.5の未決とC-2のC-4への引継ぎ（REPLACEの中断後は退避した元バイトからpublish_adoptionで作り直す）を扱う、(3) P-02の「cleanupの語が無くても残り物はあり得る」を明示解錠・片付けの前提にする。C-4の実装は未承認のまま。
- 範囲外のまま残るもの：設計レビュー213bcb7の提案P-01〜P-07（P-04・P-07は実装で満たされている）、C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03、B-4§7.1の既知の制限、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02。

## 6. 作業記録

- 保護参照：2026-11-04T02:11Z、依頼書§7の78参照＋docs/v2-history-local-c3-20261104（6ad9852）の79件を`git ls-remote`で照合し、全件一致（実装ブランチは6d69bd7で、実装者のpush後の記録と同じ）。本記録のpush後にも照合する（結果はスレッドの報告に記す）。
- 変更したもの：本書と確認スクリプト・出力（`docs/reviews/v2_history_local_c3_impl_review_20261104/`）だけを、6d69bd7から作った新しい資料ブランチdocs/v2-history-local-c3-impl-review-20261104に追加した。製品コード・実装ブランチ・既存試験・設定の変更、PR、マージ、Actions、送信、新しい市場計算は0。変異・模擬・故障の総当たりは使い捨てのクローン・worktree・一時ディレクトリで実行し、pushしていない。
- 確認スクリプト：`c3i_fault_sweep.py`・`c3i_fault_pairs.py`は`python -B <script> <e3d880aのworktree>`、`c3i_handmade_fuzz.py`は`<worktree> <件数>`（2万件、乱数の種は固定）、`c3i_review_mutants.py`は`<python> <worktree>`（store.pyを変えて戻す）。`c3i_allver.sh`・`c3i_allver_c1.sh`は実装者のrunall.shを使う4版の実行の手順（パスはこのセッションの一時領域）。
- モデル別の利用量は未計測。
