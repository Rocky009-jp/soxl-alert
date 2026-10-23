import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {load,simulate,signals,TAX} from './audit_exit.mjs';
import {simulate as previousSim} from './audit_previous.mjs';
export const ratios=[0,.1,.25,.5,.75,1];
export const starts=['2024-10-01','2025-01-02','2025-04-01','2025-07-01','2025-10-01','2026-01-02'];
export const exits=[
 ...[.2,.3,.4,.6].flatMap(profitTarget=>[75,80,85].map(exitRsi=>({id:'P'+profitTarget*100+'_OR_R'+exitRsi,exitMode:'OR',profitTarget,exitRsi}))),
 ...[.2,.3,.4,.6].map(profitTarget=>({id:'P'+profitTarget*100+'_ONLY',exitMode:'PROFIT_ONLY',profitTarget,exitRsi:75})),
 ...[75,80,85].map(exitRsi=>({id:'R'+exitRsi+'_ONLY',exitMode:'RSI_ONLY',profitTarget:.2,exitRsi})),
 {id:'NO_SELL',exitMode:'NONE',profitTarget:.2,exitRsi:75}
];
export function csv(rows) {
 if(!rows.length)return '';
 const keys=[...new Set(rows.flatMap(Object.keys))],quote=v=>v==null?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':typeof v==='object'?'"'+JSON.stringify(v).replaceAll('"','""')+'"':String(v);
 return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>quote(r[k])).join(',')).join('\n')+'\n';
}
function analyze(r,exit,scenario='BASE'){
 let bought=false;const ledger=r.ledger.map(t=>{
  const row={...t};
  if(t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY'].includes(t.type)){
   if(t.type==='REENTRY'&&!bought)row.type='INITIAL_TREND';
   bought=true;
  }
  return row;
 });
 const sales=ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');
 const p=r.daily.at(-1),mmfNet=ledger.filter(t=>t.type==='MMF_MONTHLY_PROXY').reduce((a,t)=>a+t.gross-t.tax,0)+p.mmf_accrued_gross*(1-TAX);
 const divNet=ledger.filter(t=>t.type==='DIVIDEND_ENTITLEMENT').reduce((a,t)=>a+t.net,0),realizedGain=sales.reduce((a,t)=>a+t.gain,0),tax=sales.reduce((a,t)=>a+t.tax,0);
 const s={scenario,exit_id:exit.id,exit_mode:exit.exitMode,profit_target:exit.exitMode==='RSI_ONLY'||exit.exitMode==='NONE'?null:exit.profitTarget,
  exit_RSI:exit.exitMode==='PROFIT_ONLY'||exit.exitMode==='NONE'?null:exit.exitRsi,
  ...r.summary,initial_trend_allowed:true,initial_trend_fraction:r.cfg.reentry,
  final_cash:p.cash,final_market_value:p.market_value,final_basis:p.basis,final_unrealized:p.unrealized,
  liquidation_jpy150:p.liquidation*150,pure_profit_jpy150:(p.total-r.cfg.initial)*150,
  mmf_net_total:mmfNet,dividend_net_total:divNet,realized_stock_gain:realizedGain,realized_stock_tax:tax,
  total_order_fees:ledger.reduce((a,t)=>a+(t.fee??0),0),
  initial_trend_count:ledger.filter(t=>t.type==='INITIAL_TREND'&&t.status==='FILLED_DIAGNOSTIC').length,
  after_sale_reentry_count:ledger.filter(t=>t.type==='REENTRY'&&t.status==='FILLED_DIAGNOSTIC').length};
 assert(Math.abs((r.cfg.initial+realizedGain-tax+mmfNet+divNet+p.unrealized)-p.total)<1e-6,'Accounting identity');
 for(const d of r.daily){
  assert(d.cash>=-1e-7&&d.shares>=0&&Number.isInteger(d.shares),'Balance invariant');
  if(!d.shares)assert.equal(d.basis,0);
 }
 for(const t of sales)assert(t.gain>=t.basis*.02-1e-7,'Loss sale / floor breach');
 if(exit.exitMode==='NONE')assert.equal(sales.length,0,'NO_SELL sold shares');
 return {summary:s,ledger,daily:r.daily,candidates:r.candidates};
}
export async function runExitStudy({root,out,schedulePath}){
 await fs.mkdir(out,{recursive:true});
 const input=await load(root),schedule=JSON.parse(await fs.readFile(schedulePath,'utf8'));
 const summaries=[],allTrades=[],model=new Map(),testNames=[];
 const options={end:'2026-08-10',initial:10000,allowInitialReentry:true,
  dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy',mmfRate:.03,
  closeTargetNet:false,buffer:0,slippage:0,delay:0};
 for(const start of starts)for(const exit of exits)for(const reentry of ratios){
  const r=simulate(input.rows,{...options,start,reentry,...exit});
  const a=analyze(r,exit);summaries.push(a.summary);
  for(const row of a.ledger)allTrades.push({start,exit_id:exit.id,reentry,...row});
  model.set([start,exit.id,reentry].join('|'),a);
  if(exit.id==='P20_OR_R75'){
   const old=previousSim(input.rows,{...options,start,reentry});
   assert(Math.abs(old.summary.final_total-r.summary.final_total)<1e-8,'Baseline drift');
   assert.equal(JSON.stringify(old.ledger),JSON.stringify(r.ledger),'Baseline ledger drift');
  }
 }
 testNames.push('36 base-case scenarios reproduce prior engine totals and complete ledgers exactly');
 testNames.push('720 scenarios: integer/nonnegative balances, zero-share zero basis, minimum net pre-tax gain2%, wealth accounting identities');
 testNames.push('36 NO_SELL scenarios: zero actual sells; unsold positions marked to market, no forced liquidation');
 const decisionMap=new Map(input.rows.map(r=>[r.date,r]));
 for(const exit of exits)for(const start of starts)for(const reentry of ratios){
  const a=model.get([start,exit.id,reentry].join('|'));
  for(const t of a.ledger.filter(t=>t.type==='SELL')){
   const r=decisionMap.get(t.signal_date);
   const grossGain=t.shares_before*r.close/t.basis_before-1;
   const profitHit=grossGain>=exit.profitTarget,rsiHit=r.rsi>=exit.exitRsi;
   assert(exit.exitMode==='OR'?(profitHit||rsiHit):exit.exitMode==='PROFIT_ONLY'?profitHit:exit.exitMode==='RSI_ONLY'?rsiHit:false,'Wrong exit trigger');
  }
 }
 testNames.push('Every submitted diagnostic sell matches its specific profit/RSI trigger on prior signal day');
 // Synthetic signal sequence verifies parametric decisions without relying on market-fit results.
 const synthetic=input.rows.filter(r=>r.date>='2025-02-03'&&r.date<='2025-02-21').map((r,i)=>({...r,fg:i===0?24:26,rsi:i===3?80:20,open:10,close:i>=3?12.5:10,high:13,low:9}));
 const runToy=exit=>simulate(synthetic,{...options,start:synthetic[0].date,end:synthetic.at(-1).date,...exit,dividendSchedule:[],mmfRate:0});
 const firstSell=r=>r.ledger.find(t=>t.type==='SELL')?.signal_date??null;
 const get=id=>exits.find(e=>e.id===id);
 assert.equal(firstSell(runToy(get('P20_ONLY'))),synthetic[3].date);
 assert.equal(firstSell(runToy(get('P30_ONLY'))),null);
 assert.equal(firstSell(runToy(get('R75_ONLY'))),synthetic[3].date);
 assert.equal(firstSell(runToy(get('R85_ONLY'))),null);
 assert.equal(firstSell(runToy(get('P60_OR_R75'))),synthetic[3].date);
 assert.equal(firstSell(runToy(get('P60_OR_R85'))),null);
 testNames.push('Synthetic threshold checks: profit20/30, RSI75/85 and OR independence produce expected different triggers');
 const rankings=[];
 for(const start of starts)for(const exit of exits){
  const group=summaries.filter(r=>r.start===start&&r.exit_id===exit.id).sort((a,b)=>b.final_total-a.final_total);
  const best=group[0],q25=group.find(r=>r.reentry===.25),baseline=model.get([start,'P20_OR_R75',.25].join('|')).summary;
  const liqBest=[...group].sort((a,b)=>b.liquidation-a.liquidation)[0];
  rankings.push({start,exit_id:exit.id,best_total:best.final_total,best_ratios:group.filter(r=>Math.abs(r.final_total-best.final_total)<1e-7).map(r=>r.reentry).join('|'),
   q25_total:q25.final_total,q25_net_profit:q25.net_profit,q25_delta_vs_previous_exit:q25.final_total-baseline.final_total,
   q25_is_best:Math.abs(q25.final_total-best.final_total)<1e-7,q25_gap_to_best:best.final_total-q25.final_total,
   q25_rank:1+group.filter(r=>r.final_total>q25.final_total+1e-7).length,
   q25_liquidation:q25.liquidation,q25_final_shares:q25.final_shares,
   best_liquidation:liqBest.liquidation,best_liquidation_ratio:liqBest.reentry,
   q25_sell_count:q25.sell_count,q25_buy_count:q25.buy_count});
 }
 const topByStart=starts.map(start=>{
  const group=summaries.filter(s=>s.start===start).sort((a,b)=>b.final_total-a.final_total);
  const liq=[...group].sort((a,b)=>b.liquidation-a.liquidation);
  return {start,best:group.slice(0,5),best_liquidated:liq.slice(0,3)};
 });
 const sensitivity=[];
 for(const start of starts.slice(0,2))for(const scenario of [{name:'FG_ONE_DAY_DELAY_STRESS',delay:1},{name:'SLIP0.25PCT_ASSUMPTION',slippage:.0025}])
 for(const exit of exits)for(const reentry of ratios){
  const {name,...changes}=scenario;
  const r=simulate(input.rows,{...options,start,reentry,...exit,...changes});
  sensitivity.push(analyze(r,exit,name).summary);
 }
 testNames.push('480 one-at-a-time sensitivity scenarios preserve the same accounting/no-loss model checks');
 await fs.writeFile(path.join(out,'summary.csv'),csv(summaries));
 await fs.writeFile(path.join(out,'ratio_rank_by_exit.csv'),csv(rankings));
 await fs.writeFile(path.join(out,'all_transactions.csv'),csv(allTrades));
 await fs.writeFile(path.join(out,'sensitivity.csv'),csv(sensitivity));
 await fs.writeFile(path.join(out,'top_by_start.json'),JSON.stringify(topByStart,null,2));
 const detailedKeys=new Set();
 for(const start of starts){
  for(const id of ['P20_OR_R75',...topByStart.find(t=>t.start===start).best.map(t=>t.exit_id)])detailedKeys.add([start,id,.25].join('|'));
  for(const s of topByStart.find(t=>t.start===start).best)detailedKeys.add([start,s.exit_id,s.reentry].join('|'));
 }
 for(const key of detailedKeys){
  const a=model.get(key);const tag=key.replaceAll('|','_').replaceAll('.','p');
  await fs.writeFile(path.join(out,'daily_'+tag+'.csv'),csv(a.daily));
  await fs.writeFile(path.join(out,'ledger_'+tag+'.csv'),csv(a.ledger));
 }
 await fs.writeFile(path.join(out,'specification.json'),JSON.stringify({starts,ratios,exits,common_options:{...options,dividendSchedule:'dividends_verified.json'},
  objective:'Maximize final wealth. No drawdown penalty. Separately value hypothetical final liquidation.',
  initial_allocation:'Initial trend allocation is coupled to reentry ratio, same as prior study; ratio0 disables initial trend participation',
  fixed_vs_state_dependent:'Market indicator tape fixed. Eligibility and sell dates depend on each account position/basis.',
  limitations:['Daily ideal-open retrospective-gate diagnostic only, not real market execution',
   'Historical FG as-of unverified; not original observed data','MMF3% and immediate sweep/access approximate',
   'No untouched OOS; overlapping starts and coarse parameter exploration; no statistical optimality claims']},null,2));
 await fs.writeFile(path.join(out,'input_manifest.json'),JSON.stringify(input.manifest,null,2));
 await fs.writeFile(path.join(out,'verification.json'),JSON.stringify({main_scenarios:summaries.length,sensitivity_scenarios:sensitivity.length,passed:testNames},null,2));
 return {summaries,rankings,topByStart,sensitivity,testNames};
}

