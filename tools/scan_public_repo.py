"""Public-repository and staging scanner. Standard library only.

Checks that a public repository receives no secrets, no local absolute paths, no session
identifiers in data files, and no names from a private blocklist kept OUTSIDE the repository.

    python tools/scan_public_repo.py --paths FILE_OR_DIR [FILE_OR_DIR ...]
    python tools/scan_public_repo.py --root STAGE --paths . --platform radar
    python tools/scan_public_repo.py --diff [REV]      # changed vs REV (default HEAD) + untracked
    python tools/scan_public_repo.py --history         # every blob reachable from any ref

Default output is opaque. --full is available only for this scanner's own repository. Private JSON reports
go to NOOR_PRIVATE_REPORTS_DIR. Blocklist: NOOR_BLOCKLIST_FILE (UTF-8, one entry per line).
Matched names are never printed, only their entry number. Exit: 0 clean, 1 findings, 2 config.
A narrow exception "scan:allow=<rule>" on a line silences only that rule on that line in
repository scans. Staging scans ignore inline exceptions. Secret and blocked-name rules can
never be silenced.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ALLOW_RE = re.compile(r"scan:allow=([a-z_.]+)")
NEVER_ALLOWED = ("secret.", "name.blocked")
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "graphify-out",
             ".ruff_cache", ".pytest_cache", ".pytest_tmp"}
SKIP_DIR_SUFFIXES = (".egg-info",)  # generated and git-ignored
GIT_TIMEOUT = 120
SCANNER_VERSION = "2.0.0"
TOOL_IDS = ("secrets_paths_ids", "forbidden_identities", "asset_metadata")
PLATFORMS = ("nmis_full", "radar", "quick_analysis", "atpas", "jouready")
PUBLIC_REPO = Path(__file__).resolve().parents[1]

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret.private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("secret.aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("secret.github", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("secret.openai_like", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("secret.slack", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("secret.assignment", re.compile(
        r"(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']", re.I)),
    ("path.windows", re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")),
    ("path.unc", re.compile(r"(?:^|[\s\"'])\\\\[A-Za-z0-9]")),
    ("path.file_uri", re.compile(r"file://", re.I)),  # scan:allow=path.file_uri
    ("path.posix_home", re.compile(r"/(?:home|Users|mnt|var|tmp)/")),
)
# "color_token" is the identity design-token key in labels files, not a credential.
DATA_RULE = ("data.session", re.compile(r"session|sid=|(?<!color_)token", re.I))
ARABIC_MARKS = re.compile(r"[ً-ْـ]")


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    masked: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} {self.masked}".rstrip()


class ConfigError(Exception):
    """Usage or configuration problem (exit code 2)."""


class OpaqueArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ConfigError("usage error")


@dataclass
class ScanReport:
    findings: list[Finding]
    binary_assets_for_visual_review: list[dict[str, str]]
    file_ids: dict[str, str]
    total_files: int
    file_hashes: dict[str, str] = field(default_factory=dict)

    def by_tool(self) -> dict[str, list[Finding]]:
        return {tool: [f for f in self.findings if tool_for_rule(f.rule) == tool] for tool in TOOL_IDS}


def tool_for_rule(rule: str) -> str:
    if rule in ("name.blocked", "name.blocked_path"):
        return "forbidden_identities"
    if rule.startswith("meta."):
        return "asset_metadata"
    return "secrets_paths_ids"


def is_data_file(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/")
    return (rel.startswith("samples/") or "/samples/" in rel
            or (rel.endswith(".json") and not rel.endswith(".schema.json"))
            or rel.endswith(".docx"))


def _normalise(text: str) -> str:
    return ARABIC_MARKS.sub("", text).casefold()


def _name_variants(name: str) -> set[str]:
    entry = _normalise(name)
    variants = {entry}
    if entry.startswith("ال"):
        stem = entry[2:]
        if len(stem) >= 4:
            variants.add(stem)
    if entry.isascii() and entry.isalpha():
        stem = entry[2:] if entry.startswith(("al", "el")) else entry
        if len(stem) >= 4:
            variants.update((stem, "al" + stem, "el" + stem))
    return variants


def _name_hits(text: str, blocklist: list[str]) -> list[int]:
    plain = _normalise(text)
    compact = re.sub(r"[\s\-_.]", "", plain)
    return [i for i, name in enumerate(blocklist, 1)
            if name.strip() and any(variant in plain or (variant.isascii() and variant in compact)
                                    for variant in _name_variants(name))]


def scan_text(text: str, rel_path: str, blocklist: list[str], *, allow_inline: bool = True) -> list[Finding]:
    """Scan one text; rel_path decides whether the data-file rule applies."""
    rules = RULES + ((DATA_RULE,) if is_data_file(rel_path) else ())
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        allowed = ({r for r in ALLOW_RE.findall(line) if not r.startswith(NEVER_ALLOWED)}
                   if allow_inline else set())
        for rule, pattern in rules:
            match = pattern.search(line)
            if match and rule not in allowed:
                findings.append(Finding(rule, rel_path, number, match.group(0)[:4] + "***"))
        for index in _name_hits(line, blocklist):
            findings.append(Finding("name.blocked", rel_path, number, f"#{index}"))
    return findings


def docx_text(data: bytes) -> str:
    """Text of EVERY part of a .docx: body, headers, footers, comments, notes, document properties
    and relationships. A part that is not XML (an image, an embedded file) cannot be scanned, so the
    whole file is refused, as are unsafe entry names and oversized content."""
    texts: list[str] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            name = info.filename
            if name.startswith(("/", "\\")) or ".." in name.split("/"):
                raise ValueError("unsafe entry name in docx")
            if name.endswith("/"):
                continue
            if not name.endswith((".xml", ".rels")):
                raise ValueError("docx contains a part that cannot be scanned")
            total += info.file_size
            if total > MAX_DOCX_XML_BYTES:
                raise ValueError("docx text parts too large")
            xml = archive.read(info).decode("utf-8", errors="replace")
            # Keep attribute values (relationship targets, metadata); one line per paragraph.
            # Close the tag around each attribute value so the tag stripper below keeps the value.
            xml = re.sub(r'\s[\w:]+="([^"]*)"', r"> \1 <", xml.replace("</w:p>", "</w:p>\n"))
            texts.append(re.sub(r"<[^>]*>", " ", xml))
    return "\n".join(texts)


def _metadata_text(data: bytes, suffix: str) -> tuple[str, str | None]:
    """Extract supported asset properties; return an unverifiable rule on parse failure."""
    if suffix in {".docx", ".pptx", ".xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return "\n".join(archive.read(part).decode("utf-8", "replace")
                                 for part in ("docProps/core.xml", "docProps/app.xml")
                                 if part in archive.namelist()), None
        except (zipfile.BadZipFile, OSError, ValueError):
            return "", "meta.unverifiable_office"
    if suffix == ".pdf":
        raw = data.decode("latin-1")
        if not raw.startswith("%PDF-") or "/Encrypt" in raw or "/ObjStm" in raw:
            return "", "meta.unverifiable_pdf"
        values = []
        def decode_pdf(value: bytes) -> str:
            if value.startswith((b"\xfe\xff", b"\xff\xfe")):
                return value.decode("utf-16", "replace")
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.decode("latin-1")
        for key in ("Author", "Title", "Subject", "Keywords", "Creator", "Producer"):
            for match in re.finditer(r"/" + key + r"\s*(\((?:\\.|[^\\)])*\)|<[0-9a-fA-F\s]+>)", raw):
                value = match.group(1)
                if value.startswith("<"):
                    try:
                        values.append(decode_pdf(bytes.fromhex(value[1:-1])))
                    except ValueError:
                        return "", "meta.unverifiable_pdf"
                else:
                    literal = value[1:-1].replace("\\)", ")").replace("\\(", "(")
                    values.append(decode_pdf(literal.encode("latin-1")))
        values += [decode_pdf(x.encode("latin-1")) for x in re.findall(
            r"<\?xpacket.*?<\?xpacket\s+end=.*?\?>|<x:xmpmeta.*?</x:xmpmeta>", raw, re.S)]
        return "\n".join(values), None
    if suffix == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "", "meta.unverifiable_image"
        pos, chunks, ended = 8, [], False
        try:
            while pos < len(data):
                if pos + 12 > len(data):
                    raise ValueError
                size = struct.unpack(">I", data[pos:pos + 4])[0]
                kind = data[pos + 4:pos + 8]
                payload = data[pos + 8:pos + 8 + size]
                crc = data[pos + 8 + size:pos + 12 + size]
                if len(payload) != size or len(crc) != 4 or struct.unpack(">I", crc)[0] != zlib.crc32(kind + payload):
                    raise ValueError
                if kind in (b"tEXt", b"iTXt", b"zTXt"):
                    if kind == b"zTXt":
                        payload = payload.split(b"\x00", 1)[0] + b" " + zlib.decompress(payload.split(b"\x00", 1)[1][1:])
                    elif kind == b"iTXt":
                        parts = payload.split(b"\x00", 5)
                        payload = parts[-1] if len(parts) >= 6 else payload
                        if len(parts) >= 6 and parts[1][:1] == b"\x01":
                            payload = zlib.decompress(payload)
                    chunks.append(payload.decode("utf-8", "replace"))
                pos += size + 12
                if kind == b"IEND":
                    ended = True
                    break
            if not ended:
                raise ValueError
        except (ValueError, IndexError, zlib.error):
            return "", "meta.unverifiable_image"
        return "\n".join(chunks), None
    if suffix in (".jpg", ".jpeg"):
        if not data.startswith(b"\xff\xd8"):
            return "", "meta.unverifiable_image"
        pos, chunks = 2, []
        try:
            while pos < len(data):
                if data[pos] != 0xff or pos + 1 >= len(data):
                    raise ValueError
                marker = data[pos + 1]
                if marker in (0xd9, 0xda):
                    break
                if pos + 4 > len(data):
                    raise ValueError
                size = struct.unpack(">H", data[pos + 2:pos + 4])[0]
                if size < 2 or pos + 2 + size > len(data):
                    raise ValueError
                if marker in (0xe1, 0xfe):
                    payload = data[pos + 4:pos + 2 + size]
                    chunks.extend((payload.decode("latin-1"), payload.decode("utf-8", "replace")))
                pos += 2 + size
        except (ValueError, struct.error):
            return "", "meta.unverifiable_image"
        return "\n".join(chunks), None
    return "", None


def scan_metadata(data: bytes, rel_path: str, blocklist: list[str]) -> list[Finding]:
    text, error = _metadata_text(data, Path(rel_path).suffix.lower())
    findings = [Finding(error, rel_path, 0, "")] if error else []
    for index in _name_hits(text, blocklist):
        findings.append(Finding("meta.blocked_name", rel_path, 0, f"#{index}"))
    return findings


def scan_blob(data: bytes, rel_path: str, blocklist: list[str],
              binary_allow: dict[str, str] | None = None, *, allow_inline: bool = True) -> list[Finding]:
    """Scan one file. A binary file passes only if its path and SHA-256 are in the allowlist."""
    path_only = rel_path.split("@")[0]
    if len(data) > MAX_FILE_BYTES:
        return [Finding("file.too_large", rel_path, 0, "")]
    if path_only.lower().endswith(".docx"):
        try:
            return scan_text(docx_text(data), rel_path, blocklist, allow_inline=allow_inline)
        except (zipfile.BadZipFile, ValueError):
            return [Finding("file.unscannable_docx", rel_path, 0, "")]
    # Text only for known text types that decode as strict UTF-8 with no NUL anywhere.
    # Everything else is binary: it passes only if its path and SHA-256 are pinned.
    if _is_text_name(path_only) and b"\x00" not in data:
        try:
            return scan_text(data.decode("utf-8"), rel_path, blocklist, allow_inline=allow_inline)
        except UnicodeDecodeError:
            pass
    expected = (binary_allow or {}).get(path_only) or (binary_allow or {}).get(path_only.casefold())
    if expected and hashlib.sha256(data).hexdigest() == expected:
        return []
    return [Finding("file.binary_unscanned", rel_path, 0, "")]


TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html",
                 ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".ps1", ".bat", ".cmd", ".sh",
                 ".csv", ".xml", ".sql", ".svg", ".example", ".lock", ".conf", ".env"}
TEXT_NAMES = {".gitignore", ".gitkeep", ".gitattributes", ".dockerignore", ".editorconfig",
              "Dockerfile", "LICENSE", "Makefile"}


def _is_text_name(path: str) -> bool:
    name = Path(path).name
    return name.casefold() in {item.casefold() for item in TEXT_NAMES} or Path(name).suffix.lower() in TEXT_SUFFIXES


def load_binary_allowlist(repo: Path) -> dict[str, str]:
    """tools/scan_allowlist.json: {"binary": {"<repo path>": "<sha256>"}} for documented assets."""
    path = repo / "tools" / "scan_allowlist.json"
    if not path.is_file():
        return {}
    return dict(json.loads(path.read_text(encoding="utf-8")).get("binary", {}))


def load_name_exemptions(repo: Path) -> list[str]:
    path = repo / "tools" / "scan_allowlist.json"
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("name_exempt_paths", []))


def _name_exempt(rel: str, exemptions: list[str]) -> bool:
    key = rel.casefold()
    return any(key.startswith(item.casefold()) if item.endswith("/") else key == item.casefold()
               for item in exemptions)


def _is_binary(data: bytes, rel: str) -> bool:
    suffix = Path(rel).suffix.lower()
    if suffix == ".docx":
        try:
            docx_text(data)
            return False
        except (zipfile.BadZipFile, ValueError):
            return True
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
                  ".pptx", ".xlsx", ".ttf", ".otf", ".woff", ".woff2"}:
        return True
    if not _is_text_name(rel) or b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def scan_tree(root: Path, blocklist: list[str], *, repo_exemptions: bool = False,
              paths: list[str] | None = None, repo: Path | None = None,
              forbidden_root: Path | None = None) -> ScanReport:
    """Scan files under root, optionally using repo-only name exemptions and binary pins."""
    root = root.resolve()
    repo = (repo or root).resolve()
    names = load_name_exemptions(repo) if repo_exemptions else []
    pins = {key.casefold(): value for key, value in load_binary_allowlist(repo).items()} if repo_exemptions else {}
    candidates: list[Path] = []
    walked: set[Path] = set()
    explicit: set[Path] = set()
    tracked: set[str] | None = set()
    if repo_exemptions:
        try:
            tracked = {item.decode("utf-8").replace("\\", "/").casefold()
                       for item in _git(repo, "ls-files", "-z", binary=True).split(b"\x00") if item}
        except (ConfigError, OSError, subprocess.TimeoutExpired):
            tracked = None  # Without git evidence, scan every directory.
    for raw in paths or ["."]:
        item = Path(raw)
        full = item if item.is_absolute() else root / item
        resolved = full.resolve()
        if not resolved.is_relative_to(root):
            raise ConfigError("scan path outside root")
        if forbidden_root and resolved.is_relative_to(forbidden_root):
            raise ConfigError("--full refused for staging scans")
        if full.is_symlink():
            candidates.append(full)
            explicit.add(full)
        elif full.is_dir():
            for folder, dirs, files in os.walk(full, followlinks=False):
                # A staging tree is fingerprinted whole, so it is scanned whole: skip nothing.
                def keep_dir(name: str, folder: str = folder) -> bool:
                    if not repo_exemptions or not _skipped(name) or tracked is None:
                        return True
                    rel_dir = (Path(folder) / name).relative_to(repo).as_posix().casefold() + "/"
                    return any(path.startswith(rel_dir) for path in tracked)
                dirs[:] = [d for d in dirs if keep_dir(d)]
                links = [Path(folder) / d for d in dirs if (Path(folder) / d).is_symlink()]
                candidates.extend(links)
                walked.update(links)
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
                entries = [Path(folder) / name for name in files]
                candidates.extend(entries)
                walked.update(entries)
        elif full.exists():
            candidates.append(full)
            explicit.add(full)
    findings: list[Finding] = []
    binary: list[dict[str, str]] = []
    ids: dict[str, str] = {}
    hashes: dict[str, str] = {}
    total = 0
    for full in sorted(set(candidates)):
        if forbidden_root and full.resolve().is_relative_to(forbidden_root):
            raise ConfigError("--full refused for staging scans")
        rel = full.relative_to(root).as_posix()
        if (repo_exemptions and tracked is not None and full in walked and full not in explicit and _skipped(rel)
                and rel.casefold() not in tracked):
            continue
        total += 1
        for index in sorted({hit for part in rel.split("/") for hit in _name_hits(part, blocklist)}):
            findings.append(Finding("name.blocked_path", rel, 0, f"#{index}"))
        if full.is_symlink():
            findings.append(Finding("file.symlink", rel, 0, ""))
            continue
        if not full.is_file():
            continue
        data = full.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        opaque_id = digest[:12]
        ids[rel] = opaque_id
        hashes[unicodedata.normalize("NFC", rel)] = digest
        if _is_binary(data, rel):
            binary.append({"path": rel, "opaque_id": opaque_id, "sha256": digest})
        blob_findings = scan_blob(data, rel, blocklist, pins, allow_inline=repo_exemptions)
        if repo_exemptions and _name_exempt(rel, names):
            blob_findings = [f for f in blob_findings if f.rule != "name.blocked"]
        findings.extend(blob_findings)
        metadata = scan_metadata(data, rel, blocklist)
        if repo_exemptions and _name_exempt(rel, names):
            metadata = [f for f in metadata if f.rule != "meta.blocked_name"]
        findings.extend(metadata)
    return ScanReport(findings, binary, ids, total, hashes)


def report_json(report: ScanReport) -> dict:
    return {"findings": [{"tool": tool_for_rule(f.rule), "rule": f.rule, "path": f.path,
                           "line": f.line, "masked": f.masked,
                           "opaque_id": report.file_ids.get(f.path)} for f in report.findings],
            "binary_assets_for_visual_review": report.binary_assets_for_visual_review,
            "total_files": report.total_files, "version": SCANNER_VERSION}


def opaque_summary(report: ScanReport) -> str:
    counts = Counter(f.rule for f in report.findings)
    lines = [f"{rule}: {count}" for rule, count in sorted(counts.items())]
    lines.append("finding file ids: " + ", ".join(sorted({report.file_ids[f.path] for f in report.findings
                                                               if f.path in report.file_ids})))
    lines.append(f"binary assets for review: {len(report.binary_assets_for_visual_review)}")
    lines.append(f"total files: {report.total_files}")
    lines.append(f"{len(report.findings)} finding(s)" if report.findings else "clean")
    return "\n".join(lines)


def _skipped(rel_path: str) -> bool:
    return any(part.casefold() in SKIP_DIRS or part.casefold().endswith(SKIP_DIR_SUFFIXES)
               for part in Path(rel_path).parts)


def _git(repo: Path, *args: str, binary: bool = False, stdin: bytes | None = None):
    # Fixed argv list (no shell); git is resolved from PATH on purpose.
    result = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        input=stdin, capture_output=True, timeout=GIT_TIMEOUT, check=False)
    if result.returncode != 0:
        raise ConfigError(f"git {args[0]} failed")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def load_blocklist(repo: Path, require: bool) -> list[str]:
    location = os.environ.get("NOOR_BLOCKLIST_FILE")
    if not location:
        if require:
            raise ConfigError("NOOR_BLOCKLIST_FILE is not set")
        print("WARNING: names not checked (NOOR_BLOCKLIST_FILE unset)", file=sys.stderr)
        return []
    path = Path(location).resolve()
    if path.is_relative_to(repo.resolve()):
        raise ConfigError("blocklist must live outside the repository")
    if not path.is_file():
        raise ConfigError("blocklist file not found")
    # utf-8-sig: Windows PowerShell 5.1 writes a BOM that would otherwise hide the first entry.
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def scan_paths(repo: Path, paths: list[str], blocklist: list[str],
               binary_allow: dict[str, str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for raw in paths:
        path = Path(raw)
        full = path if path.is_absolute() else repo / path
        try:
            rel = full.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            rel = path.name
        if not full.is_file():
            continue
        findings += scan_blob(full.read_bytes(), rel, blocklist, binary_allow)
    return findings


def changed_paths(repo: Path, rev: str) -> list[str]:
    changed = _git(repo, "diff", "--name-only", "--diff-filter=d", rev, "--").splitlines()
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(p for p in changed + untracked if p))


def scan_history(repo: Path, blocklist: list[str],
                 binary_allow: dict[str, str] | None = None,
                 report: ScanReport | None = None) -> list[Finding]:
    """Every blob reachable from any ref, once, reported as path@blob-prefix."""
    listing = _git(repo, "rev-list", "--all", "--objects").splitlines()
    blobs: dict[str, str] = {}
    for entry in listing:
        sha, _, name = entry.partition(" ")
        if name and sha not in blobs:
            blobs[sha] = name
    if not blobs:
        return []
    if report is not None:
        report.total_files = len(blobs)
    kinds = _git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                 stdin="\n".join(blobs).encode()).splitlines()
    findings: list[Finding] = []
    wanted = []
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ConfigError("git executable unavailable")
    git_executable = str(Path(git_executable).resolve())
    for line in kinds:
        sha, kind, size = line.split()
        if kind != "blob":
            continue
        if int(size) > MAX_FILE_BYTES:  # reported, never silently skipped
            rel = f"{blobs[sha]}@{sha[:10]}"
            findings.append(Finding("file.too_large", rel, 0, ""))
            if report is not None:
                digest = hashlib.sha256()
                process = subprocess.Popen(  # noqa: S603 - fixed git argv, no shell; sha comes from git object output
                    [git_executable, "-C", str(repo), "cat-file", "blob", sha],
                                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                if process.stdout is None:
                    raise ConfigError("git cat-file stdout unavailable")
                with process.stdout as stdout:
                    for chunk in iter(lambda: stdout.read(1024 * 1024), b""):
                        digest.update(chunk)
                if process.wait(timeout=GIT_TIMEOUT) != 0:
                    raise ConfigError("git cat-file failed")
                report.file_ids[rel] = digest.hexdigest()[:12]
        else:
            wanted.append(sha)
    exemptions = load_name_exemptions(repo)
    for sha in wanted:
        data = _git(repo, "cat-file", "blob", sha, binary=True)
        rel = f"{blobs[sha]}@{sha[:10]}"
        if report is not None:
            opaque_id = hashlib.sha256(data).hexdigest()[:12]
            report.file_ids[rel] = opaque_id
            if _is_binary(data, blobs[sha]):
                report.binary_assets_for_visual_review.append({"path": rel, "opaque_id": opaque_id})
        blob_findings = scan_blob(data, rel, blocklist, binary_allow)
        if _name_exempt(blobs[sha], exemptions):
            blob_findings = [f for f in blob_findings if f.rule != "name.blocked"]
        metadata = [Finding(f.rule, rel, f.line, f.masked)
                    for f in scan_metadata(data, blobs[sha], blocklist)]
        if _name_exempt(blobs[sha], exemptions):
            metadata = [f for f in metadata if f.rule != "meta.blocked_name"]
        for index in sorted({hit for part in blobs[sha].split("/") for hit in _name_hits(part, blocklist)}):
            findings.append(Finding("name.blocked_path", rel, 0, f"#{index}"))
        findings += blob_findings + metadata
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = OpaqueArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--paths", nargs="+")
    mode.add_argument("--diff", nargs="?", const="HEAD")
    mode.add_argument("--history", action="store_true")
    parser.add_argument("--require-blocklist", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--root")
    parser.add_argument("--platform", choices=PLATFORMS)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--opaque", action="store_true")
    output.add_argument("--full", action="store_true")
    try:
        args = parser.parse_args(argv)
        repo = Path(args.repo) if args.repo else Path(
            _git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
        root = Path(args.root).resolve() if args.root else repo.resolve()
        staging = os.environ.get("NOOR_STAGING_DIR")
        if args.full:
            if args.root or args.platform:
                raise ConfigError("--full requires repository root")
            if repo.resolve() != PUBLIC_REPO.resolve():
                raise ConfigError("--full requires scanner repository")
            git_root = Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
            if root != git_root:
                raise ConfigError("--full requires repository root")
        stage_root = Path(staging).resolve() if staging else None
        if args.full and (args.platform or (stage_root and (root.is_relative_to(stage_root)
                or stage_root.is_relative_to(root)))):
            raise ConfigError("--full refused for staging scans")
        if args.platform and not os.environ.get("NOOR_PRIVATE_REPORTS_DIR"):
            raise ConfigError("NOOR_PRIVATE_REPORTS_DIR is not set")
        private = os.environ.get("NOOR_PRIVATE_REPORTS_DIR")
        if private:
            private_root = Path(private).resolve()
            if private_root.is_relative_to(repo.resolve()) or (staging and private_root.is_relative_to(Path(staging).resolve())):
                raise ConfigError("NOOR_PRIVATE_REPORTS_DIR must be outside repository and staging")
        blocklist = load_blocklist(repo, args.require_blocklist or bool(args.platform))
        if args.history:
            report = ScanReport([], [], {}, 0)
            report.findings = scan_history(repo, blocklist, load_binary_allowlist(repo), report)
        else:
            selected = args.paths if args.paths else changed_paths(repo, args.diff)
            report = scan_tree(root, blocklist, repo_exemptions=not args.root,
                               paths=selected, repo=repo,
                               forbidden_root=stage_root if args.full else None)
        if private and (report.findings or report.binary_assets_for_visual_review):
            target = private_root / (args.platform or "repo")
            target.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            (target / f"scan-{timestamp}.json").write_text(
                json.dumps(report_json(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        print("scan error: file operation failed", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("scan error: operation timed out", file=sys.stderr)
        return 2
    except ConfigError as exc:
        print(f"scan error: {exc}", file=sys.stderr)
        return 2
    if args.full:
        for finding in report.findings:
            print(finding)
        print(f"{len(report.findings)} finding(s)" if report.findings else "clean")
    else:
        print(opaque_summary(report))
        if not private:
            print("details not written (NOOR_PRIVATE_REPORTS_DIR unset)", file=sys.stderr)
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
