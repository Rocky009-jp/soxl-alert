# V2 S3-B-5 設計・B-5a限定実装依頼 レビュー

作成日：2026-11-02（日本時間）。担当：ChatGPT / Codex。
**重大0・通常2・提案2。通常2件を文書で揃えてからD-1〜D-5を一組で採否判断へ出すことを推奨する。**
診断と採用の分割、CONSUMEの保留には賛成。実装は未承認のまま。本レビューでB-5a/B-5bの製品コードを作っていない。

## 1. 固定対象・参照

| 用途 | 固定値 |
|---|---|
| レビュー対象資料 | **9c50fcf5a405f7ebf8c6b01f481a32fb629042eb**（docs/v2-history-s3b5-20261102） |
| 設計 | docs/specs/V2_RECOVERY_S3B5_DIAGNOSIS_ADOPTION_DESIGN_DRAFT.md（blob **214d418a5f47079d9d26f482959d3e88637875be**） |
| 依頼 | docs/tasks/V2_RECOVERY_S3B5_LIMITED_IMPLEMENTATION_REQUEST.md（blob **e3bfd559c124069ae0efbf9719104ff122050450**） |
| コード基準 | **ac219801d290ebb59b720f37a086103b6e1251c9**（コードは00ae4b6と同じ） |
| B-4受領 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253 |
| 上位第4版 | e3e90947a718cca877b543739ca60539207ca7a7 |
| B-4設計・依頼 | 0108131045d904b0997299fcade5929567940d6d |

ac21980→9c50fcfは上記の新規2文書だけ（+561/-0）。設計・依頼は全文確認。上位のB-5定義、採用記録のキー、R-1/R-2との境界、既存のHistory/Snapshot codec・検査器、B-1の移行/復元/chain view、B-2 chain、B-4 points、既存scope3本と関連テストビルダーを突き合わせた。CLAUDE等の共通固定条件は継続して適用し、古いSTATUSだけで採用済み工程を取り消さない。試験クローンにAGENTS.mdは検出しなかった。

## 2. 全体の判断

- S3-B第2版§2・§11はB-5を破損診断＋prefix採用としている。B-4ではCONSUMEを別の限定依頼に保留しており、B-5へ含める指示はない。今回の範囲の読み方は整合する。
- B-5aは生バイトを受ける読取り専用診断、B-5bは新種別を受け付ける検査器変更と採用計画。受入済みB-1に変更が入る前に分ける構成は妥当。
- 厳格なJSON読込み、版/core_sha違いでprefixを探さないこと、ヘッダーを計算し直したprefixを既存検査器へ委譲すること、上からの探索、Historyを返さない境界は一貫している。
- B-5bの公開・退避・解錠をS3-Cへ回し、台帳との一致や復旧済みを診断だけで主張しない境界にも賛成。

通常2件は挙動と受入の食い違いであり、範囲拡大や新しい市場計算は不要。設計の根本方針を差し戻す指摘ではない。

## 3. 通常の指摘

### N-01 空のeventsでdiscardedを返す形が設計と受入で違う

根拠：設計§6（197行目前後）と依頼D5-10。

| 文書 | events=[]、NO_VALID_PREFIXの扱い |
|---|---|
| 設計§6 | eventsがlistなら{from_index:0,count:n,items}なので **{from_index:0,count:0,items:[]}** |
| 依頼D5-10 | 「eventsが空/非listでdiscarded=null」なので **null** |

設計§3.2/§5では空のeventsの状態自体はNO_VALID_PREFIXで揃っている。違いはdiscardedの値。両方を実装・試験で満たすことはできない。

**最小修正案**：設計§6を維持し、D5-10を「空listは{from_index:0,count:0,items:[]}、非listはnull」とする（推奨）。逆を選ぶなら設計§6側も揃える。新しい未決事項を増やす必要はないが、値は1つに固定する。
**受入補足**：空list、非list、GENESIS破損の非空listを別ケースとして明示する。schema/core_shaが正しくJSON段階を通る入力で行う。
B-5a自体はまだ無いため、これは文書の矛盾の指摘であり、存在しないAPIの実行結果とは報告しない。

### N-02 MIGRATIONを壊した「前にACKあり」の期待例が既存検査器と違う

根拠：設計§11の移行例（305行目前後）。「前者はNO_VALID_PREFIXまたはMIGRATIONより前で通らない結果」としているが、**MIGRATIONより前の最初のorigin付き記録より短いprefixは通る**。設計§5.1の最大kの定義に従うとPREFIX_ONLYになる例がある。

固定ac21980の既存ビルダーexample_mで、まず全体がvalidate_historyに通ることを確認。その後MIGRATIONのevent_hashだけを0×64へ変更し、設計どおりヘッダーを再計算して各kを検査した。

| k | 末尾 | 既存validate_historyの結果 |
|---:|---|---|
| 8 | SCHEMA_MIGRATION（seq7、壊したもの） | history_invalid/event_hash |
| 7〜3 | 最初の移行済みACKを含む、MIGRATIONなし | history_invalid/origin |
| **2** | **APPLY（seq1）** | **合格、migrated=False** |
| 1 | GENESIS（seq0） | 合格、migrated=False |

よってこの入力の最長prefixは **count=2、head_seq=1、discarded.from_index=2/count=6、itemsはseq2〜7**。これは「ACKを含むprefixが通る」話ではなく、その手前で切れば通るという話である。
対照として、既存example_m_empty_world（移行前はGENESIS＋APPLY2件）を移行してMIGRATIONだけ壊した場合はcount=3、head_seq=2、discarded.count=1となった。

**最小修正案**：§11の前者の期待を上の具体例に変更し、「originを含みMIGRATIONを含まないkは拒否されるが、最初のoriginより短いkは通り得る」と§5.2にも明記する。D5-10の「実結果を固定」はこの2つの具体的なcount・head・discardedと結び付ける。
**維持する境界**：migrated=Falseのprefixが通ったことを、移行の事実が無かった、またはB-5bで採用できるという主張にしない。B-5bは捨てる後半にSCHEMA_MIGRATIONが読める場合をmigration_discardedで拒否するという§9.5の方針のまま。
**確認方法**：同梱s3b5_review_reproduce.py。既存検査器の実行により再現済み。B-1を変更して誤った期待に合わせない。

## 4. 任意の提案

| ID | 根拠 | 提案 |
|---|---|---|
| P-01 | 設計§9.2と§9.5 | B-5bは検査器へ8種目を足すのに、§9.5では候補を「変更しないvalidate_history」に通すと書いている。「§9.2で採用記録に対応した検査器」と書けば既存版のまま通すという誤読を防げる。今回B-5aの検査器無変更とは区別する |
| P-02 | 設計§5.3・D5-16 | 約260件のAPPLYでの実測は有用だが、複数RESTOREの履歴ではvalidate_historyが各復元前のchain viewも検査するため、その計測が全入力の最悪時間の証明にはならない。「APPLY中心の指定した合成履歴での実測」と範囲を明記するとよい。今回の追加性能試験や打ち切り機構を要求する指摘ではない |

## 5. scope補正案の実行確認

実Windows11、Python **3.12.14**、core.autocrlf=false。対象資料のクローンは9c50fcfで作業ツリー差分0を維持。
別の使い捨てコピーをac21980へ固定し、依頼§3.1〜§3.3を実現する補正と、新規許可パス3つの空のプレースホルダーを置いた。**診断ランタイムは作っていない**。

- b17：新規2ディレクトリと結果文書、単一__init__例外、tests検索除外だけ。
- r3_07：指定3メソッドだけ。B17累積差分の期待値は準備時に静的リテラルとして書き込んだ。
- r4_09：指定定数と2メソッドだけ。allowed_path()/PathJudgementやRuntime、START、SCOPE_TESTSは変更しない。
- 3本の関数名集合をac21980と比較して不変を確認。
- scopeはHEADのGit差分を読むため、一時コピー内だけでローカルコミットc53e5a1ea1a5a4ac8c5276b5e05a111d96a06dbdを作成。**pushしておらず、正式な実装SHAではない**。

補正が完了しHEADへ記録された状態での結果：

| 試験ファイル | 件数 | 秒 | 結果 |
|---|---:|---:|---|
| test_b17_scope.py | 10 | 0.928 | OK |
| test_r3_07_scope.py | 11 | 0.800 | OK |
| test_r4_09_scope.py | 18 | 3.782 | OK |
| **合計** | **39** | | **failure/error/skip0、終了0** |

実行は-B -W error::ResourceWarning。依頼で許可した場所だけの補正で実現でき、追加の4本目の旧scope変更は不要と確認した。
準備中に補正が未完了だった状態の探索的実行は、この最終39件の結果に含めていない。B-5aの受入17項目や新規APIの合格を意味しない。

再現する場合は同梱s3b5_scope_probe.pyを**作業用コピー**のac21980へ実行する。ファイル・プレースホルダーの作成とローカルコミットを伴うので、原本には実行しない。このスクリプトは準備時に期待リテラルを作るレビュー用であり、将来の新scopeを現在の差分から動的生成して自己承認させる製品試験ではない。実装担当は依頼§3.4どおり、意味と差分を確認した静的な期待値を固定する。

その後、次を実行する。

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_ops -p test_b17_scope.py
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restart -p test_r3_07_scope.py
    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_history_restore -p test_r4_09_scope.py

## 6. 他の実行・未実施

s3b5_review_reproduce.pyは既存ビルダーと検査器だけを使う読取り専用のプローブ。MIGRATION破損の上記2例と、最上位[]がdecode_historyを通りschema段階に届くことを確認し、終了0。B-5aの診断APIを実装したものではない。

未実施：B-5a/B-5bの実装・受入、既存1333件の全面再実行、Linux・Python3.10/3.11/3.13、260件性能計測、全欠陥注入、ユーザーPC、物理電源断、autocrlf=true、S3-C、公開・通知・市場計算。実装担当や前回の試験結果を今回の実測へ加算しない。

## 7. D-1〜D-5への意見と次の最小作業

| 判断 | レビューの意見（ユーザーの採用ではない） |
|---|---|
| D-1 B-5の解釈、CONSUME保留、B-5a/B-5b分割 | **賛成**。今回B-5aだけとする |
| D-2 厳格読込みと最大prefix、値で返す | **賛成**。N-01/N-02で受入値を揃えることが条件 |
| D-3 B-5bの境界 | **境界として賛成**。実装詳細・検査器変更・再確認の全条件は後の限定依頼でレビューする |
| D-4 v1は診断だけ | **賛成**。v1の救済/移行採用を今回増やさない |
| D-5 Sonnet5.5/high | **賛成**。固定した読取り仕様の実装に適する |

次はN-01/N-02を2文書に整合する形で補正し、P-01/P-02は反映または留保を明記する。新しい戦略・外部サービス・保存先の採否を求める必要はない。補正後にD-1〜D-5を一組で採否判断へ出せる。
レビュー通過や文書保存を実装承認へ置き換えない。

## 8. 保存・保護

依頼§8の55参照と今回資料9c50fcfを加えた**56参照**を開始時に完全SHAで照合し一致。保存後も同じ固定値を照合する。
新資料ブランチdocs/v2-history-s3b5-review-20261102に、本レビューと2つのレビュー用プローブだけを追加する。元の資料・コード・試験・設定は更新しない。
PR・マージ・Actions・本番・送信・B-5a/B-5bの実装は行っていない。
