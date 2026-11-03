# V2 範囲試験の固定 限定実装依頼書

作成日：2026-11-03（日本時間）。版：初版。
状態：**初版・採否判断待ち・未承認。本書の保存だけでは実装を始めない。**
対になる設計はdocs/specs/V2_SCOPE_RANGE_FREEZE_DESIGN_DRAFT.md（以下「設計」）。本段階は**試験だけ**を変える。製品コード（ランタイム）は変えない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **b626c98af5f01bc94e7b41d86aadde9663695eb9**（fix/v2-history-adopt-s3b5b-review-20261103） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-scope-range-freeze-20261103）の設計とdocs/specs/V2_SCOPE_RANGE_FREEZE_TRIAL_20261103.diff。SHAと3つのblobを開始報告に記録 |
| B-5b受領 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b、docs/reviews/V2_RECOVERY_S3B5B_FIX_REREVIEW_20261103.md |
| 連鎖の指摘 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5（B-5b設計§7.3・D-3） |

ユーザーが設計§9のD-1〜D-4を採用し、この限定実装への移行を指示した後にのみ、新規実装ブランチをb626c98から作る。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-4）。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。未承認のD-1〜D-4を採用されたと書かない。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| tests/v2_history_ops/test_b17_scope.py | 設計§5.2の固定だけ（END＝b328844） |
| tests/v2_history_restart/test_r3_07_scope.py | 同（END＝d82a5ce） |
| tests/v2_history_restore/test_r4_09_scope.py | 同（END＝ac21980。B17_\*／R307_\*の6定数も受領時の値へ） |
| tests/v2_history_diagnose/test_d5_08_scope.py | 同（END＝c8ba08f。PINNEDも受領時の値へ） |
| tests/v2_history_adopt/test_a5_08_scope.py | 同（END＝b626c98。置換だけ） |
| tests/v2_scope_chain/ 新規 | test_sc_\*.py、sc_helpers.py。\_\_init\_\_.pyは作らない。設計§8の3つの監査 |
| docs/implementation/V2_SCOPE_RANGE_FREEZE_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。すべてのランタイム（v2_core、v2_persistence、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt）、上記5本以外の既存試験・変異・fixtures・ヘルパー（r3_helpers・r4_helpers・a5_helpersを含む）、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
5本の中でも、FilesChangedクラスと設計§5.2の固定定数・END・import io・git_show_at_end以外（Runtime、Imports、NoSideEffects、PathJudgement、パス判定の関数、KIND_CONSTANTS等）は1文字も変えない。
CONSUME、S3-C、B-5b再レビューの提案P-01（a5_09）、P-02へ広げない。範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 固定する振る舞い

- 5本のFilesChangedと固定定数は、ENDの時点（`git show END:path`）の文字に戻し、設計§5.2の5種の置換だけを行う。"HEAD"の置換はトークン単位で、固定文字列の中の文字を変えない。
- 置換後の読取りはすべてENDから行い、作業ツリーを読まない（open、hash-object、listdir、walkをFilesChangedに残さない）。
- setUpは、STARTかENDのコミットが無ければskipする。
- 新しい範囲試験（tests/v2_scope_chain/）は設計§6.1の形（START＝b626c98、`END = None`、`REV = END or "HEAD"`）で書き、作業ツリーを読まない。前の段階の差分を固定文字列で書き写さない。
- 固定の監査（設計§8の1）：固定しない部分はb626c98と同じ文字。固定した部分はENDの時点との差が置換の行だけで、その行を静的なリテラルで固定する（設計作成時の試行では計91行）。加えた最上位の要素はEND・import io・git_show_at_endの3つだけ。test関数名・assertの数（AST）・skipの数はENDの時点と同じ。
- 範囲の鎖（設計§6.3）：範囲試験を自動で探し、ASTでSTART・ENDを読み、隙間のない1本の鎖、各STARTがENDの祖先、各ENDがHEADの祖先、`END = None`は鎖の最後の1つだけ、を確かめる。鎖の始まりがあるのに途中が無い履歴は失敗、履歴が全く無い場合だけskip。
- 自分の範囲の監査（設計§8の3）：b626c98→REVのMが5本ちょうど、Aはtests/v2_scope_chain/と結果文書だけ、それ以外はblob単位で同じ。

## 4. 受入条件 F-01〜F-10

各IDは機能項目であってテスト件数ではない。新規Nは実測する。

| ID | 必須確認 |
|---|---|
| F-01 回帰 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170の計1634件を、完全なクローンで維持。5本のtest関数の数を変えないので件数は同じ |
| F-02 範囲の値 | 5本のSTARTとENDが設計§5.1の完全SHAどおり。r3_07・r4_09のSTARTはヘルパーのFIXED_STARTのまま |
| F-03 受領時の文字 | 5本のFilesChangedと固定定数が、ENDの時点の文字と置換の行だけ違う（新しい範囲試験が`git show END:path`から読んで比べる） |
| F-04 置換 | コードとしての"HEAD"が残らない。固定文字列の中の"HEAD"の文字は残る（r3_07で確認）。作業ツリーの読取りがFilesChangedに無い |
| F-05 固定しない部分 | 5本のFilesChanged・固定定数以外がb626c98と同じ文字。加えた最上位の要素が3つだけ |
| F-06 固定の効果 | 次の段階の模擬（設計§7と同じ変更。新規の試験の中で、一時的なgit worktreeやコピーを作らずに示せない場合は、結果文書に手順と結果を記す）で、5本のFilesChangedが失敗しないこと |
| F-07 範囲の鎖 | 固定後の鎖がadfdf765→b328844→d82a5ce→ac21980→c8ba08f→b626c98→（新しい範囲試験、END=None）。STARTの重複、隙間、ENDが祖先でない、開いた範囲が2つ、の各誤りを、試験内で作った値（ASTを読んだ結果の表）に対して判定器が拒否する |
| F-08 自分の範囲 | 設計§8の3。ランタイム・機能試験・ヘルパー・設定・研究・STATUS等の差分0 |
| F-09 skipの扱い | 履歴の無いツリー（`git archive`）でFilesChangedと鎖の試験がskipになり、失敗にならない。skipの件数を結果文書に記す（B-5b再レビュー003b6dc §3では29件） |
| F-10 範囲監査 | 新しい試験はgitとASTの読取りだけで、ネットワーク・書込み・時計・乱数を使わない。作業ツリーのファイルを書かない |

## 5. 限定欠陥注入

次の10項目を1件ずつ壊し、新しい試験の感度を確認する。検出・等価・未検出・準備失敗を分ける。

1. 5本のうち1本のENDを1つ前のコミットにする。
2. 1本のFilesChangedに、後の段階の許可を1行残す（受領時の文字に戻し忘れ）。
3. r3_07の固定文字列の中の"HEAD"もENDに置き換える。
4. 1本のFilesChangedにopen（作業ツリーの読取り）を1か所残す。
5. 固定しない部分（例：b17のKIND_CONSTANTS）を変える。
6. 固定定数（r4_09のB17_ADDEDの1行、d5_08のPINNEDの1行）を受領時と違う値にする。
7. 範囲の鎖の判定器で、隙間の検査を省く。
8. 範囲の鎖の判定器で、`END = None`が2つあっても通す。
9. 新しい範囲試験のFilesChangedで、M集合の検査を緩める（6本目の変更を通す）。
10. 新しい範囲試験が作業ツリーを読む（REVでなくopen）。

## 6. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使う。依存/設定/workflowを変更しない。
core.autocrlf=falseの別クリーンクローン（完全な履歴）で最終コードを試験する。`git archive`のツリーでの実行（F-09）は別に記録する。`git add`前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
Windowsがある場合は新規N＋B-5b 170＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行する（合計は新規N＋1158）。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_scope_chain -p "test_sc_*.py" -v

結果文書には、実モデル設定/effort、固定資料の完全SHA/3つのblob、開始/試験/最終SHA、5本の差分全文、試行の差分（設計§7）との違いとその理由、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、F-06の模擬の手順と結果、変異一覧・分類、未実施を記す。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、CONSUME、S3-Cへ進まない。

## 7. 読取専用の保護参照

次の65参照を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-scope-range-freeze-20261103も、受け取った版の完全SHAを1本加える（実装時は66参照）。

| 参照 | 完全SHA |
|---|---|
| main | 31144d9b6af8a6c920ad53c395cd550e8c48a7fa |
| feat/interim-notification-20261026 | 920e69571cf4feda09f3f2f560e96fcb9cb09d50 |
| docs/v2-roadmap-20261023 | 647aeac34cde0d01ec27174f7620aff1724af0e1 |
| feat/v2-offline-core-20261027 | 1a54a8573023af9490017b02a8b6458f061031c7 |
| feat/v2-core-state-checks-20261028 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| docs/v2-market-state-recovery-20261027 | b43205ce1a53e4560fb85f9cfb715c72a1132a75 |
| docs/v2-persistence-domain-20261028 | 425df80d04b116e25e481184069b89bed1380c3a |
| docs/v2-persistence-domain-s1-receipt-20261028 | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| feat/v2-persistence-domain-offline-20261028 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| fix/v2-persistence-domain-s1-review-20261028 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| docs/v2-persistence-domain-s1-fix-receipt-20261028 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048 |
| fix/v2-core-fg-numeric-overflow-20261028 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| docs/v2-core-fg-overflow-receipt-20261028 | a235b7607f5624ed84ba5427ac0f44029f41d262 |
| docs/v2-local-store-s2-20261028 | 73cec624cb73205ac63ca92e26df2b6f70019b16 |
| feat/v2-local-file-store-s2-20261028 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| docs/v2-local-store-s2-receipt-20261028 | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| fix/v2-local-store-s2-review-20261028 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| docs/v2-local-store-s2-fix-receipt-20261028 | 1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a |
| docs/v2-user-pc-tests-20261028 | aa21dbe85a133c61e8c011a6f78db1b23af0fb13 |
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| docs/v2-history-s3b4-review-20261102 | 814b86190562475286300d7e6df3a749a9140331 |
| fix/v2-history-restore-plan-s3b4-review-20261102 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| docs/v2-history-s3b4-fix-rereview-20261102 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| docs/v2-history-s3b5-20261102 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136 |
| docs/v2-history-s3b5-review-20261102 | 842d44b192a03531f6d3cb896d8281733814899f |
| docs/v2-history-s3b5-v2-rereview-20261102 | 6a7210c2e278e604b953acf904cf9e796c2ce710 |
| feat/v2-history-diagnose-s3b5a-20261102 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6 |
| docs/v2-history-s3b5a-review-20261102 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9 |
| docs/v2-history-s3b5b-20261102 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |
| feat/v2-history-adopt-s3b5b-20261103 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01 |
| docs/v2-history-s3b5b-review-20261103 | 92630a3d5233f14900c7472dc754850701a56b61 |
| fix/v2-history-adopt-s3b5b-review-20261103 | b626c98af5f01bc94e7b41d86aadde9663695eb9 |
| docs/v2-history-s3b5b-fix-rereview-20261103 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b |

## 8. 採用単位

設計§9のD-1（方式(a)）、D-2（固定の中身）、D-3（今後の規則）、D-4（試験だけの限定実装、Sonnet 5.5・high）と、本書の変更境界/受入/欠陥注入/結果保存を一組で判断する。
今回の文書作成と、設計§7の一時環境の試行は、その採用ではない。B-5bの受領をこの段階の実装承認にしない。
