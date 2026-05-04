from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ================================
# Data Models (Pydantic) for Travel Planning Agents
# ================================
class TripRequest(BaseModel):
    """Schema for incoming trip planning requests."""
    destination: str
    duration: Optional[str] = "3 days"
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