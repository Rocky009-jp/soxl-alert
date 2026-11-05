# V2 S4-C gitの保存先（履歴とoutbox） 限定実装依頼書

作成日：2026-11-05（日本時間）。版：**初版**。作成：Claude Opus 5.5、effort high。
状態：**初版・未採用**。設計§12のD-1〜D-9は採用されていない。限定実装は、採用の後に、別スレッドへの明示の着手指示で始める。本書の保存だけでは実装を始めない。
対になる設計はdocs/specs/V2_GIT_STORE_S4C_DESIGN_DRAFT.md（以下「設計」）。本段階はS4-Cだけを実装する。中身は次の3つである。

- gitを呼ぶ唯一の層`Git`。
- 履歴の保存先`GitHistoryStore`（S4-Aの`read`・`publish`・`reconcile`の形）。
- outbox`GitOutbox`（S4-Bの`LocalOutbox`の子クラス）。

試験のリモートは、一時ディレクトリのbareリポジトリだけである。ネットワーク、GitHub、非公開リポジトリ、資格情報、台帳（S4-D）、入口のスクリプト・workflow・秘密・本番（S4-E）は含めない。

## 1. 固定入力と実装開始条件

| 用途 | 固定値 |
|---|---|
| 実装開始点 | **6cab0506c408d194c63b656713e4a0a7d62c3ba1**（feat/v2-notify-s4b-20261105、S4-Bの受領版） |
| 対になる設計・試行の差分 | 本依頼と同じ資料コミット（docs/v2-git-store-s4c-20261105）の設計とdocs/specs/V2_GIT_STORE_S4C_TRIAL_20261105.diff。SHAと3つのblobを開始報告に記録 |
| S4-Bの受領・提案の採否 | 受領記録983ced810ac04fd5714a56802008303657c797d9、採否9b4d786a14ab10ef5c0a2525191bf7b4753f4bbf |
| S4の設計・依頼書（第2版、採用済み） | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6（§6.2） |
| 上位の保存・送信権の設計 | e3e9094 §3.2・§3.8・§5.2・§5.3（第3版） |
| 使う既存の部品 | 設計§1の表のとおり（v2_history_publish、v2_history_local、v2_persistence.local.errors、v2_notify、v2_core.errors） |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6 §6、9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |

- 新規の実装ブランチは、次の2つが揃った後にだけ、6cab050から作る（ブランチ名の案：feat/v2-git-store-s4c-YYYYMMDD）。
  1. ユーザーが設計§12のD-1〜D-9を採用すること。
  2. ユーザーがこの限定実装への移行を指示すること。
- 資料ブランチから実装を始めない。先端へ追従しない。
- 推奨担当はSonnet 5.5・high（D-9）。実際のモデルとeffortはセッション情報で確かめる。設定できない場合は、その事実を報告する。
- CLAUDE.md等と固定資料を読む。未承認のD-1〜D-9を、採用されたと書かない。
- 実行環境のgitの版（`git --version`）を開始報告に記録する。

## 2. 変更を許す範囲

| 対象 | 許可 |
|---|---|
| v2_git_store/ 新規 | `__init__.py`、`git.py`、`history.py`、`outbox.py`。4ファイルを超えない。分け方を変えたら結果文書に理由を書く |
| tests/v2_notify/test_s4b_09_scope.py | 設計§9.1の`END`の1行だけ |
| tests/v2_git_store/ 新規 | test_s4c_\*.py、s4c_helpers.py、s4c_worker.py（子プロセスの本体、任意）。\_\_init\_\_.pyは作らない |
| docs/implementation/V2_GIT_STORE_S4C_RESULT.md 新規 | 本段階の結果 |

これ以外は変更しない。次のものは固定する。

- パッケージ：v2_core、v2_persistence（local/を含む）、v2_recovery、v2_history、v2_history_ops、v2_history_restart、v2_history_restore、v2_history_diagnose、v2_history_adopt、v2_history_publish、v2_history_local、v2_history_maintain、v2_daily_run、**v2_notify**。
- 既存の試験・ヘルパー。新しいヘルパーからimportするのはよい。
- 範囲試験：test_sc_01〜03、b17、r3_07、r4_09、d5_08、a5_08、test_c1_09〜test_c4_09、test_s4a_09、test_s4b_09（上の1行を除く）。
- 設定・依存・workflow・main.py・研究・STATUS/ROADMAP/MODEL_POLICY/CLAUDE等。

次の範囲へ広げない。

- ネットワーク越しのgit（https・ssh・git://のリモート）、GitHubのAPI、資格情報・トークン・環境変数の読込み（`Git`が子プロセスの環境を作るための親の環境の写しを除く）、入口のスクリプト・CLI、workflow。
- 台帳の参照の読込み（S4-D）。巻戻しの表示（設計§8、S4-E）。
- 時間を置いた再試行、sleep、時計の読込み、強制push、参照の削除。
- 受領済みのパッケージの変更。設計§9.2の提案の修正。

範囲外の変更が必要になった場合や、固定文書に矛盾を見つけた場合は、その変更を行わずに止める。反例・影響・最小差分案を報告する。

## 3. 固定する振る舞い

1. **公開名**：`Git`、`GitError`（CoreErrorの子）、`GitHistoryStore`、`GitOutbox`、pushの結果の定数`OK`・`REJECTED`・`UNCERTAIN`。
2. **引数**：`workdir`は絶対パスの既存のディレクトリ。`ref`は設計§3の形（英小文字・数字・`-`、1〜40文字、`-`で始まらない）。`clock`は呼べるもので、時刻帯つきのdatetimeを返す。`timeout`は正の整数。`parent`は絶対パスの既存のディレクトリでリンクでないこと。違えば、gitを起動する前に`GitError`（`git_args_invalid`）。reprにパス・URLを出さない。
3. **gitの起動**：設計§4。子プロセスを起動するのは`git.py`だけで、`subprocess.run`に引数の配列を渡す（`shell`なし）。毎回`-c core.autocrlf=false -c commit.gpgsign=false`。環境は親の環境の写しから`GIT_`で始まる変数を除き、`GIT_TERMINAL_PROMPT=0`・`LC_ALL=C`・`GIT_CONFIG_NOSYSTEM=1`・作者とコミッターの固定の名前とメールを足したもの。コミットの日時は注入した時計の値。
4. **作業場所を変えない**：コミットは`hash-object`・`mktree`・`commit-tree`で作る。取得は`+refs/heads/<ref>:refs/v2remote/<ref>`だけ。`checkout`・`reset`・`add`・`commit`・`merge`・`rebase`・`update-ref refs/heads/…`・`symbolic-ref`を使わない。作業ツリー・インデックス・HEAD・`refs/heads/*`が変わらない。
5. **push**：`["push", "--porcelain", remote, "<40桁のSHA>:refs/heads/<ref>"]`の形だけ。設計§4の3の表で3つに分ける。時間切れはUNCERTAIN。
6. **取得**：設計§4の4。失敗のときは`ls-remote --heads`で、参照が無いことが確かなときだけNone。ほかは`GitError`。
7. **出力**：gitの標準出力・標準エラーを、例外の引数・repr・報告・文面・ファイル・コミットのメッセージに入れない。`GitError`・`LocalStoreError`・`NotifyError`の引数は固定の語だけ。例外処理の中で新しい例外を投げない（値を作って外で投げ、`__context__`を残さない。C4-19と同じ）。
8. **GitHistoryStore**：設計§5の表。誤りは既存の`LocalStoreError`のコードだけ（`store_io_error`、`store_uninitialized`、`store_layout_unsupported`、`publication_stale`、`store_commit_uncertain`、`already_initialized`）とC-2の公開の検査の誤り。`publish`は`check_publication`を取得した今のバイトに対して呼ぶ。`reconcile`は取得し直したバイトで`reconcile_publication`を返すだけで、前のpushのSHAを覚えない。C-2・C-3の非公開の名前を使わない。
9. **GitOutbox**：設計§6。`LocalOutbox`の子クラスで、上書きは`load`・`resend_ids`・`claim`・`record`（と`__init__`・`initialize`・`__repr__`）だけ。基底の非公開の名前（`_`で始まる属性）を呼ばない・読まない。写しは`parent`の中に自分で`mkdtemp`し、基底のモードは`file_sync_only`。キーワード専用の`_ops`（試験用）は基底へそのまま渡す。作り直しで消すのは写しの中だけ。`load`は取得の失敗で例外を出さずDAMAGEDを返す。作成は最大4回。参照が無いoutboxは、読込みDAMAGED・作成`NotifyError`。
10. **リモートのファイルの中身**：`v2-state`の`history.json`は`history_bytes`の出力そのもの。`v2-outbox`の意図・結果は、S4-Bの`LocalOutbox`が書くバイトそのもの（同じ名前）。
11. **コミット**：`v2-state`は親1つで`history.json`だけを変える（初期化は親なし）。`v2-outbox`は親1つでファイルを1つ足す（初期化は親なしで印の1ファイル）。作者・コミッターは固定、日時は時計の値、メッセージは固定の語と短いhash・ファイル名だけ。

## 4. 受入条件 S4C-01〜S4C-18

各IDは機能項目であって、テスト件数ではない。新規Nは実測する。期待値は、C-3の保存先での同じ場面の結果、C-2の関数、試験側で`git`を直接呼んで読んだバイト、偽の送信先の記録から作る。実装の出力をコピーしない。試験のリモートはすべて一時ディレクトリのbareリポジトリで、パスに印（例：`SECRETMARK_`）を入れる。

| ID | 必須確認 |
|---|---|
| S4C-01 回帰 | 既存の17スイート計2,480件を、完全なクローンで維持する（S4-Aまでの16スイート2,349件とS4-B 131件）。test_s4b_09の1行の固定を含み、件数は同じ |
| S4C-02 引数 | §3の2の各誤りで`GitError`になり、gitを起動しない（偽の`run`で起動の回数0を確かめる）。reprにパス・印が出ない |
| S4C-03 push | 本物のbareリポジトリで、(a) 早送りOK、(b) 早送りでない→REJECTED、(c) 既にある参照の作成→REJECTED、(d) リモートのpre-receiveで拒否→REJECTED、(e) post-receiveで時間切れより長く待つ（参照は更新済み）→UNCERTAIN、(f) 終了コードが0でないのに記号がOK（偽の`run`）→UNCERTAIN。`--quiet`を付けると(a)がUNCERTAINになることを欠陥注入で確かめる |
| S4C-04 取得 | 参照あり→SHA、参照なし→None、リモートのパスが無い→`GitError`。取得の前後で、作業場所の`HEAD`・`refs/heads/*`・インデックス・`git status --porcelain`が同じ |
| S4C-05 履歴の初期化と読込み | 未初期化→`store_uninitialized`。GENESISで初期化→`read`の履歴とリモートの`history.json`のバイトが、同じ公開をC-3の保存先に初期化した場合と一致。2回目の初期化→`already_initialized`。`history.json`の無い参照→`store_layout_unsupported` |
| S4C-06 C-3との一致 | 複数日の追いつき（S4-Aの試験の世界）を、C-3の保存先と`GitHistoryStore`でそれぞれ`run_morning`し、RunReportと最後の`history.json`のバイトが一致する。再実行も一致する |
| S4C-07 先を越された保存 | 読んだ後に別のクローンが先に保存→`publication_stale`でSTOPPED。`morning_job`の判定なしの文面に「同時の実行」の注記がある。リモートの履歴は別のクローンの保存のまま |
| S4C-08 成否不明 | (a) 届いた→reconcileがPUBLISHED→DONE。(b) 届かない→`run_publish_not_published`。(c) 届いた後に別の保存が続いた→PUBLISHED_THEN_EXTENDED。(d) リモートが別の内容（早送りの別の公開）→`run_publish_conflict`。(a)は(e)のpost-receiveの方法で、本物のpushで作る |
| S4C-09 リモートに届かない | 各段（取得、公開のpush、reconcile、outboxの読込み・作成・結果）の前にリモートのパスを消す・名前を変える。`run_morning`はSTOPPED（`store_io_error`）、`morning_job`はJobReportを返し、送信は0回。例外が漏れない。報告・文面・例外の引数・reprに印が出ない |
| S4C-10 別のクローンでも1通 | 2つのクローンで順に`morning_job`→送信1回。2つ目のクローンの`outbox_status`がSENT。outboxの参照のファイルが、S4-Bの`LocalOutbox`で同じ場面を作った場合と同じ名前・同じ構造 |
| S4C-11 作成の決め方 | (a) 写しを作り直した後に別の鍵のファイルがpushされた→作り直してもう一度→成功。(b) 同じ鍵を別の実行が先に作った→None（送らない）。(c) pushがUNCERTAINで実は届いた→自分の作成として送る（送信1回）。(d) UNCERTAINで届いていない→もう一度。(e) 4回とも別の鍵で進められた→`NotifyError`→CLAIM_FAILEDで送らない。(f) 結果のpushが失敗→RESULT_NOT_RECORDED、次の実行はUNKNOWNと読み送らない |
| S4C-12 outboxの初期化と壊れ | (a) 参照なし→状態DAMAGED、`morning_job`は送らない、作成は`NotifyError`。(b) 初期化の2回目は拒む。(c) 試験側でリモートに壊れた意図（空・JSONでない・鍵の違い）をコミット→DAMAGEDで送らない。(d) 基底の作成の途中の失敗（偽のFileOpsを写しへ）→そのファイルがリモートに無い |
| S4C-13 手動の再送 | `GitOutbox`の上で、S4B-14の(a)〜(f)と同じ結果（UNKNOWN・NOT_SENTの元に1通、同じidは送らない、SENTがあれば拒む、元が無い・DAMAGEDは拒む、再送がUNKNOWNなら別のidで次）。`resend_ids`の取得の失敗はCLAIM_FAILEDになり、送らない |
| S4C-14 同時の実行 | 子プロセス2〜4個（各自のクローン、1つのbareリポジトリ、ファイルの合図で同時に開始）を各10回以上。(a) 同じDの判定ありは1通まで、判定なしは1通まで。(b) 履歴の同じDのAPPLYは1つだけ（試験側でリモートの`history.json`を読む）。(c) 判定なしの文面に「同時の実行」の注記。(d) 同じ再送idを同時に→1通まで。回数と結果を結果文書に記録する |
| S4C-15 コミットの形 | 試験側で`git cat-file`・`ls-tree`を読む。`v2-state`の各コミットは親1つ（初期化は0）で木は`history.json`だけ。`v2-outbox`の各コミットは親1つで、親の木にファイルが1つ足されただけ。作者・コミッター・日時が§3の11のとおり。どの参照も早送りだけで進んだ（各先頭が前の先頭の子孫） |
| S4C-16 静的な範囲 | ランタイムのimportが許可だけ（標準ライブラリのos・re・shutil・stat・subprocess・tempfile、v2_core.errors、v2_history_publish、v2_history_local、v2_persistence.local.errors、v2_notify）。subprocessは`git.py`だけ。socket・urllib・http・time・random・threading・secretsの使用なし。`datetime.now`・`utcnow`・`today`・`sleep`の呼出しなし。`shell=True`なし。pushの引数の配列が§3の5の1か所だけで、`--force`・`-f`・`--force-with-lease`・`--mirror`・`--delete`・`--quiet`・`+`で始まる参照指定が無い。他のパッケージのオブジェクトの`_`で始まる属性を使わない |
| S4C-17 機密 | リモートのパスに印を入れ、S4C-03〜14の全場面で、例外の文字列・引数・repr、RunReport・JobReport・ResendReport、文面、outboxのファイル、コミットのメッセージに印が出ない。`GitError`の引数が固定の語だけ（静的にも確かめる） |
| S4C-18 範囲試験 | 新しい範囲試験（START＝6cab050、END＝None、REV＝END or "HEAD"、FilesChanged）が、§2の変更だけを許す。test_s4b_09の差分を自分の差分のハンクとして固定する。範囲の鎖が`…→6ad609f→6cab050→（S4-C）`で通る。ENDだけを固定して開いた範囲を外すと鎖の試験が失敗する手順を、結果文書に記録する |

## 5. 限定欠陥注入

1件ずつ壊して試験の感度を確かめる。結果は検出・等価・未検出・準備失敗に分け、等価には根拠を書く。

1. pushに`--force`を付ける（または参照指定に`+`）。
2. pushに`--quiet`を付ける。
3. UNCERTAINをOKとして扱う。
4. REJECTEDを`store_commit_uncertain`にする。
5. 取得の失敗を「参照なし」（None）とする。
6. pushの拒否を新しいコード（`store_ref_moved`等）にする。
7. `reconcile`が取得し直さず、前に読んだバイトで判定する。
8. `publish`で`check_publication`を呼ばずにコミットを作る。
9. コミットの木を作るとき、親の木のほかのファイルを落とす。
10. 取得を`refs/heads/<ref>`へ行う（作業場所の参照が動く）。
11. `GitOutbox.load`が取得の失敗で例外を出す。
12. 作成のpushが拒否されたとき、取得し直さずに「他が作った」とする。
13. 作成のpushがUNCERTAINのとき、リモートのバイトを確かめずに自分の作成とする。
14. 作成の繰り返しに上限を付けない（または1回にする）。
15. 写しの作り直しで、前の写しのファイルを消さない。
16. 参照が無いoutboxを空のoutboxとして読む。
17. `GitError`の引数にgitの標準エラーを入れる。
18. 環境から`GIT_`の変数を除かない（試験で`GIT_DIR`を別の場所に向けて検出する）。

## 6. 環境・結果保存・停止

- Python 3.10/3.11/3.12/3.13で、完全な版を記録する。gitの版を記録する。既存の隔離環境を使う。依存・設定・workflowを変更しない。
- 試験は一時ディレクトリの中だけでbareリポジトリとクローンを作る。ネットワークのリモートを使わない。利用者のgitの設定（~/.gitconfig）に依存しないよう、試験側のgitの呼出しにも`-c`で必要な設定を渡す。
- 最終コードは、core.autocrlf=falseの別クリーンクローン（完全な履歴）で試験する。
- `git add`の前に\_\_pycache\_\_を消し、PYTHONDONTWRITEBYTECODE=1で実行する。
- Windowsがある場合は、新規N、S4-B 131、S4-A 96、範囲の鎖34を実行する。実Windowsで行うまで未実施と書く。ユーザーPC・物理電源断・GitHubのリモートは未実施と書く。

新規の実行例：

    <python> -B -W error::ResourceWarning -m unittest discover -s tests/v2_git_store -p "test_s4c_*.py" -v

結果文書には、次を記す。

- 実際のモデル設定とeffort。gitの版。
- 固定資料の完全SHAと3つのblob。開始・試験・最終のSHA。
- ランタイムの全文の場所と行数。
- test_s4b_09の差分の全文。
- 試行の下書き（設計§10）との違いと、その理由。
- 受入とテスト名の対応。
- 全スイートの件数・失敗・error・skip・終了コード。
- 変異の一覧と分類。
- S4C-14の回数と結果、S4C-09の場面の一覧、S4C-18の手順と結果。
- リモートのコミットの例（`git log --format=…`と`ls-tree`の写し。パスは伏せる）。
- 未実施の事項。

保存と停止の手順：

1. 最後のコード・試験をSHAで固定する。
2. 別クリーンクローンで成功を確かめた後、結果文書1本だけを別のコミットとして加える。
3. 新しい自分の実装ブランチだけをpushする。最後の差分が結果文書だけであることを確かめて、停止する。

PR・マージ・Actions・本番・非公開リポジトリの作成・GitHubへの状態のpush・実際の送信・S4-D以降へは進まない。

## 7. 読取専用の保護参照

次の99参照を、開始時と保存・push後に完全SHAで照合する。S4-Bの依頼書の92参照に、S4-Bの資料・レビュー・実装・受領の7本を加えたものである。本書と設計を保存した資料ブランチdocs/v2-git-store-s4c-20261105についても、受け取った版の完全SHAを1本加える（実装時は100参照。設計のレビュー・再レビューの参照があれば、それも加える）。

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
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |
| docs/v2-history-s3b4-review-20261102 | 814b86190562475286300d7e6df3a749a9140331 |
| fix/v2-history-restore-plan-s3b4-review-20261102 | ac219801d290ebb59b720f37a086103b6e1251c9 |
| docs/v2-history-s3b4-fix-rereview-20261102 | 1f7d8c13ee79aa41eb79bd612c4438355ae320ab |
| docs/v2-history-s3b5-20261102 | 5c9e1e89c8f9d33689e9bc67e266fa6031507136 |
| docs/v2-history-s3b5-review-20261102 | 842d44b192a03531f6d3cb896d8281733814899f |
| docs/v2-history-s3b5-v2-rereview-20261102 | 6a7210c2e278e604b953acf904cf9e796c2ce710 |
| feat/v2-history-diagnose-s3b5a-20261102 | c8ba08f15ea28248a9fe7924f32ce136fc16d5e6 |
| docs/v2-history-s3b5a-review-20261102 | 808ffbd0e9a55ce59f819f4580cb228f5a2cc4c9 |
| docs/v2-history-s3b5b-20261102 | 5d21c10885a97e8d0cd614444f0da9b11ca322a5 |
| feat/v2-history-adopt-s3b5b-20261103 | 782debc2a901a421a2b5205f9dd8ad4f0b484b01 |
| docs/v2-history-s3b5b-review-20261103 | 92630a3d5233f14900c7472dc754850701a56b61 |
| fix/v2-history-adopt-s3b5b-review-20261103 | b626c98af5f01bc94e7b41d86aadde9663695eb9 |
| docs/v2-history-s3b5b-fix-rereview-20261103 | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b |
| docs/v2-scope-range-freeze-20261103 | 08072cc47aa12340ed947d40f02ca8741a4060d6 |
| feat/v2-scope-range-freeze-20261103 | dda7eb706637adc5f6dd37513e4b6ca360fde2ba |
| docs/v2-scope-range-freeze-review-20261103 | fa4b232810569f4512d09f244ef50f9685ff0c95 |
| fix/v2-scope-range-freeze-review-20261103 | bfbde7a7854bf91a77fb58737c24b19c6507453a |
| docs/v2-scope-range-freeze-fix-rereview-20261103 | 9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d |
| docs/v2-consume-c1-review-20261103 | b473db46ad3dbf3ad76fa76f50c49b03b558936d |
| docs/v2-consume-s3c-20261103 | a6340c3937092e4cb658913b9acfb4973a084326 |
| feat/v2-history-consume-c1-20261103 | de6549acb4ecea759cc771300fd0bef59dd5456a |
| docs/v2-history-publish-c2-20261103 | 9dd64b8eb07ad35dd23c011ed2dbb1196307f542 |
| docs/v2-history-publish-c2-review-20261103 | a6e783e57c1de5dd92e6b43cfc416a1d79a672eb |
| docs/v2-history-publish-c2-impl-review-20261103 | a91a9ed31481e97cc8b56c2396f86d957fa567e0 |
| docs/v2-history-publish-c2-revision-20261103 | 081637e95160a23aab5ea0fc3a2edd01976abba4 |
| feat/v2-history-publish-c2-20261103 | d6b0332500af8d8d46ddaae6c7fda39ee38a03db |
| docs/v2-history-local-c3-20261104 | 6ad98521a788297f8db64468337c71767dca7304 |
| docs/v2-history-local-c3-review-20261104 | 213bcb7f05d2e1be5f04d529289b437367457f3e |
| feat/v2-history-local-c3-20261104 | 6d69bd714bf5cf7b54e63208d2ed6691aff7bf0a |
| docs/v2-history-local-c3-impl-review-20261104 | 2049e1056f76e606343c3eb0fbbe82e531988ca6 |
| docs/v2-history-maintain-c4-20261104 | d11b87597ef4035f5fee0ffc8c9fa859f82fe00f |
| docs/v2-history-maintain-c4-review-20261104 | 74c93b11236f83508c354dee9a38df9cc38a1c67 |
| docs/v2-history-maintain-c4-v2-rereview-20261104 | 8f39111369531b320f20320dac733775c87f3e5c |
| feat/v2-history-maintain-c4-20261104 | 2e6ba5ff20a7fa0340f8d46e2239af3c43258bbb |
| docs/v2-history-maintain-c4-impl-review-20261104 | 906a70a2877cf135947498f53c0750cb3c43156d |
| docs/v2-history-maintain-c4-fix-rereview-20261104 | 8d02abf1622714cdeb38df6bd5bab91787249eb7 |
| docs/v2-s4-daily-run-20261104 | 7542a1829a8c16e0842d53a846dc23b83f6d2ee6 |
| docs/v2-s4-daily-run-review-20261104 | dd60f6f22d773561cfcc3ab09c868e02d9d0a973 |
| feat/v2-daily-run-s4a-20261104 | 6ad609fe52b50565103e56c598505cac85601216 |
| docs/v2-daily-run-s4a-impl-review-20261104 | 3e3fd475a486a26eb9fd234e11c4950a04e55102 |
| docs/v2-notify-s4b-20261105 | 4c54e01b218148e49e5ae283e7f0bf2fc52edb46 |
| docs/v2-notify-s4b-fix-rereview-20261105 | 77e9cf87c7eefb0741ed17eab5658a1da1f15032 |
| docs/v2-notify-s4b-fix2-rereview-20261105 | 9b4d786a14ab10ef5c0a2525191bf7b4753f4bbf |
| docs/v2-notify-s4b-impl-review-20261105 | 1f914f982a684253cba6726489d43408aeda5e79 |
| docs/v2-notify-s4b-review-20261105 | 1122052fb15d9e6de516fb9be9aea90bc48f3842 |
| docs/v2-notify-s4b-v2-rereview-20261105 | f10e719e05344379f370860d424b66dc01c0ea6a |
| feat/v2-notify-s4b-20261105 | 6cab0506c408d194c63b656713e4a0a7d62c3ba1 |

本書の作成時（2026-11-05、日本時間）に、上の99参照がリモートと完全SHAで一致することを、作業の開始時に確かめた。資料ブランチのpush後の照合は、下の追記に記す。

追記（2026-11-05）：資料ブランチdocs/v2-git-store-s4c-20261105の最初のpush（68c030bdcad1172f66389521cdcd4fe721f83df3）の後にも、上の99参照がリモートと完全SHAで一致することを確かめた。

## 8. 採用単位

設計§12のD-1〜D-9と、本書の変更境界・受入・欠陥注入・結果保存を、一組で判断する。

- D-1：S4-Cの範囲。
- D-2：参照の配置。
- D-3：gitの層。
- D-4：履歴の保存先（成否不明は内容だけで判定）。
- D-5：outbox（`LocalOutbox`の子クラス）。
- D-6：再試行（U-12）。
- D-7：巻戻しの表示（S4-Cでは入れない）。
- D-8：前の段階の提案の扱い（S4-BのEND固定、P-01〜P-04、R2-P01）。
- D-9：担当（Sonnet 5.5・high）。

今回の文書作成と、設計§10の一時環境の試行は、その採用ではない。S4-Bの受領と「進めて」を、S4-Cの実装承認にしない。非公開リポジトリの作成・GitHubへのpush・S4-D以降・本番の承認も含まない。
