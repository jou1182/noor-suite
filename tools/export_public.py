"""Copy the Noor suite (specs 001/002 work only) into a fresh public folder.

    python tools/export_public.py --out ../noor-suite-public --include-untracked

Only paths on INCLUDE are copied. Untracked files require explicit review, and the private
blocklist must be supplied outside this repository. The output must be outside the repository.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

try:
    from tools.name_replacement import replacement_pattern as shared_replacement_pattern
except ModuleNotFoundError:  # direct script entry point
    from name_replacement import replacement_pattern as shared_replacement_pattern

REPO = Path(__file__).resolve().parents[1]
SCANNER_SPEC = importlib.util.spec_from_file_location("noor_export_scanner", REPO / "tools/scan_public_repo.py")
if SCANNER_SPEC is None or SCANNER_SPEC.loader is None:
    raise RuntimeError("public scanner is unavailable")
scanner = importlib.util.module_from_spec(SCANNER_SPEC)
sys.modules[SCANNER_SPEC.name] = scanner
SCANNER_SPEC.loader.exec_module(scanner)
INCLUDE = (
    ".github/workflows/noor-v2.yml", ".gitignore", ".opencode/", ".specify/", "README.md",
    "LICENSE", "THIRD_PARTY_LICENSES.md", "pyproject.toml", "config/", "launcher/", "packages/",
    "platforms/", "samples/", "specs/", "tests/e2e/", "tests/support/", "tools/",
)
ARABIC = re.compile("[\u0600-\u06ff]")
ARABIC_LETTERS = "\u0621-\u064a\u0671-\u06d3"
PUBLIC_WORDING = (
    (re.compile(r"«?الهوية السابقة»?\s*[،,/و]\s*«?الهوية السابقة»?\s*[،,/و]\s*(و\s*)?`?former-identity`?"),
     "أسماء الهوية السابقة (العربية واللاتينية)"),
    (re.compile("هوية الهوية السابقة"), "الهوية السابقة"),
    (re.compile("«الهوية السابقة» مضمَّن"), "اسم الهوية السابقة مضمَّن"),
)


def selected(files: list[str]) -> list[str]:
    return sorted(f for f in files
                  if any(f == p or (p.endswith("/") and f.startswith(p)) for p in INCLUDE))


def git_files(repo: Path, *options: str) -> list[str]:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(repo), "ls-files", "-z", *options],  # noqa: S607
        capture_output=True, check=True, timeout=120)
    return [f for f in result.stdout.decode("utf-8").split("\0") if f]


def blocklist() -> list[str]:
    location = os.environ.get("NOOR_BLOCKLIST_FILE")
    if not location:
        raise ValueError("NOOR_BLOCKLIST_FILE is required")
    names = [line.strip() for line in Path(location).read_text(encoding="utf-8-sig").splitlines()]
    names = [name for name in names if name and not name.startswith("#")]
    if not names:
        raise ValueError("NOOR_BLOCKLIST_FILE has no entries")
    return sorted(names, key=len, reverse=True)


def is_link(path: Path) -> bool:
    # Python 3.11 has no Path.is_junction; Windows marks junctions as reparse points.
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)) or path.is_symlink()


def safe_file(repo: Path, rel: str) -> Path:
    root = repo.resolve()
    path = repo
    for part in Path(rel).parts:
        path = path / part
        if is_link(path):
            raise ValueError("selected path contains a link or junction")
        if not path.resolve().is_relative_to(root):
            raise ValueError("selected path escapes repository")
    if not path.is_file():
        raise ValueError("selected path is not a regular file")
    return path


def text_content(data: bytes) -> tuple[str, bytes] | None:
    if any(byte < 32 and byte not in (9, 10, 12, 13) for byte in data):
        return None
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    try:
        return data[len(bom):].decode("utf-8"), bom
    except UnicodeDecodeError:
        return None


def replacement_pattern(names: list[str]) -> tuple[re.Pattern[str], dict[str, str]]:
    return shared_replacement_pattern(names, "الهوية السابقة", "former-identity")


def replace_names(out: Path, files: list[str], names: list[str]) -> tuple[int, int, int]:
    replacements = cleanups = changed = 0
    pattern, values = replacement_pattern(names)
    for rel in files:
        path = out / rel
        content = text_content(path.read_bytes())
        if content is None:
            continue
        value, bom = content
        value, count = pattern.subn(lambda match: values[match.lastgroup], value)
        replacements += count
        file_cleanups = 0
        # Only files that held a name: the exporter and its tests contain these phrases verbatim.
        for wording, replacement in PUBLIC_WORDING if count else ():
            value, amount = wording.subn(replacement, value)
            file_cleanups += amount
        cleanups += file_cleanups
        if count or file_cleanups:
            path.write_bytes(bom + value.encode("utf-8"))
            changed += 1
    return replacements, cleanups, changed


def verify_names(out: Path, files: list[str], names: list[str]) -> None:
    for rel in files:
        if any(scanner._name_hits(part, names) for part in Path(rel).parts):
            raise ValueError("blocked name remains in exported path")
        content = text_content((out / rel).read_bytes())
        if content and scanner._name_hits(content[0], names):
            raise ValueError("blocked name remains in exported text")


def scan_export(repo: Path, out: Path) -> None:
    for rel in ("tools/scan_public_repo.py", "tools/scan_allowlist.json"):
        if (out / rel).read_bytes() != (repo / rel).read_bytes():
            raise ValueError("exported scanner files differ from source")
    entries = sorted(path.name for path in out.iterdir())
    result = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell
        [sys.executable, str(repo / "tools/scan_public_repo.py"), "--repo", str(out),
         "--require-blocklist", "--opaque", "--paths", *entries],
        cwd=out, check=False, timeout=120)
    if result.returncode:
        raise ValueError("public repository scan failed")


def export(repo: Path, out: Path, *, include_untracked: bool = False) -> int:
    repo = repo.resolve()
    out = out.absolute()
    if os.path.lexists(out):
        raise ValueError("output folder already exists")
    if out.resolve().is_relative_to(repo):
        raise ValueError("output folder must be outside the repository")
    names = blocklist()
    files = selected(git_files(repo, "--cached", "--others", "--exclude-standard"))
    sources = {rel: safe_file(repo, rel) for rel in files}
    untracked = sorted(set(files) & set(git_files(repo, "--others", "--exclude-standard")))
    manifest = Path(str(out) + ".untracked.txt")
    manifest.write_text("".join(rel + "\n" for rel in untracked), encoding="utf-8")
    print(f"untracked files: {len(untracked)}; review list: {manifest}")
    if untracked and not include_untracked:
        raise ValueError("untracked files require --include-untracked")
    created = False
    try:
        out.mkdir()
        created = True
        for rel, source in sources.items():
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        count, cleanups, changed = replace_names(out, files, names)
        print(f"name replacements: {count}; files changed: {changed}")
        print(f"wording cleanups: {cleanups}")
        verify_names(out, files, names)
        scan_export(repo, out)
        return len(files)
    except BaseException:
        if created:
            shutil.rmtree(out)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--include-untracked", action="store_true")
    args = parser.parse_args(argv)
    try:
        count = export(REPO, Path(args.out), include_untracked=args.include_untracked)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"export error: {exc}", file=sys.stderr)
        return 1
    print(f"exported files: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
