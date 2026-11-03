# S3-B-5b 限定実装レビュー

作成日：2026-11-03（日本時間）。担当：Codex。製品コードの修正なし。
結論：**重大0・通常1・提案0。R-01の限定修正と再確認を推奨する。** 本レビューは本番反映、S3-C、CONSUMEへの移行承認ではない。

## 1. 対象と固定資料

| 用途 | 固定値 |
|---|---|
| 実装ブランチ | `feat/v2-history-adopt-s3b5b-20261103` |
| 開始点 | `c8ba08f15ea28248a9fe7924f32ce136fc16d5e6` |
| コード・試験 | `2daab90ffbde881eaa33f6644a31e57dad0c8048` |
| 結果文書付き最終・今回の試験checkout | `782debc2a901a421a2b5205f9dd8ad4f0b484b01` |
| B-5b設計・依頼・試行diff | `5d21c10885a97e8d0cd614444f0da9b11ca322a5` |
| 上位B-5第2版 | `5c9e1e89c8f9d33689e9bc67e266fa6031507136`、設計§9 |
| 上位S3-B第2版 | `361904b1618ae9f9d3a672875c437a388826c253`、設計§3.3 |

ローカルに添付された結果文書とGitHubの `docs/implementation/V2_RECOVERY_S3B5B_RESULT.md` はバイト一致した。コードSHAから最終SHAの差分は同文書1本の追加だけ。CLAUDE.md、STATUS.md、MODEL_POLICY.mdとROADMAPの該当箇所も読んだ。STATUSは古い記述であり、今回の採用履歴を取り消す根拠にはしない。

重点確認：新パッケージ6本、既存ランタイム6本の差分、既存試験6本の補正、新規機能・scope試験、B-1検査器・B-2投影・B-4の復元下限との接続。

## 2. 結論の範囲

採用記録の12キー、evidenceの6キー、検査順序、移行の痕跡の拒否、物理prefixと捨てる側のID検査、採用記録を含める復元下限は、固定設計に整合している。既存ランタイムの変更は承認された6本に限られる。新規APIはメモリ内の候補Historyを返し、committedはFalse。ファイル公開や通知は行わない。

残る問題は、**外から読んだ計画の `discarded` の内部形式・整合性を、元バイトがない再確認経路で検査しない**ことである。候補Historyそのものの変更や、実ファイルへの書込みは今回の反例では発生しない。したがって通常とした。

## 3. 指摘 R-01

| 項目 | 内容 |
|---|---|
| 重大度 | 通常 |
| 根拠 | `v2_history_adopt/confirm.py:24` `_form_ok`、同33行のdict判定、同63〜73行 `_plan_basis`、同93〜94行 NO_CHANGE経路 |
| 契約 | B-5b設計§5.4のdiscarded形式、§5.5の「計画自身の形・内部整合をdataより先に検査」、依頼A5-13 |
| 問題 | discardedはdictであることしか検査されない。空辞書、負やboolのcount、adopt_countと異なるfrom_index、countとitemsの長さの不一致、不正なitems要素が、plan_hashを再計算すると候補バイトでNO_CHANGEになる |
| 影響 | 不正な計画が再確認成功として返る。さらにdata=Noneでは計画の不正より先にadoption_invalid/data/typeになり、エラー優先順位も外れる |
| 最小修正 | confirmの計画検査に、discardedの厳密な形・型と計画内で判定可能な整合性を追加する。全経路でdataを読む前にhistory_plan_mismatchにする。B-1検査器・保存スキーマの変更は不要 |
| 確認方法 | 付属プローブの19観測。修正後は `--expect-fixed` が終了0になり、正常な元バイト／候補バイトの対照と56ケースのprefix確認を維持すること |

再現手順：正常なprepareで得た計画のbasis.discardedだけを改変し、plan_hashを `sha256(canonical_json(basis))` で計算し直す。AdoptionPlan.from_dictで読み、元と同じ候補バイトをconfirmに渡す。例えば `discarded={}` でも結果はNO_CHANGEになる。

| 観測 | 元バイト | 候補の正規化バイト | data=None |
|---|---|---|---|
| 空辞書、負count、bool count、開始位置違い、count違い（計5例） | mismatch | **NO_CHANGE** | **data/type** |
| items非list、余分なキー、要素のキー欠落、index違い、bool index、bool seq、未知kind、不正d、不正request_id（9例） | mismatch | **NO_CHANGE** | 今回は観測対象外 |

元バイト14例がすべて拒否されることは対照として確認した。新規の既存試験 `Mismatch.test_the_keys_that_the_candidate_itself_proves_are_a_mismatch_for_the_candidate_bytes_too` はdiscardedとdiagnosis_digestを列挙から外しているため、この経路の不正形を検出しない。

**修正対象の限界：** 元バイトなしでは、形式も計画内の整合も保ったdiscardedの記述内容やdiagnosis_digestの真偽までは再検証できない。本指摘はその証明を求めない。元バイト経路の全basis再構築と、候補バイト経路の厳密なバイト一致は維持する。計画内で分かる不正な形や矛盾だけを拒否する。hashの一致を作成者の真正性の証明として扱わない。

## 4. 実行した試験

環境：Linux、Python **3.12.14**、Git 2.51.1。新規クローン、core.autocrlf=false、作業ツリー差分0。各スイートを別プロセスで `PYTHONDONTWRITEBYTECODE=1 python -B -W error::ResourceWarning -m unittest discover -s tests/<suite>` により実行した。

| スイート | 件数 | 結果 |
|---|---:|---|
| v2_core | 197 | 合格 |
| v2_persistence | 170 | 合格 |
| v2_persistence_local | 113 | 109合格・Windows専用4 skip |
| v2_recovery | 176 | 合格 |
| v2_history | 230 | 合格 |
| v2_history_ops | 173 | 合格 |
| v2_history_restart | 109 | 合格 |
| v2_history_restore | 165 | 合格 |
| v2_history_diagnose | 131 | 合格 |
| v2_history_adopt | 155 | 合格 |
| **合計** | **1619** | **1615合格・4 skip、失敗/error 0、各終了0** |

本環境の `unshare -rn true` はuid_mapへの書込みがOperation not permittedで失敗した。OS単位のネットワーク遮断は未実施。新規・履歴系のヘルパーはプロセス内でsocketを禁止するが、これをOS全体の遮断の代用とは数えない。試験は固定fixtureによるオフライン用途であり、データ取得、通知、Actionsは起動していない。

独立プローブ：`docs/reviews/s3b5b_review_probe.py`。

- R-01：19観測すべて未解消（候補バイト14例、エラー優先順位5例）。
- 元バイトでの不正計画拒否14/14、正常結果・stale・data型の対照6/6合格。
- prefix格子56/56合格。新規、再開始、複数復元、DECLARE再生、移行済みの6種類のfixtureで、各破損位置とヘッダーのみの破損を確認。期待する最長prefixは全長を短い方から列挙し既存検査器に通して独立に決定し、採用可否・市場状態不変・NO_CHANGEまで確認した。
- 欠陥注入53変異は今回再実行していない。担当者の報告と本レビューの実行を区別する。

## 5. 差分・参照の確認

- 開始点からコードSHAは27ファイルの差分。既存Mは6ランタイム＋6試験の12本、新規はパッケージ6本＋試験/補助9本。最終で結果文書1本を追加。
- 固定設計の試行diffを開始点へ適用した結果と実装を独立に比較した。違いは報告どおり、restore.pyのdocstringと、d5_08のpoints.py例外を既存分岐へ統合する箇所だけ。後者はassert数を維持し、同じパスのblob差分の検査を保つ。その他の違いなし。
- 依頼§8の60参照＋資料ブランチ＋実装ブランチの**62参照**が、レビュー開始後の取得時と保存前（2026-11-03T08:52Z）で完全SHA一致。
- 実装担当が実装前に参照照合をしなかった逸脱は、結果文書§10に明記されている。今回の照合で、過去の開始時照合をしたことにはできない。虚偽の「開始時一致」へ書き換えない。

## 6. 次の最小作業と未実施

添付の限定修正依頼案 `docs/tasks/V2_RECOVERY_S3B5B_REVIEW_FIX_REQUEST.md` の範囲でR-01を修正し、回帰試験と再現コードを確認することを推奨する。**依頼案は未承認**であり、本レビューでは実装しない。S3-CやCONSUMEの実装へは進まない。

実Windows、ユーザーPC、Python 3.10/3.11/3.13、core.autocrlf=true、物理電源断、OS単位の通信遮断は未実施。Claudeのモデル設定や他環境4版の実行は報告として受領し、本レビューの実測には含めない。

変更したのは新しいレビュー資料ブランチ上の本文、再現コード、限定修正依頼案だけ。製品コード、既存試験、既存結果、main、実装・資料の既存ブランチは変更しない。PR・マージ・本番反映・送信なし。
