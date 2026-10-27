import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sign } from 'node:crypto';
import { createVerifier } from '../node/verify.mjs';
import { assertion, principal, publicKeyPem, otherKey, privateKey, now } from './fixtures.mjs';

function verifier() { return createVerifier({ publicKeyPem, platformId: 'radar', now: () => now }); }

test('valid assertion is accepted once and replay is rejected', () => {
  const verify = verifier();
  const value = principal();
  const header = assertion(value);
  assert.deepEqual(verify(header), value);
  assert.equal(verify(header), null);
});

for (const [name, make] of [
  ['another signing key', () => assertion(principal(), otherKey)],
  ['expired assertion', () => assertion(principal({ expires_at: new Date(now).toISOString() }))],
  ['future issued_at beyond skew', () => assertion(principal({ issued_at: new Date(now + 2001).toISOString(), expires_at: new Date(now + 4000).toISOString() }))],
  ['lifetime over five seconds', () => assertion(principal({ expires_at: new Date(now + 5001).toISOString() }))],
  ['wrong platform', () => assertion(principal({ platform_id: 'jouready' }))],
  ['malformed header', () => 'v1.invalid'],
  ['extra field', () => assertion(principal({ unexpected: true }))],
  ['missing field', () => { const p = principal(); delete p.csrf; return assertion(p); }],
  ['noncanonical JSON', () => {
    const message = `v1.${Buffer.from(JSON.stringify(principal())).toString('base64url')}`;
    return `${message}.${sign(null, Buffer.from(message, 'ascii'), privateKey).toString('base64url')}`;
  }],
]) test(name, () => assert.equal(verifier()(make()), null));

