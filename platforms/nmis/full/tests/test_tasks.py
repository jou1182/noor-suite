"""لوحة المهام (كانبان): تُحجب بدون ميزة kanban، وCRUD والتحقق والنقل وسجل النشاط تعمل."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from db_manager import DBManager


class TasksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp = company_profile
        cls.app = web_dashboard.app
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES ('منى')")
            c.execute("INSERT OR IGNORE INTO master_tenders (tender_id, title, owner, submission_date, status) "
                      "VALUES ('T-KAN-1', 'صيانة مبنى الإدارة', 'أمانة الرياض', '2026-10-30', 'InProgress')")
            c.commit()
            cls.tid = c.execute("SELECT id FROM master_tenders WHERE tender_id='T-KAN-1'").fetchone()[0]

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban"]
        self.client = self.app.test_client()
        with self.client.session_transaction() as s:
            s["ok"] = True

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def create(self, **kw):
        body = {"tender_row_id": self.tid, "title": "التسعير", **kw}
        return self.client.post("/api/tasks", json=body)

    def test_hidden_when_feature_off(self):
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.client.get("/tasks").status_code, 404)
        self.assertEqual(self.client.get("/api/tasks").status_code, 404)
        self.assertNotIn("/tasks", self.client.get("/results").get_data(as_text=True))

    def test_requires_login(self):
        self.assertEqual(self.app.test_client().get("/tasks").status_code, 302)

    def test_page_renders_with_sidebar(self):
        html = self.client.get("/tasks").get_data(as_text=True)
        self.assertIn("لوحة المهام", html)
        self.assertIn('id="nsbMenu"', html)
        self.assertIn(f"\"id\": {self.tid}", html)   # المنافسات تُمرَّر للواجهة (tojson)

    def test_create_validates(self):
        self.assertEqual(self.create(title="  ").status_code, 400)
        self.assertEqual(self.create(tender_row_id=999999).status_code, 400)
        self.assertEqual(self.create(engineer="غير موجود").status_code, 400)
        self.assertEqual(self.create(due_date="30/10/2026").status_code, 400)
        self.assertEqual(self.create(start_date="2026-10-10", due_date="2026-10-01").status_code, 400)
        self.assertEqual(self.create(priority="urgent").status_code, 400)

    def test_crud_move_and_activity(self):
        r = self.create(engineer="منى", priority="high", due_date="2026-10-20")
        self.assertEqual(r.status_code, 200, r.get_json())
        t = r.get_json()["task"]
        self.assertEqual((t["status"], t["engineer"], t["tender_title"]), ("todo", "منى", "صيانة مبنى الإدارة"))

        r = self.client.post(f"/api/tasks/{t['id']}", json={"notes": "بانتظار جدول الكميات", "status": "done"})
        self.assertEqual(r.get_json()["task"]["status"], "todo")          # الحالة لا تتغير إلا عبر move
        self.assertEqual(r.get_json()["task"]["notes"], "بانتظار جدول الكميات")

        r = self.client.post(f"/api/tasks/{t['id']}/move", json={"status": "done"})
        self.assertTrue(r.get_json()["task"]["done_at"])
        r = self.client.post(f"/api/tasks/{t['id']}/move", json={"status": "doing"})
        self.assertEqual(r.get_json()["task"]["done_at"], "")
        self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/move", json={"status": "x"}).status_code, 400)

        acts = [a["action"] for a in self.client.get(f"/api/tasks/{t['id']}/activity").get_json()["activity"]]
        self.assertEqual(acts, ["move", "move", "edit", "assign", "create"])

        self.assertTrue(self.client.post(f"/api/tasks/{t['id']}/delete").get_json()["ok"])
        self.assertEqual(self.client.post(f"/api/tasks/{t['id']}/delete").status_code, 404)

    def test_move_reorders_column(self):
        ids = [self.create(title=f"م{i}").get_json()["task"]["id"] for i in range(3)]
        self.client.post(f"/api/tasks/{ids[2]}/move", json={"status": "todo", "position": 0})
        got = [t["id"] for t in self.client.get("/api/tasks").get_json()["tasks"] if t["id"] in ids]
        self.assertEqual(got, [ids[2], ids[0], ids[1]])
        for i in ids:
            self.client.post(f"/api/tasks/{i}/delete")

    def test_filter_by_engineer(self):
        a = self.create(engineer="منى").get_json()["task"]["id"]
        b = self.create().get_json()["task"]["id"]
        got = {t["id"] for t in self.client.get("/api/tasks?engineer=منى").get_json()["tasks"]}
        self.assertIn(a, got)
        self.assertNotIn(b, got)
        for i in (a, b):
            self.client.post(f"/api/tasks/{i}/delete")


if __name__ == "__main__":
    unittest.main()
