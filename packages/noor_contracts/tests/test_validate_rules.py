"""T011: validation rule and safety tests."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from noor_contracts.validate import ContractError, validate, validate_bytes


def _windows_path() -> str:
    """Build an absolute Windows path at runtime."""

    return "C" + ":" + "\\" + "x"


def _unc_path() -> str:
    """Build a UNC path at runtime."""

    return "\\" * 2 + "srv" + "\\" + "share"


def _file_uri() -> str:
    """Build a file URI at runtime."""

    return "fi" + "le://x"


def _posix_path() -> str:
    """Build a home-like POSIX path at runtime."""

    return "/" + "home" + "/u"


@pytest.mark.parametrize(
    ("schema_name", "fixture_name", "field", "path_factory"),
    (
        (
            "tender-candidate",
            "valid_tender_candidate",
            "title",
            _windows_path,
        ),
        ("tender", "valid_tender", "title", _unc_path),
        ("tender", "valid_tender", "issuing_entity", _file_uri),
        (
            "tender-candidate",
            "valid_tender_candidate",
            "title",
            _posix_path,
        ),
    ),
)
def test_path_like_top_level_value_is_rejected(
    schema_name: str,
    fixture_name: str,
    field: str,
    path_factory: Callable[[], str],
    request: pytest.FixtureRequest,
) -> None:
    """Path-like top-level strings are rejected without echoing their values."""

    sample = deepcopy(request.getfixturevalue(fixture_name))
    offending_value = path_factory()
    sample[field] = offending_value

    with pytest.raises(ContractError) as caught:
        validate(sample, schema_name)

    assert all(offending_value not in message for message in caught.value.errors)
    assert offending_value not in str(caught.value)


def test_path_like_nested_finding_message_is_rejected(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """Path-like strings in nested findings are rejected."""

    sample = deepcopy(valid_review_report)
    offending_value = _windows_path()
    sample["findings"][0]["message"] = offending_value

    with pytest.raises(ContractError) as caught:
        validate(sample, "review-report", quote_resolver=quote_resolver)

    assert all(offending_value not in message for message in caught.value.errors)
    assert offending_value not in str(caught.value)


def test_https_url_is_accepted_in_title(
    valid_tender_candidate: dict[str, Any],
) -> None:
    """An HTTPS URL is not treated as an absolute Windows path."""

    valid_tender_candidate["title"] = "https://example.org/a"

    validate(valid_tender_candidate, "tender-candidate")


@pytest.mark.parametrize(
    "credential_text", ("session", "sid=abc", "ToKeN", "session_id=1", "csrf_token")
)
def test_credential_like_values_are_rejected(
    credential_text: str,
    valid_tender_candidate: dict[str, Any],
) -> None:
    """Session, sid, and token strings are rejected case-insensitively."""

    valid_tender_candidate["title"] = credential_text

    with pytest.raises(ContractError):
        validate(valid_tender_candidate, "tender-candidate")


def test_validate_bytes_rejects_more_than_one_megabyte() -> None:
    """Oversized byte payloads are rejected before JSON parsing."""

    payload = b"x" * (1_048_576 + 1)

    with pytest.raises(ContractError) as caught:
        validate_bytes(payload, "tender")

    assert "contract larger than 1 MB" in caught.value.errors


def test_validate_bytes_rejects_latin_one_payload() -> None:
    """Bytes that are not strict UTF-8 are rejected before JSON parsing."""

    payload = b'{"value":"' + b"\xe9" + b'"}'

    with pytest.raises(ContractError) as caught:
        validate_bytes(payload, "tender")

    assert "contract is not UTF-8" in caught.value.errors


def test_validate_bytes_rejects_utf8_bom() -> None:
    """A UTF-8 BOM is rejected as invalid contract encoding."""

    payload = b"\xef\xbb\xbf{}"

    with pytest.raises(ContractError) as caught:
        validate_bytes(payload, "tender")

    assert "contract is not UTF-8" in caught.value.errors


def test_match_finding_without_quote_is_rejected(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """A match finding requires a quote for every source."""

    sample = deepcopy(valid_review_report)
    sample["findings"][0]["sources"][0].pop("quote")

    with pytest.raises(ContractError):
        validate(sample, "review-report", quote_resolver=quote_resolver)


def test_quote_longer_than_300_characters_is_rejected(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """The schema limit for source quotes remains enforced."""

    sample = deepcopy(valid_review_report)
    sample["findings"][0]["sources"][0]["quote"] = "q" * 301

    with pytest.raises(ContractError):
        validate(sample, "review-report", quote_resolver=quote_resolver)


def test_quote_must_be_present_literally_in_resolved_text(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """A quote is not accepted unless it is an exact substring."""

    sample = deepcopy(valid_review_report)
    sample["findings"][0]["sources"][0]["quote"] = "نص غير موجود"

    with pytest.raises(ContractError) as caught:
        validate(sample, "review-report", quote_resolver=quote_resolver)

    assert any(
        "quote could not be verified" in message
        for message in caught.value.errors
    )


def test_match_finding_is_rejected_without_resolver(
    valid_review_report: dict[str, Any],
) -> None:
    """A match finding cannot be verified without a quote resolver."""

    with pytest.raises(ContractError) as caught:
        validate(valid_review_report, "review-report", quote_resolver=None)

    assert any(
        "quote could not be verified" in message
        for message in caught.value.errors
    )


def test_match_finding_is_rejected_when_resolver_returns_none(
    valid_review_report: dict[str, Any],
) -> None:
    """A resolver returning no text cannot verify a match finding."""

    def unavailable(_sha256: str) -> str | None:
        return None

    with pytest.raises(ContractError) as caught:
        validate(
            valid_review_report,
            "review-report",
            quote_resolver=unavailable,
        )

    assert any(
        "quote could not be verified" in message
        for message in caught.value.errors
    )


def test_sbc_mismatch_without_quote_is_rejected(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """An SBC mismatch requires quotes and cannot be left unsupported."""

    sample = deepcopy(valid_review_report)
    sample["findings"][1]["criterion_id"] = "SBC-201"
    sample["findings"][1]["result"] = "mismatch"

    with pytest.raises(ContractError):
        validate(sample, "review-report", quote_resolver=quote_resolver)


def test_sbc_unverifiable_without_quote_is_accepted(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """An explicitly unverifiable SBC finding does not require a quote."""

    sample = deepcopy(valid_review_report)
    sample["findings"][1]["criterion_id"] = "SBC-201"
    sample["findings"][1]["result"] = "unverifiable"

    validate(sample, "review-report", quote_resolver=quote_resolver)


def test_source_hash_must_match_report_hash(
    valid_review_report: dict[str, Any],
    quote_resolver: Callable[[str], str | None],
) -> None:
    """A report source hash must match the corresponding document hash."""

    sample = deepcopy(valid_review_report)
    sample["findings"][1]["sources"][0]["sha256"] = hashlib.sha256(
        b"different-document"
    ).hexdigest()

    with pytest.raises(ContractError):
        validate(sample, "review-report", quote_resolver=quote_resolver)


def test_seal_with_duplicated_role_is_rejected(
    valid_seal: dict[str, Any],
) -> None:
    """Seal roles cannot be duplicated."""

    valid_seal["entries"][1]["role"] = "rfp"

    with pytest.raises(ContractError):
        validate(valid_seal, "seal")


def test_seal_with_missing_role_is_rejected(
    valid_seal: dict[str, Any],
) -> None:
    """Seal entries must include every required role."""

    valid_seal["entries"] = valid_seal["entries"][:2]

    with pytest.raises(ContractError):
        validate(valid_seal, "seal")


def test_seal_with_wrong_role_order_is_rejected(
    valid_seal: dict[str, Any],
) -> None:
    """Seal roles must appear in the prescribed order."""

    valid_seal["entries"][0]["role"], valid_seal["entries"][1]["role"] = (
        valid_seal["entries"][1]["role"],
        valid_seal["entries"][0]["role"],
    )

    with pytest.raises(ContractError):
        validate(valid_seal, "seal")
