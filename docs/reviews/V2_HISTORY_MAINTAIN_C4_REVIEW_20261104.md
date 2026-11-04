# V2 C-4 保守操作（解錠・移行・採用） 限定実装 レビュー

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5・high（`get_session`の`session_context.model`＝claude-opus-5-5[1m]、`effort_level`＝high、`last_served_model`＝claude-opus-5-5）。プロジェクトの方針（実装レビューはOpus・highの別スレッド）に基づく、コーディネーター経由のRockyさんの依頼（「推奨どおり。レビューを実施してください」2026-11-04T04:08Z）。実装者の結論に頼らず、変更境界・受入条件・設計と依頼書からの違い・欠陥注入（等価の判断を含む）・故障の総当たり（例外の種類の追加と2重故障）・範囲試験と次段階の模擬・保護参照・4版での再現を独立に確かめた。製品コード・実装ブランチ・既存試験は変更していない。

結論：**重大0・通常1・提案4。推奨は「限定修正」（N-01だけ）。** N-01は、移行の再開の経路で`history.json`がロックの下で見つからないと、CoreErrorでない`TypeError`が漏れる不具合で、受入C4-16(1)「CoreError以外が漏れない」とC-3の流儀に反する。データの消失・パスの漏れは無く、修正は2か所と試験数件で済む。提案はどれも任意で、受領の条件にしない。
本レビューはPR・マージ・本番反映・S4への移行の承認ではない。運用方針（日足だけで判定し、早朝に米国の確定日足で通知、夜の寄付きで手動購入。分足・NBBOは前提にしない）に照らして、C-4は人が日中に行う保守の道具で、時計・ネット・通知・定時実行・自動の再試行や解錠・退避先の削除を持たないことも確認した。

## 1. 対象と基準

| 項目 | 完全SHA・内容 |
|---|---|
| 実装開始 | 6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a（C-3の保存最終、実装レビュー2049e10で受領） |
| 試験対象 | **1eb4261ff4ea1c312bce3725fe50d39b20988b05**（コード・試験の最終） |
| 保存最終 | **9b00efd00074695626fb84d5490c9c8ea89edc16**（feat/v2-history-maintain-c4-20261104、1eb4261からは結果文書1本の追加だけ） |
| 基準 | d11b87597ef4035f5fee0ffc8c9fa859f82fe00f（docs/v2-history-maintain-c4-20261104）の設計・依頼書第2版（D-1〜D-9採用済み）、設計レビュー74c93b1（N-01〜N-03、提案P-01〜P-06）、再レビュー8f39111（提案Q-01・Q-02） |

読んだもの：依頼書第2版の全文、設計第2版の全文、結果文書の全文、ランタイム4ファイルの全文（1,190行）、比較のためC-3のv2_history_local/store.pyとC-2のcheck.py（reconcile_publication）、新規試験のうちc4_helpers・test_c4_07の全文、test_c4_04（C4-10(d)）・test_c4_05（C4-13）・test_c4_08（C4-18）の該当部分、test_c3_09の差分、共有フォルダの実装者のmutate.py・next_stage_sim.sh・runall.sh・refcheck.py。取得できなかったファイルは無い。

## 2. 確認の要点

| 観点 | 判定 | 根拠（§4に詳細） |
|---|---|---|
| 変更境界（依頼書§2、C4-21） | **合格** | 6d69bd7→1eb4261はA 15本・M 1本。Mはtest_c3_09のEND の1行だけ（設計§6.1の文言どおり）。Aはv2_history_maintain/の4ファイル（6以下）とtests/v2_history_maintain/の11本（`__init__.py`なし）。1eb4261→9b00efdはA 結果文書1本だけ |
| 依存とimport（C4-20） | **合格** | 標準ライブラリはos・secrets・stat・json・copy・dataclasses・typingだけ（設計§2.3）。v2_history_publishからの名前は12個で設計の一覧と一致。v2_history_local・LocalFileStore・hashlibのimportなし。osはパスの組立てとMaintenanceOps（mkdir・renameだけを追加）だけ |
| 受入C4-01〜C4-22 | **C4-16(1)を除き合格** | 試験対象・保存最終で4版×15スイートが合格（§4.1）。C4-16(1)は依頼の3種の例外では満たすが、FileNotFoundErrorでは移行の再開で破れる（N-01） |
| 第2版のN-01〜N-03とQ-01・Q-02 | **対処済み** | C4-10(d)（別のrequested_atでhashが違い、両方・history.jsonだけの状態でrootを変えずに止まる）、C4-12（prepare_*の呼び直し）、C4-13（読込み→照合→MANIFESTの順序と、読んだバイトを替えるとMANIFESTも退避先も作られない）、C4-20（C-2の値への`_make`等の禁止とC-4自身の値の許可）を試験で確認。Q-01は結果§11、Q-02は結果§0 |
| 試行・設計からの違い（結果§8） | **妥当** | 8項目とも設計・依頼書の規則の範囲内。特に「inspectが壊れた状態を報告し例外にしない」「check_planが名前と種類を2つの形に限る」（設計レビューP-03・P-05の趣旨を満たす） |
| 欠陥注入 | **再現：31件検出、19bは等価で妥当** | 実装者のmutate.pyを1eb4261で再実行し、結果文書§9と同じ（§4.2）。19bの等価の判断は、コードの経路と出口の誤りの観測の両方で確かめた。独立変異29件は検出18、等価4、試験の穴7（P-03） |
| 故障・例外の漏れ（C4-16、C4-19） | **N-01の160通りだけ** | 例外5種を足した単独故障2,125通り、2重故障（1回目の故障の後に、人の復旧の1巡目でもう1回）91,770通りで、元のバイトの消失・history.jsonの取り違え・パスや秘密の漏れ・復旧の失敗は0。外れたのはN-01の160通りだけ（§4.3） |
| 次段階の模擬（C4-22） | **保存最終で再現** | 9b00efdで[A]全件合格、[B]（ENDだけ固定）で範囲の鎖2件だけ失敗、[C]（仮の開いた範囲を追加）で全件合格（§4.4） |
| 保護参照 | **一致** | 依頼書§7の82参照＋資料ブランチ（d11b875）＋実装ブランチ（9b00efd）の84件を`git ls-remote`の完全SHAで照合（§6） |

## 3. 指摘

| ID | 重大度 | 根拠 | 影響 | 修正案 | 確認方法 |
|---|---|---|---|---|---|
| N-01 | 通常 | `v2_history_maintain/store.py` の `_migrate_resume`（787行・809行）が `self._read(...)[0]` と書き、`_read` が `None`（lstat・read_fileがFileNotFoundError＝ロックの下でhistory.jsonが見つからない）を返す場合を扱っていない。`TypeError: 'NoneType' object is not subscriptable` がそのまま漏れる。同じ形の `_adopt_body`（827行）と`read_original`は`None`を扱っており、C-3も`store_uninitialized`等の固定語にする | 「両方」または「history.jsonだけ」の状態で`migrate`を呼び直したとき、history.jsonがロックの下で一瞬見つからない（人や別の道具が消した、ネットワーク上のFSの一時的な誤り）と、利用者には固定語ではなくPythonの例外が出る。ロックは解放され、rootは変わらない（787行）か移行は完了している（809行、renameの後）。パス・秘密は出ない。受入C4-16(1)・設計§5.5の「CoreError以外が漏れない」に反し、結果文書§10の「どの通りでもCoreErrorだけ」は依頼の3種の例外に限った記述になる | 2か所で`None`（と念のため`False`）を固定語にする。787行は`maintenance_state_unexpected`（ruleは今と同じv1_and_v2／v2_present）、809行（renameの後の読み直し）は`maintenance_state_unexpected`か、読み直しをやめてreconcileで確かめた候補を返す。試験は、両方の状態と完了後の状態で`lstat:history`・`read_file:history`にFileNotFoundErrorを注入する数件。C4-16の総当たりの例外の種類にFileNotFoundErrorとPermissionErrorを足すと、同じ穴を今後も拾える（C-3のレビューは6種で行った） | 本レビューの`c4i_probe.py`のX1（4通りとも固定語になること）と`c4i_sweep2.py double migrate strict os,fnf`（漏れ0） |
| P-01 | 提案 | 明示解錠で、最初のrenameの後に次の対象の識別値が変わる（または行き先に何かある）と、`_move`が`maintenance_plan_stale`（または`maintenance_quarantine_invalid`／target）をそのまま返す。依頼書§3は「最初のrenameの後の失敗はmaintenance_incomplete（primaryに元のcode）」、C4-06は「plan_staleはrootと退避先を変えない」としている（`c4i_probe.py`のX2で再現：1つ目を移した後に2つ目を同じバイトの別のinodeに替えると、plan_staleで1つ目は退避先にある） | 書き手が止まっているという宣言に反する変化が解錠の最中に起きたときだけ。人の手順はどちらの語でもinspectから始まり、新しい計画で完了する（X2で確認）ので、復旧には影響しない。語の意味（「何も変えていない」）だけがずれる | `_incomplete`の変換に「ctx.changedの後のplan_stale・quarantine_invalid（phase move）」を足し、primaryに元のcodeを入れる。N-01の限定修正と同じ機会に扱ってよい（任意） | X2の後半がmaintenance_incomplete（primary＝maintenance_plan_stale）になること |
| P-02 | 提案 | 採用で写しの読み戻しが違う（`maintenance_copy_mismatch`）と、退避先に違う写しが残る。同じ公開値で呼び直すと、写しがあるので書き直さず、毎回`maintenance_copy_mismatch`で止まる（X3）。進めるには別のrequested_atで作った計画（別のkey）しかない。設計§5.3の5「写しが無ければ」のとおりの動作で、history.jsonは元のまま | 原因はディスクの破損か手での改ざんで、まれ。止まる側（安全側）だが、設計§5.4の手順（同じ入力で作り直して同じ操作を呼ぶ）では先へ進めず、手順に書かれていない | コードは変えない。結果文書の利用者向け手順（§11）か次の設計に「copy_mismatchの後は、その退避先を人が調べ、新しいrequested_atで計画から作り直す（前の退避先は残る）」と1行足す | 文書の確認だけ |
| P-03 | 提案 | 独立変異のうち7件が新規180件をすべて通る（試験の穴）。いずれも、人が退避先を手で触ったか、宣言に反する書き手がいたときだけ効く防御の確認：V01「両方」の再開で伸びた履歴（PUBLISHED_THEN_EXTENDED）も受け入れる、V02 移行の退避先にhistory.jsonがあっても許す、V05 MANIFESTの正規形を求めない（read_set_aside・inspect側）、V11 check_planが一時ファイルの順を求めない、V17 read_set_asideがMANIFEST内のkeyを比べない、V21 移行の再開でMANIFESTの無い退避先を受け入れて書く、V22 `_move`が行き先の空を確かめない（POSIXのrenameは上書きする） | 実装は正しい。将来の変更でこれらの確認が外れても、試験が気づかない。V22は外れると退避先のバイトを上書きし得る唯一のもの（ただし今のコードの順序では、同じ名前が根と退避先の両方にあり識別値も合う状態は作れない） | 次にtest_c4_03〜05を触る機会に、各1件の試験を足す（退避先へ手で置く・消す・書き換える形で作れる）。今回の受領の条件にしない | V01・V02・V05・V11・V17・V21・V22が検出されること |
| P-04 | 提案 | 記録の小さなずれ：(a) 結果文書§0・§10の「どの通りでもCoreErrorだけ」は依頼の3種の例外での結果（N-01）。(b) 移行の新規の経路で、ロックの下のsnapshot.jsonが見つからないときのruleが`v1_and_v2`（X5。状態はv1も無い）。(c) 結果文書§8の5「計画にロックが無いのに実行時にロックがある場合はplan_stale」は、ロックを取る前の確認（187行）で、ロックの取得と競合した場合はstore_busyになる（どちらも安全側） | 動作への影響なし。読む人が誤解するおそれ | 受領記録または修正版の結果文書に注記する。(b)は`empty`の方が状態に合う | 記録の確認だけ |

重大は無い。

## 4. 確認の詳細

### 4.1 全スイートの再実行（C4-01）

保存最終9b00efdを、完全な履歴の別クリーンクローン（core.autocrlf=false）にcheckoutし、実装者のrunall.sh（`PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover`）で15スイートを実行した（`c4i_allver_9b00efd.log`）。

| 版 | 結果 |
|---|---|
| 3.10.20（uv） | 15スイートとも rc＝0。既存2,069件（コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112、C-2 150、C-3 139）＋新規180件。skipはS2のWindows専用4件だけ。新規の所要253.9秒 |
| 3.11.18 | 同上（新規217.9秒） |
| 3.12.3 | 同上（新規211.1秒） |
| 3.13.18 | 同上（新規229.3秒） |

合計2,249件。新規のskipは0（強制終了・競合の試験もLinuxで動いた）。

### 4.2 欠陥注入

- **実装者の32件の再現**：共有フォルダのmutate.pyを、1eb4261を含む別クローンで3.12により2分割で再実行した（`c4i_implementer_mutants_repro.txt`）。依頼の21項目（10b・19bを含む）とE1〜E9の32件のうち31件がDETECTEDで、失敗した試験の数も結果文書§9と一致した（例：項目3は10件、20は59件、21は20件、E2は21件）。19bだけUNDETECTED。
- **19b（`_mkdir`のexcept内の`raise … from None`）の等価の判断は妥当**：
  - 経路：`_mkdir`は`_q_make`からだけ呼ばれ、`_q_make`の呼出し元は`_unlock_body`・`_migrate_fresh`・`_adopt_body`の3つで、どれも`_locked`か`_exclusive_by_plan_lock`の中で動く。`_mkdir`は呼出しの前に`ctx.changed = True`を立て、`store_io_error`（field quarantine）を投げるので、`_incomplete`が必ず新しい`maintenance_incomplete`に作り直す。`_incomplete`は例外処理の外で呼ばれ、元の誤りへの参照（cause・context）を持たない（primaryは文字列、cleanupは文字列のタプル）。解放の失敗で作り直す場合も同じ。
  - 観測：パスを`filename`に入れたOSErrorを`mkdir:qdir`に注入し、出口の誤りが`maintenance_incomplete`／quarantine／quarantine（primary＝store_io_error）で、`__context__`・`__cause__`ともNoneであることを確かめた（`c4i_probe.py`のX4）。
  - 留意：等価は`_incomplete`の作り直しに依存する。将来`_incomplete`を変えれば潜在の`from None`が表に出るので、規則（例外処理の外で投げる）は書き方として保つのがよい。今の`_mkdir`は規則どおり外で投げている。
- **独立の変異29件**（`c4i_review_mutants.py`、1eb4261の作業ツリーの写しでstore.py・values.pyを1件ずつ変え、test_c4_01〜08を`-f`で実行。出力`c4i_review_mutants_out.txt`）：

| ID | 内容 | 結果 |
|---|---|---|
| V03 / V29 | 解錠で保存水準の確認を退避先の作成の後へ／最後のディレクトリfsyncを外す | 検出（test_c4_03） |
| V04 | 採用で退避先の名前の確認を外す | 検出（test_c4_05） |
| V06 | 公開値のhashの形の確認を外す | 検出（test_c4_06） |
| V08 / V09 | 所有の確認でマーカーを比べない／解放で所有を確かめない | 検出（test_c4_06） |
| V10 | plan_unlockの一時ファイルを逆順に | 検出（test_c4_01） |
| V14 | 公開のディレクトリfsyncをSTRICTでも省く | 検出（test_c4_05） |
| V15 | 採用の完了判定でreconcileの結果を見ない | 検出（test_c4_05） |
| V16 | 変更の後のstore_io_errorを（公開の誤りも）すべてmaintenance_incompleteに | 検出（test_c4_04） |
| V18 | 変更の後の解放の失敗をstore_io_errorに | 検出（test_c4_03） |
| V19 | inspectのロックの持ち主S2とC3を入れ替える | 検出（test_c4_02） |
| V23 | inspectのreadableを常にTrue | 検出（test_c4_02） |
| V24 / V25 | 採用でsnapshot.jsonを拒否しない／移行で一時ファイルの残りを拒否しない | 検出 |
| V26 | 採用の読み戻しを（再開の写しも含めて）全部外す | 検出（test_c4_05） |
| V28 | 解錠の前の「計画の後に現れたロック」の確認を外す | 検出（test_c4_03） |
| V30 | WindowsのSTRICTを拒否しない（E8の対照） | 検出（test_c4_07） |
| **V01 / V02 / V05 / V11 / V17 / V21 / V22** | §3 P-03の7件 | **未検出**（試験の穴、P-03） |
| V07 | ロックが退避済みで一時ファイルが根に残る状態を受け入れる | 未検出・**等価**：ロックは最後に移すので、C-4自身はこの状態を作らない。退避先のロックも同じinodeであることを手順3が確かめるので、人が手で動かさない限り到達しない |
| V12 / V20 | rootと退避先のディレクトリで`is_link_like`を見ない | 未検出・**Linuxでは等価**：シンボリックリンクはlstatでディレクトリにならず先に拒否される。`is_link_like`が効くのはWindowsのジャンクション等で、実Windowsの試験でだけ意味がある（C-3レビューP-01のV05と同じ型） |
| V27 | 計画にロックがあるとき、実行時のロックを部分集合の確認から外す | 未検出・**等価**：計画にロックがあれば`write.lock`は必ず対象の名前に入っているので、元の条件でも拒否は起きない |

検出18、未検出11（等価4、試験の穴7＝P-03）。

### 4.3 故障の総当たりと例外の漏れ（C4-16、C4-19）

実装者の`Scenario`（準備・不変条件・§5.4の手順）をそのまま使い、故障の入れ方だけを広げた（`c4i_sweep2.py`、3.12）。

- **例外の種類の追加（単独故障）**：故障なしの呼出し列の各呼出しの前・後に、FileNotFoundError・PermissionError・IsADirectoryError（パスと秘密らしい文字列入り）、KeyError・ValueErrorの5種を1つずつ起こした。移行STRICT 465通り、FILE_SYNC_ONLYで移行385・採用440・解錠（ロックあり）405・解錠（一時ファイルだけ）430、計2,125通り。CoreError以外の例外0、パス・秘密の漏れ0、不変条件（元のバイトはrootか退避先、history.jsonは元か候補）の違反0、全件が§5.4の手順で最終の状態に着いた。
- **2重故障**：1回目の操作の各呼出しの前・後に故障（パス・秘密入りのOSError）を起こし、続く人の復旧の1巡目（inspect→残りがあれば新しい計画で解錠→read_original／read_set_asideから作り直して同じ操作）の各呼出しの前・後に、もう1回の故障（同じOSErrorかFileNotFoundError）を起こした。その後は故障なしで§5.4の手順を最後まで行い、最終の状態を確かめた（STRICT）。

| 場面 | 通り | CoreError以外 | 不変条件の違反 | 最終の状態に着かない |
|---|---|---|---|---|
| 移行 | 21,914 | **160（N-01）** | 0 | 0（160通りも、漏れの後の手順で完了） |
| 採用 | 25,474 | 0 | 0 | 0 |
| 解錠（ロックあり） | 21,374 | 0 | 0 | 0 |
| 解錠（一時ファイルだけ） | 23,008 | 0 | 0 | 0 |

  解錠の2場面は、初回の実行で本レビューの道具の誤り（復旧の1巡目の後の確認が、元の計画のkeyの退避先だけを見ていた。人の計画は別のkeyになる）による見かけの違反が出たため、確認を「rootかどこかのkeyの退避先に元のバイトがある」に直して再実行した。表は再実行の結果。
  N-01の160通りは、1回目にreplaceの前後で止まり「両方」または「history.jsonだけ」の状態になった後、復旧の`migrate`の中でhistory.jsonのlstat・read_fileがFileNotFoundErrorを返したものだけ。単独故障ではX1で4通りを直接再現した。
- **個別の確認**（`c4i_probe.py`、出力`c4i_probe_out_py312.txt`）：X1（N-01）、X2（P-01）、X3（P-02：copy_mismatchの後に同じ公開値では先へ進まず、別のrequested_atなら完了）、X4（19b）、X5（P-04(b)）、X6（計画のロックを持ち主が外した後の解錠はplan_staleで何も変えない）、X7（history.jsonがディレクトリ・quarantineがファイルでもinspectは報告して止まらない＝設計レビューP-03の趣旨）、X8（採用の完了後に写しを手で消すと完了と認めずpublication_stale／raw）、X9（読取り専用の採用はstore_read_only）。

### 4.4 次段階の模擬（C4-22）を保存最終で

実装者のnext_stage_sim.shを、9b00efdの別クローンで、ENDに固定するSHAを9b00efdとして実行した（`c4i_next_stage_sim_9b00efd.txt`、3.13）。

| 場合 | 範囲の鎖34 | C-1 112 | C-2 150 | C-3 139 | C-4 180 |
|---|---|---|---|---|---|
| [A] 9b00efdのまま | OK | OK | OK | OK | OK |
| [B] test_c4_09のENDだけ9b00efdに固定（1行） | **失敗2**（開いた範囲が0本） | OK | OK | OK | OK |
| [C] [B]＋仮の開いた範囲試験1本（START＝9b00efd、END=None） | OK | OK | OK | OK | OK |

[B]の2件は設計§6・C-3レビュー§4.4と同じ想定どおり。限定修正をする場合は、修正の最終コミットが新しい保存最終になり、次の段階はそのSHAでENDを固定する（C-4の範囲試験のSTARTは6d69bd7のまま）。

### 4.5 そのほか読んだ点

- 確認の順序：型→書き方（`_kind`、hashの形まで）→種類（not_migration／not_adoption）→宣言（移行）→書込み可→root→ロック→一時ファイル・v1の走査→ロックの下の読込み→check_publication→保存水準→退避先→MANIFEST→（採用は写しと読み戻し）→公開→（移行はrename）→ディレクトリfsync→解放。設計§5.2・§5.3と同じで、Orderの試験が呼出し列で固定している。
- 解錠：計画のロックを排他にするときは新しいロックを取らず、対象の順（一時ファイルの名前順、ロックは最後）にrenameし、各renameの直前にバイトとinodeと行き先の空を確かめる。部分集合の規則で再開する。計画にロックが無いときはC-4のロックを取り、取る前に現れたロックはplan_stale。
- 移行の再開は、「両方」ではPUBLISHEDだけ、「history.jsonだけ」ではPUBLISHEDかPUBLISHED_THEN_EXTENDEDで、どちらも退避先のMANIFESTのバイトの一致とsnapshot.jsonの識別値を確かめる（設計§5.2）。採用の再開は、publication_stale／rawのときだけreconcileと退避先の写しで完了を判定し、それ以外の拒否はそのまま返す（設計§5.3）。
- MANIFESTは8キーの正規化JSONで、操作のときは今書くはずのバイトとの完全一致、read_set_aside・inspectでは正規形の確認で読む。退避先の許す名前は、MANIFEST・その操作の名前・`.q.<32桁>.tmp`だけ。
- 子プロセスは5つ（依頼の「4つ以上」）、強制終了は子が一時停止の行を出してからの`kill`で、sleepに頼らない。ソケットは既存ヘルパーで無効。
- 範囲試験は`START = 6d69bd7`、`END = None`、`REV = END or "HEAD"`の形で、test_c3_09の1行を自分の差分のハンクとして固定している（C4-21、実装者の項目21の変異で20件が失敗）。

## 5. 推奨と次の作業

- **推奨：限定修正（N-01だけ）**。
  - 範囲：`v2_history_maintain/store.py`の`_migrate_resume`の2か所と、tests/v2_history_maintain/への試験の追加（FileNotFoundErrorの注入数件。C4-16の総当たりの例外の種類を増やすなら同じファイルで）。範囲試験のSTART（6d69bd7）とENDの扱い、test_c3_09の1行は変えない。
  - 確認：既存2,069＋新規（180＋追加分）を4版で、実装者の欠陥注入32件の再実行、本レビューの`c4i_probe.py`のX1と`c4i_sweep2.py double migrate strict os,fnf`。
  - 担当：小さな修正なので、C-4の実装と同じSonnet 5.5・highで足りる。修正後の確認は差分だけの再レビューでよい。
  - P-01（解錠の途中のplan_staleの語）は同じ機会に扱ってもよいが、任意。P-02〜P-04は受領記録・結果文書の注記で足りる。
- 受領した場合の残り（修正の有無に関わらず）：実Windowsでの実行は未実施（依頼書§6の新規N＋1593件。C-4のWindows専用の確認＝strictの拒否、rename・mkdir・ディレクトリ・ジャンクションの扱い（V12・V20の経路）、ロック・一時ファイル名の扱いを含む）。ユーザーPC、物理電源断、ネットワークドライブ・同期フォルダ上のrootも未実施。
- 範囲外のまま残るもの：設計レビュー74c93b1の提案P-01〜P-06（P-03・P-05は実装で満たされている）、C-3実装レビューのP-01・P-03、C-3設計レビューのP-01〜P-07、C-2実装レビューのP-02・P-03、C-1レビューのP-02・P-03、B-4§7.1の既知の制限、B-5b再レビューのP-01、範囲試験の固定のレビューのP-02。

## 6. 作業記録

- 保護参照：2026-11-04T06:35Z頃、依頼書§7の82参照＋docs/v2-history-maintain-c4-20261104（d11b875）＋feat/v2-history-maintain-c4-20261104（9b00efd）の84件を`git ls-remote`で照合し、全件一致。本記録のpush後にも照合する（結果はスレッドの報告に記す）。
- 変更したもの：本書と確認スクリプト・出力（`docs/reviews/v2_history_maintain_c4_impl_review_20261104/`）だけを、9b00efdから作った新しい資料ブランチdocs/v2-history-maintain-c4-impl-review-20261104に追加した。製品コード・実装ブランチ・既存試験・設定の変更、PR、マージ、Actions、送信、新しい市場計算は0。変異・模擬・故障の総当たりは使い捨てのクローン・作業ツリーの写し・一時ディレクトリで実行し、pushしていない。
- 確認スクリプト：`c4i_sweep2.py`は`python -B c4i_sweep2.py <クローン> kinds|double <場面> [保存水準] [2回目の例外]`、`c4i_probe.py`は`<クローン>`、`c4i_review_mutants.py`は`<クローン> <python> <作業場所>`。どれも実装者の試験ヘルパー（c4_helpers・test_c4_07のScenario）を読むだけで変えない。
- モデル別の利用量は未計測。
