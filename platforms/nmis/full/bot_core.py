# -*- coding: utf-8 -*-
"""Shared runtime for the Telegram bot: config, logging, bot/db objects, state, alerts, authorization.

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
import sys
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import schedule
import os
import json
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, UTC
from dotenv import load_dotenv
from db_manager import DBManager, DB_PATH
def decrypt_val(value):  # N5: secrets come from environment variables only; no local vault
    if value is not None and str(value).startswith("FERNET:"):
        raise RuntimeError("encrypted secret values are not supported; set the plain value in the environment")
    return value
from company_profile import PROFILE

# هوية الشركة في كل نصوص البوت -- تُقرأ من company_profile.json حتى لا يظهر
# اسم شركة أخرى لدى أي عميل. القيم الاحتياطية محايدة عمداً.
CO_SHORT = (PROFILE.get("short_ar") or "").strip() or "شركتنا"
CO_SYSTEM = (PROFILE.get("system_title") or "").strip() or "نظام متابعة المنافسات"
CO_TEAM = (PROFILE.get("team_ar") or "").strip() or "فريق المتابعة"
try:
    from pdf_report import send_monthly_report as _send_pdf
    PDF_OK = True
except ImportError:
    PDF_OK = False
try:
    from openai import OpenAI as _OpenAIClient
    _OPENAI_IMPORT_OK = True
except ImportError:
    _OPENAI_IMPORT_OK = False

# ============================================================
# 1. LOAD SECURE CONFIGURATION
# ============================================================
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN = decrypt_val(os.getenv("TELEGRAM_TOKEN"))
CHAT_ID = os.getenv("CHAT_ID")
# Optional but highly recommended: your personal Telegram User ID
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
# ROADMAP_V6 Phase 4: مدير(ون) الموافقة النهائية للموافقة المزدوجة الاختيارية
# (نفس متغير OWNER_TELEGRAM_ID المستخدم في web_dashboard.py لاستعادة كلمة المرور --
#  نفس الشخص/المفهوم "صاحب القرار النهائي"؛ يقبل معرفات متعددة مفصولة بفاصلة)
OWNER_TELEGRAM_IDS = {s.strip() for s in os.getenv("OWNER_TELEGRAM_ID", "").split(",") if s.strip()}
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", 5))
ALLOW_AUTONOMOUS_LOGIN = os.getenv("ALLOW_AUTONOMOUS_LOGIN", "0").strip().lower() in {"1", "true", "yes", "on"}
NO_VNC_URL = os.getenv("NO_VNC_URL", "http://127.0.0.1:6080/vnc.html")
UPTIMEROBOT_URL = os.getenv("UPTIMEROBOT_HEARTBEAT_URL", "")

# ── OpenAI / AI Chat ──────────────────────────────────────────
# AI_MODEL: moved to ai_assistant.py
# نموذج تحويل الصوت لنص (2026-09-23: gpt-transcribe بدل whisper-1 — أرخص $0.0045/دقيقة مقابل $0.006،
# ونصف أخطاء الكلمات على رسائل صوتية عربية، ويحافظ على اللهجة ولا يؤلّف جملاً مع الضوضاء).
# للرجوع: STT_MODEL=whisper-1 في .env
WHISPER_MODEL   = os.getenv("STT_MODEL", "gpt-transcribe").strip()
# AI_MAX_HISTORY: moved to ai_assistant.py

# ── Whisper: قاموس المصطلحات المتخصصة ─────────────────────────
# يُمرَّر لـ Whisper كـ prompt حتى يتعرف على مصطلحات المجال
# هذا يرفع دقة التفريغ بشكل كبير للأسماء والمصطلحات المتخصصة
WHISPER_DOMAIN_PROMPT = (
    f"المناقصات الحكومية السعودية، شركة {CO_SHORT}، "
    "العروض الفنية، الضمان الابتدائي، تاريخ التقديم، كراسة الشروط، "
    "الترسية، طرح المناقصة، العطاء، الجهة المالكة، المقاول، الاستشاري، "
    "أمانة الرياض، أمانة جدة، أمانة مكة، وزارة النقل، وزارة الإسكان، "
    "وزارة الشؤون البلدية، هيئة تطوير المنطقة، أرامكو، سابك، "
    "المهندس المعتمد، التصنيف، الدرجة الأولى، الثانية، الثالثة، "
    "مناقصة، منافسة، مشروع، طرق، جسور، مباني، كهرباء، ميكانيكا، "
    "موارد بشرية، رقم المنافسة، الحالة، نشط، مغلق، مُرسى، "
    # ── كلمات عامية مصرية لتحسين دقة Whisper ────────────────
    "دلوقتي، بعدين، لقيت، مش، تمام، كمان، بس، يعني، إيه، طب، "
    "اتنين، تلاتة، أربعة، خمسة، ستة، سبعة، تمانية، تسعة، عشرة، "
    "حداشر، اتناشر، عشرين، تلاتين، مية، ميتين، ألفين"
)

if not TELEGRAM_TOKEN or not CHAT_ID:
    raise RuntimeError("CRITICAL: TELEGRAM_TOKEN or CHAT_ID missing from .env file!")

# ============================================================
# 2. PROFESSIONAL LOGGING SYSTEM (Captures ALL modules)
# ============================================================
LOG_DIR = Path(os.getenv("BOT_LOG_DIR") or BASE_DIR / "logs")  # BOT_LOG_DIR: tests keep logs away from the live bot.log
LOG_DIR.mkdir(exist_ok=True)

log_fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s - %(message)s')

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_fmt)

# File Handler (daily rotation, 30 days retention)
file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=LOG_DIR / "bot.log",
    when="midnight", interval=1, backupCount=30, encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_fmt)

# KEY FIX: Configure ROOT logger so ALL modules are captured
# Previously only "BotDaemon" logger had handlers, causing EngineCore
# and DB_Manager errors to be silently swallowed!
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

logger = logging.getLogger("BotDaemon")

# Suppress noisy libraries — WARNING kept for telebot so handler exceptions surface
telebot.logger.setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("WDM").setLevel(logging.WARNING)

# ============================================================
# 3. INITIALIZE BOT & DATABASE
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)
if os.getenv("NOOR_TELEGRAM_ENABLED") != "1":  # N7: off unless a separate test bot is enabled explicitly
    raise RuntimeError("Telegram bot disabled; set NOOR_TELEGRAM_ENABLED=1 with a separate test bot")
db = DBManager()

# ============================================================
# JOB OVERLAP GUARD
# Prevents job_check_platform from running concurrently with itself
# if a previous cycle takes longer than CHECK_INTERVAL minutes.
# Without this, the scheduler fires a second job while the first
# is still scraping -> duplicate Telegram messages.
# ============================================================
_job_lock    = threading.Lock()
_backup_lock = threading.Lock()   # Prevents duplicate backup sends on concurrent restarts

# ── نظام التنبيه التلقائي عند الأعطال الصامتة ─────────────────
# إذا تكرر نفس الخطأ 3 مرات في 10 دقائق → رسالة تنبيه فورية للمسؤول
_error_tracker: dict = {}          # error_key → [timestamp, timestamp, ...]
_ERROR_ALERT_THRESHOLD  = 3        # عدد التكرارات قبل التنبيه
_ERROR_ALERT_WINDOW_SEC = 600      # نافزة الوقت (10 دقائق)
_last_alert_sent: dict  = {}       # error_key → last alert timestamp (لمنع الإزعاج)
_ALERT_COOLDOWN_SEC     = 1800     # لا ترسل نفس التنبيه مرتين خلال 30 دقيقة

def _track_error(error_key: str, detail: str = ""):
    """
    سجّل خطأً وأرسل تنبيهاً للمسؤول إذا تكرر كثيراً.
    error_key: وصف مختصر للخطأ (مثل 'OpenAI API' أو 'Whisper')
    detail: تفاصيل إضافية للرسالة
    """
    now = time.time()
    timestamps = _error_tracker.setdefault(error_key, [])

    # احتفظ فقط بالأخطاء ضمن النافذة الزمنية
    timestamps[:] = [t for t in timestamps if now - t < _ERROR_ALERT_WINDOW_SEC]
    timestamps.append(now)

    if len(timestamps) < _ERROR_ALERT_THRESHOLD:
        return  # لم يصل للحد بعد

    # تحقق من cooldown — لا تُزعج بنفس التنبيه كل دقيقة
    last_sent = _last_alert_sent.get(error_key, 0)
    if now - last_sent < _ALERT_COOLDOWN_SEC:
        return

    _last_alert_sent[error_key] = now

    # بناء رسالة التنبيه
    count    = len(timestamps)
    since    = int((now - timestamps[0]) / 60)
    msg = (
        f"🚨 *تنبيه — عطل متكرر*\n\n"
        f"*النوع:* `{error_key}`\n"
        f"*التكرار:* {count} مرة خلال {since} دقيقة\n"
    )
    if detail:
        msg += f"*التفاصيل:* `{detail[:200]}`\n"
    msg += f"\n⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}"

    try:
        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
        logger.warning(f"ALERT SENT: {error_key} × {count} in {since}min")
    except Exception as e:
        logger.error(f"Failed to send error alert: {e}")
STATE_FILE = BASE_DIR / "output" / "bot_state.json"
SESSION_ALERT_FILE = BASE_DIR / "output" / "session_alert_sent.flag"
SESSION_FAIL_ALERT_AFTER = 3  # consecutive scheduled-fetch failures before alerting (~15 min at 5-min interval)
BACKUP_ALERT_FILE = BASE_DIR / "output" / "backup_alert_sent.flag"

def utc_now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read bot_state.json; starting with empty runtime state.")
        return {}

def save_state(**updates):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = load_state()
    state.update(updates)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state

def is_paused():
    return bool(load_state().get("paused", False))

def fmt_ts(ts):
    return ts or "غير متوفر"

def file_status(path):
    path = Path(path)
    if not path.exists():
        return "غير موجود"
    age_minutes = int((time.time() - path.stat().st_mtime) / 60)
    size_kb = max(1, int(path.stat().st_size / 1024))
    return f"موجود، الحجم {size_kb}KB، آخر تعديل منذ {age_minutes} دقيقة"

def build_health_report():
    state = load_state()
    stats = db.get_system_stats() or {}
    export_status = "غير متوفر"
    status_path = BASE_DIR / "output" / "export_status.txt"
    if status_path.exists():
        export_status = status_path.read_text(encoding="utf-8", errors="ignore").strip() or "فارغ"

    session_ok = "تعمل" if export_status == "success" else "تحتاج فحص"
    paused_text = "متوقفة مؤقتاً" if state.get("paused") else "تعمل"
    auto_login_text = "مفعّل" if ALLOW_AUTONOMOUS_LOGIN else "مغلق لحماية MFA"

    return (
        f"🩺 *فحص صحة {CO_SYSTEM}*\n"
        "━━━━━━━━━━━━━━\n"
        f"الحالة: *{paused_text}*\n"
        f"آخر فحص: `{fmt_ts(state.get('last_check_at'))}`\n"
        f"آخر نجاح: `{fmt_ts(state.get('last_success_at'))}`\n"
        f"آخر نتيجة: `{state.get('last_result', 'غير متوفر')}`\n\n"
        f"آخر نسخة احتياطية: `{fmt_ts(state.get('last_backup_at'))}`\n"
        f"نتيجة النسخ: `{state.get('last_backup_result', 'غير متوفر')}`\n\n"
        f"المنافسات النشطة: *{stats.get('active_count', '؟')}*\n"
        f"المعلقات: *{stats.get('pending_count', '؟')}*\n"
        f"المغلقة: *{stats.get('closed_count', '؟')}*\n\n"
        f"جلسة المنصة: *{session_ok}* (`{export_status}`)\n"
        f"الدخول التلقائي لمايكروسوفت: *{auto_login_text}*\n"
        f"ملف الكوكيز: {file_status(BASE_DIR / 'output' / 'portal_cookies.json')}\n"
        f"قاعدة البيانات: {file_status(DB_PATH)}\n"
        f"ملف الماستر: {file_status(BASE_DIR / 'output' / 'Master_Tenders.xlsx')}\n"
    )

def send_session_expired_alert():
    # Re-send alert every 24h so user is reminded if they miss the first one
    RESEND_HOURS = 24
    if SESSION_ALERT_FILE.exists():
        try:
            age_hours = (time.time() - SESSION_ALERT_FILE.stat().st_mtime) / 3600
            if age_hours < RESEND_HOURS:
                return
        except Exception:
            pass  # If we can't check age, re-send to be safe

    err_msg = (
        "⚠️ *تعذّر سحب ملف المناقصات من المنصة*\n\n"
        "السبب إما انتهاء جلسة الدخول أو توقف موقع المنصة مؤقتاً.\n\n"
        "إن استمر: من جهاز المشغّل شغّل `Update_Server_Session.bat` وسجّل الدخول.\n\n"
        "ستصلك رسالة تلقائية عند عودة السحب. للفحص الفوري أرسل /news."
    )
    bot.send_message(CHAT_ID, err_msg, parse_mode="Markdown")
    SESSION_ALERT_FILE.write_text(utc_now_iso(), encoding="utf-8")

def send_backup_failure_alert(error):
    today = time.strftime("%Y-%m-%d")
    if BACKUP_ALERT_FILE.exists() and BACKUP_ALERT_FILE.read_text(encoding="utf-8").strip() == today:
        return
    bot.send_message(
        CHAT_ID,
        "⚠️ *فشل إرسال النسخة الاحتياطية اليومية*\n\n"
        f"التاريخ: `{today}`\n"
        f"السبب: `{str(error)[:500]}`\n\n"
        "يمكن تنفيذ /backup يدوياً بعد فحص /health.",
        parse_mode="Markdown"
    )
    BACKUP_ALERT_FILE.write_text(today, encoding="utf-8")

def ping_uptimerobot():
    """Send heartbeat ping to UptimeRobot. If pings stop, UptimeRobot alerts the admin."""
    if not UPTIMEROBOT_URL:
        return
    try:
        import requests as _req
        _req.get(UPTIMEROBOT_URL, timeout=10)
        logger.debug("UptimeRobot heartbeat sent.")
    except Exception as e:
        logger.warning(f"UptimeRobot ping failed (non-critical): {e}")

def read_last_log_lines(limit=50):
    log_path = LOG_DIR / "bot.log"
    if not log_path.exists():
        return "ملف السجل غير موجود بعد."
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-limit:]) or "ملف السجل فارغ."

# ============================================================
# 5. SECURITY HELPERS
# ============================================================
def is_authorized(message_or_call):
    """
    Auth — two valid scenarios:
      A) Message from the designated group CHAT_ID
         (if ADMIN_USER_ID is set, only that user is allowed inside the group)
      B) Private DM to the bot
         (if ADMIN_USER_ID is set, restricted to that user only;
          if not set, any private chat is allowed — the bot token is the security gate)
    """
    chat_obj  = message_or_call.chat if hasattr(message_or_call, 'chat') else message_or_call.message.chat
    from_user = getattr(message_or_call, "from_user", None)
    user_id   = str(getattr(from_user, "id", None))
    chat_id   = str(chat_obj.id)
    chat_type = getattr(chat_obj, "type", "")

    # ── Scenario A: message from the designated group ─────────────────────────
    if chat_id == str(CHAT_ID):
        if ADMIN_USER_ID and user_id != str(ADMIN_USER_ID):
            return False
        return True

    # ── Scenario B: private DM ────────────────────────────────────────────────
    if chat_type == "private":
        # If admin ID is configured → restrict to that user
        if ADMIN_USER_ID:
            if user_id == str(ADMIN_USER_ID):
                return True
        else:
            # No admin filter configured → log the user ID (helpful for first setup)
            # and allow the DM (the bot token itself is the access gate)
            logger.info(f"Private DM received from user_id={user_id}. "
                        "Set ADMIN_USER_ID in .env to restrict access to this user only.")
            return True

    logger.warning(f"Rejected: chat_id={chat_id} user_id={user_id} type={chat_type}")
    return False

