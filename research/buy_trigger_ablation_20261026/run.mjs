// node run.mjs  (Node >=22, stdlib only, no network, no env reads). Buy-trigger ablation: 144 evaluation cells = 72 reused (77bb44f) + 72 new.
// simulate budget: main 72 + regression 24 + synthetic <=12 (counted below). signals() calls outside simulate are counted separately.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import * as E from './engine.mjs';
import * as O from '../SOXL_allocation_separation_20261026/engine.mjs';
const {load, signals, sellCosts, commission, TAX} = E;

const here = path.dirname(fileURLToPath(import.meta.url)), base = path.join(here, '..');
const A = path.join(base, 'SOXL_allocation_separation_20261026'), X = path.join(base, 'SOXL_exit_study_20261023'), P = path.join(base, 'profit_target_isolated_20261026');
const SPEC_COMMIT = '4cb58b4dee6440b5200a0c22357cbcfeb1877ca1'; // committed + pushed before any computation in this file ran
const spec = JSON.parse(fs.readFileSync(path.join(here, 'specification.json'), 'utf8')), refsIn = JSON.parse(fs.readFileSync(path.join(here, 'source_refs.json'), 'utf8'));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const failures = [], checks = {};
const ok = (n, c, d) => { (checks[n] ??= {n: 0, fail: 0}).n++; if (!c) { checks[n].fail++; failures.push({check: n, detail: d}); } };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;
const pct = x => Math.round(x * 100);
const q = v => v == null ? '' : typeof v === 'string' ? '"' + v.replaceAll('"', '""') + '"' : String(v);
const csv = rows => { const keys = [...new Set(rows.flatMap(Object.keys))]; return keys.join(',') + '\n' + rows.map(r => keys.map(k => q(r[k])).join(',')).join('\n') + '\n'; };
const parse = t => { const lines = t.trim().split('\n'); const split = l => { const o = []; let f = '', inq = false; for (let i = 0; i < l.length; i++) { const c = l[i]; if (inq) { if (c === '"') { if (l[i + 1] === '"') { f += '"'; i++; } else inq = false; } else f += c; } else if (c === '"') inq = true; else if (c === ',') { o.push(f); f = ''; } else f += c; } o.push(f); return o; }; const h = split(lines[0]); return lines.slice(1).map(l => { const x = split(l); return Object.fromEntries(h.map((k, i) => [k, x[i]])); }); };
const budget = {main_new: 0, regression_original: 0, regression_copy: 0, synthetic: 0, signals_calls_outside_simulate: 0};
const sigs = (rows, o) => { budget.signals_calls_outside_simulate++; return signals(rows, o); };

// ---- pinned references
const ref = refsIn.fixed_sources;
const cur = {engine_original: sha(path.join(A, 'engine.mjs')), engine_copy: sha(path.join(here, 'engine.mjs')), profit_summary: sha(path.join(P, 'summary.csv')), profit_month: sha(path.join(P, 'month_end_summary.csv')), dividends: sha(path.join(A, 'dividends_verified.json')),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(path.join(X, 'data', f))]))};
ok('original_engine_sha', cur.engine_original === ref.original_engine_expected_sha256 && cur.engine_original === ref.original_engine_sha256, cur.engine_original);
ok('engine_copy_sha_equals_committed_ref', cur.engine_copy === refsIn.this_study_files_committed_before_computation.engine_copy_sha256, cur.engine_copy);
ok('profit_target_summary_sha', cur.profit_summary === ref.profit_target_summary_csv, '');
ok('profit_target_month_end_sha', cur.profit_month === ref.profit_target_month_end_summary_csv, '');
ok('dividends_sha', cur.dividends === ref.dividends_verified_json, '');
for (const [f, h] of Object.entries(cur.inputs)) ok('input_sha', h === ref.inputs[f], f);

const input = await load(path.join(X, 'data'));
const schedule = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const baseOpts = {end: '2026-08-10', initial: 10000, allowInitialReentry: true, dividendSchedule: schedule, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0};
const EXITS = {P20_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .2, exitRsi: 75}, P20_OR_R75: {exitMode: 'OR', profitTarget: .2, exitRsi: 75}, NO_SELL: {exitMode: 'NONE', profitTarget: .2, exitRsi: 75}};
const starts = spec.fixed.starts, delays = spec.fixed.fg_delay, MAIN_STARTS = ['2024-10-01', '2025-01-02'];
const PROFILES = [{id: 'NO_SELL_I25', exit: 'NO_SELL', I: .25, R: null, main: true}, {id: 'P20_ONLY_I25_R25', exit: 'P20_ONLY', I: .25, R: .25, main: true}, {id: 'P20_ONLY_I25_R100', exit: 'P20_ONLY', I: .25, R: 1, main: true},
  {id: 'NO_SELL_I0', exit: 'NO_SELL', I: 0, R: null, main: false}, {id: 'NO_SELL_I100', exit: 'NO_SELL', I: 1, R: null, main: false}, {id: 'P20_OR_R75_I25_R25', exit: 'P20_OR_R75', I: .25, R: .25, main: false}];
const SETTINGS = {BOTH_ON: {}, NORMAL_OFF: {enableNormal: false}, EXFEAR_OFF: {enableExFear: false}};
const cands = []; // 12
for (const p of PROFILES) { cands.push({...p, setting: 'BOTH_ON', cid: `${p.id}__BOTH_ON`, reused: true}); if (p.main) for (const s of ['NORMAL_OFF', 'EXFEAR_OFF']) cands.push({...p, setting: s, cid: `${p.id}__${s}`, reused: false}); }
ok('twelve_candidates', cands.length === 12, String(cands.length));
const optsFor = (c, start, delay, flags = SETTINGS[c.setting]) => ({...baseOpts, start, delay, ...EXITS[c.exit], reentry: c.I, initialRatio: c.I, reentryRatio: c.R ?? c.I, ...flags});

// ---- deep comparison (numbers 1e-6, everything else exact, key sets exact)
function deepDiff(a, b, p = '', out = []) {
  if (out.length > 20) return out;
  if (typeof a === 'number' && typeof b === 'number') { if (!(a === b || Math.abs(a - b) <= 1e-6)) out.push(`${p}: ${a} vs ${b}`); }
  else if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    if (ka.join() !== kb.join()) out.push(`${p}: keys ${ka.join('|')} vs ${kb.join('|')}`);
    for (const k of ka) if (k in b) deepDiff(a[k], b[k], p + '/' + k, out);
  } else if (a !== b) out.push(`${p}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
  return out;
}

// ---- analysis of one simulated cell
function label(ledger) { let sold = false; return ledger.map(t => { let cls = ''; if (t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND'; else if (['NORMAL', 'EXFEAR', 'SELL'].includes(t.type)) cls = t.type; const o = {...t, cls}; if (t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC') sold = true; return o; }); }
function analyze(r, c, delay, doChecks = true) {
  const ledger = label(r.ledger), daily = r.daily, p = daily.at(-1), tag = `${c.cid}|${r.cfg.start}|d${delay}`;
  const sales = ledger.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const mmfNet = ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + p.mmf_accrued_gross * (1 - TAX);
  const ent = ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT'), pay = ledger.filter(t => t.type === 'DIVIDEND_PAYMENT_DATE_PROXY');
  const divNet = ent.reduce((a, t) => a + t.net, 0), gain = sales.reduce((a, t) => a + t.gain, 0), tax = sales.reduce((a, t) => a + t.tax, 0);
  const fills = ledger.filter(t => t.status === 'FILLED_DIAGNOSTIC' && ['NORMAL', 'EXFEAR', 'REENTRY'].includes(t.type));
  const supp = r.candidates.filter(x => x.suppressed_market_order);
  if (doChecks) {
    ok('accounting_identity', near(r.cfg.initial + gain - tax + mmfNet + divNet + p.unrealized, p.total), tag);
    ok('terminal_date_2026-08-10', p.date === '2026-08-10', tag);
    ok('fresh_account_at_start', daily[0].date >= r.cfg.start && daily[0].cash === 10000 && daily[0].shares === 0 && ledger.every(t => t.date >= r.cfg.start), tag);
    ok('balance_invariants_nonneg_cash_integer_shares_zero_basis', daily.every(d => d.cash >= -1e-7 && Number.isInteger(d.shares) && d.shares >= 0 && (d.shares > 0 || d.basis === 0) && d.basis >= -1e-7), tag);
    ok('every_sale_net_gain_ge_2pct_of_cost', sales.every(t => t.gain >= t.basis * .02 - 1e-7), tag);
    ok('dividend_no_double_counting', near(divNet, pay.reduce((a, t) => a + t.net, 0) + p.dividend_receivable_net, 1e-9) && new Set(pay.map(t => t.ex_date)).size === pay.length && new Set(ent.map(t => t.pay_date)).size === ent.length, tag);
    ok('fee_tax_ledger_consistency', near(ledger.reduce((a, t) => a + (t.fee ?? 0), 0), fills.reduce((a, t) => a + t.fee, 0) + sales.reduce((a, t) => a + t.fee, 0)) && near(tax, sales.reduce((a, t) => a + Math.max(0, t.gain) * TAX, 0)), tag);
    if (c.exit === 'NO_SELL') ok('no_sell_zero_sales_zero_aftersale', sales.length === 0 && !ledger.some(t => t.cls === 'AFTER_SALE_REENTRY'), tag);
    if (c.setting === 'NORMAL_OFF') ok('zero_NORMAL_orders_when_normal_off', !ledger.some(t => t.type === 'NORMAL') && !r.candidates.some(x => x.pending === 'NORMAL'), tag);
    if (c.setting === 'EXFEAR_OFF') ok('zero_EXFEAR_orders_when_exfear_off', !ledger.some(t => t.type === 'EXFEAR') && !r.candidates.some(x => x.pending === 'EXFEAR'), tag);
    if (c.setting === 'BOTH_ON') ok('no_suppression_field_when_both_on', supp.length === 0 && r.candidates.every(x => !('suppressed_market_order' in x)), tag);
    if (c.setting !== 'BOTH_ON') ok('suppressed_type_matches_flag', supp.every(x => x.suppressed_market_order === (c.setting === 'NORMAL_OFF' ? 'NORMAL' : 'EXFEAR') && x.pending !== x.suppressed_market_order), tag);
  }
  return {summary: {candidate_id: c.cid, base_profile: c.id, setting: c.setting, enable_normal: c.setting !== 'NORMAL_OFF', enable_exfear: c.setting !== 'EXFEAR_OFF', exit_id: c.exit, I_initial: c.I, R_after_sale: c.R, start: r.cfg.start, fg_delay: delay,
    final_total: p.total, net_profit: p.total - r.cfg.initial, final_total_jpy150: p.total * 150, liquidation: p.liquidation, liquidation_jpy150: p.liquidation * 150, final_shares: p.shares, final_cash: p.cash, final_market_value: p.market_value, final_basis: p.basis, final_unrealized: p.unrealized,
    mmf_net_total: mmfNet, dividend_net_total: divNet, realized_stock_gain: gain, realized_stock_tax: tax, total_order_fees: ledger.reduce((a, t) => a + (t.fee ?? 0), 0),
    buy_count: fills.length, normal_exfear_buy_count: fills.filter(t => t.type !== 'REENTRY').length, normal_buy_count: fills.filter(t => t.type === 'NORMAL').length, exfear_buy_count: fills.filter(t => t.type === 'EXFEAR').length,
    initial_trend_count: ledger.filter(t => t.cls === 'INITIAL_TREND' && t.status === 'FILLED_DIAGNOSTIC').length, after_sale_reentry_count: ledger.filter(t => t.cls === 'AFTER_SALE_REENTRY' && t.status === 'FILLED_DIAGNOSTIC').length,
    sell_count: sales.length, blocked_sales: r.summary.blocked_sales, suppressed_market_orders: supp.length, first_buy_date: fills[0]?.date ?? '', first_sale_date: sales[0]?.date ?? ''}, ledger, daily, candidates: r.candidates};
}

// ---- no day can have a market buy signal coincide with a reentry candidate (so a suppressed order can never turn into a reentry order)
for (const d of delays) ok('no_day_with_ex_or_normal_and_reCandidate', sigs(input.rows, {delay: d}).every(s => !((s.ex || s.normal) && s.reCandidate)) && sigs(input.rows, {delay: d}).every(s => !(s.ex && s.normal)), `delay ${d}`);

// ---- 1. regression: original engine vs copy (both flags on), 12 conditions x 2 = 24 simulate calls
const REG = [], regCopy = new Map(); let regCounter = 0;
for (const start of MAIN_STARTS) for (const delay of delays) for (const p of PROFILES.filter(p => p.main)) {
  const c = {...p, setting: 'BOTH_ON', cid: `${p.id}__BOTH_ON`}, o = optsFor(c, start, delay, {});
  budget.regression_original++; const ro = O.simulate(input.rows, o);
  const explicit = regCounter++ % 2 === 0, flags = explicit ? {enableNormal: true, enableExFear: true} : {};
  budget.regression_copy++; const rc = E.simulate(input.rows, {...o, ...flags});
  const tag = `${c.cid}|${start}|d${delay}|${explicit ? 'explicit' : 'omitted'}`;
  for (const part of ['summary', 'ledger', 'daily', 'candidates', 'signals']) { const d = deepDiff(ro[part], rc[part]); ok('regression_' + part + '_original_vs_copy', d.length === 0, tag + ' ' + d.slice(0, 3).join(' ; ')); }
  const cfgC = {...rc.cfg}; const hasFlags = cfgC.enableNormal === true && cfgC.enableExFear === true; delete cfgC.enableNormal; delete cfgC.enableExFear;
  ok('regression_cfg_equal_except_new_flags', hasFlags && deepDiff(ro.cfg, cfgC).length === 0, tag);
  const st = storedMap(P)(c.cid, start, delay); if (st) ok('regression_copy_final_total_equals_77bb44f_stored', near(rc.summary.final_total, Number(st.final_total)), tag);
  regCopy.set(`${c.cid}|${start}|${delay}`, analyze(rc, c, delay, true)); REG.push(tag);
}
function storedMap(dir) { const rows = parse(fs.readFileSync(path.join(dir, 'summary.csv'), 'utf8')); const m = new Map(rows.map(r => [`${r.candidate_id}|${r.start}|${r.fg_delay}`, r])); return (cid, s, d) => m.get(`${cid.replace('__BOTH_ON', '')}|${s}|${d}`); }
const stored = storedMap(P);
ok('regression_runs_24', budget.regression_original === 12 && budget.regression_copy === 12 && REG.length === 12, JSON.stringify(budget));

// ---- 2. synthetic boundary checks (9 simulate calls)
function mkRows(spec) { // spec: [{fg,rsi,above(bool),shd,open,close}]
  const d = new Date('2025-01-02T00:00:00Z'); const rows = [];
  for (const s of spec) { while ([0, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1); const px = s.close ?? s.open ?? 10;
    rows.push({date: d.toISOString().slice(0, 10), open: s.open ?? px, high: px, low: px, close: px, volume: 1, fg: s.fg, rsi: s.rsi ?? 50, soxx: s.above ? 110 : 100, sma: 105, shd: s.shd ?? null}); d.setUTCDate(d.getUTCDate() + 1); }
  return rows;
}
const sOpts = (extra = {}) => ({start: '2025-01-02', end: '2025-12-31', initial: 10000, allowInitialReentry: true, dividendSchedule: null, mmfRate: 0, reentry: .25, initialRatio: .25, reentryRatio: .25, exitMode: 'NONE', profitTarget: .2, ...extra});
const synSim = (rows, o) => { budget.synthetic++; return E.simulate(rows, o); };
const fills = r => r.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type));
{ // A: EXFEAR episode consumption and rearm. fg 40x3 -> 20 (ex) -> 20 (consumed) -> 35x3 (rearm) -> 20 (ex)
  const rowsA = mkRows([40, 40, 40, 20, 20, 35, 35, 35, 20, 40, 40].map(fg => ({fg, above: false})));
  const sA = sigs(rowsA, {}), exDays = sA.filter(s => s.ex).map(s => s.date);
  const on = synSim(rowsA, sOpts()), off = synSim(rowsA, sOpts({enableExFear: false}));
  ok('synthetic_A_ex_signal_days_two_and_rearm', exDays.length === 2 && exDays[0] === rowsA[3].date && exDays[1] === rowsA[8].date, exDays.join());
  ok('synthetic_A_signals_identical_flag_on_off', deepDiff(on.signals, off.signals).length === 0, '');
  ok('synthetic_A_on_has_EXFEAR_order_at_first_ex_day', on.ledger.some(t => t.type === 'EXFEAR' && t.signal_date === rowsA[3].date && t.status === 'FILLED_DIAGNOSTIC'), '');
  ok('synthetic_A_off_zero_EXFEAR_but_episode_consumed', !off.ledger.some(t => t.type === 'EXFEAR') && off.signals.filter(s => s.ex).length === 2 && !off.signals[4].ex && off.candidates.filter(x => x.suppressed_market_order === 'EXFEAR').length === 2, JSON.stringify(off.candidates.map(x => x.suppressed_market_order)));
  ok('synthetic_A_off_account_stays_cash', off.daily.at(-1).shares === 0 && off.daily.at(-1).cash === 10000, '');
}
{ // B: NORMAL needs a rising edge; suppression must not change normal_raw history, later rise still flagged
  const row = (fg, nr) => ({fg, above: nr, rsi: 50, shd: nr ? -1 : 1});
  const rowsB = mkRows([row(40, false), row(27, true), row(27, true), row(27, true), row(40, false), row(27, true), row(40, false), row(40, false)]);
  const on = synSim(rowsB, sOpts()), off = synSim(rowsB, sOpts({enableNormal: false}));
  const nd = on.signals.filter(s => s.normal).map(s => s.date);
  ok('synthetic_B_normal_rising_edges_only', nd.length === 2 && nd[0] === rowsB[1].date && nd[1] === rowsB[5].date, nd.join());
  ok('synthetic_B_signals_identical_flag_on_off', deepDiff(on.signals, off.signals).length === 0, '');
  ok('synthetic_B_off_zero_NORMAL_orders_and_suppressed_recorded', !off.ledger.some(t => t.type === 'NORMAL') && off.candidates.filter(x => x.suppressed_market_order === 'NORMAL').length === 2 && on.ledger.filter(t => t.type === 'NORMAL').length >= 1, '');
}
{ // C: sell priority. buy via NORMAL, then ex day while profit >= 20% -> pending must be SELL for flag on and off
  const sp = [{fg: 40}, {fg: 27, above: true, shd: -1, open: 10, close: 10}, {fg: 40, open: 10, close: 10}, {fg: 40, open: 10, close: 10}, {fg: 40, open: 10, close: 10}, {fg: 40, open: 10, close: 10}, {fg: 20, open: 10, close: 12.5}, {fg: 40, open: 12.5, close: 12.5}, {fg: 40, open: 12.5, close: 12.5}];
  const rowsC = mkRows(sp), o = sOpts({exitMode: 'PROFIT_ONLY'});
  const on = synSim(rowsC, o), off = synSim(rowsC, {...o, enableExFear: false});
  const exDay = rowsC[6].date;
  ok('synthetic_C_ex_and_profit_same_day', on.signals[6].ex === true && on.candidates.some(x => x.date === exDay && x.sellCandidate && x.ex), '');
  ok('synthetic_C_pending_is_SELL_flag_on', on.candidates.find(x => x.date === exDay).pending === 'SELL', '');
  ok('synthetic_C_pending_is_SELL_flag_off_and_no_suppression_recorded', off.candidates.find(x => x.date === exDay).pending === 'SELL' && !('suppressed_market_order' in off.candidates.find(x => x.date === exDay)), '');
  ok('synthetic_C_ledger_equal_on_off_and_sale_filled', deepDiff(on.ledger, off.ledger).length === 0 && on.ledger.some(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC'), '');
}
{ // D: initial I and after-sale R stay separate and ON with either single flag off
  const up = (fg, rsi, px) => ({fg, rsi, above: true, open: px, close: px});
  const sp = [up(40, 50, 10), up(40, 50, 10), up(40, 60, 10) /*reCandidate -> initial I*/, up(40, 60, 10), up(40, 60, 10), up(40, 60, 12.5) /*+25% -> SELL*/, up(40, 60, 12.5), up(40, 60, 12.5), up(40, 60, 12.5), up(40, 60, 12.5),
    up(40, 50, 12.5), up(40, 60, 12.5) /*reCandidate after sale -> R*/, up(40, 60, 12.5), up(40, 60, 12.5)];
  const rowsD = mkRows(sp), o = sOpts({exitMode: 'PROFIT_ONLY', initialRatio: .25, reentryRatio: 1});
  const a = synSim(rowsD, {...o, enableNormal: false}), b = synSim(rowsD, {...o, enableExFear: false});
  const f = a.ledger.filter(t => t.type === 'REENTRY' && t.status === 'FILLED_DIAGNOSTIC');
  ok('synthetic_D_initial_then_aftersale_entries_exist', f.length === 2 && a.ledger.some(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC'), JSON.stringify(f.map(t => t.date)));
  if (f.length === 2) { ok('synthetic_D_initial_is_25pct', f[0].cost <= f[0].cash_before * .25 + 1e-6 && f[0].cost > f[0].cash_before * .25 - 12.6, `${f[0].cost} ${f[0].cash_before}`); ok('synthetic_D_aftersale_is_100pct', f[1].cost <= f[1].cash_before + 1e-6 && f[1].cost > f[1].cash_before - 12.6 && f[1].cost > f[1].cash_before * .9, `${f[1].cost} ${f[1].cash_before}`); }
  ok('synthetic_D_both_single_flag_runs_equal_when_no_market_buys', deepDiff(a.ledger, b.ledger).length === 0 && deepDiff(a.daily, b.daily).length === 0, '');
}
{ // E: type check
  let thrown = false; try { synSim(mkRows([{fg: 40}, {fg: 40}]), sOpts({enableNormal: 'no'})); } catch (e) { thrown = /enableNormal must be boolean/.test(e.message); }
  ok('synthetic_E_non_boolean_flag_throws', thrown, '');
}
ok('synthetic_calls_le_12', budget.synthetic <= 12, String(budget.synthetic));

// ---- 3. main: 72 new cells
const newCands = cands.filter(c => !c.reused), cells = [], runs = new Map();
const sigFull = new Map(delays.map(d => [d, sigs(input.rows, {delay: d})]));
for (const start of starts) for (const delay of delays) for (const c of cands) {
  const key = `${c.cid}|${start}|${delay}`;
  if (c.reused) {
    const st = stored(c.cid, start, delay); ok('reused_cell_exists_in_77bb44f', !!st, key);
    const s = {...st}; for (const k of Object.keys(s)) if (!isNaN(Number(s[k])) && s[k] !== '' && !/date|start|id|source|exit/.test(k)) s[k] = Number(s[k]);
    cells.push({candidate_id: c.cid, base_profile: c.id, setting: 'BOTH_ON', enable_normal: true, enable_exfear: true, exit_id: c.exit, I_initial: c.I, R_after_sale: c.R, start, fg_delay: delay, ...Object.fromEntries(['final_total', 'net_profit', 'final_total_jpy150', 'liquidation', 'liquidation_jpy150', 'final_shares', 'final_cash', 'final_market_value', 'final_basis', 'final_unrealized', 'mmf_net_total', 'dividend_net_total', 'realized_stock_gain', 'realized_stock_tax', 'total_order_fees', 'buy_count', 'normal_exfear_buy_count', 'initial_trend_count', 'after_sale_reentry_count', 'sell_count', 'blocked_sales'].map(k => [k, s[k]])),
      first_buy_date: st.first_buy_date, first_sale_date: st.first_sale_date, source: 'reuse_77bb44f', source_candidate_id: c.id, source_rank_in_21_37a14c0: st.source_rank_in_21 ?? '', source_rank_in_current_18_77bb44f: st.rank_in_current_18, new_calc_note: ''});
  } else {
    budget.main_new++; const r = E.simulate(input.rows, optsFor(c, start, delay)), a = analyze(r, c, delay);
    const sg = sigFull.get(delay).filter(s => s.date >= start && s.date <= '2026-08-10'); ok('signals_identical_to_flag_independent_signals', deepDiff(r.signals, sg).length === 0, key);
    ok('candidate_market_flags_match_signals', r.candidates.every(x => { const s = sg.find(y => y.date === x.date); return s && s.ex === x.ex && s.normal === x.normal && s.reCandidate === x.reCandidate; }) && sg.filter(s => s.ex || s.normal || s.reCandidate).length === r.candidates.filter(x => true).length - r.candidates.filter(x => x.sellCandidate && !(x.ex || x.normal || x.reCandidate)).length, key);
    runs.set(key, a); cells.push({...a.summary, source: 'rerun_new', source_candidate_id: '', source_rank_in_21_37a14c0: '', source_rank_in_current_18_77bb44f: '', new_calc_note: 'new_flag_off'});
  }
}
ok('cells_144', cells.length === 144, String(cells.length)); ok('reuse_72', cells.filter(c => c.source === 'reuse_77bb44f').length === 72, ''); ok('rerun_72', cells.filter(c => c.source === 'rerun_new').length === 72, '');
ok('main_new_72', budget.main_new === 72, String(budget.main_new));
const simTotal = budget.main_new + budget.regression_original + budget.regression_copy + budget.synthetic; ok('simulate_total_le_108', simTotal <= 108, String(simTotal));
for (const start of starts) for (const delay of delays) { const g = cells.filter(c => c.start === start && c.fg_delay === delay); for (const r of g) r.rank_in_current_12 = 1 + g.filter(x => x.final_total > r.final_total + 1e-7).length; }
// same-profile ON stored value vs ON copy for main starts already compared; sanity: all 144 final totals finite
ok('all_final_totals_finite', cells.every(c => Number.isFinite(c.final_total)), '');
fs.writeFileSync(path.join(here, 'summary.csv'), csv(cells));

// ---- paired effects (72)
const getCell = (cid, s, d) => cells.find(c => c.candidate_id === cid && c.start === s && c.fg_delay === d);
const seq = a => a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type) && t.status === 'FILLED_DIAGNOSTIC').map(t => `${t.date}|${t.type}|${t.shares}`);
const paired = [];
for (const p of PROFILES.filter(p => p.main)) for (const start of starts) for (const delay of delays) for (const off of ['NORMAL_OFF', 'EXFEAR_OFF']) {
  const on = getCell(`${p.id}__BOTH_ON`, start, delay), of = getCell(`${p.id}__${off}`, start, delay), row = {profile: p.id, start, fg_delay: delay, off_setting: off, final_on: on.final_total, final_off: of.final_total, off_minus_on: of.final_total - on.final_total, off_vs_on_pct: (of.final_total / on.final_total - 1) * 100, sign: Math.abs(of.final_total - on.final_total) < 1e-7 ? 'same' : of.final_total > on.final_total ? 'off_higher' : 'off_lower'};
  for (const [k, lab] of [['buy_count', 'buy_count'], ['first_buy_date', 'first_buy_date'], ['sell_count', 'sell_count'], ['final_cash', 'final_cash'], ['final_market_value', 'final_market_value'], ['final_shares', 'final_shares'], ['normal_exfear_buy_count', 'normal_exfear_buy_count']]) { row['on_' + lab] = on[k]; row['off_' + lab] = of[k]; }
  row.off_suppressed_market_orders = of.suppressed_market_orders; row.off_normal_buy_count = of.normal_buy_count; row.off_exfear_buy_count = of.exfear_buy_count;
  if (MAIN_STARTS.includes(start)) {
    const so = seq(regCopy.get(`${p.id}__BOTH_ON|${start}|${delay}`)), sf = seq(runs.get(`${p.id}__${off}|${start}|${delay}`)); let i = 0; while (i < Math.min(so.length, sf.length) && so[i] === sf[i]) i++;
    row.path_compared = true; row.first_divergence_fill = (so[i] ?? sf[i] ?? '').split('|')[0]; row.fills_on = so.length; row.fills_off = sf.length; row.fills_common = so.filter(x => sf.includes(x)).length; row.fills_only_on = so.filter(x => !sf.includes(x)).length; row.fills_only_off = sf.filter(x => !so.includes(x)).length;
  } else row.path_compared = false;
  paired.push(row);
}
ok('paired_72', paired.length === 72, String(paired.length));
fs.writeFileSync(path.join(here, 'paired_effects.csv'), csv(paired));

// ---- month-end (2025-06..2026-07). reused: stored 77bb44f rows; new: from daily
const storedMonth = parse(fs.readFileSync(path.join(P, 'month_end_summary.csv'), 'utf8'));
const months = []; for (let y = 2025, m = 6; !(y === 2026 && m === 8);) { months.push(`${y}-${String(m).padStart(2, '0')}`); if (++m > 12) { m = 1; y++; } }
const tapeLast = new Map(); for (const r of input.rows) { const mo = r.date.slice(0, 7); if (r.date <= '2026-08-10' && (!tapeLast.has(mo) || r.date > tapeLast.get(mo))) tapeLast.set(mo, r.date); }
const me = [];
for (const start of starts) for (const delay of delays) for (const month of months) {
  if (month < start.slice(0, 7)) continue; const grp = [];
  for (const c of cands) {
    if (c.reused) { const m = storedMonth.find(x => x.candidate_id === c.id && x.start === start && x.fg_delay === String(delay) && x.month === month); ok('reused_month_end_row_exists', !!m, `${c.id} ${start} ${delay} ${month}`); if (!m) continue;
      grp.push({start, fg_delay: delay, month, month_end_proxy_date: m.month_end_proxy_date, candidate_id: c.cid, setting: 'BOTH_ON', final_total: Number(m.final_total), shares: Number(m.shares), cash: Number(m.cash), market_value: Number(m.market_value), source: 'reuse_77bb44f'}); }
    else { const a = runs.get(`${c.cid}|${start}|${delay}`), d = a.daily.filter(x => x.date.startsWith(month)).at(-1); ok('rerun_month_end_has_record', !!d, `${c.cid} ${start} ${month}`); if (!d) continue; ok('month_end_record_equals_tape_last_date', d.date === tapeLast.get(month), `${c.cid} ${start} ${month}`);
      grp.push({start, fg_delay: delay, month, month_end_proxy_date: d.date, candidate_id: c.cid, setting: c.setting, final_total: d.total, shares: d.shares, cash: d.cash, market_value: d.market_value, source: 'rerun_new'}); }
  }
  for (const r of grp) r.rank_in_current_12 = 1 + grp.filter(x => x.final_total > r.final_total + 1e-7).length;
  me.push(...grp);
}
fs.writeFileSync(path.join(here, 'month_end_summary.csv'), csv(me));

// ---- event explanations: 36 paths (2 main starts x 3 profiles x 3 settings x 2 delays). Both-ON from regression copy runs, OFF from main memory
const rowBy = new Map(input.rows.map(r => [r.date, r])), oneShot = open => open + commission(open);
const nextDate = d => { const i = input.rows.findIndex(r => r.date === d); return input.rows[i + 1]?.date ?? ''; };
const events = [], pathCounts = [];
for (const start of MAIN_STARTS) for (const delay of delays) for (const p of PROFILES.filter(p => p.main)) for (const setting of Object.keys(SETTINGS)) {
  const c = {...p, setting, cid: `${p.id}__${setting}`}, a = setting === 'BOTH_ON' ? regCopy.get(`${c.cid}|${start}|${delay}`) : runs.get(`${c.cid}|${start}|${delay}`);
  const sgT = new Map(sigFull.get(delay).map(s => [s.date, s])), before = events.length;
  for (const t of a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type))) {
    const D = rowBy.get(t.signal_date), sg = sgT.get(t.signal_date), X0 = rowBy.get(t.date), isSell = t.type === 'SELL', filled = t.status === 'FILLED_DIAGNOSTIC';
    const frac = t.cls === 'INITIAL_TREND' ? c.I : t.cls === 'AFTER_SALE_REENTRY' ? (c.R ?? c.I) : 1, bud = isSell ? '' : t.cash_before * frac;
    let reason = ''; if (!isSell && !filled) reason = bud < oneShot(X0.open) ? 'allocation budget below one share + fee at exec Open' : 'integer rounding';
    events.push({start, fg_delay: delay, profile: p.id, setting, row_kind: filled ? 'FILLED' : isSell ? 'SELL_GATE_BLOCKED' : 'INSUFFICIENT_INTEGER_SHARE', order_type: t.type, allocation_class: t.cls, D: t.signal_date, exec_date: t.date, D_fg_used: sg.fg_used, D_raw_fg_not_used_when_delay1: D.fg, D_close: D.close, D_rsi: D.rsi,
      market_signal_ex: sg.ex, market_signal_normal: sg.normal, exec_open: X0.open, shares_before: t.shares_before, cash_before: t.cash_before, allocation_budget: bud, one_share_cost_at_open: isSell ? '' : oneShot(X0.open), shares: t.shares ?? 0, fee: t.fee ?? '', zero_share_reason: reason});
  }
  for (const x of a.candidates.filter(x => x.suppressed_market_order)) { const sg = sgT.get(x.date), D = rowBy.get(x.date);
    events.push({start, fg_delay: delay, profile: p.id, setting, row_kind: 'MARKET_SIGNAL_ORDER_SUPPRESSED', order_type: x.suppressed_market_order, allocation_class: '', D: x.date, exec_date: nextDate(x.date), D_fg_used: sg.fg_used, D_raw_fg_not_used_when_delay1: D.fg, D_close: D.close, D_rsi: D.rsi, market_signal_ex: sg.ex, market_signal_normal: sg.normal, exec_open: rowBy.get(nextDate(x.date))?.open ?? '', shares_before: a.daily.find(d => d.date === x.date)?.shares ?? '', cash_before: '', allocation_budget: '', one_share_cost_at_open: '', shares: 0, fee: '', zero_share_reason: 'order suppressed by flag (no allocation computed)'}); }
  const mine = events.slice(before); pathCounts.push({start, delay, profile: p.id, setting, events: mine.length, filled: mine.filter(e => e.row_kind === 'FILLED').length, suppressed: mine.filter(e => e.row_kind === 'MARKET_SIGNAL_ORDER_SUPPRESSED').length, insufficient: mine.filter(e => e.row_kind === 'INSUFFICIENT_INTEGER_SHARE').length, sell_blocked: mine.filter(e => e.row_kind === 'SELL_GATE_BLOCKED').length});
}
ok('event_paths_36', pathCounts.length === 36, String(pathCounts.length));
for (const e of events) { const exp = sigFull.get(e.fg_delay).find(s => s.date === e.D).fg_used; ok('events_fg_used_equals_signals_fg_used', e.D_fg_used === exp, e.D + e.fg_delay); }
events.sort((a, b) => 0); fs.writeFileSync(path.join(here, 'events_main_paths.csv'), csv(events));
fs.writeFileSync(path.join(here, 'event_path_counts.csv'), csv(pathCounts));

const sim = {main_new: budget.main_new, regression_original: budget.regression_original, regression_copy: budget.regression_copy, synthetic: budget.synthetic, total: simTotal, limit: 108, signals_calls_outside_simulate: budget.signals_calls_outside_simulate};
fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({passed_all: failures.length === 0, failure_count: failures.length, failures: failures.slice(0, 40), counts: {evaluation_cells: 144, reused: 72, new: 72, candidates: 12, paired_comparisons: paired.length, month_end_rows: me.length, event_rows: events.length, event_filled: events.filter(e => e.row_kind === 'FILLED').length, event_suppressed: events.filter(e => e.row_kind === 'MARKET_SIGNAL_ORDER_SUPPRESSED').length, event_insufficient: events.filter(e => e.row_kind === 'INSUFFICIENT_INTEGER_SHARE').length, event_sell_blocked: events.filter(e => e.row_kind === 'SELL_GATE_BLOCKED').length, event_paths: pathCounts.length, tolerance_USD: 1e-6},
  simulate_calls: sim, checks}, null, 2));
fs.writeFileSync(path.join(here, 'environment.json'), JSON.stringify({node: process.version, platform: process.platform, command: 'cd research/buy_trigger_ablation_20261026 && node run.mjs', network: 'not used', secrets: 'none', spec_commit_before_computation: SPEC_COMMIT, run_mjs_sha256: sha(path.join(here, 'run.mjs')), engine_copy_sha256: cur.engine_copy, specification_sha256: sha(path.join(here, 'specification.json')), source_refs_sha256: sha(path.join(here, 'source_refs.json')), simulate_calls: sim}, null, 2));
console.log(JSON.stringify({passed_all: failures.length === 0, failures: failures.slice(0, 12), sim, checks: Object.fromEntries(Object.entries(checks).map(([k, v]) => [k, `${v.n}/${v.fail}`]))}, null, 1));
if (failures.length) process.exit(1);
