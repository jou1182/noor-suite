"""T010: schema acceptance and rejection tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from noor_contracts.validate import ContractError, validate

_CONTRACT_CASES = (
    ("tender-candidate", "valid_tender_candidate"),
    ("tender", "valid_tender"),
    ("proposal-version", "valid_proposal_version"),
    ("review-report", "valid_review_report"),
    ("seal", "valid_seal"),
    ("gap-proposal", "valid_gap_proposal"),
)


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    _CONTRACT_CASES,
)
def test_valid_sample_is_accepted(
    schema_name: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Each packaged contract accepts its synthetic sample."""

    sample: dict[str, Any] = request.getfixturevalue(fixture_name)
    quote_resolver = request.getfixturevalue("quote_resolver")
    validate(sample, schema_name, quote_resolver=quote_resolver)


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    _CONTRACT_CASES,
)
def test_extra_top_level_field_is_rejected(
    schema_name: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Every contract rejects additional top-level properties."""

    sample = deepcopy(request.getfixturevalue(fixture_name))
    sample["unexpected_field"] = True

    with pytest.raises(ContractError):
        validate(sample, schema_name)


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    _CONTRACT_CASES,
)
def test_synthetic_false_is_rejected(
    schema_name: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Every contract requires the synthetic marker to be true."""

    sample = deepcopy(request.getfixturevalue(fixture_name))
    sample["synthetic"] = False

    with pytest.raises(ContractError):
        validate(sample, schema_name)


@pytest.mark.parametrize(
    ("schema_name", "fixture_name"),
    _CONTRACT_CASES,
)
def test_unknown_schema_version_is_rejected(
    schema_name: str,
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    """Every contract rejects versions other than its v1 schema."""

    sample = deepcopy(request.getfixturevalue(fixture_name))
    sample["schema"] = f"noor.{schema_name}/v2"

    with pytest.raises(ContractError):
        validate(sample, schema_name)


def test_tender_closing_at_without_timezone_is_rejected(
    valid_tender: dict[str, Any],
) -> None:
    """A tender closing time must carry a timezone offset."""

    valid_tender["closing_at"] = "2026-12-31T23:59:59"

    with pytest.raises(ContractError):
        validate(valid_tender, "tender")


def test_tender_candidate_accepts_null_closing_at(
    valid_tender_candidate: dict[str, Any],
) -> None:
    """A tender candidate may omit a known closing time."""

    valid_tender_candidate["closing_at"] = None

    validate(valid_tender_candidate, "tender-candidate")
