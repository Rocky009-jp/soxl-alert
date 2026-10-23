import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {load,simulate,TAX} from './audit.mjs';

const RATIOS=[0,.1,.25,.5,.75,1];
const STARTS=['2024-10-01','2025-01-02','2025-04-01','2025-07-01','2025-10-01','2026-01-02'];
export function csv(rows) {
 if(!rows.length)return '';
 const keys=[...new Set(rows.flatMap(Object.keys))];
 const quote=v=>v===null||v===undefined?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':typeof v==='object'?'"'+JSON.stringify(v).replaceAll('"','""')+'"':String(v);
 return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>quote(r[k])).join(',')).join('\n')+'\n';
}
function interpret(r,initialTrend) {
 let hasBought=false,initial=null,reentryCount=0;
 const ledger=r.ledger.map(t=>{
  const row={...t};
  if(t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY'].includes(t.type)) {
   if(t.type==='REENTRY'&&!hasBought) {
    assert(initialTrend,'Unexpected initial trend order');
    row.type='INITIAL_TREND';initial=row;
   } else if(t.type==='REENTRY')reentryCount++;
   hasBought=true;
  }
  return row;
 });
 const buys=ledger.filter(t=>t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY','INITIAL_TREND'].includes(t.type));
 const stockSales=ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC');
 const p=r.daily.at(-1);
 const fees=ledger.reduce((a,t)=>a+(t.fee??0),0);
 const tradeTax=stockSales.reduce((a,t)=>a+t.tax,0);
 const mmfNet=ledger.filter(t=>t.type==='MMF_MONTHLY_PROXY').reduce((a,t)=>a+t.gross-t.tax,0)+p.mmf_accrued_gross*(1-TAX);
 const dividendNet=ledger.filter(t=>t.type==='DIVIDEND_ENTITLEMENT').reduce((a,t)=>a+t.net,0);
 const summary={...r.summary,initial_trend_allowed:initialTrend,initial_trend_fraction:r.cfg.reentry,
  initial_trend_date:initial?.date??null,initial_trend_shares:initial?.shares??0,
  first_buy_date:buys[0]?.date??null,first_buy_type:buys[0]?.type??null,
  reentry_after_sale_count:reentryCount,initial_trend_count:initial?1:0,
  total_order_fees:fees,realized_stock_tax:tradeTax,mmf_net_total:mmfNet,
  dividend_net_total:dividendNet,realized_stock_gain:stockSales.reduce((a,t)=>a+t.gain,0),
  final_cash:p.cash,final_unrealized:p.unrealized,final_basis:p.basis,
  total_return_pct:100*(p.total/r.cfg.initial-1)};
 // Economic accounting identity, including unsold value and unpaid income.
 const identity=r.cfg.initial+summary.realized_stock_gain-summary.realized_stock_tax+
   summary.mmf_net_total+summary.dividend_net_total+p.unrealized;
 assert(Math.abs(identity-p.total)<1e-6,'Asset accounting mismatch');
 return {summary,ledger};
}
function checks(r) {
 for(const d of r.daily) {
  assert(d.cash>=-1e-8&&d.shares>=0&&Number.isInteger(d.shares));
  if(!d.shares)assert.equal(d.basis,0);
 }
 for(const t of r.ledger)if(t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC')assert(t.gain+1e-8>=t.basis*.02);
}
export async function runComparison({root,out,schedulePath,previousSummaryPath}={}) {
 await fs.mkdir(out,{recursive:true});
 const input=await load(root),schedule=JSON.parse(await fs.readFile(schedulePath,'utf8'));
 const summaries=[],traces=[],fullRuns=new Map(),passed=[];
 const sigHashes=new Map();
 for(const start of STARTS)for(const initialTrend of [false,true])for(const reentry of RATIOS){
  const r=simulate(input.rows,{start,end:'2026-08-10',initial:10000,reentry,allowInitialReentry:initialTrend,
    dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy',mmfRate:.03,
    closeTargetNet:false,buffer:0,slippage:0,delay:0});
  checks(r);
  const transformed=interpret(r,initialTrend),s=transformed.summary;
  summaries.push(s);
  const tag=start+'_'+(initialTrend?'initial_yes':'initial_no')+'_'+reentry*100;
  await fs.writeFile(path.join(out,'ledger_'+tag+'.csv'),csv(transformed.ledger));
  await fs.writeFile(path.join(out,'daily_'+tag+'.csv'),csv(r.daily));
  await fs.writeFile(path.join(out,'candidates_'+tag+'.csv'),csv(r.candidates));
  const sigHash=crypto.createHash('sha256').update(JSON.stringify(r.signals)).digest('hex');
  if(sigHashes.has(start))assert.equal(sigHashes.get(start),sigHash,'Signal tape changed by allocation');
  else sigHashes.set(start,sigHash);
  traces.push({start,initial_trend:initialTrend,reentry,buys:transformed.ledger.filter(t=>t.status==='FILLED_DIAGNOSTIC'&&['NORMAL','EXFEAR','REENTRY','INITIAL_TREND'].includes(t.type)),
    sales:transformed.ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC')});
  fullRuns.set(tag,{r,transformed});
 }
 passed.push('72 main scenarios: cash/shares nonnegative, shares integer, zero-share basis zero, every sale net gain >=2%, asset accounting identity');
 passed.push('Identical account-independent signal tape across all 12 conditions, for each start date');
 for(const start of STARTS) {
  const a=fullRuns.get(start+'_initial_no_0'),b=fullRuns.get(start+'_initial_yes_0');
  assert.equal(a.r.summary.final_total,b.r.summary.final_total);
  assert.equal(JSON.stringify(a.r.ledger),JSON.stringify(b.r.ledger));
 }
 passed.push('0%: initial yes/no produce identical ledgers for all six starts');
 for(const r of summaries.filter(s=>!s.initial_trend_allowed))assert.equal(r.initial_trend_count,0);
 for(const r of summaries)assert(r.initial_trend_count<=1);
 passed.push('Initial-trend order occurs at most once and never when disabled');
 if(previousSummaryPath) {
  const previous=(await fs.readFile(previousSummaryPath,'utf8')).trim().split(/\r?\n/);
  const header=previous.shift().split(',');
  for(const line of previous){
   const fields=line.split(','),old=Object.fromEntries(header.map((k,i)=>[k.replaceAll('"',''),fields[i]?.replaceAll('"','')]));
   const s=summaries.find(s=>s.start===old.start&&!s.initial_trend_allowed&&s.reentry===Number(old.reentry));
   assert(s,'Missing historical comparison cell');
   assert(Math.abs(s.final_total-Number(old.final_total))<1e-7,'Historical baseline drift');
  }
  passed.push('All 18 overlapping prior issuer-dividend diagnostic cells reproduced exactly');
 }
 const deltas=[];
 for(const start of STARTS)for(const reentry of RATIOS){
  const a=summaries.find(s=>s.start===start&&!s.initial_trend_allowed&&s.reentry===reentry);
  const b=summaries.find(s=>s.start===start&&s.initial_trend_allowed&&s.reentry===reentry);
  deltas.push({start,reentry,no_initial:a.final_total,with_initial:b.final_total,delta:b.final_total-a.final_total,
    initial_trend_date:b.initial_trend_date,first_without:a.first_buy_date,
    liquidation_delta:b.liquidation-a.liquidation});
 }
 const ranking=STARTS.map(start=>{
  const group=summaries.filter(s=>s.start===start).sort((a,b)=>b.final_total-a.final_total);
  const best=group[0].final_total;
  return {start,best_total:best,best_policies:group.filter(s=>Math.abs(s.final_total-best)<1e-7).map(s=>({initial:s.initial_trend_allowed,reentry:s.reentry})),
    baseline25_no:group.find(s=>!s.initial_trend_allowed&&s.reentry===.25).final_total,
    baseline25_yes:group.find(s=>s.initial_trend_allowed&&s.reentry===.25).final_total};
 });
 const sensitivity=[];
 // One assumption at a time, not a joint search; report all 12 policies on the two principal starts.
 for(const start of STARTS.slice(0,2))for(const scenario of [
  {name:'MMF0',mmfRate:0},{name:'MMF2',mmfRate:.02},{name:'MMF4',mmfRate:.04},
  {name:'SLIP_0.25pct_each_side',slippage:.0025},{name:'SLIP_0.5pct_each_side',slippage:.005},
  {name:'FG_ONE_DAY_DELAY_STRESS',delay:1}
 ])for(const initialTrend of [false,true])for(const reentry of RATIOS) {
  const {name,...changes}=scenario;
  const r=simulate(input.rows,{start,reentry,allowInitialReentry:initialTrend,dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy',...changes});
  checks(r);sensitivity.push({scenario:name,...interpret(r,initialTrend).summary});
 }
 const frozenSpec={ratios:RATIOS,starts:STARTS,end:'2026-08-10',initial_USD:10000,USDJPY:150,tax:TAX,
  initial_trend_definition:'Before first actual purchase, permit RSI55 upward-cross entry under F&G>=30 and SOXX>SMA200; allocation equals reentry ratio, so ratio0 disables both',
  after_sale_reentry:'Flat; >=3 trading days since actual full sale at signal decision; same F&G/trend/RSI conditions; next-session execution',
  default_entry_priority:'SELL candidate > EXFEAR/NORMAL > INITIAL_TREND/REENTRY',
  normal_and_exfear_allocation:1,close_target_profit:.20,RSI_sell:75,minimum_net_pre_tax_gain:.02,
  execution:'DIAGNOSTIC ideal next-day daily open; retrospective sale gate and fill-dependent sizing; not a tradable market execution simulation',
  mmf:'3% scenario; day accrual /365 and monthly tax-net reinvestment, instant sweep/access approximation',
  dividends:'Issuer schedule exact amounts, ex-date entitlement, payment-date cash proxy, US10% then JP20.315%',
  FG:'historical_proxy, as-of unverified, missing date blocks dependent signal and resets rearm streak',
  initial_account:'Zero shares, no sale history; indicator/episode warmup only; no carried prior orders',
  objective:'Final total wealth including cash/MMF, net accrued income and unsold SOXL market value; no max-drawdown penalty',
  not_OOS:true,sensitivity:'One-at-a-time assumptions; fixed slippage and FG delay are not observed actual costs/timestamps'};
 await fs.writeFile(path.join(out,'comparison_summary.csv'),csv(summaries));
 await fs.writeFile(path.join(out,'initial_entry_effect.csv'),csv(deltas));
 await fs.writeFile(path.join(out,'rankings.json'),JSON.stringify(ranking,null,2));
 await fs.writeFile(path.join(out,'trade_paths.json'),JSON.stringify(traces,null,2));
 await fs.writeFile(path.join(out,'sensitivity.csv'),csv(sensitivity));
 await fs.writeFile(path.join(out,'specification.json'),JSON.stringify(frozenSpec,null,2));
 await fs.writeFile(path.join(out,'input_manifest.json'),JSON.stringify(input.manifest,null,2));
 await fs.writeFile(path.join(out,'verification.json'),JSON.stringify({main_scenarios:summaries.length,sensitivity_scenarios:sensitivity.length,passed,signal_tape_hashes:Object.fromEntries(sigHashes)},null,2));
 return {summaries,deltas,ranking,sensitivity,passed,spec:frozenSpec};
}

