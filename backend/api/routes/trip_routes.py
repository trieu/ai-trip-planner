"""
Trip planning API endpoints.
"""

from typing import Any

import logging
from fastapi import APIRouter, HTTPException

from config import get_settings
from core_llm.smart_trip_planner import SmartTripPlanner, safe_attributes
from services.data_models.travel_models import TripRequest, TripResponse
from tasks.agent_tasks import generate_trip_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trips")
settings = get_settings()

# Instantiate once at startup
planner = SmartTripPlanner()


# ============================================================================
# Helpers
# ============================================================================

def extract_text(content: Any) -> str:
    """
    Normalize output from Gemini/OpenAI/LangChain into plain text.

    Supported:
    - str
    - dict(text=...)
    - list[dict(type=text)]
    - list[str]
    - AIMessage-like content blocks
    """

    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])

        return str(content)

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:

            if item is None:
                continue

            if isinstance(item, str):
                parts.append(item)
                continue

            if isinstance(item, dict):

                # Gemini / LangChain content block
                if item.get("type") == "text":
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                    continue

                # Generic dict containing text
                if "text" in item:
                    parts.append(str(item["text"]))
                    continue

            parts.append(str(item))

        return "\n".join(
            p.strip()
            for p in parts
            if p and p.strip()
        )

    return str(content)


def deduplicate_tool_calls(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Remove duplicated tool calls.
    """

    unique_calls = []
    seen = set()

    for call in tool_calls:

        key = (
            call.get("tool"),
            str(call.get("args", {})),
        )

        if key in seen:
            continue

        seen.add(key)
        unique_calls.append(call)

    return unique_calls


def build_trip_response(
    graph_result: dict[str, Any],
) -> TripResponse:
    """
    Convert graph result into API response.
    """

    final_text = extract_text(
        graph_result.get("final")
    )

    tool_calls = deduplicate_tool_calls(
        graph_result.get("tool_calls", [])
    )

    return TripResponse(
        result=final_text,
        tool_calls=tool_calls,
    )


# ============================================================================
# Routes
# ============================================================================

@router.post("/plan", response_model=TripResponse)
async def plan_trip(req: TripRequest):
    """
    Generate a personalized trip itinerary.
    """

    initial_state = {
        "messages": [],
        "trip_request": req.model_dump(),
        "tool_calls": [],
        "user_profile": {},
    }

    with safe_attributes(
        {
            "session.id": req.session_id or "default",
            "user.id": req.user_id or "anonymous",
            "endpoint": "/api/v1/trips/plan",
        }
    ):
        try:
            logger.info(
                "Trip planning started",
                extra={
                    "user_id": req.user_id,
                    "session_id": req.session_id,
                    "destination": req.destination,
                },
            )

            graph_result = await planner.invoke(
                initial_state
            )

            response = build_trip_response(
                graph_result
            )

            logger.info(
                "Trip planning completed",
                extra={
                    "user_id": req.user_id,
                    "session_id": req.session_id,
                    "destination": req.destination,
                    "result_length": len(response.result),
                    "tool_call_count": len(
                        response.tool_calls
                    ),
                },
            )

            logger.debug(
                "Planner result keys=%s",
                list(graph_result.keys()),
            )

            return response

        except Exception:
            logger.exception(
                "Trip planning failed",
                extra={
                    "user_id": req.user_id,
                    "session_id": req.session_id,
                    "destination": req.destination,
                    "travel_style": req.travel_style,
                },
            )

            raise HTTPException(
                status_code=500,
                detail="Failed to generate trip itinerary",
            )


@router.get("/search")
async def search_destinations(
    query: str,
    limit: int = 10,
):
    """
    Search for travel destinations.
    """

    try:
        return {
            "query": query,
            "results": [],
            "count": 0,
        }

    except Exception:
        logger.exception(
            "Destination search failed",
            extra={
                "query": query,
                "limit": limit,
            },
        )

        raise HTTPException(
            status_code=500,
            detail="Destination search failed",
        )


@router.get("/{trip_id}")
async def get_trip(trip_id: str):
    """
    Retrieve a previously planned trip.
    """

    try:
        return {
            "trip_id": trip_id,
            "destination": "Unknown",
            "itinerary": [],
        }

    except Exception:
        logger.exception(
            "Trip retrieval failed",
            extra={
                "trip_id": trip_id,
            },
        )

        raise HTTPException(
            status_code=404,
            detail="Trip not found",
        )


# ============================================================================
# Test Route for Agent Task
# ============================================================================

@router.post("/test-agent")
async def test_agent(payload: TripRequest):
    """
    Fire-and-forget async agent execution.
    """

    try:
        generate_trip_plan.send(
            payload.user_id,
            payload.destination,
        )

        logger.info(
            "Trip planning task queued",
            extra={
                "user_id": payload.user_id,
                "destination": payload.destination,
            },
        )

        return {
            "status": "queued",
            "user_id": payload.user_id,
            "message": "Trip planning started",
        }

    except Exception:
        logger.exception(
            "Failed to queue trip planning task",
            extra={
                "user_id": payload.user_id,
                "destination": payload.destination,
            },
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to start trip planning",
        )