# V2 コア F&G巨大整数の限定修正 受領確認

作成日：2026-10-28（日本時間）。  
結論：限定修正を受領する。確認した差分に新たな重大・通常の指摘はない。S1に残っていた台帳の巨大整数の所見は、この範囲で解消した。本番接続・S2以降の承認を意味しない。

## 1. 固定版と差分

| 項目 | 値 |
|---|---|
| 対象ブランチ | fix/v2-core-fg-numeric-overflow-20261028 |
| 基準 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| 試験対象 | 39f5f1f3e9f0578998ae4702b8968d178335617d |
| 保存最終 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| 採用依頼 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048、docs/tasks/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_REQUEST.md |
| 作業者の結果 | [V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RESULT.md](https://github.com/Rocky009-jp/soxl-alert/blob/2d09db770d21480202c4c603e02c2aec5e030012/docs/implementation/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RESULT.md) |

GitHub compareで、基準からの変更が次の3ファイルだけであることを確認した。

- v2_core/observations.py：_parse_valueの数値型のfloat変換にtry／except OverflowErrorを追加（+4／-1）。
- tests/v2_core/test_fg_numeric_overflow.py：新規16件。
- docs/implementation/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RESULT.md：新規結果文書。

試験対象39f5f1fから保存最終2d09db7への差分は結果文書の追加1本だけ。v2_persistence、CORE_SHA、保存スキーマ、既存試験・基準データ、依存・workflowは差分0。今回に限って許可されたobservations.py以外の既存コードは変更されていない。

## 2. 確認した動作

| 項目 | 確認 |
|---|---|
| 生台帳の巨大整数 | 正負の10**400／10**309でparse_observation、select_decision、evaluate_dayがInputError、code=fg_value_invalid、field=current_fg_value。補助観測に巨大値がある場合も拒否 |
| 安全な日次入口 | run_day_safeはErrorResult、DATA_ERROR、終了1、state_updated=false、元の状態を維持。正常なNO_SIGNALには変換しない |
| S1の準備 | prepare_dayは同じInputErrorで停止し、保存内容・seq・head_hashは不変。悪い行を除いた場合は通常どおり準備可能 |
| 保存入力 | 巨大整数の保存decisionは従来どおりPersistenceError／snapshot_invalid、rule=decision |
| 互換性 | 0／100、正常なint・float・数値文字列の受理とfloatへの正規化、bool・非有限・範囲外・不正型等の既存拒否を維持 |
| エラー表示 | code／fieldの既存形式を使い、巨大な数字列をエラー表示へ含めない |

上記は新規16件の独立実行とコード読解で確認した。正常入力の処理を変更せず、既存の変換で発生する例外1種類だけを規定の入力エラーへ統一する最小差分になっている。

## 3. 試験の主体と範囲

| 主体 | 実施・報告 |
|---|---|
| 作業者報告 | Linux、完全なクリーンクローン、通信遮断、core.autocrlf=false。Python 3.10.20／3.11.17／3.12.3／3.13.17の4版でコア197件（既存181＋追加16）と保存ドメイン170件、失敗・error・skip0、終了0 |
| 主担当のソース確認 | 一時ソース31本のGit blob SHAを対象版と照合し全一致。コア12本、保存ドメイン8本、保存ドメイン試験9本、新規コア試験1本と既存helper1本 |
| 主担当の独立実行 | Windows／Python 3.12.14。新規コア16件：全合格、失敗・error・skip0、終了0。保存ドメイン170件を探索し、fixture依存1件を除く169件：全合格、失敗・error・skip0、終了0 |
| 独立未実施 | 既存181件の今回の再実行、研究fixture依存1件、他のPython版、旧版に新規16件を当てた11失敗の独立再実行 |
| ユーザーPC | 181件の実機確認は後日のまま。主担当のWindowsレビュー環境による実行とは別 |

独立実行のコマンド：

    <python> -B -m unittest discover -s tests/v2_core -p test_fg_numeric_overflow.py -v
    <python> -B review_suite_runner.py

後者は前回と同じ一時ランナーで、新規試験のコードを編集せず、test_a03_recompute.RoundTrip.test_research_fixture_chain_matches_core_and_survives_jsonだけを明示的に実行対象から外す。こちらの一時ソースには研究fixtureが無く、この1件は未実施であり、合格やskipとして集計していない。作業者の完全クローンでは実行・合格したとの報告を区別して記録する。

    new_core: Ran 16 tests in 0.117s, OK, exit=0
    persistence: discovered=170, selected=169
    Ran 169 tests in 5.129s, OK
    failures=0, errors=0, skip=0, exit=0

独立実行では既存helperによるプロセス内ソケット禁止を維持した。WindowsでLinuxのunshare相当のOSレベル遮断を実施したとは主張しない。旧版11失敗と4版の全367件の実行は作業者報告であり、主担当が全て再現した結果ではない。

## 4. 互換性と受領範囲

CORE_SHA=b616b4eは、採用依頼§4どおり、S1の再計算互換基準の定数として維持されている。実際のソース版は本書の完全SHAで区別する。正常な市場ルール・保存入力・保存形式は変えず、S1の限定実装の受領判定も維持する。

今回の受領はこのコア修正と追加回帰に限る。セッションや系列の別の型エラーを一括改修する依頼には広げない。新たな既存コード変更や全面的な再試験を追加の完了条件にしない。

## 5. 保存と残件

本書だけを別資料ブランチdocs/v2-core-fg-overflow-receipt-20261028へ保存する。実装、作業者の結果文書、既存資料は変更しない。保存の前後に次の参照の不変を確認する。

main 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、実装基準b616b4e、上位資料b43205c、S1採用資料425df80、初回受領レビューda24fcd、元実装b9586d6、S1修正d44155b、今回の依頼資料08400ac、今回のコード2d09db7。

ユーザーPCでの181件、実ファイル保存、耐久性、複数プロセス、台帳完全性、配信、ACK／復元、実カレンダー、歴史遅延1全日照合は保留。本番反映、Actions起動、外部送信、PR、S2以降への着手はしていない。
