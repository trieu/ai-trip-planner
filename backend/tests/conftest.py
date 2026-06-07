# tests/conftest.py

import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# break circular import chain ONLY (targeted)
sys.modules["tools.travel_tools"] = MagicMock()
sys.modules["services.knowledge_service"] = MagicMock()
sys.modules["core_llm.meta_llm"] = MagicMock()
sys.modules["core_llm"] = MagicMock()
sys.modules["core_llm.smart_trip_planner"] = MagicMock()
