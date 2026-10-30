# -*- coding: utf-8 -*-
"""حسابات المهندسين (2026-09-24) — حساب وكلمة مرور لكل مهندس بدل رمز البوابة المشترك.

- الإدارة تنشئ الحساب أو تعيد تعيينه من /admin/engineers ← كلمة مرور مؤقتة تظهر لها مرة واحدة،
  والمهندس مُلزم بتغييرها عند أول دخول (must_change).
- التخزين: hash فقط (werkzeug) — لا تُحفظ كلمة المرور نفسها ولا تُسجَّل.
- مهندس له حساب: لا يقبل دخوله برمز البوابة المشترك (ENGINEER_PIN) بعد الآن.
  مهندس بلا حساب: السلوك القديم كما هو (النور لا حسابات لديه = لا تغيير).
بلا Flask: الدوال تأخذ اتصال sqlite والمستدعي يعمل commit.
"""
import secrets
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

FEATURE = "engineer_accounts"
MIN_LENGTH = 8
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"      # بلا أحرف متشابهة (l/1، o/0)


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS engineer_accounts (
        engineer_name TEXT PRIMARY KEY,
        pwd_hash      TEXT NOT NULL,
        must_change   INTEGER NOT NULL DEFAULT 1,
        active        INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT DEFAULT (datetime('now','localtime')),
        updated_at    TEXT DEFAULT (datetime('now','localtime')),
        last_login    TEXT DEFAULT ''
    )""")


def _temp_password() -> str:
    raw = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def issue(conn, engineer: str) -> str:
    """ينشئ الحساب أو يعيد تعيينه بكلمة مؤقتة (يجب تغييرها عند الدخول). يرجع الكلمة المؤقتة."""
    ensure_table(conn)
    if not conn.execute("SELECT 1 FROM engineers WHERE name=? AND is_active=1", (engineer,)).fetchone():
        raise LookupError("المهندس غير موجود أو غير نشط")
    temp = _temp_password()
    conn.execute("""INSERT INTO engineer_accounts (engineer_name, pwd_hash, must_change, active)
                    VALUES (?,?,1,1)
                    ON CONFLICT(engineer_name) DO UPDATE SET pwd_hash=excluded.pwd_hash, must_change=1,
                      active=1, updated_at=datetime('now','localtime')""",
                 (engineer, generate_password_hash(temp)))
    _drop_telegram(conn, engineer)          # أي اشتراك قديم بالرمز المشترك يسقط — يعيد الربط من بوابته
    return temp


def set_active(conn, engineer: str, active: bool) -> bool:
    ensure_table(conn)
    cur = conn.execute("UPDATE engineer_accounts SET active=?, updated_at=datetime('now','localtime') "
                       "WHERE engineer_name=?", (1 if active else 0, engineer))
    return cur.rowcount > 0


def get(conn, engineer: str):
    """صف الحساب أو None — لا ينشئ الجدول (نسخة بلا حسابات تبقى كما هي)."""
    try:
        return conn.execute("SELECT * FROM engineer_accounts WHERE engineer_name=?", (engineer,)).fetchone()
    except sqlite3.OperationalError:
        return None


def verify(conn, engineer: str, password: str):
    """None = لا حساب لهذا المهندس (يُستخدم الرمز المشترك)، False = مرفوض، وإلا صف الحساب."""
    row = get(conn, engineer)
    if row is None:
        return None
    if not row["active"] or not check_password_hash(row["pwd_hash"], password or ""):
        return False
    conn.execute("UPDATE engineer_accounts SET last_login=datetime('now','localtime') WHERE engineer_name=?",
                 (engineer,))
    return row


def change_password(conn, engineer: str, current: str, new: str, confirm: str):
    """يغيّر كلمة مرور المهندس. يرفع ValueError برسالة عربية."""
    row = get(conn, engineer)
    if row is None or not row["active"]:
        raise ValueError("لا يوجد حساب نشط")
    if not check_password_hash(row["pwd_hash"], current or ""):
        raise ValueError("كلمة المرور الحالية غير صحيحة")
    if len(new or "") < MIN_LENGTH:
        raise ValueError(f"كلمة المرور الجديدة {MIN_LENGTH} أحرف على الأقل")
    if new != confirm:
        raise ValueError("تأكيد كلمة المرور غير مطابق")
    if new == current:
        raise ValueError("اختر كلمة مرور مختلفة عن الحالية")
    conn.execute("UPDATE engineer_accounts SET pwd_hash=?, must_change=0, updated_at=datetime('now','localtime') "
                 "WHERE engineer_name=?", (generate_password_hash(new), engineer))


def overview(conn) -> list:
    """كل المهندسين (الحاليون أولاً ثم السابقون) مع حالة حساباتهم وعملهم المفتوح (لصفحة الإدارة)."""
    ensure_table(conn)
    rows = [dict(r) for r in conn.execute("""
        SELECT e.name, e.capacity, e.is_active AS employed,
               a.engineer_name IS NOT NULL AS has_account, COALESCE(a.active, 0) AS active,
               COALESCE(a.must_change, 0) AS must_change, COALESCE(a.last_login, '') AS last_login,
               COALESCE(a.updated_at, '') AS updated_at,
               (SELECT COUNT(*) FROM master_tenders m WHERE m.assigned_engineer = e.name
                  AND m.status NOT IN ('CLOSED','DELETED','REJECTED')) AS open_tenders
        FROM engineers e LEFT JOIN engineer_accounts a ON a.engineer_name = e.name
        ORDER BY e.is_active DESC, e.name""")]
    try:
        tasks = dict(conn.execute("SELECT engineer, COUNT(*) FROM tender_tasks WHERE status<>'done' "
                                  "GROUP BY engineer").fetchall())
    except sqlite3.OperationalError:
        tasks = {}
    for r in rows:
        r["open_tasks"] = tasks.get(r["name"], 0)
    return rows


# ── فريق المهندسين: إضافة مهندس معيَّن حديثاً / إزالة من ترك الشركة (2026-09-25) ──
# الإزالة إيقاف لا حذف: يختفي من كل القوائم، ويبقى تاريخه وتقييماته ونتائجه، ويمكن إعادته.

def add_engineer(conn, name: str, capacity=5) -> str:
    """ADDED / REACTIVATED (كان سابقاً) / EXISTS — نفس قواعد /addengineer في البوت."""
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 40:
        raise ValueError("اكتب اسم المهندس (من حرفين إلى 40 حرفاً)")
    try:
        capacity = max(1, min(int(capacity), 50))
    except (TypeError, ValueError):
        capacity = 5
    row = conn.execute("SELECT id, is_active FROM engineers WHERE name=?", (name,)).fetchone()
    if row and row[1]:
        return "EXISTS"
    if row:
        conn.execute("UPDATE engineers SET is_active=1, capacity=? WHERE id=?", (capacity, row[0]))
        return "REACTIVATED"
    conn.execute("INSERT INTO engineers (name, capacity, is_active) VALUES (?,?,1)", (name, capacity))
    return "ADDED"


def remove_engineer(conn, name: str) -> dict:
    """يوقف مهندساً ترك الشركة: يخرج من القوائم، يُغلق حسابه، وتتوقف رسائله على تليجرام.
    يرجع عمله المفتوح (لتعيده الإدارة لغيره)."""
    row = conn.execute("SELECT is_active FROM engineers WHERE name=?", (name,)).fetchone()
    if not row:
        raise LookupError("المهندس غير موجود")
    conn.execute("UPDATE engineers SET is_active=0 WHERE name=?", (name,))
    for sql in ("UPDATE engineer_accounts SET active=0, updated_at=datetime('now','localtime') WHERE engineer_name=?",
                "DELETE FROM engineer_subs WHERE engineer_name=?"):
        try:
            conn.execute(sql, (name,))
        except sqlite3.OperationalError:
            pass                                   # الجدول غير موجود في هذه النسخة
    left = {r["name"]: r for r in overview(conn)}.get(name, {})
    return {"open_tenders": left.get("open_tenders", 0), "open_tasks": left.get("open_tasks", 0)}


# ── ربط تليجرام بحساب المهندس (2026-09-25) ────────────────────────────────
# المهندس يدخل بوابته بكلمة مروره ← «ربط تليجرام» ← رمز 6 أرقام (10 دقائق، مرة واحدة)
# ← يرسل للبوت خاصاً: /link الرمز. لا تُكتب كلمة المرور في تليجرام أبداً.
LINK_TTL_MINUTES = 10


def _drop_telegram(conn, engineer: str):
    try:
        conn.execute("DELETE FROM engineer_subs WHERE engineer_name=?", (engineer,))
    except sqlite3.OperationalError:
        pass


def _ensure_link_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS telegram_link_codes (
        code          TEXT PRIMARY KEY,
        engineer_name TEXT NOT NULL,
        expires_at    TEXT NOT NULL)""")


def issue_link_code(conn, engineer: str) -> str:
    """رمز ربط جديد للمهندس (يلغي رموزه السابقة)."""
    row = get(conn, engineer)
    if row is None or not row["active"]:
        raise LookupError("لا يوجد حساب نشط")
    _ensure_link_table(conn)
    conn.execute("DELETE FROM telegram_link_codes WHERE engineer_name=? OR expires_at < datetime('now','localtime')",
                  (engineer,))
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not conn.execute("SELECT 1 FROM telegram_link_codes WHERE code=?", (code,)).fetchone():
            break
    conn.execute("INSERT INTO telegram_link_codes (code, engineer_name, expires_at) "
                 f"VALUES (?, ?, datetime('now','localtime','+{LINK_TTL_MINUTES} minutes'))", (code, engineer))
    return code


def redeem_link_code(conn, code: str, chat_id: int):
    """يربط محادثة تليجرام بالمهندس صاحب الرمز. يرجع اسمه، أو None لرمز خاطئ/منتهٍ/مستخدم."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        return None
    try:
        row = conn.execute("SELECT engineer_name FROM telegram_link_codes WHERE code=? "
                           "AND expires_at >= datetime('now','localtime')", (code,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row:
        return None
    name = row[0]
    account = get(conn, name)
    conn.execute("DELETE FROM telegram_link_codes WHERE code=?", (code,))          # مرة واحدة
    if account is None or not account["active"]:
        return None
    conn.execute("""CREATE TABLE IF NOT EXISTS engineer_subs (chat_id INTEGER PRIMARY KEY,
                    engineer_name TEXT NOT NULL, subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""INSERT INTO engineer_subs (chat_id, engineer_name, subscribed_at) VALUES (?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id) DO UPDATE SET engineer_name=excluded.engineer_name,
                      subscribed_at=CURRENT_TIMESTAMP""", (chat_id, name))
    return name


def telegram_links(conn, engineer: str) -> int:
    try:
        return conn.execute("SELECT COUNT(*) FROM engineer_subs WHERE engineer_name=?", (engineer,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def unlink_telegram(conn, engineer: str) -> int:
    n = telegram_links(conn, engineer)
    _drop_telegram(conn, engineer)
    return n


def pin_subscription_blocked(conn, engineer: str) -> bool:
    """صاحب الحساب الشخصي لا يُختار اسمه عبر /subscribe بالرمز المشترك — الربط من بوابته فقط."""
    return get(conn, engineer) is not None
