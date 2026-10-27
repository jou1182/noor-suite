"""Host router and loopback reverse proxy for isolated web origins."""
from __future__ import annotations

import http.client
from urllib.parse import urlsplit

from flask import abort, current_app, make_response, redirect, request

from . import sso
from .authz import load_user
from .platforms_registry import BROWSER_ORIGINS

HOME_HOST = 'noor.localhost:5310'
LOCAL_ALIASES = {'localhost:5310', '127.0.0.1:5310'}
HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailers', 'transfer-encoding', 'upgrade', 'host', 'content-length'}
WEB_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def route_host():
    host = request.host.lower()
    if host in LOCAL_ALIASES:
        return redirect(sso.HOME_ORIGIN + request.full_path.rstrip('?'), code=302)
    if host == HOME_HOST:
        return None
    platform_id = next((pid for pid, origin in BROWSER_ORIGINS.items()
                        if urlsplit(origin).netloc == host), None)
    if platform_id is None:
        abort(421)
    if request.path.startswith('/internal/'):
        abort(404)
    extension = current_app.extensions['noor_registry']
    conn = extension['get_db']()
    if request.path == '/__noor/enter':
        if request.method != 'GET':
            abort(405)
        psid = sso.exchange_entry(conn, request.args.get('c'), platform_id)
        if not psid:
            abort(403)
        response = redirect('/', code=302)
        response.set_cookie('noor_psid', psid, httponly=True, samesite='Strict', path='/')
        return response
    if request.path.startswith('/__noor/'):
        abort(404)
    psession = sso.platform_session(conn, request.cookies.get('noor_psid'), platform_id)
    if psession is None:
        abort(403)
    if request.method in WEB_METHODS and request.headers.get('Origin') != BROWSER_ORIGINS[platform_id]:
        abort(403)
    parent = conn.execute("SELECT * FROM system_session WHERE sid_hash=? AND state='active'",
                          (psession['parent_sid_hash'],)).fetchone()
    user = load_user(conn, parent['user_id']) if parent else None
    if user is None or not user.enabled:
        abort(403)
    assertion = sso.sign_assertion(extension['signing_key'], user, platform_id,
                                   parent['theme_pref'], parent['csrf_token'],
                                   psession['psid_hash'], extension['bindings'])
    upstream = urlsplit(extension['platforms'][platform_id]['upstream'])
    if upstream.hostname != '127.0.0.1' or upstream.scheme != 'http':
        abort(502)
    headers = {key: value for key, value in request.headers.items()
               if key.lower() not in HOP_HEADERS | {'cookie', 'authorization', 'x-user-email'}
               and not key.lower().startswith('x-noor-')}
    headers['X-Noor-Assertion'] = assertion
    headers['Host'] = upstream.netloc
    path = request.path + ('?' + request.query_string.decode('ascii') if request.query_string else '')
    upstream_conn = http.client.HTTPConnection('127.0.0.1', upstream.port, timeout=5)
    try:
        upstream_conn.request(request.method, path, body=request.get_data(), headers=headers)
        upstream_response = upstream_conn.getresponse()
        data = upstream_response.read()
        response = make_response(data, upstream_response.status)
        for key, value in upstream_response.getheaders():
            if key.lower() not in HOP_HEADERS | {'set-cookie'}:
                response.headers.add(key, value)
        return response
    except (OSError, http.client.HTTPException):
        response = make_response('<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><h1>المنصة متوقفة</h1></html>', 502)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    finally:
        upstream_conn.close()
