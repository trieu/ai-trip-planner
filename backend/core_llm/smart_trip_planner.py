import logging
import os

from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.instrumentation import using_attributes

from core_llm.prompt_builder import DEFAULT_BUDGET_LEVEL, build_trip_planner_prompt
from core_llm.state_models import TripState
from tools.text_utils import deduplicate_tool_calls, merge_unique_csv
from tools.weather_tools import get_current_weather
from tools.travel_tools import get_costs, get_destination_info
from services import DataServiceFactory
from meta_llm import MetaLLM

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("smart_trip_planner")

# ================================
# Constants & Configuration
# ================================
LLM_TEMPERATURE = 0.7


# ================================
# Observability Setup
# ================================

def setup_observability():
    """Initializes OpenTelemetry and Phoenix for tracing LLM calls."""
    default_endpoint = "http://localhost:6006/v1/traces"
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", default_endpoint)
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(tracer_provider)
    LangChainInstrumentor().instrument()


def safe_attributes(attrs: Dict[str, Any]):
    """Safely wraps observability attributes to prevent runtime crashes."""
    try:
        return using_attributes(attributes=attrs)
    except Exception:
        from contextlib import nullcontext
        return nullcontext()


setup_observability()


# ================================
# Core Planner Class
# ================================


class SmartTripPlanner:
    """Encapsulates the LangGraph pipeline for trip planning."""

    def __init__(self):
        self.llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)
        self.embeddings = MetaLLM.get_embeddings()
        self.profile_service = DataServiceFactory.get_service()
        self.app = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(TripState)

        builder.add_node("load_profile", self._profile_node)
        builder.add_node("research", self._research_node)
        builder.add_node("weather", self._weather_node)
        builder.add_node("budget", self._budget_node)
        builder.add_node("aggregate", self._aggregate_node)
        builder.add_node("journey_plan", self._journey_plan_node)

        # Start
        builder.add_edge(START, "load_profile")

        # Parallel branches
        builder.add_edge("load_profile", "research")
        builder.add_edge("load_profile", "weather")
        builder.add_edge("load_profile", "budget")

        # Optional dependency (only if needed)
        # builder.add_edge("weather", "research")

        # Fan-in to aggregation node
        builder.add_edge("research", "aggregate")
        builder.add_edge("weather", "aggregate")
        builder.add_edge("budget", "aggregate")

        # Final synthesis
        builder.add_edge("aggregate", "journey_plan")
        builder.add_edge("journey_plan", END)

        return builder.compile()

    # --- Node Methods ---
    def _profile_node(self, state: TripState) -> Dict[str, Any]:
        """Loads the user's saved profile data."""
        user_id = state["trip_request"].get("user_id")
        current_interests = state["trip_request"].get("interests")
        profile = {}

        if user_id:
            with safe_attributes({"service.name": "DataService", "operation": "load_profile", "user.id": user_id}):
                profile = self.profile_service.get_user_profile(user_id)

        profile.setdefault("current_interests", current_interests.split(
            ",") if current_interests else [])
        return {"user_profile": profile or {}}

    def _research_node(self, state: TripState) -> Dict[str, Any]:
        """Gathers factual information about the destination."""
        dest = state["trip_request"]["destination"]
        agent = self.llm.bind_tools([get_destination_info])

        with safe_attributes({"agent.type": "research"}):
            res = agent.invoke([
                SystemMessage(
                    content=f"You are a travel research agent. DO NOT ask questions. Task: Travel info for {dest}"),
                HumanMessage(content="Execute task.")
            ])

        calls, location_coords, summary = [], None, res.content

        # Handle potential tool calls generated by the LLM
        if getattr(res, "tool_calls", None):
            try:
                tn = ToolNode([get_destination_info])
                tool_res = tn.invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                location_coords = tool_res.get("location_coords")
                calls.append({
                    "tool": "get_destination_info",
                    "args": {
                        "destination": dest
                    }
                })
            except Exception:
                pass

        return {"research": summary, "location_coords": location_coords, "tool_calls": calls}

    def _weather_node(self, state: TripState) -> Dict[str, Any]:
        """Gathers weather information about the destination."""

        trip = state.get("trip_request", {})
        dest = trip.get("destination")

        # -------------------------
        # 1. Validate input
        # -------------------------
        if not dest or not isinstance(dest, str):
            logger.error(f"[weather_node] invalid destination: {dest}")
            return {
                "weather": "Weather unavailable due to invalid destination.",
                "tool_calls": []
            }

        dest = dest.strip()

        # -------------------------
        # 2. Call weather tool (safe)
        # -------------------------
        try:
            weather_info = get_current_weather.invoke({
                "location": dest
            })
        except Exception as e:
            logger.error(f"[weather_node] weather tool failed: {e}")
            weather_info = "Weather service unavailable."

        calls = [{
            "tool": "get_current_weather",
            "args": {"location": dest}
        }]

        existing = state.get("tool_calls", [])

        return {
            "weather": weather_info,
            "tool_calls": existing + calls
        }

    def _budget_node(self, state: TripState) -> Dict[str, Any]:
        """Calculates expected costs based on destination and budget level."""
        dest = state["trip_request"]["destination"]
        lvl = state["trip_request"].get("budget", DEFAULT_BUDGET_LEVEL)
        agent = self.llm.bind_tools([get_costs])

        with safe_attributes({"agent.type": "budget"}):
            res = agent.invoke([
                SystemMessage(
                    content=f"You are a travel cost analyst. DO NOT ask questions. Task: Estimate costs for {dest} at {lvl} budget."),
                HumanMessage(content="Execute task.")
            ])

        calls, summary = [], res.content

        if getattr(res, "tool_calls", None):
            try:
                tn = ToolNode([get_costs])
                tool_res = tn.invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_costs", "args": {
                             "destination": dest, "budget_level": lvl}})
            except Exception:
                pass

        return {"budget": summary, "tool_calls": calls}

    def _aggregate_node(self, state: TripState) -> Dict[str, Any]:
        """
        Merge parallel outputs safely and deduplicate tool calls.
        """
        tool_calls = state.get("tool_calls", [])
        deduped_calls = deduplicate_tool_calls(tool_calls)
        return {
            "tool_calls": deduped_calls
        }

    def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        """Synthesizes research, budget, and profile into a final itinerary."""

        prompt = build_trip_planner_prompt(state)

        with safe_attributes({"agent.type": "journey_plan"}):
            role = "You are a world-class travel planner creating a personalized itinerary based on user preferences and local insights."
            res = self.llm.invoke([
                SystemMessage(content=role),
                HumanMessage(content=prompt)
            ])

        return {"final": res.content}

    def invoke(self, state: dict) -> dict:
        """Entry point to run the compiled graph."""
        return self.app.invoke(state)
