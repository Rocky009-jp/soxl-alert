# V2 C-1 CONSUME 限定実装依頼書

作成日：2026-11-03（日本時間）。版：初版。
状態：**初版・採否判断待ち・未承認。本書の保存だけでは実装を始めない。**
対になる設計はdocs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md（以下「設計」）。本段階はC-1（復元の5つ目の処分CONSUME）だけを、メモリ内の純粋な計算として実装する。C-2〜C-4（公開値、v2ローカル正本、保守操作）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **bfbde7a7854bf91a77fb58737c24b19c6507453a**（fix/v2-scope-range-freeze-review-20261103） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-consume-s3c-20261103）の設計とdocs/specs/V2_CONSUME_C1_TRIAL_20261103.diff。SHAと3つのblobを開始報告に記録 |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6（設計§6、D-3）と再レビュー9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |
| B-5b再レビュー | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b §5 P-02 |
| 復元の上位設計 | S3-B第2版361904b1618ae9f9d3a672875c437a388826c253 §8.6〜8.8、B-4設計0108131045d904b0997299fcade5929567940d6d §5・§7.1・§8・§11 |

ユーザーが設計§8のD-1〜D-6を採用し、この限定実装への移行を指示した後にのみ、新規実装ブランチをbfbde7aから作る（ブランチ名の案：feat/v2-history-consume-c1-YYYYMMDD）。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-6）。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。未承認のD-1〜D-6を採用されたと書かない。運用方針は日足のみ（分足・NBBOを前提にしない）。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history/restore.py | 設計§3.3の検査器の規則（CONSUMEの形・位置・日の規則）とモジュールのdocstring。他の関数の振る舞いは変えない |
| v2_history_restore/（既存10ファイル） | 設計§3.4〜3.8。新しいファイルは足さない（r4_09のFILESを変えないため） |
| tests/v2_scope_chain/test_sc_03_scope.py | `END = None`→`END = "bfbde7a7854bf91a77fb58737c24b19c6507453a"`の1行（設計§6.1）。コメントの書き換えはその行の中だけ |
| tests/v2_history/test_h06_restore_batch.py | 設計§6.3の1件（試験名と期待2行） |
| tests/v2_history_restore/test_r4_01_point_ops.py | 設計§6.3の1件（期待2行とコメント） |
| tests/v2_history_restore/test_r4_09_scope.py | 設計§6.3の4件。Runtimeクラスの該当箇所とALLOWED_NAMES・CONSUME_NAMESだけ。FilesChanged、END、B17_\*／R307_\*の固定定数、他の試験は1文字も変えない |
| tests/v2_history_consume/ 新規 | test_c1_\*.py、c1_helpers.py。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_CONSUME_C1_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence、v2_recovery、v2_history（restore.py以外）、v2_history_ops、v2_history_restart、v2_history_diagnose、v2_history_adopt、上記以外の既存試験・変異・fixtures・ヘルパー（h_helpers、r4_helpers、sc_helpersを含む）、範囲試験の固定5本とtest_sc_01・02、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
v2_history/__init__.pyとv2_history_restore/__init__.pyの公開名（\_\_all\_\_）は変えない。v2_history.KINDSは8種のまま。v2_history_restore.values.OPS（退避記録を名指しする4処分）は4つのまま。
C-2〜C-4、B-4§7.1の既知の制限の解消、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02へ広げない。範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 固定する振る舞い

- **記録の形**（設計§3.2）：opsの要素`{op:"CONSUME", d}`、replayの要素`{op:"CONSUME", from_seq:null, d, seq, same_as_superseded:null}`。RECOVERY_RESTOREの15キー・replayの5キー・APPLYのキーは変えない。CONSUMEを除いた列が退避列を鎖の順に1回ずつ名指しし、作られる記録はopsの順に途切れずに並ぶ。
- **検査器**（設計§3.3）：表の各規則と拒否のrule名。解放日・決定・市場値は検査器で確かめない（D-2の(ii)）。作られたAPPLYは鎖ビューの通常の規則で検査される。未知の処分名（小文字の"consume"を含む）はrestore_op_unsupportedのまま。
- **計画**（設計§3.4）：段階の位置と順序。決定は残す記録の行（復元点までの有効列のFixedFacts／LedgerContextに、変更しないapply_recordsで残す記録の解決記録を当てた行）から変更しないselect_decisionで選ぶ。市場値はREAPPLYと同じ固定方法（market.py）でopsの順に読む。CONSUMEのAPPLYは変更しないapply_transitionで作る。解放日の検査は下書きの組立ての後・hashの前。段階7で事前集合から決定を選び直す。evaluate_dayは最終投影の一致の後に、REAPPLYとCONSUMEのすべての日で呼ぶ。無効果はDROPもCONSUMEも無く全REAPPLYがsame=trueのときだけ。
- **計画値**（設計§3.6）：basisは23キー、operationは"soxl-v2-history-restore-plan/1"のまま。series_inputsのCONSUMEの項目はfrom_seq=null。changesのCONSUMEの行は`{op:"CONSUME", from_seq:null, kind:"APPLY", d, to_seq, same_as_superseded:null, changed_fields:[]}`。CONSUMEを含まない計画の値はbfbde7aと同じ文字。
- **確認**（設計§3.7）：形の検査でCONSUMEの要素・項目・行を受け付ける。現在のseries_inputsはplanのopsから同じ方法で読み直す。再構築・全basis比較・NO_CHANGEは従来どおり。
- **エラー**（設計§3.8）：code／field／rule／detailを表のとおり。CONSUMEの計画側の拒否はdetail=D（日付だけ）。
- **戦略式を書かない**：閾値・比率・状態の式・台帳の判定規則を複製しない。新しいAPPLYは既存apply_transitionから、最終の確認は既存project_history_ledgerとevaluate_dayで行う。
- **P-02の規則5**（設計§4）：v2_history_restoreはv2_history_adopt・v2_history_diagnoseをimportしない。採用記録のevidence、採用計画のdiscarded・diagnosis_digestを読まない。
- **範囲試験**（設計§6.2）：tests/v2_history_consume/の範囲試験は`START = "bfbde7a…"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。前の段階の差分を固定文字列で書き写さない。既存試験4本の補正は、その削除行・追加行・ハンクをC-1自身の差分として静的に固定する。

## 4. 受入条件 C1-01〜C1-18

各IDは機能項目であってテスト件数ではない。新規Nは実測する。

| ID | 必須確認 |
|---|---|
| C1-01 回帰 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34の計1668件を、完全なクローンで維持（設計§6.3の補正6件を含む。件数は同じ） |
| C1-02 記録の形 | CONSUMEを含む候補の記録が設計§3.2の形。RECOVERY_RESTOREの15キー、replayの5キー、opsの`{op,d}`。キーの追加なし |
| C1-03 検査器 | 設計§3.3の各拒否を、独立の試験用ビルダー（h_helpersのHB等を読むだけ）で作った履歴の改変で確かめる：要素の形、opsとreplayの不一致、退避APPLYの日、重複、requestバッチの間（REPLAY・DROPの両方）、作られた記録の種別・日、途中で終わる履歴。CONSUMEのAPPLYが通常のAPPLYの規則（S1射影）で検査されること |
| C1-04 成功例 | 設計§3.10のREADYの各例で、READY→CONFIRMED_IN_MEMORY→同じ候補へのNO_CHANGE。候補をvalidate_historyとproject_history_ledgerに通す |
| C1-05 期待値の独立性 | 成功例の少なくとも2つ（宣言の取消、再開始の取消）で、作られたAPPLYのconfirmed_inputs・skipped_sessions・transition_result・state_afterを、試験側で既存S1のprepare_day（または同じ日を既存evaluate_dayで計算した値）から独立に作り、一致を確かめる。実装の出力をコピーして期待値にしない |
| C1-06 解放日 | 宣言のDROP、再開始のDROP（基点が初期状態の場合を含む）、REAPPLYで新たに飛ばす日（現在のカレンダーにセッションを加える合成入力）の3種で消費できる。REPLAYで残した宣言の日、解放範囲外の日はrestore_consume_not_released |
| C1-07 停止の維持 | 決定のある解放日をCONSUMEしなければ、従来どおりrestore_requires_consume（detail=その日）。2日のうち1日だけ消費した場合も |
| C1-08 決定 | 決定は残す記録の行から選ばれる。決定が無ければrestore_consume_no_decision。select_decisionの衝突・窓外・target_mismatchはそのまま返る。宣言＋LATE ACKをDROPした例で後発の決定（L2）が使われる。段階7の選び直しが違えばrestore_decision_changed（見えない分岐をspyまたは合成入力で通す） |
| C1-09 市場値 | CONSUMEの日のrow・prev_row・prev_session_dateが注入seriesから固定される。previous_dateの食い違いはsession_series_mismatch、形の誤りはrestore_invalid／series／market_input。計画後にその日の行を変えると確認はhistory_plan_stale |
| C1-10 順序 | 誤りの優先順位：形（段階2）→ID→決定なし・位置（段階4）→解放日（段階4の末尾、hashの前）→候補の検査（段階5）→証拠（段階6）→選び直し・新規消費・REAPPLYの決定と市場値（段階7）→最終投影→evaluate_day（段階8）。evaluate_dayは最終投影の一致の後にだけ、REAPPLYとCONSUMEの日の数だけ呼ばれる（spy） |
| C1-11 差の表示 | changesのCONSUMEの行の形。後続REAPPLYのsame_as_superseded=falseとchanged_fields。summary・reprに値・市場値・F&G・自由文が出ない |
| C1-12 無効果 | CONSUMEだけ（DROPなし、全REAPPLYがsame=true）の計画はrestore_no_effectにならない（暦の変更で新たに飛ばす日を消費する合成入力）。DROPもCONSUMEも無い計画は従来どおりrestore_no_effect |
| C1-13 確認 | 計画の改変（CONSUMEの日・位置・series_inputsの項目・changesの行）はhistory_plan_mismatch、確認hash違いもmismatch。CONSUMEの形の誤った計画はfrom_dictまたは確認の段階1で拒否 |
| C1-14 互換 | CONSUMEを含まない計画のbasis・候補が、bfbde7aの実装と同じ文字になる（同じ入力でbfbde7aの`git show`から読み込んだ実装との比較、または既存B-4試験の期待値の不変で示す。方法を結果文書に書く） |
| C1-15 P-02 | v2_history_restoreがv2_history_adopt・v2_history_diagnoseをimportせず、"discarded"・"diagnosis"・"evidence"の語を名前・文字列に持たない（docstringを除く） |
| C1-16 範囲の値 | test_sc_03のENDがbfbde7a（1行だけの差分）。範囲の鎖がadfdf765→…→b626c98→bfbde7a→（C-1、END=None）で、開いた範囲はC-1の1本だけ |
| C1-17 自分の範囲 | bfbde7a→REVで、Mは§2の許可のファイルだけ（v2_history/restore.py、v2_history_restoreの変更したファイル、試験4本）。Aはtests/v2_history_consume/と結果文書だけ。それ以外はblob単位で同じ。既存試験4本の差分は静的に固定した行・ハンクと一致 |
| C1-18 範囲監査 | 変更したランタイムに、I/O・時計・乱数・ネット・スレッド・環境変数・hashlib、新しい依存、公開名の追加が無い。新しい試験はネットワーク・書込み・時計・乱数を使わず、作業ツリーのファイルを書かない |

## 5. 限定欠陥注入

次の項目を1件ずつ壊し、試験の感度を確認する。検出・等価・未検出・準備失敗を分け、等価には根拠を書く。

1. 検査器：CONSUMEの日と作られたAPPLYの日の比較を省く。
2. 検査器：退避APPLYの日の規則を省く。
3. 検査器：requestバッチの間の規則を省く（REPLAYの場合だけ残す、の変異も）。
4. 検査器：重複の規則を省く。
5. 計画：解放日の検査を省く。
6. 計画：解放日の集合で、DROPした宣言・DROPした再開始・REAPPLYで新たに飛ばす日のどれか1種を落とす。
7. 計画：決定を残す記録の行でなく、生の台帳から選ぶ（apply_recordsを通さない）。
8. 計画：段階7の選び直しを省く。
9. 計画：CONSUMEの日をevaluate_dayの再計算から外す。
10. 計画：CONSUMEの市場値をseries_inputsに入れない（series_digestにCONSUMEの日が入らない）。
11. 計画：無効果の規則でCONSUMEを数えない。
12. 計画：CONSUMEの位置（区間の基点<D）の検査を省く。
13. 計画：解放日の検査をhashの後（候補の検査の後）へ移す（C1-10の順序で検出されること）。
14. 確認：現在のseries_inputsの読み直しでCONSUMEの日を落とす。
15. 確認：形の検査でCONSUMEの行のfrom_seq=null以外を受け付ける。
16. 範囲試験：新しい範囲試験が作業ツリーを読む（REVでなくopen）。
17. 範囲試験：既存試験4本の補正の固定行を1行変える。

## 6. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使う。依存/設定/workflowを変更しない。
core.autocrlf=falseの別クリーンクローン（完全な履歴）で最終コードを試験する。`git archive`のツリーでのskipの件数は別に記録する。`git add`前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
Windowsがある場合は新規N＋範囲の鎖34＋B-5b 170＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行する（合計は新規N＋1192）。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_consume -p "test_c1_*.py" -v

結果文書には、実モデル設定/effort、固定資料の完全SHA/3つのblob、開始/試験/最終SHA、変更したランタイムの差分全文、既存試験4本と1行の固定の差分全文、試行の差分（設計§7）との違いとその理由、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、変異一覧・分類、未実施を記す。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、C-2〜C-4へ進まない。

## 7. 読取専用の保護参照

次の70参照を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-consume-s3c-20261103も、受け取った版の完全SHAを1本加える（実装時は71参照）。

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
| docs/v2-scope-range-freeze-20261103 | 08072cc47aa12340ed947d40f02ca8741a4060d6 |
| feat/v2-scope-range-freeze-20261103 | dda7eb706637adc5f6dd37513e4b6ca360fde2ba |
| docs/v2-scope-range-freeze-review-20261103 | fa4b232810569f4512d09f244ef50f9685ff0c95 |
| fix/v2-scope-range-freeze-review-20261103 | bfbde7a7854bf91a77fb58737c24b19c6507453a |
| docs/v2-scope-range-freeze-fix-rereview-20261103 | 9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d |

## 8. 採用単位

設計§8のD-1（分割と順序、今回はC-1だけ）、D-2（CONSUMEの規則）、D-3（P-02の扱い）、D-4（S3-Cの方針は設計案として受け取るだけ）、D-5（範囲試験）、D-6（C-1の限定実装、Sonnet 5.5・high）と、本書の変更境界/受入/欠陥注入/結果保存を一組で判断する。
今回の文書作成と、設計§7の一時環境の試行は、その採用ではない。範囲試験の固定の受領をC-1の実装承認にしない。C-2〜C-4の実装承認も含まない。
