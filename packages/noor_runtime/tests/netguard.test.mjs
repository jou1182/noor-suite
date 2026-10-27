import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';

const preload = new URL('../node/netguard.mjs', import.meta.url).pathname;
const edition = new URL('../node/edition.mjs', import.meta.url).href;

function run(code, env = {}) {
  return spawnSync(process.execPath, ['--import', preload, '--input-type=module', '-e', code], {
    encoding: 'utf8', env: { ...process.env, ...env }, timeout: 5000,
  });
}

test('edition cannot be changed by environment', () => {
  const result = run(`import { NOOR_EDITION } from ${JSON.stringify(edition)}; if (NOOR_EDITION !== 'hackathon') process.exit(1)`, { NOOR_EDITION: 'cloud' });
  assert.equal(result.status, 0, result.stderr);
});

test('preload rejects remote net.connect and dns.lookup', () => {
  const result = run(`
    import net from 'node:net'; import dns from 'node:dns';
    try { net.connect({ host: '192.0.2.1', port: 80 }); process.exit(1); } catch (e) { if (e.code !== 'ENETGUARD') process.exit(2); }
    dns.lookup('example.com', (e) => process.exit(e?.code === 'ENETGUARD' ? 0 : 3));
  `);
  assert.equal(result.status, 0, result.stderr);
});

test('preload allows loopback names and addresses', () => {
  const result = run(`
    import { assertLoopback } from ${JSON.stringify(edition)};
    for (const host of ['127.0.0.1', '::1', 'localhost', 'radar.noor.localhost']) assertLoopback(host);
    import net from 'node:net';
    for (const host of ['127.0.0.1', '::1', 'localhost', 'radar.noor.localhost']) {
      const socket = net.connect({ host, port: 1 }); socket.on('error', () => {}); socket.destroy();
    }
  `);
  assert.equal(result.status, 0, result.stderr);
});
