# V2 C-2 公開値と照合 限定実装 レビュー

作成日：2026-11-03（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由のRockyさんの依頼。実装者の結論に頼らず、変更境界・受入条件・試行からの違い・欠陥注入・C-1提案P-01の取り込み・範囲試験と次段階の模擬・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常0・提案3。推奨は「受領」（限定修正は不要）。** 提案はどれも任意で、受領の条件にしない（P-01はC-3の設計への引継ぎ、P-02は次にtest_c2_03を触る機会の試験1件、P-03は受領記録の注記）。
本レビューはPR・マージ・本番反映・C-3・C-4への移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らして、C-2は日足の履歴の公開値・CAS・照合を純粋な計算として作るだけで、時計・ファイル・ネット・送信を持たないことも確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | de6549acb4ecea759cc771300fd0bef59dd5456a（C-1の保存最終） |
| ランタイム | 52782ac642b78a41fe862ab2cc1d86185584a336 |
| 試験対象 | **29e26592f3c0e79d8d33fd3296e4e8c32817907f** |
| 保存最終 | **d6b0332500af8d8d46ddaae6c7fda39ee38a03db**（feat/v2-history-publish-c2-20261103、29e2659からは結果文書1本の追加だけ） |
| 基準 | 081637e95160a23aab5ea0fc3a2edd01976abba4（docs/v2-history-publish-c2-revision-20261103）の設計・依頼書第2版（D-1〜D-8は推奨どおり採用として実装に移行）、設計レビュー a6e783e57c1de5dd92e6b43cfc416a1d79a672eb、C-1レビュー b473db46ad3dbf3ad76fa76f50c49b03b558936d（§4.5、P-01） |

読んだもの：依頼書第2版の全文、設計第2版の§4〜§6、結果文書（共有フォルダの写しと同じ内容）、実装スレッドの報告、ランタイム6ファイルの全文（519行）、test_c1_09の差分、新規試験のうちc2_helpers・test_c2_03（Verified）・test_c2_05全体・test_c2_06（Leak）・test_c2_07・test_c2_09（Constructors）、比較のためv2_persistence/local/store.pyのsnapshot読込みとv2_history/migrate.pyのconfirm_migration_plan、CLAUDE.md。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、C2-16・C2-17） | **合格** | de6549a→29e2659でMはtest_c1_09だけ（差分のSHA-256は結果文書の5b2c5fbd…と一致、2行）。Aはv2_history_publish/の6ファイル（7以下）、tests/v2_history_publish/の9本（`__init__.py`なし）。29e2659→d6b0332はA 結果文書1本だけ |
| 受入C2-01〜C2-19 | **合格** | 保存最終で4版×13スイートが合格（§4.1）。各IDの試験を読み、主要な規則は独立の変異22件で確かめた（§4.3） |
| 試行からの違い（結果§3） | **すべて妥当** | R-03（整数の範囲）、P-03（引数の誤用を先に）、R-02（物理prefixのdigestだけ）は依頼書第2版のとおり。移行のv1バイトの読み方はS2のstore.pyと同じ（UTF-8→decode_snapshot→validate_snapshot、型の誤りはsnapshot_invalid） |
| 欠陥注入39件 | **再現：39件とも検出** | 実装者のmutate.pyを29e2659の別クローンで再実行し、38件DETECTED、M18はDETECTED_BY_SIMULATION（§4.3） |
| 例外の漏れ（C2-14） | **漏れ0** | 実装者と別の探索（7つの元×全欄×20種の値と削除、記録・候補の要素の差し替え、8種の今）で約34万回呼び、CoreError以外の例外0（§4.2） |
| C-1の提案P-01 | **取り込み済み** | 受入C2-10に入り、test_c2_03のVerifiedが§4.5の履歴そのもので(a)(b)を拒否、(c)を特性として固定（§4.4） |
| 次段階の模擬（C2-19） | **保存最終で再現** | d6b0332で[A]全件合格、[B]（ENDだけ固定）でtest_sc_02のChainJudge 2件だけ失敗（「2 chain beginnings」）、[C]（仮の開いた範囲を追加）で全件合格（§4.5） |
| 保護参照 | **一致** | 依頼書§7の75参照＋第2版資料ブランチ＋実装ブランチ（d6b0332）の77件を`git ls-remote`の完全SHAで照合（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| P-01 | 提案 | check.py `_candidate`（validate_historyの呼出し）。候補の中身が無効な公開値（`_make`で手作りしたものだけ）では、check_publicationの拒否が`history_invalid`（rule＝event_hash・seq・current_state・head・record_keys・header_keys）、`unsupported_event`、`unsupported_schema`になる。設計§5.2手順3は文字どおりには「違えばpublication_invalid／candidate_digest」。実装はこれを試験（test_c2_05 `test_a_publication_whose_content_is_wrong_is_not_an_error_for_the_reconciliation`）で`history_invalid`と固定している。照合（reconcile）は設計どおり候補を作らないので、同じ手作りの値にPUBLISHED等を返す | 作り手（publish_\*）の値では到達しない（候補はvalidate_history済み、APPENDの候補は期待どおりの今＋同じrecords）。手作りの値はC2-10(c)とConstructorsの監査で既に「C-3はpublish_\*の値だけを受け取る」に引き継がれている。ただ、C-3がcheck_publicationの`history_invalid`を「今のファイルが壊れている」と読むと、手作りの値で誤った診断の経路へ進みうる | C-2は直さない。C-3の設計に「今は先にread_history_bytesで読み（設計§5.4の順）、その後のcheck_publicationの`history_invalid`は今の破損ではなく内部の不整合として扱う」と書く。C-2を将来触るなら、`_candidate`のCoreErrorを`publication_invalid`／candidate_digestへ包むのが設計の文言に近い | `c2i_probe_leak.py`の出力（拒否の内訳） |
| P-02 | 提案 | build.py `_snapshot_of`。依頼書§3「S2と同じ厳格さで読んでから確認する」の**順序**を固定する試験が無い。独立変異V14（`validate_snapshot`を外す）は通常の試験をすべて通る。単独の誤りではconfirm_migration_plan自身がvalidate_snapshotを呼ぶので同じcodeになるが、確認hashも誤っているときは、実装は`unsupported_schema`（core_sha）、変異は`migration_plan_mismatch`を返す（`c2i_probe_v14.py`で両方を確認） | 動作は今のところ正しい。将来の変更でv1のバイトの読み方が確認の後ろへ回っても試験が気づかない | 次にtest_c2_03を触る機会に、「decode_snapshotは通るがvalidate_snapshotで拒否されるv1バイト＋誤った確認hash→snapshotの拒否が先」の1件を足す。今回の受領の条件にしない | V14が検出されること |
| P-03 | 提案 | 結果文書§6と試験の記述の小さなずれ：(a)「最初に失敗した試験」は`-f`（最初の失敗で止める）の結果なので、M29・M30・M32がtest_c2_01の照合の試験（`test_a_reconciliation_holds_the_outcome_and_the_hash_only`）に帰されている（この試験は全ケースの公開値をreconcileするので正しく失敗するが、狙った試験ではない）。M06・M12・M15・M21・M22の欄は「FAIL: test_…」の途中で切れている。(b) 変異の番号にM27が無い（件数39は正しい）。(c) test_c2_03 225行目の`assertEqual(e[:2], … if e[1] is None else e[:2])`は常に成り立つ（直後の226行目が実際の確認） | 動作への影響なし。記録を読む人が、どの試験が変異を捉えたかを誤解するおそれ | 受領記録に(a)〜(c)を注記する。225行目は次にtest_c2_03を触るときに消してよい | 記録の確認だけ |

重大・通常は無い。

## 4. 確認の詳細

### 4.1 全スイートの再実行（C2-01）

保存最終d6b0332を、完全な履歴の別クリーンクローン4つ（core.autocrlf=false）にcheckoutし、`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`で13スイートを実行した（`c2i_allver.sh`、結果`c2i_allver_d6b0332.log`）。

| 版 | 結果 |
|---|---|
| 3.10.20（uv） | 13スイートとも rc＝0。合計1930件（既存1780＋新規150）、skipはS2のWindows専用4件だけ |
| 3.11.18 | 同上 |
| 3.12.3 | 同上 |
| 3.13.18 | 同上 |

`git archive`のツリー（3.12）でのskip：C-2 28（実行150件）、C-1 22、範囲の鎖33。結果文書§5と一致した。

### 4.2 例外の漏れと拒否の内訳（C2-14、P-01）

`c2i_probe_leak.py`：7つの元の公開値ごとに、bodyのすべての欄（入れ子のrecords・candidate_historyの先頭3要素まで）を20種の値（None、真偽、0・負・2^63・10^30、小数、空文字、hex、list、dict、日付文字列等）と削除に替えて`_make`で作り直し、さらにrecords／eventsの最後の要素を非dict・空dict・seqだけのdict・余分なキー付きに替えて、8種の今（期待の今、候補、None、BOM付き、`{`、`[]`、`null`、候補の延長）でcheck_publicationとreconcile_publicationを呼んだ。**342,496回でCoreError以外の例外は0**。

拒否の内訳で、check_publicationは公開値の誤りを`publication_invalid`（shape・mode・records・candidate_digest）で返すが、候補の中身を壊した値は`history_invalid`（event_hash・seq・current_state等）・`unsupported_event`・`unsupported_schema`で返した（P-01）。reconcile_publicationは形の誤りだけを例外にし、残りは4つの結果で返した。

### 4.3 欠陥注入

- **実装者の39件の再現**：共有フォルダのmutate.pyを、29e2659を含む別クローンで3.12により再実行した。M01〜M38（M27なし、2a/2b・7a/7bを含む）のうち38件がDETECTED、M18がDETECTED_BY_SIMULATION（`c2i_implementer_mutants_repro.txt`）。結果文書§6の「検出39、等価0」と一致。
- **独立の変異22件**（`c2i_review_mutants.py`、29e2659の`git archive`の複製、`-f`なしでtest_c2_01〜07、出力`c2i_review_mutants_out.txt`）：

| ID | 内容 | 結果 |
|---|---|---|
| V01 / V02 | CASの候補の比較からstate digest／head hashを外す | 検出 |
| V03 | 照合のPUBLISHEDをdigestだけで判定 | 検出（test_the_head_of_a_published_candidate…） |
| V04 | 照合でCREATEの「無い」をCONFLICTに | 検出 |
| V05〜V09 | 形の検査からDAILYの日・計画の元のrequest_id・REPLACEのexpected・MIGRATIONのsource_v1・CREATEのexpected=Noneを外す | 5件とも検出 |
| V10 | 移行のv1の型の誤用を見ない | 検出 |
| V11 | raw_identityがbytearrayを受け付ける | 検出 |
| V12 / V13 | RESTORE／RESTARTの状態の確認を外す | 検出（NO_CHANGEの拒否のcode） |
| **V14** | v1のsnapshotを確認の前に検査しない | **未検出**（単独の誤りでは等価、確認hashとの複合で区別できる。P-02） |
| V15 | v1のバイトをutf-8-sigで読む（BOMを除く） | 検出 |
| V16 | recordsの先頭seqを1つずらす | 検出 |
| V17 | 今の無効なUTF-8を置換して読む | 検出 |
| V18 | APPENDの今を正規化バイトで比べる（字下げ付きがstale） | 検出 |
| V19 | 採用で計画の識別値と受け取ったバイトの比較を外す | 検出（test_c2_07の代役） |
| V20 | 照合で今の型の誤用を見ない | 検出 |
| **V21** | summaryが無効なrequest_idもそのまま出す | **等価**（作り手の値のrequest_idは常に計画の検査済みの値。手作りの値でだけ違い、summaryは市場値等を出さない白リストのまま） |
| V22 | 読めない今をpublication_staleにする | 検出 |

検出20、未検出1（V14、P-02）、等価1（V21）。

### 4.4 C-1の提案P-01と分担（C2-10）

C-1レビュー§4.5の履歴（再開始をREPLAYし、REAPPLYの後に解放されていないD5をCONSUME）を、test_c2_03 `Verified`が同じ組み立て（`[("REPLAY", 2), ("REAPPLY", 3), (CONSUME, D5)]`、独立のoracle）で作り、検査器（validate_history）は受け付け、計画は`restore_invalid／ops／restore_consume_not_released`で拒否することを確かめている。そのうえで(a) 正しい計画のbasisをその履歴に書き換えhashを付け直した計画、(b) その履歴を持つRestoreConfirmResult、のどちらも`history_plan_mismatch`で公開値にならない。(c) 同じ履歴を`_make`で手作りした値はcheck_publicationを通る（特性）。publish_\*は7つで、Historyを受け取る関数が無いこと、`_make`の呼出しがbuild.pyの2か所だけであること（Constructors、AST）も試験されている。C-1の提案P-01は受入条件と試験の両方に入っていると判断した。

ランタイムを読んで、作り手は各確認の関数の正の結果（PREPARED、CONFIRMED_IN_MEMORY）からだけ公開値を作り、検査器を通っただけの履歴を受け取る経路が無いことも確かめた。採用はexpectedを受け取ったバイトから計算し、計画の値は一致を確かめるだけ。bodyに`discarded`・`diagnosis`の名のキーは無い（P-02規則1〜4の識別値の部分）。

### 4.5 次段階の模擬（C2-19）を保存最終で

実装者のnext_stage_sim.shを、d6b0332の別クローンで、ENDに固定するSHAをd6b0332（受領するなら次段階が固定する値）として実行した（`c2i_next_stage_sim_d6b0332.txt`、3.12）。

| 場合 | 範囲の鎖34 | C-1 112 | C-2 150 |
|---|---|---|---|
| [A] d6b0332のまま | OK | OK | OK |
| [B] test_c2_09のENDだけd6b0332に固定（1行） | **失敗2**：test_sc_02 `ChainJudge.test_an_open_range_that_is_not_last_is_rejected`、`test_two_open_ranges_are_rejected`（どちらも「2 chain beginnings (expected 1)」） | OK | OK |
| [C] [B]＋仮の開いた範囲試験1本（START＝d6b0332、END=None） | OK | OK | OK |

[B]の2件は、開いた範囲が0本になる形でだけ起きる（設計§6.3の想定どおり）。次の段階はENDの固定と自分の開いた範囲試験を同じコミットで足すので、test_sc_02は直さない。保存最終が試験対象と結果文書1本しか違わないので、範囲試験は29e2659と同じ結果になった。

### 4.6 そのほか読んだ点

- 形の検査は`_body`1つで、check_publicationとreconcile_publicationが共有している（同じ値には同じ拒否。test_c2_05 Boundariesでも確認）。整数の欄は`type(x) is int`かつ0以上で、boolを除く。candidate_head_seqはAPPENDで`expected.head_seq + len(records)`、CREATE/REPLACEで`len(events) − 1`。
- 照合の順序：形→引数→Noneの扱い→REPLACEの「元のまま」→読めなければCONFLICT→PUBLISHED→物理prefixのdigestでPUBLISHED_THEN_EXTENDED→APPENDの「まだ期待どおり」→CONFLICT。設計§5.3と同じ。巨大なcandidate_head_seqでも`len(events) > n`が偽になるだけで、スライスには届かない。
- hashlibのimportはread.pyだけ（ほかはv2_persistence.codecのsha256_textを使う）。importは設計§2.3の範囲で、新しい依存・ファイル・時計・乱数・ネットは無い。
- GENESISの公開値は、同じgenesisから始まる別の履歴をPUBLISHED_THEN_EXTENDEDと判定する（試験で明記）。genesisはstart_afterと暦から決まる1件なので、この判定は正しい。

## 5. 推奨と次の作業

- **推奨：受領**（29e2659を試験対象、d6b0332を保存最終として受け取る）。限定修正の依頼は不要。
- 受領する場合の残り：実Windowsでの実行は未実施（依頼書§6の新規150＋1304＝1454件）。ユーザーPC、物理電源断、autocrlf=trueも未実施。
- 次の段階（C-3、v2ローカル正本）の設計・依頼書を作るとき：(1) test_c2_09の`END = None`をd6b0332（受領した最終）に1行で固定し、同じコミットで自分の開いた範囲試験（START＝d6b0332）を足す、(2) 実装者の引継ぎどおり「同じプロセスでpublish_\*が返した値だけを受け取り、build.py以外が`_make`・`object.__new__(HistoryPublication)`を呼ばないことを範囲試験で監査」を受入条件に入れる、(3) P-01の扱い（今はread_history_bytesで先に読み、check_publicationの`history_invalid`を今の破損と読まない）を設計に書く。C-4には「REPLACEの中断後は退避へ写した元バイトからpublish_adoptionで作り直す」を引き継ぐ。C-3・C-4の実装は未承認のまま。
- 範囲外のまま残るもの：C-1レビューのP-02・P-03、B-4§7.1の既知の制限、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02。

## 6. 作業記録

- 保護参照：2026-11-03T16:07Z、依頼書§7の75参照＋docs/v2-history-publish-c2-revision-20261103（081637e）＋feat/v2-history-publish-c2-20261103（d6b0332）の77件を`git ls-remote`で照合し、全件一致。本記録のpush後にも照合する（結果はスレッドの報告に記す）。
- 変更したもの：本書と確認スクリプト・出力（`docs/reviews/v2_history_publish_c2_impl_review_20261103/`）だけを、d6b0332から作った新しい資料ブランチdocs/v2-history-publish-c2-impl-review-20261103に追加した。製品コード・実装ブランチ・既存試験・設定の変更、PR、マージ、Actions、送信、新しい市場計算は0。変異と模擬は使い捨てのクローン・worktree・`git archive`の複製で実行し、pushしていない。
- 確認スクリプト：`c2i_probe_leak.py`・`c2i_probe_v14.py`はリポジトリの根で`python -B <path>`、`c2i_review_mutants.py`は`<repo> <tested-sha> <python>`を渡す（リポジトリには書かない）。`c2i_allver.sh`は実装者のrunall.shを使う4版の実行の手順。
- モデル別の利用量は未計測。
