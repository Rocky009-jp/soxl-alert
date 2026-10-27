// node run.mjs   (Node >=22, stdlib only, no network)
// 68 evaluation cells = 24 reused from the stored 77bb44f summary + 44 new simulations; plus 8 regression simulations. simulate budget 52.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {load, simulate as rawSimulate, signals, sellCosts, TAX} from '../SOXL_allocation_separation_20261026/engine.mjs';

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

let simCalls = 0;
const simulate = (rows, opts) => { simCalls++; return rawSimulate(rows, opts); };

// ---- pinned references
const refs = {engine: sha(path.join(A, 'engine.mjs')), dividends: sha(path.join(A, 'dividends_verified.json')), stored_summary_77bb44f: sha(path.join(P, 'summary.csv')),
  inputs: Object.fromEntries(['daily.json', 'daily_adjclose.csv', 'fear-greed.csv'].map(f => [f, sha(path.join(X, 'data', f))])), specification: sha(path.join(here, 'specification.json')), run_this: sha(path.join(here, 'run.mjs'))};
ok('engine_sha', refs.engine === refs0.engine, refs.engine);
ok('dividends_sha', refs.dividends === refs0.dividends, refs.dividends);
ok('stored_summary_sha', refs.stored_summary_77bb44f === refs0.stored_summary_77bb44f, refs.stored_summary_77bb44f);
ok('specification_sha', refs.specification === refs0.specification, refs.specification);
for (const f of Object.keys(refs.inputs)) ok('input_sha', refs.inputs[f] === refs0.inputs[f], f);

const input = await load(path.join(X, 'data'));
const schedule = JSON.parse(fs.readFileSync(path.join(A, 'dividends_verified.json'), 'utf8'));
const rowBy = new Map(input.rows.map(r => [r.date, r]));
const baseOpts = {end: '2026-08-10', initial: 10000, allowInitialReentry: true, dividendSchedule: schedule, dividendMode: 'issuer_exact_pay_date_proxy', mmfRate: .03, closeTargetNet: false, buffer: 0, slippage: 0};
const STARTS = spec.design.starts, DELAYS = spec.design.fg_delay, END = spec.design.terminal;
const TARGETS = spec.design.profit_targets_gross_on_cost, RSIS = [70, 75, 80];
const pct = x => Math.round(x * 100);

// ---- candidates
const CANDS = [];
for (const t of TARGETS) {
  CANDS.push({id: `P${pct(t)}_ONLY_I25_R25`, target: t, rsi: null, mode: 'PROFIT_ONLY', exitRsi: 75, reused: true});
  for (const r of RSIS) CANDS.push({id: `P${pct(t)}_OR_R${r}_I25_R25`, target: t, rsi: r, mode: 'OR', exitRsi: r, reused: t === .2 && r === 75});
}
CANDS.push({id: 'NO_SELL_I25', target: null, rsi: null, mode: 'NONE', exitRsi: 75, reused: true, control: true});
ok('candidates_17', CANDS.length === 17, String(CANDS.length));
ok('reused_candidates_6', CANDS.filter(c => c.reused).length === 6, '');
const optsFor = (c, start, delay) => ({...baseOpts, start, delay, exitMode: c.mode, profitTarget: c.target ?? .2, exitRsi: c.exitRsi, reentry: .25, initialRatio: .25, reentryRatio: .25});

// ---- stored summary
const stored = new Map(parse(fs.readFileSync(path.join(P, 'summary.csv'), 'utf8')).map(s => [`${s.candidate_id}|${s.start}|${s.fg_delay}`, s]));
const last = rowBy.get(END);

// ---- analysis of a simulated run
function label(ledger) { let sold = false; return ledger.map(t => { let cls = ''; if (t.type === 'REENTRY') cls = sold ? 'AFTER_SALE_REENTRY' : 'INITIAL_TREND'; else if (['NORMAL', 'EXFEAR', 'SELL'].includes(t.type)) cls = t.type; const o = {...t, cls}; if (t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC') sold = true; return o; }); }
function analyze(r, c, delay) {
  const ledger = label(r.ledger), daily = r.daily, p = daily.at(-1), tag = `${c.id}|${r.cfg.start}|d${delay}`;
  const sales = ledger.filter(t => t.type === 'SELL' && t.status === 'FILLED_DIAGNOSTIC');
  const fills = ledger.filter(t => t.status === 'FILLED_DIAGNOSTIC' && ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type));
  const buys = fills.filter(t => t.type !== 'SELL');
  const mmfNet = ledger.filter(t => t.type === 'MMF_MONTHLY_PROXY').reduce((a, t) => a + t.gross - t.tax, 0) + p.mmf_accrued_gross * (1 - TAX);
  const ent = ledger.filter(t => t.type === 'DIVIDEND_ENTITLEMENT'), pay = ledger.filter(t => t.type === 'DIVIDEND_PAYMENT_DATE_PROXY');
  const divNet = ent.reduce((a, t) => a + t.net, 0), gain = sales.reduce((a, t) => a + t.gain, 0), tax = sales.reduce((a, t) => a + t.tax, 0);
  const liqCost = p.shares ? sellCosts(p.shares, p.close, p.date) : 0, liqTax = p.shares ? Math.max(0, p.shares * p.close - liqCost - p.basis) * TAX : 0;
  ok('accounting_identity_total', near(r.cfg.initial + gain - tax + mmfNet + divNet + p.unrealized, p.total), tag);
  ok('liquidation_identity', near(p.liquidation, p.total - liqCost - liqTax), tag);
  ok('terminal_date', p.date === END, tag);
  ok('fresh_account_and_start_date', daily[0].date === r.cfg.start && daily[0].cash === 10000 && daily[0].shares === 0 && ledger.every(t => t.date >= r.cfg.start), tag);
  ok('balance_invariants', daily.every(d => d.cash >= -1e-7 && Number.isInteger(d.shares) && d.shares >= 0 && (d.shares > 0 || d.basis === 0) && d.basis >= -1e-7), tag);
  ok('every_filled_sale_net_gain_ge_2pct_of_cost', sales.every(t => t.gain >= t.basis * .02 - 1e-7), tag);
  ok('dividend_no_double_counting', near(divNet, pay.reduce((a, t) => a + t.net, 0) + p.dividend_receivable_net, 1e-9) && new Set(pay.map(t => t.ex_date)).size === pay.length && new Set(ent.map(t => t.pay_date)).size === ent.length, tag);
  for (const t of fills) { ok('fill_price_equals_original_open_of_exec_date', t.price === rowBy.get(t.date).open, `${tag} ${t.date}`); ok('exec_date_after_signal_date', t.signal_date < t.date, tag); }
  // sale signals: D-based hits
  for (const t of ledger.filter(t => t.type === 'SELL')) {
    const D = rowBy.get(t.signal_date), gross = t.shares_before * D.close / t.basis_before - 1, ph = gross >= c.target - 1e-12, rh = c.mode === 'OR' && D.rsi >= c.exitRsi;
    ok('sale_signal_has_profit_hit_or_rsi_hit_per_exit_mode', c.mode === 'PROFIT_ONLY' ? ph : (ph || rh), `${tag} ${t.signal_date}`);
  }
  const ret = x => x / r.cfg.initial - 1;
  return {summary: {candidate_id: c.id, profit_target: c.target ?? '', rsi_option: c.mode === 'NONE' ? 'n/a' : c.rsi ?? 'none', exit_mode: c.mode, start: r.cfg.start, fg_delay: delay,
    liquidation_after_tax_same_day: p.liquidation, final_total_market_value_incl_realized_taxes: p.total, liquidation_roi_vs_10000: ret(p.liquidation), total_roi_vs_10000: ret(p.total),
    terminal_liq_sale_cost: liqCost, terminal_liq_tax_on_unrealized: liqTax, realized_stock_gain: gain, realized_stock_tax: tax, mmf_net_total_after_tax: mmfNet, dividend_net_total_after_tax: divNet, total_order_fees: ledger.reduce((a, t) => a + (t.fee ?? 0), 0),
    final_shares: p.shares, final_cash: p.cash, final_market_value_stock: p.market_value, final_basis: p.basis, final_unrealized: p.unrealized,
    buy_count: buys.length, sell_count: sales.length, blocked_sales: r.summary.blocked_sales, first_buy_date: buys[0]?.date ?? '', first_sale_date: sales[0]?.date ?? ''}, ledger, daily, candidates: r.candidates};
}
const STORED_MAP = {final_total: 'final_total_market_value_incl_realized_taxes', liquidation: 'liquidation_after_tax_same_day', final_shares: 'final_shares', final_cash: 'final_cash', final_market_value: 'final_market_value_stock', final_basis: 'final_basis', final_unrealized: 'final_unrealized',
  mmf_net_total: 'mmf_net_total_after_tax', dividend_net_total: 'dividend_net_total_after_tax', realized_stock_gain: 'realized_stock_gain', realized_stock_tax: 'realized_stock_tax', total_order_fees: 'total_order_fees', buy_count: 'buy_count', sell_count: 'sell_count', blocked_sales: 'blocked_sales'};

// ---- 68 cells
const cells = [], runs = new Map(); // runs: key -> {r, a, c, kind}
for (const start of STARTS) for (const delay of DELAYS) for (const c of CANDS) {
  const key = `${c.id}|${start}|${delay}`;
  if (c.reused) {
    const st = stored.get(key); ok('stored_cell_exists', !!st, key);
    const sh = Number(st.final_shares), cost = sh ? sellCosts(sh, last.close, END) : 0, basis = Number(st.final_basis), liq = Number(st.liquidation), tot = Number(st.final_total);
    const tax = sh ? Math.max(0, sh * last.close - cost - basis) * TAX : 0;
    ok('reused_liquidation_identity_with_derived_terminal_cost_tax', near(liq, tot - cost - tax), key);
    cells.push({candidate_id: c.id, profit_target: c.target ?? '', rsi_option: c.mode === 'NONE' ? 'n/a' : c.rsi ?? 'none', exit_mode: c.mode, start, fg_delay: delay, source: 'reused_77bb44f_stored', source_sha256: refs.stored_summary_77bb44f,
      liquidation_after_tax_same_day: liq, final_total_market_value_incl_realized_taxes: tot, liquidation_roi_vs_10000: liq / 10000 - 1, total_roi_vs_10000: tot / 10000 - 1,
      terminal_liq_sale_cost: cost, terminal_liq_tax_on_unrealized: tax, realized_stock_gain: Number(st.realized_stock_gain), realized_stock_tax: Number(st.realized_stock_tax), mmf_net_total_after_tax: Number(st.mmf_net_total), dividend_net_total_after_tax: Number(st.dividend_net_total), total_order_fees: Number(st.total_order_fees),
      final_shares: sh, final_cash: Number(st.final_cash), final_market_value_stock: Number(st.final_market_value), final_basis: basis, final_unrealized: Number(st.final_unrealized), buy_count: Number(st.buy_count), sell_count: Number(st.sell_count), blocked_sales: Number(st.blocked_sales), first_buy_date: st.first_buy_date, first_sale_date: st.first_sale_date,
      terminal_cost_tax_note: 'derived from stored final shares/basis and the 2026-08-10 close'});
  } else {
    const r = simulate(input.rows, optsFor(c, start, delay)), a = analyze(r, c, delay);
    runs.set(key, {r, a, c, kind: 'new'});
    cells.push({...a.summary, source: 'new_simulation', source_sha256: refs.run_this, terminal_cost_tax_note: 'computed by the run'});
  }
}
ok('cells_68', cells.length === 68, String(cells.length));
ok('new_44', runs.size === 44, String(runs.size));
ok('reused_24', cells.filter(c => c.source.startsWith('reused')).length === 24, '');

// ---- regression 8 (P20_ONLY R25 and P20_OR_R75 R25)
let regWorst = 0;
for (const start of STARTS) for (const delay of DELAYS) for (const id of ['P20_ONLY_I25_R25', 'P20_OR_R75_I25_R25']) {
  const c = CANDS.find(x => x.id === id), key = `${id}|${start}|${delay}`, st = stored.get(key);
  const r = simulate(input.rows, optsFor(c, start, delay)), a = analyze(r, c, delay);
  runs.set(key + '|regression', {r, a, c, kind: 'regression'});
  for (const [k, mine] of Object.entries(STORED_MAP)) { const d = Math.abs(Number(st[k]) - Number(a.summary[mine])); regWorst = Math.max(regWorst, d); ok('regression_amount_equals_stored_1e-6', d <= 1e-6, `${key} ${k} ${d}`); }
  ok('regression_dates_equal_stored', st.first_buy_date === a.summary.first_buy_date && st.first_sale_date === a.summary.first_sale_date, key);
}
ok('simulate_calls_52', simCalls === 52, String(simCalls));
ok('runs_52', runs.size === 52, String(runs.size));

// ---- fg_used consistency
const sigTapes = new Map(DELAYS.map(d => [d, new Map(signals(input.rows, {delay: d}).map(s => [s.date, s]))]));
for (const d of DELAYS) { let allOk = true, differs = 0; for (const [i, r] of input.rows.entries()) { const s = sigTapes.get(d).get(r.date), prev = i >= d ? input.rows[i - d].fg : null; if (s.fg_used !== prev) allOk = false; if (d === 1 && s.fg_used !== r.fg) differs++; } ok('signals_fg_used_equals_row_i_minus_delay', allOk, 'delay ' + d); if (d === 1) ok('delay1_fg_used_differs_from_raw_D_fg', differs > 100, String(differs)); }

fs.writeFileSync(path.join(here, 'summary.csv'), csv(cells));
const C = (id, s, d) => cells.find(x => x.candidate_id === id && x.start === s && x.fg_delay === d);
const idOf = (t, r) => r == null ? `P${pct(t)}_ONLY_I25_R25` : `P${pct(t)}_OR_R${r}_I25_R25`;
const dl = (a, b) => ({d_liq: a.liquidation_after_tax_same_day - b.liquidation_after_tax_same_day, d_mv: a.final_total_market_value_incl_realized_taxes - b.final_total_market_value_incl_realized_taxes});

// ---- profit_effects (12), rsi_effects (48), interaction_effects (36)
const profitEff = [], rsiEff = [], inter = [];
for (const s of STARTS) for (const d of DELAYS) {
  for (const t of [.3, .4, .6]) { const a = C(idOf(t), s, d), b = C(idOf(.2), s, d); const x = dl(a, b); profitEff.push({start: s, fg_delay: d, comparison: `P${pct(t)}_ONLY minus P20_ONLY (R25, no RSI)`, liq_lower: b.liquidation_after_tax_same_day, liq_this: a.liquidation_after_tax_same_day, delta_liquidation: x.d_liq, delta_market_value: x.d_mv, sells_P20: b.sell_count, sells_this: a.sell_count}); }
  for (const t of TARGETS) for (const r of RSIS) { const a = C(idOf(t, r), s, d), b = C(idOf(t), s, d); const x = dl(a, b); rsiEff.push({start: s, fg_delay: d, profit_target: t, rsi: r, comparison: `P${pct(t)}_OR_R${r} minus P${pct(t)}_ONLY`, liq_no_rsi: b.liquidation_after_tax_same_day, liq_with_rsi: a.liquidation_after_tax_same_day, delta_liquidation: x.d_liq, delta_market_value: x.d_mv, sells_no_rsi: b.sell_count, sells_with_rsi: a.sell_count}); }
  for (const t of [.3, .4, .6]) for (const r of RSIS) {
    const e = rsiEff.find(x => x.start === s && x.fg_delay === d && x.profit_target === t && x.rsi === r), e20 = rsiEff.find(x => x.start === s && x.fg_delay === d && x.profit_target === .2 && x.rsi === r);
    inter.push({start: s, fg_delay: d, profit_target: t, rsi: r, rsi_effect_at_target_liq: e.delta_liquidation, rsi_effect_at_20_liq: e20.delta_liquidation, interaction_liq: e.delta_liquidation - e20.delta_liquidation, interaction_market_value: e.delta_market_value - e20.delta_market_value});
  }
}
ok('profit_effects_12', profitEff.length === 12, ''); ok('rsi_effects_48', rsiEff.length === 48, ''); ok('interaction_effects_36', inter.length === 36, '');
fs.writeFileSync(path.join(here, 'profit_effects.csv'), csv(profitEff));
fs.writeFileSync(path.join(here, 'rsi_effects.csv'), csv(rsiEff));
fs.writeFileSync(path.join(here, 'interaction_effects.csv'), csv(inter));

// ---- ledger from the 52 in-memory runs
const ledgerRows = [], pathDesc = [];
for (const [key, run] of runs) {
  const {a, c, r} = run, [id, start, delay0] = key.split('|'), delay = Number(delay0);
  let nBoth = 0, nProfit = 0, nRsi = 0, nBlocked = 0, nFilledSell = 0, seq = 0;
  for (const t of a.ledger.filter(t => ['NORMAL', 'EXFEAR', 'REENTRY', 'SELL'].includes(t.type))) {
    const D = rowBy.get(t.signal_date), X0 = rowBy.get(t.date), isSell = t.type === 'SELL', filled = t.status === 'FILLED_DIAGNOSTIC', sg = sigTapes.get(delay).get(t.signal_date);
    const row = {run_kind: run.kind, candidate_id: id, start, fg_delay: delay, seq: ++seq, D: t.signal_date, exec_date: t.date, order_type: t.type, allocation_class: t.cls, row_kind: filled ? 'FILLED' : isSell ? 'SELL_GATE_BLOCKED' : 'INSUFFICIENT_INTEGER_SHARE',
      D_fg_used: sg.fg_used, D_close: D.close, exec_open: X0.open, shares_before: t.shares_before, cash_before: t.cash_before, basis_before: t.basis_before, shares: t.shares ?? 0, fee: t.fee ?? ''};
    if (isSell) {
      const gross = t.shares_before * D.close / t.basis_before - 1, net = (t.shares_before * D.close - sellCosts(t.shares_before, D.close, D.date)) / t.basis_before - 1;
      const ph = gross >= c.target - 1e-12, rh = c.mode === 'OR' ? D.rsi >= c.exitRsi : null;
      const cls = c.mode === 'PROFIT_ONLY' ? 'profit_only_mode' : ph && rh ? 'both' : ph ? 'profit_only' : 'rsi_only';
      if (cls === 'both') nBoth++; else if (cls === 'profit_only') nProfit++; else if (cls === 'rsi_only') nRsi++; else nProfit++;
      if (!filled) nBlocked++; else nFilledSell++;
      Object.assign(row, {D_gross_profit_on_cost_pct: gross * 100, D_net_of_costs_pct: net * 100, D_soxx_rsi: D.rsi, profit_hit: ph, rsi_hit: rh, signal_class: cls, realised_gross_pct_at_fill: filled ? (t.price * t.shares / t.basis_before - 1) * 100 : '', sell_gain_pre_tax: t.gain ?? '', sell_tax: t.tax ?? '', sell_fee: t.fee ?? ''});
    }
    ledgerRows.push(row);
  }
  const suppressed = r.candidates.filter(x => x.sellCandidate && (x.ex || x.normal || x.reCandidate)).length;
  pathDesc.push({run_kind: run.kind, candidate_id: id, start, fg_delay: delay, sell_signals_total: nBoth + nProfit + nRsi, signals_both: nBoth, signals_profit_only_or_profit_mode: nProfit, signals_rsi_only: nRsi, filled_sales: nFilledSell, gate_blocked_sales: nBlocked, buy_signal_days_overridden_by_sell_signal: suppressed,
    note: 'path description: counts depend on the earlier path, not unique causal contributions; pending-order overwrite is not possible in the engine (one pending, consumed next session)'});
}
// ---- explained paths (rule fixed in specification)
const exec = [...runs.entries()].map(([k, v]) => ({key: k, id: v.c.id, start: k.split('|')[1], delay: Number(k.split('|')[2]), liq: v.a.summary.liquidation_after_tax_same_day, kind: v.kind}));
const explained = [];
for (const s of STARTS) {
  const g = exec.filter(x => x.start === s && x.delay === 0 && x.kind === 'new'); // best/worst among all executed distinct candidates (new OR candidates; regression duplicates stored values and are covered by the reference role)
  const pool = exec.filter(x => x.start === s && x.delay === 0);
  const best = pool.reduce((a, b) => b.liq > a.liq ? b : a), worst = pool.reduce((a, b) => b.liq < a.liq ? b : a), ref = exec.find(x => x.start === s && x.delay === 0 && x.id === 'P20_ONLY_I25_R25' && x.kind === 'regression');
  for (const [role, x] of [['highest_liquidation_among_executed_runs', best], ['lowest_liquidation_among_executed_runs', worst], ['reference_P20_ONLY_R25_regression', ref]]) { const e = explained.find(y => y.key === x.key); if (e) e.roles.push(role); else explained.push({key: x.key, candidate_id: x.id, start: s, fg_delay: 0, liquidation: x.liq, roles: [role]}); }
}
for (const row of ledgerRows) { const e = explained.find(y => y.candidate_id === row.candidate_id && y.start === row.start && row.fg_delay === 0 && (row.run_kind === 'regression') === y.key.endsWith('regression')); row.explained_role = e ? e.roles.join('+') : ''; }
fs.writeFileSync(path.join(here, 'ledger_new_and_regression.csv'), csv(ledgerRows));
fs.writeFileSync(path.join(here, 'path_descriptions.csv'), csv(pathDesc));
fs.writeFileSync(path.join(here, 'explained_paths.json'), JSON.stringify({rule: spec.outputs.explained_paths, paths: explained}, null, 2));
ok('explained_paths_at_most_6', explained.length <= 6 && explained.length >= 2, String(explained.length));
ok('ledger_rows_from_52_runs_only', new Set(ledgerRows.map(r => r.run_kind)).size === 2 && pathDesc.length === 52, String(pathDesc.length));


// ---- descriptive snapshots (added after seeing the ledgers; post hoc, descriptive only): total assets and shares on fixed dates, from the 52 in-memory daily series
const SNAP = ['2026-05-29', '2026-06-26', '2026-07-31', '2026-08-10'];
const snaps = [];
for (const [key, run] of runs) { const [id, start, delay] = key.split('|'); for (const d of SNAP) { const x = run.a.daily.find(y => y.date === d); ok('snapshot_date_exists', !!x, key + d); if (x) snaps.push({run_kind: run.kind, candidate_id: id, start, fg_delay: Number(delay), date: d, total_market_value: x.total, shares: x.shares, cash: x.cash, liquidation: x.liquidation}); } }
fs.writeFileSync(path.join(here, 'snapshots_52runs.csv'), csv(snaps));

// ---- tables.md
let md = '# Tables (generated by run.mjs)\n\nUSD, principal 10,000 included. Each cell: same-day after-tax liquidation / market value (market value already deducts realised-gain, MMF and dividend taxes; unrealised-gain tax and sale cost at 2026-08-10 are not yet deducted). n = sells.\n\n';
for (const s of STARTS) for (const d of DELAYS) {
  md += `## start ${s}, FG delay ${d}  (NO_SELL I25: ${Math.round(C('NO_SELL_I25', s, d).liquidation_after_tax_same_day)} / ${Math.round(C('NO_SELL_I25', s, d).final_total_market_value_incl_realized_taxes)})\n\n| target | no RSI | OR RSI>=70 | OR RSI>=75 | OR RSI>=80 |\n|---|---|---|---|---|\n`;
  for (const t of TARGETS) md += `| ${pct(t)}% | ` + [null, 70, 75, 80].map(r => { const x = C(idOf(t, r), s, d); return `${Math.round(x.liquidation_after_tax_same_day)} / ${Math.round(x.final_total_market_value_incl_realized_taxes)} (n=${x.sell_count})`; }).join(' | ') + ' |\n';
  md += '\n';
}
fs.writeFileSync(path.join(here, 'tables.md'), md);

fs.writeFileSync(path.join(here, 'verification.json'), JSON.stringify({passed_all: failures.length === 0, failure_count: failures.length, failures: failures.slice(0, 40),
  counts: {evaluation_cells: 68, reused_from_stored: 24, new_simulations: 44, regression_simulations: 8, simulate_calls: simCalls, ledger_event_rows: ledgerRows.length, explained_paths: explained.length, regression_max_abs_diff_USD: regWorst, tolerance_USD: 1e-6}, refs, checks}, null, 2));
fs.writeFileSync(path.join(here, 'environment.json'), JSON.stringify({node: process.version, platform: process.platform, command: 'cd research/exit_factorial_current_20261027 && node run.mjs', network: 'not used', secrets: 'none'}, null, 2));
console.log(JSON.stringify({passed_all: failures.length === 0, failures: failures.slice(0, 10), simCalls, regWorst, ledger: ledgerRows.length, explained: explained.map(e => [e.candidate_id, e.start, e.roles])}, null, 1));
if (failures.length) process.exit(1);
