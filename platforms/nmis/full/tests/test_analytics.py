"""صفحة التحليلات (/analytics): المؤشرات والفترات، الأسبوعان القادمان، الخط الزمني، الأعلى فوزاً،
مخاطرة الجهات، الجهد المهدور، المقارنة — ببيانات وهمية ومهندسي النور."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from db_manager import DBManager

import analytics_core as ac
import tasks_core
from tests.test_tasks_phase2 import fresh_db

TODAY = date(2026, 9, 25)


def seed(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS tender_results (id INTEGER PRIMARY KEY, tender_id TEXT, title TEXT, owner TEXT, "
                 "assigned_engineer TEXT, did_submit INTEGER DEFAULT 0, result TEXT DEFAULT 'pending', "
                 "our_price REAL, winning_price REAL, updated_at TEXT)")
    conn.execute("DROP TABLE IF EXISTS tender_guarantees")
    conn.execute("CREATE TABLE tender_guarantees (tender_row_id INTEGER PRIMARY KEY, due_date TEXT, status TEXT)")
    for n in ("سعود", "تسنيم", "فيصل"):
        conn.execute("INSERT OR IGNORE INTO engineers (name, capacity) VALUES (?, 5)", (n,))
    conn.execute("UPDATE engineers SET is_active=0 WHERE name NOT IN ('سعود','تسنيم','فيصل')")   # مهندسو النور فقط
    rows = [  # key, owner, deadline, engineer, status, business, submitted, result, our, win
        ("A1", "بلدية الواحة (تجريبية)", "2026-03-10", "سعود", "CLOSED", "إنشاءات", 1, "won", 100, 100),
        ("A2", "بلدية الواحة (تجريبية)", "2026-04-12", "سعود", "CLOSED", "إنشاءات", 1, "won", 95, 100),
        ("A3", "بلدية الواحة (تجريبية)", "15/05/2026", "تسنيم", "CLOSED", "تشغيل وصيانة", 1, "lost", 110, 100),
        ("B1", "هيئة المياه (تجريبية)", "2026-03-01", "فيصل", "DELETED", "إنشاءات", 0, None, None, None),
        ("B2", "هيئة المياه (تجريبية)", "2026-06-01", "فيصل", "CLOSED", "إنشاءات", 1, "lost", 120, 100),
        ("B3", "هيئة المياه (تجريبية)", "2026-07-01", "تسنيم", "CLOSED", "تشغيل وصيانة", 0, "cancelled", None, None),
        ("C1", "جهة تعليمية (تجريبية)", (TODAY + timedelta(days=3)).isoformat(), "سعود", "InProgress", "إنشاءات", 0, None, None, None),
        ("C2", "جهة تعليمية (تجريبية)", (TODAY + timedelta(days=3)).strftime("%d/%m/%Y"), "سعود", "InProgress", "توريد", 0, None, None, None),
        ("C3", "جهة تعليمية (تجريبية)", (TODAY + timedelta(days=9)).isoformat(), "تسنيم", "InProgress", "توريد", 0, None, None, None),
        ("P1", "بلدية الواحة (تجريبية)", "2025-03-01", "سعود", "CLOSED", "إنشاءات", 1, "lost", None, None),
    ]
    ids = {}
    for k, owner, d, eng, st, bt, sub, res, our, win in rows:
        conn.execute("INSERT INTO master_tenders (tender_id, title, owner, submission_date, assigned_engineer, status, "
                     "business_type, sector) VALUES (?,?,?,?,?,?,?,?)", (k, f"منافسة {k} (تجريبية)", owner, d, eng, st, bt, "البنية التحتية"))
        ids[k] = conn.execute("SELECT id FROM master_tenders WHERE tender_id=?", (k,)).fetchone()[0]
        if sub or res:
            conn.execute("INSERT INTO tender_results (tender_id, owner, did_submit, result, our_price, winning_price) "
                         "VALUES (?,?,?,?,?,?)", (k, owner, sub, res, our, win))
    conn.execute("INSERT INTO tender_guarantees VALUES (?, ?, 'PENDING')", (ids["C1"], (TODAY + timedelta(days=2)).isoformat()))
    conn.execute("INSERT INTO tender_guarantees VALUES (?, ?, 'READY')", (ids["C3"], (TODAY + timedelta(days=4)).isoformat()))
    tasks_core.ensure_tables(conn)
    for _ in range(3):
        conn.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer, status) VALUES (?, 'تسعير', 'فيصل', 'done')", (ids["B1"],))
    conn.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer, status) VALUES (?, 'دراسة', 'تسنيم', 'todo')", (ids["B3"],))
    conn.commit()
    return ids


class AnalyticsCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        self.ids = seed(self.conn)
        self.r = ac.report(self.conn, "year", TODAY)

    def tearDown(self):
        self.conn.close()

    def test_kpis_year_and_manual_date_format(self):
        k = self.r["kpis"]
        self.assertEqual((k["total"], k["running"], k["closing_week"]), (9, 3, 2))   # C2 بصيغة DD/MM محسوبة
        self.assertEqual((k["submitted"], k["won"], k["win_rate"]), (4, 2, 50))
        self.assertEqual((k["cancelled"], k["cancel_rate"]), (2, 22))
        self.assertEqual((k["total_prev"], k["total_delta"]), (1, 800))
        self.assertEqual((k["guarantees14"], k["guarantee_next_days"]), (1, 2))    # الجاهز لا يُحسب

    def test_period_month_limits_to_since_first_of_month(self):
        k = ac.report(self.conn, "month", TODAY)["kpis"]
        self.assertEqual(k["total"], 3)
        self.assertEqual(ac.report(self.conn, "all", TODAY)["kpis"]["total"], 10)

    def test_two_weeks_peak_carriers_and_suggestion(self):
        tw = self.r["two_weeks"]
        self.assertEqual(len(tw["days"]), 14)
        self.assertEqual((tw["peak"]["closing"], tw["closing_total"]), (2, 3))
        self.assertEqual(tw["carriers"], [{"name": "سعود", "count": 2}])
        self.assertIn("فيصل", tw["suggestion"])                                       # الأخف حملاً (0/5)
        self.assertEqual(sum(d["guarantees"] for d in tw["days"]), 1)

    def test_timeline_busiest_and_previous_year(self):
        t = self.r["timeline"]
        self.assertEqual(t["submitted"][2:6], [1, 1, 1, 1])
        self.assertEqual(t["won"][2:4], [1, 1])
        self.assertTrue(t["has_prev"])
        self.assertEqual(t["busiest"], "مارس")

    def test_top_owners_by_rate_with_insight(self):
        rows = self.r["top_owners"]["rows"]
        self.assertEqual([(r["owner"], r["rate"]) for r in rows],
                         [("بلدية الواحة (تجريبية)", 67), ("هيئة المياه (تجريبية)", 0)])

    def test_owner_risk_levels(self):
        risk = {r["owner"]: (r["rate"], r["level"]) for r in self.r["risk"]}
        self.assertEqual(risk["هيئة المياه (تجريبية)"], (67, "high"))
        self.assertEqual(risk["بلدية الواحة (تجريبية)"], (0, "low"))
        self.assertEqual(ac.owner_risk_level(ac.load_tenders(self.conn), "هيئة المياه (تجريبية)"), "high")

    def test_wasted_effort_counts_done_tasks_on_cancelled(self):
        w = self.r["waste"]
        self.assertEqual((w["tasks"], w["engineers"], w["tenders"]), (3, 1, 1))
        self.assertIn("هيئة المياه", w["insight"])

    def test_compare_price_gap(self):
        c = ac.compare(ac.load_tenders(self.conn), "بلدية الواحة (تجريبية)", "هيئة المياه (تجريبية)")
        self.assertEqual((c["a"]["win_rate"], c["a"]["price_gap"]), (50, 1.7))     # (0 − 5 + 10) ÷ 3؛ 2025 ضمن التاريخ الكامل
        self.assertEqual((c["b"]["cancel_rate"], c["b"]["price_gap"]), (67, 20.0))


class AnalyticsWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO master_tenders (tender_id, title, owner, submission_date, status) "
                      "VALUES ('W-1', 'منافسة للتحليلات (تجريبية)', 'جهة تجريبية للتحليل', '2026-11-01', 'DELETED')")
            c.execute("INSERT OR IGNORE INTO master_tenders (tender_id, title, owner, submission_date, status) "
                      "VALUES ('W-2', 'منافسة ثانية (تجريبية)', 'جهة تجريبية للتحليل', '2026-11-05', 'InProgress')")
            cls.tid = c.execute("SELECT id FROM master_tenders WHERE tender_id='W-2'").fetchone()[0]
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.client = self.app.test_client()
        with self.client.session_transaction() as s:
            s["ok"] = True

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def test_gated_by_feature(self):
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.client.get("/analytics").status_code, 404)
        self.assertEqual(self.client.get("/api/analytics").status_code, 404)
        self.assertNotIn("مخاطرة", self.client.get(f"/tender/{self.tid}").get_data(as_text=True).split("الجهة المالكة")[1][:400])

    def test_page_api_export_and_risk_badge(self):
        self.cp.PROFILE["features"] = ["kanban", "analytics"]
        self.assertIn("التحليلات", self.client.get("/analytics").get_data(as_text=True))
        j = self.client.get("/api/analytics?period=all").get_json()
        self.assertEqual(j["period"], "all")
        self.assertEqual(set(j) >= {"kpis", "two_weeks", "timeline", "top_owners", "dist", "risk", "waste", "owners"}, True)
        self.assertEqual(self.client.get("/api/analytics?period=bogus").get_json()["period"], "year")
        csv = self.client.get("/analytics/export.csv?period=all")
        self.assertIn("text/csv", csv.content_type)
        self.assertIn("مخاطرة الجهات", csv.get_data(as_text=True))
        page = self.client.get(f"/tender/{self.tid}").get_data(as_text=True)
        self.assertIn('class="risk-high"', page)                                   # 1 من 2 محذوفة = 50%


if __name__ == "__main__":
    unittest.main()
