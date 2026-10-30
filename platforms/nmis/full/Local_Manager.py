import sys
from pathlib import Path

# Standardization
sys.stdout.reconfigure(encoding='utf-8')

# Import core system
sys.path.append(str(Path(__file__).parent))
from db_manager import DBManager

db = DBManager()

def show_menu():
    print("\n" + "="*60)
    print("   ⚓ NOOR V4 INFRASTRUCTURE - LOCAL MANAGEMENT ⚓")
    print("="*60)
    print(" [1] VIEW STAGED TENDERS (Pending Approval)")
    print(" [2] APPROVE TENDER (Local Simulation / Commit to Master)")
    print(" [3] VIEW ENGINEERS WORKLOAD & CAPACITY")
    print(" [4] RE-GENERATE MASTER EXCEL (Refresh file)")
    print(" [0] EXIT")
    print("="*60)

def main():
    while True:
        show_menu()
        choice = input(">> Select Command: ")
        
        if choice == '1':
            pendings = db.get_pending_changes()
            if not pendings:
                print("\n✅ Clean Slate: No pending tenders waiting for approval.")
            else:
                print(f"\n--- Staged Tenders ({len(pendings)}) ---")
                for p in pendings:
                    print(f"ID: {p['id']} | [{p['change_type']}] Title: {p['title']} | Suggestion: {p['suggested_engineer']}")

        elif choice == '2':
            p_id = input("\nEnter Row ID to Approve: ")
            try:
                # Get the pending record for reference
                with db._get_connection() as conn:
                    p_row = conn.execute("SELECT * FROM pending_changes WHERE id=?", (p_id,)).fetchone()
                
                if not p_row:
                    print("❌ Error: ID not found.")
                    continue
                
                print(f"Approving: {p_row['title']}")
                eng = input(f"Confirm/Change assigned engineer (Default: {p_row['suggested_engineer']}): ") or p_row['suggested_engineer']
                
                db.approve_change(int(p_id), eng)
                print(f"✅ Success! Tender committed to Master DB and Excel updated.")
            except Exception as e:
                print(f"❌ Operation Failed: {e}")

        elif choice == '3':
            engs = db.get_all_engineers()
            print("\n--- Current Roster & Performance ---")
            for e in engs:
                print(f"Engineer: {e['name']:<12} | Limit: {e['capacity']} | Status: Active")

        elif choice == '4':
            db.export_master_excel()
            print("\n📊 Master_Tenders.xlsx has been refreshed with latest DB data.")

        elif choice == '0':
            print("System management session closed.")
            break
        else:
            print("❌ Invalid input. Please select 0-4.")

if __name__ == "__main__":
    main()
