import fs from 'node:fs';
import crypto from 'node:crypto';
const folder='research/buy_trigger_ablation_20261026';
const parse=(file)=>{const [h,...lines]=fs.readFileSync(file,'utf8').trim().split(/\r?\n/);const split=line=>{const a=[];let s='',q=false;for(let i=0;i<line.length;i++){let c=line[i];if(c==='"'){if(q&&line[i+1]==='"'){s+='"';i++;}else q=!q;}else if(c===','&&!q){a.push(s);s='';}else s+=c;}a.push(s);return a;};const keys=split(h);return lines.map(l=>Object.fromEntries(split(l).map((v,i)=>[keys[i],v])));};
const S=parse(folder+'/summary.csv'), P=parse(folder+'/paired_effects.csv');
const old=parse('research/profit_target_isolated_20261026/summary.csv');
const expected=JSON.parse(fs.readFileSync(new URL('./expected_blobs.json',import.meta.url),'utf8'));
const hashChecks=expected.map(x=>{const b=fs.readFileSync(x.path);const blob=crypto.createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');return {...x,actual:blob,match:blob===x.expected};});
const get=(id,start,delay)=>S.find(s=>s.candidate_id===id&&s.start===start&&s.fg_delay===delay);
const pairedErrors=[];
for(const r of P){const on=get(r.profile+'__BOTH_ON',r.start,r.fg_delay),off=get(r.profile+'__'+r.off_setting,r.start,r.fg_delay);if(!on||!off||Math.abs(Number(off.final_total)-Number(on.final_total)-Number(r.off_minus_on))>1e-6)pairedErrors.push(r);}
const reuseErrors=S.filter(s=>s.source==='reuse_77bb44f').filter(s=>{const o=old.find(t=>t.candidate_id===s.source_candidate_id&&t.start===s.start&&t.fg_delay===s.fg_delay);return !o||Math.abs(Number(o.final_total)-Number(s.final_total))>1e-6;});
const rankErrors=S.filter(s=>{const n=1+S.filter(t=>t.start===s.start&&t.fg_delay===s.fg_delay&&Number(t.final_total)>Number(s.final_total)+1e-7).length;return n!==Number(s.rank_in_current_12);});
const profiles=[...new Set(P.map(x=>x.profile))];
const byProfile=profiles.map(profile=>({profile,settings:['NORMAL_OFF','EXFEAR_OFF'].map(setting=>({setting,delays:[0,1].map(d=>{const a=P.filter(x=>x.profile===profile&&x.off_setting===setting&&Number(x.fg_delay)===d).map(x=>({start:x.start,delta_USD:Number(x.off_minus_on),on:Number(x.final_on),off:Number(x.final_off)}));return {delay:d,lower:a.filter(x=>x.delta_USD< -1e-7).length,equal:a.filter(x=>Math.abs(x.delta_USD)<=1e-7).length,higher:a.filter(x=>x.delta_USD>1e-7).length,min:Math.min(...a.map(x=>x.delta_USD)),max:Math.max(...a.map(x=>x.delta_USD)),rows:a};})}))}));
const groups=[...new Set(S.map(s=>s.start+'|'+s.fg_delay))].map(k=>{const [start,d]=k.split('|');const rows=S.filter(x=>x.start===start&&x.fg_delay===d);const max=Math.max(...rows.map(x=>Number(x.final_total)));return {start,delay:Number(d),winners:rows.filter(x=>Number(x.final_total)>=max-1e-7).map(x=>x.candidate_id),final_total:max};});
const result={source_commit:'e14efa847e45012058957dc7332e64ad58ab85f9',cells:S.length,paired:P.length,reuse_checked:72,paired_errors:pairedErrors.length,reuse_errors:reuseErrors.length,rank_errors:rankErrors.length,lower:P.filter(x=>Number(x.off_minus_on)< -1e-7).length,equal:P.filter(x=>Math.abs(Number(x.off_minus_on))<=1e-7).length,higher:P.filter(x=>Number(x.off_minus_on)>1e-7).length,byProfile,groups,hashChecks,verification:JSON.parse(fs.readFileSync(folder+'/verification.json','utf8')),environment:JSON.parse(fs.readFileSync(folder+'/environment.json','utf8'))};
fs.writeFileSync(new URL('./reproduction.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({cells:S.length,paired:P.length,paired_errors:pairedErrors.length,reuse_errors:reuseErrors.length,rank_errors:rankErrors.length,hash_matches:hashChecks.filter(x=>x.match).length,files:hashChecks.length}));
