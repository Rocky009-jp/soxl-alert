// node analyze.mjs   (Node >=22, stdlib only, no network). Runs the 24 fixed paths with the UNCHANGED 37a14c0 engine.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load, simulate, TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), base = path.join(here, '..');
const A = path.join(base, 'SOXL_allocation_separation_20261026');
const spec = JSON.parse(fs.readFileSync(path.join(here, 'specification.json'), 'utf8'));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const failures = [], checks = {};
const ok = (n, c, d) => { (checks[n] ??= {n: 0, fail: 0}).n++; if (!c) { checks[n].fail++; failures.push({check: n, detail: d}); } };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;
const pct = x => Math.round(x * 100);
const csv = rows => { const keys = [...new Set(rows.flatMap(Object.keys))]; const q = v => v == null ? '' : typeof v === 'string' ? '"' + v.replaceAll('"', '""') + '"' : String(v); return keys.join(',') + '\n' + rows.map(r => keys.map(k => q(r[k])).join(',')).join('\n') + '\n'; };
const parse = t => { const [h, ...r] = t.trim().split('\n').map(l => l.split(',')); return r.map(x => Object.fromEntries(h.map((k, i) => [k, (x[i] ?? '').replaceAll('"', '')]))); };

// ---- pinned references
const refs = {
  engine: sha(path.join(A, 'engine.mjs')), run: sha(path.join(A, 'run.mjs')), summary: sha(path.join(A, 'summary.csv')),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(path.join(base, 'SOXL_exit_study_20261023/data', f))])),
  specification: sha(path.join(here, 'specification.json')), analyze: sha(path.join(here, 'analyze.mjs')),
  reused_event_comparison_5f2593e: sha(path.join(base, 'daily_rule_analysis_20261026/event_comparison.csv'))
};
const env = JSON.parse(fs.readFileSync(path.join(A, 'environment.json'), 'utf8'));
ok('engine_sha_equals_37a14c0_environment', refs.engine === env.engine_sha256, refs.engine);
ok('run_sha_equals_37a14c0_environment', refs.run === env.run_sha256, refs.run);
for (const m of env.input_manifest) ok('input_sha_equals_manifest', refs.inputs[m.file] === m.sha256, m.file);
fs.writeFileSync(path.join(here, 'source_refs.json'), JSON.stringify({docs_start_sha: spec.docs_start_sha, fixed_study: '37a14c0', analysis_base: '5f2593e', ...refs}, null, 2));

const input = await load(path.join(base, 'SOXL_exit_study_20261023/data'));
const schedule = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const opts = {end: '2026-08-10', initial: 10000, allowInitialReentry: true, dividendSchedule: schedule, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0, exitMode: 'OR', profitTarget: .2, exitRsi: 75};
const rowByDate = new Map(input.rows.map((r, i) => [r.date, {...r, i}]));
const { starts, R: Rs, fg_delay: delays } = spec.paths;
const stored = parse(fs.readFileSync(path.join(A, 'summary.csv'), 'utf8'));

// ---- run 24 paths
const runs = [];
for (const start of starts) for (const delay of delays) for (const R of Rs) {
  const r = simulate(input.rows, {...opts, start, delay, reentry: .25, initialRatio: .25, reentryRatio: R});
  const id = `P20_OR_R75_I25_R${pct(R)}`;
  const last = r.daily.at(-1), sales = r.ledger.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const row = stored.find(s => s.candidate_id === id && s.start === start && s.fg_delay === String(delay));
  const mine = {final_total: last.total, liquidation: last.liquidation, final_shares: last.shares, final_cash: last.cash, final_market_value: last.market_value, final_basis: last.basis,
    realized_stock_gain: sales.reduce((a, t) => a + t.gain, 0), realized_stock_tax: sales.reduce((a, t) => a + t.tax, 0), sell_count: sales.length, blocked_sales: r.summary.blocked_sales,
    total_order_fees: r.ledger.reduce((a, t) => a + (t.fee ?? 0), 0), final_unrealized: last.unrealized,
    mmf_net_total: r.ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + last.mmf_accrued_gross * (1 - TAX),
    dividend_net_total: r.ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT').reduce((a, t) => a + t.net, 0)};
  const diffs = Object.fromEntries(Object.entries(mine).map(([k, v]) => [k, Math.abs(v - Number(row[k]))]));
  for (const [k, d] of Object.entries(diffs)) ok('path_vs_original_summary_1e-6', d <= 1e-6, `${id} ${start} d${delay} ${k} ${d}`);
  runs.push({start, delay, R, id, r, mine, maxdiff: Math.max(...Object.values(diffs)), stored: row});
}
ok('twentyfour_paths', runs.length === 24, String(runs.length));

// ---- label allocation class (INITIAL before any filled sale, AFTER_SALE after)
function label(ledger) {
  let sold = false;
  return ledger.map(t => {
    let cls = '';
    if (t.status === 'FILLED_DIAGNOSTIC' && t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND';
    else if (['NORMAL', 'EXFEAR'].includes(t.type)) cls = t.type;
    else if (t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND';
    else if (t.type === 'SELL') cls = 'SELL';
    const out = {...t, cls, sold_before: sold};
    if (t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC') sold = true;
    return out;
  });
}
const tradeTypes = new Set(['NORMAL', 'EXFEAR', 'REENTRY', 'SELL']);
const events = [];
for (const run of runs) {
  const led = label(run.r.ledger).filter(t => tradeTypes.has(t.type));
  run.events = led;
  led.forEach((t, k) => {
    const D = rowByDate.get(t.signal_date), prevCloseProfit = t.type === 'SELL' ? t.shares_before * D.close / t.basis_before - 1 : null;
    const exec = rowByDate.get(t.date);
    const rsiHit = t.type === 'SELL' ? D.rsi >= 75 : null, profHit = t.type === 'SELL' ? prevCloseProfit >= .2 : null;
    events.push({start: run.start, fg_delay: run.delay, R: run.R, path: run.id, D: t.signal_date, exec_date: t.date, order_type: t.type, allocation_class: t.cls, status: t.status,
      after_first_sale: t.sold_before, D_close: D.close, D_rsi: D.rsi, D_fg_used: D.fg, exec_open: exec.open,
      cash_before: t.cash_before, shares_before: t.shares_before, avg_cost_before: t.shares_before ? t.basis_before / t.shares_before : 0, basis_before: t.basis_before,
      shares: t.shares ?? 0, price: t.price ?? '', fee: t.fee ?? '', spend: t.type === 'SELL' ? '' : (t.cost ?? 0), cash_after: t.cash_after, shares_after: t.shares_after,
      basis_after: t.type === 'SELL' ? 0 : t.basis_before + (t.cost ?? 0),
      sell_D_gross_pct: prevCloseProfit ?? '', sell_profit20_hit: profHit ?? '', sell_rsi75_hit: rsiHit ?? '',
      sell_trigger: t.type === 'SELL' ? (profHit && rsiHit ? 'PROFIT20+RSI75' : profHit ? 'PROFIT20' : 'RSI75') : '',
      sell_open_realized_gross_pct: t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC' ? t.price * t.shares / t.basis_before - 1 : '',
      sell_gain: t.gain ?? '', sell_tax: t.tax ?? '', sell_fee: t.type === 'SELL' ? (t.fee ?? '') : '',
      zero_share_reason: t.status === 'INSUFFICIENT_INTEGER_SHARE' ? (t.cash_before < D.close ? 'cash below one share' : 'integer rounding') : ''});
  });
}
// every event happens at the next session after D
for (const e of events) { const d = rowByDate.get(e.D), x = rowByDate.get(e.exec_date); ok('exec_is_next_session_after_D', x.i === d.i + 1, `${e.path} ${e.D}`); }
fs.writeFileSync(path.join(here, 'event_comparison.csv'), csv(events));

// ---- 1. identical before first filled sale across R
for (const start of starts) for (const delay of delays) {
  const g = runs.filter(r => r.start === start && r.delay === delay);
  const cut = r => { const l = r.r.ledger, i = l.findIndex(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC'); return JSON.stringify((i < 0 ? l : l.slice(0, i + 1)).filter(t => t.type !== 'MMF_MONTHLY_PROXY').map(t => [t.date, t.type, t.status, t.shares, t.price, t.cash_after])); };
  ok('same_ledger_up_to_first_sale_across_R', new Set(g.map(cut)).size === 1, `${start} d${delay}`);
}

// ---- 2. aligned buys after the first sale: (start, delay, D, type) x R
const wide = new Map();
for (const e of events) {
  if (e.order_type === 'SELL' || !e.after_first_sale) continue;
  const key = [e.start, e.fg_delay, e.D, e.allocation_class].join('|');
  const w = wide.get(key) ?? {start: e.start, fg_delay: e.fg_delay, D: e.D, kind: e.allocation_class};
  const p = 'R' + pct(e.R) + '_';
  Object.assign(w, {[p + 'exec']: e.exec_date, [p + 'shares_before']: e.shares_before, [p + 'cash_before']: e.cash_before, [p + 'avg_cost_before']: e.avg_cost_before,
    [p + 'bought']: e.shares, [p + 'spend']: e.spend, [p + 'basis_after']: e.basis_after, [p + 'status']: e.status, [p + 'zero_reason']: e.zero_share_reason});
  wide.set(key, w);
}
const alignRows = [...wide.values()].sort((a, b) => a.start.localeCompare(b.start) || a.fg_delay - b.fg_delay || a.D.localeCompare(b.D));
for (const w of alignRows) w.present_in_R = ['R0', 'R25', 'R100'].filter(p => w[p + '_exec'] !== undefined).join('/');
fs.writeFileSync(path.join(here, 'buy_alignment.csv'), csv(alignRows));

// ---- 3. sale cycles: each filled sale, with the buys since previous sale and the wait to next purchase
const cycles = [];
for (const run of runs) {
  const led = run.events.filter(t => t.status === 'FILLED_DIAGNOSTIC' || t.type === 'SELL');
  const fills = run.events.filter(t => t.status === 'FILLED_DIAGNOSTIC');
  fills.forEach((t, k) => {
    if (t.type !== 'SELL') return;
    const prevSellIdx = fills.slice(0, k).map((x, i) => x.type === 'SELL' ? i : -1).filter(i => i >= 0).at(-1) ?? -1;
    const buys = fills.slice(prevSellIdx + 1, k);
    const nextBuy = fills.slice(k + 1).find(x => x.type !== 'SELL');
    const sIdx = rowByDate.get(t.date).i, endIdx = nextBuy ? rowByDate.get(nextBuy.date).i : rowByDate.get(opts.end).i;
    const D = rowByDate.get(t.signal_date), profHit = t.shares_before * D.close / t.basis_before - 1 >= .2, rsiHit = D.rsi >= 75;
    cycles.push({start: run.start, fg_delay: run.delay, R: run.R, sale_D: t.signal_date, sale_exec: t.date, trigger: profHit && rsiHit ? 'PROFIT20+RSI75' : profHit ? 'PROFIT20' : 'RSI75',
      D_gross_pct: t.shares_before * D.close / t.basis_before - 1, open_realized_gross_pct: t.price * t.shares / t.basis_before - 1,
      shares_sold: t.shares, avg_cost: t.basis_before / t.shares, sale_price: t.price, gain: t.gain, tax: t.tax, fee: t.fee, net_after_tax: t.gain - t.tax,
      buys_since_previous_sale: buys.map(b => `${b.signal_date}:${b.cls}:${b.shares}`).join(' '), spend_since_previous_sale: buys.reduce((a, b) => a + b.cost, 0),
      next_purchase_D: nextBuy?.signal_date ?? '', next_purchase_kind: nextBuy?.cls ?? '', wait_sessions_to_next_purchase_or_terminal: endIdx - sIdx, waited_to_terminal: !nextBuy});
  });
}
fs.writeFileSync(path.join(here, 'sale_cycles.csv'), csv(cycles));

// ---- 4. calendar concentration for the dates called out in the request
const interest = [['2026-02-09', 'AFTER_SALE_REENTRY'], ['2026-03-09', 'NORMAL'], ['2026-03-12', 'SELL'], ['2026-04-09', 'SELL'], ['2026-04-13', 'SELL']];
const cal = [];
for (const [d, kind] of interest) for (const delay of delays) {
  const hit = events.filter(e => e.exec_date === d && e.allocation_class === kind && e.fg_delay === delay && e.status === 'FILLED_DIAGNOSTIC');
  const starts_hit = [...new Set(hit.map(e => e.start))];
  cal.push({exec_date: d, kind, fg_delay: delay, paths_with_event: hit.length, starts_with_event: starts_hit.join(' '), start_count: starts_hit.length, by_R: [0, 25, 100].map(R => `R${R}:${hit.filter(e => pct(e.R) === R).map(e => e.start).join('/')}`).join(' '), unique_situations_D_kind: new Set(hit.map(e => e.D + '|' + kind)).size});
}
// same check keyed on the signal date D (the judgement day), which is what the unique-situation definition uses
const interestD = [['2026-02-06', 'AFTER_SALE_REENTRY'], ['2026-03-06', 'NORMAL'], ['2026-03-09', 'NORMAL'], ['2026-03-11', 'SELL'], ['2026-04-08', 'SELL'], ['2026-04-10', 'SELL'], ['2026-06-08', 'AFTER_SALE_REENTRY'], ['2026-06-10', 'NORMAL'], ['2026-06-26', 'NORMAL'], ['2026-06-26', 'EXFEAR'], ['2026-06-30', 'SELL'], ['2026-07-29', 'NORMAL'], ['2026-08-04', 'SELL']];
for (const [d, kind] of interestD) for (const delay of delays) {
  const hit = events.filter(e => e.D === d && e.allocation_class === kind && e.fg_delay === delay && e.status === 'FILLED_DIAGNOSTIC');
  const sh = [...new Set(hit.map(e => e.start))];
  cal.push({basis: 'signal_date_D', exec_date: d, kind, fg_delay: delay, paths_with_event: hit.length, starts_with_event: sh.join(' '), start_count: sh.length, by_R: [0, 25, 100].map(R => `R${R}:${hit.filter(e => pct(e.R) === R).length}`).join(' ')});
}
for (const c of cal) c.basis ??= 'exec_date';
fs.writeFileSync(path.join(here, 'calendar_concentration.csv'), csv(cal));

// ---- 5. unique market situations (D + kind), by delay, versus raw event count
const uniq = [];
for (const delay of delays) {
  const ev = events.filter(e => e.fg_delay === delay && (e.status === 'FILLED_DIAGNOSTIC' || e.order_type !== 'SELL'));
  const keys = new Map();
  for (const e of ev) { const k = e.D + '|' + e.allocation_class; (keys.get(k) ?? keys.set(k, []).get(k)).push(`${e.start}/R${pct(e.R)}`); }
  const after = ev.filter(e => e.after_first_sale);
  const akeys = new Set(after.map(e => e.D + '|' + e.allocation_class));
  uniq.push({fg_delay: delay, path_events_total: ev.length, unique_D_kind_total: keys.size, path_events_after_first_sale: after.length, unique_D_kind_after_first_sale: akeys.size,
    max_paths_sharing_one_situation: Math.max(...[...keys.values()].map(v => v.length))});
}
fs.writeFileSync(path.join(here, 'unique_situations.csv'), csv(uniq));
const uniqList = [];
for (const delay of delays) {
  const m = new Map();
  for (const e of events.filter(e => e.fg_delay === delay && e.after_first_sale)) { const k = e.D + '|' + e.allocation_class; (m.get(k) ?? m.set(k, []).get(k)).push(`${e.start}:R${pct(e.R)}`); }
  for (const [k, v] of [...m].sort()) uniqList.push({fg_delay: delay, D: k.split('|')[0], kind: k.split('|')[1], path_count: v.length, starts: [...new Set(v.map(x => x.split(':')[0]))].join(' '), paths: v.join(' ')});
}
fs.writeFileSync(path.join(here, 'unique_situations_after_first_sale.csv'), csv(uniqList));

// ---- 6. terminal reconciliation vs the R25 reference of the same start/delay
const rec = [];
for (const start of starts) for (const delay of delays) {
  const g = runs.filter(r => r.start === start && r.delay === delay), ref = g.find(r => r.R === .25), rl = ref.r.daily.at(-1);
  for (const run of g) {
    const l = run.r.daily.at(-1), ld = run.r.ledger;
    const mmf = x => x.r.ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + x.r.daily.at(-1).mmf_accrued_gross * (1 - TAX);
    const div = x => x.r.ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT').reduce((a, t) => a + t.net, 0);
    const rg = x => x.mine.realized_stock_gain - x.mine.realized_stock_tax;
    const d = {total: l.total - rl.total, cash_plus_stock_mv_plus_accrued: (l.cash + l.market_value + l.mmf_accrued_gross * (1 - TAX) + l.dividend_receivable_net) - (rl.cash + rl.market_value + rl.mmf_accrued_gross * (1 - TAX) + rl.dividend_receivable_net)};
    const byParts = (rg(run) - rg(ref)) + (mmf(run) - mmf(ref)) + (div(run) - div(ref)) + (l.unrealized - rl.unrealized);
    ok('reconcile_difference_to_R25_balance_sheet', near(d.total, d.cash_plus_stock_mv_plus_accrued), `${start} d${delay} R${run.R}`);
    ok('reconcile_difference_to_R25_flow_identity', near(d.total, byParts), `${start} d${delay} R${run.R}`);
    rec.push({start, fg_delay: delay, R: run.R, final_total: l.total, diff_vs_R25: d.total, d_cash: l.cash - rl.cash, d_stock_market_value: l.market_value - rl.market_value, d_accrued_and_receivable: (l.mmf_accrued_gross * (1 - TAX) + l.dividend_receivable_net) - (rl.mmf_accrued_gross * (1 - TAX) + rl.dividend_receivable_net),
      d_realized_gain_after_tax: rg(run) - rg(ref), d_mmf_net: mmf(run) - mmf(ref), d_dividend_net: div(run) - div(ref), d_unrealized: l.unrealized - rl.unrealized, sells: run.mine.sell_count, final_shares: l.shares});
  }
}
fs.writeFileSync(path.join(here, 'terminal_reconciliation.csv'), csv(rec));


// ---- 7. additive decomposition of the realized-net difference to R25 by sale-execution window (windows partition the sales; no double counting)
const windows = [['A_<=2025-12-31', d => d <= '2025-12-31'], ['B_2026-01..02', d => d >= '2026-01-01' && d <= '2026-02-28'], ['C_2026-03..04', d => d >= '2026-03-01' && d <= '2026-04-30'], ['D_>=2026-05', d => d >= '2026-05-01']];
const winRows = [];
for (const start of starts) for (const delay of delays) {
  const g = runs.filter(r => r.start === start && r.delay === delay), netBy = (r, f) => cycles.filter(c => c.start === start && c.fg_delay === delay && c.R === r.R && f(c.sale_exec)).reduce((a, c) => a + c.net_after_tax, 0);
  const ref = g.find(r => r.R === .25);
  for (const run of g) {
    const row = {start, fg_delay: delay, R: run.R};
    let sum = 0;
    for (const [name, f] of windows) { const d = netBy(run, f) - netBy(ref, f); row['d_net_' + name] = d; sum += d; }
    const recRow = rec.find(x => x.start === start && x.fg_delay === delay && x.R === run.R);
    row.sum_windows = sum; row.d_realized_net_total = recRow.d_realized_gain_after_tax; row.d_mmf_dividend_unrealized = recRow.d_mmf_net + recRow.d_dividend_net + recRow.d_unrealized; row.diff_vs_R25 = recRow.diff_vs_R25;
    ok('window_decomposition_sums_to_realized_net', near(sum, row.d_realized_net_total), `${start} d${delay} R${run.R}`);
    ok('window_decomposition_plus_mmf_equals_total', near(sum + row.d_mmf_dividend_unrealized, row.diff_vs_R25), `${start} d${delay} R${run.R}`);
    winRows.push(row);
  }
}
fs.writeFileSync(path.join(here, 'window_decomposition.csv'), csv(winRows));
// ---- 8. R100 buys that end at 0 or 1 share (0 = cannot afford one share / rounding; never produced by missing data)
const smallBuys = events.filter(e => ['NORMAL', 'EXFEAR'].includes(e.order_type) && e.after_first_sale).map(e => ({start: e.start, fg_delay: e.fg_delay, R: e.R, D: e.D, kind: e.order_type, shares: e.shares, status: e.status, cash_before: e.cash_before, spend: e.spend})).filter(e => e.shares <= 1);
fs.writeFileSync(path.join(here, 'small_buys_after_first_sale.csv'), csv(smallBuys));

// ---- 9. first divergence from the R25 reference (first event whose signal date / type / shares differ)
const div = [];
for (const start of starts) for (const delay of delays) {
  const g = runs.filter(r => r.start === start && r.delay === delay), ref = g.find(r => r.R === .25);
  const seq = r => r.events.filter(t => t.status === 'FILLED_DIAGNOSTIC').map(t => [t.signal_date, t.cls, t.shares]);
  for (const run of g.filter(r => r.R !== .25)) {
    const a = seq(ref), b = seq(run); let i = 0;
    while (i < Math.min(a.length, b.length) && a[i].join() === b[i].join()) i++;
    div.push({start, fg_delay: delay, R: run.R, identical_events_before_divergence: i, ref_next_event: (a[i] ?? []).join(' '), this_next_event: (b[i] ?? []).join(' ')});
  }
}
fs.writeFileSync(path.join(here, 'first_divergence.csv'), csv(div));

// ---- path check table + verification
fs.writeFileSync(path.join(here, 'paths_check.csv'), csv(runs.map(r => ({start: r.start, fg_delay: r.delay, R: r.R, path: r.id, final_total: r.mine.final_total, stored_final_total: Number(r.stored.final_total), max_abs_diff_14_items_USD: r.maxdiff, sells: r.mine.sell_count, blocked_sales: r.mine.blocked_sales, orig_rank_in_start_delay: r.stored.rank_in_start_delay, pass: r.maxdiff <= 1e-6}))));
// reused main-start rows: only a count, nothing re-run
const reused = parse(fs.readFileSync(path.join(base, 'daily_rule_analysis_20261026/event_comparison.csv'), 'utf8').split('\n').map(l => l.replace(/"/g, '')).join('\n')).length;
fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({passed_all: failures.length === 0, failure_count: failures.length, failures: failures.slice(0, 30), counts: {new_paths: 24, original_252_rerun: 0, summary_items_compared_per_path: 14, tolerance_USD: 1e-6, events_rows: events.length, reused_5f2593e_event_rows_not_rerun: reused}, checks}, null, 2));
fs.writeFileSync(path.join(here, 'environment.json'), JSON.stringify({node: process.version, platform: process.platform, command: 'cd research/reentry_mechanism_20261026 && node analyze.mjs', network: 'not used', secrets: 'none'}, null, 2));
console.log(JSON.stringify({passed_all: failures.length === 0, failures: failures.slice(0, 10), events: events.length, align: alignRows.length, cycles: cycles.length, uniq, checks: Object.fromEntries(Object.entries(checks).map(([k, v]) => [k, `${v.n}/${v.fail}`]))}, null, 1));
if (failures.length) process.exit(1);
