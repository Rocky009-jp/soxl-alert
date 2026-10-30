# V2 S3-B-3 UNKNOWN再開始 限定実装依頼案

作成日：2026-10-30（日本時間）。版：第2版（同日のレビューN-01〜N-03と提案P-01〜P-05を反映、§9）。
状態：**第2版・レビュー待ち・限定実装は未承認。**
ユーザーが承認したのは設計・依頼書の作成まで。本書§8の一組を明示採用されるまで実装・試験を開始しない。

## 1. 固定入力・担当・開始点

| 用途 | 固定版 |
|---|---|
| コード開始点 | **b328844fdeda235cf95bf7851ba9e3d7d55aa7bb**（コード・試験は4ed0c364bcc1c63b44be07349880b741936d8b77と同じ） |
| 設計 | 本書と同じ固定コミットのdocs/specs/V2_RECOVERY_S3B3_RESTART_UNKNOWN_DESIGN_DRAFT.md |
| 初版 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c。実装根拠は本第2版とする |
| 初版レビュー原文 | 本書と同じ固定コミットのdocs/reviews/V2_RECOVERY_S3B3_REVIEW_20261030.md |
| B-2受領 | 5743732781523ab60f1025037d99410a41285de8、docs/reviews/V2_RECOVERY_S3B2_FIX_RECEIPT_20261030.md |
| 上位S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md、blob 838761207b060ca8c844bf7ed0f15a9e990ad6b7 |
| B-2設計第2版 | e083cd3187f17692cb081fcc1031b09551fb8cb7、docs/specs/V2_RECOVERY_S3B2_PROJECTION_DAILY_DESIGN_DRAFT.md、blob 988258c798ee2d867c86238db1c4f426a360dda2 |

実装担当の推奨は**Claude Sonnet 5.5、effort high**。固定した純粋な計画・確認と既存への回帰確認であり、戦略や会計の変更を含まないためである。採用後にセッション情報で実設定を確認し、確認できなければ不明と記す。独断でモデルを替えない。

CLAUDE.md、STATUS、MODEL_POLICY、ROADMAPの必要箇所と、今回の採用記録を読む。古い未承認表記でB-2の採用を取り直さない。
新規実装ブランチ例：feat/v2-history-restart-s3b3-20261030。コード開始点から作り、同名があれば上書きせず別名。資料コミットをコードへ丸ごとcherry-pickしない。
渡されたパーマリンクの完全SHAと設計・依頼の両blobを記録し、途中で新しい資料へ追従しない。

## 2. 許可する変更（採用後だけ）

| 場所 | 内容 |
|---|---|
| v2_history_restart/ 新規 | 設計§3の2関数・2型・3定数と内部の純粋処理。既存の公開名とcopy／jsonだけを利用 |
| tests/v2_history_restart/ 新規 | B3-01〜B3-16、限定欠陥注入。新規試験はtest_r3_*.py、ヘルパーはr3_helpers.py。__init__.pyは置かない。既存h_helpers／ho_helpers等は読取りimportだけ |
| tests/v2_history_ops/test_b17_scope.py | 設計§2.4のFilesChangedの3箇所だけ。新規B-3の2ディレクトリ・結果文書の許可、旧試験無変更のGit検索から新規B-3試験の除外、同じ関数末尾の__init__.py検査にv2_history_restart/__init__.pyの単一パスだけを追加例外とする。機能試験・旧ランタイムのAST検査・禁止機能・公開名は変更しない |
| docs/implementation/V2_RECOVERY_S3B3_RESULT.md 新規 | 結果記録。旧B-2結果文書には追記しない |

上記以外の既存ファイルは変更しない。v2_core／v2_persistence（local含む）／v2_recovery／v2_history／v2_history_opsの既存ランタイム、既存試験・変異スクリプト・fixtures・基準データ、依存、設定、workflow、main.py、研究、STATUS／ROADMAP／CLAUDE等は固定する。

特にHistoryAppendBatchのsourceを増やす、RESTARTをRESOLUTIONとして渡す、旧ストアを対応させる、private関数を呼ぶ、検証済みと偽ったCtxを作ることを禁止する。LedgerContextの追加不変化は行わない。
範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更は行わない。

## 3. 固定する振る舞い

- 元履歴を検査し、floorは有効履歴全体から読む。退避したAPPLY・宣言・再開始で下限を上げない。
- floor・上限・無効果の拒否を保ち、resume_after==check_dを受理する。境界は注入sessionsに存在しconfirmed=True。prepareの指定ミスはrestart_invalidとし、field／ruleは設計§5・§10。入力履歴や候補自体のvalidate_history失敗と混同しない。
- 元履歴の全区間投影を既存project_history_ledgerへ委譲する。旧APPLYの食い違い・skipped／宣言日の後発を初期化で隠さない。生台帳は変えない。
- RESTART_UNKNOWNは既存の15キー。物理先頭へ1件だけ付け、過去events・有効／退避情報・移行情報を変えない。state_afterはMarketState.initial().to_dict()。
- 候補はvalidate_historyと設計§8の保存内容の不変検査を通す。候補をcheck_dでB-2へ投影し直すことは要件にしない。未来の架空check_dで代用しない。
- 計画はREADYのみ。prepareでの既存IDは内容・種別・有効／退避を問わずconflict。NO_CHANGEは同じ元計画を候補そのものへ再確認する場合だけ。設計§4の5段階のエラー優先順位を保ち、旧境界・保存文脈の差はID照合より後で検出する。
- 確認は「計画自身→入力そのもの→digest／head→元履歴からbasis全体を再構築」の順。枝Bでは物理prefixを完全検査して元履歴を復元する。B-2の4項目変更方式を写さない。
- 戻り値は不変。未検証の値も含め全アクセサから内部の可変参照を出さず、表示前に許可した値の形を再検査する。
- 確認結果にbatch／ledger属性を付けない。committed／committableはFalse。確認は保存ではなく、どの値も旧MemoryStore／LocalFileStoreではplan_typeで拒否される。

## 4. 受入条件 B3-01〜B3-16

各IDは機能項目であり、テスト関数の件数ではない。新規Nは実測し、増えた件数だけで品質を主張しない。

| ID | 必須の確認 |
|---|---|
| B3-01 回帰・差分 | 既存コア197、保存ドメイン170、S3-A176、B-1 230、B-2 173を維持。S2 113はOS契約どおり。旧機能試験は無編集、旧範囲試験1ファイルの限定補正は別掲。旧ランタイム・fixtures等のGit差分0 |
| B3-02 有効floor | APPLY／DECLAREの最大日と現在境界を全区間から取る。RESTOREで退避した記録により下限やセッション制約を増やさない。宣言だけが最新、初期状態＋宣言、再開始を複数回含む場合を含める |
| B3-03 下限・上限・無効果 | floor各成分の未満はrestart_invalid／resume_after／restart_floor、resume_after>check_dはrestart_invalid／check_d／check_d。初期状態かつ同境界はrestart_invalid／resume_after／restart_noop、初期状態で境界を前進させる場合はREADY。resume_after==check_dは準備・確認・再確認すべて成功。旧文脈差とfloor未満が重なればfloorの拒否を優先 |
| B3-04 sessions | resumeの不存在／未確定はrestart_invalid／resume_after／restart_boundary。check_dの不存在／未確定／前後不足は設計§10の既存InputError、旧境界・旧APPLY／宣言の文脈差は既存session_context_missing／mismatch。sessions=Noneや不正な台帳行と使用済みIDが重なれば、IDより既存入力エラーを優先。check_dの次のconfirmed=Falseでも正常例を作る。元履歴のnext(D)のclose_at／confirmedの無害な変更とopen_atの有害な変更を区別 |
| B3-05 元履歴の照合 | project_history_ledgerの実呼出しをspyで確認。旧APPLYの変更はledger_mismatch、旧skipped／宣言の後発はlate_observationなど既存エラー。適切なB-2 ACKの後は成功。全行解析・record_id_conflict・version_selectionを省かない |
| B3-06 記録・候補 | 15キー・hash・5キーrequest_basis、20キーplan basisを固定。過去eventsの完全一致、追加1件、有効seqは元＋新、退避seq不変、現在状態初期、validate_historyの実呼出しを示す |
| B3-07 物理先頭 | 親がAPPLY／ACK／DECLARE／MIGRATION／RESTORE／RESTARTでも受理。現在区間の最後のAPPLYを親にしない。移行後のmigrated_sourcesは元のv1二値のdigestと一致 |
| B3-08 ID | 新IDだけREADY。同ID同内容／requested_atだけ変更、NATIVE／REPLAYED／MIGRATED、退避だけのID、他種別のIDはconflict。同じ計画の再確認との対照を置く。旧境界の時刻差と使用済みIDが重なればhistory_request_conflict、同じsessionsで未使用ID・有効floorならsession_context_mismatchになる対照を固定。例Rの使用済みIDを都合で変更しない |
| B3-09 計画の結合 | plan_hashはbasis全体に結び付く。basisの各項目・候補・floor・境界・確認hashの改変、hashだけ付け直す場合も拒否。同一入力同一時刻は同hash、時刻だけ変えるとrequest_hashのみ同じ |
| B3-10 確認A | 元履歴でCONFIRMED_IN_MEMORY、入力やplanは不変。正常に変えた履歴・台帳・sessionsはstale。不正な履歴・行・sessionsは既存エラー優先。全digest一致後の再構築不一致はmismatch |
| B3-11 確認B | 候補そのものへ同計画を渡してNO_CHANGE、2件目なし。resume==check_dを必ず含める。元の物理prefixをvalidateし元digest／head／stateとも照合することをspy・拒否例で確認。候補より先の履歴はstale |
| B3-12 日次接続 | 計画から作った例U候補を既存B-2へ渡す。境界以前拒否、F&G3帯、初回gap=false、欠測日のskipped、後発は停止、再実行ALREADY_APPLIED。新実装に戦略式がないこと |
| B3-13 ACK・宣言後 | resume_after==check_dの再開始直後、そのcheck_dで新しいACK／DECLAREを作るとtarget_not_after_boundary。境界より後で確定したセッションを新しいcheck_dに明示してから作る。追加後も境界は動かず、最初の宣言のfrontierはresume。旧区間へのACK／LATE、旧APPLY／skipped／宣言の照合が続く |
| B3-14 不変性・秘匿 | 入力と全戻り値、未検証のbasis／plan_hashのdict・list、スカラーへ偽のコンテナを入れた値の参照共有がない。深いJSON・巨大整数は固定エラー、bool／float整数は読込後の確認で拒否。repr／summary／エラーにURL・F&G・自由文・パスなし |
| B3-15 型の境界 | plan／result／candidate History／dict等は旧MemoryStoreと空の一時rootのLocalFileStore（file_sync_only）に渡してplan_typeで拒否。ストアの内容・先頭・残留物は変化なし。新APIにbatchがない |
| B3-16 範囲・停止 | 新ランタイム全体のASTで許可import・I/O等の不存在を検査。既存private・Ctx代用品・B-4/B-5/S3-Cなし。旧B2範囲試験の変更は設計§2.4の3点だけ。新規パッケージの__init__.pyを含む全ファイルを最終コミットへ含め、旧末尾検査も通ることを確認。新規の範囲試験はb328844からの差分を列挙し、この3点以外の旧試験の緩和や対象漏れを検出 |

B3-03／B3-11の等号ケースでは、未確定の未来セッションを確定扱いにせず、注入されていない日付・時刻を補わない。
B3-12／B3-13は既存B-2の関数で確認する統合試験で、新しい日次・ACK実装を作る指示ではない。

## 5. 限定欠陥注入

次の18項目を1件ずつ壊し、新規回帰が区別できるか確認する。複数変種ならIDと実件数を別掲。未検出を根拠なく等価にしない。等価なら成立する範囲と対照の検討を示す。過去の27件・13件・S3-A変異等を自動で再実行しない。

各検出は「B-3自身の事前検査で検出」「既存validate_history等の独立した防護で検出」「必須の委譲呼出しの契約をspyで検出」を区別して記録する。特に1〜3・8〜10は、B-3の検査を壊してもB-1がrestart_floor／parent／state_after等で止め得る。指定ミスの期待restart_invalidがhistory_invalidへ変わる等、codeや優先順位の変化を記録し、誤った候補が受理されたことと混同しない。

1. floorを物理配列から計算し、退避した最大日を入れる。
2. floorから有効な旧区間のAPPLYまたは宣言を落とす。
3. prev_boundaryを無視する。
4. 初期状態同境界のrestart_noopを受理する、または境界前進まで拒否する。
5. resume_after==check_dを拒否する。
6. 新境界の存在・confirmedを検査しない、または別の同日セッションの時刻を使う。
7. 元履歴のproject_history_ledgerを省く。
8. 親を物理先頭でなく最後のAPPLYにする。
9. state_afterへ親の状態をコピーする。
10. 過去eventsまたは有効／退避の列を変更する候補を通す。
11. 候補のvalidate_history、または保存内容の不変検査を省く（呼出し契約と挙動の検出を区別）。
12. request_idを有効鎖だけで照合する。
13. prepareで同ID同内容をNO_CHANGEとして受理する。
14. 確認でplan_hash／いずれかの入力digestを無視する。
15. 不正な入力をstaleへ変換する。
16. 候補の再確認をstaleにする、または2件目のRESTARTを追加する。
17. 枝Bで元prefixの検査・元digest照合・basis完全再構築のいずれかを省く。
18. planのbasis／plan_hash等のアクセサで入れ子の参照を共有する。

## 6. 環境・保存・停止

Python3.10／3.11／3.12／3.13、完全な版を記録。既存の隔離環境を使い、必要な場合だけスクラッチのuv単体Pythonを使う。依存・設定・workflowは変更しない。
通信禁止、使えるLinuxではunshare等とプロセス内socket禁止を区別。core.autocrlf=falseの別クリーンクローンで最終コードを試験する。

既存ヘルパーが他の試験ディレクトリをsys.pathへ加えるため、新規試験ファイルはtest_r3_*.py、ヘルパーはr3_helpers.pyとし、既存の同名モジュールが無いことを確認する。tests/v2_history_restart/には__init__.pyを置かない。

新規スイート例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restart -p "test_r3_*.py" -v

既存は合計1059件（Linuxでは1055合格＋Windows専用4 skip）をスイート別に記録し、新規Nと分ける。B-2の173件では範囲検査1ファイルの補正だけがあり、全既存試験が無編集とは報告しない。Windowsがあれば新規N＋B-2 173＋S3-A176＋B-1 230＋S2専用4件を実行し、Linux strict前提のS2全探索はしない。未実施のOSやユーザーPCを合格に含めない。

結果文書には、モデル実設定・固定資料SHA／両blob、開始SHA・試験対象SHA・保存最終SHA、全差分（旧範囲試験の差分全文）、受入とテスト名の対応、各スイートの件数・error・failure・skip・終了コード、候補と再確認の例、変異全一覧と分類、解釈した点・未実施を含める。B-3は候補までで、上位§9のバッチ統合・保存・耐久性を達成していないと明記する。成否不明時の計画保持・ALREADY_PUBLISHED相当の照合、後工程で旧範囲試験の見直しが再び必要になる点は、設計§2.4・§7の留保どおり記録する。

最後のコードと試験のSHAを固定してクリーンクローンを確認し、その後結果文書だけを新コミットへ足す。自分の新規実装ブランチだけをpushし、最後の差分が結果文書1本であることを確認して報告・停止する。
PR・マージ・Actions・本番・通知、B-4以降・S3-Cへ進まない。

## 7. 読取専用に固定する参照

次の45参照（初版まで）を開始時と保存・push後の終了時にそれぞれ完全SHAで照合する。本第2版・レビュー原文を保存した資料ブランチも、渡されたパーマリンクの完全SHAを追加して固定する（将来の実装時は計46参照）。表の既存参照を更新しない。

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

## 8. 採用する単位と現在の停止位置

設計§12のD-1（候補Historyまでの範囲、新パッケージ、旧範囲試験の限定補正）、D-2（既存IDはprepareで一律拒否・同じ計画の再確認はNO_CHANGE）、D-3（Sonnet 5.5・high）と、本書の変更境界・受入・通信禁止・結果保存を一組として採否判断する。

本書を保存したことはその採用ではない。今回の作業は2文書の作成だけで停止し、採用後に別ブランチで限定実装する。B-1／B-2の採用済み事項や、売買戦略・本番保存先・資格情報を再質問する依頼ではない。

## 9. 第2版の改訂

初版f90c2e6へのClaudeレビューを、同じ固定コミットのdocs/reviews/V2_RECOVERY_S3B3_REVIEW_20261030.mdへ取得した本文のまま保存する。N-01の試験実行はレビュー担当の報告であり、本補正でのコード変更・試験実行は0。

| ID | 本書の反映 |
|---|---|
| N-01 | §2・B3-16でFilesChangedの補正を3点にし、末尾の__init__.py検査の単一パス例外を追加。tests側に__init__.pyを作らない |
| N-02 | §3・B3-03／B3-04で指定ミスのcode／field／ruleをrestart_invalidへ分離。既存履歴・候補の検査器は変更しない |
| N-03 | §3・B3-03／B3-04／B3-08で設計§4の優先順位と重複エラー時の対照を固定 |
| P-01 | §6で計画保持・公開後の照合はS3-Cへ留保。任意のconflict rule細分化は今回追加しない |
| P-02 | §6で後工程の範囲試験の見直しが必要になる点を記録。後工程を先に許可しない |
| P-03 | B3-13で等号再開始後の新ACK／DECLAREには新しい確定check_dが必要と明記。旧問題の事前解決・無所属decisionの扱いは設計§5に説明 |
| P-04 | §5でB-3自身・既存検査器の防護・呼出し契約による検出を分けて報告 |
| P-05 | §2・§6で新規試験名とヘルパー名を固定 |

受入ID B3-01〜B3-16、欠陥注入18項目、コード開始点b328844、公開API・15／20キー、候補Historyまでという境界、D-1〜D-3の未採用・実装未承認は維持する。
