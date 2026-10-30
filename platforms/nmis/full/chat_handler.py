"""
chat_handler.py — Arabic Conversational Query Engine
=====================================================
Interprets free-text Arabic questions about tenders and engineers,
queries SQLite, and returns Telegram-formatted Markdown responses.

Supported question categories:
  1. Engineer workload  → "المعمري معه كم منافسة؟"
  2. Engineer schedule  → "مواعيد منافسات محمد"
  3. Busiest engineer   → "من الأكثر مشغولاً؟"
  4. Most available     → "من عنده وقت؟"
  5. Date window        → "غداً معنا كم منافسة؟"
  6. Tender search      → "بحث عن أرامكو"
  7. General stats      → "كم منافسة عندنا؟"
  8. Upcoming deadlines → "أقرب المواعيد"
"""
from __future__ import annotations  # enables str|None on Python 3.9

import re
import sqlite3
import pandas as pd
from contextlib import contextmanager
from datetime import datetime, timedelta


# ──────────────────────────────────────────────────────────────────────────────
# Connection helper
# ──────────────────────────────────────────────────────────────────────────────
@contextmanager
def _conn(db_path):
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────────
def _clean(v, default="غير محدد"):
    if v is None:
        return default
    s = str(v).strip()
    return default if s.lower() in ("", "nan", "none", "n/a") else s


def _fmt_date(v):
    try:
        d = pd.to_datetime(v, errors="coerce")
        return d.strftime("%Y-%m-%d") if pd.notnull(d) else _clean(v)
    except Exception:
        return _clean(v)


def _bar(pct):
    filled = max(0, min(10, pct // 10))
    return "▓" * filled + "░" * (10 - filled)


def _days_until(date_str):
    try:
        d = pd.to_datetime(date_str, errors="coerce")
        if pd.notnull(d):
            delta = (d.replace(tzinfo=None) - datetime.now()).days
            return delta
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Intent detection helpers
# ──────────────────────────────────────────────────────────────────────────────
_TOMORROW  = ["غد", "غدا", "غداً", "بكرة", "بكره"]
_TODAY     = ["اليوم", "النهارده", "الحين"]
_WEEK      = ["الأسبوع", "الاسبوع", "هذا الأسبوع", "أسبوع", "7 أيام", "7 ايام", "سبعة أيام"]
_MONTH     = ["الشهر", "هذا الشهر", "الشهر الحالي", "30 يوم", "ثلاثين يوم", "شهر"]
_NEAR      = ["أقرب", "اقرب", "القريب", "قريباً", "ينتهي", "تنتهي", "تغلق", "يغلق", "عاجل"]

_CHANGE_Q   = ["تغير", "تغيّر", "تغيرت", "اتغير", "تغيير", "تعديل", "تعدّل", "تعديلات", "تبدّل", "تبدل", "عُدّل", "عدّل"]
_SUMMARY_Q  = ["ملخص", "تقرير", "احصاء", "إحصاء", "موجز"]
_LOAD_Q    = ["كم", "معه", "عنده", "مشاريع", "منافسات", "مناقصات", "حمل", "مشغول", "ضغط", "نشطة"]
_SCHED_Q   = ["مواعيد", "تفاصيل", "قائمة", "تواريخ", "أسماء", "اسماء", "سرد"]
_BUSY_Q    = ["أكثر", "اكثر", "الأثقل", "الأعلى", "أعلى"]
_FREE_Q    = ["فاضي", "فاضٍ", "متاح", "أقل", "اقل", "أخف", "خفيف", "وقت", "يفضل"]
_SEARCH_Q  = ["بحث", "ابحث", "دور", "دوّر", "عن", "مسؤول عن", "مكلف", "مناقصة"]
_STATS_Q   = ["إجمالي", "اجمالي", "جميع", "كل", "عدد", "عندنا", "معنا", "نشطة"]

_QUESTION_MARKERS = set(
    ["كم", "من", "ما", "متى", "هل", "أين", "اين", "؟", "?"]
    + _LOAD_Q + _SCHED_Q + _BUSY_Q + _FREE_Q + _NEAR + _SUMMARY_Q
    + ["مواعيد", "تسلم", "تسليم", "يسلم", "إغلاق", "اغلاق"]
)


def _detect_time_window(text):
    """Returns (label, date_from, date_to) or None."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for w in _TOMORROW:
        if w in text:
            d = today + timedelta(days=1)
            return ("غداً", d, d + timedelta(days=1))
    for w in _TODAY:
        if w in text:
            return ("اليوم", today, today + timedelta(days=1))
    for w in _WEEK:
        if w in text:
            return ("خلال 7 أيام", today, today + timedelta(days=7))
    for w in _MONTH:
        if w in text:
            return ("خلال 30 يوم", today, today + timedelta(days=30))
    for w in _NEAR:
        if w in text:
            return ("الأقرب موعداً", today, today + timedelta(days=14))
    return None


def _detect_engineer(text, db_path):
    """
    Returns matched engineer name from DB, or None.
    Supports partial matching: if DB name is 'محمد العمري' and user
    types 'العمري' or 'محمد', it will match.
    """
    with _conn(db_path) as con:
        names = [r["name"] for r in
                 con.execute("SELECT name FROM engineers WHERE is_active = 1").fetchall()]
    for name in names:
        if name in text:
            return name
        # Partial: match any 4+ char word from the engineer's full name
        for part in name.split():
            if len(part) >= 3 and part in text:
                return name
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────
def handle_chat_query(text: str, db_path) -> "str | None":
    """
    Parses free-text Arabic question and returns a Telegram Markdown response.
    Returns None if the message is not a recognized question.
    """
    text = text.strip()

    # Skip commands
    if text.startswith("/"):
        return None

    # Must contain at least one recognizable question indicator
    if not any(m in text for m in _QUESTION_MARKERS):
        return None

    # ── Detect engineer mention early (used in multiple routes) ──────────────
    eng = _detect_engineer(text, db_path)

    # ── Route 0: Date-change query (HIGHEST PRIORITY — must come before time-window route) ──
    # Catches: "هل تغيرت مواعيد اليوم؟" / "تعديلات اليوم" / "هل تم تغيير مواعيد؟"
    if any(w in text for w in _CHANGE_Q):
        time_window = _detect_time_window(text)
        if time_window:
            label, d_from, d_to = time_window
            return _date_changes_in_window(label, d_from, d_to, db_path)
        else:
            # No time mentioned → show ALL recent changes (last 7 days)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return _date_changes_in_window("آخر 7 أيام", today - timedelta(days=7), today + timedelta(days=1), db_path)

    # ── Route 1: Engineer schedule (list of tenders) ─────────────────────────
    if eng and any(w in text for w in _SCHED_Q):
        return _eng_tenders(eng, db_path)

    # ── Route 2: Engineer workload (count + bar) ──────────────────────────────
    if eng and any(w in text for w in _LOAD_Q):
        return _eng_load(eng, db_path)

    # ── Route 3: Any mention of engineer alone → default to load ─────────────
    if eng:
        return _eng_load(eng, db_path)

    # ── Route 4: Busiest engineer ─────────────────────────────────────────────
    if any(w in text for w in _BUSY_Q) and any(w in text for w in ["مشغول", "ضغط", "حمل", "مهندس"]):
        return _all_engineers_ranked(db_path, busiest_first=True)

    # ── Route 5: Most available engineer ─────────────────────────────────────
    if any(w in text for w in _FREE_Q):
        return _least_busy_eng(db_path)

    # ── Route 5.5: Weekly / periodic summary ─────────────────────────────────
    # Must come BEFORE Route 6 — "ملخص الأسبوع" contains "الأسبوع" which would
    # otherwise match the date-window route and show tenders closing this week.
    if any(w in text for w in _SUMMARY_Q):
        return _weekly_summary(db_path)

    # ── Route 6: Date-window query ────────────────────────────────────────────
    time_window = _detect_time_window(text)
    if time_window:
        label, d_from, d_to = time_window
        return _tenders_in_window(label, d_from, d_to, db_path)

    # ── Route 7: Tender keyword search ───────────────────────────────────────
    if any(w in text for w in _SEARCH_Q):
        keyword = re.sub(
            r"^(بحث|ابحث|دور|دوّر|عن|تفاصيل|مناقصة|مسؤول عن|مسؤول|مكلف)\s*",
            "", text
        ).strip()
        if len(keyword) >= 2:
            return _search_tender(keyword, db_path)

    # ── Route 8: General count / stats ───────────────────────────────────────
    if any(w in text for w in _STATS_Q) or "كم" in text:
        return _total_stats(db_path)

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Query implementations
# ──────────────────────────────────────────────────────────────────────────────

def _eng_load(eng_name: str, db_path) -> str:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT title, submission_date FROM master_tenders "
            "WHERE assigned_engineer = ? AND status NOT IN ('CLOSED','REJECTED') "
            "ORDER BY submission_date ASC",
            (eng_name,)
        ).fetchall()
        cap_row = con.execute(
            "SELECT capacity FROM engineers WHERE name = ?", (eng_name,)
        ).fetchone()

    capacity = cap_row["capacity"] if cap_row else 5
    count    = len(rows)
    pct      = min(int(count / capacity * 100), 100)

    if count == 0:
        return (
            f"👷 *{eng_name}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"لا توجد منافسات مسندة إليه حالياً.\n"
            f"الحمل: [{_bar(0)}] 0%"
        )

    # Nearest deadline
    nearest_date = None
    nearest_title = ""
    for r in rows:
        d = pd.to_datetime(r["submission_date"], errors="coerce")
        if pd.notnull(d):
            d_naive = d.replace(tzinfo=None)
            if nearest_date is None or d_naive < nearest_date:
                nearest_date  = d_naive
                nearest_title = r["title"]

    days_left = _days_until(str(nearest_date)) if nearest_date else None
    urgency   = ""
    if days_left is not None:
        if days_left < 0:
            urgency = f"  ⚠️ _انتهت منذ {abs(days_left)} يوم!_"
        elif days_left == 0:
            urgency = "  🔴 _تغلق اليوم!_"
        elif days_left <= 2:
            urgency = f"  🟠 _تغلق خلال {days_left} يوم!_"
        elif days_left <= 7:
            urgency = f"  🟡 _تغلق خلال {days_left} يوم_"

    nearest_str = nearest_date.strftime("%Y-%m-%d") if nearest_date else "غير محدد"

    # Build header (summary)
    header = (
        f"👷 *{eng_name}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"المنافسات النشطة: *{count}* من أصل {capacity}\n"
        f"الحمل: [{_bar(pct)}] {pct}%\n"
        f"أقرب موعد: `{nearest_str}`{urgency}\n"
        f"━━━━━━━━━━━━━━"
    )

    # Build tenders list
    lines = [header]
    for i, r in enumerate(rows, 1):
        date_str = _fmt_date(r["submission_date"])
        days     = _days_until(r["submission_date"])
        flag     = ""
        if days is not None:
            if days < 0:
                flag = " ⚠️"
            elif days == 0:
                flag = " 🔴"
            elif days <= 2:
                flag = f" 🟠({days}d)"
            elif days <= 7:
                flag = f" 🟡({days}d)"
        lines.append(f"{i}. {r['title']}\n   📅 `{date_str}`{flag}")

    return "\n".join(lines)


def _eng_tenders(eng_name: str, db_path) -> str:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT title, submission_date FROM master_tenders "
            "WHERE assigned_engineer = ? AND status NOT IN ('CLOSED','REJECTED') "
            "ORDER BY submission_date ASC",
            (eng_name,)
        ).fetchall()

    if not rows:
        return f"👷 *{eng_name}*\n\nلا توجد منافسات مسندة إليه حالياً."

    lines = [f"📋 *قائمة منافسات {eng_name}*\n━━━━━━━━━━━━━━"]
    today = datetime.now()
    for i, r in enumerate(rows, 1):
        date_str = _fmt_date(r["submission_date"])
        days     = _days_until(r["submission_date"])
        flag     = ""
        if days is not None:
            if days < 0:
                flag = " ⚠️ منتهية"
            elif days == 0:
                flag = " 🔴 اليوم!"
            elif days <= 2:
                flag = f" 🟠 ({days}d)"
            elif days <= 7:
                flag = f" 🟡 ({days}d)"
        lines.append(f"{i}. {r['title']}\n   📅 `{date_str}`{flag}")

    lines.append(f"\n*الإجمالي: {len(rows)} منافسة*")
    return "\n".join(lines)


def _all_engineers_ranked(db_path, busiest_first=True) -> str:
    with _conn(db_path) as con:
        rows = con.execute(
            """
            SELECT e.name, e.capacity,
                   COUNT(m.id) AS load
            FROM engineers e
            LEFT JOIN master_tenders m
                ON m.assigned_engineer = e.name
               AND m.status NOT IN ('CLOSED','REJECTED')
            WHERE e.is_active = 1
            GROUP BY e.name
            ORDER BY load {}
            """.format("DESC" if busiest_first else "ASC")
        ).fetchall()

    if not rows:
        return "لا توجد بيانات للمهندسين."

    title  = "الأكثر مشغولاً" if busiest_first else "الأقل ضغطاً"
    lines  = [f"📊 *ترتيب المهندسين ({title}):*\n━━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        pct   = min(int(r["load"] / (r["capacity"] or 5) * 100), 100)
        badge = medals[i] if i < 3 else f"  {i+1}."
        lines.append(
            f"{badge} *{r['name']}*: {r['load']}/{r['capacity']}\n"
            f"    [{_bar(pct)}] {pct}%"
        )
    return "\n".join(lines)


def _least_busy_eng(db_path) -> str:
    with _conn(db_path) as con:
        row = con.execute(
            """
            SELECT e.name, e.capacity,
                   COUNT(m.id) AS load
            FROM engineers e
            LEFT JOIN master_tenders m
                ON m.assigned_engineer = e.name
               AND m.status NOT IN ('CLOSED','REJECTED')
            WHERE e.is_active = 1
            GROUP BY e.name
            ORDER BY load ASC
            LIMIT 1
            """
        ).fetchone()

    if not row:
        return "لا توجد بيانات."

    pct = min(int(row["load"] / (row["capacity"] or 5) * 100), 100)
    return (
        f"✅ *المهندس الأقل ضغطاً حالياً:*\n\n"
        f"👷 *{row['name']}*\n"
        f"المنافسات: {row['load']} من أصل {row['capacity']}\n"
        f"الحمل: [{_bar(pct)}] {pct}%"
    )


def _tenders_in_window(label: str, d_from: datetime, d_to: datetime, db_path) -> str:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT title, submission_date, assigned_engineer "
            "FROM master_tenders "
            "WHERE status NOT IN ('CLOSED','REJECTED') "
            "ORDER BY submission_date ASC"
        ).fetchall()

    matched = []
    for r in rows:
        try:
            d = pd.to_datetime(r["submission_date"], errors="coerce")
            if pd.notnull(d):
                d_naive = d.replace(tzinfo=None)
                if d_from <= d_naive < d_to:
                    matched.append(r)
        except Exception:
            pass

    if not matched:
        return (
            f"📅 *منافسات {label}:*\n\n"
            f"لا توجد منافسات بموعد تسليم في هذه الفترة. ✅"
        )

    lines = [f"📅 *منافسات {label}:* ({len(matched)} منافسة)\n━━━━━━━━━━━━━━"]
    for r in matched:
        eng  = _clean(r["assigned_engineer"])
        days = _days_until(r["submission_date"])
        flag = f" ← *{days} يوم*" if days is not None and days >= 0 else ""
        lines.append(
            f"• *{r['title']}*\n"
            f"  👷 {eng} | 📅 `{_fmt_date(r['submission_date'])}`{flag}"
        )

    return "\n".join(lines)


def _search_tender(keyword: str, db_path) -> str:
    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT title, submission_date, assigned_engineer, owner, status "
            "FROM master_tenders "
            "WHERE title LIKE ? OR owner LIKE ? "
            "ORDER BY CASE status WHEN 'CLOSED' THEN 1 ELSE 0 END, submission_date ASC "
            "LIMIT 6",
            (f"%{keyword}%", f"%{keyword}%")
        ).fetchall()

    if not rows:
        return f"🔍 لم أجد أي منافسة تتعلق بـ *{keyword}*"

    lines = [f"🔍 *نتائج البحث عن:* \"{keyword}\"\n━━━━━━━━━━━━━━"]
    for r in rows:
        icon = "🔴" if r["status"] in ("CLOSED", "REJECTED") else "🟢"
        eng  = _clean(r["assigned_engineer"])
        owner = _clean(r["owner"])
        owner_line = f"\n  🏢 _{owner}_" if owner != "غير محدد" else ""
        lines.append(
            f"{icon} *{r['title']}*{owner_line}\n"
            f"  👷 {eng} | 📅 `{_fmt_date(r['submission_date'])}`"
        )

    if len(rows) == 6:
        lines.append("\n_أظهرت أول 6 نتائج — دقّق كلمة البحث لنتائج أدق._")

    return "\n".join(lines)


def _total_stats(db_path) -> str:
    with _conn(db_path) as con:
        active  = con.execute(
            "SELECT COUNT(*) FROM master_tenders WHERE status NOT IN ('CLOSED','REJECTED')"
        ).fetchone()[0]
        closed  = con.execute(
            "SELECT COUNT(*) FROM master_tenders WHERE status = 'CLOSED'"
        ).fetchone()[0]
        pending = con.execute(
            "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED')"
        ).fetchone()[0]
        # Count tenders closing in next 7 days
        rows = con.execute(
            "SELECT submission_date FROM master_tenders WHERE status NOT IN ('CLOSED','REJECTED')"
        ).fetchall()

    urgent = 0
    today  = datetime.now()
    for r in rows:
        days = _days_until(r["submission_date"])
        if days is not None and 0 <= days <= 7:
            urgent += 1

    urgency_line = f"\n⚡ تغلق خلال 7 أيام: *{urgent}*" if urgent > 0 else ""

    return (
        f"📊 *إجمالي المنافسات:*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🟢 نشطة: *{active}*\n"
        f"⚪ مغلقة: *{closed}*\n"
        f"🟡 بانتظار الاعتماد: *{pending}*\n"
        f"📦 الإجمالي الكلي: *{active + closed}*"
        f"{urgency_line}"
    )


def _weekly_summary(db_path) -> str:
    """
    Shows a weekly summary:
      - New tenders detected this week
      - Tenders closed this week
      - Date changes this week
      - Tenders due in the next 7 days
      - Top 3 engineers by load
    """
    today      = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago   = today - timedelta(days=7)
    next_week  = today + timedelta(days=7)
    week_ago_s = week_ago.strftime("%Y-%m-%d")
    today_s    = today.strftime("%Y-%m-%d")
    next_week_s = next_week.strftime("%Y-%m-%d")

    with _conn(db_path) as con:
        new_this_week = con.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='DETECT_NEW' AND DATE(created_at) >= DATE(?)",
            (week_ago_s,)
        ).fetchone()[0]

        changes_this_week = con.execute(
            "SELECT COUNT(DISTINCT title) FROM pending_changes "
            "WHERE change_type='UPDATED_DATE' AND DATE(created_at) >= DATE(?)",
            (week_ago_s,)
        ).fetchone()[0]

        active_count = con.execute(
            "SELECT COUNT(*) FROM master_tenders WHERE status NOT IN ('CLOSED','REJECTED')"
        ).fetchone()[0]

        pending_count = con.execute(
            "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED')"
        ).fetchone()[0]

        upcoming = con.execute(
            "SELECT title, submission_date, assigned_engineer FROM master_tenders "
            "WHERE status='InProgress' AND DATE(submission_date) >= DATE(?) AND DATE(submission_date) < DATE(?) "
            "ORDER BY submission_date ASC",
            (today_s, next_week_s)
        ).fetchall()

        eng_rows = con.execute(
            """
            SELECT e.name, e.capacity, COUNT(m.id) AS load
            FROM engineers e
            LEFT JOIN master_tenders m
                ON m.assigned_engineer = e.name AND m.status NOT IN ('CLOSED','REJECTED')
            WHERE e.is_active = 1
            GROUP BY e.name ORDER BY load DESC LIMIT 3
            """
        ).fetchall()

    lines = [
        f"📈 *ملخص الأسبوع — {today.strftime('%Y-%m-%d')}*",
        "━━━━━━━━━━━━━━",
        f"🆕 منافسات جديدة هذا الأسبوع: *{new_this_week}*",
        f"🔄 تغييرات مواعيد: *{changes_this_week}*",
        f"📦 إجمالي النشطة حالياً: *{active_count}*",
    ]

    if pending_count > 0:
        lines.append(f"🟡 بانتظار الاعتماد: *{pending_count}* طلب")

    if upcoming:
        lines.append(f"\n⚡ *تسليمات الأسبوع القادم ({len(upcoming)}):*")
        for r in upcoming:
            days = _days_until(r["submission_date"])
            flag = ""
            if days is not None:
                if days == 0:
                    flag = " 🔴 اليوم"
                elif days <= 2:
                    flag = f" 🟠 ({days}d)"
                elif days <= 7:
                    flag = f" 🟡 ({days}d)"
            eng = _clean(r["assigned_engineer"])
            lines.append(
                f"  • _{r['title'][:55]}{flag}_\n"
                f"    👷 {eng} | 📅 `{_fmt_date(r['submission_date'])}`"
            )
    else:
        lines.append("\n✅ لا تسليمات في الأسبوع القادم")

    if eng_rows:
        lines.append("\n📊 *أعلى المهندسين ضغطاً:*")
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(eng_rows):
            pct = min(int(r["load"] / (r["capacity"] or 5) * 100), 100)
            lines.append(f"  {medals[i]} *{r['name']}*: {r['load']}/{r['capacity']}  [{_bar(pct)}] {pct}%")

    return "\n".join(lines)


def _date_changes_in_window(label: str, d_from: datetime, d_to: datetime, db_path) -> str:
    """
    Shows tenders whose submission date was changed (UPDATED_DATE events)
    within the given time window.

    Source of truth: pending_changes table only.
      - APPROVED status          → 🔄  (تم الاعتماد)
      - NOTIFIED / PENDING status → 🟡  (بانتظار الاعتماد)

    De-duplicates by title, keeping the latest record per tender.
    """
    from_str = d_from.strftime("%Y-%m-%d")
    to_str   = d_to.strftime("%Y-%m-%d")

    with _conn(db_path) as con:
        rows = con.execute(
            "SELECT title, submission_date, suggested_engineer, status, created_at "
            "FROM pending_changes "
            "WHERE change_type = 'UPDATED_DATE' "
            "  AND DATE(created_at) >= DATE(?) AND DATE(created_at) < DATE(?) "
            "ORDER BY created_at DESC",
            (from_str, to_str)
        ).fetchall()

    # De-duplicate: keep only the latest record per title
    seen_titles: set[str] = set()
    unique: list = []
    for r in rows:
        t = (r["title"] or "").strip()
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append(r)

    if not unique:
        return (
            f"📅 *تغييرات المواعيد — {label}:*\n\n"
            f"لم يُسجَّل أي تغيير في مواعيد التقديم خلال هذه الفترة. ✅\n"
            f"_للتأكد من آخر الوضع، شغّل /news_"
        )

    lines = [f"📅 *تغييرات المواعيد — {label}:* ({len(unique)} تغيير)\n━━━━━━━━━━━━━━"]
    for r in unique:
        eng      = _clean(r["suggested_engineer"] or "")
        eng_line = f"\n   👷 {eng}" if eng and eng != "غير محدد" else ""
        date_str = _fmt_date(r["submission_date"])
        approved = r["status"] == "APPROVED"
        icon     = "🔄" if approved else "🟡"
        label_ar = "_(تم الاعتماد)_" if approved else "_(بانتظار الاعتماد)_"
        lines.append(
            f"{icon} *{r['title']}*{eng_line}\n"
            f"   📅 الموعد الجديد: `{date_str}`  {label_ar}"
        )

    return "\n".join(lines)
