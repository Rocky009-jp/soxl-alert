# python3 make_tables.py  -> key_candidates_by_window.csv and tables.md (reads summary.csv / robustness_by_rule.csv)
import csv
r=list(csv.DictReader(open('summary.csv')))
rb=list(csv.DictReader(open('robustness_by_rule.csv')))
keys=['NO_SELL_I0','NO_SELL_I25','NO_SELL_I100','P20_ONLY_I25_R25','P20_OR_R75_I25_R25','P20_ONLY_I25_R100','P20_OR_R65_I25_R100','P30_ONLY_I25_R25','P40_ONLY_I25_R25','P60_ONLY_I25_R25']
W=['W2011','W2013','W2015','W2017','W2019','W2021','W2023','W2024_CURRENT']
rows=[];md=[]
for d in ['0','1']:
  md.append(f'\n### F&G遅延{d}日：税引後清算額（千ドル、開始1万ドル）。括弧は売却回数\n')
  md.append('| 区間 | 約定 | '+' | '.join(keys)+' | その区間の1位 |')
  md.append('|'+'---|'*(len(keys)+3))
  for w in W:
    for ex in ['NEXT_CLOSE_PROXY','NEXT_OPEN_BRIDGE']:
      g={x['candidate_id']:x for x in r if x['window']==w and x['fg_delay']==d and x['execution']==ex}
      if not g: continue
      best=min(g.values(),key=lambda x:(int(x['rank_after_tax']),x['candidate_id']))
      md.append(f"| {w} | {'翌終値' if ex=='NEXT_CLOSE_PROXY' else '翌寄付き'} | "+' | '.join(f"{float(g[k]['after_tax_liquidation'])/1000:.1f} ({g[k]['sell_count']})" for k in keys)+f" | {best['candidate_id']} {float(best['after_tax_liquidation'])/1000:.1f} |")
      for k in keys: rows.append({k2:g[k][k2] for k2 in ['window','fg_delay','execution','candidate_id','after_tax_liquidation','final_total_pretax','sell_count','rank_after_tax','ratio_to_NO_SELL_I25_after_tax','month_ends_beating_NO_SELL_I25_after_tax','month_ends']})
for d in ['0','1']:
  md.append(f'\n### F&G遅延{d}日：過去7区間で「売却なし(初回25%)」を税引後で上回った区間数（翌終値）\n')
  md.append('| 候補 | 上回った区間 | 1位の区間 | 比率 最小/中央/最大 | 今の期間 翌終値比 | 今の期間 翌寄付き比 |')
  md.append('|---|---|---|---|---|---|')
  for x in sorted([x for x in rb if x['fg_delay']==d],key=lambda x:(-int(x['past_windows_beating_NO_SELL_I25']),-float(x['median_ratio_past']),x['candidate_id'])):
    md.append(f"| {x['candidate_id']} | {x['past_windows_beating_NO_SELL_I25']}/7 | {x['past_windows_rank1']} | {float(x['min_ratio_past']):.2f} / {float(x['median_ratio_past']):.2f} / {float(x['max_ratio_past']):.2f} | {float(x['current_close_ratio']):.2f} | {float(x['current_open_ratio']):.2f} |")
with open('key_candidates_by_window.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
open('tables.md','w').write('# 表（make_tables.py が生成）\n'+'\n'.join(md)+'\n')
