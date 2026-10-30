"""اختبار دخان للوحة التحكم: تُستورد وتعمل صفحاتها الأساسية على قاعدة مؤقتة."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import unittest
from pathlib import Path

from db_manager import DBManager


class DashboardSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))  # ينشئ الجداول الأساسية
        import web_dashboard
        cls.wd = web_dashboard
        for ensure in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                       web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            ensure()
        cls.client = web_dashboard.app.test_client()

    def test_uses_temp_database(self):
        self.assertIn("noor_tests_", str(self.wd.DB_PATH))

    def test_login_page_renders(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn("النور", r.get_data(as_text=True))

    def test_home_requires_login(self):
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_all_templates_are_valid_jinja(self):
        import admin_templates
        import dashboard_templates
        for mod in (dashboard_templates, admin_templates):
            for name in [n for n in vars(mod) if n.endswith("_HTML")]:
                with self.subTest(template=name):
                    html = getattr(mod, name)
                    self.assertIn("<html", html.lower())
                    self.wd.app.jinja_env.parse(html)  # يرفع TemplateSyntaxError عند خطأ

    def test_healthz_responds(self):
        self.assertIn(self.client.get("/healthz").status_code, (200, 503))


if __name__ == "__main__":
    unittest.main()
