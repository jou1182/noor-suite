# -*- coding: utf-8 -*-
"""صفحة الإدارة لحسابات المهندسين (/admin/engineers) — تعمل فقط مع "features": ["engineer_accounts"].

الكلمة المؤقتة تُرسل في رد JSON لمتصفح الإدارة مرة واحدة فقط ولا تُحفظ ولا تُسجَّل في السجلات.
المنطق في engineer_accounts.py، والدخول في bp_engineer.py.
"""
from contextlib import closing

from flask import abort, jsonify, render_template_string, request

import engineer_accounts
import tasks_core
from company_profile import feature_enabled
from dashboard_templates import ADMIN_ENGINEERS_HTML
from web_core import DB_PATH, admin_required, app


def _require_feature():
    if not feature_enabled(engineer_accounts.FEATURE):
        abort(404)


def _conn():
    return closing(tasks_core.connect(DB_PATH))


def _audit(conn, action: str, engineer: str):
    conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                 (action, engineer, "Engineer account", "WebAdmin"))


@app.route("/admin/engineers")
@admin_required
def admin_engineers():
    _require_feature()
    with _conn() as conn:
        rows = engineer_accounts.overview(conn)
        conn.commit()
    return render_template_string(ADMIN_ENGINEERS_HTML, rows=rows, sidebar_docked=True,
                                  min_length=engineer_accounts.MIN_LENGTH)


@app.route("/admin/engineers/issue", methods=["POST"])
@admin_required
def admin_engineers_issue():
    """إنشاء حساب أو إعادة تعيين كلمة المرور ← كلمة مؤقتة تظهر للإدارة مرة واحدة."""
    _require_feature()
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    with _conn() as conn:
        try:
            temp = engineer_accounts.issue(conn, name)
        except LookupError as e:
            return jsonify({"ok": False, "msg": str(e)}), 404
        _audit(conn, "ENG_ACCOUNT_ISSUED", name)
        conn.commit()
    return jsonify({"ok": True, "name": name, "temp_password": temp})


@app.route("/admin/engineers/active", methods=["POST"])
@admin_required
def admin_engineers_active():
    _require_feature()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    active = bool(data.get("active"))
    with _conn() as conn:
        if not engineer_accounts.set_active(conn, name, active):
            return jsonify({"ok": False, "msg": "لا يوجد حساب لهذا المهندس"}), 404
        _audit(conn, "ENG_ACCOUNT_ENABLED" if active else "ENG_ACCOUNT_DISABLED", name)
        conn.commit()
    return jsonify({"ok": True})


@app.route("/admin/engineers/add", methods=["POST"])
@admin_required
def admin_engineers_add():
    """إضافة مهندس معيَّن حديثاً (أو إعادة مهندس سابق)."""
    _require_feature()
    data = request.get_json(silent=True) or {}
    with _conn() as conn:
        try:
            result = engineer_accounts.add_engineer(conn, data.get("name"), data.get("capacity", 5))
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        if result == "EXISTS":
            return jsonify({"ok": False, "msg": "هذا المهندس موجود بالفعل في الفريق"}), 409
        name = " ".join(str(data.get("name")).split())
        _audit(conn, "ENGINEER_ADDED" if result == "ADDED" else "ENGINEER_REACTIVATED", name)
        conn.commit()
    return jsonify({"ok": True, "result": result, "name": name})


@app.route("/admin/engineers/remove", methods=["POST"])
@admin_required
def admin_engineers_remove():
    """إزالة مهندس ترك الشركة (إيقاف لا حذف — تاريخه يبقى)."""
    _require_feature()
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    with _conn() as conn:
        try:
            left = engineer_accounts.remove_engineer(conn, name)
        except LookupError as e:
            return jsonify({"ok": False, "msg": str(e)}), 404
        _audit(conn, "ENGINEER_REMOVED", name)
        conn.commit()
    return jsonify({"ok": True, **left})
