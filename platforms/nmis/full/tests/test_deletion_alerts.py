"""
تنبيه حذف منافسة من المنصة قبل موعدها (2026-09-24).
الخلل الأصلي: الحذف كان يصل كسطر "ℹ️ للعلم: تم إغلاق المناقصة" مثل الإغلاق العادي فضاع.
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from db_manager import DBManager

FUTURE = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")


class DeletionAlertTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon  # noqa: F401
        import bot_callbacks
        import bot_deletions
        import bot_notifications
        cls.dl, cls.nt, cls.cb = bot_deletions, bot_notifications, bot_callbacks

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noor_tests_del_"))
        self.db = DBManager(self.tmp / "tenders.db")
        self._orig = (self.dl.db, self.nt.db)
        self.dl.db = self.nt.db = self.db
        self.sent, self.pinned, self.voices, self.edits, self.unpinned = [], [], [], [], []
        bot = self.dl.bot
        counter = iter(range(500, 600))
        patches = [
            mock.patch.object(bot, "send_message", side_effect=lambda cid, text, **k: (
                self.sent.append((cid, text, k)), SimpleNamespace(message_id=next(counter)))[1]),
            mock.patch.object(bot, "pin_chat_message", side_effect=lambda cid, mid, **k: self.pinned.append(mid)),
            mock.patch.object(bot, "unpin_chat_message", side_effect=lambda cid, mid: self.unpinned.append(mid)),
            mock.patch.object(bot, "send_voice", side_effect=lambda cid, buf, **k: self.voices.append(k)),
            mock.patch.object(bot, "edit_message_text", side_effect=lambda text, *a, **k: self.edits.append(text)),
            mock.patch.object(bot, "answer_callback_query"),
            mock.patch("bot_voice_ai._ai_speak", return_value=b"OGG"),
            mock.patch("bot_notifications._notify_engineer"),
            mock.patch.object(self.dl, "OWNER_TELEGRAM_IDS", {"777"}),
        ]
        for p in patches:
            p.start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.dl.db, self.nt.db = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stage_deleted(self, title="إعادة تأهيل الخزان الاستراتيجي <بجدة>", eng="العنتري"):
        self.db.add_pending_change(
            tender_id="AUTO-x", title=title, change_type="DELETED", submission_date=FUTURE,
            details_json=json.dumps({"owner": "القوات البحرية", "engineer": eng, "submission_date": FUTURE}),
            suggested_eng=eng)

    def alerts(self):
        with self.db._get_connection() as c:
            self.dl.ensure_table(c)
            return [dict(r) for r in c.execute("SELECT * FROM deletion_alerts")]

    def test_deleted_change_triggers_loud_pinned_voice_alert(self):
        self.stage_deleted()
        self.nt.notify_pending_changes()
        group = [m for m in self.sent if m[0] == self.dl.CHAT_ID]
        self.assertEqual(len(group), 1)
        text, kw = group[0][1], group[0][2]
        self.assertIn("🚨", text)
        self.assertIn("اتحذفت من المنصة", text)
        self.assertIn("&lt;بجدة&gt;", text)                 # HTML مُهرَّب — لا يرفضه تيليجرام
        self.assertIn("العنتري", text)
        self.assertIn("قبل موعدها بـ7 أيام", text)
        self.assertEqual(kw["parse_mode"], "HTML")
        self.assertEqual(self.pinned, [500])                  # مثبّتة أعلى المجموعة
        self.assertEqual(len(self.voices), 1)                 # رسالة صوتية ردّاً عليها
        self.assertEqual(self.voices[0]["reply_to_message_id"], 500)
        self.nt._notify_engineer.assert_called_once()        # المهندس المسؤول
        self.assertEqual([m for m in self.sent if m[0] == "777"].__len__(), 1)   # المالك
        with self.db._get_connection() as c:
            self.assertEqual(c.execute("SELECT status FROM pending_changes").fetchone()[0], "APPROVED")
        self.assertEqual(self.alerts()[0]["chat_message_id"], 500)

    def test_normal_closure_stays_a_quiet_line(self):
        self.db.add_pending_change(tender_id="AUTO-y", title="انتهى موعدها", change_type="CLOSED")
        self.nt.notify_pending_changes()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("للعلم", self.sent[0][1])
        self.assertEqual(self.pinned, [])
        self.assertEqual(self.alerts(), [])

    def test_failed_group_message_is_retried_next_cycle(self):
        self.stage_deleted()
        with mock.patch.object(self.dl.bot, "send_message", side_effect=RuntimeError("telegram down")):
            self.nt.notify_pending_changes()
        with self.db._get_connection() as c:
            self.assertEqual(c.execute("SELECT status FROM pending_changes").fetchone()[0], "PENDING_APPROVAL")
        self.assertEqual(self.alerts(), [])          # لا سجل يتيم → لا تكرار في التذكير عند إعادة المحاولة
        self.nt.notify_pending_changes()              # الدورة التالية: تيليجرام عاد
        self.assertEqual(len(self.alerts()), 1)

    def test_ack_button_records_who_unpins_and_stops_reminders(self):
        self.stage_deleted()
        self.nt.notify_pending_changes()
        alert_id = self.alerts()[0]["id"]
        self.assertEqual(self.dl.send_reminders(), 1)
        call = SimpleNamespace(id="c1", data=f"delack_{alert_id}",
                               from_user=SimpleNamespace(first_name="يوسف", last_name="سليم", username=None, id=1),
                               message=SimpleNamespace(message_id=500, chat=SimpleNamespace(id=self.dl.CHAT_ID),
                                                       html_text="🚨 تنبيه"))
        with mock.patch.object(self.cb, "is_authorized", return_value=True):
            self.cb.handle_deletion_ack(call)
        self.assertEqual(self.alerts()[0]["acked_by"], "يوسف سليم")
        self.assertIn(500, self.unpinned)
        self.assertIn("تم الاطلاع وإيقاف العمل", self.edits[-1])
        self.assertEqual(self.dl.send_reminders(), 0)

    def test_deleted_command_lists_alerts_and_older_deletions(self):
        self.stage_deleted(title="منافسة حديثة")
        self.nt.notify_pending_changes()
        with self.db._get_connection() as c:     # حُذفت قبل التحديث: مغلقة وموعدها بعد تاريخ إغلاقها
            c.execute("INSERT INTO master_tenders (tender_id, title, submission_date, assigned_engineer, status, updated_at) "
                      "VALUES ('OLD', 'منافسة قديمة', ?, 'البحيري', 'CLOSED', datetime('now','-3 days'))", (FUTURE,))
            c.commit()
        text = self.dl.recent_deletions_text()
        self.assertIn("منافسة حديثة", text)
        self.assertIn("لم يؤكد أحد الاطلاع", text)
        self.assertIn("منافسة قديمة", text)
        self.assertIn("قبل تفعيل التنبيه العاجل", text)


if __name__ == "__main__":
    unittest.main()
