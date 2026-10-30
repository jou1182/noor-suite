# -*- coding: utf-8 -*-
"""Dashboard core: Flask app, config, request hooks, DB migrations, app config, rate limiting, auth decorators.

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
VERSION = "5.22.0"   # ← bump this on every deploy (prevents old-file regressions)

from flask import Flask, render_template_string, request, redirect, session, jsonify, abort, Response
from company_profile import PROFILE
import theme_palette
import queue as _queue
import threading as _threading
import json as _json
import sqlite3, os, functools, secrets, base64, time, hmac, logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
def decrypt_val(value):  # N5: secrets come from environment variables only; no local vault
    if value is not None and str(value).startswith("FERNET:"):
        raise RuntimeError("encrypted secret values are not supported; set the plain value in the environment")
    return value
from admin_templates import ADMIN_LOGIN_HTML, ADMIN_PANEL_HTML, ADMIN_FORGOT_HTML
from dashboard_templates import (LOGIN_HTML, TENDER_DETAIL_HTML, DASHBOARD_HTML,
                                 RESULTS_HTML, ENGINEER_LOGIN_HTML,
                                 ENGINEER_DASH_HTML, ENGINEER_VIEW_HTML, OWNERS_HTML,
                                 DASH_FORGOT_HTML)

app = Flask(__name__)
@app.context_processor
def _inject_company():
    return {'co': PROFILE}

# ── Real-time SSE: one Queue per connected dashboard client ──
_sse_clients: list = []
_sse_lock = _threading.Lock()

def push_sse_event(event_type: str, data: dict = None):
    # Push an event to all connected dashboard clients (non-blocking).
    msg = _json.dumps({"type": event_type, "data": data or {}, "ts": int(time.time())})
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


# ── Secret key: env var wins; otherwise persist one to disk so
#    sessions survive service restarts (random-per-boot logged everyone out) ──
_secret = os.getenv("DASHBOARD_SECRET")
if not _secret:
    _secret_file = Path(__file__).parent / ".dashboard_secret"
    try:
        if _secret_file.exists():
            _secret = _secret_file.read_text(encoding="utf-8").strip()
        if not _secret:
            _secret = secrets.token_hex(32)
            _secret_file.write_text(_secret, encoding="utf-8")
            try:
                os.chmod(_secret_file, 0o600)
            except OSError:
                pass
    except OSError:
        _secret = _secret or secrets.token_hex(32)
app.secret_key = _secret

# مسار .env الحقيقي لهذه النسخة -- يُستخدم للقراءة (fallback فقط لو DB_PATH غير مضبوط) وللكتابة في
# مسارات استعادة/تغيير كلمات المرور أدناه -- دائماً مجلد هذا الملف نفسه،
# مش مسار /opt/noor-tender مكتوب حرفياً بالخطأ (كان بيخلي أي مستأجر/ديمو
# يكتب فوق إعدادات الإنتاج الحقيقي بدل إعداداته الخاصة عند استعادة كلمة المرور).
ENV_PATH = str(Path(__file__).parent / ".env")

from instance_paths import DEFAULT_DB_PATH, LOGO_FILE
DB_PATH  = Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)
PORT     = int("5311")

# ── Admin Control Panel ──────────────────────────────────────────
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()  # per-tenant owner email

# ── Password recovery: owner's private Telegram DM (not the shared group CHAT_ID) ──
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID", "").strip()  # dashboard-only, distinct from bot_daemon.py's ADMIN_USER_ID RBAC var
try:
    TELEGRAM_TOKEN = decrypt_val(os.getenv("TELEGRAM_TOKEN", "")) if os.getenv("NOOR_TELEGRAM_ENABLED") == "1" else ""  # N7
except Exception:
    TELEGRAM_TOKEN = ""


# ── Security: only accept connections from localhost (Cloudflare tunnel) ──
# Direct IP access (bypass Cloudflare) is blocked.
_ALLOWED_HOSTS = {'127.0.0.1', '::1', '::ffff:127.0.0.1'}

@app.before_request
def block_direct_ip_access():
    ip = request.remote_addr
    if ip not in _ALLOWED_HOSTS:
        abort(403)  # Forbidden — use your Cloudflare Tunnel domain

# ── v5.6.3: انتهاء الجلسة بعد ساعتين من عدم النشاط ──
SESSION_IDLE_SECONDS = int(os.getenv("SESSION_IDLE_SECONDS",
                           str(int(os.getenv("SESSION_IDLE_HOURS", "2")) * 3600)))

@app.before_request
def session_idle_guard():
    if not (session.get("ok") or session.get("admin_ok") or session.get("eng_ok")):
        return
    now = int(time.time())
    last = session.get("last_seen")
    if last and now - int(last) > SESSION_IDLE_SECONDS:
        was_eng = bool(session.get("eng_ok")) and not session.get("ok")
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"error": "session_expired"}), 401
        return redirect(("/engineer" if was_eng else "/login") + "?expired=1")
    # التفاعل الحقيقي فقط يجدد الجلسة (تصفح أو حفظ) — لا الاستطلاع الآلي للبيانات
    if not request.path.startswith("/api/") or request.method == "POST":
        session["last_seen"] = now

# ── v5.6.8: HTML pages must never be cached (stale tabs broke UI after deploys) ──
@app.after_request
def _no_html_cache(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp

# ── 2026-09-24: ألوان النور المكتوبة في الصفحات ← ألوان الشركة (theme_palette). النور: لا شيء ──
_PALETTE_CACHE = {}

def _palette_map():
    key = tuple(PROFILE.get(k) for k in theme_palette.REFERENCE)
    if key not in _PALETTE_CACHE:
        _PALETTE_CACHE[key] = theme_palette.build_map(PROFILE)
    return _PALETTE_CACHE[key]

@app.after_request
def _apply_palette(resp):
    if resp.mimetype == "text/html" and not resp.direct_passthrough:
        mapping = _palette_map()
        if mapping:
            resp.set_data(theme_palette.apply(resp.get_data(as_text=True), mapping))
    return resp

# ── Company Logo (served via /logo route — browser caches for 1 hour) ──
_LOGO_PNG_B64   = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
def _default_logo_bytes(logo_file=None) -> bytes:
    """شعار النسخة من LOGO_FILE (tenant/) إن وُجد، وإلا الشعار المضمّن."""
    if logo_file:
        try:
            return Path(logo_file).read_bytes()
        except OSError:
            logging.getLogger(__name__).warning("LOGO_FILE unreadable: %s — using built-in logo", logo_file)
    return base64.b64decode(_LOGO_PNG_B64)

_LOGO_PNG_BYTES = _default_logo_bytes(LOGO_FILE)   # read once at startup
_LOGO_DATA_URI  = "/logo"                            # img src → Flask /logo route
# ══════════════════════════════════════════════════════
# DB MIGRATION
# ══════════════════════════════════════════════════════
def ensure_results_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tender_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tender_id       TEXT NOT NULL,
                title           TEXT,
                owner           TEXT,
                business_type   TEXT,
                submission_date TEXT,
                assigned_engineer TEXT,
                did_submit      INTEGER DEFAULT 0,
                result          TEXT DEFAULT 'pending',
                our_price       REAL,
                winning_price   REAL,
                notes           TEXT,
                recorded_at     TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def ensure_tender_notes_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tender_notes (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                tender_id            INTEGER UNIQUE,
                notes                TEXT    DEFAULT '',
                is_extended          INTEGER DEFAULT 0,
                extension_count      INTEGER DEFAULT 0,
                extension_dates      TEXT    DEFAULT '',
                submitted_to_review  INTEGER DEFAULT 0,
                review_date          TEXT    DEFAULT '',
                submitted_to_upload  INTEGER DEFAULT 0,
                upload_submit_date   TEXT    DEFAULT '',
                uploaded_to_platform INTEGER DEFAULT 0,
                platform_upload_date TEXT    DEFAULT '',
                updated_at           TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


# ══════════════════════════════════════════════════════
# APP CONFIG (branding + settings in SQLite)
# ══════════════════════════════════════════════════════
def ensure_guarantees_table():
    """v5.6: initial bank-guarantee tracking per tender."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tender_guarantees (
                tender_row_id INTEGER PRIMARY KEY,
                required      INTEGER DEFAULT 1,
                due_date      TEXT DEFAULT '',
                status        TEXT DEFAULT 'PENDING',
                notes         TEXT DEFAULT '',
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        conn.commit()

def _guarantee_effective_due(submission_date, override):
    """موعد الضمان: يدوي إن حُدد، وإلا تلقائياً قبل التقديم بـ 5 أيام."""
    if (override or "").strip():
        try:
            return datetime.strptime(override.strip()[:10], "%Y-%m-%d").date(), False
        except Exception:
            pass
    try:
        sd = datetime.strptime(str(submission_date).strip()[:10], "%Y-%m-%d").date()
        return sd - timedelta(days=5), True
    except Exception:
        return None, True

def ensure_app_config_table():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                key        TEXT PRIMARY KEY,
                value      TEXT    DEFAULT '',
                updated_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        # البذور تُقرأ من هوية الشركة -- لا أسماء مكتوبة حرفياً حتى لا تتسرب
        # هوية شركة أخرى لأي مستأجر تنقصه مفاتيح app_config.
        defaults = [
            ("company_name_ar", PROFILE.get("name_ar", "")),
            ("company_name_en", PROFILE.get("name_en", "")),
            ("system_title",    PROFILE.get("system_title", "")),
            ("system_subtitle", PROFILE.get("system_subtitle", "لوحة متابعة المنافسات")),
            ("footer_owner",    PROFILE.get("footer_owner", "")),
            ("footer_url",      PROFILE.get("footer_url", "")),
            ("custom_logo_b64", ""),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO app_config(key,value) VALUES(?,?)", defaults
        )
        conn.commit()

def get_config(key, default=""):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT value FROM app_config WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row and row[0] else default
    except Exception:
        return default

def save_config(key, value):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_config(key,value,updated_at) "
            "VALUES(?,?,datetime('now'))",
            (key, value)
        )
        conn.commit()

# ══════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════
# ── Login rate limiting: 5 failed attempts per IP → 15-minute lockout ──
_LOGIN_FAILS: dict = {}
_LOGIN_FAILS_LOCK = _threading.Lock()
_LOGIN_MAX_FAILS  = 5
_LOGIN_WINDOW_SEC = 15 * 60

def _client_ip() -> str:
    # Real visitor IP: behind Cloudflare Tunnel remote_addr is always localhost.
    return (request.headers.get("CF-Connecting-IP")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr or "unknown")

def _login_blocked(ip: str) -> bool:
    now = time.time()
    with _LOGIN_FAILS_LOCK:
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
        if fails:
            _LOGIN_FAILS[ip] = fails
        else:
            _LOGIN_FAILS.pop(ip, None)
        return len(fails) >= _LOGIN_MAX_FAILS

def _login_failed(ip: str):
    with _LOGIN_FAILS_LOCK:
        _LOGIN_FAILS.setdefault(ip, []).append(time.time())

def _login_succeeded(ip: str):
    with _LOGIN_FAILS_LOCK:
        _LOGIN_FAILS.pop(ip, None)

_LOCKOUT_MSG = "تم إيقاف المحاولات مؤقتاً بسبب تكرار الإدخال الخاطئ — حاول مجدداً بعد 15 دقيقة"

# ── Admin password recovery: 6-digit code sent to ADMIN_USER_ID via Telegram DM ──
_RESET_CODES: dict = {}
_RESET_LOCK = _threading.Lock()
_RESET_TTL_SEC   = 10 * 60
_RESET_MAX_TRIES = 5

def _send_telegram_dm(chat_id: str, text: str) -> bool:
    if not (TELEGRAM_TOKEN and chat_id):
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": text}, timeout=8,
        )
        return r.status_code == 200
    except Exception:
        return False

def _new_reset_code(token: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    with _RESET_LOCK:
        _RESET_CODES[token] = {"code": code, "expires": time.time() + _RESET_TTL_SEC, "tries": 0}
    return code

def _check_reset_code(token: str, code: str) -> bool:
    with _RESET_LOCK:
        entry = _RESET_CODES.get(token)
        if not entry or time.time() > entry["expires"]:
            _RESET_CODES.pop(token, None)
            return False
        entry["tries"] += 1
        if entry["tries"] > _RESET_MAX_TRIES:
            _RESET_CODES.pop(token, None)
            return False
        ok = hmac.compare_digest(code, entry["code"])
        if ok:
            _RESET_CODES.pop(token, None)
        return ok

def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **kw):
        if not session.get("ok"):
            return redirect("/login")
        return f(*a, **kw)
    return wrap

# ══════════════════════════════════════════════════════
# ADMIN CONTROL PANEL ROUTES
# ══════════════════════════════════════════════════════

ENG_SESSION_KEYS = ("eng_name", "eng_ok", "eng_account", "eng_must_change")


def is_viewer() -> bool:
    """حساب العرض (web_viewer): يرى ما تراه الإدارة ولا يغيّر شيئاً."""
    return bool(session.get("viewer"))


def end_viewer_session():
    """دخول حقيقي على متصفح عليه حساب العرض يبدأ جلسة نظيفة — لا يرث admin_ok الذي منحه العرض."""
    if session.get("viewer"):
        session.clear()


def end_engineer_session():
    """ينهي هوية المهندس في الجلسة (خروج المهندس، أو دخول الفريق/الإدارة على نفس المتصفح)."""
    for k in ENG_SESSION_KEYS:
        session.pop(k, None)


def session_engineer() -> str:
    """اسم المهندس لجلسة حساب شخصي جاهزة (غيّر كلمته المؤقتة)، وإلا ''. (رمز البوابة المشترك لا يكفي.)"""
    if session.get("eng_ok") and session.get("eng_account") and not session.get("eng_must_change"):
        return session.get("eng_name", "")
    return ""

def admin_required(f):
    @functools.wraps(f)
    def wrap(*a, **kw):
        if not session.get("admin_ok"):
            return redirect("/admin/login")
        return f(*a, **kw)
    return wrap

