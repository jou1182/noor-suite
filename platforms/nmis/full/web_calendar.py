# -*- coding: utf-8 -*-
"""صفحة «التقويم» /calendar (2026-09-25) — features: calendar.
الفريق والإدارة: كل المواعيد مع فلتر المهندس. حساب المهندس الشخصي: مواعيده فقط (الفلتر مفروض عليه).
المنطق في calendar_core.py."""
from contextlib import closing

from flask import abort, jsonify, render_template_string, request

import calendar_core
from company_profile import feature_enabled
from dashboard_templates import CALENDAR_HTML
from web_core import DB_PATH, app
from web_tasks import _engineer_only, board_required


def _require_feature():
    if not feature_enabled(calendar_core.FEATURE):
        abort(404)


@app.route("/calendar")
@board_required
def calendar_page():
    _require_feature()
    me = _engineer_only()
    with closing(calendar_core.connect(DB_PATH)) as conn:
        names = [] if me else calendar_core.engineers(conn)
    return render_template_string(CALENDAR_HTML, sidebar_docked=True, me=me, engineers=names,
                                  weekdays=calendar_core.WEEKDAYS)


@app.route("/api/calendar")
@board_required
def api_calendar():
    _require_feature()
    me = _engineer_only()
    engineer = me or (request.args.get("engineer") or "").strip()[:80]
    with closing(calendar_core.connect(DB_PATH)) as conn:
        return jsonify({"ok": True, **calendar_core.month_view(conn, request.args.get("month", ""), engineer)})
