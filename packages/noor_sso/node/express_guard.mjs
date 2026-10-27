import { safeMethod, validWrite } from './write_guard.mjs';

export function expressGuard({ verify, publicPaths = [], platformOrigin } = {}) {
  if (typeof verify !== 'function') throw new TypeError('verify required');
  const allowed = new Set(publicPaths);
  return function guard(req, res, next) {
    let path;
    try { path = new URL(req.originalUrl ?? req.url, 'http://localhost').pathname; } catch { path = null; }
    if (path !== null && allowed.has(path)) return next();
    let principal;
    try { principal = verify(req.headers['x-noor-assertion']); } catch { principal = null; }
    if (!principal) { res.statusCode = 401; res.end(); return; }
    if (!safeMethod(req.method) && !validWrite(req, principal, platformOrigin, req.body?.csrf_token)) {
      res.statusCode = 403; res.end(); return;
    }
    req.noorPrincipal = principal;
    return next();
  };
}
