"""التقرير الشهري العام (pdf_report): تقرير أول الشهر عن الشهر المنتهي لا الذي بدأ لتوّه، والمواعيد
القادمة تفهم صيغتي التاريخ (DD/MM/YYYY للإدارة اليدوية)، ولا بيانات «وضع العرض» ولا المحذوفة. بيانات وهمية."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import sqlite3
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta
from unittest import mock

import pdf_report
from tests.test_tasks_phase2 import add_tender, fresh_db


class OldMonthlyReportTest(unittest.TestCase):
    def setUp(self):
        self.db = fresh_db()
        today = date.today()
        dm = lambda n: (today + timedelta(days=n)).strftime("%d/%m/%Y")
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("CREATE TABLE IF NOT EXISTS tender_results (id INTEGER PRIMARY KEY, tender_id TEXT, result TEXT,"
                      " recorded_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            add_tender(c, "M-1", "منافسة بصيغة يدوية (تجريبية)", dm(10), "أحمد")
            add_tender(c, "M-2", "منافسة بصيغة النور (تجريبية)", (today + timedelta(days=5)).isoformat(), "أحمد")
            add_tender(c, "M-3", "بعيدة (تجريبية)", dm(45), "أحمد")
            add_tender(c, "M-4", "ألغتها الجهة (تجريبية)", dm(3), "أحمد", "DELETED")
            add_tender(c, "DEMO-001", "منافسة عرض", dm(2), "أحمد")
            c.execute("INSERT INTO tender_results (tender_id, result) VALUES ('DEMO-001', 'won'), ('M-2', 'won')")
            c.commit()
        self.p = mock.patch.object(pdf_report, "DB_PATH", self.db)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def data(self):
        start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return pdf_report._get_report_data(start, (start + timedelta(days=32)).replace(day=1))

    def test_upcoming_understands_both_date_formats(self):
        titles = [u["title"] for u in self.data()["upcoming"]]
        self.assertEqual(titles, ["منافسة بصيغة النور (تجريبية)", "منافسة بصيغة يدوية (تجريبية)"])   # بالترتيب، بلا بعيدة/محذوفة/عرض

    def test_counts_skip_demo_and_deleted(self):
        d = self.data()
        self.assertEqual(d["active"], 3)
        self.assertEqual(d["won"], 1)

    def test_first_of_month_reports_the_month_that_ended(self):
        self.assertEqual(pdf_report.previous_month_start(datetime(2026, 10, 1, 9)), datetime(2026, 9, 1))
        self.assertEqual(pdf_report.previous_month_start(datetime(2027, 1, 1, 9)), datetime(2026, 12, 1))
        import bot_jobs
        with mock.patch.object(bot_jobs, "_send_pdf") as send:
            bot_jobs.job_monthly_report(datetime(2026, 9, 1))
        self.assertEqual(send.call_args.args[2], datetime(2026, 9, 1))

    def test_pdf_builds_with_manual_dates(self):
        self.assertTrue(pdf_report.generate_pdf(datetime(2026, 9, 1)).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
