# V2 ユーザーPC試験の受領記録

2026-10-28（日本時間）。ユーザーが本チャットへ提示したPowerShell出力・Pythonの版・git rev-parse HEADを根拠として記録する。主担当がユーザーPCを遠隔操作して実行した試験ではない。

## 1. 結論

**後日対応だったb616b4eの181件確認は完了。S2修正後d404d4dについても、指定したユーザーPC確認371件がすべて合格した。**

環境はユーザーのWindows PC、Python 3.10.6。今回の実行結果は、ClaudeのLinux試験および主担当の別Windows環境（Python 3.12.14）での確認と別の記録とする。

この記録により、[S2完了受領の保留表](https://github.com/Rocky009-jp/soxl-alert/blob/1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a/docs/reviews/V2_LOCAL_FILE_STORE_S2_FIX_RECEIPT_20261028.md)にあった「ユーザーPCでの既存181件は後日」を解消する。旧文書は当時の履歴として変更しない。

## 2. 旧固定版の確認

対象：b616b4ec7169420e199ec7e247dd375b3603a013。

ユーザーから次を受領した。

- py --versionの結果：Python 3.10.6。
- git rev-parse HEADの結果：上記完全SHAと一致。
- tests/v2_coreの探索結果：Ran 181 tests in 3.311s、OK。
- A1のCSV465行との最大絶対誤差：soxx、rsi、sma、shdの全項目で0.0。

判定：当時の指定固定版に対するユーザーPCの181件合格として確定。複数回貼り付けられた同一の181件ログは一つの結果として扱う。

## 3. S2修正後の確認

対象：d404d4df481957f89201c5169f3a75d7b9d86b66。
最後に受領したgit rev-parse HEADの出力が上記完全SHAと一致。

| 実行対象 | 件数 | 表示時間 | 受領した結果 |
|---|---:|---:|---|
| tests/v2_core | 197 | 3.393s | OK |
| tests/v2_persistence | 170 | 9.500s | OK |
| test_b09_modes_os.RealWindows | 3 | 0.444s | 3件ともok、末尾OK |
| test_b11_review_fixes.RealWindowsLockDirectory | 1 | 0.042s | ok、末尾OK |
| 計 | **371** | 別実行のため合計時間は算出しない | **全件合格** |

197件の実行でもA1のCSV465行とのsoxx／rsi／sma／shd最大絶対誤差は全て0.0と表示された。

Windows専用3件は、file_sync_onlyの往復と既存正本への置換、実プロセス競合の1勝、Windows strictの公開前拒否。追加1件は既存のwrite.lockディレクトリがstore_busyとなり、正本・ディレクトリが不変であることを確認するもの。ユーザーの出力に4件の試験名と個別のokが含まれている。

旧版181件と最新版371件は版ごとの別集計であり、コア試験の重複を含む。

## 4. 案内した実行方法と証拠の範囲

別フォルダへのgit clone -c core.autocrlf=false、完全SHAでのdetached checkoutを案内した。実行した試験コマンドは次のとおり。

    py -B -m unittest discover -s tests/v2_core -p "test_*.py"
    py -B -m unittest discover -s tests/v2_persistence -p "test_*.py"
    py -B -m unittest discover -s tests/v2_persistence_local -p test_b09_modes_os.py -k RealWindows -v
    py -B -m unittest discover -s tests/v2_persistence_local -p test_b11_review_fixes.py -k RealWindowsLockDirectory -v

受領したのはチャット上の試験出力・Python版・SHA。ログファイル全体、git status、設定値の再読取、個別の終了コード値、OS詳細・ファイルシステム種別は受領していない。通信遮断の実施もユーザーPCについては確認していない。案内した設定やClaudeのLinux環境の条件を、ユーザーPCで独立に実測した事実へ置き換えない。

## 5. 残る保留と次工程

- core.autocrlf=true、物理電源断、Windowsの再解析ポイント全般、全Python版・全ファイルシステムのWindows確認は未実施／未確認のまま。
- S2全113件はLinuxのstrict前提試験等を含む。今回ユーザーPCで確認したのは既存367件とWindows専用4件であり、Windowsで全113件を合格したとは扱わない。
- 87f22f4の再現コード5件は以前の主担当Windows環境で合格済み。今回はユーザーPCへ追加実行を依頼していない。
- ローカル保存を本番正本へ採用する判断、資格情報・実行場所・台帳・通知の接続は別工程。
- 次の候補はS3（明示的解錠・ACK・復元）の設計と限定依頼書作成。本記録の保存はS3の設計・実装への着手や本番切替の承認を意味しない。

## 6. 保存範囲

S2完了受領1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5aを基点に、新規資料ブランチdocs/v2-user-pc-tests-20261028へ本ファイル1本だけを追加する。実装・試験・旧結果文書・main・workflow・通知設定は変更しない。PR、本番接続、Actions起動、通知送信なし。
