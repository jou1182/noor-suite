import json
import shutil
from pathlib import Path

import pytest
from jsonschema import validate
from noor_identity import IdentityBuildError, build_identity

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def identity(tmp_path):
    path = tmp_path / "identity"
    shutil.copytree(ROOT / "config" / "identity" / "noor", path)
    return path


def test_missing_profile(tmp_path):
    with pytest.raises(IdentityBuildError, match="profile.json"):
        build_identity(tmp_path)


def test_schema_failure(identity):
    profile = json.loads((identity / "profile.json").read_text(encoding="utf-8"))
    profile["system_name"] = ""
    (identity / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(IdentityBuildError, match="schema"):
        build_identity(identity)


def test_missing_referenced_file(identity):
    (identity / "fonts" / "Tajawal-Bold.ttf").unlink()
    with pytest.raises(IdentityBuildError, match="missing"):
        build_identity(identity)


def test_symlink_escape(identity, tmp_path):
    font = identity / "fonts" / "Tajawal-Bold.ttf"
    font.unlink()
    outside = tmp_path / "outside.ttf"
    outside.write_bytes(b"test")
    try:
        font.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(IdentityBuildError, match="escape"):
        build_identity(identity)


def test_low_contrast(identity):
    profile = json.loads((identity / "profile.json").read_text(encoding="utf-8"))
    profile["palette"]["dark"]["on_surface"] = profile["palette"]["dark"]["surface"]
    (identity / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    with pytest.raises(IdentityBuildError, match="contrast"):
        build_identity(identity)


def test_corrupt_logo_falls_back_to_text(identity):
    profile = json.loads((identity / "profile.json").read_text(encoding="utf-8"))
    (identity / "logo.png").write_bytes(b"not an image")
    profile["logo"] = "logo.png"
    (identity / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    tokens = build_identity(identity)
    assert tokens["logo_ok"] is False
    assert json.loads((identity / "build" / "noor_tokens.json").read_text(encoding="utf-8"))["logo_ok"] is False


def test_explicit_theme_overrides_system_preference(identity):
    build_identity(identity)
    css = (identity / "build" / "noor-tokens.css").read_text(encoding="utf-8")
    assert ':root, [data-theme="light"]' in css
    assert '@media (prefers-color-scheme: dark) { :root:not([data-theme])' in css
    assert '[data-theme="dark"]' in css
    assert '@media (prefers-color-scheme: dark) { :root {' not in css


def test_labels_are_valid_and_separate():
    labels = json.loads((ROOT / "packages/noor_identity/noor_identity/labels.ar.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "specs/002-full-noor-suite/contracts/labels.schema.json").read_text(encoding="utf-8"))
    validate(labels, schema)
    assert "check_result.match" in labels["entries"]
    assert "approval_state.approved" in labels["entries"]
    assert labels["entries"]["check_result.match"] != labels["entries"]["approval_state.approved"]
