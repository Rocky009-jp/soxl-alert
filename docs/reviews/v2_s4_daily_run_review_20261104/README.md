# S4設計・S4-A依頼書レビューの確認スクリプト（2026-11-04）

レビュー記録：../V2_DAILY_RUN_S4_DESIGN_REVIEW_20261104.md。どれもレビュー用で、製品コード・試験ではない。

## 準備

完全な履歴のクローンで、2e6ba5f の作業ツリーを作り、試行の差分をそのまま当てる（範囲の鎖の試験のため、pushしないローカルコミットにする）。

    git worktree add <WT> 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb
    cd <WT> && git apply <repo>/docs/specs/V2_DAILY_RUN_S4A_TRIAL_20261104.diff
    git add -A && git commit -m "local trial (not pushed)"

各スクリプトは `TMPDIR=<一時ディレクトリ> PYTHONDONTWRITEBYTECODE=1 python -B <script> <WT>` で動かす。

| ファイル | 内容 | 指摘 |
|---|---|---|
| s4r_restart.py | 実物のC-3で APPLY D1・D2 → RESTART_UNKNOWN（R＝D3）→ D4のdecision。試行のランナーは毎朝 STOPPED／target_not_after_boundary。開始位置を`processing_after`に替えた版は DONE | N-01 |
| s4r_declare.py | (a) 欠測宣言の後（`latest_apply_d`＝`processing_after`で正しく進む。「gap line」の表示は試行がT-1を持たないので参考）、(b)(c) 対象D＝境界の朝 | N-01、P-03 |
| s4r_race.py | `python s4r_race.py <WT> <プロセス数> <回数> <日数>`、環境変数 STAGGER（秒）で子の開始をずらす。最終のhistory.jsonが1回の実行と同じかを数える | N-02 |
| s4r_now.py | 寄付きの後の実行、`now`より後の`observed_at` | P-04、P-05 |
| s4r_calendar.py | カレンダーが`now`より前で終わるとき、古い日へ落ちず`next_session_missing`で止まる | D-6 |
| s4r_fakestore.py | 記憶の中の保存先（C-3と同じ read／publish／reconcile の形、C-2の check_publication・reconcile_publication を使う） | — |
| runall.sh | 既存15スイートの実行（C-4実装時のものと同じ。追加の引数で `v2_daily_run:test_s4a_*.py`） | — |

出力：s4r_probes_out_py3.12.txt・py3.13.txt（restart・declare・now・calendar と試行のスクリプト、両版で同じ）、s4r_race_out_py3.13.txt、trial_runall_py3.12.log・py3.13.log、end_only_scope_chain_py3.13.log（test_c4_09のENDだけを固定し、開いた範囲を足さないときの範囲の鎖。2件失敗）。
