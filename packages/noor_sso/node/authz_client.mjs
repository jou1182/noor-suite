import http from 'node:http';
import { isIP } from 'node:net';

function loopback(host) {
  return host === 'localhost' || host === 'noor.localhost' || host.endsWith('.noor.localhost') ||
    host === '::1' || (isIP(host) === 4 && host.split('.')[0] === '127');
}

const decisionFields = new Set(['schema', 'platform_id', 'user_id', 'tender_id', 'action', 'allowed', 'reason', 'decided_at', 'synthetic']);
const reasons = new Set(['ok', 'no_membership', 'viewer_read_only', 'wrong_role', 'tender_not_found', 'expired']);
function validDecision(d) {
  return d && typeof d === 'object' && !Array.isArray(d) && Object.keys(d).length === decisionFields.size &&
    Object.keys(d).every(k => decisionFields.has(k)) && d.schema === 'noor.authz-decision/v1' &&
    typeof d.user_id === 'string' && /^U-[0-9a-f]{8}$/.test(d.user_id) &&
    typeof d.tender_id === 'string' && /^NT-[0-9]{4}-[0-9]{4}$/.test(d.tender_id) &&
    typeof d.action === 'string' && /^[a-z_]{2,40}$/.test(d.action) && typeof d.allowed === 'boolean' &&
    reasons.has(d.reason) && typeof d.decided_at === 'string' && Number.isFinite(Date.parse(d.decided_at)) &&
    d.synthetic === true;
}

export function createAuthzClient({ homeUrl, platformId, timeoutMs = 2000 } = {}) {
  const url = new URL(homeUrl);
  if (url.protocol !== 'http:' || !loopback(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new TypeError('loopback HTTP home URL required');
  }
  if (!/^[a-z_]+$/.test(platformId ?? '')) throw new TypeError('platformId required');
  const keyName = `NOOR_PLATFORM_KEY_${platformId.toUpperCase()}`;
  return function check({ assertion, tender_id, action } = {}) {
    return new Promise(resolve => {
      const deny = { allowed: false };
      const key = process.env[keyName];
      if (!key || typeof assertion !== 'string' || typeof tender_id !== 'string' || typeof action !== 'string') { resolve(deny); return; }
      const body = JSON.stringify({ assertion, tender_id, action });
      const request = http.request(new URL('/internal/authz/check', url), {
        method: 'POST', timeout: timeoutMs,
        headers: { Authorization: `Noor-Platform ${key}`, 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      }, response => {
        let data = '';
        response.setEncoding('utf8');
        response.on('data', chunk => { data += chunk; if (data.length > 16384) response.destroy(); });
        response.on('end', () => {
          try {
            const decision = JSON.parse(data);
            resolve(response.statusCode === 200 && validDecision(decision) &&
              decision.platform_id === platformId && decision.tender_id === tender_id &&
              decision.action === action && decision.allowed === true ? decision : deny);
          } catch { resolve(deny); }
        });
        response.on('error', () => resolve(deny));
      });
      request.on('timeout', () => request.destroy());
      request.on('error', () => resolve(deny));
      request.end(body);
    });
  };
}
