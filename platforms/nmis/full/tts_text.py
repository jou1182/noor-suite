# -*- coding: utf-8 -*-
"""Pure TTS text-processing: pronunciation dictionaries, Egyptian-Arabic
number-to-words, and speech text preparation. Extracted verbatim from
bot_daemon.py on 2026-07-05. No Telegram/network dependencies - unit-testable."""
import re

_PRONUNCIATION_DICT = {
    # تقنية / ذكاء اصطناعي
    "AI":           "الذكاء الاصطناعي",
    "GPT":          "جي بي تي",
    "API":          "واجهة البرمجة",
    "URL":          "رابط",
    "PDF":          "بي دي إف",
    "Excel":        "إكسل",
    "WhatsApp":     "واتساب",
    "Telegram":     "تيليجرام",
    "OpenAI":       "أوبن إي آي",
    "ChatGPT":      "شات جي بي تي",
    "Whisper":      "ويسبر",
    "Python":       "بايثون",
    "SQL":          "إس كيو إل",
    "OK":           "حسناً",
    "Yes":          "نعم",
    "No":           "لا",
    # جهات حكومية سعودية
    "MOT":          "وزارة النقل",
    "MOH":          "وزارة الإسكان",
    "MOMRA":        "وزارة الشؤون البلدية",
    "NEOM":         "نيوم",
    "PIF":          "صندوق الاستثمارات العامة",
    "NWC":          "المياه الوطنية",
    "STC":          "الاتصالات السعودية",
    "ARAMCO":       "أرامكو",
    "SABIC":        "سابك",
    "ROSHN":        "روشن",
    "NUPCO":        "نوبكو",
    "SFDA":         "هيئة الغذاء والدواء",
    "CITC":         "هيئة الاتصالات",
    "ZATCA":        "هيئة الزكاة والضريبة",
    "KACST":        "مدينة الملك عبدالعزيز للعلوم والتقنية",
    # وحدات قياس
    "KSA":          "المملكة العربية السعودية",
    "SAR":          "ريال سعودي",
    "km":           "كيلومتر",
    "m²":           "متر مربع",
    "m2":           "متر مربع",
    "m³":           "متر مكعب",
    "m3":           "متر مكعب",
    "kg":           "كيلوجرام",
    "kV":           "كيلو فولت",
    "MW":           "ميجاوات",
    # اختصارات شائعة
    "No.":          "رقم",
    "no.":          "رقم",
    "vs":           "مقابل",
    "etc":          "وغيره",
    "N/A":          "مش متاح",
    "TBD":          "هيتحدد بعدين",
    "CEO":          "الرئيس التنفيذي",
    "HR":           "الموارد البشرية",
    "IT":           "تكنولوجيا المعلومات",
}


_ARABIC_PHONETIC_CORRECTIONS = {
    # ── نطق مصطلحات المناقصات (ق → ء بالمصري) ─────────────────
    "فضلك":            "فَضلك",
    "فضلاً":           "فَضلاً",
    "مناقصة":          "مناأصة",      # ق → ء مصري
    "مناقصات":         "مناأصات",
    "منافسة":          "منافسة",
    "منافسات":         "منافسات",
    "الترسية":         "الترسية",
    "العطاء":          "العَطا",
    "الضمان":          "الضَّمان",
    "الكراسة":         "الكُرَّاسة",
    "المقاولين":       "المأاولين",   # ق → ء مصري
    "المقاول":         "المأاول",     # ق → ء مصري
    "التقديم":         "التأديم",     # ق → ء مصري
    "تقديم":           "تأديم",
    "الاستشاري":       "الاستشاري",
    "المقترح":         "المأترح",     # ق → ء مصري
    "الوقت":           "الوأت",       # ق → ء مصري
    "وقت":             "وأت",
    # ── مفردات مصرية بدل الفصحى ─────────────────────────────────
    "الآن":            "دلوقتي",
    "لاحقاً":          "بعدين",
    "وجدت":           "لقيت",
    "وجدنا":          "لقينا",
    "حسناً":          "تمام",
    "بالمائة":        "بالمية",
}


_EN_PHONETIC = {
    'a':'ا','b':'ب','c':'ك','d':'د','e':'إ','f':'ف','g':'ج','h':'ه',
    'i':'ي','j':'ج','k':'ك','l':'ل','m':'م','n':'ن','o':'و','p':'ب',
    'q':'ك','r':'ر','s':'س','t':'ت','u':'يو','v':'ف','w':'و','x':'كس',
    'y':'ي','z':'ز',
}


def _transliterate(word: str) -> str:
    """تحويل كلمة إنجليزية إلى نطق عربي تقريبي."""
    result = ""
    for ch in word.lower():
        result += _EN_PHONETIC.get(ch, ch)
    return result


def _apply_pronunciation(text: str) -> str:
    """
    1. تصحيح نطق الكلمات العربية (تشكيل)
    2. طبّق قاموس الإنجليزي→عربي الصريح
    3. أي كلمة إنجليزية متبقية → نقلها صوتياً للعربية
    """
    import re
    # ① تصحيح الكلمات العربية المُخطأة (الأطول أولاً لتجنب التعارض)
    for wrong, correct in sorted(_ARABIC_PHONETIC_CORRECTIONS.items(),
                                  key=lambda x: -len(x[0])):
        text = text.replace(wrong, correct)
    # ② القاموس الإنجليزي الصريح
    for wrong, correct in _PRONUNCIATION_DICT.items():
        text = re.sub(r'\b' + re.escape(wrong) + r'\b', correct, text, flags=re.IGNORECASE)
    # ③ أي كلمة إنجليزية تبقّت → نقل صوتي
    def _fallback(m):
        w = m.group()
        return _transliterate(w)
    text = re.sub(r'\b[A-Za-z]{2,}\b', _fallback, text)
    return text


def _num_to_ar(n: int) -> str:
    """تحويل رقم صحيح إلى كلمات عربية بالعامية المصرية."""
    if n < 0:
        return "ناقص " + _num_to_ar(-n)
    _ones = [
        "صفر","واحد","اتنين","تلاتة","أربعة","خمسة","ستة","سبعة","تمانية","تسعة",
        "عشرة","حداشر","اتناشر","تلتاشر","أرباعتاشر","خمستاشر",
        "ستاشر","سبعتاشر","تمنتاشر","تسعتاشر",
    ]
    _tens = ["","","عشرين","تلاتين","أربعين","خمسين","ستين","سبعين","تمانين","تسعين"]
    if n < 20:
        return _ones[n]
    if n < 100:
        t = _tens[n // 10]
        o = _ones[n % 10] if n % 10 else ""
        return (o + " و" + t) if o else t
    if n < 1000:
        h = n // 100
        r = n % 100
        # الصيغ المصرية المنطوقة: تلتمية، ربعمية، خمسمية… (وليس "تلاتة مية")
        p = ["", "مية", "ميتين", "تلتمية", "ربعمية", "خمسمية",
             "ستمية", "سبعمية", "تمنمية", "تسعمية"][h]
        return (p + " و" + _num_to_ar(r)) if r else p
    if n < 1_000_000:
        th = n // 1000
        r  = n % 1000
        if th == 1:    p = "ألف"
        elif th == 2:  p = "ألفين"
        elif th <= 10: p = ["", "", "", "تلات", "أربع", "خمس", "ست", "سبع", "تمن", "تسع", "عشر"][th] + " تلاف"
        else:          p = _num_to_ar(th) + " ألف"
        return (p + " و" + _num_to_ar(r)) if r else p
    if n < 1_000_000_000:
        m  = n // 1_000_000
        r  = n % 1_000_000
        p  = "مليون" if m == 1 else ("مليونين" if m == 2 else
              (_ones[m] + " مليون") if m < 20 else (_num_to_ar(m) + " مليون"))
        return (p + " و" + _num_to_ar(r)) if r else p
    # مليار (قيم المشاريع الكبيرة)
    b  = n // 1_000_000_000
    r  = n % 1_000_000_000
    p  = "مليار" if b == 1 else ("مليارين" if b == 2 else
          (_ones[b] + " مليار") if b < 20 else (_num_to_ar(b) + " مليار"))
    return (p + " و" + _num_to_ar(r)) if r else p


def _tts_prepare(text: str) -> str:
    """تحويل التواريخ والأرقام والرموز إلى نص عربي منطوق قبل الإرسال لـ TTS."""
    import re

    _AR_MONTHS = {
        1: "يناير", 2: "فبراير", 3: "مارس",   4: "أبريل",
        5: "مايو",  6: "يونيو",  7: "يوليو",  8: "أغسطس",
        9: "سبتمبر",10:"أكتوبر",11:"نوفمبر", 12: "ديسمبر",
    }

    # ⓪-a تحويل الأرقام العربية-الهندية (٠١٢…) إلى أرقام غربية
    _AR_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    text = text.translate(_AR_INDIC)
    # ⓪-b تنظيف الفواصل الألفية: 1,500,000 → 1500000
    text = re.sub(r'(\d{1,3})(,\d{3})+', lambda m: m.group().replace(',', ''), text)

    def date_to_arabic(day: int, month: int, year: int) -> str:
        m = _AR_MONTHS.get(month, str(month))
        return f"{_num_to_ar(day)} {m} {_num_to_ar(year)}"

    # ① YYYY-MM-DD  →  تاريخ بالكلمات المصرية
    def _repl_iso(m):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date_to_arabic(d, mo, y)
    text = re.sub(r'\b(\d{4})-(\d{2})-(\d{2})\b', _repl_iso, text)

    # ② DD/MM/YYYY  →  نفس التحويل
    def _repl_dmy(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date_to_arabic(d, mo, y)
    text = re.sub(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', _repl_dmy, text)

    # ③ نسبة مئوية  e.g. 85%  →  "خمسة وتمانين بالمية" (مصري)
    def _repl_pct(m):
        return _num_to_ar(int(m.group(1))) + " بالمية"
    text = re.sub(r'\b(\d+)%', _repl_pct, text)

    # ④ أرقام متبقية (بعد معالجة التواريخ)  →  كلمات عربية
    def _repl_num(m):
        try:
            return _num_to_ar(int(m.group()))
        except Exception:
            return m.group()
    text = re.sub(r'\b\d+\b', _repl_num, text)

    # ⑤ تحويل القوائم إلى جمل منطوقة طبيعية
    # "- بند" → "، بند" حتى يبدو الكلام متصلاً لا مقطوعاً
    text = re.sub(r'\n\s*[-•]\s*', '، ', text)
    text = re.sub(r'\n\s*\d+[.)]\s*', '، ', text)
    # إزالة الأسطر الفارغة المتعددة
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', '، ', text)
    # تطبيق قاموس النطق المخصص
    text = _apply_pronunciation(text)
    # ⑥ إزالة رموز Markdown التي يقرأها TTS
    text = re.sub(r'[*_`#~]', '', text)
    # ⑦ إزالة الإيموجي والرموز غير العربية
    text = re.sub(r'[^\w\s؀-ۿݐ-ݿ.,،؟!؛:\-]', ' ', text)
    # ⑧ دمج المسافات الزائدة
    text = re.sub(r'  +', ' ', text).strip()
    # ⑨ حد أقصى 550 حرف للصوت — اقطع عند آخر فاصلة طبيعية
    _TTS_MAX = 550
    if len(text) > _TTS_MAX:
        cut = text.rfind('،', 200, _TTS_MAX)
        if cut < 200:
            cut = text.rfind('.', 200, _TTS_MAX)
        if cut < 200:
            cut = _TTS_MAX
        text = text[:cut + 1].strip()
    return text


def _split_for_tts(text: str) -> list[str]:
    """
    تقسيم الرد إلى جزأين عند الحاجة:
    - جزء أول: يُرسَل فوراً (أسرع تجاوب)
    - جزء ثانٍ: يُكمل الفكرة
    القاعدة: إذا الرد أقل من 4 جمل → جزء واحد. أكثر → جزآن.
    """
    import re
    # تقسيم عند نهايات الجمل
    sentences = [s.strip() for s in re.split(r'(?<=[.!?؟])\s+', text) if s.strip()]
    if len(sentences) <= 3:
        return [text]
    # منتصف الجمل
    mid = len(sentences) // 2
    part1 = ' '.join(sentences[:mid])
    part2 = ' '.join(sentences[mid:])
    return [part1, part2]


