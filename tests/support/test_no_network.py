"""Self-tests for the demo network guard.

The guard has to fire *before* any packet leaves the machine, so every
"remote" destination used here is an unroutable address inside 10.0.0.0/8.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REMOTE_HOST = "10.255.255.1"
REMOTE_PORT = 9
TIMEOUT = 30

PY_CONNECT_BLOCKED = """
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    sock.connect((sys.argv[1], int(sys.argv[2])))
except PermissionError as exc:
    print("BLOCKED", exc)
    raise SystemExit(0)
except OSError as exc:
    print("OTHER", type(exc).__name__, exc)
    raise SystemExit(2)
print("NOT BLOCKED")
raise SystemExit(3)
"""

PY_RESOLVE_BLOCKED = """
import socket, sys
try:
    socket.getaddrinfo(sys.argv[1], 80)
except PermissionError as exc:
    print("BLOCKED", exc)
    raise SystemExit(0)
except OSError as exc:
    print("OTHER", type(exc).__name__, exc)
    raise SystemExit(2)
print("NOT BLOCKED")
raise SystemExit(3)
"""

PY_LOOPBACK_OK = """
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect((sys.argv[1], int(sys.argv[2])))
sock.sendall(b"ping")
data = sock.recv(64)
sock.close()
print("OK" if data == b"ping" else "BAD-ECHO")
raise SystemExit(0 if data == b"ping" else 2)
"""

PY_GRANDCHILD = """
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
try:
    sock.connect((sys.argv[1], int(sys.argv[2])))
except PermissionError as exc:
    print("BLOCKED", exc)
    raise SystemExit(0)
print("NOT BLOCKED")
raise SystemExit(3)
"""

PY_NESTED = (
    "import os, subprocess, sys\n"
    "script = %r\n"
    "result = subprocess.run([sys.executable, '-c', script, *sys.argv[1:]],\n"
    "                      env=os.environ.copy(), capture_output=True,\n"
    "                      text=True, timeout=30)\n"
    "print('nested', result.stdout.strip())\n"
    "if result.returncode != 0:\n"
    "    print(result.stderr.strip())\n"
    "raise SystemExit(result.returncode)\n" % (PY_GRANDCHILD,)
)

PY_INERT = """
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.close()
try:
    socket.getaddrinfo("localhost", 80)
except PermissionError as exc:
    print("BLOCKED", exc)
    raise SystemExit(2)
except OSError:
    pass
print("OK")
"""

NODE_CHILD_SCRIPT = r"""
'use strict';
const dns = require('dns');
const net = require('net');

const mode = process.argv[2];
const host = process.argv[3];
const port = Number(process.argv[4]);

function isGuardError(err) {
  if (!err) return false;
  if (err.code === 'ENETGUARD') return true;
  return String(err.message || '').indexOf('Noor guard') !== -1;
}

function blocked(err) {
  if (isGuardError(err)) {
    console.log('BLOCKED');
    process.exit(0);
  }
  console.log('OTHER ' + (err && err.code) + ' ' + (err && err.message));
  process.exit(2);
}

if (mode === 'blocked') {
  let sock = null;
  try {
    sock = net.connect(port, host);
  } catch (err) {
    blocked(err);
  }
  if (sock) {
    sock.setTimeout(5000, function () {
      console.log('NOT BLOCKED');
      process.exit(3);
    });
    sock.on('error', blocked);
    sock.on('connect', function () {
      console.log('NOT BLOCKED');
      process.exit(3);
    });
  }
} else if (mode === 'loopback') {
  const sock = net.connect(port, host);
  sock.setTimeout(10000, function () {
    console.log('OTHER timeout');
    process.exit(4);
  });
  sock.on('connect', function () {
    console.log('OK');
    sock.destroy();
    process.exit(0);
  });
  sock.on('error', function (err) {
    console.log('OTHER ' + (err && err.code) + ' ' + (err && err.message));
    process.exit(4);
  });
} else if (mode === 'dns') {
  dns.lookup(host, function (err) {
    if (isGuardError(err)) {
      console.log('BLOCKED ' + err.code);
      process.exit(0);
    }
    console.log('OTHER ' + (err && err.code) + ' ' + (err && err.message));
    process.exit(5);
  });
} else {
  console.log('OTHER unknown-mode');
  process.exit(6);
}
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def run_python(script: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        env=env,
        timeout=TIMEOUT,
        capture_output=True,
        text=True,
    )


def run_node(node: str, script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [node, str(script), *args],
        env=env,
        timeout=TIMEOUT,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def loopback_server():
    """A tiny echo server bound to 127.0.0.1 on an ephemeral port."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    host, port = server.getsockname()
    stop = threading.Event()

    def serve() -> None:
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(5)
                try:
                    conn.sendall(conn.recv(64))
                except OSError:
                    pass

    worker = threading.Thread(target=serve, name="loopback-echo", daemon=True)
    worker.start()
    try:
        yield host, port
    finally:
        stop.set()
        worker.join(timeout=5)
        server.close()


@pytest.fixture
def node_executable() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node executable not found")
    return node


@pytest.fixture
def node_script(tmp_path: Path) -> Path:
    script = tmp_path / "guard_child.cjs"
    script.write_text(NODE_CHILD_SCRIPT, encoding="utf-8")
    return script


# ---------------------------------------------------------------------------
# python side
# ---------------------------------------------------------------------------
def test_python_child_blocks_remote_connect(guarded_env):
    result = run_python(PY_CONNECT_BLOCKED, guarded_env, REMOTE_HOST, str(REMOTE_PORT))
    assert result.returncode == 0, result.stderr
    assert "BLOCKED" in result.stdout
    assert "network blocked by Noor guard" in result.stdout


def test_python_child_blocks_dns_resolution(guarded_env):
    result = run_python(PY_RESOLVE_BLOCKED, guarded_env, "example.org")
    assert result.returncode == 0, result.stderr
    assert "BLOCKED" in result.stdout
    assert "network blocked by Noor guard" in result.stdout


def test_python_child_reaches_loopback_server(guarded_env, loopback_server):
    host, port = loopback_server
    result = run_python(PY_LOOPBACK_OK, guarded_env, host, str(port))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_grandchild_process_is_guarded_too(guarded_env):
    result = run_python(PY_NESTED, guarded_env, REMOTE_HOST, str(REMOTE_PORT))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nested" in result.stdout
    assert "BLOCKED" in result.stdout


def test_guard_is_inert_without_the_env_flag(guarded_env):
    env = dict(guarded_env)
    env.pop("NOOR_NETGUARD", None)
    result = run_python(PY_INERT, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
    assert "BLOCKED" not in result.stdout


# ---------------------------------------------------------------------------
# node side
# ---------------------------------------------------------------------------
def test_node_child_blocks_remote_connect(guarded_env, node_executable, node_script):
    result = run_node(node_executable, node_script, guarded_env, "blocked", REMOTE_HOST, str(REMOTE_PORT))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout


def test_node_child_reaches_loopback_server(guarded_env, node_executable, node_script, loopback_server):
    host, port = loopback_server
    result = run_node(node_executable, node_script, guarded_env, "loopback", host, str(port))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_node_child_blocks_dns_lookup(guarded_env, node_executable, node_script):
    result = run_node(node_executable, node_script, guarded_env, "dns", "example.org")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "ENETGUARD" in result.stdout or "Noor guard" in result.stdout
