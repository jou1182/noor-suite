"""أرشفة ملف المنصة فقط عند تغيّر المحتوى (كان يُؤرشف كل 5 دقائق: ~43 ألف ملف متطابق)."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import io
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import openpyxl

import export_in_progress as ex


def xlsx_bytes(rows, created):
    wb = openpyxl.Workbook()
    wb.properties.created = created  # ملفات المنصة تختلف بايتياً في كل تنزيل
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["اسم المنافسة", "المالك", "تاريخ التقديم"]
ROWS = [HEADER, ["مشروع أ", "أمانة الرياض", "2026-10-01"]]


class ArchiveIfChangedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_archive_"))
        self._orig = (ex.ARCHIVE_DIR, ex.LAST_SIG_FILE)
        ex.ARCHIVE_DIR = self.tmp
        ex.LAST_SIG_FILE = self.tmp / ".last_content_signature"

    def tearDown(self):
        ex.ARCHIVE_DIR, ex.LAST_SIG_FILE = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def archived(self):
        return sorted(p.name for p in self.tmp.glob("in_progress_tenders_*.xlsx"))

    def test_first_download_is_archived(self):
        self.assertIsNotNone(ex.archive_if_changed(xlsx_bytes(ROWS, datetime(2026, 1, 1)), "t1"))
        self.assertEqual(self.archived(), ["in_progress_tenders_t1.xlsx"])

    def test_same_content_different_bytes_is_not_archived(self):
        a, b = xlsx_bytes(ROWS, datetime(2026, 1, 1)), xlsx_bytes(ROWS, datetime(2026, 1, 2))
        self.assertNotEqual(a, b)
        ex.archive_if_changed(a, "t1")
        self.assertIsNone(ex.archive_if_changed(b, "t2"))
        self.assertEqual(self.archived(), ["in_progress_tenders_t1.xlsx"])

    def test_changed_content_is_archived(self):
        ex.archive_if_changed(xlsx_bytes(ROWS, datetime(2026, 1, 1)), "t1")
        changed = ROWS + [["مشروع ب", "وزارة الدفاع", "2026-11-01"]]
        self.assertIsNotNone(ex.archive_if_changed(xlsx_bytes(changed, datetime(2026, 1, 1)), "t2"))
        self.assertEqual(len(self.archived()), 2)

    def test_unreadable_file_is_archived_for_safety(self):
        ex.archive_if_changed(xlsx_bytes(ROWS, datetime(2026, 1, 1)), "t1")
        self.assertIsNotNone(ex.archive_if_changed(b"not an excel file", "t2"))
        self.assertEqual(len(self.archived()), 2)
        # بصمة آخر ملف سليم تبقى — ملف سليم مطابق بعده لا يُؤرشف
        self.assertIsNone(ex.archive_if_changed(xlsx_bytes(ROWS, datetime(2026, 1, 3)), "t3"))


if __name__ == "__main__":
    unittest.main()
