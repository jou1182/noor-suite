"""The platform verifier rejects malformed, forged and replayed assertions."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def _assertion(key, **changes):
    now = datetime.now(timezone.utc)
    payload = {'schema': 'noor.principal/v1', 'platform_id': 'radar',
               'user_id': 'U-1234abcd', 'display_name': 'حساب مصطنع',
               'role': 'viewer', 'platform_permissions': ['read'],
               'csrf': _encode(b'c' * 32), 'theme': 'system',
               'issued_at': now.isoformat(), 'expires_at': (now + timedelta(seconds=5)).isoformat(),
               'nonce': _encode(b'n' * 16), 'synthetic': True}
    payload.update(changes)
    encoded = _encode(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                 separators=(',', ':')).encode())
    prefix = 'v1.' + encoded
    return prefix + '.' + _encode(key.sign(prefix.encode()))


def test_missing_assertion_fails_closed():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from noor_sso.verify import AssertionError401, AssertionVerifier
    verifier = AssertionVerifier(Ed25519PrivateKey.generate().public_key(), 'radar')
    with pytest.raises(AssertionError401):
        verifier.verify('')


def test_verifier_rejects_wrong_key_audience_expiry_and_replay():
    from noor_sso.verify import AssertionError401, AssertionVerifier
    key = Ed25519PrivateKey.generate()
    verifier = AssertionVerifier(key.public_key(), 'radar')
    good = _assertion(key)
    assert verifier.verify(good)['platform_id'] == 'radar'
    for bad in (good, _assertion(Ed25519PrivateKey.generate()),
                _assertion(key, platform_id='jouready'),
                _assertion(key, expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()),
                _assertion(key, extra='forbidden')):
        with pytest.raises(AssertionError401):
            verifier.verify(bad)


def test_asgi_guard_denies_missing_assertion_without_fastapi():
    import asyncio

    from noor_sso.fastapi_guard import AssertionMiddleware
    from noor_sso.verify import AssertionVerifier
    async def app(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})
    guard = AssertionMiddleware(app, AssertionVerifier(Ed25519PrivateKey.generate().public_key(), 'radar'))
    events = []
    async def receive():
        return {'type': 'http.request', 'body': b''}
    async def send(event):
        events.append(event)
    asyncio.run(guard({'type': 'http', 'path': '/', 'headers': []}, receive, send))
    assert events[0]['status'] == 401 and events[1]['body'] == b''


def test_flask_guard_checks_platform_origin_and_asserted_csrf():
    from flask import Flask
    from noor_sso.flask_guard import install_guard
    from noor_sso.verify import AssertionVerifier
    key = Ed25519PrivateKey.generate()
    app = Flask(__name__)
    install_guard(app, AssertionVerifier(key.public_key(), 'radar'))
    @app.post('/write')
    def write():
        return 'ok'
    client = app.test_client()
    assertion = _assertion(key)
    headers = {'X-Noor-Assertion': assertion}
    assert client.post('/write', headers=headers).status_code == 403
    headers['Origin'] = 'http://radar.noor.localhost:5310'
    headers['X-CSRF-Token'] = _encode(b'c' * 32)
    # A fresh assertion is needed because the guard consumed the nonce above.
    headers['X-Noor-Assertion'] = _assertion(key, nonce=_encode(b'm' * 16))
    assert client.post('/write', headers=headers).status_code == 200


def test_authz_client_rejects_non_loopback_open_and_redirect():
    from noor_sso.authz_client import AuthzClient, _LoopbackRedirectHandler

    client = AuthzClient('synthetic-key')
    client.url = 'file:' + '///untrusted'
    assert client.check('assertion', 'tender', 'read') is False
    with pytest.raises(ValueError, match='loopback'):
        _LoopbackRedirectHandler().redirect_request(None, None, 302, 'redirect', {},
                                                    'https://example.invalid/decision')
