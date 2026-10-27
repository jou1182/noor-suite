"""Shared synthetic contract samples."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import pytest

_RFP_SHA256 = hashlib.sha256(b"rfp-document").hexdigest()
_PROPOSAL_SHA256 = hashlib.sha256(b"proposal-document").hexdigest()
_REPORT_ID = "RR-" + hashlib.sha256(b"synthetic-report").hexdigest()[:12]
_RFP_TEXT = "طلب تجريبي"
_PROPOSAL_TEXT = "مقترح تجريبي"


@pytest.fixture
def valid_tender_candidate() -> dict[str, Any]:
    """Return a valid tender-candidate sample."""

    return {
        "schema": "noor.tender-candidate/v1",
        "source_name": "radar",
        "source_ref": "SYN-0001",
        "title": "منافسة تجريبية لصيانة مبنى مصطنع",
        "issuing_entity": "جهة مصطنعة للاختبار",
        "closing_at": "2026-12-31T23:59:59+00:00",
        "etimad_ref": None,
        "source_updated_at": "2026-01-01T00:00:00+00:00",
        "exported_at": "2026-01-02T00:00:00+00:00",
        "synthetic": True,
    }


@pytest.fixture
def valid_tender() -> dict[str, Any]:
    """Return a valid tender sample."""

    return {
        "schema": "noor.tender/v1",
        "tender_id": "NT-2026-0001",
        "title": "منافسة تجريبية لصيانة مبنى مصطنع",
        "issuing_entity": "جهة مصطنعة للاختبار",
        "closing_at": "2026-12-31T23:59:59+00:00",
        "project_type": "maintenance",
        "status": "accepted",
        "etimad_ref": None,
        "activity_codes": ["001", "002-10"],
        "synthetic": True,
    }


@pytest.fixture
def valid_proposal_version() -> dict[str, Any]:
    """Return a valid proposal-version sample."""

    return {
        "schema": "noor.proposal-version/v1",
        "tender_id": "NT-2026-0001",
        "version": 1,
        "sha256": _PROPOSAL_SHA256,
        "built_at": "2026-01-03T00:00:00+00:00",
        "requested_by": "test_user",
        "activity_codes": ["001", "002-10"],
        "rejected_activities": [],
        "identity_profile": "noor",
        "synthetic": True,
    }


@pytest.fixture
def valid_review_report() -> dict[str, Any]:
    """Return a valid review report with verifiable and unverifiable findings."""

    return {
        "schema": "noor.review-report/v1",
        "report_id": _REPORT_ID,
        "tender_id": "NT-2026-0001",
        "proposal_version": 1,
        "proposal_sha256": _PROPOSAL_SHA256,
        "rfp_sha256": _RFP_SHA256,
        "generated_at": "2026-01-04T00:00:00+00:00",
        "approval_state": "proposed",
        "checks_run": ["DOC-01", "DOC-02"],
        "limitations": ["قيود على البيانات التجريبية"],
        "findings": [
            {
                "finding_key": hashlib.sha256(b"match-finding").hexdigest(),
                "criterion_id": "DOC-01",
                "result": "match",
                "sources": [
                    {
                        "doc": "rfp",
                        "sha256": _RFP_SHA256,
                        "locator": "p1",
                        "quote": _RFP_TEXT,
                    },
                    {
                        "doc": "proposal",
                        "sha256": _PROPOSAL_SHA256,
                        "locator": "t1",
                        "quote": _PROPOSAL_TEXT,
                    },
                ],
                "message": "تطابق تجريبي",
            },
            {
                "finding_key": hashlib.sha256(b"mismatch-finding").hexdigest(),
                "criterion_id": "DOC-02",
                "result": "mismatch",
                "sources": [
                    {
                        "doc": "rfp",
                        "sha256": _RFP_SHA256,
                        "locator": "p2",
                    }
                ],
                "message": "اختلاف تجريبي",
            },
        ],
        "synthetic": True,
    }


@pytest.fixture
def valid_seal() -> dict[str, Any]:
    """Return a valid seal sample."""

    return {
        "schema": "noor.seal/v1",
        "report_id": _REPORT_ID,
        "algorithm": "sha256",
        "created_at": "2026-01-05T00:00:00+00:00",
        "entries": [
            {
                "role": "rfp",
                "sha256": _RFP_SHA256,
                "size": 128,
                "version_id": "rfp-v1",
            },
            {
                "role": "proposal",
                "sha256": _PROPOSAL_SHA256,
                "size": 256,
                "version_id": "proposal-v1",
            },
            {
                "role": "report",
                "sha256": hashlib.sha256(b"report-document").hexdigest(),
                "size": 512,
                "version_id": "report-v1",
            },
        ],
        "notice": "integrity-only; not a signature; does not prove issuer identity",
        "synthetic": True,
    }


@pytest.fixture
def valid_gap_proposal() -> dict[str, Any]:
    """Return a valid gap-proposal sample."""

    return {
        "schema": "noor.gap-proposal/v1",
        "finding_key": hashlib.sha256(b"gap-proposal").hexdigest(),
        "tender_id": "NT-2026-0001",
        "report_id": _REPORT_ID,
        "proposal_version": 1,
        "criterion_id": "SBC-201",
        "summary": "فجوة تجريبية",
        "state": "pending",
        "synthetic": True,
    }


@pytest.fixture
def quote_texts() -> dict[str, str]:
    """Return the text available to the sample quote resolver."""

    return {
        _RFP_SHA256: _RFP_TEXT,
        _PROPOSAL_SHA256: _PROPOSAL_TEXT,
    }


@pytest.fixture
def quote_resolver(
    quote_texts: dict[str, str],
) -> Callable[[str], str | None]:
    """Return a dictionary-backed quote resolver."""

    def resolve(sha256: str) -> str | None:
        return quote_texts.get(sha256)

    return resolve
