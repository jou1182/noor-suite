"""File inventory, exact tree digest, and schema-validated manifest."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

from noor_contracts.validate import validate

from tools.scan_public_repo import SCANNER_VERSION, TOOL_IDS

from . import SnapshotError, paths, read_state, write_json, write_state


def inventory(root: Path, *, exclude_root_markers: bool = False) -> list[dict]:
    files = []
    for file in root.rglob("*"):
        if file.is_symlink():
            raise SnapshotError("symlink in tree", 1)
        if not file.is_file():
            continue
        rel = file.relative_to(root).as_posix()
        if exclude_root_markers and rel in ("SOURCE.md", ".gitkeep"):
            continue
        data = file.read_bytes()
        files.append({"path": unicodedata.normalize("NFC", rel), "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})
    if len({x["path"].casefold() for x in files}) != len(files):
        raise SnapshotError("colliding normalized paths", 1)
    return sorted(files, key=lambda x: x["path"])


def tree_hash(files: list[dict]) -> str:
    listing = "".join(f"{f['path']}\t{f['size']}\t{f['sha256']}\n"
                      for f in sorted(files, key=lambda x: x["path"]))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def exact_scans(scans: list[dict]) -> bool:
    """The schema permits duplicates, but the pipeline requires each tool exactly once."""
    return len(scans) == 3 and {item.get("tool") for item in scans} == set(TOOL_IDS) and len(set(TOOL_IDS)) == 3


def check_scanned(target: Path, private: Path, state: dict) -> list[dict]:
    files = inventory(target)
    hashes = {f["path"]: f["sha256"] for f in files}
    if hashes != state.get("scan_hashes"):
        state["status"] = "staged"
        state.pop("scan_hashes", None)
        write_state(private, state)
        raise SnapshotError("stage changed since scan", 1)
    return files


def run(repo: Path, platform: str, stamp: str, source_label: str,
        source_commit: str | None, exposures: list[str], reviewed_by: str) -> str:
    target, private = paths(repo, platform, stamp)
    state = read_state(private)
    if state.get("status") != "scanned":
        raise SnapshotError("scan required", 1)
    files = check_scanned(target, private, state)
    if any("visual" not in state.get("approvals", {}).get(digest, {})
           for digest in state.get("binary_hashes", [])):
        raise SnapshotError("binary review approvals required", 1)
    manifest = {"schema": "noor.snapshot-manifest/v1", "platform_id": platform,
                "source_label": source_label, "source_commit": source_commit,
                "copied_at": state["copied_at"], "files": files, "tree_sha256": tree_hash(files),
                "scans": [{"tool": tool, "version": SCANNER_VERSION,
                           "result": state["tool_results"][tool], "at": state["scanned_at"]}
                          for tool in TOOL_IDS], "exposures_closed": exposures,
                "binary_assets_reviewed_by": reviewed_by, "synthetic_data_only": True}
    try:
        validate(manifest, "snapshot-manifest")
    except Exception:
        raise SnapshotError("manifest validation failed") from None
    if not exact_scans(manifest["scans"]):
        raise SnapshotError("manifest scans invalid")
    write_json(private / "manifest.json", manifest)
    state["status"] = "fingerprinted"
    write_state(private, state)
    return f"fingerprinted\nfiles: {len(files)}"
