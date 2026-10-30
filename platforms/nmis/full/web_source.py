# -*- coding: utf-8 -*-
"""صفحة «مصدر المنافسات» /admin/source (2026-09-25) — للإدارة، وفقط لنسخ الإدخال اليدوي (النور).
المنطق في source_core.py. الملف المرفوع يُحفظ مؤقتاً للمعاينة ثم يُطبَّق بضغطة (بمعرّف لمرة واحدة)."""
import secrets
import sqlite3
from contextlib import closing

from flask import Response, abort, jsonify, render_template_string, request

import source_core
from dashboard_templates import ADMIN_SOURCE_HTML
from web_core import DB_PATH, admin_required, app, is_viewer


def _require():
    if not source_core.is_manual_instance():
        abort(404)


def _conn():
    return closing(sqlite3.connect(str(DB_PATH)))


def _audit(conn, action: str, details: str):
    conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                 (action, "manual_source", details, "WebAdmin"))


def _stash(data: bytes) -> str:
    source_core.PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for old in sorted(source_core.PENDING_DIR.glob("*.xlsx"))[:-10]:
        old.unlink()
    token = secrets.token_hex(12)
    (source_core.PENDING_DIR / f"{token}.xlsx").write_bytes(data)
    return token


@app.route("/admin/source")
@admin_required
def admin_source():
    _require()
    with _conn() as conn:
        info = source_core.status(conn)
    if is_viewer() and info["url"]:
        info["url"] = "https://docs.google.com/…  (مخفي في حساب العرض)"
    return render_template_string(ADMIN_SOURCE_HTML, info=info, sidebar_docked=True,
                                  columns=source_core.REQUIRED_COLUMNS)


@app.route("/admin/source/preview", methods=["POST"])
@admin_required
def admin_source_preview():
    """ملف مرفوع (multipart «file») أو سحب من الرابط المحفوظ ({"from_url": true}) ← معاينة بلا تطبيق."""
    _require()
    try:
        if "file" in request.files:
            data = request.files["file"].read(source_core.MAX_BYTES + 1)
        else:
            with _conn() as conn:
                url = source_core.get_cfg(conn, source_core.CFG_URL)
            if not url:
                return jsonify({"ok": False, "msg": "لا يوجد رابط محفوظ — احفظ رابط Google أولاً"}), 400
            data = source_core.fetch_url(url)
        with _conn() as conn:
            result = source_core.preview(conn, data)
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    except Exception:
        return jsonify({"ok": False, "msg": "تعذّر قراءة المصدر — تحقق من الملف أو الرابط"}), 400
    return jsonify({"ok": True, "token": _stash(data), **result})


@app.route("/admin/source/apply", methods=["POST"])
@admin_required
def admin_source_apply():
    _require()
    token = str((request.get_json(silent=True) or {}).get("token") or "")
    if not token.isalnum():
        return jsonify({"ok": False, "msg": "طلب غير صالح"}), 400
    pending = source_core.PENDING_DIR / f"{token}.xlsx"
    if not pending.exists():
        return jsonify({"ok": False, "msg": "انتهت المعاينة — ارفع الملف مرة أخرى"}), 404
    data = pending.read_bytes()
    try:
        source_core.apply(data)
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    pending.unlink()
    with _conn() as conn:
        import hashlib
        source_core.set_cfg(conn, source_core.CFG_HASH, hashlib.sha256(data).hexdigest()[:16])
        _audit(conn, "MANUAL_SOURCE_APPLIED", f"{len(data)} bytes")
        conn.commit()
    return jsonify({"ok": True})


@app.route("/admin/source/settings", methods=["POST"])
@admin_required
def admin_source_settings():
    _require()
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    if url:
        try:
            source_core.direct_url(url)
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
    with _conn() as conn:
        source_core.set_cfg(conn, source_core.CFG_URL, url)
        source_core.set_cfg(conn, source_core.CFG_AUTO, "1" if (url and data.get("auto")) else "0")
        _audit(conn, "MANUAL_SOURCE_SETTINGS", "url set" if url else "url cleared")
        conn.commit()
    return jsonify({"ok": True})


@app.route("/admin/source/file.xlsx")
@admin_required
def admin_source_download():
    _require()
    if not source_core.MANUAL_FILE.exists():
        abort(404)
    return Response(source_core.MANUAL_FILE.read_bytes(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=tenders.xlsx"})


@app.route("/admin/source/template.xlsx")
@admin_required
def admin_source_template():
    _require()
    return Response(source_core.template_bytes(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=tenders-template.xlsx"})
