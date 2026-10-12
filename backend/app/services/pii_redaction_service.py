"""Best-effort PII detection and redaction for free-form profile text.

This deterministic service targets common CV contact details and Indonesian
identifiers. It is not a complete DLP system; callers must not treat a clean
result as proof that text contains no personal data.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "name",
        re.compile(
            r"\b(?:full\s+name|name)\s*[:#-]\s*[^\r\n;|]+",
            re.IGNORECASE,
        ),
    ),
    (
        "government_id",
        re.compile(
            r"\b(?:NIK|KTP)\s*[:#-]?\s*\d[\d -]{8,20}\d"
            r"|\bNPWP\s*[:#-]?\s*\d[\d. -]{8,20}\d"
            r"|\bpassport(?:\s*(?:no|number))?\s*[:#-]?\s*[A-Z0-9]{6,12}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "email",
        re.compile(
            r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])",
            re.IGNORECASE,
        ),
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+\d[\d(). \t-]{7,}\d|0[\d(). \t-]{8,}\d)(?!\w)"),
    ),
    (
        "address",
        re.compile(
            r"\b(?:home\s+address|address|alamat|domisili|residence)\s*[:#-]\s*"
            r"[^\r\n;|]+",
            re.IGNORECASE,
        ),
    ),
    (
        "address",
        re.compile(
            r"\b(?:Jalan|Jl\.?)\s+[^\r\n;|]{4,}",
            re.IGNORECASE,
        ),
    ),
    (
        "government_id",
        re.compile(r"(?<!\d)\d{16}(?!\d)"),
    ),
)

_REDACTION_TOKENS = {
    "name": "[REDACTED_NAME]",
    "government_id": "[REDACTED_GOVERNMENT_ID]",
    "email": "[REDACTED_EMAIL]",
    "phone": "[REDACTED_PHONE]",
    "address": "[REDACTED_ADDRESS]",
}


@dataclass(frozen=True)
class RedactionResult:
    """Redacted content and non-sensitive detection metadata."""

    redacted_text: str
    detected_types: tuple[str, ...]
    replacement_count: int


def redact_pii(text: str) -> RedactionResult:
    """Redact recognizable PII without retaining or returning matched values."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    redacted = text
    detected_types: list[str] = []
    replacement_count = 0

    for entity_type, pattern in _PATTERNS:
        def replace_match(match: re.Match[str]) -> str:
            if entity_type == "phone":
                digits = sum(char.isdigit() for char in match.group())
                if digits < 10:
                    return match.group()
            return _REDACTION_TOKENS[entity_type]

        redacted, replacements = pattern.subn(replace_match, redacted)
        if replacements:
            replacement_count += replacements
            if entity_type not in detected_types:
                detected_types.append(entity_type)

    return RedactionResult(
        redacted_text=redacted,
        detected_types=tuple(detected_types),
        replacement_count=replacement_count,
    )


def redact_structured_value(value: Any) -> Any:
    """Recursively redact string values returned by an extraction model."""
    if isinstance(value, str):
        return redact_pii(value).redacted_text
    if isinstance(value, Mapping):
        return {
            redact_pii(key).redacted_text if isinstance(key, str) else key:
            redact_structured_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structured_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structured_value(item) for item in value)
    return value
