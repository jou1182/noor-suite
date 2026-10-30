# -*- coding: utf-8 -*-
"""
طلبات القوائم في الرسائل الصوتية (2026-09-23).

"اديني أسماء المنافسات…" بالصوت كان يُرسل للمساعد الذكي فيقرأ 22 اسماً في أكثر من دقيقة
ويختصر فيخطئ في العد (قال 3 منافسات صيانة للرياض والصحيح 4). الآن:
  • القائمة كاملة **نصاً** من قاعدة البيانات مباشرة (لا يكتبها الذكاء → لا خطأ في اسم أو عدد)
  • ملخص صوتي قصير من قالب ثابت باللهجة المختارة: العدد + أقرب موعد + "بعتلك القايمة مكتوبة"

مستقل عن تيليجرام ليسهل اختباره؛ bot_voice_ai يستدعيه.
"""
import re
import sqlite3
from datetime import datetime

import pandas as pd

from chat_handler import _detect_engineer, _detect_time_window

_LIST_WORDS = ("أسماء", "اسماء", "أسامي", "اسامي", "قائمة", "قايمة", "ليستة", "لستة",
               "اذكر", "إذكر", "عدّد", "سرد", "كل المنافسات", "كل المشاريع")
_TENDER_WORDS = ("منافس", "مناقص", "مشروع", "مشاريع")
_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
              "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
_TELEGRAM_CHUNK = 3800   # حد تيليجرام 4096 حرفاً للرسالة


def is_list_request(text: str) -> bool:
    t = text or ""
    return any(w in t for w in _LIST_WORDS) and any(w in t for w in _TENDER_WORDS)


def build_list(text: str, db_path) -> dict:
    """المنافسات النشطة المطلوبة (مع فلتر المهندس و/أو الفترة إن ذُكرا)، مرتبة بالموعد."""
    eng = _detect_engineer(text, db_path)
    # "الحين" = "دلوقتي" (الآن) وليست "اليوم" — في طلب قائمة تعني كل المنافسات الحالية
    window = _detect_time_window(text.replace("الحين", ""))
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT title, owner, submission_date, assigned_engineer FROM master_tenders "
            "WHERE status NOT IN ('CLOSED','REJECTED') ORDER BY date(submission_date)"
        ).fetchall()
    finally:
        con.close()
    items = []
    for r in rows:
        d = pd.to_datetime(r["submission_date"], errors="coerce")
        d = None if pd.isnull(d) else d.to_pydatetime().replace(tzinfo=None)
        if eng and (r["assigned_engineer"] or "") != eng:
            continue
        if window and not (d and window[1] <= d < window[2]):
            continue
        items.append({"title": r["title"], "owner": r["owner"] or "—", "date": d,
                      "eng": r["assigned_engineer"] or "—"})
    return {"items": items, "eng": eng, "window_label": window[0] if window else None}


def _scope(lst) -> str:
    parts = []
    if lst["eng"]:
        parts.append(f"مع {lst['eng']}")
    if lst["window_label"]:
        parts.append(lst["window_label"])
    return " ".join(parts)


def format_text(lst) -> list:
    """قائمة نصية بلا Markdown (العناوين قد تحوي * و _ فيرفض تيليجرام الرسالة)، مقسّمة لأجزاء."""
    items, scope = lst["items"], _scope(lst)
    head = f"📋 المنافسات النشطة{(' ' + scope) if scope else ''}: {len(items)}"
    if not items:
        return [head + "\n\nلا توجد منافسات مطابقة. ✅"]
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    lines = [head, "━━━━━━━━━━━━━━"]
    for i, it in enumerate(items, 1):
        if it["date"]:
            days = (it["date"].replace(hour=0, minute=0, second=0, microsecond=0) - today).days
            when = f"{it['date']:%Y-%m-%d}" + (" (اليوم)" if days == 0 else f" (بعد {days} يوم)" if days > 0 else " (انتهى)")
        else:
            when = "بدون موعد"
        lines.append(f"{i}. {it['title']}\n   🏢 {it['owner']} | 📅 {when} | 👷 {it['eng']}")
    chunks, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > _TELEGRAM_CHUNK:
            chunks.append(cur.rstrip())
            cur = ""
        cur += line + "\n"
    chunks.append(cur.rstrip())
    return chunks


_WINDOW_SPOKEN = {   # تسمية الفترة منطوقة حسب اللهجة
    "مصري":  {"غداً": "بكرة", "اليوم": "النهارده", "خلال 7 أيام": "خلال أسبوع",
              "خلال 30 يوم": "خلال شهر", "الأقرب موعداً": "خلال أسبوعين"},
    "خليجي": {"غداً": "بكرة", "اليوم": "اليوم", "خلال 7 أيام": "خلال أسبوع",
              "خلال 30 يوم": "خلال شهر", "الأقرب موعداً": "خلال أسبوعين"},
    "فصحى":  {"غداً": "غداً", "اليوم": "اليوم", "خلال 7 أيام": "خلال أسبوع",
              "خلال 30 يوم": "خلال شهر", "الأقرب موعداً": "خلال أسبوعين"},
}


def _count_phrase(n: int) -> str:
    """مطابقة العدد والمعدود: منافسة واحدة، منافستين، 3-10 منافسات، 11+ منافسة."""
    if n == 1:
        return "منافسة واحدة"
    if n == 2:
        return "منافستين"
    return f"{n} منافسات" if n <= 10 else f"{n} منافسة"


def _short_title(title: str, max_words: int = 8) -> str:
    """اسم مختصر للنطق: قبل أي قوس/شرطة/فاصلة، وبكلمات كاملة (لا قص في منتصف كلمة)."""
    head = re.split(r"[(\-–,،/]", title or "")[0].strip()
    words = head.split()
    return " ".join(words[:max_words]) if words else (title or "")


def voice_summary(lst, dialect: str = "مصري") -> str:
    """جملتان: العدد وأقرب موعد — من نفس القائمة المرسلة نصاً فلا يمكن أن يختلفا."""
    dialect = dialect if dialect in _WINDOW_SPOKEN else "مصري"
    items = lst["items"]
    n = len(items)
    eng = f" مع {lst['eng']}" if lst["eng"] else ""
    win = _WINDOW_SPOKEN[dialect].get(lst["window_label"], lst["window_label"]) if lst["window_label"] else ""
    dated = [it for it in items if it["date"]]
    nearest = min(dated, key=lambda it: it["date"]) if dated else None
    when = f"{nearest['date'].day} {_AR_MONTHS[nearest['date'].month - 1]}" if nearest else ""
    short = _short_title(nearest["title"]) if nearest else ""

    who = lst["eng"]
    if dialect == "خليجي":
        verb = f" تنتهي {win}" if win else " نشطة"
        if not n:
            return f"ما فيه منافسات{eng}{verb}{'' if win else ' حالياً'}."
        s = f"{who} عنده {_count_phrase(n)}{verb}." if who else f"عندنا {_count_phrase(n)}{verb}."
        if n == 1 and nearest:
            return s + f" هي {short}، تنتهي يوم {when}. وأرسلت لك تفاصيلها مكتوبة."
        if nearest:
            s += f" أقربها يوم {when}، وهي {short}."
        return s + " وأرسلت لك القائمة كاملة مكتوبة."
    if dialect == "فصحى":
        verb = f" تنتهي {win}" if win else " نشطة"
        if not n:
            return f"لا توجد منافسات{eng}{verb}{'' if win else ' حالياً'}."
        s = f"لدى {who} {_count_phrase(n)}{verb}." if who else f"لدينا {_count_phrase(n)}{verb}."
        if n == 1 and nearest:
            return s + f" وهي {short}، وتنتهي في {when}. وأرسلتُ لك تفاصيلها مكتوبة."
        if nearest:
            s += f" أقربها موعداً في {when}، وهي {short}."
        return s + " وأرسلتُ لك القائمة كاملة مكتوبة."
    verb = f" بتخلص {win}" if win else " نشطة"
    if not n:
        return f"مفيش منافسات{eng}{verb}{'' if win else ' دلوقتي'}."
    s = f"أيوه، {who} معاه {_count_phrase(n)}{verb}." if who else f"أيوه، عندنا {_count_phrase(n)}{verb}."
    if n == 1 and nearest:
        return s + f" هي {short}، وبتخلص يوم {when}. وبعتلك تفاصيلها مكتوبة."
    if nearest:
        s += f" أقربهم بتخلص يوم {when}، وهي {short}."
    return s + " وبعتلك القايمة كاملة مكتوبة."
