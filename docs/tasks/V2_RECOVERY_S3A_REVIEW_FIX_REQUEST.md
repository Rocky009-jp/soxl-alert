# V2 S3-A レビューR-01／R-02 限定修正依頼

作成：2026-10-29（日本時間）。担当：**Claude Sonnet 5.5、effort high**。  
目的：採用済みS3-Aの入力検査・秘匿契約への適合。S3-B/Cへの移行依頼ではない。

## 1. 根拠・基準

- [レビュー本文](../reviews/V2_RECOVERY_S3A_IMPLEMENTATION_REVIEW_20261029.md)と[再現コード](../reviews/V2_RECOVERY_S3A_REVIEW_REPRODUCE_20261029.py)を読む。
- 開始点：2c246e3e485d9dcb90fb35ab1628040b484fb7c2。コード・試験の固定SHAは3b71816f5d4fd08b0a065e3f92e189944ac604d5で、差は結果文書1本のみ。
- 採用記録：d215193065ebf110e6a77f22edf208b390138285。設計・依頼書第3版：2d504de7cbf4628a3760d48f70fd0228dce6a61c。依頼C-01〜C-14と全除外範囲を維持。
- 今回は承認済みS3-Aの内側で、既に要求されている固定エラー・秘匿性を直す。全体の採用を再質問しない。今回の修正で新仕様・永続化を追加しない。
- 新規ブランチ例：fix/v2-recovery-resolution-s3a-review-20261029。開始点から分岐し、元のfeat・資料・レビューのブランチは上書きしない。

## 2. 変更を許す範囲

- v2_recovery/plan.py：R-01／R-02の最小修正。
- tests/v2_recovery/：対応する回帰試験。既存155件を弱めず、既存C-IDは維持。
- docs/implementation/V2_RECOVERY_S3A_RESULT.md：訂正・修正結果を追記。以前の実行・未実施の記録は消さない。
- 任意提案P-01を取り込む場合だけv2_recovery/common.pyの時刻述語と対応回帰も可。
- 任意提案P-02を取り込む場合はtests/v2_recovery/sensitivity_check.pyと独立したhash期待値の回帰を修正し、結果文書を訂正。

コア、S1、S2、既存197＋170＋S2 113件、fixtures、依存・workflow・設定・研究原本を変えない。ResolutionSet／Planのキー、正常値のcanonical JSON・hash、公開API、戦略式・委譲は維持。修正に別の範囲外変更が必要なら反例と最小案を返し、その変更は行わない。

## 3. 修正・受入条件

### R-01

ResolutionPlan.from_dictで構築できる未検証の値を、repr／summaryが無検査で表示してはならない。合成URL・自由文をstatus／request_id／commandsの日付などへ入れても表示へ出さない。from_dictで構造不正を固定PersistenceErrorとして拒否しても、表示時に安全な固定表現／固定PersistenceErrorへ処理してもよい。確認前の表示のためにconfirmを要求する設計へ変えない。正常なsummaryとconfirmの再構築は維持する。

欠落キー・誤型・不正hashの表示も、生のKeyError／TypeErrorや任意文字列を出さないこと。表示を安全にしただけで、改変計画の確認成功を許してはならない。正常計画のsummaryは従来の許可リストどおりとする。

### R-02

from_dictの深い入力のコピー・JSON変換で、PythonのValueError／RecursionError等を外へ出さない。check_jsonの深さ制限をコピー前に適用するなど、既存のJSON検査を利用して最小に直す。危険なコピー／シリアライズの例外は、field=plan・固定ruleのPersistenceErrorへ例外連鎖を抑えて変換する。正常hashの変更、整数文字列変換上限・再帰上限をプロセス全体で緩める対応は禁止する。

1200段の入れ子、10**5000の整数、正常・境界内の値を対照にする。整数変換上限のないPythonではValueErrorが出ないため、その環境の適用有無を区別し、不要なskipの水増しをしない。

### 共通

- 再現コードを修正前に実行し、元の5観測を確認。修正後は--expect-fixedが該当全件で成功すること。再現コードを通すだけにせず、tests/v2_recoveryへ独立した回帰を追加。
- 追加回帰が修正前で失敗し、修正後で成功すること。R-01／R-02を別々に戻したとき、対応回帰が検出することを限定して確認。過去53件全ての再実行は不要。
- 元の155件を維持し、新規件数を別に報告。元のコア197＋保存ドメイン170は無編集。LinuxならS2 109合格＋Windows4非対象、WindowsならS2専用4件で確認する。
- Python3.10／3.11／3.12／3.13、別クリーンクローン・core.autocrlf=false、依頼どおり通信禁止。Windowsを使えない場合は未実施と記録。主担当のWindows526件を自分の実行結果へ置き換えない。
- P-01／P-02は通常2件とは別の任意項目。取り込まなければ保留として報告し、新たな採用待ちを理由にR-01／R-02を止めない。

## 4. 保存・報告・停止位置

実設定を取得できた場合だけSonnet 5.5・highを確認済みと記録。開始／資料／試験対象／結果文書だけを加えた最終SHA、変更ファイル、試験と欠陥再現の件数・exit code・OS・Pythonを分ける。

開始と終了に、依頼書第3版§6の19参照、資料2参照、元実装ブランチ2c246e3e485d9dcb90fb35ab1628040b484fb7c2を確認。本レビューの保存ブランチも読取だけとし、実装側から更新しない。

結果を修正ブランチへ保存・push後に止める。PR・Actions・S3-B/C・新保存形式・解錠／復元・本番・通知は行わない。
