import { timingSafeEqual } from 'node:crypto';

export function safeMethod(method) {
  return ['GET', 'HEAD', 'OPTIONS'].includes(String(method ?? 'GET').toUpperCase());
}

export function validWrite(req, principal, platformOrigin, formToken) {
  const submitted = req.headers['x-csrf-token'] ?? formToken;
  const expected = principal?.csrf;
  if (!platformOrigin || req.headers.origin !== platformOrigin ||
      typeof submitted !== 'string' || typeof expected !== 'string') return false;
  const left = Buffer.from(submitted), right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}
