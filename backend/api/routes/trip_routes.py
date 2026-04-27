"""
Trip planning API endpoints.
"""

from core_llm.smart_trip_planner import SmartTripPlanner, safe_attributes
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List, Dict, Any
import logging

from services.data_models.schemas import TripRequest, TripResponse
from config import get_settings

from tasks.agent_tasks import generate_trip_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trips")
settings = get_settings()

# Instantiate the engine globally so the graph is only compiled once
planner = SmartTripPlanner()


@router.post("/plan", response_model=TripResponse)
async def plan_trip(req: TripRequest):
    """
    Generate a personalized trip itinerary.

    Args:
        req: Trip planning request with destination, duration, budget, interests, etc.

    Returns:
        TripResponse with generated itinerary and tool calls.

    Example:
        POST /api/v1/trips/plan
        {
            "destination": "Tokyo",
            "duration": "7 days",
            "budget": "moderate",
            "interests": "culture, food, temples",
            "travel_style": "adventurous"
        }
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
        "endpoint": "/api/v1/trips/plan"
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


@router.get("/search")
async def search_destinations(query: str, limit: int = 10):
    """
    Search for travel destinations.

    Args:
        query: Search query (city, country, region)
        limit: Maximum results to return

    Returns:
        List of matching destinations
    """
    try:
        # TODO: Implement destination search
        return {
            "query": query,
            "results": [],
            "count": 0
        }
    except Exception as e:
        logger.error(f"Error searching destinations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trip_id}")
async def get_trip(trip_id: str):
    """
    Retrieve a previously planned trip.

    Args:
        trip_id: Unique trip identifier

    Returns:
        Trip details and itinerary
    """
    try:
        # TODO: Implement trip retrieval from cache/database
        return {
            "trip_id": trip_id,
            "destination": "Unknown",
            "itinerary": []
        }
    except Exception as e:
        logger.error(f"Error retrieving trip: {str(e)}")
        raise HTTPException(status_code=404, detail="Trip not found")

# ========================================
# Test Route for Agent Task
# ========================================
@router.post("/test-agent")
async def plan_trip(payload: TripRequest):
    """
    Fire-and-forget async agent execution
    """
    generate_trip_plan.send(payload.user_id, payload.destination)

    return {
        "status": "queued",
        "user_id": payload.user_id,
        "message": "Trip planning started"
    }