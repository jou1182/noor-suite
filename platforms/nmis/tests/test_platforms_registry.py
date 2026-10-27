import json

import pytest
from noor_registry.platforms_registry import ORDER, load_platforms, status_documents


def test_fixed_inventory_and_status_contract():
    entries = load_platforms()
    assert set(entries) == set(ORDER)
    document = status_documents(entries, windows=True)
    assert document["schema"] == "noor.platform-status/v1"
    assert all(value["maturity"] == "L0" and value["fr010"] is None
               for value in document["platforms"].values())


def test_non_windows_atpas_is_unavailable():
    assert status_documents(load_platforms(), windows=False)["platforms"]["atpas"]["run_state"] == "unavailable_on_device"


def test_running_pending_is_not_cleared(tmp_path):
    entries = list(load_platforms().values())
    entries[0] = {**entries[0], "run_state": "running"}
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    loaded = load_platforms(path)
    assert status_documents(loaded, windows=True)["platforms"][entries[0]["platform_id"]]["run_state"] == "not_cleared_for_demo"


@pytest.mark.parametrize("change", [
    {},
    {"fr010": {"passed": 1, "total": 2, "at": "2026-10-27T00:00:00Z", "run_id": "FR-123456789abc"}},
    {"fr010": {"passed": 2, "total": 2, "at": "2026-10-27T00:00:00Z", "run_id": "FR-123456789abc"}},
])
def test_passed_gate_requires_complete_evidence_at_load(tmp_path, change):
    entries = list(load_platforms().values())
    entries[0] = {**entries[0], "demo_gate": "passed", **change}
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="complete FR-010 evidence"):
        load_platforms(path)


def test_complete_count_record_with_decision_allows_running(tmp_path):
    entries = list(load_platforms().values())
    entries[0] = {**entries[0], "run_state": "running", "demo_gate": "passed",
                  "demo_gate_decision_ref": "AP-SYN-001", "snapshot_tree_sha256": "a" * 64,
                  "fr010": {"passed_count": 2, "total_count": 2,
                            "at": "2026-10-27T00:00:00Z", "run_id": "FR-123456789abc"}}
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    status = status_documents(load_platforms(path), windows=True)["platforms"][entries[0]["platform_id"]]
    assert status["run_state"] == "running" and status["fr010"]["passed"] == 2


@pytest.mark.parametrize("target", ["https://example.invalid", "http://localhost:5312", "http://127.0.0.2:5312"])
def test_non_loopback_refused_at_load(tmp_path, target):
    entries = list(load_platforms().values())
    entries[0] = {**entries[0], "upstream": target}
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="loopback"):
        load_platforms(path)
