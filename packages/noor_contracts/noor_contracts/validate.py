"""Validation helpers for the Noor JSON contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

__all__ = [
    "SCHEMA_NAMES",
    "ContractError",
    "load_schema",
    "validate",
    "validate_bytes",
]

SCHEMA_NAMES = (
    "tender-candidate",
    "tender",
    "proposal-version",
    "review-report",
    "seal",
    "gap-proposal",
    "principal", "authz-decision", "desktop-event", "platform-status",
    "provider-config", "identity-profile", "labels", "snapshot-manifest",
    "qa-analysis", "open-approval",
)

QuoteResolver = Callable[[str], str | None]

MAX_CONTRACT_BYTES = 1_048_576


class ContractError(ValueError):
    """A contract validation failure with safe, human-readable messages."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors: list[str] = (
            [errors] if isinstance(errors, str) else list(errors)
        )
        super().__init__("; ".join(self.errors))


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load and cache a packaged JSON Schema by contract name."""

    if name not in SCHEMA_NAMES:
        raise ValueError("unknown schema name")

    resource = (
        resources.files("noor_contracts")
        .joinpath("schemas")
        .joinpath(f"{name}.schema.json")
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("schema resource is not an object")
    return schema


def _is_date_time(value: object) -> bool:
    """Check an ISO date-time and require an explicit timezone offset."""

    if not isinstance(value, str):
        return True

    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False

    return parsed.tzinfo is not None and parsed.utcoffset() is not None


_FORMAT_CHECKER = FormatChecker()
_FORMAT_CHECKER.checks("date-time")(_is_date_time)

_WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC_PATH_RE = re.compile(r"^\\\\")
_FILE_URI_RE = re.compile(r"^file:", re.IGNORECASE)  # scan:allow=path.file_uri (rule definition)
_POSIX_PATH_RE = re.compile(r"^/[^/]")
# Substring match on purpose: "session_id", "sessionid" and "csrf_token" must all be caught.
_SECRET_RE = re.compile(r"session|sid=|token", re.IGNORECASE)

_STRING_RULES = (
    ("absolute Windows path", _WINDOWS_PATH_RE),
    ("UNC path", _UNC_PATH_RE),
    ("file URI", _FILE_URI_RE),
    ("absolute POSIX path", _POSIX_PATH_RE),
)

_SCHEMA_RULE_DESCRIPTIONS = {
    "additionalProperties": "additional property is not allowed",
    "anyOf": "value does not match any allowed schema",
    "const": "value does not match the required constant",
    "contains": "required array content is missing",
    "enum": "value is not one of the allowed values",
    "format": "value does not match the required format",
    "items": "array item does not match its schema",
    "maxItems": "array has too many items",
    "maxLength": "string is too long",
    "maximum": "number is above the maximum",
    "minItems": "array has too few items",
    "minLength": "string is too short",
    "minimum": "number is below the minimum",
    "oneOf": "value does not match exactly one allowed schema",
    "pattern": "value does not match the required pattern",
    "prefixItems": "array item does not match its schema",
    "required": "required property is missing",
    "type": "value has the wrong type",
    "uniqueItems": "array items must be unique",
}


def _escape_pointer_token(token: str) -> str:
    """Escape one JSON Pointer path segment."""

    return token.replace("~", "~0").replace("/", "~1")


def _pointer_child(parent: str, token: str) -> str:
    """Append one segment to a JSON Pointer."""

    return f"{parent}/{_escape_pointer_token(token)}"


def _json_pointer(parts: Iterable[object]) -> str:
    """Build a JSON Pointer from an iterable of path components."""

    pointer = ""
    for part in parts:
        pointer = _pointer_child(pointer, str(part))
    return pointer or "/"


def _walk_strings(
    value: object, pointer: str = ""
) -> Iterator[tuple[str, str]]:
    """Yield every string value and its JSON Pointer, excluding object keys."""

    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, _pointer_child(pointer, str(index)))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, _pointer_child(pointer, str(key)))


def _schema_error_message(error: ValidationError) -> str:
    """Describe a schema error without echoing the rejected value."""

    pointer = _json_pointer(error.absolute_path)
    validator = error.validator
    description = _SCHEMA_RULE_DESCRIPTIONS.get(
        validator, "schema constraint failed"
    )
    return f"{pointer}: schema validation failed ({description})"


def _check_seal(doc: dict[str, Any], errors: list[str]) -> None:
    """Apply the explicit seal role and ordering checks."""

    entries = doc.get("entries")
    if not isinstance(entries, list):
        errors.append("/entries: seal must contain exactly three entries")
        return

    roles: list[Any] = [
        entry.get("role") if isinstance(entry, dict) else None
        for entry in entries
    ]
    expected_roles = ("rfp", "proposal", "report")

    if len(entries) != 3:
        errors.append("/entries: seal must contain exactly three entries")

    duplicate = any(
        roles[index] == roles[other]
        for index in range(len(roles))
        for other in range(index + 1, len(roles))
    )
    if duplicate:
        errors.append("/entries: seal entries must not contain duplicate roles")

    if any(role not in roles for role in expected_roles):
        errors.append("/entries: seal entries must include every required role")

    if tuple(roles) != expected_roles:
        errors.append(
            "/entries: seal roles must be exactly rfp, proposal, report in that order"
        )


def _check_review_report(
    doc: dict[str, Any],
    quote_resolver: QuoteResolver | None,
    errors: list[str],
) -> None:
    """Check report source hashes and verify quotes where required."""

    findings = doc.get("findings")
    if not isinstance(findings, list):
        return

    rfp_sha256 = doc.get("rfp_sha256")
    proposal_sha256 = doc.get("proposal_sha256")

    for finding_index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue

        result = finding.get("result")
        criterion_id = finding.get("criterion_id")
        requires_quote = result == "match" or (
            isinstance(criterion_id, str)
            and criterion_id.startswith("SBC-")
            and result != "unverifiable"
        )

        sources = finding.get("sources")
        if not isinstance(sources, list):
            continue

        for source_index, source in enumerate(sources):
            if not isinstance(source, dict):
                continue

            source_pointer = _pointer_child(
                _pointer_child(
                    _pointer_child("/findings", str(finding_index)),
                    "sources",
                ),
                str(source_index),
            )
            source_doc = source.get("doc")
            source_sha256 = source.get("sha256")

            if source_doc == "rfp":
                expected_sha256 = rfp_sha256
                expected_name = "rfp_sha256"
            elif source_doc == "proposal":
                expected_sha256 = proposal_sha256
                expected_name = "proposal_sha256"
            else:
                expected_sha256 = None
                expected_name = ""

            if source_doc in ("rfp", "proposal") and (
                not isinstance(source_sha256, str)
                or not isinstance(expected_sha256, str)
                or source_sha256 != expected_sha256
            ):
                errors.append(
                    f"{source_pointer}/sha256: source sha256 does not match "
                    f"the report {expected_name}"
                )

            if not requires_quote:
                continue

            quote_pointer = f"{source_pointer}/quote"
            quote = source.get("quote")
            if not isinstance(quote, str) or not quote:
                errors.append(
                    f"{quote_pointer}: quote is required for this finding"
                )
                continue

            if quote_resolver is None:
                errors.append(f"{quote_pointer}: quote could not be verified")
                continue

            try:
                resolved_text = (
                    quote_resolver(source_sha256)
                    if isinstance(source_sha256, str)
                    else None
                )
            except Exception:
                resolved_text = None

            if not isinstance(resolved_text, str) or quote not in resolved_text:
                errors.append(f"{quote_pointer}: quote could not be verified")


def validate(
    doc: dict[str, Any],
    schema_name: str,
    quote_resolver: QuoteResolver | None = None,
) -> None:
    """Validate a contract document and raise once with all collected errors."""

    errors: list[str] = []

    if schema_name not in SCHEMA_NAMES:
        errors.append("unknown schema name")
    else:
        expected_schema = f"noor.{schema_name}/v1"
        if not isinstance(doc, dict):
            errors.append("document must be a JSON object")
        elif doc.get("schema") != expected_schema:
            errors.append(f"/schema: schema must be {expected_schema}")

    if schema_name in SCHEMA_NAMES:
        validator = Draft202012Validator(
            load_schema(schema_name),
            format_checker=_FORMAT_CHECKER,
        )
        for error in validator.iter_errors(doc):
            errors.append(_schema_error_message(error))

    for pointer, text in _walk_strings(doc):
        if schema_name == "provider-config" and pointer == "/endpoint" and text.startswith(("http://", "https://")):
            continue
        for rule, pattern in _STRING_RULES:
            if pattern.search(text):
                errors.append(f"{pointer or '/'}: {rule} is not allowed")
        if _SECRET_RE.search(text):
            errors.append(
                f"{pointer or '/'}: credential-like value is not allowed"
            )

    if schema_name == "seal" and isinstance(doc, dict):
        _check_seal(doc, errors)

    if schema_name == "review-report" and isinstance(doc, dict):
        _check_review_report(doc, quote_resolver, errors)

    if errors:
        raise ContractError(errors)


def validate_bytes(
    data: bytes,
    schema_name: str,
    quote_resolver: QuoteResolver | None = None,
) -> dict[str, Any]:
    """Check byte limits and encoding, parse JSON, then validate the contract."""

    errors: list[str] = []

    if len(data) > MAX_CONTRACT_BYTES:
        errors.append("contract larger than 1 MB")

    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        errors.append("contract is not UTF-8")
        text = ""
    else:
        if text.startswith("\ufeff"):
            errors.append("contract is not UTF-8")

    if errors:
        raise ContractError(errors)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ContractError(
            [
                "contract is not valid JSON "
                f"(line {error.lineno}, column {error.colno})"
            ]
        ) from None

    validate(parsed, schema_name, quote_resolver)
    return parsed
