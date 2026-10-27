"""Fixed platform inventory and validated public status disclosure."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import validate

ORDER = ("radar", "quick_analysis", "nmis_full", "atpas", "jouready")
IDS = frozenset(ORDER)
BROWSER_ORIGINS = {
    "nmis_full": "http://nmis.noor.localhost:5310",
    "radar": "http://radar.noor.localhost:5310",
    "quick_analysis": "http://qa.noor.localhost:5310",
    "jouready": "http://jr.noor.localhost:5310",
}


def _local_endpoint(value: str) -> bool:
    if value == "desktop":
        return True
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                and parsed.port is not None and not parsed.username
                and not parsed.password and not parsed.path and not parsed.query
                and not parsed.fragment)
    except ValueError:
        return False


def status_documents(entries: dict, *, windows: bool | None = None) -> dict:
    """Return the complete schema-validated status document."""
    if windows is None:
        windows = sys.platform == "win32"
    platforms = {}
    for platform_id in ORDER:
        item = entries[platform_id]
        result = item.get("fr010")
        if isinstance(result, dict) and "passed_count" in result:
            result = {"passed": result.get("passed_count"), "total": result.get("total_count"),
                      "at": result.get("at"), "run_id": result.get("run_id")}
        if item["demo_gate"] == "passed":
            if (not isinstance(result, dict)
                    or not isinstance(result.get("passed"), int)
                    or isinstance(result.get("passed"), bool)
                    or not isinstance(result.get("total"), int)
                    or isinstance(result.get("total"), bool)
                    or result["total"] < 1
                    or result["passed"] != result["total"]
                    or not isinstance(item.get("demo_gate_decision_ref"), str)
                    or not item["demo_gate_decision_ref"].strip()
                    or not item.get("snapshot_tree_sha256")):
                raise ValueError(f"{platform_id}: passed demo gate requires complete FR-010 evidence, a gate decision reference, and a snapshot hash")
        platforms[platform_id] = {key: item[key] for key in (
            "run_state", "maturity", "provider_mode", "demo_gate", "fr010", "snapshot_tree_sha256")}
        platforms[platform_id]["fr010"] = result
        if item["demo_gate"] != "passed" and item["run_state"] == "running":
            platforms[platform_id]["run_state"] = "not_cleared_for_demo"
        if platform_id == "atpas" and not windows:
            platforms[platform_id]["run_state"] = "unavailable_on_device"
    document = {"schema": "noor.platform-status/v1", "platforms": platforms,
                "generated_at": datetime.now(timezone.utc).isoformat(), "synthetic": True}
    from noor_contracts import __file__ as contracts_init
    schema = json.loads((Path(contracts_init).parent / "schemas" / "platform-status.schema.json").read_text(encoding="utf-8"))
    validate(document, schema)
    return document


def load_platforms(path: Path | None = None) -> dict:
    """Load data, refusing non-loopback targets and mismatched inventories."""
    path = path or Path(__file__).with_name("platforms.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = {}
    for item in data:
        platform_id = item["platform_id"]
        if platform_id in entries or platform_id not in IDS:
            raise ValueError("duplicate or unknown platform id")
        if not _local_endpoint(item["upstream"]):
            raise ValueError(f"{platform_id}: upstream must be loopback or desktop")
        # Each web platform gets its own origin served by the home proxy (002 R2).
        expected = BROWSER_ORIGINS.get(platform_id, "desktop")
        if item["browser_origin"] != expected:
            raise ValueError(f"{platform_id}: browser_origin must be {expected}")
        if item["display_key"] != f"platform.{platform_id}":
            raise ValueError("platform display key mismatch")
        entries[platform_id] = item
    if set(entries) != IDS:
        raise ValueError("platform inventory must contain the five fixed ids")
    status_documents(entries)
    return entries
