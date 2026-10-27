import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createVerifier } from '../node/verify.mjs';
import { httpGuard } from '../node/http_guard.mjs';
import { expressGuard } from '../node/express_guard.mjs';
import { createAuthzClient } from '../node/authz_client.mjs';
import { assertion, principal, publicKeyPem, now } from './fixtures.mjs';

const verifier = () => createVerifier({ publicKeyPem, platformId: 'radar', now: () => now });

async function serve(handler, work) {
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try { return await work(`http://127.0.0.1:${server.address().port}`); }
  finally { await new Promise(resolve => server.close(resolve)); }
}

test('node:http guard protects requests and allows exact static paths', async () => {
  let calls = 0;
  await serve(httpGuard((req, res) => { calls++; res.end(req.noorPrincipal?.user_id ?? 'public'); }, {
    verify: verifier(), publicPaths: ['/assets/app.js'],
  }), async base => {
    let r = await fetch(`${base}/private`);
    assert.equal(r.status, 401); assert.equal(await r.text(), '');
    r = await fetch(`${base}/assets/app.js`);
    assert.equal(await r.text(), 'public');
    r = await fetch(`${base}/assets/app.js/other`);
    assert.equal(r.status, 401);
    const header = assertion(principal());
    r = await fetch(`${base}/private`, { headers: { 'X-Noor-Assertion': header } });
    assert.equal(await r.text(), 'U-1234abcd');
    r = await fetch(`${base}/private`, { headers: { 'X-Noor-Assertion': header } });
    assert.equal(r.status, 401);
    assert.equal(calls, 2);
  });
});

test('Express-compatible guard calls next only for valid or public requests', () => {
  const guard = expressGuard({ verify: verifier(), publicPaths: ['/static/app.js'] });
  function invoke(url, header) {
    let next = 0, ended = 0;
    const req = { url, headers: { 'x-noor-assertion': header } };
    const res = { statusCode: 200, end() { ended++; } };
    guard(req, res, () => next++);
    return { next, ended, req, res };
  }
  assert.equal(invoke('/private').res.statusCode, 401);
  assert.equal(invoke('/static/app.js').next, 1);
  const header = assertion(principal());
  const valid = invoke('/private', header);
  assert.equal(valid.next, 1);
  assert.equal(valid.req.noorPrincipal.user_id, 'U-1234abcd');
  assert.equal(invoke('/private', header).res.statusCode, 401);
});

test('guards return an empty 401 if verification throws', async () => {
  await serve(httpGuard(() => assert.fail('handler called'), { verify: () => { throw new Error('internal'); } }), async base => {
    const response = await fetch(`${base}/private`);
    assert.equal(response.status, 401);
    assert.equal(await response.text(), '');
  });
  const guard = expressGuard({ verify: () => { throw new Error('internal'); } });
  let ended = 0;
  const response = { statusCode: 200, end() { ended++; } };
  guard({ url: '/private', headers: {} }, response, () => assert.fail('next called'));
  assert.equal(response.statusCode, 401);
  assert.equal(ended, 1);
});

test('node:http guard rejects direct writes without exact Origin and CSRF', async () => {
  const origin = 'http://radar.noor.localhost:5310';
  await serve(httpGuard((req, res) => res.end('changed'), { verify: payload => principal({ nonce: payload }), platformOrigin: origin }), async base => {
    async function post(headers, body) {
      return fetch(`${base}/private`, { method: 'POST', headers: { 'X-Noor-Assertion': 'synthetic', ...headers }, body });
    }
    assert.equal((await post({}, 'csrf_token=' + 'a'.repeat(43))).status, 403);
    assert.equal((await post({ Origin: 'http://other.localhost:5310', 'X-CSRF-Token': 'a'.repeat(43) })).status, 403);
    assert.equal((await post({ Origin: origin, 'X-CSRF-Token': 'wrong' })).status, 403);
    assert.equal((await post({ Origin: origin, 'X-CSRF-Token': 'a'.repeat(43) })).status, 200);
    assert.equal((await post({ Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' }, 'csrf_token=' + 'a'.repeat(43))).status, 200);
  });
});

test('Express guard rejects direct writes without exact Origin and CSRF', () => {
  const origin = 'http://radar.noor.localhost:5310';
  const guard = expressGuard({ verify: () => principal(), platformOrigin: origin });
  function write(headers = {}, body = {}) {
    let called = false;
    const req = { url: '/private', method: 'POST', headers: { 'x-noor-assertion': 'synthetic', ...headers }, body };
    const res = { statusCode: 200, end() {} };
    guard(req, res, () => { called = true; });
    return { called, status: res.statusCode };
  }
  assert.equal(write().status, 403);
  assert.equal(write({ origin: 'http://other.localhost:5310', 'x-csrf-token': 'a'.repeat(43) }).status, 403);
  assert.equal(write({ origin, 'x-csrf-token': 'wrong' }).status, 403);
  assert.equal(write({ origin, 'x-csrf-token': 'a'.repeat(43) }).called, true);
  assert.equal(write({ origin }, { csrf_token: 'a'.repeat(43) }).called, true);
});

test('authorization client posts the contract and fails closed', async () => {
  const old = process.env.NOOR_PLATFORM_KEY_RADAR;
  process.env.NOOR_PLATFORM_KEY_RADAR = 'synthetic-test-key';
  let received;
  try {
    await serve(async (req, res) => {
      let body = '';
      for await (const chunk of req) body += chunk;
      received = { url: req.url, auth: req.headers.authorization, body: JSON.parse(body) };
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ schema: 'noor.authz-decision/v1', platform_id: 'radar', user_id: 'U-1234abcd', tender_id: 'NT-2026-0001', action: 'read', allowed: true, reason: 'ok', decided_at: new Date(now).toISOString(), synthetic: true }));
    }, async homeUrl => {
      const check = createAuthzClient({ homeUrl, platformId: 'radar' });
      const result = await check({ assertion: 'test-assertion', tender_id: 'NT-2026-0001', action: 'read' });
      assert.equal(result.allowed, true);
      assert.deepEqual(received, { url: '/internal/authz/check', auth: 'Noor-Platform synthetic-test-key', body: { assertion: 'test-assertion', tender_id: 'NT-2026-0001', action: 'read' } });
      assert.equal((await check({ assertion: 'test-assertion', tender_id: 'NT-2026-9999', action: 'read' })).allowed, false);
    });
    assert.throws(() => createAuthzClient({ homeUrl: 'http://example.com', platformId: 'radar' }));
    const unreachable = createAuthzClient({ homeUrl: 'http://127.0.0.1:1', platformId: 'radar' });
    assert.equal((await unreachable({ assertion: 'x', tender_id: 'NT-2026-0001', action: 'read' })).allowed, false);
  } finally {
    if (old === undefined) delete process.env.NOOR_PLATFORM_KEY_RADAR;
    else process.env.NOOR_PLATFORM_KEY_RADAR = old;
  }
});
