# -*- coding: utf-8 -*-
"""وضع العرض (2026-09-25) — بيانات وهمية مترابطة لعرض النسخة على الطلبة والمشترين (features: demo).

كل منافسة وهمية مفتاحها يبدأ بـ DEMO-، وكل ما يُنشأ معها مرتبط بصفّها، فالمسح يزيلها وحدها
ولا يلمس المنافسات الحقيقية ولا مهامها.
- المحرك يتجاهل DEMO- (غيابها عن ملف المصدر لا يجعلها «محذوفة من المنصة»).
- رسائل تليجرام المجدولة تتجاهلها (NOT_DEMO): البيانات الوهمية تعيش في اللوحة فقط.
- نسخة احتياطية من قاعدة البيانات قبل كل ملء، ولا تُرسل أي رسالة أثناءه.
التواريخ نسبية لليوم فيبدو العرض حياً في أي يوم، والبذرة ثابتة فتتكرر نفس البيانات.
الأسماء والجهات خيالية بالكامل (قاعدة المالك)، والمهندسون هم مهندسو النسخة نفسها.
"""
import random
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

FEATURE = "demo"
PREFIX = "DEMO-"
NOT_DEMO = f"tender_id NOT LIKE '{PREFIX}%'"      # شرط SQL: "... AND " + NOT_DEMO أو "AND mt." + NOT_DEMO
KEEP_BACKUPS = 5
ACTIVITY_DAYS = 10
CFG_NIGHTLY, CFG_LAST = "demo_nightly", "demo_last_refresh"
NIGHTLY_AT = "03:00"
SEED = 2026

EDU = "الإدارة العامة للتعليم — الواحة"
WADI = "بلدية وادي الريحان"
COAST = "هيئة تطوير الساحل الأخضر"
NAKHEEL = "أمانة مدينة النخيل"
HEALTH = "تجمع الأمل الصحي"
WATER = "شركة المياه الإقليمية"
TRANSIT = "هيئة النقل الحضري"

# (العنوان، الجهة، نوع الأعمال، القطاع، الموعد بالأيام من اليوم، الحالة)
# الحالة: active | late (مهام متأخرة) | won | lost | nosubmit | deleted
CATALOG = [
    ("إنشاء مدرسة ابتدائية بحي الياسمين", EDU, "إنشاءات", "المباني التعليمية", 2, "active"),
    ("صيانة شبكة تصريف الأمطار بوادي الريحان", WADI, "صيانة وتشغيل", "البنية التحتية", 3, "active"),
    ("توريد وتركيب إنارة LED لطريق الساحل", COAST, "توريد وتركيب", "الطاقة", 5, "active"),
    ("تأهيل ممشى الواجهة البحرية — المرحلة الأولى", NAKHEEL, "إنشاءات", "التطوير العمراني", 7, "late"),
    ("إنشاء مركز رعاية صحية أولية بحي الربوة", HEALTH, "إنشاءات", "المباني الصحية", 9, "late"),
    ("تشغيل وصيانة محطة معالجة المياه الشمالية", WATER, "صيانة وتشغيل", "المياه", 11, "active"),
    ("تنفيذ جسر مشاة عند تقاطع شارع الورود", TRANSIT, "إنشاءات", "الطرق والجسور", 14, "active"),
    ("تطوير حديقة حي الزهور", NAKHEEL, "إنشاءات", "التطوير العمراني", 18, "active"),
    ("توريد معدات مختبرات للمدارس الثانوية", EDU, "توريد", "المباني التعليمية", 22, "active"),
    ("رصف وإنارة طرق حي السلام", WADI, "إنشاءات", "الطرق والجسور", 27, "active"),
    ("صيانة مباني المراكز الصحية — عقد سنوي", HEALTH, "صيانة وتشغيل", "المباني الصحية", 33, "active"),
    ("إنشاء خزان مياه علوي بحي المروج", WATER, "إنشاءات", "المياه", 40, "active"),
    ("إنشاء مواقف سيارات متعددة الطوابق", COAST, "إنشاءات", "التطوير العمراني", 20, "deleted"),
    ("توريد حافلات مدرسية كهربائية", COAST, "توريد", "النقل", -30, "deleted"),
    ("إنشاء مبنى إداري لبلدية وادي الريحان", WADI, "إنشاءات", "المباني الحكومية", -12, "won"),
    ("صيانة طرق المنطقة الصناعية", TRANSIT, "صيانة وتشغيل", "الطرق والجسور", -25, "lost"),
    ("توريد مولدات احتياطية للمراكز الصحية", HEALTH, "توريد وتركيب", "الطاقة", -41, "won"),
    ("تأهيل ملاعب الأحياء", NAKHEEL, "إنشاءات", "التطوير العمراني", -58, "lost"),
    ("إنشاء محطة ضخ مياه جنوبية", WATER, "إنشاءات", "المياه", -77, "won"),
    ("صيانة المدارس — المجموعة الثالثة", EDU, "صيانة وتشغيل", "المباني التعليمية", -96, "lost"),
    ("دراسات تطوير الواجهة الساحلية", COAST, "استشارات", "التطوير العمراني", -120, "nosubmit"),
    ("إنشاء سوق شعبي بحي الربوة", NAKHEEL, "إنشاءات", "المباني التجارية", -150, "won"),
    ("إنارة شارع الورود", TRANSIT, "توريد وتركيب", "الطاقة", -200, "lost"),
    ("إنشاء فصول إضافية بمدرسة الواحة", EDU, "إنشاءات", "المباني التعليمية", -380, "won"),
    ("صيانة شبكة الري بالحدائق العامة", NAKHEEL, "صيانة وتشغيل", "البنية التحتية", -400, "lost"),
]
NOTES = ["تم التواصل مع الجهة بخصوص الاستفسارات", "بانتظار عرض سعر المورد", "الكميات راجعناها مع الموقع",
         "نحتاج شهادة خبرة مشابهة", "المعاينة تمت والتقرير مرفوع", "راجعنا الشروط الخاصة — لا ملاحظات"]


def _table(conn, name) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def status(conn) -> dict:
    n = conn.execute(f"SELECT COUNT(*) FROM master_tenders WHERE tender_id LIKE '{PREFIX}%'").fetchone()[0]
    tasks = conn.execute(f"""SELECT COUNT(*) FROM tender_tasks WHERE tender_row_id IN
        (SELECT id FROM master_tenders WHERE tender_id LIKE '{PREFIX}%')""").fetchone()[0] \
        if _table(conn, "tender_tasks") else 0
    return {"active": n > 0, "tenders": n, "tasks": tasks,
            "engineers": [r[0] for r in conn.execute("SELECT name FROM engineers WHERE is_active=1 ORDER BY id")],
            "nightly": _cfg(conn, CFG_NIGHTLY) == "1", "last_refresh": _cfg(conn, CFG_LAST)}


# ── التجديد الليلي (2026-09-25) ──────────────────────────────────────────
# تواريخ العرض نسبية ليوم الملء، فتبلى بعد أيام (المتأخر يتراكم والتقويم يفرغ)، وما حُرّك في المحاضرة يبقى.
# كل ليلة 03:00 (من البوت): إن كان مفعّلاً والعرض موجوداً ← يُعاد ملؤه بتاريخ اليوم. يلمس بيانات DEMO- وحدها،
# وبلا نسخة احتياطية (النسخ الخمس تحفظ ما قبل أول ملء؛ الليلية كانت ستدفعها خارج الحد خلال أيام).
def _cfg(conn, key) -> str:
    if not _table(conn, "app_config"):
        return ""
    row = conn.execute("SELECT value FROM app_config WHERE key=?", (key,)).fetchone()
    return (row[0] if row else "") or ""


def set_cfg(conn, key, value: str):
    conn.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))


def nightly_refresh(conn, today: date = None, manual: bool = True):
    """يرجع عدّادات الملء إن جُدّد، وإلا None (غير مفعّل، أو لا عرض حالياً). بلا commit."""
    if _cfg(conn, CFG_NIGHTLY) != "1" or not status(conn)["active"]:
        return None
    counts = seed(conn, today, manual)
    set_cfg(conn, CFG_LAST, datetime.now().strftime("%Y-%m-%d %H:%M"))
    if _table(conn, "audit_log"):
        conn.execute("INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                     ("DEMO_NIGHTLY", "demo_mode", str(counts), "System"))
    return counts


def backup(db_path: Path) -> Path:
    """نسخة من قاعدة البيانات كاملة قبل الملء (آخر 5)."""
    folder = Path(db_path).parent / "demo_backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"before-demo-{datetime.now():%Y%m%d-%H%M%S}.db"
    with closing(sqlite3.connect(str(db_path))) as src, closing(sqlite3.connect(str(target))) as dst:
        src.backup(dst)
    for old in sorted(folder.glob("before-demo-*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
    return target


def clear(conn) -> int:
    """يمسح كل بيانات العرض (ولا شيء غيرها). يرجع عدد المنافسات الممسوحة. بلا commit."""
    rows = conn.execute(f"SELECT id, tender_id FROM master_tenders WHERE tender_id LIKE '{PREFIX}%'").fetchall()
    if not rows:
        return 0
    ids = [r[0] for r in rows]
    q = ",".join("?" * len(ids))
    if _table(conn, "tender_tasks"):
        task_ids = [r[0] for r in conn.execute(f"SELECT id FROM tender_tasks WHERE tender_row_id IN ({q})", ids)]
        if task_ids:
            tq = ",".join("?" * len(task_ids))
            for table in ("task_activity", "task_ratings"):
                if _table(conn, table):
                    conn.execute(f"DELETE FROM {table} WHERE task_id IN ({tq})", task_ids)
        conn.execute(f"DELETE FROM tender_tasks WHERE tender_row_id IN ({q})", ids)
    for table, col in (("task_seeded", "tender_row_id"), ("tender_notes", "tender_id"),
                       ("tender_guarantees", "tender_row_id")):
        if _table(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE {col} IN ({q})", ids)
    for table, col in (("tender_results", "tender_id"), ("pending_changes", "tender_id"),
                       ("audit_log", "target_tender")):
        if _table(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE {col} LIKE '{PREFIX}%'")
    conn.execute(f"DELETE FROM master_tenders WHERE id IN ({q})", ids)
    return len(ids)


def _fmt(d: date, manual: bool) -> str:
    return d.strftime("%d/%m/%Y") if manual else d.isoformat()


def _at(d: date, rng) -> str:
    return f"{d.isoformat()} {rng.randint(8, 16):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"


def seed(conn, today: date = None, manual: bool = True) -> dict:
    """يمسح أي عرض سابق ثم يملأ من جديد. يرفع ValueError بلا مهندسين نشطين. بلا commit."""
    import tasks_core
    today = today or date.today()
    engineers = [r[0] for r in conn.execute("SELECT name FROM engineers WHERE is_active=1 ORDER BY id")]
    if not engineers:
        raise ValueError("أضف مهندساً واحداً على الأقل من «فريق المهندسين» أولاً")
    tasks_core.ensure_tables(conn)
    for ensure in _ensure_side_tables():
        conn.execute(ensure)
    clear(conn)
    rng = random.Random(SEED)
    # مهندس لكل منافسة بتوزيع غير متساوٍ (الأول أثقل حملاً) — يُظهر فروق الحمل في التحليلات
    weights = [3] + [2] * (len(engineers) - 1)
    skill = {e: (rng.uniform(3.6, 4.8), rng.uniform(0.65, 0.95)) for e in engineers}   # (جودة، التزام)
    events, counts = [], {"tenders": 0, "tasks": 0, "ratings": 0}

    for n, (title, owner, btype, sector, offset, state) in enumerate(CATALOG, start=1):
        deadline = today + timedelta(days=offset)
        eng = rng.choices(engineers, weights=weights)[0]
        status = {"won": "CLOSED", "lost": "CLOSED", "nosubmit": "CLOSED", "deleted": "DELETED"}.get(state, "InProgress")
        template = tasks_core.template_for(conn, btype)   # قالب نوع الأعمال إن عدّلته الإدارة
        created = deadline - timedelta(days=max(25, max(t[2] for t in template) + 3))   # قبل أبكر مهمة
        cur = conn.execute(
            "INSERT INTO master_tenders (tender_id, title, owner, submission_date, business_type, sector,"
            " assigned_engineer, status, portal_last_seen_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"{PREFIX}{n:03d}", title, owner, _fmt(deadline, manual), btype, sector, eng, status,
             _fmt(deadline, manual), f"{created} 09:00:00", f"{min(deadline, today)} 09:00:00"))
        row_id = cur.lastrowid
        counts["tenders"] += 1
        conn.execute("INSERT OR IGNORE INTO task_seeded (tender_row_id) VALUES (?)", (row_id,))
        _side_rows(conn, row_id, f"{PREFIX}{n:03d}", title, owner, btype, deadline, eng, state, offset, rng, manual)

        if state == "deleted":
            template = template[:2]                         # جهد بُذل ثم ألغتها الجهة
        elif state == "nosubmit":
            template = template[:1]
        for key, task_title, days_before, priority in template:
            due = deadline - timedelta(days=days_before)
            start = min(created, today)
            if state in ("won", "lost", "nosubmit", "deleted") or due < today - timedelta(days=0 if state != "late" else 4):
                st = "done"
            elif due <= today + timedelta(days=2):
                st = "doing"
            else:
                st = "todo"
            if state == "late" and today - timedelta(days=4) <= due < today:
                st = rng.choice(["todo", "doing"])        # متأخرة فعلاً — تظهر في «مطلوب منك الآن»
            q, c = skill[eng]
            done_at = ""
            if st == "done":
                late_by = 0 if rng.random() < c else rng.randint(1, 3)
                done_at = min(due + timedelta(days=late_by) - timedelta(days=rng.randint(0, 1) if not late_by else 0),
                              today)
            note = rng.choice(NOTES) if rng.random() < 0.18 else ""
            cur = conn.execute(
                "INSERT INTO tender_tasks (tender_row_id, title, engineer, status, priority, start_date, due_date,"
                " done_at, notes, created_by, template_key, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row_id, task_title, eng, st, priority, start.isoformat(), due.isoformat(),
                 done_at.isoformat() if done_at else "", note, tasks_core.SYSTEM_ACTOR, key,
                 f"{start} 09:00:00", f"{done_at or today} 12:00:00"))
            tid = cur.lastrowid
            counts["tasks"] += 1
            events.append((f"{start} 09:00:00", tid, "create", "أُنشئت تلقائياً من قالب المنافسة", tasks_core.SYSTEM_ACTOR))
            events.append((f"{start} 09:00:01", tid, "assign", f"أُسندت إلى م. {eng} (مهندس المنافسة)",
                           tasks_core.SYSTEM_ACTOR))
            if st in ("doing", "done"):
                began = max(start, (done_at or today) - timedelta(days=rng.randint(1, 3)))
                events.append((_at(began, rng), tid, "move", "نُقلت إلى «قيد التنفيذ»", eng))
            if note:
                events.append((_at(max(start, (done_at or today) - timedelta(days=1)), rng), tid, "edit",
                               f"ملاحظة: {note}", eng))
            if st == "done":
                events.append((_at(done_at, rng), tid, "move", "نُقلت إلى «منتهية»", eng))
                if rng.random() < 0.85:
                    quality = max(1, min(5, round(rng.gauss(q, 0.6))))
                    commitment = 5 if done_at <= due else rng.randint(2, 3)
                    rated = min(done_at + timedelta(days=1), today)
                    conn.execute("INSERT INTO task_ratings (task_id, quality, commitment, note, rated_by, rated_at)"
                                 " VALUES (?,?,?,?,?,?)", (tid, quality, commitment,
                                                          "عمل ممتاز" if quality == 5 else "", "الإدارة",
                                                          _at(rated, rng)))
                    events.append((_at(rated, rng), tid, "rate", f"التقييم: الجودة {quality}/5 · الالتزام {commitment}/5",
                                   "الإدارة"))
                    counts["ratings"] += 1
    # ترتيب الأعمدة: مهام العرض بعد المهام الحقيقية (ترتيبها لا يُمس)، الأقرب استحقاقاً أولاً
    # و«منتهية» الأحدث إنجازاً أولاً
    for status_ in tasks_core.STATUSES:
        first = conn.execute(f"""SELECT COALESCE(MAX(position), -1) + 1 FROM tender_tasks WHERE status=?
            AND tender_row_id NOT IN (SELECT id FROM master_tenders WHERE tender_id LIKE '{PREFIX}%')""",
                             (status_,)).fetchone()[0]
        order = "done_at DESC" if status_ == "done" else "due_date"
        ids = [r[0] for r in conn.execute(f"""SELECT id FROM tender_tasks WHERE status=? AND tender_row_id IN
            (SELECT id FROM master_tenders WHERE tender_id LIKE '{PREFIX}%') ORDER BY {order}, id""", (status_,))]
        for pos, tid in enumerate(ids, start=first):
            conn.execute("UPDATE tender_tasks SET position=? WHERE id=?", (pos, tid))
    # الجرس: حركة آخر ACTIVITY_DAYS يوماً فقط (السجل الأقدم يبقى إنشاءً وإسناداً) — وإلا 99+ غير مقروء
    horizon = (today - timedelta(days=ACTIVITY_DAYS)).isoformat()
    cap = f"{today} {datetime.now():%H:%M:%S}" if today == date.today() else f"{today} 23:59:59"   # لا حركة في المستقبل
    events = [(min(e[0], cap),) + e[1:] for e in events if e[2] in ("create", "assign") or e[0] >= horizon]
    conn.execute(f"""UPDATE task_ratings SET rated_at=MIN(rated_at, ?) WHERE task_id IN (SELECT t.id FROM tender_tasks t
        JOIN master_tenders m ON m.id=t.tender_row_id WHERE m.tender_id LIKE '{PREFIX}%')""", (cap,))
    events.sort()                                           # الأحدث = أكبر رقم ← أعلى الجرس
    conn.executemany("INSERT INTO task_activity (at, task_id, action, details, actor) VALUES (?,?,?,?,?)", events)
    return counts


def _ensure_side_tables():
    return (
        """CREATE TABLE IF NOT EXISTS tender_results (id INTEGER PRIMARY KEY AUTOINCREMENT, tender_id TEXT NOT NULL,
           title TEXT, owner TEXT, business_type TEXT, submission_date TEXT, assigned_engineer TEXT,
           did_submit INTEGER DEFAULT 0, result TEXT DEFAULT 'pending', our_price REAL, winning_price REAL, notes TEXT,
           recorded_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS tender_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, tender_id INTEGER UNIQUE,
           notes TEXT DEFAULT '', is_extended INTEGER DEFAULT 0, extension_count INTEGER DEFAULT 0,
           extension_dates TEXT DEFAULT '', submitted_to_review INTEGER DEFAULT 0, review_date TEXT DEFAULT '',
           submitted_to_upload INTEGER DEFAULT 0, upload_submit_date TEXT DEFAULT '',
           uploaded_to_platform INTEGER DEFAULT 0, platform_upload_date TEXT DEFAULT '',
           updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS tender_guarantees (tender_row_id INTEGER PRIMARY KEY, required INTEGER DEFAULT 1,
           due_date TEXT DEFAULT '', status TEXT DEFAULT 'PENDING', notes TEXT DEFAULT '',
           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    )


def _side_rows(conn, row_id, key, title, owner, btype, deadline, eng, state, offset, rng, manual):
    """النتيجة، مراحل المنافسة، والضمان — متسقة مع حالتها."""
    closed = state in ("won", "lost", "nosubmit")
    if closed:
        base = rng.randrange(900_000, 9_000_000, 50_000)
        win = {"won": base, "lost": round(base * rng.uniform(0.86, 0.96), -3)}.get(state)
        stamp = f"{deadline + timedelta(days=rng.randint(10, 30))} 10:00:00"
        conn.execute("INSERT INTO tender_results (tender_id, title, owner, business_type, submission_date,"
                     " assigned_engineer, did_submit, result, our_price, winning_price, recorded_at, updated_at)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (key, title, owner, btype, _fmt(deadline, manual), eng, 0 if state == "nosubmit" else 1,
                      None if state == "nosubmit" else state, None if state == "nosubmit" else base, win, stamp, stamp))
    stage = {2: "uploaded", 3: "upload", 5: "review"}.get(offset, "done" if state in ("won", "lost") else "")
    if stage:
        conn.execute("INSERT INTO tender_notes (tender_id, submitted_to_review, submitted_to_upload,"
                     " uploaded_to_platform) VALUES (?,?,?,?)",
                     (row_id, 1, int(stage in ("upload", "uploaded", "done")), int(stage in ("uploaded", "done"))))
    if state in ("active", "late", "won", "lost"):
        g = ("SUBMITTED" if closed or offset <= 2 else "READY" if offset <= 3 else
             "IN_PROGRESS" if offset <= 7 else "PENDING")
        conn.execute("INSERT INTO tender_guarantees (tender_row_id, due_date, status) VALUES (?,?,?)",
                     (row_id, (deadline - timedelta(days=5)).isoformat(), g))
