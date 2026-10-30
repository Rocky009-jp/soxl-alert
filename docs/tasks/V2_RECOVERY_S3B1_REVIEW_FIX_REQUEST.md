# V2 S3-B-1 受領レビュー R-01／R-02 限定修正依頼案

日付：2026-10-30（日本時間）。状態：**修正案を具体化済み。修正実装の明示指示後に着手する。**
指定担当案：Claude Sonnet 5.5、effort high。固定した不変性・入力型検査の修正であり、新しい設計や戦略判断を追加しない。

## 1. 固定版・根拠

- 修正開始点：**0fbba6c46f62a5765cf1ffb8e3646325c1787373**（コードは34cf8dbd2d645a22a4d00c711b2e8157c3db5b22と同一）。
- 元の実装ブランチfeat/v2-history-s3b1-20261029は更新しない。修正承認後は新規fix/v2-history-s3b1-review-20261030等を開始点から作る。同名があれば上書きしない。
- 設計・依頼の第2版：361904b1618ae9f9d3a672875c437a388826c253（設計blob838761207b060ca8c844bf7ed0f15a9e990ad6b7、依頼blob61a645c086c5f62e31f29fcf662cbc76e3bb22dc）。
- B-1採用・開始指示書：98e05e426b99154e7a5941c718b2b220f048e2a2。
- [受領レビュー](../reviews/V2_RECOVERY_S3B1_IMPLEMENTATION_REVIEW_20261030.md) と [再現コード](../reviews/V2_RECOVERY_S3B1_REVIEW_REPRODUCE_20261030.py) を読む。渡されたパーマリンクの資料SHAを固定する。
- CLAUDE／STATUS／MODEL_POLICYの必要箇所を確認する。過去の承認待ちと今回の明示指示を混同しない。モデルの実設定はセッション情報で確認し、不明は不明と記録する。

## 2. 許可する変更

| 場所 | 内容 |
|---|---|
| v2_history/restore.py | superseded_seqsの要素の型・範囲・完全一致 |
| v2_history/migration.py | source.schema_version／source.head_seq等、今回の整数欄の検査漏れ |
| v2_history/values.py | Historyのhead_seq／head_hash／schema_versionの戻り値の独立性 |
| v2_history/migrate.py | MigrationPlan.plan_hashの戻り値の独立性 |
| tests/v2_history/ | 必要な新規回帰。既存217件の期待値を弱めない。任意の例R対照を追加する場合は既存trueケースを保持する |
| docs/implementation/V2_RECOVERY_S3B1_RESULT.md | 訂正と修正結果の節を末尾に追記。旧実行記録を修正後の実績に置き換えない |

上記モジュール内で同種の整数欄の漏れを限定点検する。別モジュールの変更が必要なら、具体的な理由・反例・最小差分案を報告し、対象外変更を行わない。
既存v2_core／v2_persistence（local含む）／v2_recovery、既存コア197・保存ドメイン170・S2 113・S3-A176、fixture、依存・設定・workflow・研究・共通資料は変更しない。S1 Snapshot側の同形アクセサの修正は含めない。

## 3. 必須修正

### R-01：整数欄を値の等しさだけで受理しない

- superseded_seqsの要素はbool・floatを除くintで、非負の物理seq。期待する有効鎖のsuffixとの完全一致を保つ。True==1、1.0==1を利用した通過を止める。
- SCHEMA_MIGRATION.source.schema_versionは厳密なintの1、source.head_seqは厳密な非負intかつ元のhead seqと一致。JSONのtrueや1.0は拒否する。
- 新規schemaの同種整数欄にも同じ漏れがないか確認する。sameの全体仕様・hash・schema versionは変えない。
- エラーは既存history_invalidの固定ruleで返す。最小案はsuperseded_mismatch／migration_source。生例外・生値・例外連鎖を出さない。

### R-02：検証前でも公開アクセサは元の値を変えさせない

- History.head_seq／head_hash／schema_versionとMigrationPlan.plan_hashがdict／listなら、取得した入れ子を書き換えても内部の解析値を変えられないようにする。常にdeepcopyが最小案。
- 正常なint／strの返り値は従来どおりにする。意味検査をfrom_dictへ移して拒否範囲を広げる必要はない。
- History.to_dictとencode_history・digest・等値・hashが食い違わないことを確認する。MigrationPlanのto_dict・等値・hashについても同様。
- 既存のevents／current_state／basis／to_dictの独立性を保ち、私有属性の直接改変を防ぐ機構は追加しない。

## 4. 受入と結果

1. 受領再現コードの現版での10観測と対照2件を確認する。修正後は--expect-fixedで終了0。新規回帰は修正前で失敗し、修正後で成功することを示す。
2. boolだけでなく1.0などのfloat、正常な0／1等の境界int、未検証dict／list、正常な履歴・計画を対照に含める。修正を個別に戻す最小の感度確認を行う。元の欠陥注入全35変種の再実行は必須にしない。
3. 新規217件を維持し追加回帰を別掲。元の受入H-01〜H-14を弱めない。Python3.10／3.11／3.12／3.13、通信禁止、core.autocrlf=falseの別クリーンクローンで確認する。既存スイートとS2のOS区分は元の依頼どおりに記録する。
4. Windowsがなければ未実施とする。主担当のWindows217件を自分の実行結果にしない。ユーザーPC・物理電源断・autocrlf=trueを合格扱いにしない。
5. 任意P-01（H-04／H-05対応表）は文書の訂正として取り込んでよい。P-02は、例Rの#10が現在trueになる入力依存と、必要ならfalseになる対照を記録する。ランタイムの正しいsame判定を変えない。
6. 結果文書に修正点・API互換・失敗先行・個別感度・試験対応・未実施・解釈・完全SHAを追記する。試験対象SHAと結果追記だけの最終SHAを分ける。

開始指示書の29参照＋採用ブランチ98e05e4＋元実装ブランチ0fbba6cの計31参照を、開始時と保存・push後に照合する。このレビュー資料ブランチも、渡された完全SHAで読取専用に追加して固定する。開始時の照合を省かない。

修正ブランチへ保存・pushして結果を報告したら止める。B-2以降・S3-C・日次・台帳投影・実保存／移行／解錠／復元・PR・Actions・本番・通知・口座接続を行わない。
