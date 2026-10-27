"""Local authorization register (T030 fix after Codex critique)."""

import json
from pathlib import Path

import pytest
from noor_registry.authorizations import AuthorizationError, Register, load_register

RECORD = {"ref": "AUTH-1", "owner": "nmis_owner", "grantee": "pm",
          "capability": "create_synthetic_tender"}


def write(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loads_a_register_outside_the_repo(tmp_path):
    path = write(tmp_path / "auth.json", {"configurer_user_id": "mem", "authorizations": [RECORD]})
    register = load_register(tmp_path / "repo", {"NOOR_AUTHORIZATIONS_FILE": str(path)})
    assert register.require(configurer_id="mem", ref="AUTH-1", grantee="pm",
                            capability="create_synthetic_tender") == RECORD


def test_register_inside_the_repo_is_refused(tmp_path):
    path = write(tmp_path / "auth.json", {"configurer_user_id": "mem", "authorizations": []})
    with pytest.raises(AuthorizationError):
        load_register(tmp_path, {"NOOR_AUTHORIZATIONS_FILE": str(path)})


@pytest.mark.parametrize("data", [{}, {"configurer_user_id": "", "authorizations": []},
                                  {"configurer_user_id": "mem", "authorizations": ["x"]}])
def test_malformed_register_is_refused(tmp_path, data):
    path = write(tmp_path / "auth.json", data)
    with pytest.raises(AuthorizationError):
        load_register(tmp_path / "repo", {"NOOR_AUTHORIZATIONS_FILE": str(path)})


def test_missing_variable_is_refused(tmp_path):
    with pytest.raises(AuthorizationError):
        load_register(tmp_path, {})


def test_review_approver_needs_the_jouready_owner():
    register = Register("mem", ({"ref": "A", "owner": "nmis_owner", "grantee": "ra",
                                 "role": "review_approver", "tender_id": "NT-2026-0001"},))
    with pytest.raises(AuthorizationError):
        register.require(configurer_id="mem", ref="A", grantee="ra", role="review_approver",
                         tender_id="NT-2026-0001")
