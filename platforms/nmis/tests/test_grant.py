"""T030: local grant procedure. Fake account ids and display names only."""

import shutil
from pathlib import Path

import pytest
from noor_registry.authorizations import Register
from noor_registry.config import load_config
from noor_registry.db import open_db, utc_now
from noor_registry.grant import EXIT_DISABLED, EXIT_OK, EXIT_REFUSED, main
from werkzeug.security import generate_password_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TENDER = "NT-2026-0001"
REF = "AUTH-REF-001"
PASSWORDS = {"pm": "fake-pass-pm-123", "mem": "fake-pass-mem-123",
             "view": "fake-pass-view-12", "ra": "fake-pass-ra-1234"}


@pytest.fixture()
def config(tmp_path):
    identity = tmp_path / "identity"
    shutil.copytree(REPO_ROOT / "config/identity/noor", identity)
    env = {"NOOR_DATA_DIR": str(tmp_path / "data"),
           "NOOR_EXCHANGE_DIR": str(tmp_path / "exchange"),
           "NOOR_IDENTITY_DIR": str(identity),
           "NOOR_SECRET_KEY": "k" * 40}
    key_file = tmp_path / 'test_key_path.txt'
    key_file.write_text('test path marker', encoding='utf-8')
    env['NOOR_HOME_SIGNING_KEY_FILE'] = str(key_file)
    for kind in ("PROPOSAL_MANAGER", "REVIEW_APPROVER", "MEMBER", "VIEWER"):
        env[f"NOOR_PW_{kind}"] = "fake-password-" + kind.lower()
    cfg = load_config(env, repo_root=tmp_path / "repo")
    key_file.unlink()
    conn = open_db(cfg.data_dir, create=True)
    with conn:
        for uid, kind, enabled in (("pm", "proposal_manager", 1), ("mem", "member", 1),
                                   ("view", "viewer", 1), ("ra", "review_approver", 0)):
            conn.execute(
                "INSERT INTO users (user_id, display_name, kind, password_hash, enabled)"
                " VALUES (?, ?, ?, ?, ?)",
                (uid, f"Fake {uid}", kind, generate_password_hash(PASSWORDS[uid]), enabled))
        conn.execute("INSERT INTO tenders (tender_id, title, issuing_entity, created_by, created_at)"
                     " VALUES (?, 'Synthetic tender', 'Synthetic entity', 'pm', ?)",
                     (TENDER, utc_now()))
    conn.close()
    return cfg


# Designated configuration account "mem" (a test choice; the real one is set by the owner in the
# local register outside the repo).
REGISTER = Register("mem", (
    {"ref": REF, "owner": "nmis_owner", "grantee": "pm", "capability": "create_synthetic_tender"},
    {"ref": REF, "owner": "nmis_owner", "grantee": "view", "capability": "create_synthetic_tender"},
    {"ref": REF, "owner": "nmis_owner", "grantee": "pm", "role": "approver", "tender_id": TENDER},
    {"ref": REF, "owner": "nmis_owner", "grantee": "view", "role": "approver", "tender_id": TENDER},
    {"ref": REF, "owner": "nmis_owner", "grantee": "view", "role": "viewer", "tender_id": TENDER},
))


def run(config, argv, password, register=REGISTER):
    return main(argv, password_reader=lambda _prompt="": password, config_loader=lambda: config,
                register_loader=lambda: register)


def count(config, sql):
    conn = open_db(config.data_dir)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def creation(configurer="mem", grantee="pm", ref=REF):
    return ["creation", "--configurer", configurer, "--grantee", grantee,
            "--owner-authorization-ref", ref]


def membership(role, configurer="mem", grantee="pm"):
    return ["membership", "--configurer", configurer, "--grantee", grantee, "--tender", TENDER,
            "--role", role, "--owner-authorization-ref", REF]


def test_creation_grant_records_grant_and_one_approval(config, capsys):
    assert run(config, creation(), PASSWORDS["mem"]) == EXIT_OK
    assert count(config, "SELECT COUNT(*) FROM creation_grants WHERE user_id='pm'"
                         " AND configured_by_user_id='mem'") == 1
    assert count(config, "SELECT COUNT(*) FROM approvals WHERE subject_type='permission_grant'"
                         " AND subject_id='creation:pm'") == 1
    assert PASSWORDS["mem"] not in capsys.readouterr().out


@pytest.mark.parametrize("argv, password", [
    (creation(), "wrong-password-1"),                 # wrong password
    (creation(configurer="mem", grantee="pm", ref="AUTH-FAKE-999"), PASSWORDS["mem"]),  # made-up REF
    (creation(configurer="pm"), PASSWORDS["pm"]),      # self grant
    (creation(configurer="view"), PASSWORDS["view"]),  # viewer configurer
    (creation(configurer="ra"), PASSWORDS["ra"]),      # disabled configurer
    (creation(grantee="view"), PASSWORDS["mem"]),      # viewer grantee
    (creation(grantee="ghost"), PASSWORDS["mem"]),     # unknown grantee
    (creation(ref="Ahmed Ali"), PASSWORDS["mem"]),     # a name, not an opaque reference
    (creation(ref=".."), PASSWORDS["mem"]),
    (creation(ref=""), PASSWORDS["mem"]),
])
def test_refusals_write_nothing(config, argv, password, capsys):
    assert run(config, argv, password) == EXIT_REFUSED
    assert count(config, "SELECT COUNT(*) FROM creation_grants") == 0
    assert count(config, "SELECT COUNT(*) FROM approvals") == 0
    assert password not in capsys.readouterr().err


def test_duplicate_creation_grant_is_refused(config):
    assert run(config, creation(), PASSWORDS["mem"]) == EXIT_OK
    assert run(config, creation(), PASSWORDS["mem"]) == EXIT_REFUSED
    assert count(config, "SELECT COUNT(*) FROM creation_grants") == 1


def test_membership_grant(config):
    assert run(config, membership("approver"), PASSWORDS["mem"]) == EXIT_OK
    assert count(config, "SELECT COUNT(*) FROM memberships WHERE user_id='pm'"
                         f" AND tender_id='{TENDER}' AND role='approver'") == 1
    assert count(config, "SELECT COUNT(*) FROM approvals WHERE subject_type='permission_grant'") == 1


def test_review_approver_membership_is_disabled(config):
    assert run(config, membership("review_approver", grantee="ra"), PASSWORDS["mem"]) == EXIT_DISABLED
    assert count(config, "SELECT COUNT(*) FROM memberships") == 0
    assert count(config, "SELECT enabled FROM users WHERE user_id='ra'") == 0


def test_membership_to_viewer_only_as_viewer(config):
    assert run(config, membership("approver", grantee="view"), PASSWORDS["mem"]) == EXIT_REFUSED
    assert run(config, membership("viewer", grantee="view"), PASSWORDS["mem"]) == EXIT_OK


def test_only_the_designated_configurer_may_grant(config):
    # pm has a valid password and the record exists, but pm is not the designated account.
    assert run(config, creation(configurer="pm", grantee="mem"), PASSWORDS["pm"]) == EXIT_REFUSED
    assert run(config, membership("approver", configurer="pm", grantee="mem"),
               PASSWORDS["pm"]) == EXIT_REFUSED
    assert count(config, "SELECT COUNT(*) FROM approvals") == 0


def test_missing_register_refuses(config, monkeypatch):
    monkeypatch.delenv("NOOR_AUTHORIZATIONS_FILE", raising=False)
    assert main(creation(), password_reader=lambda _p="": PASSWORDS["mem"],
                config_loader=lambda: config) == EXIT_REFUSED
