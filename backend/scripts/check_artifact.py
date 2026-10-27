"""Validate a manual-validation artifact against the contract. Reads one JSON file; prints
violations (paths/rules only, never values). Exit 0 = valid, 1 = violations, 2 = usage/IO error."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.inspection.contract import validate_artifact  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python scripts/check_artifact.py <artifact.json>")
        return 2
    try:
        artifact = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read artifact ({type(exc).__name__})")
        return 2
    problems = validate_artifact(artifact)
    for problem in problems:
        print("VIOLATION:", problem)
    print("CONTRACT OK" if not problems else f"{len(problems)} violation(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))