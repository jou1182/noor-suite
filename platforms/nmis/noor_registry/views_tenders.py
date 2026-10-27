"""Tender list and tender page (T044, FR-005, RAD-07). Read only."""

from __future__ import annotations

import json

from flask import Blueprint, render_template

from .authz import AuthzError, authorize
from .registry import ACCEPT_REQUIRED_FIELDS
from .security import login_required
from .views_common import (
    DECISION_LABELS,
    FIELD_LABELS,
    STATUS_LABELS,
    check_tender_id,
    data_age,
    db,
    refused,
    user,
)

bp = Blueprint("tenders", __name__)


def _missing(row) -> list[str]:
    try:
        fields = json.loads(row["missing_fields"] or "[]")
    except ValueError:
        # A stored value we cannot read must not hide a missing field.
        return list(ACCEPT_REQUIRED_FIELDS)
    return [f for f in fields if isinstance(f, str)]


def _source(row) -> dict:
    """Where the record comes from and how old its data is (never shown as live)."""
    if row["source_name"]:
        return {"label": f"{row['source_name']} (مرجع {row['source_ref']})",
                "updated_at": row["source_updated_at"],
                "age": data_age(row["source_updated_at"])}
    return {"label": "إدخال يدوي في NMIS", "updated_at": row["created_at"],
            "age": data_age(row["created_at"])}


def _allowed(conn, tender_id: str, action: str) -> bool:
    try:
        authorize(conn, user(), tender_id, action)
    except AuthzError:
        return False
    return True


@bp.get("/tenders")
@login_required
def list_tenders():
    rows = db().execute("SELECT * FROM tenders ORDER BY created_at DESC, tender_id DESC").fetchall()
    tenders = [{"row": row, "status": STATUS_LABELS.get(row["status"], row["status"]),
                "missing": [FIELD_LABELS.get(f, f) for f in _missing(row)],
                "source": _source(row)} for row in rows]
    return render_template("tenders/list.html", tenders=tenders)


@bp.get("/tenders/<tender_id>")
@login_required
def tender_page(tender_id):
    check_tender_id(tender_id)
    conn = db()
    try:
        authorize(conn, user(), tender_id, "view")
    except AuthzError as exc:
        return refused(exc)
    row = conn.execute("SELECT * FROM tenders WHERE tender_id = ?", (tender_id,)).fetchone()
    missing = _missing(row)
    candidate = row["status"] == "candidate"
    context = {
        "tender": row,
        "status": STATUS_LABELS.get(row["status"], row["status"]),
        "missing": [(f, FIELD_LABELS.get(f, f)) for f in missing],
        "source": _source(row),
        "can_decide": candidate and _allowed(conn, tender_id, "accept_tender"),
        "can_complete": bool(missing) and _allowed(conn, tender_id, "field_completion"),
        "tasks": conn.execute(
            "SELECT t.*, u.display_name AS owner_name FROM tasks t"
            " LEFT JOIN users u ON u.user_id = t.owner_user_id"
            " WHERE t.tender_id = ? ORDER BY t.due_at, t.task_id", (tender_id,)).fetchall(),
        "versions": conn.execute(
            "SELECT * FROM proposal_versions WHERE tender_id = ? ORDER BY version",
            (tender_id,)).fetchall(),
        "reports": conn.execute(
            "SELECT * FROM review_reports WHERE tender_id = ? ORDER BY report_id",
            (tender_id,)).fetchall(),
        "gaps": conn.execute(
            "SELECT * FROM gap_proposals WHERE tender_id = ? ORDER BY finding_key",
            (tender_id,)).fetchall(),
        "decisions": conn.execute(
            "SELECT a.*, u.display_name AS actor_name FROM approvals a"
            " JOIN users u ON u.user_id = a.actor_user_id"
            " WHERE a.tender_id = ? ORDER BY a.decided_at, a.approval_id",
            (tender_id,)).fetchall(),
        "changes": conn.execute(
            "SELECT * FROM change_log WHERE tender_id = ? ORDER BY id", (tender_id,)).fetchall(),
        "decision_labels": DECISION_LABELS,
    }
    return render_template("tenders/page.html", **context)
