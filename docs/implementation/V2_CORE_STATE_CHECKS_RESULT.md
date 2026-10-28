# V2独立コア：状態検査（P-04）・record_id検査（P-06）・純粋な遷移関数（U-14）の限定実装 結果

2026-10-28（日本時間）。依頼書 `docs/tasks/V2_CORE_STATE_CHECKS_TRANSITION_REQUEST.md` の第2版（`b43205ce1a53e4560fb85f9cfb715c72a1132a75`）を、Rockyさんの採用文（2026-10-28 01:42 UTC、プロジェクトスレッド）の範囲のまま実装した。PRは作っていない。

## 1. 結論

- P-04・P-06・U-14を実装し、A-01〜A-04の試験を作って全て合格した。**既存138件は、既存の試験ファイルを1行も変えずに、Python 3.10.20／3.11.17／3.12.3／3.13.17の全てで全件合格**（失敗0、skip0）。新しい試験は43件で、同じ4版で全件合格した。
- 抽出前の動作との一致：1a54a85のコードで作った3114件の基準データと、抽出後のコードの出力が**3114件全て一致**した。
- 感度の確認：新しい検査とA-04について、欠陥を1つずつ入れた43通りの全てを、新しい試験が検出した（検出漏れ0）。元に戻すと全件合格。
- 既存の試験と新しい検査の矛盾、§1の範囲外のファイルの変更は**無かった**。

## 2. 開始・終了時の記録（§6の1）

| 項目 | 値 |
|---|---|
| 実装基準（開始SHA） | `1a54a8573023af9490017b02a8b6458f061031c7` |
| 設計参照 | `e3e90947a718cca877b543739ca60539207ca7a7` |
| 作業ブランチ | `feat/v2-core-state-checks-20261028`（1a54a85から。feat/v2-offline-core-20261027には積んでいない） |
| コミット | `2988721`（基準データ。1a54a85のコードで生成）、`9b26c88`（生成スクリプトの確認の書き換え）、`ecacf8f`（コードと試験） |
| 結果文書を含むコミット | 報告に記載（この文書自身のSHAは文書内に書けないため） |
| 担当モデル | Claude Sonnet 5.5。セッション情報で `configured_model` と `last_served_model` が `claude-sonnet-5-5` であることを確認した |
| クローン | `core.autocrlf=false`。最終のコミットを別のクローン（autocrlf=false）に取り直して、4版で181件の合格を再確認した（A1のblob固定の試験を含む） |

保護SHA（`git ls-remote`）：開始時は main `31144d9b6af8a6c920ad53c395cd550e8c48a7fa`、候補 `920e69571cf4feda09f3f2f560e96fcb9cb09d50`（feat/interim-notification-20261026）、資料正本 `647aeac34cde0d01ec27174f7620aff1724af0e1`（docs/v2-roadmap-20261023）、実装ブランチ `1a54a8573023af9490017b02a8b6458f061031c7`（feat/v2-offline-core-20261027）。終了時の確認結果は報告に記載する。

## 3. 変更したファイル（§6の2）

`1a54a85` との差分は次の10件だけ。§1の範囲外のファイルには触れていない。

| 区分 | ファイル | 内容 |
|---|---|---|
| 変更 | `v2_core/state.py` | `from_dict`を現在状態と基点の別規則に分離（P-04）。`StateInvalid`（内部の規則IDを持つ`state_invalid`）を追加 |
| 変更 | `v2_core/observations.py` | `RECORD_ID_PATTERN`、`is_valid_record_id`、`parse_observation`での検査（P-06） |
| 変更 | `v2_core/engine.py` | 遷移の計算を`apply_transition`の呼び出しに置き換え（U-14）。`evaluate_day`の責務を§2.3のとおりに限定 |
| 新規 | `v2_core/transition.py` | `apply_transition`、`Transition` |
| 新規 | `tests/v2_core/test_state_checks_p04_p06.py` | A-02、A-03（23件） |
| 新規 | `tests/v2_core/test_transition_extraction.py` | A-04の(a)(b)(b2)(c)（20件） |
| 新規 | `tests/v2_core/v2_transition_cases.py` | A-04の入力の集合と結果のJSON化 |
| 新規 | `tests/v2_core/gen_baseline_evaluate_day.py` | 基準データの生成スクリプト |
| 新規 | `tests/v2_core/data/baseline_evaluate_day_1a54a85.json` | 抽出前の出力（基準データ） |
| 新規 | `tests/v2_core/v2_sensitivity_check.py` | 感度の確認（一時コピーに欠陥を入れて実行。作業ツリーは変えない） |
| 新規 | `docs/implementation/V2_CORE_STATE_CHECKS_RESULT.md` | この文書 |

変更していないもの：既存の試験ファイル（`test_*.py`9本、`v2_helpers.py`、`v2_research_reference.py`、既存の`data/`）、`display.py`、`preview.py`、`fixture.py`などの上に挙げていない`v2_core/`のファイル、main.py、既存候補、研究原本、requirements、workflow、設定、CLAUDE.md、STATUS.md、既存の結果文書、設計案。

## 4. 受入基準の結果（§6の3）

### A-01：既存138件の回帰

`tests/v2_core`の既存の試験ファイル（1a54a85の9本）だけを実行した結果。ファイルの差分は無い。

| Python | 既存の件数 | 結果 | skip |
|---|---|---|---|
| 3.10.20 | 138 | 全件合格 | 0 |
| 3.11.17 | 138 | 全件合格 | 0 |
| 3.12.3 | 138 | 全件合格 | 0 |
| 3.13.17 | 138 | 全件合格 | 0 |

### 新しい試験と全体の件数

| Python | 新しい試験（A-02・A-03：23件、A-04：20件） | 全体（`python3 -B -m unittest discover -s tests/v2_core`） |
|---|---|---|
| 3.10.20 | 43 合格 | 181 合格、失敗0、skip0 |
| 3.11.17 | 43 合格 | 181 合格、失敗0、skip0 |
| 3.12.3 | 43 合格 | 181 合格、失敗0、skip0 |
| 3.13.17 | 43 合格 | 181 合格、失敗0、skip0 |

試験の実行中は、既存の`v2_helpers.py`がソケットを無効化する（外部通信の遮断）。標準ライブラリだけを使い、依存は足していない。

### A-02：新しい入力検査

- **P-04 現在状態**：I-01（3通りの組合せ違反を含む6件）、I-02（5件）、I-03（2件）、I-04（等しい・後の2件）、I-05（3件）、I-06（3件）を1つずつ入れた状態が`state_invalid`。例外の内部の規則IDも期待どおり（`exception.rule`）。I-07は、指紋の大文字・63桁・65桁・非16進・空・末尾改行・全角を拒否し、64桁の小文字16進を受け付ける。
- **P-04 基点**：IB-01（`fixed_decision`あり、入れ子の`base`あり、両方）、IB-02（4件）、IB-03（4件）を拒否。最上位の規則を基点に当てない試験（I-01を当てると正常な基点が落ちる）を含む。
- **P-06**：合格（1文字、64文字、英数字・`.`・`_`・`-`の全種）と不合格（空、空白、65文字、先頭が`.`・`-`・`_`、`://`、`/`、`\`、`@`、`?`、`#`、`:`、`,`、末尾・先頭の改行、タブ、NUL、全角、日本語、`é`、丸数字、アラビア数字、文字列以外）を、観測の解析（`record_id_invalid`）と状態の読込（`state_invalid`、規則I-07）の両方で確認。
- **値が出ないこと**：例外の文字列は`record_id_invalid:record_id`／`state_invalid:state`のまま。Webhook風のURLをrecord_idに入れても、`render`の出力・`code`・`field`・`detail`・規則IDに値が出ない。

### A-03：正常な基点の読込と往復

- 受け付ける：`as_of_d`あり・`fixed_decision`なし・`base`なしの基点（K-07）、キーそのものが無い基点、初期状態の基点（K-09）、`GOOD`と同じ形。
- 往復（`to_dict()`→`from_dict()`で一致）：初期状態から、`from_dict`を通した状態から、`from_dict`を通った正常な永続化状態から、それぞれ合成のF&G列（観測なしの日、欠測、3連続のarmed、欠測後、同じDの再実行を含む）を順に処理した全ての段階。**直接構築した不完全な状態（A1の通し計算の開始状態、A-04の合成格子）は往復の対象にしていない**（依頼書§3のとおり）。

### A-04：抽出前後の一致

基準データ：`tests/v2_core/data/baseline_evaluate_day_1a54a85.json`。

| 項目 | 値 |
|---|---|
| 生成に使ったコード | 1a54a85の`v2_core/`（生成スクリプトが、`v2_core/`のツリーがSHAと同一であることを確認してから書く） |
| 件数 | 3114件：A1の通し計算464日（CSV 465行のうち最初の行は開始状態）、合成の格子2592件、代表例58件 |
| サイズ | 5.9MB（gzipで約156KB） |
| sha256 | `76c0f43ee5cbb7f2dc8eb69d3394520ccd145e3503bf31b275001f6c8358b129` |
| 内容 | `DayResult`の全項目、または`ErrorResult`の全項目（コード・項目・詳細・終了コード・実行区分・次状態・`state_updated`） |

入力の集合：A1の研究fixtureの通し計算（既存の試験と同じ入力・開始状態）、格子（基点のarmed 3値×連続数{0,1,2,3}×前日normal_raw 3値のうちI-05・I-06を満たす16組 × 基点の`as_of_d`{無し、前のセッション、2つ前（欠測）} × F&G{観測なし、0、24.99、25、27.5、29.99、30、30.01、100} × 市場側{normal、trend、どちらも不成立} × 前日の市場側normal{成立、不成立}＝2592）、同じDの再実行（一致、値の衝突、record_idの衝突、decisionなし、基点なし、`fixed_decision`なし）、未処理の中間セッション、decision衝突、record_id衝突、時刻表記違いの同一記録、補助だけ・未確認の観測、窓の外、対象Dの不一致、値の範囲外、各種のデータ異常、前日の指標が使えない場合。結果はRunClass 4種（NO_SIGNAL 1850、CONDITION_MET 511、REFERENCE_UNCONFIRMED 471、WAITING_FG 257）とエラー20種を含み、3つの条件の全ての状態（TRENDのUNCONFIRMEDを除く。TRENDはarmedに依存しない）に届くことも試験で確認している。

- **(a)** 抽出後のコードの出力が3114件全て基準データと一致。
- **(b)** `DayResult`の全件について、入力から基点・D行・前日行・decisionを値として取り出して`apply_transition`を直接呼び、判定（3条件、実行区分、欠測、開始時のarmed・連続数・前日normal_raw、注記）と次状態の候補が`evaluate_day`と一致。さらにそれらの値をJSONに書き出して読み戻し（観測は`parse_observation`で作り直し、指紋の一致も確認）、そこから呼んでも一致。同じDの再実行では、候補は同じで、`state_updated`だけがfalseになる。
- **(b2)** 新規の適用でtrue、同じDの再実行でfalse、decisionなしでfalse（かつ入力の状態が同一オブジェクトで返る）。基準データの値とも一致。
- **(c)** `engine.apply_transition`を差し替えると、判定・実行区分・欠測・開始時の値・注記・次状態が変わる。引数は`(基点, D, 前のセッション日, D行, 前日行, decision)`。再実行のときは保存済みの基点が渡り、decisionなしのときは候補があっても入力の状態が返る。`engine.py`の中に`market_side_normal`・`RuleResult`・`tri_and`等の呼び出しが無く、`apply_transition`の呼び出しが`evaluate_day`の中に1回だけあることも構文木で確認。

## 5. 感度の確認（§6の4）

`python3 -B tests/v2_core/v2_sensitivity_check.py`は、作業ツリーを一時コピーし、欠陥を1つずつ入れて新しい試験（43件）を実行する。作業ツリーは変更しない。**43通り全てで新しい試験が失敗した**（検出漏れ0）。元の状態では43件全て合格。

| 区分 | 入れた欠陥 |
|---|---|
| I-01〜I-07 | I-01の無効化、I-01を2者の比較にする、I-02・I-03・I-04の無効化、I-04で等しいを許す、I-05・I-06の無効化（基点側は残す）、指紋の未検査・大文字許可・桁数の緩和・`match`化、record_idの未検査 |
| IB-01〜IB-03 | IB-01の無効化・`fixed_decision`だけ見逃す・入れ子の`base`だけ見逃す、IB-02の無効化、IB-03のarmed・前日normal_rawそれぞれの無効化、最上位のI-01を基点に当てる、基点に現在状態の規則を当てる、基点検査の省略 |
| P-06 | 65文字を許す、空白を許す、先頭の`.`を許す、末尾改行を許す（`$`）、観測側の検査を旧式（空白のみ検査）に戻す、非ASCIIの文字を許す |
| U-14 | 3境界（F&G 30を連続日に数えない）、欠測を検出しない、前日の指標が無いのをFALSE扱い、前日の市場側を逆にする、基点の写しに`fixed_decision`を残す、NORMALの下限25→26 |
| `evaluate_day` | `state_updated`を常にtrue／反転、decisionなしでupdated=true、decisionなしでコピーを返す、遷移に基点でなく状態を渡す、注記を落とす、前日行が無いときD行を代用、`evaluate_day`内に市場側判定の複製を足す、`apply_transition`の外で判定を書き換える |

感度の確認の途中で、前日の指標が使えない場合の代表例が試験の道具（`StubSeries.through`）のために実際には前日行を持っていた問題を見つけ、道具を直して基準データを1a54a85のコードから作り直した（2回目の生成。結果の一致件数は変わらない）。初回の生成（2988721）の基準データは、その後のコミットで置き換わっている。

## 6. 実施していない確認（§6の5）

- **未実施**：Windows実機での実行。既存候補（920e695）の試験（pytest／PyYAML無し、導入は許可外）。実カレンダー。実F&G観測（0件）。本番側の保存・通知接続。歴史の遅延1全日照合（補正版§11.5で留保したまま）。
- Python 3.10は、既存の環境に無かったため、一時作業環境（作業用のスクラッチ領域）にuvで単体のCPython 3.10.20を取得して実行した。リポジトリの依存・設定は変更していない。
- 試験はpytestを使わず`unittest`だけ。ローカルのクラウド環境（Linux）での実行で、Windows・`core.autocrlf=true`は未確認。

## 7. 実装上の判断と、依頼書・設計案との違い（§6の6）

1. **型と定数の置き場所**：循環参照を避けるため、`RuleStatus`・`RunClass`・`RuleResult`・`RATIO_*`・`market_side_normal/trend`を`engine.py`から`transition.py`へ移し、`engine.py`が同じ名前で再公開する（`display.py`・`preview.py`・既存の試験の`from v2_core.engine import ...`は変更なしで動く）。同一オブジェクトであることを試験で確認した。
2. **`Transition`の項目**：`rules`、`run_class`、`gap`、`effective_armed`、`effective_streak`、`effective_prev_normal_raw`、`notes`、`next_state`（decisionがあれば基点にDを適用した候補、無ければ`None`）。`state_updated`は持たない。
3. **最終の次状態と`state_updated`は`evaluate_day`が決める**：decisionなしは入力の状態そのもの（同一オブジェクト）とfalse、decisionありは候補と「同じDの再実行でない」。
4. **`StateInvalid`**：`InputError`のサブクラスで、`code="state_invalid"`、`field="state"`、文字列は従来と同じ`state_invalid:state`。内部の規則ID（`I-03`、`IB-02`、構造の誤りは`shape`）を`rule`属性に持つが、表示には出さない。表示の文言・`run_day_safe`・`preview`は変更していない。
5. **`from_dict`の挙動の変更（依頼書の想定内だが明記する）**：(a) 入れ子の`base`に`fixed_decision`や`base`があると拒否する（IB-01。従来は`fixed_decision`ありの基点を受け付けていた）。(b) `base`が`{}`・`0`・`[]`などの「偽」の値のとき、従来は基点なしとして黙って受け付けていたが、今は構造の誤りとして拒否する。(c) `fixed_decision`の指紋とrecord_idの形式を検査する。(d) `from_dict`の第2引数`_nested`（内部用）を廃止した（呼び出し元は無い）。
6. **直接構築した`MarketState`は信頼済みの内部入力**：この契約を`MarketState.from_dict`の文書文字列に書いた。コンストラクタと`evaluate_day`には検査を置いていない。
7. **record_idの規則**：`RECORD_ID_PATTERN = [A-Za-z0-9][A-Za-z0-9._-]{0,63}`を`fullmatch`で判定（`$`は末尾の改行を通すため使わない）。文字クラスを明示しているので、全角や他の文字体系の数字は通らない。従来は空白だけの文字列以外を全て受け付けていた。
8. **基準データの大きさ**：依頼書の「`DayResult`の全項目」を満たすため、省略せずに保存した（5.9MB、gzipで約156KB）。
9. **前日行の取得**：従来は`_prev_market_side_normal`の中で`InputError`を握りつぶして`None`を返していた。今は`evaluate_day`が前日行を取得し（失敗なら`None`）、`apply_transition`へ渡す。`None`のときの扱い（前日の市場側normalは不明）は従来と同じ。
10. **設計案との違い**：設計案のI-08〜I-15、IB-04（遷移記録が要る検査）、保存形式、ランナー、保存・復旧操作、ACK・outboxは実装していない（依頼書§4のとおり）。`apply_transition`の引数は依頼書の署名のまま。設計案§2.3の`rule_inputs`の保存形式そのもの（遷移記録のJSON）は作っていない。

## 8. 維持した条件（§7）

main `31144d9`は停止のまま、候補 `920e695`・資料正本 `647aeac`は変更していない。既存採用5項目、売却推奨なし、過熱参考OFF、案U（口座値は入力・保存しない）を維持。本番反映、停止解除、Actions起動、Discord／Sheets送信、実データの外部保存、口座操作、API登録・契約・課金はしていない。保存して報告したところで止まり、自動で次の工程へ進まない。

## 9. 再現手順

```
git clone -c core.autocrlf=false https://github.com/Rocky009-jp/soxl-alert
cd soxl-alert && git checkout feat/v2-core-state-checks-20261028
python3 -B -m unittest discover -s tests/v2_core            # 181件
python3 -B tests/v2_core/v2_sensitivity_check.py             # 感度の確認（43通り）
# 基準データの再生成（v2_core/が1a54a85と同一のツリーでだけ書き込む）
python3 -B tests/v2_core/gen_baseline_evaluate_day.py
```
