"""
نفس الكود لأكثر من شركة (النور + النور): كل ما يخص الشركة من .env نسختها (2026-09-24).
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import importlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
# أدوات المشغّل التي تعمل من جهازه وتستهدف سيرفر النور عمداً
OPERATOR_TOOLS = {"deploy.py", "sync_server_to_local.py", "pull_db_from_server.py", "update_server_session.py",
                  "health_check_now.py", "server_ssh.py", "noor_backup.py", "noor_restore.py"}


class InstancePathsTest(unittest.TestCase):
    def test_runtime_code_has_no_hardcoded_instance_paths(self):
        files = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        offenders = []
        for f in files:
            if "/" in f or f in OPERATOR_TOOLS:
                continue
            for n, line in enumerate((ROOT / f).read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#", 1)[0]
                if re.search(r"/opt/noor-tender|noor-bot\.service", code) and "instance_paths" not in f:
                    offenders.append(f"{f}:{n}")
        self.assertEqual(offenders, [], "استخدم instance_paths بدل المسارات الحرفية")

    def test_env_overrides_profile_and_knowledge(self):
        tmp = Path(tempfile.mkdtemp(prefix="noor_tests_inst_"))
        (tmp / "profile.json").write_text(json.dumps({"name_ar": "شركة النور للمقاولات", "short_ar": "النور"}), encoding="utf-8")
        (tmp / "kb").mkdir()
        (tmp / "kb" / "01.md").write_text("شركة النور تأسست للتدريب", encoding="utf-8")
        env = {"COMPANY_PROFILE_FILE": str(tmp / "profile.json"), "KNOWLEDGE_DIR": str(tmp / "kb"),
               "BOT_SERVICE_NAME": "course-demo-bot.service"}
        import company_profile
        import instance_paths
        try:
            with mock.patch.dict(os.environ, env):
                importlib.reload(instance_paths)
                importlib.reload(company_profile)
                self.assertEqual(company_profile.PROFILE["name_ar"], "شركة النور للمقاولات")
                self.assertEqual(instance_paths.BOT_SERVICE_NAME, "course-demo-bot.service")
                import ai_assistant
                self.assertIn("شركة النور تأسست", ai_assistant._ai_load_knowledge())
        finally:
            importlib.reload(instance_paths)
            importlib.reload(company_profile)

    def test_defaults_keep_current_behaviour(self):
        import instance_paths
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("COMPANY_PROFILE_FILE", "KNOWLEDGE_DIR", "BOT_SERVICE_NAME", "LOGO_FILE"):
                os.environ.pop(k, None)
            importlib.reload(instance_paths)
            self.assertEqual(instance_paths.COMPANY_PROFILE_FILE, ROOT / "company_profile.json")
            self.assertEqual(instance_paths.KNOWLEDGE_DIR, ROOT / "knowledge")
            self.assertEqual(instance_paths.BOT_SERVICE_NAME, "noor-bot.service")
            self.assertIsNone(instance_paths.LOGO_FILE)

    def test_logo_file_replaces_built_in_logo(self):
        """شعار كل شركة من tenant/ — «استعادة الشعار الأصلي» في نسخة أخرى لا يُظهر شعار النور."""
        import web_core
        built_in = web_core._default_logo_bytes(None)
        logo = Path(tempfile.mkdtemp(prefix="noor_tests_logo_")) / "logo.png"
        logo.write_bytes(b"\x89PNG-noor-logo")
        self.assertEqual(web_core._default_logo_bytes(logo), b"\x89PNG-noor-logo")
        self.assertEqual(web_core._default_logo_bytes(logo.with_name("missing.png")), built_in)
        with mock.patch.dict(os.environ, {"LOGO_FILE": str(logo)}):
            import instance_paths
            try:
                importlib.reload(instance_paths)
                self.assertEqual(instance_paths.LOGO_FILE, logo)
            finally:
                os.environ.pop("LOGO_FILE", None)
                importlib.reload(instance_paths)


if __name__ == "__main__":
    unittest.main()
