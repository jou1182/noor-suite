"""Synthetic-only snapshot pipeline; owner runs it against reviewed staging inputs."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

PLATFORMS = ("nmis_full", "radar", "quick_analysis", "atpas", "jouready")
DESTINATIONS = {"nmis_full": "platforms/nmis/full", "radar": "platforms/radar",
                "quick_analysis": "platforms/quick-analysis", "atpas": "platforms/atpas",
                "jouready": "platforms/jouready"}
STAMP_RE = re.compile(r"^\d{8}-\d{4}$")


class SnapshotError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def paths(repo: Path, platform: str | None = None, stamp: str | None = None,
          *, staging: bool = True) -> tuple[Path, Path]:
    """Validate private roots against the explicit repository root."""
    if not staging:
        return repo, repo
    a = os.environ.get("NOOR_STAGING_DIR")
    b = os.environ.get("NOOR_PRIVATE_REPORTS_DIR")
    if not a:
        raise SnapshotError("NOOR_STAGING_DIR is not set")
    if not b:
        raise SnapshotError("NOOR_PRIVATE_REPORTS_DIR is not set")
    stage, reports, repo = Path(a).resolve(), Path(b).resolve(), repo.resolve()
    if stage.is_relative_to(repo) or reports.is_relative_to(repo):
        raise SnapshotError("private roots must be outside repository")
    if reports.is_relative_to(stage) or stage.is_relative_to(reports):
        raise SnapshotError("private roots must be separate")
    if platform not in PLATFORMS:
        raise SnapshotError("invalid platform")
    if stamp is not None and not STAMP_RE.fullmatch(stamp):
        raise SnapshotError("invalid stamp")
    return stage / platform / stamp if stamp else stage / platform, reports / platform / stamp if stamp else reports / platform


def read_state(folder: Path) -> dict:
    try:
        return json.loads((folder / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SnapshotError("private state unavailable") from None


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_state(folder: Path, state: dict) -> None:
    write_json(folder / "state.json", state)
