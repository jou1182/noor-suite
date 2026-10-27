'use strict';

/**
 * Demo guard: refuse non-loopback network access when NOOR_NETGUARD=1.
 *
 * Load it with:
 *   NOOR_NETGUARD=1 NODE_OPTIONS="--require /abs/path/no_network.cjs" node ...
 *
 * It wraps net.Socket.prototype.connect, dns.lookup, dns.promises.lookup and
 * dgram.Socket.prototype.send.  Loopback (127.0.0.0/8, ::1, "localhost") and
 * IPC / unix-socket paths stay allowed.
 *
 * This is a demo guard for local test runs - it is not a security sandbox.
 */

const dns = require('dns');
const dgram = require('dgram');
const net = require('net');

const GUARD_MESSAGE = 'network blocked by Noor guard';
const GUARD_CODE = 'ENETGUARD';
const PATCH_FLAG = '__noorNetguardPatched';

const originalConnect = net.Socket.prototype.connect;
const originalLookup = dns.lookup;
const dnsPromises = dns.promises;
const originalPromiseLookup = dnsPromises.lookup;
const originalSend = dgram.Socket.prototype.send;

function isLoopbackIPv4(value) {
  const parts = value.split('.');
  if (parts.length !== 4) return false;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return false;
    if (Number(part) > 255) return false;
  }
  return parts[0] === '127';
}

function isLoopbackHost(host) {
  if (host === undefined || host === null) return true;
  let value = String(host).trim().toLowerCase();
  if (value === '') return true;
  if (value.startsWith('[') && value.endsWith(']')) value = value.slice(1, -1);
  const zone = value.indexOf('%');
  if (zone !== -1) value = value.slice(0, zone);
  if (value === 'localhost') return true;
  if (value === '::1' || value === '0:0:0:0:0:0:0:1') return true;
  if (isLoopbackIPv4(value)) return true;
  const mapped = /^::ffff:(.+)$/.exec(value);
  if (mapped) return isLoopbackIPv4(mapped[1]);
  return false;
}

function createGuardError(syscall) {
  const error = new Error(GUARD_MESSAGE);
  error.code = GUARD_CODE;
  error.errno = -1;
  error.syscall = syscall || 'connect';
  return error;
}

/**
 * Describe the destination of a net.Socket#connect() call.
 *
 * Supported argument forms:
 *   connect(port, host)      -> { host }
 *   connect(options)         -> { host, path }
 *   connect(path)            -> { path }  (IPC / unix socket)
 * plus the internal normalizeArgs() form connect([options, callback]).
 */
function describeTarget(args) {
  let first = args[0];
  if (Array.isArray(first)) {
    // normalizeArgs() form: [options, callback]
    first = Array.isArray(first[0]) ? first[0][0] : first[0];
  }
  if (first && typeof first === 'object') {
    return { host: first.host, path: first.path };
  }
  if (typeof first === 'number') {
    const host = typeof args[1] === 'string' ? args[1] : undefined;
    return { host, path: undefined };
  }
  if (typeof first === 'string') {
    // (path[, callback]) - IPC / unix domain socket
    return { host: undefined, path: first };
  }
  return { host: undefined, path: undefined };
}

/**
 * Describe the destination of a dgram.Socket#send() call.
 * Supported forms: send(msg, port, address) and
 * send(msg, offset, length, port, address).
 */
function describeDatagramTarget(args) {
  const rest = args.slice(1);
  if (rest.length >= 2 && typeof rest[0] === 'number' && typeof rest[1] === 'number') {
    return { port: rest[2], address: rest[3] };
  }
  if (rest.length >= 1 && typeof rest[0] === 'number') {
    return { port: rest[0], address: rest[1] };
  }
  return { port: undefined, address: undefined };
}

function guardedConnect(...args) {
  const target = describeTarget(args);
  if (target.path === undefined && !isLoopbackHost(target.host)) {
    throw createGuardError('connect');
  }
  return originalConnect.apply(this, args);
}

function guardedLookup(hostname, options, callback) {
  const done = typeof options === 'function' ? options : callback;
  if (!isLoopbackHost(hostname)) {
    const error = createGuardError('getaddrinfo');
    if (typeof done === 'function') {
      process.nextTick(done, error);
      return undefined;
    }
    throw error;
  }
  return originalLookup.apply(this, arguments);
}

function guardedPromiseLookup(hostname, options) {
  if (!isLoopbackHost(hostname)) {
    return Promise.reject(createGuardError('getaddrinfo'));
  }
  return originalPromiseLookup.apply(this, arguments);
}

function guardedSend(...args) {
  const target = describeDatagramTarget(args);
  if (target.address !== undefined && !isLoopbackHost(target.address)) {
    throw createGuardError('send');
  }
  return originalSend.apply(this, args);
}

function install() {
  if (net.Socket.prototype.connect[PATCH_FLAG]) return false;
  guardedConnect[PATCH_FLAG] = true;
  guardedLookup[PATCH_FLAG] = true;
  guardedSend[PATCH_FLAG] = true;

  net.Socket.prototype.connect = guardedConnect;
  dns.lookup = guardedLookup;
  dnsPromises.lookup = guardedPromiseLookup;
  dgram.Socket.prototype.send = guardedSend;
  return true;
}

if (process.env.NOOR_NETGUARD === '1') {
  install();
}

module.exports = { install, isLoopbackHost };
