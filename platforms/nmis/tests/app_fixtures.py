"""Shared Flask fixtures for NMIS tests (imported by conftest.py). Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from noor_registry.app import create_app
from noor_registry.config import load_config
from noor_registry.db import open_db, utc_now
from werkzeug.security import generate_password_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TENDER_ID = "NT-2026-0001"
# (user_id, display_name, kind, enabled)
USER_SPECS = (
    ("pm", "مدير العروض (اختبار)", "proposal_manager", 1),
    ("mem", "عضو الفريق (اختبار)", "member", 1),
    ("view", "حساب العرض (اختبار)", "viewer", 1),
    ("ra", "معتمِد المراجعة (اختبار)", "review_approver", 0),
)
KIND_OF = {spec[0]: spec[2] for spec in USER_SPECS}


@pytest.fixture
def nmis_app(tmp_path):
    """An app over a fresh synthetic DB: four accounts and one candidate tender."""
    env = {"NOOR_DATA_DIR": str(tmp_path / "data"),
           "NOOR_EXCHANGE_DIR": str(tmp_path / "exchange"),
           "NOOR_SECRET_KEY": "k" * 40}
    identity_dir = tmp_path / "identity"
    shutil.copytree(REPO_ROOT / "config" / "identity" / "noor", identity_dir)
    env["NOOR_IDENTITY_DIR"] = str(identity_dir)
    key_file = tmp_path / 'test_key_path.txt'
    key_file.write_text('test path marker', encoding='utf-8')
    env['NOOR_HOME_SIGNING_KEY_FILE'] = str(key_file)
    for kind in KIND_OF.values():
        env["NOOR_PW_" + kind.upper()] = "test-password-" + kind
    config = load_config(env, repo_root=tmp_path / "repo")
    key_file.unlink()
    conn = open_db(config.data_dir, create=True)
    with conn:
        for user_id, display_name, kind, enabled in USER_SPECS:
            conn.execute(
                "INSERT INTO users (user_id, display_name, kind, password_hash, enabled)"
                " VALUES (?, ?, ?, ?, ?)",
                (user_id, display_name, kind,
                 generate_password_hash(config.passwords[kind]), enabled))
        conn.execute(
            "INSERT INTO tenders (tender_id, title, issuing_entity, created_by, created_at)"
            " VALUES (?, 'منافسة تجريبية', 'جهة مصطنعة للاختبار', 'pm', ?)",
            (TENDER_ID, utc_now()))
        # Keep the id counter in step with the fixture tender so issued ids never collide.
        conn.execute("INSERT INTO tender_counter (year, last) VALUES (?, 1)",
                     (int(TENDER_ID[3:7]),))
    conn.close()
    with patch('noor_registry.sso.load_private_key', return_value=Ed25519PrivateKey.generate()):
        app = create_app(config)
    app.config["TESTING"] = True
    app.config['SERVER_NAME'] = 'noor.localhost:5310'
    return SimpleNamespace(app=app, config=config, passwords=config.passwords)


def add_user(nmis_app, user_id: str, kind: str = "proposal_manager") -> None:
    """Add one more enabled synthetic account (its password is the one of its kind)."""
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        conn.execute(
            "INSERT INTO users (user_id, display_name, kind, password_hash, enabled)"
            " VALUES (?, ?, ?, ?, 1)",
            (user_id, f"حساب اختبار {user_id}", kind,
             generate_password_hash(nmis_app.passwords[kind])))
    conn.close()
    KIND_OF[user_id] = kind


def _approval(conn, subject_id: str, tender_id=None) -> str:
    approval_id = "AP-" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO approvals (approval_id, tender_id, subject_type, subject_id, acting_role,"
        " decision, actor_user_id, decided_at) VALUES (?, ?, 'permission_grant', ?,"
        " 'configuration', 'approved', 'pm', ?)",
        (approval_id, tender_id, subject_id, utc_now()))
    return approval_id


def give_creation_grant(nmis_app, user_id: str) -> None:
    """Record a CreationGrant the way the local grant procedure (T030) does."""
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        approval_id = _approval(conn, f"creation:{user_id}")
        conn.execute(
            "INSERT INTO creation_grants (user_id, capability, owner_authorization_ref,"
            " configured_by_user_id, granted_at, grant_approval_id)"
            " VALUES (?, 'create_synthetic_tender', 'AUTH-TEST-001', 'pm', ?, ?)",
            (user_id, utc_now(), approval_id))
    conn.close()


def give_membership(nmis_app, user_id: str, tender_id: str, role: str) -> None:
    """Record a tender membership the way the local grant procedure (T030) does."""
    conn = open_db(nmis_app.config.data_dir)
    with conn:
        approval_id = _approval(conn, f"{tender_id}:{user_id}:{role}", tender_id)
        conn.execute(
            "INSERT INTO memberships (user_id, tender_id, role, owner_authorization_ref,"
            " configured_by_user_id, granted_at, grant_approval_id)"
            " VALUES (?, ?, ?, 'AUTH-TEST-001', 'pm', ?, ?)",
            (user_id, tender_id, role, utc_now(), approval_id))
    conn.close()


def query(nmis_app, sql: str, params=()):
    """Run a read query on the app database and return all rows."""
    conn = open_db(nmis_app.config.data_dir)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def candidate(**overrides) -> dict:
    """A valid noor.tender-candidate/v1 document with invented values only."""
    doc = {
        "schema": "noor.tender-candidate/v1",
        "source_name": "radar",
        "source_ref": "SYN-0001",
        "title": "توريد وتركيب معدات مختبر مصطنع للاختبار",
        "issuing_entity": "الجهة المصطنعة ألف",
        "closing_at": "2026-12-01T10:00:00+03:00",
        "etimad_ref": None,
        "source_updated_at": "2026-10-20T08:00:00+03:00",
        "exported_at": "2026-10-20T09:00:00+03:00",
        "synthetic": True,
    }
    doc.update(overrides)
    return doc


def write_exchange(nmis_app, name: str, doc) -> None:
    """Drop a contract file into the configured exchange directory."""
    data = doc if isinstance(doc, bytes) else json.dumps(doc, ensure_ascii=False).encode("utf-8")
    (nmis_app.config.exchange_dir / name).write_bytes(data)


def post(client, url: str, **data):
    """POST a form with the session's CSRF token."""
    data["csrf_token"] = csrf_of(client)
    return client.post(url, data=data, headers={'Origin': 'http://noor.localhost:5310'})


def password_for(nmis_app, user_id: str) -> str:
    return nmis_app.passwords[KIND_OF[user_id]]


def csrf_of(client) -> str:
    """Read the server-bound token rendered into the login form."""
    page = client.get('/login').get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def session_row(client):
    cookie = client.get_cookie('noor_sid', domain='noor.localhost')
    if cookie is None:
        return None
    conn = open_db(client.application.config['NOOR_CONFIG'].data_dir)
    try:
        return conn.execute('SELECT * FROM system_session WHERE sid_hash=?',
                            (hashlib.sha256(cookie.value.encode()).hexdigest(),)).fetchone()
    finally:
        conn.close()


@pytest.fixture
def client_for(nmis_app):
    """Factory: client_for(None) is anonymous; client_for("pm") is logged in as pm."""

    def make(user_id=None):
        client = nmis_app.app.test_client()
        if user_id is None:
            return client
        response = client.post("/login", data={
            "csrf_token": csrf_of(client), "user_id": user_id,
            "password": password_for(nmis_app, user_id)},
            headers={'Origin': 'http://noor.localhost:5310'})
        assert response.status_code == 302 and response.location.endswith("/"), user_id
        return client

    return make
