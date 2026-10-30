"""
ترتيب تسجيل معالجات تيليجرام — telebot يجرّب المعالجات بترتيب تسجيلها، والمعالجات
العامة (نص حر/صوت) يجب أن تبقى بعد الأوامر. أي تغيير في الترتيب يجب أن يكون مقصوداً
(حدّث القائمة هنا عندها). اللقطة مأخوذة من bot_daemon.py قبل تقسيمه (2026-09-23).
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import tempfile
import unittest

# (اسم الدالة، الأوامر، أنواع المحتوى، هل لها فلتر func)
EXPECTED_MESSAGE_HANDLERS = [
        ('handle_start', ['help', 'start'], ['text'], False),
        ('handle_subscribe', ['subscribe'], ['text'], False),
        ('handle_unsubscribe', ['unsubscribe'], ['text'], False),
        ('handle_link', ['link'], ['text'], False),   # 2026-09-25: ربط تليجرام بحساب المهندس
        ('handle_mytenders', ['mytenders'], ['text'], False),
        ('handle_mytasks', ['mytasks'], ['text'], False),   # 2026-09-24: لوحة المهام
        ('handle_owner', ['owner'], ['text'], False),
        ('handle_guarantees', ['guarantees'], ['text'], False),
        ('handle_followup', ['followup'], ['text'], False),
        ('handle_find', ['find'], ['text'], False),
        ('handle_approve_all', ['approve_all'], ['text'], False),
        ('handle_automode', ['automode'], ['text'], False),
        ('handle_predict', ['predict'], ['text'], False),
        ('handle_news', ['news'], ['text'], False),
        ('handle_list', ['list'], ['text'], False),
        ('handle_list_details', ['list_d'], ['text'], False),
        ('handle_list_details_hyphen', [], ['text'], True),
        ('handle_pending', ['pending'], ['text'], False),
        ('handle_health', ['health', 'status'], ['text'], False),
        ('handle_stats', ['stats'], ['text'], False),
        ('handle_manual_backup', ['backup'], ['text'], False),
        ('handle_report', ['report'], ['text'], False),
        ('handle_test', ['test'], ['text'], False),
        ('handle_lastlog', ['lastlog'], ['text'], False),
        ('handle_pause', ['pause'], ['text'], False),
        ('handle_resume', ['resume'], ['text'], False),
        ('handle_add_engineer', ['addengineer'], ['text'], False),
        ('handle_deleted', ['deleted'], ['text'], False),   # 2026-09-24: قبل النص الحر
        ('handle_text_query', [], ['text'], True),
        ('handle_document', [], ['document'], False),
        ('handle_ai_reset', ['reset'], ['text'], False),
        ('handle_repeat', ['repeat'], ['text'], False),
        ('handle_voicemode', ['voicemode'], ['text'], False),
        ('handle_voice_select', ['voice'], ['text'], False),
        ('handle_dialect_select', ['dialect'], ['text'], False),
        ('handle_voice_message', [], ['voice'], False),
        ('handle_ai_text', [], ['text'], True),
        ('handle_analytics', ['analytics'], ['text'], False),
        ('handle_trends', ['trends'], ['text'], False),
]

EXPECTED_CALLBACK_HANDLERS = [
        'handle_bulk_approve',
        'handle_approve',
        'handle_sub_pick',
        'handle_guarantee_set',
        'handle_followup_result',
        'handle_guarantee_menu',
        'handle_find_eng_set',
        'handle_find_eng_menu',
        'handle_autoeng_set',
        'handle_autoeng_menu',
        'handle_change_eng',
        'handle_reject',
        'handle_eng_approve',
        'handle_eng_reject',
        'handle_mgr_approve',
        'handle_mgr_reject',
        'handle_deletion_ack',   # 2026-09-24: تأكيد الاطلاع على تنبيه حذف
        'handle_task_button',    # 2026-09-24: أزرار /mytasks
]


class BotHandlerOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")  # لا اتصال بتيليجرام عند الاستيراد
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon
        cls.bot = bot_daemon.bot

    def test_message_handlers_order(self):
        got = []
        for h in self.bot.message_handlers:
            f = h["filters"]
            got.append((h["function"].__name__, sorted(f.get("commands") or []),
                        sorted(f.get("content_types") or []), f.get("func") is not None))
        self.assertEqual(got, [tuple(x) for x in EXPECTED_MESSAGE_HANDLERS])

    def test_callback_handlers_order(self):
        self.assertEqual([h["function"].__name__ for h in self.bot.callback_query_handlers],
                         EXPECTED_CALLBACK_HANDLERS)


if __name__ == "__main__":
    unittest.main()
