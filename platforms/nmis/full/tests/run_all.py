"""
tests/run_all.py — بوابة الجودة قبل أي نشر.

    python tests/run_all.py

1. يفحص صياغة كل ملفات Python في جذر المشروع (py_compile)
2. يشغّل كل اختبارات tests/test_*.py على قاعدة بيانات مؤقتة
   (لا يلمس output/tenders.db الحقيقية أبداً)

يرجع 0 عند النجاح، و1 عند أي فشل — deploy.py يرفض النشر إن فشل.
"""
import os
import sys
import logging
import tempfile
import unittest
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# قاعدة مؤقتة قبل أي import لوحدات المشروع (db_manager/engine_core تنشئ اتصالها عند الاستيراد)
_TMP = tempfile.mkdtemp(prefix="noor_tests_")
os.environ["DB_PATH"] = str(Path(_TMP) / "import_guard.db")
logging.basicConfig(level=logging.ERROR)  # إخفاء سجلات INFO/WARNING العادية أثناء الاختبار


def project_py_files() -> list:
    """ملفات Python المتتبَّعة في git فقط — السيرفر فيه سكربتات ترقيع مؤقتة غير متتبَّعة ولا تُترجم."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        files = [ROOT / p for p in out.splitlines() if "/" not in p]
        if files:
            return sorted(files)
    except Exception:
        pass
    return sorted(ROOT.glob("*.py"))


def compile_all() -> list:
    errors = []
    for f in project_py_files():
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{f.name}: {e.msg}")
    return errors


def main() -> int:
    print("[1/2] فحص صياغة ملفات Python...")
    errors = compile_all()
    for e in errors:
        print("   ❌", e)
    if errors:
        return 1
    print(f"   ✅ {len(project_py_files())} ملف سليم")

    print("[2/2] تشغيل الاختبارات...")
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_*.py", top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    ok = result.wasSuccessful()
    print(f"\n{'✅ كل الاختبارات نجحت' if ok else '❌ فشلت اختبارات'} ({result.testsRun} اختبار)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
