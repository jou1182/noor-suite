"""Opaque home sessions, server-bound CSRF, Origin checks and login helpers.

Identity comes only from the hashed server session behind ``noor_sid``.
Query arguments, form fields, headers and JSON never choose the principal.
"""

from __future__ import annotations

import hmac
import sqlite3
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional

from flask import (
    Flask,
    abort,
    current_app,
    g,
    redirect,
    request,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import sso
from .authz import load_user

#: "no-referrer" makes Chromium send "Origin: null" on form posts, which the
#: mandatory Origin check rejects; "same-origin" keeps the Origin on same-origin
#: requests and still sends no referrer to any other origin.
REFERRER_POLICY = "same-origin"

__all__ = [
    "AUTH_ENDPOINTS",
    "CSRF_FORM_FIELD",
    "CSRF_HEADER",
    "CSRF_SESSION_KEY",
    "VIEWER_ALLOWED_POST",
    "csrf_token",
    "download_route",
    "init_security",
    "login",
    "login_required",
    "state_change",
]

#: Legacy template-facing CSRF name; the value is stored on the server.
CSRF_SESSION_KEY = "_csrf"
#: Name of the form field that carries the CSRF token.
CSRF_FORM_FIELD = "csrf_token"
#: Name of the header that carries the CSRF token (used by JSON clients).
CSRF_HEADER = "X-CSRF-Token"

#: Endpoints a ``viewer`` account is still allowed to POST to.
VIEWER_ALLOWED_POST = frozenset({"logout"})

#: Endpoints that establish the identity of the caller.  They are not viewer
#: restricted state changes: a viewer may (re-)submit the login form.
AUTH_ENDPOINTS = frozenset({"login_post"})

_SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

_DUMMY_HASH: Optional[str] = None
PENDING_CSRF_TTL = timedelta(minutes=10)
PENDING_CSRF_MAX = 1024


def _flag(value: Any) -> bool:
    """Interpret a database flag (``0``/``1``/``"0"``/``"true"`` ...) safely."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "none")
    return bool(value)


def _db():
    """Return the database connection of the running application."""
    extensions = current_app.extensions.get("noor_registry") or {}
    getter = extensions.get("get_db")
    if getter is None:
        raise RuntimeError("noor_registry: the application extensions are not initialised")
    return getter()


def _view():
    """Return the view function that handles the current request (or None)."""
    if not request.endpoint:
        return None
    return current_app.view_functions.get(request.endpoint)


def _is_download(view: Any) -> bool:
    return bool(getattr(view, "_noor_download", False))


def _fetch_row(conn, statement: str, parameters):
    try:
        cursor = conn.execute(statement, parameters)
    except sqlite3.Error:
        return None
    return cursor.fetchone()


def _user_id_of(user: Any) -> Optional[str]:
    value = getattr(user, "user_id", None)
    return None if value is None else str(value)


def _user_enabled(conn, user: Any) -> bool:
    """Is the account enabled?  Falls back to the database when needed."""
    enabled = getattr(user, "enabled", None)
    if enabled is None:
        row = _fetch_row(
            conn,
            'SELECT enabled FROM users WHERE user_id = ?',
            (_user_id_of(user),),
        )
        if row is None:
            return False
        enabled = row[0]
    return _flag(enabled)


def _password_hash(conn, user: Any) -> Optional[str]:
    """Return the stored password hash of ``user`` (or None)."""
    value = getattr(user, "password_hash", None)
    if value:
        return str(value)
    row = _fetch_row(
        conn,
        'SELECT password_hash FROM users WHERE user_id = ?',
        (_user_id_of(user),),
    )
    if row is None:
        return None
    return None if row[0] is None else str(row[0])


def _equalise(password: Any) -> None:
    """Spend roughly the same time on a failed login as on a successful one."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = generate_password_hash("noor-registry-dummy-password")
    check_password_hash(_DUMMY_HASH, password if isinstance(password, str) else "")


def _safe_compare(left: Any, right: Any) -> bool:
    try:
        return hmac.compare_digest(
            str(left).encode("utf-8"), str(right).encode("utf-8")
        )
    except (TypeError, UnicodeError, ValueError):
        return False


def _submitted_token() -> Optional[str]:
    """Read the CSRF token from the form body or the header; never from the URL."""
    return request.form.get(CSRF_FORM_FIELD) or request.headers.get(CSRF_HEADER)


def csrf_token() -> str:
    """Return the token stored with the server session or pending login."""
    row = getattr(g, 'system_session', None)
    if row is not None:
        return row['csrf_token']
    pre = getattr(g, 'pre_id', None)
    if pre is None:
        pre = sso.token()
        g.pre_id = pre
    pending = current_app.extensions['noor_registry']['pending_csrf']
    with sso._lock:
        current = sso.now()
        for key, (_, issued_at) in list(pending.items()):
            if current - issued_at >= PENDING_CSRF_TTL:
                del pending[key]
        if pre not in pending:
            if len(pending) >= PENDING_CSRF_MAX:
                del pending[next(iter(pending))]
            pending[pre] = (sso.token(), current)
        return pending[pre][0]


def init_security(app: Flask, config) -> None:
    """Configure the session, the CSRF protection and the login helpers."""
    app.secret_key = config.secret_key
    app.config.update(
        SESSION_COOKIE_NAME="noor_flash",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        # The local demo runs on plain HTTP loopback; cookies remain host-only.
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_PATH="/",
    )

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.extensions['noor_registry']['pending_csrf'] = {}
    @app.context_processor
    def inject_current_user() -> dict[str, Any]:
        # The User object itself (or None), so `{% if current_user %}` means "logged in".
        return {"current_user": getattr(g, "current_user", None)}

    @app.before_request
    def load_current_user() -> None:
        """Load identity only from a hashed opaque server session."""
        g.current_user = None
        g.system_session = None
        g.pre_id = request.cookies.get('noor_pre')
        raw = request.cookies.get('noor_sid')
        if not raw:
            return None
        row = None
        try:
            row = sso.touch(_db(), sso.digest(raw))
            user = load_user(_db(), row['user_id']) if row is not None else None
        except Exception:  # pragma: no cover - fail closed, never trust the cookie
            user = None
        if user is None or not _user_enabled(_db(), user):
            if row is not None:
                sso.revoke(_db(), row['sid_hash'])
            return None
        g.current_user = user
        g.system_session = row
        return None

    @app.before_request
    def csrf_protect() -> None:
        """Reject state changing requests without a valid CSRF token."""
        if request.endpoint == "static":
            return None
        if request.path.startswith('/internal/'):
            return None
        if request.method.upper() in _SAFE_METHODS:
            return None
        if request.headers.get('Origin') != sso.HOME_ORIGIN:
            abort(403)
        token = _submitted_token()
        expected = csrf_token()
        if not token or not expected:
            abort(400)
        if not _safe_compare(token, expected):
            abort(400)
        return None

    @app.before_request
    def viewer_guard() -> None:
        """Defence in depth: viewers may not change any state."""
        user = getattr(g, "current_user", None)
        if user is None or getattr(user, "kind", None) != "viewer":
            return None
        if request.method.upper() in _SAFE_METHODS:
            return None
        if request.path.startswith('/internal/'):
            return None
        if request.endpoint in VIEWER_ALLOWED_POST | AUTH_ENDPOINTS:
            return None
        view = _view()
        if _is_download(view) and getattr(view, "_noor_viewer_download_ok", False):
            return None
        abort(403)

    @app.after_request
    def security_headers(response):
        """Attach the hardening headers to every response."""
        if request.host.lower() != 'noor.localhost:5310':
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = REFERRER_POLICY
            response.headers["Cache-Control"] = "no-store"
            response.headers.pop('X-Frame-Options', None)
            response.headers['Content-Security-Policy'] = "frame-ancestors http://noor.localhost:5310"
            return response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = REFERRER_POLICY
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        raw = getattr(g, 'issue_sid', None)
        if raw:
            response.set_cookie('noor_sid', raw, httponly=True, samesite='Strict', path='/')
            response.delete_cookie('noor_pre', path='/')
        elif getattr(g, 'clear_sid', False):
            response.delete_cookie('noor_sid', path='/')
        elif getattr(g, 'pre_id', None) and not request.cookies.get('noor_pre'):
            response.set_cookie('noor_pre', g.pre_id, httponly=True, samesite='Strict', path='/')
        return response


def login_required(view: Callable) -> Callable:
    """Only let logged in users through (GET redirects, everything else 401)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            if request.method.upper() in _SAFE_METHODS:
                return redirect(url_for("login"))
            abort(401)
        return view(*args, **kwargs)

    wrapper._noor_login_required = True
    return wrapper


def state_change(view: Callable) -> Callable:
    """Mark a view as a state changing (POST/PUT/PATCH/DELETE) view."""
    view._noor_state_change = True
    return view


def download_route(viewer_ok: bool = False) -> Callable:
    """Mark a view as a download. Downloads are POST routes (the CSRF token travels in the form
    body, never in a URL); viewers are refused unless viewer_ok."""

    def decorator(view: Callable) -> Callable:
        view._noor_download = True
        view._noor_viewer_download_ok = bool(viewer_ok)
        return view

    return decorator


def login(conn, user_id, password):
    """Authenticate ``user_id``/``password`` and start a fresh session.

    Every failure (unknown user, wrong password, disabled account) returns
    ``None`` so that the caller cannot tell the cases apart.
    """
    if not user_id or password is None:
        _equalise(password if password is not None else "")
        return None
    try:
        user = load_user(conn, str(user_id))
    except Exception:  # pragma: no cover - defensive
        user = None
    if user is None:
        _equalise(password)
        return None
    if not _user_enabled(conn, user):
        # Disabled accounts can never log in.
        _equalise(password)
        return None
    password_hash = _password_hash(conn, user)
    if not password_hash or not check_password_hash(password_hash, password):
        return None
    old = getattr(g, 'system_session', None)
    raw, _ = sso.issue(conn, _user_id_of(user) or str(user_id), old['sid_hash'] if old else None)
    g.issue_sid = raw
    g.system_session = sso.touch(conn, sso.digest(raw))
    current_app.extensions['noor_registry']['pending_csrf'].pop(getattr(g, 'pre_id', None), None)
    return user
