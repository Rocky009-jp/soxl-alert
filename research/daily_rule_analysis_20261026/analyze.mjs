// node analyze.mjs   (Node >=22, standard library only, no network)
// Daily-rule comparison & path analysis on top of the FIXED allocation-separation study (37a14c0).
// Reuses saved summary.csv / month_end_summary.csv / contrast_ledger.csv / contrast_daily.csv.
// The only new simulations are the 4 missing P20_ONLY paths (2 candidates x 2 main starts x delay 0),
// run with the unchanged engine.mjs and the same options as run.mjs. Nothing in the old folder is written.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load,simulate,signals,quantity,sellCosts,TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const src=path.join(here,'..','SOXL_allocation_separation_20261026');
const oldDir=path.join(here,'..','SOXL_exit_study_20261023');
const END='2026-08-10',MAIN=['2024-10-01','2025-01-02'],REF='P20_OR_R75_I25_R25';
const SUBSET=['P20_OR_R75_I25_R0','P20_OR_R75_I25_R25','P20_OR_R75_I25_R100','P20_OR_R75_I0_R25','P20_OR_R75_I100_R25',
  'P20_ONLY_I25_R25','P20_ONLY_I100_R25','NO_SELL_I0','NO_SELL_I25','NO_SELL_I100'];
const EXTRA=['P20_ONLY_I25_R25','P20_ONLY_I100_R25'];
const failures=[],checks={};
const pass=(name,ok,detail)=>{(checks[name]??={n:0,fail:0});checks[name].n++;if(!ok){checks[name].fail++;failures.push({check:name,detail});}};
const near=(a,b,tol=1e-6)=>Math.abs(a-b)<=tol;
function parseCsv(text){
  const rows=[];let row=[],f='',inq=false;
  for(let i=0;i<text.length;i++){const c=text[i];
    if(inq){if(c=='"'){if(text[i+1]=='"'){f+='"';i++;}else inq=false;}else f+=c;}
    else if(c=='"')inq=true;else if(c==','){row.push(f);f='';}
    else if(c=='\n'){row.push(f);rows.push(row);row=[];f='';}else if(c!='\r')f+=c;}
  if(f.length||row.length){row.push(f);rows.push(row);}
  const h=rows.shift();return rows.map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]])));
}
function csv(rows){
  const keys=[...new Set(rows.flatMap(Object.keys))];
  const q=v=>v==null?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':String(v);
  return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>q(r[k])).join(',')).join('\n')+'\n';
}
const sha=async f=>{const b=await fs.readFile(f);return {file:path.relative(path.join(here,'..','..'),f).replaceAll('\\','/'),bytes:b.length,sha256:crypto.createHash('sha256').update(b).digest('hex')};};
const num=v=>v===''||v==null?null:Number(v);

// ---- source refs (fixed inputs, code and saved outputs)
const srcFiles=['engine.mjs','run.mjs','specification.json','summary.csv','month_end_summary.csv','contrast_ledger.csv','contrast_daily.csv','dividends_verified.json','verification.json','REPORT.md'].map(f=>path.join(src,f));
const dataFiles=['daily.json','daily_adjclose.csv','fear-greed.csv'].map(f=>path.join(oldDir,'data',f));
const refs=[];for(const f of [...srcFiles,...dataFiles])refs.push(await sha(f));
const env=JSON.parse(await fs.readFile(path.join(src,'environment.json'),'utf8'));
pass('engine_sha256_equals_37a14c0_environment',refs.find(r=>r.file.endsWith('allocation_separation_20261026/engine.mjs')).sha256===env.engine_sha256,'');
pass('run_sha256_equals_37a14c0_environment',refs.find(r=>r.file.endsWith('allocation_separation_20261026/run.mjs')).sha256===env.run_sha256,'');
for(const m of env.input_manifest){const r=refs.find(x=>x.file.endsWith('/data/'+m.file));pass('input_sha256_equals_manifest',r&&r.sha256===m.sha256&&r.bytes===m.bytes,m.file);}

// ---- 1. extraction of 120 rows from the saved 252
const all=parseCsv(await fs.readFile(path.join(src,'summary.csv'),'utf8'));
pass('saved_summary_rows_252',all.length===252,String(all.length));
const sub=all.filter(r=>SUBSET.includes(r.candidate_id)).map(r=>({row_source:'saved_summary_37a14c0',...r,
  rank_note:'rank_in_start_delay is the ORIGINAL rank among all 21 candidates of that start x delay; not re-ranked inside the subset'}));
pass('subset_rows_120',sub.length===120,String(sub.length));
pass('subset_candidates_10',new Set(sub.map(r=>r.candidate_id)).size===10,'');
await fs.writeFile(path.join(here,'summary_subset.csv'),csv(sub));
const S=(id,start,d)=>all.find(r=>r.candidate_id===id&&r.start===start&&Number(r.fg_delay)===d);

// month-end subset (reuse only; proxy dates)
const me=parseCsv(await fs.readFile(path.join(src,'month_end_summary.csv'),'utf8')).filter(r=>SUBSET.includes(r.candidate_id));
await fs.writeFile(path.join(here,'month_end_subset.csv'),csv(me.map(r=>({...r,rank_note:'rank is the original rank among 21 at that month-end proxy date'}))));

// ---- 2. extra fixed-engine runs: 4 P20_ONLY paths (same options as run.mjs)
const input=await load(path.join(oldDir,'data'));
const schedule=JSON.parse(await fs.readFile(path.join(src,'dividends_verified.json'),'utf8'));
const baseOpts={end:END,initial:10000,allowInitialReentry:true,dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy',mmfRate:.03,closeTargetNet:false,buffer:0,slippage:0};
const P20_ONLY={exitMode:'PROFIT_ONLY',profitTarget:.2,exitRsi:75};
function classify(ledger){let sold=false;return ledger.map(t=>{let cls=null;
  if(t.status==='FILLED_DIAGNOSTIC'&&t.type==='REENTRY')cls=sold?'AFTER_SALE_REENTRY':'INITIAL_TREND';
  if(t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC')sold=true;return {...t,allocation_class:cls};});}
const led=parseCsv(await fs.readFile(path.join(src,'contrast_ledger.csv'),'utf8')).map(r=>({...r,path_source:'contrast_ledger_37a14c0_reused'}));
const day=parseCsv(await fs.readFile(path.join(src,'contrast_daily.csv'),'utf8')).map(r=>({...r,path_source:'contrast_daily_37a14c0_reused'}));
const extraRuns=[];
for(const start of MAIN)for(const id of EXTRA){
  const I=id.includes('I100')?1:.25,R=.25;
  const r=simulate(input.rows,{...baseOpts,start,delay:0,...P20_ONLY,initialRatio:I,reentryRatio:R,reentry:I});
  const L=classify(r.ledger),d=r.daily.at(-1),s=S(id,start,0);
  const sales=L.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');
  const mmf=L.filter(t=>t.type==='MMF_MONTHLY_PROXY').reduce((a,t)=>a+t.gross-t.tax,0)+d.mmf_accrued_gross*(1-TAX);
  const div=L.filter(t=>t.type==='DIVIDEND_ENTITLEMENT').reduce((a,t)=>a+t.net,0);
  const cmp={final_total:d.total,liquidation:d.liquidation,final_shares:d.shares,final_cash:d.cash,final_market_value:d.market_value,final_basis:d.basis,
    mmf_net_total:mmf,dividend_net_total:div,realized_stock_gain:sales.reduce((a,t)=>a+t.gain,0),realized_stock_tax:sales.reduce((a,t)=>a+t.tax,0),
    total_order_fees:L.reduce((a,t)=>a+(t.fee??0),0),sell_count:sales.length,blocked_sales:r.summary.blocked_sales};
  const diffs=Object.fromEntries(Object.entries(cmp).map(([k,v])=>[k,v-Number(s[k])]));
  const ok=Object.values(diffs).every(x=>Math.abs(x)<=1e-6);
  pass('extra_run_matches_saved_summary_1e-6',ok,`${id}|${start}|${JSON.stringify(diffs)}`);
  extraRuns.push({candidate_id:id,start,fg_delay:0,final_total_rerun:d.total,final_total_saved:Number(s.final_total),max_abs_diff_usd:Math.max(...Object.values(diffs).map(Math.abs)),fields_compared:Object.keys(cmp)});
  for(const t of L)if(t.type!=='MMF_MONTHLY_PROXY')led.push({start,candidate_id:id,date:t.date,signal_date:t.signal_date,type:t.type,allocation_class:t.allocation_class??'',status:t.status??'',shares:t.shares,price:t.price,fee:t.fee,cost:t.cost,basis:t.basis,gain:t.gain,tax:t.tax,net:t.net,cash_after:t.cash_after,shares_after:t.shares_after,path_source:'extra_run_fixed_engine_P20_ONLY'});
  for(const x of r.daily)day.push({start,candidate_id:id,date:x.date,cash:x.cash,shares:x.shares,basis:x.basis,close:x.close,market_value:x.market_value,total:x.total,path_source:'extra_run_fixed_engine_P20_ONLY'});
}
if(failures.length){console.error(JSON.stringify(failures,null,2));process.exit(1);} // stop interpretation on mismatch

// ---- 3. signal tape (account independent; the same function the engine uses) and event table for 20 paths
const tape=new Map(signals(input.rows,{delay:0}).map(r=>[r.date,r]));
const dates=input.rows.map(r=>r.date);
const nextSession=d=>dates[dates.indexOf(d)+1];
const PATHS=[];for(const start of MAIN)for(const id of SUBSET)PATHS.push({start,id});
const dayKey=new Map(day.map(r=>[`${r.start}|${r.candidate_id}|${r.date}`,r]));
const ev=[];
for(const {start,id} of PATHS){
  const rows=led.filter(r=>r.start===start&&r.candidate_id===id);
  pass('path_has_rows',rows.length>0,`${start}|${id}`);
  const sold=[];
  for(const t of rows){
    if(!['EXFEAR','NORMAL','REENTRY','SELL'].includes(t.type))continue;
    const D=t.signal_date,sig=tape.get(D),dd=dayKey.get(`${start}|${id}|${D}`);
    pass('execution_is_next_session_after_signal',nextSession(D)===t.date,`${id}|${t.date}`);
    const exec=input.rows.find(r=>r.date===t.date);
    const sharesD=Number(dd.shares),basisD=Number(dd.basis),cashD=Number(dd.cash),closeD=sig.close;
    const o={start,candidate_id:id,path_source:t.path_source,signal_date_D:D,proxy_execution_session:t.date,order_type:t.type,
      allocation_class:t.allocation_class||(t.type==='SELL'?'SELL':t.type==='REENTRY'?'':'NORMAL_OR_EXFEAR'),
      after_first_sale:sold.length>0,status:t.status,
      // morning-known (confirmed session D)
      D_close:closeD,D_fg_proxy:sig.fg_used,D_soxx_rsi:sig.rsi,D_soxx_above_sma200:sig.soxx>sig.sma,D_shd:sig.shd,D_armed_after:sig.armed,
      D_cash:cashD,D_shares:sharesD,D_basis:basisD,
      D_gross_profit_pct:sharesD?sharesD*closeD/basisD-1:null,
      D_net_profit_pct_close:sharesD?(sharesD*closeD-sellCosts(sharesD,closeD,D))/basisD-1:null,
      sell_trigger:t.type==='SELL'?[sharesD*closeD/basisD-1>=.2?'PROFIT20':null,sig.rsi>=75?'RSI75':null].filter(Boolean).join('+'):'',
      buy_shares_if_priced_at_D_close:t.type==='SELL'?null:quantity(cashD*(t.type==='REENTRY'?Number(t.allocation_class==='INITIAL_TREND'?S(id,start,0).I_initial:S(id,start,0).R_after_sale):1),closeD),
      // evaluated with the next-session Open (NOT known in the morning)
      open_proxy:exec.open,open_gap_vs_D_close:exec.open/closeD-1,shares:num(t.shares),price:num(t.price),fee:num(t.fee),cost:num(t.cost),basis_sold:num(t.basis),gain:num(t.gain),tax:num(t.tax),
      cash_after:num(t.cash_after),shares_after:num(t.shares_after),
      open_dependent:t.type==='SELL'?'2% net gate re-checked at next Open (retrospective); proceeds/tax at Open':'share count = floor(cash*fraction/Open) incl. fee'};
    if(t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC')sold.push(t.date);
    ev.push(o);
  }
}
await fs.writeFile(path.join(here,'event_comparison.csv'),csv(ev));

// ---- 4. terminal reconciliation of each path vs the reference I25/R25 (same start)
const recon=[];
for(const start of MAIN){const b=S(REF,start,0);
  for(const id of SUBSET){const s=S(id,start,0);
    const f=k=>Number(s[k])-Number(b[k]);
    const total=f('final_total'),parts={cash:f('final_cash'),stock_market_value:f('final_market_value'),
      mmf_accrued_net_and_div_receivable:total-f('final_cash')-f('final_market_value')};
    const sum=Object.values(parts).reduce((a,x)=>a+x,0);
    pass('reconciliation_parts_sum_to_total',near(sum,total,1e-6),`${id}|${start}`);
    // second (flow) decomposition: realized gain - tax + mmf + dividends + unrealized
    const flow={realized_gain_after_costs:f('realized_stock_gain'),stock_tax:-f('realized_stock_tax'),mmf_net:f('mmf_net_total'),dividend_net:f('dividend_net_total'),unrealized:f('final_unrealized')};
    pass('flow_decomposition_sums_to_total',near(Object.values(flow).reduce((a,x)=>a+x,0),total,1e-6),`${id}|${start}`);
    const breakEven=id.startsWith('NO_SELL')?(Number(b.final_total)-(Number(s.final_total)-Number(s.final_market_value)))/Number(s.final_shares):null;
    pass('reconciliation_liquidation_delta_present',Number.isFinite(f('liquidation')),`${id}|${start}`);
    recon.push({start,candidate_id:id,delta_total_vs_ref:total,delta_liquidation_vs_ref:f('liquidation'),no_sell_break_even_close_vs_ref:breakEven,...Object.fromEntries(Object.entries(parts).map(([k,v])=>['balance_'+k,v])),...Object.fromEntries(Object.entries(flow).map(([k,v])=>['flow_'+k,v]))});
  }}
await fs.writeFile(path.join(here,'terminal_reconciliation.csv'),csv(recon));

// ---- 5. P20_OR_R75 vs P20_ONLY identity check on ledgers (I25/I100, R25, main starts)
const ledgerSig=(start,id)=>JSON.stringify(led.filter(r=>r.start===start&&r.candidate_id===id).map(r=>[r.date,r.type,r.status,Number(r.shares||0),Number(r.price||0)]));
const exitCmp=[];
for(const start of MAIN)for(const I of ['I25','I100']){
  const a=`P20_OR_R75_${I}_R25`,b=`P20_ONLY_${I}_R25`;
  exitCmp.push({start,pair:`${a} vs ${b}`,identical_ledger:ledgerSig(start,a)===ledgerSig(start,b),delta_total:Number(S(a,start,0).final_total)-Number(S(b,start,0).final_total)});
}
await fs.writeFile(path.join(here,'verification.json'),JSON.stringify({passed_all:failures.length===0,failure_count:failures.length,failures,
  counts:{saved_summary_rows:252,extracted_rows:sub.length,extracted_candidates:10,month_end_subset_rows:me.length,
    reused_contrast_paths:16,extra_fixed_engine_runs:extraRuns.length,extra_runs_note:'P20_ONLY_I25_R25 and P20_ONLY_I100_R25 x 2024-10-01/2025-01-02 x delay 0; NOT part of the 120 extraction and NOT a re-run of the 252',
    event_rows:ev.length,paths:PATHS.length},
  tolerance_usd:1e-6,extra_runs:extraRuns,exit_identity:exitCmp,checks},null,2));
await fs.writeFile(path.join(here,'source_refs.json'),JSON.stringify({research_fixed_commit:'37a14c02517b6357bcaeecb6f0a023bfc8a3696a',
  docs_start_commit:'7812065cd75c4096c74bf5a3163571c0c6623e6e',note:'SHA256 of every file read; nothing in these folders was modified',files:refs,
  this_script:await sha(path.join(here,'analyze.mjs')),node:process.version,network:'not used'},null,2));
console.log(JSON.stringify({passed_all:failures.length===0,failures:failures.slice(0,5),sub:sub.length,ev:ev.length,extraRuns,exitCmp},null,2));
