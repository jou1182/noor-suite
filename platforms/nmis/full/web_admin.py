# -*- coding: utf-8 -*-
"""Admin control panel routes + knowledge base management.

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
import os
import sqlite3
from admin_templates import ADMIN_PANEL_HTML
from flask import Response, jsonify, render_template_string, request, session
from pathlib import Path
from web_core import ADMIN_EMAIL, DB_PATH, VERSION, _LOGO_DATA_URI, admin_required, app, is_viewer, save_config
@app.route("/admin")
@admin_required
def admin_panel():
    cfg = {}
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute("SELECT key,value FROM app_config").fetchall()
            cfg = {r[0]: r[1] for r in rows}
    except Exception:
        pass
    stats = {}
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            stats["tenders"]   = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE status='InProgress'"
            ).fetchone()[0]
            stats["engineers"] = conn.execute(
                "SELECT COUNT(*) FROM engineers WHERE is_active=1"
            ).fetchone()[0]
            stats["pending"]   = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE status='PENDING_APPROVAL'"
            ).fetchone()[0]
    except Exception:
        pass
    import subprocess
    try:
        r = subprocess.run(["systemctl", "is-active", BOT_SERVICE_NAME],
                           capture_output=True, text=True, timeout=3)
        stats["bot"] = r.stdout.strip()
    except Exception:
        stats["bot"] = "unknown"
    return render_template_string(ADMIN_PANEL_HTML,
                                   cfg=cfg, stats=stats,
                                   version=VERSION,
                                   logo_uri=_LOGO_DATA_URI,
                                   admin_email="••••••" if is_viewer() else ADMIN_EMAIL)

@app.route("/admin/save-identity", methods=["POST"])
@admin_required
def admin_save_identity():
    for key in ["company_name_ar", "company_name_en", "system_title",
                "system_subtitle", "footer_owner", "footer_url"]:
        val = request.form.get(key, "").strip()
        if val:
            save_config(key, val)
    return jsonify({"ok": True, "msg": "تم حفظ هوية الشركة ✅"})

@app.route("/admin/upload-logo", methods=["POST"])
@admin_required
def admin_upload_logo():
    import base64 as _b64u
    if "logo" not in request.files:
        return jsonify({"ok": False, "msg": "لم يتم رفع أي ملف"})
    f = request.files["logo"]
    if not f.filename:
        return jsonify({"ok": False, "msg": "اسم الملف فارغ"})
    data = f.read()
    if len(data) > 500_000:
        return jsonify({"ok": False, "msg": "حجم الشعار كبير (الحد 500 كيلوبايت)"})
    b64 = _b64u.b64encode(data).decode()
    save_config("custom_logo_b64", b64)
    return jsonify({"ok": True, "msg": "تم رفع الشعار ✅"})

@app.route("/admin/reset-logo", methods=["POST"])
@admin_required
def admin_reset_logo():
    save_config("custom_logo_b64", "")
    return jsonify({"ok": True, "msg": "تم استعادة الشعار الأصلي ✅"})

@app.route("/admin/db-backup")
@admin_required
def admin_db_backup():
    import shutil as _sh, tempfile
    try:
        tmp = tempfile.mktemp(suffix=".db")
        _sh.copy(str(DB_PATH), tmp)
        with open(tmp, 'rb') as f:
            data = f.read()
        os.unlink(tmp)
        from datetime import datetime as _dt
        fname = f'tenders_backup_{_dt.now().strftime("%Y%m%d_%H%M")}.db'
        return Response(data, mimetype='application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    except Exception as ex:
        return jsonify({"ok": False, "msg": str(ex)})


# ====================================================
# PHASE 2 — KNOWLEDGE BASE MANAGEMENT
# ====================================================
import os as _os, subprocess as _sp
from instance_paths import BOT_SERVICE_NAME, KNOWLEDGE_DIR, OUTPUT_DIR
_KNOW_DIR = KNOWLEDGE_DIR   # كان مسار النور حرفياً — لكل نسخة قاعدة معرفتها

def _kb_auth():
    return session.get("admin_ok") or session.get("admin_logged_in")

@app.route("/admin/knowledge")
def admin_knowledge_list():
    if not _kb_auth(): return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        files = []
        for p in sorted(_KNOW_DIR.glob("*.md")):
            st = p.stat()
            import datetime as _dt
            mod = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M")
            kb = round(st.st_size / 1024, 1)
            files.append({"name": p.name, "size": f"{kb} KB", "modified": mod})
        return jsonify({"ok": True, "files": files})
    except Exception as ex:
        return jsonify({"ok": False, "error": str(ex)})


@app.route("/admin/knowledge/read")
def admin_knowledge_read():
    if not _kb_auth(): return jsonify({"ok": False, "error": "unauthorized"}), 401
    fname = request.args.get("file", "").strip()
    if not fname or ".." in fname or "/" in fname or "\\" in fname:
        return jsonify({"ok": False, "error": "invalid filename"})
    if not fname.endswith(".md"): fname += ".md"
    fpath = _KNOW_DIR / fname
    if not fpath.exists(): return jsonify({"ok": False, "error": "file not found"})
    return jsonify({"ok": True, "content": fpath.read_text(encoding="utf-8"), "name": fname})


@app.route("/admin/knowledge/save", methods=["POST"])
def admin_knowledge_save():
    if not _kb_auth(): return jsonify({"ok": False, "msg": "unauthorized"}), 401
    fname = request.form.get("file", "").strip()
    content = request.form.get("content", "")
    if not fname or ".." in fname or "/" in fname or "\\" in fname:
        return jsonify({"ok": False, "msg": "اسم ملف غير صالح"})
    if not fname.endswith(".md"): fname += ".md"
    _KNOW_DIR.mkdir(exist_ok=True)
    fpath = _KNOW_DIR / fname
    fpath.write_text(content, encoding="utf-8")
    # Write reload flag for bot
    (OUTPUT_DIR / "reload_knowledge.flag").write_text("1")
    return jsonify({"ok": True, "msg": f"تم حفظ {fname} ✅"})


@app.route("/admin/knowledge/delete", methods=["POST"])
def admin_knowledge_delete():
    if not _kb_auth(): return jsonify({"ok": False, "msg": "unauthorized"}), 401
    fname = request.form.get("file", "").strip()
    if not fname or ".." in fname or "/" in fname:
        return jsonify({"ok": False, "msg": "اسم ملف غير صالح"})
    if not fname.endswith(".md"): fname += ".md"
    fpath = _KNOW_DIR / fname
    if not fpath.exists(): return jsonify({"ok": False, "msg": "الملف غير موجود"})
    fpath.unlink()
    (OUTPUT_DIR / "reload_knowledge.flag").write_text("1")
    return jsonify({"ok": True, "msg": f"تم حذف {fname} ✅"})


@app.route("/admin/knowledge/reload", methods=["POST"])
def admin_knowledge_reload():
    if not _kb_auth(): return jsonify({"ok": False, "msg": "unauthorized"}), 401
    # Write reload flag — bot watcher picks it up within 30s
    (OUTPUT_DIR / "reload_knowledge.flag").write_text("1")
    # Also try direct restart (may fail silently if no sudo)
    try:
        _sp.Popen(["sudo", "-n", "systemctl", "restart", BOT_SERVICE_NAME],
                  stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    except Exception:
        pass
    return jsonify({"ok": True, "msg": "تم إرسال إشارة إعادة التحميل ✅"})

