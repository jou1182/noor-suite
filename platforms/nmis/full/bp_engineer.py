# -*- coding: utf-8 -*-
"""Engineer portal Blueprint - extracted from web_dashboard.py on 2026-07-05.
Routes: /engineer, /engineer/dashboard, /engineer/logout, /api/eng/tender/<id>/status.
Registered by web_dashboard.py via app.register_blueprint(bp_engineer)."""
from flask import Blueprint, render_template_string, request, redirect, session, jsonify, url_for
import hmac, sqlite3, os
from contextlib import closing
from pathlib import Path
from dashboard_templates import ENGINEER_LOGIN_HTML, ENGINEER_DASH_HTML, ENGINEER_PASSWORD_HTML
import engineer_accounts
import tasks_core
from company_profile import feature_enabled
from web_core import _LOCKOUT_MSG, _client_ip, _login_blocked, _login_failed, _login_succeeded, end_engineer_session

bp_engineer = Blueprint("engineer", __name__)

# same env-driven config as web_dashboard (single source: the .env file)
from instance_paths import DEFAULT_DB_PATH
DB_PATH = Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)

ENGINEER_PIN = os.getenv("ENGINEER_PIN", "1234")

@bp_engineer.route("/engineer", methods=["GET", "POST"])
def engineer_home():
    """صفحة دخول المهندس"""
    error = None
    last_name = ""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pin  = request.form.get("pin",  "").strip()
        last_name = name
        ip = _client_ip()
        if not name:
            error = "اختر اسمك من القائمة"
        elif _login_blocked(ip):
            error = _LOCKOUT_MSG
        else:
            # 2026-09-24: مهندس له حساب ← كلمة مروره فقط؛ بلا حساب ← رمز البوابة المشترك (كما كان)
            with closing(sqlite3.connect(str(DB_PATH))) as conn:
                conn.row_factory = sqlite3.Row
                account = (engineer_accounts.verify(conn, name, pin)
                           if feature_enabled(engineer_accounts.FEATURE) else None)
                conn.commit()
            ok = hmac.compare_digest(pin.encode("utf-8"), ENGINEER_PIN.encode("utf-8")) if account is None else bool(account)
            if not ok:
                _login_failed(ip)
                error = "كلمة المرور غير صحيحة"
            else:
                _login_succeeded(ip)
                # الدخول يبدّل الدور: على متصفح مشترك كانت جلسة الإدارة/الفريق تبقى فيرث المهندس صلاحياتها
                session.clear()
                session["eng_name"] = name
                session["eng_ok"]   = True
                session["eng_account"] = account is not None
                session["eng_must_change"] = bool(account and account["must_change"])
                if session["eng_must_change"]:
                    return redirect(url_for(".engineer_password"))
                return redirect(url_for(".engineer_dashboard"))
    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT DISTINCT assigned_engineer FROM master_tenders "
            "WHERE assigned_engineer IS NOT NULL AND assigned_engineer != '' "
            "ORDER BY assigned_engineer"
        ).fetchall()
    engineers = [r[0] for r in rows]
    return render_template_string(ENGINEER_LOGIN_HTML,
        engineers=engineers, error=error, last_name=last_name,
        expired=request.args.get("expired"))

@bp_engineer.route("/engineer/dashboard")
def engineer_dashboard():
    """لوحة المهندس — يرى مناقصاته فقط"""
    if not session.get("eng_ok"):
        return redirect(url_for(".engineer_home"))
    if session.get("eng_must_change"):
        return redirect(url_for(".engineer_password"))
    eng_name = session.get("eng_name", "")

    from datetime import date as _date
    today = _date.today()

    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT mt.id, mt.title, mt.submission_date, mt.owner, mt.status,
                   tr.did_submit, tr.result, tr.our_price, tr.winning_price
            FROM master_tenders mt
            LEFT JOIN tender_results tr ON tr.tender_id = mt.tender_id
            WHERE mt.assigned_engineer = ?
              AND mt.status NOT IN ('Closed','Cancelled')
            ORDER BY
              CASE WHEN mt.submission_date IS NULL OR mt.submission_date='' THEN 1 ELSE 0 END,
              mt.submission_date ASC
        """, (eng_name,)).fetchall()

    tenders = []
    urgent_count = soon_count = submitted_count = won_count = 0
    for r in rows:
        t = dict(r)
        # حساب الأيام المتبقية
        days_left = None
        urgency_class = ""
        if t["submission_date"]:
            try:
                d = tasks_core.parse_deadline(t["submission_date"])     # YYYY-MM-DD أو DD/MM/YYYY
                days_left = (d - today).days
                if days_left < 0:
                    urgency_class = "urgent"
                    urgent_count += 1
                elif days_left <= 3:
                    urgency_class = "urgent"
                    urgent_count += 1
                elif days_left <= 7:
                    urgency_class = "soon"
                    soon_count += 1
            except Exception:
                pass
        t["days_left"]     = days_left
        t["urgency_class"] = urgency_class
        if t["did_submit"] == 1:
            submitted_count += 1
        if t["result"] == "won":
            won_count += 1
        tenders.append(t)

    return render_template_string(ENGINEER_DASH_HTML,
        eng_name=eng_name, tenders=tenders, total=len(tenders),
        urgent_count=urgent_count, soon_count=soon_count,
        submitted_count=submitted_count, won_count=won_count,
        has_account=bool(session.get("eng_account")), kanban_board=feature_enabled(tasks_core.FEATURE),
        tg_links=_tg_links(eng_name) if session.get("eng_account") else 0)

@bp_engineer.route("/engineer/logout")
def engineer_logout():
    end_engineer_session()
    return redirect(url_for(".engineer_home"))


def _tg_links(name: str) -> int:
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        return engineer_accounts.telegram_links(conn, name)


def _account_ready() -> str:
    """اسم المهندس لجلسة حساب شخصي جاهزة (غيّر كلمته المؤقتة)، وإلا ''."""
    if session.get("eng_ok") and session.get("eng_account") and not session.get("eng_must_change"):
        return session.get("eng_name", "")
    return ""


@bp_engineer.route("/engineer/telegram-code", methods=["POST"])
def engineer_telegram_code():
    """رمز ربط تليجرام (6 أرقام، 10 دقائق) — الهوية مثبتة بكلمة مرور المهندس في البوابة."""
    name = _account_ready()
    if not name:
        return jsonify({"ok": False, "msg": "سجّل الدخول بحسابك الشخصي"}), 401
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row
        try:
            code = engineer_accounts.issue_link_code(conn, name)
        except LookupError as e:
            return jsonify({"ok": False, "msg": str(e)}), 403
        conn.commit()
    return jsonify({"ok": True, "code": code, "minutes": engineer_accounts.LINK_TTL_MINUTES})


@bp_engineer.route("/engineer/telegram-unlink", methods=["POST"])
def engineer_telegram_unlink():
    name = _account_ready()
    if not name:
        return jsonify({"ok": False, "msg": "سجّل الدخول بحسابك الشخصي"}), 401
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        n = engineer_accounts.unlink_telegram(conn, name)
        conn.commit()
    return jsonify({"ok": True, "removed": n})


@bp_engineer.route("/engineer/password", methods=["GET", "POST"])
def engineer_password():
    """تغيير كلمة مرور المهندس — إلزامي بعد كلمة مؤقتة من الإدارة."""
    if not (session.get("eng_ok") and session.get("eng_account")):
        return redirect(url_for(".engineer_home"))
    name = session.get("eng_name", "")
    error, done = None, False
    if request.method == "POST":
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            conn.row_factory = sqlite3.Row
            try:
                engineer_accounts.change_password(conn, name, request.form.get("current", ""),
                                                  request.form.get("new", ""), request.form.get("confirm", ""))
                conn.commit()
                session["eng_must_change"] = False
                done = True
            except ValueError as e:
                error = str(e)
    return render_template_string(ENGINEER_PASSWORD_HTML, eng_name=name, error=error, done=done,
                                  forced=bool(session.get("eng_must_change")),
                                  min_length=engineer_accounts.MIN_LENGTH)

@bp_engineer.route("/api/eng/tender/<int:tid>/status", methods=["POST"])
def api_eng_update_status(tid):
    """المهندس يُحدّث حالة منافسته (قدّمنا / لم نقدّم / فزنا / خسرنا)"""
    if not session.get("eng_ok") or session.get("eng_must_change"):
        return jsonify({"ok": False, "error": "غير مصرح"}), 401
    eng_name = session.get("eng_name", "")
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "")

    # تحقق أن هذه المنافسة تابعة لهذا المهندس
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, tender_id, assigned_engineer FROM master_tenders WHERE id=?", (tid,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "غير موجودة"}), 404
        if row["assigned_engineer"] != eng_name:
            return jsonify({"ok": False, "error": "غير مصرح — ليست منافستك"}), 403

        tid_str = row["tender_id"]
        # upsert في tender_results
        existing = conn.execute(
            "SELECT id FROM tender_results WHERE tender_id=?", (tid_str,)
        ).fetchone()

        if action == "submit":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=1, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
            else:
                t = conn.execute("SELECT title, owner FROM master_tenders WHERE id=?", (tid,)).fetchone()
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit) VALUES (?,?,?,?,1)",
                    (tid_str, t["title"], t["owner"], eng_name)
                )
        elif action == "no":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=0, result=NULL, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
            else:
                t = conn.execute("SELECT title, owner FROM master_tenders WHERE id=?", (tid,)).fetchone()
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit) VALUES (?,?,?,?,0)",
                    (tid_str, t["title"], t["owner"], eng_name)
                )
        elif action in ("won", "lost"):
            result_map = {"won": "won", "lost": "lost"}
            if existing:
                conn.execute(
                    "UPDATE tender_results SET result=?, did_submit=1, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?",
                    (result_map[action], tid_str)
                )
            else:
                t = conn.execute("SELECT title, owner FROM master_tenders WHERE id=?", (tid,)).fetchone()
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit, result) VALUES (?,?,?,?,1,?)",
                    (tid_str, t["title"], t["owner"], eng_name, result_map[action])
                )
        else:
            return jsonify({"ok": False, "error": "action غير معروف"}), 400

        conn.commit()

    return jsonify({"ok": True, "action": action})

