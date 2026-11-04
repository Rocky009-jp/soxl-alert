"""Re-run the fuzz with the same seed and explain the successes and the history_invalid cases (diff of body keys)."""
import os, sys, copy
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2]]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "c3i_handmade_fuzz.py")).read()
src = src.replace('problems.append((i, op, "success for a mutated body"))',
                  'problems.append((i, op, "success", c.source, sorted(k for k in set(body)|set(c.pub.body) if body.get(k, "<absent>") != c.pub.body.get(k, "<absent>")), [(k, body.get(k)) for k in ("request_id","plan_hash","d") if body.get(k) != c.pub.body.get(k)]))')
src = src.replace('codes[(op, e.code)] += 1', 'codes[(op, e.code)] += 1\n        (e.code == "history_invalid") and problems.append((i, op, "hi", c.source, body.get("mode") if isinstance(body, dict) else body, H.raw(root)[:30] if H.HIST in os.listdir(root) else None))')
exec(compile(src, "fuzz", "exec"))
