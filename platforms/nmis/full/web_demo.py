# -*- coding: utf-8 -*-
"""صفحة «وضع العرض» /admin/demo (2026-09-25) — للإدارة، وفقط لشركة مفعَّل لها features: demo (النور).
المنطق في demo_core.py: ملء ببيانات وهمية مترابطة (بنسخة احتياطية قبلها) ومسحها بضغطة."""
import sqlite3
from contextlib import closing

from flask import abort, jsonify, render_template_string, request

import demo_core
import source_core
from company_profile import feature_enabled
from dashboard_templates import ADMIN_DEMO_HTML
from web_core import DB_PATH, admin_required, app


def _require():
    if not feature_enabled(demo_core.FEATURE):
        abort(404)


def _conn():
    return closing(sqlite3.connect(str(DB_PATH)))


def _audit(conn, action: str, details: str):
    conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                 (action, "demo_mode", details, "WebAdmin"))


@app.route("/admin/demo")
@admin_required
def admin_demo():
    _require()
    import web_viewer
    with _conn() as conn:
        info = demo_core.status(conn)
    return render_template_string(ADMIN_DEMO_HTML, info=info, catalog=demo_core.CATALOG, sidebar_docked=True,
                                  viewer=web_viewer.status(), nightly_at=demo_core.NIGHTLY_AT)


@app.route("/admin/demo/seed", methods=["POST"])
@admin_required
def admin_demo_seed():
    _require()
    backup = demo_core.backup(DB_PATH)
    with _conn() as conn:
        try:
            counts = demo_core.seed(conn, manual=source_core.is_manual_instance())
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        _audit(conn, "DEMO_SEEDED", f"{counts} backup={backup.name}")
        conn.commit()
    return jsonify({"ok": True, **counts})


@app.route("/admin/demo/nightly", methods=["POST"])
@admin_required
def admin_demo_nightly():
    """تشغيل/إيقاف التجديد الليلي (البوت ينفّذه 03:00 — demo_core.nightly_refresh)."""
    _require()
    on = bool((request.get_json(silent=True) or {}).get("on"))
    with _conn() as conn:
        demo_core.set_cfg(conn, demo_core.CFG_NIGHTLY, "1" if on else "0")
        _audit(conn, "DEMO_NIGHTLY_ON" if on else "DEMO_NIGHTLY_OFF", "")
        conn.commit()
    return jsonify({"ok": True, "on": on})


@app.route("/admin/demo/clear", methods=["POST"])
@admin_required
def admin_demo_clear():
    _require()
    with _conn() as conn:
        n = demo_core.clear(conn)
        _audit(conn, "DEMO_CLEARED", f"{n} tenders")
        conn.commit()
    return jsonify({"ok": True, "tenders": n})
