"""Domain layer for the synthetic NMIS tender registry.

Rules enforced here: a tender is always created as a 'candidate', an import may only
refresh title, closing_at and source_updated_at, and a stored closing date is never
cleared by an import. Every refusal raises RegistryError carrying a short stable reason
code. This module never commits: the caller owns the surrounding transaction.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .authz import (
    User,
    authorize,
    authorize_creation,
    grant_creator_approver,
    record_approval,
)
from .db import next_tender_id, utc_now

__all__ = [
    "ACCEPT_REQUIRED_FIELDS",
    "MATCH_WINDOW_DAYS",
    "TITLE_SIMILARITY_MIN",
    "RegistryError",
    "ImportResult",
    "create_tender",
    "find_possible_matches",
    "normalize_arabic",
    "parse_time",
    "title_similarity",
    "upsert_candidate",
]

# Fields that block acceptance while they are still missing.
ACCEPT_REQUIRED_FIELDS = ("closing_at",)

# Two closing dates farther apart than this are never considered the same tender.
MATCH_WINDOW_DAYS = 7

# Minimum normalized title similarity for a possible match.
TITLE_SIMILARITY_MIN = 0.6

# Import-updatable fields, in the order used for change reporting.
IMPORT_UPDATABLE_FIELDS = ("title", "closing_at", "source_updated_at")
# One fixed statement per updatable field: no SQL is ever built from data.
_UPDATE_SQL = {
    "title": "UPDATE tenders SET title = ? WHERE tender_id = ?",
    "closing_at": "UPDATE tenders SET closing_at = ? WHERE tender_id = ?",
    "source_updated_at": "UPDATE tenders SET source_updated_at = ? WHERE tender_id = ?",
}

_DIACRITICS_RE = re.compile("[\u064b-\u065f\u0670\u0640]")
_WHITESPACE_RE = re.compile(r"\s+")
_TRAILING_Z_RE = re.compile(r"[Zz]$")

_LETTER_MAP = str.maketrans(
    {
        "\u0623": "\u0627",  # أ -> ا
        "\u0625": "\u0627",  # إ -> ا
        "\u0622": "\u0627",  # آ -> ا
        "\u0671": "\u0627",  # ٱ -> ا
        "\u0649": "\u064a",  # ى -> ي
        "\u0629": "\u0647",  # ة -> ه
    }
)


class RegistryError(ValueError):
    """Business-rule refusal; .reason is a short stable code, the message names no secret."""

    def __init__(self, reason: str, message: str | None = None):
        super().__init__(message if message is not None else reason)
        self.reason = reason
        self.message = message if message is not None else reason


@dataclass(frozen=True)
class ImportResult:
    """Outcome of one import write: the tender id, whether it was created, what changed."""

    tender_id: str
    created: bool
    changed_fields: tuple[str, ...]


def normalize_arabic(text: str) -> str:
    """Strip Arabic diacritics/tatweel, unify alef/ya/ta-marbuta, casefold and squeeze spaces."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = _DIACRITICS_RE.sub("", text)
    cleaned = cleaned.translate(_LETTER_MAP)
    cleaned = cleaned.casefold()
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def title_similarity(a: str, b: str) -> float:
    """Symmetric similarity of two titles after Arabic normalization (0.0 - 1.0)."""
    left = normalize_arabic(a)
    right = normalize_arabic(b)
    if left == right:
        return 1.0
    forward = difflib.SequenceMatcher(None, left, right).ratio()
    backward = difflib.SequenceMatcher(None, right, left).ratio()
    return max(forward, backward)


def parse_time(value: str) -> datetime:
    """Parse an ISO-8601 timestamp that carries an explicit offset; 'Z' means UTC."""
    if not isinstance(value, str):
        raise RegistryError("bad_time", "timestamp must be an ISO-8601 string with an offset")
    text = value.strip()
    if not text:
        raise RegistryError("bad_time", "timestamp must be an ISO-8601 string with an offset")
    text = _TRAILING_Z_RE.sub("+00:00", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise RegistryError("bad_time", "timestamp is not a valid ISO-8601 value") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegistryError("bad_time", "timestamp must carry an explicit UTC offset")
    return parsed


def find_possible_matches(
    conn: sqlite3.Connection,
    *,
    title: str,
    issuing_entity: str,
    closing_at: str | None,
    exclude_tender_id: str | None = None,
) -> list[sqlite3.Row]:
    """Return tender rows that may be the same tender (same entity, similar title, close date)."""
    entity_key = normalize_arabic(issuing_entity)
    wanted_closing = parse_time(closing_at) if closing_at is not None else None
    window = timedelta(days=MATCH_WINDOW_DAYS)

    rows = conn.execute(
        "SELECT * FROM tenders WHERE (? IS NULL OR tender_id <> ?)",
        (exclude_tender_id, exclude_tender_id),
    ).fetchall()

    matches: list[sqlite3.Row] = []
    for row in rows:
        if normalize_arabic(row["issuing_entity"]) != entity_key:
            continue
        if title_similarity(row["title"], title) < TITLE_SIMILARITY_MIN:
            continue
        if wanted_closing is not None and row["closing_at"]:
            try:
                stored_closing = parse_time(row["closing_at"])
            except RegistryError:
                stored_closing = None
            if stored_closing is not None and abs(stored_closing - wanted_closing) > window:
                continue
        matches.append(row)

    matches.sort(key=lambda item: item["tender_id"])
    return matches


def create_tender(
    conn: sqlite3.Connection,
    *,
    creator: User,
    creation_grant: sqlite3.Row,
    title: str,
    issuing_entity: str,
    closing_at: str | None,
    etimad_ref: str | None = None,
    source_name: str | None = None,
    source_ref: str | None = None,
    source_updated_at: str | None = None,
    now: str | None = None,
) -> str:
    """Insert a new candidate tender and grant its creator the approver membership."""
    now = now or utc_now()
    year = parse_time(now).year
    tender_id = next_tender_id(conn, year)

    known_values = {"closing_at": closing_at}
    missing = [name for name in ACCEPT_REQUIRED_FIELDS if known_values.get(name) is None]

    try:
        conn.execute(
            "INSERT INTO tenders ("
            "tender_id, title, issuing_entity, closing_at, status, source_name, source_ref,"
            " etimad_ref, source_updated_at, missing_fields, created_by, created_at, synthetic"
            ") VALUES (?, ?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, 1)",
            (
                tender_id,
                title,
                issuing_entity,
                closing_at,
                source_name,
                source_ref,
                etimad_ref,
                source_updated_at,
                json.dumps(missing),
                creator.user_id,
                now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise RegistryError(
            "duplicate", "a tender with the same source reference already exists"
        ) from None

    grant_creator_approver(
        conn, creator=creator, tender_id=tender_id, creation_grant=creation_grant
    )
    return tender_id


def upsert_candidate(
    conn: sqlite3.Connection,
    *,
    user: User,
    candidate: dict,
    now: str | None = None,
) -> ImportResult:
    """Create or refresh a tender from a validated candidate payload; never accepts a tender."""
    grant = authorize_creation(conn, user)
    now = now or utc_now()

    source_name = candidate.get("source_name")
    source_ref = candidate.get("source_ref")
    # "=" (not "IS"): an import without a source must never match a manually entered record.
    if not source_name or not source_ref:
        raise RegistryError("bad_candidate", "an import needs a source name and reference")
    row = conn.execute(
        "SELECT * FROM tenders WHERE source_name = ? AND source_ref = ?",
        (source_name, source_ref),
    ).fetchone()

    if row is None:
        tender_id = create_tender(
            conn,
            creator=user,
            creation_grant=grant,
            title=candidate.get("title"),
            issuing_entity=candidate.get("issuing_entity"),
            closing_at=candidate.get("closing_at"),
            etimad_ref=candidate.get("etimad_ref"),
            source_name=source_name,
            source_ref=source_ref,
            source_updated_at=candidate.get("source_updated_at"),
            now=now,
        )
        record_approval(
            conn,
            actor=user,
            subject_type="import",
            subject_id=tender_id,
            decision="approved",
            acting_role="creation_grant",
            tender_id=tender_id,
        )
        return ImportResult(tender_id=tender_id, created=True, changed_fields=())

    tender_id = row["tender_id"]
    role = authorize(conn, user, tender_id, "import_update")

    changes: list[tuple[str, object, object]] = []

    new_title = candidate.get("title")
    if new_title is not None and new_title != row["title"]:
        changes.append(("title", row["title"], new_title))

    new_closing = candidate.get("closing_at")
    if new_closing is not None and new_closing != row["closing_at"]:
        changes.append(("closing_at", row["closing_at"], new_closing))

    new_source_updated_at = candidate.get("source_updated_at")
    if new_source_updated_at != row["source_updated_at"]:
        changes.append(
            ("source_updated_at", row["source_updated_at"], new_source_updated_at)
        )

    for field, old_value, new_value in changes:
        conn.execute(_UPDATE_SQL[field], (new_value, tender_id))
        conn.execute(
            'INSERT INTO change_log ('
            'tender_id, field, "old", "new", source, actor_user_id, "at", synthetic'
            ") VALUES (?, ?, ?, ?, 'radar_import', ?, ?, 1)",
            (tender_id, field, old_value, new_value, user.user_id, now),
        )

    stored_missing = row["missing_fields"]
    try:
        missing = json.loads(stored_missing) if stored_missing else []
    except (TypeError, ValueError):
        missing = []
    if not isinstance(missing, list):
        missing = []

    effective_closing = new_closing if new_closing is not None else row["closing_at"]
    remaining = [
        name
        for name in missing
        if not (name == "closing_at" and effective_closing is not None)
    ]
    if remaining != missing:
        conn.execute(
            "UPDATE tenders SET missing_fields = ? WHERE tender_id = ?",
            (json.dumps(remaining), tender_id),
        )

    record_approval(
        conn,
        actor=user,
        subject_type="import",
        subject_id=tender_id,
        decision="approved",
        acting_role=role,
        tender_id=tender_id,
    )

    return ImportResult(
        tender_id=tender_id,
        created=False,
        changed_fields=tuple(field for field, _, _ in changes),
    )
