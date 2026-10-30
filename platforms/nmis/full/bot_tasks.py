# -*- coding: utf-8 -*-
"""لوحة المهام على تليجرام (المرحلة 2 — 2026-09-24). بلا معالجات هنا: /mytasks في bot_commands،
وأزرار tsk_ في bot_callbacks (ترتيب التسجيل سلوك). المنطق المشترك مع اللوحة في tasks_core.py.

- /mytasks: مهام المهندس المشترك المفتوحة، بزر «▶ بدأت» و«✅ أنجزت» لكل مهمة.
- بعد كل دورة فحص: قوالب المنافسات الجديدة + مزامنة المراحل + إشعار الإسناد خاصاً.
- 08:20 يومياً: كل مهندس مشترك تصله مهامه المتأخرة/المستحقة اليوم، والمجموعة ملخصاً واحداً.
- أول كل شهر 09:05: تقرير الأداء PDF عن الشهر المنتهي — لتليجرام الإدارة (OWNER_TELEGRAM_ID) فقط.
تعمل فقط إن كانت "features": ["kanban"] في هوية الشركة.
"""
import os
from contextlib import closing
from datetime import date

import requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import tasks_core
from bot_core import CHAT_ID, OWNER_TELEGRAM_IDS, bot, is_paused, logger
from company_profile import feature_enabled
from db_manager import DB_PATH

FEATURE = tasks_core.FEATURE
_MAX_BUTTON_TASKS = 8


def enabled() -> bool:
    return feature_enabled(FEATURE)


def _conn():
    return closing(tasks_core.connect(DB_PATH))


def _push_board_refresh():
    """يطلب من اللوحة تحديث كل شاشات المهام المفتوحة (نفس السيرفر — أفضل جهد)."""
    port = "5311"
    try:
        requests.post(f"http://127.0.0.1:{port}/api/push-event",
                      json={"type": "tasks_changed", "data": {}}, timeout=3)
    except Exception as e:
        logger.debug(f"tasks board push failed: {e}")


def _send_notices(conn, notices):
    for eng, text in notices:
        for cid in tasks_core.subscriber_chats(conn, eng):
            try:
                bot.send_message(cid, text)
            except Exception as e:
                logger.debug(f"task notice {eng}/{cid} failed: {e}")


def after_cycle():
    """بعد دورة الفحص: تجهيز القوالب + المزامنة + الإشعارات."""
    if not enabled():
        return
    try:
        with _conn() as conn:
            changed, notices = tasks_core.refresh_and_commit(conn)
            _send_notices(conn, notices)
        if changed:
            _push_board_refresh()
            logger.info(f"Tasks refreshed after cycle ({len(notices)} notices).")
    except Exception as e:
        logger.error(f"tasks after_cycle failed: {e}")


def my_tasks_message(engineer: str):
    """(نص، أزرار) لمهام المهندس المفتوحة."""
    with _conn() as conn:
        tasks_core.ensure_tables(conn)
        rows = tasks_core.open_tasks_for(conn, engineer)
    if not rows:
        return f"✨ لا مهام مفتوحة لك الآن يا م. {engineer}.", None
    lines = [f"🗂️ مهامك المفتوحة يا م. {engineer} ({len(rows)}):", ""]
    markup = InlineKeyboardMarkup(row_width=2)
    for i, r in enumerate(rows, 1):
        icon = "🔵" if r["status"] == "doing" else "⚪"
        lines.append(f"{i}. {icon} {r['title']} — {tasks_core.STATUS_LABEL[r['status']]}")
        lines.append(f"    📄 {r['tender_title'] or '—'}")
        due = tasks_core.due_text(r["due_date"])
        if due:
            lines.append(f"    {due}")
        if i <= _MAX_BUTTON_TASKS:
            btns = []
            if r["status"] == "todo":
                btns.append(InlineKeyboardButton(f"▶ {i} بدأت", callback_data=f"tsk_{r['id']}_doing"))
            btns.append(InlineKeyboardButton(f"✅ {i} أنجزت", callback_data=f"tsk_{r['id']}_done"))
            markup.row(*btns)
    lines += ["", "⚪ لم تبدأ · 🔵 قيد التنفيذ — الأزرار تحدّث لوحة المهام فوراً."]
    return "\n".join(lines), markup


def apply_button(engineer: str, task_id: int, status: str) -> str:
    """زر من /mytasks: يتحقق أن المهمة مسندة لهذا المهندس ثم ينقلها. يرجع رسالة قصيرة."""
    if status not in ("doing", "done"):
        return "زر غير صالح"
    with _conn() as conn:
        tasks_core.ensure_tables(conn)
        row = conn.execute("SELECT engineer, status, title FROM tender_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return "المهمة غير موجودة (ربما حُذفت)"
        if row["engineer"] != engineer:
            return "هذه المهمة ليست مسندة إليك"
        if row["status"] == status:
            return "محدّثة بالفعل"
        tasks_core.move(conn, task_id, status, f"م. {engineer} (تليجرام)")
        conn.commit()
    _push_board_refresh()
    return ("✅ أُنجزت: " if status == "done" else "▶ بدأت: ") + row["title"][:40]


def job_task_reminders(today: date = None):
    """08:20: المتأخر والمستحق اليوم — خاص لكل مهندس مشترك + ملخص واحد للمجموعة."""
    if not enabled() or is_paused():
        return
    today = today or date.today()
    try:
        with _conn() as conn:
            tasks_core.ensure_tables(conn)
            late = tasks_core.overdue_by_engineer(conn, today)
            _send_notices(conn, [
                (eng, "\n".join([f"⏰ صباح الخير يا م. {eng} — مهام تحتاج انتباهك ({len(items)}):", ""] +
                                [f"• {t} — {tasks_core.due_text(d, today)}\n    📄 {tn}" for t, tn, d in items[:12]] +
                                ["", "حدّثها بالأمر /mytasks"]))
                for eng, items in late.items()])
        if late and CHAT_ID:
            total = sum(len(v) for v in late.values())
            summary = "\n".join([f"🗂️ لوحة المهام — {total} مهمة متأخرة أو مستحقة اليوم:"] +
                                [f"• م. {eng}: {len(v)}" for eng, v in sorted(late.items(), key=lambda kv: -len(kv[1]))])
            bot.send_message(CHAT_ID, summary)
        logger.info(f"Task reminders: {len(late)} engineers.")
    except Exception as e:
        logger.error(f"job_task_reminders failed: {e}")


def job_performance_report(today: date = None):
    """أول كل شهر: تقرير الأداء PDF عن الشهر المنتهي لمحادثات الإدارة — تقييم الأشخاص لا يذهب للمجموعة."""
    today = today or date.today()
    if not enabled() or today.day != 1:
        return
    if not OWNER_TELEGRAM_IDS:
        logger.warning("Performance report skipped: OWNER_TELEGRAM_ID is not set (never sent to the group).")
        return
    try:
        import performance_report
        with _conn() as conn:
            n = performance_report.send(bot, sorted(OWNER_TELEGRAM_IDS), conn, performance_report.previous_month(today))
        logger.info(f"Performance report sent to {n} management chat(s).")
    except Exception as e:
        logger.error(f"job_performance_report failed: {e}")
