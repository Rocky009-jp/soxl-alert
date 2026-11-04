# V2 C-4 保守操作 N-01限定修正 再レビュー

作成日：2026-11-04（日本時間）。担当：Claude Opus 5.5・high（実装レビュー906a70aと同じスレッド・セッション設定）。Rockyさんの「推奨どおり」（2026-11-04T10:55Z、コーディネーター経由）で行われたN-01の限定修正について、差分だけを再レビューした。製品コード・実装ブランチ・既存試験は変更していない。

結論：**N-01は解消。新しい重大・通常の指摘は無い。推奨は「受領」**（試験対象195d353、保存最終2e6ba5f）。実装レビューの提案P-01〜P-04は手付かずのまま（依頼どおり。任意で、受領の条件にしない）。
本再レビューはPR・マージ・本番反映・S4への移行の承認ではない。

## 1. 対象

| 項目 | 完全SHA |
|---|---|
| 前の保存最終（レビュー対象） | 9b00efd00074695626fb84d5490c9c8ea89edc16 |
| 実装レビュー | 906a70a2877cf135947498f53c0750cb3c43156d（docs/v2-history-maintain-c4-impl-review-20261104、重大0・通常1・提案4） |
| 修正（新しい試験対象） | **195d3531007a0fb8319db90ccd058c664d04d885** |
| 新しい保存最終 | **2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb**（feat/v2-history-maintain-c4-20261104、195d353からは結果文書の追補§14だけ） |

## 2. 差分

9b00efd→2e6ba5fで変わったのは3ファイルだけ（+67／−3）。

| ファイル | 内容 | 判定 |
|---|---|---|
| v2_history_maintain/store.py（+8／−3） | `_migrate_resume`の2か所。読み始め（旧787行）は`_read`が`None`なら`maintenance_state_unexpected`（ruleは従来どおりv1_and_v2／v2_present）。renameの後の読み直し（旧809行）は`None`なら`maintenance_state_unexpected`／store／scan／rule v2_present | 妥当。どちらの誤りも例外処理の外で投げる（`__context__`なし）。`_read`の`False`は従来どおり`store_root_invalid`。ほかの`_read`の呼出しは前から`None`を扱っている（レビュー時に確認済み） |
| tests/v2_history_maintain/test_c4_04_migrate.py（+49） | `Resume`に4件。lstat・read_fileの2種×「両方」「完了後」×読み始め・読み直しの8ケース。前後の`H.tree`の一致、renameの後の場合は「退避は済み、同じ呼出しで完了」を確かめる | 妥当。修正前のコード（9b00efd）に新しい試験だけを当てると8ケースとも`TypeError`でERRORになることを独立に確認した |
| docs/implementation/V2_HISTORY_MAINTAIN_C4_RESULT.md（+10） | 追補§14 | 内容は差分・試験と一致。§0・§10の「CoreErrorだけ」が依頼の3種の例外での結果だったことも書かれている（レビューP-04(a)の一部に当たる） |

範囲試験（test_c4_09のSTART＝6d69bd7、END=None）とtest_c3_09の1行は変わっていない。変更は C-4の開いた範囲の中（v2_history_maintain/、tests/v2_history_maintain/、結果文書）に収まる。

## 3. 確認

| 確認 | 結果 |
|---|---|
| 全スイート（2e6ba5f、完全な履歴の別クリーンクローン、core.autocrlf=false、runall.sh） | Python 3.10.20／3.11.18／3.12.3／3.13.18の4版とも15スイートrc＝0。既存2,069＋新規184＝**2,253件**合格。skipはS2のWindows専用4件だけ（`rr_allver_2e6ba5f.log`） |
| レビューのプローブX1（`c4i_probe.py`） | 4通りとも固定語：両方の読み始め→state_unexpected／v1_and_v2、両方の読み直し・完了後の2通り→state_unexpected／v2_present。rootは変わらないか、移行が完了したまま（`rr_probe_out_py312.txt`）。X2〜X9は前回と同じ結果 |
| 2重故障（移行、STRICT、OSError・FileNotFoundError、`c4i_sweep2.py double migrate strict os,fnf`） | 21,914通りで、CoreError以外**0**（前回の160通りは`maintenance_state_unexpected`になった）、不変条件の違反0、全件が§5.4の手順で最終の状態に着いた |
| 例外5種の単独故障（移行、STRICT 465通り・FILE_SYNC_ONLY 385通り） | 違反0 |
| 実装者の欠陥注入32件（mutate.py、試験対象195d353、3.12） | 31件DETECTED、19bだけUNDETECTED（等価の判断は前回のとおり妥当）。失敗した試験の数は項目11だけ11→15（追加の試験も捕まえる）で、ほかは前回と同じ |
| 次段階の模擬（next_stage_sim.sh、2e6ba5f、3.13） | [A] 全件OK、[B] ENDだけ2e6ba5fに固定で範囲の鎖2件だけ失敗（想定どおり）、[C] 仮の開いた範囲を足すと全件OK（`rr_next_stage_sim_2e6ba5f.txt`） |

確認の途中の記録：最初の全件試験は、レビュー側の作業用クローンの履歴がe3d880aで切れていた（前回のレビュー資料の取得で浅い取得をしたため）ので、範囲の鎖の試験（test_c4_09 Chain）が4版とも失敗した。これは実装ではなくレビュー側の環境の問題で、完全な履歴を取り直したクローンで再実行し、上の表のとおり全件合格した。浅いクローンで動かした欠陥注入も止め、取り直したクローンでやり直した。

## 4. 新しい指摘

なし（重大0・通常0・提案0）。

参考（指摘にしない）：renameの後の読み直しで本当にhistory.jsonが消えていた場合、rootは`quarantine/`だけになり、次の`migrate`は`maintenance_state_unexpected`／emptyで止まる。人や別の道具がロックを無視して消した場合だけで、元のバイト（snapshot.json）は退避先にあり、候補は公開値から作り直せる。設計§5.4の外の扱いで、今回の修正で新しく生じた状態ではない。

## 5. 推奨

- **推奨：受領**。試験対象は195d3531、保存最終は2e6ba5f。
- 次の段階は、test_c4_09の`END = None`を2e6ba5f（受領した最終）に1行で固定し、同じコミットで自分の開いた範囲試験（START＝2e6ba5f）を足す（[B][C]で確認済み）。
- 実装レビューの提案P-01〜P-04は任意で、受領記録に注記するか、次に該当のファイルを触る機会に扱う。P-04(a)は結果文書§14で一部対応済み。
- 未実施のまま：実Windows（新規184＋1593）、ユーザーPC、物理電源断、ネットワークドライブ・同期フォルダ上のroot。

## 6. 作業記録

- 保護参照：開始時に、依頼書§7の82参照＋docs/v2-history-maintain-c4-20261104（d11b875）＋docs/v2-history-maintain-c4-impl-review-20261104（906a70a）の84件を`git ls-remote`の完全SHAで照合し、全件一致（実装ブランチは2e6ba5f）。本記録のpush後にも照合する（結果はスレッドの報告に記す）。
- 変更したもの：本書と確認の出力（`docs/reviews/v2_history_maintain_c4_fix_rereview_20261104/`）だけを、2e6ba5fから作った新しい資料ブランチdocs/v2-history-maintain-c4-fix-rereview-20261104に追加した。確認スクリプト（c4i_probe.py、c4i_sweep2.py）は906a70aのものをそのまま使った。製品コード・実装ブランチ・既存試験・設定の変更、PR、マージ、Actions、送信は0。
- モデル別の利用量は未計測。
