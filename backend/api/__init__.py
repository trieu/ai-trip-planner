"""
API module for FastAPI routes and application setup. 
This module serves as the entry point for all API-related logic, including route definitions, middleware, and application lifecycle management.
"""

from .routes import trip_routes, persona_routes, health_routes, auth_routes
from .travel_api_app import create_travel_app

__all__ = ["trip_routes", "persona_routes", "health_routes", "auth_routes", "create_travel_app"]