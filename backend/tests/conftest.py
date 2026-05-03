# tests/conftest.py

import sys
from unittest.mock import MagicMock

# break circular import chain ONLY (targeted)
sys.modules["tools.travel_tools"] = MagicMock()
sys.modules["services.knowledge_service"] = MagicMock()
sys.modules["meta_llm"] = MagicMock()
sys.modules["core_llm"] = MagicMock()
sys.modules["core_llm.smart_trip_planner"] = MagicMock()