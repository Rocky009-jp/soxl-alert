// Separated-allocation copy of research/SOXL_exit_study_20261023/audit_exit.mjs (source SHA256 9fe10b51...ed5ec0a, not edited).
// ONLY change: simulate() accepts initialRatio (I, used while no sale has ever been FILLED) and reentryRatio (R, after a filled sale).
// When neither is given both fall back to cfg.reentry, which reproduces the legacy I=R coupling and allowInitialReentry behaviour.
// csv()/run() of the original were dropped (unused here). Everything else is byte-for-byte original logic.
// BUY-TRIGGER ABLATION COPY (from the above engine, sha256 89d766da...c239): adds cfg.enableNormal / cfg.enableExFear (default true, boolean-checked).
// A false flag only stops the market-side NORMAL / EXFEAR from becoming the pending order; signals(), armed/streak/prevNormal state, sale priority,
// reentry eligibility (I/R/cooldown), sale gate and accounting are unchanged. A suppressed order is recorded as candidates[].suppressed_market_order (only when a flag is false).
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

export const TAX = 0.20315;
export const round2 = x => Math.round((x + 1e-10) * 100) / 100;
const ceil2 = x => Math.ceil((x - 1e-10) * 100) / 100;
export function commission(gross) { return gross <= 2.22 ? 0 : round2(Math.min(22, gross * 0.00495)); }
export function secRate(d) {
  // Rakuten local trade-date schedule confirmed against its 2025-05-09 notice and current fees page.
  return d >= '2026-04-02' ? 0.0000206 : d >= '2025-05-13' ? 0 : 0.0000278;
}
export function sellCosts(n, p, d) { return commission(n * p) + ceil2(n * p * secRate(d)); }
export function saleFloor(n, basis, d, minimumGain = .02) {
  // Set before observing future execution. A $0.01 limit guarantees the model's net proceeds floor.
  let lo = 0, hi = Math.max(1, basis * (1 + minimumGain) / n + 2);
  while (hi*n-sellCosts(n,hi,d) < basis*(1+minimumGain)) hi *= 2;
  for(let k=0;k<80;k++) {let m=(lo+hi)/2; if(m*n-sellCosts(n,m,d)>=basis*(1+minimumGain)) hi=m;else lo=m;}
  return Math.ceil((hi-1e-9)*100)/100;
}
export function quantity(budget,p) {
  let n=Math.floor(budget/p);
  while(n>0 && n*p+commission(n*p)>budget+1e-8)n--;
  return n;
}
export function rsiWilder(a,n=14) {
  const out=a.map(()=>null);let g=0,l=0;
  for(let i=1;i<a.length;i++){
    const delta=a[i]-a[i-1],up=Math.max(0,delta),dn=Math.max(0,-delta);
    if(i<=n){g+=up/n;l+=dn/n;}else{g=(g*(n-1)+up)/n;l=(l*(n-1)+dn)/n;}
    if(i>=n)out[i]=g===0&&l===0?50:l===0?100:100-100/(1+g/l);
  }return out;
}
function parseCSV(s) {const lines=s.trim().split(/\r?\n/);const heads=lines.shift().split(',');return lines.map(l=>Object.fromEntries(l.split(',').map((v,i)=>[heads[i],v])));}
export async function load(root='work/raw') {
  const filenames=['daily.json','daily_adjclose.csv','fear-greed.csv'];
  const buffers=await Promise.all(filenames.map(f=>fs.readFile(path.join(root,f))));
  const manifest=filenames.map((f,i)=>({file:f,bytes:buffers[i].length,sha256:crypto.createHash('sha256').update(buffers[i]).digest('hex')}));
  const daily=JSON.parse(buffers[0]), market=parseCSV(buffers[1].toString()), fg=parseCSV(buffers[2].toString());
  const mm=new Map(market.map(r=>[r.Date,r])), ff=new Map(fg.map(r=>[r.Date,Number(r['Fear Greed'])]));
  const a=daily.references.SOXX.adjClose, rsi=rsiWilder(a), b=daily.funds.SOXL.ohlcv;
  const bars=new Map(b.date.map((d,i)=>[d,{open:b.open[i],high:b.high[i],low:b.low[i],close:b.close[i],volume:b.volume[i]}]));
  const common=daily.date.filter(d=>mm.has(d));
  const shd=new Map(common.map((d,i)=>[d,i<20?null:100*(Number(mm.get(d).SPY)/Number(mm.get(common[i-20]).SPY)-Number(mm.get(d).IEF)/Number(mm.get(common[i-20]).IEF))]));
  let sum=0;
  const rows=daily.date.map((d,i)=>{
    sum+=a[i];if(i>=200)sum-=a[i-200];
    return {date:d,index:i,soxx:a[i],rsi:rsi[i],sma:i>=199?sum/200:null,shd:shd.get(d)??null,fg:ff.get(d)??null,...bars.get(d)};
  });
  const missingFG=rows.filter(r=>r.date>='2024-09-01'&&r.date<='2026-08-10'&&r.fg===null).map(r=>r.date);
  const ohlcInvalid=rows.filter(r=>r.open!==undefined&&(!(r.low<=r.open&&r.open<=r.high&&r.low<=r.close&&r.close<=r.high)||r.volume<0)).map(r=>r.date);
  const duplicates=x=>x.filter((d,i)=>i&&d<=x[i-1]);
  const coverage={
    input_manifest:manifest,priceSource:daily.source,priceNote:daily.note,
    date_order_errors:{daily:duplicates(daily.date),ohlcv:duplicates(b.date),market:duplicates(market.map(r=>r.Date)),fg:duplicates(fg.map(r=>r.Date))},
    missing_fg:missingFG,invalid_ohlc:ohlcInvalid,
    target_rows:rows.filter(r=>r.date>='2024-10-01'&&r.date<='2026-08-10').length,
    missing_target_ohlc:rows.filter(r=>r.date>='2024-10-01'&&r.date<='2026-08-10'&&r.open===undefined).map(r=>r.date),
    missing_target_shd:rows.filter(r=>r.date>='2024-10-01'&&r.date<='2026-08-10'&&r.shd===null).map(r=>r.date),
    splits:daily.funds.SOXL.splits,dividends:daily.funds.SOXL.dividends.filter(x=>x[0]>='2024-10-01'&&x[0]<='2026-08-10'),
    input_market_last:market.at(-1).Date,
    historical_fg_asof:'UNVERIFIED: no original observation or decision timestamp available'
  };
  // Source sanity assertions verify retrieved values, not independent vendor accuracy.
  assert.equal(round2(Number(mm.get('2020-03-16')['^VIX'])),82.69);
  assert(!mm.has('2011-09-05'));
  return {rows,coverage,manifest,daily,market};
}
export function signals(rows,{delay=0,initialArmed=true}={}) {
  let armed=initialArmed,streak=0,prevNormal=false;
  return rows.map((r,i)=>{
    const f=i>=delay?rows[i-delay].fg:null;
    let ex=false;
    if(f===null)streak=0;
    else {
      streak=f>=30?streak+1:0;
      if(streak>=3)armed=true;
      if(f<25&&armed){ex=true;armed=false;}
    }
    const normalRaw=f!==null&&f>=25&&f<30&&r.soxx>r.sma&&r.rsi<=55&&r.shd!==null&&r.shd<0;
    const normal=normalRaw&&!prevNormal&&armed&&!ex;
    const reCandidate=f!==null&&f>=30&&r.soxx>r.sma&&i>0&&rows[i-1].rsi!==null&&rows[i-1].rsi<=55&&r.rsi>55;
    prevNormal=normalRaw;
    return {...r,fg_used:f,fg_quality:delay?'one_day_delay_stress':'historical_proxy',armed,streak,ex,normal,normal_raw:normalRaw,reCandidate,
      signal_date:r.date,observation_timestamp:null,decision_timestamp:null,decision_phase:'after_US_regular_close_assumed',
      event_id:r.date+':'+(ex?'EXFEAR':normal?'NORMAL':reCandidate?'RE_CANDIDATE':'NONE')};
  });
}
export function invariant(s) {
  assert(Number.isInteger(s.shares)&&s.shares>=0,'shares integer >= 0');
  assert(s.cash>=-1e-7,'cash >= 0');assert(s.basis>=-1e-7,'basis >= 0');
  if(s.shares===0)assert.equal(s.basis,0,'zero shares means zero basis');
}
export function buy(s,p,budget) {
  const n=quantity(Math.min(s.cash,budget),p);
  if(!n)return null;
  const fee=commission(n*p),cost=n*p+fee;
  s.cash-=cost;s.shares+=n;s.basis+=cost;invariant(s);
  return {shares:n,price:p,fee,cost,tax:0};
}
export function sell(s,p,date,gate=true) {
  const fee=sellCosts(s.shares,p,date),gain=s.shares*p-fee-s.basis;
  if(!s.shares|| (gate&&gain+1e-8 < s.basis*.02))return null;
  const tx={shares:s.shares,price:p,fee,basis:s.basis,gain,tax:Math.max(0,gain)*TAX};
  s.cash+=s.shares*p-fee-tx.tax;s.shares=0;s.basis=0;invariant(s);return tx;
}
export function simulate(input,options={}) {
  const cfg={start:'2024-10-01',end:'2026-08-10',initial:10000,reentry:.25,mmfRate:.03,buffer:0,slippage:0,
    mode:'legacy_oracle_open_DIAGNOSTIC',initialRatio:undefined,reentryRatio:undefined,profitTarget:.20,exitRsi:75,exitMode:'OR',delay:0,bugDisableReentry:false,allowInitialReentry:false,closeTargetNet:false,dividendMode:'source_rounded_exdate_proxy',dividendSchedule:null,...options};
  for(const k of ['enableNormal','enableExFear']){cfg[k]=options[k]??true;if(typeof cfg[k]!=='boolean')throw new Error(k+' must be boolean');}
  const sig=signals(input,{delay:cfg.delay});
  const s={cash:cfg.initial,shares:0,basis:0,accrued:0,dividendReceivable:0};
  let pending=null,lastSale=null,prevDate=null;
  const ledger=[],daily=[],candidates=[];
  const divMap=new Map(options.dividends??[]);
  const distributions=[];
  for(let i=0;i<sig.length;i++){
    const r=sig[i];if(r.date<cfg.start||r.date>cfg.end)continue;
    assert(r.open!==undefined&&r.close!==undefined,'Missing execution OHLC: '+r.date);
    // Economic shadow MMF only: instant sweep and access, NOT Rakuten operational simulation.
    if(prevDate) {
      let d=new Date(prevDate+'T00:00:00Z'),end=new Date(r.date+'T00:00:00Z');
      while(d<end){
        s.accrued+=s.cash*cfg.mmfRate/365;const prevMonth=d.getUTCMonth();d.setUTCDate(d.getUTCDate()+1);
        if(d.getUTCMonth()!==prevMonth){const tax=s.accrued*TAX; s.cash+=s.accrued-tax;ledger.push({date:d.toISOString().slice(0,10),type:'MMF_MONTHLY_PROXY',gross:s.accrued,tax});s.accrued=0;}
      }
    }
    // Entitlement before ex-date open. Proxy booked ex-date; exact pay-date ledger is blocked.
    if(cfg.dividendSchedule) {
      for(const div of cfg.dividendSchedule.filter(d=>d.ex_date===r.date)) {
        if(s.shares&&div.amount>0) {
          const gross=s.shares*div.amount,us=gross*.1,jp=(gross-us)*TAX,net=gross-us-jp;
          distributions.push({...div,entitled_shares:s.shares,net});s.dividendReceivable+=net;
          ledger.push({date:r.date,type:'DIVIDEND_ENTITLEMENT',shares:s.shares,gross,us_tax:us,tax:jp,net,pay_date:div.pay_date});
        }
      }
      for(const d of distributions.filter(d=>!d.paid&&d.pay_date<=r.date)) {
        s.cash+=d.net;s.dividendReceivable-=d.net;d.paid=true;
        ledger.push({date:r.date,type:'DIVIDEND_PAYMENT_DATE_PROXY',net:d.net,ex_date:d.ex_date,exact_broker_credit_timestamp:null});
      }
    } else if(divMap.has(r.date)&&s.shares) {
      const gross=s.shares*divMap.get(r.date),us=gross*.1,jp=(gross-us)*TAX;
      s.cash+=gross-us-jp;ledger.push({date:r.date,type:'DIVIDEND_EXDATE_PROXY',shares:s.shares,gross,us_tax:us,tax:jp,net:gross-us-jp});
    }
    if(pending){
      const base={date:r.date,signal_date:pending.signal_date,event_id:pending.event_id,type:pending.type,
        order_submitted_timestamp:null,execution_timestamp:null,execution_phase:'daily_open_proxy',mode:cfg.mode,
        observation_timestamp:null,fg_quality:r.fg_quality,cash_before:s.cash,shares_before:s.shares,basis_before:s.basis};
      if(pending.type==='SELL'){
        const p=r.open*(1-cfg.slippage);
        const tx=sell(s,p,r.date,true);
        ledger.push({...base,status:tx?'FILLED_DIAGNOSTIC':'GATE_BLOCKED_DIAGNOSTIC',...tx,limit_before_execution:pending.limit,cash_after:s.cash,shares_after:s.shares});
        if(tx)lastSale=i;
      }else{
        const p=r.open*(1+cfg.slippage);
        const tx=buy(s,p,s.cash*pending.fraction*(1-cfg.buffer));
        ledger.push({...base,status:tx?'FILLED_DIAGNOSTIC':'INSUFFICIENT_INTEGER_SHARE',...tx,cash_after:s.cash,shares_after:s.shares});
      }pending=null;
    }
    invariant(s);
    // Account-independent candidates are frozen above; sale eligibility and reentry depend on account state.
    const profit=s.shares?((s.shares*r.close-sellCosts(s.shares,r.close,r.date))/s.basis-1):null;
    const targetProfit=s.shares?(cfg.closeTargetNet?profit:s.shares*r.close/s.basis-1):null;
    const profitHit=targetProfit>=cfg.profitTarget;
    const rsiHit=r.rsi>=cfg.exitRsi;
    const exitHit=cfg.exitMode==='OR'?(profitHit||rsiHit):cfg.exitMode==='PROFIT_ONLY'?profitHit:cfg.exitMode==='RSI_ONLY'?rsiHit:false;
    const sellCandidate=s.shares>0&&profit>=.02&&exitHit;
    const cool=lastSale===null?cfg.allowInitialReentry:i-lastSale>=3;
    // lastSale===null <=> no filled sale yet <=> initial trend participation (a flat account without a sale has never bought).
    const reFraction=lastSale===null?(cfg.initialRatio??cfg.reentry):(cfg.reentryRatio??cfg.reentry);
    const reEligible=!cfg.bugDisableReentry&&reFraction>0&&s.shares===0&&cool&&r.reCandidate;
    if(sellCandidate)pending={type:'SELL',signal_date:r.date,event_id:r.date+':SELL',limit:saleFloor(s.shares,s.basis,sig[i+1]?.date??r.date)};
    else if((r.ex&&cfg.enableExFear)||(r.normal&&cfg.enableNormal))pending={type:r.ex?'EXFEAR':'NORMAL',signal_date:r.date,event_id:r.event_id,fraction:1};
    else if(reEligible)pending={type:'REENTRY',signal_date:r.date,event_id:r.event_id,fraction:reFraction};
    if(sellCandidate||r.ex||r.normal||r.reCandidate)candidates.push({date:r.date,ex:r.ex,normal:r.normal,reCandidate:r.reCandidate,reEligible,sellCandidate,flat:s.shares===0,cooldown:cool,last_sale_index:lastSale,pending:pending?.type??'',profit,...(!sellCandidate&&((r.ex&&!cfg.enableExFear)||(r.normal&&!cfg.enableNormal))?{suppressed_market_order:r.ex?'EXFEAR':'NORMAL'}:{})});
    const mv=s.shares*r.close,total=s.cash+mv+s.accrued*(1-TAX)+s.dividendReceivable;
    const liq=s.shares?mv-sellCosts(s.shares,r.close,r.date):0;
    const liquidation=s.cash+liq-Math.max(0,liq-s.basis)*TAX+s.accrued*(1-TAX)+s.dividendReceivable;
    daily.push({date:r.date,cash:s.cash,shares:s.shares,basis:s.basis,avg_cost:s.shares?s.basis/s.shares:0,
      close:r.close,market_value:mv,unrealized:mv-s.basis,mmf_accrued_gross:s.accrued,dividend_receivable_net:s.dividendReceivable,total,liquidation,
      note:'MMF scenario; dividend ex-date proxy; liquidation is valuation only, never a forced sale'});
    prevDate=r.date;
  }
  const last=daily.at(-1);
  return {cfg,summary:{start:cfg.start,reentry:cfg.reentry,initial_ratio:cfg.initialRatio??cfg.reentry,after_sale_ratio:cfg.reentryRatio??cfg.reentry,mmfRate:cfg.mmfRate,delay:cfg.delay,buffer:cfg.buffer,slippage:cfg.slippage,
    final_total:last.total,final_total_jpy150:last.total*150,net_profit:last.total-cfg.initial,liquidation:last.liquidation,final_shares:last.shares,
    allow_initial_reentry:cfg.allowInitialReentry,close_target_net:cfg.closeTargetNet,
    reentry_count:ledger.filter(t=>t.type==='REENTRY'&&t.status==='FILLED_DIAGNOSTIC').length,
    buy_count:ledger.filter(t=>['NORMAL','EXFEAR','REENTRY'].includes(t.type)&&t.status==='FILLED_DIAGNOSTIC').length,
    sell_count:ledger.filter(t=>t.type==='SELL'&&t.status==='FILLED_DIAGNOSTIC').length,
    blocked_sales:ledger.filter(t=>t.status==='GATE_BLOCKED_DIAGNOSTIC').length,
    status:'DIAGNOSTIC_ONLY_NOT_TRADABLE_RESULTS'},ledger,daily,candidates,signals:sig.filter(r=>r.date>=cfg.start&&r.date<=cfg.end)};
}
