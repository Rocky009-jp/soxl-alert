# V2 S3-B-3 限定実装 レビュー・受領記録

作成日：2026-11-02（日本時間）。レビュー担当：ChatGPT / Codex。
結論：**重大0・通常0・提案1。B-3の候補Historyまでの限定実装として受領可能。**
B-4以降・S3-C・保存・本番の承認を意味しない。既存コードの修正は行っていない。

## 1. 対象と根拠

| 区分 | 固定値 |
|---|---|
| 実装ブランチ | feat/v2-history-restart-s3b3-20261102 |
| コード開始点 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| 実際に試験したSHA | **7d75ea5dbee1f6cef9912fceced2c2be2e48fad9** |
| 結果文書を含む最終SHA | **d82a5ced64658c2e736b82b1a2f1925636055417** |
| 設計・依頼第2版 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| 設計blob | 48afb2ebb0c4be2147b2e06d751ba32630f6b681 |
| 依頼blob | 437e10dbcff36043cb377e0a8f9796b62c63e9c0 |
| 結果文書blob | 458859e0e66381dde9275732c9d8181e4cc76a7c |

参照：上記第2版の設計・依頼書、最終結果文書、v2_history_restart全6ファイル、新規試験7ファイルとr3_helpers、既存のHistory・公開検査器・read_effective・project_history_ledger・台帳解析とdigest、旧範囲試験の差分。CLAUDE.md、STATUS、MODEL_POLICY、ROADMAPの関連箇所も確認した。古いSTATUSの承認待ち表記を、既に進行した各段階の採用を取り消すものとは扱わない。

試験対象を別のcore.autocrlf=falseクローンに取得し、HEADを固定した。AGENTS.mdはこのクローンと作業ルートでは見つからなかった。7d75ea5からd82a5ceの差分は結果文書の新規1本だけであり、コード・試験は同じ。

## 2. 設計との照合

| 論点 | 確認した内容 |
|---|---|
| 変更範囲 | b328844からコード版は16ファイル、+2332/-5。既存ファイルの変更はtests/v2_history_ops/test_b17_scope.pyだけ。新パッケージ6本、新規試験・補助9本。結果版は結果文書1本がさらに増える |
| 旧範囲試験 | 許可パス追加、新規試験の除外、v2_history_restart/__init__.py単一パス例外の3点。既存機能試験や期待値の変更なし。新規範囲試験の厳密差分照合も合格 |
| 準備の順序 | 入力履歴・sessions・日付・行解析、対象セッション、時刻・ID、floor、元履歴投影、候補検査の順。旧文脈差はID照合より後という第2版の優先順位と一致 |
| floor | 有効履歴全区間のAPPLY・宣言と現在境界。退避記録を下限に入れない。下限・上限・無効果の指定ミスはrestart_invalid |
| 元履歴の照合 | 変更しないproject_history_ledgerに委譲。台帳不一致・後発・版の衝突を再開始で消さない |
| 候補 | 物理先頭に15キーのRESTART_UNKNOWNを1件追加。過去eventsの一致、有効/退避列、境界、初期状態、移行情報・既存事実の保存とvalidate_historyを確認 |
| 等号 | resume_after==check_dの準備・確認・再確認が成功。候補を同じcheck_dへ投影して架空の未来セッションで代用しない |
| ID | 物理履歴全体を照合し、prepareで既存IDを一律拒否。同内容や退避だけのIDにも例外を作らない |
| 確認 | 計画→入力そのもの→digest/head→元basisの再構築。枝Bでは物理prefixを検査し、元digest/head/stateとbasis全体を照合。同じ候補ならNO_CHANGE、候補より先へ進んでいればstale |
| 値と境界 | from_dictのJSON事前検査・安全な計画表示・アクセサの写しを確認。通常の確認結果にはbatch/ledgerがなく、committed/committable=False。旧ストアはplan_typeで拒否 |
| 日次・解決との接続 | 新しいB-2日次計算は境界より後からUNKNOWNで開始。等号再開始直後には同じcheck_dでACK/DECLAREを作れず、後の確定check_dが必要 |

実装者が選んだ内部不整合のhistory_invalid / history / rule=restart_candidateは、指定ミスのrestart_invalidと区別され、候補の不変検査に限って使われている。既存validate_historyのエラーを上書きするものではなく、今回の設計の分類と整合すると判断する。新しいユーザー判断を必須としない。

## 3. 指摘

重大：なし。通常：なし。

| ID | 種別 | 根拠・影響・推奨 |
|---|---|---|
| P-01 | 任意の提案 | v2_history_restart/values.pyのRestartConfirmResult.__init__は入力をそのまま保持し、status/history/plan_hashは直接返す。通常のconfirm_restart_planは固定status、不変History、検査済み文字列hashだけを渡すため、この経路の不変性や表示に問題はない。一方、この公開型を利用者が直接、不正なdict/listのhashや任意statusで構築すると参照共有や任意statusのrepr表示が可能。直接構築を信頼済み内部入力に限る旨をdocstringに明記することを推奨する。外部入力の構築口として使う必要が出た場合は、型・固定statusの検査などを別の限定範囲で決める。今回は正常な確認APIの不具合とは数えず、受領の必須修正にしない |

P-01は合成値だけで再現した。正常な確認結果が後から改変できた、計画の確認が迂回できた、または保存内容が変わったという観測ではない。全戻り値が「任意の不正な型による直接構築まで」保証される、と拡張して説明しない。

## 4. このレビューで実行した試験

実OS：Windows。Python：**3.12.14**。core.autocrlf=false、別クローン、HEAD=7d75ea5。-Bと-W error::ResourceWarningを指定。
スイートのヘルパーによるプロセス内socket禁止がある。LinuxのunshareやOSレベルの通信遮断と同等には扱わない。ユーザーPCでの実行でもない。

| スイート | 実行件数 | 結果 | 時間 |
|---|---:|---|---:|
| tests/v2_history_restart（test_r3_*.py） | 109 | OK | 15.578秒 |
| tests/v2_history_ops | 173 | OK | 20.936秒 |
| tests/v2_recovery | 176 | OK | 2.930秒 |
| tests/v2_history | 230 | OK | 17.351秒 |
| test_b09_modes_os.py / RealWindows | 3 | OK | 1.162秒 |
| test_b11_review_fixes.py / RealWindowsLockDirectory | 1 | OK | 0.076秒 |
| **合計** | **692** | **failure 0、error 0、skip 0** | |

Windowsでは依頼書指定の範囲を実行し、Linux strict前提のS2全探索はしていない。

コマンド例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restart -p "test_r3_*.py" -v
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_ops -p "test_*.py"
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_recovery -p "test_*.py"
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history -p "test_*.py"
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p test_b09_modes_os.py -k RealWindows -v
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p test_b11_review_fixes.py -k RealWindowsLockDirectory -v

同梱s3b3_review_probe.pyによる独立した追加確認：

- 正常候補、等号再確認、既存ID拒否、floor拒否、prefix不一致、先へ進んだ履歴のstale、不正sessions、同日投影拒否、元台帳削除の停止：**9/9**。
- basis20項目それぞれを9種類のJSON値へ置換し、hashを再計算した計画：**180ケースすべてCoreErrorによる拒否**。生のTypeError/KeyError等は観測なし。全てのJSONや型を網羅する証明ではない。
- P-01の直接構築だけの観測を別掲。正常経路の9件と混同しない。
- 追加確認のプロセス終了コード0。これらをunittestの692件へ加算しない。

実行例：

    <python> -B docs/reviews/s3b3_review_probe.py --repo <7d75ea5のクローン>

## 5. 実装者の報告と未実施の区別

実装者はLinuxのPython 3.10.20/3.11.18/3.12.3/3.13.18と、3.13.18の別通信構成について35実行の成功を報告している。既存1059件は1055合格+Windows専用4 skip、新規109件は全合格。これは実装者の記録として受領したもので、このレビューの実行には数えない。

欠陥注入18項目・34変異、全検出という結果も実装者の記録であり、このレビューでは34変異を再実行していない。M17bは結果の値では区別できず、再構築前の照合という呼出し順序をspyで確認するものだと本文に区別されている。これを誤った候補の受理を防いだ実験と読み替えない。

このレビューで未実施：コア197・保存ドメイン170の再実行、Linux、Python 3.10/3.11/3.13、全34変異の再実行、物理電源断、autocrlf=true、ユーザーPC、実ファイルへのschema2履歴公開、S3-C、本番・通知。Windows確認をLinuxでの耐久性や物理電源断の証明にはしない。

## 6. 保護参照と変更したもの

依頼書§7の45参照と第2版資料ブランチd0e11d9の計46参照をリモートの完全SHAと照合し、開始時46/46一致。実装ブランチもd82a5ced64658c2e736b82b1a2f1925636055417で一致。計47参照を今回の読取専用対象とする。保存後の再照合結果は完了報告で示す。

今回の変更は、新しいレビュー資料ブランチへの本書と再現用の追加確認スクリプトだけ。実装ブランチ、既存コード、試験、設定、依存、workflowを変更していない。試験クローンは完了時も作業ツリー差分0。
PR・マージ・Actions・本番接続・通知は行っていない。

## 7. 判断と次の最小作業

B-3の候補Historyまでの範囲では必須修正はない。P-01は任意の補足として残し、全段階のコードをまとめて不変化する作業へ広げない。
次はユーザーの指示に応じてB-4の設計・限定依頼書作成を検討できる。**今回のレビューはB-4の実装やS3-Cへの移行を承認しない。**
