# V2 S3-B-4 復元計画・確認 限定実装依頼書

作成日：2026-11-02（日本時間）。版：第1版。
状態：**レビュー待ち・未承認。本書の保存だけでは実装を始めない。**

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **d82a5ced64658c2e736b82b1a2f1925636055417**（feat/v2-history-restart-s3b3-20261102） |
| コード・試験の同値版 | 7d75ea5dbee1f6cef9912fceced2c2be2e48fad9。d82との差はB-3結果文書1本 |
| 対になる設計 | docs/specs/V2_RECOVERY_S3B4_RESTORE_PLAN_DESIGN_DRAFT.md。本依頼と同じ資料コミットを固定し、SHA・両blobを開始報告に記録 |
| B-3受領 | 78b9b405cebfb37283bf59f35d7774ad6910b331、docs/reviews/V2_RECOVERY_S3B3_IMPLEMENTATION_RECEIPT_20261102.md |
| 上位S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md |

ユーザーが設計§14のD-1〜D-3を採用し、B-4限定実装への移行を指示した後にのみ、新規実装ブランチをd82a5ceから作る。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high。仕様固定後の純粋な計画・検証・試験の実装であり、会計・戦略・保存方式の再設計は含まない。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。古いSTATUSの承認待ちを、B-3までの採用を取り直す指示とは扱わない。未承認のD-1〜D-3は採用されたと書かない。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history_restore/ 新規 | 設計の2関数・2型・3定数。公開名7名、候補Historyまで。必要な内部モジュールもこの内側 |
| tests/v2_history_restore/ 新規 | test_r4_*.py、r4_helpers.py、限定変異を保存する場合はr4_sensitivity.py。__init__.pyは作らない |
| tests/v2_history_ops/test_b17_scope.py | §3の限定補正だけ |
| tests/v2_history_restart/test_r3_07_scope.py | §3の限定補正だけ |
| docs/implementation/V2_RECOVERY_S3B4_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence（local含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restartの既存ランタイム、既存機能試験/変異/fixtures/基準データ、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
CONSUME、B-5、S3-C、ストア、batchの一般化、保存、公開、解錠、CLI、通知・本番接続へ広げない。既存private名やテストビルダーをランタイムへ取り込まない。
範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 旧範囲試験2本の限定補正

B-2はadfdf765、B-3はb328844からHEADまでを見るため、新B-4の追加だけで旧試験が失敗する。下記だけを変更する。既存機能試験/期待値、AST/公開名/禁止機能の検査、各test関数の件数は維持する。

### 3.1 B-2 test_b17_scope.py：FilesChanged内の3点

1. test_only_the_allowed_paths_differの既存許可リストへ、新規v2_history_restore/、tests/v2_history_restore/、新結果V2_RECOVERY_S3B4_RESULT.mdだけを追加。
2. 同関数末尾の__init__.py検査は、既存B-3例外を保ち、**v2_history_restore/__init__.pyの単一パス**だけを追加例外にする。tests側や他パッケージの__init__.pyを一括許可しない。
3. test_existing_tests_and_fixtures_are_untouchedのGit検索から新規tests/v2_history_restore/も除外する。B-3の除外は既存のまま。既存commands.py差分の検査は無変更。

### 3.2 B-3 test_r3_07_scope.py：FilesChangedの次の3メソッドだけ

| メソッド | 許可する補正 |
|---|---|
| test_only_the_allowed_paths_differ | 既存B-17のM例外に加え、このB-3範囲試験自身の1パスをMとして認める。新規B-4の2ディレクトリ/結果文書をAとして追加。累積差分の__init__.py集合は従来B-3の1パスと新B-4の1パスの**2つだけ**にする |
| test_no_existing_runtime_old_test_fixture_or_setting_differs | 旧ランタイム・設定の差分0を維持。testsの検索から新規B-4 testsも除外し、残る旧試験の差分をB-17と本ファイルの**2パスだけ**に固定 |
| test_the_old_range_test_differs_in_exactly_the_three_allowed_places | b328844→HEADのB-17累積差分の期待リテラルを、B-3の既存3点＋今回§3.1のB-4分に更新。許可する意味上の箇所は同じ3点。削除/追加行の厳密照合とハンク数の照合を維持する。期待値を現在のB-17から動的生成して一致させない |

B-3のSTART、Runtime全メソッド、import/公開名/禁止機能/ファイル構成の検査、r3_helpersは変えない。B-3自身のscope変更を新B-4のscopeが厳密に監査する。
具体的な行折り返しは上記意味を変えない範囲でよいが、結果文書には2ファイルの差分全文を載せる。新B-4 scopeには基準d82a5ceに対する期待差分を静的に固定し、既存assertの削除やskip/START変更・HEAD偽装を検出する。実装者が変更後ファイルを丸ごと期待値として読んで自己承認する試験にしない。
パス判定の対照として、tests/v2_history_restore/__init__.py、既存パッケージの__init__.py変更、3本目の旧試験変更、範囲外の新規ファイルを拒否することも新規試験で確認する。B-5/S3-Cを先に許可リストへ入れない。

## 4. 固定する振る舞い

- validate_historyした元履歴から、有効なPと有効なsuffixを選ぶ。物理区間による退避・退避済み点への再接続・移行前復元・request部分処分を拒否する。
- Pが旧復元バッチの途中のAPPLYである場合を許す。そのPで物理配列を切った不完全Historyに検査を要求しない。
- 4処分だけ。APPLYは保存decision/市場値のREAPPLYだけ。CONSUMEは拒否し、§8のreleased_daysで新規消費が必要ならrestore_requires_consumeで止める。後続APPLY無し・新基点UNKNOWNも対象。
- 二段階で意味内容/replayを決めてからhashを結ぶ。過去物理eventsを完全保持し、1件のRESTOREと全生成記録をまとめた候補だけを返す。
- 新stateは既存apply_transition、現在seriesとの検証は既存evaluate_dayを使う。戦略式/閾値/状態式をコピーしない。保存値の自動置換・許容差を入れない。
- REPLAYのstate_after、DECLARE frontier/context、RESTART floorを新鎖で計算し直す。参照は直接の元記録から1回写し、依存先をDROP/RETIREした場合は自動で落とさない。
- 設計§7の実物のFixedFacts/LedgerContext/check_commands/apply_records/check_versionsだけを橋渡しに使い、最後は変更しないB-2 project_history_ledgerへ委譲する。事前集合と最終照合済み結果を混同しない。
- 元履歴の**内部検査**は必須。元履歴への**現在台帳の最終投影**を先行必須にせず、DROPすべき旧制御記録が計画を妨げないようにする。候補で残る全事実の照合は省かない。
- 新IDは物理全体で未使用だけ。NO_CHANGEは保持した同計画を完全一致candidateへ再確認する場合だけ。無効果は計画で拒否する案（D-2採用後）。
- 不変性・安全な表示・23キーbasis・15キー記録・入力digest・エラー優先順位・確認の完全再構築は設計どおり。batch/ledger属性は作らず、committed/committable=False。

## 5. 受入条件 B4-01〜B4-20

各IDは機能項目であってテスト件数ではない。新規Nは実測する。

| ID | 必須確認 |
|---|---|
| B4-01 回帰・変更境界 | 既存コア197、保存170、S2 113、S3-A176、B-1 230、B-2 173、B-3 109の計1168件をOS契約どおり維持。既存機能試験無編集、scope2本の限定補正は別掲。既存ランタイム等差分0 |
| B4-02 復元点 | 新規GENESIS/移行MIGRATION自身を受理可能、移行より前・head・退避済み・hash違い・request途中を拒否。厳密intでbool/floatを拒否 |
| B4-03 有効suffix | 2回/3回復元後のsuffixが物理区間と異なる例で完全一致。既退避点の重複退避を拒否。旧復元バッチ途中の有効APPLYをPにする正常例 |
| B4-04 ops | 過不足/順序/重複/未知キー、種別違反、request部分DROP/REPLAYを拒否。CONSUMEと未知opはrestore_op_unsupported。自動ソート/補完無し |
| B4-05 同一入力のREAPPLY | 元decision/row/prev_row/prev_session_date完全保持。新baseからapply_transition。現在seriesによるevaluate_dayと一致。元state/transitionのコピーを検出 |
| B4-06 現在入力の相違 | 市場値だけの変更は判定が同じでもrestore_market_input_changed。decision不存在/別ID/指紋違いはrestore_decision_changed。選択の衝突は既存コード。CHANGED/ROW_REMOVED補完による保存decisionの選択は成功例 |
| B4-07 セッション | 全中間confirmed、prev日、共通context、境界の実注入列一致。next(D)のclose/confirmedだけの差は新計画の文脈/input_hashに無害、open/日付/中間未確定は停止。check_dのnextのみ未確定は成功 |
| B4-08 新規消費の停止 | DROP宣言、DROP再開始の免除区間、新skippedの各released_daysで有効decisionを検出。APPLYが後に無い場合・base.as_of_d=nullも停止。無関係な未適用日は勝手に消費せず、旧skip後発は既存late_observationになる対照 |
| B4-09 REPLAY参照 | retained/REAPPLY/REPLAYへの写像、DROP/RETIRE依存の拒否。移行・既再生記録で二重写像しない。元request系、origin/旧ledger_digest維持 |
| B4-10 REPLAY再計算 | 新親state_after、DECLARE frontier/context、RESTART floor/初期状態。R-bとRESTART再生の対照。元stateコピー+hash付け直しを拒否 |
| B4-11 証拠と版 | 各REPLAY requestグループの直前有効prefixを実FixedFactsにし、check_commands実呼出し。ROW_REMOVED+ADDEDの一括証拠、欠測宣言有効1件拒否、LATE、version_selectionの既存規則。未来APPLYをprefixへ混ぜない |
| B4-12 候補完全検査 | 旧events不変、RESTORE15キー/request_basis6キー/replay5キー、正しい監査prevと有効親、有効/退避列、新header。バッチ途中候補はvalidate_historyで拒否。完全candidateはB-2の全区間投影を実呼出し。事前行集合/digestとの一致 |
| B4-13 失敗の優先順位 | 不正履歴/sessions形/行はIDより前、P/opsはIDより前、IDは候補文脈より前。元現在投影は失敗しても、正当なDROPで整合するcandidateなら成功できる対照。plan不正は現在入力より前、入力不正はstaleより前 |
| B4-14 ID/無効果 | 物理全体の有効/退避/移行/再生/他種別ID、同内容/時刻変更をすべて拒否。未使用IDのみREADY。全REAPPLY trueかつDROP無しはrestore_no_effect、DROPありで市場state同一の正常例も固定 |
| B4-15 plan/hash/差 | 23キーbasis全項目を結合、candidate_recordsと末尾一致、series_inputsの範囲と正規化、changesの項目とsameの実値。改変/hash付け直し/確認hash違い拒否。時刻変更はrequest_hashのみ同じ |
| B4-16 確認A/B | 元履歴でCONFIRMED_IN_MEMORY、同じ完全candidateでNO_CHANGE・追加0。元物理headまでのprefix全検査と全basis再構築。別candidate/先に進んだ履歴/正常な入力変更はstale。digest一致後の再構築差はmismatch |
| B4-17 入力の範囲 | series.through(D)より後を見ない。前史改訂で対象rowが変われば停止。D後だけ/表示SOXL/descriptionだけの変更はseries_digest不変。REAPPLYが0ならseries=Noneを参照しない |
| B4-18 不変性/秘匿/型境界 | 未検証planの全アクセサ・コンテナhashに共有無し。JSON深さ/巨大整数/非有限/非str鍵を固定エラー。repr/summaryにURL/市場値/F&G/自由文/パス無し。旧Memory/LocalFileStore(file_sync_onlyの一時root)はplan/result/History/dictをplan_typeで拒否し、保存や残留物無し |
| B4-19 統合例 | 設計§13の各例を実際の台帳/seriesで実行。上位例R/R-bの3回復元、退避内の旧RESTORE RETIRE、元ID保持、sameの入力依存を示す。候補を既存B-2日次へ渡し、再実行ALREADY_APPLIED/後発停止を確認。数値は旧実測を無条件コピーしない |
| B4-20 範囲監査 | 新runtime全体AST、公開依存と__all__7、I/O/時計/乱数/外部private/戦略式/CONSUME実装/B-5/S3-C不存在。scope2本の差分厳密照合と禁止パスの対照、test_r4名の一意性、testsに__init__.py無し |

委譲spyは実際に新パッケージが参照する名前を差し替える。v2_core.transition.apply_transitionだけを差し替えて、別名importの呼出しを見たと主張しない。B-1等による内部再計算回数と、新B-4自身が行う委譲の観測を分ける。
既存の構造ビルダーは試験だけで読取再利用できるが、実装の期待値を同じ新実装で生成しない。例Rのq1〜q6等は既使用の意味を維持し、新外側IDだけ未使用にする。

## 6. 限定欠陥注入

次の22項目を1件ずつ壊し、新規試験の感度を確認する。複数変種なら実件数/IDを別掲し、検出・等価・未検出・準備失敗を分ける。過去B-1/B-2/B-3の全変異を自動で再実行しない。

1. 退避済み/移行前/head/request途中のPを受理する。
2. supersededを有効suffixでなく物理区間にする、または順序を変える。
3. opsの厳密整数/完全対応/種別制約/request全件処分を緩める。
4. Pが旧復元バッチ途中のAPPLYなのに物理prefixをvalidateして拒否する。
5. 保存decisionまたは市場値を現在入力で上書きする。
6. REAPPLYのstate/transitionをコピーしapply_transitionを使わない。
7. 現在市場値比較または現在decision比較を省く。
8. next(D)の無害なclose/confirmedを有害と扱う、または有害なopen差を無視する。
9. released_daysの宣言/再開始/新skipのどれかを落とす（後続APPLY無しとnull基点の変種を含む）。
10. 元現在投影を必須にし、取消で解決するケースを拒否する。
11. 参照を写さない/二重に写す/DROP依存を黙って落とす。
12. REPLAYの親state/DECLARE frontier/RESTART floorを元からコピーする。
13. REPLAYの証拠検査を省く/グループを分断する/prefixへ未来APPLYを混ぜる。
14. version_selectionまたは除外→補完の順序を崩す。
15. 最終validate_historyまたはB-2全区間投影を省く。
16. 旧events・有効/退避列・candidate_recordsの保存不変検査を省く。
17. 無効果拒否を省く、またはDROPありの正常例まで拒否する。
18. IDを有効列だけで検査する/既存同内容を新prepareで通す。
19. plan/入力いずれかのhash/digestを無視する、seriesに未来/表示だけの値を混ぜる。
20. 再確認をstaleにする/2件目を作る/元prefix検査や全basis再構築を省く。
21. 不正入力をstaleへ変換する、または計画不正より現在入力を先に処理する。
22. 未検証planのbasis/plan_hash/summary等から可変参照や任意表示を出す。

B-4自身の事前拒否、B-1/S3-A/B-2の独立防護、委譲/順序のspyを分類する。誤った候補の受理と、エラーcodeや順序の差を区別する。冗長検査の除去で値が変わらないなら、その限定的等価性と残る防護を記録し、単に「全検出」にするためだけの無根拠なspyを足さない。固定契約で要求した委譲/順序はspyの意味を説明できる。

## 7. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使い、必要な場合だけスクラッチの単体インタプリタを準備する。依存/設定/workflowを変更しない。
runtimeの通信は禁止。Linuxで使える場合のunshareと、プロセス内socket禁止を区別する。core.autocrlf=falseの別クリーンクローンで最終コードを試験する。

既存7スイートの計1168件を別掲する。Linuxは1164合格＋Windows専用4 skip。scope2本を補正するため「既存試験が全部無編集」と報告しない。scopeのtest関数を増減しなければ旧件数は維持できる。
Windowsがある場合は新規N＋B-3 109＋B-2 173＋S3-A176＋B-1 230＋S2専用4件を実行し、Linux strict前提のS2全探索はしない。合計は新規N＋692。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restore -p "test_r4_*.py" -v

結果文書には実モデル設定/effort、固定資料の完全SHA/両blob、開始/試験/最終SHA、全差分（scope2本の全文）、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、具体的な復元前後/差/再確認、変異一覧・分類、解釈した点、未実施を記す。CONSUME保留、候補までで保存/バッチ/耐久性未達、成否不明時の計画保持・公開後照合はS3-Cであることも明記。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、CONSUME実装、B-5/S3-Cへ進まない。

## 8. 読取専用の保護参照

次の48参照を開始時と保存/push後に完全SHAで照合する。本設計・依頼を保存した新資料ブランチも、受け取った完全SHAを1本加える（初版だけなら実装時は49参照）。追加のレビュー/採用参照を渡された場合もその固定値を記録する。元ブランチを更新しない。

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

## 9. 採用単位

設計§14のD-1（CONSUME保留の限定範囲・公開API委譲・候補まで・ID方針・scope2本の補正）、D-2（計画での無効果拒否）、D-3（Sonnet 5.5・high）と、本書の変更境界/受入/通信禁止/結果保存を一組として採否判断する。
今回の文書作成はその採用ではない。B-3の受領をB-4の実装承認にしない。市場戦略、本番保存先、資格情報、旧工程の採用を再質問する依頼ではない。
