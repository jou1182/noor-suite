# -*- coding: utf-8 -*-
"""Inline-button callback handlers (approve/reject/engineer/dual approval).

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot_core import OWNER_TELEGRAM_IDS, TELEGRAM_TOKEN, bot, db, is_authorized, logger
from bot_notifications import _ensure_subs_table, _guarantee_status_markup, _notify_engineer, _sub_of, _subs_for
# ============================================================
# 6. TELEGRAM CALLBACK HANDLERS
# ============================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def handle_approve(call):
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ خطأ أمني: غير مصرح لك.", show_alert=True)
        return
    """Handles Approve Button"""
    _, pending_id, eng_name = call.data.split('_', 2)

    # Get title + status; block double-approval from stale cards
    with db._get_connection() as conn:
        p = conn.execute("SELECT title, status FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
        title = p[0] if p else None
        cur_status = p[1] if p else None
    if cur_status not in ('PENDING_APPROVAL', 'NOTIFIED'):
        bot.answer_callback_query(call.id, "⚠️ هذا الطلب تمت معالجته مسبقاً — لا حاجة لإجراء.", show_alert=True)
        return

    # Proceed with database approval
    db.approve_change(pending_id, eng_name)
    logger.info(f"APPROVED: Pending ID {pending_id} assigned to {eng_name}")

    bot.edit_message_text(
        f"✅ تم بنجاح اعتماد المناقصة: *{title}*\nللمهندس: *{eng_name}* وتم تحديث ملف الماستر!",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown'
    )

    # SMART CLEANUP: Invalidate any other pending records for the same title
    if title:
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE pending_changes SET status = 'CLEANED' "
                "WHERE title = ? AND status IN ('PENDING_APPROVAL', 'NOTIFIED')",
                (title,)
            )
            conn.commit()
            logger.info(f"Cleanup: Marked all duplicate pending items for '{title}' as CLEANED.")
    
    bot.answer_callback_query(call.id, "تم الاعتماد بنجاح!")


@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def handle_sub_pick(call):
    """تثبيت اشتراك المهندس (خاص فقط — الأزرار تظهر بعد PIN صحيح)."""
    if getattr(call.message.chat, "type", "") != "private":
        bot.answer_callback_query(call.id, "الاشتراك في الخاص فقط.", show_alert=True)
        return
    _, eng_name = call.data.split('_', 1)
    import engineer_accounts
    from company_profile import feature_enabled
    if feature_enabled(engineer_accounts.FEATURE):
        with db._get_connection() as conn:
            blocked = engineer_accounts.pin_subscription_blocked(conn, eng_name)
        if blocked:   # 2026-09-25: صاحب الحساب الشخصي يربط من بوابته فقط (لا أحد يشترك باسم زميل)
            bot.answer_callback_query(call.id, "لهذا الاسم حساب شخصي — اربط من بوابتك", show_alert=True)
            bot.send_message(call.message.chat.id,
                             f"🔐 م. {eng_name} له حساب شخصي، فالربط يتم من بوابته فقط:\n"
                             "ادخل /engineer بكلمة مرورك ← «🔗 ربط تليجرام» ← أرسل هنا /link الرمز.")
            return
    with db._get_connection() as conn:
        _ensure_subs_table(conn)
        conn.execute("""INSERT INTO engineer_subs (chat_id, engineer_name, subscribed_at)
                        VALUES (?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(chat_id) DO UPDATE SET
                          engineer_name=excluded.engineer_name, subscribed_at=CURRENT_TIMESTAMP""",
                     (call.message.chat.id, eng_name))
        conn.commit()
    db.log_audit("ENG_SUBSCRIBE", eng_name, f"chat_id={call.message.chat.id}", "TelegramBot")
    bot.edit_message_text(
        f"✅ تم اشتراكك باسم *{eng_name}*" + chr(10) + chr(10) +
        "سيصلك هنا خاصاً:" + chr(10) +
        "• إشعار فوري عند إسناد منافسة إليك" + chr(10) +
        "• ملخص صباحي يومياً 8:15 بمنافساتك ومواعيدها وضماناتها" + chr(10) + chr(10) +
        "أوامرك: /mytenders لعرض منافساتك الآن — /unsubscribe لإلغاء الاشتراك",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(call.id, f"أهلاً {eng_name}!")
    logger.info(f"Engineer subscribed: {eng_name} chat={call.message.chat.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('gst_'))
def handle_guarantee_set(call):
    """تحديث حالة الضمان من زر تيليجرام."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, mid, status = call.data.split('_', 2)
    labels = {"READY": "🟢 جاهز", "SUBMITTED": "✅ قُدّم مع العرض", "NOT_REQUIRED": "⚪ غير مطلوب"}
    if status not in labels:
        return
    with db._get_connection() as conn:
        t = conn.execute("SELECT title FROM master_tenders WHERE id = ?", (mid,)).fetchone()
        if not t:
            bot.answer_callback_query(call.id, "⚠️ لم أجد المنافسة.", show_alert=True)
            return
        conn.execute("""INSERT INTO tender_guarantees (tender_row_id, status, updated_at)
                        VALUES (?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(tender_row_id) DO UPDATE SET
                          status=excluded.status, updated_at=CURRENT_TIMESTAMP""", (mid, status))
        conn.commit()
    db.log_audit("GUARANTEE_TG", t[0], f"status={status}", "TelegramBot")
    bot.edit_message_text(f"🛡️ *{str(t[0])}*\nحالة الضمان: {labels[status]} ✓",
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(call.id, "تم التحديث ✓")
    logger.info(f"Guarantee status via TG: master_id={mid} -> {status}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fres_'))
def handle_followup_result(call):
    """تسجيل نتيجة عرض من زر تيليجرام."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, rec_id, res = call.data.split('_', 2)
    labels = {"won": "🏆 فوز", "lost": "❌ خسارة", "unknown": "⚪ لم تُعلن"}
    if res not in labels:
        return
    with db._get_connection() as conn:
        row = conn.execute("SELECT title FROM tender_results WHERE id = ?", (rec_id,)).fetchone()
        if not row:
            bot.answer_callback_query(call.id, "⚠️ لم أجد السجل.", show_alert=True)
            return
        conn.execute("""UPDATE tender_results
                        SET result=?, did_submit=CASE WHEN ? IN ('won','lost') THEN 1 ELSE did_submit END,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?""", (res, res, rec_id))
        conn.commit()
    db.log_audit("RESULT_TG", row[0], f"result={res}", "TelegramBot")
    bot.edit_message_text(f"📋 *{str(row[0])}*\nالنتيجة: {labels[res]} ✓",
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(call.id, "سُجلت النتيجة ✓")
    logger.info(f"Result via TG: rec_id={rec_id} -> {res}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('gmenu_'))
def handle_guarantee_menu(call):
    """عرض أزرار حالة الضمان على بطاقة /find."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, mid = call.data.split('_', 1)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                  reply_markup=_guarantee_status_markup(mid))
    bot.answer_callback_query(call.id, "اختر حالة الضمان")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fes_'))
def handle_find_eng_set(call):
    """تعيين مهندس من بطاقة /find وتثبيته."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, mid, eng_name = call.data.split('_', 2)
    with db._get_connection() as conn:
        t = conn.execute("SELECT title FROM master_tenders WHERE id = ?", (mid,)).fetchone()
        if not t:
            bot.answer_callback_query(call.id, "⚠️ لم أجد المنافسة.", show_alert=True)
            return
        conn.execute("""UPDATE master_tenders SET assigned_engineer=?, engineer_locked=1,
                        updated_at=CURRENT_TIMESTAMP WHERE id=?""", (eng_name, mid))
        conn.commit()
    db.log_audit("CHANGE_ENG", t[0], f"/find reassigned to {eng_name} (locked)", "TelegramBot")
    db.export_master_excel()
    bot.edit_message_text(f"✅ *{str(t[0])}*\nالمهندس الجديد: *{eng_name}* 🔒",
                          call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(call.id, f"تم الإسناد إلى {eng_name}")
    _notify_engineer(eng_name, "📌 أُسندت إليك منافسة:" + chr(10) + str(t[0]))

@bot.callback_query_handler(func=lambda call: call.data.startswith('fem_'))
def handle_find_eng_menu(call):
    """قائمة المهندسين على بطاقة /find."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, mid = call.data.split('_', 1)
    engineers = db.get_all_engineers()
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(*[InlineKeyboardButton(e['name'], callback_data=f"fes_{mid}_{e['name']}")
                 for e in engineers])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "اختر المهندس")

@bot.callback_query_handler(func=lambda call: call.data.startswith('aes_'))
def handle_autoeng_set(call):
    """مزامنة آلية: تطبيق تغيير المهندس وتثبيته ضد أي اقتراح مستقبلي."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, pending_id, eng_name = call.data.split('_', 2)
    with db._get_connection() as conn:
        p = conn.execute("SELECT title FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
        if not p:
            bot.answer_callback_query(call.id, "⚠️ لم أجد السجل.", show_alert=True)
            return
        conn.execute(
            "UPDATE master_tenders SET assigned_engineer = ?, engineer_locked = 1, "
            "updated_at = CURRENT_TIMESTAMP WHERE title = ?",
            (eng_name, p[0])
        )
        conn.commit()
    db.log_audit("CHANGE_ENG", p[0], f"Auto-sync reassigned to {eng_name} (locked)", "Admin")
    db.export_master_excel()
    bot.edit_message_text(
        f"✅ تم تغيير المهندس إلى: *{eng_name}* وتثبيته 🔒\n*{p[0]}*",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id, f"تم الإسناد إلى {eng_name}")
    _notify_engineer(eng_name, "📌 أُسندت إليك منافسة:" + chr(10) + str(p[0]))
    logger.info(f"AUTO-SYNC REASSIGN: pending_id={pending_id} -> {eng_name} (locked)")

@bot.callback_query_handler(func=lambda call: call.data.startswith('aem_'))
def handle_autoeng_menu(call):
    """مزامنة آلية: عرض قائمة المهندسين للتبديل بضغطة."""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ غير مصرح.", show_alert=True)
        return
    _, pending_id = call.data.split('_', 1)
    engineers = db.get_all_engineers()
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(*[InlineKeyboardButton(e['name'], callback_data=f"aes_{pending_id}_{e['name']}")
                 for e in engineers])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "اختر المهندس الجديد")

@bot.callback_query_handler(func=lambda call: call.data.startswith('changeeng_'))
def handle_change_eng(call):
    """Handles Change Engineer Button"""
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ خطأ أمني: غير مصرح لك.", show_alert=True)
        return

    _, pending_id = call.data.split('_')
    engineers = db.get_all_engineers()
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(eng['name'], callback_data=f"approve_{pending_id}_{eng['name']}")
        for eng in engineers
    ]
    markup.add(*buttons)
    bot.edit_message_text(
        "🔄 الرجاء اختيار المهندس المراد إسناد المناقصة له من القائمة:",
        call.message.chat.id, call.message.message_id, reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def handle_reject(call):
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "❌ خطأ أمني: غير مصرح لك.", show_alert=True)
        return
    """Handles Reject Button"""
    _, pending_id = call.data.split('_')
    db.delete_pending_change(pending_id)
    logger.info(f"REJECTED: Pending ID {pending_id} dismissed by user.")
    bot.edit_message_text(
        "❌ تم تجاهل المناقصة وإزالتها من قائمة المعلقات.",
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id, "تم التجاهل")

# ============================================================
# ROADMAP_V6 Phase 4: موافقة مزدوجة اختيارية -- مراحل المهندس والمدير
# (تُستخدم فقط لو company_profile.json.dual_approval=true؛ راجع send_approval_message)
# ============================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('engapprove_'))
def handle_eng_approve(call):
    """المرحلة 1: موافقة المهندس المعيّن الفنية (خاص فقط، ويجب أن يكون هو صاحب البطاقة)."""
    if getattr(call.message.chat, "type", "") != "private":
        bot.answer_callback_query(call.id, "❌ هذا الإجراء متاح فقط في الخاص.", show_alert=True)
        return
    _, pending_id, eng_name = call.data.split('_', 2)
    if str(call.message.chat.id) not in {str(c) for c in _subs_for(eng_name)}:
        bot.answer_callback_query(call.id, "❌ خطأ أمني: هذه ليست بطاقتك.", show_alert=True)
        return

    with db._get_connection() as conn:
        p = conn.execute("SELECT title, status FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
        title = p[0] if p else None
        cur_status = p[1] if p else None
    if cur_status not in ('PENDING_APPROVAL', 'NOTIFIED'):
        bot.answer_callback_query(call.id, "⚠️ هذا الطلب تمت معالجته مسبقاً.", show_alert=True)
        return

    db.set_approval_stage(pending_id, "awaiting_manager")
    bot.edit_message_text(
        f"✅ *وافقت فنياً على:* {title}\nبانتظار الموافقة النهائية من المدير.",
        call.message.chat.id, call.message.message_id, parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id, "تم إرسالها للمدير للموافقة النهائية")

    mgr_markup = InlineKeyboardMarkup(row_width=1)
    mgr_markup.add(
        InlineKeyboardButton(f"✅ موافقة نهائية لـ ({eng_name})", callback_data=f"mgrapprove_{pending_id}_{eng_name}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"mgrreject_{pending_id}")
    )
    mgr_msg = (f"👔 *مطلوب موافقتك النهائية*\n\n📌 *الاسم:* {title}\n"
               f"🔧 *وافق فنياً:* {eng_name}\n")
    import requests
    for mid in OWNER_TELEGRAM_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": mid, "text": mgr_msg, "parse_mode": "Markdown",
                      "reply_markup": mgr_markup.to_json()},
                timeout=15
            )
        except Exception as e:
            logger.error(f"Manager-stage delivery failed for chat {mid}: {e}")
    logger.info(f"Dual-approval stage 2 (manager) sent for pending id={pending_id}.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('engreject_'))
def handle_eng_reject(call):
    """رفض المهندس للمرحلة الفنية -- ينهي الطلب مباشرة، لا يُصعَّد للمدير."""
    if getattr(call.message.chat, "type", "") != "private":
        bot.answer_callback_query(call.id, "❌ هذا الإجراء متاح فقط في الخاص.", show_alert=True)
        return
    _, pending_id = call.data.split('_', 1)
    with db._get_connection() as conn:
        p = conn.execute("SELECT suggested_engineer, status FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
    eng_name = p[0] if p else None
    cur_status = p[1] if p else None
    if not eng_name or str(call.message.chat.id) not in {str(c) for c in _subs_for(eng_name)}:
        bot.answer_callback_query(call.id, "❌ خطأ أمني: هذه ليست بطاقتك.", show_alert=True)
        return
    if cur_status not in ('PENDING_APPROVAL', 'NOTIFIED'):
        bot.answer_callback_query(call.id, "⚠️ هذا الطلب تمت معالجته مسبقاً.", show_alert=True)
        return

    db.delete_pending_change(pending_id)
    bot.edit_message_text(
        "❌ تم رفض المنافسة فنياً وإزالتها من قائمة المعلقات.",
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id, "تم الرفض")
    logger.info(f"Dual-approval: engineer rejected pending id={pending_id}.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('mgrapprove_'))
def handle_mgr_approve(call):
    """المرحلة 2 (الأخيرة): الموافقة النهائية من المدير -- هنا فقط يُكتب الاعتماد الفعلي."""
    if str(call.message.chat.id) not in OWNER_TELEGRAM_IDS:
        bot.answer_callback_query(call.id, "❌ خطأ أمني: غير مصرح لك بالموافقة النهائية.", show_alert=True)
        return
    _, pending_id, eng_name = call.data.split('_', 2)

    with db._get_connection() as conn:
        p = conn.execute("SELECT title, status FROM pending_changes WHERE id = ?", (pending_id,)).fetchone()
        title = p[0] if p else None
        cur_status = p[1] if p else None
    if cur_status not in ('PENDING_APPROVAL', 'NOTIFIED'):
        bot.answer_callback_query(call.id, "⚠️ هذا الطلب تمت معالجته مسبقاً — لا حاجة لإجراء.", show_alert=True)
        return

    db.approve_change(pending_id, eng_name)
    logger.info(f"DUAL-APPROVED: Pending ID {pending_id} assigned to {eng_name} (manager final sign-off).")

    bot.edit_message_text(
        f"✅ تم الاعتماد النهائي: *{title}*\nللمهندس: *{eng_name}* وتم تحديث ملف الماستر!",
        call.message.chat.id, call.message.message_id, parse_mode='Markdown'
    )

    if title:
        with db._get_connection() as conn:
            conn.execute(
                "UPDATE pending_changes SET status = 'CLEANED' "
                "WHERE title = ? AND status IN ('PENDING_APPROVAL', 'NOTIFIED')",
                (title,)
            )
            conn.commit()

    bot.answer_callback_query(call.id, "تم الاعتماد النهائي بنجاح!")
    _notify_engineer(eng_name, "🎉 اعتُمدت منافستك نهائياً:\n" + str(title))


@bot.callback_query_handler(func=lambda call: call.data.startswith('mgrreject_'))
def handle_mgr_reject(call):
    """رفض المدير في المرحلة الأخيرة -- ينهي الطلب."""
    if str(call.message.chat.id) not in OWNER_TELEGRAM_IDS:
        bot.answer_callback_query(call.id, "❌ خطأ أمني: غير مصرح لك.", show_alert=True)
        return
    _, pending_id = call.data.split('_', 1)
    db.delete_pending_change(pending_id)
    bot.edit_message_text(
        "❌ رفض المدير المنافسة نهائياً وتمت إزالتها من قائمة المعلقات.",
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id, "تم الرفض")
    logger.info(f"Dual-approval: manager rejected pending id={pending_id}.")


# ── تأكيد الاطلاع على تنبيه حذف منافسة (2026-09-24) ──────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith('delack_'))
def handle_deletion_ack(call):
    if not is_authorized(call):
        bot.answer_callback_query(call.id, "غير مصرح")
        return
    import bot_deletions
    who = (" ".join(filter(None, [call.from_user.first_name, call.from_user.last_name]))
           or call.from_user.username or str(call.from_user.id))
    row = bot_deletions.acknowledge(int(call.data.split("_", 1)[1]), who)
    if not row:
        bot.answer_callback_query(call.id, "التنبيه غير موجود")
        return
    bot.answer_callback_query(call.id, f"✅ تم تسجيل اطلاع {row['acked_by']}")
    note = f"\n\n✅ <b>تم الاطلاع وإيقاف العمل</b> — {row['acked_by']} ({str(row['acked_at'])[:16]})"
    try:
        if row["chat_message_id"] and call.message.message_id == row["chat_message_id"]:
            bot.edit_message_text(call.message.html_text + note, call.message.chat.id, call.message.message_id,
                                  parse_mode="HTML", reply_markup=None)
        if row["chat_message_id"]:
            bot.unpin_chat_message(bot_deletions.CHAT_ID, row["chat_message_id"])
    except Exception as e:
        logger.debug(f"deletion ack message update failed: {e}")


# ── أزرار /mytasks: بدء / إنجاز مهمة من تليجرام (2026-09-24) ──────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith('tsk_'))
def handle_task_button(call):
    import bot_tasks
    eng = _sub_of(call.message.chat.id)
    if not eng or not bot_tasks.enabled():
        bot.answer_callback_query(call.id, "للمهندسين المشتركين فقط", show_alert=True)
        return
    try:
        _, task_id, status = call.data.split("_", 2)
        msg = bot_tasks.apply_button(eng, int(task_id), status)
    except ValueError:
        msg = "زر غير صالح"
    bot.answer_callback_query(call.id, msg)
    text, markup = bot_tasks.my_tasks_message(eng)
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.debug(f"mytasks refresh failed: {e}")
