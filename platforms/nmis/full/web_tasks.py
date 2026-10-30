# -*- coding: utf-8 -*-
"""لوحة المهام (كانبان) — واجهات اللوحة.

كل منافسة تنقسم إلى مهام؛ كل مهمة كارت له مهندس وأولوية وتاريخ بدء واستحقاق وملاحظات،
ويتنقل بين ثلاثة أعمدة: لم تبدأ (todo) ← قيد التنفيذ (doing) ← منتهية (done).
مفعّلة فقط للنسخ التي في ملف هويتها "features": ["kanban"] (منصة النور أولاً).

المرحلة 1 (2026-09-24): اللوحة والواجهات. المرحلة 2: قالب مهام تلقائي لكل منافسة + مزامنة
مع مراحل المنافسة + إشعار تليجرام خاص للمهندس عند الإسناد (المنطق في tasks_core.py).
المرحلة 3: تقييم الإدارة للمهام المنتهية + صفحة /team (بطاقات أداء المهندسين) — للإدارة فقط.
كل تعديل يُسجَّل في task_activity ويُبث لكل الشاشات المفتوحة عبر /api/stream (tasks_changed).
"""
import functools
import re
import sqlite3
import threading
from contextlib import closing
from datetime import date, datetime

from flask import Response, abort, jsonify, redirect, render_template_string, request, session

import engineer_accounts
import source_core
import tasks_core
from company_profile import feature_enabled
from dashboard_templates import TASKS_HTML, TEAM_HTML
from web_core import DB_PATH, _send_telegram_dm, admin_required, app, push_sse_event, session_engineer

FEATURE = tasks_core.FEATURE
STATUSES = tasks_core.STATUSES
PRIORITIES = ("high", "medium", "normal")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_tables_ready = False


def _conn():
    return closing(tasks_core.connect(DB_PATH))


def _require_feature():
    """404 للنسخة التي لم تُفعَّل لها اللوحة؛ وتُنشأ الجداول مرة واحدة لكل عملية."""
    global _tables_ready
    if not feature_enabled(FEATURE):
        abort(404)
    if not _tables_ready:
        with _conn() as conn:
            tasks_core.ensure_tables(conn)
            conn.commit()
        _tables_ready = True


def _engineer_only() -> str:
    """اسم المهندس إن كانت الجلسة لحساب مهندس فقط (بلا دخول الفريق/الإدارة)، وإلا ''."""
    if session.get("ok") or session.get("admin_ok"):
        return ""
    return session_engineer()


def board_required(f):
    """اللوحة: دخول الفريق أو الإدارة، أو حساب مهندس شخصي (صلاحيات محدودة بمهامه)."""
    @functools.wraps(f)
    def wrap(*a, **kw):
        if session.get("ok") or session.get("admin_ok") or _engineer_only():
            return f(*a, **kw)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "msg": "انتهت الجلسة — أعد تسجيل الدخول"}), 401
        return redirect("/login")
    return wrap


def _actor() -> str:
    if session.get("admin_ok"):
        return "الإدارة"
    me = session_engineer()
    return f"م. {me}" if me else "الفريق"


def _not_my_task(task) -> bool:
    """جلسة مهندس بحسابه الشخصي ومهمة ليست مسندة إليه (يعدّل مهامه فقط)."""
    me = _engineer_only()
    return bool(me) and (task["engineer"] or "") != me


def _log(conn, task_id: int, action: str, details: str = ""):
    tasks_core.log(conn, task_id, action, details, _actor())


def _fetch_task(conn, task_id: int):
    return conn.execute("""
        SELECT t.*, m.title AS tender_title, m.owner AS tender_owner, m.submission_date AS tender_deadline
        FROM tender_tasks t LEFT JOIN master_tenders m ON m.id = t.tender_row_id
        WHERE t.id = ?""", (task_id,)).fetchone()


def _notify(conn, notices):
    """إشعارات تليجرام خاصة لمشتركي كل مهندس — في الخلفية حتى لا تنتظر الواجهة."""
    jobs = [(cid, text) for eng, text in notices for cid in tasks_core.subscriber_chats(conn, eng)]
    if jobs:
        threading.Thread(target=lambda: [_send_telegram_dm(str(c), t) for c, t in jobs], daemon=True).start()


def _assign_notice(task) -> tuple:
    due = tasks_core.due_text(task["due_date"])
    return (task["engineer"], f"🗂️ مهمة جديدة لك يا م. {task['engineer']}\n• {task['title']}\n"
                              f"📄 {task['tender_title'] or ''}" + (f"\n{due}" if due else "") +
            "\nاعرض مهامك بالأمر /mytasks")


def refresh_tasks() -> bool:
    """تجهيز قوالب المنافسات الجديدة + مزامنة المراحل. True إن تغيّر شيء."""
    with _conn() as conn:
        changed, notices = tasks_core.refresh_and_commit(conn)
        _notify(conn, notices)
    if changed:
        push_sse_event("tasks_changed", {})
    return changed


def on_stage_change():
    """يُستدعى بعد حفظ علامات المنافسة أو الضمان (web_api) — لا يفشل الحفظ الأصلي أبداً."""
    if not feature_enabled(FEATURE):
        return
    try:
        refresh_tasks()
    except sqlite3.Error:
        pass


def _clean_fields(data: dict, conn, partial: bool, old=None) -> dict:
    """يتحقق من الحقول ويرجع ما يُكتب؛ يرفع ValueError برسالة عربية عند الخطأ.
    old = الصف الحالي عند التعديل (ليُقارن البدء/الاستحقاق بعد الدمج)."""
    out = {}
    if "title" in data or not partial:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("اسم المهمة مطلوب")
        out["title"] = title[:200]
    if "tender_row_id" in data or not partial:
        try:
            tid = int(data.get("tender_row_id"))
        except (TypeError, ValueError):
            raise ValueError("اختر المنافسة")
        if not conn.execute("SELECT 1 FROM master_tenders WHERE id=?", (tid,)).fetchone():
            raise ValueError("المنافسة غير موجودة")
        out["tender_row_id"] = tid
    if "engineer" in data:
        eng = str(data.get("engineer") or "").strip()
        if eng and not conn.execute("SELECT 1 FROM engineers WHERE name=?", (eng,)).fetchone():
            raise ValueError("المهندس غير موجود")
        out["engineer"] = eng
    if "priority" in data:
        pr = str(data.get("priority") or "normal")
        if pr not in PRIORITIES:
            raise ValueError("أولوية غير صحيحة")
        out["priority"] = pr
    if "status" in data:
        st = str(data.get("status") or "todo")
        if st not in STATUSES:
            raise ValueError("حالة غير صحيحة")
        out["status"] = st
    for key in ("start_date", "due_date"):
        if key in data:
            v = str(data.get(key) or "").strip()
            if v and not _DATE_RE.match(v):
                raise ValueError("صيغة التاريخ يجب أن تكون YYYY-MM-DD")
            out[key] = v
    start = out.get("start_date", old["start_date"] if old else "")
    due = out.get("due_date", old["due_date"] if old else "")
    if start and due and due < start:
        raise ValueError("تاريخ الاستحقاق قبل تاريخ البدء")
    if "notes" in data:
        out["notes"] = str(data.get("notes") or "")[:4000]
    return out


def _changed(task_id: int):
    push_sse_event("tasks_changed", {"id": task_id})


# ── Navigation context (sidebar badge) ──────────────────────────────────
@app.context_processor
def _kanban_nav():
    on = feature_enabled(FEATURE)
    overdue = 0
    if on:
        try:
            with _conn() as conn:
                overdue = conn.execute(
                    "SELECT COUNT(*) FROM tender_tasks WHERE status<>'done' AND due_date<>'' AND due_date < ?",
                    (date.today().isoformat(),)).fetchone()[0]
        except sqlite3.Error:
            overdue = 0
    return {"kanban_on": on, "nav_overdue_tasks": overdue, "accounts_on": feature_enabled(engineer_accounts.FEATURE),
            "analytics_on": feature_enabled("analytics"), "source_on": source_core.is_manual_instance(),
            "demo_on": feature_enabled("demo"), "calendar_on": feature_enabled("calendar"),
            "eng_mode": bool(_engineer_only())}


# ── Page ────────────────────────────────────────────────────────────────
@app.route("/tasks")
@board_required
def tasks_page():
    _require_feature()
    refresh_tasks()          # فتح اللوحة يلتقط ما تغيّر خارجها (منافسات جديدة، أزرار تليجرام) بلا انتظار دورة البوت
    placeholders = ",".join("?" * len(tasks_core.ACTIVE_EXCLUDED))
    with _conn() as conn:
        engineers = [r["name"] for r in conn.execute(
            "SELECT name FROM engineers WHERE is_active=1 ORDER BY name")]
        common = list(dict.fromkeys([t[1] for t in tasks_core.template_for(conn, "")] + tasks_core.COMMON_TASKS))
        tenders = [dict(r) for r in conn.execute(
            "SELECT id, title, owner, submission_date FROM master_tenders "
            f"WHERE status NOT IN ({placeholders}) ORDER BY id", tasks_core.ACTIVE_EXCLUDED)]
    me = _engineer_only()
    return render_template_string(TASKS_HTML, engineers=engineers, tenders=tenders,
                                  common_tasks=common, status_labels=tasks_core.STATUS_LABEL,
                                  today=date.today().isoformat(), sidebar_docked=True,
                                  is_admin=bool(session.get("admin_ok")), me=me,
                                  pick_engineer=request.args.get("engineer", "") or me)


# ── API ─────────────────────────────────────────────────────────────────
@app.route("/api/tasks")
@board_required
def api_tasks_list():
    _require_feature()
    # التقييمات للإدارة فقط — الفريق يرى اللوحة بدونها
    rating_cols = (", r.quality AS rating_quality, r.commitment AS rating_commitment, r.note AS rating_note, "
                   "r.rated_at AS rating_at" if session.get("admin_ok") else "")
    sql = ("SELECT t.*, m.title AS tender_title, m.owner AS tender_owner, m.submission_date AS tender_deadline"
           f"{rating_cols} FROM tender_tasks t LEFT JOIN master_tenders m ON m.id = t.tender_row_id "
           "LEFT JOIN task_ratings r ON r.task_id = t.id WHERE 1=1")
    args = []
    if request.args.get("engineer"):
        sql += " AND t.engineer = ?"; args.append(request.args["engineer"])
    if request.args.get("tender"):
        sql += " AND t.tender_row_id = ?"; args.append(request.args["tender"])
    sql += " ORDER BY t.status, t.position, t.id"
    with _conn() as conn:
        return jsonify({"ok": True, "today": date.today().isoformat(),
                        "tasks": [dict(r) for r in conn.execute(sql, args)]})


@app.route("/api/tasks", methods=["POST"])
@board_required
def api_tasks_create():
    _require_feature()
    data = request.get_json(silent=True) or {}
    with _conn() as conn:
        me = _engineer_only()
        if me:
            data["engineer"] = me                        # المهندس ينشئ مهاماً لنفسه فقط
        try:
            f = _clean_fields(data, conn, partial=False)
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        f.setdefault("status", "todo")
        cols = list(f) + ["created_by"]
        cur = conn.execute(f"INSERT INTO tender_tasks ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                           [f[c] for c in f] + [_actor()])
        task_id = cur.lastrowid
        tasks_core.place(conn, task_id, f["status"])
        _log(conn, task_id, "create", f"أُنشئت المهمة: {f['title']}")
        if f.get("engineer"):
            _log(conn, task_id, "assign", f"أُسندت إلى م. {f['engineer']}")
        conn.commit()
        task = _fetch_task(conn, task_id)
        if task["engineer"] and task["status"] != "done":
            _notify(conn, [_assign_notice(task)])
        task = dict(task)
    _changed(task_id)
    return jsonify({"ok": True, "task": task})


@app.route("/api/tasks/<int:task_id>", methods=["POST"])
@board_required
def api_tasks_update(task_id):
    _require_feature()
    data = request.get_json(silent=True) or {}
    data.pop("status", None)          # تغيير العمود عبر /move فقط (يضبط الترتيب وتاريخ الإنجاز)
    with _conn() as conn:
        old = _fetch_task(conn, task_id)
        if not old:
            return jsonify({"ok": False, "msg": "المهمة غير موجودة"}), 404
        if _not_my_task(old):
            return jsonify({"ok": False, "msg": "تعدّل مهامك فقط"}), 403
        if _engineer_only():
            data.pop("engineer", None)                  # الإسناد للإدارة/الفريق
        try:
            f = _clean_fields(data, conn, partial=True, old=old)
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        reassigned = "engineer" in f and f["engineer"] != (old["engineer"] or "")
        if f:
            conn.execute(f"UPDATE tender_tasks SET {', '.join(k + '=?' for k in f)}, "
                         "updated_at=datetime('now','localtime') WHERE id=?", list(f.values()) + [task_id])
            if reassigned:
                _log(conn, task_id, "assign", f"أُسندت إلى م. {f['engineer']}" if f["engineer"] else "أُلغي الإسناد")
            if "due_date" in f and f["due_date"] != (old["due_date"] or ""):
                _log(conn, task_id, "due", f"تاريخ الاستحقاق: {f['due_date'] or '—'}")
            other = [k for k in f if k not in ("engineer", "due_date")
                     and str(f[k]) != str(old[k] if old[k] is not None else "")]
            if other:
                _log(conn, task_id, "edit", "عُدّلت: " + "، ".join(
                    {"title": "الاسم", "tender_row_id": "المنافسة", "priority": "الأولوية",
                     "start_date": "تاريخ البدء", "notes": "الملاحظات"}.get(k, k) for k in other))
            conn.commit()
        task = _fetch_task(conn, task_id)
        if reassigned and task["engineer"] and task["status"] != "done":
            _notify(conn, [_assign_notice(task)])
        task = dict(task)
    _changed(task_id)
    return jsonify({"ok": True, "task": task})


@app.route("/api/tasks/<int:task_id>/move", methods=["POST"])
@board_required
def api_tasks_move(task_id):
    _require_feature()
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "")
    if status not in STATUSES:
        return jsonify({"ok": False, "msg": "حالة غير صحيحة"}), 400
    with _conn() as conn:
        old = _fetch_task(conn, task_id)
        if old and _not_my_task(old):
            return jsonify({"ok": False, "msg": "تحرّك مهامك فقط"}), 403
        if not tasks_core.move(conn, task_id, status, _actor(), data.get("position")):
            return jsonify({"ok": False, "msg": "المهمة غير موجودة"}), 404
        conn.commit()
        task = dict(_fetch_task(conn, task_id))
    _changed(task_id)
    return jsonify({"ok": True, "task": task})


@app.route("/api/tasks/<int:task_id>/delete", methods=["POST"])
@board_required
def api_tasks_delete(task_id):
    _require_feature()
    if _engineer_only():
        return jsonify({"ok": False, "msg": "الحذف للإدارة أو الفريق"}), 403
    with _conn() as conn:
        if not conn.execute("SELECT 1 FROM tender_tasks WHERE id=?", (task_id,)).fetchone():
            return jsonify({"ok": False, "msg": "المهمة غير موجودة"}), 404
        conn.execute("DELETE FROM tender_tasks WHERE id=?", (task_id,))
        conn.execute("DELETE FROM task_activity WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM task_ratings WHERE task_id=?", (task_id,))
        conn.commit()
    _changed(task_id)
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>/activity")
@board_required
def api_tasks_activity(task_id):
    _require_feature()
    # التقييم للإدارة فقط — سطر «التقييم: الجودة …» لا يظهر للفريق ولا للمهندسين
    hide_ratings = "" if session.get("admin_ok") else " AND action <> 'rate'"
    with _conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT action, details, actor, at FROM task_activity WHERE task_id=?"
            f"{hide_ratings} ORDER BY id DESC LIMIT 50", (task_id,))]
    return jsonify({"ok": True, "activity": rows})


# ── المرحلة 3: تقييم الإدارة + بطاقات أداء المهندسين (للإدارة فقط) ─────────
@app.route("/api/tasks/<int:task_id>/rating", methods=["POST"])
@board_required
def api_tasks_rate(task_id):
    _require_feature()
    if not session.get("admin_ok"):
        return jsonify({"ok": False, "msg": "التقييم للإدارة فقط — سجّل دخول الإدارة"}), 403
    data = request.get_json(silent=True) or {}
    with _conn() as conn:
        try:
            tasks_core.rate(conn, task_id, data.get("quality"), data.get("commitment"), data.get("note"), _actor())
        except LookupError as e:
            return jsonify({"ok": False, "msg": str(e)}), 404
        except ValueError as e:
            return jsonify({"ok": False, "msg": str(e)}), 400
        conn.commit()
    _changed(task_id)
    return jsonify({"ok": True})


@app.route("/team")
@admin_required
def team_page():
    _require_feature()
    import performance_report
    month = performance_report.previous_month(date.today())
    months = []
    for _ in range(12):                                  # الشهر المنتهي أولاً ثم ما قبله
        months.append((f"{month:%Y-%m}", f"{performance_report.MONTHS[month.month - 1]} {month.year}"))
        month = performance_report.previous_month(month)
    this = date.today().replace(day=1)
    months.insert(1, (f"{this:%Y-%m}", f"{performance_report.MONTHS[this.month - 1]} {this.year} (حتى اليوم)"))
    return render_template_string(TEAM_HTML, sidebar_docked=True, periods=tasks_core.PERIODS, report_months=months)


@app.route("/team/report.pdf")
@admin_required
def team_report_pdf():
    """تقرير الأداء الشهري PDF — نفس ما يُرسل لتليجرام الإدارة أول كل شهر."""
    _require_feature()
    import performance_report
    try:
        month = datetime.strptime(request.args.get("month", ""), "%Y-%m").date()
    except ValueError:
        month = performance_report.previous_month(date.today())
    if month > date.today():
        abort(404)
    with _conn() as conn:
        pdf, name, _ = performance_report.generate(conn, month)
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f"attachment; filename={name}"})


@app.route("/api/team")
@admin_required
def api_team():
    _require_feature()
    period = request.args.get("period", "month")
    if period not in tasks_core.PERIODS:
        period = "month"
    with _conn() as conn:
        return jsonify({"ok": True, **tasks_core.scorecards(conn, period)})


# ── جرس الإشعارات (2026-09-25) ─────────────────────────────────────────────
def _viewer() -> str:
    if session.get("admin_ok"):
        return "admin"
    me = _engineer_only()
    return f"eng:{me}" if me else "team"


@app.route("/api/notifications")
@board_required
def api_notifications():
    _require_feature()
    with _conn() as conn:
        data = tasks_core.notifications(conn, _viewer())
        conn.commit()
    return jsonify({"ok": True, **data})


@app.route("/api/notifications/read", methods=["POST"])
@board_required
def api_notifications_read():
    _require_feature()
    with _conn() as conn:
        tasks_core.mark_notifications_read(conn, _viewer())
        conn.commit()
    return jsonify({"ok": True})
