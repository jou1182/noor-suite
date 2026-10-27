"""Tests of the session, the CSRF protection and the login (story T023)."""

from __future__ import annotations

import inspect

from app_fixtures import csrf_of, session_row
from noor_registry import app as app_module

BAD_CREDENTIALS_MESSAGE = "بيانات الدخول غير صحيحة"


def _post_login(client, user_id, password, token=None):
    if token is None:
        token = csrf_of(client)
    return client.post(
        "/login",
        data={"csrf_token": token, "user_id": user_id, "password": password},
        headers={'Origin': 'http://noor.localhost:5310'},
    )


def _session_cookie(client):
    cookie = client.get_cookie("noor_sid", domain='noor.localhost')
    return None if cookie is None else cookie.value


def test_login_success_starts_a_session(nmis_app):
    client = nmis_app.app.test_client()
    response = _post_login(client, "pm", nmis_app.passwords["proposal_manager"])
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert session_row(client)['user_id'] == 'pm'
    assert session_row(client)['csrf_token']


def test_login_failures_are_indistinguishable(nmis_app):
    outcomes = []
    cases = (
        ("pm", "not-the-right-password"),
        ("no-such-user", nmis_app.passwords["member"]),
        ("ra", nmis_app.passwords["review_approver"]),
    )
    for user_id, password in cases:
        client = nmis_app.app.test_client()
        response = _post_login(client, user_id, password)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/login")
        assert session_row(client) is None
        page = client.get("/login", follow_redirects=True)
        body = page.get_data(as_text=True)
        assert BAD_CREDENTIALS_MESSAGE in body
        outcomes.append(
            (
                response.status_code,
                response.headers["Location"],
                BAD_CREDENTIALS_MESSAGE in body,
            )
        )
    # unknown user, wrong password and disabled account look exactly the same
    assert len(set(outcomes)) == 1


def test_disabled_account_cannot_log_in(nmis_app):
    client = nmis_app.app.test_client()
    response = _post_login(client, "ra", nmis_app.passwords["review_approver"])
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert session_row(client) is None


def test_session_is_rotated_on_login(nmis_app):
    client = nmis_app.app.test_client()
    first_page = client.get("/login")
    before_cookie_header = first_page.headers.get("Set-Cookie")
    before_cookie = _session_cookie(client)
    before_token = csrf_of(client)

    response = _post_login(
        client, "pm", nmis_app.passwords["proposal_manager"], token=before_token
    )
    assert response.status_code == 302

    after_token = csrf_of(client)
    after_cookie = _session_cookie(client)
    after_cookie_header = response.headers.get("Set-Cookie")

    assert after_token != before_token
    assert after_cookie != before_cookie
    assert after_cookie_header != before_cookie_header


def test_post_login_without_csrf_token_is_rejected(nmis_app):
    client = nmis_app.app.test_client()
    response = client.post(
        "/login",
        data={"user_id": "pm", "password": nmis_app.passwords["proposal_manager"]},
        headers={'Origin': 'http://noor.localhost:5310'},
    )
    assert response.status_code == 400
    assert session_row(client) is None


def test_post_login_with_a_wrong_csrf_token_is_rejected(nmis_app):
    client = nmis_app.app.test_client()
    client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": "forged-token",
            "user_id": "pm",
            "password": nmis_app.passwords["proposal_manager"],
        },
        headers={'Origin': 'http://noor.localhost:5310'},
    )
    assert response.status_code == 400


def test_identity_cannot_be_injected_from_the_request(nmis_app):
    client = nmis_app.app.test_client()
    response = client.get("/?user_id=pm", headers={"X-User": "pm", "X-User-Id": "pm"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert session_row(client) is None


def test_injected_identity_does_not_replace_the_session(nmis_app, client_for):
    client = client_for("mem")
    response = client.get("/?user_id=pm", headers={"X-User": "pm"})
    assert response.status_code == 200
    assert session_row(client)['user_id'] == 'mem'


def test_security_headers_are_present(nmis_app):
    client = nmis_app.app.test_client()
    response = client.get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    # Not "no-referrer": with it browsers send "Origin: null" and every form post fails the Origin check.
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )


def test_browser_login_origin_and_referrer_policy_on_home_and_platform(nmis_app):
    client = nmis_app.app.test_client()
    page = client.get('/login')
    assert page.headers['Referrer-Policy'] != 'no-referrer'
    token = csrf_of(client)
    response = client.post('/login', data={'csrf_token': token, 'user_id': 'pm',
                                           'password': nmis_app.passwords['proposal_manager']},
                           headers={'Origin': 'http://noor.localhost:5310'})
    assert response.status_code == 302
    assert session_row(client)['user_id'] == 'pm'
    assert response.headers['Referrer-Policy'] != 'no-referrer'
    for host in ('radar', 'qa', 'nmis', 'jr'):
        platform = client.get('/', base_url=f'http://{host}.noor.localhost:5310')
        assert platform.headers['Referrer-Policy'] != 'no-referrer'


def test_pending_login_tokens_expire_and_are_bounded(nmis_app, monkeypatch):
    from datetime import timedelta
    from noor_registry import security
    current = security.sso.now()
    monkeypatch.setattr(security.sso, 'now', lambda: current)
    pending = nmis_app.app.extensions['noor_registry']['pending_csrf']
    for _ in range(1100):
        nmis_app.app.test_client().get('/login')
    assert len(pending) <= 1024
    monkeypatch.setattr(security.sso, 'now', lambda: current + timedelta(minutes=11))
    nmis_app.app.test_client().get('/login')
    assert len(pending) == 1


def test_session_cookie_configuration(nmis_app):
    config = nmis_app.app.config
    assert config["SESSION_COOKIE_NAME"] == "noor_flash"
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Strict"
    # Plain http on the loopback interface only, see security.init_security().
    assert config["SESSION_COOKIE_SECURE"] is False


def test_viewer_may_logout(nmis_app, client_for):
    client = client_for("view")
    token = csrf_of(client)
    response = client.post("/logout", data={"csrf_token": token}, headers={'Origin': 'http://noor.localhost:5310'})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert session_row(client) is None


def test_logout_without_csrf_token_is_rejected(nmis_app, client_for):
    client = client_for("pm")
    response = client.post("/logout", headers={'Origin': 'http://noor.localhost:5310'})
    assert response.status_code == 400


def test_application_only_binds_to_the_loopback_interface():
    assert app_module.HOST == "127.0.0.1"
    assert app_module.PORT == 5310
    source = inspect.getsource(app_module)
    assert "0.0.0.0" not in source
    assert "host=HOST" in source
    assert "port=PORT" in source
    assert "debug=False" in source
