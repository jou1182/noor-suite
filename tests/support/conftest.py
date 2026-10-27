"""Shared fixtures for the test support helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

SUPPORT_DIR = Path(__file__).resolve().parent
NO_NETWORK_DIR = SUPPORT_DIR / "no_network"
NO_NETWORK_PY = NO_NETWORK_DIR / "sitecustomize.py"
NO_NETWORK_JS = NO_NETWORK_DIR / "no_network.cjs"


def _node_require_option() -> str:
    """Build the NODE_OPTIONS value that loads the Node guard."""
    # Forward slashes: NODE_OPTIONS treats a backslash inside quotes as an escape on Windows.
    path = NO_NETWORK_JS.as_posix()
    if " " in path:
        path = '"{}"'.format(path)
    return "--require {}".format(path)


@pytest.fixture
def guarded_env() -> dict[str, str]:
    """A copy of ``os.environ`` with the demo network guard enabled."""
    env = dict(os.environ)

    parts = [str(NO_NETWORK_DIR)]
    existing = env.get("PYTHONPATH")
    if existing:
        parts.extend(part for part in existing.split(os.pathsep) if part)
    env["PYTHONPATH"] = os.pathsep.join(parts)

    env["NODE_OPTIONS"] = _node_require_option()
    env["NOOR_NETGUARD"] = "1"
    return env
