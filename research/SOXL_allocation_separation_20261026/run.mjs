// node run.mjs   (Node >=22, standard library only, no network)
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load,simulate,TAX} from './engine.mjs';
import {simulate as oldSimulate} from '../SOXL_exit_study_20261023/audit_exit.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const oldDir=path.join(here,'..','SOXL_exit_study_20261023');
const spec=JSON.parse(await fs.readFile(path.join(here,'specification.json'),'utf8'));
const starts=spec.grid.starts,delays=spec.grid.fg_delay,Is=spec.grid.I_initial_trend,Rs=spec.grid.R_after_sale;
const END='2026-08-10',MAIN_STARTS=['2024-10-01','2025-01-02'];
const failures=[],checks={};
const pass=(name,ok,detail)=>{(checks[name]??={n:0,fail:0});checks[name].n++;if(!ok){checks[name].fail++;failures.push({check:name,detail});}};
const near=(a,b,tol=1e-6)=>Math.abs(a-b)<=tol;
const pct=x=>String(Math.round(x*100));
function csv(rows){
  const keys=[...new Set(rows.flatMap(Object.keys))];
  const q=v=>v==null?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':typeof v==='object'?'"'+JSON.stringify(v).replaceAll('"','""')+'"':String(v);
  return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>q(r[k])).join(',')).join('\n')+'\n';
}
function parseCsv(text){
  const rows=[];let row=[],f='',inq=false;
  for(let i=0;i<text.length;i++){const c=text[i];
    if(inq){if(c=='"'){if(text[i+1]=='"'){f+='"';i++;}else inq=false;}else f+=c;}
    else if(c=='"')inq=true;else if(c==','){row.push(f);f='';}
    else if(c=='\n'){row.push(f);rows.push(row);row=[];f='';}else if(c!='\r')f+=c;}
  if(f.length||row.length){row.push(f);rows.push(row);}
  const h=rows.shift();return rows.map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]])));
}

// ---- inputs: reuse the fixed exit-study files, hash-checked
const dataDir=path.join(oldDir,'data');
const input=await load(dataDir);
const refManifest=JSON.parse(await fs.readFile(path.join(here,'input_manifest_reference.json'),'utf8'));
for(const m of input.manifest){const r=refManifest.find(x=>x.file===m.file);pass('input_sha256_matches_manifest',!!r&&r.sha256===m.sha256&&r.bytes===m.bytes,m.file);}
const schedule=JSON.parse(await fs.readFile(path.join(here,'dividends_verified.json'),'utf8'));
const schedOld=await fs.readFile(path.join(oldDir,'dividends_verified.json'),'utf8');
pass('dividend_table_identical_to_exit_study',schedOld===await fs.readFile(path.join(here,'dividends_verified.json'),'utf8'),'');
const baseOpts={end:END,initial:10000,allowInitialReentry:true,dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy',mmfRate:.03,closeTargetNet:false,buffer:0,slippage:0};
const EXITS={P20_OR_R75:{exitMode:'OR',profitTarget:.2,exitRsi:75},P20_ONLY:{exitMode:'PROFIT_ONLY',profitTarget:.2,exitRsi:75},NO_SELL:{exitMode:'NONE',profitTarget:.2,exitRsi:75}};

// ---- candidate list (21 unique)
const candidates=[];
for(const exit of ['P20_OR_R75','P20_ONLY'])for(const I of Is)for(const R of Rs)candidates.push({id:`${exit}_I${pct(I)}_R${pct(R)}`,exit,I,R});
for(const I of Is)candidates.push({id:`NO_SELL_I${pct(I)}`,exit:'NO_SELL',I,R:null});
if(candidates.length!==21)throw new Error('candidate count');

function classify(ledger){ // INITIAL = filled REENTRY before any filled SELL
  let sold=false,bought=false;const out=[];
  for(const t of ledger){
    let cls=null;
    if(t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY'].includes(t.type)){
      if(t.type==='REENTRY'){cls=sold?'AFTER_SALE_REENTRY':'INITIAL_TREND';pass('initial_label_equals_legacy_not_bought_label',(cls==='INITIAL_TREND')===!bought,t.date);}
      bought=true;
    }
    if(t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC')sold=true;
    out.push({...t,allocation_class:cls});
  }return out;
}
function analyze(r,c,delay){
  const ledger=classify(r.ledger),daily=r.daily,p=daily.at(-1);
  const sales=ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');
  const mmfNet=ledger.filter(t=>t.type==='MMF_MONTHLY_PROXY').reduce((a,t)=>a+t.gross-t.tax,0)+p.mmf_accrued_gross*(1-TAX);
  const ent=ledger.filter(t=>t.type==='DIVIDEND_ENTITLEMENT'),pay=ledger.filter(t=>t.type==='DIVIDEND_PAYMENT_DATE_PROXY');
  const divNet=ent.reduce((a,t)=>a+t.net,0),gain=sales.reduce((a,t)=>a+t.gain,0),tax=sales.reduce((a,t)=>a+t.tax,0);
  const tag=`${c.id}|${r.cfg.start}|d${delay}`;
  pass('accounting_identity',near(r.cfg.initial+gain-tax+mmfNet+divNet+p.unrealized,p.total),tag);
  pass('terminal_date_2026-08-10',p.date===END,tag);
  pass('fresh_account_at_start',daily[0].date>=r.cfg.start&&daily[0].cash===10000&&daily[0].shares===0&&ledger.every(t=>t.date>=r.cfg.start),tag);
  pass('balance_invariants',daily.every(d=>d.cash>=-1e-7&&Number.isInteger(d.shares)&&d.shares>=0&&(d.shares>0||d.basis===0)),tag);
  pass('no_loss_or_below_2pct_sale',sales.every(t=>t.gain>=t.basis*.02-1e-7),tag);
  pass('no_negative_basis_or_price',ledger.every(t=>!(t.shares<0)&&!(t.price<0)&&!(t.basis<0)),tag);
  const entEx=ent.map(t=>t.pay_date).sort(),payEx=pay.map(t=>t.ex_date);
  pass('dividend_no_double_counting',near(divNet,pay.reduce((a,t)=>a+t.net,0)+p.dividend_receivable_net,1e-9)&&new Set(payEx).size===payEx.length&&new Set(ent.map(t=>t.pay_date)).size===ent.length,tag);
  const initCount=ledger.filter(t=>t.allocation_class==='INITIAL_TREND').length,reCount=ledger.filter(t=>t.allocation_class==='AFTER_SALE_REENTRY').length;
  if(c.exit==='NO_SELL'){pass('no_sell_has_zero_sales_and_zero_reentry',sales.length===0&&reCount===0,tag);}
  if(c.I===0)pass('I0_no_initial_trend_buy',initCount===0,tag);
  if(c.exit!=='NO_SELL'&&c.R===0)pass('R0_no_after_sale_reentry',reCount===0,tag);
  const filledBuys=ledger.filter(t=>t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY'].includes(t.type));
  const s={candidate_id:c.id,exit_id:c.exit,I_initial:c.I,R_after_sale:c.R,start:r.cfg.start,fg_delay:delay,
    final_total:p.total,net_profit:p.total-r.cfg.initial,final_total_jpy150:p.total*150,liquidation:p.liquidation,liquidation_jpy150:p.liquidation*150,
    final_shares:p.shares,final_cash:p.cash,final_market_value:p.market_value,final_basis:p.basis,final_unrealized:p.unrealized,
    mmf_net_total:mmfNet,dividend_net_total:divNet,realized_stock_gain:gain,realized_stock_tax:tax,total_order_fees:ledger.reduce((a,t)=>a+(t.fee??0),0),
    buy_count:filledBuys.length,normal_exfear_buy_count:filledBuys.filter(t=>t.type!=='REENTRY').length,initial_trend_count:initCount,after_sale_reentry_count:reCount,sell_count:sales.length,blocked_sales:r.summary.blocked_sales,
    first_buy_date:filledBuys[0]?.date??'',first_sale_date:sales[0]?.date??''};
  return {summary:s,ledger,daily};
}

// ---- main 252
const results=new Map(),key=(id,start,d)=>`${id}|${start}|${d}`;
const t0=Date.now();
for(const start of starts)for(const delay of delays)for(const c of candidates){
  const r=simulate(input.rows,{...baseOpts,start,delay,...EXITS[c.exit],initialRatio:c.I,reentryRatio:c.R??c.I,reentry:c.I});
  results.set(key(c.id,start,delay),analyze(r,c,delay));
}
const summaries=[...results.values()].map(a=>a.summary);
pass('main_run_count_252',summaries.length===252,String(summaries.length));
pass('unique_candidates_21',new Set(summaries.map(s=>s.candidate_id)).size===21,'');

// ---- rank per start x delay x terminal
const baselineId='P20_OR_R75_I25_R25';
function rankGroup(rows,field){
  const sorted=[...rows].sort((a,b)=>b[field]-a[field]);
  for(const r of rows)r._rank=1+rows.filter(x=>x[field]>r[field]+1e-7).length;
}
for(const start of starts)for(const delay of delays){
  const g=summaries.filter(s=>s.start===start&&s.fg_delay===delay);
  const base=g.find(s=>s.candidate_id===baselineId).final_total;
  rankGroup(g,'final_total');
  for(const s of g){s.rank_in_start_delay=s._rank;delete s._rank;s.delta_vs_P20R75_I25_R25=s.final_total-base;}
}
await fs.writeFile(path.join(here,'summary.csv'),csv(summaries));

// ---- month-end sensitivity (proxy; 2025-06..2026-07, last saved record per month >= start)
const months=[];for(let y=2025,m=6;!(y===2026&&m===8);){months.push(`${y}-${String(m).padStart(2,'0')}`);if(++m>12){m=1;y++;}}
const tapeLast=new Map();for(const r of input.rows){const mo=r.date.slice(0,7);if(r.date<=END&&(!tapeLast.has(mo)||r.date>tapeLast.get(mo)))tapeLast.set(mo,r.date);}
const monthRows=[],monthNotes=[];
for(const start of starts)for(const delay of delays)for(const month of months){
  if(month<start.slice(0,7))continue; // before start month: not applicable
  const grp=[];
  for(const c of candidates){
    const a=results.get(key(c.id,start,delay));const inM=a.daily.filter(d=>d.date.startsWith(month));
    if(!inM.length){if(!(start.slice(0,7)===month&&false))monthNotes.push({start,delay,month,candidate:c.id,note:'no daily records in month'});continue;}
    const d=inM.at(-1);pass('month_end_record_equals_tape_last_date',d.date===tapeLast.get(month),`${c.id} ${start} ${month} ${d.date} vs ${tapeLast.get(month)}`);
    grp.push({start,fg_delay:delay,month,month_end_proxy_date:d.date,candidate_id:c.id,exit_id:c.exit,I_initial:c.I,R_after_sale:c.R,final_total:d.total,shares:d.shares,cash:d.cash,market_value:d.market_value});
  }
  for(const r of grp)r.rank=1+grp.filter(x=>x.final_total>r.final_total+1e-7).length;
  const b=grp.find(x=>x.candidate_id===baselineId)?.final_total;
  for(const r of grp)r.delta_vs_P20R75_I25_R25=b==null?'':r.final_total-b;
  monthRows.push(...grp);
}
await fs.writeFile(path.join(here,'month_end_summary.csv'),csv(monthRows));

// ---- regression vs OLD engine (I=R) and vs stored exit-study outputs
let oldCmp=0;
for(const start of starts)for(const delay of delays)for(const ex of Object.keys(EXITS))for(const x of Is){
  const o=oldSimulate(input.rows,{...baseOpts,start,delay,reentry:x,...EXITS[ex]});
  for(const variant of ['unspecified','explicit']){
    const n=simulate(input.rows,{...baseOpts,start,delay,reentry:x,...EXITS[ex],...(variant==='explicit'?{initialRatio:x,reentryRatio:x}:{})});
    const tag=`${ex}|I=R=${x}|${start}|d${delay}|${variant}`;
    pass('legacy_IeqR_ledger_identical_to_old_engine',JSON.stringify(o.ledger)===JSON.stringify(n.ledger),tag);
    pass('legacy_IeqR_daily_identical_to_old_engine',JSON.stringify(o.daily)===JSON.stringify(n.daily),tag);
    pass('legacy_IeqR_candidates_identical_to_old_engine',JSON.stringify(o.candidates)===JSON.stringify(n.candidates),tag);
    pass('legacy_IeqR_final_total_exact',o.summary.final_total===n.summary.final_total,tag);oldCmp++;
  }
  // new grid cell with I=R must equal the old engine too
  const id=ex==='NO_SELL'?`NO_SELL_I${pct(x)}`:`${ex}_I${pct(x)}_R${pct(x)}`;
  pass('grid_cell_IeqR_matches_old_engine_total',near(results.get(key(id,start,delay)).summary.final_total,o.summary.final_total,1e-9),`${id}|${start}|d${delay}`);
}
// stored summary.csv (delay 0) and sensitivity.csv (delay 1, first two starts)
const stored=parseCsv(await fs.readFile(path.join(oldDir,'summary.csv'),'utf8'));
let storedCmp=0;
for(const row of stored){
  const x=Number(row.reentry),ex=row.exit_id;if(!Is.includes(x)||!(ex in EXITS))continue;
  const id=ex==='NO_SELL'?`NO_SELL_I${pct(x)}`:`${ex}_I${pct(x)}_R${pct(x)}`;
  pass('stored_exit_study_summary_final_total',near(results.get(key(id,row.start,0)).summary.final_total,Number(row.final_total),1e-6),`${id}|${row.start}`);storedCmp++;
}
const storedSens=parseCsv(await fs.readFile(path.join(oldDir,'sensitivity.csv'),'utf8')).filter(r=>r.scenario==='FG_ONE_DAY_DELAY_STRESS');
let sensCmp=0;
for(const row of storedSens){
  const x=Number(row.reentry),ex=row.exit_id;if(!Is.includes(x)||!(ex in EXITS))continue;
  const id=ex==='NO_SELL'?`NO_SELL_I${pct(x)}`:`${ex}_I${pct(x)}_R${pct(x)}`;
  pass('stored_exit_study_delay1_final_total',near(results.get(key(id,row.start,1)).summary.final_total,Number(row.final_total),1e-6),`${id}|${row.start}`);sensCmp++;
}
// stored ledgers: dates, shares, prices, fees, taxes, basis
let ledgerFiles=0;
for(const f of (await fs.readdir(oldDir)).filter(f=>/^ledger_\d{4}-\d{2}-\d{2}_(P20_OR_R75|NO_SELL)_(0|0p25|1)\.csv$/.test(f))){
  const m=f.match(/^ledger_(\d{4}-\d{2}-\d{2})_(P20_OR_R75|NO_SELL)_(0|0p25|1)\.csv$/),x=m[3]==='0p25'?.25:Number(m[3]);
  const id=m[2]==='NO_SELL'?`NO_SELL_I${pct(x)}`:`${m[2]}_I${pct(x)}_R${pct(x)}`;
  const old=parseCsv(await fs.readFile(path.join(oldDir,f),'utf8')).filter(r=>r.status==='FILLED_DIAGNOSTIC');
  const nw=results.get(key(id,m[1],0)).ledger.filter(t=>t.status==='FILLED_DIAGNOSTIC');
  let ok=old.length===nw.length;
  for(let i=0;ok&&i<old.length;i++){const a=old[i],b=nw[i];
    ok=a.date===b.date&&(a.type===b.type||(a.type==='INITIAL_TREND'&&b.allocation_class==='INITIAL_TREND'))&&['shares','price','fee','tax','basis','gain','cost'].every(k=>a[k]===undefined||a[k]===''||near(Number(a[k]),Number(b[k]??NaN),1e-6));}
  pass('stored_exit_study_ledger_filled_rows',ok,f);ledgerFiles++;
}

// ---- separation behaviour
const sepI0=summaries.filter(s=>s.exit_id!=='NO_SELL'&&s.I_initial===0&&s.R_after_sale>0&&s.after_sale_reentry_count>0);
const sepR0=summaries.filter(s=>s.exit_id!=='NO_SELL'&&s.I_initial>0&&s.R_after_sale===0&&s.initial_trend_count>0&&s.sell_count>0);
pass('separation_I0_Rpos_has_after_sale_reentry_cases',sepI0.length>0,String(sepI0.length));
pass('separation_Ipos_R0_has_initial_then_sale_cases',sepR0.length>0,String(sepR0.length));
// NO_SELL: R does not matter
let nsr=0;
for(const start of starts)for(const delay of delays)for(const I of Is){
  const base=results.get(key(`NO_SELL_I${pct(I)}`,start,delay));
  for(const R of Rs){
    const r=simulate(input.rows,{...baseOpts,start,delay,...EXITS.NO_SELL,reentry:I,initialRatio:I,reentryRatio:R});
    pass('NO_SELL_ledger_independent_of_R',JSON.stringify(analyze(r,{id:'x',exit:'NO_SELL',I,R},delay).ledger)===JSON.stringify(base.ledger)||JSON.stringify(r.ledger)===JSON.stringify(base.ledger.map(({allocation_class,...t})=>t)),`I${I} R${R} ${start} d${delay}`);nsr++;
  }
}
// R-only change leaves the pre-first-sale path identical (initial allocation independent of R)
for(const start of starts)for(const delay of delays)for(const ex of ['P20_OR_R75','P20_ONLY'])for(const I of Is){
  const a=results.get(key(`${ex}_I${pct(I)}_R0`,start,delay)).ledger,b=results.get(key(`${ex}_I${pct(I)}_R100`,start,delay)).ledger;
  const cut=l=>{const i=l.findIndex(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');return JSON.stringify((i<0?l:l.slice(0,i)).map(t=>[t.date,t.type,t.shares,t.price]));};
  pass('R_change_does_not_alter_path_before_first_sale',cut(a)===cut(b),`${ex} I${I} ${start} d${delay}`);
}
// state is fresh at every start: first daily cash 10000 already checked; tape signals independent of I/R
const sigA=JSON.stringify(simulate(input.rows,{...baseOpts,start:'2025-01-02',...EXITS.NO_SELL,reentry:0}).signals.map(s=>[s.date,s.ex,s.normal,s.reCandidate]));
const sigB=JSON.stringify(simulate(input.rows,{...baseOpts,start:'2025-01-02',...EXITS.P20_OR_R75,initialRatio:1,reentryRatio:.25,reentry:1}).signals.map(s=>[s.date,s.ex,s.normal,s.reCandidate]));
pass('signal_tape_independent_of_I_R_and_exit',sigA===sigB,'');

// ---- contrast ledger/daily for the two main starts, delay 0
const contrastIds=candidates.filter(c=>c.exit==='P20_OR_R75'||c.exit==='NO_SELL').map(c=>c.id);
const cLed=[],cDay=[],cMeta=[];
for(const start of MAIN_STARTS)for(const id of contrastIds){
  const a=results.get(key(id,start,0));
  for(const t of a.ledger)if(t.type!=='MMF_MONTHLY_PROXY')cLed.push({start,candidate_id:id,date:t.date,signal_date:t.signal_date,type:t.type,allocation_class:t.allocation_class,status:t.status,shares:t.shares,price:t.price,fee:t.fee,cost:t.cost,basis:t.basis,gain:t.gain,tax:t.tax,net:t.net,cash_after:t.cash_after,shares_after:t.shares_after});
  for(const d of a.daily)cDay.push({start,candidate_id:id,date:d.date,cash:d.cash,shares:d.shares,basis:d.basis,close:d.close,market_value:d.market_value,total:d.total});
  cMeta.push(a.summary);
}
await fs.writeFile(path.join(here,'contrast_ledger.csv'),csv(cLed));
await fs.writeFile(path.join(here,'contrast_daily.csv'),csv(cDay));

// ---- environment + verification
const sha=async f=>crypto.createHash('sha256').update(await fs.readFile(path.join(here,f))).digest('hex');
const nFail=failures.length;
await fs.writeFile(path.join(here,'verification.json'),JSON.stringify({
  passed_all:nFail===0,failure_count:nFail,failures:failures.slice(0,50),
  counts:{main_diagnostic_runs:summaries.length,unique_candidates:21,starts:starts.length,delays:delays.length,
    regression_extra_runs_old_vs_new_IeqR:oldCmp,regression_extra_runs_note:'3 exits x 3 I x 6 starts x 2 delays x (old, new-unspecified, new-explicit) compared; NOT counted in the 252',
    stored_summary_rows_compared:storedCmp,stored_delay1_rows_compared:sensCmp,stored_ledger_files_compared:ledgerFiles,
    NO_SELL_R_independence_extra_runs:nsr,month_end_rows:monthRows.length,month_end_notes:monthNotes.length,
    separation_cases_I0_Rpos:sepI0.length,separation_cases_Ipos_R0_with_sale:sepR0.length},
  tolerance:{amounts_USD:1e-6,legacy_engine_comparison:'exact JSON equality of ledger/daily/candidates; final_total exact (===)',stored_csv_comparison:'1e-6 USD'},
  checks,month_end_notes:monthNotes.slice(0,50)},null,2));
await fs.writeFile(path.join(here,'environment.json'),JSON.stringify({node:process.version,platform:process.platform,
  command:'cd research/SOXL_allocation_separation_20261026 && node run.mjs',network:'not used',secrets:'none',elapsed_ms:Date.now()-t0,
  input_manifest:input.manifest,engine_sha256:await sha('engine.mjs'),run_sha256:await sha('run.mjs'),specification_sha256:await sha('specification.json'),
  old_engine_sha256:crypto.createHash('sha256').update(await fs.readFile(path.join(oldDir,'audit_exit.mjs'))).digest('hex')},null,2));
console.log(JSON.stringify({passed_all:nFail===0,failures:failures.slice(0,10),runs:summaries.length,month_rows:monthRows.length,oldCmp,storedCmp,sensCmp,ledgerFiles,sepI0:sepI0.length,sepR0:sepR0.length},null,2));
if(nFail)process.exit(1);
