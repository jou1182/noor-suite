"""حساب العرض للطلاب (web_viewer): يرى كل الشاشات، لا يغيّر شيئاً (الحماية في الخادم)، لا يرى الحساس،
ولا يرث أحد صلاحيات الإدارة التي منحها العرض. مع features: demo فقط."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

import tasks_core


class ViewerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_auth
        import web_core
        import web_dashboard
        cls.cp, cls.app, cls.wa, cls.wc = company_profile, web_dashboard.app, web_auth, web_core
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            tasks_core.ensure_tables(c)
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban", "engineer_accounts", "demo", "calendar", "analytics"]
        self.wc._LOGIN_FAILS.clear()
        self.admin = self.app.test_client()
        with self.admin.session_transaction() as s:
            s["admin_ok"] = True
        self.password = self.admin.post("/admin/demo/viewer", json={}).get_json()["password"]

    def tearDown(self):
        self.admin.post("/admin/demo/viewer", json={"action": "disable"})
        self.cp.PROFILE["features"] = self._orig
        self.wc._LOGIN_FAILS.clear()

    def viewer(self):
        v = self.app.test_client()
        r = v.post("/viewer", data={"password": self.password})
        self.assertEqual(r.status_code, 302)
        return v

    def test_sees_every_screen_with_banner(self):
        v = self.viewer()
        for path in ("/", "/tasks", "/calendar", "/analytics", "/team", "/admin", "/admin/demo",
                     "/admin/task-templates", "/admin/engineers", "/api/tasks", "/team/report.pdf"):
            with self.subTest(path=path):
                self.assertEqual(v.get(path).status_code, 200)
        page = v.get("/tasks").get_data(as_text=True)
        self.assertIn("حساب عرض", page)
        self.assertNotIn(self.wc.ADMIN_EMAIL, v.get("/admin").get_data(as_text=True))

    def test_nothing_can_change(self):
        v = self.viewer()
        for path, body in (("/api/tasks", {"title": "x"}), ("/admin/save-identity", None), ("/admin/demo/seed", None),
                           ("/admin/demo/viewer", {}), ("/api/task-templates", {"rows": []}),
                           ("/admin/change-password", None), ("/api/notifications/read", {})):
            with self.subTest(path=path):
                r = v.post(path, json=body) if body is not None else v.post(path, data={"x": "1"})
                self.assertEqual(r.status_code, 403)
                self.assertIn("للمشاهدة فقط", r.get_json()["msg"])

    def test_sensitive_reads_are_blocked(self):
        v = self.viewer()
        for path in ("/admin/db-backup", "/admin/knowledge", "/admin/knowledge/read?name=x", "/admin/forgot", "/forgot"):
            with self.subTest(path=path):
                self.assertEqual(v.get(path).status_code, 403)

    def test_real_login_after_viewer_starts_clean(self):
        v = self.viewer()
        v.post("/login", data={"password": self.wa.DASH_PWD})
        with v.session_transaction() as s:
            self.assertTrue(s.get("ok"))
            self.assertFalse(s.get("admin_ok"))                     # الفريق لا يرث إدارة العرض
            self.assertFalse(s.get("viewer"))

    def test_password_rotation_disable_and_gating(self):
        bad = self.app.test_client().post("/viewer", data={"password": "wrong"})
        self.assertIn("غير صحيحة", bad.get_data(as_text=True))
        old = self.password
        self.password = self.admin.post("/admin/demo/viewer", json={}).get_json()["password"]
        self.assertNotEqual(old, self.password)
        self.assertEqual(self.app.test_client().post("/viewer", data={"password": old}).status_code, 200)   # القديمة بطلت
        self.viewer()
        self.admin.post("/admin/demo/viewer", json={"action": "disable"})
        self.assertEqual(self.app.test_client().get("/viewer").status_code, 404)
        self.cp.PROFILE["features"] = ["kanban"]
        self.assertEqual(self.admin.post("/admin/demo/viewer", json={}).status_code, 404)
        team = self.app.test_client()
        with team.session_transaction() as s:
            s["ok"] = True
        self.assertEqual(team.post("/admin/demo/viewer", json={}).status_code, 302)                        # الإدارة فقط


if __name__ == "__main__":
    unittest.main()
