// node --test test_offline.mjs   -- synthetic responses only; no network, no real credentials. Not an API success test.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {main, execute, buildPlan, buildUrl, nyWallToUtcMs, isoZ, rfc3339ToNs, analyze, nyLabel, LIMITS} from './alpaca_fetch.mjs';

const SECRET = 'TESTSECRET_not_real_9f3a', KEYID = 'TESTKEYID_not_real_41b2';
const ENV = {APCA_API_KEY_ID: KEYID, APCA_API_SECRET_KEY: SECRET};
const NOW = new Date('2026-10-26T12:00:00Z');
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'alp-'));
const resp = (status, body = {}, raw) => ({status, arrayBuffer: async () => Buffer.from(raw ?? JSON.stringify(body))});
const mkFetch = handler => { const calls = []; const f = async (url, opts) => { calls.push({url, opts}); return handler(url, opts, calls.length); }; f.calls = calls; return f; };
const bar = (t, extra = {}) => ({t, o: 1, h: 2, l: 0.5, c: 1.5, v: 10, n: 3, vw: 1.2, ...extra});
const okHandler = url => {
  const u = new URL(url);
  if (u.pathname.endsWith('quotes')) return resp(200, {quotes: {SOXL: [{t: '2024-10-07T13:30:00.000000001Z', bp: 1, bs: 1, ap: 2, as: 1}]}, next_page_token: null});
  return resp(200, {bars: {SOXL: [bar('2024-10-07T13:30:00Z')]}, next_page_token: null});
};
const capture = async (argv, env, fetchImpl, now = NOW) => { const out = []; const r = await main({argv, env, fetchImpl, now, stdout: s => out.push(s)}); return {r, out}; };

test('plan mode: no network and credentials never read', async () => {
  let reads = 0;
  const env = new Proxy({}, {get() { reads++; return undefined; }, ownKeys() { reads++; return []; }, has() { reads++; return false; }});
  const f = mkFetch(() => { throw new Error('network must not be used'); });
  for (const argv of [[], ['--plan']]) {
    const {r, out} = await capture(argv, env, f);
    assert.equal(r.mode, 'plan');
    const plan = JSON.parse(out.join('\n'));
    assert.equal(plan.requests.length, 8 + 2 + 2);
    assert.ok(plan.requests.every(x => x.feed === 'sip'));
    assert.equal(plan.network_in_plan_mode, 0);
  }
  assert.equal(f.calls.length, 0); assert.equal(reads, 0);
});

test('plan content: fixed dates only, bars 09:29-09:37 ET, quotes 09:29:59-09:36:30 ET', () => {
  const p = buildPlan(NOW);
  assert.deepEqual(p.requests.filter(r => r.id.startsWith('daily')).map(r => r.date), ['2024-10-07', '2024-12-20', '2026-06-30', '2026-07-01', '2026-07-29', '2026-07-30', '2026-07-31', '2026-08-10']);
  const m = p.requests.filter(r => r.id.startsWith('bars1m')), q = p.requests.filter(r => r.kind === 'quotes');
  assert.deepEqual(m.map(r => r.date), ['2024-10-07', '2026-07-01']); assert.deepEqual(q.map(r => r.date), ['2024-10-07', '2026-07-01']);
  assert.ok(m.every(r => r.start_ny.includes('T09:29:00') && r.end_ny.includes('T09:37:00') && r.timeframe === '1Min'));
  assert.ok(q.every(r => r.start_ny.includes('T09:29:59') && r.end_ny.includes('T09:36:30')));
  assert.ok(p.requests.every(r => r.age_ok_at_plan_time));
});

test('DST: EDT/EST and transition days convert correctly', () => {
  assert.equal(isoZ(nyWallToUtcMs('2024-10-07', 9, 30, 0)), '2024-10-07T13:30:00Z'); // EDT
  assert.equal(isoZ(nyWallToUtcMs('2024-12-20', 9, 30, 0)), '2024-12-20T14:30:00Z'); // EST
  assert.equal(isoZ(nyWallToUtcMs('2026-03-09', 9, 30, 0)), '2026-03-09T13:30:00Z'); // first day after spring forward (2026-03-08)
  assert.equal(isoZ(nyWallToUtcMs('2026-03-06', 9, 30, 0)), '2026-03-06T14:30:00Z');
  assert.equal(isoZ(nyWallToUtcMs('2026-11-02', 9, 30, 0)), '2026-11-02T14:30:00Z'); // after fall back (2026-11-01)
  assert.equal(isoZ(nyWallToUtcMs('2026-10-30', 9, 30, 0)), '2026-10-30T13:30:00Z');
  assert.equal(nyLabel(Date.parse('2024-12-20T14:30:00Z')), '2024-12-20T09:30:00-05:00');
});

test('execute refuses before any network when preconditions fail', async () => {
  const f = mkFetch(okHandler);
  const out = path.join(tmp(), 'o');
  let r = await execute({env: {}, fetchImpl: f, now: NOW, out, maxPages: 2}); assert.equal(r.stop, 'MISSING_CREDENTIALS_ENV');
  r = await execute({env: ENV, fetchImpl: f, now: NOW, out: undefined, maxPages: 2}); assert.equal(r.stop, 'OUT_DIR_REQUIRED');
  r = await execute({env: ENV, fetchImpl: f, now: NOW, out: path.join(path.dirname(new URL(import.meta.url).pathname), 'raw_out'), maxPages: 2}); assert.equal(r.stop, 'OUT_DIR_INSIDE_GIT_WORKTREE_REFUSED');
  const nonEmpty = tmp(); fs.writeFileSync(path.join(nonEmpty, 'x'), '1');
  r = await execute({env: ENV, fetchImpl: f, now: NOW, out: nonEmpty, maxPages: 2}); assert.equal(r.stop, 'OUT_DIR_NOT_EMPTY_REFUSED');
  r = await execute({env: ENV, fetchImpl: f, now: new Date('2026-08-10T21:00:00Z'), out: path.join(tmp(), 'o2'), maxPages: 2}); assert.equal(r.stop, 'END_NOT_15_MINUTES_OLD'); // 2026-08-10 daily end is 20:00Z+3:59 ET > now-15min
  assert.equal(f.calls.length, 0);
});

test('happy path with synthetic responses: sip only, headers set, manifest sha256 over received bytes, no secret in outputs', async () => {
  const f = mkFetch(okHandler), dir = path.join(tmp(), 'o'), logs = [];
  const r = await execute({env: ENV, fetchImpl: f, now: NOW, out: dir, maxPages: 3, log: s => logs.push(s)});
  assert.equal(r.ok, true); assert.equal(f.calls.length, 12);
  for (const c of f.calls) {
    const u = new URL(c.url);
    assert.equal(u.origin, 'https://data.alpaca.markets'); assert.equal(u.searchParams.get('feed'), 'sip');
    assert.equal(c.opts.method, 'GET'); assert.equal(c.opts.redirect, 'manual'); assert.ok(c.opts.signal);
    assert.equal(c.opts.headers['APCA-API-KEY-ID'], KEYID);
    assert.ok(['/v2/stocks/bars', '/v2/stocks/quotes'].includes(u.pathname));
  }
  const man = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  for (const e of man.requests) for (const p of e.pages) {
    assert.equal(p.sha256, crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, p.file))).digest('hex'));
  }
  for (const f2 of fs.readdirSync(dir, {recursive: true})) {
    const full = path.join(dir, f2); if (fs.statSync(full).isFile()) { const t = fs.readFileSync(full, 'utf8'); assert.ok(!t.includes(SECRET) && !t.includes(KEYID), f2); }
  }
  assert.ok(!logs.join('').includes(SECRET));
  // second run into the same dir is refused (no overwrite)
  const r2 = await execute({env: ENV, fetchImpl: f, now: NOW, out: dir, maxPages: 3}); assert.equal(r2.stop, 'OUT_DIR_NOT_EMPTY_REFUSED');
});

const stopCases = [
  ['429', () => resp(429, {message: 'SECRET-BODY ' + SECRET}), 'HTTP_429_RATE_LIMIT'],
  ['401', () => resp(401, {message: 'x'}), 'HTTP_401_AUTH'],
  ['403 (no iex fallback)', () => resp(403, {message: 'subscription does not permit querying recent SIP data'}), 'HTTP_403_FORBIDDEN'],
  ['500', () => resp(500, {}), 'HTTP_500'],
  ['redirect', () => resp(302, {}), 'REDIRECT_REFUSED'],
  ['timeout', () => { const e = new Error('t'); e.name = 'TimeoutError'; throw e; }, 'TIMEOUT'],
  ['network error', () => { throw new Error('boom ' + SECRET); }, 'NETWORK_ERROR'],
  ['bad json', () => resp(200, null, '<html>not json</html>'), 'BAD_JSON'],
];
for (const [name, handler, expected] of stopCases) {
  test(`stops on ${name} after exactly one request, fixed message, no body/secret leak, never switches feed`, async () => {
    const f = mkFetch(handler), dir = path.join(tmp(), 'o'), logs = [];
    const {r, out} = await capture(['--execute', `--out=${dir}`], ENV, f);
    assert.equal(r.ok, false); assert.equal(r.stop, expected);
    assert.equal(f.calls.length, 1);
    assert.ok(f.calls.every(c => new URL(c.url).searchParams.get('feed') === 'sip'));
    const all = out.join('\n') + fs.readdirSync(dir, {recursive: true}).map(x => { const p = path.join(dir, x); return fs.statSync(p).isFile() ? fs.readFileSync(p, 'utf8') : ''; }).join('\n');
    assert.ok(!all.includes(SECRET) && !all.includes('SECRET-BODY') && !all.includes('subscription does not permit'));
    const man = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8')); assert.equal(man.stop, expected);
  });
}

test('page cap: endless next_page_token ends at cap and is marked incomplete', async () => {
  const f = mkFetch(url => resp(200, {quotes: {SOXL: [{t: '2024-10-07T13:30:00Z', bp: 1, bs: 1, ap: 2, as: 1}]}, bars: {SOXL: [bar('2024-10-07T13:30:00Z')]}, next_page_token: 'tok'}));
  const dir = path.join(tmp(), 'o'); const r = await execute({env: ENV, fetchImpl: f, now: NOW, out: dir, maxPages: 2});
  const man = r.manifest, q = man.requests.find(x => x.id === 'quotes_2024-10-07');
  assert.equal(q.pages.length, 2); assert.equal(q.complete, false); assert.equal(q.incomplete_reason, 'PAGE_CAP_REACHED');
  const d = man.requests.find(x => x.id === 'daily_2024-10-07'); assert.equal(d.pages.length, 1); assert.equal(d.complete, false);
  const m = main; assert.ok(LIMITS.hardMaxPages >= 2 && m);
});

test('missing values stay missing: no zero/previous-value fill; raw values preserved', () => {
  const r = buildPlan(NOW).requests.find(x => x.id === 'bars1m_2024-10-07');
  const items = [bar('2024-10-07T13:29:00Z'), {t: '2024-10-07T13:30:00Z', o: 1, h: 2, l: 0.5, v: 5}, bar('2024-10-07T13:37:00Z')]; // 09:30 bar lacks c; 09:31..09:36 absent; 09:37 end boundary present
  const a = analyze(r, items);
  assert.deepEqual(a.missing_fields, [{index: 1, missing: ['c']}]);
  assert.deepEqual(a.expected_minutes_missing, ['09:31', '09:32', '09:33', '09:34', '09:35', '09:36']);
  assert.equal(a.end_boundary_bar_present, true);
  assert.equal(items[1].c, undefined);
});

test('quote timestamps keep nanosecond precision and order violations are detected', () => {
  const a = rfc3339ToNs('2026-07-01T13:30:00.123456789Z'), b = rfc3339ToNs('2026-07-01T13:30:00.123456788Z');
  assert.ok(a > b); assert.equal(rfc3339ToNs('garbage'), null);
  const r = buildPlan(NOW).requests.find(x => x.id === 'quotes_2026-07-01');
  const q = (t) => ({t, bp: 1, bs: 1, ap: 2, as: 1});
  const res = analyze(r, [q('2026-07-01T13:30:00.123456789Z'), q('2026-07-01T13:30:00.123456788Z'), q('2026-07-01T13:40:00Z'), q('xx')]);
  assert.equal(res.out_of_order, 1); assert.equal(res.outside_window, 1); assert.equal(res.anomalies[0].issue, 'BAD_TIMESTAMP');
  assert.match(res.note, /UNCONFIRMED/);
});

test('URL allowlist: only data.alpaca.markets bars/quotes; no trading/latest/stream paths', () => {
  const r = buildPlan(NOW).requests[0];
  assert.throws(() => buildUrl({...r, endpoint: '/v2/account'}), /URL_NOT_ALLOWED/);
  assert.throws(() => buildUrl({...r, endpoint: '/v2/stocks/bars/latest'}), /URL_NOT_ALLOWED/);
  assert.equal(buildUrl(r).searchParams.get('feed'), 'sip');
});
