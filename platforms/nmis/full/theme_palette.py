# -*- coding: utf-8 -*-
"""ألوان الصفحات لكل شركة (2026-09-24).

الصفحات كُتبت بألوان النور (بني/ذهبي/برتقالي) مباشرةً في CSS وJS، فظهرت نسخة النور
خليطاً من بنفسجي وبرتقالي. هنا مصدر واحد يحوّل لوحة النور إلى لوحة الشركة وقت العرض:

- ألوان الهوية السبعة (theme_*) → قيم الشركة نفسها حرفياً.
- باقي درجات النور (حدود، نصوص، شريط علوي، ظلال) → نفس الإضاءة والتشبع النسبي،
  بدرجة لون الشركة: الفاتح (خلفيات/تظليل) على درجة theme_card، والباقي على درجة theme_primary.
  الإضاءة ثابتة فيبقى التباين ومقروئية النص كما صممت.
- ألوان الدلالة (أحمر/أخضر/أزرق الحالات) لا تُلمس.
النور (ألوانه = المرجع) → لا تحويل إطلاقاً: نفس HTML حرفاً بحرف.
"""
import colorsys
import re

# لوحة النور المرجعية = company_profile._DEFAULTS
REFERENCE = {
    "theme_bg": "#b88800", "theme_card": "#fffde8", "theme_hover": "#fdf5c0", "theme_head": "#f5e870",
    "theme_primary": "#8a4800", "theme_primary_l": "#b86a00", "theme_primary_d": "#5e2e00",
}
# درجات النور المكتوبة حرفياً في templates/ (هوية، لا دلالة)
BRAND_HEX = [
    "#1e1404", "#4a3810", "#7a5e28", "#c8a028", "#a07820", "#fff4d8", "#5a2800", "#6e3200", "#b06000",
    "#ffd060", "#9a8a60", "#9a7838", "#3d1c00", "#3d1800", "#ffd88a", "#fdf8ee", "#a05200", "#5a3810",
    "#ffe9b0", "#a85a00", "#6a5a30", "#6a3000", "#fef8c8", "#f7edc8", "#f3e3a8", "#eeda90", "#fdedb0",
    "#ffd97a", "#ffca2c", "#e3b341", "#d29922", "#a06800", "#a84e1a", "#ffa657", "#ffaa60",
    # بوابة المهندسين (طابع داكن بلون كهرماني)
    "#ffc107", "#7a5200", "#1c1100", "#2d1e00",
]
BRAND_RGB = [
    (138, 72, 0), (184, 106, 0), (100, 60, 0), (200, 135, 60), (255, 215, 140), (200, 160, 40),
    (200, 144, 64), (180, 140, 40), (168, 78, 26), (120, 110, 90), (255, 193, 7), (227, 179, 65),
]
DEFAULT_TEXT = "#1e1404"
_LIGHT = 0.75


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))


def _luminance(h: str) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _hex_to_rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def field_color(bg: str, card: str = "#ffffff", text: str = DEFAULT_TEXT) -> str:
    """خلفية خانات الإدخال: خلفية الصفحة إن كان النص الداكن مقروءاً عليها (النور)، وإلا لون البطاقات."""
    try:
        return bg if contrast(bg, text) >= 4.5 else card
    except (ValueError, TypeError):
        return card


def _theme(profile: dict) -> dict:
    return {k: str(profile.get(k) or v).lower() for k, v in REFERENCE.items()}


def build_map(profile: dict) -> dict:
    """{لون النور: لون الشركة} — فارغ للنور أو لأي نسخة بنفس ألوانه."""
    theme = _theme(profile)
    if theme == REFERENCE:
        return {}
    try:
        anchors = {  # (مرجع النور، الشركة) لكل دور
            "dark": (_hls(_hex_to_rgb(REFERENCE["theme_primary"])), _hls(_hex_to_rgb(theme["theme_primary"]))),
            "light": (_hls(_hex_to_rgb(REFERENCE["theme_card"])), _hls(_hex_to_rgb(theme["theme_card"]))),
        }
    except ValueError:
        return {}

    def convert(rgb):
        h, l, s = _hls(rgb)
        (_, _, ref_s), (new_h, _, new_s) = anchors["light" if l >= _LIGHT else "dark"]
        s2 = min(1.0, s * (new_s / ref_s)) if ref_s else new_s
        return tuple(c * 255 for c in colorsys.hls_to_rgb(new_h, l, s2))

    mapping = {REFERENCE[k]: theme[k] for k in REFERENCE}
    for h in BRAND_HEX:
        mapping.setdefault(h, _rgb_to_hex(convert(_hex_to_rgb(h))))
    for rgb in BRAND_RGB:
        mapping[rgb] = tuple(max(0, min(255, round(c))) for c in convert(rgb))
    return mapping


_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
_RGB_RE = re.compile(r"(rgba?\(\s*)(\d{1,3})(\s*,\s*)(\d{1,3})(\s*,\s*)(\d{1,3})")


def apply(html: str, mapping: dict) -> str:
    """يستبدل ألوان النور في نص HTML/CSS/JS بألوان الشركة."""
    if not mapping:
        return html

    def hex_sub(m):
        return mapping.get(m.group(0).lower(), m.group(0))

    def rgb_sub(m):
        new = mapping.get((int(m.group(2)), int(m.group(4)), int(m.group(6))))
        if not new:
            return m.group(0)
        return f"{m.group(1)}{new[0]}{m.group(3)}{new[1]}{m.group(5)}{new[2]}"

    return _RGB_RE.sub(rgb_sub, _HEX_RE.sub(hex_sub, html))
