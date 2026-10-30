"""مظهر الشركة (skin): يُحمَّل فقط لمن ضبط "skin" في هويته (النور)، والنور بلا أي إضافة.
+ بوابة المهندسين تحسب المتبقي لتواريخ الإدخال اليدوي DD/MM/YYYY (كانت تُهمل في النور)."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from db_manager import DBManager

PAGES = ("/login", "/", "/results", "/engineer-view", "/owners", "/admin", "/engineer")


class SkinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import web_core
        import web_dashboard
        cls.wc, cls.app = web_core, web_dashboard.app
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()
        due = (date.today() + timedelta(days=9)).strftime("%d/%m/%Y")
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES ('سعود')")
            c.execute("INSERT OR IGNORE INTO master_tenders (tender_id, title, owner, submission_date, status, "
                      "assigned_engineer) VALUES ('SK-1', 'تشجير ممر المشاة (تجريبي)', 'بلدية تجريبية', ?, "
                      "'InProgress', 'سعود')", (due,))
            c.commit()

    def setUp(self):
        self._orig = self.wc.PROFILE.get("skin")
        self.client = self.app.test_client()
        with self.client.session_transaction() as s:
            s["ok"] = True
            s["admin_ok"] = True

    def tearDown(self):
        self.wc.PROFILE["skin"] = self._orig

    def get(self, url):
        return self.client.get(url, environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_data(as_text=True)

    def test_no_skin_adds_nothing(self):
        self.wc.PROFILE["skin"] = ""
        for url in PAGES:
            with self.subTest(url=url):
                html = self.get(url)
                self.assertNotIn("مظهر النور", html)
                self.assertNotIn("noor-theme", html)                 # لا زر وضع داكن للنور
                self.assertNotIn("family=Tajawal:wght@400;500;700;800;900", html)

    def test_noor_skin_on_every_page(self):
        self.wc.PROFILE["skin"] = "noor"
        for url in PAGES:
            with self.subTest(url=url):
                html = self.get(url)
                self.assertIn("مظهر النور", html)                    # CSS المضمّن
                self.assertLess(html.index("مظهر النور"), html.index("</head>"))
                # الوضع يُضبط قبل رسم الصفحة (لا وميض أبيض) + زر التبديل
                self.assertLess(html.index('setAttribute("data-theme"'), html.index("مظهر النور"))
                self.assertIn('shell.className = "noor-shell"', html)          # الجرس + زر الوضع
                self.assertIn('t=t==="dark"?"dark":"light"', html)                 # الفاتح افتراضي

    def test_engineer_view_days_left_for_manual_dates(self):
        self.assertRegex(self.get("/engineer-view"), r"\b9 يوم")


if __name__ == "__main__":
    unittest.main()
