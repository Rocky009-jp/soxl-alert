import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(process.argv[2]??'.'),here=path.dirname(fileURLToPath(import.meta.url));
const {load,signals,commission}=await import(pathToFileURL(path.join(root,'research/SOXL_allocation_separation_20261026/engine.mjs')));
function parse(text){let rows=[],r=[],v='',q=false;for(let i=0;i<text.length;i++){let c=text[i];if(q){if(c==='"'){if(text[i+1]==='"'){v+='"';i++;}else q=false;}else v+=c;}else if(c==='"')q=true;else if(c===','){r.push(v);v='';}else if(c==='\n'){r.push(v);rows.push(r);r=[];v='';}else if(c!=='\r')v+=c;}if(v||r.length){r.push(v);rows.push(r);}const h=rows.shift();return rows.filter(x=>x.length>1).map(x=>Object.fromEntries(h.map((k,i)=>[k,x[i]])));}
const source=fs.readFileSync(path.join(root,'research/reentry_mechanism_20261026/event_comparison.csv'));
const input=await load(path.join(root,'research/SOXL_exit_study_20261023/data'));
const tapes=new Map([0,1].map(delay=>[delay,new Map(signals(input.rows,{delay}).map(x=>[x.date,x]))]));
const events=parse(source.toString()),counts={},audit=[];
const number=x=>x===''||x==null?null:Number(x);
for(const e of events){counts[e.status]=(counts[e.status]??0)+1;
 const reported=number(e.D_fg_used),expected=tapes.get(Number(e.fg_delay)).get(e.D).fg_used;
 const mismatch=reported!==expected;
 let budget=null,oneCost=null,reason='';
 if(e.status==='INSUFFICIENT_INTEGER_SHARE'){const fraction=e.order_type==='REENTRY'?(e.allocation_class==='INITIAL_TREND'?.25:Number(e.R)):1;budget=Number(e.cash_before)*fraction;oneCost=Number(e.exec_open)+commission(Number(e.exec_open));reason=budget+1e-8<oneCost?'budget_below_one_share_including_fee':'unresolved';}
 audit.push({start:e.start,fg_delay:Number(e.fg_delay),R:Number(e.R),D:e.D,exec_date:e.exec_date,kind:e.allocation_class,status:e.status,reported_D_fg_used:reported,correct_D_fg_used:expected,fg_annotation_mismatch:mismatch,reported_zero_share_reason:e.zero_share_reason,calculated_budget:budget,one_share_cost_including_fee:oneCost,correct_zero_share_reason:reason});
}
const mismatches=audit.filter(x=>x.fg_annotation_mismatch);
const result={source_sha:'9f066e51286278677803357dde5ab7be1b4454fd',source_event_csv_sha256:crypto.createHash('sha256').update(source).digest('hex'),event_rows:events.length,status_counts:counts,fg_annotation_mismatch_count:mismatches.length,mismatches_by_delay:Object.fromEntries([0,1].map(d=>[d,mismatches.filter(x=>x.fg_delay===d).length])),zero_share_rows:audit.filter(x=>x.status==='INSUFFICIENT_INTEGER_SHARE').length,unresolved_zero_share_reasons:audit.filter(x=>x.correct_zero_share_reason==='unresolved').length,scope:'annotation audit only; original engine/input/PnL unchanged; expected F&G computed by pinned signals(delay); no fresh market data'};
fs.writeFileSync(path.join(here,'annotation_audit.json'),JSON.stringify(result,null,2)+'\n');
const h=Object.keys(audit[0]),q=x=>x==null?'':typeof x==='string'?'"'+x.replaceAll('"','""')+'"':String(x);fs.writeFileSync(path.join(here,'annotation_corrections.csv'),h.join(',')+'\n'+audit.map(r=>h.map(k=>q(r[k])).join(',')).join('\n')+'\n');
console.log(JSON.stringify(result,null,2));
