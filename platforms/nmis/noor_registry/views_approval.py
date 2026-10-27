"""Accept / reject a candidate tender and complete a missing field (T045, FR-006, FR-007).

Authorization always comes first (approver on this tender, through authz.authorize), then the
state rules. Each decision writes exactly one Approval through authz.record_approval, and the
whole change happens in one transaction.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

from flask import Blueprint, flash, redirect, request, url_for

from .authz import AuthzError, authorize, record_approval
from .db import utc_now
from .registry import ACCEPT_REQUIRED_FIELDS, RegistryError, parse_time
from .security import login_required, state_change
from .views_common import check_tender_id, conflict, db, message, refused, user

bp = Blueprint("approval", __name__)

TEMPLATE_PATH = Path(__file__).resolve().parent / "task_template.json"
ACCEPT_DECISIONS = ("approved", "approved_with_reservation")
# One fixed statement per completable field (the keys equal ACCEPT_REQUIRED_FIELDS).
_COMPLETE_SQL = {
    "closing_at": "UPDATE tenders SET closing_at = ?, missing_fields = ? WHERE tender_id = ?",
}


def load_template() -> dict:
    """The single task template; a malformed file is an error, never an empty task list."""
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    tasks = template.get("tasks")
    if not template.get("template_id") or not isinstance(tasks, list) or not tasks:
        raise ValueError("task template is malformed")
    for task in tasks:
        if not (task.get("key") and task.get("title") and task.get("owner_role")
                and isinstance(task.get("due_offset_days"), int)):
            raise ValueError("task template is malformed")
    return template


def _candidate_row(conn, tender_id: str):
    row = conn.execute("SELECT * FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone()
    if row["status"] != "candidate":
        raise RegistryError("not_candidate")
    return row


def _owner(conn, tender_id: str, role: str, approver_id: str) -> tuple[str, str, bool]:
    """(owner, recorded role, fallback?) — the first account holding ``role`` on this tender,
    else the approving account with its real role ``approver``, marked as a fallback."""
    row = conn.execute(
        "SELECT user_id FROM memberships WHERE tender_id = ? AND role = ? ORDER BY user_id",
        (tender_id, role)).fetchone()
    if row:
        return row["user_id"], role, False
    return approver_id, "approver", role != "approver"


def create_template_tasks(conn, tender, actor_id: str) -> int:
    """Create the template tasks of an accepted tender (caller owns the transaction)."""
    template = load_template()
    closing = parse_time(tender["closing_at"])
    for task in template["tasks"]:
        owner, role, fallback = _owner(conn, tender["tender_id"], task["owner_role"], actor_id)
        origin = f"template:{template['template_id']}:{task['key']}"
        conn.execute(
            "INSERT INTO tasks (task_id, tender_id, title, owner_user_id, owner_role, due_at,"
            " status, origin, synthetic) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, 1)",
            ("TK-" + uuid.uuid4().hex[:16], tender["tender_id"], task["title"], owner, role,
             (closing + timedelta(days=task["due_offset_days"])).isoformat(),
             origin + (":fallback" if fallback else "")))
    return len(template["tasks"])


def _reservations() -> str | None:
    text = (request.form.get("reservations") or "").strip()
    return text or None


@bp.post("/tenders/<tender_id>/accept")
@state_change
@login_required
def accept(tender_id):
    check_tender_id(tender_id)
    decision = request.form.get("decision", "")
    if decision not in ACCEPT_DECISIONS:
        return message("قرار القبول غير صالح.", 400)
    conn = db()
    try:
        with conn:
            role = authorize(conn, user(), tender_id, "accept_tender")
            tender = _candidate_row(conn, tender_id)
            if json.loads(tender["missing_fields"] or "[]"):
                raise RegistryError("missing_fields")
            record_approval(conn, actor=user(), subject_type="tender", subject_id=tender_id,
                            decision=decision, acting_role=role, tender_id=tender_id,
                            reservations=_reservations())
            conn.execute("UPDATE tenders SET status = 'accepted' WHERE tender_id = ?",
                         (tender_id,))
            count = create_template_tasks(conn, tender, user().user_id)
    except AuthzError as exc:
        return refused(exc)
    except RegistryError as exc:
        return conflict(exc)
    flash(f"قُبلت المنافسة {tender_id} وأُنشئت {count} مهام من القالب.")
    return redirect(url_for("tenders.tender_page", tender_id=tender_id))


@bp.post("/tenders/<tender_id>/reject")
@state_change
@login_required
def reject(tender_id):
    check_tender_id(tender_id)
    conn = db()
    try:
        with conn:
            role = authorize(conn, user(), tender_id, "reject_tender")
            _candidate_row(conn, tender_id)
            record_approval(conn, actor=user(), subject_type="tender", subject_id=tender_id,
                            decision="rejected", acting_role=role, tender_id=tender_id,
                            reservations=_reservations())
            conn.execute("UPDATE tenders SET status = 'rejected' WHERE tender_id = ?",
                         (tender_id,))
    except AuthzError as exc:
        return refused(exc)
    except RegistryError as exc:
        return conflict(exc)
    flash(f"رُفضت المنافسة {tender_id}.")
    return redirect(url_for("tenders.tender_page", tender_id=tender_id))


@bp.post("/tenders/<tender_id>/complete-field")
@state_change
@login_required
def complete_field(tender_id):
    check_tender_id(tender_id)
    field = request.form.get("field", "")
    value = (request.form.get("value") or "").strip()
    conn = db()
    try:
        with conn:
            role = authorize(conn, user(), tender_id, "field_completion")
            if field not in ACCEPT_REQUIRED_FIELDS:
                return message("هذا الحقل لا يُستكمل من هنا.", 400)
            try:
                parse_time(value)
            except RegistryError:
                return message("الموعد يجب أن يكون تاريخًا ووقتًا بمنطقة زمنية.", 400)
            tender = conn.execute("SELECT * FROM tenders WHERE tender_id = ?",
                                  (tender_id,)).fetchone()
            missing = json.loads(tender["missing_fields"] or "[]")
            if field not in missing:
                raise RegistryError("not_missing")
            now = utc_now()
            conn.execute(_COMPLETE_SQL[field],
                         (value, json.dumps([f for f in missing if f != field]), tender_id))
            conn.execute(
                'INSERT INTO change_log (tender_id, field, "old", "new", source, actor_user_id,'
                ' "at", synthetic) VALUES (?, ?, ?, ?, \'manual\', ?, ?, 1)',
                (tender_id, field, tender[field], value, user().user_id, now))
            record_approval(conn, actor=user(), subject_type="field_completion",
                            subject_id=f"{tender_id}:{field}", decision="approved",
                            acting_role=role, tender_id=tender_id, reservations=_reservations())
    except AuthzError as exc:
        return refused(exc)
    except RegistryError as exc:
        return conflict(exc)
    flash(f"اكتمل الحقل في المنافسة {tender_id}، وسُجّل من أكمله.")
    return redirect(url_for("tenders.tender_page", tender_id=tender_id))
