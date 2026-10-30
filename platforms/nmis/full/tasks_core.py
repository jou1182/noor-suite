# -*- coding: utf-8 -*-
"""منطق لوحة المهام المشترك بين اللوحة (web_tasks.py) والبوت (bot_tasks.py) — بلا Flask ولا telebot.

المرحلة 2 (2026-09-24):
- قالب مهام تلقائي: كل منافسة نشطة تحصل على مهام القالب مرة واحدة فقط (task_seeded)،
  مسندة لمهندس المنافسة، باستحقاق محسوب عكسياً من موعد الإغلاق. حذف مهمة لا يعيدها.
- مزامنة المراحل: علامات المنافسة (tender_notes / tender_guarantees) تدفع مهام القالب
  المقابلة للأمام فقط — لا تُرجع مهمة حرّكها إنسان للخلف أبداً.
كل الدوال تأخذ اتصال sqlite (row_factory=sqlite3.Row) ولا تعمل commit — المستدعي يقرر.
"""
import sqlite3
from datetime import date, datetime, timedelta

FEATURE = "kanban"                    # مفتاح الميزة في "features" لهوية الشركة
STATUSES = ("todo", "doing", "done")
STATUS_LABEL = {"todo": "لم تبدأ", "doing": "قيد التنفيذ", "done": "منتهية"}
_RANK = {s: i for i, s in enumerate(STATUSES)}
ACTIVE_EXCLUDED = ("CLOSED", "DELETED", "REJECTED")
SYSTEM_ACTOR = "النظام"

# (المفتاح، اسم المهمة، أيام قبل موعد الإغلاق، الأولوية)
TEMPLATE = [
    ("study",     "دراسة كراسة الشروط والمواصفات", 12, "high"),
    ("site",      "زيارة الموقع وتقرير المعاينة",   10, "normal"),
    ("technical", "العرض الفني والمنهجية",           5, "medium"),
    ("pricing",   "التسعير وجدول الكميات",           4, "high"),
    ("guarantee", "الضمان الابتدائي",                3, "medium"),
    ("review",    "المراجعة الفنية الداخلية",        2, "medium"),
    ("upload",    "الرفع على المنصة",                1, "high"),
]
COMMON_TASKS = [t[1] for t in TEMPLATE]
PRIORITIES = ("high", "medium", "normal")
# مهام تحركها مراحل المنافسة (sync_stages) — حذفها من القالب يوقف تحريكها التلقائي
STAGE_KEYS = {"guarantee": "تتحرك مع حالة الضمان", "review": "تتحرك مع «أُرسلت للمراجعة»",
              "upload": "تتحرك مع «سُلّمت للرفع / رُفعت»"}
MAX_TEMPLATE_ROWS = 20
MAX_DAYS_BEFORE = 120


def ensure_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tender_tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_row_id INTEGER NOT NULL,
            title         TEXT    NOT NULL,
            engineer      TEXT    DEFAULT '',
            status        TEXT    NOT NULL DEFAULT 'todo',
            priority      TEXT    NOT NULL DEFAULT 'normal',
            start_date    TEXT    DEFAULT '',
            due_date      TEXT    DEFAULT '',
            done_at       TEXT    DEFAULT '',
            notes         TEXT    DEFAULT '',
            position      INTEGER NOT NULL DEFAULT 0,
            created_by    TEXT    DEFAULT '',
            created_at    TEXT    DEFAULT (datetime('now','localtime')),
            updated_at    TEXT    DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tender_tasks(status, position);
        CREATE INDEX IF NOT EXISTS idx_tasks_tender ON tender_tasks(tender_row_id);
        CREATE TABLE IF NOT EXISTS task_activity (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id   INTEGER NOT NULL,
            action    TEXT    NOT NULL,
            details   TEXT    DEFAULT '',
            actor     TEXT    DEFAULT '',
            at        TEXT    DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_task_activity ON task_activity(task_id, id);
        CREATE TABLE IF NOT EXISTS task_seeded (
            tender_row_id INTEGER PRIMARY KEY,
            seeded_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS task_ratings (
            task_id    INTEGER PRIMARY KEY,
            quality    INTEGER NOT NULL,
            commitment INTEGER NOT NULL,
            note       TEXT    DEFAULT '',
            rated_by   TEXT    DEFAULT '',
            rated_at   TEXT    DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.execute("""CREATE TABLE IF NOT EXISTS task_templates (
        business_type TEXT    NOT NULL,           -- '' = القالب الافتراضي لكل الأنواع
        position      INTEGER NOT NULL,
        key           TEXT    NOT NULL,
        title         TEXT    NOT NULL,
        days_before   INTEGER NOT NULL,
        priority      TEXT    NOT NULL,
        PRIMARY KEY (business_type, position))""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tender_tasks)")}
    if "template_key" not in cols:          # جداول المرحلة 1 على السيرفر
        conn.execute("ALTER TABLE tender_tasks ADD COLUMN template_key TEXT DEFAULT ''")


def log(conn, task_id: int, action: str, details: str, actor: str):
    conn.execute("INSERT INTO task_activity (task_id, action, details, actor) VALUES (?,?,?,?)",
                 (task_id, action, details, actor))


def place(conn, task_id: int, status: str, position=None):
    """يضع المهمة في عمود status عند الترتيب position (أو في آخره) ويعيد ترقيم العمود."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM tender_tasks WHERE status=? AND id<>? ORDER BY position, id", (status, task_id))]
    idx = len(ids) if position is None else max(0, min(int(position), len(ids)))
    ids.insert(idx, task_id)
    for pos, tid in enumerate(ids):
        conn.execute("UPDATE tender_tasks SET position=? WHERE id=?", (pos, tid))


def move(conn, task_id: int, status: str, actor: str, position=None, reason: str = "") -> bool:
    """ينقل مهمة لعمود؛ يضبط تاريخ الإنجاز ويسجل النشاط. False إن لم توجد."""
    row = conn.execute("SELECT status, done_at FROM tender_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return False
    old = row[0]
    done_at = row[1] or ""
    if status == "done" and old != "done":
        done_at = date.today().isoformat()
    elif status != "done":
        done_at = ""
    conn.execute("UPDATE tender_tasks SET status=?, done_at=?, updated_at=datetime('now','localtime') WHERE id=?",
                 (status, done_at, task_id))
    place(conn, task_id, status, position)
    if status != old:
        log(conn, task_id, "move", f"{reason}نُقلت إلى «{STATUS_LABEL[status]}»", actor)
    return True


def parse_deadline(value):
    """موعد الإغلاق كتاريخ — النور YYYY-MM-DD، الإدخال اليدوي DD/MM/YYYY."""
    s = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _engineer_or_blank(conn, name) -> str:
    name = (name or "").strip()
    if name and conn.execute("SELECT 1 FROM engineers WHERE name=? AND is_active=1", (name,)).fetchone():
        return name
    return ""


def seed_templates(conn, today: date = None) -> list:
    """ينشئ مهام القالب لكل منافسة نشطة لم تُجهَّز بعد. يرجع [(مهندس، عنوان المنافسة، عدد المهام)]."""
    today = today or date.today()
    placeholders = ",".join("?" * len(ACTIVE_EXCLUDED))
    rows = conn.execute(f"""
        SELECT m.id, m.title, m.submission_date, m.assigned_engineer, m.business_type FROM master_tenders m
        WHERE m.status NOT IN ({placeholders})
          AND m.id NOT IN (SELECT tender_row_id FROM task_seeded)
        ORDER BY m.id""", ACTIVE_EXCLUDED).fetchall()
    created = []
    for r in rows:
        tender_id, title, deadline = r[0], r[1], parse_deadline(r[2])
        eng = _engineer_or_blank(conn, r[3])
        template = template_for(conn, r[4])
        for key, task_title, days_before, priority in template:
            due = ""
            if deadline:
                d = deadline - timedelta(days=days_before)
                due = max(d, min(today, deadline)).isoformat()   # لا استحقاق قبل اليوم إلا إن أُغلقت المنافسة
            cur = conn.execute(
                "INSERT INTO tender_tasks (tender_row_id, title, engineer, status, priority, start_date, due_date,"
                " created_by, template_key) VALUES (?,?,?,?,?,?,?,?,?)",
                (tender_id, task_title, eng, "todo", priority, today.isoformat(), due, SYSTEM_ACTOR, key))
            place(conn, cur.lastrowid, "todo")
            log(conn, cur.lastrowid, "create", "أُنشئت تلقائياً من قالب المنافسة", SYSTEM_ACTOR)
            if eng:
                log(conn, cur.lastrowid, "assign", f"أُسندت إلى م. {eng} (مهندس المنافسة)", SYSTEM_ACTOR)
        conn.execute("INSERT OR IGNORE INTO task_seeded (tender_row_id) VALUES (?)", (tender_id,))
        created.append((eng, title, len(template)))
    return created


# ── قوالب المهام القابلة للتعديل (2026-09-25) ─────────────────────────────
# قالب لكل نوع أعمال، وإلا القالب الافتراضي ('')، وإلا TEMPLATE المضمّن. التعديل يسري على المنافسات
# التي تُجهَّز بعده فقط — مهام المنافسات القائمة لا تتغير.
def _norm_type(value) -> str:
    return " ".join(str(value or "").split())[:80]


def template_for(conn, business_type) -> list:
    """[(key, title, days_before, priority)] لنوع الأعمال."""
    if _table_exists(conn, "task_templates"):
        for bt in dict.fromkeys((_norm_type(business_type), "")):
            rows = conn.execute("SELECT key, title, days_before, priority FROM task_templates "
                                "WHERE business_type=? ORDER BY position", (bt,)).fetchall()
            if rows:
                return [tuple(r) for r in rows]
    return list(TEMPLATE)


def _as_dicts(rows) -> list:
    return [{"key": k, "title": t, "days_before": d, "priority": p} for k, t, d, p in rows]


def templates_overview(conn) -> dict:
    """للصفحة: الأنواع المعروفة، القوالب المحفوظة، والافتراضي الفعلي."""
    ensure_tables(conn)
    saved = {}
    for bt, k, t, d, p in conn.execute("SELECT business_type, key, title, days_before, priority FROM task_templates "
                                       "ORDER BY business_type, position"):
        saved.setdefault(bt, []).append({"key": k, "title": t, "days_before": d, "priority": p})
    known = {_norm_type(r[0]) for r in conn.execute("SELECT DISTINCT business_type FROM master_tenders")}
    types = sorted((known | set(saved)) - {""})
    counts = {}
    for bt, n in conn.execute(
        f"SELECT business_type, COUNT(*) FROM master_tenders WHERE status NOT IN ({','.join('?' * len(ACTIVE_EXCLUDED))})"
        " GROUP BY business_type", ACTIVE_EXCLUDED):
        counts[_norm_type(bt)] = counts.get(_norm_type(bt), 0) + n
    return {"types": types, "saved": saved, "default": saved.get("") or _as_dicts(TEMPLATE),
            "builtin": _as_dicts(TEMPLATE), "stage_keys": STAGE_KEYS, "priorities": list(PRIORITIES),
            "active": {bt: counts.get(bt, 0) for bt in types}}


def save_template(conn, business_type, rows) -> list:
    """يستبدل قالب النوع كاملاً. يرفع ValueError برسالة عربية. يرجع الصفوف المحفوظة."""
    import secrets
    bt = _norm_type(business_type)
    if not isinstance(rows, list) or not rows:
        raise ValueError("القالب يحتاج مهمة واحدة على الأقل")
    if len(rows) > MAX_TEMPLATE_ROWS:
        raise ValueError(f"الحد الأقصى {MAX_TEMPLATE_ROWS} مهمة في القالب")
    clean, seen = [], set()
    for i, r in enumerate(rows, start=1):
        r = r if isinstance(r, dict) else {}
        title = " ".join(str(r.get("title") or "").split())[:120]
        if not title:
            raise ValueError(f"المهمة رقم {i} بلا اسم")
        try:
            days = int(r.get("days_before"))
        except (TypeError, ValueError):
            raise ValueError(f"«{title}»: عدد الأيام قبل الإغلاق رقم صحيح")
        if not 0 <= days <= MAX_DAYS_BEFORE:
            raise ValueError(f"«{title}»: الأيام قبل الإغلاق من 0 إلى {MAX_DAYS_BEFORE}")
        priority = r.get("priority") if r.get("priority") in PRIORITIES else "normal"
        key = str(r.get("key") or "")
        builtin = {t[0] for t in TEMPLATE}
        if key not in builtin and not (key.startswith("c-") and key[2:].isalnum() and len(key) <= 16):
            key = "c-" + secrets.token_hex(4)                 # مهمة مخصصة: مفتاح ثابت لا يربطها بمرحلة
        if key in seen:
            raise ValueError(f"«{title}» مكررة في القالب")
        seen.add(key)
        clean.append((key, title, days, priority))
    ensure_tables(conn)
    conn.execute("DELETE FROM task_templates WHERE business_type=?", (bt,))
    conn.executemany("INSERT INTO task_templates (business_type, position, key, title, days_before, priority)"
                     " VALUES (?,?,?,?,?,?)", [(bt, i, *row) for i, row in enumerate(clean)])
    return _as_dicts(clean)


def delete_template(conn, business_type) -> int:
    """يحذف قالب النوع فيعود للافتراضي (أو يعيد الافتراضي للمضمّن). يرجع عدد الصفوف المحذوفة."""
    ensure_tables(conn)
    return conn.execute("DELETE FROM task_templates WHERE business_type=?", (_norm_type(business_type),)).rowcount


def _table_exists(conn, name) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _stage_targets(conn) -> dict:
    """{(tender_row_id, template_key): (الحالة المستهدفة، السبب)} من علامات المنافسة."""
    targets = {}
    if _table_exists(conn, "tender_notes"):
        for tid, rev, upl, done in conn.execute(
                "SELECT tender_id, submitted_to_review, submitted_to_upload, uploaded_to_platform FROM tender_notes"):
            if done:
                targets[(tid, "review")] = ("done", "تلقائياً (رُفعت على المنصة): ")
                targets[(tid, "upload")] = ("done", "تلقائياً (رُفعت على المنصة): ")
            elif upl:
                targets[(tid, "review")] = ("done", "تلقائياً (سُلّمت للرفع): ")
                targets[(tid, "upload")] = ("doing", "تلقائياً (سُلّمت للرفع): ")
            elif rev:
                targets[(tid, "review")] = ("doing", "تلقائياً (أُرسلت للمراجعة): ")
    if _table_exists(conn, "tender_guarantees"):
        for tid, st in conn.execute("SELECT tender_row_id, status FROM tender_guarantees"):
            if st in ("READY", "SUBMITTED", "NOT_REQUIRED"):
                targets[(tid, "guarantee")] = ("done", "تلقائياً (الضمان جاهز): ")
            elif st == "IN_PROGRESS":
                targets[(tid, "guarantee")] = ("doing", "تلقائياً (الضمان قيد التجهيز): ")
    return targets


def sync_stages(conn) -> list:
    """يدفع مهام القالب للأمام حسب مراحل المنافسة، ويسند مهام القالب غير المسندة لمهندس المنافسة.
    يرجع [(task_id, مهندس، نص)] لما أُسند حديثاً (للإشعار)."""
    for (tid, key), (target, reason) in _stage_targets(conn).items():
        for task_id, status in conn.execute(
                "SELECT id, status FROM tender_tasks WHERE tender_row_id=? AND template_key=?", (tid, key)).fetchall():
            if _RANK[target] > _RANK.get(status, 0):
                move(conn, task_id, target, SYSTEM_ACTOR, reason=reason)
    assigned = []
    for task_id, title, tender_eng in conn.execute("""
            SELECT t.id, t.title, m.assigned_engineer FROM tender_tasks t
            JOIN master_tenders m ON m.id = t.tender_row_id
            WHERE t.template_key <> '' AND COALESCE(t.engineer,'') = '' AND t.status <> 'done'
              AND COALESCE(m.assigned_engineer,'') <> ''""").fetchall():
        eng = _engineer_or_blank(conn, tender_eng)
        if eng:
            conn.execute("UPDATE tender_tasks SET engineer=?, updated_at=datetime('now','localtime') WHERE id=?",
                         (eng, task_id))
            log(conn, task_id, "assign", f"أُسندت إلى م. {eng} (مهندس المنافسة)", SYSTEM_ACTOR)
            assigned.append((task_id, eng, title))
    return assigned


def refresh(conn, today: date = None) -> list:
    """تجهيز القوالب + مزامنة المراحل. يرجع إشعارات الإسناد [(مهندس، نص)] مجمّعة."""
    ensure_tables(conn)
    notices = []
    for eng, tender_title, n in seed_templates(conn, today):
        if eng:
            notices.append((eng, f"🗂️ أُنشئت لك {n} مهام لمنافسة جديدة يا م. {eng}\n📄 {tender_title}\n"
                                 "اعرضها بالأمر /mytasks"))
    by_eng = {}
    for _, eng, title in sync_stages(conn):
        by_eng.setdefault(eng, []).append(title)
    for eng, titles in by_eng.items():
        notices.append((eng, f"🗂️ أُسندت إليك {len(titles)} مهمة يا م. {eng}:\n" +
                        "\n".join(f"• {t}" for t in titles[:10]) + "\nاعرضها بالأمر /mytasks"))
    return notices


def refresh_and_commit(conn, today: date = None):
    """refresh() + commit. يرجع (هل تغيّر شيء، إشعارات الإسناد)."""
    before = conn.total_changes
    notices = refresh(conn, today)
    changed = conn.total_changes != before
    conn.commit()
    return changed, notices


def open_tasks_for(conn, engineer: str) -> list:
    return conn.execute("""
        SELECT t.id, t.title, t.status, t.priority, t.due_date, m.title AS tender_title
        FROM tender_tasks t LEFT JOIN master_tenders m ON m.id = t.tender_row_id
        WHERE t.engineer=? AND t.status<>'done'
        ORDER BY CASE WHEN t.due_date='' THEN 1 ELSE 0 END, t.due_date, t.id""", (engineer,)).fetchall()


def due_text(due: str, today: date = None) -> str:
    today = today or date.today()
    d = parse_deadline(due)
    if not d:
        return ""
    n = (d - today).days
    if n < 0:
        return f"🔴 متأخرة {-n} يوم"
    if n == 0:
        return "🟠 مستحقة اليوم"
    return f"📅 {d.isoformat()} (بعد {n} يوم)"


def overdue_by_engineer(conn, today: date = None) -> dict:
    """{مهندس: [(عنوان المهمة، عنوان المنافسة، الاستحقاق)]} للمهام المتأخرة أو المستحقة اليوم."""
    today = (today or date.today()).isoformat()
    out = {}
    for r in conn.execute("""
            SELECT t.engineer, t.title, m.title, t.due_date FROM tender_tasks t
            LEFT JOIN master_tenders m ON m.id = t.tender_row_id
            WHERE t.status<>'done' AND t.due_date<>'' AND t.due_date<=? AND COALESCE(t.engineer,'')<>''
              AND COALESCE(m.tender_id,'') NOT LIKE 'DEMO-%'   -- وضع العرض لا يصل تليجرام (demo_core)
            ORDER BY t.due_date""", (today,)):
        out.setdefault(r[0], []).append((r[1], r[2] or "", r[3]))
    return out


def subscriber_chats(conn, engineer: str) -> list:
    if not _table_exists(conn, "engineer_subs"):
        return []
    return [r[0] for r in conn.execute("SELECT chat_id FROM engineer_subs WHERE engineer_name=?", (engineer,))]


# ── المرحلة 3: تقييم الإدارة وبطاقات الأداء ─────────────────────────────
PERIODS = {"month": "هذا الشهر", "q": "آخر 3 أشهر", "year": "هذا العام"}


def rate(conn, task_id: int, quality, commitment, note: str, actor: str):
    """تقييم الإدارة لمهمة منتهية (1–5 للجودة والالتزام). يرفع ValueError برسالة عربية."""
    try:
        quality, commitment = int(quality), int(commitment)
    except (TypeError, ValueError):
        raise ValueError("اختر عدد النجوم للجودة والالتزام")
    if not (1 <= quality <= 5 and 1 <= commitment <= 5):
        raise ValueError("التقييم من 1 إلى 5")
    row = conn.execute("SELECT status FROM tender_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise LookupError("المهمة غير موجودة")
    if row[0] != "done":
        raise ValueError("التقييم للمهام المنتهية فقط")
    note = (note or "").strip()[:1000]
    conn.execute("""INSERT INTO task_ratings (task_id, quality, commitment, note, rated_by, rated_at)
                    VALUES (?,?,?,?,?,datetime('now','localtime'))
                    ON CONFLICT(task_id) DO UPDATE SET quality=excluded.quality, commitment=excluded.commitment,
                      note=excluded.note, rated_by=excluded.rated_by, rated_at=excluded.rated_at""",
                 (task_id, quality, commitment, note, actor))
    log(conn, task_id, "rate", f"التقييم: الجودة {quality}/5 · الالتزام {commitment}/5", actor)


def period_start(period: str, today: date = None) -> date:
    today = today or date.today()
    if period == "year":
        return today.replace(month=1, day=1)
    if period == "q":
        return today - timedelta(days=90)
    return today.replace(day=1)


def scorecards(conn, period: str = "month", today: date = None, start: date = None, end: date = None) -> dict:
    """مؤشرات كل مهندس نشط في الفترة: المنتهية، في الموعد، الجودة والالتزام، الفوز، الحمل، المتأخر الآن.
    start/end = فترة محددة (التقرير الشهري لشهر مضى)؛ الحمل والمفتوح والمتأخر لحظة الإصدار دائماً."""
    today = today or date.today()
    now = today.isoformat()
    until = (end or today).isoformat()
    start = (start or period_start(period, today)).isoformat()
    placeholders = ",".join("?" * len(ACTIVE_EXCLUDED))
    has_results = _table_exists(conn, "tender_results")
    cards = []
    for e in conn.execute("SELECT name, capacity FROM engineers WHERE is_active=1 ORDER BY name").fetchall():
        name = e[0]
        done = conn.execute("""SELECT t.due_date, t.done_at, r.quality, r.commitment FROM tender_tasks t
                               LEFT JOIN task_ratings r ON r.task_id = t.id
                               WHERE t.engineer=? AND t.status='done' AND t.done_at>=? AND t.done_at<=?""",
                            (name, start, until)).fetchall()
        with_due = [d for d in done if d[0]]
        on_time = sum(1 for d in with_due if d[1] <= d[0])
        rated = [d for d in done if d[2] is not None]
        cards.append({
            "name": name,
            "capacity": e[1] or 5,
            "load": conn.execute(f"SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer=? "
                                 f"AND status NOT IN ({placeholders})", (name, *ACTIVE_EXCLUDED)).fetchone()[0],
            "open": conn.execute("SELECT COUNT(*) FROM tender_tasks WHERE engineer=? AND status<>'done'",
                                 (name,)).fetchone()[0],
            "late": conn.execute("SELECT COUNT(*) FROM tender_tasks WHERE engineer=? AND status<>'done' "
                                 "AND due_date<>'' AND due_date<?", (name, now)).fetchone()[0],
            "done": len(done),
            "on_time_n": on_time, "with_due_n": len(with_due),
            "on_time": round(100 * on_time / len(with_due)) if with_due else None,
            "rated_n": len(rated),
            "quality": round(sum(d[2] for d in rated) / len(rated), 1) if rated else None,
            "commitment": round(sum(d[3] for d in rated) / len(rated), 1) if rated else None,
            "won": conn.execute("SELECT COUNT(*) FROM tender_results WHERE assigned_engineer=? AND result='won' "
                                "AND substr(updated_at,1,10) BETWEEN ? AND ?", (name, start, until)).fetchone()[0]
                   if has_results else 0,
        })
    rated_all = [(c["quality"], c["rated_n"]) for c in cards if c["rated_n"]]
    due_all = sum(c["with_due_n"] for c in cards)
    best = max((c["quality"] for c in cards if c["quality"] is not None), default=None)
    for c in cards:
        c["top"] = best is not None and c["quality"] == best
    return {
        "period": period, "period_label": PERIODS.get(period, ""), "from": start, "to": until,
        "totals": {
            "done": sum(c["done"] for c in cards),
            "on_time": round(100 * sum(c["on_time_n"] for c in cards) / due_all) if due_all else None,
            "quality": round(sum(q * n for q, n in rated_all) / sum(n for _, n in rated_all), 1) if rated_all else None,
            "late": sum(c["late"] for c in cards),
        },
        "engineers": cards,
    }


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


# ── جرس الإشعارات (2026-09-25): من سجل نشاط المهام، لكل «مشاهد» حالة قراءته ────────
# المشاهد: "admin" (الإدارة) / "team" (دخول الفريق) / "eng:<الاسم>" (حساب مهندس شخصي).
# الإدارة: كل تغيير من غيرها · الفريق: كل تغيير من غير «الفريق» · المهندس: التغييرات على مهامه من غيره.
# سطر التقييم (rate) للإدارة فقط — كباقي النظام.
NOTIF_ICON = {"create": "➕", "move": "↔", "assign": "👤", "edit": "📝", "due": "📅", "rate": "⭐"}


def _ensure_notif_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS notif_seen (viewer TEXT PRIMARY KEY, last_id INTEGER NOT NULL DEFAULT 0)")


def _notif_filter(viewer: str):
    """(شرط SQL إضافي، معاملاته) لمن يرى ماذا."""
    # إنشاء/إسناد مهام القالب آلياً (7 لكل منافسة) ضجيج للإدارة والفريق — يبقى للمهندس لأنه يخصه
    quiet = f" AND NOT (a.actor = '{SYSTEM_ACTOR}' AND a.action IN ('create','assign'))"
    if viewer == "admin":
        return "a.actor <> 'الإدارة'" + quiet, []
    if viewer.startswith("eng:"):
        me = viewer[4:]
        return ("t.engineer = ? AND a.actor NOT IN (?, ?) AND a.action <> 'rate'",
                [me, f"م. {me}", f"م. {me} (تليجرام)"])
    return "a.actor <> 'الفريق' AND a.action <> 'rate'" + quiet, []


def notifications(conn, viewer: str, limit: int = 20, today: date = None) -> dict:
    """{unread, items, required} لجرس المشاهد."""
    ensure_tables(conn)
    _ensure_notif_table(conn)
    row = conn.execute("SELECT last_id FROM notif_seen WHERE viewer=?", (viewer,)).fetchone()
    last = row[0] if row else 0
    cond, args = _notif_filter(viewer)
    base = (" FROM task_activity a JOIN tender_tasks t ON t.id = a.task_id "
            "LEFT JOIN master_tenders m ON m.id = t.tender_row_id WHERE " + cond)
    unread = conn.execute("SELECT COUNT(*)" + base + " AND a.id > ?", args + [last]).fetchone()[0]
    items = [{"id": r[0], "action": r[1], "icon": NOTIF_ICON.get(r[1], "•"), "text": r[2], "actor": r[3], "at": r[4],
              "task_id": r[5], "task": r[6], "tender": r[7] or "", "unread": r[0] > last}
             for r in conn.execute("SELECT a.id, a.action, a.details, a.actor, a.at, t.id, t.title, m.title" + base +
                                   " ORDER BY a.id DESC LIMIT ?", args + [limit])]
    return {"unread": unread, "items": items, "required": required_now(conn, viewer, today)}


def required_now(conn, viewer: str, today: date = None) -> list:
    """«مطلوب منك الآن»: الإدارة ← منتهية بلا تقييم + متأخرة · الفريق ← متأخرة · المهندس ← متأخرة/اليوم من مهامه."""
    today = (today or date.today()).isoformat()
    out = []
    q = ("SELECT t.id, t.title, t.engineer, t.due_date, m.title FROM tender_tasks t "
         "LEFT JOIN master_tenders m ON m.id = t.tender_row_id WHERE ")
    if viewer == "admin":
        for r in conn.execute(q + "t.status='done' AND t.id NOT IN (SELECT task_id FROM task_ratings) "
                              "ORDER BY t.done_at DESC LIMIT 5"):
            out.append({"kind": "rate", "task_id": r[0], "title": f"أنجز م. {r[2] or '—'} — بانتظار تقييمك",
                        "task": r[1], "tender": r[4] or ""})
    me = viewer[4:] if viewer.startswith("eng:") else None
    late_sql = q + "t.status<>'done' AND t.due_date<>'' AND t.due_date<=?" + (" AND t.engineer=?" if me else "")
    for r in conn.execute(late_sql + " ORDER BY t.due_date LIMIT 5", [today] + ([me] if me else [])):
        out.append({"kind": "late" if r[3] < today else "today", "task_id": r[0],
                    "title": ("متأخرة" if r[3] < today else "مستحقة اليوم") + (f" — م. {r[2]}" if r[2] and not me else ""),
                    "task": r[1], "tender": r[4] or ""})
    return out


def mark_notifications_read(conn, viewer: str):
    _ensure_notif_table(conn)
    top = conn.execute("SELECT COALESCE(MAX(id), 0) FROM task_activity").fetchone()[0]
    conn.execute("INSERT INTO notif_seen (viewer, last_id) VALUES (?, ?) "
                 "ON CONFLICT(viewer) DO UPDATE SET last_id=excluded.last_id", (viewer, top))
