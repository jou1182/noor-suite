# -*- coding: utf-8 -*-
"""
إعدادات خاصة بكل نسخة (شركة) — المصدر الواحد لكل مسار أو اسم يختلف بين النسخ.

نفس الكود يشغّل أكثر من شركة على السيرفر (النور: /opt/noor-tender، النور: /opt/course-demo)،
فكل ما يخص الشركة يأتي من .env الخاص بنسختها، والافتراضي = مجلد الكود نفسه (سلوك النور).
(2026-09-24: كانت مسارات النور مكتوبة حرفياً — لوحة إدارة أي نسخة أخرى كانت ستعدّل
قاعدة معرفة النور وتعيد تشغيل بوت النور.)
"""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

COMPANY_PROFILE_FILE = Path(os.getenv("COMPANY_PROFILE_FILE") or APP_DIR / "company_profile.json")
KNOWLEDGE_DIR = Path(os.getenv("KNOWLEDGE_DIR") or APP_DIR / "knowledge")
DEFAULT_DB_PATH = APP_DIR / "output" / "tenders.db"
OUTPUT_DIR = APP_DIR / "output"
BOT_SERVICE_NAME = os.getenv("BOT_SERVICE_NAME", "noor-bot.service").strip()
# /healthz يطلب نسخة احتياطية حديثة (الإنتاج). نسخ العرض/التدريب بلا نسخ يومي: HEALTHZ_REQUIRE_BACKUP=0
HEALTHZ_REQUIRE_BACKUP = os.getenv("HEALTHZ_REQUIRE_BACKUP", "1").strip().lower() not in ("0", "false", "no", "off")
# الشعار الافتراضي للنسخة (يظهر إن لم يُرفع شعار من لوحة الإدارة، وبعد «استعادة الشعار الأصلي»).
# فارغ = الشعار المضمّن في الكود (شعار النور) — كل نسخة لشركة أخرى تضبطه على شعارها في tenant/.
LOGO_FILE = Path(os.getenv("LOGO_FILE")) if os.getenv("LOGO_FILE", "").strip() else None
