# V2 コア F&G巨大整数の入力エラー統一 限定修正 結果

2026-10-28（日本時間）。依頼書 `docs/tasks/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_REQUEST.md`（資料ブランチ `docs/v2-persistence-domain-s1-fix-receipt-20261028` の `08400ac04bfcb4831c9ef7b8ed518c00c8987048`、blob `06897906d32d15a600014e70f3685bb08c09c010`）を、Rockyさんの採用文（2026-10-28 05:34 UTC、プロジェクトスレッド。限定コア修正を承認、Sonnet 5.5・エフォートhigh、基準 d44155b）の範囲で実施した。PRは作っていない。

## 1. 結論

- `v2_core/observations.py` の `_parse_value` で、数値型の `float(raw)` が出す `OverflowError` を `InputError("fg_value_invalid", "current_fg_value")` に変換した（4行追加・1行変更）。他のファイルのコードは変更していない。
- 台帳の `current_fg_value` が `10**400`・`-10**400` 等のとき、`parse_observation` / `select_decision` / `evaluate_day` / S1の `prepare_day` は同じ `InputError`（code=`fg_value_invalid`、field=`current_fg_value`）で止まり、`run_day_safe` は `ErrorResult`（終了コード1、`DATA_ERROR`、状態更新なし）を返す。`OverflowError` は外に出ない。
- 新規回帰試験16件を追加した。**新規試験だけを旧コード（d44155b）に当てると16件中11件が失敗**（エラー）する。残る5件は「従来どおり」を固定する互換確認で、旧コードでも通る。
- 既存コア181件（既存ファイル無変更）＋保存ドメイン170件＋新規16件は、Python 3.10/3.11/3.12/3.13の全てで失敗0・skip0・終了コード0（クリーンクローン、`core.autocrlf=false`、OSレベルで通信遮断）。
- クラウド環境（Linux）での別環境の試験である。**ユーザーPCでの181件確認は後日実施のまま**で、この結果で「ユーザー実機確認済み」にはしない。範囲外の変更は不要で、停止して報告する項目は無かった。

## 2. 版の記録

| 項目 | 値 |
|---|---|
| 資料 | `08400ac04bfcb4831c9ef7b8ed518c00c8987048`。依頼書 blob `06897906d32d15a600014e70f3685bb08c09c010`、S1修正受領確認 blob `1c75b25032d7f7e1fe9c6c73c9ec534e1fc1d7e7` |
| 基準（開始SHA） | `d44155bca65719da9fc2026ba317c231e950f1b7`（`fix/v2-persistence-domain-s1-review-20261028`） |
| 作業ブランチ | `fix/v2-core-fg-numeric-overflow-20261028`（d44155bから。既存名の上書きなし） |
| **試験対象SHA（完全）** | `39f5f1f3e9f0578998ae4702b8968d178335617d`（コードと試験） |
| 保存最終SHA（完全） | 報告に記載（この文書自身のSHAは文書内に書けない）。試験対象SHAとの差分がこの結果文書の追加だけであることを `git diff --name-status` で確認し報告する |
| 担当モデル | セッション情報で確認済み：`claude-sonnet-5-5[1m]`（`last_served_model` は `claude-sonnet-5-5`）。エフォート `high` |
| OS / Python | Ubuntu 24.04、Linux 6.18.44-fc-v180。Python 3.10.20（既存の隔離インタプリタを再利用）、3.11.17、3.12.3、3.13.17 |

## 3. 変更一覧（d44155b → 39f5f1f）

    A  tests/v2_core/test_fg_numeric_overflow.py     （新規、16件、187行）
    M  v2_core/observations.py                       （+4／-1）

その後に追加するのはこの結果文書だけ（`docs/implementation/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RESULT.md`）。依存・設定・workflow・CLAUDE・STATUS・`v2_persistence`・既存試験・基準データは差分0。S1の記録「v2_core差分0」は当時のものとして残り、今回の差分には当てはまらない。

コード差分の全体：

    if isinstance(raw, (int, float)):
        try:
            v = float(raw)
        except OverflowError:
            raise InputError("fg_value_invalid", "current_fg_value")

boolの先行拒否、文字列の `ValueError` 処理、有限性と0〜100の検査はそのまま。例外メッセージに入力の数字列は含めない（既存の `InputError` は code・field だけを持つ）。

## 4. 新規試験（16件、`tests/v2_core/test_fg_numeric_overflow.py`）

| グループ | 件数 | 内容 | 旧d44155b |
|---|---|---|---|
| OverflowIsAnInputError | 9 | ±10**400、±10**309 を `parse_observation`／補助記録／`select_decision`／良い決定＋悪い補助記録／`evaluate_day`／`run_day_safe`（ErrorResult、終了1、状態不変）／正常値との対比（NO_SIGNALに化けない）／エラー文に数字列なし／台帳不変 | 全9件失敗 |
| OtherInputsAreUnchanged | 3 | 0・100・int・float・数値文字列の受理、既存の拒否（bool、nan、inf、範囲外、読めない文字列、`"1e999"`、400桁の数字文字列、None、list等）、正常値の日次結果 | 全3件合格（互換の固定） |
| PreparedDayStopsWithoutChangingTheStore | 4 | S1の `prepare_day` が同じcode／fieldで止まり、スナップショット内容・seq・先頭ハッシュが不変／保存済み日の補助記録に巨大値でも停止／悪い記録を除けば従来どおり計画できる／保存側の巨大整数は従来どおり `snapshot_invalid`（rule=`decision`） | 巨大値の2件失敗、他2件合格 |

合計：旧コードで失敗11（すべて `OverflowError`）、合格5。修正後は16件全て合格。

## 5. 試験結果（試験対象 `39f5f1f`、クリーンクローン、`unshare -rn` 下）

コマンド（`<python>` は各版）：

    <python> -B -m unittest discover -s tests/v2_core                              # 既存181＋新規16＝197
    <python> -B -m unittest discover -s tests/v2_persistence -p "test_*.py"        # 保存ドメイン170

| Python | v2_core（181＋16） | v2_persistence（170） | 失敗／error／skip | 終了コード |
|---|---|---|---|---|
| 3.10.20 | 197 OK | 170 OK | 0／0／0 | 0／0 |
| 3.11.17 | 197 OK | 170 OK | 0／0／0 | 0／0 |
| 3.12.3 | 197 OK | 170 OK | 0／0／0 | 0／0 |
| 3.13.17 | 197 OK | 170 OK | 0／0／0 | 0／0 |

- クローンは fixture を含む完全なクローンで、`git status` の差分は0。fixture依存の1件も実行され合格した。fixtureを持たない環境で独立確認する場合は、その1件を「未実施」と記録し、合格にもskipにも数えない（S1結果文書§15.6と同じ扱い）。
- 既存181件と保存ドメイン170件は、ファイルを一切変更せず、件数と結果が前工程（181＋170）と一致した。「保存入力からの再計算」と「正常入力の判定」に差が出る場合は停止する条件だったが、差は出なかった。3114ケースや歴史全日照合は新たに作り直していない。
- 通信遮断は、OSレベル（`unshare -rn`）に加え、試験の道具がプロセス内でソケット生成を無効化する既存の仕組み（`v2_helpers.py`、新試験が使う `p_helpers.py`）の二重。

## 6. 互換性

- 正常な入力（0〜100の int／float／数値文字列）の戻り値は、値・型（float）とも従来どおり（新規試験 `test_accepted_values`）。
- 既存の拒否は同じcode／fieldのまま（bool、非有限、範囲外、読めない文字列、その他の型）。
- `v2_persistence` の `CORE_SHA`（`b616b4ec7169420e199ec7e247dd375b3603a013`）と保存スキーマは変更していない。`CORE_SHA` はS1が準拠する再計算互換基準を示す定数であり、実際の全ソースHEADの自己証明ではない。今回の実際のコード版は上記の完全SHAで区別する。
- 保存側の巨大整数（`snapshot_invalid`）の経路には触れていない。台帳側（注入入力）の巨大整数が、保存側と別のエラー（`InputError`）で止まる点は依頼書どおり。

## 7. 保護参照・読んだ資料の確認（終了時、`git ls-remote`）

main `31144d9`、候補 `920e695`、資料正本 `647aeac`、旧コア `1a54a85`、実装基準 `b616b4e`、上位資料 `b43205c`、採用資料 `425df80`、前回レビュー `da24fcd`、元実装 `b9586d6`、S1修正 `d44155b`、本依頼の資料 `08400ac`：いずれも完全SHAの先頭が上記のとおりで、今回これらへは書き込んでいない。作業開始時は、d44155b と 08400ac を取得して基準にし、保護参照の一覧確認は終了時に行った。新しく進めた参照は `fix/v2-core-fg-numeric-overflow-20261028` のみ。

## 8. 保留・未実施

- ユーザーPCでの既存181件の確認、Windows実機、歴史遅延1の全日照合は今回の完了条件にしておらず、未実施。
- 台帳の巨大整数以外の入力（例：セッションや系列の型違いでコアが `TypeError` を出す経路）は範囲外のため触れていない。必要なら別件として扱う。
- PR作成、main反映、ジョブ起動、送信、S2以降への続行はしていない。
