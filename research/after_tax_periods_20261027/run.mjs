// node run.mjs   (Node >=22, standard library only, no network)
// After-tax comparison of sell rules across 8 market windows. Engine and inputs are reused unchanged from 37a14c0.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load,simulate,TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const engDir=path.join(here,'..','SOXL_allocation_separation_20261026');
const spec=JSON.parse(await fs.readFile(path.join(here,'specification.json'),'utf8'));
const failures=[],checks={};
const pass=(name,ok,detail)=>{(checks[name]??={n:0,fail:0});checks[name].n++;if(!ok){checks[name].fail++;failures.push({check:name,detail});}};
const near=(a,b,tol=1e-6)=>Math.abs(a-b)<=tol;
const pct=x=>String(Math.round(x*100));
function csv(rows){
  const keys=[...new Set(rows.flatMap(Object.keys))];
  const q=v=>v==null?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':String(v);
  return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>q(r[k])).join(',')).join('\n')+'\n';
}

// ---- inputs (hash-checked)
const input=await load(path.join(here,'..','SOXL_exit_study_20261023','data'));
const refManifest=JSON.parse(await fs.readFile(path.join(engDir,'input_manifest_reference.json'),'utf8'));
for(const m of input.manifest){const r=refManifest.find(x=>x.file===m.file);pass('input_sha256_matches_manifest',!!r&&r.sha256===m.sha256&&r.bytes===m.bytes,m.file);}
const schedule=JSON.parse(await fs.readFile(path.join(engDir,'dividends_verified.json'),'utf8'));

// ---- next-close proxy rows: SOXL adjClose as open=high=low=close (total return, so no separate dividends)
const S=input.daily.funds.SOXL,off=S.start??0;
const adj=new Map(input.daily.date.map((d,i)=>[d,i>=off?S.adjClose[i-off]:null]));
const closeRows=input.rows.map(r=>{const c=adj.get(r.date);return c==null?r:{...r,open:c,high:c,low:c,close:c,volume:0};});
pass('close_proxy_rows_same_signals_inputs',closeRows.every((r,i)=>r.soxx===input.rows[i].soxx&&r.rsi===input.rows[i].rsi&&r.fg===input.rows[i].fg&&r.shd===input.rows[i].shd),'');

// ---- MMF rate per window: mean ^IRX (annual %, 13-week T-bill) inside the window; current window keeps 3%
const irx=input.market.filter(r=>r['^IRX']!=='').map(r=>[r.Date,Number(r['^IRX'])]);
const windows=spec.windows.map(w=>{
  if(w.id==='W2024_CURRENT')return {...w,mmfRate:.03};
  const v=irx.filter(([d])=>d>=w.start&&d<=w.end).map(x=>x[1]);
  return {...w,mmfRate:v.reduce((a,b)=>a+b,0)/v.length/100};
});

// ---- candidates (53)
const G=spec.grid,candidates=[];
for(const t of G.profit_target)for(const rsi of G.rsi_threshold)for(const R of G.R_after_sale){
  const exit=rsi===null?`P${pct(t)}_ONLY`:`P${pct(t)}_OR_R${rsi}`;
  candidates.push({id:`${exit}_I25_R${pct(R)}`,exit,target:t,rsi,I:G.I_initial,R,opts:{exitMode:rsi===null?'PROFIT_ONLY':'OR',profitTarget:t,exitRsi:rsi??999}});
}
for(const I of G.no_sell.I_initial)candidates.push({id:`NO_SELL_I${pct(I)}`,exit:'NO_SELL',target:null,rsi:null,I,R:null,opts:{exitMode:'NONE',profitTarget:.2,exitRsi:75}});
pass('candidate_count_53',candidates.length===G.candidate_count,String(candidates.length));

function analyze(r,c,w,delay,exec){
  const ledger=r.ledger,daily=r.daily,p=daily.at(-1);
  const sales=ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');
  const buys=ledger.filter(t=>t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY'].includes(t.type));
  const mmfNet=ledger.filter(t=>t.type==='MMF_MONTHLY_PROXY').reduce((a,t)=>a+t.gross-t.tax,0)+p.mmf_accrued_gross*(1-TAX);
  const divNet=ledger.filter(t=>t.type==='DIVIDEND_ENTITLEMENT').reduce((a,t)=>a+t.net,0);
  const gain=sales.reduce((a,t)=>a+t.gain,0),tax=sales.reduce((a,t)=>a+t.tax,0);
  const tag=`${c.id}|${w.id}|d${delay}|${exec}`;
  pass('accounting_identity',near(r.cfg.initial+gain-tax+mmfNet+divNet+p.unrealized,p.total,1e-5),tag);
  pass('balance_invariants',daily.every(d=>d.cash>=-1e-7&&Number.isInteger(d.shares)&&d.shares>=0&&(d.shares>0||d.basis===0)),tag);
  pass('no_sale_below_2pct_net_gain',sales.every(t=>t.gain>=t.basis*.02-1e-7),tag);
  pass('fills_on_next_session_after_signal',ledger.filter(t=>t.signal_date).every(t=>t.date>t.signal_date),tag);
  pass('window_bounds',daily[0].date>=w.start&&p.date<=w.end&&daily[0].cash===10000,tag);
  if(c.exit==='NO_SELL')pass('no_sell_has_zero_sales',sales.length===0,tag);
  return {summary:{candidate_id:c.id,exit_id:c.exit,profit_target:c.target,rsi_threshold:c.rsi,I_initial:c.I,R_after_sale:c.R,
    window:w.id,start:w.start,end_date:p.date,fg_delay:delay,execution:exec,mmf_rate:w.mmfRate,
    after_tax_liquidation:p.liquidation,final_total_pretax:p.total,terminal_sale_cost_and_tax:p.total-p.liquidation,final_shares:p.shares,final_cash:p.cash,final_market_value:p.market_value,final_basis:p.basis,
    realized_gain:gain,realized_tax_paid:tax,mmf_net:mmfNet,dividend_net:divNet,total_fees:ledger.reduce((a,t)=>a+(t.fee??0),0),
    buy_count:buys.length,sell_count:sales.length,blocked_sales:r.summary.blocked_sales,first_buy_date:buys[0]?.date??'',last_sale_date:sales.at(-1)?.date??''},
    daily,ledger};
}

const results=[];const t0=Date.now();
const runs=[];
for(const w of windows)for(const delay of G.fg_delay)runs.push({w,delay,exec:'NEXT_CLOSE_PROXY',rows:closeRows,extra:{}});
const cur=windows.find(w=>w.id==='W2024_CURRENT');
for(const delay of G.fg_delay)runs.push({w:cur,delay,exec:'NEXT_OPEN_BRIDGE',rows:input.rows,extra:{dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy'}});
for(const run of runs)for(const c of candidates){
  const r=simulate(run.rows,{start:run.w.start,end:run.w.end,initial:10000,allowInitialReentry:true,mmfRate:run.w.mmfRate,closeTargetNet:false,buffer:0,slippage:0,
    ...run.extra,delay:run.delay,...c.opts,initialRatio:c.I,reentryRatio:c.R??c.I,reentry:c.I});
  results.push({...analyze(r,c,run.w,run.delay,run.exec),run});
}
pass('run_count_954',results.length===954,String(results.length));

// ---- ranks and comparison with NO_SELL_I25 (per window x delay x execution)
const groupKey=s=>`${s.window}|${s.fg_delay}|${s.execution}`;
const groups=new Map();for(const x of results){const k=groupKey(x.summary);(groups.get(k)??groups.set(k,[]).get(k)).push(x);}
const monthRows=[];
for(const [k,g] of groups){
  const ns=g.find(x=>x.summary.candidate_id==='NO_SELL_I25');
  const nsMap=new Map(ns.daily.map(d=>[d.date,d.liquidation]));
  const days=ns.daily.map(d=>d.date),monthEnds=days.filter((d,i)=>i===days.length-1||days[i+1].slice(0,7)!==d.slice(0,7));
  for(const x of g){
    const s=x.summary;
    s.rank_after_tax=1+g.filter(y=>y.summary.after_tax_liquidation>s.after_tax_liquidation+1e-7).length;
    s.rank_pretax=1+g.filter(y=>y.summary.final_total_pretax>s.final_total_pretax+1e-7).length;
    s.vs_NO_SELL_I25_after_tax=s.after_tax_liquidation-ns.summary.after_tax_liquidation;
    s.ratio_to_NO_SELL_I25_after_tax=s.after_tax_liquidation/ns.summary.after_tax_liquidation;
    s.beats_NO_SELL_I25_after_tax=s.vs_NO_SELL_I25_after_tax>1e-7;
    const dm=new Map(x.daily.map(d=>[d.date,d.liquidation]));
    let w=0;for(const d of monthEnds){if(dm.get(d)>nsMap.get(d)+1e-7)w++;}
    s.month_ends=monthEnds.length;s.month_ends_beating_NO_SELL_I25_after_tax=w;
    if(['P20_ONLY_I25_R25','P20_OR_R75_I25_R25','NO_SELL_I0','NO_SELL_I25','NO_SELL_I100'].includes(s.candidate_id))
      for(const d of monthEnds)monthRows.push({window:s.window,fg_delay:s.fg_delay,execution:s.execution,candidate_id:s.candidate_id,date:d,after_tax_liquidation:dm.get(d)});
  }
}

// ---- reproduction of stored 77bb44f results (open bridge, current window)
const ref=JSON.parse(await fs.readFile(path.join(here,'reference_77bb44f_start2024-10.json'),'utf8')).rows;
let matched=0;
for(const rr of ref){
  const x=results.find(y=>y.summary.execution==='NEXT_OPEN_BRIDGE'&&y.summary.candidate_id===rr.candidate_id&&y.summary.fg_delay===rr.fg_delay);
  if(!x)continue;matched++;
  pass('reproduces_77bb44f_final_total_and_liquidation',near(x.summary.final_total_pretax,rr.final_total)&&near(x.summary.after_tax_liquidation,rr.liquidation)&&x.summary.sell_count===rr.sell_count,`${rr.candidate_id}|d${rr.fg_delay}`);
}
pass('reproduction_overlap_count',matched===26,String(matched));

// ---- robustness by rule: past 7 windows, close proxy
const summaries=results.map(x=>x.summary);
const past=windows.filter(w=>w.id!=='W2024_CURRENT').map(w=>w.id);
const robust=[];
for(const c of candidates)for(const delay of G.fg_delay){
  const rows=summaries.filter(s=>s.candidate_id===c.id&&s.fg_delay===delay&&s.execution==='NEXT_CLOSE_PROXY');
  const p=rows.filter(s=>past.includes(s.window));
  const curClose=rows.find(s=>s.window==='W2024_CURRENT');
  const curOpen=summaries.find(s=>s.candidate_id===c.id&&s.fg_delay===delay&&s.execution==='NEXT_OPEN_BRIDGE');
  const ratios=p.map(s=>s.ratio_to_NO_SELL_I25_after_tax).sort((a,b)=>a-b);
  robust.push({candidate_id:c.id,fg_delay:delay,
    past_windows_beating_NO_SELL_I25:p.filter(s=>s.beats_NO_SELL_I25_after_tax).length,past_windows:p.length,
    past_windows_rank1:p.filter(s=>s.rank_after_tax===1).length,
    min_ratio_past:ratios[0],median_ratio_past:ratios[3],max_ratio_past:ratios.at(-1),
    ...Object.fromEntries(p.map(s=>['ratio_'+s.window,s.ratio_to_NO_SELL_I25_after_tax])),
    current_close_ratio:curClose.ratio_to_NO_SELL_I25_after_tax,current_open_ratio:curOpen.ratio_to_NO_SELL_I25_after_tax,
    current_open_after_tax:curOpen.after_tax_liquidation,current_open_rank:curOpen.rank_after_tax});
}

await fs.writeFile(path.join(here,'summary.csv'),csv(summaries));
await fs.writeFile(path.join(here,'robustness_by_rule.csv'),csv(robust));
await fs.writeFile(path.join(here,'month_end_key_candidates.csv'),csv(monthRows));
const keyLedger=results.filter(x=>['P20_ONLY_I25_R25','P20_OR_R75_I25_R25','NO_SELL_I25'].includes(x.summary.candidate_id)&&x.summary.fg_delay===0)
  .flatMap(x=>x.ledger.filter(t=>t.status).map(t=>({window:x.summary.window,execution:x.summary.execution,candidate_id:x.summary.candidate_id,signal_date:t.signal_date,date:t.date,type:t.type,status:t.status,shares:t.shares??'',price:t.price??'',gain:t.gain??'',tax:t.tax??''})));
await fs.writeFile(path.join(here,'ledger_key_candidates_delay0.csv'),csv(keyLedger));
await fs.writeFile(path.join(here,'windows_used.json'),JSON.stringify(windows,null,1));
await fs.writeFile(path.join(here,'verification.json'),JSON.stringify({passed_all:failures.length===0,checks,failures:failures.slice(0,50),runtime_ms:Date.now()-t0},null,1));
const sha=async f=>crypto.createHash('sha256').update(await fs.readFile(f)).digest('hex');
await fs.writeFile(path.join(here,'environment.json'),JSON.stringify({node:process.version,engine_sha256:await sha(path.join(engDir,'engine.mjs')),input_manifest:input.manifest,status:'DIAGNOSTIC_ONLY_NOT_TRADABLE_RESULTS'},null,1));
console.log('runs',results.length,'failures',failures.length,JSON.stringify(checks));
