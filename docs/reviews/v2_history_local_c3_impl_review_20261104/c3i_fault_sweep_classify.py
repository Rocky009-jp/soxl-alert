import ast, collections, sys
rows = [ast.literal_eval(l.strip()) for l in open(sys.argv[1]) if l.startswith("   (")]
c = collections.Counter()
for r in rows:
    c[(r[3], r[4], r[6])] += 1
for k, v in sorted(c.items()):
    print(k, v)
