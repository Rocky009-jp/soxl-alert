# V2 S3-B-5a 限定実装レビュー

作成日：2026-11-02（日本時間）。担当：ChatGPT / Codex。
**重大0・通常0・提案1。B-5aの今回の限定実装は受領可能。**
B-5bの設計の具体化・限定実装依頼書作成へ進むことを推奨する。B-5b実装、CONSUME、S3-C、本番の承認を意味しない。

## 1. 固定対象・差分

| 項目 | 固定値 |
|---|---|
| 実装ブランチ | feat/v2-history-diagnose-s3b5a-20261102 |
| コード開始点 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| 試験したコード | **fac880c40e235a849e36269cee99985a5183f5ae** |
| 結果文書つき最終 | **c8ba08f15ea28248a9fe7924f32ce136fc16d5e6** |
| 固定資料第2版 | **5c9e1e89c8f9d33689e9bc67e266fa6031507136** |
| 設計blob / 依頼blob | f4d4225545627dd5e7df1fc5c5e092a49ccee10f / 2e4bb7e34f9c442450fe11ac179e4f134b97cb29 |
| 結果文書blob | c12c9c7059ecd3d4cadb9a6b9364dc887aa806eb |

開始点→試験対象は18ファイル（追加15・変更3、+2838/-33）。新規ランタイム5本365行、新規試験10本、変更は旧scope3本だけ。
試験対象→最終はdocs/implementation/V2_RECOVERY_S3B5_RESULT.mdの追加1本（342行）だけ。既存ランタイム・機能試験・fixtures・依存・設定・workflowは変わっていない。

固定設計/依頼、結果文書、ランタイム5本の全文、新規試験・ヘルパー・感度スクリプト、scope3本の差分と新scopeの固定差分/AST検査を読解した。既存History/Snapshotの読込み・検査器・移行ビルダーとの関係を突き合わせた。共通CLAUDE/STATUS/MODEL_POLICY等は前回読解済みの同じ固定内容で、今回も変更なし。試験クローンにAGENTS.mdは検出しなかった。

モデル設定Sonnet5.5/highとLinux4版の試験は実装担当の報告として受領した。こちらが実装担当のセッション設定を独立に閲覧できたとは扱わない。

## 2. 機能と依頼境界

| 論点 | 確認 |
|---|---|
| 公開範囲 | 1関数・1型・4定数の6名。新規パッケージだけで既存への再公開なし |
| 読込み | 厳密bytes、strict UTF-8、BOMを除かず、既存decode_historyへ委譲。構文・重複キー・非有限数・深さ等の拒否を維持 |
| 版とcore_sha | schema 1/2の厳密整数、CORE_SHA一致を先に検査。違えばUNREADABLE、prefixなし |
| 全体検査とprefix | 版に応じた既存検査器。全体が通らなければnから1の順でヘッダーを再計算して検査。最初に通った最大kを採り、k=nでもPREFIX_ONLY |
| failure | 全体で最初の失敗を保持。prefix中の例外で上書きせず、文面/連鎖を出さない。既存CoreError/PersistenceErrorの識別子を固定形式へ |
| 説明値 | claimedとverifiedを分離。discardedは5項目の投影で、未知のkindは?、不正な日付/ID/seqはnull。空eventsと非listを第2版の規則どおり区別 |
| v1 | 自分の検査器だけを使い、migrated=null。採用の経路は作っていない |
| 不変性 | 読取りをコピーし、元バイト・Historyを診断値へ保持しない。直接構築は信頼済み内部入力というdocstringと結果文書の限定を確認 |
| 保存との境界 | Historyを返さず、ストア・ファイル・時計・ネット・通知・台帳照合なし。既存ストアは診断値をplan_typeで拒否 |
| 旧scope | b17/r3_07/r4_09の指定された場所だけ。新scopeがac21980起点の変更と静的差分を検査し、今回の実行でも合格 |

設計§11の移行例は、example_mのcount=2/head_seq=1/捨てる側6件、example_m_empty_worldのcount=3/head_seq=2/捨てる側1件と一致。migrated=Falseのprefixを採用可能とは表示しない。
破損ファイルを「修復」したり、寛容なJSON救出・CONSUME・採用記録を作ったりする経路は見つからなかった。

結果文書§9の「schema段階で停止した診断のschema_versionはnull、読めた版はclaimedへ」は、検査に使った版という設計の意味に沿う解釈。識別子のASCII/長さ検査は任意の文面の安全性を証明するものではないが、現在の固定検査器の識別子を扱う範囲にあり、追加の外部例外プロバイダーを認める設計ではない。

## 3. このレビューのWindows実行

環境：実Windows11、Python **3.12.14**、core.autocrlf=falseの新しいクローン、HEAD=fac880c。-B -W error::ResourceWarning。
ヘルパーのプロセス内socket禁止はあるが、Linux unshareやOSレベルのネット遮断と同一視しない。ユーザーPCではない。

| スイート | 件数 | 秒 | 結果 |
|---|---:|---:|---|
| B-5a tests/v2_history_diagnose/test_d5_*.py | 131 | 296.377 | OK |
| B-4 tests/v2_history_restore/test_r4_*.py | 165 | 30.395 | OK |
| B-3 tests/v2_history_restart/test_r3_*.py | 109 | 12.022 | OK |
| B-2 tests/v2_history_ops | 173 | 19.264 | OK |
| S3-A tests/v2_recovery | 176 | 2.604 | OK |
| B-1 tests/v2_history | 230 | 19.127 | OK |
| S2 RealWindows | 3 | 1.195 | OK |
| S2 RealWindowsLockDirectory | 1 | 0.095 | OK |
| **合計** | **988** | | **failure/error/skip0、全実行終了0** |

旧scope39件はそれぞれのスイートに含む（別加算しない）。B-5aの131件には性能試験2件とGit scope検査も含む。
S2はWindows専用4件を実行し、Linux strict前提を含む全113件のWindows探索は行っていない。コア197/保存170は今回の再実行対象に含めていない。

D5-16の指定した合成履歴（GENESIS＋APPLY260件、519622 bytes）でのWindows実測：

| 入力 | 秒 |
|---|---:|
| 正常 | 0.334 |
| 末尾のevent_hash破損 | 0.459 |
| ヘッダーだけ違う | 0.417 |
| GENESIS直後のevent_hash破損 | 8.902 |
| GENESIS破損 | 8.706 |

スイート全体296秒は履歴の構築やGit監査も含む。診断1回が296秒という意味ではない。上の値はこの環境・合成入力の実測であり、期限保証や全入力の最大時間とはしない。打ち切りは追加していない。

## 4. 追加の読取り専用プローブ

同梱docs/reviews/s3b5a_review_probe.pyを固定fac880cに対して実行し、終了0。

- GENESIS＋APPLY2件の文書を版1/2で用意し、ヘッダー各キーと各記録のキーを、null・bool・負整数・小数・空文字・URL・孤立サロゲート・list/dict等へ1項目ずつ置換。正常対照を含む**938ケース**。
- すべて診断値を返し、to_dict/repr/summaryが例外にならず、URLのcanaryが出ないことを確認。
- 同じ入力の決定性、raw_size/raw_sha256、診断digestを独立に照合。
- PREFIX_ONLY/NO_VALID_PREFIXでは、B-5aの内部関数を使わず、既存検査器で全kを下から列挙して求めた最大値と一致。VALIDの場合は元文書がその版の検査器に通ることを確認。
- status内訳：VALID14、PREFIX_ONLY644、NO_VALID_PREFIX228、UNREADABLE52。
- 上の移行破損2例を、診断APIで再確認。
- 小さい履歴のGENESIS直後の破損で、実際に呼ばれるvalidate_historyの名前へspyを置き、検査件数列[3,3,2,1]（全体1回＋prefix3回）を確認。

この938ケースは有限の合成格子で、あらゆるバイト列に対する形式的な証明や実運用事故の再現ではない。標準unittestの件数へ加算しない。

実行例：

    <python> -B -W error::ResourceWarning docs/reviews/s3b5a_review_probe.py --repo <fac880cのクローン>

## 5. 任意の提案 P-01

結果文書§7の「GENESIS直後を壊した最悪位置（count=1、検査260回）」は、**260回は失敗するprefix検査だけ**と書くと正確。

n=261では、prefixのkは261〜1の**261回**（うち260回失敗、k=1の1回成功）。その前に全体検査1回があるため、validate_historyの呼出しは**合計262回**。小さいn=3のspyでも全体3件→prefix3件→2件→1件の4呼出しを確認した。

実装と診断結果の不具合ではなく、表記上の補足である。受領を止めず、次の結果文書追記時に訂正すればよい。新しい製品コード変更や試験追加は要求しない。

## 6. 未実施と次の最小作業

このレビューでは、実装担当のLinux4版・新規131件＋旧1333件・53変異の全件実行は**報告として受領**し、こちらの実行結果へ置き換えない。53変異のスクリプトと結果の対応は読解したが、全変異を再実行してはいない。

今回未実施：Linux・Python3.10/3.11/3.13、コア197/保存170の再実行、S2全113件、全53変異、ユーザーPC、物理電源断、autocrlf=true、B-5b・CONSUME・S3-C・公開/退避/耐久性・通知/本番。
これらを988件の合格で解除しない。

重大・通常の修正依頼はない。次は、採用済みのB-5b境界をもとに、検査器への採用記録追加・計画/確認・既存機能試験の変更を具体化した設計と限定依頼書を作成することを推奨する。実装承認は別に行う。

## 7. 保存と保護参照

依頼の57参照（固定資料を含む）に再レビュー資料6a7210cと今回の実装c8ba08fを加えた**59参照**を開始時に完全SHAで照合し、59/59一致。保存後も同じ固定値で照合する。
新しいdocs/v2-history-s3b5a-review-20261102に本書とレビュー用プローブだけを保存し、既存の資料・実装ブランチを更新しない。

試験クローンはHEAD=fac880c、core.autocrlf=false、作業ツリー差分0を確認。製品コードの変更・PR・マージ・Actions・B-5b実装・CONSUME・S3-C・本番・通知は行っていない。
