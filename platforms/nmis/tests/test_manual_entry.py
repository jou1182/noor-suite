"""T037: manual entry without a source reference (FR-001, FR-002a, R3).

Synthetic data only. Possible matches = same issuing entity + similar title after simple Arabic
normalisation + closing date within seven days.
"""

from __future__ import annotations

import pytest
from app_fixtures import (
    add_user,
    candidate,
    give_creation_grant,
    post,
    query,
    write_exchange,
)
from noor_registry.registry import normalize_arabic, title_similarity

EXISTING = candidate()  # entity "الجهة المصطنعة ألف", closing 2026-12-01


@pytest.fixture
def existing(nmis_app, client_for):
    """One imported synthetic tender owned (approver) by pm."""
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", EXISTING)
    response = post(client_for("pm"), "/import", filename="cand.json")
    assert response.status_code == 302
    return response.location.rstrip("/").rsplit("/", 1)[-1]


def _manual(client, action="create", **fields):
    data = {"title": EXISTING["title"], "issuing_entity": EXISTING["issuing_entity"],
            "closing_at": "2026-12-05T10:00:00+03:00", "etimad_ref": "", "action": action}
    data.update(fields)
    return post(client, "/tenders/new", **data)


def _count(nmis_app, sql="SELECT COUNT(*) FROM tenders", params=()):
    return query(nmis_app, sql, params)[0][0]


# --- normalisation (R3) ---------------------------------------------------------------------

def test_normalize_removes_diacritics_and_tatweel():
    assert normalize_arabic("مُنَافَسَةٌ") == normalize_arabic("منافسة")
    assert normalize_arabic("منـــافسة") == normalize_arabic("منافسة")


def test_normalize_unifies_alef_ya_and_ta_marbuta():
    assert normalize_arabic("أإآا") == "اااا"
    assert normalize_arabic("مبنى") == normalize_arabic("مبني")
    assert normalize_arabic("مدرسة") == normalize_arabic("مدرسه")


def test_normalize_collapses_spaces():
    assert normalize_arabic("  توريد   معدات\tمختبر ") == "توريد معدات مختبر"


def test_title_similarity_is_symmetric_and_bounded():
    a, b = "توريد معدات مختبر", "توريد مُعدّات المختبر"
    assert title_similarity(a, b) == title_similarity(b, a)
    assert title_similarity(a, a) == 1.0
    assert 0.0 <= title_similarity(a, "صيانة طرق") < title_similarity(a, b)


# --- possible matches and the recorded decision ---------------------------------------------

def test_similar_entry_shows_matches_and_creates_nothing(nmis_app, client_for, existing):
    before = _count(nmis_app)
    title = "تَوريد وتركيب مُعدات مختبر مصطنع للاختبار"  # same title with diacritics
    response = _manual(client_for("pm"), title=title,
                       issuing_entity="الجهه المصطنعة الف")  # spelling variants
    assert response.status_code == 200
    assert existing in response.get_data(as_text=True)
    assert _count(nmis_app) == before
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'") == 0


@pytest.mark.parametrize("fields", [
    {"issuing_entity": "جهة مصطنعة مختلفة"},
    {"title": "صيانة شبكة طرق مصطنعة"},
    {"closing_at": "2026-12-10T10:00:00+03:00"},  # nine days away
], ids=["other-entity", "other-title", "outside-window"])
def test_no_match_creates_directly_and_records_the_decision(nmis_app, client_for, existing,
                                                            fields):
    response = _manual(client_for("pm"), **fields)
    assert response.status_code == 302
    new_id = response.location.rstrip("/").rsplit("/", 1)[-1]
    assert new_id != existing
    row = query(nmis_app, "SELECT * FROM tenders WHERE tender_id = ?", (new_id,))[0]
    assert row["source_name"] is None and row["source_ref"] is None
    assert row["status"] == "candidate"
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'"
                  " AND tender_id = ?", (new_id,)) == 1
    membership = query(nmis_app, "SELECT user_id, role FROM memberships WHERE tender_id = ?",
                       (new_id,))
    assert [(m["user_id"], m["role"]) for m in membership] == [("pm", "approver")]


def test_confirm_new_despite_matches_after_the_shown_check(nmis_app, client_for, existing):
    client = client_for("pm")
    before = _count(nmis_app)
    assert _manual(client, action="check").status_code == 200
    response = _manual(client, confirm_new="1")
    assert response.status_code == 302
    assert _count(nmis_app) == before + 1
    decision = query(nmis_app, "SELECT subject_id FROM approvals"
                     " WHERE subject_type = 'manual_entry'")[0]
    assert existing in decision["subject_id"]  # the shown matches are part of the record
    # The shown check is used up: a second confirmation needs a new check.
    assert _manual(client, confirm_new="1").status_code == 409


def test_direct_confirmation_without_a_shown_check_is_refused(nmis_app, client_for, existing):
    before = _count(nmis_app)
    assert _manual(client_for("pm"), confirm_new="1").status_code == 409
    assert _count(nmis_app) == before


def test_confirmation_with_changed_fields_is_refused(nmis_app, client_for, existing):
    client = client_for("pm")
    before = _count(nmis_app)
    assert _manual(client, action="check").status_code == 200
    response = _manual(client, confirm_new="1", closing_at="2026-12-04T10:00:00+03:00")
    assert response.status_code == 409
    assert _count(nmis_app) == before


def test_confirmation_with_a_changed_match_list_is_refused(nmis_app, client_for, existing):
    client = client_for("pm")
    assert _manual(client, action="check").status_code == 200
    # A second similar tender appears after the check was shown.
    write_exchange(nmis_app, "other.json", candidate(source_ref="SYN-0002"))
    assert post(client, "/import", filename="other.json").status_code == 302
    before = _count(nmis_app)
    assert _manual(client, confirm_new="1").status_code == 409
    assert _count(nmis_app) == before


def test_manual_entry_without_closing_date_is_flagged(nmis_app, client_for, existing):
    response = _manual(client_for("pm"), title="منافسة يدوية مصطنعة أخرى", closing_at="")
    assert response.status_code == 302
    new_id = response.location.rstrip("/").rsplit("/", 1)[-1]
    row = query(nmis_app, "SELECT missing_fields FROM tenders WHERE tender_id = ?", (new_id,))[0]
    assert "closing_at" in row["missing_fields"]


@pytest.mark.parametrize("fields", [
    {"title": ""},
    {"issuing_entity": ""},
    {"closing_at": "غدًا"},
    {"title": "C:\\Users\\someone\\x"},  # scan:allow=path.windows
    {"etimad_ref": "رقم غير صالح"},
], ids=["no-title", "no-entity", "bad-date", "local-path", "bad-etimad-ref"])
def test_invalid_manual_fields_are_rejected(nmis_app, client_for, existing, fields):
    before = _count(nmis_app)
    response = _manual(client_for("pm"), confirm_new="1", **fields)
    assert response.status_code == 400
    assert _count(nmis_app) == before


@pytest.mark.parametrize("user_id", ["mem", "view"])
def test_manual_entry_needs_a_creation_grant(nmis_app, client_for, existing, user_id):
    before = _count(nmis_app)
    for action in ("check", "create"):
        response = _manual(client_for(user_id), action=action, confirm_new="1",
                           title="منافسة يدوية مصطنعة")
        assert response.status_code == 403
    assert _count(nmis_app) == before


def test_manual_entry_refused_before_grant(nmis_app, client_for):
    response = _manual(client_for("pm"), confirm_new="1")
    assert response.status_code == 403
    assert _count(nmis_app) == 1  # only the fixture tender


# --- choosing an existing record ------------------------------------------------------------

def test_choosing_existing_without_membership_is_refused(nmis_app, client_for, existing):
    add_user(nmis_app, "pm2")
    give_creation_grant(nmis_app, "pm2")
    client = client_for("pm2")
    assert _manual(client, action="check").status_code == 200
    before_tenders = _count(nmis_app)
    before_members = _count(nmis_app, "SELECT COUNT(*) FROM memberships")
    response = post(client, "/tenders/new/select", tender_id=existing)
    assert response.status_code == 403
    assert _count(nmis_app) == before_tenders
    assert _count(nmis_app, "SELECT COUNT(*) FROM memberships") == before_members
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'") == 0


def test_choosing_existing_without_a_shown_check_is_refused(nmis_app, client_for, existing):
    response = post(client_for("pm"), "/tenders/new/select", tender_id=existing)
    assert response.status_code == 409
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'") == 0


def test_choosing_after_the_match_list_changed_is_refused(nmis_app, client_for, existing):
    client = client_for("pm")
    assert _manual(client, action="check").status_code == 200
    write_exchange(nmis_app, "other.json", candidate(source_ref="SYN-0002"))
    assert post(client, "/import", filename="other.json").status_code == 302
    response = post(client, "/tenders/new/select", tender_id=existing)
    assert response.status_code == 409
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'") == 0


def test_choosing_a_tender_that_was_not_shown_is_refused(nmis_app, client_for, existing):
    client = client_for("pm")
    assert _manual(client, action="check").status_code == 200
    response = post(client, "/tenders/new/select", tender_id="NT-2026-0001")  # not a match
    assert response.status_code == 409
    assert _count(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'manual_entry'") == 0


def test_choosing_existing_with_approver_records_the_decision(nmis_app, client_for, existing):
    client = client_for("pm")
    assert _manual(client, action="check").status_code == 200
    before_tenders = _count(nmis_app)
    before_members = _count(nmis_app, "SELECT COUNT(*) FROM memberships")
    response = post(client, "/tenders/new/select", tender_id=existing)
    assert response.status_code == 302
    assert response.location.endswith(f"/tenders/{existing}")
    assert _count(nmis_app) == before_tenders
    assert _count(nmis_app, "SELECT COUNT(*) FROM memberships") == before_members
    decision = query(nmis_app, "SELECT * FROM approvals WHERE subject_type = 'manual_entry'")
    assert len(decision) == 1
    assert decision[0]["tender_id"] == existing and decision[0]["actor_user_id"] == "pm"


def test_choosing_unknown_tender_is_refused(nmis_app, client_for, existing):
    client = client_for("pm")
    assert _manual(client, action="check").status_code == 200
    response = post(client, "/tenders/new/select", tender_id="NT-2026-0999")
    assert response.status_code == 409  # never shown, so never selectable
