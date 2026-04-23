
import operator

from typing import Optional, List, Dict, Any
from typing_extensions import TypedDict, Annotated

from langchain_core.messages import BaseMessage

# ================================
# LangGraph State Definition
# ================================

class TripState(TypedDict):
    """Defines the state passed between LangGraph nodes."""
    messages: Annotated[List[BaseMessage], operator.add]
    trip_request: Dict[str, Any]
    user_profile: Dict[str, Any]
    location_coords: Optional[Dict[str, float]]
    research: Optional[str]
    weather: Optional[str]
    budget: Optional[str]
    final: Optional[str]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]
