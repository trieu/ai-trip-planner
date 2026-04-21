import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv, find_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from smart_trip_planner import SmartTripPlanner, safe_attributes

# ================================
# Environment Setup
# ================================
load_dotenv(find_dotenv(), override=True)

# ================================
# Data Models (Pydantic)
# ================================
class TripRequest(BaseModel):
    """Schema for incoming trip planning requests."""
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
    """Schema for successful trip plan responses."""
    result: str
    tool_calls: List[Dict[str, Any]] = []

# ================================
# Application Initialization
# ================================
app = FastAPI(title="Gemini Trip Planner API", version="1.0.0")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Instantiate the engine globally so the graph is only compiled once
planner = SmartTripPlanner()

# ================================
# API Routes
# ================================
@app.post("/plan-trip", response_model=TripResponse)
async def plan_trip(req: TripRequest):
    """
    Endpoint to generate a personalized trip itinerary.
    Triggers the LangGraph workflow via SmartTripPlanner.
    """
    
    # Setup the initial state for LangGraph
    initial_state = {
        "messages": [],
        "trip_request": req.model_dump(),
        "tool_calls": [],
        "user_profile": {},
    }

    # Execute with telemetry wrappers
    with safe_attributes({
        "session.id": req.session_id or "default",
        "user.id": req.user_id or "anonymous",
        "endpoint": "/plan-trip"
    }):
        try:
            # Trigger the AI graph
            result = planner.invoke(initial_state)

            return TripResponse(
                result=result.get("final", "Failed to generate journey plan."),
                tool_calls=result.get("tool_calls", [])
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)