"""The single place that decides permissions and writes approvals.

Every permission question in the NMIS demo application is answered here so the
rules stay in one auditable module.  Identity always comes from the ``User``
object that was loaded from the server side session -- never from request
data supplied by the browser.

The module only ever touches the local SQLite database; there is no network
access and no shell usage.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass

from .authorizations import AuthorizationError, Register
from .db import utc_now

__all__ = [
    "ACTIONS",
    "AuthzError",
    "MEMBERSHIP_ROLES",
    "SUBJECT_TYPES",
    "DECISIONS",
    "User",
    "authorize",
    "authorize_creation",
    "grant_creator_approver",
    "grant_membership",
    "load_user",
    "record_approval",
]


class AuthzError(PermissionError):
    """Raised when an action is not permitted.

    ``reason`` carries a short, stable code (for example ``no_permission``) so
    that callers can react without parsing free text.
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message if message else reason)
        self.reason = reason


@dataclass(frozen=True)
class User:
    """The authenticated principal (always loaded from the local session)."""

    user_id: str
    kind: str
    enabled: bool
    display_name: str = ""


MEMBERSHIP_ROLES = frozenset({"approver", "review_approver", "member", "viewer"})

#: How strong each membership role is; used to report the acting role.
ROLE_STRENGTH = {
    "approver": 3,
    "review_approver": 2,
    "member": 1,
    "viewer": 0,
}

#: Membership roles that are allowed to perform each action.
ACTIONS: dict[str, frozenset[str]] = {
    "accept_tender": frozenset({"approver"}),
    "reject_tender": frozenset({"approver"}),
    "create_gap_task": frozenset({"approver"}),
    "field_completion": frozenset({"approver"}),
    "update_tender": frozenset({"approver"}),
    "import_update": frozenset({"approver"}),
    "manual_entry_existing": frozenset({"approver"}),
    "approve_report": frozenset({"review_approver"}),
    "approve_finding": frozenset({"review_approver"}),
    "approve_gaps": frozenset({"review_approver"}),
    "update_own_task": frozenset({"member"}),
    "request_build": frozenset({"approver", "member", "review_approver"}),
    "run_review": frozenset({"approver", "member", "review_approver"}),
    "import_review": frozenset({"approver", "member", "review_approver"}),
}

#: Subject types that may be recorded in the ``approvals`` table.
SUBJECT_TYPES = frozenset(
    {
        "tender",
        "report",
        "finding",
        "gap_task",
        "manual_entry",
        "field_completion",
        "import",
        "permission_grant",
        "demo_gate_decision",
    }
)

#: Decisions that may be recorded in the ``approvals`` table.
DECISIONS = frozenset({"approved", "approved_with_reservation", "rejected"})


def load_user(conn: sqlite3.Connection, user_id: str) -> User | None:
    """Load a user by id, or return ``None`` when the id is unknown."""

    row = conn.execute(
        "SELECT user_id, kind, enabled, display_name FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return User(user_id=row["user_id"], kind=row["kind"], enabled=bool(row["enabled"]),
                display_name=row["display_name"])


def _tender_exists(conn: sqlite3.Connection, tender_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM tenders WHERE tender_id = ?", (tender_id,)
    ).fetchone()
    return row is not None


def _membership_roles(
    conn: sqlite3.Connection, user_id: str, tender_id: str
) -> list[str]:
    rows = conn.execute(
        "SELECT role FROM memberships WHERE user_id = ? AND tender_id = ?",
        (user_id, tender_id),
    ).fetchall()
    return [row["role"] for row in rows]


def _strongest_role(roles: list[str]) -> str:
    best = "viewer"
    for role in roles:
        if ROLE_STRENGTH.get(role, 0) > ROLE_STRENGTH.get(best, 0):
            best = role
    return best


def authorize(
    conn: sqlite3.Connection,
    user: User | None,
    tender_id: str,
    action: str,
    *,
    task_id: str | None = None,
) -> str:
    """Return the acting role for ``action`` on ``tender_id``.

    Raises :class:`AuthzError` with a short ``reason`` code when the action
    is not allowed.
    """

    if user is None:
        raise AuthzError("no_session", "there is no authenticated session")
    if not user.enabled:
        raise AuthzError("disabled", "the account is disabled")
    if action not in ("view", "view_tender") and action not in ACTIONS:
        raise AuthzError("unknown_action", f"unknown action: {action}")
    if user.kind == "viewer" and action not in ("view", "view_tender"):
        # Viewers stay read-only even if a membership row exists somehow.
        raise AuthzError("read_only", "viewer accounts may only view")
    if not _tender_exists(conn, tender_id):
        raise AuthzError("no_tender", f"unknown tender: {tender_id}")

    if action == "view":
        if user.kind == "viewer":
            return "viewer"
        return _strongest_role(_membership_roles(conn, user.user_id, tender_id))

    if action == "view_tender":
        roles = _membership_roles(conn, user.user_id, tender_id)
        if not roles:
            raise AuthzError("no_permission", "no membership on tender")
        return "viewer" if user.kind == "viewer" else _strongest_role(roles)

    allowed = ACTIONS[action]
    granted = [role for role in _membership_roles(conn, user.user_id, tender_id)
               if role in allowed]
    if not granted:
        raise AuthzError(
            "no_permission",
            f"no {action} permission on tender {tender_id}",
        )
    if action == "update_own_task":
        task = conn.execute(
            "SELECT 1 FROM tasks WHERE task_id=? AND tender_id=? AND owner_user_id=?",
            (task_id, tender_id, user.user_id),
        ).fetchone() if task_id else None
        if task is None:
            raise AuthzError("no_permission", "task is not owned on this tender")
    return _strongest_role(granted)


def authorize_creation(conn: sqlite3.Connection, user: User | None) -> sqlite3.Row:
    """Return the ``creation_grants`` row that allows ``user`` to create tenders.

    The account kind alone never grants anything: only an explicit
    ``creation_grants`` row does.
    """

    if user is None:
        raise AuthzError("no_session", "there is no authenticated session")
    if not user.enabled:
        raise AuthzError("disabled", "the account is disabled")
    if user.kind == "viewer":
        raise AuthzError("read_only", "viewer accounts may only view")

    row = conn.execute(
        "SELECT * FROM creation_grants WHERE user_id = ?", (user.user_id,)
    ).fetchone()
    if row is None:
        raise AuthzError(
            "no_creation_grant",
            f"{user.user_id} has no creation grant",
        )
    return row


def record_approval(
    conn: sqlite3.Connection,
    *,
    actor: User,
    subject_type: str,
    subject_id: str,
    decision: str,
    acting_role: str,
    tender_id: str | None = None,
    reservations: str | None = None,
) -> str:
    """Write exactly one approval row and return its identifier.

    The caller owns the transaction (``with conn:``); this function never
    commits by itself.
    """

    if actor is None:
        raise AuthzError("no_session", "there is no authenticated session")
    if subject_type not in SUBJECT_TYPES:
        raise AuthzError("bad_decision", f"unknown subject_type: {subject_type}")
    if decision not in DECISIONS:
        raise AuthzError("bad_decision", f"unknown decision: {decision}")
    if decision == "approved_with_reservation" and not (
        reservations and reservations.strip()
    ):
        raise AuthzError(
            "bad_decision",
            "approved_with_reservation requires a non-empty reservation",
        )

    approval_id = "AP-" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO approvals ("
        " approval_id, tender_id, subject_type, subject_id, acting_role,"
        " decision, reservations, actor_user_id, decided_at, synthetic"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (
            approval_id,
            tender_id,
            subject_type,
            subject_id,
            acting_role,
            decision,
            reservations,
            actor.user_id,
            utc_now(),
        ),
    )
    return approval_id


def grant_creator_approver(
    conn: sqlite3.Connection,
    *,
    creator: User,
    tender_id: str,
    creation_grant: sqlite3.Row,
) -> str:
    """Give the creator of a synthetic tender the ``approver`` membership.

    The tender status is never touched here.  The caller owns the
    transaction.
    """

    if creator is None:
        raise AuthzError("no_session", "there is no authenticated session")
    if not creator.enabled:
        raise AuthzError("disabled", "the account is disabled")
    if not _tender_exists(conn, tender_id):
        raise AuthzError("no_tender", f"unknown tender: {tender_id}")

    owner_authorization_ref = creation_grant["owner_authorization_ref"]
    approval_id = record_approval(
        conn,
        actor=creator,
        subject_type="permission_grant",
        subject_id=f"{tender_id}:{creator.user_id}:approver",
        decision="approved",
        acting_role="creation_grant",
        tender_id=tender_id,
    )
    conn.execute(
        "INSERT INTO memberships ("
        " user_id, tender_id, role, owner_authorization_ref,"
        " configured_by_user_id, granted_at, grant_approval_id, synthetic"
        ") VALUES (?, ?, 'approver', ?, ?, ?, ?, 1)",
        (
            creator.user_id,
            tender_id,
            owner_authorization_ref,
            # Who configured the creation grant, not the creator: keeps the provenance honest.
            creation_grant["configured_by_user_id"],
            utc_now(),
            approval_id,
        ),
    )
    return approval_id


def grant_membership(
    conn: sqlite3.Connection,
    *,
    configurer: User,
    grantee_id: str,
    tender_id: str,
    role: str,
    owner_authorization_ref: str,
    register: Register,
) -> str:
    """Grant a tender membership to ``grantee_id`` (used by the local CLI).

    Only the designated configuration account may grant, and only what a documented record in the
    local authorization register allows (owner, grantee, role, tender). A permission-grant
    approval is written together with the membership. The caller owns the transaction.
    """

    if configurer is None:
        raise AuthzError("no_session", "there is no authenticated session")
    if not configurer.enabled:
        raise AuthzError("disabled", "the account is disabled")
    if configurer.kind == "viewer":
        raise AuthzError("read_only", "viewer accounts cannot configure grants")
    if not owner_authorization_ref or not str(owner_authorization_ref).strip():
        raise AuthzError(
            "bad_authorization_ref", "owner_authorization_ref is required"
        )
    if role not in MEMBERSHIP_ROLES:
        raise AuthzError("bad_role", f"unknown membership role: {role}")
    if configurer.user_id == grantee_id:
        raise AuthzError("self_grant", "an account cannot grant roles to itself")
    if not _tender_exists(conn, tender_id):
        raise AuthzError("no_tender", f"unknown tender: {tender_id}")

    grantee = load_user(conn, grantee_id)
    if grantee is None:
        raise AuthzError("no_grantee", f"unknown grantee: {grantee_id}")
    if grantee.kind == "viewer" and role != "viewer":
        raise AuthzError(
            "viewer_grant", "a viewer account may only hold the viewer role"
        )
    if role == "review_approver":
        row = conn.execute(
            "SELECT kind, operator_label FROM users WHERE user_id = ?", (grantee_id,)
        ).fetchone()
        operator_label = "" if row is None or row["operator_label"] is None else row["operator_label"]
        if grantee.kind != "review_approver" or not str(operator_label).strip():
            raise AuthzError(
                "operator_required",
                "the review approver role requires a named operator",
            )

    try:
        register.require(configurer_id=configurer.user_id, ref=owner_authorization_ref,
                         grantee=grantee_id, role=role, tender_id=tender_id)
    except AuthorizationError as exc:
        raise AuthzError("no_authorization", str(exc)) from exc

    approval_id = record_approval(
        conn,
        actor=configurer,
        subject_type="permission_grant",
        subject_id=f"{tender_id}:{grantee_id}:{role}",
        decision="approved",
        acting_role="membership_grant",
        tender_id=tender_id,
    )
    conn.execute(
        "INSERT INTO memberships ("
        " user_id, tender_id, role, owner_authorization_ref,"
        " configured_by_user_id, granted_at, grant_approval_id, synthetic"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (
            grantee_id,
            tender_id,
            role,
            owner_authorization_ref,
            configurer.user_id,
            utc_now(),
            approval_id,
        ),
    )
    return approval_id
