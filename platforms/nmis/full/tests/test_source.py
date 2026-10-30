"""مصدر المنافسات للإدخال اليدوي: قراءة وتحقق الإكسل، المعاينة (جديدة/تغيّر موعدها/ستُحذف/ستُغلق/أخطاء)،
التطبيق بنسخة احتياطية، روابط Google، والصفحة للإدارة وفقط لنسخ portal_adapter: manual. (بيانات وهمية.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import io
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from openpyxl import Workbook

import source_core as sc
import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 1)


def xlsx(rows, header=sc.REQUIRED_COLUMNS) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class SourceCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        add_tender(self.conn, "900001", "تأهيل ممر مشاة (تجريبي)", "20/10/2026")          # سيبقى بلا تغيير
        add_tender(self.conn, "900002", "إنارة ساحة (تجريبي)", "25/10/2026")              # سيتغير موعده
        add_tender(self.conn, "900003", "صيانة سور (تجريبي)", "30/10/2026")              # سيختفي قبل موعده
        add_tender(self.conn, "900004", "تشجير قديم (تجريبي)", "01/09/2026")              # سيختفي بعد موعده
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_read_rejects_bad_files(self):
        with self.assertRaises(ValueError):
            sc.read_rows(b"not excel")
        with self.assertRaisesRegex(ValueError, "أعمدة ناقصة"):
            sc.read_rows(xlsx([["1", "x"]], header=["رقم المنافسة", "اسم المنافسة"]))

    def test_preview_classifies_every_case(self):
        data = xlsx([
            ["900001", "تأهيل ممر مشاة (تجريبي)", "جهة تجريبية", "20/10/2026", "إنشاءات", "البنية التحتية"],
            ["900002", "إنارة ساحة (تجريبي)", "جهة تجريبية", "28/10/2026", "توريد", "الطاقة"],
            [900005, "مدرسة جديدة (تجريبي)", "جهة تعليمية", date(2026, 11, 20), "إنشاءات", "المباني"],
            ["900006", "", "جهة", "01/12/2026", "", ""],
            ["900007", "تاريخ خاطئ (تجريبي)", "جهة", "قريباً", "", ""],
            ["900001", "مكرر (تجريبي)", "جهة", "20/10/2026", "", ""],
        ])
        p = sc.preview(self.conn, data, TODAY)
        self.assertEqual(p["unchanged"], 1)
        self.assertEqual([c["id"] for c in p["changed"]], ["900002"])
        self.assertEqual(sorted(n["id"] for n in p["new"]), ["900005", "900007"])     # الرقم كعدد + التاريخ كخلية تاريخ
        self.assertEqual([d["id"] for d in p["will_delete"]], ["900003"])              # قبل موعده ← تنبيه أحمر
        self.assertEqual([d["id"] for d in p["will_close"]], ["900004"])
        self.assertEqual(sorted(e["row"] for e in p["errors"]), [5, 6, 7])

    def test_apply_keeps_backup_and_rejects_invalid(self):
        d = Path(tempfile.mkdtemp(prefix="noor_tests_src_"))
        target, hist = d / "tenders.xlsx", d / "history"
        first = xlsx([["1", "أ (تجريبي)", "ج", "01/12/2026", "", ""]])
        self.assertIsNone(sc.apply(first, target, hist))
        second = xlsx([["2", "ب (تجريبي)", "ج", "02/12/2026", "", ""]])
        backup = sc.apply(second, target, hist)
        self.assertEqual(backup.read_bytes(), first)
        self.assertEqual(target.read_bytes(), second)
        with self.assertRaises(ValueError):
            sc.apply(b"junk", target, hist)
        self.assertEqual(target.read_bytes(), second)                                   # لم يُمس

    def test_google_links(self):
        self.assertEqual(sc.direct_url("https://docs.google.com/spreadsheets/d/AbC-12_x/edit#gid=0"),
                         "https://docs.google.com/spreadsheets/d/AbC-12_x/export?format=xlsx")
        self.assertEqual(sc.direct_url("https://drive.google.com/file/d/Zz9/view?usp=sharing"),
                         "https://drive.google.com/uc?export=download&id=Zz9")
        for bad in ("http://docs.google.com/spreadsheets/d/x", "https://evil.example/spreadsheets/d/x", "https://drive.google.com/"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                sc.direct_url(bad)

    def test_auto_sync_only_when_enabled_and_changed(self):
        data = xlsx([["1", "أ (تجريبي)", "ج", "01/12/2026", "", ""]])
        sc.set_cfg(self.conn, sc.CFG_URL, "https://docs.google.com/spreadsheets/d/x/edit")
        with mock.patch.object(sc, "fetch_url", return_value=data), mock.patch.object(sc, "apply") as ap:
            self.assertEqual(sc.auto_sync(self.conn), "")                               # غير مفعّلة
            sc.set_cfg(self.conn, sc.CFG_AUTO, "1")
            self.assertTrue(sc.auto_sync(self.conn))
            self.assertEqual(sc.auto_sync(self.conn), "")                               # نفس المحتوى
        self.assertEqual(ap.call_count, 1)


class SourcePageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db_manager import DBManager
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        cls.cp, cls.app = company_profile, web_dashboard.app
        web_dashboard.ensure_app_config_table()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("portal_adapter")
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_srcweb_"))
        self.patches = [mock.patch.object(sc, "MANUAL_FILE", self.tmp / "tenders.xlsx"),
                        mock.patch.object(sc, "HISTORY_DIR", self.tmp / "history"),
                        mock.patch.object(sc, "PENDING_DIR", self.tmp / "pending")]
        for p in self.patches:
            p.start()
        self.admin = self.app.test_client()
        with self.admin.session_transaction() as s:
            s["admin_ok"] = True

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.cp.PROFILE["portal_adapter"] = self._orig

    def test_only_for_manual_instances_and_admins(self):
        self.cp.PROFILE["portal_adapter"] = "noor"
        self.assertEqual(self.admin.get("/admin/source").status_code, 404)
        self.cp.PROFILE["portal_adapter"] = "manual"
        self.assertEqual(self.app.test_client().get("/admin/source").status_code, 302)
        self.assertIn("مصدر المنافسات", self.admin.get("/admin/source").get_data(as_text=True))
        self.assertEqual(self.admin.get("/admin/source/template.xlsx").status_code, 200)

    def test_upload_preview_then_apply(self):
        self.cp.PROFILE["portal_adapter"] = "manual"
        data = xlsx([["777001", "منافسة مرفوعة (تجريبية)", "جهة تجريبية", "15/12/2026", "إنشاءات", "المباني"]])
        r = self.admin.post("/admin/source/preview", data={"file": (io.BytesIO(data), "t.xlsx")},
                            content_type="multipart/form-data").get_json()
        self.assertTrue(r["ok"])
        self.assertIn("777001", [n["id"] for n in r["new"]])
        self.assertFalse(sc.MANUAL_FILE.exists())                                        # المعاينة لا تكتب
        self.assertTrue(self.admin.post("/admin/source/apply", json={"token": r["token"]}).get_json()["ok"])
        self.assertEqual(sc.MANUAL_FILE.read_bytes(), data)
        self.assertEqual(self.admin.post("/admin/source/apply", json={"token": r["token"]}).status_code, 404)
        bad = self.admin.post("/admin/source/settings", json={"url": "https://evil.example/x"})
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
