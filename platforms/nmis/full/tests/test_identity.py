"""مطابقة هوية المنافسات: المفتاح AUTO-* ومطابقة العناوين المحافظة."""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import unittest

import engine_core as ec


class TestTitlesMatch(unittest.TestCase):
    # أزواج حقيقية من قاعدة النور لمنافسات مختلفة فعلاً — يجب ألا تندمج أبداً
    DISTINCT_PAIRS = [
        ("صيانة الشوارع والأرصفة بقطاع وسط مدينة الرياض الجزء الأول",
         "صيانة الشوارع والأرصفة بقطاع وسط مدينة الرياض الجزء الثاني"),
        ("صيانة الشوارع والأرصفة بقطاع جنوب مدينة الرياض الجزء الأول",
         "صيانة الشوارع والأرصفة بقطاع وسط مدينة الرياض الجزء الأول"),
        ("مشروع صيانة الطرق المحيطة بالملاعب استعداداً لكأس آسيا المرحلة الثانية",
         "مشروع صيانة الطرق المحيطة بالملاعب استعداداً لكأس آسيا المرحلة الاولى"),
        ("مشروع صيانة وتأهيل أرصفة وشوارع متفرقة بحي الدوحة الشمالية بالظهران",
         "مشروع صيانة وتأهيل أرصفة وشوارع متفرقة بحي الدوحة الجنوبية بالظهران"),
        ("تنفيذ حلول تصريف مياه الأمطار- للمنطقة BC- الحزمة الاولى- منطقة الزهرا",
         "تنفيذ حلول تصريف مياه الأمطار- للمنطقة BC- الحزمة الثانية- منطقة الزهرا"),
        ("مشروع صيانة وتأهيل مواقع متفرقة بحي الجامعة بمدينة الظهران",
         "مشروع صيانة وتأهيل مواقع متفرقة بحي الدانة الشمالية بمدينة الظهران"),
        ("مشروع تصميم وتنفيذ مواقف النخيل", "مشروع تصميم وتنفيذ مواقف الصحافة"),
        ("مشروع تأهيل الشوارع رقم 5 بالدمام", "مشروع تأهيل الشوارع رقم 6 بالدمام"),
        ("إنشاء طرق حي النرجس", "إنشاء طرق حي النرجس - إعادة طرح"),
    ]

    # نفس المنافسة بعد تصحيح إملائي/مسافات/همزات في المنصة — يجب أن تتطابق
    SAME_PAIRS = [
        ("تصميم وتنفيذ أعمال البنية التحتية لعمائرالإسكان", "تصميم وتنفيذ أعمال البنية التحتية لعمائر الإسكان"),
        ("مشروع تأهيل الشوارع الرئيسية بحي الخدمات المساندة بالدمام", "مشروع تاهيل الشوارع الرئيسيه بحي الخدمات المسانده بالدمام"),
        ("انشاء مبنى إداري بمطار الملك سلمان", "إنشاء مبنى اداري بمطار الملك سلمان"),
        ("صيانة وتشغيل محطات الضخ بالمنطقة الشرقية", "صيانة وتشغيل محطات الضخ بالمنطقه الشرقيه."),
        ("اتفاقيةاطاريه لتأهيل وتجهيز مرافق وزارة الدفاع", "اتفاقية اطارية لتأهيل وتجهيز مرافق وزارة الدفاع"),
        ("مشروع تأهيل شوارع بحي النهضة والمنتزة بالدمام", "مشروع تأهيل شوارع بحي النهضة والمنتزه بالدمام"),
    ]

    def test_distinct_tenders_never_match(self):
        for a, b in self.DISTINCT_PAIRS:
            with self.subTest(a=a, b=b):
                self.assertFalse(ec.titles_match(a, b))

    def test_spelling_fixes_match(self):
        for a, b in self.SAME_PAIRS:
            with self.subTest(a=a, b=b):
                self.assertTrue(ec.titles_match(a, b))

    def test_empty_titles_never_match(self):
        self.assertFalse(ec.titles_match("", ""))
        self.assertFalse(ec.titles_match(None, "مشروع"))


class TestIdentityKey(unittest.TestCase):
    ROW = {"اسم المنافسة": "مشروع صيانة الطرق", "المالك": "أمانة الرياض", "نوع الأعمال": "طرق", "القطاع": "حكومي"}

    def test_key_is_stable_and_prefixed(self):
        k1, k2 = ec.build_tender_identity(self.ROW), ec.build_tender_identity(dict(self.ROW))
        self.assertEqual(k1, k2)
        self.assertTrue(k1.startswith("AUTO-"))

    def test_hamza_and_diacritics_do_not_change_key(self):
        variant = dict(self.ROW, **{"المالك": "امانة الرياض", "اسم المنافسة": "مشروعُ صيانة الطرق"})
        self.assertEqual(ec.build_tender_identity(self.ROW), ec.build_tender_identity(variant))

    def test_real_tender_number_wins(self):
        self.assertEqual(ec.build_tender_identity(dict(self.ROW, **{"رقم المنافسة": "T-123"})), "T-123")


class TestFindSoftMatch(unittest.TestCase):
    CANDIDATES = [
        {"tender_id": "AUTO-a", "title": "مشروع تأهيل شوارع بحي النهضة والمنتزة بالدمام", "owner": "امانة المنطقة الشرقية"},
        {"tender_id": "AUTO-b", "title": "صيانة الشوارع بقطاع وسط الرياض الجزء الأول", "owner": "امانة الرياض"},
    ]

    # "والمنتزا" تصحيف حقيقي لا يزيله التطبيع (بخلاف ة/ه)
    def test_typo_fix_same_owner_links(self):
        row = {"اسم المنافسة": "مشروع تأهيل شوارع بحي النهضة والمنتزا بالدمام", "المالك": "أمانة المنطقة الشرقية"}
        self.assertEqual(ec.find_soft_match(row, self.CANDIDATES), "AUTO-a")

    def test_typo_fix_other_owner_does_not_link(self):
        row = {"اسم المنافسة": "مشروع تأهيل شوارع بحي النهضة والمنتزا بالدمام", "المالك": "وزارة الدفاع"}
        self.assertIsNone(ec.find_soft_match(row, self.CANDIDATES))

    def test_identical_long_title_links_even_if_owner_changed(self):
        row = {"اسم المنافسة": "مشروع تأهيل شوارع بحي النهضة والمنتزة بالدمام", "المالك": "أمانة الشرقية"}
        self.assertEqual(ec.find_soft_match(row, self.CANDIDATES), "AUTO-a")

    def test_next_part_does_not_link(self):
        row = {"اسم المنافسة": "صيانة الشوارع بقطاع وسط الرياض الجزء الثاني", "المالك": "امانة الرياض"}
        self.assertIsNone(ec.find_soft_match(row, self.CANDIDATES))

    def test_ambiguous_candidates_do_not_link(self):
        dup = self.CANDIDATES + [dict(self.CANDIDATES[0], tender_id="AUTO-c")]
        row = {"اسم المنافسة": "مشروع تأهيل شوارع بحي النهضة والمنتزه بالدمام", "المالك": "امانة المنطقة الشرقية"}
        self.assertIsNone(ec.find_soft_match(row, dup))


if __name__ == "__main__":
    unittest.main()
