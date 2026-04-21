import os
import operator
import httpx
from typing import Optional, List, Dict, Any
from typing_extensions import TypedDict, Annotated

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.instrumentation import using_attributes

from services import DataServiceFactory
from meta_llm import MetaLLM

# ================================
# Constants & Configuration
# ================================
LLM_TEMPERATURE = 0.7
SEARCH_TIMEOUT_SECONDS = 10.0
MAX_SEARCH_RESULTS = 2
DEFAULT_BUDGET_LEVEL = "moderate"

# ================================
# Observability Setup
# ================================


def setup_observability():
    """Initializes OpenTelemetry and Phoenix for tracing LLM calls."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT",
                         "http://localhost:6006/v1/traces")
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
# to merge duplicate data 
# ================================
def merge_unique_csv(prof: dict, *keys: str, sep: str = ', ') -> str:
    """
    Merge multiple interest fields from a profile dict into a unique, ordered CSV string.

    - Supports values as: None, str, list/tuple/set, mixed types
    - Deduplicates while preserving order (first occurrence wins)
    - Casts all values to string
    """

    def to_list(v):
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, (list, tuple, set)):
            return list(v)
        return [str(v)]

    seen = set()
    merged = []

    for key in keys:
        values = to_list(prof.get(key))
        for item in values:
            s = str(item)
            if s not in seen:
                seen.add(s)
                merged.append(s)

    return sep.join(merged)

# ================================
# Graph State Definition
# ================================


class TripState(TypedDict):
    """Defines the state passed between LangGraph nodes."""
    messages: Annotated[List[BaseMessage], operator.add]
    trip_request: Dict[str, Any]
    user_profile: Dict[str, Any]
    research: Optional[str]
    budget: Optional[str]
    final: Optional[str]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]

# ================================
# Tools & Helpers
# ================================


def _search_or_fallback(query: str, fallback_instruction: str) -> str:
    """Attempts a Tavily web search, falling back to LLM generation if it fails."""
    tavily_key = os.getenv("TAVILY_API_KEY")

    if tavily_key:
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT_SECONDS) as client:
                SEARCH_URL = "https://api.tavily.com/search"
                resp = client.post(
                    SEARCH_URL,
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": MAX_SEARCH_RESULTS,
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("answer"):
                    return data["answer"]
                if data.get("results"):
                    return data["results"][0].get("content", "")
        except Exception:
            pass  # Silently fallback to LLM on search failure

    # Fallback to LLM if Tavily fails or is unconfigured
    llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)
    res = llm.invoke([
        SystemMessage(content="Provide a concise travel guide."),
        HumanMessage(content=fallback_instruction)
    ])
    return str(res.content)


@tool
def get_destination_info(destination: str) -> str:
    """Get weather, safety, and visa info for a destination."""
    return _search_or_fallback(
        f"{destination} travel info",
        f"Summarize travel essentials for {destination}."
    )


@tool
def get_costs(destination: str, budget_level: str) -> str:
    """Get average costs for food, transport, and lodging."""
    return _search_or_fallback(
        f"{destination} travel costs {budget_level}",
        f"Estimated costs for {budget_level} travel in {destination}."
    )

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
        """Constructs and compiles the LangGraph state machine."""
        builder = StateGraph(TripState)

        # Register nodes
        builder.add_node("load_profile", self._profile_node)
        builder.add_node("research", self._research_node)
        builder.add_node("budget", self._budget_node)
        builder.add_node("journey_plan", self._journey_plan_node)

        # Define edges (Flow logic)
        builder.add_edge(START, "load_profile")

        # Parallel execution for research and budget
        builder.add_edge("load_profile", "research")
        builder.add_edge("load_profile", "budget")

        # Synthesize at the journey plan
        builder.add_edge("research", "journey_plan")
        builder.add_edge("budget", "journey_plan")
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

        profile.setdefault("current_interests", current_interests.split(",") if current_interests else [])
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

        calls, summary = [], res.content

        # Handle potential tool calls generated by the LLM
        if getattr(res, "tool_calls", None):
            try:
                tn = ToolNode([get_destination_info])
                tool_res = tn.invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_destination_info",
                             "args": {"destination": dest}})
            except Exception:
                pass

        return {"research": summary, "tool_calls": calls}

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

    def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        """Synthesizes research, budget, and profile into a final itinerary."""
        req = state['trip_request']
        prof = state.get('user_profile', {})
        
        user_interests_str = merge_unique_csv(
            prof,
            'current_interests',
            'personal_interests'
        )

        prompt = f"""
            # INPUT DATA
            - **Destination:** {req.get('destination')}
            - **Duration:** {req.get('duration')}
            - **Budget Level:** {req.get('budget', DEFAULT_BUDGET_LEVEL)}
            - **Local Research Data:** {state.get('research')}
            - **Estimated Costs:** {state.get('budget')}
            - **User Interests:** {user_interests_str}
            - **Target Language:** {prof.get('language', 'English')}

            # CONTENT GUIDELINES
            1. **Tone:** Professional, inspiring, and culturally respectful.
            2. **Integration:** You MUST weave the "Local Research Data" into the activities. Use specific names of landmarks, restaurants, or transport tips provided in the research.
            3. **Budget Adherence:** If the budget is "Budget," suggest street food and free walking tours. If "Luxury," suggest fine dining and private transfers.
            4. **Transport & Dining:** Every day MUST include at least one specific local dining suggestion and a "getting around" tip.

            # STRUCTURAL CONSTRAINTS (STRICT HTML)
            - **Introduction:** Start with a brief summary section:
                # Tổng quan nhanh
                <ul>
                    <li><strong>Điểm đến:</strong> ...</li>
                    <li><strong>Thời gian:</strong> ...</li>
                    <li><strong>Ngân sách:</strong> ...</li>
                    <li><strong>Sở thích:</strong> ...</li>
                </ul>
            - **Daily Headers:** Daily Header begin with #. Use exactly: # Ngày(Day) N: [Catchy Theme Name]
            - **Timeline Sections:** Timeline Section begin with ##. Every day MUST have exactly three sections: Sáng(Morning), Chiều(Afternoon), and Tối(Night).
            - **Activities:** Use <ul> and <li> <strong> [Catchy Activity Name] </strong> for activities. Keep descriptions concise but vivid (2-3 sentences per activity).
            - **NO Meta-Talk:** Do not say "Here is your itinerary" or "I hope you enjoy it." Start directly with the summary.
            - **NO Questions:** Do not ask the user for feedback or more info.

            # OUTPUT 
            - Generate the entire response ONLY in {prof.get('language', 'English')} language.
            - The final output MUST be in markdown format following the structure and tone guidelines above.
        """

        with safe_attributes({"agent.type": "journey_plan"}):
            role = "You are a world-class travel planner creating a personalized itinerary based on user preferences and local insights."
            res = self.llm.invoke([
                SystemMessage(
                    content=role),
                HumanMessage(content=prompt)
            ])

        return {"final": res.content}

    def invoke(self, state: dict) -> dict:
        """Entry point to run the compiled graph."""
        return self.app.invoke(state)
