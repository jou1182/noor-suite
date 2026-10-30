# -*- coding: utf-8 -*-
"""تقرير الأداء الشهري PDF (2026-09-25) — صفحة للفريق + صفحة لكل مهندس، للإدارة فقط (مع لوحة المهام: kanban).

الأرقام نفسها التي تعرضها «المهندسون والتقييم» (/team): tasks_core.scorecards لفترة الشهر المحدد،
والحِمل والمفتوح والمتأخر لحظة الإصدار. يُرسل في أول كل شهر عن الشهر المنتهي إلى تليجرام الإدارة
(OWNER_TELEGRAM_ID) — لا إلى المجموعة: تقييم الأشخاص للإدارة فقط. وينزَّل من /team أيضاً.

reportlab لا يشكّل العربية ولا يطبّق BiDi: كل نص يمر بـ pdf_report.ar()، والجداول تُكتب بأعمدة معكوسة
(الأول يظهر يميناً)، والنصوص قصيرة في سطر واحد (التفاف سطر عربي معكوس يقلب ترتيب الأسطر).
الخط Amiri لا Tajawal: reportlab يحتاج أشكال العرض العربية كاملة، وTajawal لا يغطيها (انظر pdf_report).
"""
import base64
import io
from datetime import date, datetime, timedelta

import tasks_core
from pdf_report import ar
from tasks_core import ACTIVE_EXCLUDED, parse_deadline

MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
          "ديسمبر")
MIN_FOR_HIGHLIGHT = 3          # لا «الأعلى التزاماً» بمهمة أو اثنتين


# ── البيانات ─────────────────────────────────────────────────────────────
def month_bounds(month_first: date, today: date):
    nxt = (month_first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return month_first, min(nxt - timedelta(days=1), today)


def previous_month(today: date) -> date:
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def _short(text, n=46) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def collect(conn, month_first: date, today: date = None) -> dict:
    today = today or date.today()
    tasks_core.ensure_tables(conn)
    start, end = month_bounds(month_first, today)
    sc = tasks_core.scorecards(conn, today=today, start=start, end=end)
    s, e, now = start.isoformat(), end.isoformat(), today.isoformat()
    people = []
    for c in sc["engineers"]:
        done = [dict(zip(("title", "tender", "due", "done_at", "quality", "commitment", "note"), r)) for r in conn.execute("""
            SELECT t.title, m.title, t.due_date, t.done_at, r.quality, r.commitment, r.note FROM tender_tasks t
            LEFT JOIN master_tenders m ON m.id = t.tender_row_id LEFT JOIN task_ratings r ON r.task_id = t.id
            WHERE t.engineer=? AND t.status='done' AND t.done_at BETWEEN ? AND ? ORDER BY t.done_at, t.id""",
            (c["name"], s, e))]
        late = [dict(zip(("title", "tender", "due"), r)) for r in conn.execute("""
            SELECT t.title, m.title, t.due_date FROM tender_tasks t LEFT JOIN master_tenders m ON m.id = t.tender_row_id
            WHERE t.engineer=? AND t.status<>'done' AND t.due_date<>'' AND t.due_date<? ORDER BY t.due_date""",
            (c["name"], now))]
        for d in done:
            d["late_by"] = ((parse_deadline(d["done_at"]) - parse_deadline(d["due"])).days
                            if d["due"] and d["done_at"] else 0)
        for d in late:
            d["days"] = (today - parse_deadline(d["due"])).days
        people.append({**c, "tasks": done, "late_tasks": late,
                       "notes": [d for d in done if (d["note"] or "").strip()]})
    closing = sum(1 for (raw,) in conn.execute(
        "SELECT submission_date FROM master_tenders WHERE status <> 'REJECTED'")
        if (d := parse_deadline(raw)) and start <= d <= end)
    results = {"won": 0, "lost": 0, "submitted": 0}
    if tasks_core._table_exists(conn, "tender_results"):
        for did_submit, result in conn.execute("SELECT did_submit, result FROM tender_results "
                                               "WHERE substr(updated_at,1,10) BETWEEN ? AND ?", (s, e)):
            results["submitted"] += bool(did_submit)
            if result in ("won", "lost"):
                results[result] += 1
    active = conn.execute(f"SELECT COUNT(*) FROM master_tenders WHERE status NOT IN "
                          f"({','.join('?' * len(ACTIVE_EXCLUDED))})", ACTIVE_EXCLUDED).fetchone()[0]
    return {"month": month_first, "label": f"{MONTHS[month_first.month - 1]} {month_first.year}",
            "from": s, "to": e, "issued": today, "totals": sc["totals"], "engineers": people,
            "commitment": _avg([(c["commitment"], c["rated_n"]) for c in people if c["rated_n"]]),
            "closing": closing, "results": results, "active": active,
            "highlights": highlights(people)}


def _avg(pairs):
    n = sum(k for _, k in pairs)
    return round(sum(v * k for v, k in pairs) / n, 1) if n else None


def highlights(people) -> list:
    """جمل حقائق قصيرة عن الشهر — بلا حكم على الأشخاص خارج الأرقام."""
    out = []
    timely = [c for c in people if c["with_due_n"] >= MIN_FOR_HIGHLIGHT]
    if timely:
        best = max(timely, key=lambda c: (c["on_time"], c["with_due_n"]))
        out.append(f"الأعلى التزاماً بالمواعيد: م. {best['name']} — {best['on_time']}% من {best['with_due_n']} مهمة.")
    rated = [c for c in people if c["rated_n"] >= MIN_FOR_HIGHLIGHT]
    if rated:
        best = max(rated, key=lambda c: (c["quality"], c["rated_n"]))
        out.append(f"أعلى متوسط جودة: م. {best['name']} — {best['quality']} من 5 ({best['rated_n']} تقييم).")
    busiest = max(people, key=lambda c: c["done"], default=None)
    if busiest and busiest["done"]:
        out.append(f"الأكثر إنجازاً: م. {busiest['name']} — {busiest['done']} مهمة منتهية.")
    late = sorted((c for c in people if c["late"]), key=lambda c: -c["late"])
    if late:
        out.append("يحتاج متابعة الآن: " + "، ".join(f"م. {c['name']} ({c['late']} متأخرة)" for c in late[:3]) + ".")
    unrated = sum(c["done"] - c["rated_n"] for c in people)
    if unrated:
        out.append(f"{unrated} مهمة منتهية هذا الشهر بلا تقييم بعد — قيّمها من لوحة المهام.")
    return out


# ── الشعار: شعار الشركة المرفوع أو شعار نسختها فقط (لا الشعار المضمّن) ─────────
def logo_bytes(conn):
    try:
        row = conn.execute("SELECT value FROM app_config WHERE key='custom_logo_b64'").fetchone()
        if row and row[0]:
            return base64.b64decode(row[0])
    except Exception:
        pass
    from instance_paths import LOGO_FILE
    if LOGO_FILE and LOGO_FILE.exists():
        return LOGO_FILE.read_bytes()
    return None


# ── PDF ──────────────────────────────────────────────────────────────────
def build_pdf(data: dict, company: dict, logo: bytes = None) -> bytes:
    from pathlib import Path
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    base = Path(__file__).parent / "AI"
    font, bold = "Amiri", "Amiri-Bold"
    for name, f in ((font, "Amiri-Regular.ttf"), (bold, "Amiri-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(base / f)))

    ink = HexColor(company.get("theme_primary_d") or "#16233B")
    pri = HexColor(company.get("theme_primary") or "#1F4C8F")
    rule, film, mute = HexColor("#CBD5E1"), HexColor("#F2F5F9"), HexColor("#6B7A93")
    late_c, ok_c, lumen = HexColor("#B42318"), HexColor("#1F7A4C"), HexColor("#8A5A00")
    co_name = company.get("name_ar") or company.get("short_ar") or ""

    def st(size=10, b=False, color=ink, align=TA_RIGHT):
        return ParagraphStyle("s", fontName=bold if b else font, fontSize=size, leading=size * 1.45,
                              textColor=color, alignment=align)

    def P(text, **kw):
        return Paragraph(ar(text), st(**kw))

    def rtl(*cells):
        return list(reversed(cells))

    def num(v, suffix=""):
        return "—" if v is None else f"{v}{suffix}"

    def bar(pct, w=3.2 * cm, h=0.42 * cm):
        d = Drawing(w, h)
        d.add(Rect(0, 1, w, h - 2, fillColor=film, strokeColor=None))
        if pct is not None:
            color = ok_c if pct >= 85 else (lumen if pct >= 60 else late_c)
            d.add(Rect(w - w * pct / 100, 1, w * pct / 100, h - 2, fillColor=color, strokeColor=None))   # يملأ من اليمين
            d.add(String(3, 3.5, f"{pct}%", fontName=bold, fontSize=8, fillColor=white if pct > 20 else ink))
        return d

    def kpi_block(cells):
        """كتلة عنوان: صف تسميات + صف أرقام، بإطار ثقيل كلوحات المخططات."""
        t = Table([rtl(*[ar(c[0]) for c in cells]), rtl(*[c[1] for c in cells])],
                  colWidths=[17 * cm / len(cells)] * len(cells))
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.4, ink), ("INNERGRID", (0, 0), (-1, -1), 0.4, rule),
            ("FONTNAME", (0, 0), (-1, 0), font), ("FONTSIZE", (0, 0), (-1, 0), 8.5), ("TEXTCOLOR", (0, 0), (-1, 0), mute),
            ("FONTNAME", (0, 1), (-1, 1), bold), ("FONTSIZE", (0, 1), (-1, 1), 17), ("TEXTCOLOR", (0, 1), (-1, 1), ink),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, 1), 2), ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
        return t

    def grid(rows, widths, header_bg=ink):
        t = Table(rows, colWidths=list(reversed(widths)), repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), bold), ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("BACKGROUND", (0, 0), (-1, 0), header_bg), ("LINEBELOW", (0, 0), (-1, -1), 0.4, rule),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, film]), ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
        return t

    def header(title, *subs):
        right = [P(title, size=19, b=True)] + [P(s, size=9.5, color=mute) for s in subs]   # سطر لكل جزء: لا التفاف
        cells = [["", right]]
        if logo:
            img = Image(io.BytesIO(logo))
            ratio = img.imageWidth / float(img.imageHeight or 1)
            img.drawHeight, img.drawWidth = 1.5 * cm, min(1.5 * cm * ratio, 4.5 * cm)
            cells = [[img, right]]
        t = Table(cells, colWidths=[5 * cm, 12 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "LEFT"),
                               ("LINEBELOW", (0, 0), (-1, 0), 1.4, ink), ("BOTTOMPADDING", (0, 0), (-1, 0), 8)]))
        return t

    story = []
    t = data["totals"]
    story += [header(f"تقرير أداء الفريق — {data['label']}", co_name,
                     f"من {data['from']} إلى {data['to']} · أُصدر {data['issued']} · سري — للإدارة فقط"),
              Spacer(1, 0.5 * cm),
              kpi_block([("مهام منتهية", str(t["done"])), ("في الموعد", num(t["on_time"], "%")),
                         ("متوسط الجودة", num(t["quality"])), ("متوسط الالتزام", num(data["commitment"])),
                         ("متأخرة الآن", str(t["late"])), ("فوز الفريق", str(data["results"]["won"]))]),
              Spacer(1, 0.25 * cm),
              P(f"منافسات أُغلقت هذا الشهر: {data['closing']} · تقدّمنا لـ {data['results']['submitted']} · "
                f"خسرنا {data['results']['lost']} · منافسات نشطة الآن: {data['active']}", size=9, color=mute),
              Spacer(1, 0.45 * cm)]
    if data["highlights"]:
        story.append(P("أبرز ما في الشهر", size=13, b=True, color=pri))
        story += [P("• " + h, size=10) for h in data["highlights"]]
        story.append(Spacer(1, 0.45 * cm))
    story.append(P("مقارنة المهندسين", size=13, b=True, color=pri))
    story.append(Spacer(1, 0.15 * cm))
    rows = [rtl(*[ar(h) for h in ("المهندس", "منتهية", "في الموعد", "الجودة", "الالتزام", "متأخرة الآن", "الحِمل", "فزنا")])]
    for c in sorted(data["engineers"], key=lambda c: (-c["done"], c["name"])):
        rows.append(rtl(ar("م. " + c["name"]), str(c["done"]), bar(c["on_time"]), num(c["quality"]), num(c["commitment"]),
                        str(c["late"]), f"{c['load']}/{c['capacity']}", str(c["won"])))
    story.append(grid(rows, [3.3 * cm, 1.5 * cm, 3.6 * cm, 1.6 * cm, 1.7 * cm, 2 * cm, 1.6 * cm, 1.4 * cm]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(P("في الموعد = المهام المنتهية في تاريخ استحقاقها أو قبله · الجودة والالتزام من تقييم الإدارة (1–5) · "
                   "الحِمل = المنافسات النشطة / الطاقة", size=8, color=mute))

    for c in sorted(data["engineers"], key=lambda c: (-c["done"], c["name"])):   # نفس ترتيب جدول المقارنة
        if not (c["done"] or c["late"] or c["open"]):
            continue
        story += [PageBreak(), header(f"م. {c['name']} — {data['label']}", f"{co_name} · سري — للإدارة فقط"),
                  Spacer(1, 0.45 * cm),
                  kpi_block([("مهام منتهية", str(c["done"])), ("في الموعد", num(c["on_time"], "%")),
                             ("الجودة", num(c["quality"])), ("الالتزام", num(c["commitment"])),
                             ("مفتوحة الآن", str(c["open"])), ("متأخرة الآن", str(c["late"]))]),
                  Spacer(1, 0.45 * cm)]
        if c["tasks"]:
            story.append(P(f"ما أنجزه في {data['label']} ({len(c['tasks'])})", size=12.5, b=True, color=pri))
            rows = [rtl(*[ar(h) for h in ("المهمة", "المنافسة", "الاستحقاق", "أُنجزت", "الموعد", "جودة · التزام")])]
            for d in c["tasks"][:40]:
                timing = "—" if not d["due"] else ("في موعدها" if d["late_by"] <= 0 else f"بعد {d['late_by']} يوم")
                rate = f"{d['quality']} · {d['commitment']}" if d["quality"] else "—"
                rows.append(rtl(ar(_short(d["title"], 26)), ar(_short(d["tender"], 34)), d["due"] or "—",
                                d["done_at"], ar(timing), rate))
            story.append(grid(rows, [4 * cm, 5.2 * cm, 2 * cm, 2 * cm, 2.1 * cm, 1.7 * cm]))
            if len(c["tasks"]) > 40:
                story.append(P(f"و{len(c['tasks']) - 40} مهمة أخرى.", size=8.5, color=mute))
            story.append(P("جودة · التزام = تقييم الإدارة للمهمة من 5", size=8, color=mute))
            story.append(Spacer(1, 0.35 * cm))
        if c["late_tasks"]:
            rows = [rtl(*[ar(h) for h in ("المهمة", "المنافسة", "الاستحقاق", "متأخرة منذ")])]
            for d in c["late_tasks"][:20]:
                rows.append(rtl(ar(_short(d["title"], 30)), ar(_short(d["tender"], 40)), d["due"], ar(f"{d['days']} يوم")))
            story.append(KeepTogether([P(f"متأخرة الآن ({len(c['late_tasks'])})", size=12.5, b=True, color=late_c),
                                       grid(rows, [4.8 * cm, 6.8 * cm, 2.4 * cm, 3 * cm], header_bg=late_c)]))
            story.append(Spacer(1, 0.35 * cm))
        if c["notes"]:
            story.append(P("ملاحظات الإدارة", size=12.5, b=True, color=pri))
            story += [P(f"• {_short(d['title'], 30)}: {_short(d['note'], 90)}", size=9.5) for d in c["notes"][:8]]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(mute)
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, ar(f"{co_name} · تقرير الأداء — {data['label']} · سري"))
        canvas.drawString(2 * cm, 1.2 * cm, str(doc.page))
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=1.6 * cm, bottomMargin=2 * cm,
                      title=f"Performance {data['from'][:7]}", author=company.get("name_en") or "").build(
        story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def generate(conn, month_first: date = None, today: date = None):
    """(pdf bytes, اسم الملف, بيانات) — الشهر الافتراضي = الشهر المنتهي."""
    from company_profile import PROFILE
    today = today or date.today()
    month_first = month_first or previous_month(today)
    data = collect(conn, month_first, today)
    stem = "".join(ch for ch in (PROFILE.get("name_en") or "Team").split()[0] if ch.isalnum()) or "Team"
    return build_pdf(data, PROFILE, logo_bytes(conn)), f"{stem}_Performance_{month_first:%Y-%m}.pdf", data


def caption(data) -> str:
    t = data["totals"]
    return (f"📊 تقرير أداء الفريق — {data['label']}\n"
            f"منتهية {t['done']} · في الموعد {t['on_time'] if t['on_time'] is not None else '—'}% · "
            f"الجودة {t['quality'] if t['quality'] is not None else '—'} · متأخرة الآن {t['late']}\n"
            "صفحة للفريق + صفحة لكل مهندس. 🔒 للإدارة فقط.")


def send(bot, chat_ids, conn, month_first: date = None) -> int:
    """يرسل التقرير لكل محادثة إدارة. يرجع عدد المرسَل إليهم."""
    pdf, name, data = generate(conn, month_first)
    sent = 0
    for chat in chat_ids:
        bot.send_document(chat, document=io.BytesIO(pdf), visible_file_name=name, caption=caption(data))
        sent += 1
    return sent


if __name__ == "__main__":          # معاينة محلية: python performance_report.py [YYYY-MM]
    import sqlite3
    import sys
    from db_manager import DB_PATH
    m = datetime.strptime(sys.argv[1], "%Y-%m").date() if len(sys.argv) > 1 else None
    with sqlite3.connect(str(DB_PATH)) as c:
        pdf_, name_, _ = generate(c, m)
    open(name_, "wb").write(pdf_)
    print(name_, len(pdf_) // 1024, "KB")
