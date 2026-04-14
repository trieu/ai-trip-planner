import os
import json
import operator
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv
import httpx

# LangChain / LangGraph imports
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict, Annotated
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.vectorstores import InMemoryVectorStore
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# OpenTelemetry / Phoenix Observability
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.langchain import LangChainInstrumentor
from openinference.instrumentation import using_prompt_template, using_attributes

from services.data_service import DataServiceFactory

load_dotenv(find_dotenv())

# --- Observability Setup ---
# Phoenix local OTLP collector typically listens on port 6006
endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces")
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
trace.set_tracer_provider(tracer_provider)
LangChainInstrumentor().instrument()

# --- LLM & Embedding Init ---
def get_llm():
    return ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7)

llm = get_llm()
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
ENABLE_RAG = os.getenv("ENABLE_RAG", "0").lower() in {"1", "true", "yes"}

# --- State & Data Models ---
class TripState(TypedDict):
    # Annotated with operator.add to append messages rather than overwrite
    messages: Annotated[List[BaseMessage], operator.add]
    trip_request: Dict[str, Any]
    user_profile: Dict[str, Any]  # user profile from database or CDP / CRM
    research: Optional[str]
    budget: Optional[str]
    local: Optional[str]
    final: Optional[str]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]

class TripRequest(BaseModel):
    destination: str
    duration: str
    budget: Optional[str] = "moderate"
    interests: Optional[str] = None
    travel_style: Optional[str] = None
    user_input: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    turn_index: Optional[int] = 0

class TripResponse(BaseModel):
    result: str
    tool_calls: List[Dict[str, Any]] = []

# --- Tool Helpers ---
def _search_or_fallback(query: str, instruction: str) -> str:
    """Helper to try Tavily/SerpAPI search, then fallback to LLM knowledge."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post("https://api.tavily.com/search", json={
                    "api_key": tavily_key, "query": query, "max_results": 2, "include_answer": True
                })
                data = resp.json()
                return data.get("answer") or data.get("results")[0].get("content")
        except: pass
    
    # Simple LLM fallback
    res = llm.invoke([SystemMessage(content="Concise guide."), HumanMessage(content=instruction)])
    return res.content

@tool
def get_destination_info(destination: str) -> str:
    """Get weather, safety, and visa info for a destination."""
    return _search_or_fallback(f"{destination} travel info", f"Summarize travel essentials for {destination}.")

@tool
def get_costs(destination: str, budget_level: str) -> str:
    """Get average costs for food, transport, and lodging."""
    return _search_or_fallback(f"{destination} travel costs {budget_level}", f"Estimated costs for {budget_level} travel in {destination}.")

# --- Agent Nodes ---

profile_service = DataServiceFactory.get_service()

def profile_node(state: TripState) -> Dict[str, Any]:
    """Retrieves user data before agents start processing."""
    user_id = state["trip_request"].get("user_id")
    profile = {}
    
    if user_id:
        with using_attributes(service="DataService", action="load_profile"):
            profile = profile_service.get_user_profile(user_id)
            
    return {"user_profile": profile}

def research_node(state: TripState):
    dest = state["trip_request"]["destination"]
    agent = llm.bind_tools([get_destination_info])
    
    with using_attributes(agent_type="research"):
        res = agent.invoke([SystemMessage(content=f"Research {dest}"), HumanMessage(content="Get info.")])
    
    calls = []
    if res.tool_calls:
        # Simple manual tool execution for internal state tracking
        tn = ToolNode([get_destination_info])
        tool_res = tn.invoke({"messages": [res]})
        summary = tool_res["messages"][-1].content
        calls = [{"tool": "get_destination_info", "args": {"destination": dest}}]
    else:
        summary = res.content
        
    return {"research": summary, "tool_calls": calls}

def budget_node(state: TripState):
    dest = state["trip_request"]["destination"]
    lvl = state["trip_request"]["budget"]
    agent = llm.bind_tools([get_costs])
    
    with using_attributes(agent_type="budget"):
        res = agent.invoke([SystemMessage(content=f"Budget for {dest}"), HumanMessage(content="Get costs.")])
    
    calls = []
    if res.tool_calls:
        tn = ToolNode([get_costs])
        tool_res = tn.invoke({"messages": [res]})
        summary = tool_res["messages"][-1].content
        calls = [{"tool": "get_costs", "args": {"destination": dest, "budget_level": lvl}}]
    else:
        summary = res.content

    return {"budget": summary, "tool_calls": calls}

def itinerary_node(state: TripState):
    prompt = f"""
    Create a {state['trip_request']['duration']} itinerary for {state['trip_request']['destination']}.
    Context:
    - Research: {state.get('research')}
    - Budget: {state.get('budget')}
    """
    with using_attributes(agent_type="itinerary"):
        res = llm.invoke([SystemMessage(content="You are a professional travel planner."), HumanMessage(content=prompt)])
    
    return {"final": res.content}

# --- Graph Construction ---
def create_planner_graph():
    builder = StateGraph(TripState)
    builder.add_node("load_profile", profile_node)
    builder.add_node("research", research_node)
    builder.add_node("budget", budget_node)
    builder.add_node("itinerary", itinerary_node)

    # 2. Wire the flow
    builder.add_edge(START, "load_profile")

    # After profile is loaded, run parallel research & budget
    builder.add_edge("load_profile", "research")
    builder.add_edge("load_profile", "budget")
      
    # Join at itinerary
    builder.add_edge("research", "itinerary")
    builder.add_edge("budget", "itinerary")
    builder.add_edge("itinerary", END)
    
    return builder.compile()

# Compile graph once at startup
planner_app = create_planner_graph()

# --- FastAPI Server ---
app = FastAPI(title="Gemini Trip Planner")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/plan-trip", response_model=TripResponse)
async def plan_trip(req: TripRequest):
    initial_state = {
        "messages": [],
        "trip_request": req.model_dump(),
        "tool_calls": []
    }
    
    # Inject tracing attributes for Phoenix (session tracking)
    with using_attributes(
        session_id=req.session_id or "default",
        user_id=req.user_id or "anonymous"
    ):
        try:
            result = planner_app.invoke(initial_state)
            return TripResponse(
                result=result.get("final", "Failed to generate itinerary."),
                tool_calls=result.get("tool_calls", [])
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
