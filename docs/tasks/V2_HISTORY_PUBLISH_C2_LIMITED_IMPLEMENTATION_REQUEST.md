# V2 C-2 公開値と照合 限定実装依頼書

作成日：2026-11-03（日本時間）。版：初版。
状態：**初版・採否判断待ち・未承認。本書の保存だけでは実装を始めない。**
対になる設計はdocs/specs/V2_HISTORY_PUBLISH_C2_DESIGN_DRAFT.md（以下「設計」）。本段階はC-2（公開値、CASの検査、照合、バイトの形）だけを、メモリ内の純粋な計算として実装する。C-3（v2ローカル正本）・C-4（保守操作）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **de6549acb4ecea759cc771300fd0bef59dd5456a**（feat/v2-history-consume-c1-20261103、C-1の保存最終） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-history-publish-c2-20261103）の設計とdocs/specs/V2_HISTORY_PUBLISH_C2_TRIAL_20261103.diff。SHAと3つのblobを開始報告に記録 |
| C-1の受領 | レビューb473db46ad3dbf3ad76fa76f50c49b03b558936d（§4.5の分担、§5のP-01〜P-03、§6） |
| 上位の分割・P-02の規則 | a6340c3937092e4cb658913b9acfb4973a084326 docs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md §4・§5.1・§5.2（D-1〜D-6採用済み） |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6（設計§6、D-3）と再レビュー9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

ユーザーが設計§8のD-1〜D-8を採用し、この限定実装への移行を指示した後にのみ、新規実装ブランチをde6549aから作る（ブランチ名の案：feat/v2-history-publish-c2-YYYYMMDD）。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-8）。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。未承認のD-1〜D-8を採用されたと書かない。運用方針は日足のみ（分足・NBBOを前提にしない）。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history_publish/ 新規 | 設計§2.3の6ファイル（`__init__.py`、`values.py`、`errors.py`、`read.py`、`build.py`、`check.py`）。ファイルの分け方を変える必要があれば、結果文書に理由を書く。7ファイルを超えない |
| tests/v2_history_consume/test_c1_09_scope.py | 設計§6.1の`END`の1行と、§6.2の自己読直しの1行（`C.show(REV, …)`→`C.show("HEAD", …)`）の計2行。コメントの書き換えはその行の中だけ |
| tests/v2_history_publish/ 新規 | test_c2_\*.py、c2_helpers.py。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_HISTORY_PUBLISH_C2_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、既存の試験・変異・fixtures・ヘルパー（h_helpers、r4_helpers、c1_helpers、sc_helpersを含む）、範囲試験（test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09の上の2行以外）、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
既存パッケージの公開名（\_\_all\_\_）、v2_history.KINDS（8種）、B-2のHistoryAppendBatchの形と規則は変えない。
C-3・C-4（ファイル、ロック、退避、解錠、移行・採用の実行）、C-1レビューのP-02（受領記録の注記）・P-03（r4_09）、B-4§7.1の既知の制限、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02へ広げない。範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 固定する振る舞い

- **作り方**（設計§3）：publish_\*の7関数とその引数。各関数は既存の確認の関数を自分で呼び、PREPARED／CONFIRMED_IN_MEMORYからだけ作る。NO_CHANGE・NO_COMMIT・ALREADY_APPLIEDは`publication_refused`（rule＝no_change／not_prepared）。確認の拒否は既存のcode・ruleのまま返す（包み直さない）。History・確認結果・dictを受け取る作り方の関数、公開値のfrom_dictを作らない。`_make`を呼ぶのはbuild.pyだけ。
- **APPENDの共通処理**：候補の先頭n件のdigestが今の履歴のdigestと同じこと、n件目以降がrecords。DAILY・RESOLUTIONはcheck_append_batchを通した候補（RESOLUTIONは確認結果のhistoryとも一致）。
- **移行の元**：snapshot.jsonのバイトを受け取り、S2の読込みと同じ厳格さ（UTF-8、decode_snapshot、validate_snapshot）で読んでから確認する。source_v1はそのバイトから計算する。
- **公開値の形**（設計§4）：body 14キー、operation "soxl-v2-history-publication/1"、sourceとmodeの固定の対応、publication_hash＝bodyの正規化JSONのSHA-256。committedは常にFalse。summary・reprはホワイトリストだけ。
- **バイト**（設計§5.1）：history_bytesは正規化UTF-8（BOM・末尾改行なし）。read_history_bytesは`bytes`だけ、BOMを取り除かない厳格な読み、既存decode_history・validate_history。正規化されていない有効なテキストを受け付ける。raw_identityは受け取ったバイトからhashlibで計算する。hashlibはread.pyだけ。
- **CAS**（設計§5.2）：検査の順序（公開値→今→候補）と各拒否のcode・rule。check_publicationは計画を確認し直さない。
- **照合**（設計§5.3）：4つの結果と条件、判断の順序（REPLACEの「元のまま」を先に）、内容の問題は値で返す。Reconciliationはoutcomeとpublication_hashだけ。
- **P-02**（a6340c3 §4の規則1〜3と規則4の識別値の部分）：採用はCONFIRMED_IN_MEMORYだけ、expectedは受け取ったバイトから計算し計画の値は一致を確かめるだけ、bodyに`discarded`・`diagnosis_digest`（その名を含むキー）を持たない。採用計画のbasisの`discarded`・`diagnosis_digest`を読まない。
- **戦略式を書かない**：閾値・比率・状態の式・台帳の判定規則・記録の作り方を複製しない。
- **範囲試験**（設計§6）：C-2の範囲試験は`START = "de6549a…"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。前の段階の差分を固定文字列で書き写さない。test_c1_09の2行はC-2自身の差分のハンクとして固定する。自分のファイルの範囲の値はHEADのテキストで確かめる。

## 4. 受入条件 C2-01〜C2-19

各IDは機能項目であってテスト件数ではない。新規Nは実測する。期待値は既存の関数（check_append_batch、各確認の結果、hashlib）や試験側の独立の計算から作り、実装の出力をコピーしない。

| ID | 必須確認 |
|---|---|
| C2-01 回帰 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165、B-5a 131、B-5b 170、範囲の鎖34、C-1 112の計1780件を、完全なクローンで維持（test_c1_09の2行の補正を含む。件数は同じ） |
| C2-02 値 | HistoryPublicationとReconciliationの不変性（属性の設定・削除の拒否、受け取った値・返す値のコピー）、bodyの14キー、operation、sourceとmodeの対応、publication_hash、committed=False、from_dictが無いこと、summary・reprに市場値・F&G・決定・自由文・ファイル名が出ないこと |
| C2-03 DAILY | 候補がprepare_history_dayのbatchをcheck_append_batchで受け入れた結果と同じ。recordsがbatchのrecordsと同じ文字。NO_COMMIT・ALREADY_APPLIEDはnot_prepared。日付・入力の誤りは既存のcodeのまま |
| C2-04 RESOLUTION | 候補が確認結果と同じ。request_id・plan_hash。NO_CHANGEはno_change。確認hashの誤り・計画の改変・入力の変更は既存のcode（history_plan_mismatch／stale等）のまま |
| C2-05 RESTART | 同上（confirm_restart_plan） |
| C2-06 RESTORE | 同上（confirm_restore_plan）。C-1のCONSUMEを含む例を少なくとも1つ（recordsが復元記録と作られたAPPLY） |
| C2-07 GENESIS | CREATE、candidate_historyがGENESISだけの履歴、make_history_genesisの拒否はそのまま |
| C2-08 MIGRATION | snapshot.jsonのバイトから。UTF-8・JSON・snapshotの誤りはS2と同じcode（snapshot_invalid等）。source_v1が受け取ったバイトの識別値。確認の拒否はそのまま |
| C2-09 ADOPTION | 元バイトでのCONFIRMED_IN_MEMORYだけで作る。候補のバイトを渡したNO_CHANGEはno_change。expectedが受け取ったバイトのsha256・長さ（試験側でhashlibで計算）。bodyに`discarded`・`diagnosis`を名に含むキーが無い |
| C2-10 P-01 | C-1レビュー§4.5の履歴（検査器は受け付け、計画はrestore_consume_not_releasedで拒否）について、(a)正しい計画のbasisをその履歴に書き換えてhashを付け直した計画、(b)その履歴を持つRestoreConfirmResult、のどちらを渡しても公開値にならない。publish_\*の一覧が7つで、Historyを受け取る関数が無い。`_make`の呼出しがbuild.pyだけ（静的） |
| C2-11 CAS | 書き方ごとの成功と、absent・present・head・raw・source_v1・current_type・source_v1の誤用の各拒否。公開値のhash・形・records・候補digestの改変（hashを付け直した改変を含む）の拒否。字下げ付きの有効なバイトの受け付け。BOM・UTF-8の誤り・壊れたJSON・無効な履歴は既存のhistory_invalid。検査の順序（公開値の誤りは今より先、今の誤りは候補より先） |
| C2-12 照合 | 書き方ごとの4つの結果：前・後・後に記録が続く・無い・読めない・別の履歴。REPLACEで元の壊れたバイトがNOT_PUBLISHED。中身の問題で例外を出さない（公開値の誤りだけ拒否）。PUBLISHED_THEN_EXTENDEDの判定が物理prefixのdigestによる（記録のhashの一致だけで判定しない：候補の最後の記録と同じhashを持つ別のprefixを作る合成入力で確かめる） |
| C2-13 バイト | history_bytesがencode_historyのUTF-8と同じ。read_history_bytesが`bytes`以外（str、bytearray、memoryview、None、サブクラス）を拒否。raw_identityの値 |
| C2-14 例外の漏れ | 公開値・今・v1のバイトのどの改変でも、AttributeError・KeyError・TypeError等の想定外の例外が出ない（固定のcodeだけ） |
| C2-15 P-02 | v2_history_publishがv2_history_diagnoseを直接importしない。"discarded"・"diagnosis"の語を名前・文字列に持たない（docstringを除く）。採用計画のbasisから読むキーがrequest_id・raw_sha256・raw_sizeだけ |
| C2-16 範囲の値 | test_c1_09のENDがde6549aで、差分は§2の2行だけ。範囲の鎖がadfdf765→…→bfbde7a→de6549a→（C-2、END=None）で、開いた範囲はC-2の1本だけ |
| C2-17 自分の範囲 | de6549a→REVで、Mはtest_c1_09だけ（2行のハンクと一致）。Aはv2_history_publish/、tests/v2_history_publish/、結果文書だけ。それ以外はblob単位で同じ |
| C2-18 範囲監査 | 新しいランタイムに、ファイル・パス・時計・乱数・ネット・スレッド・環境変数・プロセス、新しい依存が無い。hashlibはread.pyだけ。importは設計§2.3の一覧の中。既存パッケージの公開名が不変。新しい試験はネットワーク・書込み・時計・乱数を使わず、作業ツリーのファイルを書かない |
| C2-19 次の段階の模擬 | 使い捨てのコミットでC-2の範囲試験の`END`だけを自分の最終SHAに替え（1行）、新規の全試験と範囲の鎖が通ること。結果文書に手順と結果を書く（そのコミットはpushしない） |

## 5. 限定欠陥注入

次の項目を1件ずつ壊し、試験の感度を確認する。検出・等価・未検出・準備失敗を分け、等価には根拠を書く。

1. 作り方：採用のNO_CHANGEからも公開値を作る（statusの確認を外す）。
2. 作り方：DAILYでPREPARED以外（ALREADY_APPLIED）からも作る。
3. 作り方：APPENDの「候補が今の延長」の確認を外す。
4. 作り方：RESOLUTIONで確認結果のhistoryとの一致を外す。
5. 作り方：採用のexpectedを計画のbasisのraw_sha256・raw_sizeから写す。
6. 作り方：採用の公開値のbodyに計画のdiscardedを足す。
7. 作り方：Historyを受け取るpublish_historyを足す（または公開値にfrom_dictを足す）。
8. CAS：publication_hashの確認を外す。
9. CAS：APPENDの先頭の比較からhead_hashを外す。
10. CAS：REPLACEの生バイトの識別値の比較を外す。
11. CAS：CREATEで今があっても受け付ける。
12. CAS：MIGRATIONのsource_v1の確認を外す。
13. CAS：候補のdigestの比較を外す。
14. 照合：読めない今をNOT_PUBLISHEDにする。
15. 照合：PUBLISHED_THEN_EXTENDEDを、物理prefixのdigestでなく候補の最後の記録のhashの一致だけで判定する。
16. 範囲試験：新しい範囲試験が作業ツリーを読む（REVでなくopen）。
17. 範囲試験：test_c1_09の補正の固定行を1行変える。
18. 範囲試験：自分のファイルの範囲の値をREVから読む（C2-19の模擬で検出されること）。

## 6. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使う。依存/設定/workflowを変更しない。
core.autocrlf=falseの別クリーンクローン（完全な履歴）で最終コードを試験する。`git archive`のツリーでのskipの件数は別に記録する。`git add`前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
Windowsがある場合は新規N＋C-1 112＋範囲の鎖34＋B-5b 170＋B-5a 131＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行する（合計は新規N＋1304）。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_publish -p "test_c2_*.py" -v

結果文書には、実モデル設定/effort、固定資料の完全SHA/3つのblob、開始/試験/最終SHA、新しいランタイムの全文の場所と行数、test_c1_09の差分全文、試行の差分（設計§7）との違いとその理由、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、変異一覧・分類、C2-19の手順と結果、未実施を記す。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、C-3・C-4へ進まない。

## 7. 読取専用の保護参照

次の73参照を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した資料ブランチdocs/v2-history-publish-c2-20261103も、受け取った版の完全SHAを1本加える（実装時は74参照）。

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
| docs/v2-consume-c1-review-20261103 | b473db46ad3dbf3ad76fa76f50c49b03b558936d |
| docs/v2-consume-s3c-20261103 | a6340c3937092e4cb658913b9acfb4973a084326 |
| feat/v2-history-consume-c1-20261103 | de6549acb4ecea759cc771300fd0bef59dd5456a |

## 8. 採用単位

設計§8のD-1（C-2の範囲）、D-2（作り方とP-01）、D-3（公開値の形）、D-4（バイトの形と読み方）、D-5（照合）、D-6（P-02の規則1〜4）、D-7（範囲試験）、D-8（C-2の限定実装、Sonnet 5.5・high）と、本書の変更境界/受入/欠陥注入/結果保存を一組で判断する。
今回の文書作成と、設計§7の一時環境の試行は、その採用ではない。C-1の受領をC-2の実装承認にしない。C-3・C-4の実装承認も含まない。
