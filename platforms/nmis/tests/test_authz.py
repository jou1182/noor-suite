"""Authorisation tests for the NMIS registry (T020).

The tests only use the local SQLite database; no network access and no shell
usage is involved.
"""

from __future__ import annotations

import sqlite3
import uuid
from types import SimpleNamespace

import pytest
from noor_registry.authorizations import Register
from noor_registry.authz import (
    ACTIONS,
    AuthzError,
    User,
    authorize,
    authorize_creation,
    grant_creator_approver,
    grant_membership,
    load_user,
    record_approval,
)
from noor_registry.db import next_tender_id, open_db
from werkzeug.security import generate_password_hash

PASSWORD_HASH = generate_password_hash("test-password-xx")
NOW = "2026-01-01T00:00:00+00:00"

TENDER_A = "NT-2026-0001"
# Local authorization register used by grant tests (the real one lives outside the repo).
REGISTER = Register("cfg", (
    {"ref": "AUTH-REF-001", "owner": "jouready_owner", "grantee": "ra",
     "role": "review_approver", "tender_id": TENDER_A},
    {"ref": "AUTH-REF-001", "owner": "nmis_owner", "grantee": "view",
     "role": "viewer", "tender_id": TENDER_A},
    {"ref": "AUTH-REF-001", "owner": "nmis_owner", "grantee": "mem",
     "role": "member", "tender_id": TENDER_A},
))
TENDER_B = "NT-2026-0002"

# A year that is not used by the fixtures, so the generated ids do not clash.
FREE_YEAR = 2027


@pytest.fixture()
def env(tmp_path):
    data_dir = tmp_path / "data"
    conn = open_db(data_dir, create=True)

    for user_id, kind in (
        ("pm", "proposal_manager"),
        ("pm2", "proposal_manager"),
        ("mem", "member"),
        ("view", "viewer"),
        ("cfg", "proposal_manager"),
    ):
        conn.execute(
            "INSERT INTO users (user_id, display_name, kind, password_hash, enabled,"
            " operator_label) VALUES (?, ?, ?, ?, 1, NULL)",
            (user_id, f"user {user_id}", kind, PASSWORD_HASH),
        )

    # A review approver is always created disabled and only enabled once a
    # named operator label exists.
    conn.execute(
        "INSERT INTO users (user_id, display_name, kind, password_hash, enabled,"
        " operator_label) VALUES ('ra', 'user ra', 'review_approver', ?, 0, ?)",
        (PASSWORD_HASH, "مشغّل اختبار وهمي"),
    )
    conn.execute("UPDATE users SET enabled = 1 WHERE user_id = 'ra'")

    # A second review approver without any operator label.
    conn.execute(
        "INSERT INTO users (user_id, display_name, kind, password_hash, enabled,"
        " operator_label) VALUES ('ra2', 'user ra2', 'review_approver', ?, 0, NULL)",
        (PASSWORD_HASH,),
    )
    conn.commit()

    for tender_id in (TENDER_A, TENDER_B):
        conn.execute(
            "INSERT INTO tenders (tender_id, title, issuing_entity, created_by,"
            " created_at) VALUES (?, ?, ?, 'pm', ?)",
            (tender_id, f"tender {tender_id}", "synthetic entity", NOW),
        )
    conn.commit()

    users = {
        user_id: load_user(conn, user_id)
        for user_id in ("pm", "pm2", "mem", "view", "cfg", "ra", "ra2")
    }
    yield SimpleNamespace(conn=conn, users=users, data_dir=data_dir)
    conn.close()


def _add_approval(
    conn,
    *,
    subject_type="permission_grant",
    subject_id="subject",
    decision="approved",
    tender_id=None,
    actor_user_id="cfg",
    reservations=None,
):
    approval_id = "AP-" + uuid.uuid4().hex[:16]
    conn.execute(
        "INSERT INTO approvals (approval_id, tender_id, subject_type, subject_id,"
        " acting_role, decision, reservations, actor_user_id, decided_at)"
        " VALUES (?, ?, ?, ?, 'approver', ?, ?, ?, ?)",
        (
            approval_id,
            tender_id,
            subject_type,
            subject_id,
            decision,
            reservations,
            actor_user_id,
            NOW,
        ),
    )
    conn.commit()
    return approval_id


def _add_membership(
    conn,
    user_id,
    tender_id,
    role,
    *,
    owner_authorization_ref="AUTH-REF-001",
    configured_by="cfg",
):
    approval_id = _add_approval(
        conn,
        subject_type="permission_grant",
        subject_id=f"{tender_id}:{user_id}:{role}",
        tender_id=tender_id,
        actor_user_id=configured_by,
    )
    conn.execute(
        "INSERT INTO memberships (user_id, tender_id, role, owner_authorization_ref,"
        " configured_by_user_id, granted_at, grant_approval_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, tender_id, role, owner_authorization_ref, configured_by, NOW, approval_id),
    )
    conn.commit()
    return approval_id


def _add_creation_grant(conn, user_id, *, owner_authorization_ref="AUTH-REF-001"):
    approval_id = _add_approval(
        conn,
        subject_type="permission_grant",
        subject_id=f"{user_id}:create_synthetic_tender",
        actor_user_id="cfg",
    )
    conn.execute(
        "INSERT INTO creation_grants (user_id, capability, owner_authorization_ref,"
        " configured_by_user_id, granted_at, grant_approval_id)"
        " VALUES (?, 'create_synthetic_tender', ?, 'cfg', ?, ?)",
        (user_id, owner_authorization_ref, NOW, approval_id),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM creation_grants WHERE user_id = ?", (user_id,)
    ).fetchone()


def _count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --------------------------------------------------------------------------
# basic refusals
# --------------------------------------------------------------------------


def test_missing_session_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, None, TENDER_A, "view")
    assert excinfo.value.reason == "no_session"


def test_disabled_user_is_rejected(env):
    disabled = User(user_id="mem", kind="member", enabled=False)
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, disabled, TENDER_A, "view")
    assert excinfo.value.reason == "disabled"


def test_unknown_action_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["mem"], TENDER_A, "delete_everything")
    assert excinfo.value.reason == "unknown_action"


def test_unknown_tender_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["mem"], "NT-2026-9999", "view")
    assert excinfo.value.reason == "no_tender"


@pytest.mark.parametrize("action", sorted(ACTIONS))
def test_viewer_is_read_only_for_every_other_action(env, action):
    # Even a membership row inserted directly does not help a viewer.
    _add_membership(env.conn, "view", TENDER_A, "approver")
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["view"], TENDER_A, action)
    assert excinfo.value.reason == "read_only"


def test_viewer_may_view(env):
    assert authorize(env.conn, env.users["view"], TENDER_A, "view") == "viewer"


def test_viewer_view_ignores_membership_strength(env):
    _add_membership(env.conn, "view", TENDER_A, "approver")
    assert authorize(env.conn, env.users["view"], TENDER_A, "view") == "viewer"


def test_view_without_membership_reports_viewer(env):
    assert authorize(env.conn, env.users["mem"], TENDER_A, "view") == "viewer"


# --------------------------------------------------------------------------
# tender scoped roles
# --------------------------------------------------------------------------


def test_accept_tender_requires_approver_on_that_tender(env):
    _add_membership(env.conn, "pm", TENDER_A, "approver")
    assert authorize(env.conn, env.users["pm"], TENDER_A, "accept_tender") == "approver"


def test_membership_on_another_tender_does_not_count(env):
    _add_membership(env.conn, "pm", TENDER_A, "approver")
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["pm"], TENDER_B, "accept_tender")
    assert excinfo.value.reason == "no_permission"


def test_review_approver_membership_is_tender_scoped(env):
    _add_membership(env.conn, "ra", TENDER_A, "review_approver")
    assert (
        authorize(env.conn, env.users["ra"], TENDER_A, "approve_report")
        == "review_approver"
    )
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["ra"], TENDER_B, "approve_report")
    assert excinfo.value.reason == "no_permission"


def test_member_cannot_accept_but_may_request_a_build(env):
    _add_membership(env.conn, "mem", TENDER_A, "member")
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["mem"], TENDER_A, "accept_tender")
    assert excinfo.value.reason == "no_permission"
    assert authorize(env.conn, env.users["mem"], TENDER_A, "request_build") == "member"


def test_approver_alone_cannot_approve_a_report(env):
    _add_membership(env.conn, "pm", TENDER_A, "approver")
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["pm"], TENDER_A, "approve_report")
    assert excinfo.value.reason == "no_permission"
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["pm"], TENDER_A, "approve_finding")
    assert excinfo.value.reason == "no_permission"


def test_review_approver_may_approve_findings(env):
    _add_membership(env.conn, "ra", TENDER_A, "review_approver")
    assert (
        authorize(env.conn, env.users["ra"], TENDER_A, "approve_finding")
        == "review_approver"
    )


# --------------------------------------------------------------------------
# approvals
# --------------------------------------------------------------------------


def test_record_approval_writes_exactly_one_row(env):
    before = _count(env.conn, "approvals")
    approval_id = record_approval(
        env.conn,
        actor=env.users["pm"],
        subject_type="tender",
        subject_id=TENDER_A,
        decision="approved",
        acting_role="approver",
        tender_id=TENDER_A,
    )
    env.conn.commit()
    assert _count(env.conn, "approvals") == before + 1
    row = env.conn.execute(
        "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
    ).fetchone()
    assert row["decision"] == "approved"
    assert row["subject_type"] == "tender"
    assert row["actor_user_id"] == "pm"


def test_approved_with_reservation_needs_reservations(env):
    with pytest.raises(AuthzError) as excinfo:
        record_approval(
            env.conn,
            actor=env.users["ra"],
            subject_type="report",
            subject_id="R-1",
            decision="approved_with_reservation",
            acting_role="review_approver",
            tender_id=TENDER_A,
        )
    assert excinfo.value.reason == "bad_decision"


def test_unknown_decision_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        record_approval(
            env.conn,
            actor=env.users["pm"],
            subject_type="tender",
            subject_id=TENDER_A,
            decision="perhaps",
            acting_role="approver",
            tender_id=TENDER_A,
        )
    assert excinfo.value.reason == "bad_decision"


def test_approvals_cannot_be_updated_or_deleted(env):
    approval_id = record_approval(
        env.conn,
        actor=env.users["pm"],
        subject_type="tender",
        subject_id=TENDER_A,
        decision="approved",
        acting_role="approver",
        tender_id=TENDER_A,
    )
    env.conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        env.conn.execute(
            "UPDATE approvals SET decision = 'rejected' WHERE approval_id = ?",
            (approval_id,),
        )
    env.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        env.conn.execute("DELETE FROM approvals WHERE approval_id = ?", (approval_id,))
    env.conn.rollback()


# --------------------------------------------------------------------------
# creation grants
# --------------------------------------------------------------------------


def test_proposal_manager_without_grant_cannot_create(env):
    with pytest.raises(AuthzError) as excinfo:
        authorize_creation(env.conn, env.users["pm"])
    assert excinfo.value.reason == "no_creation_grant"


def test_viewer_cannot_create(env):
    with pytest.raises(AuthzError) as excinfo:
        authorize_creation(env.conn, env.users["view"])
    assert excinfo.value.reason == "read_only"


def test_creation_grant_allows_creation(env):
    _add_creation_grant(env.conn, "pm")
    row = authorize_creation(env.conn, env.users["pm"])
    assert row["user_id"] == "pm"
    assert row["capability"] == "create_synthetic_tender"


def test_creation_and_grant_happen_in_one_transaction(env):
    grant = _add_creation_grant(env.conn, "pm")

    with env.conn:
        tender_id = next_tender_id(env.conn, FREE_YEAR)
        env.conn.execute(
            "INSERT INTO tenders (tender_id, title, issuing_entity, created_by,"
            " created_at) VALUES (?, ?, ?, 'pm', ?)",
            (tender_id, "synthetic tender", "synthetic entity", NOW),
        )
        approval_id = grant_creator_approver(
            env.conn, creator=env.users["pm"], tender_id=tender_id, creation_grant=grant
        )

    rows = env.conn.execute(
        "SELECT * FROM memberships WHERE user_id = 'pm' AND tender_id = ?"
        " AND role = 'approver'",
        (tender_id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["grant_approval_id"] == approval_id
    assert rows[0]["owner_authorization_ref"] == grant["owner_authorization_ref"]
    # Provenance: the account that configured the creation grant, not the creator itself.
    assert rows[0]["configured_by_user_id"] == "cfg"

    approvals = env.conn.execute(
        "SELECT * FROM approvals WHERE subject_type = 'permission_grant'"
        " AND tender_id = ?",
        (tender_id,),
    ).fetchall()
    assert len(approvals) == 1
    assert approvals[0]["approval_id"] == approval_id

    status = env.conn.execute(
        "SELECT status FROM tenders WHERE tender_id = ?", (tender_id,)
    ).fetchone()["status"]
    assert status == "candidate"

    # The creator can now act as approver on that tender.
    assert authorize(env.conn, env.users["pm"], tender_id, "accept_tender") == "approver"


def test_failure_inside_the_transaction_rolls_everything_back(env):
    grant = _add_creation_grant(env.conn, "pm")
    tenders_before = _count(env.conn, "tenders")
    memberships_before = _count(env.conn, "memberships")
    approvals_before = _count(env.conn, "approvals")

    with pytest.raises(RuntimeError):
        with env.conn:
            tender_id = next_tender_id(env.conn, FREE_YEAR)
            env.conn.execute(
                "INSERT INTO tenders (tender_id, title, issuing_entity, created_by,"
                " created_at) VALUES (?, ?, ?, 'pm', ?)",
                (tender_id, "synthetic tender", "synthetic entity", NOW),
            )
            grant_creator_approver(
                env.conn,
                creator=env.users["pm"],
                tender_id=tender_id,
                creation_grant=grant,
            )
            raise RuntimeError("something went wrong")

    assert _count(env.conn, "tenders") == tenders_before
    assert _count(env.conn, "memberships") == memberships_before
    assert _count(env.conn, "approvals") == approvals_before
    assert (
        env.conn.execute(
            "SELECT count(*) FROM tenders WHERE tender_id = ?", (f"NT-{FREE_YEAR}-0001",)
        ).fetchone()[0]
        == 0
    )


def test_creator_without_membership_cannot_import_an_update(env):
    _add_creation_grant(env.conn, "pm2")
    _add_membership(env.conn, "pm", TENDER_A, "approver")
    with pytest.raises(AuthzError) as excinfo:
        authorize(env.conn, env.users["pm2"], TENDER_A, "import_update")
    assert excinfo.value.reason == "no_permission"


# --------------------------------------------------------------------------
# grant_membership (local grant CLI)
# --------------------------------------------------------------------------


def test_self_grant_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(
            env.conn,
            configurer=env.users["cfg"],
            grantee_id="cfg",
            tender_id=TENDER_A,
            role="approver",
            owner_authorization_ref="AUTH-REF-001",
            register=REGISTER,
        )
    assert excinfo.value.reason == "self_grant"


def test_granting_approver_to_a_viewer_is_rejected(env):
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(
            env.conn,
            configurer=env.users["cfg"],
            grantee_id="view",
            tender_id=TENDER_A,
            role="approver",
            owner_authorization_ref="AUTH-REF-001",
            register=REGISTER,
        )
    assert excinfo.value.reason == "viewer_grant"


def test_granting_reviewer_to_a_named_operator_works(env):
    before = _count(env.conn, "approvals")
    approval_id = grant_membership(
        env.conn,
        configurer=env.users["cfg"],
        grantee_id="ra",
        tender_id=TENDER_A,
        role="review_approver",
        owner_authorization_ref="AUTH-REF-001",
        register=REGISTER,
    )
    env.conn.commit()

    assert _count(env.conn, "approvals") == before + 1
    approval = env.conn.execute(
        "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
    ).fetchone()
    assert approval["subject_type"] == "permission_grant"

    membership = env.conn.execute(
        "SELECT * FROM memberships WHERE user_id = 'ra' AND tender_id = ?"
        " AND role = 'review_approver'",
        (TENDER_A,),
    ).fetchone()
    assert membership is not None
    assert membership["grant_approval_id"] == approval_id

    assert (
        authorize(env.conn, env.users["ra"], TENDER_A, "approve_report")
        == "review_approver"
    )


def test_granting_reviewer_requires_an_operator_label(env):
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(
            env.conn,
            configurer=env.users["cfg"],
            grantee_id="ra2",
            tender_id=TENDER_A,
            role="review_approver",
            owner_authorization_ref="AUTH-REF-001",
            register=REGISTER,
        )
    assert excinfo.value.reason == "operator_required"


def test_granting_reviewer_requires_the_reviewer_kind(env):
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(
            env.conn,
            configurer=env.users["cfg"],
            grantee_id="mem",
            tender_id=TENDER_A,
            role="review_approver",
            owner_authorization_ref="AUTH-REF-001",
            register=REGISTER,
        )
    assert excinfo.value.reason == "operator_required"


def test_grant_requires_an_authorization_reference(env):
    with pytest.raises(AuthzError):
        grant_membership(
            env.conn,
            configurer=env.users["cfg"],
            grantee_id="mem",
            tender_id=TENDER_A,
            role="member",
            owner_authorization_ref="   ",
            register=REGISTER,
        )


def test_viewer_role_may_be_granted_to_a_viewer(env):
    approval_id = grant_membership(
        env.conn,
        configurer=env.users["cfg"],
        grantee_id="view",
        tender_id=TENDER_A,
        role="viewer",
        owner_authorization_ref="AUTH-REF-001",
        register=REGISTER,
    )
    env.conn.commit()
    membership = env.conn.execute(
        "SELECT * FROM memberships WHERE user_id = 'view' AND tender_id = ?"
        " AND role = 'viewer'",
        (TENDER_A,),
    ).fetchone()
    assert membership["grant_approval_id"] == approval_id


def test_viewer_cannot_act_as_configurer(env):
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(
            env.conn,
            configurer=env.users["view"],
            grantee_id="mem",
            tender_id=TENDER_A,
            role="member",
            owner_authorization_ref="AUTH-REF-001",
            register=REGISTER,
        )
    assert excinfo.value.reason == "read_only"


@pytest.mark.parametrize("configurer, ref, tender", [
    ("pm", "AUTH-REF-001", TENDER_A),        # not the designated configuration account
    ("cfg", "AUTH-FAKE-999", TENDER_A),      # fabricated reference
    ("cfg", "AUTH-REF-001", "NT-2026-0002"), # record is for another tender
])
def test_grant_needs_a_matching_documented_authorization(env, configurer, ref, tender):
    env.conn.execute(
        "INSERT OR IGNORE INTO tenders (tender_id, title, issuing_entity, created_by, created_at)"
        " VALUES ('NT-2026-0002', 't', 'e', 'pm', ?)", (NOW,))
    with pytest.raises(AuthzError) as excinfo:
        grant_membership(env.conn, configurer=env.users[configurer], grantee_id="mem",
                         tender_id=tender, role="member", owner_authorization_ref=ref,
                         register=REGISTER)
    assert excinfo.value.reason == "no_authorization"
    assert env.conn.execute("SELECT COUNT(*) FROM memberships WHERE user_id='mem'").fetchone()[0] == 0
