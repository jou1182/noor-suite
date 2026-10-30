# -*- coding: utf-8 -*-
"""مصدر المنافسات للإدخال اليدوي (2026-09-25) — لنسخ "portal_adapter": "manual" (النور).

المصدر = ملف إكسل واحد (manual_input/tenders.xlsx) يقرؤه المحرك كل دورة كأنه «المنصة».
طريقتان لتحديثه من لوحة الإدارة (/admin/source) بلا دخول السيرفر:
  1) رفع ملف من المتصفح،  2) رابط Google Drive/Sheets يُسحب تلقائياً مع كل دورة.
قبل أي تطبيق: معاينة (جديدة / تغيّر تاريخها / ستختفي / بلا تغيير) + أخطاء الصفوف.
التطبيق: نسخة احتياطية من الملف السابق (آخر 20) ثم كتابة الجديد — والبوت يلتقطه خلال ثوانٍ.
⚠️ صفّ يختفي ولم يحن موعده = المحرك يعتبره «محذوفاً من المنصة» ويطلق التنبيه الأحمر.
"""
import hashlib
import io
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from instance_paths import APP_DIR
from tasks_core import ACTIVE_EXCLUDED, parse_deadline

MANUAL_FILE = APP_DIR / "manual_input" / "tenders.xlsx"
HISTORY_DIR = APP_DIR / "manual_input" / "history"
PENDING_DIR = APP_DIR / "output" / "source_pending"
REQUIRED_COLUMNS = ["رقم المنافسة", "اسم المنافسة", "المالك", "تاريخ التقديم", "نوع الأعمال", "القطاع"]
MAX_BYTES = 5 * 1024 * 1024
KEEP_HISTORY = 20
CFG_URL, CFG_AUTO, CFG_HASH = "manual_source_url", "manual_source_auto", "manual_source_hash"
ALLOWED_HOSTS = ("docs.google.com", "drive.google.com")


def is_manual_instance() -> bool:
    from company_profile import PROFILE
    return (PROFILE.get("portal_adapter") or "").strip().lower() == "manual"


# ── قراءة وتحقق ─────────────────────────────────────────────────────────────
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else (s[:-2] if re.fullmatch(r"\d+\.0", s) else s)


def read_rows(data: bytes):
    """(الصفوف كقواميس، أخطاء عامة). يرفع ValueError لملف غير صالح."""
    if not data:
        raise ValueError("الملف فارغ")
    if len(data) > MAX_BYTES:
        raise ValueError("الملف أكبر من 5 ميجابايت")
    if not data.startswith(b"PK"):
        raise ValueError("ليس ملف إكسل (.xlsx)")
    from openpyxl import load_workbook
    try:
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    except Exception:
        raise ValueError("تعذّرت قراءة ملف الإكسل")
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("الملف بلا صفوف")
    header = [_cell(h) for h in rows[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError("أعمدة ناقصة: " + "، ".join(missing))
    idx = {c: header.index(c) for c in REQUIRED_COLUMNS}
    out = []
    for n, r in enumerate(rows[1:], start=2):
        rec = {c: _cell(r[i]) if i < len(r) else "" for c, i in idx.items()}
        if not any(rec.values()):
            continue
        rec["_row"] = n
        out.append(rec)
    return out


def _identity(rec) -> str:
    from engine_core import build_tender_identity      # نفس مفتاح المحرك حرفياً
    return build_tender_identity(rec)


def preview(conn, data: bytes, today: date = None) -> dict:
    """ماذا سيحدث لو طُبّق هذا الملف؟ لا يكتب شيئاً."""
    today = today or date.today()
    rows = read_rows(data)
    errors, seen, file_ids = [], {}, {}
    for rec in rows:
        if not rec["اسم المنافسة"]:
            errors.append({"row": rec["_row"], "msg": "اسم المنافسة فارغ"})
            continue
        if not parse_deadline(rec["تاريخ التقديم"]):
            errors.append({"row": rec["_row"], "msg": f"تاريخ غير مفهوم «{rec['تاريخ التقديم']}» — استخدم DD/MM/YYYY"})
        key = _identity(rec)
        if key in seen:
            errors.append({"row": rec["_row"], "msg": f"مكرر مع الصف {seen[key]}"})
            continue
        seen[key] = rec["_row"]
        file_ids[key] = rec
    master = {r[0]: r for r in conn.execute(
        "SELECT tender_id, title, owner, submission_date, portal_last_seen_date, status FROM master_tenders")}
    new, changed, same = [], [], 0
    for key, rec in file_ids.items():
        m = master.get(key)
        item = {"id": key, "title": rec["اسم المنافسة"], "owner": rec["المالك"], "date": rec["تاريخ التقديم"]}
        if not m or m[5] in ("CLOSED", "DELETED"):
            new.append(item)
            continue
        old = parse_deadline(m[4] or m[3])
        if old != parse_deadline(rec["تاريخ التقديم"]):
            changed.append({**item, "old_date": m[4] or m[3] or "—"})
        else:
            same += 1
    gone_deleted, gone_closed = [], []
    for key, m in master.items():
        if key in file_ids or m[5] in ACTIVE_EXCLUDED or key.startswith("DEMO-"):   # وضع العرض ليس من الملف
            continue
        d = parse_deadline(m[3])
        item = {"id": key, "title": m[1], "owner": m[2] or "", "date": m[3] or ""}
        (gone_deleted if d is None or d >= today else gone_closed).append(item)
    return {"rows": len(rows), "valid": len(file_ids), "errors": errors, "new": new, "changed": changed,
            "unchanged": same, "will_delete": gone_deleted, "will_close": gone_closed,
            "hash": hashlib.sha256(data).hexdigest()[:16]}


# ── تطبيق ───────────────────────────────────────────────────────────────────
def apply(data: bytes, manual_file: Path = None, history_dir: Path = None) -> Path:
    """نسخة احتياطية من الملف الحالي ثم كتابة الجديد (ذرّياً). يرجع مسار النسخة الاحتياطية أو None."""
    read_rows(data)                                   # لا يُكتب ملف غير صالح أبداً
    manual_file = manual_file or MANUAL_FILE
    history_dir = history_dir or HISTORY_DIR
    manual_file.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if manual_file.exists():
        history_dir.mkdir(parents=True, exist_ok=True)
        backup = history_dir / f"tenders-{datetime.now():%Y%m%d-%H%M%S}.xlsx"
        backup.write_bytes(manual_file.read_bytes())
        for old in sorted(history_dir.glob("tenders-*.xlsx"))[:-KEEP_HISTORY]:
            old.unlink()
    tmp = manual_file.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(manual_file)
    return backup


def status(conn, manual_file: Path = None) -> dict:
    manual_file = manual_file or MANUAL_FILE
    info = {"path": "manual_input/tenders.xlsx", "exists": manual_file.exists(), "rows": 0, "modified": "",
            "url": get_cfg(conn, CFG_URL), "auto": get_cfg(conn, CFG_AUTO) == "1",
            "history": len(list(HISTORY_DIR.glob("tenders-*.xlsx"))) if HISTORY_DIR.exists() else 0}
    if info["exists"]:
        info["modified"] = datetime.fromtimestamp(manual_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        try:
            info["rows"] = len(read_rows(manual_file.read_bytes()))
        except ValueError as e:
            info["error"] = str(e)
    return info


def template_bytes() -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "المنافسات"
    ws.sheet_view.rightToLeft = True
    ws.append(REQUIRED_COLUMNS)
    ws.append(["251144099", "مثال: تأهيل ممر مشاة (احذف هذا الصف)", "جهة تجريبية", "30/11/2026", "إنشاءات", "البنية التحتية"])
    for col, w in zip("ABCDEF", (16, 48, 28, 16, 18, 20)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── رابط Google Drive / Sheets ─────────────────────────────────────────────
def direct_url(url: str) -> str:
    """يحوّل رابط المشاركة إلى رابط تنزيل xlsx. يرفع ValueError لغير Google."""
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        raise ValueError("الرابط يجب أن يكون من Google Drive أو Google Sheets (https)")
    m = re.search(r"/spreadsheets/d/([\w-]+)", u.path)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    m = re.search(r"/file/d/([\w-]+)", u.path) or re.search(r"[?&]id=([\w-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    raise ValueError("لم أتعرف على الرابط — انسخ رابط المشاركة من زر «مشاركة» في Google")


def fetch_url(url: str) -> bytes:
    import requests
    r = requests.get(direct_url(url), timeout=25, allow_redirects=True, stream=True)
    host = urlparse(r.url).hostname or ""
    if not (host.endswith("google.com") or host.endswith("googleusercontent.com")):
        raise ValueError("تحويل غير متوقع من الرابط")
    data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if r.status_code != 200 or not data.startswith(b"PK"):
        raise ValueError("تعذّر تنزيل الملف — تأكد أن المشاركة «أي شخص معه الرابط يستطيع العرض»")
    return data


# ── إعدادات (app_config) ────────────────────────────────────────────────────
def get_cfg(conn, key: str) -> str:
    try:
        r = conn.execute("SELECT value FROM app_config WHERE key=?", (key,)).fetchone()
        return (r[0] if r else "") or ""
    except sqlite3.OperationalError:
        return ""


def set_cfg(conn, key: str, value: str):
    conn.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO app_config (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def auto_sync(conn) -> str:
    """من دورة البوت: يسحب الرابط إن كانت المزامنة مفعّلة ويطبّقه إن تغيّر. يرجع وصفاً قصيراً أو ''."""
    url = get_cfg(conn, CFG_URL)
    if not url or get_cfg(conn, CFG_AUTO) != "1":
        return ""
    data = fetch_url(url)
    h = hashlib.sha256(data).hexdigest()[:16]
    if h == get_cfg(conn, CFG_HASH):
        return ""
    apply(data)
    set_cfg(conn, CFG_HASH, h)
    return f"synced {len(data)} bytes ({h})"
