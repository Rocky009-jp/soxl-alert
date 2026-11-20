import json, sys
root, cases_dir, golden = sys.argv[1:4]
sys.path.insert(0, cases_dir)
import ratio_cases as R
out = R.build(root)
g = json.load(open(golden, encoding="utf-8"))
print("keys equal:", sorted(out) == sorted(g), len(out))
print("all equal:", all(out[k] == g[k] for k in g))
