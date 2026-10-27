"""Create a fresh demo database with the four synthetic accounts (T029).

Run: python -m noor_registry.seed [--reset]

- Passwords come from the environment through load_config(); nothing has a default.
- An existing database is never seeded in place. With --reset it is first copied to
  NOOR_DATA_DIR/backups/ (NMIS-R: copy before seeding), then a new database is created.
- No creation grant and no tender membership is created here: the proposal manager waits
  for the local grant procedure (T030), and the review approver stays disabled, with no
  operator label and no membership, until gate T073.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash

from .config import Config, load_config
from .db import DB_FILENAME, open_db
from .platforms_registry import load_platforms

# (user_id, kind, display_name, enabled)
ACCOUNTS = (
    ("pm", "proposal_manager", "مدير العروض (حساب مصطنع)", 1),
    ("ra", "review_approver", "معتمِد المراجعة (حساب مصطنع، معطّل)", 0),
    ("mem", "member", "عضو الفريق (حساب مصطنع)", 1),
    ("view", "viewer", "حساب العرض (للقراءة فقط)", 1),
)


class SeedError(RuntimeError):
    """Seeding refused; the message is safe to show."""


def backup_existing(data_dir: Path) -> Path | None:
    """Copy the current database to data_dir/backups/ with SQLite's online backup API."""
    db_path = data_dir / DB_FILENAME
    if not db_path.exists():
        return None
    backups = data_dir / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backups / f"{DB_FILENAME}.{stamp}"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def _remove_database(data_dir: Path) -> None:
    db_path = data_dir / DB_FILENAME
    for path in (db_path, db_path.with_name(DB_FILENAME + "-wal"),
                 db_path.with_name(DB_FILENAME + "-shm")):
        path.unlink(missing_ok=True)


def seed(config: Config, *, reset: bool = False) -> Path | None:
    """Create the database and the four accounts; return the backup path if one was made."""
    db_path = config.data_dir / DB_FILENAME
    backup = None
    if db_path.exists():
        if not reset:
            raise SeedError("a database already exists; use --reset to back it up and start over")
        backup = backup_existing(config.data_dir)
        _remove_database(config.data_dir)

    conn = open_db(config.data_dir, create=True)
    try:
        with conn:
            for user_id, kind, display_name, enabled in ACCOUNTS:
                conn.execute(
                    "INSERT INTO users (user_id, display_name, kind, shared, password_hash,"
                    " enabled, operator_label, synthetic) VALUES (?, ?, ?, 0, ?, ?, NULL, 1)",
                    (user_id, display_name, kind,
                     generate_password_hash(config.passwords[kind]), enabled),
                )
            for platform_id, item in load_platforms().items():
                conn.execute(
                    'INSERT INTO platform_entry (platform_id,display_name,upstream,browser_origin,run_state,maturity,provider_mode,demo_gate,snapshot_tree_sha256) VALUES (?,?,?,?,?,?,?,?,?)',
                    (platform_id, item['display_key'], item['upstream'], item['browser_origin'],
                     item['run_state'], item['maturity'], item['provider_mode'],
                     item['demo_gate'], item['snapshot_tree_sha256']))
    finally:
        conn.close()
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="noor_registry.seed", description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true",
                        help="back up the existing database, then create a new one")
    args = parser.parse_args(argv)
    try:
        backup = seed(load_config(), reset=args.reset)
    except SeedError as exc:
        print(f"seed refused: {exc}", file=sys.stderr)
        return 2
    if backup is not None:
        print(f"previous database backed up as backups/{backup.name}")
    print("created 4 synthetic accounts: " + ", ".join(a[0] for a in ACCOUNTS)
          + " (review approver disabled until gate T073)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
