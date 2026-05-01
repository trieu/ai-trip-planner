"""
constants.py

All configuration and constants used across the planner.
Centralized for easier testing and tuning.
"""

# LLM
from config import Settings


LLM_TEMPERATURE = Settings().LLM_TEMPERATURE

# Defaults
DEFAULT_WEATHER_FALLBACK = "Weather service unavailable."
INVALID_DESTINATION_MSG = "Weather unavailable due to invalid destination."

# Observability
SERVICE_NAME = "smart_trip_planner"

# Agent types (for tracing consistency)
AGENT_RESEARCH = "research"
AGENT_BUDGET = "budget"
AGENT_JOURNEY = "journey_plan"
AGENT_PROFILE = "profile"

