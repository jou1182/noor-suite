"""Home assertion is canonical, short lived and bound only in memory."""
import base64
import json
from datetime import datetime

from app_fixtures import client_for
from noor_registry import sso
from noor_registry.db import open_db
from noor_sso.verify import AssertionVerifier, AssertionError401
import pytest


def test_signed_principal_is_canonical_and_replay_checked(nmis_app, client_for):
    client = client_for('pm')
    conn = open_db(nmis_app.config.data_dir)
    parent = conn.execute('SELECT * FROM system_session').fetchone()
    user = __import__('noor_registry.authz', fromlist=['load_user']).load_user(conn, 'pm')
    bindings = nmis_app.app.extensions['noor_registry']['bindings']
    key = nmis_app.app.extensions['noor_registry']['signing_key']
    assertion = sso.sign_assertion(key, user, 'radar', 'system', parent['csrf_token'],
                                   'a' * 64, bindings)
    parts = assertion.split('.')
    assert len(parts) == 3 and parts[0] == 'v1'
    payload_bytes = base64.urlsafe_b64decode(parts[1] + '==')
    payload = json.loads(payload_bytes)
    assert payload_bytes == json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode()
    assert datetime.fromisoformat(payload['expires_at']) - datetime.fromisoformat(payload['issued_at']) <= sso.timedelta(seconds=5)
    assert 'sid' not in json.dumps(payload)
    assert payload['nonce'] in bindings
    verifier = AssertionVerifier(key.public_key(), 'radar')
    assert verifier.verify(assertion) == payload
    with pytest.raises(AssertionError401):
        verifier.verify(assertion)
    conn.close()
