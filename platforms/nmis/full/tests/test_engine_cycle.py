"""
دورة المحرك كاملة (find_and_stage_changes) على قاعدة مؤقتة وملف منصة وهمي:
تهيئة، جديد، تعديل تاريخ، إغلاق، إعادة فتح، ربط منافسة معدّلة الاسم.
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import engine_core as ec
from db_manager import DBManager

OWNER = "امانة المنطقة الشرقية"
PAST = "2020-01-15"      # موعد تقديم منتهٍ → الإغلاق بعد 3 دورات غياب
FUTURE = "2099-06-30"


def tender(title, date=PAST, owner=OWNER, btype="طرق", sector="حكومي"):
    return {"رقم المنافسة": "", "اسم المنافسة": title, "المالك": owner,
            "تاريخ التقديم": date, "نوع الأعمال": btype, "القطاع": sector}


class EngineCycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_cycle_"))
        self.db = DBManager(self.tmp / "tenders.db")
        # tender_results تُنشئه لوحة التحكم (web_dashboard.ensure_results_table) لا DBManager
        with self.db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tender_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, tender_id TEXT NOT NULL, title TEXT,
                    owner TEXT, business_type TEXT, submission_date TEXT, assigned_engineer TEXT,
                    did_submit INTEGER DEFAULT 0, result TEXT DEFAULT 'pending', our_price REAL,
                    winning_price REAL, notes TEXT, recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP)
            """)
        self._orig = (ec.BASE_DIR, ec.NEW_FILE_DEFAULT)
        ec.BASE_DIR = self.tmp
        ec.NEW_FILE_DEFAULT = self.tmp / "in_progress_tenders.xlsx"

    def tearDown(self):
        ec.BASE_DIR, ec.NEW_FILE_DEFAULT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────
    def cycle(self, rows):
        pd.DataFrame(rows).to_excel(self.tmp / "Extracted_Tenders.xlsx", index=False)
        return ec.find_and_stage_changes(self.db, skip_scrape=True)

    def q(self, sql, *args):
        with self.db._get_connection() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def pending(self, change_type):
        return self.q("SELECT * FROM pending_changes WHERE change_type=? AND status IN ('PENDING_APPROVAL','NOTIFIED')", change_type)

    def master(self, title):
        rows = self.q("SELECT * FROM master_tenders WHERE title=?", title)
        return rows[0] if rows else None

    # ── scenarios ────────────────────────────────────────────
    def test_first_run_initializes_baseline_without_notifications(self):
        self.assertEqual(self.cycle([tender("مشروع أ"), tender("مشروع ب")]), 0)
        self.assertEqual(len(self.q("SELECT * FROM master_tenders")), 2)
        self.assertEqual(self.q("SELECT * FROM pending_changes"), [])

    def test_new_tender_is_staged(self):
        self.cycle([tender("مشروع أ")])
        self.assertEqual(self.cycle([tender("مشروع أ"), tender("مشروع جديد تماماً")]), 1)
        self.assertEqual([p["title"] for p in self.pending("NEW")], ["مشروع جديد تماماً"])

    def test_portal_date_change_is_staged(self):
        self.cycle([tender("مشروع أ", date="2099-01-01")])
        self.assertEqual(self.cycle([tender("مشروع أ", date="2099-02-01")]), 1)
        self.assertEqual(len(self.pending("UPDATED_DATE")), 1)

    def test_missing_tender_closes_after_threshold(self):
        self.cycle([tender("مشروع أ"), tender("مشروع ب")])
        for _ in range(2):
            self.cycle([tender("مشروع أ")])
            self.assertNotEqual(self.master("مشروع ب")["status"], "CLOSED")
        self.cycle([tender("مشروع أ")])
        self.assertEqual(self.master("مشروع ب")["status"], "CLOSED")
        self.assertEqual(len(self.pending("CLOSED")), 1)

    def _close(self, title, keep):
        self.cycle([tender(keep), tender(title)])
        for _ in range(3):
            self.cycle([tender(keep)])
        self.assertEqual(self.master(title)["status"], "CLOSED")
        # مثل البوت: إشعار الإغلاق "للعلم" يُعلَّم APPROVED فور إرساله (notify_pending_changes)
        with self.db._get_connection() as conn:
            conn.execute("UPDATE pending_changes SET status='APPROVED' WHERE change_type='CLOSED'")
            conn.commit()

    def test_closed_tender_back_on_portal_is_reopened(self):
        self._close("مشروع ب", keep="مشروع أ")
        self.assertEqual(self.cycle([tender("مشروع أ"), tender("مشروع ب")]), 1)
        reopened = self.pending("REOPENED")
        self.assertEqual([p["title"] for p in reopened], ["مشروع ب"])
        self.assertEqual(self.pending("NEW"), [])
        # الاعتماد يعيد الحالة إلى InProgress
        self.db.approve_change(reopened[0]["id"], "مدير النظام")
        self.assertEqual(self.master("مشروع ب")["status"], "InProgress")

    def test_reopen_is_not_re_asked_after_admin_rejects_it(self):
        self._close("مشروع ب", keep="مشروع أ")
        self.cycle([tender("مشروع أ"), tender("مشروع ب")])
        self.db.delete_pending_change(self.pending("REOPENED")[0]["id"])
        self.assertEqual(self.cycle([tender("مشروع أ"), tender("مشروع ب")]), 0)
        self.assertEqual(self.pending("REOPENED"), [])
        self.assertEqual(self.master("مشروع ب")["status"], "CLOSED")

    def test_renamed_tender_is_relinked_not_new(self):
        old = "مشروع تأهيل شوارع بحي النهضة والمنتزة بالدمام"
        fixed = "مشروع تأهيل شوارع بحي النهضة والمنتزه بالدمام"
        self.cycle([tender("مشروع أ"), tender(old)])
        original_id = self.master(old)["tender_id"]

        self.assertEqual(self.cycle([tender("مشروع أ"), tender(fixed)]), 0)
        self.assertEqual(self.pending("NEW"), [])
        row = self.q("SELECT * FROM master_tenders WHERE tender_id=?", original_id)[0]
        self.assertEqual(row["title"], fixed)
        self.assertEqual(row["missing_seen_count"], 0)
        self.assertEqual(len(self.q("SELECT * FROM tender_aliases")), 1)

        # الدورات التالية مستقرة عبر الـ alias: لا جديد ولا إغلاق للأصلية
        for _ in range(4):
            self.assertEqual(self.cycle([tender("مشروع أ"), tender(fixed)]), 0)
        self.assertEqual(self.q("SELECT status FROM master_tenders WHERE tender_id=?", original_id)[0]["status"], "InProgress")
        self.assertEqual(self.pending("CLOSED"), [])

    def test_next_part_is_new_not_relinked(self):
        part1 = "صيانة الشوارع والأرصفة بقطاع وسط مدينة الرياض الجزء الأول"
        part2 = "صيانة الشوارع والأرصفة بقطاع وسط مدينة الرياض الجزء الثاني"
        self.cycle([tender("مشروع أ"), tender(part1)])
        self.assertEqual(self.cycle([tender("مشروع أ"), tender(part2)]), 1)
        self.assertEqual([p["title"] for p in self.pending("NEW")], [part2])
        self.assertEqual(self.q("SELECT * FROM tender_aliases"), [])

    # ── حذف من المنصة قبل الموعد (2026-09-19: منافستان اختفتا قبل موعدهما بأسبوع ولم يُنبَّه أحد) ──
    def test_tender_removed_before_deadline_is_flagged_deleted(self):
        self.cycle([tender("مشروع أ"), tender("منافسة محذوفة", date=FUTURE)])
        for _ in range(10):
            self.cycle([tender("مشروع أ")])
        self.assertEqual(self.master("منافسة محذوفة")["status"], "CLOSED")
        self.assertEqual([p["title"] for p in self.pending("DELETED")], ["منافسة محذوفة"])
        self.assertEqual(self.pending("CLOSED"), [])
        self.assertEqual(len(self.q("SELECT * FROM audit_log WHERE action='AUTO_DELETE'")), 1)

    def test_demo_tenders_are_never_compared_with_the_portal(self):
        """وضع العرض (DEMO-) ليس في ملف المنصة — غيابه لا يعني حذفاً ولا إغلاقاً."""
        self.cycle([tender("مشروع أ")])
        with self.db._get_connection() as conn:
            conn.execute("INSERT INTO master_tenders (tender_id, title, owner, submission_date, status) "
                         "VALUES ('DEMO-001', 'منافسة عرض', 'جهة خيالية', ?, 'InProgress')", (FUTURE,))
            conn.commit()
        for _ in range(12):
            self.cycle([tender("مشروع أ")])
        self.assertEqual(self.master("منافسة عرض")["status"], "InProgress")
        self.assertEqual(self.pending("DELETED"), [])

    def test_tender_expired_normally_stays_quiet_closed(self):
        self.cycle([tender("مشروع أ"), tender("انتهى موعدها", date=PAST)])
        for _ in range(3):
            self.cycle([tender("مشروع أ")])
        self.assertEqual(len(self.pending("CLOSED")), 1)
        self.assertEqual(self.pending("DELETED"), [])

    def test_mass_disappearance_is_treated_as_portal_glitch(self):
        rows = [tender(f"مشروع {i}", date=FUTURE) for i in range(6)]
        self.cycle(rows)
        for _ in range(12):
            self.cycle(rows[:1])        # 5 من 6 اختفت فجأة → خلل تصدير وليس حذفاً
        self.assertEqual(self.pending("DELETED"), [])
        self.assertEqual(self.q("SELECT COUNT(*) n FROM master_tenders WHERE status='CLOSED'")[0]["n"], 0)

    def test_future_deadline_waits_longer_before_closing(self):
        self.cycle([tender("مشروع أ"), tender("مشروع مستقبلي", date=FUTURE)])
        for _ in range(5):
            self.cycle([tender("مشروع أ")])
        self.assertNotEqual(self.master("مشروع مستقبلي")["status"], "CLOSED")


if __name__ == "__main__":
    unittest.main()
