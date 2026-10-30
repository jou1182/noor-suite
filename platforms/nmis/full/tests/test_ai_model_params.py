"""
بارامترات طلبات المساعد الذكي (gpt-6-luna منذ 2026-09-23):
- temperature لا يُرسل (النموذج يرفضه مع التفكير — HTTP 400)
- النص: reasoning_effort من AI_REASONING_EFFORT، الصوت والتلخيص: none
- gpt-4o (للرجوع عبر .env) لا يُرسل له reasoning_effort
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import unittest
from types import SimpleNamespace
from unittest import mock

import ai_assistant as ai


def fake_response(text="رد"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class AiModelParamsTest(unittest.TestCase):
    def setUp(self):
        self.create = mock.MagicMock(return_value=fake_response())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))
        for p in (
            mock.patch.object(ai, "_ai_client", client),
            mock.patch.object(ai, "AI_ENABLED", True),
            mock.patch.object(ai, "AI_MODEL", "gpt-6-luna"),
            mock.patch.object(ai, "_REASONING_MODEL", True),
            mock.patch.object(ai, "AI_REASONING_EFFORT", "low"),
            mock.patch.object(ai, "_history_load", return_value=[]),   # لا يلمس ai_history.db الحقيقية
            mock.patch.object(ai, "_history_save"),
            mock.patch.object(ai, "_ai_live_context", return_value=""),
            mock.patch.dict(ai._ai_history, {}, clear=True),
        ):
            p.start()
        self.addCleanup(mock.patch.stopall)

    def kwargs(self):
        return self.create.call_args.kwargs

    def test_text_reply_uses_configured_effort_and_no_temperature(self):
        self.assertEqual(ai._ai_reply(1, "سؤال"), "رد")
        kw = self.kwargs()
        self.assertEqual(kw["model"], "gpt-6-luna")
        self.assertEqual(kw["reasoning_effort"], "low")
        self.assertNotIn("temperature", kw)

    def test_voice_reply_does_not_think(self):
        ai._ai_reply(2, "سؤال", voice_mode=True)
        kw = self.kwargs()
        self.assertEqual(kw["reasoning_effort"], "none")
        self.assertEqual(kw["max_completion_tokens"], 300)

    def test_legacy_model_gets_no_reasoning_effort(self):
        with mock.patch.object(ai, "AI_MODEL", "gpt-4o"), mock.patch.object(ai, "_REASONING_MODEL", False):
            ai._ai_reply(3, "سؤال")
        self.assertNotIn("reasoning_effort", self.kwargs())


if __name__ == "__main__":
    unittest.main()
