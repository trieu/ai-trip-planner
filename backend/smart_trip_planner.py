import os
import operator
import httpx
from typing import Optional, List, Dict, Any
from typing_extensions import TypedDict, Annotated

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.instrumentation import using_attributes

from services import DataServiceFactory

# ================================
# Constants & Configuration
# ================================
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME",  "gemini-2.5-flash-lite")
EMBEDDING_MODEL_NAME =  os.getenv("EMBEDDING_MODEL_NAME", "models/text-embedding-004")
LLM_TEMPERATURE = 0.7
SEARCH_TIMEOUT_SECONDS = 10.0
MAX_SEARCH_RESULTS = 2
DEFAULT_BUDGET_LEVEL = "moderate"

# ================================
# Observability Setup
# ================================
def setup_observability():
    """Initializes OpenTelemetry and Phoenix for tracing LLM calls."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
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
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": MAX_SEARCH_RESULTS,
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("answer"): return data["answer"]
                if data.get("results"): return data["results"][0].get("content", "")
        except Exception:
            pass # Silently fallback to LLM on search failure

    # Fallback to LLM if Tavily fails or is unconfigured
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL_NAME, temperature=LLM_TEMPERATURE)
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
        self.llm = ChatGoogleGenerativeAI(model=LLM_MODEL_NAME, temperature=LLM_TEMPERATURE)
        self.embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL_NAME)
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
        profile = {}

        if user_id:
            with safe_attributes({"service.name": "DataService", "operation": "load_profile", "user.id": user_id}):
                profile = self.profile_service.get_user_profile(user_id)

        return {"user_profile": profile or {}}

    def _research_node(self, state: TripState) -> Dict[str, Any]:
        """Gathers factual information about the destination."""
        dest = state["trip_request"]["destination"]
        agent = self.llm.bind_tools([get_destination_info])

        with safe_attributes({"agent.type": "research"}):
            res = agent.invoke([
                SystemMessage(content=f"You are a travel research agent. DO NOT ask questions. Task: Travel info for {dest}"),
                HumanMessage(content="Execute task.")
            ])

        calls, summary = [], res.content

        # Handle potential tool calls generated by the LLM
        if getattr(res, "tool_calls", None):
            try:
                tn = ToolNode([get_destination_info])
                tool_res = tn.invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_destination_info", "args": {"destination": dest}})
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
                SystemMessage(content=f"You are a travel cost analyst. DO NOT ask questions. Task: Estimate costs for {dest} at {lvl} budget."),
                HumanMessage(content="Execute task.")
            ])

        calls, summary = [], res.content

        if getattr(res, "tool_calls", None):
            try:
                tn = ToolNode([get_costs])
                tool_res = tn.invoke({"messages": [res]})
                summary = tool_res["messages"][-1].content
                calls.append({"tool": "get_costs", "args": {"destination": dest, "budget_level": lvl}})
            except Exception:
                pass

        return {"budget": summary, "tool_calls": calls}

    def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        """Synthesizes research, budget, and profile into a final itinerary."""
        req = state['trip_request']
        prof = state.get('user_profile', {})
        
        prompt = f"""
        You are an expert travel planner.
        STRICT RULES: DO NOT ask the user any questions. ALWAYS generate a complete itinerary.
        
        INPUT:
        - Destination: {req.get('destination')}
        - Duration: {req.get('duration')}
        - Budget: {req.get('budget', DEFAULT_BUDGET_LEVEL)}
        - Research: {state.get('research')}
        - Cost: {state.get('budget')}
        - User Profile: {prof}
        - User Language: {prof.get('language', 'English')}

        OUTPUT: Generate a full detailed day-by-day itinerary.
        """

        with safe_attributes({"agent.type": "journey_plan"}):
            res = self.llm.invoke([
                SystemMessage(content="You are a professional travel planner."),
                HumanMessage(content=prompt)
            ])

        return {"final": res.content}

    def invoke(self, state: dict) -> dict:
        """Entry point to run the compiled graph."""
        return self.app.invoke(state)