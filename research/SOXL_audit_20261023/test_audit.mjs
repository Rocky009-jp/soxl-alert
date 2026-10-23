import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {TAX,commission,quantity,rsiWilder,saleFloor,sellCosts,buy,sell,signals,invariant,simulate,load} from './audit.mjs';
import {compileSell,compileBuy,quoteModel} from './causal_execution.mjs';
export async function testAll(root='work/raw'){
const passed=[];const test=(name,fn)=>{fn();passed.push(name);};
test('Wilder textbook RSI seed and smoothing',()=>{
 const x=[44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28,46.00];
 const r=rsiWilder(x);assert(Math.abs(r[14]-70.464135)<.00001);assert(Math.abs(r[15]-66.249619)<.00001);
});
test('Zero and positive-only RSI',()=>{assert.equal(rsiWilder(Array(16).fill(5))[14],50);assert.equal(rsiWilder(Array.from({length:16},(_,i)=>i))[14],100);});
test('Commission cap and small amount',()=>{assert.equal(commission(50000),22);assert.equal(commission(2.22),0);});
test('Integer shares reserve commission',()=>{const n=quantity(10000,36.59);assert.equal(n,272);assert(n*36.59+commission(n*36.59)<=10000);});
test('Weighted basis and full sale reset',()=>{const a={cash:10000,shares:0,basis:0};buy(a,10,5000);buy(a,15,5000);const basis=a.basis;assert.equal(basis,10000-a.cash);assert(sell(a,30,'2026-02-01'));assert.equal(a.basis,0);assert.equal(a.shares,0);});
test('Failed loss gate preserves every balance',()=>{const a={cash:100,shares:100,basis:1000};const before={...a};assert.equal(sell(a,9,'2026-02-01'),null);assert.deepEqual(a,before);});
test('Precomputed price floor includes fees and SEC',()=>{for(const n of [1,7,100,5000]){const b=n*35.92+commission(n*35.92),p=saleFloor(n,b,'2026-07-01');assert(n*p-sellCosts(n,p,'2026-07-01')>=b*1.02-1e-7);}});
const row=(date,fg,rsi=50,shd=-1)=>({date,fg,rsi,soxx:200,sma:100,shd});
test('ExFear rearms only after three consecutive observations',()=>{const s=signals([row('1',24),row('2',31),row('3',31),row('4',24),row('5',31),row('6',31),row('7',31),row('8',24)]);assert.deepEqual(s.filter(r=>r.ex).map(r=>r.date),['1','8']);});
test('Missing FG breaks three-day consecutive rearm',()=>{const s=signals([row('1',24),row('2',31),row('3',31),row('4',null),row('5',31),row('6',24)]);assert.equal(s.filter(r=>r.ex).length,1);});
test('Normal buy excludes FG30 and uses rising edge',()=>{const s=signals([row('1',30),row('2',28),row('3',28),row('4',31),row('5',28)]);assert.deepEqual(s.filter(r=>r.normal).map(r=>r.date),['2','5']);});
test('Fear episode suppresses normal buy',()=>{assert(!signals([row('1',24),row('2',28)])[1].normal);});
test('RSI55 cross is strict and uses previous day',()=>{const s=signals([row('1',35,55),row('2',35,55),row('3',35,55.1)]);assert(!s[1].reCandidate);assert(s[2].reCandidate);});
test('Changing future indicators cannot change previous signal prefix',()=>{
 const a=[row('1',31,54),row('2',28,53),row('3',24,40),row('4',50,70)];
 const b=a.map(r=>({...r}));b[3].fg=1;b[3].rsi=1;assert.deepEqual(signals(a).slice(0,3),signals(b).slice(0,3));
});
const account={cash:10000,shares:100,basis:1000},decision={available_ms:1000,execution_date:'2026-07-01'};
test('Strict no-loss rejects unrestricted market sell',()=>{assert.equal(compileSell(account,decision,{date:'2026-07-01',submitted_ms:2000}).status,'INCOMPATIBLE');});
test('Order compiler rejects future observation',()=>{assert.throws(()=>compileSell(account,decision,{date:'2026-07-01',submitted_ms:500,kind:'LIMIT'}));});
test('Buy sizing uses observable quote only',()=>{assert.throws(()=>compileBuy(account,decision,{observed_ms:2100,ask:10,bid:9.99},{submitted_ms:2000}));});
test('Limit order below floor remains unfilled',()=>{const o=compileSell(account,decision,{date:'2026-07-01',submitted_ms:2000,kind:'LIMIT'});const fill=quoteModel(account,o,{observed_ms:2099,bid:9,ask:9.01,bid_size_shares:1000},{arrival_ms:2100});assert.equal(fill.status,'NOT_MARKETABLE_RETAIN_POSITION');assert.equal(account.shares,100);});
test('Limit order quote model respects profit floor',()=>{const o=compileSell(account,decision,{date:'2026-07-01',submitted_ms:2000,kind:'LIMIT'});const fill=quoteModel(account,o,{observed_ms:2099,bid:o.limit,ask:o.limit+.01,bid_size_shares:1000},{arrival_ms:2100});assert.equal(fill.status,'QUOTE_MODEL_ONLY');assert(fill.quantity*fill.price-fill.fee>=account.basis*1.02);});
test('Insufficient displayed depth is unconfirmed',()=>{const o=compileSell(account,decision,{date:'2026-07-01',submitted_ms:2000,kind:'LIMIT'});assert.equal(quoteModel(account,o,{observed_ms:2099,bid:50,ask:50.01,bid_size_shares:1},{arrival_ms:2100}).status,'DEPTH_INSUFFICIENT_UNCONFIRMED');});
test('Stale and future arrival quotes rejected',()=>{const o=compileSell(account,decision,{date:'2026-07-01',submitted_ms:2000,kind:'LIMIT'});assert.throws(()=>quoteModel(account,o,{observed_ms:2200},{arrival_ms:2100}));assert.equal(quoteModel(account,o,{observed_ms:500,bid:50,ask:50.01,bid_size_shares:1000},{arrival_ms:2100}).status,'STALE');});
const input=await load(root),dividends=input.coverage.dividends;
const legacy=[0,.25,1].map(reentry=>simulate(input.rows,{reentry,allowInitialReentry:true,dividends}));
test('Reported ideal-opening totals reproduced at published dollar precision',()=>{assert.deepEqual(legacy.map(r=>Math.round(r.summary.final_total)),[41135,44683,26327]);});
test('Reported three legacy reentry dates reproduced',()=>{assert.deepEqual(legacy[1].ledger.filter(t=>t.type==='REENTRY'&&t.status==='FILLED_DIAGNOSTIC').map(t=>t.date),['2024-10-07','2026-02-09','2026-06-09']);});
test('Independent start requires previous actual full sale',()=>{assert(!simulate(input.rows,{reentry:.25,dividends}).ledger.some(t=>t.date==='2024-10-07'&&t.type==='REENTRY'));});
test('Every diagnostic sale meets fee-inclusive two-percent floor',()=>{for(const r of legacy)for(const t of r.ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC'))assert(t.gain>=t.basis*.02-1e-7);});
test('All daily balances preserve ownership and mark-to-market identities',()=>{for(const r of legacy)for(const d of r.daily){invariant(d);assert(Math.abs(d.total-(d.cash+d.market_value+d.mmf_accrued_gross*(1-TAX)+d.dividend_receivable_net))<1e-7);}});
test('Injected reentry-disable fault reproduces identical totals but is explicitly not original code',()=>{const bad=[0,.25,1].map(reentry=>simulate(input.rows,{reentry,bugDisableReentry:true,dividends}));assert(bad.every(r=>r.summary.reentry_count===0));assert(bad.every(r=>r.summary.final_total===bad[0].summary.final_total));});
test('One-day-delay FG does not impute missing observation',()=>{const a=signals([row('1',31),row('2',null),row('3',20)],{delay:1});assert.equal(a[2].fg_used,null);});
const synthetic=input.rows.filter(r=>r.date>='2025-02-01'&&r.date<='2025-02-21').map((r,i)=>({...r,fg:i===0?24:26,rsi:20,open:10,close:10,low:9,high:11}));
test('Dividend entitlement and cash payment are separated',()=>{
 const ex=synthetic[3].date,pay=synthetic[6].date,r=simulate(synthetic,{start:synthetic[0].date,end:synthetic.at(-1).date,mmfRate:0,dividendSchedule:[{ex_date:ex,pay_date:pay,amount:.1}]});
 const accr=r.daily.find(d=>d.date===ex),paid=r.daily.find(d=>d.date===pay);assert(accr.dividend_receivable_net>0);assert.equal(paid.dividend_receivable_net,0);assert(paid.cash>accr.cash);
});
test('Buying on ex-date does not acquire cash distribution entitlement',()=>{
 const r=simulate(synthetic,{start:synthetic[0].date,end:synthetic.at(-1).date,mmfRate:0,dividendSchedule:[{ex_date:synthetic[1].date,pay_date:synthetic[6].date,amount:.1}]});assert(!r.ledger.some(t=>t.type==='DIVIDEND_ENTITLEMENT'));
});
test('Unliquidated final holdings remain valued; hypothetical tax never forces liquidation',()=>{const r=simulate(synthetic,{start:synthetic[0].date,end:synthetic.at(-1).date,mmfRate:0});assert(r.summary.final_shares>0);assert(r.summary.final_total>r.daily.at(-1).cash);});
return {passed:passed.length,tests:passed,scope:'Synthetic accounting/causality tests and retrieved-data diagnostic regressions; no live execution or actual minute-data performance verified'};
}

