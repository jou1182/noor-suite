# -*- coding: utf-8 -*-
"""Dashboard data layer (get_dashboard_data, deadline helpers).

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
import sqlite3
from datetime import datetime, timedelta
from web_core import DB_PATH, _guarantee_effective_due, ensure_guarantees_table
# ══════════════════════════════════════════════════════
# DATA LAYER
# ══════════════════════════════════════════════════════
def get_dashboard_data():
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row

        tenders = conn.execute("""
            SELECT t.id, t.title, t.owner, t.submission_date, t.assigned_engineer,
                   t.engineer_locked, t.date_locked,
                   t.business_type, t.sector, t.status, t.missing_seen_count,
                   COALESCE(n.submitted_to_upload,  0) AS submitted_to_upload,
                   COALESCE(n.uploaded_to_platform, 0) AS uploaded_to_platform,
                   COALESCE(n.submitted_to_review,  0) AS submitted_to_review,
                   COALESCE(n.is_extended,           0) AS is_extended
            FROM master_tenders t
            LEFT JOIN tender_notes n ON n.tender_id = t.id
            WHERE t.status NOT IN ('CLOSED','REJECTED')
            ORDER BY
                CASE WHEN t.submission_date IS NULL OR t.submission_date='' OR t.submission_date='N/A' THEN 1 ELSE 0 END,
                t.submission_date ASC
        """).fetchall()

        pending_count = conn.execute("""
            SELECT COUNT(*) FROM pending_changes
            WHERE status IN ('PENDING_APPROVAL','NOTIFIED')
        """).fetchone()[0]

        pending_tenders = conn.execute("""
            SELECT p.id, p.title, p.change_type, p.submission_date,
                   p.suggested_engineer, p.status, p.created_at, p.approval_stage,
                   mt.id AS master_id
            FROM pending_changes p
            LEFT JOIN master_tenders mt ON mt.title = p.title
            WHERE p.status IN ('PENDING_APPROVAL','NOTIFIED')
            ORDER BY p.created_at DESC
        """).fetchall()

        closed_count = conn.execute(
            "SELECT COUNT(*) FROM master_tenders WHERE status='CLOSED'"
        ).fetchone()[0]

        engineers = conn.execute(
            "SELECT name, capacity FROM engineers WHERE is_active=1 ORDER BY name"
        ).fetchall()

        eng_load = {}
        for e in engineers:
            cnt = conn.execute("""
                SELECT COUNT(*) FROM master_tenders
                WHERE assigned_engineer=? AND status NOT IN ('CLOSED','REJECTED')
            """, (e["name"],)).fetchone()[0]
            cap = max(e["capacity"] or 5, 1)
            pct = min(round((cnt / cap) * 100), 100)
            if pct >= 85:
                color = "danger"; hex_color = "#f85149"
            elif pct >= 60:
                color = "warning"; hex_color = "#e3b341"
            else:
                color = "success"; hex_color = "#3fb950"
            eng_load[e["name"]] = {
                "count": cnt, "capacity": cap, "pct": pct,
                "color": color, "hex": hex_color
            }

    enriched = []
    for t in tenders:
        row = dict(t)
        days, badge, icon = _deadline_info(row["submission_date"])
        row["days_left"] = days
        row["badge"]     = badge
        row["icon"]      = icon
        enriched.append(row)

    urgent   = sum(1 for r in enriched if isinstance(r["days_left"], int) and 0 <= r["days_left"] <= 3)
    warning  = sum(1 for r in enriched if isinstance(r["days_left"], int) and 4 <= r["days_left"] <= 7)
    ok       = sum(1 for r in enriched if isinstance(r["days_left"], int) and r["days_left"] > 7)
    expired  = sum(1 for r in enriched if isinstance(r["days_left"], int) and r["days_left"] < 0)
    submitted_upload  = sum(1 for r in enriched if r.get("submitted_to_upload"))
    uploaded_platform = sum(1 for r in enriched if r.get("uploaded_to_platform"))

    # Owner distribution (top 10)
    owner_dist = {}
    for r in enriched:
        ow = (r.get("owner") or "غير محدد").strip() or "غير محدد"
        owner_dist[ow] = owner_dist.get(ow, 0) + 1
    owner_dist = dict(sorted(owner_dist.items(), key=lambda x: x[1], reverse=True)[:10])

    # v5.6: today deadline count
    today = datetime.now().date()
    today_count = sum(1 for r in enriched if isinstance(r["days_left"], int) and r["days_left"] == 0)

    # v5.6: upcoming bank guarantees
    ensure_guarantees_table()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        g_rows = {r["tender_row_id"]: dict(r) for r in conn.execute("SELECT * FROM tender_guarantees")}
    guarantees = []
    for r in enriched:
        g = g_rows.get(r["id"], {})
        if g.get("status") in ("READY", "SUBMITTED", "NOT_REQUIRED"):
            continue
        due, is_auto = _guarantee_effective_due(r["submission_date"], g.get("due_date", ""))
        if due is None:
            continue
        dleft = (due - today).days
        if dleft < -2:
            continue
        label = ("متأخر!" if dleft < 0 else "اليوم" if dleft == 0 else
                 "غداً" if dleft == 1 else f"بعد {dleft} يوم")
        cls = "g-red" if dleft <= 0 else ("g-amber" if dleft <= 3 else "g-green")
        guarantees.append({"id": r["id"], "title": r["title"], "owner": r.get("owner") or "",
                           "due": due.isoformat(), "label": label, "cls": cls,
                           "dleft": dleft, "auto": is_auto})
    guarantees.sort(key=lambda x: x["dleft"])
    guarantees = guarantees[:6]

    # v5.6: month calendar (Sunday-first, Saudi week)
    import calendar as _pcal
    _pcal.setfirstweekday(6)
    marks = {}
    for r in enriched:
        try:
            d = datetime.strptime(str(r["submission_date"]).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if d.year == today.year and d.month == today.month:
            dl = (d - today).days
            lvl = 3 if dl <= 3 else (2 if dl <= 7 else 1)
            marks[d.day] = max(marks.get(d.day, 0), lvl)
    for g in guarantees:
        gd = datetime.strptime(g["due"], "%Y-%m-%d").date()
        if gd.year == today.year and gd.month == today.month:
            marks[gd.day] = max(marks.get(gd.day, 0), 4)
    _AR_M = ["يناير","فبراير","مارس","أبريل","مايو","يونيو",
             "يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
    cal = {"label": f"{_AR_M[today.month-1]} {today.year}",
           "weeks": _pcal.monthcalendar(today.year, today.month),
           "marks": marks, "today": today.day}

    # v5.9.6: daily tender volume, last 14 days (Phase 3 -- ROADMAP_V6.md analytics)
    with sqlite3.connect(str(DB_PATH)) as conn:
        trend_rows = conn.execute(
            "SELECT DATE(created_at) as d, COUNT(*) as c FROM master_tenders "
            "WHERE created_at >= datetime('now', '-14 days') GROUP BY d ORDER BY d"
        ).fetchall()
    trend_map = {r[0]: r[1] for r in trend_rows}
    daily_trend = {"labels": [], "data": []}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        daily_trend["labels"].append(d[5:])   # MM-DD, shorter x-axis labels
        daily_trend["data"].append(trend_map.get(d, 0))

    return {
        "tenders":           enriched,
        "total_active":      len(enriched),
        "pending_count":     pending_count,
        "closed_count":      closed_count,
        "urgent":            urgent,
        "warning":           warning,
        "ok_count":          ok,
        "expired":           expired,
        "submitted_upload":  submitted_upload,
        "uploaded_platform": uploaded_platform,
        "owner_dist":        owner_dist,
        "engineers":         [dict(e) for e in engineers],
        "eng_load":          eng_load,
        "pending_tenders":   [dict(p) for p in pending_tenders],
        "refreshed":         datetime.now().strftime("%Y-%m-%d  %H:%M"),
        "today_count":       today_count,
        "guarantees":        guarantees,
        "cal":               cal,
        "daily_trend":       daily_trend,
    }

def _deadline_info(date_str):
    try:
        dt   = datetime.strptime(str(date_str).strip()[:10], "%Y-%m-%d")
        days = (dt.date() - datetime.now().date()).days
        if days < 0:  return days, "secondary", "⚫"
        if days <= 3: return days, "danger",    "🔴"
        if days <= 7: return days, "warning",   "🟡"
        return days, "success", "🟢"
    except Exception:
        return None, "light", "⚪"

