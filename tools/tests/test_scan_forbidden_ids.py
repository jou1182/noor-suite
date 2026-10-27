"""Synthetic identities and metadata fixtures for the public scanner."""

import hashlib
import io
import json
import subprocess
import struct
import unicodedata
import zipfile
import zlib
from pathlib import Path

import pytest

from tools import scan_public_repo as scan


FAKE = "ال" + "فلاني"
LATIN = "al" + "fulani"


def test_name_variants_and_entry_number():
    for text, entry in [("فلاني", FAKE), ("elfulani", LATIN),
                        ("fulani", LATIN), ("alfulani", LATIN)]:
        findings = scan.scan_text(text, "x.txt", [entry])
        assert [f.rule for f in findings] == ["name.blocked"]
        assert findings[0].masked == "#1"


def test_repo_name_exemptions_only(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "specs").mkdir()
    (repo / "specs" / "x.txt").write_text(FAKE + "\n" + "AK" + "IA" + "X" * 16, encoding="utf-8")
    (repo / "tools").mkdir()
    (repo / "tools" / "scan_allowlist.json").write_text(
        json.dumps({"name_exempt_paths": ["specs/"]}), encoding="utf-8")
    exempt = scan.scan_tree(repo, [FAKE], repo_exemptions=True)
    stage = scan.scan_tree(repo, [FAKE], repo_exemptions=False)
    assert "name.blocked" not in [f.rule for f in exempt.findings]
    assert "secret.aws" in [f.rule for f in exempt.findings]
    assert "name.blocked" in [f.rule for f in stage.findings]


def test_stage_scan_skips_no_directory(tmp_path):
    """Everything in a stage is fingerprinted, so nothing there may escape the scan."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for skipped in ("node_modules", ".git", "x.egg-info", ".pytest_tmp"):
        (tmp_path / skipped).mkdir(exist_ok=True)
        (tmp_path / skipped / "a.txt").write_text(FAKE, encoding="utf-8")
    stage = scan.scan_tree(tmp_path, [FAKE], repo_exemptions=False)
    assert [f.rule for f in stage.findings].count("name.blocked") == 4
    assert scan.scan_tree(tmp_path, [FAKE], repo_exemptions=True).findings == []


def test_blocklist_with_bom_keeps_first_entry(tmp_path, monkeypatch):
    blocklist = tmp_path / "outside" / "blocklist.txt"
    blocklist.parent.mkdir()
    blocklist.write_bytes(b"\xef\xbb\xbf" + FAKE.encode("utf-8") + b"\n")
    (tmp_path / "repo").mkdir()
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(blocklist))
    assert scan.load_blocklist(tmp_path / "repo", True) == [FAKE]


def test_data_rule_ignores_design_token_key_only():
    assert scan.scan_text('{"color_token": "x"}', "a.json", []) == []
    assert [f.rule for f in scan.scan_text('{"csrf_token": "x"}', "a.json", [])] == ["data.session"]


def test_office_metadata_in_all_three_formats():
    for suffix in ("docx", "pptx", "xlsx"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("docProps/core.xml", "<creator>" + FAKE + "</creator>")
            archive.writestr("docProps/app.xml", "<company>" + FAKE + "</company>")
        assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(stream.getvalue(), "a." + suffix, [FAKE])]


def test_pdf_info_and_unverifiable():
    assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(
        ("%PDF-1.4\n1 0 obj << /Author (" + LATIN + ") >> endobj").encode(), "a.pdf", [LATIN])]
    assert "meta.unverifiable_pdf" in [f.rule for f in scan.scan_metadata(
        b"%PDF-1.5 /ObjStm", "a.pdf", [])]
    hex_pdf = b"%PDF-1.4\n/Author <" + LATIN.encode().hex().encode() + b">"
    assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(hex_pdf, "a.pdf", [LATIN])]
    xmp = ("%PDF-1.4\n<x:xmpmeta>" + LATIN + "</x:xmpmeta>").encode()
    assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(xmp, "a.pdf", [LATIN])]


def test_png_metadata_and_malformed():
    content = b"Author\x00" + LATIN.encode()
    chunk = struct.pack(">I", len(content)) + b"tEXt" + content
    chunk += struct.pack(">I", zlib.crc32(b"tEXt" + content))
    data = b"\x89PNG\r\n\x1a\n" + chunk + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(data, "a.png", [LATIN])]
    assert "meta.unverifiable_image" in [f.rule for f in scan.scan_metadata(data[:-2], "a.png", [])]


def test_jpeg_comment_metadata():
    payload = LATIN.encode()
    jpeg = b"\xff\xd8\xff\xfe" + struct.pack(">H", len(payload) + 2) + payload + b"\xff\xd9"
    assert "meta.blocked_name" in [f.rule for f in scan.scan_metadata(jpeg, "a.jpg", [LATIN])]


def test_binary_review_and_opaque_cli(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "picture.png").write_bytes(b"binary-image")
    report = scan.scan_tree(repo, [], repo_exemptions=True)
    assert len(report.binary_assets_for_visual_review) == 1
    assert report.binary_assets_for_visual_review[0]["opaque_id"] == hashlib.sha256(b"binary-image").hexdigest()[:12]
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--paths", "picture.png"]) == 1
    out = capsys.readouterr().out
    assert "picture.png" not in out and "binary assets for review: 1" in out


def test_history_summary_uses_content_id(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    data = ("AK" + "IA" + "X" * 16).encode()
    (repo / "fixture.txt").write_bytes(data)
    subprocess.run(["git", "-C", str(repo), "add", "fixture.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                    "-c", "user.email=t@example.test", "commit", "-qm", "init"], check=True)
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--history"]) == 1
    output = capsys.readouterr().out
    assert hashlib.sha256(data).hexdigest()[:12] in output
    assert "fixture.txt" not in output


def test_full_rejects_ancestor_traversal_and_escape(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    stage = tmp_path / "stage"
    repo.mkdir()
    stage.mkdir()
    marker = "secret_name_marker.txt"
    (stage / marker).write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("NOOR_STAGING_DIR", str(stage))
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--root", str(tmp_path), "--paths", ".", "--full"]) == 2
    assert scan.main(["--repo", str(repo), "--root", str(repo), "--paths", "..", "--full"]) == 2
    assert marker not in capsys.readouterr().out
    with pytest.raises(scan.ConfigError):
        scan.scan_tree(repo, [], paths=["../stage/" + marker])


def test_scan_report_hashes_exact_bytes(tmp_path):
    data = b"synthetic"
    (tmp_path / "a.txt").write_bytes(data)
    report = scan.scan_tree(tmp_path, [])
    assert report.file_hashes == {"a.txt": hashlib.sha256(data).hexdigest()}


def test_scan_report_hash_keys_are_nfc(tmp_path):
    name = unicodedata.normalize("NFD", "café.txt")
    (tmp_path / name).write_bytes(b"synthetic")
    report = scan.scan_tree(tmp_path, [])
    assert list(report.file_hashes) == [unicodedata.normalize("NFC", name)]


def test_blocked_identity_in_path_components(tmp_path):
    (tmp_path / LATIN).mkdir()
    (tmp_path / LATIN / "safe.txt").write_text("synthetic", encoding="utf-8")
    report = scan.scan_tree(tmp_path, [LATIN])
    assert "name.blocked_path" in [f.rule for f in report.findings]


def test_stage_ignores_inline_allow_marker(tmp_path):
    fake_uri = "fi" + "le://synthetic"
    (tmp_path / "a.txt").write_text(fake_uri + " # scan:allow=path.file_uri", encoding="utf-8")
    assert "path.file_uri" in [f.rule for f in scan.scan_tree(tmp_path, [], repo_exemptions=False).findings]
    assert "path.file_uri" not in [f.rule for f in scan.scan_tree(tmp_path, [], repo_exemptions=True).findings]


def test_git_modes_scan_skipped_directories(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "base.txt").write_text("synthetic", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "base.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                    "user.email=t@example.test", "commit", "-qm", "base"], check=True)
    skipped = repo / "node_modules"
    skipped.mkdir()
    (skipped / "a.txt").write_text("AK" + "IA" + "X" * 16, encoding="utf-8")
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--diff"]) == 1
    subprocess.run(["git", "-C", str(repo), "add", "-f", "node_modules/a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                    "user.email=t@example.test", "commit", "-qm", "fixture"], check=True)
    assert scan.main(["--repo", str(repo), "--history"]) == 1


def test_name_variants_minimum_stem_and_separators():
    assert "name.blocked" not in [f.rule for f in scan.scan_text("abc", "x.txt", ["alabc"])]
    for text in ("al-fulani", "al_fulani", "el.fulani"):
        assert "name.blocked" in [f.rule for f in scan.scan_text(text, "x.txt", [LATIN])]


def test_exact_file_exemption_applies_to_metadata(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "scan_allowlist.json").write_text(
        json.dumps({"name_exempt_paths": ["safe/a.pptx"]}), encoding="utf-8")
    (repo / "safe").mkdir()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("docProps/core.xml", "<creator>" + LATIN + "</creator>")
    (repo / "safe" / "a.pptx").write_bytes(stream.getvalue())
    (repo / "safe" / "a.pptx.bak").write_bytes(stream.getvalue())
    report = scan.scan_tree(repo, [LATIN], repo_exemptions=True)
    assert not [f for f in report.findings if f.path == "safe/a.pptx" and f.rule == "meta.blocked_name"]
    assert "meta.blocked_name" in [f.rule for f in scan.scan_tree(repo, [LATIN], repo_exemptions=False).findings]


def test_scanner_usage_errors_do_not_echo_values(tmp_path, capsys):
    marker = "secret_name_marker"
    assert scan.main(["--platform", marker, "--paths", "."]) == 2
    output = capsys.readouterr()
    assert "usage error" in output.err and marker not in output.err + output.out


def test_timeout_does_not_echo_arguments(tmp_path, monkeypatch, capsys):
    marker = "secret_name_marker"
    repo = tmp_path / "repo"
    repo.mkdir()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired([marker], 1)
    monkeypatch.setattr(scan, "changed_paths", timeout)
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--diff"]) == 2
    output = capsys.readouterr()
    assert marker not in output.out + output.err


def test_full_refuses_any_explicit_root(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("synthetic", encoding="utf-8")
    monkeypatch.delenv("NOOR_STAGING_DIR", raising=False)
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--root", str(repo), "--paths", ".", "--full"]) == 2


def test_full_refuses_another_git_repository(tmp_path, monkeypatch, capsys):
    own, other = tmp_path / "own", tmp_path / "other"
    own.mkdir()
    other.mkdir()
    monkeypatch.setattr(scan, "PUBLIC_REPO", own, raising=False)
    monkeypatch.setattr(scan, "_git", lambda repo, *args, **kwargs:
                        str(repo.resolve()) if args[0] == "rev-parse" else b"")
    assert scan.main(["--repo", str(other), "--paths", ".", "--full"]) == 2
    assert "usage" not in capsys.readouterr().out
    assert scan.main(["--repo", str(own), "--paths", ".", "--full"]) == 0
    assert "a.txt" not in capsys.readouterr().out


def test_repo_walk_includes_tracked_skipped_dir(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    ignored = repo / "node_modules"
    ignored.mkdir()
    (ignored / "tracked.txt").write_text("AK" + "IA" + "X" * 16, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-f", "node_modules/tracked.txt"], check=True)
    (ignored / "untracked.txt").write_text("AK" + "IA" + "Y" * 16, encoding="utf-8")
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    assert scan.main(["--repo", str(repo), "--paths", "."]) == 1
    report = scan.scan_tree(repo, [], repo_exemptions=True)
    assert [f.rule for f in report.findings].count("secret.aws") == 1
