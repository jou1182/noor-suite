"""Allowlist selection with hard-coded forbidden source families."""

from __future__ import annotations

import re
from pathlib import Path

from . import SnapshotError, paths, read_state, write_json, write_state
from .fingerprint import inventory

ATPAS_LIBRARY_PATTERNS = ("atpas_library", ".atplib")
FORBIDDEN_DIRS = {"user data", "local storage", ".n8n", "n8n_workflows", "dist", "build", "output", "noor_private_reports"}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3",
                      ".sqlite-", ".ldb", ".atplib", ".xls", ".xlsx", ".xlsm", ".kdbx")
# Source files may be named after password features (e.g. a reset page); only data files go.
CODE_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".html", ".css")


def glob_match(path: str, pattern: str) -> bool:
    """POSIX glob: * and ? stay within a component; ** spans components."""
    result = []
    index = 0
    while index < len(pattern):
        if pattern[index:index + 2] == "**":
            result.append(".*")
            index += 2
        elif pattern[index] == "*":
            result.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            result.append("[^/]")
            index += 1
        else:
            result.append(re.escape(pattern[index]))
            index += 1
    return re.fullmatch("".join(result), path) is not None


def forbidden(rel: str) -> bool:
    parts = rel.casefold().split("/")
    name = parts[-1]
    if any(part.startswith("security_vault") for part in parts):
        return True
    if any(p in FORBIDDEN_DIRS or p == ATPAS_LIBRARY_PATTERNS[0] for p in parts[:-1]):
        return True
    return (name.startswith(".env") and name != ".env.example"
            or name.startswith(("id_rsa", "id_ed25519", "security_vault"))
            or name == "database.sqlite"
            or ("password" in name or "passwd" in name) and not name.endswith(CODE_SUFFIXES)
            or name.startswith("scan-") and name.endswith(".json")
            or any(name.endswith(s) or (s == ".sqlite-" and s in name) for s in FORBIDDEN_SUFFIXES)
            or len(parts) >= 2 and parts[-2] == "default" and name == "cookies")


def run(repo: Path, platform: str, stamp: str) -> str:
    target, private = paths(repo, platform, stamp)
    state = read_state(private)
    allow = repo / "tools" / "snapshot" / "allowlists" / f"{platform}.txt"
    if not allow.is_file():
        raise SnapshotError("allowlist unavailable")
    globs = [s.strip() for s in allow.read_text(encoding="utf-8").splitlines()
             if s.strip() and not s.lstrip().startswith("#")]
    included = [pattern for pattern in globs if not pattern.startswith("!")]
    excluded = [pattern[1:] for pattern in globs if pattern.startswith("!")]
    if not included or any(not pattern for pattern in excluded):
        raise SnapshotError("allowlist empty")
    kept = removed = barred = 0
    report = {"kept": [], "removed_not_allowlisted": [], "removed_forbidden": []}
    for file in list(target.rglob("*")):  # materialise: the loop deletes files
        if file.is_symlink():
            report["removed_forbidden"].append(file.relative_to(target).as_posix())
            file.unlink()
            barred += 1
            continue
        if not file.is_file():
            continue
        rel = file.relative_to(target).as_posix()
        if forbidden(rel):
            file.unlink()
            barred += 1
            report["removed_forbidden"].append(rel)
        elif (any(glob_match(rel, pattern) for pattern in included)
              and not any(glob_match(rel, pattern) for pattern in excluded)):
            kept += 1
            report["kept"].append(rel)
        else:
            file.unlink()
            removed += 1
            report["removed_not_allowlisted"].append(rel)
    for folder in sorted((p for p in target.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    current = {f["path"]: f["sha256"] for f in inventory(target)}
    if removed or barred or (state.get("scan_hashes") is not None and current != state["scan_hashes"]):
        state["status"] = "staged"
        state.pop("scan_hashes", None)
        write_state(private, state)
    write_json(private / "selection.json", report)
    return f"kept: {kept}\nremoved_not_allowlisted: {removed}\nremoved_forbidden: {barred}"
