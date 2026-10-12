import importlib
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())   # make 'app' importable when run from backend/

TARGET = sys.argv[1] if len(sys.argv) > 1 else "app.services.skill_gap_service"

already = sorted(m for m in sys.modules if m == "google" or m.startswith("google."))
print(f"[1] google* modules already loaded BEFORE importing {TARGET}: {already or 'none'}")

triggers = []


def hook(event, args):
    if event != "import":
        return
    name = args[0]
    if name == "google" or name.startswith("google."):
        triggers.append(name)
        print(f"\n>>> first-time import of {name!r}; importing frames (outermost -> innermost):")
        frames = [f for f in traceback.extract_stack()[:-1]
                  if not f.filename.startswith("<frozen") and f.filename != __file__
                  and "importlib" not in f.filename]
        for f in frames[-8:]:
            print(f"      {f.filename}:{f.lineno}   {f.line}")


sys.addaudithook(hook)
importlib.import_module(TARGET)

after = sorted(m for m in sys.modules if m == "google" or m.startswith("google."))
print(f"\n[2] google* modules loaded AFTER importing {TARGET}: {after or 'none'}")
print(f"[3] first-time google imports caught while importing {TARGET}: {triggers or 'none'}")
if after and not triggers:
    print("    -> already loaded before the target import (see [1]): interpreter-startup "
          "mechanism (.pth / sitecustomize / usercustomize), not caused by the project.")