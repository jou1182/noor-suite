"""Synthetic snapshot pipeline tests; all paths live in pytest temporary space."""

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import unicodedata
from pathlib import Path

import pytest
from noor_contracts.validate import validate

from tools.snapshot import __main__ as cli


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    stage = tmp_path / "staging"
    reports = tmp_path / "reports"
    monkeypatch.setenv("NOOR_STAGING_DIR", str(stage))
    monkeypatch.setenv("NOOR_PRIVATE_REPORTS_DIR", str(reports))
    monkeypatch.setattr(cli, "REPO", repo)
    return repo, stage, reports


def run(*args):
    return cli.main(list(args))


def prepared(dirs, monkeypatch, *, name="a.txt", data=b"synthetic"):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    (source / name).parent.mkdir(parents=True, exist_ok=True)
    (source / name).write_bytes(data)
    block = stage.parent / "block.txt"
    block.write_text("al" + "fulani", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(block))
    assert run("stage", "--platform", "radar", "--from-dir", str(source)) == 0
    stamp = next((stage / "radar").iterdir()).name
    return stamp, stage / "radar" / stamp, reports / "radar" / stamp


def test_config_boundaries_and_missing_env(dirs, monkeypatch, capsys):
    repo, stage, reports = dirs
    monkeypatch.setenv("NOOR_STAGING_DIR", str(repo / "stage"))
    assert run("stage", "--platform", "radar", "--from-dir", str(repo)) == 2
    monkeypatch.setenv("NOOR_STAGING_DIR", str(stage))
    for bad in (repo / "reports", stage / "reports"):
        monkeypatch.setenv("NOOR_PRIVATE_REPORTS_DIR", str(bad))
        assert run("stage", "--platform", "radar", "--from-dir", str(repo)) == 2
    monkeypatch.delenv("NOOR_STAGING_DIR")
    assert run("stage", "--platform", "radar", "--from-dir", str(repo)) == 2
    assert "NOOR_STAGING_DIR" in capsys.readouterr().err


def test_select_forbidden_and_allowlist(dirs):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    names = ["keep.py", "drop.txt", "reset_password.py", "templates/change_password.html", ".env", ".env.example", "x.pem", "x.key", "x.p12",
             "x.pfx", "id_rsa_x", "id_ed25519_x", "security_vault_x", "x.db", "x.sqlite3",
             "User Data/Cookies", "Default/Cookies", "x.ldb", "Local Storage/x", ".n8n/x",
             "n8n_workflows/x", "database.sqlite", "ATPAS_Library/x", "x.atplib",
             "dist/x", "build/x", "output/x", "x.xls", "x.xlsx", "x.xlsm",
             "my_password.txt", "my_passwd.txt", "x.kdbx", "noor_private_reports/x", "scan-20261027.json"]
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic", encoding="utf-8")
    allow = repo / "tools" / "snapshot" / "allowlists"
    allow.mkdir(parents=True)
    (allow / "radar.txt").write_text("**\n", encoding="utf-8")
    assert run("stage", "--platform", "radar", "--from-dir", str(source)) == 0
    stamp = next((stage / "radar").iterdir()).name
    assert run("select", "--platform", "radar", "--stamp", stamp) == 0
    kept = {p.relative_to(stage / "radar" / stamp).as_posix() for p in (stage / "radar" / stamp).rglob("*") if p.is_file()}
    assert kept == {"keep.py", "drop.txt", ".env.example", "reset_password.py",
                    "templates/change_password.html"}
    (allow / "radar.txt").write_text("keep.py\n", encoding="utf-8")
    assert run("select", "--platform", "radar", "--stamp", stamp) == 0
    assert {p.name for p in (stage / "radar" / stamp).iterdir()} == {"keep.py"}


def test_tree_formula_nfc_and_verify_change(dirs, monkeypatch):
    repo, stage, reports = dirs
    from tools.snapshot.fingerprint import inventory, tree_hash
    root = stage / "radar" / "20261027-1000"
    root.mkdir(parents=True)
    name = unicodedata.normalize("NFD", "café.txt")
    (root / name).write_bytes(b"a")
    files = inventory(root)
    normalized = unicodedata.normalize("NFC", name)
    expected = hashlib.sha256((normalized + "\t1\t" + hashlib.sha256(b"a").hexdigest() + "\n").encode()).hexdigest()
    assert tree_hash(files) == expected


def test_scan_fingerprint_and_opaque_output(dirs, monkeypatch, capsys):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    marker = "secret_name_marker.txt"
    (source / marker).write_text("al" + "fulani" + "\n" + "AK" + "IA" + "X" * 16, encoding="utf-8")
    block = stage.parent / "block.txt"
    block.write_text("al" + "fulani", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(block))
    assert run("stage", "--platform", "radar", "--from-dir", str(source)) == 0
    stamp = next((stage / "radar").iterdir()).name
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1
    output = capsys.readouterr()
    for forbidden in (marker, "alfulani", "AKIA", str(source)):
        assert forbidden not in output.out + output.err
    from tools import scan_public_repo
    assert scan_public_repo.main(["--root", str(stage / "radar" / stamp), "--paths", ".", "--full", "--platform", "radar"]) == 2
    (stage / "radar" / stamp / marker).write_text("safe", encoding="utf-8")
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    (stage / "radar" / stamp / marker).write_text("changed", encoding="utf-8")
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 1
    state = json.loads((reports / "radar" / stamp / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "staged"
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    manifest = json.loads((reports / "radar" / stamp / "manifest.json").read_text(encoding="utf-8"))
    validate(manifest, "snapshot-manifest")
    assert {x["tool"] for x in manifest["scans"]} == {"secrets_paths_ids", "forbidden_identities", "asset_metadata"}
    assert all(not Path(x["path"]).is_absolute() for x in manifest["files"])
    later = capsys.readouterr()
    for forbidden in (marker, "alfulani", "AKIA", str(source)):
        assert forbidden not in later.out + later.err


def test_import_and_one_byte_verify_failure(dirs, monkeypatch):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    (source / "a.txt").write_bytes(b"a")
    block = stage.parent / "block.txt"
    block.write_text("al" + "fulani", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(block))
    assert run("stage", "--platform", "radar", "--from-dir", str(source)) == 0
    stamp = next((stage / "radar").iterdir()).name
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    assert run("import", "--platform", "radar", "--stamp", stamp) == 0
    assert run("verify", "--platform", "radar") == 0
    (repo / "platforms" / "radar" / "a.txt").write_bytes(b"b")
    assert run("verify", "--platform", "radar") == 1


def test_approval_resolves_only_non_sensitive_findings(dirs, monkeypatch):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    data = b"\x00synthetic"
    (source / "asset.bin").write_bytes(data)
    block = stage.parent / "block.txt"
    block.write_text("al" + "fulani", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(block))
    assert run("stage", "--platform", "radar", "--from-dir", str(source)) == 0
    stamp = next((stage / "radar").iterdir()).name
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1
    approved = stage.parent / "approved.txt"
    approved.write_text(hashlib.sha256(data).hexdigest() + " visual synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    state = json.loads((reports / "radar" / stamp / "state.json").read_text(encoding="utf-8"))
    assert state["tool_results"]["secrets_paths_ids"] == "findings_resolved"
    (stage / "radar" / stamp / "secret.txt").write_text("AK" + "IA" + "X" * 16, encoding="utf-8")
    changed_id = hashlib.sha256(("AK" + "IA" + "X" * 16).encode()).hexdigest()
    approved.write_text(changed_id + " visual synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1


def test_scan_rejects_change_during_scan(dirs, monkeypatch):
    from tools.snapshot import scan as snapshot_scan
    stamp, target, private = prepared(dirs, monkeypatch)
    original = snapshot_scan.scanner.scan_tree
    def mutate(*args, **kwargs):
        report = original(*args, **kwargs)
        (target / "a.txt").write_bytes(b"changed")
        return report
    monkeypatch.setattr(snapshot_scan.scanner, "scan_tree", mutate)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1
    assert json.loads((private / "state.json").read_text(encoding="utf-8"))["status"] == "staged"


def test_import_prevalidates_in_sibling_space(dirs, monkeypatch):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    observed = []
    def inspect(source, dest, record):
        observed.append(Path(dest))
        raise OSError("synthetic copy failure")
    monkeypatch.setattr(importer, "_copy_verified_file", inspect)
    assert run("import", "--platform", "radar", "--stamp", stamp) != 0
    assert observed and observed[0].is_relative_to(dirs[0].parent / f".noor-import-radar-{stamp}")
    assert not observed[0].is_relative_to(dirs[0])
    assert not public.exists()
    assert not list(dirs[0].parent.glob(".noor-import-*"))
    assert not (dirs[0] / "platforms" / "_snapshots" / "radar.json").exists()


def test_mark_requires_full_digest_and_binary_review(dirs, monkeypatch):
    stamp, target, private = prepared(dirs, monkeypatch, name="asset.bin", data=b"\x00synthetic")
    digest = hashlib.sha256(b"\x00synthetic").hexdigest()
    approved = dirs[1].parent / "approved.txt"
    approved.write_text(digest[:12], encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 2
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1
    approved.write_text(digest + " visual synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["approved_at"] and "visual" in state["approvals"][digest]
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    state["approvals"] = {}
    (private / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 1
    state["approvals"] = {digest: {"visual": {"reason": "synthetic review", "at": state["approved_at"]}}}
    (private / "state.json").write_text(json.dumps(state), encoding="utf-8")
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0


def test_hard_stop_not_approvable(dirs, monkeypatch):
    stamp, target, private = prepared(dirs, monkeypatch, name="bad.pdf", data=b"%PDF-1.5 /ObjStm")
    digest = hashlib.sha256(b"%PDF-1.5 /ObjStm").hexdigest()
    approved = dirs[1].parent / "approved.txt"
    approved.write_text(digest + " visual synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1


def test_nonempty_gitkeep_blocks_import_and_verify(dirs, monkeypatch):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    public.mkdir(parents=True)
    (public / ".gitkeep").write_text("not empty", encoding="utf-8")
    assert run("import", "--platform", "radar", "--stamp", stamp) != 0
    assert (public / ".gitkeep").read_text(encoding="utf-8") == "not empty"


def test_verify_rejects_marker_and_duplicate_scans(dirs, monkeypatch, capsys):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    assert run("import", "--platform", "radar", "--stamp", stamp) == 0
    public = dirs[0] / "platforms" / "radar"
    (public / ".gitkeep").write_text("nonempty", encoding="utf-8")
    assert run("verify", "--platform", "radar") == 1
    (public / ".gitkeep").write_bytes(b"")
    assert run("verify", "--platform", "radar") == 0
    assert "SOURCE.md: absent" in capsys.readouterr().out
    manifest_path = dirs[0] / "platforms" / "_snapshots" / "radar.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scans"] = [manifest["scans"][0]] * 3
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert run("verify", "--platform", "radar") == 1


@pytest.mark.parametrize("rule", ["file.too_large", "file.unscannable_docx", "file.symlink",
                                  "meta.unverifiable_pdf", "meta.unverifiable_image",
                                  "name.blocked", "name.blocked_path", "meta.blocked_name",
                                  "secret.aws"])
def test_approval_hard_stops(rule):
    from tools import scan_public_repo as scanner
    from tools.snapshot import scan as snapshot_scan
    digest = hashlib.sha256(b"synthetic").hexdigest()
    finding = scanner.Finding(rule, "x.txt", 0, "")
    report = scanner.ScanReport([finding], [], {"x.txt": digest[:12]}, 1, {"x.txt": digest})
    assert not snapshot_scan._approved({"approvals": {digest: {"visual": {"reason": "synthetic", "at": "now"}}}}, finding, report)


def test_import_rolls_back_partial_public_move(dirs, monkeypatch):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    def partial(source, destination):
        Path(destination).mkdir()
        (Path(destination) / "a.txt").write_bytes(b"partial")
        raise OSError("synthetic failure")
    monkeypatch.setattr(importer.os, "replace", partial)
    assert run("import", "--platform", "radar", "--stamp", stamp) == 2
    assert not (dirs[0] / "platforms" / "radar").exists()
    assert not (dirs[0] / "platforms" / "_snapshots" / "radar.json").exists()


def test_import_rejects_changed_stage_before_public_write(dirs, monkeypatch):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    (target / "a.txt").write_bytes(b"changed")
    assert run("import", "--platform", "radar", "--stamp", stamp) == 1
    assert json.loads((private / "state.json").read_text(encoding="utf-8"))["status"] == "staged"
    assert not (dirs[0] / "platforms" / "radar").exists()
    assert not (dirs[0] / "platforms" / "_snapshots" / "radar.json").exists()


def test_manifest_requires_exact_three_tools(dirs, monkeypatch):
    from tools.snapshot import fingerprint
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    monkeypatch.setattr(fingerprint, "TOOL_IDS", ("secrets_paths_ids",) * 3)
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") != 0


def test_snapshot_usage_and_fingerprint_status_only(dirs, monkeypatch, capsys):
    marker = "secret_name_marker"
    assert run("stage", "--platform", marker, "--from-dir", str(dirs[0])) == 2
    output = capsys.readouterr()
    assert "usage error" in output.err and marker not in output.err + output.out
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    manifest = json.loads((private / "manifest.json").read_text(encoding="utf-8"))
    output = capsys.readouterr().out
    assert "fingerprinted" in output and "files: 1" in output
    assert manifest["tree_sha256"][:12] not in output
    assert manifest["tree_sha256"] not in output


def test_mark_requires_kind_and_reason(dirs, monkeypatch):
    stamp, target, private = prepared(dirs, monkeypatch, name="asset.bin", data=b"\x00synthetic")
    digest = hashlib.sha256(b"\x00synthetic").hexdigest()
    approved = dirs[1].parent / "review.txt"
    for line in (digest, digest + " visual", digest + " unknown reviewed"):
        approved.write_text(line, encoding="utf-8")
        assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
                   "--list", str(approved)) == 2
    approved.write_text(digest + " visual reviewed synthetic image", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["approvals"][digest]["visual"]["reason"] == "reviewed synthetic image"
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0


@pytest.mark.parametrize("content,wrong_kind,right_kind", [
    ("fi" + "le://synthetic", "visual", "path"),
    ("session_id=synthetic", "path", "session"),
])
def test_approval_kind_must_match_finding(dirs, monkeypatch, content, wrong_kind, right_kind):
    name = "samples/a.json" if right_kind == "session" else "a.txt"
    stamp, target, private = prepared(dirs, monkeypatch, name=name, data=content.encode())
    digest = hashlib.sha256(content.encode()).hexdigest()
    approved = dirs[1].parent / "review.txt"
    approved.write_text(f"{digest} {wrong_kind} synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 1
    approved.write_text(f"{digest} {right_kind} synthetic review", encoding="utf-8")
    assert run("mark-sanitized", "--platform", "radar", "--stamp", stamp,
               "--list", str(approved)) == 0
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0


def test_verify_scans_source_marker_and_names_unchecked(dirs, monkeypatch, capsys):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    assert run("import", "--platform", "radar", "--stamp", stamp) == 0
    source = dirs[0] / "platforms" / "radar" / "SOURCE.md"
    source.write_text("synthetic", encoding="utf-8")
    monkeypatch.delenv("NOOR_BLOCKLIST_FILE")
    assert run("verify", "--platform", "radar") == 1
    assert "SOURCE.md: names-unchecked" in capsys.readouterr().out
    source.write_text("AK" + "IA" + "X" * 16, encoding="utf-8")
    assert run("verify", "--platform", "radar") == 1
    assert "SOURCE.md: findings" in capsys.readouterr().out
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(dirs[1].parent / "block.txt"))
    source.write_text("al" + "fulani", encoding="utf-8")
    assert run("verify", "--platform", "radar") == 1
    assert "SOURCE.md: findings" in capsys.readouterr().out


def test_import_refuses_existing_source_marker(dirs, monkeypatch, capsys):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    public.mkdir(parents=True)
    (public / "SOURCE.md").write_text("synthetic", encoding="utf-8")
    assert run("import", "--platform", "radar", "--stamp", stamp) == 2
    assert "move SOURCE.md aside" in capsys.readouterr().err


def test_import_refuses_source_marker_with_findings(dirs, monkeypatch, capsys):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    public.mkdir(parents=True)
    (public / "SOURCE.md").write_text("AK" + "IA" + "X" * 16, encoding="utf-8")
    assert run("import", "--platform", "radar", "--stamp", stamp) == 1
    assert "SOURCE.md findings" in capsys.readouterr().err


def test_import_single_directory_publish_and_cleanup(dirs, monkeypatch):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    public.mkdir(parents=True)
    (public / ".gitkeep").write_bytes(b"")
    calls = []
    original = importer.os.replace
    def observe(source, dest):
        calls.append((Path(source), Path(dest)))
        return original(source, dest)
    monkeypatch.setattr(importer.os, "replace", observe)
    assert run("import", "--platform", "radar", "--stamp", stamp) == 0
    assert len([pair for pair in calls if pair[1] == public]) == 1
    assert calls[0][0] == dirs[0].parent / f".noor-import-radar-{stamp}"
    assert not list(dirs[0].parent.glob(".noor-import-*"))


@pytest.mark.parametrize("changed", [False, True])
def test_import_recovers_publish_before_manifest(dirs, monkeypatch, capsys, changed):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    manifest = dirs[0] / "platforms" / "_snapshots" / "radar.json"
    original = importer.write_json
    def interrupt(path, doc):
        if Path(path) == manifest:
            raise KeyboardInterrupt()
        return original(path, doc)
    monkeypatch.setattr(importer, "write_json", interrupt)
    with pytest.raises(KeyboardInterrupt):
        importer.run(dirs[0], "radar", stamp)
    publishing = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert publishing["status"] == "publishing"
    assert publishing["publishing_manifest"]["platform_id"] == "radar"
    assert (dirs[0] / "platforms" / "radar" / "a.txt").exists()
    assert not manifest.exists()
    monkeypatch.setattr(importer, "write_json", original)
    if changed:
        (dirs[0] / "platforms" / "radar" / "a.txt").write_bytes(b"changed")
        assert run("import", "--platform", "radar", "--stamp", stamp) == 2
        assert "remove the destination" in capsys.readouterr().err
        assert not manifest.exists()
    else:
        assert run("import", "--platform", "radar", "--stamp", stamp) == 0
        assert manifest.exists()
        assert json.loads((private / "state.json").read_text(encoding="utf-8"))["status"] == "imported"


def test_import_resumes_after_interrupt_before_publish(dirs, monkeypatch):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    original = importer.os.replace
    def interrupt(source, dest):
        raise KeyboardInterrupt()
    monkeypatch.setattr(importer.os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt):
        importer.run(dirs[0], "radar", stamp)
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "publishing"
    assert not (dirs[0] / "platforms" / "radar" / "a.txt").exists()
    monkeypatch.setattr(importer.os, "replace", original)
    assert run("import", "--platform", "radar", "--stamp", stamp) == 0
    assert (dirs[0] / "platforms" / "_snapshots" / "radar.json").exists()
    assert not list(dirs[0].parent.glob(".noor-import-*"))


def test_import_prevalidation_failure_preserves_existing_marker(dirs, monkeypatch):
    from tools.snapshot import importer
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    public = dirs[0] / "platforms" / "radar"
    public.mkdir(parents=True)
    marker = public / ".gitkeep"
    marker.write_bytes(b"")
    marker_stat = marker.stat()
    def fail_copy(source, destination, record):
        raise importer.SnapshotError("synthetic validation failure", 1)
    monkeypatch.setattr(importer, "_copy_verified_file", fail_copy)
    assert run("import", "--platform", "radar", "--stamp", stamp) == 1
    assert marker.exists()
    assert marker.stat().st_ino == marker_stat.st_ino
    assert not list(dirs[0].parent.glob(".noor-import-*"))


def test_import_rejects_stale_sibling_temp(dirs, monkeypatch, capsys):
    stamp, target, private = prepared(dirs, monkeypatch)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    sibling = dirs[0].parent / f".noor-import-radar-{stamp}"
    sibling.mkdir(parents=True)
    assert run("import", "--platform", "radar", "--stamp", stamp) == 2
    assert "remove" in capsys.readouterr().err
    assert sibling.exists()


@pytest.mark.parametrize("name", ["source.md", ".GITKEEP", "Source.md/nested.txt", ".gitkeep/nested.txt"])
def test_import_rejects_casefolded_root_markers(dirs, monkeypatch, name):
    stamp, target, private = prepared(dirs, monkeypatch, name=name)
    assert run("scan", "--platform", "radar", "--stamp", stamp) == 0
    assert run("fingerprint", "--platform", "radar", "--stamp", stamp,
               "--source-label", "synthetic-source", "--reviewed-by", "Tester") == 0
    assert run("import", "--platform", "radar", "--stamp", stamp) != 0
    assert not (dirs[0] / "platforms" / "radar").exists()


def test_unsafe_tar_entry_rejected(dirs):
    from tools.snapshot.stage import extract_archive
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as tar:
        info = tarfile.TarInfo("../bad.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        extract_archive(payload.getvalue(), dirs[1] / "target")


@pytest.mark.skipif(shutil.which("git") is None, reason="git unavailable")
def test_git_archive_stage(dirs):
    repo, stage, reports = dirs
    source = repo / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "a.txt").write_text("synthetic", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=t@example.test", "commit", "-qm", "init"], check=True)
    assert run("stage", "--platform", "radar", "--from-git", str(source), "--commit", "HEAD") == 0
