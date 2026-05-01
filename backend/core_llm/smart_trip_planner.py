import logging
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

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

if Settings().ENABLE_TELEMETRY:
    logger.info("Telemetry enabled for AI observability, PHOENIX_COLLECTOR_ENDPOINT: %s",
                Settings().PHOENIX_COLLECTOR_ENDPOINT)
    setup_observability()


class SmartTripPlanner:
    """
    LangGraph-based orchestrator for trip planning.

    Responsibilities:
    - Load user profile
    - Gather research data
    - Fetch weather
    - Estimate budget
    - Generate itinerary
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

        # Parallel branches
        builder.add_edge("load_profile", "research")
        builder.add_edge("load_profile", "weather")
        builder.add_edge("load_profile", "budget")

        # Fan-in
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
        """Load user profile safely."""
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
        """Fetch weather with defensive validation."""
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

    def _research_node(self, state: TripState) -> Dict[str, Any]:
        """Fetch destination information via tool."""
        dest = state["trip_request"]["destination"]

        # Bind tool with required choice to ensure it's used if the agent tries to skip
        agent = self.llm.bind_tools(
            [get_destination_info], tool_choice="required")

        with safe_attributes({"agent.type": AGENT_RESEARCH}):
            res = agent.invoke([
                SystemMessage(content=f"Travel info for {dest}"),
                HumanMessage(content="Execute")
            ])

        summary = res.content
        calls = []

        if getattr(res, "tool_calls", None):
            try:
                tool_res = ToolNode([get_destination_info]
                                    ).invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_destination_info",
                             "args": {"destination": dest}})
            except Exception as e:
                logger.warning(f"[research_node] tool failed: {e}")

        return {"research": summary, "tool_calls": calls}

    def _budget_node(self, state: TripState) -> Dict[str, Any]:
        """Estimate travel cost."""
        dest = state["trip_request"]["destination"]
        lvl = state["trip_request"].get("budget", DEFAULT_BUDGET_LEVEL)

        # Bind tool with required choice to ensure it's used if the agent tries to skip
        agent = self.llm.bind_tools([get_costs], tool_choice="required")

        with safe_attributes({"agent.type": AGENT_BUDGET}):
            res = agent.invoke([
                SystemMessage(content=f"Estimate costs for {dest} at {lvl}"),
                HumanMessage(content="Execute")
            ])

        summary = res.content
        calls = []

        if getattr(res, "tool_calls", None):
            try:
                tool_res = ToolNode([get_costs]).invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_costs", "args": {
                             "destination": dest, "budget_level": lvl}})
            except Exception as e:
                logger.warning(f"[budget_node] tool failed: {e}")

        return {"budget": summary, "tool_calls": calls}

    def _aggregate_node(self, state: TripState) -> Dict[str, Any]:
        """Merge and deduplicate tool calls."""
        return {"tool_calls": deduplicate_tool_calls(state.get("tool_calls", []))}

    def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        """Generate final itinerary."""
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

    def invoke(self, state: dict) -> dict:
        """Run full pipeline."""
        return self.app.invoke(state)