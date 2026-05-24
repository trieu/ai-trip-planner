# 🤖 Agentic Programming with LangGraph
## A Comprehensive Lecture for Students

---

## Slide 1: Course Overview

### What You'll Learn Today

- 🤖 **What is Agentic Programming?** Move beyond single LLM calls to orchestrated AI systems
- 🗺️ **LangGraph Fundamentals**: Build directed acyclic graphs (DAGs) for agent workflows
- 🔄 **State Management**: How to pass data between agents without conflicts
- ⚡ **Parallel Execution**: Speed up AI systems by running agents simultaneously
- 🛠️ **Tool Integration**: Teach agents to call APIs, databases, and external tools
- 🏗️ **Real-World Example**: The AI Trip Planner system that demonstrates production patterns

### Prerequisites

- Python basics (functions, classes, async/await)
- Understanding of LLM APIs (OpenAI, Gemini, etc.)
- No LangGraph experience needed—we'll build it together!

---

## Slide 2: What is Agentic Programming?

### Traditional LLM Approach (Single Call)

```
User Input → LLM → Output
```

❌ **Limitations:**
- One-shot responses
- No tool use or external data
- Limited reasoning chains
- Can't decompose complex tasks

### Agentic Approach (Orchestrated System)

```
User Input → Agent 1 ← Tools → Agent 2 ← Data
              ↓                    ↓
         Orchestrator ← State Management
              ↓
           Output
```

✅ **Benefits:**
- Multi-step reasoning
- Specialized agents for different tasks
- Dynamic tool calling
- Parallel execution for speed

---

## Slide 3: The AI Trip Planner: Your Real-World Blueprint

### The Problem

Plan a personalized trip that balances:
- 🏖️ Authentic local experiences (research)
- 💰 Budget constraints (budget planning)
- 🌤️ Weather conditions (weather data)
- 👤 User preferences (personalization)

### Traditional Approach: Single LLM

```python
# ❌ Old way - single call, low quality
response = llm.invoke(f"Plan a {budget} trip to {destination}")
```

### Agentic Approach: Parallel Agents

```
Research Agent ──┐
Budget Agent ────→ Aggregator → Journey Plan
Weather Agent ───┘
```

🚀 **Result:** Better decisions, cited sources, multi-source data synthesis

---

## Slide 4: LangGraph Core Concepts

### What is LangGraph?

A library for building **stateful, multi-actor applications** with large language models.

### Three Key Components

1. **StateGraph**: Defines your workflow structure
2. **Nodes**: Functions that process state (agents, tools, logic)
3. **Edges**: Connections between nodes (control flow)

### Real-World Analogy

Think of a workflow like a restaurant kitchen:

```
OrderNode (take order) 
    ↓
CookNode (prepare dish) ← IngredientNode (fetch ingredients)
    ↓
QCNode (quality check)
    ↓
ServeNode (serve customer)
```

Each node is autonomous; the graph orchestrates flow.

---

## Slide 5: The Trip Planner Architecture

### The LangGraph Workflow

```
START
  ↓
load_profile (hydrate user preferences)
  ↓
┌─────────────────────────────────┐
│ Parallel Execution (Fan-Out)    │
├─────────────────────────────────┤
│ research_node                   │
│ weather_node                    │
│ budget_node                     │
└─────────────────────────────────┘
  ↓
aggregate (combine results)
  ↓
journey_plan (synthesize final output)
  ↓
END
```

### Why Parallel?

- **Research** takes 2s to call web APIs
- **Weather** takes 1s to fetch
- **Budget** takes 1s to calculate
- **Sequential = 4s**, **Parallel = 2s** ⚡

---

## Slide 6: State Definition in LangGraph

### What is State?

Shared data structure passed between all nodes. Think: "the trip planning context."

### Trip Planner State (from `state_models.py`)

```python
from typing import Annotated, List, Dict, Any
from typing_extensions import TypedDict
import operator
from langchain_core.messages import BaseMessage

class TripState(TypedDict):
    """Defines state passed between LangGraph nodes."""
    
    # Messages accumulate (operator.add means concatenate lists)
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Trip request from the user
    trip_request: Dict[str, Any]  # {destination, budget, interests, user_id}
    
    # Hydrated user profile (from CDP/database)
    user_profile: Dict[str, Any]   # {preferences, past_trips, dietary_restrictions}
    
    # Location geocoding
    location_coords: Optional[Dict[str, float]]  # {lat, long}
    
    # Agent outputs
    research: Optional[str]        # Destination insights
    weather: Optional[str]         # Current weather
    budget: Optional[str]          # Cost breakdown
    final: Optional[str]           # Final itinerary
    
    # Tool calls (for observability)
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]
```

### The `Annotated[List, operator.add]` Pattern

```python
# Instead of overwriting:
state["messages"] = [msg1]  # ❌ Loses previous messages
state["messages"] += [msg2] # ❌ Manual concatenation

# Use operator.add annotation:
state["messages"] = [msg1]  # First call
state["messages"] = [msg2]  # Automatically concatenates! → [msg1, msg2]
```

---

## Slide 7: Building the Graph

### Step 1: Create the StateGraph

```python
from langgraph.graph import StateGraph, START, END
from core_llm.state_models import TripState

class SmartTripPlanner:
    def __init__(self):
        self.llm = MetaLLM.get_llm(temperature=0.7)
        self.profile_service = DataServiceFactory.get_service()
        self.app = self._build_graph()
    
    def _build_graph(self):
        # Create builder for TripState
        builder = StateGraph(TripState)
        
        # Add nodes (we'll define these next)
        builder.add_node("load_profile", self._profile_node)
        builder.add_node("research", self._research_node)
        builder.add_node("weather", self._weather_node)
        builder.add_node("budget", self._budget_node)
        builder.add_node("aggregate", self._aggregate_node)
        builder.add_node("journey_plan", self._journey_plan_node)
        
        return builder.compile()  # ← Magic happens here!
```

### What Does `compile()` Do?

Converts the graph definition into an executable state machine that:
- Manages state transitions
- Parallelizes where possible
- Handles errors
- Provides trace visibility

---

## Slide 8: Defining Edges (Control Flow)

### Types of Edges

```python
# 1. START → First Node
builder.add_edge(START, "load_profile")

# 2. Sequential: A → B
builder.add_edge("load_profile", "research")

# 3. Implicit Parallelism (multiple edges from same node)
builder.add_edge("load_profile", "research")
builder.add_edge("load_profile", "weather")
builder.add_edge("load_profile", "budget")
# ← These all run in parallel!

# 4. Converging Paths
builder.add_edge("research", "aggregate")
builder.add_edge("weather", "aggregate")
builder.add_edge("budget", "aggregate")
# ← aggregate waits for all three to complete

# 5. End Node
builder.add_edge("journey_plan", END)
```

### Visualization

```
START
  ↓
load_profile ──→ research ──┐
  ├──→ weather ─────┼─→ aggregate → journey_plan → END
  └──→ budget ──────┘
```

---

## Slide 9: Writing Node Functions

### Basic Node Structure

A node function:
1. Takes the current state
2. Returns a dict update (not replacement!)
3. Can be sync or async

```python
def my_node(state: TripState) -> Dict[str, Any]:
    # Extract what you need
    destination = state["trip_request"]["destination"]
    profile = state["user_profile"]
    
    # Do work (LLM calls, tool calls, etc.)
    result = some_computation(destination, profile)
    
    # Return only the fields you update
    return {
        "research": result,
        "tool_calls": [{"tool": "get_destination_info", "args": {...}}]
    }
```

### ⚠️ Critical: Return Dict, Not Full State

```python
# ❌ WRONG - returns entire state
return state  # This overwrites everything!

# ✅ CORRECT - returns only updated fields
return {"research": result}

# ✅ CORRECT - updates multiple fields
return {
    "research": result,
    "messages": [msg],
    "tool_calls": [...]
}
```

---

## Slide 10: The Profile Node (Personalization)

### Why Load Profile First?

All downstream agents need user context:
- Dietary restrictions (vegan? allergies?)
- Travel style (luxury vs budget? solo vs family?)
- Past trips (avoid repeats?)
- Payment method (cryptocurrency? credit card?)

### The Implementation

```python
def _profile_node(self, state: TripState) -> Dict[str, Any]:
    # Extract user_id from request
    user_id = state["trip_request"].get("user_id")
    interests = state["trip_request"].get("interests")
    
    profile = {}
    
    # Fetch from data service (could be CDP, PostgreSQL, mock)
    if user_id:
        profile = self.profile_service.get_user_profile(user_id)
    
    # Set defaults
    profile.setdefault(
        "current_interests",
        interests.split(",") if interests else []
    )
    
    # Return only profile updates
    return {"user_profile": profile}
```

### Data Service Factory (Strategy Pattern)

```python
# backend/services/data_service.py
class DataServiceFactory:
    @staticmethod
    def get_service():
        if os.getenv("USE_CDP") == "true":
            return LEOCDPService()  # Real CDP API
        elif os.getenv("USE_POSTGRES") == "true":
            return PostgresProfileService()  # PostgreSQL
        else:
            return MockTestService()  # For local testing
```

✅ **Key Insight:** Change backends without changing node logic!

---

## Slide 11: The Research Node (Tool Integration)

### Node Responsibility

Gather detailed destination insights:
- Top attractions
- Local food
- Cultural events
- Hidden gems

### Implementation

```python
async def _research_node(self, state: TripState) -> Dict[str, Any]:
    dest = state["trip_request"]["destination"]
    
    # Extract user profile context
    interests = state["user_profile"].get("current_interests", [])
    
    try:
        # DIRECT TOOL CALL (no ToolNode wrapper)
        research_summary = await get_destination_info.ainvoke({
            "location": dest,
            "interests": interests
        })
        
        return {
            "research": research_summary,
            "tool_calls": [{
                "tool": "get_destination_info",
                "args": {"location": dest, "interests": interests}
            }]
        }
    
    except Exception as e:
        logger.error(f"[research_node] failed: {e}")
        return {
            "research": f"Unable to fetch research for {dest}",
            "tool_calls": []
        }
```

### Tool Definition

```python
# backend/tools/travel_tools.py
from langchain.tools import tool

@tool
async def get_destination_info(location: str, interests: list) -> str:
    """
    Fetch destination insights.
    
    Args:
        location: City or destination name
        interests: List of user interests (food, culture, nature, etc.)
    
    Returns:
        Formatted destination insights
    """
    # Could call web search, database, RAG, or LLM
    insights = await web_search_api(f"Best {interests} in {location}")
    return format_insights(insights)
```

---

## Slide 12: The Weather Node (Real-Time Data)

### Simple Tool Integration

```python
def _weather_node(self, state: TripState) -> Dict[str, Any]:
    dest = state.get("trip_request", {}).get("destination")
    
    if not dest or not isinstance(dest, str):
        return {
            "weather": "Invalid destination",
            "tool_calls": []
        }
    
    try:
        # Call tool (synchronous here)
        weather = get_current_weather.invoke({"location": dest.strip()})
    
    except Exception as e:
        logger.error(f"[weather_node] failed: {e}")
        weather = "Weather unavailable (fallback to planning without it)"
    
    return {
        "weather": weather,
        "tool_calls": [{
            "tool": "get_current_weather",
            "args": {"location": dest}
        }]
    }
```

### Tool Definition

```python
@tool
def get_current_weather(location: str) -> str:
    """Get current weather for a location."""
    # Call weather API (OpenWeatherMap, WeatherAPI, etc.)
    weather_data = fetch_weather_api(location)
    return f"Weather in {location}: {weather_data['temp']}°C, {weather_data['condition']}"
```

### Key Pattern: Graceful Fallback

If tool fails → return sensible default
→ System continues (doesn't crash)
→ Downstream agents adapt

---

## Slide 13: The Budget Node (Business Logic)

### Node Responsibility

Break down costs across trip duration:
- Accommodation
- Food
- Activities
- Transportation
- Contingency

### Implementation

```python
def _budget_node(self, state: TripState) -> Dict[str, Any]:
    trip_req = state["trip_request"]
    destination = trip_req.get("destination")
    budget = trip_req.get("budget")
    duration = trip_req.get("duration")
    
    try:
        # Get real costs
        costs = get_costs.invoke({
            "location": destination,
            "duration": duration,
            "category": "budget"  # or "mid-range", "luxury"
        })
        
        # Break down total budget
        breakdown = calculate_budget_breakdown(
            total_budget=budget,
            costs=costs,
            duration=duration
        )
        
        return {
            "budget": breakdown,
            "tool_calls": [{
                "tool": "get_costs",
                "args": {"location": destination, "duration": duration}
            }]
        }
    
    except Exception as e:
        logger.error(f"[budget_node] failed: {e}")
        return {
            "budget": f"Budget analysis unavailable",
            "tool_calls": []
        }
```

---

## Slide 14: The Aggregate Node (Data Fusion)

### Role of Aggregation

Combine outputs from parallel nodes into coherent state for final synthesis:

```python
def _aggregate_node(self, state: TripState) -> Dict[str, Any]:
    # All parallel nodes have completed
    # Now we have research, weather, budget, user_profile
    
    # Create aggregated context for final LLM call
    aggregated_context = {
        "research": state.get("research", ""),
        "weather": state.get("weather", ""),
        "budget": state.get("budget", ""),
        "user_interests": state["user_profile"].get("current_interests", []),
        "trip_request": state["trip_request"],
    }
    
    # Log for observability
    logger.info(f"[aggregate_node] Combined data from {len(state['tool_calls'])} tool calls")
    
    # Store for next node's consumption
    return {"aggregated_context": aggregated_context}
```

### What Happens Here?

1. ✅ Wait for all parallel nodes to finish
2. ✅ Validate outputs (handle partial failures)
3. ✅ Deduplicate redundant data
4. ✅ Format for downstream consumption
5. ✅ Pass to journey planner

---

## Slide 15: The Journey Plan Node (LLM Synthesis)

### Final Reasoning

Given all research, weather, budget, and profile data:
→ Synthesize a cohesive, personalized itinerary

### Implementation

```python
async def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
    context = state.get("aggregated_context", {})
    
    # Build a rich prompt
    prompt = build_trip_planner_prompt(
        destination=context["trip_request"]["destination"],
        duration=context["trip_request"]["duration"],
        budget=context["budget"],
        weather=context["weather"],
        research=context["research"],
        user_interests=context["user_interests"]
    )
    
    # Call LLM (with tools available)
    response = await self.llm.ainvoke([
        SystemMessage(content=TRIP_PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ])
    
    # Extract final plan
    final_itinerary = parse_response(response)
    
    return {
        "final": final_itinerary,
        "messages": [response]
    }
```

### Prompt Template (Simplified)

```python
def build_trip_planner_prompt(destination, duration, budget, weather, research, interests):
    return f"""
    You are an expert travel planner with access to real-time data.
    
    User Profile:
    - Interests: {interests}
    
    Trip Details:
    - Destination: {destination}
    - Duration: {duration}
    - Budget: {budget}
    
    Research Insights:
    {research}
    
    Weather Forecast:
    {weather}
    
    Now create a personalized, day-by-day itinerary that:
    1. Respects the budget constraint
    2. Aligns with user interests
    3. Adapts to weather conditions
    4. Includes hidden gems (not just tourist traps)
    
    Format as markdown with:
    - Day-by-day breakdown
    - Estimated costs
    - Why each activity matches the user
    """
```

---

## Slide 16: Running the Graph

### Invoking the Workflow

```python
# Create planner
planner = SmartTripPlanner()

# Prepare input
trip_request = {
    "destination": "Tokyo, Japan",
    "duration": "7 days",
    "budget": "$2000",
    "interests": "food, culture, nightlife",
    "user_id": "user_123"
}

# Initialize state
initial_state = {
    "trip_request": trip_request,
    "messages": [],
    "tool_calls": []
}

# Run!
result = planner.app.invoke(initial_state)

# Access outputs
print(result["final"])          # The final itinerary
print(result["research"])       # Research findings
print(result["weather"])        # Weather data
print(result["tool_calls"])     # For debugging/tracing
```

### Async Execution

```python
import asyncio

# For async nodes
result = await planner.app.ainvoke(initial_state)

# Or use asyncio directly
asyncio.run(planner.app.ainvoke(initial_state))
```

---

## Slide 17: Observability & Tracing

### Why Tracing Matters

Debug agentic systems by seeing:
- ✅ Which node ran when
- ✅ What inputs/outputs each node received
- ✅ Which tools were called
- ✅ Where latency bottlenecks exist
- ✅ Which LLM calls happened

### Integration with Arize Phoenix

```python
# backend/core_llm/observer_utils.py
from phoenix.trace import get_tracer

def setup_observability():
    tracer = get_tracer()
    # Automatically traces LLM calls, tool calls, spans
    return tracer

def safe_attributes(attributes: dict):
    """Context manager for adding custom span attributes."""
    @contextmanager
    def _context():
        span = get_span()
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield
    return _context()
```

### Usage in Nodes

```python
def _profile_node(self, state: TripState) -> Dict[str, Any]:
    user_id = state["trip_request"].get("user_id")
    
    with safe_attributes({"agent.type": "profile_loader", "user.id": user_id}):
        profile = self.profile_service.get_user_profile(user_id)
    
    return {"user_profile": profile}
```

### Phoenix Dashboard Shows

```
TripPlannerWorkflow
├── load_profile (50ms)
│   └── get_user_profile() → PostgreSQL (45ms)
├── [Parallel]
│   ├── research (2000ms)
│   │   └── get_destination_info() → Web Search (1950ms)
│   ├── weather (100ms)
│   │   └── get_current_weather() → API (80ms)
│   └── budget (150ms)
│       └── get_costs() → Database (140ms)
├── aggregate (10ms)
└── journey_plan (3000ms)
    └── LLM.ainvoke() → Claude Opus (2950ms)

Total: 5110ms (saved 1600ms+ vs sequential!)
```

---

## Slide 18: Error Handling in Agentic Systems

### Patterns for Resilience

#### 1. Try-Catch with Fallbacks

```python
async def _research_node(self, state: TripState) -> Dict[str, Any]:
    dest = state["trip_request"]["destination"]
    
    try:
        # Try primary tool
        research = await get_destination_info.ainvoke({"location": dest})
    
    except TimeoutError:
        logger.warning(f"Web search timeout for {dest}, using LLM fallback")
        # Fallback: use LLM reasoning instead
        research = await self.llm.ainvoke([
            HumanMessage(f"Generate travel insights for {dest}")
        ])
    
    except Exception as e:
        logger.error(f"[research_node] unknown error: {e}")
        research = f"Research unavailable (system will continue with other data)"
    
    return {"research": research}
```

#### 2. Conditional Edges (Branching)

```python
def _should_use_rag(state: TripState) -> str:
    """Route to RAG or LLM based on data availability."""
    if state.get("research") and len(state["research"]) > 100:
        return "rag"  # Use vector DB search
    else:
        return "llm"  # Fall back to LLM reasoning

builder.add_conditional_edges(
    "research",
    _should_use_rag,
    {"rag": "rag_node", "llm": "llm_node"}
)
```

---

## Slide 19: Conditional Branching (Advanced)

### When Decisions Matter

Different users might need different agents:

```python
def _route_to_agent(state: TripState) -> str:
    """Route based on trip complexity."""
    duration = int(state["trip_request"].get("duration", "0").split()[0])
    budget = float(state["trip_request"].get("budget", "$0").replace("$", ""))
    
    # Complex trip (long, high budget) → extra planning
    if duration > 14 and budget > 5000:
        return "detailed_planner"
    
    # Simple trip → quick planner
    else:
        return "quick_planner"

builder.add_conditional_edges(
    "load_profile",
    _route_to_agent,
    {
        "detailed_planner": "detailed_planning",
        "quick_planner": "quick_planning"
    }
)
```

### Graph with Branches

```
START
  ↓
load_profile
  ↓
[conditional: duration/budget?]
  ├→ detailed_planning → research → weather → budget → aggregate → END
  └→ quick_planning → simple_research → simple_plan → END
```

---

## Slide 20: State Mutations & Immutability

### ⚠️ Common Mistake: State Mutation

```python
# ❌ WRONG - modifies state in place
def bad_node(state: TripState) -> Dict[str, Any]:
    state["research"].append("new data")  # Mutates!
    return state  # Causes synchronization bugs!

# ✅ CORRECT - returns new data
def good_node(state: TripState) -> Dict[str, Any]:
    existing = state.get("research", "")
    new_research = existing + "\nnew data"
    return {"research": new_research}
```

### With Annotated Lists (operator.add)

```python
# In state definition
tool_calls: Annotated[List[Dict[str, Any]], operator.add]

# In node, DON'T DO THIS:
state["tool_calls"].append(new_call)  # ❌ Mutation

# DO THIS:
return {"tool_calls": [new_call]}  # ✅ operator.add handles concatenation
```

---

## Slide 21: Testing Agentic Systems

### Unit Testing Nodes

```python
# backend/tests/test_trip_planner.py
import pytest
from unittest.mock import Mock, patch
from core_llm.smart_trip_planner import SmartTripPlanner
from core_llm.state_models import TripState

@pytest.fixture
def planner():
    return SmartTripPlanner()

def test_profile_node(planner):
    """Test profile loading."""
    state = TripState(
        trip_request={"user_id": "test_user", "interests": "food, culture"},
        messages=[],
        tool_calls=[]
    )
    
    result = planner._profile_node(state)
    
    assert "user_profile" in result
    assert "current_interests" in result["user_profile"]
    assert "food" in result["user_profile"]["current_interests"]

@pytest.mark.asyncio
async def test_research_node_with_mock_tool(planner):
    """Test research with mocked tool."""
    with patch("tools.travel_tools.get_destination_info") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value="Tokyo is...")
        
        state = TripState(
            trip_request={"destination": "Tokyo, Japan"},
            user_profile={},
            messages=[],
            tool_calls=[]
        )
        
        result = await planner._research_node(state)
        
        assert result["research"] == "Tokyo is..."
        assert len(result["tool_calls"]) == 1
```

---

## Slide 22: Integration Testing

### End-to-End Workflow Test

```python
@pytest.mark.asyncio
async def test_full_trip_planner_workflow():
    """Test the complete graph execution."""
    planner = SmartTripPlanner()
    
    initial_state = {
        "trip_request": {
            "destination": "Tokyo, Japan",
            "duration": "3 days",
            "budget": "$1000",
            "interests": "food",
            "user_id": "test_user"
        },
        "messages": [],
        "tool_calls": [],
        "user_profile": {},
        "research": None,
        "weather": None,
        "budget": None,
        "final": None,
        "location_coords": None
    }
    
    result = await planner.app.ainvoke(initial_state)
    
    # Assertions
    assert result["final"] is not None
    assert len(result["final"]) > 0
    assert "Tokyo" in result["final"]
    assert len(result["tool_calls"]) > 0  # Tools were called
```

---

## Slide 23: Synthetic Evaluation

### Why Evaluation Matters

LLM outputs are subjective. Use synthetic evaluations to:
- Benchmark quality
- Detect regressions
- A/B test prompt changes

```python
# backend/test_scripts/synthetic_data_gen.py
import asyncio
import json
from core_llm.smart_trip_planner import SmartTripPlanner

# Test cases
test_destinations = [
    {"destination": "Tokyo, Japan", "duration": "7 days", "budget": "$2000"},
    {"destination": "Paris, France", "duration": "5 days", "budget": "$1500"},
    {"destination": "Bali, Indonesia", "duration": "10 days", "budget": "$800"},
]

async def evaluate_planner():
    planner = SmartTripPlanner()
    results = []
    
    for test_case in test_destinations:
        initial_state = {
            "trip_request": test_case,
            "messages": [],
            "tool_calls": [],
            "user_profile": {}
        }
        
        result = await planner.app.ainvoke(initial_state)
        
        # Store result with timing
        results.append({
            "test": test_case,
            "final": result["final"],
            "tool_calls_count": len(result["tool_calls"]),
            "status": "success"
        })
    
    with open("evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)

asyncio.run(evaluate_planner())
```

---

## Slide 24: Streaming Responses

### Why Stream?

For long-running agents, stream responses to show progress:

```
User: "Plan my trip"
                    ↓ (1 sec)
System: "Loading your profile..."
                    ↓ (2 sec)
System: "Researching Tokyo..."
                    ↓ (2 sec)
System: "Checking weather..."
                    ↓ (1 sec)
System: "Calculating budget..."
                    ↓ (3 sec)
System: "Finalizing itinerary..."

[Complete itinerary appears]
```

### Implementation with FastAPI

```python
# backend/api/routes/trip_routes.py
from fastapi.responses import StreamingResponse
import asyncio
import json

@router.post("/trips/plan/stream")
async def plan_trip_stream(request: TripRequest):
    """Stream trip planning updates."""
    
    async def stream_generator():
        planner = SmartTripPlanner()
        initial_state = {"trip_request": request.dict(), "messages": [], "tool_calls": []}
        
        # Yield progress updates
        yield f"data: {json.dumps({'status': 'loading_profile'})}\n\n"
        
        # Run workflow
        async for state in planner.app.astream(initial_state):
            # Emit state updates
            yield f"data: {json.dumps({'state': state})}\n\n"
            await asyncio.sleep(0.1)  # Browser processing time
    
    return StreamingResponse(stream_generator(), media_type="text/event-stream")
```

---

## Slide 25: Deployment Patterns

### Local Development

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with hot reload
uvicorn main:app --host 0.0.0.0 --port 8888 --reload
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
EXPOSE 8888

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888"]
```

```bash
docker build -t trip-planner:latest .
docker run -p 8888:8888 --env-file .env trip-planner:latest
```

### Production Deployment (Render)

See `render.yaml` in the repo:

```yaml
services:
  - type: web
    name: trip-planner-api
    runtime: python311
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: OPENAI_API_KEY
        scope: build,runtime
```

---

## Slide 26: Working with Custom Tools

### Tool Anatomy

```python
from langchain.tools import tool
from pydantic import BaseModel, Field

class WeatherInput(BaseModel):
    location: str = Field(description="City name")
    units: str = Field(default="celsius", description="celsius or fahrenheit")

@tool
def get_weather(location: str, units: str = "celsius") -> str:
    """
    Get current weather for a location.
    
    Args:
        location: City name (e.g., "Tokyo")
        units: Temperature units (celsius or fahrenheit)
    
    Returns:
        Formatted weather string
    """
    api_response = call_weather_api(location, units)
    return f"Weather in {location}: {api_response['temp']}°{units[0].upper()}, {api_response['description']}"
```

### Registering Tools with LLM

```python
from langchain_core.tools import ToolCollection

tools = [
    get_weather,
    get_destination_info,
    get_costs,
]

# With Claude
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-3-opus-20240229")
llm_with_tools = llm.bind_tools(tools)
```

---

## Slide 27: Tool Calling in Nodes

### Method 1: invoke() - Synchronous

```python
def _weather_node(self, state: TripState) -> Dict[str, Any]:
    result = get_weather.invoke({"location": "Tokyo"})
    return {"weather": result}
```

### Method 2: ainvoke() - Asynchronous

```python
async def _research_node(self, state: TripState) -> Dict[str, Any]:
    result = await get_destination_info.ainvoke({"location": "Tokyo"})
    return {"research": result}
```

### Method 3: LLM Tool Calling (Agent Loop)

```python
async def _research_node_llm_driven(self, state: TripState) -> Dict[str, Any]:
    """Let LLM decide which tools to call."""
    messages = [
        SystemMessage("You are a travel researcher. Use tools to research destinations."),
        HumanMessage(f"Research Tokyo for a 7-day trip")
    ]
    
    # Bind tools to LLM
    llm_with_tools = self.llm.bind_tools([get_destination_info, get_weather])
    
    # LLM decides which tools to call
    response = await llm_with_tools.ainvoke(messages)
    
    # Check if tool calls were requested
    if response.tool_calls:
        # Execute tools
        results = []
        for tool_call in response.tool_calls:
            tool = get_tool_by_name(tool_call["name"])
            result = tool.invoke(tool_call["args"])
            results.append(result)
        
        return {"research": " ".join(results)}
    else:
        return {"research": response.content}
```

---

## Slide 28: Prompt Engineering for Agentic Systems

### Don't Just Use Defaults

Tailor prompts to agent roles:

```python
# backend/core_llm/prompt_builder.py

RESEARCH_AGENT_PROMPT = """
You are an expert travel researcher specializing in {destination}.

Your job is to provide the BEST LOCAL EXPERIENCES that align with the user's interests.

**User Profile:**
- Interests: {interests}
- Travel Style: {travel_style}
- Budget Level: {budget_level}

**Requirements:**
1. Include both popular attractions AND hidden gems
2. Provide sources or reasoning for each recommendation
3. Consider seasonal factors: {weather_info}
4. Respect dietary/mobility restrictions if any
5. Format as a bulleted list with cost estimates

**Avoid:**
- Tourist traps with bad reviews
- Activities outside the budget range
- Recommendations unrelated to user interests

Now, research {destination}:
"""

BUDGET_AGENT_PROMPT = """
You are a financial planner for international trips.

Create a detailed budget breakdown for a {duration} trip to {destination}.

**Constraints:**
- Total Budget: {budget}
- Currency: {currency}
- Travel Style: {travel_style}

**Include:**
1. Accommodation (with options: budget, mid-range, luxury)
2. Food (daily breakdown)
3. Activities (aligned with research recommendations)
4. Transportation (local + to/from airport)
5. Contingency (10% buffer)

Format as a table with USD, local currency, and percentage breakdowns.
"""
```

---

## Slide 29: Meta-LLM (Provider Agnosticism)

### Why Swap LLM Providers?

- Different costs (GPT-4 vs Claude vs Gemini)
- Different latency profiles
- Regional availability
- Different capabilities

### The MetaLLM Factory

```python
# backend/core_llm/meta_llm.py
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

class MetaLLM:
    @staticmethod
    def get_llm(temperature: float = 0.7):
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        
        if provider == "openai":
            return ChatOpenAI(
                model="gpt-4-turbo",
                temperature=temperature,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        
        elif provider == "anthropic":
            return ChatAnthropic(
                model="claude-3-opus-20240229",
                temperature=temperature,
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
        
        elif provider == "google":
            return ChatGoogleGenerativeAI(
                model="gemini-1.5-pro",
                temperature=temperature,
                api_key=os.getenv("GOOGLE_API_KEY")
            )
        
        else:
            raise ValueError(f"Unknown provider: {provider}")
```

### Usage

```bash
# Swap provider with env var, no code change
export LLM_PROVIDER=anthropic
python -m uvicorn main:app --reload

# Or
export LLM_PROVIDER=google
python -m uvicorn main:app --reload
```

---

## Slide 30: RAG (Retrieval-Augmented Generation)

### The Problem

LLMs hallucinate facts. Grounding them with real data helps:

```
❌ Without RAG:
  LLM: "Roppongi is famous for its zen temples"
  Reality: Roppongi is an expensive nightlife district

✅ With RAG:
  LLM retrieves: "Roppongi is famous for its nightlife and Art Triangle museums"
  LLM: "Visit Roppongi's Art Triangle museums and entertainment district"
```

### Trip Planner RAG Architecture

```python
# backend/services/travel_rag_service.py
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

class TravelRAGService:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.vectordb = Chroma(embedding_function=self.embeddings)
        
        # Load local guide data
        self.load_guides("data/local_guides.json")
    
    def load_guides(self, filepath: str):
        """Load travel guides into vector DB."""
        with open(filepath) as f:
            guides = json.load(f)
        
        # Split guides into chunks and embed
        for guide in guides:
            self.vectordb.add_documents([
                Document(
                    page_content=guide["description"],
                    metadata={"city": guide["city"], "category": guide["category"]}
                )
            ])
    
    async def retrieve_recommendations(self, destination: str, interests: list):
        """Retrieve relevant guides using vector search."""
        query = f"Best {', '.join(interests)} experiences in {destination}"
        
        results = self.vectordb.similarity_search_with_score(
            query,
            k=5,  # Top 5 results
            filter={"city": destination}
        )
        
        # Format results
        recommendations = []
        for doc, score in results:
            recommendations.append({
                "text": doc.page_content,
                "relevance": score,
                "source": "local_guides"
            })
        
        return recommendations
```

### Usage in Research Node

```python
async def _research_node(self, state: TripState) -> Dict[str, Any]:
    dest = state["trip_request"]["destination"]
    interests = state["user_profile"]["current_interests"]
    
    # Try RAG first
    rag_results = await rag_service.retrieve_recommendations(dest, interests)
    
    if rag_results and rag_results[0]["relevance"] > 0.7:
        # High-quality RAG hit
        research = format_rag_results(rag_results)
    else:
        # Fallback: LLM generates insights
        research = await llm.ainvoke([
            HumanMessage(f"Generate travel insights for {dest}")
        ])
    
    return {"research": research}
```

---

## Slide 31: Scaling & Performance Optimization

### Latency Bottlenecks

```
TripPlanner Execution Timeline:
┌─────────────────────────────────────────────────┐
│ Sequential (Old):                               │
│ ├── research: 2000ms                            │
│ ├── weather: 100ms                              │
│ ├── budget: 150ms                               │
│ ├── aggregate: 10ms                             │
│ └── journey_plan: 3000ms                        │
│ TOTAL: 5260ms ❌                                │
└─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Parallel (LangGraph):                         │
│ ├── research: 2000ms   ┐                      │
│ ├── weather: 100ms     ├─ All simultaneous   │
│ ├── budget: 150ms      ┘                      │
│ ├── aggregate: 10ms                          │
│ └── journey_plan: 3000ms                     │
│ TOTAL: 5160ms (saved 100ms) ⚠️              │
│ Real gain would be if LLM calls were async  │
└──────────────────────────────────────────────┘
```

### Further Optimization

```python
# 1. Cache LLM responses
from langchain.cache import InMemoryCache, RedisCache

llm.cache = RedisCache()  # Avoid re-running same query

# 2. Parallel LLM calls
async def _optimized_research_node(self, state):
    dest = state["trip_request"]["destination"]
    interests = state["user_profile"]["current_interests"]
    
    # Fetch multiple sources in parallel
    results = await asyncio.gather(
        get_destination_info.ainvoke({"location": dest}),
        web_search.ainvoke({"query": f"hidden gems {dest}"}),
        rag_service.retrieve.ainvoke({"destination": dest, "interests": interests})
    )
    
    return {"research": merge_results(results)}

# 3. Use smaller models for fast paths
lightweight_llm = ChatOpenAI(model="gpt-3.5-turbo")  # Fast & cheap
heavyweight_llm = ChatOpenAI(model="gpt-4-turbo")    # Slow & expensive
```

---

## Slide 32: Common Pitfalls & How to Avoid Them

### Pitfall 1: State Mutations

```python
# ❌ WRONG
def node(state):
    state["data"].append("x")  # Mutates shared state
    return state

# ✅ RIGHT
def node(state):
    new_data = state.get("data", []) + ["x"]
    return {"data": new_data}
```

### Pitfall 2: Forgetting to Return Dict Updates

```python
# ❌ WRONG - returns old values
def node(state):
    result = expensive_computation()
    # OOPS! Forgot to return

# ✅ RIGHT
def node(state):
    result = expensive_computation()
    return {"output": result}
```

### Pitfall 3: Unhandled Exceptions

```python
# ❌ WRONG - crashes entire workflow
def node(state):
    result = external_api()  # Could fail!
    return {"data": result}

# ✅ RIGHT - graceful fallback
def node(state):
    try:
        result = external_api()
    except Exception as e:
        logger.error(f"API failed: {e}")
        result = "Fallback: using cached data"
    
    return {"data": result}
```

### Pitfall 4: Blocking Calls in Async Nodes

```python
# ❌ WRONG - blocks event loop
async def node(state):
    result = requests.get(url)  # Blocking!
    return {"data": result}

# ✅ RIGHT - async HTTP
async def node(state):
    async with aiohttp.ClientSession() as session:
        result = await session.get(url)  # Non-blocking
    return {"data": result}
```

---

## Slide 33: Debugging Techniques

### 1. Print-Based Debugging

```python
def debug_node(state):
    print(f"Input state: {json.dumps(state, indent=2, default=str)}")
    
    result = some_computation(state)
    
    print(f"Output: {result}")
    return result
```

### 2. Logging with Levels

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def node(state):
    logger.debug(f"Processing state: {state['trip_request']}")
    logger.info("Starting research node")
    
    try:
        result = risky_operation()
        logger.info(f"Success: {result}")
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
    
    return {"result": result}
```

### 3. Interactive Debugging (pdb)

```python
def node(state):
    import pdb
    pdb.set_trace()  # Pauses execution
    
    # Now you can inspect:
    # (Pdb) print(state["trip_request"])
    # (Pdb) n (next)
```

### 4. Observability Dashboard

```python
# See Slide 17 - use Arize Phoenix traces
# Query:
# - Which node is slow?
# - Which tool failed?
# - What LLM prompts generated bad outputs?
```

---

## Slide 34: Building Adaptive Agents

### Context-Aware Routing

```python
def _route_research_strategy(state: TripState) -> str:
    """Choose research strategy based on destination."""
    dest = state["trip_request"]["destination"].lower()
    
    # Well-known destinations → web search likely to be better
    if dest in ["tokyo", "paris", "new york", "london"]:
        return "web_search"
    
    # Niche destinations → use RAG + LLM
    else:
        return "rag_with_llm"

builder.add_conditional_edges(
    "load_profile",
    _route_research_strategy,
    {
        "web_search": "web_research_node",
        "rag_with_llm": "rag_research_node"
    }
)
```

### Learning from Feedback

```python
# Store user feedback after each trip
def store_feedback(user_id, trip_id, feedback_score: 1-5):
    db.execute("""
        INSERT INTO trip_feedback (user_id, trip_id, score, created_at)
        VALUES (:user_id, :trip_id, :score, NOW())
    """, {"user_id": user_id, "trip_id": trip_id, "score": feedback_score})

# Use feedback to adapt
def get_user_preferences(user_id):
    # Get high-rated trips
    high_rated = db.query("""
        SELECT trip_details FROM trips
        WHERE user_id = :user_id AND feedback_score >= 4
    """, {"user_id": user_id})
    
    # Extract patterns (prefer luxury? cultural? nature?)
    return analyze_patterns(high_rated)
```

---

## Slide 35: Agent Chains vs Agent Trees

### Agent Chain (Sequential)

```
Agent1 → Agent2 → Agent3 → Output

Use when:
- Each agent refines previous output
- Sequential reasoning needed (step A → step B → step C)
- Example: Draft → Review → Polish
```

```python
builder.add_edge("draft_agent", "review_agent")
builder.add_edge("review_agent", "polish_agent")
builder.add_edge("polish_agent", END)
```

### Agent Tree (Parallel Branches)

```
Agent1 ─┐
Agent2  ├→ Synthesizer → Output
Agent3 ─┘

Use when:
- Agents solve independent aspects
- Results must be combined
- Example: Research + Budget + Weather (like our trip planner!)
```

```python
builder.add_edge("load_profile", "research")
builder.add_edge("load_profile", "budget")
builder.add_edge("load_profile", "weather")

builder.add_edge("research", "synthesizer")
builder.add_edge("budget", "synthesizer")
builder.add_edge("weather", "synthesizer")
```

---

## Slide 36: Tool Composition

### Simple Tool

```python
@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return fetch_weather_api(location)
```

### Composite Tool (Tool + LLM)

```python
@tool
async def smart_destination_research(destination: str, interests: list) -> str:
    """
    Research a destination intelligently.
    
    Uses RAG, web search, and LLM reasoning to provide comprehensive insights.
    """
    # Step 1: Try RAG
    rag_results = await rag_service.search(destination, interests)
    
    # Step 2: Augment with web search
    web_results = await web_search_api(f"{destination} {' '.join(interests)}")
    
    # Step 3: Let LLM synthesize
    synthesis = await llm.ainvoke([
        HumanMessage(f"""
            Combine these sources into a cohesive guide for {destination}:
            
            RAG Results:
            {rag_results}
            
            Web Results:
            {web_results}
            
            Format as a travel guide.
        """)
    ])
    
    return synthesis.content
```

---

## Slide 37: Monitoring & Alerting

### Metrics to Track

```python
from prometheus_client import Counter, Histogram, Gauge

# Success/failure rates
success_counter = Counter(
    'trip_plans_successful',
    'Total successful trip plans'
)
failure_counter = Counter(
    'trip_plans_failed',
    'Total failed trip plans'
)

# Latency
plan_duration = Histogram(
    'trip_plan_duration_seconds',
    'Time to generate a trip plan'
)

# Queue depth
queue_depth = Gauge(
    'pending_plans',
    'Number of plans waiting to be processed'
)

def _record_execution(node_name, duration, success):
    if success:
        success_counter.inc()
    else:
        failure_counter.inc()
    
    plan_duration.observe(duration)
```

### Alerting

```python
# Alert if latency exceeds threshold
if plan_duration > 30_000:  # 30 seconds
    send_alert("Trip planner slow!", f"Duration: {plan_duration}ms")

# Alert if failure rate > 5%
if failure_counter.count / (success_counter.count + failure_counter.count) > 0.05:
    send_alert("High failure rate!", "Check error logs")
```

---

## Slide 38: Real-World Adaptations

### Use Case: PR Description Generator

Adapt the trip planner to auto-generate GitHub PR descriptions:

```python
# Replace nodes
research_node     → code_analyzer (analyze diff)
weather_node      → impact_analyzer (check affected services)
budget_node       → risk_analyzer (potential issues)
journey_plan_node → description_generator (create PR description)

# State changes
TripState → PRState
  destination → repo_name
  budget → affected_services
  weather → risk_level
  final → pr_description

# Tools
get_destination_info → get_code_diff
get_costs → get_risk_assessment
get_weather → get_related_tests
```

### Use Case: Customer Support Classifier

```python
# Nodes
research_node → knowledge_base_search
weather_node  → sentiment_analyzer
budget_node   → priority_calculator
journey_plan  → response_generator

# Execution
Classify ticket (low/med/high priority)
  ↓
Fetch relevant KB articles
  ↓
Determine sentiment & escalation risk
  ↓
Generate response template
```

---

## Slide 39: Future of Agentic Programming

### Emerging Patterns

1. **Multi-Turn Conversations** - Agents that remember context across turns
2. **Hierarchical Agents** - Agents that manage sub-agents
3. **Tool Learning** - Agents that learn which tools work best
4. **Reflection** - Agents that critique their own outputs
5. **Human-in-the-Loop** - Agents that ask for clarification

### Example: Reflection Loop

```python
def _reflection_node(state):
    """Agent critiques its own output."""
    itinerary = state.get("final", "")
    
    critique = llm.invoke(f"""
        Review this itinerary for issues:
        {itinerary}
        
        Check for:
        1. Infeasible timing (too much travel)?
        2. Budget overruns?
        3. Weather conflicts?
        
        Return: GOOD or NEEDS_IMPROVEMENT
    """)
    
    if "NEEDS_IMPROVEMENT" in critique.content:
        return {"needs_revision": True}
    else:
        return {"needs_revision": False}

builder.add_conditional_edges(
    "journey_plan",
    lambda state: "refine" if state.get("needs_revision") else "end",
    {"refine": "refine_node", "end": END}
)
```

---

## Slide 40: Recap & Your Turn

### What We Learned

✅ Agentic programming moves beyond single LLM calls to orchestrated workflows  
✅ LangGraph provides state management, parallelism, and observability  
✅ State is shared, immutable data passed between nodes  
✅ Nodes can be async, use tools, call LLMs, or run custom logic  
✅ Parallel execution dramatically improves latency  
✅ Error handling & fallbacks make systems resilient  
✅ Observability (tracing) is essential for debugging  
✅ RAG + tools + LLM reasoning create powerful AI systems  

### Your Challenge

**Adapt the Trip Planner for Your Domain:**

1. **Choose a domain** (PR generator? Customer support? Research assistant?)
2. **Identify your agents** (what tasks happen in parallel?)
3. **Design your state** (what data flows between agents?)
4. **Build your tools** (what APIs/databases do agents call?)
5. **Deploy & monitor** (observe performance, iterate)

### Resources

- 📚 [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- 🔗 [AI Trip Planner Repo](https://github.com/trieu/ai-trip-planner)
- 🧪 [Backend Tests](backend/tests/)
- 📊 [Arize Phoenix Observability](https://phoenix.arize.com/)
- 💬 [LangChain Discord](https://discord.gg/6adMQxSpJS)

### Final Thoughts

> "Agentic programming is not about replacing humans—it's about augmenting them with specialized AI workers that collaborate to solve complex problems faster, better, and with full observability."

**Now go build something amazing! 🚀**

---

## Appendix A: Full Trip Planner Code Example

### Complete SmartTripPlanner Implementation

```python
# backend/core_llm/smart_trip_planner.py (simplified)

import logging
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END, START
from core_llm.state_models import TripState
from core_llm.meta_llm import MetaLLM
from services import DataServiceFactory
from tools.travel_tools import get_destination_info, get_costs
from tools.weather_tools import get_current_weather

logger = logging.getLogger(__name__)

class SmartTripPlanner:
    def __init__(self):
        self.llm = MetaLLM.get_llm(temperature=0.7)
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
        
        # Edges
        builder.add_edge(START, "load_profile")
        builder.add_edge("load_profile", "research")
        builder.add_edge("load_profile", "weather")
        builder.add_edge("load_profile", "budget")
        builder.add_edge("research", "aggregate")
        builder.add_edge("weather", "aggregate")
        builder.add_edge("budget", "aggregate")
        builder.add_edge("aggregate", "journey_plan")
        builder.add_edge("journey_plan", END)
        
        return builder.compile()
    
    def _profile_node(self, state: TripState) -> Dict[str, Any]:
        user_id = state["trip_request"].get("user_id")
        interests = state["trip_request"].get("interests", "")
        
        profile = {}
        if user_id:
            profile = self.profile_service.get_user_profile(user_id)
        
        profile.setdefault("current_interests", interests.split(",") if interests else [])
        return {"user_profile": profile}
    
    async def _research_node(self, state: TripState) -> Dict[str, Any]:
        dest = state["trip_request"]["destination"]
        interests = state["user_profile"].get("current_interests", [])
        
        try:
            summary = await get_destination_info.ainvoke({
                "location": dest,
                "interests": interests
            })
        except Exception as e:
            logger.error(f"Research failed: {e}")
            summary = f"Unable to fetch research for {dest}"
        
        return {
            "research": summary,
            "tool_calls": [{"tool": "get_destination_info", "args": {"location": dest}}]
        }
    
    def _weather_node(self, state: TripState) -> Dict[str, Any]:
        dest = state["trip_request"]["destination"]
        
        try:
            weather = get_current_weather.invoke({"location": dest})
        except Exception as e:
            logger.error(f"Weather failed: {e}")
            weather = "Weather data unavailable"
        
        return {
            "weather": weather,
            "tool_calls": [{"tool": "get_current_weather", "args": {"location": dest}}]
        }
    
    def _budget_node(self, state: TripState) -> Dict[str, Any]:
        dest = state["trip_request"]["destination"]
        duration = state["trip_request"].get("duration", "7 days")
        budget = state["trip_request"].get("budget", "$1000")
        
        try:
            costs = get_costs.invoke({"location": dest, "duration": duration})
        except Exception as e:
            logger.error(f"Budget failed: {e}")
            costs = "Cost analysis unavailable"
        
        return {
            "budget": costs,
            "tool_calls": [{"tool": "get_costs", "args": {"location": dest}}]
        }
    
    def _aggregate_node(self, state: TripState) -> Dict[str, Any]:
        # Combine all parallel outputs
        return {
            "aggregated_context": {
                "destination": state["trip_request"]["destination"],
                "research": state.get("research", ""),
                "weather": state.get("weather", ""),
                "budget": state.get("budget", ""),
                "interests": state["user_profile"].get("current_interests", [])
            }
        }
    
    async def _journey_plan_node(self, state: TripState) -> Dict[str, Any]:
        context = state.get("aggregated_context", {})
        
        prompt = f"""
        Create a personalized itinerary for {context['destination']}.
        
        Research: {context['research']}
        Weather: {context['weather']}
        Budget: {context['budget']}
        Interests: {', '.join(context['interests'])}
        
        Format as a day-by-day plan with timings and costs.
        """
        
        response = await self.llm.ainvoke([
            SystemMessage("You are a world-class travel planner."),
            HumanMessage(prompt)
        ])
        
        return {
            "final": response.content,
            "messages": [response]
        }
    
    async def plan(self, trip_request: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for planning a trip."""
        initial_state = {
            "trip_request": trip_request,
            "messages": [],
            "tool_calls": [],
            "user_profile": {},
        }
        
        return await self.app.ainvoke(initial_state)

# Usage
if __name__ == "__main__":
    import asyncio
    
    planner = SmartTripPlanner()
    
    request = {
        "destination": "Tokyo, Japan",
        "duration": "7 days",
        "budget": "$2000",
        "interests": "food, culture",
        "user_id": "user_123"
    }
    
    result = asyncio.run(planner.plan(request))
    print(result["final"])
```

---

## Appendix B: Quick Reference

### StateGraph API Cheat Sheet

```python
# Create
builder = StateGraph(YourStateType)

# Add nodes
builder.add_node("name", function_or_callable)

# Add edges
builder.add_edge(START, "first_node")
builder.add_edge("node_a", "node_b")
builder.add_edge("node_c", END)

# Conditional edges
builder.add_conditional_edges("node", routing_fn, {"path1": "node1", "path2": "node2"})

# Compile
app = builder.compile()

# Run
result = app.invoke(initial_state)  # Sync
result = await app.ainvoke(initial_state)  # Async

# Stream
for step in app.stream(initial_state):
    print(step)

# Check graph structure
print(app.get_graph().draw_mermaid())
```

### Common Imports

```python
from typing import Dict, Any, Optional, List
from typing_extensions import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain.tools import tool
from pydantic import BaseModel, Field
```

---

**End of Lecture** 🎓

*Last updated: 2026-05-24*  
*For questions: See LangGraph docs or raise an issue in the AI Trip Planner repo*
