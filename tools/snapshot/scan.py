"""Three-tool scan of a private stage; detailed findings remain private."""

from __future__ import annotations

import re
from pathlib import Path

from tools import scan_public_repo as scanner

from . import SnapshotError, now, paths, read_state, write_json, write_state
from .fingerprint import inventory

OPAQUE_RE = re.compile(r"^([0-9a-f]{64})\s+(visual|path|session)\s+(.+)$")
HARD_STOPS = ("secret.", "name.blocked", "meta.blocked_name", "meta.unverifiable_",
              "file.too_large", "file.unscannable_docx", "file.symlink")
VISUAL_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
                   ".ttf", ".otf", ".woff", ".woff2"}


def _approved(state: dict, finding: scanner.Finding, report: scanner.ScanReport) -> bool:
    if finding.rule == "file.binary_unscanned" and Path(finding.path).suffix.casefold() not in VISUAL_SUFFIXES:
        return False
    kind = ("visual" if finding.rule == "file.binary_unscanned" else
            "path" if finding.rule.startswith("path.") else
            "session" if finding.rule == "data.session" else None)
    return (not finding.rule.startswith(HARD_STOPS)
            and kind is not None
            and kind in state.get("approvals", {}).get(report.file_hashes.get(finding.path), {}))


def run(repo: Path, platform: str, stamp: str) -> tuple[str, int]:
    target, private = paths(repo, platform, stamp)
    state = read_state(private)
    blocklist = scanner.load_blocklist(repo, True)
    report = scanner.scan_tree(target, blocklist, repo_exemptions=False)
    write_json(private / f"scan-{now().replace(':', '').replace('+', '-')}.json", scanner.report_json(report))
    results = {}
    for tool, findings in report.by_tool().items():
        results[tool] = ("clean" if not findings else
                         "findings_resolved" if all(_approved(state, f, report) for f in findings)
                         else "failed")
    try:
        current = {f["path"]: f["sha256"] for f in inventory(target)}
    except SnapshotError:
        current = None
    if current != report.file_hashes:
        state["status"] = "staged"
        state.pop("scan_hashes", None)
        write_state(private, state)
        return scanner.opaque_summary(report) + "\nscan changed during scan", 1
    state["scan_hashes"] = dict(report.file_hashes)
    state["binary_hashes"] = sorted({asset["sha256"] for asset in report.binary_assets_for_visual_review})
    state["tool_results"] = results
    state["scanned_at"] = now()
    state["status"] = "scanned" if "failed" not in results.values() else "staged"
    write_state(private, state)
    return scanner.opaque_summary(report), 0 if state["status"] == "scanned" else 1


def mark(repo: Path, platform: str, stamp: str, list_file: str) -> str:
    target, private = paths(repo, platform, stamp)
    state = read_state(private)
    approved: dict[str, dict[str, dict[str, str]]] = {}
    approved_at = now()
    # utf-8-sig: Windows PowerShell 5.1 writes a BOM with -Encoding UTF8.
    for line in Path(list_file).read_text(encoding="utf-8-sig").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        match = OPAQUE_RE.fullmatch(item)
        if not match or len(match.group(3).strip()) < 3:
            raise SnapshotError("invalid approval record")
        digest, kind, reason = match.groups()
        approved.setdefault(digest, {})[kind] = {"reason": reason.strip(), "at": approved_at}
    present = {f["sha256"] for f in inventory(target)}
    state["approvals"] = approved
    state["approved_at"] = approved_at
    write_state(private, state)
    return f"approved ids: {len(approved)}\nids absent from stage: {len(approved.keys() - present)}"
