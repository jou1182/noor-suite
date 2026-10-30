# Noor V4 - System Health Dashboard
import os
import sqlite3
import time
import json
from pathlib import Path
from datetime import datetime

# Dynamic paths - works on any machine regardless of installation directory
BASE_DIR     = Path(__file__).parent
OUTPUT_DIR   = BASE_DIR / "output"
DB_PATH      = OUTPUT_DIR / "tenders.db"
COOKIES_FILE = OUTPUT_DIR / "portal_cookies.json"
EXCEL_PATH   = OUTPUT_DIR / "Master_Tenders.xlsx"


def get_health():
    print("="*60)
    print("   ⚓ NOOR SYSTEM - HEALTH DASHBOARD ⚓")
    print("="*60)
    
    # 1. Database Check
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        active = c.execute("SELECT COUNT(*) FROM master_tenders WHERE status != 'CLOSED'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM pending_changes WHERE status = 'PENDING_APPROVAL'").fetchone()[0]
        last_audit = c.execute("SELECT action, created_at FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        print(f"🟢 Database: OK ({DB_PATH.name})")
        print(f"   - Active Tenders: {active}")
        print(f"   - Pending Changes: {pending}")
        if last_audit:
            print(f"   - Last Action: {last_audit[0]} at {last_audit[1]}")
    else:
        print("🔴 Database: NOT FOUND!")

    # 2. Cookies Check
    if COOKIES_FILE.exists():
        mtime = COOKIES_FILE.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        print(f"🔵 Cookies: OK (Age: {age_hours:.1f} hours)")
        if age_hours > 24:
            print("   ⚠️ WARNING: Cookies are older than 24h.")
    else:
        print("🔴 Cookies: MISSING!")

    # 3. Excel Check
    if EXCEL_PATH.exists():
        mtime = EXCEL_PATH.stat().st_mtime
        age_mins = (time.time() - mtime) / 60
        print(f"📊 Live Excel: OK ({age_mins:.1f} mins ago)")
    else:
        print("🔴 Live Excel: NOT FOUND!")

    # 4. Service Check (Local process check example)
    print("="*60)
    print(f"System Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

if __name__ == "__main__":
    get_health()
