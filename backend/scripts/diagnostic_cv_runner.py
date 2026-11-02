"""CLI: run every CV through the real Career Intelligence pipeline and record traces.

Usage (from the repository root):

    cd backend
    python -m scripts.diagnostic_cv_runner --dry-run
    python -m scripts.diagnostic_cv_runner --approve-live-llm --run-id my-run

What it does
------------
Runs ``POST /analysis/cv`` in-process through a FastAPI ``TestClient`` with the real
``CareerWorkflow`` and real agents, records the intermediate stages, and writes:

    <output-dir>/<run_id>/run.json
    <output-dir>/<run_id>/manifest.csv
    <output-dir>/<run_id>/summary.md
    <output-dir>/<run_id>/traces/<cv_id>.trace.json
    <output-dir>/<run_id>/analysis_logs/<cv_id>.analysis_log.json

Safety
------
* Requires the isolated test database (same gate as ``scripts/manual_validation.py``).
* Refuses live LLM calls unless ``--approve-live-llm`` is passed.
* Never overwrites an existing run directory.
* Never writes the original file name or any raw CV text.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.diagnostics.runner import (  # noqa: E402
    REPO_ROOT,
    DiagnosticOptions,
    DiagnosticSafetyError,
    default_run_id,
    discover_cvs,
    run_diagnostic,
    select_cvs,
)

DEFAULT_INPUT_DIR = REPO_ROOT / "frontend" / "dignostic_testing" / "input_cvs"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "frontend" / "dignostic_testing" / "results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diagnostic_cv_runner",
        description="Diagnostic CV testing through the real pipeline (artifacts only, not experiments).",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
        help=f"Folder containing the CV files (default: {DEFAULT_INPUT_DIR}).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Parent folder for run artifacts (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run folder name. Defaults to a UTC timestamp plus a short suffix. Never overwritten.",
    )
    parser.add_argument(
        "--cv", action="append", default=[], metavar="NAME",
        help="Restrict the run to a file name or stem. Repeatable.",
    )
    parser.add_argument(
        "--target-career-id", default=None,
        help="Optional canonical target career. Omit to let the system rank all careers.",
    )
    parser.add_argument(
        "--max-cvs", type=int, default=None,
        help="Process at most N CVs (useful for a first smoke run).",
    )
    parser.add_argument(
        "--fake-llm", action="store_true",
        help="Use a labeled plumbing test double. Validates the runner only, not diagnostic validity.",
    )
    parser.add_argument(
        "--approve-live-llm", action="store_true",
        help="Allow real provider calls with the CV content. Required for a real diagnostic run.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the resolved plan (CVs, output folder, LLM mode) and exit without running.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        files = select_cvs(discover_cvs(args.input_dir), tuple(args.cv))
        if args.max_cvs is not None:
            files = files[: max(1, args.max_cvs)]
        run_id = args.run_id or default_run_id()
        options = DiagnosticOptions(
            run_id=run_id,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            approve_live_llm=args.approve_live_llm,
            fake_llm=args.fake_llm,
            target_career_id=args.target_career_id,
            selected=tuple(args.cv),
            max_cvs=args.max_cvs,
        )
        if args.dry_run:
            if args.fake_llm and args.approve_live_llm:
                raise DiagnosticSafetyError("Choose exactly one LLM mode: --fake-llm or --approve-live-llm.")
            mode = "fake_llm" if args.fake_llm else ("live_llm" if args.approve_live_llm else "unset")
            print(json.dumps({
                "dry_run": True,
                "run_id": run_id,
                "run_dir": str(args.output_dir / run_id),
                "run_dir_exists": (args.output_dir / run_id).exists(),
                "input_dir": str(args.input_dir),
                "cv_count": len(files),
                "cvs": [path.name for path in files],
                "llm_mode": mode,
                "target_career_id": args.target_career_id,
            }, indent=2))
            return 0
        result = run_diagnostic(options)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    except DiagnosticSafetyError as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__,
                          "message": str(exc)[:400]}, indent=2))
        return 2
    except Exception as exc:  # type only: a driver error may carry connection details
        print(json.dumps({"status": "FAIL", "error_type": type(exc).__name__}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
