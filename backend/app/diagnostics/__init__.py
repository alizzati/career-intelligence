"""Diagnostic CV testing (read-only instrumentation of the real pipeline).

This package exists to RUN the real application and RECORD what it already produced.
It never changes agent inputs or outputs, never re-scores careers, never recalculates
skill gaps, and never rewrites the Step 12 verification result. Nothing here is
imported by the API, the workflow, or the agents.

Two modules:

* ``trace``  -- builds one ``diagnostic_trace/1.0`` document and its CSV row.
* ``runner`` -- drives ``POST /analysis/cv`` per CV and writes the artifacts.
"""
from app.diagnostics.trace import (
    CSV_COLUMNS,
    MANIFEST_SCHEMA_VERSION,
    SKILL_GAP_CATEGORIES,
    STAGE_ORDER,
    TRACE_SCHEMA_VERSION,
    build_csv_row,
    build_trace,
    observe_consistency,
)

__all__ = [
    "CSV_COLUMNS",
    "MANIFEST_SCHEMA_VERSION",
    "SKILL_GAP_CATEGORIES",
    "STAGE_ORDER",
    "TRACE_SCHEMA_VERSION",
    "build_csv_row",
    "build_trace",
    "observe_consistency",
]
