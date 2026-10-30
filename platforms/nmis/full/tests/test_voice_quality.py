"""
جودة الرد الصوتي (2026-09-23):
1) سياق المساعد: كل المنافسات النشطة بأسمائها الكاملة (كان: 7 أيام فقط ومقصوصة عند 55 حرفاً)
2) كلمات تحويل الصوت: أسماء المهندسين والجهات العربية النشطة من القاعدة
4) نطق الأرقام بالمصري: تلتمية، تلات تلاف، مليونين…
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from db_manager import DBManager

LONG_TITLE = "مشروع احلال واستبدال مفاتيح المحطات الرئيسية وكابلات الجهد المتوسط بالموقع العام والمنطقة الملكية"


class VoiceQualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon  # noqa: F401
        import ai_assistant
        import bot_voice_ai
        cls.ai, cls.v = ai_assistant, bot_voice_ai

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_voice_"))
        self.db = DBManager(self.tmp / "tenders.db")
        with self.db._get_connection() as c:
            c.execute("DELETE FROM engineers")
            for name in ("المعمري", "ناصف"):
                c.execute("INSERT INTO engineers (name) VALUES (?)", (name,))
            rows = [("T1", LONG_TITLE, "الشؤون الخاصة", "2099-01-10", "المعمري", "InProgress"),
                    ("T2", "Grading Works PAGA", "King Salman Airport", "2099-02-01", "ناصف", "InProgress"),
                    ("T3", "مشروع مغلق", "أمانة جدة", "2020-01-01", "ناصف", "CLOSED")]
            c.executemany("INSERT INTO master_tenders (tender_id, title, owner, submission_date, assigned_engineer, status) "
                          "VALUES (?,?,?,?,?,?)", rows)
            c.commit()
        self._orig = (self.ai.db, self.v.db)
        self.ai.db = self.v.db = self.db
        self.v._STT_HINTS_CACHE.update(at=0.0, text="")

    def tearDown(self):
        self.ai.db, self.v.db = self._orig
        self.v._STT_HINTS_CACHE.update(at=0.0, text="")
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 1) live context
    def test_context_lists_all_active_tenders_with_full_titles(self):
        ctx = self.ai._ai_live_context()
        self.assertIn(LONG_TITLE, ctx)                 # كامل، غير مقصوص
        self.assertIn("Grading Works PAGA", ctx)       # بعيدة الموعد لكنها نشطة
        self.assertNotIn("مشروع مغلق", ctx)            # المغلقة لا تظهر
        self.assertIn("المنافسات النشطة: 2", ctx)
        self.assertIn("اليوم ", ctx)                   # اسم اليوم للإجابة عن "بكرة"

    # 2) STT hints
    def test_stt_prompt_has_engineers_and_arabic_owners_only(self):
        p = self.v._stt_prompt()
        self.assertTrue(p.endswith(self.v.WHISPER_DOMAIN_PROMPT))
        dynamic = p[: -len(self.v.WHISPER_DOMAIN_PROMPT)]   # الجزء المأخوذ من القاعدة فقط
        self.assertTrue(dynamic.startswith("المهندسين: "))
        self.assertIn("المعمري", dynamic)
        self.assertIn("ناصف", dynamic)
        self.assertIn("الشؤون الخاصة", dynamic)
        self.assertNotIn("King Salman Airport", dynamic)   # الكلام عربي — الجهات الإنجليزية لا تفيد
        self.assertNotIn("أمانة جدة", dynamic)              # جهة منافسة مغلقة

    # 4) Egyptian numbers
    def test_numbers_are_spoken_egyptian(self):
        from tts_text import _num_to_ar, _tts_prepare
        cases = {300: "تلتمية", 900: "تسعمية", 1996: "ألف وتسعمية وستة وتسعين", 3000: "تلات تلاف",
                 1_000_000: "مليون", 2_500_000: "مليونين وخمسمية ألف", 3: "تلاتة", 22: "اتنين وعشرين"}
        for n, words in cases.items():
            with self.subTest(n=n):
                self.assertEqual(_num_to_ar(n), words)
        self.assertEqual(_tts_prepare("عنده ٣ منافسات"), "عنده تلاتة منافسات")


if __name__ == "__main__":
    unittest.main()
