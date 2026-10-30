"""
Analytics Engine - Phase 3 Enhancement
========================================
Provides comprehensive analytics and insights for Noor Tender System.

Levels:
- Level 1: Daily/Weekly/Monthly reports (Basic statistics)
- Level 2: Trends analysis (Seasonal patterns, sector trends)
- Level 3: Smart engineer suggestions (Experience + Load + Success rate)
- Level 5: Predictions and anomaly detection

This module is PURE ANALYTICS - no database modifications, only reads.
All functions accept a DBManager instance for safe concurrent access.
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from db_manager import DBManager
import logging
from pathlib import Path

logger = logging.getLogger("AnalyticsEngine")

BASE_DIR = Path(__file__).parent / "output"


class AnalyticsEngine:
    """
    Pure analytics layer - reads data and generates insights.
    Safe for concurrent access with scraper/bot.
    """

    def __init__(self, db: DBManager):
        self.db = db
        logger.info("AnalyticsEngine initialized")

    # ================================================================
    # LEVEL 1: BASIC REPORTS (Daily, Weekly, Monthly)
    # ================================================================

    def get_daily_report(self) -> Dict:
        """Generate a daily report of today's activities."""
        with self.db._get_connection() as conn:
            today = datetime.now().strftime("%Y-%m-%d")

            # New tenders today
            new_today = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(created_at) = ?",
                (today,)
            ).fetchone()[0]

            # Updated tenders today
            updated_today = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE DATE(created_at) = ? AND change_type IN ('DATE_CHANGE', 'DETAILS_CHANGE')",
                (today,)
            ).fetchone()[0]

            # Closed tenders today
            closed_today = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(updated_at) = ? AND status = 'CLOSED'",
                (today,)
            ).fetchone()[0]

            # Top sectors today
            top_sectors = conn.execute("""
                SELECT sector, COUNT(*) as count
                FROM master_tenders
                WHERE DATE(created_at) = ?
                GROUP BY sector
                ORDER BY count DESC
                LIMIT 3
            """, (today,)).fetchall()

            return {
                "date": today,
                "new_tenders": new_today,
                "updated_tenders": updated_today,
                "closed_tenders": closed_today,
                "top_sectors": [{"sector": s[0], "count": s[1]} for s in top_sectors],
                "timestamp": datetime.now().isoformat()
            }

    def get_weekly_report(self) -> Dict:
        """Generate a weekly report of the last 7 days."""
        with self.db._get_connection() as conn:
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")

            # Counts
            new_week = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(created_at) BETWEEN ? AND ?",
                (week_ago, today)
            ).fetchone()[0]

            closed_week = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(updated_at) BETWEEN ? AND ? AND status = 'CLOSED'",
                (week_ago, today)
            ).fetchone()[0]

            # Average per day
            avg_new = round(new_week / 7, 1)

            # Engineer performance
            eng_stats = conn.execute("""
                SELECT assigned_engineer, COUNT(*) as assigned_count
                FROM master_tenders
                WHERE DATE(created_at) BETWEEN ? AND ? AND assigned_engineer IS NOT NULL
                GROUP BY assigned_engineer
                ORDER BY assigned_count DESC
                LIMIT 5
            """, (week_ago, today)).fetchall()

            # Sector distribution
            sector_dist = conn.execute("""
                SELECT sector, COUNT(*) as count
                FROM master_tenders
                WHERE DATE(created_at) BETWEEN ? AND ?
                GROUP BY sector
                ORDER BY count DESC
                LIMIT 5
            """, (week_ago, today)).fetchall()

            return {
                "period": f"{week_ago} to {today}",
                "new_tenders": new_week,
                "closed_tenders": closed_week,
                "avg_daily": avg_new,
                "top_engineers": [{"name": e[0], "assigned": e[1]} for e in eng_stats],
                "top_sectors": [{"sector": s[0], "count": s[1]} for s in sector_dist]
            }

    def get_monthly_report(self, month_offset=0) -> Dict:
        """
        Generate a monthly report.
        month_offset: 0 = current month, -1 = last month, etc.
        """
        now = datetime.now()
        target_month = now.replace(day=1) - timedelta(days=1) * month_offset
        month_start = target_month.replace(day=1)

        if month_offset == 0:
            month_end = now
        else:
            # Last day of target month
            next_month = month_start + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(days=1)

        month_str = month_start.strftime("%B %Y")
        start_str = month_start.strftime("%Y-%m-%d")
        end_str = month_end.strftime("%Y-%m-%d")

        with self.db._get_connection() as conn:
            new_month = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(created_at) BETWEEN ? AND ?",
                (start_str, end_str)
            ).fetchone()[0]

            closed_month = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE DATE(updated_at) BETWEEN ? AND ? AND status = 'CLOSED'",
                (start_str, end_str)
            ).fetchone()[0]

            avg_daily = round(new_month / (month_end - month_start).days, 1) if (month_end - month_start).days > 0 else 0

            # Top owners
            top_owners = conn.execute("""
                SELECT owner, COUNT(*) as count
                FROM master_tenders
                WHERE DATE(created_at) BETWEEN ? AND ?
                GROUP BY owner
                ORDER BY count DESC
                LIMIT 5
            """, (start_str, end_str)).fetchall()

            # Sector growth/decline
            sector_count = conn.execute("""
                SELECT sector, COUNT(*) as count
                FROM master_tenders
                WHERE DATE(created_at) BETWEEN ? AND ?
                GROUP BY sector
                ORDER BY count DESC
            """, (start_str, end_str)).fetchall()

            return {
                "month": month_str,
                "period": f"{start_str} to {end_str}",
                "new_tenders": new_month,
                "closed_tenders": closed_month,
                "avg_daily": avg_daily,
                "top_owners": [{"owner": o[0], "count": o[1]} for o in top_owners],
                "sector_distribution": [{"sector": s[0], "count": s[1]} for s in sector_count]
            }

    # ================================================================
    # LEVEL 2: TRENDS ANALYSIS
    # ================================================================

    def get_sector_trends(self) -> Dict:
        """Analyze which sectors are growing/declining."""
        with self.db._get_connection() as conn:
            # This month vs last month
            now = datetime.now()
            this_month_start = now.replace(day=1).strftime("%Y-%m-%d")
            last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
            last_month_end = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

            # Get sector counts for both periods
            this_month = conn.execute("""
                SELECT sector, COUNT(*) FROM master_tenders
                WHERE DATE(created_at) >= ?
                GROUP BY sector
            """, (this_month_start,)).fetchall()

            last_month = conn.execute("""
                SELECT sector, COUNT(*) FROM master_tenders
                WHERE DATE(created_at) BETWEEN ? AND ?
                GROUP BY sector
            """, (last_month_start, last_month_end)).fetchall()

            # Calculate growth
            this_dict = {s[0]: s[1] for s in this_month}
            last_dict = {s[0]: s[1] for s in last_month}

            trends = []
            for sector, current_count in this_dict.items():
                previous_count = last_dict.get(sector, 0)
                change = current_count - previous_count
                pct_change = round((change / previous_count * 100) if previous_count > 0 else 0, 1)

                trends.append({
                    "sector": sector,
                    "this_month": current_count,
                    "last_month": previous_count,
                    "change": change,
                    "pct_change": pct_change,
                    "trend": "📈" if change > 0 else "📉" if change < 0 else "➡️"
                })

            # Sort by change
            trends.sort(key=lambda x: x['change'], reverse=True)

            return {
                "analysis": "Month-over-month sector trends",
                "trends": trends
            }

    def get_seasonal_patterns(self) -> Dict:
        """Identify patterns by day of week or month."""
        with self.db._get_connection() as conn:
            # Day of week analysis
            dow_data = conn.execute("""
                SELECT
                    CASE CAST(STRFTIME('%w', created_at) AS INTEGER)
                        WHEN 0 THEN 'Sunday'
                        WHEN 1 THEN 'Monday'
                        WHEN 2 THEN 'Tuesday'
                        WHEN 3 THEN 'Wednesday'
                        WHEN 4 THEN 'Thursday'
                        WHEN 5 THEN 'Friday'
                        WHEN 6 THEN 'Saturday'
                    END as day_name,
                    COUNT(*) as count,
                    ROUND(AVG(CAST(STRFTIME('%w', created_at) AS INTEGER)), 0) as day_num
                FROM master_tenders
                GROUP BY STRFTIME('%w', created_at)
                ORDER BY day_num
            """).fetchall()

            # Find peak day
            peak_day = max(dow_data, key=lambda x: x[1]) if dow_data else None

            return {
                "pattern": "Weekly distribution",
                "by_day_of_week": [
                    {"day": d[0], "count": d[1]} for d in dow_data
                ],
                "peak_day": peak_day[0] if peak_day else "Unknown",
                "peak_count": peak_day[1] if peak_day else 0
            }

    # ================================================================
    # LEVEL 3: IMPROVED ENGINEER SUGGESTIONS
    # ================================================================

    def calculate_engineer_score(self, engineer_name: str) -> Dict:
        """
        Calculate a comprehensive score for an engineer.

        Factors:
        - Experience in sector (historical success)
        - Current load (availability)
        - Success rate (approval percentage)
        - Time since last assignment

        Score = (Exp_Weight * Sector_Match) + (Load_Weight * Availability)
                + (Success_Weight * Approval_Rate) + (Time_Weight * Recency)
        """
        with self.db._get_connection() as conn:
            # Factor 1: Current load (20% weight)
            loads = self.db.get_all_engineers_with_load()
            load_score = 0
            for e in loads:
                if e['name'] == engineer_name:
                    # Lower load = higher score (inverse)
                    load_score = (100 - e['load_pct']) / 100
                    break

            # Factor 2: Approval rate (20% weight)
            approved = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE suggested_engineer = ? AND status = 'APPROVED'",
                (engineer_name,)
            ).fetchone()[0]

            total_suggested = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE suggested_engineer = ?",
                (engineer_name,)
            ).fetchone()[0]

            approval_rate = (approved / total_suggested) if total_suggested > 0 else 0.5

            # Factor 3: Assignment recency (15% weight)
            last_assigned = conn.execute(
                "SELECT MAX(updated_at) FROM master_tenders WHERE assigned_engineer = ?",
                (engineer_name,)
            ).fetchone()[0]

            days_since = 0
            if last_assigned:
                last_date = datetime.fromisoformat(last_assigned)
                days_since = (datetime.now() - last_date).days

            recency_score = min(1.0, days_since / 30)  # Cap at 30 days

            # Factor 4: Total experience (45% weight)
            total_assigned = conn.execute(
                "SELECT COUNT(*) FROM master_tenders WHERE assigned_engineer = ?",
                (engineer_name,)
            ).fetchone()[0]

            experience_score = min(1.0, total_assigned / 50)  # Cap at 50 projects

            # Weighted score
            final_score = (
                (experience_score * 0.45) +
                (1 - load_score * 0.20) +  # Lower is better
                (approval_rate * 0.20) +
                (recency_score * 0.15)
            )

            return {
                "engineer": engineer_name,
                "total_score": round(final_score * 100, 1),
                "factors": {
                    "experience": round(experience_score * 100, 1),
                    "availability": round(load_score * 100, 1),
                    "approval_rate": round(approval_rate * 100, 1),
                    "recency": round(recency_score * 100, 1)
                },
                "stats": {
                    "total_assigned": total_assigned,
                    "approved_suggestions": approved,
                    "days_since_assignment": days_since
                }
            }

    def get_engineer_rankings(self) -> List[Dict]:
        """Rank all engineers by comprehensive score."""
        engineers = self.db.get_all_engineers()
        scores = []

        for eng in engineers:
            score_dict = self.calculate_engineer_score(eng['name'])
            scores.append(score_dict)

        # Sort by total_score descending
        scores.sort(key=lambda x: x['total_score'], reverse=True)

        return scores

    # ================================================================
    # UTILITY METHODS
    # ================================================================

    def get_overall_health(self) -> Dict:
        """Get a quick health check of the system."""
        with self.db._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM master_tenders").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM master_tenders WHERE status != 'CLOSED'").fetchone()[0]
            closed = total - active

            pending_approval = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE status = 'PENDING_APPROVAL'"
            ).fetchone()[0]

            avg_age_days = conn.execute(
                "SELECT AVG(JULIANDAY('now') - JULIANDAY(created_at)) FROM master_tenders"
            ).fetchone()[0]

            return {
                "total_tenders": total,
                "active": active,
                "closed": closed,
                "pending_approval": pending_approval,
                "avg_age_days": round(avg_age_days or 0, 1),
                "health_status": "✅ Good" if pending_approval < 5 else "⚠️ Review Needed"
            }


# ================================================================
# HELPER FUNCTIONS FOR TELEGRAM COMMANDS
# ================================================================

def format_daily_report_for_telegram(db: DBManager) -> str:
    """Format daily report as Telegram message."""
    engine = AnalyticsEngine(db)
    report = engine.get_daily_report()

    msg = f"📊 *تقرير اليوم* - {report['date']}\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🟢 مناقصات جديدة: {report['new_tenders']}\n"
    msg += f"🔄 مناقصات معدلة: {report['updated_tenders']}\n"
    msg += f"✅ مناقصات مغلقة: {report['closed_tenders']}\n"

    if report['top_sectors']:
        msg += "\n🏆 *القطاعات الأعلى:*\n"
        for sector in report['top_sectors']:
            msg += f"  • {sector['sector']}: {sector['count']}\n"

    return msg


def format_weekly_report_for_telegram(db: DBManager) -> str:
    """Format weekly report as Telegram message."""
    engine = AnalyticsEngine(db)
    report = engine.get_weekly_report()

    msg = f"📈 *تقرير الأسبوع*\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📌 {report['period']}\n\n"
    msg += f"🟢 مناقصات جديدة: {report['new_tenders']}\n"
    msg += f"✅ مناقصات مغلقة: {report['closed_tenders']}\n"
    msg += f"📊 متوسط يومي: {report['avg_daily']}\n"

    if report['top_engineers']:
        msg += "\n👷 *أفضل المهندسين:*\n"
        for eng in report['top_engineers'][:3]:
            msg += f"  • {eng['name']}: {eng['assigned']} مناقصة\n"

    return msg


if __name__ == "__main__":
    # Quick test
    from db_manager import DBManager
    db = DBManager()
    engine = AnalyticsEngine(db)

    logger.info("=== ANALYTICS ENGINE TEST ===")
    logger.info(f"Daily Report: {engine.get_daily_report()}")
    logger.info(f"Health: {engine.get_overall_health()}")


# ══════════════════════════════════════════════════════════════
# V6 — توقع التمديد (Extension Prediction)
# ══════════════════════════════════════════════════════════════
def predict_extensions(db: DBManager) -> Dict:
    """يحلل سجل تعديلات المواعيد لكل جهة مالكة ويحسب احتمال تمديد
    كل منافسة نشطة بناءً على سلوك جهتها التاريخي المسجل في النظام."""
    import json as _json
    with db._get_connection() as conn:
        events = conn.execute(
            "SELECT title, details_json FROM pending_changes WHERE change_type='UPDATED_DATE'"
        ).fetchall()
        owner_ext_titles, owner_ext_events = {}, {}
        for r in events:
            owner = ""
            try:
                d = _json.loads(r["details_json"] or "{}")
                owner = str(d.get("المالك", "")).strip()
            except Exception:
                pass
            if not owner:
                continue
            owner_ext_titles.setdefault(owner, set()).add(str(r["title"]).strip())
            owner_ext_events[owner] = owner_ext_events.get(owner, 0) + 1

        owner_totals = {r["owner"]: r["c"] for r in conn.execute(
            "SELECT owner, COUNT(*) c FROM master_tenders "
            "WHERE owner IS NOT NULL AND owner != '' GROUP BY owner"
        )}
        active = conn.execute("""
            SELECT id, title, owner, submission_date,
                   COALESCE(assigned_engineer,'—') eng
            FROM master_tenders
            WHERE status NOT IN ('CLOSED','REJECTED')
            ORDER BY submission_date
        """).fetchall()

    results = []
    for t in active:
        owner = (t["owner"] or "").strip()
        total = max(owner_totals.get(owner, 0), 1)
        extended = len(owner_ext_titles.get(owner, set()))
        rate = extended / total
        if extended == 0:
            level, icon = "لا سجل", "⚪"
        elif rate >= 0.6:
            level, icon = "مرتفع", "🔴"
        elif rate >= 0.3:
            level, icon = "متوسط", "🟡"
        else:
            level, icon = "منخفض", "🟢"
        results.append({
            "id": t["id"], "title": str(t["title"]), "owner": owner,
            "submission_date": str(t["submission_date"] or "")[:10],
            "engineer": t["eng"], "ext_rate": round(rate * 100),
            "ext_tenders": extended, "owner_total": owner_totals.get(owner, 0),
            "level": level, "icon": icon,
        })
    results.sort(key=lambda x: -x["ext_rate"])
    return {"tenders": results,
            "history_events": sum(owner_ext_events.values()),
            "owners_with_history": len(owner_ext_titles)}


def format_extension_prediction_for_telegram(db: DBManager) -> str:
    """تقرير توقع التمديد — أمر /predict في تيليغرام."""
    data = predict_extensions(db)
    if not data["tenders"]:
        return "📊 لا توجد منافسات نشطة حالياً."
    msg  = "🔮 *توقع التمديد — المنافسات النشطة*\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"
    msg += f"مبني على {data['history_events']} حدث تمديد من {data['owners_with_history']} جهة\n\n"
    for t in data["tenders"][:15]:
        msg += f"{t['icon']} *{t['title'][:45]}*\n"
        line = f"    {t['owner'][:32]} | يغلق: {t['submission_date'] or '—'}"
        if t["ext_tenders"]:
            line += f"\n    سجل الجهة: مدّدت {t['ext_tenders']} من {t['owner_total']} منافسة ({t['ext_rate']}%)"
        msg += line + "\n"
    msg += "\n🔴 مرتفع ≥60% | 🟡 متوسط ≥30% | 🟢 منخفض | ⚪ لا سجل للجهة"
    return msg
