"""T009: the packaged schemas must stay byte-identical to the approved copies in the spec."""

from pathlib import Path

import pytest

PKG_SCHEMAS = Path(__file__).resolve().parents[1] / "noor_contracts" / "schemas"
SPEC_SCHEMAS = Path(__file__).resolve().parents[3] / "specs" / "001-single-thread-demo" / "contracts"
SUITE_SCHEMAS = Path(__file__).resolve().parents[3] / "specs" / "002-full-noor-suite" / "contracts"
NAMES = [
    "tender-candidate",
    "tender",
    "proposal-version",
    "review-report",
    "seal",
    "gap-proposal",
]
SUITE_NAMES = [p.name.removesuffix(".schema.json") for p in SUITE_SCHEMAS.glob("*.schema.json")]


@pytest.mark.parametrize("name", NAMES)
def test_schema_matches_spec_copy(name):
    packaged = (PKG_SCHEMAS / f"{name}.schema.json").read_bytes()
    approved = (SPEC_SCHEMAS / f"{name}.schema.json").read_bytes()
    assert packaged == approved, f"{name} drifted from the approved spec copy"


@pytest.mark.parametrize("name", SUITE_NAMES)
def test_suite_schema_matches_spec_copy(name):
    assert (PKG_SCHEMAS / f"{name}.schema.json").read_bytes() == (
        SUITE_SCHEMAS / f"{name}.schema.json"
    ).read_bytes()


def test_no_extra_schemas():
    assert sorted(p.name for p in PKG_SCHEMAS.glob("*.json")) == sorted(
        f"{n}.schema.json" for n in NAMES + SUITE_NAMES
    )
