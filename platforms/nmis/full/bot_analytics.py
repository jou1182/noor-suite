# -*- coding: utf-8 -*-
"""/analytics and /trends commands.

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
from bot_core import bot, db, is_authorized, logger
# Prevent multiple instances globally (Windows + Linux)


# ============================================================
# ANALYTICS COMMANDS — Phase 3
# ============================================================

@bot.message_handler(commands=['analytics'])
def handle_analytics(message):
    """تقارير analytics اليومية والأسبوعية والشهرية."""
    if not is_authorized(message): return
    parts = message.text.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else ''

    try:
        from analytics_engine import (
            format_daily_report_for_telegram,
            format_weekly_report_for_telegram,
            AnalyticsEngine,
        )

        if sub == 'daily':
            msg = format_daily_report_for_telegram(db)
            bot.send_message(message.chat.id, msg, parse_mode='Markdown')

        elif sub == 'weekly':
            msg = format_weekly_report_for_telegram(db)
            bot.send_message(message.chat.id, msg, parse_mode='Markdown')

        elif sub == 'monthly':
            engine = AnalyticsEngine(db)
            report = engine.get_monthly_report()
            msg = (
                f"\U0001f4c5 *تقرير الشهر*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"\U0001f4cc {report.get('period', '')}\n\n"
                f"\U0001f7e2 مناقصات جديدة: {report.get('new_tenders', 0)}\n"
                f"✅ مناقصات مغلقة: {report.get('closed_tenders', 0)}\n"
                f"\U0001f4ca إجمالي نشطة: {report.get('total_active', 0)}\n"
            )
            bot.send_message(message.chat.id, msg, parse_mode='Markdown')

        else:
            help_msg = (
                "\U0001f4ca *أوامر Analytics:*\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "• `/analytics daily` — تقرير اليوم\n"
                "• `/analytics weekly` — تقرير الأسبوع\n"
                "• `/analytics monthly` — تقرير الشهر\n"
                "• `/trends` — تحليل القطاعات\n"
            )
            bot.send_message(message.chat.id, help_msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        bot.send_message(message.chat.id,
                         f"❌ خطأ في التحليل: `{str(e)[:150]}`",
                         parse_mode='Markdown')


@bot.message_handler(commands=['trends'])
def handle_trends(message):
    """تحليل اتجاهات القطاعات."""
    if not is_authorized(message): return
    try:
        from analytics_engine import AnalyticsEngine
        engine = AnalyticsEngine(db)
        trends = engine.get_sector_trends()

        msg = "\U0001f4c8 *تحليل اتجاهات القطاعات*\n━━━━━━━━━━━━━━━━━━━\n\n"

        sectors = trends.get('top_sectors', [])
        if sectors:
            msg += "\U0001f3c6 *أكثر القطاعات نشاطاً:*\n"
            for i, s in enumerate(sectors[:5], 1):
                msg += f"  {i}. {s.get('sector', '?')}: {s.get('count', 0)} مناقصة\n"
        else:
            msg += "لا توجد بيانات كافية للتحليل.\n"

        growth = trends.get('growth_rate')
        if growth is not None:
            icon = "\U0001f4c8" if growth >= 0 else "\U0001f4c9"
            msg += f"\n{icon} *معدل النمو:* {growth:+.1f}%\n"

        bot.send_message(message.chat.id, msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Trends error: {e}", exc_info=True)
        bot.send_message(message.chat.id,
                         f"❌ خطأ في التحليل: `{str(e)[:150]}`",
                         parse_mode='Markdown')

