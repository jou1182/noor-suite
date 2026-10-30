# -*- coding: utf-8 -*-
"""
Noor Monthly PDF Report Generator
يولّد تقرير PDF احترافي ويرسله عبر التيليغرام
يُستدعى من bot_daemon.py في أول كل شهر
"""
import os, sqlite3, io, time
from contextlib import closing
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SHAPING_OK = True
except ImportError:
    ARABIC_SHAPING_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ── Colors ───────────────────────────────────────────
C_DARK   = HexColor("#0d1117") if REPORTLAB_OK else None
C_CARD   = HexColor("#161b22") if REPORTLAB_OK else None
C_HEADER = HexColor("#1f2937") if REPORTLAB_OK else None
C_GREEN  = HexColor("#238636") if REPORTLAB_OK else None
C_RED    = HexColor("#da3633") if REPORTLAB_OK else None
C_YELLOW = HexColor("#e3b341") if REPORTLAB_OK else None
C_BLUE   = HexColor("#58a6ff") if REPORTLAB_OK else None
C_TEXT   = HexColor("#e6edf3") if REPORTLAB_OK else None
C_MUTED  = HexColor("#8b949e") if REPORTLAB_OK else None

# كان db_path ثابتاً دائماً -- لا يحترم DB_PATH من .env إطلاقاً (نفس فئة
# الخلل المصلحة في db_manager.py/reverse_sync_to_sql.py). لأي مستأجر
# له DB_PATH مخصص، كان التقرير الشهري يُفتح قاعدة فارغة لا تحوي 
# master_tenders فينهار بـ "no such table: master_tenders". الإنتاج الحقيقي
# مافيشوش DB_PATH في .env أصلاً، فالسلوك القديم يفضل تماماً كما هو.
DB_PATH = Path(os.getenv("DB_PATH")) if os.getenv("DB_PATH", "").strip() else BASE_DIR / "output" / "tenders.db"
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH


def ar(text) -> str:
    """reportlab لا يطبّق خوارزمية Unicode (BiDi) ولا يصل الحروف العربية
    تلقائياً -- فيرسمها بالترتيب الحرفي الخام المدخل، مما يظهر معكوساً.
    هذه الدالة تعيد الوصل (arabic_reshaper) ثم ترتّب بصرياً للعرض (python-bidi)
    -- يجب تطبيقها على أي نص يمر لـ Paragraph/Table قبل التمرير مباشرة في reportlab.
    آمنة على النص الإنجليزي/الأرقام الصرفة (bidi لا يغيّرها).
    """
    if not text:
        return text
    text = str(text)
    if not ARABIC_SHAPING_OK:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def previous_month_start(now: datetime = None) -> datetime:
    """بداية الشهر المنتهي — ما يغطيه تقرير أول الشهر (كان يغطي الشهر الذي بدأ لتوّه فيخرج شبه فارغ)."""
    now = now or datetime.now()
    return (now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _get_report_data(month_start: datetime, month_end: datetime, today=None) -> dict:
    from demo_core import NOT_DEMO
    from tasks_core import ACTIVE_EXCLUDED, parse_deadline
    today = today or datetime.now().date()
    ex = ",".join("?" * len(ACTIVE_EXCLUDED))
    with closing(sqlite3.connect(str(DB_PATH))) as conn:
        conn.row_factory = sqlite3.Row

        active = conn.execute(
            f"SELECT COUNT(*) FROM master_tenders WHERE status NOT IN ({ex}) AND {NOT_DEMO}", ACTIVE_EXCLUDED
        ).fetchone()[0]

        closed_month = conn.execute(f"""
            SELECT COUNT(*) FROM master_tenders
            WHERE status='CLOSED' AND {NOT_DEMO}
            AND updated_at >= ? AND updated_at < ?
        """, (month_start.isoformat(), month_end.isoformat())).fetchone()[0]

        new_month = conn.execute(f"""
            SELECT COUNT(*) FROM master_tenders
            WHERE created_at >= ? AND created_at < ? AND {NOT_DEMO}
        """, (month_start.isoformat(), month_end.isoformat())).fetchone()[0]

        # Engineer loads
        engineers = conn.execute(f"""
            SELECT e.name, e.capacity,
                   COUNT(m.id) as tender_count
            FROM engineers e
            LEFT JOIN master_tenders m
                ON m.assigned_engineer = e.name
                AND m.status NOT IN ({ex}) AND m.{NOT_DEMO}
            WHERE e.is_active = 1
            GROUP BY e.name
            ORDER BY tender_count DESC
        """, ACTIVE_EXCLUDED).fetchall()

        # Upcoming deadlines (next 30 days) — التاريخ نصي بصيغتين (النور YYYY-MM-DD، الإدخال اليدوي
        # DD/MM/YYYY) فيُحلَّل في بايثون؛ مقارنة SQL النصية كانت تُسقط كل منافسات الإدخال اليدوي.
        upcoming = []
        for r in conn.execute(f"SELECT title, submission_date, assigned_engineer FROM master_tenders "
                              f"WHERE status NOT IN ({ex}) AND {NOT_DEMO}", ACTIVE_EXCLUDED):
            d = parse_deadline(r["submission_date"])
            if d and 0 <= (d - today).days <= 30:
                upcoming.append({**dict(r), "deadline": d, "days": (d - today).days})
        upcoming = sorted(upcoming, key=lambda u: u["deadline"])[:10]

        # Results this month
        results = conn.execute(f"""
            SELECT result, COUNT(*) as cnt FROM tender_results
            WHERE recorded_at >= ? AND recorded_at < ? AND {NOT_DEMO}
            GROUP BY result
        """, (month_start.isoformat(), month_end.isoformat())).fetchall()
        res_dict = {r["result"]: r["cnt"] for r in results}

    return {
        "active": active,
        "new_month": new_month,
        "closed_month": closed_month,
        "engineers": [dict(e) for e in engineers],
        "upcoming": upcoming,
        "won":  res_dict.get("won", 0),
        "lost": res_dict.get("lost", 0),
    }


def generate_pdf(month: datetime = None) -> bytes:
    if not REPORTLAB_OK:
        raise ImportError("reportlab غير مثبّت. شغّل: pip install reportlab")

    if month is None:
        month = datetime.now().replace(day=1)
    month_start = month.replace(day=1, hour=0, minute=0, second=0)
    next_month  = (month_start + timedelta(days=32)).replace(day=1)

    data = _get_report_data(month_start, next_month)
    month_name_ar = {
        1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",
        7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"
    }.get(month_start.month, str(month_start.month))
    partial = next_month > datetime.now()
    title_str = f"تقرير شهر {month_name_ar} {month_start.year}" + (" (حتى اليوم)" if partial else "")

    # ── Register Arabic font ──────────────────────────
    # Amiri مختار هنا عمداً بدل Tajawal (المستخدم في الويب/الداشبورد) -- reportlab لا يطبّق
    # تشكيل OpenType (GSUB) حقيقياً، فنعتمد على arabic_reshaper الذي يُخرج codepoints أشكال
    # العرض التقليدية (Presentation Forms) -- Tajawal لا يغطيها إلا جزئياً (89 من ~200)،
    # فيظهر مربعات فارغة لأحرف أساسية. Amiri يغطيها كاملة (140/140).
    font_path = BASE_DIR / "AI" / "Amiri-Regular.ttf"
    font_bold = BASE_DIR / "AI" / "Amiri-Bold.ttf"
    font_name = "Amiri"
    font_bold_name = "Amiri-Bold"

    # Fallback to system fonts if Tajawal not available
    if font_path.exists():
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    else:
        font_name = "Helvetica"

    if font_bold.exists():
        pdfmetrics.registerFont(TTFont(font_bold_name, str(font_bold)))
    else:
        font_bold_name = "Helvetica-Bold"

    styles = getSampleStyleSheet()

    def sty(size=10, bold=False, color=None, align="RIGHT"):
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
        al = {"RIGHT": TA_RIGHT, "CENTER": TA_CENTER, "LEFT": TA_LEFT}.get(align, TA_RIGHT)
        return ParagraphStyle(
            "custom",
            fontName=font_bold_name if bold else font_name,
            fontSize=size,
            textColor=color or C_TEXT,
            alignment=al,
            leading=size * 1.4,
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    story = []

    # ── Title Block ───────────────────────────────────
    from company_profile import PROFILE as _co
    _co_title = (_co.get("system_title") or "").strip() or "نظام متابعة المنافسات"
    story.append(Paragraph(ar(f"{_co_title} — متابعة المنافسات"), sty(20, bold=True, color=C_BLUE, align="CENTER")))   # بلا رموز تعبيرية: Amiri لا يرسمها
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(ar(title_str), sty(14, color=C_MUTED, align="CENTER")))
    story.append(Paragraph(ar(f"تاريخ الإصدار: {datetime.now().strftime('%Y-%m-%d')}"), sty(9, color=C_MUTED, align="CENTER")))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=C_HEADER))
    story.append(Spacer(1, 0.5*cm))

    # ── Summary Stats ─────────────────────────────────
    story.append(Paragraph(ar("ملخص الشهر"), sty(13, bold=True, color=C_BLUE)))
    story.append(Spacer(1, 0.3*cm))

    stats_data = [
        [ar("المنافسات النشطة"), ar("جديدة هذا الشهر"), ar("أُغلقت هذا الشهر"), ar("فزنا"), ar("خسرنا")],
        [str(data["active"]), str(data["new_month"]), str(data["closed_month"]),
         str(data["won"]), str(data["lost"])],
    ]
    st = Table(stats_data, colWidths=[3*cm]*5)
    st.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), C_HEADER),
        ("BACKGROUND",  (0,1), (-1,1), C_CARD),
        ("TEXTCOLOR",   (0,0), (-1,0), C_MUTED),
        ("TEXTCOLOR",   (0,1), (-1,1), C_TEXT),
        ("FONTNAME",    (0,0), (-1,-1), font_name),
        ("FONTNAME",    (0,1), (-1,1), font_bold_name),
        ("FONTSIZE",    (0,0), (-1,0), 9),
        ("FONTSIZE",    (0,1), (-1,1), 16),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [C_HEADER, C_CARD]),
        ("GRID",        (0,0), (-1,-1), 0.5, C_HEADER),
        ("TOPPADDING",  (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.7*cm))

    # ── Engineer Load ─────────────────────────────────
    story.append(Paragraph(ar("حمل المهندسين"), sty(13, bold=True, color=C_BLUE)))
    story.append(Spacer(1, 0.3*cm))

    eng_data = [[ar("المهندس"), ar("المنافسات المُسنَدة"), ar("الطاقة"), ar("نسبة الحمل")]]
    for e in data["engineers"]:
        cap  = max(e["capacity"] or 5, 1)
        pct  = min(round(e["tender_count"] / cap * 100), 100)
        eng_data.append([ar(e["name"]), str(e["tender_count"]), str(cap), f"{pct}%"])

    et = Table(eng_data, colWidths=[5*cm, 4*cm, 3*cm, 3*cm])
    et.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), C_GREEN),
        ("TEXTCOLOR",   (0,0), (-1,0), white),
        ("FONTNAME",    (0,0), (-1,-1), font_name),
        ("FONTNAME",    (0,0), (-1,0),  font_bold_name),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_CARD, C_HEADER]),
        ("TEXTCOLOR",   (0,1), (-1,-1), C_TEXT),
        ("GRID",        (0,0), (-1,-1), 0.5, C_HEADER),
        ("TOPPADDING",  (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0),(-1,-1), 7),
    ]))
    story.append(et)
    story.append(Spacer(1, 0.7*cm))

    # ── Upcoming Deadlines ────────────────────────────
    if data["upcoming"]:
        story.append(Paragraph(ar("المواعيد القادمة (30 يوماً)"), sty(13, bold=True, color=C_BLUE)))
        story.append(Spacer(1, 0.3*cm))

        up_data = [[ar("اسم المنافسة"), ar("تاريخ الإغلاق"), ar("المهندس")]]
        for u in data["upcoming"]:
            days_str = f"{u['deadline'].isoformat()}  ({u['days']} يوم)"
            title_short = (u["title"] or "")[:40] + ("…" if len(u["title"] or "") > 40 else "")
            up_data.append([ar(title_short), ar(days_str), ar(u["assigned_engineer"] or "—")])

        ut = Table(up_data, colWidths=[8*cm, 5*cm, 3*cm])
        ut.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), C_YELLOW),
            ("TEXTCOLOR",   (0,0), (-1,0), black),
            ("FONTNAME",    (0,0), (-1,-1), font_name),
            ("FONTNAME",    (0,0), (-1,0),  font_bold_name),
            ("FONTSIZE",    (0,0), (-1,-1), 9),
            ("ALIGN",       (0,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_CARD, C_HEADER]),
            ("TEXTCOLOR",   (0,1), (-1,-1), C_TEXT),
            ("GRID",        (0,0), (-1,-1), 0.5, C_HEADER),
            ("TOPPADDING",  (0,0), (-1,-1), 6),
            ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ]))
        story.append(ut)

    # ── Footer ────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_HEADER))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        ar(f"{_co_title} — تم الإنشاء تلقائياً بتاريخ {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
        sty(8, color=C_MUTED, align="CENTER")
    ))

    doc.build(story)
    return buf.getvalue()


def send_monthly_report(bot, chat_id: str, month: datetime = None):
    """Called from bot_daemon.py scheduler."""
    try:
        pdf_bytes = generate_pdf(month)
        month_now = month or datetime.now()
        month_name_ar = {
            1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",
            7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"
        }.get(month_now.month, str(month_now.month))
        from company_profile import PROFILE as _co
        _co_file = "".join(c for c in (_co.get("name_en") or "Tender").split()[0] if c.isalnum()) or "Tender"
        filename = f"{_co_file}_Report_{month_now.strftime('%Y-%m')}.pdf"
        caption  = (
            f"📄 *التقرير الشهري — {month_name_ar} {month_now.year}*\n"
            "━━━━━━━━━━━━\n"
            "تقرير PDF كامل يتضمن:\n"
            "• ملخص المنافسات النشطة والجديدة والمغلقة\n"
            "• حمل كل مهندس\n"
            "• المواعيد القادمة خلال 30 يوماً\n"
            "• نتائج الشهر (فوز/خسارة)"
        )
        bot.send_document(
            chat_id,
            document=io.BytesIO(pdf_bytes),
            visible_file_name=filename,
            caption=caption,
            parse_mode="Markdown"
        )
    except ImportError:
        bot.send_message(chat_id,
            "⚠️ مكتبة `reportlab` غير مثبّتة على السيرفر.\n"
            "شغّل: `pip install reportlab` ثم أعد المحاولة.",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ فشل إنشاء التقرير الشهري: `{str(e)[:200]}`",
                         parse_mode="Markdown")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if not REPORTLAB_OK:
        print("Install: pip install reportlab")
        sys.exit(1)
    pdf = generate_pdf()
    out = Path("test_report.pdf")
    out.write_bytes(pdf)
    print(f"PDF generated: {out} ({len(pdf)//1024} KB)")
    os.startfile(str(out))
