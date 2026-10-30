"""لوحة المهام — المرحلة 3: تقييم الإدارة للمهام المنتهية + بطاقات أداء المهندسين (/team).
التقييمات للإدارة فقط. (أسماء منافسات وهمية ومهندسو النور.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from db_manager import DBManager

import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 20)


def add_task(conn, tender, engineer, due, done_at=None) -> int:
    cur = conn.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer, status, due_date, done_at) "
                       "VALUES (?,?,?,?,?,?)", (tender, "مهمة تجريبية", engineer, "done" if done_at else "todo",
                                                due, done_at or ""))
    return cur.lastrowid


class RatingAndScorecardTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        tasks_core.ensure_tables(self.conn)
        self.conn.execute("CREATE TABLE tender_results (id INTEGER PRIMARY KEY, tender_id TEXT, assigned_engineer TEXT, "
                          "result TEXT, updated_at TEXT)")
        self.tender = add_tender(self.conn, "S-1", "إنشاء مدرسة نموذجية بحي الورود", "2026-11-30", "سعود")

    def tearDown(self):
        self.conn.close()

    def test_rate_validates_and_upserts(self):
        open_task = add_task(self.conn, self.tender, "سعود", "2026-10-25")
        done = add_task(self.conn, self.tender, "سعود", "2026-10-10", "2026-10-09")
        with self.assertRaises(ValueError):
            tasks_core.rate(self.conn, open_task, 4, 4, "", "الإدارة")          # غير منتهية
        with self.assertRaises(ValueError):
            tasks_core.rate(self.conn, done, 6, 4, "", "الإدارة")
        with self.assertRaises(ValueError):
            tasks_core.rate(self.conn, done, None, 4, "", "الإدارة")
        with self.assertRaises(LookupError):
            tasks_core.rate(self.conn, 99999, 4, 4, "", "الإدارة")
        tasks_core.rate(self.conn, done, 3, 4, "جيد", "الإدارة")
        tasks_core.rate(self.conn, done, 5, 5, "ممتاز بعد المراجعة", "الإدارة")
        self.assertEqual(tuple(self.conn.execute("SELECT quality, commitment, note FROM task_ratings").fetchall()[0]),
                         (5, 5, "ممتاز بعد المراجعة"))

    def test_scorecards_period_on_time_quality_top_late_won(self):
        a = add_task(self.conn, self.tender, "سعود", "2026-10-10", "2026-10-09")    # في الموعد
        b = add_task(self.conn, self.tender, "سعود", "2026-10-05", "2026-10-07")    # متأخرة
        add_task(self.conn, self.tender, "سعود", "2026-09-01", "2026-09-01")        # خارج «هذا الشهر»
        c = add_task(self.conn, self.tender, "تسنيم", "2026-10-15", "2026-10-15")
        add_task(self.conn, self.tender, "تسنيم", "2026-10-18")                    # متأخرة الآن
        tasks_core.rate(self.conn, a, 4, 5, "", "الإدارة")
        tasks_core.rate(self.conn, b, 3, 2, "", "الإدارة")
        tasks_core.rate(self.conn, c, 5, 5, "", "الإدارة")
        self.conn.execute("INSERT INTO tender_results (tender_id, assigned_engineer, result, updated_at) "
                          "VALUES ('S-1', 'سعود', 'won', '2026-10-12 10:00:00')")

        sc = tasks_core.scorecards(self.conn, "month", TODAY)
        e = {x["name"]: x for x in sc["engineers"]}
        self.assertEqual((e["سعود"]["done"], e["سعود"]["on_time"], e["سعود"]["quality"], e["سعود"]["won"]),
                         (2, 50, 3.5, 1))
        self.assertEqual(e["سعود"]["load"], 1)
        self.assertEqual((e["تسنيم"]["late"], e["تسنيم"]["quality"], e["تسنيم"]["top"]), (1, 5.0, True))
        self.assertFalse(e["سعود"]["top"])
        self.assertEqual(sc["totals"], {"done": 3, "on_time": 67, "quality": 4.0, "late": 1})
        self.assertEqual(tasks_core.scorecards(self.conn, "year", TODAY)["totals"]["done"], 4)


class DashboardRatingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES ('فيصل')")
            tid = add_tender(c, "S-2", "توريد وتركيب إنارة ممشى الواجهة", "2026-12-20", "فيصل")
            c.commit()
            tasks_core.ensure_tables(c)
            cls.task = add_task(c, tid, "فيصل", "2026-10-01", "2026-09-30")
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban"]

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def client(self, admin: bool):
        cl = self.app.test_client()
        with cl.session_transaction() as s:
            s["ok"] = True
            if admin:
                s["admin_ok"] = True
        return cl

    def test_rating_is_admin_only_and_hidden_from_team(self):
        team, admin = self.client(False), self.client(True)
        body = {"quality": 4, "commitment": 5, "note": "عمل متقن"}
        self.assertEqual(team.post(f"/api/tasks/{self.task}/rating", json=body).status_code, 403)
        self.assertTrue(admin.post(f"/api/tasks/{self.task}/rating", json=body).get_json()["ok"])
        mine = lambda cl: next(t for t in cl.get("/api/tasks").get_json()["tasks"] if t["id"] == self.task)
        self.assertEqual(mine(admin)["rating_quality"], 4)
        self.assertNotIn("rating_quality", mine(team))
        self.assertNotIn('id="rateBox"', team.get("/tasks").get_data(as_text=True))
        acts = lambda cl: [x["action"] for x in cl.get(f"/api/tasks/{self.task}/activity").get_json()["activity"]]
        self.assertIn("rate", acts(admin))
        self.assertNotIn("rate", acts(team))                     # «التقييم: الجودة …» لا يتسرّب عبر سجل النشاط
        self.assertIn('id="rateBox"', admin.get("/tasks").get_data(as_text=True))

    def test_team_page_admin_only(self):
        r = self.client(False).get("/team")
        self.assertEqual((r.status_code, r.headers["Location"].endswith("/admin/login")), (302, True))
        admin = self.client(True)
        self.assertIn("المهندسون والتقييم", admin.get("/team").get_data(as_text=True))
        j = admin.get("/api/team?period=year").get_json()
        self.assertEqual(j["period"], "year")
        self.assertIn("فيصل", [e["name"] for e in j["engineers"]])
        self.assertEqual(admin.get("/api/team?period=bogus").get_json()["period"], "month")

    def test_disabled_instance_hides_team(self):
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.client(True).get("/team").status_code, 404)


if __name__ == "__main__":
    unittest.main()
