"""تقرير الأداء الشهري PDF: الأرقام نفسها التي في /team لفترة الشهر، صفحة لكل مهندس له نشاط،
الشعار من الشركة لا المضمّن، ويُرسل أول الشهر لتليجرام الإدارة فقط (لا المجموعة). بيانات وهمية."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import base64
import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

import performance_report as pr
import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 1)


def pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        tasks_core.ensure_tables(self.conn)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS tender_results (id INTEGER PRIMARY KEY, tender_id TEXT,
            assigned_engineer TEXT, did_submit INTEGER, result TEXT, updated_at TEXT)""")
        for n in ("يوسف", "فاطمه"):
            self.conn.execute("INSERT OR IGNORE INTO engineers (name) VALUES (?)", (n,))
        tid = add_tender(self.conn, "P-1", "تأهيل ممشى (تجريبي)", "20/09/2026", "يوسف")
        rows = [("دراسة", "يوسف", "done", "2026-09-10", "2026-09-09", 5, 5),      # في الموعد
                ("تسعير", "يوسف", "done", "2026-09-12", "2026-09-14", 3, 2),      # متأخرة يومين
                ("معاينة", "يوسف", "done", "2026-09-05", "2026-09-05", None, None),
                ("قديمة", "يوسف", "done", "2026-08-01", "2026-08-02", 4, 4),      # خارج الشهر
                ("رفع", "فاطمه", "todo", "2026-09-28", "", None, None)]            # متأخرة الآن
        for title, eng, st, due, done_at, q, c in rows:
            t = self.conn.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer, status, due_date, done_at) "
                                  "VALUES (?,?,?,?,?,?)", (tid, title, eng, st, due, done_at)).lastrowid
            if q:
                self.conn.execute("INSERT INTO task_ratings (task_id, quality, commitment, note) VALUES (?,?,?,?)",
                                  (t, q, c, "ممتاز" if q == 5 else ""))
        self.conn.execute("INSERT INTO tender_results (tender_id, assigned_engineer, did_submit, result, updated_at) "
                          "VALUES ('P-1', 'يوسف', 1, 'won', '2026-09-25 10:00:00')")
        self.conn.commit()
        self.data = pr.collect(self.conn, date(2026, 9, 1), TODAY)

    def tearDown(self):
        self.conn.close()

    def eng(self, name):
        return next(c for c in self.data["engineers"] if c["name"] == name)

    def test_month_numbers_match_team_page(self):
        y = self.eng("يوسف")
        self.assertEqual((self.data["from"], self.data["to"]), ("2026-09-01", "2026-09-30"))
        self.assertEqual((y["done"], y["on_time"], y["quality"], y["commitment"], y["won"]), (3, 67, 4.0, 3.5, 1))
        self.assertEqual([t["late_by"] for t in y["tasks"]], [0, -1, 2])
        self.assertEqual([n["title"] for n in y["notes"]], ["دراسة"])
        f = self.eng("فاطمه")
        self.assertEqual([(t["title"], t["days"]) for t in f["late_tasks"]], [("رفع", 3)])
        self.assertEqual((self.data["results"]["won"], self.data["closing"]), (1, 1))
        self.assertTrue(any("يحتاج متابعة" in h and "فاطمه" in h for h in self.data["highlights"]))
        self.assertTrue(any("بلا تقييم" in h for h in self.data["highlights"]))

    def test_pdf_has_team_page_plus_one_per_active_engineer(self):
        active = sum(1 for c in self.data["engineers"] if c["done"] or c["late"] or c["open"])
        pdf = pr.build_pdf(self.data, {"name_ar": "شركة تجريبية"})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(pages(pdf), 1 + active)

    def test_month_helpers(self):
        self.assertEqual(pr.previous_month(date(2027, 1, 1)), date(2026, 12, 1))
        self.assertEqual(pr.month_bounds(date(2026, 10, 1), date(2026, 10, 12)), (date(2026, 10, 1), date(2026, 10, 12)))

    def test_logo_is_the_company_one_never_the_builtin(self):
        with mock.patch("instance_paths.LOGO_FILE", None):
            self.assertIsNone(pr.logo_bytes(self.conn))
        self.conn.execute("CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute("INSERT INTO app_config VALUES ('custom_logo_b64', ?)", (base64.b64encode(b"PNGDATA").decode(),))
        self.assertEqual(pr.logo_bytes(self.conn), b"PNGDATA")


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        import bot_tasks
        self.bt = bot_tasks
        self.bot = mock.Mock()
        self.patches = [mock.patch.object(bot_tasks, "bot", self.bot), mock.patch.object(bot_tasks, "enabled", lambda: True),
                        mock.patch.object(bot_tasks, "_conn", lambda: closing(tasks_core.connect(fresh_db())))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_first_of_month_to_management_only(self):
        with mock.patch.object(self.bt, "OWNER_TELEGRAM_IDS", {"111", "222"}), mock.patch.object(self.bt, "CHAT_ID", "-999"):
            self.bt.job_performance_report(date(2026, 10, 2))
            self.assertEqual(self.bot.send_document.call_count, 0)                 # ليس أول الشهر
            self.bt.job_performance_report(date(2026, 10, 1))
        chats = sorted(c.args[0] for c in self.bot.send_document.call_args_list)
        self.assertEqual(chats, ["111", "222"])                                    # لا المجموعة
        self.assertIn("سبتمبر 2026", self.bot.send_document.call_args.kwargs["caption"])

    def test_no_owner_means_no_send(self):
        with mock.patch.object(self.bt, "OWNER_TELEGRAM_IDS", set()):
            self.bt.job_performance_report(date(2026, 10, 1))
        self.bot.send_document.assert_not_called()


class DownloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            tasks_core.ensure_tables(c)
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban"]

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def client(self, **sess):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s.update(sess)
        return c

    def test_admin_downloads_pdf(self):
        r = self.client(admin_ok=True).get("/team/report.pdf?month=2026-09")
        self.assertEqual(r.content_type, "application/pdf")
        self.assertIn("Performance_2026-09.pdf", r.headers["Content-Disposition"])
        self.assertIn("تقرير PDF", self.client(admin_ok=True).get("/team").get_data(as_text=True))
        self.assertEqual(self.client(admin_ok=True).get("/team/report.pdf?month=2999-01").status_code, 404)
        self.assertEqual(self.client(ok=True).get("/team/report.pdf").status_code, 302)       # الفريق لا
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.client(admin_ok=True).get("/team/report.pdf").status_code, 404)


if __name__ == "__main__":
    unittest.main()
