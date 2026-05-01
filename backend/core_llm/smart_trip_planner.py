import logging
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END, START

from core_llm.prompt_builder import DEFAULT_BUDGET_LEVEL, build_trip_planner_prompt
from core_llm.state_models import TripState
from core_llm.observer_utils import safe_attributes, setup_observability
from core_llm.constants import *

from tools.text_utils import deduplicate_tool_calls
from tools.weather_tools import get_current_weather
from tools.travel_tools import get_costs, get_destination_info

from services import DataServiceFactory
from meta_llm import MetaLLM

# ============================================================
# Logging
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(SERVICE_NAME)


class SmartTripPlanner:
    """
    LangGraph-based orchestrator for trip planning.

    FIXED:
    - Removed ToolNode (source of config errors)
    - Direct async tool execution
    - Stable async pipeline
    """

    def __init__(self):
        self.llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)
        self.profile_service = DataServiceFactory.get_service()
        self.app = self._build_graph()

    # ============================================================
    # Graph Definition
    # ============================================================
    def _build_graph(self):
        builder = StateGraph(TripState)

        builder.add_node("load_profile", self._profile_node)
        builder.add_node("research", self._research_node)
        builder.add_node("weather", self._weather_node)
        builder.add_node("budget", self._budget_node)
        builder.add_node("aggregate", self._aggregate_node)
        builder.add_node("journey_plan", self._journey_plan_node)

        builder.add_edge(START, "load_profile")

        # Parallel execution
        builder.add_edge("load_profile", "research")
        builder.add_edge("load_profile", "weather")
        builder.add_edge("load_profile", "budget")

        builder.add_edge("research", "aggregate")
        builder.add_edge("weather", "aggregate")
        builder.add_edge("budget", "aggregate")

        builder.add_edge("aggregate", "journey_plan")
        builder.add_edge("journey_plan", END)

        return builder.compile()

    # ============================================================
    # Nodes
    # ============================================================

    def _profile_node(self, state: TripState) -> Dict[str, Any]:
        user_id = state["trip_request"].get("user_id")
        interests = state["trip_request"].get("interests")

        profile = {}

        if user_id:
            with safe_attributes({"agent.type": AGENT_PROFILE, "user.id": user_id}):
                profile = self.profile_service.get_user_profile(user_id)

        profile.setdefault(
            "current_interests",
            interests.split(",") if interests else []
        )

        return {"user_profile": profile}

    def _weather_node(self, state: TripState) -> Dict[str, Any]:
        dest = state.get("trip_request", {}).get("destination")

        if not dest or not isinstance(dest, str):
            logger.error("[weather_node] invalid destination")
            return {"weather": INVALID_DESTINATION_MSG, "tool_calls": []}

        try:
            weather = get_current_weather.invoke({"location": dest.strip()})
        except Exception as e:
            logger.error(f"[weather_node] failed: {e}")
            weather = DEFAULT_WEATHER_FALLBACK

        return {
            "weather": weather,
            "tool_calls": [{"tool": "get_current_weather", "args": {"location": dest}}]
        }

    # ============================================================
    # ✅ RESEARCH NODE (FIXED)
    # ============================================================
    async def _research_node(self, state: TripState) -> Dict[str, Any]:
        dest = state["trip_request"]["destination"]

        summary = ""
        calls = []

        try:
            # 🔥 DIRECT TOOL CALL (NO ToolNode)
            summary = await get_destination_info.ainvoke({
                "destination": dest
            })

            calls.append({
                "tool": "get_destination_info",
                "args": {"destination": dest}
            })

        except Exception as e:
            logger.error(f"[research_node] tool failed: {e}")
            summary = "Failed to fetch destination info."

        return {"research": summary, "tool_calls": calls}

    # ============================================================
    # ✅ BUDGET NODE (FIXED)
    # ============================================================
    async def _budget_node(self, state: TripState) -> Dict[str, Any]:
        dest = state["trip_request"]["destination"]
        lvl = state["trip_request"].get("budget", DEFAULT_BUDGET_LEVEL)

        summary = ""
        calls = []

        try:
            summary = await get_costs.ainvoke({
                "destination": dest,
                "budget_level": lvl
            })

            calls.append({
                "tool": "get_costs",
                "args": {"destination": dest, "budget_level": lvl}
            })

        except Exception as e:
            logger.error(f"[budget_node] tool failed: {e}")
            summary = "Failed to estimate costs."

        return {"budget": summary, "tool_calls": calls}

    # ============================================================
    def _aggregate_node(self, state: TripState) -> Dict[str, Any]:
        return {"tool_calls": deduplicate_tool_calls(state.get("tool_calls", []))}

    def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        prompt = build_trip_planner_prompt(state)

        with safe_attributes({"agent.type": AGENT_JOURNEY}):
            res = self.llm.invoke([
                SystemMessage(content="You are a travel planner."),
                HumanMessage(content=prompt)
            ])

        return {"final": res.content}

    # ============================================================
    # Public API
    # ============================================================

    async def invoke(self, state: dict) -> dict:
        return await self.app.ainvoke(state)