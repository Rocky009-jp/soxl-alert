# V2 S3-A 限定実装 受領レビュー（2026-10-29）

状態：**重大0・通常2・提案2。通常2件の限定修正を先に行い、S3-Bにはまだ進まない。**  
主担当によるコード読解・Windows実行。市場判定の変更提案ではない。ユーザーPCでの確認とは区別する。

## 1. 対象と根拠

| 項目 | 固定版・確認 |
|---|---|
| コード基準 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| 試験対象 | 3b71816f5d4fd08b0a065e3f92e189944ac604d5 |
| 保存最終 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2、feat/v2-recovery-resolution-s3a-20261029 |
| 設計・依頼書第3版 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| ユーザー採用記録 | d215193065ebf110e6a77f22edf208b390138285 |
| 結果文書 | docs/implementation/V2_RECOVERY_S3A_RESULT.md、blob c6d3fb3a565cff39c9016b70ba9b5f7182c91cd7 |
| 差分 | 開始点から新規25ファイルだけ。コード・試験24本＋結果文書1本。試験対象から保存最終は結果文書1本だけ |
| 読解対象 | v2_recoveryの全10ファイル、r_helpers、計画・宣言・参照・秘匿・範囲の試験と欠陥注入の該当箇所。必要な既存コア・S1・S2実装も確認 |
| 未取得 | 今回のレビューに必要なファイルはなし。ClaudeのLinux生ログ全体は受領しておらず、4版の数値は結果文書と報告に基づく |

設計第3版§7はrepr・エラーへURLや自由文を混ぜないこと、§7.1は固定code／field／ruleと安全な例外処理を要求する。依頼C-13の秘匿、C-14の限定範囲も判断根拠とした。

## 2. 結論

S3-Aの分割・委譲、S1／S2へ直接commitできない専用日次結果、ROW_REMOVED／CHANGED＋ADDEDの一括処理、version_selection、採用済みN-04はコード・既存試験と整合している。除外→必要時の補完→最終検査、作成時prefix、通常のセッション投影と計画確認用digestの区別も維持されている。今回、誤った市場判定や不正計画の確認成功は見つけていない。

ただし外部辞書から計画を復元する入口と、その未検証値の表示に通常2件がある。どちらもv2_recovery/plan.pyと新規回帰試験で限定して直せる。S3-Bへ渡す前にこの境界を固めることを推奨する。正常155件の合格だけでは、外部から来た不正計画に対するC-13全体の適合を主張できない。

## 3. 通常の指摘

| ID | 根拠 | 問題・影響 | 最小修正と受入 |
|---|---|---|---|
| R-01 未検証計画の表示が任意文字列を出す | v2_recovery/plan.py:57、95、104。from_dictは外側のキーとJSON型だけを確認し、summary／reprはstatus・request_id・日付等をそのまま出す | 正常計画のbasis.status、request_id、commands[0].dへ合成URLを入れてfrom_dictした値で、reprとsummaryの両方に同じURLが出た。basis={}ならsummaryはKeyError。確認はresolution_plan_mismatchで拒否されるが、確認前に表示・ログへ出すだけでC-13の秘匿と固定エラー境界を破る。実際の秘密情報の流出を観測したわけではない | 復元時の構造検査、または表示前の安全な検査で、未検証の文字列・入れ子を表示へ通さない。不正なら固定の伏字表示／固定PersistenceErrorとし、生のKeyError等を出さない。正常なsummaryの契約と確認時の再構築は維持。合成URL・自由文・欠落キーの回帰を追加 |
| R-02 計画復元がJSON変換・コピーのPython例外を漏らす | v2_recovery/plan.py:48-61。from_dictはcheck_jsonより前にdeepcopyし、_from_viewのcanonical_json／json.loadsに変換例外の処理がない | request_idへ10**5000を入れた辞書はPython 3.12.14の整数文字列変換制限でValueError。basisに1200段の辞書を入れるとcheck_jsonの深さ40の検査より前のdeepcopyでRecursionError。いずれも固定code／field／ruleがない。同じパッケージのResolutionSet.from_dictにはJSON変換例外の処理がある | JSON互換性・深さを危険なコピーより前に検査し、必要なコピー／シリアライズ例外を、例外連鎖を抑えた固定PersistenceError（field=plan、固定rule）へ変換する。整数変換制限・再帰制限をグローバルに緩めない。正常な計画のJSONとhashを変えない |

R-01/R-02は入力検査・表示の限定問題で、保存された状態の破壊や外部送信の実証ではない。実入力に秘密値を要求せず、再現は予約ドメインexample.invalidの合成文字列のみで行った。

## 4. 任意提案

| ID | 内容 |
|---|---|
| P-01 不正な保存時刻の分類 | common.py:65-72のis_requested_textはparse_aware_datetimeだけをtry内に置き、UTCへの変換は外にある。requested_atを0001-01-01T00:00:00+23:00にして計画hashを再計算すると、confirmはresolution_plan_mismatchでなくInputError(datetime_invalid, requested_at)。安全には停止するが、不正計画の分類と違う。述語内のUTC変換まで扱い、validate_resolutionsではresolution_invalid、confirmではresolution_plan_mismatchへそろえることを推奨。呼出側の新規requested_atのInputError契約とは分ける |
| P-02 M15の等価判定と独立したhash期待値 | sensitivity_check.pyのM15はrequest_hashの入力へt=1を追加している。request_hashは公開のbasis・記録・encode結果に残り、値が変わるので外から観測不能な等価変異ではない。現行の正常コードの式は設計どおりだが、作成と検査が同じ関数を使う試験だけではこの差が見えない。M15は現時点では「非等価・未検出」と整理し、独立した固定JSON／literal hashの少数ケースを追加する案。依頼がこの変異の検出を特に義務付けていたわけではない |

主担当は53件の欠陥注入を再実行していない。P-02は変異のコード読解と、元の式／t=1を加えた式のhashが異なることの計算確認による。報告値を暫定的に整理するなら検出49・等価3・非等価未検出1であり、新しい試験でM15を検出した後は再集計する。他の等価3件は今回の2件と混ぜない。

## 5. 主担当が実行した確認

Windows、Python **3.12.14**。試験対象3b71816f5d4fd08b0a065e3f92e189944ac604d5をcore.autocrlf=falseで新規clone・detached checkoutした。実行後git status --porcelainは空、HEADとautocrlfを読み返して一致。既存helperによるPython内のsocket遮断は有効。OSレベルの通信遮断は行っておらず、Claudeのunshare実行と区別する。

| 実行 | 件数 | 結果・所要秒 |
|---|---|---|
| tests/v2_core 全探索 | 197 | OK、10.698秒、exit 0 |
| tests/v2_persistence 全探索 | 170 | OK、25.424秒、exit 0 |
| S2 RealWindows | 3 | OK、2.092秒、exit 0 |
| S2 RealWindowsLockDirectory | 1 | OK、0.266秒、exit 0 |
| tests/v2_recovery 全探索 | 155 | OK、3.804秒、exit 0 |
| 合計 | **526** | 失敗0・error0・skip0。Linux向けS2全探索は実行していない |

コアのA1は465行のsoxx／rsi／sma／shd最大誤差0、exact_days=360、after_gap_days=103、unconfirmed_ex_or_normal=1、rearm_date=2026-04-13。上の試験は独立したPythonプロセスで並行実行したため、秒数を単独実行の性能基準にしない。

初回の155件探索では、初期化済みLocalFileStoreの試験がstore_io_error:lockで1errorとなった。この時点ではOSエラーの原文は取得しておらず、製品不具合の根拠と断定しない。TEMP／TMPに書込み可能な専用一時ディレクトリを明示した上の正式確認では155件すべて合格した。初回を合格扱いにしていない。

### 独立再現

[再現コード](V2_RECOVERY_S3A_REVIEW_REPRODUCE_20261029.py)を合成fixtureで実行した。実装コードは変更していない。

- R1_repr：任意URLをreprに表示。
- R1_summary：任意URLをsummaryに表示。
- R1_missing_keys：KeyError。
- R2_deep_input：RecursionError。
- R2_numeric_serialization：ValueError（Pythonの整数文字列変換制限が有効な環境）。
- 対照：無改変の正常計画はCONFIRMED_IN_MEMORY、committed=False。
- 通常モードは5件の欠陥観測が期待と一致しexit 0。--expect-fixedは未解消5件のためexit 1。これは追加の回帰試験5件が合格したという意味ではない。

実行例：

    python -B docs/reviews/V2_RECOVERY_S3A_REVIEW_REPRODUCE_20261029.py --repo <固定SHAのcheckout>
    python -B docs/reviews/V2_RECOVERY_S3A_REVIEW_REPRODUCE_20261029.py --repo <修正checkout> --expect-fixed

## 6. 未実施と証拠の区別

ClaudeのLinux4版の367／109／155件は受領報告として保持し、主担当のWindows結果と混ぜない。ユーザーPCでのS3-A155件、主担当による他のPython版・Linux再実行、53件の欠陥注入の再実行、autocrlf=true、物理電源断・実ファイル復旧・本番通知は未実施。今回のWindows526件はユーザー自身のPCの実測ではない。

## 7. 次の最小作業

[限定修正依頼](../tasks/V2_RECOVERY_S3A_REVIEW_FIX_REQUEST.md)に従い、Sonnet 5.5・highでR-01/R-02を同じS3-Aの承認範囲内で修正し、新規回帰・既存不変を確認する。P-01/P-02は任意で、取り込んだ場合は変更と件数を明記する。修正結果の確認後に、S3-Bの設計・限定依頼書を具体化するかを判断する。S3-Bの実装・新保存形式・本番は本レビューから承認しない。

## 8. 変更と参照

レビュー側の追加は本書・再現コード・限定修正依頼の3本だけ。元実装ブランチ、既存コード・試験・資料は変更していない。依頼の19参照＋設計／採用の資料2参照＋今回の実装1参照＝22参照を保存前に完全SHAで照合し、すべて一致。保存後も同じ22参照を照合する。PR・Actions・送信・S3-B/C・新市場計算は行っていない。
