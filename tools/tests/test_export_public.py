"""Public export checks use only disposable repositories and synthetic blocklists."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "export_public", Path(__file__).resolve().parents[1] / "export_public.py"
)
assert SPEC and SPEC.loader
export_public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_public)
REAL_SCAN_EXPORT = export_public.scan_export


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    blocklist = tmp_path / "names.txt"
    blocklist.write_text("# synthetic only\nOldBrand\nقديم\n", encoding="utf-8-sig")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(blocklist))
    monkeypatch.setattr(export_public, "scan_export", lambda _repo, _out: None)
    return repo, tmp_path / "public"


def add(repo: Path, rel: str, data: bytes, *, tracked: bool = True) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if tracked:
        subprocess.run(["git", "-C", str(repo), "add", "--", rel], check=True)
    return path


def test_untracked_gate_and_review_list(source, capsys):
    repo, out = source
    add(repo, "README.md", b"tracked")
    add(repo, "packages/new.txt", b"untracked", tracked=False)
    with pytest.raises(ValueError, match="include-untracked"):
        export_public.export(repo, out)
    assert not out.exists()
    assert (repo.parent / "public.untracked.txt").read_text(encoding="utf-8") == "packages/new.txt\n"
    output = capsys.readouterr().out
    assert "untracked files: 1" in output
    assert "packages/new.txt" not in output
    assert export_public.export(repo, out, include_untracked=True) == 2
    assert (out / "packages/new.txt").read_bytes() == b"untracked"


def test_replacement_preserves_bom_crlf_and_binary(source):
    repo, out = source
    original = b"\xef\xbb\xbf" + "OLDBRAND\r\nقديم\r\n".encode("utf-8")
    add(repo, "README.md", original)
    binary = b"\x00\xffOldBrand\r\n"
    add(repo, "packages/blob.bin", binary)
    export_public.export(repo, out)
    assert (out / "README.md").read_bytes() == b"\xef\xbb\xbf" + (
        "former-identity\r\nالهوية السابقة\r\n".encode("utf-8")
    )
    assert (out / "packages/blob.bin").read_bytes() == binary
    assert (repo / "README.md").read_bytes() == original


def test_longer_names_first(source, monkeypatch):
    repo, out = source
    (repo.parent / "names.txt").write_text("Old\nOldBrand\n", encoding="utf-8")
    add(repo, "README.md", b"OldBrand")
    export_public.export(repo, out)
    assert (out / "README.md").read_text() == "former-identity"


def test_arabic_stem_and_diacritics(source):
    repo, out = source
    (repo.parent / "names.txt").write_text("السنديان\n", encoding="utf-8")
    add(repo, "README.md", "سنديان الْسنديان سِنْدَيَان".encode("utf-8"))
    export_public.export(repo, out)
    result = (out / "README.md").read_text(encoding="utf-8")
    assert result == "الهوية السابقة الهوية السابقة الهوية السابقة"
    assert not export_public.scanner._name_hits(result, ["السنديان"])


def test_latin_stem_and_separated_variants(source):
    repo, out = source
    (repo.parent / "names.txt").write_text("alsindyan\n", encoding="utf-8")
    add(repo, "README.md", b"SiNdYaN eL-sInDyAn AL_SINDYAN")
    export_public.export(repo, out)
    result = (out / "README.md").read_text(encoding="utf-8")
    assert result == "former-identity former-identity former-identity"
    assert not export_public.scanner._name_hits(result, ["alsindyan"])


@pytest.mark.parametrize(("original", "expected"), [
    ("هوية الهوية السابقة", "الهوية السابقة"),
    ("«الهوية السابقة» و«الهوية السابقة» و`former-identity`",
     "أسماء الهوية السابقة (العربية واللاتينية)"),
    ("«الهوية السابقة»، «الهوية السابقة»، `former-identity`",
     "أسماء الهوية السابقة (العربية واللاتينية)"),
    ("الهوية السابقة، الهوية السابقة، `former-identity`",
     "أسماء الهوية السابقة (العربية واللاتينية)"),
    ("الهوية السابقة/الهوية السابقة/`former-identity`",
     "أسماء الهوية السابقة (العربية واللاتينية)"),
    ("**الهوية السابقة:** «الهوية السابقة» مضمَّن",
     "**الهوية السابقة:** اسم الهوية السابقة مضمَّن"),
])
def test_public_wording_examples(source, original, expected):
    _repo, out = source
    out.mkdir()
    (out / "README.md").write_text(original + " alsindyan", encoding="utf-8")
    replacements, cleanups, changed = export_public.replace_names(out, ["README.md"], ["alsindyan"])
    assert (replacements, cleanups, changed) == (1, 1, 1)
    assert (out / "README.md").read_text(encoding="utf-8") == expected + " former-identity"


def test_public_wording_skips_files_without_names(source):
    _repo, out = source
    out.mkdir()
    (out / "README.md").write_text("هوية الهوية السابقة", encoding="utf-8")
    assert export_public.replace_names(out, ["README.md"], ["alsindyan"]) == (0, 0, 0)
    assert (out / "README.md").read_text(encoding="utf-8") == "هوية الهوية السابقة"


def test_boundaries_fail_closed_for_embedded_variants(source):
    repo, out = source
    (repo.parent / "names.txt").write_text("alsindyan\nالسنديان\n", encoding="utf-8")
    add(repo, "README.md", "prealsindyanpost وسنديانx".encode("utf-8"))
    with pytest.raises(ValueError, match="exported text"):
        export_public.export(repo, out)
    assert not out.exists()


def test_multiline_variant_is_not_replaced_but_fails_verification(source):
    """The scanner compacts newlines; replacement must preserve the CRLF and fail closed."""
    _repo, out = source
    out.mkdir()
    original = b"sin\r\ndyan"
    (out / "README.md").write_bytes(original)
    assert export_public.replace_names(out, ["README.md"], ["alsindyan"]) == (0, 0, 0)
    assert (out / "README.md").read_bytes() == original
    with pytest.raises(ValueError, match="exported text"):
        export_public.verify_names(out, ["README.md"], ["alsindyan"])


def test_variant_in_path_removes_output(source):
    repo, out = source
    (repo.parent / "names.txt").write_text("alsindyan\n", encoding="utf-8")
    add(repo, "specs/El-Sindyan/notes.txt", b"safe")
    with pytest.raises(ValueError, match="exported path"):
        export_public.export(repo, out)
    assert not out.exists()


def test_scan_uses_source_scanner_in_repository_mode(source, monkeypatch):
    repo, out = source
    out.mkdir()
    (out / "README.md").write_text("safe")
    for rel in ("tools/scan_public_repo.py", "tools/scan_allowlist.json"):
        path = add(repo, rel, b"reviewed content")
        exported = out / rel
        exported.parent.mkdir(parents=True, exist_ok=True)
        exported.write_bytes(path.read_bytes())
    calls = []

    def capture(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(export_public, "scan_export", REAL_SCAN_EXPORT)
    monkeypatch.setattr(export_public.subprocess, "run", capture)
    export_public.scan_export(repo, out)
    argv, kwargs = calls[0]
    assert argv == [export_public.sys.executable, str(repo / "tools/scan_public_repo.py"),
                    "--repo", str(out), "--require-blocklist", "--opaque", "--paths",
                    "README.md", "tools"]
    assert "--root" not in argv
    assert kwargs["cwd"] == out


def test_scan_refuses_modified_exported_scanner(source, monkeypatch):
    repo, out = source
    out.mkdir()
    for rel in ("tools/scan_public_repo.py", "tools/scan_allowlist.json"):
        path = add(repo, rel, b"reviewed content")
        exported = out / rel
        exported.parent.mkdir(parents=True, exist_ok=True)
        exported.write_bytes(path.read_bytes())
    (out / "tools/scan_allowlist.json").write_bytes(b"modified")
    monkeypatch.setattr(export_public, "scan_export", REAL_SCAN_EXPORT)
    with pytest.raises(ValueError, match="differ from source"):
        export_public.scan_export(repo, out)


def test_linked_file_refused(source):
    repo, out = source
    outside = repo.parent / "outside.txt"
    outside.write_text("outside")
    link = repo / "README.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    with pytest.raises(ValueError, match="link or junction"):
        export_public.export(repo, out)
    assert not out.exists()


def test_linked_parent_refused(source):
    repo, out = source
    outside = repo.parent / "outside"
    outside.mkdir()
    (outside / "data.txt").write_text("outside")
    link = repo / "packages"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    # Git does not enumerate children of a directory link; inject a selected path to
    # exercise the path validation independently of Git's enumeration.
    with pytest.raises(ValueError, match="link or junction"):
        export_public.safe_file(repo, "packages/data.txt")


def test_resolved_outside_refused(source, monkeypatch):
    repo, _out = source
    add(repo, "README.md", b"safe")
    real_resolve = Path.resolve

    def escaped(path: Path, *args, **kwargs):
        if path == repo / "README.md":
            return repo.parent / "outside.txt"
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escaped)
    with pytest.raises(ValueError, match="escapes repository"):
        export_public.safe_file(repo, "README.md")


def test_failed_scan_removes_output(source, monkeypatch):
    repo, out = source
    add(repo, "README.md", b"safe")

    def fail(_repo, _out):
        raise ValueError("scan failed")

    monkeypatch.setattr(export_public, "scan_export", fail)
    with pytest.raises(ValueError, match="scan failed"):
        export_public.export(repo, out)
    assert not out.exists()


def test_output_inside_repo_refused(source):
    repo, _out = source
    add(repo, "README.md", b"safe")
    with pytest.raises(ValueError, match="outside the repository"):
        export_public.export(repo, repo / "public")
    assert not (repo / "public").exists()


def test_existing_output_refused(source):
    repo, out = source
    add(repo, "README.md", b"safe")
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        export_public.export(repo, out)
    assert (out / "keep.txt").read_text() == "keep"


def test_missing_or_empty_blocklist_refused(source, monkeypatch):
    repo, out = source
    add(repo, "README.md", b"safe")
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE")
    with pytest.raises(ValueError, match="required"):
        export_public.export(repo, out)
    assert not out.exists()
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(repo.parent / "names.txt"))
    (repo.parent / "names.txt").write_text("# no entries\n")
    with pytest.raises(ValueError, match="no entries"):
        export_public.export(repo, out)
    assert not out.exists()
