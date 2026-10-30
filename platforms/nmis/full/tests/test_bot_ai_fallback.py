"""
الرسائل النصية الحرة في تيليجرام: معالج الأسئلة أولاً، والمساعد الذكي عند عدم الفهم.
(قبل 2026-09-23 كان المساعد الذكي لا يرد على النص أبداً — handle_text_query يلتقط كل الرسائل.)
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


def fake_message(text="سؤال غير مفهوم"):
    return SimpleNamespace(text=text, chat=SimpleNamespace(id=42, type="group"),
                           from_user=SimpleNamespace(id=7))


class AiFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon  # noqa: F401  (يسجّل المعالجات بالترتيب الصحيح)
        import bot_commands
        import bot_voice_ai
        cls.cmd, cls.ai = bot_commands, bot_voice_ai

    def setUp(self):
        patches = [
            mock.patch.object(self.cmd, "is_authorized", return_value=True),
            mock.patch.object(self.cmd.bot, "send_message"),
            mock.patch.object(self.cmd.bot, "send_chat_action"),
            mock.patch.object(self.ai, "reply_with_ai"),
            mock.patch.object(self.ai, "AI_ENABLED", True),
            mock.patch("chat_handler.handle_chat_query", return_value=None),
        ]
        self.mocks = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)
        _, self.send, _, self.ai_reply, _, self.chat = self.mocks

    def test_understood_question_uses_query_handler_only(self):
        self.chat.return_value = "📋 عندنا 22 منافسة"
        self.cmd.handle_text_query(fake_message("كم منافسة عندنا؟"))
        self.send.assert_called_once()
        self.assertIn("22 منافسة", self.send.call_args.args[1])
        self.ai_reply.assert_not_called()

    def test_not_understood_falls_back_to_ai(self):
        msg = fake_message()
        self.cmd.handle_text_query(msg)
        self.ai_reply.assert_called_once_with(msg)
        self.send.assert_not_called()

    def test_ai_disabled_shows_help(self):
        with mock.patch.object(self.ai, "AI_ENABLED", False):
            self.cmd.handle_text_query(fake_message())
        self.ai_reply.assert_not_called()
        self.assertIn("لم أفهم سؤالك", self.send.call_args.args[1])

    def test_ai_failure_shows_help(self):
        self.ai_reply.side_effect = RuntimeError("openai down")
        self.cmd.handle_text_query(fake_message())
        self.assertIn("لم أفهم سؤالك", self.send.call_args.args[1])

    def test_reply_with_ai_sends_text_reply(self):
        mock.patch.stopall()
        with mock.patch.object(self.ai, "_ai_reply", return_value="رد المساعد") as ai_call, \
             mock.patch.object(self.ai.bot, "send_message") as send, \
             mock.patch.object(self.ai.bot, "send_chat_action"):
            self.ai.reply_with_ai(fake_message("مرحبا"))
        ai_call.assert_called_once_with(42, "مرحبا", voice_mode=False)
        send.assert_called_once_with(42, "رد المساعد")


if __name__ == "__main__":
    unittest.main()
