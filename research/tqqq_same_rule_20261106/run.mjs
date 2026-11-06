// node run.mjs   (Node >=22, stdlib only, no network)
// Reference simulation: the same daily rule and the same accounting as the SOXL studies, with the traded fund swapped to TQQQ.
// Engine research/SOXL_allocation_separation_20261026/engine.mjs is imported unchanged. Inputs are the saved Yahoo file
// research/SOXL_exit_study_20261023/data/daily.json, which already holds TQQQ OHLCV (split-adjusted, from 2024-10-01) and QQQ adjClose.
// The only change is a research copy of daily.json in which funds.SOXL is replaced by funds.TQQQ (traded fund) and/or
// references.SOXX by references.QQQ (signal index for SMA200 / RSI14 / exit RSI). F&G and SPY-IEF stay as they are.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load, simulate, sellCosts, quantity, commission, TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

const here = path.dirname(fileURLToPath(import.meta.url)), base = path.join(here, '..');
const A = path.join(base, 'SOXL_allocation_separation_20261026'), X = path.join(base, 'SOXL_exit_study_20261023', 'data'), P = path.join(base, 'profit_target_isolated_20261026');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const failures = [], checks = {};
const ok = (n, c, d) => { (checks[n] ??= {n: 0, fail: 0}).n++; if (!c) { checks[n].fail++; failures.push({check: n, detail: d}); } };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;
const q = v => v == null ? '' : typeof v === 'string' ? '"' + v.replaceAll('"', '""') + '"' : String(v);
const csv = rows => { const keys = [...new Set(rows.flatMap(Object.keys))]; return keys.join(',') + '\n' + rows.map(r => keys.map(k => q(r[k])).join(',')).join('\n') + '\n'; };
const parse = t => { const lines = t.trim().split(/\r?\n/); const h = lines[0].split(','); return lines.slice(1).map(l => { const x = l.split(','); return Object.fromEntries(h.map((k, i) => [k.replaceAll('"', ''), (x[i] ?? '').replaceAll('"', '')])); }); };

const refs = {engine: sha(fs.readFileSync(path.join(A, 'engine.mjs'))), dividends_soxl: sha(fs.readFileSync(path.join(A, 'dividends_verified.json'))),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(fs.readFileSync(path.join(X, f)))]))};
const daily0 = JSON.parse(fs.readFileSync(path.join(X, 'daily.json'), 'utf8'));

// ---- research copies of the input folder (daily.json rewritten, other two files copied byte for byte)
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tqqq-'));
async function variant(fund, index) {
  const d = structuredClone(daily0);
  d.funds.SOXL = structuredClone(daily0.funds[fund]);
  d.references.SOXX = structuredClone(daily0.references[index]);
  const dir = path.join(tmp, `${fund}_${index}`); fs.mkdirSync(dir);
  fs.writeFileSync(path.join(dir, 'daily.json'), JSON.stringify(d));
  for (const f of ['daily_adjclose.csv', 'fear-greed.csv']) fs.copyFileSync(path.join(X, f), path.join(dir, f));
  return (await load(dir)).rows;
}
const VARIANTS = [
  {id: 'SOXL_SOXX', fund: 'SOXL', index: 'SOXX', role: 'baseline (current SOXL rule)'},
  {id: 'TQQQ_SOXX', fund: 'TQQQ', index: 'SOXX', role: 'MAIN: TQQQ traded, rule unchanged (SOXX signals)'},
  {id: 'TQQQ_QQQ', fund: 'TQQQ', index: 'QQQ', role: 'REFERENCE: TQQQ traded, SOXX replaced by QQQ'},
  {id: 'SOXL_QQQ', fund: 'SOXL', index: 'QQQ', role: 'DIAGNOSTIC: separates the signal-index effect from the fund effect'}];
const rowsBy = {};
for (const v of VARIANTS) rowsBy[v.id] = await variant(v.fund, v.index);
const orig = (await load(X)).rows;
ok('soxl_soxx_copy_equals_original_rows', JSON.stringify(orig) === JSON.stringify(rowsBy.SOXL_SOXX), '');
for (const v of VARIANTS) {
  const rows = rowsBy[v.id], o = daily0.funds[v.fund].ohlcv, oi = new Map(o.date.map((x, i) => [x, i]));
  ok('fund_ohlc_equals_saved_fund', rows.filter(r => r.open !== undefined).every(r => r.open === o.open[oi.get(r.date)] && r.close === o.close[oi.get(r.date)]), v.id);
  ok('fg_and_shd_unchanged', rows.every((r, i) => r.fg === orig[i].fg && r.shd === orig[i].shd && r.date === orig[i].date), v.id);
  if (v.index === 'SOXX') ok('soxx_signals_unchanged', rows.every((r, i) => r.rsi === orig[i].rsi && r.sma === orig[i].sma && r.soxx === orig[i].soxx), v.id);
}

// ---- distribution schedules
// SOXL: issuer schedule already used by 77bb44f / 737ef35 (unchanged).
// TQQQ: saved Yahoo ex-date amounts (split-adjusted, 3 decimals, consistent with the adjClose ratio; checked below).
//       Pay date is a PROXY = first saved trading day at least 7 calendar days after the ex-date (ProShares pay dates not retrieved).
const schedSOXL = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const cal = daily0.date;
const addDays = (d, k) => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() + k); return x.toISOString().slice(0, 10); };
const payProxy = ex => cal.find(d => d >= addDays(ex, 7)) ?? addDays(ex, 7);
const tq = daily0.funds.TQQQ, tqo = tq.ohlcv, tqi = new Map(tqo.date.map((x, i) => [x, i])), ci = new Map(cal.map((x, i) => [x, i]));
const schedTQQQ = tq.dividends.filter(([d]) => d >= '2024-10-01' && d <= '2026-08-31').map(([ex, amount]) => ({ex_date: ex, pay_date: payProxy(ex), amount, evidence: 'Yahoo saved ex-date amount; pay_date proxy ex+7d'}));
for (const s of schedTQQQ) {
  const j = tqi.get(s.ex_date), i = ci.get(s.ex_date), c0 = tqo.close[j - 1];
  const implied = c0 * (1 - (tq.adjClose[i - tq.start] / tq.adjClose[i - 1 - tq.start]) / (tqo.close[j] / c0));
  s.adjclose_implied = Math.abs(implied);
  ok('tqqq_dividend_matches_adjclose_implied_within_1pct', Math.abs(Math.abs(implied) - s.amount) <= 0.01 * s.amount + 0.0006, `${s.ex_date} ${s.amount} vs ${implied}`);
}
const schedFor = fund => fund === 'TQQQ' ? schedTQQQ : schedSOXL;

// ---- candidates and cells (same option mapping as 77bb44f / 737ef35)
const EXITS = {P20_ONLY: {exitMode: 'PROFIT_ONLY', profitTarget: .2, exitRsi: 75}, P20_OR_R75: {exitMode: 'OR', profitTarget: .2, exitRsi: 75}, NO_SELL: {exitMode: 'NONE', profitTarget: .2, exitRsi: 75}};
const CANDS = [
  {id: 'NO_SELL_I0', exit: 'NO_SELL', I: 0, R: null}, {id: 'NO_SELL_I25', exit: 'NO_SELL', I: .25, R: null}, {id: 'NO_SELL_I100', exit: 'NO_SELL', I: 1, R: null},
  {id: 'P20_ONLY_I25_R25', exit: 'P20_ONLY', I: .25, R: .25}, {id: 'P20_ONLY_I25_R100', exit: 'P20_ONLY', I: .25, R: 1}, {id: 'P20_OR_R75_I25_R25', exit: 'P20_OR_R75', I: .25, R: .25}];
const STARTS = ['2024-10-01', '2025-01-02', '2025-04-01', '2025-07-01', '2025-10-01', '2026-01-02'], DELAYS = [0, 1], END = '2026-08-10';
const baseOpts = {end: END, initial: 10000, allowInitialReentry: true, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0};

const summary = [], ledgers = [], monthEnd = [];
let simCalls = 0;
for (const v of VARIANTS) for (const start of STARTS) for (const delay of DELAYS) for (const c of CANDS) {
  simCalls++;
  const r = simulate(rowsBy[v.id], {...baseOpts, start, delay, dividendSchedule: schedFor(v.fund), ...EXITS[c.exit], reentry: c.I, initialRatio: c.I, reentryRatio: c.R ?? c.I});
  const L = r.ledger, p = r.daily.at(-1), tag = `${v.id}|${c.id}|${start}|d${delay}`;
  const sales = L.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const buys = L.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY'].includes(t.type) && t.status === 'FILLED_DIAGNOSTIC');
  const mmfNet = L.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + p.mmf_accrued_gross * (1 - TAX);
  const divNet = L.filter(t => t.type === 'DIVIDEND_ENTITLEMENT').reduce((a, t) => a + t.net, 0);
  const gain = sales.reduce((a, t) => a + t.gain, 0), tax = sales.reduce((a, t) => a + t.tax, 0);
  const liqCost = p.shares ? sellCosts(p.shares, p.close, p.date) : 0, liqTax = p.shares ? Math.max(0, p.shares * p.close - liqCost - p.basis) * TAX : 0;
  ok('accounting_identity_total', near(10000 + gain - tax + mmfNet + divNet + p.unrealized, p.total), tag);
  ok('liquidation_identity', near(p.liquidation, p.total - liqCost - liqTax), tag);
  ok('terminal_and_start_dates', p.date === END && r.daily[0].date === start && r.daily[0].shares === 0, tag);
  ok('balance_invariants', r.daily.every(d => d.cash >= -1e-7 && Number.isInteger(d.shares) && d.shares >= 0 && (d.shares > 0 || d.basis === 0)), tag);
  ok('every_sale_net_gain_ge_2pct', sales.every(t => t.gain >= t.basis * .02 - 1e-7), tag);
  if (c.exit === 'NO_SELL') ok('no_sell_has_no_sales', sales.length === 0, tag);
  const ohlc = new Map(rowsBy[v.id].map(x => [x.date, x]));
  for (const t of [...buys, ...sales]) { ok('fill_price_equals_exec_day_open_of_traded_fund', t.price === ohlc.get(t.date).open, tag + ' ' + t.date); ok('exec_after_signal', t.signal_date < t.date, tag); }
  summary.push({variant: v.id, fund: v.fund, signal_index: v.index, candidate_id: c.id, exit_id: c.exit, I_initial: c.I, R_after_sale: c.R ?? c.I, start, fg_delay: delay,
    liquidation_after_tax_same_day: p.liquidation, final_total_market_value: p.total, liquidation_jpy150: p.liquidation * 150, liquidation_roi: p.liquidation / 10000 - 1,
    realized_stock_gain: gain, realized_stock_tax: tax, mmf_net: mmfNet, dividend_net: divNet, final_shares: p.shares, final_cash: p.cash, final_basis: p.basis, final_unrealized: p.unrealized,
    buy_count: buys.length, sell_count: sales.length, blocked_sales: r.summary.blocked_sales, first_buy_date: buys[0]?.date ?? '', first_sale_date: sales[0]?.date ?? ''});
  if ((start === '2024-10-01' || start === '2025-01-02') && delay === 0)
    for (const t of L.filter(t => t.status === 'FILLED_DIAGNOSTIC')) ledgers.push({variant: v.id, candidate_id: c.id, start, fg_delay: delay, date: t.date, signal_date: t.signal_date, type: t.type, shares: t.shares, price: t.price, cost: t.cost ?? '', gain: t.gain ?? '', tax: t.tax ?? '', cash_after: t.cash_after});
  if (delay === 0 && start === '2024-10-01') {
    const byMonth = new Map(); for (const d of r.daily) byMonth.set(d.date.slice(0, 7), d);
    for (const [m, d] of byMonth) monthEnd.push({variant: v.id, candidate_id: c.id, start, fg_delay: delay, month: m, date: d.date, total: d.total, liquidation: d.liquidation, shares: d.shares});
  }
}
ok('simulate_calls_288', simCalls === 288, simCalls);

// ---- SOXL baseline must equal the stored 77bb44f values (same engine, same input, same options)
const stored = parse(fs.readFileSync(path.join(P, 'summary.csv'), 'utf8'));
let compared = 0, maxDiff = 0;
for (const s of stored) {
  const m = summary.find(x => x.variant === 'SOXL_SOXX' && x.candidate_id === s.candidate_id && x.start === s.start && String(x.fg_delay) === s.fg_delay);
  if (!m || s.liquidation === undefined) continue;
  compared++;
  const d1 = Math.abs(m.liquidation_after_tax_same_day - Number(s.liquidation)), d2 = Math.abs(m.final_total_market_value - Number(s.final_total));
  maxDiff = Math.max(maxDiff, d1, d2);
  ok('soxl_baseline_equals_stored_77bb44f', d1 <= 1e-6 && d2 <= 1e-6, `${s.candidate_id}|${s.start}|${s.fg_delay} ${d1} ${d2}`);
}
ok('stored_cells_compared_at_least_24', compared >= 24, compared);

// ---- buy-and-hold price reference (not a simulation; price ratio only, before costs/dividends/tax)
const bh = [];
for (const fund of ['SOXL', 'TQQQ']) { const o = daily0.funds[fund].ohlcv, oi = new Map(o.date.map((x, i) => [x, i]));
  for (const start of STARTS) { const op = o.open[oi.get(start)], cl = o.close[oi.get(END)], n = quantity(10000, op), cost = n * op + commission(n * op), proceeds = n * cl - sellCosts(n, cl, END);
    bh.push({fund, start, open_at_start: op, close_at_end: cl, price_ratio: cl / op, shares: n, liquidation_after_tax_no_div_no_mmf: 10000 - cost + proceeds - Math.max(0, proceeds - cost) * TAX}); } }

fs.writeFileSync(path.join(here, 'summary.csv'), csv(summary));
fs.writeFileSync(path.join(here, 'ledger_main_starts_delay0.csv'), csv(ledgers));
fs.writeFileSync(path.join(here, 'month_end_2024-10-01_delay0.csv'), csv(monthEnd));
fs.writeFileSync(path.join(here, 'buy_and_hold_price_ratio.csv'), csv(bh));
fs.writeFileSync(path.join(here, 'tqqq_distribution_schedule.json'), JSON.stringify(schedTQQQ, null, 1));
fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({refs, simulate_calls: simCalls, stored_cells_compared: compared, stored_max_abs_diff: maxDiff, checks, failures: failures.slice(0, 50), failure_count: failures.length}, null, 1));
console.log('simulate calls', simCalls, 'stored compared', compared, 'maxDiff', maxDiff, 'failures', failures.length);
if (failures.length) console.log(failures.slice(0, 10));
