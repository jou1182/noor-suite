"""Local grant procedure for NMIS (T030). Synthetic data only.

    python -m noor_registry.grant creation   --configurer ID --grantee ID --owner-authorization-ref REF
    python -m noor_registry.grant membership --configurer ID --grantee ID --tender NT-YYYY-NNNN \
        --role {approver,member,viewer} --owner-authorization-ref REF

- Only the account designated in the local authorization register (NOOR_AUTHORIZATIONS_FILE,
  outside the repository) may configure, proven by its password read with getpass (never from argv
  or the environment). --configurer only names which account is trying.
- Every grant must match a documented record in that register: owner role, grantee, capability or
  role, and tender. A made-up REF is refused.
- No self grant, no viewer configurer, and (for creation) no viewer grantee.
- REF is an opaque reference to a documented owner authorization, never a person's name.
- review_approver grants stay disabled until gate T073; this tool cannot name an operator or
  enable an account.
- Every refusal prints the same generic message; nothing secret is ever printed.
"""

from __future__ import annotations

import argparse
import getpass
import re
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

from werkzeug.security import check_password_hash

from .authorizations import AuthorizationError, Register, load_register
from .authz import AuthzError, User, grant_membership, load_user, record_approval
from .config import Config, load_config
from .db import open_db, utc_now

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_DISABLED = 3

REPO_ROOT = Path(__file__).resolve().parents[3]
REF_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{3,64}$")
MEMBERSHIP_ROLES = ("approver", "member", "viewer")
REFUSED = "configuration refused"
DISABLED_MESSAGE = (
    "review_approver grants are disabled until gate T073 "
    "(owner authorization, named operator, retention period)"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m noor_registry.grant")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("creation", "membership"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--configurer", required=True)
        cmd.add_argument("--grantee", required=True)
        cmd.add_argument("--owner-authorization-ref", required=True)
        if name == "membership":
            cmd.add_argument("--tender", required=True)
            cmd.add_argument("--role", required=True)
    return parser


def _refuse(message: str = REFUSED) -> int:
    print(message, file=sys.stderr)
    return EXIT_REFUSED


def _authenticate(conn: sqlite3.Connection, user_id: str,
                  password_reader: Callable[[str], str]) -> User | None:
    """Return the configurer only if the account is usable and the password matches."""
    row = conn.execute("SELECT password_hash FROM users WHERE user_id = ?", (user_id,)).fetchone()
    user = load_user(conn, user_id)
    if row is None or user is None or not user.enabled or user.kind == "viewer":
        return None
    supplied = password_reader("Password: ")
    if not supplied or not check_password_hash(row["password_hash"], supplied):
        return None
    return user


def _grant_creation(conn: sqlite3.Connection, configurer: User, grantee: User, ref: str,
                    register: Register) -> str:
    """CreationGrant row + its permission_grant approval, in one transaction."""
    register.require(configurer_id=configurer.user_id, ref=ref, grantee=grantee.user_id,
                     capability="create_synthetic_tender")
    with conn:
        approval_id = record_approval(
            conn, actor=configurer, subject_type="permission_grant",
            subject_id=f"creation:{grantee.user_id}", decision="approved",
            acting_role="configuration",
        )
        conn.execute(
            "INSERT INTO creation_grants (user_id, capability, owner_authorization_ref,"
            " configured_by_user_id, granted_at, grant_approval_id, synthetic)"
            " VALUES (?, 'create_synthetic_tender', ?, ?, ?, ?, 1)",
            (grantee.user_id, ref, configurer.user_id, utc_now(), approval_id),
        )
    return approval_id


def main(argv: list[str] | None = None, *,
         password_reader: Callable[[str], str] = getpass.getpass,
         config_loader: Callable[[], Config] = load_config,
         register_loader: Callable[[], Register] | None = None) -> int:
    args = _parser().parse_args(argv)
    ref = args.owner_authorization_ref.strip()
    if not REF_PATTERN.fullmatch(ref):
        return _refuse()
    if args.command == "membership":
        if args.role == "review_approver":
            print(DISABLED_MESSAGE, file=sys.stderr)
            return EXIT_DISABLED
        if args.role not in MEMBERSHIP_ROLES:
            return _refuse()
    if args.configurer == args.grantee:
        return _refuse()

    try:
        register = (register_loader or (lambda: load_register(REPO_ROOT)))()
        conn = open_db(config_loader().data_dir)
    except Exception:  # register, config or database problems: same generic refusal
        return _refuse()
    try:
        configurer = _authenticate(conn, args.configurer, password_reader)
        grantee = load_user(conn, args.grantee)
        if configurer is None or grantee is None:
            return _refuse()
        if args.command == "creation":
            if grantee.kind == "viewer":
                return _refuse()
            exists = conn.execute(
                "SELECT 1 FROM creation_grants WHERE user_id = ?", (grantee.user_id,)
            ).fetchone()
            if exists:
                return _refuse("already granted")
            approval_id = _grant_creation(conn, configurer, grantee, ref, register)
        else:
            with conn:
                approval_id = grant_membership(
                    conn, configurer=configurer, grantee_id=grantee.user_id,
                    tender_id=args.tender.strip(), role=args.role,
                    owner_authorization_ref=ref, register=register,
                )
    except (AuthzError, AuthorizationError, sqlite3.Error):
        return _refuse()
    finally:
        conn.close()

    print(f"granted {args.command} to {grantee.user_id} (approval {approval_id})")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
