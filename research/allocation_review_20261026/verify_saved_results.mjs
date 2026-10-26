// Verify a checkout of research commit 37a14c0 after running its run.mjs.
// node verify_saved_results.mjs PATH_TO_RESEARCH_CHECKOUT
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(process.argv[2]??'.');
const read=p=>fs.readFileSync(path.join(root,p));
const blob=b=>crypto.createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
const reference=JSON.parse(fs.readFileSync(path.join(here,'artifact_hash_checks.json')));
const matches=reference.map(r=>({path:r.path,expected:r.expected,actual:blob(read(r.path))})).map(r=>({...r,match:r.actual===r.expected}));
assert.equal(matches.length,53);
assert(matches.filter(r=>!r.match).every(r=>r.path.endsWith('/environment.json')),'unexpected artifact mismatch');
function csv(text){const rr=[];let row=[],v='',q=false;for(let i=0;i<text.length;i++){const c=text[i];if(q){if(c==='"'){if(text[i+1]==='"'){v+='"';i++;}else q=false;}else v+=c;}else if(c==='"')q=true;else if(c===','){row.push(v);v='';}else if(c==='\n'){row.push(v);rr.push(row);row=[];v='';}else if(c!=='\r')v+=c;}if(v||row.length){row.push(v);rr.push(row);}const h=rr.shift();return rr.filter(r=>r.length>1).map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]])));}
const rows=csv(read('research/SOXL_allocation_separation_20261026/summary.csv').toString());
assert.equal(rows.length,252);assert.equal(new Set(rows.map(r=>r.candidate_id)).size,21);
const expected=JSON.parse(fs.readFileSync(path.join(here,'summary_checks.json')));
for(const g of expected.terminal_groups){const group=rows.filter(r=>r.start===g.start&&+r.fg_delay===g.fg_delay);assert.equal(group.length,21);const max=Math.max(...group.map(r=>+r.final_total));assert.equal(max,g.winner_total);assert.deepEqual(group.filter(r=>Math.abs(+r.final_total-max)<1e-7).map(r=>r.candidate_id),g.winners);assert(g.winners.every(id=>id.startsWith('NO_SELL_')));assert.equal(+group.find(r=>r.candidate_id==='P20_OR_R75_I25_R25').final_total,g.baseline);}
const data=JSON.parse(read('research/SOXL_exit_study_20261023/data/daily.json'));
const evidence=read('research/SOXL_audit_20261023/evidence/yahoo_SOXL.json');
assert.equal(blob(evidence),'7dbe382acfd5b85c1cd19ec780363e111850aa80');
const y=JSON.parse(evidence).chart.result[0],q=y.indicators.quote[0],b=data.funds.SOXL.ohlcv;
const dates=new Map(y.timestamp.map((t,i)=>[new Date(t*1000).toISOString().slice(0,10),i]));
const priceChecks=['open','high','low','close'].map(field=>{let n=0,max=0;for(let i=0;i<b.date.length;i++){const date=b.date[i];if(date<'2024-10-01'||date>'2026-08-10')continue;const j=dates.get(date);assert(j!=null&&q[field][j]!=null);const rel=Math.abs(b[field][i]/q[field][j]-1);assert(rel<=.00005);n++;max=Math.max(max,rel);}assert.equal(n,465);return {field,compared:n,max_relative_error:max};});
console.log(JSON.stringify({passed:true,artifact_count:matches.length,exact:matches.filter(r=>r.match).length,environment_mismatch_allowed:true,main_rows:rows.length,terminal_groups:expected.terminal_groups.length,price_checks:priceChecks},null,2));
