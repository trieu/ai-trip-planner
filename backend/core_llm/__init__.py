"""
Core module initialization for configuration and utilities.
"""

# Import the factory from the internal module
from .prompt_builder import build_trip_planner_prompt
from .state_models import TripState
from .smart_trip_planner import SmartTripPlanner, safe_attributes
from .config import Settings, get_settings, settings

# Define what is accessible when someone imports * from services
__all__ = ["build_trip_planner_prompt", "TripState", "SmartTripPlanner", "safe_attributes","Settings", "get_settings", "settings"]

