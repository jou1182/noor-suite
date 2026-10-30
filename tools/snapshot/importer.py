"""Validate staged bytes outside the repo, then publish one directory."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import unicodedata
from pathlib import Path

from noor_contracts.validate import validate

from . import DESTINATIONS, SnapshotError, paths, read_state, write_json, write_state
from .fingerprint import check_label, check_sanitize_gate, exact_scans, inventory, tree_hash
from .verify import source_status, tree_matches_manifest


def _copy_verified_file(source: Path, destination: Path, record: dict) -> None:
    """Read staged bytes once and copy only bytes matching the manifest."""
    data = source.read_bytes()
    if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise SnapshotError("stage changed since fingerprint", 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def _reset_stage(private: Path, state: dict) -> None:
    state["status"] = "staged"
    state.pop("scan_hashes", None)
    write_state(private, state)


def run(repo: Path, platform: str, stamp: str) -> str:
    repo = repo.resolve()
    stage, private = paths(repo, platform, stamp)
    state = read_state(private)
    check_sanitize_gate(repo, platform, state)
    target = repo / DESTINATIONS[platform]
    manifest_path = repo / "platforms" / "_snapshots" / f"{platform}.json"
    unpublished = not target.exists() or all(
        p.name.casefold() == ".gitkeep" and p.is_file() and not p.stat().st_size
        for p in target.iterdir())
    if state.get("status") == "publishing" and unpublished:
        # Interrupted before the rename: nothing reached the public tree, so drop the
        # private sibling and an emptied destination, then import again from the start.
        shutil.rmtree(repo.parent / f".noor-import-{platform}-{stamp}", ignore_errors=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        state["status"] = "fingerprinted"
        state.pop("publishing_manifest", None)
        write_state(private, state)
    if state.get("status") == "publishing":
        manifest = state.get("publishing_manifest")
        try:
            validate(manifest, "snapshot-manifest")
            valid = (manifest["platform_id"] == platform and exact_scans(manifest["scans"])
                     and tree_matches_manifest(target, manifest))
        except Exception:
            valid = False
        if not valid:
            raise SnapshotError("published tree mismatch; remove the destination")
        check_label(repo, manifest["source_label"])
        write_json(manifest_path, manifest)
        state["status"] = "imported"
        state.pop("publishing_manifest", None)
        write_state(private, state)
        return f"imported\nfiles: {len(manifest['files'])}"
    if state.get("status") != "fingerprinted":
        raise SnapshotError("fingerprint required", 1)
    try:
        manifest = json.loads((private / "manifest.json").read_text(encoding="utf-8"))
        validate(manifest, "snapshot-manifest")
    except Exception:
        raise SnapshotError("manifest invalid", 1) from None
    if manifest["platform_id"] != platform or not exact_scans(manifest["scans"]):
        raise SnapshotError("manifest scans or platform invalid", 1)
    check_label(repo, manifest["source_label"])
    records = {item["path"]: item for item in manifest["files"]}
    if len(records) != len(manifest["files"]):
        raise SnapshotError("duplicate manifest path", 1)
    folded = [unicodedata.normalize("NFC", name).casefold() for name in records]
    if len(set(folded)) != len(folded):
        raise SnapshotError("colliding manifest paths", 1)
    if any(name.split("/", 1)[0].casefold() in ("source.md", ".gitkeep")
           or unicodedata.normalize("NFC", name) != name
           for name in records):
        raise SnapshotError("reserved or non-normalized manifest path", 1)
    sources: dict[str, Path] = {}
    for source in stage.rglob("*"):
        if source.is_symlink():
            raise SnapshotError("symlink in stage", 1)
        if source.is_file():
            name = unicodedata.normalize("NFC", source.relative_to(stage).as_posix())
            if name.casefold() in {key.casefold() for key in sources}:
                raise SnapshotError("colliding stage paths", 1)
            sources[name] = source
    if sources.keys() != records.keys():
        _reset_stage(private, state)
        raise SnapshotError("stage file set changed", 1)
    sibling = repo.parent / f".noor-import-{platform}-{stamp}"
    staging_root = Path(os.environ["NOOR_STAGING_DIR"]).resolve()
    if sibling.resolve().is_relative_to(repo) or sibling.resolve().is_relative_to(staging_root):
        raise SnapshotError("temporary import location invalid")
    if any(repo.parent.glob(".noor-import-*")):
        raise SnapshotError("temporary import exists; remove it before retrying")
    if manifest_path.exists():
        raise SnapshotError("manifest already exists")
    if target.exists():
        source_marker = target / "SOURCE.md"
        if source_marker.exists():
            if source_status(repo, target) == "findings":
                raise SnapshotError("SOURCE.md findings", 1)
            raise SnapshotError("move SOURCE.md aside before import")
        entries = list(target.iterdir())
        if not entries:
            raise SnapshotError("destination requires empty .gitkeep")
        if any(p.name.casefold() != ".gitkeep" for p in entries):
            raise SnapshotError("destination not empty")
        if len(entries) > 1 or entries and (not entries[0].is_file() or entries[0].stat().st_size):
            raise SnapshotError("destination marker not empty", 1)
    had_target = target.exists()
    had_marker = had_target and (target / ".gitkeep").is_file()
    created_sibling = False
    marker_removed = False
    publish_started = False
    try:
        sibling.mkdir(parents=True)
        created_sibling = True
        try:
            for name, record in records.items():
                _copy_verified_file(sources[name], sibling / name, record)
        except SnapshotError:
            _reset_stage(private, state)
            raise
        checked = inventory(sibling)
        hashes = {item["path"]: item["sha256"] for item in checked}
        if hashes != state.get("scan_hashes") or tree_hash(checked) != manifest["tree_sha256"]:
            _reset_stage(private, state)
            raise SnapshotError("stage changed since scan", 1)
        state["status"] = "publishing"
        state["publishing_manifest"] = manifest
        write_state(private, state)
        if target.exists():
            if had_marker:
                (target / ".gitkeep").unlink()
                marker_removed = True
            target.rmdir()
        target.parent.mkdir(parents=True, exist_ok=True)
        publish_started = True
        os.replace(sibling, target)
        write_json(manifest_path, manifest)
        state["status"] = "imported"
        state.pop("publishing_manifest", None)
        write_state(private, state)
    except Exception:
        if publish_started:
            manifest_path.unlink(missing_ok=True)
            if target.exists():
                shutil.rmtree(target)
        if marker_removed:
            target.mkdir(parents=True)
            if had_marker:
                (target / ".gitkeep").write_bytes(b"")
        if state.get("status") in ("publishing", "imported"):
            state["status"] = "fingerprinted"
            state.pop("publishing_manifest", None)
            write_state(private, state)
        raise
    finally:
        if created_sibling and sibling.exists():
            shutil.rmtree(sibling)
    return f"imported\nfiles: {len(records)}"
