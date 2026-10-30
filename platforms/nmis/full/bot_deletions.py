# -*- coding: utf-8 -*-
"""
تنبيه حذف منافسة من المنصة قبل موعدها (2026-09-24).

السبب: في 2026-09-19 اختفت منافستان من منصة النور قبل موعدهما بأسبوع (حُذفتا)، فجاءهما
نفس سطر "ℹ️ للعلم: تم إغلاق المناقصة" الذي يصل عدة مرات أسبوعياً للمنافسات المنتهية طبيعياً
— فضاع بين الرسائل وظل الفريق يعمل عليهما أسبوعاً.

الآن (engine_core يصنّفها DELETED):
  • رسالة حمراء بارزة في المجموعة + تثبيتها أعلى المجموعة
  • رسالة صوتية قصيرة باللهجة الافتراضية (صوت الإشعار يلفت الانتباه)
  • رسالة خاصة للمهندس المسؤول (إن كان مشتركاً) وللمالك
  • زر "✅ اطّلعت وأوقفنا العمل" يسجّل من أكّد ومتى، ويلغي التثبيت
  • تذكير 9 صباحاً و1 ظهراً بأي حذف لم يؤكده أحد
  • /deleted: آخر 30 يوماً (يشمل ما قبل هذا التحديث)

لا يسجّل معالجات تيليجرام بنفسه (ترتيب المعالجات يُحكَم في bot_commands/bot_callbacks).
"""
import html
import io
import json
import os
import re
from datetime import datetime

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_core import CHAT_ID, OWNER_TELEGRAM_IDS, bot, db, logger

PORTAL_TENDERS_URL = os.getenv("PORTAL_URL", "https://www.noor-ms.com").rstrip("/") + "/ar/tendering/tendering_main_index/"
REMINDER_WINDOW_DAYS = 14


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deletion_alerts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id        TEXT NOT NULL,
            title            TEXT,
            owner            TEXT,
            engineer         TEXT,
            deadline         TEXT,
            detected_at      TEXT DEFAULT (datetime('now','localtime')),
            chat_message_id  INTEGER,
            acked_by         TEXT,
            acked_at         TEXT
        )
    """)


def _days_before_deadline(deadline: str):
    try:
        d = datetime.strptime(str(deadline)[:10], "%Y-%m-%d").date()
        return (d - datetime.now().date()).days
    except Exception:
        return None


def _days_phrase(n: int) -> str:
    """مطابقة العدد: يوم واحد، يومين، 3-10 أيام، 11+ يوم."""
    if n == 1:
        return "يوم واحد"
    if n == 2:
        return "يومين"
    return f"{n} أيام" if n <= 10 else f"{n} يوم"


def _short_title(title: str, max_words: int = 8) -> str:
    head = re.split(r"[(\-–,،/]", title or "")[0].strip()
    return " ".join(head.split()[:max_words]) or (title or "")


def _ack_markup(alert_id: int) -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup(row_width=1)
    m.add(InlineKeyboardButton("✅ اطّلعت وأوقفنا العمل عليها", callback_data=f"delack_{alert_id}"),
          InlineKeyboardButton("🔗 افتح المنصة للتأكد", url=PORTAL_TENDERS_URL))
    return m


def build_alert_html(title, owner, engineer, deadline) -> str:
    e = lambda v: html.escape(str(v or "—"))   # العناوين قد تحوي < > & — HTML آمن بعد التهريب
    days = _days_before_deadline(deadline)
    before = f" — <b>قبل موعدها بـ{_days_phrase(days)}</b>" if days and days > 0 else ""
    return (
        "🚨🚨🚨 <b>تنبيه عاجل: منافسة اتحذفت من المنصة!</b> 🚨🚨🚨\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{e(title)}</b>\n"
        f"🏢 الجهة: {e(owner)}\n"
        f"👷 المهندس المسؤول: <b>{e(engineer)}</b>\n"
        f"📅 موعد التقديم كان: {e(str(deadline)[:10])}{before}\n"
        f"🕒 اكتُشف اختفاؤها: {datetime.now():%Y-%m-%d %H:%M}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⛔ <b>أوقفوا العمل عليها فوراً</b> لحد ما نتأكد من المنصة أو من الجهة المالكة.\n"
        "👇 اضغط الزر بعد التأكد"
    )


def voice_text(title, deadline) -> str:
    days = _days_before_deadline(deadline)
    before = f" قبل موعدها بـ{_days_phrase(days)}" if days and days > 0 else ""
    return (f"تنبيه عاجل! منافسة {_short_title(title)} اتحذفت من المنصة{before}. "
            "وقّفوا الشغل عليها لحد ما نتأكد.")


def send_deletion_alert(change) -> int:
    """يرسل التنبيه الكامل. يرفع استثناءً إن فشلت الرسالة الأساسية (فيُعاد المحاولة في الدورة التالية)."""
    try:
        details = json.loads(change["details_json"] or "{}")
    except Exception:
        details = {}
    title = change["title"]
    owner = details.get("owner")
    engineer = details.get("engineer") or change["suggested_engineer"]
    deadline = details.get("submission_date") or change["submission_date"]

    with db._get_connection() as conn:
        ensure_table(conn)
        alert_id = conn.execute(
            "INSERT INTO deletion_alerts (tender_id, title, owner, engineer, deadline) VALUES (?,?,?,?,?)",
            (change["tender_id"], title, owner, engineer, deadline)).lastrowid
        conn.commit()

    # ① الرسالة الأساسية — إن فشلت يُحذف سجل التنبيه ويُرفع الاستثناء
    #    (notify_pending_changes يعيد المحاولة في الدورة التالية دون تكرار السجل في التذكير)
    try:
        msg = bot.send_message(CHAT_ID, build_alert_html(title, owner, engineer, deadline),
                               parse_mode="HTML", reply_markup=_ack_markup(alert_id))
    except Exception:
        with db._get_connection() as conn:
            conn.execute("DELETE FROM deletion_alerts WHERE id=?", (alert_id,))
            conn.commit()
        raise
    with db._get_connection() as conn:
        conn.execute("UPDATE deletion_alerts SET chat_message_id=? WHERE id=?", (msg.message_id, alert_id))
        conn.commit()
    logger.warning(f"🚨 DELETION ALERT sent: {change['tender_id']} '{title}' (alert #{alert_id})")

    # ② تثبيت أعلى المجموعة (يحتاج صلاحية مشرف للبوت) — أفضل جهد
    try:
        bot.pin_chat_message(CHAT_ID, msg.message_id, disable_notification=False)
    except Exception as e:
        logger.warning(f"Deletion alert pin failed (bot needs 'pin messages' admin right): {e}")

    # ③ رسالة صوتية — الاستيراد داخل الدالة حتى لا يتغير ترتيب تسجيل المعالجات
    try:
        import bot_voice_ai
        audio = bot_voice_ai._ai_speak(voice_text(title, deadline), chat_id=0)
        if audio:
            vbuf = io.BytesIO(audio); vbuf.name = "deleted_alert.ogg"
            bot.send_voice(CHAT_ID, vbuf, reply_to_message_id=msg.message_id)
    except Exception as e:
        logger.warning(f"Deletion voice alert failed: {e}")

    # ④ رسائل خاصة: المهندس المسؤول (إن كان مشتركاً) + المالك
    plain = (f"🚨 منافستك اتحذفت من المنصة قبل موعدها:\n{title}\n"
             f"موعدها كان: {str(deadline)[:10]}\n⛔ أوقف العمل عليها لحد ما نتأكد.")
    try:
        from bot_notifications import _notify_engineer
        if engineer:
            _notify_engineer(engineer, plain)
    except Exception as e:
        logger.debug(f"engineer DM failed: {e}")
    for oid in OWNER_TELEGRAM_IDS:
        if str(oid) == str(CHAT_ID):
            continue
        try:
            bot.send_message(oid, build_alert_html(title, owner, engineer, deadline), parse_mode="HTML")
        except Exception as e:
            logger.debug(f"owner DM {oid} failed: {e}")
    return alert_id


def acknowledge(alert_id: int, by: str):
    """يسجّل الاطلاع. يرجع صف التنبيه، أو None إن لم يوجد. التأكيد الأول هو المعتمد."""
    with db._get_connection() as conn:
        ensure_table(conn)
        row = conn.execute("SELECT * FROM deletion_alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            return None
        if not row["acked_at"]:
            conn.execute("UPDATE deletion_alerts SET acked_by=?, acked_at=datetime('now','localtime') WHERE id=?",
                         (by, alert_id))
            conn.commit()
        return conn.execute("SELECT * FROM deletion_alerts WHERE id=?", (alert_id,)).fetchone()


def pending_reminders():
    with db._get_connection() as conn:
        ensure_table(conn)
        return conn.execute(
            "SELECT * FROM deletion_alerts WHERE acked_at IS NULL "
            f"AND detected_at >= datetime('now','localtime','-{REMINDER_WINDOW_DAYS} days') ORDER BY id").fetchall()


def send_reminders() -> int:
    rows = pending_reminders()
    if not rows:
        return 0
    lines = [f"⏰ <b>تذكير: {len(rows)} منافسة اتحذفت من المنصة ولم يؤكد أحد الاطلاع عليها</b>", ""]
    markup = InlineKeyboardMarkup(row_width=1)
    for r in rows:
        lines.append(f"🚨 <b>{html.escape(r['title'] or '')}</b>\n   👷 {html.escape(r['engineer'] or '—')} | "
                     f"📅 كان موعدها {html.escape(str(r['deadline'] or '—')[:10])} | اكتُشف {html.escape(str(r['detected_at'])[:16])}")
        markup.add(InlineKeyboardButton(f"✅ اطّلعت: {_short_title(r['title'], 5)}", callback_data=f"delack_{r['id']}"))
    bot.send_message(CHAT_ID, "\n".join(lines), parse_mode="HTML", reply_markup=markup)
    return len(rows)


def recent_deletions_text(days: int = 30) -> str:
    """نص /deleted: التنبيهات المسجّلة + ما حُذف قبل هذا التحديث (مغلقة وموعدها كان بعد تاريخ إغلاقها)."""
    with db._get_connection() as conn:
        ensure_table(conn)
        alerts = conn.execute(
            f"SELECT * FROM deletion_alerts WHERE detected_at >= datetime('now','localtime','-{days} days') ORDER BY id DESC").fetchall()
        known = {a["tender_id"] for a in alerts}
        legacy = [r for r in conn.execute(
            "SELECT tender_id, title, assigned_engineer, submission_date, updated_at FROM master_tenders "
            "WHERE status='CLOSED' AND date(submission_date) > date(updated_at) "
            f"AND updated_at >= datetime('now','-{days} days') ORDER BY updated_at DESC").fetchall()
            if r["tender_id"] not in known]
    if not alerts and not legacy:
        return f"✅ لم تُحذف أي منافسة من المنصة قبل موعدها خلال آخر {days} يوماً."
    out = [f"🗑️ المنافسات المحذوفة من المنصة قبل موعدها — آخر {days} يوماً ({len(alerts) + len(legacy)})", "━━━━━━━━━━━━━━"]
    for a in alerts:
        status = f"✅ اطّلع: {a['acked_by']} ({str(a['acked_at'])[:16]})" if a["acked_at"] else "⚠️ لم يؤكد أحد الاطلاع"
        out.append(f"• {a['title']}\n   👷 {a['engineer'] or '—'} | 📅 كان موعدها {str(a['deadline'])[:10]} | اكتُشف {str(a['detected_at'])[:16]}\n   {status}")
    for r in legacy:
        out.append(f"• {r['title']}\n   👷 {r['assigned_engineer'] or '—'} | 📅 كان موعدها {str(r['submission_date'])[:10]} | اختفت {str(r['updated_at'])[:16]}\n   🕘 قبل تفعيل التنبيه العاجل (وصلها سطر \"للعلم\" فقط)")
    return "\n".join(out)
