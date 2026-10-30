# -*- coding: utf-8 -*-
"""صفحة «قوالب المهام» /admin/task-templates (2026-09-25) — للإدارة، مع لوحة المهام (features: kanban).
قالب لكل نوع أعمال يحدد مهام المنافسة الجديدة وأيامها قبل الإغلاق. المنطق في tasks_core (template_for/save_template)."""
import json

from flask import abort, jsonify, render_template_string, request

import tasks_core
from company_profile import feature_enabled
from dashboard_templates import TASK_TEMPLATES_HTML
from web_core import admin_required, app
from web_tasks import _conn


def _require_feature():
    if not feature_enabled(tasks_core.FEATURE):
        abort(404)


def _audit(conn, action: str, business_type: str, details: str):
    conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                 (action, business_type or "الافتراضي", details, "WebAdmin"))


@app.route("/admin/task-templates")
@admin_required
def admin_task_templates():
    _require_feature()
    return render_template_string(TASK_TEMPLATES_HTML, sidebar_docked=True)


@app.route("/api/task-templates")
@admin_required
def api_task_templates():
    _require_feature()
    with _conn() as conn:
        data = tasks_core.templates_overview(conn)
        conn.commit()
    return jsonify({"ok": True, **data})


@app.route("/api/task-templates", methods=["POST"])
@admin_required
def api_task_templates_save():
    _require_feature()
    body = request.get_json(silent=True) or {}
    with _conn() as conn:
        try:
            rows = tasks_core.save_template(conn, body.get("business_type", ""), body.get("rows"))
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        _audit(conn, "TASK_TEMPLATE_SAVED", tasks_core._norm_type(body.get("business_type")),
               json.dumps([r["title"] for r in rows], ensure_ascii=False)[:900])
        conn.commit()
    return jsonify({"ok": True, "rows": rows})


@app.route("/api/task-templates/delete", methods=["POST"])
@admin_required
def api_task_templates_delete():
    _require_feature()
    bt = tasks_core._norm_type((request.get_json(silent=True) or {}).get("business_type"))
    with _conn() as conn:
        n = tasks_core.delete_template(conn, bt)
        _audit(conn, "TASK_TEMPLATE_RESET", bt, f"{n} rows")
        conn.commit()
    return jsonify({"ok": True, "deleted": n})
