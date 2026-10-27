"""Recompute imported destination digests without staging environment."""

from __future__ import annotations

import json
import os
from pathlib import Path

from noor_contracts.validate import validate
from tools import scan_public_repo as scanner

from . import DESTINATIONS, SnapshotError
from .fingerprint import exact_scans, inventory, tree_hash


def source_status(repo: Path, target: Path) -> str:
    """Scan the excluded provenance marker using repository scanner rules."""
    source = target / "SOURCE.md"
    if not source.exists():
        return "absent"
    names_set = bool(os.environ.get("NOOR_BLOCKLIST_FILE"))
    blocklist = scanner.load_blocklist(repo, True) if names_set else []
    report = scanner.scan_tree(target, blocklist, repo_exemptions=True,
                               paths=["SOURCE.md"], repo=repo)
    if report.findings:
        return "findings"
    return "clean" if names_set else "names-unchecked"


def tree_matches_manifest(target: Path, manifest: dict) -> bool:
    """Compare the destination tree and empty root marker with a manifest."""
    if not target.is_dir():
        return False
    actual = inventory(target, exclude_root_markers=True)
    expected = manifest["files"]
    marker = target / ".gitkeep"
    if marker.exists() and (not marker.is_file() or marker.stat().st_size):
        return False
    return ({(item["path"], item["size"], item["sha256"]) for item in actual}
            == {(item["path"], item["size"], item["sha256"]) for item in expected}
            and len(actual) == len(expected) and tree_hash(actual) == manifest["tree_sha256"])


def run(repo: Path, platform: str) -> tuple[str, int]:
    manifest_path = repo / "platforms" / "_snapshots" / f"{platform}.json"
    if not manifest_path.is_file():
        raise SnapshotError("manifest unavailable", 1)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate(manifest, "snapshot-manifest")
    except Exception:
        raise SnapshotError("manifest invalid", 1) from None
    if not exact_scans(manifest["scans"]):
        raise SnapshotError("manifest scans invalid", 1)
    if manifest["platform_id"] != platform:
        raise SnapshotError("manifest platform mismatch", 1)
    target = repo / DESTINATIONS[platform]
    source_result = source_status(repo, target)
    actual = inventory(target, exclude_root_markers=True) if target.is_dir() else []
    expected = {f["path"]: f["sha256"] for f in manifest["files"]}
    found = {f["path"]: f["sha256"] for f in actual}
    added, removed = found.keys() - expected.keys(), expected.keys() - found.keys()
    changed = {p for p in found.keys() & expected.keys() if found[p] != expected[p]}
    marker = target / ".gitkeep"
    marker_ok = not marker.exists() or marker.is_file() and marker.stat().st_size == 0
    match = (source_result not in ("findings", "names-unchecked") and marker_ok
             and not (added or removed or changed) and tree_matches_manifest(target, manifest))
    ids = sorted({found[p][:12] for p in changed})
    return (f"{'match' if match else 'mismatch'}\nadded: {len(added)}\nremoved: {len(removed)}"
            f"\nchanged: {len(changed)}\nchanged ids: {', '.join(ids)}"
            f"\nSOURCE.md: {source_result}", 0 if match else 1)


def all_manifests(repo: Path) -> tuple[str, int]:
    root = repo / "platforms" / "_snapshots"
    manifests = list(root.glob("*.json")) if root.is_dir() else []
    if not manifests:
        return "no snapshots", 0
    messages, codes = [], []
    for path in sorted(manifests):
        if path.stem not in DESTINATIONS:
            messages.append("invalid platform manifest")
            codes.append(1)
        else:
            message, code = run(repo, path.stem)
            messages.append(f"{path.stem}: {message}")
            codes.append(code)
    return "\n".join(messages), max(codes)
