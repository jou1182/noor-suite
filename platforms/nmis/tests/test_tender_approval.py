"""T036: accepting or rejecting a candidate tender (Q3, Q4, FR-006, FR-007, first edge case).

Synthetic data only.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from app_fixtures import (
    candidate,
    give_creation_grant,
    give_membership,
    post,
    query,
    write_exchange,
)

TEMPLATE = Path(__file__).resolve().parents[1] / "noor_registry" / "task_template.json"


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
def imported(nmis_app, client_for):
    """Import one synthetic candidate as pm; return a factory for more."""
    give_creation_grant(nmis_app, "pm")

    def make(**overrides):
        write_exchange(nmis_app, "cand.json", candidate(**overrides))
        response = post(client_for("pm"), "/import", filename="cand.json")
        assert response.status_code == 302
        return response.location.rstrip("/").rsplit("/", 1)[-1]

    return make


def _state(nmis_app, tender_id):
    status = query(nmis_app, "SELECT status FROM tenders WHERE tender_id = ?",
                   (tender_id,))[0]["status"]
    tasks = query(nmis_app, "SELECT COUNT(*) FROM tasks WHERE tender_id = ?",
                  (tender_id,))[0][0]
    return status, tasks


def test_template_tasks_have_an_owner_role_and_a_due_offset():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert template["template_id"]
    assert template["tasks"]
    for task in template["tasks"]:
        assert task["title"] and task["owner_role"] in {"approver", "member"}
        assert isinstance(task["due_offset_days"], int)


@pytest.mark.parametrize("user_id", ["view", "mem"])
def test_users_without_approver_cannot_accept(nmis_app, client_for, imported, user_id):
    tender_id = imported()
    if user_id == "mem":
        give_membership(nmis_app, "mem", tender_id, "member")
    response = post(client_for(user_id), f"/tenders/{tender_id}/accept", decision="approved")
    assert response.status_code == 403
    assert _state(nmis_app, tender_id) == ("candidate", 0)
    assert query(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'tender'")[0][0] == 0


def test_approver_accepts_and_template_tasks_are_created(nmis_app, client_for, imported):
    tender_id = imported()
    response = post(client_for("pm"), f"/tenders/{tender_id}/accept", decision="approved")
    assert response.status_code == 302

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert _state(nmis_app, tender_id) == ("accepted", len(template["tasks"]))
    closing = _parse(candidate()["closing_at"])
    for task in query(nmis_app, "SELECT * FROM tasks WHERE tender_id = ?", (tender_id,)):
        assert task["owner_user_id"] and task["owner_role"]
        assert task["due_at"] and _parse(task["due_at"]) <= closing
        assert task["origin"].startswith("template:")
        assert task["status"] == "open"

    decision = query(nmis_app, "SELECT * FROM approvals WHERE subject_type = 'tender'"
                     " AND tender_id = ?", (tender_id,))
    assert len(decision) == 1
    assert decision[0]["actor_user_id"] == "pm"
    assert decision[0]["acting_role"] == "approver"
    assert decision[0]["decision"] == "approved"


def _roles(nmis_app, user_id, tender_id):
    return {r["role"] for r in query(
        nmis_app, "SELECT role FROM memberships WHERE user_id = ? AND tender_id = ?",
        (user_id, tender_id))}


def test_task_owner_role_matches_the_owner_permissions(nmis_app, client_for, imported):
    """No member on the tender: member tasks fall back to the approver, visibly."""
    tender_id = imported()
    assert post(client_for("pm"), f"/tenders/{tender_id}/accept",
                decision="approved").status_code == 302
    template = {t["key"]: t for t in json.loads(TEMPLATE.read_text(encoding="utf-8"))["tasks"]}
    for task in query(nmis_app, "SELECT * FROM tasks WHERE tender_id = ?", (tender_id,)):
        assert task["owner_role"] in _roles(nmis_app, task["owner_user_id"], tender_id)
        key = task["origin"].split(":")[2]
        fallback = template[key]["owner_role"] != task["owner_role"]
        assert fallback == task["origin"].endswith(":fallback"), task["origin"]
    page = client_for("pm").get(f"/tenders/{tender_id}").get_data(as_text=True)
    assert "إسناد احتياطي" in page


def test_member_tasks_go_to_a_member_when_there_is_one(nmis_app, client_for, imported):
    tender_id = imported()
    give_membership(nmis_app, "mem", tender_id, "member")
    assert post(client_for("pm"), f"/tenders/{tender_id}/accept",
                decision="approved").status_code == 302
    rows = query(nmis_app, "SELECT owner_user_id, owner_role, origin FROM tasks"
                 " WHERE tender_id = ?", (tender_id,))
    assert {(r["owner_user_id"], r["owner_role"]) for r in rows} == {
        ("pm", "approver"), ("mem", "member")}
    assert not any(r["origin"].endswith(":fallback") for r in rows)


def test_accepting_twice_does_not_duplicate_tasks(nmis_app, client_for, imported):
    tender_id = imported()
    client = client_for("pm")
    assert post(client, f"/tenders/{tender_id}/accept", decision="approved").status_code == 302
    _, tasks = _state(nmis_app, tender_id)
    assert post(client, f"/tenders/{tender_id}/accept", decision="approved").status_code == 409
    assert _state(nmis_app, tender_id) == ("accepted", tasks)


def test_reservation_needs_a_text(nmis_app, client_for, imported):
    tender_id = imported()
    client = client_for("pm")
    response = post(client, f"/tenders/{tender_id}/accept", decision="approved_with_reservation")
    assert response.status_code == 400
    assert _state(nmis_app, tender_id) == ("candidate", 0)
    response = post(client, f"/tenders/{tender_id}/accept",
                    decision="approved_with_reservation", reservations="تحفظ اختباري")
    assert response.status_code == 302
    row = query(nmis_app, "SELECT reservations FROM approvals WHERE subject_type = 'tender'")[0]
    assert row["reservations"] == "تحفظ اختباري"


def test_unknown_decision_is_refused(nmis_app, client_for, imported):
    tender_id = imported()
    response = post(client_for("pm"), f"/tenders/{tender_id}/accept", decision="rejected")
    assert response.status_code == 400
    assert _state(nmis_app, tender_id) == ("candidate", 0)


def test_reject_records_a_decision_and_creates_no_tasks(nmis_app, client_for, imported):
    tender_id = imported()
    client = client_for("pm")
    assert post(client, f"/tenders/{tender_id}/reject",
                reservations="سبب اختباري").status_code == 302
    assert _state(nmis_app, tender_id) == ("rejected", 0)
    row = query(nmis_app, "SELECT * FROM approvals WHERE subject_type = 'tender'")[0]
    assert row["decision"] == "rejected"
    assert post(client, f"/tenders/{tender_id}/accept", decision="approved").status_code == 409


def test_missing_closing_date_blocks_acceptance_until_completed(nmis_app, client_for, imported):
    tender_id = imported(closing_at=None)
    client = client_for("pm")
    assert post(client, f"/tenders/{tender_id}/accept", decision="approved").status_code == 409
    assert _state(nmis_app, tender_id) == ("candidate", 0)

    # Completing the field needs approver on this tender and a valid date-time with a zone.
    assert post(client_for("mem"), f"/tenders/{tender_id}/complete-field",
                field="closing_at", value="2026-12-01T10:00:00+03:00").status_code == 403
    assert post(client, f"/tenders/{tender_id}/complete-field",
                field="closing_at", value="2026-12-01").status_code == 400
    assert post(client, f"/tenders/{tender_id}/complete-field",
                field="title", value="x").status_code == 400

    assert post(client, f"/tenders/{tender_id}/complete-field",
                field="closing_at", value="2026-12-01T10:00:00+03:00").status_code == 302
    row = query(nmis_app, "SELECT closing_at, missing_fields FROM tenders WHERE tender_id = ?",
                (tender_id,))[0]
    assert row["closing_at"] == "2026-12-01T10:00:00+03:00"
    assert row["missing_fields"] == "[]"
    completion = query(nmis_app, "SELECT * FROM approvals WHERE subject_type = 'field_completion'")
    assert len(completion) == 1 and completion[0]["actor_user_id"] == "pm"
    log = query(nmis_app, "SELECT * FROM change_log WHERE tender_id = ? AND source = 'manual'",
                (tender_id,))
    assert [(r["field"], r["new"]) for r in log] == [("closing_at", "2026-12-01T10:00:00+03:00")]

    # A field that is not missing cannot be "completed" again.
    assert post(client, f"/tenders/{tender_id}/complete-field",
                field="closing_at", value="2026-12-02T10:00:00+03:00").status_code == 409
    assert post(client, f"/tenders/{tender_id}/accept", decision="approved").status_code == 302
    assert _state(nmis_app, tender_id)[0] == "accepted"


def test_unknown_tender_is_not_found(client_for, nmis_app):
    give_creation_grant(nmis_app, "pm")
    response = post(client_for("pm"), "/tenders/NT-2026-0999/accept", decision="approved")
    assert response.status_code in (403, 404)


def test_tender_page_shows_decision_forms_only_with_permission(nmis_app, client_for, imported):
    tender_id = imported()
    assert f"/tenders/{tender_id}/accept" in client_for("pm").get(
        f"/tenders/{tender_id}").get_data(as_text=True)
    for user_id in ("mem", "view"):
        page = client_for(user_id).get(f"/tenders/{tender_id}")
        assert page.status_code == 200
        assert f"/tenders/{tender_id}/accept" not in page.get_data(as_text=True)
