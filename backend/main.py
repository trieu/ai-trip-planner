import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv, find_dotenv

from tools.auth import get_current_user
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse  # Added for serving files
from fastapi.staticfiles import StaticFiles # Added for serving directory assets
from pydantic import BaseModel

from core_llm.smart_trip_planner import SmartTripPlanner, safe_attributes

# ================================
# Environment Setup
# ================================
load_dotenv(find_dotenv(), override=True)

# Define the frontend directory from environment variables or default to "frontend"
FRONTEND_DIR = os.getenv("FRONTEND_DIR", "../frontend")

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

# Mount the static directory to serve CSS, JS, and Images
# This makes files in FRONTEND_DIR accessible at /assets/*
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")

# Instantiate the engine globally so the graph is only compiled once
planner = SmartTripPlanner()

# ================================
# API Routes
# ================================

@app.get("/")
@app.get("/index.html")
async def serve_index():
    """
    Returns the static index.html from the configured frontend folder.
    """
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    
    if not os.path.exists(index_path):
        # Fallback message if the file is missing
        return {"message": "Frontend index.html not found. Check FRONTEND_DIR config."}
        
    return FileResponse(index_path)

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

@app.get("/profile")
async def get_profile(user=Depends(get_current_user)):
    # TODO: Implement actual profile retrieval logic    
    return {
        "message": "secure data",
        "user": user
    }

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host=HOST, port=PORT)