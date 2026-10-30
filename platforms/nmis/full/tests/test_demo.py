"""وضع العرض (demo_core / web_demo): ملء متسق ومترابط، إعادة الملء بلا تكرار، المسح لا يلمس الحقيقي،
ولا شيء منه يصل تليجرام أو يُعتبر «محذوفاً» من ملف المصدر. الصفحة للإدارة وفقط مع features: demo."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import analytics_core
import demo_core
import source_core
import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 1)


class DemoCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        # fresh_db يبني نسخة مختصرة من جداول اللوحة؛ العرض يملأ أعمدتها الكاملة كما على السيرفر
        self.conn.executescript("DROP TABLE tender_guarantees; DROP TABLE tender_notes;")
        self.real = add_tender(self.conn, "900001", "منافسة حقيقية (تجريبية)", "20/10/2026", "أحمد")
        tasks_core.refresh(self.conn, TODAY)
        self.real_tasks = self.conn.execute("SELECT COUNT(*) FROM tender_tasks").fetchone()[0]
        self.conn.commit()
        self.counts = demo_core.seed(self.conn, TODAY)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()[0]

    def test_seed_fills_every_screen(self):
        self.assertEqual(self.counts["tenders"], len(demo_core.CATALOG))
        statuses = {r[0] for r in self.conn.execute("SELECT t.status FROM tender_tasks t JOIN master_tenders m "
                                                    "ON m.id=t.tender_row_id WHERE m.tender_id LIKE 'DEMO-%'")}
        self.assertEqual(statuses, {"todo", "doing", "done"})
        self.assertGreater(self.counts["ratings"], 20)
        late = tasks_core.overdue_by_engineer(self.conn, TODAY)            # يصل تليجرام ← بلا عرض
        self.assertEqual(late, {})
        overdue_on_board = self.one("SELECT COUNT(*) FROM tender_tasks WHERE status<>'done' AND due_date<?",
                                    TODAY.isoformat())
        self.assertGreater(overdue_on_board, 0)                               # لكن اللوحة تُظهر المتأخر
        self.assertEqual(self.one("SELECT COUNT(*) FROM tender_tasks WHERE engineer=''"), 0)   # كل مهمة لمهندس
        rep = analytics_core.report(self.conn, "all", TODAY)
        self.assertGreaterEqual(rep["kpis"]["won"], 5)
        self.assertEqual(rep["risk"][0]["owner"], demo_core.COAST)            # الجهة التي ألغت مرتين
        self.assertTrue(rep["waste"]["available"])
        bell = tasks_core.notifications(self.conn, "admin", today=TODAY)
        self.assertTrue(0 < bell["unread"] < 99)                               # حيّ لكن ليس ضجيجاً
        self.assertTrue(all(i["at"][:10] <= TODAY.isoformat() for i in bell["items"]))

    def test_no_template_reseed_and_no_assignment_notices(self):
        """البوت يجهّز قوالب المنافسات النشطة ويرسل إشعار إسناد — منافسات العرض مجهّزة سلفاً."""
        self.assertEqual(tasks_core.refresh(self.conn, TODAY), [])

    def real_positions(self):
        return [tuple(r) for r in self.conn.execute(
            "SELECT t.id, t.status, t.position FROM tender_tasks t JOIN master_tenders m ON m.id=t.tender_row_id "
            "WHERE m.tender_id='900001' ORDER BY t.id")]

    def test_real_tasks_keep_their_board_order(self):
        real = self.real_positions()
        demo_core.seed(self.conn, TODAY)
        self.assertEqual(self.real_positions(), real)
        first_demo = self.one("SELECT MIN(position) FROM tender_tasks t JOIN master_tenders m ON m.id=t.tender_row_id "
                              "WHERE m.tender_id LIKE 'DEMO-%' AND t.status='todo'")
        self.assertGreater(first_demo, max(p for _, st, p in real if st == "todo"))

    def test_reseed_replaces_and_clear_keeps_real_data(self):
        demo_core.seed(self.conn, TODAY)
        self.assertEqual(self.one("SELECT COUNT(*) FROM master_tenders WHERE tender_id LIKE 'DEMO-%'"),
                         len(demo_core.CATALOG))
        self.assertEqual(demo_core.clear(self.conn), len(demo_core.CATALOG))
        self.assertEqual(self.one("SELECT COUNT(*) FROM master_tenders"), 1)
        self.assertEqual(self.one("SELECT COUNT(*) FROM tender_tasks"), self.real_tasks)
        self.assertEqual(self.one("SELECT COUNT(*) FROM task_activity WHERE task_id NOT IN (SELECT id FROM tender_tasks)"), 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM task_ratings"), 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM tender_results"), 0)
        self.assertFalse(demo_core.status(self.conn)["active"])

    def test_nightly_refresh_only_when_on_and_demo_present(self):
        later = TODAY + timedelta(days=5)
        self.assertIsNone(demo_core.nightly_refresh(self.conn, later))                     # غير مفعّل
        demo_core.set_cfg(self.conn, demo_core.CFG_NIGHTLY, "1")
        real_before = self.one("SELECT COUNT(*) FROM tender_tasks t JOIN master_tenders m ON m.id=t.tender_row_id "
                               "WHERE m.tender_id='900001'")
        self.conn.execute("UPDATE tender_tasks SET status='done' WHERE tender_row_id IN "
                          "(SELECT id FROM master_tenders WHERE tender_id='DEMO-001')")      # «حُرّك في المحاضرة»
        self.assertEqual(demo_core.nightly_refresh(self.conn, later)["tenders"], len(demo_core.CATALOG))
        d = self.conn.execute("SELECT submission_date FROM master_tenders WHERE tender_id='DEMO-001'").fetchone()[0]
        self.assertEqual(d, (later + timedelta(days=demo_core.CATALOG[0][4])).strftime("%d/%m/%Y"))   # تاريخ اليوم الجديد
        self.assertNotEqual(self.one("SELECT COUNT(*) FROM tender_tasks t JOIN master_tenders m ON m.id=t.tender_row_id "
                                     "WHERE m.tender_id='DEMO-001' AND t.status<>'done'"), 0)            # رجع كما كان
        self.assertEqual(self.one("SELECT COUNT(*) FROM tender_tasks t JOIN master_tenders m ON m.id=t.tender_row_id "
                                  "WHERE m.tender_id='900001'"), real_before)
        self.assertTrue(demo_core.status(self.conn)["last_refresh"])
        demo_core.clear(self.conn)
        self.assertIsNone(demo_core.nightly_refresh(self.conn, later))                      # لا عرض = لا شيء

    def test_source_preview_ignores_demo(self):
        from tests.test_source import xlsx
        p = source_core.preview(self.conn, xlsx([["900001", "منافسة حقيقية (تجريبية)", "جهة تجريبية",
                                                   "20/10/2026", "", ""]]), TODAY)
        self.assertEqual(p["will_delete"], [])
        self.assertEqual(p["will_close"], [])

    def test_needs_engineers(self):
        self.conn.execute("UPDATE engineers SET is_active=0")
        with self.assertRaisesRegex(ValueError, "مهندس"):
            demo_core.seed(self.conn, TODAY)

    def test_dates_follow_instance_format(self):
        d = self.conn.execute("SELECT submission_date FROM master_tenders WHERE tender_id='DEMO-001'").fetchone()[0]
        self.assertEqual(d, (TODAY + timedelta(days=demo_core.CATALOG[0][4])).strftime("%d/%m/%Y"))


class DemoPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app
        web_dashboard.ensure_app_config_table()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES ('مهندس العرض')")
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.admin = self.app.test_client()
        with self.admin.session_transaction() as s:
            s["admin_ok"] = True

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            demo_core.clear(c)
            c.commit()

    def test_gated_by_feature_and_admin(self):
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.admin.get("/admin/demo").status_code, 404)
        self.assertEqual(self.admin.post("/admin/demo/seed").status_code, 404)
        self.cp.PROFILE["features"] = ["kanban", "demo"]
        self.assertEqual(self.app.test_client().get("/admin/demo").status_code, 302)
        self.assertEqual(self.app.test_client().post("/admin/demo/seed").status_code, 302)
        self.assertIn("وضع العرض", self.admin.get("/admin/demo").get_data(as_text=True))

    def test_seed_backs_up_then_clear(self):
        self.cp.PROFILE["features"] = ["kanban", "demo"]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(demo_core, "backup",
                                                                   return_value=Path(d) / "b.db") as bk:
            r = self.admin.post("/admin/demo/seed").get_json()
        bk.assert_called_once()
        self.assertTrue(r["ok"])
        self.assertEqual(r["tenders"], len(demo_core.CATALOG))
        self.assertIn("بيانات العرض موجودة", self.admin.get("/admin/demo").get_data(as_text=True))
        self.assertEqual(self.admin.post("/admin/demo/clear").get_json()["tenders"], len(demo_core.CATALOG))

    def test_nightly_toggle_and_bot_job(self):
        self.cp.PROFILE["features"] = ["kanban", "demo"]
        self.assertTrue(self.admin.post("/admin/demo/nightly", json={"on": True}).get_json()["on"])
        self.assertIn('id="nightly" checked', self.admin.get("/admin/demo").get_data(as_text=True))
        self.admin.post("/admin/demo/seed")
        import bot_jobs
        with mock.patch("bot_tasks._push_board_refresh") as push:
            bot_jobs.job_demo_nightly()
        push.assert_called_once()
        self.assertIn("آخر تجديد", self.admin.get("/admin/demo").get_data(as_text=True))
        self.assertFalse(self.admin.post("/admin/demo/nightly", json={"on": False}).get_json()["on"])
        team = self.app.test_client()
        with team.session_transaction() as s:
            s["ok"] = True
        self.assertEqual(team.post("/admin/demo/nightly", json={"on": True}).status_code, 302)

    def test_backup_is_a_full_copy(self):
        d = Path(tempfile.mkdtemp(prefix="noor_tests_demo_"))
        db = d / "x.db"
        with closing(sqlite3.connect(db)) as c:
            c.execute("CREATE TABLE t (v)")
            c.execute("INSERT INTO t VALUES (7)")
            c.commit()
        b = demo_core.backup(db)
        with closing(sqlite3.connect(b)) as c:
            self.assertEqual(c.execute("SELECT v FROM t").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()
