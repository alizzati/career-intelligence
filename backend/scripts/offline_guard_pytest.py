"""Offline launcher. Blocks database and Gemini configuration for THIS process, then runs pytest
(or a standalone test module with --module). Any test that tries to reach the DB therefore errors
instead of mutating it. Skips are only tolerated for the two known DB-gated reasons.

Why set values in os.environ here: PowerShell deletes env vars assigned ''. python-dotenv (override
=False) does not override a key already present in os.environ, even when empty.

Why sys.path is extended: running `python scripts\\offline_guard_pytest.py` puts scripts/ (not
backend/) at sys.path[0], so `tests` and `app` would not be importable. The backend root is derived
from this file's location, not from the current working directory."""
import os
import runpy
import sys
import tempfile
import xml.etree.ElementTree as ET

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

for _name in ("CAREER_DB_URL", "CAREER_DB_PASSWORD", "GEMINI_API_KEY", "CAREER_RUN_RUNTIME_DB_TESTS"):
    os.environ[_name] = ""

import pytest  # noqa: E402  (after env is blocked)

ALLOWED_SKIP = ("CAREER_RUN_RUNTIME_DB_TESTS", "database not configured")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--module"]:
        if len(argv) != 2:
            print("usage: offline_guard_pytest.py --module <dotted.module.name>")
            return 2
        # An exception inside the module (AssertionError, ImportError, ...) -> traceback, exit 1.
        runpy.run_module(argv[1], run_name="__main__")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "result.xml")
        code = int(pytest.main(["-q", "-rs", f"--junitxml={xml_path}", *argv]))
        if not os.path.exists(xml_path):
            print("GUARD: no junit report produced")
            return 1
        skipped, unexpected = 0, []
        for case in ET.parse(xml_path).getroot().iter("testcase"):
            node = case.find("skipped")
            if node is not None:
                skipped += 1
                if not any(reason in (node.get("message") or "") for reason in ALLOWED_SKIP):
                    unexpected.append(f"{case.get('classname')}::{case.get('name')}")
        print(f"GUARD: pytest exit={code}; skipped={skipped}; unexpected_skips={len(unexpected)}")
        for item in unexpected:
            print("GUARD: unexpected skip:", item)
        return code or (1 if unexpected else 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))