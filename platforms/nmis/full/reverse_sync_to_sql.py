import sqlite3
import pandas as pd
import os
from pathlib import Path
import logging
import time
from dotenv import load_dotenv

logger = logging.getLogger("Reverse_Sync")

# Paths
ROOT_DIR = Path(__file__).parent.resolve()
excel_path = ROOT_DIR / "output" / "Master_Tenders.xlsx"

# كان db_path ثابتاً على output/tenders.db دائماً -- لا يحترم DB_PATH من
# .env إطلاقاً (نفس فئة الخلل المصلحة في db_manager.py). لأي عميل له
# DB_PATH مخصص (كل مستأجر الويزارد)، كانت المزامنة العكسية تكتب بصمت في
# قاعدة فارغة لا يراها أي كود آخر، والتعديل اليدوي يختفي بصمت. الإنتاج
# الحقيقي مافيشوش DB_PATH في .env أصلاً، فالسلوك القديم يفضل كما هو.
load_dotenv(ROOT_DIR / ".env")
db_path = Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH", "").strip() else ROOT_DIR / "output" / "tenders.db"
if not db_path.is_absolute():
    db_path = ROOT_DIR / db_path

REQUIRED_COLS = ["ID_النظام", "اسم المنافسة", "المهندس المسؤول"]

def reverse_sync() -> int:
    """
    Reads the Manager's Master Excel file and updates the DB accordingly.
    Supports updating existing tenders AND adding new ones manually.
    """
    if not excel_path.exists():
        logger.warning(f"Reverse Sync skipped: {excel_path} not found.")
        return 0

    try:
        # Read only the active sheet
        df = pd.read_excel(excel_path, sheet_name='المناقصات النشطة')
    except Exception:
        try:
            df = pd.read_excel(excel_path)
        except Exception as e:
            logger.error(f"Reverse Sync: Cannot read Excel file -> {e}")
            return 0

    # Validate columns exist
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        logger.warning(f"Reverse Sync skipped: Missing columns {missing}")
        return 0

    # --- PART 1: Sync Tenders (UPSERT Logic) ---
    updated_count = 0
    added_count = 0
    
    with sqlite3.connect(db_path) as conn:
        for _, row in df.iterrows():
            sys_id   = row.get("ID_النظام")
            title    = str(row.get("اسم المنافسة", "")).strip()
            tender_id = str(row.get("رقم المنافسة", "")).strip()
            owner    = str(row.get("المالك", "")).strip()
            engineer = str(row.get("المهندس المسؤول", "")).strip()
            sub_date = str(row.get("تاريخ التقديم", "")).strip()
            biz_type = str(row.get("نوع الأعمال", "")).strip()
            sector   = str(row.get("القطاع", "")).strip()
            status   = str(row.get("الحالة", "InProgress")).strip()

            if not title or title in ("nan", "اسم المنافسة"):
                continue
            
            if engineer in ("nan", ""): engineer = None
            if status not in ("InProgress", "CLOSED", "ACTIVE"): status = "InProgress"

            # Case A: Existing tender (Has ID)
            if not pd.isna(sys_id) and str(sys_id).strip() != "":
                try:
                    sys_id = int(float(sys_id))
                    # NOTE: submission_date is intentionally NOT updated here.
                    # It is controlled by the portal scraper (engine_core) and the
                    # web dashboard. Overwriting it from Excel would revert any
                    # manual date corrections the user has made via the dashboard.
                    cursor = conn.execute('''
                        UPDATE master_tenders
                        SET    assigned_engineer = CASE
                               WHEN engineer_locked = 1 THEN assigned_engineer
                               ELSE COALESCE(?, assigned_engineer)
                           END,
                               status            = ?,
                               updated_at        = CURRENT_TIMESTAMP
                        WHERE  id = ?
                    ''', (engineer, status, sys_id))
                    if cursor.rowcount > 0: updated_count += 1
                except: continue
            
            # Case B: Manual New Entry (No ID but has title)
            else:
                # Check if already exists by title to prevent duplicates
                exists = conn.execute("SELECT id FROM master_tenders WHERE title = ?", (title,)).fetchone()
                if not exists:
                    if not tender_id or tender_id == "nan":
                        tender_id = f"MANUAL-{int(time.time())}"
                    
                    conn.execute('''
                        INSERT INTO master_tenders (tender_id, title, owner, submission_date, business_type, sector, assigned_engineer, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (tender_id, title, owner, sub_date, biz_type, sector, engineer, status))
                    added_count += 1

        # --- PART 2: Sync Engineers ---
        eng_updates = []
        try:
            df_eng = pd.read_excel(excel_path, sheet_name='إدارة المهندسين')
            for _, row in df_eng.iterrows():
                name = str(row.get("اسم المهندس", "")).strip()
                cap  = row.get("الطاقة الاستيعابية", 5)
                active = row.get("نشط (1=نعم)", 1)
                if name and name != "nan":
                    eng_updates.append((name, int(cap), int(active)))
        except: pass

        if eng_updates:
            conn.execute("DELETE FROM engineers")
            conn.executemany("INSERT INTO engineers (name, capacity, is_active) VALUES (?, ?, ?)", eng_updates)
            
        conn.commit()

    logger.info(f"Reverse Sync complete: {updated_count} updated, {added_count} added manually.")
    return updated_count + added_count

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reverse_sync()
