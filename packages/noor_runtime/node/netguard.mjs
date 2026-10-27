/** Load with `node --import ./packages/noor_runtime/node/netguard.mjs ...`. */
import net from 'node:net';
import dns from 'node:dns';
import { isLoopbackHost } from './edition.mjs';

const marker = Symbol.for('noor.runtime.netguard');
const blocked = syscall => Object.assign(new Error('network blocked by Noor guard'), { code: 'ENETGUARD', syscall });

if (!net.Socket.prototype.connect[marker]) {
  const connect = net.Socket.prototype.connect;
  function guardedConnect(...args) {
    let first = args[0];
    if (Array.isArray(first)) first = first[0];
    let host;
    if (first && typeof first === 'object') {
      if (first.path !== undefined) return connect.apply(this, args);
      host = first.host ?? 'localhost';
    } else if (typeof first === 'number') host = typeof args[1] === 'string' ? args[1] : 'localhost';
    else if (typeof first === 'string') return connect.apply(this, args); // IPC path
    else throw blocked('connect');
    if (!isLoopbackHost(host)) throw blocked('connect');
    return connect.apply(this, args);
  }
  guardedConnect[marker] = true;
  net.Socket.prototype.connect = guardedConnect;

  const lookup = dns.lookup;
  dns.lookup = function guardedLookup(host, options, callback) {
    if (!isLoopbackHost(host)) {
      const error = blocked('getaddrinfo');
      const done = typeof options === 'function' ? options : callback;
      if (typeof done === 'function') { process.nextTick(done, error); return; }
      throw error;
    }
    return lookup.apply(this, arguments);
  };
  const promiseLookup = dns.promises.lookup;
  dns.promises.lookup = function guardedPromiseLookup(host, options) {
    if (!isLoopbackHost(host)) return Promise.reject(blocked('getaddrinfo'));
    return promiseLookup.call(this, host, options);
  };
}
