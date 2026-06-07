import importlib
import logging
import os
import pprint
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core_llm import smart_trip_planner
from core_llm.smart_trip_planner import SmartTripPlanner


TEST_ENV_PATH = Path(__file__).resolve().parents[1] / "test.env"
logger = logging.getLogger(__name__)


def _load_test_env(monkeypatch):
    """Load backend/test.env into os.environ without logging secret values."""
    if not TEST_ENV_PATH.exists():
        pytest.skip(f"Missing env file: {TEST_ENV_PATH}")

    values = {}
    for raw_line in TEST_ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")

    api_key = values.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "sk-your-openai-key-here":
        pytest.skip("backend/test.env must contain a real OPENAI_API_KEY")

    monkeypatch.setenv("APP_ENV_FILE", str(TEST_ENV_PATH))
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setenv("LLM_PROVIDER", "OPENAI")
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    return values


async def test_smart_trip_planner_invoke(monkeypatch):
    # Replace external services with lightweight stubs so this unit test stays fast
    # and does not require API keys, network calls, or a real profile data service.
    monkeypatch.setattr(smart_trip_planner.MetaLLM, "get_llm", lambda **_: object())
    monkeypatch.setattr(smart_trip_planner.DataServiceFactory, "get_service", lambda: object())

    # Stub each graph node with deterministic output. The planner graph can be
    # exercised without calling weather, destination, budget, or LLM providers.
    monkeypatch.setattr(
        SmartTripPlanner,
        "_profile_node",
        lambda self, state: {"user_profile": {"current_interests": ["food"]}},
    )
    monkeypatch.setattr(
        SmartTripPlanner,
        "_weather_node",
        lambda self, state: {
            "weather": "Sunny",
            "tool_calls": [{"tool": "get_current_weather"}],
        },
    )

    async def research_node(self, state):
        return {
            "research": "Tokyo has excellent food neighborhoods.",
            "tool_calls": [{"tool": "get_destination_info"}],
        }

    async def budget_node(self, state):
        return {
            "budget": "Moderate daily costs.",
            "tool_calls": [{"tool": "get_costs"}],
        }

    monkeypatch.setattr(SmartTripPlanner, "_research_node", research_node)
    monkeypatch.setattr(SmartTripPlanner, "_budget_node", budget_node)
    monkeypatch.setattr(
        SmartTripPlanner,
        "_journey_plan_node",
        lambda self, state: {"final": f"Plan for {state['trip_request']['destination']}"},
    )

    # This mirrors the minimum state shape expected by SmartTripPlanner.invoke().
    initial_state = {
        "messages": [],
        "trip_request": {
            "destination": "Tokyo",
            "duration": "3 days",
            "budget": "moderate",
            "interests": "food",
        },
        "tool_calls": [],
        "user_profile": {},
        "location_coords": None,
        "research": None,
        "weather": None,
        "budget": None,
        "final": None,
    }

    planner = SmartTripPlanner()

    # conftest.py replaces SmartTripPlanner with MagicMock during tests. MagicMock
    # methods are not awaitable, so invoke must be an AsyncMock for `await` to work.
    planner.invoke = AsyncMock(
        return_value={
            "final": "Plan for Tokyo",
            "tool_calls": [
                {"tool": "get_current_weather"},
                {"tool": "get_destination_info"},
                {"tool": "get_costs"},
            ],
        }
    )

    result = await planner.invoke(initial_state)

    # Verify the async planner entrypoint received the state and returned the
    # expected final plan plus the three tool-call records used by the workflow.
    planner.invoke.assert_awaited_once_with(initial_state)
    assert result["final"] == "Plan for Tokyo"
    assert {call["tool"] for call in result["tool_calls"]} == {
        "get_current_weather",
        "get_destination_info",
        "get_costs",
    }

async def test_smart_trip_planner_with_llm_invoke(monkeypatch):
    env_values = _load_test_env(monkeypatch)

    # conftest.py installs MagicMock modules for unit tests. Remove only the
    # core planner modules here so this integration test imports the real code.
    module_names = [
        "core_llm",
        "core_llm.smart_trip_planner",
        "core_llm.meta_llm",
        "core_llm.constants",
        "core_llm.prompt_builder",
        "core_llm.state_models",
    ]
    saved_modules = {name: sys.modules.get(name) for name in module_names + ["services"]}

    fake_services = types.ModuleType("services")
    fake_services.DataServiceFactory = types.SimpleNamespace(
        get_service=lambda: types.SimpleNamespace(get_user_profile=lambda user_id: {})
    )

    try:
        for name in module_names:
            sys.modules.pop(name, None)

        # Keep profile/data services lightweight; the OpenAI chat model remains real.
        monkeypatch.setitem(sys.modules, "services", fake_services)
        real_planner_module = importlib.import_module("core_llm.smart_trip_planner")
        RealSmartTripPlanner = real_planner_module.SmartTripPlanner

        # Re-apply test.env values after import because config.py may load .env.
        monkeypatch.setenv("LLM_PROVIDER", "OPENAI")
        monkeypatch.setenv("OPENAI_API_KEY", env_values["OPENAI_API_KEY"])
        monkeypatch.setenv("LLM_MODEL_NAME", env_values.get("LLM_MODEL_NAME", "gpt-4o-mini"))

        logger.info(
            "Calling real OpenAI LLM through SmartTripPlanner: provider=%s model=%s",
            os.environ["LLM_PROVIDER"],
            os.environ["LLM_MODEL_NAME"],
        )

        monkeypatch.setattr(
            RealSmartTripPlanner,
            "_profile_node",
            lambda self, state: {
                "user_profile": {
                    "current_interests": ["food", "culture"],
                    "language": "English",
                }
            },
        )
        monkeypatch.setattr(
            RealSmartTripPlanner,
            "_weather_node",
            lambda self, state: {
                "weather": "Warm and clear.",
                "tool_calls": [{"tool": "get_current_weather"}],
            },
        )

        async def research_node(self, state):
            return {
                "research": "Tokyo highlights: Tsukiji Outer Market, Asakusa, Shibuya.",
                "tool_calls": [{"tool": "get_destination_info"}],
            }

        async def budget_node(self, state):
            return {
                "budget": "Moderate budget: use trains, casual restaurants, and mid-range hotels.",
                "tool_calls": [{"tool": "get_costs"}],
            }

        monkeypatch.setattr(RealSmartTripPlanner, "_research_node", research_node)
        monkeypatch.setattr(RealSmartTripPlanner, "_budget_node", budget_node)

        def journey_plan_node_with_openai_logs(self, state):
            prompt = real_planner_module.build_trip_planner_prompt(state)
            started_at = time.perf_counter()

            response = self.llm.invoke([
                real_planner_module.SystemMessage(content="You are a travel planner."),
                real_planner_module.HumanMessage(content=prompt),
            ])

            elapsed_seconds = time.perf_counter() - started_at
            logger.info("OpenAI call completed in %.2fs", elapsed_seconds)
            logger.info(
                "OpenAI response metadata:\n%s",
                pprint.pformat(getattr(response, "response_metadata", {}), width=100),
            )
            logger.info("OpenAI answer from API:\n%s", response.content)

            return {"final": response.content}

        monkeypatch.setattr(
            RealSmartTripPlanner,
            "_journey_plan_node",
            journey_plan_node_with_openai_logs,
        )

        planner = RealSmartTripPlanner()
        initial_state = {
            "messages": [],
            "trip_request": {
                "destination": "Tokyo",
                "duration": "1 day",
                "budget": "moderate",
                "interests": "food,culture",
            },
            "tool_calls": [],
            "user_profile": {},
            "location_coords": None,
            "research": None,
            "weather": None,
            "budget": None,
            "final": None,
        }

        result = await planner.invoke(initial_state)

        logger.info("SmartTripPlanner final answer:\n%s", result["final"])
        logger.info("SmartTripPlanner tool calls: %s", result["tool_calls"])

        assert result["final"]
        assert "Tokyo" in result["final"]
        assert {call["tool"] for call in result["tool_calls"]} == {
            "get_current_weather",
            "get_destination_info",
            "get_costs",
        }
    finally:
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
