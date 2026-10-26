// node make_tables.mjs  -> tables.md (read-only derivation from summary.csv / month_end_summary.csv)
import fs from 'node:fs';
const p=f=>{const [h,...r]=fs.readFileSync(f,'utf8').trim().split('\n').map(l=>l.split(','));return r.map(x=>Object.fromEntries(h.map((k,i)=>[k,x[i].replaceAll('"','')])))};
const S=p('summary.csv'),M=p('month_end_summary.csv');
const starts=['2024-10-01','2025-01-02','2025-04-01','2025-07-01','2025-10-01','2026-01-02'];
const n0=x=>Number(x).toLocaleString('en-US',{maximumFractionDigits:0});
const get=(id,st,d)=>S.find(s=>s.candidate_id===id&&s.start===st&&s.fg_delay===String(d));
const out=[];
const P=s=>out.push(s);
P('# 派生表（make_tables.mjs が summary.csv / month_end_summary.csv から機械生成）\n');
P('金額は元本10,000USDを含む2026-08-10の最終時価総資産（USD）。診断モデルの数値で、楽天で取引可能な成績ではない。\n');
for(const d of [0,1]){
  P(`## F&G遅延${d}：主終端の順位（21候補）\n`);
  P('| 開始 | 1位 | 2位 | 3位 | 売却あり最良 | 基準 P20_OR_R75 I25/R25（順位） | NO_SELL I0 / I25 / I100 |\n|---|---|---|---|---|---|---|');
  for(const st of starts){
    const g=S.filter(s=>s.start===st&&s.fg_delay===String(d)).sort((a,b)=>b.final_total-a.final_total);
    const bs=g.filter(s=>s.exit_id!=='NO_SELL')[0],b=get('P20_OR_R75_I25_R25',st,d);
    const f=s=>`${s.candidate_id} ${n0(s.final_total)}`;
    P(`| ${st} | ${f(g[0])} | ${f(g[1])} | ${f(g[2])} | ${f(bs)} | ${n0(b.final_total)}（${b.rank_in_start_delay}） | ${[0,25,100].map(I=>n0(get('NO_SELL_I'+I,st,d).final_total)).join(' / ')} |`);
  }
  P('');
}
for(const d of [0,1])for(const st of starts){
  P(`## 配分格子 開始${st} 遅延${d}（最終総資産、[売却数/初回参加買い/売却後再エントリー買い]）\n`);
  P('| 出口 | I＼R | R=0 | R=25% | R=100% |\n|---|---|---:|---:|---:|');
  for(const ex of ['P20_OR_R75','P20_ONLY'])for(const I of [0,25,100]){
    P(`| ${ex} | I=${I}% | `+[0,25,100].map(R=>{const s=get(`${ex}_I${I}_R${R}`,st,d);return `${n0(s.final_total)} [${s.sell_count}/${s.initial_trend_count}/${s.after_sale_reentry_count}]`}).join(' | ')+' |');
  }
  P(`| NO_SELL | I=0/25/100% | ${[0,25,100].map(I=>n0(get('NO_SELL_I'+I,st,d).final_total)).join(' / ')}（Rは作用せず） | | |`);
  P('');
}
P('## 配分効果の分解（P20_OR_R75、遅延0、主終端）\n');
P('基準 I25/R25 からの差額（USD）。ΔI＝I0に変えた差、ΔR＝Rだけ変えた差。\n');
P('| 開始 | 基準 | I0/R25−基準 | I100/R25−基準 | I25/R0−基準 | I25/R100−基準 | 初回参加が実際に起きたか（I25での初回参加買い数） |\n|---|---:|---:|---:|---:|---:|---|');
for(const st of starts){const b=get('P20_OR_R75_I25_R25',st,0),dl=id=>{const v=get(id,st,0).final_total-b.final_total;return (v>=0?'+':'')+n0(v)};
  P(`| ${st} | ${n0(b.final_total)} | ${dl('P20_OR_R75_I0_R25')} | ${dl('P20_OR_R75_I100_R25')} | ${dl('P20_OR_R75_I25_R0')} | ${dl('P20_OR_R75_I25_R100')} | ${b.initial_trend_count} |`);}
P('');
for(const d of [0]){
  for(const st of starts){
    P(`## 月末感度 開始${st} 遅延${d}（月末proxy日の総資産）\n`);
    P('| 月 | proxy日 | 全体1位 | 売却あり最良 | 基準 | NO_SELL I0 | NO_SELL I25 | NO_SELL I100 |\n|---|---|---|---|---:|---:|---:|---:|');
    const months=[...new Set(M.filter(m=>m.start===st&&m.fg_delay===String(d)).map(m=>m.month))];
    for(const mo of months){const g=M.filter(m=>m.start===st&&m.fg_delay===String(d)&&m.month===mo).sort((a,b)=>b.final_total-a.final_total);
      const bs=g.filter(x=>x.exit_id!=='NO_SELL')[0],gt=id=>n0(g.find(x=>x.candidate_id===id).final_total);
      P(`| ${mo} | ${g[0].month_end_proxy_date} | ${g[0].candidate_id} ${n0(g[0].final_total)} | ${bs.candidate_id} ${n0(bs.final_total)} | ${gt('P20_OR_R75_I25_R25')} | ${gt('NO_SELL_I0')} | ${gt('NO_SELL_I25')} | ${gt('NO_SELL_I100')} |`);}
    P('');
  }
}
fs.writeFileSync('tables.md',out.join('\n'));
