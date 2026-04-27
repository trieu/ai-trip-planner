"""
Task definitions for background processing with Dramatiq.
"""

from .agent_tasks import generate_trip_plan

__all__ = ["generate_trip_plan"]