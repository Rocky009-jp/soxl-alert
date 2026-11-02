# V2 S3-B-4 限定修正 再レビュー

作成日：2026-11-02（日本時間）。担当：ChatGPT / Codex。対象はR-01〜R-03の限定修正。
**前回の通常3件はすべて解消。新しい重大0・通常0・提案0。**
B-4の今回の限定修正は受領可能と判断する。B-5の設計・限定依頼書作成へ進むかは次のユーザー判断とし、本レビューで実装や本番接続を承認しない。

## 1. 固定対象と範囲

| 項目 | 完全SHA・内容 |
|---|---|
| 修正開始 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| 修正の試験対象 | **00ae4b6a69e358fd868ce1f2e9b24b14519b507e** |
| 結果文書つき最終 | **ac219801d290ebb59b720f37a086103b6e1251c9** |
| 修正ブランチ | fix/v2-history-restore-plan-s3b4-review-20261102 |
| 前回レビュー・修正依頼 | 814b86190562475286300d7e6df3a749a9140331 |
| 固定設計・依頼 | 0108131045d904b0997299fcade5929567940d6d |
| 比較に使った修正前コード | 47eb7c5c8c42acc8e218b3b891ce1b6a02e5a664（5eede11とランタイム・試験は同じ） |

修正前→試験対象は**6ファイル、+401/-21**。v2_history_restoreのbuild.py/records.py/confirm.py/values.py、r4_sensitivity.py、新規test_r4_10_review_fixes.pyのみ。
試験対象→最終はdocs/implementation/V2_RECOVERY_S3B4_RESULT.mdの追記だけ（+63/-0）。旧144件の試験本体、既存scope2本、v2_core・既存パッケージ・fixtures・依存・設定・workflowに追加差分はない。変更は限定依頼の範囲内。

固定版のCLAUDE.md、STATUS.md、MODEL_POLICY.md、ROADMAP.mdの関連部分、前回レビュー・限定依頼、修正差分全文、関連する確認/組立て/入力変換、結果文書§10、新回帰21件と感度スクリプト差分を確認した。試験クローン内でAGENTS.mdは検出しなかった。STATUSの旧記述を今回の未承認扱いへ置き換える根拠にはせず、ユーザーの工程指示と固定依頼を優先した。

## 2. 指摘ごとの確認

| ID | 判定 | 実装と実行による根拠 |
|---|---|---|
| R-01 最終参照と差の表示 | **解消** | _chain_afterの直後にsettle_changesを実行。最終ACKと直接の元記録をapplied_ref/missing_ref/state_afterだけで比較する。保持参照2例はstate_afterだけ。再適用したAPPLYへの参照が変わる対照はapplied_refも変更として残る |
| R-02 plan固有の構造を入力より先に検査 | **解消** | change_ok/series_item_ok、非負の厳密整数、_reapply_oldsの先行呼出しを確認。元履歴への確認Aと候補への再確認Bの両方で、悪いplan＋sessions=Noneはhistory_plan_mismatch/plan。正しいplan＋不正入力は入力固有エラーを維持 |
| R-03 4つの旧等価判定と設計説明 | **解消** | 4反例が新回帰に固定され、公開された単一変異をメモリ上で各1件適用した独立再現でも区別できた。「DROPなし、かつ全REAPPLYがsame=true」の厳密条件は維持。DROPなしでカレンダー追加によりsame=falseとなる例は準備・確認A・再確認Bまで成功 |
| P-01 M16aの理由の範囲 | **対応済み** | 生成器を変更しない単一変異という範囲、分離入力未発見・等価の証明ではないことを追記。元prefix照合を削除していない。M16a非等価を今回証明したとも扱わない |

R-01の処理は表示用changesだけを変え、候補記録の内容・連結hashへ影響しない位置にある。下記3例を**修正前47eb7c5と修正後00ae4b6の別プロセスで実際に生成**し、candidate_digestが一致することを確認した。単に新試験の固定期待値を信頼したという確認ではない。

| ケース | 修正前後で一致したcandidate_digest |
|---|---|
| 保持applied_ref | 79fec80154f21c9470b7238d8b4e5f7637ee620ee89c7474eb773ed2d083cd6e |
| 保持missing_ref | eda9b04e5475a4295c835e7e4ea2536b3a3f0a559459c08e63f59e87f65c5cba |
| 新seqへ写像する参照 | cfa1d1e3ff39eec7837a1d84005aa5b379aef69d12c9249f1e6f156bf106f917 |

changesを訂正した計画ではplan_hashは変わり得る。候補Historyが変わることと混同しない。

## 3. この再レビューで実行した試験

環境：**実Windows 11（10.0.26300）、Python3.12.14**、core.autocrlf=falseの新規クローン、HEAD=00ae4b6。-B、-W error::ResourceWarning。プロセス内socket禁止を持つヘルパーを利用しているが、OSネットワーク遮断やLinux unshareと同一視しない。ユーザーPCでの確認ではない。

| スイート | 件数 | 結果 | 秒 |
|---|---:|---|---:|
| B-4 tests/v2_history_restore/test_r4_*.py | 165（旧144＋新21） | OK | 32.808 |
| B-3 tests/v2_history_restart/test_r3_*.py | 109 | OK | 11.977 |
| B-2 tests/v2_history_ops | 173 | OK | 18.890 |
| S3-A tests/v2_recovery | 176 | OK | 2.880 |
| B-1 tests/v2_history | 230 | OK | 15.494 |
| S2 RealWindows | 3 | OK | 1.110 |
| S2 RealWindowsLockDirectory | 1 | OK | 0.077 |
| **合計** | **857** | **失敗0・error0・skip0、全実行終了0** | |

S2のWindows4件にはfile_sync_onlyの往復/既存ファイル置換、独立プロセス競合、strictの公開前拒否、既存ロックディレクトリのstore_busyと不変性が含まれる。Linux strict前提を含むS2全113件のWindows全探索は行っていない。

基本コマンド：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restore -p "test_r4_*.py"

B-3はtest_r3_*.py、B-2/S3-A/B-1は各ディレクトリのunittest discover。S2はtest_b09_modes_os.pyの-k RealWindows（3件）とtest_b11_review_fixes.pyの-k RealWindowsLockDirectory（1件）。元コード/既存試験への変更なし。

## 4. 独立再現・単一変異

前回保存済みのdocs/reviews/s3b4_review_reproduce.py（814b861版と同内容）を読み取り専用で次のように実行した。

    <python> -B -W error::ResourceWarning <再現スクリプト> --repo <00ae4b6のクローン> --expect-fixed --mutations

**終了0、runtime observations=10、unresolved=0**。
R-01は保持applied_ref/missing_refの2観測、R-02は不正changes3形×確認A/Bと負from_seq×確認A/Bの8観測。正常な確認A・再確認Bも成功した。

| 単一変異 | 正常コード | 同じ公開置換を1件だけ適用した結果 |
|---|---|---|
| M09c | restore_requires_consume | late_observation |
| M12b | READY、新frontier=D0 | history_invalid/history/declare_frontier |
| M16d | history_plan_mismatch/plan | sessions_invalid/sessions |
| M17c | READY、same=false | restore_no_effect |

4件ともDISTINGUISHED。M17cの正常対照はDROPなし、changed_fields=[input_hash, skipped_sessions]で、確認A=CONFIRMED_IN_MEMORY、再確認B=NO_CHANGE。カレンダーの追加/欠落は合成入力であり、実市場の改訂例という主張ではない。

新21件は、保持参照と写像参照、候補digest、changesの不正形、series_inputsの不正形、負値/bool/範囲外seq、REAPPLYの非APPLY参照、正しいplanの入力固有エラー、4つの反例と無効果の対照に対応する。読み取りでも各期待値と修正箇所の対応を確認した。

実装担当の「旧61変異を全件再実行し60検出・M16a1件」「修正を戻す10変異すべて検出」は**受領報告**として扱う。本再レビューで71変異すべてを再実行したわけではない。独立実行したのは上表4単一変異と再現スクリプト・標準857件であり、他者の結果を加算しない。M16aについて新しい証明や非等価の反例はない。

## 5. 結果文書と残る境界

結果文書§10で、旧4件の等価判断の誤り、旧144件は検出していないこと、新回帰で検出すること、旧§1〜§9を過去の記録として残すことを明示している。主担当の「DROPなしなら必ず同じ」という説明の誤りも撤回済みで、実装の厳密なAND条件は変更されていない。

次を今回の合格で解除しない。

- 案aの既知の保守的な拒否（宣言＋後のLATE ACK、ROW_REMOVED＋後のCHANGED ACK等）。
- CONSUME保留、復元計画・確認から候補Historyまで。実ファイル保存・バッチ統合・公開後の照合は未実装。
- ユーザーPC、物理電源断、autocrlf=trueは今回未実施。
- 本再レビューのLinux・Python3.10/3.11/3.13、コア197/保存ドメイン170、全71変異の再実行は未実施。実装担当のLinux40実行と区別する。

新しい重大・通常の指摘はない。追加修正や全面再レビューを先行させず、次はB-5の設計・限定実装依頼書作成へ進むかを判断できる。

## 6. 保存と保護参照

今回の保護対象は、修正依頼の52参照＋前回レビュー資料814b861＋今回修正ac21980の**54参照**。開始時のGitHubリモート照合は54/54一致。実装担当の53参照へ今回修正ブランチ自身を加えた数であり、相違を隠すための数え替えではない。
保存後も同じ54件を照合する。新しい資料ブランチdocs/v2-history-s3b4-fix-rereview-20261102に本書1本だけを保存し、コード・試験・既存文書を変更しない。

試験クローンはHEAD=00ae4b6、作業ツリー差分0を確認。修正ブランチ・元featブランチ・前回資料は更新しない。PR・マージ・Actions・B-5実装・S3-C・本番・通知・口座操作は行っていない。
