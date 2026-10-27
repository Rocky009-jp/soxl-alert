import json,csv,io,hashlib
from pathlib import Path
src=Path('research/historical_daily_data_20261027')
names=['specification.json','source_refs.json','attempts.json','quality_check.json','incidental_ohlc_concordance.json','digrin_vs_stored_adjclose_month_end.json','data_candidates/B_digrin_monthly_SOXL_secondary_extraction.csv','data_candidates/README.md']
p={name:(src/name).read_bytes().decode('utf-8') for name in names}
d=json.loads(Path('research/SOXL_exit_study_20261023/data/daily.json').read_text()); s=d['funds']['SOXL']; dates=d['date']
refs=json.loads(p['source_refs.json']); checks={}
for name,key in [('specification.json','specification')]:
 checks[name]=hashlib.sha256(p[name].encode()).hexdigest()==refs[key]
for name,want in refs['derived_files'].items(): checks[name]=hashlib.sha256(p[name].encode()).hexdigest()==want
for name,want in refs['data_candidates'].items(): checks['data_candidates/'+name]=hashlib.sha256(p['data_candidates/'+name].encode()).hexdigest()==want if 'data_candidates/'+name in p else 'not staged'
checks['daily_input_sha']=hashlib.sha256(Path('research/SOXL_exit_study_20261023/data/daily.json').read_bytes()).hexdigest()==refs['stored_inputs_for_calendar_crosscheck']['daily.json']
inc=json.loads(p['incidental_ohlc_concordance.json'])['rows']; oh=s['ohlcv']; keys=['open','high','low','close','volume']
inc_check=[]
for r in inc:
 i=oh['date'].index(r['date']); vals=[oh[k][i] for k in keys]
 inc_check.append({'date':r['date'],'stored_fields_match':vals==r['stored'],'ohlc_comparison_correct':(r['public'][:4]==vals[:4])==r['ohlc_equal'],'volume_rel_diff_correct':abs(abs(r['public'][4]/vals[4]-1)-r['volume_rel_diff'])<1e-12})
months=json.loads(p['digrin_vs_stored_adjclose_month_end.json'])['rows']; month_check=[]
for r in months:
 ix=max(i for i,t in enumerate(dates) if t.startswith(r['month']))
 month_check.append({'month':r['month'],'stored_date_correct':dates[ix]==r['stored_month_end_date'],'stored_adjclose_correct':s['adjClose'][ix-s['start']]==r['stored_adjClose'],'reported_rel_diff_correct':abs(abs(r['digrin_adjusted']-r['stored_adjClose'])/r['digrin_adjusted']-r['rel_diff'])<1e-12})
out={'source_commit':'6a836567d92d1510c6ee507fefc0844e481ec1dd','simulate_calls':0,'scope':'saved-number arithmetic and input matching; external extraction and page completeness NOT independently verified','hash_checks':checks,'stored_calendar_rows_in_target':sum('2021-03-03'<=x<='2024-09-30' for x in dates),'month_rows':len(months),'max_month_rel_diff_pct':max(abs(r['rel_diff']) for r in months)*100,'monthly_checks':month_check,'incidental_checks':inc_check,'ohlc_equal_rows':sum(r['ohlc_equal'] for r in inc),'ohlcv_exact_rows':sum(r['public']==r['stored'] for r in inc)}
Path('research/historical_daily_data_review_20261027/verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))

