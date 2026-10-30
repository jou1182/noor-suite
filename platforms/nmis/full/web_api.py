# -*- coding: utf-8 -*-
"""JSON APIs: tender edits, locks, results, pending approval, notes, guarantees, SSE stream, stats.

Split out of web_dashboard.py on 2026-09-23 (routes/endpoints unchanged)."""
import sqlite3
import queue as _queue
from flask import Response, jsonify, request, session
from web_core import DB_PATH, _guarantee_effective_due, _sse_clients, _sse_lock, app, ensure_guarantees_table, login_required, push_sse_event, session_engineer
# ══════════════════════════════════════════════════════
# EDIT API
# ══════════════════════════════════════════════════════
@app.route("/api/tender/<int:row_id>")
@login_required
def api_get_tender(row_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title, submission_date, assigned_engineer, engineer_locked, date_locked FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        engineers = conn.execute(
            "SELECT name FROM engineers WHERE is_active=1 ORDER BY name"
        ).fetchall()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id":       row["id"],
        "title":    row["title"],
        "date":     (row["submission_date"] or "")[:10],
        "engineer": row["assigned_engineer"] or "",
        "locked":       bool(row["engineer_locked"]),
        "date_locked":  bool(row["date_locked"]) if "date_locked" in row.keys() else False,
        "engineers": [e["name"] for e in engineers],
    })

@app.route("/api/tender/<int:row_id>/update", methods=["POST"])
@login_required
def api_update_tender(row_id):
    data     = request.get_json(force=True)
    new_eng  = (data.get("engineer") or "").strip()
    new_date = (data.get("date")     or "").strip()
    if not new_eng and not new_date:
        return jsonify({"error": "لا يوجد تعديل"}), 400
    changes = []
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT tender_id, title, assigned_engineer, submission_date FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "المنافسة غير موجودة"}), 404
        tid, title, old_eng, old_date = row
        if new_eng and new_eng != old_eng:
            conn.execute(
                "UPDATE master_tenders SET assigned_engineer=?, engineer_locked=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_eng, row_id)
            )
            conn.execute(
                "UPDATE pending_changes SET suggested_engineer=? WHERE tender_id=? AND status IN ('PENDING_APPROVAL','NOTIFIED')",
                (new_eng, tid)
            )
            conn.execute(
                "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                ("DASHBOARD_ENG_CHANGE", tid,
                 f"Engineer: {old_eng} → {new_eng} | Title: {title[:60]}", "WebDashboard")
            )
            changes.append(f"المهندس: {old_eng} ← {new_eng}")
        if new_date and new_date != (old_date or "")[:10]:
            # Update submission_date AND portal_last_seen_date together.
            # Setting portal_last_seen_date to the CURRENT portal value (which the
            # engine tracks) prevents the engine from generating a "portal changed"
            # notification purely because submission_date now differs from the portal.
            # We read the current portal_last_seen_date from DB to preserve it; if it
            # doesn't exist yet we fall back to old_date so the engine stays accurate.
            portal_row = conn.execute(
                "SELECT portal_last_seen_date FROM master_tenders WHERE id=?", (row_id,)
            ).fetchone()
            current_portal_seen = (portal_row[0] if portal_row and portal_row[0] else old_date) or old_date
            conn.execute(
                "UPDATE master_tenders "
                "SET submission_date=?, portal_last_seen_date=?, date_locked=1, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (new_date, current_portal_seen, row_id)
            )
            # Cancel ALL active pending notifications for this tender so that
            # no old Telegram approval button can override the user's manual date.
            # We delete any change_type (UPDATED_DATE, NEW, etc.) that is still
            # approvable (PENDING_APPROVAL or NOTIFIED).  If approve_change() is
            # called for a deleted row it returns immediately (row not found).
            conn.execute(
                "DELETE FROM pending_changes WHERE tender_id=? AND status IN ('PENDING_APPROVAL','NOTIFIED')",
                (tid,)
            )
            conn.execute(
                "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                ("DASHBOARD_DATE_CHANGE", tid,
                 f"Date: {old_date} → {new_date} | Title: {title[:60]}", "WebDashboard")
            )
            changes.append(f"التاريخ: {old_date} ← {new_date}")
        conn.commit()
    return jsonify({"ok": True, "changes": changes})

# ══════════════════════════════════════════════════════
# RESULTS API
# ══════════════════════════════════════════════════════




@app.route("/api/tender/<int:row_id>/toggle-date-lock", methods=["POST"])
@login_required
def api_toggle_date_lock(row_id):
    """تبديل حالة قفل تاريخ التقديم (مقفول / مفتوح)."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title, tender_id, submission_date, date_locked FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "المنافسة غير موجودة"}), 404

        new_lock = 0 if row["date_locked"] else 1
        conn.execute(
            "UPDATE master_tenders SET date_locked=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_lock, row_id)
        )
        action = "LOCK_DATE" if new_lock else "UNLOCK_DATE"
        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            (action, str(row_id),
             f"{'قفل' if new_lock else 'فتح'} تاريخ {row['submission_date']} | {row['title'][:60]}",
             "WebDashboard")
        )
        conn.commit()

    return jsonify({
        "ok": True,
        "locked": bool(new_lock),
        "message": "🔒 التاريخ مقفول — لن يتغير تلقائياً" if new_lock else "🔓 التاريخ مفتوح — قد يتغير بتغيير المنصة"
    })

@app.route("/api/tender/<int:row_id>/toggle-lock", methods=["POST"])
@login_required
def api_toggle_engineer_lock(row_id):
    """تبديل حالة قفل تعيين المهندس (مقفول / مفتوح)."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title, assigned_engineer, engineer_locked FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "المنافسة غير موجودة"}), 404

        new_lock = 0 if row["engineer_locked"] else 1
        conn.execute(
            "UPDATE master_tenders SET engineer_locked=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_lock, row_id)
        )
        action = "LOCK_ENGINEER" if new_lock else "UNLOCK_ENGINEER"
        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            (action, row["tender_id"] if "tender_id" in row.keys() else str(row_id),
             f"{'قفل' if new_lock else 'فتح'} تعيين {row['assigned_engineer']} | {row['title'][:60]}",
             "WebDashboard")
        )
        conn.commit()

    return jsonify({
        "ok": True,
        "locked": bool(new_lock),
        "message": "🔒 تعيين المهندس مقفول — لن يتغير تلقائياً" if new_lock else "🔓 تعيين المهندس مفتوح — يمكن للنظام تغييره"
    })

@app.route("/api/bulk_assign", methods=["POST"])
@login_required
def api_bulk_assign():
    data     = request.get_json(force=True)
    engineer = (data.get("engineer") or "").strip()
    ids      = data.get("ids") or []
    if not engineer:
        return jsonify({"error": "اختر مهندساً أولاً"}), 400
    if not ids:
        return jsonify({"error": "لا توجد مناقصات محددة"}), 400
    updated = 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        for row_id in ids:
            try:
                row = conn.execute(
                    "SELECT tender_id, title, assigned_engineer FROM master_tenders WHERE id=?",
                    (row_id,)
                ).fetchone()
                if not row:
                    continue
                tid, title, old_eng = row
                conn.execute(
                    "UPDATE master_tenders SET assigned_engineer=?, engineer_locked=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (engineer, row_id)
                )
                conn.execute(
                    "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
                    ("BULK_ENG_ASSIGN", tid,
                     f"Bulk: {old_eng or '—'} → {engineer} | {title[:60]}", "WebDashboard")
                )
                updated += 1
            except Exception:
                continue
        conn.commit()
    return jsonify({"ok": True, "updated": updated,
                    "message": f"✅ تم تعيين {engineer} على {updated} منافسة"})

@app.route("/api/result/<int:row_id>")
@login_required
def api_get_result(row_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        t = conn.execute(
            "SELECT tender_id, title, owner, business_type, submission_date, assigned_engineer FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        if not t:
            return jsonify({"error": "not found"}), 404
        existing = conn.execute(
            "SELECT * FROM tender_results WHERE tender_id=? ORDER BY recorded_at DESC LIMIT 1",
            (t["tender_id"],)
        ).fetchone()
    return jsonify({
        "tender_id": t["tender_id"],
        "title":     t["title"],
        "existing":  dict(existing) if existing else None,
    })

@app.route("/api/result/<int:row_id>/save", methods=["POST"])
@login_required
def api_save_result(row_id):
    d = request.get_json(force=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        t = conn.execute(
            "SELECT tender_id, title, owner, business_type, submission_date, assigned_engineer FROM master_tenders WHERE id=?",
            (row_id,)
        ).fetchone()
        if not t:
            return jsonify({"error": "المنافسة غير موجودة"}), 404
        existing = conn.execute(
            "SELECT id FROM tender_results WHERE tender_id=?", (t["tender_id"],)
        ).fetchone()
        did_submit  = 1 if d.get("did_submit") else 0
        result      = d.get("result", "pending")
        our_price   = float(d["our_price"])  if d.get("our_price")  else None
        win_price   = float(d["win_price"])  if d.get("win_price")  else None
        notes       = (d.get("notes") or "").strip()
        if existing:
            conn.execute("""
                UPDATE tender_results SET did_submit=?, result=?, our_price=?, winning_price=?,
                notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
            """, (did_submit, result, our_price, win_price, notes, existing["id"]))
        else:
            conn.execute("""
                INSERT INTO tender_results
                (tender_id, title, owner, business_type, submission_date, assigned_engineer,
                 did_submit, result, our_price, winning_price, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (t["tender_id"], t["title"], t["owner"], t["business_type"],
                  t["submission_date"], t["assigned_engineer"],
                  did_submit, result, our_price, win_price, notes))
        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            ("RESULT_RECORDED", t["tender_id"],
             f"result={result} | submit={did_submit} | price={our_price}", "WebDashboard")
        )
        conn.commit()
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════
# PENDING APPROVAL API
# ══════════════════════════════════════════════════════
@app.route("/api/pending/<int:pending_id>/approve", methods=["POST"])
@login_required
def api_approve_pending(pending_id):
    data   = request.get_json(force=True)
    action = data.get("action", "approve")   # 'approve' | 'reject'
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        p = conn.execute(
            "SELECT * FROM pending_changes WHERE id=?", (pending_id,)
        ).fetchone()
        if not p:
            return jsonify({"error": "الطلب غير موجود"}), 404

        new_status = "APPROVED" if action == "approve" else "REJECTED"
        conn.execute(
            "UPDATE pending_changes SET status=? WHERE id=?",
            (new_status, pending_id)
        )

        if action == "approve":
            # Apply the suggested engineer if this is an engineer-assignment change
            eng = p["suggested_engineer"]
            if eng:
                conn.execute("""
                    UPDATE master_tenders
                    SET assigned_engineer=?, engineer_locked=1, updated_at=CURRENT_TIMESTAMP
                    WHERE title=?
                """, (eng, p["title"]))

        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            ("PENDING_" + new_status, p["title"][:60],
             f"{action} by WebDashboard | eng={p['suggested_engineer'] or '—'}", "WebDashboard")
        )
        conn.commit()
    return jsonify({"ok": True, "status": new_status})

@app.route("/api/tender/<int:row_id>/notes", methods=["POST"])
@login_required
def api_save_notes(row_id):
    d = request.get_json(force=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        existing = conn.execute(
            "SELECT id FROM tender_notes WHERE tender_id=?", (row_id,)
        ).fetchone()
        vals = (
            (d.get("notes") or "").strip(),
            1 if d.get("is_extended") else 0,
            int(d.get("extension_count") or 0),
            (d.get("extension_dates") or "").strip(),
            1 if d.get("submitted_to_review") else 0,
            (d.get("review_date") or "").strip(),
            1 if d.get("submitted_to_upload") else 0,
            (d.get("upload_submit_date") or "").strip(),
            1 if d.get("uploaded_to_platform") else 0,
            (d.get("platform_upload_date") or "").strip(),
        )
        if existing:
            conn.execute("""
                UPDATE tender_notes
                SET notes=?, is_extended=?, extension_count=?, extension_dates=?,
                    submitted_to_review=?, review_date=?,
                    submitted_to_upload=?, upload_submit_date=?,
                    uploaded_to_platform=?, platform_upload_date=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE tender_id=?
            """, vals + (row_id,))
        else:
            conn.execute("""
                INSERT INTO tender_notes
                (notes, is_extended, extension_count, extension_dates,
                 submitted_to_review, review_date,
                 submitted_to_upload, upload_submit_date,
                 uploaded_to_platform, platform_upload_date, tender_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, vals + (row_id,))
        # Audit log
        t_row = conn.execute(
            "SELECT tender_id FROM master_tenders WHERE id=?", (row_id,)
        ).fetchone()
        tid = t_row[0] if t_row else str(row_id)
        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            ("NOTES_UPDATED", tid, "Dashboard notes/checklist saved", "WebDashboard")
        )
        conn.commit()
    import web_tasks   # مراحل المنافسة تحرّك مهام القالب (لوحة المهام، إن كانت مفعّلة)
    web_tasks.on_stage_change()
    return jsonify({"ok": True})


@app.route("/api/tender/<int:row_id>/guarantee", methods=["GET", "POST"])
@login_required
def api_tender_guarantee(row_id):
    """v5.6: read/save initial bank-guarantee state for a tender."""
    ensure_guarantees_table()
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        status = d.get("status", "PENDING")
        if status not in ("PENDING", "IN_PROGRESS", "READY", "SUBMITTED", "NOT_REQUIRED"):
            status = "PENDING"
        due = (d.get("due_date") or "").strip()[:10]
        notes = (d.get("notes") or "").strip()[:500]
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("""INSERT INTO tender_guarantees (tender_row_id, due_date, status, notes, updated_at)
                            VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                            ON CONFLICT(tender_row_id) DO UPDATE SET
                              due_date=excluded.due_date, status=excluded.status,
                              notes=excluded.notes, updated_at=CURRENT_TIMESTAMP""",
                         (row_id, due, status, notes))
            conn.commit()
        try:
            push_sse_event("guarantee", {"id": row_id, "status": status})
        except Exception:
            pass
        import web_tasks
        web_tasks.on_stage_change()
        return jsonify({"ok": True})
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        g = conn.execute("SELECT * FROM tender_guarantees WHERE tender_row_id=?", (row_id,)).fetchone()
        t = conn.execute("SELECT submission_date FROM master_tenders WHERE id=?", (row_id,)).fetchone()
    if not t:
        return jsonify({"ok": False, "error": "not found"}), 404
    g = dict(g) if g else {}
    due, is_auto = _guarantee_effective_due(t["submission_date"], g.get("due_date", ""))
    return jsonify({"ok": True, "status": g.get("status", "PENDING"),
                    "due_date": due.isoformat() if due else "",
                    "auto": is_auto, "notes": g.get("notes", "")})

@app.route("/api/result-rec/<int:rec_id>/quick", methods=["POST"])
@login_required
def api_result_quick(rec_id):
    """v5.6.1: one-tap result from the follow-up list."""
    d = request.get_json(silent=True) or {}
    result = d.get("result", "pending")
    if result not in ("won", "lost", "pending", "cancelled", "unknown"):
        return jsonify({"ok": False, "error": "bad result"}), 400
    with sqlite3.connect(str(DB_PATH)) as conn:
        row = conn.execute("SELECT tender_id FROM tender_results WHERE id=?", (rec_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "not found"}), 404
        conn.execute("""UPDATE tender_results
                        SET result=?, did_submit=CASE WHEN ? IN ('won','lost') THEN 1 ELSE did_submit END,
                            updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                     (result, result, rec_id))
        conn.execute(
            "INSERT INTO audit_log (action, target_tender, details, performed_by) VALUES (?,?,?,?)",
            ("RESULT_QUICK", row[0], f"result={result}", "WebDashboard"))
        conn.commit()
    try:
        push_sse_event("result", {"rec": rec_id, "result": result})
    except Exception:
        pass
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════
# LOGIN TEMPLATE
# ══════════════════════════════════════════════════════
# LOGIN_HTML: moved to dashboard_templates.py

# ══════════════════════════════════════════════════════
# TENDER DETAIL TEMPLATE
# ══════════════════════════════════════════════════════
# TENDER_DETAIL_HTML: moved to dashboard_templates.py

# ══════════════════════════════════════════════════════
# DASHBOARD TEMPLATE — REDESIGNED
# ══════════════════════════════════════════════════════
# DASHBOARD_HTML: moved to dashboard_templates.py

# ══════════════════════════════════════════════════════
# RESULTS TEMPLATE — REDESIGNED
# ══════════════════════════════════════════════════════
# RESULTS_HTML: moved to dashboard_templates.py


# ====================================================
# REAL-TIME API ROUTES
# ====================================================
@app.route("/api/stream")
def sse_stream():
    # Server-Sent Events endpoint — dashboard clients connect here.
    if not (session.get("ok") or session.get("admin_ok") or session_engineer()):
        return "Unauthorized", 401

    def event_gen():
        q = _queue.Queue(maxsize=30)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield 'data: ' + msg + '\n\n'
                except _queue.Empty:
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        event_gen(),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    )


@app.route("/api/push-event", methods=["POST"])
def api_push_event():
    # Internal: bot posts events here, dashboard receives via SSE.
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"ok": False, "error": "localhost only"}), 403
    data = request.get_json(silent=True) or {}
    push_sse_event(data.get("type", "update"), data.get("data", {}))
    return jsonify({"ok": True})


@app.route("/api/stats")
def api_stats():
    # Live JSON stats for dashboard auto-refresh.
    if not session.get("ok"):
        return jsonify({"error": "unauthorized"}), 401
    try:
        import sqlite3, time as _t
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        active  = con.execute("SELECT COUNT(*) FROM master_tenders WHERE status NOT IN ('CLOSED','REJECTED')").fetchone()[0]
        pending = con.execute("SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED')").fetchone()[0]
        closed  = con.execute("SELECT COUNT(*) FROM master_tenders WHERE status='CLOSED'").fetchone()[0]
        soon    = con.execute(
            "SELECT title, submission_date, COALESCE(assigned_engineer,'') eng"
            " FROM master_tenders"
            " WHERE status NOT IN ('CLOSED','REJECTED')"
            " AND date(submission_date) BETWEEN date('now') AND date('now','+7 days')"
            " ORDER BY submission_date LIMIT 5"
        ).fetchall()
        con.close()
        return jsonify({
            "active": active, "pending": pending, "closed": closed,
            "soon": [{"title": r["title"][:55], "date": r["submission_date"], "eng": r["eng"]} for r in soon],
            "ts": int(_t.time())
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


# ── API تحديث حالة المنافسة (للأدمن من engineer-view) ───────────────────────
@app.route('/api/admin/tender/<int:tid>/status', methods=['POST'])
@login_required
def api_admin_update_status(tid):
    """الأدمن يُحدّث حالة منافسة من بوابة المهندسين"""
    import sqlite3 as _sq3
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "")
    if action not in ("submit", "no", "won", "lost"):
        return jsonify({"ok": False, "error": "إجراء غير صالح"}), 400

    with _sq3.connect(str(DB_PATH)) as conn:
        conn.row_factory = _sq3.Row
        row = conn.execute(
            "SELECT id, tender_id, title, owner, assigned_engineer FROM master_tenders WHERE id=?",
            (tid,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "غير موجودة"}), 404

        tid_str  = row["tender_id"]
        eng_name = row["assigned_engineer"] or ""
        existing = conn.execute(
            "SELECT id FROM tender_results WHERE tender_id=?", (tid_str,)
        ).fetchone()

        if action == "submit":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=1, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
            else:
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit) VALUES (?,?,?,?,1)",
                    (tid_str, row["title"], row["owner"], eng_name)
                )
        elif action == "no":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=0, result=NULL, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
        elif action == "won":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=1, result='won', updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
            else:
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit, result) VALUES (?,?,?,?,1,'won')",
                    (tid_str, row["title"], row["owner"], eng_name)
                )
        elif action == "lost":
            if existing:
                conn.execute("UPDATE tender_results SET did_submit=1, result='lost', updated_at=CURRENT_TIMESTAMP WHERE tender_id=?", (tid_str,))
            else:
                conn.execute(
                    "INSERT INTO tender_results (tender_id, title, owner, assigned_engineer, did_submit, result) VALUES (?,?,?,?,1,'lost')",
                    (tid_str, row["title"], row["owner"], eng_name)
                )
        conn.commit()

    return jsonify({"ok": True, "action": action})

