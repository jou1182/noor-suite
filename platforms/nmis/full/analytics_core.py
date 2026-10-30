# -*- coding: utf-8 -*-
"""تحليلات المنافسات (2026-09-25) — منطق صفحة /analytics بلا Flask.

الفترة تُقاس بموعد إغلاق المنافسة (submission_date بأي من صيغتي YYYY-MM-DD و DD/MM/YYYY):
  month = منذ أول الشهر الحالي · q = منذ أول الشهر قبل شهرين · year = السنة الحالية · all = الكل.
كل النسب None عند غياب المقام، وكل «خلاصة» جملة عربية مبنية من الأرقام نفسها (لا نص ثابت).
الأسبوعان القادمان والضمانات ومخاطرة الجهات لا تتقيد بالفترة (نظرة للأمام / تاريخ الجهة كله).
"""
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta

from tasks_core import ACTIVE_EXCLUDED, parse_deadline

PERIODS = {"month": "هذا الشهر", "q": "آخر 3 أشهر", "year": "هذه السنة", "all": "الكل"}
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
GUARANTEE_DONE = ("READY", "SUBMITTED", "NOT_REQUIRED")


def _table(conn, name) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _pct(a, b):
    return round(100 * a / b) if b else None


def period_range(period: str, today: date):
    """(من، إلى) بموعد الإغلاق؛ None = بلا حد."""
    if period == "month":
        return today.replace(day=1), None
    if period == "q":
        m = today.month - 2
        y = today.year + (m - 1) // 12
        return date(y, (m - 1) % 12 + 1, 1), None
    if period == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    return None, None


def load_tenders(conn) -> list:
    """كل المنافسات مع نتيجتها وتاريخ إغلاقها المحلَّل."""
    has_results = _table(conn, "tender_results")
    sql = ("SELECT m.id, m.tender_id, m.title, m.owner, m.submission_date, m.business_type, m.sector, "
           "m.assigned_engineer, m.status" +
           (", r.did_submit, r.result, r.our_price, r.winning_price FROM master_tenders m "
            "LEFT JOIN tender_results r ON r.tender_id = m.tender_id" if has_results else
            ", NULL, NULL, NULL, NULL FROM master_tenders m"))
    out = []
    for r in conn.execute(sql):
        t = dict(zip(("id", "tender_id", "title", "owner", "raw_date", "business_type", "sector", "engineer",
                      "status", "did_submit", "result", "our_price", "winning_price"), r))
        t["deadline"] = parse_deadline(t["raw_date"])
        t["owner"] = (t["owner"] or "").strip() or "—"
        t["active"] = t["status"] not in ACTIVE_EXCLUDED
        t["cancelled"] = t["status"] == "DELETED" or t["result"] == "cancelled"
        t["submitted"] = bool(t["did_submit"])
        t["won"] = t["result"] == "won"
        out.append(t)
    return out


def _in_period(t, start, end) -> bool:
    if start is None and end is None:
        return True
    d = t["deadline"]
    return bool(d) and (start is None or d >= start) and (end is None or d <= end)


def kpis(tenders, period, today) -> dict:
    start, end = period_range(period, today)
    p = [t for t in tenders if _in_period(t, start, end)]
    submitted = [t for t in p if t["submitted"]]
    won = [t for t in submitted if t["won"]]
    cancelled = [t for t in p if t["cancelled"]]
    running = [t for t in p if t["active"]]
    week = [t for t in running if t["deadline"] and 0 <= (t["deadline"] - today).days <= 7]
    prev = None
    if period == "year":
        prev = sum(1 for t in tenders if t["deadline"] and t["deadline"].year == today.year - 1) or None
    return {
        "total": len(p), "total_prev": prev, "total_delta": _pct(len(p) - prev, prev) if prev else None,
        "running": len(running), "closing_week": len(week),
        "submitted": len(submitted), "submit_rate": _pct(len(submitted), len(p)),
        "won": len(won), "win_rate": _pct(len(won), len(submitted)),
        "cancelled": len(cancelled), "cancel_rate": _pct(len(cancelled), len(p)),
    }


def guarantees(conn, today) -> dict:
    if not _table(conn, "tender_guarantees"):
        return {"due14": 0, "next_days": None, "by_day": {}}
    by_day = Counter()
    for due, st in conn.execute("""SELECT g.due_date, g.status FROM tender_guarantees g
                                   JOIN master_tenders m ON m.id = g.tender_row_id
                                   WHERE m.status NOT IN (?,?,?)""", ACTIVE_EXCLUDED):
        d = parse_deadline(due)
        if d and st not in GUARANTEE_DONE and 0 <= (d - today).days <= 13:
            by_day[d.isoformat()] += 1
    days = sorted(by_day)
    return {"due14": sum(by_day.values()),
            "next_days": (date.fromisoformat(days[0]) - today).days if days else None,
            "by_day": dict(by_day)}


def _loads(conn) -> dict:
    """{مهندس: (منافسات نشطة، السعة)} للمهندسين الحاليين."""
    loads = {}
    for name, cap in conn.execute("SELECT name, capacity FROM engineers WHERE is_active=1"):
        n = conn.execute(f"SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer=? AND status NOT IN "
                         f"({','.join('?' * len(ACTIVE_EXCLUDED))})", (name, *ACTIVE_EXCLUDED)).fetchone()[0]
        loads[name] = (n, cap or 5)
    return loads


def two_weeks(conn, tenders, today) -> dict:
    """الأسبوعان القادمان: إغلاقات كل يوم + الضمانات + يوم الذروة ومن يحمله + اقتراح تخفيف."""
    g = guarantees(conn, today)
    days = []
    for i in range(14):
        d = today + timedelta(days=i)
        closing = [t for t in tenders if t["active"] and t["deadline"] == d]
        days.append({"date": d.isoformat(), "day": d.day, "weekday": DAYS[d.weekday()],
                     "weekend": d.weekday() in (4, 5), "closing": len(closing),
                     "guarantees": g["by_day"].get(d.isoformat(), 0),
                     "engineers": Counter(t["engineer"] for t in closing if t["engineer"])})
    peak = max(days, key=lambda x: x["closing"]) if any(x["closing"] for x in days) else None
    suggestion = None
    carriers = []
    if peak:
        carriers = [{"name": e, "count": n} for e, n in peak["engineers"].most_common()]
        loads = _loads(conn)
        busy = carriers[0]["name"] if carriers and carriers[0]["count"] > 1 else None
        free = sorted(((n / c, name) for name, (n, c) in loads.items() if name not in peak["engineers"]),
                      key=lambda x: x[0])
        if busy and free:
            n, c = loads[free[0][1]]
            suggestion = f"م. {busy} عنده {peak['engineers'][busy]} إغلاقات يوم الذروة — م. {free[0][1]} الأخف حملاً ({n}/{c})"
    for x in days:
        x["engineers"] = dict(x["engineers"])
    return {"days": days, "closing_total": sum(x["closing"] for x in days), "guarantees_total": g["due14"],
            "peak": {"date": peak["date"], "weekday": peak["weekday"], "day": peak["day"],
                     "closing": peak["closing"]} if peak else None,
            "carriers": carriers, "suggestion": suggestion}


def timeline(tenders, year) -> dict:
    series = {k: [0] * 12 for k in ("submitted", "won", "cancelled", "prev_submitted")}
    for t in tenders:
        d = t["deadline"]
        if not d:
            continue
        if d.year == year:
            if t["submitted"]:
                series["submitted"][d.month - 1] += 1
            if t["won"]:
                series["won"][d.month - 1] += 1
            if t["cancelled"]:
                series["cancelled"][d.month - 1] += 1
        elif d.year == year - 1 and t["submitted"]:
            series["prev_submitted"][d.month - 1] += 1
    active_months = [i for i, v in enumerate(series["submitted"]) if v]
    busiest = max(range(12), key=lambda i: series["submitted"][i]) if active_months else None
    return {"year": year, "months": MONTHS, **series,
            "has_prev": any(series["prev_submitted"]),
            "busiest": MONTHS[busiest] if busiest is not None else None,
            "monthly_avg": round(sum(series["submitted"]) / len(active_months), 1) if active_months else None}


def top_owners(tenders, period, today, limit=5) -> dict:
    start, end = period_range(period, today)
    sub = defaultdict(lambda: [0, 0])
    for t in tenders:
        if _in_period(t, start, end) and t["submitted"]:
            sub[t["owner"]][0] += 1
            sub[t["owner"]][1] += t["won"]
    rows = sorted(({"owner": o, "submitted": s, "won": w, "rate": _pct(w, s)} for o, (s, w) in sub.items()),
                  key=lambda r: (-r["rate"], -r["submitted"], r["owner"]))
    insight = None
    if len(rows) > 1:
        most = max(rows, key=lambda r: r["submitted"])
        if most is not rows[0] and most["rate"] < rows[0]["rate"]:
            insight = (f"الأكثر تقديماً ليست الأربح: {most['owner']} — {most['submitted']} تقديمات و"
                       f"{most['won']} فوز فقط.")
    return {"rows": rows[:limit], "insight": insight}


def distributions(tenders, period, today) -> dict:
    start, end = period_range(period, today)
    running = [t for t in tenders if t["active"] and _in_period(t, start, end)]
    owners = Counter(t["owner"] for t in running).most_common(6)
    types = Counter((t["business_type"] or "غير محدد") for t in running).most_common(6)
    sectors = Counter((t["sector"] or "غير محدد") for t in tenders if _in_period(t, start, end)).most_common(6)
    n_sec = sum(c for _, c in sectors)
    ins = {}
    if owners and len(running) >= 3:
        share = _pct(owners[0][1], len(running))
        if share >= 30:
            ins["owners"] = f"{share}% من العمل الجاري عند جهة واحدة ({owners[0][0]}) — تركّز مرتفع."
    by_type = defaultdict(lambda: [0, 0])
    for t in tenders:
        if t["submitted"]:
            by_type[t["business_type"] or "غير محدد"][0] += 1
            by_type[t["business_type"] or "غير محدد"][1] += t["won"]
    best = max(((w / s, k, s) for k, (s, w) in by_type.items() if s >= 2), default=None)
    if best and best[0] > 0:
        ins["types"] = f"فوزنا الأعلى في «{best[1]}» ({round(best[0] * 100)}% من {best[2]} مقدَّمة) — ركّز التقديم فيه."
    return {"owners": [{"k": k, "n": n} for k, n in owners],
            "types": [{"k": k, "n": n} for k, n in types],
            "sectors": [{"k": k, "n": n, "pct": _pct(n, n_sec)} for k, n in sectors],
            "insights": ins}


def owner_risk(tenders, min_total=2) -> list:
    """من يطرح ثم يلغي؟ تاريخ الجهة كله. المخاطرة: عالية ≥35% · متوسطة ≥15% · منخفضة."""
    agg = defaultdict(lambda: [0, 0])
    for t in tenders:
        agg[t["owner"]][0] += 1
        agg[t["owner"]][1] += t["cancelled"]
    rows = []
    for o, (n, c) in agg.items():
        if n < min_total or o == "—":
            continue
        rate = _pct(c, n)
        rows.append({"owner": o, "total": n, "cancelled": c, "rate": rate,
                     "level": "high" if rate >= 35 else ("medium" if rate >= 15 else "low")})
    return sorted(rows, key=lambda r: (-r["rate"], -r["total"]))


def owner_risk_level(tenders, owner) -> str:
    for r in owner_risk(tenders):
        if r["owner"] == owner:
            return r["level"]
    return ""


def wasted_effort(conn, tenders, period, today) -> dict:
    """مهام أُنجزت فعلاً على منافسات أُلغيت أو حُذفت من المنصة (من لوحة المهام)."""
    if not _table(conn, "tender_tasks"):
        return {"available": False}
    start, end = period_range(period, today)
    dead = {t["id"]: t for t in tenders if t["cancelled"] and _in_period(t, start, end)}
    rows, engineers, total = [], set(), 0
    for tid, t in dead.items():
        done = conn.execute("SELECT engineer FROM tender_tasks WHERE tender_row_id=? AND status='done'",
                            (tid,)).fetchall()
        if not done:
            continue
        names = sorted({d[0] for d in done if d[0]})
        engineers.update(names)
        total += len(done)
        rows.append({"id": tid, "title": t["title"], "owner": t["owner"], "tasks": len(done), "engineers": names})
    rows.sort(key=lambda r: -r["tasks"])
    insight = None
    if rows:
        worst = Counter()
        for r in rows:
            worst[r["owner"]] += r["tasks"]
        o, n = worst.most_common(1)[0]
        insight = f"أغلب الهدر عند «{o}» ({n} مهمة) — أجّل التسعير لديها حتى يثبت الطرح."
    return {"available": True, "tasks": total, "engineers": len(engineers), "tenders": len(rows),
            "rows": rows[:6], "insight": insight}


def compare(tenders, a: str, b: str) -> dict:
    def stats(owner):
        ts = [t for t in tenders if t["owner"] == owner]
        sub = [t for t in ts if t["submitted"]]
        gaps = [(t["our_price"] - t["winning_price"]) / t["winning_price"] * 100 for t in sub
                if t["our_price"] and t["winning_price"]]
        return {"owner": owner, "total": len(ts), "submit_rate": _pct(len(sub), len(ts)),
                "win_rate": _pct(sum(t["won"] for t in sub), len(sub)),
                "cancel_rate": _pct(sum(t["cancelled"] for t in ts), len(ts)),
                "price_gap": round(sum(gaps) / len(gaps), 1) if gaps else None}
    return {"a": stats(a), "b": stats(b)}


def report(conn, period="year", today: date = None) -> dict:
    today = today or date.today()
    if period not in PERIODS:
        period = "year"
    tenders = load_tenders(conn)
    k = kpis(tenders, period, today)
    g = guarantees(conn, today)
    k["guarantees14"], k["guarantee_next_days"] = g["due14"], g["next_days"]
    return {
        "period": period, "period_label": PERIODS[period], "today": today.isoformat(),
        "kpis": k, "two_weeks": two_weeks(conn, tenders, today), "timeline": timeline(tenders, today.year),
        "top_owners": top_owners(tenders, period, today), "dist": distributions(tenders, period, today),
        "risk": owner_risk(tenders)[:8], "waste": wasted_effort(conn, tenders, period, today),
        "owners": sorted({t["owner"] for t in tenders if t["owner"] != "—"}),
        "search": [{"id": t["id"], "title": t["title"], "owner": t["owner"]} for t in tenders][-800:],
    }


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn
