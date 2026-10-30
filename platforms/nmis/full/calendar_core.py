# -*- coding: utf-8 -*-
"""تقويم المواعيد (2026-09-25) — شهر واحد يجمع إغلاق المنافسات واستحقاق المهام ومواعيد الضمان (features: calendar).

منطق بلا Flask تستدعيه web_calendar.py. الأسبوع يبدأ الأحد (أسبوع العمل في السعودية).
موعد الإغلاق نصي بصيغتين (النور YYYY-MM-DD، الإدخال اليدوي DD/MM/YYYY) فيُحلَّل في بايثون لا في SQL.
موعد الضمان: المحدد يدوياً، وإلا قبل الإغلاق بـ 5 أيام (نفس قاعدة لوحة المنافسات).
"""
import sqlite3
from datetime import date, timedelta

from tasks_core import ACTIVE_EXCLUDED, parse_deadline

FEATURE = "calendar"
MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
          "ديسمبر")
WEEKDAYS = ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت")
GUARANTEE_DONE = ("READY", "SUBMITTED", "NOT_REQUIRED")
GUARANTEE_DAYS_BEFORE = 5
KINDS = ("deadline", "guarantee", "task")
_ORDER = {"deadline": 0, "guarantee": 1, "task": 2}


def _table(conn, name) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def parse_month(value, today: date) -> date:
    """«2026-10» ← أول يوم في الشهر؛ أي قيمة أخرى ← الشهر الحالي."""
    try:
        y, m = str(value or "").split("-")
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        return today.replace(day=1)


def grid_range(first: date):
    """من أحد أول أسبوع إلى سبت آخر أسبوع يغطيان الشهر."""
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = nxt - timedelta(days=1)
    return start, last + timedelta(days=(5 - last.weekday()) % 7)


def _shift(first: date, months: int) -> str:
    y, m = divmod(first.year * 12 + first.month - 1 + months, 12)
    return f"{y:04d}-{m + 1:02d}"


def events(conn, start: date, end: date, engineer: str = "", today: date = None) -> list:
    """كل مواعيد الفترة [start, end]. engineer = مواعيد هذا المهندس فقط."""
    today = today or date.today()
    out = []
    has_g = _table(conn, "tender_guarantees")
    rows = conn.execute(
        "SELECT m.id, m.title, m.owner, m.submission_date, m.assigned_engineer, m.status" +
        (", g.due_date, g.status FROM master_tenders m LEFT JOIN tender_guarantees g ON g.tender_row_id = m.id"
         if has_g else ", NULL, NULL FROM master_tenders m") +
        " WHERE m.status <> 'REJECTED'").fetchall()
    for rid, title, owner, raw, eng, status, g_due, g_status in rows:
        eng = eng or ""
        if engineer and eng != engineer:
            continue
        deadline = parse_deadline(raw)
        if deadline and start <= deadline <= end:
            state = "deleted" if status == "DELETED" else ("closed" if status in ACTIVE_EXCLUDED else "active")
            out.append({"kind": "deadline", "date": deadline.isoformat(), "id": rid, "title": title,
                        "owner": owner or "", "engineer": eng, "state": state})
        if status in ACTIVE_EXCLUDED or (g_status or "PENDING") in GUARANTEE_DONE:
            continue
        due = parse_deadline(g_due) or (deadline - timedelta(days=GUARANTEE_DAYS_BEFORE) if deadline else None)
        if due and start <= due <= end:
            out.append({"kind": "guarantee", "date": due.isoformat(), "id": rid, "title": title,
                        "owner": owner or "", "engineer": eng,
                        "state": "late" if due < today else ("progress" if g_status == "IN_PROGRESS" else "pending")})
    if _table(conn, "tender_tasks"):
        sql = ("SELECT t.id, t.title, t.engineer, t.status, t.due_date, m.title, m.id FROM tender_tasks t "
               "LEFT JOIN master_tenders m ON m.id = t.tender_row_id WHERE t.due_date BETWEEN ? AND ?")
        args = [start.isoformat(), end.isoformat()]
        if engineer:
            sql += " AND t.engineer = ?"
            args.append(engineer)
        for tid, title, eng, status, due, tender, tender_id in conn.execute(sql, args):
            state = "done" if status == "done" else ("late" if due < today.isoformat() else status)
            out.append({"kind": "task", "date": due[:10], "id": tid, "title": title, "tender": tender or "",
                        "tender_id": tender_id, "engineer": eng or "", "state": state})
    out.sort(key=lambda e: (e["date"], _ORDER[e["kind"]], e["state"] == "done", e["title"]))
    return out


def month_view(conn, month: str = "", engineer: str = "", today: date = None) -> dict:
    today = today or date.today()
    first = parse_month(month, today)
    start, end = grid_range(first)
    evs = events(conn, start, end, engineer, today)
    by_day = {}
    for e in evs:
        by_day.setdefault(e["date"], []).append(e)
    days, d = [], start
    while d <= end:
        days.append({"date": d.isoformat(), "day": d.day, "in_month": d.month == first.month,
                     "weekend": d.weekday() in (4, 5), "today": d == today, "events": by_day.get(d.isoformat(), [])})
        d += timedelta(days=1)
    inside = [e for e in evs if e["date"][:7] == first.isoformat()[:7]]
    open_ = [e for e in inside if e["state"] not in ("done", "closed", "deleted")]
    load = {}
    for e in open_:
        load[e["date"]] = load.get(e["date"], 0) + 1
    busiest = max(load.items(), key=lambda kv: (kv[1], kv[0] >= today.isoformat())) if load else None
    return {
        "month": first.isoformat()[:7], "label": f"{MONTHS[first.month - 1]} {first.year}",
        "prev": _shift(first, -1), "next": _shift(first, 1), "this": today.isoformat()[:7],
        "today": today.isoformat(), "engineer": engineer, "weekdays": WEEKDAYS, "days": days,
        "summary": {
            "deadlines": sum(e["kind"] == "deadline" and e["state"] == "active" for e in inside),
            "guarantees": sum(e["kind"] == "guarantee" for e in inside),
            "tasks": sum(e["kind"] == "task" and e["state"] != "done" for e in inside),
            "late": sum(e["state"] == "late" for e in inside),
            "busiest": {"date": busiest[0], "count": busiest[1]} if busiest and busiest[1] > 1 else None,
        },
    }


def engineers(conn) -> list:
    return [r[0] for r in conn.execute("SELECT name FROM engineers WHERE is_active=1 ORDER BY name")]


def connect(db_path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))
