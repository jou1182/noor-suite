"""
طلبات القوائم بالصوت: القائمة نصاً من القاعدة + ملخص صوتي من نفس الاستعلام (2026-09-23).
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import voice_lists as vl
from db_manager import DBManager


def d(days):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


class VoiceListsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_lists_"))
        self.db_path = self.tmp / "tenders.db"
        db = DBManager(self.db_path)
        with db._get_connection() as c:
            c.execute("DELETE FROM engineers")
            c.executemany("INSERT INTO engineers (name, is_active) VALUES (?, 1)", [("المعمري",), ("وسيم",)])
            c.executemany(
                "INSERT INTO master_tenders (tender_id, title, owner, submission_date, assigned_engineer, status) VALUES (?,?,?,?,?,?)",
                [("A", "صيانة الشوارع بقطاع وسط الرياض (الجزء الأول)", "أمانة الرياض", d(1), "المعمري", "InProgress"),
                 ("B", "Grading *Works* _PAGA_", "مطار الملك سلمان", d(3), "وسيم", "InProgress"),
                 ("C", "خط مياه وادي حنيفة", "الدرعية", d(20), "المعمري", "InProgress"),
                 ("D", "مشروع مغلق", "أمانة جدة", d(2), "وسيم", "CLOSED")])
            c.commit()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detects_list_requests_only(self):
        for q in ("اديني أسماء المنافسات اللي موجودة حالياً", "قولي أسامي المشاريع", "اذكر المنافسات اللي بتخلص بكرة"):
            self.assertTrue(vl.is_list_request(q), q)
        for q in ("كم منافسة عندنا؟", "المعمري معاه كام منافسة؟", "اديني أسماء المهندسين"):
            self.assertFalse(vl.is_list_request(q), q)

    def test_all_active_sorted_and_closed_excluded(self):
        lst = vl.build_list("اديني أسماء المنافسات", self.db_path)
        self.assertEqual([i["title"][:5] for i in lst["items"]], ["صيانة", "Gradi", "خط مي"])
        self.assertIsNone(lst["eng"]); self.assertIsNone(lst["window_label"])

    def test_engineer_and_window_filters(self):
        self.assertEqual(len(vl.build_list("أسماء منافسات المعمري", self.db_path)["items"]), 2)
        self.assertEqual(len(vl.build_list("أسماء المنافسات اللي بتخلص بكرة", self.db_path)["items"]), 1)
        self.assertEqual(len(vl.build_list("أسماء المنافسات اللي بتخلص الأسبوع ده", self.db_path)["items"]), 2)

    def test_alhin_means_now_not_today(self):
        lst = vl.build_list("وش أسماء المنافسات الحين؟", self.db_path)
        self.assertEqual(len(lst["items"]), 3)

    def test_summary_count_matches_text_list(self):
        lst = vl.build_list("اديني أسماء المنافسات", self.db_path)
        text = "\n".join(vl.format_text(lst))
        self.assertIn(": 3", text.splitlines()[0])
        self.assertIn("Grading *Works* _PAGA_", text)        # نص خام بلا Markdown
        summary = vl.voice_summary(lst)
        self.assertIn("عندنا 3 منافسات نشطة", summary)
        self.assertIn("صيانة الشوارع بقطاع وسط الرياض", summary)   # الأقرب، مختصر قبل القوس
        self.assertNotIn("(", summary)

    def test_arabic_count_agreement(self):
        self.assertEqual(vl._count_phrase(1), "منافسة واحدة")
        self.assertEqual(vl._count_phrase(2), "منافستين")
        self.assertEqual(vl._count_phrase(4), "4 منافسات")
        self.assertEqual(vl._count_phrase(22), "22 منافسة")

    def test_empty_and_single_wording(self):
        empty = {"items": [], "eng": None, "window_label": "غداً"}
        self.assertEqual(vl.voice_summary(empty), "مفيش منافسات بتخلص بكرة.")
        one = vl.build_list("أسماء المنافسات اللي بتخلص بكرة", self.db_path)
        self.assertIn("منافسة واحدة", vl.voice_summary(one))
        self.assertIn("تفاصيلها", vl.voice_summary(one))

    def test_long_lists_are_chunked_under_telegram_limit(self):
        items = [{"title": "مشروع " * 30, "owner": "جهة", "date": datetime.now() + timedelta(days=5), "eng": "وسيم"}] * 60
        chunks = vl.format_text({"items": items, "eng": None, "window_label": None})
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 4096 for c in chunks))
        self.assertEqual(sum(c.count("\n🏢") + c.count("   🏢") for c in chunks) >= 60, True)


class SendVoiceListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon  # noqa: F401
        import bot_voice_ai
        cls.v = bot_voice_ai

    def test_sends_text_then_voice_and_saves_history(self):
        lst = {"items": [{"title": "مشروع أ", "owner": "جهة", "date": datetime.now() + timedelta(days=2), "eng": "وسيم"}],
               "eng": None, "window_label": None}
        calls = []
        with mock.patch.object(self.v.voice_lists, "build_list", return_value=lst), \
             mock.patch.object(self.v.bot, "send_message", side_effect=lambda *a, **k: calls.append(("text", a[1]))), \
             mock.patch.object(self.v.bot, "send_voice", side_effect=lambda *a, **k: calls.append(("voice", None))), \
             mock.patch.object(self.v, "_ai_speak", return_value=b"OGG"), \
             mock.patch.object(self.v, "_history_load", return_value=[]), \
             mock.patch.object(self.v, "_history_save") as saved, \
             mock.patch.dict(self.v._ai_history, {}, clear=True):
            self.v._send_voice_list(55, "اديني أسماء المنافسات")
            hist = list(self.v._ai_history[55])
        self.assertEqual([c[0] for c in calls], ["text", "voice"])
        self.assertIn("مشروع أ", calls[0][1])
        self.assertEqual([h["role"] for h in hist], ["user", "assistant"])
        self.assertEqual(saved.call_count, 2)


if __name__ == "__main__":
    unittest.main()
