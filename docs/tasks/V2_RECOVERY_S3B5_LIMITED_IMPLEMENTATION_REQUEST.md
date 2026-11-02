# V2 S3-B-5a 破損診断 限定実装依頼書

作成日：2026-11-02（日本時間）。版：初版。
状態：**初版・レビュー待ち・未承認。本書の保存だけでは実装を始めない。**
本書はB-5のうちB-5a（診断）だけを対象とする。B-5b（RECOVERY_PREFIX_ADOPTION記録と採用の計画・確認）は対になる設計§9で境界だけを示し、ここでは依頼しない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **ac219801d290ebb59b720f37a086103b6e1251c9**（fix/v2-history-restore-plan-s3b4-review-20261102） |
| コード・試験の同値版 | 00ae4b6a69e358fd868ce1f2e9b24b14519b507e。ac21980との差はB-4結果文書§10の追記1本 |
| 対になる設計 | docs/specs/V2_RECOVERY_S3B5_DIAGNOSIS_ADOPTION_DESIGN_DRAFT.md。本依頼と同じ資料コミットを固定し、SHA・両blobを開始報告に記録 |
| B-4受領 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab、docs/reviews/V2_RECOVERY_S3B4_FIX_REREVIEW_20261102.md |
| B-4設計・依頼 | 0108131045d904b0997299fcade5929567940d6d |
| 上位S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253、docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md（§11） |

ユーザーが設計§13のD-1〜D-5を採用し、B-5a限定実装への移行を指示した後にのみ、新規実装ブランチをac21980から作る。資料ブランチから実装を始めたり、先端へ追従したりしない。
推奨担当はSonnet 5.5・high（D-5）。仕様固定後の読取り専用の診断と試験の実装であり、会計・戦略・保存方式の再設計は含まない。実モデル/effortはセッション情報で確認し、設定できない場合は事実を報告する。
CLAUDE.md等と固定資料を読む。古いSTATUSの承認待ちを、B-4までの採用を取り直す指示とは扱わない。未承認のD-1〜D-5は採用されたと書かない。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_history_diagnose/ 新規 | 設計§3の1関数・1型・4定数。公開名6名。必要な内部モジュールもこの内側 |
| tests/v2_history_diagnose/ 新規 | test_d5_*.py、d5_helpers.py、限定変異を保存する場合はd5_sensitivity.py。__init__.pyは作らない |
| tests/v2_history_ops/test_b17_scope.py | §3.1の限定補正だけ |
| tests/v2_history_restart/test_r3_07_scope.py | §3.2の限定補正だけ |
| tests/v2_history_restore/test_r4_09_scope.py | §3.3の限定補正だけ |
| docs/implementation/V2_RECOVERY_S3B5_RESULT.md 新規 | 本段階の結果。旧結果文書は追記しない |

これ以外の既存ファイルは変更しない。v2_core、v2_persistence（local含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restoreの既存ランタイム、既存機能試験/変異/fixtures/基準データ、設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等は固定する。
B-5b（8種目の記録、検査器の変更、採用の計画・確認）、CONSUME、S3-C、ストア、ファイル・パスの読み書き、CLI、通知・本番接続へ広げない。既存private名やテストビルダーをランタイムへ取り込まない。
範囲外の変更や固定文書の矛盾が必要なら、反例・影響・最小差分案を報告し、その変更を行わず止める。

## 3. 旧範囲試験3本の限定補正

B-2のb17はadfdf765、B-3のr3_07はb328844、B-4のr4_09はd82a5ceからHEADまでを見るため、新しいB-5aの追加だけで3本とも失敗する見込みである（読取りによる見込み。本書作成では実行していない）。下記だけを変更する。既存機能試験/期待値、AST/公開名/禁止機能の検査、各test関数の件数は維持する。

### 3.1 B-2 test_b17_scope.py：FilesChanged内の3点

1. test_only_the_allowed_paths_differの既存許可リストへ、新規v2_history_diagnose/、tests/v2_history_diagnose/、新結果V2_RECOVERY_S3B5_RESULT.mdだけを追加する。
2. 同関数末尾の__init__.py検査は、既存のB-3・B-4の例外を保ち、**v2_history_diagnose/__init__.pyの単一パス**だけを追加例外にする。
3. test_existing_tests_and_fixtures_are_untouchedのGit検索から新規tests/v2_history_diagnoseも除外する。既存の除外とcommands.py差分の検査は無変更。

r3_07とr4_09はadfdf765から見てAなので、既存のtests/v2_history_restart/・tests/v2_history_restore/の許可に含まれ、追加のM例外は不要。

### 3.2 B-3 test_r3_07_scope.py：FilesChangedの次の3メソッドだけ

| メソッド | 許可する補正 |
|---|---|
| test_only_the_allowed_paths_differ | 既存B-17のM例外は変更しない。r4_09はb328844から見てAなので既存許可に含まれる。新規B-5aの2ディレクトリ/結果文書をAとして追加。累積差分の__init__.py集合はB-3・B-4・B-5aの**3パスだけ**にする |
| test_no_existing_runtime_old_test_fixture_or_setting_differs | 旧ランタイム・設定の差分0を維持。tests検索に:(exclude)tests/v2_history_diagnoseだけを追加。除外後の期待値は従来どおりB-17の**1パスだけ** |
| test_the_old_range_test_differs_in_exactly_the_three_allowed_places | b328844→HEADのB-17累積差分の期待リテラル（削除行・追加行・ハンク数）を、§3.1を加えた差分に更新する。許可する意味上の箇所は同じ3点。期待値を現在のB-17から動的生成して一致させない |

B-3のSTART、Runtime全メソッド、import/公開名/禁止機能/ファイル構成の検査、r3_helpersは変えない。

### 3.3 B-4 test_r4_09_scope.py：モジュール定数と2メソッドだけ

| 対象 | 許可する補正 |
|---|---|
| モジュール定数B17_REMOVED／B17_ADDED／B17_HUNKS、R307_REMOVED／R307_ADDED／R307_HUNKS | d82a5ce→HEADの累積差分に合わせて静的リテラルを更新する。動的生成にしない |
| FilesChanged.test_only_the_allowed_paths_differ | 新規B-5aの2ディレクトリ/結果文書をAとして受け入れる条件を**このメソッド内に**追加し、__init__.py集合をB-4・B-5aの2パスにする。M集合はSCOPE_TESTSの2本のまま（r4_09自身はd82a5ceから見てA） |
| FilesChanged.test_no_existing_runtime_old_test_fixture_or_setting_differs | tests検索に:(exclude)tests/v2_history_diagnoseを追加。期待値はSCOPE_TESTSのまま |

モジュール関数allowed_path()とPathJudgementは変更しない。これらはB-4自身の新規パスの判定であり、"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"を拒否する既存の対照も維持する。START、SCOPE_TESTS、Runtime全メソッド、test_the_two_old_range_tests_differ_in_exactly_the_pinned_lines・test_the_r3_07_edits_lie_in_the_three_allowed_methods_only・test_the_b3_runtime_tests_and_result_are_the_same_as_the_code_startの本体は変えない。

### 3.4 新B-5a scopeによる監査

旧3本の比較元からは、r3_07・r4_09がAまたは検索除外となるため、旧scopeの成功だけで今回の補正を監査できない。ac21980起点の新B-5a scopeが次を直接検査する。

- ac21980→HEADのM集合が上記3本ちょうどであること。他の変更はすべてA、かつ§2の新規パスであること。__init__.pyはv2_history_diagnose/__init__.pyの1本だけ。
- 3本の削除行・追加行・ハンクを、ac21980に対する期待差分として静的に固定する。既存assertの削除、skip、START変更、HEAD偽装を検出する。実装者が変更後ファイルを丸ごと期待値として読んで自己承認する試験にしない。
- 3本のtest関数名の集合がac21980と同じ。r3_07の変更行が§3.2の3メソッド内、r4_09の変更行が§3.3の定数と2メソッド内にあること。
- v2_history_restore/、r4_09以外のtests/v2_history_restore/、V2_RECOVERY_S3B4_RESULT.md、およびB-3以前のランタイム・試験・結果文書がac21980から差分0であること（blob比較）。
- パス判定の対照として、tests/v2_history_diagnose/__init__.py、既存パッケージの変更、4本目の旧試験変更、範囲外の新規ファイル、B-5bに当たるv2_history/values.pyの変更を拒否すること。

具体的な行折り返しは上記の意味を変えない範囲でよいが、結果文書には3ファイルの差分全文を載せる。

## 4. 固定する振る舞い

- 引数は厳密にbytes。型違いだけがdiagnosis_invalid/data/typeの例外。内容の不正はすべてHistoryDiagnosisの値で返す。
- 段階はutf8→json→schema→validate（設計§4.1）。UTF-8はstrict、BOMを除かない。JSONは変更しないdecode_historyで読み、既存の厳格規則とエラーを使う。最上位dict・版1/2・core_sha一致でなければUNREADABLEで、prefixを探さない。
- 版2は変更しないvalidate_history、版1は変更しないvalidate_snapshot。版を取り違えない。全体が通ればVALID。
- 全体が通らず、eventsが空でないlistなら、k＝nから1まで順にhistory_dict／snapshot_dictでヘッダーを計算し直して検査し、最初に通ったkを採る（設計§5）。二分探索・下からの探索・バッチ境界の独自判定をしない。k＝n（ヘッダーだけの違い）も対象。
- 各段階の失敗は{stage, code, field, rule}で、全体検査の最初のエラー。例外集合と変換は設計§4.2どおり。例外文・生の値・連鎖を出さない。
- 壊れたJSONを寛容に解析して記録を救出しない（設計§4.3）。
- 10キーのto_dict、verified・claimed・discarded・itemsの形は設計§3.1・§4.4・§5.4・§6どおり。canonical_textは参考値で状態に影響しない。
- Historyや元バイト・デコード文字列を保持・公開しない。同じバイトから同じto_dict・digest。時刻・乱数・I/Oなし。
- 台帳・sessions・seriesを受け取らない。B-5bの記録種別・採用計画・検査器変更を作らない。

## 5. 受入条件 D5-01〜D5-17

各IDは機能項目であってテスト件数ではない。新規Nは実測する。

| ID | 必須確認 |
|---|---|
| D5-01 回帰・変更境界 | 既存コア197、保存170、S2 113、S3-A 176、B-1 230、B-2 173、B-3 109、B-4 165の計1333件をOS契約どおり維持。機能試験無編集、scope3本の限定補正は別掲。ac21980起点の新B-5a scopeが§3.4を直接検査する |
| D5-02 引数 | bytesだけ受理。str、bytearray、memoryview、None、int、bytesのサブクラスはdiagnosis_invalid/data/type。空のbytesは例外でなくUNREADABLE（json） |
| D5-03 utf8段階 | 非UTF-8、途中で切れた多バイト文字はstage=utf8。BOMつきの正常JSONはutf8を通りjsonで失敗（S2の_loadと同じ扱い） |
| D5-04 json段階 | 途中で切れたJSON、重複キー、NaN/Infinity、深さ超過、巨大整数がdecode_historyの既存ruleでUNREADABLE。prefix探索の検査器呼出しが0回であることをspyで確認 |
| D5-05 schema段階 | 最上位list/文字列、schema_version 0・3・true・"2"、core_sha違いがUNREADABLE。v2のcore_shaだけを変えた入力は、ヘッダーを作り直せば通る内容でもprefixを探さない（変異3の検出） |
| D5-06 VALID | 新規v2、移行済み、例R（3回の復元）、例R-b、再開始を含む履歴のencode_historyバイトがVALID。verifiedがvalidate_historyのHistoryCheckと全項目一致、document_digest＝raw_sha256、canonical_text=true。同じ値の字下げJSONはVALIDでcanonical_text=false |
| D5-07 ヘッダーだけの違い | head_seq、head_hash、current_state、余分なヘッダーキーのそれぞれでPREFIX_ONLY、count＝n、discarded.count＝0、failureは全体検査のrule。元のヘッダーで検査する誤り（変異6）を検出 |
| D5-08 後半の破損 | 末尾のevent_hash改変でcount＝n−1。中ほどのAPPLYの値改変でcount＝その位置、後ろの正しい記録もitemsへ。最後のkが通った後に下を試さない（spy） |
| D5-09 バッチと非単調 | 復元バッチ途中・requestバッチ途中で終わる履歴は、バッチ開始位置がcount。途中のkをvalidate_historyが拒否したことをspyで確認。バッチ途中のkは通らないがより長いkは通る入力で、最長が選ばれる（下から/二分探索の変異を検出） |
| D5-10 NO_VALID_PREFIXと移行 | GENESIS破損でNO_VALID_PREFIX、from_index＝0、itemsは全件。eventsが空/非listでdiscarded=null。移行済み履歴でMIGRATIONを壊した2種（移行前にACKあり、GENESIS/APPLYだけ）の実結果を固定し、itemsにSCHEMA_MIGRATIONが出ること。後者でMIGRATIONを捨てたprefixが通ることを「採用可能」とは表示しない |
| D5-11 v1 | S2のencode_snapshotバイトで、正常VALID、末尾改ざんPREFIX_ONLY（n−1）、ヘッダーだけ違うPREFIX_ONLY（n）、GENESIS破損NO_VALID_PREFIX。schema_version=1、verifiedのv1列（設計§5.4）、migrated=null。v1をvalidate_historyへ、v2をvalidate_snapshotへ渡さない |
| D5-12 failureと例外 | {stage, code, field, rule}の4キー、固定識別子だけ。検査器内のKeyError等をmalformedへ（版ごとのcode）、CoreErrorはruleなし。例外文、生の値、パス、連鎖を出さない。prefix検査中の例外で診断全体が落ちない |
| D5-13 discarded | itemsの5キー。未知の種別"?"、seq/d/request_idの型が不正ならnull、resume_afterや市場値・F&G・decision・自由文を出さない。summaryは件数と種別ごとの数、最初と最後のdだけ |
| D5-14 claimedとverified | 宣言値の型規則（boolのhead_seqはnull等）。verifiedの版2列がHistoryCheck、版1列がValidatedSnapshotと一致。state_digest、document_digestを独立に計算して照合 |
| D5-15 不変性・決定性・秘匿 | to_dictと全読取りが独立した写し。HistoryDiagnosisに元バイト・文字列・Historyを持たない（__slots__等で確認）。同じバイト2回でto_dict・digest完全一致、元bytesは不変。repr/summaryに生の値・URL・パス無し。旧MemoryStore/LocalFileStore（file_sync_onlyの一時root）が診断値・dictをplan_typeで拒否し、保存や残留物無し |
| D5-16 費用の実測 | 合成した約260件のAPPLY（1年分程度）の履歴で、GENESIS直後を壊した最悪位置と、末尾を壊した通常位置の所要時間をLinuxで実測して結果文書に記録。閾値・打ち切りは入れない。試験の実行時間を不当に延ばす場合は、性能の実測を試験から分けた別スクリプトにしてよい |
| D5-17 範囲監査 | 新runtime全体のAST。公開依存は設計§12の名前だけ、__all__は6名。hashlibは生バイトのSHA-256の1か所だけ。I/O・時計・乱数・環境・外部private・戦略式・閾値なし。B-5bの記録種別名や採用計画の関数、ストア・公開・解錠・CONSUMEの語が無い（"diagnos"はB-5aの名のため禁止しない）。新規試験名はd5で一意、testsに__init__無し |

委譲spyは新パッケージが実際に参照する名前を差し替える。v2_history.validate.validate_historyだけを差し替えて、別名importの呼出しを見たと主張しない。
既存の構造ビルダー（h_helpers、ho_helpers、r3_helpers、r4_helpers）は試験だけで読取り再利用できるが、期待値を同じ新実装で生成しない。prefixのcountは、入力を作った位置から独立に決める。

## 6. 限定欠陥注入

次の17項目を1件ずつ壊し、新規試験の感度を確認する。複数変種なら実件数/IDを別掲し、検出・等価・未検出・準備失敗を分ける。過去B-1〜B-4の全変異を自動で再実行しない。

1. UTF-8をerrors="replace"等で読む、またはBOMを除く。
2. 重複キー・非有限数を許す寛容な読込みにする。
3. 版・core_sha違いでもprefixを探す。
4. 版1をvalidate_historyへ、または版2をvalidate_snapshotへ渡す。
5. 下からの探索・二分探索・バッチ境界の独自判定で、最長でないkを採る。
6. ヘッダーを作り直さず元のヘッダーのまま各kを検査する。
7. k＝n（ヘッダーだけの違い）を試さない、またはk＝nで通ればVALIDとする。
8. 全体の検査を省いてprefix探索から始める（VALIDとPREFIX_ONLYの区別を誤る）。
9. prefix検査の例外を捕まえない、または例外文をfailureへ入れる。
10. failureを最後に試したprefixのエラーにする、またはstageを誤る。
11. canonical_textで状態を変える。
12. discardedのitemsへ生の値（市場値、decision、resume_after、不正なrequest_id）を出す、または未知の種別を"?"にしない。
13. verifiedの版1列・版2列の取り違え、document_digestを元バイトで計算する、state_digestの対象違い。
14. to_dictや読取りが内部の参照を返す、または元バイト/Historyを保持する。
15. bytes以外（bytearray等）を受け付ける、または内容の不正で例外を出す。
16. digestやto_dictに非決定的な値を入れる。
17. prefixの各kで、バッチ途中のkを検査器へ渡さずに飛ばす（validate_historyへの委譲を省く）。

B-5a自身の判断と、B-1/S1検査器の独立防護、委譲のspyを分類する。冗長な検査の除去で値が変わらないなら、その限定的な等価性と残る防護を記録し、単に「全検出」にするためだけの無根拠なspyを足さない。等価と分類する場合は、生成器を変えない単一変異の範囲で、反例を探した入力を示す。

## 7. 環境・結果保存・停止

Python 3.10/3.11/3.12/3.13で完全な版を記録する。既存の隔離環境を使い、必要な場合だけスクラッチの単体インタプリタを準備する。依存/設定/workflowを変更しない。
runtimeの通信は禁止。Linuxで使える場合のunshareと、プロセス内socket禁止を区別する。core.autocrlf=falseの別クリーンクローンで最終コードを試験する。`git add`前に__pycache__を消し、PYTHONDONTWRITEBYTECODE=1で実行する。

既存8スイートの計1333件を別掲する。Linuxは1329合格＋Windows専用4 skip。scope3本を補正するため「既存試験が全部無編集」と報告しない。scopeのtest関数を増減しなければ旧件数は維持できる。
Windowsがある場合は新規N＋B-4 165＋B-3 109＋B-2 173＋S3-A 176＋B-1 230＋S2専用4件を実行し、Linux strict前提のS2全探索はしない。合計は新規N＋857。未実施のOSやユーザーPCを他者の結果で代用しない。

新規実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_diagnose -p "test_d5_*.py" -v

結果文書には実モデル設定/effort、固定資料の完全SHA/両blob、開始/試験/最終SHA、全差分（scope3本の全文）、受入とテスト名の対応、全スイートの件数/失敗/error/skip/終了コード、具体的な診断例（入力の作り方、status、count、failure）、D5-16の実測値、変異一覧・分類、解釈した点、未実施を記す。B-5b未着手、CONSUME保留、診断は書込みなしで復旧ではないこと、元バイトの退避・公開・照合はS3-Cであることも明記。
最後のコード・試験をSHAで固定し、別クリーンクローンの成功後、結果文書1本だけを別コミットへ加える。新しい自分の実装ブランチだけをpushし、その最後の差分が結果文書のみであることを確認して停止する。
PR・マージ・Actions・本番・通知、B-5b、CONSUME、S3-Cへ進まない。

## 8. 読取専用の保護参照

次の55参照（B-4修正再レビュー§6の54参照＋再レビュー資料1f7d8c1）を開始時と保存/push後に完全SHAで照合する。本書と設計を保存した新資料ブランチdocs/v2-history-s3b5-20261102も、受け取った完全SHAを1本加える（本初版だけなら実装時は56参照）。追加のレビュー/採用参照を渡された場合もその固定値を記録する。元ブランチを更新しない。

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

## 9. 採用単位

設計§13のD-1（B-5の範囲の解釈、CONSUMEを含めないこと、B-5a／B-5bの分割と今回B-5aだけ）、D-2（厳格読込み・版違いでprefixを探さない・上からの全探索・値で返す）、D-3（B-5bの境界の固定。実装承認ではない）、D-4（v1は診断だけ）、D-5（Sonnet 5.5・high）と、本書の変更境界/受入/通信禁止/結果保存を一組として採否判断する。
今回の文書作成はその採用ではない。B-4の受領をB-5の実装承認にしない。市場戦略、本番保存先、資格情報、旧工程の採用を再質問する依頼ではない。
