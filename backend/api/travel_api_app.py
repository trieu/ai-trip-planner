import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from api.routes import trip_routes, persona_routes, health_routes, auth_routes

settings = get_settings()
logger = logging.getLogger(__name__)

# ========================================
# Lifespan Handler (Replaces on_event)
# ========================================
@asynccontextmanager
async def travel_app_lifespan(app: FastAPI):
    """
    Handles startup and shutdown logic for the Travel API.
    Replaces the deprecated @app.on_event handlers.
    """
    # --- STARTUP CHECKS ---
    logger.info("🔍 Running startup validation...")
    
    # 1. Validate LLM Configuration
    if settings.LLM_PROVIDER == "OPENAI" and not settings.OPENAI_API_KEY:
        logger.error("❌ Missing OPENAI_API_KEY")
        raise RuntimeError("Application cannot start without OpenAI API Key.")
    
    if settings.LLM_PROVIDER == "GOOGLE_GEMINI" and not settings.GOOGLE_GEMINI_API_KEY:
        logger.error("❌ Missing GOOGLE_GEMINI_API_KEY")
        raise RuntimeError("Application cannot start without Google Gemini API Key.")

    # 2. Ensure Filesystem Readiness
    required_dirs = [
        settings.PERSONA_DATA_DIR, 
        settings.REPORTS_DATA_DIR, 
        settings.TEMPLATES_DIR
    ]
    for directory in required_dirs:
        os.makedirs(directory, exist_ok=True)
    
    logger.info("✅ Runtime environment validated.")
    
    yield  # --- Application is running ---

    # --- SHUTDOWN LOGIC ---
    logger.info("🛑 Cleaning up Travel API resources...")
    # Add cleanup here: e.g., await db.disconnect(), redis.close()
    logger.info("✅ Shutdown complete.")


def create_travel_app() -> FastAPI:
    """
    Factory function to initialize the Travel Trip Planner FastAPI instance.
    """
    app = FastAPI(
        title="AI Trip Planner API",
        description="Personalized travel itinerary planning with AI",
        version="1.0.0",
        lifespan=travel_app_lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Routes Configuration
    api_base = f"{settings.API_PREFIX}/{settings.API_VERSION}"

    # Standard Domains
    app.include_router(health_routes.router, prefix=api_base, tags=["health"])
    app.include_router(trip_routes.router, prefix=api_base, tags=["trips"])
    app.include_router(auth_routes.router, prefix=settings.API_PREFIX, tags=["auth"])

    # Optional Domains
    if settings.ENABLE_PERSONA_REPORTS:
        app.include_router(persona_routes.router, prefix=api_base, tags=["personas"])

    # Exception Handling
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global Error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(exc) if settings.is_development else "An unexpected error occurred."
            }
        )

    return app