import sqlite3
import pandas as pd
import re
import difflib
import os
from pathlib import Path
from typing import Iterator, List, Optional
from contextlib import contextmanager
import logging
import json
import time
from dotenv import load_dotenv

logger = logging.getLogger("DB_Manager")

BASE_DIR = Path(__file__).parent / "output"

# هذا الملف قد يُستورد مباشرة (سكربت تشخيص يدوي، python -c "import db_manager"،
# أو أي أداة في الكورس) قبل ما يُنفّذ مستدعيه أي load_dotenv() خاص به --
# فلا يُفترض ترتيب الاستيراد في الملف المستدعي. override=False الافتراضي، فلا يؤثر
# على التشغيل تحت systemd (المتغيرات مضبوطة مسبقاً عبر EnvironmentFile).
load_dotenv(Path(__file__).parent / ".env")

# DB_PATH يحترم متغير البيئة DB_PATH لو مضبوط (نفس نمط web_dashboard.py بالضبط) --
# بدونه، أي كود بينادي DBManager() من غير مسار صريح (bot_daemon.py مثلاً) كان
# بيفتح ملف مختلف تماماً عن الملف اللي جهّزه الويزارد أو provision_instance.py،
# فيلاقي قاعدة فاضية بلا هوية الشركة. الإنتاج الحقيقي مافيشوش DB_PATH في .env
# أصلاً، فالسلوك القديم يفضل تماماً كما هو -- التعديل إضافي بحت.
DB_PATH = Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH", "").strip() else BASE_DIR / "tenders.db"


def _normalize_ar_light(text) -> str:
    """نسخة خفيفة من normalize_arabic (توحيد الهمزات/إزالة التشكيل والتطويل)
    لأغراض مقارنة التشابه هنا فقط -- نسخة محلية بدل استيراد engine_core
    (الذي يستورد db_manager أصلاً، فكان سيسبب استيراداً دائرياً)."""
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'[\u064B-\u065F]', '', text)
    text = text.replace('ـ', '')
    return text.strip().lower()


class DBManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._initialize_tables()
        self._seed_engineers()
        # Startup integrity check — warns early if DB is corrupted
        if self.db_path.exists():
            try:
                with sqlite3.connect(str(self.db_path)) as _c:
                    r = _c.execute("PRAGMA integrity_check").fetchone()[0]
                    if r != "ok":
                        logger.critical(f"⚠️ DB INTEGRITY CHECK FAILED ON STARTUP: {r}")
                    else:
                        logger.info("DB integrity check on startup: OK ✓")
            except Exception as e:
                logger.critical(f"⚠️ DB startup check error: {e}")

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-32000")
            conn.execute("PRAGMA foreign_keys=ON")
            # Checkpoint WAL every 200 pages (vs default 1000) to keep
            # the main .db file up-to-date and reduce corruption risk.
            conn.execute("PRAGMA wal_autocheckpoint=200")
            yield conn
            if conn.in_transaction:
                conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def check_integrity(self) -> bool:
        """Run SQLite integrity check. Returns True if DB is healthy."""
        try:
            with self._get_connection() as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    logger.error(f"DB integrity check FAILED: {result}")
                    return False
                logger.info("DB integrity check passed ✓")
                return True
        except Exception as e:
            logger.error(f"DB integrity check error: {e}")
            return False

    def force_checkpoint(self) -> None:
        """Force a full WAL checkpoint — flush all WAL pages to main DB."""
        try:
            with self._get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.info("WAL checkpoint completed ✓")
        except Exception as e:
            logger.warning(f"WAL checkpoint warning: {e}")

    def _initialize_tables(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS engineers (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    name     TEXT    UNIQUE NOT NULL,
                    capacity INTEGER DEFAULT 5,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS master_tenders (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    tender_id        TEXT NOT NULL UNIQUE,
                    title            TEXT NOT NULL,
                    owner            TEXT,
                    submission_date  TEXT,
                    business_type    TEXT,
                    sector           TEXT,
                    assigned_engineer TEXT,
                    status           TEXT DEFAULT 'InProgress',
                    missing_seen_count INTEGER DEFAULT 0,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_changes (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    tender_id         TEXT NOT NULL,
                    title             TEXT NOT NULL,
                    change_type       TEXT NOT NULL,
                    submission_date   TEXT,
                    details_json      TEXT,
                    suggested_engineer TEXT,
                    status            TEXT DEFAULT 'PENDING_APPROVAL',
                    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tender_id, change_type, status)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    action           TEXT NOT NULL,
                    target_tender    TEXT,
                    details          TEXT,
                    performed_by     TEXT,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self._migrate_master_tenders_schema(conn)
            self._migrate_pending_changes_constraints(conn)
            self._migrate_pending_changes_approval_stage(conn)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_tenders_title  ON master_tenders(title)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_tenders_status ON master_tenders(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_tenders_eng    ON master_tenders(assigned_engineer)")
            conn.commit()

    def _migrate_master_tenders_schema(self, conn: sqlite3.Connection) -> None:
        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='master_tenders'").fetchone()
        if not table: return
        columns = conn.execute("PRAGMA table_info(master_tenders)").fetchall()
        col_names = {c["name"] for c in columns}
        if "missing_seen_count" not in col_names:
            conn.execute("ALTER TABLE master_tenders ADD COLUMN missing_seen_count INTEGER DEFAULT 0")
        # portal_last_seen_date: tracks what the portal last showed, independent of
        # any manual date override the user may have set via the dashboard.
        # The engine compares the NEW scraped date against THIS value — not against
        # submission_date — so manual dashboard edits never trigger false notifications.
        if "portal_last_seen_date" not in col_names:
            conn.execute("ALTER TABLE master_tenders ADD COLUMN portal_last_seen_date TEXT")
            # Seed with current submission_date so first run doesn't flood with notifications
            conn.execute("UPDATE master_tenders SET portal_last_seen_date = submission_date WHERE portal_last_seen_date IS NULL")
        # engineer_locked / date_locked: يحدّدان لو التعيين/التاريخ تم تثبيته يدوياً
        # (من لوحة التحكم) فما ينعكسش عليه تحديثات المنصة التلقائية بعد كده --
        # موجودان في قاعدة الإنتاج الحقيقية منذ زمن طويل عبر ترحيل يدوي غير مسجَّل
        # هنا، فأي قاعدة بيانات جديدة (عميل جديد) كانت تفتقدهما تماماً وتسقط فوراً.
        if "engineer_locked" not in col_names:
            conn.execute("ALTER TABLE master_tenders ADD COLUMN engineer_locked INTEGER DEFAULT 0")
        if "date_locked" not in col_names:
            conn.execute("ALTER TABLE master_tenders ADD COLUMN date_locked INTEGER DEFAULT 0")

    def _migrate_pending_changes_constraints(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_active_change ON pending_changes(tender_id, change_type) WHERE status IN ('PENDING_APPROVAL', 'NOTIFIED')")

    def _migrate_pending_changes_approval_stage(self, conn: sqlite3.Connection) -> None:
        """ROADMAP_V6 Phase 4: عمود يتتبع مرحلة الموافقة المزدوجة الاختيارية.
        NULL = مسار الموافقة الواحدة القديم (السلوك الافتراضي، غير مُفعّل).
        القيم عند التفعيل: awaiting_engineer -> awaiting_manager -> (يُحذف عند approve_change)."""
        columns = conn.execute("PRAGMA table_info(pending_changes)").fetchall()
        if "approval_stage" not in {c["name"] for c in columns}:
            conn.execute("ALTER TABLE pending_changes ADD COLUMN approval_stage TEXT")

    def _seed_engineers(self) -> None:
        with self._get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM engineers").fetchone()[0]
            if count == 0:
                engineers = [("أحمد", 5), ("عمر", 5), ("خالد", 5), ("فهد", 5)]
                conn.executemany("INSERT INTO engineers (name, capacity) VALUES (?, ?)", engineers)
                conn.commit()

    def log_audit(self, action: str, target: str, details: str, user: str = "System", conn=None):
        query = "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?, ?, ?, ?)"
        params = (action, target, details, user)
        if conn: conn.execute(query, params)
        else:
            with self._get_connection() as c:
                c.execute(query, params)
                c.commit()

    def get_all_engineers(self) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM engineers WHERE is_active = 1 ORDER BY name").fetchall()

    def add_engineer(self, name: str, capacity: int = 5) -> str:
        """
        يضيف مهندساً جديداً إلى الجدول، أو يعيد تفعيل مهندس مُعطّل بنفس الاسم.
        يعيد رمز الحالة: 'ADDED' | 'REACTIVATED' | 'EXISTS'.
        الأزرار في تيليجرام تُبنى من هذا الجدول (get_all_engineers)،
        فيظهر المهندس تلقائياً في كل الكيبوردات فور الإضافة — لا حاجة لأي كود إضافي.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("اسم المهندس فارغ.")
        try:
            capacity = int(capacity)
        except (TypeError, ValueError):
            capacity = 5
        if capacity < 1:
            capacity = 1
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, is_active FROM engineers WHERE name = ?", (name,)
            ).fetchone()
            if row:
                if row["is_active"]:
                    return "EXISTS"
                conn.execute(
                    "UPDATE engineers SET is_active = 1, capacity = ? WHERE id = ?",
                    (capacity, row["id"])
                )
                self.log_audit("ENGINEER_REACTIVATED", name, f"capacity={capacity}", conn=conn)
                conn.commit()
                return "REACTIVATED"
            conn.execute(
                "INSERT INTO engineers (name, capacity, is_active) VALUES (?, ?, 1)",
                (name, capacity)
            )
            self.log_audit("ENGINEER_ADDED", name, f"capacity={capacity}", conn=conn)
            conn.commit()
            return "ADDED"

    def suggest_best_engineer(self, tender_title: str = "") -> str:
        """Legacy wrapper — kept for backward compatibility."""
        return self.smart_suggest_engineer()['name']

    def smart_suggest_engineer(self, owner: str = "", business_type: str = "", submission_date: str = "") -> dict:
        """
        نظام ترشيح ذكي من 100 نقطة أساسية + حتى 10 نقاط إضافية لجودة الأداء:
          حمل المهندس الحالي       20 نقطة  (كلما كان فاضياً أكثر نقاطاً)
          ضغط المواعيد القادمة     30 نقطة  (كلما كانت مشاريعه بعيدة أكثر نقاطاً)
          خبرة نطاق العمل          30 نقطة  (مشاريع مماثلة سابقة × 10، حد أقصى 30)
          خبرة الجهة المالكة       20 نقطة  (تعاملات سابقة مع نفس الجهة × 10، حد أقصى 20)
          نسبة الفوز التاريخية    +10 نقطة إضافية (فقط لو 3 نتائج محسومة فأكثر --
                                    بيانات أقل من كده مش كافية تُحكم بها بإنصاف، فتُعطى صفر محايد)
        """
        _na = {"n/a", "nan", "none", "غير محدد", ""}

        with self._get_connection() as conn:
            engineers = conn.execute("SELECT * FROM engineers WHERE is_active = 1").fetchall()
            if not engineers:
                return {"name": "مدير النظام", "score": 0, "reason": "لا مهندسين متاحين", "breakdown": "", "all_scores": []}

            scored = []
            for eng in engineers:
                name     = eng['name']
                capacity = eng['capacity'] or 5

                active_count = conn.execute(
                    "SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer = ? AND status NOT IN ('CLOSED','REJECTED')",
                    (name,)
                ).fetchone()[0]

                # مشاريع تُغلق خلال 30 يوماً
                upcoming = conn.execute(
                    """SELECT COUNT(*) FROM master_tenders
                       WHERE assigned_engineer = ?
                         AND status NOT IN ('CLOSED','REJECTED')
                         AND submission_date NOT IN ('N/A','غير محدد','')
                         AND date(submission_date) BETWEEN date('now') AND date('now','+30 days')""",
                    (name,)
                ).fetchone()[0]

                # خبرة نطاق العمل
                bt_clean = (business_type or "").strip()
                type_exp = conn.execute(
                    "SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer = ? AND business_type = ?",
                    (name, bt_clean)
                ).fetchone()[0] if bt_clean.lower() not in _na else 0

                # خبرة الجهة المالكة
                ow_clean = (owner or "").strip()
                owner_exp = conn.execute(
                    "SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer = ? AND owner = ?",
                    (name, ow_clean)
                ).fetchone()[0] if ow_clean.lower() not in _na else 0

                # نسبة الفوز التاريخية -- بونص إضافي، محايد (صفر) إن البيانات غير كافية
                MIN_DECIDED_SAMPLE = 3
                win_decided = conn.execute(
                    "SELECT COUNT(*) FROM tender_results WHERE assigned_engineer = ? AND result IN ('won','lost')",
                    (name,)
                ).fetchone()[0]
                win_won = conn.execute(
                    "SELECT COUNT(*) FROM tender_results WHERE assigned_engineer = ? AND result = 'won'",
                    (name,)
                ).fetchone()[0]
                win_rate  = (win_won / win_decided) if win_decided >= MIN_DECIDED_SAMPLE else None
                win_score = round(win_rate * 10, 1) if win_rate is not None else 0

                load_score     = round((1 - min(active_count / capacity, 1.0)) * 20, 1)
                pressure_ratio = upcoming / active_count if active_count > 0 else 0
                deadline_score = round((1 - min(pressure_ratio, 1.0)) * 30, 1)
                type_score     = min(type_exp * 10, 30)
                owner_score    = min(owner_exp * 10, 20)
                total          = round(load_score + deadline_score + type_score + owner_score + win_score, 1)

                scored.append({
                    "name": name, "score": total,
                    "load_score": load_score, "deadline_score": deadline_score,
                    "type_score": type_score, "owner_score": owner_score, "win_score": win_score,
                    "active_count": active_count, "upcoming": upcoming,
                    "type_exp": type_exp, "owner_exp": owner_exp, "capacity": capacity,
                    "win_decided": win_decided, "win_rate": win_rate,
                })

        scored.sort(key=lambda x: x['score'], reverse=True)
        best = scored[0]

        reasons = []
        if best['win_rate'] is not None and best['win_rate'] >= 0.5:
            reasons.append(f"نسبة فوز {round(best['win_rate']*100)}% في {best['win_decided']} مناقصة محسومة")
        if best['owner_exp'] > 0:
            reasons.append(f"عمل مع نفس الجهة {best['owner_exp']} مرة")
        if best['type_exp'] > 0:
            reasons.append(f"خبرة {best['type_exp']} مشروع مماثل")
        if best['upcoming'] == 0 and best['active_count'] > 0:
            reasons.append("لا مواعيد ضاغطة قريباً")
        reason = " | ".join(reasons) if reasons else "الأقل حملاً حالياً"

        win_line = (
            f"  🏆 نسبة الفوز: {best['win_score']}/10  ({round(best['win_rate']*100)}% من {best['win_decided']} محسومة)\n"
            if best['win_rate'] is not None else
            f"  🏆 نسبة الفوز: — (بيانات غير كافية بعد، أقل من 3 نتائج محسومة)\n"
        )
        breakdown = (
            f"📊 _تفصيل النقاط ({best['score']}/110)_\n"
            f"  🏋️ الحمل: {best['load_score']}/20  ({best['active_count']}/{best['capacity']} مشاريع)\n"
            f"  ⏰ المواعيد: {best['deadline_score']}/30  ({best['upcoming']} تُغلق في 30 يوم)\n"
            f"  🏗️ نطاق العمل: {best['type_score']}/30  ({best['type_exp']} مشروع مماثل)\n"
            f"  🏢 الجهة المالكة: {best['owner_score']}/20  ({best['owner_exp']} تعامل سابق)\n"
            f"{win_line}"
        ).rstrip()

        return {
            "name": best['name'],
            "score": best['score'],
            "reason": reason,
            "breakdown": breakdown,
            "all_scores": scored,
        }

    def add_pending_change(self, tender_id, title, change_type, submission_date="", details_json="{}", suggested_eng=None, conn=None):
        t_id_str = str(tender_id).strip().lower()
        if not t_id_str or t_id_str in ('nan', 'n/a', 'none', ''): return
        q = "INSERT OR IGNORE INTO pending_changes (tender_id, title, change_type, submission_date, details_json, suggested_engineer) VALUES (?, ?, ?, ?, ?, ?)"
        params = (tender_id, title, change_type, submission_date, details_json, suggested_eng)
        if conn: conn.execute(q, params)
        else:
            with self._get_connection() as c:
                c.execute(q, params)
                c.commit()

    def get_pending_changes(self) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM pending_changes WHERE status = 'PENDING_APPROVAL' ORDER BY created_at ASC").fetchall()

    def approve_change(self, pending_id: int, finalize_engineer: str) -> None:
        with self._get_connection() as conn:
            try:
                row = conn.execute("SELECT * FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
                if not row: return
                tender_id, title, submission_date, change_type, details = row['tender_id'], row['title'], row['submission_date'], row['change_type'], json.loads(row['details_json'] or "{}")
                valid_tender_id = str(tender_id).strip().lower() not in ('', 'nan', 'n/a', 'none')
                existing = None
                if valid_tender_id:
                    existing = conn.execute("SELECT id FROM master_tenders WHERE tender_id = ?", (tender_id,)).fetchone()
                if not existing:
                    existing = conn.execute("SELECT id FROM master_tenders WHERE title = ?", (title,)).fetchone()

                if change_type in ('NEW', 'NEW_TENDER'):
                    if existing:
                        conn.execute('''
                            UPDATE master_tenders
                            SET submission_date = CASE WHEN date_locked=1 THEN submission_date ELSE ? END,
                                portal_last_seen_date = ?,
                                assigned_engineer = CASE WHEN engineer_locked=1 THEN assigned_engineer ELSE ? END,
                                status = 'InProgress', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (submission_date, submission_date, finalize_engineer, existing['id']))
                    else:
                        if not valid_tender_id:
                            tender_id = f"MANUAL-{int(time.time())}"
                        owner = details.get('المالك') or details.get('owner')
                        business_type = details.get('نوع الأعمال') or details.get('business_type')
                        sector = details.get('القطاع') or details.get('sector')
                        conn.execute('''
                            INSERT INTO master_tenders (tender_id, title, owner, submission_date, portal_last_seen_date, business_type, sector, assigned_engineer)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (tender_id, title, owner, submission_date, submission_date, business_type, sector, finalize_engineer))
                else:
                    if existing:
                        conn.execute('''
                            UPDATE master_tenders
                            SET submission_date = CASE WHEN date_locked=1 THEN submission_date ELSE ? END,
                                portal_last_seen_date = ?,
                                assigned_engineer = CASE WHEN engineer_locked=1 THEN assigned_engineer ELSE ? END,
                                status = 'InProgress', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (submission_date, submission_date, finalize_engineer, existing['id']))
                    elif valid_tender_id:
                        conn.execute(
                            "UPDATE master_tenders SET submission_date = ?, portal_last_seen_date = ?, assigned_engineer = ?, status = 'InProgress', updated_at = CURRENT_TIMESTAMP WHERE tender_id = ?",
                            (submission_date, submission_date, finalize_engineer, tender_id)
                        )
                conn.execute("UPDATE pending_changes SET status = 'APPROVED' WHERE id = ?", (pending_id,))
                self.log_audit("APPROVE", title, f"Assigned to {finalize_engineer}", "Admin", conn=conn)
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Approval failed: {e}")
        self.export_master_excel()

    def delete_pending_change(self, pending_id: int) -> None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT title FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
            if row: self.log_audit("REJECT", row[0], "Rejected via Telegram", "Admin", conn=conn)
            conn.execute("UPDATE pending_changes SET status = 'REJECTED' WHERE id = ?", (pending_id,))
            conn.commit()

    def set_approval_stage(self, pending_id: int, stage: str, engineer_name: str = None) -> None:
        """ROADMAP_V6 Phase 4: يحرّك طلبًا معلّقًا بين مراحل الموافقة المزدوجة
        (awaiting_engineer -> awaiting_manager) دون لمس master_tenders --
        الاعتماد الفعلي النهائي يبقى حصريًا عبر approve_change()."""
        with self._get_connection() as conn:
            if engineer_name:
                conn.execute(
                    "UPDATE pending_changes SET approval_stage = ?, suggested_engineer = ? WHERE id = ?",
                    (stage, engineer_name, pending_id)
                )
            else:
                conn.execute(
                    "UPDATE pending_changes SET approval_stage = ? WHERE id = ?",
                    (stage, pending_id)
                )
            conn.commit()

    def export_master_excel(self) -> None:
        try:
            with self._get_connection() as conn:
                df_active = pd.read_sql("SELECT id, tender_id, title, owner, submission_date, business_type, sector, assigned_engineer, status FROM master_tenders WHERE status NOT IN ('CLOSED', 'REJECTED') ORDER BY created_at ASC", conn)
                df_closed = pd.read_sql("SELECT id, tender_id, title, owner, submission_date, business_type, sector, assigned_engineer, status, updated_at FROM master_tenders WHERE status = 'CLOSED' ORDER BY updated_at DESC", conn)
                df_engineers = pd.read_sql("SELECT name, capacity, is_active FROM engineers", conn)
            
            def clean_date(val):
                try:
                    if pd.isna(val) or str(val).lower() in ("n/a", "none", ""): return "غير محدد"
                    return pd.to_datetime(val).strftime('%Y-%m-%d')
                except: return str(val)

            for df in [df_active, df_closed]:
                if 'submission_date' in df.columns: df['submission_date'] = df['submission_date'].apply(clean_date)
            if 'updated_at' in df_closed.columns: df_closed['updated_at'] = df_closed['updated_at'].apply(clean_date)

            ar_cols = ["ID_النظام", "رقم المنافسة", "اسم المنافسة", "المالك", "تاريخ التقديم", "نوع الأعمال", "القطاع", "المهندس المسؤول", "الحالة"]
            df_active.columns = ar_cols
            df_closed.columns = ar_cols + ["تاريخ الإغلاق"]
            df_engineers.columns = ["اسم المهندس", "الطاقة الاستيعابية", "نشط (1=نعم)"]

            excel_path = BASE_DIR / "Master_Tenders.xlsx"
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_active.to_excel(writer, sheet_name='المناقصات النشطة', index=False)
                df_closed.to_excel(writer, sheet_name='الأرشيف (مغلقة)', index=False)
                df_engineers.to_excel(writer, sheet_name='إدارة المهندسين', index=False)
        except Exception as e:
            logger.error(f"Excel export failed: {e}")

    def get_stats_summary(self) -> dict:
        try:
            with self._get_connection() as conn:
                active = conn.execute("SELECT COUNT(*) FROM master_tenders WHERE status != 'CLOSED'").fetchone()[0]
                closed = conn.execute("SELECT COUNT(*) FROM master_tenders WHERE status = 'CLOSED'").fetchone()[0]
                pending = conn.execute("SELECT COUNT(*) FROM pending_changes WHERE status = 'PENDING_APPROVAL'").fetchone()[0]
            return {"active_count": active, "closed_count": closed, "pending_count": pending, "engineers": self.get_all_engineers_with_load()}
        except: return None

    def get_system_stats(self) -> dict:
        return self.get_stats_summary()

    def find_similar_won_tenders(self, title: str, owner: str = "", business_type: str = "", limit: int = 3) -> List[dict]:
        """يبحث عن مناقصات فائزة سابقة (tender_results.result='won') مشابهة
        للمنافسة الجديدة -- نفس الجهة و/أو نفس نطاق العمل و/أو تشابه العنوان --
        عشان يعرض للمهندس سياق تسعير مفيد قبل اتخاذ القرار."""
        norm_title = _normalize_ar_light(title)
        norm_owner = _normalize_ar_light(owner) if owner else ""
        norm_btype = _normalize_ar_light(business_type) if business_type else ""

        with self._get_connection() as conn:
            won = conn.execute(
                "SELECT title, owner, business_type, our_price, winning_price "
                "FROM tender_results WHERE result = 'won'"
            ).fetchall()

        scored = []
        for w in won:
            score = 0.0
            if norm_owner and w["owner"] and norm_owner == _normalize_ar_light(w["owner"]):
                score += 50
            if norm_btype and w["business_type"] and norm_btype == _normalize_ar_light(w["business_type"]):
                score += 30
            ratio = difflib.SequenceMatcher(None, norm_title, _normalize_ar_light(w["title"] or "")).ratio()
            score += ratio * 20
            if score >= 40:
                scored.append({
                    "title": w["title"], "owner": w["owner"],
                    "our_price": w["our_price"], "winning_price": w["winning_price"],
                    "score": round(score, 1),
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def get_all_engineers_with_load(self) -> List[dict]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT e.name, e.capacity,
                       ((SELECT COUNT(*) FROM master_tenders m WHERE m.assigned_engineer = e.name AND m.status NOT IN ('CLOSED', 'REJECTED')) +
                        (SELECT COUNT(*) FROM pending_changes p WHERE p.suggested_engineer = e.name AND p.status = 'PENDING_APPROVAL')) as current_load
                FROM engineers e WHERE e.is_active = 1
            ''').fetchall()
            return [{"name": r['name'], "load": r['current_load'], "capacity": r['capacity'], "load_pct": min(100, int((r['current_load'] / r['capacity']) * 100)) if r['capacity'] > 0 else 100} for r in rows]

if __name__ == "__main__":
    db = DBManager()
    db.export_master_excel()
