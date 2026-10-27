import { Readable } from 'node:stream';
import { safeMethod, validWrite } from './write_guard.mjs';

export function httpGuard(handler, { verify, publicPaths = [], platformOrigin } = {}) {
  if (typeof handler !== 'function' || typeof verify !== 'function') throw new TypeError('handler and verify required');
  const allowed = new Set(publicPaths);
  return async function guarded(req, res) {
    let path;
    try { path = new URL(req.url, 'http://localhost').pathname; } catch { path = null; }
    if (path !== null && allowed.has(path)) return handler(req, res);
    let principal;
    try { principal = verify(req.headers['x-noor-assertion']); } catch { principal = null; }
    if (!principal) { res.writeHead(401); res.end(); return; }
    req.noorPrincipal = principal;
    if (!safeMethod(req.method)) {
      if (req.headers['x-csrf-token'] !== undefined) {
        if (!validWrite(req, principal, platformOrigin, null)) {
          res.writeHead(403); res.end(); return;
        }
        return handler(req, res);
      }
      let raw = Buffer.alloc(0);
      try {
        for await (const chunk of req) {
          raw = Buffer.concat([raw, chunk]);
          if (raw.length > 65536) { res.writeHead(413); res.end(); return; }
        }
      } catch { res.writeHead(403); res.end(); return; }
      const formToken = req.headers['content-type']?.split(';')[0] === 'application/x-www-form-urlencoded'
        ? new URLSearchParams(raw.toString('utf8')).get('csrf_token') : null;
      if (!validWrite(req, principal, platformOrigin, formToken)) {
        res.writeHead(403); res.end(); return;
      }
      const forwarded = Readable.from([raw]);
      forwarded.headers = req.headers;
      forwarded.method = req.method;
      forwarded.url = req.url;
      forwarded.noorPrincipal = principal;
      return handler(forwarded, res);
    }
    return handler(req, res);
  };
}
