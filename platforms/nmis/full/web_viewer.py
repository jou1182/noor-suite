# -*- coding: utf-8 -*-
"""حساب العرض للطلاب والعملاء (2026-09-25) — مع «وضع العرض» (features: demo).

الدخول من /viewer بكلمة مرور تصدرها الإدارة من /admin/demo (تظهر مرة واحدة، يُحفظ hash فقط في app_config).
الجلسة = جلسة الإدارة والفريق للعرض (ok + admin_ok) + علامة viewer، فيرى كل الشاشات كما هي. والحماية
في الخادم لا في الواجهة: كل طلب يغيّر شيئاً (غير GET) يُرفض، ومعه صفحات GET الحساسة (نسخة قاعدة البيانات،
قاعدة المعرفة، استعادة كلمة المرور). البريد ورابط Google يُخفيان في صفحاتهما (web_admin / web_source).
شريط أعلى كل صفحة يوضح أنه حساب عرض. الدخول الحقيقي بعده يبدأ جلسة نظيفة (end_viewer_session).
"""
import secrets
import sqlite3
from contextlib import closing

from flask import abort, jsonify, redirect, render_template_string, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import demo_core
from company_profile import feature_enabled
from web_core import (DB_PATH, _LOCKOUT_MSG, _client_ip, _login_blocked, _login_failed, _login_succeeded,
                      admin_required, app, is_viewer)

CFG_HASH = "viewer_pwd_hash"
# الدخول الحقيقي مسموح (يبدأ جلسة نظيفة)؛ غيرها من طلبات التعديل مرفوض
LOGIN_POSTS = {"/login", "/admin/login", "/engineer", "/viewer"}
BLOCKED_GET = ("/admin/db-backup", "/admin/knowledge", "/admin/forgot", "/forgot")
READ_ONLY_MSG = "👁️ حساب العرض للمشاهدة فقط — لا يُحفظ أي تغيير."


def _enabled() -> bool:
    return feature_enabled(demo_core.FEATURE)


def _conn():
    return closing(sqlite3.connect(str(DB_PATH)))


def _get_hash() -> str:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT value FROM app_config WHERE key=?", (CFG_HASH,)).fetchone()
        return (row[0] if row else "") or ""
    except sqlite3.Error:
        return ""


def _set_hash(value: str):
    with _conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (CFG_HASH, value))
        conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                     ("VIEWER_ISSUED" if value else "VIEWER_DISABLED", "viewer", "", "WebAdmin"))
        conn.commit()


def status() -> dict:
    return {"enabled": bool(_get_hash())}


# ── الحماية: قبل كل طلب ──────────────────────────────────────────────────
@app.before_request
def viewer_read_only():
    if not session.get("viewer"):
        return None
    path = request.path
    blocked = (request.method not in ("GET", "HEAD", "OPTIONS") and path not in LOGIN_POSTS) or \
        any(path == p or path.startswith(p + "/") for p in BLOCKED_GET)
    if not blocked:
        return None
    if path.startswith("/api/") or request.is_json or request.accept_mimetypes.best == "application/json" \
            or request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.method != "GET":
        return jsonify({"ok": False, "msg": READ_ONLY_MSG, "error": READ_ONLY_MSG}), 403
    return render_template_string(_BLOCKED_HTML, msg=READ_ONLY_MSG), 403


# ── شريط «حساب عرض» أعلى كل صفحة ────────────────────────────────────────
_BANNER = ('<div id="viewerBar" role="status" style="position:sticky;top:0;z-index:2000;display:flex;gap:12px;'
           'justify-content:center;align-items:center;flex-wrap:wrap;padding:7px 14px;background:#8A5A00;color:#fff;'
           'font:700 13px Tajawal,sans-serif;direction:rtl">👁️ حساب عرض — تصفّح كل الشاشات بحرية؛ لا يُحفظ أي تغيير'
           '<a href="/logout" style="color:#fff;text-decoration:underline">خروج</a></div>')


@app.after_request
def viewer_banner(resp):
    if session.get("viewer") and resp.mimetype == "text/html" and resp.status_code == 200             and not resp.direct_passthrough and not resp.is_streamed:
        html = resp.get_data(as_text=True)
        i = html.find("<body")
        j = html.find(">", i) if i >= 0 else -1
        if j >= 0:
            resp.set_data(html[:j + 1] + _BANNER + html[j + 1:])
    return resp


# ── الدخول ───────────────────────────────────────────────────────────────
@app.route("/viewer", methods=["GET", "POST"])
def viewer_login():
    if not _enabled() or not _get_hash():
        abort(404)
    error = ""
    if request.method == "POST":
        ip = _client_ip()
        if _login_blocked(ip):
            error = _LOCKOUT_MSG
        elif check_password_hash(_get_hash(), request.form.get("password", "")):
            _login_succeeded(ip)
            session.clear()
            session.update({"viewer": True, "ok": True, "admin_ok": True})
            return redirect("/tasks")
        else:
            _login_failed(ip)
            error = "كلمة المرور غير صحيحة"
    return render_template_string(_LOGIN_HTML, error=error)


# ── الإدارة: إصدار/إيقاف كلمة مرور العرض (من صفحة «وضع العرض») ─────────────
@app.route("/admin/demo/viewer", methods=["POST"])
@admin_required
def admin_demo_viewer():
    if not _enabled():
        abort(404)
    if (request.get_json(silent=True) or {}).get("action") == "disable":
        _set_hash("")
        return jsonify({"ok": True, "enabled": False})
    password = "-".join(secrets.token_hex(2) for _ in range(3))      # مثل 3f9a-07c2-b41e: سهلة الإملاء في المحاضرة
    _set_hash(generate_password_hash(password))
    return jsonify({"ok": True, "enabled": True, "password": password, "url": request.host_url.rstrip("/") + "/viewer"})


_LOGIN_HTML = """<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ co.short_ar }} — دخول العرض</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;800&display=swap" rel="stylesheet">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F2F5F9;color:#16233B;font-family:Tajawal,sans-serif}
form{background:#fff;border:1.5px solid #16233B;border-radius:6px;padding:26px 28px;width:min(360px,92vw)}
img{height:54px;display:block;margin:0 auto 10px}h1{font-size:20px;margin:0 0 4px;text-align:center}
p{margin:0 0 16px;color:#3A4A66;font-size:13.5px;text-align:center}
input{width:100%;box-sizing:border-box;border:1px solid #CBD5E1;border-radius:8px;padding:10px;font:inherit;direction:ltr;text-align:center}
button{width:100%;margin-top:12px;border:0;border-radius:8px;padding:11px;background:{{ co.theme_primary or '#1F4C8F' }};color:#fff;font:700 15px Tajawal,sans-serif;cursor:pointer}
.err{color:#B42318;font-weight:700;text-align:center;margin-top:10px}</style>{% include "_skin.html" %}</head>
<body><form method="post"><img src="/logo" alt=""><h1>👁️ دخول العرض</h1>
<p>تصفّح النظام كاملاً كما تراه الإدارة — للمشاهدة فقط.</p>
<label for="pw" style="font-size:13px;font-weight:700">كلمة مرور العرض</label>
<input id="pw" name="password" type="password" autocomplete="off" required autofocus>
<button type="submit">دخول</button>{% if error %}<div class="err" role="alert">{{ error }}</div>{% endif %}</form></body></html>"""

_BLOCKED_HTML = """<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>للمشاهدة فقط</title>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700&display=swap" rel="stylesheet"></head>
<body style="font-family:Tajawal,sans-serif;display:grid;place-items:center;min-height:90vh;background:#F2F5F9;color:#16233B">
<div style="text-align:center"><h1 style="font-size:22px">{{ msg }}</h1><a href="javascript:history.back()">↩ رجوع</a></div></body></html>"""
