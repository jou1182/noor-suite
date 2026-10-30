"""Write a verified public provenance marker after import."""

from __future__ import annotations

import json
from pathlib import Path

from noor_contracts.validate import validate

from . import DESTINATIONS, SnapshotError
from .fingerprint import check_label, exact_scans
from .verify import source_status, tree_matches_manifest


def _globs(repo: Path, platform: str) -> tuple[str, str]:
    allow = repo / "tools" / "snapshot" / "allowlists" / f"{platform}.txt"
    try:
        patterns = [line.strip() for line in allow.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    except OSError:
        raise SnapshotError("allowlist unavailable", 1) from None
    included = [pattern for pattern in patterns if not pattern.startswith("!")]
    excluded = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
    if not included:
        raise SnapshotError("allowlist empty", 1)
    return "\n".join(f"- {item}" for item in included), "\n".join(f"- {item}" for item in excluded) or "- none"


def run(repo: Path, platform: str) -> str:
    target = repo / DESTINATIONS[platform]
    source = target / "SOURCE.md"
    if source.exists():
        raise SnapshotError("SOURCE.md already exists", 1)
    manifest_file = repo / "platforms" / "_snapshots" / f"{platform}.json"
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        validate(manifest, "snapshot-manifest")
    except Exception:
        raise SnapshotError("manifest invalid or unavailable", 1) from None
    if manifest["platform_id"] != platform or not exact_scans(manifest["scans"]):
        raise SnapshotError("manifest invalid", 1)
    check_label(repo, manifest["source_label"])
    if not tree_matches_manifest(target, manifest):
        raise SnapshotError("destination tree mismatch", 1)
    included, excluded = _globs(repo, platform)
    try:
        template = (repo / "tools" / "snapshot" / "templates" / "SOURCE.template.md").read_text(encoding="utf-8")
    except OSError:
        raise SnapshotError("SOURCE.md template unavailable", 1) from None
    exposures = "\n".join(f"- {item}" for item in manifest["exposures_closed"]) or "- none"
    scans = "\n".join(f"- {item['tool']}: {item['result']} (version {item['version']})"
                      for item in manifest["scans"])
    content = template.format(source_label=manifest["source_label"], tree_sha256=manifest["tree_sha256"],
                              copied_at=manifest["copied_at"], file_count=len(manifest["files"]),
                              included=included, excluded=excluded, exposures_closed=exposures, scans=scans)
    source.write_text(content, encoding="utf-8")
    try:
        status = source_status(repo, target)
    except Exception:
        source.unlink()
        raise SnapshotError("SOURCE.md scan failed", 1) from None
    if status != "clean":
        source.unlink()
        raise SnapshotError(f"SOURCE.md: {status}", 1)
    return f"SOURCE.md: {status}"
