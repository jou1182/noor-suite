# -*- coding: utf-8 -*-
"""Company identity loader — single source of truth for all tenant-specific
branding. Reads company_profile.json; falls back to NEUTRAL defaults (never a
real company's identity — identity-leak lesson). Import PROFILE anywhere:
`from company_profile import PROFILE`."""
import json
from pathlib import Path

_DEFAULTS = {
    "name_ar": "شركتك",
    "name_en": "YOUR COMPANY",
    "short_ar": "شركتك",
    "system_title": "نظام متابعة المنافسات",
    "system_subtitle": "لوحة متابعة المنافسات",
    "team_ar": "فريق العروض الفنية",
    "department_ar": "قسم العروض الفنية",
    "portal_url": "https://www.noor-ms.com",
    "portal_export_path": "/ar/tendering/export_to_excel_in_progress_tender/",
    "portal_cookie_domain": ".noor-ms.com",
    "theme_bg": "#b88800",
    "theme_card": "#fffde8",
    "theme_hover": "#fdf5c0",
    "theme_head": "#f5e870",
    "theme_primary": "#8a4800",
    "theme_primary_l": "#b86a00",
    "theme_primary_d": "#5e2e00",
    "footer_owner": "",
    "footer_url": "",
    "ai_scope_ar": "المناقصات ومتابعة العروض الفنية",
    "engineers": [{"name": "مهندس 1", "capacity": 5}],
    "dual_approval": False,
    # ميزات اختيارية لكل شركة (2026-09-24): "kanban" = لوحة المهام + القائمة الجانبية
    "features": [],
    # مظهر خاص (templates/skins/<skin>.css) — "" = المظهر الأساسي
    "skin": "",
}

def load_profile():
    data = dict(_DEFAULTS)
    try:
        from instance_paths import COMPANY_PROFILE_FILE
        p = COMPANY_PROFILE_FILE   # COMPANY_PROFILE_FILE في .env لكل نسخة
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, bool):
                    data[k] = v
                elif isinstance(v, str) and v.strip():
                    data[k] = v
                elif isinstance(v, list):
                    data[k] = v
    except Exception:
        pass
    return data

PROFILE = load_profile()
# خلفية خانات الإدخال (2026-09-24): كانت = خلفية الصفحة، فصارت داكنة بنص داكن في النور
if not PROFILE.get("theme_field"):
    from theme_palette import field_color
    PROFILE["theme_field"] = field_color(PROFILE["theme_bg"], PROFILE["theme_card"])


def feature_enabled(name: str) -> bool:
    """ميزة مفعّلة لهذه النسخة؟ ("features": ["kanban"] في ملف هوية الشركة)."""
    return name in (PROFILE.get("features") or [])
