# -*- coding: utf-8 -*-
"""HTML pages: dashboard, tender detail, results, owners, engineer view, CSV export, /healthz, /logo.

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
from flask import Response
import sqlite3
from dashboard_templates import DASHBOARD_HTML, ENGINEER_VIEW_HTML, OWNERS_HTML, RESULTS_HTML, TENDER_DETAIL_HTML
from datetime import datetime
from flask import jsonify, render_template_string, request
from pathlib import Path
from instance_paths import HEALTHZ_REQUIRE_BACKUP
import tasks_core
from company_profile import feature_enabled
from web_core import DB_PATH, VERSION, _LOGO_DATA_URI, _LOGO_PNG_BYTES, app, get_config, login_required
from web_data import _deadline_info, get_dashboard_data
@app.route('/logo')
def serve_logo():
    """Serve logo — custom logo from DB overrides the built-in one."""
    custom_b64 = get_config('custom_logo_b64', '')
    if custom_b64:
        import base64 as _b64m
        try:
            data = _b64m.b64decode(custom_b64)
            return Response(data, mimetype='image/png',
                            headers={'Cache-Control': 'no-cache, must-revalidate'})
        except Exception:
            pass
    return Response(
        _LOGO_PNG_BYTES,
        mimetype='image/png',
        headers={'Cache-Control': 'public, max-age=3600, immutable'}
    )

# ══════════════════════════════════════════════════════
# TENDER DETAIL + NOTES API
# ══════════════════════════════════════════════════════
@app.route("/tender/<int:row_id>")
@login_required
def tender_detail(row_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        t = conn.execute("""
            SELECT t.*,
                   COALESCE(n.notes,'')                AS nt_notes,
                   COALESCE(n.is_extended,0)            AS nt_extended,
                   COALESCE(n.extension_count,0)        AS nt_ext_count,
                   COALESCE(n.extension_dates,'')        AS nt_ext_dates,
                   COALESCE(n.submitted_to_review,0)    AS nt_s_review,
                   COALESCE(n.review_date,'')            AS nt_review_date,
                   COALESCE(n.submitted_to_upload,0)    AS nt_s_upload,
                   COALESCE(n.upload_submit_date,'')     AS nt_upload_date,
                   COALESCE(n.uploaded_to_platform,0)   AS nt_uploaded,
                   COALESCE(n.platform_upload_date,'')  AS nt_platform_date
            FROM master_tenders t
            LEFT JOIN tender_notes n ON n.tender_id = t.id
            WHERE t.id=?
        """, (row_id,)).fetchone()
        if not t:
            return "<h2 dir='rtl' style='font-family:Tajawal;padding:2rem'>المنافسة غير موجودة</h2>", 404
        engineers = conn.execute(
            "SELECT name FROM engineers WHERE is_active=1 ORDER BY name"
        ).fetchall()
    days, badge, icon = _deadline_info(t["submission_date"])
    from_page = request.args.get("from", "")
    back_url  = "/engineer-view" if from_page == "engineer" else "/"
    owner_risk = ""
    if feature_enabled("analytics"):        # مخاطرة الجهة (تاريخ إلغاءاتها) قبل أن يبدأ الفريق — صفحة /analytics
        import analytics_core
        with sqlite3.connect(str(DB_PATH)) as conn:
            owner_risk = analytics_core.owner_risk_level(analytics_core.load_tenders(conn), (t["owner"] or "").strip())
    return render_template_string(TENDER_DETAIL_HTML,
        t=dict(t),
        engineers=[e["name"] for e in engineers],
        days_left=days, badge=badge, icon=icon,
        back_url=back_url, owner_risk=owner_risk)

# ══════════════════════════════════════════════════════
# CSV EXPORT
# ══════════════════════════════════════════════════════
@app.route("/healthz")
def healthz():
    """v5.7.5: نبض عميق للمراقبة الخارجية — 200 فقط إذا كانت المنظومة تعمل فعلاً:
    قاعدة البيانات مقروءة + دورة فحص البوت حديثة + النسخة الاحتياطية طازجة."""
    _root = Path(__file__).parent
    now = datetime.now()
    checks, ok_all = {}, True
    try:
        with sqlite3.connect(str(DB_PATH), timeout=5) as conn:
            n = conn.execute("SELECT COUNT(*) FROM master_tenders").fetchone()[0]
        checks["db"] = {"ok": True, "tenders": n}
    except Exception as e:
        checks["db"] = {"ok": False, "error": str(e)[:80]}
        ok_all = False
    try:
        blog = _root / "logs" / "bot.log"
        age_min = (now - datetime.fromtimestamp(blog.stat().st_mtime)).total_seconds() / 60
        fresh = age_min < 15
        checks["bot_cycle"] = {"ok": fresh, "log_age_min": round(age_min, 1)}
        if not fresh:
            ok_all = False
    except Exception as e:
        checks["bot_cycle"] = {"ok": False, "error": str(e)[:80]}
        ok_all = False
    try:
        bdir = _root / "backups"
        newest = max(bdir.glob("backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, default=None)
        if newest:
            age_h = (now - datetime.fromtimestamp(newest.stat().st_mtime)).total_seconds() / 3600
            bok = age_h < 26
            checks["backup"] = {"ok": bok, "age_hours": round(age_h, 1)}
            if not bok:
                ok_all = False
        elif not HEALTHZ_REQUIRE_BACKUP:
            # نسخة عرض/تدريب بلا نسخ احتياطي يومي — لا تُسقط الفحص (HEALTHZ_REQUIRE_BACKUP=0 في .env)
            checks["backup"] = {"ok": True, "note": "not required for this instance"}
        else:
            checks["backup"] = {"ok": False, "error": "no backups found"}
            ok_all = False
    except Exception as e:
        checks["backup"] = {"ok": False, "error": str(e)[:80]}
        ok_all = False
    return jsonify({"ok": ok_all, "version": VERSION, "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "checks": checks}), (200 if ok_all else 503)


@app.route("/owners")
@login_required
def owners_page():
    """v5.6: owner-memory page - relationship class + priority score per owner."""
    import json as _json
    today = datetime.now().date()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        base = conn.execute("""
            SELECT TRIM(owner) ow, COUNT(*) total,
                   SUM(CASE WHEN status NOT IN ('CLOSED','REJECTED') THEN 1 ELSE 0 END) active,
                   MIN(CASE WHEN status NOT IN ('CLOSED','REJECTED')
                             AND submission_date >= date('now') THEN submission_date END) next_dl
            FROM master_tenders
            WHERE owner IS NOT NULL AND TRIM(owner) != '' AND TRIM(LOWER(owner)) NOT IN ('n/a','nan')
            GROUP BY TRIM(owner)""").fetchall()
        res = conn.execute("""
            SELECT TRIM(owner) ow,
                   SUM(CASE WHEN did_submit=1 THEN 1 ELSE 0 END) submitted,
                   SUM(CASE WHEN result='won'  THEN 1 ELSE 0 END) wins,
                   SUM(CASE WHEN result='lost' THEN 1 ELSE 0 END) losses
            FROM tender_results
            WHERE owner IS NOT NULL AND TRIM(owner) != ''
            GROUP BY TRIM(owner)""").fetchall()
        ext_rows = conn.execute(
            "SELECT details_json FROM pending_changes WHERE change_type='UPDATED_DATE'").fetchall()
    resmap = {r["ow"]: dict(r) for r in res}
    ext = {}
    OWNER_KEY = "المالك"
    for r in ext_rows:
        try:
            ow = str(_json.loads(r["details_json"] or "{}").get(OWNER_KEY, "")).strip()
            if ow:
                ext[ow] = ext.get(ow, 0) + 1
        except Exception:
            pass
    owners = []
    for b in base:
        ow = b["ow"]
        rr = resmap.get(ow, {})
        submitted = rr.get("submitted") or 0
        wins      = rr.get("wins") or 0
        losses    = rr.get("losses") or 0
        active    = b["active"] or 0
        decided   = wins + losses
        win_rate  = round(wins / decided * 100) if decided else None
        days_next = None
        if b["next_dl"]:
            try:
                days_next = (datetime.strptime(str(b["next_dl"])[:10], "%Y-%m-%d").date() - today).days
            except Exception:
                pass
        score = min(100, active * 22
                    + (20 if (days_next is not None and days_next <= 7)
                       else 10 if (days_next is not None and days_next <= 21) else 0)
                    + wins * 8 + min(submitted, 8))
        if wins and active:
            cls, ccls = "عميل رابح نشط", "c-green"
        elif wins:
            cls, ccls = "رابح — يحتاج تنشيط", "c-amber"
        elif active:
            cls, ccls = "فرصة جارية", "c-blue"
        elif submitted:
            cls, ccls = "علاقة تحتاج تنشيط", "c-muted"
        else:
            cls, ccls = "أرشيف", "c-muted"
        owners.append({"name": ow, "total": b["total"], "active": active,
                       "submitted": submitted, "wins": wins, "losses": losses,
                       "win_rate": win_rate, "ext": ext.get(ow, 0),
                       "next_dl": (b["next_dl"] or "")[:10], "days_next": days_next,
                       "score": score, "cls": cls, "ccls": ccls})
    owners.sort(key=lambda x: (-x["score"], -x["active"]))
    s = {"total": len(owners),
         "active_org": sum(1 for o in owners if o["active"]),
         "winners": sum(1 for o in owners if o["wins"]),
         "submissions": sum(o["submitted"] for o in owners)}
    return render_template_string(OWNERS_HTML, owners=owners, s=s, logo_uri=_LOGO_DATA_URI,
                                  refreshed=datetime.now().strftime("%Y-%m-%d %H:%M"))


@app.route("/export/csv")
@login_required
def export_csv():
    import io, csv
    from flask import Response
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT t.id, t.tender_id, t.title, t.owner, t.submission_date,
                   t.assigned_engineer, t.business_type, t.sector, t.status,
                   COALESCE(n.is_extended, 0)          AS is_extended,
                   COALESCE(n.extension_count, 0)      AS extension_count,
                   COALESCE(n.extension_dates, '')     AS extension_dates,
                   COALESCE(n.submitted_to_review, 0)  AS submitted_to_review,
                   COALESCE(n.submitted_to_upload, 0)  AS submitted_to_upload,
                   COALESCE(n.uploaded_to_platform, 0) AS uploaded_to_platform,
                   COALESCE(n.notes, '')               AS notes
            FROM master_tenders t
            LEFT JOIN tender_notes n ON n.tender_id = t.id
            WHERE t.status NOT IN ('CLOSED','REJECTED')
            ORDER BY t.submission_date ASC
        """).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["#", "رقم المنافسة", "اسم المنافسة", "الجهة المالكة",
                     "تاريخ التقديم", "المهندس المسؤول", "نوع الأعمال", "القطاع", "الحالة",
                     "تمديد", "عدد التمديدات", "تواريخ التمديد",
                     "قُدِّم للمراجعة", "مرفوع لقسم الرفع", "منشور على المنصة", "ملاحظات"])
    for i, r in enumerate(rows, 1):
        writer.writerow([
            i, r["tender_id"] or "", r["title"] or "", r["owner"] or "",
            (r["submission_date"] or "")[:10],
            r["assigned_engineer"] or "", r["business_type"] or "",
            r["sector"] or "", r["status"] or "",
            "نعم" if r["is_extended"] else "لا",
            r["extension_count"],
            r["extension_dates"] or "",
            "نعم" if r["submitted_to_review"] else "لا",
            "نعم" if r["submitted_to_upload"] else "لا",
            "نعم" if r["uploaded_to_platform"] else "لا",
            r["notes"] or "",
        ])
    fname = f"tenders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        "﻿" + output.getvalue(),   # BOM for Arabic in Excel
        mimetype="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


@app.route("/results")
@login_required
def results_page():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT tr.id AS rec_id, tr.title, tr.owner, tr.business_type,
                   tr.assigned_engineer, tr.submission_date,
                   tr.did_submit, tr.result, tr.our_price, tr.winning_price,
                   tr.notes, tr.recorded_at,
                   mt.id AS master_id
            FROM tender_results tr
            LEFT JOIN master_tenders mt ON mt.tender_id = tr.tender_id
            ORDER BY tr.recorded_at DESC
        """).fetchall()

    total    = len(rows)
    submits  = sum(1 for r in rows if r["did_submit"])
    won      = sum(1 for r in rows if r["result"] == "won")
    lost     = sum(1 for r in rows if r["result"] == "lost")
    unknown  = sum(1 for r in rows if r["result"] == "unknown")
    decided  = won + lost
    # النتائج لا تُعلن دائماً في السوق — النسبة الصادقة تُحسب من المعروف فقط
    win_rate = round((won / decided * 100) if decided else 0)

    eng_stats = {}
    for r in rows:
        if not r["did_submit"]: continue
        e = r["assigned_engineer"] or "غير محدد"
        if e not in eng_stats:
            eng_stats[e] = {"submitted": 0, "won": 0, "lost": 0}
        eng_stats[e]["submitted"] += 1
        if r["result"] == "won":
            eng_stats[e]["won"] += 1
        elif r["result"] == "lost":
            eng_stats[e]["lost"] += 1
    for e in eng_stats:
        s = eng_stats[e]
        s["decided"] = s["won"] + s["lost"]
        s["rate"]  = round(s["won"] / s["decided"] * 100) if s["decided"] else 0
        s["color"] = "success" if s["rate"] >= 60 else ("warning" if s["rate"] >= 30 else "danger")
        s["hex"]   = "#3fb950" if s["rate"] >= 60 else ("#e3b341" if s["rate"] >= 30 else "#f85149")

    # v5.6.1: waiting days + price gap per row
    today = datetime.now().date()
    enriched_rows = []
    for r in rows:
        d = dict(r)
        wd = None
        if d["did_submit"] and (d["result"] or "pending") == "pending":
            try:
                sd = datetime.strptime(str(d["submission_date"])[:10], "%Y-%m-%d").date()
                wd = (today - sd).days
            except Exception:
                pass
        d["waiting_days"] = wd
        gap = None
        if d["our_price"] and d["winning_price"]:
            try:
                gap = round((d["our_price"] - d["winning_price"]) / d["winning_price"] * 100, 1)
            except Exception:
                pass
        d["price_gap"] = gap
        enriched_rows.append(d)

    followup = sorted([d for d in enriched_rows if (d["waiting_days"] or 0) >= 21],
                      key=lambda x: -(x["waiting_days"] or 0))[:8]
    pending_res = sum(1 for d in enriched_rows
                      if d["did_submit"] and (d["result"] or "pending") == "pending")

    # monthly timeline: last 8 months
    ym = []
    y, m = today.year, today.month
    for _ in range(8):
        ym.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    ym.reverse()
    tl = {k: {"sub": 0, "won": 0, "lost": 0} for k in ym}
    for d in enriched_rows:
        k = str(d["submission_date"] or "")[:7]
        if k in tl and d["did_submit"]:
            tl[k]["sub"] += 1
            if d["result"] == "won":
                tl[k]["won"] += 1
            elif d["result"] == "lost":
                tl[k]["lost"] += 1
    timeline = {"labels": ym,
                "sub":  [tl[k]["sub"]  for k in ym],
                "won":  [tl[k]["won"]  for k in ym],
                "lost": [tl[k]["lost"] for k in ym]}

    # owner win stats (top 6 by submissions)
    ostats = {}
    for d in enriched_rows:
        if not d["did_submit"]:
            continue
        ow = (d["owner"] or "غير محدد").strip() or "غير محدد"
        o = ostats.setdefault(ow, {"submitted": 0, "won": 0, "lost": 0})
        o["submitted"] += 1
        if d["result"] == "won":
            o["won"] += 1
        elif d["result"] == "lost":
            o["lost"] += 1
    owner_stats = sorted(
        ({"name": k, "submitted": v["submitted"], "won": v["won"],
          "decided": v["won"] + v["lost"],
          "rate": round(v["won"] / (v["won"] + v["lost"]) * 100) if (v["won"] + v["lost"]) else 0}
         for k, v in ostats.items()),
        key=lambda x: -x["submitted"])[:6]

    return render_template_string(RESULTS_HTML,
        version=VERSION,
        rows=enriched_rows,
        total=total, submits=submits, won=won, lost=lost,
        win_rate=win_rate, eng_stats=eng_stats,
        unknown=unknown, decided=decided,
        followup=followup, pending_res=pending_res,
        timeline=timeline, owner_stats=owner_stats,
        refreshed=datetime.now().strftime("%Y-%m-%d %H:%M")
    ,
        logo_uri=_LOGO_DATA_URI)

@app.route("/")
@login_required
def dashboard():
    data = get_dashboard_data()
    if not data:
        return "<h2 dir='rtl' style='font-family:Tajawal'>⚠️ قاعدة البيانات غير موجودة.</h2>", 500
    return render_template_string(DASHBOARD_HTML, **data,
        logo_uri=_LOGO_DATA_URI)
# ENGINEER_PIN: moved to bp_engineer.py

# ═══════════════════════════════════════════════════════════════
# ENGINEER PORTAL — بوابة المهندس
# ═══════════════════════════════════════════════════════════════

# ENGINEER_LOGIN_HTML: moved to dashboard_templates.py

# ENGINEER_DASH_HTML: moved to dashboard_templates.py




# ═══════════════════════════════════════════════════════════════
# ENGINEER PORTAL ROUTES
# ═══════════════════════════════════════════════════════════════

# engineer_home: moved to bp_engineer.py

# engineer_dashboard: moved to bp_engineer.py

# engineer_logout: moved to bp_engineer.py

# api_eng_update_status: moved to bp_engineer.py



# ═══════════════════════════════════════════════════════════════
# ENGINEER VIEW — بوابة المهندسين (داخل المنصة الرئيسية)
# ═══════════════════════════════════════════════════════════════

# ENGINEER_VIEW_HTML: moved to dashboard_templates.py


# ── بوابة المهندسين (داخل المنصة) ──────────────────────────────────────────
@app.route('/engineer-view')
@login_required
def engineer_view():
    import sqlite3 as _sq3
    from datetime import date

    with _sq3.connect(str(DB_PATH)) as conn:
        conn.row_factory = _sq3.Row

        engineers = [r[0] for r in conn.execute(
            "SELECT DISTINCT assigned_engineer FROM master_tenders "
            "WHERE assigned_engineer IS NOT NULL AND assigned_engineer != '' "
            "ORDER BY assigned_engineer"
        ).fetchall()]

        rows = conn.execute("""
            SELECT m.id, m.title, m.assigned_engineer,
                   m.submission_date, m.business_type, m.engineer_locked,
                   COALESCE(tr.did_submit, 0) as did_submit,
                   tr.result, tr.our_price, tr.winning_price
            FROM master_tenders m
            LEFT JOIN tender_results tr ON tr.tender_id = m.tender_id
            WHERE m.assigned_engineer IS NOT NULL AND m.assigned_engineer != ''
            ORDER BY
              CASE WHEN m.submission_date IS NULL OR m.submission_date='' THEN 1 ELSE 0 END,
              m.submission_date ASC
        """).fetchall()

    tenders = []
    today = date.today()
    for r in rows:
        t = dict(r)
        try:
            cdate = tasks_core.parse_deadline(t["submission_date"])   # YYYY-MM-DD أو DD/MM/YYYY (إدخال يدوي)
            t["days_left"] = (cdate - today).days if cdate else None
        except Exception:
            t["days_left"] = None
        tenders.append(t)

    total     = len(tenders)
    pending   = sum(1 for t in tenders if not t["did_submit"] and not t["result"])
    submitted = sum(1 for t in tenders if t["did_submit"] and not t["result"])
    won       = sum(1 for t in tenders if t["result"] == "won")
    lost      = sum(1 for t in tenders if t["result"] == "lost")
    eng_counts = {eng: sum(1 for t in tenders if t["assigned_engineer"] == eng)
                  for eng in engineers}

    return render_template_string(
        ENGINEER_VIEW_HTML,
        engineers=engineers,
        tenders=tenders,
        eng_counts=eng_counts,
        total_tenders=total,
        pending_tenders=pending,
        submitted_tenders=submitted,
        won_tenders=won,
        lost_tenders=lost,
    )

