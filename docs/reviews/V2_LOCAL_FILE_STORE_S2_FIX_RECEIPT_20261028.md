# V2 S2 限定修正の受領・完了確認

2026-10-28（日本時間）。主担当による差分レビューと実Windowsでの直接確認。
対象はローカル試験用のS2限定実装。本番保存先への採用、S3／S4、PR、切替の承認は含まない。

## 1. 固定した版と結論

| 用途 | 完全SHA |
|---|---|
| 修正基準 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| 修正依頼・再現コード | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| 修正コード・試験 | 163821a6e8a81d708f6c8cd6c9b026642d4a5a47 |
| 受領最終 | d404d4df481957f89201c5169f3a75d7b9d86b66 |

実装ブランチ：fix/v2-local-store-s2-review-20261028。
結果文書：[固定版§10](https://github.com/Rocky009-jp/soxl-alert/blob/d404d4df481957f89201c5169f3a75d7b9d86b66/docs/implementation/V2_LOCAL_FILE_STORE_S2_RESULT.md)。

**R-01・R-02の解消を確認した。新たな重大0件・通常0件。元のS2契約の限定範囲で実装完了として受領する。**
Linuxの全体確認は担当者報告として、実Windowsの下記9件は主担当の直接実行として区別する。Windowsの全機能・全Python版・全ファイルシステムを検証したとは扱わない。

## 2. 差分の確認

基準00e7f84から変更されたのは次の4ファイルだけ。

- v2_persistence/local/store.py：R-01のcleanup統合とR-02のロック分類。
- tests/v2_persistence_local/test_b11_review_fixes.py：新規13件。
- tests/v2_persistence_local/sensitivity_check.py：既存の新規S2補助へ2変異追加。
- docs/implementation/V2_LOCAL_FILE_STORE_S2_RESULT.md：§10追記と元記録2か所への訂正注記。

試験SHA163821aから最終d404d4dへの差分は結果文書だけ。既存コア、S1、既存197＋170件、基準データ、schema／CORE_SHA、依存・設定・workflowには差分なし。元のS2実装ブランチ、資料ブランチを上書きしていない。

## 3. 修正の評価

| ID | 実装と実測 | 判定 |
|---|---|---|
| R-01 | _lockedが新しいエラーを返す際に、元のLocalStoreErrorのcleanupを新しいロック用トークンと重複なく統合。実Windowsで「tmp書込失敗→tmp削除失敗→lock削除失敗」を再現し、code=store_io_error、field=lock、phase=lock_release、primary=store_io_error、cleanup=(tmp_left, lock_left)を確認。tmpとlockの残留、旧正本不変、次のreadがstore_busyになることも確認。 | 解消 |
| R-02 | 排他的作成失敗後、lstatでロックの存在を確認できる場合だけstore_busyへ分類。存在を確認できなければstore_io_errorを維持。実Windowsで既存のwrite.lockディレクトリに対するread／commitがstore_busyとなり、ディレクトリと正本が不変であることを直接確認。 | 解消 |

所有喪失時に他者のロックを消さないこと、replace呼出し後のuncertain優先、同日reconcileのALREADY_APPLIEDと古い計画のCAS拒否は、再現コードの対照試験でも維持された。

Q-01のWindows実行コマンド区別、Q-02のファイル数訂正は結果文書§10で反映済み。元の測定履歴を残した扱いも妥当。新たな修正依頼はない。

## 4. 主担当が直接行ったWindows確認

実Windows 11（10.0.26300）、Python 3.12.14（MSC 64bit）。
以前の確認用コピーから独立したフォルダを作り、今回の固定版の差分を取得した。実行対象のv2_core／v2_persistence／保存ドメイン試験／S2試験計45ファイルを、d404d4dのGit treeのblob SHAと照合し全て一致。再現コードは87f22f4の固定blobを照合した。Gitのクリーンクローンそのものではない。

全書込は明示した専用review-temp配下へ生成したテストrootだけ。TEMP／TMPも書込可能な専用フォルダへ設定。helperとworkerのプロセス内ソケット禁止を使用し、LinuxのunshareによるOSレベル通信遮断と同一条件とは扱わない。ファイルシステム種別は今回未計測。

| 実行 | 件数 | 結果 |
|---|---:|---|
| 87f22f4の再現コード --expect-fixed | 5 | 全合格、skip0、終了0 |
| test_b09_modes_os.RealWindows | 3 | 全合格、skip0、終了0 |
| test_b11_review_fixes.RealWindowsLockDirectory | 1 | 合格、skip0、終了0 |
| 計 | 9 | 失敗0・error0・skip0 |

Windows専用3件は、修正後コードに対してfile_sync_onlyの往復・既存正本への置換、strictの公開前拒否、独立プロセス競合の1勝を確認したもの。R-02のWindows固有の直接確認が残っていた点は、追加1件と再現コードで完了した。

再現可能なコマンド（資料側と実装側は別チェックアウトでよい）：

    <python> -B -W error::ResourceWarning <資料87f22f4>/docs/reviews/v2_s2_receipt_probe.py --repo-root <実装d404d4d> --scratch-root <専用一時フォルダ> --expect-fixed
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p test_b09_modes_os.py -k RealWindows -v
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_persistence_local -p test_b11_review_fixes.py -k RealWindowsLockDirectory -v

下2本は実装側のルートで実行する。Linuxのstrict前提試験を含む全探索をWindowsで実行して、非対応分を製品不具合へ数えることはしない。

## 5. 担当者のLinux結果として受領したもの

- Python 3.10.20／3.11.17／3.12.3／3.13.17の4版で既存367件（コア197＋S1保存170）が無編集で合格。
- S2は113件探索、109件合格、Windows専用4件はskipとして未実施。Windows4件の主担当実行を、担当者Linuxのskipを合格へ変更する形で混ぜない。
- 別クリーンクローン、core.autocrlf=false、unshare -rnによる通信遮断。
- 3.10と3.13でS2各10回の反復に失敗なし、欠陥注入29件検出。

これらは今回主担当が独立に再実行したものではない。モデルとeffortのセッション記録確認も担当者報告として受領した。Linux上のPermissionError注入を実Windowsの証拠へ置き換えていない。

## 6. 保留と次工程

以下はS2の完了判定と分けて引き継ぐ。

- 物理電源断は元のS2契約で試験しない対象であり、未試験のまま。COMMITTEDを全ハードウェアの電源断耐久保証へ拡張しない。
- Windowsの再解析ポイント全般、全Python版でのWindows全体試験は未確認。今回の9件をWindows全面対応の証明にしない。Windows strictは契約どおり未対応。
- core.autocrlf=true、ユーザーPCでの既存181件は後日。主担当Windows確認と本人PC確認を区別する。
- ローカル・信頼済み・非同期の専用rootという前提、残留ロック／tmpの自動解錠・昇格なしを維持。本番保存先・資格情報・実行場所の未決事項は残る。
- 次の作業候補はS3（明示的解錠・ACK・復元）の設計と限定依頼書作成。今回S3の設計・実装には着手しておらず、実装承認にも置き換えない。

## 7. 参照と変更したもの

依頼の13保護参照、資料73cec62、元S2実装00e7f84、受領レビュー87f22f4、計16参照をGitHub APIで確認し全て不変。修正ブランチの先頭もd404d4df481957f89201c5169f3a75d7b9d86b66と一致。

本受領記録は新規のdocs/v2-local-store-s2-fix-receipt-20261028へ保存するだけ。実装・元結果文書・保護参照は変更しない。PR、Actions、本番接続、通知・外部送信、口座、S3／S4操作なし。
