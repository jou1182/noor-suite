import { generateKeyPairSync, sign, randomBytes } from 'node:crypto';

export const { publicKey, privateKey } = generateKeyPairSync('ed25519');
export const otherKey = generateKeyPairSync('ed25519').privateKey;
export const publicKeyPem = publicKey.export({ type: 'spki', format: 'pem' });
export const now = Date.parse('2026-10-27T12:00:00.000Z');

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}

export function principal(changes = {}) {
  return {
    schema: 'noor.principal/v1', platform_id: 'radar', user_id: 'U-1234abcd',
    display_name: 'Synthetic User', role: 'member', platform_permissions: ['read'],
    csrf: 'a'.repeat(43), theme: 'system',
    issued_at: new Date(now).toISOString(), expires_at: new Date(now + 4000).toISOString(),
    nonce: randomBytes(16).toString('base64url'), synthetic: true, ...changes,
  };
}

export function assertion(payload, key = privateKey) {
  const message = `v1.${Buffer.from(canonical(payload)).toString('base64url')}`;
  return `${message}.${sign(null, Buffer.from(message, 'ascii'), key).toString('base64url')}`;
}
