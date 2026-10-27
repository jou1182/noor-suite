"""002 session properties; these must hold across browser and proxy requests."""
import hashlib
from datetime import datetime, timedelta

from app_fixtures import csrf_of
from noor_registry.db import open_db


def test_login_issues_opaque_server_session(nmis_app):
    client = nmis_app.app.test_client()
    csrf = csrf_of(client)
    response = client.post('/login', data={'csrf_token': csrf, 'user_id': 'pm',
                                           'password': nmis_app.passwords['proposal_manager']},
                           headers={'Origin': 'http://noor.localhost:5310'})
    assert response.status_code == 302
    cookie = client.get_cookie('noor_sid', domain='noor.localhost')
    assert cookie is not None and len(cookie.value) == 43
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert 'SameSite=Strict' in response.headers['Set-Cookie']
    assert 'Domain=' not in response.headers['Set-Cookie']
    conn = open_db(nmis_app.config.data_dir)
    row = conn.execute('SELECT * FROM system_session').fetchone()
    assert row['sid_hash'] == hashlib.sha256(cookie.value.encode()).hexdigest()
    assert cookie.value not in repr(tuple(row))
    assert datetime.fromisoformat(row['idle_expires_at']) - datetime.fromisoformat(row['last_seen_at']) == timedelta(minutes=30)
    assert datetime.fromisoformat(row['absolute_expires_at']) - datetime.fromisoformat(row['created_at']) == timedelta(hours=8)
    conn.close()


def test_expiry_and_logout_revoke_derived_sessions(nmis_app, client_for):
    client = client_for('pm')
    conn = open_db(nmis_app.config.data_dir)
    sid = conn.execute('SELECT sid_hash FROM system_session').fetchone()['sid_hash']
    code = __import__('noor_registry.sso', fromlist=['entry_code']).entry_code(conn, sid, 'radar')
    psid = __import__('noor_registry.sso', fromlist=['exchange_entry']).exchange_entry(conn, code, 'radar')
    assert psid
    token = csrf_of(client)
    response = client.post('/logout', data={'csrf_token': token},
                           headers={'Origin': 'http://noor.localhost:5310'})
    assert response.status_code == 302
    assert conn.execute('SELECT state FROM system_session WHERE sid_hash=?', (sid,)).fetchone()['state'] == 'logged_out'
    assert conn.execute('SELECT state FROM platform_session WHERE parent_sid_hash=?', (sid,)).fetchone()['state'] == 'revoked'
    conn.close()
