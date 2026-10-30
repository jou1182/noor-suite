# -*- coding: utf-8 -*-
"""صفحة التحليلات /analytics (2026-09-25) — تعمل فقط مع "features": ["analytics"] (النور).
المنطق والأرقام في analytics_core.py؛ هنا الصفحة والواجهات والتصدير فقط."""
import csv
import io
from contextlib import closing

from flask import Response, abort, jsonify, render_template_string, request

import analytics_core
from company_profile import feature_enabled
from dashboard_templates import ANALYTICS_HTML
from web_core import DB_PATH, app, login_required

FEATURE = "analytics"


def _require_feature():
    if not feature_enabled(FEATURE):
        abort(404)


def _period():
    p = request.args.get("period", "year")
    return p if p in analytics_core.PERIODS else "year"


@app.route("/analytics")
@login_required
def analytics_page():
    _require_feature()
    return render_template_string(ANALYTICS_HTML, sidebar_docked=True, periods=analytics_core.PERIODS)


@app.route("/api/analytics")
@login_required
def api_analytics():
    _require_feature()
    with closing(analytics_core.connect(DB_PATH)) as conn:
        return jsonify({"ok": True, **analytics_core.report(conn, _period())})


@app.route("/api/analytics/compare")
@login_required
def api_analytics_compare():
    _require_feature()
    a, b = request.args.get("a", ""), request.args.get("b", "")
    with closing(analytics_core.connect(DB_PATH)) as conn:
        return jsonify({"ok": True, **analytics_core.compare(analytics_core.load_tenders(conn), a, b)})


@app.route("/analytics/export.csv")
@login_required
def analytics_export():
    """تصدير أرقام الصفحة (المؤشرات + مخاطرة الجهات + الأعلى فوزاً) لإكسل."""
    _require_feature()
    with closing(analytics_core.connect(DB_PATH)) as conn:
        r = analytics_core.report(conn, _period())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["القسم", "البند", "القيمة"])
    labels = {"total": "المنافسات", "running": "جارية", "closing_week": "تُغلق خلال أسبوع", "submitted": "قدّمنا",
              "submit_rate": "نسبة التقديم %", "won": "فزنا", "win_rate": "نسبة الفوز %", "cancelled": "أُلغيت/حُذفت",
              "cancel_rate": "نسبة الإلغاء %", "guarantees14": "ضمانات خلال 14 يوماً"}
    for k, lbl in labels.items():
        w.writerow([f"المؤشرات ({r['period_label']})", lbl, r["kpis"].get(k, "")])
    for row in r["top_owners"]["rows"]:
        w.writerow(["الأعلى فوزاً", row["owner"], f"{row['won']}/{row['submitted']} ({row['rate']}%)"])
    for row in r["risk"]:
        w.writerow(["مخاطرة الجهات", row["owner"], f"{row['cancelled']}/{row['total']} ({row['rate']}%)"])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=analytics-{r['period']}.csv"})
