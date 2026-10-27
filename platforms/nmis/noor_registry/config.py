"""Environment driven configuration for the NMIS demo application.

Every setting is read from environment variables so the demo can be started on
a workstation without editing files.  Problems are reported through
:class:`ConfigError` using variable *names* only -- secret values are never
echoed into error messages, logs or ``repr`` output.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ACCOUNT_KINDS",
    "Config",
    "ConfigError",
    "PASSWORD_VARS",
    "REQUIRED_VARS",
    "load_config",
]

DATA_DIR_VAR = "NOOR_DATA_DIR"
EXCHANGE_DIR_VAR = "NOOR_EXCHANGE_DIR"
SECRET_KEY_VAR = "NOOR_SECRET_KEY"  # noqa: S105 - variable name, not a value
IDENTITY_DIR_VAR = "NOOR_IDENTITY_DIR"

#: Environment variables that must be present (and non empty).
REQUIRED_VARS: tuple[str, ...] = (
    DATA_DIR_VAR,
    EXCHANGE_DIR_VAR,
    SECRET_KEY_VAR,
    IDENTITY_DIR_VAR,
    "NOOR_PW_PROPOSAL_MANAGER",
    "NOOR_PW_REVIEW_APPROVER",
    "NOOR_PW_MEMBER",
    "NOOR_PW_VIEWER",
    "NOOR_HOME_SIGNING_KEY_FILE",
)

#: Account kind -> environment variable holding its password.
PASSWORD_VARS: dict[str, str] = {
    "proposal_manager": "NOOR_PW_PROPOSAL_MANAGER",
    "review_approver": "NOOR_PW_REVIEW_APPROVER",
    "member": "NOOR_PW_MEMBER",
    "viewer": "NOOR_PW_VIEWER",
}

#: The account kinds understood by the application.
ACCOUNT_KINDS: tuple[str, ...] = tuple(PASSWORD_VARS)

MIN_SECRET_KEY_LENGTH = 32
MIN_PASSWORD_LENGTH = 12


class ConfigError(Exception):
    """Raised when the environment does not describe a usable configuration."""


@dataclass(frozen=True)
class Config:
    """Immutable configuration bundle handed to the application factory."""

    data_dir: Path
    exchange_dir: Path
    identity_dir: Path
    secret_key: str = field(repr=False)
    passwords: dict[str, str] = field(repr=False)
    signing_key_file: Path | None = field(default=None, repr=False)


def load_config(
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> Config:
    """Build a :class:`Config` from environment variables.

    ``env`` defaults to ``os.environ``.  ``repo_root`` defaults to the root of
    the repository this module lives in; the data and exchange directories must
    live *outside* of it so the demo never writes into the source tree.
    """

    if env is None:
        env = os.environ
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]

    values: dict[str, str] = {}
    missing: list[str] = []
    for name in REQUIRED_VARS:
        raw = env.get(name)
        if raw is None or not raw.strip():
            missing.append(name)
        else:
            values[name] = raw
    if missing:
        raise ConfigError(
            "Missing or empty required environment variable(s): " + ", ".join(missing)
        )

    data_dir = _absolute_dir(values[DATA_DIR_VAR], DATA_DIR_VAR)
    exchange_dir = _absolute_dir(values[EXCHANGE_DIR_VAR], EXCHANGE_DIR_VAR)
    identity_dir = _absolute_dir(values[IDENTITY_DIR_VAR], IDENTITY_DIR_VAR)
    signing_key_file = _absolute_dir(values["NOOR_HOME_SIGNING_KEY_FILE"], "NOOR_HOME_SIGNING_KEY_FILE")

    root = Path(repo_root).resolve()
    data_resolved = data_dir.resolve()
    exchange_resolved = exchange_dir.resolve()
    if data_resolved.is_relative_to(root):
        raise ConfigError(
            f"{DATA_DIR_VAR} must not be located inside the repository root"
        )
    if exchange_resolved.is_relative_to(root):
        raise ConfigError(
            f"{EXCHANGE_DIR_VAR} must not be located inside the repository root"
        )
    if signing_key_file.resolve().is_relative_to(root):
        raise ConfigError("NOOR_HOME_SIGNING_KEY_FILE must be outside the repository root")
    if not signing_key_file.is_file():
        raise ConfigError("NOOR_HOME_SIGNING_KEY_FILE must name an existing PEM file")
    if data_resolved == exchange_resolved:
        raise ConfigError(
            f"{DATA_DIR_VAR} and {EXCHANGE_DIR_VAR} must be different directories"
        )

    secret_key = values[SECRET_KEY_VAR]
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ConfigError(
            f"{SECRET_KEY_VAR} must be at least {MIN_SECRET_KEY_LENGTH} characters long"
        )

    passwords: dict[str, str] = {}
    for kind, var_name in PASSWORD_VARS.items():
        password = values[var_name]
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ConfigError(
                f"{var_name} must be at least {MIN_PASSWORD_LENGTH} characters long"
            )
        passwords[kind] = password

    _ensure_directory(data_resolved, DATA_DIR_VAR)
    _ensure_directory(exchange_resolved, EXCHANGE_DIR_VAR)

    from noor_identity import IdentityBuildError, build_identity
    try:
        build_identity(identity_dir)
    except (IdentityBuildError, OSError) as exc:
        raise ConfigError(f"{IDENTITY_DIR_VAR} identity build failed: {exc}") from exc

    return Config(
        data_dir=data_resolved,
        exchange_dir=exchange_resolved,
        identity_dir=identity_dir.resolve(),
        secret_key=secret_key,
        passwords=passwords,
        signing_key_file=signing_key_file.resolve(),
    )


def _absolute_dir(raw: str, name: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise ConfigError(f"{name} must be an absolute path")
    return path


def _ensure_directory(path: Path, name: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"{name} could not be created: {exc.strerror}") from exc
