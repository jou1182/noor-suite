"""Consumer checks for each 002 contract, using invented values only."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from noor_contracts.validate import ContractError, validate

ROOT = Path(__file__).resolve().parents[3]
AT = "2026-10-27T00:00:00Z"
HASH = "a" * 64


def samples():
    inventory = json.loads((ROOT / "platforms/nmis/noor_registry/platforms.json").read_text(encoding="utf-8"))
    statuses = {item["platform_id"]: {key: item[key] for key in
                ("run_state", "maturity", "provider_mode", "demo_gate", "fr010", "snapshot_tree_sha256")}
                for item in inventory}
    return {
        "principal": {"schema": "noor.principal/v1", "platform_id": "radar", "user_id": "U-12345678",
                      "display_name": "مستخدم اختبار", "role": "viewer", "platform_permissions": ["read"],
                      "csrf": "a" * 43, "theme": "light", "issued_at": AT, "expires_at": AT,
                      "nonce": "b" * 22, "synthetic": True},
        "authz-decision": {"schema": "noor.authz-decision/v1", "platform_id": "radar",
                           "user_id": "U-12345678", "tender_id": "NT-2026-0001", "action": "read",
                           "allowed": True, "reason": "ok", "decided_at": AT, "synthetic": True},
        "desktop-event": {"schema": "noor.desktop-event/v1", "client": "desktop:atpas",
                          "event": "heartbeat", "at": AT},
        "platform-status": {"schema": "noor.platform-status/v1", "platforms": statuses,
                            "generated_at": AT, "synthetic": True},
        "provider-config": {"schema": "noor.provider-config/v1", "platform_id": "radar", "mode": "local",
                            "endpoint": "http://127.0.0.1:11434", "model": "synthetic-model"},
        "identity-profile": json.loads((ROOT / "config/identity/noor/profile.json").read_text(encoding="utf-8")),
        "labels": json.loads((ROOT / "packages/noor_identity/noor_identity/labels.ar.json").read_text(encoding="utf-8")),
        "snapshot-manifest": {"schema": "noor.snapshot-manifest/v1", "platform_id": "radar",
                              "source_label": "synthetic-source", "source_commit": "a" * 40,
                              "copied_at": AT, "files": [{"path": "src/app.py", "size": 1, "sha256": HASH}],
                              "tree_sha256": HASH, "scans": [
                                  {"tool": tool, "version": "1", "result": "clean", "at": AT}
                                  for tool in ("secrets_paths_ids", "forbidden_identities", "asset_metadata")],
                              "exposures_closed": [], "binary_assets_reviewed_by": "reviewer",
                              "synthetic_data_only": True},
        "qa-analysis": {"schema": "noor.qa-analysis/v1",
                        "job_id": "12345678-1234-4123-8123-123456789abc", "tender_id": "NT-2026-0001",
                        "level": "quick", "state": "uploaded", "report_docx_sha256": None,
                        "report_pdf_sha256": None, "provider_mode": "local", "model": "synthetic-model",
                        "nature": "general_first_look_no_evidence", "updated_at": AT, "synthetic": True},
        "open-approval": {"schema": "noor.open-approval/v1", "report_id": "RR-123456789abc",
                          "tender_id": "NT-2026-0001", "synthetic": True},
    }


@pytest.mark.parametrize("name", list(samples()))
def test_suite_contract_accepts_valid_and_rejects_extra_path_and_version(name):
    sample = samples()[name]
    validate(sample, name)
    for change in ({"unexpected_field": True}, {"schema": f"noor.{name}/v2"}):
        invalid = {**deepcopy(sample), **change}
        with pytest.raises(ContractError):
            validate(invalid, name)
    path_fields = {"principal": "display_name", "authz-decision": "action", "desktop-event": "event",
                   "provider-config": "endpoint", "identity-profile": "system_name",
                   "snapshot-manifest": "source_label", "qa-analysis": "model", "open-approval": "report_id"}
    invalid = deepcopy(sample)
    if name == "platform-status":
        invalid["platforms"]["radar"]["maturity"] = "/etc/synthetic"
    elif name == "labels":
        invalid["entries"]["platform.radar"]["text_ar"] = "/etc/synthetic"
    else:
        invalid[path_fields[name]] = "/etc/synthetic"
    with pytest.raises(ContractError) as caught:
        validate(invalid, name)
    assert any("absolute POSIX path" in error for error in caught.value.errors)


@pytest.mark.parametrize("path", ["/etc/synthetic", "\\\\host\\share", "C:\\synthetic", "file:/synthetic"])  # scan:allow=path.windows
def test_suite_absolute_paths_rejected(path):
    sample = samples()["principal"]
    sample["display_name"] = path
    with pytest.raises(ContractError, match="path|URI"):
        validate(sample, "principal")


def test_only_provider_endpoint_allows_url():
    sample = samples()["provider-config"]
    validate(sample, "provider-config")
    sample["endpoint"] = "/etc/synthetic"
    with pytest.raises(ContractError):
        validate(sample, "provider-config")
