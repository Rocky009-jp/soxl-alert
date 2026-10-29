# V2 S3-A ACK・欠測宣言の入力解決／計画 限定実装依頼案

作成2026-10-29、第3版2026-10-29（日本時間）。状態：**第2版の再レビューで通常4件は解消確認済み。任意補正を反映し、採用判断待ち・実装未承認。**
ユーザーが今回承認したのはS3の設計・限定依頼書作成まで。本書を受け取った担当者は、採用・着手の明示指示があるまでコード・試験へ着手しない。本番保存先やS3-B／Cを一括で承認する文書ではない。

## 1. 固定版・担当

- コード基準：d404d4df481957f89201c5169f3a75d7b9d86b66。
- 設計：[V2_RECOVERY_S3_DESIGN_DRAFT.md](../specs/V2_RECOVERY_S3_DESIGN_DRAFT.md)。**実装対象は§3〜§8のS3-Aだけ**。§9・§10は後続の境界で、実装する根拠にしない。
- 資料ブランチ：docs/v2-recovery-s3-20261029。同一の固定コミットから設計と依頼を読み、渡されたパーマリンクの完全SHAと両blob SHAを記録する。作業中に更新へ追従しない。
- 実装担当案：**Claude Sonnet 5.5、effort high**。確定した純粋な入力解決と計画検査の実装として選ぶ。実設定は開始時のセッション情報で確認し、未取得なら不明と記録する。
- 実装を承認された後の新規ブランチ例：feat/v2-recovery-resolution-s3a-20261029。基準d404d4dから作り、保護参照や資料ブランチを上書きしない。

CLAUDE／STATUS／MODEL_POLICY／ROADMAPを確認する。STATUSの古い承認待ちを現在の設計指示と混同せず、今回の「文書作成まで」という範囲も超えない。モデルの役割や未知の復旧意味を独断で変えない。

## 2. 変更を許す場所（着手承認後だけ）

| 場所 | 内容 |
|---|---|
| v2_recovery/ 新規 | ResolutionSet、EffectiveLedger、ResolutionPlan、純粋な検査・投影・計画確認・S1単日処理のラッパー。既存public APIと標準ライブラリのみ |
| tests/v2_recovery/ 新規 | C-01〜C-14に対応する合成試験。既存helper／fixtureは読取再利用可 |
| docs/implementation/V2_RECOVERY_S3A_RESULT.md 新規 | API・形式・優先順位・試験対応・解釈・保留・固定SHA・参照照合 |

既存v2_core、既存v2_persistence（localを含む）、既存197件＋170件＋S2の113件、基準データ、研究原本、main.py、依存、設定、workflow、CLAUDE／STATUS／ROADMAP、既存結果文書は変更しない。v2_persistence/__init__.pyへの再公開も不要。

ランタイムはファイル・root・ストア・秘密値・口座値を受け取らない。LocalFileStoreのprivate属性を呼ばない。解決記録をS1 SnapshotやS2 snapshot.jsonへ保存するAPI、unlock／restore／restart／CORRECTION、schema=2のストア、MemoryStoreへの新しいcommit方式、CLI、取得・通知・outbox・自動日付・追いつき・プロセス・スレッド・乱数は作らない。試験fixtureの独立したS1 APPLY作成はよいが、S3-Aの戻り値をAppendPlanへ変換して作成しない。commit型拒否の確認に限り、試験側が専用一時rootで既存LocalFileStoreを使ってよい。S3-Aランタイムへパスや保存能力を追加しない。

範囲内で実装できない契約矛盾や既存ファイル変更の必要が判明した場合は、具体的な反例・影響・最小差分案を報告し、その変更を行わない。新しい全面レビューや市場計算を自動で追加しない。

## 3. 固定する振る舞い

1. 設計§3.1のResolutionSetは検証用のメモリ値。S1のschema=1／CORE_SHAを変えない。source_headが指す作成時prefixと参照先を検査し、後の正常APPLY延長で古い解決記録を失効させない。
2. 全生行をparse_observationで個別に検査する。解析できない行は除外で逃がさない。同じrecord_idの衝突を、正しい指紋除外が作用する前に確定させない。
3. ACKのADDED／CHANGED／ROW_REMOVEDは保存済みAPPLYへ束縛し、LATEは欠測の参照へ束縛する。LATEに固定decisionや補完を要求しない。宣言済みDのLATEもAPPLYなしで受け付ける。
4. 除外→保存decisionの必要時だけの補完→最終検査の順序。完全指紋だけで除外し、元行があれば補わない。元台帳と保存状態は不変。
5. DECLARE_MISSINGは作成時frontierの直後の1セッションだけ。対象の全decision指紋を明示し、適用済みDを宣言し直さない。0件またはDに関係する妨害の場合だけを許し、正常な有効decision1件の宣言を拒否する。他の日だけの衝突をその1件の除外根拠にしない。同一バッチの先行宣言をfrontierへ数える。市場状態やbaseは変えない。
6. 保存窓と今回窓の投影はS1と同じ。next(D)のclose_at／confirmedだけの変化で通常の投影を恒久停止させない。
7. 計画のbasis／plan_hashへ全入力digestと候補全体を結び付け、確認時に再構築する。計画自体へ循環したhashを入れない。確認結果はCONFIRMED_IN_MEMORY／NO_CHANGE、committed=False。
8. request_idは依頼側が指定する。同じID・異内容を拒否。request_hashからrequested_atを除き、時刻だけ新しい再提出は元記録・元時刻を保持してNO_CHANGEにする。各解決記録には確認時のledger_digestを保存する。同じ内容の既存SetでNO_CHANGEにするときも現在の投影検査は行う。現在Setが別に進んだ場合は自動マージしない。
9. prepare_resolved_dayは既存S1 prepare_dayへ委譲後、専用SimulationDayResultへ変換する。解決Setの有無を問わずAppendPlan／S1 PrepareResult／planプロパティを公開しない。イベント文字列／hashでS1と比較し、committable=False、committed=False。state_updatedのコアの意味を変えない。解決記録を確認しただけで市場状態更新・保存済み・通知可能と表示しない。
10. ADDEDは、元の保存行が台帳にあるか、同じapplied_refのROW_REMOVED／元行なしCHANGEDが既存Setまたは同じ候補バッチにあるときだけ許す。後者の根拠はバッチ全体で検査し、指示の前後で結果を変えない。既存Setだけで現在台帳の最終投影が通ることを、新規計画の前提にしない。
11. 全指示にversion_selection禁止を適用。生台帳で同じrecord_idの複数版の一部を除外し、未固定の版を最終集合へ残してはならない。残る版がS1の固定decisionならCHANGED元行併存等の例外を維持。全版を除く場合もそれぞれの適法な指示・対象が必要。
12. check_dはGENESIS境界より後かつ最新APPLY日以上、等日は再実行可。新規宣言と新規ACK（LATEを含む）のDはcheck_d以下。新規ACKの上限超過はack_evidence、宣言はdeclare_frontier。作成時request_basis.check_dの上限であり、既存記録へ今回のcheck_dを遡って適用しない。範囲外の衝突は台帳修正で直し、包括的除外へ広げない。過去のrequest_basisのcheck_dは作成時prefixに対して検査。
13. 戻り値は独立した写し／再帰的な不変値。repr・エラーは固定code／field／ruleと安全な件数・hashだけ。raw値・URL・note・source_url・パスを自動表示しない。

## 4. 受入条件C-01〜C-14

IDは受入項目でありテスト関数件数ではない。新規Nは実測し、増やした件数だけで品質を主張しない。

| ID | 必須の確認 |
|---|---|
| C-01 既存回帰 | 完全クローンで既存コア197＋保存ドメイン170を無編集合格。S2は既存113件をOS別契約どおり維持（Linux109合格・Windows4非対象）。新規Nを別集計。既存ファイル・fixtures差分0。 |
| C-02 全行解析 | 解決対象に名指ししても解析不能行、bool／巨大整数／NaN等の不正値、role/status/date不正が先に既存入力エラーとなる。誤入力を未観測やNO_SIGNALに変えない。空のSetの正常ケースはS1と判定・イベント文字列／hash・状態が一致。GENESIS境界以前や指示の対象外の衝突は、範囲拡張せず停止。 |
| C-03 ADDED | 保存行＋別ID追加をACKすると追加行だけが除外される。保存行／状態不変。元行が無く適合するROW_REMOVED／CHANGEDも無い場合や、別APPLYの固定行を隠す指示は拒否。A削除＋別IDのB追加を{ROW_REMOVED,ADDED}の両指示順で解決し、A補完1件・B除外を確認。CHANGED＋ADDEDも確認。ACKした行をさらに変更すると再び停止。 |
| C-04 CHANGED | 元行なしの置換は変更版を除外→保存入力を1件補完して通る。元行併存では補完0。別オフセットの同じ行は同一。元role/statusが変わったケースも指紋で束縛し、新版を採用しない。 |
| C-05 ROW_REMOVED | 行なし・空一覧で確認→補完→最終検査の順で通る。元行が再出現したら二重補完しない。APPLYが無い、applied_ref相違、非空一覧、同じIDの未確認変更版は拒否。ROW_REMOVED＋ADDEDの同一バッチを許し、ADDED単独は拒否。 |
| C-06 LATE | skipped_sessionsを持つAPPLY参照と、DECLARE_MISSING参照の両方で通る。対象DのAPPLYは不要、補完0。参照違い、APPLYあり、空一覧、誤ったapplied_ref、指紋の変更は拒否。上位X-17b/c/dを区別する。新規LATEは適法な欠測参照があってもD > check_dならack_evidenceで拒否し、D = check_dは他の条件を満たせば受理。LATEの除外で同IDの未固定の別日版が残る場合はversion_selectionで拒否。 |
| C-07 欠測宣言 | 0件とDに関係する衝突2件の宣言は通り、有効1件はdeclare_valid_decisionで拒否。別日だけの無関係な衝突があっても有効1件を宣言できない。名指し不足／余分はdeclare_incomplete、対象等の未確定はdeclare_unconfirmed（check_d自体の違反は先に既存エラー）。2日連続を1バッチで宣言でき、逆順はdeclare_frontier。同IDの別日版を一方だけ残す宣言はversion_selection。DECLARE後の新指紋はLATEで停止。 |
| C-08 日次接続 | DECLARE済みDはS1が許す日付ならNO_COMMIT、次のAPPLYが既存欠測規則で進む。F&G≥30、<25、25〜30未満の3帯を固定し、≥30のstreak=1を確認。別に用意したS1試験fixtureのAPPLYでSnapshotを延長しても解決記録が有効で、宣言DへAPPLYした不正な組合せは拒否。S3-AのSimulationDayResultからAppendPlanを取り出す経路は使わない。 |
| C-09 参照と状態 | hash鎖、source_head prefix、applied／missing参照の名前空間、記録順・要求バッチの欠け、state_after改変を拒否。記録作成時prefixと現在Snapshotを混同しない。ACK後も保存されたbaseは変わらない。ledger_digestが各記録に残り、現在台帳の変更だけでは過去記録を失効させない。 |
| C-10 計画の確認 | plan改変・確認hash違い、計画後のSnapshot／Set／台帳／sessions変更が停止。候補途中で1件失敗しても何も変更しない。異なるrequestの自動マージなし。同じIDの異内容は拒否し、同じ候補全体への再確認はNO_CHANGE。同じID・指示でrequested_atだけを変えるとNO_CHANGEで元時刻を保持し、指示の変更はresolution_request_conflictとなる。check_dの境界・最新APPLY再実行・新規宣言と新規ACKのDの上限も確認。既存記録の対象Dが今回のcheck_dより後であることだけでは拒否せず、必要な投影検査は維持。 |
| C-11 セッションと同一性 | 適用済み窓／宣言窓で必要列不足や時刻改訂を拒否。通常実行でnext(D)のconfirmed／close_atだけを変えても受け付け、open_at変更は停止。計画確認の全列sessions_digestは意図どおりstaleを返す。台帳の順番・同一UTC表記と、同一行の個数の扱いを設計どおり区別。 |
| C-12 委譲と一致 | S1正常ケースのPREPARED／NO_COMMIT／ALREADY_APPLIEDで判定・イベントの正規化テキスト／hash・状態が一致し、戻り値は専用SimulationDayResult。空SetでもAppendPlanでなくplanプロパティも無い。新ラッパーが実際に参照するprepare_dayをspy／差し替えして委譲を確認。ルール式・閾値・apply_transitionの別実装なし。 |
| C-13 不変性と秘匿 | 入力／戻り値の入れ子を変更しても元Set・Snapshot・計画が変わらない。複数箇所を一括確認し、未解決箇所があればREADYを返さない。既存指紋の行が消えても古いSetの構造検査は通り、新しい不一致は最終検査で止まる。未処理D/Eを対象とする同ID2版でDECLARE(D)、LATE、ADDEDによる一方の選択が拒否され、CHANGEDの固定旧版併存は通る。URLや自由文をrepr／エラー／計画表示へ出さない。 |
| C-14 範囲と停止 | 実ランタイムにI/O・解錠・復元・再初期化・保存・通知・実時計・自動リトライ・依存追加なし。ResolutionSetをS1の保存形式へ混入させない。NO_CHANGE／CONFIRMED_IN_MEMORYがcommitted=False、日次SimulationDayResultがcommittable=Falseかつcommitted=Falseである。専用日次結果と候補イベント文字列をMemoryStore.commit／LocalFileStore.commitへ直接渡すと、既存snapshot_invalid（rule=plan_type）で拒否され、保存内容・seq・先頭・残留物が不変。LocalFileStoreは未初期化の空の一時rootで型拒否を確認し、rootが空のままであることを確かめるか、durability="file_sync_only"で初期化した上で保存内容・seq・先頭・残留物の不変を確認する。Windowsで既定strictのinitializeを試験準備に使わない。新規試験はOS依存機能を不要とする。 |

追加回帰は上位設計のX-14／X-15／X-16、X-17a〜d、K-11〜K-14のうちAの範囲と対応させる。K-14の実復元やRT系を、Aの試験で達成済みと書かない。

重要な欠陥注入は今回の機能に限定する。最低限、解析前除外、除外前補完、補完禁止、無条件補完、record_idだけの除外、LATEへapplied_refを要求、LATEへ補完、固定行の除外許可、plan_hash／いずれかの入力digest無視、入れ子参照共有、S1 AppendPlanの公開、ADDEDの証拠を生台帳だけで判定、version_selection検査の省略、有効1件の欠測宣言許可を1つずつ入れ、対応試験の失敗を確認する。等価変異・対象外は件数を分け、過去全機能の欠陥注入や全市場グリッドを再実行しない。

## 5. 環境・結果の保存

Python3.10／3.11／3.12／3.13で確認し、完全版を記録。既存隔離インタプリタを再利用し、必要な場合だけスクラッチ領域のuv単体Python取得を認める。リポジトリの依存・設定・workflowを変えない。

新規スイート例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_recovery -p "test_*.py" -v

試験は通信禁止。Linuxで使える場合はunshare等のOSレベル遮断を併用し、プロセス内のsocket禁止と区別する。S3-Aランタイムにworkerは不要。core.autocrlf=falseの別クリーンクローンで最終コードを確認し、資料だけの最終コミットとの差分を示す。既存研究fixtureが無い独立環境では未実施と書き、合格・skipへ水増ししない。

新規S3-Aは純粋関数だけなので、Windows環境を使える場合は新規Nをそのまま実行する。Windowsで既存S2全探索を実行してLinux strict前提のエラーを製品不具合に数えない。S2のWindows専用4件だけは既存手順で確認でき、Windowsが無ければ未実施と記録する。ユーザーのPCで確認済みの181／371件を、今回の作業者自身の実行へ置換しない。

結果文書には次を含める。

- モデル実設定・effort、開始／試験／最終の完全SHA、資料SHAとblob、追加ファイル一覧。
- C-01〜C-14とテスト名の対応、既存367／S2の113／新規Nを分けた件数・失敗・error・skip・終了コード、OS・Python・クリーンクローン・通信遮断の区分。
- ResolutionSet／Plan／EffectiveLedgerのキー、参照の名前空間、source_head prefixの扱い、各code／field／rule。
- **ROW_REMOVED**、LATEのAPPLY参照と宣言参照、CHANGED旧行有無の実測を明確にする。N-01〜N-04の反例と修正後期待値、declare_incomplete／declare_unconfirmed／late_missing_ref／version_selection／declare_valid_decisionを対応させる。
- 欠陥注入の一覧・検出・等価・未実施、解釈した点と設計との差。prefix検査は現在Snapshot全体の検査結果から導出する最適化でもよく、方式を記録する。未検査prefixの採用や古い検査結果の使い回しは不可。未依頼の全期間照合や耐久性証明を追加しない。
- Aはメモリ上の候補確認であり、ACK永続化・実ファイル解錠・履歴復元・再初期化・本番通知を実装していないこと。
- 保護参照の前後、PR／Actions／本番／通知なし。結果保存後に止め、B／Cを続行しない。

## 6. 変更しない参照

開始と終了に完全SHAを照合し、この一覧へ書き込まない。資料の今回コミットも固定し、その資料ブランチを書き換えない。

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

## 7. レビュー後に採用する単位（未採用）

採用する場合の対象は次の一組とする。

- S3-Aだけ（入力解決、メモリ上の計画・純粋な確認、S1ラッパー）。§2の追加場所だけ。
- 設計のACK4種・0件またはDに関係する妨害に限る次の1日の欠測宣言・version_selection禁止・不一致時停止・計画hashの確認・専用の非commit可能な日次結果。
- C-01〜C-14、既存固定版・回帰不変、Sonnet 5.5・high、隔離Pythonと通信禁止。
- S3-B／C、新保存形式、実解錠・復元・再初期化、本番は含めない。

今回のユーザー発言は「S3の設計・限定依頼書作成へ進めることを承認」であり、この一組の実装採用はまだ得ていない。本書はその判断を代替しない。第2版の再レビューで通常4件はすべて解消と報告され、第3版で任意提案3件も文書補正した。追加の全面レビューを必須にせず、この一組とN-04の方針（有効decision1件の欠測宣言を拒否）の採否をユーザーが判断する。


## 8. 第2版の補正とレビューの状態

[レビュー本文](../reviews/V2_RECOVERY_S3_S3A_REVIEW_20261029.md)の通常N-01〜N-04を設計§3〜§7と本書§3・C-02〜C-14へ反映した。提案P-01〜P-07も文書補正として取り込み、対応は設計§12に記した。C-01〜C-14という受入IDは維持し、S3-B／C、依存、既存コードの範囲は広げていない。

有効なdecision1件の欠測宣言は拒否する主担当案へ絞った。これはユーザーが実装を採用した記録ではない。修正は文書だけで、実装・試験実行・新市場計算は0。再レビュー後に本書§7の一組の採否を判断する。今回のレビューを承認回答に置き換えない。

## 9. 第3版の任意補正と再レビュー受領

[第2版の再レビュー](../reviews/V2_RECOVERY_S3_S3A_V2_REREVIEW_20261029.md)は重大・通常の新規指摘なし、通常4件解消・提案7件反映済みとの報告。Q-01は設計の「補完権限」をADDEDの「証拠」へ変更、Q-02はC-14のWindows共通の準備方法、Q-03は新規ACKを含むD ≤ check_dの作成時上限として反映した。C-01〜C-14のIDと既存コード不変・S3-A限定の範囲を維持する。

再レビューは実行による検証ではなく、第3版の補正も文書のみ。S3-A実装とN-04の採用は未承認のままで、ユーザーの採用回答後だけ着手する。S3-B／C・本番の承認を含めない。
