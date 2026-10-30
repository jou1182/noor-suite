# -*- coding: utf-8 -*-
"""
Noor Tender Exporter - Cookie Edition
=========================================
Uses session cookies extracted from local Chrome to bypass login.
"""
import os
import sys
import time
import json
import logging
import requests
from pathlib import Path

logger = logging.getLogger("Exporter")

# ── Paths ──────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.resolve()
DOWNLOAD_DIR = ROOT_DIR / "output"
ARCHIVE_DIR  = DOWNLOAD_DIR / "archive"
OUT_XLSX     = DOWNLOAD_DIR / "in_progress_tenders.xlsx"
STATUS_FILE  = DOWNLOAD_DIR / "export_status.txt"
COOKIES_FILE = DOWNLOAD_DIR / "portal_cookies.json"

config_path = ROOT_DIR / "selectors.json"
if config_path.exists():
    config = json.loads(config_path.read_text(encoding="utf-8"))
    BASE_URL = config.get("portal_url", "https://www.noor-ms.com")
    EXPORT_URL = BASE_URL + config.get("export_path", "/ar/tendering/export_to_excel_in_progress_tender/")
else:
    BASE_URL   = "https://www.noor-ms.com"
    EXPORT_URL = BASE_URL + "/ar/tendering/export_to_excel_in_progress_tender/"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

LAST_SIG_FILE = ARCHIVE_DIR / ".last_content_signature"


def content_signature(xlsx_bytes: bytes):
    """
    بصمة محتوى الجدول (القيم فقط). ملف Excel يختلف بايتياً في كل تنزيل (طوابع زمنية
    داخلية) حتى لو لم تتغير أي منافسة — لذا المقارنة بالقيم لا بالبايتات.
    يرجع None إن تعذرت القراءة (عندها يُؤرشف الملف احتياطاً).
    """
    import hashlib
    import io
    try:
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True).active
        rows = repr([tuple(r) for r in ws.iter_rows(values_only=True)])
        return hashlib.sha1(rows.encode("utf-8")).hexdigest()
    except Exception as e:
        logger.warning(f"Could not fingerprint export (will archive anyway): {e}")
        return None


def archive_if_changed(xlsx_bytes: bytes, ts: str):
    """يحفظ نسخة أرشيفية فقط عند تغيّر محتوى المنافسات عن آخر نسخة مؤرشفة."""
    sig = content_signature(xlsx_bytes)
    last = LAST_SIG_FILE.read_text(encoding="utf-8").strip() if LAST_SIG_FILE.exists() else ""
    if sig and sig == last:
        return None
    archive = ARCHIVE_DIR / f"in_progress_tenders_{ts}.xlsx"
    archive.write_bytes(xlsx_bytes)
    if sig:
        LAST_SIG_FILE.write_text(sig, encoding="utf-8")
    logger.info(f"📚 Portal content changed — archived {archive.name}")
    return archive


def ensure_dirs():
    for d in (DOWNLOAD_DIR, ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)

def download_via_cookies() -> bool:
    if not COOKIES_FILE.exists():
        logger.error(f"Cookies file not found at: {COOKIES_FILE}")
        return False

    session = requests.Session()
    try:
        cookies_data = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        for cookie in cookies_data:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', '.noor-ms.com'))
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
        return False

    logger.info("📡 Attempting download using provided session cookies...")
    try:
        resp = session.get(EXPORT_URL, headers=HEADERS, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 5000:
            ts = time.strftime("%Y-%m-%d_%H%M")
            archive_if_changed(resp.content, ts)
            tmp = OUT_XLSX.with_suffix(".xlsx.part")
            tmp.write_bytes(resp.content)
            tmp.replace(OUT_XLSX)  # استبدال ذري: المحرك لا يقرأ ملفاً نصف مكتوب
            logger.info(f"✅ Success! File saved: {OUT_XLSX.name}")
            return True
        else:
            logger.error(f"❌ Download failed. Status: {resp.status_code}, Size: {len(resp.content)} bytes")
            if resp.status_code == 403:
                logger.error("Session expired. Please run 'Update_Server_Session.bat' on your Desktop.")
            return False
    except Exception as e:
        logger.error(f"Network error: {e}")
        return False

def main():
    ensure_dirs()
    ok = download_via_cookies()
    STATUS_FILE.write_text("success" if ok else "failed", encoding="utf-8")
    return ok

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    sys.exit(0 if main() else 1)
