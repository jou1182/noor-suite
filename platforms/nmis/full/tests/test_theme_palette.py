"""ألوان كل شركة: صفحات النور لا تتغير حرفاً، ونسخة أخرى لا يبقى فيها أي لون من هوية النور،
وخانات الإدخال مقروءة (كانت داكنة بنص داكن في النور)."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import colorsys
import os
import unittest
from pathlib import Path

from db_manager import DBManager

import theme_palette as tp

NOOR = {"theme_bg": "#0f1c33", "theme_card": "#eef3fb", "theme_hover": "#dbe6f7", "theme_head": "#c7d9f2",
        "theme_primary": "#4c1a89", "theme_primary_l": "#2a6ab5", "theme_primary_d": "#0f2e54"}


def hls(h):
    return colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)))


class PaletteTest(unittest.TestCase):
    def test_noor_is_untouched(self):
        self.assertEqual(tp.build_map(dict(tp.REFERENCE)), {})
        self.assertEqual(tp.apply("a{color:#8a4800}", {}), "a{color:#8a4800}")

    def test_other_company_keeps_lightness_and_takes_its_hues(self):
        m = tp.build_map(NOOR)
        for k, v in NOOR.items():
            self.assertEqual(m[tp.REFERENCE[k]], v)
        for h in tp.BRAND_HEX:
            with self.subTest(color=h):
                self.assertAlmostEqual(hls(m[h])[1], hls(h)[1], delta=0.02)          # نفس الإضاءة = نفس التباين
                target = hls(NOOR["theme_card"] if hls(h)[1] >= 0.75 else NOOR["theme_primary"])[0]
                if hls(m[h])[2] > 0.05:
                    self.assertAlmostEqual(hls(m[h])[0], target, delta=0.02)

    def test_apply_replaces_brand_hex_and_rgba_only(self):
        m = tp.build_map(NOOR)
        css = ("b{border:1px solid #C8A028;box-shadow:0 0 4px rgba(138, 72, 0, .3);color:#3fb950}"
               "i{background:rgba(36,120,72,.1)}")
        out = tp.apply(css, m)
        self.assertIn(m["#c8a028"], out)
        r, g, b = m[(138, 72, 0)]
        self.assertIn(f"rgba({r}, {g}, {b}, .3)", out)
        self.assertIn("#3fb950", out)                    # ألوان الدلالة ثابتة
        self.assertIn("rgba(36,120,72,.1)", out)

    def test_field_color_is_readable(self):
        self.assertEqual(tp.field_color(tp.REFERENCE["theme_bg"], "#fffde8"), "#b88800")   # النور كما هو
        self.assertEqual(tp.field_color(NOOR["theme_bg"], NOOR["theme_card"]), NOOR["theme_card"])
        self.assertGreaterEqual(tp.contrast(tp.field_color(NOOR["theme_bg"], NOOR["theme_card"]), tp.DEFAULT_TEXT), 4.5)


class RenderedPagesTest(unittest.TestCase):
    """صفحات اللوحة بألوان النور: لا يبقى أي لون من هوية النور، وخانات الإدخال فاتحة."""

    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import web_core
        import web_dashboard
        cls.wc, cls.app = web_core, web_dashboard.app
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()

    def setUp(self):
        self._orig = {k: self.wc.PROFILE.get(k) for k in list(NOOR) + ["theme_field"]}
        self.wc.PROFILE.update(NOOR, theme_field=tp.field_color(NOOR["theme_bg"], NOOR["theme_card"]))

    def tearDown(self):
        self.wc.PROFILE.update(self._orig)

    def test_no_noor_brand_colors_left(self):
        cl = self.app.test_client()
        with cl.session_transaction() as s:
            s["ok"] = True
            s["admin_ok"] = True
        brand = set(tp.BRAND_HEX) | set(tp.REFERENCE.values())
        for url in ("/login", "/", "/results", "/engineer-view", "/owners", "/admin", "/engineer"):
            with self.subTest(url=url):
                html = cl.get(url, environ_base={"REMOTE_ADDR": "127.0.0.1"}).get_data(as_text=True).lower()
                self.assertEqual(sorted(c for c in brand if c in html), [])
                if url == "/":
                    self.assertIn(f"--field:{NOOR['theme_card']}", html)


if __name__ == "__main__":
    unittest.main()
