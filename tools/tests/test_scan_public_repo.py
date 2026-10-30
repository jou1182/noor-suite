"""T005: public-repository scanner. Fake secrets and paths are assembled at runtime so this file
itself contains no matching literal."""

import importlib.util
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "scan_public_repo", Path(__file__).resolve().parents[1] / "scan_public_repo.py")
scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scan  # dataclasses look their module up here
SPEC.loader.exec_module(scan)

AWS = "AK" + "IA" + "X" * 16
GH = "gh" + "p_" + "a" * 36
SK = "s" + "k-" + "b" * 24
WIN = "C" + ":" + "\\" + "data"
UNC = " " + "\\" * 2 + "server"
FILE_URI = "fi" + "le://x"
HOME = "/" + "home" + "/user"
PRIVATE = "-----BEG" + "IN RSA PRIVATE KEY-----"
ASSIGN = "pass" + "word = '" + "z" * 16 + "'"


def rules(text, path="src/a.py", blocklist=()):
    return [f.rule for f in scan.scan_text(text, path, list(blocklist))]


@pytest.mark.parametrize("text, rule", [
    (AWS, "secret.aws"), (GH, "secret.github"), (SK, "secret.openai_like"),
    (PRIVATE, "secret.private_key"), (ASSIGN, "secret.assignment"),
    (WIN, "path.windows"), (UNC, "path.unc"), (FILE_URI, "path.file_uri"), (HOME, "path.posix_home"),
])
def test_each_rule_fires(text, rule):
    assert rule in rules(text)


def test_https_url_is_not_a_windows_path():
    assert rules("see https://example.org/x") == []


def test_session_rule_only_in_data_files():
    line = "session" + "_id=1"
    assert "data.session" in rules(line, "samples/synthetic/x.md")
    assert "data.session" in rules(line, "out/contract.json")
    assert "data.session" not in rules(line, "specs/x/contract.schema.json")
    assert "data.session" not in rules(line, "src/app.py")


def test_blocklist_matches_arabic_without_tashkeel_and_never_prints_name():
    name = "شركة" + " " + "مثال"
    text = "العرض من شَرِكَة مثال للمقاولات"
    findings = scan.scan_text(text, "README.md", [name])
    assert [f.rule for f in findings] == ["name.blocked"]
    assert name not in str(findings[0]) and "#1" in str(findings[0])


def test_masked_output_hides_the_secret():
    finding = scan.scan_text(AWS, "a.txt", [])[0]
    assert AWS not in str(finding)
    assert finding.masked == AWS[:4] + "***"


MARK = "scan" + ":allow="


def test_allow_marker_silences_only_the_named_rule():
    assert rules(WIN + "  # " + MARK + "path.windows") == []
    assert rules(WIN + " " + FILE_URI + "  # " + MARK + "path.windows") == ["path.file_uri"]


def test_bare_allow_marker_silences_nothing():
    assert rules(WIN + "  # scan" + ":allow") == ["path.windows"]


def test_secrets_and_names_can_never_be_silenced():
    assert rules(AWS + "  # " + MARK + "secret.aws") == ["secret.aws"]
    name = "اسم" + "محظور"
    assert rules(name + "  # " + MARK + "name.blocked", blocklist=[name]) == ["name.blocked"]


def test_docx_text_is_scanned_as_data():
    xml = "<w:document><w:p><w:r><w:t>" + WIN + "</w:t></w:r></w:p></w:document>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/document.xml", xml)
    assert [f.rule for f in scan.scan_blob(buf.getvalue(), "samples/a.docx", [])] == ["path.windows"]


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def test_paths_mode_exit_codes(tmp_path, monkeypatch):
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    repo = _git_repo(tmp_path)
    (repo / "clean.txt").write_text("hello", encoding="utf-8")
    (repo / "dirty.txt").write_text(HOME, encoding="utf-8")
    assert scan.main(["--repo", str(repo), "--paths", "clean.txt"]) == 0
    assert scan.main(["--repo", str(repo), "--paths", "dirty.txt"]) == 1


def test_blocklist_inside_repo_is_refused(tmp_path, monkeypatch):
    repo = _git_repo(tmp_path)
    inside = repo / "names.txt"
    inside.write_text("x\n", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(inside))
    assert scan.main(["--repo", str(repo), "--paths", "names.txt"]) == 2


def test_require_blocklist(tmp_path, monkeypatch):
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    repo = _git_repo(tmp_path)
    assert scan.main(["--repo", str(repo), "--paths", "x", "--require-blocklist"]) == 2


def test_diff_mode_sees_untracked_files(tmp_path, monkeypatch):
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    repo = _git_repo(tmp_path)
    (repo / "a.txt").write_text("ok", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "init"], check=True)
    (repo / "new.txt").write_text(FILE_URI, encoding="utf-8")
    assert scan.main(["--repo", str(repo), "--diff"]) == 1


def test_history_mode_finds_a_removed_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    repo = _git_repo(tmp_path)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    (repo / "a.txt").write_text(AWS, encoding="utf-8")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "one"], check=True)
    (repo / "a.txt").write_text("gone", encoding="utf-8")
    subprocess.run(git + ["commit", "-qam", "two"], check=True)
    assert scan.main(["--repo", str(repo), "--diff"]) == 0
    assert scan.main(["--repo", str(repo), "--history"]) == 1


def _docx(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return buf.getvalue()


def test_docx_header_and_properties_are_scanned():
    data = _docx({"word/document.xml": "<w:p>clean</w:p>",
                  "word/header1.xml": "<w:t>" + HOME + "</w:t>",
                  "docProps/core.xml": '<dc:creator x="' + WIN + '"/>'})
    found = {f.rule for f in scan.scan_blob(data, "samples/a.docx", [])}
    assert {"path.posix_home", "path.windows"} <= found


def test_docx_with_an_unscannable_part_is_refused():
    data = _docx({"word/document.xml": "<w:p>ok</w:p>", "word/media/image1.png": b"\x89PNG"})
    assert [f.rule for f in scan.scan_blob(data, "samples/a.docx", [])] == ["file.unscannable_docx"]


def test_unknown_binary_fails_and_only_a_pinned_hash_passes():
    import hashlib
    blob = b"\x00\x01binary"
    assert [f.rule for f in scan.scan_blob(blob, "assets/x.bin", [])] == ["file.binary_unscanned"]
    pinned = {"assets/x.bin": hashlib.sha256(blob).hexdigest()}
    assert scan.scan_blob(blob, "assets/x.bin", [], pinned) == []
    assert scan.scan_blob(blob + b"!", "assets/x.bin", [], pinned)[0].rule == "file.binary_unscanned"


def test_approved_finding_is_dropped_only_for_exact_bytes_and_approvable_rules(tmp_path):
    import hashlib
    import json
    (tmp_path / "tools").mkdir()
    data = ("x = '" + UNC + "'\nkey = '" + AWS + "'\n").encode()
    approved = {"approved_findings": {
        "src/a.py": {"sha256": hashlib.sha256(data).hexdigest(), "rules": ["path.unc"]},
        "src/b.py": {"sha256": hashlib.sha256(data).hexdigest(), "rules": ["path.unc", "secret.aws"]}}}
    (tmp_path / "tools" / "scan_allowlist.json").write_text(json.dumps(approved), encoding="utf-8")
    loaded = scan.load_approved_findings(tmp_path)
    assert list(loaded) == ["src/a.py"]  # an entry naming a non-approvable rule is ignored whole
    found = scan.scan_blob(data, "src/a.py", [])
    assert {f.rule for f in found} >= {"path.unc", "secret.aws"}
    kept = {f.rule for f in scan._drop_approved(found, "src/a.py", data, loaded)}
    assert "path.unc" not in kept and "secret.aws" in kept
    changed = data + b"\n"
    assert "path.unc" in {f.rule for f in scan._drop_approved(
        scan.scan_blob(changed, "src/a.py", []), "src/a.py", changed, loaded)}


def test_binary_without_an_early_nul_is_not_read_as_text():
    blob = b"\xff\xfe" * 6000 + b"\x00"  # NUL only after the first 8 KB
    assert [f.rule for f in scan.scan_blob(blob, "assets/a.txt", [])] == ["file.binary_unscanned"]
    assert [f.rule for f in scan.scan_blob(b"\xff\xfe abc", "notes.txt", [])] == [
        "file.binary_unscanned"]  # not strict UTF-8
    assert [f.rule for f in scan.scan_blob(b"plain", "photo.png", [])] == ["file.binary_unscanned"]


def test_history_reports_oversized_blobs(tmp_path, monkeypatch):
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE", raising=False)
    monkeypatch.setattr(scan, "MAX_FILE_BYTES", 10)
    repo = _git_repo(tmp_path)
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    (repo / "big.txt").write_text("x" * 50, encoding="utf-8")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "big"], check=True)
    rules_found = [f.rule for f in scan.scan_history(repo, [])]
    assert rules_found == ["file.too_large"]
