// node build_price_checks.mjs  -> price_checks.csv  (stored values read from the fixed exit-study daily.json; fetched values transcribed from evidence/fetch_log.md)
import fs from 'node:fs';
const d=JSON.parse(fs.readFileSync('../SOXL_exit_study_20261023/data/daily.json','utf8')).funds.SOXL.ohlcv;
const dates=['2024-10-07','2024-12-20','2026-06-30','2026-07-01','2026-07-29','2026-07-30','2026-07-31','2026-08-10'];
const items=['open','high','low','close'];
const FC={ // financialcontent.com/quote/NY:SOXL/historical, fetched 2026-10-26 via WebFetch (summarised, not raw bytes)
 '2026-07-29':[107.62,112.67,91.50,91.99],'2026-07-30':[107.38,118.00,105.12,114.72],'2026-07-31':[129.90,133.88,112.42,114.72],'2026-08-10':[142.80,143.45,130.00,130.00]};
const DG={'2026-06-30':{close:266.71},'2026-07-31':{close:114.72}}; // digrin.com monthly "Real price" = month's last close (monthly page, not daily)
const rows=[];
for(const t of dates){const i=d.date.indexOf(t);
  items.forEach((it,k)=>{
    const stored=d[it][i];
    const mk=(src,url,val,def,indep,status)=>{const abs=val==null?'':Math.abs(val-stored),rel=val==null?'':abs/stored;
      rows.push({date:t,item:it,stored_value:stored,source:src,url,fetched_value:val??'',abs_diff:abs,rel_diff:rel,rel_diff_pct:rel===''?'':rel*100,unit:'USD per share',adjustment_definition:def,independence_from_Yahoo:indep,retrieved_at_UTC:'2026-10-26 (clock time not recorded)',status});};
    const fc=FC[t]?.[k];
    if(fc!=null)mk('FinancialContent (Stock Market JSON API)','https://www.financialcontent.com/quote/NY:SOXL/historical',fc,'Open/High/Low/Close labelled raw; separate Adjusted Close column; adjustment method not documented on page','UNKNOWN (upstream feed not named)',Math.abs(fc-stored)/stored<=5e-5?'MATCH_WITHIN_0.005PCT_SOURCE_INDEPENDENCE_UNKNOWN':'DIFFERENCE_UNRESOLVED');
    else mk('FinancialContent','https://www.financialcontent.com/quote/NY:SOXL/historical',null,'table covered 2026-07-27..2026-10-23 only','UNKNOWN','NOT_AVAILABLE_FROM_SOURCE');
    if(DG[t]?.[it]!=null)mk('Digrin monthly (Real price = month-end close)','https://digrin.com/stocks/detail/SOXL/price',DG[t][it],'monthly page; "Real price" vs "Adjusted price" not defined on page; month-end date not stated','UNKNOWN','MATCH_MONTH_END_ONLY_NOT_A_DAILY_DATE_CONFIRMATION');
  });
  if(!FC[t])dates.length; }
const keys=Object.keys(rows[0]);
// unresolved placeholders for date/items with no fetched value from any source
for(const t of dates)for(const it of items){if(!rows.some(r=>r.date===t&&r.item===it&&r.fetched_value!==''))rows.push({date:t,item:it,stored_value:d[it][d.date.indexOf(t)],source:'(none obtained)',url:'',fetched_value:'',abs_diff:'',rel_diff:'',rel_diff_pct:'',unit:'USD per share',adjustment_definition:'',independence_from_Yahoo:'',retrieved_at_UTC:'',status:'UNRESOLVED_NO_SOURCE_OBTAINED'});}
const q=v=>String(v).includes(',')||String(v).includes('"')?'"'+String(v).replaceAll('"','""')+'"':String(v);
rows.sort((a,b)=>a.date.localeCompare(b.date)||items.indexOf(a.item)-items.indexOf(b.item));
fs.writeFileSync('price_checks.csv',keys.join(',')+'\n'+rows.map(r=>keys.map(k=>q(r[k]??'')).join(',')).join('\n')+'\n');
const c={};for(const r of rows)c[r.status]=(c[r.status]??0)+1;console.log(c);
