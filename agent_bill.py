"""Convenience launcher for running Agent Bill from project root."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


# Ensure src/ is importable when running `python agent_bill.py`.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
PACKAGE_DIR = SRC_DIR / "agent_bill"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# If this file is imported as module `agent_bill`, expose package path so
# submodule imports like `agent_bill.models.bill` still work.
if __name__ != "__main__":
    __path__ = [str(PACKAGE_DIR)]


if __name__ == "__main__":
    # Avoid conflicts between this launcher filename and the package name.
    # When running from project root, `agent_bill.py` can shadow `src/agent_bill`.
    project_root_str = str(PROJECT_ROOT)
    sys.path[:] = [p for p in sys.path if p != project_root_str]
    module = sys.modules.get("agent_bill")
    if module is not None and not hasattr(module, "__path__"):
        sys.modules.pop("agent_bill", None)

    runpy.run_module("agent_bill.main", run_name="__main__")
