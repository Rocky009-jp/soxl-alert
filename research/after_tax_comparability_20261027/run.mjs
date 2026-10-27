// node run.mjs   (Node >=22, stdlib only, no network)
// 48 evaluation cells = 6 candidates x 2 starts x 2 FG delays x {NEXT_OPEN, NEXT_CLOSE}.
// simulate() budget: 24 Open re-simulations (compared with the stored 77bb44f values) + 24 Close = 48 calls. Engine and inputs unchanged.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load, simulate as rawSimulate, signals, sellCosts, commission, TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), base = path.join(here, '..');
const A = path.join(base, 'SOXL_allocation_separation_20261026'), X = path.join(base, 'SOXL_exit_study_20261023'), P = path.join(base, 'profit_target_isolated_20261026');
const spec = JSON.parse(fs.readFileSync(path.join(here, 'specification.json'), 'utf8'));
const refs0 = JSON.parse(fs.readFileSync(path.join(here, 'source_refs.json'), 'utf8'));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const failures = [], checks = {};
const ok = (n, c, d) => { (checks[n] ??= {n: 0, fail: 0}).n++; if (!c) { checks[n].fail++; failures.push({check: n, detail: d}); } };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;
const q = v => v == null ? '' : typeof v === 'string' ? '"' + v.replaceAll('"', '""') + '"' : String(v);
const csv = rows => { const keys = [...new Set(rows.flatMap(Object.keys))]; return keys.join(',') + '\n' + rows.map(r => keys.map(k => q(r[k])).join(',')).join('\n') + '\n'; };
const parse = t => { const lines = t.trim().split(/\r?\n/); const split = l => { const o = []; let f = '', inq = false; for (let i = 0; i < l.length; i++) { const c = l[i]; if (inq) { if (c === '"') { if (l[i + 1] === '"') { f += '"'; i++; } else inq = false; } else f += c; } else if (c === '"') inq = true; else if (c === ',') { o.push(f); f = ''; } else f += c; } o.push(f); return o; }; const h = split(lines[0]); return lines.slice(1).map(l => { const x = split(l); return Object.fromEntries(h.map((k, i) => [k, x[i]])); }); };

// ---- simulate call counter (budget 48)
let simCalls = 0;
const simulate = (rows, opts) => { simCalls++; return rawSimulate(rows, opts); };

// ---- pinned references
const refs = {engine: sha(path.join(A, 'engine.mjs')), dividends: sha(path.join(A, 'dividends_verified.json')), stored_summary_77bb44f: sha(path.join(P, 'summary.csv')),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(path.join(X, 'data', f))])), specification: sha(path.join(here, 'specification.json')), run_this: sha(path.join(here, 'run.mjs'))};
ok('engine_sha_equals_source_refs', refs.engine === refs0.engine, refs.engine);
ok('dividends_sha_equals_source_refs', refs.dividends === refs0.dividends, refs.dividends);
ok('stored_summary_sha_equals_source_refs', refs.stored_summary_77bb44f === refs0.stored_summary_77bb44f, refs.stored_summary_77bb44f);
ok('specification_sha_equals_source_refs', refs.specification === refs0.specification, refs.specification);
for (const f of Object.keys(refs.inputs)) ok('input_sha_equals_source_refs', refs.inputs[f] === refs0.inputs[f], f);
const engineText = fs.readFileSync(path.join(A, 'engine.mjs'), 'utf8');
const simText = engineText.slice(engineText.indexOf('export function simulate')); // load() also reads r.open, but only for OHLC presence/validity of the ORIGINAL rows
const openUses = [...simText.matchAll(/\br\.open\b/g)].length;
ok('engine_open_uses_exactly_expected', openUses === 3, 'count ' + openUses); // assert(r.open!==undefined...), sell price, buy price
ok('engine_open_use_sites', /assert\(r\.open!==undefined&&r\.close!==undefined/.test(engineText) && /const p=r\.open\*\(1-cfg\.slippage\)/.test(engineText) && /const p=r\.open\*\(1\+cfg\.slippage\)/.test(engineText), 'sites');

// ---- inputs, original rows and the NEXT_CLOSE research copy (only 'open' is replaced by the same-day original close)
const input = await load(path.join(X, 'data'));
const schedule = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const origRows = input.rows, rowBy = new Map(origRows.map(r => [r.date, r]));
const origJson0 = JSON.stringify(origRows);
const closeRows = origRows.map(r => r.open !== undefined ? {...r, open: r.close} : r);
const strip = o => { const {open, ...rest} = o; return rest; };
ok('close_copy_same_length_and_dates', closeRows.length === origRows.length && closeRows.every((r, i) => r.date === origRows[i].date), '');
ok('close_copy_open_equals_original_close_on_ohlc_rows', closeRows.every((r, i) => origRows[i].open === undefined ? r.open === undefined : r.open === origRows[i].close), '');
ok('close_copy_non_open_fields_identical', closeRows.every((r, i) => JSON.stringify(strip(r)) === JSON.stringify(strip(origRows[i]))), '');
const openDiffersFromClose = origRows.filter(r => r.date >= '2024-10-01' && r.date <= '2026-08-10' && r.open !== undefined && r.open !== r.close).length;
for (const d of [0, 1]) {
  const s0 = signals(origRows, {delay: d}).map(strip), s1 = signals(closeRows, {delay: d}).map(strip);
  ok('signals_identical_before_after_close_transform', JSON.stringify(s0) === JSON.stringify(s1), 'delay ' + d);
}

// ---- candidates (same option mapping as 77bb44f run.mjs)
const EXITS = {P20_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .2, exitRsi: 75}, P20_OR_R75: {exitMode: 'OR', profitTarget: .2, exitRsi: 75}, NO_SELL: {exitMode: 'NONE', profitTarget: .2, exitRsi: 75}};
const CANDS = [
  {id: 'NO_SELL_I0', exit: 'NO_SELL', I: 0, R: null}, {id: 'NO_SELL_I25', exit: 'NO_SELL', I: .25, R: null}, {id: 'NO_SELL_I100', exit: 'NO_SELL', I: 1, R: null},
  {id: 'P20_ONLY_I25_R25', exit: 'P20_ONLY', I: .25, R: .25}, {id: 'P20_ONLY_I25_R100', exit: 'P20_ONLY', I: .25, R: 1}, {id: 'P20_OR_R75_I25_R25', exit: 'P20_OR_R75', I: .25, R: .25}];
ok('six_candidates', CANDS.length === 6, '');
const baseOpts = {end: '2026-08-10', initial: 10000, allowInitialReentry: true, dividendSchedule: schedule, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0};
const STARTS = spec.cells_48.starts, DELAYS = spec.cells_48.fg_delay, EXECS = spec.cells_48.execution, END = spec.cells_48.terminal;
const runCell = (c, start, delay, exec) => {
  const e = EXITS[c.exit];
  return simulate(exec === 'NEXT_CLOSE' ? closeRows : origRows, {...baseOpts, start, delay, ...e, reentry: c.I, initialRatio: c.I, reentryRatio: c.R ?? c.I});
};

function label(ledger) {
  let sold = false;
  return ledger.map(t => { let cls = ''; if (t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND'; else if (['NORMAL', 'EXFEAR', 'SELL'].includes(t.type)) cls = t.type; const o = {...t, cls}; if (t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC') sold = true; return o; });
}
function analyze(r, c, delay, exec) {
  const ledger = label(r.ledger), daily = r.daily, p = daily.at(-1), tag = `${c.id}|${r.cfg.start}|d${delay}|${exec}`;
  const sales = ledger.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const fills = ledger.filter(t => t.status === 'FILLED_DIAGNOSTIC' && ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type));
  const buys = fills.filter(t => t.type !== 'SELL');
  const mmfNet = ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + p.mmf_accrued_gross * (1 - TAX);
  const ent = ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT'), pay = ledger.filter(t => t.type === 'DIVIDEND_PAYMENT_DATE_PROXY');
  const divNet = ent.reduce((a, t) => a + t.net, 0), gain = sales.reduce((a, t) => a + t.gain, 0), tax = sales.reduce((a, t) => a + t.tax, 0);
  const orderFees = ledger.reduce((a, t) => a + (t.fee ?? 0), 0);
  const liqCost = p.shares ? sellCosts(p.shares, p.close, p.date) : 0, liqTax = p.shares ? Math.max(0, p.shares * p.close - liqCost - p.basis) * TAX : 0;
  ok('accounting_identity_total', near(r.cfg.initial + gain - tax + mmfNet + divNet + p.unrealized, p.total), tag);
  ok('terminal_liquidation_identity_total_minus_cost_minus_tax', near(p.liquidation, p.total - liqCost - liqTax), tag);
  ok('terminal_date_2026-08-10', p.date === END, tag);
  ok('fresh_account_at_start', daily[0].date >= r.cfg.start && daily[0].cash === 10000 && daily[0].shares === 0 && ledger.every(t => t.date >= r.cfg.start), tag);
  ok('start_date_exactly_requested', daily[0].date === r.cfg.start, tag + ' ' + daily[0].date);
  ok('balance_invariants_nonneg_cash_integer_shares_zero_basis', daily.every(d => d.cash >= -1e-7 && Number.isInteger(d.shares) && d.shares >= 0 && (d.shares > 0 || d.basis === 0) && d.basis >= -1e-7), tag);
  ok('every_sale_net_gain_ge_2pct_of_cost', sales.every(t => t.gain >= t.basis * .02 - 1e-7), tag);
  ok('dividend_no_double_counting', near(divNet, pay.reduce((a, t) => a + t.net, 0) + p.dividend_receivable_net, 1e-9) && new Set(pay.map(t => t.ex_date)).size === pay.length && new Set(ent.map(t => t.pay_date)).size === ent.length, tag);
  if (c.exit === 'NO_SELL') ok('no_sell_zero_sales_zero_aftersale', sales.length === 0 && !ledger.some(t => t.cls === 'AFTER_SALE_REENTRY'), tag);
  if (c.I === 0) ok('I0_no_initial_trend_buy', !ledger.some(t => t.cls === 'INITIAL_TREND' && t.status === 'FILLED_DIAGNOSTIC'), tag);
  // fill price equals the original Open (NEXT_OPEN) or original Close (NEXT_CLOSE) of the execution date; exec date is after the signal date D
  for (const t of fills) {
    const o = rowBy.get(t.date), want = exec === 'NEXT_CLOSE' ? o.close : o.open;
    ok('fill_price_equals_original_open_or_close_of_exec_date', t.price === want, `${tag} ${t.date} ${t.price} vs ${want}`);
    ok('exec_date_after_signal_date', t.signal_date < t.date, `${tag} ${t.date}`);
    ok('engine_internal_phase_label_is_daily_open_proxy_for_both', t.execution_phase === 'daily_open_proxy', tag);
  }
  for (const t of sales) { const D = rowBy.get(t.signal_date); const gp = t.shares_before * D.close / t.basis_before - 1; ok('sale_signal_gross_on_cost_at_least_target_on_original_D_close', c.exit === 'NO_SELL' || c.exit === 'P20_OR_R75' || gp >= EXITS[c.exit].profitTarget - 1e-12, tag + ' ' + t.signal_date); }
  const ret = x => x / r.cfg.initial - 1;
  return {summary: {candidate_id: c.id, exit_id: c.exit, I_initial: c.I, R_after_sale: c.R, start: r.cfg.start, fg_delay: delay, evaluation_execution: exec, engine_internal_phase: 'daily_open_proxy (engine label; NOT the real fill time for NEXT_CLOSE)',
    liquidation_after_tax_same_day: p.liquidation, final_total_market_value_incl_realized_taxes: p.total, liquidation_roi_vs_10000: ret(p.liquidation), total_roi_vs_10000: ret(p.total),
    terminal_liq_sale_cost: liqCost, terminal_liq_tax_on_unrealized: liqTax, realized_stock_gain: gain, realized_stock_tax: tax, mmf_net_total_after_tax: mmfNet, dividend_net_total_after_tax: divNet, total_order_fees: orderFees,
    final_shares: p.shares, final_cash: p.cash, final_market_value_stock: p.market_value, final_basis: p.basis, final_unrealized: p.unrealized, final_dividend_receivable: p.dividend_receivable_net,
    buy_count: buys.length, sell_count: sales.length, blocked_sales: r.summary.blocked_sales, initial_trend_count: ledger.filter(t => t.cls === 'INITIAL_TREND' && t.status === 'FILLED_DIAGNOSTIC').length, after_sale_reentry_count: ledger.filter(t => t.cls === 'AFTER_SALE_REENTRY' && t.status === 'FILLED_DIAGNOSTIC').length,
    first_buy_date: buys[0]?.date ?? '', first_sale_date: sales[0]?.date ?? '', last_fill_date: fills.at(-1)?.date ?? ''}, ledger, daily};
}

// ---- stored 77bb44f values (Open reference)
const stored = new Map(parse(fs.readFileSync(path.join(P, 'summary.csv'), 'utf8')).map(s => [`${s.candidate_id}|${s.start}|${s.fg_delay}`, s]));
const STORED_NUM = {final_total: 'final_total_market_value_incl_realized_taxes', liquidation: 'liquidation_after_tax_same_day', final_shares: 'final_shares', final_cash: 'final_cash', final_market_value: 'final_market_value_stock', final_basis: 'final_basis', final_unrealized: 'final_unrealized',
  mmf_net_total: 'mmf_net_total_after_tax', dividend_net_total: 'dividend_net_total_after_tax', realized_stock_gain: 'realized_stock_gain', realized_stock_tax: 'realized_stock_tax', total_order_fees: 'total_order_fees', buy_count: 'buy_count', sell_count: 'sell_count', blocked_sales: 'blocked_sales',
  initial_trend_count: 'initial_trend_count', after_sale_reentry_count: 'after_sale_reentry_count'};

// ---- 48 cells
const cells = [], sim = new Map();
for (const start of STARTS) for (const delay of DELAYS) for (const exec of EXECS) for (const c of CANDS) {
  const r = runCell(c, start, delay, exec), a = analyze(r, c, delay, exec), tag = `${c.id}|${start}|${delay}`;
  sim.set(`${tag}|${exec}`, {r, a});
  const row = {...a.summary};
  if (exec === 'NEXT_OPEN') {
    const st = stored.get(tag); ok('stored_77bb44f_open_cell_exists', !!st, tag);
    let worst = 0;
    for (const [k, mine] of Object.entries(STORED_NUM)) { const d = Math.abs(Number(st[k]) - Number(a.summary[mine])); worst = Math.max(worst, d); ok('open_cell_equals_stored_77bb44f_value_1e-6', d <= 1e-6, `${tag} ${k} ${d}`); }
    ok('open_cell_first_buy_first_sale_dates_equal_stored', st.first_buy_date === a.summary.first_buy_date && st.first_sale_date === a.summary.first_sale_date, tag);
    row.source = 'stored_77bb44f_reused_and_resimulated_for_ledger'; row.stored_77bb44f_final_total = Number(st.final_total); row.stored_77bb44f_liquidation = Number(st.liquidation); row.max_abs_diff_vs_stored_USD = worst;
  } else { row.source = 'new_close_cell'; row.stored_77bb44f_final_total = ''; row.stored_77bb44f_liquidation = ''; row.max_abs_diff_vs_stored_USD = ''; }
  cells.push(row);
}
ok('cells_48', cells.length === 48, String(cells.length));
ok('open_24_close_24', cells.filter(c => c.evaluation_execution === 'NEXT_OPEN').length === 24 && cells.filter(c => c.evaluation_execution === 'NEXT_CLOSE').length === 24, '');
ok('simulate_calls_equal_48_budget', simCalls === 48, String(simCalls));
// the market signal tape returned by simulate must be identical (except open) between Open and Close for the same cell
for (const start of STARTS) for (const delay of DELAYS) for (const c of CANDS) {
  const o = sim.get(`${c.id}|${start}|${delay}|NEXT_OPEN`).r.signals.map(strip), k = sim.get(`${c.id}|${start}|${delay}|NEXT_CLOSE`).r.signals.map(strip);
  ok('simulate_signal_tape_identical_open_vs_close', JSON.stringify(o) === JSON.stringify(k), `${c.id} ${start} d${delay}`);
}
ok('original_rows_not_mutated_after_all_runs', JSON.stringify(origRows) === origJson0, '');
fs.writeFileSync(path.join(here, 'summary.csv'), csv(cells));

// ---- paired effects: Close - Open for the same candidate / start / delay (24 rows). No summing across starts.
const paired = [];
const FIELDS = ['liquidation_after_tax_same_day', 'final_total_market_value_incl_realized_taxes', 'realized_stock_gain', 'realized_stock_tax', 'mmf_net_total_after_tax', 'dividend_net_total_after_tax', 'total_order_fees', 'terminal_liq_sale_cost', 'terminal_liq_tax_on_unrealized', 'final_shares', 'final_basis', 'final_cash', 'buy_count', 'sell_count'];
for (const start of STARTS) for (const delay of DELAYS) for (const c of CANDS) {
  const o = cells.find(x => x.candidate_id === c.id && x.start === start && x.fg_delay === delay && x.evaluation_execution === 'NEXT_OPEN');
  const k = cells.find(x => x.candidate_id === c.id && x.start === start && x.fg_delay === delay && x.evaluation_execution === 'NEXT_CLOSE');
  const row = {candidate_id: c.id, start, fg_delay: delay, open_liquidation: o.liquidation_after_tax_same_day, close_liquidation: k.liquidation_after_tax_same_day};
  for (const f of FIELDS) row['delta_close_minus_open__' + f] = k[f] - o[f];
  row.delta_liquidation_roi_pp = (k.liquidation_roi_vs_10000 - o.liquidation_roi_vs_10000) * 100;
  row.delta_liquidation_pct_of_open = (k.liquidation_after_tax_same_day / o.liquidation_after_tax_same_day - 1) * 100;
  row.open_sell_count = o.sell_count; row.close_sell_count = k.sell_count; row.open_first_sale = o.first_sale_date; row.close_first_sale = k.first_sale_date;
  paired.push(row);
}
ok('paired_24', paired.length === 24, String(paired.length));
fs.writeFileSync(path.join(here, 'paired_execution_effects.csv'), csv(paired));

// ---- explanation ledger: 12 paths = 2 starts x delay 0 x 3 candidates x {Open, Close}
const EXPL = ['NO_SELL_I25', 'P20_ONLY_I25_R25', 'P20_OR_R75_I25_R25'];
const sigTapes = new Map(DELAYS.map(d => [d, new Map(signals(origRows, {delay: d}).map(s => [s.date, s]))]));
for (const d of DELAYS) { let allOk = true, differs = 0; for (const [i, r] of origRows.entries()) { const s = sigTapes.get(d).get(r.date), prev = i >= d ? origRows[i - d].fg : null; if (s.fg_used !== prev) allOk = false; if (d === 1 && s.fg_used !== r.fg) differs++; } ok('signals_fg_used_equals_row_i_minus_delay', allOk, 'delay ' + d); if (d === 1) ok('delay1_fg_used_differs_from_raw_D_fg_on_some_rows', differs > 100, String(differs)); }
const events = [], pathEvents = new Map();
for (const start of STARTS) for (const cid of EXPL) for (const exec of EXECS) {
  const a = sim.get(`${cid}|${start}|0|${exec}`).a, c = CANDS.find(x => x.id === cid);
  const rows = [];
  let seq = 0;
  for (const t of a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type))) {
    const D = rowBy.get(t.signal_date), sg = sigTapes.get(0).get(t.signal_date), X0 = rowBy.get(t.date), isSell = t.type === 'SELL', filled = t.status === 'FILLED_DIAGNOSTIC';
    const fill = exec === 'NEXT_CLOSE' ? X0.close : X0.open;
    const frac = t.cls === 'INITIAL_TREND' ? c.I : t.cls === 'AFTER_SALE_REENTRY' ? (c.R ?? c.I) : 1, budget = isSell ? '' : t.cash_before * frac;
    let reason = ''; if (!isSell && !filled) reason = budget < fill + commission(fill) ? 'allocation budget below one share + fee at the exec fill price' : 'integer rounding';
    rows.push({start, fg_delay: 0, candidate_id: cid, evaluation_execution: exec, seq: ++seq, D: t.signal_date, exec_date: t.date, order_type: t.type, allocation_class: t.cls,
      row_kind: filled ? 'FILLED' : isSell ? 'SELL_GATE_BLOCKED' : 'INSUFFICIENT_INTEGER_SHARE', D_fg_used: sg.fg_used, D_close: D.close, D_rsi: D.rsi, exec_original_open: X0.open, exec_original_close: X0.close, fill_price_used: fill,
      shares_before: t.shares_before, cash_before: t.cash_before, basis_before: t.basis_before, allocation_budget: budget, shares: t.shares ?? 0, fee: t.fee ?? '',
      D_gross_profit_on_cost_pct: isSell ? (t.shares_before * D.close / t.basis_before - 1) * 100 : '', fill_gross_profit_on_cost_pct: isSell && filled ? (t.price * t.shares / t.basis_before - 1) * 100 : '', sell_gain_pre_tax: t.gain ?? '', sell_tax: t.tax ?? '', zero_share_reason: reason});
  }
  pathEvents.set(`${start}|${cid}|${exec}`, rows); events.push(...rows);
}
// first divergence per (start, candidate) pair
const divergence = [];
for (const start of STARTS) for (const cid of EXPL) {
  const o = pathEvents.get(`${start}|${cid}|NEXT_OPEN`), k = pathEvents.get(`${start}|${cid}|NEXT_CLOSE`), n = Math.max(o.length, k.length);
  let first = null;
  for (let i = 0; i < n; i++) { const a = o[i], b = k[i]; if (!a || !b || a.D !== b.D || a.order_type !== b.order_type || a.row_kind !== b.row_kind || a.shares !== b.shares || a.exec_date !== b.exec_date) { first = i; break; } }
  const sameOrderPrice = []; for (let i = 0; i < Math.min(o.length, k.length) && (first === null || i < first); i++) sameOrderPrice.push(o[i].fill_price_used - k[i].fill_price_used);
  const d0 = sim.get(`${cid}|${start}|0|NEXT_OPEN`).a.daily, d1 = sim.get(`${cid}|${start}|0|NEXT_CLOSE`).a.daily;
  let maxGap = {abs: 0}; for (let i = 0; i < d0.length; i++) { const g = d1[i].total - d0[i].total; if (Math.abs(g) > maxGap.abs) maxGap = {abs: Math.abs(g), date: d0[i].date, gap: g}; }
  divergence.push({start, candidate_id: cid, open_events: o.length, close_events: k.length, first_divergent_seq: first === null ? '' : first + 1,
    first_divergent_open: first === null || !o[first] ? '' : `${o[first].D}>${o[first].exec_date} ${o[first].order_type} ${o[first].row_kind} sh=${o[first].shares} @${o[first].fill_price_used}`,
    first_divergent_close: first === null || !k[first] ? '' : `${k[first].D}>${k[first].exec_date} ${k[first].order_type} ${k[first].row_kind} sh=${k[first].shares} @${k[first].fill_price_used}`,
    identical_order_sequence_before_divergence: first === null ? o.length : first, max_abs_total_gap_date: maxGap.date, max_total_gap_close_minus_open: maxGap.gap ?? 0, terminal_liq_gap_close_minus_open: cells.find(x => x.candidate_id === cid && x.start === start && x.fg_delay === 0 && x.evaluation_execution === 'NEXT_CLOSE').liquidation_after_tax_same_day - cells.find(x => x.candidate_id === cid && x.start === start && x.fg_delay === 0 && x.evaluation_execution === 'NEXT_OPEN').liquidation_after_tax_same_day});
}
fs.writeFileSync(path.join(here, 'ledger_12paths.csv'), csv(events));
fs.writeFileSync(path.join(here, 'first_divergence.csv'), csv(divergence));
ok('twelve_explained_paths', pathEvents.size === 12, String(pathEvents.size));

// ---- month-end gap (Close - Open total) for the 6 explained pairs (proxy: last saved record per month)
const months = []; for (let y = 2024, m = 10; !(y === 2026 && m === 9);) { months.push(`${y}-${String(m).padStart(2, '0')}`); if (++m > 12) { m = 1; y++; } }
const tapeLast = new Map(); for (const r of origRows) { const mo = r.date.slice(0, 7); if (r.date <= END && (!tapeLast.has(mo) || r.date > tapeLast.get(mo))) tapeLast.set(mo, r.date); }
const gaps = [];
for (const start of STARTS) for (const cid of EXPL) for (const month of months) {
  const d0 = sim.get(`${cid}|${start}|0|NEXT_OPEN`).a.daily.filter(x => x.date.startsWith(month)).at(-1), d1 = sim.get(`${cid}|${start}|0|NEXT_CLOSE`).a.daily.filter(x => x.date.startsWith(month)).at(-1);
  if (!d0 || !d1) continue;
  ok('month_end_record_equals_tape_last_date', d0.date === tapeLast.get(month) && d1.date === d0.date, `${cid} ${start} ${month}`);
  gaps.push({start, candidate_id: cid, month, month_end_proxy_date: d0.date, open_total: d0.total, close_total: d1.total, gap_close_minus_open: d1.total - d0.total, open_shares: d0.shares, close_shares: d1.shares, open_liquidation: d0.liquidation, close_liquidation: d1.liquidation});
}
fs.writeFileSync(path.join(here, 'month_end_gap_6pairs.csv'), csv(gaps));

// ---- tables for the report
const L = (c, s, d, e) => cells.find(x => x.candidate_id === c && x.start === s && x.fg_delay === d && x.evaluation_execution === e);
let md = '# Tables (generated by run.mjs)\n\nUSD, principal 10,000 included. liq = same-day after-tax liquidation; mv = market value (realized-gain, MMF and dividend taxes already deducted; tax on unrealized gains and sale costs at 2026-08-10 not yet deducted).\n\n';
for (const start of STARTS) for (const delay of DELAYS) {
  md += `## start ${start}, FG delay ${delay}\n\n| candidate | Open liq | Close liq | Close-Open | Open mv | Close mv | Open sells/buys | Close sells/buys |\n|---|---:|---:|---:|---:|---:|---|---|\n`;
  for (const c of CANDS) { const o = L(c.id, start, delay, 'NEXT_OPEN'), k = L(c.id, start, delay, 'NEXT_CLOSE'); md += `| ${c.id} | ${Math.round(o.liquidation_after_tax_same_day)} | ${Math.round(k.liquidation_after_tax_same_day)} | ${Math.round(k.liquidation_after_tax_same_day - o.liquidation_after_tax_same_day)} | ${Math.round(o.final_total_market_value_incl_realized_taxes)} | ${Math.round(k.final_total_market_value_incl_realized_taxes)} | ${o.sell_count}/${o.buy_count} | ${k.sell_count}/${k.buy_count} |\n`; }
  md += '\n';
}
fs.writeFileSync(path.join(here, 'tables.md'), md);


// ---- descriptive: next-session Close/Open - 1 on the exec dates of FILLED orders in the 24 Open cells (unique by exec date and side; cells overlap, so this is NOT an independent sample)
const uniq = new Map();
for (const [k, v] of sim) { if (!k.endsWith('NEXT_OPEN')) continue; for (const t of v.a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type) && t.status === 'FILLED_DIAGNOSTIC')) { const side = t.type === 'SELL' ? 'SELL' : 'BUY', o = rowBy.get(t.date); uniq.set(side + '|' + t.date, o.close / o.open - 1); } }
const stat = a => { const s = [...a].sort((x, y) => x - y); return {n: s.length, mean_pct: 100 * s.reduce((x, y) => x + y, 0) / s.length, median_pct: 100 * s[Math.floor(s.length / 2)], min_pct: 100 * s[0], max_pct: 100 * s.at(-1)}; };
const fillGap = {note: 'close/open-1 on the exec date; unique exec dates over the 24 Open cells; descriptive only, overlapping paths', BUY: stat([...uniq].filter(([k]) => k.startsWith('BUY')).map(x => x[1])), SELL: stat([...uniq].filter(([k]) => k.startsWith('SELL')).map(x => x[1]))};
fs.writeFileSync(path.join(here, 'fill_day_close_vs_open.json'), JSON.stringify(fillGap, null, 2));

fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({passed_all: failures.length === 0, failure_count: failures.length, failures: failures.slice(0, 40),
  counts: {cells: 48, open_cells_reused_and_resimulated: 24, close_cells_new: 24, simulate_calls: simCalls, paired_rows: paired.length, explained_paths: pathEvents.size, ledger_event_rows: events.length, month_end_gap_rows: gaps.length, tolerance_USD: 1e-6,
    original_ohlc_rows_with_open_ne_close_in_window: openDiffersFromClose}, refs, checks}, null, 2));
fs.writeFileSync(path.join(here, 'environment.json'), JSON.stringify({node: process.version, platform: process.platform, command: 'cd research/after_tax_comparability_20261027 && node run.mjs', network: 'not used', secrets: 'none'}, null, 2));
console.log(JSON.stringify({passed_all: failures.length === 0, failures: failures.slice(0, 10), simCalls, events: events.length, gaps: gaps.length, checks: Object.fromEntries(Object.entries(checks).map(([k, v]) => [k, `${v.n}/${v.fail}`]))}, null, 1));
if (failures.length) process.exit(1);
