"""Synthetic tests for private-stage rule execution."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tools.snapshot import __main__ as cli
from tools.snapshot import write_json

ROOT = Path(__file__).resolve().parents[2]
STAMP = "20261030-1200"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    stage = tmp_path / "stage" / "nmis_full" / STAMP
    private = tmp_path / "private" / "nmis_full" / STAMP
    stage.mkdir(parents=True)
    private.mkdir(parents=True)
    write_json(private / "state.json", {"status": "scanned", "scan_hashes": {"old": "hash"},
                                        "copied_at": "2026-10-30T12:00:00+00:00"})
    rules = repo / "tools" / "snapshot" / "rules"
    rules.mkdir(parents=True)
    shutil.copyfile(ROOT / "tools" / "snapshot" / "rules" / "nmis_full.json", rules / "nmis_full.json")
    monkeypatch.setenv("NOOR_STAGING_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("NOOR_PRIVATE_REPORTS_DIR", str(tmp_path / "private"))
    block = tmp_path / "block.txt"
    block.write_text("Oldmark\nقديمك\n", encoding="utf-8")
    monkeypatch.setenv("NOOR_BLOCKLIST_FILE", str(block))
    identity = tmp_path / "identity"
    identity.mkdir()
    profile = json.loads((ROOT / "config" / "identity" / "noor" / "profile.json").read_text(encoding="utf-8"))
    profile["system_name"] = "Synthetic System"
    profile["short_name"] = "بديل"
    profile["company_name"] = "Synthetic Company"
    write_json(identity / "profile.json", profile)
    monkeypatch.setenv("NOOR_IDENTITY_DIR", str(identity))
    monkeypatch.setattr(cli, "REPO", repo)
    return repo, stage, private, rules


def run():
    return cli.main(["sanitize", "--platform", "nmis_full", "--stamp", STAMP])


def command(name, *args):
    return cli.main([name, "--platform", "nmis_full", "--stamp", STAMP, *args])


def _rule(rules, *, blocking=True, pattern="unsafe"):
    write_json(rules / "nmis_full.json",
               [{"id": "synthetic-check", "decision": "N5", "kind": "forbid",
                 "blocking": blocking, "files": ["*.py"], "pattern": pattern}])


def _keep_rules(rules, *ids):
    original = json.loads((rules / "nmis_full.json").read_text(encoding="utf-8"))
    write_json(rules / "nmis_full.json", [rule for rule in original if rule["id"] in ids])


def _fingerprint():
    return command("fingerprint", "--source-label", "synthetic-source", "--reviewed-by", "Tester")


def test_fingerprint_requires_sanitize_and_same_scanned_tree(setup, capsys):
    _, stage, private, rules = setup
    _rule(rules)
    file = stage / "safe.py"
    file.write_text("safe", encoding="utf-8")
    assert command("scan") == 0
    assert _fingerprint() == 1
    assert "sanitize required" in capsys.readouterr().err
    assert run() == 0
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["sanitize"]["rules_sha256"] == hashlib.sha256(
        (rules / "nmis_full.json").read_bytes()).hexdigest()
    file.write_text("changed", encoding="utf-8")
    assert command("scan") == 0
    assert _fingerprint() == 1
    assert "sanitize required" in capsys.readouterr().err


def test_informational_rule_blocks_fingerprint_and_import_checks_rules(setup, capsys):
    _, stage, private, rules = setup
    _rule(rules, blocking=False)
    file = stage / "safe.py"
    file.write_text("unsafe", encoding="utf-8")
    assert run() == 0
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["sanitize"]["rules"][0] == {"id": "synthetic-check", "status": "info", "count": 1}
    assert command("scan") == 0
    assert _fingerprint() == 1
    assert "sanitize gate open: synthetic-check" in capsys.readouterr().err
    file.write_text("safe", encoding="utf-8")
    assert run() == 0
    assert command("scan") == 0
    assert _fingerprint() == 0
    _rule(rules, blocking=False, pattern="different")
    assert command("import") == 1
    assert "sanitize required" in capsys.readouterr().err


def test_blocked_source_label_refused_before_manifest(setup, capsys):
    _, stage, private, rules = setup
    _rule(rules)
    (stage / "safe.py").write_text("safe", encoding="utf-8")
    assert run() == 0
    assert command("scan") == 0
    assert command("fingerprint", "--source-label", "oldmark-repo", "--reviewed-by", "Tester") == 1
    err = capsys.readouterr().err
    assert "source label invalid" in err and "oldmark" not in err.casefold()
    assert not (private / "manifest.json").exists()


def test_keep_group_unmatched_optional_group_is_opaque(setup, capsys):
    _, stage, _, rules = setup
    (stage / "sample.py").write_text("port=1\n", encoding="utf-8")
    write_json(rules / "nmis_full.json", [
        {"id": "optional", "decision": "N6", "kind": "replace", "files": ["*.py"],
         "pattern": "(app\\.run\\()?port=1", "replacement": "port=2", "keep_group": 1,
         "expect": {"exact": 1}}])
    assert run() == 1
    err = capsys.readouterr().err
    assert "keep_group unmatched: optional" in err and "sample.py" not in err
    assert (stage / "sample.py").read_text(encoding="utf-8") == "port=1\n"


def test_rules_change_after_sanitize_blocks_fingerprint(setup, capsys):
    _, stage, _, rules = setup
    _rule(rules)
    (stage / "safe.py").write_text("safe", encoding="utf-8")
    assert run() == 0
    assert command("scan") == 0
    _rule(rules, pattern="changed")
    assert _fingerprint() == 1
    assert "sanitize required" in capsys.readouterr().err


@pytest.mark.parametrize("content", [
    "# os.environ[\"ADMIN_PASS\"]\n",
    "os.environ[\"ADMIN_PASS\"]\n",
    "os.environ[\"ADMIN_KEY\"]\n",
    "a = 'os.environ[\"ADMIN_PASS\"]'\nb = 'os.environ[\"USER_PASS\"]'\n",
])
def test_n0_done_pattern_requires_password_target_and_two_reads(setup, content, capsys):
    _, stage, _, rules = setup
    original = json.loads((rules / "nmis_full.json").read_text(encoding="utf-8"))[0]
    write_json(rules / "nmis_full.json", [original])
    (stage / "web_auth.py").write_text(content, encoding="utf-8")
    assert run() == 1
    assert "n0-password-defaults N0 mismatch count=0" in capsys.readouterr().out


@pytest.mark.parametrize("content", [
    "# app.run(host=\"127.0.0.1\", port=5311)\n",
    "host=\"127.0.0.1\"\nport=5311\n",
    "otherhost=\"127.0.0.1\"\notherport=5311\n",
    "app.run(); host=\"127.0.0.1\"; port=5311\n",
    "text = 'app.run(host=\"127.0.0.1\", port=5311)'\n",
    "if False:\n    app.run(host=\"127.0.0.1\", port=5311)\napp.run(host=HOST, port=PORT)\n",
    "HOST = \"127.0.0.1\"\nPORT = 5311\napp.run(host=HOST, port=PORT)\n",
    "app.run(host=\"127.0.0.1\", port=\"5311\") if False else None\nx = (\n",
])
def test_n6_done_patterns_require_run_call(setup, content, capsys):
    _, stage, _, rules = setup
    _keep_rules(rules, "n6-loopback-host")
    (stage / "web_dashboard.py").write_text(content, encoding="utf-8")
    assert run() == 1
    assert "n6-loopback-host N6 mismatch count=0" in capsys.readouterr().out


@pytest.mark.parametrize("content", [
    'host="::"\nport=4000\n',
    'app.run(); host="::"; port=4000\n',
])
def test_n6_replace_patterns_ignore_wrong_target(setup, content, capsys):
    _, stage, _, rules = setup
    _keep_rules(rules, "n6-loopback-host")
    (stage / "web_dashboard.py").write_text(content, encoding="utf-8")
    assert run() == 1
    assert (stage / "web_dashboard.py").read_text(encoding="utf-8") == content
    assert "mismatch count=0" in capsys.readouterr().out


@pytest.mark.parametrize(("core", "tasks", "status"), [
    ('PORT = int(os.getenv("DASHBOARD_PORT", "8080"))\n', '    port = os.getenv("DASHBOARD_PORT", "8080")\n', "ok"),
    ('# PORT = int("5311")\n', '    text = \'port = "5311"\'\n', "mismatch"),
    ('PORT = int(os.getenv("OTHER_PORT", "8080"))\n', '    port = os.getenv("DASHBOARD_PORT", "8080")\n', "mismatch"),
])
def test_n6_port_targets_both_reads(setup, core, tasks, status, capsys):
    _, stage, _, rules = setup
    _keep_rules(rules, "n6-port")
    (stage / "web_core.py").write_text(core, encoding="utf-8")
    (stage / "bot_tasks.py").write_text(tasks, encoding="utf-8")
    assert run() == (0 if status == "ok" else 1)
    assert f"n6-port N6 {status}" in capsys.readouterr().out
    if status == "ok":
        assert 'PORT = int("5311")' in (stage / "web_core.py").read_text(encoding="utf-8")


def _nmis_like(stage):
    """Invented NMIS-shaped files covering every real rule (names come from the synthetic blocklist)."""
    (stage / "web_auth.py").write_bytes(
        b'\xef\xbb\xbfimport os\nfrom security_vault import decrypt_val\n'
        b'a = os.environ.get("ADMIN_PASS", "invented")\nb = os.getenv(\'USER_PASS\', \'invented\')\n')
    (stage / "web_dashboard.py").write_text('app.run(host = "::", port=PORT)\n', encoding="utf-8")
    (stage / "web_core.py").write_text(
        'import os\nfrom security_vault import decrypt_val\n'
        'PORT     = int(os.getenv("DASHBOARD_PORT", "8080"))\n'
        'ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "owner@invented.example").strip()\n'
        'try:\n    TELEGRAM_TOKEN = decrypt_val(os.getenv("TELEGRAM_TOKEN", ""))\nexcept Exception:\n    pass\n'
        f'_LOGO_PNG_B64   = "{"A" * 2100}"\n'
        'label = "Oldmark / قديمك"\nclass OldmarkPortalAdapter: pass\nnote = "وقديمك OLDMARK oldmark_x"\n',
        encoding="utf-8")
    (stage / "bot_core.py").write_text(
        'import os\nimport telebot\nfrom security_vault import decrypt_val\n'
        'TELEGRAM_TOKEN = decrypt_val(os.getenv("TELEGRAM_TOKEN"))\nbot = telebot.TeleBot(TELEGRAM_TOKEN)\n',
        encoding="utf-8")
    (stage / "bot_tasks.py").write_text('def link():\n    port = os.getenv("DASHBOARD_PORT", "8080")\n',
                                        encoding="utf-8")
    (stage / "asset.bin").write_bytes(b"\x00Oldmark")


def test_real_rules_idempotent_bom_binary_and_opaque(setup, capsys):
    _, stage, private, _ = setup
    _nmis_like(stage)
    assert run() == 0
    first = capsys.readouterr()
    for secret in ("web_auth.py", "web_core.py", "Oldmark", "قديمك", "invented"):
        assert secret not in first.out + first.err
    assert (stage / "web_auth.py").read_bytes().startswith(b"\xef\xbb\xbf")
    auth = (stage / "web_auth.py").read_text(encoding="utf-8-sig")
    assert 'os.environ["ADMIN_PASS"]' in auth and "security_vault" not in auth and "def decrypt_val" in auth
    assert (stage / "web_dashboard.py").read_text(encoding="utf-8") == 'app.run(host="127.0.0.1", port=PORT)\n'
    core = (stage / "web_core.py").read_text(encoding="utf-8")
    assert 'PORT     = int("5311")' in core and 'os.getenv("ADMIN_EMAIL", "")' in core
    assert 'if os.getenv("NOOR_TELEGRAM_ENABLED") == "1" else ""' in core
    assert "A" * 2000 not in core
    assert "بديل" in core and "وبديل" in core and "NoorPortalAdapter" in core and "NOOR" in core and "noor_x" in core
    assert "Oldmark" not in core and "oldmark" not in core.casefold() and "قديمك" not in core
    bot = (stage / "bot_core.py").read_text(encoding="utf-8")
    assert bot.index("telebot.TeleBot") < bot.index('if os.getenv("NOOR_TELEGRAM_ENABLED") != "1":')
    assert 'port = "5311"' in (stage / "bot_tasks.py").read_text(encoding="utf-8")
    for name in ("web_auth.py", "web_core.py", "bot_core.py", "bot_tasks.py"):
        compile((stage / name).read_text(encoding="utf-8-sig"), name, "exec")
    state = json.loads((private / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "staged" and "scan_hashes" not in state
    assert "files skipped: 1" in first.out
    before = {p.name: p.read_bytes() for p in stage.iterdir()}
    assert run() == 0
    assert before == {p.name: p.read_bytes() for p in stage.iterdir()}
    assert "files changed: 0" in capsys.readouterr().out


def test_rule_mismatch_and_info(setup, capsys):
    _, stage, private, rules = setup
    (stage / "sample.py").write_text("alert = 'unsafe'\n", encoding="utf-8")
    write_json(rules / "nmis_full.json", [
        {"id": "exact", "decision": "N0", "kind": "replace", "files": ["*.py"],
         "pattern": "missing", "replacement": "done", "expect": {"exact": 1}},
        {"id": "minimum", "decision": "N0", "kind": "replace", "files": ["*.py"],
         "pattern": "alert", "replacement": "notice", "expect": {"min": 2}},
        {"id": "informational", "decision": "N5", "kind": "forbid", "blocking": False,
         "files": ["*.py"], "pattern": "unsafe"},
    ])
    assert run() == 1
    out = capsys.readouterr().out
    assert "exact N0 mismatch count=0" in out
    assert "minimum N0 mismatch count=1" in out
    assert "informational N5 info count=1" in out
    report = next(private.glob("sanitize-*.json"))
    assert json.loads(report.read_text(encoding="utf-8"))["rules"][2]["per_file"]["sample.py"] == 1


@pytest.mark.parametrize("keep", [0, 2, True, "1"])
def test_keep_group_must_name_a_pattern_group(setup, keep, capsys):
    _, stage, _, rules = setup
    (stage / "sample.py").write_text("app.run(port=1)\n", encoding="utf-8")
    write_json(rules / "nmis_full.json", [
        {"id": "keep", "decision": "N6", "kind": "replace", "files": ["*.py"],
         "pattern": "(app\\.run\\()port=1", "replacement": "port=2", "keep_group": keep,
         "expect": {"exact": 1}}])
    assert run() == 1
    assert "rules invalid" in capsys.readouterr().err
    assert (stage / "sample.py").read_text(encoding="utf-8") == "app.run(port=1)\n"


def test_missing_rules_and_refusal(setup, capsys):
    _, stage, private, rules = setup
    (rules / "nmis_full.json").unlink()
    assert run() == 1
    assert "rules unavailable" in capsys.readouterr().err
    write_json(rules / "nmis_full.json", [{"id": "check", "decision": "N0", "kind": "forbid",
                                          "files": ["**"], "pattern": "bad"}])
    for status in ("fingerprinted", "publishing", "imported"):
        write_json(private / "state.json", {"status": status})
        assert run() == 1


def test_symlink_refused(setup):
    _, stage, _, rules = setup
    write_json(rules / "nmis_full.json", [{"id": "check", "decision": "N0", "kind": "forbid",
                                          "files": ["**"], "pattern": "bad"}])
    target = stage / "target.py"
    target.write_text("safe", encoding="utf-8")
    try:
        (stage / "link.py").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert run() == 1
