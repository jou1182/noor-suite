"""SQLite storage for the local NMIS / ``noor_registry`` demo application.

Everything in here is synthetic demo data.  The database lives inside the
configured ``data_dir`` as ``noor.sqlite3``.

Design rules that matter for the rest of the package:

* A database is created **once**.  ``open_db(..., create=True)`` refuses to
  touch an existing file, so a live database is never migrated in place.
* The schema is versioned through the ``noor_schema`` table.  A database whose
  version does not match :data:`SCHEMA_VERSION` is rejected.
* Every table carries a ``synthetic`` guard column (``CHECK (synthetic = 1)``)
  so that real data can never be mixed into the demo database.
* No network access and no shell usage anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "DB_FILENAME",
    "SCHEMA_VERSION",
    "SCHEMA_SQL",
    "DbError",
    "next_tender_id",
    "open_db",
    "utc_now",
]

DB_FILENAME = "noor.sqlite3"
SCHEMA_VERSION = 2


class DbError(RuntimeError):
    """Raised when a database cannot be opened, created or used."""


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``+00:00`` offset."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA_SQL = """
CREATE TABLE users (
    user_id TEXT PRIMARY KEY
        CHECK (user_id GLOB '[a-z0-9_]*' AND length(user_id) BETWEEN 2 AND 40),
    display_name TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('proposal_manager', 'review_approver', 'member', 'viewer')),
    shared INTEGER NOT NULL DEFAULT 0 CHECK (shared = 0),
    password_hash TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    operator_label TEXT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    CHECK (kind = 'review_approver' OR operator_label IS NULL)
);

CREATE TRIGGER users_review_approver_created_disabled
BEFORE INSERT ON users
WHEN NEW.kind = 'review_approver' AND NEW.enabled = 1
BEGIN
    SELECT RAISE(ABORT, 'review_approver users must be created disabled');
END;

CREATE TRIGGER users_review_approver_requires_operator_label
BEFORE UPDATE ON users
WHEN NEW.kind = 'review_approver'
     AND NEW.enabled = 1
     AND (NEW.operator_label IS NULL OR trim(NEW.operator_label) = '')
BEGIN
    SELECT RAISE(ABORT, 'review_approver requires an operator_label before enabling');
END;

CREATE TABLE tenders (
    tender_id TEXT PRIMARY KEY
        CHECK (tender_id GLOB 'NT-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]'),
    title TEXT NOT NULL,
    issuing_entity TEXT NOT NULL,
    closing_at TEXT NULL,
    project_type TEXT NULL,
    activity_codes TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'accepted', 'rejected')),
    source_name TEXT NULL,
    source_ref TEXT NULL,
    etimad_ref TEXT NULL,
    source_updated_at TEXT NULL,
    missing_fields TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    UNIQUE (source_name, source_ref),
    CHECK ((source_name IS NULL) = (source_ref IS NULL))
);

CREATE TRIGGER tenders_tender_id_immutable
BEFORE UPDATE OF tender_id ON tenders
WHEN NEW.tender_id <> OLD.tender_id
BEGIN
    SELECT RAISE(ABORT, 'tender_id is immutable');
END;

CREATE TABLE approvals (
    approval_id TEXT PRIMARY KEY,
    tender_id TEXT NULL REFERENCES tenders(tender_id),
    subject_type TEXT NOT NULL
        CHECK (subject_type IN (
            'tender', 'report', 'finding', 'gap_task', 'manual_entry',
            'field_completion', 'import', 'permission_grant', 'demo_gate_decision')),
    subject_id TEXT NOT NULL,
    acting_role TEXT NOT NULL,
    decision TEXT NOT NULL
        CHECK (decision IN ('approved', 'approved_with_reservation', 'rejected')),
    reservations TEXT NULL,
    actor_user_id TEXT NOT NULL REFERENCES users(user_id),
    decided_at TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    CHECK (decision <> 'approved_with_reservation'
           OR length(trim(coalesce(reservations, ''))) > 0)
);

CREATE TRIGGER approvals_are_immutable_update
BEFORE UPDATE ON approvals
BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable');
END;

CREATE TRIGGER approvals_are_immutable_delete
BEFORE DELETE ON approvals
BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable');
END;

CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    title TEXT NOT NULL,
    owner_user_id TEXT NULL REFERENCES users(user_id),
    owner_role TEXT NULL,
    due_at TEXT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
    origin TEXT NOT NULL,
    proposal_version INTEGER NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE proposal_versions (
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    version INTEGER NOT NULL CHECK (version >= 1),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    built_at TEXT NOT NULL,
    requested_by TEXT NOT NULL REFERENCES users(user_id),
    activity_codes TEXT NOT NULL,
    rejected_activities TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('built', 'failed')),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    PRIMARY KEY (tender_id, version)
);

CREATE TABLE review_reports (
    report_id TEXT PRIMARY KEY,
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    proposal_version INTEGER NOT NULL,
    proposal_sha256 TEXT NOT NULL,
    rfp_sha256 TEXT NOT NULL,
    report_sha256 TEXT NULL,
    artifact_id TEXT NULL,
    seal_artifact_id TEXT NULL,
    checks_run TEXT NOT NULL,
    limitations TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'proposed'
        CHECK (approval_state IN ('proposed', 'approved', 'approved_with_reservation', 'rejected')),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE findings (
    finding_key TEXT NOT NULL,
    report_id TEXT NOT NULL REFERENCES review_reports(report_id),
    criterion_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('match', 'mismatch', 'unverifiable')),
    sources TEXT NOT NULL,
    message TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'proposed'
        CHECK (approval_state IN ('proposed', 'approved', 'approved_with_reservation', 'rejected')),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    PRIMARY KEY (report_id, finding_key)
);

CREATE TABLE gap_proposals (
    finding_key TEXT NOT NULL,
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    report_id TEXT NOT NULL REFERENCES review_reports(report_id),
    proposal_version INTEGER NOT NULL,
    criterion_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'finding_approved', 'task_created', 'rejected')),
    task_id TEXT NULL REFERENCES tasks(task_id),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    PRIMARY KEY (report_id, finding_key)
);

CREATE TABLE memberships (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    role TEXT NOT NULL
        CHECK (role IN ('approver', 'review_approver', 'member', 'viewer')),
    owner_authorization_ref TEXT NOT NULL,
    configured_by_user_id TEXT NOT NULL REFERENCES users(user_id),
    granted_at TEXT NOT NULL,
    grant_approval_id TEXT NOT NULL REFERENCES approvals(approval_id),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1),
    PRIMARY KEY (user_id, tender_id, role)
);

CREATE TABLE creation_grants (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    capability TEXT NOT NULL CHECK (capability = 'create_synthetic_tender'),
    owner_authorization_ref TEXT NOT NULL,
    configured_by_user_id TEXT NOT NULL REFERENCES users(user_id),
    granted_at TEXT NOT NULL,
    grant_approval_id TEXT NOT NULL REFERENCES approvals(approval_id),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT NOT NULL REFERENCES tenders(tender_id),
    field TEXT NOT NULL,
    "old" TEXT NULL,
    "new" TEXT NULL,
    source TEXT NOT NULL CHECK (source IN ('radar_import', 'manual')),
    actor_user_id TEXT NOT NULL REFERENCES users(user_id),
    "at" TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE tender_counter (
    year INTEGER PRIMARY KEY,
    last INTEGER NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE noor_schema (
    version INTEGER NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);

CREATE TABLE system_session (
    sid_hash TEXT PRIMARY KEY CHECK (length(sid_hash) = 64 AND sid_hash NOT GLOB '*[^0-9a-f]*'),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    idle_expires_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active','logged_out','expired','revoked')),
    theme_pref TEXT NOT NULL DEFAULT 'system' CHECK (theme_pref IN ('system','light','dark')),
    csrf_token TEXT NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TRIGGER system_session_no_reactivation BEFORE UPDATE OF state ON system_session
WHEN OLD.state <> 'active' AND NEW.state = 'active'
BEGIN SELECT RAISE(ABORT, 'session cannot reactivate'); END;
CREATE TABLE platform_session (
    psid_hash TEXT PRIMARY KEY CHECK (length(psid_hash) = 64 AND psid_hash NOT GLOB '*[^0-9a-f]*'),
    parent_sid_hash TEXT NOT NULL REFERENCES system_session(sid_hash),
    platform_id TEXT NOT NULL CHECK (platform_id IN ('nmis_full','radar','quick_analysis','jouready')),
    created_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active','revoked')),
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TRIGGER platform_session_no_reactivation BEFORE UPDATE OF state ON platform_session
WHEN OLD.state = 'revoked' AND NEW.state = 'active'
BEGIN SELECT RAISE(ABORT, 'platform session cannot reactivate'); END;
CREATE TRIGGER system_session_revoke_derived AFTER UPDATE OF state ON system_session
WHEN OLD.state = 'active' AND NEW.state <> 'active'
BEGIN
    UPDATE platform_session SET state='revoked' WHERE parent_sid_hash=NEW.sid_hash;
    UPDATE desktop_handle SET state='locked' WHERE sid_hash=NEW.sid_hash;
END;
CREATE TABLE entry_code (
    code_hash TEXT PRIMARY KEY CHECK (length(code_hash) = 64 AND code_hash NOT GLOB '*[^0-9a-f]*'),
    parent_sid_hash TEXT NOT NULL REFERENCES system_session(sid_hash),
    platform_id TEXT NOT NULL CHECK (platform_id IN ('nmis_full','radar','quick_analysis','jouready')),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE desktop_launch_ticket (
    ticket_hash TEXT PRIMARY KEY CHECK (length(ticket_hash) = 64 AND ticket_hash NOT GLOB '*[^0-9a-f]*'),
    sid_hash TEXT NOT NULL REFERENCES system_session(sid_hash),
    client TEXT NOT NULL CHECK (client = 'desktop:atpas'),
    launched_pid INTEGER NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE desktop_handle (
    handle_hash TEXT PRIMARY KEY CHECK (length(handle_hash) = 64 AND handle_hash NOT GLOB '*[^0-9a-f]*'),
    sid_hash TEXT NOT NULL REFERENCES system_session(sid_hash),
    client TEXT NOT NULL CHECK (client = 'desktop:atpas'),
    pid INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active','locked')),
    last_check_at TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE access_decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    platform_id TEXT,
    user_id TEXT,
    result TEXT NOT NULL CHECK (result IN ('ok','no_session','expired','forbidden','bad_platform_key','bad_assertion')),
    action TEXT,
    tender_id TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE platform_entry (
    platform_id TEXT PRIMARY KEY CHECK (platform_id IN ('nmis_full','radar','quick_analysis','atpas','jouready')),
    display_name TEXT NOT NULL, upstream TEXT NOT NULL, browser_origin TEXT NOT NULL,
    run_state TEXT NOT NULL CHECK (run_state IN ('running','stopped','unavailable_on_device','not_cleared_for_demo')),
    maturity TEXT NOT NULL CHECK (maturity IN ('L0','L1','L2','L3')),
    provider_mode TEXT NOT NULL CHECK (provider_mode IN ('local','cloud','none')),
    demo_gate TEXT NOT NULL CHECK (demo_gate IN ('passed','failed','at_risk','pending')),
    fr010_result TEXT, exposure_closure_ref TEXT, snapshot_tree_sha256 TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE fr010_run (
    run_id TEXT PRIMARY KEY, platform_id TEXT NOT NULL REFERENCES platform_entry(platform_id),
    at TEXT NOT NULL, snapshot_tree_sha256 TEXT NOT NULL, checklist_version TEXT NOT NULL,
    passed_count INTEGER NOT NULL, total_count INTEGER NOT NULL,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
CREATE TABLE fr010_item (
    run_id TEXT NOT NULL REFERENCES fr010_run(run_id), item_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('pass','fail','blocked')),
    evidence_sha256 TEXT, note TEXT,
    synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1), PRIMARY KEY(run_id,item_id)
);
CREATE TABLE qa_eval_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, model TEXT NOT NULL,
    sample_id TEXT NOT NULL, m1_fact_recall REAL NOT NULL, m2_invented_numbers INTEGER NOT NULL,
    m3_seconds REAL NOT NULL, threshold_version TEXT NOT NULL, passed INTEGER NOT NULL CHECK (passed IN (0,1)),
    reproduce_cmd TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 1 CHECK (synthetic = 1)
);
"""


def open_db(data_dir: Path, *, create: bool = False) -> sqlite3.Connection:
    """Open the demo database that lives inside ``data_dir``.

    ``create=True`` initialises a brand new database and refuses to run when
    the file already exists (no in-place migration of a live database).
    ``create=False`` opens an existing, initialised database and validates the
    schema version.
    """

    data_dir = Path(data_dir)
    db_path = data_dir / DB_FILENAME

    if create:
        if db_path.exists():
            raise DbError(
                f"refusing to create a database that already exists: {db_path.name}"
            )
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - depends on the filesystem
            raise DbError(f"cannot create data directory: {exc}") from exc
    else:
        if not db_path.exists():
            raise DbError(f"database not found: {db_path.name}")

    try:
        # The default isolation level is kept on purpose: callers use
        # ``with conn:`` for transactions.
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        raise DbError(f"cannot open database: {exc}") from exc

    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error as exc:
        conn.close()
        raise DbError(f"cannot configure database: {exc}") from exc

    if create:
        try:
            with conn:
                conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO noor_schema (version, synthetic) VALUES (?, 1)",
                (SCHEMA_VERSION,),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.close()
            # A half-initialised file would make every later create=True refuse to run.
            for leftover in (db_path, db_path.with_name(db_path.name + "-wal"),
                             db_path.with_name(db_path.name + "-shm")):
                leftover.unlink(missing_ok=True)
            raise DbError(f"cannot initialise database: {exc}") from exc
        return conn

    try:
        row = conn.execute("SELECT version FROM noor_schema").fetchone()
    except sqlite3.Error as exc:
        conn.close()
        raise DbError("database has not been initialised") from exc
    if row is None:
        conn.close()
        raise DbError("database has not been initialised")
    if row["version"] != SCHEMA_VERSION:
        conn.close()
        raise DbError(f"unsupported schema version: {row['version']}")
    return conn


def next_tender_id(conn: sqlite3.Connection, year: int) -> str:
    """Return the next tender identifier for ``year``.

    The counter is incremented inside the caller's transaction; this helper
    never commits on its own.
    """

    if isinstance(year, bool) or not isinstance(year, int):
        raise DbError("year must be an integer")
    if year < 0 or year > 9999:
        raise DbError("year out of range")

    row = conn.execute(
        "SELECT last FROM tender_counter WHERE year = ?", (year,)
    ).fetchone()
    last = int(row["last"]) if row is not None else 0
    nxt = last + 1
    if nxt > 9999:
        raise DbError(f"tender counter for year {year} is exhausted")

    conn.execute(
        "INSERT INTO tender_counter (year, last, synthetic) VALUES (?, ?, 1) "
        "ON CONFLICT(year) DO UPDATE SET last = excluded.last",
        (year, nxt),
    )
    return f"NT-{year:04d}-{nxt:04d}"
