"""Tests for :mod:`noor_registry.config` (T017/T018).

The tests never touch the real process environment: every case passes an
explicit ``env`` mapping so they stay deterministic and side-effect free.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
from noor_registry.config import Config, ConfigError, load_config

PASSWORD_VARS = [
    "NOOR_PW_PROPOSAL_MANAGER",
    "NOOR_PW_REVIEW_APPROVER",
    "NOOR_PW_MEMBER",
    "NOOR_PW_VIEWER",
]

ALL_VARS = [
    "NOOR_DATA_DIR",
    "NOOR_EXCHANGE_DIR",
    "NOOR_SECRET_KEY",
    "NOOR_IDENTITY_DIR",
    "NOOR_HOME_SIGNING_KEY_FILE",
    *PASSWORD_VARS,
]


def base_env(tmp_path: Path) -> dict[str, str]:
    """A complete, valid environment mapping rooted below ``tmp_path``."""
    identity = tmp_path / "identity"
    if not identity.exists():
        shutil.copytree(Path(__file__).resolve().parents[3] / "config/identity/noor", identity)
    key_file = tmp_path / 'test_key_path.txt'
    if not key_file.exists():
        key_file.write_text('test path marker', encoding='utf-8')
    return {
        "NOOR_DATA_DIR": str(tmp_path / "data"),
        "NOOR_EXCHANGE_DIR": str(tmp_path / "exchange"),
        "NOOR_SECRET_KEY": "s" * 40,
        "NOOR_IDENTITY_DIR": str(identity),
        "NOOR_HOME_SIGNING_KEY_FILE": str(key_file),
        "NOOR_PW_PROPOSAL_MANAGER": "pm" * 8,
        "NOOR_PW_REVIEW_APPROVER": "ra" * 8,
        "NOOR_PW_MEMBER": "me" * 8,
        "NOOR_PW_VIEWER": "vi" * 8,
    }


def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_missing_variable_is_named(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env.pop("NOOR_SECRET_KEY")
    with pytest.raises(ConfigError) as excinfo:
        load_config(env=env, repo_root=repo_root(tmp_path))
    message = str(excinfo.value)
    assert "NOOR_SECRET_KEY" in message
    for value in env.values():
        assert value not in message


@pytest.mark.parametrize("name", ALL_VARS)
def test_each_missing_variable_is_reported(tmp_path: Path, name: str) -> None:
    env = base_env(tmp_path)
    env.pop(name)
    with pytest.raises(ConfigError) as excinfo:
        load_config(env=env, repo_root=repo_root(tmp_path))
    message = str(excinfo.value)
    assert name in message
    for other in ALL_VARS:
        if other != name:
            assert other not in message
    for value in env.values():
        assert value not in message


@pytest.mark.parametrize("name", ALL_VARS)
def test_empty_variable_is_treated_as_missing(tmp_path: Path, name: str) -> None:
    env = base_env(tmp_path)
    env[name] = ""
    with pytest.raises(ConfigError) as excinfo:
        load_config(env=env, repo_root=repo_root(tmp_path))
    assert name in str(excinfo.value)


def test_all_missing_variables_are_listed_once(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env.pop("NOOR_SECRET_KEY")
    env.pop("NOOR_PW_MEMBER")
    with pytest.raises(ConfigError) as excinfo:
        load_config(env=env, repo_root=repo_root(tmp_path))
    message = str(excinfo.value)
    assert "NOOR_SECRET_KEY" in message
    assert "NOOR_PW_MEMBER" in message


def test_data_dir_inside_repo_root_is_rejected(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    env = base_env(tmp_path)
    env["NOOR_DATA_DIR"] = str(root / "data")
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=root)


def test_exchange_dir_inside_repo_root_is_rejected(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    env = base_env(tmp_path)
    env["NOOR_EXCHANGE_DIR"] = str(root / "exchange")
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=root)


def test_repo_root_itself_is_rejected(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    env = base_env(tmp_path)
    env["NOOR_DATA_DIR"] = str(root)
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=root)


def test_relative_data_dir_is_rejected(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env["NOOR_DATA_DIR"] = "relative/data"
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=repo_root(tmp_path))


def test_relative_exchange_dir_is_rejected(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env["NOOR_EXCHANGE_DIR"] = "relative/exchange"
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=repo_root(tmp_path))


def test_same_directory_is_rejected(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    shared = str(tmp_path / "shared")
    env["NOOR_DATA_DIR"] = shared
    env["NOOR_EXCHANGE_DIR"] = shared
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=repo_root(tmp_path))


def test_short_secret_key_is_rejected(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    env["NOOR_SECRET_KEY"] = "s" * 31
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=repo_root(tmp_path))


@pytest.mark.parametrize("name", PASSWORD_VARS)
def test_short_password_is_rejected(tmp_path: Path, name: str) -> None:
    env = base_env(tmp_path)
    env[name] = "p" * 11
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=repo_root(tmp_path))


def test_happy_path_creates_directories(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    config = load_config(env=env, repo_root=repo_root(tmp_path))
    assert isinstance(config, Config)
    assert config.data_dir.is_dir()
    assert config.exchange_dir.is_dir()
    assert config.data_dir == (tmp_path / "data").resolve()
    assert config.exchange_dir == (tmp_path / "exchange").resolve()
    assert config.secret_key == env["NOOR_SECRET_KEY"]


def test_invalid_identity_profile_is_named(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    profile = Path(env["NOOR_IDENTITY_DIR"]) / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError, match="NOOR_IDENTITY_DIR"):
        load_config(env=env, repo_root=repo_root(tmp_path))


def test_passwords_are_keyed_by_account_kind(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    config = load_config(env=env, repo_root=repo_root(tmp_path))
    assert set(config.passwords) == {
        "proposal_manager",
        "review_approver",
        "member",
        "viewer",
    }
    assert config.passwords["member"] == env["NOOR_PW_MEMBER"]


def test_config_is_frozen(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    config = load_config(env=env, repo_root=repo_root(tmp_path))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.secret_key = "other"  # type: ignore[misc]


def test_repr_hides_secrets(tmp_path: Path) -> None:
    env = base_env(tmp_path)
    config = load_config(env=env, repo_root=repo_root(tmp_path))
    text = repr(config)
    assert config.secret_key not in text
    for password in config.passwords.values():
        assert password not in text
    assert "secret_key" not in text
    assert "password" not in text


def test_no_directories_are_created_when_validation_fails(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    env = base_env(tmp_path)
    env["NOOR_DATA_DIR"] = str(root / "data")
    with pytest.raises(ConfigError):
        load_config(env=env, repo_root=root)
    assert not (root / "data").exists()
    assert not (tmp_path / "exchange").exists()
