# -*- coding: utf-8 -*-
"""Login/logout/forgot for the dashboard and the admin panel + password changes.

DASH_PWD/ADMIN_PWD live here with every function that reads or rebinds them (`global`),
so a password change takes effect immediately.

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
import hmac
import os
import secrets
from admin_templates import ADMIN_FORGOT_HTML, ADMIN_LOGIN_HTML
from dashboard_templates import DASH_FORGOT_HTML, LOGIN_HTML
from flask import jsonify, redirect, render_template_string, request, session
def decrypt_val(value):  # N5: secrets come from environment variables only; no local vault
    if value is not None and str(value).startswith("FERNET:"):
        raise RuntimeError("encrypted secret values are not supported; set the plain value in the environment")
    return value
from web_core import ADMIN_EMAIL, ENV_PATH, OWNER_TELEGRAM_ID, _LOCKOUT_MSG, _LOGO_DATA_URI, _check_reset_code, _client_ip, _login_blocked, _login_failed, _login_succeeded, _new_reset_code, _send_telegram_dm, admin_required, app, end_engineer_session, end_viewer_session
DASH_PWD = decrypt_val(os.environ["DASHBOARD_PASSWORD"])  # FERNET: or plain -- decrypt_val handles both
ADMIN_PWD   = decrypt_val(os.environ["ADMIN_PASSWORD"])  # FERNET: or plain -- decrypt_val handles both

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        ip = _client_ip()
        if _login_blocked(ip):
            error = _LOCKOUT_MSG
        elif hmac.compare_digest(request.form.get("password", "").encode("utf-8"), DASH_PWD.encode("utf-8")):
            _login_succeeded(ip)
            end_viewer_session()
            end_engineer_session()
            session["ok"] = True
            return redirect("/")
        else:
            _login_failed(ip)
            error = "كلمة المرور غير صحيحة"
    return render_template_string(LOGIN_HTML, error=error, logo_uri=_LOGO_DATA_URI,
                                  expired=request.args.get("expired"),
                                  reset_ok=request.args.get("reset") == "1")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/forgot", methods=["GET", "POST"])
def dash_forgot():
    """استعادة كلمة مرور صفحة الدخول الرئيسية -- نفس آلية /admin/forgot بالضبط،
    تُحدّث DASHBOARD_PASSWORD بدلاً من ADMIN_PASSWORD."""
    global DASH_PWD
    error = ""
    sent  = False
    token = request.form.get("token", "")
    if request.method == "POST":
        ip = _client_ip()
        action = request.form.get("action", "")
        if action == "send":
            if _login_blocked(ip):
                error = _LOCKOUT_MSG
            elif not OWNER_TELEGRAM_ID:
                error = "لم يتم ضبط OWNER_TELEGRAM_ID في .env — لا يمكن إرسال كود عبر تليجرام حتى تضبطه"
            else:
                token = secrets.token_urlsafe(16)
                code = _new_reset_code(token)
                ok = _send_telegram_dm(
                    OWNER_TELEGRAM_ID,
                    f"🔐 كود استعادة كلمة مرور الدخول: {code}\nصالح لمدة 10 دقائق. تجاهل الرسالة إن لم تطلبها.",
                )
                if ok:
                    sent = True
                else:
                    error = "تعذر إرسال الكود عبر تليجرام — تأكد من صلاحية التوكن"
        elif action == "verify":
            sent = True
            code     = request.form.get("code", "").strip()
            new_pwd  = request.form.get("new_pwd", "").strip()
            new_pwd2 = request.form.get("new_pwd2", "").strip()
            if _login_blocked(ip):
                error = _LOCKOUT_MSG
            elif not _check_reset_code(token, code):
                _login_failed(ip)
                error = "الكود غير صحيح أو منتهي الصلاحية"
            elif not new_pwd or len(new_pwd) < 8:
                error = "كلمة المرور الجديدة قصيرة (8 أحرف على الأقل)"
            elif new_pwd != new_pwd2:
                error = "كلمتا المرور غير متطابقتين"
            else:
                env_path = ENV_PATH
                try:
                    with open(env_path, "r", encoding="utf-8") as ef:
                        lines_ = ef.readlines()
                    updated = False
                    for i, line in enumerate(lines_):
                        if line.startswith("DASHBOARD_PASSWORD="):
                            lines_[i] = f"DASHBOARD_PASSWORD={new_pwd}\n"
                            updated = True
                            break
                    if not updated:
                        lines_.append(f"DASHBOARD_PASSWORD={new_pwd}\n")
                    with open(env_path, "w", encoding="utf-8") as ef:
                        ef.writelines(lines_)
                    DASH_PWD = new_pwd
                    _login_succeeded(ip)
                    return redirect("/login?reset=1")
                except Exception as ex:
                    error = f"خطأ: {ex}"
    return render_template_string(DASH_FORGOT_HTML, error=error, sent=sent,
                                   token=token, logo_uri=_LOGO_DATA_URI)

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        ip = _client_ip()
        email = request.form.get("email", "").strip().lower()
        apwd  = request.form.get("apwd", "").strip()
        if _login_blocked(ip):
            error = _LOCKOUT_MSG
        elif email == ADMIN_EMAIL.lower() and hmac.compare_digest(apwd.encode("utf-8"), ADMIN_PWD.encode("utf-8")):
            _login_succeeded(ip)
            end_viewer_session()
            end_engineer_session()
            session["admin_ok"] = True
            return redirect("/admin")
        else:
            _login_failed(ip)
            error = "البريد الإلكتروني أو كلمة المرور غير صحيحة"
    return render_template_string(ADMIN_LOGIN_HTML, error=error,
                                   reset_ok=request.args.get("reset") == "1",
                                   logo_uri=_LOGO_DATA_URI)

@app.route("/admin/forgot", methods=["GET", "POST"])
def admin_forgot():
    global ADMIN_PWD
    error = ""
    sent  = False
    token = request.form.get("token", "")
    if request.method == "POST":
        ip = _client_ip()
        action = request.form.get("action", "")
        if action == "send":
            if _login_blocked(ip):
                error = _LOCKOUT_MSG
            elif not OWNER_TELEGRAM_ID:
                error = "لم يتم ضبط OWNER_TELEGRAM_ID في .env — لا يمكن إرسال كود عبر تليجرام حتى تضبطه"
            else:
                token = secrets.token_urlsafe(16)
                code = _new_reset_code(token)
                ok = _send_telegram_dm(
                    OWNER_TELEGRAM_ID,
                    f"🔐 كود استعادة كلمة مرور المشرف: {code}\n"
                    f"البريد المسجّل: {ADMIN_EMAIL}\n"
                    "صالح لمدة 10 دقائق. تجاهل الرسالة إن لم تطلبها.",
                )
                if ok:
                    sent = True
                else:
                    error = "تعذر إرسال الكود عبر تليجرام — تأكد من صلاحية التوكن"
        elif action == "verify":
            sent = True
            code     = request.form.get("code", "").strip()
            new_pwd  = request.form.get("new_apwd", "").strip()
            new_pwd2 = request.form.get("new_apwd2", "").strip()
            if _login_blocked(ip):
                error = _LOCKOUT_MSG
            elif not _check_reset_code(token, code):
                _login_failed(ip)
                error = "الكود غير صحيح أو منتهي الصلاحية"
            elif not new_pwd or len(new_pwd) < 8:
                error = "كلمة المرور الجديدة قصيرة (8 أحرف على الأقل)"
            elif new_pwd != new_pwd2:
                error = "كلمتا المرور غير متطابقتين"
            else:
                env_path = ENV_PATH
                try:
                    with open(env_path, 'r', encoding='utf-8') as ef:
                        lines = ef.readlines()
                    updated = False
                    for i, line in enumerate(lines):
                        if line.startswith('ADMIN_PASSWORD='):
                            lines[i] = f'ADMIN_PASSWORD={new_pwd}\n'
                            updated = True
                            break
                    if not updated:
                        lines.append(f'ADMIN_PASSWORD={new_pwd}\n')
                    with open(env_path, 'w', encoding='utf-8') as ef:
                        ef.writelines(lines)
                    ADMIN_PWD = new_pwd
                    _login_succeeded(ip)
                    return redirect("/admin/login?reset=1")
                except Exception as ex:
                    error = f"خطأ: {ex}"
    return render_template_string(ADMIN_FORGOT_HTML, error=error, sent=sent,
                                   token=token, logo_uri=_LOGO_DATA_URI)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_ok", None)
    return redirect("/login")

@app.route("/admin/change-password", methods=["POST"])
@admin_required
def admin_change_password():
    global DASH_PWD
    new_pwd  = request.form.get("new_pwd", "").strip()
    new_pwd2 = request.form.get("new_pwd2", "").strip()
    if not new_pwd or len(new_pwd) < 6:
        return jsonify({"ok": False, "msg": "كلمة المرور قصيرة (6 أحرف على الأقل)"})
    if new_pwd != new_pwd2:
        return jsonify({"ok": False, "msg": "كلمتا المرور غير متطابقتين"})
    env_path = ENV_PATH
    try:
        with open(env_path, 'r', encoding='utf-8') as ef:
            lines = ef.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('DASHBOARD_PASSWORD='):
                lines[i] = f'DASHBOARD_PASSWORD={new_pwd}\n'
                updated = True
                break
        if not updated:
            lines.append(f'DASHBOARD_PASSWORD={new_pwd}\n')
        with open(env_path, 'w', encoding='utf-8') as ef:
            ef.writelines(lines)
        DASH_PWD = new_pwd
        return jsonify({"ok": True, "msg": "تم تغيير كلمة المرور ✅ (فعّالة فوراً)"})
    except Exception as ex:
        return jsonify({"ok": False, "msg": f"خطأ: {ex}"})

@app.route("/admin/change-admin-password", methods=["POST"])
@admin_required
def admin_change_admin_password():
    global ADMIN_PWD
    cur_pwd  = request.form.get("cur_apwd", "").strip()
    new_pwd  = request.form.get("new_apwd", "").strip()
    new_pwd2 = request.form.get("new_apwd2", "").strip()
    if cur_pwd != ADMIN_PWD:
        return jsonify({"ok": False, "msg": "كلمة المرور الحالية غير صحيحة"})
    if not new_pwd or len(new_pwd) < 8:
        return jsonify({"ok": False, "msg": "كلمة المرور الجديدة قصيرة (8 أحرف على الأقل)"})
    if new_pwd != new_pwd2:
        return jsonify({"ok": False, "msg": "كلمتا المرور غير متطابقتين"})
    env_path = ENV_PATH
    try:
        with open(env_path, 'r', encoding='utf-8') as ef:
            lines = ef.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('ADMIN_PASSWORD='):
                lines[i] = f'ADMIN_PASSWORD={new_pwd}\n'
                updated = True
                break
        if not updated:
            lines.append(f'ADMIN_PASSWORD={new_pwd}\n')
        with open(env_path, 'w', encoding='utf-8') as ef:
            ef.writelines(lines)
        ADMIN_PWD = new_pwd
        return jsonify({"ok": True, "msg": "تم تغيير كلمة مرور المشرف ✅"})
    except Exception as ex:
        return jsonify({"ok": False, "msg": f"خطأ: {ex}"})

