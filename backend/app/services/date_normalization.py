from __future__ import annotations

import logging
import re
from datetime import date, datetime

logger = logging.getLogger(__name__)

_ONGOING_VALUES = {
    "present",
    "current",
    "currently",
    "ongoing",
    "to date",
    "now",
}


def _strip_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise TypeError(f"Unsupported date value type: {type(value).__name__}")
    text = value.strip()
    return text or None


def normalize_date_value(value: object, *, field_name: str = "date", is_end_date: bool = False) -> date | None:
    """Normalize a CV-extracted date to a PostgreSQL-compatible date.

    The function accepts common month-year and year-month formats and converts
    them to the first day of the period to stay compatible with DATE columns.
    Ambiguous or invalid values are dropped safely instead of reaching SQL.
    """
    text = _strip_value(value)
    if text is None:
        return None

    lowered = text.lower()
    if lowered in _ONGOING_VALUES:
        if is_end_date:
            return None
        raise ValueError(f"{field_name} cannot be an ongoing indicator")

    cleaned = text.replace("–", "-").replace("—", "-").replace("/", "-")
    cleaned = re.sub(r"\s+", " ", cleaned.strip())

    candidates = [
        "%Y-%m-%d",
        "%Y-%m",
        "%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %Y",
        "%B %Y",
        "%b, %Y",
        "%B, %Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in candidates:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.date()
        except ValueError:
            continue

    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"]:
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.date()
        except ValueError:
            continue

    logger.warning("Discarding unsupported %s value after CV normalization", field_name)
    return None
