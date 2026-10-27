# python3 compare_with_052ee96.py <path to 052ee96 research/after_tax_periods_20261027/summary.csv>
# Reads the NEXT_CLOSE_PROXY rows of window W2024_CURRENT (start 2024-10-01, Adj Close fills, no cash distributions) and compares them with
# this study's same-accounting NEXT_CLOSE rows (original Close fills, cash distributions, same fixed 3% MMF). Descriptive reconciliation only.
import csv, sys
old = {(r['candidate_id'], r['fg_delay']): r for r in csv.DictReader(open(sys.argv[1])) if r['window'] == 'W2024_CURRENT' and r['execution'] == 'NEXT_CLOSE_PROXY'}
new = {(r['candidate_id'], r['fg_delay']): r for r in csv.DictReader(open('summary.csv')) if r['evaluation_execution'] == 'NEXT_CLOSE' and r['start'] == '2024-10-01'}
out = []
for k in sorted(new):
    if k not in old: continue
    a, b = float(old[k]['after_tax_liquidation']), float(new[k]['liquidation_after_tax_same_day'])
    out.append({'candidate_id': k[0], 'fg_delay': k[1], 'liq_052ee96_adjclose_close_proxy': round(a, 2), 'liq_same_accounting_close': round(b, 2), 'diff': round(b - a, 2), 'diff_pct_of_052ee96': round((b / a - 1) * 100, 2)})
w = csv.DictWriter(open('compare_with_052ee96.csv', 'w', newline=''), fieldnames=list(out[0]))
w.writeheader(); w.writerows(out)
for r in out: print(r)
