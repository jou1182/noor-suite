"""Schema and connection tests for the NMIS registry database (T019)."""

from __future__ import annotations

import sqlite3

import pytest
from noor_registry.db import (
    DB_FILENAME,
    SCHEMA_VERSION,
    DbError,
    next_tender_id,
    open_db,
)

NOW = "2026-01-01T00:00:00+00:00"


@pytest.fixture()
def conn(tmp_path):
    connection = open_db(tmp_path / "data", create=True)
    yield connection
    connection.close()


def _add_user(conn, user_id="pm", kind="member", enabled=1, operator_label=None):
    conn.execute(
        "INSERT INTO users (user_id, display_name, kind, password_hash, enabled,"
        " operator_label) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, f"user {user_id}", kind, "synthetic-hash", enabled, operator_label),
    )
    conn.commit()


def _add_tender(
    conn,
    tender_id="NT-2026-0001",
    created_by="pm",
    source_name=None,
    source_ref=None,
):
    conn.execute(
        "INSERT INTO tenders (tender_id, title, issuing_entity, source_name,"
        " source_ref, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            tender_id,
            f"tender {tender_id}",
            "synthetic entity",
            source_name,
            source_ref,
            created_by,
            NOW,
        ),
    )
    conn.commit()


def _add_approval(
    conn,
    approval_id="AP-0000000000000001",
    tender_id=None,
    subject_type="tender",
    subject_id="NT-2026-0001",
    decision="approved",
    reservations=None,
    actor_user_id="pm",
):
    conn.execute(
        "INSERT INTO approvals (approval_id, tender_id, subject_type, subject_id,"
        " acting_role, decision, reservations, actor_user_id, decided_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            approval_id,
            tender_id,
            subject_type,
            subject_id,
            "approver",
            decision,
            reservations,
            actor_user_id,
            NOW,
        ),
    )
    conn.commit()
    return approval_id


# --------------------------------------------------------------------------
# opening / creating
# --------------------------------------------------------------------------


def test_create_database_writes_file(tmp_path):
    data_dir = tmp_path / "data"
    conn = open_db(data_dir, create=True)
    try:
        assert (data_dir / DB_FILENAME).exists()
        row = conn.execute("SELECT version FROM noor_schema").fetchone()
        assert row["version"] == SCHEMA_VERSION
    finally:
        conn.close()


def test_create_twice_is_refused(tmp_path):
    data_dir = tmp_path / "data"
    conn = open_db(data_dir, create=True)
    conn.close()
    with pytest.raises(DbError):
        open_db(data_dir, create=True)


def test_open_without_create_on_missing_file_is_refused(tmp_path):
    with pytest.raises(DbError):
        open_db(tmp_path / "missing")


def test_open_existing_database_works(tmp_path):
    data_dir = tmp_path / "data"
    conn = open_db(data_dir, create=True)
    conn.close()
    reopened = open_db(data_dir)
    reopened.close()


def test_open_rejects_uninitialised_database(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(data_dir / DB_FILENAME))
    raw.close()
    with pytest.raises(DbError):
        open_db(data_dir)


def test_open_rejects_other_schema_version(tmp_path):
    data_dir = tmp_path / "data"
    conn = open_db(data_dir, create=True)
    conn.execute("UPDATE noor_schema SET version = ?", (SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()
    with pytest.raises(DbError):
        open_db(data_dir)


def test_connection_is_configured(conn):
    assert conn.row_factory is sqlite3.Row
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


# --------------------------------------------------------------------------
# CHECK constraints
# --------------------------------------------------------------------------


def test_unknown_user_kind_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, display_name, kind, password_hash, enabled)"
            " VALUES ('x1', 'x', 'superuser', 'h', 1)",
        )
    conn.rollback()


def test_unknown_membership_role_is_rejected(conn):
    _add_user(conn)
    _add_tender(conn)
    _add_approval(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO memberships (user_id, tender_id, role, owner_authorization_ref,"
            " configured_by_user_id, granted_at, grant_approval_id)"
            " VALUES ('pm', 'NT-2026-0001', 'owner', 'REF', 'pm', ?, ?)",
            (NOW, "AP-0000000000000001"),
        )
    conn.rollback()


def test_unknown_tender_status_is_rejected(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tenders (tender_id, title, issuing_entity, status, created_by,"
            " created_at) VALUES ('NT-2026-0009', 't', 'e', 'pending', 'pm', ?)",
            (NOW,),
        )
    conn.rollback()


def test_unknown_approval_subject_type_is_rejected(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _add_approval(conn, approval_id="AP-2", subject_type="wish")
    conn.rollback()


def test_unknown_approval_decision_is_rejected(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _add_approval(conn, approval_id="AP-3", decision="maybe")
    conn.rollback()


def test_approved_with_reservation_requires_reservations(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _add_approval(
            conn,
            approval_id="AP-4",
            decision="approved_with_reservation",
            reservations=None,
        )
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        _add_approval(
            conn,
            approval_id="AP-5",
            decision="approved_with_reservation",
            reservations="   ",
        )
    conn.rollback()


def test_synthetic_zero_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, display_name, kind, password_hash, enabled,"
            " synthetic) VALUES ('pm', 'p', 'member', 'h', 1, 0)",
        )
    conn.rollback()


def test_shared_user_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (user_id, display_name, kind, shared, password_hash,"
            " enabled) VALUES ('pm', 'p', 'member', 1, 'h', 1)",
        )
    conn.rollback()


def test_malformed_tender_id_is_rejected(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _add_tender(conn, tender_id="TENDER-2026-0001")
    conn.rollback()


def test_unknown_creation_capability_is_rejected(conn):
    _add_user(conn)
    _add_approval(conn, approval_id="AP-6", subject_type="permission_grant")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO creation_grants (user_id, capability, owner_authorization_ref,"
            " configured_by_user_id, granted_at, grant_approval_id)"
            " VALUES ('pm', 'delete_tender', 'REF', 'pm', ?, 'AP-6')",
            (NOW,),
        )
    conn.rollback()


def test_half_source_pair_is_rejected(conn):
    _add_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _add_tender(conn, tender_id="NT-2026-0002", source_name="radar", source_ref=None)
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        _add_tender(conn, tender_id="NT-2026-0003", source_name=None, source_ref="R-1")
    conn.rollback()


def test_unknown_finding_result_is_rejected(conn):
    _add_user(conn)
    _add_tender(conn)
    conn.execute(
        "INSERT INTO review_reports (report_id, tender_id, proposal_version,"
        " proposal_sha256, rfp_sha256, checks_run, limitations)"
        " VALUES ('R-1', 'NT-2026-0001', 1, ?, ?, '[]', '[]')",
        ("a" * 64, "b" * 64),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO findings (finding_key, report_id, criterion_id, result,"
            " sources, message) VALUES ('F-1', 'R-1', 'C-1', 'unknown', '[]', 'm')",
        )
    conn.rollback()


# --------------------------------------------------------------------------
# UNIQUE / immutability / triggers
# --------------------------------------------------------------------------


def test_source_pair_is_unique(conn):
    _add_user(conn)
    _add_tender(conn, tender_id="NT-2026-0001", source_name="radar", source_ref="R-1")
    with pytest.raises(sqlite3.IntegrityError):
        _add_tender(conn, tender_id="NT-2026-0002", source_name="radar", source_ref="R-1")
    conn.rollback()


def test_approvals_cannot_be_updated(conn):
    _add_user(conn)
    _add_approval(conn, approval_id="AP-7")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        conn.execute(
            "UPDATE approvals SET decision = 'rejected' WHERE approval_id = 'AP-7'"
        )
    assert "immutable" in str(excinfo.value)
    conn.rollback()


def test_approvals_cannot_be_deleted(conn):
    _add_user(conn)
    _add_approval(conn, approval_id="AP-8")
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        conn.execute("DELETE FROM approvals WHERE approval_id = 'AP-8'")
    assert "immutable" in str(excinfo.value)
    conn.rollback()


def test_review_approver_cannot_be_created_enabled(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _add_user(
            conn,
            user_id="ra",
            kind="review_approver",
            enabled=1,
            operator_label="operator",
        )
    conn.rollback()


def test_review_approver_cannot_be_enabled_without_operator_label(conn):
    _add_user(conn, user_id="ra", kind="review_approver", enabled=0, operator_label=None)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE users SET enabled = 1 WHERE user_id = 'ra'")
    conn.rollback()


def test_review_approver_can_be_enabled_with_operator_label(conn):
    _add_user(conn, user_id="ra", kind="review_approver", enabled=0, operator_label="op")
    conn.execute("UPDATE users SET enabled = 1 WHERE user_id = 'ra'")
    conn.commit()
    row = conn.execute("SELECT enabled FROM users WHERE user_id = 'ra'").fetchone()
    assert row["enabled"] == 1


def test_tender_id_is_immutable(conn):
    _add_user(conn)
    _add_tender(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE tenders SET tender_id = 'NT-2026-0002' WHERE tender_id = 'NT-2026-0001'"
        )
    conn.rollback()


# --------------------------------------------------------------------------
# tender counter
# --------------------------------------------------------------------------


def test_next_tender_id_counts_up(conn):
    with conn:
        first = next_tender_id(conn, 2026)
        second = next_tender_id(conn, 2026)
    assert first == "NT-2026-0001"
    assert second == "NT-2026-0002"
    row = conn.execute(
        "SELECT last FROM tender_counter WHERE year = 2026"
    ).fetchone()
    assert row["last"] == 2


def test_next_tender_id_is_per_year(conn):
    with conn:
        assert next_tender_id(conn, 2026) == "NT-2026-0001"
        assert next_tender_id(conn, 2027) == "NT-2027-0001"


def test_next_tender_id_refuses_to_overflow(conn):
    conn.execute(
        "INSERT INTO tender_counter (year, last, synthetic) VALUES (2030, 9999, 1)"
    )
    conn.commit()
    with pytest.raises(DbError):
        next_tender_id(conn, 2030)
    conn.rollback()
