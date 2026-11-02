# V2 S3-B-4 限定実装レビュー

作成日：2026-11-02（日本時間）。担当：ChatGPT / Codex。
**重大0・通常3・提案1。通常3件の限定修正後に再確認することを推奨する。**
今回はレビューと修正依頼書の保存だけ。B-5/S3-C・PR・Actions・本番・通知には進まない。

## 1. 固定対象・確認範囲

| 項目 | 固定値 |
|---|---|
| 実装ブランチ | feat/v2-history-restore-plan-s3b4-20261102 |
| 開始点 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| 試験したコード | **47eb7c5c8c42acc8e218b3b891ce1b6a02e5a664** |
| 結果文書つき最終 | **5eede119b6729e288d188c67de900bcdfcb27cb1** |
| 固定資料 | **0108131045d904b0997299fcade5929567940d6d**（補記済み第2版） |
| 設計blob / 依頼blob | 6111058bdc0ae8eba1df15caccee03f83dd14d59 / dcbc98b2b7ca5fcc5a96d783b98f7a1711a71731 |
| 結果文書blob | cf301c7c98e4c7779179d35a58b7aa9cb221a7f9 |

設計・依頼、結果文書、新規ランタイム10本と試験、S3-A/B-1/B-2/B-3の対応コード、scope差分を読解した。CLAUDE等の固定条件も継続して適用する。AGENTS.mdは試験クローンでは検出しなかった。
7d等の旧版と混同せず、47eb7c5の別クローンで試験した。47eb7c5→5eede11は結果文書1本だけ。開始点→コード版は23ファイル（+4064/-10）、既存変更は指定のscope2本だけである。

## 2. 全体の所見

元の物理記録を残す二段階の組立て、元有効suffix、保存済み入力からのapply_transition、B-2投影→evaluate_dayの順、同じ候補へのNO_CHANGE、案aの保守的な拒否制限は設計に沿っている。CONSUME/保存/バッチは作られていない。
今回、誤った売買判定や保存内容の変更に直接つながる重大な問題は確認していない。以下は差の表示、計画の検査順序、試験と設計説明の不備である。

## 3. 通常の指摘

### R-01 参照hashを埋める前にchangesを計算し、変わらない参照を「変更」と表示する

根拠：v2_history_restore/records.pyの_replay_resolution（99行目〜、changed計算134行目）。再生ACKの参照hashを一度Noneにして、build.py::_chain_after（90行目〜）で後から確定する。その前に旧参照との比較をしている。

実行で再現した2例：

| 例 | 最終記録同士を比べた実際の差 | 現在のchanges |
|---|---|---|
| Pに残すAPPLYをADDED ACKが参照。途中のRESTARTをDROPしACKをREPLAY | state_afterだけ。applied_refはseq/hash/fingerprintすべて同じ | applied_ref, state_after |
| Pに残すAPPLYの旧skipをLATE ACKが参照。同様にRESTARTをDROP | state_afterだけ。missing_refはkind/seq/hashすべて同じ | missing_ref, state_after |

両例ともprepare/confirmは成功し、候補の参照自体は正しい。問題はsummaryにも載るchanged_fieldsの誤表示で、設計§10の「変わった項目名のみ」と食い違う。
**最小修正**：参照のfixup完了後の記録と直接の元記録から、許された比較項目だけでchangesを確定する。seq/parent/event_hash等の連結上の差を追加しない。保持参照・写像で実際に変わる参照の両方を回帰にする。正常なcandidateのevents/digestを変える必要はない（plan_hashは正しいchangesに合わせて変わる）。

### R-02 plan自身の構造検査が不十分で、不正なplanより現在入力を先に読んでしまう

根拠：confirm.py::_form_ok（27行目〜）はchanges/series_inputsをlistかどうかだけで判定し、seq下限なども十分に検査しない。_reapply_olds（71行目〜）は、現在履歴・sessions・台帳の検査より後（confirm_restore_planの段階2）で呼ばれる。

実行で、正常planのhashを付け直して次の変更を施した。

- changes=[{}]
- changes=[{op:[]}]
- changes=[{op:REAPPLY,from_seq:true}]
- REAPPLYのfrom_seq=-1

現在入力が正常なら最終的にhistory_plan_mismatchになる。しかし同時にsessions=Noneを渡すと、元履歴に対する確認Aでも候補に対する再確認Bでも、**sessions_invalid**が先に出た（8観測）。
設計§11手順1はchangesの安全な形・厳密整数等を先に検査し、B4-13は不正planを現在入力より先に拒否すると定めている。候補が不正のまま確認成功したという観測ではない。
**最小修正**：plan固有の安全な形・seq下限・REAPPLY参照抽出を現在入力に触れる前に行い、失敗はhistory_plan_mismatch/planへ固定する。正しいplan＋不正入力は従来どおり入力固有エラーを維持する。unsafe値の表示やdeep JSONの防護は維持する。

### R-03 等価とされた4変異に反例がある。設計のDROPなし同値説明も訂正が必要

ここは実装担当の報告だけでなく、**主担当が設計§10/P-01に書いた同値の説明にも誤りがあった**。現在の注入カレンダーが変わる場合を落としていた。
元の厳密な条件「DROPなし、かつ全REAPPLYがsame=trueなら無効果」は維持し、「DROPなしなら必ずsame=true」という説明だけを撤回することを推奨する。DROPなしの一律拒否へ実装を変える指摘ではない。

同梱スクリプトは、r4_sensitivity.pyに公開された各置換を**そのまま1件ずつ**メモリ上で適用した。別の不具合との組合せでも、リポジトリ書換えでもない。

| 変異 | 実際の入力と対照 | 47eb7c5 | その単一変異 |
|---|---|---|---|
| M09c 新skipをreleased_daysから除く | 元sessionsはD1無し、G(D0)→APPLY D3→RESTART D3。現在sessionsへD1を追加し、D1の有効decisionも追加。P=G、D3 REAPPLY・RESTART DROP。D3のprevはD2のまま | restore_requires_consume | late_observation |
| M12b DECLAREのfrontierを旧値コピー | G→DECLARE D1→DECLARE D2。現在sessionsからD1を除き、P=G、D1 DROP・D2 REPLAY、台帳空。新next(D0)=D2 | READY、新frontier=D0 | history_invalid/history/declare_frontier |
| M16d candidate_recordsと候補末尾の比較を省く | candidate_records=[{}]としてplan_hashを付け直す。同時にsessions=None | history_plan_mismatch | sessions_invalid |
| M17c same条件を除きDROPなしだけで拒否 | 元sessionsはD1無し、G→APPLY D3。現在sessionsへD1を追加、D1のdecision無し。P=G、D3 REAPPLYのみ（DROPなし） | READY、same=false | restore_no_effect |

これらの元履歴はいずれもvalidate_historyを通る。カレンダー変更は合成入力であり、現実の取引所で変更があったという主張ではない。M09c/M17cは旧contextとの共有日が一致し、D3の直前セッションはD2のままなので、設計の照合条件を満たす。追加されたD1でinput_hash/skipped_sessionsが変わる。
M17cの正常対照は確認AがCONFIRMED_IN_MEMORY、同候補への確認BがNO_CHANGEまで通ることも実行した。M12bでは、DROPした宣言日の現在カレンダー欠落を設計§8が許すことが重要である。

**最小修正**：4反例を新しい回帰に固定し、等価注記と結果文書を訂正する。旧144件がこれらを検出したとは数え直さない。新回帰で検出してから結果を更新する。修正後の追加防護によってある削除変異が本当に冗長になる場合は、その新版と条件を区別し、旧版の等価判断が正しかったことにはしない。
61件すべてを今回再実行したわけではなく、累積件数を新たな全件実行結果として報告しない。

## 4. 任意の提案

P-01：M16aの「validate_historyのhash鎖が独立に残る」という等価理由は、「生成器を変えず当該検査だけを削除する単一変異では差が出ない」という範囲へ限定するとよい。hash鎖が自己整合していることだけでは、別の元履歴のままであることまで証明しない。元prefix比較の実装は現在残っており、今回これを削除する提案ではない。M16a自体の非等価を再現したとは報告しない。

## 5. このレビューの実行結果

実Windows、Python **3.12.14**、core.autocrlf=falseの別クローン、HEAD=47eb7c5。-Bと-W error::ResourceWarning。ヘルパーのsocket禁止があるが、OSレベルのネット遮断やLinux unshareとは同一視しない。ユーザーPCではない。

| スイート | 件数 | 結果 | 秒 |
|---|---:|---|---:|
| B-4 tests/v2_history_restore/test_r4_*.py | 144 | OK | 32.803 |
| B-3 tests/v2_history_restart/test_r3_*.py | 109 | OK | 13.406 |
| B-2 tests/v2_history_ops | 173 | OK | 20.246 |
| S3-A tests/v2_recovery | 176 | OK | 3.152 |
| B-1 tests/v2_history | 230 | OK | 19.668 |
| S2 RealWindows | 3 | OK | 1.480 |
| S2 RealWindowsLockDirectory | 1 | OK | 0.094 |
| **合計** | **836** | **failure/error/skip 0** | |

Linux strict前提のS2全探索はしていない。実装者のLinux40実行は報告として受領し、ここへ加算しない。
追加再現：R-01の2観測、R-02の8観測が未解消。4単一変異の反例は全て元コードと区別できた。正常な確認/再確認等の対照も成功。
実行：

    <python> -B docs/reviews/s3b4_review_reproduce.py --repo <47eb7c5のクローン> --mutations

上の調査モードは、観測と単一変異の差が成立すれば終了0。修正済みを要求する次のモードは、元47eb7c5で10観測未解消のため終了1であった。

    <python> -B docs/reviews/s3b4_review_reproduce.py --repo <対象クローン> --expect-fixed

--expect-fixedを付けた場合も、等価判断用の正常なカレンダー対照は維持する。--mutationsは保存された置換パターンが新版でも存在するかを検査し、欠落は準備失敗として区別する。
未実施：Linux・他3版Python、コア197/保存170の再実行、全61変異、物理電源断、autocrlf=true、ユーザーPC、保存/通知/本番。

## 6. 次の限定作業と変更

対になるdocs/tasks/V2_RECOVERY_S3B4_REVIEW_FIX_REQUEST.mdにR-01〜R-03と設計説明の補足、変更境界、受入をまとめた。実装はこのレビューで行っておらず、修正依頼書は承認待ち。
既知の案a制限・CONSUME保留・候補Historyまで、B-1〜B-3既存ランタイム固定は維持する。無関係な全型の不変化、カレンダー仕様の全面変更、B-5/S3-Cへ広げない。

保護は依頼の50参照に、別の第2版資料ブランチf353fb9と実装5eede11を加えた52参照を開始時に完全SHAで照合し一致。保存後も同じ固定値で照合する。
今回の成果物は新しいレビュー資料ブランチの本書・追加再現スクリプト・限定修正依頼書。実装ブランチは更新せず、試験クローンの作業ツリー差分も0。
