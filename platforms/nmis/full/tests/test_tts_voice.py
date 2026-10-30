"""
الرد الصوتي (2026-09-23): Google Chirp3 صوت Kore أولاً، واللهجة المصرية افتراضياً.
- pitch ممنوع (Chirp3 يرفضه بـ 400 — كان سبب فشل كل طلبات Google سابقاً)
- مفتاح Google في الترويسة لا في الرابط (رسائل الخطأ تحوي الرابط وتُسجَّل)
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import base64
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


class TtsVoiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="noor_tests_logs_")
        import bot_daemon  # noqa: F401
        import ai_assistant
        import bot_voice_ai
        cls.v, cls.ai = bot_voice_ai, ai_assistant

    def google_ok(self):
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None,
                               json=lambda: {"audioContent": base64.b64encode(b"OGG").decode()})

    def test_defaults_are_kore_and_egyptian(self):
        self.assertEqual(self.v._GOOGLE_VOICE_MAP[self.v.DEFAULT_TTS_VOICE], "ar-XA-Chirp3-HD-Kore")
        self.assertEqual(self.ai.AI_DEFAULT_DIALECT, "مصري")

    def test_google_request_has_no_pitch_and_key_only_in_header(self):
        with mock.patch.dict(os.environ, {"GOOGLE_TTS_KEY": "AIzaTESTKEY"}), \
             mock.patch("requests.post", return_value=self.google_ok()) as post:
            self.assertEqual(self.v._ai_speak_google("مرحبا", 123), b"OGG")
        url = post.call_args.args[0]
        body = post.call_args.kwargs["json"]
        self.assertNotIn("AIzaTESTKEY", url)
        self.assertEqual(post.call_args.kwargs["headers"]["X-Goog-Api-Key"], "AIzaTESTKEY")
        self.assertNotIn("pitch", body["audioConfig"])
        self.assertEqual(body["voice"]["name"], "ar-XA-Chirp3-HD-Kore")

    def test_speak_prefers_google_over_openai(self):
        with mock.patch.dict(os.environ, {"GOOGLE_TTS_KEY": "k"}), \
             mock.patch.object(self.v, "_ai_speak_google", return_value=b"G") as g, \
             mock.patch.object(self.v, "_ai_client") as oai:
            self.assertEqual(self.v._ai_speak("نص", 5), b"G")
        g.assert_called_once()
        oai.audio.speech.create.assert_not_called()

    def test_speak_falls_back_to_openai_when_google_fails(self):
        fake = mock.MagicMock()
        fake.audio.speech.create.return_value.iter_bytes.return_value = [b"O"]
        with mock.patch.dict(os.environ, {"GOOGLE_TTS_KEY": "k"}), \
             mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(self.v, "_ai_speak_google", return_value=None), \
             mock.patch.object(self.v, "_ai_client", fake), \
             mock.patch.object(self.v, "AI_ENABLED", True):
            os.environ.pop("GEMINI_API_KEY", None)
            self.assertEqual(self.v._ai_speak("نص", 6), b"O")


if __name__ == "__main__":
    unittest.main()
