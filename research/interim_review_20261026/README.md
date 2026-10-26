# ad83f9bの追加観測

[レビュー](../../docs/reviews/INTERIM_IMPLEMENTATION_REVIEW_20261026.md)を参照。元48件の再実行ではなく、旧候補の欠陥を確認する5観測です。修正後コードの合格試験として使わないでください。

候補ad83f9bf47c43f713e7cafb738f3de1bbb42705aのチェックアウト／ソース出力を別に用意し、pandas・numpyが導入されたPythonから実行します。

```text
python review_probes.py --source-dir <pinned-candidate-directory> --output <result-json-path>
```

依存を別ディレクトリへ導入済みの場合だけ --site-packages <directory> を指定できます。Requestsはこの試験プロセス内でスタブへ置き換えます。curlは任意で、存在しなければその観測を未実施と記録します。curlの入力は合成トークンを含む不正なループバックURLで、実Webhookを与えません。実Requestsの追従はこのスクリプトで実行せず、引数未指定だけを確認します。

記録環境はPython 3.12.10／pandas 2.3.3／numpy 2.2.6／Windows curl 8.21.0。本番Python 3.10や実装者の環境の合格を代替しません。
