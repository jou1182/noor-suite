"""Home-owned opaque sessions, one-use entries, and short Ed25519 assertions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator, FormatChecker

HOME_ORIGIN = "http://noor.localhost:5310"
IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=8)
_lock = threading.RLock()


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat()


def digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def token():
    return secrets.token_urlsafe(32)


def load_private_key(config):
    path = config.signing_key_file
    root = Path(__file__).resolve().parents[3]
    if path is None or not path.is_absolute() or path.resolve().is_relative_to(root):
        raise ValueError('NOOR_HOME_SIGNING_KEY_FILE must be an absolute path outside the repository')
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError('NOOR_HOME_SIGNING_KEY_FILE must contain an Ed25519 PEM private key') from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('NOOR_HOME_SIGNING_KEY_FILE must contain an Ed25519 PEM private key')
    return key


def revoke(conn, sid_hash, state='revoked'):
    if state not in ('logged_out', 'expired', 'revoked'):
        raise ValueError('invalid session transition')
    with conn:
        changed = conn.execute("UPDATE system_session SET state=? WHERE sid_hash=? AND state='active'",
                               (state, sid_hash)).rowcount
        if changed:
            conn.execute("UPDATE platform_session SET state='revoked' WHERE parent_sid_hash=?", (sid_hash,))
            conn.execute("UPDATE desktop_handle SET state='locked' WHERE sid_hash=?", (sid_hash,))
    return bool(changed)


def expire_due(conn):
    current = iso(now())
    rows = conn.execute("SELECT sid_hash FROM system_session WHERE state='active' AND (idle_expires_at<=? OR absolute_expires_at<=?)",
                        (current, current)).fetchall()
    for row in rows:
        revoke(conn, row['sid_hash'], 'expired')


def touch(conn, sid_hash):
    if not sid_hash:
        return None
    with _lock:
        expire_due(conn)
        row = conn.execute("SELECT * FROM system_session WHERE sid_hash=? AND state='active'", (sid_hash,)).fetchone()
        if row is None:
            return None
        current = now()
        with conn:
            conn.execute('UPDATE system_session SET last_seen_at=?, idle_expires_at=? WHERE sid_hash=?',
                         (iso(current), iso(current + IDLE), sid_hash))
        return conn.execute('SELECT * FROM system_session WHERE sid_hash=?', (sid_hash,)).fetchone()


def issue(conn, user_id, old_sid_hash=None):
    with _lock:
        if old_sid_hash:
            revoke(conn, old_sid_hash, 'revoked')
        raw = token()
        current = now()
        csrf = token()
        with conn:
            conn.execute('INSERT INTO system_session (sid_hash,user_id,created_at,last_seen_at,idle_expires_at,absolute_expires_at,state,csrf_token) VALUES (?,?,?,?,?,?,?,?)',
                         (digest(raw), user_id, iso(current), iso(current), iso(current + IDLE), iso(current + ABSOLUTE), 'active', csrf))
        return raw, csrf


def entry_code(conn, sid_hash, platform_id):
    raw = token()
    current = now()
    with conn:
        conn.execute('INSERT INTO entry_code (code_hash,parent_sid_hash,platform_id,issued_at,expires_at) VALUES (?,?,?,?,?)',
                     (digest(raw), sid_hash, platform_id, iso(current), iso(current + timedelta(seconds=60))))
    return raw


def exchange_entry(conn, raw, platform_id):
    if not raw:
        return None
    current = iso(now())
    with _lock, conn:
        row = conn.execute('SELECT parent_sid_hash FROM entry_code WHERE code_hash=? AND platform_id=? AND used_at IS NULL AND expires_at>?',
                           (digest(raw), platform_id, current)).fetchone()
        if row is None:
            return None
        parent = touch(conn, row['parent_sid_hash'])
        if parent is None:
            return None
        changed = conn.execute('UPDATE entry_code SET used_at=? WHERE code_hash=? AND used_at IS NULL',
                               (current, digest(raw))).rowcount
        if changed != 1:
            return None
        psid = token()
        conn.execute("INSERT INTO platform_session (psid_hash,parent_sid_hash,platform_id,created_at,state) VALUES (?,?,?,?,'active')",
                     (digest(psid), row['parent_sid_hash'], platform_id, current))
        return psid


def platform_session(conn, raw, platform_id):
    if not raw:
        return None
    row = conn.execute("SELECT * FROM platform_session WHERE psid_hash=? AND platform_id=? AND state='active'",
                       (digest(raw), platform_id)).fetchone()
    if row is None or touch(conn, row['parent_sid_hash']) is None:
        return None
    return row


def principal_user_id(local_id):
    return 'U-' + hashlib.sha256(local_id.encode('utf-8')).hexdigest()[:8]


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def sign_assertion(key, user, platform_id, theme, csrf, psid_hash, bindings):
    from .platforms_registry import BROWSER_ORIGINS
    if platform_id not in BROWSER_ORIGINS:
        raise ValueError('unknown web platform')
    current = now()
    nonce = _b64(secrets.token_bytes(16))
    payload = {'schema': 'noor.principal/v1', 'platform_id': platform_id,
               'user_id': principal_user_id(user.user_id), 'display_name': user.display_name,
               'role': user.kind, 'platform_permissions': list(ROLE_PERMISSIONS[platform_id][user.kind]),
               'csrf': csrf, 'theme': theme, 'issued_at': iso(current),
               'expires_at': iso(current + timedelta(seconds=5)), 'nonce': nonce,
               'synthetic': True}
    encoded = _b64(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    message = 'v1.' + encoded
    with _lock:
        for old, (_, expiry) in list(bindings.items()):
            if expiry <= current:
                del bindings[old]
        bindings[nonce] = (psid_hash, current + timedelta(seconds=5))
    return message + '.' + _b64(key.sign(message.encode('ascii')))


ROLE_PERMISSIONS = {
    'radar': {'proposal_manager': ('read','send_candidate'), 'review_approver': ('read',), 'member': ('read',), 'viewer': ('read',)},
    'quick_analysis': {'proposal_manager': ('read','upload_analyze'), 'review_approver': ('read',), 'member': ('read','upload_analyze'), 'viewer': ('read_report',)},
    'nmis_full': {'proposal_manager': ('read','full','accept_tender'), 'review_approver': ('read','approve_gaps'), 'member': ('read','own_tasks'), 'viewer': ('read',)},
    'jouready': {'proposal_manager': ('read','run_review'), 'review_approver': ('read','approve_report'), 'member': ('read',), 'viewer': ('read',)},
    'atpas': {'proposal_manager': ('read_outputs','build'), 'review_approver': ('read_outputs',),
              'member': ('read_outputs','build'), 'viewer': ('read_outputs',)},
}

ACTION_TO_CORE = {
    'read': 'view_tender', 'read_report': 'view_tender', 'read_outputs': 'view_tender',
    'send_candidate': 'import_review', 'upload_analyze': 'run_review',
    'full': 'request_build', 'accept_tender': 'accept_tender',
    'approve_gaps': 'approve_gaps', 'own_tasks': 'update_own_task',
    'build': 'request_build', 'run_review': 'run_review',
    'approve_report': 'approve_report',
}


def register_authz(app):
    import os
    import re
    from flask import current_app, jsonify, request
    from .authz import AuthzError, authorize, load_user
    from noor_sso.verify import AssertionVerifier, AssertionError401
    from .platforms_registry import BROWSER_ORIGINS

    extension = app.extensions['noor_registry']
    key = extension['signing_key'].public_key()
    verifiers = {platform: AssertionVerifier(key, platform) for platform in BROWSER_ORIGINS}
    key_names = {platform: 'NOOR_PLATFORM_KEY_' + platform.upper() for platform in BROWSER_ORIGINS}

    @app.post('/internal/authz/check')
    def internal_authz_check():
        if 'Origin' in request.headers:
            return '', 403
        authorization = request.headers.get('Authorization', '')
        supplied = authorization[len('Noor-Platform '):] if authorization.startswith('Noor-Platform ') else ''
        platform = next((pid for pid, name in key_names.items()
                         if os.environ.get(name) and hmac.compare_digest(supplied.encode(), os.environ[name].encode())), None)
        conn = extension['get_db']()
        body = request.get_json(silent=True) or {}
        tender = body.get('tender_id') if isinstance(body.get('tender_id'), str) and re.fullmatch(r'NT-\d{4}-\d{4}', body['tender_id']) else 'NT-0000-0000'
        action = body.get('action') if isinstance(body.get('action'), str) and re.fullmatch(r'[a-z_]{2,40}', body['action']) else 'invalid'
        claimed = None
        actor_id = None
        result = 'bad_platform_key' if platform is None else 'bad_assertion'
        reason = 'expired'
        allowed = False
        if platform:
            try:
                claimed = verifiers[platform].verify(body.get('assertion', ''), replay=False)
                binding = extension['bindings'].get(claimed['nonce'])
                if binding is None or binding[1] <= now():
                    result = 'expired'
                else:
                    psession = conn.execute("SELECT * FROM platform_session WHERE psid_hash=? AND platform_id=? AND state='active'",
                                            (binding[0], platform)).fetchone()
                    parent = touch(conn, psession['parent_sid_hash']) if psession else None
                    user = load_user(conn, parent['user_id']) if parent else None
                    if not user or not user.enabled or principal_user_id(user.user_id) != claimed['user_id']:
                        result = 'no_session'
                    else:
                        actor_id = user.user_id
                    if actor_id and action not in ROLE_PERMISSIONS[platform][user.kind]:
                        result, reason = 'forbidden', 'wrong_role'
                    elif actor_id:
                        try:
                            authorize(conn, user, tender, ACTION_TO_CORE[action],
                                      task_id=body.get('task_id') if action == 'own_tasks' and isinstance(body.get('task_id'), str) else None)
                            allowed, result, reason = True, 'ok', 'ok'
                        except AuthzError as exc:
                            result = 'forbidden'
                            reason = {'no_tender': 'tender_not_found', 'no_permission': 'no_membership',
                                      'read_only': 'viewer_read_only'}.get(exc.reason, 'wrong_role')
            except (AssertionError401, TypeError, KeyError):
                result = 'bad_assertion'
        document = {'schema': 'noor.authz-decision/v1', 'platform_id': platform or 'nmis_full',
                    'user_id': claimed['user_id'] if claimed else 'U-00000000',
                    'tender_id': tender, 'action': action, 'allowed': allowed,
                    'reason': reason, 'decided_at': iso(now()), 'synthetic': True}
        with conn:
            conn.execute('INSERT INTO access_decision_log (at,platform_id,user_id,result,action,tender_id) VALUES (?,?,?,?,?,?)',
                         (iso(now()), platform, actor_id,
                          result, action, tender))
            conn.execute('DELETE FROM access_decision_log WHERE at<?', (iso(now() - timedelta(days=30)),))
        return jsonify(document), 200 if platform else 401


def start_expiry_timer(app):
    def loop():
        while True:
            try:
                from .db import open_db
                conn = open_db(app.config['NOOR_CONFIG'].data_dir)
                try:
                    expire_due(conn)
                    with conn:
                        conn.execute('DELETE FROM access_decision_log WHERE at<?',
                                     (iso(now() - timedelta(days=30)),))
                    with _lock:
                        bindings = app.extensions['noor_registry']['bindings']
                        for nonce, (_, expiry) in list(bindings.items()):
                            if expiry <= now():
                                del bindings[nonce]
                finally:
                    conn.close()
            except Exception:
                pass
            threading.Event().wait(1)
    threading.Thread(target=loop, daemon=True, name='noor-session-expiry').start()
