import sqlite3
import json
from pathlib import Path
from db_manager import DBManager

db = DBManager()

def auto_approve_all():
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_changes WHERE status != 'APPROVED'")
        pendings = cursor.fetchall()
    
    count = 0
    with db._get_connection() as conn:
        for pending in pendings:
            tender_id = pending['tender_id']
            title = pending['title']
            submission_date = pending['submission_date']
            details = json.loads(pending['details_json'])
            
            owner = str(details.get('المالك', 'N/A'))
            business_type = str(details.get('نوع الأعمال', 'N/A'))
            sector = str(details.get('القطاع', 'N/A'))
            
            # Insert into master
            conn.execute('''
                INSERT OR REPLACE INTO master_tenders 
                (tender_id, title, owner, submission_date, business_type, sector, assigned_engineer)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (tender_id, title, owner, submission_date, business_type, sector, pending['suggested_engineer']))
            
            # Note: We assign them to the suggested engineer just to clear the queue
            # And mark as APPROVED
            conn.execute("UPDATE pending_changes SET status = 'APPROVED' WHERE id = ?", (pending['id'],))
            count += 1
        conn.commit()
    return count

if __name__ == "__main__":
    cleared = auto_approve_all()
    db.export_master_excel()
    print(f"Bypassed and Auto-Approved {cleared} pending items into master_tenders.")
