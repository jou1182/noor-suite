"""
يُستورد أول سطر في كل ملف اختبار: يوجّه DB_PATH إلى قاعدة مؤقتة قبل استيراد
db_manager/engine_core (ينشئان اتصالهما عند الاستيراد) — حتى لو شُغّل ملف الاختبار منفرداً.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "noor_tests_" not in os.environ.get("DB_PATH", ""):
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="noor_tests_")) / "import_guard.db")
