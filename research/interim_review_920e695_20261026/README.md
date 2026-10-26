# 920e695の限定確認

[対応確認レビュー](../../docs/reviews/INTERIM_FIX_REVIEW_920e695.md)を参照。実装者の95件とは別に、主担当が4経路を確認した記録です。

固定候補920e69571cf4feda09f3f2f560e96fcb9cb09d50のソースを用意し、pandas・numpyのあるPythonで実行します。

```text
python review_probes.py --source-dir <pinned-candidate-directory> --output <result-json-path>
```

依存を別場所へ導入済みの場合だけ --site-packages <directory> を指定できます。Requestsは試験プロセス内でスタブへ置き換えます。実API・curl・サーバを呼ぶコードはありません。正常・古い負価格・最新欠損・不正日付を検査します。

記録環境はPython3.12.10／pandas2.3.3／numpy2.2.6。実Requests、YAML/bash、Python3.10、元95件の独立再実行ではありません。
