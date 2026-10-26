#!/usr/bin/env node
// Read-only helper for the USER to fetch a tiny, fixed SOXL sample from Alpaca historical market data (feed=sip).
// Default mode (--plan) performs NO network access and NEVER reads credentials. Real access needs --execute AND --out <private dir>
// AND user-set APCA_API_KEY_ID / APCA_API_SECRET_KEY. Node >= 22, standard library only.
// Not run in the preparation task (actual downloads: 0).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

export const HOST = 'https://data.alpaca.markets';
export const ALLOWED_PATHS = new Set(['/v2/stocks/bars', '/v2/stocks/quotes']);
export const SYMBOL = 'SOXL';
export const DAILY_DATES = ['2024-10-07', '2024-12-20', '2026-06-30', '2026-07-01', '2026-07-29', '2026-07-30', '2026-07-31', '2026-08-10'];
export const SAMPLE_DATES = ['2024-10-07', '2026-07-01'];
export const LIMITS = {timeoutMs: 20000, defaultMaxPages: 5, hardMaxPages: 20, pageLimit: 10000, minAgeMinutes: 15};

// ---- America/New_York wall time -> UTC (DST aware, no deps)
const fmt = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', timeZoneName: 'longOffset'});
export function nyOffsetMinutes(utcMs) {
  const p = fmt.formatToParts(new Date(utcMs)).find(x => x.type === 'timeZoneName').value; // "GMT-04:00"
  const m = /GMT([+-])(\d{2}):(\d{2})/.exec(p);
  if (!m) throw new Error('OFFSET_PARSE');
  return (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
}
export function nyWallToUtcMs(date, hh, mm, ss) {
  const [y, mo, d] = date.split('-').map(Number);
  const wall = Date.UTC(y, mo - 1, d, hh, mm, ss);
  let utc = wall - nyOffsetMinutes(wall) * 60000;
  utc = wall - nyOffsetMinutes(utc) * 60000;
  return utc;
}
export const isoZ = ms => new Date(ms).toISOString().replace('.000Z', 'Z');
export function nyLabel(ms) {
  const off = nyOffsetMinutes(ms), t = new Date(ms + off * 60000).toISOString().slice(0, 19);
  const sign = off < 0 ? '-' : '+', a = Math.abs(off);
  return `${t}${sign}${String(Math.trunc(a / 60)).padStart(2, '0')}:${String(a % 60).padStart(2, '0')}`;
}
// RFC3339 with up to 9 fractional digits -> epoch nanoseconds (BigInt); precision is never reduced.
export function rfc3339ToNs(s) {
  const m = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(String(s));
  if (!m) return null;
  const sec = BigInt(Date.parse(m[1] + (m[3] === 'Z' ? 'Z' : m[3])) / 1000);
  return sec * 1000000000n + BigInt((m[2] ?? '').padEnd(9, '0') || '0');
}

// ---- plan
export function buildPlan(now = new Date(), maxPages = LIMITS.defaultMaxPages) {
  const reqs = [];
  const mk = (id, kind, date, timeframe, s, e, extra = {}) => {
    const startMs = nyWallToUtcMs(date, ...s), endMs = nyWallToUtcMs(date, ...e);
    return {id, kind, symbol: SYMBOL, date, timeframe, start_utc: isoZ(startMs), end_utc: isoZ(endMs), start_ny: nyLabel(startMs), end_ny: nyLabel(endMs),
      feed: 'sip', adjustment: 'raw', limit: kind === 'quotes' || timeframe === '1Min' ? LIMITS.pageLimit : 10, max_pages: kind === 'quotes' ? maxPages : (timeframe === '1Min' ? 2 : 1),
      endpoint: kind === 'quotes' ? '/v2/stocks/quotes' : '/v2/stocks/bars', age_ok_at_plan_time: now.getTime() - endMs >= LIMITS.minAgeMinutes * 60000, ...extra};
  };
  for (const d of DAILY_DATES) reqs.push(mk(`daily_${d}`, 'bars', d, '1Day', [0, 0, 0], [23, 59, 59]));
  for (const d of SAMPLE_DATES) reqs.push(mk(`bars1m_${d}`, 'bars', d, '1Min', [9, 29, 0], [9, 37, 0], {expected_labels_ny: ['09:29', '09:30', '09:31', '09:32', '09:33', '09:34', '09:35', '09:36'], note: 'bar t = left edge; end is inclusive so a 09:37:00 bar may appear and is outside [09:29,09:37)'}));
  for (const d of SAMPLE_DATES) reqs.push(mk(`quotes_${d}`, 'quotes', d, null, [9, 29, 59], [9, 36, 30]));
  return {host: HOST, feed: 'sip', no_iex_fallback: true, symbol: SYMBOL, requests: reqs, network_in_plan_mode: 0, credentials_read_in_plan_mode: 0};
}

export function buildUrl(r, pageToken) {
  const u = new URL(HOST + r.endpoint);
  if (u.origin !== HOST || !ALLOWED_PATHS.has(u.pathname)) throw new Error('URL_NOT_ALLOWED');
  u.searchParams.set('symbols', r.symbol);
  if (r.kind === 'bars') u.searchParams.set('timeframe', r.timeframe);
  u.searchParams.set('start', r.start_utc); u.searchParams.set('end', r.end_utc);
  u.searchParams.set('limit', String(r.limit)); u.searchParams.set('feed', 'sip');
  if (r.kind === 'bars') u.searchParams.set('adjustment', 'raw');
  u.searchParams.set('sort', 'asc');
  if (pageToken) u.searchParams.set('page_token', pageToken);
  return u;
}

// ---- output safety
export function insideGitWorkTree(dir) {
  let p = path.resolve(dir);
  for (;;) {
    if (fs.existsSync(path.join(p, '.git'))) return true;
    const up = path.dirname(p);
    if (up === p) return false;
    p = up;
  }
}
const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');
const STOP = {REDIRECT: 'REDIRECT_REFUSED', TIMEOUT: 'TIMEOUT', NET: 'NETWORK_ERROR', JSON: 'BAD_JSON'};
function httpStop(code) { return code === 429 ? 'HTTP_429_RATE_LIMIT' : code === 401 ? 'HTTP_401_AUTH' : code === 403 ? 'HTTP_403_FORBIDDEN' : `HTTP_${code}`; }

// ---- execute
export async function execute({env, fetchImpl, now, out, maxPages, log}) {
  if (!out) return {ok: false, stop: 'OUT_DIR_REQUIRED'};
  if (insideGitWorkTree(out)) return {ok: false, stop: 'OUT_DIR_INSIDE_GIT_WORKTREE_REFUSED'};
  const keyId = env.APCA_API_KEY_ID, secret = env.APCA_API_SECRET_KEY;
  if (!keyId || !secret) return {ok: false, stop: 'MISSING_CREDENTIALS_ENV'};
  const plan = buildPlan(now, maxPages);
  const tooRecent = plan.requests.filter(r => !r.age_ok_at_plan_time).map(r => r.id);
  if (tooRecent.length) return {ok: false, stop: 'END_NOT_15_MINUTES_OLD', ids: tooRecent};
  const root = path.resolve(out);
  if (fs.existsSync(root) && fs.readdirSync(root).length) return {ok: false, stop: 'OUT_DIR_NOT_EMPTY_REFUSED'};
  fs.mkdirSync(path.join(root, 'raw'), {recursive: true});
  const manifest = {tool: 'alpaca_fetch.mjs', started_utc: now.toISOString(), host: HOST, feed: 'sip', requests: [], stop: null, secrets_stored: false};
  const headers = {'APCA-API-KEY-ID': keyId, 'APCA-API-SECRET-KEY': secret, accept: 'application/json'};
  let stopAll = null;
  for (const r of plan.requests) {
    if (stopAll) break;
    const entry = {id: r.id, kind: r.kind, date: r.date, start_utc: r.start_utc, end_utc: r.end_utc, pages: [], items: 0, complete: false, incomplete_reason: null, anomalies: []};
    manifest.requests.push(entry);
    let token = null, items = [];
    for (let page = 1; page <= r.max_pages; page++) {
      const url = buildUrl(r, token);
      let res, buf;
      try {
        res = await fetchImpl(url.toString(), {method: 'GET', headers, redirect: 'manual', signal: AbortSignal.timeout(LIMITS.timeoutMs)});
        if (res.status >= 300 && res.status < 400) { stopAll = STOP.REDIRECT; break; }
        if (res.status !== 200) { stopAll = httpStop(res.status); break; }
        buf = Buffer.from(await res.arrayBuffer());
      } catch (e) {
        stopAll = e && (e.name === 'TimeoutError' || e.name === 'AbortError') ? STOP.TIMEOUT : STOP.NET; break;
      }
      let body;
      try { body = JSON.parse(buf.toString('utf8')); } catch { stopAll = STOP.JSON; break; }
      const file = `raw/${r.id}_p${page}.json`;
      fs.writeFileSync(path.join(root, file), buf, {flag: 'wx'});
      const arr = body?.[r.kind]?.[r.symbol];
      if (arr !== undefined && !Array.isArray(arr)) { entry.anomalies.push('ITEMS_NOT_ARRAY'); }
      const got = Array.isArray(arr) ? arr : [];
      entry.pages.push({page, file, bytes: buf.length, sha256: sha256(buf), fetched_utc: new Date().toISOString(), items: got.length, has_next_page_token: Boolean(body?.next_page_token)});
      items.push(...got);
      token = body?.next_page_token ?? null;
      if (!token) { entry.complete = true; break; }
      if (page === r.max_pages) entry.incomplete_reason = 'PAGE_CAP_REACHED';
    }
    entry.items = items.length;
    if (stopAll) { entry.incomplete_reason = stopAll; }
    Object.assign(entry, analyze(r, items));
    fs.writeFileSync(path.join(root, `normalized_${r.id}.json`), JSON.stringify({request: r, raw_items: items, derived: derive(r, items)}, null, 2), {flag: 'wx'});
  }
  manifest.stop = stopAll;
  manifest.finished_utc = new Date().toISOString();
  fs.writeFileSync(path.join(root, 'manifest.json'), JSON.stringify(manifest, null, 2), {flag: 'wx'});
  log?.(stopAll ? `STOPPED:${stopAll}` : 'DONE');
  return {ok: !stopAll, stop: stopAll, manifest};
}

// raw values untouched; derived adds time labels only
export function derive(r, items) {
  return items.map(x => {
    const ns = rfc3339ToNs(x.t);
    return {t_raw: x.t, epoch_ns: ns === null ? null : ns.toString(), t_ny: ns === null ? null : nyLabel(Number(ns / 1000000n))};
  });
}
export function analyze(r, items) {
  const a = {anomalies: [], missing_fields: [], out_of_order: 0, outside_window: 0};
  const req = r.kind === 'bars' ? ['t', 'o', 'h', 'l', 'c', 'v'] : ['t', 'bp', 'bs', 'ap', 'as'];
  let prev = null;
  const lo = BigInt(Date.parse(r.start_utc)) * 1000000n, hi = BigInt(Date.parse(r.end_utc)) * 1000000n;
  items.forEach((x, i) => {
    const miss = req.filter(k => !(k in x) || x[k] === null);
    if (miss.length) a.missing_fields.push({index: i, missing: miss}); // never filled with 0 / previous values
    const ns = rfc3339ToNs(x.t);
    if (ns === null) { a.anomalies.push({index: i, issue: 'BAD_TIMESTAMP'}); return; }
    if (prev !== null && ns < prev) a.out_of_order++;
    prev = ns;
    if (ns < lo || ns > hi) a.outside_window++;
  });
  if (r.kind === 'bars' && r.timeframe === '1Min') {
    const present = new Set(items.map(x => (derive(r, [x])[0].t_ny ?? '').slice(11, 16)));
    a.expected_minutes_missing = r.expected_labels_ny.filter(l => !present.has(l)); // a minute without qualifying trades has no bar; not filled
    a.end_boundary_bar_present = present.has('09:37');
  }
  if (r.kind === 'quotes') a.note = 'quote bid/ask size units, NBBO status and raw-key meaning are UNCONFIRMED (see PLAN.md); not usable as NBBO or fill price without that';
  return a;
}

// ---- CLI
export async function main({argv, env, fetchImpl = globalThis.fetch, now = new Date(), stdout = s => console.log(s)} = {}) {
  const args = new Set(argv.filter(a => a.startsWith('--') && !a.includes('=')));
  const kv = Object.fromEntries(argv.filter(a => a.includes('=')).map(a => a.replace(/^--/, '').split(/=(.*)/s).slice(0, 2)));
  const maxPages = Math.min(Number(kv['max-pages'] ?? LIMITS.defaultMaxPages) || LIMITS.defaultMaxPages, LIMITS.hardMaxPages);
  if (!args.has('--execute')) { // default: plan only. `env` is not touched here.
    stdout(JSON.stringify(buildPlan(now, maxPages), null, 2));
    return {mode: 'plan'};
  }
  const res = await execute({env, fetchImpl, now, out: kv.out, maxPages, log: stdout});
  if (!res.ok) stdout(`STOP ${res.stop}`);
  return {mode: 'execute', ...res};
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const r = await main({argv: process.argv.slice(2), env: process.env});
  if (r.mode === 'execute' && !r.ok) process.exitCode = 2;
}
