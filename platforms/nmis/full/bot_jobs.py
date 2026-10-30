# -*- coding: utf-8 -*-
"""Scheduled jobs and the scheduler thread.

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
import os
import schedule
import sys
import time
from datetime import datetime
from db_manager import DB_PATH
import demo_core
from demo_core import NOT_DEMO  # وضع العرض لا يصل تليجرام
from bot_core import ALLOW_AUTONOMOUS_LOGIN, BACKUP_ALERT_FILE, BASE_DIR, CHAT_ID, CHECK_INTERVAL, CO_SHORT, CO_TEAM, PDF_OK, SESSION_ALERT_FILE, SESSION_FAIL_ALERT_AFTER, _backup_lock, _job_lock, _send_pdf, bot, db, is_paused, load_state, logger, ping_uptimerobot, save_state, send_backup_failure_alert, send_session_expired_alert, utc_now_iso
from pdf_report import previous_month_start
from bot_notifications import _ensure_subs_table, _personal_digest, _send_guarantee_cards, notify_pending_changes
def job_monthly_report(month=None):
    """Fires on 1st of each month at 09:00 for the month that just ended (/report: this month so far)."""
    if not PDF_OK:
        logger.warning("job_monthly_report: pdf_report module not available, skipping.")
        return
    logger.info("Sending monthly PDF report...")
    try:
        _send_pdf(bot, CHAT_ID, month)
        logger.info("Monthly PDF report sent successfully.")
    except Exception as e:
        logger.error(f"Monthly report failed: {e}")
        bot.send_message(CHAT_ID, f"⚠️ فشل إرسال التقرير الشهري: `{str(e)[:200]}`", parse_mode="Markdown")

def job_demo_nightly():
    """03:00: تجديد بيانات «وضع العرض» بتاريخ اليوم إن فعّلته الإدارة (demo_core.nightly_refresh). بلا رسائل."""
    import sqlite3
    from contextlib import closing
    import demo_core
    import source_core
    from company_profile import feature_enabled
    if not feature_enabled(demo_core.FEATURE):
        return
    try:
        with closing(sqlite3.connect(str(DB_PATH))) as conn:
            counts = demo_core.nightly_refresh(conn, manual=source_core.is_manual_instance())
            conn.commit()
        if counts:
            import bot_tasks
            bot_tasks._push_board_refresh()
            logger.info(f"Demo nightly refresh: {counts}")
    except Exception as e:
        logger.error(f"job_demo_nightly failed: {e}")

def job_engineer_digests():
    """v5.7: ملخص صباحي خاص لكل مهندس مشترك (08:15)."""
    if is_paused():
        return
    try:
        with db._get_connection() as conn:
            _ensure_subs_table(conn)
            subs = conn.execute("SELECT chat_id, engineer_name FROM engineer_subs").fetchall()
        sent = 0
        for cid, eng in subs:
            digest = _personal_digest(eng)
            if digest:
                try:
                    bot.send_message(cid, digest)
                    sent += 1
                except Exception as e:
                    logger.debug(f"digest to {eng}/{cid} failed: {e}")
        logger.info(f"Engineer digests sent: {sent}/{len(subs)}.")
    except Exception as e:
        logger.error(f"job_engineer_digests failed: {e}")


# ============================================================
# 6. MAIN HEARTBEAT JOB (Runs every N minutes)
# ============================================================
def job_check_platform():
    """The primary scheduled heartbeat function."""
    # JOB OVERLAP GUARD: non-blocking acquire
    if not _job_lock.acquire(blocking=False):
        logger.warning("job_check_platform: Previous cycle still running - SKIPPING this trigger to prevent duplicate notifications.")
        return
    try:
        save_state(last_check_at=utc_now_iso(), last_result="running")
        if is_paused():
            logger.info("Scheduled check skipped because bot sync is paused by admin.")
            save_state(last_result="paused")
            return

        logger.info(f"{'='*20} Scheduled Check Started {'='*20}")

        # STEP A: تعطيل reverse_sync التلقائي — يُشغَّل فقط عند رفع Excel يدوياً
        # (تعطيل: كان يُعيد كتابة تعيينات المهندسين من Excel القديم كل دورة)
        # try:
        #     import reverse_sync_to_sql
        #     reverse_sync_to_sql.reverse_sync()
        #     logger.info("Excel -> SQL sync completed successfully.")
        # except Exception as e:
        #     logger.error(f"Automatic Excel Sync failed: {e}")

        # STEP A2 (2026-09-25): مصدر الإدخال اليدوي من رابط Google — يُسحب قبل المقارنة إن فُعّلت المزامنة
        import source_core
        if source_core.is_manual_instance():
            try:
                with db._get_connection() as _sc:
                    note = source_core.auto_sync(_sc)
                    _sc.commit()
                if note:
                    logger.info(f"Manual source auto-sync: {note}")
            except Exception as e:
                logger.warning(f"Manual source auto-sync failed (keeping current file): {e}")
        save_state(manual_source_mtime=_manual_mtime())

        # STEP B: Run the portal scraper and compare with Master DB
        import engine_core
        staged_count = engine_core.find_and_stage_changes()

        if staged_count == -1:
            # 🛡️ AUTONOMOUS RECOVERY (V4.1 Cyber-Resilience Feature)
            if not ALLOW_AUTONOMOUS_LOGIN:
                logger.error(
                    "Session failure detected, but Microsoft SSO auto-login is disabled. "
                    "Keeping MFA quiet; manual noVNC login is required if cookies expire."
                )
            else:
                logger.warning("Session failure detected. Attempting autonomous server-side refresh...")
                import subprocess
                try:
                    # Try to refresh cookies directly on the server (Watchdog Timeout = 4 minutes)
                    result = subprocess.run([sys.executable, "server_autonomous_sync.py"], capture_output=True, text=True, timeout=240)
                    if "Login Success" in result.stdout:
                        logger.info("✨ Autonomous recovery SUCCESS! Retrying scraper...")
                        staged_count = engine_core.find_and_stage_changes()
                    else:
                        logger.error(f"❌ Autonomous recovery failed: {result.stderr}")
                except subprocess.TimeoutExpired:
                    logger.error("🛑 WATCHDOG ALERT: Autonomous scraper froze for > 4 minutes! Killing process.")
                    if os.name == 'nt':
                        os.system("taskkill /F /IM chromedriver.exe >nul 2>&1")
                    else:
                        os.system("pkill -f chromedriver || true; pkill -f google-chrome || true")
                except Exception as e:
                    logger.error(f"Critical error during recovery attempt: {e}")

        if staged_count == -1:
            # STILL FAILED. Alert only after consecutive failures — a single
            # portal timeout is common and recovers on the next cycle.
            fails = int(load_state().get("consecutive_fetch_failures", 0)) + 1
            save_state(last_result="session_failed", consecutive_fetch_failures=fails)
            if fails >= SESSION_FAIL_ALERT_AFTER:
                send_session_expired_alert()
            else:
                logger.warning(f"Fetch failed ({fails}/{SESSION_FAIL_ALERT_AFTER}) — alert deferred until consecutive failures.")

        else:
            # Reset alert flag on success (+ tell the user it recovered if we had alerted)
            if SESSION_ALERT_FILE.exists():
                SESSION_ALERT_FILE.unlink()
                try:
                    bot.send_message(CHAT_ID, "✅ *عاد سحب المنصة للعمل بنجاح* — لا حاجة لأي إجراء.", parse_mode="Markdown")
                except Exception as e:
                    logger.warning(f"Recovery notice failed: {e}")
            save_state(last_success_at=utc_now_iso(), last_result=f"ok:{staged_count}", consecutive_fetch_failures=0)
            ping_uptimerobot()

            if staged_count > 0:
                logger.info(f"Staging complete: {staged_count} new changes found.")
            else:
                logger.info("No new changes detected. System is up to date.")

        # STEP C: Notify manager via Telegram for any pending approvals.
        notify_pending_changes()

        # STEP D: لوحة المهام — قوالب المنافسات الجديدة + مزامنة المراحل (إن كانت مفعّلة)
        import bot_tasks
        bot_tasks.after_cycle()

        logger.info(f"{'='*20} Scheduled Check Ended {'='*20}")
    finally:
        _job_lock.release()

def _manual_mtime() -> float:
    import source_core
    try:
        return source_core.MANUAL_FILE.stat().st_mtime if source_core.is_manual_instance() else 0.0
    except OSError:
        return 0.0


def job_manual_source_watch():
    """كل 20 ثانية (نسخ الإدخال اليدوي): ملف المصدر تغيّر من صفحة «مصدر المنافسات» ← فحص فوري."""
    m = _manual_mtime()
    if m and not is_paused() and m != load_state().get("manual_source_mtime"):
        logger.info("Manual source file changed — running check now.")
        job_check_platform()


def job_backup_system():
    """Daily backup: sends the latest DB and Excel to Telegram."""
    # ── Lock guard: prevents two concurrent calls (e.g. scheduler + manual /backup) ──
    if not _backup_lock.acquire(blocking=False):
        logger.info("Backup guard: another backup is already running. Skipping.")
        return

    today = time.strftime("%Y-%m-%d")
    try:
        # ── Date guard (re-checked inside lock) ──────────────────────────
        if load_state().get("last_backup_local_date") == today:
            logger.info(f"Backup guard: already sent today ({today}). Skipping duplicate.")
            return

        # ── CLAIM TODAY FIRST — before any sending ────────────────────────
        # Saving the date BEFORE we send prevents a restart-during-send from
        # causing the backup to be sent twice (different file sizes).
        save_state(
            last_backup_at=utc_now_iso(),
            last_backup_local_date=today,
            last_backup_result="sending"
        )

        logger.info("📦 Generating daily cloud backup...")

        # Ensure latest excel is generated
        db.export_master_excel()

        # Files to backup
        files = [
            (DB_PATH, "🗄️ نسخة احتياطية لقاعدة البيانات (SQLite)"),
            (BASE_DIR / "output" / "Master_Tenders.xlsx", "📊 نسخة احتياطية لملف الماستر (Excel)")
        ]

        for file_path, caption in files:
            if file_path.exists():
                with open(file_path, "rb") as f:
                    bot.send_document(CHAT_ID, f, caption=f"{caption}\n📅 بتاريخ: {time.strftime('%Y-%m-%d')}")
            else:
                raise FileNotFoundError(f"Backup file missing: {file_path}")

        logger.info("✅ Daily backup sent to Telegram.")
        save_state(
            last_backup_at=utc_now_iso(),
            last_backup_local_date=today,
            last_backup_result="ok"
        )
        if BACKUP_ALERT_FILE.exists():
            BACKUP_ALERT_FILE.unlink()
        return True

    except Exception as e:
        logger.error(f"❌ Backup Job failed: {e}")
        save_state(
            last_backup_at=utc_now_iso(),
            last_backup_local_date=today,
            last_backup_result=f"failed:{e}"
        )
        try:
            send_backup_failure_alert(e)
        except Exception as alert_error:
            logger.error(f"Could not send backup failure alert: {alert_error}")
        return False

    finally:
        _backup_lock.release()

def job_guarantee_reminder():
    """v5.6: تذكير يومي بالضمانات الابتدائية المستحقة (اليوم/غداً/بعد 3 أيام)."""
    if is_paused():
        return
    try:
        from datetime import datetime as _dt, timedelta as _td
        with db._get_connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS tender_guarantees (
                tender_row_id INTEGER PRIMARY KEY, required INTEGER DEFAULT 1,
                due_date TEXT DEFAULT '', status TEXT DEFAULT 'PENDING',
                notes TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            rows = conn.execute(f"""
                SELECT mt.id, mt.title, mt.owner, mt.submission_date,
                       COALESCE(g.status,'PENDING') gstatus, COALESCE(g.due_date,'') gdue
                FROM master_tenders mt
                LEFT JOIN tender_guarantees g ON g.tender_row_id = mt.id
                WHERE mt.status NOT IN ('CLOSED','REJECTED') AND mt.{NOT_DEMO}
                  AND COALESCE(g.status,'PENDING') NOT IN ('READY','SUBMITTED','NOT_REQUIRED')
            """).fetchall()
        today = _dt.now().date()
        due_list = []
        for r in rows:
            due = None
            if r["gdue"]:
                try:
                    due = _dt.strptime(r["gdue"][:10], "%Y-%m-%d").date()
                except Exception:
                    pass
            if due is None:
                try:
                    due = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date() - _td(days=5)
                except Exception:
                    continue
            dleft = (due - today).days
            if dleft in (-1, 0, 1, 3):
                due_list.append((dleft, str(r["title"]), str(r["owner"] or ""), due.isoformat(), r["id"]))
        if not due_list:
            logger.info("Guarantee reminder: nothing due — skipped.")
            return
        due_list.sort()
        bot.send_message(CHAT_ID,
                         f"🛡️ *تذكير الضمانات الابتدائية* — {len(due_list)} مستحقة، حدّث الحالة بالأزرار:",
                         parse_mode="Markdown")
        _send_guarantee_cards(due_list)
        logger.info(f"Guarantee reminder sent: {len(due_list)} item(s).")
    except Exception as e:
        logger.error(f"Guarantee reminder failed: {e}")

def job_morning_briefing():
    """Daily 8:00 AM briefing: tenders due today/tomorrow, overdue, pending approvals."""
    logger.info("🌅 Running Morning Briefing...")
    import pandas as pd
    from datetime import datetime, timedelta

    _ARABIC_DAYS = {
        "Monday": "الإثنين", "Tuesday": "الثلاثاء", "Wednesday": "الأربعاء",
        "Thursday": "الخميس", "Friday": "الجمعة", "Saturday": "السبت", "Sunday": "الأحد"
    }
    try:
        with db._get_connection() as conn:
            tenders = conn.execute(
                f"SELECT title, submission_date, assigned_engineer FROM master_tenders WHERE status = 'InProgress' AND {NOT_DEMO}"
            ).fetchall()
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED')"
            ).fetchone()[0]

        now          = datetime.now()
        today_s      = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_s   = today_s + timedelta(days=1)
        day_after_s  = tomorrow_s + timedelta(days=1)

        due_today, due_tomorrow, overdue = [], [], []
        for t in tenders:
            try:
                d = pd.to_datetime(t['submission_date'], errors='coerce')
                if pd.notnull(d):
                    dn = d.replace(tzinfo=None)
                    if today_s <= dn < tomorrow_s:
                        due_today.append(t)
                    elif tomorrow_s <= dn < day_after_s:
                        due_tomorrow.append(t)
                    elif dn < today_s:
                        overdue.append(t)
            except Exception:
                pass

        day_ar = _ARABIC_DAYS.get(now.strftime("%A"), now.strftime("%A"))
        msg = f"🌅 *صباح الخير — {day_ar} {now.strftime('%Y-%m-%d')}*\n━━━━━━━━━━━━━━\n"

        if due_today:
            msg += f"🔴 *تسليمات اليوم ({len(due_today)}):*\n"
            for t in due_today:
                msg += f"  • _{t['title'][:55]}_\n    👷 {t['assigned_engineer'] or 'غير محدد'}\n"
        else:
            msg += "✅ لا تسليمات اليوم\n"

        msg += "\n"

        if due_tomorrow:
            msg += f"⚡ *تسليمات غداً ({len(due_tomorrow)}):*\n"
            for t in due_tomorrow:
                msg += f"  • _{t['title'][:55]}_\n    👷 {t['assigned_engineer'] or 'غير محدد'}\n"
        else:
            msg += "✅ لا تسليمات غداً\n"

        if overdue:
            msg += f"\n⚠️ *متأخرة ولم تُغلق ({len(overdue)}):*\n"
            for t in overdue[:3]:
                msg += f"  • _{t['title'][:55]}_\n"
            if len(overdue) > 3:
                msg += f"  _...و {len(overdue) - 3} أخرى_\n"

        if pending_count > 0:
            msg += f"\n🟡 *بانتظار اعتمادك: {pending_count} طلب* — /pending\n"

        msg += f"\n💚 _{CO_TEAM} — {CO_SHORT}_"

        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
        logger.info(f"Morning briefing sent: today={len(due_today)}, tomorrow={len(due_tomorrow)}, overdue={len(overdue)}, pending={pending_count}")

    except Exception as e:
        logger.error(f"Morning briefing failed: {e}")


def job_evening_alert():
    """Daily 5:00 PM alert — only fires when there are tenders due tomorrow."""
    logger.info("🌆 Running Evening Alert...")
    import pandas as pd
    from datetime import datetime, timedelta

    try:
        with db._get_connection() as conn:
            tenders = conn.execute(
                f"SELECT title, submission_date, assigned_engineer FROM master_tenders WHERE status = 'InProgress' AND {NOT_DEMO}"
            ).fetchall()

        now         = datetime.now()
        tomorrow_s  = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_after_s = tomorrow_s + timedelta(days=1)

        due_tomorrow = []
        for t in tenders:
            try:
                d = pd.to_datetime(t['submission_date'], errors='coerce')
                if pd.notnull(d):
                    dn = d.replace(tzinfo=None)
                    if tomorrow_s <= dn < day_after_s:
                        due_tomorrow.append(t)
            except Exception:
                pass

        if not due_tomorrow:
            logger.info("Evening alert: no tenders due tomorrow — skipping.")
            return

        msg = (
            f"⏰ *تنبيه المساء — تسليمات الغد*\n"
            f"━━━━━━━━━━━━━━\n"
            f"غداً *{tomorrow_s.strftime('%Y-%m-%d')}* معنا *{len(due_tomorrow)}* تسليم:\n\n"
        )
        for t in due_tomorrow:
            msg += f"📌 *{t['title'][:60]}*\n   👷 {t['assigned_engineer'] or 'غير محدد'}\n\n"
        msg += "_تأكد من جاهزية الملفات الآن 💼_"

        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
        logger.info(f"Evening alert sent: {len(due_tomorrow)} tenders due tomorrow.")

    except Exception as e:
        logger.error(f"Evening alert failed: {e}")


def job_deadline_sentinel():
    """Checks for tenders closing in the next 48 hours and sends alerts."""
    logger.info("⏰ Running Deadline Sentinel...")
    import pandas as pd
    from datetime import datetime, timedelta

    try:
        with db._get_connection() as conn:
            # Fetch all InProgress tenders
            tenders = conn.execute(f"SELECT title, submission_date, assigned_engineer FROM master_tenders WHERE status = 'InProgress' AND {NOT_DEMO}").fetchall()

        now = datetime.now()
        threshold = now + timedelta(hours=48)

        for t in tenders:
            try:
                # Robust date parsing
                close_date = pd.to_datetime(t['submission_date'], errors='coerce')
                if pd.notnull(close_date):
                    if now < close_date <= threshold:
                        #🚨 ALERT!
                        msg = (f"⏰ *إنذار الموعد النهائي (Deadline)!*\n"
                               f"━━━━━━━━━━━━━━\n"
                               f"📌 *المناقصة:* {t['title']}\n"
                               f"👷 *المسؤول:* {t['assigned_engineer']}\n"
                               f"⏱️ *تاريخ الإغلاق:* {t['submission_date']}\n\n"
                               f"⚡ الرجاء التأكد من جاهزية ملفات التقديم!")
                        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
            except: continue

    except Exception as e:
        logger.error(f"Deadline Sentinel failed: {e}")

# ============================================================
# 7. BACKGROUND SCHEDULER THREAD
# ============================================================
def job_deletion_reminder():
    """تذكير بأي منافسة حُذفت من المنصة ولم يضغط أحد "اطّلعت" خلال 14 يوماً."""
    try:
        import bot_deletions
        n = bot_deletions.send_reminders()
        if n:
            logger.info(f"Deletion reminder sent for {n} unacknowledged alert(s).")
    except Exception as e:
        logger.error(f"job_deletion_reminder failed: {e}")


def schedule_runner():
    """Runs the schedule loop inside a background thread."""
    # ★ Run one check IMMEDIATELY on startup
    logger.info("Running initial startup check...")
    try:
        job_check_platform()
    except Exception as e:
        logger.error(f"Initial check failed: {e}")

    schedule.every(CHECK_INTERVAL).minutes.do(job_check_platform)
    schedule.every(20).seconds.do(job_manual_source_watch)     # مصدر يدوي حُدّث من اللوحة ← فحص خلال ثوانٍ

    # ★ Daily Cloud Backup at Midnight
    schedule.every().day.at("00:00").do(job_backup_system)

    # ★ Morning Briefing at 08:00 AM
    schedule.every().day.at("08:00").do(job_morning_briefing)
    # ★ تذكير بحذف منافسات لم يؤكد أحد الاطلاع عليه (2026-09-24)
    schedule.every().day.at("09:00").do(job_deletion_reminder)
    schedule.every().day.at("13:00").do(job_deletion_reminder)
    schedule.every().day.at("08:30").do(job_guarantee_reminder)
    schedule.every().day.at("08:15").do(job_engineer_digests)
    # ★ لوحة المهام: المتأخر والمستحق اليوم (فقط إن كانت kanban مفعّلة)
    import bot_tasks
    schedule.every().day.at("08:20").do(bot_tasks.job_task_reminders)
    # وضع العرض: تجديد ليلي بتاريخ اليوم (إن فعّلته الإدارة من /admin/demo)
    schedule.every().day.at(demo_core.NIGHTLY_AT).do(job_demo_nightly)

    # ★ Evening Alert at 17:00 (only fires if tenders due tomorrow)
    schedule.every().day.at("17:00").do(job_evening_alert)

    # (أُزيل تذكير الكوكيز اليومي المبني على عمر الملف — 2026-09-22: كان إنذاراً كاذباً.
    #  التنبيه الآن فقط عند فشل السحب فعلياً — راجع SESSION_FAIL_ALERT_AFTER في job_check_platform)

    # تقرير الأداء (لوحة المهام) — أول كل شهر 09:05 لتليجرام الإدارة فقط
    schedule.every().day.at("09:05").do(bot_tasks.job_performance_report)

    # ★ Monthly PDF report on 1st of each month at 09:00
    schedule.every().day.at("09:00").do(
        lambda: job_monthly_report(previous_month_start()) if datetime.now().day == 1 else None
    )

    logger.info(f"Scheduler armed: every {CHECK_INTERVAL}min | Briefing 08:00 | DeletedReminder 09:00+13:00 | EngDigest 08:15 | Guarantees 08:30 | Evening 17:00 | Backup 00:00 | MonthlyReport 1st@09:00 | Performance 1st@09:05.")
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"Schedule Runner error: {e}")
        time.sleep(1)

