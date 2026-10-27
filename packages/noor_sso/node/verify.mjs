import { createPublicKey, verify as verifySignature } from 'node:crypto';
import { readFileSync } from 'node:fs';

const fields = new Set(['schema', 'platform_id', 'user_id', 'display_name', 'role', 'platform_permissions', 'csrf', 'theme', 'issued_at', 'expires_at', 'nonce', 'synthetic']);
const platforms = new Set(['nmis_full', 'radar', 'quick_analysis', 'atpas', 'jouready']);
const roles = new Set(['proposal_manager', 'review_approver', 'member', 'viewer']);
const permissions = new Set(['read', 'send_candidate', 'upload_analyze', 'read_report', 'full', 'accept_tender', 'approve_gaps', 'own_tasks', 'build', 'read_outputs', 'run_review', 'approve_report']);
const themes = new Set(['system', 'light', 'dark']);
const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}

function validDate(value) {
  return typeof value === 'string' && iso.test(value) && Number.isFinite(Date.parse(value));
}

function validPrincipal(p) {
  return p !== null && typeof p === 'object' && !Array.isArray(p) &&
    Object.keys(p).length === fields.size && Object.keys(p).every(k => fields.has(k)) &&
    p.schema === 'noor.principal/v1' && platforms.has(p.platform_id) &&
    typeof p.user_id === 'string' && /^U-[0-9a-f]{8}$/.test(p.user_id) &&
    typeof p.display_name === 'string' && p.display_name.length >= 1 && p.display_name.length <= 120 &&
    roles.has(p.role) && Array.isArray(p.platform_permissions) && p.platform_permissions.length <= 20 &&
    p.platform_permissions.every(x => permissions.has(x)) && new Set(p.platform_permissions).size === p.platform_permissions.length &&
    typeof p.csrf === 'string' && /^[A-Za-z0-9_-]{43}$/.test(p.csrf) &&
    themes.has(p.theme) && validDate(p.issued_at) && validDate(p.expires_at) &&
    typeof p.nonce === 'string' && /^[A-Za-z0-9_-]{22}$/.test(p.nonce) && p.synthetic === true;
}

export function createVerifier({ publicKeyPem, platformId, now = Date.now } = {}) {
  if (!platforms.has(platformId)) throw new TypeError('valid platformId required');
  const pem = publicKeyPem ?? readFileSync(process.env.NOOR_HOME_PUBLIC_KEY_FILE);
  if (!String(pem).includes('-----BEGIN PUBLIC KEY-----')) throw new TypeError('public key PEM required');
  const key = createPublicKey(pem);
  if (key.asymmetricKeyType !== 'ed25519') throw new TypeError('Ed25519 public key required');
  const seen = new Map();
  return function verify(header) {
    try {
      if (typeof header !== 'string') return null;
      const parts = /^v1\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/.exec(header);
      if (!parts) return null;
      const payloadBytes = Buffer.from(parts[1], 'base64url');
      const sig = Buffer.from(parts[2], 'base64url');
      if (payloadBytes.toString('base64url') !== parts[1] || sig.toString('base64url') !== parts[2] || sig.length !== 64) return null;
      if (!verifySignature(null, Buffer.from(`v1.${parts[1]}`, 'ascii'), key, sig)) return null;
      const payload = JSON.parse(payloadBytes.toString('utf8'));
      if (canonical(payload) !== payloadBytes.toString('utf8') || !validPrincipal(payload)) return null;
      if (payload.platform_id !== platformId) return null;
      const clock = now();
      const issued = Date.parse(payload.issued_at), expires = Date.parse(payload.expires_at);
      if (issued > clock + 2000 || clock >= expires || expires < issued || expires - issued > 5000) return null;
      for (const [nonce, end] of seen) if (end <= clock) seen.delete(nonce);
      if (seen.has(payload.nonce)) return null;
      seen.set(payload.nonce, expires);
      return payload;
    } catch { return null; }
  };
}
