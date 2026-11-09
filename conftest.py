"""Global pytest bootstrap to prevent shadowing the agent_bill package."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

launcher_module = sys.modules.get("agent_bill")
if launcher_module is not None and not hasattr(launcher_module, "__path__"):
    sys.modules.pop("agent_bill", None)
