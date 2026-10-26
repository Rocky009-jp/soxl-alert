// node run.mjs   (Node >=22, stdlib only, no network). 216 cells = 108 reused from 37a14c0 + 108 re-run with the UNCHANGED 37a14c0 engine.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load, simulate, signals, sellCosts, commission, TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), base = path.join(here, '..');
const A = path.join(base, 'SOXL_allocation_separation_20261026'), X = path.join(base, 'SOXL_exit_study_20261023');
const spec = JSON.parse(fs.readFileSync(path.join(here, 'specification.json'), 'utf8'));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const failures = [], checks = {};
const ok = (n, c, d) => { (checks[n] ??= {n: 0, fail: 0}).n++; if (!c) { checks[n].fail++; failures.push({check: n, detail: d}); } };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;
const pct = x => Math.round(x * 100);
const q = v => v == null ? '' : typeof v === 'string' ? '"' + v.replaceAll('"', '""') + '"' : String(v);
const csv = rows => { const keys = [...new Set(rows.flatMap(Object.keys))]; return keys.join(',') + '\n' + rows.map(r => keys.map(k => q(r[k])).join(',')).join('\n') + '\n'; };
const parse = t => { const lines = t.trim().split('\n'); const split = l => { const o = []; let f = '', inq = false; for (let i = 0; i < l.length; i++) { const c = l[i]; if (inq) { if (c === '"') { if (l[i + 1] === '"') { f += '"'; i++; } else inq = false; } else f += c; } else if (c === '"') inq = true; else if (c === ',') { o.push(f); f = ''; } else f += c; } o.push(f); return o; }; const h = split(lines[0]); return lines.slice(1).map(l => { const x = split(l); return Object.fromEntries(h.map((k, i) => [k, x[i]])); }); };

// ---- pinned references
const env = JSON.parse(fs.readFileSync(path.join(A, 'environment.json'), 'utf8'));
const refs = {engine: sha(path.join(A, 'engine.mjs')), run_37a14c0: sha(path.join(A, 'run.mjs')), summary_37a14c0: sha(path.join(A, 'summary.csv')), month_end_37a14c0: sha(path.join(A, 'month_end_summary.csv')),
  exit_study_summary: sha(path.join(X, 'summary.csv')), exit_study_sensitivity: sha(path.join(X, 'sensitivity.csv')), dividends: sha(path.join(A, 'dividends_verified.json')),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(path.join(X, 'data', f))])), h2_corrections_reference: sha(path.join(here, 'h2_annotation_corrections_reference.csv')),
  specification: sha(path.join(here, 'specification.json')), run_this: sha(path.join(here, 'run.mjs'))};
ok('engine_sha_equals_37a14c0_environment', refs.engine === env.engine_sha256, refs.engine);
ok('run_sha_equals_37a14c0_environment', refs.run_37a14c0 === env.run_sha256, refs.run_37a14c0);
for (const m of env.input_manifest) ok('input_sha_equals_manifest', refs.inputs[m.file] === m.sha256, m.file);
fs.writeFileSync(path.join(here, 'source_refs.json'), JSON.stringify({docs_start_sha: spec.docs_start_sha, fixed_study: '37a14c0', ...refs}, null, 2));

const input = await load(path.join(X, 'data'));
const schedule = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const baseOpts = {end: '2026-08-10', initial: 10000, allowInitialReentry: true, dividendSchedule: schedule, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0};
const EXITS = {P20_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .2, exitRsi: 75}, P30_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .3, exitRsi: 75}, P40_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .4, exitRsi: 75},
  P60_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .6, exitRsi: 75}, P20_OR_R75: {exitMode: 'OR', profitTarget: .2, exitRsi: 75}, NO_SELL: {exitMode: 'NONE', profitTarget: .2, exitRsi: 75}};
const TARGET = {P20_ONLY: .2, P30_ONLY: .3, P40_ONLY: .4, P60_ONLY: .6, P20_OR_R75: .2, NO_SELL: ''};
const starts = spec.cells.starts, delays = spec.cells.fg_delay, Rs = [0, .25, 1], Is = [0, .25, 1];
const candidates = [];
for (const exit of ['P20_ONLY', 'P30_ONLY', 'P40_ONLY', 'P60_ONLY', 'P20_OR_R75']) for (const R of Rs) candidates.push({id: `${exit}_I25_R${pct(R)}`, exit, I: .25, R, reused: ['P20_ONLY', 'P20_OR_R75'].includes(exit)});
for (const I of Is) candidates.push({id: `NO_SELL_I${pct(I)}`, exit: 'NO_SELL', I, R: null, reused: true});
ok('eighteen_candidates', candidates.length === 18, String(candidates.length));

// ---- analysis of one simulated cell (same fields as the 37a14c0 run.mjs summary)
function label(ledger) {
  let sold = false;
  return ledger.map(t => { let cls = ''; if (t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND'; else if (['NORMAL', 'EXFEAR', 'SELL'].includes(t.type)) cls = t.type; const o = {...t, cls}; if (t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC') sold = true; return o; });
}
function analyze(r, c, delay, tagChecks = true) {
  const ledger = label(r.ledger), daily = r.daily, p = daily.at(-1), tag = `${c.id}|${r.cfg.start}|d${delay}`;
  const sales = ledger.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const mmfNet = ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + p.mmf_accrued_gross * (1 - TAX);
  const ent = ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT'), pay = ledger.filter(t => t.type === 'DIVIDEND_PAYMENT_DATE_PROXY');
  const divNet = ent.reduce((a, t) => a + t.net, 0), gain = sales.reduce((a, t) => a + t.gain, 0), tax = sales.reduce((a, t) => a + t.tax, 0);
  if (tagChecks) {
    ok('accounting_identity', near(r.cfg.initial + gain - tax + mmfNet + divNet + p.unrealized, p.total), tag);
    ok('terminal_date_2026-08-10', p.date === '2026-08-10', tag);
    ok('fresh_account_at_start', daily[0].date >= r.cfg.start && daily[0].cash === 10000 && daily[0].shares === 0 && ledger.every(t => t.date >= r.cfg.start), tag);
    ok('balance_invariants_nonneg_cash_integer_shares_zero_basis', daily.every(d => d.cash >= -1e-7 && Number.isInteger(d.shares) && d.shares >= 0 && (d.shares > 0 || d.basis === 0) && d.basis >= -1e-7), tag);
    ok('every_sale_net_gain_ge_2pct_of_cost', sales.every(t => t.gain >= t.basis * .02 - 1e-7), tag);
    ok('dividend_no_double_counting', near(divNet, pay.reduce((a, t) => a + t.net, 0) + p.dividend_receivable_net, 1e-9) && new Set(pay.map(t => t.ex_date)).size === pay.length && new Set(ent.map(t => t.pay_date)).size === ent.length, tag);
    if (c.exit === 'NO_SELL') ok('no_sell_zero_sales_zero_aftersale', sales.length === 0 && !ledger.some(t => t.cls === 'AFTER_SALE_REENTRY'), tag);
    if (c.R === 0) ok('R0_no_after_sale_buy', !ledger.some(t => t.cls === 'AFTER_SALE_REENTRY' && t.status === 'FILLED_DIAGNOSTIC'), tag);
    for (const t of sales) { const D = input.rows.find(x => x.date === t.signal_date); const gp = t.shares_before * D.close / t.basis_before - 1; ok('sale_signal_gross_on_cost_at_least_target', c.exit === 'NO_SELL' || c.exit === 'P20_OR_R75' || gp >= EXITS[c.exit].profitTarget - 1e-12, tag + ' ' + t.signal_date); }
  }
  const fills = ledger.filter(t => t.status === 'FILLED_DIAGNOSTIC' && ['NORMAL', 'EXFEAR', 'REENTRY'].includes(t.type));
  return {summary: {candidate_id: c.id, exit_id: c.exit, profit_target_gross_on_cost: TARGET[c.exit], rsi75_in_exit: c.exit === 'P20_OR_R75', I_initial: c.I, R_after_sale: c.R, start: r.cfg.start, fg_delay: delay,
    final_total: p.total, net_profit: p.total - r.cfg.initial, final_total_jpy150: p.total * 150, liquidation: p.liquidation, liquidation_jpy150: p.liquidation * 150, final_shares: p.shares, final_cash: p.cash, final_market_value: p.market_value, final_basis: p.basis, final_unrealized: p.unrealized,
    mmf_net_total: mmfNet, dividend_net_total: divNet, realized_stock_gain: gain, realized_stock_tax: tax, total_order_fees: ledger.reduce((a, t) => a + (t.fee ?? 0), 0),
    buy_count: fills.length, normal_exfear_buy_count: fills.filter(t => t.type !== 'REENTRY').length, initial_trend_count: ledger.filter(t => t.cls === 'INITIAL_TREND' && t.status === 'FILLED_DIAGNOSTIC').length,
    after_sale_reentry_count: ledger.filter(t => t.cls === 'AFTER_SALE_REENTRY' && t.status === 'FILLED_DIAGNOSTIC').length, sell_count: sales.length, blocked_sales: r.summary.blocked_sales,
    first_buy_date: fills[0]?.date ?? '', first_sale_date: sales[0]?.date ?? ''}, ledger, daily};
}
const runCell = (c, start, delay) => {
  const e = EXITS[c.exit];
  return simulate(input.rows, {...baseOpts, start, delay, ...e, reentry: c.I, initialRatio: c.I, reentryRatio: c.R ?? c.I});
};
const storedSummary = parse(fs.readFileSync(path.join(A, 'summary.csv'), 'utf8'));
const storedMonth = parse(fs.readFileSync(path.join(A, 'month_end_summary.csv'), 'utf8'));
const sKey = (id, st, d) => `${id}|${st}|${d}`;
const storedMap = new Map(storedSummary.map(s => [sKey(s.candidate_id, s.start, s.fg_delay), s]));
const NUMS = ['final_total', 'liquidation', 'final_shares', 'final_cash', 'final_market_value', 'final_basis', 'final_unrealized', 'mmf_net_total', 'dividend_net_total', 'realized_stock_gain', 'realized_stock_tax', 'total_order_fees', 'buy_count', 'sell_count', 'blocked_sales', 'initial_trend_count', 'after_sale_reentry_count'];
const cmpStored = (s, st, tag, name) => { const worst = Math.max(...NUMS.map(k => Math.abs(Number(s[k]) - Number(st[k])))); ok(name, worst <= 1e-6, `${tag} ${worst}`); return worst; };

// ---- 216 cells
const cells = [], rerunSim = new Map();
for (const start of starts) for (const delay of delays) for (const c of candidates) {
  const tag = sKey(c.id, start, delay);
  if (c.reused) {
    const st = storedMap.get(tag); ok('reused_cell_exists_in_37a14c0', !!st, tag);
    const s = {...Object.fromEntries(Object.entries(st)), ...{candidate_id: c.id, exit_id: c.exit, profit_target_gross_on_cost: TARGET[c.exit], rsi75_in_exit: c.exit === 'P20_OR_R75', I_initial: c.I, R_after_sale: c.R, start, fg_delay: delay}};
    for (const k of NUMS.concat(['final_total_jpy150', 'net_profit', 'liquidation_jpy150'])) s[k] = Number(st[k]);
    s.source = 'reuse_37a14c0'; s.source_rank_in_21 = Number(st.rank_in_start_delay); s.overlap_check_with_old_coupled_study = false;
    delete s.rank_in_start_delay; delete s.delta_vs_P20R75_I25_R25;
    cells.push(s);
  } else {
    const r = runCell(c, start, delay), a = analyze(r, c, delay); rerunSim.set(tag, {r, a});
    const overlap = c.R === .25 && delay === 0; // I25/R25 equals the old I=R study
    cells.push({...a.summary, source: 'rerun_new', source_rank_in_21: '', overlap_check_with_old_coupled_study: overlap});
  }
}
ok('cells_216', cells.length === 216, String(cells.length));
ok('reuse_108', cells.filter(c => c.source === 'reuse_37a14c0').length === 108, '');
ok('rerun_108', cells.filter(c => c.source === 'rerun_new').length === 108, '');
ok('overlap_18', cells.filter(c => c.overlap_check_with_old_coupled_study).length === 18, '');

// ---- overlap checks against the old I=R study
const oldSummary = parse(fs.readFileSync(path.join(X, 'summary.csv'), 'utf8')), oldSens = parse(fs.readFileSync(path.join(X, 'sensitivity.csv'), 'utf8')).filter(r => r.scenario === 'FG_ONE_DAY_DELAY_STRESS');
const oldMap = (rows, ex) => rows.find(r => r.exit_id === ex.exit && Number(r.reentry) === .25);
let ov = 0, ov1 = 0;
for (const c of cells.filter(c => c.overlap_check_with_old_coupled_study)) {
  const o = oldSummary.find(r => r.scenario === 'BASE' && r.exit_id === c.exit_id && r.start === c.start && Number(r.reentry) === .25);
  ok('overlap18_vs_exit_study_summary_final_total', !!o && near(c.final_total, Number(o.final_total)), c.candidate_id + c.start);
  if (o) { for (const [a, b] of [['liquidation', 'liquidation'], ['final_shares', 'final_shares'], ['final_cash', 'final_cash'], ['final_basis', 'final_basis'], ['mmf_net_total', 'mmf_net_total'], ['dividend_net_total', 'dividend_net_total'], ['realized_stock_gain', 'realized_stock_gain'], ['realized_stock_tax', 'realized_stock_tax'], ['total_order_fees', 'total_order_fees']]) ok('overlap18_vs_exit_study_summary_items', near(c[a], Number(o[b])), c.candidate_id + c.start + a); }
  ov++;
}
for (const c of cells.filter(c => c.source === 'rerun_new' && c.R_after_sale === .25 && c.fg_delay === 1)) {
  const o = oldSens.find(r => r.exit_id === c.exit_id && r.start === c.start && Number(r.reentry) === .25);
  if (o) { ok('extra_overlap6_delay1_vs_exit_study_sensitivity', near(c.final_total, Number(o.final_total)), c.candidate_id + c.start); ov1++; }
}

// ---- harness check: re-run the 9 reused candidates for two starts and compare with the stored values (not part of the 216)
let harness = 0;
for (const start of ['2024-10-01', '2025-01-02']) for (const delay of delays) for (const c of candidates.filter(c => c.reused)) {
  const a = analyze(runCell(c, start, delay), c, delay, false), st = storedMap.get(sKey(c.id, start, delay));
  cmpStored(a.summary, st, sKey(c.id, start, delay), 'harness_rerun_reused_vs_37a14c0_summary'); harness++;
  const stM = storedMonth.filter(m => m.candidate_id === c.id && m.start === start && m.fg_delay === String(delay));
  for (const m of stM) { const d = a.daily.filter(x => x.date.startsWith(m.month)).at(-1); ok('harness_month_end_vs_37a14c0', d && d.date === m.month_end_proxy_date && near(d.total, Number(m.final_total)), `${c.id} ${start} d${delay} ${m.month}`); }
}

// ---- rank within the current 18 (ties share a rank), source rank kept separately
for (const start of starts) for (const delay of delays) {
  const g = cells.filter(c => c.start === start && c.fg_delay === delay);
  for (const r of g) r.rank_in_current_18 = 1 + g.filter(x => x.final_total > r.final_total + 1e-7).length;
  const ref = g.find(c => c.candidate_id === 'P20_OR_R75_I25_R25');
  for (const r of g) { r.delta_vs_P20_OR_R75_I25_R25 = r.final_total - ref.final_total; const same = g.find(c => c.exit_id === 'P20_OR_R75' && c.R_after_sale === r.R_after_sale && r.R_after_sale !== null); r.delta_vs_P20_OR_R75_same_R = same ? r.final_total - same.final_total : ''; }
}
fs.writeFileSync(path.join(here, 'summary.csv'), csv(cells));

// ---- month-end (reused: stored rows; rerun: from daily). Ranks recomputed among the current 18.
const months = []; for (let y = 2025, m = 6; !(y === 2026 && m === 8);) { months.push(`${y}-${String(m).padStart(2, '0')}`); if (++m > 12) { m = 1; y++; } }
const tapeLast = new Map(); for (const r of input.rows) { const mo = r.date.slice(0, 7); if (r.date <= '2026-08-10' && (!tapeLast.has(mo) || r.date > tapeLast.get(mo))) tapeLast.set(mo, r.date); }
const me = [];
for (const start of starts) for (const delay of delays) for (const month of months) {
  if (month < start.slice(0, 7)) continue;
  const grp = [];
  for (const c of candidates) {
    if (c.reused) {
      const m = storedMonth.find(x => x.candidate_id === c.id && x.start === start && x.fg_delay === String(delay) && x.month === month);
      ok('reused_month_end_row_exists', !!m, `${c.id} ${start} ${delay} ${month}`); if (!m) continue;
      grp.push({start, fg_delay: delay, month, month_end_proxy_date: m.month_end_proxy_date, candidate_id: c.id, exit_id: c.exit, I_initial: c.I, R_after_sale: c.R, final_total: Number(m.final_total), shares: Number(m.shares), cash: Number(m.cash), market_value: Number(m.market_value), source: 'reuse_37a14c0'});
    } else {
      const a = rerunSim.get(sKey(c.id, start, delay)).a, d = a.daily.filter(x => x.date.startsWith(month)).at(-1);
      ok('rerun_month_end_has_record', !!d, `${c.id} ${start} ${month}`); if (!d) continue;
      ok('month_end_record_equals_tape_last_date', d.date === tapeLast.get(month), `${c.id} ${start} ${month}`);
      grp.push({start, fg_delay: delay, month, month_end_proxy_date: d.date, candidate_id: c.id, exit_id: c.exit, I_initial: c.I, R_after_sale: c.R, final_total: d.total, shares: d.shares, cash: d.cash, market_value: d.market_value, source: 'rerun_new'});
    }
  }
  const refT = grp.find(x => x.candidate_id === 'P20_OR_R75_I25_R25')?.final_total;
  for (const r of grp) { r.rank_in_current_18 = 1 + grp.filter(x => x.final_total > r.final_total + 1e-7).length; r.delta_vs_P20_OR_R75_I25_R25 = refT == null ? '' : r.final_total - refT; }
  me.push(...grp);
}
fs.writeFileSync(path.join(here, 'month_end_summary.csv'), csv(me));

// ---- explanatory events for the two main starts, rerun candidates only (fg_used from signals; D vs exec; gross / net / after-tax separate)
const sigTapes = new Map(delays.map(d => [d, new Map(signals(input.rows, {delay: d}).map(s => [s.date, s]))]));
for (const d of delays) { let allOk = true, differs = 0; for (const [i, r] of input.rows.entries()) { const s = sigTapes.get(d).get(r.date), prev = i >= d ? input.rows[i - d].fg : null; if (s.fg_used !== prev) allOk = false; if (d === 1 && s.fg_used !== r.fg) differs++; } ok('signals_fg_used_equals_row_i_minus_delay', allOk, `delay ${d}`); if (d === 1) ok('delay1_fg_used_differs_from_raw_D_fg_on_some_rows', differs > 100, String(differs)); }
const oneShotCost = (open) => open + commission(open);
const events = [];
function eventsFor(a, c, start, delay) {
  const rowBy = new Map(input.rows.map(r => [r.date, r]));
  for (const t of a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type))) {
    const D = rowBy.get(t.signal_date), sg = sigTapes.get(delay).get(t.signal_date), X0 = rowBy.get(t.date), isSell = t.type === 'SELL';
    const frac = t.cls === 'INITIAL_TREND' ? c.I : t.cls === 'AFTER_SALE_REENTRY' ? (c.R ?? c.I) : 1, budget = isSell ? '' : t.cash_before * frac;
    const filled = t.status === 'FILLED_DIAGNOSTIC';
    let reason = ''; if (!isSell && !filled) reason = budget < oneShotCost(X0.open) ? 'allocation budget below one share + fee at exec Open' : 'integer rounding';
    const gross = isSell ? t.shares_before * D.close / t.basis_before - 1 : '', netD = isSell ? (t.shares_before * D.close - sellCosts(t.shares_before, D.close, D.date)) / t.basis_before - 1 : '';
    events.push({start, fg_delay: delay, candidate_id: c.id, D: t.signal_date, exec_date: t.date, order_type: t.type, allocation_class: t.cls, row_kind: filled ? 'FILLED' : isSell ? 'SELL_GATE_BLOCKED' : 'INSUFFICIENT_INTEGER_SHARE',
      D_fg_used: sg.fg_used, D_raw_fg_same_day_not_used_when_delay1: D.fg, D_close: D.close, D_rsi: D.rsi, exec_open: X0.open, shares_before: t.shares_before, cash_before: t.cash_before, allocation_budget: budget, one_share_cost_at_open: isSell ? '' : oneShotCost(X0.open),
      shares: t.shares ?? 0, fee: t.fee ?? '', D_gross_profit_on_cost_pct: gross, D_net_of_costs_pct: netD, open_realized_gross_pct: isSell && filled ? t.price * t.shares / t.basis_before - 1 : '', sell_gain_pre_tax: t.gain ?? '', sell_tax: t.tax ?? '', zero_share_reason: reason});
  }
}
for (const start of ['2024-10-01', '2025-01-02']) for (const delay of delays) for (const c of candidates.filter(c => !c.reused)) eventsFor(rerunSim.get(sKey(c.id, start, delay)).a, c, start, delay);
fs.writeFileSync(path.join(here, 'events_main_starts.csv'), csv(events));
const nFilled = events.filter(e => e.row_kind === 'FILLED').length;

// ---- H2 correction used as a test: our fg_used / zero-share reasoning must equal the principal's corrected annotations for the same paths
const h2 = parse(fs.readFileSync(path.join(here, 'h2_annotation_corrections_reference.csv'), 'utf8')); let h2n = 0;
const h2Cache = new Map();
for (const row of h2) {
  const k = `${row.start}|${row.fg_delay}|${row.R}`; let a = h2Cache.get(k);
  if (!a) { const c = {id: `P20_OR_R75_I25_R${pct(Number(row.R))}`, exit: 'P20_OR_R75', I: .25, R: Number(row.R)}; a = analyze(runCell(c, row.start, Number(row.fg_delay)), c, Number(row.fg_delay), false); h2Cache.set(k, a); }
  const ev = a.ledger.find(t => t.signal_date === row.D && t.date === row.exec_date && ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type));
  ok('h2_corrected_events_found_in_this_harness', !!ev, k + row.D);
  if (ev) { ok('h2_corrected_fg_used_matches', near(sigTapes.get(Number(row.fg_delay)).get(row.D).fg_used, Number(row.correct_D_fg_used), 1e-9), k + row.D); h2n++; }
}

// ---- tables for the report
const tid = (c, st, d) => cells.find(x => x.candidate_id === c && x.start === st && x.fg_delay === d);
const Rtab = [], Ttab = [];
for (const start of starts) for (const delay of delays) {
  for (const ex of ['P20_ONLY', 'P30_ONLY', 'P40_ONLY', 'P60_ONLY', 'P20_OR_R75']) {
    const t = Rs.map(R => tid(`${ex}_I25_R${pct(R)}`, start, delay)), best = Math.max(...t.map(x => x.final_total));
    Rtab.push({start, fg_delay: delay, exit_id: ex, R0: t[0].final_total, R25: t[1].final_total, R100: t[2].final_total, best_R: t.filter(x => x.final_total >= best - 1e-7).map(x => x.R_after_sale).join('/'), R25_minus_R0: t[1].final_total - t[0].final_total, R25_minus_R100: t[1].final_total - t[2].final_total, best_minus_R25: best - t[1].final_total});
  }
  for (const R of Rs) {
    const o = ['P20_ONLY', 'P30_ONLY', 'P40_ONLY', 'P60_ONLY'].map(ex => tid(`${ex}_I25_R${pct(R)}`, start, delay));
    Ttab.push({start, fg_delay: delay, R, P20: o[0].final_total, P30: o[1].final_total, P40: o[2].final_total, P60: o[3].final_total, d30_20: o[1].final_total - o[0].final_total, d40_30: o[2].final_total - o[1].final_total, d60_40: o[3].final_total - o[2].final_total,
      sells_20_30_40_60: o.map(x => x.sell_count).join('/'), final_shares_20_30_40_60: o.map(x => x.final_shares).join('/'), market_value_share_of_total_20_30_40_60: o.map(x => (x.final_market_value / x.final_total).toFixed(3)).join('/'), NO_SELL_I25: tid('NO_SELL_I25', start, delay).final_total});
  }
}
fs.writeFileSync(path.join(here, 'R_effect_by_exit.csv'), csv(Rtab));
fs.writeFileSync(path.join(here, 'target_effect_by_R.csv'), csv(Ttab));

fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({passed_all: failures.length === 0, failure_count: failures.length, failures: failures.slice(0, 40), counts: {cells: 216, reused_from_37a14c0: 108, rerun_new: 108, of_rerun_overlap_check_old_coupled_study_I25R25_delay0: ov, extra_overlap_delay1_not_counted: ov1,
  harness_rerun_reused_extra_cells: harness, h2_corrected_event_rows_checked: h2n, events_main_starts_rows: events.length, events_filled: nFilled, events_insufficient_or_blocked: events.length - nFilled, month_end_rows: me.length, tolerance_USD: 1e-6}, checks}, null, 2));
fs.writeFileSync(path.join(here, 'environment.json'), JSON.stringify({node: process.version, platform: process.platform, command: 'cd research/profit_target_isolated_20261026 && node run.mjs', network: 'not used', secrets: 'none'}, null, 2));
console.log(JSON.stringify({passed_all: failures.length === 0, failures: failures.slice(0, 10), ov, ov1, harness, h2n, events: events.length, nFilled, me: me.length, checks: Object.fromEntries(Object.entries(checks).map(([k, v]) => [k, `${v.n}/${v.fail}`]))}, null, 1));
if (failures.length) process.exit(1);
