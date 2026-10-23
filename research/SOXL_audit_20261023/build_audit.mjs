import fs from 'node:fs/promises';
import path from 'node:path';
import {run,load,simulate} from './audit.mjs';
import {testAll} from './test_audit.mjs';
export function csv(rows){
 const keys=[...new Set(rows.flatMap(Object.keys))];
 const quote=x=>x==null?'':typeof x==='string'?'"'+x.replaceAll('"','""')+'"':JSON.stringify(x);
 return keys.join(',')+'\n'+rows.map(r=>keys.map(k=>quote(r[k])).join(',')).join('\n')+'\n';
}
export async function build(root='work/raw',out='outputs/SOXL_audit_20261023',schedulePath='work/dividends_verified.json'){
 const result=await run(root,out);const input=await load(root);
 const tests=await testAll(root);await fs.writeFile(path.join(out,'test_results.json'),JSON.stringify(tests,null,2));
 const schedule=JSON.parse(await fs.readFile(schedulePath,'utf8'));
 const legacy=[0,.25,1].map(reentry=>simulate(input.rows,{reentry,allowInitialReentry:true,dividends:input.coverage.dividends}));
 const rec=legacy.map((r,i)=>({reentry:r.cfg.reentry,reported_total:[41135,44683,26327][i],reproduced_total:r.summary.final_total,
   reproduced_pure_profit:r.summary.net_profit,published_rounding_difference:Math.round(r.summary.final_total)-[41135,44683,26327][i],
   note:'Recovered numerical reproduction, not proof original code is identical'}));
 await fs.writeFile(path.join(out,'legacy_reconciliation.csv'),csv(rec));
 for(const r of legacy) {
   await fs.writeFile(path.join(out,'legacy_ledger_'+r.cfg.reentry*100+'.csv'),csv(r.ledger));
 }
 const modes=[];
 for(const allowInitialReentry of [true,false])for(const closeTargetNet of [false,true])for(const reentry of [0,.25,1]) {
   modes.push(simulate(input.rows,{reentry,allowInitialReentry,closeTargetNet,dividends:input.coverage.dividends}).summary);
 }
 await fs.writeFile(path.join(out,'initial_state_and_target_variants.csv'),csv(modes));
 const improved=[];
 for(const start of ['2024-10-01','2025-01-02','2025-04-01','2025-07-01','2025-10-01','2026-01-02'])
 for(const reentry of [0,.25,1]){
   const r=simulate(input.rows,{start,reentry,dividendSchedule:schedule,dividendMode:'issuer_exact_pay_date_proxy'});
   improved.push(r.summary);const tag=start+'_'+reentry*100;
   await fs.writeFile(path.join(out,'issuer_dividend_ledger_'+tag+'.csv'),csv(r.ledger));
   await fs.writeFile(path.join(out,'issuer_dividend_daily_'+tag+'.csv'),csv(r.daily));
 }
 await fs.writeFile(path.join(out,'issuer_dividend_diagnostic_summary.csv'),csv(improved));
 const bufferCases=[0,.005,.01].map(buffer=>simulate(input.rows,{reentry:.25,allowInitialReentry:true,buffer,dividends:input.coverage.dividends}).summary);
 await fs.writeFile(path.join(out,'buffer_scenarios_NOT_attribution.csv'),csv(bufferCases));
 const prospective=new Map();
 // Keep every account-independent buy/reentry candidate, plus sale candidates from both init conventions
 // and target definitions. For strict no-loss limit paths, candidate dates can expand further.
 for(const r of [...legacy,...[0,.25,1].map(reentry=>simulate(input.rows,{reentry,dividends:input.coverage.dividends}))]){
   for(const c of r.candidates){
     const i=input.rows.findIndex(t=>t.date===c.date);const d=input.rows[i+1]?.date;if(!d||d>'2026-08-10')continue;
     for(const offset of [0,1,3,5]){
       const key=d+'_'+offset,old=prospective.get(key);const types=[c.ex?'EXFEAR':null,c.normal?'NORMAL':null,c.reCandidate?'RE_CANDIDATE':null,c.sellCandidate?'SELL_CANDIDATE':null].filter(Boolean);
       prospective.set(key,{date:d,offset_minutes:offset,time_ET:'09:'+String(30+offset).padStart(2,'0')+':00',
         signal_date:c.date,reasons:[...new Set([...(old?.reasons??[]),...types])],adjusted:false,
         minute_status:'MISSING',nbbo_status:'MISSING',note:'Preliminary union, not final trading path'});
     }
   }
 }
 await fs.writeFile(path.join(out,'intraday_request_manifest.csv'),csv([...prospective.values()].sort((a,b)=>a.date.localeCompare(b.date)||a.offset_minutes-b.offset_minutes).map(r=>({...r,reasons:r.reasons.join('|')}))));
 // Same fixed event list execution-quality comparison is also blocked, separate from strategy path runs.
 await fs.writeFile(path.join(out,'fixed_signal_execution_comparison.csv'),csv([...prospective.values()].map(r=>({date:r.date,offset_minutes:r.offset_minutes,buy_price:null,sell_price:null,spread_bps:null,status:'BLOCKED_MISSING_NBBO_OR_MINUTE_DATA'}))));
 return {rec,improved,tests,main:result.summary,dates:prospective.size/4,minuteCells:prospective.size,bufferCases};
}

