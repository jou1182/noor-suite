# -*- coding: utf-8 -*-
"""Text command handlers (registration order matters: imported first by bot_daemon).

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
import os
import threading
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot_core import BASE_DIR, CO_SYSTEM, PDF_OK, bot, build_health_report, db, is_authorized, logger, read_last_log_lines, save_state, utc_now_iso
from bot_notifications import _auto_engineer_for, _collect_guarantees, _notify_engineer, _personal_digest, _send_guarantee_cards, _sub_of, get_progress_bar, is_auto_approve, run_manual_list_report, run_manual_news_check, send_open_pending_cards, send_tenders_detail_table
from bot_jobs import job_backup_system, job_monthly_report
# ============================================================
# 5. COMMAND HANDLERS
# ============================================================
@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    if not is_authorized(message): return
    bot.send_message(message.chat.id, f"👋 أهلاً بك في {CO_SYSTEM} لإدارة المناقصات.\n\n"
                                      "استخدم /news لفحص المنصة الآن.\n"
                                      "استخدم /list لعرض عدد منافسات المنصة وقاعدة البيانات.\n"
                                      "استخدم /list_d لتحميل جدول المنافسات بالتفصيل.\n"
                                      "استخدم /pending لعرض طلبات الاعتماد العالقة.\n"
                                      "استخدم /status أو /health لفحص النظام.\n"
                                      "استخدم /stats لرؤية الإحصائيات.\n"
                                      "استخدم /backup لنقل نسخة احتياطية فورية.\n"
                                      "استخدم /report لإنشاء وإرسال تقرير PDF شهري الآن.\n"
                                      "استخدم /predict لتوقع تمديد المنافسات النشطة.\n"
                                      "استخدم /approve_all لاعتماد كل الطلبات المنتظرة دفعة واحدة.\n"
                                      "استخدم /automode للمزامنة الآلية الكاملة (on/off).\n"
                                      "استخدم /guarantees لعرض وتحديث الضمانات بالأزرار.\n"
                                      "استخدم /followup لتسجيل نتائج العروض المعلقة بضغطة.\n"
                                      "استخدم /find كلمة — بحث سريع ببطاقة إجراءات.\n"
                                      "استخدم /owner جهة — بطاقة ذاكرة الجهة المالكة.\n"
                                      "للمهندسين: راسلوا البوت خاصاً بـ /subscribe للإشعارات الشخصية.\n"
                                      "استخدم /test لتجربة إشعار آمن.\n"
                                      "استخدم /lastlog لآخر سجل تشغيل.\n"
                                      "استخدم /pause و /resume للتحكم في المزامنة.\n"
                                      "استخدم /addengineer الاسم [السعة] لإضافة مهندس جديد فوراً.\n"
                                      "استخدم /deleted لعرض المنافسات المحذوفة من المنصة قبل موعدها."
                                      + (chr(10) + "للمهندسين: /mytasks لعرض مهامك وتحديثها بالأزرار."
                                         if _tasks_enabled() else "")
                                      + (chr(10) + "أصحاب الحسابات الشخصية: اربطوا تليجرام من بوابتكم ثم أرسلوا هنا /link الرمز."
                                         if _accounts_enabled() else ""))


def _accounts_enabled():
    import engineer_accounts
    from company_profile import feature_enabled
    return feature_enabled(engineer_accounts.FEATURE)


def _tasks_enabled():
    import bot_tasks
    return bot_tasks.enabled()

@bot.message_handler(commands=['subscribe'])
def handle_subscribe(message):
    """اشتراك مهندس (محادثة خاصة + PIN بوابة المهندسين)."""
    if getattr(message.chat, "type", "") != "private":
        bot.send_message(message.chat.id,
                         "🔒 الاشتراك يتم في محادثة خاصة مع البوت — راسلني خاصاً بالأمر:" + chr(10) +
                         "/subscribe رقم-البوابة")
        return
    cur = _sub_of(message.chat.id)
    parts = (message.text or "").strip().split()
    pin = os.getenv("ENGINEER_PIN", "1234")
    if len(parts) < 2 or parts[1].strip() != pin:
        hint = f"(مشترك حالياً باسم: {cur})" + chr(10) if cur else ""
        bot.send_message(message.chat.id,
                         hint + "🔑 أرسل: /subscribe متبوعاً برقم بوابة المهندسين" + chr(10) +
                         "مثال: /subscribe 0000")
        return
    engineers = db.get_all_engineers()
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(*[InlineKeyboardButton(e['name'], callback_data=f"sub_{e['name']}")
                 for e in engineers])
    bot.send_message(message.chat.id, "✅ رمز صحيح — اختر اسمك:", reply_markup=markup)

@bot.message_handler(commands=['unsubscribe'])
def handle_unsubscribe(message):
    cur = _sub_of(message.chat.id)
    if not cur:
        bot.send_message(message.chat.id, "لا يوجد اشتراك مسجل لهذه المحادثة.")
        return
    with db._get_connection() as conn:
        conn.execute("DELETE FROM engineer_subs WHERE chat_id=?", (message.chat.id,))
        conn.commit()
    bot.send_message(message.chat.id, f"🚫 أُلغي اشتراك «{cur}» — لن تصلك إشعارات شخصية بعد الآن.")


_LINK_FAILS = {}            # chat_id → [أوقات المحاولات الخاطئة] — 5 خلال ساعة ثم إيقاف مؤقت


@bot.message_handler(commands=['link'])
def handle_link(message):
    """ربط تليجرام بحساب المهندس الشخصي: /link <رمز من البوابة> (2026-09-25)."""
    import time as _time
    import engineer_accounts
    from company_profile import feature_enabled
    if not feature_enabled(engineer_accounts.FEATURE):
        bot.send_message(message.chat.id, "الربط بالحسابات الشخصية غير مفعّل لهذه الشركة — استخدم /subscribe.")
        return
    if getattr(message.chat, "type", "") != "private":
        bot.send_message(message.chat.id, "🔒 الربط في محادثة خاصة مع البوت فقط.")
        return
    now = _time.time()
    fails = [t for t in _LINK_FAILS.get(message.chat.id, []) if now - t < 3600]
    if len(fails) >= 5:
        bot.send_message(message.chat.id, "⛔ محاولات كثيرة — حاول بعد ساعة، أو أصدر رمزاً جديداً من بوابتك.")
        return
    parts = (message.text or "").split()
    with db._get_connection() as conn:
        name = engineer_accounts.redeem_link_code(conn, parts[1] if len(parts) > 1 else "", message.chat.id)
        conn.commit()
    if not name:
        _LINK_FAILS[message.chat.id] = fails + [now]
        bot.send_message(message.chat.id, "❌ الرمز غير صحيح أو انتهت صلاحيته.\n"
                         "ادخل بوابتك ← «🔗 ربط تليجرام» ← أرسل هنا: /link الرمز (صالح 10 دقائق).")
        return
    _LINK_FAILS.pop(message.chat.id, None)
    db.log_audit("ENG_TELEGRAM_LINKED", name, f"chat_id={message.chat.id}", "TelegramBot")
    bot.send_message(message.chat.id, f"✅ رُبطت هذه المحادثة بحساب م. {name}.\n"
                     "ستصلك هنا مهامك وتذكيراتك. أوامرك: /mytasks — /mytenders — /unsubscribe")

@bot.message_handler(commands=['mytenders'])
def handle_mytenders(message):
    """منافساتي الآن — للمهندس المشترك."""
    eng = _sub_of(message.chat.id)
    if not eng:
        bot.send_message(message.chat.id,
                         "هذا الأمر للمهندسين المشتركين — راسلني خاصاً بـ /subscribe أولاً.")
        return
    digest = _personal_digest(eng)
    bot.send_message(message.chat.id, digest or f"✨ لا منافسات نشطة مسندة إليك حالياً يا {eng}.")

@bot.message_handler(commands=['mytasks'])
def handle_mytasks(message):
    """مهامي في لوحة المهام — للمهندس المشترك، بأزرار بدء/إنجاز (2026-09-24)."""
    import bot_tasks
    if not bot_tasks.enabled():
        bot.send_message(message.chat.id, "لوحة المهام غير مفعّلة لهذه الشركة.")
        return
    eng = _sub_of(message.chat.id)
    if not eng:
        bot.send_message(message.chat.id,
                         "هذا الأمر للمهندسين المشتركين — راسلني خاصاً بـ /subscribe أولاً.")
        return
    text, markup = bot_tasks.my_tasks_message(eng)
    bot.send_message(message.chat.id, text, reply_markup=markup)

def _owner_card_text(term):
    """بطاقة ذاكرة الجهة — نفس ذكاء صفحة /owners مضغوطاً لتيليجرام."""
    import json as _json
    from datetime import datetime as _dt
    # v5.7.1: مطابقة عربية ذكية — توحيد الهمزات + تجربة الاسم بدون "ال" التعريف
    # (مثال: "الإسكان" يجب أن يجد "الشركة الوطنية للإسكان" رغم اختلاف "ال" عن "لل")
    from engine_core import normalize_arabic as _norm
    t = _norm(term).strip()
    cands = [t]
    if t.startswith("ال") and len(t) > 4:
        cands.append(t[2:])
    with db._get_connection() as conn:
        all_owners = conn.execute("""
            SELECT TRIM(owner) ow, COUNT(*) total,
                   SUM(CASE WHEN status NOT IN ('CLOSED','REJECTED') THEN 1 ELSE 0 END) active,
                   MIN(CASE WHEN status NOT IN ('CLOSED','REJECTED')
                        AND submission_date >= date('now') THEN submission_date END) next_dl
            FROM master_tenders
            WHERE owner IS NOT NULL AND TRIM(owner) != ''
              AND TRIM(LOWER(owner)) NOT IN ('n/a','nan')
            GROUP BY TRIM(owner)""").fetchall()
    matches = [r for r in all_owners if any(c and c in _norm(r["ow"]) for c in cands)]
    if not matches:
        return None
    matches.sort(key=lambda r: (-(r["active"] or 0), -(r["total"] or 0)))
    b = matches[0]
    _others = [m["ow"] for m in matches[1:4]]
    with db._get_connection() as conn:
        ow = b["ow"]
        rr = conn.execute("""
            SELECT SUM(CASE WHEN did_submit=1 THEN 1 ELSE 0 END) s,
                   SUM(CASE WHEN result='won'  THEN 1 ELSE 0 END) w,
                   SUM(CASE WHEN result='lost' THEN 1 ELSE 0 END) l
            FROM tender_results WHERE TRIM(owner)=?""", (ow,)).fetchone()
        acts = conn.execute("""
            SELECT title, submission_date FROM master_tenders
            WHERE TRIM(owner)=? AND status NOT IN ('CLOSED','REJECTED')
            ORDER BY submission_date LIMIT 3""", (ow,)).fetchall()
        ext_rows = conn.execute(
            "SELECT details_json FROM pending_changes WHERE change_type='UPDATED_DATE'").fetchall()
    OWNER_KEY = "المالك"
    ext = 0
    for e_ in ext_rows:
        try:
            if str(_json.loads(e_["details_json"] or "{}").get(OWNER_KEY, "")).strip() == ow:
                ext += 1
        except Exception:
            pass
    s = rr["s"] or 0
    w = rr["w"] or 0
    l = rr["l"] or 0
    dec = w + l
    active = b["active"] or 0
    if w and active:   cls = "🟢 عميل رابح نشط"
    elif w:            cls = "🟠 رابح — يحتاج تنشيط"
    elif active:       cls = "🔵 فرصة جارية"
    elif s:            cls = "⚪ علاقة تحتاج تنشيط"
    else:              cls = "🗂 أرشيف"
    lines = [f"🏢 *{ow}*", f"التصنيف: {cls}", ""]
    lines.append(f"📊 السجل: {b['total']} منافسة معروفة | جارية الآن: {active}")
    lines.append(f"📤 قدمنا: {s} | 🏆 فوز: {w} | ❌ خسارة: {l}"
                 + (f" | نسبة الفوز: {round(w/dec*100)}% (من {dec} معروفة)" if dec else ""))
    if ext:
        lines.append(f"🔮 سلوك التمديد: مدّدت مواعيدها {ext} مرة تاريخياً — توقع مرونة في المواعيد")
    if b["next_dl"]:
        lines.append(f"⏰ أقرب إغلاق: {str(b['next_dl'])[:10]}")
    if acts:
        lines.append("")
        lines.append("*الفرص الجارية:*")
        for a in acts:
            lines.append(f"• {a['title']}")
            lines.append(f"   يغلق {str(a['submission_date'] or '—')[:10]}")
        if active > 3:
            lines.append(f"… و{active - 3} أخرى")
    if _others:
        lines.append("")
        lines.append("🔎 جهات أخرى مطابقة: " + "، ".join(_others))
    return chr(10).join(lines)

@bot.message_handler(commands=['owner'])
def handle_owner(message):
    """v5.7: بطاقة ذاكرة الجهة المالكة."""
    if not is_authorized(message): return
    q = (message.text or "").split(maxsplit=1)
    if len(q) < 2 or not q[1].strip():
        bot.send_message(message.chat.id,
                         "الاستخدام: `/owner جزء من اسم الجهة`" + chr(10) + "مثال: `/owner الإسكان`",
                         parse_mode="Markdown")
        return
    try:
        card = _owner_card_text(q[1].strip())
        if card:
            bot.send_message(message.chat.id, card, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"🔍 لا توجد جهة تطابق «{q[1].strip()}»")
    except Exception as e:
        logger.error(f"/owner failed: {e}")
        bot.send_message(message.chat.id, f"⚠️ خطأ: {e}")

@bot.message_handler(commands=['guarantees'])
def handle_guarantees(message):
    """v5.6.4: قائمة الضمانات المستحقة مع أزرار تحديث فورية."""
    if not is_authorized(message): return
    try:
        items = _collect_guarantees(max_ahead=14, min_behind=-3)
        if not items:
            bot.send_message(message.chat.id, "🛡️ لا ضمانات مستحقة خلال 14 يوماً القادمة ✓")
            return
        bot.send_message(message.chat.id,
                         f"🛡️ *الضمانات المستحقة خلال 14 يوماً* — {len(items)}:",
                         parse_mode="Markdown")
        _send_guarantee_cards(items, chat_id=message.chat.id)
    except Exception as e:
        logger.error(f"/guarantees failed: {e}")
        bot.send_message(message.chat.id, f"⚠️ خطأ: {e}")

@bot.message_handler(commands=['followup'])
def handle_followup(message):
    """v5.6.4: العروض المقدمة بلا نتيجة — تسجيل بضغطة."""
    if not is_authorized(message): return
    try:
        from datetime import datetime as _dt
        with db._get_connection() as conn:
            rows = conn.execute("""
                SELECT id, title, owner, submission_date FROM tender_results
                WHERE did_submit = 1 AND (result IS NULL OR result = 'pending')
                ORDER BY submission_date""").fetchall()
        if not rows:
            bot.send_message(message.chat.id, "✅ لا عروض بانتظار نتيجة — السجل نظيف!")
            return
        today = _dt.now().date()
        bot.send_message(message.chat.id,
                         f"📋 *عروض بانتظار النتيجة* — {len(rows)}:\n"
                         "(النتائج لا تُعلن دائماً — «لم تُعلن» تقفل المتابعة)",
                         parse_mode="Markdown")
        for r in rows[:10]:
            days = ""
            try:
                sd = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date()
                days = f" · منذ {(today - sd).days} يوم"
            except Exception:
                pass
            txt = f"*{str(r['title'])}*\n{str(r['owner'] or '')}{days}"
            m = InlineKeyboardMarkup(row_width=3)
            m.add(InlineKeyboardButton("🏆 فزنا", callback_data=f"fres_{r['id']}_won"),
                  InlineKeyboardButton("❌ خسرنا", callback_data=f"fres_{r['id']}_lost"),
                  InlineKeyboardButton("⚪ لم تُعلن", callback_data=f"fres_{r['id']}_unknown"))
            bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=m)
    except Exception as e:
        logger.error(f"/followup failed: {e}")
        bot.send_message(message.chat.id, f"⚠️ خطأ: {e}")

@bot.message_handler(commands=['find'])
def handle_find(message):
    """v5.6.4: بحث سريع بالاسم أو الجهة — بطاقة كاملة بأزرار إجراء."""
    if not is_authorized(message): return
    q = (message.text or "").split(maxsplit=1)
    if len(q) < 2 or not q[1].strip():
        bot.send_message(message.chat.id, "الاستخدام: `/find كلمة من اسم المنافسة أو الجهة`", parse_mode="Markdown")
        return
    term = q[1].strip()
    try:
        from datetime import datetime as _dt, timedelta as _td
        # v5.7.2: مطابقة عربية موحّدة (همزات + "ال") — نفس محرك /owner
        from engine_core import normalize_arabic as _norm
        t = _norm(term).strip()
        cands = [t]
        if t.startswith("ال") and len(t) > 4:
            cands.append(t[2:])
        def _hit(title, owner):
            hay = _norm(str(title or "") + " " + str(owner or ""))
            return any(c and c in hay for c in cands)
        with db._get_connection() as conn:
            all_rows = conn.execute("""
                SELECT mt.id, mt.title, mt.owner, mt.submission_date,
                       COALESCE(mt.assigned_engineer,'—') eng, mt.status,
                       COALESCE(g.status,'PENDING') gstatus, COALESCE(g.due_date,'') gdue
                FROM master_tenders mt
                LEFT JOIN tender_guarantees g ON g.tender_row_id = mt.id
                WHERE mt.status NOT IN ('CLOSED','REJECTED')
                ORDER BY mt.submission_date""").fetchall()
            closed_rows = conn.execute(
                "SELECT title, owner FROM master_tenders WHERE status IN ('CLOSED','REJECTED')").fetchall()
        rows = [r for r in all_rows if _hit(r["title"], r["owner"])][:5]
        closed_n = sum(1 for r in closed_rows if _hit(r["title"], r["owner"]))
        if not rows:
            extra = f"\n(يوجد {closed_n} نتيجة في الأرشيف المغلق)" if closed_n else ""
            bot.send_message(message.chat.id, f"🔍 لا نتائج نشطة تطابق «{term}»{extra}")
            return
        today = _dt.now().date()
        _GLBL = {"PENDING": "⚪ لم يبدأ", "IN_PROGRESS": "🟡 قيد الإصدار",
                 "READY": "🟢 جاهز", "SUBMITTED": "✅ قُدّم", "NOT_REQUIRED": "➖ غير مطلوب"}
        for r in rows:
            days_txt, icon = "", "⚪"
            try:
                d = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date()
                dl = (d - today).days
                icon = "🔴" if dl <= 3 else ("🟡" if dl <= 7 else "🟢")
                days_txt = f" (باقي {dl} يوم)" if dl >= 0 else f" (منتهية منذ {-dl} يوم)"
            except Exception:
                pass
            gdue_txt = ""
            if r["gstatus"] not in ("READY", "SUBMITTED", "NOT_REQUIRED"):
                gd = None
                if r["gdue"]:
                    try: gd = _dt.strptime(r["gdue"][:10], "%Y-%m-%d").date()
                    except Exception: pass
                if gd is None:
                    try: gd = _dt.strptime(str(r["submission_date"])[:10], "%Y-%m-%d").date() - _td(days=5)
                    except Exception: pass
                if gd:
                    gdue_txt = f" · استحقاقه {gd.isoformat()}"
            txt = (f"{icon} *{str(r['title'])}*\n"
                   f"الجهة: {str(r['owner'] or '—')}\n"
                   f"الإغلاق: {str(r['submission_date'] or '—')[:10]}{days_txt}\n"
                   f"المهندس: *{r['eng']}*\n"
                   f"الضمان: {_GLBL.get(r['gstatus'], r['gstatus'])}{gdue_txt}")
            m = InlineKeyboardMarkup(row_width=2)
            m.add(InlineKeyboardButton("🔁 تغيير المهندس", callback_data=f"fem_{r['id']}"),
                  InlineKeyboardButton("🛡️ حالة الضمان", callback_data=f"gmenu_{r['id']}"))
            bot.send_message(message.chat.id, txt, parse_mode="Markdown", reply_markup=m)
        if len(rows) == 5:
            bot.send_message(message.chat.id, "عرضت أول 5 نتائج — دقّق كلمة البحث لنتائج أقل.")
    except Exception as e:
        logger.error(f"/find failed: {e}")
        bot.send_message(message.chat.id, f"⚠️ خطأ: {e}")

@bot.message_handler(commands=['approve_all'])
def handle_approve_all(message):
    """اعتماد جماعي لكل الطلبات المنتظرة (جديدة + تعديلات مواعيد) بضغطة واحدة."""
    if not is_authorized(message): return
    with db._get_connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED') "
            "AND change_type IN ('NEW','NEW_TENDER','UPDATED_DATE','REOPENED')"
        ).fetchone()[0]
    if n == 0:
        bot.send_message(message.chat.id, "✅ لا توجد طلبات منتظرة — كل شيء متزامن.")
        return
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"✅ نعم، اعتمد الكل ({n})", callback_data="bulkapprove_go"),
               InlineKeyboardButton("إلغاء", callback_data="bulkapprove_no"))
    bot.send_message(message.chat.id,
        f"⚠️ سيتم اعتماد *{n}* طلباً منتظراً دفعة واحدة\n"
        "(الجديدة تُسند للمهندس المقترح، وتعديلات التواريخ تحافظ على مهندسها الحالي)\n\nهل أنت متأكد؟",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('bulkapprove_'))
def handle_bulk_approve(call):
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    if call.data == 'bulkapprove_no':
        bot.edit_message_text("تم الإلغاء — لم يُعتمد شيء.", call.message.chat.id, call.message.message_id)
        return
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED') "
            "AND change_type IN ('NEW','NEW_TENDER','UPDATED_DATE','REOPENED') ORDER BY created_at"
        ).fetchall()
    done, lines = 0, []
    for row in rows:
        try:
            eng = _auto_engineer_for(row)
            db.approve_change(row['id'], eng)
            kind = {"NEW": "🆕", "NEW_TENDER": "🆕", "REOPENED": "🔄"}.get(row['change_type'], "📅")
            lines.append(f"{kind} {str(row['title'])[:42]} ← {eng}")
            _notify_engineer(eng, "📌 أُسندت إليك منافسة:" + chr(10) + str(row['title']))
            done += 1
        except Exception as e:
            logger.error(f"Bulk approve failed for id={row['id']}: {e}")
    summary = f"✅ *تم اعتماد {done} طلباً:*\n" + "\n".join(lines[:20])
    if len(lines) > 20:
        summary += f"\n… و{len(lines)-20} أخرى"
    bot.edit_message_text(summary, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    logger.info(f"BULK APPROVE: {done} items approved via Telegram.")

@bot.message_handler(commands=['automode'])
def handle_automode(message):
    """تفعيل/إيقاف المزامنة الآلية الكاملة (اعتماد تلقائي + إشعار للعلم فقط)."""
    if not is_authorized(message): return
    parts = (message.text or "").strip().split()
    if len(parts) > 1 and parts[1].lower() in ("on", "off"):
        save_state(auto_approve=(parts[1].lower() == "on"))
        logger.info(f"AUTO-APPROVE mode set to {parts[1].lower()} via Telegram.")
    status = "🟢 مفعّل — الاعتماد تلقائي والإشعارات للعلم فقط" if is_auto_approve() \
             else "🔴 متوقف — كل تغيير يحتاج موافقتك (الوضع الحالي)"
    bot.send_message(message.chat.id,
        f"🤖 *وضع المزامنة الآلية:* {status}\n\n"
        "للتبديل: /automode on أو /automode off",
        parse_mode="Markdown")

@bot.message_handler(commands=['predict'])
def handle_predict(message):
    """V6: توقع تمديد المنافسات النشطة بناءً على سلوك الجهات التاريخي."""
    if not is_authorized(message): return
    try:
        from analytics_engine import format_extension_prediction_for_telegram
        bot.send_message(message.chat.id,
                         format_extension_prediction_for_telegram(db),
                         parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/predict failed: {e}")
        bot.send_message(message.chat.id, f"⚠️ تعذر حساب التوقع: {e}")

@bot.message_handler(commands=['news'])
def handle_news(message):
    if not is_authorized(message): return
    logger.info(f"Manual /news command received from chat_id={message.chat.id}")
    bot.send_message(message.chat.id, "🔎 حاضر، سأفحص المنصة الآن وأقارنها بقاعدة البيانات...")
    threading.Thread(target=run_manual_news_check, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(commands=['list'])
def handle_list(message):
    if not is_authorized(message): return
    bot.send_message(message.chat.id, "📋 حاضر، سأحدّث قائمة المنصة وأقارنها بقاعدة البيانات...")
    threading.Thread(target=run_manual_list_report, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(commands=['list_d'])
def handle_list_details(message):
    if not is_authorized(message): return
    bot.send_message(message.chat.id, "📄 حاضر، سأجهز لك جدول المنافسات الحالي...")
    threading.Thread(target=send_tenders_detail_table, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(func=lambda message: bool(getattr(message, "text", "")) and message.text.strip().split()[0].lower().split("@")[0] == "/list-d")
def handle_list_details_hyphen(message):
    if not is_authorized(message): return
    bot.send_message(message.chat.id, "📄 حاضر، سأجهز لك جدول المنافسات الحالي...")
    threading.Thread(target=send_tenders_detail_table, args=(message.chat.id,), daemon=True).start()

@bot.message_handler(commands=['pending'])
def handle_pending(message):
    if not is_authorized(message): return
    send_open_pending_cards(message.chat.id)

@bot.message_handler(commands=['status', 'health'])
def handle_health(message):
    if not is_authorized(message): return
    bot.send_message(message.chat.id, build_health_report(), parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if not is_authorized(message): return
    stats = db.get_system_stats() # Corrected method name
    if not stats: 
        bot.send_message(message.chat.id, "❌ فشل جلب الإحصائيات.")
        return
    
    msg = (f"📊 *إحصائيات {CO_SYSTEM}*\n"
           f"━━━━━━━━━━━━━━\n"
           f"🟢 نشطة: {stats['active_count']}\n"
           f"🟡 معلقة: {stats['pending_count']}\n"
           f"⚪ مغلقة: {stats['closed_count']}\n\n"
           f"👷 *حمل المهندسين:*\n")
    
    for e in stats['engineers']:
        bar = get_progress_bar(e['load_pct'])
        msg += f"• *{e['name']}:* {e['load']}/{e['capacity']}\n  [{bar}] {e['load_pct']}%\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['backup'])
def handle_manual_backup(message):
    if not is_authorized(message): return
    ok = job_backup_system()
    if ok:
        bot.send_message(message.chat.id, "✅ تم إرسال النسخة الاحتياطية بنجاح.")
    else:
        bot.send_message(message.chat.id, "❌ فشل إرسال النسخة الاحتياطية. راجع /health أو سجل البوت.")

@bot.message_handler(commands=['report'])
def handle_report(message):
    if not is_authorized(message): return
    if not PDF_OK:
        bot.send_message(message.chat.id,
            "⚠️ مكتبة `reportlab` غير مثبّتة على السيرفر.\n"
            "شغّل: `pip install reportlab` ثم أعد المحاولة.",
            parse_mode="Markdown")
        return
    bot.send_message(message.chat.id, "⏳ جاري إنشاء التقرير الشهري، لحظة...")
    job_monthly_report()

@bot.message_handler(commands=['test'])
def handle_test(message):
    if not is_authorized(message): return
    bot.send_message(
        message.chat.id,
        "🧪 *اختبار إشعار فقط - لا يؤثر على قاعدة البيانات*\n\n"
        "هذه رسالة تجربة من البوت. لم يتم إنشاء pending، ولم يتم تعديل قاعدة البيانات، ولا يوجد إجراء مطلوب.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['lastlog'])
def handle_lastlog(message):
    if not is_authorized(message): return
    log_text = read_last_log_lines(45)
    if len(log_text) > 3500:
        log_text = log_text[-3500:]
    bot.send_message(message.chat.id, f"```text\n{log_text}\n```", parse_mode="Markdown")

@bot.message_handler(commands=['pause'])
def handle_pause(message):
    if not is_authorized(message): return
    save_state(paused=True, paused_at=utc_now_iso(), paused_by=getattr(message.from_user, "id", "telegram"))
    bot.send_message(message.chat.id, "⏸️ تم إيقاف مزامنة المنصة مؤقتاً. النسخ الاحتياطية وأوامر تيليجرام ستبقى تعمل.")

@bot.message_handler(commands=['resume'])
def handle_resume(message):
    if not is_authorized(message): return
    save_state(paused=False, resumed_at=utc_now_iso())
    bot.send_message(message.chat.id, "▶️ تم تشغيل المزامنة مرة أخرى. سأبدأ الفحص في الدورة القادمة.")

@bot.message_handler(commands=['addengineer'])
def handle_add_engineer(message):
    """إضافة مهندس ديناميكياً — يظهر فوراً كزر في التعيين والاشتراك.
    الصيغة: /addengineer <الاسم> [السعة]   (السعة اختيارية، الافتراضي 5)."""
    if not is_authorized(message): return
    tokens = (message.text or "").split()[1:]
    if not tokens:
        bot.send_message(
            message.chat.id,
            "🧩 *إضافة مهندس*\n"
            "الصيغة: `/addengineer الاسم [السعة]`\n"
            "أمثلة:\n"
            "• `/addengineer وسيم`\n"
            "• `/addengineer عبدالله الحربي 8`",
            parse_mode="Markdown")
        return
    # لو آخر عنصر رقماً صحيحاً اعتبرناه السعة، والباقي اسماً (يدعم الأسماء المركّبة)
    capacity = 5
    if len(tokens) > 1 and tokens[-1].isdigit():
        capacity = int(tokens[-1])
        name = " ".join(tokens[:-1])
    else:
        name = " ".join(tokens)
    try:
        result = db.add_engineer(name, capacity)
    except Exception as e:
        logger.error(f"add_engineer failed for '{name}': {e}")
        bot.send_message(message.chat.id, f"❌ تعذّرت الإضافة: {e}")
        return
    if result == "ADDED":
        logger.info(f"Engineer added via Telegram: {name} (cap={capacity})")
        bot.send_message(
            message.chat.id,
            f"✅ تمت إضافة المهندس *{name}* (السعة: {capacity}).\n"
            "سيظهر الآن كزر في التعيين والاشتراك تلقائياً.",
            parse_mode="Markdown")
    elif result == "REACTIVATED":
        logger.info(f"Engineer reactivated via Telegram: {name} (cap={capacity})")
        bot.send_message(
            message.chat.id,
            f"♻️ المهندس *{name}* كان مُعطّلاً وأُعيد تفعيله (السعة: {capacity}).",
            parse_mode="Markdown")
    else:  # EXISTS
        bot.send_message(
            message.chat.id,
            f"ℹ️ المهندس *{name}* موجود ونشط بالفعل — لا حاجة لأي إجراء.",
            parse_mode="Markdown")

@bot.message_handler(commands=['deleted'])
def handle_deleted(message):
    """المنافسات التي حُذفت من المنصة قبل موعدها — آخر 30 يوماً."""
    if not is_authorized(message): return
    import bot_deletions
    bot.send_message(message.chat.id, bot_deletions.recent_deletions_text())


@bot.message_handler(func=lambda m: (
    bool(getattr(m, "text", ""))
    and not m.text.strip().startswith("/")
))
def handle_text_query(message):
    """Conversational NLQ handler — responds to free-text Arabic questions."""
    if not is_authorized(message):
        return
    logger.info(f"Chat query received from user={getattr(message.from_user,'id','?')}: {message.text[:80]}")
    try:
        from chat_handler import handle_chat_query
        response = handle_chat_query(message.text, db.db_path)
        if response:
            bot.send_message(message.chat.id, response, parse_mode="Markdown")
            return
        # لم يفهم معالج الأسئلة → المساعد الذكي يرد (إن كان مفعّلاً)
        # الاستيراد داخل الدالة عمداً: استيراده أعلى الملف يسجّل معالجات الصوت/الذكاء
        # قبل الأوامر ويكسر ترتيب المعالجات (tests/test_bot_handlers.py)
        import bot_voice_ai
        if bot_voice_ai.AI_ENABLED:
            try:
                logger.info("Chat query not understood — falling back to AI assistant")
                bot_voice_ai.reply_with_ai(message)
                return
            except Exception as e:
                logger.exception(f"AI fallback failed, showing help instead: {e}")
        bot.send_message(
            message.chat.id,
            "🤖 لم أفهم سؤالك تماماً.\n\n"
            "جرّب مثلاً:\n"
            "• _غداً معنا كم منافسة مفروض تسلم؟_\n"
            "• _المعمري معه كم منافسة؟_\n"
            "• _مواعيد منافسات محمد_\n"
            "• _من الأكثر مشغولاً؟_\n"
            "• _من عنده وقت؟_\n"
            "• _بحث عن أرامكو_\n"
            "• _كم منافسة عندنا؟_\n\n"
            "أو اكتب /help لقائمة الأوامر.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception(f"handle_text_query error: {e}")
        bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء معالجة سؤالك:\n`{e}`", parse_mode="Markdown")


@bot.message_handler(content_types=['document'])
def handle_document(message):
    if not is_authorized(message): return
    
    file_name = message.document.file_name
    if not file_name.endswith('.xlsx'):
        bot.reply_to(message, "❌ نأسف، النظام يقبل ملفات Excel فقط (.xlsx).")
        return
        
    try:
        # Download the file from Telegram
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Save it over the Master_Tenders.xlsx
        master_path = BASE_DIR / "output" / "Master_Tenders.xlsx"
        master_path.parent.mkdir(parents=True, exist_ok=True)
        with open(master_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        bot.reply_to(message, "⏳ تم استلام الملف بنجاح. جاري المزامنة مع قاعدة البيانات...")
        
        # Trigger the reverse sync
        import reverse_sync_to_sql
        updated_count = reverse_sync_to_sql.reverse_sync()
        
        bot.send_message(message.chat.id, f"✅ اكتملت المزامنة!\nتم تحديث ({updated_count}) مناقصة في النظام بناءً على ملفك.")
        logger.info(f"Manual Excel Upload applied: {updated_count} updates.")
        
    except Exception as e:
        logger.error(f"Failed to process uploaded Excel: {e}")
        bot.reply_to(message, f"❌ حدث خطأ أثناء معالجة الملف:\n{e}")

