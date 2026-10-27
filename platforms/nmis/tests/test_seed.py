"""T029: synthetic account seeding."""

import shutil
from pathlib import Path

import pytest
from noor_registry.config import load_config
from noor_registry.db import open_db
from noor_registry.seed import SeedError, seed
from werkzeug.security import check_password_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
KINDS = ("proposal_manager", "review_approver", "member", "viewer")


@pytest.fixture()
def config(tmp_path):
    identity = tmp_path / "identity"
    shutil.copytree(REPO_ROOT / "config/identity/noor", identity)
    env = {
        "NOOR_DATA_DIR": str(tmp_path / "data"),
        "NOOR_EXCHANGE_DIR": str(tmp_path / "exchange"),
        "NOOR_IDENTITY_DIR": str(identity),
        "NOOR_SECRET_KEY": "k" * 40,
    }
    key_file = tmp_path / 'test_key_path.txt'
    key_file.write_text('test path marker', encoding='utf-8')
    env['NOOR_HOME_SIGNING_KEY_FILE'] = str(key_file)
    for kind in KINDS:
        env[f"NOOR_PW_{kind.upper()}"] = f"fake-password-{kind}"
    config = load_config(env, repo_root=tmp_path / "repo")
    key_file.unlink()
    return config


def _users(config):
    conn = open_db(config.data_dir)
    try:
        return {row["user_id"]: row for row in conn.execute("SELECT * FROM users")}
    finally:
        conn.close()


def test_four_accounts_with_passwords_from_config(config):
    seed(config)
    users = _users(config)
    assert {row["kind"] for row in users.values()} == set(KINDS)
    for row in users.values():
        assert row["shared"] == 0 and row["synthetic"] == 1
        assert check_password_hash(row["password_hash"], config.passwords[row["kind"]])


def test_review_approver_is_disabled_without_operator(config):
    seed(config)
    ra = _users(config)["ra"]
    assert ra["enabled"] == 0
    assert ra["operator_label"] is None


def test_no_grants_or_memberships_are_seeded(config):
    seed(config)
    conn = open_db(config.data_dir)
    try:
        for table in ("creation_grants", "memberships", "approvals", "tenders"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0  # noqa: S608
    finally:
        conn.close()


def test_existing_database_is_not_seeded_in_place(config):
    seed(config)
    with pytest.raises(SeedError):
        seed(config)


def test_reset_backs_up_before_seeding(config):
    seed(config)
    backup = seed(config, reset=True)
    assert backup is not None and backup.exists()
    assert backup.parent == config.data_dir / "backups"
    assert set(_users(config)) == {"pm", "ra", "mem", "view"}
