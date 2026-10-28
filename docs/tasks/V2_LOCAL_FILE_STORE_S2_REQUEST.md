# V2 S2 ローカル実ファイル保存 限定実装依頼

2026-10-28（日本時間）。状態：S2への実装移行についてユーザー指示あり。下記限定範囲で着手可。  
新たな本番保存先・S3／S4の採用は含まない。再びS2全体の承認を待つために止めない。契約に実装上の矛盾がある場合だけ、該当変更を行わず具体的に報告する。

## 1. 担当・固定版

担当：Sonnet 5.5、エフォートhigh。固定した入出力・比較更新・ファイルI/Oの実装として割り当てる。実際の設定は開始時に確認し、確認不能なら不明と記録する。指定モデルを独断で変えない。

コード開始点：2d09db770d21480202c4c603e02c2aec5e030012。  
設計：[V2_LOCAL_FILE_STORE_S2_DESIGN.md](../specs/V2_LOCAL_FILE_STORE_S2_DESIGN.md)。  
資料ブランチ：docs/v2-local-store-s2-20261028。本書・設計を同じコミットから読み、資料の完全SHAとblob SHAを最初に記録する。渡されたコミットパーマリンクがあればその固定版を使う。作業中の更新へ自動追従しない。

コード用の新規ブランチ例：feat/v2-local-file-store-s2-20261028。基準2d09db7から作り、既存ブランチを上書きしない。古いSTATUSは今回の指示を取り消さない。

## 2. 追加を許す場所

| 場所 | 内容 |
|---|---|
| v2_persistence/local/（新規） | LocalFileStore、低水準I/O・排他・結果型等。標準ライブラリと既存v2_persistence／v2_coreだけに依存 |
| tests/v2_persistence_local/（新規） | ファイル試験、独立プロセスworker、故障注入、必要な小さなhelper。既存helper／fixtureは読取再利用可 |
| docs/implementation/V2_LOCAL_FILE_STORE_S2_RESULT.md（新規） | 設計対応、結果、保存形式・同期水準・停止条件・再現手順・保留 |

既存v2_core、既存v2_persistenceのファイル、既存コア197件・保存ドメイン170件・基準データ、main.py、依存・設定・workflow、CLAUDE／STATUS／ROADMAPを変更しない。既存パッケージの__init__を書換えず、利用側はfrom v2_persistence.local import LocalFileStore等とする。

今回はローカル保存の試験用アダプタ。実データ・口座値・資格情報・本番パスを入力せず、全書込を明示した専用の一時テストrootへ限定する。新しいリポジトリ・トークン・通知・取得・自動日付・cron・ACK・復元・強制解錠API・自動再送は作らない。PRも作らない。

## 3. 固定する実装契約

設計§2〜§9を仕様とする。

- S1の全履歴入りSnapshotをsnapshot.json一つへ保存する。encode／decode／validateを再利用し、schema_versionとCORE_SHAは変えない。論理操作はGENESIS初期化またはAPPLY1件追加のみ。
- rootは明示した既存の専用絶対パス。既定writable=False、書込には明示的なTrueを必要とする。readにも排他メタデータの作成権限は必要で、正本更新の禁止とOSの読取専用媒体を区別する。
- 同じrootの全プロセス・全インスタンスでwrite.lockの排他的作成を使う。既存ロックは即store_busy。期限切れ推定、自動強奪・削除、PIDだけの所有判断をしない。
- readは毎回ディスクから全検査。commitはロック内で再読取→CAS→候補の全検査→保存。S1の市場計算や検査を複製しない。
- 保存は同じrootで一時ファイル作成→全量write→flush→file fsync→close→os.replace→strictならdirectory fsync→正常なロック解放。旧正本の先行削除や直接truncateは禁止。
- strictを既定とし、同期機能が未対応なら書込の公開前に停止。file_sync_onlyは明示指定のみで、結果のpersistence_levelを区別する。Windows strictは今回未対応として明示的に拒否し、Win32固有APIを増やさず、黙って弱めない。
- 置換呼出し開始以降の失敗はstore_commit_uncertain。読めた新版を同期成功とみなさず、ロールバック・再追記しない。再読取＋既存reconcileは論理照合だけ。
- 残留ロック／一時ファイル、欠損、破損を自動で直さない。通常例外時は自分が所有するものだけを片付け、後始末の失敗を隠さない。
- 公開APIの構造化戻り値は独立した写しまたは再帰的な不変値。パス・raw行・生OSError・秘密値を例外表示へ出さない。

## 4. 受入条件B-01〜B-10

IDは項目であってテスト関数件数ではない。新規件数Nは実測する。

| ID | 必須の確認 |
|---|---|
| B-01 既存回帰・互換 | 既存コア197件＋保存ドメイン170件を無編集で合格。S1 SnapshotのJSON往復、保存入力からの全再計算、現在状態・判定の一致。CORE_SHA／schema不変 |
| B-02 読取・初期化 | 未初期化のread／commit拒否、明示GENESIS1件の初期化・別インスタンス／別プロセスで読取、二重初期化とAPPLY入り初期化の拒否、既定read_onlyで正本不変 |
| B-03 通常更新・再実行 | 準備だけではファイル不変、成功時のみAPPLY1件・seq+1、過去イベント値不変。NO_COMMIT／ALREADY_APPLIEDは正本を書かない。再起動・読直し後も同日追記0。戻り値の入れ子改変で正本・ストアは変わらない |
| B-04 プロセス間競合 | 同じ先頭から2つの独立プロセスが同内容／異内容の同D、異なるDを準備して競合。成功は1、敗者はstore_busyかcas_conflict。敗者の明示的読直しでS1 reconcileの結果を確認し、自動再追記しない |
| B-05 保存手順と通常故障 | 実ファイルを使い、write／flush／file fsync／close／replace／directory fsync／解放の順を観測。短いwrite、書込・同期・置換のOSError、ロック作成途中と後始末の失敗を注入。公開前は旧正本不変、公開開始後は不明codeで成功を返さない |
| B-06 強制終了 | 別プロセスを、ロック取得後・部分書込後・file fsync後・replace後・directory fsync後の各点で強制終了。正本の生バイトは旧版か完全な新版（初期化前なら不存在）、中途半端なJSONを正本にしない。次回APIは残留ロック等で停止し、自動採用・削除をしない |
| B-07 成否不明 | 実際にreplaceを行ってから例外を出すケース、置換後directory fsync失敗、置換後の解放失敗でstore_commit_uncertain・COMMITTEDなし。読める場合のreconcileは論理存在だけを示す。先頭が進んだだけで自分の保存成功としない |
| B-08 破損・パス | 欠損、途中JSON、重複キー、非UTF-8、hash／状態／schemaの違反を拒否。残留tmpを正本へ昇格しない。root・管理対象のリンク／非通常ファイル、root外を指す管理対象のリンクやパス、所有が変わったロックは安全に拒否し、外側・他者のファイルを変更しない |
| B-09 同期モード・OS | strictとfile_sync_onlyの結果水準、未対応strictの公開前拒否、黙った格下げなし。実Linuxでstrictを確認。利用できる実Windowsではfile_sync_only・strict拒否・置換・プロセス競合を確認し、未実施なら留保。Linux上のWindows分岐模擬を実Windows合格にしない |
| B-10 境界・報告 | 全試験を通信禁止で実行。ランタイムにネット取得・通知・資格情報・時計による対象日・復旧経路なし。実ファイル／実プロセス／故障注入／未実施の物理電源断を分け、エラーのcode／field／phaseと保存・後始末の結果を記録 |

### 4.1 プロセス競合の具体化

threadingだけでB-04を済ませない。multiprocessingのspawnまたは独立したPython workerを使い、両者が同じ先頭を読む段階をEvent／Pipe等で同期させる。sleepによる偶然の競合に依存しない。テスト上のタイムアウトは設けてよいが、製品のロック期限に転用しない。

Aがロックを保持した状態でBがstore_busyとなり他者のロックを消さないことも確認する。A完了後、Bが同じ古い計画を明示的にもう一度渡すとcas_conflictになることを確認する。テストの明示再呼出しを、製品の自動リトライとして実装しない。

### 4.2 強制終了と故障注入の具体化

B-06は捕捉できるPython例外だけで済ませず、workerのos._exit等でfinallyが動かない状況を作る。親は子の終了を確認してから、専用rootの生ファイルを診断する。残留ロックの削除が必要な試験後半では、全worker終了と所有を確認したテスト側の明示操作に限る。製品側へ自動解錠を足さない。

B-05／B-07の権限・容量・同期エラーは、専用rootのI/O層で故障注入してよい。実際にディスクを満杯にしたり、マシンの電源を切ったり、保護フォルダの権限を変えたりしない。故障注入と実プロセス終了の結果を同じ証拠として混ぜない。

最低限、ロック取得後の所有変更、ロック取得途中の例外、replace前失敗、replace実施後の例外、directory fsync失敗、unlink失敗を個別に確認する。失敗後に同じSnapshot参照とのassertEqualだけで不変性を判定せず、変更前の深い値と正本バイト列・先頭も比較する。

## 5. 環境と結果の保存

Python 3.10／3.11／3.12／3.13を対象とし完全バージョンを記録する。既存の隔離インタプリタを再利用し、必要ならスクラッチ領域のuv単体Python取得だけを利用する。リポジトリの依存・設定は変えない。

実Linuxを最初の検証対象とする。実Windowsが利用できない場合もLinuxでの実装・検証は進め、「Windows未実施」「file_sync_onlyの実機確認未完了」を明記する。ユーザーPCの既存181件確認は後日のままで、S2作業者の試験に置き換えない。

既存367件と新規N件を別集計する。新規の探索例：

    <python> -B -m unittest discover -s tests/v2_persistence_local -p "test_*.py" -v

全workerも通信遮断を引き継ぐことを確認する。OSレベル遮断が使える環境では併用する。既存367件の研究fixtureは完全クローンで揃えて実行する。fixtureやOSが無い独立確認は未実施として記録し、合格・skipに水増ししない。OS別の非対象ケース・実施ケースを分け、全件skipのスイートで対応済みとしない。

最終コードをcore.autocrlf=falseの別クリーンクローンで試験する。結果文書追記だけが後になる場合は、試験対象SHAと保存最終SHA、両者の文書だけの差分を分ける。市場シミュレーション、歴史全日照合、過去の全欠陥注入を自動追加しない。

結果文書には次を記録する。

- 開始／試験／保存最終の完全SHA、モデル・エフォート、OS・Python・ファイルシステム・同期モード、core.autocrlf、コマンド、実測件数、失敗・error・skip・終了コード。
- B-01〜B-10と試験の対応、保存ファイルとAPI、code／field／phase、どの時点まで未公開でどの失敗が成否不明か。
- 競合のworker数と同期方法、強制終了点、残留物、物理電源断を試験していないこと、Windows等の未実施。
- 既存ファイル差分0、保護参照の前後、外部送信・本番操作・PRなし。S2のローカル保存を本番正本へ採用したとは書かない。

## 6. 変更しない参照

開始・終了時に完全SHAを確認し、今回これらへ書き込まない。

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

本依頼を読んだ資料コミットも固定する。範囲外のコード変更や仕様の矛盾があれば、最小差分案と影響を報告してその変更には着手しない。新しい全面レビューを理由なく増やさず、B-01〜B-10の結果を保存・報告して止める。S3／S4への続行は含めない。
