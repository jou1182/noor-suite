# -*- coding: utf-8 -*-
"""Approval cards, pending-change notifications, /news & /list reports, subscription and guarantee helpers.

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
import json
import time
from company_profile import PROFILE
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
import bot_deletions
from demo_core import NOT_DEMO  # وضع العرض لا يصل تليجرام
from bot_core import BASE_DIR, CHAT_ID, CO_SHORT, CO_TEAM, OWNER_TELEGRAM_IDS, SESSION_ALERT_FILE, TELEGRAM_TOKEN, _job_lock, bot, db, load_state, logger, save_state, send_session_expired_alert, utc_now_iso
# ============================================================
# 4. TELEGRAM MESSAGE DELIVERY
# ============================================================
def get_progress_bar(pct):
    filled = int(pct / 10)
    return "▓" * filled + "░" * (10 - filled)

def send_approval_message(change):
    """Sends the interactive approval message to the Manager."""
    # ── استخراج بيانات الترشيح الذكي من details_json ──────────────────
    suggestion  = {}
    owner_name  = ""
    btype_name  = ""
    try:
        details = json.loads(change['details_json'] or "{}")
        suggestion  = details.get('_smart_suggestion', {})
        owner_name  = str(details.get('المالك', '') or details.get('owner', '')).strip()
        btype_name  = str(details.get('نوع الأعمال', '') or details.get('business_type', '')).strip()
    except Exception:
        pass

    eng_name  = suggestion.get('name') or change['suggested_engineer']
    score     = suggestion.get('score', 0)
    reason    = suggestion.get('reason', '')
    breakdown = suggestion.get('breakdown', '')

    # ── شريط حمل المهندس المقترح ──────────────────────────────────────
    eng_load = 50
    try:
        for e in db.get_all_engineers_with_load():
            if e['name'] == eng_name:
                eng_load = e['load_pct']
                break
    except Exception:
        pass
    bar = get_progress_bar(eng_load)

    action_str  = {
        "NEW": "مناقصة جديدة",
        "REOPENED": "عودة منافسة مغلقة إلى المنصة",
    }.get(change['change_type'], "تعديل في تاريخ الإغلاق")
    score_stars = "⭐" * min(int(score // 20), 5)

    # ── بناء رسالة تيليجرام ───────────────────────────────────────────
    meta_line = ""
    if owner_name and owner_name not in ("N/A", "غير محدد", "nan"):
        meta_line += f"🏢 *الجهة:* {owner_name}\n"
    if btype_name and btype_name not in ("N/A", "غير محدد", "nan"):
        meta_line += f"🏗️ *النطاق:* {btype_name}\n"

    msg = (
        f"🚨 *اكتشاف {action_str}!*\n\n"
        f"📌 *الاسم:* {change['title']}\n"
        f"⏱️ *تاريخ الإغلاق:* {change['submission_date']}\n"
        f"{meta_line}"
        f"\n🤖 *اقتراح الذكاء الاصطناعي:*\n"
        f"المهندس *{eng_name}* هو الأنسب {score_stars}\n"
        f"⚖️ الحمل: [{bar}] {eng_load}%\n"
        f"💡 _السبب: {reason}_\n"
    )
    if breakdown:
        msg += f"\n{breakdown}\n"

    # ── ROADMAP_V6 Phase 2: كشف التشابه مع مناقصات فائزة سابقة ──────────
    if change['change_type'] in ('NEW', 'NEW_TENDER'):
        try:
            similar = db.find_similar_won_tenders(change['title'], owner_name, btype_name)
        except Exception:
            similar = []
        if similar:
            sim_lines = []
            for s in similar:
                price_str = f" — فزنا بـ {s['winning_price']:,.0f} ريال" if s['winning_price'] else ""
                sim_lines.append(f"• {str(s['title'])[:45]}{price_str}")
            msg += "\n🎯 *مشابهة لمشاريع فزنا بها سابقاً:*\n" + "\n".join(sim_lines) + "\n"

    # -- ROADMAP_V6 Phase 4: موافقة مزدوجة اختيارية (مهندس ثم مدير) --------
    # مُفعّلة فقط لو company_profile.json.dual_approval=true وكان المهندس
    # المقترح مشتركاً فعلاً (/subscribe) وفيه مدير مضبوط (OWNER_TELEGRAM_ID) --
    # غير ذلك يرجع تلقائياً لمسار الموافقة الواحدة الحالي (سلوك النور الحالي).
    pending_id = change["id"]
    eng_chat_ids = _subs_for(eng_name) if eng_name else []
    if PROFILE.get("dual_approval") and eng_chat_ids and OWNER_TELEGRAM_IDS:
        db.set_approval_stage(pending_id, "awaiting_engineer", eng_name)
        eng_markup = InlineKeyboardMarkup(row_width=1)
        eng_markup.add(
            InlineKeyboardButton("✅ موافقة فنية", callback_data=f"engapprove_{pending_id}_{eng_name}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"engreject_{pending_id}")
        )
        eng_msg = "🔧 *مطلوب موافقتك الفنية أولاً*\n\n" + msg
        import requests
        for cid in eng_chat_ids:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    json={"chat_id": cid, "text": eng_msg, "parse_mode": "Markdown",
                          "reply_markup": eng_markup.to_json()},
                    timeout=15
                )
            except Exception as e:
                logger.error(f"Engineer-stage delivery failed for chat {cid}: {e}")
        logger.info(f"Dual-approval stage 1 (engineer) sent for tender id={pending_id} to {eng_name}.")
        return

    markup = InlineKeyboardMarkup(row_width=1)
    btn_approve = InlineKeyboardButton(
        f"اعتماد لـ ({eng_name}) وتحديث الماستر",
        callback_data=f"approve_{pending_id}_{eng_name}"
    )
    btn_change_eng = InlineKeyboardButton(
        "أفضّل إسنادها لمهندس آخر",
        callback_data=f"changeeng_{pending_id}"
    )
    btn_reject = InlineKeyboardButton(
        "تجاهل وحذف من المعلقات",
        callback_data=f"reject_{pending_id}"
    )
    markup.add(btn_approve, btn_change_eng, btn_reject)

    import requests
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": markup.to_json()
    }
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload, timeout=15
        )
        logger.info(f"Delivered approval card for tender id={pending_id} via fresh TCP connection.")
    except Exception as e:
        logger.error(f"Telegram delivery failed: {e}")

def is_auto_approve() -> bool:
    """وضع المزامنة الآلية — يُبدَّل بأمر /automode on|off."""
    return bool(load_state().get("auto_approve", False))

def _auto_engineer_for(change) -> str:
    """اختيار المهندس للاعتماد الآلي: مهندس المنافسة الحالي إن وُجدت،
    وإلا المقترح الذكي المخزن، وإلا اقتراح موازنة الأحمال."""
    try:
        with db._get_connection() as conn:
            r = conn.execute(
                "SELECT assigned_engineer FROM master_tenders WHERE title = ?",
                (change['title'],)
            ).fetchone()
        if r and r[0]:
            return r[0]
    except Exception:
        pass
    try:
        if change['suggested_engineer']:
            return change['suggested_engineer']
    except Exception:
        pass
    return db.suggest_best_engineer(change['title'])

def notify_pending_changes():
    """Notify manager for fresh pending approvals and mark them as notified."""
    notified_count = 0
    pending_changes = db.get_pending_changes()
    for change in pending_changes:
        try:
            # PRE-MARK as NOTIFIED atomically before sending to prevent duplicate sends.
            with db._get_connection() as conn:
                affected = conn.execute(
                    "UPDATE pending_changes SET status = 'NOTIFIED' WHERE id = ? AND status = 'PENDING_APPROVAL'",
                    (change['id'],)
                ).rowcount
                conn.commit()

            if affected == 0:
                logger.warning(f"Skipping duplicate send for pending_id={change['id']} (already claimed).")
                continue

            if change['change_type'] == 'DELETED':
                # حُذفت من المنصة قبل موعدها → تنبيه عاجل بارز (bot_deletions)
                bot_deletions.send_deletion_alert(change)
                with db._get_connection() as conn:
                    conn.execute("UPDATE pending_changes SET status = 'APPROVED' WHERE id = ?", (change['id'],))
                    conn.commit()
            elif change['change_type'] == 'CLOSED':
                bot.send_message(
                    CHAT_ID,
                    f"\u2139\ufe0f *للعلم:* تم إغلاق المناقصة بشكل آلي وإزالتها من الموقع:\n*{change['title']}*",
                    parse_mode="Markdown"
                )
                # الإغلاق مُطبَّق آلياً في الماستر — أكمل حالة السجل حتى لا يتضخم عداد "بانتظار الاعتماد"
                with db._get_connection() as conn:
                    conn.execute("UPDATE pending_changes SET status = 'APPROVED' WHERE id = ?", (change['id'],))
                    conn.commit()
            elif is_auto_approve():
                def _dmy(s):
                    p = str(s or '')[:10].split('-')
                    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 and p[0].isdigit() else (str(s or '—')[:10])
                is_new = change['change_type'] in ('NEW', 'NEW_TENDER')
                old_date = ""
                if not is_new:
                    # التاريخ القديم يُقرأ قبل الاعتماد (الاعتماد سيستبدله)
                    try:
                        with db._get_connection() as conn:
                            r = conn.execute("SELECT submission_date FROM master_tenders WHERE title = ?",
                                             (change['title'],)).fetchone()
                        old_date = str(r[0])[:10] if r and r[0] else ""
                    except Exception:
                        pass
                eng = _auto_engineer_for(change)
                db.approve_change(change['id'], eng)
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔁 تغيير المهندس", callback_data=f"aem_{change['id']}"))
                new_date = _dmy(change['submission_date'])
                if is_new:
                    msg = (f"🤖 *مزامنة آلية:* تم اعتماد منافسة جديدة:\n*{change['title']}*\n"
                           f"تاريخ التقديم: {new_date}\nالمهندس: *{eng}*")
                elif change['change_type'] == 'REOPENED':
                    msg = (f"🤖 *مزامنة آلية:* 🔄 أُعيد فتح منافسة كانت مغلقة وعادت للظهور في المنصة:\n"
                           f"*{change['title']}*\n"
                           f"تاريخ التقديم: {new_date}\nالمهندس: *{eng}*")
                else:
                    msg = (f"🤖 *مزامنة آلية:* تم اعتماد تحديث تاريخ:\n*{change['title']}*\n"
                           f"تاريخ التقديم القديم: {_dmy(old_date)}\n"
                           f"تاريخ التقديم الجديد: {new_date}\nالمهندس: *{eng}*")
                bot.send_message(CHAT_ID, msg, parse_mode="Markdown", reply_markup=markup)
                if is_new:
                    _notify_engineer(eng, "📌 أُسندت إليك منافسة جديدة:" + chr(10)
                                     + str(change['title']) + chr(10) + "الإغلاق: " + new_date)
            else:
                send_approval_message(change)
            notified_count += 1
            time.sleep(1)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification, will retry: {e}")
            # Revert to PENDING_APPROVAL so it retries next cycle.
            try:
                with db._get_connection() as conn:
                    conn.execute("UPDATE pending_changes SET status = 'PENDING_APPROVAL' WHERE id = ?", (change['id'],))
                    conn.commit()
            except Exception as e2:
                logger.error(f"CRITICAL: Could not revert status for pending_id={change['id']}: {e2}")
    return notified_count

def build_news_clear_message():
    return (
        "✅ لا توجد أي منافسات جديدة أو منافسات تم تغيير تاريخ التقديم حتى هذه اللحظة.\n\n"
        "اطمئن، المنصة وقاعدة البيانات متطابقتان الآن.\n\n"
        f"💚 صنع بكل حب من {CO_TEAM} — {CO_SHORT}"
    )

def run_manual_list_report(chat_id):
    if not _job_lock.acquire(blocking=False):
        bot.send_message(chat_id, "⏳ يوجد فحص يعمل الآن بالفعل. جرّب /list بعد دقيقة.")
        return

    try:
        logger.info(f"Manual /list command received from chat_id={chat_id}")
        import pandas as pd
        import portal_adapter

        ok = portal_adapter.get_active_portal().fetch_to_file()
        if not ok:
            bot.send_message(
                chat_id,
                "⚠️ لم أتمكن من تحديث قائمة المنصة الآن. تأكد من مصدر البيانات (جلسة الدخول أو ملف الإدخال اليدوي).",
                parse_mode="Markdown"
            )
            return

        export_path = BASE_DIR / "output" / "in_progress_tenders.xlsx"
        portal_count = len(pd.read_excel(export_path)) if export_path.exists() else 0

        with db._get_connection() as conn:
            db_count = conn.execute(
                f"SELECT COUNT(*) FROM master_tenders WHERE status NOT IN ('CLOSED', 'REJECTED') AND {NOT_DEMO}"
            ).fetchone()[0]
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL', 'NOTIFIED')"
            ).fetchone()[0]

        match_text = "✅ متطابقان" if portal_count == db_count else "⚠️ يوجد فرق يحتاج مراجعة"
        msg = (
            f"📋 *قائمة منافسات {CO_SHORT} الحالية*\n"
            "━━━━━━━━━━━━━━\n"
            f"المنصة: *{portal_count}* منافسة\n"
            f"قاعدة البيانات: *{db_count}* منافسة نشطة\n"
            f"الحالة: *{match_text}*\n"
            f"طلبات بانتظار الاعتماد: *{pending_count}*\n\n"
            f"آخر تحديث: `{utc_now_iso()}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"Manual /list report failed: {e}")
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تنفيذ /list:\n{e}")
    finally:
        _job_lock.release()

def send_open_pending_cards(chat_id):
    logger.info(f"Manual /pending command received from chat_id={chat_id}")
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_changes WHERE status IN ('PENDING_APPROVAL', 'NOTIFIED') ORDER BY created_at ASC"
        ).fetchall()

    if not rows:
        bot.send_message(chat_id, "✅ لا توجد طلبات بانتظار الاعتماد حالياً.")
        return

    bot.send_message(chat_id, f"🟡 يوجد ({len(rows)}) طلب بانتظار الاعتماد. سأعرضها الآن:")
    for change in rows:
        if change['change_type'] == 'CLOSED':
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("❌ إزالة من المعلقات", callback_data=f"reject_{change['id']}"))
            bot.send_message(
                chat_id,
                f"ℹ️ *طلب إغلاق معلق*\n\n*{change['title']}*",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            send_approval_message(change)
        time.sleep(1)

def send_tenders_detail_table(chat_id):
    logger.info(f"Manual detailed list command received from chat_id={chat_id}")
    try:
        import pandas as pd

        with db._get_connection() as conn:
            df = pd.read_sql(
                f"""
                SELECT title, submission_date, assigned_engineer
                FROM master_tenders
                WHERE status NOT IN ('CLOSED', 'REJECTED') AND {NOT_DEMO}
                ORDER BY created_at ASC
                """,
                conn
            )

        if df.empty:
            bot.send_message(chat_id, "لا توجد منافسات نشطة حالياً في قاعدة البيانات.")
            return

        def clean_date(value):
            try:
                if pd.isna(value) or str(value).strip().lower() in ("", "nan", "none", "n/a"):
                    return "غير محدد"
                return pd.to_datetime(value).strftime("%Y-%m-%d")
            except Exception:
                return str(value)

        report_df = pd.DataFrame({
            "مسلسل": range(1, len(df) + 1),
            "اسم المنافسة": df["title"].fillna(""),
            "تاريخ التقديم": df["submission_date"].apply(clean_date),
            "المهندس المسؤول": df["assigned_engineer"].fillna("غير محدد"),
        })

        report_path = BASE_DIR / "output" / "قائمة_المنافسات_الحالية.xlsx"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            report_df.to_excel(writer, sheet_name="المنافسات الحالية", index=False)

        with open(report_path, "rb") as report_file:
            bot.send_document(
                chat_id,
                report_file,
                caption=(
                    f"📄 قائمة المنافسات الحالية\n"
                    f"العدد: {len(report_df)} منافسة\n"
                    "الأعمدة: مسلسل، اسم المنافسة، تاريخ التقديم، المهندس المسؤول"
                )
            )
    except Exception as e:
        logger.exception(f"Detailed tenders list failed: {e}")
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تجهيز جدول المنافسات:\n{e}")

def run_manual_news_check(chat_id):
    if not _job_lock.acquire(blocking=False):
        bot.send_message(chat_id, "⏳ يوجد فحص يعمل الآن بالفعل. جرّب /news بعد دقيقة.")
        return

    try:
        save_state(last_manual_news_at=utc_now_iso(), last_manual_news_result="running")
        logger.info(f"{'='*20} Manual /news Check Started {'='*20}")

        try:
            import reverse_sync_to_sql
            reverse_sync_to_sql.reverse_sync()
            logger.info("Manual /news Excel -> SQL sync completed successfully.")
        except Exception as e:
            logger.error(f"Manual /news Excel Sync failed: {e}")

        import engine_core
        staged_count = engine_core.find_and_stage_changes()

        if staged_count == -1:
            send_session_expired_alert()
            save_state(last_manual_news_result="session_failed")
            bot.send_message(
                chat_id,
                "⚠️ لم أتمكن من فحص المنصة الآن لأن الجلسة تحتاج تجديد. راجع /health للتفاصيل.",
                parse_mode="Markdown"
            )
            return

        if SESSION_ALERT_FILE.exists():
            SESSION_ALERT_FILE.unlink()

        notified_count = notify_pending_changes()
        save_state(last_manual_news_result=f"ok:{staged_count}", last_success_at=utc_now_iso())

        if staged_count > 0 or notified_count > 0:
            bot.send_message(
                chat_id,
                f"🚨 تم فحص المنصة.\n\nتم العثور على ({max(staged_count, notified_count)}) تحديث يحتاج مراجعتك، وأرسلت لك تفاصيله الآن.",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(chat_id, build_news_clear_message())

        logger.info(f"{'='*20} Manual /news Check Ended {'='*20}")
    except Exception as e:
        logger.exception(f"Manual /news check failed: {e}")
        save_state(last_manual_news_result="failed")
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تنفيذ /news:\n{e}")
    finally:
        _job_lock.release()

# ══════════════════════════════════════════════════════════
# v5.7: اشتراكات المهندسين الشخصية + بطاقة الجهة
# ══════════════════════════════════════════════════════════
def _ensure_subs_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS engineer_subs (
        chat_id INTEGER PRIMARY KEY,
        engineer_name TEXT NOT NULL,
        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

def _sub_of(chat_id):
    with db._get_connection() as conn:
        _ensure_subs_table(conn)
        r = conn.execute("SELECT engineer_name FROM engineer_subs WHERE chat_id=?", (chat_id,)).fetchone()
    return r[0] if r else None

def _subs_for(eng_name):
    with db._get_connection() as conn:
        _ensure_subs_table(conn)
        return [r[0] for r in conn.execute(
            "SELECT chat_id FROM engineer_subs WHERE engineer_name=?", (eng_name,)).fetchall()]

def _notify_engineer(eng_name, text):
    """إشعار خاص لمشتركي مهندس معين — أفضل جهد، لا يوقف التدفق."""
    try:
        for cid in _subs_for(eng_name):
            try:
                bot.send_message(cid, text)
            except Exception as _e:
                logger.debug(f"notify {eng_name}/{cid} failed: {_e}")
    except Exception as e:
        logger.debug(f"_notify_engineer failed: {e}")

def _personal_digest(eng_name):
    """ملخص شخصي: منافسات المهندس + مواعيدها + ضماناتها المستحقة."""
    from datetime import datetime as _dt, timedelta as _td
    today = _dt.now().date()
    with db._get_connection() as conn:
        rows = conn.execute(f"""
            SELECT mt.title, mt.owner, mt.submission_date,
                   COALESCE(g.status,'PENDING') gstatus, COALESCE(g.due_date,'') gdue
            FROM master_tenders mt
            LEFT JOIN tender_guarantees g ON g.tender_row_id = mt.id
            WHERE mt.assigned_engineer = ? AND mt.status NOT IN ('CLOSED','REJECTED') AND mt.{NOT_DEMO}
            ORDER BY mt.submission_date""", (eng_name,)).fetchall()
    if not rows:
        return None
    lines = [f"👷 ملخصك اليومي يا {eng_name} — منافساتك ({len(rows)}):", ""]
    for r in rows[:12]:
        icon, dtxt = "⚪", ""
        try:
            d = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date()
            dl = (d - today).days
            icon = "🔴" if dl <= 3 else ("🟡" if dl <= 7 else "🟢")
            dtxt = f" (باقي {dl} يوم)" if dl >= 0 else " (منتهية!)"
        except Exception:
            pass
        lines.append(f"{icon} {r['title']}")
        lines.append(f"      الإغلاق: {str(r['submission_date'] or '—')[:10]}{dtxt}")
        if r["gstatus"] not in ("READY", "SUBMITTED", "NOT_REQUIRED"):
            gd = None
            if r["gdue"]:
                try: gd = _dt.strptime(r["gdue"][:10], "%Y-%m-%d").date()
                except Exception: pass
            if gd is None:
                try: gd = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date() - _td(days=5)
                except Exception: pass
            if gd is not None and (gd - today).days <= 5:
                lines.append(f"      🛡️ الضمان مستحق {gd.isoformat()} — غير جاهز بعد!")
        lines.append("")
    return chr(10).join(lines).strip()

def _guarantee_status_markup(mid):
    m = InlineKeyboardMarkup(row_width=3)
    m.add(InlineKeyboardButton("🟢 جاهز", callback_data=f"gst_{mid}_READY"),
          InlineKeyboardButton("✅ قُدّم", callback_data=f"gst_{mid}_SUBMITTED"),
          InlineKeyboardButton("⚪ غير مطلوب", callback_data=f"gst_{mid}_NOT_REQUIRED"))
    return m

def _send_guarantee_cards(due_list, chat_id=None):
    """بطاقة لكل ضمان مع أزرار تحديث الحالة. due_list: (dleft,title,owner,due,mid)"""
    for dleft, title, owner, due, mid in due_list[:8]:
        when = ("⚠️ متأخر" if dleft < 0 else "🔴 اليوم" if dleft == 0
                else "🟠 غداً" if dleft == 1 else f"🟡 بعد {dleft} يوم")
        txt = f"{when} — استحقاق {due}\n*{title}*"
        if owner:
            txt += f"\n{owner}"
        bot.send_message(chat_id or CHAT_ID, txt, parse_mode="Markdown",
                         reply_markup=_guarantee_status_markup(mid))

def _collect_guarantees(max_ahead=14, min_behind=-3):
    """كل الضمانات غير المكتملة ضمن النافذة. يعيد (dleft,title,owner,due,mid) مرتبة."""
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
    out = []
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
        if min_behind <= dleft <= max_ahead:
            out.append((dleft, str(r["title"]), str(r["owner"] or ""), due.isoformat(), r["id"]))
    out.sort()
    return out

