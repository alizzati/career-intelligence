"""Deterministic 12-CV subset selection for the frozen ablation design.

The full crosswalk has 43 labelled candidates. The limited evaluation design
requires 12 CVs: one representative from each of the 10 career categories plus
two additional candidates drawn only from categories that have more than one
sample. Selection is a pure function of the source crosswalk rows and a fixed
seed, so the frozen manifest can be re-derived and audited.

This module never reads a CV body, a database, or a model. It only selects
already-validated crosswalk rows.
"""
from __future__ import annotations

import random
from typing import Iterable, Mapping, Sequence

SUBSET_SIZE = 12
SUBSET_SEED = 20261115
SUBSET_SCHEMA_VERSION = "ablation_subset_manifest/1.0"
SUBSET_CONFIGURATIONS = ("B0", "B2", "B3", "F")

SUBSET_SELECTION_PROCEDURE = (
    "Validate all 43 crosswalk rows and their CV SHA-256 hashes. Group the rows "
    "by annotator_1_career_id. Using one random.Random(seed) instance, draw one "
    "row per career category in ascending career_id order from that category's "
    "rows sorted by candidate_id. Then draw two additional rows without "
    "replacement from the remaining rows whose category originally had more "
    "than one sample, sorted by candidate_id. Store the resulting 12 rows sorted "
    "by candidate_id. The same 12 candidates are used for B0, B2, B3, and F."
)


class SubsetSelectionError(ValueError):
    """The source crosswalk cannot produce the required frozen subset."""


def select_subset_rows(
    rows: Iterable[Mapping[str, str]],
    *,
    seed: int = SUBSET_SEED,
    expected_size: int = SUBSET_SIZE,
) -> list[dict[str, str]]:
    """Return the deterministic subset rows, sorted by candidate ID.

    Every row must carry a non-empty ``candidate_id`` and
    ``annotator_1_career_id``. The source must contain exactly 10 career
    categories so that one representative per category is well defined.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise SubsetSelectionError("seed must be an integer")
    if expected_size < 1:
        raise SubsetSelectionError("expected_size must be positive")

    cleaned: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for raw in rows:
        row = {key: (value or "").strip() for key, value in raw.items()}
        candidate_id = row.get("candidate_id", "")
        career_id = row.get("annotator_1_career_id", "")
        if not candidate_id:
            raise SubsetSelectionError("every crosswalk row needs a candidate_id")
        if candidate_id in seen_ids:
            raise SubsetSelectionError(f"duplicate candidate_id {candidate_id!r}")
        if not career_id:
            raise SubsetSelectionError(
                f"candidate {candidate_id!r} has no annotator_1_career_id"
            )
        seen_ids.add(candidate_id)
        cleaned.append(row)

    groups: dict[str, list[dict[str, str]]] = {}
    for row in cleaned:
        groups.setdefault(row["annotator_1_career_id"], []).append(row)
    if len(groups) != 10:
        raise SubsetSelectionError(
            f"subset selection requires exactly 10 career categories; found {len(groups)}"
        )
    if expected_size < len(groups) or expected_size > len(cleaned):
        raise SubsetSelectionError(
            f"expected_size={expected_size} cannot cover {len(groups)} categories "
            f"from {len(cleaned)} rows"
        )

    rng = random.Random(seed)
    selected: list[dict[str, str]] = []
    for career_id in sorted(groups):
        category_rows = sorted(groups[career_id], key=lambda row: row["candidate_id"])
        selected.append(rng.choice(category_rows))

    selected_ids = {row["candidate_id"] for row in selected}
    extra_pool = sorted(
        (
            row for row in cleaned
            if row["candidate_id"] not in selected_ids
            and len(groups[row["annotator_1_career_id"]]) > 1
        ),
        key=lambda row: row["candidate_id"],
    )
    extra_count = expected_size - len(selected)
    if len(extra_pool) < extra_count:
        raise SubsetSelectionError(
            "not enough remaining rows from categories with more than one sample "
            f"to draw {extra_count} additional candidates"
        )
    selected.extend(rng.sample(extra_pool, extra_count))

    if len(selected) != expected_size:
        raise SubsetSelectionError(
            f"selection produced {len(selected)} rows; expected {expected_size}"
        )
    career_ids = {row["annotator_1_career_id"] for row in selected}
    if career_ids != set(groups):
        raise SubsetSelectionError("selection does not cover every career category")
    return sorted(selected, key=lambda row: row["candidate_id"])
