import { isIP } from 'node:net';

export const NOOR_EDITION = 'hackathon';

export function isLoopbackHost(host) {
  if (typeof host !== 'string') return false;
  const value = host.toLowerCase();
  if (value === 'localhost' || value === 'noor.localhost' || /^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.noor\.localhost$/.test(value)) return true;
  if (value === '::1' || value === '0:0:0:0:0:0:0:1') return true;
  if (isIP(value) === 4) return value.split('.')[0] === '127';
  if (value.startsWith('::ffff:')) return isLoopbackHost(value.slice(7));
  return false;
}

export function assertLoopback(urlOrHost) {
  if (typeof urlOrHost !== 'string' || !urlOrHost || urlOrHost.trim() !== urlOrHost) throw new TypeError('loopback address required');
  let host = urlOrHost;
  if (urlOrHost.includes('://')) {
    const url = new URL(urlOrHost);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new TypeError('loopback URL required');
    host = url.hostname;
  } else if (/[/@?#]/.test(host)) throw new TypeError('loopback host required');
  if (host.startsWith('[') && host.endsWith(']')) host = host.slice(1, -1);
  if (!isLoopbackHost(host)) throw new TypeError('non-loopback address');
  return urlOrHost;
}
