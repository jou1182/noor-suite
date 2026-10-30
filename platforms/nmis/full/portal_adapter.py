# -*- coding: utf-8 -*-
"""portal_adapter.py — العقد المعياري لأي منصة مناقصات جديدة.

كل منصة عربية مختلفة في آلية الدخول والتصدير. هذا الملف لا "يحل" الفروق —
بل يفرض عقداً واضحاً: أي منصة جديدة تنفّذ دالة واحدة إجبارية:

    fetch_to_file() -> bool   # اسحب المنافسات واكتبها كملف Excel قياسي، أرجع النجاح

هذا هو بالضبط ما يحتاجه محرك المقارنة (engine_core) — يقرأ نفس الملف القياسي
بعد النجاح. أي منصة API-based يمكنها أيضاً تنفيذ export_tenders() -> DataFrame.

المحوّل المرجعي (NoorPortalAdapter) يُغلّف export_in_progress.py الحي حرفياً
بلا أي تغيير في سلوكه — لذلك ربط هذا الملف بالمحرك = صفر تغيير سلوكي.

اختيار المنصة المفعّلة: مفتاح "portal_adapter" في company_profile.json
(الافتراضي: "noor"). لإضافة منصة: أنشئ فئة ترث PortalAdapter، سجّلها في
_REGISTRY، وضع اسمها في ملف الهوية.
"""
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd

# الأعمدة التي يتوقعها engine_core من أي منصة (ثابتة بالعربية لأنه نظامك الحالي)
REQUIRED_COLUMNS = [
    "رقم المنافسة", "اسم المنافسة", "المالك",
    "تاريخ التقديم", "نوع الأعمال", "القطاع",
]


class PortalAdapter(ABC):
    """العقد الذي تنفّذه أي منصة مناقصات."""

    platform_name: str = "منصة غير مسمّاة"

    @abstractmethod
    def fetch_to_file(self) -> bool:
        """اسحب المنافسات الحالية واكتبها كملف Excel قياسي في المسار المتوقّع
        (output/in_progress_tenders.xlsx). أرجع True عند النجاح، False عند الفشل.
        لا تُنفّذ منطق المقارنة هنا — هذا عمل engine_core حصراً."""
        raise NotImplementedError

    def export_tenders(self) -> pd.DataFrame:
        """(اختياري) يُرجع المنافسات كـ DataFrame — مفيد للمنصات القائمة على API.
        التنفيذ الافتراضي: يشغّل fetch_to_file ثم يقرأ الملف القياسي."""
        if not self.fetch_to_file():
            raise RuntimeError(f"فشل السحب من {self.platform_name}")
        target = Path(__file__).parent / "output" / "in_progress_tenders.xlsx"
        return pd.read_excel(target)

    def validate_columns(self, df: pd.DataFrame) -> list:
        return [c for c in REQUIRED_COLUMNS if c not in df.columns]


class NoorPortalAdapter(PortalAdapter):
    """المحوّل المرجعي — يُغلّف export_in_progress.py الحي بلا أي تعديل عليه."""

    platform_name = "النور"

    def fetch_to_file(self) -> bool:
        # سلوك مطابق تماماً للاستدعاء المباشر السابق: export_in_progress.main()
        import export_in_progress
        return bool(export_in_progress.main())


class EtimadPortalAdapter(PortalAdapter):
    """
    ⚠️ قالب فاضي (Template) -- غير مكتمل عمداً. لا حساب حقيقي على منصة
    اعتماد متاح للاختبار وقت كتابة هذا الملف، فبُني كنموذج موثّق جاهز
    للتعبئة السريعة يوم ما يتوفر عميل/حساب حقيقي، بدل ما نخترع منطق سحب
    وهمي مش هيشتغل فعلياً.

    ── قائمة التحقق قبل أي تنفيذ حقيقي (اتبعها بالترتيب) ──────────────
    1. هل عندك حساب حقيقي على المنصة؟ بدون واحد، مفيش طريقة تختبر أي
       خطوة تالية بثقة -- كل الخطوات دي نظرية لحد ما يتوفر.
    2. افحص طريقة الدخول: كوكيز بسيطة (زي النور)؟ نموذج دخول + كابتشا؟
       مصادقة ثنائية (2FA)؟ API رسمي موثّق؟ -- ده بيحدد هل تحتاج
       `requests` بسيط زي export_in_progress.py، أو Selenium كامل.
    3. لو محتاج Selenium: أنشئ selectors_etimad.json (نفس شكل selectors.json
       الحالي) بدل ما تكتب أي CSS/XPath selector مباشرة في الكود.
    4. حدد أعمدة تصدير المنصة الحقيقية وطابقها مع REQUIRED_COLUMNS فوق --
       لاحظ REQUIRED_COLUMNS ثابتة بالعربية لأنها نفس أعمدة نظامنا الحالي؛
       أي منصة جديدة لازم تُخرّج نفس الأسماء دي بالظبط (أو تُترجَم إليها
       داخل fetch_to_file نفسها قبل كتابة ملف الإكسل).
    5. اختبر fetch_to_file() لوحدها أولاً (بدون ربطها بـ engine_core) --
       تأكد إنها بتكتب output/in_progress_tenders.xlsx بالشكل الصحيح.
    6. زي ما حصل فعلاً مع محوّل النور: اختبر بمحاكاة (Mock) الأول، انشر،
       راقب أول دورة فحص حية قبل ما تثق فيها بالكامل.

    ── لماذا هذا الكلاس مسجّل في _REGISTRY رغم إنه غير مكتمل؟ ──────────
    عمداً -- لو مستأجر (tenant) جديد ضبط "portal_adapter": "etimad" في
    company_profile.json بالغلط قبل ما يكتمل التنفيذ الحقيقي، النظام
    لازم يفشل بوضوح هنا (NotImplementedError برسالة واضحة) بدل ما يسقط
    صامتاً على NoorPortalAdapter ويسحب بيانات شركة النور الحقيقية
    لعميل مختلف تماماً -- ده كان سيكون تسريب بيانات فعلي.
    """

    platform_name = "اعتماد (قالب غير مكتمل)"

    def fetch_to_file(self) -> bool:
        raise NotImplementedError(
            "EtimadPortalAdapter قالب فاضي -- لسه مش مكتمل. "
            "راجع التعليق التوضيحي فوق الكلاس ده (قائمة التحقق) قبل أي محاولة تنفيذ حقيقي."
        )


class ManualExcelPortalAdapter(PortalAdapter):
    """
    محوّل بيانات يدوي -- الحل العملي لأي عميل ملوش منصة مدعومة، أو مش
    عايز/محتاج يبني محوّل سحب آلي مخصص (شغل مطورين متخصص، زي ما شرحنا في
    EtimadPortalAdapter فوق). العميل بيحدّث **ملف إكسل واحد** بنفسه بالأعمدة
    المطلوبة بالظبط (REQUIRED_COLUMNS)، والنظام كله -- محرك المقارنة، بوت
    تليجرام، لوحة الويب، المساعد الذكي -- يشتغل من غير أي تعديل إضافي،
    بالظبط كأن البيانات جاية من سحب آلي حقيقي.

    ── مكان الملف ──
    manual_input/tenders.xlsx -- بجوار مجلد output/ لكن منفصل عنه عمداً:
    output/ مُدار بالكامل من النظام (يُكتب فوقه تلقائياً)، وmanual_input/
    ملك العميل، يعدّل فيه براحته وقت ما يحب.

    ── أول تشغيل ──
    لو الملف مش موجود، الأداة بتنشئ نسخة فاضية بالأعمدة الصحيحة تلقائياً
    وترجع False (لا بيانات بعد) -- العميل بس يفتح الملف الجاهز ده ويملاه.
    """

    platform_name = "إدخال يدوي (إكسل)"

    def __init__(self, manual_file: Path = None, output_file: Path = None):
        # المسارات قابلة للحقن (dependency injection) لتسهيل الاختبار المعزول
        # بلا أي لمس لملفات الإنتاج الحقيقية -- الافتراضي هو المسار الحقيقي.
        self.manual_file = manual_file or (Path(__file__).parent / "manual_input" / "tenders.xlsx")
        self.output_file = output_file or (Path(__file__).parent / "output" / "in_progress_tenders.xlsx")

    def fetch_to_file(self) -> bool:
        self.manual_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.manual_file.exists():
            template = pd.DataFrame(columns=REQUIRED_COLUMNS)
            template.to_excel(self.manual_file, index=False)
            print(f"[إدخال يدوي] تم إنشاء قالب فاضٍ: {self.manual_file}")
            print("املأ المنافسات في الملف ده واحفظه، وشغّل النظام تاني.")
            return False

        df = pd.read_excel(self.manual_file)
        missing = self.validate_columns(df)
        if missing:
            print(f"[إدخال يدوي] أعمدة ناقصة في {self.manual_file}: {missing}")
            return False

        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(self.output_file, index=False)
        return True


# ── سجل المنصات المتاحة ──
_REGISTRY = {
    "noor": NoorPortalAdapter,
    "etimad": EtimadPortalAdapter,     # قالب فاضي موثّق -- راجع تعليق الكلاس قبل التفعيل
    "manual": ManualExcelPortalAdapter,  # جاهز وشغّال بالكامل -- الحل العملي للعملاء الجدد
}


def get_active_portal() -> PortalAdapter:
    """يعيد محوّل المنصة المفعّلة حسب company_profile.json (الافتراضي: النور)."""
    key = "noor"
    try:
        from company_profile import PROFILE
        key = (PROFILE.get("portal_adapter") or "noor").strip().lower()
    except Exception:
        pass
    cls = _REGISTRY.get(key, NoorPortalAdapter)
    return cls()
