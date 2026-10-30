"""قوالب المهام القابلة للتعديل: قالب لكل نوع أعمال ← الافتراضي ← المضمّن، مفاتيح المراحل تبقى
(فتتحرك المهام مع مراحل المنافسة)، التحقق، ولا يُمس ما جُهّز سابقاً. الصفحة للإدارة مع kanban فقط."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

import tasks_core as tc
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 1)


def keys_of(conn, tid):
    return [r[0] for r in conn.execute("SELECT template_key FROM tender_tasks WHERE tender_row_id=? ORDER BY id", (tid,))]


class TemplateCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tc.connect(fresh_db())
        tc.ensure_tables(self.conn)

    def tearDown(self):
        self.conn.close()

    def tender(self, key, btype):
        tid = add_tender(self.conn, key, f"منافسة {key} (تجريبية)", "30/10/2026", "أحمد")
        self.conn.execute("UPDATE master_tenders SET business_type=? WHERE id=?", (btype, tid))
        return tid

    def test_fallback_chain(self):
        self.assertEqual(tc.template_for(self.conn, "توريد"), tc.TEMPLATE)                   # لا قوالب محفوظة
        tc.save_template(self.conn, "", [{"key": "study", "title": "دراسة", "days_before": 9, "priority": "high"},
                                         {"title": "اجتماع انطلاق", "days_before": 7}])
        default = tc.template_for(self.conn, "توريد")
        self.assertEqual([r[1] for r in default], ["دراسة", "اجتماع انطلاق"])
        self.assertTrue(default[1][0].startswith("c-"))                                      # مفتاح مخصص ثابت
        tc.save_template(self.conn, " توريد  ", [{"key": "upload", "title": "الرفع", "days_before": 1}])
        self.assertEqual(tc.template_for(self.conn, "توريد"), [("upload", "الرفع", 1, "normal")])
        self.assertEqual(len(tc.template_for(self.conn, "إنشاءات")), 2)                     # نوع آخر = الافتراضي
        tc.delete_template(self.conn, "توريد")
        self.assertEqual(len(tc.template_for(self.conn, "توريد")), 2)
        tc.delete_template(self.conn, "")
        self.assertEqual(tc.template_for(self.conn, "توريد"), tc.TEMPLATE)

    def test_seeding_uses_type_template_and_keeps_stage_sync(self):
        tc.save_template(self.conn, "توريد", [{"key": "study", "title": "مراجعة المواصفات الفنية", "days_before": 6},
                                              {"key": "review", "title": "مراجعة داخلية", "days_before": 2}])
        a, b = self.tender("T-1", "توريد"), self.tender("T-2", "إنشاءات")
        tc.seed_templates(self.conn, TODAY)
        self.assertEqual(keys_of(self.conn, a), ["study", "review"])
        self.assertEqual(len(keys_of(self.conn, b)), len(tc.TEMPLATE))
        self.assertEqual(self.conn.execute("SELECT due_date FROM tender_tasks WHERE tender_row_id=? AND template_key='study'",
                                           (a,)).fetchone()[0], "2026-10-24")
        self.conn.execute("INSERT INTO tender_notes (tender_id, submitted_to_review) VALUES (?, 1)", (a,))
        tc.sync_stages(self.conn)                                                            # المرحلة تحرّك المهمة
        self.assertEqual(self.conn.execute("SELECT status FROM tender_tasks WHERE tender_row_id=? AND template_key='review'",
                                           (a,)).fetchone()[0], "doing")

    def test_existing_tenders_keep_their_tasks(self):
        a = self.tender("T-3", "توريد")
        tc.seed_templates(self.conn, TODAY)
        tc.save_template(self.conn, "توريد", [{"title": "مهمة واحدة", "days_before": 1}])
        tc.seed_templates(self.conn, TODAY)
        self.assertEqual(len(keys_of(self.conn, a)), len(tc.TEMPLATE))

    def test_validation(self):
        for rows, msg in (([], "مهمة واحدة"), ([{"title": " ", "days_before": 1}], "بلا اسم"),
                          ([{"title": "س", "days_before": "x"}], "رقم صحيح"), ([{"title": "س", "days_before": 500}], "من 0"),
                          ([{"key": "upload", "title": "أ", "days_before": 1}, {"key": "upload", "title": "ب", "days_before": 1}], "مكررة"),
                          ([{"title": f"م{i}", "days_before": 1} for i in range(21)], "الحد الأقصى")):
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError, msg):
                tc.save_template(self.conn, "", rows)
        rows = tc.save_template(self.conn, "", [{"key": "evil'; --", "title": "س", "days_before": 0, "priority": "urgent"}])
        self.assertTrue(rows[0]["key"].startswith("c-"))
        self.assertEqual(rows[0]["priority"], "normal")

    def test_overview_lists_types_and_counts(self):
        self.tender("T-4", "توريد")
        self.tender("T-5", "توريد ")
        ov = tc.templates_overview(self.conn)
        self.assertIn("توريد", ov["types"])
        self.assertEqual(ov["active"]["توريد"], 2)
        self.assertEqual(ov["default"], ov["builtin"])


class TemplatePageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban"]
        self.admin = self.app.test_client()
        with self.admin.session_transaction() as s:
            s["admin_ok"] = True

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            tc.ensure_tables(c)
            c.execute("DELETE FROM task_templates")
            c.commit()

    def test_admin_only_and_feature_gated(self):
        team = self.app.test_client()
        with team.session_transaction() as s:
            s["ok"] = True
        self.assertEqual(team.get("/admin/task-templates").status_code, 302)
        self.assertEqual(team.post("/api/task-templates", json={"rows": []}).status_code, 302)
        self.assertIn("قوالب المهام", self.admin.get("/admin/task-templates").get_data(as_text=True))
        self.cp.PROFILE["features"] = []
        self.assertEqual(self.admin.get("/api/task-templates").status_code, 404)

    def test_save_and_reset(self):
        r = self.admin.post("/api/task-templates", json={"business_type": "صيانة", "rows": [
            {"title": "جدول الصيانة الوقائية", "days_before": 5, "priority": "high"}]}).get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(self.admin.get("/api/task-templates").get_json()["saved"]["صيانة"][0]["title"], "جدول الصيانة الوقائية")
        bad = self.admin.post("/api/task-templates", json={"business_type": "صيانة", "rows": []})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.admin.post("/api/task-templates/delete", json={"business_type": "صيانة"}).get_json()["deleted"], 1)


if __name__ == "__main__":
    unittest.main()
