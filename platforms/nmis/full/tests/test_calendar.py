"""تقويم المواعيد (calendar_core / web_calendar): شبكة الأحد–السبت، صيغتا التاريخ، قاعدة الضمان،
فلتر المهندس (ومفروض على حساب المهندس)، والصفحة فقط مع features: calendar. (بيانات وهمية.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

import calendar_core as cc
import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 12)


class CalendarCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        tasks_core.ensure_tables(self.conn)
        self.conn.executescript("DROP TABLE tender_guarantees; CREATE TABLE tender_guarantees ("
                                "tender_row_id INTEGER PRIMARY KEY, due_date TEXT DEFAULT '', status TEXT DEFAULT 'PENDING')")
        self.a = add_tender(self.conn, "C-1", "تأهيل ممشى (تجريبي)", "20/10/2026", "يوسف")         # DD/MM
        self.b = add_tender(self.conn, "C-2", "إنارة ساحة (تجريبي)", "2026-10-25", "فاطمه")        # ISO
        self.c = add_tender(self.conn, "C-3", "سور ملغى (تجريبي)", "15/10/2026", "يوسف", "DELETED")
        add_tender(self.conn, "C-4", "مرفوضة (تجريبي)", "16/10/2026", "يوسف", "REJECTED")
        self.conn.execute("INSERT INTO tender_guarantees (tender_row_id, due_date, status) VALUES (?, '2026-10-08', 'PENDING')",
                          (self.b,))
        for title, eng, status, due in (("التسعير", "يوسف", "todo", "2026-10-10"),
                                        ("المعاينة", "يوسف", "done", "2026-10-09"),
                                        ("العرض الفني", "فاطمه", "doing", "2026-10-14")):
            self.conn.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer, status, due_date) VALUES (?,?,?,?,?)",
                              (self.a, title, eng, status, due))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def kinds(self, view, day):
        return [(e["kind"], e["state"]) for d in view["days"] if d["date"] == day for e in d["events"]]

    def test_grid_is_sunday_to_saturday(self):
        start, end = cc.grid_range(date(2026, 10, 1))
        self.assertEqual((start, end), (date(2026, 9, 27), date(2026, 10, 31)))
        v = cc.month_view(self.conn, "2026-10", today=TODAY)
        self.assertEqual(len(v["days"]) % 7, 0)
        self.assertEqual((v["label"], v["prev"], v["next"]), ("أكتوبر 2026", "2026-09", "2026-11"))
        self.assertEqual(cc.month_view(self.conn, "2026-12", today=TODAY)["next"], "2027-01")
        self.assertEqual(cc.month_view(self.conn, "junk", today=TODAY)["month"], "2026-10")

    def test_every_kind_on_its_day(self):
        v = cc.month_view(self.conn, "2026-10", today=TODAY)
        self.assertEqual(self.kinds(v, "2026-10-20"), [("deadline", "active")])                 # DD/MM
        self.assertEqual(self.kinds(v, "2026-10-25"), [("deadline", "active")])                 # ISO
        self.assertEqual(self.kinds(v, "2026-10-15"), [("deadline", "deleted"),                 # ألغتها الجهة
                                                       ("guarantee", "pending")])               # ضمان C-1 = الإغلاق − 5
        self.assertEqual(self.kinds(v, "2026-10-08"), [("guarantee", "late")])                  # ضمان يدوي فات
        self.assertEqual(self.kinds(v, "2026-10-10"), [("task", "late")])
        self.assertEqual(self.kinds(v, "2026-10-09"), [("task", "done")])
        self.assertEqual(self.kinds(v, "2026-10-16"), [])                                       # المرفوضة لا تظهر
        s = v["summary"]
        self.assertEqual((s["deadlines"], s["guarantees"], s["tasks"], s["late"]), (2, 2, 2, 2))

    def test_ready_guarantee_disappears(self):
        self.conn.execute("UPDATE tender_guarantees SET status='READY'")
        v = cc.month_view(self.conn, "2026-10", today=TODAY)
        self.assertEqual(self.kinds(v, "2026-10-08"), [])

    def test_engineer_filter(self):
        v = cc.month_view(self.conn, "2026-10", "فاطمه", today=TODAY)
        evs = [e for d in v["days"] for e in d["events"]]
        self.assertEqual(sorted((e["kind"], e["title"]) for e in evs),
                         [("deadline", "إنارة ساحة (تجريبي)"), ("guarantee", "إنارة ساحة (تجريبي)"), ("task", "العرض الفني")])


class CalendarPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import bp_engineer
        import company_profile
        import engineer_accounts as ea
        import web_dashboard
        cls.cp, cls.app, cls.bp = company_profile, web_dashboard.app, bp_engineer
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.row_factory = sqlite3.Row
            for n in ("سعود", "منى"):
                c.execute("INSERT OR IGNORE INTO engineers (name) VALUES (?)", (n,))
            add_tender(c, "CAL-1", "منافسة سعود (تجريبي)", date.today().isoformat(), "سعود")
            add_tender(c, "CAL-2", "منافسة منى (تجريبي)", date.today().isoformat(), "منى")
            temp = ea.issue(c, "سعود")
            ea.change_password(c, "سعود", temp, "Noor-Saud-1", "Noor-Saud-1")
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban", "engineer_accounts", "calendar"]

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def titles(self, client, q=""):
        j = client.get("/api/calendar" + q).get_json()
        return {e["title"] for d in j["days"] for e in d["events"]}

    def test_gated_by_feature_and_login(self):
        self.assertEqual(self.app.test_client().get("/calendar").status_code, 302)
        team = self.app.test_client()
        with team.session_transaction() as s:
            s["ok"] = True
        self.assertIn("التقويم", team.get("/calendar").get_data(as_text=True))
        self.assertTrue({"منافسة سعود (تجريبي)", "منافسة منى (تجريبي)"} <= self.titles(team))
        self.assertNotIn("منافسة منى (تجريبي)", self.titles(team, "?engineer=سعود"))
        self.cp.PROFILE["features"] = ["kanban"]
        self.assertEqual(team.get("/calendar").status_code, 404)
        self.assertEqual(team.get("/api/calendar").status_code, 404)

    def test_engineer_sees_only_his_own(self):
        eng = self.app.test_client()
        eng.post("/engineer", data={"name": "سعود", "pin": "Noor-Saud-1"})
        page = eng.get("/calendar").get_data(as_text=True)
        self.assertIn("مواعيدي", page)
        self.assertNotIn("كل المهندسين", page)
        self.assertEqual(self.titles(eng, "?engineer=منى") & {"منافسة منى (تجريبي)"}, set())   # الفلتر مفروض عليه
        self.assertIn("منافسة سعود (تجريبي)", self.titles(eng))


if __name__ == "__main__":
    unittest.main()
