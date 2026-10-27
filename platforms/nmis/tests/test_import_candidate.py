"""T035: importing noor.tender-candidate/v1 into NMIS (Q1a, Q1, Q2, SC-005, FR-002a).

Synthetic data only. The exchange file is read through views_import.read_exchange_file, so the
tests can prove that a refused caller never makes NMIS open the file.
"""

from __future__ import annotations

import json
import os
import re

import pytest
from app_fixtures import (
    add_user,
    candidate,
    give_creation_grant,
    post,
    query,
    write_exchange,
)

ID_RE = re.compile(r"^NT-\d{4}-\d{4}$")


@pytest.fixture
def opened(monkeypatch):
    """Record every exchange file NMIS opens."""
    import noor_registry.views_import as views_import

    calls = []
    real = views_import.read_exchange_file

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(views_import, "read_exchange_file", spy)
    return calls


def _tender_count(nmis_app):
    return query(nmis_app, "SELECT COUNT(*) FROM tenders")[0][0]


def _import(client, name="cand.json"):
    return post(client, "/import", filename=name)


def _imported_id(response):
    assert response.status_code == 302, response.status_code
    tender_id = response.location.rstrip("/").rsplit("/", 1)[-1]
    assert ID_RE.match(tender_id), tender_id
    return tender_id


@pytest.mark.parametrize("user_id", ["pm", "mem"])
def test_import_refused_without_creation_grant_before_opening_the_file(
        nmis_app, client_for, opened, user_id):
    write_exchange(nmis_app, "cand.json", candidate())
    before = _tender_count(nmis_app)
    response = _import(client_for(user_id))
    assert response.status_code == 403
    assert opened == [], "the exchange file was opened before authorization"
    assert _tender_count(nmis_app) == before
    assert query(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'import'")[0][0] == 0


def test_viewer_import_refused_before_opening_the_file(nmis_app, client_for, opened):
    write_exchange(nmis_app, "cand.json", candidate())
    response = _import(client_for("view"))
    assert response.status_code == 403
    assert opened == []


def test_import_creates_candidate_with_creator_approver(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    client = client_for("pm")
    tender_id = _imported_id(_import(client))

    row = query(nmis_app, "SELECT * FROM tenders WHERE tender_id = ?", (tender_id,))[0]
    assert row["status"] == "candidate"
    assert (row["source_name"], row["source_ref"]) == ("radar", "SYN-0001")
    assert row["created_by"] == "pm"
    assert row["missing_fields"] == "[]"

    membership = query(nmis_app, "SELECT * FROM memberships WHERE tender_id = ?", (tender_id,))
    assert [(m["user_id"], m["role"]) for m in membership] == [("pm", "approver")]
    grant = query(nmis_app, "SELECT * FROM approvals WHERE approval_id = ?",
                  (membership[0]["grant_approval_id"],))[0]
    assert grant["subject_type"] == "permission_grant"
    assert grant["tender_id"] == tender_id
    imports = query(nmis_app, "SELECT * FROM approvals WHERE subject_type = 'import'"
                    " AND tender_id = ?", (tender_id,))
    assert len(imports) == 1 and imports[0]["actor_user_id"] == "pm"
    # Importing never accepts the tender: no tender decision, no tasks.
    assert query(nmis_app, "SELECT COUNT(*) FROM approvals WHERE subject_type = 'tender'")[0][0] == 0
    assert query(nmis_app, "SELECT COUNT(*) FROM tasks")[0][0] == 0

    page = client.get(f"/tenders/{tender_id}").get_data(as_text=True)
    assert tender_id in page
    assert "مرشَّحة" in page
    assert "radar" in page  # the source is shown with the data age (RAD-07)
    assert "عمر البيانات" in page


def test_same_candidate_twice_keeps_the_id_and_logs_changes(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    client = client_for("pm")
    write_exchange(nmis_app, "cand.json", candidate())
    first = _imported_id(_import(client))
    count = _tender_count(nmis_app)

    changed = candidate(title="عنوان معدّل لمنافسة مصطنعة", issuing_entity="جهة أخرى مصطنعة",
                        source_updated_at="2026-10-22T08:00:00+03:00", etimad_ref=None)
    write_exchange(nmis_app, "cand.json", changed)
    second = _imported_id(_import(client))

    assert second == first
    assert _tender_count(nmis_app) == count
    row = query(nmis_app, "SELECT * FROM tenders WHERE tender_id = ?", (first,))[0]
    assert row["title"] == "عنوان معدّل لمنافسة مصطنعة"
    assert row["issuing_entity"] == "الجهة المصطنعة ألف"  # not an updatable field
    assert row["source_updated_at"] == "2026-10-22T08:00:00+03:00"
    logged = {r["field"] for r in query(
        nmis_app, "SELECT field FROM change_log WHERE tender_id = ? AND source = 'radar_import'",
        (first,))}
    assert logged == {"title", "source_updated_at"}
    assert query(nmis_app, "SELECT COUNT(*) FROM memberships WHERE tender_id = ?",
                 (first,))[0][0] == 1  # no second approver grant


def test_duplicate_updates_closing_date_but_null_never_erases_it(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    client = client_for("pm")
    write_exchange(nmis_app, "cand.json", candidate(closing_at=None))
    tender_id = _imported_id(_import(client))

    write_exchange(nmis_app, "cand.json", candidate(closing_at="2026-12-03T10:00:00+03:00"))
    assert _imported_id(_import(client)) == tender_id
    row = query(nmis_app, "SELECT closing_at, missing_fields FROM tenders WHERE tender_id = ?",
                (tender_id,))[0]
    assert row["closing_at"] == "2026-12-03T10:00:00+03:00"
    assert row["missing_fields"] == "[]"
    assert [r["field"] for r in query(
        nmis_app, "SELECT field FROM change_log WHERE tender_id = ?", (tender_id,))] == [
        "closing_at"]

    write_exchange(nmis_app, "cand.json", candidate(closing_at=None))
    assert _imported_id(_import(client)) == tender_id
    row = query(nmis_app, "SELECT closing_at FROM tenders WHERE tender_id = ?", (tender_id,))[0]
    assert row["closing_at"] == "2026-12-03T10:00:00+03:00"


def _swap_after_check(monkeypatch, action):
    """Run ``action(path)`` right after the name check and before the file is opened."""
    import noor_registry.views_import as views_import

    real = views_import.resolve_exchange_name

    def checked_then_swapped(exchange_dir, name):
        path = real(exchange_dir, name)
        action(path)
        return path

    monkeypatch.setattr(views_import, "resolve_exchange_name", checked_then_swapped)


def test_file_grown_between_check_and_open_is_refused(nmis_app, client_for, monkeypatch):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    _swap_after_check(monkeypatch, lambda path: path.write_bytes(b" " * (1_048_576 + 10)))
    before = _tender_count(nmis_app)
    assert _import(client_for("pm")).status_code == 400
    assert _tender_count(nmis_app) == before


def test_file_swapped_for_a_link_between_check_and_open_is_refused(
        nmis_app, client_for, monkeypatch, tmp_path):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(candidate(source_ref="SYN-OUT")), encoding="utf-8")
    probe = tmp_path / "probe-link"
    try:
        os.symlink(outside, probe)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available on this machine")

    def swap(path):
        path.unlink()
        os.symlink(outside, path)

    _swap_after_check(monkeypatch, swap)
    before = _tender_count(nmis_app)
    assert _import(client_for("pm")).status_code == 400
    assert _tender_count(nmis_app) == before


def test_reimport_by_another_creator_without_membership_is_refused(nmis_app, client_for):
    add_user(nmis_app, "pm2")
    give_creation_grant(nmis_app, "pm")
    give_creation_grant(nmis_app, "pm2")
    write_exchange(nmis_app, "cand.json", candidate())
    tender_id = _imported_id(_import(client_for("pm")))

    write_exchange(nmis_app, "cand.json", candidate(title="محاولة تعديل بلا صلاحية"))
    response = _import(client_for("pm2"))
    assert response.status_code == 403
    row = query(nmis_app, "SELECT title FROM tenders WHERE tender_id = ?", (tender_id,))[0]
    assert row["title"] == candidate()["title"]
    assert query(nmis_app, "SELECT COUNT(*) FROM change_log")[0][0] == 0


def test_second_synthetic_tender_gets_its_own_id_and_grant(nmis_app, client_for):
    add_user(nmis_app, "pm2")
    give_creation_grant(nmis_app, "pm")
    give_creation_grant(nmis_app, "pm2")
    write_exchange(nmis_app, "a.json", candidate())
    write_exchange(nmis_app, "b.json", candidate(source_ref="SYN-0002"))
    first = _imported_id(_import(client_for("pm"), "a.json"))
    second = _imported_id(_import(client_for("pm2"), "b.json"))

    assert first != second
    rows = query(nmis_app, "SELECT user_id, tender_id FROM memberships ORDER BY tender_id")
    assert [(r["user_id"], r["tender_id"]) for r in rows] == [("pm", first), ("pm2", second)]


@pytest.mark.parametrize("doc", [
    candidate(extra_field="x"),
    candidate(synthetic=False),
    candidate(schema="noor.tender/v2"),
    candidate(title="C:\\Users\\someone\\file.docx"),  # scan:allow=path.windows
    candidate(source_ref="sid=abc"),
], ids=["extra-field", "not-synthetic", "unknown-schema", "local-path", "session-like"])
def test_invalid_contract_is_rejected_without_changes(nmis_app, client_for, doc):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", doc)
    before = _tender_count(nmis_app)
    response = _import(client_for("pm"))
    assert response.status_code == 400
    assert _tender_count(nmis_app) == before


def test_non_utf8_and_oversized_files_are_rejected(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    client = client_for("pm")
    write_exchange(nmis_app, "latin.json", "{}".encode("utf-16"))
    assert _import(client, "latin.json").status_code == 400
    write_exchange(nmis_app, "big.json", b" " * (1_048_576 + 1))
    assert _import(client, "big.json").status_code == 400


@pytest.mark.parametrize("name", [
    "../cand.json", "..\\cand.json", "sub/cand.json", "C:cand.json", "cand.txt", "", "CON.json",
])
def test_bad_file_names_are_refused_before_opening(nmis_app, client_for, opened, name):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    response = _import(client_for("pm"), name)
    assert response.status_code == 400
    assert opened == []


def test_absolute_path_is_refused(nmis_app, client_for, opened):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    absolute = str(nmis_app.config.exchange_dir / "cand.json")
    assert _import(client_for("pm"), absolute).status_code == 400
    assert opened == []


def test_symlink_leaving_the_exchange_dir_is_refused(nmis_app, client_for, opened, tmp_path):
    give_creation_grant(nmis_app, "pm")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = nmis_app.config.exchange_dir / "link.json"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available on this machine")
    assert _import(client_for("pm"), "link.json").status_code == 400
    assert opened == []


def test_missing_file_is_a_clear_error(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    assert _import(client_for("pm"), "absent.json").status_code == 400


def test_missing_closing_date_is_flagged(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate(closing_at=None))
    client = client_for("pm")
    tender_id = _imported_id(_import(client))
    row = query(nmis_app, "SELECT missing_fields, status FROM tenders WHERE tender_id = ?",
                (tender_id,))[0]
    assert row["status"] == "candidate"
    assert "closing_at" in row["missing_fields"]
    page = client.get(f"/tenders/{tender_id}").get_data(as_text=True)
    assert "حقول ناقصة" in page


def test_import_page_lists_exchange_files_by_name_only(nmis_app, client_for):
    give_creation_grant(nmis_app, "pm")
    write_exchange(nmis_app, "cand.json", candidate())
    page = client_for("pm").get("/import").get_data(as_text=True)
    assert "cand.json" in page
    assert str(nmis_app.config.exchange_dir) not in page
